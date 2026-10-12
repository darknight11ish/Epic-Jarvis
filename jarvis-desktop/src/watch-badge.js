/**
 * The Watch with me badge (watch-badge.html; look.rs `show_badge`).
 *
 * Draws the sign from the PC's session (`screen-status`, fixed words and
 * minutes) with look-rules.js - the same rule the bar's strip uses. Its
 * buttons: Stop watching (never held) and 20 more minutes (the last two
 * minutes). It never says a program, a site, a title or a word from the
 * screen: the PC never tells it any. Follows the app's theme and text size.
 * Counts the minutes down between the PC's news.
 */
import { watchSign, ENDED_SHOW_S } from "./look-rules.js";

const TAURI = globalThis.__TAURI__;
/** The badge's size at 100% text, in logical pixels (look.rs BADGE_W/H). */
const BADGE_W = 400;
const BADGE_H = 88;
const THEMES = ["deep-space", "paper", "high-contrast"];
const ZOOM_KEY = "jarvis.zoom";
const ZOOM_STEPS = [0.8, 0.9, 1, 1.15, 1.3, 1.5, 1.75, 2, 2.5];
/** How long a refusal (a button that did not work) stays up. */
const ERROR_FOR_MS = 6000;
/** How often the badge re-reads the session while it is up. */
const POLL_MS = 10000;
/** A payload older than this is not trusted to keep counting: the minutes
 *  FREEZE instead of carrying on down. A countdown that keeps running on
 *  stale news is what made a sign for an ended session look alive
 *  (2026-10-11). */
const TRUST_MS = POLL_MS * 2 + 5000;

const $ = (id) => document.getElementById(id);
const el = {
  badge: $("badge"),
  title: $("title"),
  detail: $("detail"),
  more: $("more"),
  stop: $("stop"),
};

/** The last status and when it arrived, so the minutes can be counted down. */
let last = { status: null, at: 0, stale: false };
let failed = { words: "", until: 0 };
let timer = null;
/** The height (in css px) the window was last sized to. */
let fitted = BADGE_H;

async function invoke(command, args = {}) {
  if (!TAURI || !TAURI.core) return null;
  try {
    return await TAURI.core.invoke(command, args);
  } catch (error) {
    failed = { words: String((error && error.message) || error), until: Date.now() + ERROR_FOR_MS };
    render();
    return null;
  }
}

/** The status with its time counted on from when it arrived. */
function current() {
  const s = last.status;
  if (!s || typeof s !== "object") return null;
  // Never past TRUST_MS: a stale payload must not keep counting down.
  const age = Math.max(0, Date.now() - last.at);
  const gone = Math.floor(Math.min(age, TRUST_MS) / 1000);
  if (s.on === true && Number.isFinite(s.left_s)) {
    return { ...s, left_s: Math.max(0, s.left_s - gone) };
  }
  return s;
}

function endedAgo() {
  const s = last.status;
  if (!s || s.state !== "ended") return null;
  return Math.floor((Date.now() - last.at) / 1000);
}

/**
 * One tick: re-read the session, then let `take` draw it.
 *
 * The PC can end a session without THIS app asking - the voice or quick "stop
 * watching", the phone, the countdown running out, a watchdog - and the
 * `screen-status` event is only emitted when this app itself made the call
 * (look.rs run_watch -> on_status). A badge that only listened therefore
 * outlived the session for ever, still saying "Jarvis is watching" with a
 * countdown running down (2026-10-11). So the sign re-reads on the tick it
 * already ran. A read that fails is not fatal: `invoke` shows its own line,
 * and render() runs again on the next tick.
 */
function tick() {
  invoke("screen_status").then((status) => {
    if (status && typeof status === "object") take(status);
    else render();
  });
}

/**
 * The sign is gone: hide the window. The PC hides it when IT saw the session
 * end (look.rs hide_badge, 15 s after); when the end came from anywhere else
 * nothing told it to, which is this fix's whole point. `allow-hide` on this
 * window is what makes it possible (capabilities/watch-badge.json).
 */
async function closeBadge() {
  if (!TAURI || !TAURI.window) return;
  try {
    await TAURI.window.getCurrentWindow().hide();
  } catch (error) {
    console.info("[watch-badge] could not close the sign:", error);
  }
}

function render() {
  const now = Date.now();
  const sign = watchSign(current(), { stale: last.stale, endedAgo: endedAgo() });
  el.title.textContent = sign.title || "Jarvis is watching";
  let detail = sign.detail;
  if (now < failed.until) detail = failed.words;
  el.detail.textContent = detail;
  // The whole sign, whatever fits.
  el.badge.title = detail ? `${el.title.textContent}\n${detail}` : el.title.textContent;
  el.stop.hidden = !sign.stop;
  el.stop.textContent = sign.stop || "Stop watching";
  el.more.hidden = !sign.more;
  el.badge.dataset.tone = sign.tone;
  clearTimeout(timer);
  // While it is on, the minutes change; after it ended, the sign goes.
  if (sign.on) timer = setTimeout(tick, POLL_MS);
  else if (sign.show) timer = setTimeout(render, (ENDED_SHOW_S + 1) * 1000 - (endedAgo() || 0) * 1000);
  // Ended (or plainly off) and the words have had their time: go. `last.at > 0`
  // keeps a just-opened badge from closing itself before its first read lands.
  else if (last.at > 0) closeBadge();
  if (now < failed.until) setTimeout(render, failed.until - now + 50);
  fit();
}

/** The window is a fixed size, so it can be too small for the words (a long
 *  line, or big text). Grow it to fit what is drawn, so the Stop button is
 *  never cut off. It never shrinks below the normal size. */
function fit() {
  if (!TAURI || !TAURI.window) return;
  requestAnimationFrame(async () => {
    try {
      const zoom = storedZoom();
      const need = Math.max(BADGE_H, Math.ceil(el.badge.offsetHeight + 8));
      if (need === fitted) return;
      fitted = need;
      const Size = (TAURI.dpi && TAURI.dpi.LogicalSize) || (TAURI.window && TAURI.window.LogicalSize);
      if (Size) await TAURI.window.getCurrentWindow().setSize(new Size(Math.round(BADGE_W * zoom), Math.round(need * zoom)));
    } catch {
      /* the fixed size stands */
    }
  });
}

function take(payload) {
  if (!payload || typeof payload !== "object") return;
  last = {
    status: payload.status || null,
    at: Date.now(),
    stale: payload.stale === true,
  };
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
      await TAURI.window.getCurrentWindow().setSize(new Size(Math.round(BADGE_W * zoom), Math.round(fitted * zoom)));
    }
  } catch (error) {
    console.info("[watch-badge] could not follow the text size:", error);
  }
}

window.addEventListener("storage", (event) => {
  if (event.key === ZOOM_KEY) applyZoom();
  if (event.key === "jarvis.theme") applyTheme(event.newValue);
});

el.stop.addEventListener("click", () => invoke("screen_watch", { action: "stop" }));
el.more.addEventListener("click", () => invoke("screen_watch", { action: "extend", minutes: 20 }));

if (TAURI && TAURI.event) {
  TAURI.event.listen("screen-status", (event) => take(event.payload));
  TAURI.event.listen("theme-changed", (event) => applyTheme(event.payload));
  TAURI.core.invoke("get_theme").then((t) => {
    if (typeof t === "string") applyTheme(t);
  }).catch(() => { /* the cached theme above stands */ });
  invoke("screen_status").then(take);
  applyZoom();
}
render();
