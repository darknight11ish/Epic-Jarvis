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
  onEvent,
  onLink,
  onQueue,
  pauseTask,
  reconnect as reconnectLink,
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
import { startVoice, setVoiceMode, setLevel, attachSpeechSource } from "./voice.js";
import {
  lookLine,
  markMessage,
  refusedWords,
  SEEN as LOOK_SEEN,
  stripShown,
  watchOn,
  watchSign,
  DROP as LOOK_DROP,
  lookHeld,
} from "./look-rules.js";
import { followClip, trackFor } from "./face-voice.js";
import { ignoreWhileTalking, loadBargeIn } from "./barge-in.js";
import {
  createCutOff,
  createInterruptFlow,
  createMomentFlow,
  flowFromStatus,
  HEARD_SOUND,
  heardSoundSamples,
  isToolStart,
  loadHeard,
  loadMoment,
  PAUSE,
  RESUME,
  STOP,
  WAIT_MAX_MS,
} from "./voice-flow.js";
import {
  createToolWatch,
  mayReadAloud,
  onlyReadAloudToolsBetween,
  privacyFromHeard,
  PRIVATE_LINE,
  screenReadBetween,
  TOOL_WORDS,
  toolRanBetween,
  toolsKnownBetween,
} from "./private-speech.js";
// The renderer the answer card and the approval preview use - see markdown.js.
import { escapeHtml, renderMarkdown } from "./markdown.js";
import { approvalPlainText, isEmailCard } from "./email-sending.js";
// "Forget a time frame": where the Brain opens after "forget what you learned
// last week" (openBrainFromRoute).
import { BRAIN_PLACE_KEY, PLACE as FORGET_RANGE_PLACE } from "./forget-range.js";
import {
  fromChatFailure,
  fromStreamError,
  SETTINGS_PLACE_KEY,
  shown,
  STATUSES,
  WHERE_KINDS,
} from "./plain-errors.js";
import {
  boxTagAfter,
  CHAT_GONE,
  CHAT_GONE_KEY,
  commitExchange,
  CONTINUE_BUSY,
  CONTINUE_LIVE,
  CONTINUED_NOTHING,
  continuedHistoryLine,
  CONTINUED_TAINTED,
  CONTINUED_TEMPORARY_OFF,
  CARRY_ON_LAST,
  carryOnLastTitle,
  storedIdleNewMs,
  continuedLine,
  continuedSkipped,
  continuedTrimmed,
  continueWindow,
  EARLIER_CHATS,
  EARLIER_CHATS_TITLE,
  ENDED_SAVED,
  ENDED_TEMPORARY,
  historyMessages,
  crisisRoute,
  keepsInThread,
  IDLE_NEW_LINE,
  IDLE_NEW_LINE_TEMPORARY,
  idleExpired,
  MOVED_HERE,
  NEW_CONVERSATION,
  newConversationId,
  pairsAboveReadLine,
  sentProvenance,
  takeChatsGone,
  addToThread,
  THREAD_READS_FROM,
  threadSummary,
  userMessage,
} from "./chat-history.js";
import { fileNote, loadTargets, notSetUp, noTargetsLine, targetName } from "./note-capture.js";
// Where a spoken answer is cut into pieces - the same rule as the phone.
import { nextSpeechPiece } from "./speech-pieces.js";
// Temporary chat and "Used in this answer" (2026-09-25) - answer-memory.js.
import { createAnswerMemory, createTemporaryToggle } from "./answer-memory.js";
// One card on every screen, and what a spoken question hears about a card
// (the creativity audit, 2026-09-25) - card-words.js.
import { CARD_KICKER, cardTitle, createCardVoice, isCardLine } from "./card-words.js";
import { HeavyGate, isHeavy } from "./heavy-approve.js";
import { buildSayableList } from "./sayable.js";
// The command palette (docs/UI-AUDIT-2026-10-05.md section 2.4, "what I would
// change" row 4): the list and the search live in palette.js, which is pure,
// and every name in it comes from the generated menu catalogue.
import { HINT_LABEL, WORDS as PALETTE_WORDS } from "./palette.js";
import { buildPaletteHint, close as closePalette, isOpen as paletteOpen, mountPalette, openPalette } from "./palette-ui.js";
// A timer said aloud while hands-free listening is on (2026-09-25).
import { aloudFor } from "./coming-up.js";
import { READING as PHOTO_READING, mountProposal } from "./photo-reminder.js";
// "Inbox tidy by voice" (2026-09-28): the Undo strip under the input.
import { mountInboxTidy } from "./inbox-tidy.js";
// "Coach this" - the prompt coach's button above the box and the panel its
// critique opens (prompt-coach-panel.js; the owner's request of 2026-10-08).
import { historyFor, mountPromptCoach } from "./prompt-coach-panel.js";
// "Spending summaries" (2026-09-30): the table a spending answer announced.
import { mountSpendingTable, tableIdFromBody, tableIdFromLine } from "./spending.js";
import { mountFormReview } from "./form-review.js";
// What a `step` event means, in words - shared with Brain's Live tab
// (item 10, UI-AUDIT-2026-09-26.md).
import { stepText } from "./step-words.js";
import { DEVICE_CHANGES, stepTuning } from "./animal-shared.js";
import { loadFaceTuning, saveFaceTuning } from "./face-tuning.js";
import {
  apply as applyMenuVisibility,
  isHidden,
  loadState as loadMenuState,
  parseRoute as parseMenuRoute,
  saveState as saveMenuState,
} from "./menu-visibility.js";
// Jarvis Live: the same rules as the phone's (live-rules.js, 2026-09-28).
import {
  BUTTONS,
  cardInSession,
  couldBeSideTalk,
  DUCK_VOLUME,
  END_TONE,
  isSideTalk,
  liveBarge,
  liveChips,
  liveFold,
  liveReply,
  liveSign,
  liveTransition,
  loadInterrupt,
  LOCK_UNKNOWN_WORDS,
  deviceWords,
  moveWords,
  NEEDS_VOICE,
  onHere,
  SEEN,
  TITLE,
} from "./live-rules.js";
// The approval clock's own second-level ticker (2026-10-08 cohesion audit,
// finding 2: this file's `setInterval(..., 1000)` and widget.js's).
import { clockTimer, IDLE_MS } from "./clock-timer.js";

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
  reactor: $("reactor"),
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
  temporary: $("temporary"),
  temporaryStrip: $("temporary-strip"),
  lockdownStrip: $("lockdown-strip"),
  temporaryLine: $("temporary-line"),
  temporaryRefused: $("temporary-refused"),
  answerUsed: $("answer-used"),
  answerUsedLine: $("answer-used-line"),
  answerUsedList: $("answer-used-list"),
  answerMemoryNote: $("answer-memory-note"),
  answerSources: $("answer-sources"),
  answerSourcesLine: $("answer-sources-line"),
  answerSourcesList: $("answer-sources-list"),
  answerCloudOffer: $("answer-cloud-offer"),
  cloudOfferTry: $("cloud-offer-try"),
  cloudOfferDismiss: $("cloud-offer-dismiss"),
  approvalOptionsWhy: $("approval-options-why"),
  offlineRetry: $("offline-retry"),
  primer: $("primer"),
  mic: $("mic"),
  voiceAuto: $("voice-auto"),
  liveToggle: $("jarvis-live-toggle"),
  watchToggle: $("watch-toggle"),
  watchStrip: $("watch-strip"),
  watchTitle: $("watch-title"),
  watchDetail: $("watch-detail"),
  watchNote: $("watch-note"),
  watchMore: $("watch-more"),
  watchDrop: $("watch-drop"),
  watchStop: $("watch-stop"),
  liveStrip: $("jarvis-live-strip"),
  liveTitle: $("jarvis-live-title"),
  liveDetail: $("jarvis-live-detail"),
  liveMove: $("jarvis-live-move"),
  liveHint: $("jarvis-live-hint"),
  liveTemporary: $("jarvis-live-temporary"),
  liveMore: $("jarvis-live-more"),
  liveShowCard: $("jarvis-live-show-card"),
  liveFix: $("jarvis-live-fix"),
  liveCarryOn: $("jarvis-live-carry-on"),
  liveResume: $("jarvis-live-resume"),
  liveStopTalking: $("jarvis-live-stop-talking"),
  liveMute: $("jarvis-live-mute"),
  liveEnd: $("jarvis-live-end"),
  liveChips: $("jarvis-live-chips"),
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
  captureFindDate: $("capture-find-date"),
  photoProposal: $("photo-proposal"),
  inboxTidy: $("inbox-tidy"),
  // The prompt coach: the `.field` the "Coach this" button is put into, above
  // the box, and the panel the critique is drawn in (prompt-coach-panel.js).
  promptField: $("prompt-field"),
  coachPanel: $("coach-panel"),
  spendingTable: $("spending-table"),
  approvalPicture: $("approval-picture"),
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
  // A failed answer's fix button and "Details" (plain-errors.js).
  problem: $("answer-problem"),
  problemAction: $("problem-action"),
  problemWhere: $("problem-where"),
  problemDetails: $("problem-details"),
  problemDetailsText: $("problem-details-text"),
  cardBody: $("card-body"),
  answer: $("answer"),
  cursor: $("cursor"),
  copy: $("copy"),
  stop: $("stop"),
  newConversation: $("new-conversation"),
  // "Earlier chats" (the chat audit, 2026-09-28): the Brain's History, from
  // the card and from the primer; and the quiet line about the chat itself.
  earlierChats: $("earlier-chats"),
  earlierChatsPrimer: $("earlier-chats-primer"),
  chatNote: $("chat-note"),
  // "Carry on the last chat": beside the note that a new conversation began
  // after the owner's own quiet wait - 30 minutes by default (the second chat
  // audit, 2026-09-28; the wait is set in Settings, chat-history.js).
  carryOnLast: $("carry-on-last"),
  // "You: ..." above the answer - the question this answer is for.
  youLine: $("you-line"),
  chatEndedNote: $("chat-ended-note"),
  services: $("services"),

  previousAnswer: $("previous-answer"),
  previousAnswerSummary: $("previous-answer-summary"),
  previousAnswerBody: $("previous-answer-body"),
};

/** Feasibility I110: a `notice.weight: "heavy"` card's Approve stays grey
 * for a moment and until `#approval-preview` has been in view - see
 * heavy-approve.js's own doc comment. `syncApprovalButtons` is a plain
 * function declaration, hoisted, so naming it here (before its own textual
 * definition further down) is safe. */
const heavyGate = new HeavyGate({
  scrollEl: dom.approvalPreview,
  onChange: () => syncApprovalButtons(),
});

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
   * What the bar SHOWS of the conversation (the owner's decision,
   * 2026-09-28: "the whole current conversation as a scrollable thread"):
   * every finished `{ question, answer }` pair of this conversation, oldest
   * first - not trimmed to the model's re-send window like `conversation`,
   * only capped (chat-history.js THREAD_MAX). This window's memory only;
   * emptied wherever `conversation` starts afresh.
   */
  thread: [],
  /**
   * "Hide memory lists and chat history" is on (chat_thread_hidden): the
   * thread of earlier answers is not drawn (the owner's decision,
   * 2026-09-28, after the second chat audit). The answer on screen, being
   * asked about right now, is not hidden. Fails closed: a failed read counts
   * as hidden.
   */
  threadHidden: false,
  /** The PC made this conversation temporary by itself, because it is a game
   *  or role-play (the route header said so). Ends with the conversation. */
  gameChat: false,
  /** The chat the 30-quiet-minutes rule just ended, for "Carry on the last
   *  chat": its id, or null when there is none or it was never kept. */
  lastChatId: null,
  /**
   * The id every request of this conversation carries as `conversation_id`
   * (JARVIS-API.md section 18), so the PC's History keeps one entry per
   * conversation. A new one at start, on "New conversation" and on Esc -
   * wherever `conversation` above is emptied (closeCard).
   */
  conversationId: newConversationId(),
  /** When the last answer of this conversation finished (ms) - a new
   *  conversation starts after the owner's own wait (chat-history.js
   *  `storedIdleNewMs()`, 30 quiet minutes by default; the owner's decision,
   *  2026-09-28). 0: none yet. */
  lastTurnAt: 0,
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
  /** The private-answer rule (private-speech.js), for a voice turn: what the
   *  utterance reply said (`privateAloud`, `questionPrivate`,
   *  `memoryAloud`, `sensitiveAloud`, `screenAloud`), the route line (`gate`,
   *  `injected_facts`, `injected_sensitive`), whether `: jarvis-status` said a
   *  tool ran, the tool counters when the question was sent (`toolStart`,
   *  a `toolWatch` snapshot), and whether "It's on your screen." was said
   *  already. */
  voicePrivacy: null,
  turnRoute: null,
  toolRan: false,
  toolStart: null,
  privateLineSaid: false,
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
  lastAsked: "typed",
  /** "A cloud model could give this one a second look." (jarvis_router
   *  gate "offer"): the lane name it would use, or null when this answer
   *  carries no offer. Cleared on every new turn and once acted on. */
  cloudOffer: null,
  /** The previous turn's `{ prompt, buffer }`, once a new one starts — one
   *  level of scrollback, shown folded in the card until dismissed. */
  previousAnswer: null,
};

/**
 * Temporary chat (the owner's decision, 2026-09-25): the toggle and the
 * marker strip. Turning it on or off starts a new conversation, so nothing
 * said in one kind of chat is re-sent in the other. On only when the PC
 * says it can hold one (commands.rs temporary_chat_available; stream_chat
 * checks again before each temporary question).
 */
const temporaryChat = createTemporaryToggle({
  button: dom.temporary,
  strip: dom.temporaryStrip,
  line: dom.temporaryLine,
  refused: dom.temporaryRefused,
  root: dom.shell,
  check: () => (IS_TAURI ? invokeStrict("temporary_chat_available") : Promise.resolve(false)),
  restart: () => {
    state.turnQuestion = null;
    // The toggle has already flipped: the chat that ends here was the other kind.
    const wasTemporary = !temporaryChat.on;
    closeCard({ wasTemporary, quiet: true });
    state.conversation = [];
    state.thread = [];
    focusInput();
  },
  busy: () => Boolean(state.inFlight || state.abort),
  announce,
  onChange: () => {
    // Live's strip says "Temporary is on" while it is (paintLive).
    paintLive();
    syncWindowHeight();
  },
});

/**
 * "Used 2 memories" under the answer, and the temporary-chat notes. The
 * words of the facts are read from the PC only when the line is opened;
 * Forget and Erase are ONE fact each, asked about first, held on a stale
 * link (answer-memory.js).
 */
const answerMemory = createAnswerMemory({
  box: dom.answerUsed,
  lineButton: dom.answerUsedLine,
  list: dom.answerUsedList,
  note: dom.answerMemoryNote,
  invoke: (command, args) => invokeStrict(command, args),
  isStale: () => Boolean(currentLink().stale),
  confirm: (question) => window.confirm(question),
  announce,
  onChange: () => syncWindowHeight(),
  // "Erase the words" with its chat, when that chat is the one this bar is
  // in: a new conversation, said (the chat audit, 2026-09-28).
  onChatDeleted: (id) => {
    if (id === state.conversationId && state.conversation.length) startFreshQuietly(CHAT_GONE);
  },
  // "Where this came from" (feasibility I42/I132): the notes, wiki pages,
  // web results and files this answer actually read, plus the quote check.
  sources: {
    box: dom.answerSources,
    lineButton: dom.answerSourcesLine,
    list: dom.answerSourcesList,
  },
});

/** The Undo strip for an inbox tidy (inbox-tidy.js), mounted just below.
 *  Declared BEFORE it is mounted: a `let` used above its own line is a
 *  ReferenceError at load, which took the whole bar down. */
let inboxTidyView = null;

/**
 * "Inbox tidy by voice" (inbox-tidy.js; JARVIS-API.md section 95): ten
 * minutes of Undo after a tidy card was approved. The card itself is decided
 * above, in this bar; this strip only offers Undo - one tap, no card, held on
 * a stale link, and waiting for the unlock while Jarvis is locked (Rust).
 * It shows counts and the PC's own words, never a sender or a subject.
 */
if (dom.inboxTidy) {
  inboxTidyView = mountInboxTidy(dom.inboxTidy, {
    invoke: (command, args) => invokeStrict(command, args),
    isStale: () => Boolean(currentLink().stale),
    announce,
    onChange: () => syncWindowHeight(),
  });
  inboxTidyView.refresh();
  window.addEventListener("focus", () => inboxTidyView.refresh());
}

/** The spending table under the newest answer (spending.js), mounted just
 *  below. Declared BEFORE it is mounted, like the strip above. */
let spendingView = null;

/**
 * "Spending summaries" (JARVIS-API.md section 100): the stream said
 * `: jarvis-table <id>` before the answer's sentence, so this asks the PC for
 * the table and draws it under the sentence. In memory only - never stored,
 * never read aloud, no export. Under "Hide memory lists and chat history"
 * and while App lock has locked Jarvis it shows "Spending table hidden" and
 * the PC is not asked (Rust, spending.rs `chat_table`).
 */
if (dom.spendingTable) {
  spendingView = mountSpendingTable(dom.spendingTable, {
    invoke: (command, args) => invokeStrict(command, args),
    announce,
    onChange: () => syncWindowHeight(),
  });
  window.addEventListener("focus", () => spendingView.recheck());
}

/**
 * The picture of a filled-in web form on a "submit this form" card
 * (form-review.js; docs/FORM-REVIEW-DESIGN.md). Only this bar's full card
 * shows it - never the widget, a toast or the HUD page. Held in memory only
 * and dropped with the card.
 */
const formReview = dom.approvalPicture
  ? mountFormReview(dom.approvalPicture, {
    invoke: (command, args) => invokeStrict(command, args),
    onChange: () => syncWindowHeight(),
    announce,
  })
  : null;

/**
 * "Coach this" (prompt-coach-panel.js; docs/PROMPT-COACH-DESIGN.md, the
 * owner's request of 2026-10-08): the button above the box, and the panel that
 * shows ONE critique of the words in it - a score out of 10, what is missing
 * and why it matters and the smallest fix for each, the questions it would
 * have to ask, and the rewritten prompt in full.
 *
 * The button is drawn only while the PC says the coach is on (off by default);
 * with it off there is no button at all, which is the owner's own rule.
 *
 * NOTHING HERE SENDS A TURN BY ITSELF. The critique is advice: the score is
 * never a gate, and the panel's own two buttons are the only things that send
 * anything -
 *
 *  - "Send mine" hands back exactly what is in the box, unchanged, through the
 *    same `send()` the Enter key uses;
 *  - "Send the suggestion" puts the rewritten prompt in the box and sends
 *    that. Writing it marks the box "typed" - the words are a question for
 *    Jarvis written for the owner to read and send, not something pasted in
 *    from elsewhere (chat-history.js `boxTagAfter`, which holds that rule).
 *
 * The history handed over is the bar's own thread - the last few turns it was
 * going to re-send to the same local model anyway, and never anything the PC
 * does not already have.
 */
const promptCoach = dom.coachPanel
  ? mountPromptCoach(dom.promptField, dom.coachPanel, {
    invoke: (command, args) => invokeStrict(command, args),
    boxText: () => dom.prompt.value,
    history: () => historyFor(state.thread),
    sendMine: (text) => send(text, state.boxTag),
    sendSuggestion: async (text) => {
      dom.prompt.value = text;
      // A rewritten question is the owner's own typing, not a paste: it was
      // written for them to read and send, and every rule about pasted words
      // stays with words that really were pasted (chat-history.js).
      state.boxTag = boxTagAfter("typed", "edit", text);
      state.historyIndex = null;
      autoGrowPrompt();
      await send(text, state.boxTag);
    },
    announce,
    onChange: () => syncWindowHeight(),
  })
  : null;

/** Tools that ran (`step` events) and drops of the event stream, for the
 *  private-answer rule - fed below, where this window subscribes to the
 *  link (private-speech.js `createToolWatch`). */
const toolWatch = createToolWatch();

/** Jarvis Live's state in this bar (the Jarvis Live section below). */
const LIVE_ME = "desktop";
/** How long "Heard you - thinking" / "Didn't catch that" stay up. */
const LIVE_FLASH_MS = 6000;
/** A first answer slower than this plays "One moment." (the model loading). */
const LIVE_SLOW_MS = 2500;

const live = {
  status: null,
  stale: false,
  lockUnknown: false,
  callUnknown: false,
  micWait: "",
  thinking: false,
  short: false,
  flashUntil: 0,
  chips: [],
  elsewhere: "",
  /** The fresh chat id this bar started Live with, and the other device's
   *  chat for "Move it here" - read once, by liveAdoptChat. */
  pendingCid: "",
  moveCid: "",
  elsewhereTimer: null,
  // When it ended, as the PC counted it: {at: this PC's ms, ago: seconds}.
  endedBase: null,
  endedTimer: null,
  // Why Live did not start, in the strip; `noticeNeedsVoice` adds a
  // "Settings, then Voice" button.
  notice: "",
  noticeNeedsVoice: false,
  noticeTimer: null,
  // One click at a time on the Live button.
  busy: false,
  // "Resume Live" / "Move it here": the same chat carries on.
  resuming: false,
  // The answer that was on screen, while a Live answer could still be side
  // talk (liveHeldAnswer).
  keep: null,
  sideTalkUntil: 0,
  troubleUntil: 0,
  explaining: false,
  toldPlaying: false,
  heldForCard: false,
  heldForAnswer: false,
  sounded: false,
  slowTimer: null,
  duckTimer: null,
  lastQuestion: "",
  pending: null,
};

/** How many prompts `state.promptHistory` keeps. Older ones fall off the front. */
const PROMPT_HISTORY_LIMIT = 50;

/** `idle` | `streaming` | `done` | `error` | `approval`. */
function setPhase(phase) {
  state.phase = phase;
  dom.root.dataset.state = phase;
  // An answer just finished: a tidy it made may now be open to Undo.
  if (phase === "done" && inboxTidyView) inboxTidyView.refresh();
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

    // Jarvis Live: while a spoken answer could still be side talk, the
    // answer that was on screen stays (liveHeldAnswer).
    const held = liveHeldAnswer();
    dom.answer.innerHTML = renderMarkdown(held ? held.buffer : state.buffer);
    // The crisis help line (jarvis_wellbeing.py, 2026-09-27): a calm, plain
    // panel - larger numbers, nothing else about the layout - instead of an
    // ordinary answer, the moment the server's own flag says so
    // (`X-Jarvis-Route`'s `wellbeing: "crisis"` - see docs/JARVIS-API.md
    // section 38; not yet confirmed sent by every backend, so this is a
    // no-op, and the words still show as an ordinary answer, until it is).
    const route = held ? held.route : state.turnRoute;
    dom.answer.classList.toggle("wellbeing-crisis", Boolean(route && route.wellbeing === "crisis"));
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

    syncCardTools();
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
  syncCardTools();
  syncPrimer();
}

/** Copy has nothing to copy on a card with no answer yet (a chat just
 *  carried on from History), and the thread's divider has nothing under it
 *  then (the second chat audit, 2026-09-28, desktop B4). */
function syncCardTools() {
  const empty = !state.buffer.trim();
  dom.copy.disabled = empty;
  dom.copy.title = empty ? "There is no answer to copy yet." : "Copy the answer";
  if (dom.previousAnswer) dom.previousAnswer.classList.toggle("alone", empty);
}

/**
 * Fills the primer's #sayable-list from sayable.js's own fixed words
 * ("Things you can say" - the ease-of-use audit's do-first table, row 4).
 *
 * Unlike the kbd chips this replaces, these are not live PC settings: the
 * hardcoded list in sayable.js IS the source both apps read, so there is
 * nothing to fetch and nothing that can go stale from a rebind. Tapping a
 * line only fills #prompt - it is never sent by the list itself.
 */
function renderSayableList() {
  const host = document.getElementById("sayable-list");
  if (!host) return;
  host.replaceChildren(
    buildSayableList((sentence) => {
      dom.prompt.value = sentence;
      autoGrowPrompt();
      dom.prompt.focus();
      dom.prompt.setSelectionRange(sentence.length, sentence.length);
      syncWindowHeight();
    }),
  );
}

/**
 * The bar's own way into the palette, beside "Things you can say": a button
 * because it does something on click, and a keyboard user reaches it with
 * Tab. Typing "/" in an empty box does the same thing (palette-ui.js), so
 * the hint is the discoverable half and the key is the fast one.
 */
function renderPaletteHint() {
  const host = document.getElementById("palette-hint");
  if (!host) return;
  host.replaceChildren(buildPaletteHint(() => openPalette()));
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
function closeCard({ wasTemporary = temporaryChat.on, quiet = false } = {}) {
  dom.card.hidden = true;
  paintYouLine("");
  dom.answer.innerHTML = "";
  dom.answer.classList.remove("wellbeing-crisis");
  if (spendingView) spendingView.clear();
  dom.cardStat.textContent = "";
  paintProblem(null, "");
  dom.cursor.hidden = true;
  state.buffer = "";
  state.lastPrompt = "";
  state.previousAnswer = null;
  // The conversation goes with the card it was shown in: Esc, which ends
  // up here, has always meant "done with this", and a question asked next
  // time the window opens should not silently follow on from one that is no
  // longer on screen. Hiding on focus loss does not come here.
  const hadChat = state.conversation.length > 0;
  // A game is a temporary chat the PC made by itself: nothing of it was kept
  // either (the second chat audit, 2026-09-28, desktop B3).
  const endedTemporary = wasTemporary || state.gameChat;
  state.conversation = [];
  state.thread = [];
  state.gameChat = false;
  state.lastChatId = null;
  hideCarryOn();
  temporaryChat.setGame(false);
  // A conversation forgotten here is a finished one on the PC too: the next
  // question starts a new entry in History (JARVIS-API.md section 18).
  state.conversationId = newConversationId();
  state.lastTurnAt = 0;
  state.turnQuestion = null;
  state.turnProvenance = null;
  hideChatNote();
  // Where it went, said the next time the bar is opened, until a question
  // is asked (the chat audit, 2026-09-28: Esc used to end a chat without a
  // word). A temporary chat was never kept, so it says nothing.
  // A second Esc with no chat left leaves the line as it is. Turning a
  // temporary chat on says the same of the chat it ended, which was kept
  // (the chat audit, desktop C11: it used to go without a word). A
  // temporary chat or a game says that nothing of it was kept, and every
  // ending is said to a screen reader too (the second chat audit,
  // 2026-09-28, desktop B3 and C3).
  if (dom.chatEndedNote && hadChat) {
    const line = endedTemporary ? ENDED_TEMPORARY : ENDED_SAVED;
    dom.chatEndedNote.hidden = false;
    dom.chatEndedNote.textContent = line;
    if (!quiet) announce(line);
  }
  paintedBlocks = 0;
  spokenUpTo = 0;
  stopSpeaking();
  setPhase("idle");
  renderPreviousAnswer();
  syncNewConversation();
  answerMemory.clear();
  temporaryChat.paint(true);
  paint({ immediate: true });
}

/**
 * Shows or hides the folded "previous answer" strip from `state.previousAnswer`.
 *
 * Closed by default (the `<details>` starts with no `open` attribute) every
 * time it is (re)populated — a follow-up you asked on purpose should not have
 * the last answer thrust back open in front of it.
 */
function renderPreviousAnswer({ open = false } = {}) {
  // The whole conversation so far, not only the last answer (the owner's
  // decision, 2026-09-28: "the whole current conversation as a scrollable
  // thread"): every finished question and answer before the one on screen,
  // oldest first. The words are escaped; each answer goes through the same
  // markdown renderer as the card (escaped first). Nothing new is kept:
  // this is `state.conversation`, which the bar already holds in memory.
  // Under "Hide memory lists and chat history" the thread is not drawn at
  // all (the owner's decision, 2026-09-28): it is the chat history.
  const pairs = state.threadHidden ? [] : threadPairs();
  dom.previousAnswer.hidden = !pairs.length;
  if (!pairs.length) {
    dom.previousAnswerBody.replaceChildren();
    return;
  }
  dom.previousAnswer.open = open;
  dom.previousAnswerSummary.textContent = threadSummary(pairs.length);
  // Where what Jarvis reads back begins: the thread shows the whole
  // conversation, the model is re-sent only the newest questions.
  const above = pairsAboveReadLine(state.thread.length, state.conversation.length);
  const line = `<p class="thread-reads-from" role="note">${escapeHtml(THREAD_READS_FROM)}</p>`;
  dom.previousAnswerBody.innerHTML = pairs.map((p, i) =>
    `${above > 0 && i === above ? line : ""}<section class="thread-turn"><p class="thread-q"><span class="thread-who">You:</span> ${
      escapeHtml(truncateForSummary(p.question, 400))}</p><div class="thread-a">${
      renderMarkdown(p.answer)}</div></section>`).join("")
    + (above > 0 && above >= pairs.length ? line : "");
  if (open) scrollThreadToNewest();
}

/** The thread opens on its newest end - where the conversation is - not the
 *  oldest (the second chat audit, 2026-09-28, desktop worst-three #3). */
function scrollThreadToNewest() {
  const body = dom.previousAnswerBody;
  const go = () => { body.scrollTop = body.scrollHeight; };
  go();
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(go);
}

if (dom.previousAnswer) {
  dom.previousAnswer.addEventListener("toggle", () => {
    if (dom.previousAnswer.open) scrollThreadToNewest();
    syncWindowHeight();
  });
}

/** Asks the PC whether the private lists are hidden, and draws the thread
 *  again when the answer changed. A failed ask counts as hidden. */
async function refreshThreadHidden() {
  if (!IS_TAURI) return;
  let hidden = true;
  try {
    hidden = (await invokeStrict("chat_thread_hidden")) === true;
  } catch {
    hidden = true;
  }
  if (hidden !== state.threadHidden) {
    state.threadHidden = hidden;
    renderPreviousAnswer({ open: dom.previousAnswer.open });
    syncWindowHeight();
  }
}

/** "You: ..." above the answer: the question this answer is for. On screen
 *  only; the bar showed it only after the NEXT question (desktop audit). */
function paintYouLine(question) {
  if (!dom.youLine) return;
  const q = String(question || "").replace(/\s+/g, " ").trim();
  dom.youLine.hidden = !q;
  dom.youLine.replaceChildren();
  if (!q) return;
  const who = document.createElement("span");
  who.className = "thread-who";
  who.textContent = "You:";
  dom.youLine.append(who, document.createTextNode(` ${q.length > 240 ? `${q.slice(0, 239)}…` : q}`));
}

/** "Carry on the last chat": shown with the note that the owner's own quiet
 *  wait began a new conversation (30 minutes by default), for a chat that was
 *  kept. Its tooltip says the wait the owner really chose ([carryOnLastTitle]). */
function showCarryOn(id) {
  if (!dom.carryOnLast) return;
  state.lastChatId = id;
  dom.carryOnLast.hidden = false;
}

function hideCarryOn() {
  state.lastChatId = null;
  if (dom.carryOnLast) dom.carryOnLast.hidden = true;
}

/** The finished turns before the one on screen: all of `thread`, less the
 *  last pair when it is the answer the card is showing. */
function threadPairs() {
  const pairs = state.thread.slice();
  const last = pairs[pairs.length - 1];
  if (last && !state.inFlight && state.phase === "done" && state.lastPrompt
      && last.question === state.lastPrompt && state.buffer.trim()) {
    pairs.pop();
  }
  return pairs;
}

/** The one quiet line about the chat itself: a new conversation after a
 *  while, a chat carried on, a chat deleted. Said to a screen reader too. */
function showChatNote(line) {
  if (!dom.chatNote || !line) return;
  dom.chatNote.textContent = line;
  dom.chatNote.hidden = false;
  announce(line);
}

function hideChatNote() {
  if (!dom.chatNote) return;
  dom.chatNote.hidden = true;
  dom.chatNote.textContent = "";
}

/** A new conversation without clearing what is on screen - after 30 quiet
 *  minutes, or when the chat this bar was in was deleted. */
function startFreshQuietly(line, { carryOn = null } = {}) {
  state.conversation = [];
  state.thread = [];
  state.conversationId = newConversationId();
  state.lastTurnAt = 0;
  state.previousAnswer = null;
  state.gameChat = false;
  temporaryChat.setGame(false);
  renderPreviousAnswer();
  syncNewConversation();
  hideCarryOn();
  showChatNote(line);
  if (carryOn) showCarryOn(carryOn);
}

/**
 * "Continue this chat" (from the Brain's History) and "Move it here" (Jarvis
 * Live): this bar carries on a kept conversation - the SAME conversation id,
 * so the PC files the new turns with it and its "read outside text" mark
 * carries over (the PC decides that from its own record); the newest kept
 * messages that fit a chat's re-send limit, skipping any whose answer was
 * not kept (chat-history.js continueWindow). A support, chatbot or
 * comparison record is refused by Rust (chat_continue_open). A temporary
 * chat is never kept, so it can never be continued; turning to a kept chat
 * turns Temporary off first.
 */
async function continueChat(id, { moved = false } = {}) {
  if (state.inFlight || state.abort) {
    openCard("Busy");
    showChatNote(CONTINUE_BUSY);
    return;
  }
  if (!moved && liveOnHere()) {
    // Live's words are filed in Live's own chat: carrying another one on
    // under it would mix the two (the second chat audit).
    openCard("Not continued");
    showChatNote(CONTINUE_LIVE);
    return;
  }
  let conv;
  try {
    conv = await invokeStrict("chat_continue_open", { id });
  } catch (error) {
    if (moved) {
      // "Move it here" with nothing in History to read back (history off, a
      // list hidden, or no answer kept yet): the session's chat is still the
      // one carried on here - the same id, so the PC files what follows with
      // it - just with no earlier words re-sent.
      conv = { turns: [], tainted: false };
    } else {
      openCard("Not continued");
      showChatNote(String((error && error.message) || error));
      return;
    }
  }
  const { window: kept, trimmed, trimmedCount, skipped } = continueWindow(conv && conv.turns);
  let tempOff = false;
  if (temporaryChat.on) {
    await temporaryChat.toggle();
    tempOff = !temporaryChat.on;
  }
  closeCard({ quiet: true });
  state.conversation = kept;
  state.thread = kept.slice();
  state.conversationId = id;
  state.lastTurnAt = Date.now();
  if (dom.chatEndedNote) dom.chatEndedNote.hidden = true;
  openCard(moved ? "Jarvis Live" : "Continuing a chat");
  await refreshThreadHidden();
  const lines = [moved ? MOVED_HERE : continuedLine(conv && conv.title)];
  if (!kept.length && !moved) lines.push(CONTINUED_NOTHING);
  if (skipped && kept.length) lines.push(continuedSkipped(skipped));
  if (trimmed) lines.push(continuedTrimmed(trimmedCount));
  if (conv && conv.tainted === true) lines.push(CONTINUED_TAINTED);
  if (tempOff) lines.push(CONTINUED_TEMPORARY_OFF);
  // History off (or unable to keep anything): the chat can be read and
  // carried on, but what is said now is not kept (the owner, 2026-09-29).
  // Not for "Move it here": that says where the chat went, not that it was
  // filed, and Live's own strip carries its own Temporary line.
  const historyLine = moved ? null : continuedHistoryLine(conv && conv.history);
  if (historyLine) lines.push(historyLine);
  renderPreviousAnswer({ open: true });
  showChatNote(lines.join(" "));
  syncNewConversation();
  syncWindowHeight();
  focusInput();
}

/** "Earlier chats": the Brain, on History (plain_errors.rs open_fix_place). */
function openEarlierChats() {
  invoke("open_fix_place", { place: "history" });
}

/** A one-line label for the scrollback summary — long prompts wrap the card. */
function truncateForSummary(text, max = 80) {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

/** Renders a failure inside the card instead of silently doing nothing. */
function showError(message) {
  showProblem(shown("pc_said", message), "", "Error");
}

/**
 * A failure in plain words (plain-errors.js): what happened, what to do,
 * ONE button for it, and the technical detail - scrubbed - behind
 * "Details" for a bug report. The same words as the phone's.
 */
function showProblem(problem, details = problem.details || "", status = "Not answered") {
  setPhase("error");
  openCard(status);
  dom.cursor.hidden = true;
  state.buffer = problem.kind === "pc_said"
    ? `**Jarvis could not answer.**\n\n${problem.says}`
    : `**${problem.says}**\n\n${problem.fix}`;
  paintProblem(problem, details);
  paint({ immediate: true });
}

/** The fix button and "Details" under a failed answer; hidden otherwise. */
function paintProblem(problem, details) {
  if (!dom.problem) return;
  const action = problem && problem.button ? problem.action : "none";
  dom.problem.hidden = !problem || (action === "none" && !details);
  if (dom.problemAction) {
    dom.problemAction.hidden = action === "none";
    dom.problemAction.textContent = problem ? problem.button : "";
    dom.problemAction.dataset.action = action;
  }
  if (dom.problemWhere) {
    const place = problem ? WHERE_KINDS[problem.kind] || "" : "";
    dom.problemWhere.hidden = !place;
    dom.problemWhere.dataset.place = place;
    if (place) dom.problem.hidden = false;
  }
  if (dom.problemDetails) {
    dom.problemDetails.hidden = !details;
    dom.problemDetails.open = false;
  }
  if (dom.problemDetailsText) dom.problemDetailsText.textContent = details || "";
}

/** What an error's fix button does (the contract file's actions). */
function runProblemAction(action) {
  if (action === "retry") {
    const again = state.lastPrompt;
    if (again) send(again, state.lastAsked || "typed");
  } else if (action === "reconnect") {
    reconnectLink();
  } else if (action === "connection") {
    invoke("open_fix_place", { place: "settings" });
  } else if (action === "models") {
    invoke("open_fix_place", { place: "brain" });
  }
}

if (dom.problemAction) {
  dom.problemAction.addEventListener("click", () =>
    runProblemAction(dom.problemAction.dataset.action || "none"));
}

/** "Show me where": Settings, at the place the fix names (plain-errors.js). */
if (dom.problemWhere) {
  dom.problemWhere.addEventListener("click", () => {
    const place = dom.problemWhere.dataset.place || "";
    try {
      localStorage.setItem(SETTINGS_PLACE_KEY, JSON.stringify({ place, at: Date.now() }));
    } catch {
      /* no storage: Settings opens at the top, and the fix's words say where */
    }
    invoke("open_fix_place", { place: "settings" });
  });
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
  // Kept whole for the private-answer rule (gate, injected_facts) - the
  // route line carries nothing else (commands.rs route_line_from_header).
  state.turnRoute = route && typeof route === "object" ? route : null;
  // The facts this answer used (ids only) and the temporary-chat marks.
  answerMemory.route(state.turnRoute);
  if (answerMemory.state.game && !state.gameChat) {
    state.gameChat = true;
    temporaryChat.setGame(true);
  }
  openSettingsFromRoute(state.turnRoute);
  applyFaceTuningFromRoute(state.turnRoute);
  cloudOfferFromRoute(state.turnRoute);
  openBrainFromRoute(state.turnRoute);
  menuVisibilityFromRoute(state.turnRoute);
  const next = routeFromHeader(route);
  if (!next) return;
  state.routeFromHeader = true;
  applyRoute(next);
}

/**
 * "Show or hide menus" by voice or chat (jarvis_menus.py, jarvis_quick.py,
 * 2026-09-30; docs/MENU-VISIBILITY-DESIGN.md, JARVIS-API section 109):
 * `menu_visibility` in X-Jarvis-Route names the action and target. Applies
 * immediately to localStorage with no confirmation card.
 */
function menuVisibilityFromRoute(route) {
  const parsed = parseMenuRoute(route);
  if (!parsed) return;
  const st = loadMenuState();
  applyMenuVisibility(st, parsed.action, parsed.target, "desktop");
  saveMenuState(st);
}

/**
 * "Open <a settings section>" by voice or chat (jarvis_settings_registry.py,
 * 2026-09-27): `open_settings` on X-Jarvis-Route names the section id
 * settings.html and settings.js already use ("web-search", "manner", ...).
 * The SAME mechanism "Show me where" already uses (plain-errors.js's own
 * button): leave the place under SETTINGS_PLACE_KEY, then ask Rust to open
 * or focus the Settings window; settings.js's own goToPlace() (generalised
 * the same day, to any section id, not only "Starting Jarvis for you")
 * takes it from there. Nothing here changes a setting - this only jumps
 * the app to it, the owner still makes the change by hand.
 */
function openSettingsFromRoute(route) {
  const place = route && typeof route.open_settings === "string" ? route.open_settings : "";
  if (!place) return;
  try {
    localStorage.setItem(SETTINGS_PLACE_KEY, JSON.stringify({ place, at: Date.now() }));
  } catch {
    /* no storage: Settings opens at the top, and the answer's own words say where */
  }
  invoke("open_fix_place", { place: "settings" });
}

/**
 * "Make the animal sharper" / "smoother" by voice or chat (jarvis_quick.py,
 * the owner's decisions of 2026-09-28): sharpness and frame rate are kept
 * per device, so the PC changes nothing and names the change in
 * X-Jarvis-Route's `face_tuning` - and THIS computer, the one that asked,
 * applies it to its own face settings (face-tuning.js) with the PC's own
 * rule (animal-shared.js stepTuning). Every face page and Settings hear it
 * through localStorage. Only one of a fixed list of words is acted on.
 * Returns the line announced about it, or "".
 */
function applyFaceTuningFromRoute(route) {
  const change = route && typeof route.face_tuning === "string" ? route.face_tuning : "";
  if (!change || !DEVICE_CHANGES.includes(change)) return "";
  const step = stepTuning(loadFaceTuning(), change);
  if (step.changed) saveFaceTuning(step.tuning);
  const line = step.line.replace("{device}", "this computer");
  if (line) announce(line);
  return line;
}

/**
 * "A cloud model could give this one a second look." (jarvis_router
 * gate "offer", docs/JARVIS-API.md "`offer` in `X-Jarvis-Route`"): every
 * gate that would refuse escalation outright - private, tainted, a
 * picture, no lane, no budget - already ran before this ever appears, so
 * accepting it only ever turns an offer this question already earned on
 * its own merits into an escalation. Never a standing choice: cleared on
 * every new turn (see send()) and the moment the owner acts on it.
 */
function cloudOfferFromRoute(route) {
  state.cloudOffer =
    route && route.gate === "offer" && typeof route.offer === "string" && route.offer
      ? route.offer
      : null;
}

/**
 * "Forget a time frame" (jarvis_forget_range.py, 2026-09-28): after "forget
 * what you learned last week", said or typed, `open_brain` on X-Jarvis-Route
 * names the Brain place with the list already filled in. The same shape as
 * openSettingsFromRoute: leave the place under BRAIN_PLACE_KEY, then ask Rust
 * to open or focus the Brain; brain.js takes it from there. Navigation only -
 * nothing is removed until the owner ticks, presses Forget these and
 * approves the card.
 */
function openBrainFromRoute(route) {
  if (!route) return;
  // "Label my chat about the boiler as Home" (docs/CHAT-TAGS-DESIGN.md
  // section 10): History opens with the search words filled in and a banner
  // to file the tapped chat under the tag `file_under`. Only those two
  // fields ride along, and the Brain checks them again; nothing is filed
  // until the owner taps a chat.
  if (route.open_brain === "history") {
    const left = { place: "history", at: Date.now() };
    if (typeof route.file_under === "string" && typeof route.history_q === "string") {
      left.file_under = route.file_under;
      left.history_q = route.history_q;
    }
    try {
      localStorage.setItem(BRAIN_PLACE_KEY, JSON.stringify(left));
    } catch {
      /* no storage: the Brain opens where it was, and the answer's own words say where */
    }
    // The Brain removes the key the moment it reads it (takeAnyPlace). If it
    // never opens, the search words are not left lying about: gone in a minute.
    setTimeout(() => {
      try {
        const now = JSON.parse(localStorage.getItem(BRAIN_PLACE_KEY) || "null");
        if (now && now.at === left.at) localStorage.removeItem(BRAIN_PLACE_KEY);
      } catch {
        /* nothing to clear */
      }
    }, 65_000);
    invoke("open_fix_place", { place: "brain" });
    return;
  }
  // Topic controls (docs/TOPIC-CONTROLS-DESIGN.md C1): "switch off my work
  // topic" is ambiguous, so the PC opens the picker instead of guessing.
  // Only the place and a whole-number topic id ride along; the Brain checks
  // the id again and changes nothing until the owner taps Change.
  if (route.open_brain === "topics") {
    const left = { place: "topics", at: Date.now() };
    if (Number.isInteger(route.topic_id) && route.topic_id >= 1) left.topic_id = route.topic_id;
    try {
      localStorage.setItem(BRAIN_PLACE_KEY, JSON.stringify(left));
    } catch {
      /* no storage: the Brain opens where it was, and the answer's own words say where */
    }
    setTimeout(() => {
      try {
        const now = JSON.parse(localStorage.getItem(BRAIN_PLACE_KEY) || "null");
        if (now && now.at === left.at) localStorage.removeItem(BRAIN_PLACE_KEY);
      } catch {
        /* nothing to clear */
      }
    }, 65_000);
    invoke("open_fix_place", { place: "brain" });
    return;
  }
  if (route.open_brain !== FORGET_RANGE_PLACE) return;
  try {
    localStorage.setItem(BRAIN_PLACE_KEY, JSON.stringify({ place: FORGET_RANGE_PLACE, at: Date.now() }));
  } catch {
    /* no storage: the Brain opens where it was, and the answer's own words say where */
  }
  invoke("open_fix_place", { place: "brain" });
}

/**
 * The command palette's way of opening one row (palette-ui.js calls this with
 * what palette.js's own placeFor() worked out). It is the SAME two navigation
 * mechanisms the bar already uses - "open <a settings section>" writes the
 * place Settings reads, and "earlier chats"/"forget a time frame" writes the
 * place the Brain reads - so the palette adds no command, no grant and no new
 * way for anything to happen. Nothing is changed by opening a place: the
 * owner still makes every change by hand.
 *
 * Returns the line to say about it, or "" when there is nothing to add.
 */
function openPlaceFromPalette(place) {
  if (!place || !place.window) return "";
  if (place.window === "settings") {
    if (!place.place) return "";
    try {
      localStorage.setItem(
        SETTINGS_PLACE_KEY,
        JSON.stringify({ place: place.place, at: Date.now() }),
      );
    } catch {
      /* no storage: Settings opens at the top, and the row's own name said where */
    }
    invoke("open_fix_place", { place: "settings" });
    return "";
  }
  if (place.window === "brain") {
    const left = { place: place.place, at: Date.now() };
    try {
      localStorage.setItem(BRAIN_PLACE_KEY, JSON.stringify(left));
    } catch {
      /* no storage: the Brain opens where it was, and the row's own name said where */
    }
    // The Brain removes the key the moment it reads it (takeAnyPlace); if it
    // never opens, the place is not left lying about - gone in a minute.
    setTimeout(() => {
      try {
        const now = JSON.parse(localStorage.getItem(BRAIN_PLACE_KEY) || "null");
        if (now && now.at === left.at) localStorage.removeItem(BRAIN_PLACE_KEY);
      } catch {
        /* nothing to clear */
      }
    }, 65_000);
    invoke("open_fix_place", { place: "brain" });
    return "";
  }
  return "";
}

/** Paints the three health dots in the card footer. */
function applyHealth(report) {  if (!report || !Array.isArray(report.services)) return;

  for (const service of report.services) {
    const dot = dom.services.querySelector(`[data-service="${service.id}"]`);
    if (!dot) continue;
    dot.dataset.online = String(Boolean(service.online));
    // The cloud escalation lane is optional: not set up is normal, so its
    // dot is drawn quiet, not red.
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
 * the cloud lane's own state are not on the event bus, so their dots still need
 * a probe;
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
  if (!state.capture) {
    hidePictureNotice();
    closePhotoProposal();
  }
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
  // The PC reads the WORDS in the picture itself when the model cannot see
  // it, and sends them marked as outside text (backend jarvis_ocr.py, the
  // owner's decision of 2026-09-26): nothing to ask, the picture just goes.
  if (check && check.readsText === true) return { ok: true, check };
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
  // Jarvis Live: speech pauses and the microphone closes for the card.
  liveCardShown(true);

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
    `${CARD_KICKER}: ${cardTitle(approval)}. ${riskLine(approval.risk)}. ` +
      "Deny and Approve are in the gate; Escape puts it aside.",
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

  // Feasibility I110: a genuinely new heavy card restarts the clock and the
  // scroll watch; a re-render of the SAME card (a resync, `raised` ticking
  // up) must not, or a backend that resyncs the queue every few seconds
  // would hold Approve grey forever. A card that stops being heavy (should
  // never happen mid-life, but nothing here assumes it cannot) is stopped.
  if (fresh) {
    if (isHeavy(approval)) heavyGate.start();
    else heavyGate.stop();
  }

  // The PC's own words for it (notice.title, card-words.js), never the code
  // name: "Jarvis wants to switch to a different AI model", not `switch_model`.
  dom.approvalAction.textContent = cardTitle(approval);
  const target = approval.detail && typeof approval.detail === "object"
    ? approval.detail.target || approval.detail.note_target || approval.detail.to
    : null;
  dom.approvalTarget.hidden = !target;
  if (target) dom.approvalTarget.textContent = String(target);

  renderRaised(approval.raised);

  if (isEmailCard(approval)) {
    // An email is shown exactly as it will be sent - never as Markdown,
    // which would turn `[words](link)` into "words" and hide where the link
    // goes, or eat a line's `**`. textContent in a <pre>: every character
    // and line break, nothing interpreted (the owner's decision of
    // 2026-09-25: the card shows the recipients, the subject and every word).
    const pre = document.createElement("pre");
    pre.className = "approval-verbatim";
    pre.textContent = approvalPlainText(approval);
    dom.approvalPreview.replaceChildren(pre);
  } else {
    dom.approvalPreview.innerHTML = renderMarkdown(approvalPreview(approval));
    decorateDiff(dom.approvalPreview);
  }
  if (formReview) formReview.show(approval);
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
  const title = cardTitle(state.approval);
  state.parked.add(state.approval.id);
  closeApproval();
  announce(`Put aside: ${title}. It is still waiting; nothing was decided.`);
  // Another card still waiting takes its place, as the queue subscription
  // would show it on its next read (and skipping, like it does, the one just
  // answered here). Parking the first of two cards used to hide BOTH until
  // the next event, with the line saying "1 approval is still waiting"
  // while two were (play tester, 2026-09-27). Display only: openApproval
  // puts focus on the card, never on Approve, and decides nothing.
  const next = currentQueue().items.find(
    (item) => !state.parked.has(item.id) && item.id !== state.decided
  );
  if (next) {
    openApproval(next);
    syncParkedBar();
    return;
  }
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
  liveCardShown(false);
  // Feasibility I110: no card left to watch. `openApproval`/`refreshApproval`
  // restarts it for whichever card (the same or a different one) opens next.
  heavyGate.stop();
  // `state.decided` is deliberately NOT cleared here. It is the guard that
  // stops an already-answered gate being answered again, and `decide_approval`
  // does not re-read the queue — so between answering and the server's next
  // `approval` event the tray still says "1 waiting" and its row reopens the
  // same card with live buttons. Clearing the guard on close disarmed it at
  // precisely the moment it was needed. `openApproval` clears it when a
  // DIFFERENT id arrives, which is the only time it should go.
  dom.approval.hidden = true;
  dom.approvalPreview.innerHTML = "";
  if (formReview) formReview.clear();
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
  // Feasibility I110: a heavy card's Approve stays grey until BOTH
  // heavyGate conditions clear (the delay, and the preview having been in
  // view). Deny is never touched by this, same as `cutOff` below.
  const heavyBlocked = isHeavy(state.approval) && !heavyGate.ok;
  // A card whose request was cut off on its way here cannot be approved: what
  // is on screen is not all of what would run. Deny stays - refusing
  // something unread costs a retry, approving it is the thing to prevent.
  dom.approvalApprove.disabled =
    blocked || Boolean(state.approval && state.approval.cutOff) || heavyBlocked;
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
  // A card opened, closed or was replaced: the line under the risk row is
  // about to change, so wake its clock now instead of waiting out a slow beat.
  nudgeApprovalClock();
}

/**
 * The line under the risk line: "Nothing runs until you decide", plus how
 * long the card has left (the gate refuses it by itself at the deadline -
 * approval-expiry.patch), or why Approve is off for a cut-off request.
 * Re-painted by the ticker below, and only this line: it is not
 * a live region, so the countdown is never read out.
 */
function paintApprovalClock() {
  const line = document.querySelector("#approval .approval-reassure");
  if (!line) return;
  const approval = state.approval;
  const parts = ["Nothing runs until you decide."];
  if (approval && approval.cutOff) {
    parts.push("This request was cut off before it reached this card, so it cannot be approved here - deny it and ask Jarvis for a shorter plan.");
  } else if (isHeavy(approval) && !heavyGate.ok) {
    // Feasibility I110. Two conditions, said as one sentence rather than
    // two, since they clear together and the owner only needs to know
    // there is something left to do, not the mechanism.
    const left = heavyGate.secondsLeft();
    parts.push(
      heavyGate.scrollOk
        ? `Approve unlocks in ${left}s.`
        : `Read the whole card (scroll down) - Approve unlocks once you have, and no sooner than ${left}s.`
    );
  }
  const clock = approval ? expiryWords(approval.expiresAt) : "";
  if (clock) parts.push(clock);
  const text = parts.join(" ");
  if (line.textContent !== text) line.textContent = text;
}

/**
 * What the shown line is worth waiting for, in ms (2026-10-08 cohesion audit,
 * finding 2).
 *
 * This used to be a flat `setInterval(..., 1000)`: 3,600 wake-ups an hour
 * whether or not a card was up, and whether or not this window was on screen.
 * Measured at 61 runs a simulated minute by `tests/timers.mjs`.
 *
 * The wait is now the thing the text can actually do next:
 *  - nothing on screen, or the card's clock is not running          -> IDLE_MS
 *  - an approval is counting down, or the heavy gate is ("unlocks in 2s") -> 1 s
 * The align step in `clock-timer.js` is added to this, so the digits turn
 * over on the second rather than a little later every tick.
 */
function clockWaitMs() {
  const line = document.querySelector("#approval .approval-reassure");
  if (!state.approval || !line || dom.approval.hidden) return IDLE_MS;
  if (isHeavy(state.approval) && !heavyGate.ok) return 1000;
  return state.approval.expiresAt ? 1000 : IDLE_MS;
}

const approvalClock = clockTimer(() => {
  if (state.approval && !dom.approval.hidden) paintApprovalClock();
}, { delay: clockWaitMs, name: "hud" });
approvalClock.wake();

/**
 * The card opened, closed or was replaced: the line under the risk row is
 * about to change, so the clock re-arms now rather than on its next wake -
 * which may be the idle minute away (2026-10-08 cohesion audit, finding 2).
 * Called from `syncApprovalButtons`, the one place every surface repaints a
 * card from.
 */
export function nudgeApprovalClock() {
  approvalClock.wake();
}

function desktopUndoNotice(approval) {
  if (!approval) return null;
  const risk = approval.risk || {};
  if (risk.reversible === "no") return "This cannot be undone.";
  const action = approval.action;
  if (action === "tidy_inbox") return "Inbox tidy: 10 minutes to undo.";
  if (action === "forget_time_frame" || action === "forget_fact") return "Memory: 10 minutes to undo.";
  if (action === "reminder_create" || action === "reminder_delete") return "Reminders: say “cancel that” to undo.";
  if (action === "model_switch" || action === "model_install") return "Model: roll back anytime in settings.";
  if (action === "setting_change" || action === "toggle_feature") return "Settings: turn back off anytime.";
  if (action === "write_note" || action === "smart_home_light") return null;
  if (risk.reversible === "yes") return "Undo is available for this action.";
  return null;
}

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
    // An inbox tidy approved here: its Undo strip shows as soon as the PC has done it.
    if (approved && approval.action === "tidy_inbox" && inboxTidyView) {
      inboxTidyView.watchQuickly();
    }
    // The card's own title (card-words.js), not the code name.
    let decisionLine = `${approved ? "Approved" : "Denied"} in the Jarvis bar: ${cardTitle(approval)}.`;
    if (approved) {
      const cue = desktopUndoNotice(approval);
      if (cue) decisionLine += `\n> ${cue}`;
    }
    state.buffer += `${state.buffer.trim() ? "\n\n" : ""}> ${decisionLine}`;
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
      // "Nothing was approved. Windows Hello is not set up ..." (lock/rules.rs
      // not_approved_words) already says what happened and what to do.
      : /^Nothing was approved\./.test(message) ? message
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
    // `: jarvis-table <id>` (spending summaries): a table to fetch and draw
    // under this answer. Not the answer's words, so never appended.
    const tableId = tableIdFromLine(line);
    if (tableId && spendingView) spendingView.arrived(tableId);
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

  // A `stream: false` style body names its table as a top-level field.
  const bodyTable = tableIdFromBody(chunk);
  if (bodyTable && spendingView) spendingView.arrived(bodyTable);

  if (chunk.error) {
    // The PC's own failure (jarvis_agent's plain sentence, with a `code`):
    // the shared plain words and a fix button, the sentence behind Details.
    showProblem(fromStreamError(chunk.error));
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

/** What `: jarvis-status <word>` means, for the card's status line - the
 *  shared words (plain-errors.js). "loading" is the PC saying the model is
 *  not in memory yet (after standby): the first words take longer. */
const WAIT_STATUS = {
  approval: STATUSES.approval,
  working: STATUSES.working,
  thinking: STATUSES.thinking,
  loading: STATUSES.loading,
  // How the card ended (jarvis_agent.CARD_OUTCOME_WORDS): the wait is over,
  // and the answer is on its way.
  approved: STATUSES.thinking,
  denied: STATUSES.thinking,
  timed_out: STATUSES.thinking,
};

function showWaitStatus(word) {
  // A spoken question waiting on a card hears so, and then how it ended
  // (card-words.js). Fixed lines, never the card's words - and never an
  // invitation to answer by voice: only a tap on the card decides.
  const cardLine = state.voiceTurn ? cardVoice.onStatus(word) : null;
  if (cardLine) sayCardLine(cardLine);
  // A tool ran (or waited on its card) while this answer was written: the
  // rest of a voice answer is not read aloud unless the owner allowed it.
  if (TOOL_WORDS.includes(word) && !state.toolRan) {
    state.toolRan = true;
    if (!speakableNow()) {
      dropAnswerSpeech();
      // Not straight after "there's a card on your screen": the fixed
      // private line comes when the answer's words do (enqueueSpeech).
      if (state.voiceTurn && !cardLine) sayPrivateLineOnce();
    }
  }
  const text = WAIT_STATUS[word];
  if (!text || state.phase !== "streaming" || dom.card.hidden) return;
  if (dom.cardStatusText.textContent === text) return;
  dom.cardStatusText.textContent = text;
  if (word === "approval") announce("Waiting for your approval.");
  if (word === "loading") announce(STATUSES.loading);
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
  if (!state.chunks) dom.cardStatusText.textContent = STATUSES.answering;
  if (!state.chunks && state.liveTurn) liveAnswerArrived();
  state.buffer += text;
  state.chunks += 1;
  updateStat();
  paint();
  checkForSpeakableSentence();
}

/** The card's corner used to count the pieces received and the seconds -
 *  developer information. It says nothing now; the status line says what
 *  is going on. */
function updateStat() {
  dom.cardStat.textContent = "";
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
    // stream_chat's tagged facts (plain_errors.rs) -> the plain words.
    showProblem(fromChatFailure(error));
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
        ...(payload.temporary ? { temporary: true } : {}),
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
    showProblem(
      error instanceof TypeError
        ? { ...shown("jarvis_not_running"), details: `fetch ${JARVIS_SERVER}: ${error.message}` }
        : fromChatFailure(error)
    );
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
async function send(promptText, provenance = "typed", { live: isLive = false, cloudYes = false } = {}) {
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
  hideChatNote();
  if (dom.chatEndedNote) dom.chatEndedNote.hidden = true;
  // A new conversation after the owner's own wait (Settings -> "A new
  // conversation starts after"; 30 quiet minutes by DEFAULT - the owner's
  // decision, 2026-09-28, and what a missing or unreadable choice reads as).
  // "Never" is a real choice: then this only fires when the owner starts a new
  // conversation. Never in the middle of Jarvis Live, which has its own quiet
  // rule. The old one stays in History; Continue brings it back.
  const idleWaitMs = storedIdleNewMs();
  if (!liveOnHere() && idleExpired(state.lastTurnAt, Date.now(), state.conversation.length > 0, idleWaitMs)) {
    // A temporary chat or a game was never kept, so there is no "last one in
    // History" to point to or carry on (the second chat audit, desktop C2).
    const kept = !(temporaryChat.on || state.gameChat);
    const ended = state.conversationId;
    startFreshQuietly(kept ? IDLE_NEW_LINE : IDLE_NEW_LINE_TEMPORARY,
      { carryOn: kept ? ended : null });
  }
  // Jarvis Live: a spoken turn is marked, and its tap buttons go.
  liveBeforeSend(isLive, provenance);

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
  paintYouLine(message);
  // How it was asked, as given - so "Try again" under a failed answer sends
  // the same words with the same tag (a pasted question stays pasted).
  state.lastAsked = provenance;

  state.buffer = "";
  state.chunks = 0;
  // A new question: the last failure's fix button and Details go with it.
  paintProblem(null, "");
  // A new answer, so no id and no mark until the server gives it one.
  state.turnId = null;
  state.turnMark = "none";
  paintAnswerMark();
  // A new question starts with no cloud offer until the route header (if
  // any) says otherwise - the last answer's offer does not carry over.
  state.cloudOffer = null;
  paintCloudOffer();
  // ...and the last answer's spending table goes too (it is not kept).
  if (spendingView) spendingView.clear();
  spokenUpTo = 0;
  // "Stop" silences one turn, not every turn after it: a new question is
  // allowed to be answered out loud again. Cleared only past the guard
  // above, so a push-to-talk barge-in whose send() was refused because the
  // old answer is still streaming leaves that old answer muted.
  speechMuted = false;
  // A new question supersedes whatever of the last answer was still
  // waiting to be said: its queued sentences, and a clip already made
  // ahead for it, are dropped (a clip playing right now finishes). Kept,
  // they would be checked against THIS question's privacy - its route, its
  // tools - not their own.
  speechQueue = [];
  aheadClip = null;
  // Interrupting by talking starts again with this answer (its own three
  // seconds of grace), and "One moment." may be said once for it - only
  // when it was asked out loud (voice-flow.js).
  interrupt.replyEnded();
  endPause();
  lastPlayedText = null;
  if (state.voiceTurn) {
    momentFlow.turnStarted();
    refreshVoiceFlow();
  } else {
    momentFlow.turnEnded();
  }
  // Nothing is known yet about whether this answer is private.
  state.turnRoute = null;
  state.toolRan = false;
  state.privateLineSaid = false;
  cardVoice.reset();
  // Where the tool counters stood when the question was sent: a `step`
  // event after this, or a drop in the event stream, keeps the rest of a
  // voice answer on screen (private-speech.js).
  state.toolStart = toolWatch.snapshot();
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
  if (!live.keep) {
    dom.answer.innerHTML = "";
    dom.answer.classList.remove("wellbeing-crisis");
  }
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

  // Clipboard context rides as its own USER turn, tagged "clipboard", just
  // before the question - the same shape as the phone's Share
  // (JARVIS-API.md section 18.1). It used to be a system turn, and the PC's
  // outside-text rules only read user turns, so copied text slipped past the
  // "note writes after outside text ask first" rule (security audit M1). The
  // server validates an OpenAI-shaped `messages` array and routes on
  // `has_image`.
  //
  // The conversation so far goes FIRST, then this turn's clipboard block,
  // then the question. Ollama reuses what it has already read only up to
  // the first thing that changed, so the earlier turns - identical from one
  // request to the next - must lead, and the per-turn clipboard block must
  // come after them. (It is a user turn now, so it no longer puts a system
  // message at position 0 on a first turn, which made Ollama drop the
  // Modelfile's own SYSTEM prompt - memory-prefix.patch quotes the line.)
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
        ? [userMessage(`Context:\n${state.clipboard}`, "clipboard")]
        : []),
      liveTag(withCutOff(screenTag(userMessage(content, state.turnProvenance)))),
    ],
    hasImage: Boolean(state.capture),
    auto: true,
    // JARVIS-API.md section 18. Informational for the PC's History list;
    // stream_chat (commands.rs) passes on only a well-formed id and a
    // device it knows.
    conversationId: state.conversationId,
    device: "desktop",
    // A temporary chat (section 18.1): no memory used, nothing learned,
    // nothing kept. stream_chat sends it only to a PC that has one.
    temporary: temporaryChat.on,
    // The owner's yes to "Try the cloud model" for THIS one question
    // (backend/cloud-say-yes.patch). stream_chat forwards it only when
    // true, the same rule it already follows for `temporary`.
    cloudYes,
  };
  // The picture is this ONE question's, and it goes with it (the owner's
  // decision of 2026-10-07; SCREEN-ATTACH-DESIGN.md's flow, step 5). The
  // design described the old attachment as already working this way; it did
  // not - a capture stayed in the box until it was removed or the bar closed,
  // so a screenshot taken for a chart would quietly ride on the next,
  // unrelated question. Cleared AFTER `content`, `turnProvenance` and
  // `hasImage` are built from it, and never on the path that holds the words
  // back (the "your model can't see pictures" notice returns above, with the
  // picture still attached and still on screen).
  if (state.capture) {
    state.capture = null;
    dom.captureThumb.removeAttribute("src");
    syncAttachments();
  }
  // What this answer used, and what the PC said about a temporary one,
  // start from nothing (answer-memory.js).
  answerMemory.begin(temporaryChat.on);
  temporaryChat.paint(false);

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
    const out = await invokeStrict("mark_answer", {
      turnId,
      mark: next,
      conversationId: state.conversationId,
    });
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

/** Shows or hides "A cloud model could give this one a second look." */
function paintCloudOffer() {
  if (!dom.answerCloudOffer) return;
  const show = Boolean(state.cloudOffer) && state.phase === "done";
  dom.answerCloudOffer.hidden = !show;
}

/** "Try the cloud model": the owner's yes for this one question only -
 *  resends the same words that earned the offer, with `cloud_yes: true`. */
function tryCloudModel() {
  const again = state.lastPrompt;
  const asked = state.lastAsked || "typed";
  state.cloudOffer = null;
  paintCloudOffer();
  if (again) send(again, asked, { cloudYes: true });
}

/** "Not now": the offer was seen and declined, for this answer only. */
function dismissCloudOffer() {
  state.cloudOffer = null;
  paintCloudOffer();
}

if (dom.cloudOfferTry) dom.cloudOfferTry.addEventListener("click", tryCloudModel);
if (dom.cloudOfferDismiss) dom.cloudOfferDismiss.addEventListener("click", dismissCloudOffer);

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
  // Jarvis Live's side talk: "(not for Jarvis)", not kept, never spoken.
  const sideTalk = phase !== "error" && liveSideTalk();
  // A crisis turn (the PC's own flag): its question and its help answer stay
  // on screen as the current answer, but never join the thread or what the
  // model is re-sent, so the next question (or leaving the chat) takes them
  // off the screen for good (the owner, 2026-09-29). The chat is still kept
  // in History by the PC, as "A difficult moment".
  const crisisTurn = crisisRoute(state.turnRoute);
  if (
    question &&
    !sideTalk &&
    keepsInThread(crisisTurn) &&
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
    state.thread = addToThread(state.thread, question, state.buffer);
    state.lastTurnAt = Date.now();
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
  // "Used 2 memories" on an answer that came back, and whether a temporary
  // one was confirmed (answer-memory.js).
  answerMemory.finish(phase !== "error");
  refreshThreadHidden();
  // "A cloud model could give this one a second look." - shown only once
  // the answer is really done, and only when this one earned an offer.
  paintCloudOffer();

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
  // No tool can start for this answer any more: no "One moment." after it.
  momentFlow.turnEnded();
  if (wasVoiceTurn && !sideTalk && phase !== "error" && !speechMuted) {
    const remainder = state.buffer.slice(spokenUpTo).trim();
    if (remainder) enqueueSpeech(remainder);
  }
  // Jarvis Live: tap buttons after a spoken question, and a sentence that
  // waited for this answer goes now.
  liveTurnFinished(wasVoiceTurn && !sideTalk && phase !== "error" && !statusText);

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
  // closeCard empties the conversation itself, and says where the chat went
  // (it used to be emptied here first, so it never knew there had been one).
  closeCard();
  announce(`${NEW_CONVERSATION} Your next question starts fresh.`);
  focusInput();
}

/* "Continue this chat", and a chat deleted elsewhere (the chat audit,
   2026-09-28). The Brain names a chat to carry on (brain_continue_chat ->
   the `continue-chat` event, the id only); a chat the Brain deleted - by
   Delete, "Erase the words" with its chat, or "Forget a time frame" - is
   left under CHAT_GONE_KEY: if it is the one this bar is in, its old turns
   must stop being sent, so a new conversation starts and the bar says so. */
listen("continue-chat", (event) => {
  const id = event && typeof event.payload === "string" ? event.payload : "";
  if (id) continueChat(id);
});

function chatsGoneElsewhere() {
  const gone = takeChatsGone();
  if (gone.includes(state.conversationId) && state.conversation.length) {
    startFreshQuietly(CHAT_GONE);
  }
}
window.addEventListener("storage", (e) => {
  if (e.key === CHAT_GONE_KEY && e.newValue) chatsGoneElsewhere();
});
window.addEventListener("focus", chatsGoneElsewhere);

/* ==========================================================================
   Voice: push-to-talk in, a spoken reply out
   ========================================================================== */

/** Whether the microphone is currently open. Mirrors `dom.mic`'s
 *  `aria-pressed`, kept separately so a stray extra pointerup (a second
 *  finger, a mouse button released outside the window) cannot try to stop a
 *  recording that never started. */
let micRecording = false;

/**
 * "Caught it" (item 7, UI-AUDIT-2026-09-26.md): the reactor contracts toward
 * its core and springs back, once, the moment the talk button is let go -
 * the desktop's answer to the phone's haptic tick, since a PC cannot buzz.
 * A plain CSS class plus a `@keyframes` in style.css; reduced motion already
 * collapses any one-shot animation to nothing, the same as `.fresh`/`card-in`
 * elsewhere in this file, so this needs no motion check of its own.
 */
function inhaleReactor() {
  const el = dom.reactor;
  if (!el) return;
  el.classList.remove("inhale");
  // Force a reflow so letting go again before the last inhale finished
  // restarts the animation instead of the class-add being a no-op.
  void el.offsetWidth;
  el.classList.add("inhale");
}
dom.reactor?.addEventListener("animationend", (event) => {
  if (event.animationName === "reactor-inhale") dom.reactor.classList.remove("inhale");
});

async function startPushToTalk() {
  if (micRecording || state.autoListening) return;
  // Barge-in: holding the mic to talk again is as clear a signal as this
  // app gets that whatever Jarvis was saying is done mattering right now.
  noteCutOff();
  stopSpeaking();
  micRecording = true;
  dom.mic.setAttribute("aria-pressed", "true");
  // While the owner talks: what the PC allows now, and its "One moment."
  // clip, so both are here before the answer needs them.
  refreshVoiceFlow();
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
  // The owner's turn is over: a small "I heard you" (voice-flow.js) and the
  // reactor's own "Caught it" (item 7, UI-AUDIT-2026-09-26.md) - on the same
  // beat, same as the phone's tick-plus-inhale. Only on a real release: a
  // pointer cancel (abandonPushToTalk, below) never played this either.
  playHeardSound();
  inhaleReactor();
  try {
    const heard = await invokeStrict("stop_voice_capture");
    if (!heard.available) {
      announce(heard.reason || "Speech recognition is not available here.", "assertive");
      return;
    }
    if (heard.tooShort) {
      // Refused before the voice check (docs/JARVIS-API.md section 16): the
      // PC's own sentence says how much more to say. Not "that did not
      // sound like you" - it was never checked.
      announce(heard.reason || "That was too short to be sure it was you. Say a little more.", "assertive");
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
    state.voicePrivacy = privacyFromHeard(heard);
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
/** True while a clip is actually playing (not while its sound is still
 *  being made). Only then is the next sentence's sound asked for. */
let clipPlaying = false;
/** The next sentence, its sound already asked of the backend while the
 *  current clip plays - `{ text, generation, request }`, or null. One
 *  ahead, never more, so the PC makes one sentence's sound at a time.
 *  Dropped by "stop", by a new question, and when the answer turns out to
 *  be private; checked again right before it is played either way. */
let aheadClip = null;
/** One `AudioContext` reused across every clip, rather than one per
 *  sentence: `attachSpeechSource` (voice.js) would otherwise open and close
 *  one per `Audio` element, and a fast reply is many of those a second. */
let speechAudioCtx = null;
function speechContext() {
  if (speechAudioCtx) return speechAudioCtx;
  const Ctx = typeof AudioContext === "function"
    ? AudioContext
    : typeof webkitAudioContext === "function" ? webkitAudioContext : null;
  if (!Ctx) return null;
  try { speechAudioCtx = new Ctx(); } catch { speechAudioCtx = null; }
  return speechAudioCtx;
}

/**
 * Lip-sync (face-voice.js): tells the faces in the other windows - the
 * Widget's, the floating face, the HUD's - about one clip as it plays: its
 * mouth track once, then where the playback is. Every sound Jarvis makes
 * here goes through this - the answer's sentences, "One moment.", a focus
 * line, a timer said aloud - so the animals' mouths move with every word
 * and never without one. Returns the function that stops following it.
 *
 * `routed`: the clip plays through `speechContext()`'s Web Audio graph
 * (`attachSpeechSource`), whose own output delay the element's clock does
 * not include - so it is taken off, and the mouth follows what is HEARD,
 * not what has been handed to the graph.
 */
function followForFaces(audio, uri, routed = false) {
  const ctx = routed ? speechAudioCtx : null;
  const latency = ctx ? (Number(ctx.baseLatency) || 0) + (Number(ctx.outputLatency) || 0) : 0;
  return followClip(audio, uri, { send: sendFaceVoice, latency });
}

/** One lip-sync message to Rust, which hands it to every window
 *  (voice.rs `face_voice`). Failures are the caller's to drop quietly. */
function sendFaceVoice(cue) {
  if (!IS_TAURI) return Promise.resolve();
  return TAURI.core.invoke("face_voice", { cue });
}

/** Interrupting by talking and "One moment." (voice-flow.js): the rules,
 *  and what the PC allows (`get_voice_flow`, the `flow` block of
 *  /api/voice/status - nothing, until it says). */
const interrupt = createInterruptFlow();
const momentFlow = createMomentFlow();
/** Where the owner last cut a spoken answer off, for the next question. */
const cutOff = createCutOff();
/** The sentence playing now, and the last one that started - for `cutOff`. */
let playingText = null;
let lastPlayedText = null;
let voiceFlow = flowFromStatus(null);
/** The "One moment." clip, `{key, uri}`, fetched again when the PC's key
 *  changes (another voice). */
let momentClip = null;
/** The reply is paused while the PC checks whether the owner is talking. */
let speechPaused = false;
/** Clips waiting to start until the pause ends. */
let pauseWaiters = [];
/** Carries on after `WAIT_MAX_MS` with no answer from the PC. */
let pauseTimer = null;
/** "One moment." while it plays, and the promise of its end. */
let momentAudio = null;
let momentDone = null;
let finishMoment = null;

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

/** Looks for one or more complete pieces that have arrived since
 *  `spokenUpTo` and queues each to be spoken (speech-pieces.js). A piece
 *  is a sentence - end punctuation FOLLOWED BY whitespace, because the
 *  stream may simply not have produced the next character yet, and
 *  speaking a sentence the model was about to keep extending would need it
 *  un-said a moment later. The FIRST piece of an answer (nothing cut yet,
 *  `spokenUpTo` 0) may end sooner, at its first comma once the phrase is
 *  long enough, so Jarvis starts talking sooner. Not fool-proof against
 *  "Dr." or "3.14" - a real sentence splitter is more machinery than a
 *  queue that is, worst case, a little choppier warrants. */
function checkForSpeakableSentence() {
  if (!state.voiceTurn || speechMuted) return;
  // Jarvis Live: nothing is said while the answer could still be the side-
  // talk marker ("[not for me]"), which is never spoken.
  if (state.liveTurn && couldBeSideTalk(state.buffer)) return;
  for (;;) {
    const cut = nextSpeechPiece(state.buffer.slice(spokenUpTo), spokenUpTo === 0);
    if (!cut) return;
    spokenUpTo += cut.consumed;
    enqueueSpeech(cut.piece);
  }
}

function enqueueSpeech(text) {
  if (speechMuted) return;
  const clean = stripMarkdownForSpeech(text);
  if (!clean) return;
  if (!speakableNow()) {
    sayPrivateLineOnce();
    return;
  }
  speechQueue.push(clean);
  drainSpeechQueue();
}

/** The owner's private-answer rule for this voice turn (private-speech.js):
 *  may what it says be read aloud? */
function speakableNow() {
  const now = toolWatch.snapshot();
  // `: jarvis-status working` / `approval` names no tool: it counts as a
  // private one unless the `step` events since the question say every tool
  // that ran was a read-aloud one (web search, home status - the owner's
  // decision of 2026-09-27).
  const statusSaysPrivate = state.toolRan && !onlyReadAloudToolsBetween(state.toolStart, now);
  return mayReadAloud({
    ...(state.voicePrivacy || {}),
    route: state.turnRoute,
    toolRan: statusSaysPrivate || toolRanBetween(state.toolStart, now),
    // An answer about the screen: kept on screen unless the utterance reply
    // said `screenAloud` (the owner's decision of 2026-09-28).
    screenRead: screenReadBetween(state.toolStart, now),
    toolsKnown: toolsKnownBetween(state.toolStart, now),
  });
}

/** Something may have made the voice answer being read private - a tool
 *  ran, or the event stream stopped being able to say. What is queued is
 *  dropped and the fixed line said instead, once. */
function recheckSpeech() {
  // Nothing queued and no voice answer still arriving: nothing to hold back.
  if (!speechQueue.length && !aheadClip && !state.voiceTurn) return;
  if (speakableNow()) return;
  dropAnswerSpeech();
  sayPrivateLineOnce();
}

/** Drops what is queued of the answer, and a clip already being made for
 *  it ahead of time - but never a fixed line, which may already be
 *  queued or made (`privateLineSaid` is set when it is queued, so dropping
 *  it here would mean it is never said at all). */
function dropAnswerSpeech() {
  speechQueue = speechQueue.filter(isFixedLine);
  if (aheadClip && !isFixedLine(aheadClip.text)) aheadClip = null;
}

/** A line Jarvis says in its own fixed words - "It's on your screen." or a
 *  card line - never the answer's: always safe to say, whatever the answer. */
function isFixedLine(text) {
  return text === PRIVATE_LINE || isCardLine(text);
}

/** Which card line this spoken question has said (card-words.js). */
const cardVoice = createCardVoice();

/** Says one card line ("I need your OK for that..."), in the answer's
 *  queue so it never talks over a sentence already playing. */
function sayCardLine(line) {
  if (speechMuted) return;
  speechQueue.push(line);
  drainSpeechQueue();
}

/** Instead of a private answer, one fixed line - once per answer. */
function sayPrivateLineOnce() {
  if (state.privateLineSaid || speechMuted) return;
  state.privateLineSaid = true;
  speechQueue.push(PRIVATE_LINE);
  drainSpeechQueue();
}

/** The next queued line to ask a sound for, or undefined. Checked here, as
 *  its sound is asked for: a tool may have run since it was queued - then
 *  the rest of the answer is dropped and the fixed line comes instead. */
function takeNextLine() {
  for (;;) {
    const next = speechQueue.shift();
    if (next === undefined || isFixedLine(next) || speakableNow()) return next;
    dropAnswerSpeech();
    if (!state.privateLineSaid) {
      state.privateLineSaid = true;
      return PRIVATE_LINE;
    }
    // Already said or queued: a queued fixed line survived the drop above.
  }
}

/** Asks the backend for one line's sound. Never rejects: a missing voice
 *  is logged, and the line is skipped, not shown as an error banner over a
 *  perfectly good answer already on screen. */
function requestClip(text) {
  const request = invokeStrict("speak_reply", { text }).then((uri) => {
    // Lip-sync: the clip's mouth track is worked out as soon as its sound
    // arrives - usually while the sentence before it is still playing - so
    // starting it later waits on nothing (face-voice.js keeps the result).
    if (uri) trackFor(uri);
    return uri;
  }, (error) => {
    console.info("[quickbar] spoken reply unavailable:", error);
    return null;
  });
  return { text, generation: speechGeneration, request };
}

/** One ahead: while a clip plays, the next line's sound is asked for, so
 *  it is ready the moment this one ends instead of after a silence as long
 *  as the backend takes to make it. Only while a clip is PLAYING, and only
 *  one - never a second request while one is already on its way. */
function prefetchNextClip() {
  if (!clipPlaying || aheadClip || speechMuted) return;
  const next = takeNextLine();
  if (next === undefined) return;
  aheadClip = requestClip(next);
}

/** Speaks whatever is queued, one clip at a time, through the backend's
 *  TTS, asking for the next clip's sound while the current one plays. */
async function drainSpeechQueue() {
  if (speaking) {
    // A line queued while a clip plays: its sound is made now.
    prefetchNextClip();
    return;
  }
  if (speechMuted) {
    speechQueue = [];
    aheadClip = null;
    return;
  }
  speaking = true;
  syncLiveAnswer();
  const generation = speechGeneration;
  try {
    for (;;) {
      let clip = aheadClip;
      aheadClip = null;
      if (!clip || clip.generation !== generation) {
        const next = takeNextLine();
        if (next === undefined) return;
        clip = requestClip(next);
      }
      const dataUri = await clip.request;
      // "Stop" may have landed while the backend was making this clip. If it
      // did, the clip is dropped here - playing it now would be exactly the
      // sentence the owner just asked Jarvis to stop saying.
      if (generation !== speechGeneration || speechMuted) return;
      // Checked again right before it is played, not only when its sound
      // was asked for: a tool may have run, or the event stream dropped,
      // while the sound was being made. Then this clip is dropped unplayed
      // and the fixed line said instead, once.
      if (!isFixedLine(clip.text) && !speakableNow()) {
        dropAnswerSpeech();
        if (!state.privateLineSaid) {
          state.privateLineSaid = true;
          speechQueue.push(PRIVATE_LINE);
        }
        continue;
      }
      if (!dataUri) continue;
      await playClip(dataUri, generation, clip.text);
      if (generation !== speechGeneration) return;
    }
  } finally {
    // A drain that "stop" overtook leaves the bookkeeping alone: stopSpeaking
    // already reset it, and a newer drain may own it by now.
    if (generation === speechGeneration) {
      currentAudio = null;
      finishCurrentClip = null;
      clipPlaying = false;
      speaking = false;
      syncLiveAnswer();
    }
  }
}

/** Plays one clip to its end (or until "stop"), asking for the next
 *  line's sound as it starts. */
async function playClip(dataUri, generation, text = "") {
  // The reply is about to make a sound: "One moment." is not started after
  // this, and one already playing is let finish first (it is under a
  // second) - never over the reply.
  momentFlow.replyStarted();
  // Jarvis Live: a sound was made - a second thought no longer joins it.
  live.sounded = true;
  if (momentAudio && momentDone) await momentDone;
  // Paused while the PC checks whether the owner is talking: this clip
  // waits, and is dropped if the answer was "stop".
  if (speechPaused) await new Promise((resolve) => pauseWaiters.push(resolve));
  if (generation !== speechGeneration) return;
  const audio = new Audio(dataUri);
  currentAudio = audio;
  clipPlaying = true;
  // "It's on your screen." is not a sentence of the answer.
  const own = text && !isFixedLine(text) ? text : null;
  playingText = own;
  if (own) lastPlayedText = own;
  // The reactor's mic-and-voice meter (item 1, UI-AUDIT-2026-09-26.md): the
  // level of the audio actually playing, never a guess at what it might
  // sound like. `attachSpeechSource` (voice.js) was already written for
  // exactly this and never called - this is the clip it was written for.
  // A context that fails to open (no Web Audio, or blocked) leaves the
  // reactor on its honest synthetic fallback; the reply still plays either
  // way, since detachLevel is a no-op and nothing here awaits it.
  const speechCtx = speechContext();
  if (speechCtx && speechCtx.state === "suspended") speechCtx.resume().catch(() => {});
  const detachLevel = speechCtx ? attachSpeechSource(audio, { context: speechCtx }) : () => {};
  // Lip-sync: the faces in the other windows follow this clip's own clock.
  const unfollow = followForFaces(audio, dataUri, Boolean(speechCtx));
  try {
    try {
      await audio.play();
    } catch (error) {
      // Paused (an interruption being checked) before it could begin: it
      // starts when the pause ends - resumeSpeaking plays `currentAudio` -
      // instead of being skipped.
      if (!(speechPaused && currentAudio === audio)) throw error;
    }
    interrupt.replyStarted(performance.now());
    prefetchNextClip();
    await new Promise((resolve) => {
      if (currentAudio !== audio) return resolve();
      finishCurrentClip = resolve;
      audio.onended = resolve;
      audio.onerror = resolve;
    });
  } catch (error) {
    console.info("[quickbar] spoken reply unavailable:", error);
  } finally {
    detachLevel();
    unfollow();
    if (playingText === own) playingText = null;
    if (generation === speechGeneration) {
      clipPlaying = false;
      currentAudio = null;
      finishCurrentClip = null;
    }
  }
}

/** Barge-in: discards anything still queued, stops whatever is playing right
 *  now, drops a clip still being made, and keeps the rest of this reply
 *  quiet even though it is still streaming in - called the moment the owner
 *  starts talking again, on either listening mode, and when the card
 *  closes. The next `send()` lets Jarvis speak again. */
function stopSpeaking() {
  stopFocusCallout();
  speechMuted = true;
  speechGeneration += 1;
  interrupt.replyEnded();
  momentFlow.stopped();
  stopMoment();
  endPause();
  speechQueue = [];
  // A clip made ahead is dropped with the rest (its generation is old now,
  // so it would not be played anyway).
  aheadClip = null;
  clipPlaying = false;
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
  syncLiveAnswer();
}

/* ── Focus session callouts ────────────────────────────────────────────────
   One line of a focus session ("YouTube can wait."), sent by Rust as SOUND
   (brain/focus.rs play_callout fetches it from this PC's backend - the words
   never reach this window). Played on its own element, never through the
   answer's queue, and never over Jarvis talking: a line that arrives while
   an answer is being spoken is dropped - the next drift says it again.
   "Stop" (stopSpeaking) silences it too. It opens no microphone.

   "Stop everything" silences one that is playing (stopSpeaking), and one
   still on its way is dropped: Rust drops a sound that was being made when
   the stop came (focus.rs play_callout), and this page ignores any callout
   for a few seconds after a stop, in case one was already in flight. */
let focusAudio = null;
let focusStoppedAt = 0;
const FOCUS_STOP_QUIET_MS = 5000;

/** Stops following the focus line playing now, for the faces (lip-sync). */
let focusUnfollow = () => {};

function stopFocusCallout() {
  if (!focusAudio) return;
  focusAudio.onended = null;
  focusAudio.pause();
  focusUnfollow();
  focusAudio = null;
}

function playFocusCallout(payload) {
  const uri = payload && typeof payload.uri === "string" ? payload.uri : "";
  if (!uri.startsWith("data:audio/wav;base64,")) return;
  if (jarvisTalking() || focusAudio) return;
  if (focusStoppedAt && Date.now() - focusStoppedAt < FOCUS_STOP_QUIET_MS) return;
  const audio = new Audio(uri);
  focusAudio = audio;
  // Lip-sync, as for an answer's sentence; `ended` or `stopFocusCallout`
  // stops following it.
  const unfollow = followForFaces(audio, uri);
  focusUnfollow = unfollow;
  audio.onended = () => {
    if (focusAudio === audio) focusAudio = null;
  };
  audio.play().catch((error) => {
    console.info("[quickbar] focus callout could not play:", error);
    unfollow();
    if (focusAudio === audio) focusAudio = null;
  });
}

listen("focus-callout", (event) => playFocusCallout(event.payload));

/** Whether Jarvis is talking: a clip is being made or played, or more are
 *  queued behind it. */
function jarvisTalking() {
  return speaking || speechQueue.length > 0 || aheadClip !== null;
}

/* -- Interrupting by talking: pause first, decide second (voice-flow.js) -- */

/** Pauses the reply where it is, until the PC answers or `WAIT_MAX_MS`. */
function pauseSpeaking() {
  speechPaused = true;
  if (currentAudio) currentAudio.pause();
  clearTimeout(pauseTimer);
  pauseTimer = setTimeout(() => actOnInterrupt(interrupt.tick(performance.now())), WAIT_MAX_MS);
}

/** Lets clips waiting on the pause go (they check "stop" themselves). */
function endPause() {
  speechPaused = false;
  clearTimeout(pauseTimer);
  pauseTimer = null;
  const waiting = pauseWaiters;
  pauseWaiters = [];
  waiting.forEach((resolve) => resolve());
}

/** Carries on from where the reply paused. */
function resumeSpeaking() {
  if (!speechPaused) return;
  const audio = currentAudio;
  endPause();
  if (audio) audio.play().catch(() => {});
}

function actOnInterrupt(action) {
  if (action === PAUSE) pauseSpeaking();
  else if (action === RESUME) resumeSpeaking();
  // The owner's voice (or "stop"): silenced for good, a sentence made
  // ahead dropped with it - and nothing else. It is not a command.
  else if (action === STOP) {
    noteCutOff();
    stopSpeaking();
  }
}

/** The owner is cutting the spoken answer off: the sentence they heard last
 *  goes with the next question (voice-flow.js `createCutOff`), so the PC
 *  can tell its model the answer stopped there. Only while it is talking. */
function noteCutOff() {
  // Only to a PC that keeps it on the PC (`flow.cut_off`): an older one
  // could pass an unknown field on with the question.
  if (!jarvisTalking() || speechMuted || !voiceFlow.cutOff) return;
  cutOff.cut(playingText || lastPlayedText, performance.now());
}

/** The newest user message, with where the last answer was cut off when the
 *  owner cut it off in the last two minutes - once (JARVIS-API section 17,
 *  6). The PC takes the field off before any model or the relay sees it. */
function withCutOff(message) {
  const said = cutOff.take(performance.now());
  return said ? { ...message, interrupted: said } : message;
}

/** What the PC allows now (`flow` of /api/voice/status), and the "One
 *  moment." clip when its key changed. Never throws; an older PC allows
 *  nothing. */
async function refreshVoiceFlow() {
  let flow = null;
  try {
    flow = await invokeStrict("get_voice_flow");
  } catch {
    flow = null;
  }
  voiceFlow = flowFromStatus(flow ? { flow } : null);
  if (!voiceFlow.momentReady || !voiceFlow.momentKey) return;
  if (momentClip && momentClip.key === voiceFlow.momentKey) return;
  try {
    const uri = await invokeStrict("get_voice_moment");
    if (typeof uri === "string" && uri) momentClip = { key: voiceFlow.momentKey, uri };
  } catch (error) {
    console.info("[quickbar] no One moment clip:", error);
  }
}

/**
 * The face's mic-level meter (item 1, UI-AUDIT-2026-09-26.md): the
 * microphone's own loudness, 0..1, while push-to-talk or "hey Jarvis"
 * listening holds it open (voice.rs, `VOICE_LEVEL`) - never the audio
 * itself. `setLevel` (voice.js) is authoritative about the mode this puts
 * the reactor in: the moment a real level arrives it takes over from
 * whatever the event stream last said, and the arriving numbers replace
 * the synthetic "still listening" fallback with the owner's real voice.
 */
listen("voice-level", (event) => {
  setLevel(Number(event && event.payload));
});

/** Half a second of speech while listening (voice.rs): pause the reply,
 *  and have the PC say whether it was the owner. Only while Jarvis talks,
 *  with the owner's switch on, a PC that can tell the owner's voice, and a
 *  live link (rule 4); the first three seconds of a reply are ignored. */
listen("voice-barge-onset", (event) => {
  const id = event && event.payload ? Number(event.payload.id) : NaN;
  if (!Number.isFinite(id)) return;
  // Jarvis Live: lower the voice while the PC checks (live-rules.js).
  if (liveOnHere()) {
    liveBargeOnset(id);
    return;
  }
  const allowed = loadBargeIn() && voiceFlow.bargeIn && jarvisTalking() && !speechMuted &&
    toolWatch.snapshot().live;
  if (interrupt.onset(performance.now(), id, allowed) !== PAUSE) return;
  pauseSpeaking();
  invoke("judge_barge_in", { id });
});

/** The PC's answer: stop for good (the owner, or "stop"), or carry on. */
listen("voice-barge-verdict", (event) => {
  const v = (event && event.payload) || {};
  // The PC cannot tell the owner's voice now: no more checks until its
  // status says otherwise.
  if (v.available === false) voiceFlow = { ...voiceFlow, bargeIn: false };
  if (liveOnHere()) {
    liveBargeVerdict(v);
    return;
  }
  actOnInterrupt(interrupt.verdict(Number(v.id), v.stop === true));
});

/* -- "One moment." when a tool starts (voice-flow.js) -- */

function maybeSayOneMoment(data) {
  if (!isToolStart(data) || !state.voiceTurn || speechMuted) return;
  if (!momentFlow.toolStarted(loadMoment() && voiceFlow.moment, Boolean(momentClip))) return;
  const audio = new Audio(momentClip.uri);
  momentAudio = audio;
  // Lip-sync: "One moment." moves the mouths too; `end` stops following it
  // however it ends (played out, stopped, or the 3-second bound).
  const unfollow = followForFaces(audio, momentClip.uri);
  momentDone = new Promise((resolve) => {
    let bound = null;
    const end = () => {
      clearTimeout(bound);
      unfollow();
      if (momentAudio === audio) momentAudio = null;
      if (finishMoment === end) finishMoment = null;
      resolve();
    };
    finishMoment = end;
    audio.onended = end;
    audio.onerror = end;
    // Never holds the reply for long, whatever the audio does.
    bound = setTimeout(end, 3000);
    audio.play().catch(end);
  });
}

function stopMoment() {
  if (momentAudio) {
    momentAudio.onended = null;
    momentAudio.onerror = null;
    momentAudio.pause();
  }
  if (finishMoment) finishMoment();
  momentAudio = null;
}

/* -- "I heard you": a tiny sound when the owner's turn is cut -- */

let heardContext = null;
function playHeardSound() {
  // Settings -> Voice, "Play a short sound when I finish speaking"
  // (voice-flow.js): read each time, so a change in Settings counts at once.
  if (!loadHeard()) return;
  try {
    const Ctx = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (!Ctx) return;
    heardContext = heardContext || new Ctx();
    const samples = heardSoundSamples();
    const buffer = heardContext.createBuffer(1, samples.length, HEARD_SOUND.rate);
    const channel = buffer.getChannelData(0);
    samples.forEach((v, i) => {
      channel[i] = v / 32768;
    });
    const source = heardContext.createBufferSource();
    source.buffer = buffer;
    source.connect(heardContext.destination);
    if (heardContext.state === "suspended") heardContext.resume().catch(() => {});
    source.start();
  } catch (error) {
    console.info("[quickbar] no I-heard-you sound:", error);
  }
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
  // Jarvis Live: the owner's voice stops Jarvis unless "Interrupt by tap
  // only" is chosen (then the microphone is closed while Jarvis talks).
  if (liveOnHere()) {
    if (loadInterrupt() !== "voice") return;
    noteCutOff();
    stopSpeaking();
    return;
  }
  if (ignoreWhileTalking(loadBargeIn(), jarvisTalking())) return;
  noteCutOff();
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
    refreshVoiceFlow();
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
  // Jarvis Live's sentences, "let's talk", and the offer to move Live here.
  if (liveHeard(heard)) return;
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
  // "Hey Jarvis" was heard from the owner, but the command after it was
  // too short to check: said, with the PC's own words. A short clip WITHOUT
  // the phrase could be anyone in the room, so it stays silent.
  if (heard.tooShort && heard.wakeHeard) {
    announce(heard.reason || "That was too short to be sure it was you. Say a little more.");
    return;
  }
  if (!heard.isOwner) return; // ambient speech that is not the owner - ignored, not announced
  // "Hey Jarvis" from the owner: the turn was cut and taken - a small "I
  // heard you". Here, not when the listener cuts: that happens for every
  // sound in the room, and only the PC knows which were addressed to Jarvis.
  if (heard.wakeHeard) playHeardSound();
  if (heard.awake) {
    // "Hey Jarvis." on its own: the PC is listening for the next sentence.
    announce("Listening.");
    return;
  }
  const text = String(heard.text || "").trim();
  if (!text) return;
  state.voiceTurn = true;
  state.voicePrivacy = privacyFromHeard(heard);
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
  // Jarvis Live: Esc only hides the bar. The conversation, the answer on
  // screen and Live itself carry on (the review's #1 - it used to forget
  // the conversation mid-Live). End Live ends it.
  if (liveOnHere()) {
    await setPinned(false, { silent: true });
    await invoke("hide_quickbar");
    return;
  }
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
  // makes a voice transcript the owner's own typing (a clipboard snippet
  // stays "clipboard", like pasted text), and an emptied box starts again
  // as typed.
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
if (dom.carryOnLast) {
  dom.carryOnLast.textContent = CARRY_ON_LAST;
  dom.carryOnLast.title = carryOnLastTitle(storedIdleNewMs());
  dom.carryOnLast.addEventListener("click", () => {
    const id = state.lastChatId;
    hideCarryOn();
    if (id) continueChat(id);
  });
}
for (const b of [dom.earlierChats, dom.earlierChatsPrimer]) {
  if (b) {
    b.textContent = EARLIER_CHATS;
    b.title = EARLIER_CHATS_TITLE;
    b.addEventListener("click", openEarlierChats);
  }
}
if (dom.temporary) dom.temporary.addEventListener("click", () => temporaryChat.toggle());

dom.copy.addEventListener("click", async () => {
  const text = state.buffer.trim();
  if (!text) return;
  // Feasibility I114, "Private copy": an answer copied from here is kept
  // out of Windows Clipboard History (Win+V) and Cloud Clipboard sync -
  // both of them ways an answer that never left this PC over Jarvis's own
  // network could still leave it through Windows' own clipboard features
  // (clipboard_privacy.rs has the how and why). If the privacy command is
  // ever unavailable (an older build), fall back to a plain copy rather
  // than copying nothing at all - the owner still gets the text, just
  // without the exclusion.
  try {
    await invoke("write_clipboard_private", { text });
  } catch {
    await invoke("write_clipboard", { text });
  }
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

/* "Photo to reminder" (photo-reminder.js; JARVIS-API.md section 83): the
   PC reads the dates in the capture and PROPOSES a reminder here. Nothing
   is set up until "Add a Jarvis reminder" is tapped (ONE photo_add_reminder,
   held on a stale link in Rust). The words are outside text: shown with
   textContent only, never put in the prompt, never sent to the model from
   here, and dropped when the proposal closes. */
let photoView = null;

function closePhotoProposal() {
  if (photoView) photoView.close();
  photoView = null;
  if (dom.photoProposal) {
    dom.photoProposal.replaceChildren();
    dom.photoProposal.hidden = true;
  }
}

async function findDateInCapture() {
  const picture = state.capture;
  if (!picture || !dom.photoProposal) return;
  closePhotoProposal();
  dom.photoProposal.hidden = false;
  dom.photoProposal.textContent = PHOTO_READING;
  dom.captureFindDate.disabled = true;
  syncWindowHeight();
  let out = null;
  try {
    out = await invokeStrict("photo_scan", { image: picture });
  } catch (error) {
    dom.photoProposal.textContent = String(error && error.message ? error.message : error);
    dom.captureFindDate.disabled = false;
    syncWindowHeight();
    return;
  }
  dom.captureFindDate.disabled = false;
  // The capture was removed or replaced while the PC was reading.
  if (state.capture !== picture) return;
  photoView = mountProposal(dom.photoProposal, out, {
    invoke: invokeStrict,
    canAct: () => !currentLink().stale,
    buttonClass: "text-button",
    onClose: () => {
      photoView = null;
      syncWindowHeight();
    },
  });
  syncWindowHeight();
}

dom.captureFindDate.addEventListener("click", findDateInCapture);

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
  // A spending table still on screen is asked for again: hidden if the PC
  // has been locked meanwhile, drawn again once it is unlocked.
  if (spendingView) spendingView.recheck();
  // Rust sizes the bar back to its short height every time it is shown; the
  // height this window last reported would then look current and nothing
  // would grow it again - a chat still in memory sat invisible under the
  // prompt (the second chat audit, 2026-09-28, desktop worst-three #1).
  lastReportedHeight = 0;
  syncWindowHeight();
  commitWindowHeight();
  refreshThreadHidden();
});

// "Hide memory lists and chat history" came back on: the thread goes at once.
listen("private-hidden", () => {
  // The spending table goes at once, before anything else is decided.
  if (spendingView) spendingView.hide();
  if (state.threadHidden) return;
  state.threadHidden = true;
  renderPreviousAnswer({ open: dom.previousAnswer.open });
  syncWindowHeight();
});

// "Stop everything" (the hotkey, Alt+Shift+X by default): silence first,
// before the PC is even asked - commands.rs `stop_everything_now` sends this
// and then calls POST /api/stop_all itself, and says in a notification what
// was stopped. The answer on screen stays as far as it got.
listen("stop-everything", () => {
  focusStoppedAt = Date.now();
  stopSpeaking();
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

// A look the PC could not hand a picture back for (the owner's decision of
// 2026-10-07; SCREEN-ATTACH-DESIGN.md): the reason is said in the watch strip,
// in the PC's own plain words, and NOT as an error banner - the look itself
// worked, the answer box and the owner's words are left exactly as they are,
// and nothing about the screen is shown. `screenNotice` is the strip's own
// notice, the same place a refused look speaks.
listen("capture-failed", (event) => {
  const why = String(event.payload || "").trim();
  screenNotice(why || "Jarvis could not attach a picture of your screen.");
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
renderSayableList();
// The command palette (palette-ui.js): built from the menu catalogue, opened
// with "/" in an empty box or the "Find" button, closed with Escape. It never
// opens over a waiting gate - that card is the top surface then, and covering
// it would hide the one thing the app stops for.
mountPalette({
  openPlace: openPlaceFromPalette,
  canOpen: () => !state.approval,
  // "Show or hide menus" is cosmetic (nothing is turned off), so a hidden menu
  // is still listed - the palette is a way to reach one that was tidied away.
  // The row says "hidden", read from the same stored set the Settings card
  // reads, so the two can never disagree.
  isHidden: (id) => isHidden(loadMenuState(), id),
  onClose: () => syncWindowHeight(),
});
renderPaletteHint();
syncTaskControls();
startVoice(dom.root);
// Subscribed before the link starts, so the first state it reports counts.
onLink((link) => {
  toolWatch.link(link);
  recheckSpeech();
  // Lockdown (2026-09-28): said in the bar while it is on, from the link.
  if (dom.lockdownStrip && dom.lockdownStrip.hidden === Boolean(link.lockdown)) {
    dom.lockdownStrip.hidden = !link.lockdown;
    syncWindowHeight();
  }
  // Forget and Erase under "Used in this answer" are held on a stale link.
  answerMemory.linkChanged();
});
onEvent((frame) => {
  toolWatch.event(frame);
  if (frame && frame.kind === "step") {
    recheckSpeech();
    maybeSayOneMoment(frame.data);
    // Item 10 (UI-AUDIT-2026-09-26.md): the card used to feed a step only to
    // speech (above) and never to the screen, so it said "Working…" through
    // the whole of a tool call. Brain's Live tab already turns the same
    // event into words with `stepText` (now shared, step-words.js) - the bar
    // shows the same words here, not a word of its own.
    if (state.phase === "streaming" && !dom.card.hidden) {
      dom.cardStatusText.textContent = stepText(frame.data);
    }
  }
  // A timer going off, said aloud while "Hey Jarvis" listening is on - the
  // owner's "say timers aloud when voice is on" (2026-09-25). The toast
  // shows as well (Rust). Generic words only: the room may not be private.
  const aloud = aloudFor(frame, state.autoListening);
  if (aloud) sayAside(aloud);
});

/* ==========================================================================
   Jarvis Live (live.rs, live-rules.js; docs/LIVE-DESIGN.md)
   --------------------------------------------------------------------------
   A back-and-forth voice conversation the owner starts and stops. The PC
   holds the session; the microphone is Rust's (every sentence goes as
   `source=live` and is checked for the owner's voice before any words
   exist). This bar:
   - starts and ends it (the Live button - "End Live" once on), and shows
     the sign, with End Live, Mic off, Carry on, Resume Live, 20 more
     minutes (in the last five), Show the card, and Move it here when Live
     is on the phone;
   - sends each heard sentence as a spoken question marked `live: true`
     (the PC adds its Live note: short answers, choices in words, side talk
     answered with the marker only);
   - never speaks side talk: an answer that is only "[not for me]" leaves
     the answer on screen as it was (a crisis help panel included), shows
     "(not for Jarvis)" on the sign for a moment, and is left out of the
     conversation - the PC does not keep it either;
   - after a spoken answer that ends with a question, shows tap buttons
     under the answer - each is sent as the owner's TYPED words (typed-turn
     rules), and never while a card raised in this session is on screen;
   - while such a card is shown: speech pauses and the microphone closes
     (cards are decided by tapping only), and the sign says so;
   - interrupting ("Interrupting Jarvis", one setting): by voice, another
     voice LOWERS Jarvis's voice while the PC checks it, and it stops only
     if it was the owner; by button only, the microphone closes while
     Jarvis talks and "Stop talking" cuts it off; "Don't interrupt" shows no
     Stop talking;
   - a second thought said before Jarvis made a sound joins the question;
   - Esc hides the bar and keeps the conversation (it used to forget it);
   - typing or tapping keeps Live open (the PC's quiet clock);
   - a short tone when Live ends here, and the PC's fixed line for why.
   ========================================================================== */

/** Where "Settings, then Voice" opens (settings.html section id). */
const LIVE_TRAIN_PLACE = "voice";
/** Shown once, the first time Live is on here, until the first answer. */
const LIVE_EXPLAINED_KEY = "jarvis.live.explained";
const LIVE_TYPE_HINT = "Type to Jarvis - typed answers stay on screen";
const LIVE_EXPLAINER =
  "Jarvis now listens after every answer - just talk, no \"Hey Jarvis\" needed. Every sentence is checked for your voice first.";

function liveOnHere() {
  return onHere(live.status, LIVE_ME);
}

/** Seconds since Live ended, counted on from the PC's `ended_ago_s`. */
function liveEndedAgo() {
  if (!live.endedBase) return null;
  return live.endedBase.ago + Math.floor((Date.now() - live.endedBase.at) / 1000);
}

/** Does the card the bar shows hold Live? Only one raised in THIS session
 *  (live-rules.js `cardInSession`, the PC's own rule). */
function liveCardHolds() {
  return Boolean(state.approval) && liveOnHere() && cardInSession(state.approval.created, live.status);
}

function liveExplained() {
  try {
    return localStorage.getItem(LIVE_EXPLAINED_KEY) === "yes";
  } catch {
    return true;
  }
}

function paintLive() {
  if (!dom.liveStrip) return;
  const on = liveOnHere();
  // One name, one state: the button is "Jarvis Live" and pressed while on.
  dom.liveToggle.setAttribute("aria-pressed", String(on));
  dom.liveToggle.title = on
    ? "Jarvis Live is on - click to end it"
    : "Jarvis Live: talk back and forth, no \"Hey Jarvis\" needed";
  const now = Date.now();
  const flash = now < live.flashUntil;
  const sign = liveSign(live.status, LIVE_ME, {
    stale: live.stale,
    thinking: flash && live.thinking,
    short: flash && live.short,
    cardShown: liveCardHolds(),
    endedAgo: liveEndedAgo(),
  });
  const offer = live.elsewhere && !sign.show;
  const notice = !on && live.notice ? live.notice : "";
  const show = sign.show || Boolean(offer) || Boolean(notice);
  dom.liveStrip.hidden = !show;
  if (show) {
    dom.liveTitle.textContent = sign.show ? sign.title : TITLE;
    let detail = sign.detail;
    if (!detail && sign.stop && live.micWait) detail = live.micWait;
    if (!detail && sign.stop && live.lockUnknown) detail = LOCK_UNKNOWN_WORDS;
    if (!detail && sign.stop && live.callUnknown) detail = SEEN.call_unknown;
    if (!detail && sign.stop && now < live.troubleUntil) detail = SEEN.trouble;
    if (!detail && sign.stop && now < live.sideTalkUntil) detail = SEEN.not_for_me;
    if (offer) detail = moveWords(live.elsewhere);
    if (notice && !sign.show) detail = notice;
    if (detail && detail !== dom.liveDetail.textContent) announce(detail);
    dom.liveDetail.textContent = detail;
    // The end hint (and, the first time, what Live is), under the sign.
    let hint = "";
    if (on && !detail) hint = live.explaining ? LIVE_EXPLAINER : SEEN.end_hint;
    dom.liveHint.hidden = !hint;
    dom.liveHint.textContent = hint;
    // Temporary is on: this Live session is not kept in History (the owner,
    // 2026-09-29). Said once to a screen reader when it appears.
    const tempLine = on && temporaryChat.on ? SEEN.temporary_on : "";
    if (tempLine && dom.liveTemporary.hidden) announce(tempLine);
    dom.liveTemporary.hidden = !tempLine;
    dom.liveTemporary.textContent = tempLine;
    const s = live.status || {};
    dom.liveStrip.dataset.muted = String(Boolean(on && s.muted));
    dom.liveStrip.dataset.ended = String(!on);
    dom.liveEnd.hidden = !sign.stop;
    dom.liveEnd.textContent = sign.stop || BUTTONS.endLive;
    dom.liveMute.hidden = !sign.mute;
    dom.liveMute.textContent = sign.mute || BUTTONS.micOff;
    dom.liveCarryOn.hidden = !sign.carryOn;
    dom.liveResume.hidden = !sign.resume;
    dom.liveMore.hidden = !sign.moreTime;
    dom.liveShowCard.hidden = !sign.showCard;
    dom.liveFix.hidden = !(notice && live.noticeNeedsVoice);
    dom.liveStopTalking.hidden = !(on && jarvisTalking() && loadInterrupt() !== "off");
    dom.liveMove.hidden = !(sign.move || offer);
  }
  // Typing in Live: the same hint the phone's text box gives.
  if (on && !dom.prompt.dataset.livePlaceholder) {
    dom.prompt.dataset.livePlaceholder = dom.prompt.placeholder;
    dom.prompt.placeholder = LIVE_TYPE_HINT;
  } else if (!on && dom.prompt.dataset.livePlaceholder) {
    dom.prompt.placeholder = dom.prompt.dataset.livePlaceholder;
    delete dom.prompt.dataset.livePlaceholder;
  }
  // The tap buttons sit under the answer, not in the sign's row.
  const chips = on && !liveCardHolds() ? live.chips : [];
  dom.liveChips.hidden = chips.length === 0;
  dom.liveChips.replaceChildren(
    ...chips.map((chip) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "text-button";
      b.textContent = chip;
      b.addEventListener("click", () => liveTapChip(chip));
      return b;
    })
  );
  syncWindowHeight();
}

/** Repaints when the ended sign or Resume Live runs out (they never stay). */
function liveScheduleEndedRepaint() {
  clearTimeout(live.endedTimer);
  const ago = liveEndedAgo();
  if (ago === null) return;
  const limits = (live.status && live.status.limits) || {};
  const marks = [Number(limits.ended_show_s) || 15, Number(limits.resume_s) || 600]
    .map((s) => s + 1 - ago)
    .filter((s) => s > 0);
  if (!marks.length) return;
  live.endedTimer = setTimeout(() => {
    paintLive();
    liveScheduleEndedRepaint();
  }, Math.min(...marks) * 1000);
}

/** Why Live did not start, in the strip; "Settings, then Voice" gets a button. */
function liveRefused(why) {
  const text = String(why || "").trim() || "Jarvis Live could not start.";
  live.noticeNeedsVoice = text.startsWith(NEEDS_VOICE);
  live.resuming = false;
  live.notice = /^Jarvis Live/.test(text) ? text : `Jarvis Live didn't start. ${text}`;
  clearTimeout(live.noticeTimer);
  live.noticeTimer = setTimeout(() => {
    live.notice = "";
    paintLive();
  }, 30000);
  announce(live.notice, "assertive");
  paintLive();
}

async function toggleLive() {
  // One click at a time: a double click used to start Live twice, and the
  // second start took the Live microphone for a "hey Jarvis" one (bug 6).
  if (live.busy) return;
  live.busy = true;
  dom.liveToggle.setAttribute("aria-busy", "true");
  try {
    if (liveOnHere()) {
      await invokeStrict("live_stop");
    } else {
      live.elsewhere = "";
      live.notice = "";
      // A new Live session is a new chat: its id goes with Start, so the
      // PC can name it to the other device for "Move it here".
      live.pendingCid = newConversationId();
      await invokeStrict("live_start", { by: "button", conversationId: live.pendingCid });
    }
  } catch (error) {
    liveRefused(String((error && error.message) || error));
  } finally {
    live.busy = false;
    dom.liveToggle.removeAttribute("aria-busy");
  }
}

async function liveDo(command, args = {}) {
  try {
    await invokeStrict(command, args);
  } catch (error) {
    const why = String((error && error.message) || error);
    if (command === "live_start") liveRefused(why);
    else announce(why, "assertive");
  }
}

/** A tap button: the owner's own words, TYPED - a typed answer's rules. */
function liveTapChip(chip) {
  live.chips = [];
  paintLive();
  send(chip, "typed");
}

/** Called by `send`: is this a Live voice turn? Typing in Live keeps it open. */
function liveBeforeSend(isLive, provenance) {
  state.liveTurn = Boolean(isLive) && provenance === "voice" && liveOnHere();
  live.sounded = false;
  live.chips = [];
  clearTimeout(live.slowTimer);
  // What is on screen stays there until the new answer really starts - if it
  // turns out to be side talk, it never goes (the review's #2).
  live.keep = state.liveTurn && !dom.card.hidden && state.buffer.trim() && state.phase !== "error"
    ? {
      buffer: state.buffer,
      route: state.turnRoute,
      prompt: state.lastPrompt,
      previousAnswer: state.previousAnswer,
      turnId: state.turnId,
      turnMark: state.turnMark,
    }
    : null;
  if (state.liveTurn) {
    live.slowTimer = setTimeout(liveSlowFirstAnswer, LIVE_SLOW_MS);
    // The answer comes into this bar: shown (without taking the keyboard)
    // if it was hidden (live.rs `live_act` "show"; the review's #10).
    invoke("live_act", { action: "show" });
  } else if (liveOnHere() && provenance === "typed") {
    // The owner typed (or tapped a quick answer) in Live: the conversation
    // goes on, so the PC's quiet clock starts again (the review's B4).
    invoke("live_act", { action: "active" });
  }
  paintLive();
}

/** What `paint` shows while a Live answer could still be side talk: the
 *  answer that was on screen before, or null for the new one. */
function liveHeldAnswer() {
  if (!state.liveTurn || !live.keep) return null;
  if (!state.buffer.trim() || couldBeSideTalk(state.buffer)) return live.keep;
  live.keep = null;
  return null;
}

/** The newest user message, marked as said in Jarvis Live. */
function liveTag(message) {
  return state.liveTurn ? { ...message, live: true } : message;
}

/** Back to what the answer rule says about the microphone (held only while
 *  an answer plays and talking over it may not interrupt). */
function liveReleaseHold() {
  live.heldForAnswer = liveOnHere() && loadInterrupt() !== "voice" && speaking;
  if (!live.heldForAnswer) invoke("live_hold", { what: "answer", on: false });
}

/** The first answer is slow (the model loading): "One moment.", under its
 *  own switch, once per question (momentFlow), with the microphone held so
 *  Jarvis's own voice is not sent as a sentence (the review's #9). */
function liveSlowFirstAnswer() {
  if (!state.liveTurn || !state.inFlight || state.chunks || speechMuted) return;
  if (!momentFlow.toolStarted(loadMoment() && voiceFlow.moment, Boolean(momentClip))) return;
  const audio = new Audio(momentClip.uri);
  invoke("live_hold", { what: "answer", on: true });
  let done = false;
  const end = () => {
    if (done) return;
    done = true;
    liveReleaseHold();
  };
  audio.onended = end;
  audio.onerror = end;
  setTimeout(end, 3000);
  audio.play().catch(end);
}

function liveAnswerArrived() {
  clearTimeout(live.slowTimer);
  live.thinking = false;
  live.flashUntil = 0;
  if (live.explaining) {
    live.explaining = false;
    try {
      localStorage.setItem(LIVE_EXPLAINED_KEY, "yes");
    } catch {
      /* shown again next time: harmless */
    }
  }
  paintLive();
}

/** Called by `finishStream` before the answer is kept: side talk is never
 *  spoken, leaves what was on screen as it was, shows "(not for Jarvis)" on
 *  the sign, and is not kept in the conversation. */
function liveSideTalk() {
  if (!state.liveTurn || !isSideTalk(state.buffer)) return false;
  const kept = live.keep;
  live.keep = null;
  live.sideTalkUntil = Date.now() + LIVE_FLASH_MS;
  if (kept) {
    state.buffer = kept.buffer;
    state.turnRoute = kept.route;
    state.lastPrompt = kept.prompt;
    state.previousAnswer = kept.previousAnswer;
    state.turnId = kept.turnId;
    state.turnMark = kept.turnMark;
    renderPreviousAnswer();
  } else {
    state.buffer = SEEN.not_for_me;
  }
  return true;
}

function liveTurnFinished(spokenAnswer) {
  clearTimeout(live.slowTimer);
  const wasLive = state.liveTurn;
  state.liveTurn = false;
  live.keep = null;
  live.thinking = false;
  if (wasLive && spokenAnswer && liveOnHere()) {
    live.chips = liveChips(state.buffer, { cardShown: liveCardHolds() });
  }
  paintLive();
  const next = live.pending;
  live.pending = null;
  if (next && liveOnHere()) {
    setTimeout(() => liveSend(next.text, next.privacy), 0);
  }
}

function liveSend(text, privacy) {
  state.voiceTurn = true;
  state.voicePrivacy = privacy;
  live.lastQuestion = text;
  send(text, "voice", { live: true });
}

/** One sentence the PC heard from the owner in Live. */
function liveAsk(text, heard) {
  if (!text) return;
  live.thinking = true;
  live.short = false;
  live.flashUntil = Date.now() + LIVE_FLASH_MS;
  // "I heard you", under its own switch - as on the phone (the audit's
  // both-apps 2).
  playHeardSound();
  const privacy = privacyFromHeard(heard);
  if (state.inFlight) {
    // Still answering the last one. Before any sound, a second thought
    // joins it; after, it waits for this answer to wind up.
    const folded = state.liveTurn && !live.sounded;
    live.pending = {
      text: folded ? liveFold(live.lastQuestion, text, false) : text,
      privacy,
    };
    if (folded) abortStream();
    return;
  }
  liveSend(text, privacy);
}

/** Every reply the PC sent for a Live sentence (and "let's talk" or the
 *  move offer for a "hey Jarvis" one). True when it was Live's. */
function liveHeard(heard) {
  const isLive = heard.source === "live" || Boolean(heard.live) || Boolean(heard.liveElsewhere);
  if (!isLive) return false;
  const reply = liveReply(heard);
  switch (reply.action) {
    case "end":
      live.chips = [];
      if (reply.say) sayAside(reply.say);
      break;
    case "refused": {
      // "Hey Jarvis, let's talk" the PC would not start: said aloud, in the
      // PC's fixed words, and shown (the review's #7).
      const why = String(heard.reason || "Jarvis Live could not start.");
      liveRefused(why);
      sayAside(why);
      break;
    }
    case "start":
      live.resuming = false;
      if (reply.say) sayAside(reply.say);
      break;
    case "move":
      live.elsewhere = String(heard.liveElsewhere || "");
      clearTimeout(live.elsewhereTimer);
      live.elsewhereTimer = setTimeout(() => {
        live.elsewhere = "";
        paintLive();
      }, 30000);
      // Said, in fixed words, as the phone does - the offer was easy to miss.
      sayAside(`${SEEN.elsewhere.replace("{device}", deviceWords(live.elsewhere))}.`);
      break;
    case "stop":
      if (loadInterrupt() !== "off") {
        noteCutOff();
        stopSpeaking();
      }
      break;
    case "answer":
      liveAsk(String(heard.text || "").trim(), heard);
      break;
    case "short":
      live.thinking = false;
      live.short = true;
      live.flashUntil = Date.now() + LIVE_FLASH_MS;
      if (reply.say) sayAside(reply.say);
      break;
    case "trouble":
      // The owner's voice, but no words could be made of it: Live carries
      // on (it used to be taken as the end - the review's bug 2).
      live.thinking = false;
      live.troubleUntil = Date.now() + LIVE_FLASH_MS;
      break;
    default:
      if (reply.say) sayAside(reply.say);
  }
  paintLive();
  return true;
}

/** A card is on screen (or gone): speech pauses and the microphone closes
 *  until it is decided - by tapping only. Only a card raised in THIS Live
 *  session holds it (cardInSession). */
function liveCardShown(on) {
  if (!liveOnHere()) {
    live.heldForCard = false;
    return;
  }
  if (on === live.heldForCard) return;
  live.heldForCard = on;
  invoke("live_hold", { what: "card", on });
  if (on) {
    live.chips = [];
    speechPaused = true;
    clearTimeout(pauseTimer);
    if (currentAudio) currentAudio.pause();
  } else {
    resumeSpeaking();
  }
  paintLive();
}

/** "By button only" / "Don't interrupt": the microphone is closed while
 *  Jarvis talks. */
function syncLiveAnswer() {
  const hold = liveOnHere() && loadInterrupt() !== "voice" && speaking;
  if (hold !== live.heldForAnswer) {
    live.heldForAnswer = hold;
    invoke("live_hold", { what: "answer", on: hold });
  }
  // voice.rs drops a Live sentence that began over an answer unless the
  // PC said it was the owner (the review's #9): it is told when one plays.
  const playing = liveOnHere() && jarvisTalking();
  if (playing !== live.toldPlaying) {
    live.toldPlaying = playing;
    invoke("live_hold", { what: "speaking", on: playing });
  }
  if (dom.liveStopTalking) {
    dom.liveStopTalking.hidden = !(liveOnHere() && jarvisTalking() && loadInterrupt() !== "off");
  }
}

/** Another voice while Jarvis talks, in Live: lower Jarvis's voice and ask
 *  the PC whose it was. */
function liveBargeOnset(id) {
  if (loadInterrupt() !== "voice" || !jarvisTalking() || speechMuted) return;
  if (!voiceFlow.bargeIn || !toolWatch.snapshot().live) return;
  if (liveBarge("onset") === "duck" && currentAudio) currentAudio.volume = DUCK_VOLUME;
  clearTimeout(live.duckTimer);
  live.duckTimer = setTimeout(() => {
    if (currentAudio) currentAudio.volume = 1;
  }, WAIT_MAX_MS);
  invoke("judge_barge_in", { id });
}

/** The PC's answer: the owner - stop; anyone else - back to full voice. */
function liveBargeVerdict(verdict) {
  clearTimeout(live.duckTimer);
  if (liveBarge(verdict.stop === true ? "owner" : "other") === "stop") {
    noteCutOff();
    stopSpeaking();
  } else if (currentAudio) {
    currentAudio.volume = 1;
  }
}

/** The short sound when Live ends here (the "I heard you" notes the other
 *  way round, live-rules.js END_TONE). */
let liveToneContext = null;
function playLiveEndTone() {
  try {
    const Ctx = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (!Ctx) return;
    liveToneContext = liveToneContext || new Ctx();
    const samples = heardSoundSamples({
      ...HEARD_SOUND,
      tones: END_TONE.map(([hz, ms]) => ({ hz, ms })),
    });
    const buffer = liveToneContext.createBuffer(1, samples.length, HEARD_SOUND.rate);
    const channel = buffer.getChannelData(0);
    samples.forEach((v, i) => {
      channel[i] = v / 32768;
    });
    const source = liveToneContext.createBufferSource();
    source.buffer = buffer;
    source.connect(liveToneContext.destination);
    if (liveToneContext.state === "suspended") liveToneContext.resume().catch(() => {});
    source.start();
  } catch (error) {
    console.info("[quickbar] no Live end tone:", error);
  }
}

/** A new Live session here (not "Resume Live"): one Live session is one
 *  chat (docs/LIVE-DESIGN.md section 3.7), so the next question starts a
 *  new conversation. What is on screen stays until then. */
function liveNewSession(cid = newConversationId()) {
  state.conversation = [];
  state.thread = [];
  state.conversationId = cid;
  state.lastTurnAt = 0;
  state.previousAnswer = null;
  renderPreviousAnswer();
  syncNewConversation();
  live.explaining = !liveExplained();
}

/**
 * Live came on here: which chat it is (the chat audit, 2026-09-28). The
 * session carries its chat's id (JARVIS-API.md section 63.1):
 * - the fresh id this bar started it with - a new chat;
 * - the other device's chat, after "Move it here" - carried on here, the
 *   same conversation (it used to start a new one on the PC, and the
 *   phone carried on the WRONG chat);
 * - none (started by voice or from the tray) - a new chat, named to the PC.
 */
function liveAdoptChat(s) {
  const cid = typeof s.conversation_id === "string" ? s.conversation_id : "";
  const mine = live.pendingCid;
  const moved = live.moveCid;
  live.pendingCid = "";
  live.moveCid = "";
  if (live.resuming) return;
  if (cid && cid === mine) {
    liveNewSession(cid);
  } else if (cid && (cid === moved || cid !== state.conversationId)) {
    continueChat(cid, { moved: true });
  } else if (!cid) {
    liveNewSession();
    invoke("live_act", { action: "active", conversationId: state.conversationId });
  }
}

function liveTake(p) {
  const before = live.status;
  live.status = p.status || null;
  live.stale = p.stale === true;
  live.lockUnknown = p.lockUnknown === true;
  live.callUnknown = p.callUnknown === true;
  // live.rs WAIT_TALK_TYPE: talk-to-type holds the microphone for now.
  live.micWait = typeof p.micWait === "string" ? p.micWait : "";
  const s = live.status || {};
  if (s.state === "ended") {
    if (!(before && before.state === "ended" && before.session === s.session)) {
      live.endedBase = { at: Date.now(), ago: Number.isInteger(s.ended_ago_s) ? s.ended_ago_s : 0 };
      liveScheduleEndedRepaint();
    }
  } else {
    live.endedBase = null;
  }
  const wasHere = onHere(before, LIVE_ME);
  if (liveOnHere()) {
    live.elsewhere = "";
    live.notice = "";
    if (!wasHere || (before && before.session !== s.session)) {
      liveAdoptChat(s);
      live.resuming = false;
    }
    // Live began (or carried on) with a card of this session on screen: held too.
    if (liveCardHolds() && !live.heldForCard) liveCardShown(true);
  } else {
    live.chips = [];
    live.heldForCard = false;
    live.heldForAnswer = false;
    live.toldPlaying = false;
    live.explaining = false;
    if (wasHere) playLiveEndTone();
  }
  return before;
}

listen("live-status", (event) => {
  const p = (event && event.payload) || {};
  const before = liveTake(p);
  const line = (typeof p.say === "string" && p.say) || liveTransition(before, live.status, LIVE_ME);
  if (line) sayAside(line);
  paintLive();
});

/* Jarvis Live on the PHONE shows here too ("Jarvis Live is on your phone",
   Move it here - the review: it was invisible on the PC). The PC's `live`
   event carries the status; a session on THIS PC comes from live.rs's own
   watcher instead (live-status above), so it is not taken twice. */
onEvent((frame) => {
  if (!frame || frame.kind !== "live" || !frame.data || typeof frame.data !== "object") return;
  const s = frame.data;
  if (liveOnHere() || s.device === LIVE_ME || s.ended_device === LIVE_ME) return;
  liveTake({ status: s, stale: live.stale, lockUnknown: false, callUnknown: false });
  paintLive();
});

listen("live-heard", (event) => {
  const p = (event && event.payload) || {};
  live.thinking = p.heard === true;
  live.short = p.short === true;
  live.flashUntil = Date.now() + LIVE_FLASH_MS;
  paintLive();
  setTimeout(paintLive, LIVE_FLASH_MS + 50);
});

/* ==========================================================================
   Look at this / Watch with me (look-rules.js; look.rs; docs/SCREEN-DESIGN.md)
   --------------------------------------------------------------------------
   "Look at this" is a KEY (Rust looks first, THEN this bar comes up); Watch
   with me is the button beside Live. The PC holds the session and any look:
   this window only ever hears fixed words and minutes (`screen-status`) and
   ONE note about a look (`screen-look`: "Looked at: Chrome window - words
   only", or why there was no look). No picture and no word from the screen
   ever comes here. While a look is held, each question carries the mark
   `screen: "look"`, and the PC adds the words to THAT question as outside
   text. The strip is thrown away when the bar closes (Rust says so).
   ========================================================================== */

const screen = {
  status: null,
  at: 0,
  stale: false,
  /** The last look's note ("Looked at: ..."), or "". */
  note: "",
  /** The note of the last MARKED question, kept beside its answer. */
  answerNote: "",
  /** A refusal (the start was held, the look could not be taken). */
  notice: "",
  noticeTimer: null,
  paintTimer: null,
  busy: false,
};

/** The message, marked to read the look the PC holds (look-rules.js). */
function screenTag(message) {
  const marked = markMessage(message, screen.status);
  screen.answerNote = marked !== message ? screen.note || LOOK_SEEN.held_short : "";
  return marked;
}

/** The status with its minutes counted on from when it arrived. */
function screenNow() {
  const s = screen.status;
  if (!s || typeof s !== "object") return null;
  if (s.on === true && Number.isFinite(s.left_s)) {
    const gone = Math.floor((Date.now() - screen.at) / 1000);
    return { ...s, left_s: Math.max(0, s.left_s - gone) };
  }
  return s;
}

function paintWatch() {
  if (!dom.watchStrip) return;
  const now = screenNow();
  const on = watchOn(now);
  dom.watchToggle.setAttribute("aria-pressed", String(on));
  dom.watchToggle.title = on
    ? "Watch with me is on - click to stop"
    : "Watch with me: Jarvis looks at your screen when you ask, and pauses on passwords. A sign stays on screen.";
  const endedAgo = now && now.state === "ended" ? Math.floor((Date.now() - screen.at) / 1000) : null;
  const sign = watchSign(now, { stale: screen.stale, endedAgo });
  const held = lookHeld(now);
  const note = screen.notice || (held ? screen.note : screen.answerNote) || "";
  const show = sign.show || stripShown(now, note);
  dom.watchStrip.hidden = !show;
  clearTimeout(screen.paintTimer);
  if (!show) return;
  dom.watchStrip.dataset.tone = sign.show ? sign.tone : "off";
  dom.watchTitle.textContent = sign.show ? sign.title : "Your screen";
  let detail = sign.detail;
  if (held && !detail) detail = LOOK_SEEN.held;
  if (detail !== dom.watchDetail.textContent && detail) announce(detail);
  dom.watchDetail.textContent = detail;
  let line = note;
  if (!line && on && !held) line = LOOK_SEEN.watching_note;
  dom.watchNote.hidden = !line;
  dom.watchNote.textContent = line;
  dom.watchNote.dataset.tone = screen.notice ? "warn" : "ok";
  dom.watchStop.hidden = !sign.stop;
  dom.watchStop.textContent = sign.stop || "Stop watching";
  dom.watchMore.hidden = !sign.more;
  dom.watchDrop.hidden = !held;
  dom.watchDrop.textContent = LOOK_DROP;
  // While it is on the minutes change; after it ended the sign goes.
  if (on || sign.show) screen.paintTimer = setTimeout(paintWatch, 10000);
}

function screenNotice(text, ms = 20000) {
  screen.notice = String(text || "").trim();
  clearTimeout(screen.noticeTimer);
  if (screen.notice) {
    announce(screen.notice, "assertive");
    screen.noticeTimer = setTimeout(() => {
      screen.notice = "";
      paintWatch();
    }, ms);
  }
  paintWatch();
}

function screenTake(payload) {
  if (!payload || typeof payload !== "object") return;
  screen.status = payload.status && typeof payload.status === "object" ? payload.status : null;
  screen.at = Date.now();
  screen.stale = payload.stale === true;
  // A look that is no longer held (used up, two minutes old, the bar
  // closed) has no note left to show, unless a question already carries it.
  if (!lookHeld(screen.status)) screen.note = "";
  paintWatch();
}

listen("screen-status", (event) => screenTake(event && event.payload));

listen("screen-look", (event) => {
  const p = (event && event.payload) || {};
  if (p.closed === true) {
    // The bar closed: nothing about the last look stays on it.
    screen.note = "";
    screen.answerNote = "";
    screen.notice = "";
    paintWatch();
    return;
  }
  const line = lookLine(p);
  if (line.tone === "ok") {
    screen.notice = "";
    screen.note = line.text;
    announce(line.text);
  } else {
    screen.note = "";
    screenNotice(line.text);
    return;
  }
  paintWatch();
});

async function toggleWatch() {
  // One click at a time.
  if (screen.busy) return;
  screen.busy = true;
  dom.watchToggle.setAttribute("aria-busy", "true");
  try {
    if (watchOn(screen.status)) {
      await invokeStrict("screen_watch", { action: "stop" });
    } else {
      screen.notice = "";
      await invokeStrict("screen_watch", { action: "start", by: "button" });
    }
  } catch (error) {
    screenNotice(refusedWords(error));
  } finally {
    screen.busy = false;
    dom.watchToggle.removeAttribute("aria-busy");
  }
}

async function watchDo(action, args = {}) {
  try {
    await invokeStrict("screen_watch", { action, ...args });
  } catch (error) {
    screenNotice(refusedWords(error));
  }
}

if (dom.watchToggle) {
  dom.watchToggle.addEventListener("click", toggleWatch);
  dom.watchStop.addEventListener("click", () => watchDo("stop"));
  dom.watchMore.addEventListener("click", () => watchDo("extend", { minutes: 20 }));
  dom.watchDrop.addEventListener("click", () => {
    screen.note = "";
    screen.answerNote = "";
    watchDo("drop");
  });
  invoke("screen_status").then(screenTake);
}

/** "Resume Live" and "Move it here": the same chat carries on. */
function liveResume() {
  live.resuming = true;
  live.elsewhere = "";
  liveDo("live_start", { by: "button", conversationId: state.conversationId });
}

if (dom.liveToggle) {
  dom.liveToggle.addEventListener("click", toggleLive);
  dom.liveEnd.addEventListener("click", () => liveDo("live_stop"));
  dom.liveMute.addEventListener("click", () =>
    liveDo("live_mute", { muted: !(live.status && live.status.muted) })
  );
  dom.liveCarryOn.addEventListener("click", () => liveDo("live_act", { action: "resume" }));
  dom.liveResume.addEventListener("click", liveResume);
  dom.liveMore.addEventListener("click", () => liveDo("live_act", { action: "extend", minutes: 20 }));
  dom.liveShowCard.addEventListener("click", () => {
    if (!dom.approval.hidden) {
      dom.approval.scrollIntoView({ block: "nearest" });
      dom.approval.focus({ preventScroll: true });
    }
  });
  dom.liveMove.addEventListener("click", () => {
    live.elsewhere = "";
    // "Move it here": the same chat carries on (the chat audit, 2026-09-28)
    // - the other device's conversation id goes with Start, and this bar
    // takes that chat over when Live comes on here (liveAdoptChat).
    const theirs = live.status && typeof live.status.conversation_id === "string"
      ? live.status.conversation_id : "";
    live.moveCid = theirs;
    if (!theirs) live.pendingCid = newConversationId();
    liveDo("live_start", { by: "button", conversationId: theirs || live.pendingCid });
  });
  dom.liveFix.addEventListener("click", () => {
    try {
      localStorage.setItem(SETTINGS_PLACE_KEY, JSON.stringify({ place: LIVE_TRAIN_PLACE, at: Date.now() }));
    } catch {
      /* Settings opens at the top; the words say where */
    }
    invoke("open_fix_place", { place: "settings" });
  });
  dom.liveStopTalking.addEventListener("click", () => {
    noteCutOff();
    stopSpeaking();
  });
  invoke("live_status").then((p) => {
    if (!p || typeof p !== "object") return;
    // The first read counts too: an ended session read when the bar opens
    // offers Resume Live from the PC's own count (the review's #5).
    live.resuming = true;
    liveTake(p);
    live.resuming = false;
    paintLive();
  });
}

/** One fixed line, said on its own - not part of any answer, so none of an
 *  answer's queue or privacy rules apply to it, and it never stops one. */
async function sayAside(line) {
  // Jarvis Live: the microphone is held closed while a fixed line plays, so
  // Jarvis's own voice is not sent as a sentence (live.rs `live_hold`).
  const holdMic = liveOnHere();
  try {
    if (holdMic) await invoke("live_hold", { what: "answer", on: true });
    const uri = await invokeStrict("speak_reply", { text: line });
    if (uri) {
      const audio = new Audio(uri);
      // Lip-sync, as for an answer's sentence; `ended` stops following it.
      const unfollow = followForFaces(audio, uri);
      await new Promise((resolve) => {
        const gaveUp = () => {
          unfollow();
          resolve();
        };
        audio.onended = resolve;
        audio.onerror = gaveUp;
        audio.play().catch(gaveUp);
        // Never held for long, whatever the audio does.
        setTimeout(resolve, 15000);
      });
    }
  } catch (error) {
    console.info("[quickbar] could not say it aloud:", error);
  } finally {
    if (holdMic) liveReleaseHold();
  }
}
listen("jarvis-resync", () => {
  toolWatch.resync();
  recheckSpeech();
});
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
  TAURI.event.listen("show-approval", (event) => {
    const queue = currentQueue();
    // "Open the card" names the card its window showed (card-link.js); the
    // tray and the widget name none. A card no longer waiting falls back to
    // the first one that is.
    const wanted = event && typeof event.payload === "string" ? event.payload : null;
    const next = (wanted && queue.items.find((item) => item.id === wanted)) || queue.items[0];
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
