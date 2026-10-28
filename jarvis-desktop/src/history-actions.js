/**
 * history-actions.js - ONE table of what a History row offers, the words it
 * says, and the two request shapes those actions send.
 *
 * WHY THIS FILE EXISTS. The Gemini ruling of 2026-10-27 (after the owner asked
 * for "both should have pinnable chats, project organization by chat, and
 * more"): the Brain window's History tab and the HUD's History sidebar edit the
 * SAME chats through the SAME routes, so their row actions, their labels and
 * their delete confirmation are held here, once, and both windows read them -
 * the same shape as `hud-actions.js` for a reminder row. A second copy of
 * "Delete this conversation?" or of the keep-the-facts sentence in the HUD is
 * exactly how two windows come to say two things.
 *
 * WHO READS IT.
 *   - `history-view.js` (the Brain's History tab, drawn by `brain.js`) - the
 *     delete question and the delete label.
 *   - `hud-history.js` (the HUD's sidebar, `jarvis_hud.html`) - the whole row
 *     menu, the confirm, and the args/body the writes send.
 *
 * THE PC IS THE AUTHORITY, NOT THIS FILE. The routes, the bodies and the id
 * check are enforced in Rust (`src-tauri/src/brain/history.rs`): `hud_act_body`
 * builds the HUD's request and shares `tag_chat_body` / `delete_body` with the
 * Brain's own commands. The shapes below are only what this window hands that
 * command; the command refuses anything else.
 *
 * NO DOM, NO IMPORTS. Pure data and pure functions, so a Node test (and, later,
 * a generated contract) can compare the two windows without a browser.
 *
 * @module history-actions
 */

/** The owner-facing words for each row action. One spelling, every window. */
export const ACTION_LABELS = Object.freeze({
  open: "Open",
  pin: "Pin chat",
  unpin: "Unpin chat",
  move: "Move to project",
  noTag: "No project",
  delete: "Delete",
  keep: "Keep it",
  newChat: "New chat",
});

/** What a row's menu offers, in the order it is drawn. Pinning is the one
 *  action whose label depends on the row (`labelFor`); `move` opens the tag
 *  list, which is drawn from the PC's own tags and adds nothing here. */
export const ROW_ACTIONS = Object.freeze(["open", "pin", "move", "delete"]);

/** The Brain's question before deleting ONE chat, in pieces so both windows
 *  can say it: `deleteWords` joins them for a `window.confirm`, and the HUD's
 *  menu box reads the same three sentences (it cannot use `window.confirm` - a
 *  webview may not draw one, and a dialog the page cannot see is a delete with
 *  no question at all). */
export const DELETE_QUESTION = "Delete this conversation?";
export const DELETE_REMOVES = "It is removed from this PC. This cannot be undone.";

/** Said with Delete, in both apps (ease-of-use audit 2026-09-27, #7), when
 *  there is nothing to offer: the chat taught no fact still in use, or this PC
 *  cannot list them. The phone's ChatLog.DELETE_KEEPS_FACTS. Since the chat
 *  audit (2026-09-28) it points to "Forget a time frame", not to forgetting
 *  "one by one". */
export const DELETE_KEEPS_FACTS =
  "Deleting a chat does not forget facts Jarvis learned from it. To forget what Jarvis learned " +
  "over some days, use Forget a time frame. Copies in older backups stay until they age out.";

/** The label for one action on one row - "Pin chat" or "Unpin chat" by what the
 *  row already is, everything else fixed. */
export function labelFor(action, pinned) {
  if (action === "pin") return pinned === true ? ACTION_LABELS.unpin : ACTION_LABELS.pin;
  return ACTION_LABELS[action] || "";
}

/** The Brain's whole confirm for deleting one chat, word for word: what is
 *  being deleted, that it cannot be undone, and what it does not forget. */
export function deleteWords(title, note = "") {
  return (
    `${DELETE_QUESTION}\n\n${title || "(no title)"}\n\n` +
    `${DELETE_REMOVES}\n\n${note || DELETE_KEEPS_FACTS}`
  );
}

/** The args ONE write hands `hud_history_act` (the Rust command): the action,
 *  the one chat, and that action's own value - never a route or a body, so a
 *  script in the page cannot aim it at anything else. `null` for anything this
 *  window may not send. */
export function actArgs(action, id, value) {
  const args = { action: String(action || ""), id: String(id || "") };
  if (action === "pin") {
    if (value !== true && value !== false) return null;
    args.pinned = value;
  } else if (action === "tag") {
    if (!(value === null || (typeof value === "number" && Number.isFinite(value) && value > 0))) {
      return null;
    }
    args.tag = value;
  } else if (action !== "delete") {
    return null;
  }
  if (!args.id) return null;
  return args;
}

/** The POST body for the SAME action in a plain browser (no Tauri command to
 *  hand it to) - the routes this page already reads, so a browser HUD pins and
 *  files through the documented shapes rather than a second set of them. */
export function actBody(action, id, value) {
  const args = actArgs(action, id, value);
  if (!args) return null;
  const body = { id: args.id };
  if (action === "pin") body.pinned = args.pinned;
  if (action === "tag") body.tag_id = args.tag;
  return body;
}
