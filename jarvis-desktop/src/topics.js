/**
 * Topic controls (the owner's request of 2026-09-30, "adjust the brain of
 * Jarvis to include or exclude different topics"; docs/TOPIC-CONTROLS-DESIGN.md,
 * "Slice contract (frozen)"; JARVIS-API.md section 107; backend jarvis_topics.py;
 * src-tauri/src/brain/topics.rs).
 *
 * Every saved fact sits under one topic, and each topic has a mode: learn and
 * use, use but do not learn, learn but do not use, or off. The PC enforces the
 * modes and decides which changes need an approval card; this module holds the
 * shared words (word for word as the phone uses them, held to
 * tests/fixtures/topics-cases.json), the reading of what the PC sends, and the
 * small pure rules the Brain draws from. brain.js draws them.
 *
 * Nothing here is stored. Topic names are the owner's words: not in
 * localStorage, not as a draft, and only ever put on the page as text.
 *
 * @module topics
 */

import { COLOURS, ICON_PATHS, ICONS as TAG_ICONS } from "./history-tags.js";

/* ── The shared words (contract C6; the fixture's `words`) ─────────────── */

export const WORDS = Object.freeze({
  title: "Topics",
  intro: "A topic is a folder for things Jarvis knows. Pick what Jarvis may do with each folder.",
  sorted_guess:
    "Jarvis sorted {n} of your {total} facts by guessing from the words. Check them so switching a topic off works as you expect.",
  sorted_guess_one:
    "Jarvis sorted 1 fact by guessing from the words. Check it so switching a topic off works as you expect.",
  check_button: "Check these ({n})",
  check_right: "These are right",
  check_held: "Held back: might be about {name}",
  check_guessed: "Jarvis guessed",
  add_button: "Add a topic",
  private_tag: "Private",
  private_asks: "This will ask for your OK first.",
  unsorted_name: "Unsorted",
  kept_hidden: "{n} facts kept, hidden",
  kept_hidden_one: "1 fact kept, hidden",
  show_them: "Show them",
  not_used_tag: "not used in answers",
  skipped: "{n} new things not saved this week",
  skipped_one: "1 new thing not saved this week",
  left_out: "Left out {n} facts because of your topic settings",
  left_out_one: "Left out 1 fact because of your topic settings",
  preview_left_out: "{n} things Jarvis knows about {name} will be left out of answers.",
  preview_left_out_one: "1 thing Jarvis knows about {name} will be left out of answers.",
  preview_none: "Nothing Jarvis knows about {name} will change in answers.",
  preview_stop_learning: "Jarvis will stop saving new things about {name}.",
  preview_pinned: "{n} pinned facts about {name} will pause until you switch it back on.",
  preview_pinned_one: "1 pinned fact about {name} will pause until you switch it back on.",
  help_plain:
    "Topic names and facts are stored in the same plain file on this PC. Jarvis's sorting is a guess from the words, in English only; check it.",
  model_help: "Let Jarvis's local model help sort",
  model_help_note:
    "Uses the model on this PC, never a cloud one, on up to 20 facts a night. It only suggests; you check.",
  confirm_delete: "Delete this topic? Its facts are kept; pick where they go.",
  screen_reader: "{name}, {n} facts, {mode}, button: change mode",
  screen_reader_one: "{name}, 1 fact, {mode}, button: change mode",
  hidden_row: "Topic {index}, {n} facts, {mode}",
  hidden_row_one: "Topic {index}, 1 fact, {mode}",
  moved_line: "Done: {name} is {mode}. You can change it in Brain.",
  pick_line: "Pick what Jarvis may do with {name}.",
  no_such_topic: "I do not have a topic called {name}.",
  topics_are: "Your topics are: {names}.",
  outside:
    "I do not change your topics after I have read outside text, like an email or a web page. Use Brain, then Memory, then Topics.",
  missing: "Your PC's Jarvis does not have topic controls yet - run apply-patches.ps1 on the PC.",
  waiting: "Waiting for your approval.",
  sorting_now: "Jarvis is still sorting {n} of your facts.",
  pin_paused: "Paused: {name} is off",
  pin_paused_learn: "Paused: {name} is set to Learn, but don't use",
  used_left_out: "A memory from a topic you have since switched off.",
  ask_save: "Save under Unsorted",
  ask_skip: "Skip it",
  add_title: "Add a topic",
  name_label: "Name",
  words_label: "Keywords (optional)",
  words_pc_only: "Keywords are set on your PC.",
  delete_where: "Where should its facts go?",
  delete_looser:
    "That home is more open than {name}: Jarvis may learn about or use these facts more than it does now.",
});

/** The four modes, in the picker's order (contract C6). */
export const MODES = Object.freeze([
  { id: "both", name: "Learn and use", sentence: "Jarvis remembers new things about this and uses them in answers." },
  { id: "use_only", name: "Use, but don't learn", sentence: "Jarvis keeps what it knows and uses it, but saves nothing new." },
  { id: "learn_only", name: "Learn, but don't use", sentence: "Jarvis keeps learning quietly, but leaves this out of its answers." },
  {
    id: "off",
    name: "Off",
    sentence:
      "Jarvis neither learns nor uses this. What it knows is kept, not deleted, and comes back when you switch it on.",
  },
]);

/** The PC's sentence for each error code (also what `message` carries). */
export const ERRORS = Object.freeze({
  bad_request: "Jarvis could not understand that request.",
  bad_name: "A topic needs a name of 1 to 24 letters or numbers.",
  name_taken: "You already have a topic with that name.",
  too_many_topics: "You can have up to 16 topics of your own. Delete one first.",
  bad_colour: "That colour is not one of the eight to pick from.",
  bad_icon: "That picture is not one of the ones to pick from.",
  bad_words: "Keywords are short words or phrases, up to 20 of them.",
  topic_not_found: "That topic is not there any more.",
  bad_mode: "That is not one of the four choices.",
  no_delete_unsorted: "Unsorted cannot be deleted.",
  no_rename_unsorted: "Unsorted cannot be renamed.",
  needs_destination: "Pick a topic for its facts to move to first.",
  bad_destination: "Pick a different topic for its facts to move to.",
  no_such_fact: "One of those facts is not there any more.",
  unavailable: "Topics are not available on this PC yet.",
});

/** How the newest card ended (the fixture's `last_words`). */
export const LAST_WORDS = Object.freeze({
  applied: "You approved the card, so the change was made.",
  denied: "The card was turned down, so nothing about your topics changed.",
  timed_out: "Nobody answered the card in time, so nothing about your topics changed.",
  refused: "Your PC's settings do not let this be approved, so nothing changed.",
  withdrawn: "You changed this again while the card waited, so approving it changed nothing.",
  failed: "It was approved, but the change could not be saved, so nothing changed.",
});

/** Words of the app's own (not in the fixture; the contract says "app wording"). */
export const APP_WORDS = Object.freeze({
  hidden_from_answers: "Hidden from answers",
  nothing_to_check: "Nothing to check.",
  next_ten: "Show the next ten",
  file_under: "File under…",
  file_under_label: "File this fact under",
  change: "Change",
  cancel: "Cancel",
  save: "Save",
  delete: "Delete",
  edit: "Edit",
  undo: "Undo",
  rename: "Rename",
  colour_icon: "Colour and icon",
  keywords: "Keywords",
  move_up: "Move up",
  move_down: "Move down",
  mark_private: "Mark private",
  not_private: "Not private",
  colour_label: "Colour",
  icon_label: "Icon",
  hidden_note: "Names are hidden until Windows Hello confirms it is you. You can still change a mode.",
  at_limit: "You have 16 topics of your own. Delete one to add another.",
  reading: "Reading…",
  more_options: "More",
  no_facts: "Nothing is filed under this topic.",
  facts_word: (n) => `${n} ${n === 1 ? "fact" : "facts"}`,
});

export const LIMITS = Object.freeze({
  maxTopics: 16,
  nameMax: 24,
  wordsMax: 20,
  batch: 10,
  colours: 8,
  unsortedId: 1,
  pollMs: 2000,
});

/** The place the Jarvis bar leaves for the Brain when a spoken "switch off my
 *  work topic" is ambiguous (route `open_brain: "topics"`). */
export const TOPICS_PLACE = "topics";

/* ── Small helpers ─────────────────────────────────────────────────────── */

/** "{n} facts" filled in. Unknown placeholders stay as they are. */
export function fill(template, vars = {}) {
  return String(template).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

export const modeById = (id) => MODES.find((m) => m.id === id) || null;

/** A mode's plain name; an unknown id is shown as it came, never guessed. */
export const modeName = (id) => (modeById(id) ? modeById(id).name : String(id || ""));

export const isMode = (id) => MODES.some((m) => m.id === id);

const int = (v) => (Number.isInteger(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");
const posInt = (v) => (Number.isInteger(v) && v >= 1 ? v : null);

/* ── The rules the PC also checks (held to the fixture) ────────────────── */

export const codePointLength = (s) => Array.from(String(s)).length;

/** The topic name, tidied (spaces collapsed) - or null when it is not allowed. */
export function cleanName(raw) {
  if (typeof raw !== "string") return null;
  const s = raw.split(/\s+/).filter(Boolean).join(" ");
  if (!s || codePointLength(s) > LIMITS.nameMax) return null;
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (c < 32 || "​‌‍⁠﻿".includes(ch)) return null;
  }
  return s;
}

const WORD_OK = /^[\p{L}\p{N}_][\p{L}\p{N}_' -]*[\p{L}\p{N}_]$/u;

/** The owner's keywords, lower-cased, no duplicates - or null. Takes null, a
 *  string (split on commas and new lines) or a list of strings. */
export function cleanWords(raw) {
  if (raw === null || raw === undefined) return [];
  let items = raw;
  if (typeof raw === "string") items = raw.split(/[\n,]/);
  if (!Array.isArray(items) || items.length > LIMITS.wordsMax * 2) return null;
  const out = [];
  for (const item of items) {
    if (typeof item !== "string") return null;
    const w = item.split(/\s+/).filter(Boolean).join(" ").toLowerCase();
    if (!w) continue;
    const n = codePointLength(w);
    if (n < 2 || n > 30 || !WORD_OK.test(w)) return null;
    if (!out.includes(w)) out.push(w);
  }
  return out.length <= LIMITS.wordsMax ? out : null;
}

/* ── Modes: what a change opens up (contract C4, C8) ───────────────────── */

const CAPS = Object.freeze({
  both: { learn: true, use: true },
  use_only: { learn: false, use: true },
  learn_only: { learn: true, use: false },
  off: { learn: false, use: false },
});

/** True when `next` lets Jarvis learn or use something `prev` did not. Used
 *  for the delete dialog's "more open" line only; whether a card is raised is
 *  the PC's decision (the preview's `card_line`). */
export function loosens(prev, next) {
  const a = CAPS[prev];
  const b = CAPS[next];
  if (!a || !b) return false;
  return (b.learn && !a.learn) || (b.use && !a.use);
}

/** The label rule the fixture's `mode_cases` pins: a looser choice on a
 *  private topic asks. The app uses the PC's `card_line`; this is for tests. */
export const needsCardLabel = (prev, next, isPrivate) => Boolean(isPrivate) && loosens(prev, next);

/* ── Reading the PC's answers ──────────────────────────────────────────── */

/** True for a refusal the PC classified: `{ok: false, error, message}`. */
export function isRefusal(out) {
  return Boolean(out && typeof out === "object" && out.ok === false && typeof out.error === "string");
}

/** The PC's own sentence for a refusal; else the shared one for its code. */
export function refusalWords(out) {
  if (!out || typeof out !== "object") return ERRORS.bad_request;
  if (typeof out.message === "string" && out.message.trim()) return out.message.trim();
  return ERRORS[out.error] || ERRORS.bad_request;
}

function readTopic(t) {
  if (!t || typeof t !== "object") return null;
  const id = posInt(t.id);
  if (id === null || !isMode(t.mode)) return null;
  return {
    id,
    name: text(t.name),
    colour: int(t.colour) !== null && t.colour >= 0 && t.colour < LIMITS.colours ? t.colour : 6,
    icon: text(t.icon) || "folder",
    mode: t.mode,
    private: t.private === true,
    words: Array.isArray(t.words) ? t.words.filter((w) => typeof w === "string") : [],
    ord: int(t.ord) ?? 0,
    system: t.system === true || id === LIMITS.unsortedId,
    facts: Math.max(0, int(t.facts) ?? 0),
    unchecked: Math.max(0, int(t.unchecked) ?? 0),
    hidden: t.mode === "off",
    skippedWeek: Math.max(0, int(t.skipped_week) ?? 0),
  };
}

function readWaiting(w) {
  if (!w || typeof w !== "object") return null;
  const topic = posInt(w.topic);
  if (topic === null) return null;
  return { topic, kind: text(w.kind) };
}

function readLast(l) {
  if (!l || typeof l !== "object") return null;
  const outcome = text(l.outcome);
  const message = text(l.message).trim() || LAST_WORDS[outcome] || "";
  return message ? { outcome, why: text(l.why), at: Number.isFinite(l.at) ? l.at : 0, message } : null;
}

/**
 * `GET /api/topics` (or any write's view), as the page uses it, or null when
 * the answer is not a topics view. `listsHidden` is true while "Hide memory
 * lists and chat history" is on: Rust took the names and keywords out, so the
 * rows read "Topic N, X facts, mode" (contract C5).
 */
export function readTopics(answer) {
  const a = answer && typeof answer === "object" ? answer : null;
  if (!a || a.ok !== true || !Array.isArray(a.topics)) return null;
  const topics = a.topics.map(readTopic).filter(Boolean);
  const bf = a.backfill && typeof a.backfill === "object" ? a.backfill : {};
  return {
    topics,
    listsHidden: a.lists_hidden === true,
    unchecked: Math.max(0, int(a.unchecked) ?? 0),
    facts: Math.max(0, int(a.facts) ?? 0),
    sorted: Math.max(0, int(a.sorted) ?? 0),
    modelHelp: a.model_help === true,
    backfillRemaining: bf.done === true ? 0 : Math.max(0, int(bf.remaining) ?? 0),
    maxTopics: posInt(a.limits && a.limits.max_topics) ?? LIMITS.maxTopics,
    waiting: readWaiting(a.waiting),
    last: readLast(a.last),
  };
}

export const topicById = (view, id) =>
  (view && view.topics ? view.topics.find((t) => t.id === Number(id)) : null) || null;

/** The owner's own topics (Unsorted is not counted, contract C4). */
export const ownTopics = (view) => (view && view.topics ? view.topics.filter((t) => !t.system) : []);

/** True when another topic can still be added. */
export const canAdd = (view) => ownTopics(view).length < (view ? view.maxTopics : LIMITS.maxTopics);

/** The 1-based place of a topic among the owner's own topics (Unsorted has none). */
export function ownIndex(view, id) {
  const i = ownTopics(view).findIndex((t) => t.id === Number(id));
  return i < 0 ? 0 : i + 1;
}

/** What to call a topic on screen: its name, or "Topic N" while names are hidden. */
export function displayName(view, topic) {
  if (!topic) return "";
  if (topic.system) return WORDS.unsorted_name;
  if (view && view.listsHidden) return hiddenName(ownIndex(view, topic.id));
  return topic.name;
}

/* ── The lines the rows read (contract C3, C5) ─────────────────────────── */

/** The row as a screen reader says it (contract C4). */
export const screenReader = (name, n, modeId) =>
  fill(Number(n) === 1 ? WORDS.screen_reader_one : WORDS.screen_reader, { name, n, mode: modeName(modeId) });

/** What a topic is called while names are hidden: "Topic 1". */
export const hiddenName = (index) => `Topic ${index}`;

/** The row while names are hidden: "Topic 1, 41 facts, Use, but don't learn". */
export const hiddenRow = (index, n, modeId) =>
  fill(Number(n) === 1 ? WORDS.hidden_row_one : WORDS.hidden_row, { index, n, mode: modeName(modeId) });

/** "{n} facts" - and "1 fact". */
export const factCount = (n) => APP_WORDS.facts_word(Math.max(0, Number(n) || 0));

/** A row's line for a topic, whatever is hidden. */
export function rowSpeech(view, topic) {
  if (view && view.listsHidden && !topic.system) {
    return hiddenRow(ownIndex(view, topic.id), topic.facts, topic.mode);
  }
  return screenReader(displayName(view, topic), topic.facts, topic.mode);
}

/** The little tags beside a row, in the order they are drawn. Colour is never
 *  the only clue: the icon and the name always show as well. */
export function rowTags(topic) {
  const out = [];
  if (topic.private) out.push({ kind: "private", text: WORDS.private_tag });
  if (topic.mode === "learn_only") out.push({ kind: "not-used", text: WORDS.not_used_tag });
  if (topic.mode === "off") {
    out.push({ kind: "kept-hidden", text: keptHiddenLine(topic.facts) });
  }
  if (topic.skippedWeek > 0) {
    out.push({
      kind: "skipped",
      text: topic.skippedWeek === 1 ? WORDS.skipped_one : fill(WORDS.skipped, { n: topic.skippedWeek }),
    });
  }
  return out;
}

/** The line above the rows while the PC is still sorting old facts. */
export const sortingLine = (view) =>
  view && view.backfillRemaining > 0 ? fill(WORDS.sorting_now, { n: view.backfillRemaining }) : "";

/** "Jarvis sorted N of your M facts by guessing..." - when any are unchecked. */
export function sortedGuessLine(view) {
  if (!view || view.unchecked <= 0) return "";
  if (view.unchecked === 1) return WORDS.sorted_guess_one;
  return fill(WORDS.sorted_guess, { n: view.unchecked, total: view.facts });
}

export const checkButtonLabel = (n) => fill(WORDS.check_button, { n });

/* ── The preview under the picker (contract C2, C4) ────────────────────── */

/** The sentence the picker shows, and the card line under it. The PC builds
 *  `line`; while names are hidden Rust blanks it (it names the topic), so it is
 *  built here from the numbers with `name` (a "Topic N"). */
export function previewLines(p, name) {
  const pv = p && typeof p === "object" ? p : {};
  const lines = [];
  const line = text(pv.line).trim();
  if (line) {
    lines.push(line);
  } else if (pv.ok === true) {
    const affected = Math.max(0, int(pv.affected) ?? 0);
    if (affected === 0) lines.push(fill(WORDS.preview_none, { name }));
    else if (affected === 1) lines.push(fill(WORDS.preview_left_out_one, { name }));
    else lines.push(fill(WORDS.preview_left_out, { n: affected, name }));
    if (pv.stops_learning === true) lines.push(fill(WORDS.preview_stop_learning, { name }));
    const pinned = Math.max(0, int(pv.pinned) ?? 0);
    if (pinned === 1) lines.push(fill(WORDS.preview_pinned_one, { name }));
    else if (pinned > 1) lines.push(fill(WORDS.preview_pinned, { n: pinned, name }));
  }
  return { line: lines.join(" "), cardLine: text(pv.card_line).trim() };
}

/* ── The card being waited on (contract C2 "202 waiting/card flow") ────── */

/** True while one approval card is up. */
export const isWaiting = (view) => Boolean(view && view.waiting);

/** True when this topic is the one whose card is up: its picker cannot be
 *  reopened until it clears (contract C3). */
export const isWaitingOn = (view, id) => Boolean(view && view.waiting && view.waiting.topic === Number(id));

/** What to say when a card that was up has ended: the PC's own sentence. */
export function endedWords(view) {
  return view && view.last ? view.last.message : "";
}

/** A 202: the write raised a card and changed nothing yet. */
export const isWaitingAnswer = (out) =>
  Boolean(out && out.ok === true && out.waiting === true);

/* ── Row order, moving and deleting ────────────────────────────────────── */

/** The `before` for moving `id` one place up (-1) or down (+1) among the
 *  owner's own topics: the id it must go before, `null` for last, or
 *  `undefined` when it cannot move that way. */
export function moveTarget(view, id, direction) {
  const own = ownTopics(view);
  const i = own.findIndex((t) => t.id === Number(id));
  if (i < 0) return undefined;
  if (direction < 0) return i === 0 ? undefined : own[i - 1].id;
  if (i === own.length - 1) return undefined;
  return i + 2 < own.length ? own[i + 2].id : null;
}

/** Where a deleted topic's facts may go: every other topic, Unsorted first. */
export const deleteDestinations = (view, id) =>
  (view ? view.topics : []).filter((t) => t.id !== Number(id));

/** The delete dialog's warning for one destination, or "". */
export function deleteWarning(view, from, to) {
  if (!from || !to) return "";
  return loosens(from.mode, to.mode) ? fill(WORDS.delete_looser, { name: displayName(view, from) }) : "";
}

/** The next colour slot to offer a new topic: the least used, lowest first. */
export function nextColour(view) {
  const used = new Array(LIMITS.colours).fill(0);
  for (const t of ownTopics(view)) if (t.colour >= 0 && t.colour < LIMITS.colours) used[t.colour] += 1;
  let best = 0;
  for (let i = 1; i < used.length; i += 1) if (used[i] < used[best]) best = i;
  return best;
}

/* ── The colours and pictures (shared with chat tags) ──────────────────── */

export { COLOURS };

/** The tags' ten icons, then the three topics add. */
export const ICONS = Object.freeze([...TAG_ICONS, "heart", "coin", "people"]);

/** The three drawings topics add (24x24, stroked in the current colour,
 *  the same style as the tags' icons). */
export const EXTRA_ICON_PATHS = Object.freeze({
  heart: ["M12 20s-8-4.6-8-10.4A4.6 4.6 0 0 1 12 7a4.6 4.6 0 0 1 8 2.6C20 15.4 12 20 12 20z"],
  coin: ["M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z", "M14.5 9a3 3 0 0 0-2.5-1.2c-1.7 0-3 .9-3 2.2s1.3 1.8 3 2.2 3 .9 3 2.2-1.3 2.2-3 2.2A3 3 0 0 1 9.5 15", "M12 6.5v1.3", "M12 16.7V18"],
  people: [
    "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "M3 20v-1a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v1",
    "M16 5.2a3 3 0 0 1 0 5.6",
    "M18 14.3a5 5 0 0 1 3 4.7v1",
  ],
});

const SVG_NS = "http://www.w3.org/2000/svg";

/** An inline SVG for a topic's icon: the tags' drawings, plus heart, coin and
 *  people; an unknown name draws the folder. Decoration only - the name beside
 *  it says the same thing - so it is hidden from screen readers. */
export function topicIconNode(name, doc = document) {
  const paths = EXTRA_ICON_PATHS[name] || ICON_PATHS[name] || ICON_PATHS.folder;
  const svg = doc.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.classList.add("tag-icon");
  for (const d of paths) {
    const path = doc.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

/* ── The "Check these" list (contract C4) ──────────────────────────────── */

/** `GET /api/topics/review` (or `/hidden`): the facts, the cursor, the total.
 *  A fact without a whole-number id is dropped, never guessed. */
export function readFacts(answer) {
  const a = answer && typeof answer === "object" ? answer : null;
  if (!a || a.ok !== true || !Array.isArray(a.facts)) return null;
  return {
    listsHidden: a.lists_hidden === true,
    facts: a.facts
      .filter((f) => f && posInt(f.id) !== null)
      .map((f) => ({
        id: f.id,
        text: text(f.text),
        savedAt: Number.isFinite(f.saved_at) ? f.saved_at : null,
        topic: posInt(f.topic) ?? LIMITS.unsortedId,
        alt: posInt(f.alt),
        how: f.how === "model" ? "model" : f.how === "owner" ? "owner" : "rule",
        checked: f.checked === true,
        heldBack: f.held_back === true,
      })),
    next: a.next === null || a.next === undefined ? null : String(a.next),
    total: Math.max(0, int(a.total) ?? 0),
  };
}

/** The batch as runs of consecutive facts under the same suggested topic
 *  (the PC orders by topic then id, contract C2). */
export function groupByTopic(facts) {
  const groups = [];
  for (const f of facts) {
    const last = groups[groups.length - 1];
    if (last && last.topic === f.topic) last.facts.push(f);
    else groups.push({ topic: f.topic, facts: [f] });
  }
  return groups;
}

/** "Held back: might be about Work" for a fact already being left out. */
export const heldWords = (name) => fill(WORDS.check_held, { name });

/* ── The lines elsewhere in the Brain and the chat (contract C4) ───────── */

/** "Left out 2 facts because of your topic settings", or "" for none. */
export function leftOutLine(n) {
  const count = Number.isInteger(n) && n > 0 ? n : 0;
  if (!count) return "";
  return count === 1 ? WORDS.left_out_one : fill(WORDS.left_out, { n: count });
}

/** "3 facts kept, hidden" for the lists' own note (`topics_hidden`), or "". */
export function keptHiddenLine(n) {
  const count = Number.isInteger(n) && n > 0 ? n : 0;
  if (count === 1) return WORDS.kept_hidden_one;
  return count ? fill(WORDS.kept_hidden, { n: count }) : "";
}

/** The tag on a fact whose topic is "Learn, but don't use", or "". `view` is
 *  the last topics view; without one nothing is claimed. */
export function factTag(view, topicId) {
  const t = topicById(view, topicId);
  return t && t.mode === "learn_only" ? WORDS.not_used_tag : "";
}

/** A pinned fact whose topic may not be used: "Paused: Work is off" (Off) or
 *  "Paused: Work is set to Learn, but don't use". `modeId` is the topic's mode. */
export function pinPausedLine(name, modeId) {
  const key = modeId === "learn_only" ? WORDS.pin_paused_learn : WORDS.pin_paused;
  return fill(key, { name: name || "" });
}

/** The two buttons of a memory card that asks about a topic (`topic_ask`). */
export function askLabels(pending) {
  return pending && pending.topic_ask === true
    ? { accept: WORDS.ask_save, decline: WORDS.ask_skip }
    : null;
}

/** What the Jarvis bar left for the Brain: a topic to open the picker for. */
export function readTopicPlace(left) {
  if (!left || left.place !== TOPICS_PLACE) return { topicId: null };
  return { topicId: posInt(left.topic_id) };
}
