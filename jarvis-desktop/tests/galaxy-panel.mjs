/**
 * Galaxy "facts behind this dot" (docs/GALAXY-PANEL-DESIGN.md sections 2, 3, 6
 * and 7; src/galaxy-view.js factPage / factRow, src/galaxy-panel.js, brain.js
 * select()).
 *
 * The first half needs no browser: the shared words against
 * tests/fixtures/galaxy-cases.json (written by tools/gen_galaxy_cases.py), the
 * paging of ids, the rows, and CONTROL checks on the source. The second half
 * needs Playwright and drives the real Brain window.
 *
 * What must hold:
 * - the words are the fixture's, word for word; the heading count is the
 *   dot's own fact_ids.length;
 * - 20 facts at a time, newest first, never more than 100 ids a read, the next
 *   page starting where the last stopped;
 * - current, forgotten (after the current ones), pinned, erased ("Erased. Only
 *   the dates are kept."), a missing id (skipped), an Off-topic fact (never
 *   shown, counted);
 * - hidden lists: no read; an open panel is wiped and says the hidden line;
 * - read-only: no Forget / Erase / Pin here, only "Open in Memory"; no chat,
 *   history, document or graph route; no new <script src>.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  PANEL_MAX_IDS,
  PANEL_PAGE,
  PANEL_WORDS,
  buildEntityGraph,
  factPage,
  factRow,
  panelWords,
  sortRows,
} from "../src/galaxy-view.js";
import { readEntities } from "../src/memory-entities.js";
import { readUsed } from "../src/memory-used.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIX = JSON.parse(readFileSync(join(HERE, "fixtures", "galaxy-cases.json"), "utf8"));
const W = FIX.words;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── Words and pure helpers ────────────────────────────────────────────── */

await check("the words are the shared fixture's, word for word", async () => {
  assert.deepEqual({ ...PANEL_WORDS }, W);
  assert.equal(PANEL_PAGE, FIX.page_size);
  assert.equal(PANEL_MAX_IDS, FIX.max_ids_per_read);
  assert.equal(panelWords("galaxy_panel", { count: 43 }), "Facts behind this dot (43)");
  assert.equal(panelWords("galaxy_panel_showing", { n: 40, total: 43 }), "Showing 40 of 43");
  assert.equal(panelWords("galaxy_panel_topics_hidden", { n: 2 }), "2 hidden by topic settings");
});

await check("pages: 20 ids at a time, the next page starts where the last stopped, never over 100", async () => {
  const ids = Array.from({ length: 250 }, (_, i) => 1000 - i);
  const node = { factIds: ids };
  assert.deepEqual(factPage(node, 0), ids.slice(0, 20));
  assert.deepEqual(factPage(node, 1), ids.slice(20, 40));
  assert.equal(factPage(node, 2)[0], ids[39 + 1]);
  assert.equal(factPage({ factIds: ids.slice(0, 43) }, 2).length, 3);
  assert.deepEqual(factPage({ factIds: ids.slice(0, 43) }, 3), []);
  assert.equal(factPage(node, 0, 500).length, 100, "capped at 100");
  assert.equal(factPage(node, 0, 0).length, 20);
  assert.deepEqual(factPage(null, 0), []);
  const g = buildEntityGraph(readEntities({ entities: [{ id: 1, name: "Priya", kind: "person",
    fact_ids: [9, 8, 7] }] }));
  assert.deepEqual(g.nodes[0].factIds, [9, 8, 7], "the dot carries its fact ids, newest first");
});

await check("rows: current, forgotten after current, pinned, erased, off-topic, missing", async () => {
  const v = readUsed({ facts: [
    { id: 1, text: "Old news", current: false, pinned: false, created: 100, valid_to: 200 },
    { id: 2, text: "Owner likes jazz", current: true, pinned: true, created: 300 },
    { id: 3, text: "", current: false, created: 50, erased_at: 400 },
    { id: 4, text: "", current: true, left_out: true, created: 60 },
    { id: 5, text: "Owner has a cat", current: true, created: 70 },
  ], missing: [99] });
  const rows = v.facts.map(factRow);
  assert.deepEqual(rows.map((r) => r.id), [1, 2, 3, 4, 5]);
  assert.equal(rows[0].forgotten, true);
  assert.equal(rows[1].pinned, true);
  assert.equal(rows[2].erased, true);
  assert.equal(rows[2].text, W.galaxy_panel_erased);
  assert.equal(rows[2].forgotten, false, "erased is its own mark");
  assert.equal(rows[2].created, 50);
  assert.equal(rows[2].erasedAt, 400);
  assert.equal(rows[3].skip, true, "an Off-topic fact is never shown");
  assert.equal(rows[3].text, "");
  assert.deepEqual(sortRows(rows.filter((r) => !r.skip)).map((r) => r.id), [2, 3, 5, 1]);
  assert.deepEqual(v.missing, [99]);
});

/* ── CONTROL: the source ───────────────────────────────────────────────── */

await check("CONTROL: only memory_used is read; no other route, no library, no new script tag", async () => {
  const src = read("src/galaxy-panel.js");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.deepEqual([...code.matchAll(/invoke\(\s*"([a-z_]+)"/g)].map((m) => m[1]), ["memory_used"]);
  assert.doesNotMatch(code, /\/api\/|fetch\(|XMLHttpRequest|localStorage|sessionStorage|indexedDB/);
  for (const bad of ["chat", "history", "document", "graph", "brain_memory_forget", "brain_memory_erase", "pin"]) {
    assert.ok(!new RegExp(`["'\`]\\w*${bad}\\w*["'\`]`, "i").test(code.replace(/"galaxy_panel_[a-z_]*"/g, "")),
      `the panel mentions ${bad}`);
  }
  assert.ok(!/from "https?:|import\(/.test(code), "an outside import");
  const scripts = [...read("src/brain.html").matchAll(/<script[^>]*src="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(scripts, ["brain.js"], "brain.html gained a script src");
  const brain = read("src/brain.js");
  assert.match(brain, /galaxyPanel\.show\(node\)/);
  assert.match(brain, /galaxyPanel\.clear\(\)/);
  assert.match(read("src/galaxy-panel.js"), /from "\.\/galaxy-view\.js"/);
});

/* ── The Brain window ──────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1200, height: 900 };
const NOW = 1790000000;

// Priya: 43 facts, newest first (ids 500 down to 458). Special ones on page 1.
const IDS = Array.from({ length: 43 }, (_, i) => 500 - i);
const ENTITIES = { entities: [
  { id: 1, name: "Priya", kind: "person", also: [], aliases: ["sister"], fact_ids: IDS, facts: 43 },
  { id: 2, name: "Lisbon", kind: "place", also: [], aliases: [], fact_ids: [500, 499, 498], facts: 3 },
], count: 2, limit: 500 };
const USED = {};
IDS.forEach((id, i) => {
  USED[id] = { id, text: `Priya fact number ${i + 1}`, current: true, pinned: false,
    created: NOW - i * 86400, valid_to: null, erased_at: null };
});
USED[499] = { ...USED[499], text: "Priya loves jazz", pinned: true };
USED[498] = { ...USED[498], text: "Priya lived in Leeds", current: false, valid_to: NOW - 5 };
USED[497] = { ...USED[497], text: "", erased_at: NOW - 1000 };
USED[496] = { ...USED[496], text: "SECRET-OFF-TOPIC", left_out: true };
USED[495] = { ...USED[495], text: "Priya likes tea" };
delete USED[494]; // an id with no fact: skipped without an error
const FACTS = { available: true, learning: true, pending: 0, facts: [] };

async function galaxy(extra = {}, brainExtra = {}, setup = {}) {
  const page = await K.open(browser, base, "brain.html",
    { brain: { ...K.BRAIN, memory_entities: ENTITIES, memory_facts: FACTS, ...brainExtra }, ...extra }, SIZE);
  await page.evaluate((s) => Object.assign(window, s), { __usedFacts: USED, ...setup });
  await page.waitForTimeout(300);
  await page.locator("#rail-advanced-toggle").click();
  await page.locator("#tab-galaxy").click();
  await page.waitForTimeout(2200);
  return page;
}
const pick = async (page, name = "Priya") => {
  await page.fill("#graph-search", name);
  await page.waitForTimeout(500);
};
const reads = (page) => page.evaluate(() => window.__usedReads || []);

await check("picking a dot lists its newest 20 facts, with the heading count from the list", async () => {
  const page = await galaxy();
  await pick(page);
  const heading = await page.locator("#galaxy-facts-title").textContent();
  const items = await page.locator("#galaxy-facts-list li").allInnerTexts();
  const count = await page.locator("#galaxy-facts-count").innerText();
  const region = await page.getByRole("region", { name: heading }).count();
  const isList = await page.locator("ul#galaxy-facts-list").count();
  const r = await reads(page);
  const errors = page.__errors;
  await page.close();
  assert.equal(heading, "Facts behind this dot (43)");
  assert.equal(items.length, 18, "20 ids: one with no fact and one Off-topic are not rows");
  assert.deepEqual(r, [IDS.slice(0, 20)], "one read of the first 20 ids");
  assert.equal(count, "Showing 20 of 43");
  assert.equal(region, 1);
  assert.equal(isList, 1);
  assert.match(items[0], /Priya fact number 1\b/);
  assert.deepEqual(errors, []);
});

await check("marks, order, erased line, Off-topic count, and a missing id", async () => {
  const page = await galaxy();
  await pick(page);
  const items = await page.locator("#galaxy-facts-list li").allInnerTexts();
  const note = await page.locator("#galaxy-facts-note").innerText();
  const all = await page.locator("#inspector").innerText();
  await page.close();
  const at = (re) => items.findIndex((t) => re.test(t));
  assert.ok(at(/Priya loves jazz[\s\S]*Pinned/) >= 0, "pinned mark");
  const leeds = at(/Priya lived in Leeds/);
  assert.match(items[leeds], /Forgotten/);
  assert.ok(leeds > at(/Priya likes tea/), "forgotten after current ones");
  assert.equal(leeds, items.length - 1, "forgotten last on the page");
  const erased = at(/Erased\. Only the dates are kept\./);
  assert.ok(erased >= 0);
  assert.match(items[erased], /Erased on /, "the dates are kept");
  assert.equal(note, "1 hidden by topic settings");
  assert.doesNotMatch(all, /SECRET-OFF-TOPIC/);
  assert.ok(!items.some((t) => /Forget\b|Erase the words|Unpin/.test(t)), "an edit button in a read-only panel");
});

await check("only Open in Memory per row; it opens the same About page", async () => {
  const page = await galaxy();
  await pick(page);
  const names = [...new Set(await page.locator("#galaxy-facts-list button").allInnerTexts())];
  const others = await page.locator("#galaxy-facts button").allInnerTexts();
  await page.locator("#galaxy-facts-list li").first().getByRole("button", { name: W.galaxy_panel_open }).click();
  await page.waitForTimeout(600);
  const title = await page.locator("#memory-about-title").innerText();
  const view = await page.locator("#view-memory").isVisible();
  const writes = await page.evaluate(() => window.__calls.filter((c) => /forget|erase|pin|decide|set_/.test(c[0])));
  await page.close();
  assert.deepEqual(names, [W.galaxy_panel_open]);
  assert.ok(others.includes(W.galaxy_panel_more));
  assert.equal(view, true);
  assert.match(title, /Priya/i);
  assert.deepEqual(writes, [], "the panel changed something");
});

await check("Show 20 more: next 20 ids, focus on the first new row, announced politely", async () => {
  const page = await galaxy();
  await pick(page);
  const before = await page.locator("#galaxy-facts-list li").count();
  await page.getByRole("button", { name: W.galaxy_panel_more }).click();
  await page.waitForTimeout(400);
  const after = await page.locator("#galaxy-facts-list li").count();
  const count = await page.locator("#galaxy-facts-count").innerText();
  const live = await page.locator("#galaxy-facts-live").innerText();
  const liveAttr = await page.locator("#galaxy-facts-live").getAttribute("aria-live");
  const focused = await page.evaluate((n) => {
    const li = document.querySelectorAll("#galaxy-facts-list li")[n];
    return li === document.activeElement;
  }, before);
  const r = await reads(page);
  await page.getByRole("button", { name: W.galaxy_panel_more }).click();
  await page.waitForTimeout(400);
  const last = await page.locator("#galaxy-facts-count").innerText();
  const more = await page.getByRole("button", { name: W.galaxy_panel_more }).count();
  const r2 = await reads(page);
  await page.close();
  assert.ok(after > before);
  assert.equal(count, "Showing 40 of 43");
  assert.equal(live, "Showing 40 of 43");
  assert.equal(liveAttr, "polite");
  assert.equal(focused, true);
  assert.deepEqual(r, [IDS.slice(0, 20), IDS.slice(20, 40)]);
  assert.deepEqual(r2[2], IDS.slice(40, 43));
  assert.ok(r2.every((ids) => ids.length <= 100));
  assert.equal(last, "Showing 43 of 43");
  assert.equal(more, 0, "no button when nothing is left");
});

await check("a dot with 3 facts: no Show more; another dot resets the list", async () => {
  const page = await galaxy();
  await pick(page);
  await pick(page, "Lisbon");
  const heading = await page.locator("#galaxy-facts-title").textContent();
  const count = await page.locator("#galaxy-facts-count").innerText();
  const more = await page.getByRole("button", { name: W.galaxy_panel_more }).count();
  const items = await page.locator("#galaxy-facts-list li").count();
  await page.close();
  assert.equal(heading, "Facts behind this dot (3)");
  assert.equal(count, "Showing 3 of 3");
  assert.equal(more, 0);
  assert.ok(items >= 1 && items <= 3);
});

await check("the section closes with the inspector and holds no words afterwards", async () => {
  const page = await galaxy();
  await pick(page);
  await page.locator("#inspector-close").click();
  const hidden = await page.locator("#galaxy-facts").isHidden();
  const html = await page.locator("#galaxy-facts").innerHTML();
  await page.close();
  assert.equal(hidden, true);
  assert.ok(!html.includes("Priya fact number"), "words stayed in the DOM");
});

await check("a failed read says so with Try again, and a retry works", async () => {
  const page = await galaxy();
  await page.evaluate(() => {
    const core = window.__TAURI__.core;
    const real = core.invoke;
    window.__fail = true;
    core.invoke = async (c, a) => {
      if (c === "memory_used" && window.__fail) throw new Error("nope");
      return real(c, a);
    };
  });
  await pick(page);
  const msg = await page.locator("#galaxy-facts-note").innerText();
  await page.evaluate(() => { window.__fail = false; });
  await page.getByRole("button", { name: W.galaxy_panel_retry }).click();
  await page.waitForTimeout(400);
  const items = await page.locator("#galaxy-facts-list li").count();
  const retryLeft = await page.getByRole("button", { name: W.galaxy_panel_retry }).count();
  await page.close();
  assert.match(msg, new RegExp(W.galaxy_panel_failed.replace(/\./g, "\\.")));
  assert.match(msg, new RegExp(W.galaxy_panel_retry));
  assert.ok(items > 0);
  assert.equal(retryLeft, 0, "Try again stayed after it worked");
});

await check("an empty dot says there is nothing to show", async () => {
  const ent = { entities: [{ id: 3, name: "Ghost", kind: "thing", also: [], aliases: [],
    fact_ids: [7001], facts: 1 }], count: 1, limit: 500 };
  const page = await galaxy({}, { memory_entities: ent });
  await pick(page, "Ghost");
  const note = await page.locator("#galaxy-facts-note").innerText();
  await page.close();
  assert.equal(note, W.galaxy_panel_empty);
});

await check("lists hidden while a dot is open: the panel is wiped, says the hidden line, keeps no words", async () => {
  const page = await galaxy();
  await pick(page);
  const had = await page.locator("#galaxy-facts-list li").count();
  await page.evaluate(() => { window.__security.hidden = true; window.__security.revealed = false; });
  await page.getByRole("button", { name: W.galaxy_panel_more }).click();
  await page.waitForTimeout(400);
  const items = await page.locator("#galaxy-facts-list li").count();
  const note = await page.locator("#galaxy-facts-note").innerText();
  const html = await page.content();
  await page.close();
  assert.ok(had > 0);
  assert.equal(items, 0);
  assert.equal(note, W.galaxy_panel_hidden);
  assert.ok(!html.includes("Priya fact number") && !html.includes("Priya loves jazz"), "words stayed on the page");
});

await check("lists hidden from the start: no dot to pick and no words read", async () => {
  const page = await galaxy({ security: { hidden: true } });
  await page.fill("#graph-search", "Priya");
  await page.waitForTimeout(300);
  const r = await reads(page);
  const hidden = await page.locator("#galaxy-facts").isHidden();
  await page.close();
  assert.deepEqual(r, []);
  assert.equal(hidden, true);
});

await browser.close();
await close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe facts behind a dot: read-only, paged, hidden with the memory lists");
process.exit(fails.length ? 1 : 0);
