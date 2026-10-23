/**
 * hud-actions.js - ONE kind -> actions table for a schedule row (F5 of the
 * 2026-10-22 coherence slice; Gemini ruling Q2).
 *
 * WHAT IT IS. Every surface that shows a reminder / timer / alarm / to-do row
 * must offer the SAME one-job actions with the SAME words. This module is the
 * single table: the HUD's Reminders panel and the Brain's Coming up both read
 * it, and the cross-surface test (`tests/coming-up.mjs`) holds the HUD page's
 * fallback and the phone's list to it.
 *
 * THE PC IS THE AUTHORITY, NOT THIS FILE. `backend/jarvis_schedule.py`
 * `Scheduler.act` decides what is actually allowed, and the table mirrors it:
 *   - a kind with no time of its own (`Kind.ends`, "remind me next time ...")
 *     cannot pause or resume - Delete is its one action;
 *   - a to-do is done or deleted, never paused;
 *   - a job waiting for an approval can only be deleted;
 *   - add_time is a TIMER's alone: `act` answers "Time can only be added to a
 *     timer." for every other kind, so no other row draws it;
 *   - snooze is only for something that already went off;
 *   - the quiet `review` row belongs to the Decks window and has no actions.
 *
 * NO DEPENDENCY, NO DOM. Pure data and a pure function, so the phone (or a
 * generated contract later) can compare against it without a browser.
 *
 * @module hud-actions
 */

/** The owner-facing words for each action. One spelling, every surface. */
export const ACTION_LABELS = Object.freeze({
  add_time: "+5 minutes",
  pause: "Pause",
  resume: "Resume",
  delete: "Delete",
  done: "Done",
  snooze: "Snooze 10 minutes",
});

/** Actions for a row that has ALREADY gone off (snooze or clear). */
export const WENT_OFF_ACTIONS = Object.freeze(["snooze", "delete"]);

/**
 * Kinds whose PC state has no pause of its own (`Kind.ends` in
 * jarvis_schedule.py). A row of one of these offers Delete only.
 */
export const NO_PAUSE_KINDS = Object.freeze(["nexttime"]);

/** The action descriptors one row offers, in the order the buttons draw them. */
export function actionsFor(job, wentOff = false) {
  if (!job || typeof job !== "object") return [];
  const kind = String(job.kind || "");
  const state = String(job.state || "");
  if (wentOff) {
    return WENT_OFF_ACTIONS.map((doIt) => ({ do: doIt, label: ACTION_LABELS[doIt] }));
  }
  if (kind === "review") return [];
  if (state === "waiting") {
    return [{ do: "delete", label: ACTION_LABELS.delete, danger: true }];
  }
  if (kind === "todo") {
    return [
      { do: "done", label: ACTION_LABELS.done },
      { do: "delete", label: ACTION_LABELS.delete, danger: true },
    ];
  }
  const out = [];
  if (kind === "timer") {
    out.push({ do: "add_time", label: ACTION_LABELS.add_time });
  }
  if (!NO_PAUSE_KINDS.includes(kind)) {
    if (state === "active") out.push({ do: "pause", label: ACTION_LABELS.pause });
    else if (state === "paused") out.push({ do: "resume", label: ACTION_LABELS.resume });
  }
  out.push({ do: "delete", label: ACTION_LABELS.delete, danger: true });
  return out;
}

/** The same answer as action names only (what the Brain's list stores). */
export function actionNames(job, wentOff = false) {
  return actionsFor(job, wentOff).map((action) => action.do);
}

/**
 * Whether the PC lets time be added to this kind. `jarvis_schedule.act`'s
 * add_time branch refuses every kind but a timer, so this table does too - and
 * the test reads the backend's own sentence to prove it.
 */
export function kindAllowsAddTime(kind) {
  return kind === "timer";
}

/* ------------------------------------------------------------------ *
 * Phase 2 (2026-10-22, the owner's Reminders request): the row editor's
 * words, the kinds it may edit, and the keyboard reorder's rank. The HUD's
 * Reminders panel and the Brain's Coming up read these, so the two windows
 * cannot come to different words for the same control; the PC's own
 * jarvis_schedule._act_phase2 is the authority on every refusal.
 * ------------------------------------------------------------------ */

export const EDIT_LABEL = "Edit";
export const SAVE_LABEL = "Save changes";
export const CANCEL_LABEL = "Cancel";
export const MOVE_TO_TODO_LABEL = "To-do list";
export const UP_LABEL = "Move up";
export const DOWN_LABEL = "Move down";
export const ASKED_REPEAT_WORDS =
  "Asked the PC. Nothing changes until you answer the card.";
export const REPEAT_CARD_WORDS =
  "A repeat change asks with one card; the old schedule stays active until " +
  "you answer it.";
export const NOTHING_CHANGED_WORDS = "Nothing changed.";
export const TIMER_MINUTES_HINT = "1 to 1440 minutes (24 hours).";

/** The kinds whose ONE item may be edited, moved or reordered. */
export const EDITABLE_KINDS = Object.freeze(["timer", "alarm", "reminder", "todo"]);

/**
 * Whether a row offers Edit at all. `phase2` is the PC's own read marker:
 * an older backend draws nothing. Hidden words (App lock / hidden memory
 * lists) also draw nothing - editing needs the words and list names.
 */
export function canEdit(job, { phase2 = false, hidden = false } = {}) {
  if (!job || typeof job !== "object" || !phase2 || hidden) return false;
  if (job.hidden === true) return false;
  if (!EDITABLE_KINDS.includes(String(job.kind || ""))) return false;
  return job.state === "active" || job.state === "paused";
}

/** The rank an Up/Down button moves from: the PC's own, else the row's index. */
export function rankOf(job, index = 0) {
  return Number.isInteger(job && job.rank) ? job.rank : index;
}
