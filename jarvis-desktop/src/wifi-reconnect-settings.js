/**
 * Settings -> "On this PC" -> "Wi-Fi reconnect" (2026-11-08;
 * `jarvis_wifi.py`, GET/POST `/api/wifi-reconnect`).
 *
 * TWO Rust commands (src-tauri/src/wifi_reconnect.rs), Settings window only:
 *  - get_wifi_reconnect: the whole switch state, in the PC's own shape;
 *  - set_wifi_reconnect {enabled}: ONE change, carded in ONE direction: turning
 *    it ON raises ONE `change_own_config` approval card and the switch stays off
 *    until it is answered; turning it OFF is instant and removes the two-hourly
 *    automatic attempt that the shipped default the owner asked for restores.
 *
 * THE VALUE IS THE PC'S, NOT THIS WINDOW'S. It is not in localStorage and there
 * is no second copy: a chat or Jarvis Live sentence ("turn off the auto Wi-Fi
 * reconnect") changes the SAME value this switch shows. The state is painted
 * from the PC's answer, never from the click - a save that did not happen reads
 * as not saved.
 *
 * ONE READER, USED BY BOTH THE TICK AND THE LINE (fixed 2026-11-18). The PC
 * names its state in ONE field, `enabled` (a JSON boolean): `jarvis_wifi.state()`,
 * `set_enabled()` and `request_enabled()` all send it, and the two Rust commands
 * pass that body on unchanged. This page used to tick the box from a field
 * called `on`, which no answer has ever carried, while it worded the line from
 * the PC's `words` field - so a switch that was really ON showed "On ..." (or
 * "The auto Wi-Fi reconnect is already on. Nothing was changed." after a click)
 * over an unticked box, every time. `readWifi()` below is now the ONLY reader of
 * the PC's yes-or-no; `paint()` ticks from its `on` and `describe()` words the
 * line from the same `on`, so the tick and the sentence cannot name different
 * states again. `tests/wifi-reconnect.mjs` drives that with a fake PC.
 *
 * WHAT THIS PAGE NEVER DOES: it never shows a network name, a password or a key,
 * and it never asks the PC to connect to anything. The switch is the owner's
 * control; the two-hourly attempt belongs to the PC.
 *
 * @module wifi-reconnect-settings
 */

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

/* ── The words this page itself says ────────────────────────────────────── */

/** The line when the PC says ON. Its state word comes from `on`, not from a
 *  backend sentence, so it cannot name a state the tick does not show. */
export const ON_SAID =
  "On. While this PC has no internet, Jarvis tries a saved password-protected " +
  "Wi-Fi network it already knows, every 2 hours.";

/** The line when the PC says OFF. */
export const OFF_SAID =
  "Off. Jarvis will not touch this PC's Wi-Fi choice. Turning it back on " +
  "restores the default you asked for.";

/** The line while turning it ON waits for its ONE approval card. */
export const WAITING =
  "Waiting for your approval card in the Jarvis bar — the switch stays " +
  "off until it is approved.";

/** The page's own sentence for a PC answer it cannot read - never "off". */
export const UNREADABLE =
  "Jarvis answered, but not in a way this app can read, so it will not say " +
  "whether the Wi-Fi reconnect is on. Update the backend by running " +
  "apply-patches.ps1.";

/** The page's own sentence for a switch the PC itself could not read. */
export const DAMAGED =
  "Jarvis could not read its saved Wi-Fi reconnect setting on this PC, so it " +
  "will not say whether it is on. Say \"turn on the auto Wi-Fi reconnect\" to " +
  "write the saved setting again.";

/** One line of the PC's own words, trimmed; never a non-string. */
const text = (value) => (typeof value === "string" ? value.trim() : "");

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

/* ── The ONE reader of the PC's yes-or-no ───────────────────────────────── */

/**
 * `get_wifi_reconnect`'s / `set_wifi_reconnect`'s answer, read once, so the
 * checkbox and the line below it can never read two different fields.
 *
 * `on` is the PC's own `enabled` field and nothing else:
 *   - a boolean there is the state, on or off;
 *   - a body without one is UNKNOWN (`on: null`, `known: false`), never "off";
 *   - `known: false` from the PC (its saved setting file is damaged, so it is
 *     failing safe) is also not a state this page may claim;
 *   - `available: false` is a PC without the route, said in its own words.
 *
 * `words` is the PC's own sentence and `last_words` its last check; they are
 * DETAIL only. Neither may decide the tick or the state word.
 */
export function readWifi(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) {
    return {
      available: false, readable: false, known: false, on: null, waiting: false,
      why: text(a.why) || UNREADABLE, words: "", last_words: "",
    };
  }
  const readable = typeof a.enabled === "boolean";
  const on = readable ? a.enabled : null;
  return {
    available: true,
    readable,
    known: readable && a.known !== false,
    on,
    waiting: a.waiting === true,
    why: "",
    words: text(a.words),
    last_words: text(a.last_words),
  };
}

/**
 * The line under the switch. Every state word here comes from the SAME `on`
 * the box is ticked from; the PC's words are used only where there is no
 * on/off to name (a waiting card) or where the PC itself could not answer.
 */
export function describe(view) {
  if (!view || typeof view !== "object") return "";
  if (view.available === false) return view.why || UNREADABLE;
  if (!view.known) return view.readable ? DAMAGED : UNREADABLE;
  if (view.waiting === true) return view.words || WAITING;
  if (view.on !== true) return OFF_SAID;
  return view.last_words ? ON_SAID + " Last check: " + view.last_words : ON_SAID;
}

/* ── The page ───────────────────────────────────────────────────────────── */

let view = readWifi(null);
let busy = false;

function paint(next, extra) {
  view = next || readWifi(null);
  const box = $("wifi-reconnect-switch");
  const line = $("wifi-reconnect-status");
  const usable = view.available !== false && view.known === true;
  if (box) {
    box.checked = usable && view.on === true;
    box.disabled = busy || !usable;
  }
  if (!line) return;
  line.textContent = typeof extra === "string" ? extra : describe(view);
}

function syncEnabled() {
  const box = $("wifi-reconnect-switch");
  if (!box) return;
  box.disabled = busy || !(view.available !== false && view.known === true);
}

async function load() {
  try {
    if (!IS_TAURI) throw new Error("no desktop backend");
    paint(readWifi(await TAURI.core.invoke("get_wifi_reconnect")));
  } catch (error) {
    paint(readWifi({ available: false, why: problemWords(error) }));
  }
}

async function save(on) {
  if (busy) return;
  busy = true;
  // While the PC answers, the box shows what the click really means: turning it
  // ON waits for ONE approval card, so the box cannot show ON yet; OFF is
  // immediate.
  paint(readWifi({ enabled: !on }), on ? WAITING : "Turning it off…");
  try {
    paint(readWifi(await TAURI.core.invoke("set_wifi_reconnect", { enabled: on })));
  } catch (error) {
    const said = problemWords(error);
    try {
      // A save that did not happen is shown as not saved, and the real state is
      // read back from the PC so the box never keeps a lie.
      paint(readWifi(await TAURI.core.invoke("get_wifi_reconnect")));
    } catch (ignored) {
      paint(readWifi({ available: false, why: said }));
    }
    const line = $("wifi-reconnect-status");
    if (line) line.textContent = said;
  } finally {
    busy = false;
    // Re-enable from the state last read - never a blanket `false`, which would
    // make an unreadable switch clickable again.
    syncEnabled();
  }
}

function wire() {
  const box = $("wifi-reconnect-switch");
  if (!box) return;
  box.addEventListener("change", () => save(Boolean(box.checked)));
  load();
}

if (typeof document !== "undefined" && typeof globalThis.document === "object") {
  // The page is one document; this module is loaded once at the end of it.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
}
