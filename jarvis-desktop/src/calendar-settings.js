/**
 * Settings -> "Jarvis Calendar" (2026-10-30; JARVIS-API section 166;
 * backend `jarvis_local_calendar.py`'s POST /api/calendar/settings).
 *
 * WHY THIS EXISTS. The PHONE has drawn this switch since its own slice
 * (`CalendarSettingsPlate.kt`); the DESKTOP's calendar is the HUD's card, and
 * the HUD is a different window with no Settings page. So before this, "turn
 * the Jarvis Calendar off" had no desktop control at all - the owner's own rule
 * of 2026-10-22 ("every switch findable AND adjustable in Settings too") was
 * not met for it, and the feature row in features.json said so.
 *
 * ONE ROUTE, ONE FIELD. Both controls call the new `calendar_settings` Tauri
 * command, which posts `{"on": true|false}` to `/api/calendar/settings` - the
 * same route (and the same `jarvis_local_calendar.set_switch` function) the
 * phone's row and the typed sentence "turn off the Jarvis calendar" use.
 *
 * NO CARD, EITHER DIRECTION, and that is the owner's ruling of 2026-10-29: it
 * is a preference he can change back in one press, the same shape as the
 * Anti-Slop filter beside it. **OFF NEVER DELETES AN EVENT** - the store keeps
 * every row and both apps stop drawing it - so the sentence under the switch
 * says so rather than letting it be discovered.
 *
 * THE READ IS THE SWITCH ONLY. There is no GET /api/calendar/settings route;
 * the switch rides on GET /api/calendar?days=1's `on`, plus the PC's own `why`
 * when a damaged settings file reads as off. The Rust command drops everything
 * else from that answer, so this page cannot read an event, a title or a count
 * even by accident - it draws one row.
 *
 * NOT HELD ON A STALE LINK: the switch opens no way out of the PC, reads no
 * folder and takes no action, and a stale event stream says nothing about
 * whether the owner wants his calendar drawn. That is a decision, not an
 * omission; surfaces.toml records it beside the grant.
 *
 * @module calendar-settings
 */

import { announce, onEvent } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  card: $("calendar"),
  state: $("cal-set-state"),
  body: $("cal-set-body"),
  sw: $("cal-set-switch"),
  onWords: $("cal-set-on"),
  offWords: $("cal-set-off"),
  line: $("cal-set-line"),
  status: $("cal-set-status"),
};

/** The two sentences the switch says, in the page's own words. */
const ON_SAID = "On. The Calendar card is drawn in the HUD, and the phone's Calendar screen works.";
const OFF_SAID = "Off. Nothing was deleted - every event is still on this PC - and no app draws it until you turn it back on.";
/** What the switch's own button reads, and the state it reports. */
const TURN_ON = "Turn the Jarvis Calendar on";
const TURN_OFF = "Turn the Jarvis Calendar off";

let view = null;
let busy = false;

function say(target, text, tone) {
  if (!target) return;
  target.textContent = text;
  if (tone) target.dataset.tone = tone;
  else delete target.dataset.tone;
}

/** A bridge error in words the owner can act on, never a stack or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function syncBusy() {
  if (el.sw) el.sw.disabled = busy;
}

/** Paints the switch from the PC's own answer, or from nothing at all. */
function paint() {
  if (!el.card) return;
  if (!view) {
    say(el.state, "Asking Jarvis\u2026");
    if (el.body) el.body.hidden = true;
    return;
  }
  if (!view.available) {
    say(el.state, view.why, "bad");
    if (el.body) el.body.hidden = true;
    return;
  }
  say(el.state, "", null);
  if (el.body) el.body.hidden = false;
  if (el.sw) {
    el.sw.setAttribute("aria-checked", view.on ? "true" : "false");
    el.sw.textContent = view.on ? TURN_OFF : TURN_ON;
  }
  if (el.onWords) el.onWords.hidden = !view.on;
  if (el.offWords) el.offWords.hidden = view.on;
  say(el.line, view.on ? ON_SAID : OFF_SAID);
  syncBusy();
}

async function load() {
  if (!el.card || !IS_TAURI) return;
  try {
    const answer = await TAURI.core.invoke("calendar_settings", { action: "read" });
    // FAIL CLOSED, the same rule the HUD page keeps: only an answer that says
    // `ok: true` AND carries a real boolean `on` is drawn as the switch.
    if (!answer || answer.ok !== true || typeof answer.on !== "boolean") {
      view = { available: false,
        why: "Your PC's Jarvis answered in a shape this window does not understand, so the switch is not drawn. Turn it off or on by asking, and your events are kept on the PC." };
      paint();
      return;
    }
    view = { available: true, on: answer.on, why: String(answer.why || "") };
  } catch (error) {
    view = { available: false, why: `Could not read the calendar's switch: ${problemWords(error)}` };
  }
  paint();
}

/** ONE change, then a re-read: the page must show what the PC really holds. */
async function flip() {
  if (busy || !view || !view.available) return;
  busy = true;
  syncBusy();
  say(el.status, "Sending\u2026");
  const want = !view.on;
  let ok = false;
  try {
    const answer = await TAURI.core.invoke("calendar_settings", {
      action: want ? "on" : "off",
    });
    if (!answer || answer.ok !== true) throw new Error("the PC did not confirm the change");
    ok = true;
    const said = String(answer.said || (want
      ? "The Jarvis Calendar is on." : "The Jarvis Calendar is off."));
    say(el.status, said, "ok");
    announce(said);
  } catch (error) {
    say(el.status, problemWords(error), "bad");
    announce(el.status.textContent, "assertive");
  } finally {
    busy = false;
    syncBusy();
  }
  // A failed change re-reads too, so the switch never shows a state the PC
  // refused.
  await load();
  return ok;
}

if (el.sw) el.sw.addEventListener("click", flip);

// A change made anywhere else - the phone's row, or "turn on the Jarvis
// calendar" typed into chat - arrives on the bus as one "calendar" frame. The
// frame is a doorbell, so this re-reads rather than trusting its payload.
onEvent((frame) => {
  if (frame && frame.kind === "calendar") load();
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});

load();
