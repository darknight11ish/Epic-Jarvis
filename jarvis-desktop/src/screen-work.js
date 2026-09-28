/**
 * "Jarvis is working on your screen, 0:42 - Stop" (the owner's choice of
 * 2026-09-28; docs/RESEARCH-AUDIT-2026-09-28.md idea 17).
 *
 * The widget shows this one line while an approved Windows screen-control
 * plan runs - Jarvis moving the mouse and typing in another program - with
 * how long it has been going and a Stop button. Stop is the "Stop
 * everything" key, not a second kind of stop (screen_work.rs).
 *
 * What "a plan runs" means is the PC's answer, never a guess here: Rust reads
 * GET /api/task and says whether a `control_computer` task is in its running
 * list (screen_work.rs `read_running`). This file only keeps the clock.
 */

/** The line's words. Plain, and the same everywhere it is quoted. */
export const WORKING_WORDS = "Jarvis is working on your screen";

/** The Stop button's hover text: what it does, and what it does not undo. */
export const STOP_TITLE =
  "Stop everything - the same as the Stop everything key. Jarvis stops before its next step; steps already done stay done.";

/** Said once, to a screen reader, when the line appears. */
export const APPEARED_WORDS = `${WORKING_WORDS}. Press Stop to stop it.`;

/** How often the widget asks the PC while Jarvis reports it is working. */
export const POLL_MS = 2000;

/**
 * The next state of the line from Rust's answer.
 *
 * `prev` is `{ id, since }` or null; `got` is screen_work's
 * `{ running, id, elapsed_ms }`; `now` is Date.now(). The start time is
 * fixed when a plan is first seen and kept for that plan, so the clock never
 * jumps back and forth with each poll. With no trusted time from the PC
 * (`elapsed_ms` null) it counts from when the widget first saw the plan.
 */
export function nextScreenWork(prev, got, now) {
  if (!got || !got.running) return null;
  const id = got.id == null ? "" : String(got.id);
  if (prev && prev.id === id) return prev;
  const elapsed = Number.isFinite(got.elapsed_ms) && got.elapsed_ms >= 0 ? got.elapsed_ms : 0;
  return { id, since: now - elapsed };
}

/** Whole seconds the plan has been running, never negative. */
export function secondsRunning(view, now) {
  if (!view) return 0;
  return Math.max(0, Math.floor((now - view.since) / 1000));
}
