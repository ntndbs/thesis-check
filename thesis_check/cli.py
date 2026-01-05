from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

from .config import Settings
from .runner import run_duel


def main() -> int:
    p = argparse.ArgumentParser(
        prog="thesis-check",
        description="Local Pro/Contra debate runner + judge (LM Studio / OpenAI-compatible endpoint).",
    )
    p.add_argument("thesis", nargs="*", help="Thesis text")
    args = p.parse_args()

    thesis = "Germany will reach net greenhouse-gas neutrality by 2045."
    if args.thesis:
        thesis = " ".join(args.thesis).strip()

    settings = Settings.from_env()

    t0 = time.time()
    A, B, J, log_path = run_duel(thesis, settings)

    print("\n=== PRO ===")
    for i, t in enumerate(A, 1):
        print(f"\n[Round {i}]\n{t}")

    print("\n=== CONTRA ===")
    for i, t in enumerate(B, 1):
        print(f"\n[Round {i}]\n{t}")

    print("\n=== JUDGE (Final) ===")
    print(json.dumps(asdict(J), indent=2, ensure_ascii=False))

    print(
        f"\nDuration: {time.time() - t0:.1f}s | Models: A={settings.model_creative}, "
        f"B={settings.model_critical}, Judge={settings.model_judge} | Log: {log_path}"
    )
    return 0
