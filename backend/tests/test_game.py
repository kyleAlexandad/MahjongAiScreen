"""GameState and dora helper tests."""

from __future__ import annotations

import pytest

from backend.app.mahjong.game import (
    GameState,
    Meld,
    PlayerState,
    dora_tile_for,
    dora_tiles,
)
from backend.app.mahjong.tiles import tile_code, tile_id_from_code


def _id(code: str) -> int:
    return tile_id_from_code(code)


def test_dora_indicator_number_suit_cycles():
    # Manzu cycles 1 -> 2 -> ... -> 9 -> 1
    assert tile_code(dora_tile_for(_id("1m"))) == "2m"
    assert tile_code(dora_tile_for(_id("4m"))) == "5m"
    assert tile_code(dora_tile_for(_id("9m"))) == "1m"
    # Pinzu and souzu behave the same
    assert tile_code(dora_tile_for(_id("9p"))) == "1p"
    assert tile_code(dora_tile_for(_id("9s"))) == "1s"


def test_dora_indicator_winds_cycle():
    # E -> S -> W -> N -> E
    assert tile_code(dora_tile_for(_id("1z"))) == "2z"
    assert tile_code(dora_tile_for(_id("2z"))) == "3z"
    assert tile_code(dora_tile_for(_id("3z"))) == "4z"
    assert tile_code(dora_tile_for(_id("4z"))) == "1z"


def test_dora_indicator_dragons_cycle():
    # Haku -> Hatsu -> Chun -> Haku
    assert tile_code(dora_tile_for(_id("5z"))) == "6z"
    assert tile_code(dora_tile_for(_id("6z"))) == "7z"
    assert tile_code(dora_tile_for(_id("7z"))) == "5z"


def test_dora_tiles_helper():
    indicators = [_id("4m"), _id("3z")]
    assert dora_tiles(indicators) == [_id("5m"), _id("4z")]


def test_game_state_validation_round_wind():
    with pytest.raises(ValueError):
        GameState(round_wind=_id("5z"), seat_wind=_id("1z"))


def test_game_state_validation_seat_wind():
    with pytest.raises(ValueError):
        GameState(round_wind=_id("1z"), seat_wind=_id("5z"))


def test_game_state_factory():
    state = GameState.from_hand(
        "123m456p789s1122z7z",
        round_wind="1z",
        seat_wind="2z",
        dora_indicators="3m",
        honba=2,
    )
    assert state.hand_size() == 14
    assert state.round_wind == _id("1z")
    assert state.seat_wind == _id("2z")
    assert state.dora_indicators == [_id("3m")]
    assert state.honba == 2


def test_meld_validation():
    Meld(type="chi", tiles=[0, 1, 2])
    Meld(type="pon", tiles=[5, 5, 5])
    Meld(type="kan", tiles=[5, 5, 5, 5])
    Meld(type="ankan", tiles=[5, 5, 5, 5])
    with pytest.raises(ValueError):
        Meld(type="chi", tiles=[0, 1])
    with pytest.raises(ValueError):
        Meld(type="kan", tiles=[5, 5, 5])
    with pytest.raises(ValueError):
        Meld(type="bogus", tiles=[5, 5, 5])


def test_post_riichi_discards():
    p = PlayerState(
        discards=[1, 2, 3, 4, 5],
        riichi=True,
        riichi_discard_index=2,
    )
    assert p.post_riichi_discards() == [3, 4, 5]


def test_post_riichi_discards_when_not_in_riichi():
    p = PlayerState(discards=[1, 2, 3])
    assert p.post_riichi_discards() == []
