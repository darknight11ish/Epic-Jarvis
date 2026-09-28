/**
 * Brain -> Memory -> "Bring in old chats" (JARVIS-API section 85; backend
 * jarvis_history_import.py and import_history.py; Rust
 * brain/history_import.rs).
 *
 * The owner picks a ChatGPT, Claude, Gemini or DeepSeek export on this PC (the Windows
 * "Open" dialog runs in Rust - this window gets no file access), and the PC
 * reads the owner's OWN messages in the background and PROPOSES facts.
 * Every one lands under "Waiting for you" as its own card: nothing is saved
 * by itself, and there is no approve-all. While a run is going this page
 * asks the PC where it is every POLL_MS, and only while the Memory tab is
 * showing; it shows the PC's own sentence (counts only - never the file's
 * name or a word of a chat).
 *
 * Start is held on a stale link (rule 4) - Rust refuses too. Stop never is:
 * it only makes Jarvis do less.
 *
 * The phone has no button for this (ARCHITECTURE.md section 8): the export
 * is a file on the PC. The cards it makes show in the phone's review queue
 * like any other.
 *
 * @module history-import
 */

/** How often a running import is asked about, while the Memory tab shows. */
export const POLL_MS = 2000;

/** The words this page shows. ABOUT is the PC's own (jarvis_history_import.ABOUT). */
export const HISTORY_IMPORT = {
  title: "Bring in old chats",
  start: "Bring in chats from ChatGPT, Claude, Gemini or DeepSeek",
  again: "Choose a file and carry on",
  stop: "Stop",
  stopping: "Stopping…",
  choosing: "Choose the export file…",
  about: "Jarvis reads only what you wrote in those chats - never the other assistant's " +
    "replies - on this PC, with the AI model on this PC. Every possible fact waits under " +
    "“Waiting for you” for your yes, one at a time; nothing is saved by itself. " +
    "The chats are not added to your History. It can take hours for a big export, and " +
    "Jarvis may answer more slowly while it runs.",
  how: "How to get the file: in ChatGPT, Settings, Data controls, Export data - an email " +
    "brings a link to a .zip. In Claude, Settings, Privacy, Export data. For Gemini, " +
    "Google Takeout (takeout.google.com) with only “My Activity”, Gemini Apps, " +
    "chosen, and JSON as its format. In DeepSeek, Settings, Data, Export data. " +
    "Save the .zip on this PC, then choose it here. " +
    "Nothing is uploaded.",
  missing: "Your PC's Jarvis cannot bring in old chats yet - run apply-patches.ps1 on the PC.",
  unreadable: "Your PC answered, but not in a way this app can read.",
  notHere: "Old chats are brought in on the PC only: the export file is on the PC " +
    "(Brain, Memory).",
};

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 300) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

/**
 * What the card shows for one answer of `history_import_status`: the
 * sentence, and which buttons. Pure, for the tests.
 */
export function importView(answer) {
  if (!answer || typeof answer !== "object") {
    return { words: HISTORY_IMPORT.unreadable, tone: "warn", running: false,
             canStart: false, canStop: false, waiting: 0, available: false };
  }
  if (answer.available === false) {
    return { words: String(answer.why || HISTORY_IMPORT.missing), tone: "warn",
             running: false, canStart: false, canStop: false, waiting: 0, available: false };
  }
  if (typeof answer.state !== "string" || typeof answer.words !== "string") {
    return { words: HISTORY_IMPORT.unreadable, tone: "warn", running: false,
             canStart: false, canStop: false, waiting: 0, available: false };
  }
  const running = answer.state === "running" || answer.state === "stopping";
  const here = answer.here !== false;
  const paused = answer.outcome === "queue_full" || answer.outcome === "cancelled"
    || answer.outcome === "no_model";
  return {
    words: here || running ? answer.words : HISTORY_IMPORT.notHere,
    tone: answer.outcome === "failed" || answer.outcome === "not_export"
      || answer.outcome === "empty" || answer.outcome === "no_model" ? "warn" : "",
    running,
    canStart: !running && here,
    canStop: answer.state === "running",
    startLabel: paused ? HISTORY_IMPORT.again : HISTORY_IMPORT.start,
    waiting: Number(answer.waiting) || 0,
    available: true,
  };
}

/**
 * Wire the card. `deps`: `invoke`, `canAct()` (the link is live),
 * `showing()` (the Memory tab is in front), `say(text, tone)` (a toast),
 * `onWaiting()` (new cards were made: re-read "Waiting for you").
 * Returns `{ refresh, sync }`: `sync` re-greys Start after a link change.
 */
export function mountHistoryImport(els, deps) {
  const { words, start, stop } = els;
  let view = null;
  let timer = null;
  let lastWaiting = 0;
  let reading = false;

  const paint = () => {
    const v = view || importView(null);
    words.textContent = v.words;
    if (v.tone) words.dataset.tone = v.tone;
    else delete words.dataset.tone;
    start.hidden = !v.available || v.running;
    stop.hidden = !v.running;
    stop.disabled = !v.canStop;
    stop.textContent = v.canStop || !v.running ? HISTORY_IMPORT.stop : HISTORY_IMPORT.stopping;
    start.textContent = v.startLabel || HISTORY_IMPORT.start;
    sync();
  };

  function sync() {
    const live = deps.canAct();
    const v = view;
    start.disabled = start.dataset.busy === "true" || !live || !v || !v.canStart;
    start.title = live ? "" : "Waiting for the link to catch up. Nothing can be sent until it does.";
  }

  const schedule = () => {
    clearTimeout(timer);
    timer = null;
    if (!view || !view.running) return;
    timer = setTimeout(() => {
      timer = null;
      if (deps.showing()) refresh();
      else schedule();
    }, POLL_MS);
  };

  const take = (answer) => {
    view = importView(answer);
    if (view.waiting !== lastWaiting) {
      if (view.waiting > lastWaiting && deps.onWaiting) deps.onWaiting();
      lastWaiting = view.waiting;
    }
    paint();
    schedule();
  };

  async function refresh() {
    if (reading) return;
    reading = true;
    try {
      take(await deps.invoke("history_import_status"));
    } catch (error) {
      view = { words: problemWords(error), tone: "warn", running: false, canStart: true,
               canStop: false, waiting: lastWaiting, available: true };
      paint();
    } finally {
      reading = false;
    }
  }

  start.addEventListener("click", async () => {
    if (!deps.canAct()) return;
    start.dataset.busy = "true";
    sync();
    words.textContent = HISTORY_IMPORT.choosing;
    try {
      const out = await deps.invoke("history_import_start");
      if (out && out.cancelled) {
        paint();
        return;
      }
      lastWaiting = 0;
      take(out);
    } catch (error) {
      deps.say(problemWords(error), "bad");
      paint();
    } finally {
      start.dataset.busy = "false";
      sync();
    }
  });

  stop.addEventListener("click", async () => {
    stop.disabled = true;
    stop.textContent = HISTORY_IMPORT.stopping;
    try {
      take(await deps.invoke("history_import_cancel"));
    } catch (error) {
      deps.say(problemWords(error), "bad");
      refresh();
    }
  });

  paint();
  return { refresh, sync };
}
