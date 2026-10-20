/**
 * Settings -> "Searchable recordings and videos" (F5 S2; the owner's decision
 * of 2026-10-19: keep READABLE transcript text, switch ON by default;
 * backend/jarvis_media_index.py, the drop-in folder plugins/ready/media-index/,
 * and the route GET/POST /api/media-index it installs; JARVIS-API section 149).
 *
 * One Rust command (`src-tauri/src/media_index.rs` `media_index`), Settings
 * only:
 *  - read:   the switch, how many recordings/words are stored, how many are
 *            still waiting, and the PC's own disclosure sentence.
 *  - off:    at once, and never held.
 *  - on:     ONE normal approval card on the PC, decided in the Jarvis bar;
 *            nothing changes before a person says yes. Held on a stale link.
 *  - delete: THE ONE DELETE - removes every stored word and the index file.
 *            It never touches a recording, and it is never held.
 *
 * The page never sees a word from a recording: this is a switch, a few
 * counts, the disclosure, and a Delete button. The disclosure below the title
 * is written plainly BY THE PAGE as well as by the PC, so it is readable even
 * when the PC is unreachable.
 *
 * @module media-index-settings
 */

import { currentLink, linkWords, onLink } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

const $ = (id) => document.getElementById(id);

const el = {
  body: $("mi-body"),
  reading: $("mi-reading"),
  disclosure: $("mi-disclosure"),
  sw: $("mi-switch"),
  linkNote: $("mi-link-note"),
  line: $("mi-line"),
  counts: $("mi-counts"),
  deleteBtn: $("mi-delete"),
  say: $("mi-status"),
};

const ASKING = "Asking the PC…";
const OFF_ON = "Turn searchable recordings on";
const OFF_OFF = "Turn searchable recordings off";
const WAITING_LINK = "The connection is catching up. Turning it back on needs a live " +
  "connection (it asks for your approval); turning it off and Delete work at once.";

let view = null;
let busy = false;

function live() {
  return linkWords(currentLink()).canAct;
}

function say(text, tone) {
  if (!el.say) return;
  el.say.textContent = text;
  if (tone) el.say.dataset.tone = tone;
  else delete el.say.dataset.tone;
}

function countsWords(v) {
  if (!v) return "";
  if (!v.files) return "Nothing stored yet. Ask Jarvis about your recordings to fill it in.";
  return `${v.files} recording${v.files === 1 ? "" : "s"} with ${v.lines} stored line` +
    `${v.lines === 1 ? "" : "s"}${v.pending ? `, ${v.pending} still to read` : ""}`;
}

function paint() {
  if (!el.body) return;
  el.reading.hidden = true;
  el.body.hidden = false;
  if (!view) {
    if (el.sw) el.sw.disabled = true;
    if (el.deleteBtn) el.deleteBtn.disabled = true;
    return;
  }
  if (el.disclosure && typeof view.disclosure === "string" && view.disclosure) {
    el.disclosure.textContent = view.disclosure;
  }
  // Turning it ON asks for a card, so it needs a live link; turning it OFF and
  // Delete never wait (rule 4 only holds what loosens).
  const held = !view.enabled && !live();
  if (el.sw) {
    el.sw.disabled = busy || held;
    el.sw.textContent = view.enabled ? OFF_OFF : OFF_ON;
  }
  if (el.linkNote) {
    el.linkNote.textContent = held ? WAITING_LINK : "";
    el.linkNote.hidden = !held;
  }
  if (el.line) el.line.textContent = view.line || "";
  if (el.counts) el.counts.textContent = countsWords(view);
  if (el.deleteBtn) {
    el.deleteBtn.disabled = busy || !view.files;
  }
  if (view.last && view.last.message) {
    const tone = view.last.outcome === "enabled" ? "ok" : "warn";
    if (!el.say.textContent) say(view.last.message, tone);
  }
}

async function load() {
  if (!el.body || !IS_TAURI) return;
  try {
    view = await TAURI.core.invoke("media_index", { action: "read" });
  } catch (error) {
    view = null;
    el.body.hidden = true;
    el.reading.hidden = false;
    el.reading.textContent = String((error && error.message) || error ||
      "The PC could not be asked about searchable recordings.");
    return;
  }
  paint();
}

async function setSwitch(on) {
  if (busy) return;
  busy = true;
  say(ASKING);
  paint();
  try {
    const out = await TAURI.core.invoke("media_index", { action: on ? "on" : "off" });
    say((out && out.message) || (on ? "Asked." : "Off."), "ok");
  } catch (error) {
    say(String((error && error.message) || error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

async function deleteAll() {
  if (busy) return;
  const sure = window.confirm(
    "Delete every stored word from your recordings? This removes the index " +
    "file on this PC - it is never in a backup, so it cannot be undone. Your " +
    "original recordings are not touched.");
  if (!sure) return;
  busy = true;
  say(ASKING);
  paint();
  try {
    const out = await TAURI.core.invoke("media_index", { action: "delete" });
    say((out && out.words) || "Deleted.", "ok");
  } catch (error) {
    say(String((error && error.message) || error), "warn");
  } finally {
    busy = false;
  }
  await load();
}

if (el.body && IS_TAURI) {
  el.sw?.addEventListener("click", () => setSwitch(!(view && view.enabled)));
  el.deleteBtn?.addEventListener("click", deleteAll);
  onLink(() => paint());
  load();
} else if (el.body) {
  el.reading.textContent = "This window cannot ask the PC.";
} else if (el.reading) {
  el.reading.textContent = "This window cannot ask the PC.";
}
