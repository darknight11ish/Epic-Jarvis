/**
 * Settings -> "Protected from Jarvis" (the owner's request of 2026-10-31;
 * contract `.dsh-scratch/PROTECTED-ITEMS-2026-10-31/CONTRACT.md`).
 *
 * Five Rust commands, Settings only (src-tauri/src/protected.rs):
 *  - get_protection: the list in the PC's words. A read.
 *  - protection_pick {kind}: the Windows folder or file picker. Only the
 *    chosen path comes back - this page never gets a file system of its own.
 *  - protection_programs: the executable names of the programs running now,
 *    so "Add a program…" offers a real list.
 *  - add_protection {kind,target,mode}: the owner's own direct act, immediate
 *    (tightening) and never a card. The PC still refuses a relative or
 *    missing path, an unknown program or a duplicate, in its own sentence.
 *  - remove_protection {id}: removing is loosening, so the PC raises ONE
 *    approval card; a 202 says the card is up. Held on a stale link here
 *    (greyed) and in Rust.
 *
 * The mode is a second, explicit choice after the target: Blocked (the
 * recommended one) or Read-only. Nothing is sent until Add is pressed.
 *
 * @module protected-settings
 */

import { announce, currentLink, linkWords, onLink, onQueue } from "./jarvis-link.js";
import {
  actions,
  ADD_FILE,
  ADD_FOLDER,
  ADD_PROGRAM,
  describeAdd,
  MISSING,
  modeHint,
  readPick,
  readPrograms,
  readProtection,
  REMOVE,
  STALE,
  WAITING_REMOVE,
} from "./protected.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

const el = {
  section: $("protection"),
  detail: $("pr-detail"),
  state: $("pr-state"),
  body: $("pr-body"),
  change: $("pr-change"),
  list: $("pr-list"),
  empty: $("pr-empty"),
  addFolder: $("pr-add-folder"),
  addFile: $("pr-add-file"),
  addProgram: $("pr-add-program"),
  choice: $("pr-choice"),
  choiceTitle: $("pr-choice-title"),
  choiceTarget: $("pr-choice-target"),
  programs: $("pr-programs"),
  modes: $("pr-modes"),
  modeBlocked: $("pr-mode-blocked"),
  modeReadonly: $("pr-mode-readonly"),
  modeHint: $("pr-mode-hint"),
  confirm: $("pr-add-confirm"),
  cancel: $("pr-choice-cancel"),
  status: $("pr-status"),
};

let view = null;
/** The target the owner has chosen and not yet added: `{kind, target}`. */
let choice = null;
/** The running programs, while "Add a program…" is choosing one. */
let programs = null;
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

function say(words, tone) {
  if (!el.status) return;
  el.status.textContent = words || "";
  if (tone) el.status.dataset.tone = tone;
  else delete el.status.dataset.tone;
}

/** The selected mode's value, Blocked when nothing is checked. */
function chosenMode() {
  const picked = document.querySelector('input[name="pr-mode"]:checked');
  return picked && picked.value === "readonly" ? "readonly" : "blocked";
}

function paintChoice() {
  if (!el.choice) return;
  const open = Boolean(choice || programs);
  el.choice.hidden = !open;
  if (!open) return;
  if (programs) {
    el.choiceTitle.textContent = ADD_PROGRAM;
    el.choiceTarget.textContent =
      "Programs running on this PC right now. Pick the one Jarvis must leave alone.";
    el.programs.hidden = false;
    el.programs.replaceChildren(...programs.map((name) => {
      const b = node("button", "btn small pr-program", name);
      b.type = "button";
      b.addEventListener("click", () => {
        choice = { kind: "program", target: name };
        programs = null;
        paint();
      });
      return b;
    }));
    el.modes.hidden = true;
    el.confirm.hidden = true;
    return;
  }
  el.programs.hidden = true;
  el.programs.replaceChildren();
  el.choiceTitle.textContent = `Add a ${(choice.kind || "").toLowerCase()}`;
  el.choiceTarget.textContent = choice.target;
  el.modes.hidden = false;
  el.confirm.hidden = false;
  el.modeHint.textContent = modeHint(chosenMode(), choice.kind);
}

function paint() {
  if (!el.section) return;
  if (!IS_TAURI) {
    el.state.textContent = "Open this in Jarvis Desktop to change what is protected.";
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  if (!view) return;
  if (!view.available) {
    el.state.textContent = view.why || MISSING;
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  el.state.hidden = true;
  el.body.hidden = false;
  el.change.textContent = view.changeCard;
  const can = actions(view, live());
  el.detail.textContent = "";
  // textContent everywhere: the target is the owner's, never markup.
  el.list.replaceChildren(...view.items.map((entry) => {
    const li = node("li", "sc-gpu");
    li.dataset.kind = entry.kind;
    li.append(node("span", "sc-gpu-name", entry.target));
    li.append(node("span", "sc-gpu-role",
      `${entry.kindWords} · ${entry.modeWords}`));
    if (entry.modeHint) li.append(node("span", "sc-gpu-role pr-hint", entry.modeHint));
    const rm = node("button", "btn small", REMOVE);
    rm.type = "button";
    rm.disabled = busy || !can.remove;
    if (!can.remove && can.removeWhy) rm.title = can.removeWhy;
    rm.addEventListener("click", () => remove(entry));
    li.append(rm);
    return li;
  }));
  el.empty.hidden = view.items.length > 0;
  el.empty.textContent = "Nothing is protected yet. Everything is available to Jarvis.";
  for (const b of [el.addFolder, el.addFile, el.addProgram]) {
    if (b) b.disabled = busy || !can.add;
  }
  el.addFolder.textContent = ADD_FOLDER;
  el.addFile.textContent = ADD_FILE;
  el.addProgram.textContent = ADD_PROGRAM;
  paintChoice();
}

async function load() {
  if (!el.section) return;
  if (!IS_TAURI) {
    paint();
    return;
  }
  try {
    view = readProtection(await TAURI.core.invoke("get_protection"));
  } catch (error) {
    el.state.textContent = problemWords(error);
    el.state.hidden = false;
    el.body.hidden = true;
    return;
  }
  paint();
}

async function startPick(kind) {
  if (busy) return;
  busy = true;
  say("Choosing…");
  paint();
  try {
    const out = await TAURI.core.invoke("protection_pick", { kind });
    const path = readPick(out);
    if (path) {
      choice = { kind, target: path };
      programs = null;
      say("");
    } else {
      say("");
    }
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    busy = false;
  }
  paint();
}

async function loadPrograms() {
  if (busy) return;
  busy = true;
  say("Reading the programs running now…");
  paint();
  try {
    const got = readPrograms(await TAURI.core.invoke("protection_programs"));
    programs = got.programs;
    choice = null;
    if (!programs.length) {
      programs = null;
      say("No programs are running that Jarvis can name. Open one, then try again.", "bad");
    } else {
      say("");
    }
  } catch (error) {
    say(problemWords(error), "bad");
    programs = null;
  } finally {
    busy = false;
  }
  paint();
}

async function confirmAdd() {
  if (!choice || busy) return;
  const mode = chosenMode();
  const target = choice.target;
  const kind = choice.kind;
  busy = true;
  say("Adding…");
  paint();
  try {
    const out = describeAdd(await TAURI.core.invoke("add_protection", { kind, target, mode }));
    say(out.text, out.tone);
    announce(out.text, out.tone === "bad" ? "assertive" : "polite");
    choice = null;
    programs = null;
  } catch (error) {
    say(problemWords(error), "bad");
    choice = null;
    programs = null;
  } finally {
    busy = false;
  }
  await load();
}

async function remove(entry) {
  if (!live()) {
    say(STALE, "bad");
    return;
  }
  if (busy) return;
  busy = true;
  say("Asking the PC to remove it…");
  paint();
  try {
    const out = await TAURI.core.invoke("remove_protection", { id: entry.id });
    if (out && out.state === "waiting") {
      say(WAITING_REMOVE);
      announce(WAITING_REMOVE);
    } else {
      const words = String((out && (out.message || out.said || out.error)) || "Done.");
      say(words, out && out.ok === false ? "bad" : "ok");
    }
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    busy = false;
  }
  await load();
}

if (el.section) {
  if (el.addFolder) el.addFolder.addEventListener("click", () => startPick("folder"));
  if (el.addFile) el.addFile.addEventListener("click", () => startPick("file"));
  if (el.addProgram) el.addProgram.addEventListener("click", loadPrograms);
  if (el.confirm) el.confirm.addEventListener("click", confirmAdd);
  if (el.cancel) {
    el.cancel.addEventListener("click", () => {
      choice = null;
      programs = null;
      say("");
      paint();
    });
  }
  if (el.modes) {
    el.modes.addEventListener("change", () => {
      if (choice) el.modeHint.textContent = modeHint(chosenMode(), choice.kind);
    });
  }
  if (el.detail) el.detail.textContent = "";
  el.change.textContent = "";
  el.status.textContent = "";
}
onLink(() => paint());
// A card answered (or expired): the list may have changed - a removal may
// just have gone through. onQueue also delivers the current queue at once.
onQueue(() => load());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) load();
});
