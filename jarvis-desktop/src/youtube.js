/**
 * Quiz me on a YouTube video, the block under the paste box on the Brain's
 * Work tab (the owner's decision of 2026-09-30; docs/STUDY-FROM-TEXT-DESIGN.md
 * section 14; JARVIS-API.md section 112; quiz.js holds the words and the
 * reading; src-tauri/src/brain/youtube.rs holds the four commands).
 *
 * The owner pastes a link. The PC raises ONE approval card for it (a risky
 * approval, decided in the ordinary approval screens - never here) and only
 * after a yes reads the video's caption text and writes questions. This block
 * polls the request about every two seconds until it is ready (the ordinary
 * quiz opens, through `adopt`) or over (the PC's own sentence is shown and the
 * link field is offered again). Cancel shows only while the card waits.
 *
 * THIS WINDOW KEEPS NOTHING: the link lives in the box only until the card is
 * raised, then the box is emptied. It is never in localStorage, a draft, a
 * log, a toast, an announcement or a sentence of ours. Every refusal and
 * failure sentence is the PC's own. With "Hide memory lists and chat history"
 * on, the link box and the request's link are not drawn (Rust also takes them
 * out); the state sentence and Cancel stay. The terms line is always visible.
 * The start button is held on a stale link (rule 4); polling and Cancel are
 * not. A PC without the feature gets one line and no block.
 *
 * Every string from the PC goes in with textContent.
 *
 * @module youtube
 */
import {
  YT_CANCEL, YT_CANCELLING, YT_COUNT, YT_INTRO, YT_LINK_MAX, YT_MISSING, YT_NO_LINK,
  YT_OUTSIDE, YT_PLACEHOLDER, YT_POLL_SECONDS, YT_START, YT_STARTING, YT_TERMS, YT_TITLE,
  ytCanStart, ytGiveUpOnUnknown, ytIsKnown, ytKeepPolling, ytOutcome, ytReadInfo,
  ytReadRequest, ytShown, ytTruncatedNote, ytValidId,
} from "./quiz.js";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

/**
 * @param {object} deps
 *   root        the block's element (starts hidden)
 *   invoke      Tauri invoke
 *   canAct      () => whether the link is live (rule 4)
 *   staleLine   the words for a stale link
 *   live        { add(button), sync(button) } - the Brain's live buttons
 *   listen      (event, fn) => void, or null
 *   view        () => the Brain tab showing
 *   covered     () => true while a quiz or its summary is open
 *   spanish     () => true while Spanish practice is chosen
 *   adopt       (quiz, note|null) => opens the ordinary quiz
 *   errorText   (error) => plain words for a thrown error
 *   hiddenNode  () => the Brain's "hidden until Windows Hello" node
 *   announce    (words, mode) => screen-reader line (optional)
 *   pollMs      override for the poll gap (tests only; default 2 s)
 */
export function createYoutubeBlock(deps) {
  const { root } = deps;
  const S = {
    available: null,   // null until a read answered; false on a PC without it
    hidden: false,     // the private lists are hidden
    request: null,     // the open request (waiting, fetching, writing)
    busy: false,
    said: "",
    unknownSince: null,
    timer: null,
    gen: 0,            // bumped when a request ends, so a late answer is dropped
    started: false,
    wasLive: true,
  };
  const pollMs = deps.pollMs || YT_POLL_SECONDS * 1000;

  // ── The pieces, built once, so a repaint never wipes a link being pasted ──
  const missing = el("p", "note", YT_MISSING);
  const title = el("h3", "subhead", YT_TITLE);
  const intro = el("p", "note", YT_INTRO);
  const status = el("p", "yt-status");
  status.setAttribute("role", "status");
  const linkLine = el("p", "note yt-link");
  const cancel = el("button", "btn small", YT_CANCEL);
  cancel.type = "button";
  const form = el("form", "yt-form");
  form.autocomplete = "off";
  const input = el("input", "field yt-input");
  input.type = "text";
  input.id = "youtube-link";
  input.maxLength = YT_LINK_MAX + 1;
  input.spellcheck = false;
  input.autocomplete = "off";
  input.placeholder = YT_PLACEHOLDER;
  input.setAttribute("aria-label", YT_PLACEHOLDER);
  input.setAttribute("aria-describedby", "youtube-terms");
  const terms = el("p", "note", YT_TERMS);
  terms.id = "youtube-terms";
  const outside = el("p", "note", YT_OUTSIDE);
  const start = el("button", "btn small", YT_START);
  start.type = "submit";
  start.id = "youtube-start";
  const actions = el("div", "goal-actions");
  actions.append(start);
  form.append(input, terms, outside, actions);
  const hiddenBox = el("div", "yt-hidden");
  const saidLine = el("p", "note yt-said");
  saidLine.setAttribute("role", "status");
  root.append(missing, title, intro, status, linkLine, cancel, form, hiddenBox, saidLine);
  root.hidden = true;
  if (deps.live) deps.live.add(start);

  function say(words) {
    if (deps.announce && words) deps.announce(words, "polite");
  }

  function paintStart() {
    start.textContent = S.busy ? YT_STARTING : YT_START;
    start.dataset.busy = S.busy || !ytCanStart(input.value) ? "true" : "false";
    if (deps.live) deps.live.sync(start);
    else start.disabled = start.dataset.busy === "true";
  }

  /** Draws whatever is true now. Cheap; never touches the link box's text. */
  function paint() {
    const req = S.request;
    // Like the phone: only where the paste box is (no quiz open), and in Spanish
    // mode only while a request is already open on the PC.
    const shown = !deps.covered() && (!deps.spanish() || Boolean(req));
    if (!shown || (S.available == null && !req)) {
      root.hidden = true;
      return;
    }
    root.hidden = false;
    if (S.available === false) {
      missing.hidden = false;
      for (const n of [title, intro, status, linkLine, cancel, form, hiddenBox, saidLine]) n.hidden = true;
      return;
    }
    missing.hidden = true;
    title.hidden = false;
    intro.hidden = false;
    if (req) {
      status.hidden = false;
      status.textContent = ytShown(req);
      linkLine.hidden = S.hidden || !req.link;
      linkLine.textContent = S.hidden ? "" : req.link || "";
      cancel.hidden = req.phase !== "waiting";
      cancel.textContent = S.busy ? YT_CANCELLING : YT_CANCEL;
      cancel.disabled = S.busy;
      form.hidden = true;
      hiddenBox.hidden = true;
    } else {
      status.hidden = true;
      status.textContent = "";
      linkLine.hidden = true;
      linkLine.textContent = "";
      cancel.hidden = true;
      if (S.hidden) {
        // The link box is not offered, and nothing pasted stays in it.
        input.value = "";
        form.hidden = true;
        hiddenBox.hidden = false;
        if (!hiddenBox.firstChild) hiddenBox.append(deps.hiddenNode());
      } else {
        form.hidden = false;
        hiddenBox.hidden = true;
        hiddenBox.replaceChildren();
      }
    }
    saidLine.textContent = S.said;
    saidLine.hidden = !S.said;
    paintStart();
  }

  function stopTimer() {
    if (S.timer) clearTimeout(S.timer);
    S.timer = null;
  }

  /** Forgets the open request (it is over, or the PC no longer has it). */
  function end() {
    S.request = null;
    S.unknownSince = null;
    S.gen += 1;
    stopTimer();
  }

  function schedule() {
    stopTimer();
    if (!S.request || !ytKeepPolling(S.request.phase)) return;
    // Stop polling when the page closes: away from the Work tab nothing is asked.
    if (deps.view() !== "work") return;
    S.timer = setTimeout(poll, pollMs);
  }

  /**
   * Takes a request the PC described: a ready one opens the ordinary quiz, an
   * ended one shows the PC's sentence, an unknown state keeps polling for at
   * most three minutes. Returns true when the request is over.
   */
  function settle(out) {
    const req = out.request;
    if (req.phase === "ready") {
      const quiz = req.quiz;
      end();
      S.said = "";
      if (quiz) deps.adopt(quiz, ytTruncatedNote(req));
      return true;
    }
    if (req.phase === "ended") {
      end();
      S.said = out.said;
      return true;
    }
    S.request = req;
    if (ytIsKnown(req.state)) {
      S.unknownSince = null;
    } else {
      const now = Date.now();
      S.unknownSince = S.unknownSince == null ? now : S.unknownSince;
      if (ytGiveUpOnUnknown(S.unknownSince, now)) {
        end();
        S.said = out.said;
        return true;
      }
    }
    S.said = "";
    return false;
  }

  async function poll() {
    S.timer = null;
    const cur = S.request;
    if (!cur) return;
    if (!ytValidId(cur.id)) {
      end();
      paint();
      return;
    }
    const gen = S.gen;
    let answer;
    try {
      answer = await deps.invoke("brain_youtube_get", { id: cur.id });
    } catch (error) {
      if (gen !== S.gen) return;
      S.said = deps.errorText(error);
      paint();
      schedule();
      return;
    }
    if (gen !== S.gen) return;
    if (answer && answer.ok !== false) S.hidden = answer.hidden === true;
    const out = ytOutcome(answer, "Not read.");
    if (!out.ok || !out.request) {
      // The PC no longer has it, or a ready request had nothing readable in it: over.
      if (out.gone || out.request) {
        end();
        S.said = out.said;
        paint();
        return;
      }
      S.said = out.said;
      paint();
      schedule();
      return;
    }
    const over = settle(out);
    paint();
    if (!over) schedule();
    else if (S.said) say(S.said);
  }

  /** Reads `GET /api/youtube`: whether the PC has it, and a request already open. Never starts anything. */
  async function check() {
    let answer;
    try {
      answer = await deps.invoke("brain_youtube_info", {});
    } catch {
      return;
    }
    const info = ytReadInfo(answer);
    if (!info) return;
    S.available = info.available;
    S.hidden = info.hidden;
    if (info.available && !S.request && info.latest && ytKeepPolling(info.latest.phase)) {
      S.request = info.latest;
      S.unknownSince = null;
    }
    paint();
    schedule();
  }

  async function begin() {
    const link = input.value;
    if (S.busy) return;
    if (!deps.canAct()) {
      S.said = deps.staleLine;
      paint();
      return;
    }
    if (!ytCanStart(link)) {
      S.said = YT_NO_LINK;
      paint();
      return;
    }
    S.busy = true;
    S.said = "";
    paint();
    let answer;
    try {
      answer = await deps.invoke("brain_youtube_start", { url: link, count: YT_COUNT });
    } catch (error) {
      S.busy = false;
      const words = deps.errorText(error);
      if (words === YT_MISSING) {
        S.available = false;
        S.said = words;
      } else {
        S.said = `Not started. ${words}`;
      }
      paint();
      return;
    }
    S.busy = false;
    if (answer && answer.ok !== false) S.hidden = answer.hidden === true;
    const out = ytOutcome(answer, "Not started.");
    if (!out.ok || !out.request) {
      // The link stays in the box: the PC's words say what to fix.
      S.said = out.said;
      paint();
      say(out.said);
      return;
    }
    // The card is raised: the link is let go at once. The block now shows the
    // PC's state sentence itself, so nothing is said twice.
    input.value = "";
    S.unknownSince = null;
    S.gen += 1;
    S.request = out.request;
    S.said = "";
    const over = settle(out);
    paint();
    if (!over) schedule();
    else if (S.said) say(S.said);
  }

  async function withdraw() {
    const cur = S.request;
    if (!cur || S.busy) return;
    if (!ytValidId(cur.id)) {
      end();
      paint();
      return;
    }
    S.busy = true;
    paint();
    let answer;
    try {
      // Never held on a stale link: it only ever makes things safer.
      answer = await deps.invoke("brain_youtube_cancel", { id: cur.id });
    } catch (error) {
      S.busy = false;
      S.said = `Not cancelled. ${deps.errorText(error)}`;
      paint();
      return;
    }
    S.busy = false;
    const out = ytOutcome(answer, "Not cancelled.");
    S.said = out.said;
    if (out.gone) {
      end();
    } else if (out.ok && out.request) {
      if (out.request.phase === "ended") end();
      else S.request = out.request;
    }
    paint();
    say(S.said);
    schedule();
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    begin();
  });
  input.addEventListener("input", paintStart);
  cancel.addEventListener("click", withdraw);

  // Private lists hidden or shown again: read it again, Rust decides what comes back.
  if (deps.listen) {
    deps.listen("security-changed", () => { if (deps.view() === "work") check(); });
    deps.listen("private-hidden", () => { if (deps.view() === "work") check(); });
  }

  return {
    /** The Work tab opened: ask the PC (a read) and pick up an open request. */
    enter() {
      S.started = true;
      paint();
      check();
    },
    /** Another tab opened: stop asking. The request stays open on the PC. */
    leave() {
      stopTimer();
    },
    /** The paste box's owner changed something (a quiz opened or closed, the mode changed). */
    sync() {
      paint();
      if (S.request && !S.timer && deps.view() === "work") schedule();
    },
    /** The link came back or went away. */
    linkChanged() {
      paintStart();
      const live = deps.canAct();
      // Ask again only when the link comes back, not on every event.
      if (live && !S.wasLive && S.started && deps.view() === "work") check();
      S.wasLive = live;
    },
    /** For tests and the Brain's own checks. */
    get open() {
      return S.request;
    },
    readRequest: ytReadRequest,
  };
}
