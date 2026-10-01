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

  const saveCurrent = () => {
    saveNotificationPrefs({
      alarms: dom.alarms ? dom.alarms.checked : true,
      reminders: dom.reminders ? dom.reminders.checked : true,
      briefing: dom.briefing ? dom.briefing.checked : true,
      handoff: dom.handoff ? dom.handoff.checked : true,
      quietEnabled: dom.quietEnabled ? dom.quietEnabled.checked : false,
      quietStart: dom.quietStart ? dom.quietStart.value : DEFAULT_QUIET_START,
      quietEnd: dom.quietEnd ? dom.quietEnd.value : DEFAULT_QUIET_END,
    });
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
