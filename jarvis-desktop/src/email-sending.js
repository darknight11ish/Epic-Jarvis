/**
 * Sending email (the owner's decision of 2026-09-25, after the Muse audit;
 * JARVIS-API.md section 26; backend jarvis_email_send.py, email-send.patch).
 *
 * Jarvis may send an email from the owner's own account, ONE approval card
 * per email, the card showing the recipients, the subject and every word.
 * This module holds what the desktop needs for that, with no DOM:
 *
 *  - how an email's card is recognised and read WORD FOR WORD (the Jarvis
 *    bar shows it in a <pre>, never as Markdown - Markdown would turn
 *    `[words](link)` into "words" and hide where the link goes);
 *  - the widget's words: an email is approved in the Jarvis bar, where all
 *    of it can be read, never from the widget's one line (Rust holds the
 *    same rule in commands.rs, `waiting_email`);
 *  - the Settings line: `get_email_sending` (email_sending.rs) reads
 *    GET /api/email/sending, and the PC's own `said` is shown as it is -
 *    the phone shows the same words (net/EmailSending.kt).
 *
 * @module email-sending
 */

/** The gate action every email is asked under (jarvis_email_send.ACTION). */
export const SEND_EMAIL_ACTION = "send_email";

/**
 * The gate action every draft is asked under (jarvis_email_draft.ACTION;
 * JARVIS-API.md section 40). A draft's card shows the same whole-email
 * shape (From, To, Cc, Subject, the WHOLE text) as sending's, so it needs
 * the same never-Markdown, never-widget-approve treatment - `isEmailCard`
 * below recognises both.
 */
export const DRAFT_EMAIL_ACTION = "draft_email";

export const TITLE = "Sending email";

/** Settings' explanation, the same words as the phone's. */
export const NOTE =
  "Jarvis can send an email from your own account, but only after you have read all of it " +
  "on an approval card and said yes - one card per email, and there is no \"always allow\". " +
  "It uses the same account as reading email, set up on the PC.";

/** What a PC without jarvis_email_send.py says (Rust SENDING_MISSING). */
export const MISSING = "Your PC's Jarvis cannot send email yet - run apply-patches.ps1 on the PC.";

/** The widget's line for an email card, and its Approve button. */
export const EMAIL_DETAIL = "An email - open the Jarvis bar to read all of it before approving.";
export const EMAIL_APPROVE = "Read it in the Jarvis bar";

/** Whether a card is an email - sent, or a draft (both show the whole text
 * word for word and must never be Markdown-rendered or approved from the
 * widget's one line). */
export function isEmailCard(approval) {
  return Boolean(approval)
    && (approval.action === SEND_EMAIL_ACTION || approval.action === DRAFT_EMAIL_ACTION);
}

/**
 * The card's text, unrendered: `detail.text` (what the chat loop puts on
 * every card), or `detail` itself when it arrived as a string (cut off by
 * the gate - the PC refuses an email whose card would be), or the prompt.
 */
export function approvalPlainText(approval) {
  const detail = approval && approval.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && typeof detail.text === "string" && detail.text.trim()) {
    return detail.text;
  }
  const prompt = approval && typeof approval.prompt === "string" ? approval.prompt : "";
  return prompt.trim() ? prompt : "No detail was recorded for this action.";
}

/**
 * GET /api/email/sending, as `get_email_sending` hands it back: the PC's own
 * line, whether it is ready, and a tone for the line. A PC without the
 * route says so in MISSING's words.
 */
export function readSending(answer) {
  if (!answer || typeof answer !== "object" || answer.available === false) {
    const said = answer && typeof answer.said === "string" && answer.said.trim()
      ? answer.said.trim()
      : MISSING;
    return { available: false, ready: false, said, tone: "warn" };
  }
  const said = typeof answer.said === "string" ? answer.said.trim() : "";
  const ready = answer.ready === true;
  return {
    available: true,
    ready,
    said: said || MISSING,
    state: typeof answer.state === "string" ? answer.state : "",
    tone: ready ? "ok" : "warn",
  };
}
