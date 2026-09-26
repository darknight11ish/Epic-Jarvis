/**
 * "Folders Jarvis may look in" (the owner's decisions of 2026-09-26: asking
 * about PDFs and Word files, and bringing in a Notion export; JARVIS-API.md
 * section 35; backend jarvis_documents.py, documents.patch) - the words, and
 * how to read what the PC sends. No DOM.
 *
 * ONE list, empty by default. Adding a folder is the PC's only: the Windows
 * folder picker, then ONE approval card on the PC - held while the event
 * stream is stale, because it lets Jarvis see more. Removing one is at once,
 * never held - it only lets Jarvis see less. "Bring in a Notion export"
 * unzips the owner's export into a new folder inside a listed one (the PC
 * only, no card: the owner picked the file and the folder here).
 *
 * The PC writes the words (title, detail, the empty line, the phone's line);
 * the page shows them as they are. The phone shows the same list, with
 * Remove only (FoldersPlate.kt, net/Folders.kt). Used by Settings
 * (folders-settings.js; src-tauri/src/folders.rs).
 *
 * @module folders
 */

export const TITLE = "Folders Jarvis may look in";
/** What a PC without jarvis_documents.py / documents.patch says (Rust FOLDERS_MISSING). */
export const MISSING =
  "Your PC's Jarvis cannot look in folders yet - run apply-patches.ps1 on the PC.";
export const STALE =
  "The connection to Jarvis is catching up, so nothing can be sent until it does.";
export const ADD_LABEL = "Add a folder…";
export const REMOVE_LABEL = "Remove";
export const NOTION_LABEL = "Choose the .zip…";
export const NOT_HERE = "Not found on this PC any more.";

function text(v) {
  return typeof v === "string" ? v : "";
}

/** One listed folder, from the PC's answer. */
function folder(f) {
  return {
    path: text(f.path),
    name: text(f.name) || text(f.path),
    exists: f.exists !== false,
  };
}

/**
 * GET /api/folders (through get_folders), read. `available: false` with
 * `why` for a PC without it.
 */
export function readFolders(answer) {
  if (!answer || typeof answer !== "object" || answer.available === false) {
    const why = answer && text(answer.why).trim() ? text(answer.why).trim() : MISSING;
    return { available: false, why, folders: [] };
  }
  const docs = answer.documents && typeof answer.documents === "object" ? answer.documents : {};
  const notion = answer.notion && typeof answer.notion === "object" ? answer.notion : {};
  const last = answer.last && typeof answer.last === "object" ? answer.last : null;
  return {
    available: true,
    title: text(answer.title) || TITLE,
    detail: text(answer.detail),
    empty: text(answer.empty),
    why: text(answer.why),
    folders: Array.isArray(answer.folders) ? answer.folders.map(folder).filter((f) => f.path) : [],
    canAdd: answer.can_add === true,
    phoneAdd: text(answer.phone_add),
    waiting: answer.waiting && text(answer.waiting.path) ? text(answer.waiting.path) : "",
    waitingWords: text(answer.waiting_words),
    lastWords: last ? text(last.message) : "",
    documentsReady: docs.ready === true,
    documentsSaid: text(docs.said),
    notionTitle: text(notion.title),
    notionDetail: text(notion.detail),
    canImport: notion.can_import === true,
    removeLabel: text(answer.remove_label) || REMOVE_LABEL,
    max: Number.isInteger(answer.max) ? answer.max : 20,
  };
}

/**
 * What the page can offer now. Adding (a card) and importing wait for a
 * live link and for the PC to say this request may; removing never waits.
 */
export function actions(view, live) {
  const full = view.folders.length >= view.max;
  return {
    add: view.available && view.canAdd && live && !view.waiting && !full,
    addWhy: !view.available ? view.why
      : !view.canAdd ? view.phoneAdd
        : !live ? STALE
          : view.waiting ? view.waitingWords
            : full ? `The list already has ${view.max} folders - remove one first.` : "",
    remove: view.available,
    notion: view.available && view.canImport && live && view.folders.some((f) => f.exists),
  };
}

/** The lines under a folder's name. */
export function folderLines(f) {
  return f.exists ? [f.path] : [f.path, NOT_HERE];
}
