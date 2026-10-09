/**
 * Desktop notification preferences (the owner's decisions of 2026-09-30, and of
 * 2026-10-08).
 *
 * THE BACKEND IS THE ONE SOURCE OF TRUTH. Since 2026-10-08 the seven values
 * live in the owner's `[notifications]` table in `jarvis-framework.toml`, owned
 * by `backend/jarvis_notify_prefs.py`, and both apps reach them through the one
 * limits route (`GET /api/limits`, `POST /api/limits/settings`) - because a
 * phone can never read another app's `localStorage`, and the phone must be able
 * to change these. So `localStorage` here is a CACHE and never an authority:
 * `readFromBackend` is what fills it, and a value this page is holding is never
 * written back over a value the backend already has unless the owner changed it
 * here.
 *
 * TWO COPIES, WRITTEN TOGETHER, AND ONLY ONE OF THEM IS AUTHORITY. The toasts
 * themselves are raised in Rust (brain/schedule.rs, brain/briefing.rs,
 * stream.rs) and Rust cannot read another window's `localStorage`, so every
 * change is still PUSHED to Rust through `set_notification_prefs`. The page's
 * copy exists so the switches paint at once and survive a restart without a
 * round trip; it is refreshed FROM the backend on open, and while this window is
 * open it is refreshed again every `REFRESH_MS`, which is how a change made on
 * the phone reaches this page.
 *
 * @module notifications-prefs
 */

export const NOTIF_ALARMS_KEY = "jarvis.notifications.alarms";
export const NOTIF_REMINDERS_KEY = "jarvis.notifications.reminders";
export const NOTIF_BRIEFING_KEY = "jarvis.notifications.briefing";
export const NOTIF_HANDOFF_KEY = "jarvis.notifications.handoff";
export const NOTIF_QUIET_ENABLED_KEY = "jarvis.notifications.quiet_enabled";
export const NOTIF_QUIET_START_KEY = "jarvis.notifications.quiet_start";
export const NOTIF_QUIET_END_KEY = "jarvis.notifications.quiet_end";

export const DEFAULT_QUIET_START = "22:00";
export const DEFAULT_QUIET_END = "07:00";

/** The Rust command that carries these choices to the toasts. */
export const SET_NOTIFICATION_PREFS_COMMAND = "set_notification_prefs";

/** The Rust command that reads the limits table - the authority for these seven. */
export const GET_LIMITS_COMMAND = "get_limits";

/** The Rust command that changes ONE limit; the PC decides whether it asks first. */
export const SET_LIMIT_COMMAND = "set_limit";

/**
 * The seven limits rows, in the order the card draws them: the four toggles,
 * the quiet-hours switch, then the window's two ends.
 *
 * `key` is the limits-table row (`backend/jarvis_limits.py`), `pref` is the name
 * this module and Rust use, and `mode` says where a change goes: `"limit"` means
 * the backend owns it and this page only asks (see `saveNotificationPrefs`).
 */
export const NOTIF_ROWS = [
  { key: "notif_alarms", pref: "alarms", kind: "bool" },
  { key: "notif_reminders", pref: "reminders", kind: "bool" },
  { key: "notif_briefing", pref: "briefing", kind: "bool" },
  { key: "notif_handoff", pref: "handoff", kind: "bool" },
  { key: "notif_quiet_enabled", pref: "quietEnabled", kind: "bool" },
  { key: "notif_quiet_start", pref: "quietStart", kind: "time" },
  { key: "notif_quiet_end", pref: "quietEnd", kind: "time" },
];

/**
 * How often the open Settings window asks the backend what is really in force.
 *
 * A phone change has to reach this page somehow, and this is that. The window is
 * built on demand and destroyed when it is closed (windows.rs
 * `show_settings_unlocked`), so this runs only while it is open; a change made
 * while it is closed arrives the next time it is opened, and is pushed to Rust
 * then. See this repository's report for the exact window and its limits.
 */
export const REFRESH_MS = 30000;

function loadBool(key, defaultValue, storage = globalThis.localStorage) {
  try {
    if (!storage) return defaultValue;
    const v = storage.getItem(key);
    if (v === null) return defaultValue;
    return v === "true" || v === "on";
  } catch {
    return defaultValue;
  }
}


function saveBool(key, value, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(key, value ? "true" : "false");
    return true;
  } catch {
    return false;
  }
}

function loadString(key, defaultValue, storage = globalThis.localStorage) {
  try {
    if (!storage) return defaultValue;
    const v = storage.getItem(key);
    return v !== null ? v : defaultValue;
  } catch {
    return defaultValue;
  }
}

function saveString(key, value, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(key, String(value));
    return true;
  } catch {
    return false;
  }
}

export function loadNotificationPrefs(storage = globalThis.localStorage) {
  return {
    alarms: loadBool(NOTIF_ALARMS_KEY, true, storage),
    reminders: loadBool(NOTIF_REMINDERS_KEY, true, storage),
    briefing: loadBool(NOTIF_BRIEFING_KEY, true, storage),
    handoff: loadBool(NOTIF_HANDOFF_KEY, true, storage),
    quietEnabled: loadBool(NOTIF_QUIET_ENABLED_KEY, false, storage),
    quietStart: loadString(NOTIF_QUIET_START_KEY, DEFAULT_QUIET_START, storage),
    quietEnd: loadString(NOTIF_QUIET_END_KEY, DEFAULT_QUIET_END, storage),
  };
}

export function saveNotificationPrefs(prefs, storage = globalThis.localStorage, { push = true } = {}) {
  if (!prefs) return false;
  let ok = true;
  if (typeof prefs.alarms === "boolean") ok = saveBool(NOTIF_ALARMS_KEY, prefs.alarms, storage) && ok;
  if (typeof prefs.reminders === "boolean") ok = saveBool(NOTIF_REMINDERS_KEY, prefs.reminders, storage) && ok;
  if (typeof prefs.briefing === "boolean") ok = saveBool(NOTIF_BRIEFING_KEY, prefs.briefing, storage) && ok;
  if (typeof prefs.handoff === "boolean") ok = saveBool(NOTIF_HANDOFF_KEY, prefs.handoff, storage) && ok;
  if (typeof prefs.quietEnabled === "boolean") ok = saveBool(NOTIF_QUIET_ENABLED_KEY, prefs.quietEnabled, storage) && ok;
  if (typeof prefs.quietStart === "string") ok = saveString(NOTIF_QUIET_START_KEY, prefs.quietStart, storage) && ok;
  if (typeof prefs.quietEnd === "string") ok = saveString(NOTIF_QUIET_END_KEY, prefs.quietEnd, storage) && ok;
  // The same change goes to Rust, which is what the toasts honour. Every save
  // path goes through this function, so no switch can be drawn as saved and
  // left un-sent. Fire and forget by default: the page must not wait on a file
  // write to redraw, and `pushNotificationPrefs` reports its own failure.
  //
  // `push: false` is for the one caller that wants to REPORT the answer itself:
  // Settings has a status line and says so when the PC did not take them
  // (settings-audit, 2026-10-08 - the switches used to look saved while the
  // toasts went on, which is the opposite of what this module's header claims).
  if (push) void pushNotificationPrefs(prefs);
  return ok;
}

/**
 * The choices as Rust wants them: the four switches and the quiet-hours
 * window, camelCase, times filled in when an input is blank. Pure, so it is
 * testable without a window.
 */
export function notificationPrefsPayload(prefs = {}) {
  const on = (value) => value !== false;
  return {
    alarms: on(prefs.alarms),
    reminders: on(prefs.reminders),
    briefing: on(prefs.briefing),
    handoff: on(prefs.handoff),
    quietEnabled: prefs.quietEnabled === true,
    quietStart: typeof prefs.quietStart === "string" && prefs.quietStart
      ? prefs.quietStart
      : DEFAULT_QUIET_START,
    quietEnd: typeof prefs.quietEnd === "string" && prefs.quietEnd
      ? prefs.quietEnd
      : DEFAULT_QUIET_END,
  };
}

/** `__TAURI__.core.invoke`, or null when this page is not inside the app. */
function tauriInvoke() {
  const tauri = globalThis.__TAURI__;
  if (tauri && tauri.core && typeof tauri.core.invoke === "function") {
    return tauri.core.invoke.bind(tauri.core);
  }
  return null;
}

/**
 * Sends the choices to Rust, which raises every toast.
 *
 * Resolves true when Rust has them, false when this page is not in the app or
 * the call was refused - the caller says so rather than leaving the owner
 * believing a switch took effect. Called on every save, and once when
 * Settings opens: that first call is how choices made before Rust kept them
 * (they were only ever in `localStorage`) are carried over instead of being
 * quietly reverted.
 */
export async function pushNotificationPrefs(prefs, invoke = tauriInvoke()) {
  if (!invoke) return false;
  try {
    await invoke(SET_NOTIFICATION_PREFS_COMMAND, { prefs: notificationPrefsPayload(prefs) });
    return true;
  } catch (err) {
    // Not fatal for the page - the localStorage copy is still right, and the
    // next save tries again - but it must not be silent: this is the
    // difference between a switch that works and one that only looks as if it
    // does, which is the exact bug this push exists to close.
    console.warn("[jarvis] the notification switches did not reach the PC:", err);
    return false;
  }
}

// ---------------------------------------------------------------------------
//   The backend, which owns the values (2026-10-08)
// ---------------------------------------------------------------------------

/** A time of day as the backend stores and checks it, "HH:MM", or null. Pure. */
export function validTime(text) {
  const t = String(text == null ? "" : text).trim();
  if (!/^\d{2}:\d{2}$/.test(t)) return null;
  const h = Number(t.slice(0, 2));
  const m = Number(t.slice(3, 5));
  if (!(h >= 0 && h <= 23) || !(m >= 0 && m <= 59)) return null;
  return t;
}

/**
 * The seven values out of a `GET /api/limits` answer, or null when the answer
 * is not the shape this card can read.
 *
 * A row whose kind is not `bool` or `time` is ignored - the table carries other
 * kinds for other screens, and this card draws only these seven. A row that is
 * absent leaves its value alone rather than inventing one: an older PC without
 * these rows must not have its switches silently changed by a page that guessed.
 */
export function notificationPrefsFromLimits(body) {
  const rows = body && Array.isArray(body.limits) ? body.limits : null;
  if (!rows) return null;
  const byKey = new Map(rows.filter((r) => r && typeof r === "object").map((r) => [r.key, r]));
  const prefs = {};
  let found = 0;
  for (const row of NOTIF_ROWS) {
    const got = byKey.get(row.key);
    if (!got) continue;
    found += 1;
    if (row.kind === "bool") prefs[row.pref] = got.value === true;
    else {
      const t = validTime(got.value);
      if (t !== null) prefs[row.pref] = t;
    }
  }
  return found ? prefs : null;
}

/**
 * What is really in force on this PC: the owner's own settings file, through
 * the limits route. Null when the PC cannot be asked, or has no such route.
 *
 * Never throws: an unreachable PC is a fact the caller reports, not a crash.
 */
export async function readFromBackend(invoke = tauriInvoke()) {
  if (!invoke) return null;
  try {
    return notificationPrefsFromLimits(await invoke(GET_LIMITS_COMMAND));
  } catch (err) {
    console.warn("[jarvis] the PC's notification settings could not be read:", err);
    return null;
  }
}

/**
 * Writes ONE value to the PC, through the one limits route.
 *
 * The BACKEND decides whether a change asks first: these seven rows carry no
 * loosening in either direction (`loosening="none"`), so a change is applied at
 * once and there is no card - which is the point, because a card over "show me
 * the briefing" could otherwise leave an alarm waiting on an answer.
 *
 * @returns the PC's own sentence, or a refusal in the PC's own words.
 */
export async function writeToBackend(rowKey, valueJson, invoke = tauriInvoke()) {
  if (!invoke) return { ok: false, why: "Open this in Jarvis Desktop to change these." };
  try {
    const out = await invoke(SET_LIMIT_COMMAND, { key: rowKey, value: valueJson });
    return { ok: true, said: String((out && out.said) || "Changed.") };
  } catch (error) {
    const raw = error && error.message !== undefined ? error.message : error;
    const said = String(raw == null ? "" : raw).trim();
    return {
      ok: false,
      why: said && !/[{}<>]|::/.test(said) && said.length <= 400
        ? said
        : "Could not change that on the PC. Try again in a moment, or restart Jarvis Desktop.",
    };
  }
}

