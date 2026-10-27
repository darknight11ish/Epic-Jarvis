/**
 * Settings -> "The big HUD window": a speaker beside each answer you can hear.
 *
 * The owner's ask of 2026-10-27, in his own words: "a read out loud button i
 * can enable in the settings which will add a read out loud icon next to all
 * chat boxes that i can click on and jarvis will speak out loud the chat box
 * in his chosen current voice".
 *
 * WHAT IT IS NOT. It is not the automatic read-aloud rule. That rule - the
 * `private-speech.js` check and the `voice.speak` call at the end of the HUD's
 * own send - is unchanged in either position of this switch, and turning this
 * ON speaks nothing by itself. It only lets the big "Jarvis" window draw one
 * small speaker on each finished answer; a click on that speaker reads THAT
 * answer through the page's existing `voice.speak`, the same OS voice the
 * window already uses for its automatic read-aloud.
 *
 * WHAT IT MAY NEVER DO. Show a speaker on an answer the window is treating as
 * private. The page asks `private-speech.js`'s `mayReadAloud` with that
 * answer's own route before it draws anything, and the shell's own
 * `speechSynthesis.speak` wrapper refuses a kept-on-screen answer whatever the
 * page asks for - two independent refusals, neither of them loosened here.
 *
 * WHERE IT IS KEPT. This window origin's `localStorage`, under the key below -
 * the same place, and the same shape, as `hud-window.js`'s OPEN_BAR_KEY,
 * because this is the same kind of choice: a per-computer cosmetic one, with
 * no backend, no pairing token and no approval card. The default is the
 * opposite way round on purpose. OPEN_BAR_KEY shows a button the owner already
 * had and defaults to ON; this is new behaviour and defaults to OFF, because he
 * asked for a switch he can enable.
 *
 * WHY THE HUD PAGE SPELLS THE KEY AGAIN. `jarvis_hud.html`'s inline script has
 * to read this while it is drawing an answer, and the page is vendored into the
 * backend folder and served on its own in a browser besides - it cannot import
 * a value at that point, so it keeps its own copy of the reading rule, exactly
 * as `hud_bootstrap.js` keeps its own copy of OPEN_BAR_KEY. `tests/hud-live-
 * read-aloud.mjs` holds the page's copy to `readAloudIconsOn` below, value by
 * value, so the two cannot drift.
 *
 * @module read-aloud-icons
 */

/** The `localStorage` key. Namespaced like this window's other keys. */
export const READ_ALOUD_ICONS_KEY = "jarvis.hud.readAloudIcons";

/**
 * Whether the speakers show: OFF unless this computer saved them on, and OFF
 * when storage cannot be read at all (private mode, cleared site data).
 *
 * The reading is `notifications-prefs.js`'s `loadBool` and `hud-window.js`'s
 * `openBarShown` rule - "true" or "on" is on, ANY other stored value is off -
 * with the default flipped, which is the only difference between the two.
 */
export function readAloudIconsOn(storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    const v = storage.getItem(READ_ALOUD_ICONS_KEY);
    if (v === null) return false;
    return v === "true" || v === "on";
  } catch {
    return false;
  }
}

/** Saves the choice. Returns whether it could be saved. */
export function saveReadAloudIcons(on, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(READ_ALOUD_ICONS_KEY, on ? "true" : "false");
    return true;
  } catch {
    return false;
  }
}

/**
 * One line saying what is chosen now, for the card's own status line.
 *
 * It says the two things a reader has to be able to trust: that a speaker is
 * not offered on an answer that has to stay on screen, and that OFF does not
 * turn off the read-aloud the window already does. Both are true of the code,
 * not hopes: the page asks `mayReadAloud` before it draws a speaker, and this
 * switch is read nowhere else.
 */
export function describeReadAloudIcons(on) {
  return on
    ? "On: each finished answer that may be read aloud gets a small speaker, and clicking it reads that answer out loud. An answer that has to stay on screen gets none."
    : "Off: no speakers beside answers. Jarvis still reads answers aloud as it does today - this switch only adds the speakers.";
}
