/**
 * Jarvis desktop widget.
 *
 * A 320px pane that lives on the desktop. Two states — a 44px mini-pill and an
 * expanded card — plus three jobs:
 *
 *   • render telemetry pushed from Rust on a timer;
 *   • surface pending autonomy gates and resolve them in one click;
 *   • capture a note without summoning the spotlight.
 *
 * Everything privileged goes through app-defined commands, so this file holds
 * no secrets and needs no plugin capability of its own.
 */

/* ==========================================================================
   Tauri bridge
   ========================================================================== */

import {
  announce,
  amend as amendOnBackend,
  currentLink,
  decide as decideOnBackend,
  injectTaskNote,
  onEvent,
  onLink,
  onQueue,
  pauseTask,
  resumeTask,
  riskLine,
  expiryWords,
  stopTask,
  followTheme,
  followZoom,
  linkWords,
  surfaceState,
  start as startLink,
} from "./jarvis-link.js";
import { TARGETS, fileNote, loadTargets, noTargetsLine, targetName } from "./note-capture.js";
import { EMAIL_APPROVE, EMAIL_DETAIL, isEmailCard } from "./email-sending.js";
import { CARD_KICKER, cardTitle } from "./card-words.js";
import {
  actionsOf as focusActionsOf,
  clock as focusClock,
  HELD_WHEN_STALE as FOCUS_HELD,
  LABELS as FOCUS_LABELS,
  leftNow as focusLeftNow,
  LOCK_TITLE as FOCUS_LOCK_TITLE,
  readFocus,
  toneOf as focusToneOf,
} from "./focus.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

/** Calls a Rust command, resolving to null when the backend is absent. */
async function invoke(command, args = {}) {
  if (!IS_TAURI) {
    console.info(`[widget] invoke("${command}") skipped - no Tauri backend`);
    return null;
  }
  try {
    return await TAURI.core.invoke(command, args);
  } catch (error) {
    console.error(`[widget] invoke("${command}") failed:`, error);
    return null;
  }
}

/** Like `invoke`, but surfaces the failure to the caller. */
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
    console.error(`[widget] listen("${event}") failed:`, error);
    return () => {};
  }
}

/* ==========================================================================
   DOM
   ========================================================================== */

const $ = (id) => document.getElementById(id);

const dom = {
  root: document.documentElement,
  shell: $("widget-shell"),
  tray: $("widget-tray"),
  faceWrap: $("face-wrap"),
  faceFrame: $("face-frame"),

  focusStrip: $("focus-strip"),
  focusClock: $("focus-clock"),
  focusWord: $("focus-word"),
  focusPause: $("focus-pause"),
  focusLock: $("focus-lock"),
  focusStop: $("focus-stop"),

  netDot: $("net-dot"),
  offline: $("widget-offline"),
  offlineText: $("widget-offline-text"),
  offlineRetry: $("widget-offline-retry"),
  gpuTemp: $("gpu-temp-compact"),
  routePill: $("route-pill"),

  btnToggle: $("btn-toggle-expand"),
  btnPin: $("btn-pin"),
  btnLog: $("btn-quick-log"),
  btnJoplin: $("btn-quick-joplin"),
  btnObs: $("btn-quick-obs"),

  meterVram: $("meter-vram"),
  meterCpu: $("meter-cpu"),
  meterGpu: $("meter-gpu"),
  vramVal: $("vram-val"),
  vramBar: $("vram-bar"),
  cpuVal: $("cpu-val"),
  cpuBar: $("cpu-bar"),
  gpuVal: $("gpu-val"),
  gpuBar: $("gpu-bar"),

  apprCard: $("approval-card"),
  apprRisk: $("appr-risk"),
  apprRaised: $("appr-raised"),
  apprRaisedChip: $("appr-raised-chip"),
  apprRaisedQuote: $("appr-raised-quote"),
  apprAction: $("appr-action"),
  apprDetail: $("appr-detail"),
  apprOptions: $("appr-options"),
  apprOptionsWhy: $("appr-options-why"),
  apprWhy: $("appr-why"),
  apprCount: $("appr-count"),
  apprNoteInput: $("appr-note"),
  btnApprNoteSend: $("btn-appr-note-send"),
  btnApprYes: $("btn-appr-yes"),
  btnApprNo: $("btn-appr-no"),

  widgetProgress: $("widget-progress"),
  taskControls: $("task-controls"),
  btnTaskPause: $("btn-task-pause"),
  btnTaskResume: $("btn-task-resume"),
  btnTaskStop: $("btn-task-stop"),
  taskNoteInput: $("task-note"),
  btnTaskNoteSend: $("btn-task-note-send"),

  captureTarget: $("capture-target"),
  captureRow: $("capture-row"),
  noteTargetsLine: $("note-targets-line"),
  captureInput: $("capture-input"),
  btnCaptureSend: $("btn-capture-send"),
  flash: $("widget-flash"),
};

/* ==========================================================================
   State
   ========================================================================== */

const state = {
  expanded: false,
  alwaysOnTop: true,
  /** Id of the gate awaiting a decision, or null. */
  approval: null,
  /** `"logseq"`, `"joplin"` or `"obsidian"` — which store the capture field
   *  files to. Only ever one the PC says is set up. */
  captureTarget: "logseq",
  /** Which note apps the PC is set up for (note-capture.js `readTargets`).
   *  Unknown until the PC answers - and unknown shows none, never all. */
  noteTargets: { known: false, why: "not checked yet" },
  /** A note is being filed. Separate from `deciding`: they are unrelated, and
   *  one shared flag meant each silently disabled the other. */
  busy: false,
  /** A decision is in flight. */
  deciding: false,
  /** The id already answered from this window, so a second click cannot send
   *  a contradictory decision before the resolution broadcast lands. */
  decided: null,
  /** A note is being sent for the current approval. Its own flag, on
   *  purpose - `busy` (the Logseq/Joplin capture) and `deciding` already
   *  learned this lesson once: one shared flag makes two unrelated actions
   *  silently no-op each other. */
  noteBusy: false,
  /** A pause/resume/stop request for the running task is in flight - its
   *  own flag for the same reason as `noteBusy` above. */
  taskActionBusy: false,
  /** A note for the running task is being sent. */
  taskNoteBusy: false,
  /** `link.activity` as last reported by the server - "working", "paused",
   *  or "idle". This, and ONLY this, decides whether Resume or Pause is
   *  shown: clicking Pause does not flip it, because a click only proves a
   *  request was SENT, never that the task actually paused. Read the
   *  comment on `sendTaskAction` before changing that - it is the one
   *  honesty rule this whole feature exists to hold. */
  taskActivity: "idle",
  /** App lock is on (Settings, Security). While it is, an approval card
   *  here shows the notice's title only, and Approve opens the Jarvis bar -
   *  behind the lock - instead of approving. See `applyAppLock`. */
  appLock: false,
};

/**
 * Saturation thresholds for VRAM, where running out is a real failure.
 *
 * CPU and GPU *utilisation* are deliberately not coloured this way: a GPU at
 * 95% during inference is the machine working, not the machine in trouble, and
 * an amber bar there would train the eye to ignore the colour that matters.
 */
const WARN_AT = 80;
const CRITICAL_AT = 92;

/** GPU temperature, in °C — this is the GPU number worth a warning colour. */
const TEMP_WARN = 78;
const TEMP_CRITICAL = 87;

/* ==========================================================================
   Native window sizing
   ========================================================================== */

let lastHeight = 0;
let sizeTimer = null;

/**
 * Asks the backend to match the window to the shell.
 *
 * Coalesced for the same reason the spotlight coalesces: each resize is a
 * `SetWindowPos` on an Acrylic-backed transparent window, and DWM recomposites
 * the blur every time.
 */
function syncSize() {
  if (sizeTimer !== null) return;
  sizeTimer = setTimeout(() => {
    sizeTimer = null;
    const height = Math.ceil(dom.shell.getBoundingClientRect().height);
    if (!height || Math.abs(height - lastHeight) < 2) return;
    lastHeight = height;
    invoke("resize_desktop_widget", { expanded: state.expanded, height });
  }, 60);
}

if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(syncSize).observe(dom.shell);
}

/* ==========================================================================
   Focus session (focus.js; JARVIS-API.md section 31)

   A countdown under the bar while a session runs, tinted when the owner is
   off target, with Pause / Resume, Lock on and Stop - ONE thing per tap, no
   card. Resume and Lock on wait while the link is stale (Rust refuses them
   too); Pause and Stop do not. Never what was in front: the PC sends only
   booleans and counts, and says the distraction out loud through the Jarvis
   bar (focus.rs play_callout), not here.
   ========================================================================== */

const focus = { view: null, readAt: 0, triedAt: 0, timer: null, loading: false, again: false,
  readOnce: false };
const FOCUS_WORDS = { drift: "off target", paused: "paused", settling: "settling in",
  on: "on target" };

async function loadFocus() {
  if (!IS_TAURI) return;
  if (focus.loading) {
    focus.again = true;
    return;
  }
  focus.loading = true;
  focus.triedAt = Date.now();
  try {
    const got = await invoke("focus_status");
    if (got) {
      focus.view = readFocus(got);
      focus.readAt = Date.now();
      focus.readOnce = true;
    }
  } finally {
    focus.loading = false;
  }
  if (focus.again) {
    focus.again = false;
    await loadFocus();
    return;
  }
  paintFocus();
}

function focusTickOnce() {
  const v = focus.view;
  if (!v || !v.on) return;
  const left = focusLeftNow(v, Date.now() - focus.readAt);
  dom.focusClock.textContent = focusClock(left);
  // At zero, ask the PC whether it has ended - every 2 s at most, like the
  // Brain, not every second (bug audit 2026-09-26, "possible" list).
  if (left <= 0 && !focus.loading && Date.now() - focus.triedAt > 2000) loadFocus();
}

function syncFocusButtons() {
  if (!dom.focusStrip) return;
  const canAct = linkWords(currentLink()).canAct;
  for (const b of [dom.focusPause, dom.focusLock, dom.focusStop]) {
    const held = FOCUS_HELD.has(b.dataset.action) && !canAct;
    b.disabled = held || b.dataset.busy === "true";
  }
}

function paintFocus() {
  if (!dom.focusStrip) return;
  const v = focus.view;
  const on = Boolean(v && v.available && v.on);
  dom.focusStrip.hidden = !on;
  if (on) {
    const tone = focusToneOf(v);
    dom.focusStrip.dataset.tone = tone;
    dom.focusWord.textContent = v.excused && v.drifting ? "research" : FOCUS_WORDS[tone] || "";
    dom.focusClock.textContent = focusClock(focusLeftNow(v, Date.now() - focus.readAt));
    const [first] = focusActionsOf(v, "widget");
    dom.focusPause.textContent = FOCUS_LABELS[first];
    dom.focusPause.dataset.action = first;
    dom.focusLock.dataset.action = "lock";
    dom.focusLock.title = FOCUS_LOCK_TITLE;
    dom.focusStop.dataset.action = "stop";
    syncFocusButtons();
  }
  const ticking = on && !v.paused;
  if (ticking && !focus.timer) focus.timer = setInterval(focusTickOnce, 1000);
  if (!ticking && focus.timer) {
    clearInterval(focus.timer);
    focus.timer = null;
  }
  syncSize();
}

async function focusAct(button) {
  const action = button.dataset.action;
  if (!action) return;
  button.dataset.busy = "true";
  syncFocusButtons();
  try {
    const out = await invokeStrict("focus_act", { action, minutes: null });
    announce(String((out && out.said) || "Done."));
  } catch (error) {
    announce(String(error && error.message ? error.message : error));
  } finally {
    button.dataset.busy = "false";
  }
  await loadFocus();
}

for (const b of [dom.focusPause, dom.focusLock, dom.focusStop]) {
  if (b) b.addEventListener("click", () => focusAct(b));
}

/* ==========================================================================
   Expand / collapse / pin
   ========================================================================== */

/**
 * Shows or hides the live face preview and starts or stops its animation.
 *
 * The face is a live canvas animating every frame. `hidden` on its wrapper
 * stops it being SEEN but not being DRAWN — an iframe's rAF loop keeps
 * running under `display:none`, so clearing `src` is what actually stops
 * the work rather than just hiding its output. Re-set on every show rather
 * than only the first time, so a face or colour the owner changed while
 * hidden shows up on the next open without this window needing its own
 * copy of the appearance-changed listener.
 *
 * Hidden while collapsed (nothing to see), and ALSO hidden whenever an
 * approval card is open — the single biggest, most purely decorative thing
 * in the tray, freeing the height an urgent, long approval needs to keep
 * Approve on screen rather than clipped past `WIDGET_MAX_HEIGHT`
 * (`src-tauri/src/windows.rs`, 400px — a real, hard ceiling the window
 * cannot grow past, not a soft target).
 *
 * Known, harmless race: prefs (expanded or not) and the pending-approval
 * queue resolve independently at boot. A widget that starts already
 * expanded WITH an approval already waiting briefly starts loading the
 * face before the queue read lands, then cancels that load here a moment
 * later — a real aborted request a strict test harness can flag, with no
 * user-visible effect (nothing was ever painted). Not worth serialising
 * boot on the queue read to close a gap nobody can see.
 */
function applyFaceVisibility() {
  const show = state.expanded && !state.approval;
  if (dom.faceWrap) dom.faceWrap.hidden = !show;
  // `feed=parent`: this window tells the face what to wear and what state to
  // show, the way the HUD does. The frame used to ask for the owner's face
  // itself and was refused - the widget's capability had no appearance
  // permission at all - so the widget always wore the default face in the
  // default colours. And an event sent to this window is delivered to its
  // top-level page, never to a frame inside it, so the frame could not have
  // followed a change anyway. See `postFace`.
  if (dom.faceFrame) dom.faceFrame.src = show ? "faces.html?mode=display&feed=parent" : "";
}

/** The owner's appearance document, as this window last read it. */
let faceAppearance = null;

/** Hands the face frame the state to show and the face to wear. */
function postFace() {
  const frame = dom.faceFrame;
  if (!frame || !frame.contentWindow || !frame.getAttribute("src")) return;
  const message = { type: "jarvis-hud-face", state: surfaceState(currentLink()) };
  if (faceAppearance) message.appearance = faceAppearance;
  try {
    frame.contentWindow.postMessage(message, location.origin);
  } catch (error) {
    /* the frame is mid-navigation; its load event posts again */
  }
}

/**
 * Reads the owner's face. `fromServer` once at boot - `get_appearance` asks
 * Jarvis, so a face or colour changed on the phone arrives - and from memory
 * (`appearance_snapshot`) after that. Never `get_appearance` from inside the
 * `appearance-changed` listener: that command broadcasts the same event, and
 * listening to your own echo is a loop.
 */
async function readFaceAppearance(fromServer) {
  if (!IS_TAURI) return;
  try {
    const doc = await TAURI.core.invoke(fromServer ? "get_appearance" : "appearance_snapshot");
    if (doc && typeof doc === "object") faceAppearance = { face: doc.face || null, bindings: doc.bindings || {} };
  } catch (error) {
    if (fromServer) return readFaceAppearance(false);
  }
  postFace();
}

function applyExpanded(expanded) {
  state.expanded = expanded;
  dom.root.dataset.state = expanded ? "expanded" : "collapsed";
  dom.tray.hidden = !expanded;
  dom.btnToggle.title = expanded ? "Collapse (E)" : "Expand (E)";
  applyFaceVisibility();
  syncSize();
}

async function toggleExpand() {
  applyExpanded(!state.expanded);
  // Send the state change immediately; syncSize follows with the measurement.
  await invoke("resize_desktop_widget", { expanded: state.expanded });
}

async function setPinned(alwaysOnTop) {
  state.alwaysOnTop = alwaysOnTop;
  dom.btnPin.setAttribute("aria-pressed", String(alwaysOnTop));
  dom.btnPin.title = alwaysOnTop
    ? "Floating above other windows"
    : "Pinned to the desktop — active windows cover it";
  await invoke("set_widget_always_on_top", { alwaysOnTop });
}

/* ==========================================================================
   Telemetry rendering
   ========================================================================== */

/** Classifies a 0-100 reading for the meter colour. */
function levelFor(percent) {
  if (percent >= CRITICAL_AT) return "critical";
  if (percent >= WARN_AT) return "warn";
  return "ok";
}

/**
 * Paints one meter. `level` decides the colour and is passed in separately from
 * the width, because the bar's length and its severity are not always the same
 * measurement — the GPU bar shows load but warns on heat.
 */
function paintMeter(meter, bar, percent, available, level = "ok") {
  meter.dataset.available = String(Boolean(available));
  if (!available) {
    bar.style.transform = "scaleX(0)";
    meter.dataset.level = "ok";
    return;
  }
  const clamped = Math.max(0, Math.min(100, percent));
  // scaleX rather than width: see the comment on `.meter-track i`. This runs
  // every three seconds for as long as the widget is open.
  bar.style.transform = `scaleX(${clamped / 100})`;
  meter.dataset.level = level;
}

/** Severity for a GPU temperature reading. */
function tempLevel(celsius) {
  if (!Number.isFinite(celsius)) return "ok";
  if (celsius >= TEMP_CRITICAL) return "critical";
  if (celsius >= TEMP_WARN) return "warn";
  return "ok";
}

function applyTelemetry(data) {
  if (!data) return;

  // CPU is always available.
  const cpu = Number(data.cpuPercent) || 0;
  dom.cpuVal.textContent = `${cpu.toFixed(0)}%`;
  // Neutral colour: a busy CPU is not a fault.
  paintMeter(dom.meterCpu, dom.cpuBar, cpu, true, "ok");

  // GPU and VRAM only exist when nvidia-smi answered.
  const hasVram = Number.isFinite(data.vramUsedMb) && Number.isFinite(data.vramTotalMb) && data.vramTotalMb > 0;
  if (hasVram) {
    const used = data.vramUsedMb / 1024;
    const total = data.vramTotalMb / 1024;
    dom.vramVal.textContent = `${used.toFixed(1)} / ${total.toFixed(1)} GB`;
    const vramPercent = (data.vramUsedMb / data.vramTotalMb) * 100;
    paintMeter(dom.meterVram, dom.vramBar, vramPercent, true, levelFor(vramPercent));
  } else {
    dom.vramVal.textContent = "n/a";
    paintMeter(dom.meterVram, dom.vramBar, 0, false);
  }

  const hasGpu = Number.isFinite(data.gpuUtilPercent) || Number.isFinite(data.gpuTempC);
  if (hasGpu) {
    const util = Number.isFinite(data.gpuUtilPercent) ? data.gpuUtilPercent : 0;
    const temp = Number.isFinite(data.gpuTempC) ? `${data.gpuTempC}°` : "--°";
    dom.gpuVal.textContent = `${util}% · ${temp}`;
    // Length is load; colour is heat.
    paintMeter(dom.meterGpu, dom.gpuBar, util, true, tempLevel(data.gpuTempC));
  } else {
    dom.gpuVal.textContent = "n/a";
    paintMeter(dom.meterGpu, dom.gpuBar, 0, false);
  }

  // Compact readout: temperature is the one number worth a glance when the
  // widget is collapsed.
  if (Number.isFinite(data.gpuTempC)) {
    dom.gpuTemp.textContent = `${data.gpuTempC}°`;
    dom.gpuTemp.classList.toggle("hot", data.gpuTempC >= TEMP_WARN);
    dom.gpuTemp.classList.toggle("critical", data.gpuTempC >= TEMP_CRITICAL);
  } else {
    dom.gpuTemp.textContent = `${Math.round(cpu)}%`;
    dom.gpuTemp.title = "CPU load (no NVIDIA GPU detected)";
  }

  if (data.routeLane) applyLane(data.routeLane);
}

/** Paints the route pill. */
function applyLane(lane) {
  const value = String(lane).toLowerCase();
  const cloud = /cloud|remote|escalat/.test(value);
  const offline = value === "offline";
  dom.routePill.dataset.lane = offline ? "offline" : cloud ? "cloud" : "local";
  dom.routePill.textContent = String(lane).toUpperCase();
}

/** Paints the connection dot from a health report. */
function applyHealth(report) {
  if (!report || !Array.isArray(report.services)) return;
  // An optional service (LiteLLM, the cloud lane's proxy) counts only when it
  // answers - not running is normal with no cloud model set up. Same rule as
  // commands.rs summarise_health.
  const counted = report.services.filter((s) => s.online || !s.optional);
  const online = counted.filter((s) => s.online).length;
  dom.netDot.classList.toggle("online", online === counted.length);
  dom.netDot.classList.toggle("partial", online > 0 && online < counted.length);
  dom.netDot.title = report.summary || "Core connection";
  // The shape and the hue are for the eye. This is the same fact in words.
  const word = online === counted.length
    ? "all local services answered"
    : online > 0
      ? "some local services answered"
      : "no local service answered";
  dom.netDot.setAttribute("role", "img");
  dom.netDot.setAttribute("aria-label", `Connection: ${word}`);

  const core = report.services.find((s) => s.id === "jarvis");
  if (core && !core.online) applyLane("offline");
}

/* ==========================================================================
   Approval gates
   ========================================================================== */

/**
 * One line describing what the agent wants to do.
 *
 * `detail` reaches here already parsed by the link module — an object when the
 * gate's JSON survived its 4000-character truncation, the raw string when it
 * did not.
 */
function approvalDetail(approval) {
  const detail = approval.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim().split("\n")[0].slice(0, 200);
  }
  if (detail && typeof detail === "object") {
    for (const key of ["preview", "summary", "content", "command", "diff", "text"]) {
      const value = detail[key];
      if (typeof value === "string" && value.trim()) {
        return value.trim().split("\n")[0].slice(0, 200);
      }
    }
    return JSON.stringify(detail).slice(0, 200);
  }
  if (approval.prompt.trim()) return approval.prompt.trim().split("\n")[0].slice(0, 200);
  return "No detail supplied.";
}

/* App lock and this window (apps security audit M3; the owner's decision,
 * 2026-09-25). The widget sits on the desktop outside the lock, where anyone
 * at the PC can read it. So while App lock is on its approval card shows only
 * the notice's short title - never `detail`, `prompt`, the rush quote or the
 * options, which can quote an email or a file - and its Approve opens the
 * Jarvis bar, which asks Windows Hello before it shows, to approve there.
 * Deny stays here, as on the phone's widget: refusing never needs the lock.
 * Rust holds the same rule in `decide_approval`, so this is the courtesy and
 * that is the gate. */
const LOCKED_TITLE = "Jarvis is waiting for your approval";
const LOCKED_DETAIL = "App lock is on, so what this is for is shown in the Jarvis bar, not here.";
const LOCKED_APPROVE = "Approve in the Jarvis bar";

/** The one line shown about a card while App lock is on. */
function lockedTitle(approval) {
  const title = approval && approval.notice && typeof approval.notice.title === "string"
    ? approval.notice.title.trim()
    : "";
  return title ? clip(title, 80) : LOCKED_TITLE;
}

/** App lock turned on or off (read at start, then `security-changed`). */
function applyAppLock(on) {
  const next = Boolean(on);
  if (next === state.appLock) return;
  state.appLock = next;
  // Repaint the card on screen under the new rule. Same id, so nothing is
  // announced again and a half-typed note is kept.
  if (state.approval) openApproval(state.approval);
  syncTaskControls();
}

/** Whether App lock is on. Fails closed: a read that fails is treated as on,
 *  which only means Approve opens the Jarvis bar. */
async function readAppLock() {
  try {
    return (await invokeStrict("get_app_lock")) !== false;
  } catch (error) {
    console.error("[widget] could not read whether App lock is on:", error);
    return true;
  }
}

/** Approve while App lock is on, or on an email: open the Jarvis bar on this
 *  card. */
async function approveInBar() {
  flash("Opening the Jarvis bar - approve it there.");
  try {
    await invokeStrict("open_approval_in_quickbar");
  } catch (error) {
    flash(`${String((error && error.message) || error)} - nothing was decided.`, "bad");
  }
}

/**
 * Renders the gate.
 *
 * Driven by the queue the backend read, never by anything this window worked
 * out for itself: one list, one moment, three surfaces showing the same thing.
 */
function openApproval(approval) {
  // A different gate releases the "already answered" latch. Deliberately not
  // released in `closeApproval`: `decide_approval` does not re-read the queue,
  // so between answering and the server's next event the same card can be
  // reopened, and clearing on close would disarm the latch exactly then.
  if (state.decided && state.decided !== approval.id) state.decided = null;
  // The gate no longer claims `alertdialog`, so it announces itself — with the
  // risk line, which is the part that changes the decision.
  const locked = state.appLock;
  if (!state.approval || state.approval.id !== approval.id) {
    announce(
      `${CARD_KICKER}: ${locked ? lockedTitle(approval) : cardTitle(approval)}. ${riskLine(approval.risk)}.`,
      "assertive"
    );
  }
  const fresh = !state.approval || state.approval.id !== approval.id;
  state.approval = approval;
  // An email is approved in the Jarvis bar, lock or not: this card shows
  // one line, and an email's card is its recipients, subject and every word
  // (the owner's decision of 2026-09-25). Rust refuses an email's Approve
  // from this window too (commands.rs, `waiting_email`).
  const email = isEmailCard(approval);
  // The PC's own words for it (card-words.js), never the code name.
  dom.apprAction.textContent = locked ? lockedTitle(approval) : cardTitle(approval);
  // textContent, never innerHTML: this string comes from a model.
  dom.apprDetail.textContent = locked ? LOCKED_DETAIL
    : email ? EMAIL_DETAIL : approvalDetail(approval);
  dom.btnApprYes.textContent = locked ? LOCKED_APPROVE : email ? EMAIL_APPROVE : "Approve";
  dom.btnApprYes.title = locked
    ? "App lock is on: opens the Jarvis bar, which asks Windows Hello, to approve there"
    : email ? "Opens the Jarvis bar on this email, to read all of it and approve there" : "";
  // A note changes the plan, so it waits for the unlocked Jarvis bar too.
  const noteRow = dom.apprNoteInput.closest(".appr-note-row");
  if (noteRow) noteRow.hidden = locked;
  dom.apprRisk.textContent = riskLine(approval.risk);
  dom.apprRisk.dataset.reversible = approval.risk ? approval.risk.reversible : "no";

  // Why this is being asked at all. `text` already carries its own "(4th time
  // today)" when the source has tripped this repeatedly; nothing here counts.
  // Both strings are hostile text by definition and go in as textContent.
  // Not while App lock is on: the quote is outside text, word for word.
  const raised = locked ? null : approval.raised;
  dom.apprRaised.hidden = !raised;
  dom.apprRaisedChip.textContent = raised ? raised.text : "";
  dom.apprRaisedQuote.textContent = raised && raised.quote ? `“${raised.quote}”` : "";
  dom.apprRaisedQuote.hidden = !(raised && raised.quote);
  renderOptions(approval);
  // ONLY on a different card - `fresh` is already computed above. The old
  // comment here said this was "safe unconditionally" and it was not:
  // openApproval() runs again for the SAME gate on every queue re-read, and
  // each one deleted whatever was half-typed in the note, with no undo. A
  // genuinely new card arrives with the field already empty - closeApproval()
  // clears it.
  if (fresh) dom.apprNoteInput.value = "";
  dom.apprCard.hidden = false;
  applyFaceVisibility();
  syncApprovalButtons();
  // A gate is the one thing worth opening the widget for on its own — but only
  // when it is a new one, or re-reading the queue would keep re-expanding a
  // widget the user had just collapsed.
  if (fresh && !state.expanded) toggleExpand();
  else syncSize();
}

/**
 * Renders a plan's options — docs/AUTONOMY-PROPOSALS.md §3a.
 *
 * Zero or one option: `.appr-options` stays empty and hidden, and the
 * static Approve button (below) is the only way to approve — the exact
 * behaviour this card had before options existed at all. Two or more:
 * the static Approve button is hidden (Deny is not — denying never needs
 * to say which option) and one button per option appears instead.
 *
 * Those per-option buttons are rendered **disabled**, for the same reason
 * and the same way `main.js`'s copy of this function is - see its comment.
 * Short version: `decide_approval` in Rust never receives `option_id` at
 * all (docs/JARVIS-API.md §8), so before this fix every option button sent
 * the identical `/api/approve` request with nothing saying which plan was
 * meant. jarvis-client's `needsChoice` (`ApiModels.kt`) took the same way
 * out first.
 */
function renderOptions(approval) {
  // No options while App lock is on: their labels are the plan's own words,
  // and the one button then opens the Jarvis bar, which shows them.
  const options = !state.appLock && Array.isArray(approval.options) ? approval.options : [];
  dom.apprOptions.replaceChildren();
  const multiple = options.length > 1;
  dom.apprOptions.hidden = !multiple;
  dom.btnApprYes.hidden = multiple;
  dom.apprOptionsWhy.hidden = !multiple;
  dom.apprOptionsWhy.textContent = multiple
    ? `Jarvis offered ${options.length} ways to do this. The desktop can't yet tell it which one you picked, so approving is off here. Deny still works.`
    : "";
  if (!multiple) return;
  for (const option of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "appr-option";
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
    dom.apprOptions.append(btn);
  }
}

function closeApproval() {
  state.approval = null;
  dom.apprCard.hidden = true;
  dom.apprOptions.replaceChildren();
  dom.apprOptions.hidden = true;
  dom.apprOptionsWhy.hidden = true;
  dom.apprCount.hidden = true;
  dom.btnApprYes.hidden = false;
  dom.apprNoteInput.value = "";
  applyFaceVisibility();
  syncSize();
}

/**
 * Enables the buttons only while the stream can confirm the queue is live.
 * Answering one that cannot be confirmed is how the same thing gets approved
 * twice, from two surfaces, seconds apart.
 */
function syncApprovalButtons() {
  // `deciding`, not `busy`: `busy` is the capture box's flag (see its own
  // note), so the old `stale || busy` left Approve and Deny live-looking while
  // a decision was on its way - a second click silently swallowed by the
  // latch - and greyed them for no reason while a note was being filed. The
  // quickbar has always used `stale || deciding`.
  const link = currentLink();
  const blocked = link.stale || state.deciding;
  // A cut-off request cannot be approved - see the quickbar's twin.
  dom.btnApprYes.disabled = blocked || Boolean(state.approval && state.approval.cutOff);
  dom.btnApprNo.disabled = blocked;
  paintApprovalClock();
  // And say why, on the card. Two grey buttons and nothing else was all the
  // widget showed while the queue could not be confirmed.
  const why = link.stale
    ? `${linkWords(link).short} — the approval queue cannot be confirmed, so nothing can be answered from here.`
    : state.deciding
      ? "That decision is on its way."
      : "";
  dom.apprWhy.hidden = !why;
  dom.apprWhy.textContent = why;
  dom.apprWhy.dataset.tone = link.stale ? "bad" : "";
  // Not `= blocked`: `renderOptions` leaves these permanently disabled (see
  // its own comment), and `= blocked` would re-enable them once the stream
  // stopped being stale.
  if (blocked) for (const opt of dom.apprOptions.children) opt.disabled = true;
  // The note is a separate action from deciding (see `state.noteBusy`'s own
  // comment) but it still needs the stream live to mean anything, and it
  // still needs to stop once a decision on THIS card is in flight or has
  // already landed — sending a note for a plan already being decided would
  // arrive after the fact.
  const noteBlocked = blocked || state.noteBusy || state.deciding
    || (state.approval && state.decided === state.approval.id);
  dom.apprNoteInput.disabled = noteBlocked;
  dom.btnApprNoteSend.disabled = noteBlocked;
}

/**
 * The risk line, plus how long the card has left or why Approve is off for a
 * request that was cut off. Re-painted every second, and only this line.
 */
function paintApprovalClock() {
  const approval = state.approval;
  if (!approval) return;
  const parts = [riskLine(approval.risk)];
  if (approval.cutOff) {
    parts.push("Cut off before it reached this card, so it cannot be approved here - deny it and ask Jarvis for a shorter plan.");
  }
  const clock = expiryWords(approval.expiresAt);
  if (clock) parts.push(clock);
  const text = parts.join(" · ");
  if (dom.apprRisk.textContent !== text) dom.apprRisk.textContent = text;
}
setInterval(() => {
  if (state.approval && !dom.apprCard.hidden) paintApprovalClock();
}, 1000);

async function decide(approved, optionId = null) {
  if (!state.approval || state.deciding) return;
  // App lock on: this window approves nothing (see `applyAppLock`). Nor,
  // lock or not, an email: all of it is read in the Jarvis bar first.
  if (approved && (state.appLock || isEmailCard(state.approval))) {
    await approveInBar();
    return;
  }
  // The id latch the spotlight has and this window did not. `deciding` is
  // released in `finally`, but the card only closes when the backend
  // broadcasts the resolution — so between those two moments a second click
  // sent a SECOND, contradictory decision for the same action. Only the
  // server's 409 stood between that and a real double-decide.
  if (state.decided === state.approval.id) return;
  state.decided = state.approval.id;
  // `deciding`, not the shared `busy`. One flag served both this and the note
  // field, so filing a note — which runs a whole chat turn and takes seconds —
  // made Approve and Deny into live-looking no-ops with no feedback, and an
  // in-flight decision silently swallowed Enter in the capture field.
  state.deciding = true;
  syncApprovalButtons();
  // The same words the quickbar uses, so the grey buttons have a reason.
  flash(approved ? "Approving…" : "Denying…");

  try {
    await decideOnBackend(state.approval.id, approved, optionId);
    // The backend broadcasts approval-resolved, which closes the card.
    flash(approved ? "Approved." : "Denied.", approved ? "ok" : null);
  } catch (error) {
    const message = String((error && error.message) || error);
    // 409 means the id is unknown, expired, or already decided. Someone
    // answered it — that is not an error to shout about.
    const handled = /409|already/i.test(message);
    // Release the latch ONLY here, and only when the decision genuinely did
    // not land. A 409 means it was answered somewhere else, so the latch
    // stays. Releasing in `finally` instead would release it on SUCCESS too,
    // which is the whole thing the latch exists to prevent.
    if (!handled) state.decided = null;
    flash(handled ? "Already handled elsewhere."
      : /^Nothing was approved\./.test(message) ? message : `${message} — nothing was decided.`,
          handled ? null : "bad");
  } finally {
    state.deciding = false;
    syncApprovalButtons();
  }
}

/* ==========================================================================
   Quick capture
   ========================================================================== */

function setCaptureTarget(target) {
  state.captureTarget = target;
  dom.captureTarget.dataset.target = target;
  dom.captureTarget.textContent = (TARGETS[target] || TARGETS.logseq).prefix;
  const where = {
    logseq: "the Logseq journal",
    joplin: "Joplin",
    obsidian: "today's Obsidian daily note",
  }[target] || targetName(target);
  const more = readyTargets().length > 1;
  dom.captureTarget.title = `Filing to ${where}${more ? " — click to switch" : ""}`;
  dom.captureTarget.setAttribute("aria-label",
    `Capture target: ${where}.${more ? " Activate to switch to the next note app." : ""}`);
}

/** The note apps the PC said are set up - empty while that is not known. */
function readyTargets() {
  return state.noteTargets.known ? state.noteTargets.targets : [];
}

/**
 * Shows a button and a capture target only for a note app the PC is set up
 * for. None set up, or the PC could not be asked: no capture field, and one
 * line saying which.
 */
function syncNoteTargets() {
  const ready = readyTargets();
  dom.btnLog.hidden = !ready.includes("logseq");
  dom.btnJoplin.hidden = !ready.includes("joplin");
  dom.btnObs.hidden = !ready.includes("obsidian");
  dom.captureRow.hidden = ready.length === 0;
  dom.noteTargetsLine.hidden = ready.length > 0;
  if (!ready.length) dom.noteTargetsLine.textContent = noTargetsLine(state.noteTargets);
  if (ready.length) {
    setCaptureTarget(ready.includes(state.captureTarget) ? state.captureTarget : ready[0]);
  }
}

async function refreshNoteTargets() {
  state.noteTargets = await loadTargets(invokeStrict);
  syncNoteTargets();
}

let flashTimer = null;

/** Shortens a sentence for a 320px window without cutting mid-word. */
function clip(text, max) {
  const t = String(text).trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).trimEnd()}…`;
}

/**
 * Shows a transient one-line status under the capture field.
 *
 * `title` is for the sentence that does not fit in 320px but that the reader
 * needs when the short version could be misread — "sent" versus "filed", for
 * one.
 */
function flash(message, tone, title) {
  // `#widget-flash` is hidden when it is written and revealed afterwards,
  // which is the pattern that reliably says nothing. The shared region is
  // always present, so this is the half that actually speaks.
  announce(message);
  dom.flash.textContent = message;
  if (title) dom.flash.title = title;
  else dom.flash.removeAttribute("title");
  if (tone) dom.flash.dataset.tone = tone;
  else delete dom.flash.dataset.tone;
  dom.flash.hidden = false;
  syncSize();

  if (flashTimer !== null) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    dom.flash.hidden = true;
    flashTimer = null;
    syncSize();
  }, 2600);
}

async function sendCapture() {
  const text = dom.captureInput.value.trim();
  if (!text || state.busy) return;

  state.busy = true;
  dom.captureInput.disabled = true;
  dom.btnCaptureSend.disabled = true;
  flash("Filing…");

  try {
    // The PC's own answer, not a model's account (note-capture.js): "Filed"
    // only once the backend has written the note and read it back. This used
    // to ask a model to call a tool that did not exist and could only say
    // "Sent". While an approval card waits, the field is free again - the
    // result arrives in the flash when the card is answered.
    const target = state.captureTarget;
    let first = true;
    await fileNote(invokeStrict, target, text, (said) => {
      if (first) {
        dom.captureInput.value = "";
        first = false;
        state.busy = false;
        dom.captureInput.disabled = false;
        dom.btnCaptureSend.disabled = false;
      }
      flash(clip(said.text, 90), said.tone, said.text);
    });
  } catch (error) {
    flash(String((error && error.message) || error), "bad");
  } finally {
    state.busy = false;
    dom.captureInput.disabled = false;
    dom.btnCaptureSend.disabled = false;
    dom.captureInput.focus();
  }
}

/**
 * Sends a note before the first decision on the open card —
 * docs/AUTONOMY-PROPOSALS.md §3b. Approves nothing: the expected result is
 * a NEW proposal for the same id, arriving the normal way through the
 * queue, which `onQueue` below already repaints from — this function does
 * not apply anything itself, only sends the text and reports whether it
 * landed.
 */
async function sendNote() {
  const note = dom.apprNoteInput.value.trim();
  if (!note || !state.approval || state.noteBusy) return;
  const id = state.approval.id;

  state.noteBusy = true;
  syncApprovalButtons();
  flash("Sending your note…");

  try {
    await amendOnBackend(id, note);
    dom.apprNoteInput.value = "";
    // task-control.patch keeps the note WITH the card; it does not re-plan
    // on its own. The model reads it together with the owner's answer.
    flash("Note kept with this card.", "ok", "Nothing was approved or denied, and the card is unchanged. Jarvis reads your note together with your answer - to have it plan differently, deny the card.");
  } catch (error) {
    flash(String((error && error.message) || error), "bad");
  } finally {
    state.noteBusy = false;
    syncApprovalButtons();
  }
}

/* ==========================================================================
   Task controls - pause, stop, and inject-while-running
   docs/AUTONOMY-PROPOSALS.md §3d
   ========================================================================== */

/**
 * Enables/disables the buttons and picks Pause vs. Resume.
 *
 * The swap answers only to `state.taskActivity`, which is set in exactly one
 * place — the `onLink` handler below, reading the server's own broadcast —
 * never by a click here. A click can fail silently, reach a backend that
 * has not implemented pausing at all, or race a resolution that already
 * happened; the one thing this window can trust is what the server itself
 * last said it was doing, the same rule `approval-resolved` already uses to
 * decide when a gate is actually closed rather than just answered.
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
  // App lock covers task notes too (the owner's decision of 2026-09-26),
  // like the card's note: a note steers what Jarvis does next, so it waits
  // for the unlocked Jarvis bar. Rust refuses it from this window as well.
  const taskNoteRow = dom.taskNoteInput.closest(".task-note-row");
  if (taskNoteRow) taskNoteRow.hidden = state.appLock;
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
 * paused, resumed, or stopped anything - the button swap has to wait for
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
      flash("Pause requested — sent.", "ok",
        "Jarvis was asked to pause. This button will only say Resume once " +
          "Jarvis itself reports it has actually paused.");
    } else if (kind === "resume") {
      await resumeTask();
      // Resume only ASKS (task-control.patch): the server raises an
      // approval card listing the steps left, and nothing runs until that
      // card is approved. Saying "resumed" here would be untrue.
      flash("Resume asks first — see the card.", "ok",
        "Resume sent. Nothing runs yet: Jarvis shows an approval card listing the steps that are left, and continues only if you approve it.");
    } else {
      await stopTask();
      flash("Stop sent.", "ok",
        "Stop sent. Jarvis stops before its next step; steps already done stay done. The buttons change when Jarvis reports it has stopped.");
    }
  } catch (error) {
    flash(String((error && error.message) || error), "bad");
  } finally {
    state.taskActionBusy = false;
    syncTaskControls();
  }
}

/**
 * Sends a note that applies to what the running task does next - it never
 * touches whatever step is already in flight, same rule as `sendNote()`
 * above for an approval that has not been decided yet.
 */
async function sendTaskNote() {
  const note = dom.taskNoteInput.value.trim();
  if (!note || state.taskNoteBusy || state.appLock) return;

  state.taskNoteBusy = true;
  syncTaskControls();
  flash("Sending your note…");

  try {
    await injectTaskNote(note);
    dom.taskNoteInput.value = "";
    flash(
      "Sent — applies to what Jarvis does next.",
      "ok",
      "Jarvis reads it when the current step finishes. It changes no step " +
        "you already approved."
    );
  } catch (error) {
    flash(String((error && error.message) || error), "bad");
  } finally {
    state.taskNoteBusy = false;
    syncTaskControls();
  }
}

/* ==========================================================================
   Events
   ========================================================================== */

dom.btnToggle.addEventListener("click", toggleExpand);
dom.btnPin.addEventListener("click", () => setPinned(!state.alwaysOnTop));

dom.btnLog.addEventListener("click", () => invoke("prefill_quickbar", { target: "logseq" }));
dom.btnJoplin.addEventListener("click", () => invoke("prefill_quickbar", { target: "joplin" }));
dom.btnObs.addEventListener("click", () => invoke("prefill_quickbar", { target: "obsidian" }));

dom.btnApprYes.addEventListener("click", () => decide(true));
dom.btnApprNo.addEventListener("click", () => decide(false));
dom.btnApprNoteSend.addEventListener("click", sendNote);
dom.apprNoteInput.addEventListener("keydown", (event) => {
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

dom.captureTarget.addEventListener("click", () => {
  // The next note app that is set up, round and round.
  const ready = readyTargets();
  if (ready.length < 2) return;
  setCaptureTarget(ready[(ready.indexOf(state.captureTarget) + 1) % ready.length]);
});
dom.btnCaptureSend.addEventListener("click", sendCapture);
dom.offlineRetry.addEventListener("click", async () => {
  dom.offlineText.textContent = "Reconnecting…";
  await invoke("refresh_link");
});
dom.captureInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendCapture();
  } else if (event.key === "Escape") {
    event.preventDefault();
    dom.captureInput.value = "";
    dom.captureInput.blur();
  }
});

/**
 * The keyboard's way in and out.
 *
 * The widget is `focus: false` and `skipTaskbar: true`: it is not in the
 * Alt+Tab order and nothing used to give it the keyboard, so every control in
 * it — including an approval gate — was mouse-only. `toggle_widget` now focuses
 * it on show, which makes Alt+Shift+W the way in; this is the way out, and the
 * two shortcuts for the things that are otherwise a hunt through eight
 * unlabelled icon buttons.
 */
window.addEventListener("keydown", (event) => {
  // The capture field owns its own Escape (clear, then blur), so a person
  // mid-note is not thrown out of the window by the key that means "undo the
  // last thing I typed".
  if (event.target === dom.captureInput) return;
  if (event.altKey || event.ctrlKey || event.metaKey) return;

  if (event.key === "Escape") {
    event.preventDefault();
    invoke("hide_widget");
    return;
  }
  // A gate is never one keystroke away. Approve and Deny stay where they are,
  // reachable by Tab like everything else, because a hotkey that answers a
  // gate is a hotkey that answers it by accident.
  if (event.key.toLowerCase() === "e") {
    event.preventDefault();
    toggleExpand();
  } else if (event.key.toLowerCase() === "n") {
    event.preventDefault();
    if (!state.expanded) toggleExpand();
    dom.captureInput.focus();
  }
});

// Persist the position once the drag ends rather than on every mouse move.
window.addEventListener("mouseup", () => invoke("save_widget_position", {}));

listen("desktop-telemetry", (event) => applyTelemetry(event.payload));
listen("health-report", (event) => applyHealth(event.payload));
// `approval-requested` is gone: it was the quickbar telling this window what
// it had found in a chat chunk, which made two surfaces the authority on the
// same queue. The queue below is read once, by Rust, from /api/pending.
listen("approval-resolved", (event) => {
  // Check the id. This used to close unconditionally, so resolving one gate
  // hid a different one that was still pending - and the queue re-read that
  // followed then force-expanded a widget the user may have collapsed.
  const resolved = event.payload;
  if (!state.approval) return;
  if (resolved && resolved.id && String(resolved.id) !== state.approval.id) return;
  closeApproval();
});

/* ==========================================================================
   Boot
   ========================================================================== */

(async () => {
  setCaptureTarget("logseq");
  syncNoteTargets();
  refreshNoteTargets();
  // Asked again each time the widget is focused, so an app set up since shows.
  window.addEventListener("focus", () => refreshNoteTargets());
  syncTaskControls();

  // App lock first, so a card already waiting is never drawn in full.
  applyAppLock(await readAppLock());
  listen("security-changed", (event) => applyAppLock(event.payload && event.payload.appLock));

  // Restore the mode the user left the widget in.
  const prefs = await invoke("get_widget_prefs");
  applyExpanded(Boolean(prefs && prefs.expanded));
  await setPinned(prefs ? Boolean(prefs.alwaysOnTop) : true);

  // One stream, owned by Rust, fanned out to all three surfaces.
  followTheme();
  // The widget measures itself and asks Rust to match, so a zoom step has to
  // re-measure or the frame keeps the old height around the new text.
  followZoom(() => syncSize());
startLink();

  // Focus session: read once now, again on every `focus` event and when the
  // link comes back; counted down here once a second in between.
  onEvent((frame) => {
    if (frame && frame.kind === "focus") loadFocus();
  });
  loadFocus();

  onLink((link) => {
    // A held-open event stream is a stronger liveness signal than a probe that
    // succeeded a moment ago, so the lane pill follows it directly.
    if (!link.connected) applyLane("offline");

    // Offline used to be reported and never acted on: the dot went red, the
    // pill said OFFLINE, and there was nothing anywhere in this window to do
    // about it. And connected-but-stale showed nothing at all, while Approve
    // and Deny quietly went grey. Both now say what is wrong, in the same
    // words every window uses (linkWords), red for offline, amber for stale.
    const words = linkWords(link);
    dom.offline.hidden = words.canAct;
    if (!words.canAct) {
      dom.offlineText.textContent = clip(words.text, 110);
      dom.offlineText.title = link.error || "";
      dom.offline.dataset.tone = words.tone;
    }
    postFace();

    // Live progress — docs/AUTONOMY-PROPOSALS.md §3c. Only shown while
    // something is actually reported in progress; offline already has its
    // own row above, and an idle Jarvis has nothing to narrate.
    const working = link.connected && link.activity === "working";
    const detail = working ? link.activityDetail : "";
    dom.widgetProgress.hidden = !detail;
    if (detail) dom.widgetProgress.textContent = detail;

    // Pause/stop/inject — docs/AUTONOMY-PROPOSALS.md §3d. `activity` is the
    // one field this window trusts for whether a task is live at all, and
    // "paused" counts as live: a paused task still has a card worth showing
    // controls on, per §3d ("`not_run` steps stay live rather than closed
    // out"). Anything else - idle, disconnected, or a value neither client
    // nor server has defined - means there is nothing to pause, stop, or
    // note, and a stale Resume from a task that already ended cannot carry
    // over into whatever runs next.
    state.taskActivity = link.connected ? link.activity : "idle";
    dom.taskControls.hidden = state.taskActivity !== "working" && state.taskActivity !== "paused";
    syncTaskControls();

    syncApprovalButtons();
    syncFocusButtons();
    if (link.connected && !focus.readOnce) loadFocus();
    syncSize();
  });

  onQueue((queue) => {
    const open = queue.items[0] || null;
    if (open) openApproval(open);
    else if (state.approval) closeApproval();
    // "1 of 3", the quickbar's wording. A number only - nothing here acts on
    // more than the one card on screen.
    const total = queue.items.length;
    dom.apprCount.hidden = !open || total < 2;
    dom.apprCount.textContent = open && total > 1 ? `1 of ${total}` : "";
    postFace();
  });

  // The face frame: posted to when it loads and whenever what it shows
  // changes. Read once from Jarvis (so a phone change arrives), then from
  // memory on every change.
  if (dom.faceFrame) dom.faceFrame.addEventListener("load", postFace);
  listen("appearance-changed", () => readFaceAppearance(false));
  readFaceAppearance(true);

  // Ollama and the LiteLLM proxy are not on the bus, so their dots still need
  // one probe. Once, at boot — there is no timer here any more.
  const report = await invoke("check_server_health");
  if (report) applyHealth(report);

  syncSize();
  console.info(
    `[widget] ready - backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
  );
})();
