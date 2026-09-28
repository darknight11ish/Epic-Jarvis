/**
 * Settings -> Hardware and models -> PC help (JARVIS-API section 84,
 * backend/jarvis_pc_help.py): five plain answers about this PC - why it is
 * slow, how full the drives are, what is using the graphics card, how hot it
 * is, and when it last restarted. Its real answers are
 * tests/fixtures/pc-help-cases.json.
 *
 * READ-ONLY. Nothing here changes anything, so nothing is held on a stale
 * link and there is no approval card. The PC is asked only when the owner
 * presses "Check now" - one reading takes a couple of seconds - never on a
 * timer. Every sentence is the PC's own (`title`, `words`, `changes`,
 * `private`); the three labels below are the phone's (net/PcHelp.kt) word
 * for word, checked by backend/test_pc_help.py. The answer can name
 * programs: it is shown, never stored or logged here.
 *
 * @module pc-help
 */

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

/** The labels this page adds. The phone's PcHelp.kt has the same words. */
export const PC_HELP = {
  heading: "PC help",
  check: "Check now",
  checking: "Checking your PC…",
};

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 300) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

/**
 * Paint one answer of `get_pc_help` into the list. An older backend's
 * `{available: false, why}` is its sentence; so is anything unreadable.
 */
export function paintPcHelp(answer, list, status) {
  list.replaceChildren();
  if (!answer || answer.available === false || !Array.isArray(answer.sections)) {
    status.textContent = (answer && answer.why) || "Your PC answered, but not in a way this app can read.";
    status.dataset.tone = "warn";
    return;
  }
  delete status.dataset.tone;
  status.textContent = "";
  for (const s of answer.sections) {
    if (!s || typeof s.title !== "string" || typeof s.words !== "string") continue;
    const li = node("li", "pc-help-item");
    li.dataset.id = String(s.id || "");
    li.append(node("strong", "pc-help-title", s.title), node("p", "pc-help-words", s.words));
    list.append(li);
  }
  const notes = [answer.private, answer.changes].filter((t) => typeof t === "string" && t);
  for (const t of notes) list.append(node("li", "pc-help-note note", t));
}

export function startPcHelp() {
  const button = $("pc-help-check");
  const list = $("pc-help-list");
  const status = $("pc-help-status");
  if (!button || !list || !status) return;
  button.textContent = PC_HELP.check;
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    status.textContent = PC_HELP.checking;
    delete status.dataset.tone;
    try {
      if (!IS_TAURI) throw new Error("no desktop backend");
      paintPcHelp(await TAURI.core.invoke("get_pc_help"), list, status);
    } catch (e) {
      list.replaceChildren();
      status.textContent = problemWords(e);
      status.dataset.tone = "warn";
    } finally {
      button.disabled = false;
    }
  });
}

startPcHelp();
