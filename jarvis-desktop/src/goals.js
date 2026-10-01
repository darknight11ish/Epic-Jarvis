/**
 * Goals - a plan the owner edits, one card per acting step (the owner's
 * "build it now", 2026-09-27; JARVIS-API.md section 59; backend
 * jarvis_goals.py).
 *
 * The owner types a goal ("insulate the garage before winter") and a short
 * plan - typed by hand, or something they asked Jarvis to suggest in an
 * ordinary chat message first and pasted in. They edit it, then Accept it.
 * Accepting sets up a weekly, model-free check-in at once, with no card -
 * like a plain repeating reminder (the owner, 2026-09-28): it only ever
 * reminds and never acts. (Until then it raised one `schedule_repeat` card;
 * an older PC may still say "waiting" for it.) Ticking a step
 * done, and Stop tracking, need no card and are immediate, like a to-do
 * item. When a step needs real action (search installers, draft an email),
 * the owner asks Jarvis for that in ordinary chat - unrelated to this file.
 *
 * This module holds the words and reads what the PC sends; brain.js draws
 * the section and calls the four Rust commands (src-tauri/src/brain/
 * goals.rs): brain_goals (a read, with the words taken out while the
 * private lists are hidden, same as Coming up), brain_goals_create,
 * brain_goals_accept, brain_goals_step and brain_goals_stop - all four held
 * on a stale link; none raises a card.
 *
 * ## Where the weekly check-in shows
 *
 * The backend registers the check-in as an ordinary kind on the ONE
 * scheduler, `owner_listed=True` (its own default) - so it already shows
 * on Coming up, exactly like a reminder or the morning briefing's job.
 * This file does not try to hide it from there and give Goals a private
 * channel instead: Coming up already shows the briefing's and the standby
 * schedule's own jobs the same way, so a third kind appearing there too is
 * the pattern already in place, not a new one. What this file adds is only
 * a way to find, for one particular goal, which row in that same list is
 * its check-in: by the job id the backend hands back the moment a goal is
 * accepted (`checkin.id`, kept for as long as the window stays open), or,
 * failing that (a reload lost it), by matching the job's own `text` back
 * to the goal's own words - the same words `accept()` gave the job on the
 * backend, so this is not a guess so much as reading the one field that
 * ties them together. Either way the STATE shown ("waiting for the card",
 * paused, its next-run note) always comes from that real job, read from
 * the PC just now - never assumed from having clicked Accept a moment ago.
 *
 * @module goals
 */

import { readList, readProject } from "./projects.js";

export const GOALS_TITLE = "Goals";
export const GOALS_DETAIL =
  "Say what you want, add a few steps with rough dates, then Accept. Jarvis checks in once " +
  "a week - only ever a nudge, never an action. Ticking a step off, and Stop tracking, need " +
  "no approval card.";

/** A PC without the scheduler patch behind Goals (jarvis_goals.py). */
export const GOALS_MISSING =
  "Your PC's Jarvis does not have Goals yet - run apply-patches.ps1 on the PC.";

export const EMPTY_GOALS = "No goals yet. Say what you want to get done, below.";

export const NEW_GOAL_PLACEHOLDER = "What do you want to get done?";
export const NEW_GOAL_LABEL = "Add";
export const ACCEPT_LABEL = "Accept";
export const STOP_LABEL = "Stop tracking";
export const ADD_STEP_LABEL = "Add a step";
export const REMOVE_STEP_LABEL = "Remove";
export const STEP_PLACEHOLDER = "A step";
export const BY_PLACEHOLDER = "Rough date (optional)";

/* Step locks (JARVIS-API section 101; docs/GOALS-PROGRESS-DESIGN.md "Slice
   contract"): the small labels this page adds. The PC sends the lock
   sentences whole (`lock_words`, `reached_words`, its refusals in `error`) and
   this page shows them as sent - it never works out a state itself. */
export const NEEDS_LABEL = "Do these first";
export const MEASURE_LABEL = "Follows a number";
export const FOLLOWS_LABEL = "Follows: ";
export const UNDO_LABEL = "Undo";

/**
 * The lock and number sentences, the same in both apps and equal, key for
 * key and word for word, to `goal_words` in tests/fixtures/projects-cases.json
 * (jarvis_goals.WORDS, plus the screens' own sentences that
 * tools/gen_projects_cases.py adds). An app shows `lock_words` /
 * `reached_words` / `error` as sent. `{max}` and `{step}` are filled in by
 * the app (brain.js goalFill).
 */
export const GOAL_WORDS = Object.freeze({
  after: "after: {steps}",
  after_open_again: "after: {steps} (open again)",
  circle: "These steps wait on each other in a circle: {steps}.",
  follows_empty: "No number with a target yet. Set a target on a benchmark in Projects first.",
  follows_none: "No number",
  follows_under: "The step shows \"reached\" when that number reaches its target. You still tick it yourself.",
  locked: "locked",
  locked_refusal: "Do \"{step}\" first, or tick it if it is already done.",
  measure_gone: "The number this step follows is gone - tick it by hand.",
  needs_cleaned: "Removed \"{step}\" - the steps that waited on it no longer do.",
  needs_limit: "At most {max} steps can come first.",
  needs_none: "Nothing - this step can start now",
  needs_under: "This step stays locked until the ones you pick are done. Pick up to 3.",
  no_such_benchmark: "\"{step}\" follows a number that does not exist any more.",
  no_target: "\"{step}\" follows \"{name}\", which has no target yet - set one first.",
  reached: "The number reached its target: {latest} (target {target}).",
  reached_tag: "number reached",
  reached_tick: "{step}: the number reached its target - tick it when you are ready.",
  self_wait: "\"{step}\" cannot wait on itself.",
  ticked: "Ticked \"{step}\".",
  too_many_needs: "\"{step}\" can wait on at most 3 other steps.",
  unknown_wait: "\"{step}\" waits on a step that is not in this plan.",
  unticked: "Unticked \"{step}\".",
  waiting_on: "Waiting on \"{step}\".",
});

export const NEEDS_NONE = GOAL_WORDS.needs_none;
export const NEEDS_UNDER = GOAL_WORDS.needs_under;
export const NEEDS_FULL = GOAL_WORDS.needs_limit;
export const NEEDS_CLEANED = GOAL_WORDS.needs_cleaned;
export const MEASURE_NONE = GOAL_WORDS.follows_none;
export const MEASURE_UNDER = GOAL_WORDS.follows_under;
export const MEASURE_EMPTY = GOAL_WORDS.follows_empty;
export const REACHED_TAG = GOAL_WORDS.reached_tag;
export const UNDO_TICKED = GOAL_WORDS.ticked;
export const UNTICKED = GOAL_WORDS.unticked;

/** The step ids the PC makes (jarvis_goals.STEP_IDS). */
export const STEP_IDS = Object.freeze(["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]);

const STEP_STATES = ["open", "locked", "met_by_number", "done"];

/** A goal's status, in the owner's own words. */
export const STATUS_LABELS = Object.freeze({
  draft: "Draft", active: "Active", done: "Done", stopped: "Stopped",
});

export function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

/** The backend's own limits (jarvis_goals.py), until `GET /api/goals` says otherwise. */
export const DEFAULT_LIMITS = Object.freeze({ text: 300, steps: 7, goals: 20, by: 40, needs: 3 });

const STATUSES = ["draft", "active", "done", "stopped"];
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/**
 * `brain_goals`'s answer, read. `{goals, limits}` from the PC; `available:
 * false` with `why` from an older PC; `hidden: true` while the private
 * lists are hidden (Rust took the words out). A row without an id the PC
 * makes ("g" and ten hex digits) is dropped, never guessed.
 */
export function readGoals(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const available = a.available !== false && Array.isArray(a.goals);
  const okId = (g) => g && typeof g === "object" && /^g[0-9a-f]{10}$/.test(String(g.id || ""));
  const ids = (v) => (Array.isArray(v) ? v.filter((x) => STEP_IDS.includes(x)) : []);
  const hex32 = (v) => typeof v === "string" && /^[0-9a-f]{32}$/.test(v);
  const step = (s) => {
    const o = s && typeof s === "object" ? s : {};
    const m = o.measure && typeof o.measure === "object" ? o.measure : null;
    const done = o.done === true;
    return {
      // What the PC stores (and the only things sent back on a save).
      id: STEP_IDS.includes(o.id) ? o.id : "",
      step: text(o.step),
      by: text(o.by),
      done,
      needs: ids(o.needs),
      measure: m && hex32(m.project) && hex32(m.bench) ? { project: m.project, bench: m.bench } : null,
      // What the PC works out - shown, never sent back, never decided here.
      doneAt: num(o.done_at),
      state: STEP_STATES.includes(o.state) ? o.state : (done ? "done" : "open"),
      waitingOn: ids(o.waiting_on),
      lockWords: text(o.lock_words),
      reached: o.reached === true,
      reachedWords: text(o.reached_words),
      measureName: text(o.measure_name),
      measureGone: o.measure_gone === true,
      measureSensitive: o.measure_sensitive === true,
    };
  };
  const goal = (g) => ({
    id: g.id,
    text: text(g.text),
    plan: Array.isArray(g.plan) ? g.plan.filter((s) => s && typeof s === "object").map(step) : [],
    status: STATUSES.includes(g.status) ? g.status : "draft",
    created: num(g.created),
    changed: num(g.changed),
    hidden: g.hidden === true,
  });
  const limits = a.limits && typeof a.limits === "object" ? a.limits : {};
  return {
    available,
    why: available ? "" : text(a.why) || GOALS_MISSING,
    hidden: available && a.hidden === true,
    goals: available ? a.goals.filter(okId).map(goal) : [],
    limits: {
      text: num(limits.text) || DEFAULT_LIMITS.text,
      steps: num(limits.steps) || DEFAULT_LIMITS.steps,
      goals: num(limits.goals) || DEFAULT_LIMITS.goals,
      by: num(limits.by) || DEFAULT_LIMITS.by,
      needs: num(limits.needs) || DEFAULT_LIMITS.needs,
    },
    // An older PC has no locks: it sends no `needs` limit, so the editor
    // offers no pickers and sends the plain steps as before.
    locks: available && num(limits.needs) !== null,
  };
}

/** How many goals count against the open limit (draft + active - jarvis_goals._count_open). */
export function openCount(view) {
  return view ? view.goals.filter((g) => g.status === "draft" || g.status === "active").length : 0;
}

/**
 * Whether a plan is worth sending to Accept: at least one step, none of
 * them empty or over the PC's own limits. The PC checks the same things
 * and says so in its own words if this ever disagrees with it.
 */
export function planIsValid(plan, limits = DEFAULT_LIMITS) {
  if (!Array.isArray(plan) || !plan.length || plan.length > limits.steps) return false;
  return plan.every((s) => {
    const step = String((s && s.step) || "").trim();
    return step.length > 0 && step.length <= limits.text
      && String((s && s.by) || "").length <= limits.by;
  });
}

/**
 * The weekly check-in job for one ACTIVE goal, found in the Coming up list
 * already read for that tab - never a second read of its own. `knownId` is
 * the id `accept()` handed back for this goal, if this window still has
 * it; when it does not (a reload lost it), the fallback is matching the
 * job's own `text` to the goal's own words, which is exactly what the
 * backend's own `accept()` set it to. Returns null while Coming up has not
 * been read yet, or while there is truly no such job (the PC is older than
 * this feature, say).
 */
export function checkinJobFor(goal, jobs, knownId) {
  if (!jobs || !jobs.length || !goal) return null;
  if (knownId) {
    const byId = jobs.find((j) => j.id === knownId && j.kind === "goal_checkin");
    if (byId) return byId;
  }
  return jobs.find((j) => j.kind === "goal_checkin" && j.text === goal.text) || null;
}

/**
 * The lines to show under an active goal for its check-in: how often, and
 * either the same "waiting for the card" words Coming up already uses
 * (`waitingWords`), Paused, or the PC's own deterministic nudge (`note`,
 * e.g. `"insulate the garage...": still on track for "contact 3
 * installers" (this week)?`). Empty while the job is not known yet.
 */
export function checkinLines(job, waitingWords) {
  if (!job) return [];
  const out = [];
  if (job.repeat) out.push(`Weekly check-in: ${job.repeat}`);
  if (job.state === "waiting") out.push(waitingWords);
  else if (job.state === "paused") out.push("Paused");
  else if (job.note) out.push(job.note);
  return out;
}

/* ── Step locks: the row, the editor, the save ─────────────────────────── */

/**
 * The fields the PC stores for a step - and the ONLY ones sent back on
 * Accept: `{id?, step, by, done, needs, measure}`. Never `state`,
 * `waiting_on`, `lock_words`, `reached*`, `measure_*` or `done_at` (the PC
 * ignores them and `done_at` is set by the PC alone). A step with no id yet
 * (a new one, or one from an older PC) is sent without one.
 */
export function storedStep(s) {
  const o = s && typeof s === "object" ? s : {};
  const out = {
    step: text(o.step),
    by: text(o.by),
    done: o.done === true,
    needs: Array.isArray(o.needs) ? o.needs.filter((x) => typeof x === "string") : [],
    measure: o.measure && typeof o.measure === "object"
      ? { project: text(o.measure.project), bench: text(o.measure.bench) } : null,
  };
  if (typeof o.id === "string" && o.id) return { id: o.id, ...out };
  return out;
}

/** The whole plan as it is sent to Accept or Create. */
export function planBody(plan) {
  return (Array.isArray(plan) ? plan : []).map(storedStep);
}

/** The first of s1..s9 no step in `plan` uses; "" if none (cannot happen at 7 steps). */
export function freeStepId(plan) {
  const taken = new Set((plan || []).map((s) => s && s.id));
  return STEP_IDS.find((id) => !taken.has(id)) || "";
}

/**
 * A new, empty step for the editor. It takes a free id at once, so other
 * steps can be told to wait on it before the plan is saved; the PC keeps a
 * free id it is sent. Without lock support (an older PC) it has no id.
 */
export function newStep(plan, locks = true) {
  const base = { step: "", by: "", done: false, needs: [], measure: null };
  const id = locks ? freeStepId(plan) : "";
  return id ? { id, ...base } : base;
}

/**
 * Takes the step at `index` out of the plan and out of every other step's
 * `needs` (the PC does not clean that for the app). Returns how many other
 * steps waited on it, so the editor can say so before the plan is saved.
 */
export function removeStepAt(plan, index) {
  const [gone] = plan.splice(index, 1);
  let touched = 0;
  if (gone && gone.id) {
    for (const s of plan) {
      if (Array.isArray(s.needs) && s.needs.includes(gone.id)) {
        s.needs = s.needs.filter((n) => n !== gone.id);
        touched += 1;
      }
    }
  }
  return { gone, touched };
}

/** Puts a step id on or off a step's "Do these first"; stops at `max`. Returns whether it changed. */
export function setNeed(step, id, on, max = DEFAULT_LIMITS.needs) {
  const needs = Array.isArray(step.needs) ? step.needs : [];
  if (on) {
    if (needs.includes(id)) return false;
    if (needs.length >= max) return false;
    step.needs = [...needs, id];
    return true;
  }
  if (!needs.includes(id)) return false;
  step.needs = needs.filter((n) => n !== id);
  return true;
}

/** The other steps a step can wait on: those with an id, not itself. */
export function needChoices(plan, index) {
  return plan
    .map((s, i) => ({ s, i }))
    .filter(({ s, i }) => i !== index && s.id)
    .map(({ s, i }) => ({ id: s.id, position: i + 1, label: `${i + 1}. ${text(s.step).trim() || "(empty step)"}` }));
}

/** The ids of the projects in a `projects_read` list answer, at most 20
 *  (nothing while hidden). Life and coding alike: a step may follow a number
 *  from either. */
export function benchProjectIds(list) {
  const l = readList(list);
  return l.available && !l.hidden ? l.projects.slice(0, 20).map((p) => p.id) : [];
}

/**
 * The number benchmarks a step can follow, in life and coding projects alike:
 * those with a target and a better direction (the PC refuses any other). `list` is a `projects_read` list
 * answer and `projectAnswers` the full-project answers, one per project;
 * anything hidden or unreadable gives nothing.
 */
export function measureChoices(list, projectAnswers) {
  const l = readList(list);
  if (!l.available || l.hidden) return [];
  const out = [];
  for (const ans of projectAnswers || []) {
    if (!ans || ans.hidden === true) continue;
    const p = readProject(ans.project);
    if (!p.id) continue;
    for (const b of p.benchList) {
      if (b.kind !== "number" || b.target === null || b.better === null) continue;
      out.push({ project: p.id, bench: b.id, label: `${p.name} - ${b.name}` });
    }
  }
  return out;
}

/**
 * What a step row shows, from the PC's own fields. `hideWords` is true while
 * the private lists are hidden: a sensitive number's name and sentence go
 * (Rust has already blanked every step's words then; this is the second
 * lock). Never works a state out itself.
 */
export function stepRow(s, { hideWords = false } = {}) {
  const locked = s.state === "locked";
  const met = s.state === "done" || s.state === "met_by_number";
  const hideSensitive = hideWords && s.measureSensitive;
  const reachedLine = s.reached && !hideSensitive ? s.reachedWords : "";
  const lockLine = s.lockWords;
  const follows = s.measure && !hideSensitive && s.measureName && !s.measureGone
    ? FOLLOWS_LABEL + s.measureName : "";
  const goneLine = s.measure && s.measureGone ? GOAL_WORDS.measure_gone : "";
  const reason = locked ? lockLine : "";
  const parts = [text(s.step)];
  if (locked) parts.push(GOAL_WORDS.locked);
  if (lockLine) parts.push(lockLine);
  if (reachedLine) parts.push(reachedLine);
  if (goneLine) parts.push(goneLine);
  return {
    locked,
    met,
    reached: s.reached && s.state !== "done",
    lockLine,
    reachedLine,
    follows,
    goneLine,
    reason,
    label: parts.filter(Boolean).join(", "),
  };
}
