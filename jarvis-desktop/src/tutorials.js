/**
 * Brain -> Tutorials and the FAQ (JARVIS-API section 114,
 * backend/jarvis_tutorials.py): one catalogue for both apps, and the owner's
 * reading progress kept on the PC.
 *
 * QUIT AND RESUME. Every step the owner moves through is written back as
 * `{id, state, step}`, so closing this page at step 3 and coming back offers
 * "Continue at step 3" instead of starting again. Nothing here asks for an
 * approval card: this is the owner marking their own reading, and a card per
 * "Next" would be absurd.
 *
 * SKIPPABLE, AND REVERSIBLE. The intro can be dismissed from its own card, a
 * tutorial can be left mid-way, and "Show this one again" clears the record.
 * A tutorial whose steps changed comes back on its own (`due`).
 *
 * The steps say WHERE the thing is in words ("Brain -> Memory") rather than
 * only showing a picture, because the words still work when the screen has
 * moved on. Pictures are optional and named by the catalogue.
 *
 * The labels here are the phone's (net/Tutorials.kt) word for word; both are
 * checked against the backend's own catalogue by backend/test_tutorials.py.
 *
 * @module tutorials
 */

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/** The words this page adds. The phone's Tutorials.kt has the same ones. */
export const LABELS = {
  heading: "Tutorials",
  introOffer: "New here? Start with what Jarvis is",
  faqHeading: "Questions and answers",
  next: "Next",
  back: "Back",
  skip: "Skip this one",
  quit: "Leave it here",
  again: "Show this one again",
  resume: "Continue at step",
  restart: "Start again",
  search: "Search the answers",
  stepOf: "Step",
  of: "of",
  done: "Done",
  inProgress: "In progress",
  notStarted: "Not started",
  skipped: "Skipped",
  nothingFound: "Nothing matched that. Try a word from the question.",
};

/** The two sections, in the order the backend sends them. */
export const SECTION_ORDER = ["pc", "phone"];

/**
 * The tutorials of one section, plus the shared ones.
 *
 * A tutorial with `section: "both"` belongs in each app's own list, which is
 * what "the same tutorials on both apps" means: the catalogue is shared, the
 * sections are not.
 */
export function sectionList(catalogue, section) {
  const all = (catalogue && catalogue.tutorials) || [];
  return all.filter((t) => t.section === section || t.section === "both");
}

/** "Step 3 of 5", or the last step when there are no more. */
export function stepWords(tutorial, index) {
  const total = (tutorial && tutorial.steps_total) || 0;
  const at = Math.min(Math.max(index, 0), Math.max(total - 1, 0)) + 1;
  return `${LABELS.stepOf} ${at} ${LABELS.of} ${total}`;
}

/**
 * Where "Next" goes: the next step, or null when this is the last one - at
 * which point the tutorial is finished rather than "nexted" past its end.
 */
export function nextIndex(tutorial, index) {
  const total = (tutorial && tutorial.steps_total) || 0;
  return index + 1 < total ? index + 1 : null;
}

/** Where "Back" goes: null on the first step. */
export function backIndex(index) {
  return index > 0 ? index - 1 : null;
}

/**
 * Where opening this tutorial should put the owner: the recorded step when
 * they were part-way through, otherwise the first step.
 */
export function startIndex(tutorial) {
  const at = tutorial && tutorial.resume_at;
  if (typeof at === "number" && at > 0 && at < (tutorial.steps_total || 0)) return at;
  return 0;
}

/** The one line a row shows about the owner's place in it. */
export function stateWords(tutorial) {
  if (!tutorial) return LABELS.notStarted;
  if (tutorial.done) return LABELS.done;
  if (tutorial.state === "in_progress" && tutorial.resume_at) {
    return `${LABELS.resume} ${tutorial.resume_at + 1}`;
  }
  if (tutorial.state === "skipped") return LABELS.skipped;
  if (tutorial.state === "in_progress") return LABELS.inProgress;
  return LABELS.notStarted;
}

/** The button a finished or skipped tutorial shows instead of starting over. */
export function showsAgain(tutorial) {
  return Boolean(tutorial && (tutorial.done || tutorial.state === "skipped"));
}

/**
 * The FAQ, filtered by what the owner typed. Matching is case-insensitive and
 * looks in the question AND the answer, because half the time the owner
 * remembers a word from the answer.
 */
export function searchFaq(questions, typed) {
  const list = questions || [];
  const needle = String(typed || "").trim().toLowerCase();
  if (!needle) return list.slice();
  return list.filter((q) => `${q.q} ${q.a} ${q.where || ""}`.toLowerCase().includes(needle));
}

/** What to send when a step is reached. Pure, so a test can read it. */
export function progressBody(tutorial, index, state = "in_progress") {
  return { id: tutorial.id, state, step: index };
}

// --------------------------------------------------------------------------
//   Talking to the PC
// --------------------------------------------------------------------------

async function invoke(name, args) {
  if (!IS_TAURI) throw new Error("This page is only on the PC app.");
  return TAURI.core.invoke(name, args);
}

export async function loadTutorials(section) {
  return invoke("get_tutorials", section ? { section } : {});
}

export async function loadFaq() {
  return invoke("get_faq", {});
}

/** Record where the owner is. Failure is reported, never silent. */
export async function saveProgress(tutorial, index, state = "in_progress") {
  return invoke("mark_tutorial", progressBody(tutorial, index, state));
}

/** "Show this one again": the record is removed, not merely re-marked. */
export async function showAgain(tutorial) {
  return invoke("mark_tutorial", { id: tutorial.id, state: "not_started", step: 0 });
}
