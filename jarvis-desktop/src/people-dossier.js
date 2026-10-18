/**
 * One person's dossier, as the desktop's "People and things" draws it (LM-4).
 *
 * The PC builds the dossier (`backend/jarvis_people_crm.py`, JARVIS-API
 * section 143) and owns every privacy rule: while App lock or "Hide memory
 * lists and chat history" is on, the `people_dossier` command answers with a
 * withheld shape and one plain sentence - the page never asks and never
 * decides. This module is only the page's part: turn one answer into the two
 * strings the card draws, and never invent a name or a fact.
 *
 * Pure, so the rules can be tested without a window (`tests/people-dossier.mjs`).
 */

/** What the card shows when the PC withheld the dossier. */
export const HIDDEN_LINE =
  'Hidden while App lock or "Hide memory lists and chat history" is on.';

/** A PC whose backend predates the route (the command raises this). */
export const MISSING_LINE =
  "Your PC's Jarvis does not have the person dossier yet. Run apply-patches.ps1 on the PC.";

/** The PC answered, but not in a shape this page can read. */
export const UNREADABLE_LINE =
  "Jarvis answered, but not in a way this app can read. Update the backend by running apply-patches.ps1.";

/** Nothing has been opened yet: the card stays hidden. */
export const NOTHING_LINE = "";

/** The title, with the name only when the answer was actually allowed. */
export function dossierTitle(name, answer) {
  const clean = typeof name === "string" ? name : "";
  if (!answer || typeof answer !== "object" || answer.withheld === true) {
    return "Person dossier";
  }
  if (answer.ok === false && !clean) return "Person dossier";
  return clean ? `Person dossier - ${clean}` : "Person dossier";
}

/** The body: the PC's own rendering, or its one withheld sentence. */
export function dossierBody(answer) {
  if (!answer || typeof answer !== "object") return UNREADABLE_LINE;
  if (answer.withheld === true) {
    return String(answer.why || answer.text || HIDDEN_LINE);
  }
  if (answer.ok === false) {
    return String(answer.why || answer.text || UNREADABLE_LINE);
  }
  if (typeof answer.text === "string" && answer.text.trim()) return answer.text;
  // A dossier that was allowed but has no words at all still says so plainly.
  return "Jarvis has no saved facts about them.";
}

/** Is this answer the PC's withheld answer? */
export function isWithheld(answer) {
  return Boolean(answer && typeof answer === "object" && answer.withheld === true);
}
