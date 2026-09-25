/**
 * "About <name>" and the "are these the same?" card, in the Brain window's
 * Memory tab - memory wave 3, 2026-09-25 (JARVIS-API.md section 6,
 * `/api/memory/entities`; docs/ARCHITECTURE.md section 5, "Who is my
 * sister?").
 *
 * The PC links every saved fact to the people, pets, places and things it
 * names, and remembers what the owner calls them ("sister" -> Priya) - only
 * from a fact that says both. Chat recall uses that on the PC; both apps
 * get better answers without doing anything. This window also SHOWS it:
 *
 * - under a fact, the names it is linked to, each opening "About <name>";
 * - "About <name>" lists that entry's facts, word for word, read by id
 *   (brain/used.rs memory_used, the same read as "Used in this answer").
 *   There is no summary: nothing here is written by a model;
 * - the "are these the same?" card in the review queue, labelled for what
 *   its answers really do (yes joins the two, no keeps them apart for good).
 *
 * The phone shows none of this on purpose: the memory graph stays off the
 * phone (CLAUDE.md; ARCHITECTURE.md section 8, "One-sided on purpose").
 * Its recall improves all the same, because recall happens on the PC.
 *
 * This module holds the words and reads what the PC sends; brain.js draws.
 *
 * @module memory-entities
 */

/** The review-queue `source` of an "are these the same?" card. */
export const MERGE_SOURCE = "entity_merge";

/** The card's tag and two answers. */
export const MERGE_TAG = "same?";
export const MERGE_YES = "Yes, the same";
export const MERGE_NO = "No, keep them apart";
export const MERGE_YES_TITLE =
  "Join these two. A question about one also finds the other's facts. No fact is changed.";
export const MERGE_NO_TITLE = "Keep them apart. Jarvis will not ask about these two again.";
export const MERGE_NOTE =
  "Saying yes joins them. No fact is changed, added or forgotten either way.";
/** Said after each answer went through. */
export const MERGE_JOINED = "Joined. A question about one now finds the other's facts too.";
export const MERGE_KEPT = "Kept apart. Jarvis will not ask about these two again.";

/** The line under a fact, before its names. */
export const LINKED_LABEL = "About:";

/** "About Priya". */
export function aboutTitle(name) {
  return `About ${String(name || "").trim() || "this"}`;
}

/** The section's one line - what it is, and what it is not. */
export const ABOUT_DETAIL =
  "The facts Jarvis has linked to this name, word for word. Nothing here is written by the model.";

/** "You call them: sister" - the words the owner used, from their own facts. */
export function calledLine(aliases) {
  const a = (aliases || []).filter((x) => typeof x === "string" && x.trim());
  return a.length ? `You call them: ${a.join(", ")}` : "";
}

/** "Also written: Priyaa" - names the owner said were the same. */
export function alsoLine(also) {
  const a = (also || []).filter((x) => typeof x === "string" && x.trim());
  return a.length ? `Also written: ${a.join(", ")}` : "";
}

/** How many facts one "About" reads at most: the PC's /api/memory/used limit. */
export const ABOUT_MAX = 100;

export function moreLine(n) {
  return n > 0 ? `and ${n} older fact${n === 1 ? "" : "s"} not shown` : "";
}

/** Nothing linked (an entry whose facts were all forgotten since). */
export const ABOUT_EMPTY = "No fact in use is linked to this name any more.";

const wholeId = (v) => Number.isInteger(v) && v > 0;

/**
 * The PC's answer to GET /api/memory/entities, read defensively:
 * `{available, hidden, hiddenCount, entities: [{id, name, kind, aliases,
 * also, factIds}], byFact: Map(factId -> [entity, ...])}`. Anything that
 * is not that shape is "not available" - and then no fact shows a name,
 * rather than a half-read list.
 */
export function readEntities(body) {
  const none = { available: false, hidden: false, hiddenCount: 0, entities: [], byFact: new Map() };
  if (!body || typeof body !== "object" || body.available === false) return none;
  if (body.hidden === true) {
    return { ...none, available: true, hidden: true,
             hiddenCount: Number(body.hidden_count) || 0 };
  }
  if (!Array.isArray(body.entities)) return none;
  const entities = [];
  const byFact = new Map();
  for (const e of body.entities) {
    if (!e || typeof e !== "object" || !wholeId(e.id)) continue;
    const name = typeof e.name === "string" ? e.name.trim() : "";
    if (!name) continue;
    const factIds = (Array.isArray(e.fact_ids) ? e.fact_ids : []).filter(wholeId);
    const one = {
      id: e.id,
      name,
      kind: typeof e.kind === "string" ? e.kind : null,
      aliases: (Array.isArray(e.aliases) ? e.aliases : []).filter((a) => typeof a === "string"),
      also: (Array.isArray(e.also) ? e.also : []).filter((a) => typeof a === "string"),
      factIds,
    };
    entities.push(one);
    for (const f of factIds) {
      if (!byFact.has(f)) byFact.set(f, []);
      byFact.get(f).push(one);
    }
  }
  for (const list of byFact.values()) list.sort((a, b) => a.name.localeCompare(b.name));
  return { available: true, hidden: false, hiddenCount: 0, entities, byFact };
}

/** The entries one fact is linked to, by name. */
export function entitiesFor(view, factId) {
  if (!view || !view.byFact) return [];
  return view.byFact.get(Number(factId)) || [];
}

/** One entry by id, or null. */
export function entityById(view, id) {
  if (!view || !Array.isArray(view.entities)) return null;
  return view.entities.find((e) => e.id === Number(id)) || null;
}
