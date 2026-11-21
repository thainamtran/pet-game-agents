"""Templates the mock (and fallback) agents use to emit a playable game."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

DESIGN_START = "# --- DESIGN START ---"
DESIGN_END = "# --- DESIGN END ---"

REQUIRED_STATS = ("hunger", "happiness", "energy")
REQUIRED_ACTIONS = ("feed", "play", "sleep")


def load_template(name: str) -> str:
    return files(__package__).joinpath(name).read_text(encoding="utf-8")


def default_design(species: str, theme: str) -> dict[str, Any]:
    species = (species or "cat").strip().lower() or "cat"
    default_names = {
        "cat": "Mochi",
        "dog": "Biscuit",
        "bunny": "Bông",
        "dragon": "Ember",
    }
    titles = {
        "cat": "Little Companion",
        "dog": "Yard Buddy",
        "bunny": "Garden Friend",
        "dragon": "Tiny Ember",
    }
    return {
        "title": titles.get(species, "Little Companion"),
        "theme": theme or "cozy backyard companion",
        "species": species,
        "pet_name_default": default_names.get(species, "Mochi"),
        "stats": {
            "hunger": {"min": 0, "max": 100, "start": 70, "decay_per_turn": 8},
            "happiness": {"min": 0, "max": 100, "start": 72, "decay_per_turn": 5},
            "energy": {"min": 0, "max": 100, "start": 80, "decay_per_turn": 4},
        },
        "leveling": {"xp_per_action": 10, "xp_to_level": 30, "max_level": 5},
        "actions": [
            {"id": "feed", "label": "Feed", "effects": {"hunger": 32, "energy": 4, "happiness": 6}},
            {"id": "play", "label": "Play", "effects": {"happiness": 26, "energy": -16, "hunger": -8}},
            {"id": "sleep", "label": "Sleep", "effects": {"energy": 38, "hunger": -6, "happiness": 6}},
        ],
        "notes": (
            "Hunger is a fullness meter: 100 is well fed, 0 is starving. "
            "Every action advances a turn and applies idle decay."
        ),
    }


def validate_design(design: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not design.get("species"):
        issues.append("design is missing species")
    stats = design.get("stats") or {}
    for name in REQUIRED_STATS:
        spec = stats.get(name)
        if not isinstance(spec, dict):
            issues.append(f"design.stats.{name} is missing")
            continue
        for key in ("min", "max", "start", "decay_per_turn"):
            if key not in spec:
                issues.append(f"design.stats.{name}.{key} is missing")
    actions = design.get("actions") or []
    ids = {a.get("id") for a in actions if isinstance(a, dict)}
    for action_id in REQUIRED_ACTIONS:
        if action_id not in ids:
            issues.append(f"design.actions is missing {action_id}")
    leveling = design.get("leveling") or {}
    for key in ("xp_per_action", "xp_to_level", "max_level"):
        if key not in leveling:
            issues.append(f"design.leveling.{key} is missing")
    return issues


def render_game_source(design: dict[str, Any]) -> str:
    template = load_template("pet_game.py.tmpl")
    block = (
        f"{DESIGN_START}\n"
        f"DESIGN: dict[str, Any] = {json.dumps(design, indent=4)}\n"
        f"{DESIGN_END}"
    )
    start = template.find(DESIGN_START)
    end = template.find(DESIGN_END)
    if start == -1 or end == -1:
        raise RuntimeError("Game template is missing DESIGN markers")
    end += len(DESIGN_END)
    return template[:start] + block + template[end:]


def render_tests_source() -> str:
    return load_template("test_pet_game.py.tmpl")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if path.suffix == ".py":
        path.chmod(path.stat().st_mode | 0o111)
