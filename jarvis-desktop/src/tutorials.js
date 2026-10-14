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

// The desktop's OWN questions - the fifteen the Settings card "Help and FAQ"
// held until 2026-10-08, moved here so the one Help place answers them too
// (desktop-help.js says why in full). The backend still serves the questions
// both apps ask; `mergeQuestions` is what puts the two halves on one screen.
import { DESKTOP_FAQ, WORDS as HELP_WORDS, mergeQuestions } from "./desktop-help.js";

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
  // The button's own label is markup in brain.html (the CSP check counts the
  // static controls); this is only the line it says once the window is open.
  featuresOpened: "Opened.",
  stepOf: "Step",
  of: "of",
  done: "Done",
  due: "Not read yet",
  inProgress: "In progress",
  notStarted: "Not started",
  skipped: "Skipped",
  nothingFound: "Nothing matched that. Try a word from the question.",
  showMe: "Show me",
  pointed: "There it is.",
  otherWindow: "It is in another window",
  noPoint: "Nothing on this screen to point at for this step.",
};

/**
 * The real controls a tutorial may point at, by the name the catalogue uses
 * (`backend/jarvis_tutorials.py`'s per-step `point.desktop`).
 *
 * A tutorial POINTS; it never presses. The pointing below is a highlight and a
 * scroll - `pointAt` has no other verb available to it, and the suite in
 * `tests/tutorials.mjs` fails if one is ever added. That is not tidiness: this
 * app never approves anything by itself (rule 4), and a tutorial that can press
 * a button can approve.
 *
 * Two kinds, because the Brain panel can only reach its OWN document:
 *
 *   * `{ selector }` - a control in THIS window, which is `brain.html`. It is
 *     found, scrolled to and marked, so the owner sees the real thing rather
 *     than a picture of it.
 *   * `{ file, id, label }` - a control in a different window (the Jarvis bar,
 *     Settings, the HUD, the Faces window). No script here can highlight it, so
 *     the step says which window to open instead of pretending.
 *     `tests/tutorials.mjs` checks that the file really holds that id, so this
 *     cannot rot into a lie.
 *
 * `prompt-field` and `approval-card` were `{ selector }` entries until
 * 2026-10-10 and belonged to neither kind: the ids are in `index.html` - the
 * Jarvis bar's prompt field and its approval card - while this panel is drawn
 * in `brain.html` (`brain.js` calls `showTutorials($("tutorials-root"))` and
 * `id="tutorials-root"` is in brain.html). `pointAt` searched the Brain's own
 * document, found nothing, and said "Nothing on this screen to point at for
 * this step" - which is the honest answer, and exactly the wrong one. The
 * suite did not catch it because it concatenated the two documents before
 * looking; it does not any more. Two of the ten names were in that state, and
 * they are the two most-reached controls in the whole curriculum.
 *
 * The name is a registry key and never a raw selector, so the catalogue cannot
 * name a `div` that merely happens to exist, and a control that moves is fixed
 * in one place here.
 */
export const CONTROL_POINTS = {
  // This window - brain.html, which is where this panel is drawn.
  "brain-memory": { selector: "#view-memory" },
  "brain-tutorials": { selector: "#tutorials-root" },
  "brain-about": { selector: "#memory-about" },

  // Other windows - pointed at by naming the window, which is all that is
  // honest from here.
  "prompt-field": { file: "index.html", id: "prompt-field", label: "The Jarvis bar's own prompt field" },
  "approval-card": { file: "index.html", id: "approval", label: "The approval card in the Jarvis bar" },
  "hotkeys": { file: "settings.html", id: "hotkey-rows", label: "Settings → Hotkeys" },
  "asks-first": { file: "settings.html", id: "asks-first", label: "Settings → What asks first" },
  "faces": { file: "faces.html", id: "face-n", label: "The Faces window" },
  "hud-talk": { file: "jarvis_hud.html", id: "talk", label: "The HUD's own talk button" },
  "stop-everything": { file: "settings.html", id: "hotkey-rows", label: "Settings → Hotkeys → Stop everything" },
};

/** The two sections, in the order the backend sends them. */
export const SECTION_ORDER = ["pc", "phone"];

/**
 * `TRY_ACTIONS` - the actions a step may ask this app to NOTICE, which is the
 * `used` half of the design and is **designed and NOT BUILT**
 * (docs/TUTORIALS-DESIGN.md, "`try` and the `used` state - DESIGN ONLY").
 *
 * A step may carry `try` beside `point`, in the same per-app shape:
 *
 *   "try": {"desktop": "switch-model", "phone": null}
 *
 * `None` means "this app never shows this as a thing to do", exactly as it does
 * for `point`, and for the same reason: a step the app cannot observe must not
 * offer a control that never lights up.
 *
 * **NOTHING OBSERVES THESE YET.** No state is written, no `used` record can
 * exist, and neither app draws one - `tutorials.js` never reads this map. It is
 * a registry of NAMES, declared so that the catalogue cannot name an action no
 * app declares, and so that building the mechanism is a change to one file per
 * app rather than a rewrite of the curriculum. `tests/tutorials.mjs` holds the
 * catalogue to it, which is the whole point of it existing now.
 *
 * Each name is a verb phrase the app could recognise from something it already
 * does: switching the model, finishing the measurement, deciding a card. When
 * it is built, the observing code goes where the app already knows the thing
 * happened - nothing new listens to anything.
 */
export const TRY_ACTIONS = {
  "switch-model": "the model actually changed, confirmed by the PC's own answer",
  "measure-hardware": "a hardware measurement finished and was reported",
  "open-crash-notes": "the crash-notes list really drew a note",
  "finish-set-up": "the Set up Jarvis card was finished",
  "spending-summary": "a spending summary was really read back",
  "ask-home-status": "Home Assistant answered a status question",
  "open-memory": "the Memory tab was really opened",
  "open-work": "the Work tab was really opened",
  "pick-voice": "the spoken voice really changed",
  "ring-phone": "a paired phone really rang",
};

/**
 * Where the place key sends the Brain for this page - "Tutorials and the FAQ".
 *
 * Since 2026-10-08 this is also where Help goes: the palette's own Help row
 * (`entry.help`) and anything else that leaves `TUTORIALS_PLACE` under
 * `jarvis.brain.place` opens this tab rather than the Settings card "Help and
 * FAQ", which no longer exists. It is the view's own key in brain.js's `VIEWS`,
 * which is what lets the Brain open it the same way it opens History.
 */
export const TUTORIALS_PLACE = "tutorials";

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
 * "You have met 9 of the 23 lessons here. 14 to go." - the ONE number this page
 * is allowed to show, and it counts down.
 *
 * The backend has computed this since the route was written
 * (`jarvis_tutorials.py`'s `read()`: `counts.done`, `counts.due`,
 * `counts.total`) and NOTHING DREW IT - not this page, not the phone. This is
 * the drawing of it.
 *
 * Four decisions, and each of them is the design's (docs/EDUCATION-TAB-DESIGN.md
 * sections 5.2 and 5.3), not a preference:
 *
 *   * NOT a percentage, and not "X% complete". A percentage is the number that
 *     goes up fastest by clicking Next through the shortest lessons, and this
 *     project already refuses to count a row nobody reached as a pass
 *     (`CLAUDE.md`: BLOCKED and NOT-TESTABLE are never passes).
 *   * "met", not "done" or "learned". A lesson that was skipped was MET AND
 *     DECLINED - the backend keeps `skipped` and "never opened" apart, and a
 *     total that merged them would destroy the only distinction this page has.
 *     So `met` is every tutorial with a record of any kind.
 *   * The remainder is stated, not implied. "14 to go" is the honest half of
 *     the same sentence, and it is information rather than a nag: nothing here
 *     interrupts the owner about it (the design refuses a nudge outright).
 *   * It never says what he CAN DO. Only that he has looked. The stronger
 *     `used` state is designed and deliberately not built
 *     (docs/EDUCATION-TAB-DESIGN.md section 5.3) - this line must not imply it.
 *
 * The counts come from the PC, so the two apps can never disagree about them.
 * A backend too old to send `counts` gets no line at all rather than a made-up
 * one - an invented total is worse than no total.
 */
export function metWords(counts) {
  const total = Number(counts && counts.total);
  const due = Number(counts && counts.due);
  if (!Number.isFinite(total) || !Number.isFinite(due) || total <= 0) return "";
  const met = total - due;
  const toGo = total - met;
  const lessons = total === 1 ? "lesson" : "lessons";
  if (toGo <= 0) return `You have met all ${total} ${lessons} here.`;
  return `You have met ${met} of the ${total} ${lessons} here. ${toGo} to go.`;
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
//   The panel itself
// --------------------------------------------------------------------------

/** A node with a class and some text, the way brain.js builds everything. */
function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** The step's target for an app, or null. The catalogue sends both names. */
export function pointFor(step, app) {
  const point = (step && step.point) || null;
  const name = point && point[app];
  return typeof name === "string" && name.trim() ? name : null;
}

/** What this window can point at for a step: a registry name, or null. */
export function pointName(step) {
  const name = pointFor(step, "desktop");
  return name && Object.prototype.hasOwnProperty.call(CONTROL_POINTS, name) ? name : null;
}

/**
 * Point at the real control a step names, in THIS window. Returns words for the
 * owner, and never acts.
 *
 * This is the whole of "interactive" on the PC: the owner sees the control the
 * step means, in the app as it is right now, rather than a screenshot of how it
 * looked the day the picture was taken.
 *
 * Every entry that lives in another window is answered in words, because no
 * script here can reach across windows and pretending otherwise would be the
 * kind of small lie a tutorial cannot afford.
 */
export function pointAt(step, doc = document) {
  const name = pointFor(step, "desktop");
  const entry = name ? CONTROL_POINTS[name] : null;
  if (!entry) return LABELS.noPoint;
  if (entry.file) return `${LABELS.otherWindow}: ${entry.label}.`;

  const target = doc.querySelector(entry.selector);
  if (!target) return LABELS.noPoint;
  // Mark, then unmark: for as long as the owner is looking, and no longer.
  target.classList.add("tutorial-pointed");
  if (typeof target.scrollIntoView === "function") {
    target.scrollIntoView({ block: "center", inline: "nearest" });
  }
  globalThis.setTimeout(() => target.classList.remove("tutorial-pointed"), 2400);
  return LABELS.pointed;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|undefined|null|not found/i.test(said) || said.length > 300) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

/**
 * Draw the whole panel into `root`.
 *
 * Called by brain.js's view switch, the way showProjects() is. Everything is
 * built from the backend's own answers; nothing is held between openings, so a
 * tutorial finished on the phone shows as finished here the next time this is
 * drawn.
 */
export async function showTutorials(root) {
  root.textContent = "";
  const head = el("div", "panel-head");
  head.append(el("h2", null, LABELS.heading));
  root.append(head);
  const body = el("div", "tutorials-body");
  root.append(body);

  let catalogue;
  try {
    catalogue = await loadTutorials();
  } catch (error) {
    body.append(el("p", "problem", problemWords(error)));
    return;
  }
  if (catalogue && catalogue.available === false) {
    body.append(el("p", "problem", catalogue.why || "The tutorials are not on this PC yet."));
    return;
  }

  const columns = el("div", "tutorial-columns");
  // The one number this page shows, and it counts down (see `metWords`). Drawn
  // above the two lists, from the PC's own total for everything the page lists -
  // including the shared tutorials, which appear in both sections and are
  // therefore counted once.
  const met = metWords(catalogue.counts);
  if (met) body.append(el("p", "tutorial-met", met));
  for (const section of SECTION_ORDER) {
    const title = ((catalogue.sections || []).find((s) => s.id === section) || {}).title
      || section;
    const column = el("section", "tutorial-section");
    column.append(el("h3", null, title));
    const list = el("ul", "tutorial-list");
    for (const item of sectionList(catalogue, section)) {
      const row = el("li", "tutorial-row");
      const open = el("button", "tutorial-open");
      open.type = "button";
      open.append(el("strong", null, item.title));
      open.append(el("span", "tutorial-state", stateWords(item)));
      if (item.due && !item.done) open.append(el("span", "tutorial-due", LABELS.due));
      open.addEventListener("click", () => openTutorial(item, column));
      row.append(open);
      if (showsAgain(item)) {
        const again = el("button", "tutorial-again", LABELS.again);
        again.type = "button";
        again.addEventListener("click", async () => {
          try {
            await showAgain(item);
          } catch (error) {
            column.append(el("p", "problem", problemWords(error)));
            return;
          }
          showTutorials(root);
        });
        row.append(again);
      }
      list.append(row);
    }
    column.append(list);
    columns.append(column);
  }
  body.append(columns);

  const faqBox = el("section", "tutorial-faq");
  faqBox.append(el("h3", null, LABELS.faqHeading));
  // The shared questions come from the PC; the desktop's own fifteen come from
  // desktop-help.js and are drawn whether or not the PC answered. So a backend
  // that is down, or one older than /api/faq, still leaves the owner with the
  // half only this app can answer - rather than an empty help page. A failure
  // is still said out loud, above those fifteen.
  let questions = [];
  try {
    questions = mergeQuestions(await loadFaq());
  } catch (error) {
    faqBox.append(el("p", "problem", problemWords(error)));
    questions = mergeQuestions(null);
  }
  const search = el("input", "tutorial-search");
  search.type = "search";
  search.placeholder = LABELS.search;
  const answers = el("div", "tutorial-answers");
  // Where the desktop's own half begins, said plainly rather than left to be
  // guessed at from one question about the pairing token. It is appended by
  // `paint`, between the two halves, so a search that finds only shared answers
  // does not leave an "On this computer" heading over an empty list.
  const localHead = el("div", "tutorial-faq-local");
  localHead.append(el("h4", null, HELP_WORDS.heading));
  localHead.append(el("p", "note", HELP_WORDS.note));
  // The shared half is whatever the PC answered; the rest is this file's own.
  // Counted against the local length rather than assumed, so a backend that
  // answered nothing (or with fewer questions than the last build) still
  // splits the two halves in the right place.
  const localOnly = mergeQuestions(null).length;
  const sharedQuestions = questions.slice(0, questions.length - localOnly);
  const paint = (typed) => {
    answers.textContent = "";
    const draw = (list) => {
      for (const item of searchFaq(list, typed)) {
        const one = el("details", "tutorial-question");
        one.append(el("summary", null, item.q));
        one.append(el("p", null, item.a));
        if (item.where) one.append(el("p", "where", item.where));
        answers.append(one);
      }
    };
    const local = searchFaq(DESKTOP_FAQ, typed);
    const shared = searchFaq(sharedQuestions, typed);
    if (!local.length && !shared.length) {
      answers.append(el("p", "empty", LABELS.nothingFound));
      return;
    }
    const hasLocal = sharedQuestions.length > 0 && local.length > 0;
    draw(shared);
    if (hasLocal) answers.append(localHead);
    draw(local);
  };
  search.addEventListener("input", () => paint(search.value));
  faqBox.append(search, answers);
  paint("");
  body.append(faqBox);

  // "Everything Jarvis can do" (docs/FEATURES-LIST-DESIGN.md, the owner's
  // request of 2026-10-08): the whole feature set, opened from the one Help
  // place. This is PR #106's page, moved here on 2026-10-08 with the FAQ - the
  // button was NOT deleted with the Settings card, because the Brain is now the
  // only way in that is not the tray icon (tests/features.mjs holds that).
  mountFeaturesButton();
}

/**
 * The "Everything Jarvis can do" button, and the live line that says what
 * happened when it is pressed.
 *
 * The same three lines the Settings card used for the same command
 * (`open_features`, in the `features-open` permission set): the window it opens
 * reads one bundled list of text and draws it, there is nothing to wait for but
 * the window itself, and a refusal is said out loud rather than swallowed - the
 * failure mode this project has shipped before, where a button calls a command
 * the ACL does not grant and simply does nothing.
 *
 * Wired here, in the tab that draws the FAQ, rather than in brain.js: this is
 * the one Help place, and the button is part of it.
 */
function mountFeaturesButton() {
  const open = document.getElementById("open-features");
  const status = document.getElementById("features-status");
  if (!open || !status) return;
  open.addEventListener("click", async () => {
    status.textContent = "";
    try {
      await invoke("open_features");
      status.textContent = LABELS.featuresOpened;
    } catch (error) {
      status.textContent = problemWords(error);
    }
  });
}

/** One tutorial's step card, inside its own section column. */
function openTutorial(tutorial, column) {
  const card = column.querySelector(".tutorial-card");
  if (card) card.remove();
  const box = el("div", "tutorial-card");
  let index = startIndex(tutorial);
  let lastSaved = index;

  const paint = () => {
    box.textContent = "";
    const step = (tutorial.steps || [])[index] || {};
    box.append(el("p", "tutorial-step", stepWords(tutorial, index)));
    box.append(el("h4", null, step.title || ""));
    box.append(el("p", null, step.body || ""));
    if (step.where) box.append(el("p", "where", step.where));

    // "Show me" is the interactive part, and it is offered only when the
    // catalogue names a control this app actually declares. A step with no
    // target simply has no button, rather than a button that does nothing.
    if (pointName(step)) {
      const show = el("button", "tutorial-show", LABELS.showMe);
      show.type = "button";
      const said = el("span", "tutorial-show-said");
      show.addEventListener("click", () => {
        said.textContent = pointAt(step);
      });
      box.append(show);
      box.append(said);
    }

    const row = el("div", "tutorial-buttons");
    const back = el("button", null, LABELS.back);
    back.type = "button";
    back.disabled = backIndex(index) === null;
    back.addEventListener("click", () => {
      const at = backIndex(index);
      if (at !== null) {
        index = at;
        save(index);
      }
    });
    const next = el("button", "primary", LABELS.next);
    next.type = "button";
    const at = nextIndex(tutorial, index);
    next.addEventListener("click", () => {
      if (at === null) {
        save(index, "done");
        box.append(el("p", "done-words", LABELS.done));
        return;
      }
      index = at;
      save(index);
    });
    const skip = el("button", null, LABELS.skip);
    skip.type = "button";
    skip.addEventListener("click", () => {
      save(index, "skipped");
      box.append(el("p", "done-words", LABELS.skipped));
    });
    const quit = el("button", null, LABELS.quit);
    quit.type = "button";
    quit.addEventListener("click", () => {
      save(index);
      box.remove();
    });
    row.append(back, next, skip, quit);
    box.append(row);
  };

  /** Write where the owner is. A failure is shown, never swallowed. */
  const save = async (at, state = "in_progress") => {
    const opening = box.querySelector(".problem");
    if (opening) opening.remove();
    try {
      if (at !== lastSaved || state !== "in_progress") {
        await saveProgress(tutorial, at, state);
        lastSaved = at;
        tutorial.state = state;
        tutorial.resume_at = at;
      }
      paint();
    } catch (error) {
      box.append(el("p", "problem", problemWords(error)));
    }
  };

  paint();
  column.append(box);
  save(index);   // opening the card is itself a place in it
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
