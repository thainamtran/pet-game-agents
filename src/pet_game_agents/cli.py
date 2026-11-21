"""Command-line interface for the pet-game agent pipeline."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .config import Settings
from .graph import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pet-game-agents",
        description=(
            "Run a crew of AI agents that design, code, illustrate, and test "
            "a pet-raising game (game nuôi thú)."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--mock",
        action="store_true",
        help="Force offline mock mode (no API key, deterministic output).",
    )
    mode.add_argument(
        "--llm",
        action="store_true",
        help="Force LLM mode (requires OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "mock", "llm"],
        default=None,
        help="How to choose a model. 'auto' uses an LLM when a key is set (default).",
    )
    parser.add_argument("--species", help="Pet species (e.g. cat, dog, bunny, dragon).")
    parser.add_argument("--theme", help="Game theme (e.g. 'cozy backyard companion').")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Do not prompt for major decisions; accept species/theme defaults.",
    )
    parser.add_argument(
        "--output",
        dest="output_dir",
        default=None,
        help="Directory for the generated game (default: output/).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="How many times the manager may send work back after a failed test.",
    )
    parser.add_argument(
        "--model",
        dest="openai_model",
        default=None,
        help="OpenAI-compatible model name (LLM mode only).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mode = args.mode
    if args.mock:
        mode = "mock"
    elif args.llm:
        mode = "llm"
    overrides = {
        "mode": mode,
        "species": args.species,
        "theme": args.theme,
        "auto_approve": True if args.auto_approve else None,
        "output_dir": args.output_dir,
        "max_retries": args.max_retries,
        "openai_model": args.openai_model,
    }
    # Drop Nones so from_env can fill defaults.
    overrides = {k: v for k, v in overrides.items() if v is not None}
    try:
        settings = Settings.from_env(**overrides)
        if settings.resolved_mode() == "mock":
            print("Running in mock mode (offline, deterministic).")
        else:
            print(f"Running in LLM mode with model {settings.openai_model}.")
        result = run_pipeline(settings=settings)
    except Exception as exc:  # noqa: BLE001 — CLI should show a clean error
        print(f"error: {exc}", file=sys.stderr)
        return 1

    status = result.get("status")
    playable = result.get("playable")
    output = result.get("output_dir")
    print()
    print(f"Status:   {status}  (playable={playable})")
    print(f"Species:  {result.get('species')}")
    print(f"Theme:    {result.get('theme')}")
    print(f"Retries:  {result.get('retries')}")
    print(f"Output:   {output}")
    if result.get("log"):
        print("Log:")
        for line in result["log"]:
            print(f"  - {line}")
    if playable:
        print()
        print("The game is ready. Play it with:")
        print(f"  python {output}/pet_game.py")
        return 0
    print("The pipeline finished without a playable game. See output/pipeline_log.json.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
