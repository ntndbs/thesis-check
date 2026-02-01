from __future__ import annotations

"""
CLI entrypoint.

Takes a thesis from the command line, runs the debate pipeline, prints the
round outputs and the final judge JSON, and shows timing/model info.
"""

import argparse
import json
import sys
import time
from dataclasses import asdict

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .config import Settings
from .runner import run_duel

__all__ = ["main"]

console = Console()


def main() -> int:
    """Parse CLI args, load settings from env, run the debate, and print results."""
    p = argparse.ArgumentParser(
        prog="thesis-check",
        description="Local Pro/Contra debate runner + judge (LM Studio / OpenAI-compatible endpoint).",
    )
    p.add_argument("thesis", nargs="*", help="Thesis text")
    args = p.parse_args()

    thesis = "Switching to a heat pump will reduce household emissions over 10 years."
    if args.thesis:
        thesis = " ".join(args.thesis).strip()

    settings = Settings.from_env()

    try:
        settings.validate()
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        return 1

    console.print(Panel(thesis, title="Thesis", border_style="blue"))

    t0 = time.time()
    with console.status("[bold green]Running debate...", spinner="dots"):
        pro_rounds, con_rounds, judge_result, log_path = run_duel(thesis, settings)

    console.print("\n[bold cyan]=== PRO ===[/bold cyan]")
    for i, txt in enumerate(pro_rounds, 1):
        console.print(f"\n[dim]Round {i}[/dim]")
        console.print(txt)

    console.print("\n[bold magenta]=== CONTRA ===[/bold magenta]")
    for i, txt in enumerate(con_rounds, 1):
        console.print(f"\n[dim]Round {i}[/dim]")
        console.print(txt)

    console.print("\n[bold yellow]=== JUDGE (Final) ===[/bold yellow]")
    console.print_json(json.dumps(asdict(judge_result), ensure_ascii=False))

    duration = time.time() - t0
    info = Text()
    info.append(f"Duration: {duration:.1f}s", style="green")
    info.append(" | Models: ", style="dim")
    info.append(f"A={settings.model_creative}", style="cyan")
    info.append(", ", style="dim")
    info.append(f"B={settings.model_critical}", style="magenta")
    info.append(", ", style="dim")
    info.append(f"Judge={settings.model_judge}", style="yellow")
    info.append(" | Log: ", style="dim")
    info.append(log_path, style="blue underline")
    console.print(info)

    return 0


if __name__ == "__main__":
    sys.exit(main())
