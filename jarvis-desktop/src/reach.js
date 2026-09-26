/**
 * "What Jarvis can reach" (the Muse audit, 2026-09-25; JARVIS-API.md
 * section 24; backend jarvis_reach.py, reach.patch) - the words, and how to
 * read what the PC sends.
 *
 * Every way Jarvis can reach something outside itself, whether each is on,
 * where it goes (a host name only), whether it asks first, and one plain
 * line. The PC writes every row from its own settings - the AI model never
 * does - and the page shows the PC's words as they are. The words below are
 * only the parts of the screen, and the same as the PC's and the phone's
 * (backend/test_reach.py checks all three).
 *
 * Read only: nothing here changes a setting, so it is not held on a stale
 * link. Used by Settings, "What Jarvis can reach" (reach-settings.js;
 * src-tauri/src/reach.rs). The phone shows the same list on Mind
 * (ReachPlate.kt, net/Reach.kt).
 *
 * @module reach
 */

export const TITLE = "What Jarvis can reach";
export const DETAIL =
  "Every way Jarvis can reach something outside itself, and whether each one is " +
  "on right now. The PC writes this list from its own settings - the AI model does " +
  "not write it, so it cannot be talked into saying something else. Passwords, keys " +
  "and private links are never shown.";
export const MISSING =
  "Your PC's Jarvis cannot list what it can reach yet - run apply-patches.ps1 on " +
  "the PC.";
export const TOOLS_TITLE = "Tools the AI model is offered";
export const TOOLS_NONE = "None: the AI model is offered no tools, so it can only write answers.";
export const EVERYTHING_ELSE = "Anything not on this list stays on this PC.";
export const WHERE_LABEL = "Goes to";
export const ASKS_LABEL = "Asks you first";

const STATES = Object.freeze(["on", "off", "not_set_up", "blocked"]);

function text(v) {
  return typeof v === "string" ? v : "";
}

/** One row, from the PC's answer - its words as they are. */
function row(r) {
  const state = STATES.includes(r.state) ? r.state : "off";
  return {
    id: text(r.id),
    name: text(r.name),
    state,
    on: r.on === true && state === "on",
    stateWords: text(r.state_words) || state,
    where: text(r.where),
    asks: text(r.asks),
    line: text(r.line),
  };
}

/**
 * GET /api/reach (through get_reach), read. `available: false` with `why`
 * for a PC without it.
 */
export function readReach(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) return { available: false, why: text(a.why) || MISSING };
  const rows = Array.isArray(a.rows)
    ? a.rows.filter((r) => r && typeof r === "object" && r.id && r.name).map(row)
    : [];
  if (!rows.length) return { available: false, why: MISSING };
  const tools = Array.isArray(a.tools)
    ? a.tools.filter((t) => t && t.id).map((t) => ({ id: text(t.id), name: text(t.name) || text(t.id) }))
    : [];
  return {
    available: true,
    title: text(a.title) || TITLE,
    detail: text(a.detail) || DETAIL,
    rows,
    tools,
    toolsTitle: text(a.tools_title) || TOOLS_TITLE,
    toolsNone: text(a.tools_none) || TOOLS_NONE,
    everythingElse: text(a.everything_else) || EVERYTHING_ELSE,
    whereLabel: text(a.where_label) || WHERE_LABEL,
    asksLabel: text(a.asks_label) || ASKS_LABEL,
    on: rows.filter((r) => r.on).length,
  };
}

/** The lines under a row's name: where it goes and whether it asks (only
 *  when it is on), then its plain line. */
export function rowLines(r, v) {
  const out = [];
  if (r.on && r.where) out.push(`${(v && v.whereLabel) || WHERE_LABEL}: ${r.where}`);
  if (r.on && r.asks && r.asks !== "-") out.push(`${(v && v.asksLabel) || ASKS_LABEL}: ${r.asks}`);
  if (r.line) out.push(r.line);
  return out;
}
