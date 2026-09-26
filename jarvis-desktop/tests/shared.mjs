/**
 * "Between us", on the Brain's Memory tab (the owner's decision of
 * 2026-09-27; JARVIS-API.md section 44 `/api/memory/shared`;
 * src/memory-shared.js, brain.js paintShared / shareButton,
 * src-tauri/src/brain/shared.rs).
 *
 * What must hold:
 * - the section says what it is in the words both apps use, each tagged
 *   fact listed word for word, with a Forget (the ordinary Forget, not a
 *   new one);
 * - wherever a current fact has Pin - "Saved automatically" and "What
 *   Jarvis knows about you" - it also has "Between us" (or "Not between
 *   us", when it is tagged); a forgotten fact has neither;
 * - a tap sends ONE brain_memory_share with that one id and asks nothing
 *   first (no card, no confirm: the owner's own tap, like Pin);
 * - held on a stale link (greyed here, refused in Rust);
 * - hidden with the other memory lists under Windows Hello;
 * - a PC without the list: no "Between us" buttons, and the section says so.
 *
 * The pure words first, then the Brain window in a real browser on the uikit
 * mock, then CONTROL checks that read the Rust.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  isShared,
  readShared,
  SHARE_LABEL,
  SHARED,
  SHARED_DETAIL,
  SHARED_EMPTY,
  SHARED_MISSING,
  SHARED_TITLE,
  UNSHARE_LABEL,
  UNSHARED,
} from "../src/memory-shared.js";
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
  { id: 11, text: "We call the printer 'the beast'", saved_at: NOW - 7200,
    provenance: "voice", device: "phone" },
];
const SHARED_11 = { facts: [{ id: 11, text: "We call the printer 'the beast'", created: NOW - 60 }] };

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the section's words are both apps' words, word for word", async () => {
  assert.equal(SHARED_TITLE, "Between us");
  assert.equal(SHARE_LABEL, "Between us");
  assert.equal(UNSHARE_LABEL, "Not between us");
  const html = read("src/brain.html");
  assert.match(html, /<h2>Between us<\/h2>/);
  assert.ok(html.includes(`>${SHARED_DETAIL}</p>`));
});

await check("the PC's answer is read, and anything else is not a list", async () => {
  const v = readShared({ facts: [{ id: 3, text: "We call it the beast" },
    { id: "4", text: "no whole-number id" }] });
  assert.equal(v.available, true);
  assert.deepEqual(v.facts, [{ id: 3, text: "We call it the beast", created: null }]);
  assert.ok(isShared(v, 3) && !isShared(v, 4));
  for (const nothing of [null, undefined, {}, { ok: true }, "x"]) {
    const n = readShared(nothing);
    assert.equal(n.available, false, JSON.stringify(nothing));
    assert.equal(n.why, SHARED_MISSING);
    assert.equal(n.ids.size, 0);
  }
  const hidden = readShared({ facts: [], hidden: true, hidden_count: 2 });
  assert.equal(hidden.hidden, true);
  assert.equal(hidden.hiddenCount, 2);
});

/* ── The Brain window ─────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 820 };

async function memoryTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(400);
  return page;
}

await check("the section: title, its one line, each tagged fact with Forget", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, shared: SHARED_11 });
  const card = page.locator("#memory-shared-card");
  const title = (await card.locator("h2").textContent()).trim();
  const note = await card.locator(".note").first().innerText();
  const rows = await card.locator(".row-item").allInnerTexts();
  const buttons = await card.locator(".row-item button").allInnerTexts();
  await page.close();
  assert.equal(title, SHARED_TITLE);
  assert.equal(note, SHARED_DETAIL);
  assert.equal(rows.length, 1);
  assert.match(rows[0], /the beast/);
  assert.deepEqual(buttons, [UNSHARE_LABEL, "Forget"]);
});

await check("\"Between us\" sits with Forget on every current fact, in both lists; none on a forgotten one", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, shared: SHARED_11 });
  const auto = [];
  const rows = page.locator("#memory-auto-list .row-item");
  for (let i = 0; i < await rows.count(); i++) auto.push(await rows.nth(i).locator("button").allInnerTexts());
  const current = await page.locator("#memory-facts .row-item").first().locator("button").allInnerTexts();
  const retired = await page.locator("#memory-facts .row-item").nth(2).locator("button").allInnerTexts();
  await page.close();
  assert.deepEqual(auto, [[SHARE_LABEL, "Forget", "Erase the words"],
    [UNSHARE_LABEL, "Forget", "Erase the words"]]);
  assert.ok(current.includes(SHARE_LABEL), current);
  assert.ok(!retired.includes(SHARE_LABEL) && !retired.includes(UNSHARE_LABEL),
    `a forgotten fact offered ${retired}`);
});

await check("a tap sends ONE tag for that id, asks nothing, and the list shows it", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, shared: SHARED_11 });
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: SHARE_LABEL }).click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__memoryWrites);
  const listed = await page.locator("#memory-shared .row-item").allInnerTexts();
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.equal(asked, false, "tagging asked a question - it is the owner's own tap");
  assert.deepEqual(sent, [{ cmd: "brain_memory_share", id: 12, shared: true }]);
  assert.equal(listed.length, 2);
  assert.match(listed[1], /Is building Jarvis/);
  assert.equal(toast, SHARED);
});

await check("untagging sends one untag, and the fact leaves the list; the fact itself stays", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, shared: SHARED_11 });
  await page.locator("#memory-shared").getByRole("button", { name: UNSHARE_LABEL }).click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__memoryWrites);
  const empty = await page.locator("#memory-shared").innerText();
  const toast = await page.locator("#toast").innerText();
  const autoTexts = await page.locator("#memory-auto-list .row-item").allInnerTexts();
  await page.close();
  assert.deepEqual(sent, [{ cmd: "brain_memory_share", id: 11, shared: false }]);
  assert.equal(empty.trim(), SHARED_EMPTY);
  assert.equal(toast, UNSHARED);
  assert.ok(autoTexts.some((t) => t.includes("the beast")), "the fact's own words are untouched");
});

await check("Forget in the section sends the ordinary Forget for that id, asked the ordinary way", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, shared: SHARED_11 });
  const asked = [];
  page.once("dialog", (d) => { asked.push(d.message()); d.accept(); });
  await page.locator("#memory-shared").getByRole("button", { name: "Forget" }).click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__memoryWrites);
  const autoList = await page.locator("#memory-auto-list .row-item").count();
  await page.close();
  // The mock does not simulate a forgotten fact leaving "Between us" (nor
  // "Always keep in mind") - that is the real backend's current_facts()
  // filter (bitemporal.patch), proved against real SQLite in
  // backend/test_between_us.py, not this mock.
  assert.match(asked[0], /^Stop recalling this\?\n\nWe call the printer/);
  assert.deepEqual(sent, [{ cmd: "brain_memory_forget", id: 11 }]);
  assert.equal(autoList, 1, "left Saved automatically too, like any other Forget");
});

await check("on a stale link \"Between us\" is greyed, like Pin", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, shared: SHARED_11, link: { stale: true } });
  const tag = await page.locator("#memory-auto-list").getByRole("button", { name: SHARE_LABEL })
    .first().isDisabled();
  const untag = await page.locator("#memory-shared").getByRole("button", { name: UNSHARE_LABEL })
    .isDisabled();
  await page.close();
  assert.equal(tag, true, "\"Between us\" was offered on a stale link");
  assert.equal(untag, true, "\"Not between us\" was offered on a stale link");
});

await check("hidden with the other memory lists until Windows Hello says it is you", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, shared: SHARED_11,
    security: { hidden: true } });
  const text = await page.locator("#memory-shared").innerText();
  await page.close();
  assert.doesNotMatch(text, /beast/);
  assert.match(text, /hidden until Windows Hello/);
});

await check("a PC without the list: the section says so, and no fact offers \"Between us\"", async () => {
  const page = await memoryTab({ auto: { facts: LIST } });
  const text = await page.locator("#memory-shared").innerText();
  const buttons = await page.getByRole("button", { name: SHARE_LABEL, exact: true }).count();
  await page.close();
  assert.equal(text.trim(), SHARED_MISSING);
  assert.equal(buttons, 0);
});

/* ── CONTROL: the Rust ────────────────────────────────────────────────── */

await check("CONTROL: brain_memory_share is held on a stale link, sends one id and one answer, Brain only", async () => {
  const rs = read("src-tauri/src/brain/shared.rs");
  const f = rs.slice(rs.indexOf("pub async fn brain_memory_share("));
  const body = f.slice(0, f.indexOf("\n}\n"));
  assert.match(body, /id: i64,\s*shared: bool,/);
  assert.ok(body.indexOf("require_link_live") >= 0
    && body.indexOf("require_link_live") < body.indexOf(".post("), "share is not held on a stale link");
  assert.match(rs, /serde_json::json!\(\{ "id": id, "shared": shared \}\)/);
  const list = rs.slice(rs.indexOf("pub async fn brain_memory_shared("));
  assert.match(list.slice(0, list.indexOf("\n}\n")), /private_hidden/,
    "the list is not hidden with the other memory lists");
  for (const cmd of ["brain_memory_shared", "brain_memory_share"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::shared::${cmd},`));
    const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-memory"], cmd);
  }
  assert.match(read("src-tauri/src/brain/routes.rs"), /"\/api\/memory\/shared",/,
    "the write-route list the read allowlist is checked against lacks the shared route");
  assert.match(read("src-tauri/src/hud_bootstrap.js"), /sleep_time\|profile\|shared\)/,
    "the HUD page could tag a fact");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\n\"Between us\": one fact per tap, the list word for word, held on a stale link");
process.exit(fails.length ? 1 : 0);
