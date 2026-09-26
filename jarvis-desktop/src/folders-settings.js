/**
 * Settings -> "Folders Jarvis may look in" (the owner's decisions of
 * 2026-09-26; JARVIS-API.md section 35; backend jarvis_documents.py,
 * documents.patch).
 *
 * Four Rust commands (src-tauri/src/folders.rs), Settings only:
 *  - get_folders: the list, in the PC's words. A read.
 *  - add_folder: the Windows folder picker, then ONE approval card on the PC.
 *    Held on a stale link here (greyed) and in Rust.
 *  - remove_folder {path}: at once, never held.
 *  - import_notion {into}: the Windows file picker for the .zip Notion made,
 *    then the PC unzips it into a new folder inside `into`. Held on a stale
 *    link. No card: the owner chose the file and the folder here.
 *
 * The page never gets a file system of its own: the pickers are in Rust, and
 * only a chosen path comes back.
 *
 * @module folders-settings
 */

import { announce, currentLink, linkWords, onLink, onQueue } from "./jarvis-link.js";
import {
  actions,
  ADD_LABEL,
  folderLines,
  NOTION_LABEL,
  readFolders,
  STALE,
} from "./folders.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("folders"),
  detail: $("fo-detail"),
  state: $("fo-state"),
  body: $("fo-body"),
  list: $("fo-list"),
  empty: $("fo-empty"),
  add: $("fo-add"),
  addWhy: $("fo-add-why"),
  docs: $("fo-docs"),
  notionTitle: $("fo-notion-title"),
  notionDetail: $("fo-notion-detail"),
  notionInto: $("fo-notion-into"),
  notionPick: $("fo-notion-pick"),
  status: $("fo-status"),
};

let view = null;
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
  // textContent everywhere: folder names are the owner's, never markup.
  el.detail.textContent = view.detail;
  const can = actions(view, live());
  el.list.replaceChildren(...view.folders.map((f) => {
    const li = node("li", "sc-gpu");
    li.append(node("span", "sc-gpu-name", f.name));
    for (const line of folderLines(f)) li.append(node("span", "sc-gpu-role", line));
    const rm = node("button", "btn small", view.removeLabel);
    rm.type = "button";
    rm.disabled = busy || !can.remove;
    rm.addEventListener("click", () => remove(f.path));
    li.append(rm);
    return li;
  }));
  el.empty.hidden = view.folders.length > 0;
  el.empty.textContent = view.why || view.empty;
  el.add.textContent = ADD_LABEL;
  el.add.disabled = busy || !can.add;
  el.addWhy.textContent = view.waiting ? `${view.waitingWords} (${view.waiting})` : can.addWhy;
  el.addWhy.hidden = !el.addWhy.textContent;
  el.docs.textContent = view.documentsSaid;
  el.docs.dataset.tone = view.documentsReady ? "ok" : "warn";
  el.notionTitle.textContent = view.notionTitle;
  el.notionDetail.textContent = view.notionDetail;
  const keep = el.notionInto.value;
  el.notionInto.replaceChildren(...view.folders.filter((f) => f.exists).map((f) => {
    const o = node("option", "", f.name);
    o.value = f.path;
    return o;
  }));
  if (keep) el.notionInto.value = keep;
  el.notionInto.disabled = busy || !can.notion;
  el.notionPick.textContent = NOTION_LABEL;
  el.notionPick.disabled = busy || !can.notion;
  if (view.lastWords && !el.status.textContent) say(view.lastWords);
}

async function load() {
  if (!el.section) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to choose folders.";
    return;
  }
  try {
    view = readFolders(await TAURI.core.invoke("get_folders"));
  } catch (error) {
    el.state.textContent = problemWords(error);
    el.state.hidden = false;
    return;
  }
  paint();
}

async function run(command, args, working) {
  if (busy) return;
  busy = true;
  say(working);
  paint();
  try {
    const out = await TAURI.core.invoke(command, args);
    if (out && out.cancelled) {
      say("");
    } else {
      const words = String((out && (out.message || out.said || out.error)) || "Done.");
      say(words, out && out.ok === false ? "bad" : "ok");
      announce(words);
    }
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

function add() {
  if (!live()) {
    say(STALE, "bad");
    return;
  }
  run("add_folder", {}, "Choose a folder…");
}

function remove(path) {
  run("remove_folder", { path }, "Removing…");
}

function notion() {
  if (!live()) {
    say(STALE, "bad");
    return;
  }
  const into = el.notionInto.value;
  if (!into) return;
  run("import_notion", { into }, "Choose the .zip Notion made…");
}

if (el.section) {
  el.add.addEventListener("click", add);
  el.notionPick.addEventListener("click", notion);
}
onLink(() => paint());
// A card answered (or expired): the list may have changed. onQueue also
// delivers the current queue at once - the first read.
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
