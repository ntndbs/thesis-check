from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class TemplateSpec:
    keys: Tuple[str, str, str, str]


SPEC_A = TemplateSpec(keys=("PRO1", "PRO2", "NEW_ASSUMPTION", "RISK"))
SPEC_B = TemplateSpec(keys=("CONTRA1", "CONTRA2", "ASSUMPTION_CHECK", "EDGE_CASE"))


def truncate(txt: str, max_chars: int) -> str:
    return txt[:max_chars] if len(txt) > max_chars else txt


def stop_phrase_hit(text: str, stop_phrases: List[str]) -> bool:
    t = text.lower()
    return any(p.lower() in t for p in stop_phrases)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(a=a.lower().strip(), b=b.lower().strip()).ratio()


def parse_template(text: str, spec: TemplateSpec) -> Dict[str, str] | None:
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
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
        if not val:
            return None
        out[key] = val

    # must match keys exactly, no missing/extra keys
    if tuple(out.keys()) and set(out.keys()) != set(spec.keys):
        return None
    return out

def validate_agent_output(text: str, which: str) -> bool:
    spec = SPEC_A if which == "A" else SPEC_B
    return parse_template(text, spec) is not None


def too_similar(candidate: str, previous_other: str, threshold: float = 0.92) -> bool:
    if not previous_other.strip():
        return False
    return similarity(candidate, previous_other) >= threshold