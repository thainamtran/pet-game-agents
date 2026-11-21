from __future__ import annotations

import pytest

from pet_game_agents.config import Settings
from pet_game_agents.llm import extract_json


def test_extract_json_from_fenced_block():
    text = 'Sure.\n```json\n{"title": "Little Companion", "ok": true}\n```\n'
    assert extract_json(text) == {"title": "Little Companion", "ok": True}


def test_extract_json_from_raw_object():
    assert extract_json('{"a": 1}')["a"] == 1


def test_auto_mode_without_key_resolves_to_mock(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODE", "auto")
    settings = Settings.from_env(output_dir=tmp_path, auto_approve=True)
    assert settings.resolved_mode() == "mock"


def test_llm_mode_requires_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings.from_env(mode="llm", output_dir=tmp_path, auto_approve=True)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        settings.require_llm_key()
