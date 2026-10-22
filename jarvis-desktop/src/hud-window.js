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

/* The switch's own name and its detail are NOT here: a static toggle's words
 * live in settings.html, the one place they are drawn, exactly as the floating
 * face's and the notification switches' do. Only what the page cannot write by
 * hand is in this module - the reading, the saving, and the line below, which
 * follows the switch's state. */

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

/* ==========================================================================
   The HUD's three layouts (2026-10-20)

   LEGACY SINCE H1 (2026-10-21). These three ids and this key are now the
   page's own three-way look and the fallback for a page served on its own in a
   browser; the owner's layout is the versioned region document in
   `hud-layout.js`, saved through `hud-layout-store.js`. `hud-window-settings.js`
   no longer calls the save functions below - the store is the one writer - and
   the injected bootstrap wears the saved preset's nearest look on load. The
   functions stay because the vendored page still spells the key and its three
   pills still switch it, and tests/hud-window.mjs covers that reading.

   The owner asked for a choice of three UIs for the big HUD window, "looking
   cutting edge while still being intuitive and effective" (the work order of
   2026-10-20, PART III+IV). All three are ONE page - jarvis_hud.html - switched
   by `document.body.dataset.hudLayout`; there is no second HTML file to keep in
   step, and the same DOM ids are in the document in every mode.

   WHERE IT IS KEPT, AND WHY THE SAME PLACE AS THE OPEN-BAR SWITCH ABOVE. It is
   a per-computer cosmetic choice with no effect on what Jarvis does, so it
   lives in the HUD window origin's `localStorage` under the key below -
   exactly the mechanism the "Open the Jarvis bar" button setting already uses,
   and the same reason: one key, read by the Settings window that changes it and
   by the HUD window that obeys it, and no roundtrip to the backend. A change
   made while the HUD is open reaches it through the shared `storage` event.

   WHY THE HUD PAGE NAMES THE KEY A THIRD TIME. jarvis_hud.html is served by
   the Python backend as well as bundled in the shell, so it cannot `import`
   this module; its inline script spells the key, the three ids and the
   reading rule itself, the same way hud_bootstrap.js spells OPEN_BAR_KEY. The
   two copies cannot drift silently: tests/hud.mjs opens the REAL page with
   `readHudLayout`/`saveHudLayout`'s key and values and fails unless the page
   obeys them, and tests/hud-window.mjs holds the pure rule here to every
   value storage can hold.

   It raises NO approval card and is never held on a stale link (CLAUDE.md's
   rule for a cosmetic option: it changes at once). The phone has no HUD, so
   there is nothing for it there - docs/ARCHITECTURE.md section 8 says so.
   ========================================================================== */

/** The `localStorage` key. Namespaced like this window's other keys. */
export const HUD_LAYOUT_KEY = "jarvis.hud.layout";

/** The three layouts, default first. The order the pickers draw them in. */
export const HUD_LAYOUTS = ["cockpit", "studio", "ambient"];

/**
 * What the pickers say about each layout: a glyph that needs no image file
 * (the page is CSP-bound to `img-src 'self' data:`, and a text glyph is also
 * the accessible name's friend), a name and one line. The words are the
 * work order's own, plain enough to choose by.
 */
export const HUD_LAYOUT_INFO = {
  cockpit: {
    label: "Command Cockpit",
    blurb:
      "Three-column tactical deck: navigation and the brain switcher on the "
      + "left, the Jarvis core and conversation in the middle, and Bento "
      + "inspector cards on the right.",
    glyph: "\u229e",
  },
  studio: {
    label: "Studio Split-Workspace",
    blurb:
      "A slim icon dock, conversation on the left, and the Galaxy map or the "
      + "HUD's telemetry/approvals/memory stage on the right - side by side.",
    glyph: "\u25eb",
  },
  ambient: {
    label: "Ambient Voice Core",
    blurb:
      "No sidebars: one large reactive core, floating glass status pills, the "
      + "latest exchange as a centred card, and a centred composer.",
    glyph: "\u25ce",
  },
};

/** A stored layout id as this build reads it. Anything unknown is the default. */
export function normaliseHudLayout(name) {
  return HUD_LAYOUTS.includes(name) ? name : HUD_LAYOUTS[0];
}

/**
 * The layout this computer chose: the stored id, or the default when nothing
 * is stored (a fresh install) or storage cannot be read at all (private mode,
 * cleared site data) - the same way round as `openBarShown` above.
 */
export function readHudLayout(storage = globalThis.localStorage) {
  try {
    if (!storage) return HUD_LAYOUTS[0];
    return normaliseHudLayout(storage.getItem(HUD_LAYOUT_KEY));
  } catch {
    return HUD_LAYOUTS[0];
  }
}

/** Saves the choice. Returns whether it could be saved (storage may refuse). */
export function saveHudLayout(name, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(HUD_LAYOUT_KEY, normaliseHudLayout(name));
    return true;
  } catch {
    return false;
  }
}

/** One line saying what is chosen now, for the card's own status line. */
export function describeHudLayout(name) {
  const id = normaliseHudLayout(name);
  return `${HUD_LAYOUT_INFO[id].label}: ${HUD_LAYOUT_INFO[id].blurb}`;
}
