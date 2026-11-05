/**
 * Attention-first sorting for the Work pane (2026-11-04).
 *
 * Ported from `dsh-superagent`'s `waits_for_person` predicate (Part II pattern
 * 4 of the owner-forwarded 2026-11-04 spec), because a Work tab that lists
 * every background job equally makes healthy work look like work the owner
 * must look at. The whole pane is now two sections: "Needs you" (a person has
 * to decide, answer, retry or read a failure) and one collapsed
 * "Quiet / healthy" bar for everything else.
 *
 * ## The contract, and where the fact comes from
 *
 * `waitsForPerson(job)` is TRUE only when a human decision, an answer or an
 * unacknowledged failure is what the job is waiting on:
 *
 *   status in ("waiting_approval", "blocked", "needs_input")
 *   or (status == "failed" and not dismissed_by_owner)
 *
 * The PC may send the answer itself in a per-job `waits_for_person` boolean;
 * when it does, that boolean WINS (the server knows things this file cannot
 * see, and a client that overrode it could hide a card). When the boolean is
 * absent - every backend shipped before 2026-11-04, and any payload from one -
 * the derivation above is used, so the pane looks right against an older PC
 * rather than broken.
 *
 * The job's state is read from `state`, which both feeds (`GET /api/jobs` and
 * `GET /api/tasks`) use. `status` is accepted too because the predicate was
 * specified in those words; a row carrying both is read from `state` first.
 *
 * The module is PURE: no DOM, no clock of its own (callers pass `now`), no
 * network. `jarvis-desktop/tests/attention-first.mjs` pins the truth table,
 * the stable order and the one-line summary.
 */

/** The section heading the owner reads. The phone draws the same words. */
export const NEEDS_YOU = "Needs you";

/** The collapsed bar's own name. The phone draws the same words. */
export const QUIET_HEALTHY = "Quiet / healthy";

/** What the bar's trailing hint says, closed and open. */
export const SHOW = "Show";
export const HIDE = "Hide";

/** The states that ALWAYS wait for a person, by the spec's own list. */
export const NEEDS_PERSON_STATES = Object.freeze([
  "waiting_approval",
  "blocked",
  "needs_input",
]);

/** `blocked` in the task feed is the same fact as `waiting_approval` here. */
const NEEDS = new Set(NEEDS_PERSON_STATES);

/** A field as trimmed text, never `undefined`. */
function word(value) {
  return value === undefined || value === null ? "" : String(value).trim();
}

/**
 * A job's status, under either name. `state` wins when a row carries both,
 * because that is the name both of this PC's feeds actually send.
 */
export function jobStatus(job) {
  if (!job || typeof job !== "object") return "";
  return word(job.state) || word(job.status);
}

/**
 * True only when the job is waiting on a person. See the module note for the
 * contract and for why the server's own boolean, when present, wins.
 */
export function waitsForPerson(job) {
  if (!job || typeof job !== "object") return false;
  if (typeof job.waits_for_person === "boolean") return job.waits_for_person;
  const status = jobStatus(job);
  if (NEEDS.has(status)) return true;
  if (status !== "failed") return false;
  // A failure the owner has already put aside is not still asking for him.
  // `=== true` on purpose: a malformed value must never HIDE a failure.
  return job.dismissed_by_owner !== true;
}

/**
 * Stable partition: the jobs that wait for a person, then everything else.
 * Both lists keep the payload's own order - nothing is sorted by time or by
 * severity, so a row never jumps position between two reads of the same
 * answer (the spec's "sorting stable").
 */
export function partitionJobs(jobs) {
  const needs = [];
  const quiet = [];
  for (const job of Array.isArray(jobs) ? jobs : []) {
    (waitsForPerson(job) ? needs : quiet).push(job);
  }
  return { needs, quiet };
}

/** Whole words for an age, the same shape `brain.js`'s `ago()` uses. */
export function agoWords(epochSeconds, nowSeconds) {
  const at = Number(epochSeconds);
  if (!Number.isFinite(at) || at <= 0) return "";
  const now = Number(nowSeconds);
  const seconds = Math.max(0, Math.round(
    (Number.isFinite(now) && now > 0 ? now : Date.now() / 1000) - at,
  ));
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

/**
 * The collapsed bar's ONE line. It says only what the payload supports:
 *
 *   Quiet / healthy · 3 background jobs — 1 still running, 2 finished · last finished 5m ago
 *
 * A count is printed only when it is non-zero, and "last finished" only when
 * a row really carries a finished time. Nothing here claims a watcher is
 * healthy that the PC has not said anything about: the sections are defined
 * by `waitsForPerson`, not by a health guess.
 */
export function quietSummary(jobs, nowSeconds) {
  const list = Array.isArray(jobs) ? jobs : [];
  if (!list.length) return "";
  const counts = { running: 0, done: 0, failed: 0, cancelled: 0 };
  let last = 0;
  for (const job of list) {
    const status = jobStatus(job);
    if (status === "running" || status === "queued") counts.running += 1;
    else if (status === "done") counts.done += 1;
    else if (status === "failed") counts.failed += 1;
    else if (status === "cancelled") counts.cancelled += 1;
    const finished = Number(job && job.finished);
    if (Number.isFinite(finished) && finished > last) last = finished;
  }
  const bits = [];
  if (counts.running) bits.push(`${counts.running} still running`);
  if (counts.done) bits.push(`${counts.done} finished`);
  if (counts.failed) bits.push(`${counts.failed} failed`);
  if (counts.cancelled) bits.push(`${counts.cancelled} cancelled`);
  let line = `${QUIET_HEALTHY} · ${list.length} background job${list.length === 1 ? "" : "s"}`;
  if (bits.length) line += ` — ${bits.join(", ")}`;
  if (last) line += ` · last finished ${agoWords(last, nowSeconds)}`;
  return line;
}
