/**
 * Settings -> "Notifications": choose which notifications appear on this PC,
 * set quiet hours, and test Windows notifications.
 *
 * The owner's decisions of 2026-09-30, and of 2026-10-08: THE PC IS THE ONE
 * SOURCE OF TRUTH. The seven values live in the owner's `[notifications]` table
 * in `jarvis-framework.toml` (`backend/jarvis_notify_prefs.py`) and both apps
 * change them through the one limits route, because a phone can never read this
 * window's `localStorage` and the phone must be able to change them.
 *
 * So this card:
 *
 *  - READS the backend when it opens, and paints what is really in force;
 *  - WRITES every change to the backend first, and pushes the PC's own answer
 *    to Rust (which raises the toasts) only once the PC has taken it;
 *  - keeps `localStorage` as a CACHE of what it last read, never as a second
 *    authority - a failed read leaves the stored copy on screen looking like
 *    what it is (this window's last reading) rather than being pushed over the
 *    PC's real values;
 *  - asks again every `REFRESH_MS` while it is open, which is how a change made
 *    on the phone reaches this page (and, from here, the PC's toasts).
 *
 * @module notifications-settings
 */

import {
  loadNotificationPrefs,
  saveNotificationPrefs,
  pushNotificationPrefs,
  readFromBackend,
  writeToBackend,
  notificationPrefsPayload,
  NOTIF_ROWS,
  REFRESH_MS,
  DEFAULT_QUIET_START,
  DEFAULT_QUIET_END,
} from "./notifications-prefs.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const dom = {
  section: $("notifications"),
  alarms: $("notif-alarms"),
  reminders: $("notif-reminders"),
  briefing: $("notif-briefing"),
  handoff: $("notif-handoff"),
  quietEnabled: $("notif-quiet-enabled"),
  quietTimes: $("notif-quiet-times"),
  quietStart: $("notif-quiet-start"),
  quietEnd: $("notif-quiet-end"),
  sendTest: $("notif-send-test"),
  status: $("notif-status"),
};

/** The switch elements by the name the rest of this module uses. */
const SWITCHES = {
  alarms: () => dom.alarms,
  reminders: () => dom.reminders,
  briefing: () => dom.briefing,
  handoff: () => dom.handoff,
  quietEnabled: () => dom.quietEnabled,
};

const TIME_FIELDS = { quietStart: () => dom.quietStart, quietEnd: () => dom.quietEnd };

function say(text, tone) {
  if (!dom.status) return;
  dom.status.textContent = text;
  if (tone) dom.status.dataset.tone = tone;
  else delete dom.status.dataset.tone;
}

/** The seven values as the card is showing them right now. */
function shownPrefs() {
  const prefs = {};
  for (const [name, get] of Object.entries(SWITCHES)) {
    const el = get();
    prefs[name] = el ? el.checked : false;
  }
  prefs.quietStart = (dom.quietStart && dom.quietStart.value) || DEFAULT_QUIET_START;
  prefs.quietEnd = (dom.quietEnd && dom.quietEnd.value) || DEFAULT_QUIET_END;
  return prefs;
}

export function initNotificationsSettings() {
  if (!dom.section) return;

  /** Paint the seven values, and remember them as this window's last reading. */
  function paint(prefs) {
    for (const [name, get] of Object.entries(SWITCHES)) {
      const el = get();
      if (el) el.checked = prefs[name] === true;
    }
    if (dom.quietTimes) dom.quietTimes.hidden = prefs.quietEnabled !== true;
    if (dom.quietStart) dom.quietStart.value = prefs.quietStart || DEFAULT_QUIET_START;
    if (dom.quietEnd) dom.quietEnd.value = prefs.quietEnd || DEFAULT_QUIET_END;
    // The cache, not the authority: the backend has just been read (or could not
    // be), and this is what the page will paint from on a restart with no
    // round trip. It is refreshed from the backend again on every read.
    saveNotificationPrefs(prefs, globalThis.localStorage, { push: false });
  }

  /**
   * The reason to show when the PC could not be asked. The switches are drawn
   * from this window's last reading, so the owner is told plainly that what is
   * on screen may not be what is in force - the exact failure the settings audit
   * of 2026-10-08 was about.
   */
  const UNREAD =
    "Could not read these from the PC, so this is what it last said. The "
    + "notifications keep following the PC's own settings until it can be asked.";

  async function pushToPc(next) {
    const reached = await pushNotificationPrefs(next);
    if (!dom.status) return;
    if (reached) say("");
    else {
      say("These switches did not reach the PC, so the notifications still "
        + "follow what it has. Try again, or restart Jarvis Desktop.", "bad");
    }
  }

  /**
   * What is really in force, from the PC. Paints it, pushes it to Rust (which
   * raises the toasts), and caches it.
   *
   * It NEVER pushes what the page was already holding: a failed read must not
   * turn a stale local copy into the PC's settings, which would quietly undo a
   * change the owner made on the phone.
   */
  async function refresh({ announce = false } = {}) {
    const fromPc = await readFromBackend();
    if (!fromPc) {
      if (announce) say(UNREAD, "bad");
      return false;
    }
    paint({ ...shownPrefs(), ...fromPc, quietEnabled: fromPc.quietEnabled === true });
    await pushToPc(shownPrefs());
    return true;
  }

  // First paint from the cache, so the card is never blank while the PC is
  // asked; then the PC's own answer, which is what counts.
  paint(loadNotificationPrefs());
  void refresh({ announce: true });

  /**
   * Write ONE row to the PC, then push the PC's own answer to Rust.
   *
   * ONE row, not all seven: sending all seven on a single click would overwrite
   * a change the owner made on the phone in the meantime with this window's
   * copy of the others. The backend owns each value on its own.
   */
  async function saveOne(pref) {
    const row = NOTIF_ROWS.find((r) => r.pref === pref);
    if (!row) return;
    const prefs = shownPrefs();
    const value = row.kind === "bool" ? prefs[pref] === true : prefs[pref];
    // The cache follows what the owner just did, so a repaint is instant and a
    // restart shows their last action; the PC's answer is what makes it true.
    saveNotificationPrefs(prefs, globalThis.localStorage, { push: false });
    say("Saving…");
    const out = await writeToBackend(row.key, row.kind === "bool" ? value : JSON.stringify(value));
    if (!out.ok) {
      say(out.why, "bad");
      // The PC refused it, so what is on screen is wrong: read what is really
      // in force and paint that, rather than leaving a switch showing a value
      // the PC never took.
      await refresh();
      return;
    }
    say(out.said || "");
    // Rust raises the toasts and cannot read this window's storage or the
    // backend, so the value the PC has just confirmed is what it is given.
    await pushToPc(shownPrefs());
  }

  for (const [name, get] of Object.entries(SWITCHES)) {
    const el = get();
    if (!el) continue;
    el.addEventListener("change", () => {
      if (name === "quietEnabled" && dom.quietTimes) {
        dom.quietTimes.hidden = !el.checked;
      }
      void saveOne(name);
    });
  }

  for (const [name, get] of Object.entries(TIME_FIELDS)) {
    const el = get();
    if (!el) continue;
    el.addEventListener("change", () => void saveOne(name));
  }

  // While this window is open, keep asking. This is how a change made on the
  // phone reaches the PC's toasts: the phone writes the settings file through
  // the backend, this read finds it, and the push hands it to Rust.
  const timer = globalThis.setInterval(() => void refresh(), REFRESH_MS);
  globalThis.addEventListener("beforeunload", () => globalThis.clearInterval(timer));
  // Coming back to the window is a better moment than the timer: the owner is
  // looking at the card again, so a stale switch is worse than a round trip.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void refresh();
  });

  if (dom.sendTest) {
    dom.sendTest.addEventListener("click", async () => {
      say("Sending…");
      try {
        await invoke("notify_user", {
          title: "Jarvis",
          body: "This is a test notification from Jarvis.",
        });
        say("Sent test notification.");
        setTimeout(() => say(""), 4000);
      } catch (err) {
        say("Could not send test notification.", "bad");
      }
    });
  }
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initNotificationsSettings);
  } else {
    initNotificationsSettings();
  }
}
