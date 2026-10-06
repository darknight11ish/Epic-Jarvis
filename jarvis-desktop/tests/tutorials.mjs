/**
 * Tutorials and the FAQ, on the PC side (src/tutorials.js).
 *
 * WHAT IS CHECKED
 *
 * * the two sections, and that the shared tutorials appear in both - the whole
 *   point of "the same tutorials on both apps, a section for each";
 * * quitting and resuming: the step recorded is the step offered to continue
 *   at, and a tutorial that was never started still opens at step 1;
 * * Next stops at the last step instead of running past it, and Back stops at
 *   the first;
 * * the words a row shows for each state, including the offer to show a
 *   finished or skipped one again;
 * * the FAQ search looks in the question AND the answer, and says so plainly
 *   when nothing matches;
 * * what a step writes back to the PC (`{id, state, step}`);
 * * the labels and section ids here are the backend's own, read out of
 *   backend/jarvis_tutorials.py - so the catalogue, the PC and (once it
 *   exists) the phone cannot drift apart without this failing.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import * as T from "../src/tutorials.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..");
let passed = 0;

function check(what, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${what}`);
}

const tutorial = (over = {}) => ({
  id: "memory", section: "both", title: "What Jarvis remembers", why: "…",
  minutes: 3, steps: [{}, {}, {}, {}, {}], steps_total: 5,
  state: "not_started", step: 0, done: false, resume_at: null, due: true,
  changed_since: false, ...over,
});

const CATALOGUE = {
  ok: true,
  sections: [{ id: "pc", title: "On this PC" }, { id: "phone", title: "On your phone" }],
  tutorials: [
    tutorial({ id: "intro", section: "both" }),
    tutorial({ id: "memory", section: "both" }),
    tutorial({ id: "pc-at-a-glance", section: "pc" }),
    tutorial({ id: "phone-pairing", section: "phone", steps_total: 4, steps: [{}, {}, {}, {}] }),
  ],
  counts: { done: 0, due: 4, total: 4 },
};

check("the PC section is its own tutorials plus the shared ones", () => {
  const ids = T.sectionList(CATALOGUE, "pc").map((t) => t.id);
  assert.deepEqual(ids, ["intro", "memory", "pc-at-a-glance"]);
});

check("the phone section is its own plus the shared ones", () => {
  const ids = T.sectionList(CATALOGUE, "phone").map((t) => t.id);
  assert.deepEqual(ids, ["intro", "memory", "phone-pairing"]);
});

check("a phone tutorial never appears in the PC's own section", () => {
  const pc = T.sectionList(CATALOGUE, "pc").map((t) => t.id);
  assert.ok(!pc.includes("phone-pairing"));
});

check("the step counter reads the way a person says it", () => {
  assert.equal(T.stepWords(tutorial(), 0), "Step 1 of 5");
  assert.equal(T.stepWords(tutorial(), 4), "Step 5 of 5");
});

check("Next stops at the last step rather than running past it", () => {
  assert.equal(T.nextIndex(tutorial(), 0), 1);
  assert.equal(T.nextIndex(tutorial(), 3), 4);
  assert.equal(T.nextIndex(tutorial(), 4), null);
});

check("Back stops at the first step", () => {
  assert.equal(T.backIndex(0), null);
  assert.equal(T.backIndex(2), 1);
});

check("a tutorial nobody opened opens at step 1", () => {
  assert.equal(T.startIndex(tutorial()), 0);
  assert.equal(T.startIndex(tutorial({ state: "in_progress", resume_at: 3 })), 3);
});

check("a resume point past the end is ignored, not trusted", () => {
  assert.equal(T.startIndex(tutorial({ state: "in_progress", resume_at: 99 })), 0);
});

check("a row says where the owner is, in words", () => {
  assert.equal(T.stateWords(tutorial()), "Not started");
  assert.equal(T.stateWords(tutorial({ done: true, state: "done" })), "Done");
  assert.equal(T.stateWords(tutorial({ state: "in_progress", resume_at: 2 })),
    "Continue at step 3");
  assert.equal(T.stateWords(tutorial({ state: "skipped" })), "Skipped");
});

check("a finished or skipped tutorial is offered again, a fresh one is not", () => {
  assert.equal(T.showsAgain(tutorial({ done: true, state: "done" })), true);
  assert.equal(T.showsAgain(tutorial({ state: "skipped" })), true);
  assert.equal(T.showsAgain(tutorial()), false);
});

check("a step writes back exactly what the route wants", () => {
  assert.deepEqual(T.progressBody(tutorial({ id: "intro" }), 2),
    { id: "intro", state: "in_progress", step: 2 });
  assert.deepEqual(T.progressBody(tutorial({ id: "intro" }), 4, "done"),
    { id: "intro", state: "done", step: 4 });
});

const FAQ = [
  { q: "Does Jarvis send my things anywhere?", a: "Only the named exceptions.", where: "What asks first" },
  { q: "How do I make it forget something?", a: "Erase the words wipes the text.", where: "Brain → Memory" },
];

check("the FAQ search looks in the question", () => {
  assert.deepEqual(T.searchFaq(FAQ, "forget").map((q) => q.q), [FAQ[1].q]);
});

check("and in the answer, which is where the remembering word often is", () => {
  assert.deepEqual(T.searchFaq(FAQ, "wipe").map((q) => q.q), [FAQ[1].q]);
});

check("an empty search shows everything, and nothing matching says so", () => {
  assert.equal(T.searchFaq(FAQ, "").length, 2);
  assert.equal(T.searchFaq(FAQ, "zzz").length, 0);
  assert.ok(T.LABELS.nothingFound.includes("Nothing matched"));
});

check("the words this page adds are the ones it says they are", () => {
  for (const key of ["heading", "next", "back", "skip", "quit", "again",
                     "resume", "restart", "search", "done", "skipped"]) {
    assert.equal(typeof T.LABELS[key], "string");
    assert.ok(T.LABELS[key].length > 1, `${key} is a word`);
  }
});

check("the sections and states here are the backend's own", () => {
  const py = readFileSync(join(REPO, "backend", "jarvis_tutorials.py"), "utf-8");
  for (const id of T.SECTION_ORDER) {
    assert.ok(new RegExp(`"${id}":`).test(py), `the backend names the ${id} section`);
  }
  for (const state of ["in_progress", "done", "skipped", "not_started"]) {
    assert.ok(py.includes(state), `the backend knows the state ${state}`);
  }
  for (const path of ["/api/tutorials", "/api/tutorials/progress", "/api/faq"]) {
    assert.ok(py.includes(`"${path}"`), `the backend serves ${path}`);
  }
});

check("the phone's own file, once it exists, says the same words", () => {
  const kt = join(REPO, "jarvis-client", "app", "src", "main", "java", "com", "jarvis",
    "client", "net", "Tutorials.kt");
  let text;
  try {
    text = readFileSync(kt, "utf-8");
  } catch {
    console.log("     (the phone's Tutorials.kt is not written yet: nothing to compare)");
    return;
  }
  for (const word of ["Tutorials", T.LABELS.next, T.LABELS.back, T.LABELS.skip]) {
    assert.ok(text.includes(`"${word}"`), `the phone says ${word}`);
  }
});

console.log(`\n${passed} checks passed`);
