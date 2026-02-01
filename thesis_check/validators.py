from __future__ import annotations

"""Output validators (structure > truth).

We validate the strict 4-line templates for both agents to keep outputs comparable,
machine-checkable, and stable for logging/screenshotting.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Dict, List, Optional, Tuple

__all__ = [
    "AgentRole",
    "truncate",
    "stop_phrase_hit",
    "similarity",
    "validate_agent_output",
    "too_similar",
    "parse_template",
    "TemplateSpec",
    "SPEC_A",
    "SPEC_B",
    "SIMILARITY_THRESHOLD",
]

# Anti-mirroring threshold: outputs above this similarity are rejected
SIMILARITY_THRESHOLD = 0.92


class AgentRole(Enum):
    """Agent roles in the debate."""

    PRO = "A"
    CONTRA = "B"


@dataclass(frozen=True)
class TemplateSpec:
    keys: Tuple[str, str, str, str]


SPEC_A = TemplateSpec(keys=("PRO1", "PRO2", "NEW_ASSUMPTION", "RISK"))
SPEC_B = TemplateSpec(keys=("CONTRA1", "CONTRA2", "ASSUMPTION_CHECK", "EDGE_CASE"))


def truncate(txt: str, max_chars: int) -> str:
    return txt[:max_chars] if len(txt) > max_chars else txt


def stop_phrase_hit(text: str, stop_phrases: List[str]) -> bool:
    t = (text or "").lower()
    return any((p or "").lower() in t for p in stop_phrases)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(a=(a or "").lower().strip(), b=(b or "").lower().strip()).ratio()


def parse_template(text: str, spec: TemplateSpec) -> Optional[Dict[str, str]]:
    """Parse strict 4-line '- KEY: value' template into a dict, or return None if invalid."""
    lines = [ln.rstrip() for ln in (text or "").strip().splitlines() if ln.strip()]
    if len(lines) != 4:
        return None

    out: Dict[str, str] = {}
    for ln in lines:
        if not ln.startswith("- "):
            return None
        if ":" not in ln:
            return None

        left, right = ln[2:].split(":", 1)
        key = left.strip()
        val = right.strip()

        if not key or not val:
            return None
        if key in out:  # reject duplicate keys (dict would otherwise overwrite)
            return None

        out[key] = val

    # Must match keys exactly (no missing or extra keys)
    if set(out.keys()) != set(spec.keys):
        return None

    return out


def validate_agent_output(text: str, which: AgentRole | str) -> bool:
    """Return True iff the agent output matches the strict template for A or B."""
    if isinstance(which, str):
        which = AgentRole(which)
    spec = SPEC_A if which == AgentRole.PRO else SPEC_B
    return parse_template(text, spec) is not None


def too_similar(
    candidate: str, previous_other: str, threshold: float = SIMILARITY_THRESHOLD
) -> bool:
    """Heuristic to detect mirroring/repetition between agents."""
    if not (previous_other or "").strip():
        return False
    return similarity(candidate, previous_other) >= threshold
