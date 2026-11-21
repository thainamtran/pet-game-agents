"""GameDesigner agent — invents mechanics, stats, and the care loop."""

from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from ..config import Settings
from ..llm import LLMError, get_client
from ..state import BuildState
from ..templates import default_design, validate_design, write_text

SYSTEM_PROMPT = """You are GameDesigner, an expert at cozy pet-raising games (Tamagotchi-style).
Design a small, balanced terminal pet game. Hunger is a fullness meter: 100 is well fed, 0 is starving.
Every action must advance one turn and apply idle decay so the player has to keep caring for the pet.
Return a single JSON object with this exact shape:
{
  "title": str,
  "theme": str,
  "species": str,
  "pet_name_default": str,
  "stats": {
    "hunger": {"min": 0, "max": 100, "start": int, "decay_per_turn": int},
    "happiness": {"min": 0, "max": 100, "start": int, "decay_per_turn": int},
    "energy": {"min": 0, "max": 100, "start": int, "decay_per_turn": int}
  },
  "leveling": {"xp_per_action": int, "xp_to_level": int, "max_level": int},
  "actions": [
    {"id": "feed", "label": "Feed", "effects": {"hunger": int, "energy": int, "happiness": int}},
    {"id": "play", "label": "Play", "effects": {"happiness": int, "energy": int, "hunger": int}},
    {"id": "sleep", "label": "Sleep", "effects": {"energy": int, "hunger": int, "happiness": int}}
  ],
  "notes": str
}
Keep the game fair: a player who alternates feed, play, and sleep for about 8 turns
should stay alive and reach at least level 2. Start stats should be 65-85.
Decay should be modest (hunger 6-10, happiness 4-7, energy 3-6).
Feed must raise hunger by more than hunger decay. Play must raise happiness net of decay.
Sleep must raise energy net of decay. Play may cost energy and a little hunger.
Do not add extra required systems. JSON only."""


def _llm_design(state: BuildState, settings: Settings) -> dict[str, Any]:
    client = get_client(settings)
    user = (
        f"Species: {state['species']}\n"
        f"Theme: {state['theme']}\n"
        "If a previous test report is included, fix the design issues it describes.\n"
    )
    report = state.get("test_report") or {}
    if report and not report.get("passed"):
        user += f"Previous test report: {report.get('summary')}\nIssues: {report.get('issues')}\n"
    data = client.complete_json(SYSTEM_PROMPT, user)
    if not isinstance(data, dict):
        raise LLMError("Designer did not return a JSON object")
    # Keep the intake decision authoritative.
    data["species"] = state["species"]
    data["theme"] = state["theme"]
    return data


def designer_node(state: BuildState, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings.from_env()
    mode = state.get("mode") or settings.resolved_mode()
    if mode == "llm":
        try:
            design = _llm_design(state, settings)
        except LLMError as exc:
            return {
                "design": None,
                "playable": False,
                "failure_category": "design",
                "log": [f"designer: LLM failed ({exc}); leaving design unset"],
            }
    else:
        design = default_design(state["species"], state["theme"])
        report = state.get("test_report") or {}
        # If we came back because decay was too harsh, soften slightly.
        if report and report.get("category") == "design":
            for spec in (design.get("stats") or {}).values():
                if isinstance(spec, dict) and "decay_per_turn" in spec:
                    spec["decay_per_turn"] = max(2, int(spec["decay_per_turn"]) - 2)

    issues = validate_design(design) if design else ["no design produced"]
    if issues:
        return {
            "design": design,
            "playable": False,
            "failure_category": "design",
            "log": [f"designer: invalid design: {'; '.join(issues)}"],
        }

    output_dir = Path(state["output_dir"])
    write_text(output_dir / "design.json", json.dumps(design, indent=2) + "\n")
    return {
        "design": design,
        "files_written": [str(output_dir / "design.json")],
        "log": [
            f"designer: designed {design['title']} "
            f"({design['species']}, {design['theme']}) in {mode} mode"
        ],
    }
