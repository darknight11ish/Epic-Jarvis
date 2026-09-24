/**
 * Settings.
 *
 * Two things are writable here and nothing else: where the backend is, and
 * whether Jarvis Desktop may start one. Everything the desktop will show in
 * build order step 5 — models, memory, the enforced config, skills — is
 * read-only by design, and `POST /api/config` answers 501 on purpose, so this
 * page is deliberately not the beginning of a control panel.
 *
 * The token field is write-only. `get_api_settings` reports whether one is
 * set, and where it came from, and never returns it, so a blank field means
 * "keep what you have".
 *
 * One deliberate exception, on a click: "Show the token for my phone" asks
 * `reveal_pairing_token` for it, because the phone has to be given the same
 * token and before this the only way was to go and find a file. It is shown
 * in a read-only box, hidden again after a minute, and never logged or
 * stored by this page.
 *
 * Not into any page: the HUD window is the exception. `hud_bootstrap.js`
 * injects the live token so the vendored page can reach the backend, where a
 * script in that page can read it. This comment used to say "no path by which
 * the secret comes back into a webview", full stop, which was false and made
 * the storage look stronger than it is.
 */

import {
  announce,
  applyTheme,
  currentZoom,
  followTheme,
  followZoom,
  linkWords,
  onLink,
  reconnect,
  setZoom,
  start as startLink,
  THEME_INFO,
  THEMES,
} from "./jarvis-link.js";
import {
  FRAME_RATES,
  loadFaceTuning,
  QUALITIES,
  saveFaceTuning,
  SPEEDS,
} from "./face-tuning.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

const $ = (id) => document.getElementById(id);

const dom = {
  base: $("base"),
  token: $("token"),
  tokenState: $("token-state"),
  bindAddress: $("bind-address"),
  saveConnection: $("save-connection"),
  clearToken: $("clear-token"),
  revealToken: $("reveal-token"),
  pairingShown: $("pairing-shown"),
  pairingToken: $("pairing-token"),
  copyToken: $("copy-token"),
  hideToken: $("hide-token"),
  connectionStatus: $("connection-status"),
  linkState: $("link-state"),
  linkText: $("link-text"),
  linkTech: $("link-tech"),
  linkDetail: $("link-detail"),
  reconnect: $("reconnect"),

  supervise: $("supervise"),
  program: $("program"),
  args: $("args"),
  cwd: $("cwd"),
  saveBackend: $("save-backend"),
  startBackend: $("start-backend"),
  stopBackend: $("stop-backend"),
  backendStatus: $("backend-status"),
  backendState: $("backend-state"),
  backendTech: $("backend-tech"),
  backendDetail: $("backend-detail"),

  autostart: $("autostart"),
  autostartNote: $("autostart-note"),
  openLogs: $("open-logs"),
  logsStatus: $("logs-status"),
  logsState: $("logs-state"),

  updateAuto: $("update-auto"),
  updateState: $("update-state"),
  updateCheck: $("update-check"),
  updateInstall: $("update-install"),
  updateRestart: $("update-restart"),
  updateStatus: $("update-status"),
  updateProgress: $("update-progress"),
  updateProgressFill: $("update-progress-fill"),
  updateIntroOff: $("update-intro-off"),
  updateIntroOn: $("update-intro-on"),
  faqUpdateOff: $("faq-update-off"),
  faqUpdateOn: $("faq-update-on"),
  updateNotes: $("update-notes"),
  updateNotesBody: $("update-notes-body"),

  hotkeyRows: $("hotkey-rows"),
  saveHotkeys: $("save-hotkeys"),
  resetHotkeys: $("reset-hotkeys"),
  hotkeyStatus: $("hotkey-status"),

  aboutVersion: $("about-version"),

  storePath: $("store-path"),
};

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

/** Shows a one-line result next to the button that caused it. */
function report(target, text, tone) {
  target.textContent = text;
  if (tone) target.dataset.tone = tone;
  else delete target.dataset.tone;
}

/** Runs an action, reporting whatever it says or throws in the same place. */
let busy = false;

async function act(button, target, work) {
  if (busy) return;
  const others = [dom.saveBackend, dom.startBackend, dom.stopBackend];
  const lock = others.includes(button) ? others : [button];
  busy = true;
  lock.forEach((b) => (b.disabled = true));
  report(target, "working…");
  try {
    const outcome = await work();
    report(target, outcome || "Saved.", "ok");
  } catch (error) {
    report(target, String((error && error.message) || error), "bad");
  } finally {
    busy = false;
    lock.forEach((b) => (b.disabled = false));
    await paintBackend();
  }
}

/* ==========================================================================
   Connection
   ========================================================================== */

/** Where the token in use came from, in words. Never the token. */
const TOKEN_SOURCE = {
  "credential-manager": "set here, kept in Windows Credential Manager",
  "settings-file": "set here by an older version, still in the settings file as plain text",
  environment: "from the JARVIS_TOKEN / HUD_TOKEN environment variable",
  "backend-credential-manager": "Jarvis's own, kept in Windows Credential Manager",
  "backend-file": "Jarvis's own, still in its old plain-text file - update the backend (apply-patches.ps1) to move it",
};

async function loadConnection() {
  const settings = await invoke("get_api_settings");
  dom.base.value = settings.base || "";
  dom.tokenState.textContent = TOKEN_SOURCE[settings.tokenSource] ||
    (settings.hasToken ? "set" : "not set");
  // Only a token typed here can be cleared here. Clearing Jarvis's own, or
  // one from the environment, is not something this button can do.
  dom.clearToken.disabled =
    !["credential-manager", "settings-file"].includes(settings.tokenSource);
  dom.bindAddress.value = settings.bindAddress || "";
  dom.storePath.textContent = settings.store || "";
  // Saved by an older version that checked less; the backend is not started
  // with it, so say so instead of letting the field look like it works.
  if (settings.bindAddressProblem) {
    report(dom.connectionStatus,
      `The phone address above is not being used: ${settings.bindAddressProblem}`, "bad");
  }
}

dom.saveConnection.addEventListener("click", () =>
  act(dom.saveConnection, dom.connectionStatus, async () => {
    const base = dom.base.value.trim();
    const token = dom.token.value;
    // An untouched token field means "keep the current one" — passing "" would
    // clear it, which is not what leaving a field alone should ever mean.
    const note = await invoke("set_api_settings", {
      base,
      token: token.length ? token : null,
      bindAddress: dom.bindAddress.value.trim(),
    });
    dom.token.value = "";
    await loadConnection();
    // The stream is pointed at the old base until it reconnects.
    reconnect();
    return note ? `Saved. ${note} Reconnecting the event stream.`
      : "Saved. Reconnecting the event stream.";
  })
);

dom.clearToken.addEventListener("click", () =>
  act(dom.clearToken, dom.connectionStatus, async () => {
    await invoke("set_api_settings", { base: null, token: "" });
    const after = await invoke("get_api_settings");
    await loadConnection();
    reconnect();
    // Cleared means "forget the one typed here", not "use no token": the
    // app goes back to Jarvis's own, and says so.
    return after.hasToken
      ? `Token cleared. Now using ${TOKEN_SOURCE[after.tokenSource] || "the token Jarvis made"}.`
      : "Token cleared. No other token was found, so Jarvis may refuse this app until it has one.";
  })
);

/* Showing the token for the phone. Hidden again after a minute. */
let hideTimer = null;

function hidePairingToken() {
  clearTimeout(hideTimer);
  dom.pairingToken.value = "";
  dom.pairingShown.hidden = true;
  dom.revealToken.hidden = false;
}

dom.revealToken.addEventListener("click", () =>
  act(dom.revealToken, dom.connectionStatus, async () => {
    const token = await invoke("reveal_pairing_token");
    dom.pairingToken.value = token;
    dom.pairingShown.hidden = false;
    dom.revealToken.hidden = true;
    dom.pairingToken.focus();
    dom.pairingToken.select();
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hidePairingToken, 60_000);
    return "Shown below. Type it into the phone.";
  })
);

dom.hideToken.addEventListener("click", hidePairingToken);

dom.copyToken.addEventListener("click", async () => {
  dom.pairingToken.select();
  let copied = false;
  try {
    await navigator.clipboard.writeText(dom.pairingToken.value);
    copied = true;
  } catch {
    try { copied = document.execCommand("copy"); } catch { copied = false; }
  }
  report(dom.connectionStatus, copied ? "Copied." : "Select it and press Ctrl+C.", copied ? "ok" : null);
});

dom.reconnect.addEventListener("click", () => {
  reconnect();
  report(dom.connectionStatus, "Reconnecting…");
});

/* ==========================================================================
   Backend
   ========================================================================== */

/**
 * Repaints the backend section.
 *
 * `fields` is false for the polled refresh. The poll used to rewrite the inputs
 * unconditionally, so anything half-typed was reverted within five seconds, and
 * it re-enabled Start while a start was still in flight — long enough to issue
 * a second one.
 */
async function paintBackend({ fields = false } = {}) {
  let status;
  try {
    status = await invoke("supervisor_status");
  } catch (error) {
    dom.backendState.textContent = String((error && error.message) || error);
    return;
  }

  // Never overwrite a field the user is editing.
  const editing = [dom.program, dom.args, dom.cwd].includes(document.activeElement);
  if (fields && !editing) {
    dom.supervise.checked = Boolean(status.supervise);
    dom.program.value = status.backend.program || "";
    dom.args.value = (status.backend.args || []).join("\n");
    dom.cwd.value = status.backend.cwd || "";
  }

  // While `act()` holds the button lock, it owns the disabled state.
  if (!busy) {
    dom.startBackend.disabled = status.owned || !status.supervise;
    dom.stopBackend.disabled = !status.owned;
  }

  // Plain words first; the process id and the address sit behind
  // "Technical detail", the way the phone's checks do it.
  const detail = [];
  if (status.owned) {
    const up = Number(status.uptime_seconds || 0);
    dom.backendState.textContent =
      `Jarvis Desktop started Jarvis, and it has been running for ${formatUptime(up)}.`;
    detail.push(`pid ${status.pid}`);
    if (status.launcher_exited) detail.push("launcher exited, process tree still supervised");
  } else if (!status.supervise) {
    dom.backendState.textContent =
      "Jarvis Desktop is not managing Jarvis. It will not start or stop it.";
  } else if (!status.configured) {
    dom.backendState.textContent =
      "Turned on, but no program is set, so there is nothing to start yet.";
  } else {
    dom.backendState.textContent =
      "Turned on. Jarvis is not running from here right now — it was not started by Jarvis Desktop.";
  }
  if (status.base) detail.push(status.base);
  dom.backendTech.hidden = !detail.length;
  dom.backendDetail.textContent = detail.join(" · ");
}

function formatUptime(seconds) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

dom.saveBackend.addEventListener("click", () =>
  act(dom.saveBackend, dom.backendStatus, async () => {
    await invoke("set_supervision", {
      supervise: dom.supervise.checked,
      backend: {
        program: dom.program.value.trim(),
        args: dom.args.value
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
        cwd: dom.cwd.value.trim() || null,
      },
    });
    // Saving never starts or stops anything: a preference change is not the
    // moment to take down a running process.
    return "Saved.";
  })
);

dom.startBackend.addEventListener("click", () =>
  act(dom.startBackend, dom.backendStatus, () => invoke("start_backend"))
);

dom.stopBackend.addEventListener("click", () =>
  act(dom.stopBackend, dom.backendStatus, () => invoke("stop_backend"))
);

/* ==========================================================================
   Boot
   ========================================================================== */

/* ==========================================================================
   Appearance
   --------------------------------------------------------------------------
   The picker writes through `set_theme`, which persists to the store and fans
   a `theme-changed` event out to every open window. This page is one of the
   listeners, so the select stays correct when the change came from the Brain.
   ========================================================================== */

/*
 * Three rows, the phone's ThemeRow: a swatch, the phone's name for it and its
 * one-line description. Radios rather than the old <select>, so a screen
 * reader says which is chosen with no extra wiring, and the descriptions are
 * on screen rather than squeezed into an option label.
 *
 * "Match Windows light or dark mode" is the phone's "Follow the system": with
 * it on, Windows picks between Daylight and the dark theme chosen here, and
 * the list becomes "Theme for dark mode" (dark themes only). Rust reads
 * Windows' setting and holds a switch while an approval is waiting - see
 * system_theme.rs for why the pages cannot ask for it themselves.
 */
const themeList = $("theme-list");
const themeLegend = $("theme-legend");
const followSystem = $("follow-system");
const followDetail = $("follow-system-detail");
const FOLLOW_DETAIL = followDetail ? followDetail.textContent.trim() : "";
let themePrefs = null;

function buildThemeRows() {
  for (const id of THEMES) {
    const info = THEME_INFO[id];
    const row = document.createElement("label");
    row.className = "theme-row";
    // `data-choice`, not `data-theme`: theme.css keys every palette on
    // `[data-theme="..."]`, so a row carrying that attribute would repaint
    // itself in the theme it names.
    row.dataset.choice = id;
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "theme";
    radio.value = id;
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.dataset.swatch = id;
    swatch.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.className = "theme-text";
    const name = document.createElement("span");
    name.className = "theme-name";
    name.textContent = info.label;
    const blurb = document.createElement("span");
    blurb.className = "theme-blurb";
    blurb.textContent = info.blurb;
    text.append(name, blurb);
    const check = document.createElement("span");
    check.className = "theme-check";
    check.setAttribute("aria-hidden", "true");
    check.textContent = "✓";
    row.append(radio, swatch, text, check);
    radio.addEventListener("change", () => pickTheme(id));
    themeList.append(row);
  }
}

/** Ticks the row for the theme the owner chose (not what Windows forced). */
function paintThemeRows(current) {
  const following = Boolean(themePrefs && themePrefs.follow_system);
  const chosen = themePrefs
    ? following ? themePrefs.dark_theme : themePrefs.theme
    : current;
  themeLegend.textContent = following ? "Theme for dark mode" : "Theme";
  for (const row of themeList.querySelectorAll(".theme-row")) {
    const id = row.dataset.choice;
    // Daylight is never "the theme for dark mode".
    row.hidden = following && !THEME_INFO[id].dark;
    row.querySelector("input").checked = id === chosen;
  }
  if (followSystem) followSystem.checked = following;
  if (followDetail) {
    followDetail.textContent =
      following && themePrefs && themePrefs.system_light === null
        ? "Windows' light or dark setting could not be read, so the theme below is used."
        : FOLLOW_DETAIL;
  }
}

async function readThemePrefs() {
  try {
    const prefs = await invoke("get_theme_prefs");
    if (prefs && typeof prefs === "object") themePrefs = prefs;
  } catch (error) {
    /* an older shell: the rows still work from the theme alone */
  }
  paintThemeRows(document.documentElement.getAttribute("data-theme"));
}

async function pickTheme(id) {
  // Paint at once when it will show, so the control feels connected; the
  // fan-out from set_theme corrects it either way.
  if (!themePrefs || !themePrefs.follow_system) applyTheme(id);
  try {
    const shown = await invoke("set_theme", { theme: id });
    if (typeof shown === "string") applyTheme(shown);
  } catch (error) {
    console.error("[settings] could not save the theme:", error);
  }
  await readThemePrefs();
}

if (themeList) buildThemeRows();

if (followSystem) {
  followSystem.addEventListener("change", async () => {
    try {
      const prefs = await invoke("set_theme_follow_system", { follow: followSystem.checked });
      if (prefs && typeof prefs === "object") {
        themePrefs = prefs;
        applyTheme(prefs.effective);
      }
    } catch (error) {
      followSystem.checked = !followSystem.checked;
      console.error("[settings] could not save Match Windows:", error);
    }
    paintThemeRows(document.documentElement.getAttribute("data-theme"));
  });
}

followTheme((theme) => {
  paintThemeRows(theme);
  readThemePrefs();
});
readThemePrefs();

/* Text size: the phone's control, for the zoom Ctrl+= / Ctrl+- already walk.
   Five sizes as buttons; the keyboard reaches the rest. */
const TEXT_SIZES = [0.9, 1, 1.15, 1.3, 1.5];
const textSize = $("text-size");
const textSizeNote = $("text-size-note");
const TEXT_SIZE_NOTE = textSizeNote ? textSizeNote.textContent.trim() : "";

function paintTextSize() {
  if (!textSize) return;
  const now = currentZoom();
  for (const b of textSize.querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(Number(b.dataset.zoom) === now));
  }
  textSizeNote.textContent = TEXT_SIZES.includes(now)
    ? TEXT_SIZE_NOTE
    : `Now ${Math.round(now * 100)}%. ${TEXT_SIZE_NOTE}`;
}

if (textSize) {
  for (const z of TEXT_SIZES) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "choice";
    b.dataset.zoom = String(z);
    b.textContent = `${Math.round(z * 100)}%`;
    b.addEventListener("click", () => {
      setZoom(z);
      paintTextSize();
      announce(`Text size ${Math.round(z * 100)} percent.`);
    });
    textSize.append(b);
  }
}

// This window is user-resizable, so nothing needs to re-measure after a step
// - only the buttons need to show the new size.
followZoom(() => paintTextSize());
paintTextSize();

/* The face on THIS computer (face-tuning.js). Per computer, never sent to the
   phone. The face frames in the widget and the HUD read the same key. */
let faceTuning = loadFaceTuning();
const faceAuto = $("face-auto");
const faceStatus = $("face-status");

function choiceRow(box, options, label, onPick) {
  if (!box) return;
  for (const option of options) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "choice";
    b.dataset.value = String(option.id ?? option);
    b.textContent = label(option);
    b.addEventListener("click", () => onPick(option));
    box.append(b);
  }
}

function paintFaceTuning() {
  if (faceAuto) faceAuto.checked = faceTuning.autoAdjust;
  const mark = (id, value) => {
    const box = $(id);
    if (!box) return;
    for (const b of box.querySelectorAll("button")) {
      b.setAttribute("aria-pressed", String(b.dataset.value === String(value)));
    }
  };
  // While Auto is on, it is picking these; neither row claims a choice.
  mark("face-quality", faceTuning.autoAdjust ? "" : faceTuning.quality);
  mark("face-fps", faceTuning.autoAdjust ? "auto" : faceTuning.frameRate);
  mark("face-speed", faceTuning.speed);
  const note = $("face-quality-note");
  if (note) {
    note.textContent = faceTuning.autoAdjust
      ? "Auto adjust is choosing. Picking one turns Auto adjust off."
      : "High matches the reactor kit. Low is easiest on the graphics card.";
  }
}

function setFaceTuning(next, said) {
  faceTuning = saveFaceTuning(next);
  paintFaceTuning();
  if (faceStatus) report(faceStatus, said || "Saved on this computer.", "ok");
}

choiceRow($("face-quality"), QUALITIES, (q) => q.label, (q) =>
  // An explicit choice is not overridden: Auto goes off, as on the phone.
  setFaceTuning({ ...faceTuning, quality: q.id, autoAdjust: false }));
choiceRow($("face-fps"), FRAME_RATES, (f) => f.label, (f) =>
  setFaceTuning({ ...faceTuning, frameRate: f.id, autoAdjust: false }));
choiceRow($("face-speed"), SPEEDS, (s) => `${s}×`, (s) =>
  setFaceTuning({ ...faceTuning, speed: s }));
if (faceAuto) {
  faceAuto.addEventListener("change", () =>
    setFaceTuning({ ...faceTuning, autoAdjust: faceAuto.checked }));
}
paintFaceTuning();

/* Shared with your phone: whether the face and state colours actually reach
   the phone, from get_appearance's own answer. Read on open and when the
   window comes back into view - never from an `appearance-changed` listener,
   because get_appearance broadcasts that event itself. */
const appearanceShared = $("appearance-shared");

async function paintShared() {
  if (!appearanceShared || !IS_TAURI) return;
  try {
    const loaded = await invoke("get_appearance");
    appearanceShared.dataset.tone = loaded && loaded.shared ? "ok" : "";
    appearanceShared.textContent = loaded && loaded.shared
      ? "Shared with your phone."
      : `Not shared yet: ${String((loaded && loaded.note) || "Jarvis could not be asked.")} For now they stay on this computer.`;
  } catch (error) {
    appearanceShared.textContent =
      `Could not check whether they are shared: ${String((error && error.message) || error)}`;
  }
}
paintShared();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) paintShared();
});

$("open-faces").addEventListener("click", async () => {
  try {
    await invoke("open_faces");
    report($("faces-status"), "Opened.", "ok");
  } catch (error) {
    report($("faces-status"), String((error && error.message) || error), "bad");
  }
});

startLink();

onLink((link) => {
  // The same words every other window uses (jarvis-link.js linkWords), plus
  // what the quickbar cannot fit: where it is connected, and - behind
  // "Technical detail" - the whole reason when it is not.
  const words = linkWords(link);
  dom.linkState.dataset.connected = String(link.connected);
  dom.linkState.dataset.tone = words.tone;
  if (words.canAct) {
    const bits = ["Connected, and updates are arriving."];
    if (link.approvals === 1) bits.push("1 approval waiting.");
    else if (link.approvals > 1) bits.push(`${link.approvals} approvals waiting.`);
    dom.linkText.textContent = bits.join(" ");
  } else {
    dom.linkText.textContent = words.text;
  }
  const detail = [link.base ? `Address: ${link.base}` : "", link.error || ""]
    .filter(Boolean)
    .join(" · ");
  dom.linkTech.hidden = !detail;
  dom.linkDetail.textContent = detail;
});

/* ==========================================================================
   Startup and logs
   --------------------------------------------------------------------------
   Two small things that were the difference between "it broke and I have no
   idea why" and a file you can read. The log did not exist at all: a released
   Windows build has no console, so every print in the Rust and every traceback
   from the Python child went to a dead handle.
   ========================================================================== */

/** Human bytes. A log size nobody can read is not information. */
function size(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "empty";
  if (n < 1024) return `${n} bytes`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

async function paintLogs() {
  let info;
  try {
    info = await invoke("get_log_info");
  } catch (error) {
    dom.logsState.textContent = String((error && error.message) || error);
    dom.openLogs.disabled = true;
    return;
  }
  if (!info || info.available === false) {
    dom.logsState.textContent = String(info?.note || "No log directory.");
    dom.openLogs.disabled = true;
    return;
  }
  dom.openLogs.disabled = false;
  // The folder path is rendered as text as well as being openable, because
  // Explorer can be refused on a locked-down machine and a path you can
  // select and copy is the difference between sending a log and giving up.
  dom.logsState.textContent =
    `${info.dir} · this app ${size(info.app?.bytes)} · backend ${size(info.backend?.bytes)}`;
}

async function paintAutostart() {
  let info;
  try {
    info = await invoke("get_autostart");
  } catch (error) {
    dom.autostartNote.textContent = String((error && error.message) || error);
    dom.autostart.disabled = true;
    return;
  }
  // Read back from the registry every time, never remembered here: the owner
  // can turn this off in Task Manager's Startup tab, and a checkbox still
  // showing ticked after that would be a lie about the machine.
  dom.autostart.checked = Boolean(info.enabled);
  dom.autostart.disabled = !info.supported;
  if (!info.supported) {
    dom.autostartNote.textContent =
      "Starting with the computer is a Windows feature. This build is not Windows.";
  }
}

dom.autostart.addEventListener("change", async () => {
  const wanted = dom.autostart.checked;
  dom.autostart.disabled = true;
  try {
    const out = await invoke("set_autostart", { enabled: wanted });
    // Render what came back, not what was asked for. A registry write that
    // silently did nothing must show as off.
    dom.autostart.checked = Boolean(out && out.enabled);
    report(
      dom.logsStatus,
      out && out.enabled ? "Jarvis will start with Windows." : "Jarvis will not start with Windows.",
      "ok"
    );
  } catch (error) {
    report(dom.logsStatus, String((error && error.message) || error), "bad");
    await paintAutostart();
  } finally {
    dom.autostart.disabled = false;
  }
});

dom.openLogs.addEventListener("click", async () => {
  try {
    await invoke("open_log_folder");
    report(dom.logsStatus, "Opened.", "ok");
  } catch (error) {
    report(dom.logsStatus, String((error && error.message) || error), "bad");
  }
});

(async () => {
  if (!IS_TAURI) {
    report(dom.connectionStatus, "No desktop backend — browser preview.", "bad");
    return;
  }
  try {
    await loadConnection();
  } catch (error) {
    report(dom.connectionStatus, String((error && error.message) || error), "bad");
  }
  await paintBackend({ fields: true });
  await paintAutostart();
  await paintLogs();
  // Cheap, and only while the window is actually on screen — a settings page
  // nobody is looking at has no reason to poll.
  let timer = null;
  const poll = () => {
    if (timer) clearInterval(timer);
    timer = document.hidden
      ? null
      : setInterval(() => {
          paintBackend();
          // The backend log grows while the backend runs, so the size on
          // screen should move. Autostart is not polled: it changes only when
          // someone changes it, here or in Task Manager, and re-reading the
          // registry every five seconds to catch the second case is not worth
          // it - the page re-reads it on open.
          paintLogs();
        }, 5000);
  };
  document.addEventListener("visibilitychange", poll);
  poll();
})();


/* ==========================================================================
   Shortcuts
   --------------------------------------------------------------------------
   The five global accelerators were constants in `lib.rs` until the first
   machine this ran on refused `Alt+Space`, at which point the spotlight had no
   shortcut and nothing could be done about it short of editing Rust.

   Recorded rather than typed. "Alt+Space" spelled by hand invites a string
   nothing accepts, and the combination someone wants is the one their fingers
   already know — so the field listens instead of reading.
   ========================================================================== */

/** The bindings as last read from Rust, keyed by action id. */
let hotkeys = [];
/** The row currently listening, if any. */
let recording = null;

/** Windows names the Super key differently from the accelerator syntax. */
const MOD_LABEL = { Super: "Win", Control: "Ctrl" };

/**
 * A `keydown` as an accelerator string Rust can parse, or `null` while the
 * user is still only holding modifiers.
 *
 * Tauri's parser wants `Super`, `Control`, `Alt`, `Shift` and a `KeyX` /
 * `Digit1` / `F5` code, so this speaks in `event.code` rather than `event.key`:
 * `key` is layout-dependent and reports "S" for whatever key sits there, which
 * is not what the OS binds.
 */
function accelerator(event) {
  const mods = [];
  if (event.ctrlKey) mods.push("Control");
  if (event.altKey) mods.push("Alt");
  if (event.shiftKey) mods.push("Shift");
  if (event.metaKey) mods.push("Super");

  const code = event.code;
  // A modifier on its own is not a binding yet — the user is mid-chord.
  if (/^(Control|Alt|Shift|Meta|OS)(Left|Right)?$/.test(code)) return null;

  let key = null;
  if (/^Key[A-Z]$/.test(code)) key = code.slice(3);
  else if (/^Digit[0-9]$/.test(code)) key = code.slice(5);
  else if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) key = code;
  else if (code === "Space") key = "Space";
  else if (code === "Enter") key = "Enter";
  else if (code === "Backquote") key = "Backquote";
  else if (code === "Minus") key = "Minus";
  else if (code === "Equal") key = "Equal";
  else if (code === "BracketLeft") key = "BracketLeft";
  else if (code === "BracketRight") key = "BracketRight";
  else if (code === "Semicolon") key = "Semicolon";
  else if (code === "Quote") key = "Quote";
  else if (code === "Comma") key = "Comma";
  else if (code === "Period") key = "Period";
  else if (code === "Slash") key = "Slash";
  else if (code === "Backslash") key = "Backslash";
  else if (/^Arrow(Up|Down|Left|Right)$/.test(code)) key = code;
  else return null;

  // Refused here as well as in Rust. Rust is the authority — a page cannot be
  // trusted with a rule this consequential — but stopping it at the keystroke
  // means the user sees why immediately instead of after a save.
  if (!mods.length) return { error: "That needs a modifier — hold Ctrl, Alt, Shift or Win." };

  return { accelerator: [...mods, key].join("+") };
}

/** The accelerator as a person reads it. */
function prettyKey(accel) {
  return String(accel)
    .split("+")
    .map((part) => MOD_LABEL[part] || part.replace(/^Key|^Digit/, ""))
    .join(" + ");
}

function renderHotkeys() {
  dom.hotkeyRows.textContent = "";
  for (const row of hotkeys) {
    const wrap = document.createElement("div");
    wrap.className = "hotkey";
    wrap.dataset.bound = String(Boolean(row.registered));

    const name = document.createElement("div");
    name.className = "hotkey-name";
    name.textContent = row.label;

    const hint = document.createElement("div");
    hint.className = "hotkey-hint";
    hint.textContent = row.hint;

    const key = document.createElement("button");
    key.type = "button";
    key.className = "hotkey-key";
    key.textContent = prettyKey(row.accelerator);
    // The accessible name has to carry the action, or every one of these is
    // announced as the bare combination with no clue what it does.
    key.setAttribute("aria-label", `${row.label}: ${prettyKey(row.accelerator)}. Press to change.`);
    key.addEventListener("click", () => startRecording(row.id, key));

    const state = document.createElement("div");
    state.className = "hotkey-state";
    state.textContent = row.registered
      ? "working"
      : row.error
        ? "in use by another app"
        : "not bound";
    if (!row.registered && row.error) state.title = row.error;

    wrap.append(name, key, hint, state);
    dom.hotkeyRows.append(wrap);
  }
}

function startRecording(id, button) {
  stopRecording();
  recording = { id, button, previous: button.textContent };
  button.dataset.recording = "true";
  button.textContent = "press keys…";
  button.focus();
  announce(`Recording a shortcut for ${hotkeys.find((h) => h.id === id)?.label}. Press Escape to cancel.`);
}

function stopRecording() {
  if (!recording) return;
  recording.button.dataset.recording = "false";
  recording.button.textContent = recording.previous;
  recording = null;
}

// Capture phase, on the window: a recording field has to see the keystroke
// before anything else does, including this page's own Ctrl+= zoom handler.
window.addEventListener(
  "keydown",
  (event) => {
    if (!recording) return;
    event.preventDefault();
    event.stopPropagation();

    if (event.code === "Escape") {
      stopRecording();
      announce("Cancelled.");
      return;
    }

    const read = accelerator(event);
    if (!read) return; // still holding modifiers
    if (read.error) {
      report(dom.hotkeyStatus, read.error, "bad");
      return;
    }

    const row = hotkeys.find((h) => h.id === recording.id);
    if (row) row.accelerator = read.accelerator;
    stopRecording();
    renderHotkeys();
    report(dom.hotkeyStatus, "Not saved yet — press Save shortcuts.", "");
  },
  true
);

async function loadHotkeys() {
  try {
    hotkeys = (await invoke("get_hotkeys")) || [];
    renderHotkeys();
  } catch (error) {
    report(dom.hotkeyStatus, String(error.message || error), "bad");
  }
}

dom.saveHotkeys.addEventListener("click", async () => {
  stopRecording();
  const bindings = Object.fromEntries(hotkeys.map((h) => [h.id, h.accelerator]));
  try {
    hotkeys = await invoke("set_hotkeys", { bindings });
    renderHotkeys();
    const refused = hotkeys.filter((h) => !h.registered);
    if (refused.length) {
      // Saved is not the same as working, and saying "Saved" alone is how the
      // old build left someone believing a shortcut was live when it was not.
      report(
        dom.hotkeyStatus,
        `Saved. ${refused.length} still held by another application.`,
        "bad"
      );
    } else {
      report(dom.hotkeyStatus, "Saved, and all of them bound.", "ok");
    }
    announce(dom.hotkeyStatus.textContent);
  } catch (error) {
    // Rust validated the whole set before writing or unbinding anything, so
    // nothing changed and the old shortcuts are still live.
    report(dom.hotkeyStatus, `${error.message || error} Nothing was changed.`, "bad");
    announce(dom.hotkeyStatus.textContent, "assertive");
  }
});

dom.resetHotkeys.addEventListener("click", async () => {
  stopRecording();
  try {
    hotkeys = await invoke("reset_hotkeys");
    renderHotkeys();
    report(dom.hotkeyStatus, "Back to the shipped combinations.", "ok");
  } catch (error) {
    report(dom.hotkeyStatus, String(error.message || error), "bad");
  }
});

loadHotkeys();


/* ==========================================================================
   Updates
   --------------------------------------------------------------------------
   Check, report, and install only on a press. There is deliberately no path
   through this file that installs without one — `check_for_update` and
   `install_update` are separate commands in Rust for the same reason, so that
   no later edit can turn a check into an install by passing a flag.
   ========================================================================== */

function paintUpdate(status) {
  if (!status) return;
  // About's version, from the same read as everything else here - never a
  // second, separately-maintained copy of the number that could drift from
  // the one actually running.
  dom.aboutVersion.textContent = status.current || "—";
  dom.updateAuto.checked = Boolean(status.check_on_start);
  dom.updateAuto.disabled = !status.supported;
  // "Not set up yet" until this build carries the update key, and not a
  // moment longer: the same `supported` that greys the buttons.
  const setUp = Boolean(status.supported);
  if (dom.updateIntroOff) dom.updateIntroOff.hidden = setUp;
  if (dom.updateIntroOn) dom.updateIntroOn.hidden = !setUp;
  if (dom.faqUpdateOff) dom.faqUpdateOff.hidden = setUp;
  if (dom.faqUpdateOn) dom.faqUpdateOn.hidden = !setUp;

  const notes = String(status.notes || "").trim();
  dom.updateNotes.hidden = !notes;
  dom.updateNotesBody.textContent = notes;

  if (!status.supported) {
    // A Check button that can only ever fail invites someone to keep pressing
    // it, so say what is actually true about this build instead.
    dom.updateState.textContent =
      `Version ${status.current}. This build has no update key, so it cannot ` +
      `verify a download and will not offer one.`;
    dom.updateCheck.disabled = true;
    dom.updateInstall.hidden = true;
    return;
  }

  dom.updateCheck.disabled = false;
  if (status.available) {
    dom.updateState.textContent =
      `Version ${status.available} is available. You are running ${status.current}` +
      (status.date ? ` · published ${status.date}` : "") + ".";
    dom.updateInstall.hidden = false;
    dom.updateInstall.textContent = `Install ${status.available}`;
  } else {
    dom.updateInstall.hidden = true;
    dom.updateState.textContent = status.error
      ? `Version ${status.current}. ${status.error}`
      : `Version ${status.current} — the newest published.`;
  }
}

async function loadUpdate() {
  try {
    paintUpdate(await invoke("update_status"));
  } catch (error) {
    report(dom.updateStatus, String(error.message || error), "bad");
  }
}

dom.updateCheck.addEventListener("click", async () => {
  report(dom.updateStatus, "Checking…", "");
  try {
    const status = await invoke("check_for_update");
    paintUpdate(status);
    const said = status.available
      ? `Version ${status.available} is available.`
      : status.error || "Nothing newer.";
    report(dom.updateStatus, said, status.available ? "ok" : "");
    announce(said);
  } catch (error) {
    report(dom.updateStatus, String(error.message || error), "bad");
  }
});

/** Bytes to a short human string. `formatBytes(0)` reads as "0 B", not "". */
function formatBytes(n) {
  if (!Number.isFinite(n)) return "";
  const units = ["B", "KB", "MB", "GB"];
  let value = n;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${i === 0 ? value : value.toFixed(1)} ${units[i]}`;
}

function paintProgress({ downloaded, total }) {
  dom.updateProgress.hidden = false;
  if (total) {
    dom.updateProgress.dataset.indeterminate = "false";
    dom.updateProgressFill.style.width = `${Math.min(100, (downloaded / total) * 100)}%`;
    report(dom.updateStatus,
      `Downloading… ${formatBytes(downloaded)} of ${formatBytes(total)}`, "");
  } else {
    // No Content-Length reported — say so honestly rather than a percentage
    // that would be invented.
    dom.updateProgress.dataset.indeterminate = "true";
    report(dom.updateStatus, `Downloading… ${formatBytes(downloaded)} so far`, "");
  }
}

dom.updateInstall.addEventListener("click", async () => {
  // No confirmation dialog, because the button is the confirmation: it only
  // appears once a check has found something, and it names the version.
  report(dom.updateStatus, "Downloading and verifying…", "");
  dom.updateInstall.disabled = true;
  dom.updateCheck.disabled = true;
  dom.updateProgress.hidden = false;
  dom.updateProgress.dataset.indeterminate = "true";
  dom.updateProgressFill.style.width = "";
  try {
    const version = await invoke("install_update");
    dom.updateProgress.hidden = true;
    report(dom.updateStatus, `${version} installed.`, "ok");
    announce(dom.updateStatus.textContent, "assertive");
    dom.updateInstall.hidden = true;
    dom.updateRestart.hidden = false;
  } catch (error) {
    // A signature that does not verify lands here, and it is the one failure
    // that must not read as a routine network problem.
    dom.updateProgress.hidden = true;
    report(dom.updateStatus, String(error.message || error), "bad");
    announce(dom.updateStatus.textContent, "assertive");
    dom.updateInstall.disabled = false;
  } finally {
    dom.updateCheck.disabled = false;
  }
});

dom.updateRestart.addEventListener("click", () => {
  // No confirmation here either, same reasoning as Install: the button only
  // appears once an install has already finished, and it says what it does.
  dom.updateRestart.disabled = true;
  report(dom.updateStatus, "Restarting…", "");
  invoke("restart_app").catch((error) => {
    // Reachable only if the restart itself could not even be requested — the
    // process is gone by the time this would normally resolve.
    dom.updateRestart.disabled = false;
    report(dom.updateStatus, String(error.message || error), "bad");
  });
});

dom.updateAuto.addEventListener("change", async () => {
  try {
    await invoke("set_update_check_on_start", { enabled: dom.updateAuto.checked });
    report(
      dom.updateStatus,
      dom.updateAuto.checked
        ? "Jarvis will look once at startup."
        : "Jarvis will not look on its own.",
      "ok"
    );
  } catch (error) {
    report(dom.updateStatus, String(error.message || error), "bad");
    dom.updateAuto.checked = !dom.updateAuto.checked;
  }
});

// The startup check finishes after this window may already be open.
if (IS_TAURI) TAURI.event.listen("update-status", (event) => paintUpdate(event.payload));
// Emitted only while `install_update` is downloading — see `paintProgress`.
if (IS_TAURI) TAURI.event.listen("update-progress", (event) => paintProgress(event.payload));

// About's source link opens in the real OS browser, never inside the
// WebView - same reasoning and the same `data-external`/`open_external_url`
// pattern main.js already uses for the quickbar's own linkified text.
document.addEventListener("click", (event) => {
  const anchor = event.target.closest("a[data-external]");
  if (!anchor) return;
  event.preventDefault();
  if (IS_TAURI) {
    invoke("open_external_url", { url: anchor.href }).catch(() => {});
  } else {
    window.open(anchor.href, "_blank", "noopener");
  }
});

loadUpdate();
