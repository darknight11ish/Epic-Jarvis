/**
 * Settings -> "Backups" (the owner's decision of 2026-09-27, CLAUDE.md:
 * "one locked backup file into a folder the owner picks ... locked with a
 * recovery code only the owner has (shown once) ... Jarvis keeps only the
 * last few"; backend jarvis_backup.py, backup.patch; JARVIS-API.md section
 * 44).
 *
 * Six Rust commands (src-tauri/src/backup.rs), Settings only:
 *  - get_backup: GET /api/backup - the folder, a waiting card, the last
 *    backup and the last restore's outcome. A read.
 *  - set_backup_folder: the Windows folder picker (the same one "Folders
 *    Jarvis may look in" uses), then ONE approval card on the PC. Held on
 *    a stale link.
 *  - backup_now: no card - the folder was already approved. Returns a
 *    fresh recovery code, shown here ONCE and never asked for again.
 *  - list_backups: the files in the folder, newest first. A read.
 *  - preview_restore(name, code): decrypts to show counts and a date -
 *    never content. Changes nothing.
 *  - restore_backup(name, code): ONE approval card that always needs
 *    Windows Hello. Its answer may carry a SECOND one-time recovery code -
 *    for the safety backup Jarvis makes of the current state first, so
 *    the restore itself can be undone.
 *
 * The recovery code is never sent anywhere by this page, never written to
 * this app's own storage, and disappears from the screen once this panel
 * is left - Jarvis does not keep a second copy either.
 *
 * @module backup-settings
 */

import { onLink, onQueue, currentLink, linkWords } from "./jarvis-link.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const DETAIL = "Jarvis can write one locked backup file - your memory, chat history, " +
  "settings and notes, encrypted - into a folder you pick. A NordLocker or similar " +
  "cloud-synced folder is fine: that program uploads the file, as it does anything " +
  "else you put there, and the file itself stays locked either way. Jarvis keeps the " +
  "newest 5 backups there and deletes older ones.";
const LOST_CODE_WARN = "Write this down or save it somewhere safe now. Jarvis will not " +
  "show it again, and cannot recover it. If it is lost, this backup can never be " +
  "opened again - there is no other way in.";
const NO_FOLDER_WHY = "Choose a folder before backing up.";
const MISSING = "Your PC's Jarvis cannot make backups yet - run apply-patches.ps1 on this PC.";

/** Never trusts the bridge's raw answer blindly (the same defence
 * folders.js's readFolders uses): a missing, malformed or unavailable
 * answer becomes one honest shape, never a thrown error. */
function readBackup(answer) {
  if (!answer || typeof answer !== "object" || answer.available === false) {
    const why = answer && typeof answer.why === "string" && answer.why.trim()
      ? answer.why.trim() : MISSING;
    return { available: false, why };
  }
  return answer;
}

const el = {
  section: $("backup"),
  detail: $("bk-detail"),
  state: $("bk-state"),
  body: $("bk-body"),
  folder: $("bk-folder"),
  chooseFolder: $("bk-choose-folder"),
  folderWhy: $("bk-folder-why"),
  now: $("bk-now"),
  last: $("bk-last"),
  codeBox: $("bk-code-box"),
  codeTitle: $("bk-code-title"),
  codeWarn: $("bk-code-warn"),
  code: $("bk-code"),
  codeCopy: $("bk-code-copy"),
  codeDone: $("bk-code-done"),
  empty: $("bk-empty"),
  list: $("bk-list"),
  eraseLimit: $("bk-erase-limit"),
  status: $("bk-status"),
};

let view = null;
let backups = [];
let busy = false;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function live() {
  return linkWords(currentLink()).canAct;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Could not ask Jarvis. Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function say(text, tone) {
  if (!el.status) return;
  el.status.textContent = text;
  if (tone) el.status.dataset.tone = tone;
  else delete el.status.dataset.tone;
}

function ago(seconds) {
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - seconds));
  if (secs < 90) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 90) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 36) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function when(seconds) {
  try {
    return new Date(seconds * 1000).toLocaleString();
  } catch {
    return "";
  }
}

/** Shows a recovery code once, with the standard warning. Cleared only by
 * leaving the panel (reload) or pressing "I've saved it" - never re-shown. */
function showCode(title, code) {
  el.codeTitle.textContent = title;
  el.codeWarn.textContent = LOST_CODE_WARN;
  el.code.textContent = code;
  el.codeBox.hidden = false;
}

function hideCode() {
  el.codeBox.hidden = true;
  el.code.textContent = "";
}

function restoreRow(b) {
  const li = node("li", "sc-gpu");
  li.append(node("span", "sc-gpu-name", when(b.at)));
  li.append(node("span", "sc-gpu-role", `${(b.size / 1024).toFixed(0)} KB`));
  const codeInput = document.createElement("input");
  codeInput.type = "text";
  codeInput.placeholder = "Recovery code";
  codeInput.autocomplete = "off";
  codeInput.spellcheck = false;
  const preview = node("button", "btn small", "Preview…");
  preview.type = "button";
  const restore = node("button", "btn small", "Restore…");
  restore.type = "button";
  const out = node("p", "note", "");
  preview.addEventListener("click", () => doPreview(b.name, codeInput.value, out));
  restore.addEventListener("click", () => doRestore(b.name, codeInput.value, out));
  const row = node("div", "row");
  row.append(codeInput, preview, restore);
  li.append(row, out);
  return li;
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
  el.detail.textContent = DETAIL;
  el.folder.textContent = view.folder || "Not set";
  el.chooseFolder.disabled = busy;
  const pendingFolder = view.pending_folder_card;
  el.folderWhy.textContent = pendingFolder
    ? "Waiting for your approval on the PC."
    : (!view.folder ? NO_FOLDER_WHY : "");
  el.folderWhy.hidden = !el.folderWhy.textContent;
  el.now.disabled = busy || !view.folder;
  const lastBackup = view.last_backup;
  el.last.textContent = lastBackup
    ? (lastBackup.ok
      ? `Last backup: ${ago(lastBackup.at)} (${when(lastBackup.at)}).`
      : `Last backup attempt failed: ${lastBackup.error}`)
    : "No backup has been made yet.";
  const pendingRestore = view.pending_restore_card;
  const lastRestore = view.last_restore;
  if (pendingRestore) {
    say("Waiting for your approval, with Windows Hello.");
  } else if (lastRestore && lastRestore.message && !el.status.textContent) {
    say(lastRestore.message, lastRestore.outcome === "restored" ? "ok" : "");
  }
  if (lastRestore && lastRestore.safety_backup && lastRestore.safety_backup.recovery_code) {
    showCode(
      "Your data just before the restore",
      lastRestore.safety_backup.recovery_code,
    );
  }
  el.empty.hidden = backups.length > 0;
  el.list.replaceChildren(...backups.map(restoreRow));
  el.eraseLimit.textContent = view.erase_limit || "";
}

async function load() {
  if (!el.section) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to set up backups.";
    el.state.hidden = false;
    return;
  }
  try {
    view = readBackup(await TAURI.core.invoke("get_backup"));
  } catch (error) {
    el.state.textContent = problemWords(error);
    el.state.hidden = false;
    return;
  }
  if (view.available && view.folder) {
    try {
      const out = await TAURI.core.invoke("list_backups");
      backups = (out && out.backups) || [];
    } catch {
      backups = [];
    }
  } else {
    backups = [];
  }
  paint();
}

async function chooseFolder() {
  if (!live()) {
    say("The connection to Jarvis is catching up, so nothing can be sent until it does.", "bad");
    return;
  }
  busy = true;
  say("Choose a folder…");
  paint();
  try {
    const out = await TAURI.core.invoke("set_backup_folder");
    if (out && out.cancelled) {
      say("");
    } else {
      const words = String((out && (out.message || out.error)) || "Done.");
      say(words, out && out.ok === false ? "bad" : "ok");
    }
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

async function backupNow() {
  busy = true;
  say("Backing up…");
  paint();
  try {
    const out = await TAURI.core.invoke("backup_now");
    if (out && out.ok && out.recovery_code) {
      showCode("Your new backup's recovery code", out.recovery_code);
      say(out.message || "Backed up.", "ok");
    } else {
      say(String((out && (out.message || out.error)) || "Could not back up."),
        out && out.ok === false ? "bad" : "");
    }
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

async function doPreview(name, code, out) {
  if (!code) {
    out.textContent = "Type the recovery code first.";
    return;
  }
  out.textContent = "Checking…";
  try {
    const resp = await TAURI.core.invoke("preview_restore", { name, code });
    if (resp && resp.ok) {
      const counts = resp.counts || {};
      const dbs = Object.entries(counts.databases || {})
        .map(([db, tables]) => `${db}: ${Object.values(tables).reduce((a, b) => a + b, 0)} rows`)
        .join(", ");
      out.textContent = `Made ${when(resp.created_at)}. ${dbs}. ` +
        `${counts.settings_files || 0} settings files, ${counts.notes_files || 0} notes.`;
    } else {
      out.textContent = problemWords(resp && resp.error);
    }
  } catch (error) {
    out.textContent = problemWords(error);
  }
}

async function doRestore(name, code, out) {
  if (!code) {
    out.textContent = "Type the recovery code first.";
    return;
  }
  if (!live()) {
    out.textContent = "The connection to Jarvis is catching up, so nothing can be sent " +
      "until it does.";
    return;
  }
  if (!window.confirm(
    "Restore Jarvis from this backup? This replaces your memory, chat history, settings " +
    "and notes with what was saved then. You will need to approve a card with Windows " +
    "Hello. Jarvis backs up your current data first, so this can be undone.")) {
    return;
  }
  busy = true;
  out.textContent = "Waiting for your approval, with Windows Hello…";
  paint();
  try {
    const resp = await TAURI.core.invoke("restore_backup", { name, code });
    out.textContent = String((resp && resp.message) || "Waiting for your approval.");
  } catch (error) {
    out.textContent = problemWords(error);
  } finally {
    busy = false;
  }
  await load();
}

if (el.section) {
  el.chooseFolder.addEventListener("click", chooseFolder);
  el.now.addEventListener("click", backupNow);
  el.codeCopy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(el.code.textContent || "");
      say("Copied. Paste it somewhere safe now.", "ok");
    } catch {
      say("Could not copy - select the code and copy it by hand.", "bad");
    }
  });
  el.codeDone.addEventListener("click", hideCode);
}
onLink(() => paint());
// A card answered (or expired): the folder or the last outcome may have
// changed. onQueue also delivers the current queue at once - the first read.
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
