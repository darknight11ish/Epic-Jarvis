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
  isOpenable,
  missingLine,
  NOT_CURRENT_MARK,
  NOT_CURRENT_TITLE,
  PINNED_MARK,
  PINNED_MARK_TITLE,
  QUOTE_WARNING_LABEL,
  QUOTE_WARNING_TITLE,
  readSources,
  readUsed,
  REMEMBER_OFF,
  rowActions,
  SOURCES_LINE,
  SOURCES_LINE_TITLE,
  SOURCES_TITLE,
  sourceLine,
  TEMPORARY_ENDED,
  TEMPORARY_LINE,
  TEMPORARY_NOT_CONFIRMED,
  TEMPORARY_OFF_TITLE,
  TEMPORARY_ON_TITLE,
  TEMPORARY_STARTED,
  TEMPORARY_UNAVAILABLE,
  GAME_TEMPORARY,
  temporaryOutcome,
  USED_LINE_TITLE,
  USED_TITLE,
  usedIds,
  usedLine,
} from "./memory-used.js";
import { whenLine } from "./history-view.js";
import {
  eraseAlsoChatNamedConfirm,
  ERASED_NO_CHAT,
  otherFactsInChat,
  readFactChat,
  ERASE_ALSO_CHAT_CONFIRM,
  ERASE_LABEL,
  ERASE_TITLE,
  ERASED,
  ERASED_AND_CHAT_DELETED,
  erasedLine,
  eraseQuestion,
  FORGOTTEN,
  forgetQuestion,
} from "./auto-learn.js";
import { DONE_LINE } from "./coming-up.js";
import { leftOutLine, WORDS as TOPIC_WORDS } from "./topics.js";

/** The strip's line: the label beside it already says "Temporary chat". */
const TEMPORARY_STRIP_LINE = TEMPORARY_LINE.replace(/^Temporary chat:\s*/, "");
/** A game or role-play the PC made temporary by itself. */
const GAME_STRIP_LINE = "This looks like a game, so nothing in it is kept or learned.";

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

const errorText = (e) => String((e && e.message) || e || "It did not work.");

/** Forget and Erase while the event stream is stale (rule 4). */
export const STALE_TITLE = "The event stream is stale, so this cannot be confirmed live.";

/** The shape every `turn_id` is - `jarvis_feedback._TURN` on the PC,
 *  `commands::valid_turn_id` in Rust. Checked here too so a malformed or
 *  missing id never even tries the round trip. */
const TURN_ID_RX = /^[0-9a-f]{32}$/;

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
    /** The PC made this conversation temporary by itself: a game or
     *  role-play (the route header said so). The strip says so too - it used
     *  to be one small quiet line under the answer. */
    game: false,
    checking: false,
    setGame(value) {
      t.game = Boolean(value);
      t.paint(t.game ? false : true);
    },
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
        // The label already says "Temporary chat": the line does not repeat it.
        line.textContent = empty ? TEMPORARY_STRIP_LINE : "";
        line.hidden = !empty;
      } else if (t.game) {
        strip.dataset.state = "game";
        strip.hidden = false;
        line.textContent = GAME_STRIP_LINE;
        line.hidden = false;
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
 * window's own confirm. `sources` (optional; feasibility I42/I132, "Where
 * this came from") is `{box, lineButton, list}`, the same three-part shape
 * as the memory ones above - omit it and this behaves exactly as before.
 */
export function createAnswerMemory({ box, lineButton, list, note, invoke, isStale, confirm,
  announce, onChange, sources, onChatDeleted = null }) {
  const a = {
    ids: [],
    count: 0,
    sentTemporary: false,
    game: false,
    route: null,
    done: false,
    open: false,
    view: null,
    error: "",
    notice: "",
    loading: false,
    buttons: new Set(),
    // "Where this came from" (I42/I132): fetched once, quietly, as soon as
    // the answer finishes - there is no cheap count to show first (see
    // memory-used.js's own note on why). `srcOpen` only controls whether
    // the LIST is expanded; the line itself appears as soon as `srcView`
    // has something to show.
    turnId: null,
    srcView: null,
    srcError: "",
    srcLoading: false,
    srcOpen: false,
  };
  const src = sources || {};

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
    a.turnId = null;
    a.srcView = null;
    a.srcError = "";
    a.srcLoading = false;
    a.srcOpen = false;
    if (src.box) src.box.hidden = true;
    if (src.list) {
      src.list.hidden = true;
      src.list.replaceChildren();
    }
    if (src.lineButton) src.lineButton.setAttribute("aria-expanded", "false");
  }

  function paintNote() {
    const lines = [];
    const outcome = temporaryOutcome(a.sentTemporary, a.route);
    if (a.done && outcome === "unconfirmed") lines.push(TEMPORARY_NOT_CONFIRMED);
    if (outcome === "game") lines.push(GAME_TEMPORARY);
    if (a.route && a.route.remember_off === true) lines.push(REMEMBER_OFF);
    // Topic controls: how many facts the owner's topic settings kept out of
    // this answer. A count, so it is shown whatever the lock settings say.
    const leftOut = a.route ? leftOutLine(a.route.topics_left_out) : "";
    if (leftOut) lines.push(leftOut);
    // Answered WITHOUT the model (a timer, a reminder, the to-do list -
    // JARVIS-API.md section 21): the small "done" line both apps show.
    if (a.route && typeof a.route.quick === "string" && a.route.quick) lines.push(DONE_LINE);
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

  async function write(button, command, f, question, done, args) {
    if (isStale() || !confirm(question(f))) return;
    await sendWrite(button, command, { id: Number(f.id), ...args }, done);
  }

  async function sendWrite(button, command, args, done) {
    button.dataset.busy = "true";
    syncButton(button);
    try {
      const out = await invoke(command, args);
      if (out && out.ok === false) throw new Error(out.error || out.reason || "Refused.");
      const said = typeof done === "function" ? done(out) : done;
      announce(said);
      await load();
      a.notice = said;
      paintList();
    } catch (error) {
      button.dataset.busy = "false";
      syncButton(button);
      a.error = errorText(error);
      paintList();
    }
  }

  /** "Erase the words", with "Also delete the chat it came from" (the
   *  owner's decision, 2026-09-27) asked as a second yes/no right after
   *  the main confirm - `window.confirm` has no room for a checkbox.
   *  Cancelling the second one still erases the fact. */
  async function writeErase(button, f) {
    if (isStale() || !confirm(eraseQuestion(f))) return;
    // The chat named first, and no question when none is on record (the
    // chat audit, 2026-09-28) - brain.js eraseFact asks the same way.
    let chat;
    try {
      chat = readFactChat(await invoke("brain_fact_chat", { id: Number(f.id) }));
    } catch {
      chat = undefined;
    }
    const others = chat ? await otherFactsInChat(invoke, chat, f.id) : 0;
    const alsoChat = chat === undefined ? window.confirm(ERASE_ALSO_CHAT_CONFIRM)
      : chat ? window.confirm(eraseAlsoChatNamedConfirm(chat, whenLine(chat.updated), others))
        : false;
    await sendWrite(button, "brain_memory_erase",
      { id: Number(f.id), also_delete_conversation: alsoChat },
      (out) => {
        // The chat this bar is in, deleted: its turns must stop being sent.
        if (out && out.chat_deleted && chat && typeof onChatDeleted === "function") {
          onChatDeleted(chat.id);
        }
        return out && out.chat_deleted ? ERASED_AND_CHAT_DELETED
          : alsoChat || chat === null ? ERASED_NO_CHAT : ERASED;
      });
  }

  function row(f) {
    const item = el("li", "answer-used-item");
    item.dataset.id = String(f.id);
    if (f.erasedAt) {
      item.append(el("span", "answer-used-text erased", erasedLine(f.erasedAt)));
    } else {
      // A fact whose topic was switched off since: the PC sends no words.
      item.append(el("span", "answer-used-text",
        f.leftOut ? TOPIC_WORDS.used_left_out : f.text || "(no words)"));
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
      buttons.append(actionButton(ERASE_LABEL, ERASE_TITLE, (b) => writeErase(b, f), true));
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

  /* ------------------------------------------------------------------------
   * "Where this came from" (I42), and the quote check (I132). No-ops when
   * the caller did not pass `sources` - so an older page that has not added
   * the three elements yet keeps working exactly as before.
   * ------------------------------------------------------------------------ */

  function paintSourcesLine() {
    if (!src.box) return;
    const v = a.srcView;
    const has = a.srcLoading
      || Boolean(v && (v.available === false || v.sources.length || v.quotes.length || v.hidden));
    // Never on a temporary answer: nothing was recorded for one to read
    // back (jarvis_sources.record is never reached - jarvis_agent's own
    // tool loop still ran, but a temporary chat's turn_id is not kept).
    const show = a.done && !a.sentTemporary && has;
    src.box.hidden = !show;
    if (!show) return;
    if (src.lineButton) {
      src.lineButton.textContent = SOURCES_LINE;
      src.lineButton.title = SOURCES_LINE_TITLE;
      src.lineButton.setAttribute("aria-expanded", String(a.srcOpen));
    }
  }

  function sourceRow(s) {
    const item = el("li", "answer-used-item");
    if (isOpenable(s)) {
      const a2 = document.createElement("a");
      a2.className = "answer-used-text";
      a2.href = s.url;
      a2.dataset.external = "true";
      // The host only, never the full link and never a title the website
      // chose - the full address shows only once the owner actually taps
      // it, as a real navigation in the real browser (see main.js's
      // `a[data-external]` handler; this element opts into it by attribute
      // alone, nothing here opens or fetches anything itself).
      a2.textContent = sourceLine(s);
      a2.title = s.url;
      item.append(a2);
    } else {
      item.append(el("span", "answer-used-text", sourceLine(s)));
    }
    return item;
  }

  function paintSourcesList() {
    if (!src.list) return;
    src.list.replaceChildren();
    src.list.hidden = !a.srcOpen;
    if (!a.srcOpen) return onChange();
    src.list.append(el("p", "answer-used-title", SOURCES_TITLE));
    const v = a.srcView;
    if (a.srcLoading && !v) {
      src.list.append(el("p", "answer-used-empty", "Reading…"));
    } else if (!v) {
      src.list.append(el("p", "answer-used-empty failed",
        `Could not read this: ${a.srcError || "no answer"}`));
    } else if (!v.available) {
      src.list.append(el("p", "answer-used-empty", v.why));
    } else if (v.hidden) {
      src.list.append(el("p", "answer-used-empty", hiddenLine(v.hiddenCount || v.sources.length)));
    } else {
      if (v.sources.length) {
        const ul = el("ul", "answer-used-rows");
        for (const s of v.sources) ul.append(sourceRow(s));
        src.list.append(ul);
      } else {
        src.list.append(el("p", "answer-used-empty", "Nothing was read for this answer."));
      }
      for (const q of v.quotes) {
        const p = el("p", "answer-used-empty warn");
        p.title = QUOTE_WARNING_TITLE;
        p.append(el("span", "answer-used-quote", `“${q}”`), document.createTextNode(" — "),
          el("span", null, QUOTE_WARNING_LABEL));
        src.list.append(p);
      }
      if (a.srcError) src.list.append(el("p", "answer-used-empty failed", a.srcError));
    }
    onChange();
  }

  async function loadSources() {
    if (!TURN_ID_RX.test(a.turnId || "") || a.srcLoading) return;
    a.srcLoading = true;
    a.srcError = "";
    paintSourcesLine();
    if (a.srcOpen) paintSourcesList();
    try {
      a.srcView = readSources(await invoke("chat_sources", { turnId: a.turnId }));
    } catch (error) {
      a.srcView = null;
      a.srcError = errorText(error);
    } finally {
      a.srcLoading = false;
    }
    paintSourcesLine();
    if (a.srcOpen) paintSourcesList();
  }

  if (src.lineButton) {
    src.lineButton.addEventListener("click", () => {
      a.srcOpen = !a.srcOpen;
      if (src.lineButton) src.lineButton.setAttribute("aria-expanded", String(a.srcOpen));
      paintSourcesList();
    });
  }

  return {
    begin(sentTemporary) {
      clear();
      a.sentTemporary = Boolean(sentTemporary);
    },
    route(route) {
      a.route = route && typeof route === "object" ? route : null;
      a.game = temporaryOutcome(a.sentTemporary, a.route) === "game";
      a.ids = usedIds(a.route);
      // The facts the line opens: the ones with an id. (A fact from the
      // older word list over the jsonl has none, and cannot be listed.)
      a.count = a.ids.length;
      // "Where this came from" (I42): the SAME id the right/wrong mark
      // already uses (commands.rs route_line_from_header now passes it
      // on, validated there too - a bad or missing one is simply null).
      const t = a.route && typeof a.route.turn_id === "string" ? a.route.turn_id : "";
      a.turnId = TURN_ID_RX.test(t) ? t : null;
      paintNote();
      paintLine();
    },
    finish(done) {
      a.done = Boolean(done);
      paintNote();
      paintLine();
      // Fetched once, quietly, right as the answer finishes - there is no
      // cheap count to gate this on first (see memory-used.js). Never on a
      // temporary answer: nothing was recorded to read back for one.
      if (a.done && a.turnId && !a.sentTemporary) loadSources();
      else paintSourcesLine();
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
      return { ids: [...a.ids], open: a.open, sentTemporary: a.sentTemporary,
        game: a.game, turnId: a.turnId, srcOpen: a.srcOpen };
    },
  };
}
