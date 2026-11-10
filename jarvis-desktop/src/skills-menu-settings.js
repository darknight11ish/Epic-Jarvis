/**
 * Settings -> "Skills": the skills menu (the owner's decision of 2026-11-02,
 * scope B of `.dsh-scratch/OWNER-QUEUE-2026-11-02/HERMES-SKILLS-RESEARCH.md`;
 * `skills_menu.rs`, `backend/jarvis_skill_menu.py`,
 * `plugins/ready/skill-menu/`, JARVIS-API.md section 178).
 *
 * ONE Rust command (`skills_menu`) with ten actions, Settings only:
 *  - read:        the list - every installed skill, every turned-off one, its
 *                 verdict and its `scripts/` sentence. A read, never held.
 *  - pick_folder / pick_zip: the Windows dialogs, and nothing else.
 *  - scan:        the PC's scanner on what was picked - verdict, findings, the
 *                 warnings to read. The PC raises NO card for this.
 *  - install:     the same scanner, then ONE approval card on the PC. Nothing
 *                 is installed before a person says yes, and a skill the
 *                 scanner refuses never becomes a card at all.
 *  - import_scan: a read-only scan of %USERPROFILE%\.hermes\skills. Installs
 *                 nothing, raises no card. Each folder is then its own install
 *                 and its own ONE card - there is no "import all".
 *  - enable:      ONE card, then the skill is installed again from skills-off\.
 *  - disable:     at once, never held. Nothing is deleted.
 *  - remove_off:  deletes ONE skill that is ALREADY turned off - the copy this
 *                 menu parked in skills-off\. At once, never held: it is out of
 *                 the load path already, so it only takes something away.
 *  - edit:        the same scanner and the same ONE card for a SKILL.md the
 *                 owner edited here. A block finding never reaches the card.
 *
 * Remove of an INSTALLED skill is NOT here: it already exists
 * (POST /api/skills/decide with {"remove": true}) and the Brain's own command
 * does it, with its "are you sure?". This card calls that same command, so
 * there is one removal path for an installed skill. The one thing that path
 * cannot reach is the copy this menu itself parked in skills-off\ - the PC
 * resolves an uninstall name only under the skills folder - so `remove_off`
 * deletes that copy through the same state route that parked it, and the PC
 * refuses an installed name there outright. Two objects, two doors, and no
 * folder reachable from both.
 *
 * Nothing on this page downloads anything, browses a marketplace, or runs a
 * script inside a skill. The PC's words are shown as they arrive.
 *
 * @module skills-menu-settings
 */

import { announce, currentLink, linkWords, onLink, onQueue } from "./jarvis-link.js";
import {
  answerWords,
  CHOOSING,
  CREATOR_MISSING,
  creatorView,
  importView,
  menuView,
  MISSING,
  refusedWords,
  scanView,
  WAITING_LINK,
} from "./skills-menu-rules.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("skills-menu"),
  state: $("sk-state"),
  body: $("sk-body"),
  list: $("sk-list"),
  offTitle: $("sk-off-title"),
  offList: $("sk-off-list"),
  empty: $("sk-empty"),
  installFolder: $("sk-install-folder"),
  installZip: $("sk-install-zip"),
  hermes: $("sk-hermes"),
  hermesWhy: $("sk-hermes-why"),
  hermesRoot: $("sk-hermes-root"),
  importList: $("sk-import-list"),
  importNote: $("sk-import-note"),
  pickTitle: $("sk-pick-title"),
  pickDetail: $("sk-pick-detail"),
  pickInert: $("sk-pick-inert"),
  pickFindings: $("sk-pick-findings"),
  pickFindingsNone: $("sk-pick-findings-none"),
  pickGo: $("sk-pick-go"),
  pickCancel: $("sk-pick-cancel"),
  creator: $("sk-creator"),
  creatorFolder: $("sk-creator-folder"),
  creatorList: $("sk-creator-list"),
  creatorNote: $("sk-creator-note"),
  creatorRefresh: $("sk-creator-refresh"),
  editTitle: $("sk-edit-title"),
  editText: $("sk-edit-text"),
  editNote: $("sk-edit-note"),
  editInert: $("sk-edit-inert"),
  editSave: $("sk-edit-save"),
  editCancel: $("sk-edit-cancel"),
  status: $("sk-status"),
};

let view = null;
let creator = null; // the waiting folder's own read; see loadCreator()
let busy = false;
let pending = null; // the scanned source, waiting for "Install it"
let editing = null; // the skill whose text is in the editor

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function live() {
  return linkWords(currentLink()).canAct;
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

/** One invoke of the one command, with every argument named. */
async function ask(action, args = {}) {
  return TAURI.core.invoke("skills_menu", {
    action,
    path: args.path ?? null,
    hermes: args.hermes ?? null,
    name: args.name ?? null,
    text: args.text ?? null,
    acceptWarnings: args.acceptWarnings ?? false,
  });
}

async function working(text, fn) {
  if (busy) return null;
  busy = true;
  say(text);
  paint();
  try {
    return await fn();
  } catch (error) {
    say(problemWords(error), "bad");
    return null;
  } finally {
    busy = false;
    paint();
  }
}

function line(li, text) {
  if (text) li.append(node("span", "sc-gpu-role", text));
}

function skillRow(skill) {
  const li = node("li", "sc-gpu");
  li.dataset.skill = skill.name;
  li.append(node("span", "sc-gpu-name", skill.name));
  line(li, skill.description);
  const bits = [];
  if (skill.trust) bits.push(`Trust: ${skill.trust}`);
  if (skill.verdict) bits.push(`scanned: ${skill.verdict}`);
  if (skill.uses) bits.push(`used ${skill.uses} time(s)`);
  line(li, bits.join(" · "));
  // The owner's own sentence, when the PC sent one: a scripts/ folder is kept
  // and never run.
  line(li, skill.inert);
  const buttons = node("div", "row");
  const off = node("button", "btn small", "Turn off");
  off.type = "button";
  off.disabled = busy;
  off.addEventListener("click", () => turn(skill.name, false));
  const edit = node("button", "btn small", "Edit");
  edit.type = "button";
  edit.disabled = busy;
  edit.addEventListener("click", () => openEditor(skill.name));
  const rm = node("button", "btn small", "Remove…");
  rm.type = "button";
  rm.disabled = busy;
  rm.addEventListener("click", () => remove(skill.name));
  buttons.append(off, edit, rm);
  li.append(buttons);
  return li;
}

function offRow(skill) {
  const li = node("li", "sc-gpu");
  li.dataset.skill = skill.name;
  li.append(node("span", "sc-gpu-name", `${skill.name} - turned off`));
  line(li, skill.description);
  line(li, skill.inert);
  const buttons = node("div", "row");
  const on = node("button", "btn small", "Turn on…");
  on.type = "button";
  on.disabled = busy;
  on.addEventListener("click", () => turn(skill.name, true));
  // Removing a turned-off skill is a different question from turning it back
  // on, and the PC has a different door for it (see `removeOff`).
  const rm = node("button", "btn small", "Remove…");
  rm.type = "button";
  rm.disabled = busy;
  rm.addEventListener("click", () => removeOff(skill.name));
  buttons.append(on, rm);
  li.append(buttons);
  return li;
}

function paint() {
  paintSkills();
  paintCreator();
}

function paintSkills() {
  if (!el.section) return;
  if (!view) return;
  if (!view.available) {
    el.state.textContent = view.why || MISSING;
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  el.state.hidden = true;
  el.body.hidden = false;
  el.list.replaceChildren(...view.skills.map(skillRow));
  el.empty.hidden = view.skills.length > 0;
  el.empty.textContent = view.note || "No skills are installed yet.";
  el.offTitle.hidden = view.off.length === 0;
  el.offList.hidden = view.off.length === 0;
  el.offList.replaceChildren(...view.off.map(offRow));
  el.hermes.hidden = false;
  el.hermes.disabled = busy;
  el.hermesWhy.textContent = view.hermes.available
    ? ""
    : view.hermes.why || "There is no Hermes skills folder on this PC.";
  el.hermesWhy.hidden = !el.hermesWhy.textContent;
  el.hermesRoot.textContent = view.hermes.available ? view.hermes.root : "";
  el.hermesRoot.hidden = !el.hermesRoot.textContent;
  el.installFolder.disabled = busy;
  el.installZip.disabled = busy;
  // The three doors that raise a card need a live event stream (rule 4); say
  // so before a press rather than after one fails.
  if (!live() && !el.status.textContent) say(WAITING_LINK);
}

/* ── Creator mode: things waiting in one folder on this PC ──────────────── */

/**
 * One waiting item. The PC says what it is, what the scanner found and whether
 * it may be installed; the page only draws that. A row the PC refuses never
 * gets a button, because the PC would not draw a card for it.
 */
function creatorItemRow(item) {
  const li = node("li", "sc-gpu");
  li.dataset.skill = `creator:${item.name}`;
  li.append(node("span", "sc-gpu-name", `${item.name} - ${item.kindWords} - ${item.verdict}`));
  line(li, item.summary);
  if (item.installed) line(li, item.sentence || "Already installed, and turned off.");
  for (const found of item.blocking.slice(0, 3)) line(li, `Refused: ${found.message}`);
  for (const found of item.warnings.slice(0, 3)) line(li, `Warning: ${found.message}`);
  if (item.canInstall) {
    const go = node(
      "button",
      "btn small",
      item.installed ? "Install it again…" : "Install it…",
    );
    go.type = "button";
    go.disabled = busy;
    go.addEventListener("click", () => installCreator(item));
    li.append(go);
  }
  return li;
}

function paintCreator() {
  if (!el.creator) return;
  el.creatorRefresh.disabled = busy;
  if (!creator) {
    el.creatorList.replaceChildren();
    el.creatorNote.hidden = true;
    return;
  }
  el.creatorFolder.textContent = creator.folder ? `Waiting folder: ${creator.folder}` : "";
  el.creatorFolder.hidden = !el.creatorFolder.textContent;
  if (!creator.available) {
    el.creatorList.replaceChildren();
    el.creatorNote.textContent = creator.why || CREATOR_MISSING;
    el.creatorNote.hidden = false;
    return;
  }
  el.creatorList.replaceChildren(...creator.items.map(creatorItemRow));
  const counts = creator.counts || {};
  const ready = Number.isFinite(Number(counts.ready)) ? Number(counts.ready) : 0;
  const note = creator.note || "";
  el.creatorNote.textContent = creator.items.length
    ? `${creator.items.length} item(s) waiting; ${ready} can be installed. ${note}`.trim()
    : "Nothing is waiting in the folder yet.";
  el.creatorNote.hidden = !el.creatorNote.textContent;
}

/**
 * Read the waiting folder and scan it. OWNER-TRIGGERED ONLY: this runs when
 * the card is first opened, when the page becomes visible again, and when
 * "Look again" is pressed - never on a timer, never on an event stream, and it
 * installs nothing.
 */
async function loadCreator() {
  if (!el.creator || !IS_TAURI) return;
  try {
    creator = creatorView(await ask("creator_read"));
  } catch (error) {
    creator = {
      available: false,
      why: problemWords(error),
      folder: "",
      items: [],
      counts: {},
      note: "",
    };
  }
  paintCreator();
}

async function installCreator(item) {
  if (!live()) {
    say(WAITING_LINK, "bad");
    return;
  }
  if (item.needsWarnings) {
    const go = globalThis.confirm
      ? globalThis.confirm(
          `This skill has warnings:\n\n${item.warnings.map((w) => w.message).join("\n")}\n\n` +
            "Read it before you say yes. Install it anyway?",
        )
      : true;
    if (!go) return;
  }
  const out = await working("Waiting for your answer on the PC…", () =>
    ask("creator_install", {
      name: item.name,
      acceptWarnings: item.needsWarnings,
    }),
  );
  if (!out) return;
  const words = answerWords(out);
  say(words || "Done.", out.ok === false ? "bad" : "ok");
  if (words) announce(words);
  await load();
  await loadCreator();
}

function clearPick() {
  pending = null;
  if (!el.pickTitle) return;
  el.pickTitle.textContent = "";
  el.pickDetail.textContent = "";
  el.pickInert.textContent = "";
  el.pickInert.hidden = true;
  el.pickFindings.replaceChildren();
  el.pickFindings.hidden = true;
  el.pickFindingsNone.hidden = true;
  el.pickGo.hidden = true;
  el.pickCancel.hidden = true;
}

function showPick(scanned, source) {
  pending = { scanned, source };
  el.pickTitle.textContent = scanned.name
    ? `${scanned.name} - ${scanned.verdict}`
    : "That is not a skill";
  el.pickDetail.textContent = scanned.reason || "";
  el.pickInert.textContent = scanned.inert || "";
  el.pickInert.hidden = !scanned.inert;
  const rows = [];
  for (const f of scanned.blocking) rows.push(node("li", "", `Refused: ${f.message}`));
  for (const f of scanned.warnings) rows.push(node("li", "", `Warning: ${f.message}`));
  el.pickFindings.replaceChildren(...rows);
  el.pickFindings.hidden = rows.length === 0;
  el.pickFindingsNone.hidden = rows.length !== 0;
  el.pickFindingsNone.textContent =
    rows.length === 0 ? "Nothing in it matches a known attack pattern." : "";
  el.pickCancel.hidden = false;
  if (scanned.ok && scanned.verdict !== "refuse") {
    el.pickGo.hidden = false;
    el.pickGo.textContent = scanned.needsWarnings ? "Install anyway…" : "Install it…";
    el.pickGo.disabled = busy;
    el.pickGo.dataset.warnings = scanned.needsWarnings ? "yes" : "no";
  } else {
    el.pickGo.hidden = true;
  }
}

async function load() {
  if (!el.section) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to see your skills.";
    el.state.hidden = false;
    return;
  }
  try {
    const raw = await ask("read");
    view = menuView(raw);
  } catch (error) {
    view = null;
    el.state.textContent = problemWords(error);
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  if (!view) {
    el.state.textContent = MISSING;
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  paint();
}

async function pickAndScan(which) {
  if (!live()) {
    say(WAITING_LINK, "bad");
    return;
  }
  clearPick();
  const chosen = await working(CHOOSING, () => ask(which));
  if (!chosen) return;
  if (chosen.cancelled) {
    say("");
    return;
  }
  const scanned = scanView(await working("Reading it, and scanning it…", () =>
    ask("scan", { path: chosen.path })));
  if (!scanned) return;
  showPick(scanned, { path: chosen.path });
  if (!scanned.ok) {
    say(scanned.reason || "That is not a skill.", "bad");
    announce(scanned.reason || "That is not a skill.");
    return;
  }
  say(`${scanned.name}: ${scanned.verdict}. Nothing is installed until you say yes.`);
}

async function installPicked() {
  if (!pending) return;
  const { scanned, source } = pending;
  const asked = scanned.needsWarnings;
  if (asked) {
    const go = globalThis.confirm
      ? globalThis.confirm(
          `This skill has warnings:\n\n${scanned.warnings.map((w) => w.message).join("\n")}\n\n` +
            "Read it before you say yes. Install it anyway?",
        )
      : true;
    if (!go) return;
  }
  const out = await working("Waiting for your answer on the PC…", () =>
    ask("install", { ...source, acceptWarnings: asked }));
  if (!out) return;
  const words = answerWords(out);
  say(words || "Done.", out.ok === false ? "bad" : "ok");
  if (words) announce(words);
  clearPick();
  await load();
}

async function turn(name, on) {
  if (!live()) {
    say(WAITING_LINK, "bad");
    return;
  }
  const verbs = on ? "Waiting for your answer on the PC…" : "Turning it off…";
  const out = await working(verbs, () => ask(on ? "enable" : "disable", { name }));
  if (!out) return;
  const words = answerWords(out);
  say(words || "Done.", out.ok === false ? "bad" : "ok");
  if (words) announce(words);
  await load();
}

/** Remove is the PC's own existing route, through the Brain's command. */
async function remove(name) {
  const sure = globalThis.confirm
    ? globalThis.confirm(`Remove the skill ${name}? Its folder is deleted from this PC.`)
    : true;
  if (!sure) return;
  const out = await working("Removing…", async () => {
    try {
      return await TAURI.core.invoke("brain_remove_skill", { name });
    } catch (error) {
      return { ok: false, reason: problemWords(error) };
    }
  });
  if (!out) return;
  const words = answerWords(out);
  say(words || "Done.", out.ok === false ? "bad" : "ok");
  if (words) announce(words);
  await load();
}

/** A TURNED-OFF skill only: the copy this menu parked in skills-off\. */
async function removeOff(name) {
  const sure = globalThis.confirm
    ? globalThis.confirm(
        `Remove the turned-off skill ${name}? Its folder is deleted from this PC, ` +
          "and there is no undo.",
      )
    : true;
  if (!sure) return;
  const out = await working("Removing…", () => ask("remove_off", { name }));
  if (!out) return;
  const words = answerWords(out);
  say(words || "Done.", out.ok === false ? "bad" : "ok");
  if (words) announce(words);
  await load();
}

async function openEditor(name) {
  const raw = await working("Opening it…", () => ask("read", { name }));
  if (!raw || typeof raw !== "object") return;
  editing = name;
  el.editTitle.textContent = `Editing ${name}`;
  el.editText.value = typeof raw.text === "string" ? raw.text : "";
  el.editInert.textContent = typeof raw.inert === "string" ? raw.inert : "";
  el.editInert.hidden = !el.editInert.textContent;
  el.editNote.textContent =
    "Saving asks you on this PC first, then the scanner reads the whole file again - " +
    "a skill that fails it is not saved.";
  el.editSave.disabled = busy;
  el.editText.disabled = busy;
  el.editCancel.disabled = busy;
  el.editTitle.scrollIntoView?.({ block: "nearest" });
  el.editText.focus();
}

function closeEditor() {
  editing = null;
  el.editText.value = "";
  el.editInert.textContent = "";
  el.editInert.hidden = true;
}

async function saveEditor() {
  if (!editing) return;
  if (!live()) {
    say(WAITING_LINK, "bad");
    return;
  }
  el.editSave.disabled = true;
  const out = await working("Waiting for your answer on the PC…", () =>
    ask("edit", { name: editing, text: el.editText.value }));
  el.editSave.disabled = false;
  if (!out) return;
  const words = answerWords(out);
  say(words || "Done.", out.ok === false ? "bad" : "ok");
  if (words) announce(words);
  if (out.ok === true) closeEditor();
  await load();
}

async function importScan() {
  if (!live()) {
    say(WAITING_LINK, "bad");
    return;
  }
  const scanned = importView(await working("Looking in your Hermes folder…", () =>
    ask("import_scan")));
  if (!scanned) return;
  if (!scanned.ok || !scanned.available) {
    el.importList.replaceChildren();
    say(scanned.why || "There is nothing to import.", "bad");
    return;
  }
  el.importList.replaceChildren(...scanned.folders.map(importRow));
  el.importNote.textContent = scanned.note || "";
  el.importNote.hidden = !scanned.note;
  say(
    scanned.folders.length
      ? `${scanned.folders.length} skill(s) found. Each one is installed with its own card; nothing is imported by this list.`
      : "There are no skills in your Hermes folder.",
  );
}

function importRow(found) {
  const li = node("li", "sc-gpu");
  li.dataset.skill = found.folder;
  li.append(node("span", "sc-gpu-name", `${found.name} - ${found.verdict}`));
  line(li, found.summary);
  line(li, found.inert);
  if (found.installed) line(li, "Already installed on this PC.");
  const go = node("button", "btn small", "Import…");
  go.type = "button";
  go.disabled = busy || !found.canImport;
  go.title = found.canImport ? "" : "The scanner refused this one, so it cannot be installed.";
  go.addEventListener("click", () => importOne(found));
  li.append(go);
  return li;
}

async function importOne(found) {
  if (found.needsWarnings) {
    const go = globalThis.confirm
      ? globalThis.confirm(
          `This skill has warnings:\n\n${found.summary}\n\nRead it before you say yes. ` +
            "Import it anyway?",
        )
      : true;
    if (!go) return;
  }
  const out = await working("Waiting for your answer on the PC…", () =>
    ask("install", { hermes: found.folder, acceptWarnings: found.needsWarnings }));
  if (!out) return;
  const words = answerWords(out);
  say(words || "Done.", out.ok === false ? "bad" : "ok");
  if (words) announce(words);
  await load();
}

if (el.section) {
  el.installFolder?.addEventListener("click", () => pickAndScan("pick_folder"));
  el.installZip?.addEventListener("click", () => pickAndScan("pick_zip"));
  el.hermes?.addEventListener("click", importScan);
  el.pickGo?.addEventListener("click", installPicked);
  el.pickCancel?.addEventListener("click", () => {
    clearPick();
    say("");
  });
  el.editSave?.addEventListener("click", saveEditor);
  el.editCancel?.addEventListener("click", () => {
    closeEditor();
    say("");
  });
  el.creatorRefresh?.addEventListener("click", loadCreator);
  clearPick();
  closeEditor();
}
onLink(() => paint());
// A card answered (or expired): the list may have changed. onQueue also
// delivers the current queue at once - the first read.
onQueue(() => load());
// Creator mode is a scan of a folder, so it is read when the card is opened
// and when the page comes back into view - never on a timer and never on every
// event, which would turn "look at what is waiting" into a watcher.
if (el.creator) loadCreator();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    load();
    if (el.creator) loadCreator();
  }
});
