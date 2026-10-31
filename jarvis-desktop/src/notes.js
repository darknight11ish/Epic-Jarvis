/**
 * The notes editor's plate in the Brain window - the whole Obsidian vault,
 * both apps (contract 2026-10-31: `.dsh-scratch/NOTES-EDITOR-2026-10-31/CONTRACT.md`).
 *
 * The owner chose "the whole vault, both apps": every `.md` and `.txt` note
 * can be found, opened and edited, on this PC and on the phone. This plate is
 * the desktop half. The four routes it reads are the PC's own:
 *
 *   GET  /api/notes/list        every note (path, title, size, mtime), newest
 *                               first, with an optional `?q=` search
 *   GET  /api/notes/read        one note's words and SHA-256
 *   POST /api/notes/save        asks to overwrite; the PC raises ONE ordinary
 *                               approval card (`edit_vault_note`, tier `ask`)
 *   GET  /api/notes/save?id=    how that save ended
 *
 * **Every save is a card.** This program never approves anything: Save sends
 * the owner's words with the hash the note had when it was opened, the PC
 * raises the same card every other risky action raises, and the file is not
 * written until that card is answered. `waiting`, `saved`, `denied` and
 * `conflict` below are the four things the plate can say afterwards, and every
 * sentence shown in those states comes from the PC's own answer.
 *
 * **Two editors can never clobber each other.** The save carries the hash it
 * started from; if the note changed on disk since it was opened, the PC
 * refuses with `conflict` and the current hash, and nothing is written. The
 * plate keeps the owner's unsaved words in the box and says so.
 *
 * @module notes
 */

import { APPROVE_WHERE } from "./jarvis-link.js";

/** How often to ask how a save is going, and for how long before giving up. */
export const POLL_MS = 3000;
/** The card's own life is on the PC; this is only the display's patience. */
export const GIVE_UP_MS = 30 * 60 * 1000;
/** Failed polls in a row before the follow stops. One blip is not the end. */
export const MAX_FAILED_POLLS = 3;

/** `GET /api/notes/list`'s answer, read. Never any note text. */
export function readNotesList(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const notes = Array.isArray(a.notes) ? a.notes : [];
  return {
    root: typeof a.root === "string" ? a.root : "",
    count: Number.isFinite(a.count) ? a.count : notes.length,
    truncated: a.truncated === true,
    notes: notes
      .filter((n) => n && typeof n.path === "string")
      .map((n) => ({
        path: n.path,
        title: typeof n.title === "string" && n.title ? n.title : n.path.split("/").pop(),
        size: Number.isFinite(n.size) ? n.size : 0,
        mtime: Number.isFinite(n.mtime) ? n.mtime : 0,
      })),
  };
}

/** `GET /api/notes/read`'s answer, read. `sha256` is the save's check. */
export function readNote(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  return {
    path: typeof a.path === "string" ? a.path : "",
    text: typeof a.text === "string" ? a.text : "",
    sha256: typeof a.sha256 === "string" ? a.sha256 : "",
    size: Number.isFinite(a.size) ? a.size : 0,
    mtime: Number.isFinite(a.mtime) ? a.mtime : 0,
  };
}

/**
 * Words for one save answer, as `{ text, tone, final, state }`.
 *
 * The four states are the contract's: `waiting` (the card is up - not a
 * finish), `saved` (the only state that reads as written), `denied` (said no
 * or expired - nothing written) and `failed`. `conflict` is answered by `POST
 * /api/notes/save` itself, before any card; it is final, nothing was written,
 * and the owner's words stay in the box.
 */
export function describeSave(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const state = typeof a.state === "string" ? a.state : "";
  const said = (typeof a.message === "string" && a.message.trim()) || "";
  const error = (typeof a.error === "string" && a.error.trim()) || "";
  switch (state) {
    case "waiting":
      return {
        text: said || `Waiting for your approval. Approve it ${APPROVE_WHERE} - nothing is written until you do.`,
        tone: null,
        final: false,
        state,
      };
    case "saved":
      return { text: said || `Saved ${a.path || "the note"}.`, tone: "ok", final: true, state };
    case "denied":
      return { text: said || "You said no, so nothing was written.", tone: "bad", final: true, state };
    case "failed":
      return { text: said || error || "The save could not be written; the note is unchanged.",
        tone: "bad", final: true, state };
    case "conflict": {
      const now = typeof a.current_sha256 === "string" ? a.current_sha256.slice(0, 12) : "";
      return {
        text: said || `The note changed since you opened it${now ? ` (now ${now}…)` : ""} - `
          + "nothing was overwritten. Open it again and save your words on top of the new copy.",
        tone: "bad",
        final: true,
        state,
      };
    }
    default:
      return { text: "The PC answered, but did not say how the save went. Open the note again to see what is there.",
        tone: "bad", final: true, state };
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Save one note, then follow the card's job until it ends, calling `onSay`
 * with each `describeSave` answer. Resolves to the last one (with its
 * `state`).
 *
 * A transport failure while asking resolves to that sentence - nothing is
 * claimed to be written. After the ask, `waiting` with an id is followed with
 * `GET /api/notes/save?id=`; the follow survives a bad moment exactly like
 * the wiki's: up to `MAX_FAILED_POLLS - 1` failed polls in a row are said and
 * retried, and while `linkDown()` says the PC is unreachable no poll is sent
 * at all (the job carries on there).
 */
export async function saveNote(invoke, { path, text, expectedSha256 }, onSay,
                               { pollMs = POLL_MS, giveUpMs = GIVE_UP_MS,
                                 maxFailedPolls = MAX_FAILED_POLLS,
                                 linkDown = () => false } = {}) {
  let said;
  let job;
  try {
    job = await invoke("notes_save", { path, text, expectedSha256 });
  } catch (error) {
    said = { text: String((error && error.message) || error), tone: "bad", final: true, state: "" };
    onSay(said);
    return said;
  }
  said = describeSave(job);
  onSay(said);
  const id = job && job.id;
  const started = Date.now();
  let failed = 0;
  let skipping = false;
  while (!said.final && id) {
    await sleep(pollMs);
    if (Date.now() - started > giveUpMs) {
      said = { text: "Still waiting for the card on the PC. Nothing is written until you answer it.",
        tone: null, final: true, state: "waiting" };
      onSay(said);
      break;
    }
    let down = false;
    try { down = Boolean(linkDown()); } catch { down = false; }
    if (down) {
      if (!skipping) {
        skipping = true;
        onSay({ text: "Waiting for the link to the PC to come back. The card and the save carry on there.",
          tone: null, final: false, state: "waiting" });
      }
      continue;
    }
    skipping = false;
    try {
      said = describeSave(await invoke("notes_save_status", { id }));
      failed = 0;
    } catch (error) {
      failed += 1;
      const why = String((error && error.message) || error);
      said = failed >= maxFailedPolls
        ? { text: `Lost track of the save (${why}). Check the card, then open the note to see what is on disk.`,
          tone: "bad", final: true, state: "" }
        : { text: `Could not ask the PC how the save is going (${why}). Trying again.`,
          tone: null, final: false, state: "waiting" };
    }
    onSay(said);
  }
  return said;
}

/** A note's size in words: "812 B", "4.1 kB". */
function sizeWords(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  return `${(v / 1024).toFixed(1)} kB`;
}

/**
 * Paints the plate into `container`.
 *
 * `plate` is `{ view, listError, open, openError, said, saving }`: the last
 * list read (from `readNotesList`), why it failed, the note open in the
 * editor (from `readNote`), why it failed, the last save answer and whether
 * one is in flight. `ui` is the Brain's own `el`, `row` and `button` helpers,
 * so Save is greyed on a stale link exactly like every other Brain button
 * (rule 4). `plate.onOpen(path)`, `plate.onSave()`, `plate.onReload()` and
 * `plate.onClose()` are the actions; the words in the editor belong to the
 * page, so Save reads them there.
 */
export function renderNotes(container, plate, ui) {
  const { el, row, button } = ui;
  container.replaceChildren();
  if (!plate.view) {
    container.append(el("p", "empty", plate.listError
      ? `Could not read your notes: ${plate.listError}`
      : "Reading…"));
    return;
  }
  const v = plate.view;
  if (v.root) {
    const where = el("p", "notes-root", `Vault: ${v.root}`);
    where.title = "The Obsidian vault folder on this PC. Only .md and .txt notes inside it are listed.";
    container.append(where);
  }
  if (plate.listError) {
    container.append(el("p", "empty notes-failed", `Could not read the list again: ${plate.listError}`));
  }

  const said = plate.said;
  if (said && said.text) {
    const line = el("p", "notes-job", said.text);
    if (said.tone) line.dataset.tone = said.tone;
    if (said.state) line.dataset.state = said.state;
    line.setAttribute("role", "status");
    container.append(line);
  }

  const open = plate.open;
  if (open) {
    const box = el("div", "notes-editor");
    const head = el("div", "notes-head");
    head.append(el("span", "notes-path", open.path));
    if (open.sha256) {
      const meta = el("span", "notes-meta",
        `${sizeWords(open.size)} · ${open.sha256.slice(0, 12)}…`);
      meta.title = "The note's SHA-256 when it was opened. A save is refused if the note has changed since.";
      head.append(meta);
    }
    box.append(head);
    if (plate.openError) {
      box.append(el("p", "empty notes-failed", `Could not open it: ${plate.openError}`));
    }
    const text = el("textarea", "field notes-text");
    text.id = "notes-text";
    text.rows = 18;
    text.spellcheck = true;
    text.value = open.text;
    text.setAttribute("aria-label", `The words of ${open.path}`);
    box.append(text);
    const actions = el("div", "row-actions notes-actions");
    const save = button("Save", () => plate.onSave(), {
      live: true,
      title: "Sends your words to the PC, which raises ONE approval card; nothing is written until you "
        + "approve it there. The note is not saved from here.",
    });
    // A save already waiting for its card cannot be sent twice.
    if (plate.saving || (said && said.final === false)) save.disabled = true;
    actions.append(save);
    actions.append(button("Open it again", () => plate.onReload(), {
      title: "Reads the note from disk again, throwing away your unsaved words in the box.",
    }));
    actions.append(button("Close", () => plate.onClose(), { title: "Puts the list back." }));
    box.append(actions);
    container.append(box);
    return;
  }

  const list = el("div", "rows");
  for (const note of v.notes) {
    list.append(row({
      tag: "note",
      state: "",
      title: note.title || note.path,
      meta: [note.path, sizeWords(note.size)],
      actions: [button("Open", () => plate.onOpen(note.path), {
        title: "Reads this note from the PC; opening it never writes anything.",
      })],
    }));
  }
  if (!v.notes.length) {
    list.append(el("p", "empty notes-empty", v.truncated
      ? "No note matches that search."
      : "No notes found. The notes editor reads .md and .txt files inside your Obsidian vault."));
  }
  container.append(list);
  if (v.truncated) {
    container.append(el("p", "note notes-truncated",
      "The list stops at 2,000 notes. Search to narrow it down."));
  }
}
