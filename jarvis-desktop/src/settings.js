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
  APPROVE_WHERE,
  currentZoom,
  followTheme,
  followZoom,
  linkWords,
  onLink,
  onQueue,
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
    // Focused so a screen reader reads it, and NOT selected: a selected
    // token is one Ctrl+C away from Windows' clipboard history.
    dom.pairingToken.focus();
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hidePairingToken, 60_000);
    return "Shown below. Type it into the phone.";
  })
);

dom.hideToken.addEventListener("click", hidePairingToken);

// No Copy button for the token (CONN-6). Anything copied on Windows is kept
// in Clipboard History, and with cloud clipboard on it is sent to the
// owner's other devices - a secret that outlives this window by days. The
// phone needs it typed in anyway. The second card's Copy (`pin_command`) is
// not a secret and keeps its button.

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

/* ==========================================================================
   Second graphics card
   --------------------------------------------------------------------------
   Everything built for a second graphics card, all OFF (docs/SECOND-CARD.md).
   Read from `get_second_card` (GET /api/second-card, the backend's
   jarvis_second_card.status() - its real shape is
   tests/fixtures/second-card-cases.json), written one switch at a time with
   `set_second_card`.

   Turning a switch ON approves nothing: the backend raises ONE approval card
   and answers `pending: true`, and the switch stays off until the owner says
   yes on that card, in the Jarvis bar, on the widget or on the phone. There
   is no event for the card being decided, so this re-reads when the approval
   queue changes (the "approvals-changed" signal every window gets), when the
   window comes back into view, and gently every few seconds while a card is
   waiting. Turning a switch OFF is immediate.

   Every word about the cards comes from the backend's own sentences (`why`,
   `pin_note`); nothing here guesses what a card can do.
   ========================================================================== */

const sc = {
  card: $("second-card"),
  state: $("sc-state"),
  body: $("sc-body"),
  found: $("sc-found"),
  cards: $("sc-cards"),
  blocked: $("sc-blocked"),
  switches: $("sc-switches"),
  status: $("sc-status"),
  lane: $("sc-lane"),
  pinned: $("sc-pinned"),
  pin: $("sc-pin"),
  pinCommand: $("sc-pin-command"),
  pinCopy: $("sc-pin-copy"),
  pinStatus: $("sc-pin-status"),
};

/** The same words the Brain's model install uses while its card waits. */
const SC_WAITING =
  `Waiting for your approval. Approve it ${APPROVE_WHERE} — nothing changes until you do.`;
const SC_UPDATE =
  "This PC's Jarvis does not have the second graphics card part yet. Update the backend by running apply-patches.ps1, then open this again.";
/** The main switch has no row in `features`; these are its words. */
const SC_MASTER = {
  id: "master",
  name: "Use the second graphics card",
  what: "The main switch. None of the switches below can be turned on until this one is on.",
};
const SC_ROLE = {
  primary: "the one chat runs on",
  second: "the second card",
  unused: "not used",
};
const SC_LANE = { off: "Off", starting: "Starting", running: "Running", failed: "Failed" };
/** How often, and for how long, to re-read while a card waits. */
const SC_POLL_MS = 5000;
const SC_POLL_FOR_MS = 10 * 60 * 1000;

let scLast = null;
let scReadSeq = 0;
let scBusy = false;
let scPollTimer = null;
/** When the gentle re-reading stops; 0 while no card waits. */
let scPollUntil = 0;
/** Switches with a card waiting at the last read, to say how each ended. */
let scWaiting = new Set();
/** When this page first saw each of those cards waiting, in seconds. */
const scWaitingSince = new Map();

/**
 * How a switch's card ended, in words, for the second card and the big
 * model alike.
 *
 * A backend with the `last` field (`status().last`: `{feature, outcome,
 * why, at}`) says what really happened; without it - an older backend -
 * the page can only see that the switch is still off, and says the old
 * "denied or ran out of time". `last` is used only when it is about THIS
 * switch and ended after the page started waiting on it, so an older card's
 * ending is never reported as this one's. Every field is read defensively:
 * a missing, renamed or odd value falls back to the old words, never to a
 * guess.
 */
const CARD_OUTCOMES = {
  enabled: "enabled", approved: "enabled", on: "enabled",
  denied: "denied", rejected: "denied",
  expired: "expired", timed_out: "expired", timeout: "expired",
  refused: "refused",
  failed: "failed", error: "failed",
  withdrawn: "withdrawn", cancelled: "withdrawn", canceled: "withdrawn",
};

/** Seconds since the epoch from a number (seconds or ms) or a date string. */
function cardSeconds(at) {
  if (typeof at === "number" && Number.isFinite(at)) return at > 1e12 ? at / 1000 : at;
  if (typeof at === "string" && at.trim()) {
    const n = Number(at);
    if (Number.isFinite(n)) return n > 1e12 ? n / 1000 : n;
    const parsed = Date.parse(at);
    if (Number.isFinite(parsed)) return parsed / 1000;
  }
  return null;
}

/** `last`, when it is about switch `id` and ended after `since` (seconds). */
function cardLast(status, id, since) {
  const last = status && status.last;
  if (!last || typeof last !== "object") return null;
  const which = String(last.feature ?? last.switch ?? "").trim();
  if (which !== id) return null;
  const outcome = CARD_OUTCOMES[String(last.outcome || "").trim().toLowerCase()];
  if (!outcome) return null;
  const at = cardSeconds(last.at);
  // A few seconds of slack: the page's clock and the backend's are the same
  // PC's, but the page noted `since` when it READ the card as waiting.
  if (at !== null && Number.isFinite(since) && at < since - 5) return null;
  return { outcome, why: String(last.why ?? last.reason ?? "").trim() };
}

/** The sentence for switch `name`, which was waiting and no longer is. */
function cardEndedWords(name, on, last) {
  if (on) return `"${name}" is on.`;
  const why = scSentence(last && last.why);
  const because = why ? ` ${why}` : "";
  switch (last && last.outcome) {
    case "denied":
      return `"${name}" was not turned on: the card was denied.`;
    case "expired":
      return `"${name}" was not turned on: the card ran out of time before anyone answered it.`;
    case "refused":
      return `"${name}" was not turned on: Jarvis refused it.${because || " It did not say why."}`;
    case "failed":
      return `"${name}" was approved, but turning it on failed.${because || " Jarvis did not say why."}`;
    case "withdrawn":
      return `"${name}" was not turned on: the card was withdrawn before it was answered.${because}`;
    case "enabled":
      // Approved, yet off by this read: turned off again since.
      return `"${name}" was approved and turned on, but it is off again now.${because}`;
    default:
      return `"${name}" was not turned on: the card was denied or ran out of time.`;
  }
}

/** A backend sentence as a sentence: first letter up, one full stop. */
function scSentence(text) {
  const s = String(text || "").trim().replace(/[.\s]+$/, "");
  return s ? `${s.charAt(0).toUpperCase()}${s.slice(1)}.` : "";
}

/** A backend sentence after a colon: as it was written, with one full stop. */
function scClause(text) {
  const s = String(text || "").trim().replace(/[.\s]+$/, "");
  return s ? `${s}.` : "";
}

/** An error in words. The Rust side only ever rejects with a sentence; if
 *  anything else arrives (a bridge error, JSON), it is not shown as is. */
function scProblemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 300) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function scNode(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function scGigabytes(mb) {
  const n = Number(mb);
  return Number.isFinite(n) && n > 0 ? `${Math.round(n / 1024)} GB` : "";
}

/** The model a feature uses, and whether it is installed - with the exact
 *  name to type when it is not. There is no catalogue: the Brain's Install
 *  box is the existing way, a typed name and an approval card. */
function scModelLine(feature) {
  const model = typeof feature.model === "string" ? feature.model.trim() : "";
  if (!model) return "The model is chosen once a capable second card is found.";
  if (feature.model_installed === true) return `Model: ${model}, installed.`;
  if (feature.model_installed === false) {
    return `Model: ${model}, not installed yet. To install it, open the Brain window, go to ` +
      `Faculties, then Models, type ${model} in the Install box and press Install. ` +
      "Nothing downloads until you approve that card too.";
  }
  return `Model: ${model}. Jarvis could not check whether it is installed.`;
}

function scMemoryLine(feature) {
  const gib = Number(feature.memory_gib);
  if (feature.memory_gib === null || feature.memory_gib === undefined || !Number.isFinite(gib)) {
    return "";
  }
  return `Uses about ${gib.toFixed(1)} GB of the second card's memory.`;
}

/**
 * Whether a switch may be changed now, and if not, why - in words.
 * Only turning ON is ever held back: OFF only narrows what runs, so a switch
 * that is on can always be turned off, even with the card gone.
 */
function scHeld(sw, status, names) {
  if (sw.pending) return SC_WAITING;
  if (sw.enabled) return "";
  const detected = status.detected || {};
  if (detected.capable !== true) {
    return `Can't be turned on yet: ${scClause(detected.why) || "no capable second graphics card was found."}`;
  }
  if (sw.id !== "master" && status.enabled !== true) {
    return `Turn on "${SC_MASTER.name}" first.`;
  }
  const missing = (sw.needs || []).filter((need) => !names.enabled.has(need));
  if (missing.length) {
    return `Needs ${missing.map((m) => `"${names.byId[m] || m}"`).join(" and ")} on first.`;
  }
  return "";
}

function scSwitchRow(sw, status, names) {
  const row = scNode("div", "sc-switch");
  row.dataset.id = sw.id;
  row.dataset.state = sw.pending ? "waiting" : sw.enabled ? "on" : "off";

  const label = scNode("label", "toggle");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = `sc-switch-${sw.id}`;
  input.checked = Boolean(sw.enabled);
  const held = scHeld(sw, status, names);
  input.disabled = Boolean(held);
  const text = scNode("span", "", sw.name);
  text.append(scNode("span", "toggle-detail", sw.what || ""));
  label.append(input, text);
  row.append(label);

  const lines = scNode("div", "sc-lines");
  const describedBy = [];
  const addLine = (className, words) => {
    if (!words) return;
    const line = scNode("p", className, words);
    line.id = `sc-${sw.id}-${className.split(" ").pop()}`;
    describedBy.push(line.id);
    lines.append(line);
  };
  addLine("sc-why", sw.why);
  const capable = (status.detected || {}).capable === true;
  if (sw.pending) addLine("sc-held sc-waiting", SC_WAITING);
  // With no capable card, the one line above the switches says why for all
  // of them, rather than the same sentence under each.
  // Nor twice when the backend's own line already says it ("Off. Needs
  // Longer conversations on first.").
  else if (held && capable && !String(sw.why || "").includes(held.replace(/"/g, ""))) {
    addLine("sc-held", held);
  }
  if (held && !capable) describedBy.push("sc-blocked");
  if (sw.id !== "master") {
    addLine("sc-model", scModelLine(sw));
    addLine("sc-memory", scMemoryLine(sw));
  }
  if (describedBy.length) input.setAttribute("aria-describedby", describedBy.join(" "));
  row.append(lines);

  input.addEventListener("change", () => scToggle(sw, input));
  return row;
}

function scCardItem(card) {
  const item = scNode("li", "sc-gpu");
  item.dataset.role = String(card.role || "unused");
  const size = scGigabytes(card.total_mb);
  item.append(scNode("span", "sc-gpu-name", `${card.name || "A graphics card"}${size ? ` (${size})` : ""}`));
  const role = SC_ROLE[card.role] || SC_ROLE.unused;
  item.append(scNode("span", "sc-gpu-role", `${role.charAt(0).toUpperCase()}${role.slice(1)}. ${scSentence(card.why)}`.trim()));
  return item;
}

/** The master switch in the same shape as a feature row. */
function scMasterSwitch(status) {
  const detected = status.detected || {};
  const pending = (status.pending || []).includes("master");
  let why = "Off.";
  if (status.enabled && status.active) why = "On.";
  else if (status.enabled) {
    why = `On, but it cannot run: ${scClause(detected.why) || "no capable second card was found."} Your choice is kept.`;
  }
  return { ...SC_MASTER, enabled: status.enabled === true, pending, needs: [], why };
}

function scShowProblem(words) {
  scLast = null;
  sc.body.hidden = true;
  sc.state.hidden = false;
  sc.state.dataset.tone = "bad";
  sc.state.textContent = words;
  scStopPoll();
}

function scPaint(status) {
  const previous = scLast;
  scLast = status;
  const detected = status.detected || {};
  const features = status.features.filter((f) => f && typeof f.id === "string");
  const pending = new Set(Array.isArray(status.pending) ? status.pending : []);

  sc.state.hidden = true;
  delete sc.state.dataset.tone;
  sc.body.hidden = false;

  // What was found, in the backend's own words.
  sc.found.textContent = scSentence(detected.why) || "Jarvis did not say what it found.";
  const cards = Array.isArray(detected.cards) ? detected.cards : [];
  sc.cards.replaceChildren(...cards.map(scCardItem));
  sc.cards.hidden = !cards.length;

  sc.blocked.hidden = detected.capable === true;
  sc.blocked.textContent = detected.capable === true ? ""
    : `Nothing here can be turned on until Jarvis finds a capable second graphics card ` +
      `(an RTX 20 series or newer, with 10 GB or more): ${scClause(detected.why)} ` +
      "The switches are shown so you can see what is coming.";

  const names = {
    byId: Object.fromEntries(features.map((f) => [f.id, String(f.name || f.id)])),
    enabled: new Set(features.filter((f) => f.enabled === true).map((f) => f.id)),
  };
  const rows = [scMasterSwitch(status)].concat(features.map((f) => ({
    ...f, enabled: f.enabled === true, pending: pending.has(f.id),
    needs: Array.isArray(f.needs) ? f.needs : [],
  })));
  // Keep the keyboard where it was across a repaint.
  const focused = document.activeElement && document.activeElement.id;
  sc.switches.replaceChildren(...rows.map((sw) => scSwitchRow(sw, status, names)));
  if (focused && focused.startsWith("sc-switch-")) {
    const again = document.getElementById(focused);
    if (again) again.focus();
  }

  // The second Ollama.
  const lane = status.lane || {};
  const laneWord = SC_LANE[lane.state] || "Unknown";
  sc.lane.textContent = `${laneWord}. ${scSentence(lane.why)}`.trim();
  sc.lane.dataset.tone = lane.state === "running" ? "ok" : lane.state === "failed" ? "bad" : "";

  // Everyday Ollama pinned to the main card.
  sc.pinned.textContent = scSentence(status.pin_note) ||
    "Jarvis could not tell whether your everyday Ollama is kept on the main card.";
  sc.pinned.dataset.tone = status.main_ollama_pinned === true ? "ok"
    : status.main_ollama_pinned === false ? "warn" : "";
  const command = typeof status.pin_command === "string" ? status.pin_command.trim() : "";
  sc.pin.hidden = !command;
  sc.pinCommand.value = command;

  // How each card that was waiting ended.
  if (previous) {
    for (const id of scWaiting) {
      if (pending.has(id)) continue;
      const name = id === "master" ? SC_MASTER.name : names.byId[id] || id;
      const on = id === "master" ? status.enabled === true : names.enabled.has(id);
      report(sc.status, cardEndedWords(name, on, cardLast(status, id, scWaitingSince.get(id))),
        on ? "ok" : null);
      announce(sc.status.textContent);
    }
  }
  for (const id of [...scWaitingSince.keys()]) if (!pending.has(id)) scWaitingSince.delete(id);
  for (const id of pending) if (!scWaitingSince.has(id)) scWaitingSince.set(id, Date.now() / 1000);
  scWaiting = pending;
  if (pending.size) scStartPoll();
  else scStopPoll();
}

async function loadSecondCard() {
  if (!IS_TAURI || !sc.card) return;
  const seq = ++scReadSeq;
  let answer;
  try {
    answer = await invoke("get_second_card");
  } catch (error) {
    if (seq !== scReadSeq) return;
    scShowProblem(`Jarvis could not be asked about your graphics cards. ${scProblemWords(error)}`);
    return;
  }
  if (seq !== scReadSeq) return;
  if (answer && answer.available === false) {
    scShowProblem(typeof answer.why === "string" && answer.why ? answer.why : SC_UPDATE);
    return;
  }
  if (!answer || typeof answer !== "object" || !answer.detected || !Array.isArray(answer.features)) {
    scShowProblem(`Jarvis's answer about your graphics cards could not be read. ${SC_UPDATE}`);
    return;
  }
  scPaint(answer);
}

function scStartPoll() {
  if (!scPollUntil) scPollUntil = Date.now() + SC_POLL_FOR_MS;
  clearTimeout(scPollTimer);
  scPollTimer = null;
  // Gently, and not forever: after ten minutes a card nobody has answered is
  // left to the approval-queue signal and to the window coming back into view.
  if (Date.now() > scPollUntil) return;
  scPollTimer = setTimeout(() => {
    scPollTimer = null;
    // Not while the window is hidden; coming back into view re-reads.
    if (!document.hidden) loadSecondCard();
  }, SC_POLL_MS);
}

function scStopPoll() {
  clearTimeout(scPollTimer);
  scPollTimer = null;
  scPollUntil = 0;
}

/** One switch, one request. ON raises a card and nothing more. */
async function scToggle(sw, input) {
  const turnOn = input.checked;
  if (scBusy) {
    input.checked = !turnOn;
    return;
  }
  scBusy = true;
  input.disabled = true;
  report(sc.status, turnOn ? `Asking to turn on "${sw.name}"…` : `Turning off "${sw.name}"…`);
  try {
    const out = await invoke("set_second_card", { feature: sw.id, enabled: turnOn });
    if (turnOn && out && out.pending === true) {
      report(sc.status, SC_WAITING, "ok");
      announce(`"${sw.name}": ${SC_WAITING}`);
    } else if (out && typeof out.message === "string" && out.message) {
      report(sc.status, out.message, "ok");
    } else {
      report(sc.status, turnOn ? `"${sw.name}" is on.` : `"${sw.name}" is off.`, "ok");
    }
  } catch (error) {
    report(sc.status, scProblemWords(error), "bad");
    announce(sc.status.textContent, "assertive");
  } finally {
    scBusy = false;
  }
  // The switch shows what Jarvis says, never what was clicked: ON stays off
  // until the card is approved.
  await loadSecondCard();
}

if (sc.pinCopy) {
  sc.pinCopy.addEventListener("click", async () => {
    sc.pinCommand.select();
    let copied = false;
    try {
      await navigator.clipboard.writeText(sc.pinCommand.value);
      copied = true;
    } catch {
      try { copied = document.execCommand("copy"); } catch { copied = false; }
    }
    report(sc.pinStatus, copied ? "Copied. Paste it into PowerShell and press Enter." : "Select it and press Ctrl+C.",
      copied ? "ok" : null);
  });
}

// The approval-decided signal: the queue changes when a card is answered
// (or expires). Only worth a read while one of these cards is waiting.
onQueue(() => {
  if (scWaiting.size) loadSecondCard();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) loadSecondCard();
});
loadSecondCard();

/* ==========================================================================
   Big model (slow)
   --------------------------------------------------------------------------
   colibri, a separate program, runs a model far bigger than a graphics card
   holds, on the processor and the SSD, for background jobs only: the wiki
   builder and deep questions - never chat, voice or approvals
   (docs/BIG-MODEL.md). Read from `get_big_model` (GET /api/big-model, the
   backend's jarvis_big_model.status() - its real shape is
   tests/fixtures/big-model-cases.json), written one switch at a time with
   `set_big_model`.

   The same shape as the second graphics card above, on purpose: every
   switch is OFF until the owner turns it on, and none can be turned on until
   the backend says everything was found (`detected.capable`). Turning one ON
   approves nothing - the backend raises ONE approval card and answers
   `pending: true`, and the switch stays off until the owner says yes on that
   card. So this re-reads when the approval queue changes, when the window
   comes back into view, and gently every few seconds while a card waits (or
   while colibri is loading, which takes minutes). Turning OFF is immediate.

   Every sentence about what was found comes from the backend (`why`,
   `note`, `key_where`, `unverified`); nothing here guesses. The key colibri
   is started with never reaches this page - only where it is kept.
   ========================================================================== */

const bm = {
  card: $("big-model"),
  state: $("bm-state"),
  body: $("bm-body"),
  found: $("bm-found"),
  parts: $("bm-parts"),
  models: $("bm-models"),
  blocked: $("bm-blocked"),
  switches: $("bm-switches"),
  status: $("bm-status"),
  engine: $("bm-engine"),
  address: $("bm-address"),
  cuda: $("bm-cuda"),
  key: $("bm-key"),
  measured: $("bm-measured"),
  unverified: $("bm-unverified"),
};

const BM_UPDATE =
  "This PC's Jarvis does not have the big model part yet. Update the backend by running apply-patches.ps1, then open this again.";
/** The main switch has no row in `switches`; these are its words. */
const BM_MASTER = {
  id: "master",
  name: "Use the big model",
  what: "The main switch. Neither job below can be turned on until this one is on.",
};
const BM_ENGINE = { off: "Off", loading: "Loading", ready: "Ready", failed: "Failed" };
const BM_KIND = { medium: "medium model", giant: "giant model" };
/** Said even when the backend's own sentence is missing - the owner's rule. */
const BM_UNVERIFIED =
  "None of colibri's speed claims have been checked on this PC. The numbers here, from your own jobs, are the first real ones.";

let bmReadSeq = 0;
let bmBusy = false;
let bmPollTimer = null;
/** When the gentle re-reading stops; 0 while nothing is waiting. */
let bmPollUntil = 0;
/** Switches with a card waiting at the last read, to say how each ended. */
let bmWaiting = new Set();
/** When this page first saw each of those cards waiting, in seconds. */
const bmWaitingSince = new Map();
let bmPainted = false;

/** `scSentence`, except that colibri keeps its own lower-case name. */
function bmSentence(text) {
  return /^\s*colibri\b/.test(String(text || "")) ? scClause(text) : scSentence(text);
}

/** A number of gigabytes as the owner reads it: "3,100 GB", "25.3 GB". */
function bmGb(value) {
  const n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n)) return "";
  return `${n.toLocaleString("en-US", { maximumFractionDigits: 1 })} GB`;
}

function bmSeconds(value) {
  const s = Math.round(Number(value));
  if (!Number.isFinite(s) || s < 0) return "";
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60} s`;
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
}

/** One entry in a list: a name, and lines under it. */
function bmItem(name, lines, { tone, state } = {}) {
  const item = scNode("li", "sc-gpu");
  if (state) item.dataset.state = state;
  item.append(scNode("span", "sc-gpu-name", name));
  for (const line of lines) {
    if (!line) continue;
    const text = typeof line === "string" ? line : line.text;
    const node = scNode("span", "sc-gpu-role", text);
    if (typeof line === "object" && line.warn) node.classList.add("bm-warn");
    item.append(node);
  }
  if (tone) item.dataset.tone = tone;
  return item;
}

function bmParts(detected) {
  const colibri = detected.colibri || {};
  const python = detected.python || {};
  const ram = detected.ram || {};
  // Python is looked for only once colibri is found; the backend says "not
  // checked" then, which is not the same as missing.
  const found = (thing) => (thing.found === true ? "found"
    : /^\s*not checked/i.test(String(thing.why || "")) ? "not checked yet" : "not found");
  const memory = [bmGb(ram.total_gb) && `${bmGb(ram.total_gb)} in total`,
    bmGb(ram.available_gb) && `${bmGb(ram.available_gb)} free right now`].filter(Boolean);
  return [
    bmItem(`colibri: ${found(colibri)}`, [bmSentence(colibri.why)],
      { state: colibri.found === true ? "ok" : "missing" }),
    bmItem(`Python 3: ${found(python)}`, [bmSentence(python.why)],
      { state: python.found === true ? "ok" : "missing" }),
    bmItem("Memory", [memory.length ? `${memory.join(", ")}.` : "Jarvis could not read this PC's memory."]),
  ];
}

function bmModelItem(model) {
  const kind = BM_KIND[model.kind] || "model";
  const drive = String(model.drive || "").trim();
  const type = model.drive_type && model.drive_type !== "unknown" ? model.drive_type : "drive type unknown";
  const free = bmGb(model.free_gb);
  const lines = [
    model.dir ? `Folder: ${model.dir}` : "",
    drive ? `On ${drive} (${type}), ${free ? `${free} free` : "free space unknown"}.` : "",
    bmGb(model.need_gb) ? `Needs about ${bmGb(model.need_gb)} of free memory to run.` : "",
    bmSentence(model.why),
    model.note ? { text: bmSentence(model.note), warn: true } : "",
  ];
  return bmItem(`${model.name || model.id || "A model"} (${kind})`, lines,
    { state: model.usable === true ? "ok" : "missing" });
}

/**
 * Whether a switch may be changed now, and if not, why - in words. Only
 * turning ON is ever held back: a switch that is on can always be turned off.
 */
function bmHeld(sw, status) {
  if (sw.pending) return SC_WAITING;
  if (sw.enabled) return "";
  const detected = status.detected || {};
  if (detected.capable !== true) {
    return `Can't be turned on yet: ${scClause(detected.why) || "Jarvis has not found everything the big model needs."}`;
  }
  if (sw.id !== "master" && status.enabled !== true) return `Turn on "${BM_MASTER.name}" first.`;
  return "";
}

function bmMasterSwitch(status) {
  const detected = status.detected || {};
  let why = "Off.";
  if (status.enabled && status.active) why = "On.";
  else if (status.enabled) {
    why = `On, but it cannot run: ${scClause(detected.why) || "something it needs is missing."} Your choice is kept.`;
  }
  return { ...BM_MASTER, enabled: status.enabled === true,
    pending: (status.pending || []).includes("master"), why };
}

function bmSwitchRow(sw, status) {
  const row = scNode("div", "sc-switch");
  row.dataset.id = sw.id;
  row.dataset.state = sw.pending ? "waiting" : sw.enabled ? "on" : "off";

  const label = scNode("label", "toggle");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = `bm-switch-${sw.id}`;
  input.checked = Boolean(sw.enabled);
  const held = bmHeld(sw, status);
  input.disabled = Boolean(held);
  const text = scNode("span", "", sw.name);
  text.append(scNode("span", "toggle-detail", sw.what || ""));
  label.append(input, text);
  row.append(label);

  const lines = scNode("div", "sc-lines");
  const describedBy = [];
  const addLine = (className, words) => {
    if (!words) return;
    const line = scNode("p", className, words);
    line.id = `bm-${sw.id}-${className.split(" ").pop()}`;
    describedBy.push(line.id);
    lines.append(line);
  };
  addLine("sc-why", bmSentence(sw.why));
  const capable = (status.detected || {}).capable === true;
  if (sw.pending) addLine("sc-held sc-waiting", SC_WAITING);
  // With nothing found, the one line above the switches says why for all of
  // them. Nor twice when the backend's own line already says it ("Off. Turn
  // on the big model itself first.").
  else if (held && capable && !/\bfirst\b/i.test(String(sw.why || ""))) addLine("sc-held", held);
  if (held && !capable) describedBy.push("bm-blocked");
  if (sw.id !== "master") {
    const model = String(sw.model_name || sw.model || "").trim();
    addLine("sc-model", model ? `Model: ${model}.` : "No model is chosen for this job yet.");
  }
  if (describedBy.length) input.setAttribute("aria-describedby", describedBy.join(" "));
  row.append(lines);

  input.addEventListener("change", () => bmToggle(sw, input));
  return row;
}

function bmMeasuredItem(sw, m, names) {
  if (!m || typeof m !== "object") return bmItem(sw.name, ["Not measured on this PC yet."], { state: "none" });
  const model = names[m.model] || m.model || "the big model";
  const when = Number(m.at) > 0
    ? new Date(Number(m.at) * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : "";
  const lines = [
    `${m.words_per_s} words a second (${m.tokens_per_s} tokens a second).`,
    `${m.tokens} tokens in ${bmSeconds(m.seconds)}, by ${model}${when ? `, ${when}` : ""}.`,
  ];
  return bmItem(sw.name, lines, { state: "measured" });
}

function bmShowProblem(words) {
  bm.body.hidden = true;
  bm.state.hidden = false;
  bm.state.dataset.tone = "bad";
  bm.state.textContent = words;
  bmPainted = false;
  bmStopPoll();
}

function bmPaint(status) {
  const detected = status.detected || {};
  const jobs = status.switches.filter((s) => s && typeof s.id === "string");
  const pending = new Set(Array.isArray(status.pending) ? status.pending : []);
  const models = Array.isArray(detected.models) ? detected.models : [];
  const names = Object.fromEntries(models.map((m) => [m.id, String(m.name || m.id)]));

  bm.state.hidden = true;
  delete bm.state.dataset.tone;
  bm.body.hidden = false;

  bm.found.textContent = bmSentence(detected.why) || "Jarvis did not say what it found.";
  bm.parts.replaceChildren(...bmParts(detected));
  bm.models.replaceChildren(...(models.length ? models.map(bmModelItem)
    : [bmItem("No models set up", ["Add them to jarvis-framework.toml, [big_model] - docs/BIG-MODEL.md, step 3, says how."])]));

  bm.blocked.hidden = detected.capable === true;
  bm.blocked.textContent = detected.capable === true ? ""
    : `Nothing here can be turned on until Jarvis finds colibri, Python 3, a model and enough ` +
      `memory and disk: ${scClause(detected.why)} The switches are shown so you can see what is there.`;

  const rows = [bmMasterSwitch(status)].concat(jobs.map((s) => ({
    ...s, enabled: s.enabled === true, pending: pending.has(s.id) })));
  const focused = document.activeElement && document.activeElement.id;
  bm.switches.replaceChildren(...rows.map((sw) => bmSwitchRow(sw, status)));
  if (focused && focused.startsWith("bm-switch-")) {
    const again = document.getElementById(focused);
    if (again) again.focus();
  }

  const engine = status.engine || {};
  bm.engine.textContent = `${BM_ENGINE[engine.state] || "Unknown"}. ${bmSentence(engine.why)}`.trim() +
    (engine.busy === true ? " It is working on a job right now." : "");
  bm.engine.dataset.tone = engine.state === "ready" ? "ok" : engine.state === "failed" ? "bad" : "";
  const idle = Number(engine.idle_minutes);
  bm.address.textContent = [
    engine.listens_on ? `Listens on ${engine.listens_on} - this computer only.` : "",
    Number.isFinite(idle) && idle > 0 ? `Stops ${idle} minute${idle === 1 ? "" : "s"} after its last job.` : "",
  ].filter(Boolean).join(" ");
  bm.address.hidden = !bm.address.textContent;

  const cuda = status.cuda || {};
  bm.cuda.textContent = bmSentence(cuda.why) || "Jarvis did not say whether a graphics card is used.";
  bm.cuda.dataset.tone = cuda.setting === "on" && cuda.usable === false ? "bad" : "";

  const where = String(status.key_where || "").trim();
  const lead = { "not-made-yet": "Not made yet. It is ", "credential-manager": "Kept in ",
    "this-run-only": "Kept for this run only: " }[status.key_kept] || "Where it is kept: ";
  bm.key.textContent = where
    ? `${lead}${scClause(where)} The key itself is never shown here, and only colibri on this PC is given it.`
    : "Jarvis did not say where the key is kept.";

  const measured = status.measured && typeof status.measured === "object" ? status.measured : {};
  bm.measured.replaceChildren(...jobs.map((sw) => bmMeasuredItem(sw, measured[sw.id], names)));
  bm.unverified.textContent = String(status.unverified || "").trim() || BM_UNVERIFIED;

  // How each card that was waiting ended.
  if (bmPainted) {
    const byId = Object.fromEntries(jobs.map((s) => [s.id, s]));
    for (const id of bmWaiting) {
      if (pending.has(id)) continue;
      const name = id === "master" ? BM_MASTER.name : (byId[id] && byId[id].name) || id;
      const on = id === "master" ? status.enabled === true : Boolean(byId[id] && byId[id].enabled);
      report(bm.status, cardEndedWords(name, on, cardLast(status, id, bmWaitingSince.get(id))),
        on ? "ok" : null);
      announce(bm.status.textContent);
    }
  }
  bmPainted = true;
  for (const id of [...bmWaitingSince.keys()]) if (!pending.has(id)) bmWaitingSince.delete(id);
  for (const id of pending) if (!bmWaitingSince.has(id)) bmWaitingSince.set(id, Date.now() / 1000);
  bmWaiting = pending;
  if (pending.size || engine.state === "loading") bmStartPoll();
  else bmStopPoll();
}

async function loadBigModel() {
  if (!IS_TAURI || !bm.card) return;
  const seq = ++bmReadSeq;
  let answer;
  try {
    answer = await invoke("get_big_model");
  } catch (error) {
    if (seq !== bmReadSeq) return;
    bmShowProblem(`Jarvis could not be asked about the big model. ${scProblemWords(error)}`);
    return;
  }
  if (seq !== bmReadSeq) return;
  if (answer && answer.available === false) {
    bmShowProblem(typeof answer.why === "string" && answer.why ? answer.why : BM_UPDATE);
    return;
  }
  if (!answer || typeof answer !== "object" || !answer.detected || !Array.isArray(answer.switches)) {
    bmShowProblem(`Jarvis's answer about the big model could not be read. ${BM_UPDATE}`);
    return;
  }
  bmPaint(answer);
}

function bmStartPoll() {
  if (!bmPollUntil) bmPollUntil = Date.now() + SC_POLL_FOR_MS;
  clearTimeout(bmPollTimer);
  bmPollTimer = null;
  if (Date.now() > bmPollUntil) return;
  bmPollTimer = setTimeout(() => {
    bmPollTimer = null;
    if (!document.hidden) loadBigModel();
  }, SC_POLL_MS);
}

function bmStopPoll() {
  clearTimeout(bmPollTimer);
  bmPollTimer = null;
  bmPollUntil = 0;
}

/** One switch, one request. ON raises a card and nothing more. */
async function bmToggle(sw, input) {
  const turnOn = input.checked;
  if (bmBusy) {
    input.checked = !turnOn;
    return;
  }
  bmBusy = true;
  input.disabled = true;
  report(bm.status, turnOn ? `Asking to turn on "${sw.name}"…` : `Turning off "${sw.name}"…`);
  try {
    const out = await invoke("set_big_model", { switch: sw.id, enabled: turnOn });
    if (turnOn && out && out.pending === true) {
      report(bm.status, SC_WAITING, "ok");
      announce(`"${sw.name}": ${SC_WAITING}`);
    } else if (out && typeof out.message === "string" && out.message) {
      report(bm.status, out.message, "ok");
    } else {
      report(bm.status, turnOn ? `"${sw.name}" is on.` : `"${sw.name}" is off.`, "ok");
    }
  } catch (error) {
    report(bm.status, scProblemWords(error), "bad");
    announce(bm.status.textContent, "assertive");
  } finally {
    bmBusy = false;
  }
  // The switch shows what Jarvis says, never what was clicked.
  await loadBigModel();
}

onQueue(() => {
  if (bmWaiting.size) loadBigModel();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) loadBigModel();
});
loadBigModel();

loadUpdate();
