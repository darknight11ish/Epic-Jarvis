/**
 * Goal step locks (docs/GOALS-PROGRESS-DESIGN.md "Slice contract (frozen)";
 * JARVIS-API.md section 101; src/goals.js, brain.js paintGoals,
 * src-tauri/src/brain/goals.rs) - the part that needs no browser.
 *
 * What must hold:
 * - the lock sentences are the contract file's (`goal_words`), word for word;
 * - every real answer of the real backend reads (`goal_cases`): the state of
 *   each step, its lock sentence, its number, its id;
 * - a row shows the PC's own sentences and never works a state out itself;
 * - only the stored fields are sent back on a save (never a computed field,
 *   never `done_at`);
 * - the draft editor gives a new step a free id, stops "Do these first" at
 *   three, and takes a deleted step out of the others' lists;
 * - "Follows a number" offers the number benchmarks with a target and a
 *   direction, life and coding projects alike.
 *
 * The browser half (rows, pickers, the 409, Undo) is in tests/goals.mjs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  DEFAULT_LIMITS,
  freeStepId,
  GOAL_WORDS,
  benchProjectIds,
  measureChoices,
  needChoices,
  newStep,
  planBody,
  readGoals,
  removeStepAt,
  setNeed,
  stepRow,
  storedStep,
} from "../src/goals.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/projects-cases.json"));
const GC = CASES.goal_cases;
const LIFE_ID = CASES.cases.life.project.id;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const DRAFT = { id: "g0000000001", text: "insulate the garage",
  plan: [{ step: "insulate the garage", by: "", done: false }], status: "draft", created: 1, changed: 1 };
const ACTIVE = { id: "g0000000002", text: "learn to bake bread",
  plan: [{ step: "buy flour", by: "this week", done: true }, { step: "try a recipe", by: "", done: false }],
  status: "active", created: 2, changed: 2 };

const goalOf = (post, status = "active", id = "g0000000010") => ({ ...(post.body || post).goal, status, id });


await check("the lock sentences are the contract's, key for key and word for word", async () => {
  assert.deepEqual(GOAL_WORDS, CASES.goal_words);
  assert.deepEqual(DEFAULT_LIMITS.needs, CASES.goal_limits.needs);
  assert.equal(DEFAULT_LIMITS.steps, CASES.goal_limits.steps);
});

await check("every real goal answer reads: states, locks, numbers, ids and the rest", async () => {
  const made = readGoals({ goals: [goalOf(GC.created, "draft")], limits: GC.list.limits });
  assert.equal(made.locks, true);
  assert.equal(made.limits.needs, 3);
  const [s1, s2, s3] = made.goals[0].plan;
  assert.deepEqual([s1.id, s2.id, s3.id], ["s1", "s2", "s3"]);
  assert.deepEqual([s1.state, s2.state, s3.state], ["open", "locked", "locked"]);
  assert.deepEqual(s2.needs, ["s1"]);
  assert.deepEqual(s2.waitingOn, ["s1"]);
  assert.equal(s2.lockWords, 'after: "Get the 5k under 30"');
  assert.deepEqual(s1.measure, { project: "a".repeat(32), bench: "b".repeat(32) });
  assert.equal(s1.measureName, "5k time");
  const reached = readGoals({ goals: [goalOf(GC.number_reached)] }).goals[0].plan[0];
  assert.equal(reached.state, "met_by_number");
  assert.equal(reached.reached, true);
  assert.equal(reached.reachedWords, "The number reached its target: 29.5 min (target 30 min).");
  assert.equal(reached.done, false, "reaching a target never ticks the step");
  const undone = readGoals({ goals: [goalOf(GC.first_undone)] }).goals[0].plan;
  assert.equal(undone[1].done, true);
  assert.equal(undone[1].state, "done");
  assert.equal(undone[1].doneAt, 1790000120);
  // A step from an older PC: no id, no state - open or done, no locks.
  const old = readGoals({ goals: [DRAFT, ACTIVE] });
  assert.equal(old.goals[1].plan[0].state, "done");
  assert.equal(old.goals[1].plan[1].state, "open");
  assert.equal(old.goals[1].plan[1].id, "");
  assert.deepEqual(old.goals[1].plan[1].needs, []);
});

await check("a row shows the PC's sentences as sent and never works out a state itself", async () => {
  const plan = readGoals({ goals: [goalOf(GC.created)] }).goals[0].plan;
  const r2 = stepRow(plan[1]);
  assert.equal(r2.locked, true);
  assert.equal(r2.lockLine, 'after: "Get the 5k under 30"');
  assert.equal(r2.reason, r2.lockLine, "a locked tick says why");
  assert.equal(r2.label, 'Enter the race, locked, after: "Get the 5k under 30"');
  const r1 = stepRow(plan[0]);
  assert.equal(r1.locked, false);
  assert.equal(r1.follows, "Follows: 5k time");
  const met = stepRow(readGoals({ goals: [goalOf(GC.number_reached)] }).goals[0].plan[0]);
  assert.equal(met.locked, false, "met by number is not locked");
  assert.equal(met.reached, true);
  assert.equal(met.reachedLine, "The number reached its target: 29.5 min (target 30 min).");
  // A step ticked before its earlier one was unticked reads "(open again)".
  const reopened = { ...plan[1], state: "done", done: true, lockWords: 'after: "Get the 5k under 30" (open again)' };
  const ro = stepRow(reopened);
  assert.equal(ro.locked, false);
  assert.equal(ro.lockLine, 'after: "Get the 5k under 30" (open again)');
  // The number this step followed was deleted.
  const gone = stepRow({ ...plan[0], measureGone: true, measureName: "" });
  assert.equal(gone.goneLine, GOAL_WORDS.measure_gone);
  assert.equal(gone.follows, "");
  // A sensitive number's name and sentence hide with the private lists.
  const priv = { ...readGoals({ goals: [goalOf(GC.number_reached)] }).goals[0].plan[0], measureSensitive: true };
  assert.equal(stepRow(priv).reachedLine.length > 0, true);
  assert.equal(stepRow(priv, { hideWords: true }).reachedLine, "");
  assert.equal(stepRow(priv, { hideWords: true }).follows, "");
});

await check("only the stored fields are sent back, never the computed ones or done_at", async () => {
  const plan = readGoals({ goals: [goalOf(GC.first_undone, "draft")] }).goals[0].plan;
  const body = planBody(plan);
  for (const st of body) {
    assert.deepEqual(Object.keys(st).sort(), ["by", "done", "id", "measure", "needs", "step"]);
  }
  assert.deepEqual(body[0].measure, { project: "a".repeat(32), bench: "b".repeat(32) });
  assert.deepEqual(body[1].needs, ["s1"]);
  assert.equal(JSON.stringify(body).includes("done_at"), false);
  assert.equal(JSON.stringify(body).includes("lock_words"), false);
  assert.deepEqual(Object.keys(storedStep({ step: "x" })).sort(), ["by", "done", "measure", "needs", "step"],
    "a new step has no id key");
});

await check("the editor: a new step takes a free id; Remove cleans the others; three is the most", async () => {
  const plan = readGoals({ goals: [goalOf(GC.created, "draft")] }).goals[0].plan.map((s) => ({ ...s }));
  assert.equal(freeStepId(plan), "s4");
  const added = newStep(plan);
  assert.equal(added.id, "s4");
  assert.equal(newStep(plan, false).id, undefined, "no ids without lock support");
  plan.push(added);
  const choices = needChoices(plan, 1);
  assert.deepEqual(choices.map((c) => c.id), ["s1", "s3", "s4"], "the OTHER steps, not itself");
  assert.equal(choices[0].label, "1. Get the 5k under 30");
  // Up to three, then it stops.
  const st = { needs: [] };
  assert.equal(setNeed(st, "s1", true, 3), true);
  assert.equal(setNeed(st, "s2", true, 3), true);
  assert.equal(setNeed(st, "s3", true, 3), true);
  assert.equal(setNeed(st, "s4", true, 3), false, "the fourth is refused before it is sent");
  assert.deepEqual(st.needs, ["s1", "s2", "s3"]);
  assert.equal(setNeed(st, "s2", false, 3), true);
  assert.deepEqual(st.needs, ["s1", "s3"]);
  // Deleting s1 takes it out of s2's list and says how many were touched.
  const { gone, touched } = removeStepAt(plan, 0);
  assert.equal(gone.id, "s1");
  assert.equal(touched, 1);
  assert.deepEqual(plan.find((s) => s.id === "s2").needs, []);
});

await check("Follows a number offers the life AND coding number benchmarks with a target and a direction", async () => {
  const CODING_ID = CASES.cases.coding.project.id;
  assert.deepEqual(benchProjectIds(CASES.cases.list_two), [LIFE_ID, CODING_ID]);
  const choices = measureChoices(CASES.cases.list_two, [CASES.cases.life, CASES.cases.coding]);
  const names = choices.map((c) => c.label).sort();
  const expect = [CASES.cases.life, CASES.cases.coding].flatMap((c) => c.project.benchmark_list
    .filter((b) => b.kind === "number" && b.target !== null && b.target !== undefined && b.better)
    .map((b) => `${c.project.name} - ${b.name}`)).sort();
  assert.deepEqual(names, expect);
  assert.ok(names.some((n) => n.endsWith(" - Startup")), "a coding project's number benchmark is offered");
  assert.ok(names.some((n) => n.startsWith("Half marathon - ")), "a life project's too");
  assert.equal(names.some((n) => n.endsWith(" - tests")), false, "a command benchmark is never offered");
  assert.deepEqual(measureChoices({ ok: true, hidden: true }, [{ hidden: true }]), []);
  assert.deepEqual(measureChoices(null, null), []);
  assert.deepEqual(benchProjectIds({ ok: true, hidden: true }), []);
});

await check("the shared wording: every screen sentence is in the contract, and the pieces read right", async () => {
  for (const k of ["follows_none", "follows_under", "follows_empty", "needs_cleaned", "needs_limit",
    "needs_none", "needs_under", "reached_tag", "ticked", "unticked"]) {
    assert.ok(typeof CASES.goal_words[k] === "string" && CASES.goal_words[k].length > 0, k);
  }
  assert.equal(GOAL_WORDS.follows_none, "No number");
  assert.equal(GOAL_WORDS.needs_limit, "At most {max} steps can come first.");
  assert.equal(GOAL_WORDS.reached_tag, "number reached");
});


console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nGoal locks: states, sentences and saves read from the contract, no state worked out here");
process.exit(fails.length ? 1 : 0);
