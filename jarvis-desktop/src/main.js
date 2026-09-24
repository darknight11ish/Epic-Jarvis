/**
 * Jarvis Desktop — spotlight frontend.
 *
 * Responsibilities:
 *   • bridge to the Rust backend (`invoke`) and its events (`listen`);
 *   • stream `POST /api/chat` from the local Jarvis server and render the
 *     tokens as markdown into the answer card;
 *   • keep the native window sized to the card as it grows;
 *   • handle the keyboard contract — Enter to send, Esc to dismiss.
 *
 * The page is loaded with `withGlobalTauri`, so the API arrives on
 * `window.__TAURI__` rather than through a bundler. Every call is guarded so
 * the same file also runs in a plain browser tab while iterating on styling.
 */

/* ==========================================================================
   Configuration
   ========================================================================== */

const JARVIS_SERVER = "http://127.0.0.1:4719";
const CHAT_ENDPOINT = `${JARVIS_SERVER}/api/chat`;

/** Route badge defaults, overridden by whatever the server reports. */
// The model field is null until the server names one. Both of these used to
// carry a hard-coded guess — "qwen3:8b" and "jarvis-escalate" — which the badge
// then presented with the same confidence as a real answer.
const DEFAULT_ROUTE = { tier: "local", label: "Local", model: null };
const CLOUD_ROUTE = { tier: "cloud", label: "Cloud", model: null };

/**
 * Sent as `X-Jarvis-Client`. The Jarvis server accepts a request whose `Origin`
 * is not in its allow-list only when this header marks it as a first-party HUD
 * client, and a Tauri WebView's origin (`http://tauri.localhost`) is never in
 * that list.
 */
const JARVIS_CLIENT_HEADER = "hud";

/**
 * The shared secret is deliberately absent from this file. Chat requests are
 * made by the Rust backend, which reads `JARVIS_TOKEN` from the environment, so
 * the token never enters WebView2 memory where a script in the HUD could read
 * it. See `stream_chat` in `commands.rs`.
 */

/** Clipboard context longer than this is trimmed in the attachment chip. */
const CLIPBOARD_PREVIEW = 90;

/**
 * Quick-capture prefixes. Typing one at the head of the prompt files the rest
 * as a note (see `fileFromBar`) instead of asking Jarvis anything, and shows a
 * chip while typing; the prefix itself is not part of the note.
 */
const NOTE_PREFIXES = {
  "#log": { target: "logseq", label: "Logseq Journal" },
  "#logseq": { target: "logseq", label: "Logseq Journal" },
  "#journal": { target: "logseq", label: "Logseq Journal" },
  "#joplin": { target: "joplin", label: "Joplin Note" },
  "#jop": { target: "joplin", label: "Joplin Note" },
  // "#vault" meant Joplin until 2026-09-24; the owner moved it to Obsidian,
  // whose own word it is.
  "#vault": { target: "obsidian", label: "Obsidian Daily Note" },
  "#obs": { target: "obsidian", label: "Obsidian Daily Note" },
  "#obsidian": { target: "obsidian", label: "Obsidian Daily Note" },
  "#daily": { target: "obsidian", label: "Obsidian Daily Note" },
};

/** What Alt+Shift+N (and the widget's buttons) type in for each target. */
const ARM_PREFIX = { logseq: "#log ", joplin: "#joplin ", obsidian: "#obs " };

/*
 * There used to be a NOTE_INSTRUCTIONS table here: a system turn asking the
 * model to call `append_logseq_journal` / `create_joplin_note`. Neither tool
 * existed, so no note was ever filed. A prefixed prompt now goes straight to
 * `/api/notes/capture` (backend note-capture.patch) - the owner's own words,
 * no model, through the approval gate - and the card says how it ended.
 * Searching notes is a question for Jarvis in chat (its notes_search tool).
 */

/**
 * Smallest gap between native window resizes, in milliseconds. Each resize is a
 * `SetWindowPos` on a transparent, Acrylic-backed window; firing one per token
 * makes DWM recomposite the blur dozens of times a second, which shows up as
 * border flicker and stutter. Coalescing to ~7 Hz is invisible to the reader
 * and costs DWM nothing.
 */
const RESIZE_INTERVAL_MS = 150;

/* ==========================================================================
   Tauri bridge
   ========================================================================== */

import {
  currentLink,
  announce,
  currentQueue,
  amend as amendOnBackend,
  decide as decideOnBackend,
  faceState,
  fetchDigest,
  injectTaskNote,
  markDigestSeen,
  onLink,
  onQueue,
  pauseTask,
  resumeTask,
  linkWords,
  riskLine,
  expiryWords,
  setMuted,
  stopTask,
  followTheme,
  followZoom,
  start as startLink,
} from "./jarvis-link.js";
import { startVoice, setVoiceMode } from "./voice.js";
import { ignoreWhileTalking, loadBargeIn } from "./barge-in.js";
// The renderer the answer card and the approval preview use - see markdown.js.
import { escapeHtml, renderMarkdown } from "./markdown.js";
import {
  boxTagAfter,
  commitExchange,
  historyMessages,
  newConversationId,
  sentProvenance,
  userMessage,
} from "./chat-history.js";
import { fileNote, loadTargets, notSetUp, noTargetsLine, targetName } from "./note-capture.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/**
 * Calls a Rust command. Resolves to `null` (and warns) when the backend is
 * unavailable, so a failed IPC call never takes the UI down with it.
 */
async function invoke(command, args = {}) {
  if (!IS_TAURI) {
    console.info(`[jarvis] invoke("${command}") skipped - no Tauri backend`);
    return null;
  }
  try {
    return await TAURI.core.invoke(command, args);
  } catch (error) {
    console.error(`[jarvis] invoke("${command}") failed:`, error);
    return null;
  }
}

/**
 * Like [`invoke`], but propagates the rejection. Used where the caller needs to
 * see the failure — the chat stream reports its terminal state through the
 * promise, so swallowing it would leave the card spinning forever.
 */
async function invokeStrict(command, args = {}) {
  if (!IS_TAURI) throw new Error("no Tauri backend");
  return TAURI.core.invoke(command, args);
}

/** Subscribes to a backend event. No-ops outside Tauri. */
async function listen(event, handler) {
  if (!TAURI || !TAURI.event || !TAURI.event.listen) return () => {};
  try {
    return await TAURI.event.listen(event, handler);
  } catch (error) {
    console.error(`[jarvis] listen("${event}") failed:`, error);
    return () => {};
  }
}

/* ==========================================================================
   DOM handles
   ========================================================================== */

const $ = (id) => document.getElementById(id);

const dom = {
  root: document.documentElement,
  shell: $("shell"),
  prompt: $("prompt"),
  route: $("route"),
  routeTier: $("route-tier"),
  routeModel: $("route-model"),
  routeSep: $("route-sep"),
  offline: $("offline"),
  offlineText: $("offline-text"),
  micLabel: $("mic-label"),
  answerMark: $("answer-mark"),
  markRight: $("mark-right"),
  markWrong: $("mark-wrong"),
  answerMarkNote: $("answer-mark-note"),
  approvalOptionsWhy: $("approval-options-why"),
  offlineRetry: $("offline-retry"),
  primer: $("primer"),
  mic: $("mic"),
  voiceAuto: $("voice-auto"),
  pin: $("pin"),
  submitHint: $("submit-hint"),
  noteChip: $("note-chip"),
  noteChipLabel: $("note-chip-label"),

  approval: $("approval"),
  approvalAction: $("approval-action"),
  approvalTarget: $("approval-target"),
  approvalPreview: $("approval-preview"),
  approvalOptions: $("approval-options"),
  approvalNoteInput: $("approval-note"),
  approvalNoteSend: $("approval-note-send"),
  approvalHint: $("approval-hint"),
  approvalApprove: $("approval-approve"),
  approvalDeny: $("approval-deny"),
  approvalCount: $("approval-count"),
  parked: $("parked"),
  parkedText: $("parked-text"),
  parkedShow: $("parked-show"),
  approvalRaised: $("approval-raised"),
  raisedChip: $("raised-chip"),
  raisedSource: $("raised-source"),
  raisedQuote: $("raised-quote"),
  raisedContextWrap: $("raised-context-wrap"),
  raisedContext: $("raised-context"),

  progressLine: $("progress-line"),
  taskControls: $("task-controls"),
  btnTaskPause: $("btn-task-pause"),
  btnTaskResume: $("btn-task-resume"),
  btnTaskStop: $("btn-task-stop"),
  taskNoteInput: $("task-note"),
  btnTaskNoteSend: $("btn-task-note-send"),

  attention: $("attention"),
  attentionCount: $("attention-count"),
  attentionBudget: $("attention-budget"),
  attentionMute: $("attention-mute"),
  attentionClose: $("attention-close"),
  attentionNote: $("attention-note"),
  digest: $("digest"),
  digestSeen: $("digest-seen"),

  attachments: $("attachments"),
  captureChip: $("attachment-capture"),
  captureThumb: $("capture-thumb"),
  captureMeta: $("capture-meta"),
  captureRemove: $("capture-remove"),
  clipboardChip: $("attachment-clipboard"),
  clipboardMeta: $("clipboard-meta"),
  clipboardRemove: $("clipboard-remove"),
  pictureNotice: $("picture-notice"),
  pictureNoticeText: $("picture-notice-text"),
  pictureTextOnly: $("picture-text-only"),
  pictureAnyway: $("picture-anyway"),
  pictureKeep: $("picture-keep"),

  card: $("card"),
  cardStatusText: $("card-status-text"),
  cardStat: $("card-stat"),
  cardBody: $("card-body"),
  answer: $("answer"),
  cursor: $("cursor"),
  copy: $("copy"),
  stop: $("stop"),
  newConversation: $("new-conversation"),
  services: $("services"),

  previousAnswer: $("previous-answer"),
  previousAnswerSummary: $("previous-answer-summary"),
  previousAnswerBody: $("previous-answer-body"),
};

/* ==========================================================================
   State
   ========================================================================== */

const state = {
  /** `idle` | `streaming` | `done` | `error` */
  phase: "idle",
  /** This turn was sent by voice, so its reply gets spoken back too - set
   *  right before `send()` from the push-to-talk flow, read once in
   *  `finishStream` and cleared there so a later TYPED turn stays silent. */
  voiceTurn: false,
  /** Automatic (VAD) listening is on. Mutually exclusive with push-to-talk
   *  at the Rust level too - `start_voice_capture` refuses while this is
   *  true, and vice versa. */
  autoListening: false,
  /** Raw markdown accumulated from the stream. */
  buffer: "",
  /** Prompt currently in flight, kept for the retry path. */
  inFlight: null,
  /**
   * The conversation so far: finished `{ question, answer }` pairs, oldest
   * first, trimmed to fit the model (chat-history.js). Sent ahead of every
   * new question so a follow-up is understood. This window's memory only,
   * never written to disk; cleared by "New conversation" and by Esc.
   */
  conversation: [],
  /**
   * The id every request of this conversation carries as `conversation_id`
   * (JARVIS-API.md section 18), so the PC's History keeps one entry per
   * conversation. A new one at start, on "New conversation" and on Esc -
   * wherever `conversation` above is emptied (closeCard).
   */
  conversationId: newConversationId(),
  /**
   * Where the words now in the box came from: "typed", "clipboard" (the
   * clipboard hotkey's prefill, until it is edited) or "pasted" (a paste or
   * drop since the box was last empty). Moved only by `boxTagAfter`
   * (chat-history.js), which holds every rule.
   */
  boxTag: "typed",
  /** The tag the turn now streaming was sent with, kept with it into
   *  `conversation` when it finishes, so it is sent again with that turn. */
  turnProvenance: null,
  /** The question of the turn now streaming, exactly as sent, until it
   *  finishes. Null when nothing is in flight or the turn was abandoned. */
  turnQuestion: null,
  /** The turn's reply came as `data:` lines (SSE), and whether one of them
   *  said it had finished. SSE that stops without saying so was cut off,
   *  and is not added to the conversation. */
  turnFramed: false,
  turnEnded: false,
  /** The answer stopped at the length limit (`finish_reason: "length"`). It
   *  is shown, and kept, with a note saying it was cut short. */
  turnCutShort: false,
  /** This turn's Local/Cloud badge came from the server's X-Jarvis-Route
   *  header, so nothing in the stream may overwrite it with a guess. */
  routeFromHeader: false,
  /** Cancels whichever transport is streaming; null when idle. */
  abort: null,
  startedAt: 0,
  chunks: 0,
  pinned: false,
  /** Pending screen capture, as a JPEG data URI. */
  capture: null,
  /** Pending clipboard context. */
  clipboard: null,
  /** The owner chose "Send it anyway" for the attached picture, once. */
  pictureCleared: false,
  /** The words held back while the picture notice asks what to do. */
  pictureHeld: null,
  /** ...and where they came from, put back on the box with them. */
  pictureHeldTag: "typed",
  /** `null`, `"logseq"`, `"joplin"` or `"obsidian"` — set by a prompt prefix. */
  noteTarget: null,
  /** Which note apps the PC is set up for (note-capture.js `readTargets`).
   *  Unknown until the PC answers - and unknown shows none, never all. */
  noteTargets: { known: false, why: "not checked yet" },
  /** The approval gate awaiting a decision, if any. */
  approval: null,
  /** True while a decision is in flight, so a double tap cannot send twice. */
  deciding: false,
  /** The id of the gate a decision was sent for, so it cannot be sent twice. */
  decided: null,
  /** A note is being sent for the current approval - §3b. Its own flag: the
   *  Logseq/Joplin capture path and `deciding` already learned this lesson
   *  once, so a note (which runs a whole chat turn) does not silently
   *  no-op Approve/Deny or vice versa. */
  noteBusy: false,
  /** A pause/resume/stop request for the running task is in flight - §3d.
   *  Its own flag, for the same reason as `noteBusy` above. */
  taskActionBusy: false,
  /** A note for the running task is being sent - §3d. */
  taskNoteBusy: false,
  /** `link.activity` as last reported by the server - "working", "paused",
   *  or "idle". This, and ONLY this, decides whether Resume or Pause is
   *  shown on the task-controls card: a click only proves a request was
   *  SENT, never that the task actually paused. See widget.js's identical
   *  field and `syncTaskControls()` below for the reasoning in full. */
  taskActivity: "idle",
  /** Gate ids the user put away with Esc. Still pending; just not on screen. */
  parked: new Set(),
  /** The digest as last read, in the server's order. Never re-sorted. */
  digest: null,
  /**
   * Three states, not two. `null` is "the user has not said" — the panel
   * follows the count. `true` is "opened deliberately". `false` is "dismissed",
   * and it survives until the count goes UP.
   *
   * A boolean was the bug: `attentionOpen || pending > 0` re-showed the panel
   * within milliseconds of Close, because `same_link` includes `last_id` and
   * the stream republishes the link on every event that carries one. Close did
   * nothing, and the panel landed back on top of any gate opened from it.
   */
  attentionOpen: null,
  /** The pending count when the panel was dismissed, so a NEW item re-arms it. */
  attentionDismissedAt: 0,
  /** True while a digest read is in flight, so a repaint cannot stack them. */
  digestLoading: false,
  route: { ...DEFAULT_ROUTE },

  /**
   * Prompts actually submitted, oldest first, for Up/Down recall. In-memory
   * for this run of the window only — never written to disk — but NOT
   * cleared by `dismiss()`: the quickbar hides and reopens on every
   * Alt+Space, and history that reset on every hide would barely recall
   * anything.
   */
  promptHistory: [],
  /** The tag each prompt in `promptHistory` was sent with, by its text, so a
   *  pasted prompt recalled with Up is sent as pasted again - not as typed. */
  promptTags: new Map(),
  /** Index into `promptHistory` while browsing it; `null` when not browsing. */
  historyIndex: null,
  /** What was in the composer before Up was first pressed, restored on Down
   *  past the newest entry — so browsing history never eats a draft. */
  historyDraft: "",
  /** ...and the draft's tag, restored with it. */
  historyDraftTag: "typed",
  /** The prompt behind the answer currently in `state.buffer`, kept after the
   *  turn finishes so a later turn can label it in the scrollback strip. */
  lastPrompt: "",
  /** The previous turn's `{ prompt, buffer }`, once a new one starts — one
   *  level of scrollback, shown folded in the card until dismissed. */
  previousAnswer: null,
};

/** How many prompts `state.promptHistory` keeps. Older ones fall off the front. */
const PROMPT_HISTORY_LIMIT = 50;

/** `idle` | `streaming` | `done` | `error` | `approval`. */
function setPhase(phase) {
  state.phase = phase;
  dom.root.dataset.state = phase;
}

/* ==========================================================================
   Card rendering and native window sizing
   ========================================================================== */

let paintQueued = false;

/** Repaints the card from the buffer, at most once per animation frame. */
/**
 * How often the answer is re-rendered while tokens are arriving.
 *
 * Every paint re-parses the WHOLE buffer and rebuilds the whole answer subtree,
 * so the cost is quadratic in the length of the answer. At one paint per frame
 * a thirty-second reply parsed its own text about eighteen hundred times, and
 * the last of those frames were parsing tens of kilobytes each — in an
 * always-on-top transparent window that is also resizing itself.
 *
 * 100ms is under the ~150ms at which text stops feeling live, and it cuts the
 * parse count roughly sixfold. It also fixes the `.fresh` animation below,
 * which could never complete at frame rate.
 */
const STREAM_PAINT_MS = 100;
let lastPaintAt = 0;
/** How many blocks the answer had last paint, so `.fresh` fires once each. */
let paintedBlocks = 0;

function paint({ immediate = false } = {}) {
  if (paintQueued && !immediate) return;
  if (!immediate && state.phase === "streaming") {
    const now = performance.now();
    if (now - lastPaintAt < STREAM_PAINT_MS) return;
  }
  paintQueued = true;

  requestAnimationFrame(() => {
    paintQueued = false;
    lastPaintAt = performance.now();

    dom.answer.innerHTML = renderMarkdown(state.buffer);
    // `.fresh` marks a block that has just appeared. It used to be added to
    // `lastElementChild` on every paint — but `innerHTML` destroys and
    // recreates that element each time, so the 260ms animation restarted every
    // frame and never finished: the trailing paragraph sat permanently near
    // opacity 0, flickering. Marking only when the block COUNT rises means a
    // block animates once, when it first exists.
    const blocks = dom.answer.childElementCount;
    const last = dom.answer.lastElementChild;
    if (last && state.phase === "streaming" && blocks > paintedBlocks) {
      last.classList.add("fresh");
    }
    paintedBlocks = blocks;

    // Keep the newest tokens in view unless the user scrolled up to read.
    const body = dom.cardBody;
    const nearBottom =
      body.scrollHeight - body.scrollTop - body.clientHeight < 60;
    if (nearBottom) body.scrollTop = body.scrollHeight;

    syncWindowHeight();
  });
}

let lastReportedHeight = 0;
let pendingHeight = 0;
let lastResizeAt = 0;
let resizeTimer = null;

/**
 * Measures the shell and asks the backend to match it, at most once every
 * [`RESIZE_INTERVAL_MS`]. While an answer streams the window only ever grows:
 * a reflow that briefly reports a shorter shell would otherwise make the frame
 * jitter between two heights.
 */
function syncWindowHeight() {
  // Every caller that changes what the stack holds already calls this, which
  // makes it the one place the primer's visibility cannot be forgotten.
  syncPrimer();
  const height = Math.ceil(dom.shell.getBoundingClientRect().height);
  if (!height) return;
  if (state.phase === "streaming" && height < lastReportedHeight) return;

  pendingHeight = height;
  if (Math.abs(height - lastReportedHeight) < 2) return;

  const elapsed = performance.now() - lastResizeAt;
  if (elapsed >= RESIZE_INTERVAL_MS) {
    commitWindowHeight();
  } else if (resizeTimer === null) {
    resizeTimer = setTimeout(commitWindowHeight, RESIZE_INTERVAL_MS - elapsed);
  }
}

/** Sends the pending height to the backend and restarts the throttle window. */
function commitWindowHeight() {
  if (resizeTimer !== null) {
    clearTimeout(resizeTimer);
    resizeTimer = null;
  }
  if (!pendingHeight || Math.abs(pendingHeight - lastReportedHeight) < 2) return;
  lastReportedHeight = pendingHeight;
  lastResizeAt = performance.now();
  invoke("resize_quickbar", { height: pendingHeight });
}

if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(() => syncWindowHeight()).observe(dom.shell);
}

/** Shows the card and sets its status line. */
function openCard(statusText) {
  dom.card.hidden = false;
  dom.cardStatusText.textContent = statusText;
  syncPrimer();
}

/**
 * Rewrites the primer's key chips from the bindings Rust actually holds.
 *
 * The four global combinations are configurable, so the markup's copy is only
 * a placeholder for first paint. A hardcoded list here would be wrong from the
 * first rebind — and this block exists precisely because the app was telling
 * people about keys that did not do what it said.
 *
 * A refused binding is marked too: "Alt + Space (in use)" is more useful than
 * a combination that silently does nothing, and it points at the one place
 * that can fix it.
 */
async function syncPrimerKeys() {
  if (!IS_TAURI) return;
  let bound;
  try {
    bound = await invokeStrict("get_hotkeys");
  } catch (error) {
    // Leave the placeholders. They are the shipped defaults, so they are right
    // unless something has been changed — and being quietly out of date beats
    // an empty row.
    console.warn("[jarvis] could not read the hotkeys:", error);
    return;
  }
  for (const row of bound || []) {
    const slot = dom.primer.querySelector(`[data-hotkey="${row.id}"]`);
    if (!slot) continue;
    slot.textContent = "";
    // `Super` is the accelerator syntax; the key on the keyboard says Windows.
    const parts = String(row.accelerator).split("+");
    parts.forEach((part, i) => {
      if (i) slot.append("+");
      const kbd = document.createElement("kbd");
      kbd.textContent = part === "Super" ? "Win" : part === "Control" ? "Ctrl" : part;
      slot.append(kbd);
    });
    if (!row.registered) {
      const note = document.createElement("span");
      note.className = "primer-unbound";
      note.textContent = " in use elsewhere";
      slot.append(note);
    }
  }
  syncWindowHeight();
}

/**
 * The primer is the window's empty state: visible when nothing else in the
 * stack is, gone the instant anything is.
 *
 * Kept as one function rather than a `hidden = false` at each of the six call
 * sites, because the failure mode of the second approach is a primer left
 * behind under a streaming answer, and it only shows up on the one path nobody
 * re-tested.
 */
function syncPrimer() {
  const busy =
    !dom.card.hidden ||
    !dom.attention.hidden ||
    !dom.approval.hidden ||
    !dom.parked.hidden ||
    !dom.attachments.hidden;
  dom.primer.hidden = busy;
}

/** Collapses the card and clears everything it was showing. */
function closeCard() {
  dom.card.hidden = true;
  dom.answer.innerHTML = "";
  dom.cardStat.textContent = "";
  dom.cursor.hidden = true;
  state.buffer = "";
  state.lastPrompt = "";
  state.previousAnswer = null;
  // The conversation goes with the card it was shown in: Esc, which ends
  // up here, has always meant "done with this", and a question asked next
  // time the window opens should not silently follow on from one that is no
  // longer on screen. Hiding on focus loss does not come here.
  state.conversation = [];
  // A conversation forgotten here is a finished one on the PC too: the next
  // question starts a new entry in History (JARVIS-API.md section 18).
  state.conversationId = newConversationId();
  state.turnQuestion = null;
  state.turnProvenance = null;
  paintedBlocks = 0;
  spokenUpTo = 0;
  stopSpeaking();
  setPhase("idle");
  renderPreviousAnswer();
  syncNewConversation();
  paint({ immediate: true });
}

/**
 * Shows or hides the folded "previous answer" strip from `state.previousAnswer`.
 *
 * Closed by default (the `<details>` starts with no `open` attribute) every
 * time it is (re)populated — a follow-up you asked on purpose should not have
 * the last answer thrust back open in front of it.
 */
function renderPreviousAnswer() {
  const prev = state.previousAnswer;
  dom.previousAnswer.hidden = !prev;
  if (!prev) return;
  dom.previousAnswer.open = false;
  dom.previousAnswerSummary.textContent = truncateForSummary(prev.prompt);
  dom.previousAnswerBody.innerHTML = renderMarkdown(prev.buffer);
}

/** A one-line label for the scrollback summary — long prompts wrap the card. */
function truncateForSummary(text, max = 80) {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

/** Renders a failure inside the card instead of silently doing nothing. */
function showError(message) {
  setPhase("error");
  openCard("Error");
  dom.cursor.hidden = true;
  state.buffer = `**Jarvis could not answer.**\n\n${message}`;
  paint({ immediate: true });
}

/* ==========================================================================
   Route badge and service health
   ========================================================================== */

function applyRoute(route) {
  state.route = { ...state.route, ...route };
  dom.route.dataset.route = state.route.tier;
  dom.routeTier.textContent = state.route.label;

  // No model name until one has actually been reported. An empty slot says "I
  // have not been told"; a plausible-looking default says "it is this", which
  // is a different and unearned claim.
  const model = state.route.model ? String(state.route.model) : "";
  dom.routeModel.textContent = model;
  dom.routeModel.hidden = !model;
  dom.routeSep.hidden = !model;
  dom.route.title = state.route.tier === "offline"
    ? state.route.why || "No event stream. Nothing is being served."
    : model
      ? `Serving from ${state.route.label.toLowerCase()} — ${model}`
      : `Serving from ${state.route.label.toLowerCase()}. The model is named when the server names it.`;

  // The widget shows the same lane; it has no stream to learn it from.
  invoke("set_route_lane", { lane: state.route.tier });
}

/**
 * Normalises the many shapes a server might use to describe the active route
 * into the two the badge understands.
 */
function routeFromPayload(payload) {
  if (!payload || typeof payload !== "object") return null;

  const meta = payload.meta || payload.metadata || payload;
  const rawTier = String(
    meta.route || meta.tier || meta.provider || ""
  ).toLowerCase();
  const model = meta.model || meta.model_name || payload.model;

  if (!rawTier && !model) return null;

  const isCloud = /cloud|remote|escalat|openai|anthropic|azure|litellm/.test(
    rawTier
  );
  const base = isCloud ? CLOUD_ROUTE : DEFAULT_ROUTE;

  return {
    tier: isCloud ? "cloud" : "local",
    label: isCloud ? "Cloud" : "Local",
    model: model || base.model,
  };
}

/**
 * The badge from the server's own word, `X-Jarvis-Route`, which says which
 * lane answered and - since chat-stream.patch - `where`: "local" or "cloud".
 *
 * The badge used to be guessed from each chunk's `model` string, which an
 * Ollama chunk always carries and which says nothing about where it ran - so
 * a cloud answer would have been labelled Local. An older backend with no
 * `where` is read by its gate: only "escalate" sends a turn to a cloud lane.
 */
function routeFromHeader(route) {
  if (!route || typeof route !== "object") return null;
  const where =
    route.where === "cloud" || route.where === "local"
      ? route.where
      : route.gate === "escalate"
        ? "cloud"
        : "local";
  const cloud = where === "cloud";
  const lane = typeof route.lane === "string" && route.lane ? route.lane : null;
  // second-card.patch: on a turn the second graphics card answered, `lane`
  // is the model really answering and `second_card` says why ("long_context"
  // or "vision"). It is still this PC, so still Local - the badge says which
  // card, in words, rather than a second badge.
  const second = typeof route.second_card === "string" && route.second_card;
  return {
    tier: cloud ? "cloud" : "local",
    label: cloud ? "Cloud" : "Local",
    model: lane && second ? `${lane} on the second graphics card` : lane,
  };
}

function applyHeaderRoute(route) {
  const next = routeFromHeader(route);
  if (!next) return;
  state.routeFromHeader = true;
  applyRoute(next);
}

/** Paints the three health dots in the card footer. */
function applyHealth(report) {
  if (!report || !Array.isArray(report.services)) return;

  for (const service of report.services) {
    const dot = dom.services.querySelector(`[data-service="${service.id}"]`);
    if (!dot) continue;
    dot.dataset.online = String(Boolean(service.online));
    // LiteLLM (the cloud lane's proxy) is optional: not running is normal
    // with no cloud model set up, so its dot is drawn quiet, not red.
    dot.dataset.optional = String(Boolean(service.optional));
    dot.title = `${service.name}: ${service.detail}`;
    // Shape and hue are for the eye; this is the same fact for a screen
    // reader, which was previously told only the service's name.
    dot.setAttribute(
      "aria-label",
      `${service.name}: ${service.online ? "online" : service.optional
        ? "not running, only needed for a cloud model" : "not answering"}`
    );
  }

  const core = report.services.find((service) => service.id === "jarvis");
  if (core && !core.online) {
    applyRoute({
      tier: "offline",
      label: "Offline",
      model: null,
      why: core.detail
        ? `Jarvis is not answering: ${core.detail}`
        : `Jarvis is not answering at ${currentLink().base || "the address set in Settings"}.`,
    });
  } else if (state.route.tier === "offline") {
    applyRoute(DEFAULT_ROUTE);
  }
}

/**
 * Fire-and-forget probe of the three local services.
 *
 * Called when something has actually changed — the window is summoned, the
 * stream connects or drops, a request fails — and never on a timer. Ollama and
 * the LiteLLM proxy are not on the event bus, so their dots still need a probe;
 * Jarvis itself does not, because a live event stream *is* the proof that it is
 * up, and a better one than a request that succeeded a moment ago.
 */
async function refreshHealth() {
  const report = await invoke("check_server_health");
  if (report) applyHealth(report);
}

/* ==========================================================================
   Attachments
   ========================================================================== */

function syncAttachments() {
  if (!state.capture) hidePictureNotice();
  dom.captureChip.hidden = !state.capture;
  dom.clipboardChip.hidden = !state.clipboard;
  dom.attachments.hidden = !state.capture && !state.clipboard;
  syncWindowHeight();
}

function attachCapture(payload) {
  hidePictureNotice();
  state.pictureCleared = false;
  state.capture = payload.dataUri;
  dom.captureThumb.src = payload.dataUri;
  dom.captureMeta.textContent = `${payload.width}x${payload.height} · ${Math.round(
    payload.bytes / 1024
  )} KB · ${payload.elapsedMs} ms`;
  syncAttachments();
}

function attachClipboard(text) {
  state.clipboard = text;
  const preview = text.replace(/\s+/g, " ").trim();
  dom.clipboardMeta.textContent =
    preview.length > CLIPBOARD_PREVIEW
      ? `${preview.slice(0, CLIPBOARD_PREVIEW)}…`
      : preview;
  syncAttachments();
}

/* ==========================================================================
   A picture, and a model that may not see it
   --------------------------------------------------------------------------
   A screen capture goes to the LOCAL model and nowhere else: the backend
   keeps any turn with a picture on this machine (jarvis_router.choose, gate
   "image"), because a screenshot can show an email, a file or a password.
   The local model today reads text only, and sent a picture it answers as if
   there were none. So before sending, ask Ollama (vision.rs) and, unless the
   answer is a clear yes, say so and let the owner choose. Nothing is sent
   while the notice is up; the words go back into the box so none are lost.
   ========================================================================== */

async function pictureCanBeSeen() {
  let check = null;
  try {
    check = await invokeStrict("local_model_vision");
  } catch (error) {
    check = { vision: null, model: null, reason: String((error && error.message) || error) };
  }
  if (check && check.vision === true) return { ok: true, check };
  return { ok: false, check: check || { vision: null, model: null, reason: "" } };
}

function pictureNoticeWords(check) {
  const model = check.model ? ` (${check.model})` : "";
  if (check.vision === false) {
    return (
      `Your current model${model} can't see pictures, so it would answer as if ` +
      `the picture were not there. A picture model such as qwen2.5vl can be ` +
      `installed later - it needs more graphics memory; your planned second ` +
      `graphics card would help (once it is in, turn on Pictures in Settings, ` +
      `under Second graphics card). The picture is never sent to an online model ` +
      `instead. Send your words without it?`
    );
  }
  return (
    `Jarvis could not check whether your current model${model} can see pictures` +
    (check.reason ? ` (${check.reason.replace(/[.\s]+$/, "")})` : "") +
    `. If it can't, it will answer as if the picture were not there. The ` +
    `picture is never sent to an online model instead.`
  );
}

function showPictureNotice(message, check, provenance) {
  state.pictureHeld = message;
  state.pictureHeldTag = provenance || "typed";
  // The box was cleared on submit; put the words back so nothing is lost -
  // with where they came from, so a pasted question stays pasted.
  if (!dom.prompt.value.trim()) {
    dom.prompt.value = message;
    state.boxTag = state.pictureHeldTag;
    autoGrowPrompt();
  }
  dom.pictureNoticeText.textContent = pictureNoticeWords(check);
  // "Send it anyway" only when the answer is "could not tell". A clear no
  // gets no such button: sending a picture to a model known to be blind to
  // it only produces an answer that ignores it.
  dom.pictureAnyway.hidden = check.vision === false;
  dom.pictureNotice.hidden = false;
  syncWindowHeight();
  announce(dom.pictureNoticeText.textContent, "assertive");
  dom.pictureTextOnly.focus();
}

function hidePictureNotice() {
  state.pictureHeld = null;
  if (dom.pictureNotice) dom.pictureNotice.hidden = true;
}

/** Takes the held words back out of the box and sends them. */
function sendHeldWords() {
  const typed = dom.prompt.value.trim();
  const words = typed || state.pictureHeld || "";
  const tag = typed ? state.boxTag : state.pictureHeldTag;
  hidePictureNotice();
  if (!words) return;
  pushPromptHistory(words, tag);
  dom.prompt.value = "";
  state.boxTag = boxTagAfter(state.boxTag, "clear");
  autoGrowPrompt();
  send(words, tag);
}

dom.pictureTextOnly.addEventListener("click", () => {
  state.capture = null;
  dom.captureThumb.removeAttribute("src");
  syncAttachments();
  sendHeldWords();
});
dom.pictureAnyway.addEventListener("click", () => {
  state.pictureCleared = true;
  sendHeldWords();
});
dom.pictureKeep.addEventListener("click", () => {
  hidePictureNotice();
  syncWindowHeight();
  focusInput({ selectAll: false });
});

/* ==========================================================================
   Quick capture — note prefixes
   ========================================================================== */

/**
 * Splits a leading `#log` / `#joplin` prefix off the prompt.
 * Returns the target (or null) and the text with the prefix removed.
 */
function parseNotePrefix(text) {
  const match = text.match(/^\s*(#[a-z]+)(\s+|$)/i);
  if (!match) return { target: null, label: null, body: text };
  const spec = NOTE_PREFIXES[match[1].toLowerCase()];
  if (!spec) return { target: null, label: null, body: text };
  return { ...spec, body: text.slice(match[0].length) };
}

/** True only when the PC said this target is set up. */
function targetReady(target) {
  return state.noteTargets.known && state.noteTargets.targets.includes(target);
}

/** True when the PC said, for certain, that this target is NOT set up. */
function targetMissing(target) {
  return state.noteTargets.known && !state.noteTargets.targets.includes(target);
}

/** Mirrors the prefix in the chip beside the reactor as the user types. */
function syncNoteChip() {
  const { target, label } = parseNotePrefix(dom.prompt.value);
  state.noteTarget = target;
  dom.noteChip.hidden = !target;
  if (target) {
    dom.noteChip.dataset.target = target;
    const missing = targetMissing(target);
    dom.noteChip.dataset.unset = String(missing);
    dom.noteChipLabel.textContent = missing ? `${label} — not set up` : label;
  }
  syncWindowHeight();
}

/**
 * The help list shows a prefix only for a note app the PC is set up for,
 * and one line saying why when it shows none.
 */
function syncNotePrimer() {
  for (const row of document.querySelectorAll("[data-note-target]")) {
    row.hidden = !targetReady(row.dataset.noteTarget);
  }
  const line = document.getElementById("note-targets-line");
  if (!line) return;
  const none = !state.noteTargets.known || state.noteTargets.targets.length === 0;
  line.hidden = !none;
  if (none) line.lastElementChild.textContent = noTargetsLine(state.noteTargets);
}

/** Asks the PC which note apps are set up, then repaints what depends on it. */
async function refreshNoteTargets() {
  state.noteTargets = await loadTargets(invokeStrict);
  syncNotePrimer();
  syncNoteChip();
}

/* ==========================================================================
   Approval gates
   ========================================================================== */

/*
 * There used to be an `approvalFromChunk()` here that sniffed the chat stream
 * for anything that looked like a gate — `tier: "ask"`, `status:
 * "pending_approval"`, half a dozen id spellings — and opened a card from it.
 *
 * It is gone, and its absence is the point. `/api/pending` is the only place
 * that knows what is waiting, `jarvis_gate.pending()` is what fills it, and the
 * `risk` object that says what getting the answer wrong costs is derived there
 * at read time and exists nowhere else. A card built by guessing at chat chunks
 * had no risk to show and no way to know when something had already been
 * answered somewhere else.
 *
 * So the quickbar no longer decides what an approval is. Rust reads the queue
 * once, when the stream rings the bell, and every surface renders the same
 * list. This file's remaining job is to draw it.
 */

/**
 * Builds the markdown preview shown inside the approval card.
 *
 * `detail` is whatever the caller passed to `jarvis_gate.check()`, JSON-encoded
 * and truncated to 4000 characters by the gate — so it can arrive as an object,
 * as a string that no longer parses, or not at all. All three are drawn.
 */
function approvalPreview(approval) {
  const detail = approval.detail;

  if (typeof detail === "string") {
    return detail.trim()
      ? `\`\`\`\n${detail.trim()}\n\`\`\``
      : "_No detail was recorded for this action._";
  }
  if (detail && typeof detail === "object") {
    for (const [key, fence] of [
      ["diff", "diff"],
      ["command", "sh"],
      ["cmd", "sh"],
    ]) {
      if (typeof detail[key] === "string" && detail[key].trim()) {
        return `\`\`\`${fence}\n${detail[key].trim()}\n\`\`\``;
      }
    }
    for (const key of ["preview", "content", "body", "text", "summary"]) {
      if (typeof detail[key] === "string" && detail[key].trim()) return detail[key];
    }
    return `\`\`\`json\n${JSON.stringify(detail, null, 2)}\n\`\`\``;
  }
  if (approval.prompt.trim()) return approval.prompt.trim();
  return "_No detail was recorded for this action._";
}

/**
 * Colours a unified diff inside the preview.
 *
 * Operates on `textContent` and rebuilds the node from escaped pieces, so the
 * escape-first guarantee of the renderer still holds.
 */
function decorateDiff(container) {
  for (const code of container.querySelectorAll("pre code.language-diff")) {
    const html = code.textContent
      .split("\n")
      .map((line) => {
        const escaped = escapeHtml(line);
        if (/^(\+\+\+|---|@@|diff |index )/.test(line)) {
          return `<span class="diff-meta">${escaped || "&nbsp;"}</span>`;
        }
        if (line.startsWith("+")) {
          return `<span class="diff-add">${escaped || "&nbsp;"}</span>`;
        }
        if (line.startsWith("-")) {
          return `<span class="diff-remove">${escaped || "&nbsp;"}</span>`;
        }
        return `<span>${escaped || "&nbsp;"}</span>`;
      })
      .join("");
    code.innerHTML = html;
  }
}

/**
 * Renders a plan's options — docs/AUTONOMY-PROPOSALS.md §3a.
 *
 * Zero or one option: `#approval-options` stays empty and hidden, and the
 * static Approve button is the only way to approve — the exact behaviour
 * this card had before options existed at all. Two or more: the static
 * Approve button is hidden (Deny is not — denying never needs to say which
 * option) and one button per option appears instead.
 *
 * Those per-option buttons are rendered **disabled**. docs/JARVIS-API.md §8
 * found that `option_id` never reaches the server at all: `jarvis-link.js`'s
 * `decide()` does attach it, but `decide_approval` in Rust takes only
 * `(app, id, approved)`, so Tauri drops the extra argument on the way in —
 * there is no confirmed backend route that reads it
 * (docs/AUTONOMY-PROPOSALS.md §3b names one, unbuilt). Before this, clicking
 * "option B" sent the exact same `/api/approve` request as any other option
 * button would, with nothing telling the server which plan was meant — the
 * choice the buttons appeared to offer was never real. jarvis-client hit the
 * same gap first and took the same way out: see `needsChoice` in
 * `ApiModels.kt`, which disables approval the same way and for the same
 * reason. `title` explains this to whoever clicks; the option is still shown
 * so the plans on offer are at least legible, and Deny is untouched — it
 * never needed to say which option.
 */
function renderOptions(approval) {
  const options = Array.isArray(approval.options) ? approval.options : [];
  dom.approvalOptions.replaceChildren();
  const multiple = options.length > 1;
  dom.approvalOptions.hidden = !multiple;
  dom.approvalApprove.hidden = multiple;
  if (dom.approvalOptionsWhy) {
    dom.approvalOptionsWhy.hidden = !multiple;
    dom.approvalOptionsWhy.textContent = multiple
      ? `Jarvis offered ${options.length} ways to do this. The desktop can't yet tell it which one you picked, so approving is off here. Deny still works.`
      : "";
  }
  if (!multiple) return;
  for (const option of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "approval-option";
    btn.dataset.optionId = option.id;
    btn.disabled = true;
    btn.title = "Approving one option is not possible from the desktop yet. Deny still works.";
    const label = document.createElement("span");
    label.className = "opt-label";
    label.textContent = option.label; // textContent: model-authored text.
    btn.append(label);
    if (option.summary) {
      const summary = document.createElement("span");
      summary.className = "opt-summary";
      summary.textContent = option.summary;
      btn.append(summary);
    }
    dom.approvalOptions.append(btn);
  }
}

/**
 * Renders the gate and hands the keyboard to it.
 *
 * Called only from the queue subscription — never from the chat stream.
 */
function openApproval(approval) {
  // A different gate releases the "already answered" guard. It is kept across
  // `closeApproval` on purpose — see the note there — so this is the one place
  // that clears it, and it must clear only for a genuinely different id.
  if (state.decided && state.decided !== approval.id) state.decided = null;
  refreshApproval(approval);
  setPhase("approval");

  if (!dom.card.hidden) dom.cardStatusText.textContent = "Paused for approval";

  // The window, yes. The keyboard, no.
  //
  // Focus stays where the user put it. Moving it onto Approve is what turned a
  // stray Enter into an approval, and there is no version of "helpfully focus
  // the destructive button" that is safe on a surface that appears by itself.
  // The gate is announced instead: `role="alertdialog"` with `aria-live` on the
  // section carries it to a screen reader without stealing anything.
  // What the role used to imply, said explicitly and with the part that
  // actually matters — what getting it wrong costs.
  announce(
    `Approval required: ${approval.action}. ${riskLine(approval.risk)}. ` +
      "Approve and Deny are in the gate; Escape puts it aside.",
    "assertive"
  );

  setPinned(true, { silent: true });
  if (!dom.prompt.value.trim() && document.activeElement !== dom.prompt) {
    // Nothing half-typed and the composer is not where the user is looking:
    // put focus on the gate itself, not on either button, so Tab reaches the
    // buttons and Enter does nothing.
    dom.approval.focus({ preventScroll: true });
  }
  syncWindowHeight();
}

/** Paints a gate's contents without touching focus, pinning or the phase. */
function refreshApproval(approval) {
  // Whether this is a DIFFERENT gate, worked out before `state.approval` is
  // overwritten below - the note field depends on it.
  const fresh = !state.approval || state.approval.id !== approval.id;
  state.approval = approval;

  dom.approvalAction.textContent = approval.action;
  const target = approval.detail && typeof approval.detail === "object"
    ? approval.detail.target || approval.detail.note_target || approval.detail.to
    : null;
  dom.approvalTarget.hidden = !target;
  if (target) dom.approvalTarget.textContent = String(target);

  renderRaised(approval.raised);

  dom.approvalPreview.innerHTML = renderMarkdown(approvalPreview(approval));
  decorateDiff(dom.approvalPreview);
  renderOptions(approval);
  // ONLY on a different card. The old comment here said this was "safe
  // unconditionally" and it was not: the queue subscription calls
  // refreshApproval() for the SAME gate on every re-read - a resync, a
  // `raised` count ticking up, a risk re-derivation - and each one deleted
  // whatever was half-typed in the note, with no undo. The note is the
  // documented way to amend an action before approving it, so it is the text
  // in this window most worth not losing. A genuinely new card arrives with
  // the field already empty: closeApproval() clears it on every path that
  // ends a gate.
  if (fresh) dom.approvalNoteInput.value = "";

  // The risk line is the whole reason the gate is worth showing rather than
  // merely enforcing: `switch_model` and `send_email` are both tier `ask` and
  // arrive looking identical until this is on screen.
  // The risk line, plus what Esc does now — years of muscle memory say Esc
  // dismisses a window, and until this change it denied an action instead.
  dom.approvalHint.textContent = `${riskLine(approval.risk)} · Esc puts it aside`;
  dom.approvalHint.dataset.reversible = approval.risk
    ? approval.risk.reversible
    : "no";
  dom.approvalHint.dataset.reach = approval.risk ? approval.risk.reach : "outbound";

  const queue = currentQueue();
  const index = queue.items.findIndex((item) => item.id === approval.id);
  dom.approvalCount.hidden = queue.items.length < 2;
  if (queue.items.length > 1 && index >= 0) {
    dom.approvalCount.textContent = `${index + 1} of ${queue.items.length}`;
  }

  syncApprovalButtons();
  dom.approval.hidden = false;
  syncWindowHeight();
}

/* ==========================================================================
   Attention: the interruption budget and the daily brief
   --------------------------------------------------------------------------
   Two counts live near each other here and they must not be confused.

     link.approvals            things waiting for a DECISION — the gate queue
     link.attention.pending    things waiting to be TOLD to you — the digest

   The second is the tray badge and the notch count on the reactor's rim. A
   finished job adds to it and makes no sound, which is the whole point of the
   budget: the code path that finishes a job is not the code path that checks
   whether Jarvis may speak.
   ========================================================================== */

/** Paints the panel from the link, and opens or closes it as the count moves. */
function syncAttention() {
  const a = currentLink().attention;

  // Nothing has been read yet — say so rather than showing a confident zero
  // over a digest that was never fetched.
  if (!a.known) {
    dom.attention.hidden = true;
    return;
  }

  // Re-arm when something new arrives, so dismissing is not permanent.
  if (state.attentionOpen === false && a.pending > state.attentionDismissedAt) {
    state.attentionOpen = null;
  }
  const visible =
    state.attentionOpen === true ||
    (state.attentionOpen === null && a.pending > 0);
  const wasHidden = dom.attention.hidden;
  dom.attention.hidden = !visible;
  if (!visible) {
    state.digest = null;
    syncWindowHeight();
    return;
  }

  dom.attentionCount.textContent =
    a.pending === 0
      ? "Nothing waiting"
      : a.pending === 1
        ? "1 thing waiting to be told"
        : `${a.pending} things waiting to be told`;

  // Why nothing is being said out loud, when nothing is. `blockedBy` is the
  // server's own words — Quiet, Standby, a locked session, or muted — and it
  // outranks the count, because a budget with three left and a locked session
  // is still a budget of zero.
  dom.attentionBudget.textContent = a.blockedBy
    ? `Silent — ${a.blockedBy}`
    : `${a.remaining} of ${a.limit} spoken interruptions left today`;
  dom.attention.dataset.banked = String(a.banked);

  // Worded with its end date in both directions. There is no mute without one.
  dom.attentionMute.textContent = a.muted
    ? "Unmute"
    : "Mute until tomorrow";
  dom.attentionMute.title = a.muted
    ? "Let Jarvis speak again today"
    : "Jarvis stays silent until tomorrow. There is no mute without an end.";

  if (wasHidden || state.digest === null) loadDigest();
  syncWindowHeight();
}

/** Reads the brief. Called when the panel opens and when the count moves. */
async function loadDigest() {
  if (state.digestLoading) return;
  state.digestLoading = true;
  try {
    const brief = await fetchDigest();
    // `{"available": false}` means the arbiter is not installed. §7 says hide
    // the UI for a false capability rather than show an empty one.
    if (brief && brief.available === false) {
      state.digest = { items: [], unavailable: true };
    } else {
      state.digest = brief || { items: [] };
    }
  } catch (error) {
    console.error("[jarvis] digest unavailable:", error);
    state.digest = { items: [], error: String(error.message || error) };
  } finally {
    state.digestLoading = false;
    renderDigest();
  }
}

/**
 * Renders the brief in the order it arrived.
 *
 * **Nothing here sorts.** `jarvis_arbiter._rank` orders by what kind of thing
 * an item is and then by a priority its producer set — deliberately never by
 * urgency, because an item that could move itself up the list by saying it was
 * urgent would implement the attack `jarvis_content_risk` exists to catch. A
 * client that re-sorted would hand that ranking back to whoever wrote the text.
 */
function renderDigest() {
  const brief = state.digest;
  dom.digest.replaceChildren();

  if (!brief || brief.unavailable) {
    delete dom.attentionNote.dataset.tone;
    dom.attentionNote.textContent = brief
      ? "The digest is not available on this backend."
      : "Reading the brief…";
    dom.digestSeen.hidden = true;
    syncWindowHeight();
    return;
  }
  if (brief.error) {
    // Amber, and with a way to try again: a failed read used to be plain
    // text with nothing to do about it short of closing the panel.
    dom.attentionNote.textContent = `${brief.error} `;
    dom.attentionNote.dataset.tone = "warn";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "text-button";
    retry.textContent = "Retry";
    retry.addEventListener("click", () => {
      state.digest = null;
      renderDigest();
      loadDigest();
    });
    dom.attentionNote.append(retry);
    dom.digestSeen.hidden = true;
    syncWindowHeight();
    return;
  }
  delete dom.attentionNote.dataset.tone;

  const items = Array.isArray(brief.items) ? brief.items : [];
  for (const item of items) {
    dom.digest.append(digestRow(item));
  }

  const shown = items.length;
  const total = Number(brief.count || shown);
  dom.attentionNote.textContent =
    shown === 0
      ? "Nothing in the brief."
      : total > shown
        ? `Showing ${shown} of ${total}. Marking read approves nothing.`
        : "Marking read approves nothing.";
  dom.digestSeen.hidden = shown === 0;
  syncWindowHeight();
}

/**
 * One row of the brief.
 *
 * An approval row arrives with `opens_card: true` and an empty body — the
 * server deliberately does not send the detail here, and there is no route
 * that decides one from the digest. So the row is a link into the gate, not a
 * decision. This is also why there is no select-all, no bulk action and no
 * approve-all anywhere on this panel: if a decision is worth a gate, it is
 * worth one tap each, and batching is how a gesture stops being a decision.
 */
function digestRow(item) {
  const li = document.createElement("li");
  li.className = "digest-row";
  li.dataset.kind = String(item.kind || "note");
  li.dataset.priority = String(item.priority || "normal");

  const head = document.createElement("div");
  head.className = "digest-head";

  const kind = document.createElement("span");
  kind.className = "digest-kind";
  kind.textContent = String(item.kind || "note");
  head.append(kind);

  const title = document.createElement("span");
  title.className = "digest-title";
  title.textContent = String(item.title || "(untitled)");
  head.append(title);

  if (item.source) {
    const source = document.createElement("span");
    source.className = "digest-source";
    source.textContent = String(item.source);
    head.append(source);
  }
  li.append(head);

  if (item.opens_card) {
    // Not a decision — a way to reach the one place a decision can be made.
    const open = document.createElement("button");
    open.type = "button";
    open.className = "text-button digest-open";
    open.textContent = "Open the approval";
    open.addEventListener("click", () => openDigestApproval(item));
    li.append(open);
  } else if (item.body) {
    const body = document.createElement("p");
    body.className = "digest-body";
    body.textContent = String(item.body);
    li.append(body);
  }

  return li;
}

/**
 * Opens the gate for a digest row.
 *
 * The digest's `ref` is the approval id. The card is rendered from the *queue*
 * rather than from the digest row, because the queue is where `risk` and
 * `raised` live — the digest carries neither, on purpose. If the item is no
 * longer in the queue it has already been answered, and saying so is better
 * than opening an empty card.
 */
function openDigestApproval(item) {
  const id = String(item.ref || item.id || "");
  const match = currentQueue().items.find((row) => row.id === id);
  if (!match) {
    dom.attentionNote.textContent =
      "That one has already been answered — it will drop off the brief.";
    return;
  }
  // Same as Close: dismissed until the count rises, so the panel cannot land
  // back on top of the gate it just opened.
  state.attentionOpen = false;
  state.attentionDismissedAt = currentLink().attention.pending;
  dom.attention.hidden = true;
  openApproval(match);
}

/** Mutes or unmutes, then lets the refreshed link repaint the panel. */
async function toggleMute() {
  const a = currentLink().attention;
  dom.attentionMute.disabled = true;
  try {
    await setMuted(!a.muted);
  } catch (error) {
    console.error("[jarvis] mute failed:", error);
    dom.attentionNote.textContent = String(error.message || error);
  } finally {
    dom.attentionMute.disabled = false;
  }
}

/**
 * Marks the whole brief read.
 *
 * **This approves nothing**, and the button says so next to it. The server's
 * `mark_digest_delivered` stamps a delivery time; every approval in the brief
 * is still pending afterwards and still needs its own card.
 */
async function markBriefRead() {
  dom.digestSeen.disabled = true;
  try {
    await markDigestSeen([]);
    state.digest = null;
  } catch (error) {
    console.error("[jarvis] marking the digest read failed:", error);
    dom.attentionNote.textContent = String(error.message || error);
  } finally {
    dom.digestSeen.disabled = false;
  }
}

/**
 * Renders `raised` — the reason this is on screen at all.
 *
 * Four rules from JARVIS-API §4, and each one is a decision rather than a
 * style:
 *
 * - `text` is a chip. It already carries "(4th time today)" when the source has
 *   tripped this repeatedly; nothing here counts anything, because the count is
 *   the server's and a client that recounted would drift.
 * - `quote` goes inline, in quotation marks. Those are the attacker's words and
 *   showing them is the entire point — a card that said "this looked suspicious"
 *   teaches nothing.
 * - `context` is text from the page or document being judged, so it is never
 *   shown without the user asking. Hence a closed `<details>`, collapsed again
 *   on every render so the previous card's disclosure does not carry over.
 * - `source` is named, never quoted. It is an identifier the server chose, not
 *   content, and quoting it would suggest otherwise.
 *
 * All three strings go in through `textContent`. They are hostile text by
 * definition; the markdown renderer never sees them.
 *
 * There is deliberately no control here that clears the latch. It lasts ten
 * minutes, and the alternative is a button whose whole purpose is to undo a
 * safety rule under time pressure.
 */
function renderRaised(raised) {
  if (!raised) {
    dom.approvalRaised.hidden = true;
    dom.raisedChip.textContent = "";
    dom.raisedQuote.textContent = "";
    dom.raisedContext.textContent = "";
    return;
  }

  dom.raisedChip.textContent = raised.text || "This text tried to rush you";
  dom.raisedChip.dataset.code = raised.code || "rushed";

  dom.raisedSource.textContent = raised.source ? `from ${raised.source}` : "";
  dom.raisedSource.hidden = !raised.source;

  // Quoted with real quotation marks rather than a CSS pseudo-element, so the
  // words stay quoted when the card is copied or read by a screen reader.
  dom.raisedQuote.textContent = raised.quote ? `“${raised.quote}”` : "";
  dom.raisedQuote.hidden = !raised.quote;

  dom.raisedContext.textContent = raised.context || "";
  dom.raisedContextWrap.hidden = !raised.context;
  dom.raisedContextWrap.open = false;

  // The tier move, when the server reported one. It is the concrete fact —
  // "this would not have asked you at all" — and it is what makes the chip
  // more than a warning label.
  if (raised.fromTier && raised.toTier && raised.fromTier !== raised.toTier) {
    dom.approvalRaised.dataset.tiers = `${raised.fromTier} → ${raised.toTier}`;
  } else {
    delete dom.approvalRaised.dataset.tiers;
  }

  dom.approvalRaised.hidden = false;
}

/**
 * Puts the gate away without answering it.
 *
 * The item stays pending and stays counted; only this window stops showing it,
 * until the user asks for it back or a different one arrives. Without the
 * parked set the queue subscription would reopen it on the next event, which
 * is what made Esc feel like it did nothing.
 */
function parkApproval() {
  if (!state.approval) return;
  const action = state.approval.action;
  state.parked.add(state.approval.id);
  closeApproval();
  announce(`Put aside: ${action}. It is still waiting; nothing was decided.`);
  syncParkedBar();
  focusInput({ selectAll: false });
}

/**
 * The one-line reminder that something is still waiting after it was parked.
 *
 * Parking must not be a way to lose an approval. This is deliberately not a
 * decision surface — it is a way back to the card.
 */
function syncParkedBar() {
  const queue = currentQueue();
  const waiting = queue.items.filter((item) => state.parked.has(item.id));
  const hidden = Boolean(state.approval) || waiting.length === 0;
  dom.parked.hidden = hidden;
  if (hidden) {
    syncWindowHeight();
    return;
  }
  dom.parkedText.textContent =
    waiting.length === 1
      ? "1 approval is still waiting."
      : `${waiting.length} approvals are still waiting.`;
  syncWindowHeight();
}

/** Clears the gate. Called when it leaves the queue, however it left. */
function closeApproval() {
  state.approval = null;
  // `state.decided` is deliberately NOT cleared here. It is the guard that
  // stops an already-answered gate being answered again, and `decide_approval`
  // does not re-read the queue — so between answering and the server's next
  // `approval` event the tray still says "1 waiting" and its row reopens the
  // same card with live buttons. Clearing the guard on close disarmed it at
  // precisely the moment it was needed. `openApproval` clears it when a
  // DIFFERENT id arrives, which is the only time it should go.
  dom.approval.hidden = true;
  dom.approvalPreview.innerHTML = "";
  dom.approvalOptions.replaceChildren();
  dom.approvalOptions.hidden = true;
  dom.approvalApprove.hidden = false;
  dom.approvalNoteInput.value = "";
  renderRaised(null);
  // The pin was taken to hold the window open for the gate. Every path that
  // ends a gate has to give it back, not only the one where the user answered
  // here: an approval resolved on the phone used to leave a 750px always-on-top
  // window floating over everything until it was clicked and dismissed.
  if (!state.abort && !state.inFlight) setPinned(false, { silent: true });
  syncWindowHeight();
}

/**
 * Enables or disables the two buttons from the link state.
 *
 * A stale stream means the queue cannot be confirmed live, and answering one
 * that cannot be confirmed is how the same action gets approved twice.
 */
function syncApprovalButtons() {
  const link = currentLink();
  const blocked = link.stale || state.deciding;
  // A card whose request was cut off on its way here cannot be approved: what
  // is on screen is not all of what would run. Deny stays - refusing
  // something unread costs a retry, approving it is the thing to prevent.
  dom.approvalApprove.disabled = blocked || Boolean(state.approval && state.approval.cutOff);
  dom.approvalDeny.disabled = blocked;
  paintApprovalClock();
  // Not `= blocked`: the option buttons `renderOptions` builds are already
  // permanently disabled (see its own comment on why), and setting this to
  // `blocked` would re-enable them the moment the stream stopped being
  // stale.
  if (blocked) for (const opt of dom.approvalOptions.children) opt.disabled = true;
  if (link.stale && state.approval) {
    // "Offline" was wrong when the stream is connected and only the queue
    // could not be read; linkWords says which it is.
    dom.approvalHint.textContent =
      `${linkWords(link).short} — the approval queue cannot be confirmed, so nothing can be answered from here.`;
    state.hintIsStale = true;
  } else if (state.hintIsStale && state.approval && !state.deciding) {
    // Back to the risk line once the link catches up: it used to keep saying
    // the queue could not be confirmed after it had been.
    state.hintIsStale = false;
    dom.approvalHint.textContent = `${riskLine(state.approval.risk)} · Esc puts it aside`;
  }
  // The note is a separate action from deciding (see `state.noteBusy`'s own
  // comment) but it still needs the stream live to mean anything, and it
  // still needs to stop once a decision on THIS card is in flight or has
  // already landed — sending a note for a plan already being decided would
  // arrive after the fact.
  const noteBlocked = blocked || state.noteBusy || state.deciding
    || (state.approval && state.decided === state.approval.id);
  dom.approvalNoteInput.disabled = noteBlocked;
  dom.approvalNoteSend.disabled = noteBlocked;
}

/**
 * The line under the risk line: "Nothing runs until you decide", plus how
 * long the card has left (the gate refuses it by itself at the deadline -
 * approval-expiry.patch), or why Approve is off for a cut-off request.
 * Re-painted every second by the ticker below, and only this line: it is not
 * a live region, so the countdown is never read out.
 */
function paintApprovalClock() {
  const line = document.querySelector("#approval .approval-reassure");
  if (!line) return;
  const approval = state.approval;
  const parts = ["Nothing runs until you decide."];
  if (approval && approval.cutOff) {
    parts.push("This request was cut off before it reached this card, so it cannot be approved here - deny it and ask Jarvis for a shorter plan.");
  }
  const clock = approval ? expiryWords(approval.expiresAt) : "";
  if (clock) parts.push(clock);
  const text = parts.join(" ");
  if (line.textContent !== text) line.textContent = text;
}
setInterval(() => {
  if (state.approval && !dom.approval.hidden) paintApprovalClock();
}, 1000);

/**
 * Sends the decision and reports the outcome in the answer card.
 *
 * The decision itself goes to `decide_approval` in Rust — the one place that
 * talks to `/api/approve` and `/api/deny`, so the 409 that means "already
 * decided" is handled once rather than in each of three windows. The card
 * closes when the backend broadcasts the resolution, not when this returns,
 * so a decision taken in the widget closes the quickbar's copy the same way.
 */
async function decideApproval(approved, optionId = null) {
  const approval = state.approval;
  if (!approval || state.deciding) return;
  // `deciding` is released in `finally`, but the card only closes when the
  // backend broadcasts the resolution - so between those two moments a second
  // Ctrl+Enter used to send the same decision again. The id latch closes that
  // window; it is cleared when a different gate opens.
  if (state.decided === approval.id) return;

  state.decided = approval.id;
  state.deciding = true;
  syncApprovalButtons();
  dom.approvalHint.textContent = approved ? "Approving…" : "Denying…";

  try {
    await decideOnBackend(approval.id, approved, optionId);
    state.buffer += `${state.buffer.trim() ? "\n\n" : ""}> ${
      approved ? "Approved" : "Denied"
    } \`${approval.action}\` from the desktop spotlight.`;
    openCard(approved ? "Approved" : "Denied");
    paint({ immediate: true });
  } catch (error) {
    const message = String(
      (error && error.message) || error || "the decision could not be sent"
    );
    // The server answers 409 when the id is unknown, expired, or already
    // decided. That is not a failure to report as one — someone answered it,
    // possibly on the phone — so say so and let the queue update close the card.
    const handled = /409|already/i.test(message);
    dom.approvalHint.textContent = handled
      ? "Already handled somewhere else."
      : `${message} — nothing was decided. Try again.`;
    // Release the latch. It exists to stop a SECOND decision racing a
    // successful first one; a decision that never reached the server is not a
    // first one. Leaving it set made the gate permanently unanswerable —
    // both buttons re-enabled by `syncApprovalButtons` below, and every
    // subsequent click returning at the `state.decided === approval.id` guard
    // with no feedback at all. A 409 keeps the latch, because that one really
    // was answered, somewhere.
    if (!handled) state.decided = null;
  } finally {
    state.deciding = false;
    syncApprovalButtons();
    // Only if nothing is still streaming. `closeApproval` is careful about
    // exactly this and this path was not: answering a gate that arrived
    // mid-answer unpinned the window under the running stream, so clicking
    // away hid the spotlight and the answer with it.
    if (!state.abort && !state.inFlight) await setPinned(false, { silent: true });
  }
}

/**
 * Appends a line to the answer feed and makes sure the card is visible to
 * show it — this window's only status surface, the same one
 * `decideApproval` above already writes its own outcome into (there is no
 * separate flash strip here the way the widget has `#widget-flash`). Never
 * overwrites `card-status-text` while a gate or an active stream already
 * owns it; only opens the card when it was otherwise idle.
 */
function noteToFeed(line) {
  state.buffer += `${state.buffer.trim() ? "\n\n" : ""}> ${line}`;
  if (dom.card.hidden) {
    openCard(state.phase === "approval" ? "Paused for approval" : "Noted");
  }
  paint({ immediate: true });
}

/**
 * Sends a note before the first decision on the open card —
 * docs/AUTONOMY-PROPOSALS.md §3b. Approves nothing: the expected result is
 * a NEW proposal for the same id, arriving the normal way through the
 * queue, which `onQueue` already repaints from — this function only sends
 * the text and reports whether it landed, mirroring the widget's own
 * `sendNote`.
 */
async function sendNote() {
  const note = dom.approvalNoteInput.value.trim();
  if (!note || !state.approval || state.noteBusy) return;
  const id = state.approval.id;

  state.noteBusy = true;
  syncApprovalButtons();

  try {
    await amendOnBackend(id, note);
    dom.approvalNoteInput.value = "";
    noteToFeed("Note kept with this card. Nothing was approved or denied, and the card is unchanged. Jarvis reads your note together with your answer - to have it plan differently, deny the card.");
  } catch (error) {
    noteToFeed(String((error && error.message) || error));
  } finally {
    state.noteBusy = false;
    syncApprovalButtons();
  }
}

/* ==========================================================================
   Task controls - pause, stop, and inject-while-running
   docs/AUTONOMY-PROPOSALS.md §3d. Mirrors widget.js's identical section —
   same honesty rule, same draft backend, same "activity is the only source
   of truth" design. See widget.js for the fuller reasoning.
   ========================================================================== */

/**
 * Enables/disables the task-control buttons and picks Pause vs. Resume.
 *
 * The swap answers only to `state.taskActivity`, set in exactly one place —
 * the `onLink` handler below, reading the server's own broadcast — never by
 * a click here. A click can fail silently, reach a backend that has not
 * implemented pausing at all, or race a resolution that already happened;
 * the one thing this window can trust is what the server itself last said
 * it was doing.
 */
function syncTaskControls() {
  const paused = state.taskActivity === "paused";
  dom.btnTaskPause.hidden = paused;
  dom.btnTaskResume.hidden = !paused;
  dom.btnTaskPause.disabled = state.taskActionBusy;
  dom.btnTaskResume.disabled = state.taskActionBusy;
  dom.btnTaskStop.disabled = state.taskActionBusy;
  dom.taskNoteInput.disabled = state.taskNoteBusy;
  dom.btnTaskNoteSend.disabled = state.taskNoteBusy;
}

/**
 * Sends a pause, resume, or stop request for whatever Jarvis is running
 * right now, through `backend/task-control.patch`'s routes. A rejected
 * invoke (no route on this backend, nothing running, a stale link for
 * Resume) surfaces its real error rather than pretending the task's state
 * changed.
 *
 * Deliberately does not touch `state.taskActivity` on success. An invoke
 * that resolves only means the IPC round trip completed, not that Jarvis
 * paused, resumed, or stopped anything — the button swap has to wait for
 * the server's own next `activity` report, or it is a guess wearing the
 * shape of a fact.
 */
async function sendTaskAction(kind) {
  if (state.taskActionBusy) return;
  state.taskActionBusy = true;
  syncTaskControls();

  try {
    if (kind === "pause") {
      await pauseTask();
      noteToFeed(
        "Pause requested — sent. This button will only say Resume once " +
          "Jarvis itself reports it has actually paused."
      );
    } else if (kind === "resume") {
      await resumeTask();
      // Resume only ASKS (task-control.patch) - see widget.js.
      noteToFeed("Resume sent. Nothing runs yet: Jarvis shows an approval card listing the steps that are left, and continues only if you approve it.");
    } else {
      await stopTask();
      noteToFeed("Stop sent. Jarvis stops before its next step; steps already done stay done.");
    }
  } catch (error) {
    noteToFeed(String((error && error.message) || error));
  } finally {
    state.taskActionBusy = false;
    syncTaskControls();
  }
}

/**
 * Sends a note that applies to what the running task does next — it never
 * touches whatever step is already in flight, same rule as `sendNote()`
 * above for an approval that has not been decided yet.
 */
async function sendTaskNote() {
  const note = dom.taskNoteInput.value.trim();
  if (!note || state.taskNoteBusy) return;

  state.taskNoteBusy = true;
  syncTaskControls();

  try {
    await injectTaskNote(note);
    dom.taskNoteInput.value = "";
    noteToFeed(
      "Sent — applies to what Jarvis does next. Jarvis reads it when the " +
        "current step finishes; it changes no step you already approved."
    );
  } catch (error) {
    noteToFeed(String((error && error.message) || error));
  } finally {
    state.taskNoteBusy = false;
    syncTaskControls();
  }
}

/* ==========================================================================
   Streaming
   ========================================================================== */

/**
 * Pulls a text delta out of one decoded stream object, supporting the shapes
 * Jarvis, Ollama and OpenAI-compatible proxies each emit.
 */
function deltaFromChunk(chunk) {
  if (typeof chunk === "string") return chunk;
  if (!chunk || typeof chunk !== "object") return "";

  const choice = Array.isArray(chunk.choices) ? chunk.choices[0] : null;
  const fromChoice =
    choice &&
    ((choice.delta && choice.delta.content) ||
      (choice.message && choice.message.content) ||
      choice.text);
  const fromDelta =
    typeof chunk.delta === "string"
      ? chunk.delta
      : chunk.delta && chunk.delta.content;

  return (
    fromChoice ||
    (chunk.message && chunk.message.content) ||
    chunk.response ||
    fromDelta ||
    chunk.token ||
    chunk.content ||
    chunk.text ||
    ""
  );
}

/** True when a decoded object marks the end of the stream. */
function isTerminal(chunk) {
  if (!chunk || typeof chunk !== "object") return false;
  const choice = Array.isArray(chunk.choices) ? chunk.choices[0] : null;
  return (
    chunk.done === true ||
    chunk.finished === true ||
    chunk.event === "done" ||
    Boolean(choice && choice.finish_reason)
  );
}

/**
 * Consumes one line of the response body. Handles Server-Sent Events
 * (`data: {...}`), newline-delimited JSON, and bare text as a last resort.
 * Returns `true` when the stream should stop.
 */
function consumeLine(rawLine) {
  let line = rawLine.trim();
  if (!line) return false;

  // SSE comment / heartbeat. One kind says what the PC is waiting on
  // (chat-stream.patch): `: jarvis-status approval` while an approval card
  // waits - so the card says so instead of sitting on "Thinking…".
  if (line.startsWith(":")) {
    const status = /^:\s*jarvis-status\s+(\w+)/.exec(line);
    if (status) showWaitStatus(status[1]);
    return false;
  }

  // SSE fields other than `data:` carry nothing we render.
  if (/^(event|id|retry):/i.test(line)) return false;

  if (line.toLowerCase().startsWith("data:")) {
    line = line.slice(5).trim();
    state.turnFramed = true;
  }

  if (line === "[DONE]") {
    state.turnEnded = true;
    return true;
  }

  let chunk;
  try {
    chunk = JSON.parse(line);
  } catch {
    // Not JSON - treat it as a raw token, which is what a plain text stream
    // produces.
    appendDelta(line);
    return false;
  }

  if (chunk.error) {
    showError(String((chunk.error && chunk.error.message) || chunk.error));
    return true;
  }

  // A guess from the chunk only when the server has not said: every Ollama
  // chunk names a model, and that says nothing about where it ran.
  if (!state.routeFromHeader) {
    const route = routeFromPayload(chunk);
    if (route) applyRoute(route);
  }

  appendDelta(deltaFromChunk(chunk));

  const choice = Array.isArray(chunk.choices) ? chunk.choices[0] : null;
  if (choice && choice.finish_reason === "length") state.turnCutShort = true;

  const ended = isTerminal(chunk);
  if (ended) state.turnEnded = true;
  return ended;
}

/** What `: jarvis-status <word>` means, for the card's status line. */
const WAIT_STATUS = {
  approval: "Waiting for your approval…",
  working: "Working…",
  thinking: "Thinking…",
};

function showWaitStatus(word) {
  const text = WAIT_STATUS[word];
  if (!text || state.phase !== "streaming" || dom.card.hidden) return;
  if (dom.cardStatusText.textContent === text) return;
  dom.cardStatusText.textContent = text;
  if (word === "approval") announce("Waiting for your approval.");
}

/** Appends text to the buffer and schedules a repaint. */
function appendDelta(text) {
  if (!text) return;
  // The first token is the moment "thinking" becomes "streaming", and it is
  // the only honest moment for it. Both transports used to flip the label the
  // instant the request left — one of them before it left — so "Thinking…" was
  // on screen for a handful of milliseconds and the card claimed to be
  // streaming through the whole cold start of a local model, which is the one
  // stretch a person actually wants explained.
  if (!state.chunks) dom.cardStatusText.textContent = "Streaming";
  state.buffer += text;
  state.chunks += 1;
  updateStat();
  paint();
  checkForSpeakableSentence();
}

function updateStat() {
  const seconds = (performance.now() - state.startedAt) / 1000;
  dom.cardStat.textContent = `${state.chunks} chunks · ${seconds.toFixed(1)}s`;
}

/** Cancels the stream in flight, if there is one. */
function abortStream() {
  const abort = state.abort;
  if (!abort) return;
  state.abort = null;
  abort();
}

/**
 * Streams through the Rust backend over a Tauri channel.
 *
 * The channel carries raw response lines; the promise carries the terminal
 * state. That split means the frontend never has to infer "the stream ended"
 * from silence, and a transport failure arrives as a rejection rather than a
 * card that spins forever.
 */
async function streamViaBackend(payload) {
  const channel = new TAURI.core.Channel();
  let settled = false;

  channel.onmessage = (line) => {
    if (typeof line !== "string") return;
    // The answer's id, sent by stream_chat ahead of the answer itself - not
    // part of it, so it never reaches consumeLine.
    if (line.startsWith(TURN_LINE_PREFIX)) {
      state.turnId = line.slice(TURN_LINE_PREFIX.length);
      return;
    }
    // Which lane answered, from X-Jarvis-Route - the same kind of line.
    if (line.startsWith(ROUTE_LINE_PREFIX)) {
      try {
        applyHeaderRoute(JSON.parse(line.slice(ROUTE_LINE_PREFIX.length)));
      } catch {
        /* not a route - ignore it rather than show it */
      }
      return;
    }
    if (settled) return;
    // `consumeLine` returns true on the stream's own terminator, and on an
    // approval gate — both mean stop reading.
    if (consumeLine(line)) {
      settled = true;
      invoke("cancel_chat");
      // This used to stop here. Every `finishStream` call site is guarded by
      // `if (settled) return`, so a stream that ended with its own terminator
      // - which is every stream, the server proxies OpenAI-style
      // `data: [DONE]` - left the card in the `streaming` phase for ever: the
      // window never un-pinned, Escape aborted instead of dismissing, and the
      // re-entrancy guard in `send()` then silently discarded every prompt
      // after the first. Only the Stop button and a stream with no terminator
      // ever finished. `streamViaFetch` always did this correctly, which is
      // why browser preview never showed it.
      finishStream(state.phase === "error" ? "error" : "done");
    }
  };

  state.abort = () => {
    settled = true;
    invoke("cancel_chat");
    finishStream("done", "Stopped");
  };

  try {
    await invokeStrict("stream_chat", { ...payload, onEvent: channel });
    if (settled) return;
    settled = true;
    finishStream(state.phase === "error" ? "error" : "done");
  } catch (error) {
    if (settled) return;
    settled = true;
    showError(String((error && error.message) || error));
    finishStream("error");
    refreshHealth();
  }
}

/**
 * Browser-preview transport: a plain streaming fetch, used only when the page
 * is opened outside Tauri (`npm run dev` in a browser tab, or the headless
 * screenshot harness). It is subject to CORS and carries no token.
 */
async function streamViaFetch(payload) {
  const controller = new AbortController();
  state.abort = () => controller.abort();

  try {
    const response = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Jarvis-Client": JARVIS_CLIENT_HEADER,
      },
      body: JSON.stringify({
        messages: payload.messages,
        has_image: payload.hasImage,
        stream: true,
        auto: payload.auto,
        conversation_id: payload.conversationId,
        device: payload.device,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const hint =
        response.status === 403
          ? " — the server rejected this origin."
          : response.status === 400
            ? " — the server rejected the request body."
            : "";
      throw new Error(
        `the server answered HTTP ${response.status} ${response.statusText}${hint}`
      );
    }

    try {
      const header = response.headers.get("X-Jarvis-Route");
      if (header) applyHeaderRoute(JSON.parse(header));
    } catch {
      /* no usable route header - the badge keeps its guess */
    }

    if (!response.body) {
      consumeLine(await response.text());
      finishStream("done");
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;

      pending += decoder.decode(value, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop() || "";

      let stop = false;
      for (const line of lines) {
        if (consumeLine(line)) {
          stop = true;
          break;
        }
      }
      if (stop) {
        await reader.cancel().catch(() => {});
        break;
      }
    }

    if (pending.trim()) consumeLine(pending);
    finishStream(state.phase === "error" ? "error" : "done");
  } catch (error) {
    if (error && error.name === "AbortError") {
      finishStream("done", "Stopped");
      return;
    }
    const hint =
      error instanceof TypeError
        ? `Could not reach the Jarvis server at ${JARVIS_SERVER}. Is it running?`
        : String((error && error.message) || error);
    showError(hint);
    finishStream("error");
    refreshHealth();
  }
}

/**
 * Files a `#log` / `#joplin` / `#obs` note (and Alt+Shift+N, which arms the
 * first note app the PC is set up for).
 *
 * No chat turn and no model: the owner's own words go to the backend, which
 * writes them through the approval gate. The card shows the backend's answer
 * - "Filed in Logseq, journals/…", "Waiting for your approval…", or why it
 * was not filed - and never claims more than that answer says.
 */
async function fileFromBar(target, text) {
  const place = targetName(target);
  if (state.approval) closeApproval();
  state.turnId = null;
  paintAnswerMark();
  setPhase("done");
  openCard(`Filing in ${place}…`);
  state.buffer = "";
  paint({ immediate: true });
  // The PC said this app is not set up: say so, and send nothing. (When the
  // PC could not be asked, the note is sent, and the PC's own answer - it
  // refuses an app that is not set up, saying why - is what is shown.)
  if (targetMissing(target)) {
    dom.cardStatusText.textContent = "Not filed";
    state.buffer = notSetUp(target);
    paint({ immediate: true });
    announce(state.buffer);
    return;
  }
  if (!text) {
    dom.cardStatusText.textContent = "Nothing filed";
    state.buffer = `Nothing to file — type the note after the prefix.`;
    paint({ immediate: true });
    return;
  }
  state.inFlight = text;
  try {
    await fileNote(invokeStrict, target, text, (said) => {
      // The field is free again once the first answer is in.
      state.inFlight = null;
      dom.cardStatusText.textContent = !said.final
        ? "Waiting for approval"
        : said.tone === "ok"
          ? "Filed"
          : "Not filed";
      state.buffer = said.text;
      paint({ immediate: true });
      announce(said.text);
    });
  } catch (error) {
    showError(`The note was not filed. ${String((error && error.message) || error)}`);
  } finally {
    state.inFlight = null;
    commitWindowHeight();
  }
}

/**
 * Sends the prompt and streams the answer into the card.
 *
 * `provenance` is where the words came from - "typed", "voice",
 * "clipboard" or "pasted" (chat-history.js) - and rides on the user message
 * (JARVIS-API.md section 18). Anything else is sent as no tag, which the PC
 * treats as not the owner's own words.
 */
async function send(promptText, provenance = "typed") {
  const message = promptText.trim();
  if (!message) return;
  // A note prefix files the rest instead of asking anything - see fileFromBar.
  const prefixed = parseNotePrefix(message);
  if (prefixed.target) {
    if (state.abort || state.inFlight) return;
    await fileFromBar(prefixed.target, prefixed.body.trim());
    return;
  }
  // Guard on the live stream handle, not on the phase. The phase is moved to
  // `approval` and then `done` by the approval flow while the stream is still
  // open, so a phase check let a second `stream_chat` start alongside the
  // first - two channels writing into one buffer, and `state.abort` pointing
  // only at the newer one, so Stop could never reach the older.
  // `state.abort` is only assigned once the transport starts, and `send` has
  // an `await` before then, so the handle alone is not a synchronous latch.
  // `inFlight` is - it is set on the same tick as the guard, and cleared in
  // `finishStream`, which is the single funnel every ending passes through.
  if (state.abort || state.inFlight) return;
  state.inFlight = message;

  // A picture goes only to a model that can see it - see "A picture, and a
  // model that may not see it" above. A "no" leaves everything as it was.
  if (state.capture && !state.pictureCleared) {
    const { ok, check } = await pictureCanBeSeen();
    if (!ok) {
      state.inFlight = null;
      showPictureNotice(message, check, provenance);
      return;
    }
  }
  state.pictureCleared = false;
  hidePictureNotice();

  // An answered gate belongs to the turn that is ending, not the next one.
  if (state.approval) closeApproval();

  // Fold the just-finished turn into scrollback before wiping the buffer for
  // the new one — a follow-up asked seconds later used to erase the answer
  // it was a follow-up TO, with no way back short of asking again. Only a
  // completed turn is worth keeping; an error banner is not an answer.
  state.previousAnswer =
    state.phase === "done" && state.buffer.trim() && state.lastPrompt
      ? { prompt: state.lastPrompt, buffer: state.buffer }
      : null;
  renderPreviousAnswer();
  state.lastPrompt = message;

  state.buffer = "";
  state.chunks = 0;
  // A new answer, so no id and no mark until the server gives it one.
  state.turnId = null;
  state.turnMark = "none";
  paintAnswerMark();
  spokenUpTo = 0;
  // "Stop" silences one turn, not every turn after it: a new question is
  // allowed to be answered out loud again. Cleared only past the guard
  // above, so a push-to-talk barge-in whose send() was refused because the
  // old answer is still streaming leaves that old answer muted.
  speechMuted = false;
  // A new answer starts from no blocks, or the first paragraph of the second
  // reply never gets its entrance.
  paintedBlocks = 0;
  lastPaintAt = 0;
  state.startedAt = performance.now();

  setPhase("streaming");
  announce("Working on it.");
  openCard("Thinking…");
  dom.cursor.hidden = false;
  dom.stop.hidden = false;
  dom.answer.innerHTML = "";
  dom.cardStat.textContent = "";

  // Stay open while the answer streams, even if focus wanders.
  await setPinned(true, { silent: true });

  // Prefixed notes never get here (see the top of this function).
  const text = message;

  // A capture rides INSIDE the user message, not as a sibling `images` array.
  // The server forwards `messages` verbatim to /v1/chat/completions and reads
  // no `images` field anywhere, so the old shape sent the screenshot into a
  // void while `has_image` still routed the turn to a vision model.
  const content = state.capture
    ? [
        { type: "text", text },
        { type: "image_url", image_url: { url: state.capture } },
      ]
    : text;

  // Clipboard context rides as a system turn; the server validates an
  // OpenAI-shaped `messages` array and routes on `has_image`.
  //
  // The conversation so far goes FIRST, then this turn's own system turns,
  // then the question. Two reasons for that order. Ollama reuses what it has
  // already read only up to the first thing that changed, so the earlier
  // turns - identical from one request to the next - must lead, and the
  // per-turn note or clipboard block must come after them. And a system
  // message at position 0 makes Ollama drop the Modelfile's own SYSTEM
  // prompt, where the persona's rules live (memory-prefix.patch quotes the
  // line); with history in front, a follow-up keeps them. The very first
  // turn with a note or clipboard still puts a system message first, as it
  // always has.
  //
  // Screenshots are not kept in the conversation - only the words.
  state.turnQuestion = text;
  // Words sent with a picture are a picture's caption; the picture itself is
  // never kept in the conversation, only the words and this tag.
  state.turnProvenance = sentProvenance(provenance, Boolean(state.capture));
  state.turnFramed = false;
  state.turnEnded = false;
  state.turnCutShort = false;
  state.routeFromHeader = false;
  // A mark that failed on the last answer (a 503 from a busy database, say)
  // is tried again on this one: an answer that carries an id proves the
  // backend keeps them. It used to stay hidden until the app restarted.
  state.markUnavailable = false;
  syncNewConversation();
  const payload = {
    messages: [
      ...historyMessages(state.conversation),
      ...(state.clipboard
        ? [{ role: "system", content: `Context:\n${state.clipboard}` }]
        : []),
      userMessage(content, state.turnProvenance),
    ],
    hasImage: Boolean(state.capture),
    auto: true,
    // JARVIS-API.md section 18. Informational for the PC's History list;
    // stream_chat (commands.rs) passes on only a well-formed id and a
    // device it knows.
    conversationId: state.conversationId,
    device: "desktop",
  };

  if (IS_TAURI) {
    await streamViaBackend(payload);
  } else {
    await streamViaFetch(payload);
  }
}

/** Common teardown for every way a stream can end. */
/* ==========================================================================
   Right or wrong: the mark on one answer (feedback.patch)
   --------------------------------------------------------------------------
   Items 1 and 8 of docs/LEARNING-RESEARCH-2026-09-23.md. The server gives
   each answer an id (`turn_id` in X-Jarvis-Route); a mark on it counts,
   for each remembered fact used in that answer, whether it helped or hurt.
   A mark changes no memory. Enough "wrong" answers built on one fact raise a
   single "stop using this fact?" card in the Brain's review queue, which
   still needs its own decision.

   Shown only on a finished answer that has an id, for that answer alone.
   Pressing the mark that is already on takes it back. A backend without the
   patch sends no id (nothing shows); one with the id but without the route
   answers "not available", and the control hides itself again.
   ========================================================================== */

/** stream_chat's marker for the one line that is the answer's id. */
const TURN_LINE_PREFIX = "\u001fjarvis-turn:";
/** ...and for the one that is X-Jarvis-Route's lane, where and gate. */
const ROUTE_LINE_PREFIX = "\u001fjarvis-route:";

function paintAnswerMark() {
  if (!dom.answerMark) return;
  const show = Boolean(state.turnId) && state.phase === "done" && !state.markUnavailable;
  dom.answerMark.hidden = !show;
  if (!show) return;
  dom.markRight.setAttribute("aria-pressed", String(state.turnMark === "right"));
  dom.markWrong.setAttribute("aria-pressed", String(state.turnMark === "wrong"));
}

async function sendMark(mark) {
  const turnId = state.turnId;
  if (!turnId || state.markBusy) return;
  // Pressing the mark that is already on takes it back.
  const next = state.turnMark === mark ? "none" : mark;
  state.markBusy = true;
  dom.markRight.disabled = true;
  dom.markWrong.disabled = true;
  try {
    const out = await invokeStrict("mark_answer", { turnId, mark: next });
    if (turnId !== state.turnId) return; // a new answer has started
    if (out && out.available === false) {
      // This backend cannot take marks: hide the control, quietly.
      state.markUnavailable = true;
    } else {
      state.turnMark = next;
      dom.answerMarkNote.textContent =
        next === "none" ? "Mark taken back." : "Thanks — noted for this answer.";
    }
  } catch (error) {
    dom.answerMarkNote.textContent = "Could not send the mark.";
    console.error("[jarvis] mark failed:", error);
  } finally {
    state.markBusy = false;
    dom.markRight.disabled = false;
    dom.markWrong.disabled = false;
    paintAnswerMark();
  }
}

if (dom.markRight) dom.markRight.addEventListener("click", () => sendMark("right"));
if (dom.markWrong) dom.markWrong.addEventListener("click", () => sendMark("wrong"));

function finishStream(phase, statusText) {
  state.abort = null;
  state.inFlight = null;
  dom.cursor.hidden = true;
  dom.stop.hidden = true;

  // Into the conversation only when the answer really finished: not an
  // error, not Stopped (statusText), not empty, and not SSE that stopped
  // without its end marker. Read BEFORE the empty-answer placeholder below
  // is written into the buffer - that placeholder is not something Jarvis
  // said.
  const question = state.turnQuestion;
  state.turnQuestion = null;
  if (
    question &&
    phase !== "error" &&
    !statusText &&
    state.buffer.trim() &&
    !(state.turnFramed && !state.turnEnded)
  ) {
    state.conversation = commitExchange(
      state.conversation,
      question,
      state.buffer,
      state.turnProvenance
    );
  }

  // Stopped at the length limit: kept (it is what Jarvis said), but the
  // card says it is not the whole answer, instead of looking finished.
  const cutShort = state.turnCutShort && phase !== "error" && !statusText;
  state.turnCutShort = false;
  if (cutShort && state.buffer.trim()) {
    state.buffer += "\n\n_(Answer cut short: it reached the length limit. Ask \"go on\" for the rest.)_";
  }

  if (phase !== "error") {
    setPhase("done");
    dom.cardStatusText.textContent =
      statusText ||
      (state.buffer.trim() ? (cutShort ? "Cut short" : "Complete") : "No content returned");
    if (!state.buffer.trim()) {
      state.buffer = "_The server closed the stream without sending content._";
    }
  }

  updateStat();
  paint({ immediate: true });
  paintAnswerMark();

  // Once, at the end. The answer element carries no live region any more —
  // announcing a growing buffer per repaint is what left a screen reader
  // minutes behind the screen. The word count is the useful part: it tells
  // someone how much there is before they start reading it.
  if (phase !== "error") {
    const words = state.buffer.trim().split(/\s+/).filter(Boolean).length;
    announce(
      words
        ? `Answer complete, ${words} ${words === 1 ? "word" : "words"}.`
        : "The server closed the stream without sending content."
    );
  }

  // The stream is over, so settle the window on its final height immediately
  // rather than waiting out the throttle.
  commitWindowHeight();

  // A turn spoken to Jarvis gets a spoken answer back; a typed one stays
  // silent, the same way a phone call and a text message get different
  // replies. Read and cleared here, once, so a follow-up typed while this
  // window is still open does not keep talking back uninvited.
  //
  // Most of the reply was already queued sentence by sentence as it
  // streamed in (`checkForSpeakableSentence`, called from `appendDelta`) -
  // this is only the tail end: whatever came after the last sentence
  // boundary the stream happened to produce trailing whitespace for, which
  // a reply ending mid-sentence-looking punctuation (no space after the
  // final period, because there is nothing left to follow it) always
  // leaves behind.
  const wasVoiceTurn = state.voiceTurn;
  state.voiceTurn = false;
  if (wasVoiceTurn && phase !== "error" && !speechMuted) {
    const remainder = state.buffer.slice(spokenUpTo).trim();
    if (remainder) enqueueSpeech(remainder);
  }

  syncNewConversation();

  // Release the pin so clicking away dismisses the bar again.
  setPinned(false, { silent: true });
}

/**
 * "New conversation" shows once there is a conversation to forget, and not
 * while an answer is arriving (Stop is the control for that).
 */
function syncNewConversation() {
  if (!dom.newConversation) return;
  const n = state.conversation.length;
  dom.newConversation.hidden = n === 0 || Boolean(state.inFlight);
  dom.newConversation.title =
    n === 1
      ? "Your next question follows on from the last one. Start afresh instead."
      : `Your next question follows on from the last ${n}. Start afresh instead.`;
}

/**
 * Forgets the conversation and clears the card, leaving the window open for
 * a fresh question. Only this window's copy exists to forget; what Jarvis
 * has learned is kept on the backend and is not touched.
 */
function newConversation() {
  abortStream();
  state.turnQuestion = null;
  state.conversation = [];
  closeCard();
  announce("New conversation. Your next question starts fresh.");
  focusInput();
}

/* ==========================================================================
   Voice: push-to-talk in, a spoken reply out
   ========================================================================== */

/** Whether the microphone is currently open. Mirrors `dom.mic`'s
 *  `aria-pressed`, kept separately so a stray extra pointerup (a second
 *  finger, a mouse button released outside the window) cannot try to stop a
 *  recording that never started. */
let micRecording = false;

async function startPushToTalk() {
  if (micRecording || state.autoListening) return;
  // Barge-in: holding the mic to talk again is as clear a signal as this
  // app gets that whatever Jarvis was saying is done mattering right now.
  stopSpeaking();
  micRecording = true;
  dom.mic.setAttribute("aria-pressed", "true");
  try {
    await invokeStrict("start_voice_capture");
  } catch (error) {
    micRecording = false;
    dom.mic.setAttribute("aria-pressed", "false");
    announce(String((error && error.message) || error), "assertive");
  }
}

async function stopPushToTalk() {
  if (!micRecording) return;
  micRecording = false;
  dom.mic.setAttribute("aria-pressed", "false");
  try {
    const heard = await invokeStrict("stop_voice_capture");
    if (!heard.available) {
      announce(heard.reason || "Speech recognition is not available here.", "assertive");
      return;
    }
    if (!heard.isOwner) {
      // Deliberately vague rather than naming a score/threshold: the point
      // is that a voice which is not the owner's never becomes text, not to
      // explain how close it came.
      announce("That did not sound like you, so nothing was sent.", "assertive");
      return;
    }
    const text = heard.text.trim();
    if (!text) {
      announce("Nothing was heard.");
      return;
    }
    state.voiceTurn = true;
    // The PC's own speech route wrote these words (stop_voice_capture), so
    // they go as "voice"; the PC checks that against what it transcribed.
    send(text, "voice");
  } catch (error) {
    announce(String((error && error.message) || error), "assertive");
  }
}

/** Releasing push-to-talk outside the button (pointer leaves, or a second
 *  pointer cancels it) discards the clip rather than sending whatever was
 *  caught - the same "if you say no, nothing happens" contract the rest of
 *  this app holds everywhere else. */
function abandonPushToTalk() {
  if (!micRecording) return;
  micRecording = false;
  dom.mic.setAttribute("aria-pressed", "false");
  invoke("cancel_voice_capture");
}

/* ==========================================================================
   Voice: speaking a reply, one sentence at a time, and barge-in
   ========================================================================== */

/** Text already turned into speech (or queued to be), as an index into
 *  `state.buffer` - reset to 0 at the start of every turn in `send()`. Lets
 *  a voice-initiated reply start being SPOKEN well before the model has
 *  finished streaming it, rather than waiting for the last token like the
 *  original one-shot version of this did. */
let spokenUpTo = 0;
let speechQueue = [];
let speaking = false;
let currentAudio = null;
/** Set by "stop" (`stopSpeaking`) for the rest of the turn it landed in, and
 *  cleared only by the next `send()`. Without it, "stop" silenced only the
 *  sentence playing at that moment: the stream was still open, so the next
 *  complete sentence - and the tail in `finishStream` - queued itself again
 *  a moment later and Jarvis carried on talking. */
let speechMuted = false;
/** Bumped by every `stopSpeaking`. A `speak_reply` that was already on its
 *  way to the backend when "stop" landed comes back with an older number,
 *  and its clip is dropped instead of played. */
let speechGeneration = 0;
/** Settles the "wait for this clip to end" promise of whatever is playing,
 *  so a clip cut off by "stop" does not leave that wait pending forever. */
let finishCurrentClip = null;

/** A rough pass at making streamed markdown speakable. Not a renderer - just
 *  enough that "**bold**" is not read aloud as "asterisk asterisk bold
 *  asterisk asterisk", and a code block (rarely useful spoken at all) is
 *  skipped rather than read character by character. */
function stripMarkdownForSpeech(text) {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trim();
}

/** Looks for one or more complete sentences that have arrived since
 *  `spokenUpTo` and queues each to be spoken. A "complete" sentence needs
 *  end punctuation FOLLOWED BY whitespace - punctuation alone is not
 *  enough, because the stream may simply not have produced the next
 *  character yet, and speaking a sentence the model was about to keep
 *  extending would need it un-said a moment later. Not fooled-proof
 *  against "Dr." or "3.14" - a real sentence splitter is more machinery
 *  than a queue that is, worst case, a little choppier warrants. */
function checkForSpeakableSentence() {
  if (!state.voiceTurn || speechMuted) return;
  for (;;) {
    const unspoken = state.buffer.slice(spokenUpTo);
    const match = unspoken.match(/^([\s\S]*?[.!?])\s+/);
    if (!match) return;
    spokenUpTo += match[0].length;
    enqueueSpeech(match[1]);
  }
}

function enqueueSpeech(text) {
  if (speechMuted) return;
  const clean = stripMarkdownForSpeech(text);
  if (!clean) return;
  speechQueue.push(clean);
  drainSpeechQueue();
}

/** Speaks whatever is queued, one clip at a time, through the backend's
 *  TTS. Best effort throughout: a missing voice is logged, not shown as an
 *  error banner over a perfectly good answer already on screen. */
async function drainSpeechQueue() {
  if (speaking) return;
  if (speechMuted) {
    speechQueue = [];
    return;
  }
  const next = speechQueue.shift();
  if (next === undefined) return;
  speaking = true;
  const generation = speechGeneration;
  try {
    const dataUri = await invokeStrict("speak_reply", { text: next });
    // "Stop" may have landed while the backend was making this clip. If it
    // did, the clip is dropped here - playing it now would be exactly the
    // sentence the owner just asked Jarvis to stop saying.
    if (generation !== speechGeneration || speechMuted) return;
    const audio = new Audio(dataUri);
    currentAudio = audio;
    await audio.play();
    await new Promise((resolve) => {
      if (currentAudio !== audio) return resolve();
      finishCurrentClip = resolve;
      audio.onended = resolve;
      audio.onerror = resolve;
    });
  } catch (error) {
    console.info("[quickbar] spoken reply unavailable:", error);
  } finally {
    // A drain that "stop" overtook leaves the bookkeeping alone: stopSpeaking
    // already reset it, and a newer drain may own it by now.
    if (generation === speechGeneration) {
      currentAudio = null;
      finishCurrentClip = null;
      speaking = false;
      drainSpeechQueue();
    }
  }
}

/** Barge-in: discards anything still queued, stops whatever is playing right
 *  now, drops a clip still being made, and keeps the rest of this reply
 *  quiet even though it is still streaming in - called the moment the owner
 *  starts talking again, on either listening mode, and when the card
 *  closes. The next `send()` lets Jarvis speak again. */
function stopSpeaking() {
  speechMuted = true;
  speechGeneration += 1;
  speechQueue = [];
  if (currentAudio) {
    currentAudio.onended = null;
    currentAudio.onerror = null;
    currentAudio.pause();
    currentAudio = null;
  }
  if (finishCurrentClip) {
    const finish = finishCurrentClip;
    finishCurrentClip = null;
    finish();
  }
  speaking = false;
}

/** Whether Jarvis is talking: a clip is being made or played, or more are
 *  queued behind it. */
function jarvisTalking() {
  return speaking || speechQueue.length > 0;
}

/** "Hey Jarvis" listening's barge-in hook: Rust sends this when a clip
 *  that held the wake word, or the word "stop", comes back, so either cuts
 *  off a reply still being spoken (other sounds in the room do not).
 *  Push-to-talk gets the same treatment directly in `startPushToTalk`, since
 *  holding the button is itself the signal there.
 *
 *  Settings -> Voice, "Interrupt Jarvis while it talks" (barge-in.js): with
 *  it off, this is ignored while Jarvis is talking - the reply plays to the
 *  end, or until Esc closes the bar. */
listen("voice-speech-started", () => {
  if (ignoreWhileTalking(loadBargeIn(), jarvisTalking())) return;
  stopSpeaking();
});

/** The HUD's mic button (voice.rs `summon_push_to_talk`): the quickbar is
 *  already on screen by the time this arrives. Focus the mic and say how to
 *  use it, in words a sighted owner sees too (the placeholder) and not only
 *  the screen-reader announcement. Starts NO recording - holding the mic
 *  (or Space/Enter on it) is still the only thing that does. */
const PROMPT_PLACEHOLDER = dom.prompt ? dom.prompt.getAttribute("placeholder") : null;
function restorePromptPlaceholder() {
  if (!dom.prompt) return;
  if (PROMPT_PLACEHOLDER === null) dom.prompt.removeAttribute("placeholder");
  else dom.prompt.setAttribute("placeholder", PROMPT_PLACEHOLDER);
}
listen("voice-summon", () => {
  const how = state.autoListening
    ? "Listening for \"hey Jarvis\" - say it, then speak."
    : "Hold the mic button, or hold Space while it is selected, then speak and let go.";
  if (dom.prompt && !state.autoListening) {
    dom.prompt.setAttribute("placeholder", how);
    dom.prompt.addEventListener("input", restorePromptPlaceholder, { once: true });
    setTimeout(restorePromptPlaceholder, 15000);
  }
  dom.mic.focus();
  announce(how);
});

/** Turns "hey Jarvis" listening on or off (the command keeps its old name,
 *  `start_automatic_listening`). Mutually exclusive with push-to-talk.
 *  Turning it on when the PC's wake word is off does not open the
 *  microphone: it asks for the approval card, and the refusal text says so. */
async function setAutoListening(enabled) {
  if (enabled === state.autoListening) return;
  if (enabled) {
    let info = null;
    try {
      info = await invokeStrict("start_automatic_listening");
    } catch (error) {
      announce(String((error && error.message) || error), "assertive");
      return;
    }
    state.autoListening = true;
    dom.voiceAuto.setAttribute("aria-pressed", "true");
    dom.mic.dataset.auto = "true";
    dom.mic.title = 'Listening for "hey Jarvis"';
    // The name a screen reader reads, not only the tooltip: "Hold to talk"
    // on a button that no longer responds to being held was wrong.
    if (dom.micLabel) {
      dom.micLabel.textContent =
        'Listening for "hey Jarvis" - turn it off with the button next to this';
    }
    // `echoCancelling` (voice.rs ListenInfo): the microphone goes through
    // Windows' echo cancelling, so "stop" or "hey Jarvis" is heard over
    // Jarvis's own voice. An older build returns nothing - the plain line.
    // `microphone`: which one, by Windows' own name for it - both paths
    // open the default microphone, and a PC with a headset and a webcam
    // has more than one.
    announce(listeningLine(info));
  } else {
    state.autoListening = false;
    dom.voiceAuto.setAttribute("aria-pressed", "false");
    delete dom.mic.dataset.auto;
    dom.mic.title = "Hold to talk to Jarvis";
    if (dom.micLabel) {
      dom.micLabel.textContent =
        "Hold to talk to Jarvis - hold Space or Enter, speak, then let go";
    }
    await invoke("stop_automatic_listening");
  }
}

/** What the listener says it is hearing through, in one line. */
function listeningLine(info) {
  const mic = info && typeof info.microphone === "string" && info.microphone.trim()
    ? ` on ${info.microphone.trim()}`
    : "";
  // "Interrupt Jarvis while it talks" is off in Settings: say so, rather
  // than promise a "stop" that will be ignored.
  if (!loadBargeIn()) {
    return `Listening for "hey Jarvis"${mic}. While Jarvis talks, what it hears is ignored (Settings, Voice).`;
  }
  return info && info.echoCancelling
    ? `Listening for "hey Jarvis"${mic}. Say "stop" to interrupt Jarvis while it talks.`
    : `Listening for "hey Jarvis"${mic}.`;
}

/** The listener changed how it hears while still on (voice.rs
 *  VOICE_LISTENING): the echo-cancelled microphone stopped and it carries
 *  on through the ordinary one. Said, so the owner is not left expecting
 *  "stop" to work over Jarvis's voice when it no longer can. */
listen("voice-listening", (event) => {
  const info = event && event.payload;
  if (!info || !state.autoListening) return;
  announce(info.note ? `${info.note} ${listeningLine(info)}` : listeningLine(info));
});

/** One "hey Jarvis" utterance the listener cut and sent on its own - there
 *  is no command call waiting on this the way `stop_voice_capture` returns
 *  push-to-talk's result directly, so it arrives as an event instead. Only
 *  clips that held the wake word (or a broken engine) arrive here; the rest
 *  are dropped in Rust without a word. */
listen("voice-heard", (event) => {
  const heard = event && event.payload;
  if (!heard) return;
  if (!heard.available) {
    // The whole feature is broken, not just this one utterance - repeating
    // this every few seconds while automatic listening stays on would be
    // its own kind of noise, so it is said once and the mode turns itself
    // off rather than keep trying against an engine that is not there.
    announce(
      heard.reason || 'Speech recognition is not available here. Listening for "hey Jarvis" turned off.',
      "assertive"
    );
    setAutoListening(false);
    return;
  }
  // "Interrupt Jarvis while it talks" is off: nothing heard over a reply
  // is acted on, a new question included (barge-in.js).
  if (ignoreWhileTalking(loadBargeIn(), jarvisTalking())) return;
  if (!heard.isOwner) return; // ambient speech that is not the owner - ignored, not announced
  if (heard.awake) {
    // "Hey Jarvis." on its own: the PC is listening for the next sentence.
    announce("Listening.");
    return;
  }
  const text = String(heard.text || "").trim();
  if (!text) return;
  state.voiceTurn = true;
  send(text, "voice");
});

/* ==========================================================================
   Pin and dismiss
   ========================================================================== */

async function setPinned(pinned, { silent = false } = {}) {
  state.pinned = pinned;
  dom.pin.setAttribute("aria-pressed", String(pinned));
  if (!silent) {
    dom.pin.title = pinned
      ? "Unpin (auto-hide on focus loss)"
      : "Keep Jarvis open when it loses focus";
  }
  await invoke("set_quickbar_pinned", { pinned });
}

/** Clears the composer and hides the window. */
async function dismiss() {
  abortStream();
  closeApproval();
  dom.prompt.value = "";
  state.boxTag = boxTagAfter(state.boxTag, "clear");
  autoGrowPrompt();
  syncNoteChip();
  state.capture = null;
  state.clipboard = null;
  dom.captureThumb.removeAttribute("src");
  syncAttachments();
  closeCard();
  await setPinned(false, { silent: true });
  await invoke("hide_quickbar");
}

/* ==========================================================================
   Composer
   ========================================================================== */

/** Grows the textarea up to two lines before it starts scrolling. */
function autoGrowPrompt() {
  dom.prompt.style.height = "auto";
  dom.prompt.style.height = `${Math.min(dom.prompt.scrollHeight, 56)}px`;
  syncWindowHeight();
}

function focusInput({ selectAll = true } = {}) {
  dom.prompt.focus();
  if (selectAll) dom.prompt.select();
}

function submitCurrentPrompt() {
  // Enter does NOT approve, and the comment that used to sit here claimed the
  // opposite of what the code did — "the safe thing must be the deliberate
  // thing" above a call to `decideApproval(true)`.
  //
  // The failure it caused: a gate arrives while you are mid-sentence, the old
  // `openApproval` moved focus onto Approve, and the Enter you were about to
  // press to send your prompt approved an action you had not read. Chromium
  // fires `click` on keydown for a focused button, so there was no gap to
  // notice it in.
  //
  // Approving now takes the Approve button — reachable by Tab, and Enter works
  // on it natively once it is focused, which is a deliberate act rather than a
  // reflex. `quickActionable()` in jarvis-link.js is the gate any faster path
  // must go through, and it refuses anything carrying `raised`.
  const value = dom.prompt.value;
  if (!value.trim()) return;
  const tag = state.boxTag;
  pushPromptHistory(value.trim(), tag);
  dom.prompt.value = "";
  state.boxTag = boxTagAfter(tag, "clear");
  autoGrowPrompt();
  send(value, tag);
}

/* ==========================================================================
   Prompt history (Up / Down recall)
   ========================================================================== */

/** Records a submitted prompt, skipping an immediate repeat, and the tag it
 *  was sent with (the newest wins for a prompt sent twice). */
function pushPromptHistory(text, tag = "typed") {
  state.historyIndex = null;
  state.historyDraft = "";
  state.historyDraftTag = "typed";
  const { promptHistory, promptTags } = state;
  promptTags.set(text, tag);
  if (promptHistory[promptHistory.length - 1] === text) return;
  promptHistory.push(text);
  if (promptHistory.length > PROMPT_HISTORY_LIMIT) {
    const gone = promptHistory.shift();
    if (!promptHistory.includes(gone)) promptTags.delete(gone);
  }
}

/**
 * Moves through `state.promptHistory`. `direction` is -1 for older (Up) or
 * +1 for newer (Down). Returns whether it moved anything, so the caller
 * knows whether to swallow the keystroke or let the caret behave normally.
 *
 * Entering history stashes whatever was being typed in `historyDraft`, and
 * stepping past the newest entry restores exactly that — so reconsidering
 * and pressing Down back to the bottom never loses a half-written prompt.
 */
function recallHistory(direction) {
  const { promptHistory } = state;
  if (!promptHistory.length) return false;

  if (state.historyIndex === null) {
    if (direction > 0) return false; // nothing newer than "not browsing"
    state.historyDraft = dom.prompt.value;
    state.historyDraftTag = state.boxTag;
    state.historyIndex = promptHistory.length - 1;
  } else {
    const next = state.historyIndex + direction;
    if (next < 0) return true; // already at the oldest; swallow, don't wrap
    if (next >= promptHistory.length) {
      state.historyIndex = null;
      dom.prompt.value = state.historyDraft;
      state.boxTag = state.historyDraftTag;
      autoGrowPrompt();
      placeCaretForRecall(direction);
      return true;
    }
    state.historyIndex = next;
  }

  dom.prompt.value = promptHistory[state.historyIndex];
  // A recalled prompt is sent with the tag it was first sent with.
  state.boxTag = state.promptTags.get(dom.prompt.value) || "typed";
  autoGrowPrompt();
  placeCaretForRecall(direction);
  return true;
}

/**
 * Setting `.value` leaves the caret wherever the browser defaults to, which
 * is not consistently "somewhere that lets the SAME key keep working" — so
 * without this, one Up press recalled correctly and a second, from wherever
 * the caret landed, silently did nothing. Up parks it at the start, Down at
 * the end, matching each key's own boundary check below.
 */
function placeCaretForRecall(direction) {
  const pos = direction < 0 ? 0 : dom.prompt.value.length;
  dom.prompt.setSelectionRange(pos, pos);
}

/* ==========================================================================
   Event wiring
   ========================================================================== */

dom.prompt.addEventListener("input", (event) => {
  // A real keystroke, as opposed to `recallHistory` assigning `.value`
  // directly (which fires no `input` event) — so typing anything always
  // breaks out of history browsing, the same way a shell's would.
  state.historyIndex = null;
  // Where the words came from (JARVIS-API.md section 18). A paste or a drop
  // is tagged by its own event below, which fires first; any other edit
  // makes a clipboard snippet the owner's own typing, and an emptied box
  // starts again as typed.
  const type = (event && event.inputType) || "";
  if (type !== "insertFromPaste" && type !== "insertFromDrop") {
    state.boxTag = boxTagAfter(state.boxTag, "edit", dom.prompt.value);
  }
  autoGrowPrompt();
  syncNoteChip();
});

// Pasted or dropped text is not the owner's own words, whatever is typed
// around it, until the box is empty again (chat-history.js boxTagAfter).
for (const kind of ["paste", "drop"]) {
  dom.prompt.addEventListener(kind, () => {
    state.boxTag = boxTagAfter(state.boxTag, "paste");
  });
}

dom.prompt.addEventListener("keydown", (event) => {
  // Enter sends; Shift+Enter inserts a newline.
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitCurrentPrompt();
    return;
  }

  // A single-line prompt has no "line above" or "line below" for the arrow
  // key to reach anyway, so recall always applies there. A multi-line one
  // (Shift+Enter) does, so recall only claims the key at the very start or
  // end of the whole text — anywhere else, the caret should move a line
  // the ordinary way. Already-selected text counts as "not at an edge";
  // collapse it first if that's the intent.
  const singleLine = !dom.prompt.value.includes("\n");
  if (event.key === "ArrowUp") {
    const atStart = dom.prompt.selectionStart === 0 && dom.prompt.selectionEnd === 0;
    if ((singleLine || atStart) && recallHistory(-1)) event.preventDefault();
    return;
  }
  if (event.key === "ArrowDown") {
    const atEnd =
      dom.prompt.selectionStart === dom.prompt.value.length &&
      dom.prompt.selectionEnd === dom.prompt.value.length;
    if ((singleLine || atEnd) && recallHistory(1)) event.preventDefault();
  }
});

// Esc is handled at the document level so it also works while focus sits on a
// button inside the card.
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    // Esc parks the gate; it does not deny it. In a spotlight overlay Esc means
    // "close this", and wiring the most reflexive key in the app to a decision
    // meant people answered a gate believing they had dismissed a window.
    //
    // Parking keeps the item in the queue — it is still pending, the tray still
    // counts it, and the bar below says so — but stops it reopening over
    // whatever the user does next. Denying takes the Deny button.
    if (state.approval) {
      parkApproval();
      return;
    }
    // The first Esc stops a running stream; a second one dismisses the window.
    if (state.abort) {
      abortStream();
      return;
    }
    dismiss();
    return;
  }

  // Ctrl+Enter forces a send from anywhere in the window.
  if (event.key === "Enter" && event.ctrlKey) {
    event.preventDefault();
    submitCurrentPrompt();
  }
});

dom.stop.addEventListener("click", abortStream);

if (dom.newConversation) dom.newConversation.addEventListener("click", newConversation);

dom.copy.addEventListener("click", async () => {
  const text = state.buffer.trim();
  if (!text) return;
  await invoke("write_clipboard", { text });
  const original = dom.copy.textContent;
  dom.copy.textContent = "Copied";
  setTimeout(() => {
    dom.copy.textContent = original;
  }, 1200);
});

dom.pin.addEventListener("click", () => setPinned(!state.pinned));

// Push-to-talk: pointer down starts, pointer up sends, the pointer leaving
// the button (or a second pointer cancelling it) abandons the clip rather
// than sending it. `click` fires no `mic` handler at all - a click that
// isn't a hold-and-release is not this control's gesture.
dom.mic.addEventListener("pointerdown", (event) => {
  event.preventDefault(); // do not steal focus from wherever it already is
  startPushToTalk();
});
dom.mic.addEventListener("pointerup", stopPushToTalk);
dom.mic.addEventListener("pointerleave", abandonPushToTalk);
dom.mic.addEventListener("pointercancel", abandonPushToTalk);
// Keyboard: Space/Enter while the button is focused. `keydown` fires
// repeatedly while held, so `startPushToTalk` guards on `micRecording`
// already being true; `event.repeat` skips the redundant calls outright.
dom.mic.addEventListener("keydown", (event) => {
  if (event.repeat || (event.key !== " " && event.key !== "Enter")) return;
  event.preventDefault();
  startPushToTalk();
});
dom.mic.addEventListener("keyup", (event) => {
  if (event.key !== " " && event.key !== "Enter") return;
  event.preventDefault();
  stopPushToTalk();
});
dom.voiceAuto.addEventListener("click", () => setAutoListening(!state.autoListening));

dom.approvalApprove.addEventListener("click", () => decideApproval(true));
dom.approvalDeny.addEventListener("click", () => decideApproval(false));
dom.approvalNoteSend.addEventListener("click", sendNote);
dom.approvalNoteInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendNote();
  }
});

dom.btnTaskPause.addEventListener("click", () => sendTaskAction("pause"));
dom.btnTaskResume.addEventListener("click", () => sendTaskAction("resume"));
dom.btnTaskStop.addEventListener("click", () => sendTaskAction("stop"));
dom.btnTaskNoteSend.addEventListener("click", sendTaskNote);
dom.taskNoteInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendTaskNote();
  }
});

dom.captureRemove.addEventListener("click", () => {
  state.capture = null;
  dom.captureThumb.removeAttribute("src");
  syncAttachments();
  focusInput({ selectAll: false });
});

dom.clipboardRemove.addEventListener("click", () => {
  state.clipboard = null;
  syncAttachments();
  focusInput({ selectAll: false });
});

// Links open in the real browser, never inside the WebView.
//
// Bound to the shell rather than to `#answer`: the approval preview renders
// model-authored text through the same linkifier, and a click there was a real
// navigation that took the window off index.html with no way back - the app
// was gone until relaunch.
document.addEventListener("click", (event) => {
  const anchor = event.target.closest("a[data-external]");
  if (!anchor) return;
  event.preventDefault();
  if (IS_TAURI) {
    // The backend validates the URL and hands it to the OS shell; a WebView
    // `window.open` would either be swallowed or open inside the app.
    invoke("open_external_url", { url: anchor.href });
  } else {
    window.open(anchor.href, "_blank", "noopener");
  }
});

/* ==========================================================================
   Backend events
   ========================================================================== */

listen("focus-input", () => {
  focusInput();
  refreshHealth();
});

listen("clipboard-inject", (event) => {
  const text = String(event.payload || "");
  if (!text.trim()) return;
  attachClipboard(text);
  // A short snippet is more useful in the box; a long one becomes context.
  // In the box it is tagged "clipboard" until the owner edits it.
  if (text.length <= 200 && !dom.prompt.value.trim()) {
    dom.prompt.value = text;
    state.boxTag = boxTagAfter(state.boxTag, "clipboard");
    autoGrowPrompt();
  }
  focusInput({ selectAll: false });
});

listen("screen-captured", (event) => {
  const payload = event.payload;
  if (!payload || !payload.dataUri) return;
  attachCapture(payload);
  if (!dom.prompt.value.trim()) {
    dom.prompt.value = "What am I looking at?";
  }
  autoGrowPrompt();
  focusInput();
});

listen("quick-note-summon", (event) => {
  const asked = String(event.payload || "logseq");
  // Alt+Shift+N always asks for Logseq; if the PC is not set up for that,
  // arm the first note app it is set up for instead.
  const ready = state.noteTargets.known ? state.noteTargets.targets : [];
  const target = ready.includes(asked) || !ready.length ? asked : ready[0];
  const prefix = ARM_PREFIX[target] || ARM_PREFIX.logseq;
  // Keep whatever the user had already typed; just arm the destination.
  const existing = dom.prompt.value.trim();
  const { target: current, body } = parseNotePrefix(dom.prompt.value);
  dom.prompt.value = current
    ? `${prefix}${body.trim()}`
    : `${prefix}${existing}`;
  autoGrowPrompt();
  syncNoteChip();
  focusInput({ selectAll: false });
  // Put the caret after the prefix so typing continues the note.
  const caret = dom.prompt.value.length;
  dom.prompt.setSelectionRange(caret, caret);
});

listen("capture-failed", (event) => {
  showError(`Desktop capture failed: ${String(event.payload || "unknown error")}`);
});

listen("health-report", (event) => applyHealth(event.payload));

// `approval-resolved` fires the instant a decision is accepted, ahead of the
// queue re-read that follows it. Closing here as well as on the queue update
// means the card goes away when the button is pressed rather than one round
// trip later — and closing twice is harmless.
listen("approval-resolved", (event) => {
  const resolved = event.payload;
  if (!state.approval) return;
  if (resolved && resolved.id && String(resolved.id) !== state.approval.id) return;
  closeApproval();
  setPhase("done");
  paint({ immediate: true });
});

listen("pin-changed", (event) => {
  state.pinned = Boolean(event.payload);
  dom.pin.setAttribute("aria-pressed", String(state.pinned));
});

/* ==========================================================================
   Boot
   ========================================================================== */

applyRoute(DEFAULT_ROUTE);
syncNoteChip();
syncNotePrimer();
refreshNoteTargets();
// Asked again each time the bar comes up, so a vault set up since shows.
window.addEventListener("focus", () => refreshNoteTargets());
autoGrowPrompt();
syncWindowHeight();
refreshHealth();
focusInput();

// One stream, owned by Rust, fanned out to all three surfaces. This window
// subscribes; it does not connect, and it does not poll.
followTheme();
// Ctrl+= / Ctrl+- / Ctrl+0. Every size here is in `px` and a Tauri window
// has no browser chrome, so without this there is no way to make the text
// bigger anywhere in the app. The window re-measures after each step.
followZoom(() => syncWindowHeight());
syncPrimerKeys();
syncTaskControls();
startVoice(dom.root);
startLink();

let lastConnected = null;
onLink((link) => {
  // The Jarvis dot comes off the stream now. A held-open connection is a
  // stronger liveness signal than a probe that succeeded a moment ago, and it
  // costs nothing.
  const dot = dom.services.querySelector('[data-service="jarvis"]');
  if (dot) {
    dot.dataset.online = String(link.connected);
    dot.setAttribute(
      "aria-label",
      `Core: ${link.connected ? "event stream live" : "not answering"}`
    );
    dot.title = link.connected
      ? `Jarvis: event stream live${link.activity === "idle" ? "" : ` · ${link.activity}`}`
      : `Jarvis: ${link.error || "no event stream"}`;
  }
  // The offline bar, and the one thing there is to do about it. Also shown
  // while connected but stale - the stream is up and the queue could not be
  // read, so nothing can be approved - which used to show no words at all
  // while Approve and Deny quietly went grey. The words are the shared ones
  // (linkWords); before the first hello it says "Connecting…" rather than
  // naming an address that failed, because nothing has failed yet.
  const words = linkWords(link);
  const wasOffline = !dom.offline.hidden;
  dom.offline.hidden = words.canAct;
  if (!words.canAct) {
    dom.offlineText.textContent = words.text;
    dom.offline.dataset.tone = words.tone;
    // Once, on the transition. A live region that repeated this on every
    // reconnect attempt would talk over everything else in the window.
    if (!wasOffline) announce(dom.offlineText.textContent, "assertive");
  }
  // The model and lane in the route chip are last known while stale; the
  // phone drops the same extras.
  const showModel = !link.stale && Boolean(dom.routeModel.textContent);
  dom.routeModel.hidden = !showModel;
  dom.routeSep.hidden = !showModel;
  syncWindowHeight();

  if (!link.connected && state.route.tier !== "offline") {
    applyRoute({
      tier: "offline",
      label: "Offline",
      // "core unreachable" was a message sitting in the slot that names a
      // model. The reason belongs in the tooltip; the slot stays empty.
      model: null,
      why: link.error
        ? `No event stream: ${link.error}`
        : `No event stream yet. Connecting to ${link.base || "the address set in Settings"}.`,
    });
  } else if (link.connected && state.route.tier === "offline") {
    applyRoute(DEFAULT_ROUTE);
  }

  // Ollama and LiteLLM are not on the bus, so they are re-probed when the link
  // changes state — which is the moment their answer is most likely to differ.
  if (lastConnected !== null && lastConnected !== link.connected) refreshHealth();
  lastConnected = link.connected;

  // Section B: the reactor talks. `faceState()` is the composed state the
  // arbiter would serve if any route served it, and `speaking` / `listening`
  // are the only two the envelope cares about. Everything else stops the loop.
  //
  // This is deliberately NOT `data-state`, which is this window's own phase
  // machine (idle / streaming / done / error / approval) and says nothing
  // about audio. A gate can be open while Jarvis is mid-sentence.
  setVoiceMode(faceState(link));

  // Live progress — docs/AUTONOMY-PROPOSALS.md §3c — and pause/stop/inject
  // for whatever it describes — §3d. Mirrors widget.js's onLink handling
  // exactly: progress only while `activity === "working"`; the task
  // controls stay up through "paused" too, since a paused task still has a
  // live card worth acting on, and both go away the moment activity drops
  // to anything else, so a stale Resume can never carry into a new task.
  const workingNow = link.connected && link.activity === "working";
  const progressDetail = workingNow ? link.activityDetail : "";
  dom.progressLine.hidden = !progressDetail;
  if (progressDetail) dom.progressLine.textContent = progressDetail;

  state.taskActivity = link.connected ? link.activity : "idle";
  dom.taskControls.hidden = state.taskActivity !== "working" && state.taskActivity !== "paused";
  syncTaskControls();
  syncWindowHeight();

  syncApprovalButtons();
  syncAttention();
});

onQueue((queue) => {
  // Anything answered elsewhere stops being parked — the set must not grow for
  // ever, and an id that has left the queue is not waiting for anything.
  const live = new Set(queue.items.map((item) => item.id));
  for (const id of [...state.parked]) if (!live.has(id)) state.parked.delete(id);

  const open = queue.items.find((item) => !state.parked.has(item.id)) || null;
  syncParkedBar();
  if (!open) {
    if (state.approval) {
      // It left the queue: answered here, in the widget, on the phone, or it
      // expired. Either way there is nothing left to decide.
      closeApproval();
      setPhase(state.phase === "approval" ? "done" : state.phase);
      paint({ immediate: true });
    }
    return;
  }
  // A re-read of the same gate must refresh it in place, not reopen it.
  // These two branches used to be the identical statement - the `if` was dead
  // code - so every queue re-read stole focus from the input mid-typing and
  // re-pinned the window, and a stale read that still carried an already
  // answered id put its card back with live buttons.
  const same = state.approval && state.approval.id === open.id;
  if (same) {
    // `risk` is derived per read and must never be cached against an id, so
    // the card takes the new copy - but quietly. `raised` is stored on the
    // row rather than derived, but it is re-read here for the same reason:
    // one source, every time.
    refreshApproval(open);
    return;
  }
  if (state.decided === open.id) {
    // Answered here; the resolution broadcast just has not landed yet.
    return;
  }
  openApproval(open);
});

dom.parkedShow.addEventListener("click", () => {
  const next = currentQueue().items.find((item) => state.parked.has(item.id));
  if (!next) return;
  state.parked.delete(next.id);
  openApproval(next);
  syncParkedBar();
});

dom.offlineRetry.addEventListener("click", async () => {
  // Cuts the backoff short rather than waiting it out. Saying so matters: the
  // stream can sit in a 30s backoff, and a button that looked like it did
  // nothing is how the old "Offline" dead end felt even once it had a button.
  dom.offlineText.textContent = "Reconnecting…";
  announce("Reconnecting.");
  await invoke("refresh_link");
  refreshHealth();
});

dom.attentionMute.addEventListener("click", toggleMute);
dom.digestSeen.addEventListener("click", markBriefRead);
dom.attentionClose.addEventListener("click", () => {
  // Closing hides the panel until something new arrives or the tray asks for
  // it again. It does not mark anything read: those are different actions and
  // conflating them would silently clear a brief nobody looked at.
  state.attentionOpen = false;
  state.attentionDismissedAt = currentLink().attention.pending;
  dom.attention.hidden = true;
  syncWindowHeight();
});

// The tray's approvals row opens the gate here rather than in the HUD: this is
// the surface that renders the risk line and the `raised` block.
if (IS_TAURI) {
  TAURI.event.listen("show-approval", () => {
    const queue = currentQueue();
    const next = queue.items[0];
    if (!next) return;
    state.parked.delete(next.id);
    openApproval(next);
    syncParkedBar();
  });
}

// The tray's "N things waiting" row and the widget both open the brief here.
if (IS_TAURI) {
  TAURI.event.listen("show-digest", () => {
    state.attentionOpen = true;
    state.digest = null;
    syncAttention();
  });
}

console.info(
  `[jarvis] spotlight ready - backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
);
