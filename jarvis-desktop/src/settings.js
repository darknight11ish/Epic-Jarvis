/**
 * Settings.
 *
 * Two things are writable here and nothing else: where the backend is, and
 * whether Jarvis Desktop may start one. Everything the desktop will show in
 * build order step 5 — models, memory, the enforced config, skills — is
 * read-only by design, and `POST /api/config` answers 501 on purpose, so this
 * page is deliberately not the beginning of a control panel.
 *
 * The token is write-only from here. `get_api_settings` reports whether one is
 * set and never returns it, so a blank field means "keep what you have" and
 * there is no path by which the secret comes back into a webview.
 */

import {
  announce,
  applyTheme,
  followTheme,
  followZoom,
  onLink,
  reconnect,
  start as startLink,
  THEMES,
} from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

const $ = (id) => document.getElementById(id);

const dom = {
  base: $("base"),
  token: $("token"),
  tokenState: $("token-state"),
  saveConnection: $("save-connection"),
  clearToken: $("clear-token"),
  connectionStatus: $("connection-status"),
  linkState: $("link-state"),
  linkText: $("link-text"),
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

  hotkeyRows: $("hotkey-rows"),
  saveHotkeys: $("save-hotkeys"),
  resetHotkeys: $("reset-hotkeys"),
  hotkeyStatus: $("hotkey-status"),

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

async function loadConnection() {
  const settings = await invoke("get_api_settings");
  dom.base.value = settings.base || "";
  dom.tokenState.textContent = settings.hasToken ? "set" : "not set";
  dom.clearToken.disabled = !settings.hasToken;
  dom.storePath.textContent = settings.store || "";
}

dom.saveConnection.addEventListener("click", () =>
  act(dom.saveConnection, dom.connectionStatus, async () => {
    const base = dom.base.value.trim();
    const token = dom.token.value;
    // An untouched token field means "keep the current one" — passing "" would
    // clear it, which is not what leaving a field alone should ever mean.
    await invoke("set_api_settings", {
      base,
      token: token.length ? token : null,
    });
    dom.token.value = "";
    await loadConnection();
    // The stream is pointed at the old base until it reconnects.
    reconnect();
    return "Saved. Reconnecting the event stream.";
  })
);

dom.clearToken.addEventListener("click", () =>
  act(dom.clearToken, dom.connectionStatus, async () => {
    await invoke("set_api_settings", { base: null, token: "" });
    await loadConnection();
    reconnect();
    return "Token cleared.";
  })
);

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

  if (status.owned) {
    const up = Number(status.uptime_seconds || 0);
    const handedOff = status.launcher_exited
      ? " · launcher exited, tree still supervised"
      : "";
    dom.backendState.textContent =
      `started by Jarvis Desktop · pid ${status.pid} · up ${formatUptime(up)}${handedOff} · ${status.base}`;
  } else if (!status.supervise) {
    dom.backendState.textContent =
      `supervision off · Jarvis Desktop will not start or stop anything · ${status.base}`;
  } else if (!status.configured) {
    dom.backendState.textContent = "supervision on, but no program is configured";
  } else {
    dom.backendState.textContent =
      `supervision on · not started by Jarvis Desktop · ${status.base}`;
  }
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

const themePicker = $("theme");
if (themePicker) {
  themePicker.addEventListener("change", async () => {
    // Paint immediately so the control feels connected, then persist. If the
    // write fails the fan-out below puts it back.
    applyTheme(themePicker.value);
    try {
      await invoke("set_theme", { theme: themePicker.value });
    } catch (error) {
      console.error("[settings] could not save the theme:", error);
    }
  });
}

followTheme((theme) => {
  if (themePicker) themePicker.value = theme;
});

// This window is user-resizable, so nothing needs to re-measure after a step.
followZoom();

startLink();

onLink((link) => {
  dom.linkState.dataset.connected = String(link.connected);
  if (link.connected) {
    const bits = [`event stream live on ${link.base}`, link.power];
    if (link.activity !== "idle") bits.push(link.activity);
    if (link.approvals > 0) bits.push(`${link.approvals} waiting`);
    dom.linkText.textContent = bits.join(" · ");
  } else {
    dom.linkText.textContent = link.error || "no event stream";
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
  // Cheap, and only while the window is actually on screen — a settings page
  // nobody is looking at has no reason to poll.
  let timer = null;
  const poll = () => {
    if (timer) clearInterval(timer);
    timer = document.hidden ? null : setInterval(paintBackend, 5000);
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
