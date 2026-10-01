import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  loadNotificationPrefs,
  saveNotificationPrefs,
  NOTIF_ALARMS_KEY,
  NOTIF_REMINDERS_KEY,
  NOTIF_BRIEFING_KEY,
  NOTIF_HANDOFF_KEY,
  NOTIF_QUIET_ENABLED_KEY,
  NOTIF_QUIET_START_KEY,
  NOTIF_QUIET_END_KEY,
  DEFAULT_QUIET_START,
  DEFAULT_QUIET_END,
} from "../src/notifications-prefs.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf-8");
}

console.log("--- notifications prefs tests ---");

// Mock storage
const store = new Map();
const mockStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

// 1. Defaults when storage is empty
const def = loadNotificationPrefs(mockStorage);
assert.equal(def.alarms, true, "alarms on by default");
assert.equal(def.reminders, true, "reminders on by default");
assert.equal(def.briefing, true, "briefing on by default");
assert.equal(def.handoff, true, "handoff on by default");
assert.equal(def.quietEnabled, false, "quiet hours off by default");
assert.equal(def.quietStart, DEFAULT_QUIET_START, "default quiet start 22:00");
assert.equal(def.quietEnd, DEFAULT_QUIET_END, "default quiet end 07:00");

// 2. Save settings
saveNotificationPrefs(
  {
    alarms: true,
    reminders: false,
    briefing: false,
    handoff: true,
    quietEnabled: true,
    quietStart: "23:00",
    quietEnd: "06:30",
  },
  mockStorage
);

const saved = loadNotificationPrefs(mockStorage);
assert.equal(saved.alarms, true);
assert.equal(saved.reminders, false);
assert.equal(saved.briefing, false);
assert.equal(saved.handoff, true);
assert.equal(saved.quietEnabled, true);
assert.equal(saved.quietStart, "23:00");
assert.equal(saved.quietEnd, "06:30");

console.log("ok    prefs load and save with localStorage");

// 3. Check HTML structure
const html = read("src/settings.html");
assert.ok(html.includes('href="#notifications"'), "jump link to notifications present");
assert.ok(html.includes('id="notifications"'), "notifications section present");
assert.ok(html.includes('id="notif-alarms"'), "alarms checkbox present");
assert.ok(html.includes('id="notif-reminders"'), "reminders checkbox present");
assert.ok(html.includes('id="notif-briefing"'), "briefing checkbox present");
assert.ok(html.includes('id="notif-handoff"'), "handoff checkbox present");
assert.ok(html.includes('id="notif-quiet-enabled"'), "quiet enabled checkbox present");
assert.ok(html.includes('id="notif-quiet-times"'), "quiet times container present");
assert.ok(html.includes('id="notif-quiet-start"'), "quiet start input present");
assert.ok(html.includes('id="notif-quiet-end"'), "quiet end input present");
assert.ok(html.includes('id="notif-send-test"'), "send test notification button present");
assert.ok(html.includes('id="notif-status"'), "status display present");
assert.ok(html.includes('src="notifications-settings.js"'), "script tag for notifications-settings.js present");

// 4. Notes wording checks
const norm = html.replace(/\s+/g, " ");
assert.ok(
  norm.includes('Alarms and urgent "tell me when" alerts ring until dismissed') &&
  norm.includes("break through Windows Focus Assist"),
  "focus assist note present"
);
assert.ok(
  norm.includes("Decisions waiting for your yes always notify you and cannot be turned off"),
  "approvals non-silence note present"
);
assert.ok(
  norm.includes("Quiet hours never silence urgent alerts or decisions waiting for you"),
  "quiet hours note present"
);

console.log("ok    settings.html markup and notes verified");

console.log("\nAll notifications tests passed!");
