/**
 * guardian-panel.js - Brain -> Projects -> "File history" (Pillar 18's file
 * guardian; JARVIS-API section 140; LM-2C).
 *
 * WHAT THE OWNER SEES
 * The copies Jarvis took of a file before changing it - newest first, with the
 * file's name, when, why and its size. "Show the difference" draws the module's
 * own bounded diff; "Put this version back" asks "are you sure?", then asks the
 * PC, which raises the EXISTING undo_action card in the Jarvis bar. This page
 * never approves anything: the card decides, and the PC's own sentence is shown.
 *
 * WHERE IT LIVES, AND WHY
 * Inside the Projects view, beside the Progress pictures and the Pictures
 * gallery (projects-panel.js calls setGuardianVisible/refreshGuardian the same
 * way it calls the other two). The guardian keeps copies of project files and
 * notes, so Projects is the surface those files already live on; no new rail
 * tab and no new window.
 *
 * THE HIDING RULE
 * A snapshot's path and reason are the owner's own work, so the whole drawer
 * hides while App lock is locked OR "Hide memory lists and chat history" is on.
 * That decision is made in RUST (brain/guardian.rs `words_hidden`), before this
 * file sees the answer: a hidden answer carries ONE sentence and no rows, no
 * count and no path. This file draws that sentence and asks for nothing else -
 * and the drawer is cleared at once when it is told to hide.
 *
 * WHY THE WORDS ARE THE PC'S
 * "Put back the version from <when>", "The card was turned down...", "That
 * earlier version is not in the time machine any more" - every sentence about
 * an outcome comes from the PC. This file only draws it.
 * @module guardian-panel
 */

import { currentLink, linkWords, onLink } from "./jarvis-link.js";
import {
  WORDS,
  diffModel,
  restoreModel,
  restoreRequest,
  sizeWords,
  snapshotModel,
} from "./guardian.js";

const TAURI = globalThis.__TAURI__;

async function invoke(command, args = {}) {
  const core = TAURI && TAURI.core;
  if (!core || !core.invoke) return null;
  return core.invoke(command, args);
}

function errorText(error) {
  return String((error && error.message) || error || "Something went wrong.");
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function button(label, onClick, { title = "" } = {}) {
  const b = el("button", "btn small", label);
  b.type = "button";
  if (title) b.title = title;
  b.addEventListener("click", onClick);
  return b;
}

const state = {
  /** snapshotModel() answer, or null before the first read. */
  model: null,
  error: "",
  said: "",
  visible: true,
  reading: false,
  again: false,
  /** The row whose difference is open, and its diffModel() answer. */
  open: null,
  diff: null,
  busy: false,
};

function canAct() {
  const link = currentLink();
  return Boolean(link) && !link.stale;
}

function say(words) {
  state.said = String(words || "");
  paint();
}

function hiddenBlock(words) {
  const wrap = el("div", "private-hidden guardian-hidden");
  wrap.append(el("p", "empty", words || WORDS.hidden_short));
  return wrap;
}

/** Draws the drawer from the pure model. Every word is textContent. */
function paint() {
  const box = document.getElementById("guardian-root");
  if (!box) return;
  if (!state.visible) {
    box.replaceChildren();
    return;
  }
  const card = el("section", "card guardian-card");
  card.id = "guardian-card";
  card.append(el("h2", "guardian-title", WORDS.title));
  card.append(el("p", "note guardian-under", WORDS.under));

  if (state.error) {
    card.append(el("p", "empty", state.error));
    box.replaceChildren(card);
    return;
  }
  const model = state.model;
  if (!model) {
    card.append(el("p", "note", "Asking Jarvis…"));
    box.replaceChildren(card);
    return;
  }
  if (model.missing) {
    card.append(el("p", "empty", WORDS.missing));
    box.replaceChildren(card);
    return;
  }
  if (model.hidden) {
    card.append(hiddenBlock(model.hiddenWords));
    box.replaceChildren(card);
    return;
  }

  if (!model.rows.length) {
    card.append(el("p", "empty", model.words || WORDS.empty));
  } else {
    const list = el("ul", "guardian-list");
    for (const row of model.rows) {
      list.append(rowBlock(row));
    }
    card.append(list);
  }

  if (state.open) card.append(diffBlock());
  const said = el("p", "guardian-said", state.said);
  said.id = "guardian-said";
  said.setAttribute("role", "status");
  card.append(said);
  box.replaceChildren(card);
}

function rowBlock(row) {
  const li = el("li", "guardian-row");
  li.dataset.sha = row.sha256;
  const body = el("div", "guardian-row-body");
  body.append(el("strong", "guardian-label", row.label));
  const meta = [row.when, sizeWords(row.size)].filter(Boolean).join(" · ");
  if (meta) body.append(el("span", "guardian-meta", meta));
  if (row.reason) body.append(el("span", "guardian-reason", row.reason));
  li.append(body);
  const actions = el("div", "guardian-actions");
  actions.append(button(WORDS.show_diff, () => showDiff(row),
                        { title: "Show the bounded difference this copy makes" }));
  const put = button(WORDS.restore, () => restore(row),
                     { title: canAct() ? WORDS.restore_ask : linkWords() });
  put.classList.add("guardian-restore");
  if (!canAct() || state.busy) {
    put.disabled = true;
    put.title = !canAct() ? WORDS.stale : "";
  }
  actions.append(put);
  li.append(actions);
  return li;
}

function diffBlock() {
  const row = state.open;
  const wrap = el("section", "guardian-diff-card");
  wrap.id = "guardian-diff";
  wrap.append(el("h3", "guardian-diff-title", row.label));
  if (state.busy && !state.diff) {
    wrap.append(el("p", "note", "Reading the difference…"));
    return wrap;
  }
  const diff = state.diff;
  if (diff && diff.text) {
    const pre = el("pre", "guardian-diff-text");
    pre.id = "guardian-diff-text";
    pre.textContent = diff.text;
    wrap.append(pre);
  }
  if (diff && diff.words) {
    wrap.append(el("p", "guardian-diff-words", diff.words));
  }
  if (diff && diff.truncated) {
    const cut = el("p", "guardian-diff-cut", WORDS.diff_cut);
    cut.id = "guardian-diff-cut";
    wrap.append(cut);
  }
  wrap.append(button(WORDS.close_diff, () => {
    state.open = null;
    state.diff = null;
    paint();
  }));
  return wrap;
}

/** Shows the module's own bounded diff for one row. A read: not held. */
async function showDiff(row) {
  state.open = row;
  state.diff = null;
  state.busy = true;
  paint();
  try {
    const out = await invoke("guardian_diff", { path: row.path, shaBefore: row.sha256 });
    state.diff = diffModel(out);
  } catch (error) {
    state.diff = { ok: false, text: "", truncated: false, hidden: false,
                   words: errorText(error) };
  } finally {
    state.busy = false;
  }
  paint();
}

/**
 * "Put this version back": one question here, then the PC's own card. A
 * refusal changes nothing, so nothing is re-read and nothing is re-sent.
 */
async function restore(row) {
  if (!canAct() || state.busy) return;
  if (!window.confirm(WORDS.restore_ask)) return;
  state.busy = true;
  paint();
  try {
    const out = await invoke("guardian_restore", restoreRequest(row));
    const done = restoreModel(out);
    state.said = done.words;
    if (done.refresh) {
      // The PC says the file changed: read the list again so the new copy (the
      // restore leaves one) and the new order are what the owner sees next.
      state.model = null;
      state.busy = false;
      await refreshGuardian();
      state.said = done.words;
    }
  } catch (error) {
    state.said = errorText(error);
  } finally {
    state.busy = false;
  }
  paint();
}

/** Reads the guardian's page again and draws it. One line for any error. */
export async function refreshGuardian() {
  if (!state.visible) return;
  if (state.reading) {
    state.again = true;
    return;
  }
  state.reading = true;
  try {
    const out = await invoke("brain_read", { sections: ["guardian_history"] });
    const part = out && typeof out === "object" ? out.guardian_history : null;
    state.model = snapshotModel(part);
    state.error = "";
  } catch (error) {
    state.error = errorText(error);
    state.model = null;
  } finally {
    state.reading = false;
  }
  paint();
  if (state.again) {
    state.again = false;
    await refreshGuardian();
  }
}

/** The Projects view calls this: the drawer sits above the project list. */
export function setGuardianVisible(on) {
  state.visible = !!on;
  if (!state.visible) {
    state.open = null;
    state.diff = null;
    const box = document.getElementById("guardian-root");
    if (box) box.replaceChildren();
  }
}

/** Nothing is read until the drawer is on screen; a lock change hides it. */
onLink(() => {
  if (state.visible && state.model) paint();
});

if (TAURI && TAURI.event) {
  TAURI.event.listen("security-changed", () => {
    if (!state.visible) return;
    // App lock or the hidden lists may have just turned on: forget the open
    // difference and ask Rust again, which answers with the one hidden line.
    state.open = null;
    state.diff = null;
    refreshGuardian();
  });
}
