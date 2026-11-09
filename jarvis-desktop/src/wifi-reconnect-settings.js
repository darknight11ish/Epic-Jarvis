/**
 * Settings -> "On this PC" -> "Wi-Fi reconnect" (2026-11-08;
 * `jarvis_wifi.py`, GET/POST `/api/wifi-reconnect`).
 *
 * TWO Rust commands (src-tauri/src/wifi_reconnect.rs), Settings window only:
 *  - get_wifi_reconnect: the whole switch state, in the PC's own shape;
 *  - set_wifi_reconnect {enabled}: ONE change, cardless in both directions (OFF
 *    removes the two-hourly automatic attempt; ON restores the shipped default
 *    the owner asked for).
 *
 * THE VALUE IS THE PC'S, NOT THIS WINDOW'S. It is not in localStorage and there
 * is no second copy: a chat or Jarvis Live sentence ("turn off the auto Wi-Fi
 * reconnect") changes the SAME value this switch shows. The state is painted
 * from the PC's answer, never from the click - a save that did not happen reads
 * as not saved.
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

function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

/** The line under the switch, from the PC's own answer. */
function describe(view) {
  if (!view || typeof view !== "object") return "";
  if (view.on === false) {
    return "Off. Jarvis will not touch this PC's Wi-Fi choice. Turning it back on " +
      "restores the default you asked for.";
  }
  if (typeof view.words === "string" && view.words.trim()) return view.words.trim();
  return "On. While this PC has no internet, Jarvis tries a saved password-protected " +
    "Wi-Fi network it already knows, every 2 hours.";
}

/** What the last check actually did, when the PC reports one. */
function lastWords(view) {
  if (!view || typeof view !== "object") return "";
  if (typeof view.last_words === "string" && view.last_words.trim()) {
    return view.last_words.trim();
  }
  return "";
}

let busy = false;

function paint(view, extra) {
  const box = $("wifi-reconnect-switch");
  const line = $("wifi-reconnect-status");
  const known = Boolean(view && view.known !== false && view.available !== false);
  if (box) {
    box.checked = known && view.on === true;
    box.disabled = busy || !known;
  }
  if (!line) return;
  if (extra) {
    line.textContent = extra;
    return;
  }
  if (view && view.available === false) {
    line.textContent = view.why || "";
    return;
  }
  if (!known) {
    line.textContent = (view && (view.why || view.words)) || "";
    return;
  }
  const last = lastWords(view);
  line.textContent = describe(view) + (last ? " Last check: " + last : "");
}

async function load() {
  try {
    if (!IS_TAURI) throw new Error("no desktop backend");
    const reply = await TAURI.core.invoke("get_wifi_reconnect");
    paint(reply);
  } catch (error) {
    paint({ known: false, available: false, why: problemWords(error) });
  }
}

async function save(on) {
  if (busy) return;
  busy = true;
  paint({ known: true, on: !on }, on ? "Turning it on…" : "Turning it off…");
  try {
    const reply = await TAURI.core.invoke("set_wifi_reconnect", { enabled: on });
    paint(reply);
  } catch (error) {
    // A save that did not happen is shown as not saved, then the real state is
    // read back from the PC so the box never keeps a lie.
    const line = $("wifi-reconnect-status");
    if (line) line.textContent = problemWords(error);
    try {
      const back = await TAURI.core.invoke("get_wifi_reconnect");
      paint(back);
    } catch (ignored) {
      paint({ known: false, available: false, why: problemWords(error) });
    }
  } finally {
    busy = false;
    const box = $("wifi-reconnect-switch");
    if (box) box.disabled = false;
  }
}

const box = $("wifi-reconnect-switch");
if (box) {
  box.addEventListener("change", () => save(Boolean(box.checked)));
  load();
}
