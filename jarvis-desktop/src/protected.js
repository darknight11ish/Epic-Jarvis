/**
 * Settings -> "Protected from Jarvis" - the words, and how to read what the
 * PC sends. No DOM.
 *
 * The owner's request of 2026-10-31: *"add a list of file folders, and
 * programs that i can manually add to (or ask jarvis to exclude in chat and
 * get a card) that blocks jarvis from having any access (read or write) or the
 * ability to make certain files or folders or programs read only"*. The fixed
 * contract is `.dsh-scratch/PROTECTED-ITEMS-2026-10-31/CONTRACT.md`.
 *
 * ONE list on the PC. Every entry is a folder, a file or a program, and has
 * one of two modes:
 *
 *   blocked   no access at all - no read, no search hit, no write, no delete,
 *             and for a program no opening/closing/controlling and no screen
 *             reading of its windows.
 *   readonly  files/folders: reads and search results are allowed, every
 *             write/delete/rename/restore is refused. A program: see it,
 *             never act - reading its window is allowed, clicking, typing,
 *             opening or closing it is refused.
 *
 * Adding in Settings is the owner's own direct act (immediate, tightening);
 * removing always raises ONE approval card on the PC. The PC writes the
 * sentences; this page shows them as they are. The phone shows the same list
 * with Remove only and no pickers (the phone has no view of the PC's files).
 *
 * Used by Settings (`protected-settings.js`) and its Rust commands
 * (`src-tauri/src/protected.rs`).
 *
 * @module protected
 */

export const TITLE = "Protected from Jarvis";
/** What a PC without the protected-items module says (Rust `PROTECTION_MISSING`). */
export const MISSING =
  "Your PC's Jarvis cannot protect things yet - run apply-patches.ps1 on the PC.";
export const STALE =
  "The connection to Jarvis is catching up, so nothing can be sent until it does.";
export const ADD_FOLDER = "Add a folder…";
export const ADD_FILE = "Add a file…";
export const ADD_PROGRAM = "Add a program…";
export const REMOVE = "Remove";
export const MODE_BLOCKED = "Blocked — no access";
export const MODE_READONLY = "Read-only";
export const WAITING_REMOVE =
  "Removing asks for one approval card on this PC. Nothing is removed until you answer it.";

/** One word per kind, for the row and the choice heading. */
export const KINDS = { folder: "Folder", file: "File", program: "Program" };

/** The two modes, in the owner's words; Blocked is the recommended one. */
export const MODES = [
  {
    id: "blocked",
    label: MODE_BLOCKED,
    hint: "Jarvis cannot read, write, search or act on it at all.",
  },
  {
    id: "readonly",
    label: MODE_READONLY,
    hint: "Jarvis may read it; every write, delete, rename or action is refused.",
  },
];

function text(v) {
  return typeof v === "string" ? v : "";
}

/** "Folder", "File" or "Program"; an unknown kind shows as it came. */
export function kindWords(kind) {
  return KINDS[kind] || text(kind);
}

/** The mode in the owner's words. */
export function modeWords(mode) {
  return mode === "blocked" ? MODE_BLOCKED : mode === "readonly" ? MODE_READONLY : text(mode);
}

/**
 * The line under an entry's mode. A program's Read-only is the owner's own
 * chosen meaning ("see it, never act"), so it is said in those words.
 */
export function modeHint(mode, kind) {
  if (mode === "blocked") {
    return kind === "program"
      ? "Jarvis cannot open, close or control it, and cannot read its window."
      : "Jarvis cannot read, write, search or open it at all.";
  }
  if (mode === "readonly") {
    return kind === "program"
      ? "See it, never act: Jarvis may read its window, but clicking, typing, opening or closing it is refused."
      : "Jarvis may read it; every write, delete, rename or restore is refused.";
  }
  return "";
}

/** One listed entry, from the PC's answer. */
function item(i) {
  const kind = text(i.kind);
  const mode = text(i.mode);
  return {
    id: text(i.id),
    kind,
    target: text(i.target),
    mode,
    added: text(i.added),
    addedBy: text(i.added_by),
    kindWords: kindWords(kind),
    modeWords: modeWords(mode),
    modeHint: modeHint(mode, kind),
  };
}

/**
 * `GET /api/protection` (through `get_protection`), read. `available: false`
 * with `why` for a PC without the route or with no vault-style setup.
 */
export function readProtection(answer) {
  if (!answer || typeof answer !== "object" || answer.available === false) {
    const why = answer && text(answer.why).trim() ? text(answer.why).trim() : MISSING;
    return { available: false, why, count: 0, items: [], changeCard: "" };
  }
  const items = Array.isArray(answer.items) ? answer.items.map(item).filter((i) => i.id) : [];
  return {
    available: true,
    why: "",
    count: Number.isInteger(answer.count) ? answer.count : items.length,
    items,
    changeCard: text(answer.change_card),
  };
}

/** The programs this PC is running now: names only, lower-cased, unique. */
export function readPrograms(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const raw = Array.isArray(a.programs) ? a.programs : [];
  const seen = new Set();
  const out = [];
  for (const name of raw) {
    if (typeof name !== "string") continue;
    const n = name.trim().toLowerCase();
    if (!n || seen.has(n)) continue;
    seen.add(n);
    out.push(n);
  }
  out.sort();
  return { ok: a.ok !== false, programs: out };
}

/** The chosen path from `protection_pick`; "" when the dialog was cancelled. */
export function readPick(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.cancelled === true) return "";
  return text(a.path);
}

/**
 * Words for one add answer, as `{ text, tone }`. The PC's own `message` when
 * it stored the entry; its own `error` sentence when it refused. Never claims
 * a stored entry without one.
 */
export function describeAdd(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const said = text(a.message).trim() || text(a.error).trim() || text(a.why).trim();
  if (a.ok === true) {
    return { text: said || "Protected. Jarvis will leave it alone.", tone: "ok" };
  }
  return { text: said || "That entry was not added. Nothing was changed.", tone: "bad" };
}

/**
 * What the page may offer now. Adding is the owner's direct act (immediate,
 * so it does not wait for a live stream); removing raises a card, so it is
 * offered only on a live link (rule 4), exactly like the folders plate.
 */
export function actions(view, live) {
  return {
    add: Boolean(view && view.available),
    remove: Boolean(view && view.available && live),
    removeWhy: !view || !view.available ? text(view && view.why) || MISSING
      : !live ? STALE : "",
  };
}
