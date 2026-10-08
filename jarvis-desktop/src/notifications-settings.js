/**
 * Settings -> "Notifications": choose which notifications appear on this PC,
 * set quiet hours, and test Windows notifications (the owner's decisions of
 * 2026-09-30).
 *
 * @module notifications-settings
 */

import {
  loadNotificationPrefs,
  saveNotificationPrefs,
  pushNotificationPrefs,
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

function say(text, tone) {
  if (!dom.status) return;
  dom.status.textContent = text;
  if (tone) dom.status.dataset.tone = tone;
  else delete dom.status.dataset.tone;
}

export function initNotificationsSettings() {
  if (!dom.section) return;

  const prefs = loadNotificationPrefs();

  if (dom.alarms) dom.alarms.checked = prefs.alarms;
  if (dom.reminders) dom.reminders.checked = prefs.reminders;
  if (dom.briefing) dom.briefing.checked = prefs.briefing;
  if (dom.handoff) dom.handoff.checked = prefs.handoff;
  if (dom.quietEnabled) dom.quietEnabled.checked = prefs.quietEnabled;
  if (dom.quietTimes) dom.quietTimes.hidden = !prefs.quietEnabled;
  if (dom.quietStart) dom.quietStart.value = prefs.quietStart || DEFAULT_QUIET_START;
  if (dom.quietEnd) dom.quietEnd.value = prefs.quietEnd || DEFAULT_QUIET_END;

  // Hand what is shown to Rust, which raises every toast. On a first run
  // these choices are only in localStorage - they were made before Rust kept
  // them - so this is the carry-over: what the owner already turned off stays
  // off instead of coming back on, and a page with nothing stored sends
  // everything on, which is what the app did before the switches existed.
  void pushToPc(prefs);

  /**
   * Sends the switches to the PC and SAYS SO when it did not take them.
   *
   * Without this the four switches could be stored as off while the PC kept
   * notifying: `saveNotificationPrefs` wrote localStorage and fired the push
   * into the void, and only a console warning marked the refusal - so the
   * owner saw a switch off and the toasts went on (settings-audit, 2026-10-08).
   * This module's own header promises the opposite, and the push exists
   * precisely because that silent failure happened before.
   */
  async function pushToPc(next) {
    const reached = await pushNotificationPrefs(next);
    if (!dom.status) return;
    if (reached) {
      // A later save that works clears the last complaint, like every other
      // card's status line.
      say("");
    } else {
      say("These switches did not reach the PC, so the notifications still "
        + "follow what it has. Try again, or restart Jarvis Desktop.", "bad");
    }
  }

  const saveCurrent = () => {
    const prefs = {
      alarms: dom.alarms ? dom.alarms.checked : true,
      reminders: dom.reminders ? dom.reminders.checked : true,
      briefing: dom.briefing ? dom.briefing.checked : true,
      handoff: dom.handoff ? dom.handoff.checked : true,
      quietEnabled: dom.quietEnabled ? dom.quietEnabled.checked : false,
      quietStart: dom.quietStart ? dom.quietStart.value : DEFAULT_QUIET_START,
      quietEnd: dom.quietEnd ? dom.quietEnd.value : DEFAULT_QUIET_END,
    };
    // localStorage now; the PC from here, so its answer can be reported.
    saveNotificationPrefs(prefs, globalThis.localStorage, { push: false });
    void pushToPc(prefs);
  };

  [dom.alarms, dom.reminders, dom.briefing, dom.handoff].forEach((el) => {
    if (el) el.addEventListener("change", saveCurrent);
  });

  if (dom.quietEnabled) {
    dom.quietEnabled.addEventListener("change", () => {
      if (dom.quietTimes) dom.quietTimes.hidden = !dom.quietEnabled.checked;
      saveCurrent();
    });
  }

  if (dom.quietStart) dom.quietStart.addEventListener("change", saveCurrent);
  if (dom.quietEnd) dom.quietEnd.addEventListener("change", saveCurrent);

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
