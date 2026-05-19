"""Tile representation and parser tests."""

from __future__ import annotations

import pytest

from backend.app.mahjong.tiles import (
    NUM_TILES,
    Tile,
    YAOCHU_IDS,
    counts_from_ids,
    counts_to_codes,
    parse_hand,
    tile_code,
    tile_id_from_code,
)


def test_tile_id_round_trip():
    for tid in range(NUM_TILES):
        code = tile_code(tid)
        assert tile_id_from_code(code) == tid, code


def test_parse_simple():
    assert parse_hand("123m") == [0, 1, 2]
    assert parse_hand("9p") == [17]
    assert parse_hand("1z2z3z4z5z6z7z") == [27, 28, 29, 30, 31, 32, 33]


def test_parse_compact_block():
    ids = parse_hand("123m456p789s11122z")
    assert sorted(ids) == sorted([0, 1, 2, 12, 13, 14, 24, 25, 26, 27, 27, 27, 28, 28])


def test_parse_rejects_invalid():
    # Note: '0m' / '0p' / '0s' are NOW valid red-five aliases (return 4/13/22).
    # Out-of-range honors and bad shapes must still error.
    with pytest.raises(ValueError):
        parse_hand("8z")
    with pytest.raises(ValueError):
        parse_hand("123")
    with pytest.raises(ValueError):
        parse_hand("m123")
    with pytest.raises(ValueError):
        parse_hand("0z")  # honors don't have a red zero alias


def test_parse_accepts_red_five_aliases():
    assert parse_hand("0m") == [4]
    assert parse_hand("0p") == [13]
    assert parse_hand("0s") == [22]


def test_counts_round_trip():
    ids = parse_hand("11223344m5566p77s")
    counts = counts_from_ids(ids)
    assert sum(counts) == len(ids)
    assert sorted(counts_to_codes(counts)) == sorted(tile_code(i) for i in ids)


def test_yaochu_membership():
    expected_codes = {"1m", "9m", "1p", "9p", "1s", "9s", "1z", "2z", "3z", "4z", "5z", "6z", "7z"}
    actual_codes = {tile_code(t) for t in YAOCHU_IDS}
    assert actual_codes == expected_codes


def test_tile_attrs():
    t = Tile(tile_id_from_code("5m"))
    assert t.suit == "m"
    assert t.number == 5
    assert not t.is_honor
    assert not t.is_terminal

    t = Tile(tile_id_from_code("1s"))
    assert t.is_terminal
    assert t.is_yaochu

    t = Tile(tile_id_from_code("7z"))
    assert t.is_honor
    assert t.long_name == "Chun"

    assert Tile(tile_id_from_code("3p")).image_filename == "Pin3.svg"
    assert Tile(tile_id_from_code("1z")).image_filename == "Ton.svg"
    assert Tile(tile_id_from_code("5z")).image_filename == "Haku.svg"
