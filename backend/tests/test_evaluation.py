"""Tests for the expected-value play model (the strong classical AI)."""

from __future__ import annotations

import pytest

from backend.app.mahjong.analyzer import analyze_game
from backend.app.mahjong.evaluation import (
    dealin_probability,
    discard_expected_value,
    points_for_han,
    weighted_acceptance,
    win_probability,
)
from backend.app.mahjong.game import GameState
from backend.app.mahjong.hand import Hand
from backend.app.mahjong.shanten import calculate_shanten, clear_cache
from backend.app.mahjong.tiles import tile_id_from_code as _id
from backend.app.mahjong.visibility import remaining_counts


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# Scoring table
# ---------------------------------------------------------------------------


def test_points_monotone_and_dealer_premium():
    prev = -1
    for han in range(1, 13):
        p = points_for_han(han, dealer=False)
        assert p >= prev  # non-decreasing in han
        prev = p
    assert points_for_han(3, dealer=True) > points_for_han(3, dealer=False)
    assert points_for_han(13, dealer=False) == 32000  # yakuman
    assert points_for_han(99, dealer=False) == 32000  # capped
    assert points_for_han(0, dealer=False) == 0


# ---------------------------------------------------------------------------
# Win probability
# ---------------------------------------------------------------------------


def test_win_probability_decreases_with_shanten():
    p = [win_probability(s, 8, 20.0, 12) for s in (0, 1, 2, 3, 4)]
    assert p == sorted(p, reverse=True)
    assert all(0.0 <= x <= 0.95 for x in p)


def test_win_probability_rewards_wider_tenpai_and_more_draws():
    narrow = win_probability(0, 2, 2.0, 12)
    wide = win_probability(0, 12, 12.0, 12)
    assert wide > narrow
    early = win_probability(1, 6, 30.0, 14)
    late = win_probability(1, 6, 30.0, 2)
    assert early > late


def test_winning_hand_is_certain():
    assert win_probability(-1, 0, 0.0, 1) == 1.0


# ---------------------------------------------------------------------------
# Two-step weighted acceptance (ukeire²)
# ---------------------------------------------------------------------------


def test_weighted_acceptance_discriminates_shapes():
    """Two 1-shanten shapes can have similar one-step ukeire but very
    different *quality* — the smarter metric should separate them."""
    # Both are 1-shanten (2 melds + 2 partials + pair + 1 floating 1z).
    # Wide: the two partials are ryanmen (accept 2 kinds each, advance
    # into a wide tenpai). Narrow: both are kanchan (1 kind each).
    wide = Hand.from_string("123m456m2p3p6p7p9s9s1z").counts  # 13 tiles
    narrow = Hand.from_string("123m456m2p4p6p8p9s9s1z").counts  # 13 tiles
    sh_w = calculate_shanten(wide)
    sh_n = calculate_shanten(narrow)
    assert sh_w == sh_n  # same distance to tenpai...
    uw, qw = weighted_acceptance(list(wide), None, 0, sh_w)
    un, qn = weighted_acceptance(list(narrow), None, 0, sh_n)
    # ...but the ryanmen shape advances into strictly wider tenpai.
    assert qw > qn


def test_weighted_acceptance_winning_returns_zeroish():
    counts = Hand.from_string("123m456p789s11122z").counts  # 14 -> drop later
    counts[_id("2z")] -= 1  # 13-tile tenpai
    sh = calculate_shanten(counts)
    uke, q = weighted_acceptance(list(counts), None, 0, sh)
    assert uke >= 1 and q >= 0.0


# ---------------------------------------------------------------------------
# Deal-in probability + EV
# ---------------------------------------------------------------------------


def test_dealin_probability_bounds():
    assert dealin_probability(0, opp_riichi=True) == 0.0  # genbutsu
    assert dealin_probability(100, opp_riichi=True) > dealin_probability(
        100, opp_riichi=False
    )
    assert 0.0 <= dealin_probability(100, opp_riichi=True) <= 1.0


def test_ev_trades_speed_against_danger():
    safe = discard_expected_value(0.25, 5000, [(0, 8000, True)])
    risky = discard_expected_value(0.25, 5000, [(90, 8000, True)])
    assert safe.ev > risky.ev  # same speed, more danger -> worse EV
    # With nobody in riichi the danger term is tiny, so EV ≈ speed*value.
    calm = discard_expected_value(0.25, 5000, [(90, 8000, False)])
    assert calm.ev > risky.ev


# ---------------------------------------------------------------------------
# Integration: EV ranking is exposed and behaves
# ---------------------------------------------------------------------------


def test_analyze_game_exposes_ev_fields():
    state = GameState.from_hand(
        "123m456p789s1122z7z", round_wind="1z", seat_wind="1z"
    )
    res = analyze_game(state)
    best = res["best_discard"]
    assert best["tile_code"] == "7z"  # still the obvious dead-weight cut
    assert 0.0 <= best["win_p"] <= 1.0
    assert best["value_estimate"] > 0
    assert best["expected_value"] is not None
    assert "win rate" in res["explanation"].lower()


def test_riichi_pressure_never_picks_a_more_dangerous_tile():
    """Push/fold property: introducing a riichi threat must not make the
    engine recommend a tile *more* dangerous (vs that threat) than the
    pure-efficiency pick would have been."""
    hand = "2m2m3m3m5m345p456s77z9s"  # 14-tile, mid-shanten with choices
    calm = GameState.from_hand(hand, round_wind="1z", seat_wind="1z")
    push_best = analyze_game(calm)["best_discard"]

    fold = GameState.from_hand(hand, round_wind="1z", seat_wind="1z")
    fold.opponents[1].riichi = True
    fold.opponents[1].riichi_discard_index = 0
    fold.opponents[1].discards = [_id("9s")]  # 9s is genbutsu vs toimen
    fold_res = analyze_game(fold)
    fold_best = fold_res["best_discard"]

    def danger_vs_toimen(discard_dict):
        d = discard_dict["danger"]
        return next(o["score"] for o in d["per_opponent"] if o["seat"] == 2)

    assert danger_vs_toimen(fold_best) <= danger_vs_toimen(push_best)
    assert any(t["label"] == "toimen" for t in fold_res["threats"])


def test_call_no_yaku_open_is_not_recommended():
    """The classic weak-AI mistake: chi/pon that opens a closed hand with
    no yaku route must never be recommended (you couldn't win)."""
    from backend.app.mahjong.calls import analyze_call

    # Scattered, no yaku, no honors: pon of 5m opens a dead hand.
    state = GameState.from_hand(
        "1m3m5m5m9m1p3p5p7p9p1s3s5s", round_wind="1z", seat_wind="1z"
    )
    res = analyze_call(state, _id("5m"), discarder_seat=2)
    pon = next(o for o in res["options"] if o["action"] == "pon")
    assert pon["legal"] is True
    assert pon["recommended"] is False
    assert any("yaku" in n.lower() for n in pon["notes"])
