/**
 * Galaxy: the people and things Jarvis knows about - the pure half (the
 * owner's choice of 2026-09-28; docs/RESEARCH-AUDIT-2026-09-28.md section
 * 8.2, idea 1; JARVIS-API.md section 71). brain.js draws it on the canvas.
 *
 * Built from `GET /api/memory/entities` - the list the Memory tab already
 * reads for "About <name>", and already hides under "Windows Hello for
 * memory lists and chat history" (lock/rules.rs PRIVATE_LISTS). Each dot is
 * one person, pet, place or thing a saved fact names; its size is how many
 * facts name it; two dots are joined when one fact names both, and the
 * line is as strong as how many facts they share. All of that is worked
 * out HERE, from the fact ids the list already carries - no new route, no
 * fact's words, nothing sent anywhere.
 *
 * It replaces the old picture of `/api/graph`, whose "fact" dots could
 * carry a fact's words while the memory lists said "hidden" (privacy
 * finding B1). The idea of a picture of people and things is Hindsight's
 * (MIT, `entities-view.tsx` / `constellation.tsx`); none of its code is
 * used. The phone has no Galaxy: the memory graph stays off it (CLAUDE.md).
 *
 * @module galaxy-view
 */

/**
 * Each kind the PC can name (jarvis_entities.KINDS), its group on the
 * canvas, and the words the legend and the panel use. A kind the PC did not
 * name, or one this list has never heard of, is "other".
 */
export const KIND_GROUPS = Object.freeze({
  person: "person",
  pet: "pet",
  place: "place",
  organisation: "organisation",
  project: "project",
  thing: "thing",
});

/** The legend's words, plural, and the panel's, singular. */
export const GROUP_WORDS = Object.freeze({
  person: ["people", "person"],
  pet: ["pets", "pet"],
  place: ["places", "place"],
  organisation: ["organisations", "organisation"],
  project: ["projects", "project"],
  thing: ["things", "thing"],
  other: ["not sure what kind", "not sure what kind"],
});

/** Facts naming more than this many names are not joined pairwise: such a
 *  fact is a list, and joining everything in it says nothing. */
export const MAX_NAMES_PER_FACT = 12;

export function groupFor(kind) {
  return (typeof kind === "string" && KIND_GROUPS[kind]) || "other";
}

export function groupWords(group, { plural = true } = {}) {
  const w = GROUP_WORDS[group] || GROUP_WORDS.other;
  return plural ? w[0] : w[1];
}

/**
 * readEntities()'s view (memory-entities.js) -> `{nodes, links}`:
 *   nodes: [{id: "e:<id>", entityId, label, group, weight (facts), aliases,
 *            also}], most facts first;
 *   links: [{source: "e:<a>", target: "e:<b>", shared (facts both are in)}].
 */
export function buildEntityGraph(view) {
  const entities = view && Array.isArray(view.entities) ? view.entities : [];
  const nodes = entities.map((e) => ({
    id: `e:${e.id}`,
    entityId: e.id,
    label: e.name,
    group: groupFor(e.kind),
    weight: Array.isArray(e.factIds) ? e.factIds.length : 0,
    aliases: Array.isArray(e.aliases) ? e.aliases : [],
    also: Array.isArray(e.also) ? e.also : [],
  }));
  nodes.sort((a, b) => b.weight - a.weight || a.label.localeCompare(b.label) || a.entityId - b.entityId);
  const byId = new Map(entities.map((e) => [e.id, e]));
  const byFact = new Map();
  for (const n of nodes) {
    const e = byId.get(n.entityId);
    for (const f of (e && e.factIds) || []) {
      if (!byFact.has(f)) byFact.set(f, []);
      const names = byFact.get(f);
      if (!names.includes(n.id)) names.push(n.id);
    }
  }
  const shared = new Map();
  for (const names of byFact.values()) {
    if (names.length < 2 || names.length > MAX_NAMES_PER_FACT) continue;
    for (let i = 0; i < names.length; i++) {
      for (let j = i + 1; j < names.length; j++) {
        const [a, b] = [names[i], names[j]].sort();
        const key = `${a}\u0000${b}`;
        shared.set(key, (shared.get(key) || 0) + 1);
      }
    }
  }
  const links = [...shared.entries()]
    .map(([key, n]) => {
      const [source, target] = key.split("\u0000");
      return { source, target, shared: n };
    })
    .sort((x, y) => y.shared - x.shared || x.source.localeCompare(y.source) || x.target.localeCompare(y.target));
  return { nodes, links };
}

/** "2 shared facts". */
export function sharedWords(n) {
  return `${n} shared ${n === 1 ? "fact" : "facts"}`;
}

/**
 * The names that match what was typed - in the name, a name joined to it,
 * or a word the owner uses for it ("sister") - most facts first. Any case.
 */
export function findNames(nodes, query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q || !Array.isArray(nodes)) return [];
  return nodes.filter((n) =>
    [n.label, ...(n.also || []), ...(n.aliases || [])].some((s) => String(s).toLowerCase().includes(q)));
}

/** What the line beside the search box says (the research audit's B3: it
 *  used to jump to the first match only, and say nothing when there was
 *  none). */
export function findStatus(at, total) {
  if (!total) return "No name matches that.";
  if (total === 1) return "1 match.";
  return `${at + 1} of ${total}. Press Enter for the next.`;
}
