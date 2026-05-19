// MahjongAiScreen — frontend
//
// Vanilla JS, no build step. Two flows:
//   * Quick analyze : Phase 1-style hand-only analysis.
//   * Game tracking : click-driven manual round tracking with defense + AI badges.
//
// Game-tracking design:
//   - Each player has a seat: 0=user, 1=shimocha (right), 2=toimen (across), 3=kamicha (left).
//   - Play order is 0 -> 1 -> 2 -> 3 -> 0, starting from the dealer seat.
//   - Dealer is the seat whose seat-wind == round-wind == East at hand start; we let the user
//     override this in setup if they prefer.
//   - The center tile selector is context-aware: clicking a tile means
//       "user drew this" if it's the user's turn and they haven't drawn,
//       "<seat> discarded this" otherwise.

const TILE_IMG_BASE = "/tiles";
const API_BASE = "/api";

const SUIT_ROWS = [
  { suit: "m", label: "M", count: 9 },
  { suit: "p", label: "P", count: 9 },
  { suit: "s", label: "S", count: 9 },
  { suit: "z", label: "Z", count: 7 },
];

// Extended tile ids used FRONTEND-ONLY for red fives. They normalise to
// regular 5m / 5p / 5s (4 / 13 / 22) before any logic that cares about
// tile identity (count >= 4 limits, chi-shape detection, sending to the
// backend). The extended ids only carry visual + dora-counting information.
const RED_5M = 34;
const RED_5P = 35;
const RED_5S = 36;
const RED_TO_NORMAL = { 34: 4, 35: 13, 36: 22 };
const NORMAL_TO_RED = { 4: 34, 13: 35, 22: 36 };
// Red fives intentionally re-use the regular 5m / 5p / 5s artwork. The red
// identity is added purely via CSS (.is-red-five glow + .tile-aka-badge).
// This avoids depending on extra image files that may not exist in every
// asset bundle, and guarantees red dora never renders blank.
function normalizeTileId(id) { return RED_TO_NORMAL[id] ?? id; }
function isRedFive(id) { return id === 34 || id === 35 || id === 36; }
function normalizeHand(hand) { return hand.map(normalizeTileId); }
function countAkaInList(list) { return list.filter(isRedFive).length; }
function asNormalizedCounts(hand) {
  const c = {};
  for (const id of hand) {
    const n = normalizeTileId(id);
    c[n] = (c[n] || 0) + 1;
  }
  return c;
}

// Aka-aware tile-count limits.
//
// Standard aka-dora rules: each suit has a real-world deck of
//   * 3 normal 5 (m / p / s)  +  1 red 5 (m / p / s)  =  4 fives total
// Every other tile has 4 normal copies. The helpers below let the tile
// selector and the click handler enforce these limits without conflating
// "I already have 4 fives total" with "I already have 3 normal fives".
//
// `addedRed`     — count of red copies of THIS suit's 5 already added.
// `addedNormal`  — count of normal copies of THIS suit's 5 already added.
// `addedTotal`   — combined for the same tile id (after normalization).

function akaBucketsForBase(list, baseId) {
  // Returns { red, normal, total } for a base 5 id (4 / 13 / 22).
  const red = list.filter((id) => isRedFive(id) && normalizeTileId(id) === baseId).length;
  const total = list.filter((id) => normalizeTileId(id) === baseId).length;
  return { red, normal: total - red, total };
}

// Returns how many MORE copies of `tileId` can still be added to a list
// that already contains the given visible / hand tiles.
//
//   * If `tileId` is a red five (ext id 34/35/36):
//       max 1 in total, AND combined (normal + red) must stay ≤ 4.
//   * If `tileId` is a regular five (4/13/22):
//       max 3 normal copies, AND combined ≤ 4.
//   * Any other tile: max 4 copies.
function akaAwareRemaining(list, tileId) {
  const baseId = normalizeTileId(tileId);
  if (isRedFive(tileId)) {
    const { red, total } = akaBucketsForBase(list, baseId);
    if (red >= 1) return 0;
    return total < 4 ? 1 : 0;
  }
  if (NORMAL_TO_RED[tileId] !== undefined) {
    const { normal, total } = akaBucketsForBase(list, baseId);
    return Math.max(0, Math.min(3 - normal, 4 - total));
  }
  // Generic tile — count anything that normalizes to it.
  let n = 0;
  for (const id of list) if (normalizeTileId(id) === baseId) n++;
  return Math.max(0, 4 - n);
}

// ---------------------------------------------------------------------------
// Call-legality helpers (mirror backend/app/mahjong/legality.py).
//
// Both layers must agree:
//   * The frontend uses these to disable illegal Pon/Kan/Chi drop zones
//     before the user can drop on them.
//   * `finishMeldDrop` re-checks them as a defensive guard so an
//     illegal drag never mutates the snapshot.
// All checks operate on NORMALIZED ids so red 5 + normal 5 satisfies a
// pon/kan/chi on a regular 5.
// ---------------------------------------------------------------------------

function canUserPon(snap, discardedTile) {
  if (!snap || discardedTile == null) return false;
  const counts = countOccurrences(snap.hand);
  const base = normalizeTileId(discardedTile);
  return (counts[base] || 0) >= 2;
}

function canUserOpenKan(snap, discardedTile) {
  if (!snap || discardedTile == null) return false;
  const counts = countOccurrences(snap.hand);
  const base = normalizeTileId(discardedTile);
  return (counts[base] || 0) >= 3;
}

// Returns the list of [a, b] consumed pairs that form legal chi shapes,
// considering kamicha-only restriction and the user's hand.
// `callerSeat` defaults to 0 (the user) — opp callers can't be strictly
// validated because we don't see their hand.
function getLegalChiOptions(snap, discardedTile, discarderSeat, callerSeat = 0) {
  if (!snap || discardedTile == null) return [];
  const base = normalizeTileId(discardedTile);
  if (base >= 27) return [];                                  // honors: no chi
  if (discarderSeat !== ((callerSeat + 3) % 4)) return [];     // kamicha only
  const suitBase = Math.floor(base / 9) * 9;
  const n = (base % 9) + 1;
  const geom = [];
  if (n >= 3) geom.push([base - 2, base - 1]);
  if (n >= 2 && n <= 8) geom.push([base - 1, base + 1]);
  if (n <= 7) geom.push([base + 1, base + 2]);
  const inSuit = ([a, b]) =>
    a >= suitBase && a < suitBase + 9 && b >= suitBase && b < suitBase + 9;
  const filtered = geom.filter(inSuit);
  if (callerSeat !== 0) return filtered;
  const counts = countOccurrences(snap.hand);
  return filtered.filter(([a, b]) => {
    if (a === b) return (counts[a] || 0) >= 2;
    return (counts[a] || 0) >= 1 && (counts[b] || 0) >= 1;
  });
}

function isChiSeatLegal(callerSeat, discarderSeat) {
  return discarderSeat === ((callerSeat + 3) % 4);
}

// Tile-pool feasibility (mirrors backend/app/mahjong/legality.py
// `opponent_call_feasible`). An opponent's hand is hidden, but every other
// tile is visible, so a call whose hidden tiles can't exist anymore is
// physically impossible and must be rejected even though we can't see the
// hand. `tileId` is still in the discarder's river at call time, so it is
// counted as visible (one of the four copies); the meld's other tiles must
// come from the opponent's hidden hand and therefore from the unseen pool.
//   pon -> 2 hidden copies of tileId      kan -> 3 (daiminkan)
//   chi -> 1 hidden copy of EACH run tile
function opponentCallFeasible(snap, callType, tileId, runPair) {
  if (!snap || tileId == null) return false;
  const base = normalizeTileId(tileId);
  if (!(base >= 0 && base < 34)) return false;
  const visible = computeVisibleCounts(snap);
  const unseen = (tid) => Math.max(0, 4 - (visible[tid] || 0));
  if (callType === "pon") return unseen(base) >= 2;
  if (callType === "kan") return unseen(base) >= 3;
  if (callType === "chi") {
    if (!runPair) return true;
    const a = normalizeTileId(runPair[0]);
    const b = normalizeTileId(runPair[1]);
    if (a === b) return false;
    return unseen(a) >= 1 && unseen(b) >= 1;
  }
  return true;
}

// The called tile leaves the discarder's river and joins the caller's
// meld. Shared by the drag-drop flow and the "Opponent called" picker flow
// so neither path double-counts the tile (once in the river, once in the
// meld). Also keeps a post-riichi discard index pointing at the right slot.
function removeCalledTileFromRiver(snap, fromSeat, tileId) {
  const discarder = fromSeat === 0 ? snap.user : snap.opponents[fromSeat - 1];
  if (!discarder) return;
  let idx = discarder.discards.lastIndexOf(tileId);
  if (idx < 0) idx = discarder.discards.lastIndexOf(normalizeTileId(tileId));
  if (idx >= 0) {
    discarder.discards.splice(idx, 1);
    if (discarder.riichi_discard_index != null && idx < discarder.riichi_discard_index) {
      discarder.riichi_discard_index -= 1;
    }
  }
}

// Compute legality for a single drop zone given the latest discard. For
// the user (callerSeat 0) we strictly validate the hand; for opponents we
// allow the drop (manual tracking) since their hand is hidden.
function callZoneLegality(snap, ui, callerSeat, callType) {
  const last = ui ? ui.lastDiscard : null;
  if (!last) return { legal: false, reason: "no_discard", soft: false };
  if (last.seat === callerSeat) return { legal: false, reason: "self", soft: false };
  if (callerSeat === 0) {
    if (callType === "pon") {
      return canUserPon(snap, last.tile_id)
        ? { legal: true, reason: "", soft: false }
        : { legal: false, reason: "not_enough_pon", soft: false };
    }
    if (callType === "kan") {
      return canUserOpenKan(snap, last.tile_id)
        ? { legal: true, reason: "", soft: false }
        : { legal: false, reason: "not_enough_kan", soft: false };
    }
    if (callType === "chi") {
      if (!isChiSeatLegal(0, last.seat)) {
        return { legal: false, reason: "chi_not_kamicha", soft: false };
      }
      const opts = getLegalChiOptions(snap, last.tile_id, last.seat, 0);
      return opts.length > 0
        ? { legal: true, reason: "", soft: false }
        : { legal: false, reason: "no_chi_tiles", soft: false };
    }
  }
  // Opp-side zone: allow with a "soft" flag (not strictly verified).
  return { legal: true, reason: "manual", soft: true };
}

function legalityWarningKey(reason) {
  return ({
    not_enough_pon: "cannot_pon",
    not_enough_kan: "cannot_kan",
    chi_not_kamicha: "warn_chi_not_kamicha",
    no_chi_tiles: "cannot_chi_no_tiles",
    self: "cannot_call_own_discard",
  })[reason] || "invalid_action_rejected";
}

const STORAGE_KEY = "mahjongAiScreen.gameState.v2";

const SEAT_KEYS = ["you", "shimocha", "toimen", "kamicha"];
const SEAT_KEYS_SHORT = ["you_short", "shimocha_short", "toimen_short", "kamicha_short"];

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let tileMetadata = null;
let assetsAvailable = false;

const state = {
  view: "quick",
  quick: {
    hand: zeros(34),
  },
  game: {
    phase: "setup",
    config: {
      roundWind: "1z",
      seatWind: "1z",
      honba: 0,
      riichiSticks: 0,
      // Note: dealer position is *always* derived from seat wind (East seat is
      // dealer in Riichi). We no longer store a user-set dealerSeat.
      doraIndicators: [],
      startingHand: [],
    },
    snapshot: null,
    history: [],
    // UI-only state (not sent to backend)
    ui: {
      currentTurnSeat: 0,
      lastDiscard: null,        // { seat, tile_id }
      pendingCall: null,        // { type: 'chi'|'pon'|'kan', tile_id }
      lastAnalysis: null,       // last /api/analyze-game payload (for badges)
      message: "",
    },
  },
};

// Picker callbacks.
let pickerCallback = null;

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  init().catch((err) => {
    console.error(err);
    alert(`Failed to load: ${err.message}`);
  });
});

async function init() {
  await Promise.all([loadTileMetadata(), probeAssets()]);
  setLanguage(getLanguage()); // applies stored language to data-i18n elements
  bindLanguageToggle();
  bindTabs();
  initQuickView();
  initSetupView();
  initTrackingView();
  initTilePicker();
  initHandEndModal();
  restoreFromStorage();
  renderAll();
  window.addEventListener("i18n:changed", renderAll);
}

async function loadTileMetadata() {
  const resp = await fetch(`${API_BASE}/tiles`);
  if (!resp.ok) throw new Error(`/api/tiles returned ${resp.status}`);
  const data = await resp.json();
  tileMetadata = new Array(34);
  for (const t of data) tileMetadata[t.tile_id] = t;
}

async function probeAssets() {
  try {
    const resp = await fetch(`${TILE_IMG_BASE}/Man1.svg`, { method: "HEAD" });
    assetsAvailable = resp.ok;
  } catch (_e) {
    assetsAvailable = false;
  }
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

function persistGame() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        phase: state.game.phase,
        config: state.game.config,
        snapshot: state.game.snapshot,
        ui: state.game.ui,
      })
    );
  } catch (_e) {
    /* ignore */
  }
}

function restoreFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    if (data.config) Object.assign(state.game.config, data.config);
    if (data.snapshot && data.phase === "tracking") {
      state.game.snapshot = data.snapshot;
      state.game.phase = "tracking";
      if (data.ui) Object.assign(state.game.ui, data.ui);
    }
  } catch (_e) {
    /* ignore */
  }
}

// ---------------------------------------------------------------------------
// Language toggle
// ---------------------------------------------------------------------------

function bindLanguageToggle() {
  document.getElementById("langToggle").addEventListener("click", () => {
    const next = getLanguage() === "en" ? "zh" : "en";
    setLanguage(next);
  });
}

// ---------------------------------------------------------------------------
// Tabs / view routing
// ---------------------------------------------------------------------------

function bindTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view;
      state.view = view;
      document.querySelectorAll(".tab").forEach((t) =>
        t.classList.toggle("is-active", t.dataset.view === view)
      );
      document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
      document.getElementById(view === "quick" ? "viewQuick" : "viewGame").classList.add("is-active");
      renderAll();
    });
  });
}

function renderAll() {
  if (state.view === "quick") renderQuickView();
  if (state.view === "game") renderGameView();
}

// ---------------------------------------------------------------------------
// Tile helpers
// ---------------------------------------------------------------------------

function zeros(n) { return new Array(n).fill(0); }

function codeToId(code) {
  const n = parseInt(code[0], 10);
  const s = code[1];
  if (s === "m") return n - 1;
  if (s === "p") return 9 + n - 1;
  if (s === "s") return 18 + n - 1;
  if (s === "z") return 27 + n - 1;
  throw new Error(`bad code: ${code}`);
}

function buildTile(tileId, sizeClass = "") {
  const div = document.createElement("div");
  div.className = "tile";
  if (sizeClass) div.classList.add(sizeClass);
  // Face-down placeholder (opponent ankan with unknown tiles).
  if (tileId == null || tileId < 0 || (tileId >= 34 && !isRedFive(tileId))) {
    div.classList.add("tile-back");
    div.title = t("unknown_tile");
    return div;
  }
  // Red five: ALWAYS render the regular 5 image and add CSS overlay + badge.
  // No separate red-five SVG asset is required.
  const isRed = isRedFive(tileId);
  const baseId = isRed ? RED_TO_NORMAL[tileId] : tileId;
  const meta = tileMetadata[baseId];
  if (baseId >= 27) div.classList.add("honor");
  if (assetsAvailable) {
    const img = document.createElement("img");
    img.src = `${TILE_IMG_BASE}/${meta.image}`;
    img.alt = meta.long_name;
    div.appendChild(img);
  } else {
    div.classList.add("tile-fallback");
    div.textContent = meta.short_name;
  }
  if (isRed) {
    div.classList.add("is-red-five");
    const badge = document.createElement("span");
    badge.className = "tile-aka-badge";
    badge.textContent = "赤";
    div.appendChild(badge);
    div.title = `${meta.long_name} (赤 / aka)`;
  } else {
    div.title = meta.long_name;
  }
  div.dataset.tileId = String(tileId);
  return div;
}

function buildSelectorInto(rootEl, onPick, opts = {}) {
  rootEl.innerHTML = "";
  for (const row of SUIT_ROWS) {
    const div = document.createElement("div");
    div.className = "suit-row";
    const label = document.createElement("span");
    label.className = "suit-label";
    label.textContent = row.label;
    div.appendChild(label);
    for (let n = 1; n <= row.count; n++) {
      const tileId = codeToId(`${n}${row.suit}`);
      const tile = buildTile(tileId);
      const remaining = opts.remainingFor ? opts.remainingFor(tileId) : 4;
      if (remaining <= 0) {
        tile.classList.add("disabled");
      } else {
        tile.addEventListener("click", () => onPick(tileId));
      }
      if (opts.showRemaining && remaining < 4 && remaining > 0) {
        const chip = document.createElement("span");
        chip.className = "tile-remaining";
        chip.textContent = String(remaining);
        tile.appendChild(chip);
      }
      div.appendChild(tile);
    }
    // Red-five button at the end of m / p / s rows. We query the ext id
    // (34/35/36) so the caller's `remainingFor` can apply the
    // "max-1-red, max-3-normal, combined-≤-4" rule.
    if (!opts.hideRedFive && row.suit !== "z") {
      const redId = { m: RED_5M, p: RED_5P, s: RED_5S }[row.suit];
      const tile = buildTile(redId);
      const remaining = opts.remainingFor ? opts.remainingFor(redId) : 1;
      if (remaining <= 0) {
        tile.classList.add("disabled");
      } else {
        tile.addEventListener("click", () => onPick(redId));
      }
      div.appendChild(tile);
    }
    rootEl.appendChild(div);
  }
}

function shantenLabel(s) {
  if (s < 0) return t("shanten_winning");
  if (s === 0) return t("shanten_tenpai");
  return t("shanten_n", { n: s });
}
function shantenClass(s) {
  if (s < 0) return "shanten-neg";
  if (s === 0) return "shanten-pos-0";
  return `shanten-pos-${Math.min(8, s)}`;
}
function formLabel(form) {
  if (form === "normal")    return t("form_normal");
  if (form === "chiitoitsu") return t("form_chiitoi");
  if (form === "kokushi")    return t("form_kokushi");
  return form;
}

function seatLabel(seatIndex) {
  return t(SEAT_KEYS[seatIndex]);
}

function seatLabelShort(seatIndex) {
  return t(SEAT_KEYS_SHORT[seatIndex]);
}

function windLabel(code) {
  const map = { "1z": "east", "2z": "south", "3z": "west", "4z": "north" };
  return t(map[code] || "east");
}

// ---------------------------------------------------------------------------
// Tile picker overlay
// ---------------------------------------------------------------------------

function initTilePicker() {
  document.getElementById("tilePickerClose").addEventListener("click", closePicker);
  document.getElementById("tilePicker").addEventListener("click", (e) => {
    if (e.target.id === "tilePicker") closePicker();
  });
}

function openPicker(titleKey, onPick, opts = {}) {
  document.getElementById("tilePickerTitle").textContent = t(titleKey);
  pickerCallback = onPick;
  buildSelectorInto(
    document.getElementById("tilePickerSelector"),
    (tileId) => {
      const cb = pickerCallback;
      pickerCallback = null;
      closePicker();
      cb(tileId);
    },
    opts
  );
  document.getElementById("tilePicker").hidden = false;
}

function closePicker() {
  document.getElementById("tilePicker").hidden = true;
  pickerCallback = null;
}

// ---------------------------------------------------------------------------
// QUICK VIEW
// ---------------------------------------------------------------------------

function initQuickView() {
  document.getElementById("quickAnalyzeBtn").addEventListener("click", quickAnalyze);
  document.getElementById("quickClearBtn").addEventListener("click", () => {
    state.quick.hand = zeros(34);
    document.getElementById("quickResult").innerHTML = "";
    setStatus("quickStatus", "");
    renderQuickView();
  });
}

function renderQuickView() {
  renderQuickSelector();
  renderQuickHand();
}

function renderQuickSelector() {
  buildSelectorInto(
    document.getElementById("quickTileSelector"),
    (tileId) => {
      const total = state.quick.hand.reduce((a, b) => a + b, 0);
      if (total >= 14) { setStatus("quickStatus", t("hand_too_full"), "error"); return; }
      if (state.quick.hand[tileId] >= 4) { setStatus("quickStatus", t("too_many_copies"), "error"); return; }
      state.quick.hand[tileId]++;
      setStatus("quickStatus", "");
      renderQuickView();
    },
    { remainingFor: (tid) => 4 - state.quick.hand[tid], hideRedFive: true }
  );
}

function renderQuickHand() {
  const root = document.getElementById("quickHandTiles");
  root.innerHTML = "";
  const sorted = sortedHandIds(state.quick.hand);
  if (sorted.length === 0) {
    const empty = document.createElement("p");
    empty.className = "hand-empty";
    empty.textContent = t("hand_empty_quick");
    root.appendChild(empty);
  } else {
    for (const tid of sorted) {
      const tile = buildTile(tid);
      tile.addEventListener("click", () => { state.quick.hand[tid]--; renderQuickView(); });
      root.appendChild(tile);
    }
  }
  const total = sorted.length;
  const expected = total === 14 ? 14 : 13;
  document.getElementById("quickHandSize").textContent = `${total} / ${expected}`;
  document.getElementById("quickAnalyzeBtn").disabled = !(total === 13 || total === 14);
}

async function quickAnalyze() {
  const total = state.quick.hand.reduce((a, b) => a + b, 0);
  if (total !== 13 && total !== 14) {
    setStatus("quickStatus", t("hand_size_error", { n: total }), "error");
    return;
  }
  setStatus("quickStatus", t("analyze_running"));
  try {
    const res = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hand: idsFromCounts(state.quick.hand) }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    setStatus("quickStatus", "");
    renderAnalysis(document.getElementById("quickResult"), data, { withDefense: false });
  } catch (err) {
    setStatus("quickStatus", t("analyze_failed", { msg: err.message }), "error");
  }
}

// ---------------------------------------------------------------------------
// SETUP VIEW
// ---------------------------------------------------------------------------

function initSetupView() {
  // Button groups (click = pick). dealerSeat is no longer a user-editable
  // field; we derive it from seatWind whenever needed.
  document.querySelectorAll(".btn-group[data-group]").forEach((group) => {
    group.addEventListener("click", (e) => {
      const btn = e.target.closest(".btn-opt");
      if (!btn) return;
      const field = group.dataset.group;
      state.game.config[field] = btn.dataset.value;
      renderSetup();
    });
  });

  // Counter +/-
  document.querySelectorAll("[data-counter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const field = btn.dataset.counter;
      const delta = parseInt(btn.dataset.delta, 10);
      state.game.config[field] = Math.max(0, (state.game.config[field] || 0) + delta);
      renderSetup();
    });
  });

  document.getElementById("setupAddDoraBtn").addEventListener("click", () => {
    openPicker("pick_tile", (tileId) => {
      state.game.config.doraIndicators.push(tileId);
      renderSetup();
    });
  });

  document.getElementById("setupClearHandBtn").addEventListener("click", () => {
    if (state.game.config.startingHand.length === 0) return;
    if (!confirm(t("setup_clear_hand_confirm"))) return;
    state.game.config.startingHand = [];
    renderSetup();
  });

  document.getElementById("setupStartBtn").addEventListener("click", startGameFromSetup);
}

function dealerSeatFromSeatWind(seatWind) {
  // If user is East -> user is dealer (seat 0).
  // If user is South -> dealer is to user's left (kamicha = seat 3).
  // If user is West -> dealer is across (toimen = seat 2).
  // If user is North -> dealer is to user's right (shimocha = seat 1).
  return { "1z": 0, "2z": 3, "3z": 2, "4z": 1 }[seatWind] ?? 0;
}

function renderGameView() {
  if (state.game.phase === "setup") {
    document.getElementById("setupView").hidden = false;
    document.getElementById("trackingView").hidden = true;
    renderSetup();
  } else {
    document.getElementById("setupView").hidden = true;
    document.getElementById("trackingView").hidden = false;
    renderTracking();
  }
}

function renderSetup() {
  const cfg = state.game.config;
  // Active classes for button groups.
  document.querySelectorAll(".btn-group[data-group]").forEach((group) => {
    const field = group.dataset.group;
    const current = String(cfg[field]);
    group.querySelectorAll(".btn-opt").forEach((b) =>
      b.classList.toggle("is-active", b.dataset.value === current)
    );
  });
  document.getElementById("setupHonbaValue").textContent = cfg.honba;
  document.getElementById("setupRiichiSticksValue").textContent = cfg.riichiSticks;
  // Dealer is derived from seat wind: East seat is always dealer.
  const dealerSeat = dealerSeatFromSeatWind(cfg.seatWind);
  const dealerSeatLabel = dealerSeat === 0 ? t("you") : t(SEAT_KEYS[dealerSeat]);
  document.getElementById("setupDealerInferred").textContent =
    t("dealer_inferred", { player: dealerSeatLabel });

  // Dora indicators row.
  const doraEl = document.getElementById("setupDoraTiles");
  doraEl.innerHTML = "";
  if (cfg.doraIndicators.length === 0) {
    const empty = document.createElement("p");
    empty.className = "hand-empty";
    empty.textContent = t("no_indicators");
    doraEl.appendChild(empty);
  } else {
    cfg.doraIndicators.forEach((tid, i) => {
      const tile = buildTile(tid, "small");
      tile.addEventListener("click", () => {
        cfg.doraIndicators.splice(i, 1);
        renderSetup();
      });
      doraEl.appendChild(tile);
    });
  }

  // Starting hand display.
  const handEl = document.getElementById("setupHandTiles");
  handEl.innerHTML = "";
  if (cfg.startingHand.length === 0) {
    const empty = document.createElement("p");
    empty.className = "hand-empty";
    empty.textContent = t("starting_hand_hint");
    handEl.appendChild(empty);
  } else {
    [...cfg.startingHand].sort((a, b) => a - b).forEach((tid) => {
      const tile = buildTile(tid);
      tile.addEventListener("click", () => {
        const idx = cfg.startingHand.indexOf(tid);
        if (idx >= 0) cfg.startingHand.splice(idx, 1);
        renderSetup();
      });
      handEl.appendChild(tile);
    });
  }
  document.getElementById("setupHandSize").textContent = `${cfg.startingHand.length} / 13`;

  // Selector for adding tiles. Aka-aware limits keep each suit at a real
  // deck of 3 normal 5s + 1 red 5 (combined ≤ 4) and every other tile at 4.
  buildSelectorInto(
    document.getElementById("setupHandSelector"),
    (tileId) => {
      if (cfg.startingHand.length >= 13) {
        setStatus("setupStatus", t("hand_too_full"), "error");
        return;
      }
      const remaining = akaAwareRemaining(cfg.startingHand, tileId);
      if (remaining <= 0) {
        const msg = isRedFive(tileId)
          ? t("only_one_red_per_suit")
          : NORMAL_TO_RED[tileId] !== undefined
          ? t("normal_five_max_3")
          : t("too_many_copies");
        setStatus("setupStatus", msg, "error");
        return;
      }
      cfg.startingHand.push(tileId);
      setStatus("setupStatus", "");
      renderSetup();
    },
    { remainingFor: (tid) => akaAwareRemaining(cfg.startingHand, tid) }
  );

  const handSize = cfg.startingHand.length;
  document.getElementById("setupStartBtn").disabled = handSize !== 13;
  if (handSize !== 13) {
    setStatus("setupStatus", t("pick_more_tiles", { count: 13 - handSize }));
  } else {
    setStatus("setupStatus", t("ready_to_start"), "success");
  }
}

function startGameFromSetup() {
  const cfg = state.game.config;
  state.game.snapshot = freshSnapshot(cfg);
  state.game.history = [];
  state.game.ui = {
    currentTurnSeat: dealerSeatFromSeatWind(cfg.seatWind),
    lastDiscard: null,
    pendingCall: null,
    lastAnalysis: null,
    callAnalysis: null,
    message: "",
  };
  state.game.phase = "tracking";
  persistGame();
  document.getElementById("trackingResult").innerHTML = "";
  setStatus("trackingStatus", "");
  renderGameView();
}

function freshSnapshot(cfg) {
  return {
    round_wind: cfg.roundWind,
    seat_wind: cfg.seatWind,
    honba: cfg.honba,
    riichi_sticks: cfg.riichiSticks,
    dora_indicators: cfg.doraIndicators.slice(),
    turn_number: 0,
    hand: cfg.startingHand.slice(),
    drawn_tile: null,
    user: { discards: [], melds: [], riichi: false, riichi_discard_index: null },
    opponents: [
      { discards: [], melds: [], riichi: false, riichi_discard_index: null },
      { discards: [], melds: [], riichi: false, riichi_discard_index: null },
      { discards: [], melds: [], riichi: false, riichi_discard_index: null },
    ],
  };
}

// ---------------------------------------------------------------------------
// TRACKING VIEW — turn-driven workflow
// ---------------------------------------------------------------------------

function initTrackingView() {
  document.getElementById("undoBtn").addEventListener("click", undoLastAction);
  document.getElementById("resetBtn").addEventListener("click", resetTracking);
  document.getElementById("newHandBtn").addEventListener("click", () => {
    if (!confirm(t("new_setup_confirm"))) return;
    state.game.phase = "setup";
    state.game.snapshot = null;
    state.game.history = [];
    persistGame();
    renderGameView();
  });
  document.getElementById("addDoraBtn").addEventListener("click", () => {
    openPicker("pick_dora_title", (tileId) => {
      pushHistory();
      state.game.snapshot.dora_indicators.push(tileId);
      persistGame();
      renderTracking();
    });
  });
  document.getElementById("trackingAnalyzeBtn").addEventListener("click", trackingAnalyze);
  document.getElementById("advanceTurnBtn").addEventListener("click", () => {
    pushHistory();
    advanceTurn();
    state.game.ui.lastDiscard = null;
    closeCallBar();
    persistGame();
    renderTracking();
  });

  document.querySelectorAll("[data-riichi-seat]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const seat = parseInt(cb.dataset.riichiSeat, 10);
      toggleOpponentRiichi(seat, cb.checked);
    });
  });
  document.getElementById("userRiichiToggle").addEventListener("change", (e) => {
    pushHistory();
    state.game.snapshot.user.riichi = e.target.checked;
    if (e.target.checked) {
      state.game.snapshot.user.riichi_discard_index = state.game.snapshot.user.discards.length;
    } else {
      state.game.snapshot.user.riichi_discard_index = null;
    }
    persistGame();
    renderTracking();
  });

  // Per-player Ron/Tsumo.
  document.querySelectorAll("[data-end-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.endAction;
      const seat = parseInt(btn.dataset.endSeat, 10);
      handleEndOfHand(action, seat);
    });
  });

  // Call action bar (legacy click flow — still used for Pass / Ron).
  document.querySelectorAll(".call-btn[data-call]").forEach((btn) => {
    btn.addEventListener("click", () => handleCallButton(btn.dataset.call));
  });
  document.getElementById("oppCalledBtn").addEventListener("click", openOpponentCallFlow);

  // Drag-and-drop: bind drop handlers on every call zone.
  document.querySelectorAll(".call-zone").forEach((zone) => {
    zone.addEventListener("dragover", onCallZoneDragOver);
    zone.addEventListener("dragleave", onCallZoneDragLeave);
    zone.addEventListener("drop", onCallZoneDrop);
  });

  // Ankan buttons (one per seat: 0=user, 1=shimocha, 2=toimen, 3=kamicha).
  document.querySelectorAll("[data-ankan-seat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const seat = parseInt(btn.dataset.ankanSeat, 10);
      if (seat === 0) handleUserAnkan();
      else handleOpponentAnkan(seat);
    });
  });

  // Chi popup
  document.getElementById("chiShapeClose").addEventListener("click", closeChiShapeModal);
  document.getElementById("chiShapeModal").addEventListener("click", (e) => {
    if (e.target.id === "chiShapeModal") closeChiShapeModal();
  });
}

function pushHistory() {
  state.game.history.push({
    snapshot: JSON.parse(JSON.stringify(state.game.snapshot)),
    ui: JSON.parse(JSON.stringify(state.game.ui)),
  });
  if (state.game.history.length > 200) state.game.history.shift();
}

function undoLastAction() {
  if (state.game.history.length === 0) return;
  const prev = state.game.history.pop();
  state.game.snapshot = prev.snapshot;
  state.game.ui = prev.ui;
  document.getElementById("trackingResult").innerHTML = "";
  setStatus("trackingStatus", t("undone_msg"), "success");
  persistGame();
  renderTracking();
}

function resetTracking() {
  if (!confirm(t("reset_confirm"))) return;
  state.game.snapshot = freshSnapshot(state.game.config);
  state.game.history = [];
  state.game.ui = {
    currentTurnSeat: dealerSeatFromSeatWind(state.game.config.seatWind),
    lastDiscard: null,
    pendingCall: null,
    lastAnalysis: null,
    callAnalysis: null,
    message: "",
  };
  document.getElementById("trackingResult").innerHTML = "";
  setStatus("trackingStatus", t("reset_msg"), "success");
  persistGame();
  renderTracking();
}

function advanceTurn() {
  state.game.ui.currentTurnSeat = (state.game.ui.currentTurnSeat + 1) % 4;
}

// --- center-selector click dispatcher --------------------------------------

function handleCenterTileClick(tileId) {
  const snap = state.game.snapshot;
  const ui = state.game.ui;
  if (!snap) return;
  const turn = ui.currentTurnSeat;

  if (turn === 0) {
    // User's turn -> draw.
    // After a chi/pon/kan call the user's hand is in the post-draw state
    // already (no real draw), and they should discard rather than draw.
    if (isUserPostDrawState(snap)) {
      setStatus("trackingStatus", t("hand_full_discard_first"), "error");
      return;
    }
    pushHistory();
    snap.hand.push(tileId);
    snap.drawn_tile = tileId;
    snap.turn_number += 1;
    ui.lastDiscard = null;
    closeCallBar();
    persistGame();
    renderTracking();
    trackingAnalyze();
    return;
  }

  // Opponent's turn -> record discard.
  pushHistory();
  const opp = snap.opponents[turn - 1];
  if (opp.riichi && opp.riichi_discard_index === null) {
    opp.riichi_discard_index = opp.discards.length;
  }
  opp.discards.push(tileId);
  ui.lastDiscard = { seat: turn, tile_id: tileId };
  showCallBar(turn, tileId);
  persistGame();
  renderTracking();
}

// --- user discard ----------------------------------------------------------

// ---- closed-hand size helpers (open-meld aware) --------------------------
//
// The user's concealed-hand length depends on how many open melds they own:
//   * between turns : 13 - 3 * meldCount  tiles closed
//   * post-draw     : 14 - 3 * meldCount  tiles closed
// Each chi/pon/kan removes 3 of the user's tiles (from concealed -> meld);
// kan replaces the rinshan draw, so the 13/14 invariant is preserved per
// number of melds. These helpers are used in place of the old `=== 13/14`
// checks that incorrectly fired errors after every chi/pon/kan.

function userMeldCount(snap) {
  return snap && snap.user && snap.user.melds ? snap.user.melds.length : 0;
}

function expectedClosedSize(snap, postDraw) {
  return (postDraw ? 14 : 13) - 3 * userMeldCount(snap);
}

function isHandValidForAnalysis(snap) {
  if (!snap) return false;
  const between = expectedClosedSize(snap, false);
  const post = expectedClosedSize(snap, true);
  return snap.hand.length === between || snap.hand.length === post;
}

function isUserPostDrawState(snap) {
  return snap && snap.hand.length === expectedClosedSize(snap, true);
}

function userDiscard(tileId) {
  const snap = state.game.snapshot;
  const ui = state.game.ui;
  if (!snap) return;
  if (!isUserPostDrawState(snap) || ui.currentTurnSeat !== 0) {
    setStatus("trackingStatus", t("turn_blocked"), "error");
    return;
  }
  const idx = snap.hand.indexOf(tileId);
  if (idx < 0) return;
  pushHistory();
  snap.hand.splice(idx, 1);
  snap.user.discards.push(tileId);
  if (snap.drawn_tile === tileId) snap.drawn_tile = null;
  if (snap.user.riichi && snap.user.riichi_discard_index === null) {
    snap.user.riichi_discard_index = snap.user.discards.length - 1;
  }
  ui.lastDiscard = { seat: 0, tile_id: tileId };
  ui.lastAnalysis = null; // discard invalidates the per-tile badges
  advanceTurn();
  showCallBar(0, tileId);
  persistGame();
  renderTracking();
}

// --- call action bar -------------------------------------------------------

function showCallBar(discarderSeat, tileId) {
  const bar = document.getElementById("callBar");
  const label = document.getElementById("callBarLabel");
  const tileShort = tileMetadata[tileId].short_name;
  const seatName = seatLabel(discarderSeat);
  label.textContent = t("after_discard", { tile: tileShort, seat: seatName });

  // Quick client-side legality check (used to auto-pass when no call is
  // possible). Uses the same strict helpers as the drop-zone disabling so
  // the call bar and the drop zones never disagree.
  const snap = state.game.snapshot;
  const chiOpts = getLegalChiOptions(snap, tileId, discarderSeat, 0);
  const userCanChi = chiOpts.length > 0;
  const userCanPon = discarderSeat !== 0 && canUserPon(snap, tileId);
  const userCanKan = discarderSeat !== 0 && canUserOpenKan(snap, tileId);
  // Ron legality requires shanten check — handled by /api/analyze-call.
  bar.querySelector('[data-call="chi"]').disabled = !userCanChi;
  bar.querySelector('[data-call="pon"]').disabled = !userCanPon;
  bar.querySelector('[data-call="kan"]').disabled = !userCanKan;
  bar.querySelector('[data-call="ron"]').disabled = discarderSeat === 0;

  // If there's no possible call AT ALL (chi/pon/kan/ron) AND the discarder
  // is an opponent, auto-pass to skip the manual click.
  // Ron is skipped because we can't be certain client-side; once the
  // backend tells us it's not legal we'll auto-advance.
  if (discarderSeat !== 0 && !userCanChi && !userCanPon && !userCanKan) {
    bar.hidden = true;
    state.game.ui.callAnalysis = null;
    // Verify with backend asynchronously: if the user could in fact RON,
    // re-open the bar; otherwise just advance the turn.
    fetchCallAnalysis(tileId, discarderSeat).then((data) => {
      if (data && data.legal_actions && data.legal_actions.includes("ron")) {
        // Ron-only opportunity: surface the bar so the user can claim it.
        state.game.ui.callAnalysis = data;
        bar.hidden = false;
        renderCallBarAnalysis(data);
      } else {
        // No legal calls for the user — auto-advance the turn for UX, but
        // keep `lastDiscard` alive so the tile in the discarder's river
        // stays draggable for opponent-to-opponent calls. The reference
        // is naturally cleared when the next discard arrives or when a
        // meld is recorded.
        if (state.game.ui.lastDiscard
            && state.game.ui.lastDiscard.seat === discarderSeat
            && state.game.ui.lastDiscard.tile_id === tileId) {
          advanceTurn();
          persistGame();
          renderTracking();
        }
      }
    });
    return;
  }

  bar.hidden = false;
  state.game.ui.callAnalysis = null;
  renderCallBarAnalysis(null);
  // Kick off async AI analysis to attach recommendation pills.
  if (discarderSeat !== 0) {
    fetchCallAnalysis(tileId, discarderSeat).then((data) => {
      // Make sure the user hasn't already pressed Pass / called something.
      if (state.game.ui.lastDiscard
          && state.game.ui.lastDiscard.seat === discarderSeat
          && state.game.ui.lastDiscard.tile_id === tileId) {
        state.game.ui.callAnalysis = data;
        renderCallBarAnalysis(data);
      }
    });
  }
}

async function fetchCallAnalysis(tileId, discarderSeat) {
  try {
    const res = await fetch(`${API_BASE}/analyze-call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state: serializeForBackend(state.game.snapshot),
        discarded_tile: tileId,
        discarder_seat: discarderSeat,
      }),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (_e) {
    return null;
  }
}

function renderCallBarAnalysis(data) {
  const bar = document.getElementById("callBar");
  const recBox = document.getElementById("callRecommendation");
  recBox.innerHTML = "";
  // Reset per-button labels.
  bar.querySelectorAll(".call-btn[data-call]").forEach((btn) => {
    btn.classList.remove("recommended", "not-recommended");
    const oldChip = btn.querySelector(".call-chip");
    if (oldChip) oldChip.remove();
  });
  if (!data) return;

  // Surface the headline recommendation.
  const headline = document.createElement("div");
  headline.className = "call-headline";
  const recAction = data.recommended_action;
  if (recAction === "ron") {
    headline.classList.add("ron");
    headline.textContent = `${t("ron_available")} — ${t("rec_recommended")}`;
  } else if (recAction === "pass") {
    headline.classList.add("pass");
    headline.textContent = t("rec_pass_default");
  } else {
    headline.classList.add("good");
    const opt = data.options.find((o) => o.action === recAction);
    headline.textContent = `${callActionLabel(recAction)} — ${t("rec_recommended")}` +
      (opt && opt.notes && opt.notes.length ? ` · ${opt.notes[0]}` : "");
  }
  recBox.appendChild(headline);

  // Annotate each call button with a small chip + class for quick scanning.
  data.options.forEach((opt) => {
    if (opt.action === "pass") return;
    const btn = bar.querySelector(`[data-call="${opt.action}"]`);
    if (!btn) return;
    if (!opt.legal) {
      btn.disabled = true;
      return;
    }
    btn.disabled = false;
    if (opt.recommended) btn.classList.add("recommended");
    else btn.classList.add("not-recommended");
    const chip = document.createElement("span");
    chip.className = "call-chip" + (opt.recommended ? " good" : " bad");
    chip.textContent = opt.recommended ? t("rec_recommended") : t("rec_not_recommended");
    btn.appendChild(chip);
  });
}

function callActionLabel(action) {
  return ({ chi: t("call_chi"), pon: t("call_pon"), kan: t("call_kan"), ron: t("call_ron") })[action] || action;
}

function closeCallBar() {
  document.getElementById("callBar").hidden = true;
  state.game.ui.callAnalysis = null;
  // Hide the opponent-call inline picker too.
  const oppPicker = document.getElementById("oppCallPicker");
  if (oppPicker) oppPicker.hidden = true;
}

function hasChiCandidates(tileId) {
  if (tileId >= 27) return false;
  const counts = countOccurrences(state.game.snapshot.hand);
  const suitBase = Math.floor(tileId / 9) * 9;
  const n = (tileId % 9) + 1;
  // Possible chi shapes that include this tile:
  //   (n-2,n-1,n), (n-1,n,n+1), (n,n+1,n+2)
  const checks = [];
  if (n >= 3) checks.push([tileId - 2, tileId - 1]);
  if (n >= 2 && n <= 8) checks.push([tileId - 1, tileId + 1]);
  if (n <= 7) checks.push([tileId + 1, tileId + 2]);
  return checks.some(
    ([a, b]) =>
      a >= suitBase && a < suitBase + 9 &&
      b >= suitBase && b < suitBase + 9 &&
      (counts[a] || 0) >= 1 && (counts[b] || 0) >= 1
  );
}

function handleCallButton(action) {
  const ui = state.game.ui;
  const last = ui.lastDiscard;
  if (!last) return;
  if (action === "pass") {
    closeCallBar();
    if (last.seat !== 0) advanceTurn();
    persistGame();
    renderTracking();
    return;
  }
  if (action === "ron") {
    handleEndOfHand("ron", 0); // user wins by ron from the latest discard
    return;
  }
  if (last.seat === 0) {
    // User-side last discard: any direct call here is meaningless. The user
    // should use "Opponent called" → seat → type instead.
    openOpponentCallFlow();
    return;
  }
  // User is calling on the opponent's discard.
  doUserCall(action, last.seat, last.tile_id);
}

function doUserCall(callType, fromSeat, tileId) {
  const snap = state.game.snapshot;
  const counts = countOccurrences(snap.hand);
  const baseTileId = normalizeTileId(tileId);
  if (callType === "pon") {
    if ((counts[baseTileId] || 0) < 2) { setStatus("trackingStatus", t("cannot_pon"), "error"); return; }
    pushHistory();
    removeFromHand(snap, baseTileId, 2);
    snap.user.melds.push({ type: "pon", tiles: [baseTileId, baseTileId, baseTileId], called_from: fromSeat });
  } else if (callType === "kan") {
    if ((counts[baseTileId] || 0) < 3) { setStatus("trackingStatus", t("cannot_kan"), "error"); return; }
    pushHistory();
    removeFromHand(snap, baseTileId, 3);
    snap.user.melds.push({ type: "kan", tiles: [baseTileId, baseTileId, baseTileId, baseTileId], called_from: fromSeat });
  } else if (callType === "chi") {
    if (fromSeat !== 3) { setStatus("trackingStatus", t("cannot_chi"), "error"); return; }
    const shapes = chiShapesContaining(tileId);
    const valid = shapes.filter(([a, b]) => (counts[a] || 0) >= 1 && (counts[b] || 0) >= 1);
    if (valid.length === 0) { setStatus("trackingStatus", t("not_enough_tiles_for_meld"), "error"); return; }
    let chosen = valid[0];
    if (valid.length > 1) {
      // Ask user to pick which shape via simple confirm prompt with codes.
      const labels = valid.map((sh) => sh.map((id) => tileMetadata[id].short_name).join("-"));
      const idx = pickFromList(t("pick_meld_tiles"), labels);
      if (idx < 0) return;
      chosen = valid[idx];
    }
    pushHistory();
    chosen.forEach((id) => removeFromHand(snap, id, 1));
    snap.user.melds.push({ type: "chi", tiles: [...chosen, tileId].sort((a, b) => a - b), called_from: fromSeat });
  } else {
    return;
  }
  // The called tile leaves the discarder's river and joins the user's meld
  // (same fix as the drag-drop flow — otherwise it is counted twice).
  removeCalledTileFromRiver(snap, fromSeat, tileId);
  // After a call, the user must discard. Set turn to user (no draw).
  state.game.ui.currentTurnSeat = 0;
  state.game.ui.lastDiscard = null;
  closeCallBar();
  persistGame();
  renderTracking();
}

function chiShapesContaining(tileId) {
  if (tileId >= 27) return [];
  const suitBase = Math.floor(tileId / 9) * 9;
  const n = (tileId % 9) + 1;
  const out = [];
  if (n >= 3) out.push([tileId - 2, tileId - 1]);
  if (n >= 2 && n <= 8) out.push([tileId - 1, tileId + 1]);
  if (n <= 7) out.push([tileId + 1, tileId + 2]);
  return out.filter(([a, b]) =>
    a >= suitBase && a < suitBase + 9 && b >= suitBase && b < suitBase + 9
  );
}

function removeFromHand(snap, tileId, n) {
  // Tile id may be an extended red-five id; we match on the NORMALIZED id
  // so that a meld of "5m" can consume a red 5m if present. Prefer to
  // consume regular copies first (keep the red one for value).
  const baseId = normalizeTileId(tileId);
  let removed = 0;
  let akaRemoved = 0;
  // Pass 1: remove regular copies.
  for (let i = snap.hand.length - 1; i >= 0 && removed < n; i--) {
    if (snap.hand[i] === baseId) {
      snap.hand.splice(i, 1);
      removed++;
    }
  }
  // Pass 2: if still short, consume the red copy.
  if (removed < n) {
    const redId = NORMAL_TO_RED[baseId];
    for (let i = snap.hand.length - 1; i >= 0 && removed < n; i--) {
      if (snap.hand[i] === redId) {
        snap.hand.splice(i, 1);
        removed++;
        akaRemoved++;
      }
    }
  }
  if (akaRemoved > 0) {
    // Track that the just-formed meld absorbed a red 5: caller can read
    // this hint via snap.__lastAkaConsumed.
    snap.__lastAkaConsumed = (snap.__lastAkaConsumed || 0) + akaRemoved;
  }
  if ((snap.drawn_tile === baseId || snap.drawn_tile === NORMAL_TO_RED[baseId])
      && !snap.hand.includes(snap.drawn_tile)) {
    snap.drawn_tile = null;
  }
}

// Simple prompt-based "pick from list" for chi shape disambiguation.
function pickFromList(title, options) {
  const message = `${title}\n` + options.map((s, i) => `${i + 1}. ${s}`).join("\n");
  const ans = prompt(message, "1");
  const idx = parseInt(ans, 10) - 1;
  if (Number.isNaN(idx) || idx < 0 || idx >= options.length) return -1;
  return idx;
}

// --- opponent call flow ----------------------------------------------------
//
// Replaces the previous prompt()-based flow with a small inline picker
// embedded in the call bar:
//
//   Step 1: Click "Opponent called" -> show three seat buttons.
//   Step 2: Click a seat button -> show three call-type buttons.
//   Step 3: Click a call type -> the call is recorded immediately. The
//           caller becomes the current player and must discard next.
//
// For chi we additionally use the tile picker overlay to ask which run
// shape the opponent claimed (their consumed tiles are unknown to us).

function openOpponentCallFlow() {
  const last = state.game.ui.lastDiscard;
  if (!last) return;
  state.game.ui.opponentCallPick = { stage: "seat", seat: null };
  renderOpponentCallPicker();
}

function renderOpponentCallPicker() {
  const root = document.getElementById("oppCallPicker");
  if (!root) return;
  const pick = state.game.ui.opponentCallPick;
  if (!pick) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  root.hidden = false;
  root.innerHTML = "";

  if (pick.stage === "seat") {
    const label = document.createElement("span");
    label.className = "muted small";
    label.textContent = t("opp_called_pick_seat");
    root.appendChild(label);
    [1, 2, 3].forEach((seat) => {
      // Skip the discarder seat (they can't call their own discard).
      if (seat === state.game.ui.lastDiscard.seat) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "call-btn ghost";
      btn.textContent = seatLabel(seat);
      btn.addEventListener("click", () => {
        pick.seat = seat;
        pick.stage = "type";
        renderOpponentCallPicker();
      });
      root.appendChild(btn);
    });
    return;
  }

  if (pick.stage === "type") {
    const label = document.createElement("span");
    label.className = "muted small";
    label.textContent = t("opp_called_pick_type", { seat: seatLabel(pick.seat) });
    root.appendChild(label);
    const last = state.game.ui.lastDiscard;
    const isShimocha = pick.seat === ((last.seat + 1) % 4 || 4);
    const types = isShimocha ? ["chi", "pon", "kan"] : ["pon", "kan"];
    const labels = { chi: t("call_chi"), pon: t("call_pon"), kan: t("call_kan") };
    types.forEach((type) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "call-btn ghost";
      btn.textContent = labels[type];
      btn.addEventListener("click", () => recordOpponentCall(pick.seat, type));
      root.appendChild(btn);
    });
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "call-btn ghost";
    cancel.textContent = t("cancel");
    cancel.addEventListener("click", () => {
      state.game.ui.opponentCallPick = null;
      renderOpponentCallPicker();
    });
    root.appendChild(cancel);
  }
}

function recordOpponentCall(seat, type) {
  const last = state.game.ui.lastDiscard;
  if (!last) return;
  const snap = state.game.snapshot;
  const opp = snap.opponents[seat - 1];
  const base = normalizeTileId(last.tile_id);

  if (type === "chi") {
    // We don't know the opponent's consumed tiles. Use the tile picker to
    // ask for the lowest tile of their run; the meld is then
    // [low, low+1, low+2]. pushHistory()/feasibility run AFTER the pick so a
    // cancelled or impossible pick neither mutates state nor leaves a stray
    // undo entry behind.
    openPicker("chi_pick_low", (rawLow) => {
      const low = normalizeTileId(rawLow);
      const n = (low % 9) + 1;
      // The run must stay inside one numbered suit (no honors, no 8/9 lows).
      if (low >= 27 || n > 7) {
        alert(t("cannot_chi_no_tiles"));
        return;
      }
      const tiles = [low, low + 1, low + 2];
      const runPair = tiles.filter((id) => id !== base);
      if (!tiles.includes(base) || runPair.length !== 2) {
        // The picked run does not actually contain the discarded tile.
        alert(t("cannot_chi_no_tiles"));
        return;
      }
      if (!opponentCallFeasible(snap, "chi", base, runPair)) {
        alert(t("call_not_enough_copies"));
        return;
      }
      pushHistory();
      opp.melds.push({ type: "chi", tiles: tiles.slice().sort((a, b) => a - b), called_from: last.seat });
      removeCalledTileFromRiver(snap, last.seat, last.tile_id);
      finalizeOpponentCall(seat);
    });
    return;
  }

  if (type === "pon" || type === "kan") {
    if (!opponentCallFeasible(snap, type, base)) {
      alert(t("call_not_enough_copies"));
      return;
    }
    pushHistory();
    opp.melds.push({
      type,
      tiles: type === "pon"
        ? [base, base, base]
        : [base, base, base, base],
      called_from: last.seat,
    });
    removeCalledTileFromRiver(snap, last.seat, last.tile_id);
    finalizeOpponentCall(seat);
  }
}

function finalizeOpponentCall(callerSeat) {
  state.game.ui.lastDiscard = null;
  state.game.ui.opponentCallPick = null;
  state.game.ui.currentTurnSeat = callerSeat;
  closeCallBar();
  persistGame();
  renderTracking();
}

// pickFromList is no longer used by the call flow. Keep it around in case
// some other site (e.g. chi shape disambiguation when the user calls) still
// relies on it.

// ---------------------------------------------------------------------------
// Drag-and-drop call recording
// ---------------------------------------------------------------------------
//
// Source: the LATEST tile in any river is draggable (we mark it
//   `tile.is-latest-discard` and set `draggable="true"`). The dataTransfer
//   payload is `{ tileId, fromSeat }`.
// Targets: every player card has a row of three drop zones — Chi/Pon/Kan —
//   tagged with `data-call-type` and `data-caller-seat`.
//
// Dropping records the meld, removes the called tile from the discarder's
// river (because in real play the tile leaves the pile and joins the
// caller's open meld), and sets the caller as the current player.
// For Chi the user is asked to pick which run shape was claimed, since the
// other two consumed tiles can vary (e.g. for 3m: 1-2-3 / 2-3-4 / 3-4-5).

let currentDrag = null; // { tileId, fromSeat }

function setRiverTileDraggable(tileEl, tileId, fromSeat) {
  tileEl.draggable = true;
  tileEl.classList.add("is-latest-discard");
  tileEl.addEventListener("dragstart", (e) => {
    currentDrag = { tileId, fromSeat };
    try {
      e.dataTransfer.setData("text/plain", JSON.stringify(currentDrag));
    } catch (_e) { /* some browsers reject JSON; we still have currentDrag */ }
    e.dataTransfer.effectAllowed = "move";
    tileEl.classList.add("dragging");
    // Refresh legality classes so drag-target/illegal are accurate, then
    // mark only legal zones as visual targets. Illegal user-side zones
    // get the .is-illegal class and are NOT outlined as targets.
    refreshCallZoneLegality();
    document.querySelectorAll(".call-zone").forEach((z) => {
      const callerSeat = parseInt(z.dataset.callerSeat, 10);
      if (callerSeat === fromSeat) return; // can't call your own discard
      if (z.dataset.legal === "0") return; // strictly illegal for user
      z.classList.add("drag-target");
    });
  });
  tileEl.addEventListener("dragend", () => {
    tileEl.classList.remove("dragging");
    document.querySelectorAll(".call-zone").forEach((z) =>
      z.classList.remove("drag-target", "drag-over", "drag-illegal-hover")
    );
    currentDrag = null;
  });
}

// Update each call zone's `.is-illegal` / `.is-legal` classes and
// `data-legal` attribute based on the latest discard. Called on every
// renderTracking() and at dragstart so the state is always fresh.
function refreshCallZoneLegality() {
  const snap = state.game.snapshot;
  const ui = state.game.ui;
  document.querySelectorAll(".call-zone").forEach((zone) => {
    const callerSeat = parseInt(zone.dataset.callerSeat, 10);
    const callType = zone.dataset.callType;
    if (!snap) {
      zone.classList.remove("is-legal", "is-illegal");
      zone.dataset.legal = "0";
      delete zone.dataset.illegalReason;
      return;
    }
    const res = callZoneLegality(snap, ui, callerSeat, callType);
    zone.classList.toggle("is-legal", res.legal);
    zone.classList.toggle("is-illegal", !res.legal);
    zone.classList.toggle("is-soft", !!res.soft);
    zone.dataset.legal = res.legal ? "1" : "0";
    if (!res.legal) zone.dataset.illegalReason = res.reason;
    else delete zone.dataset.illegalReason;
  });
}

function onCallZoneDragOver(e) {
  if (!currentDrag) return;
  const zone = e.currentTarget;
  const callerSeat = parseInt(zone.dataset.callerSeat, 10);
  if (callerSeat === currentDrag.fromSeat) return;
  // Reject illegal user-side drops at the dragover stage so the browser
  // shows the "no-drop" cursor and never fires drop. The zone class is
  // set in refreshCallZoneLegality() during dragstart.
  if (zone.dataset.legal === "0") {
    zone.classList.add("drag-illegal-hover");
    return; // do NOT preventDefault → drop is rejected
  }
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
  zone.classList.add("drag-over");
}

function onCallZoneDragLeave(e) {
  e.currentTarget.classList.remove("drag-over", "drag-illegal-hover");
}

function onCallZoneDrop(e) {
  e.preventDefault();
  const zone = e.currentTarget;
  zone.classList.remove("drag-over", "drag-illegal-hover");
  // Defensive: the dragover guard already blocks illegal user-side drops,
  // but if any browser still fires `drop` on an illegal zone we hard-stop
  // here to guarantee the snapshot is never mutated.
  if (zone.dataset.legal === "0") {
    const reason = zone.dataset.illegalReason || "invalid_action_rejected";
    alert(t(legalityWarningKey(reason)));
    return;
  }
  let drag = currentDrag;
  if (!drag) {
    try { drag = JSON.parse(e.dataTransfer.getData("text/plain")); } catch (_e) { return; }
  }
  if (!drag) return;
  const callerSeat = parseInt(zone.dataset.callerSeat, 10);
  const callType = zone.dataset.callType;
  if (callerSeat === drag.fromSeat) return;
  applyDroppedCall(callerSeat, callType, drag);
}

function applyDroppedCall(callerSeat, callType, drag) {
  const snap = state.game.snapshot;
  if (!snap) return;
  const fromSeat = drag.fromSeat;
  const tileId = drag.tileId;
  // Strict legality check for the user (callerSeat 0). Reject before any
  // history is pushed or any meld bookkeeping runs.
  if (callerSeat === 0) {
    if (callType === "pon" && !canUserPon(snap, tileId)) {
      alert(t("cannot_pon"));
      return;
    }
    if (callType === "kan" && !canUserOpenKan(snap, tileId)) {
      alert(t("cannot_kan"));
      return;
    }
    if (callType === "chi") {
      if (!isChiSeatLegal(0, fromSeat)) {
        alert(t("warn_chi_not_kamicha"));
        return;
      }
      const opts = getLegalChiOptions(snap, tileId, fromSeat, 0);
      if (opts.length === 0) {
        alert(t("cannot_chi_no_tiles"));
        return;
      }
    }
  } else {
    // Opp callers: chi off non-kamicha is unusual but allowed via confirm
    // (manual override).
    if (callType === "chi" && !isChiSeatLegal(callerSeat, fromSeat)) {
      const ok = confirm(t("warn_chi_not_kamicha"));
      if (!ok) return;
    }
  }
  if (callType === "chi") {
    openChiShapeModal(callerSeat, fromSeat, tileId);
  } else if (callType === "pon" || callType === "kan") {
    finishMeldDrop(callerSeat, fromSeat, tileId, callType, null);
  }
}

function finishMeldDrop(callerSeat, fromSeat, tileId, callType, chiShape) {
  const snap = state.game.snapshot;
  if (!snap) return;
  const baseTileId = normalizeTileId(tileId);

  // ── Defensive strict re-check for the user. Runs BEFORE pushHistory()
  // so a rejected drop never leaves a stray history entry behind.
  if (callerSeat === 0) {
    if (callType === "pon" && !canUserPon(snap, tileId)) {
      alert(t("cannot_pon"));
      return;
    }
    if (callType === "kan" && !canUserOpenKan(snap, tileId)) {
      alert(t("cannot_kan"));
      return;
    }
    if (callType === "chi") {
      const baseChi = (chiShape || []).map(normalizeTileId);
      const legalOpts = getLegalChiOptions(snap, tileId, fromSeat, 0);
      const ok = baseChi.length === 2 &&
        legalOpts.some((o) => o[0] === baseChi[0] && o[1] === baseChi[1]);
      if (!ok) {
        alert(t("cannot_chi_no_tiles"));
        return;
      }
    }
  } else {
    // Opponent caller: their hand is hidden, but a call whose hidden tiles
    // can no longer exist on the table is physically impossible — reject it
    // before it silently corrupts the visible-tile counts.
    const runPair = callType === "chi" ? (chiShape || []).map(normalizeTileId) : null;
    if (!opponentCallFeasible(snap, callType, tileId, runPair)) {
      alert(t("call_not_enough_copies"));
      return;
    }
  }

  pushHistory();
  const player = callerSeat === 0 ? snap.user : snap.opponents[callerSeat - 1];

  // Build meld tile list in NORMALIZED ids (backend rejects ext red ids).
  let meldTiles;
  if (callType === "chi") {
    const baseChi = chiShape.map(normalizeTileId);
    meldTiles = [...baseChi, baseTileId].sort((x, y) => x - y);
  } else if (callType === "pon") {
    meldTiles = [baseTileId, baseTileId, baseTileId];
  } else if (callType === "kan") {
    meldTiles = [baseTileId, baseTileId, baseTileId, baseTileId];
  }

  // Remove the consumed tiles from the user's concealed hand. All
  // checks/removals use NORMALIZED tile ids so a red 5 in hand can satisfy
  // a pon/kan/chi requirement on a regular 5.
  if (callerSeat === 0) {
    if (callType === "chi") {
      chiShape.map(normalizeTileId).forEach((id) => removeFromHand(snap, id, 1));
    } else if (callType === "pon") {
      removeFromHand(snap, baseTileId, 2);
    } else if (callType === "kan") {
      removeFromHand(snap, baseTileId, 3);
    }
  }

  // The dropped tile counts as red if its source id is an extended red id
  // (the discarder marked the discard as the red copy).
  const droppedAka = isRedFive(tileId) ? 1 : 0;
  // Plus any red copies the user had to surrender from their concealed hand.
  const consumedAka = (snap.__lastAkaConsumed || 0);
  snap.__lastAkaConsumed = 0;
  player.melds.push({
    type: callType,
    tiles: meldTiles,
    called_from: fromSeat,
    aka_count: droppedAka + consumedAka,
  });

  // The tile leaves the discarder's river and joins the meld.
  removeCalledTileFromRiver(snap, fromSeat, tileId);

  // Caller becomes the current player and owes a discard.
  state.game.ui.currentTurnSeat = callerSeat;
  state.game.ui.lastDiscard = null;
  state.game.ui.callAnalysis = null;
  state.game.ui.opponentCallPick = null;
  closeCallBar();

  // For the user, the act of calling means they are now in the post-draw
  // state (must discard) — turn analysis runs again so badges refresh.
  persistGame();
  renderTracking();
  if (callerSeat === 0) trackingAnalyze();
}

// ---------------------------------------------------------------------------
// Chi shape modal
// ---------------------------------------------------------------------------

function chiShapesForTile(tileId) {
  if (tileId >= 27) return [];
  const suitBase = Math.floor(tileId / 9) * 9;
  const n = (tileId % 9) + 1;
  const out = [];
  if (n >= 3) out.push([tileId - 2, tileId - 1]);
  if (n >= 2 && n <= 8) out.push([tileId - 1, tileId + 1]);
  if (n <= 7) out.push([tileId + 1, tileId + 2]);
  return out.filter(([a, b]) =>
    a >= suitBase && a < suitBase + 9 && b >= suitBase && b < suitBase + 9
  );
}

function openChiShapeModal(callerSeat, fromSeat, tileId) {
  const modal = document.getElementById("chiShapeModal");
  const opts = document.getElementById("chiShapeOptions");
  const hint = document.getElementById("chiShapeHint");
  const snap = state.game.snapshot;
  // For the user we go through the strict legality helper so the modal
  // only ever shows shapes that pass the same check the drop-zone uses.
  // For opponents (manual tracking) we still show every geometric shape.
  const shapes = callerSeat === 0
    ? getLegalChiOptions(snap, tileId, fromSeat, 0)
    : chiShapesForTile(normalizeTileId(tileId));
  if (shapes.length === 0) {
    alert(t("cannot_chi_no_tiles"));
    return;
  }
  hint.textContent = t("chi_pick_shape_hint", { tile: tileMetadata[tileId].short_name });
  opts.innerHTML = "";
  shapes.forEach(([a, b]) => {
    const opt = document.createElement("div");
    opt.className = "chi-shape-option";
    const tilesEl = document.createElement("div");
    tilesEl.className = "chi-shape-tiles";
    [a, tileId, b].sort((x, y) => x - y).forEach((id) => {
      const t = buildTile(id);
      if (id === tileId) t.classList.add("chi-shape-claimed");
      tilesEl.appendChild(t);
    });
    opt.appendChild(tilesEl);
    const label = document.createElement("span");
    label.className = "chi-shape-label";
    label.textContent = [a, tileId, b].sort((x, y) => x - y)
      .map((id) => tileMetadata[id].short_name).join(" - ");
    opt.appendChild(label);
    opt.addEventListener("click", () => {
      closeChiShapeModal();
      finishMeldDrop(callerSeat, fromSeat, tileId, "chi", [a, b]);
    });
    opts.appendChild(opt);
  });
  modal.hidden = false;
}

function closeChiShapeModal() {
  document.getElementById("chiShapeModal").hidden = true;
}

// ---------------------------------------------------------------------------
// Ankan (concealed kan)
// ---------------------------------------------------------------------------
//
// User Ankan: requires 4 of one tile in the concealed hand. We auto-detect
// candidate tiles; if there are several we ask the user which to declare.
// Opponent Ankan: we don't know which tile — accept "unknown" and store
// the meld with placeholder tile id 0 (rendered face-down). For known
// tiles the user picks via the regular tile picker.

function userAnkanCandidates() {
  const snap = state.game.snapshot;
  if (!snap) return [];
  const counts = countOccurrences(snap.hand);
  const out = [];
  for (let tid = 0; tid < 34; tid++) {
    if ((counts[tid] || 0) >= 4) out.push(tid);
  }
  return out;
}

function handleUserAnkan() {
  const cands = userAnkanCandidates();
  if (cands.length === 0) {
    alert(t("ankan_no_candidates"));
    return;
  }
  const apply = (tid) => {
    pushHistory();
    const snap = state.game.snapshot;
    removeFromHand(snap, tid, 4);
    snap.user.melds.push({ type: "ankan", tiles: [tid, tid, tid, tid], called_from: null });
    // Ankan keeps the user as the current player; they must rinshan-draw next.
    state.game.ui.currentTurnSeat = 0;
    state.game.ui.lastDiscard = null;
    closeCallBar();
    persistGame();
    renderTracking();
    if (confirm(t("ankan_kan_dora_prompt"))) {
      openPicker("pick_dora_title", (doraTid) => {
        pushHistory();
        snap.dora_indicators.push(doraTid);
        persistGame();
        renderTracking();
      });
    }
  };
  if (cands.length === 1) {
    apply(cands[0]);
  } else {
    openPicker("ankan_pick_tile", apply, {
      remainingFor: (tid) => (cands.includes(tid) ? 1 : 0),
    });
  }
}

function handleOpponentAnkan(seat) {
  const snap = state.game.snapshot;
  if (!snap) return;
  // Ask the user whether they know which tile it is. If unknown, record a
  // placeholder ankan with face-down tiles (tile id null sentinel).
  const known = confirm(t("opp_ankan_known_prompt"));
  const apply = (tid) => {
    pushHistory();
    const opp = snap.opponents[seat - 1];
    opp.melds.push({
      type: "ankan",
      tiles: tid == null ? [null, null, null, null] : [tid, tid, tid, tid],
      called_from: null,
    });
    state.game.ui.currentTurnSeat = seat;
    state.game.ui.lastDiscard = null;
    closeCallBar();
    persistGame();
    renderTracking();
    if (confirm(t("ankan_kan_dora_prompt"))) {
      openPicker("pick_dora_title", (doraTid) => {
        pushHistory();
        snap.dora_indicators.push(doraTid);
        persistGame();
        renderTracking();
      });
    }
  };
  if (known) {
    openPicker("ankan_pick_tile", apply);
  } else {
    apply(null);
  }
}

// --- riichi toggles --------------------------------------------------------

function toggleOpponentRiichi(seat, on) {
  const opp = state.game.snapshot.opponents[seat - 1];
  pushHistory();
  opp.riichi = on;
  if (on) {
    opp.riichi_discard_index = opp.discards.length;
  } else {
    opp.riichi_discard_index = null;
  }
  persistGame();
  renderTracking();
}

// --- end of hand -----------------------------------------------------------

function handleEndOfHand(action, seat) {
  let winner = seat === 0 ? t("win_player_user") : t("win_player_opp", { seat: seatLabel(seat) });
  let summary;
  if (action === "tsumo") {
    summary = t("win_by_tsumo", { player: winner });
  } else if (action === "ron") {
    if (!state.game.ui.lastDiscard) {
      alert(t("no_last_discard"));
      return;
    }
    summary = t("win_by_ron", { player: winner });
  }
  document.getElementById("handEndSummary").textContent = summary;
  document.getElementById("handEndModal").hidden = false;
}

function initHandEndModal() {
  document.getElementById("handEndClose").addEventListener("click", () => {
    document.getElementById("handEndModal").hidden = true;
  });
  document.getElementById("handEndModal").addEventListener("click", (e) => {
    if (e.target.id === "handEndModal") document.getElementById("handEndModal").hidden = true;
  });
  document.getElementById("handEndNext").addEventListener("click", () => {
    document.getElementById("handEndModal").hidden = true;
    // Reset the tracking session but keep the setup config.
    state.game.snapshot = freshSnapshot(state.game.config);
    state.game.history = [];
    state.game.ui = {
      currentTurnSeat: dealerSeatFromSeatWind(state.game.config.seatWind),
      lastDiscard: null, pendingCall: null, lastAnalysis: null, callAnalysis: null, message: "",
    };
    persistGame();
    renderTracking();
  });
  document.getElementById("handEndReset").addEventListener("click", () => {
    document.getElementById("handEndModal").hidden = true;
    resetTracking();
  });
  document.getElementById("handEndSetup").addEventListener("click", () => {
    document.getElementById("handEndModal").hidden = true;
    state.game.phase = "setup";
    state.game.snapshot = null;
    state.game.history = [];
    persistGame();
    renderGameView();
  });
}

// --- main render -----------------------------------------------------------

// ---------- dora helpers ---------------------------------------------------
//
// The indicator -> dora mapping cycles within each suit:
//   1m -> 2m -> ... -> 9m -> 1m, 1p -> 2p -> ..., winds E->S->W->N->E,
//   dragons Haku -> Hatsu -> Chun -> Haku.
// Red five identity is independent: a red 5m is *also* dora when 4m is the
// indicator, doubling its value.

function doraTileForIndicator(indicatorIdRaw) {
  const id = normalizeTileId(indicatorIdRaw);
  if (id < 27) {
    const base = Math.floor(id / 9) * 9;
    const n = id - base;
    return base + ((n + 1) % 9);
  }
  if (id < 31) return 27 + (((id - 27) + 1) % 4);
  return 31 + (((id - 31) + 1) % 3);
}

function getDoraTiles(indicators) {
  return (indicators || []).map(doraTileForIndicator);
}

function getDoraCount(tileId, indicators) {
  const norm = normalizeTileId(tileId);
  return (indicators || []).reduce(
    (acc, ind) => acc + (doraTileForIndicator(ind) === norm ? 1 : 0),
    0
  );
}

function isDora(tileId, indicators) {
  return getDoraCount(tileId, indicators) > 0;
}

// Apply dora / red-dora highlight classes to a tile element.
function applyDoraHighlight(tileEl, tileId, indicators) {
  const doraN = getDoraCount(tileId, indicators);
  const isRed = isRedFive(tileId);
  if (doraN > 0) tileEl.classList.add("is-dora");
  if (doraN > 1) tileEl.classList.add("is-dora-multi");
  if (isRed) tileEl.classList.add("is-red-dora");
  if (isRed && doraN > 0) tileEl.classList.add("is-double-dora");
  if (doraN > 1 || (isRed && doraN > 0)) {
    const badge = document.createElement("span");
    badge.className = "tile-dora-badge";
    const totalDora = doraN + (isRed ? 1 : 0);
    badge.textContent = `${t("dora_short")}×${totalDora}`;
    tileEl.appendChild(badge);
  }
}

// ---------- seat wind helpers (Step 8 — auto wind positioning) -------------
//
// Around the table play goes counter-clockwise: E -> S -> W -> N -> E.
// In our seat ordering 0=user, 1=shimocha (next), 2=toimen, 3=kamicha (prev).
// Counter-clockwise from user: user -> shimocha -> toimen -> kamicha -> user.
// So seat winds advance from the user's seat wind by +1 each step.

const WIND_ORDER = ["1z", "2z", "3z", "4z"];
function windFor(seatIndex, userSeatWind) {
  const i = WIND_ORDER.indexOf(userSeatWind);
  if (i < 0) return "1z";
  return WIND_ORDER[(i + seatIndex) % 4];
}

function renderSeatWindBadges(snap) {
  document.querySelectorAll("[data-wind-for-seat]").forEach((el) => {
    const seat = parseInt(el.dataset.windForSeat, 10);
    const code = windFor(seat, snap.seat_wind);
    el.textContent = windLabel(code);
  });
  // Highlight whichever opp/user card currently holds the East wind (= dealer).
  document.querySelectorAll(".opp-card").forEach((card) => {
    const seat = parseInt(card.dataset.seat, 10);
    const isDealer = windFor(seat, snap.seat_wind) === "1z";
    card.classList.toggle("is-dealer", isDealer);
  });
  const userArea = document.querySelector(".user-area");
  if (userArea) userArea.classList.toggle("is-dealer", snap.seat_wind === "1z");
}

// Render the per-player han chip from the latest analysis result. The chip
// is mounted on a dynamic span inside each player's `.opp-head` (or the
// user's `.user-area-head`); we (re-)create it on every render so it
// reflects the freshest data.
function renderHanChips(snap) {
  const han = state.game.ui.lastAnalysis && state.game.ui.lastAnalysis.han_estimates;
  const set = (selector, info, isUser) => {
    const host = document.querySelector(selector);
    if (!host) return;
    let chip = host.querySelector(".han-chip");
    if (!chip) {
      chip = document.createElement("span");
      chip.className = "han-chip";
      host.appendChild(chip);
    }
    if (!info) {
      chip.style.display = "none";
      return;
    }
    chip.style.display = "";
    const yaku = info.yaku_han ?? 0;
    const dora = info.dora_han ?? 0;
    const total = info.han ?? (yaku + dora);
    // Show "Yaku N · Dora M" so dora and yaku are visually separated.
    // Add "no yaku yet" warning when dora > 0 but yaku == 0.
    const parts = [
      `${t(isUser ? "han_user_label" : "han_opp_label")}: ${total}${info.estimate ? "+" : ""}`,
    ];
    if (yaku || dora) {
      parts.push(`${t("yaku_han_short")} ${yaku} · ${t("dora_han_short")} ${dora}`);
    }
    chip.innerHTML = "";
    const top = document.createElement("span");
    top.className = "han-chip-total";
    top.textContent = parts[0];
    chip.appendChild(top);
    if (parts[1]) {
      const sub = document.createElement("span");
      sub.className = "han-chip-split";
      sub.textContent = parts[1];
      chip.appendChild(sub);
    }
    if (dora > 0 && !info.has_yaku) {
      chip.classList.add("han-needs-yaku");
      chip.title = t("dora_alone_not_yaku") + " · " + (info.notes || []).join(" · ");
    } else {
      chip.classList.remove("han-needs-yaku");
      chip.title = (info.notes || []).join(" · ");
    }
    chip.classList.toggle("han-strong", total >= 4);
    chip.classList.toggle("han-medium", total >= 2 && total < 4);
  };
  if (!han) {
    set(".user-area-head", null, true);
    document.querySelectorAll('.opp-card').forEach((c) => set(`.opp-card[data-seat="${c.dataset.seat}"] .opp-head`, null, false));
    return;
  }
  const byseat = {};
  for (const h of han) byseat[h.seat] = h;
  set(".user-area-head", byseat[0], true);
  for (const seat of [1, 2, 3]) {
    set(`.opp-card[data-seat="${seat}"] .opp-head`, byseat[seat], false);
  }
}

function renderTracking() {
  if (!state.game.snapshot) {
    state.game.phase = "setup";
    renderGameView();
    return;
  }
  const snap = state.game.snapshot;
  const ui = state.game.ui;

  renderSeatWindBadges(snap);
  renderHanChips(snap);

  // Round info bar.
  document.getElementById("roundLabel").textContent =
    t("round_label", { wind: windLabel(snap.round_wind), turn: snap.turn_number || 0 });
  document.getElementById("seatLabel").textContent =
    t("seat_label", { wind: windLabel(snap.seat_wind) });
  document.getElementById("honbaLabel").textContent =
    t("honba_label", { honba: snap.honba, sticks: snap.riichi_sticks });

  // Dora row. Show indicator + the corresponding dora tile alongside.
  const doraEl = document.getElementById("doraRow");
  doraEl.innerHTML = "";
  if (snap.dora_indicators.length === 0) {
    const empty = document.createElement("span");
    empty.className = "muted small";
    empty.textContent = t("no_dora");
    doraEl.appendChild(empty);
  } else {
    snap.dora_indicators.forEach((tid) => {
      const tile = buildTile(tid, "small");
      tile.title = `${t("dora_indicator_label")}: ${tileMetadata[normalizeTileId(tid)].long_name}`;
      doraEl.appendChild(tile);
    });
  }

  // Turn indicator (post-draw-aware so chi/pon/kan states show the right hint).
  const turnEl = document.getElementById("turnIndicator");
  if (isUserPostDrawState(snap) && ui.currentTurnSeat === 0) {
    turnEl.textContent = t("turn_user_discard");
    turnEl.classList.remove("is-opp");
  } else if (ui.currentTurnSeat === 0) {
    turnEl.textContent = t("turn_user_draw");
    turnEl.classList.remove("is-opp");
  } else {
    turnEl.textContent = t("turn_opp_discard", { seat: seatLabel(ui.currentTurnSeat) });
    turnEl.classList.add("is-opp");
  }

  // Center selector — aka-aware, so the red-5 button also disables once
  // either (a) the red copy is already on the table or (b) the combined
  // 5-count for that suit hits 4.
  const visibleList = collectVisibleTileIds(snap);
  buildSelectorInto(
    document.getElementById("centerSelector"),
    handleCenterTileClick,
    {
      remainingFor: (tid) => akaAwareRemaining(visibleList, tid),
      showRemaining: true,
    }
  );

  // Each opponent.
  for (let seat = 1; seat <= 3; seat++) {
    const opp = snap.opponents[seat - 1];
    const card = document.querySelector(`.opp-card[data-seat="${seat}"]`);
    card.classList.toggle("is-riichi", !!opp.riichi);
    card.classList.toggle("is-active-turn", ui.currentTurnSeat === seat);
    document.querySelector(`[data-riichi-seat="${seat}"]`).checked = !!opp.riichi;

    const meldsEl = card.querySelector(`[data-melds-seat="${seat}"]`);
    meldsEl.innerHTML = "";
    opp.melds.forEach((meld) => {
      const grp = document.createElement("div");
      grp.className = "meld-group";
      const aka = meld.aka_count || 0;
      let akaShown = 0;
      meld.tiles.forEach((tid) => {
        // Render the meld's aka_count tiles as red 5s if their type matches.
        let renderId = tid;
        if (aka > akaShown && tid != null && NORMAL_TO_RED[tid] != null) {
          renderId = NORMAL_TO_RED[tid];
          akaShown++;
        }
        const t2 = buildTile(renderId, "tiny");
        applyDoraHighlight(t2, renderId, snap.dora_indicators);
        grp.appendChild(t2);
      });
      meldsEl.appendChild(grp);
    });

    const riverEl = card.querySelector(`[data-river-seat="${seat}"]`);
    riverEl.innerHTML = "";
    const lastIdx = opp.discards.length - 1;
    opp.discards.forEach((tid, i) => {
      const tile = buildTile(tid, "small");
      applyDoraHighlight(tile, tid, snap.dora_indicators);
      const isPostRiichi =
        opp.riichi && opp.riichi_discard_index !== null && i >= opp.riichi_discard_index;
      if (isPostRiichi) tile.style.borderColor = "#ef9a9a";
      tile.addEventListener("click", () => {
        if (!confirm(`Remove ${tileMetadata[tid].short_name} from this river?`)) return;
        pushHistory();
        opp.discards.splice(i, 1);
        if (opp.riichi_discard_index !== null && i < opp.riichi_discard_index) {
          opp.riichi_discard_index -= 1;
        }
        persistGame();
        renderTracking();
      });
      // The most recent tile in this river is draggable -> drop into a
      // call zone to record chi/pon/kan from any other player.
      if (i === lastIdx
          && ui.lastDiscard
          && ui.lastDiscard.seat === seat
          && ui.lastDiscard.tile_id === tid) {
        setRiverTileDraggable(tile, tid, seat);
      }
      riverEl.appendChild(tile);
    });
  }

  // User river.
  const userRiverEl = document.getElementById("userRiver");
  userRiverEl.innerHTML = "";
  const userLastIdx = snap.user.discards.length - 1;
  snap.user.discards.forEach((tid, i) => {
    const tile = buildTile(tid, "small");
    applyDoraHighlight(tile, tid, snap.dora_indicators);
    tile.addEventListener("click", () => {
      if (!confirm(`Remove ${tileMetadata[tid].short_name} from your river?`)) return;
      pushHistory();
      snap.user.discards.splice(i, 1);
      persistGame();
      renderTracking();
    });
    if (i === userLastIdx
        && ui.lastDiscard
        && ui.lastDiscard.seat === 0
        && ui.lastDiscard.tile_id === tid) {
      setRiverTileDraggable(tile, tid, 0);
    }
    userRiverEl.appendChild(tile);
  });

  // User melds.
  const userMeldsEl = document.getElementById("userMeldsRow");
  userMeldsEl.innerHTML = "";
  snap.user.melds.forEach((meld) => {
    const grp = document.createElement("div");
    grp.className = "meld-group";
    const aka = meld.aka_count || 0;
    let akaShown = 0;
    meld.tiles.forEach((tid) => {
      let renderId = tid;
      if (aka > akaShown && tid != null && NORMAL_TO_RED[tid] != null) {
        renderId = NORMAL_TO_RED[tid];
        akaShown++;
      }
      const t2 = buildTile(renderId, "tiny");
      applyDoraHighlight(t2, renderId, snap.dora_indicators);
      grp.appendChild(t2);
    });
    userMeldsEl.appendChild(grp);
  });

  // User hand.
  const handEl = document.getElementById("trackingHandTiles");
  handEl.innerHTML = "";
  const sortedHand = [...snap.hand].sort((a, b) => a - b);
  const rankByTileId = badgeMapFromAnalysis(ui.lastAnalysis, snap);
  const reasonByTileId = tileReasonsFromAnalysis(ui.lastAnalysis);
  sortedHand.forEach((tid) => {
    const tile = buildTile(tid);
    const baseTid = normalizeTileId(tid);
    if (snap.drawn_tile === tid || snap.drawn_tile === baseTid) tile.classList.add("drawn");
    applyDoraHighlight(tile, tid, snap.dora_indicators);
    if (isUserPostDrawState(snap) && ui.currentTurnSeat === 0) {
      tile.addEventListener("click", () => userDiscard(tid));
    } else {
      tile.style.cursor = "default";
    }
    // AI badges (looked up by normalized id).
    const info = rankByTileId.get(baseTid);
    if (info) {
      const badge = document.createElement("span");
      badge.className = "tile-rank-badge" + (info.rank === 2 ? " rank-2" : info.rank === 3 ? " rank-3" : "");
      badge.textContent = info.rank === 1 ? t("rank_best") : t("rank_n", { n: info.rank });
      tile.appendChild(badge);
      const score = document.createElement("span");
      const scoreText =
        info.danger != null
          ? t("badge_score_def", { n: info.ukeire_count, d: info.danger })
          : t("badge_score", { n: info.ukeire_count });
      score.className = "tile-score-badge";
      if (info.danger >= 60) score.classList.add("bad");
      else if (info.danger >= 35) score.classList.add("warn");
      score.textContent = scoreText;
      tile.appendChild(score);
      if (info.rank === 1) tile.classList.add("recommended");
    }
    // Per-tile reason chip from yaku layer (lower-right corner).
    const reasons = reasonByTileId.get(baseTid);
    if (reasons && reasons.length) {
      const primary = pickPrimaryReason(reasons);
      const chip = document.createElement("span");
      chip.className = `tile-reason-badge ${reasonClass(primary)}`;
      chip.textContent = t(reasonLabelKey(primary));
      tile.appendChild(chip);
    }
    handEl.appendChild(tile);
  });

  const expected = isUserPostDrawState(snap)
    ? expectedClosedSize(snap, true)
    : expectedClosedSize(snap, false);
  document.getElementById("trackingHandSize").textContent =
    `${sortedHand.length} / ${expected}`;
  document.getElementById("trackingAnalyzeBtn").disabled = !isHandValidForAnalysis(snap);
  document.getElementById("undoBtn").disabled = state.game.history.length === 0;

  // User riichi reflection.
  document.getElementById("userRiichiToggle").checked = !!snap.user.riichi;

  // Ankan buttons: enable only when applicable.
  const userAnkanBtn = document.querySelector('[data-ankan-seat="0"]');
  if (userAnkanBtn) userAnkanBtn.disabled = userAnkanCandidates().length === 0;

  // Refresh strict legality classes on every drop zone so visual state
  // matches the latest discard. (Reads `ui.lastDiscard` + `snap.hand`.)
  refreshCallZoneLegality();
}

function badgeMapFromAnalysis(analysis, snap) {
  const out = new Map();
  if (!analysis || !analysis.discards) return out;
  if (!isUserPostDrawState(snap)) return out;
  // Compare against normalized hand ids so red 5s match the backend's base ids.
  const tilesInHand = new Set(snap.hand.map(normalizeTileId));
  const ranked = analysis.discards.filter((d) => tilesInHand.has(d.tile_id));
  ranked.slice(0, 3).forEach((d, i) => {
    out.set(d.tile_id, {
      rank: i + 1,
      ukeire_count: d.ukeire_count,
      danger: d.danger ? d.danger.score : null,
      is_dora: !!d.is_dora,
    });
  });
  return out;
}

function tileReasonsFromAnalysis(analysis) {
  // analysis.tile_reasons keys are stringified tile ids (yaku module).
  const map = new Map();
  if (!analysis || !analysis.tile_reasons) return map;
  for (const [k, v] of Object.entries(analysis.tile_reasons)) {
    map.set(parseInt(k, 10), v);
  }
  return map;
}

// First non-bestKeep reason wins the chip. Order chosen for visual clarity.
const REASON_PRIORITY = [
  "yakuhai", "dora", "keep_chinitsu", "keep_honitsu",
  "keep_toitoi", "keep_kokushi", "keep_chiitoitsu", "keep_tanyao",
  "break_chinitsu", "break_honitsu", "break_tanyao",
];
function pickPrimaryReason(reasons) {
  for (const k of REASON_PRIORITY) if (reasons.includes(k)) return k;
  return reasons[0];
}
function reasonLabelKey(reason) {
  return ({
    yakuhai: "reason_yakuhai",
    dora: "reason_dora",
    keep_honitsu: "reason_keep_honitsu",
    keep_chinitsu: "reason_keep_chinitsu",
    keep_tanyao: "reason_keep_tanyao",
    keep_toitoi: "reason_keep_toitoi",
    keep_kokushi: "reason_keep_kokushi",
    keep_chiitoitsu: "reason_keep_chiitoi",
    break_tanyao: "reason_break_tanyao",
    break_honitsu: "reason_break_honitsu",
    break_chinitsu: "reason_break_chinitsu",
  })[reason] || reason;
}
function reasonClass(reason) {
  if (reason === "yakuhai") return "yakuhai";
  if (reason === "dora") return "dora";
  if (reason && reason.startsWith("keep_honitsu")) return "honitsu";
  if (reason && reason.startsWith("keep_chinitsu")) return "chinitsu";
  if (reason && reason.startsWith("keep_tanyao")) return "tanyao";
  if (reason && reason.startsWith("keep_toitoi")) return "toitoi";
  if (reason && reason.startsWith("break_")) return "warn";
  return "";
}

function computeVisibleCounts(snap) {
  const counts = zeros(34);
  // Normalise red ext ids (34/35/36) so they count toward the same base
  // 5m / 5p / 5s slot as their regular siblings.
  // Face-down opponent ankan stores null tile ids — skip them so we don't
  // corrupt the count vector (normalizeTileId(null) is not a valid slot).
  const tally = (tid) => {
    if (tid == null) return;
    const n = normalizeTileId(tid);
    if (n >= 0 && n < 34) counts[n]++;
  };
  snap.hand.forEach(tally);
  snap.dora_indicators.forEach(tally);
  [snap.user, ...snap.opponents].forEach((p) => {
    p.discards.forEach(tally);
    p.melds.forEach((m) => (m.tiles || []).forEach(tally));
  });
  return counts;
}

// A flat list of every visible tile id, preserving red identity (red 5s
// appear as their ext ids 34/35/36). This is what `akaAwareRemaining`
// needs to check the per-suit 3-normal + 1-red limit.
function collectVisibleTileIds(snap) {
  const out = [];
  // hand / dora indicators / discards: ext ids stay as-is.
  out.push(...(snap.hand || []));
  out.push(...(snap.dora_indicators || []));
  for (const p of [snap.user, ...snap.opponents]) {
    out.push(...(p.discards || []));
    for (const m of p.melds || []) {
      const aka = m.aka_count || 0;
      let akaInjected = 0;
      // meld.tiles always stores NORMALIZED ids; we synthesise the red ext
      // id for the first `aka` matching base tiles so the limit logic sees
      // them as red copies rather than additional normals.
      for (const tid of m.tiles || []) {
        if (tid != null && akaInjected < aka && NORMAL_TO_RED[tid] !== undefined) {
          out.push(NORMAL_TO_RED[tid]);
          akaInjected++;
        } else if (tid != null) {
          out.push(tid);
        }
      }
    }
  }
  return out;
}

// --- analyze --------------------------------------------------------------

async function trackingAnalyze() {
  const snap = state.game.snapshot;
  if (!snap) return;
  if (!isHandValidForAnalysis(snap)) {
    setStatus(
      "trackingStatus",
      t("hand_size_error_with_melds", { n: snap.hand.length, melds: userMeldCount(snap) }),
      "error"
    );
    return;
  }
  setStatus("trackingStatus", t("analyze_running"));
  try {
    const res = await fetch(`${API_BASE}/analyze-game`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(serializeForBackend(snap)),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    setStatus("trackingStatus", "");
    state.game.ui.lastAnalysis = data;
    persistGame();
    renderAnalysis(document.getElementById("trackingResult"), data, { withDefense: true });
    renderTracking(); // re-render hand with badges
  } catch (err) {
    setStatus("trackingStatus", t("analyze_failed", { msg: err.message }), "error");
  }
}

function serializeForBackend(snap) {
  // Convert ext red-five ids to base ids for the backend (which only knows
  // 0..33). For each meld we ALSO compute aka_count from any red ids in
  // its tile list, ON TOP of any aka_count the frontend already set.
  const normTileList = (list) => (list || []).map((t) => (t == null ? null : normalizeTileId(t)));
  const meldAka = (m) => {
    const explicit = typeof m.aka_count === "number" ? m.aka_count : 0;
    const fromTiles = (m.tiles || []).filter((t) => isRedFive(t)).length;
    return Math.max(explicit, fromTiles);
  };
  const cleanMeld = (m) => ({
    type: m.type,
    tiles: normTileList(m.tiles),
    called_from: m.called_from ?? null,
    aka_count: meldAka(m),
  });
  const sanitisePlayer = (p) => ({
    discards: normTileList(p.discards).filter((t) => t != null && t >= 0 && t < 34),
    melds: (p.melds || [])
      .filter((m) => Array.isArray(m.tiles) && m.tiles.every((t) => t != null))
      .map(cleanMeld),
    riichi: !!p.riichi,
    riichi_discard_index: p.riichi_discard_index ?? null,
  });
  return {
    round_wind: snap.round_wind,
    seat_wind: snap.seat_wind,
    honba: snap.honba,
    riichi_sticks: snap.riichi_sticks,
    dora_indicators: normTileList(snap.dora_indicators),
    turn_number: snap.turn_number,
    hand: normTileList(snap.hand),
    drawn_tile: snap.drawn_tile == null ? null : normalizeTileId(snap.drawn_tile),
    aka_in_hand: countAkaInList(snap.hand || []),
    user: sanitisePlayer(snap.user),
    opponents: snap.opponents.map(sanitisePlayer),
  };
}

// ---------------------------------------------------------------------------
// ANALYSIS RENDERING
// ---------------------------------------------------------------------------

function renderAnalysis(root, data, opts = {}) {
  root.innerHTML = "";

  const summary = document.createElement("div");
  summary.className = "summary";
  const tag = document.createElement("div");
  tag.className = `summary-line shanten-tag ${shantenClass(data.shanten)}`;
  tag.textContent = shantenLabel(data.shanten);
  summary.appendChild(tag);

  const detail = document.createElement("div");
  detail.className = "summary-line";
  detail.textContent = `${t("best_form")}: ${formLabel(data.shanten_breakdown.best_form)} ` +
    `(${t("shanten")}: normal ${data.shanten_breakdown.normal}, ` +
    `chiitoi ${data.shanten_breakdown.chiitoitsu}, ` +
    `kokushi ${data.shanten_breakdown.kokushi})`;
  summary.appendChild(detail);

  if (data.tile_count === 13) {
    const uke = document.createElement("div");
    uke.className = "summary-line";
    uke.textContent = t("ukeire_count", { n: data.ukeire_count, k: data.ukeire.length });
    summary.appendChild(uke);
  }
  if (data.threats && data.threats.length > 0) {
    const tline = document.createElement("div");
    tline.className = "summary-line";
    tline.textContent = `${t("threats")}: ${data.threats.map((x) => x.label).join(", ")}`;
    summary.appendChild(tline);
  }
  root.appendChild(summary);

  const expl = document.createElement("div");
  expl.className = "explanation";
  expl.textContent = data.explanation || "";
  root.appendChild(expl);

  // Yaku-direction section (Phase 2.6).
  if (data.yaku_directions && data.yaku_directions.length) {
    const head = document.createElement("h3");
    head.className = "section-title";
    head.textContent = t("yaku_directions_label");
    root.appendChild(head);
    root.appendChild(buildYakuList(data.yaku_directions));
  }
  if (data.value_hints
      && (data.value_hints.dora_in_hand
          || (data.value_hints.yakuhai_pairs && data.value_hints.yakuhai_pairs.length))) {
    const v = document.createElement("div");
    v.className = "value-hints";
    const parts = [];
    if (data.value_hints.dora_in_hand) {
      parts.push(`${t("dora_in_hand")}: ${data.value_hints.dora_in_hand}`);
    }
    if (data.value_hints.yakuhai_pairs && data.value_hints.yakuhai_pairs.length) {
      parts.push(`${t("yakuhai_pairs")}: ${data.value_hints.yakuhai_pairs.join(", ")}`);
    }
    v.textContent = parts.join(" · ");
    root.appendChild(v);
  }

  // Han breakdown for the user (Yaku han vs Dora han, with explicit
  // "dora alone is not a yaku" warning).
  if (data.han_estimates && data.han_estimates[0]) {
    const u = data.han_estimates[0];
    const yaku = u.yaku_han ?? 0;
    const dora = u.dora_han ?? 0;
    if (yaku || dora) {
      const block = document.createElement("div");
      block.className = "han-breakdown";
      const head = document.createElement("h3");
      head.className = "section-title";
      head.textContent = t("han_breakdown_title");
      block.appendChild(head);
      const row = document.createElement("div");
      row.className = "han-breakdown-row";
      const mk = (key, value, klass) => {
        const cell = document.createElement("span");
        cell.className = `han-cell ${klass}`;
        cell.textContent = `${t(key)}: ${value}`;
        return cell;
      };
      row.appendChild(mk("yaku_han_label", yaku, "han-cell-yaku"));
      row.appendChild(mk("dora_han_label", dora, "han-cell-dora"));
      row.appendChild(mk("visible_value_label", yaku + dora, "han-cell-total"));
      block.appendChild(row);
      if (dora > 0 && !u.has_yaku) {
        const warn = document.createElement("p");
        warn.className = "han-warn";
        warn.textContent = t("dora_alone_not_yaku");
        block.appendChild(warn);
      }
      root.appendChild(block);
    }
  }

  if (data.tile_count === 13 && data.ukeire.length > 0) {
    const head = document.createElement("h3");
    head.className = "section-title";
    head.textContent = t("improving_tiles");
    root.appendChild(head);
    root.appendChild(buildUkeireRow(data.ukeire));
  }

  if (data.tile_count === 14 && data.discards && data.discards.length > 0) {
    const head = document.createElement("h3");
    head.className = "section-title";
    head.textContent = opts.withDefense ? t("discard_candidates_def") : t("discard_candidates");
    root.appendChild(head);
    const list = document.createElement("div");
    list.className = "discard-list";
    data.discards.forEach((d, idx) => list.appendChild(buildDiscardItem(d, idx === 0)));
    root.appendChild(list);
  }
}

function buildDiscardItem(discard, isBest) {
  const wrap = document.createElement("div");
  wrap.className = "discard-item" + (isBest ? " best" : "");
  const tile = buildTile(discard.tile_id, "small");
  if (isBest) tile.classList.add("recommended");
  // Discarding a dora is rarely free — show a warning chip on the tile.
  if (discard.is_dora) {
    tile.classList.add("is-dora");
    const warn = document.createElement("span");
    warn.className = "tile-dora-badge";
    warn.textContent = t("dora_short");
    tile.appendChild(warn);
  }
  wrap.appendChild(tile);

  const info = document.createElement("div");
  info.className = "discard-item-info";
  const head = document.createElement("strong");
  head.textContent = `${tileMetadata[discard.tile_id].short_name}`;
  if (discard.is_dora) {
    const tag = document.createElement("span");
    tag.className = "dora-warn-pill";
    tag.textContent = t("dora_warn_pill");
    head.appendChild(tag);
  }
  info.appendChild(head);

  const stats = document.createElement("span");
  stats.textContent = `→ ${shantenLabel(discard.shanten_after)} · ` +
    `${discard.ukeire_count} ${t("ukeire")} (${discard.ukeire.length})`;
  info.appendChild(stats);

  if (discard.danger) {
    const pill = document.createElement("span");
    pill.className = "danger-pill";
    pill.dataset.label = discard.danger.label;
    pill.textContent = t("danger_pill", { n: discard.danger.score, label: discard.danger.label });
    info.appendChild(pill);
    if (discard.danger.summary) {
      const s = document.createElement("span");
      s.style.marginTop = "2px";
      s.textContent = discard.danger.summary;
      info.appendChild(s);
    }
  }
  if (discard.ukeire.length > 0) info.appendChild(buildUkeireRow(discard.ukeire, true));
  wrap.appendChild(info);
  return wrap;
}

function buildYakuList(directions) {
  const wrap = document.createElement("div");
  wrap.className = "yaku-list";
  directions.forEach((d) => {
    const row = document.createElement("div");
    row.className = "yaku-item";
    const head = document.createElement("div");
    head.className = "yaku-item-head";
    const name = document.createElement("span");
    name.textContent = getLanguage() === "zh" ? d.label_zh : d.label_en;
    head.appendChild(name);
    const conf = document.createElement("span");
    conf.className = "conf-pill" + (d.confidence >= 70 ? "" : d.confidence >= 40 ? " medium" : " weak");
    conf.textContent = `${d.confidence}/100`;
    head.appendChild(conf);
    row.appendChild(head);
    if (d.notes && d.notes.length) {
      const notes = document.createElement("div");
      notes.className = "yaku-item-notes";
      notes.textContent = d.notes.join(" · ");
      row.appendChild(notes);
    }
    wrap.appendChild(row);
  });
  return wrap;
}

function buildUkeireRow(ukeireList, compact = false) {
  const row = document.createElement("div");
  row.className = "ukeire-row";
  for (const u of ukeireList) {
    const chip = document.createElement("span");
    chip.className = "ukeire-tile";
    chip.title = `${tileMetadata[u.tile_id].long_name}: ${u.remaining}`;
    const label = document.createElement("span");
    label.textContent = tileMetadata[u.tile_id].short_name;
    chip.appendChild(label);
    const count = document.createElement("span");
    count.className = "count";
    count.textContent = `×${u.remaining}`;
    chip.appendChild(count);
    row.appendChild(chip);
  }
  if (compact) row.style.marginTop = "4px";
  return row;
}

// ---------------------------------------------------------------------------
// Misc helpers
// ---------------------------------------------------------------------------

function setStatus(elementId, text, level = "") {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = text || "";
  el.classList.remove("error", "success");
  if (level === "error") el.classList.add("error");
  if (level === "success") el.classList.add("success");
}

function sortedHandIds(counts) {
  const out = [];
  for (let tid = 0; tid < counts.length; tid++) {
    for (let i = 0; i < counts[tid]; i++) out.push(tid);
  }
  return out;
}

function idsFromCounts(counts) { return sortedHandIds(counts); }

// Counts use NORMALIZED tile ids (red 5s collapse onto regular 5s) so that
// "max 4 of each", chi/pon/kan legality, and shanten parity all work.
function countOccurrences(ids) {
  const out = {};
  for (const id of ids) {
    const n = normalizeTileId(id);
    out[n] = (out[n] || 0) + 1;
  }
  return out;
}
