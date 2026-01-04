from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Settings
from .llm import LLM
from .prompts import ROLE_A, ROLE_B, ROLE_JUDGE, SYSTEM_SAFETY
from .validators import truncate, stop_phrase_hit, too_similar, validate_agent_output


@dataclass
class JudgeOut:
    summary: str
    key_evidence_for: List[str]
    key_evidence_against: List[str]
    verdict: str
    probability: float


def parse_judge(raw: str) -> JudgeOut:
    s, e = raw.find("{"), raw.rfind("}") + 1
    try:
        obj = json.loads(raw[s:e])
        p = float(obj.get("probability", 0.5))
        p = max(0.0, min(1.0, p))
        return JudgeOut(
            summary=str(obj.get("summary", "")),
            key_evidence_for=list(obj.get("key_evidence_for", []))[:10],
            key_evidence_against=list(obj.get("key_evidence_against", []))[:10],
            verdict=str(obj.get("verdict", "")),
            probability=p,
        )
    except Exception:
        return JudgeOut(
            summary="JSON-Fallback",
            key_evidence_for=[],
            key_evidence_against=[],
            verdict=raw[:240],
            probability=0.5,
        )


class JsonlLogger:
    def __init__(self, log_dir: str):
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.path = Path(log_dir) / f"run-{ts}.jsonl"

    def write(self, event: Dict[str, Any]) -> None:
        event["ts"] = time.time()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _agent_messages(role_prompt: str, thesis: str, history_compact: str) -> List[Dict[str, str]]:
    msgs = [
        {"role": "system", "content": SYSTEM_SAFETY},
        {"role": "system", "content": role_prompt},
    ]
    if history_compact.strip():
        msgs.append({"role": "user", "content": f"Kontext (letzte Runde, komprimiert):\n{history_compact}"})
    msgs.append({"role": "user", "content": f"These: {thesis}\nAntworte strikt im geforderten Template."})
    return msgs


def _compact_history(last_pro: str, last_con: str) -> str:
    if not last_pro and not last_con:
        return ""
    return f"PRO zuletzt:\n{last_pro}\n\nCONTRA zuletzt:\n{last_con}"


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
    which: str,
) -> str:
    """Template enforcement + anti-mirroring + anti-repeat (self/other) with retries.
    Returns last VALID output if retries fail.
    """
    last_valid: str = ""
    last_out: str = ""

    for _attempt in range(3):
        msgs = _agent_messages(role_prompt, thesis, history_compact)

        # Only on retry: force novelty
        if _attempt > 0:
            msgs.append(
                {
                    "role": "system",
                    "content": "WICHTIG: Liefere komplett neue Punkte, andere Perspektive. Keine Wiederholung. Halte das Template exakt ein.",
                }
            )

        last_out = truncate(llm.chat(model=model, messages=msgs, temperature=temperature), max_chars)

        if not validate_agent_output(last_out, which=which):
            continue
        if last_other and too_similar(last_out, last_other):
            continue
        if last_self and too_similar(last_out, last_self):
            continue

        last_valid = last_out
        return last_valid

    # If all attempts failed, return last valid (if any), else a safe placeholder
    if last_valid:
        return last_valid

    if which == "A":
        return (
            "- PRO1: (Fehler) Template konnte nicht zuverlässig erzeugt werden.\n"
            "- PRO2: Bitte erneut ausführen oder Modell/Prompt anpassen.\n"
            "- ANNAHME_NEU: Modell hält Template nicht ein.\n"
            "- RISIKO: Bewertung ist eingeschränkt."
        )
    else:
        return (
            "- CONTRA1: (Fehler) Template konnte nicht zuverlässig erzeugt werden.\n"
            "- CONTRA2: Bitte erneut ausführen oder Modell/Prompt anpassen.\n"
            "- ANNAHMEPRUEFUNG: Modell hält Template nicht ein.\n"
            "- EDGE_CASE: Bewertung ist eingeschränkt."
        )


def judge_call(llm: LLM, settings: Settings, thesis: str, pros_last: str, cons_last: str) -> JudgeOut:
    base_msgs = [
        {"role": "system", "content": SYSTEM_SAFETY},
        {"role": "system", "content": ROLE_JUDGE},
        {
            "role": "user",
            "content": (
                f"These: {thesis}\n\n"
                f"PRO (letzte Runde):\n{pros_last}\n\n"
                f"CONTRA (letzte Runde):\n{cons_last}"
            ),
        },
    ]

    raw = ""
    parsed: Optional[JudgeOut] = None

    for attempt in range(2):
        msgs = list(base_msgs)
        if attempt > 0:
            msgs.append({"role": "system", "content": "STRICT: Antworte ausschließlich als gültiges JSON, nichts anderes."})

        raw = llm.chat(model=settings.model_judge, messages=msgs, temperature=settings.temp_j)
        parsed = parse_judge(raw)

        # Heuristic: if we got real JSON fields, accept
        if parsed.summary != "JSON-Fallback" and parsed.verdict:
            break

    out = parsed if parsed else parse_judge(raw)

    # Post-limit (safe)
    out.summary = out.summary[:800]
    out.verdict = out.verdict[:800]
    out.key_evidence_for = [x[:200] for x in out.key_evidence_for][:10]
    out.key_evidence_against = [x[:200] for x in out.key_evidence_against][:10]
    return out

def run_duel(thesis: str, settings: Settings) -> Tuple[List[str], List[str], JudgeOut, str]:
    llm = LLM(base_url=settings.base_url, api_key=settings.api_key, seed=settings.seed)
    logger = JsonlLogger(settings.log_dir)

    pro_all: List[str] = []
    con_all: List[str] = []
    last_prob: Optional[float] = None

    last_pro = ""
    last_con = ""

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
            which="A",
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
            which="B",
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
                {
                    "type": "early_stop",
                    "round": r,
                    "reason": f"converged (Δ={abs(j_probe.probability - last_prob):.3f})",
                }
            )
            break
        last_prob = j_probe.probability

    final_j = judge_call(llm, settings, thesis, last_pro, last_con)
    logger.write({"type": "judge_final", "round": len(pro_all), "judge": asdict(final_j), "thesis": thesis})

    return pro_all, con_all, final_j, str(logger.path)
