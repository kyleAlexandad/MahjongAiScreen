# MahjongAiScreen

A Japanese Riichi Mahjong AI assistant for **learning, hand analysis, and
manual game tracking**. It does **not** auto-play any online client.

This repository is built in stages.

### Phase 1 — tile efficiency

- Pure-Python tile / hand model
- Shanten calculation (standard + chiitoitsu + kokushi)
- Ukeire (effective tiles)
- Best-discard recommendation with a beginner-friendly explanation
- A Quick-analyze web UI: click tiles → instant discard advice

### Phase 2 — defense + manual game tracking *(this commit)*

- Game-state model: round wind, seat wind, dora indicators, honba, every
  player's discards / melds, riichi flags, post-riichi safe-tile timeline
- Visible-tile counting (hand + dora + discards + every meld)
- Tightened ukeire — copies remaining are now capped by what is still
  likely to exist outside the table
- Defense engine:
  - **Genbutsu** vs each opponent (own pile + post-riichi public discards)
  - **Suji** (full / half) vs riichi opponents
  - **Kabe** when 4 copies of a tile are visible
  - Honor / wind / dragon / edge / middle heuristics
  - 0–100 danger score per tile with human-readable reasons
- Recommendation now blends efficiency and defense: same-shanten
  candidates are tie-broken by danger when any opponent is in riichi
- New tracking UI:
  - Setup screen (winds, dora, starting hand)
  - Tracking screen with all four rivers, opponent melds, riichi toggles,
    dora panel, draw / discard actions
  - Undo, reset hand, return to setup
  - localStorage persistence
- All Phase 1 functionality is preserved as the **Quick analyze** tab

### Deferred to later phases

- Riichi-declaration *decisions* by the AI
- Call (chi / pon / kan) *decisions* by the AI
- Yaku and hand-value estimation
- Push-vs-fold cost-benefit modelling

---

## Live web version (GitHub Pages)

The whole app also runs as a **static site with no backend** — the
pure-Python engine executes in the browser via
[Pyodide](https://pyodide.org). The prebuilt site lives in `docs/`.

To publish it for free on GitHub Pages (one-time, repo owner):

> **Settings → Pages → Build and deployment → Source: _Deploy from a
> branch_ → Branch: `main`, folder: `/docs` → Save.**

After ~1 minute it is live at
`https://<user>.github.io/MahjongAiScreen/`. First load downloads the
Python runtime (~6 MB, then browser-cached); analysis afterwards is
instant and fully offline.

Rebuild the static bundle after any backend/frontend change:

```bash
python scripts/build_pages.py   # regenerates docs/
```

`backend/tests/test_web_bridge.py` asserts the in-browser bridge returns
byte-identical results to the FastAPI server, so the two never diverge.

## Quick start (local server)

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download tile images (one-time, requires internet access)
python scripts/download_tiles.py

# 4. Run the web app
python run.py

# 5. Open http://127.0.0.1:8000 in your browser
```

If you cannot reach GitHub, the UI still works — tiles will render with a
text-only fallback (e.g. "5m", "Rd").

## Run the tests

```bash
pytest
```

## Project layout

```
MahjongAiScreen/
├── backend/
│   └── app/
│       ├── main.py              FastAPI app + static mounts
│       ├── api/routes.py        /api/* endpoints
│       └── mahjong/             Pure-Python AI engine
│           ├── tiles.py
│           ├── hand.py
│           ├── shanten.py
│           ├── ukeire.py
│           ├── visibility.py    visible/remaining tile counts
│           ├── game.py          GameState + dora helpers
│           ├── defense.py       genbutsu / suji / kabe / danger
│           └── analyzer.py      analyze_hand + analyze_game
├── backend/tests/               pytest tests for the engine + API
├── frontend/static/             Vanilla HTML/CSS/JS UI
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── tiles/                   Populated by download_tiles.py
├── scripts/download_tiles.py
├── run.py                       Convenience entry point
├── requirements.txt
└── README.md
```

## Tile notation

Hands are written in **mpsz** notation:

| Suit       | Letter | Examples                          |
|------------|--------|-----------------------------------|
| Manzu      | `m`    | `1m`, `5m`, `9m`                  |
| Pinzu      | `p`    | `1p`, `5p`, `9p`                  |
| Souzu      | `s`    | `1s`, `5s`, `9s`                  |
| Honors `z` | `z`    | `1z=E`, `2z=S`, `3z=W`, `4z=N`, `5z=Haku (white)`, `6z=Hatsu (green)`, `7z=Chun (red)` |

You can also pass compact strings like `123m456p789s11122z` to the engine.

## API

All endpoints accept JSON and return JSON. See `backend/app/api/routes.py`
for full schemas; an abridged reference:

| Method | Path                   | Body                                                    |
|--------|------------------------|---------------------------------------------------------|
| GET    | `/api/tiles`           | (none) — tile metadata + image filenames                |
| POST   | `/api/shanten`         | `{ "hand": "..." }` — shanten only                      |
| POST   | `/api/ukeire`          | `{ "hand": "..." }` — 13-tile improving tiles           |
| POST   | `/api/analyze`         | `{ "hand": "..." }` — efficiency-only (Phase 1)         |
| POST   | `/api/analyze-game`    | full `GameState` snapshot — efficiency + defense        |

Example `analyze-game` request body:

```json
{
  "round_wind": "1z",
  "seat_wind": "1z",
  "honba": 0,
  "riichi_sticks": 0,
  "dora_indicators": ["3m"],
  "turn_number": 5,
  "hand": ["1m","2m","3m","4p","5p","6p","7s","8s","9s","1z","1z","2z","2z","7z"],
  "drawn_tile": "7z",
  "user":      { "discards": [], "melds": [], "riichi": false, "riichi_discard_index": null },
  "opponents": [
    { "discards": ["9m"], "melds": [], "riichi": true,  "riichi_discard_index": 0 },
    { "discards": [],     "melds": [], "riichi": false, "riichi_discard_index": null },
    { "discards": [],     "melds": [], "riichi": false, "riichi_discard_index": null }
  ]
}
```

The response includes `shanten`, `shanten_breakdown`, `discards` (every
candidate ranked best-first with `shanten_after`, `ukeire`, `ukeire_count`,
`danger.score`, `danger.label`, `danger.summary`, and per-opponent reasons),
`best_discard`, `threats` (list of riichi opponents), `dora_tiles`, and a
beginner-friendly `explanation` string.

## Notes on correctness

- Shanten is `min(normal, chiitoitsu, kokushi)` and validated against
  reference hands in `backend/tests/test_shanten.py`.
- Ukeire copy counts subtract every visible copy (your hand, every
  player's discards, all melds, all dora indicators).
- Defense scoring is **heuristic** — it produces fast beginner-friendly
  guidance, not a precise win-probability model. Numbers should be read
  as "rough risk class" rather than "exact percent chance of dealing in".
- Genbutsu via post-riichi public discards uses pile-depth ordering since
  no full turn-by-turn timeline is recorded yet; in practice this matches
  the common "all discards added after the riichi indicator are safe vs
  that opponent" heuristic.
