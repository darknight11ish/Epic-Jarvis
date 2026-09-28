/**
 * The Jarvis Live badge (live-badge.html; live.rs `show_badge`).
 *
 * Draws the sign from the PC's session (`live-status`, fixed words and
 * minutes) with live-rules.js - the same rule the bar and the phone use -
 * and shows "Heard you - thinking" / "Didn't catch that - say a bit more"
 * for a moment when the PC says so (`live-heard`, never any words). Its
 * buttons: End Live (never held), Mic off / Mic on / Listen anyway, Carry on
 * (after a voice pause), Resume Live (a session that ended by itself, while
 * it can be resumed), 20 more minutes (the last five), and Show the card
 * (opens the Jarvis bar at the card). Clicking the words opens the bar.
 * Follows the app's theme and text size (the review of 2026-09-28: it read
 * the theme once and ignored the zoom).
 */
import { liveSign, LOCK_UNKNOWN_WORDS, SEEN, TITLE } from "./live-rules.js";

const TAURI = globalThis.__TAURI__;
const ME = "desktop";
/** How long "Heard you - thinking" stays up without anything newer. */
const HEARD_FOR_MS = 6000;
/** The badge's size at 100% text, in logical pixels (live.rs BADGE_W/H). */
const BADGE_W = 420;
const BADGE_H = 84;
const THEMES = ["deep-space", "paper", "high-contrast"];
const ZOOM_KEY = "jarvis.zoom";
const ZOOM_STEPS = [0.8, 0.9, 1, 1.15, 1.3, 1.5, 1.75, 2, 2.5];

const $ = (id) => document.getElementById(id);
const el = {
  badge: $("badge"),
  words: $("words"),
  title: $("title"),
  detail: $("detail"),
  carryOn: $("carry-on"),
  resume: $("resume"),
  more: $("more"),
  showCard: $("show-card"),
  mute: $("mute"),
  stop: $("stop"),
};

let last = { status: null, stale: false, lockUnknown: false, callUnknown: false };
let heard = { thinking: false, short: false, until: 0 };
let heardTimer = null;
let endedBase = null;
let endedTimer = null;

async function invoke(command, args = {}) {
  if (!TAURI || !TAURI.core) return null;
  try {
    return await TAURI.core.invoke(command, args);
  } catch (error) {
    el.detail.textContent = String((error && error.message) || error);
    return null;
  }
}

function endedAgo() {
  if (!endedBase) return null;
  return endedBase.ago + Math.floor((Date.now() - endedBase.at) / 1000);
}

function render() {
  const now = Date.now();
  const flash = now < heard.until;
  const sign = liveSign(last.status, ME, {
    stale: last.stale,
    thinking: flash && heard.thinking,
    short: flash && heard.short,
    endedAgo: endedAgo(),
  });
  el.title.textContent = sign.title || TITLE;
  let detail = sign.detail;
  const s = last.status || {};
  if (!detail && sign.stop && last.lockUnknown) detail = LOCK_UNKNOWN_WORDS;
  if (!detail && sign.stop && last.callUnknown) detail = SEEN.call_unknown;
  if (!detail && sign.stop) detail = SEEN.end_hint;
  el.detail.textContent = detail;
  // The whole sign, whatever fits.
  el.badge.title = detail ? `${el.title.textContent}\n${detail}` : el.title.textContent;
  el.words.title = `${el.badge.title}\n(click to open the Jarvis bar)`;
  el.stop.hidden = !sign.stop;
  el.stop.textContent = sign.stop || "End Live";
  el.mute.hidden = !sign.mute;
  el.mute.textContent = sign.mute || "Mic off";
  el.carryOn.hidden = !sign.carryOn;
  el.resume.hidden = !sign.resume;
  el.more.hidden = !sign.moreTime;
  el.showCard.hidden = !sign.showCard;
  el.badge.dataset.quiet = String(Boolean(s.muted) || s.state === "ended");
}

function scheduleEnded() {
  clearTimeout(endedTimer);
  const ago = endedAgo();
  if (ago === null) return;
  const limits = (last.status && last.status.limits) || {};
  const marks = [Number(limits.ended_show_s) || 15, Number(limits.resume_s) || 600]
    .map((x) => x + 1 - ago)
    .filter((x) => x > 0);
  if (marks.length) endedTimer = setTimeout(() => { render(); scheduleEnded(); }, Math.min(...marks) * 1000);
}

function take(payload) {
  if (!payload || typeof payload !== "object") return;
  const before = last.status;
  last = {
    status: payload.status || null,
    stale: payload.stale === true,
    lockUnknown: payload.lockUnknown === true,
    callUnknown: payload.callUnknown === true,
  };
  const s = last.status || {};
  if (s.state === "ended") {
    if (!(before && before.state === "ended" && before.session === s.session)) {
      endedBase = { at: Date.now(), ago: Number.isInteger(s.ended_ago_s) ? s.ended_ago_s : 0 };
      scheduleEnded();
    }
  } else {
    endedBase = null;
  }
  render();
}

/* ── The app's theme and text size ─────────────────────────────────────── */

function applyTheme(name) {
  if (THEMES.includes(name)) document.documentElement.setAttribute("data-theme", name);
  else document.documentElement.removeAttribute("data-theme");
}

function storedZoom() {
  try {
    const z = Number(localStorage.getItem(ZOOM_KEY));
    return ZOOM_STEPS.includes(z) ? z : 1;
  } catch {
    return 1;
  }
}

async function applyZoom() {
  const zoom = storedZoom();
  if (!TAURI) return;
  try {
    if (TAURI.webview) await TAURI.webview.getCurrentWebview().setZoom(zoom);
    const Size = (TAURI.dpi && TAURI.dpi.LogicalSize) || (TAURI.window && TAURI.window.LogicalSize);
    if (Size && TAURI.window) {
      await TAURI.window.getCurrentWindow().setSize(new Size(Math.round(BADGE_W * zoom), Math.round(BADGE_H * zoom)));
    }
  } catch (error) {
    console.info("[live-badge] could not follow the text size:", error);
  }
}

window.addEventListener("storage", (event) => {
  if (event.key === ZOOM_KEY) applyZoom();
  if (event.key === "jarvis.theme") applyTheme(event.newValue);
});

el.stop.addEventListener("click", () => invoke("live_stop"));
el.mute.addEventListener("click", () => {
  const muted = Boolean(last.status && last.status.muted);
  invoke("live_mute", { muted: !muted });
});
el.carryOn.addEventListener("click", () => invoke("live_act", { action: "resume" }));
el.resume.addEventListener("click", () => invoke("live_start", { by: "button" }));
el.more.addEventListener("click", () => invoke("live_act", { action: "extend", minutes: 20 }));
el.showCard.addEventListener("click", () => invoke("live_act", { action: "show_card" }));
el.words.addEventListener("click", () => invoke("live_act", { action: "open" }));

if (TAURI && TAURI.event) {
  TAURI.event.listen("live-status", (event) => take(event.payload));
  TAURI.event.listen("live-heard", (event) => {
    const p = event.payload || {};
    heard = { thinking: p.heard === true, short: p.short === true, until: Date.now() + HEARD_FOR_MS };
    render();
    clearTimeout(heardTimer);
    heardTimer = setTimeout(render, HEARD_FOR_MS + 50);
  });
  TAURI.event.listen("theme-changed", (event) => applyTheme(event.payload));
  TAURI.core.invoke("get_theme").then((t) => {
    if (typeof t === "string") applyTheme(t);
  }).catch(() => { /* the cached theme above stands */ });
  invoke("live_status").then(take);
  applyZoom();
}
render();
