/**
 * hud-window.js - "The big HUD window": whether the "Open the Jarvis bar"
 * button shows in it, and the words this PC's Settings card shows.
 *
 * THE OWNER'S REQUEST (2026-10-06). Looking at the big "Jarvis" window (the
 * HUD, jarvis_hud.html), the owner asked for its "Open the Jarvis bar"
 * button to be replaced by a text box he could type into directly, and then
 * chose: keep the button beside the box, and add an option in Settings that
 * controls whether the button shows in that window at all.
 *
 * The box is PR #85's work and is not rebuilt here. This module is only the
 * option. Its default is ON, because that is the state the owner already
 * approved on 2026-10-06 ("The 'Open the Jarvis bar' button stays in that
 * window, beside the box").
 *
 * WHERE IT IS KEPT, AND WHY NOT SOMEWHERE ELSE. It is a per-computer
 * cosmetic choice, so it lives in this window origin's `localStorage`
 * (key below), the same place and for the same reasons as the floating
 * face (floating.js), "Interrupt Jarvis while it talks" (barge-in.js,
 * live-rules.js) and the face tuning (face-tuning.js): one key, read by the
 * Settings window that changes it and by the HUD window that obeys it, and
 * no roundtrip to the backend for a switch that changes nothing Jarvis does.
 *
 * It raises NO approval card and is never held on a stale link. CLAUDE.md's
 * rule for a cosmetic option is that it changes at once: showing or hiding
 * this button changes nothing about what Jarvis does, asks or remembers -
 * the window's own chat box, its Send and the mic button are untouched, and
 * Alt+Space still opens the Jarvis bar.
 *
 * WHY THE BOOTSTRAP NAMES THE KEY A SECOND TIME. `hud_bootstrap.js` is
 * injected into the HUD page as a plain script, so it cannot `import` this
 * module; it reads `OPEN_BAR_KEY` itself. The two spellings cannot drift
 * silently: tests/hud-window.mjs reads the bootstrap's own source and
 * fails unless the key it reads is this one, and runs the bootstrap in a
 * hand-made DOM to prove both read it the same way.
 *
 * @module hud-window
 */

/** The `localStorage` key. Namespaced like this window's other keys. */
export const OPEN_BAR_KEY = "jarvis.hud.openBar";

/** The switch's name in Settings, and the words both apps' tests quote. */
export const OPEN_BAR_NAME = "Show the \"Open the Jarvis bar\" button";

/** What the switch means, under its name in Settings. */
export const OPEN_BAR_DETAIL =
  "On: the button sits beside the big window's own chat box, and opens the Jarvis bar " +
  "ready to type. Off: the button is not drawn there. The chat box, its Send and the " +
  "microphone button are unchanged, and Alt+Space still opens the Jarvis bar.";

/**
 * Whether the button shows: ON unless this computer has saved it off, and ON
 * when storage cannot be read at all (private mode, cleared site data) - the
 * same way round as the settings either side of it, so a browser that will
 * not store anything leaves the approved default alone.
 *
 * The reading is notifications-prefs.js's `loadBool`: "true" or "on" is on,
 * ANY other stored value is off. The bootstrap's own copy of this rule is
 * checked against it, value by value, in tests/hud-window.mjs.
 */
export function openBarShown(storage = globalThis.localStorage) {
  try {
    if (!storage) return true;
    const v = storage.getItem(OPEN_BAR_KEY);
    if (v === null) return true;
    return v === "true" || v === "on";
  } catch {
    return true;
  }
}

/** Saves the choice. Returns whether it could be saved. */
export function saveOpenBarShown(on, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(OPEN_BAR_KEY, on ? "true" : "false");
    return true;
  } catch {
    return false;
  }
}

/** One line saying what is chosen now, for the card's own status line. */
export function describeOpenBar(on) {
  return on
    ? "Shown: the button is beside the big window's own chat box."
    : "Hidden: the big window shows its chat box and microphone only.";
}
