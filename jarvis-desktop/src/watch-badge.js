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
const BADGE_H = 64;
const THEMES = ["deep-space", "paper", "high-contrast"];
const ZOOM_KEY = "jarvis.zoom";
const ZOOM_STEPS = [0.8, 0.9, 1, 1.15, 1.3, 1.5, 1.75, 2, 2.5];
/** How long a refusal (a button that did not work) stays up. */
const ERROR_FOR_MS = 6000;

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
  const gone = Math.floor((Date.now() - last.at) / 1000);
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
  if (sign.on) timer = setTimeout(render, 10000);
  else if (sign.show) timer = setTimeout(render, (ENDED_SHOW_S + 1) * 1000 - (endedAgo() || 0) * 1000);
  if (now < failed.until) setTimeout(render, failed.until - now + 50);
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
      await TAURI.window.getCurrentWindow().setSize(new Size(Math.round(BADGE_W * zoom), Math.round(BADGE_H * zoom)));
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
