/**
 * "History of this fact" on the Brain's Memory tab (the owner's choice of
 * 2026-09-28; JARVIS-API.md section 71; src/fact-history.js, brain.js
 * toggleFactHistory, src-tauri/src/brain/fact_history.rs).
 *
 * What must hold:
 * - a fact with another wording on the list has a History button; one with
 *   none does not;
 * - History opens every version under the row, oldest first, the one
 *   opened marked, the changed words marked with <del> and <ins> (not by
 *   colour alone);
 * - an ERASED version shows no words, and no diff is drawn against it, so
 *   erased words cannot come back even as "removed";
 * - hidden under Windows Hello like every memory list; an older PC says
 *   plainly it cannot show it; nothing is changed by looking;
 * - diffWords (copied from Hindsight, MIT) gives back both texts exactly;
 * - CONTROL: the Rust command is the Brain's only, in the memory set, and
 *   the copied code's notice is in THIRD-PARTY-NOTICES.txt.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  diffWords,
  hasOtherVersions,
  readFactHistory,
  versionLine,
} from "../src/fact-history.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const T = 1790000000;
const FACTS = [
  { id: 7, text: "Owner's dentist is Dr Okafor on Station Road", source: "edited",
    valid_from: T + 200, created: T + 200, valid_to: null, retired_at: null, retired_by: null, current: true },
  { id: 6, text: "", source: "edited", erased_at: T + 300,
    valid_from: T + 100, created: T + 100, valid_to: T + 200, retired_at: T + 200, retired_by: 7, current: false },
  { id: 5, text: "", source: "auto", erased_at: T + 300,
    valid_from: T, created: T, valid_to: T + 100, retired_at: T + 100, retired_by: 6, current: false },
  { id: 3, text: "Owner lives in Leeds", source: "extracted",
    valid_from: T + 50, created: T + 50, valid_to: null, retired_at: null, retired_by: null, current: true },
  { id: 2, text: "Owner lives in York", source: "user",
    valid_from: T - 50, created: T - 50, valid_to: T + 50, retired_at: T + 50, retired_by: 3, current: false },
  { id: 1, text: "Owner likes green tea", source: "auto",
    valid_from: T - 90, created: T - 90, valid_to: null, retired_at: null, retired_by: null, current: true },
];

/* ── The pure module ───────────────────────────────────────────────────── */

await check("diffWords gives back both wordings exactly, and marks what changed", async () => {
  const a = "Owner lives in York  with two cats";
  const b = "Owner now lives in Leeds with two cats";
  const parts = diffWords(a, b);
  const as = parts.filter((p) => p.type !== "added").map((p) => p.text).join("");
  const bs = parts.filter((p) => p.type !== "removed").map((p) => p.text).join("");
  assert.equal(as, a);
  assert.equal(bs, b);
  assert.deepEqual(parts.filter((p) => p.type === "removed" && p.text.trim()).map((p) => p.text), ["York"]);
  assert.deepEqual(parts.filter((p) => p.type === "added" && p.text.trim()).map((p) => p.text), ["now", "Leeds"]);
  assert.ok(diffWords("same words", "same words").every((p) => p.type === "same"));
});

await check("the answer is read defensively; an erased version's words are blanked here too", async () => {
  const v = readFactHistory({ id: 6, versions: [
    { id: 5, text: "Owner's PIN is 4821", erased_at: T + 300, this: false },
    { id: 6, text: "Owner lives in Leeds", this: true, current: true },
    { id: "x", text: "no id" }] });
  assert.equal(v.versions.length, 2);
  assert.equal(v.versions[0].text, "", "an erased version never keeps words");
  assert.equal(v.versions[1].isThis, true);
  assert.equal(readFactHistory({ available: false, why: "update" }).available, false);
  assert.equal(readFactHistory({ hidden: true, hidden_count: 3 }).hiddenCount, 3);
  assert.match(versionLine(v.versions[0], 0), /^Version 1 · words erased /);
  assert.match(versionLine(v.versions[1], 1), /in use now · the one you opened$/);
});

await check("History is offered only where there is another wording on the list", async () => {
  assert.equal(hasOtherVersions(FACTS[0], FACTS), true, "replaced something (6 names it)");
  assert.equal(hasOtherVersions(FACTS[4], FACTS), true, "was replaced");
  assert.equal(hasOtherVersions(FACTS[5], FACTS), false, "never reworded");
});

/* ── The Brain window, in a real browser ────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1100, height: 900 };
const BRAIN = { ...K.BRAIN, memory_facts: { available: true, learning: true, pending: 0, facts: FACTS } };

async function memoryTab(extra = {}) {
  const page = await K.open(browser, base, "brain.html", { brain: BRAIN, ...extra }, SIZE);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(300);
  return page;
}
const factRow = (page, text) => page.locator("#memory-facts .row-item", { hasText: text });

await check("History opens every version under the row, oldest first, the changed words marked", async () => {
  const page = await memoryTab();
  const tea = await factRow(page, "green tea").getByRole("button", { name: "History" }).count();
  await factRow(page, "Leeds").getByRole("button", { name: "History" }).click();
  await page.waitForTimeout(300);
  const box = page.locator("#fact-history");
  const lines = await box.locator(".fact-history-line").allInnerTexts();
  const del = await box.locator("del").allInnerTexts();
  const ins = await box.locator("ins").allInnerTexts();
  const expanded = await factRow(page, "Leeds").getByRole("button", { name: "Close history" })
    .getAttribute("aria-expanded");
  const writes = await page.evaluate(() => window.__calls.map((c) => c[0])
    .filter((c) => /forget|erase|edit|decide|_pin$|_share$/.test(c)));
  await box.getByRole("button", { name: "Close" }).click();
  await page.waitForTimeout(200);
  const closed = await page.locator("#fact-history").count();
  await page.close();
  assert.equal(tea, 0, "a fact never reworded offers no history");
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^Version 1 .* true until /);
  assert.match(lines[1], /^Version 2 .* in use now · the one you opened$/);
  assert.deepEqual(del.map((t) => t.trim()).filter(Boolean), ["York"]);
  assert.deepEqual(ins.map((t) => t.trim()).filter(Boolean), ["Leeds"]);
  assert.equal(expanded, "true");
  assert.deepEqual(writes, [], "looking changes nothing");
  assert.equal(closed, 0);
});

await check("erased versions show no words and no diff is drawn against them", async () => {
  const page = await memoryTab();
  await factRow(page, "Dr Okafor").getByRole("button", { name: "History" }).click();
  await page.waitForTimeout(300);
  const box = page.locator("#fact-history");
  const words = await box.locator(".fact-history-words").allInnerTexts();
  const marks = await box.locator("del, ins").count();
  const text = await box.innerText();
  await page.close();
  assert.deepEqual(words, ["The words were erased.", "The words were erased.",
    "Owner's dentist is Dr Okafor on Station Road"]);
  assert.equal(marks, 0, "the newest wording is shown plain after an erased one");
  assert.doesNotMatch(text, /\[erased\]/);
});

await check("hidden under Windows Hello, and an older PC says so plainly", async () => {
  // Hidden: the facts list itself is hidden, so there is nothing to open.
  let page = await memoryTab({ security: { hidden: true } });
  const buttons = await page.locator("#memory-facts").getByRole("button", { name: "History" }).count();
  await page.close();
  assert.equal(buttons, 0);
  page = await memoryTab();
  await page.evaluate(() => { window.__factHistoryMissing = true; });
  await factRow(page, "Leeds").getByRole("button", { name: "History" }).click();
  await page.waitForTimeout(300);
  const said = await page.locator("#fact-history").innerText();
  await page.close();
  assert.match(said, /cannot show a fact's history yet - run apply-patches\.ps1/);
});

await check("CONTROL: the Brain's only, in the memory set; the copied code's notice is kept", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  const holders = sets.filter((s) => s.includes("\"allow-brain-fact-history\""))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders, ["brain-memory"]);
  assert.match(read("src-tauri/build.rs"), /"brain_fact_history"/);
  assert.match(read("src-tauri/src/lib.rs"), /brain::fact_history::brain_fact_history,/);
  const rust = read("src-tauri/src/brain/fact_history.rs");
  assert.match(rust, /private_hidden\(&app\)[\s\S]*redact_fact_history/);
  const notices = readRepo("THIRD-PARTY-NOTICES.txt");
  assert.match(notices, /Hindsight[\s\S]*diffWords[\s\S]*jarvis-desktop\/src\/fact-history\.js/);
  assert.match(notices, /supermemory[\s\S]*version-chain\.ts[\s\S]*jarvis_memory\.py/);
  assert.match(read("src/fact-history.js"), /MIT License, Copyright \(c\) 2025 Vectorize AI, Inc\./);
});

await browser.close();
await close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nHistory of this fact holds");
process.exit(fails.length ? 1 : 0);
