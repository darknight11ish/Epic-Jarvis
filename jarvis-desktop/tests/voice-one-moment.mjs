/**
 * "Say One moment" - TWO stores, ANDed at use time (2026-11-19 state-drift.
 *
 *   node tests/voice-one-moment.mjs
 *
 * WHY THIS EXISTS. DESKTOP-STATE-DRIFT.md section 3.1 (MISMATCH-WORDS): the
 * Settings row painted its tick and its sentence from THIS window's
 * localStorage only. The PC keeps its own half in `voice-flow.json`, and a chat
 * sentence turns that half off (`request_one_moment`). The behaviour plays the
 * clip only when BOTH are on (`main.js`: `loadMoment() && voiceFlow.moment`),
 * so after "stop saying one moment" in chat the row still said
 * "On: ... it says 'One moment.'" while Jarvis had stopped - words claiming a
 * state the store did not have.
 *
 * The fix is ONE reader of the two stores ([readOneMoment]); this suite holds
 * every combination, including the two that must never read as On: the PC's
 * half turned off by chat, and a PC that has not answered at all.
 *
 * Run by CI's frontend shards (`tests/*.mjs`); needs no browser.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  describeMoment,
  MOMENT_NOT_CONFIRMED,
  MOMENT_OFF_ON_THE_PC,
  readOneMoment,
} from "../src/voice-flow.js";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

/** The PC's `GET /api/voice/status` answer with both halves on. */
const PC_BOTH_ON = {
  flow: {
    available: true,
    barge_in: { enabled: false, available: false, why: "" },
    moment: { enabled: true, ready: true, key: "moment-1" },
    after_question: false,
    cut_off: false,
  },
};

/** The same PC after a chat sentence turned its own half off. */
const PC_MOMENT_OFF = {
  flow: {
    available: true,
    barge_in: { enabled: false, available: false, why: "" },
    moment: { enabled: false, ready: true, key: "moment-1" },
    after_question: false,
    cut_off: false,
  },
};

test("both halves on: the row says On and the tick is on", () => {
  const row = readOneMoment(true, PC_BOTH_ON);
  assert.equal(row.on, true);
  assert.equal(row.half, "both");
  assert.equal(row.words, describeMoment(true));
});

test("this window is on but a chat sentence turned the PC's half off: the row must NOT say On", () => {
  // The audit's exact words: owner says "stop saying one moment", the PC half
  // goes off, Jarvis really stops - and the row still said On.
  const row = readOneMoment(true, PC_MOMENT_OFF);
  assert.equal(row.on, false, "the behaviour ANDs both halves, so the row is not on");
  assert.equal(row.half, "pc-off");
  assert.equal(row.words, MOMENT_OFF_ON_THE_PC);
  assert.match(row.words, /chat sentence turned the PC's own half/);
  assert.match(row.words, /start saying one moment again/);
  assert.doesNotMatch(row.words, /^On/);
});

test("a PC that has not answered is not 'on' and not claimed as a state", () => {
  const unknown = readOneMoment(true, null);
  assert.equal(unknown.on, false);
  assert.equal(unknown.half, "pc-silent");
  assert.equal(unknown.words, MOMENT_NOT_CONFIRMED);
  assert.doesNotMatch(unknown.words, /^On/);
  assert.match(unknown.words, /has not confirmed/);

  // An older PC with no flow block is the same "not confirmed", never On.
  const older = readOneMoment(true, { gate: {} });
  assert.equal(older.on, false);
  assert.equal(older.half, "pc-silent");
  assert.equal(older.words, MOMENT_NOT_CONFIRMED);
});

test("this window's own switch off is off whatever the PC says", () => {
  for (const status of [null, PC_BOTH_ON, PC_MOMENT_OFF, { gate: {} }]) {
    const row = readOneMoment(false, status);
    assert.equal(row.on, false, "the AND is false when this window is off");
    assert.equal(row.half, "this-window");
    assert.equal(row.words, describeMoment(false));
  }
});

test("Settings paints the row from that ONE reader, not from localStorage alone", () => {
  // There is no Compose-style host here: settings.js needs the whole Settings
  // document. The wiring is held as a source pin, the same way this repo pins
  // other page rules - and each pin names the line the audit found false.
  const settings = read("../src/settings.js");
  assert.match(
    settings,
    /import\s*\{[^}]*readOneMoment[^}]*\}\s*from\s*"\.\/voice-flow\.js"/,
    "settings.js no longer imports the two-store reader",
  );
  assert.match(settings, /const reading = readOneMoment\(loadMoment\(\), pcMomentStatus\)/);
  assert.match(settings, /oneMoment\.checked = reading\.on;/);
  assert.match(settings, /oneMomentDetail\.textContent = reading\.words;/);
  assert.doesNotMatch(
    settings,
    /const on = loadMoment\(\);\s*\n\s*oneMoment\.checked = on;/,
    "the row is back to painting ONLY this window's localStorage half",
  );
  // The PC's half is the page's own `get_voice_status` read, and the row
  // refreshes through the one live rule (a PC change arrives as an event, a
  // queue change or a steady read) - it is not read once at load.
  assert.match(settings, /pcMomentStatus = status;/);
  assert.match(settings, /liveRow\(\{ read: loadVoice, queue: false \}\)/);
});
