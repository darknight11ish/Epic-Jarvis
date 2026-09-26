/**
 * The Brain — everything Jarvis knows and everything it can do.
 *
 * Six views over one Rust command. `brain_read` fans out across a fixed
 * allowlist of read-only endpoints in parallel and returns them keyed by
 * section; this window renders them. Nothing here opens a stream, polls an
 * endpoint or holds its own idea of the link state — it subscribes to the one
 * connection Rust owns, like every other surface.
 *
 * ## The rule about server text
 *
 * Almost everything rendered here was written by somebody else: repository
 * descriptions from GitHub, skill names from disk, job labels, model
 * identifiers, ledger hashes. All of it reaches the DOM through `textContent`
 * or through the `el()` helper, which uses `textContent`. There is no
 * `innerHTML` in this file that touches server data. The one place the
 * window renders model text as Markdown is a deep question's answer, in
 * deep.js, through the quickbar's own renderer (markdown.js), which escapes
 * everything before it adds any markup - see that module's note.
 *
 * @module brain
 */

import {
  announce,
  APPROVE_WHERE,
  currentLink,
  followTheme,
  followZoom,
  linkWords,
  normaliseTheme,
  reconnect,
  THEMES,
  surfaceState,
  currentQueue,
  onEvent,
  onLink,
  onQueue,
  start as startLink,
} from "./jarvis-link.js";
import { addToWiki, readWiki, renderWiki } from "./wiki.js";
import { mountCardLink } from "./card-link.js";
import { stepText } from "./step-words.js";
import {
  actionsOf as focusActionsOf,
  BAD_MINUTES as FOCUS_BAD_MINUTES,
  clock as focusClock,
  driftWords,
  FOCUS_MISSING,
  INTENT_HIDDEN as FOCUS_INTENT_HIDDEN,
  LABELS as FOCUS_LABELS,
  LAST_TITLE as FOCUS_LAST_TITLE,
  leftNow as focusLeftNow,
  minutesOf as focusMinutesOf,
  readFocus,
  toneOf as focusToneOf,
} from "./focus.js";
import {
  actionsOf,
  addPlaceholder,
  anyTicking,
  CLEAR_LIST_LABEL,
  clearListQuestion,
  EMPTY_JOBS,
  EMPTY_TODO,
  labelOf,
  metaOf,
  namedLists,
  readSchedule,
  SCHEDULE_MISSING,
  SNOOZE_SECONDS,
  STANDBY_BAD_TIMES,
  standbyOf,
  standbyTimes,
  tagOf,
  titleOf,
  todoItems,
  WENT_OFF_ACTIONS,
  wentOffMeta,
} from "./coming-up.js";
import {
  BUILDING as BRIEFING_BUILDING,
  EMPTY as BRIEFING_EMPTY,
  KEPT as BRIEFING_KEPT,
  lateLine,
  NOW_BUSY as BRIEFING_NOW_BUSY,
  NOW_LABEL as BRIEFING_NOW_LABEL,
  outsideLine as briefingOutsideLine,
  MISSED_BUSY,
  MISSED_DETAIL,
  MISSED_LABEL,
  MISSED_MISSING,
  readBriefing,
  readMissed,
} from "./briefing.js";
import {
  addPage,
  deleteQuestion,
  DENIED_REPLY,
  deviceTag,
  keepConfirm,
  keepLabel,
  keepNeedsConfirm,
  keepReply,
  KEEP_CHOICES,
  notRecordingLine,
  OFF_REPLY,
  olderThan,
  ON_REPLY,
  PAGE as HISTORY_PAGE,
  readConversation,
  readHistory,
  refreshRows,
  renderTranscript,
  rowMeta,
  SWITCH_DETAIL,
  SWITCH_LABEL,
  TAINT_TITLE,
  whenWords,
} from "./history-view.js";
import {
  addPage as addAutoPage,
  AUTO_MISSING,
  AUTO_OFF,
  CANCEL_LABEL,
  CANCEL_TITLE,
  EMPTY as AUTO_EMPTY,
  ERASE_LABEL,
  ERASE_TITLE,
  ERASED,
  erasedAt,
  erasedLine,
  eraseQuestion,
  factMeta,
  FORGOTTEN,
  forgetQuestion,
  lastLineNow,
  LEARNING_OFF_NOTE,
  olderThan as olderAuto,
  PAGE as AUTO_PAGE,
  readAuto,
  refreshRows as refreshAutoRows,
  rememberedLine,
  savedIds,
  SENSITIVE_NEEDS_AUTO,
  stillOffLine,
  SWITCHES as AUTO_SWITCHES,
  VOICE_MARK,
  VOICE_TITLE,
} from "./auto-learn.js";
import {
  cardLines,
  plainDateOf,
  statusRows,
  WORDS as MEMORY_WORDS,
} from "./memory-words.js";
import {
  isPinned,
  PIN_LABEL,
  PIN_TITLE,
  PINNED,
  PROFILE_DETAIL,
  PROFILE_EMPTY,
  PROFILE_MISSING,
  readProfile,
  UNPIN_LABEL,
  UNPIN_TITLE,
  UNPINNED,
  usedLine,
} from "./memory-profile.js";
import {
  missingLine,
  NOT_CURRENT_MARK,
  PINNED_MARK,
  readUsed,
  REMEMBERED_LINE_TITLE,
  REMEMBERED_TITLE,
  rowActions,
  SHOW_ALL,
} from "./memory-used.js";
import {
  ABOUT_EMPTY,
  ABOUT_MAX,
  aboutTitle,
  alsoLine,
  calledLine,
  entitiesFor,
  entityById,
  LINKED_LABEL,
  MERGE_JOINED,
  MERGE_KEPT,
  MERGE_NO,
  MERGE_NO_TITLE,
  MERGE_NOTE,
  MERGE_SOURCE,
  MERGE_TAG,
  MERGE_YES,
  MERGE_YES_TITLE,
  moreLine,
  readEntities,
} from "./memory-entities.js";
import {
  askDeep,
  leadLine as deepLead,
  POLL_MS as DEEP_POLL_MS,
  readDeep,
  renderJobs as renderDeepJobs,
  RUNNING as DEEP_RUNNING,
  runningCount,
} from "./deep.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/**
 * Every view, and what the topbar says about it.
 *
 * Order here is the rail's order (see `TAB_ORDER` below): the three
 * everyday views first, then the four moved behind "Advanced" — galaxy,
 * live, trust, watch, unchanged and still fully wired, just not on the
 * rail by default.
 */
const VIEWS = {
  memory: { title: "Memory", sub: "what Jarvis has learned about you" },
  history: { title: "History", sub: "your conversations, kept on this PC" },
  faculties: { title: "Model", sub: "models, compute, skills, memory" },
  work: { title: "Work", sub: "coming up, jobs in flight and what can be put back" },
  galaxy: { title: "Galaxy", sub: "what Jarvis knows" },
  live: { title: "Live", sub: "what Jarvis is doing" },
  trust: { title: "Trust", sub: "the audit chain and what outside text tried" },
  watch: { title: "Watch", sub: "the GitHub watchlist" },
};

/** Views tucked behind the "Advanced" disclosure until it is opened. */
const ADVANCED_VIEWS = ["galaxy", "live", "trust", "watch"];

/** Which sections each view needs, so a switch reads only what it will show. */
const VIEW_SECTIONS = {
  galaxy: ["graph"],
  live: ["attention", "status"],
  faculties: ["models", "compute", "skills", "memory", "memory_pending"],
  // memory_entities: the names under each fact, for "About <name>"
  // (memory-entities.js). Hidden with the other memory lists.
  memory: ["memory_facts", "memory_pending", "memory_entities"],
  // Read through its own commands (brain/history.rs), not brain_read.
  history: [],
  work: ["jobs", "undo"],
  trust: ["content_risk", "ledger"],
  watch: ["watch", "watch_report"],
};

// The theme ids come from jarvis-link.js, the one list every window shares.

const $ = (id) => document.getElementById(id);

const dom = {
  root: document.documentElement,
  title: $("view-title"),
  sub: $("view-sub"),
  banner: $("banner"),
  linkPill: $("link-pill"),
  linkText: $("link-text"),
  refresh: $("refresh"),
  reconnectLink: $("reconnect-link"),
  freshness: $("freshness"),
  rushStrip: $("rush-strip"),
  toast: $("toast"),
  themePicker: $("theme-picker"),
  rail: $("rail-nav"),
  advancedToggle: $("rail-advanced-toggle"),
  countAdvanced: $("count-advanced"),

  canvas: $("graph-canvas"),
  graphEmpty: $("graph-empty"),
  graphEmptyText: $("graph-empty-text"),
  graphStat: $("graph-stat"),
  graphSearch: $("graph-search"),
  graphRefit: $("graph-refit"),
  legend: $("legend"),
  inspector: $("inspector"),
  inspectorClose: $("inspector-close"),
  nodeKind: $("node-kind"),
  nodeLabel: $("node-label"),
  nodeFacts: $("node-facts"),
  nodeLinks: $("node-links"),

  nowFace: $("now-face"),
  nowActivity: $("now-activity"),
  nowPower: $("now-power"),
  nowKv: $("now-kv"),
  budget: $("budget"),
  budgetNote: $("budget-note"),
  trace: $("trace"),
  traceClear: $("trace-clear"),

  models: $("models"),
  compute: $("compute"),
  skills: $("skills"),
  memory: $("memory"),
  memoryLearning: $("memory-learning"),
  memoryProposals: $("memory-proposals"),
  memoryFacts: $("memory-facts"),
  memoryFactsFilter: $("memory-facts-filter"),
  memoryAuto: $("memory-auto"),
  memoryAutoList: $("memory-auto-list"),
  memorySavedLine: $("memory-saved-line"),
  memoryProfile: $("memory-profile"),
  memoryAboutCard: $("memory-about-card"),
  memoryAboutTitle: $("memory-about-title"),
  memoryAbout: $("memory-about"),
  jobs: $("jobs"),
  undo: $("undo"),
  focus: $("focus"),
  focusForm: $("focus-form"),
  focusMinutes: $("focus-minutes"),
  focusOn: $("focus-on"),
  focusStart: $("focus-start"),
  focusReport: $("focus-report"),
  comingUp: $("coming-up"),
  todoList: $("todo-list"),
  todoForm: $("todo-form"),
  todoText: $("todo-text"),
  todoAdd: $("todo-add"),
  wentOffPart: $("went-off-part"),
  wentOff: $("went-off"),
  namedLists: $("named-lists"),
  listsNote: $("lists-note"),
  standbyForm: $("standby-form"),
  standbyStart: $("standby-start"),
  standbyEnd: $("standby-end"),
  standbyAdd: $("standby-add"),
  standbyIsSet: $("standby-is-set"),
  briefing: $("briefing"),
  briefingNow: $("briefing-now"),
  briefingMissed: $("briefing-missed"),
  contentRisk: $("content-risk"),
  ledger: $("ledger"),
  watch: $("watch"),
  watchReport: $("watch-report"),

  watchForm: $("watch-form"),
  watchAddOpen: $("watch-add-open"),
  watchCancel: $("watch-cancel"),
  watchSeen: $("watch-seen"),
  countLive: $("count-live"),
  countWork: $("count-work"),
  countTrust: $("count-trust"),
  countWatch: $("count-watch"),
  countMemory: $("count-memory"),
};

const state = {
  view: "memory",
  /** Section name → last body read. */
  data: {},
  /** True while a read is in flight, so a repaint cannot stack them. */
  loading: false,
  /** Section name → `{ why, at }` for a read that failed while an older good
   *  read is still being shown. The phone keeps the last read that worked,
   *  and so does this: a failed re-read used to overwrite it. */
  failed: {},
  /** Section name → when it last read successfully (ms). */
  readAt: {},
  /** A model switch or install sent and waiting on its approval card. */
  modelAsk: null,
  /** What became of the last model request whose card left the queue
   *  without a `model` event: shown in its place until the next ask. */
  modelAskEnded: null,
  graph: null,
  trace: [],
};

/** Whether the four views behind "Advanced" are on the rail right now. */
let advancedOpen = false;

/* ==========================================================================
   Plumbing
   ========================================================================== */

async function invoke(command, args = {}) {
  if (!IS_TAURI) {
    console.info(`[brain] invoke("${command}") skipped — no desktop backend`);
    return null;
  }
  return TAURI.core.invoke(command, args);
}

let toastTimer = null;
function toast(message, tone = "") {
  announce(String(message), tone === "bad" ? "assertive" : "polite");
  dom.toast.textContent = String(message);
  dom.toast.dataset.tone = tone;
  dom.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    dom.toast.hidden = true;
  }, tone === "bad" ? 9000 : 4200);
}

/** Builds an element. Text always goes in as text — see the module note. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function rows(container, items, render, emptyText) {
  container.replaceChildren();
  if (!items || !items.length) {
    // A node (whyNode) goes in as it is: it may carry a Retry button.
    container.append(emptyText instanceof Node ? emptyText : el("p", "empty", emptyText));
    return;
  }
  const list = el("div", "rows");
  for (const item of items) list.append(render(item));
  container.append(list);
}

/** A row: a tag, a title with meta beneath it, and optional actions. */
function row({ tag, state: tagState, title, meta, actions }) {
  const item = el("div", "row-item");
  const t = el("span", "row-tag", tag || "");
  if (tagState) t.dataset.state = tagState;
  item.append(t);

  const main = el("div", "row-main");
  main.append(el("span", "row-title", title));
  for (const line of [].concat(meta || []).filter(Boolean)) {
    main.append(el("span", "row-meta", line));
  }
  item.append(main);

  const box = el("div", "row-actions");
  for (const action of actions || []) box.append(action);
  item.append(box);
  return item;
}

/** Buttons that act on the server, re-synced whenever the link changes. */
const liveButtons = new Set();

const STALE_TITLE = "Waiting for the link to catch up. Nothing can be sent until it does.";

/** Greys a `live` button while the link cannot be confirmed (rule 4). */
function syncLiveButton(b) {
  const blocked = !linkWords(currentLink()).canAct;
  b.disabled = blocked || b.dataset.busy === "true";
  b.title = blocked ? STALE_TITLE : b.dataset.title || "";
}

function syncLiveButtons() {
  for (const b of liveButtons) {
    if (!b.isConnected) liveButtons.delete(b);
    else syncLiveButton(b);
  }
}

/**
 * `live: true` for anything that sends a decision or a change: it is greyed,
 * with the reason as its title, while the link is stale or down - the
 * phone's `canAct`. Before this every Brain button stayed clickable on a stale
 * link and failed afterwards with a toast. Rust refuses the same calls too
 * (brain.rs require_link_live); this only stops the click being offered.
 */
function button(label, onClick, { danger = false, title = "", live = false } = {}) {
  const b = el("button", `btn small${danger ? " danger" : ""}`, label);
  b.type = "button";
  if (title) b.title = title;
  b.dataset.title = title;
  if (live) {
    liveButtons.add(b);
    syncLiveButton(b);
  }
  b.addEventListener("click", async () => {
    b.disabled = true;
    b.dataset.busy = "true";
    try {
      await onClick();
    } finally {
      b.dataset.busy = "false";
      if (live) syncLiveButton(b);
      else b.disabled = false;
    }
  });
  return b;
}

/** Model files are gigabytes; "4863.7 MB" is a number nobody reads as 4.7 GB. */
const bytes = (n) => {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  if (v < 1024 ** 2) return `${(v / 1024).toFixed(1)} kB`;
  if (v < 1024 ** 3) return `${(v / 1024 ** 2).toFixed(1)} MB`;
  return `${(v / 1024 ** 3).toFixed(1)} GB`;
};

function ago(epochSeconds) {
  const t = Number(epochSeconds);
  if (!Number.isFinite(t) || t <= 0) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - t));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/**
 * What is known about one section, in the phone's four states (SectionRead):
 *
 * - `reading`: nothing has come back yet.
 * - `absent`: a 404 or 503, or the backend's own `{available: false}` - this
 *   machine does not have the module. A fact, not a fault, so no Retry.
 * - `failed`: the read failed and there is nothing older to show. Amber, with
 *   a Retry.
 * - `stale`: the read failed, and the last read that worked is still shown.
 * - `data`: the last read worked.
 *
 * All four used to be one faint grey line.
 */
function sectionState(section) {
  const body = state.data[section];
  const failure = state.failed[section];
  if (!body) return failure ? { kind: "failed", why: failure.why } : { kind: "reading" };
  if (body.available === false) {
    return body.read === "failed"
      ? { kind: "failed", why: String(body.error || "no reason given") }
      : { kind: "absent" };
  }
  return failure ? { kind: "stale", why: failure.why, at: failure.at } : { kind: "data" };
}

/** The line a pane shows instead of its content, or null when it has some. */
function unavailable(section) {
  const s = sectionState(section);
  if (s.kind === "reading") return "Reading…";
  if (s.kind === "absent") return "Not on this backend.";
  if (s.kind === "failed") return `Could not read this: ${s.why}`;
  return null;
}

/** Reads one section again. Changes nothing on the server. */
function retryButton(section) {
  const b = el("button", "btn small", "Retry");
  b.type = "button";
  b.addEventListener("click", async () => {
    b.disabled = true;
    await load([section], { quiet: true });
    render(state.view);
  });
  return b;
}

/** `unavailable`, as a node: amber with a Retry for a failure, grey otherwise. */
function whyNode(section, tag = "p") {
  const s = sectionState(section);
  const node = el(tag, "empty", unavailable(section) || "");
  if (s.kind === "failed") {
    node.classList.add("failed");
    node.append(" ", retryButton(section));
  }
  return node;
}

/** Every view also reads the rush latch, so it is never out of sight. */
function sectionsFor(view) {
  const sections = VIEW_SECTIONS[view] || [];
  return sections.includes("content_risk") ? sections : [...sections, "content_risk"];
}

/* ==========================================================================
   Reading
   ========================================================================== */

async function load(sections, { quiet = false } = {}) {
  if (!IS_TAURI) {
    dom.banner.hidden = false;
    dom.banner.textContent =
      "No desktop backend — this is a browser preview, so nothing is being read.";
    return;
  }
  if (state.loading) return;
  state.loading = true;
  dom.refresh.disabled = true;
  try {
    const body = await invoke("brain_read", { sections });
    const now = Date.now();
    for (const [section, value] of Object.entries(body || {})) {
      const failedRead = value && value.available === false && value.read === "failed";
      const had = state.data[section];
      const hadGood = had && had.available !== false;
      if (failedRead && hadGood) {
        // Keep what worked last time on screen, and say it is old. The rush
        // latch above all: a latch seen a minute ago must not vanish because
        // the next check failed.
        state.failed[section] = { why: String(value.error || "no reason given"), at: now };
      } else {
        state.data[section] = value;
        // The overnight-tidy card is handed out once a day, to the first
        // read that asks for it - which may be the Faculties view's, not
        // the Memory tab's. Noted here so it is not lost either way.
        if (section === "memory_pending" && value) noteSleepOffer(value.setup);
        if (failedRead) {
          state.failed[section] = { why: String(value.error || "no reason given"), at: now };
        } else {
          delete state.failed[section];
          state.readAt[section] = now;
        }
      }
    }
    // One banner for the window, for FAILURES only - a module this backend
    // does not have is said in its own pane, in grey, and is not a fault.
    // Each failure gets its own Retry, which only reads again.
    const failed = sections.filter((s) => {
      const k = sectionState(s).kind;
      return k === "failed" || k === "stale";
    });
    dom.banner.hidden = failed.length === 0;
    dom.banner.replaceChildren();
    for (const s of failed) {
      const st = sectionState(s);
      const line = el(
        "span",
        "banner-item",
        st.kind === "stale"
          ? `Could not read ${s.replace(/_/g, " ")}: ${st.why}. What is shown is from the last read that worked.`
          : `Could not read ${s.replace(/_/g, " ")}: ${st.why}.`
      );
      line.append(" ", retryButton(s));
      dom.banner.append(line);
    }
  } catch (error) {
    dom.banner.hidden = false;
    dom.banner.textContent = String((error && error.message) || error);
    if (!quiet) toast(String((error && error.message) || error), "bad");
  } finally {
    state.loading = false;
    dom.refresh.disabled = false;
    paintFreshness();
  }
}

async function showView(name, { reload = true } = {}) {
  if (!VIEWS[name]) return;
  state.view = name;
  dom.root.dataset.view = name;
  dom.title.textContent = VIEWS[name].title;
  dom.sub.textContent = VIEWS[name].sub;

  for (const key of Object.keys(VIEWS)) {
    const tab = $(`tab-${key}`);
    const view = $(`view-${key}`);
    if (tab) {
      tab.setAttribute("aria-selected", String(key === name));
      // Roving tabindex: exactly one tab is in the document's tab order, and
      // it is the selected one. Without this the six buttons are six stops.
      tab.tabIndex = key === name ? 0 : -1;
    }
    if (view) view.hidden = key !== name;
  }

  if (reload) await load(sectionsFor(name));
  render(name);
  if (name === "galaxy") fitCanvas();
}

/** Paints whichever view is showing from `state.data`. */
function render(name) {
  switch (name) {
    case "galaxy":
      renderGraph();
      break;
    case "live":
      renderLive();
      break;
    case "faculties":
      renderModels();
      renderCompute();
      renderSkills();
      renderMemory();
      break;
    case "memory":
      renderLearning();
      renderProfile();
      renderAuto();
      renderProposals();
      renderFacts();
      renderWikiPlate();
      renderDeepPlate();
      break;
    case "history":
      renderHistory();
      break;
    case "work":
      renderFocus();
      renderComingUp();
      renderBriefing();
      renderJobs();
      renderUndo();
      break;
    case "trust":
      renderContentRisk();
      renderLedger();
      break;
    case "watch":
      renderWatch();
      renderWatchReport();
      break;
  }
  renderRushStrip();
  renderCounts();
  paintFreshness();
}

/**
 * The rush latch, at the top of every view. The phone puts it first on Mind
 * and keeps the last latch it saw when a check fails (BrainScreen.kt); this
 * does the same. Nothing here clears a latch - Retry only reads again.
 */
function renderRushStrip() {
  const s = sectionState("content_risk");
  const risk = state.data.content_risk;
  const rush = risk && risk.available !== false ? risk.rush : null;
  dom.rushStrip.replaceChildren();
  dom.rushStrip.dataset.tone = "";
  if (rush) {
    dom.rushStrip.dataset.tone = "bad";
    const line = el(
      "span",
      "",
      "A rush latch is active: outside text tried to hurry a decision. It expires on its own."
    );
    dom.rushStrip.append(line);
    // `phrase` or `quote`: jarvis_content_risk is only on the owner's PC, the
    // phone read `quote` and this read `phrase`, so both apps read both.
    const said = rush.phrase || rush.quote;
    if (said) dom.rushStrip.append(" ", el("span", "rush-quote", `“${said}”`));
    if (s.kind === "stale") {
      const mins = Math.max(0, Math.round((Date.now() - (state.readAt.content_risk || Date.now())) / 60000));
      dom.rushStrip.append(
        " ",
        el("span", "rush-age", `Last seen ${mins} min ago — the newest check failed: ${s.why}.`),
        " ",
        retryButton("content_risk")
      );
    }
    dom.rushStrip.hidden = false;
    return;
  }
  if (s.kind === "failed" || s.kind === "stale") {
    dom.rushStrip.dataset.tone = "warn";
    dom.rushStrip.append(
      el("span", "", `Could not check for a rush latch: ${s.why}.`),
      " ",
      retryButton("content_risk")
    );
    dom.rushStrip.hidden = false;
    return;
  }
  dom.rushStrip.hidden = true;
}

/** "3 min ago" from a millisecond time. */
function agoMs(ms) {
  if (!ms) return "";
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}

/**
 * How old the numbers on screen are - the phone's Freshness line. Reads
 * "Refreshing…" while a read runs, and says everything is last known while
 * the link is stale or down.
 */
function paintFreshness() {
  if (!dom.freshness) return;
  const sections = (VIEW_SECTIONS[state.view] || []).filter((s) => state.readAt[s]);
  const oldest = sections.length ? Math.min(...sections.map((s) => state.readAt[s])) : 0;
  const what = (VIEWS[state.view] && VIEWS[state.view].title.toLowerCase()) || "this";
  const words = linkWords(currentLink());
  dom.freshness.dataset.tone = words.canAct ? "" : "warn";
  if (!words.canAct) {
    dom.freshness.textContent = oldest
      ? `${words.short}. Everything below is last known, read ${agoMs(oldest)}.`
      : `${words.short}. Nothing has been read yet.`;
  } else if (state.loading) {
    dom.freshness.textContent = "Refreshing…";
  } else if (oldest) {
    dom.freshness.textContent = `Link live · ${what} read ${agoMs(oldest)}`;
  } else {
    dom.freshness.textContent = "Link live · reading…";
  }
}
setInterval(paintFreshness, 15000);

function renderCounts() {
  const set = (node, n) => {
    node.hidden = !n;
    node.textContent = String(n || "");
  };
  const jobs = (state.data.jobs && state.data.jobs.jobs) || [];
  set(
    dom.countWork,
    jobs.filter((j) => j.state === "running" || j.state === "queued").length
  );
  // Kept at 1 while the last latch seen is still on screen, even if the
  // newest check failed - a failed read is not an all-clear.
  const risk = state.data.content_risk;
  const trustCount = risk && risk.available !== false && risk.rush ? 1 : 0;
  set(dom.countTrust, trustCount);
  const watch = state.data.watch;
  const watchCount = (watch && watch.waiting_for_you) || 0;
  set(dom.countWatch, watchCount);
  const attention = currentLink().attention;
  const liveCount = attention.known ? attention.pending : 0;
  set(dom.countLive, liveCount);
  // Proposals waiting. This is the badge that matters most, because the
  // extractor fills that queue on its own - nobody asked for the thing that
  // is waiting, so nothing else would tell you it is there.
  const proposed = state.data.memory_pending;
  set(dom.countMemory, waitingCount(proposed));

  // Live, Trust and Watch carry their own badges but sit behind "Advanced"
  // by default, where nobody sees them. Rolled into one count on the
  // toggle itself while it is collapsed, so closing it cannot make
  // something waiting on the user go quiet.
  set(dom.countAdvanced, advancedOpen ? 0 : liveCount + trustCount + watchCount);
}

/* ==========================================================================
   Faculties
   ========================================================================== */

function renderModels() {
  const body = state.data.models || {};
  const why = unavailable("models");
  if (why) return rows(dom.models, [], null, whyNode("models"));

  const current = body.current || body.active || "";
  const previous = body.previous || "";
  const installed = Array.isArray(body.installed) ? body.installed : [];

  const items = installed.length
    ? installed.map((m) => (typeof m === "string" ? { ref: m } : m))
    : current
      ? [{ ref: current }]
      : [];

  rows(
    dom.models,
    items,
    (m) => {
      const ref = String(m.ref || m.name || m.model || "");
      const isCurrent = ref && ref === current;
      const actions = [];
      if (ref && !isCurrent) {
        actions.push(
          button("Use", () => modelAction("switch", ref), {
            title: `Ask to switch to this model. You approve it ${APPROVE_WHERE}.`,
            live: true,
          })
        );
      }
      return row({
        tag: isCurrent ? "active" : "installed",
        state: isCurrent ? "present" : "",
        title: ref || "(unnamed)",
        meta: [
          m.size ? bytes(m.size) : "",
          m.family || "",
          ref && ref === previous ? "the previous model" : "",
        ],
        actions,
      });
    },
    "No models reported."
  );

  // Is the model actually ON the graphics card? Nothing else anywhere says.
  // llama.cpp spills layers to the CPU silently and Ollama still reports the
  // model as loaded and healthy, so the only symptom is that everything got
  // slow - and the owner blames Jarvis rather than the fit.
  //
  // Prepended after `rows()` rather than composed before it, because `rows()`
  // calls replaceChildren on whatever it is given, and the rollback button
  // below appends to the same element.
  const off = body.offload || {};
  if (off.status === "cpu" || off.status === "partial") {
    dom.models.prepend(
      el("p", "banner", String(off.note || "The model is not on the graphics card."))
    );
  }

  // How fast answers have been (speed-record.patch). docs/JARVIS-API.md says
  // show exactly three things: one line for the current model, the backend's
  // own note only when it got slower, and its own old-vs-new sentence beside
  // the rollback button. The phone does the same (ApiModels.kt ModelSpeed);
  // this window ignored the block entirely.
  const speed = modelSpeed(body.speed, current);
  if (speed.line) dom.models.append(el("p", "model-speed", speed.line));
  if (speed.slowdown) dom.models.append(el("p", "banner", speed.slowdown));

  if (previous && previous !== current) {
    if (speed.lastSwitch) dom.models.append(el("p", "model-speed", speed.lastSwitch));
    const back = el("div", "row-actions");
    back.style.paddingTop = "10px";
    back.append(
      button(`Roll back to ${previous}`, () => modelAction("rollback"), {
        title: "Goes back to the previous model at once. Rollback never waits for approval.",
        live: true,
      })
    );
    dom.models.append(back);
  }

  // A switch or install that raised a card and is waiting on it. Said here
  // until the next `model` event or until its card leaves the queue,
  // because the toast is gone in seconds and "switched" was never true - the
  // server only raised an approval card (JARVIS-API: tier `ask`, "success
  // means a card was raised").
  if (state.modelAsk) {
    dom.models.append(
      el(
        "p",
        "banner model-ask",
        state.modelAsk.action === "install"
          ? `Waiting for your approval: installing ${state.modelAsk.ref}. Approve it ${APPROVE_WHERE} — nothing downloads until you do.`
          : `Waiting for your approval: switching to ${state.modelAsk.ref}. Approve it ${APPROVE_WHERE} — nothing changes until you do.`
      )
    );
  } else if (state.modelAskEnded) {
    // Its card left the queue without the model changing: what happened,
    // in the words the phone uses, instead of a line that silently vanished
    // (or, before this, one that kept claiming a card was waiting).
    dom.models.append(el("p", "banner model-ask-ended", state.modelAskEnded));
  }

  dom.models.append(installForm());
}

/**
 * "Install a model": the name typed by hand, the way it would be given to
 * Ollama (`ollama pull <name>`). No catalogue, no list of what could be
 * installed - the same shape the phone has (BrainScreen.kt ModelsPlate) and
 * the owner's 2026-09-20 rule. Posting it only raises an approval card
 * (tier `ask`); nothing downloads until that is approved.
 */
function installForm() {
  const wrap = el("div", "model-install");
  wrap.append(
    el(
      "p",
      "model-speed",
      "Install a model this computer does not have yet. Type its name the way you " +
        "would give it to Ollama, for example llama3.1:8b. This only asks: nothing " +
        `downloads until you approve its card ${APPROVE_WHERE}.`
    )
  );
  const line = el("div", "row-actions");
  const input = el("input", "field");
  input.id = "model-install-ref";
  input.type = "text";
  input.placeholder = "model:tag";
  input.spellcheck = false;
  input.autocomplete = "off";
  input.setAttribute("aria-label", "Model to install");
  const go = button(
    "Install",
    async () => {
      const ref = input.value.trim();
      if (!ref) {
        toast("Type the model's name first, for example llama3.1:8b.", "bad");
        return;
      }
      await modelAction("install", ref);
    },
    { title: `Ask to install this model. You approve it ${APPROVE_WHERE}.`, live: true }
  );
  go.id = "model-install";
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") go.click();
  });
  line.append(input, go);
  wrap.append(line);
  return wrap;
}

/**
 * The `speed` block of /api/models, in the same three pieces the phone shows
 * (ApiModels.kt ModelSpeed.from, ported line for line). Numbers only - the
 * block carries no conversation text.
 */
function modelSpeed(speed, current) {
  const out = { line: "", slowdown: "", lastSwitch: "" };
  if (!speed || typeof speed !== "object" || speed.available === false) return out;
  const num = (v) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null);
  const text = (v) => (typeof v === "string" && v.trim() ? v : "");
  const byModel = speed.by_model && typeof speed.by_model === "object" ? speed.by_model : {};
  const bare = (name) => String(name || "").replace(/:latest$/, "");
  const key = current && (byModel[current] ? current
    : Object.keys(byModel).find((k) => bare(k) === bare(current)));
  const mine = key ? byModel[key] : null;
  if (mine && typeof mine === "object") {
    const parts = [];
    const wps = num(mine.median_words_per_s);
    const firstMs = num(mine.median_first_word_ms);
    if (wps !== null) parts.push(`about ${Math.round(wps)} words a second`);
    if (firstMs !== null) {
      const tenths = Math.round(firstMs / 100);
      parts.push(`first word after ${Math.floor(tenths / 10)}.${tenths % 10} s`);
    }
    if (parts.length) {
      const n = num(mine.answers);
      const over = n ? ` (middle of the last ${Math.round(n)} answers)` : "";
      out.line = `Recent answers: ${parts.join(", ")}${over}.`;
    }
  }
  if (speed.slowdown && speed.slowdown.slower === true) out.slowdown = text(speed.note);
  if (speed.last_switch && typeof speed.last_switch === "object") {
    out.lastSwitch = text(speed.last_switch_note);
  }
  return out;
}

/**
 * How long a model request whose card has left the queue waits for the
 * `model` event an approval brings, before saying it was not approved. An
 * approval on the phone reaches this window only as the card disappearing,
 * a moment before the `model` event - so "gone" alone is not "denied".
 */
const MODEL_ASK_GRACE_MS = 3000;

/** The card raised by the ask, found by difference like the phone's
 *  `noteModelRequest`: the one waiting now that was not waiting before.
 *  Anything other than exactly one new card is `null` - the line then lasts
 *  until the next `model` event, as it always did. */
async function findNewCard(waitingBefore) {
  try {
    const payload = await invoke("get_pending_approvals");
    const items = Array.isArray(payload && payload.items) ? payload.items : [];
    const fresh = items
      .map((row) => (row && row.id !== undefined && row.id !== null ? String(row.id) : ""))
      .filter((id) => id && !waitingBefore.has(id));
    return fresh.length === 1 ? fresh[0] : null;
  } catch (error) {
    return null;
  }
}

/** The model line's words once its card is no longer waiting. */
function modelAskEndedWords(ask, outcome) {
  const what = ask.action === "install" ? `installing ${ask.ref}` : `switching to ${ask.ref}`;
  if (outcome === "denied") {
    return `You denied ${what}. Nothing changed.`;
  }
  return `The request for ${what} is no longer waiting: it was denied or ran out of time. Nothing changed.`;
}

/** Its card left the queue: settle the "Waiting for your approval" line. */
function modelCardGone(ask) {
  if (state.modelAsk !== ask || ask.gone) return;
  ask.gone = true;
  if (ask.decided === "denied") {
    state.modelAsk = null;
    state.modelAskEnded = modelAskEndedWords(ask, "denied");
    if (state.view === "faculties") renderModels();
    return;
  }
  // Approved here, or decided elsewhere, or expired: an approval brings a
  // `model` event, which clears the line on its own. Only when none comes
  // is it said that the request was not approved.
  setTimeout(() => {
    if (state.modelAsk !== ask) return;
    state.modelAsk = null;
    if (ask.decided !== "approved") state.modelAskEnded = modelAskEndedWords(ask, "gone");
    if (state.view === "faculties") renderModels();
  }, MODEL_ASK_GRACE_MS);
}

/** Whether the approval queue holds a card to turn learning on, wherever it
 *  was raised (`learning_enable`, docs/JARVIS-API.md `/api/memory/learning`). */
function learningCardWaiting(queue = currentQueue()) {
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  return items.some((item) => item && item.action === "learning_enable");
}
let learningCardSeen = false;

/** The learning card left the queue: read the switch after the backend has
 *  had a moment to apply an approval. On: the line goes (renderLearning).
 *  Still off: it was denied or ran out of time, and that is said. */
onQueue((queue) => {
  // A learning card raised elsewhere (the phone, or another window) came
  // or went: the waiting line follows it, as History's does.
  const waitingNow = learningCardWaiting(queue);
  if (waitingNow !== learningCardSeen) {
    learningCardSeen = waitingNow;
    if (state.view === "memory") renderLearning();
  }
  const ask = state.learningAsk;
  if (!ask || !ask.cardId || ask.gone) return;
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  if (items.some((item) => item && item.id === ask.cardId)) return;
  ask.gone = true;
  setTimeout(async () => {
    if (state.learningAsk !== ask) return;
    await refreshMemory();
    if (state.learningAsk === ask) {
      state.learningAsk = null;
      const facts = state.data.memory_facts || {};
      if (facts.learning !== true) {
        toast("Background learning stays off: the card was denied or ran out of time.", "bad");
      }
      renderLearning();
    }
  }, MODEL_ASK_GRACE_MS);
});

onQueue((queue) => {
  const ask = state.modelAsk;
  if (!ask || !ask.cardId) return;
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  if (!items.some((item) => item && item.id === ask.cardId)) modelCardGone(ask);
});

// Decided on THIS PC (the Jarvis bar or the widget): Rust says which way
// the moment it is accepted, so "denied" can be said as a fact rather than
// as "denied or ran out of time".
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  TAURI.event.listen("approval-resolved", (event) => {
    const resolved = (event && event.payload) || {};
    const ask = state.modelAsk;
    if (!ask || !ask.cardId || String(resolved.id) !== ask.cardId) return;
    ask.decided = resolved.approved ? "approved" : "denied";
    modelCardGone(ask);
  });
}

async function modelAction(action, reference) {
  const waitingBefore = new Set(
    (currentQueue().items || []).map((item) => item && item.id).filter(Boolean)
  );
  try {
    const out = await invoke("brain_model", { action, reference: reference || null });
    // Switch and install are tier `ask`: success means an approval card was
    // raised, not that anything changed. This used to toast "Model
    // switched." Rollback is tier `auto` and really has happened.
    state.modelAskEnded = null;
    if (action === "rollback") {
      toast("Rolled back.", "ok");
    } else {
      const ask = { action, ref: String(reference || ""), cardId: null };
      state.modelAsk = ask;
      ask.cardId = await findNewCard(waitingBefore);
      toast(
        action === "install"
          ? `Waiting for your approval. Approve it ${APPROVE_WHERE} — nothing downloads until you do.`
          : `Waiting for your approval. Approve it ${APPROVE_WHERE} — nothing changes until you do.`,
        "ok"
      );
    }
    if (out) await load(["models"], { quiet: true });
    render("faculties");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
}

/**
 * The compute plan. Reads the keys `jarvis_compute.Plan.as_dict()` really
 * sends - text_model, text_on, vision_resident, tts_resident, simulated,
 * prefer, devices[], why, total_mb (backend/rebuilt/jarvis_compute.py) -
 * checked by backend/test_connection_contract.py. It used to read only
 * plan/mode/gpu/vram_total_mb/gpu_layers/context/note, none of which that
 * module sends, so this pane always said "No compute plan reported." The old
 * names are still read as a fallback for a differently-built backend, and a
 * body wrapped as {plan: {...}} is unwrapped.
 */
function renderCompute() {
  const raw = state.data.compute || {};
  const body = raw.plan && typeof raw.plan === "object" ? raw.plan : raw;
  const why = unavailable("compute");
  dom.compute.replaceChildren();
  if (why) return dom.compute.append(whyNode("compute"));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", String(v)));
  };
  const gb = (mb) => `${(Number(mb) / 1024).toFixed(1)} GB`;
  const yesNo = (v) => (v === true ? "kept loaded" : v === false ? "loaded when needed" : undefined);
  const where = (on) => {
    if (typeof on !== "string" || !on) return on;
    if (on === "cpu") return "the processor (no graphics card in use)";
    return on.replace(/cuda:(\d+)/g, "graphics card $1").replace(/\+/g, " + ");
  };

  add("Model", body.text_model);
  add("Runs on", where(body.text_on));
  add("Picture model", yesNo(body.vision_resident));
  add("Voice model", yesNo(body.tts_resident));
  add("Aims for", body.prefer === "speed" ? "speed" : body.prefer === "capability"
    ? "capability (spread over every card)" : body.prefer);
  const devices = Array.isArray(body.devices) ? body.devices : [];
  devices.forEach((d) => {
    if (!d || typeof d !== "object") return;
    const free = d.free_mb != null ? `${gb(d.free_mb)} free of ` : "";
    add(`Card ${d.index ?? ""}`.trim(),
      `${d.name || "graphics card"} - ${free}${d.total_mb != null ? gb(d.total_mb) : "?"}`);
  });
  if (!devices.length && Number(body.total_mb) > 0) add("Graphics memory", gb(body.total_mb));
  add("Why", body.why);
  if (body.simulated === true) {
    add("Measured?", "No - no graphics card could be asked, so this is a guess");
  }

  // Older / other backends.
  add("Plan", body.mode || body.strategy);
  add("GPU", body.gpu || body.device);
  add(
    "VRAM",
    body.vram_total_mb
      ? `${((body.vram_used_mb || 0) / 1024).toFixed(1)} / ${(body.vram_total_mb / 1024).toFixed(1)} GB`
      : body.vram
  );
  add("Layers on GPU", body.gpu_layers ?? body.n_gpu_layers);
  add("Context", body.context ?? body.n_ctx);
  add("Note", body.note || body.reason);
  if (!dl.childElementCount) {
    return dom.compute.append(el("p", "empty", "No compute plan reported."));
  }
  dom.compute.append(dl);
}

function renderSkills() {
  const body = state.data.skills || {};
  const why = unavailable("skills");
  if (why) return rows(dom.skills, [], null, whyNode("skills"));
  const list = Array.isArray(body.skills) ? body.skills : Array.isArray(body) ? body : [];

  rows(
    dom.skills,
    list,
    (s) => {
      const name = String(s.name || s.id || "(unnamed)");
      const verdict = String(s.verdict || s.scan || (s.ok === false ? "flagged" : "clean"));
      // skill-notes.patch sends each skill's notes: short lines Jarvis wrote
      // for itself about the skill, which go into the model's context with
      // the skill every time it is used. Anything that steers an answer has
      // to be readable here. Strings, or objects carrying the words in
      // `note`/`text` - whichever the backend's jarvis_skills.py stores.
      const notes = (Array.isArray(s.notes) ? s.notes : [])
        .map((n) => (typeof n === "string" ? n : n && (n.note || n.text)))
        .filter((n) => typeof n === "string" && n.trim())
        .map((n) => `Jarvis's note: “${n.trim()}”`);
      return row({
        tag: verdict,
        state: /clean|ok|pass/i.test(verdict) ? "ok" : "warn",
        title: name,
        meta: [s.description || s.summary || "", s.path || "", ...notes],
        actions: [
          button(
            "Remove",
            async () => {
              // Removal is not undoable from here: there is deliberately no
              // route that installs a skill, because installing runs the
              // scanner and the gate. So it asks, in those words.
              if (
                !confirm(
                  `Remove the skill "${name}"?\n\n` +
                    "This cannot be undone from the desktop. There is no route " +
                    "that installs a skill — installing runs the scanner and " +
                    "the gate, and a client that bypassed both would be the " +
                    "whole attack. Putting it back means putting the file back " +
                    "on the machine."
                )
              ) {
                return;
              }
              try {
                await invoke("brain_remove_skill", { name });
                toast(`Removed ${name}.`, "ok");
                await load(["skills"], { quiet: true });
                render("faculties");
              } catch (error) {
                toast(String((error && error.message) || error), "bad");
              }
            },
            { danger: true }
          ),
        ],
      });
    },
    "No skills installed, or the scanner has quarantined them all."
  );
}

function renderMemory() {
  const body = state.data.memory || {};
  const pending = state.data.memory_pending || {};
  dom.memory.replaceChildren();
  const why = unavailable("memory");
  if (why) return dom.memory.append(whyNode("memory"));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", v));
  };
  // The names jarvis_memory's MemoryStore.status() really sends (checked by
  // backend/test_memory_honesty.py against the real store). This used to
  // read path/model/documents/chunks, which status() never sends, so Store
  // and Embedding never showed - and "Facts" was the total, retired ones
  // included, while the pane said nothing about how many were retired.
  // The rows are memory-words.js's statusRows, the phone's
  // MemoryCounts.fields word for word (one fixture holds both, the memory
  // review's I8): the re-ranker's state and "Said again" are among them.
  // The store's file path is the PC's own, so only this window shows it.
  for (const [k, v] of statusRows(body)) add(k, v);
  if (typeof body.db === "string") add("Store", body.db);
  if (dl.childElementCount) dom.memory.append(dl);

  const proposed = Array.isArray(pending.pending) ? pending.pending : [];
  if (pending.hidden === true && waitingCount(pending)) {
    dom.memory.append(el("h3", "inspector-sub", "Proposed facts"));
    dom.memory.append(el("p", "note",
      `${waitingCount(pending)} waiting, hidden. Press Show on the Memory tab to see them.`));
  }
  if (proposed.length) {
    dom.memory.append(el("h3", "inspector-sub", "Proposed facts"));
    const list = el("div", "rows");
    for (const p of proposed.slice(0, 12)) {
      list.append(
        row({
          tag: "proposed",
          state: "warn",
          // Decided in the Memory tab, one card at a time, where each card
          // shows what it would replace and any warning. This pane says a
          // decision is waiting; it does not offer to make it.
          title: String(p.text || "(no text)"),
          meta: [p.source ? `from ${p.source}` : "", ago(p.created)],
          actions: [],
        })
      );
    }
    dom.memory.append(list);
    dom.memory.append(
      el(
        "p",
        "note",
        // This used to say "decided in the approval gate, one at a time - not
        // from here", which sent the owner somewhere that can never hold the
        // item: memory proposals live in jarvis_extract's table and never
        // enter jarvis_gate's queue. The Memory tab of this window is where
        // they are decided (the HUD only points there); this pane cannot.
        "Decide these in the Memory tab, one at a time. The approval gate " +
          "never sees them — memory proposals live in their own queue."
      )
    );
  }
  if (!dom.memory.childElementCount) {
    dom.memory.append(el("p", "empty", "The memory store reported nothing."));
  }
}

/* ==========================================================================
   Memory — what Jarvis has learned, and every way to change it

   Every write here is one fact and one decision. There is no select-all, no
   "keep the rest", no bulk anything, and that is not an omission: the server
   takes a single integer id per call and forgetting cannot be undone.
   ========================================================================== */

/* The "as of" view.
 *
 * `null` means the normal, live pane. A number is epoch seconds, and while it
 * is set the facts list shows what Jarvis BELIEVED then rather than what is
 * true now, with every editing control gone — the past is not editable, and a
 * Forget button that silently acted on today's store would be a trap.
 *
 * Held here rather than in `state.data` because it is a question this window
 * is asking, not an answer the server sent, and `load()` overwrites the
 * latter on every refresh. */
let memoryAsOf = null;
let memoryAsOfRows = null;

/**
 * The daily overnight-tidy card, cached client-side once seen.
 *
 * The server marks the day's offer as made the moment this window reads
 * `/api/memory/pending?...&sleep_offer=1` (routes.rs) - not when the owner
 * acts on it - so a second read the same day, from ANY write on this pane
 * refreshing the section, comes back with the card already gone. (Only
 * clients that show the card send `sleep_offer=1`; the HUD page does not,
 * so it no longer uses the offer up.) `load()` notes it whichever view read
 * the section. Without this cache the card would flash once
 * and vanish the instant the owner clicked Keep or Discard on an unrelated
 * proposal, before they had a chance to read it.
 *
 * `dismissed` is a second, separate flag rather than just clearing the cache:
 * `state.data` can still be holding the very same non-null offer from the
 * last real fetch (nothing forced a re-read since), so a plain
 * `cachedSleepOffer = null` followed by this function's own re-render would
 * immediately re-adopt the exact offer just turned down. Both flags reset
 * only on a fresh launch of this window - matching what "not now" and "stop
 * asking" actually promise, which is today, not forever.
 */
let cachedSleepOffer = null;
let sleepOfferDismissed = false;

function noteSleepOffer(setup) {
  if (setup && setup.sleep_time_offer && !cachedSleepOffer && !sleepOfferDismissed) {
    cachedSleepOffer = setup.sleep_time_offer;
  }
}

function dismissSleepOffer() {
  cachedSleepOffer = null;
  sleepOfferDismissed = true;
}

/**
 * Asks, optionally, for the date a fact stopped being true — the bi-temporal
 * correction `jarvis_memory.retire()` has supported since `bitemporal.patch`
 * but that neither Reword nor Forget had any way to ask for until now.
 *
 * Returns a unix-seconds timestamp, `null` for "just now" (the field left
 * blank — the common case, and identical to the old behaviour), or
 * `undefined` if the owner cancelled. `undefined` is a distinct answer from
 * `null` on purpose: the caller must abort the whole action on a cancel,
 * not quietly fall back to "just now" for a date the owner never confirmed.
 */
function promptValidTo(message) {
  const raw = window.prompt(message, "");
  if (raw === null) return undefined;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  // A bare YYYY-MM-DD is parsed as local midnight, not Date.parse's UTC
  // midnight - west of Greenwich that shift lands the timestamp on the
  // previous calendar day, the same trap the "as of" picker above avoids.
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  const ts = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3])).getTime()
    : Date.parse(trimmed);
  if (Number.isNaN(ts)) {
    window.alert(`"${trimmed}" is not a date I understand. Try YYYY-MM-DD.`);
    return undefined;
  }
  return ts / 1000;
}

/** Dates before this are refused by "What did you know on…". The server
 * ignores a moment before September 2001 and answers with today's facts
 * instead; no Jarvis existed then anyway. The phone uses the same year. */
const AS_OF_EARLIEST_YEAR = 2002;

/**
 * "What did Jarvis know on YYYY-MM-DD?" as the moment to ask the server
 * about: the LAST second of that day, local time, so "the 1st" includes
 * everything learned on the 1st - or null for a date that cannot be asked
 * (not a real date, before AS_OF_EARLIEST_YEAR, or after today).
 *
 * `new Date("2026-06-01")` would be UTC midnight - the START of the day, in
 * the wrong zone. The phone's `MemoryDates.knownAt` (net/Learning.kt) is the
 * same rule, and backend/test_memory_honesty.py runs this function against
 * the numbers the phone's unit test pins, so the same typed date means the
 * same moment on both apps.
 */
function asOfSeconds(typed, now) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(typed == null ? "" : typed).trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const end = new Date(y, mo - 1, d, 23, 59, 59);
  // new Date() quietly rolls 31 February into March; a date that does not
  // exist is refused instead. (And years 0-99 into the 1900s.)
  if (end.getFullYear() !== y || end.getMonth() !== mo - 1 || end.getDate() !== d) return null;
  if (y < AS_OF_EARLIEST_YEAR) return null;
  const today = now instanceof Date ? now : new Date();
  const lastOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 23, 59, 59);
  if (end.getTime() > lastOfToday.getTime()) return null;
  return Math.floor(end.getTime() / 1000);
}

/** Re-read the pane's own sections and repaint. Used after every write. */
async function refreshMemory() {
  // The "Saved automatically" list is read through its own command
  // (brain/auto_learn.rs), next to the pane's sections: a Forget or a
  // decision changes it too.
  await Promise.all([load(VIEW_SECTIONS.memory, { quiet: true }), loadAuto(), loadProfile(),
    loadSavedFacts()]);
  render("memory");
}

/** Turn a write into a toast, so no handler swallows a failure silently. */
async function memoryWrite(command, args, okText) {
  // Nothing may be written while the pane is showing a past moment. Every
  // caller already hides its buttons in that state, so reaching here means a
  // code path was added that forgot to — which is exactly when a guard earns
  // its keep, because the write would have landed on TODAY'S store while the
  // owner was looking at last June.
  if (memoryAsOf !== null) {
    toast("This is what Jarvis believed then. Return to now to change anything.", "bad");
    return null;
  }
  try {
    const out = await invoke(command, args);
    // The server can refuse while still answering 200 — the learning switch
    // does exactly that when JARVIS_EXTRACT is off in the environment. Render
    // what came back, never what was asked for.
    if (out && out.ok === false) {
      toast(String(out.error || out.reason || "Refused."), "bad");
    } else {
      toast(typeof okText === "function" ? okText(out) : okText, "ok");
      // Forgotten, reworded or erased, from either list: no longer current, so not
      // "saved automatically" any more - even on a page "Load older" brought
      // in, which the re-read below does not replace.
      if (command === "brain_memory_forget" || command === "brain_memory_edit"
          || command === "brain_memory_erase") {
        autoL.rows = autoL.rows.filter((r) => r.id !== args.id);
      }
    }
    await refreshMemory();
    return out;
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
    return null;
  }
}

/* ==========================================================================
   Private answers - Settings' "Windows Hello for memory lists and chat history"

   While it is on, brain_read hands the two memory lists back EMPTY, with
   `hidden: true` and how many there were (lock.rs redact_private). The
   entries never reach this page until Show has passed Windows Hello, so
   nothing here can be read round: this only draws the count and the button.
   ========================================================================== */

/** How many proposals are waiting, whether or not they are shown. */
function waitingCount(pending) {
  if (!pending) return 0;
  if (pending.hidden === true) return Number(pending.hidden_count) || 0;
  return (Array.isArray(pending.pending) && pending.pending.length) || 0;
}

function hiddenNode(count, what) {
  const n = Number(count) || 0;
  const box = el("div", "private-hidden");
  box.append(el("p", "empty", n
    ? `${n} ${what === "facts" ? (n === 1 ? "fact" : "facts") : "waiting"}, hidden until Windows Hello confirms it is you.`
    : "Hidden until Windows Hello confirms it is you."));
  box.append(button("Show", revealPrivate,
    { title: "Asks Windows Hello - your PIN, fingerprint or face - then shows this list." }));
  return box;
}

async function revealPrivate() {
  try {
    await invoke("reveal_private_answers");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
    return;
  }
  await refreshMemory();
  // The deep questions, on the Memory tab, come back with the lists.
  deep.at = 0;
  fx.at = 0;
  if (state.view !== "memory") render(state.view);
  else loadDeep();
}

// Settings changed, or the owner was away long enough that a Show ended:
// read the lists again - Rust decides whether they come back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const reread = async () => {
    await load(VIEW_SECTIONS.memory, { quiet: true });
    render(state.view);
  };
  TAURI.event.listen("security-changed", reread);
  TAURI.event.listen("private-hidden", reread);
}

function renderLearning() {
  const facts = state.data.memory_facts || {};
  const pending = state.data.memory_pending || {};
  dom.memoryLearning.replaceChildren();
  const why = unavailable("memory_facts");
  if (why) return dom.memoryLearning.append(whyNode("memory_facts"));

  // A past view's rows came from a Show; hidden again, it goes back to now.
  if (facts.hidden === true) {
    memoryAsOf = null;
    memoryAsOfRows = null;
  }
  const on = facts.learning === true;
  if (on) state.learningAsk = null;    // the card was approved
  const setup = pending.setup || {};
  noteSleepOffer(setup);

  if (cachedSleepOffer) {
    const offer = cachedSleepOffer;
    const list = el("div", "rows");
    list.append(
      row({
        tag: "offer",
        state: "warn",
        title: String(offer.title || "Overnight memory tidying - not built yet"),
        meta: [String(offer.body || "")],
        actions: [
          // Dismissed BEFORE the write, not after: `memoryWrite`'s own
          // success path calls `refreshMemory()` internally, before this
          // handler gets a chance to run anything of its own, and that
          // re-render has to see `sleepOfferDismissed` already set - or
          // `noteSleepOffer` re-adopts the very offer this click is
          // answering, from whatever `pending.setup` that fetch still holds.
          // Rolled back below only if the write actually fails, so a network
          // hiccup never costs the owner their only way to act on this until
          // tomorrow's offer. The immediate `render("memory")` also closes
          // the double-click window that dismissing-after left open: the
          // card leaves the DOM right away, taking its buttons with it,
          // instead of staying clickable for the length of the write.
          button("Enable", async () => {
            const answered = cachedSleepOffer;
            dismissSleepOffer();
            render("memory");
            // The truth, which is short: nothing is built, so nothing runs.
            // This toast used to promise an overnight tidy that nothing does.
            const out = await memoryWrite("brain_memory_sleep_time", { enabled: true },
              "Noted that you want it. It is not built yet, so nothing runs "
              + "and nothing in memory changes.");
            if (!out || out.ok === false) {
              cachedSleepOffer = answered;
              sleepOfferDismissed = false;
              render("memory");
            }
          }, { title: "Records that you want overnight tidying. It is not built yet: "
                     + "nothing runs, and no fact changes without your yes on that "
                     + "one fact.", live: true }),
          button("Not now", async () => {
            dismissSleepOffer();
            render("memory");
            // A real answer since 2026-09-25 (jarvis_backoff.py): the PC keeps
            // this offer quiet for a day, then a week, then a month. Not held
            // on a stale link - it only makes Jarvis quieter - and a failure
            // only means the offer may come back tomorrow, as before.
            try {
              const out = await invoke("brain_memory_sleep_time", { notNow: true });
              if (out && out.said) toast(String(out.said), "ok");
            } catch {
              /* dismissed here either way */
            }
          }, { title: "Not now. Jarvis waits a day before offering this again, then a week, "
                     + "then a month. Turning it on stays one tap away." }),
          button("Stop asking", async () => {
            const answered = cachedSleepOffer;
            dismissSleepOffer();
            render("memory");
            const out = await memoryWrite("brain_memory_sleep_time", { remind: false },
              "Won't ask again.");
            if (!out || out.ok === false) {
              cachedSleepOffer = answered;
              sleepOfferDismissed = false;
              render("memory");
            }
          }, { title: "Never offer this again. (The choice is saved in sleep_time.json "
                     + "in Jarvis's config folder; deleting that file brings the offer back.)",
               live: true }),
        ],
      })
    );
    dom.memoryLearning.append(list);
  }

  const dl = el("dl", "kv");
  dl.append(el("dt", "", "Background learning"), el("dd", "", on ? "on" : "off"));
  dl.append(el("dt", "", "Waiting"), el("dd", "",
    String(facts.pending ?? waitingCount(pending))));
  if (setup.note) dl.append(el("dt", "", "Note"), el("dd", "", String(setup.note)));
  // memory-intake.patch: why the last "Remember:" did NOT become a card (a
  // queued one is already a card, marked "your own words"), or that it was
  // saved without one (`auto_saved`, JARVIS-API.md section 19), and how many
  // repeat cards were dropped - the backend's own sentences, as the phone's
  // MemoryCards.setupNotes shows them.
  const last = setup.remember_last;
  if (last && (last.queued === false || last.auto_saved === true) && last.note) {
    dl.append(el("dt", "", "Last “Remember:”"), el("dd", "", String(last.note)));
  }
  if (setup.near_duplicates_note) {
    dl.append(el("dt", "", MEMORY_WORDS.repeats),
      el("dd", "", String(setup.near_duplicates_note)));
  }
  dom.memoryLearning.append(dl);

  // Our own click, or a card raised elsewhere - the history switch's rule
  // (`chats.ask || v.waiting`), read from the queue.
  if (state.learningAsk || (!on && learningCardWaiting())) {
    dom.memoryLearning.append(el("p", "hint learning-waiting",
      `Waiting for your approval to turn background learning on. Approve it ${APPROVE_WHERE}.`));
  }
  const box = el("div", "row-actions");
  box.append(
    button(on ? "Pause background learning" : "Start background learning", async () => {
      const waitingBefore = new Set(
        (currentQueue().items || []).map((item) => item && item.id).filter(Boolean)
      );
      const out = await memoryWrite(
        "brain_memory_learning",
        { enabled: !on },
        (out) =>
          out && out.waiting
            // Turning learning ON raises an approval card (learning-asks.patch):
            // it is NOT on yet, and it is not "off" as a result of this either.
            ? String(out.message || `Waiting for your approval. Approve it ${APPROVE_WHERE}.`)
            : out && out.note
              ? String(out.note)
              : out && out.enabled
                ? "Background learning is on."
                : "Background learning is off. Nothing new will be proposed."
      );
      state.learningAsk = out && out.waiting ? { cardId: await findNewCard(waitingBefore) } : null;
      renderLearning();
    }, { title: on
        ? "Stop reading conversations for facts. Nothing already proposed is lost. "
          + "A message that starts “Remember:” still makes a card."
        : "Read conversations for facts again. With “Learn automatically” on, facts in "
          + "your own words are saved straight away; everything else waits for your yes." })
  );
  box.append(
    button("Export everything", async () => {
      try {
        // To a file the owner picks, never the clipboard. Windows can sync
        // the clipboard to other devices ("Sync across your devices"), so a
        // clipboard copy of everything Jarvis knows about the owner could
        // leave this machine with nobody deciding that it should. The save
        // dialog is opened by the app itself (brain.rs); this window gets no
        // file access of its own.
        const out = await invoke("brain_memory_export");
        if (!out || out.cancelled) return;
        const n = Number(out.facts) || 0;
        toast(`Saved ${n} fact${n === 1 ? "" : "s"} to ${out.saved}. `
          + "Keep that file private: it holds everything Jarvis knows about you.", "ok");
      } catch (error) {
        toast(String((error && error.message) || error), "bad");
      }
    }, { title: "Save every fact, current and retired, to a file you choose. "
        + "Nothing is sent anywhere." })
  );
  box.append(
    button(memoryAsOf === null ? "What did you know on\u2026" : "Back to now", async () => {
      if (memoryAsOf !== null) {
        memoryAsOf = null;
        memoryAsOfRows = null;
        render("memory");
        return;
      }
      // A date, not a datetime. Nobody remembers the hour they told their
      // assistant something, and asking for one would make the feature feel
      // like a database console.
      const typed = window.prompt(
        "What did Jarvis know on this date?\n\nYYYY-MM-DD",
        new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10)
      );
      if (typed === null) return;
      const day = typed.trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) {
        toast("A date like 2026-06-01.", "bad");
        return;
      }
      const when = asOfSeconds(day, new Date());
      if (when === null) {
        toast(`Pick a real date from ${AS_OF_EARLIEST_YEAR} up to today.`, "bad");
        return;
      }
      try {
        const out = await invoke("brain_memory_as_of", { when });
        // The server answers a date it cannot use with TODAY's facts and no
        // `known_at` - which this screen would then have labelled "what
        // Jarvis believed on" the typed date. Refused instead.
        if (!out || typeof out.known_at !== "number") {
          toast("Jarvis answered without using that date, so nothing is shown "
            + "rather than today's facts under the wrong heading.", "bad");
          return;
        }
        memoryAsOf = when;
        memoryAsOfRows = Array.isArray(out && out.facts) ? out.facts : [];
        render("memory");
      } catch (error) {
        toast(String((error && error.message) || error), "bad");
      }
    }, { title: memoryAsOf === null
        ? "Show what Jarvis believed on a past date, including things it has since stopped believing. Read-only."
        : "Go back to what is true now." })
  );
  dom.memoryLearning.append(box);
}

function renderProposals() {
  const body = state.data.memory_pending || {};
  const why = unavailable("memory_pending");
  if (why) {
    dom.memoryProposals.replaceChildren(whyNode("memory_pending"));
    return;
  }
  if (body.hidden === true) {
    dom.memoryProposals.replaceChildren(hiddenNode(body.hidden_count, "waiting"));
    return;
  }
  const items = Array.isArray(body.pending) ? body.pending : [];
  rows(
    dom.memoryProposals,
    items,
    (p) => proposalRow(p),
    "Nothing is waiting. Either Jarvis has not heard anything worth keeping, or background learning is off."
  );
}

/**
 * One review card. Three kinds, each labelled for what its buttons really do:
 *
 * - an ordinary proposal: Keep / Discard, plus "Both are true" when the
 *   server says the card corrects an older fact and both can stand
 *   (`keep_both_ok`, memory-intake.patch);
 * - a "stop using this fact?" card (`source == "feedback_retire"`,
 *   feedback.patch): accepting RETIRES the fact it names, so its buttons say
 *   "Stop using this fact" / "Keep using it", never "Keep" - which on this
 *   card would do the opposite of what it says;
 * - any card whose text reads like a planted instruction (`flags`) carries
 *   a plain-words warning. The warning drops nothing; the owner decides.
 *
 * Still one card, one decision. Nothing here decides more than one.
 */
function proposalRow(p) {
  const id = Number(p.id);
  // memory-entities.js: "are these the same?" (memory wave 3). Its own two
  // answers - never Keep / Discard, never "Both are true".
  if (p.source === MERGE_SOURCE) return mergeRow(p, id);
  const flags = Array.isArray(p.flags) ? p.flags.filter((f) => f && typeof f === "object") : [];
  const retire = p.source === "feedback_retire";
  const meta = retire
    ? [
        p.replaces_text || p.replaces ? `The fact: “${p.replaces_text || p.replaces}”` : "",
        "Stopping it does not delete it: the fact stays in Jarvis's history, marked as no longer used.",
        // The phone shows why this stayed a card on a retire card too
        // (MemoryCards.from); so does this window now (the memory review's
        // fit audit, 2026-09-27).
        ...reasonLines(p),
        ago(p.created),
      ]
    : [
        // Only a card that names the stored fact BY ID replaces anything:
        // jarvis_extract._accept() retires by `replaces_id` and nothing else
        // (memory-safety.patch). `replaces` alone is the model's own
        // description of some fact, and a card with words but no id retires
        // nothing - so it must not say it would. Same rule as the phone's
        // MemoryCards.from. The stored fact's own words, when the server
        // sent them, rather than the model's description of it.
        p.replaces_id
          ? `would replace: ${p.replaces_text || p.replaces || `fact #${p.replaces_id}`}`
          : "",
        p.verbatim ? "your own words" : "",
        p.confidence != null ? `confidence ${Number(p.confidence).toFixed(2)}` : "",
        p.source ? `from ${p.source}` : "",
        // Why automatic learning left this one for your yes (section 2 of
        // JARVIS-API.md section 19): "from pasted text", "sensitive:
        // health"... in the PC's own words. Then, on its own line, the PC's
        // "it sounds older than what Jarvis knows" warning with plain dates
        // (memory-words.js cardLines; the memory review's I9).
        ...reasonLines(p),
        ago(p.created),
      ];
  const actions = retire
    ? [
        button("Stop using this fact", async () => {
          await memoryWrite("brain_memory_decide", { id, accept: true },
            "Jarvis will stop using that fact. It stays in the history.");
        }, { title: "Jarvis stops recalling this fact. It is not deleted.", live: true }),
        button("Keep using it", async () => {
          await memoryWrite("brain_memory_decide", { id, accept: false },
            "Kept. Jarvis will go on using that fact.");
        }, { title: "Leave the fact exactly as it is.", live: true }),
      ]
    : [
        button("Keep", async () => {
          await memoryWrite("brain_memory_decide", { id, accept: true },
            "Kept. Jarvis can recall it now.");
        }, { title: "Add it to memory. It can be reworded or forgotten later.", live: true }),
        ...(p.keep_both_ok === true
          ? [button("Both are true", async () => {
              await memoryWrite("brain_memory_keep_both", { id },
                "Kept both. The older fact stays current too.");
            }, { title: "Keep this AND the fact it would replace. Nothing is retired.", live: true })]
          : []),
        button("Discard", async () => {
          await memoryWrite("brain_memory_decide", { id, accept: false },
            "Discarded. It was never in memory.");
        }, { title: "Throw the proposal away. Nothing is removed from memory, because it was never there.", live: true }),
      ];
  const item = row({
    tag: retire ? "stop using?" : "proposed",
    state: retire || flags.length ? "bad" : "warn",
    title: String(p.text || "(no text)"),
    meta,
    actions,
  });
  if (flags.length) {
    const warn = el("div", "row-warning");
    warn.append(el("strong", "", "Careful: this reads like an instruction someone slipped in, not a fact about you. "));
    warn.append(el("span", "", "Only keep it if you really said this. "));
    for (const f of flags) {
      if (f.why) warn.append(el("span", "row-warning-why", String(f.why)));
    }
    const main = item.querySelector(".row-main");
    (main || item).append(warn);
  }
  return item;
}

/**
 * An "are these the same?" card (memory-entities.patch): the PC saw a new
 * name that is likely a typo of one it knows. Yes joins the two (a question
 * about one then finds the other's facts); no keeps them apart, and the PC
 * never asks about that pair again. One card, one decision - like every
 * other card here - and no fact is added, changed or forgotten either way.
 */
function mergeRow(p, id) {
  return row({
    tag: MERGE_TAG,
    state: "warn",
    title: String(p.text || "(no text)"),
    meta: [MERGE_NOTE, ago(p.created)],
    actions: [
      button(MERGE_YES, async () => {
        await memoryWrite("brain_memory_decide", { id, accept: true }, MERGE_JOINED);
      }, { title: MERGE_YES_TITLE, live: true }),
      button(MERGE_NO, async () => {
        await memoryWrite("brain_memory_decide", { id, accept: false }, MERGE_KEPT);
      }, { title: MERGE_NO_TITLE, live: true }),
    ],
  });
}

/* ==========================================================================
   "About <name>" (memory wave 3, 2026-09-25; memory-entities.js)

   Under a fact still in use: the people and things the PC linked it to,
   each a small button. It opens "About <name>": that entry's facts, word
   for word, read by id (memory_used - hidden like every memory list), with
   what the owner calls them. A read only; changes stay on the fact lists.
   ========================================================================== */

const aboutL = { id: null, view: null, error: "", loading: false };

function entitiesView() {
  return readEntities(state.data.memory_entities);
}

/** The "About: Priya, Lisbon" line under one fact, or null. */
function linkedNode(f) {
  const ents = entitiesFor(entitiesView(), f.id);
  if (!ents.length) return null;
  const line = el("span", "row-meta entity-links");
  line.append(el("span", "", `${LINKED_LABEL} `));
  for (const e of ents) {
    const b = button(e.name, () => openAbout(e.id), { title: aboutTitle(e.name) });
    b.classList.add("entity-link");
    b.dataset.entity = String(e.id);
    line.append(b, " ");
  }
  return line;
}

function withLinks(item, f) {
  const links = linkedNode(f);
  if (links) {
    const main = item.querySelector(".row-main");
    (main || item).append(links);
  }
  return item;
}

async function openAbout(entityId) {
  aboutL.id = Number(entityId);
  aboutL.view = null;
  aboutL.error = "";
  paintAbout();
  if (dom.memoryAboutCard) dom.memoryAboutCard.scrollIntoView({ block: "nearest" });
  const e = entityById(entitiesView(), aboutL.id);
  if (!e || !e.factIds.length || !IS_TAURI) return paintAbout();
  aboutL.loading = true;
  try {
    aboutL.view = readUsed(await invoke("memory_used", { ids: e.factIds.slice(0, ABOUT_MAX) }));
  } catch (error) {
    aboutL.error = errorText(error);
  } finally {
    aboutL.loading = false;
  }
  paintAbout();
}

function closeAbout() {
  aboutL.id = null;
  aboutL.view = null;
  paintAbout();
}

function paintAbout() {
  const card = dom.memoryAboutCard;
  const box = dom.memoryAbout;
  if (!card || !box) return;
  const ents = entitiesView();
  const e = aboutL.id === null ? null : entityById(ents, aboutL.id);
  if (!e || ents.hidden) {
    card.hidden = true;
    box.replaceChildren();
    return;
  }
  card.hidden = false;
  if (dom.memoryAboutTitle) dom.memoryAboutTitle.textContent = aboutTitle(e.name);
  box.replaceChildren();
  for (const line of [calledLine(e.aliases), alsoLine(e.also)].filter(Boolean)) {
    box.append(el("p", "about-line", line));
  }
  const v = aboutL.view;
  if (!e.factIds.length) {
    box.append(el("p", "empty", ABOUT_EMPTY));
  } else if (!v) {
    box.append(el("p", `empty${aboutL.error ? " failed" : ""}`, aboutL.error
      ? `Could not read these facts: ${aboutL.error}` : "Reading…"));
  } else if (!v.available) {
    box.append(el("p", "empty", v.why));
  } else if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount || e.factIds.length, "facts"));
  } else {
    const list = el("div", "rows about-rows");
    for (const f of v.facts) {
      const marks = [];
      if (f.pinned) marks.push(PINNED_MARK);
      if (!f.current && !f.erasedAt) marks.push(NOT_CURRENT_MARK);
      const item = row({
        tag: "fact",
        state: f.current ? "ok" : "idle",
        title: f.erasedAt ? erasedLine(f.erasedAt) : (f.text || "(no text)"),
        meta: marks,
        actions: [],
      });
      item.dataset.id = String(f.id);
      list.append(item);
    }
    box.append(list);
    const more = moreLine(e.factIds.length - Math.min(e.factIds.length, ABOUT_MAX));
    if (more) box.append(el("p", "empty", more));
  }
  const foot = el("div", "row-actions");
  foot.append(button("Close", closeAbout));
  box.append(foot);
}

function renderFacts() {
  paintAbout();
  const body = state.data.memory_facts || {};
  const why = unavailable("memory_facts");
  if (why) {
    dom.memoryFacts.replaceChildren(whyNode("memory_facts"));
    return;
  }
  if (body.hidden === true) {
    memoryAsOf = null;
    memoryAsOfRows = null;
    dom.memoryFacts.replaceChildren(hiddenNode(body.hidden_count, "facts"));
    return;
  }
  const past = memoryAsOf !== null;
  const loaded = past
    ? (memoryAsOfRows || [])
    : (Array.isArray(body.facts) ? body.facts : []);
  // The filter box (ease-of-use audit #7): the list already loaded, by its
  // words. An erased fact has no words left, so a filter never matches it.
  const needle = (dom.memoryFactsFilter?.value || "").trim().toLowerCase();
  const facts = needle
    ? loaded.filter((f) => erasedAt(f) === null && String(f.text || "").toLowerCase().includes(needle))
    : loaded;
  // `rows()` calls replaceChildren on whatever it is given, so the banner
  // cannot share a parent with it. The list goes in its own box and the pane
  // is assembled afterwards.
  const list = el("div", "");
  rows(
    list,
    facts,
    (f) => {
      // `current` is computed server-side, but do not depend on it being
      // there: a retired fact rendered as live is a fact the owner thinks
      // Jarvis still uses, offered a Forget button that does nothing. Fall
      // back to the bi-temporal field the flag is derived from.
      // The server computes `current` against the moment being asked about —
      // now, or the "as of" date — so the fallback has to use the same moment,
      // not Date.now(). Getting that wrong would render a fact as live in a
      // view of last June because it happens to be live today.
      const asOfSeconds = past ? memoryAsOf : Date.now() / 1000;
      const current =
        f.current === true ? true
        : f.current === false ? false
        : f.valid_to === null || f.valid_to === undefined
          || Number(f.valid_to) > asOfSeconds;
      // "Erase the words" (the owner's decision, 2026-09-24): an erased fact
      // is drawn as the date it was erased, never its words - the server
      // sends a marker as its text, and that marker is not shown either.
      const erased = erasedAt(f);
      const actions = [];
      if (current && !past && erased === null) {
        actions.push(
          button("Reword", async () => {
            // A prompt rather than an inline editor: this is the one place the
            // owner rewrites something the model will be told, and a
            // full-width text box that autosaves is how a stray keystroke
            // becomes a fact. A dialog makes the change deliberate.
            const next = window.prompt("Reword this fact:", String(f.text || ""));
            if (next === null) return;
            const text = next.trim();
            if (!text || text === String(f.text || "")) return;
            const validTo = promptValidTo(
              "When did the old wording stop being true?\n\n" +
              "Leave blank for \"just now\" — the usual case. Only answer this " +
              "if the change is really old news, like correcting an address " +
              "you moved out of months ago."
            );
            if (validTo === undefined) return; // the date prompt was cancelled
            const args = { id: Number(f.id), text };
            if (validTo !== null) args.valid_to = validTo;
            await memoryWrite("brain_memory_edit", args,
              "Reworded. The old wording is kept as history.");
          }, { title: "Replace the wording. The old one is retired, not erased." }),
          button("Forget", async () => {
            if (!window.confirm(forgetQuestion(f))) return;
            const validTo = promptValidTo(
              "When did this actually stop being true?\n\n" +
              "Leave blank for \"just now\" — the usual case. Only answer this " +
              "if it stopped being true a while ago and you are only telling " +
              "Jarvis about it now."
            );
            if (validTo === undefined) return; // the date prompt was cancelled
            const args = { id: Number(f.id) };
            if (validTo !== null) args.valid_to = validTo;
            await memoryWrite("brain_memory_forget", args, FORGOTTEN);
          }, { danger: true, title: "Stop this being recalled. There is no undo." })
        );
      }
      // "Always keep in mind": Pin / Unpin on a fact still in use, first -
      // before the buttons that cannot be undone, as in Saved automatically.
      if (current && !past && erased === null) {
        const pin = pinButton(f);
        if (pin) actions.unshift(pin);
      }
      // Erase is offered on a forgotten fact too: forgetting kept its words,
      // and this is how they go. Never in the past view, like every write.
      if (!past && erased === null) {
        actions.push(button(ERASE_LABEL, () => eraseFact(f),
          { danger: true, live: true, title: ERASE_TITLE }));
      }
      const item = row({
        tag: erased !== null ? "erased" : current ? "fact" : "retired",
        state: current && erased === null ? "ok" : undefined,
        title: erased !== null ? erasedLine(erased) : String(f.text || "(no text)"),
        meta: [
          f.source === "auto" ? "saved automatically"
            : f.source ? `from ${f.source}` : "",
          // One wording in both apps (the memory review's I11): today,
          // a fact no longer in use is "no longer used", like the count
          // above; on a past date, "true then" / "no longer true", as the
          // phone's "What did Jarvis know on this date?" says it.
          past
            ? (current ? MEMORY_WORDS.true_then : MEMORY_WORDS.no_longer_true)
            : (current ? "" : MEMORY_WORDS.no_longer_used),
          // `retired_by` is the column the store writes: the id of the fact
          // that replaced this one. (It used to read `supersedes`, which is
          // an argument to add(), not a column, so this never showed.)
          f.retired_by ? `replaced by #${f.retired_by}` : "",
          whenTrue(f),
          // The two axes, and the only place the difference is visible. They
          // are usually the same day and this says nothing; when they are not,
          // it is because the fact was corrected after the fact — "true until
          // January, found out in March" — and that is precisely the case the
          // second column was added for, so it must not be inferable only
          // from the JSON export.
          whenLearned(f),
          whenNoticed(f),
        ],
        actions,
      });
      // The names it is linked to, each opening "About <name>" - on a fact
      // in use, in today's view only (the links are today's).
      return current && !past && erased === null ? withLinks(item, f) : item;
    },
    needle && loaded.length
      ? "No fact on this list has those words."
      : past
        ? "Jarvis knew nothing on that date."
        : "Nothing yet. Facts arrive from the queue above, once you keep one."
  );
  if (past) {
    // Before the list, not after it: the difference between "these are your
    // facts" and "these WERE your facts" is the whole meaning of the screen,
    // and a footnote is read second.
    const when = new Date(memoryAsOf * 1000);
    dom.memoryFacts.replaceChildren(
      el("p", "banner",
         `What Jarvis believed on ${when.toLocaleDateString()} \u2014 right or ` +
         "wrong. Nothing here can be changed; use \u201cBack to now\u201d first."),
      list
    );
  } else {
    dom.memoryFacts.replaceChildren(list);
  }
}

/* ==========================================================================
   Wiki - backend/wiki.patch. Its own plate on the Memory tab, read through
   its own commands (not brain_read); the plate itself is wiki.js.
   ========================================================================== */

const wiki = { view: null, error: "", job: null, at: 0, loading: false };
/** The Memory tab repaints often; the list is re-read at most this often. */
const WIKI_READ_MS = 15000;

async function loadWiki() {
  if (wiki.loading) return;
  wiki.loading = true;
  try {
    wiki.view = readWiki(await invoke("wiki_status"));
    wiki.error = "";
  } catch (error) {
    wiki.error = String((error && error.message) || error);
  } finally {
    wiki.loading = false;
    wiki.at = Date.now();
  }
  paintWiki();
}

function paintWiki() {
  const box = $("wiki");
  if (!box) return;
  renderWiki(box, { ...wiki, onAdd: addWiki, onOpen: openWikiFolder }, { el, row, button });
}

function renderWikiPlate() {
  paintWiki();
  if (IS_TAURI && !wiki.loading && Date.now() - wiki.at > WIKI_READ_MS) loadWiki();
}

/** "Add to wiki": one card is raised on the PC; this follows it to the end. */
async function addWiki(source) {
  wiki.job = { source, said: { text: "Asking the PC…", tone: null, final: false } };
  paintWiki();
  // With the link to the PC down, polls are skipped rather than failed: the
  // job carries on there, and following it resumes when the link does.
  const last = await addToWiki(invoke, source, (said) => {
    wiki.job = { source, said };
    paintWiki();
  }, { linkDown: () => !currentLink().connected });
  announce(`${source}: ${last.text}`, last.tone === "bad" ? "assertive" : "polite");
  await loadWiki();
}

async function openWikiFolder() {
  try {
    await invoke("wiki_open_folder");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
}

/* ==========================================================================
   Deep questions - backend/big-model.patch. Their own plate on the Memory
   tab, beside the wiki (the big model's other job), read through their own
   commands; the list itself is deep.js.

   Refreshed by the `deep` event (a question finished) - see the onEvent
   handler at the bottom - and, only while a question is still going, by a
   gentle poll in case that event is missed.
   ========================================================================== */

const deep = { view: null, error: "", at: 0, loading: false, openId: undefined,
  asking: false, pollTimer: null, going: new Set() };
/** The Memory tab repaints often; the list is re-read at most this often. */
const DEEP_READ_MS = 15000;

async function loadDeep() {
  if (deep.loading) return;
  deep.loading = true;
  try {
    deep.view = readDeep(await invoke("get_deep"));
    deep.error = "";
  } catch (error) {
    deep.error = String((error && error.message) || error);
  } finally {
    deep.loading = false;
    deep.at = Date.now();
  }
  // Say when one this window saw going has finished.
  if (deep.view) {
    for (const job of deep.view.jobs) {
      if (deep.going.has(job.id) && !DEEP_RUNNING.has(job.state)) {
        announce(job.state === "done" ? "A deep question has been answered."
          : `A deep question was not answered. ${job.why}`);
      }
    }
    deep.going = new Set(deep.view.jobs.filter((j) => DEEP_RUNNING.has(j.state)).map((j) => j.id));
  }
  paintDeep();
  scheduleDeepPoll();
}

function paintDeep() {
  const lead = $("deep-state");
  if (!lead) return;
  const v = deep.view;
  const ask = $("deep-ask");
  if (!v) {
    lead.textContent = deep.error ? `Could not read the deep questions: ${deep.error}` : "Reading…";
    lead.dataset.ready = "false";
    ask.hidden = true;
  } else {
    lead.textContent = deepLead(v);
    lead.dataset.ready = String(v.available);
    // Only when GET /api/deep says available; otherwise the line says why.
    ask.hidden = !v.available;
    const box = $("deep-question");
    box.maxLength = v.questionChars;
    paintDeepCount();
  }
  renderDeepJobs($("deep-jobs"), {
    view: v, error: v ? deep.error : "", openId: deep.openId,
    onToggle: (id, open) => {
      if (open) deep.openId = id;
      else if (deep.openId === id || deep.openId === undefined) deep.openId = null;
    },
  }, { el, row, hiddenNode });
}

function paintDeepCount() {
  const v = deep.view;
  const box = $("deep-question");
  const count = $("deep-count");
  if (!v || !box || !count) return;
  const n = box.value.length;
  const going = runningCount(v);
  count.textContent = `${n.toLocaleString("en-US")} / ${v.questionChars.toLocaleString("en-US")} characters` +
    (going >= v.queue ? ` · ${going} questions are already waiting or running; ask again when one has finished.` : "");
}

function renderDeepPlate() {
  paintDeep();
  if (IS_TAURI && !deep.loading && Date.now() - deep.at > DEEP_READ_MS) loadDeep();
}

/** Only while a question is going, and only while the Memory tab shows. */
function scheduleDeepPoll() {
  clearTimeout(deep.pollTimer);
  deep.pollTimer = null;
  if (!deep.view || runningCount(deep.view) === 0) return;
  deep.pollTimer = setTimeout(() => {
    deep.pollTimer = null;
    if (state.view === "memory" && !document.hidden) loadDeep();
    else scheduleDeepPoll();
  }, DEEP_POLL_MS);
}

/** "Ask slowly": one question, queued in the background. No card. */
async function askDeepNow() {
  if (deep.asking) return;
  const box = $("deep-question");
  const said = $("deep-said");
  deep.asking = true;
  said.textContent = "Asking…";
  delete said.dataset.tone;
  try {
    const out = await askDeep(invoke, box.value);
    said.textContent = out.text;
    said.dataset.tone = out.tone;
    announce(out.text, out.tone === "bad" ? "assertive" : "polite");
    if (out.queued) {
      box.value = "";
      paintDeepCount();
    }
  } finally {
    deep.asking = false;
  }
  await loadDeep();
}

function setupDeepAsk() {
  const rowBox = $("deep-ask-row");
  const box = $("deep-question");
  if (!rowBox || !box) return;
  const go = button("Ask slowly", askDeepNow, {
    live: true,
    title: "The big model answers in the background, on this PC - expect minutes. No approval " +
      "card per question: you approved the Deep questions switch.",
  });
  go.id = "deep-ask-button";
  rowBox.prepend(go);
  box.addEventListener("input", paintDeepCount);
  box.addEventListener("keydown", (event) => {
    // Ctrl+Enter asks; a plain Enter is a new line in the question.
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (!go.disabled) go.click();
    }
  });
}
setupDeepAsk();

/* ==========================================================================
   History - chat history on the PC (JARVIS-API.md section 18). Its own tab,
   next to Memory, read through its own commands (brain/history.rs), not
   brain_read; the words and the transcript are history-view.js.

   The switch is the learning switch's shape: ON raises one approval card
   and shows "Waiting for your approval" until the card leaves the queue;
   OFF is immediate. Rust holds ON (and a keep change) on a stale link, and
   the controls are greyed then. Delete is one conversation, after a
   confirm. There is no "delete all".
   ========================================================================== */

const chats = {
  /** readHistory() of the first page, or null before the first read. */
  view: null,
  /** Every conversation shown, newest first: the first page, then older. */
  rows: [],
  /** The last page was full, so there may be older ones. */
  more: false,
  error: "",
  at: 0,
  loading: false,
  older: false,
  /** The conversation open below its row, and its transcript. */
  openId: null,
  open: null,
  openError: "",
  /** `{ cardId, gone }` while an ON card waits (like `learningAsk`). */
  ask: null,
};
/** The tab repaints often; the list is re-read at most this often. */
const HISTORY_READ_MS = 15000;

const errorText = (error) => String((error && error.message) || error);

async function loadHistory() {
  if (chats.loading) return;
  chats.loading = true;
  try {
    const v = readHistory(await invoke("brain_history_list", { before: null, limit: HISTORY_PAGE }));
    chats.view = v;
    // The re-read every 15 seconds replaces the newest page only: pages
    // "Load older" brought in stay, and so does a conversation opened
    // from one of them. A hidden list (Windows Hello) keeps nothing.
    const kept = v.hidden ? { rows: v.conversations, more: false }
      : refreshRows(chats.rows, v.conversations, HISTORY_PAGE, chats.more);
    chats.rows = kept.rows;
    chats.more = kept.more;
    chats.error = "";
    if (v.enabled) chats.ask = null; // the card was approved
    if (chats.openId && !chats.rows.some((c) => c.id === chats.openId)) {
      chats.openId = null;
      chats.open = null;
    }
  } catch (error) {
    chats.error = errorText(error);
  } finally {
    chats.loading = false;
    chats.at = Date.now();
  }
  paintHistory();
}

async function loadOlderHistory() {
  const before = olderThan(chats.rows);
  if (before === null || chats.older) return;
  chats.older = true;
  try {
    const v = readHistory(await invoke("brain_history_list", { before, limit: HISTORY_PAGE }));
    chats.rows = addPage(chats.rows, v.conversations);
    chats.more = v.conversations.length >= HISTORY_PAGE;
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    chats.older = false;
  }
  paintHistory();
}

async function toggleConversation(id) {
  if (chats.openId === id) {
    chats.openId = null;
    chats.open = null;
    paintHistory();
    return;
  }
  chats.openId = id;
  chats.open = null;
  chats.openError = "";
  paintHistory();
  try {
    const conv = readConversation(await invoke("brain_history_open", { id }));
    if (chats.openId === id) chats.open = conv;
  } catch (error) {
    if (chats.openId === id) chats.openError = errorText(error);
  }
  paintHistory();
}

async function deleteConversation(c) {
  if (!window.confirm(deleteQuestion(c))) return;
  try {
    const out = await invoke("brain_history_delete", { id: c.id });
    toast(out && out.gone ? "That conversation was already deleted." : "Deleted from this PC.", "ok");
    chats.rows = chats.rows.filter((r) => r.id !== c.id);
    if (chats.openId === c.id) {
      chats.openId = null;
      chats.open = null;
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  paintHistory();
}

async function setHistoryEnabled(on) {
  const waitingBefore = new Set(
    (currentQueue().items || []).map((item) => item && item.id).filter(Boolean)
  );
  try {
    const out = await invoke("brain_history_settings", { enabled: on, keepDays: null });
    if (out && out.ok === false) {
      toast(String(out.error || out.reason || "Refused."), "bad");
    } else if (on && out && out.waiting) {
      // Turning history ON raises an approval card: it is NOT on yet.
      chats.ask = { cardId: await findNewCard(waitingBefore) };
      toast(String(out.message || `Waiting for your approval. Approve it ${APPROVE_WHERE}.`), "ok");
    } else if (on) {
      chats.ask = null;
      toast(out && out.enabled === true ? ON_REPLY : String((out && out.message) || "Chat history is still off."),
        out && out.enabled === true ? "ok" : "bad");
    } else {
      chats.ask = null;
      toast(OFF_REPLY, "ok");
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  chats.at = 0;
  await loadHistory();
}

async function setKeepDays(days) {
  try {
    const out = await invoke("brain_history_settings", { enabled: null, keepDays: days });
    if (out && out.ok === false) toast(String(out.error || out.reason || "Refused."), "bad");
    else toast(keepReply(days, out), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  chats.at = 0;
  await loadHistory();
}

async function revealHistory() {
  try {
    await invoke("reveal_private_answers");
  } catch (error) {
    toast(errorText(error), "bad");
    return;
  }
  chats.at = 0;
  await loadHistory();
}

/** The ON card left the queue: read the switch again after the backend has
 *  had a moment to apply an approval. Still off: it was denied or ran out
 *  of time, and that is said - the learning switch's handler, for history. */
onQueue((queue) => {
  const ask = chats.ask;
  if (!ask || !ask.cardId || ask.gone) return;
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  if (items.some((item) => item && item.id === ask.cardId)) return;
  ask.gone = true;
  setTimeout(async () => {
    if (chats.ask !== ask) return;
    chats.at = 0;
    await loadHistory();
    if (chats.ask === ask) {
      chats.ask = null;
      if (!(chats.view && chats.view.enabled)) toast(DENIED_REPLY, "bad");
      paintHistory();
    }
  }, MODEL_ASK_GRACE_MS);
});

// Private answers turned on or off, or a Show ran out: read the list again -
// Rust decides whether it comes back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadHistory = () => {
    chats.at = 0;
    if (state.view === "history") loadHistory();
  };
  TAURI.event.listen("security-changed", rereadHistory);
  TAURI.event.listen("private-hidden", rereadHistory);
}

function paintHistorySettings() {
  const box = $("history-settings");
  if (!box) return;
  box.replaceChildren();
  const v = chats.view;
  if (!v) {
    const line = el("p", "empty", chats.error ? `Could not read the chat history: ${chats.error}` : "Reading…");
    if (chats.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadHistory));
    }
    box.append(line);
    return;
  }
  if (!v.available) {
    box.append(el("p", "empty", v.why));
    return;
  }

  const label = el("label", "history-switch");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = "history-enabled";
  input.setAttribute("role", "switch");
  input.setAttribute("aria-describedby", "history-switch-detail");
  input.checked = v.enabled;
  label.append(input, el("span", "history-switch-label", SWITCH_LABEL));
  const detail = el("p", "note history-switch-detail", SWITCH_DETAIL);
  detail.id = "history-switch-detail";
  box.append(label, detail);
  // Turning it ON waits for a live link (rule 4); OFF never does.
  if (!v.enabled) {
    input.dataset.title = "Asks you first, with an approval card.";
    liveButtons.add(input);
    syncLiveButton(input);
  }
  input.addEventListener("change", async () => {
    const want = input.checked;
    // Show what the PC says, never what was clicked: ON is only a card.
    input.checked = v.enabled;
    input.disabled = true;
    input.dataset.busy = "true";
    await setHistoryEnabled(want);
  });

  if (chats.ask || v.waiting) {
    box.append(el("p", "hint learning-waiting history-waiting",
      `Waiting for your approval to turn chat history on. Approve it ${APPROVE_WHERE}.`));
  }
  const why = notRecordingLine(v);
  if (why) box.append(el("p", "history-why-not", why));

  const keep = el("label", "history-keep");
  keep.append(el("span", "history-keep-label", "Delete conversations older than"));
  const select = document.createElement("select");
  select.id = "history-keep";
  select.className = "field";
  const choices = KEEP_CHOICES.some((c) => c.days === v.keepDays)
    ? KEEP_CHOICES
    : [...KEEP_CHOICES, { days: v.keepDays, label: keepLabel(v.keepDays) }];
  for (const c of choices) {
    const option = document.createElement("option");
    option.value = String(c.days);
    option.textContent = c.label;
    select.append(option);
  }
  select.value = String(v.keepDays);
  select.dataset.title = "Older conversations are deleted from this PC. There is no undo.";
  liveButtons.add(select);
  syncLiveButton(select);
  select.addEventListener("change", async () => {
    const days = Number(select.value);
    select.value = String(v.keepDays);
    // A shorter period (or any, from "Never") deletes conversations now,
    // with no undo: asked first, the phone's question word for word.
    if (keepNeedsConfirm(v.keepDays, days) && !window.confirm(keepConfirm(days))) return;
    select.disabled = true;
    select.dataset.busy = "true";
    await setKeepDays(days);
  });
  keep.append(select);
  box.append(keep);
}

function paintHistoryList() {
  const box = $("history-list");
  if (!box) return;
  box.replaceChildren();
  const v = chats.view;
  if (!v) {
    box.append(el("p", "empty", chats.error ? "Nothing to show until the chat history can be read." : "Reading…"));
    return;
  }
  if (!v.available) {
    box.append(el("p", "empty", "Nothing to show until this PC keeps chat history."));
    return;
  }
  if (v.hidden) {
    const hidden = el("div", "private-hidden");
    const n = v.hiddenCount;
    hidden.append(el("p", "empty", n
      ? `${n} ${n === 1 ? "conversation" : "conversations"}, hidden until Windows Hello confirms it is you.`
      : "Hidden until Windows Hello confirms it is you."));
    hidden.append(button("Show", revealHistory,
      { title: "Asks Windows Hello - your PIN, fingerprint or face - then shows this list." }));
    box.append(hidden);
    return;
  }
  if (!chats.rows.length) {
    box.append(el("p", "empty", v.enabled
      ? "No conversations kept yet."
      : "No conversations kept. Chat history is off."));
    return;
  }
  // The search box (ease-of-use audit row 20; the owner's answer of
  // 2026-09-27: "shown on screen only; nothing saved, nothing handed to the
  // AI"): the list already loaded, by its title only - nothing is asked of
  // the PC and nothing reaches the model. The same shape as "What Jarvis
  // knows about you"'s filter (renderFacts).
  const needle = ($("history-filter")?.value || "").trim().toLowerCase();
  const shown = needle
    ? chats.rows.filter((c) => String(c.title || "").toLowerCase().includes(needle))
    : chats.rows;
  if (needle && !shown.length) {
    box.append(el("p", "empty", chats.more
      ? "No loaded conversations match that search. \"Load older\" may bring in more to search."
      : "No conversations match that search."));
  }
  const list = el("div", "rows history-rows");
  for (const c of shown) {
    const open = chats.openId === c.id;
    const device = deviceTag(c.device);
    const item = row({
      tag: device.tag,
      title: c.title || "(no title)",
      meta: [rowMeta(c)],
      actions: [
        button(open ? "Close" : "Open", () => toggleConversation(c.id),
          { title: open ? "Close the conversation." : "Read the conversation. Nothing changes." }),
        button("Delete", () => deleteConversation(c),
          { danger: true, live: true, title: "Delete this conversation from this PC. There is no undo." }),
      ],
    });
    item.dataset.id = c.id;
    if (device.words) item.querySelector(".row-tag").title = device.words;
    const main = item.querySelector(".row-main");
    if (c.hasVoice || c.tainted) {
      const marks = el("span", "history-marks");
      if (c.hasVoice) {
        const mic = el("span", "history-mark history-mark-voice", "voice");
        mic.title = "Some of it was said aloud to Jarvis.";
        marks.append(mic);
      }
      if (c.tainted) {
        const taint = el("span", "history-mark history-mark-taint", "read outside text");
        taint.title = TAINT_TITLE;
        marks.append(taint);
      }
      main.append(marks);
    }
    list.append(item);
    if (open) {
      const t = el("div", "history-transcript");
      t.id = "history-transcript";
      if (chats.openError) t.append(el("p", "empty failed", chats.openError));
      else if (!chats.open) t.append(el("p", "empty", "Reading…"));
      else renderTranscript(t, chats.open, { el });
      list.append(t);
    }
  }
  box.append(list);
  if (chats.more) {
    const more = el("div", "row-actions history-more");
    more.append(button(chats.older ? "Loading…" : "Load older", loadOlderHistory,
      { title: "Show the next page of older conversations." }));
    box.append(more);
  }
}

function paintHistory() {
  paintHistorySettings();
  paintHistoryList();
}

function renderHistory() {
  paintHistory();
  if (IS_TAURI && !chats.loading && Date.now() - chats.at > HISTORY_READ_MS) loadHistory();
}

/* ==========================================================================
   Automatic learning (JARVIS-API.md section 19). On the Memory tab, next to
   the learning switch; the words are auto-learn.js, the commands
   brain/auto_learn.rs.

   The two switches are the learning switch's shape: ON raises one approval
   card and shows "Waiting for your approval" until the card leaves the
   queue - including a card raised on the phone; OFF is immediate. Rust
   holds ON on a stale link, and the switch is greyed then; OFF never is.
   While a card waits the switch is greyed too (a second ON would only ask
   for the same card), and "Cancel the request" in the waiting line sends
   OFF, which withdraws the card on the PC (FIXLIST 8, R6). Under each
   switch: how its newest card ended (`auto_last` / `sensitive_last`, in
   the PC's plain words when it refused), and for "Learn automatically" the
   PC's sentence when its settings file was damaged (`why`).
   "Saved automatically" lists what was saved without a card, newest first,
   with Forget on each (brain_memory_forget, one fact, after a confirm) and
   "Load older". A `memory_saved` event is a quiet line that opens the list.
   ========================================================================== */

const autoL = {
  /** readAuto() of the first page, or null before the first read. */
  view: null,
  /** Every fact shown, newest first: the first page, then older ones. */
  rows: [],
  more: false,
  error: "",
  /** The list alone could not be read (the switches could). */
  listError: "",
  at: 0,
  loading: false,
  /** A read was asked for while one was in flight: read once more after. */
  again: false,
  older: false,
  /** `{ cardId, gone }` while an ON card waits, per switch. */
  ask: { auto: null, sensitive: null },
  /** Whether each switch's card was in the queue at the last look. */
  seen: { auto: false, sensitive: false },
  /** Ids of ON cards withdrawn by turning the switch OFF while they waited
   *  (R6). The PC has let go of them - approving one changes nothing - but
   *  the card stays in the queue until it is answered or runs out, so the
   *  switch must not keep saying "waiting" for it. */
  withdrawn: { auto: new Set(), sensitive: new Set() },
  /** Ids from `memory_saved` events the owner has not looked at yet. */
  unseen: new Set(),
};
const AUTO_READ_MS = 15000;

async function loadAuto() {
  if (autoL.loading) {
    autoL.again = true;
    return;
  }
  autoL.loading = true;
  try {
    // The switches come from GET /api/memory/learning, the list from GET
    // /api/memory/auto; an older PC without the first is read from the
    // second (readAuto). Both failing is the one error worth a Retry.
    const [list, status] = await Promise.allSettled([
      invoke("brain_memory_auto_list", { before: null, limit: AUTO_PAGE }),
      invoke("brain_memory_learning_status"),
    ]);
    if (list.status === "rejected" && status.status === "rejected") throw list.reason;
    autoL.listError = list.status === "rejected" ? errorText(list.reason) : "";
    const v = readAuto(list.status === "fulfilled" ? list.value : null,
      status.status === "fulfilled" ? status.value : null);
    autoL.view = v;
    // Pages "Load older" brought in stay; a hidden list keeps nothing.
    const kept = v.hidden ? { rows: [], more: false }
      : refreshAutoRows(autoL.rows, v.facts, AUTO_PAGE, autoL.more);
    autoL.rows = kept.rows;
    autoL.more = kept.more;
    autoL.error = "";
    if (v.auto) autoL.ask.auto = null;           // the card was approved
    if (v.sensitive) autoL.ask.sensitive = null;
  } catch (error) {
    autoL.error = errorText(error);
  } finally {
    autoL.loading = false;
    autoL.at = Date.now();
  }
  if (autoL.again) {
    autoL.again = false;
    await loadAuto();
    return;
  }
  if (state.view === "memory") paintAuto();
}

async function loadOlderAuto() {
  const before = olderAuto(autoL.rows);
  if (before === null || autoL.older) return;
  autoL.older = true;
  try {
    const v = readAuto(await invoke("brain_memory_auto_list", { before, limit: AUTO_PAGE }), null);
    autoL.rows = addAutoPage(autoL.rows, v.facts);
    autoL.more = v.facts.length >= AUTO_PAGE;
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    autoL.older = false;
  }
  paintAuto();
}

/** Whether the approval queue holds this switch's ON card, wherever it was
 *  raised - this window, the phone, or anywhere else. */
function autoCardWaiting(which, queue = currentQueue()) {
  const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
  const action = AUTO_SWITCHES[which].action;
  const gone = autoL.withdrawn[which];
  return items.some((item) => item && item.action === action && !gone.has(item.id));
}

async function setAutoSwitch(which, on) {
  const sw = AUTO_SWITCHES[which];
  const waitingBefore = new Set(
    (currentQueue().items || []).map((item) => item && item.id).filter(Boolean)
  );
  try {
    const out = await invoke(sw.command, { enabled: on });
    const said = out && typeof out.message === "string" ? out.message.trim() : "";
    if (out && out.ok === false) {
      toast(String(out.error || out.reason || "Refused."), "bad");
    } else if (on && out && out.waiting) {
      // ON raises an approval card: it is NOT on yet.
      autoL.ask[which] = { cardId: await findNewCard(waitingBefore) };
      toast(said || sw.waiting(APPROVE_WHERE), "ok");
    } else {
      autoL.ask[which] = null;
      // OFF withdraws a waiting ON card on the PC (R6): the card is not
      // counted as waiting any more, even while it is still in the queue.
      if (!on) {
        for (const item of currentQueue().items || []) {
          if (item && item.action === sw.action && item.id) autoL.withdrawn[which].add(item.id);
        }
      }
      // The PC's own sentence first, both ways (FIXLIST 5).
      toast(said || (on ? sw.on : sw.off), "ok");
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  autoL.at = 0;
  await loadAuto();
}

/** "Erase the words" on one fact, from either list: asks first, then one
 *  brain_memory_erase for that id (held on a stale link in Rust, like
 *  Forget). An erased fact is no longer current, so it leaves "Saved
 *  automatically" too. */
async function eraseFact(f) {
  if (!window.confirm(eraseQuestion(f))) return;
  const out = await memoryWrite("brain_memory_erase", { id: Number(f.id) }, ERASED);
  if (out && out.ok !== false) {
    autoL.rows = autoL.rows.filter((r) => r.id !== Number(f.id));
    paintAuto();
  }
}

async function forgetAuto(f) {
  if (!window.confirm(forgetQuestion(f))) return;
  const out = await memoryWrite("brain_memory_forget", { id: f.id }, FORGOTTEN);
  if (out && out.ok !== false) {
    autoL.rows = autoL.rows.filter((r) => r.id !== f.id);
    paintAuto();
  }
}

/** A `memory_saved` event: count what was saved, and read the list again. */
function noteMemorySaved(data) {
  const ids = savedIds(data);
  if (!ids.length) return;
  for (const id of ids) autoL.unseen.add(id);
  autoL.at = 0;
  paintSavedLine();
  if (state.view === "memory") loadAuto();
}

/** The whole "Saved automatically" list: shown and scrolled to. */
async function showSavedList() {
  if (state.view !== "memory") await showView("memory");
  const card = $("memory-auto-card");
  if (card) {
    card.scrollIntoView({ block: "start" });
    dom.memoryAutoList.focus({ preventScroll: true });
  }
}

/* "Jarvis remembered 2 things" opens the facts themselves (the owner's
   decision, 2026-09-25; JARVIS-API.md section 19.5): their words read from
   the PC by id (memory-used.js, brain/used.rs memory_used - hidden like
   every memory list under Windows Hello), each with Forget and "Erase the
   words", the same one-fact commands and confirms as the list below. */
const savedFacts = { ids: [], open: false, view: null, error: "", loading: false };

async function loadSavedFacts() {
  if (!savedFacts.open || !savedFacts.ids.length || !IS_TAURI) return;
  savedFacts.loading = true;
  paintSavedLine();
  try {
    savedFacts.view = readUsed(await invoke("memory_used", { ids: savedFacts.ids }));
    savedFacts.error = "";
  } catch (error) {
    savedFacts.view = null;
    savedFacts.error = errorText(error);
  } finally {
    savedFacts.loading = false;
  }
  paintSavedLine();
}

/** The quiet line opens those facts, and the line goes - here and in
 *  Rust's copy of the count (below). */
async function openSavedList() {
  savedFacts.ids = [...autoL.unseen];
  savedFacts.open = true;
  savedFacts.view = null;
  autoL.unseen.clear();
  if (IS_TAURI) invoke("brain_memory_saved_unseen", { seen: true }).catch(() => {});
  if (state.view !== "memory") await showView("memory");
  paintSavedLine();
  await loadSavedFacts();
  const box = dom.memorySavedLine;
  if (box) box.scrollIntoView({ block: "nearest" });
}

function savedFactsNode() {
  const box = el("div", "memory-saved-facts");
  box.append(el("h3", "memory-saved-title", REMEMBERED_TITLE));
  const v = savedFacts.view;
  if (!v) {
    box.append(el("p", `empty${savedFacts.error ? " failed" : ""}`, savedFacts.error
      ? `Could not read these facts: ${savedFacts.error}` : "Reading…"));
  } else if (!v.available) {
    box.append(el("p", "empty", v.why));
  } else if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount || savedFacts.ids.length, "facts"));
  } else {
    const list = el("div", "rows saved-fact-rows");
    const past = memoryAsOf !== null;
    for (const f of v.facts) {
      const acts = rowActions(f);
      const marks = [];
      if (f.pinned) marks.push(PINNED_MARK);
      if (!f.current && !f.erasedAt) marks.push(NOT_CURRENT_MARK);
      const item = row({
        tag: "auto",
        state: f.current ? "ok" : "idle",
        title: f.erasedAt ? erasedLine(f.erasedAt) : (f.text || "(no text)"),
        meta: marks,
        actions: past ? [] : [
          ...(acts.forget ? [button("Forget", () => forgetSaved(f),
            { danger: true, live: true, title: "Stop this being recalled. There is no undo." })] : []),
          ...(acts.erase ? [button(ERASE_LABEL, () => eraseSaved(f),
            { danger: true, live: true, title: ERASE_TITLE })] : []),
        ],
      });
      item.dataset.id = String(f.id);
      list.append(item);
    }
    box.append(list);
    const gone = missingLine(v.missing.length);
    if (gone) box.append(el("p", "empty", gone));
  }
  const foot = el("div", "row-actions");
  foot.append(
    button(SHOW_ALL, showSavedList, { title: "The whole list, newest first." }),
    button("Close", () => { savedFacts.open = false; paintSavedLine(); }),
  );
  box.append(foot);
  return box;
}

async function forgetSaved(f) {
  await forgetAuto(f);
  await loadSavedFacts();
}

async function eraseSaved(f) {
  await eraseFact(f);
  await loadSavedFacts();
}

/** The ON card left the queue: read the switch again after the backend has
 *  had a moment to apply an approval. Still off: it was denied or ran out
 *  of time, and that is said - the learning switch's handler. */
onQueue((queue) => {
  let changed = false;
  for (const which of Object.keys(AUTO_SWITCHES)) {
    const waitingNow = autoCardWaiting(which, queue);
    if (waitingNow !== autoL.seen[which]) {
      autoL.seen[which] = waitingNow;
      changed = true;
    }
    const ask = autoL.ask[which];
    if (!ask || !ask.cardId || ask.gone) continue;
    const items = (queue && Array.isArray(queue.items)) ? queue.items : [];
    if (items.some((item) => item && item.id === ask.cardId)) continue;
    ask.gone = true;
    setTimeout(async () => {
      if (autoL.ask[which] !== ask) return;
      autoL.at = 0;
      await loadAuto();
      if (autoL.ask[which] === ask) {
        autoL.ask[which] = null;
        const v = autoL.view;
        // Still off: how the card ended, as the PC says it (`*_last`) -
        // never a guess that it was denied (FIXLIST 2, 28).
        if (!(v && v[AUTO_SWITCHES[which].field])) {
          toast((v && lastLineNow(which, v)) || stillOffLine(which), "bad");
        }
        if (state.view === "memory") paintAuto();
      }
    }, MODEL_ASK_GRACE_MS);
  }
  // A withdrawn card that has left the queue is forgotten.
  const ids = new Set(((queue && Array.isArray(queue.items)) ? queue.items : [])
    .map((item) => item && item.id));
  for (const gone of Object.values(autoL.withdrawn)) {
    for (const id of gone) if (!ids.has(id)) gone.delete(id);
  }
  // A card came or went: the line follows the queue at once, and the PC's
  // own `*_waiting` is read again so it does not hold the line up.
  if (changed && state.view === "memory") {
    paintAutoSettings();
    autoL.at = 0;
    loadAuto();
  }
});

// Private answers turned on or off, or a Show ran out: read the list again -
// Rust decides whether it comes back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadAuto = () => {
    autoL.at = 0;
    if (state.view === "memory") loadAuto();
    // The facts "Jarvis remembered N things" opened are a memory list too.
    loadSavedFacts();
  };
  TAURI.event.listen("security-changed", rereadAuto);
  TAURI.event.listen("private-hidden", rereadAuto);
}

// The Brain window is destroyed when it is closed, and a `memory_saved`
// that came while it was closed never reached it. Rust counts them for it
// (brain/auto_learn.rs note_saved), ids only: picked up here when the
// window opens, and cleared when the owner opens the list.
if (IS_TAURI) {
  invoke("brain_memory_saved_unseen", { seen: false }).then((out) => {
    const before = autoL.unseen.size;
    for (const id of savedIds(out)) autoL.unseen.add(id);
    if (autoL.unseen.size !== before) paintSavedLine();
  }).catch(() => {});
}

function autoSwitchNode(which, v) {
  const sw = AUTO_SWITCHES[which];
  const on = v[sw.field] === true;
  // Our own click, or a card raised elsewhere (the phone): the queue says,
  // and so does the PC (`auto_waiting` / `sensitive_waiting`).
  const waiting = !on && Boolean(autoL.ask[which] || v[sw.waitingField] || autoCardWaiting(which));
  const box = el("div", "auto-switch-box");
  const label = el("label", "history-switch auto-switch");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = `memory-${which}-on`;
  input.setAttribute("role", "switch");
  input.setAttribute("aria-describedby", `memory-${which}-detail`);
  input.checked = on;
  label.append(input, el("span", "history-switch-label", sw.label));
  const detail = el("p", "note history-switch-detail", sw.detail);
  detail.id = `memory-${which}-detail`;
  box.append(label, detail);
  if (waiting) {
    // Greyed while its card waits (FIXLIST 8): pressing it again would only
    // ask for the same card. Turning it back OFF is the Cancel button in
    // the waiting line, which withdraws the card (R6).
    input.disabled = true;
    input.title = "A card to turn this on is waiting for your approval.";
  } else if (!on) {
    // Turning it ON waits for a live link (rule 4); OFF never does.
    input.dataset.title = "Asks you first, with an approval card.";
    liveButtons.add(input);
    syncLiveButton(input);
  }
  input.addEventListener("change", async () => {
    const want = input.checked;
    // Show what the PC says, never what was clicked: ON is only a card.
    input.checked = on;
    input.disabled = true;
    input.dataset.busy = "true";
    await setAutoSwitch(which, want);
  });
  // The settings file was damaged, so the PC treats this as off and says
  // why (FIXLIST 1).
  if (which === "auto" && v.fileWhy) {
    box.append(el("p", "history-why-not auto-file-why", v.fileWhy));
  }
  // The sensitive switch does nothing without the first (FIXLIST 3).
  if (which === "sensitive" && !v.auto) {
    box.append(el("p", "hint auto-needs-auto", SENSITIVE_NEEDS_AUTO));
  }
  if (waiting) {
    const line = el("p", "hint learning-waiting history-waiting auto-waiting", sw.waiting(APPROVE_WHERE));
    // OFF, so never held on a stale link.
    line.append(" ", button(CANCEL_LABEL, () => setAutoSwitch(which, false), { title: CANCEL_TITLE }));
    box.append(line);
  } else {
    // How the newest card ended, in the PC's words (FIXLIST 2).
    const words = lastLineNow(which, v);
    if (words) {
      const line = el("p", "hint auto-last", words);
      const last = v[sw.lastField];
      if (last && last.why) line.title = last.why;
      box.append(line);
    }
  }
  return box;
}

function paintAutoSettings() {
  const box = dom.memoryAuto;
  if (!box) return;
  box.replaceChildren();
  const v = autoL.view;
  if (!v) {
    const line = el("p", "empty", autoL.error
      ? `Could not read automatic learning: ${autoL.error}` : "Reading…");
    if (autoL.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadAuto));
    }
    box.append(line);
    return;
  }
  if (!v.switches) {
    box.append(el("p", "empty", v.why));
    return;
  }
  box.append(autoSwitchNode("auto", v), autoSwitchNode("sensitive", v));
  // "Learn automatically" means something only while learning is on. The
  // learning route says; an older PC's answer is the facts list's flag.
  const facts = state.data.memory_facts || {};
  const learning = v.learning ?? (typeof facts.learning === "boolean" ? facts.learning : null);
  if (learning === false && v.auto) {
    box.append(el("p", "history-why-not auto-learning-off", LEARNING_OFF_NOTE));
  }
}

function paintSavedLine() {
  const box = dom.memorySavedLine;
  if (!box) return;
  box.replaceChildren();
  const words = rememberedLine(autoL.unseen.size);
  if (words) {
    const b = el("button", "btn small ghost memory-saved", words);
    b.type = "button";
    b.title = REMEMBERED_LINE_TITLE;
    b.addEventListener("click", openSavedList);
    box.append(b);
  }
  // The facts the line opened, with Forget beside each.
  if (savedFacts.open) box.append(savedFactsNode());
}

function paintAutoList() {
  const box = dom.memoryAutoList;
  if (!box) return;
  box.tabIndex = -1;
  box.replaceChildren();
  const v = autoL.view;
  if (!v) {
    box.append(el("p", "empty", autoL.error
      ? "Nothing to show until automatic learning can be read." : "Reading…"));
    return;
  }
  if (!v.available) {
    // The switches' box already says why when nothing is there at all.
    if (v.switches) box.append(el("p", "empty", AUTO_MISSING));
    return;
  }
  if (autoL.listError) {
    const line = el("p", "empty failed", `Could not read what was saved automatically: ${autoL.listError}`);
    line.append(" ", button("Retry", loadAuto));
    box.append(line);
    return;
  }
  if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount, "facts"));
    return;
  }
  if (!autoL.rows.length) {
    box.append(el("p", "empty", v.auto ? AUTO_EMPTY : `${AUTO_EMPTY} ${AUTO_OFF}`));
    return;
  }
  const past = memoryAsOf !== null;
  const list = el("div", "rows auto-rows");
  for (const f of autoL.rows) {
    const item = row({
      tag: "auto",
      state: "ok",
      title: f.text || "(no text)",
      meta: [factMeta(f)],
      // Nothing is changed while the pane shows a past moment (memoryWrite).
      actions: past ? [] : [
        ...[pinButton(f)].filter(Boolean),
        button("Forget", () => forgetAuto(f),
          { danger: true, live: true, title: "Stop this being recalled. There is no undo." }),
        button(ERASE_LABEL, () => eraseFact(f),
          { danger: true, live: true, title: ERASE_TITLE }),
      ],
    });
    item.dataset.id = String(f.id);
    if (!past) withLinks(item, f);
    if (f.provenance === "voice") {
      const marks = el("span", "history-marks");
      const mic = el("span", "history-mark history-mark-voice", VOICE_MARK);
      mic.title = VOICE_TITLE;
      marks.append(mic);
      const main = item.querySelector(".row-main");
      (main || item).append(marks);
    }
    list.append(item);
  }
  box.append(list);
  if (autoL.more) {
    const more = el("div", "row-actions history-more");
    more.append(button(autoL.older ? "Loading…" : "Load older", loadOlderAuto,
      { title: "Show the next page of older facts saved automatically." }));
    box.append(more);
  }
}

function paintAuto() {
  paintAutoSettings();
  paintSavedLine();
  paintAutoList();
}

function renderAuto() {
  paintAuto();
  if (IS_TAURI && !autoL.loading && Date.now() - autoL.at > AUTO_READ_MS) loadAuto();
}

/* ==========================================================================
   "Always keep in mind" (the owner's decision, 2026-09-24; memory-profile.js)

   A short list of facts the owner pins, which Jarvis reads with every
   question, word for word. Its own section, with how many of the list's
   1,200 characters are used and an Unpin on each; a Pin / Unpin on every
   fact still in use in "Saved automatically" and "What Jarvis knows about
   you". One fact per call (brain_memory_pin), no card - the owner's own
   tap, like Forget - held on a stale link in Rust and greyed here. No
   event: the list is read again after every memory write, and when the
   Memory tab is shown.
   ========================================================================== */

const profileL = {
  /** readProfile() of the last read, or null before the first. */
  view: null,
  error: "",
  loading: false,
  again: false,
  at: 0,
};
const PROFILE_READ_MS = 15000;

async function loadProfile() {
  if (!IS_TAURI) return;
  if (profileL.loading) {
    profileL.again = true;
    return;
  }
  profileL.loading = true;
  try {
    profileL.view = readProfile(await invoke("brain_memory_profile"));
    profileL.error = "";
  } catch (error) {
    profileL.error = errorText(error);
  } finally {
    profileL.loading = false;
    profileL.at = Date.now();
  }
  if (profileL.again) {
    profileL.again = false;
    await loadProfile();
    return;
  }
  if (state.view === "memory") {
    // The Pin / Unpin on the fact lists follow the list.
    paintProfile();
    paintAutoList();
    renderFacts();
  }
}

/** Pin or Unpin for one fact, by what the PC last said - or nothing while
 *  that is not known (not read yet, an older PC, or the list hidden). */
function pinButton(f) {
  const v = profileL.view;
  if (!v || !v.available || v.hidden || !Number.isInteger(Number(f.id))) return null;
  const on = isPinned(v, f.id);
  return button(on ? UNPIN_LABEL : PIN_LABEL, () => setPinned(f, !on),
    { live: true, title: on ? UNPIN_TITLE : PIN_TITLE });
}

/** One fact on or off the list. memoryWrite shows the PC's refusal in its
 *  own words ("That would make the list too long - unpin something first")
 *  and reads the pane again, this list included. */
async function setPinned(f, on) {
  return memoryWrite("brain_memory_pin", { id: Number(f.id), pinned: on },
    on ? PINNED : UNPINNED);
}

function paintProfile() {
  const box = dom.memoryProfile;
  if (!box) return;
  box.replaceChildren();
  const v = profileL.view;
  if (!v) {
    const line = el("p", "empty", profileL.error
      ? `Could not read the list: ${profileL.error}` : "Reading…");
    if (profileL.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadProfile));
    }
    box.append(line);
    return;
  }
  if (!v.available) {
    box.append(el("p", "empty", v.why || PROFILE_MISSING));
    return;
  }
  if (v.hidden) {
    box.append(hiddenNode(v.hiddenCount, "facts"));
    return;
  }
  box.append(el("p", "hint profile-used", usedLine(v.chars, v.limit)));
  if (profileL.error) {
    box.append(el("p", "empty failed", `Could not read it again: ${profileL.error}`));
  }
  if (!v.facts.length) {
    box.append(el("p", "empty", PROFILE_EMPTY));
    return;
  }
  // Nothing is changed while the pane shows a past moment (memoryWrite).
  const past = memoryAsOf !== null;
  const list = el("div", "rows profile-rows");
  for (const f of v.facts) {
    const item = row({
      tag: "pinned",
      state: "ok",
      title: f.text || "(no text)",
      meta: [f.added ? `pinned ${ago(f.added)}` : ""],
      actions: past ? [] : [
        button(UNPIN_LABEL, () => setPinned(f, false), { live: true, title: UNPIN_TITLE }),
      ],
    });
    item.dataset.id = String(f.id);
    list.append(item);
  }
  box.append(list);
}

function renderProfile() {
  paintProfile();
  if (IS_TAURI && !profileL.loading && Date.now() - profileL.at > PROFILE_READ_MS) loadProfile();
}

// Private answers turned on or off, or a Show ran out: read it again - Rust
// decides whether it comes back hidden.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadProfile = () => {
    profileL.at = 0;
    if (state.view === "memory") loadProfile();
  };
  TAURI.event.listen("security-changed", rereadProfile);
  TAURI.event.listen("private-hidden", rereadProfile);
}

/**
 * When a fact became true, in words: "true from 1 January 2021" when that is
 * more than a day away from when Jarvis learned it (the owner's words gave a
 * date, or history was recorded), else "saved 3 h ago" / "saved 12 Sept
 * 2026". This used to be a bare `ago(valid_from)` - "2825d ago" on a fact
 * true since 2019, with nothing saying what the number was (the memory
 * review's I10).
 */
function whenTrue(f) {
  const learned = Number(f.created);
  const from = Number(f.valid_from);
  const has = (v) => Number.isFinite(v) && v > 0;
  if (has(from) && (!has(learned) || Math.abs(learned - from) >= 86400)) {
    const day = plainDateOf(from);
    return day ? `${MEMORY_WORDS.true_from} ${day}` : "";
  }
  const saved = whenWords(has(learned) ? learned : from);
  return saved ? `saved ${saved}` : "";
}

/** "learned 12 September 2026" only when that differs from when the fact
 *  became true.
 *
 * valid_from and created are stamped together for anything typed or accepted
 * in the moment, so saying both every time would be noise on every row. A gap
 * of more than a day means someone recorded history, and that is worth a line.
 */
function whenLearned(f) {
  const learned = Number(f.created);
  const from = Number(f.valid_from);
  if (!Number.isFinite(learned) || !Number.isFinite(from)) return "";
  if (Math.abs(learned - from) < 86400) return "";
  const day = plainDateOf(learned);
  return day ? `learned ${day}` : "";
}

/** The same gap at the other end: stopped being true then, found out later.
 *
 * "I moved in January" told in March gives valid_to = January and
 * retired_at = March. Facts retired before the retired_at column existed have
 * it backfilled equal to valid_to, so they correctly say nothing here.
 */
function whenNoticed(f) {
  const until = Number(f.valid_to);
  const noticed = Number(f.retired_at);
  if (!Number.isFinite(until) || !Number.isFinite(noticed)) return "";
  if (Math.abs(noticed - until) < 86400) return "";
  const a = plainDateOf(until);
  const b = plainDateOf(noticed);
  return a && b ? `true until ${a}, noticed ${b}` : "";
}

/** A review card's reason and older-news lines, whichever there are. */
function reasonLines(p) {
  const { reason, older } = cardLines(p);
  return [reason || "", older || ""];
}

/* ==========================================================================
   Work
   ========================================================================== */

/* ==========================================================================
   Focus session (the owner's decision of 2026-09-25; JARVIS-API.md section
   26; focus.js, brain/focus.rs).

   Start one (minutes, and optionally what it is on), then the countdown -
   counted down here once a second from what the PC last said - the PC's own
   line, the drift count, and Pause / Resume, +10 minutes and Stop: ONE
   thing per tap, no card. Start, Resume and +10 minutes are held on a stale
   link (greyed here, refused in Rust); Pause and Stop are not. After a
   session, its report card. The PC never sends what was in front. The
   `focus` event (a state word, or a callout's number) reads it again.
   ========================================================================== */

const fx = { view: null, error: "", loading: false, again: false, at: 0, readAt: 0, timer: null };
const FOCUS_READ_MS = 15000;

async function loadFocus() {
  if (!IS_TAURI) return;
  if (fx.loading) {
    fx.again = true;
    return;
  }
  fx.loading = true;
  try {
    fx.view = readFocus(await invoke("focus_status"));
    fx.error = "";
    fx.readAt = Date.now();
  } catch (error) {
    fx.error = errorText(error);
  } finally {
    fx.loading = false;
    fx.at = Date.now();
  }
  if (fx.again) {
    fx.again = false;
    await loadFocus();
    return;
  }
  if (state.view === "work") paintFocus();
}

async function focusAct(action) {
  try {
    const out = await invoke("focus_act", { action, minutes: null });
    toast(String((out && out.said) || "Done."), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadFocus();
}

async function focusStart() {
  const minutes = focusMinutesOf(dom.focusMinutes && dom.focusMinutes.value);
  if (minutes === null) {
    toast(FOCUS_BAD_MINUTES, "bad");
    return;
  }
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  try {
    const out = await invoke("focus_start", { minutes, on: dom.focusOn ? dom.focusOn.value : "" });
    toast(String((out && out.said) || "Started."), "ok");
    if (dom.focusOn) dom.focusOn.value = "";
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadFocus();
}

function focusTick() {
  if (state.view !== "work" || !fx.view || !fx.view.on || fx.view.paused) return;
  const clockNode = dom.focus && dom.focus.querySelector(".focus-clock");
  if (!clockNode) return;
  const left = focusLeftNow(fx.view, Date.now() - fx.readAt);
  clockNode.textContent = focusClock(left);
  // The PC says when it ended; read again once the count reaches zero.
  if (left <= 0 && !fx.loading && Date.now() - fx.at > 2000) loadFocus();
}

function paintFocus() {
  const box = dom.focus;
  if (!box) return;
  const v = fx.view;
  if (dom.focusReport) dom.focusReport.replaceChildren();
  if (!v) {
    const line = el("p", "empty", fx.error ? `Could not read the focus session: ${fx.error}` : "Reading…");
    if (fx.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadFocus));
    }
    box.replaceChildren(line);
    if (dom.focusForm) dom.focusForm.hidden = true;
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why || FOCUS_MISSING));
    if (dom.focusForm) dom.focusForm.hidden = true;
    return;
  }
  if (dom.focusForm) dom.focusForm.hidden = v.on;
  if (!v.on) {
    box.replaceChildren(el("p", "empty", v.line || "No focus session."));
    if (v.report && dom.focusReport) {
      const card = el("div", "focus-report");
      card.append(el("h3", "subhead", FOCUS_LAST_TITLE));
      const title = el("p", "focus-report-title", v.report.title);
      if (v.report.clean) title.dataset.state = "ok";
      card.append(title);
      for (const line of v.report.lines) card.append(el("p", "note", line));
      dom.focusReport.replaceChildren(card);
    }
  } else {
    const wrap = el("div", "focus-now");
    wrap.dataset.tone = focusToneOf(v);
    wrap.append(el("span", "focus-clock mono", focusClock(focusLeftNow(v, Date.now() - fx.readAt))));
    if (v.intent) wrap.append(el("p", "note", `On: ${v.intent}`));
    else if (v.intentHidden) wrap.append(el("p", "note", FOCUS_INTENT_HIDDEN));
    wrap.append(el("p", "focus-line", v.line));
    wrap.append(el("p", "note", driftWords(v.drifts)));
    if (v.note) wrap.append(el("p", "note", v.note));
    const actions = el("div", "row-actions");
    for (const a of focusActionsOf(v, "brain")) {
      actions.append(button(FOCUS_LABELS[a], () => focusAct(a),
        { live: a === "resume" || a === "extend", danger: a === "stop" }));
    }
    wrap.append(actions);
    box.replaceChildren(wrap);
  }
  if (fx.error) box.prepend(el("p", "empty failed", `Could not read it again: ${fx.error}`));
  const ticking = v.on && !v.paused;
  if (ticking && !fx.timer) fx.timer = setInterval(focusTick, 1000);
  if (!ticking && fx.timer) {
    clearInterval(fx.timer);
    fx.timer = null;
  }
}

function renderFocus() {
  paintFocus();
  if (IS_TAURI && !fx.loading && Date.now() - fx.at > FOCUS_READ_MS) loadFocus();
}

if (dom.focusForm) {
  dom.focusForm.addEventListener("submit", (event) => {
    event.preventDefault();
    focusStart();
  });
}
if (dom.focusStart) {
  liveButtons.add(dom.focusStart);
  syncLiveButton(dom.focusStart);
}

/* ==========================================================================
   Coming up - timers, alarms, reminders and the to-do list (the owner's
   decisions of 2026-09-25; JARVIS-API.md section 21; coming-up.js).

   Read through its own command (brain/schedule.rs), not brain_read: while
   the private lists are hidden Rust takes the words out. Every change is
   ONE job (Pause / Resume / Delete / Done) or one new to-do item, held on a
   stale link, with no card - none of them can make Jarvis do more. There is
   no "delete all". The `schedule` event (ids and the kind only) reads the
   list again; a running timer counts down here once a second from what the
   PC last said.
   ========================================================================== */

const upL = { view: null, error: "", loading: false, again: false, at: 0, readAt: 0 };
const SCHEDULE_READ_MS = 15000;
/** id -> {span, job} for the countdowns the ticker repaints. */
const ticking = new Map();
let tickTimer = null;

async function loadComingUp() {
  if (!IS_TAURI) return;
  if (upL.loading) {
    upL.again = true;
    return;
  }
  upL.loading = true;
  try {
    upL.view = readSchedule(await invoke("brain_schedule"));
    upL.error = "";
    upL.readAt = Date.now();
  } catch (error) {
    upL.error = errorText(error);
  } finally {
    upL.loading = false;
    upL.at = Date.now();
  }
  if (upL.again) {
    upL.again = false;
    await loadComingUp();
    return;
  }
  if (state.view === "work") paintComingUp();
}

async function scheduleAct(job, action) {
  try {
    // Snooze says how long (10 minutes), so the PC and this button agree.
    const args = action === "snooze" ? { id: job.id, action, seconds: SNOOZE_SECONDS }
      : { id: job.id, action };
    const out = await invoke("brain_schedule_act", args);
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else toast(String((out && out.said) || "Done."), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

/**
 * One new item, on the to-do list or (with `list`) a named list - the
 * list's own Add box. Held on a stale link.
 */
async function addTodo(input = dom.todoText, list = null, title = "To-do list") {
  const words = input ? input.value.trim() : "";
  if (!words) return;
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  const where = title.charAt(0).toLowerCase() + title.slice(1);
  try {
    const out = await invoke("brain_schedule_add_todo", list ? { text: words, list } : { text: words });
    if (out && out.ok === false) {
      toast(String(out.error || "Refused."), "bad");
    } else {
      toast(out && out.job && out.job.already ? `That is already on your ${where}.`
        : `Added to your ${where}.`, "ok");
      input.value = "";
    }
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

/**
 * "Clear list" under a NAMED list: "are you sure?" first, like Forget, then
 * ONE request naming the list and how many items this page showed - the PC
 * clears nothing if that number is no longer right. Held on a stale link.
 */
async function clearList(l) {
  if (!window.confirm(clearListQuestion(l.title, l.items.length))) return;
  try {
    const out = await invoke("brain_schedule_clear_list", { list: l.name, count: l.items.length });
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else toast(String((out && out.said) || "Cleared."), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

/** Something that went off in the last hour: its words, when, and Snooze. */
function wentOffRow(job) {
  const item = row({
    tag: tagOf(job),
    state: "warn",
    title: titleOf(job),
    meta: wentOffMeta(job),
    actions: WENT_OFF_ACTIONS.map((a) =>
      button(labelOf(a), () => scheduleAct(job, a), { live: true })),
  });
  item.dataset.id = job.id;
  return item;
}

/**
 * The named lists, each under its own heading: its items (Done / Delete),
 * an Add box, and Clear list. While the private lists are hidden the names
 * and words are gone (Rust took them out) and nothing is offered but Show.
 */
function paintNamedLists(v) {
  const box = dom.namedLists;
  if (!box) return;
  const out = [];
  for (const l of namedLists(v)) {
    const part = el("div", "named-list");
    part.dataset.list = l.name;
    part.append(el("h3", "subhead", l.title));
    const list = el("div", "rows");
    for (const j of l.items) list.append(scheduleRow(j));
    part.append(list);
    if (!v.hidden) {
      const form = el("form", "todo-form");
      form.autocomplete = "off";
      const input = el("input", "field todo-text");
      input.type = "text";
      input.maxLength = 300;
      input.placeholder = addPlaceholder(l.title);
      input.setAttribute("aria-label", addPlaceholder(l.title));
      const add = el("button", "btn small", "Add");
      add.type = "submit";
      liveButtons.add(add);
      syncLiveButton(add);
      form.append(input, add);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        addTodo(input, l.name, l.title);
      });
      part.append(form);
      const actions = el("div", "row");
      actions.append(button(CLEAR_LIST_LABEL, () => clearList(l), { live: true, danger: true }));
      part.append(actions);
    }
    out.push(part);
  }
  box.replaceChildren(...out);
}

/**
 * The standby schedule: two times, set up at once on the PC with no card
 * (since 2026-09-26; the PC's answer says the next night). It then sits in
 * the list above like any repeating job. Held on a stale link, like every
 * change here; Rust refuses it too.
 */
async function addStandby() {
  const times = standbyTimes(dom.standbyStart && dom.standbyStart.value,
    dom.standbyEnd && dom.standbyEnd.value);
  if (!times) {
    toast(STANDBY_BAD_TIMES, "bad");
    return;
  }
  if (!linkWords(currentLink()).canAct) {
    toast(STALE_TITLE, "bad");
    return;
  }
  try {
    const out = await invoke("brain_schedule_add_standby", { start: times.at, end: times.until });
    if (out && out.ok === false) toast(String(out.error || "Refused."), "bad");
    else toast(String((out && out.said) || "Done."), "ok");
  } catch (error) {
    toast(errorText(error), "bad");
  }
  await loadComingUp();
}

function scheduleRow(job) {
  const since = Date.now() - upL.readAt;
  const item = row({
    tag: tagOf(job),
    state: job.state === "waiting" ? "warn" : job.state === "paused" ? "" : "ok",
    title: titleOf(job),
    meta: metaOf(job, since),
    actions: actionsOf(job).map((a) =>
      button(labelOf(a), () => scheduleAct(job, a), { live: true, danger: a === "delete" })),
  });
  item.dataset.id = job.id;
  if (job.kind === "timer" && job.state === "active") {
    const span = item.querySelector(".row-meta");
    if (span) {
      span.classList.add("countdown");
      ticking.set(job.id, { span, job });
    }
  }
  return item;
}

function tick() {
  if (state.view !== "work" || !ticking.size) return;
  const since = Date.now() - upL.readAt;
  let finished = false;
  for (const [id, { span, job }] of ticking) {
    if (!span.isConnected) {
      ticking.delete(id);
      continue;
    }
    span.textContent = metaOf(job, since)[0] || "";
    if (job.left !== null && job.left - since / 1000 <= 0) finished = true;
  }
  // The PC says when it went off; read again once the count reaches zero.
  if (finished && !upL.loading && Date.now() - upL.at > 2000) loadComingUp();
}

function paintComingUp() {
  const box = dom.comingUp;
  if (!box) return;
  ticking.clear();
  const v = upL.view;
  if (!v) {
    const line = el("p", "empty", upL.error ? `Could not read Coming up: ${upL.error}` : "Reading…");
    if (upL.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadComingUp));
    }
    box.replaceChildren(line);
    if (dom.todoList) dom.todoList.replaceChildren();
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why || SCHEDULE_MISSING));
    if (dom.todoList) dom.todoList.replaceChildren();
    if (dom.namedLists) dom.namedLists.replaceChildren();
    if (dom.wentOffPart) dom.wentOffPart.hidden = true;
    if (dom.listsNote) dom.listsNote.hidden = true;
    if (dom.todoForm) dom.todoForm.hidden = true;
    if (dom.standbyForm) dom.standbyForm.hidden = true;
    if (dom.standbyIsSet) dom.standbyIsSet.hidden = true;
    return;
  }
  if (dom.todoForm) dom.todoForm.hidden = false;
  // One standby schedule at most: the form while there is none, a pointer
  // to its row while there is.
  const hasStandby = Boolean(standbyOf(v));
  if (dom.standbyForm) dom.standbyForm.hidden = hasStandby;
  if (dom.standbyIsSet) dom.standbyIsSet.hidden = !hasStandby;
  rows(box, v.jobs, scheduleRow, EMPTY_JOBS);
  if (upL.error) box.prepend(el("p", "empty failed", `Could not read it again: ${upL.error}`));
  // Just went off (the last hour): Snooze, ONE job per tap.
  if (dom.wentOffPart) dom.wentOffPart.hidden = !v.wentOff.length;
  if (dom.wentOff) rows(dom.wentOff, v.wentOff, wentOffRow, "");
  if (dom.todoList) rows(dom.todoList, todoItems(v), scheduleRow, EMPTY_TODO);
  paintNamedLists(v);
  // Its example says "milk": nothing of that shape shows while hidden.
  if (dom.listsNote) dom.listsNote.hidden = v.hidden;
  if (v.hidden) {
    box.append(hiddenNode(0, "words"));
  }
  if (anyTicking(v) && !tickTimer) tickTimer = setInterval(tick, 1000);
  if (!anyTicking(v) && tickTimer) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
}

function renderComingUp() {
  paintComingUp();
  if (IS_TAURI && !upL.loading && Date.now() - upL.at > SCHEDULE_READ_MS) loadComingUp();
}

if (dom.todoForm) {
  dom.todoForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addTodo();
  });
}
if (dom.todoAdd) {
  liveButtons.add(dom.todoAdd);
  syncLiveButton(dom.todoAdd);
}
if (dom.standbyForm) {
  dom.standbyForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addStandby();
  });
}
if (dom.standbyAdd) {
  liveButtons.add(dom.standbyAdd);
  syncLiveButton(dom.standbyAdd);
}

// Private answers turned on or off, or a Show ran out: read it again - Rust
// decides whether the words come back.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadSchedule = () => {
    upL.at = 0;
    if (state.view === "work") loadComingUp();
  };
  TAURI.event.listen("security-changed", rereadSchedule);
  TAURI.event.listen("private-hidden", rereadSchedule);
  // The deep questions are hidden with the lists too (commands.rs get_deep).
  const rereadDeep = () => {
    deep.at = 0;
    if (state.view === "memory") loadDeep();
  };
  TAURI.event.listen("security-changed", rereadDeep);
  TAURI.event.listen("private-hidden", rereadDeep);
  // And what a focus session is on (brain/focus.rs hide_intent).
  const rereadFocus = () => {
    fx.at = 0;
    if (state.view === "work") loadFocus();
  };
  TAURI.event.listen("security-changed", rereadFocus);
  TAURI.event.listen("private-hidden", rereadFocus);
}

/* ==========================================================================
   Morning briefing (the owner's decisions of 2026-09-25; JARVIS-API.md
   section 22; briefing.js).

   The latest briefing, read through its own command (brain/briefing.rs), so
   while the private lists are hidden Rust takes every line out and only the
   counts reach this page. "Brief me now" only READS - the PC puts one
   together without the model - so, like every read, it is not held on a
   stale link. When it arrives each morning is set in Settings. The
   `schedule` event with kind "briefing" (ids only) reads it again; the
   toast is Rust's (toast_ready), with the fixed words only.
   ========================================================================== */

const brief = { view: null, error: "", loading: false, at: 0, asking: false, missedAsking: false };
const BRIEFING_READ_MS = 15000;

async function loadBriefing() {
  if (!IS_TAURI || brief.loading) return;
  brief.loading = true;
  try {
    brief.view = readBriefing(await invoke("brain_briefing"));
    brief.error = "";
  } catch (error) {
    brief.error = errorText(error);
  } finally {
    brief.loading = false;
    brief.at = Date.now();
  }
  if (state.view === "work") paintBriefing();
}

/**
 * "What did I miss?": the briefing's builder since the owner last talked to
 * Jarvis. A read, like "Brief me now" - not held on a stale link. Shown in
 * place of the briefing until the next read; the PC keeps nothing of it.
 */
async function briefMissed() {
  if (brief.asking) return;
  brief.asking = true;
  brief.missedAsking = true;
  paintBriefing();
  try {
    const v = readMissed(await invoke("brain_briefing_now", { missed: true }));
    if (v) {
      brief.view = { ...(brief.view || v), ...v, setups: (brief.view && brief.view.setups) || v.setups };
      brief.error = "";
    } else {
      toast(MISSED_MISSING, "bad");
    }
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    brief.asking = false;
    brief.missedAsking = false;
    brief.at = Date.now();
  }
  paintBriefing();
}

async function briefNow() {
  if (brief.asking) return;
  brief.asking = true;
  paintBriefing();
  try {
    brief.view = readBriefing(await invoke("brain_briefing_now"));
    brief.error = "";
  } catch (error) {
    toast(errorText(error), "bad");
  } finally {
    brief.asking = false;
    brief.at = Date.now();
  }
  paintBriefing();
}

function paintBriefing() {
  const box = dom.briefing;
  if (!box) return;
  if (dom.briefingNow) {
    dom.briefingNow.disabled = brief.asking;
    dom.briefingNow.textContent = brief.asking && !brief.missedAsking ? BRIEFING_NOW_BUSY
      : BRIEFING_NOW_LABEL;
  }
  if (dom.briefingMissed) {
    dom.briefingMissed.disabled = brief.asking;
    dom.briefingMissed.textContent = brief.missedAsking ? MISSED_BUSY : MISSED_LABEL;
  }
  const v = brief.view;
  if (!v) {
    const line = el("p", "empty", brief.error ? `Could not read the briefing: ${brief.error}` : "Reading…");
    if (brief.error) {
      line.classList.add("failed");
      line.append(" ", button("Retry", loadBriefing));
    }
    box.replaceChildren(line);
    return;
  }
  if (!v.available) {
    box.replaceChildren(el("p", "empty", v.why));
    if (dom.briefingNow) dom.briefingNow.hidden = true;
    if (dom.briefingMissed) dom.briefingMissed.hidden = true;
    return;
  }
  if (dom.briefingNow) dom.briefingNow.hidden = false;
  if (dom.briefingMissed) dom.briefingMissed.hidden = false;
  const b = v.briefing;
  const out = [];
  if (v.building || (brief.asking && !brief.missedAsking)) out.push(el("p", "empty", BRIEFING_BUILDING));
  if (!b) {
    if (!v.building && !brief.asking) out.push(el("p", "empty", BRIEFING_EMPTY));
    box.replaceChildren(...out);
    return;
  }
  out.push(el("p", "briefing-heading", b.heading));
  const late = lateLine(b);
  if (late) out.push(el("p", "empty", late));
  const list = el("div", "rows");
  for (const s of b.sections) {
    list.append(row({
      tag: s.title,
      state: s.state === "ok" ? "ok" : s.state === "empty" ? "" : "warn",
      title: s.summary,
      meta: b.hidden ? [] : s.items,
    }));
  }
  out.push(list);
  const missed = b.source === "missed";
  // "What did I miss?" fetches nothing from the internet and is not kept.
  // The last line is the PC's own (the weather from Home Assistant, or not).
  if (!missed) out.push(el("p", "note", briefingOutsideLine(b)));
  for (const n of b.notIncluded) out.push(el("p", "note", n));
  if (b.hidden) out.push(hiddenNode(0, "lines"));
  out.push(el("p", "note", missed ? MISSED_DETAIL : BRIEFING_KEPT));
  box.replaceChildren(...out);
}

function renderBriefing() {
  paintBriefing();
  if (IS_TAURI && !brief.loading && Date.now() - brief.at > BRIEFING_READ_MS) loadBriefing();
}

if (dom.briefingNow) dom.briefingNow.addEventListener("click", briefNow);
if (dom.briefingMissed) dom.briefingMissed.addEventListener("click", briefMissed);

// Hiding turned on or off, or a Show ran out: read it again - Rust decides
// whether the lines come back.
if (IS_TAURI && TAURI.event && TAURI.event.listen) {
  const rereadBriefing = () => {
    brief.at = 0;
    if (state.view === "work") loadBriefing();
  };
  TAURI.event.listen("security-changed", rereadBriefing);
  TAURI.event.listen("private-hidden", rereadBriefing);
}

function renderJobs() {
  const body = state.data.jobs || {};
  const why = unavailable("jobs");
  if (why) return rows(dom.jobs, [], null, whyNode("jobs"));
  const list = Array.isArray(body.jobs) ? body.jobs : [];

  rows(
    dom.jobs,
    list,
    (j) => {
      const jobState = String(j.state || "queued");
      const live = jobState === "running" || jobState === "queued";
      // Either set of names: this window's (caps, tainted, created) or the
      // phone's (capabilities, private, progress). jarvis_jobs.py is only on
      // the owner's PC, so both apps read both.
      const caps = Array.isArray(j.caps) && j.caps.length ? j.caps
        : Array.isArray(j.capabilities) ? j.capabilities : [];
      const progress = typeof j.progress === "number" ? `${Math.round(j.progress * 100)}% done` : "";
      return row({
        tag: jobState,
        state: jobState,
        title: String(j.label || j.handler || j.id || "(job)"),
        meta: [
          // The frozen capability set, shown because it is the promise: it was
          // fixed when the job was created and it cannot grow.
          caps.length ? `frozen capabilities: ${caps.join(", ")}` : "no capabilities",
          j.tainted ? "tainted — this job read private data and stays local" : "",
          j.private ? "private — the phone is not shown what this is working on" : "",
          [ago(j.created), j.result_summary || j.error || "", progress].filter(Boolean).join(" · "),
        ],
        actions: live
          ? [
              button(
                "Cancel",
                async () => {
                  if (
                    !confirm(
                      `Cancel "${j.label || j.id}"?\n\n` +
                        "Cancelling works mid-step and a cancelled job is not " +
                        "resumable — it starts again from the beginning or not at all."
                    )
                  ) {
                    return;
                  }
                  try {
                    await invoke("brain_cancel_job", { id: String(j.id) });
                    toast("Cancelled.", "ok");
                    await load(["jobs"], { quiet: true });
                    render("work");
                  } catch (error) {
                    toast(String((error && error.message) || error), "bad");
                  }
                },
                { danger: true }
              ),
            ]
          : [],
      });
    },
    "No background jobs."
  );
}

function renderUndo() {
  const body = state.data.undo || {};
  const why = unavailable("undo");
  if (why) return rows(dom.undo, [], null, whyNode("undo"));
  const shelf = Array.isArray(body.shelf) ? body.shelf : [];

  rows(
    dom.undo,
    shelf,
    (e) => {
      // Either set of names: this window's (action/kind, revertible, ts) or
      // the phone's (label/what, reversible, at_ms). jarvis_undo.py is only on
      // the owner's PC, so both apps read both.
      const revertible = e.revertible === true || e.reversible === true;
      const when = e.ts ?? (Number(e.at_ms) > 0 ? Number(e.at_ms) / 1000 : undefined);
      const actions = [];
      if (revertible) {
        actions.push(
          button("Put it back", async () => {
            try {
              await invoke("brain_revert_undo", { id: String(e.id) });
              toast("Reverted.", "ok");
              await load(["undo"], { quiet: true });
              render("work");
            } catch (error) {
              toast(String((error && error.message) || error), "bad");
            }
          })
        );
      }
      // A hold is a message inside its send window: cancellable now, gone in a
      // moment, and never unsendable afterwards.
      if (e.category === "hold" && e.detail && e.detail.handle) {
        actions.push(
          button(
            "Stop sending",
            async () => {
              try {
                await invoke("brain_cancel_hold", { handle: String(e.detail.handle) });
                toast("Stopped before it went.", "ok");
                await load(["undo"], { quiet: true });
                render("work");
              } catch (error) {
                const message = String((error && error.message) || error);
                toast(
                  /409/.test(message)
                    ? "That one has already gone — there is no unsend."
                    : message,
                  "bad"
                );
              }
            },
            { danger: true }
          )
        );
      }
      // A hold inside its send window is the one entry that is neither
      // revertible nor final: it has not happened yet. Tagging it "final" next
      // to a live "Stop sending" button made the tag contradict the action.
      const holding = e.category === "hold" && e.detail && e.detail.handle;
      return row({
        tag: holding ? "holding" : revertible ? "revertible" : "final",
        state: holding ? "warn" : revertible ? "ok" : "bad",
        title: String(e.action || e.kind || e.label || e.what || "(action)"),
        meta: [
          e.target || "",
          holding
            ? e.reason || "still inside its send window — it can still be stopped"
            : revertible
              ? ""
              : e.reason || "cannot be undone",
          [ago(when), e.before_bytes ? `${bytes(e.before_bytes)} held` : ""]
            .filter(Boolean)
            .join(" · "),
        ],
        actions,
      });
    },
    "Nothing on the shelf."
  );
}

/* ==========================================================================
   Trust
   ========================================================================== */

function renderContentRisk() {
  const body = state.data.content_risk || {};
  const why = unavailable("content_risk");
  dom.contentRisk.replaceChildren();
  if (why) return dom.contentRisk.append(whyNode("content_risk"));

  const rush = body.rush;
  const banner = el(
    "div",
    "row-item",
    ""
  );
  banner.replaceChildren();
  const tag = el("span", "row-tag", rush ? "latched" : "clear");
  tag.dataset.state = rush ? "bad" : "ok";
  banner.append(tag);
  const main = el("div", "row-main");
  if (rush) {
    main.append(
      el(
        "span",
        "row-title",
        "A rush latch is active — outside text tried to hurry a decision."
      )
    );
    // The attacker's own words, quoted, because showing them is the point.
    const said = rush.phrase || rush.quote; // either name, as in the rush strip
    if (said) main.append(el("span", "row-meta", `“${said}”`));
    if (rush.source) main.append(el("span", "row-meta", `from ${rush.source}`));
    main.append(
      el(
        "span",
        "row-meta",
        "It expires on its own. There is deliberately no control here that clears it."
      )
    );
  } else {
    main.append(el("span", "row-title", "No rush latch active."));
  }
  banner.append(main, el("div", "row-actions"));
  const wrap = el("div", "rows");
  wrap.append(banner);
  dom.contentRisk.append(wrap);

  const pins = Array.isArray(body.pins) ? body.pins : [];
  dom.contentRisk.append(el("h3", "inspector-sub", "Pinned text"));
  const pinBox = el("div");
  rows(
    pinBox,
    pins,
    (p) =>
      row({
        tag: "pinned",
        state: "ok",
        title: String(p.name || p.source || "(pinned)"),
        meta: [p.kind || "", p.at ? ago(p.at) : "", p.digest ? `digest ${String(p.digest).slice(0, 12)}` : ""],
        actions: [],
      }),
    "Nothing pinned. A skill or MCP tool description is pinned when a person has read its full current text."
  );
  dom.contentRisk.append(pinBox);
}

function renderLedger() {
  const body = state.data.ledger || {};
  const why = unavailable("ledger");
  dom.ledger.replaceChildren();
  if (why) return dom.ledger.append(whyNode("ledger"));

  const dl = el("dl", "kv");
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dl.append(el("dt", "", k), el("dd", "", v));
  };
  add("Entries", body.entries);
  add("Head", body.head ? String(body.head).slice(0, 20) + "…" : "");
  add("Head sequence", body.head_seq);
  add("Last entry", body.head_ts ? ago(body.head_ts) : "");
  add("With payload", body.with_payload);
  add("Metadata only", body.no_payload);
  add("Redacted", body.redacted);
  add("Expired", body.expired);
  dom.ledger.append(dl);

  const anchors = Array.isArray(body.anchors) ? body.anchors : [];
  dom.ledger.append(el("h3", "inspector-sub", "Anchors"));
  const box = el("div");
  rows(
    box,
    anchors.slice(-8).reverse(),
    (a) =>
      row({
        tag: a.mac_ok ? "verified" : "unverified",
        state: a.mac_ok ? "ok" : "bad",
        title: `seq ${a.seq ?? "—"}`,
        meta: [a.hash ? String(a.hash).slice(0, 24) + "…" : "", a.ts ? ago(a.ts) : ""],
        actions: [],
      }),
    "No anchors written yet."
  );
  dom.ledger.append(box);
}

/* ==========================================================================
   Watch
   ========================================================================== */

function renderWatch() {
  const body = state.data.watch || {};
  const why = unavailable("watch");
  if (why) return rows(dom.watch, [], null, whyNode("watch"));

  const head = el("p", "note");
  head.textContent = [
    `${body.topics ?? 0} topics · ${body.tracking ?? 0} repositories known`,
    body.rate_limit || "",
  ]
    .filter(Boolean)
    .join(" · ");

  const list = Array.isArray(body.list) ? body.list : [];
  const box = el("div");
  rows(
    box,
    list,
    (t) =>
      row({
        tag: t.error ? "error" : "watching",
        state: t.error ? "bad" : "ok",
        title: String(t.name || ""),
        meta: [
          t.query && t.query !== t.name ? `query: ${t.query}` : "",
          t.error ? String(t.error) : "",
          [t.checked ? `checked ${ago(t.checked)}` : "never checked",
           t.notify ? "notify on" : "notify off"].join(" · "),
        ],
        actions: [
          button(
            "Forget",
            async () => {
              if (
                !confirm(
                  `Forget "${t.name}"?\n\nEverything remembered about this topic ` +
                    "goes with it — which repositories were already seen, and what " +
                    "was already reported. Adding it back starts from nothing."
                )
              ) {
                return;
              }
              try {
                await invoke("brain_watch_remove", { name: String(t.name) });
                toast(`Forgot ${t.name}.`, "ok");
                await load(["watch", "watch_report"], { quiet: true });
                render("watch");
              } catch (error) {
                toast(String((error && error.message) || error), "bad");
              }
            },
            { danger: true }
          ),
        ],
      }),
    "No topics watched."
  );
  dom.watch.replaceChildren(head, box);
}

function renderWatchReport() {
  const body = state.data.watch_report || {};
  const why = unavailable("watch_report");
  if (why) return rows(dom.watchReport, [], null, whyNode("watch_report"));
  const findings = Array.isArray(body.findings)
    ? body.findings
    : Array.isArray(body.items)
      ? body.items
      : [];

  dom.watchSeen.disabled = findings.length === 0;

  rows(
    dom.watchReport,
    findings,
    (f) => {
      // "none stated" means no permission, not "probably fine" — so an absent
      // licence is rendered as a warning, not as a blank.
      const licence = String(f.licence || f.license || "").trim();
      const stated = licence && !/^(none|unknown|null)$/i.test(licence);
      return row({
        tag: stated ? licence : "no licence",
        state: stated ? "ok" : "warn",
        title: String(f.full_name || f.name || "(repository)"),
        meta: [
          String(f.descr || f.description || ""),
          [
            f.stars !== undefined ? `★ ${f.stars}` : "",
            f.topic ? `topic: ${f.topic}` : "",
            f.archived ? "archived" : "",
            stated ? "" : "no licence stated - no permission to use it",
          ]
            .filter(Boolean)
            .join(" · "),
          f.note ? `scanner: ${f.note}` : "",
        ],
        actions: [],
      });
    },
    "Nothing new since you last marked the list read."
  );
}

/* ==========================================================================
   Live
   ========================================================================== */

function renderLive() {
  const link = currentLink();
  const attention = link.attention;

  // The same answer the tray paints, from the same function — including
  // `approval` and `standby`, which the arbiter's own `face_state` does not
  // compose because they are UI precedence rather than its business.
  const face = surfaceState(link);
  dom.nowFace.dataset.face = face;
  dom.nowActivity.textContent = face;
  dom.nowPower.textContent = link.connected
    ? `power: ${link.power}${link.powerSetBy ? ` · ${link.powerSetBy}` : ""}`
    : link.error || "offline";

  const status = state.data.status || {};
  dom.nowKv.replaceChildren();
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dom.nowKv.append(el("dt", "", k), el("dd", "", v));
  };
  add("Model", status.model || status.current_model);
  add("Lane", status.lane || status.route);
  add("Approvals waiting", link.approvals);
  add("Stream", link.connected ? (link.stale ? "connected, stale" : "live") : "down");
  add("Last event", link.lastId || "");

  // The budget as pips, one per interruption. Spent ones go flat; when the
  // budget is blocked outright — Quiet, Standby, a locked session, muted — the
  // remaining pips go grey too, because "four left" is not true then.
  dom.budget.replaceChildren();
  if (attention.known) {
    const blocked = Boolean(attention.blockedBy);
    dom.budget.dataset.blocked = String(blocked);
    for (let i = 0; i < Math.max(attention.limit, 1); i++) {
      const pip = el("span", "pip");
      pip.dataset.spent = String(i < attention.spent);
      dom.budget.append(pip);
    }
    dom.budgetNote.textContent = blocked
      ? `Silent — ${attention.blockedBy}. ${attention.pending} waiting to be told.`
      : `${attention.remaining} of ${attention.limit} spoken interruptions left today · ` +
        `${attention.pending} waiting to be told`;
  } else {
    dom.budgetNote.textContent = "The interruption budget has not been read yet.";
  }
}

function pushTrace(frame) {
  const now = new Date();
  const time =
    String(now.getHours()).padStart(2, "0") +
    ":" +
    String(now.getMinutes()).padStart(2, "0") +
    ":" +
    String(now.getSeconds()).padStart(2, "0");

  const kind = String((frame && frame.kind) || "event");
  let body = "";
  const data = (frame && frame.data) || {};
  if (kind === "activity") {
    // Two shapes are in the wild: the state at the top level, and the rebuilt
    // bus's `note()` shape, `{key, value: {state, detail}}`. The detail is
    // what the tool loop announces ("Using calculator..."), so show it.
    const value = data.value && typeof data.value === "object" ? data.value : {};
    const state = String(data.state || value.state || "");
    const detail = String(data.detail || data.activity_detail || value.detail || "");
    body = detail ? `${state} · ${detail}` : state;
  } else if (kind === "step") body = stepText(data);
  else if (kind === "attention") {
    body = `remaining ${data.remaining ?? "?"} · pending ${data.pending ?? "?"}` +
      (data.banked ? " · banked" : "") +
      (data.blocked_by ? ` · ${data.blocked_by}` : "");
  } else if (kind === "approval") body = `${data.count ?? "?"} waiting`;
  else if (kind === "proposal") {
    // The extractor now runs on its own, after a conversation goes quiet, so
    // the review queue fills having asked nobody. Without this branch the
    // event landed in the generic `else` below and read as a raw id array —
    // a doorbell ringing into an empty room, which is the exact defect the
    // backend patch that added the event was written to fix elsewhere.
    //
    // Count only. The event deliberately carries no fact text (a proposal
    // quotes whatever produced it), so there is nothing here to render but
    // the number, and the memory pane is where you go to read them.
    const n = data.count ?? (Array.isArray(data.value) ? data.value.length : "?");
    body = n === 0 ? "review queue empty" : `${n} to review`;
  } else if (kind === "memory_saved") {
    // Automatic learning saved something: how many, never the words (the
    // event carries ids only - JARVIS-API.md section 19).
    const n = savedIds(data).length;
    body = rememberedLine(n) || "saved nothing";
  } else if (kind === "deep") {
    // The id and how it ended - never the question or the answer.
    body = `question ${String(data.id || "?")} ${String(data.state || "")}`.trim();
  } else if (kind === "hello") {
    body = `resumed from ${data.resumed_from ?? 0}${data.stale ? " · STALE" : ""}`;
  } else {
    const value = data.value !== undefined ? data.value : data.title || data.key;
    body = value === undefined ? JSON.stringify(data).slice(0, 120) : String(value);
  }

  state.trace.push({ time, kind, body });
  // Bounded: this window can be left open for a day, and an unbounded list of
  // DOM nodes is a leak with a nice name.
  if (state.trace.length > 300) state.trace.splice(0, state.trace.length - 300);

  if (state.view !== "live") return;
  const li = el("li");
  li.append(
    el("span", "trace-time", time),
    el("span", "trace-kind", kind),
    el("span", "trace-body", body)
  );
  dom.trace.append(li);
  while (dom.trace.childElementCount > 300) dom.trace.firstElementChild.remove();
  dom.trace.scrollTop = dom.trace.scrollHeight;
}

// stepText now lives in step-words.js, shared with the Jarvis bar
// (item 10, UI-AUDIT-2026-09-26.md).

function repaintTrace() {
  dom.trace.replaceChildren();
  for (const t of state.trace) {
    const li = el("li");
    li.append(
      el("span", "trace-time", t.time),
      el("span", "trace-kind", t.kind),
      el("span", "trace-body", t.body)
    );
    dom.trace.append(li);
  }
  dom.trace.scrollTop = dom.trace.scrollHeight;
}

/* ==========================================================================
   The galaxy
   --------------------------------------------------------------------------
   A force-directed layout, simulated to a stop and then drawn statically.

   Two decisions worth stating. First, the layout runs for a bounded number of
   cooling ticks and then freezes: a graph that jiggles for ever is harder to
   read and burns a core on a window that may be left open all day. The
   assembly is visible while it settles, which is the one moment of spectacle
   this view gets.

   Second, repulsion uses a uniform grid rather than every-pair. The node count
   is set by how much the owner's memory store knows, not by anything the UI
   controls, so O(n²) is a cliff somebody eventually falls off.
   ========================================================================== */

/**
 * A group is a hue AND a form, because ten hues cannot encode ten categories.
 *
 * The old ten-colour map measured CIEDE2000 6.0 between `core` and `cluster`
 * in normal vision — under the visual spec's own "obviously different at arm's
 * length" line before any colour blindness — and 1.0 under deuteranopia, which
 * is the spec's own word for indistinguishable. High contrast gave the two the
 * same hex outright.
 *
 * Five hues each carry two groups, told apart by whether the node is a filled
 * disc or a hollow ring. The pairs are semantically adjacent, so a misread
 * costs the least: a cluster mistaken for the core is a smaller error than a
 * cluster mistaken for a document. Form is not a theme concern — it is a fact
 * about what the group is — so it lives here and not in theme.css.
 */
const GROUP_STYLE = {
  core: ["--node-h1", "disc"],
  cluster: ["--node-h1", "ring"],
  model: ["--node-h2", "disc"],
  source: ["--node-h2", "ring"],
  fact: ["--node-h3", "disc"],
  document: ["--node-h3", "ring"],
  tool: ["--node-h4", "disc"],
  skill: ["--node-h4", "ring"],
  persona: ["--node-h5", "disc"],
  entity: ["--node-h5", "ring"],
};

/** Unknown groups get the last hue as a ring, which reads as "other". */
function styleFor(group) {
  return GROUP_STYLE[group] || ["--node-h5", "ring"];
}

const view = { x: 0, y: 0, scale: 1 };
let sim = null;
let hovered = null;
let selected = null;
const hiddenGroups = new Set();

/**
 * Node colours, cached.
 *
 * This is called once per node inside `draw()`, and `draw()` can run many times
 * per displayed frame. `getComputedStyle` per node per frame was a style query,
 * a string allocation and a trim for every dot on screen. The cache is cleared
 * whenever the theme changes and whenever a new graph is loaded, which are the
 * only two moments the answer can move.
 */
const colourCache = new Map();
function colourFor(group) {
  let hit = colourCache.get(group);
  if (hit !== undefined) return hit;
  const token = styleFor(group)[0];
  hit = getComputedStyle(dom.root).getPropertyValue(token).trim() || "#888";
  colourCache.set(group, hit);
  return hit;
}

/** Draws one node in its group's form. A ring is stroked, a disc is filled. */
function drawNode(ctx, x, y, r, group, colour) {
  if (styleFor(group)[1] === "ring") {
    // Stroked inside the radius so a ring and a disc of the same group read as
    // the same size — otherwise the ring looks like a bigger node.
    ctx.strokeStyle = colour;
    ctx.lineWidth = Math.max(1.4, r * 0.42);
    ctx.beginPath();
    ctx.arc(x, y, Math.max(1, r - ctx.lineWidth / 2), 0, Math.PI * 2);
    ctx.stroke();
    ctx.lineWidth = 1;
    return;
  }
  ctx.fillStyle = colour;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

/**
 * Coalesces redraws onto the frame.
 *
 * `pointermove` fires at the mouse's polling rate — 125Hz typically, 1000Hz on
 * a gaming mouse — and every handler used to call `draw()` directly, so the
 * renderer could be asked to draw sixteen times per displayed frame. Every
 * input path goes through here instead.
 */
let drawQueued = false;
// The four theme tokens the canvas paints with. Cached because reading them
// is a forced style recalc and they change only when the theme does.
let _ink = null;
function themeInk() {
  if (_ink) return _ink;
  const css = getComputedStyle(dom.root);
  const edge = css.getPropertyValue("--edge").trim() || "rgba(140,165,190,0.22)";
  _ink = {
    edge,
    edgeActive: css.getPropertyValue("--edge-active").trim() || edge,
    text: css.getPropertyValue("--text").trim() || "#fff",
    faint: css.getPropertyValue("--text-faint").trim() || "#888",
  };
  return _ink;
}

function invalidate() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => {
    drawQueued = false;
    draw();
  });
}

function renderGraph() {
  const body = state.data.graph || {};
  const why = unavailable("graph");
  if (why) {
    dom.graphEmpty.hidden = false;
    dom.graphEmptyText.textContent = why;
    dom.graphStat.textContent = "—";
    state.graph = null;
    return;
  }
  const nodes = Array.isArray(body.nodes) ? body.nodes : [];
  const links = Array.isArray(body.links) ? body.links : [];
  if (!nodes.length) {
    dom.graphEmpty.hidden = false;
    dom.graphEmptyText.textContent = "The graph is empty.";
    state.graph = null;
    return;
  }
  dom.graphEmpty.hidden = true;

  const byId = new Map();
  const N = nodes.map((n, i) => {
    // A deterministic ring start rather than random: the same graph lays out
    // the same way twice, so the picture the owner learns stays learnable.
    const a = (i / nodes.length) * Math.PI * 2;
    const r = 40 + (i % 9) * 26;
    const node = {
      id: String(n.id),
      label: String(n.label ?? n.id),
      group: String(n.group || "entity"),
      weight: Number(n.weight) || 1,
      extra: n,
      x: Math.cos(a) * r,
      y: Math.sin(a) * r,
      vx: 0,
      vy: 0,
      deg: 0,
    };
    byId.set(node.id, node);
    return node;
  });
  const L = [];
  for (const l of links) {
    const s = byId.get(String(l.source));
    const t = byId.get(String(l.target));
    if (!s || !t || s === t) continue;
    s.deg++;
    t.deg++;
    L.push({ s, t, kind: String(l.kind || "") });
  }

  colourCache.clear();
  // Same node set as last time? Keep the settled positions. Clicking Galaxy
  // used to replay 1.3s of assembly on every visit, which is charming once and
  // an obstacle by the tenth time. Refresh still re-lays it out, so the
  // spectacle is one click away and never imposed.
  const signature = nodes.map((n) => n.id).join("\u0000");
  const settled = state.graph && state.graph.signature === signature
    ? new Map(state.graph.nodes.map((n) => [n.id, n]))
    : null;
  if (settled) {
    for (const n of N) {
      const was = settled.get(n.id);
      if (was) { n.x = was.x; n.y = was.y; }
    }
  }

  state.graph = { nodes: N, links: L, byId, signature };
  selected = null;
  dom.inspector.hidden = true;
  buildLegend(body.counts || countGroups(N));
  dom.graphStat.textContent = `${N.length} nodes · ${L.length} links`;
  if (settled) {
    fitCanvas();
    draw();
  } else {
    startLayout();
  }
}

function countGroups(nodes) {
  const counts = {};
  for (const n of nodes) counts[n.group] = (counts[n.group] || 0) + 1;
  return counts;
}

function buildLegend(counts) {
  const present = countGroups(state.graph.nodes);
  dom.legend.replaceChildren();
  for (const group of Object.keys(present).sort()) {
    const item = el("button", "legend-item");
    item.type = "button";
    item.setAttribute("aria-pressed", String(!hiddenGroups.has(group)));
    const sw = el("span", "legend-swatch");
    const [, form] = styleFor(group);
    sw.dataset.form = form;
    if (form === "ring") {
      sw.style.background = "transparent";
      sw.style.borderColor = colourFor(group);
    } else {
      sw.style.background = colourFor(group);
      sw.style.borderColor = "transparent";
    }
    item.append(sw, el("span", "", group), el("span", "legend-count", present[group]));
    item.addEventListener("click", () => {
      if (hiddenGroups.has(group)) hiddenGroups.delete(group);
      else hiddenGroups.add(group);
      item.setAttribute("aria-pressed", String(!hiddenGroups.has(group)));
      draw();
    });
    dom.legend.append(item);
  }
  const missing = Object.keys(counts).filter((k) => !(k in present) && counts[k]);
  if (missing.length) {
    dom.legend.append(el("span", "legend-count", `(${missing.join(", ")} not in the graph)`));
  }
}

function startLayout() {
  if (sim) cancelAnimationFrame(sim);
  const g = state.graph;
  if (!g) return;

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const total = 320;
  // Ticks are driven by elapsed time, not by frames. Four ticks per frame meant
  // 80 frames of assembly: 1.33s at 60Hz, 0.67s at 120Hz, 0.49s at 165Hz — the
  // animation ran at whatever speed the monitor happened to be. The visual spec
  // already wrote this bug report for the reactor (`state_transforms.phase`:
  // never multiply the clock by a rate, integrate it) and this is the
  // frame-count version of the same mistake.
  const SIM_HZ = 240;
  let tick = 0;
  let carried = 0;
  let last = 0;

  // Reduced motion means no visible ASSEMBLY. It does not mean no time.
  //
  // This used to run all 320 ticks in one synchronous `while` loop, which is
  // the same total work the animated path does — delivered as a frozen window.
  // The node count is set by how much the owner's memory store knows, so on a
  // large graph that is a multi-second hang, and the person who gets it is the
  // one who asked for less motion because motion makes them unwell.
  //
  // Same chunking, same yielding, nothing drawn until it has settled.
  if (reduced) {
    dom.graphEmpty.hidden = false;
    dom.graphEmptyText.textContent = "Laying out the graph…";
    const slice = () => {
      const until = performance.now() + 8;
      while (tick < total && performance.now() < until) {
        step(g, 1 - tick / total);
        tick++;
      }
      if (tick < total) {
        sim = requestAnimationFrame(slice);
        return;
      }
      sim = null;
      dom.graphEmpty.hidden = true;
      fitToContent();
      draw();
    };
    sim = requestAnimationFrame(slice);
    return;
  }

  const frame = (now) => {
    if (!last) last = now;
    // Clamped: a background tab or a stalled frame must not deliver a hundred
    // ticks at once and detonate the layout.
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    carried += dt * SIM_HZ;
    const steps = Math.min(8, Math.floor(carried));
    carried -= steps;
    for (let i = 0; i < steps && tick < total; i++, tick++) {
      step(g, 1 - tick / total);
    }

    // The camera follows the whole way and eases in, rather than tracking for
    // twelve frames and then teleporting to the final fit. `k` is derived from
    // dt so the glide is the same on any refresh rate.
    fitToContent({ ease: 1 - Math.exp(-dt / 0.35) });
    draw();

    if (tick < total) sim = requestAnimationFrame(frame);
    else {
      sim = null;
      fitToContent();
      // Labels are only placed once the nodes have stopped. Re-running the
      // collision test every frame made names flicker in and out as the
      // packing resolved differently each time — the ugliest part of the
      // assembly, and removing it is also cheaper.
      draw();
    }
  };
  sim = requestAnimationFrame(frame);
}

/** One cooling tick: repulsion by grid, springs along links, pull to centre. */
function step(g, heat) {
  const nodes = g.nodes;
  // Tuned away from a lattice. The first pass used uniform repulsion with a
  // short cutoff and a uniform spring rest length, and uniform forces reach a
  // uniform equilibrium: 165 nodes settled into a visible grid, which reads as
  // a diagram of nothing.
  //
  // Two changes break it. Repulsion is longer-range and weaker per pair, so it
  // separates whole clusters rather than spacing individual nodes; and the
  // springs are four times stronger, so anything linked clumps hard. What you
  // see then is the shape of the connections, which is the only thing this
  // view is for.
  const REPEL = 2600;
  // CELL must be at least the reach radius, or the 3x3 neighbourhood below
  // does not contain everything the force is supposed to touch. It used to be
  // 130 against a 286px reach, so repulsion was silently truncated AND
  // direction-dependent: whether a node 200px east pushed you depended on
  // where the cell boundaries happened to fall. The layout still looked
  // plausible, which is why it survived — but it was not the force field the
  // constants describe.
  const REACH_R = 286;
  const CELL = REACH_R;
  const REACH = REACH_R ** 2;
  const SPRING = 0.035;
  const REST = 42;
  const CENTRE = 0.0009;
  const DAMP = 0.86;

  // Bucket by cell so repulsion is over neighbours rather than everybody.
  // Integer keys, not template strings. The string form cost one allocation
  // and one hash per node to insert plus nine more to look up — ten per node
  // per tick, times 320 ticks. At a few hundred nodes the garbage collector
  // was the bottleneck long before the geometry was.
  const key = (cx, cy) => (cx + 4096) * 8192 + (cy + 4096);
  const grid = new Map();
  for (const n of nodes) {
    const k = key(Math.floor(n.x / CELL), Math.floor(n.y / CELL));
    let cell = grid.get(k);
    if (!cell) grid.set(k, (cell = []));
    cell.push(n);
  }
  for (const n of nodes) {
    const cx = Math.floor(n.x / CELL);
    const cy = Math.floor(n.y / CELL);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const cell = grid.get(key(cx + dx, cy + dy));
        if (!cell) continue;
        for (const m of cell) {
          if (m === n) continue;
          let ex = n.x - m.x;
          let ey = n.y - m.y;
          let d2 = ex * ex + ey * ey;
          if (d2 > REACH) continue;
          if (d2 < 0.01) {
            // Two nodes exactly on top of each other have no direction to
            // separate along; nudge deterministically by id so the layout
            // stays reproducible.
            ex = (n.id.charCodeAt(0) % 7) - 3 || 1;
            ey = (n.id.charCodeAt(1 % n.id.length) % 7) - 3 || 1;
            d2 = ex * ex + ey * ey;
          }
          const f = (REPEL * (1 + m.deg * 0.12)) / d2;
          const d = Math.sqrt(d2);
          n.vx += (ex / d) * f;
          n.vy += (ey / d) * f;
        }
      }
    }
  }

  for (const l of g.links) {
    const ex = l.t.x - l.s.x;
    const ey = l.t.y - l.s.y;
    const d = Math.hypot(ex, ey) || 0.01;
    const f = (d - REST) * SPRING;
    const ux = (ex / d) * f;
    const uy = (ey / d) * f;
    l.s.vx += ux;
    l.s.vy += uy;
    l.t.vx -= ux;
    l.t.vy -= uy;
  }

  for (const n of nodes) {
    n.vx -= n.x * CENTRE;
    n.vy -= n.y * CENTRE;
    n.vx *= DAMP;
    n.vy *= DAMP;
    const cap = 30 * heat;
    n.x += Math.max(-cap, Math.min(cap, n.vx));
    n.y += Math.max(-cap, Math.min(cap, n.vy));
  }
}

function radiusOf(n) {
  return 3 + Math.min(9, Math.sqrt(n.weight * 2 + n.deg));
}

function visible(n) {
  return !hiddenGroups.has(n.group);
}

/// Device pixels per CSS pixel for the graph canvas.
///
/// One function because there used to be two numbers: `fitCanvas` sized the
/// backing store at one cap and `draw` set its transform with another. Every
/// caller now reads the same value.
///
/// Capped at 3 rather than 2: the cap is a memory guard — a backing store
/// grows with its square — but `devicePixelRatio` also carries the webview
/// zoom, so on a 2x display at 150% the honest ratio is 3 and clamping to 2
/// renders the graph soft for exactly the person who enlarged it to see it.
function canvasScale() {
  return Math.min(3, window.devicePixelRatio || 1);
}

function fitCanvas() {
  const c = dom.canvas;
  const rect = c.getBoundingClientRect();
  // 3, not 2. The cap is a memory guard — a backing store grows with its
  // square — but it is also what a reader who has zoomed to 200% runs into:
  // `devicePixelRatio` carries the webview zoom, so on a 2x display at 150%
  // the honest ratio is 3 and clamping to 2 renders the graph soft for exactly
  // the person who enlarged it in order to see it.
  const dpr = canvasScale();
  c.width = Math.max(1, Math.round(rect.width * dpr));
  c.height = Math.max(1, Math.round(rect.height * dpr));
  draw();
}

function fitToContent({ ease = 1 } = {}) {
  const g = state.graph;
  if (!g || !g.nodes.length) return;
  const shown = g.nodes.filter(visible);
  const list = shown.length ? shown : g.nodes;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of list) {
    minX = Math.min(minX, n.x);
    maxX = Math.max(maxX, n.x);
    minY = Math.min(minY, n.y);
    maxY = Math.max(maxY, n.y);
  }
  const rect = dom.canvas.getBoundingClientRect();
  const pad = 60;
  const sx = (rect.width - pad * 2) / Math.max(1, maxX - minX);
  const sy = (rect.height - pad * 2) / Math.max(1, maxY - minY);
  const scale = Math.max(0.12, Math.min(2.4, Math.min(sx, sy)));
  const x = rect.width / 2 - ((minX + maxX) / 2) * scale;
  const y = rect.height / 2 - ((minY + maxY) / 2) * scale;
  const k = Math.max(0, Math.min(1, ease));
  view.scale += (scale - view.scale) * k;
  view.x += (x - view.x) * k;
  view.y += (y - view.y) * k;
}

function draw() {
  const c = dom.canvas;
  const ctx = c.getContext("2d");
  if (!ctx) return;
  // The SAME cap `fitCanvas` sizes the backing store with. They disagreed —
  // 3 there, 2 here — from the moment the cap was raised, so on any display
  // where `devicePixelRatio` exceeds 2 (a 300% Windows scale, or Ctrl+= up to
  // the 2.5 zoom step) the graph drew into the top-left two thirds of its own
  // buffer while the hit test went on using the full width. Clicking a visible
  // node selected nothing.
  const dpr = canvasScale();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, c.width / dpr, c.height / dpr);

  const g = state.graph;
  if (!g) return;

  // getComputedStyle forces a style recalc, and this ran inside draw() - so
  // every interaction frame, at up to one per displayed frame while dragging,
  // paid for one. The values are four theme tokens that change only when the
  // theme does, so they are read once and refreshed from followTheme below.
  const { edge, edgeActive, text, faint } = themeInk();

  const T = (n) => [n.x * view.scale + view.x, n.y * view.scale + view.y];
  const focus = selected || hovered;
  const near = new Set();
  if (focus) {
    near.add(focus.id);
    for (const l of g.links) {
      if (l.s === focus) near.add(l.t.id);
      if (l.t === focus) near.add(l.s.id);
    }
  }

  // Two passes, two paths, two strokes — not one path per link. Each
  // beginPath/stroke pair is a separate Skia draw call, and at a couple of
  // thousand links that was the single most expensive thing on the canvas.
  // Links only ever come in two appearances (lit, or not), so two batches
  // covers every case.
  ctx.lineWidth = 1;
  for (const lit of [false, true]) {
    if (lit && !focus) continue;
    ctx.strokeStyle = lit ? edgeActive : edge;
    ctx.globalAlpha = focus ? (lit ? 1 : 0.18) : 1;
    ctx.beginPath();
    let drew = false;
    for (const l of g.links) {
      if (!visible(l.s) || !visible(l.t)) continue;
      const isLit = Boolean(focus && (l.s === focus || l.t === focus));
      if (isLit !== lit) continue;
      const [x1, y1] = T(l.s);
      const [x2, y2] = T(l.t);
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      drew = true;
    }
    if (drew) ctx.stroke();
  }
  ctx.globalAlpha = 1;

  for (const n of g.nodes) {
    if (!visible(n)) continue;
    const [x, y] = T(n);
    const r = radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale));
    const dim = focus && !near.has(n.id);
    // 0.45, not 0.2. At 0.2 a dimmed node measured 1.11:1 against the canvas —
    // invisible, while `nodeAt` still hit-tested it, so you could click a node
    // you could not see. De-emphasis, not erasure.
    ctx.globalAlpha = dim ? 0.45 : 1;
    drawNode(ctx, x, y, r, n.group, colourFor(n.group));
    if (n === selected) {
      ctx.strokeStyle = text;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, Math.PI * 2);
      ctx.stroke();
      ctx.lineWidth = 1;
    }
  }
  ctx.globalAlpha = 1;

  // Labels only where they can be read: the core, the heavy nodes, and
  // whatever is focused. Every node labelled at any zoom is a grey smear.
  ctx.font = '11px "Segoe UI", system-ui, sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "top";

  // Drawn in importance order and skipped where one would land on another
  // already placed. Overlapping labels are worse than missing ones: two names
  // on top of each other are unreadable AND hide that there are two things.
  // Not while it is still settling: see the note in `startLayout`.
  if (sim) return;
  const placed = [];
  const ordered = g.nodes
    .filter(visible)
    .filter((n) => n.group === "core" || n.group === "cluster" || n.deg >= 6 || near.has(n.id))
    .sort((a, b) => {
      const rank = (n) =>
        (n === focus ? 4 : 0) + (near.has(n.id) ? 2 : 0) +
        (n.group === "core" ? 3 : n.group === "cluster" ? 1 : 0);
      return rank(b) - rank(a) || b.deg - a.deg;
    });

  for (const n of ordered) {
    if (view.scale < 0.35 && !near.has(n.id) && n.group !== "core") continue;
    const [x, y] = T(n);
    const label = n.label.length > 34 ? n.label.slice(0, 33) + "…" : n.label;
    const w = ctx.measureText(label).width;
    const top = y + radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale)) + 3;
    const box = { x1: x - w / 2 - 2, x2: x + w / 2 + 2, y1: top - 1, y2: top + 13 };
    if (placed.some((p) => box.x1 < p.x2 && box.x2 > p.x1 && box.y1 < p.y2 && box.y2 > p.y1)) {
      continue;
    }
    placed.push(box);
    ctx.fillStyle = near.has(n.id) || !focus ? text : faint;
    // 0.55, not 0.25: at 0.25 these measured 1.43:1 and simply vanished — and
    // they are the orientation landmarks, so they disappeared exactly when
    // someone was exploring.
    ctx.globalAlpha = focus && !near.has(n.id) ? 0.55 : 1;
    ctx.fillText(label, x, top);
  }
  ctx.globalAlpha = 1;
}

function nodeAt(clientX, clientY) {
  const g = state.graph;
  if (!g) return null;
  const rect = dom.canvas.getBoundingClientRect();
  const px = clientX - rect.left;
  const py = clientY - rect.top;
  let best = null;
  let bestD = Infinity;
  for (const n of g.nodes) {
    if (!visible(n)) continue;
    const x = n.x * view.scale + view.x;
    const y = n.y * view.scale + view.y;
    const r = radiusOf(n) * Math.max(0.55, Math.min(1.6, view.scale)) + 4;
    const d = (x - px) ** 2 + (y - py) ** 2;
    if (d <= r * r && d < bestD) {
      best = n;
      bestD = d;
    }
  }
  return best;
}

function select(node) {
  selected = node;
  if (!node) {
    dom.inspector.hidden = true;
    draw();
    return;
  }
  dom.nodeKind.textContent = node.group;
  dom.nodeLabel.textContent = node.label;

  dom.nodeFacts.replaceChildren();
  const add = (k, v) => {
    if (v === undefined || v === null || v === "") return;
    dom.nodeFacts.append(el("dt", "", k), el("dd", "", v));
  };
  add("id", node.id);
  add("connections", node.deg);
  for (const [k, v] of Object.entries(node.extra || {})) {
    if (["id", "label", "group", "weight"].includes(k)) continue;
    if (v === null || typeof v === "object") continue;
    add(k, v);
  }

  const g = state.graph;
  const neighbours = [];
  for (const l of g.links) {
    if (l.s === node) neighbours.push([l.t, l.kind]);
    else if (l.t === node) neighbours.push([l.s, l.kind]);
  }
  dom.nodeLinks.replaceChildren();
  if (!neighbours.length) {
    dom.nodeLinks.append(el("li", "empty", "Nothing connected."));
  }
  for (const [other, kind] of neighbours.slice(0, 60)) {
    const li = el("li");
    const b = el("button", "", `${other.label}${kind ? ` · ${kind}` : ""}`);
    b.type = "button";
    b.addEventListener("click", () => {
      select(other);
      centreOn(other);
      // `select` calls `replaceChildren` on this list, so the button that was
      // just activated is removed from the document while it holds focus and
      // focus falls to <body>. A keyboard user lost their place on every hop
      // and had to tab from the top of the window again.
      dom.nodeLabel.focus({ preventScroll: true });
    });
    li.append(b);
    dom.nodeLinks.append(li);
  }
  dom.inspector.hidden = false;
  // A canvas has no accessibility tree, so selecting a node is otherwise a
  // silent event. This is the only thing that tells a screen-reader user
  // anything happened.
  announce(
    `${node.label}, ${node.group}, ${node.deg} ` +
      `${node.deg === 1 ? "connection" : "connections"}.`
  );
  draw();
}

function centreOn(node) {
  const rect = dom.canvas.getBoundingClientRect();
  view.x = rect.width / 2 - node.x * view.scale;
  view.y = rect.height / 2 - node.y * view.scale;
  draw();
}

/* ---- Canvas interaction -------------------------------------------------- */

let dragging = null;

dom.canvas.addEventListener("pointerdown", (e) => {
  dom.canvas.setPointerCapture(e.pointerId);
  dragging = { x: e.clientX, y: e.clientY, moved: false };
});

dom.canvas.addEventListener("pointermove", (e) => {
  if (dragging) {
    const dx = e.clientX - dragging.x;
    const dy = e.clientY - dragging.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) dragging.moved = true;
    view.x += dx;
    view.y += dy;
    dragging.x = e.clientX;
    dragging.y = e.clientY;
    invalidate();
    return;
  }
  const hit = nodeAt(e.clientX, e.clientY);
  if (hit !== hovered) {
    hovered = hit;
    dom.canvas.style.cursor = hit ? "pointer" : "grab";
    invalidate();
  }
});

dom.canvas.addEventListener("pointerup", (e) => {
  const wasDrag = dragging && dragging.moved;
  dragging = null;
  if (wasDrag) return;
  select(nodeAt(e.clientX, e.clientY));
});

dom.canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const rect = dom.canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const factor = Math.exp(-e.deltaY * 0.0016);
    const next = Math.max(0.08, Math.min(4, view.scale * factor));
    // Zoom about the cursor rather than the origin, so the thing under the
    // pointer stays under the pointer.
    view.x = px - ((px - view.x) / view.scale) * next;
    view.y = py - ((py - view.y) / view.scale) * next;
    view.scale = next;
    invalidate();
  },
  { passive: false }
);

// The canvas is focusable, so the graph is pannable and zoomable without a
// mouse. Selecting a node without one goes through the search field, which is
// also what makes the view usable with a screen reader.
dom.canvas.addEventListener("keydown", (e) => {
  const stepPx = e.shiftKey ? 120 : 40;
  const keys = {
    ArrowLeft: () => (view.x += stepPx),
    ArrowRight: () => (view.x -= stepPx),
    ArrowUp: () => (view.y += stepPx),
    ArrowDown: () => (view.y -= stepPx),
    "+": () => (view.scale = Math.min(4, view.scale * 1.2)),
    "=": () => (view.scale = Math.min(4, view.scale * 1.2)),
    "-": () => (view.scale = Math.max(0.08, view.scale / 1.2)),
    "0": () => fitToContent(),
    Escape: () => select(null),
  };
  const fn = keys[e.key];
  if (!fn) return;
  e.preventDefault();
  fn();
  invalidate();
});

/* ==========================================================================
   Theme
   ========================================================================== */

function applyTheme(name, { persist = true } = {}) {
  const theme = normaliseTheme(name);
  dom.root.setAttribute("data-theme", theme);
  dom.themePicker.value = theme;
  try {
    localStorage.setItem("jarvis.theme", theme);
  } catch (error) {
    /* the store below is the source of truth; this is only the anti-flash cache */
  }
  if (persist) {
    invoke("set_theme", { theme }).catch((error) =>
      console.error("[brain] could not persist the theme:", error)
    );
  }
  // The graph reads its colours from the computed style, so a theme change has
  // to repaint it — nothing else on the page needs telling.
  colourCache.clear();
  if (state.graph) draw();
}

/* ==========================================================================
   Wiring
   ========================================================================== */

const TAB_ORDER = Object.keys(VIEWS);

for (const key of TAB_ORDER) {
  const tab = $(`tab-${key}`);
  if (tab) tab.addEventListener("click", () => showView(key));
}

/**
 * The rail is a `tablist`, and a tablist is one Tab stop with the arrows moving
 * inside it. It shipped as six separate Tab stops, which is the pattern the
 * role explicitly is not: a screen reader announces "tab, 1 of 6" and then the
 * arrows do nothing, and a keyboard user has to press Tab six times to get past
 * the navigation to the thing they came for.
 *
 * Vertical rail, so Up/Down are the axis and Left/Right are accepted too —
 * costs nothing and saves the reader guessing which one this rail thinks it is.
 *
 * Cycles only the tabs currently on the rail: while "Advanced" is collapsed
 * its four tabs are `hidden` and cannot take focus, so including them here
 * would let arrowing past Work land nowhere.
 */
function visibleTabOrder() {
  return TAB_ORDER.filter((key) => advancedOpen || !ADVANCED_VIEWS.includes(key));
}

dom.rail?.addEventListener("keydown", (event) => {
  const STEP = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
  const order = visibleTabOrder();
  const here = order.indexOf(state.view);
  let next = null;
  if (event.key in STEP) next = (here + STEP[event.key] + order.length) % order.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = order.length - 1;
  if (next === null || here < 0) return;
  event.preventDefault();
  // Selection follows focus, which is the right choice for a tablist whose
  // panels are already loaded: it is what a reader expects, and the alternative
  // (arrow to move, Enter to open) makes them press two keys for every view.
  showView(order[next]);
  $(`tab-${order[next]}`)?.focus();
});

/**
 * "Advanced" reveals the four views this window used to always show —
 * Galaxy, Live, Trust, Watch — unchanged, just not on the rail by default.
 * Collapsing it again hides the tabs but never touches `state.view`: a view
 * that was open when the rail collapsed stays open, it just has no visible
 * tab until Advanced is reopened.
 */
dom.advancedToggle?.addEventListener("click", () => {
  advancedOpen = !advancedOpen;
  dom.advancedToggle.setAttribute("aria-expanded", String(advancedOpen));
  for (const key of ADVANCED_VIEWS) {
    const item = $(`tab-${key}`)?.closest("li");
    if (item) item.hidden = !advancedOpen;
  }
  // Roving tabindex needs exactly one reachable stop at all times. showView()
  // already keeps that true whenever the active view is on the visible rail;
  // the one gap is collapsing Advanced while one of ITS views is the active
  // one, which would otherwise leave every tab at -1 and the rail untabbable.
  if (!advancedOpen && ADVANCED_VIEWS.includes(state.view)) {
    for (const key of TAB_ORDER) {
      const tab = $(`tab-${key}`);
      if (tab) tab.tabIndex = key === "memory" ? 0 : -1;
    }
  }
  renderCounts();
});

dom.refresh.addEventListener("click", async () => {
  // Drop the cached layout so a refresh really re-lays out — and note that
  // `render` calls `startLayout` itself, so calling it again here started the
  // simulation twice and cancelled the first one mid-flight.
  if (state.view === "galaxy") state.graph = null;
  if (state.view === "history") chats.at = 0;
  if (state.view === "memory") autoL.at = 0;
  await load(sectionsFor(state.view));
  render(state.view);
});

dom.graphRefit.addEventListener("click", () => {
  fitToContent();
  draw();
});

dom.inspectorClose.addEventListener("click", () => select(null));

dom.memoryFactsFilter?.addEventListener("input", () => renderFacts());
$("history-filter")?.addEventListener("input", () => paintHistoryList());

dom.graphSearch.addEventListener("input", () => {
  const q = dom.graphSearch.value.trim().toLowerCase();
  if (!q || !state.graph) return;
  const hit = state.graph.nodes.find(
    (n) => visible(n) && n.label.toLowerCase().includes(q)
  );
  if (hit) {
    select(hit);
    centreOn(hit);
  }
});

dom.traceClear.addEventListener("click", () => {
  state.trace = [];
  dom.trace.replaceChildren();
});

dom.themePicker.addEventListener("change", () => applyTheme(dom.themePicker.value));

dom.watchAddOpen.addEventListener("click", () => {
  dom.watchForm.hidden = !dom.watchForm.hidden;
  if (!dom.watchForm.hidden) $("watch-name").focus();
});
dom.watchCancel.addEventListener("click", () => {
  dom.watchForm.hidden = true;
});

dom.watchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("watch-name").value.trim();
  if (!name) return;
  const stars = $("watch-stars").value.trim();
  try {
    await invoke("brain_watch_add", {
      name,
      query: $("watch-query").value.trim() || null,
      minStars: stars ? Number(stars) : null,
      language: $("watch-language").value.trim() || null,
      notify: $("watch-notify").checked,
    });
    toast(`Watching ${name}.`, "ok");
    dom.watchForm.reset();
    dom.watchForm.hidden = true;
    await load(["watch", "watch_report"], { quiet: true });
    render("watch");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
});

dom.watchSeen.addEventListener("click", async () => {
  try {
    await invoke("brain_watch_seen", { topic: null });
    toast("Marked read.", "ok");
    await load(["watch", "watch_report"], { quiet: true });
    render("watch");
  } catch (error) {
    toast(String((error && error.message) || error), "bad");
  }
});

window.addEventListener("resize", () => {
  if (state.view === "galaxy") fitCanvas();
});

// Toggling the OS setting used to have no effect until the next refresh,
// because `matchMedia` was read once inside `startLayout`.
matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", () => {
  if (state.view === "galaxy" && state.graph) startLayout();
});

// Applied at boot AND on every change. The Brain read `get_theme` once and
// then ignored `theme-changed` for the life of the window, so picking a theme
// in Settings left the largest coloured surface in the product on the old
// palette until it was reopened. `tests/themes-all.mjs` only measured the
// boot path, so it passed while claiming "every window follows the theme".
// The cached ink has to die with the old palette, or the graph keeps painting
// the previous theme's edges until something else forces a reload.
followTheme((theme) => {
  dom.themePicker.value = theme;
  _ink = null;
  if (state.view === "galaxy" && state.graph) invalidate();
});

// The canvas is sized in device pixels from its CSS box, so a zoom step has to
// re-measure it or the graph is drawn at the old scale inside the new box.
followZoom(() => {
  if (state.view === "galaxy") fitCanvas();
});

/* ---- The one stream ------------------------------------------------------ */

startLink();
// "Open the card": one line while an approval card waits (card-link.js).
mountCardLink(document.getElementById("card-link"));

onLink((link) => {
  // The same words as every other window. "stream live · stale" used to sit
  // in the same green pill as "stream live", so stale looked fully live.
  const words = linkWords(link);
  dom.linkPill.dataset.connected = String(link.connected);
  dom.linkPill.dataset.tone = words.tone;
  dom.linkText.textContent = words.short;
  dom.linkPill.title = link.error || `${link.base} · last event ${link.lastId}`;
  dom.reconnectLink.hidden = link.connected;
  syncLiveButtons();
  paintFreshness();
  if (state.view === "live") renderLive();
  renderCounts();
});

dom.reconnectLink.addEventListener("click", () => {
  reconnect();
  dom.linkText.textContent = "Reconnecting…";
  announce("Reconnecting.");
});

onEvent((frame) => {
  pushTrace(frame);
  // A doorbell for the pane that is open. Reading everything on every frame
  // would put the graph's multi-second walk on the event path.
  const kind = String((frame && frame.kind) || "");
  // The next `model` event is the card being answered (or the download
  // moving), so the "waiting for your approval" line has done its job.
  if (kind === "model" && (state.modelAsk || state.modelAskEnded)) {
    state.modelAsk = null;
    state.modelAskEnded = null;
    if (state.view === "faculties") renderModels();
  }
  // A deep question finished (`{id, state}` only - a doorbell): read the
  // list again, so the answer shows without polling. Off the Memory tab it
  // is only marked old, and read when the tab is next shown.
  if (kind === "deep") {
    deep.at = 0;
    if (state.view === "memory") loadDeep();
  }
  // Automatic learning saved something (`{ids}` only, never the text): the
  // quiet line, and the list read again. Never a pop-up.
  if (kind === "memory_saved") noteMemorySaved(frame && frame.data);
  // A timer, alarm or reminder went off, or Coming up changed (`{id, kind,
  // state}` only - a doorbell): read the list again. The toast itself is
  // Rust's (brain/schedule.rs toast_fired), so it shows with the Brain shut.
  // A focus session started, changed or ended, or has a line to say
  // (`{state}` or `{state: "callout", seq}` - never what was in front): read
  // it again. The line itself is played by the Jarvis bar, fetched by Rust.
  if (kind === "focus") {
    fx.at = 0;
    if (state.view === "work") loadFocus();
  }
  if (kind === "schedule") {
    upL.at = 0;
    if (state.view === "work") loadComingUp();
    // A briefing went off or is ready (`{id, kind: "briefing", state}`):
    // read the briefing again, its lines by the authenticated route only.
    if (frame && frame.data && frame.data.kind === "briefing") {
      brief.at = 0;
      if (state.view === "work") loadBriefing();
    }
  }

  const refreshes = {
    model: ["models"],
    finding: ["watch", "watch_report"],
    job: ["jobs"],
    // The learner filled the review queue on its own (or a "Remember:"
    // made a card). Without this the Memory tab showed an old queue until
    // something else refreshed it.
    proposal: ["memory_pending"],
    // ...or saved some on its own (automatic learning): the facts list too.
    memory_saved: ["memory_facts"],
  };
  const sections = refreshes[kind];
  if (!sections) return;
  const showing = VIEW_SECTIONS[state.view] || [];
  if (!sections.some((s) => showing.includes(s))) return;
  load(sections, { quiet: true }).then(() => render(state.view));
});

/* ---- Boot ---------------------------------------------------------------- */

(async () => {
  // The inline bootstrap already painted from localStorage; this reconciles
  // with the store, which is what the other windows read.
  try {
    const stored = await invoke("get_theme");
    if (stored && stored !== dom.root.getAttribute("data-theme")) {
      applyTheme(stored, { persist: false });
    } else {
      dom.themePicker.value = dom.root.getAttribute("data-theme") || THEMES[0];
    }
  } catch (error) {
    dom.themePicker.value = dom.root.getAttribute("data-theme") || THEMES[0];
  }

  repaintTrace();
  await showView("memory");
})();

console.info(
  `[brain] ready — backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
);
