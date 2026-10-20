/**
 * The three calls the Settings questionnaire makes to the PC - and the only
 * file that names the desktop's bridge command or the body fields it sends.
 *
 * Commands (Tauri): ONE command, `setup_questionnaire`, with three verbs:
 *
 *   read   - `GET /api/setup`: the questions, the current values, the last
 *            answers, the last outcomes and the card patience time.
 *   plan   - `POST /api/setup/plan {"answers": {...}}`: READ-ONLY on the PC.
 *            It writes nothing and raises no card, so this page may ask for it
 *            whenever an answer changes.
 *   apply  - `POST /api/setup/apply {"answers": {...}, "confirm": true}`: the
 *            one write. It changes settings through the PC's EXISTING setters,
 *            one at a time, and every loosening change raises its own existing
 *            approval card. `confirm: true` is sent only from
 *            `applySetup()`; `readSetup()` and `planSetup()` never carry it.
 *
 * NOTHING HERE DECIDES, APPROVES OR RETRIES. A refusal is returned as the
 * PC's own words; a card waiting is reported by the answer itself. There is no
 * second post on an error, no retry loop and no timer.
 *
 * The Rust side is `src-tauri/src/setup_questionnaire.rs`; Settings only,
 * through `permissions/surfaces.toml`'s `setup-questionnaire` set. The reason
 * the page holds no route or token is the same as every other card: no desktop
 * page holds the pairing token, and a check that lives only in the webview is
 * not a check.
 *
 * The budgets: the apply can wait for the PC's cards one at a time, so its
 * budget outlasts the Rust command's own 3,600 s timeout - a page that gave up
 * first would say "not known" while a real card can still be answered. The
 * test pins that order.
 *
 * @module setup-bridge
 */
import {
  LATE_ACTION,
  READ_BUDGET_MS,
  withBudget,
} from "./invoke-budget.js";

/** The one Tauri command. */
export const COMMAND = "setup_questionnaire";

/** The verbs it takes. Nothing else reaches it. */
export const VERBS = ["read", "plan", "apply"];

/** One small backend read (the Rust side allows 15 s). */
export const READ_BUDGET = READ_BUDGET_MS;
/** The plan is a read on the PC too, but it walks every answer (Rust: 30 s). */
export const PLAN_BUDGET_MS = 60_000;
/** The apply works through changes one at a time, each waiting on its own
 *  card. The Rust command allows 3,600 s; this is a little longer again, so a
 *  real card can still be answered before the page stops waiting. */
export const APPLY_BUDGET_MS = 3_650_000;

function invoke() {
  const tauri = globalThis.__TAURI__;
  if (!tauri || !tauri.core || !tauri.core.invoke) {
    throw new Error("This window cannot ask the PC.");
  }
  return tauri.core.invoke;
}

function words(error) {
  if (typeof error === "string" && error.trim()) return error.trim();
  if (error && typeof error.message === "string" && error.message.trim()) {
    return error.message.trim();
  }
  return "";
}

/** One command, with a budget and the shared "it is not known" sentence. */
function call(args, ms) {
  const send = invoke();
  return withBudget(send(COMMAND, args), { ms, late: LATE_ACTION });
}

/**
 * The reading (`GET /api/setup`). A bridge that is not there yet, or a
 * backend that has not shipped the route, becomes the reading's own
 * `available: false` line; this never invents a question.
 */
export async function readSetup() {
  try {
    return await call({ action: "read" }, READ_BUDGET);
  } catch (error) {
    return {
      available: false,
      why: words(error) ||
        "This desktop build has no setup questionnaire bridge yet. Update the " +
        "app and the backend.",
    };
  }
}

/**
 * The read-only plan (`POST /api/setup/plan`). `body` is
 * `setup-questionnaire.js`'s `planBody(draft)` - an answers object and nothing
 * else; there is no `confirm` field in it at all.
 */
export async function planSetup(body) {
  try {
    return await call({ action: "plan", answers: body && body.answers }, PLAN_BUDGET_MS);
  } catch (error) {
    return { ok: false, error: words(error) || "The plan could not be read." };
  }
}

/**
 * The ONE write (`POST /api/setup/apply`). Call this from the confirm button
 * and nowhere else: `body` is `setup-questionnaire.js`'s `applyBody(draft)`,
 * which is the only body in this app carrying `confirm: true`.
 *
 * An error is thrown as words for the page's line; it never becomes a second
 * post, and nothing here approves a card.
 */
export async function applySetup(body) {
  return call(
    { action: "apply", answers: body && body.answers, confirm: true },
    APPLY_BUDGET_MS,
  );
}
