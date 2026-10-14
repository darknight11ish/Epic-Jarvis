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

/**
 * The CATALOGUE literal of the real backend module, up to its own closing
 * bracket. The module's prose explains `point` and `try` with examples, and an
 * example is not a step - reading the whole file made an earlier version of
 * these checks fail on a docstring.
 */
function catalogueText() {
  const py = readFileSync(join(REPO, "backend", "jarvis_tutorials.py"), "utf-8");
  const start = py.indexOf("\nCATALOGUE = (");
  if (start <= 0) throw new Error("the catalogue is not where this check expects it");
  const end = py.indexOf("\n)\n", start);
  if (end <= start) throw new Error("the catalogue has no closing bracket");
  return py.slice(start, end);
}

/**
 * Every name the catalogue's `point` maps give one app, in file order.
 *
 * Read as `point` maps and not as loose `"desktop": "..."` matches: a step may
 * carry a `try` as well, whose names belong to a different registry
 * (`TRY_ACTIONS`). Conflating the two is the check being wrong about its own
 * subject, which is how this one was written the first time.
 */
function namesIn(field, app) {
  const pattern = new RegExp(
    `"${field}":\\s*\\{[^}]*?"${app}":\\s*(?:"([a-z0-9-]+)"|null)`, "g");
  return [...catalogueText().matchAll(pattern)].map((m) => m[1]).filter(Boolean);
}

function catalogueControls(app) {
  return namesIn("point", app);
}

/** The same, for the `try` maps - the not-yet-built half of the design. */
function catalogueTries(app) {
  return namesIn("try", app);
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

check("the one number this page shows counts down, and is never a percentage", () => {
  // The backend has computed `counts` since the route was written and nothing
  // drew it. This is the drawing: "met" (every lesson with any record, skipped
  // included - met and declined) out of the total, and the remainder said out
  // loud. The design refuses a percentage, a streak and a nudge, so the words
  // are asserted and the forbidden shapes are asserted absent.
  assert.equal(T.metWords({ done: 0, due: 23, total: 23 }),
    "You have met 0 of the 23 lessons here. 23 to go.");
  assert.equal(T.metWords({ done: 12, due: 14, total: 23 }),
    "You have met 9 of the 23 lessons here. 14 to go.");
  assert.equal(T.metWords({ done: 23, due: 0, total: 23 }),
    "You have met all 23 lessons here.");
  // A skipped lesson counts as MET, which is the whole reason `due` is the
  // input: the backend sets `due` false for a skipped one, so it is met.
  assert.match(T.metWords({ done: 0, due: 20, total: 23 }), /met 3 of the 23/);
  // One lesson is not "1 lessons".
  assert.equal(T.metWords({ done: 0, due: 1, total: 1 }), "You have met 0 of the 1 lesson here. 1 to go.");
  assert.equal(T.metWords({ done: 1, due: 0, total: 1 }), "You have met all 1 lesson here.");
  // A backend too old to send `counts` gets NO line, rather than a made-up one.
  for (const nothing of [undefined, null, {}, { total: 0, due: 0 }, { total: "x", due: 1 }]) {
    assert.equal(T.metWords(nothing), "", `a missing total invented a line: ${nothing && JSON.stringify(nothing)}`);
  }
  // And nothing in the sentence is a shape the design rejected.
  const said = T.metWords({ done: 1, due: 22, total: 23 });
  assert.ok(!said.includes("%"), "the line is a percentage");
  assert.ok(!/streak|badge|points|score/i.test(said), "the line scores the owner");
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

// ── Interactive steps: `point`, and the controls it is allowed to name ──────

check("every control the catalogue points at here is one this app declares", () => {
  // The catalogue names a registry KEY, never a selector, so the PC cannot be
  // asked to point at a `div` that merely happens to exist. Read from the real
  // file rather than a fixture: a step added to the catalogue with a name
  // nothing declares is the silent lie this check exists to catch.
  //
  // Only the `point` maps are read, not every `"desktop": "..."` in the
  // catalogue: each step now also carries an optional `try`, whose keys are a
  // DIFFERENT registry (TRY_ACTIONS, the not-yet-built `used` half of
  // docs/TUTORIALS-DESIGN.md). Reading the whole file made this check call them
  // point controls, which is the check being wrong about its own subject.
  const named = catalogueControls("desktop");
  assert.ok(named.length > 0, "the catalogue points at something on the PC");
  for (const name of named) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(T.CONTROL_POINTS, name),
      `src/tutorials.js declares the control \`${name}\``,
    );
  }
});

check("every action the catalogue asks this app to notice is one it declares", () => {
  // `try` is DESIGNED, NOT BUILT (docs/TUTORIALS-DESIGN.md). It is checked here
  // anyway, for the reason the `point` check above exists: a name written into
  // the catalogue that no app declares is drift, and drift written down once is
  // the kind that survives. Nothing observes these yet - the registry is the
  // list, and step 2 of that design is wiring it up.
  const named = catalogueTries("desktop");
  assert.ok(named.length > 0, "the lessons added on 2026-10-10 still carry their try actions");
  for (const name of named) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(T.TRY_ACTIONS, name),
      `src/tutorials.js declares the try action \`${name}\``,
    );
  }
});

check("a control in this window is a selector that really matches the markup", () => {
  // `{ selector }` entries are the ones the owner actually SEES highlighted, so
  // they are held to the markup itself. A selector that matches nothing is a
  // "Show me" button that does nothing.
  //
  // THE PANEL IS DRAWN IN ONE DOCUMENT, AND IT IS brain.html: brain.js calls
  // `showTutorials($("tutorials-root"))`, and `id="tutorials-root"` is in
  // brain.html. So this reads THAT file and no other. It used to concatenate
  // index.html and brain.html into one `markup` string and check the joined
  // text - which proved an id was in ONE OF THE TWO, and could not tell that it
  // was in the wrong one. Two entries (`prompt-field`, `approval-card`) were
  // declared "in this window" while their ids live in index.html, so `pointAt`
  // found nothing and said "Nothing on this screen to point at for this step".
  // Both are `{ file, id, label }` now, and this check can tell the documents
  // apart so they cannot come back.
  const brain = readFileSync(join(REPO, "jarvis-desktop", "src", "brain.html"), "utf-8");
  let pointed = 0;
  for (const [name, entry] of Object.entries(T.CONTROL_POINTS)) {
    if (!entry.selector) continue;
    pointed += 1;
    const id = entry.selector.replace(/^#/, "");
    assert.ok(
      brain.includes(`id="${id}"`),
      `\`${name}\` (${entry.selector}) says it is in the panel's own document, and brain.html has no id="${id}"`,
    );
  }
  assert.ok(pointed > 0, "at least one control is in this window, so Show me is not a word only");
});

check("a control in another window names that window and a real id in it", () => {
  // No script in the Brain panel can reach across Tauri windows, so these are
  // pointed at in words instead of a highlight that would never appear. Checked
  // against the file, so "it is in Settings" cannot rot into a lie.
  let crossWindow = 0;
  for (const [name, entry] of Object.entries(T.CONTROL_POINTS)) {
    if (!entry.file) continue;
    crossWindow += 1;
    const text = readFileSync(join(REPO, "jarvis-desktop", "src", entry.file), "utf-8");
    assert.ok(
      text.includes(`id="${entry.id}"`),
      `\`${name}\` says ${entry.file}, and ${entry.id} is in it`,
    );
    assert.ok(entry.label && entry.label.length > 3, `\`${name}\` says which window in words`);
  }
  assert.ok(crossWindow > 0, "some controls live in other windows and say so");
});

check("every point is one kind or the other, never neither", () => {
  for (const [name, entry] of Object.entries(T.CONTROL_POINTS)) {
    assert.ok(
      Boolean(entry.selector) !== Boolean(entry.file),
      `\`${name}\` is either a selector here or a window elsewhere, not both and not neither`,
    );
  }
});

check("a step with no target gets no button, rather than a button that does nothing", () => {
  assert.equal(T.pointName({ point: { desktop: null } }), null);
  assert.equal(T.pointName({}), null);
  assert.equal(T.pointName({ point: { desktop: "not-a-control" } }), null);
  assert.equal(T.pointName({ point: { desktop: "prompt-field" } }), "prompt-field");
  // A step only the phone has must not light up on the PC.
  assert.equal(T.pointName({ point: { desktop: null, phone: "talk-button" } }), null);
});

check("pointing at a control in this window marks it, and marks nothing else", () => {
  // `brain-memory` is one of the three that really are in the panel's own
  // document. The control a step points at is found by its own selector, so the
  // stub answers only that one.
  const marked = [];
  const fake = {
    querySelector: (sel) => (sel === "#view-memory" ? { classList: { add: (c) => marked.push(c), remove: () => {} }, scrollIntoView: () => {} } : null),
  };
  assert.equal(T.pointAt({ point: { desktop: "brain-memory" } }, fake), T.LABELS.pointed);
  assert.deepEqual(marked, ["tutorial-pointed"]);
});

check("a control in another window is answered in words, not faked", () => {
  const said = T.pointAt({ point: { desktop: "hotkeys" } }, { querySelector: () => null });
  assert.ok(said.includes(T.LABELS.otherWindow), said);
  assert.ok(said.includes("Settings"), said);
  // And the two that used to be declared "in this window" while their ids were
  // in the Jarvis bar's document: they name that window now instead of finding
  // nothing and saying so.
  const prompt = T.pointAt({ point: { desktop: "prompt-field" } }, { querySelector: () => null });
  assert.ok(prompt.includes(T.LABELS.otherWindow), prompt);
  assert.ok(prompt.includes("Jarvis bar"), prompt);
  const card = T.pointAt({ point: { desktop: "approval-card" } }, { querySelector: () => null });
  assert.ok(card.includes("approval card"), card);
});

check("pointing NEVER presses: the only verbs pointAt has are mark and scroll", () => {
  // This is rule 4 in the small: the app never approves anything by itself, and
  // a tutorial that can press a button can approve. The check is on the source
  // of `pointAt` alone, so it fails the day someone adds `.click()` to it.
  const src = readFileSync(join(REPO, "jarvis-desktop", "src", "tutorials.js"), "utf-8");
  const start = src.indexOf("export function pointAt(");
  assert.ok(start > 0, "pointAt is still there");
  const end = src.indexOf("\n}", start);
  const body = src.slice(start, end);
  for (const forbidden of [".click(", "dispatchEvent", ".submit(", ".focus(", ".value ="]) {
    assert.ok(!body.includes(forbidden), `pointAt does not ${forbidden}`);
  }
  for (const allowed of ["querySelector", "classList", "scrollIntoView"]) {
    assert.ok(body.includes(allowed), `pointAt only marks and scrolls (${allowed})`);
  }
});

check("no phone-only control is declared on the PC", () => {
  // The two registries may agree where the two apps mean the same thing (both
  // have an approval card, both have a talk button). What must never happen is
  // a control only the PHONE has turning up here: a desktop tutorial telling
  // the owner to tap a card, swipe it, or open Quick Settings is the same
  // failure in the other direction. The phone's half of this pair is in
  // jarvis-client's TutorialsTest.kt.
  const phoneOnly = ["pairing", "notifications", "live-tile", "phone-pc-only"];
  for (const name of phoneOnly) {
    assert.ok(
      !Object.prototype.hasOwnProperty.call(T.CONTROL_POINTS, name),
      `the PC must not declare the phone-only control \`${name}\``,
    );
  }
});

check("the labels for pointing are the ones this page adds", () => {
  for (const key of ["showMe", "pointed", "otherWindow", "noPoint"]) {
    assert.equal(typeof T.LABELS[key], "string");
    assert.ok(T.LABELS[key].length > 2, `${key} is a word`);
  }
});

console.log(`\n${passed} checks passed`);
