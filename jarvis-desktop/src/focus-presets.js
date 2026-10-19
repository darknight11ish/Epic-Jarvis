/**
 * Focus presets - the reading and the words the desktop draws.
 *
 * The PC owns this feature: it decides which presets exist, what each one is
 * called, which models and lane it uses, what it costs, what it is worse at,
 * which one is chosen and whether a preset is ready. This file only reads that
 * answer and turns it into the small view objects the quickbar and Settings
 * draw. It deliberately knows no preset name or id: a preset added, renamed or
 * removed by the PC must appear, disappear or move without a desktop release.
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

function isFalse(value) {
  return value === false || value === "false" || value === 0 || value === "0";
}

function presetStatus(row) {
  const raw = field(row, ["status", "state", "readiness"]);
  const state = raw.toLowerCase();
  const beingPrepared = Boolean(row && row.being_prepared) ||
    isFalse(row && row.prepared) ||
    isFalse(row && row.ready) ||
    (Array.isArray(row && row.state) && row.state.some((x) => plain(x).toLowerCase() === "preparing"));
  const known = /prepar|install|download|measur|pending|not ready|preparing/.test(state);
  const ready = !(beingPrepared || known);
  const statusWords = field(row, [
    "status_words", "preparing_words", "why", "note", "not_ready_words",
  ]);
  return { ready, statusWords: ready ? "" : (statusWords || BEING_PREPARED) };
}

function detailsOf(row) {
  const out = [];
  const model = field(row, ["model", "model_name"]);
  const lane = field(row, ["lane", "card", "graphics_card", "gpu"]);
  const context = field(row, ["context", "context_words", "context_size"]);
  const cost = field(row, ["cost", "cost_words", "costs"]);
  const worse = field(row, ["worse_at", "worseAt", "worse_words", "worse"]);
  if (model) out.push({ label: "Model", value: model });
  if (lane) out.push({ label: "Lane", value: lane });
  if (context) out.push({ label: "Context", value: context });
  if (cost) out.push({ label: "Cost", value: cost });
  if (worse) out.push({ label: "Worse at", value: worse });
  return out;
}

function normalisePreset(row) {
  if (!row || typeof row !== "object") return null;
  const id = field(row, ["id", "preset_id", "slug"]);
  const name = field(row, ["name", "label", "title"]);
  if (!id || !name) return null;
  const status = presetStatus(row);
  return {
    id,
    name,
    description: field(row, ["description", "words", "what", "detail", "summary"]),
    details: detailsOf(row),
    ready: status.ready,
    statusWords: status.statusWords,
    // Kept so a later contract field can be honoured without changing the
    // drawing code; the PC's own answer wins.
    canApply: row.can_apply === undefined ? true : !isFalse(row.can_apply),
    selectedOnServer: Boolean(row.selected || row.current || row.chosen),
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
  };
}

/**
 * The PC's answer, read. Never throws; a shape this desktop cannot read is an
 * honest `available: false` with the update line, not a made-up preset list.
 *
 * `raw` is whatever the bridge returned: the HTTP body unchanged, or a Tauri
 * error string. The field names below are the contract the backend branch
 * publishes; the aliases are only tolerance for the few spellings already used
 * by older backend answers (camelCase and snake_case).
 */
export function normaliseReading(raw) {
  if (typeof raw === "string") {
    return emptyReading(raw.trim() || BAD_ANSWER_WORDS);
  }
  if (!raw || typeof raw !== "object") return emptyReading(BAD_ANSWER_WORDS);
  if (raw.ok === false) {
    return emptyReading(field(raw, ["why", "error", "message"]) || UNAVAILABLE_WORDS);
  }
  const body = raw.data && typeof raw.data === "object" ? raw.data : raw;
  if (!body || typeof body !== "object") return emptyReading(BAD_ANSWER_WORDS);
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
  const chosen = presets.find((p) => p.id === chosenId) || null;
  if (chosenId && !chosen) return emptyReading(BAD_ANSWER_WORDS);

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
    canApply: body.can_apply === undefined ? true : !isFalse(body.can_apply),
    applyWhy: field(body, ["cannot_apply_words", "apply_why", "apply_note"]),
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
  if (!reading.canApply) return { ok: false, why: reading.applyWhy || REFUSED_WORDS };
  const preset = reading.presets.find((p) => p.id === selectedId);
  if (!preset) return { ok: false, why: PICK_FIRST };
  if (preset.id === reading.chosenId) return { ok: false, why: ALREADY_CHOSEN };
  if (!preset.ready) return { ok: false, why: preset.statusWords || BEING_PREPARED };
  if (!preset.canApply) return { ok: false, why: preset.statusWords || REFUSED_WORDS };
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
    items: reading.presets.map((p) => ({
      ...presetView(p, reading.chosenId),
      selected: p.id === selection,
      selectable: true,
    })),
    action: {
      label: ACTION,
      disabled: !applied.ok,
      why: applied.why,
    },
    line: String(line || ""),
  };
}

/**
 * The Settings page: the same list and the same one action, with the one-card
 * explanation. Nothing here writes a setting until the owner posts the action.
 */
export function settingsView(reading, selectedId, { stale = false, busy = false, line = "" } = {}) {
  if (!reading || !reading.available) {
    return {
      available: false,
      heading: TITLE,
      kicker: KICKER,
      reason: reading ? reading.why : UNAVAILABLE_WORDS,
      oneCard: ONE_CARD,
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
    oneCard: reading.oneCard || ONE_CARD,
    note: reading.note || "",
    lane: reading.lane,
    items: reading.presets.map((p) => ({
      ...presetView(p, reading.chosenId),
      selected: p.id === selection,
      selectable: true,
    })),
    action: { label: ACTION, disabled: !applied.ok, why: applied.why },
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
