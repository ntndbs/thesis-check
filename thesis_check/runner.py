from __future__ import annotations

"""
Debate orchestration.

Design:
- Two agents (PRO/CONTRA) produce strict 4-line templates (easy to validate + compare).
- A judge summarizes ONLY the last round and outputs strict JSON with a conservative probability.
- Robustness: retries for template drift/mirroring; JSON repair for occasional malformed judge output.
- Efficiency: compact history (last round) to keep local inference fast and stable.
- Auditability: JSONL logs per run for reproducibility and screenshots.
"""

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Tuple

from .config import (
    AGENT_MAX_RETRIES,
    EVIDENCE_ITEM_CHARS,
    FIELD_TRUNCATE_CHARS,
    JUDGE_MAX_RETRIES,
    MAX_EVIDENCE_ITEMS,
    Settings,
)
from .llm import LLM
from .prompts import ROLE_A, ROLE_B, ROLE_JUDGE, SYSTEM_SAFETY
from .validators import AgentRole, stop_phrase_hit, too_similar, truncate, validate_agent_output

__all__ = ["JudgeOut", "JsonlLogger", "run_duel", "parse_judge"]

# Regex to find JSON object in text (handles nested braces)
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")


@dataclass
class JudgeOut:
    summary: str
    key_evidence_for: List[str]
    key_evidence_against: List[str]
    verdict: str
    probability: float


def _judge_from_obj(obj: dict) -> JudgeOut:
    """Normalize judge JSON into a typed object and clamp probability to [0, 1]."""
    p = float(obj.get("probability", 0.5))
    p = max(0.0, min(1.0, p))
    return JudgeOut(
        summary=str(obj.get("summary", "")),
        key_evidence_for=list(obj.get("key_evidence_for", []))[:MAX_EVIDENCE_ITEMS],
        key_evidence_against=list(obj.get("key_evidence_against", []))[:MAX_EVIDENCE_ITEMS],
        verdict=str(obj.get("verdict", "")),
        probability=p,
    )


def parse_judge(raw: str) -> JudgeOut:
    """Parse the first valid JSON object found in the judge output."""
    raw = (raw or "").strip()

    # Fast path: the model returned pure JSON
    try:
        return _judge_from_obj(json.loads(raw))
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fallback: find JSON objects using regex (more efficient than O(n²) scan)
    for match in _JSON_OBJECT_RE.finditer(raw):
        try:
            return _judge_from_obj(json.loads(match.group()))
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    return JudgeOut(
        summary="JSON-Fallback",
        key_evidence_for=[],
        key_evidence_against=[],
        verdict=raw[:FIELD_TRUNCATE_CHARS],
        probability=0.5,
    )


class JsonlLogger:
    """Append-only JSONL log for auditability and easy screenshotting."""

    def __init__(self, log_dir: str):
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.path = Path(log_dir) / f"run-{ts}.jsonl"
        self._file: Optional[IO[str]] = None

    def _ensure_open(self) -> IO[str]:
        if self._file is None or self._file.closed:
            self._file = self.path.open("a", encoding="utf-8")
        return self._file

    def write(self, event: Dict[str, Any]) -> None:
        event["ts"] = time.time()
        f = self._ensure_open()
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()

    def close(self) -> None:
        if self._file is not None and not self._file.closed:
            self._file.close()

    def __enter__(self) -> "JsonlLogger":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _agent_messages(role_prompt: str, thesis: str, history_compact: str) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_SAFETY},
        {"role": "system", "content": role_prompt},
    ]
    if history_compact.strip():
        msgs.append({"role": "user", "content": f"Context (last round, condensed):\n{history_compact}"})
    msgs.append({"role": "user", "content": f"Thesis: {thesis}\nFollow the required template strictly."})
    return msgs


def _first_4_lines(text: str) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(lines[:4])


def _compact_history(last_pro: str, last_con: str) -> str:
    """Keep context small: last round only (token budget + stability)."""
    if not last_pro and not last_con:
        return ""
    return f"Last PRO:\n{_first_4_lines(last_pro)}\n\nLast CONTRA:\n{_first_4_lines(last_con)}"


def agent_call_validated(
    llm: LLM,
    model: str,
    role_prompt: str,
    thesis: str,
    last_other: str,
    last_self: str,
    history_compact: str,
    temperature: float,
    max_chars: int,
    which: AgentRole | str,
) -> str:
    """Call an agent with strict template enforcement and anti-repetition.

    We retry a few times because local models occasionally drift from strict formats.
    On retry, we add a stronger instruction to force novelty and reduce mirroring.
    """
    if isinstance(which, str):
        which = AgentRole(which)

    for attempt in range(AGENT_MAX_RETRIES):
        msgs = _agent_messages(role_prompt, thesis, history_compact)

        if attempt > 0:
            # Retry only: force novelty + strict compliance (prevents repetition/mirroring).
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        "IMPORTANT: Output exactly 4 lines and ONLY those 4 lines. "
                        "Do not add any other text. Do not output JSON. "
                        "Provide entirely new points from a different angle. "
                        "Do not repeat yourself and do not mirror the other agent. "
                        "Follow the template exactly."
                    ),
                }
            )

        out = truncate(llm.chat(model=model, messages=msgs, temperature=temperature), max_chars)

        if not validate_agent_output(out, which=which):
            continue
        if last_other and too_similar(out, last_other):
            continue
        if last_self and too_similar(out, last_self):
            continue

        return out

    # All retries failed, return a safe placeholder
    if which == AgentRole.PRO:
        return (
            "- PRO1: (Error) The model did not reliably follow the required template.\n"
            "- PRO2: Re-run or adjust the prompt/model settings.\n"
            "- NEW_ASSUMPTION: The model failed template compliance.\n"
            "- RISK: The evaluation may be limited."
        )

    return (
        "- CONTRA1: (Error) The model did not reliably follow the required template.\n"
        "- CONTRA2: Re-run or adjust the prompt/model settings.\n"
        "- ASSUMPTION_CHECK: The model failed template compliance.\n"
        "- EDGE_CASE: The evaluation may be limited."
    )


def judge_call(llm: LLM, settings: Settings, thesis: str, pros_last: str, cons_last: str) -> JudgeOut:
    """Ask the judge for strict JSON on the last round only.

    If JSON parsing fails, we run a repair prompt (temp=0) to convert the output into valid JSON.
    """
    base_msgs = [
        {"role": "system", "content": SYSTEM_SAFETY},
        {"role": "system", "content": ROLE_JUDGE},
        {
            "role": "user",
            "content": (
                f"Thesis: {thesis}\n\n"
                f"PRO (last round):\n{pros_last}\n\n"
                f"CONTRA (last round):\n{cons_last}"
            ),
        },
    ]

    raw = ""
    parsed: Optional[JudgeOut] = None

    for attempt in range(JUDGE_MAX_RETRIES):
        msgs = list(base_msgs)
        if attempt > 0:
            msgs.append({"role": "system", "content": "STRICT: Reply with valid JSON only. No extra text."})

        raw = llm.chat(model=settings.model_judge, messages=msgs, temperature=settings.temp_j)
        parsed = parse_judge(raw)

        if parsed.summary != "JSON-Fallback" and parsed.verdict:
            break

    out = parsed if parsed else parse_judge(raw)

    if out.summary == "JSON-Fallback":
        # Some local models emit extra tokens or malformed JSON; repair pass makes this robust.
        repair_msgs = [
            {"role": "system", "content": "Output ONLY valid JSON. No extra text."},
            {"role": "user", "content": f"Fix this to valid JSON only, preserving meaning:\n\n{raw}"},
        ]
        raw2 = llm.chat(model=settings.model_judge, messages=repair_msgs, temperature=0.0)
        out = parse_judge(raw2)

    # Post-limit (safe)
    out.summary = out.summary[:FIELD_TRUNCATE_CHARS]
    out.verdict = out.verdict[:FIELD_TRUNCATE_CHARS]
    out.key_evidence_for = [x[:EVIDENCE_ITEM_CHARS] for x in out.key_evidence_for][:MAX_EVIDENCE_ITEMS]
    out.key_evidence_against = [x[:EVIDENCE_ITEM_CHARS] for x in out.key_evidence_against][:MAX_EVIDENCE_ITEMS]
    return out


def run_duel(thesis: str, settings: Settings) -> Tuple[List[str], List[str], JudgeOut, str]:
    """Run a structured PRO/CONTRA debate and return the final judge decision.

    Early stop:
    - stop phrases, or
    - probability convergence (Δ below threshold).

    Returns (pro_all, con_all, final_judge, log_path).
    """
    llm = LLM(base_url=settings.base_url, api_key=settings.api_key, seed=settings.seed)

    pro_all: List[str] = []
    con_all: List[str] = []
    last_prob: Optional[float] = None

    last_pro = ""
    last_con = ""

    with JsonlLogger(settings.log_dir) as logger:
        for r in range(1, settings.max_rounds + 1):
            history_compact = _compact_history(last_pro, last_con)

            pro = agent_call_validated(
                llm=llm,
                model=settings.model_creative,
                role_prompt=ROLE_A,
                thesis=thesis,
                last_other=last_con,
                last_self=last_pro,
                history_compact=history_compact,
                temperature=settings.temp_a,
                max_chars=settings.max_chars_agent,
                which=AgentRole.PRO,
            )
            logger.write({"type": "agentA", "round": r, "text": pro})

            con = agent_call_validated(
                llm=llm,
                model=settings.model_critical,
                role_prompt=ROLE_B,
                thesis=thesis,
                last_other=pro,
                last_self=last_con,
                history_compact=_compact_history(pro, last_con),
                temperature=settings.temp_b,
                max_chars=settings.max_chars_agent,
                which=AgentRole.CONTRA,
            )
            logger.write({"type": "agentB", "round": r, "text": con})

            pro_all.append(pro)
            con_all.append(con)
            last_pro, last_con = pro, con

            if stop_phrase_hit(pro, settings.stop_phrases) or stop_phrase_hit(con, settings.stop_phrases):
                logger.write({"type": "early_stop", "round": r, "reason": "stop_phrase"})
                break

            j_probe = judge_call(llm, settings, thesis, pro, con)
            logger.write({"type": "judge_probe", "round": r, "judge": asdict(j_probe)})

            if last_prob is not None and abs(j_probe.probability - last_prob) < settings.convergence_delta:
                logger.write(
                    {"type": "early_stop", "round": r, "reason": f"converged (Δ={abs(j_probe.probability - last_prob):.3f})"}
                )
                break
            last_prob = j_probe.probability

        final_j = judge_call(llm, settings, thesis, last_pro, last_con)
        logger.write({"type": "judge_final", "round": len(pro_all), "judge": asdict(final_j), "thesis": thesis})

        return pro_all, con_all, final_j, str(logger.path)