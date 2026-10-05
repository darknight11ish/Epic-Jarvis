/**
 * Desktop notification preferences (the owner's decisions of 2026-09-30).
 *
 * This module is the ONE place the notification choices are read, written and
 * sent on. `localStorage` on this PC keeps the page's own copy, so the
 * switches paint correctly and survive an app restart with no roundtrip; and
 * every change is PUSHED to Rust through `set_notification_prefs` as well,
 * because the toasts themselves are raised in Rust (brain/schedule.rs,
 * brain/briefing.rs, stream.rs) and Rust cannot read another window's
 * `localStorage`.
 *
 * That push is what makes the switches real. Until it existed, a kind
 * switched off here still notified: the page wrote a key nothing that posts a
 * toast ever read. Two copies are kept and always written together - the
 * page's, for what it draws, and Rust's, for what it does - and a save that
 * cannot reach Rust says so rather than pretending.
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

export function saveNotificationPrefs(prefs, storage = globalThis.localStorage) {
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
  // left un-sent. Fire and forget: the page must not wait on a file write to
  // redraw, and `pushNotificationPrefs` reports its own failure.
  void pushNotificationPrefs(prefs);
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
