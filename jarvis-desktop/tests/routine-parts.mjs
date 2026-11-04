/**
 * A reminder that is a ROUTINE - up to twelve parts, each with its own time and
 * its own question - on the desktop HUD (2026-11-03; the owner's ask, Gemini's
 * Q8/Q9 rulings, BUILD-SPEC section 5).
 *
 *   node tests/routine-parts.mjs
 *
 * WHAT THIS IS. The desktop half of "multi-part reminders": the ONE parts
 * builder both doors use (the Add form for a new routine, the row editor for an
 * existing one), the per-part list and buttons a row draws, and the Rust command
 * fields that carry them. Nothing here creates a second creation path, and
 * nothing here bypasses the PC's own validation - `jarvis_schedule._clean_steps`
 * is the authority and refuses in one plain sentence, which the form shows.
 *
 * HOW IT RUNS WITHOUT A BROWSER. The page is vendored from the backend and must
 * stay byte-identical, so its reminders script cannot become a module. This
 * suite therefore takes the REAL functions out of the page by name and RUNS
 * them - `partsBody` is pure, and `partsOf`/`partsFromJob` are given the two
 * globals they read - so what is asserted is the code the HUD runs, not a copy
 * of it. CI's `frontend` job runs this suite with every other tests/*.mjs.
 *
 * WHAT IS PROVEN:
 *
 *   1. the body a save makes is the shape the PC's `_clean_steps` takes: 2 to
 *      12 parts, ONE time per part (a clock time, minutes after the start, or
 *      neither = "after the part before"), a part's own words, and its question
 *      as the SAME block a reminder's own question is;
 *   2. every refusal is one plain sentence, and a shape this app cannot mean
 *      never leaves it - a single part, thirteen, two times at once, a time that
 *      is not HH:MM, minutes past a day, an empty label;
 *   3. the PC's own parts are read without inventing anything: the EFFECTIVE
 *      buttons (its own, or the ONE implicit Done), the times, the marks, and no
 *      part at all while App lock hides the words (the PC blanks the labels);
 *   4. a row that has gone off says WHICH part ("Morning routine - 2 of 4") and
 *      each part carries its own buttons, pressed with the part's INDEX too -
 *      never a label;
 *   5. there is ONE builder: `partsInto`/`partsRead`/`partsBody` are each
 *      defined once and called from both the Add form and the row editor, and no
 *      second script block was added to the page;
 *   6. the Rust door carries them: `ScheduleChange` has `steps` (and `action`),
 *      `answer_body` takes the part's index with the PC's own ceiling, and
 *      `hud_add_body` refuses a thirteenth part - so the page's `steps` is never
 *      dropped by `deny_unknown_fields` and never silently refused;
 *   7. the three vendored copies of the page are byte-identical.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const SRC_PATH = join(ROOT, "src", "jarvis_hud.html");
const SRC = readFileSync(SRC_PATH, "utf8");
const RUST = readFileSync(join(ROOT, "src-tauri", "src", "brain", "schedule.rs"), "utf8");
const CMD = readFileSync(join(ROOT, "src-tauri", "src", "hud_schedule.rs"), "utf8");

/** The page is vendored three times and the copies must stay byte-identical:
 *  the desktop app serves src/, the published base carries backend/, and the
 *  backend test suite compares them (backend/test_vendored_three.py). */
const COPIES = [
  ["desktop src", SRC_PATH],
  ["backend", join(ROOT, "..", "backend", "jarvis_hud.html")],
  ["jarvis-backend", join(ROOT, "..", "jarvis-backend", "jarvis_hud.html")],
];

let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`ok   ${name}`);
  } catch (e) {
    console.error(`FAIL ${name}\n     ${e.message}`);
    process.exitCode = 1;
  }
}

/** Everything from `start` to the brace that closes the block that opened
 *  there, counting braces and stepping over strings and comments. */
function balanced(text, start) {
  let depth = 0;
  let opened = false;
  for (let at = start; at < text.length; at += 1) {
    const ch = text[at];
    if (ch === '"' || ch === "'" || ch === "`") {
      const quote = ch;
      at += 1;
      while (at < text.length && text[at] !== quote) {
        if (text[at] === "\\") at += 1;
        at += 1;
      }
      continue;
    }
    if (ch === "/" && text[at + 1] === "/") {
      while (at < text.length && text[at] !== "\n") at += 1;
      continue;
    }
    if (ch === "/" && text[at + 1] === "*") {
      const end = text.indexOf("*/", at + 2);
      at = end < 0 ? text.length : end + 1;
      continue;
    }
    if (ch === "{") {
      depth += 1;
      opened = true;
    } else if (ch === "}") {
      depth -= 1;
      if (opened && depth === 0) return text.slice(start, at + 1);
    }
  }
  throw new Error(`a block opened at ${start} is never closed`);
}

/** One `function name(...) { ... }` cut out of the page, by name. */
function fnFromPage(name) {
  const at = SRC.indexOf(`function ${name}(`);
  assert.ok(at >= 0, `the HUD page has no ${name}() at all`);
  const open = SRC.indexOf("{", at);
  assert.ok(open > at, `${name}() has no body`);
  const block = balanced(SRC.slice(open), 0);
  return SRC.slice(at, open + block.length);
}

/** The page's own pure functions, called for real. `txt` and `ASK_DOES` are the
 *  two globals `partsOf` reads; everything else is self-contained. */
const page = new Function(
  "txt",
  "ASK_DOES",
  `${fnFromPage("partsOf")}
   ${fnFromPage("partWhenWords")}
   ${fnFromPage("titleWithPart")}
   ${fnFromPage("partsBody")}
   ${fnFromPage("partsFromJob")}
   return { partsOf, partWhenWords, titleWithPart, partsBody, partsFromJob };`,
)((v) => (typeof v === "string" ? v : ""), ["record", "done", "snooze"]);

const ASKS = ["done", "record", "snooze"];

/* ------------------------------------------------------------------ *
 * 1. The body a save makes is the shape the PC's `_clean_steps` takes.
 * ------------------------------------------------------------------ */

check("a routine's body is 2..12 parts, each with ONE time and its own words", () => {
  const body = page.partsBody([
    { label: "  meds  ", when: "minutes", minutes: 0 },
    { label: "keys", when: "after" },
    { label: "badge", when: "after" },
    { label: "leave", when: "at", at: "08:30",
      ask: { question: "Did you lock the door?",
             buttons: [{ label: "Locked", does: "record" }],
             record: { history: true } } },
  ]);
  assert.deepEqual(body, [
    // Tidied, and NEVER an id: the PC numbers the parts itself, so a page can
    // never name one (§2.3 of the spec).
    { label: "meds", offset_min: 0 },
    // "After the part before" is neither key at all - never a time of zero.
    { label: "keys" },
    { label: "badge" },
    // A part's question is the SAME block a reminder's own question is.
    { label: "leave", at: "08:30",
      ask: { question: "Did you lock the door?",
             buttons: [{ label: "Locked", does: "record" }],
             record: { history: true } } },
  ]);
  // No parts typed at all: no `steps` key is sent, so a plain reminder is
  // created exactly as it was before this feature.
  assert.deepEqual(page.partsBody([]), []);
  assert.deepEqual(page.partsBody(null), []);
  // Twelve is a routine; the body is the PC's own shape for the lot.
  const twelve = [];
  for (let i = 0; i < 12; i += 1) {
    twelve.push({ label: `part ${i}`, when: "minutes", minutes: i });
  }
  assert.equal(page.partsBody(twelve).length, 12);
});

check("every refusal is one plain sentence, before anything is sent", () => {
  const err = (rows) => {
    const out = page.partsBody(rows);
    assert.ok(out instanceof Error, `not refused: ${JSON.stringify(rows)}`);
    return out.message;
  };
  assert.equal(err([{ label: "one", when: "after" }]),
    "A routine needs at least two parts - a single part is just a reminder.");
  const thirteen = [];
  for (let i = 0; i < 13; i += 1) thirteen.push({ label: `part ${i}`, when: "after" });
  assert.equal(err(thirteen), "A routine has up to 12 parts.");
  assert.equal(err([{ label: "", when: "after" }, { label: "b", when: "after" }]),
    "Every part needs its own words.");
  assert.equal(err([{ label: "   ", when: "after" }, { label: "b", when: "after" }]),
    "Every part needs its own words.");
  assert.equal(err([{ label: "x".repeat(81), when: "after" },
                    { label: "b", when: "after" }]),
    "A part's words are up to 80 characters.");
  assert.equal(err([{ label: "a", when: "at", at: "9:30" }, { label: "b", when: "after" }]),
    "A part's time looks like 09:30.");
  assert.equal(err([{ label: "a", when: "at", at: "25:00" }, { label: "b", when: "after" }]),
    "A part's time looks like 09:30.");
  assert.equal(err([{ label: "a", when: "at", at: "" }, { label: "b", when: "after" }]),
    "A part's time looks like 09:30.");
  for (const minutes of [-1, 1441, 1.5, NaN]) {
    assert.equal(
      err([{ label: "a", when: "minutes", minutes }, { label: "b", when: "after" }]),
      "A part is 0 to 1440 minutes after the start.",
      `minutes ${minutes} was not refused`);
  }
  // A part's own question is checked by the SAME rules a reminder's is, and its
  // sentence arrives here as it is rather than being retyped.
  const asked = err([{ label: "a", when: "after", ask: new Error("A question needs at least one button - that is what you press when it goes off.") },
                     { label: "b", when: "after" }]);
  assert.equal(asked,
    "A question needs at least one button - that is what you press when it goes off.");
});

/* ------------------------------------------------------------------ *
 * 2. The PC's own parts are read without inventing anything.
 * ------------------------------------------------------------------ */

check("the PC's parts are read as it drew them, with the EFFECTIVE buttons", () => {
  const parts = page.partsOf({
    steps_parts: 3, steps_cursor: 1,
    steps: [
      { id: "p1", label: "meds", offset_min: 0, at: null, when: "08:00",
        ask: { question: "Taken?", buttons: [{ label: "Taken", does: "record" }],
               record: { history: true } },
        buttons: [{ label: "Taken", does: "record" }],
        fired_at: 1762192800.0, done: true, missed: false, current: false },
      { id: "p2", label: "keys", offset_min: null, at: null,
        buttons: [{ label: "Done", does: "done" }],
        fired_at: 1762193100.0, done: false, missed: true, current: true },
      { id: "p3", label: "badge", offset_min: 30, at: null, when: "08:30",
        buttons: [], fired_at: null, done: false, missed: false, current: false },
    ],
  });
  assert.equal(parts.length, 3);
  assert.deepEqual(parts[0].buttons, [{ label: "Taken", does: "record" }]);
  assert.equal(parts[0].done, true);
  assert.equal(parts[0].ask.question, "Taken?");
  // A plain checklist line: the PC hands out the ONE implicit Done, and the page
  // draws THAT rather than inventing a label of its own.
  assert.deepEqual(parts[1].buttons, [{ label: "Done", does: "done" }]);
  assert.equal(parts[1].ask, null);
  assert.equal(parts[1].missed, true);
  assert.equal(parts[1].current, true);
  assert.equal(parts[2].offsetMin, 30);
  assert.equal(parts[2].when, "08:30");
  // A part whose words the PC blanked (App lock / hidden lists) draws NOTHING -
  // the row still shows its count and times, and there is no label to leak.
  const hiddenParts = page.partsOf({
    steps_parts: 2, steps_cursor: 0,
    steps: [{ label: "", offset_min: 0, when: "08:00", buttons: [] },
            { label: "", offset_min: 30, when: "08:30", buttons: [] }],
  });
  assert.deepEqual(hiddenParts, []);
  // A row with no parts at all - every row written before today - draws nothing.
  assert.deepEqual(page.partsOf({ text: "Call Mum" }), []);
  assert.deepEqual(page.partsOf(null), []);
  // A shape the page does not understand is dropped, never half-drawn.
  assert.deepEqual(page.partsOf({ steps: "nonsense" }), []);
  assert.deepEqual(page.partsOf({ steps: [null, 4, { label: "" }] }), []);
  // A button whose verb is not one of the three is dropped with its part's
  // others; the PC never sends one, so this only guards a hand-edited row.
  const odd = page.partsOf({ steps: [{ label: "a", buttons: [{ label: "Go", does: "shell" }] }] });
  assert.deepEqual(odd[0].buttons, [{ label: "Done", does: "done" }]);
  for (const does of ASKS) {
    const one = page.partsOf({ steps: [{ label: "a", buttons: [{ label: "L", does }] }] });
    assert.equal(one[0].buttons[0].does, does);
  }
});

check("a part's time is said in the owner's words, never a bare number", () => {
  assert.equal(page.partWhenWords({ when: "08:30" }), "08:30");
  assert.equal(page.partWhenWords({ when: "", offsetMin: 0 }), "at the start");
  assert.equal(page.partWhenWords({ when: "", offsetMin: 45 }), "45 min after the start");
  // An untimed part is surfaced by the part before it, and says so.
  assert.equal(page.partWhenWords({ when: "", offsetMin: null }),
    "after the part before it");
});

check("a row that has gone off says WHICH part, and a quiet one does not", () => {
  const job = { partsCount: 4, partsCursor: 1 };
  assert.equal(page.titleWithPart("Morning routine", job, true),
    "Morning routine \u00b7 2 of 4");
  // A routine waiting for its first part is a reminder with a list under it -
  // "1 of 4" there would be a count that means nothing yet.
  assert.equal(page.titleWithPart("Morning routine", job, false), "Morning routine");
  // A plain reminder grows no suffix, whatever was passed.
  assert.equal(page.titleWithPart("Call Mum", { partsCount: 0, partsCursor: 0 }, true),
    "Call Mum");
  // The PC's cursor is 0-based; the owner reads 1-based, and it never runs past
  // the count.
  assert.equal(page.titleWithPart("R", { partsCount: 2, partsCursor: 1 }, true),
    "R \u00b7 2 of 2");
  assert.equal(page.titleWithPart("R", { partsCount: 2, partsCursor: 9 }, true),
    "R \u00b7 2 of 2");
});

check("an existing routine opens as the PC holds it, so nothing is retyped", () => {
  const job = { parts: page.partsOf({ steps: [
    { label: "meds", offset_min: 0, at: null, when: "08:00",
      buttons: [{ label: "Taken", does: "record" }],
      ask: { question: "Taken?",
             buttons: [{ label: "Taken", does: "record" },
                       { label: "Later", does: "snooze", minutes: 30 }],
             record: { history: true, obsidian_daily: true, goal: "g-1" } } },
    { label: "keys", offset_min: null, at: null, buttons: [] },
    { label: "leave", offset_min: null, at: "08:30", when: "08:30", buttons: [] },
    { label: "badge", offset_min: 60, at: null, when: "09:00", buttons: [] },
  ] }) };
  const rows = page.partsFromJob(job);
  assert.deepEqual(rows.map((r) => r.when), ["minutes", "after", "at", "minutes"]);
  assert.equal(rows[0].minutes, 0);
  assert.equal(rows[2].at, "08:30");
  assert.equal(rows[3].minutes, 60);
  assert.equal(rows[0].ask.question, "Taken?");
  assert.equal(rows[1].ask, null);
  // Round trip: what the editor holds saves back to the shape the PC stored
  // (minus the ids it numbers itself), so an untouched routine sends nothing.
  // EVERY part of the question survives, destinations included - an editor that
  // dropped where an answer is written would silently change what a button does.
  const body = page.partsBody(rows);
  assert.deepEqual(body, [
    { label: "meds", offset_min: 0,
      ask: { question: "Taken?",
             buttons: [{ label: "Taken", does: "record" },
                       { label: "Later", does: "snooze", minutes: 30 }],
             record: { history: true, obsidian_daily: true, goal: "g-1" } } },
    { label: "keys" },
    // An `at` part keeps its clock time even though it HAS an offset in the
    // drawn shape; the body never carries both.
    { label: "leave", at: "08:30" },
    { label: "badge", offset_min: 60 },
  ]);
  // A question with no destination at all carries no `record` key, so the PC
  // reads it exactly as one that never had any.
  const bare = page.partsBody([
    { label: "a", when: "after", ask: { question: "Q?", buttons: [{ label: "Yes", does: "done" }] } },
    { label: "b", when: "after" },
  ]);
  assert.equal(bare[0].ask.record, undefined);
  assert.deepEqual(page.partsFromJob(null), []);
  assert.deepEqual(page.partsFromJob({}), []);
});

/* ------------------------------------------------------------------ *
 * 3. ONE builder, both doors, no second creation or edit path.
 * ------------------------------------------------------------------ */

check("there is ONE parts builder, and both doors call it", () => {
  for (const name of ["partsInto", "partsRead", "partsBody", "partsFromJob", "partRowOf"]) {
    const defs = [...SRC.matchAll(new RegExp(`function ${name}\\(`, "g"))];
    assert.equal(defs.length, 1, `${name}() is defined ${defs.length} times`);
  }
  const add = SRC.slice(SRC.indexOf("function submitAdd("),
    SRC.indexOf("/* ---- start ---"));
  assert.match(add, /partsBody\(partsRead\(partsHost\)\)/,
    "the Add form does not build its parts with the shared builder");
  assert.match(add, /args\.steps = routineParts/,
    "the Add form never sends `steps` to hud_schedule_add");
  const editor = SRC.slice(SRC.indexOf("function openEditor("),
    SRC.indexOf("function submitEdit("));
  assert.match(editor, /partsInto\(partsHost, partsFromJob\(job\)\)/,
    "the row editor does not draw the parts with the shared builder");
  const save = SRC.slice(SRC.indexOf("function submitEdit("),
    SRC.indexOf("function rowOf("));
  assert.match(save, /out\.steps = now/,
    "the row editor never sends the parts it holds through `change`");
  // Both are the SAME `hud_schedule_act` change path: one command, no second
  // edit door, and a repeat edit keeps its ONE card.
  assert.match(save, /change\(job, "edit", out, \{/,
    "the row editor no longer saves through the one change path");
});

check("a routine is only offered when the PC says it can keep one", () => {
  // The PC's own additive marker, exactly like `phase2` / `actions` / `asks`.
  assert.match(SRC, /steps: available && src\.steps === true,/,
    "the read does not carry the PC's `steps` marker");
  const sync = SRC.slice(SRC.indexOf("function syncForm("), SRC.indexOf("function syncThen("));
  assert.match(sync, /var canRoutine = kind === "reminder" && !!\(view && view\.steps\);/,
    "the parts block is not gated on the PC's own marker");
  assert.match(sync, /if \(\$\("rem-parts-row"\)\) \$\("rem-parts-row"\)\.hidden = !canRoutine;/,
    "the parts row is never hidden for a PC that cannot keep parts");
  // A routine's OWN "Then" is not offered: the PC fires a routine's action only
  // for a PART, so it would promise something that never happens.
  assert.match(sync, /&& !routineNow;/,
    "the Add form still offers a routine its own action");
  // The row editor is gated the same way.
  assert.match(SRC, /if \(job\.kind === "reminder" && view && view\.steps === true\) \{/,
    "the row editor draws the parts editor whatever the PC said");
});

check("a part answers ITS OWN part, by index, and never by a label", () => {
  const painter = SRC.slice(SRC.indexOf("function partsListOf("),
    SRC.indexOf("function group("));
  assert.match(painter, /answer\(job, buttonIndex, btn, index\)/,
    "a part's button does not carry WHICH part it answers");
  assert.match(painter, /el\("button", "rem-btn rem-answer", b\.label\)/,
    "a part's button does not take its words from the PC's own list");
  assert.doesNotMatch(painter, /rem-answer", "/,
    "a part's button has words typed into the page instead of the PC's");
  const answer = SRC.slice(SRC.indexOf("function answer("), SRC.indexOf("function openButtonOf("));
  assert.match(answer, /if \(typeof step === "number"\) args\.step = step;/,
    "the answer invoke never carries the part's index");
  assert.match(answer, /action: "answer", button: index/,
    "the answer invoke no longer carries the button's index");
  // A row with parts answers a PART, never the row's own question.
  assert.match(SRC.slice(SRC.indexOf("function askBarOf("), SRC.indexOf("function answer(")),
    /if \(job\.parts && job\.parts\.length\) return null;/,
    "a routine still draws the row's own question buttons");
  // The parts are drawn for real, and the marks are the PC's own words.
  assert.match(painter, /if \(wentOff && part\.firedAt !== null\) \{/,
    "a part that has not come up yet still draws buttons the PC would refuse");
  assert.match(painter, /part\.done \? "done" : \(part\.missed \? "missed"/,
    "a part's mark no longer comes from the PC's own done/missed flags");
});

check("no second inline script block was added to the page", () => {
  const blocks = [...SRC.replace(/<!--[\s\S]*?-->/g, "").matchAll(/<script\b([^>]*)>/g)]
    .filter((m) => !/\bsrc\s*=/.test(m[1]));
  assert.equal(blocks.length, 4,
    `jarvis_hud.html has ${blocks.length} inline script blocks; the parts editor ` +
    "must live inside the reminders IIFE (tests/csp-inline.mjs holds the count)");
  // ...and the parts code really is INSIDE that block: after its start and
  // before its closing IIFE.
  const start = SRC.indexOf("// ---- The Reminders tab (2026-10-21");
  const end = SRC.indexOf("/* ---- the fixed Stop everything control");
  const at = SRC.indexOf("function partsBody(");
  assert.ok(start >= 0 && end > start, "the reminders IIFE's bounds moved");
  assert.ok(at > start && at < end,
    "the parts builder is outside the reminders script block");
});

/* ------------------------------------------------------------------ *
 * 4. The Rust door carries them (so `deny_unknown_fields` cannot eat them).
 * ------------------------------------------------------------------ */

check("the Rust change carries `steps` and `action`, and the ask shape is shared", () => {
  const change = RUST.slice(RUST.indexOf("pub struct ScheduleChange {"),
    RUST.indexOf("pub(crate) fn change_timeout("));
  assert.match(change, /pub steps: Option<serde_json::Value>,/,
    "ScheduleChange has no `steps` - deny_unknown_fields would refuse the page's save");
  assert.match(change, /pub action: Option<serde_json::Value>,/,
    "ScheduleChange has no `action`, so an existing question cannot be edited");
  assert.match(RUST, /pub\(crate\) const MAX_STEPS: u32 = 12;/,
    "the Rust ceiling is not the PC's 12");
  const body = RUST.slice(RUST.indexOf("pub(crate) fn change_body("),
    RUST.indexOf("pub(crate) const REMINDERS_FORM_HINT"));
  assert.match(body, /body\.insert\("steps"\.into\(\), steps_body\(raw\)\?\);/,
    "one edit does not carry the parts");
  const add = RUST.slice(RUST.indexOf("pub(crate) fn hud_add_body("),
    RUST.indexOf("fn joined_words("));
  assert.match(add, /steps: Option<&serde_json::Value>,/,
    "the Add form's builder has no `steps`");
  assert.match(add, /body\["steps"\] = steps;/,
    "the Add form never puts `steps` in the body");
  assert.match(add, /Only a reminder can be a routine\./,
    "a timer or to-do can be given parts");
  // A part's question is `ask_block` - the same code as the reminder's own,
  // without the `kind` marker (§2.3 of the spec).
  assert.match(RUST, /built\["ask"\] = ask_block\(ask\)\?;/,
    "a part's question is not built by the shared ask block");
  assert.match(RUST, /fn ask_body\(obj: &serde_json::Map<String, serde_json::Value>\)/,
    "ask_body's shape changed under its callers");
});

check("the Rust commands take the part's index, and cap it at twelve", () => {
  assert.match(RUST,
    /pub\(crate\) fn answer_body\(\s*id: &str,\s*button: Option<u32>,\s*step: Option<u32>,\s*\)/,
    "answer_body has no part index");
  assert.match(RUST, /if step >= MAX_STEPS \{\s*return Err\(format!\("A routine has up to \{MAX_STEPS\} parts\."\)\);/,
    "a thirteenth part index is not refused");
  assert.match(CMD, /step: Option<u32>,\s*\) -> Result<serde_json::Value, String> \{/,
    "hud_schedule_act has no `step` argument");
  assert.match(CMD, /let body = answer_body\(&id, button, step\)\?;/,
    "hud_schedule_act does not pass the part's index");
  assert.match(CMD, /steps: Option<serde_json::Value>,/,
    "hud_schedule_add has no `steps` argument");
  assert.match(CMD, /action\.as_ref\(\),\s*steps\.as_ref\(\),/,
    "hud_schedule_add does not pass the parts to its builder");
});

check("the toast says which part, and never the words while they are hidden", () => {
  assert.match(RUST, /pub\(crate\) fn part_title\(title: &str, part: \(u64, u64\)\) -> String \{/,
    "there is no part-aware toast title");
  assert.match(RUST, /format!\("\{title\} \u00b7 \{\} of \{\}", part\.0 \+ 1, part\.1\)/,
    "the toast title does not say which part");
  const fired = RUST.slice(RUST.indexOf("pub async fn toast_fired("),
    RUST.indexOf("pub(crate) fn open_notice("));
  assert.match(fired, /if !private \{\s*let label = part_label\(job\.as_ref\(\), part\.0\);/,
    "a part's label is read on a locked screen");
  assert.match(fired, /let opening = if part\.is_some\(\) \{\s*None/,
    "a routine is still offered an Open button for an action the PC never fires");
});

check("the three vendored copies of the page are byte-identical", () => {
  const [first, ...rest] = COPIES;
  const original = readFileSync(first[1]);
  for (const [name, file] of rest) {
    const other = readFileSync(file);
    assert.ok(original.equals(other), `${name} copy differs from ${first[0]}`);
  }
});

console.log(`\n${passed} passed, 0 skipped, ${process.exitCode ? 1 : 0} failed`);
