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
  currentLink,
  decide as decideOnBackend,
  onLink,
  onQueue,
  riskLine,
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

  netDot: $("net-dot"),
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
  apprAction: $("appr-action"),
  apprDetail: $("appr-detail"),
  btnApprYes: $("btn-appr-yes"),
  btnApprNo: $("btn-appr-no"),

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
  busy: false,
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

function applyExpanded(expanded) {
  state.expanded = expanded;
  dom.root.dataset.state = expanded ? "expanded" : "collapsed";
  dom.tray.hidden = !expanded;
  dom.btnToggle.title = expanded ? "Collapse" : "Expand";
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
    bar.style.width = "0%";
    meter.dataset.level = "ok";
    return;
  }
  const clamped = Math.max(0, Math.min(100, percent));
  bar.style.width = `${clamped}%`;
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
  const fresh = !state.approval || state.approval.id !== approval.id;
  state.approval = approval;
  dom.apprAction.textContent = approval.action;
  // textContent, never innerHTML: this string comes from a model.
  dom.apprDetail.textContent = approvalDetail(approval);
  dom.apprRisk.textContent = riskLine(approval.risk);
  dom.apprRisk.dataset.reversible = approval.risk ? approval.risk.reversible : "no";
  dom.apprCard.hidden = false;
  syncApprovalButtons();
  // A gate is the one thing worth opening the widget for on its own — but only
  // when it is a new one, or re-reading the queue would keep re-expanding a
  // widget the user had just collapsed.
  if (fresh && !state.expanded) toggleExpand();
  else syncSize();
}

function closeApproval() {
  state.approval = null;
  dom.apprCard.hidden = true;
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
}

async function decide(approved) {
  if (!state.approval || state.busy) return;
  state.busy = true;
  syncApprovalButtons();

  try {
    await decideOnBackend(state.approval.id, approved);
    // The backend broadcasts approval-resolved, which closes the card.
    flash(approved ? "Approved." : "Denied.", approved ? "ok" : null);
  } catch (error) {
    const message = String((error && error.message) || error);
    // 409 means the id is unknown, expired, or already decided. Someone
    // answered it — that is not an error to shout about.
    flash(
      /409|already/i.test(message) ? "Already handled elsewhere." : message,
      /409|already/i.test(message) ? null : "bad"
    );
  } finally {
    state.busy = false;
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

/** Shows a transient one-line status under the capture field. */
function flash(message, tone) {
  dom.flash.textContent = message;
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
    await invokeStrict("capture_note", { target: state.captureTarget, text });
    dom.captureInput.value = "";
    flash(state.captureTarget === "joplin" ? "Filed to Joplin." : "Appended to Logseq.", "ok");
  } catch (error) {
    flash(String((error && error.message) || error), "bad");
  } finally {
    state.busy = false;
    dom.captureInput.disabled = false;
    dom.btnCaptureSend.disabled = false;
    dom.captureInput.focus();
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

dom.captureTarget.addEventListener("click", () =>
  setCaptureTarget(state.captureTarget === "logseq" ? "joplin" : "logseq")
);
dom.btnCaptureSend.addEventListener("click", sendCapture);
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

// Persist the position once the drag ends rather than on every mouse move.
window.addEventListener("mouseup", () => invoke("save_widget_position", {}));

listen("desktop-telemetry", (event) => applyTelemetry(event.payload));
listen("health-report", (event) => applyHealth(event.payload));
// `approval-requested` is gone: it was the quickbar telling this window what
// it had found in a chat chunk, which made two surfaces the authority on the
// same queue. The queue below is read once, by Rust, from /api/pending.
listen("approval-resolved", () => closeApproval());

/* ==========================================================================
   Boot
   ========================================================================== */

(async () => {
  setCaptureTarget("logseq");

  // Restore the mode the user left the widget in.
  const prefs = await invoke("get_widget_prefs");
  applyExpanded(Boolean(prefs && prefs.expanded));
  await setPinned(prefs ? Boolean(prefs.alwaysOnTop) : true);

  // One stream, owned by Rust, fanned out to all three surfaces.
  startLink();

  onLink((link) => {
    // A held-open event stream is a stronger liveness signal than a probe that
    // succeeded a moment ago, so the lane pill follows it directly.
    if (!link.connected) applyLane("offline");
    syncApprovalButtons();
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
