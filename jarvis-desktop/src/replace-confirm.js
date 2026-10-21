/**
 * replace-confirm.js - the second, explicit confirmation on cards that
 * REPLACE what is already on this PC.
 *
 * WHY (the owner's incident, 2026-10-20). One "approve all" click approved
 * three backup restores, two imports and a device-key registration. Those
 * cards stack up and then are walked by muscle memory, and the existing
 * "heavy card" guard (`heavy-approve.js`) does not slow them down: it keys on
 * a card that cannot be undone or leaves the PC, while `restore_backup` and
 * `register_approval_key` are both classified reversible-and-local. The
 * review the owner accepted (ruling 8.2 of
 * FOR-GEMINI-COMPREHENSIVE-REVIEW-2026-10-20-LATE) therefore asks for a
 * mechanical guard on the state-REPLACING cards themselves.
 *
 * WHAT IT DOES. For those cards only - `restore_backup`,
 * `register_approval_key`, `memory_forget_range`, and the voice-training clear
 * (a `change_own_config` card its own module marks) - the card carries a plain
 * "REPLACES CURRENT DATA" heading, and Approve takes TWO presses: the first
 * one arms it and says what the second press will do; only the second one
 * sends the approval. Deny is never touched: refusing is always the safe
 * direction, and costing a retry is the point of a guard.
 *
 * WHERE THE FLAG COMES FROM. The PC puts `replaces` on every waiting card
 * (`jarvis_gate.pending()`, `backend/gate-touches.patch`), so the backend and
 * both apps agree on the set and no app invents its own list. The fallback
 * for an OLDER PC, whose rows carry no such field, is the three action names
 * below - never a guessed default: an unknown card is ordinary, exactly as it
 * was before this file existed, and the phone/desktop never see a card they
 * cannot classify flagged by accident.
 *
 * The one copy of the words: `REPLACES_WARNING` is the heading,
 * `REPLACES_NOTE` the sentence under it. The HUD window's own page
 * (`jarvis_hud.html`) cannot import modules and carries the same two strings
 * inline; `tests/replace-confirm.mjs` holds the three surfaces together.
 */

/** The plain heading on a state-replacing card. Words, not colour alone. */
export const REPLACES_WARNING = "REPLACES CURRENT DATA";

/** What the first Approve press says, before anything is sent. */
export const REPLACES_NOTE =
  "Approving this replaces what is there now. Press Approve again to confirm.";

/** The fallback for a PC too old to send `replaces` (see the module comment). */
const FALLBACK_ACTIONS = new Set([
  "restore_backup",
  "register_approval_key",
  "memory_forget_range",
]);

/**
 * Does deciding this card replace or delete what is already on the PC?
 *
 * `approval.replaces === true` is the PC's own answer and always wins. When
 * the field is absent (an older backend) the three real action names are
 * recognised here; the voice-training clear needs the field because it shares
 * `change_own_config` with ordinary voice-settings cards. `false` - ordinary -
 * is the untouched behaviour, so a missing/unknown card behaves exactly as it
 * did before this guard existed.
 */
export function isReplaceCard(approval) {
  if (!approval || typeof approval !== "object") return false;
  if (approval.replaces === true) return true;
  const action = typeof approval.action === "string" ? approval.action : "";
  return FALLBACK_ACTIONS.has(action);
}

/** The Approve button's own words while a card is armed. */
export function approveLabel(approval, armed) {
  return isReplaceCard(approval) && armed ? "Confirm replace" : "Approve";
}

/**
 * Tracks the two-step press for ONE card at a time.
 *
 * A new card always starts unarmed, and a re-render of the SAME card never
 * changes the arm (the queue resyncs every few seconds; restarting the guard
 * on each repaint would make it impossible to confirm). Nothing here decides
 * anything: `press()` only says whether THIS press is the confirming one.
 */
export class ReplaceGate {
  constructor() {
    this._id = null;
    this._armed = false;
  }

  /** True while the current card is waiting for its confirming press. */
  get armed() {
    return this._armed;
  }

  /** Start watching `approval`; a different card always starts unarmed. */
  sync(approval) {
    const id = approval && approval.id != null ? String(approval.id) : null;
    if (id !== this._id) {
      this._id = id;
      this._armed = false;
    }
    return isReplaceCard(approval);
  }

  /**
   * One press on Approve. Returns `true` when this press may send the
   * approval; `false` when it only armed the card (nothing was sent).
   */
  press() {
    if (!this._armed) {
      this._armed = true;
      return false;
    }
    return true;
  }

  /** Forget the arm (the card closed, or a decision is already on its way). */
  reset() {
    this._armed = false;
  }
}
