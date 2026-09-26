/**
 * Focus sessions (the owner's decision of 2026-09-25; JARVIS-API.md section
 * 26; backend jarvis_focus.py).
 *
 * A timer plus Quiet. On this PC Jarvis watches which app or site is in
 * front, names a drift out loud, keeps only counts, and ends with a report
 * card. This module holds the words and reads what the PC sends; brain.js
 * draws the Work tab's "Focus session" (start, the countdown, Pause/Resume,
 * +10 minutes, Stop, the report card) and widget.js the small countdown on
 * the desktop that tints on a drift (Pause/Resume, Lock on, Stop). Both call
 * the Rust commands in src-tauri/src/brain/focus.rs.
 *
 * The PC never sends what was in front - only booleans and counts - and the
 * spoken line reaches this app as sound, fetched by Rust from the PC itself
 * (focus.rs play_callout), never as words.
 *
 * The phone says the same words (net/Focus.kt); tests/focus.mjs and the
 * phone's FocusTest check them against tools/gen_focus_cases.py's file.
 *
 * @module focus
 */

export const FOCUS_TITLE = "Focus session";
export const FOCUS_DETAIL =
  "A timer plus Quiet. On the PC, Jarvis watches which app or site is in front " +
  "and says so when you drift - out loud, on the PC only. It keeps counts, never " +
  "what it saw, and nothing leaves the PC. Off unless you start it.";
export const FOCUS_MISSING =
  "Your PC's Jarvis does not have focus sessions yet - run apply-patches.ps1 on the PC.";

export const DEFAULT_MINUTES = 25;
export const MIN_MINUTES = 1;
export const MAX_MINUTES = 240;
export const EXTEND_MINUTES = 10;
export const BAD_MINUTES = "A focus session is 1 to 240 minutes long.";

export const LABELS = {
  pause: "Pause",
  resume: "Resume",
  extend: "+10 minutes",
  stop: "Stop",
  lock: "Lock on",
};
export const START_LABEL = "Start";
export const LAST_TITLE = "Last session";
/** The widget's Lock on: what it does, because the button is IN Jarvis. */
export const LOCK_TITLE =
  "Go back to what you are working on - Jarvis locks on where you land. (Or say \"lock on this\" there.)";

/** Held on a stale link: they make Jarvis watch, or watch for longer. */
export const HELD_WHEN_STALE = new Set(["start", "resume", "extend", "lock"]);

const num = (v, d = 0) => (typeof v === "number" && Number.isFinite(v) ? v : d);
const text = (v) => (typeof v === "string" ? v.trim() : "");

/**
 * GET /api/focus as a view, or `{available: false, why}` for a PC without
 * focus sessions (Rust answers that for a 404 or 501) or anything unreadable.
 */
export function readFocus(body) {
  if (!body || typeof body !== "object" || body.available === false || typeof body.on !== "boolean") {
    return { available: false, why: text(body && body.why) || FOCUS_MISSING };
  }
  const r = body.report && typeof body.report === "object" ? body.report : null;
  return {
    available: true,
    on: body.on,
    paused: body.paused === true,
    state: text(body.state) || (body.on ? "locked" : "off"),
    minutes: num(body.minutes),
    left: Math.max(0, num(body.left_s)),
    intent: text(body.intent),
    deferred: body.deferred === true,
    onTarget: typeof body.on_target === "boolean" ? body.on_target : null,
    drifting: body.drifting === true,
    excused: body.excused === true,
    drifts: num(body.drifts),
    line: text(body.line),
    note: text(body.note),
    report: r ? {
      title: text(r.title),
      lines: Array.isArray(r.lines) ? r.lines.filter((x) => typeof x === "string") : [],
      clean: r.clean === true,
      streak: num(r.streak),
      completed: r.completed === true,
    } : null,
  };
}

/** Seconds left now, counted down from what the PC said `sinceMs` ago. */
export function leftNow(view, sinceMs = 0) {
  if (!view || !view.on) return 0;
  if (view.paused) return view.left;
  return Math.max(0, view.left - Math.floor(sinceMs / 1000));
}

/** "24:05", or "1:02:05" past an hour. */
export function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/**
 * How the countdown looks: "drift" (tinted - off target, not excused),
 * "paused", "settling" (waiting to lock on), or "on".
 */
export function toneOf(view) {
  if (!view || !view.on) return "off";
  if (view.paused) return "paused";
  if (view.drifting && !view.excused) return "drift";
  if (view.deferred) return "settling";
  return "on";
}

/** The buttons, in order. `where`: "brain" or "widget" (the widget has Lock on). */
export function actionsOf(view, where = "brain") {
  if (!view || !view.on) return [];
  const first = view.paused ? "resume" : "pause";
  return where === "widget" ? [first, "lock", "stop"] : [first, "extend", "stop"];
}

/** The minutes typed, or null when they are not 1 to 240. */
export function minutesOf(value) {
  const s = String(value == null ? "" : value).trim();
  if (!/^\d{1,3}$/.test(s)) return null;
  const n = Number(s);
  return n >= MIN_MINUTES && n <= MAX_MINUTES ? n : null;
}

/** The drift count, in words. */
export function driftWords(n) {
  if (!n) return "No drifts so far.";
  return n === 1 ? "One drift so far." : `${n} drifts so far.`;
}
