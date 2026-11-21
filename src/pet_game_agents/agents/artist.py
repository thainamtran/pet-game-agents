"""Artist agent — creates ASCII moods and simple SVG sprites."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import Settings
from ..llm import LLMError, get_client
from ..state import BuildState
from ..templates import write_text

# Mood-specific ASCII art keyed by species. Kept deterministic for mock mode.
ASCII_ART: dict[str, dict[str, str]] = {
    "cat": {
        "happy": "  /\\_/\\\n ( ^.^ )\n  > ^ <",
        "hungry": "  /\\_/\\\n ( o.o )\n  > ~ <",
        "sleepy": "  /\\_/\\\n ( -.- )\n  > ^ <  zzz",
        "sad": "  /\\_/\\\n ( ;_; )\n  > ^ <",
        "play": "  /\\_/\\\n ( ^o^ )\n  /   \\  *",
    },
    "dog": {
        "happy": "  / \\__\n (  ^.^)\n /  -- \\",
        "hungry": "  / \\__\n (  o.o)\n /  -- \\",
        "sleepy": "  / \\__\n (  -.-) zzz\n /  -- \\",
        "sad": "  / \\__\n (  ;_;)\n /  -- \\",
        "play": "  / \\__\n (  ^o^)  woof!\n /  -- \\",
    },
    "bunny": {
        "happy": "  (\\_/)\n  ( ^.^)\n  (___)",
        "hungry": "  (\\_/)\n  ( o.o)\n  (___)",
        "sleepy": "  (\\_/)\n  ( -.-) zzz\n  (___)",
        "sad": "  (\\_/)\n  ( ;_;)\n  (___)",
        "play": "  (\\_/)\n  ( ^o^)  hop!\n  (___)",
    },
    "dragon": {
        "happy": "    /\\   /\\\n   (  ^.^  )\n  <        >~~\n    /    \\",
        "hungry": "    /\\   /\\\n   (  o.o  )\n  <        >~~\n    /    \\",
        "sleepy": "    /\\   /\\\n   (  -.-  ) zzz\n  <        >~~\n    /    \\",
        "sad": "    /\\   /\\\n   (  ;_;  )\n  <        >~~\n    /    \\",
        "play": "    /\\   /\\\n   (  ^o^  )\n  <        >~~ *\n    /    \\",
    },
}

PALETTES: dict[str, dict[str, str]] = {
    "cat": {"body": "#f4a261", "stroke": "#9c5a1c", "ear": "#e76f51", "eye": "#2a2a2a"},
    "dog": {"body": "#e9c46a", "stroke": "#7a4e12", "ear": "#c28a2b", "eye": "#2a2a2a"},
    "bunny": {"body": "#f1faee", "stroke": "#9a8c98", "ear": "#ffc2d4", "eye": "#2a2a2a"},
    "dragon": {"body": "#2a9d8f", "stroke": "#1d3557", "ear": "#e9c46a", "eye": "#e63946"},
}

SYSTEM_PROMPT = """You are Artist, illustrating a tiny terminal pet game.
Return JSON with this shape:
{
  "ascii": {"happy": str, "hungry": str, "sleepy": str, "sad": str, "play": str},
  "svg": {"happy": "<svg ...>", "hungry": "...", "sleepy": "...", "sad": "...", "play": "..."}
}
ASCII should be 3-5 lines, monospaced, and clearly show the given species.
Each SVG must be a complete 128x128 image (viewBox=\"0 0 128 128\") of the pet in that mood.
JSON only."""


def _svg_for(species: str, mood: str) -> str:
    palette = PALETTES.get(species, PALETTES["cat"])
    body, stroke, ear, eye = palette["body"], palette["stroke"], palette["ear"], palette["eye"]
    # Eye and mouth change with mood.
    if mood == "sleepy":
        eyes = (
            f'<path d="M44 64 H60" stroke="{eye}" stroke-width="3" stroke-linecap="round"/>'
            f'<path d="M68 64 H84" stroke="{eye}" stroke-width="3" stroke-linecap="round"/>'
        )
        mouth = f'<path d="M56 78 Q64 82 72 78" fill="none" stroke="{stroke}" stroke-width="2"/>'
        extra = '<text x="96" y="40" font-size="12" fill="#4a4a4a">zzz</text>'
    elif mood == "sad":
        eyes = (
            f'<circle cx="52" cy="64" r="4" fill="{eye}"/>'
            f'<circle cx="76" cy="64" r="4" fill="{eye}"/>'
            f'<path d="M50 58 L54 62" stroke="{stroke}" stroke-width="2"/>'
            f'<path d="M78 58 L74 62" stroke="{stroke}" stroke-width="2"/>'
        )
        mouth = f'<path d="M56 84 Q64 76 72 84" fill="none" stroke="{stroke}" stroke-width="2"/>'
        extra = ""
    elif mood == "hungry":
        eyes = (
            f'<circle cx="52" cy="64" r="5" fill="{eye}"/>'
            f'<circle cx="76" cy="64" r="5" fill="{eye}"/>'
        )
        mouth = f'<ellipse cx="64" cy="84" rx="7" ry="6" fill="#3d1f14" stroke="{stroke}"/>'
        extra = ""
    elif mood == "play":
        eyes = (
            f'<circle cx="52" cy="62" r="5" fill="{eye}"/>'
            f'<circle cx="76" cy="62" r="5" fill="{eye}"/>'
            f'<circle cx="53.5" cy="60.5" r="1.5" fill="#fff"/>'
            f'<circle cx="77.5" cy="60.5" r="1.5" fill="#fff"/>'
        )
        mouth = f'<path d="M54 80 Q64 92 74 80" fill="#3d1f14" stroke="{stroke}" stroke-width="1.5"/>'
        extra = f'<circle cx="104" cy="28" r="5" fill="{ear}" stroke="{stroke}"/>'
    else:
        eyes = (
            f'<circle cx="52" cy="64" r="4.5" fill="{eye}"/>'
            f'<circle cx="76" cy="64" r="4.5" fill="{eye}"/>'
            f'<circle cx="53.5" cy="62.5" r="1.4" fill="#fff"/>'
            f'<circle cx="77.5" cy="62.5" r="1.4" fill="#fff"/>'
        )
        mouth = f'<path d="M56 80 Q64 88 72 80" fill="none" stroke="{stroke}" stroke-width="2"/>'
        extra = ""

    # Species silhouette: ears / snout / tail.
    if species == "dog":
        ears = (
            f'<ellipse cx="36" cy="36" rx="12" ry="22" fill="{ear}" stroke="{stroke}" '
            'stroke-width="3" transform="rotate(-20 36 36)"/>'
            f'<ellipse cx="92" cy="36" rx="12" ry="22" fill="{ear}" stroke="{stroke}" '
            'stroke-width="3" transform="rotate(20 92 36)"/>'
        )
        tail = f'<path d="M100 90 Q122 70 112 44" fill="none" stroke="{stroke}" stroke-width="6"/>'
    elif species == "bunny":
        ears = (
            f'<ellipse cx="46" cy="22" rx="8" ry="26" fill="{ear}" stroke="{stroke}" stroke-width="3"/>'
            f'<ellipse cx="82" cy="22" rx="8" ry="26" fill="{ear}" stroke="{stroke}" stroke-width="3"/>'
        )
        tail = f'<circle cx="108" cy="96" r="8" fill="#fff" stroke="{stroke}" stroke-width="3"/>'
    elif species == "dragon":
        ears = (
            f'<path d="M34 48 L20 18 L50 40 Z" fill="{ear}" stroke="{stroke}" stroke-width="3"/>'
            f'<path d="M94 48 L108 18 L78 40 Z" fill="{ear}" stroke="{stroke}" stroke-width="3"/>'
        )
        tail = (
            f'<path d="M100 92 Q126 86 118 50" fill="none" stroke="{stroke}" stroke-width="6"/>'
            f'<path d="M118 50 L126 42 L114 44 Z" fill="{ear}" stroke="{stroke}" stroke-width="2"/>'
        )
    else:
        ears = (
            f'<path d="M32 70 L28 22 L58 46 Z" fill="{ear}" stroke="{stroke}" stroke-width="3"/>'
            f'<path d="M96 70 L100 22 L70 46 Z" fill="{ear}" stroke="{stroke}" stroke-width="3"/>'
        )
        tail = ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128" role="img" aria-label="{species} {mood}">
  <rect width="128" height="128" fill="#fff6e9"/>
  {tail}
  {ears}
  <circle cx="64" cy="72" r="36" fill="{body}" stroke="{stroke}" stroke-width="3"/>
  {eyes}
  <ellipse cx="64" cy="74" rx="6" ry="4" fill="{ear}" stroke="{stroke}" stroke-width="1"/>
  {mouth}
  {extra}
</svg>
"""


def _mock_art(species: str) -> tuple[dict[str, str], dict[str, str]]:
    ascii_map = dict(ASCII_ART.get(species, ASCII_ART["cat"]))
    svgs = {mood: _svg_for(species, mood) for mood in ascii_map}
    return ascii_map, svgs


def _write_art(output_dir: Path, ascii_map: dict[str, str], svgs: dict[str, str]) -> list[str]:
    sprites = output_dir / "sprites"
    written = []
    ascii_path = sprites / "ascii.json"
    write_text(ascii_path, json.dumps(ascii_map, indent=2) + "\n")
    written.append(str(ascii_path))
    for mood, svg in svgs.items():
        path = sprites / f"pet_{mood}.svg"
        write_text(path, svg)
        written.append(str(path))
    return written


def artist_node(state: BuildState, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings.from_env()
    species = (state.get("species") or "cat").lower()
    mode = state.get("mode") or settings.resolved_mode()
    output_dir = Path(state["output_dir"])

    if mode == "llm":
        try:
            client = get_client(settings)
            design = state.get("design") or {}
            user = f"Species: {species}\nTheme: {state.get('theme')}\nDesign title: {design.get('title')}\n"
            data = client.complete_json(SYSTEM_PROMPT, user)
            ascii_map = {str(k): str(v) for k, v in (data.get("ascii") or {}).items()}
            svgs = {str(k): str(v) for k, v in (data.get("svg") or {}).items()}
            if not ascii_map:
                raise LLMError("Artist returned no ASCII art")
        except LLMError as exc:
            # Still ship mock art so the game can render something.
            ascii_map, svgs = _mock_art(species)
            paths = _write_art(output_dir, ascii_map, svgs)
            return {
                "files_written": paths,
                "log": [f"artist: LLM failed ({exc}); fell back to mock sprites"],
            }
    else:
        ascii_map, svgs = _mock_art(species)

    paths = _write_art(output_dir, ascii_map, svgs)
    return {
        "files_written": paths,
        "log": [f"artist: wrote ASCII + {len(svgs)} SVG sprite(s) for a {species} in {mode} mode"],
    }
