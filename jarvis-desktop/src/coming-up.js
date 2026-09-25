/**
 * "Coming up", on the Brain's Work tab - timers, alarms, reminders, the
 * repeating ones with their next time, and the to-do list (the owner's
 * decisions of 2026-09-25; JARVIS-API.md section 21; backend
 * jarvis_schedule.py).
 *
 * This module holds the words and reads what the PC sends; brain.js draws
 * the section and calls the three Rust commands (src-tauri/src/brain/
 * schedule.rs): brain_schedule (a read, with the words taken out while the
 * private lists are hidden), brain_schedule_act (ONE job: pause, resume,
 * delete, done, add time - held on a stale link, no card) and
 * brain_schedule_add_todo (one to-do item, held on a stale link). There is
 * no "delete all", here or anywhere.
 *
 * The phone says the same words (net/Schedule.kt); backend/test_schedule.py
 * and tests/coming-up.mjs check that they match.
 *
 * @module coming-up
 */

/** The section, both apps' words. */
export const COMING_UP_TITLE = "Coming up";
export const COMING_UP_DETAIL =
  "Timers, alarms and reminders, kept on your PC. They go off on both apps " +
  "while they are connected. Anything that repeats waits for your yes on an approval card.";
export const TODO_TITLE = "To-do list";

/** Nothing on a list. */
export const EMPTY_JOBS =
  "Nothing coming up. Say or type \"set a timer for 10 minutes\" or \"remind me at 6 to call Mum\".";
export const EMPTY_TODO = "Nothing on your to-do list.";

/** A PC without the scheduler (Rust answers `{available: false}`). */
export const SCHEDULE_MISSING =
  "Your PC's Jarvis does not have timers and reminders yet - run apply-patches.ps1 on the PC.";

/** The buttons. */
export const PAUSE_LABEL = "Pause";
export const RESUME_LABEL = "Resume";
export const DELETE_LABEL = "Delete";
export const DONE_LABEL = "Done";
export const ADD_LABEL = "Add";
export const ADD_PLACEHOLDER = "Add to the to-do list";

/** A repeating job whose card has not been answered. */
export const WAITING = "Waiting for your yes on the approval card.";

/** A word that stands in for words the private lists hide. */
export const HIDDEN_TEXT = "(hidden)";

/** Under an answer made without the model (X-Jarvis-Route `quick`). */
export const DONE_LINE = "Done - answered on this PC without the AI model.";

/**
 * The standby schedule (backend jarvis_standby_schedule.py): Standby - the
 * same Standby as the tray's Change power mode - on a timetable, every day.
 * Setting it up is one approval card on the PC (schedule_repeat); it then
 * sits in the list above like any repeating job, where Pause skips it and
 * Delete turns it off. Both apps' words.
 */
export const STANDBY_TITLE = "Standby schedule";
export const STANDBY_DETAIL =
  "Jarvis goes on standby at night and wakes in the morning. Standby unloads its models " +
  "and frees the graphics card; waking loads the chat model again, so the first answer is " +
  "quick. Timers and reminders still go off. Setting it up asks once with an approval card.";
export const STANDBY_START_LABEL = "Standby at";
export const STANDBY_END_LABEL = "Wake at";
export const STANDBY_ADD = "Set up";
export const STANDBY_IS_SET =
  "Your standby schedule is in the list above. Pause skips it and Delete turns it off. " +
  "Neither wakes Jarvis - choose Active for that.";
export const STANDBY_BAD_TIMES = "Write each time as HH:MM, like 01:00, and pick two different times.";
export const STANDBY_DEFAULT_START = "01:00";
export const STANDBY_DEFAULT_END = "07:00";

/** A notification's title, by kind (brain/schedule.rs toast_title). */
export const TOAST_TITLES = Object.freeze({
  timer: "Timer done",
  alarm: "Alarm",
  reminder: "Reminder",
  todo: "To-do",
});

/** What a locked screen may show, by kind, when the PC did not say. */
export const LOCK_SCREEN = Object.freeze({
  timer: "Jarvis: your timer is done.",
  alarm: "Jarvis: alarm.",
  reminder: "Jarvis: a reminder is due.",
  todo: "Jarvis: a to-do item is due.",
});

/** The tag on a row, by kind. */
export const KIND_TAGS = Object.freeze({
  timer: "timer",
  alarm: "alarm",
  reminder: "reminder",
  todo: "to-do",
  standby: "standby",
  briefing: "briefing",
});

/** A morning briefing job's title (it has no words of its own; briefing.js). */
export const BRIEFING_JOB_TITLE = "Morning briefing";

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/** 600 -> "10 minutes", 5400 -> "1 hour 30 minutes" (jarvis_schedule.length_words). */
export function lengthWords(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const parts = [];
  if (h) parts.push(`${h} hour${h !== 1 ? "s" : ""}`);
  if (m) parts.push(`${m} minute${m !== 1 ? "s" : ""}`);
  if (sec && !h) parts.push(`${sec} second${sec !== 1 ? "s" : ""}`);
  return parts.length ? parts.join(" ") : "0 seconds";
}

/** 598 -> "9:58", 3723 -> "1:02:03". A countdown, never negative. */
export function countdown(seconds) {
  const s = Math.max(0, Math.ceil(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const two = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${two(m)}:${two(sec)}` : `${m}:${two(sec)}`;
}

/**
 * `brain_schedule`'s answer, read. `{jobs, todo}` from the PC;
 * `available: false` with `why` from an older PC; `hidden: true` while the
 * private lists are hidden (Rust took the words out). A row without an id
 * the PC makes ("s" and ten hex digits) is dropped, never guessed.
 */
export function readSchedule(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const available = a.available !== false && Array.isArray(a.jobs) && Array.isArray(a.todo);
  const ok = (j) => j && typeof j === "object" && /^s[0-9a-f]{10}$/.test(String(j.id || ""));
  const row = (j) => ({
    id: j.id,
    kind: text(j.kind),
    text: text(j.text),
    state: text(j.state),
    due: num(j.due),
    left: num(j.left),
    duration: num(j.duration),
    when: text(j.when),
    repeats: j.repeats === true,
    repeat: text(j.repeat),
    next: Array.isArray(j.next) ? j.next.filter((t) => num(t) !== null) : [],
    missed: text(j.missed),
    note: text(j.note),
    hidden: j.hidden === true,
  });
  return {
    available,
    why: available ? "" : text(a.why) || SCHEDULE_MISSING,
    hidden: available && a.hidden === true,
    jobs: available ? a.jobs.filter(ok).map(row) : [],
    todo: available ? a.todo.filter(ok).map(row) : [],
  };
}

/** Seconds left on a timer now, from what the PC said `sinceMs` ago. */
export function leftNow(job, sinceMs) {
  if (job.left === null) return null;
  if (job.state !== "active") return job.left;
  return Math.max(0, job.left - Math.max(0, sinceMs) / 1000);
}

/** A row's title: the owner's words, or what kind of thing it is. */
export function titleOf(job) {
  if (job.kind === "standby") return STANDBY_TITLE;
  const words = job.hidden ? HIDDEN_TEXT : job.text;
  if (job.kind === "timer") {
    return words ? `${words} timer` : `${lengthWords(job.duration || 0)} timer`;
  }
  if (job.kind === "briefing") return BRIEFING_JOB_TITLE;
  if (words) return words;
  return job.kind === "alarm" ? "Alarm" : job.kind === "todo" ? "To-do" : "Reminder";
}

/** The lines under a row's title. `sinceMs`: how long ago the PC said it. */
export function metaOf(job, sinceMs = 0) {
  const out = [];
  if (job.state === "waiting") {
    if (job.repeat) out.push(job.repeat);
    out.push(WAITING);
    return out;
  }
  if (job.kind === "timer") {
    const left = leftNow(job, sinceMs);
    out.push(job.state === "paused" ? `Paused - ${countdown(left)} left` : `${countdown(left)} left`);
    return out;
  }
  if (job.repeats && job.repeat) out.push(job.repeat);
  if (job.state === "paused") out.push("Paused");
  else if (job.when) out.push(job.repeats ? `next: ${job.when}` : job.when);
  if (job.missed) out.push(`Went off late (${job.missed}) - the PC was off or asleep.`);
  if (job.note) out.push(job.note);
  return out;
}

/** The standby schedule on the list, or null. There is only ever one. */
export function standbyOf(view) {
  return (view && view.jobs.find((j) => j.kind === "standby")) || null;
}

const HHMM = /^([01]?\d|2[0-3]):([0-5]\d)$/;

/**
 * The two times for a new standby schedule, tidied to HH:MM, or null when
 * either is not a time of day or they are the same (the PC says the same).
 */
export function standbyTimes(start, end) {
  const tidy = (v) => {
    const m = HHMM.exec(String(v || "").trim());
    return m ? `${m[1].padStart(2, "0")}:${m[2]}` : null;
  };
  const at = tidy(start);
  const until = tidy(end);
  if (!at || !until || at === until) return null;
  return { at, until };
}

/** The buttons one row offers, as action names, in order. Never "all". */
export function actionsOf(job) {
  if (job.kind === "todo") return ["done", "delete"];
  if (job.state === "waiting") return ["delete"];
  return [job.state === "paused" ? "resume" : "pause", "delete"];
}

/** A button's label for an action name. */
export function labelOf(action) {
  return {
    pause: PAUSE_LABEL,
    resume: RESUME_LABEL,
    delete: DELETE_LABEL,
    done: DONE_LABEL,
  }[action] || action;
}

/** Is anything counting down (worth a once-a-second repaint)? */
export function anyTicking(view) {
  return Boolean(view && view.jobs.some((j) => j.kind === "timer" && j.state === "active"));
}
