"""Integrated game-aware analysis (efficiency + defense)."""

from __future__ import annotations

import pytest

from backend.app.mahjong.analyzer import analyze_game
from backend.app.mahjong.game import GameState
from backend.app.mahjong.shanten import clear_cache
from backend.app.mahjong.tiles import tile_id_from_code


def _id(code: str) -> int:
    return tile_id_from_code(code)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


def test_analyze_game_basic_14_tile():
    state = GameState.from_hand(
        "123m456p789s1122z7z",
        round_wind="1z",
        seat_wind="1z",
    )
    res = analyze_game(state)
    assert res["tile_count"] == 14
    best = res["best_discard"]
    assert best is not None
    assert best["tile_code"] == "7z"
    # Defense info should be attached.
    assert best["danger"] is not None
    assert "score" in best["danger"]
    assert "summary" in best["danger"]


def test_analyze_game_threats_listed_when_riichi_declared():
    state = GameState.from_hand(
        "123m456p789s1122z7z",
        round_wind="1z",
        seat_wind="1z",
    )
    state.opponents[1].riichi = True
    state.opponents[1].riichi_discard_index = 0
    state.opponents[1].discards = [_id("9m")]
    res = analyze_game(state)
    assert any(t["label"] == "toimen" for t in res["threats"])


def test_analyze_game_genbutsu_overrides_pure_efficiency():
    """When toimen is in riichi and 7z is in their pile, discarding 7z is
    safe AND keeps tenpai -> the engine should keep recommending 7z."""
    state = GameState.from_hand(
        "123m456p789s1122z7z",
        round_wind="1z",
        seat_wind="1z",
    )
    state.opponents[1].riichi = True
    state.opponents[1].riichi_discard_index = 0
    state.opponents[1].discards = [_id("7z")]
    res = analyze_game(state)
    assert res["best_discard"]["tile_code"] == "7z"
    # Per-opponent danger vs toimen on 7z must be 0 (genbutsu).
    danger = res["best_discard"]["danger"]
    toimen = next(p for p in danger["per_opponent"] if p["seat"] == 2)
    assert toimen["score"] == 0
    assert toimen["label"] == "genbutsu"


def test_remaining_caps_ukeire():
    # Tenpai shanpon hand on 1z/2z; user already saw 3 of the 1z elsewhere.
    state = GameState.from_hand(
        "123m456p789s1122z",
        round_wind="3z",
        seat_wind="1z",
    )
    # Pretend three 1z are already gone.
    state.opponents[0].discards = [_id("1z"), _id("1z")]
    state.user.discards = [_id("1z")]  # but our hand still has 2 of them
    # Hand has 2 copies of 1z, opponents/discards show another 3 -> oversaturated.
    # We'll trim user to keep counts <= 4. Reduce hand 1z to 1 instead.
    state = GameState.from_hand(
        "123m456p789s122z11z",
        round_wind="3z",
        seat_wind="1z",
    )
    # Two 1z in hand, two more visible elsewhere -> 0 remaining
    state.opponents[0].discards = [_id("1z"), _id("1z")]
    res = analyze_game(state)
    # ukeire on 1z must report 0 / not be listed since no copies remain
    ukeire_codes = {u["tile_code"]: u["remaining"] for u in res["ukeire"]}
    assert ukeire_codes.get("1z", 0) == 0


def test_invalid_hand_size_rejected():
    state = GameState(round_wind=27, seat_wind=27, hand=[0, 1, 2])
    with pytest.raises(ValueError):
        analyze_game(state)
