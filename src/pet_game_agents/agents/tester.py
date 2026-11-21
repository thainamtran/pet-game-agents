"""Tester agent — really runs pytest and a scripted playthrough of the game."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..state import BuildState, TestReport


SCRIPTED_COMMANDS = [
    "feed",
    "play",
    "sleep",
    "feed",
    "play",
    "sleep",
    "feed",
    "sleep",
]


def _load_game(game_path: Path):
    spec = importlib.util.spec_from_file_location("pet_game_under_test", game_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {game_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_pytest(output_dir: Path) -> tuple[int, str]:
    tests_dir = output_dir / "tests"
    if not tests_dir.exists():
        return 1, "No tests/ directory was generated."
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(output_dir), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(tests_dir)],
        cwd=str(output_dir),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output.strip()


def _categorize(issues: list[str]) -> str:
    blob = " ".join(issues).lower()
    if any(word in blob for word in ("sprite", "ascii", "svg", "art")):
        return "art"
    if any(word in blob for word in ("design", "decay", "balance", "too harsh", "unbalanced")):
        return "design"
    return "code"


def tester_node(state: BuildState) -> dict[str, Any]:
    output_dir = Path(state["output_dir"])
    game_path = output_dir / "pet_game.py"
    issues: list[str] = []
    scripted: dict[str, Any] = {}

    if not game_path.is_file():
        issues.append("pet_game.py is missing")

    sprites_ascii = output_dir / "sprites" / "ascii.json"
    if not sprites_ascii.is_file():
        issues.append("ASCII sprite sheet is missing")
    svg_files = list((output_dir / "sprites").glob("*.svg")) if (output_dir / "sprites").exists() else []
    if len(svg_files) < 3:
        issues.append("Expected at least 3 SVG sprites")

    pytest_code, pytest_output = (1, "skipped: game file missing")
    if game_path.is_file():
        pytest_code, pytest_output = _run_pytest(output_dir)
        if pytest_code != 0:
            issues.append("pytest failed")

        try:
            module = _load_game(game_path)
        except Exception as exc:  # noqa: BLE001 — surface any load error to the manager
            issues.append(f"game failed to import: {exc}")
            module = None

        if module is not None:
            if not hasattr(module, "Pet"):
                issues.append("game is missing a Pet class")
            if not hasattr(module, "run_scripted"):
                issues.append("game is missing run_scripted()")
            else:
                try:
                    result = module.run_scripted(list(SCRIPTED_COMMANDS))
                    scripted = result if isinstance(result, dict) else {"raw": result}
                    final = scripted.get("final") or {}
                    if not scripted.get("alive", final.get("alive", False)):
                        issues.append("scripted playthrough died — design may be too harsh")
                    if int(final.get("level") or 0) < 2:
                        issues.append("scripted playthrough did not reach level 2 — balance/XP issue")
                    for stat in ("hunger", "happiness", "energy"):
                        if int(final.get(stat) or 0) <= 0:
                            issues.append(f"scripted playthrough ended with {stat} <= 0")
                except Exception as exc:  # noqa: BLE001
                    issues.append(f"run_scripted failed: {exc}")

    passed = not issues
    category = _categorize(issues) if issues else "code"
    summary = "All playability checks passed." if passed else "; ".join(issues)
    report = TestReport(
        passed=passed,
        playable=passed,
        category=category,  # type: ignore[typeddict-item]
        summary=summary,
        issues=issues,
        pytest_exit_code=pytest_code,
        pytest_output=pytest_output[-4000:],
        scripted_result={
            k: scripted[k]
            for k in ("final", "alive")
            if k in scripted
        },
    )
    return {
        "test_report": report,
        "playable": passed,
        "failure_category": None if passed else category,
        "log": [f"tester: {'PASS' if passed else 'FAIL'} — {summary}"],
    }
