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
  onLink,
  onQueue,
  pauseTask,
  resumeTask,
  riskLine,
  stopTask,
  followTheme,
  followZoom,
  start as startLink,
} from "./jarvis-link.js";

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
  /** `"logseq"` or `"joplin"` — which store the capture field files to. */
  captureTarget: "logseq",
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
  if (dom.faceFrame) dom.faceFrame.src = show ? "faces.html?mode=display" : "";
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
  const online = report.services.filter((s) => s.online).length;
  dom.netDot.classList.toggle("online", online === report.services.length);
  dom.netDot.classList.toggle("partial", online > 0 && online < report.services.length);
  dom.netDot.title = report.summary || "Core connection";
  // The shape and the hue are for the eye. This is the same fact in words.
  const word = online === report.services.length
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
  if (!state.approval || state.approval.id !== approval.id) {
    announce(
      `Approval required: ${approval.action}. ${riskLine(approval.risk)}.`,
      "assertive"
    );
  }
  const fresh = !state.approval || state.approval.id !== approval.id;
  state.approval = approval;
  dom.apprAction.textContent = approval.action;
  // textContent, never innerHTML: this string comes from a model.
  dom.apprDetail.textContent = approvalDetail(approval);
  dom.apprRisk.textContent = riskLine(approval.risk);
  dom.apprRisk.dataset.reversible = approval.risk ? approval.risk.reversible : "no";

  // Why this is being asked at all. `text` already carries its own "(4th time
  // today)" when the source has tripped this repeatedly; nothing here counts.
  // Both strings are hostile text by definition and go in as textContent.
  const raised = approval.raised;
  dom.apprRaised.hidden = !raised;
  dom.apprRaisedChip.textContent = raised ? raised.text : "";
  dom.apprRaisedQuote.textContent = raised && raised.quote ? `“${raised.quote}”` : "";
  dom.apprRaisedQuote.hidden = !(raised && raised.quote);
  renderOptions(approval);
  // A note about a still-open card is stale; a note about a fresh one has
  // nothing typed yet either way, so this is safe unconditionally.
  dom.apprNoteInput.value = "";
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
 * to say which option) and one button per option appears instead, each a
 * full plan of its own to approve, never a modifier on a shared one.
 */
function renderOptions(approval) {
  const options = Array.isArray(approval.options) ? approval.options : [];
  dom.apprOptions.replaceChildren();
  const multiple = options.length > 1;
  dom.apprOptions.hidden = !multiple;
  dom.btnApprYes.hidden = multiple;
  if (!multiple) return;
  for (const option of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "appr-option";
    btn.dataset.optionId = option.id;
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
    btn.addEventListener("click", () => decide(true, option.id));
    dom.apprOptions.append(btn);
  }
}

function closeApproval() {
  state.approval = null;
  dom.apprCard.hidden = true;
  dom.apprOptions.replaceChildren();
  dom.apprOptions.hidden = true;
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
  const blocked = currentLink().stale || state.busy;
  dom.btnApprYes.disabled = blocked;
  dom.btnApprNo.disabled = blocked;
  for (const opt of dom.apprOptions.children) opt.disabled = blocked;
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

async function decide(approved, optionId = null) {
  if (!state.approval || state.deciding) return;
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
    flash(handled ? "Already handled elsewhere." : `${message} — nothing was decided.`,
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
  dom.captureTarget.textContent = target === "joplin" ? "#jop" : "#log";
  dom.captureTarget.title =
    target === "joplin"
      ? "Filing to the Joplin vault — click to switch"
      : "Filing to the Logseq journal — click to switch";
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
    // What comes back is the model's own account of what it did, not a receipt.
    // `/api/chat` runs a chat turn whose system message ASKS for
    // `append_logseq_journal`; a model can decline it, not have it, or answer
    // in prose, and HTTP 200 covers all three. This used to say "Appended to
    // Logseq." on any 200 — a confident claim about a file the desktop has
    // never seen and cannot check.
    const reply = String((await invokeStrict("capture_note", {
      target: state.captureTarget,
      text,
    })) || "").trim();
    dom.captureInput.value = "";
    const where = state.captureTarget === "joplin" ? "Joplin" : "Logseq";
    const first = reply.split("\n").find((l) => l.trim()) || "";
    flash(
      first ? `Sent to ${where} — ${clip(first, 70)}` : `Sent to ${where}.`,
      "ok",
      `Jarvis was asked to file this in ${where}. What it says it did is above; ` +
        `the desktop has no way to confirm the note landed.`
    );
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
    flash(
      "Sent — waiting for a new proposal.",
      "ok",
      "Jarvis will read this note and propose again for the same request; " +
        "nothing has been approved or denied."
    );
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
}

/**
 * Sends a pause, resume, or stop request for whatever Jarvis is running
 * right now. DRAFT: `pause_task`/`resume_task`/`stop_task` may not exist as
 * Rust commands yet - same situation `amend_approval` was in before it got
 * one - so a rejected invoke surfaces its real error rather than pretending
 * the task's state changed.
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
      flash("Resume requested — sent.", "ok",
        "Jarvis was asked to resume. This button will only say Pause again " +
          "once Jarvis itself reports it has actually resumed.");
    } else {
      await stopTask();
      flash("Stop requested — sent.", "ok",
        "Jarvis was asked to stop. The desktop has no way to confirm it actually did.");
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
  if (!note || state.taskNoteBusy) return;

  state.taskNoteBusy = true;
  syncTaskControls();
  flash("Sending your note…");

  try {
    await injectTaskNote(note);
    dom.taskNoteInput.value = "";
    flash(
      "Sent — applies to what Jarvis does next.",
      "ok",
      "This does not change the step already running, and the desktop has " +
        "no way to confirm Jarvis read it."
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

dom.captureTarget.addEventListener("click", () =>
  setCaptureTarget(state.captureTarget === "logseq" ? "joplin" : "logseq")
);
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
  syncTaskControls();

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

  onLink((link) => {
    // A held-open event stream is a stronger liveness signal than a probe that
    // succeeded a moment ago, so the lane pill follows it directly.
    if (!link.connected) applyLane("offline");

    // Offline used to be reported and never acted on: the dot went red, the
    // pill said OFFLINE, and there was nothing anywhere in this window to do
    // about it.
    dom.offline.hidden = link.connected;
    if (!link.connected) {
      dom.offlineText.textContent = link.error
        ? clip(`Not answering: ${link.error}`, 90)
        : "Jarvis is not answering.";
    }

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
    syncSize();
  });

  onQueue((queue) => {
    const open = queue.items[0] || null;
    if (open) openApproval(open);
    else if (state.approval) closeApproval();
  });

  // Ollama and the LiteLLM proxy are not on the bus, so their dots still need
  // one probe. Once, at boot — there is no timer here any more.
  const report = await invoke("check_server_health");
  if (report) applyHealth(report);

  syncSize();
  console.info(
    `[widget] ready - backend ${IS_TAURI ? "connected" : "absent (browser preview)"}`
  );
})();
