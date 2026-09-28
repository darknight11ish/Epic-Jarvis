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

/** A goal's status, in the owner's own words. */
export const STATUS_LABELS = Object.freeze({
  draft: "Draft", active: "Active", done: "Done", stopped: "Stopped",
});

export function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

/** The backend's own limits (jarvis_goals.py), until `GET /api/goals` says otherwise. */
export const DEFAULT_LIMITS = Object.freeze({ text: 300, steps: 7, goals: 20, by: 40 });

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
  const step = (s) => ({
    step: text(s && s.step),
    by: text(s && s.by),
    done: Boolean(s && s.done === true),
  });
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
    },
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
