"""The browser bridge must return byte-identical bodies to the live API.

If this passes, the static GitHub Pages build behaves exactly like the
FastAPI server (same engine, same coercion, same error shapes).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import web_bridge as br
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


def _unwrap(json_str: str):
    payload = json.loads(json_str)
    return payload


def test_tiles_match(client: TestClient):
    api = client.get("/api/tiles").json()
    bridge = _unwrap(br.tiles_json())
    assert bridge["ok"] is True
    assert bridge["data"] == api


@pytest.mark.parametrize(
    "hand",
    [
        "123m456p789s1122z7z",   # 14-tile, clear best discard
        "123m456p789s11122z",    # 14-tile winning
        "123m456p789s1122z",     # 13-tile tenpai
    ],
)
def test_analyze_matches_api(client: TestClient, hand: str):
    api = client.post("/api/analyze", json={"hand": hand}).json()
    bridge = _unwrap(br.analyze_json(json.dumps({"hand": hand})))
    assert bridge["ok"] is True
    assert bridge["data"] == api


def test_analyze_bad_hand_matches_api_error(client: TestClient):
    resp = client.post("/api/analyze", json={"hand": "123m"})
    api_status, api_detail = resp.status_code, resp.json()["detail"]
    bridge = _unwrap(br.analyze_json(json.dumps({"hand": "123m"})))
    assert bridge["ok"] is False
    assert bridge["status"] == api_status == 400
    assert bridge["detail"] == api_detail


def test_analyze_game_matches_api():
    app = create_app()
    client = TestClient(app)
    payload = {
        "round_wind": "1z",
        "seat_wind": "1z",
        "turn_number": 6,
        "hand": ["2m", "2m", "3m", "3m", "5m", "3p", "4p", "5p",
                 "4s", "5s", "6s", "7z", "7z", "9s"],
        "opponents": [
            {},
            {"riichi": True, "riichi_discard_index": 0, "discards": ["9s"]},
            {},
        ],
    }
    api = client.post("/api/analyze-game", json=payload).json()
    bridge = _unwrap(br.analyze_game_json(json.dumps(payload)))
    assert bridge["ok"] is True
    assert bridge["data"] == api


def test_analyze_game_pool_error_matches_api(client: TestClient):
    # Five copies of 1m -> structurally impossible -> 400 tile_pool_invalid.
    payload = {
        "round_wind": "1z",
        "seat_wind": "1z",
        "hand": ["1m"] * 5 + ["2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m", "1p"],
        "opponents": [{}, {}, {}],
    }
    resp = client.post("/api/analyze-game", json=payload)
    bridge = _unwrap(br.analyze_game_json(json.dumps(payload)))
    assert resp.status_code == 400
    assert bridge["ok"] is False and bridge["status"] == 400
    assert bridge["detail"] == resp.json()["detail"]


def test_analyze_call_matches_api(client: TestClient):
    payload = {
        "state": {
            "round_wind": "1z",
            "seat_wind": "1z",
            "hand": ["1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s",
                     "9s", "5z", "5z", "2m", "4m"],
            "opponents": [{}, {}, {}],
        },
        "discarded_tile": "5z",
        "discarder_seat": 2,
    }
    api = client.post("/api/analyze-call", json=payload).json()
    bridge = _unwrap(br.analyze_call_json(json.dumps(payload)))
    assert bridge["ok"] is True
    assert bridge["data"] == api
