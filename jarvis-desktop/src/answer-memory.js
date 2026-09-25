/**
 * The quickbar's temporary chat and "Used in this answer" - the owner's
 * decisions of 2026-09-25 (JARVIS-API.md sections 4, 6 and 18.1). The words
 * and the reading of the PC's answers are memory-used.js; this draws them.
 *
 * main.js owns the conversation and the stream. It calls:
 *   - `temporary.toggle()` from the button; `temporary.on` is read by send()
 *     for the request's `temporary` flag; `temporary.paint(empty)` whenever
 *     the conversation empties or fills.
 *   - `answer.begin(sentTemporary)` when a question is sent,
 *     `answer.route(route)` with the route line, `answer.finish(done)` when
 *     the stream ends, `answer.clear()` with the card, and
 *     `answer.linkChanged()` on every link change (Forget and Erase are held
 *     on a stale link - here greyed, and refused in Rust).
 *
 * Nothing here decides anything about memory: every write is ONE fact, the
 * Brain's own command, after the confirm both apps use.
 *
 * @module answer-memory
 */
import {
  hiddenLine,
  missingLine,
  NOT_CURRENT_MARK,
  NOT_CURRENT_TITLE,
  PINNED_MARK,
  PINNED_MARK_TITLE,
  readUsed,
  REMEMBER_OFF,
  rowActions,
  TEMPORARY_ENDED,
  TEMPORARY_LINE,
  TEMPORARY_NOT_CONFIRMED,
  TEMPORARY_OFF_TITLE,
  TEMPORARY_ON_TITLE,
  TEMPORARY_STARTED,
  TEMPORARY_UNAVAILABLE,
  temporaryOutcome,
  USED_LINE_TITLE,
  USED_TITLE,
  usedIds,
  usedLine,
} from "./memory-used.js";
import {
  ERASE_LABEL,
  ERASE_TITLE,
  ERASED,
  erasedLine,
  eraseQuestion,
  FORGOTTEN,
  forgetQuestion,
} from "./auto-learn.js";

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

const errorText = (e) => String((e && e.message) || e || "It did not work.");

/** Forget and Erase while the event stream is stale (rule 4). */
export const STALE_TITLE = "The event stream is stale, so this cannot be confirmed live.";

/**
 * The temporary-chat toggle and the marker strip.
 *
 * `check()` resolves true only when the PC says it can hold a temporary
 * chat (commands.rs temporary_chat_available); `restart()` starts a new
 * conversation (main.js), so nothing said in one kind of chat is re-sent in
 * the other; `busy()` is true while an answer is arriving.
 */
export function createTemporaryToggle({ button, strip, line, refused, root, check, restart,
  busy, announce, onChange }) {
  const t = {
    on: false,
    checking: false,
    async toggle() {
      if (t.checking || busy()) return;
      if (t.on) {
        t.on = false;
        refused.hidden = true;
        restart();
        announce(TEMPORARY_ENDED);
        t.paint(true);
        return;
      }
      t.checking = true;
      button.disabled = true;
      let ok = false;
      let why = TEMPORARY_UNAVAILABLE;
      try {
        ok = (await check()) === true;
      } catch (error) {
        why = errorText(error);
      }
      t.checking = false;
      button.disabled = false;
      if (!ok) {
        // Never pretend: the mode stays off and says why.
        refused.textContent = why;
        refused.hidden = false;
        strip.hidden = false;
        strip.dataset.state = "refused";
        announce(why, "assertive");
        onChange();
        return;
      }
      t.on = true;
      refused.hidden = true;
      restart();
      announce(TEMPORARY_STARTED);
      t.paint(true);
    },
    /** `empty`: the conversation has nothing in it yet - the one line. */
    paint(empty) {
      // A refusal is said until the next question is asked.
      if (!empty) refused.hidden = true;
      button.setAttribute("aria-pressed", String(t.on));
      button.title = t.on ? TEMPORARY_OFF_TITLE : TEMPORARY_ON_TITLE;
      root.dataset.temporary = String(t.on);
      if (t.on) {
        strip.dataset.state = "on";
        strip.hidden = false;
        line.textContent = empty ? TEMPORARY_LINE : "";
        line.hidden = !empty;
      } else if (refused.hidden) {
        strip.hidden = true;
        line.textContent = "";
      }
      onChange();
    },
  };
  return t;
}

/**
 * "Used N memories" under the answer, and the temporary-chat notes.
 *
 * `invoke(command, args)` rejects on failure (main.js invokeStrict);
 * `isStale()` is the event stream's staleness; `confirm(question)` is the
 * window's own confirm.
 */
export function createAnswerMemory({ box, lineButton, list, note, invoke, isStale, confirm,
  announce, onChange }) {
  const a = {
    ids: [],
    count: 0,
    sentTemporary: false,
    route: null,
    done: false,
    open: false,
    view: null,
    error: "",
    notice: "",
    loading: false,
    buttons: new Set(),
  };

  function clear() {
    a.ids = [];
    a.count = 0;
    a.route = null;
    a.done = false;
    a.open = false;
    a.view = null;
    a.error = "";
    a.notice = "";
    a.buttons.clear();
    box.hidden = true;
    list.hidden = true;
    list.replaceChildren();
    note.hidden = true;
    note.textContent = "";
    lineButton.setAttribute("aria-expanded", "false");
  }

  function paintNote() {
    const lines = [];
    const outcome = temporaryOutcome(a.sentTemporary, a.route);
    if (a.done && outcome === "unconfirmed") lines.push(TEMPORARY_NOT_CONFIRMED);
    if (a.route && a.route.remember_off === true) lines.push(REMEMBER_OFF);
    note.textContent = lines.join(" ");
    note.hidden = !lines.length;
    note.dataset.tone = outcome === "unconfirmed" ? "warn" : "quiet";
  }

  function paintLine() {
    // Only on a finished answer, and never on a temporary one: it used none.
    const show = a.done && a.ids.length > 0 && !a.sentTemporary;
    box.hidden = !show;
    if (!show) return;
    lineButton.textContent = usedLine(a.count);
    lineButton.title = USED_LINE_TITLE;
    lineButton.setAttribute("aria-expanded", String(a.open));
  }

  function actionButton(label, title, fn, danger) {
    const b = el("button", `text-button${danger ? " danger" : ""}`, label);
    b.type = "button";
    b.dataset.title = title;
    b.addEventListener("click", () => fn(b));
    a.buttons.add(b);
    syncButton(b);
    return b;
  }

  function syncButton(b) {
    const stale = isStale();
    b.disabled = stale || b.dataset.busy === "true";
    b.title = stale ? STALE_TITLE : b.dataset.title;
  }

  async function write(button, command, f, question, done) {
    if (isStale() || !confirm(question(f))) return;
    button.dataset.busy = "true";
    syncButton(button);
    try {
      const out = await invoke(command, { id: Number(f.id) });
      if (out && out.ok === false) throw new Error(out.error || out.reason || "Refused.");
      announce(done);
      await load();
      a.notice = done;
      paintList();
    } catch (error) {
      button.dataset.busy = "false";
      syncButton(button);
      a.error = errorText(error);
      paintList();
    }
  }

  function row(f) {
    const item = el("li", "answer-used-item");
    item.dataset.id = String(f.id);
    if (f.erasedAt) {
      item.append(el("span", "answer-used-text erased", erasedLine(f.erasedAt)));
    } else {
      item.append(el("span", "answer-used-text", f.text || "(no words)"));
    }
    const marks = el("span", "answer-used-marks");
    if (f.pinned) {
      const m = el("span", "answer-used-mark", PINNED_MARK);
      m.title = PINNED_MARK_TITLE;
      marks.append(m);
    }
    if (!f.current && !f.erasedAt) {
      const m = el("span", "answer-used-mark", NOT_CURRENT_MARK);
      m.title = NOT_CURRENT_TITLE;
      marks.append(m);
    }
    if (marks.childNodes.length) item.append(marks);
    const acts = rowActions(f);
    const buttons = el("span", "answer-used-actions");
    if (acts.forget) {
      buttons.append(actionButton("Forget", "Stop this being recalled. There is no undo.",
        (b) => write(b, "brain_memory_forget", f, forgetQuestion, FORGOTTEN), true));
    }
    if (acts.erase) {
      buttons.append(actionButton(ERASE_LABEL, ERASE_TITLE,
        (b) => write(b, "brain_memory_erase", f, eraseQuestion, ERASED), true));
    }
    if (buttons.childNodes.length) item.append(buttons);
    return item;
  }

  function paintList() {
    a.buttons.clear();
    list.replaceChildren();
    list.hidden = !a.open;
    if (!a.open) return onChange();
    list.append(el("p", "answer-used-title", USED_TITLE));
    const v = a.view;
    if (a.loading && !v) {
      list.append(el("p", "answer-used-empty", "Reading…"));
    } else if (!v) {
      list.append(el("p", "answer-used-empty failed",
        `Could not read these facts: ${a.error || "no answer"}`));
    } else if (!v.available) {
      list.append(el("p", "answer-used-empty", v.why));
    } else if (v.hidden) {
      list.append(el("p", "answer-used-empty", hiddenLine(v.hiddenCount || a.ids.length)));
    } else {
      const ul = el("ul", "answer-used-rows");
      for (const f of v.facts) ul.append(row(f));
      list.append(ul);
      const gone = missingLine(v.missing.length);
      if (gone) list.append(el("p", "answer-used-empty", gone));
      if (a.notice) list.append(el("p", "answer-used-done", a.notice));
      if (a.error) list.append(el("p", "answer-used-empty failed", a.error));
    }
    onChange();
  }

  async function load() {
    a.loading = true;
    a.error = "";
    a.notice = "";
    paintList();
    try {
      a.view = readUsed(await invoke("memory_used", { ids: a.ids }));
    } catch (error) {
      a.view = null;
      a.error = errorText(error);
    } finally {
      a.loading = false;
    }
    paintList();
  }

  lineButton.addEventListener("click", async () => {
    a.open = !a.open;
    paintLine();
    if (a.open) await load();
    else paintList();
  });

  return {
    begin(sentTemporary) {
      clear();
      a.sentTemporary = Boolean(sentTemporary);
    },
    route(route) {
      a.route = route && typeof route === "object" ? route : null;
      a.ids = usedIds(a.route);
      // The facts the line opens: the ones with an id. (A fact from the
      // older word list over the jsonl has none, and cannot be listed.)
      a.count = a.ids.length;
      paintNote();
      paintLine();
    },
    finish(done) {
      a.done = Boolean(done);
      paintNote();
      paintLine();
      onChange();
    },
    clear() {
      clear();
      a.sentTemporary = false;
      onChange();
    },
    linkChanged() {
      for (const b of a.buttons) syncButton(b);
    },
    /** For tests and main.js: what is shown. */
    get state() {
      return { ids: [...a.ids], open: a.open, sentTemporary: a.sentTemporary };
    },
  };
}
