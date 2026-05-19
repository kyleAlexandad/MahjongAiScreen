"""Download tile artwork from FluffyStuff/riichi-mahjong-tiles.

The repository is licensed under CC BY 4.0 by FluffyStuff. We only download
the SVGs we need for the 34 tile types plus the tile back/blank/front frame.

Usage::

    python scripts/download_tiles.py            # download into frontend/static/tiles
    python scripts/download_tiles.py --force    # re-download even if files exist
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_BASE = (
    "https://raw.githubusercontent.com/FluffyStuff/riichi-mahjong-tiles/master/Regular"
)

# (tile_id, asset_basename) — aligned with backend/app/mahjong/tiles.py
TILE_ASSETS: list[tuple[int, str]] = [
    (0,  "Man1"),  (1,  "Man2"),  (2,  "Man3"),  (3,  "Man4"),  (4,  "Man5"),
    (5,  "Man6"),  (6,  "Man7"),  (7,  "Man8"),  (8,  "Man9"),
    (9,  "Pin1"),  (10, "Pin2"),  (11, "Pin3"),  (12, "Pin4"),  (13, "Pin5"),
    (14, "Pin6"),  (15, "Pin7"),  (16, "Pin8"),  (17, "Pin9"),
    (18, "Sou1"),  (19, "Sou2"),  (20, "Sou3"),  (21, "Sou4"),  (22, "Sou5"),
    (23, "Sou6"),  (24, "Sou7"),  (25, "Sou8"),  (26, "Sou9"),
    (27, "Ton"),   (28, "Nan"),   (29, "Shaa"),  (30, "Pei"),
    (31, "Haku"),  (32, "Hatsu"), (33, "Chun"),
]
EXTRA_ASSETS = ["Back", "Blank", "Front"]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _download(url: str, dest: Path, force: bool) -> bool:
    """Return True if a file was written, False if skipped."""
    if dest.exists() and not force and dest.stat().st_size > 0:
        return False
    req = Request(url, headers={"User-Agent": "MahjongAiScreen/0.1 downloader"})
    with urlopen(req, timeout=30) as resp:
        data = resp.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if files already exist")
    parser.add_argument(
        "--out",
        type=Path,
        default=_project_root() / "frontend" / "static" / "tiles",
        help="output directory (default: frontend/static/tiles)",
    )
    args = parser.parse_args(argv)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    todo = [name for _, name in TILE_ASSETS] + EXTRA_ASSETS
    print(f"Downloading {len(todo)} SVG assets into {out_dir}")

    written = 0
    skipped = 0
    failed: list[str] = []
    for name in todo:
        url = f"{REPO_BASE}/{name}.svg"
        dest = out_dir / f"{name}.svg"
        try:
            if _download(url, dest, args.force):
                written += 1
                print(f"  + {name}.svg")
            else:
                skipped += 1
        except (HTTPError, URLError) as exc:
            failed.append(f"{name}: {exc}")
            print(f"  ! failed {name}.svg ({exc})")

    print(
        f"Done. Written: {written}, skipped (already present): {skipped}, failed: {len(failed)}."
    )
    if failed:
        print("Failures:")
        for line in failed:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
