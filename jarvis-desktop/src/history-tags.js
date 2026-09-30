/**
 * Chat tags and sections in History (docs/CHAT-TAGS-DESIGN.md, the frozen
 * contract in section 10; JARVIS-API.md section 99).
 *
 * This file is the PURE half: the words, the palette, the icon drawings, how
 * the PC's answers are read, how the loaded chats are grouped into sections,
 * and the one thing kept on this device (which sections are open). brain.js
 * draws it. The words and the palette are the phone's too, word for word:
 * tests/history.mjs and tests/tags.mjs hold this file to
 * tests/fixtures/history-cases.json when tools/gen_history_cases.py has put
 * the tag keys there, and to the contract's own values until it has.
 *
 * What is never stored here: tag names. They are the owner's words, so they
 * are read from the PC each time, and Rust hides them with the private lists
 * (brain/history.rs). The only thing kept on this device is whether each
 * section is open or closed, by tag id - a view preference, not chat content.
 */

/* ── The shared words (section 10, "Shared words") ─────────────────────── */

export const UNTAGGED = "Untagged";
export const ALL = "All";
export const TAGS_TITLE = "Tags";
export const ADD_TAG = "Add a tag";
export const RENAME = "Rename";
export const DELETE_TAG = "Delete this tag";
export const MOVE_TO = "Move to";
export const NO_TAG = "No tag";
export const BANNER_CANCEL = "Cancel";

/** Section header: `{name} ({count})`. */
export const headerText = (name, count) => `${name} (${count})`;
/** The screen-reader form: `{name}, {count} chats, collapsed|expanded`. */
export const sectionSpeech = (name, count, open) =>
  `${name}, ${count} chats, ${open ? "expanded" : "collapsed"}`;
/** Delete confirm. */
export const deleteConfirm = (name, count) =>
  `Delete the tag ${name}? Its ${count} chats become untagged.`;
/** The banner while an older chat is being found to file. */
export const bannerText = (name) => `Tap the chat to file it under ${name}.`;

/* ── Words that are this app's own (not in the contract's shared list) ─── */

export const TAGS_EDITOR_NOTE =
  "Tags are your own labels for chats. A chat has one tag. Nothing here leaves this PC.";
export const NAME_LABEL = "Tag name";
export const COLOUR_LABEL = "Colour";
export const ICON_LABEL = "Icon";
export const MOVE_UP = "Move up";
export const MOVE_DOWN = "Move down";
export const TAG_CHIPS_LABEL = "Show chats with this tag";
export const NO_TAG_CHATS = "No chats are filed under this tag yet.";
export const NOT_LOADED_LINE = "Older chats here load with Load older.";
export const MOVE_PLACEHOLDER = "Move to…";
export const TAGS_HIDDEN_LINE =
  "Tags are hidden along with your chat titles until Windows Hello confirms it is you.";

/** One plain sentence per error code the PC answers with. */
export const TAG_ERRORS = Object.freeze({
  bad_name: "A tag name needs 1 to 24 letters or numbers.",
  name_taken: "You already have a tag with that name.",
  too_many_tags: "You can have up to 12 tags. Delete one to make room.",
  bad_colour: "That colour is not one of the eight.",
  bad_icon: "That icon is not on the list.",
  tag_not_found: "That tag is gone. Reload History to see your tags.",
  not_found: "That chat is gone - it may have been deleted.",
  bad_request: "That request was not understood.",
});

export function errorWords(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const code = typeof a.error === "string" ? a.error : "";
  return TAG_ERRORS[code] || (typeof a.message === "string" && a.message.trim()) ||
    TAG_ERRORS.bad_request;
}

export const filedWords = (name) => `Filed under ${name}.`;
export const UNFILED_WORDS = "Tag taken off.";
/** The banner's button on a chat row while an older chat is being found. */
export const fileUnderWords = (name) => `File under ${name}`;

/* ── The contract's numbers ────────────────────────────────────────────── */

export const MAX_TAGS = 12;
export const NAME_MAX = 24;

/** Eight colour slots. `light` and `dark` are the ink colours the contract
 *  checked at 4.5:1 or better on the tinted header; the CSS variables in
 *  theme.css (`--tag-0` ... `--tag-7`) carry them, and a test holds the two
 *  together. */
export const COLOURS = Object.freeze([
  { slot: 0, name: "blue", light: "#1d4ed8", dark: "#93b4ff" },
  { slot: 1, name: "green", light: "#146c36", dark: "#86e0a6" },
  { slot: 2, name: "amber", light: "#8a5300", dark: "#f5c26b" },
  { slot: 3, name: "violet", light: "#6d28d9", dark: "#c4a8ff" },
  { slot: 4, name: "teal", light: "#0f766e", dark: "#7adfd3" },
  { slot: 5, name: "rose", light: "#be123c", dark: "#ff9ab5" },
  { slot: 6, name: "slate", light: "#475569", dark: "#b6c2d1" },
  { slot: 7, name: "orange", light: "#b43a00", dark: "#ffb385" },
]);

/** The shared icon names, in the contract's order. */
export const ICONS = Object.freeze([
  "briefcase", "book", "home", "folder", "lightbulb", "star", "flag", "wrench", "leaf", "music",
]);

/** The starter tags (created by the PC the first time the registry is read;
 *  here only so a test can hold the contract to them). */
export const STARTERS = Object.freeze([
  { id: 1, name: "Work", colour: 0, icon: "briefcase" },
  { id: 2, name: "Learning", colour: 1, icon: "book" },
  { id: 3, name: "Personal", colour: 2, icon: "home" },
  { id: 4, name: "Projects", colour: 3, icon: "folder" },
  { id: 5, name: "Ideas", colour: 4, icon: "lightbulb" },
]);

/** The colour's plain name ("blue"), for the picker and the screen reader:
 *  a colour is never the only clue. */
export function colourName(slot) {
  const c = COLOURS[slot];
  return c ? c.name : COLOURS[6].name;
}

/** Simple line drawings on a 24x24 grid, stroked in the current colour. One
 *  or more path strings each. No icon library, no emoji. */
export const ICON_PATHS = Object.freeze({
  briefcase: [
    "M5 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z",
    "M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2",
    "M3 13h18",
  ],
  book: [
    "M6 3h13v15H6a2 2 0 0 0-2 2V5a2 2 0 0 1 2-2z",
    "M4 20a2 2 0 0 0 2 2h13",
    "M9 8h6",
  ],
  home: ["M3 11l9-8 9 8", "M5 10v10h5v-6h4v6h5V10"],
  folder: ["M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
  lightbulb: [
    "M9 18h6",
    "M10 21h4",
    "M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z",
  ],
  star: ["M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"],
  flag: ["M5 21V4", "M5 4h11l-2 4 2 4H5"],
  wrench: ["M15 4a4 4 0 0 0-3.6 5.7L4 17a2 2 0 0 0 3 3l7.3-7.4A4 4 0 0 0 20 9l-3 3-3-3z"],
  leaf: ["M5 19C5 9 11 4 20 4c0 9-5 15-15 15z", "M5 19c3-4 6-7 10-9"],
  music: [
    "M9 18V5l11-2v13",
    "M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    "M20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
  ],
});

const SVG_NS = "http://www.w3.org/2000/svg";

/** An inline SVG for an icon name (an unknown name draws the folder). It is
 *  decoration: the name beside it says the same thing, so it is hidden from
 *  screen readers. */
export function iconNode(name, doc = document) {
  const svg = doc.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.classList.add("tag-icon");
  for (const d of ICON_PATHS[name] || ICON_PATHS.folder) {
    const path = doc.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

/* ── Reading the PC's answers ──────────────────────────────────────────── */

const int = (v) => (Number.isInteger(v) ? v : null);
const text = (v) => (typeof v === "string" ? v : "");

/**
 * `GET /api/history/tags`, as the page uses it. An older PC (`available:
 * false`) has no tags and the History list stays flat. While the private
 * lists are hidden the names are gone (Rust took them out) and only counts
 * are left: `hidden` is true then.
 */
export function readTags(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) {
    return { available: false, why: text(a.why).trim(), hidden: false, tags: [], untagged: 0 };
  }
  const list = Array.isArray(a.tags) ? a.tags : [];
  const hidden = a.hidden === true;
  const tags = list
    .filter((t) => t && int(t.id) !== null && t.id > 0)
    .map((t, i) => ({
      id: t.id,
      name: hidden ? "" : text(t.name).trim(),
      colour: int(t.colour) !== null && t.colour >= 0 && t.colour < COLOURS.length ? t.colour : 6,
      icon: ICONS.includes(t.icon) ? t.icon : "folder",
      order: int(t.order) ?? i,
      count: Math.max(0, int(t.count) ?? 0),
    }))
    .sort((x, y) => x.order - y.order || x.id - y.id);
  return {
    available: true,
    why: "",
    hidden,
    tags,
    untagged: Math.max(0, int(a.untagged) ?? 0),
  };
}

/** A tag by id, or null. */
export function tagById(view, id) {
  if (!view || !view.available || id === null || id === undefined) return null;
  return view.tags.find((t) => t.id === id) || null;
}

/** `tag_id` on a row, as a whole number or null. */
export function readTagId(value) {
  return Number.isInteger(value) && value > 0 ? value : null;
}

/* ── Sections ──────────────────────────────────────────────────────────── */

/**
 * The loaded chats in sections: one per tag in the tags' own order, newest
 * chat first inside (the list is already newest first and its order is
 * kept), "Untagged" last. A chat whose tag is not in the registry (deleted
 * elsewhere a moment ago) falls under Untagged. A tag with no chats and no
 * count is left out - an empty header says nothing.
 *
 * `count` is what the header shows: the PC's own count for the tag when
 * nothing narrows the list (`exact`), else how many rows are shown - a
 * "Live only" or title filter changes what "N chats" would mean.
 */
export function groupRows(rows, view, { exact = true } = {}) {
  const tags = view && view.available ? view.tags : [];
  const known = new Set(tags.map((t) => t.id));
  const byTag = new Map(tags.map((t) => [t.id, []]));
  const loose = [];
  for (const c of rows) {
    if (c.tagId !== null && c.tagId !== undefined && known.has(c.tagId)) byTag.get(c.tagId).push(c);
    else loose.push(c);
  }
  const sections = [];
  for (const t of tags) {
    const shown = byTag.get(t.id);
    const count = exact ? Math.max(t.count, shown.length) : shown.length;
    if (!shown.length && !count) continue;
    sections.push({ key: String(t.id), tag: t, rows: shown, count });
  }
  const untaggedCount = exact ? Math.max(view ? view.untagged : 0, loose.length) : loose.length;
  if (loose.length || untaggedCount) {
    sections.push({ key: "none", tag: null, rows: loose, count: untaggedCount });
  }
  return sections;
}

/* ── Which sections are open (the one thing kept on this device) ───────── */

export const SECTIONS_KEY = "jarvis.history.sections";

/** The stored flags: `{ "<tag id>" | "none": boolean }`, nothing else. */
export function readOpenFlags(storage = globalThis.localStorage) {
  try {
    const raw = JSON.parse(storage.getItem(SECTIONS_KEY) || "{}");
    const out = {};
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      for (const [k, v] of Object.entries(raw)) {
        if ((k === "none" || /^[1-9][0-9]{0,5}$/.test(k)) && typeof v === "boolean") out[k] = v;
      }
    }
    return out;
  } catch {
    return {};
  }
}

/** Remembers one section open or closed. Only that flag is written. */
export function saveOpenFlag(key, open, storage = globalThis.localStorage) {
  const flags = readOpenFlags(storage);
  if (!(key === "none" || /^[1-9][0-9]{0,5}$/.test(String(key)))) return flags;
  flags[String(key)] = Boolean(open);
  try {
    storage.setItem(SECTIONS_KEY, JSON.stringify(flags));
  } catch {
    /* no storage: it just opens the way it started */
  }
  return flags;
}

/** Open unless the owner closed it. */
export function isOpen(flags, key) {
  return flags[key] !== false;
}

/* ── "Label my chat about the boiler as Home" ──────────────────────────── */

/**
 * The route fields main.js leaves under the Brain's place key: the tag id
 * (`file_under`, digits) and the search words (`history_q`). Nothing else is
 * taken, and both are checked again here. Null when either is missing or odd.
 */
export function readFilePlace(left) {
  if (!left || typeof left !== "object") return null;
  const raw = left.file_under;
  const id = typeof raw === "number" ? raw : /^[0-9]{1,6}$/.test(String(raw ?? "")) ? Number(raw) : NaN;
  const q = text(left.history_q).replace(/\s+/g, " ").trim().slice(0, 100);
  if (!Number.isInteger(id) || id <= 0 || !q) return null;
  return { tagId: id, q };
}
