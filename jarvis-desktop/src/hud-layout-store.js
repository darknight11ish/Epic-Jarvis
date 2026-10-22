/**
 * hud-layout-store.js - where the desktop HUD's layout is kept (H1 of the
 * editable-HUD design; Gemini rulings 23-28, 2026-10-21).
 *
 * ONE STORE, ONE COMMAND. The layout is saved through the desktop settings
 * store (`jarvis-desktop.json`) with the Rust commands `get_hud_layout` /
 * `set_hud_layout`, the same appearance-class surface as `theme`: no backend
 * call, no pairing token, no approval card. The Settings picker uses this
 * module, and the HUD's injected bootstrap reads through it.
 *
 * THE OLD THREE-WAY SETTING IS MIGRATED, NOT RESET. Before this model, the
 * choice lived in this origin's `localStorage` under `jarvis.hud.layout` as
 * one of `cockpit`/`studio`/`ambient`. The first time the shell has no saved
 * document, that value is read once and saved here; a browser-served page (no
 * shell, no command) keeps reading the old key exactly as before, so nothing
 * regresses where the command does not exist.
 *
 * A SAVE THAT DID NOT HAPPEN IS REPORTED AS SUCH. The picker's status line is
 * painted from the answer, never from the click: `saved: false` is shown as
 * not saved. That is the difference between a cosmetic setting and a lying one.
 *
 * NO NEW DEPENDENCY. Plain ES module, same as the rest of the pages.
 *
 * @module hud-layout-store
 */

import {
  DEFAULT_PRESET_ID,
  PRESETS,
  describeLayout,
  migrateLegacyLayout,
  normalizeLayout,
  presetInfo,
  presetLayout,
} from "./hud-layout.js";

/** The old localStorage key (src/hud-window.js HUD_LAYOUT_KEY keeps it too). */
export const LEGACY_KEY = "jarvis.hud.layout";

/**
 * Which of the page's three existing looks each preset wears until H2 draws
 * the real region grid. It is a VIEW mapping, not a saved value: the layout
 * document keeps its own shell_template, and a later slice replacing the page's
 * three looks will drop this table rather than migrate anything.
 */
export const LOOK_BY_PRESET = Object.freeze({
  cockpit: "cockpit",
  studio: "studio",
  ambient: "ambient",
  quiet: "ambient",
  telemetry: "cockpit",
  second_brain: "studio",
  minimal: "ambient",
});

/** The three looks the page still understands in H1. */
const LEGACY_LOOKS = new Set(["cockpit", "studio", "ambient"]);

/** The shell's invoke, or null in a plain browser (the page served alone). */
function shellInvoke() {
  const tauri = globalThis.__TAURI__;
  return tauri && tauri.core && typeof tauri.core.invoke === "function"
    ? tauri.core.invoke.bind(tauri.core)
    : null;
}

/** The page's look for a preset id, or the preset's own shell mapped down. */
export function lookForPreset(presetId) {
  if (LOOK_BY_PRESET[presetId]) return LOOK_BY_PRESET[presetId];
  const preset = PRESETS.find((entry) => entry.id === presetId);
  const shell = preset ? preset.shell_template : "three-column";
  if (shell === "split-stage") return "studio";
  if (shell === "center-core" || shell === "single-stage-bento") return "ambient";
  return "cockpit";
}

/**
 * Read the saved layout for a page or a picker.
 *
 * Returns `{layout, saved, source, migrated}`:
 *  - inside the shell: the command's answer, normalized here as well (the
 *    Rust side validates too; a bad document can never reach the renderer);
 *    no saved document means the old three-way value is migrated and saved;
 *  - in a plain browser: the old value, which is all that page ever had.
 */
export async function loadLayout(storage = globalThis.localStorage) {
  const invoke = shellInvoke();
  const legacy = () => {
    try {
      return storage ? storage.getItem(LEGACY_KEY) : null;
    } catch {
      return null;
    }
  };
  if (!invoke) {
    return {
      layout: migrateLegacyLayout(legacy()),
      saved: false,
      source: "browser",
      migrated: false,
    };
  }
  let answer = null;
  try {
    answer = await invoke("get_hud_layout");
  } catch {
    answer = null;
  }
  const stored = answer && answer.layout;
  if (stored) {
    return {
      layout: normalizeLayout(stored),
      saved: true,
      source: String(answer.source || "saved"),
      migrated: false,
    };
  }
  const layout = migrateLegacyLayout(legacy());
  const sealed = await saveLayout(layout, storage);
  return { layout, saved: sealed.saved, source: "migrated", migrated: true };
}

/**
 * Save one layout document. Returns `{layout, saved, source}`; `saved: false`
 * carries the Rust refusal sentence when there is one, so a caller can show it
 * rather than pretend.
 */
export async function saveLayout(layout, storage = globalThis.localStorage) {
  const clean = normalizeLayout(layout);
  const invoke = shellInvoke();
  if (!invoke) {
    return { layout: clean, saved: false, source: "browser",
      error: "Saved on this PC only when the desktop app is running." };
  }
  try {
    const answer = await invoke("set_hud_layout", { layout: clean });
    if (answer && answer.layout) {
      return { layout: normalizeLayout(answer.layout), saved: true,
        source: String(answer.source || "saved") };
    }
    return { layout: clean, saved: false, source: "saved",
      error: "The layout was not saved." };
  } catch (e) {
    return { layout: clean, saved: false, source: "saved",
      error: String(e && e.message ? e.message : e) };
  }
}

/**
 * Choose one built-in HUD layout. The document in the settings store is the
 * ONLY saved truth since F1 of the 2026-10-22 coherence slice; the retired
 * three-way localStorage key is not written any more (the HUD page no longer
 * reads it either). A page that is already open follows through the shell's
 * layout event, not through this function.
 */
export async function choosePreset(presetId) {
  return saveLayout(presetLayout(presetId));
}

/** One line for the picker's status: what is chosen and whether it was kept. */
export function layoutStatus(answer) {
  if (!answer || !answer.layout) return "No HUD layout is saved yet.";
  const line = describeLayout(answer.layout);
  if (answer.saved) return line;
  const why = answer.error || "It could not be saved on this PC.";
  return `${line} (Not saved: ${why})`;
}

/** The preset rows the Settings picker draws, with the saved one selected. */
export function presetRows(answer) {
  const chosen = answer && answer.layout ? answer.layout.base_preset : null;
  return PRESETS.map((preset) => ({
    ...presetInfo(preset.id),
    chosen: preset.id === chosen,
  }));
}

/** A fresh default preset document (cockpit), for a picker's first paint. */
export function defaultLayout() {
  return presetLayout(DEFAULT_PRESET_ID);
}
