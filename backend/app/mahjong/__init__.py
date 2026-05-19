"""Pure-Python Riichi Mahjong AI engine.

Phase 1: tile efficiency (shanten / ukeire / discard recommendation).
Phase 2: defense scoring (genbutsu / suji / kabe) + game-state tracking.
"""

from .tiles import (
    NUM_TILES,
    Tile,
    tile_id_from_code,
    tile_code,
    tile_short_name,
    parse_hand,
    counts_to_codes,
    image_filename_for_tile,
    YAOCHU_IDS,
)
from .hand import Hand
from .shanten import calculate_shanten, ShantenBreakdown
from .ukeire import calculate_ukeire
from .analyzer import (
    analyze_hand,
    analyze_game,
    recommend_discards,
    DiscardCandidate,
)
from .game import GameState, PlayerState, Meld, dora_tile_for, dora_tiles
from .defense import TileDanger, OpponentDanger, assess_tile_danger
from .visibility import visible_counts, remaining_counts
from .calls import CallOption, analyze_call
from .yaku import YakuDirection, analyze_yaku_directions
from .han import HanEstimate, estimate_all_han
from .legality import (
    can_user_pon,
    can_user_open_kan,
    can_user_ankan,
    user_ankan_candidates,
    get_legal_chi_options,
    is_chi_seat_legal,
    opponent_call_feasible,
    remaining_unseen,
)
from .validation import count_visible_tiles, validate_tile_pool

__all__ = [
    "NUM_TILES",
    "Tile",
    "tile_id_from_code",
    "tile_code",
    "tile_short_name",
    "parse_hand",
    "counts_to_codes",
    "image_filename_for_tile",
    "YAOCHU_IDS",
    "Hand",
    "calculate_shanten",
    "ShantenBreakdown",
    "calculate_ukeire",
    "analyze_hand",
    "analyze_game",
    "recommend_discards",
    "DiscardCandidate",
    "GameState",
    "PlayerState",
    "Meld",
    "dora_tile_for",
    "dora_tiles",
    "TileDanger",
    "OpponentDanger",
    "assess_tile_danger",
    "visible_counts",
    "remaining_counts",
    "CallOption",
    "analyze_call",
    "YakuDirection",
    "analyze_yaku_directions",
    "HanEstimate",
    "estimate_all_han",
    "can_user_pon",
    "can_user_open_kan",
    "can_user_ankan",
    "user_ankan_candidates",
    "get_legal_chi_options",
    "is_chi_seat_legal",
    "opponent_call_feasible",
    "remaining_unseen",
    "count_visible_tiles",
    "validate_tile_pool",
]
