/**
 * Settings -> Sending email (the owner's decision of 2026-09-25, after the
 * Muse audit; JARVIS-API.md section 26; backend jarvis_email_send.py,
 * email-send.patch).
 *
 * One line, in the PC's own words: whether Jarvis can send email, from which
 * address and through which server - never the password (the PC sends only
 * whether one is set). Read through `get_email_sending` (email_sending.rs),
 * Settings only. There is nothing to change here: the account is the one
 * email reading already uses, set on the PC, and every email is its own
 * approval card.
 *
 * The phone's Mind -> Sending email shows the same line
 * (EmailSendingPlate.kt, net/EmailSending.kt).
 *
 * @module email-sending-settings
 */

import { onQueue } from "./jarvis-link.js";
import { NOTE, readSending, TITLE } from "./email-sending.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const es = {
  section: $("email-sending"),
  title: $("es-title"),
  note: $("es-note"),
  state: $("es-state"),
  said: $("es-said"),
};

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

let seq = 0;

async function load() {
  if (!IS_TAURI || !es.section) return;
  const mine = ++seq;
  let answer;
  try {
    answer = await TAURI.core.invoke("get_email_sending");
  } catch (error) {
    if (mine !== seq) return;
    es.said.hidden = true;
    es.state.hidden = false;
    es.state.dataset.tone = "bad";
    es.state.textContent = `Jarvis could not be asked whether it can send email. ${problemWords(error)}`;
    return;
  }
  if (mine !== seq) return;
  const v = readSending(answer);
  es.state.hidden = true;
  es.said.hidden = false;
  // textContent: the PC's own words, which name an address and a server.
  es.said.textContent = v.said;
  es.said.dataset.tone = v.ready ? "ok" : "";
}

if (es.section) {
  es.title.textContent = TITLE;
  es.note.textContent = NOTE;
}
// onQueue delivers the current queue at once (the first read), and again
// whenever it changes - a restarted backend, a new setting.
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
