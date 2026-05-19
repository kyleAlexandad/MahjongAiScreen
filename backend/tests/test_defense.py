"""Defense engine tests: genbutsu, suji, kabe, danger labels."""

from __future__ import annotations

import pytest

from backend.app.mahjong.defense import assess_tile_danger
from backend.app.mahjong.game import GameState, Meld, PlayerState
from backend.app.mahjong.tiles import tile_id_from_code
from backend.app.mahjong.visibility import visible_counts


def _id(code: str) -> int:
    return tile_id_from_code(code)


def _state_with_opponent(opp_index: int, *, riichi: bool, discards: list[str], riichi_at: int | None = None) -> GameState:
    state = GameState.from_hand("123m456p789s1122z3z", round_wind="1z", seat_wind="1z")
    opp = state.opponents[opp_index]
    opp.discards = [_id(c) for c in discards]
    opp.riichi = riichi
    if riichi:
        opp.riichi_discard_index = riichi_at if riichi_at is not None else 0
    return state


def test_genbutsu_in_opponent_pile():
    state = _state_with_opponent(1, riichi=True, discards=["5m"])
    visible = visible_counts(state)
    danger = assess_tile_danger(_id("5m"), state, visible)
    # Toimen has it as genbutsu; aggregate is the worst across opponents,
    # but since 5m isn't in any other opponent's pile and there's a riichi
    # threat, toimen's genbutsu doesn't dominate aggregate. Check per-opp.
    toimen = next(p for p in danger.per_opponent if p.seat == 2)
    assert toimen.score == 0
    assert toimen.label == "genbutsu"
    assert any("genbutsu" in r.lower() for r in toimen.reasons)


def test_genbutsu_post_riichi_pool():
    # Toimen declared riichi at their first discard. Then user (or others)
    # discarded 5m afterwards => 5m is genbutsu vs toimen.
    state = GameState.from_hand("123m456p789s1122z3z", round_wind="1z", seat_wind="1z")
    state.opponents[1].discards = [_id("9m")]
    state.opponents[1].riichi = True
    state.opponents[1].riichi_discard_index = 0
    state.user.discards = [_id("5m")]  # discarded after toimen's riichi
    visible = visible_counts(state)
    danger = assess_tile_danger(_id("5m"), state, visible)
    toimen = next(p for p in danger.per_opponent if p.seat == 2)
    assert toimen.score == 0
    assert toimen.label == "genbutsu"


def test_full_suji_reduces_danger():
    # Opponent (in riichi) discarded 1m and 7m. So 4m has full suji vs them.
    state = _state_with_opponent(0, riichi=True, discards=["1m", "7m"])
    visible = visible_counts(state)
    safe = assess_tile_danger(_id("4m"), state, visible)
    risky = assess_tile_danger(_id("5m"), state, visible)
    # The shimocha entry should reflect full suji explicitly.
    shimo_safe = next(p for p in safe.per_opponent if p.seat == 1)
    shimo_risky = next(p for p in risky.per_opponent if p.seat == 1)
    assert shimo_safe.score < shimo_risky.score
    assert any("suji" in r.lower() for r in shimo_safe.reasons)


def test_half_suji_partial_reduction():
    state = _state_with_opponent(0, riichi=True, discards=["1m"])
    visible = visible_counts(state)
    half = assess_tile_danger(_id("4m"), state, visible).per_opponent[0]
    assert "half suji" in " ".join(half.reasons).lower()
    assert 0 < half.score < 100


def test_honor_with_three_visible_is_near_safe():
    # Set up: 1z appears 3 times across discards / dora indicator
    state = GameState.from_hand("123m456p789s1122m3m", round_wind="1z", seat_wind="1z")
    state.opponents[0].riichi = True
    state.opponents[0].riichi_discard_index = 0
    state.opponents[0].discards = [_id("9m"), _id("1z"), _id("1z")]
    state.user.discards = [_id("1z")]
    visible = visible_counts(state)
    danger = assess_tile_danger(_id("1z"), state, visible)
    # 1z is in shimocha's pile -> genbutsu vs them
    shimo = next(p for p in danger.per_opponent if p.seat == 1)
    assert shimo.score == 0
    # And vs the others (no riichi), we still expect very-safe at worst
    others = [p for p in danger.per_opponent if p.seat != 1]
    assert all(o.score <= 25 for o in others)


def test_terminal_is_safer_than_middle_in_neutral_state():
    state = GameState.from_hand("123m456p789s1122z3z", round_wind="1z", seat_wind="1z")
    state.opponents[0].riichi = True
    state.opponents[0].riichi_discard_index = 0
    visible = visible_counts(state)
    one = assess_tile_danger(_id("1m"), state, visible).per_opponent[0]
    five = assess_tile_danger(_id("5m"), state, visible).per_opponent[0]
    assert one.score < five.score


def test_no_riichi_lower_baseline_than_riichi():
    state_no = GameState.from_hand("123m456p789s1122z3z", round_wind="1z", seat_wind="1z")
    state_yes = GameState.from_hand("123m456p789s1122z3z", round_wind="1z", seat_wind="1z")
    state_yes.opponents[0].riichi = True
    state_yes.opponents[0].riichi_discard_index = 0
    vis_no = visible_counts(state_no)
    vis_yes = visible_counts(state_yes)
    no = assess_tile_danger(_id("5m"), state_no, vis_no).per_opponent[0]
    yes = assess_tile_danger(_id("5m"), state_yes, vis_yes).per_opponent[0]
    assert no.score < yes.score
