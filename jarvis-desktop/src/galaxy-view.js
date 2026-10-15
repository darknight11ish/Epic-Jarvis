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
 * fact's words, nothing sent anywhere. The picture is bounded: at most
 * MAX_RENDERED_NODES dots, chosen by orderedEntities (most facts first,
 * then the most recent) so the same list always draws the same Galaxy.
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

/** The most names the Galaxy draws at once.
 *
 *  A CHOSEN bound, not a measured one: the PC caps its own answer at 500
 *  entries (`entities_view(limit=500)`, rebuilt/jarvis_memory.py:3705), and
 *  every one of these is a real HTML button over the picture
 *  (galaxy-constellation.js), not a painted dot - so a picture of 500 names
 *  is both unreadable and the heaviest thing this page can draw. 240 is
 *  comfortably more than any list a person reads at a glance and well under
 *  the PC's own ceiling. Which 240 is not arbitrary: see orderedEntities. */
export const MAX_RENDERED_NODES = 240;

/**
 * Is a saved fact still in use at `asOfSeconds`? This is brain.js's own rule
 * (brain.js:2884-2888), where the Memory tab renders every fact row with it:
 * the server's `current` flag first, then the bi-temporal field it is
 * derived from. The rule lives in two files and must not drift - the fact
 * list writes it inline over the rows it draws, and the cap needs the same
 * answer to decide which names survive - so a check in tests/galaxy.mjs
 * compares both sources for it.
 */
export function isLiveFactAt(fact, asOfSeconds) {
  if (!fact || typeof fact !== "object") return false;
  if (fact.current === true) return true;
  if (fact.current === false) return false;
  const to = fact.valid_to;
  return to === null || to === undefined || Number(to) > asOfSeconds;
}

/** The fact rows a caller handed us, by id (id -> row). */
function factRowsById(facts) {
  const by = new Map();
  if (!Array.isArray(facts)) return by;
  for (const f of facts) {
    const id = Number(f && f.id);
    if (Number.isInteger(id)) by.set(id, f);
  }
  return by;
}

/**
 * The names the Galaxy draws, in the order the cap keeps, cut to
 * MAX_RENDERED_NODES. Deterministic and total: the same list always draws
 * the same picture, twice, and from a shuffled copy of itself.
 *
 *   1. most facts first - what a dot's size means, and the PC's own order
 *      (`-facts, name, id`, rebuilt/jarvis_memory.py:3767);
 *   2. then the newest fact id: the PC sends `fact_ids` newest-first
 *      (rebuilt/jarvis_memory.py:3765, and memory-entities.js keeps that
 *      order), so the highest id is the most recent thing Jarvis learned
 *      about that name. This is the "recent wins" half of the rule, and it
 *      is real - it is carried by the answer the Galaxy already reads;
 *   3. then the label A-Z, then the entity id, so names that tie on all of
 *      the above still have exactly one order.
 *
 * RETIRED FACTS. A caller may hand in fact rows (`facts`: the `facts` array
 * of the Memory tab's /api/memory/facts answer, each `{id, current,
 * valid_to}`) and the moment asked about. Then a name whose facts are all
 * retired (`isLiveFactAt`) sorts below every name with a live fact and counts
 * only its live facts, so retired names are the first the cap drops.
 *
 * That branch CANNOT ARISE FROM TODAY'S PC, and a reader must not expect to
 * observe it: /api/memory/entities builds its links with `WHERE f.erased_at
 * IS NULL AND (f.valid_to IS NULL OR f.valid_to > ?)`
 * (rebuilt/jarvis_memory.py:3731-3732), so a retired fact is filtered at the
 * source and never reaches this list at all. The rule is kept for a caller
 * that does supply rows - a test, or a PC that one day lists them. A fact id
 * with NO row handed in counts as live, because the PC's answer lists only
 * current, unerased facts.
 */
export function orderedEntities(entities, { facts = null, asOfSeconds = null } = {}) {
  const list = Array.isArray(entities) ? entities : [];
  const by = factRowsById(facts);
  // Left out, the moment asked about is NOW - not epoch 0, which is what
  // Number(null) would quietly give a fact rows' caller.
  const asked = asOfSeconds === null || asOfSeconds === undefined ? NaN : Number(asOfSeconds);
  const at = Number.isFinite(asked) ? asked : Date.now() / 1000;
  const scored = list.map((e, i) => {
    const ids = Array.isArray(e && e.factIds) ? e.factIds : [];
    let live = 0;
    let newest = 0;
    for (const id of ids) {
      const n = Number(id);
      const row = by.get(n);
      if (row && !isLiveFactAt(row, at)) continue;   // retired: not counted
      live += 1;
      if (Number.isFinite(n) && n > newest) newest = n;
    }
    return { e, live, newest, i, label: String((e && e.name) || ""), id: Number(e && e.id) };
  });
  scored.sort((a, b) =>
    b.live - a.live
    || b.newest - a.newest
    || a.label.localeCompare(b.label)
    || ((Number.isFinite(a.id) ? a.id : 0) - (Number.isFinite(b.id) ? b.id : 0))
    || a.i - b.i);
  return scored.slice(0, MAX_RENDERED_NODES).map((s) => s.e);
}

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
 *            also}], in orderedEntities' order (most facts first), at most
 *            MAX_RENDERED_NODES of them;
 *   links: [{source: "e:<a>", target: "e:<b>", shared (facts both are in)}].
 *
 * The cap is applied to the ENTITIES before the map, not to the finished
 * nodes: a dropped name gets no dot, and the links below only ever join dots
 * that are really drawn.
 */
export function buildEntityGraph(view, opts = {}) {
  const entities = view && Array.isArray(view.entities) ? view.entities : [];
  const nodes = orderedEntities(entities, opts).map((e) => ({
    id: `e:${e.id}`,
    entityId: e.id,
    label: e.name,
    group: groupFor(e.kind),
    weight: Array.isArray(e.factIds) ? e.factIds.length : 0,
    // Newest first, as the PC sends them: the "facts behind this dot" panel
    // reads their words by id, a page at a time.
    factIds: Array.isArray(e.factIds) ? e.factIds : [],
    aliases: Array.isArray(e.aliases) ? e.aliases : [],
    also: Array.isArray(e.also) ? e.also : [],
  }));
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

/* ==========================================================================
 * "Facts behind this dot" - the pure half of the panel
 * (docs/GALAXY-PANEL-DESIGN.md sections 2, 3 and 7; JARVIS-API.md section 106).
 *
 * The words are the shared `galaxy_panel*` keys, word for word, in
 * tests/fixtures/galaxy-cases.json (written by tools/gen_galaxy_cases.py).
 * Facts are read by id from `GET /api/memory/used` only - nothing else.
 * ========================================================================== */

/** The shared words. `{count}`, `{n}` and `{total}` are filled by code. */
export const PANEL_WORDS = Object.freeze({
  galaxy_panel: "Facts behind this dot ({count})",
  galaxy_panel_more: "Show 20 more",
  galaxy_panel_showing: "Showing {n} of {total}",
  galaxy_panel_reading: "Reading the facts...",
  galaxy_panel_erased: "Erased. Only the dates are kept.",
  galaxy_panel_forgotten: "Forgotten",
  galaxy_panel_pinned: "Pinned",
  galaxy_panel_hidden: "Hidden. Show memory lists to see these facts.",
  galaxy_panel_empty: "No facts to show.",
  galaxy_panel_failed: "Your PC could not read these facts.",
  galaxy_panel_retry: "Try again",
  galaxy_panel_open: "Open in Memory",
  galaxy_panel_topics_hidden: "{n} hidden by topic settings",
});

/** How many facts one page shows, and the most ids one read may carry. */
export const PANEL_PAGE = 20;
export const PANEL_MAX_IDS = 100;

/** Fills `{count}`, `{n}` and `{total}` in one of the words. */
export function panelWords(key, vars = {}) {
  const t = PANEL_WORDS[key] || "";
  return t.replace(/\{(count|n|total)\}/g, (_, k) => String(vars[k] ?? 0));
}

/**
 * The fact ids of one page of a dot (page 0 is the newest `size`). Never more
 * than 100, and page N+1 starts exactly where page N stopped.
 */
export function factPage(node, page, size = PANEL_PAGE) {
  const ids = node && Array.isArray(node.factIds) ? node.factIds : [];
  const n = Math.max(1, Math.min(PANEL_MAX_IDS, Math.floor(Number(size)) || PANEL_PAGE));
  const p = Math.max(0, Math.floor(Number(page)) || 0);
  return ids.slice(p * n, p * n + n);
}

/**
 * One fact (memory-used.js readUsed's shape) -> how its row reads:
 * `{id, skip, text, erased, forgotten, pinned, created, erasedAt, leftOut}`.
 * An erased fact has no words: its row says the erased line. A fact hidden by
 * a topic setting is `skip` (counted, never shown). A retired fact is marked
 * Forgotten; a pinned one Pinned (only a current fact can be pinned).
 */
export function factRow(fact) {
  const f = fact && typeof fact === "object" ? fact : {};
  const erased = Boolean(f.erasedAt);
  const leftOut = f.leftOut === true && !erased;
  return {
    id: f.id,
    skip: leftOut,
    leftOut,
    erased,
    text: erased ? PANEL_WORDS.galaxy_panel_erased : (leftOut ? "" : String(f.text || "")),
    forgotten: !erased && f.current !== true,
    pinned: !erased && f.pinned === true,
    created: typeof f.created === "number" ? f.created : null,
    erasedAt: erased ? f.erasedAt : null,
  };
}

/** Current facts before forgotten ones, otherwise in the order read (newest first). */
export function sortRows(rows) {
  return rows.map((r, i) => [r, i])
    .sort((a, b) => Number(a[0].forgotten) - Number(b[0].forgotten) || a[1] - b[1])
    .map((x) => x[0]);
}
