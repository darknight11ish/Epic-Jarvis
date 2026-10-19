/**
 * Focus presets - the reading and the words the desktop draws.
 *
 * The PC owns this feature. `backend/jarvis_presets.py` and the generated
 * `backend/fixtures/work_presets.json` are the contract: five presets (an id,
 * title, focus, what, cost, worse, model, lane, context, pending, heavy-mode and
 * the one apply block), the hardware block and the recommendations. This file
 * only reads that answer and turns it into the small view objects the quickbar
 * and Settings draw. It deliberately knows no preset name or id: a preset
 * added, renamed or removed by the PC must appear, disappear or move without a
 * desktop release.
 *
 * The LAN/apply half has not landed yet. Every preset's `apply` block has the
 * action, switch route, lane-start bit and `auto: false` - but no apply route -
 * so applyState reports "waiting" and the one action stays disabled. When the
 * lane patch adds its route/field, this reading enables it without a UI change.
 *
 * It is a plain ES module with no DOM and no Tauri import so `node
 * tests/focus-presets.mjs` can exercise every rule without a browser. The DOM
 * wiring lives in focus-presets-bar.js (the command bar) and
 * focus-presets-settings.js (Settings -> Focus presets).
 *
 * NOTHING HERE APPLIES A PRESET. There is one action in the whole feature -
 * "Use this preset" - and only a click on that button posts it. A page load,
 * a link reconnect, a changed selection and a fresh reading all draw words and
 * nothing else.
 */

/** This page's own words. Every preset's words come from the PC. */
export const TITLE = "Focus presets";
export const KICKER = "What are you about to work on?";
export const HOW_TO =
  "Pick the preset closest to the work. The PC shows what each one is for, " +
  "which model and graphics card it uses, and what it is honestly worse at " +
  "before you choose anything.";
export const ONE_CARD =
  "Choosing a preset raises one approval card on the PC. Nothing switches " +
  "until you answer it, and the phone shows the same card.";
export const ACTION = "Use this preset";
export const CURRENT_WORDS = "Current";
export const PICK_FIRST = "Pick a preset first.";
export const ALREADY_CHOSEN = "This preset is already chosen.";
export const STALE_WORDS =
  "The PC link is stale. Wait for it to come back, then try again.";
export const UNAVAILABLE_WORDS =
  "This PC does not have the preset selector yet. Update the backend by " +
  "running apply-patches.ps1.";
export const BAD_ANSWER_WORDS =
  "The PC answered, but not in a way this app can read. Update the backend " +
  "by running apply-patches.ps1.";
export const NO_PRESETS_WORDS = "The PC listed no presets.";
export const NO_CHOICE_WORDS = "No preset chosen yet";
export const BEING_PREPARED = "Being prepared";
export const APPLY_WAITING =
  "The apply/lane patch is not on the PC yet. Until it lands, no preset can " +
  "be applied; nothing changes here.";
export const ASKED_WORDS = "Asked the PC. Nothing changes until you answer the card.";
export const REFUSED_WORDS = "That did not work.";

function plain(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map(plain).filter(Boolean).join(" ");
  }
  if (typeof value === "object") {
    for (const key of ["words", "text", "label", "name", "title", "why", "detail", "value"]) {
      const got = plain(value[key]);
      if (got) return got;
    }
  }
  return "";
}

function field(row, names) {
  for (const name of names) {
    const got = plain(row && row[name]);
    if (got) return got;
  }
  return "";
}

function numberText(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  return plain(value);
}

function isFalse(value) {
  return value === false || value === "false" || value === 0 || value === "0";
}

function laneWords(row) {
  const lane = row && row.lane;
  if (typeof lane === "string") return lane.trim();
  if (!lane || typeof lane !== "object") return "";
  const card = field(lane, ["card", "name", "label"]);
  const words = field(lane, ["words", "detail", "why"]);
  return [card, words].filter(Boolean).join(" · ");
}

function contextWords(value) {
  const got = numberText(value);
  return got ? `${got} tokens` : "";
}

function presetStatus(row) {
  const pending = Boolean(row && (row.pending === true || row.preparing === true)) ||
    isFalse(row && row.ready) ||
    /preparing|pending|install|download|measuring|not ready/i.test(
      field(row, ["status", "state", "readiness"]),
    );
  const statusWords = field(row, ["status_words", "pending_words", "why", "note", "not_ready_words"]);
  return { ready: !pending, statusWords: pending ? (statusWords || BEING_PREPARED) : "" };
}

function applySupport(row) {
  const apply = row && row.apply && typeof row.apply === "object" ? row.apply : {};
  // The contract half ships switch_route/lane_start/auto but NO apply route.
  // The LAN/apply patch adds the route (or sets an explicit ready/available
  // bit); until then the one action is disabled, never guessed.
  const route = field(apply, ["apply_route", "route", "apply_path", "path"]) ||
    field(row, ["apply_route", "apply_path"]);
  const enabled = Boolean(route) ||
    ((apply.enabled === true || apply.available === true || apply.ready === true) &&
      !isFalse(apply.enabled) && !isFalse(apply.available));
  return {
    ready: enabled,
    action: field(apply, ["action", "label", "words"]) || ACTION,
    why: field(apply, ["why", "note", "waiting_words", "disabled_words"]) || APPLY_WAITING,
    route,
    laneStart: apply.lane_start === true || apply.lane_start === "true",
    auto: apply.auto === true,
  };
}

function detailsOf(row) {
  const out = [];
  const model = field(row, ["model", "model_name"]);
  const lane = laneWords(row);
  const context = contextWords(row && row.context);
  const cost = field(row, ["cost", "cost_words", "costs"]);
  const worse = field(row, ["worse", "worse_at", "worseAt", "worse_words"]);
  if (model) out.push({ label: "Model", value: model });
  if (lane) out.push({ label: "Lane", value: lane });
  if (context) out.push({ label: "Context", value: context });
  if (cost) out.push({ label: "Cost", value: cost });
  if (worse) out.push({ label: "Worse at", value: worse });
  if (row && row.heavy_mode === true) out.push({ label: "Mode", value: "Heavy: both cards" });
  return out;
}

function normalisePreset(row) {
  if (!row || typeof row !== "object") return null;
  const id = field(row, ["id", "preset_id", "slug"]);
  const name = field(row, ["title", "name", "label"]);
  if (!id || !name) return null;
  const status = presetStatus(row);
  const apply = applySupport(row);
  return {
    id,
    name,
    focus: field(row, ["focus", "focus_words", "kicker"]),
    description: field(row, ["what", "description", "words", "detail", "summary"]),
    details: detailsOf(row),
    ready: status.ready,
    statusWords: status.statusWords,
    applyReady: apply.ready,
    applyAction: apply.action,
    applyWhy: apply.why,
    selectedOnServer: Boolean(row.selected || row.current || row.chosen),
  };
}

function hardwareCard(row) {
  if (!row || typeof row !== "object") return null;
  const name = field(row, ["name", "model", "title"]);
  const vram = numberText(row.vram_gib ?? row.memory_gib ?? row.vram);
  return {
    name: name || "A graphics card",
    vram: vram ? `${vram} GB` : "",
  };
}

function normaliseHardware(raw) {
  if (!raw || typeof raw !== "object") {
    return {
      available: false, count: 0, cards: [], source: "",
      focusChoices: [], priorityChoices: [], why: "",
    };
  }
  const detected = raw.detected && typeof raw.detected === "object" ? raw.detected : {};
  const questionnaire = raw.questionnaire && typeof raw.questionnaire === "object" ? raw.questionnaire : {};
  const cards = Array.isArray(detected.cards)
    ? detected.cards.map(hardwareCard).filter(Boolean)
    : [];
  const count = Number.isInteger(detected.count) ? detected.count : cards.length;
  const focusChoices = Array.isArray(questionnaire.focus_choices)
    ? questionnaire.focus_choices.map((x) => plain(x)).filter(Boolean)
    : [];
  const priorityChoices = Array.isArray(questionnaire.priority_choices)
    ? questionnaire.priority_choices.map((x) => plain(x)).filter(Boolean)
    : [];
  return {
    available: true,
    count,
    cards,
    source: field(detected, ["source"]),
    focusChoices,
    priorityChoices,
    answers: questionnaire.answers,
    why: "",
  };
}

function emptyReading(why) {
  return {
    available: false,
    why,
    title: TITLE,
    kicker: KICKER,
    howTo: HOW_TO,
    chosenId: "",
    chosen: null,
    lane: { words: "", label: "", ready: false, why: "" },
    presets: [],
    hardware: normaliseHardware(null),
    applyAction: ACTION,
    applyReady: false,
    applyWhy: APPLY_WAITING,
  };
}

/**
 * The PC's answer, read. Never throws; a shape this desktop cannot read is an
 * honest `available: false` with the update line, not a made-up preset list.
 *
 * `raw` is whatever the bridge returned: the fixture/HTTP body unchanged, or a
 * Tauri error string. The fixture's real shape is in
 * `backend/fixtures/work_presets.json`; tests read that file itself so this
 * reading cannot drift from the contract.
 */
export function normaliseReading(raw) {
  if (typeof raw === "string") return emptyReading(raw.trim() || BAD_ANSWER_WORDS);
  if (!raw || typeof raw !== "object") return emptyReading(BAD_ANSWER_WORDS);
  if (raw.ok === false) {
    return emptyReading(field(raw, ["why", "error", "message"]) || UNAVAILABLE_WORDS);
  }
  const body = raw.data && typeof raw.data === "object" ? raw.data : raw;
  if (body.available === false) {
    return emptyReading(field(body, ["why", "detail", "error"]) || UNAVAILABLE_WORDS);
  }
  const rows = body.presets;
  if (!Array.isArray(rows)) return emptyReading(field(body, ["why", "error"]) || BAD_ANSWER_WORDS);
  if (rows.length === 0) return emptyReading(NO_PRESETS_WORDS);

  const seen = new Set();
  const presets = [];
  for (const row of rows) {
    const preset = normalisePreset(row);
    if (!preset || seen.has(preset.id)) return emptyReading(BAD_ANSWER_WORDS);
    seen.add(preset.id);
    presets.push(preset);
  }

  const chosenRaw = body.chosen !== undefined ? body.chosen
    : body.current !== undefined ? body.current
      : body.selected !== undefined ? body.selected : "";
  let chosenId = "";
  if (typeof chosenRaw === "string") chosenId = chosenRaw.trim();
  else if (chosenRaw && typeof chosenRaw === "object") {
    chosenId = field(chosenRaw, ["id", "preset_id", "slug"]);
  }
  if (!chosenId) {
    const selected = presets.find((p) => p.selectedOnServer);
    chosenId = selected ? selected.id : "";
  }
  // An unknown chosen id is not fatal: the PC may have removed it between reads.
  // It simply marks no row until the next read, rather than blanking the page.
  const chosen = presets.find((p) => p.id === chosenId) || null;
  if (!chosen) chosenId = "";

  const laneRaw = body.lane !== undefined ? body.lane
    : body.lane_status !== undefined ? body.lane_status
      : body.laneStatus !== undefined ? body.laneStatus : "";
  const laneObject = laneRaw && typeof laneRaw === "object" ? laneRaw : null;
  const lane = {
    words: plain(laneRaw),
    label: field(laneObject || {}, ["label", "name", "words"]),
    ready: laneObject ? !isFalse(laneObject.ready) : true,
    why: field(laneObject || {}, ["why", "detail", "note"]),
  };
  if (!lane.label) lane.label = lane.words;

  const apply = applySupport(presets[0]);
  const waiting = presets.find((p) => !p.applyReady);
  return {
    available: true,
    why: "",
    title: field(body, ["title", "heading"]) || TITLE,
    kicker: field(body, ["kicker", "question"]) || KICKER,
    howTo: field(body, ["how_to", "howTo", "explain"]) || HOW_TO,
    oneCard: field(body, ["one_card", "one_card_words", "approval_words"]) || ONE_CARD,
    note: field(body, ["note", "note_words", "second_note"]),
    chosenId: chosen ? chosen.id : "",
    chosen,
    lane,
    presets,
    hardware: normaliseHardware(body.hardware),
    oldIds: Array.isArray(body.old_ids_replaced)
      ? body.old_ids_replaced.map((x) => plain(x)).filter(Boolean)
      : [],
    applyAction: apply.action,
    applyReady: presets.every((p) => p.applyReady),
    applyWhy: presets.every((p) => p.applyReady) ? "" : (waiting || {}).applyWhy || APPLY_WAITING,
  };
}

/** The chip in the command bar: only the PC's own name for the chosen preset. */
export function chipView(reading, { stale = false, busy = false } = {}) {
  if (!reading || !reading.available) return { hidden: true };
  const name = reading.chosen ? reading.chosen.name : NO_CHOICE_WORDS;
  return {
    hidden: false,
    label: name,
    title: reading.chosen
      ? `Focus presets: ${name}. Click to choose another.`
      : `Focus presets: ${name}. Click to choose one.`,
    stale: Boolean(stale),
    disabled: Boolean(stale) || Boolean(busy),
    why: stale ? STALE_WORDS : "",
  };
}

/** One preset row, in the command-bar card and on Settings. */
export function presetView(preset, chosenId) {
  return {
    id: preset.id,
    name: preset.name,
    focus: preset.focus,
    description: preset.description,
    details: preset.details,
    current: preset.id === chosenId,
    ready: preset.ready,
    statusWords: preset.statusWords,
  };
}

function applyState(reading, selectedId, { stale = false, busy = false } = {}) {
  if (stale) return { ok: false, why: STALE_WORDS };
  if (busy) return { ok: false, why: "Asking the PC..." };
  if (!reading || !reading.available) return { ok: false, why: reading ? reading.why : UNAVAILABLE_WORDS };
  if (!reading.applyReady) return { ok: false, why: reading.applyWhy || APPLY_WAITING };
  const preset = reading.presets.find((p) => p.id === selectedId);
  if (!preset) return { ok: false, why: PICK_FIRST };
  if (preset.id === reading.chosenId) return { ok: false, why: ALREADY_CHOSEN };
  if (!preset.ready) return { ok: false, why: preset.statusWords || BEING_PREPARED };
  if (!preset.applyReady) return { ok: false, why: preset.applyWhy || APPLY_WAITING };
  return { ok: true, why: "", id: preset.id };
}

/**
 * The command-bar card: every preset the PC listed, in the PC's order, with
 * exactly one apply action. `selectedId` starts as the current preset so the
 * action is disabled on arrival (a second click on a card opened from the chip
 * cannot apply without an explicit different choice).
 */
export function pickerView(reading, selectedId, { stale = false, busy = false, line = "" } = {}) {
  if (!reading || !reading.available) {
    return {
      available: false,
      heading: TITLE,
      kicker: KICKER,
      reason: reading ? reading.why : UNAVAILABLE_WORDS,
      items: [],
      action: { label: ACTION, disabled: true, why: reading ? reading.why : UNAVAILABLE_WORDS },
      line: String(line || ""),
    };
  }
  const selection = selectedId || "";
  const applied = applyState(reading, selection, { stale, busy });
  return {
    available: true,
    heading: reading.title,
    kicker: reading.kicker,
    howTo: reading.howTo,
    lane: reading.lane,
    hardware: reading.hardware,
    items: reading.presets.map((p) => ({
      ...presetView(p, reading.chosenId),
      selected: p.id === selection,
      selectable: true,
    })),
    action: {
      label: reading.applyAction,
      disabled: !applied.ok,
      why: applied.why,
    },
    line: String(line || ""),
  };
}

/**
 * The Settings page: the same list and the same one action, with the one-card
 * explanation and the contract's hardware block. Nothing here writes a
 * setting until the owner posts the action; and while the apply/lane patch is
 * absent the one action stays disabled with the PC's own waiting line.
 */
export function settingsView(reading, selectedId, { stale = false, busy = false, line = "" } = {}) {
  if (!reading || !reading.available) {
    return {
      available: false,
      heading: TITLE,
      kicker: KICKER,
      reason: reading ? reading.why : UNAVAILABLE_WORDS,
      oneCard: ONE_CARD,
      note: "",
      items: [],
      hardware: normaliseHardware(null),
      action: { label: ACTION, disabled: true, why: reading ? reading.why : UNAVAILABLE_WORDS },
      line: String(line || ""),
    };
  }
  const selection = selectedId || "";
  const applied = applyState(reading, selection, { stale, busy });
  return {
    available: true,
    heading: reading.title,
    kicker: reading.kicker,
    howTo: reading.howTo,
    oneCard: reading.oneCard || ONE_CARD,
    note: reading.note || "",
    lane: reading.lane,
    hardware: reading.hardware,
    items: reading.presets.map((p) => ({
      ...presetView(p, reading.chosenId),
      selected: p.id === selection,
      selectable: true,
    })),
    action: { label: reading.applyAction, disabled: !applied.ok, why: applied.why },
    line: String(line || ""),
  };
}

/** The words after the one action. Backend words win; fixed words are fallback. */
export function resultLine(raw) {
  if (typeof raw === "string") return raw.trim();
  if (!raw || typeof raw !== "object") return "";
  if (raw.ok === false) {
    return field(raw, ["why", "error", "message", "detail"]) || REFUSED_WORDS;
  }
  const said = field(raw, ["said", "message", "words", "answer", "detail"]);
  if (said) return said;
  if (raw.pending || raw.card || raw.approval || raw.asked) return ASKED_WORDS;
  return ASKED_WORDS;
}

/**
 * The body the one action posts. The backend contract branch names this field;
 * keep it here alone so the fixture can change it in one place. The preset id
 * is the PC's own id, never a desktop-side id.
 */
export function applyArgs(id, fieldName = "preset") {
  return { [fieldName]: String(id || "") };
}

/** Is the one action even reachable on this link? */
export function pressable({ stale = false, busy = false } = {}) {
  return !stale && !busy;
}
