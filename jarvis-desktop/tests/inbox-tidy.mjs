/**
 * "Inbox tidy by voice" on the desktop (the owner's decision of 2026-09-28;
 * JARVIS-API.md section 92; src/inbox-tidy.js, src/main.js, src/index.html,
 * src-tauri/src/brain/inbox_tidy.rs).
 *
 * What must hold:
 * - the words are the PC's and the phone's, word for word (the contract file's
 *   `words`, made by tools/gen_inbox_tidy_cases.py, and net/InboxTidy.kt);
 * - every real status reads, and the strip says what the contract's `strip`
 *   rows say for it: an ordinary one, Jarvis locked (only that the inbox was
 *   tidied, no count), the link stale (Undo held, and why), several tidies
 *   open (the newest, the others counted);
 * - the minutes run down while the link is down, and an Undo whose ten
 *   minutes are up is gone;
 * - the strip: Undo sends ONE call, never twice; held on a stale link and
 *   while locked (the button is off and the words say why); the PC's own
 *   sentence is shown after it; a refusal is shown as it is;
 * - a tidy's approval card is an email-shaped card: shown verbatim, and
 *   approved only in the Jarvis bar, never from the widget's one line;
 * - CONTROL: the two commands are the Jarvis bar's alone; Rust holds Undo on
 *   a stale link and while the words are hidden, and takes the words out of
 *   a read then; the strip holds no sender or subject.
 *
 * Needs no browser: a tiny stand-in for the few DOM calls the strip makes.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  aged,
  leftWords,
  mountInboxTidy,
  readStatus,
  stripFor,
  WORDS,
} from "../src/inbox-tidy.js";
import { emailDetail, isEmailCard, TIDY_DETAIL } from "../src/email-sending.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/inbox-tidy-cases.json"));
const C = CASES.cases;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── a stand-in for the few DOM calls the strip makes ─────────────────── */

class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {};
    this.hidden = false; this.disabled = false; this.className = ""; this._text = ""; this.type = "";
  }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); }
  append(...kids) { this.children.push(...kids); }
  replaceChildren(...kids) { this.children = kids; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  async click() { for (const fn of this.listeners.click || []) await fn(); }
}
globalThis.document = { createElement: (tag) => new El(tag), hidden: false };

function mount(over = {}) {
  const box = new El("section");
  box.hidden = true;
  const calls = [];
  const timers = [];
  const laters = [];
  let stale = false;
  const clock = { t: 1_000_000 };
  const view = mountInboxTidy(box, {
    invoke: over.invoke || (async (command) => {
      calls.push(command);
      throw new Error("no answer");
    }),
    isStale: () => stale,
    announce: over.announce || (() => {}),
    onChange: () => {},
    now: () => clock.t,
    setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimer: () => {},
    visible: () => true,
    later: (fn, ms) => { laters.push({ fn, ms }); },
  });
  return { box, view, calls, timers, laters, clock, setStale: (v) => { stale = v; } };
}

const undoRow = (box) => box.children[1];
const undoButton = (box) => undoRow(box).children[1];

/* ── the words, the answers, the rule ─────────────────────────────────── */

await check("the words are the contract's and the phone's, word for word", async () => {
  assert.deepEqual({ ...WORDS }, CASES.words);
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/InboxTidy.kt")
    .replace(/"\s*\+\s*\n\s*"/g, "");
  for (const [key, words] of Object.entries(CASES.words)) {
    assert.ok(kt.includes(`"${key}" to "${words.replace(/"/g, "\\\"")}"`),
      `the phone does not say ${key}: ${words}`);
  }
  assert.equal(CASES.routes.status, "/api/email/tidy");
  assert.equal(CASES.routes.undo, "/api/email/tidy/undo");
  assert.equal(CASES.undo_minutes, 10);
});

await check("every real status reads", async () => {
  const idle = readStatus(C.status_idle.body);
  assert.equal(idle.available, true);
  assert.equal(idle.undo, null);
  const open = readStatus(C.status_undo.body);
  assert.equal(open.undo.count, 3);
  assert.equal(open.undo.action, "archive");
  assert.equal(open.undo.said, "Archived 3 emails.");
  assert.equal(open.undo.minutesLeft, 10);
  assert.equal(open.undo.more, 0);
  const two = readStatus(C.status_undo_two.body);
  assert.equal(two.undo.action, "mark_read");
  assert.equal(two.undo.more, 1);
  assert.equal(readStatus(C.status_undo_last_minute.body).undo.minutesLeft, 1);
  assert.deepEqual(readStatus(null), { available: false, hidden: false, undo: null });
  assert.equal(readStatus({ undo: { said: "x" } }).undo, null, "no minutes: not an Undo");
  assert.equal(readStatus({ undo: { minutes_left: 3 } }).undo, null, "no words: not an Undo");
});

await check("the strip says what the contract's rows say, for every situation", async () => {
  assert.ok(CASES.strip.length >= 20);
  for (const row of CASES.strip) {
    const got = stripFor(readStatus({ ...C[row.case].body, hidden: row.locked }),
      { locked: row.locked, stale: row.stale });
    assert.deepEqual(got, row.expect, `${row.case} locked=${row.locked} stale=${row.stale}`);
  }
});

await check("locked: no count, no action, no words of the PC's - only that it was tidied", async () => {
  const s = stripFor(readStatus({ ...C.status_undo_two.body, hidden: true }), { locked: true });
  assert.equal(s.text, WORDS.hidden);
  assert.equal(s.can_undo, false);
  assert.equal(s.note, WORDS.locked);
  assert.ok(!/Archived|Marked|earlier/.test(s.text));
});

await check("the minutes run down, and an Undo out of time is gone", async () => {
  const st = readStatus(C.status_undo.body);            // 570 seconds left when read
  assert.equal(aged(st, 0).undo.minutesLeft, 10);
  assert.equal(aged(st, 30_000).undo.minutesLeft, 9);
  assert.equal(aged(st, 30_000).undo.secondsLeft, 540);
  assert.equal(aged(st, 569_000).undo.minutesLeft, 1);
  assert.equal(aged(st, 570_000).undo, null);
  assert.equal(aged(st, 9_999_999).undo, null);
  assert.equal(aged({ available: true, undo: null }, 5000).undo, null);
  assert.equal(leftWords(3), "3 min left to undo");
});

/* ── the strip itself ─────────────────────────────────────────────────── */

await check("nothing open: the strip is hidden; a tidy open: it shows, with Undo", async () => {
  let body = C.status_idle.body;
  const m = mount({ invoke: async () => body });
  await m.view.refresh();
  assert.equal(m.box.hidden, true);
  body = C.status_undo.body;
  await m.view.refresh();
  const v = m.view.view();
  assert.equal(v.hidden, false);
  assert.equal(v.text, "Archived 3 emails.");
  assert.equal(v.left, "10 min left to undo");
  assert.equal(v.disabled, false);
  assert.equal(undoButton(m.box).textContent, "Undo");
  m.clock.t += 601_000;                                    // ten minutes later, link down
  m.timers[0].fn();
  assert.equal(m.view.view().hidden, false, "a poll that fails changes nothing");
});

await check("it polls on its own while the bar is showing", async () => {
  const m = mount({ invoke: async () => C.status_idle.body });
  assert.equal(m.timers.length, 1);
  assert.equal(m.timers[0].ms, 20000);
});

await check("a stale link: Undo is off and the words say why", async () => {
  const m = mount({ invoke: async () => C.status_undo.body });
  await m.view.refresh();
  m.setStale(true);
  await m.view.refresh();
  const v = m.view.view();
  assert.equal(v.disabled, true);
  assert.equal(v.note, WORDS.stale);
});

await check("locked (Rust took the words out): only that it was tidied, Undo off", async () => {
  const m = mount({ invoke: async () => ({ ...C.status_undo_two.body, hidden: true,
    undo: { ...C.status_undo_two.body.undo, said: WORDS.hidden, count: 0, action: "", more: 0 } }) });
  await m.view.refresh();
  const v = m.view.view();
  assert.equal(v.text, WORDS.hidden);
  assert.equal(v.disabled, true);
  assert.equal(v.note, WORDS.locked);
});

await check("Undo sends ONE call, shows the PC's sentence, and never doubles", async () => {
  const calls = [];
  const said = [];
  let phase = "open";
  const m = mount({
    invoke: async (command) => {
      calls.push(command);
      if (command === "inbox_tidy_read") return phase === "open" ? C.status_undo.body : C.status_idle.body;
      phase = "done";
      return { ...C.undo_done.body, http: 200 };
    },
    announce: (t) => said.push(t),
  });
  await m.view.refresh();
  const first = undoButton(m.box).click();
  const second = undoButton(m.box).click();               // a double tap
  await Promise.all([first, second]);
  assert.equal(calls.filter((c) => c === "inbox_tidy_undo").length, 1);
  const v = m.view.view();
  assert.equal(v.text, C.undo_done.body.message, "the sentence is shown, alone, after the Undo");
  assert.equal(said.at(-1), C.undo_done.body.message);
  assert.equal(m.laters.at(-1).ms, 8000);
  m.laters.at(-1).fn();                                    // a few seconds later
  assert.equal(m.view.view().hidden, true);
});

await check("a refusal is shown as the PC or Rust said it, and Undo stays available", async () => {
  const m = mount({
    invoke: async (command) => {
      if (command === "inbox_tidy_read") return C.status_undo.body;
      throw new Error(C.undo_unreachable.body.error);
    },
  });
  await m.view.refresh();
  await undoButton(m.box).click();
  const v = m.view.view();
  assert.equal(v.note, C.undo_unreachable.body.error);
  assert.equal(v.disabled, false, "a failed Undo can be tried again");
  assert.equal(v.hidden, false);
});

await check("watchQuickly reads again a few times, then stops", async () => {
  let reads = 0;
  const m = mount({ invoke: async () => { reads += 1; return C.status_idle.body; } });
  const before = m.timers.length;
  m.view.watchQuickly();
  assert.equal(m.timers.length, before + 1);
  assert.equal(m.timers.at(-1).ms, 3000);
  for (let i = 0; i < 6; i += 1) await m.timers.at(-1).fn();
  assert.equal(reads, 6);
});

/* ── an approval card that lists the owner's mail ─────────────────────── */

await check("a tidy's card is email-shaped: verbatim, approved only in the Jarvis bar", async () => {
  assert.equal(isEmailCard({ action: "tidy_inbox" }), true);
  assert.equal(emailDetail({ action: "tidy_inbox" }), TIDY_DETAIL);
  assert.match(TIDY_DETAIL, /Jarvis bar/);
  const rs = read("src-tauri/src/email_sending.rs");
  assert.match(rs, /TIDY_INBOX_ACTION: &str = "tidy_inbox"/);
  assert.match(rs, /action == Some\(TIDY_INBOX_ACTION\)/);
  const widget = read("src/widget.js");
  assert.match(widget, /emailDetail\(approval\)/);
});

/* ── CONTROL: what the source promises ────────────────────────────────── */

await check("CONTROL: the two commands are the Jarvis bar's alone, and Undo cannot start a tidy", async () => {
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  const i = surfaces.indexOf('identifier = "inbox-tidy"');
  assert.ok(i > 0, "a permission set for it");
  const block = surfaces.slice(i, i + 700);
  assert.match(block, /allow-inbox-tidy-read/);
  assert.match(block, /allow-inbox-tidy-undo/);
  assert.equal((block.match(/allow-/g) || []).length, 2, "nothing else in the set");
  for (const file of ["quickbar"]) {
    assert.match(read(`src-tauri/capabilities/${file}.json`), /"inbox-tidy"/);
  }
  for (const file of ["brain", "settings", "widget", "hud", "faces", "floating", "live-badge",
    "onboarding"]) {
    assert.doesNotMatch(read(`src-tauri/capabilities/${file}.json`), /"inbox-tidy"/,
      `${file} must not hold it`);
  }
  const build = read("src-tauri/build.rs");
  assert.match(build, /"inbox_tidy_read"/);
  assert.match(build, /"inbox_tidy_undo"/);
  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /brain::inbox_tidy::inbox_tidy_read/);
  assert.match(lib, /brain::inbox_tidy::inbox_tidy_undo/);
});

await check("CONTROL: Rust holds Undo on a stale link and while the words are hidden; a read is redacted then", async () => {
  const rs = read("src-tauri/src/brain/inbox_tidy.rs");
  const undo = rs.slice(rs.indexOf("pub async fn inbox_tidy_undo"));
  assert.ok(undo.indexOf("words_hidden(&app)") > 0 && undo.indexOf("stale(&app)") > 0);
  assert.ok(undo.indexOf("words_hidden(&app)") < undo.indexOf(".post("), "held before anything is sent");
  assert.ok(undo.indexOf("stale(&app)") < undo.indexOf(".post("));
  const readFn = rs.slice(rs.indexOf("pub async fn inbox_tidy_read"), rs.indexOf("pub async fn inbox_tidy_undo"));
  assert.match(readFn, /redact\(answer\)/);
  assert.doesNotMatch(readFn, /\.post\(/, "a read never posts");
  assert.match(rs, /crate::lock::app_locked\(app\)/);
  assert.match(rs, /crate::lock::private_hidden\(app\)/);
  assert.doesNotMatch(rs, /answer_approval|jarvis_gate|\/api\/approve/, "it approves nothing");
});

await check("CONTROL: the strip holds no sender or subject, and the page draws it with textContent", async () => {
  const js = read("src/inbox-tidy.js");
  assert.doesNotMatch(js, /innerHTML/);
  assert.doesNotMatch(js, /sender_name|\.subject\b|\.sender\b/);
  const html = read("src/index.html");
  assert.match(html, /id="inbox-tidy"/);
  const blob = JSON.stringify(CASES);
  for (const word of ["Shop Weekly", "weekly digest", "news@shop", "Sam Smith", "Lunch on Friday"]) {
    assert.ok(!blob.includes(word), `the contract holds ${word}`);
  }
  const main = read("src/main.js");
  assert.match(main, /mountInboxTidy\(dom\.inboxTidy/);
  assert.match(main, /watchQuickly\(\)/);
});

await check("a11y: the strip is named, and its sentence is a live region", async () => {
  const m = mount({ invoke: async () => C.status_undo.body });
  await m.view.refresh();
  assert.equal(m.box.attrs["aria-label"], WORDS.title);
  assert.equal(m.box.children[2].attrs.role, "status");
  assert.equal(undoButton(m.box).type, "button");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall inbox-tidy checks passed");
