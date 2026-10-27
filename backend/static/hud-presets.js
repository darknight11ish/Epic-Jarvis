/**
 * hud-presets.js - the "Presets" menu: the PC's local-AI focus presets and
 * personalities (2026-10-27, the owner's ask), the owner's saved HUD layouts,
 * and the Export / Import controls (H3 of the editable-HUD design, 2026-10-22;
 * Gemini ruling Q5, Rulings 9/27/28).
 *
 * ONE DOCUMENT, ONE WRITE. The layout library lives inside the SAME saved
 * layout document the H2 editor writes, and it is saved through the SAME
 * `set_hud_layout` command (H2's one owner-approved write grant). There is no
 * new capability, no new command, no approval card and no network. Rust
 * (`hud_layout.rs::sanitise`) bounds and validates what is saved; this module's
 * normalizer is the page-side second line, exactly as in H2.
 *
 * COPY/PASTE JSON ONLY. Export writes the current document as pretty JSON into
 * a read-only textarea; Import reads a pasted textarea, validates it with the
 * same closed-world normalizer and saves the repaired document. There is no
 * file input, no `blob:`, no `URL.createObjectURL` and no Tauri dialog
 * capability: the HUD's CSP stays `default-src 'self'` (Ruling 9).
 *
 * THE MENU IS CALLED "PRESETS" NOW, AND IT LISTS MORE THAN LAYOUTS (the
 * owner, 2026-10-26: "you didnt put presets, you put hud layouts" and "i also
 * want the presets to include all the ideal local ai presets that are made
 * (like coder, or general, etc) along with the different personalities of
 * jarvis that i can select"). Above the saved layouts, in the SAME one menu:
 *
 *   * the five local-AI focus presets (`GET /api/presets`, JARVIS-API section
 *     145), with the PC's own `chosen_preset` marking the chosen one;
 *   * Jarvis's nine personalities plus the owner's own "My personalities"
 *     (`GET /api/manner`), with the PC's own `personality` marking the current
 *     one.
 *
 * TWO KINDS, TWO RULES, and the second one is why this file now fetches:
 *
 *   * A MODEL PRESET IS A LOOSENING. Applying one starts its lane and raises
 *     the PC's ONE `change_own_config` (switch_model) approval card; nothing is
 *     chosen until the owner answers it, so NOTHING IS MARKED CHOSEN HERE. The
 *     mark comes from a REFETCH of the PC's own `chosen_preset`, never from the
 *     click that asked for it - a denied card changes nothing and must not look
 *     like a success.
 *   * A PERSONALITY IS WORDING ONLY. The PC says it plainly ("Nothing here
 *     raises a card", `jarvis_manner.py`), so the click is immediate: the menu
 *     shows the PC's own `said` (its switch_ack), then refetches and marks the
 *     personality the PC now names.
 *
 * TWO ROADS, ONE ANSWER. In the desktop shell this page holds NO token (apps
 * security audit M2) and the bootstrap's fetch shim refuses every write except
 * `/api/chat`, so each call has a Rust bridge: `apply_focus_preset` (the same
 * command the page's own focus-preset rail calls), and the HUD's two
 * personality commands (`hud_personalities`, `hud_switch_personality`, granted
 * by the `hud-personalities` set). A plain browser (no shell) uses the same
 * two routes directly with `X-Jarvis-Client: hud`, exactly as the page's own
 * rail does. Both roads answer the same JSON, so the rendering below is one
 * code path.
 *
 * WHAT THIS FILE OWNS: the pure library helpers (duplicate / rename / delete /
 * apply / export / import), so node tests can prove them without a browser; and
 * the browser-only menu/dialog wiring. The card arrangement itself is still
 * H2's `applyAction` - this module only chooses which saved document is active.
 *
 * @module hud-presets
 */

import {
  CARD_REGISTRY,
  DEFAULT_PRESET_ID,
  MAX_USER_PRESETS,
  PRESETS,
  USER_ID_RE,
  USER_NAME_MAX,
  isUserLayout,
  normalizeLayout,
  presetInfo,
  presetLayout,
  userLayouts,
} from "./hud-layout.js";
import { saveLayout } from "./hud-layout-store.js";

/* ── 1. Pure library helpers (node-tested) ───────────────────────────────── */

const BUILT_IN_IDS = new Set(PRESETS.map((preset) => preset.id));

/** A fresh custom id that no existing layout in `doc` uses. */
export function newLayoutId(doc, basePreset) {
  const base = BUILT_IN_IDS.has(basePreset) ? basePreset : DEFAULT_PRESET_ID;
  const taken = new Set(userLayouts(doc).map((entry) => entry.id));
  for (let n = 1; n <= MAX_USER_PRESETS + 1; n += 1) {
    const id = `custom-${base}-${n}`;
    if (!taken.has(id)) return id;
  }
  return `custom-${base}-1`;
}

/** One library entry made from a live document's current arrangement. */
export function entryFromDocument(doc, name, id) {
  const clean = normalizeLayout(doc);
  return {
    id: id || newLayoutId(clean, clean.base_preset),
    name: String(name || "").trim().slice(0, USER_NAME_MAX),
    base_preset: clean.base_preset,
    shell_template: clean.shell_template,
    density: clean.density,
    default_stage_tab: clean.default_stage_tab,
    cards: clean.cards,
  };
}

function withLibrary(doc, library, id, name) {
  return normalizeLayout({ ...doc, id, name, user_presets: library });
}

/**
 * The first edit of a built-in layout becomes a copy, as Ruling 27 asks: the
 * owner's own layout is never silently the shipped one. Editing a user layout
 * returns it unchanged.
 */
export function ensureCustomCopy(doc) {
  const clean = normalizeLayout(doc);
  if (isUserLayout(clean)) return clean;
  const info = presetInfo(clean.base_preset);
  const id = newLayoutId(clean, clean.base_preset);
  const name = `${info ? info.label : clean.name} (Custom)`.slice(0, USER_NAME_MAX);
  const entry = entryFromDocument(clean, name, id);
  return withLibrary({ ...clean, id, name }, [...userLayouts(clean), entry], id, name);
}

/** Duplicate the active arrangement as a new user layout ("Copy of …"). */
export function duplicateLayout(doc) {
  const clean = normalizeLayout(doc);
  if (userLayouts(clean).length >= MAX_USER_PRESETS) {
    return { doc: clean, refused: `You can keep up to ${MAX_USER_PRESETS} layouts. Delete one first.` };
  }
  const baseName = isUserLayout(clean) ? clean.name : `${(presetInfo(clean.base_preset) || clean).name || clean.name}`;
  const name = `${baseName} copy`.slice(0, USER_NAME_MAX);
  const id = newLayoutId(clean, clean.base_preset);
  const entry = entryFromDocument(clean, name, id);
  return { doc: withLibrary({ ...clean, id, name }, [...userLayouts(clean), entry], id, name), refused: "" };
}

/**
 * Rename one saved layout WITHOUT making it active (H3-5). Renaming an entry
 * that is not current must not switch the window to it.
 */
export function renameUserLayout(doc, id, name) {
  const clean = normalizeLayout(doc);
  if (!userLayouts(clean).some((entry) => entry.id === id)) {
    return { doc: clean, refused: "That layout is not saved here." };
  }
  if (clean.id === id) return renameActiveLayout(clean, name);
  const wanted = String(name || "").trim().replace(/\s+/g, " ").slice(0, USER_NAME_MAX);
  if (!wanted) return { doc: clean, refused: "A name is needed." };
  const library = userLayouts(clean).map((entry) => (entry.id === id
    ? { ...entry, name: wanted } : entry));
  return { doc: withLibrary(clean, library, clean.id, clean.name), refused: "" };
}

/** Rename the ACTIVE user layout. Built-in layouts cannot be renamed. */
export function renameActiveLayout(doc, name) {
  const clean = normalizeLayout(doc);
  if (!isUserLayout(clean)) {
    return { doc: clean, refused: "Built-in layouts keep their names. Use Duplicate first." };
  }
  const wanted = String(name || "").trim().replace(/\s+/g, " ").slice(0, USER_NAME_MAX);
  if (!wanted) return { doc: clean, refused: "A name is needed." };
  const library = userLayouts(clean).map((entry) => (entry.id === clean.id
    ? { ...entry, name: wanted } : entry));
  return { doc: withLibrary(clean, library, clean.id, wanted), refused: "" };
}

/** Apply one user layout by id (returns the same document if unknown). */
export function applyUserLayout(doc, id) {
  const clean = normalizeLayout(doc);
  const entry = userLayouts(clean).find((item) => item.id === id);
  if (!entry) return clean;
  const library = userLayouts(clean);
  return normalizeLayout({
    ...clean,
    id: entry.id,
    name: entry.name,
    base_preset: entry.base_preset,
    shell_template: entry.shell_template,
    density: entry.density,
    default_stage_tab: entry.default_stage_tab,
    cards: entry.cards,
    user_presets: library,
  });
}

/** Delete a user layout. Deleting the active one falls back to its base. */
export function deleteUserLayout(doc, id) {
  const clean = normalizeLayout(doc);
  const library = userLayouts(clean).filter((entry) => entry.id !== id);
  if (library.length === userLayouts(clean).length) return clean;
  const removed = userLayouts(clean).find((entry) => entry.id === id);
  if (clean.id !== id) return withLibrary(clean, library, clean.id, clean.name);
  const fallback = presetLayout(removed ? removed.base_preset : clean.base_preset);
  return normalizeLayout({ ...fallback, user_presets: library });
}

/** The document as exportable JSON text: structure only, never page content. */
export function exportLayoutJson(doc) {
  const clean = normalizeLayout(doc);
  return `${JSON.stringify({
    version: clean.version,
    kind: "jarvis.hud.layout",
    id: clean.id,
    name: clean.name,
    base_preset: clean.base_preset,
    shell_template: clean.shell_template,
    density: clean.density,
    default_stage_tab: clean.default_stage_tab,
    cards: clean.cards,
    user_presets: clean.user_presets,
  }, null, 2)}\n`;
}

export const IMPORT_MAX_BYTES = 64 * 1024;

/**
 * Validate pasted JSON and turn it into the document the page would render.
 * Refuses, in plain words, anything that is not recognisably one of our layout
 * documents - a hostile or unrelated JSON blob must never silently become a
 * layout.
 */
export function importLayoutText(text) {
  const raw = typeof text === "string" ? text : "";
  if (!raw.trim()) return { ok: false, error: "Paste a layout first." };
  // H3-4: count BYTES, the same unit the store's cap uses - a multi-byte
  // character is one UTF-16 unit but more than one byte, and the save would
  // otherwise fail after validation with a different sentence.
  const bytes = typeof TextEncoder === "function"
    ? new TextEncoder().encode(raw).length : raw.length * 2;
  if (bytes > IMPORT_MAX_BYTES) {
    return { ok: false, error: "That JSON is too long to be one of your layouts." };
  }
  let value;
  try {
    value = JSON.parse(raw);
  } catch {
    return { ok: false, error: "That is not valid JSON. Nothing was imported." };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { ok: false, error: "That is not a layout. Nothing was imported." };
  }
  if (value.version !== 1) {
    return { ok: false, error: "That layout is a different version. Nothing was imported." };
  }
  const rawCards = Array.isArray(value.cards) ? value.cards : [];
  if (!rawCards.length) {
    return { ok: false, error: "That layout has no cards. Nothing was imported." };
  }
  // H3-2: check the RAW library length before the normalizer clamps it, so an
  // oversize import is refused in words instead of being silently truncated.
  const rawLibrary = Array.isArray(value.user_presets) ? value.user_presets : [];
  if (rawLibrary.length > MAX_USER_PRESETS) {
    return { ok: false, error: `That JSON carries more than ${MAX_USER_PRESETS} layouts. Nothing was imported.` };
  }
  const clean = normalizeLayout(value);
  // normalizeLayout repairs unknown cards by dropping them. For an IMPORT,
  // dropping most of a document silently would be a lie: refuse instead.
  const registry = new Set(CARD_REGISTRY.map((card) => card.id));
  const knownRaw = rawCards.filter((card) => card && typeof card === "object"
    && registry.has(card.id));
  if (!knownRaw.length) {
    return { ok: false, error: "That layout names no card Jarvis knows. Nothing was imported." };
  }
  if (knownRaw.length < rawCards.length) {
    return { ok: false, error: "That layout names a card Jarvis does not have. Nothing was imported." };
  }
  if (userLayouts(clean).length > MAX_USER_PRESETS) {
    return { ok: false, error: `That layout carries more than ${MAX_USER_PRESETS} layouts. Nothing was imported.` };
  }
  return { ok: true, doc: clean };
}

const importSignature = (entry) => JSON.stringify({
  base: entry.base_preset,
  shell: entry.shell_template,
  density: entry.density,
  tab: entry.default_stage_tab,
  cards: entry.cards,
});

/**
 * The imported layout becomes ACTIVE and is added to My layouts - it never
 * replaces or truncates the owner's saved library (H3-1).
 *
 * `currentDoc` is the document the owner already has. Its `user_presets` are
 * the base of the merged library; the imported document's own entries are only
 * added when their id and name are not already used, so importing the owner's
 * own full export does not duplicate the active entry toward the 20 cap. If the
 * merged library would exceed the cap, this REFUSES in words rather than
 * silently trimming the owner's layouts.
 */
export function adoptImportedLayout(doc, currentDoc = null) {
  const imported = normalizeLayout(doc);
  const current = currentDoc ? normalizeLayout(currentDoc) : presetLayout(DEFAULT_PRESET_ID);
  const merged = userLayouts(current).map((entry) => ({ ...entry }));
  const ids = new Set(merged.map((entry) => entry.id));
  const names = new Set(merged.map((entry) => entry.name.toLowerCase()));
  const full = () => ({
    doc: current,
    refused: `You can keep up to ${MAX_USER_PRESETS} layouts. Delete one before importing.`,
  });

  // The imported document may itself carry a library (the owner's own export).
  for (const entry of userLayouts(imported)) {
    if (ids.has(entry.id) || names.has(entry.name.toLowerCase())) continue;
    if (merged.length >= MAX_USER_PRESETS) return full();
    merged.push(entry);
    ids.add(entry.id);
    names.add(entry.name.toLowerCase());
  }

  const base = presetInfo(imported.base_preset) ? imported.base_preset : DEFAULT_PRESET_ID;
  let name = (String(imported.name || "").trim() || "Imported layout").slice(0, USER_NAME_MAX);
  // Reuse the owner's own entry when the imported arrangement IS that entry
  // (their own full export); otherwise this is a new saved layout.
  let entry = merged.find((item) => item.name.toLowerCase() === name.toLowerCase()
    && importSignature(item) === importSignature(entryFromDocument({
      ...imported, base_preset: base,
    }, name, "custom-placeholder")));
  if (!entry && names.has(name.toLowerCase())) {
    // Same name, different arrangement: keep both, with a plain, unique suffix.
    let n = 2;
    while (names.has(name.toLowerCase()) && n < 50) {
      name = `${String(imported.name || "Imported layout").trim().slice(0, USER_NAME_MAX - 3)} ${n}`;
      n += 1;
    }
  }
  entry = merged.find((item) => item.name.toLowerCase() === name.toLowerCase()
    && importSignature(item) === importSignature(entryFromDocument({
      ...imported, base_preset: base,
    }, name, "custom-placeholder")));
  if (!entry) {
    if (merged.length >= MAX_USER_PRESETS) return full();
    const id = newLayoutId({ ...imported, user_presets: merged }, base);
    entry = entryFromDocument({ ...imported, base_preset: base }, name, id);
    merged.push(entry);
  }
  return {
    doc: withLibrary({ ...imported, id: entry.id, name: entry.name, base_preset: base },
      merged, entry.id, entry.name),
    refused: "",
  };
}

export { USER_ID_RE, MAX_USER_PRESETS };

/* ── 2. The PC's own presets (node-tested) ───────────────────────────────── */

/**
 * The five local-AI focus presets, in the order the PC lists them
 * (`GET /api/presets`). Pure, so node tests can prove the reading without a
 * browser. The PC's own `chosen_preset` is the ONLY thing that marks a row
 * chosen - never the click that asked for it.
 */
export function modelPresetRows(payload) {
  const body = payload && typeof payload === "object" ? payload : {};
  if (body.available === false) return [];
  const rows = Array.isArray(body.presets) ? body.presets : [];
  const chosen = typeof body.chosen_preset === "string" ? body.chosen_preset : "";
  return rows
    .filter((row) => row && typeof row === "object"
      && typeof row.id === "string" && row.id)
    .map((row) => ({
      id: row.id,
      title: typeof row.title === "string" && row.title ? row.title : row.id,
      focus: typeof row.focus === "string" ? row.focus : "",
      chosen: row.id === chosen,
    }));
}

/**
 * The personalities the PC offers (`GET /api/manner`): its nine built-ins in
 * its own order, then the owner's saved "My personalities" when there are
 * any. `current` is the PC's own answer, never the last click. Pure for the
 * same reason as above; a row that carries no id or no name is dropped rather
 * than drawn as an unclickable blank.
 */
export function personalityRows(payload) {
  const body = payload && typeof payload === "object" ? payload : {};
  const current = typeof body.personality === "string" ? body.personality : "";
  const builtIn = Array.isArray(body.personalities) ? body.personalities : [];
  const own = Array.isArray(body.user_personalities) ? body.user_personalities
    : (Array.isArray(body.custom_personalities) ? body.custom_personalities : []);
  const rows = [];
  for (const raw of builtIn) {
    const row = raw && typeof raw === "object" ? raw : {};
    const id = typeof row.id === "string" ? row.id : "";
    if (!id) continue;
    rows.push({
      id,
      title: typeof row.title === "string" && row.title ? row.title : id,
      hint: typeof row.description === "string" ? row.description : "",
      custom: false,
      current: id === current,
    });
  }
  for (const raw of own) {
    const row = raw && typeof raw === "object" ? raw : {};
    const id = typeof row.id === "string" ? row.id : "";
    const name = typeof row.name === "string" && row.name ? row.name : "";
    if (!id || !name) continue;
    rows.push({
      id,
      title: name,
      hint: typeof row.line === "string" ? row.line : "",
      custom: true,
      current: id === current,
    });
  }
  return { rows, current };
}

/** The body one personality click sends: ONE field, never a dial or a mode. */
export function personalitySwitchBody(id) {
  return { personality: String(id || "") };
}

/** The body one model-preset click sends: ONE field, the preset's own id. */
export function modelApplyBody(id) {
  return { preset: String(id || "") };
}

/* ── 3. The roads to the PC (node-tested with a fake window) ─────────────── */

/** The shell's IPC bridge, or null in a plain browser. The HUD page holds no
 *  token (apps security audit M2): with a shell every request goes through
 *  Rust, which adds it. */
export function shellCoreOf(win) {
  try {
    const core = win && win.__TAURI__ && win.__TAURI__.core;
    return core && typeof core.invoke === "function" ? core : null;
  } catch { /* a page with no shell */ }
  return null;
}

/** The header the standing rule asks for on EVERY request: the page's own
 *  `JARVIS.headers()` adds the token when the page has one (a browser), and
 *  `X-Jarvis-Client: hud` is sent either way. Rust's `jarvis_headers()` sends
 *  the same client name on the shell road. */
export function apiHeadersFor(win, extra) {
  const base = extra ? { ...extra } : {};
  const jarvis = win && win.JARVIS;
  if (jarvis && typeof jarvis.headers === "function") return jarvis.headers(base);
  return { "X-Jarvis-Client": "hud", ...base };
}

export function apiUrlFor(win, path) {
  const jarvis = win && win.JARVIS;
  return jarvis && typeof jarvis.url === "function" ? jarvis.url(path) : path;
}

/** A thrown string (Rust) or an Error, said in one plain line. */
export function errorTextOf(error) {
  if (typeof error === "string" && error) return error;
  return (error && error.message) || String(error || "no answer");
}

/** The one reading of a write's answer, on the browser road. */
async function readWriteAnswer(response) {
  let answer = null;
  try { answer = await response.json(); } catch { /* a refusal may be empty */ }
  if (!response.ok) {
    throw new Error((answer && (answer.error || answer.reason))
      || `the PC answered ${response.status}`);
  }
  if (!answer || typeof answer !== "object") {
    throw new Error("the PC answered, but not in a way this menu can read");
  }
  return answer;
}

/** `GET /api/presets`, on whichever road this page has. The shell command is
 *  the page's own `get_focus_presets` (the same answer the page's focus-preset
 *  rail reads); a plain browser reads the route itself. */
export async function readFocusPresetsOnPc(win) {
  const core = shellCoreOf(win);
  if (core) return core.invoke("get_focus_presets");
  const response = await win.fetch(apiUrlFor(win, "/api/presets"), {
    cache: "no-store", headers: apiHeadersFor(win),
  });
  if (!response.ok) throw new Error(`the PC answered ${response.status}`);
  return response.json();
}

/** `GET /api/manner`: the personalities half. It has its own HUD command
 *  (`hud_personalities`) because this page holds no token (M2) and a read
 *  outside `hud_get`'s fixed list would be refused by the bootstrap. */
export async function readPersonalitiesOnPc(win) {
  const core = shellCoreOf(win);
  if (core) return core.invoke("hud_personalities");
  const response = await win.fetch(apiUrlFor(win, "/api/manner"), {
    cache: "no-store", headers: apiHeadersFor(win),
  });
  if (!response.ok) throw new Error(`the PC answered ${response.status}`);
  return response.json();
}

/** `POST /api/work/apply {"preset": id}` - ONE card on the PC. In the shell
 *  this is the page's own `apply_focus_preset` command, which is exactly the
 *  route the bootstrap's fetch shim refuses to let a page POST itself. */
export async function applyFocusPresetOnPc(win, id) {
  const core = shellCoreOf(win);
  if (core) return core.invoke("apply_focus_preset", { preset: id });
  const response = await win.fetch(apiUrlFor(win, "/api/work/apply"), {
    method: "POST",
    headers: apiHeadersFor(win, { "Content-Type": "application/json" }),
    body: JSON.stringify(modelApplyBody(id)),
  });
  return readWriteAnswer(response);
}

/** `POST /api/manner {"personality": id}` - ONE field, no card. */
export async function switchPersonalityOnPc(win, id) {
  const core = shellCoreOf(win);
  if (core) return core.invoke("hud_switch_personality", { personality: id });
  const response = await win.fetch(apiUrlFor(win, "/api/manner"), {
    method: "POST",
    headers: apiHeadersFor(win, { "Content-Type": "application/json" }),
    body: JSON.stringify(personalitySwitchBody(id)),
  });
  return readWriteAnswer(response);
}

/* ── 4. The Presets menu (browser only; imported by the page) ─────────────── */

const MENU_ID = "hud-presets-menu";
const STATUS_ID = "hud-presets-status";

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * Mount the "Presets" menu and its dialogs. The page calls this once; the
 * module finds the badge H2's editor already created (and the rail button the
 * page draws) and turns their click into the ONE menu. A page without the
 * editor (an older page) simply has no badge and this mount still wires the
 * rail button.
 */
export function mountHudPresets(options = {}) {
  const doc = options.document || globalThis.document;
  const win = options.window || globalThis.window || globalThis;
  const shellPresent = typeof options.shellPresent === "boolean"
    ? options.shellPresent
    : Boolean(globalThis.__TAURI__ && globalThis.__TAURI__.core);
  const save = options.saveLayout || saveLayout;
  if (!doc || !doc.body) return null;

  let layout = options.layout
    ? normalizeLayout(options.layout)
    : globalThis.__jarvisHudLayout ? normalizeLayout(globalThis.__jarvisHudLayout) : presetLayout(DEFAULT_PRESET_ID);
  let badge = null;
  let menu = null;
  // The owner's left-rail Presets button (2026-10-26): the menu's second door,
  // wired in start(). `focusDoor` is whichever door opened the one menu, so
  // Escape and a second click put focus back where it came from.
  let railDoor = null;
  let focusDoor = null;
  let returnFocus = null;
  let statusLine = null;
  // The last line said in the menu, kept so a re-render (which rebuilds the
  // menu's own line element) does not wipe the answer the owner is reading.
  let statusNote = "";

  // The PC's own two lists (2026-10-27). `null` = not read yet, and the menu
  // says that in words rather than drawing an empty section; `pcBusy` holds the
  // ONE in-flight pick per kind, so a double click cannot send two applies.
  let pcPresets = null;   // GET /api/presets answer (or {available:false, why})
  let pcManner = null;    // GET /api/manner answer (or {available:false, why})
  let pcReading = false;
  let pcError = "";
  let pcBusy = { preset: "", personality: "" };

  // A page-level live line for the menu/dialog results. It is separate from
  // H2's editing bar (which only exists while editing) so a saved layout is
  // reported in normal mode too.
  function ensureStatus() {
    if (statusLine && statusLine.isConnected) return statusLine;
    statusLine = doc.createElement("div");
    statusLine.id = STATUS_ID;
    statusLine.className = "hud-presets-status sr-only";
    statusLine.setAttribute("role", "status");
    statusLine.setAttribute("aria-live", "polite");
    doc.body.appendChild(statusLine);
    return statusLine;
  }

  function announce(text) {
    statusNote = String(text || "");
    const line = ensureStatus();
    line.textContent = statusNote;
    if (menu) {
      const inside = menu.querySelector(".hud-presets-line");
      if (inside) inside.textContent = statusNote;
    }
  }

  /* ── the PC's own presets: two roads, one answer ──────────────────────── */

  // The roads themselves live at the top of this file (`readFocusPresetsOnPc`
  // and friends), so a plain node test can prove what each one sends with a
  // fake window and a fake fetch - no browser needed. Here the mount only
  // keeps the two lists, the one in-flight pick per kind, and the rendering.

  /** Read both lists. The menu keeps whatever it already shows and says it is
   *  reading, so reopening never blanks a list the owner is looking at. */
  function readPcLists() {
    if (pcReading) return;
    pcReading = true;
    pcError = "";
    renderMenu();
    const done = () => {
      pcReading = false;
      renderMenu();
    };
    readFocusPresetsOnPc(win)
      .then((answer) => { pcPresets = answer; })
      .catch((error) => { pcPresets = null; pcError = errorTextOf(error); })
      .then(() => readPersonalitiesOnPc(win))
      .then((answer) => { pcManner = answer; })
      .catch((error) => { pcManner = null; if (!pcError) pcError = errorTextOf(error); })
      .then(done);
  }

  /** ONE model-preset click. The PC's `switch_model` card is raised by the
   *  apply itself, and the apply only answers 2xx once the owner approved it -
   *  so this waits, says what it is waiting for, and then lets a REFETCH of the
   *  PC's own contract decide the mark. A denied card returns a refusal and
   *  marks nothing. */
  async function pickModelPreset(id, title) {
    if (!id || pcBusy.preset) return;
    pcBusy.preset = id;
    renderMenu();
    announce(`Asked the PC to apply ${title || id}. Nothing changes until you answer its approval card.`);
    try {
      await applyFocusPresetOnPc(win, id);
      pcPresets = await readFocusPresetsOnPc(win).catch(() => pcPresets);
      const row = modelPresetRows(pcPresets).find((item) => item.id === id);
      announce(row && row.chosen
        ? `Now using ${row.title}. The PC switched its model and lane.`
        : `The PC answered, but its preset list does not name ${title || id} as chosen - nothing is marked here.`);
    } catch (error) {
      announce(`That did not work: ${errorTextOf(error)}`);
      pcPresets = await readFocusPresetsOnPc(win).catch(() => pcPresets);
    } finally {
      pcBusy.preset = "";
      renderMenu();
    }
  }

  /** ONE personality click: immediate, NO card (wording only - the PC's own
   *  words). The PC's `said` is its switch_ack; the mark comes from the
   *  refetched `personality`, never from this click. */
  async function pickPersonality(id, title) {
    if (!id || pcBusy.personality) return;
    pcBusy.personality = id;
    renderMenu();
    announce(`Switching to ${title || id}...`);
    try {
      const answer = await switchPersonalityOnPc(win, id);
      pcManner = await readPersonalitiesOnPc(win).catch(() => pcManner);
      const said = answer && typeof answer.said === "string" && answer.said
        ? answer.said : `Now speaking as ${title || id}.`;
      announce(said);
    } catch (error) {
      announce(`That did not work: ${errorTextOf(error)}`);
    } finally {
      pcBusy.personality = "";
      renderMenu();
    }
  }

  function adopt(next, note) {
    if (next) {
      layout = normalizeLayout(next);
      try { globalThis.__jarvisHudLayout = layout; } catch { /* ignore */ }
      win.dispatchEvent(new CustomEvent("jarvis:hud-layout", { detail: layout }));
    }
    renderMenu();
    if (note) announce(note);
  }

  async function commit(next, note) {
    const clean = normalizeLayout(next);
    if (!shellPresent && !options.saveLayout) {
      announce("Open the Jarvis desktop app to save a layout.");
      return;
    }
    const answer = await save(clean);
    const saved = answer && answer.layout ? answer.layout : clean;
    adopt(saved, answer && answer.saved
      ? note || `Saved. ${saved.name}.`
      : `Not saved: ${(answer && answer.error) || "the PC refused the write"}.`);
  }

  /* ── the menu itself ─────────────────────────────────────────────────── */

  /** Both doors say whether the ONE menu is open: the "Layout:" badge (H2's)
   *  and the owner's left-rail Presets button (2026-10-26). One menu, two
   *  controls that must never disagree about it. */
  function sayDoors(open) {
    for (const node of [badge, railDoor]) {
      if (node) node.setAttribute("aria-expanded", open ? "true" : "false");
    }
  }

  function closeMenu(returnToDoor) {
    if (!badge) badge = doc.getElementById("hud-layout-badge");
    if (!menu) return;
    menu.hidden = true;
    menu.setAttribute("aria-hidden", "true");
    sayDoors(false);
    // Focus goes back to the control that opened the menu - the rail button
    // when the rail button opened it, never a jump across the window to the
    // badge at the other end of the stage bar.
    const back = focusDoor || badge;
    if (returnToDoor && back) back.focus();
    focusDoor = null;
    returnFocus = null;
  }

  function menuItem(text, hint, onPick, extraClass) {
    const button = el(doc, "button", `hud-presets-item${extraClass ? ` ${extraClass}` : ""}`, text);
    button.type = "button";
    button.setAttribute("role", "menuitem");
    if (hint) {
      button.title = hint;
      button.setAttribute("aria-label", `${text}. ${hint}`);
    }
    button.addEventListener("click", async () => {
      try {
        await onPick();
      } catch (error) {
        announce(`That did not work: ${error && error.message ? error.message : error}`);
      }
    });
    return button;
  }

  function section(heading) {
    const box = el(doc, "div", "hud-presets-group");
    const title = el(doc, "p", "hud-presets-head", heading);
    title.setAttribute("role", "presentation");
    box.appendChild(title);
    return box;
  }

  /** One grey plain-words line inside a section (never a control). */
  function note(text, className) {
    return el(doc, "p", className || "hud-presets-empty", text);
  }

  /** A one-line placeholder for a section whose read has not landed yet. */
  function loadingNote(what) {
    return note(pcError
      ? `The PC did not list ${what} (${pcError}).`
      : (pcReading ? `Reading ${what} from the PC...` : `Open the menu again to read ${what}.`));
  }

  /** The five local-AI focus presets (GET /api/presets). A row is marked
   *  chosen ONLY from the PC's own `chosen_preset`, and the section says the
   *  card rule in words before any click. */
  function renderModelPresets() {
    const group = section("Model presets");
    if (pcPresets === null) {
      group.appendChild(loadingNote("its presets"));
      return group;
    }
    if (pcPresets.available === false) {
      group.appendChild(note(pcPresets.why || "This PC's Jarvis cannot list presets yet."));
      return group;
    }
    const rows = modelPresetRows(pcPresets);
    if (!rows.length) {
      group.appendChild(note("The PC listed no presets."));
      return group;
    }
    group.appendChild(note("Applying one asks the PC for ONE approval card - nothing is chosen until you answer it."));
    for (const row of rows) {
      const asking = pcBusy.preset === row.id;
      const button = menuItem(
        `${row.title}${row.chosen ? " (chosen)" : ""}${asking ? " - asking..." : ""}`,
        row.focus,
        () => { pickModelPreset(row.id, row.title); },
      );
      if (row.chosen) button.setAttribute("aria-current", "true");
      // The id in the DOM, so a person tabbing through and the tests both see
      // which row a button is - never read back as the chosen state, which is
      // the PC's answer alone.
      button.dataset.preset = row.id;
      if (pcBusy.preset && !asking) button.disabled = true;
      group.appendChild(button);
    }
    return group;
  }

  /** Jarvis's nine personalities (GET /api/manner), then the owner's own
   *  "My personalities" as their own section when there are any. A click is
   *  immediate - no card - and the mark comes from the PC's own `personality`. */
  function renderPersonalities() {
    const group = section("Personality");
    if (pcManner === null) {
      group.appendChild(loadingNote("its personalities"));
      return group;
    }
    if (pcManner.available === false) {
      group.appendChild(note(pcManner.why || "This PC's Jarvis cannot list its personalities yet."));
      return group;
    }
    const { rows } = personalityRows(pcManner);
    const builtIns = rows.filter((row) => !row.custom);
    if (!builtIns.length) {
      group.appendChild(note("The PC listed no personalities."));
      return group;
    }
    group.appendChild(note("Switching is immediate: it changes how Jarvis talks and asks for no card."));
    for (const row of builtIns) {
      const asking = pcBusy.personality === row.id;
      const button = menuItem(
        `${row.title}${row.current ? " (current)" : ""}${asking ? " - switching..." : ""}`,
        row.hint,
        () => { pickPersonality(row.id, row.title); },
      );
      if (row.current) button.setAttribute("aria-current", "true");
      button.dataset.personality = row.id;
      if (pcBusy.personality && !asking) button.disabled = true;
      group.appendChild(button);
    }
    return group;
  }

  /** The owner's saved personalities, only when the PC says there are any. */
  function renderMyPersonalities() {
    if (pcManner === null || pcManner.available === false) return null;
    const { rows } = personalityRows(pcManner);
    const own = rows.filter((row) => row.custom);
    if (!own.length) return null;
    const group = section("My personalities");
    for (const row of own) {
      const asking = pcBusy.personality === row.id;
      const button = menuItem(
        `${row.title}${row.current ? " (current)" : ""}${asking ? " - switching..." : ""}`,
        row.hint,
        () => { pickPersonality(row.id, row.title); },
      );
      if (row.current) button.setAttribute("aria-current", "true");
      button.dataset.personality = row.id;
      if (pcBusy.personality && !asking) button.disabled = true;
      group.appendChild(button);
    }
    return group;
  }

  function renderMenu() {
    if (!menu) return;
    const scroll = menu.querySelector(".hud-presets-scroll");
    if (!scroll) return;
    scroll.textContent = "";
    // The owner's presets first (2026-10-27): the five local-AI focus presets
    // and the personalities, then the saved HUD layouts the menu always had.
    // Every action below is unchanged - this only adds sections above them.
    scroll.appendChild(renderModelPresets());
    scroll.appendChild(renderPersonalities());
    const ownPersonalities = renderMyPersonalities();
    if (ownPersonalities) scroll.appendChild(ownPersonalities);
    const builtIns = section("Built-in layouts");
    for (const preset of PRESETS) {
      const info = presetInfo(preset.id);
      const current = layout.id === preset.id;
      builtIns.appendChild(menuItem(
        `${info ? info.label : preset.id}${current ? " (current)" : ""}`,
        info ? info.blurb : "",
        () => closeMenu(false) || commit(normalizeLayout({
          ...presetLayout(preset.id),
          user_presets: userLayouts(layout),
        }), `Layout: ${info ? info.label : preset.id}.`),
      ));
    }
    scroll.appendChild(builtIns);

    const mine = section("My layouts");
    const library = userLayouts(layout);
    if (!library.length) {
      mine.appendChild(el(doc, "p", "hud-presets-empty",
        "No saved layouts yet. Press Duplicate to keep this arrangement."));
    }
    for (const entry of library) {
      const row = el(doc, "div", "hud-presets-row");
      const choose = menuItem(
        `${entry.name}${layout.id === entry.id ? " (current)" : ""}`,
        `Use the layout "${entry.name}"`,
        () => closeMenu(false) || commit(applyUserLayout(layout, entry.id), `Layout: ${entry.name}.`),
      );
      const rename = el(doc, "button", "hud-presets-small", "Rename");
      rename.type = "button";
      rename.setAttribute("role", "menuitem");
      rename.setAttribute("aria-label", `Rename ${entry.name}`);
      rename.addEventListener("click", () => {
        closeMenu(false);
        openRename(entry.id);
      });
      const remove = el(doc, "button", "hud-presets-small hud-presets-danger", "Delete");
      remove.type = "button";
      remove.setAttribute("role", "menuitem");
      remove.setAttribute("aria-label", `Delete ${entry.name}`);
      remove.addEventListener("click", () => {
        closeMenu(false);
        openDelete(entry.id);
      });
      row.append(choose, rename, remove);
      mine.appendChild(row);
    }
    scroll.appendChild(mine);

    const actions = section("This layout");
    actions.appendChild(menuItem("Duplicate to My layouts", "Keep this arrangement as your own copy",
      () => { closeMenu(false); duplicateActive(); }));
    actions.appendChild(menuItem(`Reset to ${(presetInfo(layout.base_preset) || { label: "the shipped layout" }).label}`,
      "Put back the shipped layout, keeping your saved layouts",
      () => { closeMenu(false); resetActive(); }));
    actions.appendChild(menuItem("Export / Import JSON…", "Move a layout by copy and paste",
      () => { closeMenu(false); openTransfer("export"); }));
    scroll.appendChild(actions);

    const line = el(doc, "p", "hud-presets-line", statusNote);
    line.setAttribute("role", "status");
    line.setAttribute("aria-live", "polite");
    scroll.appendChild(line);
  }

  function ensureMenu() {
    if (menu && menu.isConnected) return menu;
    menu = doc.createElement("div");
    menu.id = MENU_ID;
    menu.className = "hud-presets-menu";
    menu.hidden = true;
    menu.setAttribute("role", "menu");
    menu.setAttribute("aria-label", "Presets");
    const head = el(doc, "p", "hud-presets-title", "Presets");
    const scroll = el(doc, "div", "hud-presets-scroll");
    const close = el(doc, "button", "hud-presets-close", "Close");
    close.type = "button";
    close.setAttribute("aria-label", "Close the presets menu");
    close.addEventListener("click", () => closeMenu(true));
    menu.append(head, scroll, close);
    doc.body.appendChild(menu);
    menu.addEventListener("keydown", onMenuKeyDown);
    doc.addEventListener("pointerdown", (event) => {
      if (!menu || menu.hidden) return;
      const target = event.target;
      // Both DOORS are outside the menu but must not dismiss it: the click is
      // the toggle, and dismissing on pointerdown first would turn a second
      // click on either door into close-then-reopen. The rail button is a door
      // too (2026-10-26), so it is exempt exactly as the badge is.
      if (!railDoor) railDoor = doc.getElementById("rail-presets");
      if (menu.contains(target)
        || (badge && badge.contains(target))
        || (railDoor && railDoor.contains(target))) return;
      closeMenu(false);
    }, true);
    return menu;
  }

  function onMenuKeyDown(event) {
    if (!menu || menu.hidden) return;
    const items = [...menu.querySelectorAll('[role="menuitem"]')].filter((node) => !node.disabled);
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu(true);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const at = items.indexOf(doc.activeElement);
      const step = event.key === "ArrowDown" ? 1 : -1;
      const next = items[(at + step + items.length) % items.length] || items[0];
      if (next) next.focus();
    }
  }

  function openMenu(anchor) {
    // A click can arrive before the 100 ms badge poll has run; resolve the
    // badge on demand so `aria-expanded` and the menu position are never lost.
    if (!badge) badge = doc.getElementById("hud-layout-badge");
    if (!railDoor) railDoor = doc.getElementById("rail-presets");
    ensureMenu();
    renderMenu();
    // Read the PC's two lists each time the menu opens: the chosen preset and
    // the current personality can be changed from the Settings window or the
    // bar, and this menu must never show yesterday's answer as today's. The
    // cached copy stays on screen while the read is in flight.
    readPcLists();
    // Which control opened it decides where the ONE menu appears: under the
    // badge at the top right (no anchor, exactly as before), or beside the
    // rail button when the rail button asked (2026-10-26) - so a click in the
    // left column is answered in the left column, not at the far corner.
    focusDoor = (anchor && anchor.getBoundingClientRect) ? anchor : badge;
    const rect = focusDoor
      ? focusDoor.getBoundingClientRect()
      : { left: 16, right: 16, bottom: 40 };
    const left = focusDoor === badge
      ? Math.max(8, Math.min(win.innerWidth - 360, rect.left))
      : Math.max(8, Math.min(win.innerWidth - 360, rect.right + 8));
    menu.style.left = `${left}px`;
    menu.style.top = `${Math.round(rect.bottom + 6)}px`;
    menu.hidden = false;
    menu.setAttribute("aria-hidden", "false");
    sayDoors(true);
    const first = menu.querySelector('[role="menuitem"]');
    if (first) first.focus();
  }

  function enhanceBadge() {
    if (!badge || badge.dataset.hudPresets === "1") return;
    badge.dataset.hudPresets = "1";
    badge.setAttribute("aria-haspopup", "menu");
    badge.setAttribute("aria-expanded", "false");
    // The CLICK is owned by H2's editor, which dispatches
    // `jarvis:hud-presets-open` (one door, so a click cannot toggle twice).
    // This handler only makes the badge keyboard-openable.
    badge.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || (event.key === "Enter" && !menu?.hidden)) {
        event.preventDefault();
        openMenu();
      }
    });
  }

  /* ── dialogs: rename, delete, export/import ──────────────────────────── */

  function dialogShell(titleText) {
    const wrapper = doc.createElement("dialog");
    wrapper.className = "hud-presets-dialog";
    const form = el(doc, "div", "hud-presets-dialog-body");
    const title = el(doc, "h2", "hud-presets-dialog-title", titleText);
    const line = el(doc, "p", "hud-presets-dialog-line");
    line.setAttribute("role", "status");
    const buttons = el(doc, "div", "hud-presets-dialog-actions");
    form.append(title, line, buttons);
    wrapper.appendChild(form);
    doc.body.appendChild(wrapper);
    return { wrapper, form, title, line, buttons };
  }

  function closeDialog(wrapper) {
    try { wrapper.close(); } catch { wrapper.remove(); }
    wrapper.remove();
    if (returnFocus && returnFocus.isConnected) returnFocus.focus();
    returnFocus = null;
  }

  function showDialog(wrapper) {
    if (typeof wrapper.showModal === "function") {
      try { wrapper.showModal(); return; } catch { /* fall through */ }
    }
    wrapper.setAttribute("open", "");
  }

  function openRename(id) {
    const entry = userLayouts(layout).find((item) => item.id === id);
    if (!entry) return;
    returnFocus = badge;
    ensureMenu();
    const { wrapper, form, line, buttons } = dialogShell("Rename layout");
    const label = el(doc, "label", "hud-presets-label", "Name");
    const input = doc.createElement("input");
    input.type = "text";
    input.maxLength = 60;
    input.value = entry.name;
    input.id = "hud-presets-rename";
    label.htmlFor = input.id;
    const saveButton = el(doc, "button", "hud-presets-save", "Save name");
    saveButton.type = "button";
    const cancel = el(doc, "button", "ghost", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => closeDialog(wrapper));
    saveButton.addEventListener("click", async () => {
      const renamed = renameUserLayout(layout, id, input.value);
      if (renamed.refused) { line.textContent = renamed.refused; return; }
      closeDialog(wrapper);
      await commit(renamed.doc, `Renamed to "${input.value.trim()}".`);
    });
    wrapper.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); closeDialog(wrapper); }
    });
    form.insertBefore(label, line);
    form.insertBefore(input, line);
    buttons.append(saveButton, cancel);
    showDialog(wrapper);
    input.focus();
    input.select();
  }

  function openDelete(id) {
    const entry = userLayouts(layout).find((item) => item.id === id);
    if (!entry) return;
    returnFocus = badge;
    ensureMenu();
    const { wrapper, line, buttons } = dialogShell(`Delete "${entry.name}"?`);
    line.textContent = "This cannot be undone. The layout is removed from this PC.";
    const remove = el(doc, "button", "hud-presets-danger", "Delete it");
    remove.type = "button";
    const cancel = el(doc, "button", "ghost", "Keep it");
    cancel.type = "button";
    cancel.addEventListener("click", () => closeDialog(wrapper));
    remove.addEventListener("click", async () => {
      closeDialog(wrapper);
      await commit(deleteUserLayout(layout, id), `Deleted "${entry.name}".`);
    });
    wrapper.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); closeDialog(wrapper); }
    });
    buttons.append(remove, cancel);
    showDialog(wrapper);
    cancel.focus();
  }

  function openTransfer(mode) {
    returnFocus = badge;
    ensureMenu();
    const { wrapper, form, line, buttons } = dialogShell("Move a layout by copy and paste");
    line.textContent = "The HUD keeps its locked-down page: there is no file picker and no network. Copy this text to save a layout, or paste one to bring it in.";

    const exportLabel = el(doc, "p", "hud-presets-label", "This layout, as JSON (read only)");
    const out = doc.createElement("textarea");
    out.readOnly = true;
    out.id = "hud-presets-export-json";
    out.rows = 7;
    out.className = "hud-presets-json";
    out.value = exportLayoutJson(layout);
    const copy = el(doc, "button", "ghost", "Copy JSON");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(out.value);
          line.textContent = "Copied. Paste it anywhere safe.";
          return;
        }
      } catch { /* fall through to the honest fallback */ }
      out.focus();
      out.select();
      line.textContent = "Selected. Press Ctrl+C to copy.";
    });

    const importLabel = el(doc, "p", "hud-presets-label", "Paste a layout to import");
    const input = doc.createElement("textarea");
    input.rows = 7;
    input.id = "hud-presets-import-json";
    input.className = "hud-presets-json";
    input.placeholder = "Paste the JSON text here";
    const importButton = el(doc, "button", "hud-presets-save", "Validate & import");
    importButton.type = "button";
    importButton.addEventListener("click", async () => {
      const checked = importLayoutText(input.value);
      if (!checked.ok) { line.textContent = checked.error; return; }
      const adopted = adoptImportedLayout(checked.doc, layout);
      if (adopted.refused) { line.textContent = adopted.refused; return; }
      closeDialog(wrapper);
      await commit(adopted.doc, `Imported "${adopted.doc.name}". It is now your layout.`);
    });
    const cancel = el(doc, "button", "ghost", "Close");
    cancel.type = "button";
    cancel.addEventListener("click", () => closeDialog(wrapper));
    wrapper.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); closeDialog(wrapper); }
    });

    form.insertBefore(exportLabel, line);
    form.insertBefore(out, line);
    form.insertBefore(copy, line);
    form.insertBefore(importLabel, line);
    form.insertBefore(input, line);
    buttons.append(importButton, cancel);
    showDialog(wrapper);
    (mode === "import" ? input : out).focus();
  }

  async function duplicateActive() {
    const result = duplicateLayout(layout);
    if (result.refused) { announce(result.refused); return; }
    await commit(result.doc, `Saved as "${result.doc.name}".`);
  }

  async function resetActive() {
    const base = presetLayout(layout.base_preset);
    await commit(normalizeLayout({ ...base, user_presets: userLayouts(layout) }),
      `Reset to ${(presetInfo(layout.base_preset) || { label: "the shipped layout" }).label}.`);
  }

  /* ── mount ───────────────────────────────────────────────────────────── */

  function start() {
    const tryBadge = () => {
      const found = doc.getElementById("hud-layout-badge");
      if (found && !found.dataset.hudPresets) {
        badge = found;
        enhanceBadge();
      }
    };
    tryBadge();
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      tryBadge();
      if (badge || tries >= 50) clearInterval(timer);
    }, 100);
    win.addEventListener("jarvis:hud-layout", (event) => {
      if (event && event.detail && !options.frozen) {
        layout = normalizeLayout(event.detail);
        renderMenu();
      }
    });
    win.addEventListener("jarvis:hud-layout-saved", (event) => {
      if (event && event.detail) {
        layout = normalizeLayout(event.detail);
        renderMenu();
      }
    });
    // H2's editor owns the badge element; it asks the module that owns the
    // menu to open it (one badge, one menu, no duplicate click handlers).
    // The owner's left-rail Presets button (2026-10-26) dispatches the SAME
    // event, carrying itself as the anchor, so both doors go through this one
    // listener and there is still exactly one Layouts menu.
    win.addEventListener("jarvis:hud-presets-open", (event) => {
      if (menu && !menu.hidden) closeMenu(true);
      else openMenu(event && event.detail ? event.detail.anchor : null);
    });
    // The door itself: a click on the rail button opens (or closes) the same
    // menu the badge opens, beside the button that was clicked. The dataset
    // mark stops a second mount wiring a second handler - two handlers would
    // toggle twice, which reads as "the button does nothing".
    railDoor = doc.getElementById("rail-presets");
    if (railDoor && railDoor.dataset.hudPresets !== "1") {
      railDoor.dataset.hudPresets = "1";
      railDoor.addEventListener("click", () => {
        win.dispatchEvent(new CustomEvent("jarvis:hud-presets-open", {
          detail: { anchor: railDoor },
        }));
      });
    }
    const controller = {
      get layout() { return layout; },
      open: openMenu,
      close: () => closeMenu(false),
      adopt,
      duplicate: duplicateActive,
      reset: resetActive,
      exportJson: () => exportLayoutJson(layout),
      menu: () => menu,
    };
    try { globalThis.__jarvisHudPresets = controller; } catch { /* ignore */ }
    return controller;
  }

  return start();
}

export { MENU_ID, STATUS_ID };
