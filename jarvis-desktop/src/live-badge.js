/**
 * The Jarvis Live badge (live-badge.html; live.rs `show_badge`).
 *
 * Draws the sign from the PC's session (`live-status`, fixed words and
 * minutes) with live-rules.js - the same rule the bar and the phone use -
 * and shows "Heard you - thinking" / "Didn't catch that - say a bit more"
 * for a moment when the PC says so (`live-heard`, never any words). Its
 * buttons: Stop (never held), Mute/Unmute, Carry on (after a voice pause)
 * and Resume Live (a session that ended by itself, within ten minutes).
 */
import { liveSign, LOCK_UNKNOWN_WORDS, SEEN } from "./live-rules.js";

const TAURI = globalThis.__TAURI__;
const ME = "desktop";
/** How long "Heard you - thinking" stays up without anything newer. */
const HEARD_FOR_MS = 6000;

const $ = (id) => document.getElementById(id);
const el = {
  badge: $("badge"),
  title: $("title"),
  detail: $("detail"),
  carryOn: $("carry-on"),
  resume: $("resume"),
  mute: $("mute"),
  stop: $("stop"),
};

let last = { status: null, stale: false, lockUnknown: false, callUnknown: false };
let heard = { thinking: false, short: false, until: 0 };
let heardTimer = null;

async function invoke(command, args = {}) {
  if (!TAURI || !TAURI.core) return null;
  try {
    return await TAURI.core.invoke(command, args);
  } catch (error) {
    el.detail.textContent = String((error && error.message) || error);
    return null;
  }
}

function render() {
  const now = Date.now();
  const flash = now < heard.until;
  const sign = liveSign(last.status, ME, {
    stale: last.stale,
    thinking: flash && heard.thinking,
    short: flash && heard.short,
  });
  el.title.textContent = sign.title || "Jarvis Live";
  let detail = sign.detail;
  const s = last.status || {};
  if (!detail && sign.stop && last.lockUnknown) detail = LOCK_UNKNOWN_WORDS;
  if (!detail && sign.stop && last.callUnknown) detail = SEEN.call_unknown;
  el.detail.textContent = detail ? ` · ${detail}` : "";
  el.stop.hidden = !sign.stop;
  el.stop.textContent = sign.stop || "Stop";
  el.mute.hidden = !sign.mute;
  el.mute.textContent = sign.mute || "Mute";
  el.carryOn.hidden = !sign.carryOn;
  el.resume.hidden = !sign.resume;
  el.badge.dataset.quiet = String(Boolean(s.muted) || s.state === "ended");
}

function take(payload) {
  if (!payload || typeof payload !== "object") return;
  last = {
    status: payload.status || null,
    stale: payload.stale === true,
    lockUnknown: payload.lockUnknown === true,
    callUnknown: payload.callUnknown === true,
  };
  render();
}

el.stop.addEventListener("click", () => invoke("live_stop"));
el.mute.addEventListener("click", () => {
  const muted = Boolean(last.status && last.status.muted);
  invoke("live_mute", { muted: !muted });
});
el.carryOn.addEventListener("click", () => invoke("live_act", { action: "resume" }));
el.resume.addEventListener("click", () => invoke("live_start", { by: "button" }));

if (TAURI && TAURI.event) {
  TAURI.event.listen("live-status", (event) => take(event.payload));
  TAURI.event.listen("live-heard", (event) => {
    const p = event.payload || {};
    heard = { thinking: p.heard === true, short: p.short === true, until: Date.now() + HEARD_FOR_MS };
    render();
    clearTimeout(heardTimer);
    heardTimer = setTimeout(render, HEARD_FOR_MS + 50);
  });
  invoke("live_status").then(take);
}
render();
