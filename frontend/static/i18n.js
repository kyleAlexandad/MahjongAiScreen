// MahjongAiScreen — translation dictionary + helpers.
//
// Usage:
//   - Set HTML elements with `data-i18n="key"` to have their textContent translated.
//   - Set HTML elements with `data-i18n-title="key"` to translate their title attribute.
//   - In JS, call `t("key")` to fetch the current-language string.
//   - Call `setLanguage("en"|"zh")` to switch; `applyI18n()` re-renders all attributes.
//
// New keys belong in BOTH `en` and `zh`. Missing keys fall back to the key itself.

const I18N_STORAGE_KEY = "mahjongAiScreen.lang.v1";

const I18N = {
  en: {
    // ---- top bar / global ----
    app_title: "MahjongAiScreen",
    app_subtitle: "Riichi Mahjong AI assistant",
    tab_quick: "Quick analyze",
    tab_game: "Game tracking",
    lang_label: "中文",

    // ---- common ----
    clear: "Clear",
    analyze: "Analyze",
    analysis: "Analysis",
    analyze_running: "Analyzing…",
    analyze_failed: "Analysis failed: {msg}",
    pick_tile: "Pick a tile",
    close: "Close",
    none_paren: "(none)",
    of: "of",

    // ---- quick view ----
    your_hand: "Your hand",
    hand_empty_quick: "Click tiles below to add them to your hand.",
    hand_hint_quick:
      "A normal hand has 13 tiles (before drawing) or 14 (after drawing). Click a tile in the hand to remove it.",
    tile_selector: "Tile selector",
    hand_too_full: "Hand already has 14 tiles.",
    too_many_copies: "All 4 copies of that tile are already in your hand.",
    hand_size_error: "Hand must have 13 or 14 tiles (currently {n}).",
    hand_size_error_with_melds:
      "Closed hand must have 13/14 tiles minus 3 per open meld (currently {n} with {melds} meld(s)).",

    // ---- setup view ----
    setup_title: "Set up the hand",
    setup_hint:
      "Configure the round, your seat, the dora indicator(s) and your 13 starting tiles. All fields can be changed later.",
    round_wind: "Round wind",
    seat_wind: "Your seat wind",
    honba: "Honba",
    riichi_sticks: "Riichi sticks",
    dealer_position: "Dealer position",
    dealer_inferred_label: "Dealer",
    dealer_inferred: "{player} (East seat)",
    dora_indicators: "Dora indicators",
    add_dora: "+ Add indicator",
    starting_hand: "Starting hand",
    starting_hand_hint: "Pick 13 tiles for your starting hand.",
    start_hand: "Start hand",
    pick_more_tiles: "Pick {count} more tile(s).",
    ready_to_start: "Ready to start.",
    setup_clear_hand_confirm: "Clear all picked starting tiles?",
    no_indicators: "No indicators yet — click + Add indicator.",

    // winds + seat names
    east: "East",
    south: "South",
    west: "West",
    north: "North",
    east_dealer: "East (dealer)",
    you: "You",
    shimocha: "Right (shimocha)",
    toimen: "Across (toimen)",
    kamicha: "Left (kamicha)",
    you_short: "You",
    shimocha_short: "Right",
    toimen_short: "Across",
    kamicha_short: "Left",

    // ---- tracking view ----
    tracking_title: "Game tracking",
    round_label: "{wind} round · turn {turn}",
    seat_label: "Your seat: {wind}",
    honba_label: "Honba {honba} · sticks {sticks}",
    your_river: "Your discards",
    your_hand_label: "Your hand",
    add_dora_kan: "+ Indicator (kan)",
    no_dora: "(no dora yet)",
    undo: "Undo",
    reset_hand: "Reset hand",
    new_setup: "New setup",
    new_setup_confirm: "Discard the current tracking session and return to setup?",
    reset_confirm: "Reset back to the starting hand?",
    undone_msg: "Undone.",
    reset_msg: "Reset.",
    pick_dora_title: "Pick the new dora indicator",

    // turn prompts
    turn_user_draw: "Your turn — click the tile you drew",
    turn_user_discard: "Click a tile in your hand to discard",
    turn_opp_discard: "{seat}'s turn — click the tile they discarded",
    turn_user_call: "You called — choose tiles from your hand to confirm the meld",
    turn_blocked: "Resolve the call action above before continuing",
    advance_turn_btn: "Skip turn",

    // call bar
    after_discard: "Latest discard: {tile} from {seat}",
    call_chi: "Chi",
    call_pon: "Pon",
    call_kan: "Kan",
    call_ron: "Ron",
    call_pass: "Pass",
    riichi: "Riichi",
    opp_called_btn: "Opponent called",
    opp_called_title: "Record an opponent call",
    pick_called_tile: "Pick the tile that was called",
    pick_meld_tiles: "Click the tile that completes the meld",
    chi_pick_low: "Click the lowest tile of the run",
    pon_chosen: "Pon: 3 copies will be recorded",
    kan_chosen: "Kan: 4 copies will be recorded",
    cannot_chi: "Chi is only legal off your kamicha (left) opponent.",
    cannot_pon: "You don't have two copies of this tile.",
    cannot_kan: "You don't have three copies of this tile.",
    call_not_enough_copies:
      "Not enough copies of this tile are left for that call — too many are already visible on the table.",

    // call recommendation labels (Phase 2.5)
    rec_recommended: "Recommended",
    rec_not_recommended: "Not recommended",
    rec_pass_default: "No call recommended — Pass and keep building the hand.",
    ron_available: "Ron available",
    tsumo_available: "Tsumo available",
    call_opportunity: "Call opportunity",
    latest_discard: "Latest discard",
    current_turn: "Current turn",
    winning_hand: "Winning hand",
    open_melds_label: "Open melds",
    discard_river: "Discard river",
    unknown_tile: "Unknown tile",
    cancel: "Cancel",
    opp_called_pick_seat: "Which opponent called?",
    opp_called_pick_type: "{seat} — call type?",
    no_legal_calls_auto_passed: "No legal calls — turn auto-advanced.",

    // Drag-and-drop call recording (Phase 2.7)
    call_zone_chi: "Drop here for Chi",
    call_zone_pon: "Drop here for Pon",
    call_zone_kan: "Drop here for Kan",
    drag_discard_here: "Drag the latest discard onto a player's call zone",
    warn_chi_not_kamicha:
      "Chi is normally only legal from your kamicha (left) opponent. Record this call anyway?",
    chi_pick_shape: "Pick the Chi shape",
    chi_pick_shape_hint: "{tile} was claimed — choose which two tiles in hand complete the run.",

    // Ankan (concealed kan)
    call_ankan: "Ankan",
    ankan_no_candidates: "You don't have four of any tile in your concealed hand.",
    ankan_pick_tile: "Pick the tile to declare Ankan on",
    ankan_kan_dora_prompt: "Add a new dora indicator now (kan reveal)?",
    opp_ankan_known_prompt: "Do you know which tile this Ankan is on? OK = pick the tile, Cancel = record as unknown.",

    // Yaku-direction panel (Phase 2.6)
    yaku_directions_label: "Possible yaku directions",
    dora_in_hand: "Dora in hand",
    yakuhai_pairs: "Yakuhai pairs",

    // Per-tile reason chips on the user's hand
    reason_yakuhai: "Yakuhai",
    reason_dora: "Dora",
    reason_keep_honitsu: "Keep — Honitsu",
    reason_keep_chinitsu: "Keep — Chinitsu",
    reason_keep_tanyao: "Keep — Tanyao",
    reason_keep_toitoi: "Keep — Toitoi",
    reason_keep_kokushi: "Keep — Kokushi",
    reason_keep_chiitoi: "Keep — Chiitoi",
    reason_break_tanyao: "Breaks Tanyao",
    reason_break_honitsu: "Breaks Honitsu",
    reason_break_chinitsu: "Breaks Chinitsu",

    // Red dora / aka / dora highlight (Phase 2.9)
    dora_short: "Dora",
    dora_indicator_label: "Dora indicator",
    aka_dora_label: "Red Dora",
    dora_warn_pill: "DORA",
    only_one_red_per_suit: "Only one red five per suit allowed.",
    normal_five_max_3:
      "A real deck has only 3 normal fives per suit (the 4th copy is the red five).",
    tile_limit_reached: "Tile limit reached.",
    normal_five_label: "Normal Five",
    red_five_label: "Red Five",
    han_user_label: "Han",
    han_opp_label: "Han",  // user-side note: opponent values are estimates ('+' suffix)
    estimated_han: "Estimated han",
    visible_han: "Visible han",
    valuable_tile: "Valuable tile",
    dora_discard_warning: "Discarding a dora gives up value",
    tile_is_dora: "This tile is dora",
    tile_is_red_dora: "This tile is red dora",
    tile_is_double_dora: "This tile is BOTH red dora AND a regular dora — premium value",
    unknown_label: "Unknown",

    // ron / tsumo
    win_tsumo: "Tsumo",
    win_ron: "Ron",
    win_section_title: "End of hand",
    win_by_tsumo: "{player} won by Tsumo",
    win_by_ron: "{player} won by Ron",
    next_hand: "Next hand",
    return_setup: "Back to setup",
    win_player_user: "You",
    win_player_opp: "Opponent ({seat})",
    no_last_discard: "No discard recorded yet — Ron needs a recent discard.",

    // analysis panel
    ai_recommendation: "AI recommendation",
    best_form: "Best form",
    form_normal: "standard (4 melds + pair)",
    form_chiitoi: "chiitoitsu (7 pairs)",
    form_kokushi: "kokushi musou (13 orphans)",
    shanten: "Shanten",
    shanten_winning: "Winning hand (agari)",
    shanten_tenpai: "Tenpai",
    shanten_n: "{n}-shanten",
    ukeire: "Ukeire",
    ukeire_count: "Effective tiles to draw: {n} ({k} kinds)",
    threats: "Riichi threats",
    discard_candidates: "Discard candidates (best first)",
    discard_candidates_def: "Discard candidates (efficiency × defense)",
    improving_tiles: "Tiles that improve your shanten",
    danger_pill: "Danger {n} · {label}",
    rank_best: "Best",
    rank_n: "#{n}",
    badge_score: "{n} ukeire",
    badge_score_def: "{n} ukeire · risk {d}",

    // misc
    chi_only_kamicha: "Chi is only legal from kamicha (left).",
    not_enough_tiles_for_meld: "You don't have the required tiles in hand.",
    hand_full_discard_first: "Discard a tile before drawing again.",

    // ---- Strict legality + audit warnings (Phase 2.10) ----
    cannot_chi_no_tiles: "Chi requires two matching sequence tiles in your hand.",
    cannot_call_own_discard: "You can't call your own discard.",
    invalid_action_rejected: "Invalid action rejected.",
    not_enough_matching_tiles: "Not enough matching tiles in hand.",
    chi_left_only: "Chi is only allowed from the left (kamicha) player.",
    tile_count_exceeds_limit: "Tile count exceeds limit.",
    manual_override: "Manual override",
    tile_pool_invalid: "Tile pool inconsistent — last action was rejected.",

    // Yaku han vs Dora han split
    yaku_han_label: "Yaku han",
    dora_han_label: "Dora han",
    yaku_han_short: "Yaku",
    dora_han_short: "Dora",
    visible_value_label: "Visible value",
    han_breakdown_title: "Han breakdown",
    dora_alone_not_yaku:
      "Dora alone is not a yaku — you still need a yaku such as Riichi, Yakuhai, or Tanyao to win.",
  },
  zh: {
    app_title: "MahjongAiScreen",
    app_subtitle: "日本麻将 AI 助手",
    tab_quick: "快速分析",
    tab_game: "对局记录",
    lang_label: "EN",

    clear: "清空",
    analyze: "开始分析",
    analysis: "AI 分析",
    analyze_running: "分析中…",
    analyze_failed: "分析失败：{msg}",
    pick_tile: "选择一张牌",
    close: "关闭",
    none_paren: "（无）",
    of: "/",

    your_hand: "我的手牌",
    hand_empty_quick: "点击下方牌图加入手牌。",
    hand_hint_quick:
      "一般手牌为 13 张（摸牌前）或 14 张（摸牌后）。点击手牌中的牌可移除。",
    tile_selector: "牌选择器",
    hand_too_full: "手牌已经是 14 张。",
    too_many_copies: "这张牌的 4 张都已经在你手里。",
    hand_size_error: "手牌必须是 13 或 14 张（当前 {n}）。",
    hand_size_error_with_melds:
      "暗手牌应为 13/14 张减去 3 × 副露数（当前 {n} 张，副露 {melds} 个）。",

    setup_title: "开局设置",
    setup_hint: "设置场风、自风、宝牌指示牌和起始 13 张手牌。这些项稍后均可修改。",
    round_wind: "场风",
    seat_wind: "自风",
    honba: "本场",
    riichi_sticks: "立直棒",
    dealer_position: "亲家位置",
    dealer_inferred_label: "亲家",
    dealer_inferred: "{player}（东家）",
    dora_indicators: "宝牌指示牌",
    add_dora: "+ 添加指示牌",
    starting_hand: "起始手牌",
    starting_hand_hint: "请选择 13 张作为起始手牌。",
    start_hand: "开始对局",
    pick_more_tiles: "还需选择 {count} 张牌。",
    ready_to_start: "可以开始。",
    setup_clear_hand_confirm: "清空已选的全部起始牌？",
    no_indicators: "尚未添加指示牌 — 点击 + 添加指示牌。",

    east: "东",
    south: "南",
    west: "西",
    north: "北",
    east_dealer: "东（亲）",
    you: "我",
    shimocha: "下家",
    toimen: "对面",
    kamicha: "上家",
    you_short: "我",
    shimocha_short: "下家",
    toimen_short: "对面",
    kamicha_short: "上家",

    tracking_title: "对局记录",
    round_label: "{wind}场 · 第 {turn} 巡",
    seat_label: "自风：{wind}",
    honba_label: "本场 {honba} · 立直棒 {sticks}",
    your_river: "我的牌河",
    your_hand_label: "我的手牌",
    add_dora_kan: "+ 杠后指示牌",
    no_dora: "（暂无宝牌）",
    undo: "撤销",
    reset_hand: "重置当局",
    new_setup: "新对局",
    new_setup_confirm: "确认放弃当前对局并返回设置？",
    reset_confirm: "重置回起始手牌？",
    undone_msg: "已撤销。",
    reset_msg: "已重置。",
    pick_dora_title: "选择新增的宝牌指示牌",

    turn_user_draw: "你的回合 — 点击你刚摸到的牌",
    turn_user_discard: "点击手牌中的一张作为打出的牌",
    turn_opp_discard: "{seat}的回合 — 点击对方打出的牌",
    turn_user_call: "你已鸣牌 — 请从手牌中点击需要露出的牌",
    turn_blocked: "请先处理上方的鸣牌动作",
    advance_turn_btn: "跳过这巡",

    after_discard: "最近舍牌：{tile}（来自{seat}）",
    call_chi: "吃",
    call_pon: "碰",
    call_kan: "杠",
    call_ron: "荣和",
    call_pass: "跳过",
    riichi: "立直",
    opp_called_btn: "对手鸣牌",
    opp_called_title: "记录对手的鸣牌",
    pick_called_tile: "点击被鸣的牌",
    pick_meld_tiles: "点击和这张牌组成副露的牌",
    chi_pick_low: "点击吃顺中最小的那张",
    pon_chosen: "碰：将记录 3 张相同的牌",
    kan_chosen: "杠：将记录 4 张相同的牌",
    cannot_chi: "只能从上家（左侧）吃。",
    cannot_pon: "你手中没有两张同样的牌。",
    cannot_kan: "你手中没有三张同样的牌。",
    call_not_enough_copies:
      "这张牌剩余的数量不足以进行该鸣牌——牌面上已经能看到太多张了。",

    rec_recommended: "推荐",
    rec_not_recommended: "不推荐",
    rec_pass_default: "暂无好的鸣牌选择 — 跳过继续整理手牌。",
    ron_available: "可荣和",
    tsumo_available: "可自摸",
    call_opportunity: "可鸣牌",
    latest_discard: "最新弃牌",
    current_turn: "当前回合",
    winning_hand: "和牌",
    open_melds_label: "副露",
    discard_river: "牌河",
    unknown_tile: "未知牌",
    cancel: "取消",
    opp_called_pick_seat: "哪位对手鸣牌？",
    opp_called_pick_type: "{seat} — 选择鸣牌类型",
    no_legal_calls_auto_passed: "没有可鸣的牌 — 已自动跳过。",

    call_zone_chi: "拖到这里执行：吃",
    call_zone_pon: "拖到这里执行：碰",
    call_zone_kan: "拖到这里执行：杠",
    drag_discard_here: "将最新弃牌拖到对应玩家的鸣牌区域",
    warn_chi_not_kamicha: "吃通常只能从上家（左侧）执行。仍然记录这次鸣牌？",
    chi_pick_shape: "选择吃顺型",
    chi_pick_shape_hint: "已被吃：{tile} — 请选择手中两张完成顺子的牌。",

    call_ankan: "暗杠",
    ankan_no_candidates: "你手里没有四张同样的牌。",
    ankan_pick_tile: "选择要暗杠的牌",
    ankan_kan_dora_prompt: "现在添加杠后宝牌指示牌？",
    opp_ankan_known_prompt: "知道是哪张牌吗？确定 = 选择该牌，取消 = 记录为未知。",

    yaku_directions_label: "可能的役种方向",
    dora_in_hand: "手中宝牌",
    yakuhai_pairs: "役牌对子",

    reason_yakuhai: "役牌",
    reason_dora: "宝牌",
    reason_keep_honitsu: "留 - 混一色",
    reason_keep_chinitsu: "留 - 清一色",
    reason_keep_tanyao: "留 - 断幺九",
    reason_keep_toitoi: "留 - 对对和",
    reason_keep_kokushi: "留 - 国士",
    reason_keep_chiitoi: "留 - 七对",
    reason_break_tanyao: "破断幺九",
    reason_break_honitsu: "破混一色",
    reason_break_chinitsu: "破清一色",

    dora_short: "宝",
    dora_indicator_label: "宝牌指示牌",
    aka_dora_label: "红宝牌",
    dora_warn_pill: "宝牌",
    only_one_red_per_suit: "每种花色只允许一张红五。",
    normal_five_max_3: "每种花色仅有 3 张普通五（第 4 张是红五）。",
    tile_limit_reached: "牌数已达上限。",
    normal_five_label: "普通五",
    red_five_label: "红五",
    han_user_label: "番数",
    han_opp_label: "番数",
    estimated_han: "估计番数",
    visible_han: "可见番数",
    valuable_tile: "高价值牌",
    dora_discard_warning: "弃宝牌将损失打点",
    tile_is_dora: "这张牌是宝牌",
    tile_is_red_dora: "这张牌是红宝牌",
    tile_is_double_dora: "这张牌同时是红宝牌和宝牌——价值很高",
    unknown_label: "未知",

    win_tsumo: "自摸",
    win_ron: "荣和",
    win_section_title: "本局结束",
    win_by_tsumo: "{player}自摸",
    win_by_ron: "{player}荣和",
    next_hand: "下一局",
    return_setup: "返回设置",
    win_player_user: "你",
    win_player_opp: "对手（{seat}）",
    no_last_discard: "尚无最近舍牌 — 荣和需要有最近的舍牌。",

    ai_recommendation: "AI 推荐",
    best_form: "最佳形",
    form_normal: "标准（4面子+1雀头）",
    form_chiitoi: "七对子",
    form_kokushi: "国士无双",
    shanten: "向听数",
    shanten_winning: "和牌型",
    shanten_tenpai: "听牌",
    shanten_n: "{n}-向听",
    ukeire: "有效牌",
    ukeire_count: "有效摸牌：{n} 张（{k} 种）",
    threats: "立直威胁",
    discard_candidates: "舍牌候选（按最佳排序）",
    discard_candidates_def: "舍牌候选（效率 × 防守）",
    improving_tiles: "可使向听前进的牌",
    danger_pill: "危险度 {n} · {label}",
    rank_best: "最推荐",
    rank_n: "#{n}",
    badge_score: "有效 {n}",
    badge_score_def: "有效 {n} · 险 {d}",

    chi_only_kamicha: "只能从上家（左侧）吃。",
    not_enough_tiles_for_meld: "你手中没有所需的牌。",
    hand_full_discard_first: "请先打出一张再摸牌。",

    cannot_chi_no_tiles: "吃牌需要手中有对应的两张顺子牌。",
    cannot_call_own_discard: "不能鸣自己打出的牌。",
    invalid_action_rejected: "非法操作已拒绝。",
    not_enough_matching_tiles: "手牌中没有足够的同种牌。",
    chi_left_only: "只能吃上家的牌。",
    tile_count_exceeds_limit: "牌数超过上限。",
    manual_override: "手动覆盖",
    tile_pool_invalid: "牌池数据不一致——上一步动作已撤销。",

    yaku_han_label: "役种番数",
    dora_han_label: "宝牌番数",
    yaku_han_short: "役",
    dora_han_short: "宝",
    visible_value_label: "可见打点",
    han_breakdown_title: "番数构成",
    dora_alone_not_yaku:
      "宝牌本身不是役——你仍然需要立直、役牌、断幺九等真正的役才能和牌。",
  },
};

let currentLang = "en";

function getStoredLang() {
  try {
    return localStorage.getItem(I18N_STORAGE_KEY) || "en";
  } catch (_e) {
    return "en";
  }
}

function setLanguage(lang) {
  if (!I18N[lang]) lang = "en";
  currentLang = lang;
  try {
    localStorage.setItem(I18N_STORAGE_KEY, lang);
  } catch (_e) {
    /* ignore */
  }
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  applyI18n();
}

function getLanguage() {
  return currentLang;
}

function t(key, params) {
  const dict = I18N[currentLang] || I18N.en;
  const fallback = I18N.en[key];
  let raw = dict[key] !== undefined ? dict[key] : fallback;
  if (raw === undefined) raw = key;
  if (params) {
    for (const k of Object.keys(params)) {
      raw = raw.replaceAll(`{${k}}`, String(params[k]));
    }
  }
  return raw;
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder));
  });
  // Tell the rest of the app to redraw any computed labels.
  window.dispatchEvent(new CustomEvent("i18n:changed", { detail: { lang: currentLang } }));
}

// Bootstrap: pick stored language as soon as the dictionary loads.
currentLang = getStoredLang();
