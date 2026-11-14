/**
 * "Personalize Jarvis" on the desktop: the model, the stepper, the bridge, the
 * page's one action, and the PC's real questions.
 *
 * Part 1 reads the PC's own questions from `backend/jarvis_setup.py` with the
 * real Python interpreter (`tests/lib/python.mjs`), so this suite cannot pass
 * against a hand-written idea of the questionnaire: the count, the ids, the
 * options and the order are the PC's. When there is no Python on this machine
 * those checks SKIP and say so - a skip is not a pass. The suite never types
 * the number of questions: the fixture's generated `count` is the one number,
 * so a backend that grows from fourteen to twenty-five cannot leave this file
 * lying.
 *
 * Part 2 is the model: the reading, the draft ("All"/"None" expand at the data
 * level), the READ-ONLY plan body, the one apply body (the only one carrying
 * `confirm: true`), the progress body, the effect words (instant / card /
 * blocked - never rounded), the gate a stale link holds, and the honest
 * outcomes (a card still waiting is NOT "failed" and NOT "done").
 *
 * Part 3 is the stepper (Wave B, 2026-11-03): the section tabs, the "new /
 * unanswered" filter driven by each question's own `version`, the next-question
 * rule and the progress words - all pure, all tested here.
 *
 * Part 4 is a fake bridge: what the page sends for read, plan, progress and
 * apply, and that a read, a plan or a progress note can never carry `confirm`.
 * It also reads the Rust and the page as text for the wiring and for what must
 * NOT be there: no route name in the page, no gate action, no auto-apply on
 * load; and the HUD's own banner and the one command it needs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { pythonFor } from "./lib/python.mjs";
import * as Q from "../src/setup-questionnaire.js";
import * as Bridge from "../src/setup-bridge.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");
/** A file elsewhere in the repository, by its repo-relative path. */
const repoRead = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const PY = pythonFor(join(HERE, "..", "..", "backend"));

let passed = 0;
let failed = 0;
let skipped = 0;
const check = async (name, fn) => {
  try {
    await fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (error) {
    if (PY.caught(name, error)) {
      skipped += 1;
      return;
    }
    failed += 1;
    console.log(`FAIL  ${name}\n      ${error.message}`);
  }
};

/* ── 1. The PC's real questions ──────────────────────────────────────────── */

const LIVE = PY.run(`
import json
import jarvis_setup as S
print(json.dumps({
    "questions": [{
        "id": q["id"], "title": q["title"], "help": q["help"],
        "multi": bool(q["multi"]),
        "options": [{"id": o["id"], "label": o["label"],
                     "detail": o.get("detail", "")} for o in q["options"]],
        "all_none": bool(q["multi"]),
        "section": q.get("section", ""),
        "version": q.get("version", 0),
        "sections": list(getattr(S, "SECTIONS", ())),
    } for q in S.QUESTIONS],
}))
`);

function needLive() {
  if (!LIVE || !Array.isArray(LIVE.questions)) {
    PY.skip("the PC's questions", "no Python here - the real backend module was not read");
  }
  return LIVE.questions;
}

await check("the PC's questionnaire is a list of questions, each with choices", () => {
  const questions = needLive();
  assert.ok(questions.length > 0, "the PC sent no questions at all");
  const ids = questions.map((q) => q.id);
  assert.equal(new Set(ids).size, ids.length, "question ids are unique");
  for (const q of questions) {
    assert.ok(q.title && q.help, `${q.id} has a title and a help line`);
    assert.ok(q.options.length >= 2, `${q.id} offers at least two choices`);
    assert.equal(new Set(q.options.map((o) => o.id)).size, q.options.length,
      `${q.id}'s choice ids are unique`);
  }
  // Wave B's per-question fields, once the PC sends them: `version` is a whole
  // number and `section` (when present) is one of the PC's own declared
  // sections. Before the backend lands they are absent, which is allowed - the
  // reading treats that as "no version data", never as a broken question.
  const declared = new Set((questions[0].sections || []).map((row) => row[0]));
  for (const q of questions) {
    assert.ok(Number.isInteger(q.version) && q.version >= 0,
      `${q.id}'s version is a whole number`);
    if (q.section) {
      assert.ok(declared.has(q.section), `${q.id}'s section is one the PC declares`);
    }
  }
});

await check("the reading carries every question, option, label and help line the PC sent", () => {
  const questions = needLive();
  const reading = Q.normaliseReading({ available: true, questions });
  assert.equal(reading.available, true);
  assert.deepEqual(reading.questions.map((q) => q.id), questions.map((q) => q.id),
    "the PC's order is kept");
  for (const [index, sent] of questions.entries()) {
    const got = reading.questions[index];
    assert.equal(got.title, sent.title);
    assert.equal(got.help, sent.help);
    assert.equal(got.multi, sent.multi);
    assert.equal(got.allNone, sent.multi, "a choose-any question takes All/None");
    assert.deepEqual(got.options, sent.options, `${sent.id}'s choices`);
  }
});

await check("no question id or title is hardcoded in the page's source", () => {
  const questions = needLive();
  const sources = ["src/setup-questionnaire.js", "src/setup-settings.js"]
    .map((one) => read(one)).join("\n");
  for (const q of questions) {
    assert.ok(!sources.includes(q.title), `source hardcodes the question "${q.title}"`);
    if (q.id.length >= 6) {
      assert.ok(!sources.includes(q.id), `source hardcodes the id ${q.id}`);
    }
  }
});

await check("the shared fixture is the PC's questions, and the phone reads the same file", () => {
  const questions = needLive();
  const fixture = JSON.parse(read("../backend/fixtures/setup_questions.json"));
  // The count is the fixture's own generated number, never one typed here: a
  // backend that grows from fourteen questions to twenty-five regenerates it,
  // and this file needs no edit to stay honest.
  assert.equal(fixture.count, questions.length,
    "the fixture is stale: run py -3 tools/gen_setup_questions.py");
  assert.equal(fixture.generated_by, "tools/gen_setup_questions.py");
  assert.equal(fixture.source, "backend/jarvis_setup.py");
  // Compared on the fields the fixture has always carried, in the order the PC
  // sends them. Wave B adds `section` and `version` per question once the PC
  // sends them; the fixture picks those up when it is next regenerated, and
  // this comparison does not care either way.
  const shape = (rows) => rows.map((q) => ({
    id: q.id, title: q.title, help: q.help, multi: q.multi,
    options: q.options, all_none: q.all_none === true || q.multi === true,
  }));
  assert.deepEqual(shape(fixture.questions), shape(questions),
    "the fixture is stale: run py -3 tools/gen_setup_questions.py");
});

await check("a reading with no questions, or an old backend, says so instead of guessing", () => {
  const none = Q.normaliseReading({ available: true, questions: [] });
  assert.equal(none.available, true);
  assert.deepEqual(none.questions, []);

  const old = Q.normaliseReading({ available: false, why: "not on this PC" });
  assert.equal(old.available, false);
  assert.equal(old.reason, "not on this PC");

  const missing = Q.normaliseReading(null);
  assert.equal(missing.available, false);
  assert.equal(missing.reason, Q.BAD_READ_WORDS);
});

/* ── 2. The draft, the plan and the one apply body ───────────────────────── */

const FAKE = {
  available: true,
  questions: [
    {
      id: "style", title: "How should it talk?", help: "Words only.",
      multi: false, all_none: false,
      options: [
        { id: "warm", label: "Warm", detail: "Friendly." },
        { id: "plain", label: "Plain", detail: "Neutral." },
      ],
    },
    {
      id: "tools", title: "Which things may it read?", help: "One card each to turn on.",
      multi: true, all_none: true,
      options: [
        { id: "calendar", label: "Calendar", detail: "" },
        { id: "email", label: "Email", detail: "" },
        { id: "notes", label: "Notes", detail: "" },
      ],
    },
  ],
  current: { manner: "warm", calendar_read: false },
  answers: { style: "warm", tools: ["calendar", "email"] },
  completed_at: 1_765_000_000,
  last_outcomes: [{ setting: "manner", label: "How it talks", effect: "instant",
    state: "changed", message: "changed." }],
  card_wait_s: 300,
  storage: "setup.json in the Jarvis settings folder",
};
const READING = Q.normaliseReading(FAKE);
const STYLE = READING.questions[0];
const TOOLS = READING.questions[1];

await check("the draft prefills the last accepted answers and drops choices this PC no longer offers", () => {
  const draft = Q.draftFromAnswers(READING);
  assert.deepEqual(draft, { style: "warm", tools: ["calendar", "email"] });

  const stale = Q.normaliseReading({
    ...FAKE,
    answers: { style: "gone", tools: ["calendar", "gone"], unknown: "warm" },
  });
  assert.deepEqual(Q.draftFromAnswers(stale), { tools: ["calendar"] },
    "a stale option is dropped, never sent back");
});

await check("one-choice answers replace; choose-any toggles, and All/None stay data-level words", () => {
  let draft = Q.chooseOne({}, "style", "plain");
  assert.deepEqual(draft, { style: "plain" });
  draft = Q.chooseOne(draft, "style", "warm");
  assert.deepEqual(draft, { style: "warm" });

  // A checkbox checked on from nothing picks just that one.
  draft = Q.toggleOption({}, TOOLS, "calendar");
  assert.deepEqual(draft, { tools: ["calendar"] });
  draft = Q.toggleOption(draft, TOOLS, "email");
  assert.deepEqual(draft, { tools: ["calendar", "email"] });
  draft = Q.toggleOption(draft, TOOLS, "calendar");
  assert.deepEqual(draft, { tools: ["email"] });
  assert.equal(Q.optionOn(draft, TOOLS, "calendar"), false);
  assert.equal(Q.optionOn(draft, TOOLS, "email"), true);

  // "All" makes every box look checked; unticking one is the concrete rest.
  draft = Q.chooseAll({}, "tools");
  assert.equal(Q.allNoneState(draft, "tools"), "all");
  assert.equal(Q.optionOn(draft, TOOLS, "calendar"), true);
  assert.equal(Q.optionOn(draft, TOOLS, "notes"), true);
  draft = Q.toggleOption(draft, TOOLS, "calendar");
  assert.deepEqual(draft, { tools: ["email", "notes"] });

  // "None" then ticking one is that one.
  draft = Q.chooseNone({}, "tools");
  assert.equal(Q.allNoneState(draft, "tools"), "none");
  assert.equal(Q.optionOn(draft, TOOLS, "email"), false);
  draft = Q.toggleOption(draft, TOOLS, "email");
  assert.deepEqual(draft, { tools: ["email"] });

  // Unticking the last one leaves the question unanswered, not [].
  assert.deepEqual(Q.toggleOption({ tools: ["email"] }, TOOLS, "email"), {});
  assert.equal(Q.answeredCount({}), 0);
  assert.equal(Q.answeredCount({ style: "warm", tools: ["email"] }), 2);
});

await check("the plan body is read-only: answers only, never a confirm", () => {
  const body = Q.planBody({ style: "warm", tools: "all" });
  assert.deepEqual(body, { answers: { style: "warm", tools: "all" } });
  assert.deepEqual(Object.keys(body), ["answers"]);
  assert.ok(!("confirm" in body));
  assert.doesNotMatch(JSON.stringify(body), /confirm/);

  // An unanswered question is not sent at all.
  assert.deepEqual(Q.planBody({ style: "warm" }).answers, { style: "warm" });
  assert.deepEqual(Q.planBody({}).answers, {});
});

await check("the apply body carries confirm: true and is built for one explicit press", () => {
  const body = Q.applyBody({ style: "warm", tools: ["email"] });
  assert.deepEqual(body, {
    answers: { style: "warm", tools: ["email"] },
    confirm: true,
  });
  assert.equal(body.confirm, true);
});

await check("a plan keeps the PC's order, words and effects - instant, card and blocked are never rounded", () => {
  const plan = Q.planView({
    ok: true,
    changes: [
      { setting: "email_read", label: "Email reading", question: "tools",
        from: false, to: true, effect: "card",
        sentence: "Email reading: off -> on" },
      { setting: "manner", label: "How it talks", question: "style",
        from: "warm", to: "plain", effect: "instant",
        sentence: "How it talks: warm -> plain" },
      { setting: "odd", label: "Odd", question: "tools", from: "a", to: "b",
        effect: "experimental", sentence: "Odd: a -> b" },
    ],
    summary: ["Takes effect immediately: How it talks: warm -> plain"],
    skipped: [
      { setting: "humor", reason: "Humour: already off" },
      { setting: "web_search", reason: "Web search: this PC's settings file does not ask for this change, so it cannot be made from here" },
    ],
    recommendation: { id: "coding", title: "Coding", why: "A preset changes models, so it is only a recommendation here - apply it from the preset selector if you want it." },
  }, READING);
  assert.equal(plan.ok, true);
  assert.deepEqual(plan.changes.map((c) => c.setting), ["manner", "email_read", "odd"],
    "the PC's question order wins over the change order");
  assert.equal(plan.changes[0].effectWords, Q.EFFECT_WORDS.instant);
  assert.equal(plan.changes[1].effectWords, Q.EFFECT_WORDS.card);
  assert.equal(plan.changes[2].effectWords, "experimental", "an unknown effect is never called instant");
  assert.equal(plan.changes[0].from, "warm");
  assert.equal(plan.changes[0].to, "plain");
  assert.deepEqual(plan.counts, { instant: 1, card: 1, blocked: 0 });
  assert.deepEqual(plan.skipped.map((s) => s.reason), [
    "Humour: already off",
    "Web search: this PC's settings file does not ask for this change, so it cannot be made from here",
  ], "the PC's reasons are kept word for word");
  assert.equal(plan.recommendation.title, "Coding");
  assert.match(plan.recommendation.why, /recommendation/i);
  assert.match(plan.recommendation.why, /changes no models|changes models/i);
  assert.equal(plan.hasChanges, true);

  assert.equal(Q.effectWords("blocked"), Q.EFFECT_WORDS.blocked);
  assert.equal(Q.effectWords("CARD"), Q.EFFECT_WORDS.card);

  const refusal = Q.planView({ ok: false, error: "the answers must be one object" }, READING);
  assert.equal(refusal.ok, false);
  assert.equal(refusal.error, "the answers must be one object");
  assert.deepEqual(Q.planView(null, READING).changes, []);
});

await check("the one Apply button is held by a stale link and by a plan that changes nothing", () => {
  const plan = Q.planView({ ok: true, changes: [{ setting: "manner", label: "How it talks",
    question: "style", from: "warm", to: "plain", effect: "instant", sentence: "" }],
  skipped: [], summary: [], recommendation: null }, READING);
  assert.deepEqual(Q.gate({ reading: READING, plan }), { enabled: true, why: "" });

  assert.equal(Q.gate({ reading: READING, plan, stale: true }).enabled, false,
    "rule 4: a stale link never applies");
  assert.equal(Q.gate({ reading: READING, plan, stale: true }).why, Q.APPLY_HELD);
  assert.equal(Q.gate({ reading: READING, plan, busy: true }).enabled, false);
  assert.equal(Q.gate({ reading: READING, plan: null }).why, Q.CHOOSE_FIRST);
  assert.equal(Q.gate({ reading: READING, plan: Q.planView({ ok: true, changes: [] }, READING) }).why,
    Q.NOTHING_TO_APPLY);
  assert.equal(Q.gate({ reading: READING, plan: Q.planView({ ok: false, error: "bad" }, READING) }).why,
    "bad");
  assert.equal(Q.gate({ reading: Q.normaliseReading({ available: false }) }).why, Q.UPDATE_WORDS);
  assert.equal(Q.gate({}).why, "Reading this PC…");
});

await check("the confirm step says how many changes, how many cards, and that nothing changed yet", () => {
  const plan = Q.planView({ ok: true, changes: [
    { setting: "manner", label: "How it talks", question: "style", effect: "instant", sentence: "" },
    { setting: "email_read", label: "Email reading", question: "tools", effect: "card", sentence: "" },
  ], skipped: [], summary: [], recommendation: null }, READING);
  const words = Q.confirmWords(plan);
  assert.match(words, /Apply 2 changes now\?/);
  assert.match(words, /1 of them will ask you on a card/);
  assert.match(words, /Nothing has been changed yet/);
  assert.match(Q.confirmWords(Q.planView({ ok: true, changes: [
    { setting: "manner", label: "How it talks", question: "style", effect: "instant", sentence: "" },
  ], skipped: [], summary: [], recommendation: null }, READING)),
  /None of them needs an approval card/);
  assert.equal(Q.confirmWords({ changes: [], counts: {} }), Q.NOTHING_TO_APPLY);
});

await check("apply outcomes are honest: waiting is waiting, denied stays as it was, changed is changed", () => {
  const view = Q.applyView({
    ok: true,
    confirmed: true,
    completed_at: 1_765_000_100,
    changed_count: 2,
    outcomes: [
      { setting: "manner", label: "How it talks", effect: "instant", state: "changed",
        message: "changed." },
      { setting: "email_read", label: "Email reading", effect: "card",
        state: "asked-and-approved", message: "you approved the card, so it changed." },
      { setting: "calendar_read", label: "Calendar reading", effect: "card",
        state: "asked-no-answer", message: "The card is still waiting - answer it and the change is made.", waited: true },
      { setting: "web_search", label: "Web search", effect: "card",
        state: "asked-and-denied", message: "The card was not approved, so it stays as it was." },
      { setting: "better_voice", label: "Better voice", effect: "card",
        state: "not-available", message: "Better voice: that can only be changed on the PC." },
    ],
    summary: [],
  });
  assert.equal(view.ok, true);
  assert.equal(view.waiting, 1);
  assert.equal(view.denied, 1);
  assert.equal(view.changedCount, 2);
  assert.equal(view.rows[0].stateWords, "Changed.");
  assert.equal(view.rows[2].stateWords,
    "Still waiting: answer its card on the PC and it changes.");
  assert.equal(view.rows[3].stateWords,
    "Not changed - the card was not approved.");
  assert.equal(view.rows[4].stateWords, "Not available on this PC.");
  assert.equal(view.rows[2].waited, true);
  assert.ok(view.completedAt > 0);

  // A refusal is the PC's own sentence and keeps any outcomes it did report.
  const refused = Q.applyView({ ok: false, confirmed: true, error: "the settings were attempted, but the answers could not be saved", outcomes: view.rows.length ? [{
    setting: "manner", label: "How it talks", effect: "instant", state: "changed", message: "changed." }] : [] });
  assert.equal(refused.ok, false);
  assert.match(refused.error, /could not be saved/);
  assert.equal(refused.rows.length, 1);
  assert.deepEqual(Q.applyView(null).rows, []);
});

await check("the card patience is said in minutes, and the last run is readable", () => {
  assert.equal(Q.cardWaitWords(300), "Each approval card can wait up to 5 minutes for you before the questionnaire moves on.");
  assert.equal(Q.cardWaitWords(60), "Each approval card can wait up to 1 minute for you before the questionnaire moves on.");
  assert.equal(Q.cardWaitWords(900), "Each approval card can wait up to 15 minutes for you before the questionnaire moves on.");
  assert.match(Q.cardWaitWords(null), /5 minutes/);

  const last = Q.lastRunView(READING);
  assert.equal(last.rows.length, 1);
  assert.equal(last.rows[0].stateWords, "Changed.");
  assert.equal(Q.lastRunView(Q.normaliseReading({ available: true, questions: [] })).rows.length, 0);
});

/* ── 3. The stepper: sections, the filter, the next question, progress ───── */

/* A reading shaped like the PC's answer after Wave B: seven sections, some
 * questions from version 1 and some new in version 2, and an owner who has
 * answered five of the eleven and last finished version 1. */
const STEPS = Q.normaliseReading({
  available: true,
  version: 2,
  completed_version: 1,
  answered_count: 5,
  dismissed_at: null,
  in_progress: { section: "learning", question: "reworded_memories",
    started_at: 1_793_941_000.5, draft_answers: { reworded_memories: "on" } },
  sections: [
    { id: "talk", title: "How it talks" },
    { id: "read", title: "What it may read" },
    { id: "learning", title: "Learning & privacy" },
    { id: "notify", title: "Notifications" },
  ],
  questions: [
    { id: "talk_style", title: "How should Jarvis talk?", help: "Words only.", multi: false,
      section: "talk", version: 1,
      options: [{ id: "warm", label: "Warm" }, { id: "plain", label: "Plain" }] },
    { id: "personality", title: "Which personality?", help: "", multi: false,
      section: "talk", version: 2,
      options: [{ id: "warm_peer", label: "Warm" }, { id: "calm_stoic", label: "Calm" }] },
    { id: "reading_tools", title: "Which of your things may it read?", help: "",
      multi: true, section: "read", version: 1,
      options: [{ id: "calendar", label: "Calendar" }, { id: "email", label: "Email" }] },
    { id: "lights_without_card", title: "Lights without a card?", help: "", multi: false,
      section: "read", version: 2,
      options: [{ id: "on", label: "On" }, { id: "off", label: "Off" }] },
    { id: "learning", title: "How should Jarvis learn?", help: "", multi: false,
      section: "learning", version: 1,
      options: [{ id: "learn", label: "Learn" }, { id: "learn_off", label: "Off" }] },
    { id: "reworded_memories", title: "Save a reworded fact?", help: "", multi: false,
      section: "learning", version: 2,
      options: [{ id: "on", label: "On" }, { id: "off", label: "Off" }] },
    { id: "chat_history", title: "Keep chats on this PC?", help: "", multi: false,
      section: "learning", version: 2,
      options: [{ id: "on", label: "On" }, { id: "off", label: "Off" }] },
    { id: "notifications", title: "Which notifications?", help: "", multi: true,
      section: "notify", version: 1,
      options: [{ id: "phone", label: "Phone" }, { id: "watch", label: "Watch" }] },
  ],
  answers: {
    talk_style: "warm", reading_tools: ["calendar"], learning: "learn",
    notifications: ["phone"], // answered, and still version 1
  },
});
const STEPS_DRAFT = Q.draftFromAnswers(STEPS);
/** The same reading with every question answered: the pass the owner finishes. */
const STEPS_EVERY_ANSWER = {
  talk_style: "warm", personality: "calm_stoic", reading_tools: ["calendar"],
  lights_without_card: "off", learning: "learn", reworded_memories: "on",
  chat_history: "off", notifications: ["phone"],
};

await check("the PC's sections are the tabs, in its order; a backend without them still gets one", () => {
  const sections = Q.sectionsOf(STEPS);
  assert.deepEqual(sections.map((s) => s.id), ["talk", "read", "learning", "notify"],
    "the PC's declared order is kept");
  assert.deepEqual(sections.map((s) => s.title),
    ["How it talks", "What it may read", "Learning & privacy", "Notifications"]);
  assert.deepEqual(sections[1].questions.map((q) => q.id),
    ["reading_tools", "lights_without_card"]);

  // No declared sections: derived from the questions' own `section` values, in
  // the order they appear - never a blank page.
  const derived = Q.sectionsOf(Q.normaliseReading({
    available: true,
    questions: [
      { id: "a", title: "A", options: [{ id: "x" }, { id: "y" }], section: "one" },
      { id: "b", title: "B", options: [{ id: "x" }, { id: "y" }], section: "two" },
      { id: "c", title: "C", options: [{ id: "x" }, { id: "y" }], section: "one" },
    ],
  }));
  assert.deepEqual(derived.map((s) => s.id), ["one", "two"]);
  assert.deepEqual(derived[0].questions.map((q) => q.id), ["a", "c"]);

  // No sections and none on the questions: ONE unnamed tab, holding all of
  // them. An older PC is not a broken card.
  const fallback = Q.sectionsOf(Q.normaliseReading({
    available: true,
    questions: [
      { id: "a", title: "A", options: [{ id: "x" }, { id: "y" }] },
      { id: "b", title: "B", options: [{ id: "x" }, { id: "y" }] },
    ],
  }));
  assert.equal(fallback.length, 1);
  assert.equal(fallback[0].id, "");
  assert.equal(fallback[0].title, Q.SECTION_FALLBACK_TITLE);
  assert.equal(fallback[0].questions.length, 2);
  // A section the PC declared but has no questions for is left out.
  assert.equal(Q.sectionsOf(Q.normaliseReading({
    available: true, sections: [{ id: "empty", title: "Empty" }],
    questions: [{ id: "a", title: "A", options: [{ id: "x" }, { id: "y" }], section: "one" }],
  })).some((s) => s.id === "empty"), false);
});

await check("the filter is new-or-unanswered, driven by each question's own version", () => {
  // Answered in version 1, unchanged since: hidden by the filter.
  assert.equal(Q.isNewOrUnanswered(STEPS, STEPS.questions[0]), false);
  // Answered in version 1, but the question is now version 2: SHOWN - this is
  // exactly ruling Q3's "10 new questions" after a 1 -> 2 bump.
  assert.equal(Q.isNewOrUnanswered(STEPS, STEPS.questions[1]), true);
  // Never answered: shown whatever its version.
  assert.equal(Q.isNewOrUnanswered(STEPS, STEPS.questions[6]), true);
  const fresh = Q.visibleQuestions(STEPS, { filter: true });
  assert.deepEqual(fresh.map((q) => q.id),
    ["personality", "lights_without_card", "reworded_memories", "chat_history"]);
  // The count in the label is this same call, never a number typed on the page.
  assert.equal(fresh.length, 4);

  // A section narrows it; both together are the card's filter.
  assert.deepEqual(Q.visibleQuestions(STEPS, { section: "learning", filter: true })
    .map((q) => q.id), ["reworded_memories", "chat_history"]);
  assert.deepEqual(Q.visibleQuestions(STEPS, { section: "talk" }).map((q) => q.id),
    ["talk_style", "personality"]);

  // No version data at all (an older PC): the filter keeps only the
  // unanswered, and never hides a question it cannot judge.
  const oldPc = Q.normaliseReading({
    available: true, questions: [
      { id: "a", title: "A", options: [{ id: "x" }, { id: "y" }] },
      { id: "b", title: "B", options: [{ id: "x" }, { id: "y" }] },
    ], answers: { a: "x" },
  });
  assert.deepEqual(Q.visibleQuestions(oldPc, { filter: true }).map((q) => q.id), ["b"]);
});

await check("the filter's empty line and its count tell the same truth", () => {
  // Four questions are new or unanswered across the whole questionnaire; that
  // number is the label above the panel ("Show only new / unanswered (4)").
  assert.equal(Q.visibleQuestions(STEPS, { filter: true }).length, 4);
  // The section on screen holds none of them, so the panel says THAT. It used
  // to say "Every question is answered and up to date" here, contradicting
  // the count right above it (audit 2026-11-03, bug 6).
  assert.equal(Q.visibleQuestions(STEPS, { section: "notify", filter: true }).length, 0);
  assert.equal(Q.filterEmptyWords(STEPS, { section: "notify", filter: true }),
    Q.FILTER_SECTION_EMPTY);
  assert.doesNotMatch(Q.FILTER_SECTION_EMPTY, /Every question is answered/);
  // A section that does have fresh questions says nothing at all.
  assert.equal(Q.filterEmptyWords(STEPS, { section: "talk", filter: true }), "");
  assert.equal(Q.filterEmptyWords(STEPS, { section: "learning", filter: true }), "");
  // The completion sentence is for a questionnaire with nothing fresh
  // ANYWHERE - the same set the count is taken from.
  const finished = Q.normaliseReading({
    available: true, version: 1, completed_version: 1,
    sections: [{ id: "a", title: "A" }, { id: "b", title: "B" }],
    questions: [
      { id: "q1", title: "Q1", section: "a", version: 1, options: [{ id: "x", label: "X" }] },
      { id: "q2", title: "Q2", section: "b", version: 1, options: [{ id: "x", label: "X" }] },
    ],
    answers: { q1: "x", q2: "x" },
  });
  assert.equal(Q.visibleQuestions(finished, { filter: true }).length, 0);
  assert.equal(Q.filterEmptyWords(finished, { section: "a", filter: true }), Q.FILTER_EMPTY);
  assert.equal(Q.filterEmptyWords(finished, { filter: true }), Q.FILTER_EMPTY);
  // The filter off is no empty state at all: the whole section is on screen.
  assert.equal(Q.filterEmptyWords(STEPS, { section: "notify", filter: false }), "");
  // The two sentences are different on purpose.
  assert.notEqual(Q.FILTER_EMPTY, Q.FILTER_SECTION_EMPTY);
});

await check("next, first-unanswered and the position words walk the PC's order", () => {
  // Forward from a question to the next one with no answer in the draft.
  assert.equal(Q.nextQuestion(STEPS, STEPS_DRAFT, "talk_style").id, "personality");
  assert.equal(Q.nextQuestion(STEPS, STEPS_DRAFT, "learning").id, "reworded_memories");
  // From the start (`""`) it is the first unanswered question overall.
  assert.equal(Q.nextQuestion(STEPS, STEPS_DRAFT, "").id, "personality");
  // From the last question there is nothing after it.
  assert.equal(Q.nextQuestion(STEPS, STEPS_DRAFT, "notifications"), null);
  // "Skip" is this same rule after the id is dropped from the draft: the
  // question just walked past is not offered again.
  const skipped = Q.chooseOne(STEPS_DRAFT, "personality", "");
  assert.equal(Q.answerFor(skipped, "personality"), null);
  assert.equal(Q.nextQuestion(STEPS, skipped, "personality").id, "lights_without_card");

  // First open: the first question the owner has never answered.
  assert.equal(Q.firstUnanswered(STEPS).id, "personality");
  // Everything answered: null, so the card opens at its own top.
  const all = { talk_style: "warm", personality: "calm_stoic", reading_tools: ["calendar"],
    lights_without_card: "off", learning: "learn", reworded_memories: "on",
    chat_history: "off", notifications: ["phone"] };
  assert.equal(Q.firstUnanswered({ ...STEPS, answers: all }), null);

  // "8 of 25 answered" is a count, never a percentage, and it follows the DRAFT.
  assert.equal(Q.progressWords(STEPS, STEPS_DRAFT), "4 of 8 answered");
  assert.equal(Q.progressWords(STEPS, {}), "0 of 8 answered");
  assert.equal(Q.progressWords(Q.normaliseReading({ available: true, questions: [] }), {}),
    "0 of 0 answered");
  assert.equal(Q.positionWords(STEPS, "learning"), "Question 5 of 8");
  assert.equal(Q.positionWords(STEPS, "not-a-question"), "");
});

await check("the last question's Next is Finish, and one press records the pass", () => {
  // (a) 2026-11-13, the owner's own report. Before this, Next at the end of the
  // list painted the row and returned: the press did nothing, Finish was never
  // painted or wired, and the pass could never be recorded as complete - so the
  // app kept telling him the quiz was unfinished.
  const last = Q.nextStep(STEPS, {
    section: "notify", currentId: "notifications", draft: STEPS_EVERY_ANSWER,
  });
  assert.equal(last.kind, Q.STEP_FINISH, "the last question's Next is Finish");
  assert.notEqual(last.kind, Q.STEP_END, "and not the silent end it used to be");
  assert.equal(last.id, "");
  assert.equal(last.why, "", "Finish needs no apology under the row");

  // The same press at the end of a FILTERED walk: the four version-2 questions
  // are all that is left of this pass, and their end is the questionnaire's end.
  assert.deepEqual(
    Q.visibleQuestions(STEPS, { section: "learning", filter: true }).map((q) => q.id),
    ["reworded_memories", "chat_history"]);
  const filtered = Q.nextStep(STEPS, {
    filter: true, section: "learning", currentId: "chat_history",
    draft: STEPS_EVERY_ANSWER,
  });
  assert.equal(filtered.kind, Q.STEP_FINISH);

  // An ordinary step is still a question - the next one on screen - and the end
  // of a section still opens the section after it.
  assert.deepEqual(
    Q.nextStep(STEPS, { section: "talk", currentId: "talk_style", draft: STEPS_DRAFT }),
    { kind: Q.STEP_QUESTION, id: "personality", why: "" });
  assert.equal(Q.nextStep(STEPS, {
    section: "read", currentId: "lights_without_card", draft: STEPS_DRAFT,
  }).id, "learning");
});

await check("walking the PC's own question list reaches Finish at the end of it", () => {
  // The owner's state on 2026-11-13: `completed_version` 1, the set at version
  // 2, every one of the 25 questions staged in the draft - and a Next button
  // that did nothing at the end, so the pass could never be recorded. This walks
  // the real list, question by question, with the same rule the button uses.
  const fixture = JSON.parse(read("../backend/fixtures/setup_questions.json"));
  const questions = fixture.questions.map((q) => ({
    id: q.id, title: q.title, help: q.help, multi: q.multi === true,
    all_none: q.multi === true, section: q.section || "", version: q.version || 1,
    options: q.options,
  }));
  const answers = {};
  for (const q of questions) {
    answers[q.id] = q.multi ? [q.options[0].id] : q.options[0].id;
  }
  const reading = Q.normaliseReading({
    available: true, version: Number(fixture.version) || 2, completed_version: 1,
    questions, answers: {},
  });
  assert.ok(Q.passComplete(reading, answers), "every question has an answer");
  let section = Q.sectionsOf(reading)[0].id;
  let currentId = questions[0].id;
  const walked = [];
  for (let guard = 0; guard <= questions.length; guard += 1) {
    const action = Q.nextStep(reading, {
      section, filter: false, currentId, draft: answers,
    });
    if (action.kind === Q.STEP_FINISH) {
      walked.push("finish");
      break;
    }
    assert.equal(action.kind, Q.STEP_QUESTION,
      `Next has no second move at ${currentId}: ${action.why}`);
    walked.push(action.id);
    currentId = action.id;
    section = (Q.questionById(reading, action.id) || {}).section || section;
  }
  assert.equal(walked[walked.length - 1], "finish",
    "the end of the real question list is Finish, not a press that does nothing");
  assert.equal(walked.length, questions.length,
    "and it walks every question on the way there, once each");
});

await check("a question the filter hid is stepped over one at a time, never a section", () => {
  // (b) 2026-11-13. `findIndex` for a question the filter has hidden is -1, and
  // the old Next fell straight through to the NEXT SECTION - skipping every
  // question of this one that came after it. One step is the whole rule.
  const reading = Q.normaliseReading({
    available: true, version: 1, completed_version: 1,
    sections: [{ id: "talk", title: "Talk" }, { id: "read", title: "Read" }],
    questions: [
      { id: "q1", title: "One", help: "", section: "talk", version: 1,
        options: [{ id: "x", label: "X" }, { id: "y", label: "Y" }] },
      { id: "q2", title: "Two", help: "", section: "talk", version: 1,
        options: [{ id: "x", label: "X" }, { id: "y", label: "Y" }] },
      { id: "q3", title: "Three", help: "", section: "read", version: 1,
        options: [{ id: "x", label: "X" }, { id: "y", label: "Y" }] },
    ],
    answers: { q1: "x" },
  });
  assert.deepEqual(
    Q.visibleQuestions(reading, { section: "talk", filter: true }).map((q) => q.id),
    ["q2"], "the filter really has hidden the question on screen");
  const action = Q.nextStep(reading, {
    section: "talk", filter: true, currentId: "q1", draft: Q.draftFromAnswers(reading),
  });
  assert.equal(action.kind, Q.STEP_QUESTION);
  assert.equal(action.id, "q2", "one step, into the question after it in its own section");
  assert.notEqual(action.id, "q3", "never a jump over the rest of the section to the next one");

  // A section with nothing left in it still has a defined move: the next
  // section that has something. It is not a press that does nothing.
  assert.equal(Q.nextStep(reading, {
    section: "talk", filter: true, currentId: "", draft: {},
  }).id, "q3");
});

await check("an incomplete pass offers no Finish, and the end says what is left", () => {
  // (c) 2026-11-13. Finish records the pass as complete on the PC, so it is
  // offered only on a pass that IS complete - and four of these eight have no
  // answer. Before this, the end was a button that did nothing at all.
  assert.equal(Q.passComplete(STEPS, STEPS_DRAFT), false);
  assert.equal(Q.unansweredCount(STEPS, STEPS_DRAFT), 4);
  assert.equal(Q.passComplete(STEPS, STEPS_EVERY_ANSWER), true);

  const end = Q.nextStep(STEPS, {
    section: "notify", currentId: "notifications", draft: STEPS_DRAFT,
  });
  assert.equal(end.kind, Q.STEP_END, "no Finish on a pass with questions left");
  assert.notEqual(end.kind, Q.STEP_FINISH);
  assert.equal(end.id, "");
  assert.match(end.why, /last question/);
  assert.match(end.why, /4 questions still have no answer/);
  assert.match(end.why, /Keep current settings/,
    "it points at the one button that records the pass without an answer");

  // The count is the draft's own, and it is said in the singular for one.
  const oneLeft = { ...STEPS_EVERY_ANSWER };
  delete oneLeft.chat_history;
  assert.equal(Q.passComplete(STEPS, oneLeft), false);
  assert.match(Q.stepOpenWords(STEPS, oneLeft), /1 question still has no answer/);

  // A complete pass the PC has ALREADY recorded is not offered Finish a second
  // time: there is nothing left to record, and the line says exactly that.
  const recorded = { ...STEPS, completedVersion: 2 };
  const done = Q.nextStep(recorded, {
    section: "notify", currentId: "notifications", draft: STEPS_EVERY_ANSWER,
  });
  assert.equal(done.kind, Q.STEP_END);
  assert.equal(done.why, Q.STEP_END_WORDS);

  // And on a PC whose module predates the versioned pass there is no record to
  // write at all - which is said, not silently ignored.
  const oldPc = Q.normaliseReading({
    available: true,
    questions: [{ id: "q1", title: "One", options: [{ id: "x", label: "X" }] }],
  });
  const oldEnd = Q.nextStep(oldPc, { currentId: "q1", draft: { q1: "x" } });
  assert.equal(oldEnd.kind, Q.STEP_END);
  assert.equal(oldEnd.why, Q.STEP_END_NO_RECORD);
  assert.match(oldEnd.why, /does not keep a record/);
});

await check("the reading carries the PC's own progress state, and tolerates every missing field", () => {
  assert.equal(STEPS.version, 2);
  assert.equal(STEPS.completedVersion, 1);
  assert.equal(STEPS.answeredCount, 5);
  assert.equal(STEPS.dismissedAt, null);
  assert.equal(STEPS.inProgress.question, "reworded_memories");
  assert.equal(STEPS.inProgress.section, "learning");
  assert.deepEqual(STEPS.inProgress.draftAnswers, { reworded_memories: "on" });
  assert.equal(STEPS.completedAt, null);
  assert.equal(STEPS.runs, 0);

  // An old three-key file, and a body with no progress fields at all: zeros,
  // never a guess and never a throw.
  const old = Q.normaliseReading({
    available: true, questions: [{ id: "a", title: "A", options: [{ id: "x" }] }],
  });
  assert.equal(old.version, 0);
  assert.equal(old.completedVersion, 0);
  assert.equal(old.inProgress, null);
  assert.equal(old.answeredCount, 0);
  assert.deepEqual(old.sections, []);
  // A corrupt `in_progress` is no position, not a crash.
  assert.equal(Q.normaliseReading({ available: true, questions: [], in_progress: "here" }).inProgress,
    null);
  assert.equal(Q.normaliseReading({
    available: true, questions: [], in_progress: { section: "learning" },
  }).inProgress, null, "a position with no question is not a position");
});

await check("the card's offer row honours Not now for the same day the toast does", () => {
  const at = 1_800_000_000;
  // Unfinished, never dismissed: offered.
  assert.equal(STEPS.version, 2);
  assert.equal(STEPS.completedVersion, 1);
  assert.equal(Q.offerShown(STEPS, at), true);
  // Dismissed now, an hour ago, a second before the day is up: not offered.
  // The row used to ignore `dismissed_at` entirely and paint itself again on
  // the next open, inside the very day it promised to stay quiet (audit
  // 2026-11-03, bug 4).
  const dismissed = { ...STEPS, dismissedAt: at };
  assert.equal(Q.offerShown(dismissed, at), false);
  assert.equal(Q.offerShown(dismissed, at + 3_600), false);
  assert.equal(Q.offerShown(dismissed, at + Q.OFFER_QUIET_SECS - 1), false);
  // Twenty-four hours later the offer is back, exactly as the toast's is.
  assert.equal(Q.offerShown(dismissed, at + Q.OFFER_QUIET_SECS), true);
  assert.equal(Q.offerShown(dismissed, at + Q.OFFER_QUIET_SECS + 60), true);
  // A clock that went backwards is still "just pressed": the quiet reading.
  assert.equal(Q.offerShown(dismissed, at - 60), false);
  // Zero is not a real press, so it hides nothing.
  assert.equal(Q.offerShown({ ...STEPS, dismissedAt: 0 }, at), true);
  // A finished pass is not offered whatever the clock says, and a PC without
  // the questionnaire offers nothing at all.
  assert.equal(Q.offerShown({ ...STEPS, completedVersion: 2 }, at), false);
  assert.equal(Q.offerShown(Q.normaliseReading({ available: false }), at), false);
  // The 24 hours is the Rust toast's own number, not a second opinion.
  const rust = read("src-tauri/src/setup_offer.rs");
  const hours = Number(
    /DISMISS_QUIET_SECS: f64 = ([0-9.]+) \* 60\.0 \* 60\.0/.exec(rust)[1],
  );
  assert.equal(hours * 3_600, Q.OFFER_QUIET_SECS, "one press, one length of quiet");
});

await check("the finished block never claims answers the pass does not have", () => {
  // Not finished: no block at all.
  assert.equal(Q.finishedPassWords(STEPS, STEPS_DRAFT), "");
  assert.equal(Q.finishedPassWords(Q.normaliseReading({ available: true }), {}), "");

  // "Keep current settings" records `completed_version` and writes NO answer,
  // so the block may not say "Every question the PC has is answered" - it used
  // to, and kept saying it (audit 2026-11-03, bug 5).
  const kept = { ...STEPS, completedVersion: 2 };
  const keptWords = Q.finishedPassWords(kept, STEPS_DRAFT);
  assert.equal(keptWords, `${Q.DONE_HEADING}. ${Q.KEPT_WORDS}`);
  assert.doesNotMatch(keptWords, /Every question the PC has is answered/);
  assert.match(keptWords, /still unanswered/);

  // Every question answered: the completion sentence, and only then.
  const all = {
    talk_style: "warm", personality: "calm_stoic", reading_tools: ["calendar"],
    lights_without_card: "off", learning: "learn", reworded_memories: "on",
    chat_history: "off", notifications: ["phone"],
  };
  assert.equal(Q.finishedPassWords(kept, all), `${Q.DONE_HEADING}. ${Q.DONE_WORDS}`);
  // One answer short is not completion, and an empty answer is not one either.
  const almost = { ...all };
  delete almost.chat_history;
  assert.equal(Q.finishedPassWords(kept, almost), `${Q.DONE_HEADING}. ${Q.KEPT_WORDS}`);
  assert.equal(Q.finishedPassWords(kept, { ...all, chat_history: "" }),
    `${Q.DONE_HEADING}. ${Q.KEPT_WORDS}`);
  // A reading with no questions is never "every question is answered".
  const empty = Q.normaliseReading({
    available: true, version: 2, completed_version: 2, questions: [],
  });
  assert.equal(Q.finishedPassWords(empty, {}), `${Q.DONE_HEADING}. ${Q.KEPT_WORDS}`);
  // And the two bodies are different words, not the same one twice.
  assert.notEqual(Q.DONE_WORDS, Q.KEPT_WORDS);
});

/* ── 4. The bridge: what is sent, and what can never be sent ─────────────── */

const calls = [];
let reply = async () => ({ available: true, questions: [] });
globalThis.__TAURI__ = {
  core: {
    invoke: async (command, args) => {
      calls.push({ command, args });
      return reply(command, args);
    },
  },
};
const reset = (answer) => {
  calls.length = 0;
  reply = answer || (async () => ({}));
};

await check("read sends one verb and no answers or confirm", async () => {
  reset(async () => ({ available: true, questions: [], card_wait_s: 300 }));
  const got = await Bridge.readSetup();
  assert.equal(got.available, true);
  assert.deepEqual(calls, [{ command: "setup_questionnaire", args: { action: "read" } }]);
  assert.ok(!("confirm" in calls[0].args));
  assert.ok(!("answers" in calls[0].args));
});

await check("plan sends only read-only answers - a plan can never carry confirm", async () => {
  reset(async () => ({ ok: true, changes: [] }));
  const body = Q.planBody({ style: "warm" });
  await Bridge.planSetup(body);
  assert.deepEqual(calls, [{
    command: "setup_questionnaire",
    args: { action: "plan", answers: { style: "warm" } },
  }]);
  assert.ok(!("confirm" in calls[0].args));
  assert.doesNotMatch(JSON.stringify(calls[0].args), /confirm/);
});

await check("apply sends the one write body, with confirm: true, and nothing else", async () => {
  reset(async () => ({ ok: true, confirmed: true, outcomes: [] }));
  await Bridge.applySetup(Q.applyBody({ style: "warm" }));
  assert.deepEqual(calls, [{
    command: "setup_questionnaire",
    args: { action: "apply", answers: { style: "warm" }, confirm: true },
  }]);
  assert.deepEqual(Object.keys(calls[0].args).sort(), ["action", "answers", "confirm"]);
  assert.equal(Bridge.COMMAND, "setup_questionnaire");
  assert.deepEqual(Bridge.VERBS, ["read", "plan", "progress", "apply"]);
});

await check("progress sends one small note, and never an answer's confirm", async () => {
  reset(async () => ({ ok: true }));
  await Bridge.progressSetup(Q.progressBody({ section: "learning", question: "learning" }));
  assert.deepEqual(calls, [{
    command: "setup_questionnaire",
    args: { action: "progress", progress: { section: "learning", question: "learning" } },
  }]);
  assert.ok(!("confirm" in calls[0].args));
  assert.ok(!("answers" in calls[0].args));
  assert.doesNotMatch(JSON.stringify(calls[0].args), /confirm/);

  // The three shapes, and only those. "Not now" wins over anything else that
  // was sent with it (the Rust builder applies the same order).
  assert.deepEqual(Q.progressBody({ dismiss: true, question: "learning" }), { dismiss: true });
  assert.deepEqual(Q.progressBody({ keepCurrent: true, question: "learning" }),
    { keep_current: true });
  assert.deepEqual(
    Q.progressBody({ section: "talk", question: "talk_style", draft: { talk_style: "warm" } }),
    { section: "talk", question: "talk_style", draft_answers: { talk_style: "warm" } });
  // Nothing staged means no draft field at all, not an empty object.
  assert.deepEqual(Q.progressBody({ question: "talk_style", draft: {} }),
    { question: "talk_style" });
  // EXCEPT for "Take it again", which needs the explicit empty object: the PC
  // merges a supplied draft and only an explicit `{}` clears it, while an
  // absent field means "keep what you have" - so the retake was undone on the
  // next open (audit 2026-11-03, bug 2).
  assert.deepEqual(
    Q.progressBody({ section: "talk", question: "talk_style", draft: {}, clearDraft: true }),
    { section: "talk", question: "talk_style", draft_answers: {} });
  // A clear that still has staged answers sends them as usual: the flag never
  // turns a real draft into a wipe.
  assert.deepEqual(
    Q.progressBody({ question: "talk_style", draft: { talk_style: "warm" }, clearDraft: true }),
    { question: "talk_style", draft_answers: { talk_style: "warm" } });
  assert.ok(!("confirm" in Q.progressBody({ question: "talk_style", clearDraft: true })));
  // It is never an apply: no confirm, no answers.
  for (const body of [Q.progressBody({ dismiss: true }),
    Q.progressBody({ keepCurrent: true }),
    Q.progressBody({ question: "talk_style", draft: { talk_style: "warm" } })]) {
    assert.ok(!("confirm" in body));
    assert.ok(!("answers" in body));
  }

  // A refusal comes back as words, not a throw and not a retry.
  reset(async () => { throw new Error("this PC has no progress route"); });
  const refused = await Bridge.progressSetup(Q.progressBody({ question: "learning" }));
  assert.equal(refused.ok, false);
  assert.match(refused.error, /no progress route/);
  assert.equal(calls.length, 1);
});

await check("a failed read or plan becomes words, and a failed apply is thrown - never retried", async () => {
  reset(async () => { throw new Error("the PC said no"); });
  const old = await Bridge.readSetup();
  assert.equal(old.available, false);
  assert.equal(old.why, "the PC said no");
  const plan = await Bridge.planSetup(Q.planBody({ style: "warm" }));
  assert.equal(plan.ok, false);
  assert.equal(plan.error, "the PC said no");
  await assert.rejects(() => Bridge.applySetup(Q.applyBody({ style: "warm" })), /the PC said no/);
  assert.equal(calls.length, 3, "one call each - no retry loop");
});

await check("the page's budget outlasts the Rust apply timeout", () => {
  const rust = read("src-tauri/src/setup_questionnaire.rs");
  const seconds = Number(
    /const APPLY_TIMEOUT: Duration = Duration::from_secs\(([0-9_]+)\)/
      .exec(rust)[1].replaceAll("_", ""),
  );
  assert.ok(seconds >= 3_600, `the Rust timeout is ${seconds}s`);
  assert.ok(Bridge.APPLY_BUDGET_MS > seconds * 1000,
    `page budget ${Bridge.APPLY_BUDGET_MS}ms must outlast the Rust ${seconds}s`);
  assert.ok(Bridge.PLAN_BUDGET_MS >= 30_000);
});

await check("the page names no route and no gate action, and never applies on load", () => {
  const page = read("src/setup-settings.js");
  const model = read("src/setup-questionnaire.js");
  // Comments may explain the routes; executable code may not carry one - the
  // Rust command is the only caller the parity check should see.
  const code = (source) => source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'])\/\/[^\n]*/g, "$1");
  for (const source of [page, model]) {
    assert.doesNotMatch(code(source), /\/api\//, "the route belongs to the Rust command");
    for (const action of ["change_own_config", "switch_model", "decide_approval",
      "loosen_what_asks_first", "approve_action"]) {
      assert.ok(!code(source).includes(action), `the page invents the gate action ${action}`);
    }
  }
  // `applySetup` is called from the confirm handler and nowhere else.
  assert.equal((page.match(/await applySetup\(/g) || []).length, 1,
    "one call to applySetup");
  const confirmAt = page.indexOf("async function confirmApply");
  const applyAt = page.indexOf("await applySetup(");
  assert.ok(confirmAt > 0 && applyAt > confirmAt,
    "the one apply call sits inside confirmApply");
  // load() (and refreshing the questions) never reaches the apply body.
  const loadAt = page.indexOf("async function load()");
  const loadEnd = page.indexOf("function onAnswered()");
  const loadBody = page.slice(loadAt, loadEnd);
  assert.ok(loadAt > 0 && loadEnd > loadAt);
  assert.doesNotMatch(loadBody, /applySetup|applyBody/,
    "loading the card never applies anything");
  // Two races the card must not lose: a plan answer that arrives after the
  // answers changed is dropped, and no answer can change while an apply runs.
  assert.match(page, /generation !== planGeneration/,
    "a late plan answer must be dropped");
  assert.match(page, /setQuestionsEnabled\(!busy\)/,
    "the questionnaire is disabled while the one apply runs");
  assert.match(page, /confirmYes\.disabled = !gate\(/,
    "the confirm press is held by the same gate as the first press");
  // The model's planBody must not carry confirm (applyBody is the only one).
  const bareModel = code(model);
  const planAt = bareModel.indexOf("export function planBody");
  const applyBodyAt = bareModel.indexOf("export function applyBody");
  assert.ok(planAt > 0 && applyBodyAt > planAt);
  assert.ok(!bareModel.slice(planAt, applyBodyAt).includes("confirm"),
    "planBody never builds a confirm");
});

await check("the card paints the three honest states from the model", () => {
  const page = read("src/setup-settings.js");
  // Bugs 4, 5 and 6 were each a sentence computed in the page: the offer row
  // ignored the PC's dismissal, the done block claimed answers it did not
  // have, and the empty panel tested a different set from the count above it.
  assert.match(page, /offerShown\(reading, Date\.now\(\) \/ 1000\)/,
    "the offer row decides from the PC's dismissal again");
  assert.match(page, /finishedPassWords\(reading, draft\)/,
    "the done block words itself from its own idea of finished");
  assert.match(page, /filterEmptyWords\(reading, \{ section, filter: filterOn \}\)/,
    "the empty panel is not the count's own set");
  for (const word of ["DONE_HEADING", "DONE_WORDS", "FILTER_EMPTY"]) {
    assert.ok(!page.includes(word), `the page still words ${word} itself`);
  }
  // "Take it again" sends the explicit empty draft AT ONCE - not through the
  // debounced position note, which the next answer would replace (bug 2).
  assert.match(page, /clearDraft: true/);
  const takeAt = page.indexOf("function takeAgain()");
  const takeEnd = page.indexOf("function planRows(");
  assert.ok(takeAt > 0 && takeEnd > takeAt, "takeAgain is gone from the page");
  const takeBody = page.slice(takeAt, takeEnd);
  assert.ok(takeBody.includes("clearStagedDraft()"),
    "the retake never clears the draft the PC stores");
  assert.ok(!takeBody.includes("queueProgress()"),
    "the retake's clear rides the debounce, where the next note replaces it");
});

await check("the page paints Finish from the model's one rule, and Finish records the pass", () => {
  const page = read("src/setup-settings.js");
  // The label, the disabled state and the sentence under the row all come from
  // `nextStep`. A second idea of what the next step is, in the page, is exactly
  // what made the last question a press that did nothing (2026-11-13).
  assert.equal((page.match(/const action = nextStep\(reading, \{/g) || []).length, 2,
    "the painted row and the press read the same rule");
  assert.match(page, /el\.next\.textContent = action\.kind === STEP_FINISH \? FINISH : NEXT/);
  assert.match(page, /el\.next\.disabled = busy \|\| action\.kind === STEP_END/);
  assert.ok(!page.includes("shown.length <= 1 ? FINISH"),
    "Finish is not painted from how many questions happen to be on screen");
  const nextAt = page.indexOf("function goNext()");
  const backAt = page.indexOf("function goBack()");
  assert.ok(nextAt > 0 && backAt > nextAt, "goNext is gone from the page");
  const nextBody = page.slice(nextAt, backAt);
  assert.ok(nextBody.includes("action.kind === STEP_FINISH"),
    "the press routes Finish nowhere, so Finish is painted and not wired");
  assert.ok(nextBody.includes("void finishPass()"), "Finish does not record anything");
  assert.ok(!nextBody.includes("findIndex"),
    "the page works the next step out itself again");
  // Finish is the same cardless `{"keep_current": true}` note "Keep current
  // settings" already sends: it records the pass, writes no answer and changes
  // no setting - so it may never reach the apply body or the apply call.
  const finishAt = page.indexOf("async function finishPass()");
  const loadAt = page.indexOf("async function load()");
  assert.ok(finishAt > 0 && loadAt > finishAt, "finishPass is gone from the page");
  const finishBody = page.slice(finishAt, loadAt);
  assert.ok(finishBody.includes("recordPassComplete()"),
    "Finish does not record the pass as complete");
  assert.ok(!finishBody.includes("applySetup") && !finishBody.includes("applyBody"),
    "Finish must never apply an answer: Apply is the only write");
  assert.equal((page.match(/progressBody\(\{ keepCurrent: true \}\)/g) || []).length, 1,
    "the completion note is built in one place, for both buttons");
});

await check("the Rust command builds the bodies, refuses without confirm, and holds only apply on a stale link", () => {
  const rust = read("src-tauri/src/setup_questionnaire.rs");
  assert.match(rust, /pub\(crate\) const PATH: &str = "\/api\/setup";/);
  assert.match(rust, /PLAN_PATH: &str = "\/api\/setup\/plan";/);
  assert.match(rust, /PROGRESS_PATH: &str = "\/api\/setup\/progress";/);
  assert.match(rust, /APPLY_PATH: &str = "\/api\/setup\/apply";/);
  assert.match(rust, /confirm != Some\(true\)/);
  assert.match(rust, /\{ "answers": answers, "confirm": true \}/);
  assert.match(rust, /const ACTIONS: &\[&str\] = &\["read", "plan", "progress", "apply"\];/);
  // Three slices of the command: the read-only plan and the progress note are
  // never held on a stale link, and the one write always is. Written per
  // slice, so a passing line in one branch cannot cover another.
  const planAt = rust.indexOf('"plan" =>');
  const progressAt = rust.indexOf('"progress" =>');
  const applyAt = rust.indexOf("The only verb left");
  const testsAt = rust.indexOf("#[cfg(test)]");
  assert.ok(planAt > 0 && progressAt > planAt && applyAt > progressAt && testsAt > applyAt);
  // `.stale` is the code expression; the comments in these arms may explain a
  // stale link without holding on one.
  assert.ok(!rust.slice(planAt, progressAt).includes(".stale"),
    "a read-only plan is not held on a stale link");
  assert.ok(!rust.slice(progressAt, applyAt).includes(".stale"),
    "a progress note is not held on a stale link");
  assert.match(rust.slice(applyAt, testsAt), /\.link\(\)\s*\.stale/,
    "the write is held on a stale link");
  // A fifth verb is refused before any body is built.
  assert.match(rust, /if !ACTIONS\.contains\(&verb\)/);
  // The progress body is one of exactly three small shapes: a dismissal, a
  // keep-current, or where the owner is - and an unknown field is refused
  // rather than passed on.
  assert.match(rust, /const FIELDS: &\[&str\] = &\[/);
  assert.match(rust, /"keep_current": true/);
  // No approval machinery in this module: it can only ask the PC.
  for (const name of ["decide_approval", "approve_approval", "jarvis_gate", "deny("]) {
    assert.ok(!rust.includes(name), `the command must not call ${name}`);
  }
});

await check("the wiring is real: the card, the command, its permissions and the phone's read-only row", () => {
  // Desktop: the Settings card (with the section tabs, the mode row, the
  // progress line and the filter), its script tag and its jump link; the
  // module; the command list; the permission set and the capability; the
  // generated permission files. A dropped line here means the page or the
  // command is unreachable, which no unit test of the model above would
  // notice.
  const settingsHtml = read("src/settings.html");
  assert.match(settingsHtml, /<section class="card" id="setup-questionnaire">/);
  // The place other surfaces ask for by name, on the card's first line.
  assert.match(settingsHtml, /<span id="personalize-jarvis" class="place-anchor"><\/span>/);
  assert.match(settingsHtml, /id="sq-body"/);
  assert.match(settingsHtml, /id="sq-sections"[^>]*role="tablist"/);
  assert.match(settingsHtml, /id="sq-step"[^>]*>Step through one by one</);
  assert.match(settingsHtml, /id="sq-showall"/);
  assert.match(settingsHtml, /id="sq-progress"/);
  assert.match(settingsHtml, /id="sq-filter"/);
  assert.match(settingsHtml, /id="sq-not-now"/);
  assert.match(settingsHtml, /id="sq-keep"/);
  assert.match(settingsHtml, /id="sq-again"/);
  assert.match(settingsHtml, /<script type="module" src="setup-settings.js"><\/script>/);
  assert.match(settingsHtml, /href="#setup-questionnaire">Personalize Atlas</);
  // The notification switch's page row comes from the generated catalogue
  // (`tools/gen_settings_cases.py`, from the backend registry). Wave B's
  // backend half landed the registry row, so the row is on the page now: what
  // this pins is that it is the GENERATED row, spelled the way the catalogue
  // spells every other notification toggle.
  assert.match(settingsHtml, /<input id="notif-setup" type="checkbox" checked \/>/,
    "the notification switch's generated row is on the page");

  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /pub mod setup_questionnaire;/);
  assert.match(lib, /setup_questionnaire::setup_questionnaire,/);
  // Wave B: the offer module, its state and its one command.
  assert.match(lib, /pub mod setup_offer;/);
  assert.match(lib, /setup_offer::hud_setup_dismiss,/);
  assert.match(lib, /manage\(setup_offer::SetupOfferState::default\(\)\)/);
  assert.match(lib, /setup_offer::refresh_setup_state/);
  assert.match(lib, /setup_offer::offer_once/);
  assert.match(lib, /setup_offer::offer_after_onboarding/);

  const build = read("src-tauri/build.rs");
  assert.match(build, /"setup_questionnaire",/);
  assert.match(build, /"hud_setup_dismiss",/);

  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /identifier = "setup-questionnaire"/);
  assert.match(surfaces, /permissions = \["allow-setup-questionnaire"\]/);
  // The HUD's banner sets are the ones it already holds: one navigation door
  // and one dismissal.
  assert.match(surfaces, /"allow-hud-setup-dismiss",/);
  assert.match(surfaces, /"allow-open-fix-place",/);

  const capabilities = read("src-tauri/capabilities/settings.json");
  assert.match(capabilities, /"setup-questionnaire",/);
  assert.match(read("src-tauri/capabilities/hud.json"), /"hud-link",/);

  const generated = read("src-tauri/permissions/autogenerated/setup_questionnaire.toml");
  assert.match(generated, /identifier = "allow-setup-questionnaire"/);
  assert.match(generated, /commands\.allow = \["setup_questionnaire"\]/);
  const generatedDismiss = read("src-tauri/permissions/autogenerated/hud_setup_dismiss.toml");
  assert.match(generatedDismiss, /identifier = "allow-hud-setup-dismiss"/);
  assert.match(generatedDismiss, /commands\.allow = \["hud_setup_dismiss"\]/);

  // The HUD's own banner: the read, the two buttons and the one command.
  const hud = read("src/jarvis_hud.html");
  assert.match(hud, /id="setup-offer"/);
  assert.match(hud, /id="setup-offer-finish"/);
  assert.match(hud, /id="setup-offer-not-now"/);
  assert.match(hud, /jfetch\("\/api\/setup"/);
  assert.match(hud, /core\.invoke\("open_fix_place", \{place:"personalize-jarvis"\}\)/);
  assert.match(hud, /core\.invoke\("hud_setup_dismiss"\)/);
  // The read is on the HUD's allow-list, and the writes beside it are not. The
  // constant's own block is what is checked: the refused-path test below it
  // names the writes to prove they are refused, which is not the same thing as
  // allowing them.
  const proxy = read("src-tauri/src/hud_proxy.rs");
  assert.match(proxy, /HUD_GET_PATHS: \[&str; 15\]/);
  const arrayAt = proxy.indexOf("HUD_GET_PATHS: [&str; 15]");
  const arrayEnd = proxy.indexOf("];", arrayAt);
  const allowed = proxy.slice(arrayAt, arrayEnd);
  assert.match(allowed, /"\/api\/setup",/);
  assert.ok(!allowed.includes("/api/setup/progress"));
  assert.ok(!allowed.includes("/api/setup/apply"));

  // The tray's row is driven by the same state and opens the same place.
  const tray = read("src-tauri/src/tray.rs");
  assert.match(tray, /ID_SETUP/);
  assert.match(tray, /pub fn on_setup_state\(/);
  assert.match(tray, /show_settings_at\(app, "personalize-jarvis"\)/);

  // The place is in the closed list both surfaces ask through.
  assert.match(read("src-tauri/src/windows.rs"),
    /SETTINGS_PLACES: \[&str; 2\] = \["updates", "personalize-jarvis"\]/);
  assert.match(read("src-tauri/src/plain_errors.rs"),
    /"personalize-jarvis" => crate::windows::show_settings_at\(&app, "personalize-jarvis"\)/);

  // Phone: its Settings row, jump entry, search row and the two READS. It has
  // no apply path, and no source file may name one. The TITLE is the phone
  // session's to rename (Wave B gives both apps the same words) - what this
  // suite holds is the id and the two reads, which cannot change on either
  // side without the other knowing.
  const screen = repoRead(
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt",
  );
  assert.match(screen, /item\(key = "setup-questionnaire"\)/);
  assert.match(repoRead("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt"),
    /Entry\("(?:First-time setup|Personalize Jarvis)", "setup-questionnaire"\)/);
  assert.match(repoRead("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt"),
    /key = "setup-questionnaire", title = "(?:First-time setup|Personalize Jarvis)"/);
  const api = repoRead("jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt");
  assert.match(api, /probe\(SetupQuestionnaire\.PATH\)/);
  assert.match(api, /postObject\(SetupQuestionnaire\.PLAN_PATH/);
  const runtime = repoRead("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt");
  assert.match(runtime, /suspend fun setupQuestionnaire\(\)/);
  assert.match(runtime, /suspend fun setupPlan\(body: String\)/);
  for (const [name, source] of [["JarvisApi", api], ["JarvisRuntime", runtime],
    ["SettingsScreen", screen]]) {
    assert.ok(!source.includes("/api/setup/apply"), `${name} must name no apply route`);
  }
});

/* ── Verdict ─────────────────────────────────────────────────────────────── */

console.log(`\n${passed} passed, ${failed} failed${skipped ? `, ${skipped} skipped (a skip is not a pass)` : ""}`);
if (skipped) console.log(PY.summary().trim());
if (failed) process.exit(1);
