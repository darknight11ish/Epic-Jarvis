/**
 * One budget for every command the desktop windows send.
 *
 * WHY (the Settings freeze of 2026-10-16). The owner pressed "Pair a phone" and
 * the section froze for ever: `devices.js` awaited `TAURI.core.invoke` with no
 * budget of any kind, so a command that never settled left its `busy` flag true,
 * `paint()` kept every control disabled, and the section sat on "Asking your PC
 * for a code…" with nothing said. `settings.js` had a budget, but a private one
 * - an `OPEN_READS` set consulted only by its own `invoke()` - so nothing else
 * in the app could use it, and 100 call sites across 39 files had none.
 *
 * This module is that budget, shared. Every window imports `call` instead of
 * reaching for `TAURI.core.invoke`, so the next card cannot repeat the freeze.
 *
 * THE TWO SENTENCES, and why there are two:
 *
 *   - A late READ only goes stale: the page may be showing an old value.
 *     `LATE_READ` says exactly that, in the words `settings.js` already used.
 *   - A late ACTION is not the same claim. Rust does not cancel a command, so
 *     the PC can finish the work a moment AFTER this page stops waiting: a
 *     pairing session may be live, a backup may have been written. "May be out
 *     of date" would understate that; "it failed" would be a lie the other way.
 *     `LATE_ACTION` says the only true thing left - it is not known - and tells
 *     the owner to look before pressing again.
 *
 * THA BUDGETS, and why they are not all the same. A backup restore is not a
 * status read, and bounding them alike would report "I do not know" on work
 * that is still correctly running.
 *
 *   30 s   - one small backend call. This is `settings.js`'s own budget: the
 *            longest read the PC offers is 10 s, so 30 s can only fire on a
 *            request that is never coming back.
 *   120 s  - a command that goes out to the internet (a tool-update check
 *            reaches package registries), where the network is the wait.
 *   15 min - a command that copies or restores the owner's data, and the one
 *            that raises an approval card and waits for a person. These are
 *            SUPPOSED to take minutes; the budget is only there for a wedged
 *            command, so it must be far above any honest run.
 *
 * Nothing here cancels anything: the work keeps running and its late result is
 * ignored. The race handles both sides, so a late rejection is not unhandled.
 *
 * @module invoke-budget
 */

/** A late READ: the page may be showing something out of date. THE ONLY copy in
 * the tree - `settings.js` and `devices-words.js` import it rather than spelling
 * it again, and `tests/invoke-budget.mjs` fails if either sentence is ever
 * defined twice. It was defined twice before 2026-10-16, in two files that had
 * already stopped agreeing. */
export const LATE_READ =
  "Jarvis has not answered yet, so this part of Settings may be out of date. Try again in a moment.";

/** A late ACTION: it is not known whether it happened - never that it failed.
 *
 * Deliberately names no phone, no list and no backup: this module is imported by
 * every card, so the sentence has to make sense on all of them. It read "Check
 * your phone and the list before trying again" while it lived in
 * `devices-words.js` - true of the Devices card, wrong on a backup card - and
 * "look again" is the part of that advice that is true everywhere. */
export const LATE_ACTION =
  "Jarvis has not answered yet, so it is not known whether it happened. Look again before pressing it a second time.";

/** One small backend call. The page's existing budget, unchanged. */
export const READ_BUDGET_MS = 30_000;
export const ACTION_BUDGET_MS = 30_000;
/** A command whose wait is the internet. */
export const NETWORK_BUDGET_MS = 120_000;
/** A command that copies or restores data, or waits for an approval card. */
export const LONG_BUDGET_MS = 900_000;

/** The preset apply waits for the PC's own switch_model approval card. The PC's
 * gate may wait up to 900 s; the Rust command allows 1,200 s, so the page's
 * budget is a little longer still (1,250 s). It must outlast the card, or the
 * page would claim the result is unknown while a real card can still be
 * answered. */
export const APPLY_BUDGET_MS = 1_250_000;

/** A command that really works for minutes - see LONG_BUDGET_MS. */
const LONG = new Set([
  "backup_now",        // copies every database the owner has
  "restore_backup",    // rewrites them, and waits on an approval card first
  "delete_older_backups",
  "set_backup_folder", // a native folder picker: the owner may take minutes
]);

/** A command whose wait is the network. */
const NETWORK = new Set([
  "check_tool_updates",
]);

/** How long `command` gets, given whether it is a read or an action. */
export function budgetFor(command, kind = "read") {
  if (command === "apply_focus_preset") return APPLY_BUDGET_MS;
  if (LONG.has(command)) return LONG_BUDGET_MS;
  if (NETWORK.has(command)) return NETWORK_BUDGET_MS;
  return kind === "action" ? ACTION_BUDGET_MS : READ_BUDGET_MS;
}

/** The sentence for a late `command` of this kind. */
export function lateWords(kind = "read") {
  return kind === "action" ? LATE_ACTION : LATE_READ;
}

/**
 * A request that must answer. `work` keeps running and its late result is
 * ignored; `late` is what is thrown when it does not come back in `ms`.
 */
export function withBudget(work, { ms = READ_BUDGET_MS, late = LATE_READ } = {}) {
  let bell = 0;
  const gone = new Promise((_, fail) => {
    bell = setTimeout(() => fail(new Error(late)), ms);
  });
  return Promise.race([work, gone]).finally(() => clearTimeout(bell));
}

/** The bridge, read at call time - the harness installs it before the page. */
function bridge() {
  const tauri = globalThis.__TAURI__;
  if (!tauri || !tauri.core || !tauri.core.invoke) throw new Error("no desktop backend");
  return tauri.core.invoke;
}

/**
 * Send one command with a budget. `kind` is "read" (the default) or "action";
 * it chooses the sentence, never the size - `budgetFor` owns the size.
 */
export function call(command, args = {}, kind = "read") {
  const invoke = bridge();
  return withBudget(invoke(command, args), {
    ms: budgetFor(command, kind),
    late: lateWords(kind),
  });
}
