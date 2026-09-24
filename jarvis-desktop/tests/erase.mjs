/**
 * "Erase the words", on the Brain's Memory tab (the owner's decision of
 * 2026-09-24; JARVIS-API.md section 6 and 19; src/auto-learn.js, brain.js
 * eraseFact, src-tauri/src/brain.rs brain_memory_erase).
 *
 * What must hold:
 * - wherever Forget is offered - "Saved automatically" and "What Jarvis
 *   knows about you" - "Erase the words" is offered beside it, and on a
 *   forgotten (retired) fact too, where Forget is not;
 * - it asks first, in both apps' words, and a no sends nothing; a yes sends
 *   ONE brain_memory_erase with that one id, and says "Erased.";
 * - it is held on a stale link, like Forget (greyed here, refused in Rust);
 * - an erased fact is shown as "Erased on <date>", never its words and never
 *   the "[erased]" marker the PC stores, with nothing to press. (The past
 *   view, "what did Jarvis know on...", is drawn by the same renderFacts.)
 *
 * The pure words first, then the Brain window in a real browser on the uikit
 * mock, then CONTROL checks that read the Rust.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  ERASE_CONFIRM,
  ERASE_LABEL,
  ERASED,
  erasedAt,
  erasedLine,
  eraseQuestion,
} from "../src/auto-learn.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const NOW = Math.floor(Date.now() / 1000);
const LIST = [
  { id: 12, text: "Is building Jarvis, a local assistant.", saved_at: NOW - 300,
    provenance: "typed", device: "desktop" },
  { id: 11, text: "Prefers tea to coffee.", saved_at: NOW - 7200,
    provenance: "voice", device: "phone" },
];
/** An erased fact, the way /api/memory/facts sends it: the marker, retired, erased_at. */
const ERASED_ROW = { id: 5, text: "[erased]", source: "auto", valid_from: NOW - 500000,
  valid_to: NOW - 3600, retired_at: NOW - 3600, erased_at: NOW - 3600, current: false };

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the question is both apps' words, word for word, and names the fact", async () => {
  assert.equal(ERASE_LABEL, "Erase the words");
  assert.equal(ERASE_CONFIRM, "Erase the words of this fact from your PC for good? Jarvis keeps " +
    "only the date it was saved, so its history shows something was erased here. This cannot be undone.");
  assert.equal(eraseQuestion({ text: "Prefers tea." }), `${ERASE_CONFIRM}\n\nPrefers tea.`);
  assert.equal(ERASED, "Erased.");
});

await check("only a real erased_at makes a fact erased", async () => {
  assert.equal(erasedAt({ erased_at: 1790000000.5 }), 1790000000.5);
  for (const v of [null, undefined, "1790000000", 0, NaN, true]) {
    assert.equal(erasedAt({ erased_at: v }), null, String(v));
  }
  assert.equal(erasedAt(null), null);
  assert.match(erasedLine(1790000000), /^Erased on \S.*\d{4}$/);
});

/* ── The Brain window ─────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 820 };

async function memoryTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(350);
  return page;
}
const withFacts = (extra) => ({
  ...K.BRAIN,
  memory_facts: { ...K.BRAIN.memory_facts, facts: [...K.BRAIN.memory_facts.facts, ...extra] },
});

await check("Saved automatically: Erase the words sits beside Forget on every row", async () => {
  const page = await memoryTab({ auto: { facts: LIST } });
  const rows = page.locator("#memory-auto-list .row-item");
  const labels = [];
  for (let i = 0; i < await rows.count(); i++) labels.push(await rows.nth(i).locator("button").allInnerTexts());
  await page.close();
  assert.deepEqual(labels, [["Forget", ERASE_LABEL], ["Forget", ERASE_LABEL]]);
});

await check("it asks first; a no sends nothing; a yes sends one erase for that id and says Erased.", async () => {
  const page = await memoryTab({ auto: { facts: LIST } });
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.dismiss(); });
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(200);
  const afterNo = await page.evaluate(() => window.__memoryWrites);
  page.once("dialog", (d) => d.accept());
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(400);
  const afterYes = await page.evaluate(() => window.__memoryWrites);
  const left = await page.locator("#memory-auto-list .row-item").allInnerTexts();
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.equal(asked, eraseQuestion({ text: "Is building Jarvis, a local assistant." }));
  assert.deepEqual(afterNo, [], "dismissing the confirm still erased");
  assert.deepEqual(afterYes, [{ cmd: "brain_memory_erase", id: 12 }]);
  assert.equal(left.length, 1, "the erased fact stayed in Saved automatically");
  assert.match(left[0], /Prefers tea/);
  assert.equal(toast, ERASED);
});

await check("What Jarvis knows: a current fact has Forget and Erase; a forgotten one has Erase only", async () => {
  const page = await memoryTab();
  const current = await page.locator("#memory-facts .row-item").first().locator("button").allInnerTexts();
  const retired = page.locator("#memory-facts .row-item").nth(2);
  const tag = await retired.locator(".row-tag").innerText();
  const retiredButtons = await retired.locator("button").allInnerTexts();
  page.once("dialog", (d) => d.accept());
  await retired.getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__memoryWrites);
  await page.close();
  assert.deepEqual(current, ["Reword", "Forget", ERASE_LABEL]);
  assert.equal(tag.trim().toLowerCase(), "retired");
  assert.deepEqual(retiredButtons, [ERASE_LABEL], "a forgotten fact cannot have its words erased");
  assert.deepEqual(sent, [{ cmd: "brain_memory_erase", id: 4 }]);
});

await check("an erased fact shows 'Erased on <date>' - no words, no marker, nothing to press", async () => {
  const page = await memoryTab({ brain: withFacts([ERASED_ROW]) });
  const row = page.locator("#memory-facts .row-item").nth(3);
  const text = await row.innerText();
  const tag = await row.locator(".row-tag").innerText();
  const buttons = await row.locator("button").count();
  const pane = await page.locator("#memory-facts").innerText();
  await page.close();
  assert.match(text, /Erased on /);
  assert.equal(tag.trim().toLowerCase(), "erased");
  assert.equal(buttons, 0, "an erased fact has nothing left to forget or erase");
  assert.doesNotMatch(pane, /\[erased\]/, "the PC's marker was shown as if it were words");
});

await check("on a stale link Erase is greyed in both lists, like Forget", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, link: { stale: true } });
  const inAuto = await page.locator("#memory-auto-list").getByRole("button", { name: ERASE_LABEL })
    .first().isDisabled();
  const inFacts = await page.locator("#memory-facts").getByRole("button", { name: ERASE_LABEL })
    .first().isDisabled();
  await page.close();
  assert.equal(inAuto, true, "Erase was offered on a stale link (Saved automatically)");
  assert.equal(inFacts, true, "Erase was offered on a stale link (What Jarvis knows)");
});

/* ── CONTROL: the Rust ────────────────────────────────────────────────── */

await check("CONTROL: brain_memory_erase is held on a stale link, sends one id, Brain only", async () => {
  const rs = read("src-tauri/src/brain.rs");
  const f = rs.slice(rs.indexOf("pub async fn brain_memory_erase("));
  const body = f.slice(0, f.indexOf("\n}\n"));
  assert.match(body, /\(app: AppHandle, id: i64\)/, "the command takes more than one id");
  assert.ok(body.indexOf("require_link_live") >= 0
    && body.indexOf("require_link_live") < body.indexOf("post("), "Erase is not held on a stale link");
  assert.match(body, /"\/api\/memory\/erase", serde_json::json!\(\{ "id": id \}\)/);
  assert.match(read("src-tauri/build.rs"), /"brain_memory_erase"/);
  assert.match(read("src-tauri/src/lib.rs"), /brain::brain_memory_erase,/);
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  const holders = sets.filter((s) => s.includes('"allow-brain-memory-erase"'))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders, ["brain-memory"]);
  assert.match(read("src-tauri/src/brain/routes.rs"), /"\/api\/memory\/erase",/,
    "the write-route list the read allowlist is checked against lacks erase");
  assert.match(read("src-tauri/src/hud_bootstrap.js"), /forget\|erase\|/,
    "the HUD page could send an erase");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nerasing a fact's words asks first, sends one id, and never shows the words again");
process.exit(fails.length ? 1 : 0);
