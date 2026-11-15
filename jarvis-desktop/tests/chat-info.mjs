/**
 * "About this conversation" - the small card a History row's "i" opens
 * (src/history-view.js's `chatInfoCard`, drawn by brain.js).
 *
 * The owner's ask of 2026-11-15: "does chat history have in both jarvis
 * desktop and app have an info menu that i can click show (or a symbol or
 * something) on each conversation that i can look at? that includes info like
 * if the chat was on which device (phone or laptop) and more? without this
 * being overwhelming".
 *
 * What must hold, and is pinned here:
 * - the card's exact words - title, Close, the device, the two dates, the
 *   count, and each mark's line - because the phone shows the SAME strings and
 *   a re-word on one side must fail a test, not drift;
 * - one line per fact, and nothing the row does not carry: a plain chat with
 *   no marks says only its device, its two dates and its message count;
 * - a date the PC did not send says "The PC did not say when." - never a
 *   guess and never silence;
 * - "Last used" is left out when the chat was used in the minute it started,
 *   so one time is never printed twice under two labels;
 * - a voice/taint/pin/archive line is absent when its flag is false, and the
 *   tag line appears only when this window may read tag names at all.
 *
 *   node tests/chat-info.mjs      (no browser, no Playwright; CI's frontend
 *                                  job runs every tests/*.mjs)
 */
import assert from "node:assert/strict";
import {
  chatInfoCard,
  filedUnderWords,
  deviceTag,
  messagesWords,
  whenLine,
  INFO_ARCHIVE,
  INFO_CLOSE,
  INFO_NODATE,
  INFO_OUTSIDE,
  INFO_PIN,
  INFO_TAG_NONE,
  INFO_TITLE,
  INFO_USED,
  INFO_VOICE,
} from "../src/history-view.js";

const fails = [];
const check = (name, fn) => {
  try {
    fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

// A fixed clock, so a date's words never depend on the day the suite runs.
// whenLine is the app's own local-time wording and is already pinned by
// history.mjs; here the DATE is composed through it, so the assertion is
// "the card says the app's words for that moment", not a second copy of them.
const NOW = Date.UTC(2026, 10, 15, 18, 0, 0);
const at = (h, m) => Math.floor(Date.UTC(2026, 10, 15, h, m, 0) / 1000);
const STARTED = at(14, 5);
const UPDATED = at(16, 40);
const startedWords = whenLine(STARTED, NOW);
const updatedWords = whenLine(UPDATED, NOW);
assert.ok(startedWords && updatedWords, "the fixture's times must have words");

/** The card for one row, with the two things brain.js passes from its own tag
 *  list (`tagName`, `tagsKnown`). */
const card = (c, opts = {}) => chatInfoCard(c, NOW, opts);

/** A row with every fact the PC sends - the "full card" case. */
const EVERY_MARK = Object.freeze({
  id: "c-full",
  title: "Dentist on Tuesday",
  device: "hud",
  started: STARTED,
  updated: UPDATED,
  turns: 12,
  hasVoice: true,
  tainted: true,
  pinned: true,
  archived: true,
  tagId: 3,
  kind: "chat",
});
const FULL = [
  "Had in the HUD window on this PC.",
  `Started: ${startedWords}`,
  `Last used: ${updatedWords}`,
  "12 messages",
  "Some of it was said aloud.",
  "It read text that did not come from you: a web page, a file, an email or another tool's output.",
  "Filed under: Work",
  "Pinned to the top.",
  "In Archived.",
];

check("the card's own words, exactly, in both apps", () => {
  assert.equal(INFO_TITLE, "About this conversation");
  assert.equal(INFO_CLOSE, "Close");
  assert.equal(INFO_VOICE, "Some of it was said aloud.");
  assert.equal(INFO_OUTSIDE,
    "It read text that did not come from you: a web page, a file, an email or another tool's output.");
  assert.equal(INFO_PIN, "Pinned to the top.");
  assert.equal(INFO_ARCHIVE, "In Archived.");
  assert.equal(INFO_TAG_NONE, "Not filed under a tag.");
  assert.equal(INFO_NODATE, "The PC did not say when.");
  assert.equal(INFO_USED, "Last used: ");
  assert.equal(filedUnderWords("Work"), "Filed under: Work");
});

check("the four device words are the app's own, not a second copy", () => {
  assert.equal(card({ ...EVERY_MARK, device: "desktop" }).lines[0],
    "Had in the Jarvis bar on this PC.");
  assert.equal(card({ ...EVERY_MARK, device: "hud" }).lines[0],
    "Had in the HUD window on this PC.");
  assert.equal(card({ ...EVERY_MARK, device: "phone" }).lines[0], "Had on your phone.");
  assert.equal(card({ ...EVERY_MARK, device: "" }).lines[0],
    "The PC did not say which app this was had in.");
  // The card reads the SAME table the row's tag does.
  assert.equal(deviceTag("phone").words, "Had on your phone.");
});

check("every mark: the whole card, in order, and nothing else", () => {
  const got = card(EVERY_MARK, { tagName: "Work", tagsKnown: true });
  assert.equal(got.title, "About this conversation");
  assert.equal(got.close, "Close");
  assert.deepEqual(got.lines, FULL);
});

check("a plain one: title, device, two dates, count - nothing else", () => {
  const plain = {
    id: "c-plain", title: "Boiler service", device: "desktop",
    started: STARTED, updated: UPDATED, turns: 4,
    hasVoice: false, tainted: false, pinned: false, archived: false,
    tagId: null, kind: "chat",
  };
  const got = card(plain);
  assert.deepEqual(got.lines, [
    "Had in the Jarvis bar on this PC.",
    `Started: ${startedWords}`,
    `Last used: ${updatedWords}`,
    "4 messages",
  ]);
  // Said explicitly, so a new line added for one of these facts cannot slip in.
  for (const absent of [INFO_VOICE, INFO_OUTSIDE, INFO_PIN, INFO_ARCHIVE, INFO_TAG_NONE]) {
    assert.ok(!got.lines.includes(absent), `a plain chat grew a line it does not carry: ${absent}`);
  }
});

check("a time the PC did not send says so - never a guess, never silence", () => {
  // No dates at all: one line says the PC did not say when, and the second
  // date is not the same sentence twice.
  const bare = card({ device: "phone", turns: 1 });
  assert.deepEqual(bare.lines, [
    "Had on your phone.",
    "Started: The PC did not say when.",
    "1 message",
  ]);
  // Started known, last used missing: the missing one is said, on its line.
  const half = card({ device: "desktop", started: STARTED, turns: 2 });
  assert.deepEqual(half.lines, [
    "Had in the Jarvis bar on this PC.",
    `Started: ${startedWords}`,
    "Last used: The PC did not say when.",
    "2 messages",
  ]);
  // Last used known, started missing.
  const otherHalf = card({ device: "desktop", updated: UPDATED, turns: 2 });
  assert.deepEqual(otherHalf.lines, [
    "Had in the Jarvis bar on this PC.",
    "Started: The PC did not say when.",
    `Last used: ${updatedWords}`,
    "2 messages",
  ]);
});

check("one time, not two labels for it: used in the minute it started", () => {
  const oneMoment = card({ device: "desktop", started: STARTED, updated: STARTED, turns: 3 });
  assert.deepEqual(oneMoment.lines, [
    "Had in the Jarvis bar on this PC.",
    `Started: ${startedWords}`,
    "3 messages",
  ]);
  assert.ok(!oneMoment.lines.some((l) => l.startsWith(INFO_USED)),
    "\"Last used\" repeated the start's own words");
});

check("each mark is absent while its flag is false, present while true", () => {
  const base = { device: "desktop", started: STARTED, updated: UPDATED, turns: 5 };
  const without = card(base);
  assert.deepEqual(without.lines, [
    "Had in the Jarvis bar on this PC.",
    `Started: ${startedWords}`,
    `Last used: ${updatedWords}`,
    "5 messages",
  ]);
  for (const mark of [INFO_VOICE, INFO_OUTSIDE, INFO_PIN, INFO_ARCHIVE]) {
    assert.ok(!without.lines.includes(mark), `${mark} shown with its flag false`);
  }
  // One at a time, so a line cannot depend on another mark being there.
  assert.deepEqual(card({ ...base, hasVoice: true }).lines.slice(-1), [INFO_VOICE]);
  assert.deepEqual(card({ ...base, tainted: true }).lines.slice(-1), [INFO_OUTSIDE]);
  assert.deepEqual(card({ ...base, pinned: true }).lines.slice(-1), [INFO_PIN]);
  assert.deepEqual(card({ ...base, archived: true }).lines.slice(-1), [INFO_ARCHIVE]);
});

check("the tag line is filed, unfiled, or not said at all when names are hidden", () => {
  const base = { device: "phone", started: STARTED, updated: UPDATED, turns: 1, tagId: 7 };
  // Readable tag list: always says which it is, word for word.
  assert.deepEqual(card(base, { tagName: "Work", tagsKnown: true }).lines.at(-1),
    "Filed under: Work");
  assert.deepEqual(card({ ...base, tagId: null }, { tagsKnown: true }).lines.at(-1),
    "Not filed under a tag.");
  // Hidden memory lists / App lock: the window may not read tag names, so it
  // says nothing rather than claim a chat is unfiled.
  const hidden = card(base, { tagName: "", tagsKnown: false });
  assert.ok(!hidden.lines.some((l) => l.startsWith("Filed under") || l === INFO_TAG_NONE),
    "a hidden tag list still spoke about filing");
  // The name is the PC's spelling, trimmed, never re-worded.
  assert.equal(filedUnderWords("  Home  "), "Filed under: Home");
});

check("message count is the app's own word, singular or plural", () => {
  assert.equal(messagesWords(1), "1 message");
  assert.equal(card({ turns: 1 }).lines.at(-1), "1 message");
  assert.equal(card({ turns: 12 }).lines.at(-1), "12 messages");
  // A row the PC sent no count for says none, not "NaN messages".
  assert.equal(card({}).lines.at(-1), "0 messages");
});

check("the card is read-only data: no request, no write, no extra fact", () => {
  // A row carrying everything the PC sends, including fields the card is not
  // allowed to show, must produce exactly the same lines as the full card.
  const noisy = {
    ...EVERY_MARK,
    project: "Home",
    hidden: true,
    snippet: { role: "user", parts: [{ text: "x", hit: true }] },
    hits: 3,
  };
  assert.deepEqual(card(noisy, { tagName: "Work", tagsKnown: true }).lines, FULL);
});

console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe conversation info card says the row's own facts, one line each, in both apps' words");
process.exit(fails.length ? 1 : 0);
