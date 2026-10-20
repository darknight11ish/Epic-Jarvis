/**
 * The setup questionnaire on the desktop: the model, the bridge, the page's
 * one action, and the PC's real fourteen questions.
 *
 * Part 1 reads the PC's own questions from `backend/jarvis_setup.py` with the
 * real Python interpreter (`tests/lib/python.mjs`), so this suite cannot pass
 * against a hand-written idea of the questionnaire: the count, the ids, the
 * options and the order are the PC's. When there is no Python on this machine
 * those checks SKIP and say so - a skip is not a pass.
 *
 * Part 2 is the model: the reading, the draft ("All"/"None" expand at the data
 * level), the READ-ONLY plan body, the one apply body (the only one carrying
 * `confirm: true`), the effect words (instant / card / blocked - never
 * rounded), the gate a stale link holds, and the honest outcomes (a card still
 * waiting is NOT "failed" and NOT "done").
 *
 * Part 3 is a fake bridge: what the page sends for read, plan and apply, and
 * that a read or a plan can never carry `confirm`. It also reads the Rust and
 * the page as text for the wiring and for what must NOT be there: no route
 * name in the page, no gate action, no auto-apply on load.
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
    } for q in S.QUESTIONS],
}))
`);

function needLive() {
  if (!LIVE || !Array.isArray(LIVE.questions)) {
    PY.skip("the PC's questions", "no Python here - the real backend module was not read");
  }
  return LIVE.questions;
}

await check("the PC's questionnaire is fourteen questions, each with choices", () => {
  const questions = needLive();
  assert.equal(questions.length, 14, `the PC sent ${questions.length} questions`);
  const ids = questions.map((q) => q.id);
  assert.equal(new Set(ids).size, ids.length, "question ids are unique");
  for (const q of questions) {
    assert.ok(q.title && q.help, `${q.id} has a title and a help line`);
    assert.ok(q.options.length >= 2, `${q.id} offers at least two choices`);
    assert.equal(new Set(q.options.map((o) => o.id)).size, q.options.length,
      `${q.id}'s choice ids are unique`);
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
  assert.equal(fixture.count, 14, "the fixture says fourteen questions");
  assert.equal(fixture.generated_by, "tools/gen_setup_questions.py");
  assert.equal(fixture.source, "backend/jarvis_setup.py");
  assert.deepEqual(fixture.questions, questions,
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

/* ── 3. The bridge: what is sent, and what can never be sent ─────────────── */

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
  assert.deepEqual(Bridge.VERBS, ["read", "plan", "apply"]);
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
  // The model's planBody must not carry confirm (applyBody is the only one).
  const bareModel = code(model);
  const planAt = bareModel.indexOf("export function planBody");
  const applyBodyAt = bareModel.indexOf("export function applyBody");
  assert.ok(planAt > 0 && applyBodyAt > planAt);
  assert.ok(!bareModel.slice(planAt, applyBodyAt).includes("confirm"),
    "planBody never builds a confirm");
});

await check("the Rust command builds the bodies, refuses without confirm, and holds only apply on a stale link", () => {
  const rust = read("src-tauri/src/setup_questionnaire.rs");
  assert.match(rust, /pub\(crate\) const PATH: &str = "\/api\/setup";/);
  assert.match(rust, /PLAN_PATH: &str = "\/api\/setup\/plan";/);
  assert.match(rust, /APPLY_PATH: &str = "\/api\/setup\/apply";/);
  assert.match(rust, /confirm != Some\(true\)/);
  assert.match(rust, /\{ "answers": answers, "confirm": true \}/);
  // The plan branch never checks the link; the apply branch does, before the
  // post. Two slices of the command, so the check cannot pass on the other
  // branch's line.
  const planAt = rust.indexOf('"plan" =>');
  const applyAt = rust.indexOf("The only verb left");
  const testsAt = rust.indexOf("#[cfg(test)]");
  assert.ok(planAt > 0 && applyAt > planAt && testsAt > applyAt);
  assert.ok(!rust.slice(planAt, applyAt).includes("stale"),
    "a read-only plan is not held on a stale link");
  assert.match(rust.slice(applyAt, testsAt), /\.link\(\)\s*\.stale/,
    "the write is held on a stale link");
  // A fourth verb is refused before any body is built.
  assert.match(rust, /if !ACTIONS\.contains\(&verb\)/);
  // No approval machinery in this module: it can only ask the PC.
  for (const name of ["decide_approval", "approve_approval", "jarvis_gate", "deny("]) {
    assert.ok(!rust.includes(name), `the command must not call ${name}`);
  }
});

await check("the wiring is real: the card, the command, its one permission and the phone's read-only row", () => {
  // Desktop: the Settings card, its script tag and its jump link; the module;
  // the command list; the one permission set and the capability; the generated
  // permission file. A dropped line here means the page or the command is
  // unreachable, which no unit test of the model above would notice.
  const settingsHtml = read("src/settings.html");
  assert.match(settingsHtml, /<section class="card" id="setup-questionnaire">/);
  assert.match(settingsHtml, /id="sq-body"/);
  assert.match(settingsHtml, /<script type="module" src="setup-settings.js"><\/script>/);
  assert.match(settingsHtml, /href="#setup-questionnaire"/);

  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /pub mod setup_questionnaire;/);
  assert.match(lib, /setup_questionnaire::setup_questionnaire,/);

  const build = read("src-tauri/build.rs");
  assert.match(build, /"setup_questionnaire",/);

  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /identifier = "setup-questionnaire"/);
  assert.match(surfaces, /permissions = \["allow-setup-questionnaire"\]/);

  const capabilities = read("src-tauri/capabilities/settings.json");
  assert.match(capabilities, /"setup-questionnaire",/);

  const generated = read("src-tauri/permissions/autogenerated/setup_questionnaire.toml");
  assert.match(generated, /identifier = "allow-setup-questionnaire"/);
  assert.match(generated, /commands\.allow = \["setup_questionnaire"\]/);

  // Phone: its Settings row, jump entry, search row and the two READS. It has
  // no apply path, and no source file may name one.
  const screen = repoRead(
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt",
  );
  assert.match(screen, /item\(key = "setup-questionnaire"\)/);
  assert.match(repoRead("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsJump.kt"),
    /Entry\("First-time setup", "setup-questionnaire"\)/);
  assert.match(repoRead("jarvis-client/app/src/main/java/com/jarvis/client/ui/SettingsSearch.kt"),
    /key = "setup-questionnaire", title = "First-time setup"/);
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
