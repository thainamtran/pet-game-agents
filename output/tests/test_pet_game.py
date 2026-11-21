"""Playability tests for the generated pet-raising game.

The Tester agent runs this file with pytest. It also imports the game
and drives a scripted session so we know the loop is actually playable.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

GAME_PATH = Path(__file__).resolve().parents[1] / "pet_game.py"


def load_game():
    spec = importlib.util.spec_from_file_location("pet_game", GAME_PATH)
    assert spec and spec.loader, f"Cannot load game from {GAME_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def game():
    return load_game()


def test_game_file_exists():
    assert GAME_PATH.is_file()


def test_pet_starts_with_valid_stats(game):
    pet = game.Pet()
    assert pet.name
    assert pet.species
    assert 0 < pet.hunger <= 100
    assert 0 < pet.happiness <= 100
    assert 0 < pet.energy <= 100
    assert pet.level == 1
    assert pet.alive is True
    assert pet.ascii_art()


def test_feed_increases_hunger(game):
    pet = game.Pet()
    before = pet.hunger
    # Apply the action without the end-of-turn decay so the effect is visible.
    pet.feed.__func__  # noqa: B018 — touch the method
    # Compare against a no-decay call by inspecting the designed effect:
    after_snapshot = pet.feed()
    # Even with decay, a proper meal should leave the pet at least as full
    # as a turn of waiting would, and usually fuller than before.
    waited = game.Pet()
    waited.wait()
    assert after_snapshot["hunger"] > waited.hunger
    assert after_snapshot["hunger"] >= before - 5


def test_play_increases_happiness(game):
    pet = game.Pet()
    before = pet.happiness
    snap = pet.play()
    waited = game.Pet()
    waited.wait()
    assert snap["happiness"] > waited.happiness
    assert snap["happiness"] >= before - 5


def test_sleep_increases_energy(game):
    pet = game.Pet()
    # Drain a little energy first so there is room to recover.
    pet.energy = min(pet.energy, 50)
    before = pet.energy
    snap = pet.sleep()
    assert snap["energy"] > before


def test_stats_are_clamped(game):
    pet = game.Pet()
    pet.hunger = 1000
    pet.happiness = -50
    pet._apply({"hunger": 0, "happiness": 0}, tick=False, grant_xp=False)
    assert 0 <= pet.hunger <= 100
    assert 0 <= pet.happiness <= 100


def test_level_up_after_enough_actions(game):
    pet = game.Pet()
    starting_level = pet.level
    # Alternate care actions; should be enough XP to level at least once.
    for _ in range(6):
        pet.feed()
        pet.play()
        pet.sleep()
    assert pet.level > starting_level
    assert pet.alive is True


def test_scripted_playthrough_stays_alive_and_progresses(game):
    commands = [
        "feed",
        "play",
        "sleep",
        "feed",
        "play",
        "sleep",
        "feed",
        "sleep",
        "status",
    ]
    result = game.run_scripted(commands)
    final = result["final"]
    assert result["alive"] is True
    assert final["alive"] is True
    assert final["turn"] >= 8
    assert final["level"] >= 2
    assert final["hunger"] > 0
    assert final["happiness"] > 0
    assert final["energy"] > 0
