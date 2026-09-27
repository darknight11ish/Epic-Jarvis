/**
 * Settings -> "Check for tool updates" (the owner's own request, made
 * directly: "a feature that allows me to run it on request that looks for
 * updates of current tools that are integrated into Jarvis already (through
 * GitHub)."; backend jarvis_tool_updates.py, tool-updates.patch;
 * JARVIS-API.md section 48).
 *
 * A DIFFERENT thing from "Updates" above it on this same page (Jarvis
 * Desktop's own version, update.rs) - this checks the Python packages, Rust
 * building blocks and any pinned GitHub tool Jarvis is BUILT FROM.
 *
 * Report only: it never installs or changes a file itself. It shows the
 * exact command to run yourself, and stops there.
 *
 * Two Rust commands (src-tauri/src/tool_updates.rs):
 *  - get_tool_updates: GET /api/tool_updates - whether the owner has ever
 *    approved a check, whether one is running now, the last card's
 *    outcome, and the last finished report. A read.
 *  - check_tool_updates: POST /api/tool_updates/check {} - the FIRST press
 *    ever raises ONE approval card on the PC and returns at once; every
 *    later press starts the check in the background and also returns at
 *    once - it never blocks on the check itself, which can take a few
 *    minutes (crates.io is asked once per Rust crate NAME - 576 of them in
 *    this project alone today - and PyPI once per Python package). This
 *    page polls get_tool_updates while `waiting` or `checking` is true, the
 *    same "start it, poll for it" shape hardware-panel.js already uses for
 *    measuring the graphics cards.
 *
 * @module tool-updates-settings
 */

import { onLink, onQueue } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const DETAIL = "Jarvis can look up whether the Python packages, the Rust building blocks and " +
  "any pinned GitHub-hosted tool it is built from have a newer version out. It only reports - " +
  "it never installs or changes anything itself; it shows the exact command to run yourself. " +
  "The first time you press the button, Jarvis asks once, because it means reaching PyPI, " +
  "crates.io and GitHub over the internet; after that one yes it never asks again.";
const MISSING = "Your PC's Jarvis cannot check for tool updates yet - run apply-patches.ps1 " +
  "on this PC.";
const WAITING = "Waiting for your approval on the PC or phone.";
const POLL_MS = 4000;
const POLL_FOR_MS = 10 * 60 * 1000; // a real check can take a few minutes (576 Rust crates)

/** Never trusts the bridge's raw answer blindly (the same defence
 * backup-settings.js's readBackup uses). */
function readView(answer) {
  if (!answer || typeof answer !== "object" || answer.available === false) {
    const why = answer && typeof answer.why === "string" && answer.why.trim()
      ? answer.why.trim() : MISSING;
    return { available: false, why };
  }
  return answer;
}

const el = {
  section: $("tool-updates"),
  detail: $("tu-detail"),
  state: $("tu-state"),
  body: $("tu-body"),
  check: $("tu-check"),
  status: $("tu-status"),
  summary: $("tu-summary"),
  groups: $("tu-groups"),
};

let view = null;
let busy = false;
let pollTimer = null;
let pollUntil = 0;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function say(text, tone) {
  if (!el.status) return;
  el.status.textContent = text;
  if (tone) el.status.dataset.tone = tone;
  else delete el.status.dataset.tone;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Could not ask Jarvis. Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

/** One item row: "name: current -> latest" plus the command, when outdated. */
function itemRow(it) {
  const li = node("li", "sc-gpu");
  const words = it.outdated
    ? `${it.name}: you have ${it.current}, ${it.latest} is out`
    : `${it.name}: ${it.current} (latest)`;
  li.append(node("span", "sc-gpu-name", words));
  if (it.outdated && it.command) {
    const code = node("code", "", it.command);
    li.append(code);
  }
  if (it.note) li.append(node("p", "note", it.note));
  return li;
}

function unreachableRow(it) {
  return node("li", "note", `${it.name}: could not be checked (${it.why})`);
}

function groupBlock(g) {
  const box = node("div", "card");
  box.append(node("h3", "subhead", g.ecosystem));
  if (!g.available) {
    box.append(node("p", "note", g.why));
    return box;
  }
  if (g.why) box.append(node("p", "note", g.why));
  const outdated = g.items.filter((it) => it.outdated);
  const current = g.items.filter((it) => !it.outdated);
  if (!g.items.length && !g.unreachable.length) {
    box.append(node("p", "note", "Nothing to check here yet."));
    return box;
  }
  if (outdated.length) {
    const ul = node("ul", "sc-cards");
    ul.append(...outdated.map(itemRow));
    box.append(ul);
  }
  if (current.length) {
    box.append(node("p", "note", `${current.length} more already on the latest version.`));
  }
  if (g.unreachable.length) {
    const ul = node("ul", "sc-cards");
    ul.append(...g.unreachable.map(unreachableRow));
    box.append(ul);
  }
  return box;
}

function paint() {
  if (!el.section || !view) return;
  if (!view.available) {
    el.state.textContent = view.why;
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  el.state.hidden = true;
  el.body.hidden = false;
  el.detail.textContent = view.detail || DETAIL;
  el.check.textContent = view.button_label || "Check for tool updates";
  const busyNow = busy || view.waiting || view.checking;
  el.check.disabled = busyNow;
  if (view.waiting) {
    say(WAITING);
  } else if (view.checking) {
    say((view.last && view.last.message) || "Checking now - this can take a few minutes.");
  } else if (view.last && view.last.message && !el.status.textContent) {
    say(view.last.message, view.last.outcome === "denied" || view.last.outcome === "timed_out"
      ? "" : "ok");
  }
  const report = view.report;
  if (!report) {
    el.summary.hidden = true;
    el.groups.replaceChildren();
  } else {
    el.summary.hidden = false;
    el.summary.textContent = report.summary;
    el.groups.replaceChildren(...(report.groups || []).map(groupBlock));
  }
  if (busyNow) startPoll();
  else stopPoll();
}

async function load() {
  if (!el.section) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to check for tool updates.";
    el.state.hidden = false;
    return;
  }
  try {
    view = readView(await TAURI.core.invoke("get_tool_updates"));
  } catch (error) {
    el.state.textContent = problemWords(error);
    el.state.hidden = false;
    return;
  }
  paint();
}

async function check() {
  busy = true;
  say("");
  paint();
  try {
    const out = await TAURI.core.invoke("check_tool_updates");
    say(String((out && out.message) || ""));
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

function startPoll() {
  if (!pollUntil) pollUntil = Date.now() + POLL_FOR_MS;
  clearTimeout(pollTimer);
  if (Date.now() > pollUntil) { stopPoll(); return; }
  pollTimer = setTimeout(() => {
    pollTimer = null;
    if (!document.hidden) load();
  }, POLL_MS);
}

function stopPoll() {
  clearTimeout(pollTimer);
  pollTimer = null;
  pollUntil = 0;
}

if (el.section) {
  el.check.addEventListener("click", check);
}
onLink(() => paint());
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
