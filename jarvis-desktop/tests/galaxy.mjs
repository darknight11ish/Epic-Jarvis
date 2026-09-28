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
  MAX_NAMES_PER_FACT,
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
