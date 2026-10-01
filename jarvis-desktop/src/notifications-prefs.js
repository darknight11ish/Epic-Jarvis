/**
 * Desktop notification preferences (the owner's decisions of 2026-09-30).
 *
 * Stored in localStorage on this PC, so it survives app restarts and requires
 * no backend roundtrip or gate card.
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
  return ok;
}
