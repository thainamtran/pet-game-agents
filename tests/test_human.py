from __future__ import annotations

from pet_game_agents.human import default_decision, normalize_decision


PAYLOAD = {
    "question": "What pet?",
    "defaults": {"species": "cat", "theme": "cozy backyard companion"},
}


def test_default_decision_uses_payload_defaults():
    decision = default_decision(PAYLOAD)
    assert decision["species"] == "cat"
    assert decision["theme"] == "cozy backyard companion"
    assert decision["approved"] is True


def test_normalize_pipe_string():
    decision = normalize_decision("dragon | tiny volcano", PAYLOAD)
    assert decision["species"] == "dragon"
    assert decision["theme"] == "tiny volcano"


def test_normalize_yes_keeps_defaults():
    assert normalize_decision("yes", PAYLOAD)["species"] == "cat"
    assert normalize_decision("", PAYLOAD)["theme"] == "cozy backyard companion"


def test_normalize_dict():
    decision = normalize_decision({"species": "Bunny", "theme": "garden tea party"}, PAYLOAD)
    assert decision["species"] == "bunny"
    assert decision["theme"] == "garden tea party"
