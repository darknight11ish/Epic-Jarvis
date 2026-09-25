/**
 * "Who is my sister?" on the Brain's Memory tab - memory wave 3, 2026-09-25
 * (JARVIS-API.md section 6 `/api/memory/entities`; src/memory-entities.js,
 * brain.js linkedNode / paintAbout / mergeRow; src-tauri/src/brain/routes.rs,
 * src-tauri/src/lock/rules.rs).
 *
 * What must hold:
 * - under a fact in use, the names the PC linked it to, each opening
 *   "About <name>" - in "Saved automatically" and "What Jarvis knows about
 *   you"; none under a forgotten fact;
 * - "About <name>" lists that entry's facts word for word, read by id
 *   (memory_used), with what the owner calls them - and no summary, and
 *   nothing sent that changes anything;
 * - the "are these the same?" card has its own two answers, never Keep /
 *   Discard / "Both are true", and each sends ONE decide for that one card;
 * - hidden with the other memory lists under Windows Hello (the names are
 *   memory too);
 * - a PC without the route: no names, no error;
 * - CONTROL: the Rust asks for the list and the merge cards, and hides the
 *   list; the phone calls neither (the memory graph stays off the phone).
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  aboutTitle,
  alsoLine,
  calledLine,
  entitiesFor,
  MERGE_NO,
  MERGE_SOURCE,
  MERGE_YES,
  moreLine,
  readEntities,
} from "../src/memory-entities.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const NOW = Math.floor(Date.now() / 1000);
const FACTS = [
  { id: 23, text: "Priya's wedding is in Lisbon next May", source: "auto",
    valid_from: NOW - 3600, valid_to: null, current: true },
  { id: 22, text: "Owner's sister is called Priya", source: "auto",
    valid_from: NOW - 7200, valid_to: null, current: true },
  { id: 21, text: "Owner's manager is called Marta", source: "extracted",
    valid_from: NOW - 900000, valid_to: NOW - 90000, current: false },
];
const ENTITIES = { entities: [
  { id: 5, name: "Priya", kind: "person", also: [], aliases: ["sister"], fact_ids: [23, 22], facts: 2 },
  { id: 6, name: "Lisbon", kind: null, also: [], aliases: [], fact_ids: [23], facts: 1 },
], count: 2, limit: 500 };
const USED = {
  23: { id: 23, text: "Priya's wedding is in Lisbon next May", current: true, pinned: false, erased_at: null },
  22: { id: 22, text: "Owner's sister is called Priya", current: true, pinned: true, erased_at: null },
};
const MERGE_CARD = { id: 77, source: "entity_merge", confidence: null, created: NOW - 60,
  text: "Are these the same person? “Priya Sharma” and “Priya Sharmaa”. Saying yes joins them.",
  flags: [], flags_checked: true, keep_both_ok: false, verbatim: false };
const AUTO = [{ id: 23, text: "Priya's wedding is in Lisbon next May", saved_at: NOW - 3600,
  provenance: "typed", device: "desktop" }];

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the PC's list is read, and anything else shows no names", async () => {
  const v = readEntities(ENTITIES);
  assert.equal(v.available, true);
  assert.deepEqual(entitiesFor(v, 23).map((e) => e.name), ["Lisbon", "Priya"]);
  assert.deepEqual(entitiesFor(v, 22).map((e) => e.name), ["Priya"]);
  assert.deepEqual(entitiesFor(v, 21), []);
  for (const nothing of [null, undefined, {}, { ok: true }, "x", { available: false, why: "old" },
    { entities: [{ id: "5", name: "Priya", fact_ids: [22] }] }]) {
    const n = readEntities(nothing);
    assert.equal(entitiesFor(n, 22).length, 0, JSON.stringify(nothing));
  }
  const hidden = readEntities({ entities: [], hidden: true, hidden_count: 2 });
  assert.equal(hidden.hidden, true);
  assert.equal(hidden.hiddenCount, 2);
  assert.equal(aboutTitle("Priya"), "About Priya");
  assert.equal(calledLine(["sister"]), "You call them: sister");
  assert.equal(calledLine([]), "");
  assert.equal(alsoLine(["Priyaa"]), "Also written: Priyaa");
  assert.equal(moreLine(1), "and 1 older fact not shown");
  assert.equal(MERGE_SOURCE, "entity_merge");
  assert.ok(read("src/brain.html").includes(
    "The facts Jarvis has linked to this name, word for word. Nothing here is written by the model."));
});

/* ── The Brain window ─────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

async function memoryTab(data = {}, setup = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.evaluate((s) => Object.assign(window, s), setup);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(400);
  return page;
}
const brain = (extra = {}) => ({ ...K.BRAIN,
  memory_facts: { available: true, learning: true, facts: FACTS },
  memory_entities: ENTITIES, ...extra });

await check("names under each fact in use, in both lists; none under a forgotten fact", async () => {
  const page = await memoryTab({ brain: brain(), auto: { facts: AUTO } });
  const known = page.locator("#memory-facts .row-item");
  const first = await known.nth(0).locator(".entity-link").allInnerTexts();
  const second = await known.nth(1).locator(".entity-link").allInnerTexts();
  const retired = await known.nth(2).locator(".entity-link").count();
  const auto = await page.locator("#memory-auto-list .row-item .entity-link").allInnerTexts();
  const line = await known.nth(1).locator(".entity-links").innerText();
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(first, ["Lisbon", "Priya"]);
  assert.deepEqual(second, ["Priya"]);
  assert.equal(retired, 0, "a forgotten fact offered a name");
  assert.deepEqual(auto, ["Lisbon", "Priya"]);
  assert.match(line, /^About:/);
  assert.deepEqual(errors, []);
});

await check("\"About Priya\": her facts word for word, read by id; what you call her; nothing sent", async () => {
  const page = await memoryTab({ brain: brain(), auto: { facts: AUTO } }, { __usedFacts: USED });
  assert.equal(await page.locator("#memory-about-card").isVisible(), false, "open before asked");
  await page.locator("#memory-facts .row-item").nth(1).locator(".entity-link",
    { hasText: "Priya" }).click();
  await page.waitForTimeout(400);
  const title = (await page.locator("#memory-about-title").textContent()).trim();
  const text = await page.locator("#memory-about").innerText();
  const rows = await page.locator("#memory-about .row-item").allInnerTexts();
  const buttons = await page.locator("#memory-about button").allInnerTexts();
  const reads = await page.evaluate(() => window.__usedReads);
  const writes = await page.evaluate(() => window.__memoryWrites);
  await page.close();
  assert.equal(title, "About Priya");
  assert.match(text, /You call them: sister/);
  assert.equal(rows.length, 2);
  assert.match(rows[0], /Priya's wedding is in Lisbon next May/);
  assert.match(rows[1], /Owner's sister is called Priya/);
  assert.deepEqual(reads, [[23, 22]], "the facts were not read by id");
  assert.deepEqual(buttons, ["Close"], "About offers something beyond Close");
  assert.deepEqual(writes, []);
});

await check("Close hides it again", async () => {
  const page = await memoryTab({ brain: brain() }, { __usedFacts: USED });
  await page.locator("#memory-facts .entity-link", { hasText: "Priya" }).first().click();
  await page.waitForTimeout(300);
  await page.locator("#memory-about").getByRole("button", { name: "Close" }).click();
  const shown = await page.locator("#memory-about-card").isVisible();
  await page.close();
  assert.equal(shown, false);
});

await check("the \"are these the same?\" card: its own two answers, one decide each", async () => {
  const pending = { available: true, setup: {}, pending: [MERGE_CARD] };
  for (const [label, accept] of [[MERGE_YES, true], [MERGE_NO, false]]) {
    const page = await memoryTab({ brain: brain({ memory_pending: pending }) });
    const card = page.locator("#memory-proposals .row-item").first();
    const buttons = await card.locator("button").allInnerTexts();
    const tag = await card.locator(".row-tag").innerText();
    await card.getByRole("button", { name: label }).click();
    await page.waitForTimeout(300);
    const sent = await page.evaluate(() => window.__memoryWrites);
    await page.close();
    assert.deepEqual(buttons, [MERGE_YES, MERGE_NO]);
    assert.equal(tag.toLowerCase(), "same?");
    assert.deepEqual(sent, [{ cmd: "brain_memory_decide", id: 77, accept }]);
  }
});

await check("on a stale link both answers are greyed", async () => {
  const pending = { available: true, setup: {}, pending: [MERGE_CARD] };
  const page = await memoryTab({ brain: brain({ memory_pending: pending }), link: { stale: true } });
  const card = page.locator("#memory-proposals .row-item").first();
  const yes = await card.getByRole("button", { name: MERGE_YES }).isDisabled();
  const no = await card.getByRole("button", { name: MERGE_NO }).isDisabled();
  await page.close();
  assert.equal(yes && no, true);
});

await check("hidden with the other memory lists until Windows Hello says it is you", async () => {
  const page = await memoryTab({ brain: brain(), security: { hidden: true } });
  const links = await page.locator(".entity-link").count();
  const html = await page.content();
  await page.close();
  assert.equal(links, 0);
  assert.ok(!html.includes("sister"), "a linked word showed while hidden");
});

await check("a PC without the route: no names, no error", async () => {
  const page = await memoryTab({ brain: brain({ memory_entities: undefined }), auto: { facts: AUTO } });
  const links = await page.locator(".entity-link").count();
  const errors = page.__errors;
  await page.close();
  assert.equal(links, 0);
  assert.deepEqual(errors, []);
});

/* ── CONTROL: the Rust, and the phone ─────────────────────────────────── */

await check("CONTROL: the Rust reads the list, asks for merge cards, and hides the list", async () => {
  const routes = read("src-tauri/src/brain/routes.rs");
  assert.match(routes, /\("memory_entities", "\/api\/memory\/entities"\)/);
  assert.match(routes, /"\/api\/memory\/pending\?retire_cards=1&sleep_offer=1&merge_cards=1"/);
  assert.match(read("src-tauri/src/lock/rules.rs"), /\("memory_entities", "entities"\)/);
  assert.match(read("src/brain.js"), /memory: \["memory_facts", "memory_pending", "memory_entities"\]/);
});

await check("CONTROL: the phone calls neither (the memory graph stays off the phone)", async () => {
  const root = join(HERE, "..", "..", "jarvis-client", "app", "src", "main", "java");
  const all = [];
  const walk = (d) => {
    for (const n of readdirSync(d)) {
      const p = join(d, n);
      if (statSync(p).isDirectory()) walk(p);
      else if (p.endsWith(".kt")) all.push(readFileSync(p, "utf8"));
    }
  };
  walk(root);
  const kt = all.join("\n");
  assert.ok(!kt.includes("/api/memory/entities"), "the phone reads the entity list");
  assert.ok(!kt.includes("merge_cards"), "the phone asks for merge cards");
  assert.match(readRepo("docs/ARCHITECTURE.md"), /About <name>/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\n\"Who is my sister?\": names under facts, About lists them word for word, one card per pair");
process.exit(fails.length ? 1 : 0);
