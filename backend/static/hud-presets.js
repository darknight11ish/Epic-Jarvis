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
 * THE STUDIO DOCK'S "CURRENT MODELS" PANEL IS THE SECOND MENU HERE (the owner's
 * ask, 2026-10-26: "under the button on the jarvis hud that says auto, theres
 * several options including bulk, critic, escalate, can you just get rid of this
 * button and replace it with a button that says \"Current Models\" and clicking
 * it will show what models are being used and or loaded on jarvis?"). Since
 * 2026-10-27 it is opened by the TOP-RIGHT MODEL NAME itself (the owner: "the
 * model name ... must become a BUTTON that opens the current-models menu ...
 * DELETE the separate Current Models button"), and Ambient's top-left pill
 * carries a second door to the same panel, because the stage bar's chip is
 * hidden in that shell. The panel is a READ-ONLY view: `GET /api/models`'s
 * `current`/`previous` and its `offload.models` (what is really in memory),
 * `/api/status`'s `default_model` when it differs, and `/api/presets`'s chosen
 * preset. Its route buttons are built from the page's own `#lanes .lane`
 * buttons - the one source of truth - so no lane name is copied here.
 *
 * THE CLOUD SECTION (2026-10-27, the owner's ask: a "Cloud" preset beside
 * coder/general/fast, listing "the API providers the PC has connected"). It is
 * drawn ONLY from the PC's own `GET /api/presets` answer's `cloud` object
 * (`provider`, `providers[]`, `escalate{on,why}`); a PC that does not send one
 * gets no row and no invented provider. Picking a provider is an APPLY, the
 * same road and the same ONE approval card as every other preset - it changes
 * where the owner's words go, so it is a loosening - and nothing is marked
 * chosen until a REFETCH of the PC's answer names it. A service with no key
 * saved is NOT a button: it shows the PC's own `key_line` and says to add the
 * key on the PC, because a key is never typed, pasted or sent from an app
 * (rule 3).
 *
 * THE ESCALATE CHECKBOX is the owner's switch: "Escalate to the cloud when the
 * work is too complex". Its tick comes from `cloud.escalate.on` and NEVER from
 * the click; a click posts ONCE (`POST /api/work/cloud-escalate {"on":…}`,
 * through the HUD's own `hud_cloud_escalate` command in the shell) and the
 * refetched answer decides. ON is a loosening and the PC raises its ONE card;
 * OFF is instant. A refused card, an expired one or a failed read always clears
 * this menu's busy state, so the owner is never left with dead rows.
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
 *
 * TWO FACTS DECIDE WHETHER A ROW CAN BE APPLIED, and both are the PC's:
 * `heavy_mode` (its model needs both cards as one pooled lane, which this PC
 * refuses until that lane support lands - the same refusal the phone and the
 * older focus-preset module honour) and `pending` (the PC is still preparing
 * it). Carrying them here is the fix for the 2026-10-27 contract audit's F1:
 * the menu offered Coding, the PC always answered 409, and nothing said why.
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
      heavy: row.heavy_mode === true,
      pending: row.pending === true,
    }));
}

/**
 * The personalities the PC offers (`GET /api/manner`): its nine built-ins in
 * its own order, then the owner's saved "My personalities" when there are
 * any. The PC's `personalities` list already carries the saved ones too -
 * each marked `builtin: false` (`jarvis_manner.py` `all_personalities`) - so
 * the split is that flag, and a saved personality is never drawn twice.
 * `current` is the PC's own answer, never the last click. Pure for the same
 * reason as above; a row that carries no id or no name is dropped rather than
 * drawn as an unclickable blank.
 */
export function personalityRows(payload) {
  const body = payload && typeof payload === "object" ? payload : {};
  const current = typeof body.personality === "string" ? body.personality : "";
  const listed = Array.isArray(body.personalities) ? body.personalities : [];
  const builtIn = listed.filter((row) => !(row && typeof row === "object" && row.builtin === false));
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

/** The body one model-preset click sends: the preset's own id, plus the ONE
 *  provider id when the Cloud preset asks for one (2026-10-27). With no
 *  provider the body is byte-for-byte what every preset click sent before, so
 *  an older PC and the five local presets are untouched. */
export function modelApplyBody(id, provider) {
  const body = { preset: String(id || "") };
  const pid = typeof provider === "string" ? provider.trim() : "";
  if (pid) body.provider = pid;
  return body;
}

/** The one plain-words line the PC's own contract says a heavy preset cannot
 *  be applied. VERBATIM the phone's (`FocusPresets.kt:66-68`), because it is
 *  the same refusal and the two apps must not describe it differently. */
export const HEAVY_PRESET_WORDS = "This preset needs both cards at once as one "
  + "pooled lane. Your PC refuses heavy mode until that lane support lands, so "
  + "it cannot be used from here yet.";

const cloudText = (value) => (typeof value === "string" ? value.trim() : "");

/**
 * The API services the PC says it is connected to, from `GET /api/presets`'s
 * `cloud` object. PURE, and it invents nothing: a PC that sends no `cloud`
 * object gets an empty list and the menu draws no providers at all.
 *
 * The chosen one is `cloud.provider` - the PC's own word for which service the
 * cloud lane uses. A per-row `chosen` flag is accepted too (the shape the
 * plan wrote first), but the container key wins when both are present, and a
 * click here never marks anything.
 */
export function providerRows(payload) {
  const body = payload && typeof payload === "object" ? payload : {};
  const cloud = body.cloud && typeof body.cloud === "object" ? body.cloud : null;
  if (!cloud) return [];
  const listed = Array.isArray(cloud.providers) ? cloud.providers : [];
  const named = cloudText(cloud.provider);
  const rows = listed
    .filter((row) => row && typeof row === "object" && typeof row.id === "string" && row.id)
    .map((row) => {
      const money = row.money && typeof row.money === "object" ? row.money : null;
      return {
        id: row.id,
        name: cloudText(row.name) || cloudText(row.company) || row.id,
        company: cloudText(row.company),
        host: cloudText(row.host),
        model: cloudText(row.model),
        keySaved: row.key_saved === true,
        ready: row.ready === true,
        why: cloudText(row.why),
        chosen: false,
        money: money ? {
          limit: cloudText(money.limit),
          left: cloudText(money.left),
          reached: money.reached === true,
        } : null,
        keyLine: cloudText(row.key_line),
        keyWhere: cloudText(row.key_where),
      };
    });
  const winner = named || cloudText((listed.find((row) => row && row.chosen === true) || {}).id);
  for (const row of rows) row.chosen = Boolean(winner) && row.id === winner;
  return rows;
}

/** The PC's own escalate switch: `{on, why}` from the same answer. ON only
 *  when the PC sent a literal `true`; anything unreadable is OFF. */
export function cloudEscalate(payload) {
  const body = payload && typeof payload === "object" ? payload : {};
  const cloud = body.cloud && typeof body.cloud === "object" ? body.cloud : null;
  const escalate = cloud && cloud.escalate && typeof cloud.escalate === "object"
    ? cloud.escalate : null;
  return {
    on: Boolean(escalate && escalate.on === true),
    why: cloudText(escalate && escalate.why),
  };
}

/**
 * The "Cloud" row itself, or null when the PC does not offer one. It sits
 * beside the five local presets, with the chosen service's own name when the
 * PC names one; `chosen` comes from `cloud.provider` alone.
 */
export function cloudPresetRow(payload) {
  const body = payload && typeof payload === "object" ? payload : {};
  if (!body.cloud || typeof body.cloud !== "object") return null;
  const providers = providerRows(payload);
  const chosenRow = providers.find((row) => row.chosen) || null;
  return {
    id: "cloud",
    title: "Cloud",
    chosen: Boolean(chosenRow),
    provider: chosenRow ? chosenRow.name : "",
    providers,
    escalate: cloudEscalate(payload),
  };
}

/** The body one escalate click sends: ONE boolean, nothing else. */
export function cloudEscalateBody(on) {
  return { on: on === true };
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
 *  route the bootstrap's fetch shim refuses to let a page POST itself. A
 *  provider id rides along for the Cloud preset only, and the command sends
 *  the `provider` key only when one was given. */
export async function applyFocusPresetOnPc(win, id, provider) {
  const body = modelApplyBody(id, provider);
  const core = shellCoreOf(win);
  if (core) return core.invoke("apply_focus_preset", body);
  const response = await win.fetch(apiUrlFor(win, "/api/work/apply"), {
    method: "POST",
    headers: apiHeadersFor(win, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return readWriteAnswer(response);
}

/** `POST /api/work/cloud-escalate {"on": true|false}` - the owner's escalate
 *  switch (2026-10-27). ON is a loosening and the PC raises its ONE card; OFF
 *  is instant. In the shell this is the HUD's own narrow `hud_cloud_escalate`
 *  command; a plain browser posts the same one-field body itself. */
export async function setCloudEscalateOnPc(win, on) {
  const body = cloudEscalateBody(on);
  const core = shellCoreOf(win);
  if (core) return core.invoke("hud_cloud_escalate", { on: body.on });
  const response = await win.fetch(apiUrlFor(win, "/api/work/cloud-escalate"), {
    method: "POST",
    headers: apiHeadersFor(win, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
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
  let pcBusy = { preset: "", personality: "", escalate: false, provider: "" };
  // Is the Cloud section's provider submenu open? ONE at a time, and Escape
  // closes it before the menu (2026-10-27).
  let cloudOpen = false;

  /** Tell the page what the PC says about its escalate switch. The chat body's
   *  `cloud_yes` is decided from this, so the page writes it only when the PC's
   *  own answer said on - never from a click in this menu. */
  function sayCloudState() {
    const state = cloudEscalate(pcPresets);
    try {
      win.dispatchEvent(new CustomEvent("jarvis:cloud-escalate", { detail: state }));
    } catch { /* a window without CustomEvent (a fake one in a node test) */ }
    return state;
  }

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
      .then((answer) => { pcPresets = answer; sayCloudState(); })
      .catch((error) => {
        pcPresets = null;
        pcError = errorTextOf(error);
        sayCloudState();          // a failed read is not a "yes"
      })
      .then(() => readPersonalitiesOnPc(win))
      .then((answer) => { pcManner = answer; })
      .catch((error) => { pcManner = null; if (!pcError) pcError = errorTextOf(error); })
      .then(done);
  }

  /** ONE model-preset click. The PC's `switch_model` card is raised by the
   *  apply itself, and the apply only answers 2xx once the owner approved it -
   *  so this waits, says what it is waiting for, and then lets a REFETCH of the
   *  PC's own contract decide the mark. A denied card returns a refusal and
   *  marks nothing.
   *
   *  `provider` is only ever given by the Cloud section: picking a service is
   *  the SAME apply with one more field (2026-10-27). */
  async function pickModelPreset(id, title, provider) {
    if (!id || pcBusy.preset) return;
    pcBusy.preset = id;
    pcBusy.provider = provider || "";
    renderMenu();
    announce(provider
      ? `Asked the PC to use ${title || id} for the cloud. Nothing changes until you answer its approval card.`
      : `Asked the PC to apply ${title || id}. Nothing changes until you answer its approval card.`);
    try {
      await applyFocusPresetOnPc(win, id, provider);
      pcPresets = await readFocusPresetsOnPc(win).catch(() => pcPresets);
      sayCloudState();
      const row = modelPresetRows(pcPresets).find((item) => item.id === id);
      const chosen = provider
        ? providerRows(pcPresets).some((item) => item.chosen && item.id === provider)
        : Boolean(row && row.chosen);
      announce(chosen
        ? (provider
          ? `Now using ${title || id} for the cloud when it answers there.`
          : `Now using ${row.title}. The PC switched its model and lane.`)
        : `The PC answered, but its own list does not name ${title || id} as chosen - nothing is marked here.`);
    } catch (error) {
      announce(`That did not work: ${errorTextOf(error)}`);
      pcPresets = await readFocusPresetsOnPc(win).catch(() => pcPresets);
      sayCloudState();
    } finally {
      // Cleared on EVERY end: a refused card, an expired one and a failed read
      // all leave the menu usable (2026-10-27 HUD audit P2-3). Only the row
      // that is actually waiting is disabled, and only while it waits.
      pcBusy.preset = "";
      pcBusy.provider = "";
      renderMenu();
    }
  }

  /** ONE provider click: apply the Cloud preset with this service. It is the
   *  same ONE card every preset raises, and it changes where the owner's words
   *  go, so it is never instant and never marked from here. */
  async function pickCloudProvider(row) {
    if (!row || !row.id || !row.keySaved || !row.ready) return;
    await pickModelPreset("cloud", row.name, row.id);
  }

  /** ONE escalate click: post ONCE, then let the PC's own answer draw the box.
   *  ON raises the PC's ONE card; OFF is instant. The tick is NEVER set from
   *  this click - it is re-read from the refetched `cloud.escalate.on`, so a
   *  refused or expired card leaves it off and the owner can try again. */
  async function setCloudEscalate(next) {
    if (pcBusy.escalate) return;
    pcBusy.escalate = true;
    renderMenu();
    announce(next
      ? "Asked the PC to escalate hard questions to the cloud. Nothing changes until you answer its approval card."
      : "Asked the PC to stop escalating to the cloud.");
    try {
      const answer = await setCloudEscalateOnPc(win, next === true);
      pcPresets = await readFocusPresetsOnPc(win).catch(() => pcPresets);
      const state = sayCloudState();
      const said = answer && typeof answer.said === "string" ? answer.said : "";
      if (state.on === (next === true)) {
        announce(said || (state.on
          ? "Escalating is on: a hard question may go to the cloud. Your monthly limit still applies."
          : "Escalating is off. Every question stays on this PC."));
      } else if (answer && answer.waiting === true) {
        announce(said || "The PC is waiting for you to answer its card - nothing has changed yet.");
      } else {
        announce(said || `The PC did not switch it ${next ? "on" : "off"} - nothing is marked here.`);
      }
    } catch (error) {
      announce(`That did not work: ${errorTextOf(error)}`);
      pcPresets = await readFocusPresetsOnPc(win).catch(() => pcPresets);
      sayCloudState();
    } finally {
      pcBusy.escalate = false;
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
    if (!menu) return null;
    menu.hidden = true;
    menu.setAttribute("aria-hidden", "true");
    cloudOpen = false;
    sayDoors(false);
    // Focus goes back to the control that opened the menu - the rail button
    // when the rail button opened it, never a jump across the window to the
    // badge at the other end of the stage bar.
    const back = focusDoor || badge;
    if (returnToDoor && back) back.focus();
    focusDoor = null;
    returnFocus = null;
    // The caller may need the door for a dialog's own focus return (P2-6):
    // `closeMenu(false)` used to throw that identity away, so Rename/Delete/
    // Export always sent focus to the badge at the other end of the window.
    return back;
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

  /** The five local-AI focus presets (GET /api/presets), plus the Cloud preset
   *  beside them when the PC offers one. A row is marked chosen ONLY from the
   *  PC's own `chosen_preset` / `cloud.provider`, and the section says the card
   *  rule in words before any click.
   *
   *  A HEAVY PRESET IS NOT A BUTTON (2026-10-27, contract audit F1): the PC
   *  always answers 409 for it, so the row says so in the PC's own sentence
   *  instead of offering a dead action. The same rule the phone follows. */
  function renderModelPresets() {
    // "Focus presets" is the ONE name this feature has everywhere else - the
    // phone's title, Settings, the bar and JARVIS-API (2026-10-27 audit F5).
    const group = section("Focus presets");
    if (pcPresets === null) {
      group.appendChild(loadingNote("its focus presets"));
      return group;
    }
    // The PC's own reason key is `error` (a 503 body); `why` is read too, for
    // the older shape (2026-10-27 audit F8).
    if (pcPresets.available === false) {
      group.appendChild(note(pcPresets.error || pcPresets.why
        || "This PC's Jarvis cannot list presets yet."));
      return group;
    }
    const rows = modelPresetRows(pcPresets);
    const cloud = cloudPresetRow(pcPresets);
    if (!rows.length && !cloud) {
      group.appendChild(note("The PC listed no presets."));
      return group;
    }
    group.appendChild(note("Applying one asks the PC for ONE approval card - nothing is chosen until you answer it."));
    for (const row of rows) {
      const asking = pcBusy.preset === row.id;
      if (row.heavy) {
        // Unavailable, in the PC's own words - never a button that always fails.
        const dead = el(doc, "p", "hud-presets-empty", `${row.title} - ${HEAVY_PRESET_WORDS}`);
        dead.dataset.preset = row.id;
        group.appendChild(dead);
        continue;
      }
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
      // A waiting row is NOT disabled: the click handler's own guard already
      // refuses a second send, and a `disabled` button cannot keep the
      // keyboard focus across the re-render that follows - which is exactly
      // how the owner's Space press ended up on <body> (P2-2). Only the
      // label says it is waiting.
      group.appendChild(button);
    }
    if (cloud) group.appendChild(renderCloudRow(cloud));
    return group;
  }

  /** The one "Cloud" row, after the five. It does NOT apply anything: it opens
   *  the provider submenu. The mark is the PC's `cloud.provider`. */
  function renderCloudRow(cloud) {
    const asking = pcBusy.preset === "cloud";
    const button = menuItem(
      `Cloud${cloud.provider ? ` - ${cloud.provider}` : ""}${cloud.chosen ? " (chosen)" : ""}`
        + `${asking ? " - asking..." : ""}${cloudOpen ? " - open" : ""}`,
      cloud.providers.length
        ? "Choose the API service the cloud turns use"
        : "No API service is connected on this PC yet",
      () => { toggleCloud(!cloudOpen); },
    );
    button.setAttribute("aria-haspopup", "true");
    button.setAttribute("aria-expanded", cloudOpen ? "true" : "false");
    button.setAttribute("aria-controls", "hud-presets-cloud-menu");
    button.dataset.cloudAction = "open";
    if (cloud.chosen) button.setAttribute("aria-current", "true");
    return button;
  }

  function providerState(row) {
    if (row.chosen) return "chosen";
    // The PC's own sentence whenever it sent one, never this page's guess.
    if (!row.keySaved) return row.why || "no key saved on this PC";
    if (row.ready) {
      return row.money && row.money.limit ? `ready - ${row.money.limit} a month` : "ready";
    }
    return row.why || "this PC cannot use it yet";
  }

  /** The Cloud section's provider submenu. Rendered beside the menu (not inside
   *  another group) so `menu.json`-style readers see one flat list, and hidden
   *  until the Cloud row is pressed. Nothing here sends anything: a row that is
   *  not usable is not a button at all. */
  function renderCloudSubmenu(cloud) {
    let box = menu.querySelector("#hud-presets-cloud-menu");
    if (!box) {
      box = el(doc, "div", "hud-presets-submenu");
      box.id = "hud-presets-cloud-menu";
      box.setAttribute("role", "group");
      box.setAttribute("aria-label", "Cloud providers");
    }
    box.textContent = "";
    box.hidden = !cloudOpen;
    if (!cloudOpen) return box;

    box.appendChild(note("One service at a time. Applying one asks the PC for ONE approval card - nothing changes until you answer it."));
    if (!cloud.providers.length) {
      box.appendChild(note("The PC has not listed any API service it is connected to yet. Add the key on your PC, then open this menu again."));
    }
    for (const row of cloud.providers) {
      const state = providerState(row);
      const line = el(doc, "div", "hud-presets-cloud-row");
      if (!row.keySaved) {
        // A key is added on the PC only (rule 3). The PC's own command is
        // offered as selectable text, and this row is NOT an apply.
        const dead = el(doc, "p", "hud-presets-empty", `${row.name} - ${state}.`);
        dead.dataset.provider = row.id;
        line.appendChild(dead);
        if (row.keyLine) {
          const cmd = el(doc, "p", "hud-presets-key", row.keyLine);
          line.appendChild(cmd);
        }
        line.appendChild(note("Add the key on your PC, then open this menu again."));
        box.appendChild(line);
        continue;
      }
      const asking = pcBusy.preset === "cloud" && pcBusy.provider === row.id;
      const button = menuItem(
        `${row.name}${row.chosen ? " (chosen)" : ""}${asking ? " - asking..." : ""}`,
        [row.host, row.model, state].filter((bit) => bit).join(" - "),
        () => { pickCloudProvider(row); },
      );
      button.dataset.provider = row.id;
      if (row.chosen) button.setAttribute("aria-current", "true");
      // A service the PC says is not ready is not clickable - the same rule as
      // a heavy preset, and the reason is on the line below it. Waiting is NOT
      // a disabled state: the row keeps the keyboard focus and its own guard.
      if (!row.ready) button.disabled = true;
      line.appendChild(button);
      const words = el(doc, "p", "hud-presets-empty",
        [row.host, state].filter((bit) => bit).join(" - "));
      line.appendChild(words);
      box.appendChild(line);
    }

    // The owner's own switch: "Escalate to the cloud when the work is too
    // complex". DRAWN FROM THE PC (`cloud.escalate.on`), never from the click.
    const escalate = cloud.escalate;
    const label = el(doc, "label", "hud-presets-check");
    const boxInput = doc.createElement("input");
    boxInput.type = "checkbox";
    boxInput.id = "hud-escalate-cloud";
    boxInput.checked = escalate.on;
    // Never disabled: `setCloudEscalate` has its own in-flight guard, and a
    // disabled checkbox would lose the keyboard focus on the re-render that
    // follows the click (P2-2/P2-3 in one place).
    boxInput.setAttribute("aria-describedby", "hud-escalate-cloud-why");
    boxInput.addEventListener("change", () => { setCloudEscalate(boxInput.checked); });
    label.htmlFor = boxInput.id;
    label.appendChild(boxInput);
    label.appendChild(el(doc, "span", "", "Escalate to the cloud when the work is too complex"));
    box.appendChild(label);
    const why = el(doc, "p", "hud-presets-empty",
      escalate.why || (escalate.on
        ? "On: a hard question may go to the cloud without asking you first. Private words, a picture or your screen still never leave this PC, and your monthly limit still applies."
        : "When off, every question is answered on this PC first. Turning it on asks the PC for ONE approval card."));
    why.id = "hud-escalate-cloud-why";
    box.appendChild(why);

    const back = menuItem("Back", "Close the cloud providers",
      () => { toggleCloud(false); });
    back.dataset.cloudAction = "back";
    back.id = "hud-presets-cloud-back";
    box.appendChild(back);
    return box;
  }

  /** Open or close the ONE provider submenu, and put focus where the state
   *  says it goes: into the submenu when it opens, back on the Cloud row when
   *  it closes (so a keyboard user is never dropped on <body>). */
  function toggleCloud(open) {
    cloudOpen = Boolean(open);
    renderMenu();
    if (!menu) return;
    const target = cloudOpen
      ? menu.querySelector("#hud-presets-cloud-menu .hud-presets-item:not([disabled]), #hud-escalate-cloud, #hud-presets-cloud-back")
      : menu.querySelector('[data-cloud-action="open"]');
    if (target && typeof target.focus === "function") target.focus();
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
      group.appendChild(button);
    }
    return group;
  }

  /** A stable identity for one menu control, so a rebuild can put the keyboard
   *  focus back on the SAME row instead of dropping it on <body> (2026-10-27
   *  HUD audit P2-2). Built from the row's own DATA, never from its position
   *  and never from its visible text: a row that becomes "General (chosen)"
   *  after the PC answers is still the same row, and using its text as the key
   *  lost the focus on exactly the action the owner had just taken. */
  function focusKey(node) {
    if (!node || !node.dataset) return "";
    const data = node.dataset;
    const stable = [
      data.preset ? `preset:${data.preset}` : "",
      data.personality ? `personality:${data.personality}` : "",
      data.provider ? `provider:${data.provider}` : "",
      data.cloudAction ? `cloud:${data.cloudAction}` : "",
      node.id ? `id:${node.id}` : "",
    ].filter(Boolean);
    if (stable.length) return stable.join("\u0001");
    return `text:${(node.textContent || "").trim()}`;
  }

  function renderMenu() {
    if (!menu) return;
    const scroll = menu.querySelector(".hud-presets-scroll");
    if (!scroll) return;
    const active = doc.activeElement;
    const hadFocus = Boolean(active && scroll.contains(active));
    const key = hadFocus ? focusKey(active) : "";
    scroll.textContent = "";
    // The owner's presets first (2026-10-27): the five local-AI focus presets
    // (then the Cloud preset and its provider submenu when the PC offers one)
    // and the personalities, then the saved HUD layouts the menu always had.
    scroll.appendChild(renderModelPresets());
    const cloud = cloudPresetRow(pcPresets);
    if (cloud) scroll.appendChild(renderCloudSubmenu(cloud));
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
        () => { closeMenu(false); commit(normalizeLayout({
          ...presetLayout(preset.id),
          user_presets: userLayouts(layout),
        }), `Layout: ${info ? info.label : preset.id}.`); },
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
        () => { closeMenu(false); commit(applyUserLayout(layout, entry.id), `Layout: ${entry.name}.`); },
      );
      const rename = el(doc, "button", "hud-presets-small", "Rename");
      rename.type = "button";
      rename.setAttribute("role", "menuitem");
      rename.setAttribute("aria-label", `Rename ${entry.name}`);
      rename.addEventListener("click", () => {
        const back = closeMenu(false);
        openRename(entry.id, back);
      });
      const remove = el(doc, "button", "hud-presets-small hud-presets-danger", "Delete");
      remove.type = "button";
      remove.setAttribute("role", "menuitem");
      remove.setAttribute("aria-label", `Delete ${entry.name}`);
      remove.addEventListener("click", () => {
        const back = closeMenu(false);
        openDelete(entry.id, back);
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
      () => { const back = closeMenu(false); openTransfer("export", back); }));
    scroll.appendChild(actions);

    const line = el(doc, "p", "hud-presets-line", statusNote);
    line.setAttribute("role", "status");
    line.setAttribute("aria-live", "polite");
    scroll.appendChild(line);

    // Put the keyboard back where it was when the rebuild replaced the row it
    // was on. `preventScroll` because the list has not been measured yet and
    // the menu is already placed. Never while the menu is closed: focus must
    // not be moved into a hidden control.
    if (key && !menu.hidden) {
      const again = [...scroll.querySelectorAll('[role="menuitem"], input, button')]
        .find((node) => focusKey(node) === key);
      if (again && !again.disabled && typeof again.focus === "function") {
        try { again.focus({ preventScroll: true }); } catch { again.focus(); }
      }
    }
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
    // Escape closes the menu wherever the focus is (2026-10-27; hud.mjs at
    // 150% DPI caught it): the menu's own keydown only fires while a menu item
    // holds focus, and opening reads the PC's lists and re-renders the list,
    // which can leave focus on the page - so Escape closed nothing, the next
    // press on either door closed it instead, and the reveal check failed. A
    // capture listener sees Escape first; the dialog opened FROM the menu keeps
    // its own Escape, so an open dialog is left alone here.
    doc.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !menu || menu.hidden) return;
      if (doc.querySelector("dialog.hud-presets-dialog[open]")) return;
      event.preventDefault();
      // ONE Escape, ONE owner (P3-1 of the same audit): without this the same
      // key also closed the open left/right drawer and left HUD edit mode, and
      // the focus return then targeted a control sliding off-screen.
      event.stopPropagation();
      // The provider submenu is the inner thing: it closes first, the menu
      // second (2026-10-27).
      if (cloudOpen) { toggleCloud(false); return; }
      closeMenu(true);
    }, true);
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
      event.stopPropagation();
      if (cloudOpen) { toggleCloud(false); return; }
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

  /** The menu's own width, and the smallest gap kept from the window's edges.
   *  ONE number for the CSS (`min(352px, calc(100vw - 16px))`) and for this
   *  placement - they used to disagree by 8px (P3-6 of the HUD audit). */
  const MENU_WIDTH = 352;
  const MENU_GAP = 8;

  /** Place the open menu beside/under its door, INSIDE the window.
   *
   *  The vertical clamp is the fix for P2-1: the menu used to open at
   *  `rect.bottom + 6` with a `72vh` max-height, so from the rail in the Studio
   *  shell its bottom (and its Close button) landed ~96px BELOW an 820px
   *  window. There is no bottom clamp in CSS for a fixed box, so it is done
   *  here, from the real measured height, and again on resize and on a shell
   *  change (P3-4). */
  function placeMenu() {
    if (!menu || menu.hidden) return;
    const rect = focusDoor && typeof focusDoor.getBoundingClientRect === "function"
      ? focusDoor.getBoundingClientRect()
      : { left: 16, right: 16, bottom: 40 };
    const viewportWidth = Number(win.innerWidth) || MENU_WIDTH + (MENU_GAP * 2);
    const viewportHeight = Number(win.innerHeight) || 0;
    const width = Math.min(MENU_WIDTH, Math.max(240, viewportWidth - 16));
    // Under the door it belongs to: the rail button answers in the left
    // column, the badge and the chip door under their own left edge.
    const left = focusDoor === railDoor
      ? Math.max(MENU_GAP, Math.min(viewportWidth - width - MENU_GAP, rect.right + MENU_GAP))
      : Math.max(MENU_GAP, Math.min(viewportWidth - width - MENU_GAP, rect.left));
    const height = menu.offsetHeight || 0;
    const below = Math.round(rect.bottom + 6);
    const top = viewportHeight
      ? Math.max(MENU_GAP, Math.min(below, viewportHeight - height - MENU_GAP))
      : Math.max(MENU_GAP, below);
    menu.style.left = `${Math.round(left)}px`;
    menu.style.top = `${Math.round(top)}px`;
  }

  function openMenu(anchor) {
    // A click can arrive before the 100 ms badge poll has run; resolve the
    // badge on demand so `aria-expanded` and the menu position are never lost.
    if (!badge) badge = doc.getElementById("hud-layout-badge");
    if (!railDoor) railDoor = doc.getElementById("rail-presets");
    ensureMenu();
    // A reopen is a new intent: whatever was in flight last time does not get
    // to leave the rows disabled (P2-3).
    pcBusy = { preset: "", personality: "", escalate: false, provider: "" };
    cloudOpen = false;
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
    // Visible FIRST, then measured and placed: an offsetHeight of 0 would put
    // the Close button back off-screen.
    menu.hidden = false;
    menu.setAttribute("aria-hidden", "false");
    placeMenu();
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

  function openRename(id, back) {
    const entry = userLayouts(layout).find((item) => item.id === id);
    if (!entry) return;
    // Back to the control that opened the menu, which for the rail door is
    // the rail button - never a jump across the window to the badge (P2-6).
    returnFocus = back || badge;
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

  function openDelete(id, back) {
    const entry = userLayouts(layout).find((item) => item.id === id);
    if (!entry) return;
    returnFocus = back || badge;
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

  function openTransfer(mode, back) {
    returnFocus = back || badge;
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
    // Keep the open menu inside the window when the window or the shell
    // changes (P3-4): it is position:fixed with coordinates computed at open
    // time, so a resize or a shell switch used to leave it hanging at the old
    // spot - and the rail door sliding off-canvas with aria-expanded still
    // true. Re-place while it is open; nothing is closed for the owner.
    win.addEventListener("resize", () => { if (menu && !menu.hidden) placeMenu(); });
    win.addEventListener("jarvis:hud-shell", () => { if (menu && !menu.hidden) placeMenu(); });
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

/* ── 5. The Current Models panel (the owner's ask, 2026-10-26) ───────────── */

/**
 * The three reads behind the panel, in the order it shows them. All three are
 * on `hud_proxy.rs`'s fixed read list (`allowed_get`), so in the desktop shell
 * the bootstrap's fetch shim sends each one to `hud_get` with Rust's token; in
 * a plain browser they are the routes themselves, with the page's own
 * `X-Jarvis-Client: hud` header. `/api/models` was NOT on the list before this
 * panel: it is read-only model facts, never a switch (`/api/models/switch`
 * stays refused, and so does every other write).
 */
export const CURRENT_MODELS_READS = ["/api/models", "/api/status", "/api/presets"];

/** One GET of one HUD read, on whichever road this page has. Throws with a
 *  plain sentence; the caller turns that into "the PC did not answer". */
export async function readHudPath(win, path) {
  const response = await win.fetch(apiUrlFor(win, path), {
    cache: "no-store",
    headers: apiHeadersFor(win),
  });
  if (!response.ok) throw new Error(`the PC answered ${response.status}`);
  return response.json();
}

/**
 * Read the panel's three facts from the PC. Each read settles on its own, so
 * one route the PC cannot answer (an older backend with no `/api/models`, or a
 * failed status) leaves the other two sections telling the truth instead of
 * blanking the whole panel. Nothing here is retried, guessed or cached.
 */
export async function readCurrentModelsOnPc(win) {
  const settled = (path) => readHudPath(win, path).then(
    (value) => ({ ok: true, value }),
    (error) => ({ ok: false, error: errorTextOf(error) }),
  );
  const answers = await Promise.all(CURRENT_MODELS_READS.map(settled));
  return { models: answers[0], status: answers[1], presets: answers[2] };
}

const objectOf = (value) => (value && typeof value === "object" && !Array.isArray(value)
  ? value : {});
const stringOf = (value) => (typeof value === "string" ? value.trim() : "");
const numberOrNull = (value) => (typeof value === "number" && Number.isFinite(value)
  ? value : null);

/** The one sentence the owner asked for, exactly, when the PC names nothing. */
export const NO_MODEL_IN_MEMORY = "The PC did not say any model is in memory right now.";

/** `No preset chosen yet - the PC routes on its own.`, with an em dash. */
export const NO_PRESET_CHOSEN = "No preset chosen yet \u2014 the PC routes on its own.";

/**
 * The panel's three read sections, in plain words, from the PC's own answers.
 * PURE: no DOM, no fetch, no clock - so every honest empty state is proved in
 * node, and the panel itself only places these lines.
 *
 * Each section is a list of `{text, dim}` lines: `dim` is an absence or a
 * refusal (the panel draws it in the page's grey "empty" style), not a fact.
 * A fact is only ever built from a field the PC actually sent.
 */
export function currentModelsWords(reads) {
  return {
    answering: answeringWords(reads && reads.models, reads && reads.status),
    loaded: loadedWords(reads && reads.models),
    focus: focusWords(reads && reads.presets),
  };
}

function answeringWords(models, status) {
  const lines = [];
  if (!models || !models.ok) {
    lines.push({ text: "The PC did not answer when asked which model is answering.", dim: true });
    return lines;
  }
  const body = objectOf(models.value);
  const current = stringOf(body.current);
  const previous = stringOf(body.previous);
  if (current) lines.push({ text: current, dim: false });
  else lines.push({ text: "The PC did not name a model it is answering with.", dim: true });
  if (previous && previous !== current) {
    lines.push({ text: `Before that: ${previous}`, dim: true });
  }
  const fallback = status && status.ok ? stringOf(objectOf(status.value).default_model) : "";
  if (current && fallback && fallback !== current) {
    lines.push({ text: `The PC's default model is ${fallback}.`, dim: true });
  } else if (current && status && !status.ok) {
    lines.push({
      text: "The PC did not answer when asked for its status, so whether it has a "
        + "different default model is unknown.",
      dim: true,
    });
  }
  return lines;
}

function loadedWords(models) {
  if (!models || !models.ok) {
    return [{ text: "The PC did not answer when asked what is loaded.", dim: true }];
  }
  const offload = objectOf(objectOf(models.value).offload);
  const rows = (Array.isArray(offload.models) ? offload.models : [])
    .filter((row) => row && typeof row === "object");
  if (offload.available === false || !rows.length) {
    return [{ text: NO_MODEL_IN_MEMORY, dim: true }];
  }
  return rows.map((row) => {
    const name = stringOf(row.name) || "(the PC did not name it)";
    const size = numberOrNull(row.size_mb);
    const vram = numberOrNull(row.vram_mb);
    const onGpu = numberOrNull(row.on_gpu_percent);
    const bits = [];
    if (size !== null) bits.push(`${size} MB in memory`);
    if (vram !== null) bits.push(`${vram} MB of that on the graphics card`);
    if (onGpu !== null) bits.push(`${onGpu}% on the GPU`);
    return { text: bits.length ? `${name} \u2014 ${bits.join(", ")}` : name, dim: false };
  });
}

function focusWords(presets) {
  if (!presets || !presets.ok) {
    return [{ text: "The PC did not answer when asked which focus preset is chosen.", dim: true }];
  }
  const body = objectOf(presets.value);
  if (body.available === false) {
    // The PC's own reason key is `error` (a 503 body); `why` is the older
    // shape and is still read (2026-10-27 audit F8).
    return [{ text: stringOf(body.error) || stringOf(body.why)
      || "This PC's Jarvis cannot list focus presets.", dim: true }];
  }
  const chosen = stringOf(body.chosen_preset);
  if (!chosen) return [{ text: NO_PRESET_CHOSEN, dim: false }];
  const rows = Array.isArray(body.presets) ? body.presets : [];
  const row = rows.find((item) => item && typeof item === "object" && item.id === chosen);
  const title = (row && stringOf(row.title)) || chosen;
  const model = stringOf(body.chosen_model) || (row && stringOf(row.model)) || "";
  return [{
    text: model ? `Chosen focus preset: ${title} (${model})` : `Chosen focus preset: ${title}`,
    dim: false,
  }];
}

const PANEL_ID = "current-models-panel";

function nodeOf(doc, tag, className, text) {
  const made = doc.createElement(tag);
  if (className) made.className = className;
  if (text !== undefined) made.textContent = text;
  return made;
}

/**
 * Mount the Current Models panel and the two doors that open it (2026-10-27).
 * The page calls this once.
 *
 * THE DOORS ARE THE MODEL NAME ITSELF: the stage bar's chip (`#chip-model-door`,
 * visible in five of six shells) and Ambient's top-left pill
 * (`#chip-model-door-ambient`, because the bar's chip is display:none in that
 * shell - P1-2 of the HUD audit). Both are plain buttons that only open the one
 * panel; `#current-models` and its separate button are gone.
 *
 * WHAT IT IS: one READ of the PC's own model facts, plus the SAME lane route
 * the compact lane dropdown in that slot always offered. Clicking a route
 * clicks the page's own `#lanes .lane` button - so `S.lane`, the chip, the
 * Cloud button and the chat body all move exactly as they did before - and the
 * mark is then read back off `#lanes`, never set from the click. There is no
 * POST, no command, no approval card, no model switch and no new route.
 *
 * WHEN THE PC DOES NOT ANSWER: each of the three sections says so in its own
 * words and changes nothing; no value is invented.
 */
export function mountCurrentModels(options = {}) {
  const doc = options.document || globalThis.document;
  const win = options.window || globalThis.window || globalThis;
  if (!doc || !doc.body) return null;
  const DOOR_IDS = ["chip-model-door", "chip-model-door-ambient"];
  const doors = DOOR_IDS.map((id) => doc.getElementById(id)).filter(Boolean);
  if (!doors.length) return null;
  if (doors.some((door) => door.dataset.currentModels === "1")) {
    return globalThis.__jarvisCurrentModels || null;
  }

  let panel = null;
  let reading = false;
  let readings = null;
  // Which door opened it, so Escape and Close put focus back where it came
  // from - the Ambient pill's door when Ambient opened it (P2-6).
  let openedFrom = null;
  const lanesBox = () => doc.getElementById("lanes");

  /** The page's own lane buttons, as the panel's routes: one source of truth,
   *  re-read every render so a lane `renderLanes()` added or removed shows up
   *  here and the pressed mark is the PAGE's, never this panel's. */
  function routeRows() {
    const box = lanesBox();
    const buttons = box ? Array.from(box.querySelectorAll(".lane")) : [];
    return buttons.map((source) => {
      const label = source.querySelector("span");
      const tag = source.querySelector(".tag");
      return {
        lane: source.dataset.lane || "",
        label: (label && label.textContent) || source.dataset.lane || "",
        tag: (tag && tag.textContent) || "",
        pressed: source.getAttribute("aria-pressed") === "true",
        source,
      };
    });
  }

  function section(heading) {
    const group = nodeOf(doc, "div", "hud-presets-group");
    group.appendChild(nodeOf(doc, "p", "hud-presets-head", heading));
    return group;
  }

  function line(parent, text, dim) {
    parent.appendChild(nodeOf(doc, "p", dim ? "hud-presets-empty" : "hud-models-fact", text));
  }

  function renderRoutes(group) {
    line(group, "The next message only: it raises no card and switches no model.", true);
    line(group, "To change the model itself instead, open the Presets menu - that asks ONE card.", true);
    // The cloud is no longer a mode in this list (2026-10-27): it is the rail's
    // Cloud button and the Presets menu's Cloud section, and saying so here is
    // the one place the owner would look for it.
    line(group, "For the cloud, use the rail's Cloud button or the Presets menu's Cloud section.", true);
    const rows = routeRows();
    if (!rows.length) {
      line(group, "This page has no lanes to route, so there is nothing to choose here.", true);
      return;
    }
    for (const row of rows) {
      const button = nodeOf(doc, "button", "hud-presets-item hud-models-route");
      button.type = "button";
      button.dataset.lane = row.lane;
      button.setAttribute("aria-pressed", row.pressed ? "true" : "false");
      if (row.pressed) button.title = "The next message goes this way now.";
      button.appendChild(nodeOf(doc, "span", "", row.label));
      if (row.tag) button.appendChild(nodeOf(doc, "span", "tag", row.tag));
      button.addEventListener("click", () => {
        const again = routeRows().find((item) => item.lane === row.lane);
        if (!again) return;
        // The PAGE's button does the routing; this panel only asked for it.
        again.source.click();
        // Re-read #lanes after the page has repainted it: the mark follows the
        // page's own aria-pressed, so a route that the page refused cannot be
        // marked here as if it had happened.
        render();
        const moved = Array.from(panel.querySelectorAll(".hud-models-route"))
          .find((item) => item.dataset.lane === row.lane);
        if (moved) moved.focus();
      });
      group.appendChild(button);
    }
  }

  function render() {
    if (!panel) return;
    const scroll = panel.querySelector(".hud-presets-scroll");
    if (!scroll) return;
    const words = readings ? currentModelsWords(readings) : null;
    // The panel RE-RENDERS right after it opens (refresh() renders before its
    // read lands and again after), so the route the keyboard was on would be
    // thrown away - the same bug the Presets menu fixed, and the reason the
    // panel's own Escape never fired (P2-5 of the HUD audit). Remember it and
    // put it back.
    const active = doc.activeElement;
    const keepLane = active && scroll.contains(active) && active.dataset
      ? active.dataset.lane || "" : "";
    scroll.textContent = "";

    const heading = section("Answering now");
    if (words) for (const row of words.answering) line(heading, row.text, row.dim);
    else line(heading, reading ? "Reading the PC..." : "Open this panel to read the PC.", true);
    scroll.appendChild(heading);

    const loaded = section("Loaded right now");
    if (words) for (const row of words.loaded) line(loaded, row.text, row.dim);
    else line(loaded, reading ? "Reading the PC..." : "Open this panel to read the PC.", true);
    scroll.appendChild(loaded);

    const focus = section("Chosen focus preset");
    if (words) for (const row of words.focus) line(focus, row.text, row.dim);
    else line(focus, reading ? "Reading the PC..." : "Open this panel to read the PC.", true);
    scroll.appendChild(focus);

    const routes = section("Route the next message");
    renderRoutes(routes);
    scroll.appendChild(routes);

    const refreshButton = panel.querySelector("#current-models-refresh");
    if (refreshButton) {
      refreshButton.disabled = reading;
      refreshButton.textContent = reading ? "Refreshing..." : "Refresh";
    }
    if (keepLane) {
      const again = [...panel.querySelectorAll(".hud-models-route")]
        .find((item) => item.dataset.lane === keepLane);
      if (again && typeof again.focus === "function") again.focus({ preventScroll: true });
    }
  }

  function ensurePanel() {
    if (panel && panel.isConnected) return panel;
    // The panel wears the Presets menu's own popover classes (`hud-presets-*`):
    // one panel look, one set of tokens, nothing new to keep in step.
    panel = nodeOf(doc, "div", "hud-presets-menu hud-models-panel");
    panel.id = PANEL_ID;
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Current Models");
    panel.appendChild(nodeOf(doc, "p", "hud-presets-title", "Current Models"));
    panel.appendChild(nodeOf(doc, "div", "hud-presets-scroll"));
    const actions = nodeOf(doc, "div", "hud-models-actions");
    // Q3 (Gemini packet #8, 2026-10-26): the panel answers "what is Jarvis
    // using"; switching the model preset or the Cloud lane stays ONE click
    // away in the rail's own Presets menu, which already owns both. This door
    // only asks that page's own button to open - it copies no lane list, sends
    // nothing and changes no model itself.
    const presetsButton = nodeOf(doc, "button", "hud-presets-small", "Open Presets menu");
    presetsButton.type = "button";
    presetsButton.id = "current-models-presets";
    presetsButton.setAttribute("aria-label", "Open the Presets menu to switch the model preset");
    presetsButton.addEventListener("click", () => {
      close(false);
      const rail = doc.getElementById("rail-presets");
      if (rail) rail.click();
    });
    const refreshButton = nodeOf(doc, "button", "hud-presets-small", "Refresh");
    refreshButton.type = "button";
    refreshButton.id = "current-models-refresh";
    refreshButton.addEventListener("click", () => { refresh(); });
    const closeButton = nodeOf(doc, "button", "hud-presets-close", "Close");
    closeButton.type = "button";
    closeButton.setAttribute("aria-label", "Close the Current Models panel");
    closeButton.addEventListener("click", () => close(true));
    actions.append(presetsButton, refreshButton, closeButton);
    panel.appendChild(actions);
    doc.body.appendChild(panel);
    // Escape is heard from the DOCUMENT, not from the panel: the panel's own
    // keydown only fires while something inside it holds focus, and the
    // render that follows opening had already dropped focus to <body> - the
    // exact failure the Presets menu fixed, which this branch did not copy
    // (P2-5). `stopPropagation` so ONE Escape closes ONE thing (P3-1).
    doc.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !panel || panel.hidden) return;
      event.preventDefault();
      event.stopPropagation();
      close(true);
    }, true);
    doc.addEventListener("pointerdown", (event) => {
      if (!panel || panel.hidden) return;
      if (panel.contains(event.target)) return;
      // BOTH doors are exempt: a second click on a door is the toggle, and
      // dismissing on pointerdown first would turn it into close-then-reopen.
      if (doors.some((door) => door.contains(event.target))) return;
      close(false);
    }, true);
    return panel;
  }

  /** Under the door that opened it, kept inside the window - the same
   *  placement rule the Presets menu uses, including the vertical clamp: this
   *  panel declares `max-height:72vh` too, so from the Ambient pill at the top
   *  of a 640px window an unclamped `rect.bottom + 6` would put its Close
   *  button off-screen (P2-1). */
  function place(door) {
    const host = door || openedFrom || doors[0];
    const rect = host && typeof host.getBoundingClientRect === "function"
      ? host.getBoundingClientRect()
      : { left: 16, bottom: 40 };
    const viewportWidth = Number(win.innerWidth) || 360;
    const viewportHeight = Number(win.innerHeight) || 0;
    const width = Math.min(352, Math.max(240, viewportWidth - 16));
    const left = Math.max(8, Math.min(viewportWidth - width - 8, rect.left));
    const height = panel.offsetHeight || 0;
    const below = Math.round(rect.bottom + 6);
    const top = viewportHeight
      ? Math.max(8, Math.min(below, viewportHeight - height - 8))
      : Math.max(8, below);
    panel.style.left = `${Math.round(left)}px`;
    panel.style.top = `${Math.round(top)}px`;
  }

  async function refresh() {
    if (reading) return;
    reading = true;
    render();
    try {
      readings = await readCurrentModelsOnPc(win);
    } finally {
      reading = false;
      render();
      // The read is what moves the panel's height; re-clamp after it lands.
      if (panel && !panel.hidden) place(openedFrom);
    }
  }

  function sayDoors(open) {
    for (const door of doors) door.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function open(from) {
    ensurePanel();
    openedFrom = from || openedFrom || doors[0];
    render();
    panel.hidden = false;
    panel.setAttribute("aria-hidden", "false");
    sayDoors(true);
    place(openedFrom);
    const first = panel.querySelector(".hud-models-route") || panel.querySelector("button");
    if (first) first.focus();
    // Always a fresh read: the PC's loaded model can change between openings.
    refresh();
  }

  function close(returnFocus) {
    if (!panel || panel.hidden) return;
    panel.hidden = true;
    panel.setAttribute("aria-hidden", "true");
    sayDoors(false);
    const back = openedFrom || doors[0];
    if (returnFocus && back) back.focus();
  }

  // The page's own lane changes (a click in the rail, the Cloud button, a
  // preset apply) repaint #lanes; the panel follows that, and only that.
  const lanes = lanesBox();
  if (lanes && typeof globalThis.MutationObserver === "function") {
    const observer = new globalThis.MutationObserver(() => {
      if (panel && !panel.hidden) render();
    });
    observer.observe(lanes, { childList: true, subtree: true, attributes: true });
  }

  // Both doors: a click opens the one panel under the door that was clicked,
  // and a second click closes it back to that same door.
  for (const door of doors) {
    door.dataset.currentModels = "1";
    door.addEventListener("click", () => {
      if (panel && !panel.hidden) close(true);
      else open(door);
    });
  }

  const controller = {
    open,
    close: () => close(false),
    refresh,
    panel: () => panel,
    get readings() { return readings; },
  };
  try { globalThis.__jarvisCurrentModels = controller; } catch { /* ignore */ }
  return controller;
}

export { MENU_ID, PANEL_ID, STATUS_ID };
