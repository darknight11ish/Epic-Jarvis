/**
 * "Coach this" - the prompt coach in the Jarvis bar, and the panel its
 * critique opens (the owner's request of 2026-10-08 and their answers the same
 * day; docs/PROMPT-COACH-DESIGN.md; backend jarvis_prompt_coach.py,
 * JARVIS-API.md section 119; src-tauri/src/prompt_coach.rs).
 *
 * The switch lives in Settings (`prompt-coach-settings.js`). This file is the
 * feature itself, and it is deliberately the bar's own: the button sits above
 * the box where the owner types (src/index.html, inside `.field`), and the
 * panel hangs under the bar. Neither file knows the other's DOM.
 *
 * What it does, in plain words:
 *
 *  - **Off by default, and when it is off there is NO button at all.** The one
 *    read (`get_prompt_coach`, the PC's own answer) decides it. A PC with no
 *    such route (`MISSING`) or a read that failed also shows nothing - never a
 *    button that cannot work. The read is repeated when the window is focused
 *    and when it becomes visible again, the same as the Settings card's own.
 *
 *  - **"Coach this" sends the words in the box, plus the last few turns.** The
 *    history is at most [`HISTORY_TURNS`] entries of
 *    `{"who": "owner"|"jarvis", "text": "..."}` - pronouns get an antecedent
 *    and no more (the PC caps it again at its own MAX_TURNS). Nothing is sent
 *    anywhere else: one call to the owner's own PC.
 *
 *  - **The panel shows, in order: the score out of 10, what is missing and why
 *    it matters and the smallest fix for each, the questions it would have to
 *    ask, and the rewritten prompt IN FULL.** Nothing is truncated, no part is
 *    behind a "more" button, and nothing is summarised by this side: the words
 *    on screen are the model's.
 *
 *  - **A 1 out of 10 is not a gate.** The score is shown and nothing else
 *    happens because of it: both buttons stay live at 1 and at 10.
 *
 *  - **Nothing is ever sent except by one of the two buttons.** "Send mine"
 *    hands back exactly what the owner typed, unchanged. "Send the suggestion"
 *    puts the rewritten prompt in the box and sends that. Closing the panel,
 *    pressing "Coach this" again, or reading a critique sends nothing at all.
 *
 *  - **A refusal shows the PC's own sentence.** A 409 ("The prompt coach is
 *    switched off.", "That is too short to coach - write a little more and
 *    try again.", "The model on this PC did not answer, ...") is shown as it
 *    came, word for word, and never as a generic failure and never as an empty
 *    panel.
 *
 * The words it shows are the PC's - BUTTON / SEND_MINE / SEND_SUGGESTION /
 * MISSING come from `prompt-coach-settings.js`, which holds byte-identical
 * copies of jarvis_prompt_coach.py's constants. Only the panel's own furniture
 * (the headings over each part) is written here.
 *
 * @module prompt-coach-panel
 */

import { BUTTON, MISSING, SEND_MINE, SEND_SUGGESTION, readPromptCoach } from "./prompt-coach-settings.js";

/**
 * How many earlier turns the coach is given. The owner's answer of 2026-10-08
 * was "the last few turns, so pronouns have an antecedent, and no more"; the
 * PC's own `MAX_TURNS` is 6, and this is the client's half of the same cap.
 */
export const HISTORY_TURNS = 6;

/** The headings over each part of the panel. Ours, not the PC's. */
export const WORDS = Object.freeze({
  score: "Score",
  scoreOf: "out of 10",
  issues: "What is missing",
  why: "Why it matters",
  fix: "Smallest fix",
  questions: "It would have to ask you",
  suggestion: "The rewritten prompt",
  sendMine: SEND_MINE,
  sendSuggestion: SEND_SUGGESTION,
  button: BUTTON,
  missing: MISSING,
  coaching: "Reading your question…",
  close: "Close",
  /** Nothing in the box, so there is nothing to coach. The PC would say "That
   *  is too short to coach - write a little more and try again." after a model
   *  round trip; this says it without the round trip. */
  nothing:
    "There is nothing in the box to coach - write your question first, then press Coach this.",
  /** Shown when a read or a critique failed in a way the PC did not put into
   *  words - a bridge error or JSON is never shown to the owner. */
  trouble: "Try again in a moment, or restart Jarvis Desktop.",
});

/** A non-empty string field of the PC's answer, or "". */
function words(v) {
  return typeof v === "string" && v.trim() ? v.trim() : "";
}

/**
 * The critique inside `coach_prompt`'s answer, read. Returns null for a body
 * that carries no usable critique - the caller shows the PC's own sentence
 * instead, never an empty panel.
 *
 * Every list is capped for the screen the way the PC already caps it (four
 * gaps, four questions), but a `suggestion` is NEVER trimmed: the rewritten
 * prompt is shown in full, because a half-shown rewrite is worse than none.
 */
export function readCritique(answer) {
  const box = answer && typeof answer === "object" ? answer.coach : null;
  if (!box || typeof box !== "object") return null;
  const score = box.score;
  if (typeof score !== "number" || !Number.isFinite(score)) return null;
  const rawIssues = Array.isArray(box.issues) ? box.issues : [];
  const issues = [];
  for (const item of rawIssues) {
    if (!item || typeof item !== "object") continue;
    const what = words(item.what);
    if (!what) continue;
    issues.push({ what, why: words(item.why), fix: words(item.fix) });
    if (issues.length >= 4) break;
  }
  const rawMissing = Array.isArray(box.missing) ? box.missing : [];
  const missing = [];
  for (const q of rawMissing) {
    const line = words(q);
    if (line) missing.push(line);
    if (missing.length >= 4) break;
  }
  return {
    // Clamped to the range the PC's own schema declares (1-10); a model that
    // answered 0 or 12 is shown as the nearest real score rather than as
    // "0 out of 10", which the PC would never have said.
    score: Math.max(1, Math.min(10, Math.round(score))),
    clear: box.clear === true && issues.length === 0,
    issues,
    missing,
    suggestion: typeof box.suggestion === "string" ? box.suggestion : "",
  };
}

/**
 * The last few turns as `{"who", "text"}` - what the coach is told about the
 * conversation so "it" and "that file" have something to point at.
 *
 * `turns` is the bar's own `state.thread`: `{ question, answer }` pairs, oldest
 * first (chat-history.js). A pair contributes its answer first and then its
 * question, and the whole list is cut to the NEWEST [`HISTORY_TURNS`] entries -
 * the same "the last few turns" the PC's `_turns` keeps. An answer that is
 * still streaming is not in `thread` and so is never handed over half-written.
 */
export function historyFor(turns, cap = HISTORY_TURNS) {
  const out = [];
  const pairs = Array.isArray(turns) ? turns : [];
  for (const pair of pairs) {
    if (!pair || typeof pair !== "object") continue;
    const answer = words(pair.answer);
    const question = words(pair.question);
    if (answer) out.push({ who: "jarvis", text: answer });
    if (question) out.push({ who: "owner", text: question });
  }
  return out.slice(-cap);
}

/** An error in words, never a bridge error or JSON - the same rule the
 *  Settings card's own `problemWords` follows. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return WORDS.trouble;
  }
  return said;
}

/** One labelled block of the panel, with the box its lines go into. */
function block(doc, className, heading) {
  const box = doc.createElement("div");
  box.className = className;
  if (heading) {
    const title = doc.createElement("p");
    title.className = "coach-heading";
    title.textContent = heading;
    box.append(title);
  }
  const lines = doc.createElement("div");
  lines.className = "coach-lines";
  box.append(lines);
  box.lines = lines;
  return box;
}

/**
 * Mounts the bar's half of the prompt coach into `box` (the panel) and puts the
 * button into `buttonHost` (the `.field`, above the box the owner types in).
 *
 * Everything that touches the rest of the bar is handed in, so this module
 * never reaches into main.js's state:
 *
 *  - `invoke(command, args)` - the strict Tauri call (main.js `invokeStrict`);
 *  - `boxText()` - the words currently in the box;
 *  - `history()` - the last few turns, as `state.thread`;
 *  - `sendMine(text)` - send the owner's own words, UNCHANGED;
 *  - `sendSuggestion(text)` - ask the bar to put the rewritten prompt in the
 *    box and send it (main.js owns the box's tag and its own bookkeeping);
 *  - `announce(text)` - speak to a screen reader;
 *  - `onChange()` - let the window fit its height (main.js `syncWindowHeight`).
 *
 * Returns `{ refresh, coach, close, view, button }`.
 */
export function mountPromptCoach(buttonHost, box, {
  invoke,
  boxText = () => "",
  history = () => [],
  sendMine = async () => {},
  sendSuggestion = async () => {},
  announce = () => {},
  onChange = () => {},
  doc = globalThis.document,
} = {}) {
  const button = doc.createElement("button");
  button.type = "button";
  button.id = "coach-this";
  button.className = "text-button coach-this";
  button.hidden = true;
  // The PC's own name for it, from the read; this is only what shows until the
  // first answer arrives (and it is hidden until then anyway).
  button.textContent = BUTTON;
  // PREPENDED, not appended: `.field` is a flex COLUMN, and appending would
  // put the button UNDER the box the owner types in - the one place it must
  // not be. Prepending makes it the first row of the column, above the box.
  if (buttonHost) {
    if (typeof buttonHost.prepend === "function") buttonHost.prepend(button);
    else buttonHost.append(button);
  }

  const score = doc.createElement("p");
  score.className = "coach-score";
  const issues = block(doc, "coach-issues", WORDS.issues);
  const questions = block(doc, "coach-missing", WORDS.questions);
  const suggestion = block(doc, "coach-suggestion", WORDS.suggestion);
  const note = doc.createElement("p");
  note.className = "coach-note";
  note.setAttribute("role", "status");
  const actions = doc.createElement("div");
  actions.className = "coach-actions";
  const mine = doc.createElement("button");
  mine.type = "button";
  mine.className = "text-button coach-send-mine";
  mine.textContent = SEND_MINE;
  const send = doc.createElement("button");
  send.type = "button";
  send.className = "text-button coach-send-suggestion";
  send.textContent = SEND_SUGGESTION;
  const closeButton = doc.createElement("button");
  closeButton.type = "button";
  closeButton.className = "text-button coach-close";
  closeButton.textContent = WORDS.close;
  actions.append(mine, send, closeButton);
  box.append(score, issues, questions, suggestion, note, actions);
  box.setAttribute("aria-label", BUTTON);
  box.hidden = true;

  // The setting as last read: null until the PC has answered. `available`
  // false is a PC with no such route - no button.
  let view = null;
  let held = null;      // { critique } - the answer on screen
  let why = "";         // the PC's own sentence, when it refused
  let busy = false;

  function on() {
    return Boolean(view && view.available && view.on);
  }

  /** The button exists only when the coach is on (the owner's rule: off, and
   *  there is no button at all). */
  function paintButton() {
    const show = on();
    if (button.hidden === !show) return;
    button.hidden = !show;
    if (!show) wipe();
    onChange();
  }

  function syncBusy() {
    button.disabled = busy;
    const live = !busy && Boolean(held || why);
    mine.disabled = !live;
    // "Send the suggestion" needs one: a critique that rewrote nothing has
    // nothing to put in the box.
    send.disabled = !live || !(held && held.critique.suggestion);
  }

  function paint() {
    paintButton();
    const open = Boolean(held || why);
    box.hidden = !open;
    if (!open) {
      onChange();
      return;
    }
    score.hidden = true;
    issues.hidden = true;
    questions.hidden = true;
    suggestion.hidden = true;
    issues.lines.replaceChildren();
    questions.lines.replaceChildren();
    suggestion.lines.replaceChildren();
    if (why) {
      // The PC's own sentence - the coach is off, the question was too short,
      // or the model did not answer. Never a generic failure, never blank.
      note.textContent = why;
      note.dataset.tone = "bad";
    } else {
      const c = held.critique;
      score.hidden = false;
      score.textContent = `${WORDS.score}: ${c.score} ${WORDS.scoreOf}`;
      if (c.issues.length) {
        issues.hidden = false;
        for (const issue of c.issues) {
          const row = doc.createElement("div");
          row.className = "coach-issue";
          const what = doc.createElement("p");
          what.className = "coach-what";
          what.textContent = issue.what;
          row.append(what);
          if (issue.why) {
            const whyLine = doc.createElement("p");
            whyLine.className = "coach-why";
            whyLine.textContent = `${WORDS.why}: ${issue.why}`;
            row.append(whyLine);
          }
          if (issue.fix) {
            const fix = doc.createElement("p");
            fix.className = "coach-fix";
            fix.textContent = `${WORDS.fix}: ${issue.fix}`;
            row.append(fix);
          }
          issues.lines.append(row);
        }
      }
      if (c.missing.length) {
        questions.hidden = false;
        for (const q of c.missing) {
          const line = doc.createElement("p");
          line.className = "coach-question";
          line.textContent = q;
          questions.lines.append(line);
        }
      }
      if (c.suggestion) {
        suggestion.hidden = false;
        const text = doc.createElement("p");
        text.className = "coach-suggestion-text";
        // In full: never trimmed, never a preview.
        text.textContent = c.suggestion;
        suggestion.lines.append(text);
      }
      note.textContent = "";
      if (note.dataset) delete note.dataset.tone;
    }
    syncBusy();
    onChange();
  }

  /** Empties the panel without touching the wiring, so closing and reopening
   *  it never loses a listener. */
  function wipe() {
    held = null;
    why = "";
    score.hidden = true;
    issues.hidden = true;
    questions.hidden = true;
    suggestion.hidden = true;
    issues.lines.replaceChildren();
    questions.lines.replaceChildren();
    suggestion.lines.replaceChildren();
    note.textContent = "";
    if (note.dataset) delete note.dataset.tone;
    box.hidden = true;
    syncBusy();
  }

  /** Reads the switch again. A failed read leaves the button as it was (and
   *  hidden if it has never been shown): a button that cannot work is never
   *  drawn. */
  async function refresh() {
    try {
      view = readPromptCoach(await invoke("get_prompt_coach"));
    } catch {
      return;
    }
    // The PC's own line for a PC without the route, kept on the button so the
    // reason is there to read rather than the button simply not existing.
    button.title = view.available ? "" : view.why || MISSING;
    paintButton();
  }

  /** Pressing "Coach this". Nothing is sent: this asks the PC's own model for
   *  a critique of the words in the box. */
  async function coach() {
    if (busy || !on()) return;
    const text = String(boxText() || "");
    if (!text.trim()) {
      held = null;
      why = WORDS.nothing;
      paint();
      return;
    }
    busy = true;
    held = null;
    why = "";
    paint();
    note.textContent = WORDS.coaching;
    try {
      const answer = await invoke("coach_prompt", { text, history: history() });
      const critique = readCritique(answer);
      if (critique) {
        held = { critique };
        why = "";
      } else {
        // A body with no critique this side can read. The PC's own sentence
        // where it sent one, our plain line otherwise - never an empty panel.
        why = words(answer && answer.error) || WORDS.trouble;
        held = null;
      }
    } catch (error) {
      // A 409 is the PC's own sentence (the coach is off, too short, the model
      // did not answer); anything else is said plainly. Both are shown as they
      // came.
      why = problemWords(error);
      held = null;
    } finally {
      busy = false;
    }
    paint();
    announce(held ? `${WORDS.score}: ${held.critique.score} ${WORDS.scoreOf}.` : why);
  }

  function close() {
    busy = false;
    wipe();
    onChange();
  }

  mine.addEventListener("click", async () => {
    if (busy || mine.disabled) return;
    busy = true;
    syncBusy();
    try {
      await sendMine(String(boxText() || ""));
      close();
    } catch (error) {
      why = problemWords(error);
      held = null;
      busy = false;
      paint();
    }
  });

  send.addEventListener("click", async () => {
    if (busy || send.disabled || !held) return;
    const text = held.critique.suggestion;
    busy = true;
    syncBusy();
    try {
      await sendSuggestion(text);
      close();
    } catch (error) {
      why = problemWords(error);
      held = null;
      busy = false;
      paint();
    }
  });

  button.addEventListener("click", coach);
  closeButton.addEventListener("click", close);

  // The switch can be turned on or off in Settings while this window is open.
  // The bar re-reads when it is shown again, like the Settings card does.
  if (globalThis.document) {
    globalThis.document.addEventListener("visibilitychange", () => {
      if (!globalThis.document.hidden) refresh();
    });
  }
  globalThis.addEventListener?.("focus", () => refresh());

  refresh();

  return {
    refresh,
    coach,
    close,
    /** For the tests: the panel and the button as drawn now. */
    view() {
      return {
        visible: !box.hidden,
        buttonHidden: button.hidden,
        buttonDisabled: button.disabled,
        buttonTitle: button.title,
        score: box.hidden || score.hidden ? null : score.textContent,
        note: note.textContent,
        issues: issues.hidden ? null : issues.lines.children,
        questions: questions.hidden ? null : questions.lines.children,
        suggestion: suggestion.hidden ? null : suggestion.lines.children[0]?.textContent,
        mineDisabled: mine.disabled,
        suggestDisabled: send.disabled,
        sendMineWords: mine.textContent,
        sendSuggestionWords: send.textContent,
      };
    },
    button,
  };
}
