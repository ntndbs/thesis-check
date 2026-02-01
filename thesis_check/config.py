from __future__ import annotations

"""Configuration via environment variables.

Settings are loaded from `.env` (local) and the process environment (CI/production).
This keeps code provider-agnostic: you can swap models, temperatures, stop criteria,
and logging paths without touching Python code.
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv

__all__ = [
    "Settings",
    "AGENT_MAX_RETRIES",
    "JUDGE_MAX_RETRIES",
    "FIELD_TRUNCATE_CHARS",
    "EVIDENCE_ITEM_CHARS",
    "MAX_EVIDENCE_ITEMS",
]

# Retry counts for template compliance
AGENT_MAX_RETRIES = 3
JUDGE_MAX_RETRIES = 2

# Truncation limits for judge output fields
FIELD_TRUNCATE_CHARS = 800
EVIDENCE_ITEM_CHARS = 200
MAX_EVIDENCE_ITEMS = 10


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v == "" else v


def _env_float(name: str, default: str) -> float:
    try:
        return float(_env(name, default))
    except ValueError:
        return float(default)


def _env_int(name: str, default: str) -> int:
    try:
        return int(_env(name, default))
    except ValueError:
        return int(default)


def _env_int_optional(name: str) -> Optional[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str

    model_creative: str
    model_critical: str
    model_judge: str

    temp_a: float
    temp_b: float
    temp_j: float

    max_rounds: int
    convergence_delta: float
    stop_phrases: List[str]

    max_chars_agent: int
    max_chars_judge: int

    seed: Optional[int]
    log_dir: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables (with sane defaults)."""
        # Do not override already-set environment variables.
        load_dotenv(override=False)

        stop_phrases = [
            s.strip()
            for s in _env("STOP_PHRASES", "agreement reached;no new points").split(";")
            if s.strip()
        ]

        return cls(
            base_url=_env("LOCAL_BASE_URL", "http://127.0.0.1:1234/v1"),
            api_key=_env("LOCAL_API_KEY", "lm-studio"),
            model_creative=_env("MODEL_CREATIVE", "qwen2.5-7b-instruct"),
            model_critical=_env("MODEL_CRITICAL", "qwen2.5-7b-instruct"),
            model_judge=_env("MODEL_JUDGE", "qwen2.5-7b-instruct"),
            temp_a=_env_float("TEMP_A", "0.8"),
            temp_b=_env_float("TEMP_B", "0.2"),
            temp_j=_env_float("TEMP_J", "0.2"),
            max_rounds=_env_int("MAX_ROUNDS", "3"),
            convergence_delta=_env_float("CONVERGENCE_DELTA", "0.02"),
            stop_phrases=stop_phrases,
            max_chars_agent=_env_int("MAX_CHARS_AGENT", "700"),
            max_chars_judge=_env_int("MAX_CHARS_JUDGE", "2500"),
            seed=_env_int_optional("SEED"),
            log_dir=_env("LOG_DIR", "runs"),
        )

    def validate(self) -> None:
        """Validate settings constraints. Raises ValueError if invalid."""
        errors: List[str] = []

        if self.max_rounds < 1:
            errors.append("max_rounds must be >= 1")
        if self.convergence_delta <= 0:
            errors.append("convergence_delta must be > 0")
        if not (0 <= self.temp_a <= 2):
            errors.append("temp_a must be in [0, 2]")
        if not (0 <= self.temp_b <= 2):
            errors.append("temp_b must be in [0, 2]")
        if not (0 <= self.temp_j <= 2):
            errors.append("temp_j must be in [0, 2]")
        if self.max_chars_agent < 100:
            errors.append("max_chars_agent must be >= 100")
        if self.max_chars_judge < 100:
            errors.append("max_chars_judge must be >= 100")
        if not self.base_url:
            errors.append("base_url cannot be empty")

        if errors:
            raise ValueError(f"Invalid settings: {'; '.join(errors)}")
