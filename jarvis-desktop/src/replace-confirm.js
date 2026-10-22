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

/**
 * Review ruling 8.1 (2026-10-21): the heading is not one generic sentence any
 * more. The PC sends the category and its own words on every row
 * (`replaces_kind`, `replaces_heading`, `replaces_note`, from
 * `jarvis_gate.replaces_words_for()`), so a card can never claim a deletion
 * when a recoverable copy is kept, nor promise a kept copy when there is none.
 * These three are the OLDER-PC fallback (a row with `replaces: true` but no
 * words yet), chosen by the category - the generic `REPLACES_WARNING` stays
 * for a card that says it replaces data but gives no category at all.
 */
export const REPLACE_HEADINGS = {
  deletes_data: "DELETES OR REPLACES DATA",
  overwrites_note: "OVERWRITES EXISTING NOTE",
  replaces_code_or_state: "REPLACES LIVE CODE OR STATE",
};

/** The heading this card draws: the PC's own words, else the category's. */
export function replacesHeading(approval) {
  if (!isReplaceCard(approval)) return "";
  const heading = typeof approval.replacesHeading === "string"
    ? approval.replacesHeading : "";
  if (heading) return heading;
  const kind = typeof approval.replacesKind === "string"
    ? approval.replacesKind : "";
  return REPLACE_HEADINGS[kind] || REPLACES_WARNING;
}

/** The honest one-line consequence this card draws. */
export function replacesNote(approval) {
  if (!isReplaceCard(approval)) return "";
  const note = typeof approval.replacesNote === "string"
    ? approval.replacesNote : "";
  return note || REPLACES_NOTE;
}

/**
 * The client-side FLOOR for the actions whose card replaces or deletes data
 * already on the PC.
 *
 * The PC's own `replaces` field is the authority and can ADD an action; this
 * list can never be used to SUBTRACT one. A row that says `replaces: false`
 * for an action in this list still takes the second press, and so does a row
 * with no field at all (an older PC during a partial deploy) - the failure
 * direction is always the extra press, never the silent one.
 *
 * The owner extended the guard on 2026-10-21 ("Extend the two-press guard to
 * them") to the other irreversible data-changing actions the pre-merge audit
 * named; the backend's `_REPLACES_ACTIONS` is the same set, and
 * `jarvis-backend/jarvis_gate.py`'s `_RISK` table says why each one is
 * state-changing (`no` or `hard` reversibility, local reach).
 */
const FALLBACK_ACTIONS = new Set([
  "restore_backup",
  "register_approval_key",
  "memory_forget_range",
  "delete_file",
  "delete_joplin_note",
  "delete_logseq_page",
  "edit_joplin_note",
  "edit_logseq_page",
  "modify_own_code",
  "app_merge_change",
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
