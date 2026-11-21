from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from langgraph.types import Command

from pet_game_agents.config import Settings
from pet_game_agents.graph import build_graph, interrupt_payloads, run_pipeline
from pet_game_agents.state import initial_state
from pet_game_agents.templates import default_design, validate_design


def test_default_design_is_valid():
    design = default_design("cat", "cozy backyard companion")
    assert validate_design(design) == []
    assert design["pet_name_default"] == "Mochi"


def test_mock_pipeline_end_to_end(tmp_path: Path):
    result = run_pipeline(
        mode="mock",
        auto_approve=True,
        species="cat",
        theme="cozy backyard companion",
        output_dir=str(tmp_path),
        max_retries=2,
    )
    assert result["playable"] is True
    assert result["status"] == "playable"
    assert result["retries"] == 0
    assert result["species"] == "cat"
    assert (tmp_path / "pet_game.py").is_file()
    assert (tmp_path / "tests" / "test_pet_game.py").is_file()
    assert (tmp_path / "design.json").is_file()
    assert (tmp_path / "sprites" / "ascii.json").is_file()
    assert len(list((tmp_path / "sprites").glob("*.svg"))) >= 4
    assert (tmp_path / "README.md").is_file()
    assert (tmp_path / "pipeline_log.json").is_file()

    # The Tester already ran pytest; also drive the game ourselves.
    script = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "pet_game.py"),
            "--script",
            "feed,play,sleep,feed,play,sleep,feed,sleep",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert script.returncode == 0, script.stdout + script.stderr
    assert "alive" in script.stdout.lower()

    log = "\n".join(result["log"])
    assert "designer:" in log
    assert "coder:" in log
    assert "artist:" in log
    assert "tester: PASS" in log
    assert "manager:" in log


def test_retry_on_injected_coder_failure(tmp_path: Path):
    result = run_pipeline(
        mode="mock",
        auto_approve=True,
        species="bunny",
        theme="garden tea party",
        output_dir=str(tmp_path),
        max_retries=3,
        inject_coder_failures=1,
    )
    assert result["playable"] is True
    assert result["status"] == "playable"
    assert result["retries"] == 1
    assert result["species"] == "bunny"
    log = "\n".join(result["log"])
    assert "injected a broken build" in log
    assert "retry 1/3 via coder" in log
    assert "tester: PASS" in log
    # The recovered game should actually run.
    script = subprocess.run(
        [sys.executable, str(tmp_path / "pet_game.py"), "--script", "feed,play,sleep"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert script.returncode == 0, script.stdout + script.stderr


def test_human_interrupt_then_resume(tmp_path: Path):
    settings = Settings.from_env(
        mode="mock",
        auto_approve=False,
        species="cat",
        theme="cozy backyard companion",
        output_dir=tmp_path,
        max_retries=2,
    )
    graph = build_graph(settings)
    config = {"configurable": {"thread_id": "test-human"}, "recursion_limit": 50}
    state = initial_state(
        species="cat",
        theme="cozy backyard companion",
        auto_approve=False,
        output_dir=str(tmp_path),
        mode="mock",
        max_retries=2,
    )
    paused = graph.invoke(state, config)
    payloads = interrupt_payloads(paused)
    assert payloads, "expected a human-in-the-loop interrupt for species/theme"
    assert payloads[0]["type"] == "major_decision"

    result = graph.invoke(
        Command(resume={"species": "dragon", "theme": "tiny volcano hatchling"}),
        config,
    )
    assert interrupt_payloads(result) == []
    assert result["playable"] is True
    assert result["species"] == "dragon"
    assert result["theme"] == "tiny volcano hatchling"
    design = json.loads((tmp_path / "design.json").read_text(encoding="utf-8"))
    assert design["species"] == "dragon"
    assert "intake: human chose" in "\n".join(result["log"])


def test_human_handler_callback(tmp_path: Path):
    seen = {}

    def handler(payload):
        seen["payload"] = payload
        return "dog | rainy-day rescue"

    result = run_pipeline(
        mode="mock",
        auto_approve=False,
        output_dir=str(tmp_path),
        human_handler=handler,
    )
    assert seen["payload"]["type"] == "major_decision"
    assert result["species"] == "dog"
    assert result["theme"] == "rainy-day rescue"
    assert result["playable"] is True


def test_manager_gives_up_after_max_retries(tmp_path: Path):
    result = run_pipeline(
        mode="mock",
        auto_approve=True,
        species="cat",
        theme="cozy backyard companion",
        output_dir=str(tmp_path),
        max_retries=1,
        inject_coder_failures=5,  # always broken
    )
    assert result["playable"] is False
    assert result["status"] == "failed"
    assert result["retries"] >= 1
    assert "giving up" in "\n".join(result["log"])
