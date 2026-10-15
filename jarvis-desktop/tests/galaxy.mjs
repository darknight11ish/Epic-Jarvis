/**
 * Galaxy: the people and things Jarvis knows about (the owner's choice of
 * 2026-09-28; docs/RESEARCH-AUDIT-2026-09-28.md section 8; src/galaxy-view.js,
 * brain.js renderGraph / select / findInGalaxy; JARVIS-API.md section 71).
 *
 * What must hold:
 * - it is drawn from /api/memory/entities (`memory_entities`), never from
 *   /api/graph - whose fact dots were not hidden with the memory lists
 *   (privacy finding B1) - and the Brain cannot even ask for `graph` now;
 * - a dot per name, its size how many facts name it; two names joined when
 *   a fact names both, worked out on the page from the fact ids;
 * - under Windows Hello the picture is empty, says how many names are
 *   hidden, and offers Show - no name reaches the page;
 * - picking a name says what the list says about it (never a fact's words)
 *   and "About <name>" opens the Memory tab at it;
 * - finding a name (the audit's B3): every match counted, Enter steps
 *   through them, and "No name matches that." when none does;
 * - the legend in plain words, the same five hues and two forms.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  buildEntityGraph,
  findNames,
  findStatus,
  groupFor,
  groupWords,
  isLiveFactAt,
  MAX_NAMES_PER_FACT,
  MAX_RENDERED_NODES,
} from "../src/galaxy-view.js";
import { readEntities } from "../src/memory-entities.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The pure module ───────────────────────────────────────────────────── */

await check("names are joined only when one fact names both, and a line is as strong as what they share", async () => {
  const view = readEntities({ entities: [
    { id: 1, name: "Priya", kind: "person", aliases: ["sister"], also: [], fact_ids: [10, 11, 12] },
    { id: 2, name: "Lisbon", kind: "place", aliases: [], also: [], fact_ids: [10, 11] },
    { id: 3, name: "Miso", kind: "pet", aliases: [], also: [], fact_ids: [12] },
    { id: 4, name: "Leeds", kind: "place", aliases: [], also: [], fact_ids: [40] },
  ] });
  const g = buildEntityGraph(view);
  assert.deepEqual(g.nodes.map((n) => [n.label, n.weight]),
    [["Priya", 3], ["Lisbon", 2], ["Leeds", 1], ["Miso", 1]], "most facts first");
  assert.deepEqual(g.links, [
    { source: "e:1", target: "e:2", shared: 2 },
    { source: "e:1", target: "e:3", shared: 1 },
  ]);
  const crowd = readEntities({ entities: Array.from({ length: MAX_NAMES_PER_FACT + 1 }, (_, i) => (
    { id: i + 1, name: `N${i}`, kind: null, aliases: [], also: [], fact_ids: [7] })) });
  assert.equal(buildEntityGraph(crowd).links.length, 0, "a fact that is a long list joins nothing");
});

/* ── The node cap (task-8 Part B) ─────────────────────────────────────────
 *
 * The picture used to map EVERY name the PC sent: 500 names meant 500 dots
 * and 500 real buttons over them (galaxy-constellation.js). It is capped
 * now, and which names survive is DECIDED rather than arbitrary - the same
 * list draws the same Galaxy, and the names with the most (and most recent)
 * facts win. These four checks are the promise; each one is shown able to
 * fail in the handoff.
 */

await check("at most MAX_RENDERED_NODES names are drawn, the newest are kept, and a shuffled list draws the same picture", async () => {
  // Every name has one fact, so the newest fact id decides - the PC sends
  // fact_ids newest-first (rebuilt/jarvis_memory.py:3765).
  const raw = Array.from({ length: MAX_RENDERED_NODES + 25 }, (_, i) => (
    { id: i + 1, name: `N${String(i).padStart(4, "0")}`, kind: null, aliases: [], also: [],
      fact_ids: [i + 1] }));
  const g = buildEntityGraph(readEntities({ entities: raw }));
  assert.equal(g.nodes.length, MAX_RENDERED_NODES, "the cap was not applied");
  assert.equal(g.nodes[0].label, `N0${MAX_RENDERED_NODES + 24}`, "the newest name is not first");
  assert.ok(!g.nodes.some((n) => n.label === "N0000"), "the oldest name was kept over a newer one");
  // CONTROL: the same names in the opposite order must draw the same picture,
  // or "deterministic" is only true of one array order.
  const shuffled = readEntities({ entities: [...raw].reverse() });
  assert.deepEqual(buildEntityGraph(shuffled).nodes.map((n) => n.id), g.nodes.map((n) => n.id),
    "the picture depends on the order the names arrived in");
  // CONTROL: a list inside the cap is drawn whole - the cap culls, it does
  // not pad, and it does not drop when it does not have to.
  assert.equal(buildEntityGraph(readEntities({ entities: raw.slice(0, 5) })).nodes.length, 5);
  assert.equal(buildEntityGraph(readEntities({ entities: [] })).nodes.length, 0);
});

await check("equal facts: the name with the newer facts comes first, and the fact count still outranks it", async () => {
  // The labels are chosen to run AGAINST the answer: "Zeta" has the newer
  // fact, so a cap that fell back to the label would put "Alpha" first.
  const tie = readEntities({ entities: [
    { id: 1, name: "Alpha", kind: null, aliases: [], also: [], fact_ids: [7] },
    { id: 2, name: "Zeta", kind: null, aliases: [], also: [], fact_ids: [900] },
  ] });
  assert.deepEqual(buildEntityGraph(tie).nodes.map((n) => n.label), ["Zeta", "Alpha"],
    "an older fact id outranked a newer one, or the label decided it");
  // CONTROL: the count is the first key, not recency - three older facts beat
  // one newer, which is what a dot's size already tells the owner.
  const more = readEntities({ entities: [
    { id: 1, name: "Zeta", kind: null, aliases: [], also: [], fact_ids: [1, 2, 3] },
    { id: 2, name: "Alpha", kind: null, aliases: [], also: [], fact_ids: [900] },
  ] });
  assert.deepEqual(buildEntityGraph(more).nodes.map((n) => n.label), ["Zeta", "Alpha"],
    "recency outranked how many facts name the thing");
});

await check("a retired fact sinks below a live one when a caller supplies the rows (a rule the PC's own answer cannot carry)", async () => {
  // /api/memory/entities filters retired facts out at the source
  // (rebuilt/jarvis_memory.py:3731-3732), so no name here can be
  // retired-only. This branch is for a caller that hands in fact rows - the
  // shape /api/memory/facts sends - and it must still order them correctly.
  const view = readEntities({ entities: [
    { id: 1, name: "Retired", kind: null, aliases: [], also: [], fact_ids: [1, 2, 3] },
    { id: 2, name: "Live", kind: null, aliases: [], also: [], fact_ids: [4] },
  ] });
  const at = 1000;
  const rows = [
    { id: 1, current: false, valid_to: 900 },
    { id: 2, current: false, valid_to: 900 },
    { id: 3, current: false, valid_to: 900 },
    { id: 4, current: true, valid_to: null },
  ];
  assert.deepEqual(buildEntityGraph(view, { facts: rows, asOfSeconds: at }).nodes.map((n) => n.label),
    ["Live", "Retired"], "a name whose three facts are all retired outranked a name with one live fact");
  // The rule itself, on valid_to alone - brain.js's own test (brain.js:2887).
  assert.equal(isLiveFactAt({ valid_to: 900 }, at), false, "valid_to in the past is not retired");
  assert.equal(isLiveFactAt({ valid_to: 2000 }, at), true, "valid_to in the future is not live");
  assert.equal(isLiveFactAt({ valid_to: null }, at), true, "no valid_to is not live");
  // CONTROL: the same rows, all live, put the three-fact name back on top -
  // so the check above is measuring the dates and not the names or the cap.
  const live = rows.map((f) => ({ id: f.id, valid_to: null }));
  assert.deepEqual(buildEntityGraph(view, { facts: live, asOfSeconds: at }).nodes.map((n) => n.label),
    ["Retired", "Live"], "the live-row control did not flip the order back");
});

await check("CONTROL: the retired test has not drifted between the fact rows and the cap", async () => {
  // brain.js renders every fact row with this expression; galaxy-view.js's
  // isLiveFactAt decides the cap with it. One file changing what "retired"
  // means while the other does not would draw a name the fact list calls
  // gone, or drop one it calls live.
  const flat = (src) => src.replace(/\s+/g, " ");
  assert.ok(flat(read("src/brain.js")).includes(
    "f.valid_to === null || f.valid_to === undefined || Number(f.valid_to) > asOfSeconds"),
    "brain.js's fact-row retired test moved or changed");
  assert.ok(flat(read("src/galaxy-view.js")).includes(
    "to === null || to === undefined || Number(to) > asOfSeconds"),
    "galaxy-view.js's isLiveFactAt no longer matches brain.js");
});

await check("kinds, words and finding a name", async () => {
  assert.equal(groupFor("person"), "person");
  assert.equal(groupFor(null), "other");
  assert.equal(groupFor("spaceship"), "other");
  assert.equal(groupWords("organisation"), "organisations");
  assert.equal(groupWords("other", { plural: false }), "not sure what kind");
  const nodes = [{ label: "Priya", aliases: ["sister"], also: [] },
                 { label: "Marta", aliases: ["boss"], also: ["Marta K"] }];
  assert.deepEqual(findNames(nodes, "SIST").map((n) => n.label), ["Priya"]);
  assert.deepEqual(findNames(nodes, "marta k").map((n) => n.label), ["Marta"]);
  assert.deepEqual(findNames(nodes, "zzz"), []);
  assert.equal(findStatus(0, 0), "No name matches that.");
  assert.equal(findStatus(0, 1), "1 match.");
  assert.equal(findStatus(1, 4), "2 of 4. Press Enter for the next.");
});

/* ── The Brain window, in a real browser ────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1200, height: 800 };
const ENTITIES = K.makeEntities();
const FACTS = { available: true, learning: true, pending: 0, facts: [
  { id: 10, text: "Priya's wedding is in Lisbon next May", source: "auto",
    valid_from: 1790000000, valid_to: null, current: true }] };

async function galaxy(extra = {}, brainExtra = {}) {
  const page = await K.open(browser, base, "brain.html",
    { brain: { ...K.BRAIN, memory_entities: ENTITIES, memory_facts: FACTS, ...brainExtra }, ...extra }, SIZE);
  await page.waitForTimeout(400);
  await page.locator("#rail-advanced-toggle").click();
  await page.locator("#tab-galaxy").click();
  await page.waitForTimeout(2200);
  return page;
}

await check("Galaxy reads the people-and-things list, never the old graph, and counts names and links", async () => {
  const page = await galaxy();
  const asked = await page.evaluate(() => window.__calls.filter((c) => c[0] === "brain_read")
    .flatMap((c) => c[1].sections));
  const stat = await page.locator("#graph-stat").innerText();
  const legend = await page.locator("#legend").innerText();
  const empty = await page.locator("#graph-empty").isHidden();
  const errors = page.__errors;
  await page.close();
  assert.ok(asked.includes("memory_entities"));
  assert.ok(!asked.includes("graph"), "the old graph was asked for");
  assert.match(stat, new RegExp(`^${ENTITIES.entities.length} names · \\d+ links$`), stat);
  for (const w of ["people", "pets", "places", "organisations", "projects", "things", "not sure what kind"]) {
    assert.ok(legend.includes(w), `legend says ${w}: ${legend}`);
  }
  assert.equal(empty, true);
  assert.deepEqual(errors, []);
});

await check("finding a name counts every match, steps with Enter, and says when nothing matches (B3)", async () => {
  const page = await galaxy();
  await page.fill("#graph-search", "sister");
  await page.waitForTimeout(200);
  const one = await page.locator("#graph-find").innerText();
  const picked = await page.locator("#node-label").innerText();
  await page.fill("#graph-search", "Name 1");
  await page.waitForTimeout(200);
  const many = await page.locator("#graph-find").innerText();
  const first = await page.locator("#node-label").innerText();
  await page.locator("#graph-search").press("Enter");
  const next = await page.locator("#graph-find").innerText();
  const second = await page.locator("#node-label").innerText();
  await page.locator("#graph-search").press("Shift+Enter");
  const back = await page.locator("#node-label").innerText();
  await page.fill("#graph-search", "zzz-nobody");
  await page.waitForTimeout(200);
  const none = await page.locator("#graph-find").innerText();
  const live = await page.locator("#graph-find").getAttribute("aria-live");
  await page.close();
  assert.equal(one, "1 match.");
  assert.equal(picked, "Priya", "found by what the owner calls her");
  assert.match(many, /^1 of \d+\. Press Enter for the next\.$/);
  assert.match(next, /^2 of \d+\./);
  assert.notEqual(first, second);
  assert.equal(back, first);
  assert.equal(none, "No name matches that.");
  assert.equal(live, "polite");
});

/* ── "Nothing is drawn only on the canvas" ────────────────────────────────
 *
 * The project's own rule (docs/HANDOFF-DESKTOP-2026-10-09.md item 2): a thing
 * that exists only as pixels on the canvas is a thing a keyboard user and a
 * screen reader cannot reach. The Galaxy's answer is that every dot NAMES a
 * person or thing, and the search box finds any name in the list - so the
 * accessible path to every node is `#graph-search`, and the canvas is a view of
 * it rather than the only way in.
 *
 * That was a promise in comments. These two checks make it a fact the build
 * tests: one at the data level, one against the running window.
 */

await check("every dot the graph draws has a name a search can find (the canvas is not the only way in)", async () => {
  // Pure: a node with a blank label, or one whose label the search would not
  // match, is a dot that exists only as pixels.
  const g = buildEntityGraph(readEntities(ENTITIES));
  assert.ok(g.nodes.length >= ENTITIES.entities.length, `only ${g.nodes.length} nodes for ${ENTITIES.entities.length} names`);
  for (const node of g.nodes) {
    assert.ok(typeof node.label === "string" && node.label.trim() !== "",
      `a node with no name reaches the canvas: ${JSON.stringify(node.id)}`);
    assert.equal(findNames([node], node.label).length, 1,
      `"${node.label}" does not find itself, so its dot cannot be reached by name`);
    // The owner's own word for it counts too ("sister" -> Priya), which is what
    // makes the search usable rather than merely present.
    for (const alias of [...(node.also || []), ...(node.aliases || [])]) {
      assert.equal(findNames([node], alias).length, 1, `"${alias}" does not find "${node.label}"`);
    }
  }
  // CONTROL: the search is not matching everything - a name nobody has must
  // come back empty, or the assertions above would pass on a broken filter.
  assert.deepEqual(findNames(g.nodes, "zzz-nobody"), []);
});

await check("every dot's name is reachable in the running window, through the box the keyboard uses", async () => {
  const page = await galaxy();
  // How many dots the window actually drew. The pure check above proves every
  // node in the graph is findable, so this number plus that fact is the whole
  // guarantee: N drawn, N findable, therefore no dot is canvas-only.
  const stat = await page.locator("#graph-stat").innerText();
  const drawn = Number(/^(\d+) names? · /.exec(stat)?.[1]);
  assert.equal(drawn, ENTITIES.entities.length,
    `the window drew ${drawn} dots for ${ENTITIES.entities.length} names - a name with no dot, or a dot with no name`);
  // A real type-and-read round trip over the names that are easiest to get
  // wrong: one with a space, a short one, one with no kind at all, one that is
  // only an alias, and a generated one.
  for (const name of ["Priya", "Lisbon", "Miso", "Initech", "Marta", "Jarvis app", "Blue bike", "Okafor", "Name 1", "Name 31"]) {
    await page.fill("#graph-search", name);
    await page.waitForTimeout(140);
    const line = await page.locator("#graph-find").innerText();
    const picked = await page.locator("#node-label").innerText();
    assert.doesNotMatch(line, /No name matches that/, `"${name}" is drawn on the canvas but the search cannot find it`);
    assert.ok(picked.trim() !== "", `"${name}" found nothing to show in the inspector`);
  }
  // And the owner's own word for it, which is the search's reason for existing:
  // the alias must still reach the person, not only the exact name.
  await page.fill("#graph-search", "sister");
  await page.waitForTimeout(140);
  assert.equal(await page.locator("#node-label").innerText(), "Priya");
  await page.close();
});

await check("the running window draws the cap, and says how many names it left out", async () => {
  const big = K.makeEntities(20);            // 648 names, over the cap
  assert.ok(big.entities.length > MAX_RENDERED_NODES, "the fixture does not reach the cap");
  const page = await galaxy({}, { memory_entities: big });
  const stat = await page.locator("#graph-stat").innerText();
  const buttons = await page.locator("#graph-overlay .galaxy-node-button").count();
  const dots = await page.locator("#graph-svg circle.galaxy-node-shape").count();
  const errors = page.__errors;
  await page.close();
  // The count line is the honest half: "240 names" over a 648-name list would
  // read as "these are all the names Jarvis knows".
  assert.match(stat, new RegExp(`^${MAX_RENDERED_NODES} of ${big.entities.length} names · `), stat);
  assert.equal(buttons, MAX_RENDERED_NODES, `the window drew ${buttons} buttons`);
  assert.equal(dots, buttons, "a dot with no button, or a button with no dot");
  assert.deepEqual(errors, []);
});

await check("a picked name says what the list says - never a fact's words - and About opens the Memory tab at it", async () => {
  const page = await galaxy();
  await page.fill("#graph-search", "Priya");
  await page.waitForTimeout(200);
  const kind = await page.locator("#node-kind").innerText();
  const facts = await page.locator("#node-facts").innerText();
  const panel = await page.locator("#inspector").innerText();
  const links = await page.locator("#node-links li").allInnerTexts();
  await page.locator("#node-actions").getByRole("button", { name: "About Priya" }).click();
  await page.waitForTimeout(600);
  const view = await page.locator("#view-memory").isVisible();
  const about = await page.locator("#memory-about-card").isVisible();
  const title = await page.locator("#memory-about-title").innerText();
  const used = await page.evaluate(() => window.__calls.filter((c) => c[0] === "memory_used").map((c) => c[1].ids));
  await page.close();
  assert.equal(kind.toLowerCase(), "person", "shown in capitals by CSS only");
  assert.match(facts, /Facts that name it\s+5/);
  assert.match(facts, /You call it\s+sister/);
  assert.doesNotMatch(panel, /wedding/, "a fact's words reached the Galaxy panel");
  assert.ok(links.some((l) => /Lisbon · 1 shared fact/.test(l)), links.join(" | "));
  assert.equal(view, true);
  assert.equal(about, true);
  assert.match(title, /Priya/i);
  assert.deepEqual(used[0], [10, 11, 12, 13, 14], "About reads Priya's facts by id, as on the Memory tab");
});

await check("hidden under Windows Hello: no name on the page, how many are hidden, and Show", async () => {
  const page = await galaxy({ security: { hidden: true } });
  const text = await page.locator("#graph-empty").innerText();
  const visible = await page.locator("#graph-empty").isVisible();
  const show = await page.locator("#graph-empty").getByRole("button", { name: "Show" }).count();
  const html = await page.content();
  await page.fill("#graph-search", "Priya");
  await page.waitForTimeout(200);
  const inspector = await page.locator("#inspector").isHidden();
  await page.close();
  assert.equal(visible, true);
  assert.match(text, new RegExp(`${ENTITIES.entities.length} names, hidden until Windows Hello`));
  assert.equal(show, 1);
  assert.ok(!html.includes("Lisbon") && !html.includes("Initech"), "a name reached the page");
  assert.equal(inspector, true);
});

await check("no names yet, and an older PC, each say so in words", async () => {
  let page = await galaxy({}, { memory_entities: { entities: [], count: 0, limit: 500 } });
  const empty = await page.locator("#graph-empty-text").innerText();
  await page.close();
  assert.match(empty, /No people or things yet/);
  page = await galaxy({}, { memory_entities: { available: false, error: "HTTP 404", read: "absent" } });
  const old = await page.locator("#graph-empty-text").innerText();
  await page.close();
  assert.ok(old.trim().length > 10, `said "${old}"`);
});

await check("CONTROL: the Brain cannot read /api/graph, and Galaxy asks for memory_entities", async () => {
  const routes = read("src-tauri/src/brain/routes.rs");
  const table = routes.slice(routes.indexOf("const READ_ROUTES"), routes.indexOf("];"));
  assert.doesNotMatch(table, /"\/api\/graph"/);
  assert.match(routes, /fn the_graph_is_not_readable_and_every_memory_list_is_private/);
  const brain = read("src/brain.js");
  assert.match(brain, /galaxy: \["memory_entities"\]/);
  assert.doesNotMatch(brain, /state\.data\.graph/);
});

await browser.close();
await close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe people-and-things Galaxy holds");
process.exit(fails.length ? 1 : 0);
