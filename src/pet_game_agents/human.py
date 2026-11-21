"""Human-in-the-loop hook for major decisions (species, theme, scope changes)."""

from __future__ import annotations

from typing import Any, Callable

from langgraph.types import interrupt

from .state import BuildState

DecisionHandler = Callable[[dict[str, Any]], dict[str, Any]]


def default_decision(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the suggested defaults for a major decision."""
    defaults = dict(payload.get("defaults") or {})
    return {
        "species": str(defaults.get("species") or "cat").strip().lower() or "cat",
        "theme": str(defaults.get("theme") or "cozy backyard companion").strip()
        or "cozy backyard companion",
        "approved": True,
    }


def normalize_decision(raw: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Accept a dict, a 'species | theme' string, or an empty/yes response."""
    defaults = default_decision(payload)
    if raw is None or raw is True or raw == "":
        return defaults
    if isinstance(raw, str):
        text = raw.strip()
        if text.lower() in {"y", "yes", "ok", "okay", "default", "defaults"}:
            return defaults
        if "|" in text:
            species, _, theme = text.partition("|")
        elif "," in text:
            species, _, theme = text.partition(",")
        else:
            species, theme = text, defaults["theme"]
        return {
            "species": (species.strip().lower() or defaults["species"]),
            "theme": (theme.strip() or defaults["theme"]),
            "approved": True,
        }
    if isinstance(raw, dict):
        return {
            "species": str(raw.get("species") or defaults["species"]).strip().lower(),
            "theme": str(raw.get("theme") or defaults["theme"]).strip(),
            "approved": bool(raw.get("approved", True)),
        }
    return defaults


def prompt_stdin(payload: dict[str, Any]) -> dict[str, Any]:
    """CLI prompt used when the pipeline is resumed interactively."""
    defaults = default_decision(payload)
    question = payload.get("question") or "Please make a decision."
    print()
    print("=" * 60)
    print("Major decision needed")
    print(question)
    if payload.get("details"):
        print(payload["details"])
    print(f"Default species: {defaults['species']}")
    print(f"Default theme:   {defaults['theme']}")
    print("Press Enter to accept the defaults, or type: species | theme")
    print("=" * 60)
    try:
        answer = input("> ")
    except EOFError:
        answer = ""
    return normalize_decision(answer, payload)


def intake_node(state: BuildState) -> dict[str, Any]:
    """Ask the user for pet species and theme unless auto-approve is on."""
    payload = {
        "type": "major_decision",
        "question": "What pet should we raise, and what is the game's theme?",
        "details": (
            "Agents will invent the rest of the gameplay (stats, actions, art, tests). "
            "Only this kind of major choice is sent to you."
        ),
        "defaults": {
            "species": state.get("species") or "cat",
            "theme": state.get("theme") or "cozy backyard companion",
        },
    }
    if state.get("auto_approve"):
        decision = default_decision(payload)
        return {
            "species": decision["species"],
            "theme": decision["theme"],
            "log": [
                f"intake: auto-approved species={decision['species']!r} theme={decision['theme']!r}"
            ],
        }
    raw = interrupt(payload)
    decision = normalize_decision(raw, payload)
    return {
        "species": decision["species"],
        "theme": decision["theme"],
        "log": [
            f"intake: human chose species={decision['species']!r} theme={decision['theme']!r}"
        ],
    }
