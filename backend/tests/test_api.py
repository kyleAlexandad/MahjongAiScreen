"""HTTP-layer smoke tests using fastapi.TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.mahjong.shanten import clear_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_list_tiles(client: TestClient):
    resp = client.get("/api/tiles")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 34
    assert {t["tile_id"] for t in data} == set(range(34))
    by_code = {t["code"]: t for t in data}
    assert by_code["5m"]["image"] == "Man5.svg"
    assert by_code["1z"]["image"] == "Ton.svg"


def test_shanten_endpoint(client: TestClient):
    resp = client.post("/api/shanten", json={"hand": "123m456p789s11122z"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["shanten"] == -1
    assert body["best_form"] == "normal"


def test_ukeire_endpoint(client: TestClient):
    resp = client.post("/api/ukeire", json={"hand": "123m456p789s1122z"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["shanten"] == 0
    assert body["ukeire_count"] == 4


def test_analyze_endpoint_14(client: TestClient):
    resp = client.post(
        "/api/analyze",
        json={"hand": "123m456p789s1122z7z"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tile_count"] == 14
    assert body["best_discard"]["tile_code"] == "7z"
    assert body["best_discard"]["shanten_after"] == 0


def test_invalid_hand_returns_400(client: TestClient):
    resp = client.post("/api/analyze", json={"hand": "11111m"})
    assert resp.status_code == 400


def test_analyze_endpoint_accepts_id_list(client: TestClient):
    # 13 tiles by tile-id list; tenpai shanpon hand
    ids = []
    for code in ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "1z", "1z", "2z", "2z"]:
        from backend.app.mahjong.tiles import tile_id_from_code
        ids.append(tile_id_from_code(code))
    resp = client.post("/api/analyze", json={"hand": ids})
    assert resp.status_code == 200
    assert resp.json()["shanten"] == 0


# ---------------------------------------------------------------------------
# /api/analyze-game (Phase 2)
# ---------------------------------------------------------------------------


def _empty_player() -> dict:
    return {"discards": [], "melds": [], "riichi": False, "riichi_discard_index": None}


def test_analyze_game_endpoint_basic(client: TestClient):
    payload = {
        "round_wind": "1z",
        "seat_wind": "1z",
        "honba": 0,
        "riichi_sticks": 0,
        "dora_indicators": [],
        "turn_number": 1,
        "hand": ["1m","2m","3m","4p","5p","6p","7s","8s","9s","1z","1z","2z","2z","7z"],
        "drawn_tile": "7z",
        "user": _empty_player(),
        "opponents": [_empty_player(), _empty_player(), _empty_player()],
    }
    resp = client.post("/api/analyze-game", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["best_discard"]["tile_code"] == "7z"
    assert body["best_discard"]["danger"] is not None
    assert body["threats"] == []


def test_analyze_game_endpoint_with_riichi_threat(client: TestClient):
    payload = {
        "round_wind": "1z",
        "seat_wind": "1z",
        "honba": 0,
        "riichi_sticks": 0,
        "dora_indicators": [],
        "turn_number": 5,
        "hand": ["1m","2m","3m","4p","5p","6p","7s","8s","9s","1z","1z","2z","2z","7z"],
        "drawn_tile": "7z",
        "user": _empty_player(),
        "opponents": [
            {"discards": ["7z", "9m"], "melds": [], "riichi": True, "riichi_discard_index": 0},
            _empty_player(),
            _empty_player(),
        ],
    }
    resp = client.post("/api/analyze-game", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Discarding 7z is genbutsu vs the riichi shimocha.
    assert body["best_discard"]["tile_code"] == "7z"
    danger = body["best_discard"]["danger"]
    shimo = next(p for p in danger["per_opponent"] if p["seat"] == 1)
    assert shimo["score"] == 0
    assert shimo["label"] == "genbutsu"
    assert any(t["seat"] == 1 for t in body["threats"])


def test_analyze_game_endpoint_rejects_bad_size(client: TestClient):
    payload = {
        "round_wind": "1z",
        "seat_wind": "1z",
        "hand": ["1m", "2m", "3m"],
        "user": _empty_player(),
        "opponents": [_empty_player(), _empty_player(), _empty_player()],
    }
    resp = client.post("/api/analyze-game", json=payload)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tile-pool sanity validation (Phase 2.10)
# ---------------------------------------------------------------------------


def test_analyze_game_rejects_more_than_4_copies(client: TestClient):
    # Hand legitimately has 14 tiles but with 5 copies of 1m visible across
    # hand + a discard river — pool inconsistent.
    payload = {
        "round_wind": "1z",
        "seat_wind": "1z",
        "hand": ["1m", "1m", "1m", "1m", "5p", "6p", "7p", "8p", "9p", "1z", "1z", "2z", "3z", "4z"],
        "user": _empty_player(),
        "opponents": [
            {"discards": ["1m"], "melds": [], "riichi": False, "riichi_discard_index": None},
            _empty_player(),
            _empty_player(),
        ],
    }
    resp = client.post("/api/analyze-game", json=payload)
    assert resp.status_code == 400
    body = resp.json()
    msgs = body["detail"]["messages"]
    assert any("1m" in m for m in msgs)


def test_analyze_call_rejects_invalid_pool(client: TestClient):
    payload = {
        "state": {
            "round_wind": "1z",
            "seat_wind": "1z",
            "hand": ["1m", "1m", "1m", "1m", "5p", "6p", "7p", "8p", "9p", "1z", "1z", "2z", "3z", "4z"],
            "user": _empty_player(),
            "opponents": [
                {"discards": ["1m"], "melds": [], "riichi": False, "riichi_discard_index": None},
                _empty_player(),
                _empty_player(),
            ],
        },
        "discarded_tile": "1m",
        "discarder_seat": 1,
    }
    resp = client.post("/api/analyze-call", json=payload)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/legality
# ---------------------------------------------------------------------------


def test_legality_endpoint_pon_legal(client: TestClient):
    # User has 9m + 9m in hand; opponent discards 9m -> pon legal, kan illegal.
    payload = {
        "state": {
            "round_wind": "1z",
            "seat_wind": "1z",
            "hand": ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "9m", "9m", "1z", "2z"],
            "user": _empty_player(),
            "opponents": [_empty_player(), _empty_player(), _empty_player()],
        },
        "discarded_tile": "9m",
        "discarder_seat": 2,
    }
    resp = client.post("/api/legality", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["can_pon"] is True
    assert body["can_kan"] is False
    assert body["chi_options"] == []  # not from kamicha


def test_legality_endpoint_pon_illegal_with_one_tile(client: TestClient):
    # Only 1 9m in hand -> pon and kan must be illegal.
    payload = {
        "state": {
            "round_wind": "1z",
            "seat_wind": "1z",
            "hand": ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s", "9m", "1z", "2z", "3z"],
            "user": _empty_player(),
            "opponents": [_empty_player(), _empty_player(), _empty_player()],
        },
        "discarded_tile": "9m",
        "discarder_seat": 2,
    }
    resp = client.post("/api/legality", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["can_pon"] is False
    assert body["can_kan"] is False


def test_legality_endpoint_chi_only_from_kamicha(client: TestClient):
    payload = {
        "state": {
            "round_wind": "1z",
            "seat_wind": "1z",
            "hand": ["1m", "2m", "4p", "5p", "6p", "7s", "8s", "9s", "9m", "9m", "1z", "2z", "3z"],
            "user": _empty_player(),
            "opponents": [_empty_player(), _empty_player(), _empty_player()],
        },
        "discarded_tile": "3m",
        "discarder_seat": 3,  # kamicha
    }
    resp = client.post("/api/legality", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert any(opt == [0, 1] for opt in body["chi_options"])  # 1m+2m

    # Now from toimen (seat 2) -> illegal.
    payload["discarder_seat"] = 2
    resp = client.post("/api/legality", json=payload)
    body = resp.json()
    assert body["chi_options"] == []
