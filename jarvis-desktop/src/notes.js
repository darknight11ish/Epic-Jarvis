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

/* ==========================================================================
   Rename and move ONE note (wave 4, 2026-10-31)

   Two small chrome controls in the editor. Each asks the PC's own existing
   route - `POST /api/notes/rename` / `POST /api/notes/move` - with exactly the
   body the chat uses; the PC raises its ONE ordinary approval card, and the
   editor follows the job with `GET /api/notes/change?id=`. This page approves
   nothing, saves nothing itself and has no second write path: a rename or a
   move happens only after the card is answered on the PC, and the module's own
   sentence says what happened (including "You can undo it.").
   ========================================================================== */

/** A note's title from its path: the filename without its extension. */
export function titleOf(path) {
  const name = String(path || "").split("/").pop() || "";
  return name.replace(/\.(md|txt)$/i, "");
}

/** The exact body `POST /api/notes/rename` takes (no extra fields). */
export function renameBody({ path, title } = {}) {
  return { path: String(path || ""), title: String(title || "").trim() };
}

/** The exact body `POST /api/notes/move` takes; `create_folder` is a real boolean. */
export function moveBody({ path, folder, createFolder } = {}) {
  return {
    path: String(path || ""),
    folder: String(folder || "").trim(),
    create_folder: createFolder === true,
  };
}

/** Every folder the note list proves exists, plus the vault's top level (""). */
export function folderChoices(notes = []) {
  const found = new Set([""]);
  for (const note of Array.isArray(notes) ? notes : []) {
    const parts = String((note && note.path) || "").split("/");
    parts.pop();
    let sofar = "";
    for (const part of parts) {
      if (!part) continue;
      sofar = sofar ? `${sofar}/${part}` : part;
      found.add(sofar);
    }
  }
  return [...found].sort((a, b) => (a === "" ? -1 : b === "" ? 1 : a.localeCompare(b)));
}

/**
 * Words for one rename/move answer, as `{ text, tone, final, state, target }`.
 * The four states are the module's: `waiting` (the card is up - not a finish),
 * `saved` (the only state that reads as changed; the sentence is the module's,
 * including "You can undo it."), `denied` (said no or expired - nothing
 * changed) and `failed` (nothing changed; its own words). Never composed
 * beyond the default when the PC sent none.
 */
export function describeChange(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const state = typeof a.state === "string" ? a.state : "";
  const said = (typeof a.message === "string" && a.message.trim()) || "";
  const error = (typeof a.error === "string" && a.error.trim()) || "";
  const target = typeof a.target === "string" ? a.target : "";
  switch (state) {
    case "waiting":
      return {
        text: said || "Waiting for your approval on the PC - nothing is renamed or moved, and no link changes, until you answer its ONE card.",
        tone: null, final: false, state, target,
      };
    case "saved":
      return { text: said || "Done. You can undo it.", tone: "ok", final: true, state, target };
    case "denied":
      return {
        text: said || "You said no, so the note was not renamed or moved and no link was changed.",
        tone: "bad", final: true, state, target,
      };
    case "failed":
      return {
        text: said || error || "The change could not be written, so every note is as it was.",
        tone: "bad", final: true, state, target,
      };
    default:
      return {
        text: "The PC answered, but did not say how the change went. Open the note again to see what is on disk.",
        tone: "bad", final: true, state, target,
      };
  }
}

/**
 * Asks for one rename or move, then follows the card's job until it ends,
 * calling `onSay` with each `describeChange` answer. Resolves to the last one.
 * Uses only the notes editor's own commands; it never calls a save route, a
 * pending/approval route, or anything that decides a card.
 */
export async function changeNote(invoke, { kind, path, title, folder, createFolder }, onSay,
                                  { pollMs = POLL_MS, giveUpMs = GIVE_UP_MS,
                                    maxFailedPolls = MAX_FAILED_POLLS,
                                    linkDown = () => false } = {}) {
  let said;
  let job;
  try {
    job = kind === "rename"
      ? await invoke("notes_rename", renameBody({ path, title }))
      : await invoke("notes_move", moveBody({ path, folder, createFolder }));
  } catch (error) {
    said = { text: String((error && error.message) || error), tone: "bad", final: true, state: "", target: "" };
    onSay(said);
    return said;
  }
  said = describeChange(job);
  onSay(said);
  const id = job && job.id;
  const started = Date.now();
  let failed = 0;
  let skipping = false;
  while (!said.final && id) {
    await sleep(pollMs);
    if (Date.now() - started > giveUpMs) {
      said = { text: "Still waiting for the card on the PC. Nothing is changed until you answer it.",
        tone: null, final: true, state: "waiting", target: said.target };
      onSay(said);
      break;
    }
    let down = false;
    try { down = Boolean(linkDown()); } catch { down = false; }
    if (down) {
      if (!skipping) {
        skipping = true;
        onSay({ text: "Waiting for the link to the PC to come back. The card carries on there.",
          tone: null, final: false, state: "waiting", target: said.target });
      }
      continue;
    }
    skipping = false;
    try {
      said = describeChange(await invoke("notes_change_status", { id }));
      failed = 0;
    } catch (error) {
      failed += 1;
      const why = String((error && error.message) || error);
      said = failed >= maxFailedPolls
        ? { text: `Lost track of the change (${why}). Check the card, then open the note to see what is on disk.`,
          tone: "bad", final: true, state: "", target: said.target }
        : { text: `Could not ask the PC how the change is going (${why}). Trying again.`,
          tone: null, final: false, state: "waiting", target: said.target };
    }
    onSay(said);
  }
  return said;
}

/** Rename one note through the PC's ONE card. */
export function renameNote(invoke, { path, title }, onSay, options = {}) {
  return changeNote(invoke, { kind: "rename", path, title }, onSay, options);
}

/** Move one note through the PC's ONE card; `createFolder` is explicit. */
export function moveNote(invoke, { path, folder, createFolder }, onSay, options = {}) {
  return changeNote(invoke, { kind: "move", path, folder, createFolder }, onSay, options);
}

/** A note's size in words: "812 B", "4.1 kB". */
function sizeWords(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  return `${(v / 1024).toFixed(1)} kB`;
}

/* ==========================================================================
   Formatting toolbar, shortcuts and templates (owner request, 2026-10-31)

   Everything here edits the textarea's VALUE, in the page, and calls the
   plate's optional `onDraft` so a repaint keeps the owner's words. Nothing
   here saves, writes, calls the PC, creates a note or overwrites one: Save is
   still the only write, through its ONE approval card. The built-in template
   text is deliberately local and read-only; a template is inserted into the
   box exactly like typing, and nothing reaches disk until Save is approved.
   ========================================================================== */

/** Formatting controls, in toolbar order. Titles say the exact markdown. */
export const TOOLBAR = Object.freeze([
  { action: "bold", label: "B", aria: "Bold", title: "Bold (Ctrl+B) - puts ** on each side of the selection." },
  { action: "italic", label: "I", aria: "Italic", title: "Italic (Ctrl+I) - puts _ on each side of the selection." },
  { action: "strike", label: "S", aria: "Strikethrough", title: "Strikethrough (Ctrl+Shift+X) - puts ~~ on each side of the selection." },
  { action: "code", label: "<>", aria: "Inline code", title: "Inline code (Ctrl+E) - puts ` on each side of the selection." },
  { action: "quote", label: "❝", aria: "Quote", title: "Quote (Ctrl+Shift+Q) - puts > at the start of each selected line." },
  { action: "bullet", label: "•", aria: "Bullet list", title: "Bullet list (Ctrl+Shift+8) - puts - at the start of each selected line." },
  { action: "numbered", label: "1.", aria: "Numbered list", title: "Numbered list (Ctrl+Shift+7) - numbers each selected line." },
  { action: "checklist", label: "☐", aria: "Checklist", title: "Checklist (Ctrl+Shift+9) - puts - [ ] at the start of each selected line." },
  { action: "h2", label: "H2", aria: "Heading 2", title: "Heading 2 (Ctrl+2) - puts ## at the start of each selected line." },
  { action: "h3", label: "H3", aria: "Heading 3", title: "Heading 3 (Ctrl+3) - puts ### at the start of each selected line." },
  { action: "rule", label: "—", aria: "Horizontal rule", title: "Horizontal rule - inserts --- on a line of its own." },
  { action: "wikilink", label: "[[", aria: "Wikilink", title: "Wikilink (Ctrl+K) - wraps the selection in [[...]]; with no selection inserts [[]] with the cursor inside." },
  { action: "tag", label: "#", aria: "Tag", title: "Tag - inserts # before the selection, or #tag with no selection." },
  { action: "datetime", label: "Date", aria: "Insert date and time", title: "Insert date and time - inserts the local date and time, for example 2026-10-31 17:58." },
]);

/** The formatting shortcuts. Only the editor's textarea listens for them. */
export const SHORTCUTS = Object.freeze({
  "ctrl+b": "bold", "ctrl+i": "italic", "ctrl+k": "wikilink",
  "ctrl+e": "code", "ctrl+shift+x": "strike", "ctrl+shift+q": "quote",
  "ctrl+shift+7": "numbered", "ctrl+shift+8": "bullet",
  "ctrl+shift+9": "checklist", "ctrl+2": "h2", "ctrl+3": "h3",
});

/** Built-in templates. Text only; insertion never writes a file. */
export const BUILTIN_TEMPLATES = Object.freeze([
  { id: "workout-log", label: "Workout log",
    body: "# Workout - {date}\n\n- Exercise:\n  - Sets:\n  - Reps:\n  - Weight:\n\nNotes:\n" },
  { id: "meeting-notes", label: "Meeting notes",
    body: "# Meeting notes - {date}\n\nAttendees:\n\nAgenda:\n- \n\nNotes:\n\nActions:\n- [ ] \n" },
  { id: "daily-journal", label: "Daily journal",
    body: "# Daily journal - {date}\n\n## Today\n- \n\n## Notes\n- \n\n## Tomorrow\n- [ ] \n" },
  { id: "project-note", label: "Project note",
    body: "# Project note - {title}\n\nStatus:\n\nGoal:\n\nNotes:\n\nTasks:\n- [ ] \n" },
]);

/** The editor's help line, kept in one place so the buttons and it agree. */
export const EDITOR_HELP =
  "Markdown formatting is inserted into the box, never saved by itself. "
  + "Shortcuts work inside the box only: Ctrl+B bold · Ctrl+I italic · Ctrl+K wikilink · "
  + "Ctrl+E code · Ctrl+Shift+X strikethrough · Ctrl+Shift+Q quote · Ctrl+2/3 headings · "
  + "Ctrl+Shift+7 numbered · Ctrl+Shift+8 bullets · Ctrl+Shift+9 checklist. "
  + "Save is still the one write, with one approval card.";

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** A local date and time, the form the date button inserts. */
export function formatDateTime(date = new Date()) {
  const d = date instanceof Date && !Number.isNaN(date.getTime()) ? date : new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} `
    + `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/** Words, characters and the selection count for the live counter. */
export function noteCounts(text, start = 0, end = 0) {
  const value = typeof text === "string" ? text : "";
  const words = (value.match(/\S+/g) || []).length;
  const a = Math.max(0, Math.min(Number(start) || 0, value.length));
  const b = Math.max(a, Math.min(Number(end) || 0, value.length));
  const selected = value.slice(a, b);
  return {
    chars: value.length,
    words,
    selectedChars: selected.length,
    selectedWords: (selected.match(/\S+/g) || []).length,
  };
}

/** Fill a template's {date}/{title} tokens. Unknown tokens are left alone. */
export function fillTemplate(body, { date = "", title = "" } = {}) {
  return String(body || "")
    .replace(/\{date\}/g, date)
    .replace(/\{title\}/g, title);
}

/** One built-in template's text, filled, or "" for an unknown id. */
export function builtinTemplate(id, options = {}) {
  const found = BUILTIN_TEMPLATES.find((t) => t.id === id);
  return found ? fillTemplate(found.body, options) : "";
}

/**
 * The owner's vault Templates folder, from the list the plate already read.
 * Only `.md` files under a path segment called "Templates" (any case); this
 * never opens a file and never writes one.
 */
export function vaultTemplateFiles(notes = []) {
  const out = [];
  for (const note of Array.isArray(notes) ? notes : []) {
    const p = note && typeof note.path === "string" ? note.path : "";
    const parts = p.split("/");
    if (!p || !/\.md$/i.test(p)) continue;
    if (!parts.some((part) => part.toLowerCase() === "templates")) continue;
    const label = note.title || parts[parts.length - 1].replace(/\.md$/i, "");
    if (!out.some((n) => n.path === p)) out.push({ path: p, label });
  }
  return out;
}

function replaceRange(text, start, end, insert) {
  return text.slice(0, start) + insert + text.slice(end);
}

/** Insert text at the caret, or over the selection; returns the new caret. */
export function insertTextAtSelection(text, start, end, insert) {
  const value = typeof text === "string" ? text : "";
  const a = Math.max(0, Math.min(Number(start) || 0, value.length));
  const b = Math.max(a, Math.min(Number(end) || 0, value.length));
  const added = String(insert == null ? "" : insert);
  return {
    text: replaceRange(value, a, b, added),
    selectionStart: a + added.length,
    selectionEnd: a + added.length,
  };
}

const INLINE = {
  bold: { open: "**", close: "**", placeholder: "bold" },
  italic: { open: "_", close: "_", placeholder: "italic" },
  strike: { open: "~~", close: "~~", placeholder: "strikethrough" },
  code: { open: "`", close: "`", placeholder: "code" },
  wikilink: { open: "[[", close: "]]", placeholder: "" },
  tag: { open: "#", close: "", placeholder: "tag" },
};
const LINE_PREFIX = { quote: "> ", bullet: "- ", checklist: "- [ ] ", h2: "## ", h3: "### " };

function lineBlock(value, start, end) {
  const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
  let lineEnd = value.indexOf("\n", end);
  if (lineEnd === -1) lineEnd = value.length;
  return { lineStart, lineEnd, block: value.slice(lineStart, lineEnd) };
}

function prefixLines(value, start, end, prefix, numbered = false) {
  const { lineStart, lineEnd, block } = lineBlock(value, start, end);
  const lines = block.split("\n");
  const already = numbered
    ? lines.every((line) => /^\d+\.\s/.test(line))
    : lines.every((line) => line.startsWith(prefix));
  const changed = lines.map((line, i) => {
    if (numbered) return already ? line.replace(/^\d+\.\s/, "") : `${i + 1}. ${line}`;
    return already ? line.slice(prefix.length) : prefix + line;
  }).join("\n");
  const caret = lineStart + changed.length;
  return {
    text: value.slice(0, lineStart) + changed + value.slice(lineEnd),
    selectionStart: caret,
    selectionEnd: caret,
  };
}

/**
 * Apply one formatting control to the value. Pure: the caller decides what to
 * do with the result (the textarea here; a test elsewhere).
 */
export function applyMarkdownEdit(text, start, end, action, { now = new Date() } = {}) {
  const value = typeof text === "string" ? text : "";
  const a = Math.max(0, Math.min(Number(start) || 0, value.length));
  const b = Math.max(a, Math.min(Number(end) || 0, value.length));
  const selected = value.slice(a, b);
  const inline = INLINE[action];
  if (inline) {
    const { open, close, placeholder } = inline;
    if (action === "wikilink" && !selected) {
      return { text: replaceRange(value, a, b, "[[]]"),
        selectionStart: a + 2, selectionEnd: a + 2 };
    }
    if (action === "tag" && !selected) {
      return { text: replaceRange(value, a, b, "#"),
        selectionStart: a + 1, selectionEnd: a + 1 };
    }
    if (!selected && close) {
      const inserted = open + placeholder + close;
      return { text: replaceRange(value, a, b, inserted),
        selectionStart: a + open.length,
        selectionEnd: a + open.length + placeholder.length };
    }
    const wrapped = selected || placeholder;
    const inserted = open + wrapped + close;
    const startSel = a + open.length;
    return { text: replaceRange(value, a, b, inserted),
      selectionStart: startSel, selectionEnd: startSel + wrapped.length };
  }
  if (action === "numbered") {
    return prefixLines(value, a, b, "", true);
  }
  if (LINE_PREFIX[action]) {
    return prefixLines(value, a, b, LINE_PREFIX[action]);
  }
  if (action === "rule") {
    const prefix = a > 0 && value[a - 1] !== "\n" ? "\n" : "";
    const inserted = `${prefix}---\n`;
    return { text: replaceRange(value, a, b, inserted),
      selectionStart: a + inserted.length, selectionEnd: a + inserted.length };
  }
  if (action === "fence") {
    if (selected) {
      const inserted = "```\n" + selected + "\n```";
      return { text: replaceRange(value, a, b, inserted),
        selectionStart: a + inserted.length, selectionEnd: a + inserted.length };
    }
    const inserted = "```\n\n```";
    return { text: replaceRange(value, a, b, inserted),
      selectionStart: a + 4, selectionEnd: a + 4 };
  }
  if (action === "datetime") {
    const inserted = formatDateTime(now);
    return insertTextAtSelection(value, a, b, inserted);
  }
  return { text: value, selectionStart: a, selectionEnd: b };
}

/** Map a keydown to one of the toolbar actions, or "" outside the editor. */
export function shortcutAction(event) {
  if (!event || !(event.ctrlKey || event.metaKey) || event.altKey) return "";
  const key = String(event.key || "").toLowerCase();
  const code = String(event.code || "");
  if (event.shiftKey) {
    if (key === "x") return SHORTCUTS["ctrl+shift+x"];
    if (key === "q") return SHORTCUTS["ctrl+shift+q"];
    if (code === "Digit7" || key === "7" || key === "&") return SHORTCUTS["ctrl+shift+7"];
    if (code === "Digit8" || key === "8" || key === "*") return SHORTCUTS["ctrl+shift+8"];
    if (code === "Digit9" || key === "9" || key === "(") return SHORTCUTS["ctrl+shift+9"];
    return "";
  }
  return SHORTCUTS[`ctrl+${key}`] || "";
}

/**
 * The editor's formatting toolbar, template menu, help line and counter.
 * Built from plain DOM through the Brain's own `el`, so it inherits the
 * design system; every button has an aria-label and a title with the exact
 * markdown it inserts. It never saves: the caller's `plate.onDraft` only
 * remembers the words in the page.
 */
function editorTools(plate, text, open, ui) {
  const { el } = ui;
  const title = String(open.path || "").split("/").pop().replace(/\.md$/i, "");
  const toolbar = el("div", "notes-toolbar");
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "Markdown formatting");
  const counts = el("p", "notes-count");
  counts.setAttribute("role", "status");
  counts.setAttribute("aria-live", "polite");
  const templateSaid = el("p", "notes-template-said");
  templateSaid.setAttribute("role", "status");
  templateSaid.hidden = true;

  const afterEdit = () => {
    if (plate.onDraft) plate.onDraft(text.value);
    updateCounts();
  };

  const edit = (action) => {
    const result = applyMarkdownEdit(text.value, text.selectionStart,
      text.selectionEnd, action);
    text.value = result.text;
    text.focus();
    text.setSelectionRange(result.selectionStart, result.selectionEnd);
    afterEdit();
  };

  for (const spec of TOOLBAR) {
    const b = el("button", "btn small note-tool", spec.label);
    b.type = "button";
    b.dataset.action = spec.action;
    b.setAttribute("aria-label", spec.aria);
    b.title = spec.title;
    b.addEventListener("click", (event) => {
      event.preventDefault();
      edit(spec.action);
    });
    toolbar.append(b);
  }

  const select = el("select", "field note-template");
  select.setAttribute("aria-label", "Insert template");
  select.title = "Insert a template's markdown in the box at the caret. It does not create or "
    + "overwrite a note; Save is still the only write and needs its one card.";
  const placeholder = el("option", null, "Insert template…");
  placeholder.value = "";
  select.append(placeholder);
  const builtins = el("optgroup");
  builtins.label = "Built in";
  for (const template of BUILTIN_TEMPLATES) {
    const option = el("option", null, template.label);
    option.value = `builtin:${template.id}`;
    option.title = template.body.split("\n")[0].replace(/\{date\}/g, "date")
      .replace(/\{title\}/g, title);
    builtins.append(option);
  }
  select.append(builtins);
  const vaultTemplates = vaultTemplateFiles(plate.view && plate.view.notes);
  if (vaultTemplates.length) {
    const group = el("optgroup");
    group.label = "From your vault's Templates folder";
    for (const template of vaultTemplates) {
      const option = el("option", null, template.label);
      option.value = `vault:${template.path}`;
      option.title = template.path;
      group.append(option);
    }
    select.append(group);
  }
  select.addEventListener("change", async () => {
    const chosen = select.value;
    select.value = "";
    if (!chosen) return;
    let body = "";
    try {
      if (chosen.startsWith("builtin:")) {
        body = builtinTemplate(chosen.slice("builtin:".length),
          { date: formatDateTime(), title });
      } else if (chosen.startsWith("vault:")) {
        const path = chosen.slice("vault:".length);
        if (typeof plate.readTemplate !== "function") {
          throw new Error("this window cannot read that template file");
        }
        body = await plate.readTemplate(path);
      }
    } catch (error) {
      templateSaid.hidden = false;
      templateSaid.dataset.tone = "bad";
      templateSaid.textContent = `Could not read that template: ${String((error && error.message) || error)}. Nothing was changed.`;
      return;
    }
    if (!body) {
      templateSaid.hidden = false;
      templateSaid.dataset.tone = "bad";
      templateSaid.textContent = "That template is empty, so nothing was inserted.";
      return;
    }
    templateSaid.hidden = true;
    templateSaid.textContent = "";
    const result = insertTextAtSelection(text.value, text.selectionStart,
      text.selectionEnd, body);
    text.value = result.text;
    text.focus();
    text.setSelectionRange(result.selectionStart, result.selectionEnd);
    afterEdit();
  });
  toolbar.append(select);

  const help = el("p", "notes-help", EDITOR_HELP);

  function updateCounts() {
    const got = noteCounts(text.value, text.selectionStart, text.selectionEnd);
    let said = `${got.words} words · ${got.chars} characters`;
    if (got.selectedChars) {
      said += ` · ${got.selectedWords} words / ${got.selectedChars} characters selected`;
    }
    counts.textContent = said;
  }

  text.addEventListener("input", () => {
    if (plate.onDraft) plate.onDraft(text.value);
    updateCounts();
  });
  for (const eventName of ["select", "keyup", "click", "focus"]) {
    text.addEventListener(eventName, updateCounts);
  }
  text.addEventListener("keydown", (event) => {
    const action = shortcutAction(event);
    if (!action) return;
    event.preventDefault();
    edit(action);
  });
  updateCounts();
  return { toolbar, help, counts, templateSaid };
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
    const tools = editorTools(plate, text, open, ui);
    box.append(tools.toolbar, tools.help, text, tools.counts, tools.templateSaid);
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
    // Rename / Move (wave 4, 2026-10-31): two small chrome controls beside
    // Save. Each asks the PC's existing route, shows the PC's own words, and
    // follows the same ONE card; this window approves nothing and writes no
    // file. Disabled when the note has no path (nothing to rename or move).
    const canChange = Boolean(open.path) && !plate.saving && !plate.changing
      && !(said && said.final === false);
    const changeBox = el("div", "notes-change");
    changeBox.hidden = true;
    const baseTitle = titleOf(open.path);
    const rename = button("Rename…", () => {
      changeBox.replaceChildren();
      changeBox.append(el("p", "notes-help",
        "Rename this note. The PC raises ONE approval card; nothing is renamed, and no link changes, until you answer it there."));
      const input = el("input", "field notes-rename-title");
      input.type = "text";
      input.value = baseTitle;
      input.maxLength = 120;
      input.setAttribute("aria-label", "The note's new name");
      const go = button("Rename note", () => {
        const title = input.value.trim();
        if (!title) {
          input.setAttribute("aria-invalid", "true");
          input.focus();
          return;
        }
        input.removeAttribute("aria-invalid");
        if (plate.onRename) plate.onRename(title);
      }, { title: "Asks the PC to rename this note. ONE card on the PC decides; this window never approves it." });
      go.disabled = !canChange;
      changeBox.append(input, go);
      changeBox.hidden = false;
      input.focus();
      input.select();
    }, { title: "Rename this note on the PC - its ONE card decides, and links are kept." });
    rename.disabled = !canChange;
    const move = button("Move…", () => {
      changeBox.replaceChildren();
      changeBox.append(el("p", "notes-help",
        "Move this note into another folder in your vault. The PC raises ONE approval card; nothing moves, and no link changes, until you answer it there."));
      const select = el("select", "field notes-move-folder");
      select.setAttribute("aria-label", "The folder to move the note into");
      for (const folder of folderChoices(v.notes)) {
        const option = el("option", null, folder === "" ? "Top level (no folder)" : folder);
        option.value = folder;
        select.append(option);
      }
      const fresh = el("input", "field notes-move-new");
      fresh.type = "text";
      fresh.placeholder = "New folder name (optional)";
      fresh.setAttribute("aria-label", "A new folder name, if you want one");
      const createLabel = el("label", "check notes-move-create");
      const create = el("input");
      create.type = "checkbox";
      createLabel.append(create, el("span", null, "Create it if it does not exist"));
      const go = button("Move note", () => {
        const typed = fresh.value.trim();
        if (typed && !create.checked) {
          fresh.setAttribute("aria-invalid", "true");
          fresh.focus();
          return;
        }
        fresh.removeAttribute("aria-invalid");
        const folder = typed || select.value;
        if (plate.onMove) plate.onMove(folder, typed ? create.checked : false);
      }, { title: "Asks the PC to move this note. ONE card on the PC decides; this window never approves it." });
      go.disabled = !canChange;
      changeBox.append(select, fresh, createLabel, go);
      changeBox.hidden = false;
      select.focus();
    }, { title: "Move this note on the PC - its ONE card decides, and links are kept." });
    move.disabled = !canChange;
    actions.append(rename, move);
    box.append(actions, changeBox);
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
