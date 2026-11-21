"""Coder agent — writes the playable Python game and its tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import Settings
from ..llm import LLMError, get_client
from ..state import BuildState
from ..templates import render_game_source, render_tests_source, write_text

SYSTEM_PROMPT = """You are Coder, writing a complete playable terminal pet-raising game in Python 3.
Return a JSON object: {"files": {"pet_game.py": "...", "tests/test_pet_game.py": "..."}}.
Requirements for pet_game.py:
- Self-contained, runnable with `python pet_game.py`.
- Include a Pet class with hunger, happiness, energy, level, xp, alive, name, species.
- Methods: feed(), play(), sleep(), wait(), tick(), mood(), ascii_art(), status_text(), snapshot().
- Higher hunger means the pet is more full (0 = starving).
- After feed/play/sleep/wait, call tick() to apply idle decay and increment the turn.
- Include run_scripted(commands: list[str], name=None) -> dict with keys final, history, logs, alive.
- Include main() with argparse --name and --script (comma-separated commands).
- Embed the provided DESIGN dict exactly.
- Keep the game balanced so alternating feed, play, sleep for ~8 turns stays alive and reaches level 2.
Requirements for tests/test_pet_game.py:
- pytest tests covering start stats, feed/play/sleep effects, clamping, leveling, and run_scripted.
JSON only. Do not wrap the file contents in extra commentary."""


def _broken_game(design: dict[str, Any]) -> str:
    """Intentionally incomplete source used only for retry-path tests."""
    species = design.get("species", "cat")
    return (
        "#!/usr/bin/env python3\n"
        "DESIGN = " + repr(design) + "\n\n"
        "class Pet:\n"
        "    def __init__(self, name=None, species=None):\n"
        f"        self.name = name or 'Broken'\n"
        f"        self.species = species or {species!r}\n"
        "        self.hunger = 70\n"
        "        self.happiness = 70\n"
        "        self.energy = 70\n"
        "        self.level = 1\n"
        "        self.xp = 0\n"
        "        self.alive = True\n"
        "        self.turn = 0\n"
        "    def snapshot(self):\n"
        "        return {'name': self.name, 'alive': self.alive, 'level': self.level}\n"
        "# Missing feed/play/sleep/run_scripted on purpose.\n"
    )


def _write_pair(output_dir: Path, game_src: str, tests_src: str) -> list[str]:
    game_path = output_dir / "pet_game.py"
    tests_path = output_dir / "tests" / "test_pet_game.py"
    write_text(game_path, game_src)
    write_text(tests_path, tests_src)
    # pytest needs tests/ to be a package or have a path hook; a blank conftest is enough.
    conftest = output_dir / "tests" / "conftest.py"
    if not conftest.exists():
        write_text(conftest, "")
    return [str(game_path), str(tests_path)]


def _llm_code(state: BuildState, settings: Settings) -> dict[str, str]:
    client = get_client(settings)
    user = f"DESIGN = {state.get('design')}\n"
    report = state.get("test_report") or {}
    if report and not report.get("passed"):
        user += (
            f"\nThe previous build failed testing.\nSummary: {report.get('summary')}\n"
            f"Issues: {report.get('issues')}\nPytest output (tail):\n{str(report.get('pytest_output') or '')[-1500:]}\n"
            "Fix the files.\n"
        )
    data = client.complete_json(SYSTEM_PROMPT, user)
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict) or "pet_game.py" not in files:
        raise LLMError("Coder did not return files.pet_game.py")
    return {str(k): str(v) for k, v in files.items()}


def coder_node(state: BuildState, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings.from_env()
    design = state.get("design")
    if not design:
        return {
            "playable": False,
            "failure_category": "design",
            "log": ["coder: no design available, cannot write the game"],
        }

    output_dir = Path(state["output_dir"])
    remaining = int(state.get("inject_coder_failures") or 0)
    if remaining > 0:
        paths = _write_pair(output_dir, _broken_game(design), "# broken tests on purpose\n")
        return {
            "files_written": paths,
            "inject_coder_failures": remaining - 1,
            "log": ["coder: injected a broken build for retry testing"],
        }

    mode = state.get("mode") or settings.resolved_mode()
    if mode == "llm":
        try:
            files = _llm_code(state, settings)
        except LLMError as exc:
            return {
                "playable": False,
                "failure_category": "code",
                "log": [f"coder: LLM failed ({exc})"],
            }
        game_src = files["pet_game.py"]
        tests_src = files.get("tests/test_pet_game.py") or render_tests_source()
        paths = _write_pair(output_dir, game_src, tests_src)
        extra = []
        for rel, content in files.items():
            if rel in {"pet_game.py", "tests/test_pet_game.py"}:
                continue
            path = output_dir / rel
            write_text(path, content)
            extra.append(str(path))
        return {
            "files_written": paths + extra,
            "inject_coder_failures": 0,
            "log": [f"coder: wrote {len(paths) + len(extra)} file(s) in llm mode"],
        }

    paths = _write_pair(output_dir, render_game_source(design), render_tests_source())
    return {
        "files_written": paths,
        "inject_coder_failures": 0,
        "log": ["coder: wrote pet_game.py and tests from the mock templates"],
    }
