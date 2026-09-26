/**
 * "Always keep in mind", on the Brain's Memory tab (the owner's decision of
 * 2026-09-24; JARVIS-API.md section 6 `/api/memory/profile`;
 * src/memory-profile.js, brain.js paintProfile / pinButton,
 * src-tauri/src/brain/profile.rs).
 *
 * What must hold:
 * - the section says what it is in the words both apps use, and how many of
 *   the list's 1,200 characters are used ("19 of 1,200 characters used");
 * - every pinned fact is listed word for word, with an Unpin;
 * - wherever a current fact has Forget - "Saved automatically" and "What
 *   Jarvis knows about you" - it has Pin (or Unpin, when it is pinned); a
 *   forgotten fact has neither;
 * - a tap sends ONE brain_memory_pin with that one id and asks nothing
 *   first (no card, no confirm: the owner's own tap, like the Pin it is);
 * - a refusal ("That would make the list too long - unpin something first")
 *   is shown in the PC's words;
 * - held on a stale link (greyed here, refused in Rust);
 * - hidden with the other memory lists under Windows Hello;
 * - a PC without the list: no Pin buttons, and the section says so.
 *
 * The pure words first, then the Brain window in a real browser on the uikit
 * mock, then CONTROL checks that read the Rust and the phone.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  grouped,
  isPinned,
  PIN_LABEL,
  PINNED,
  PROFILE_DETAIL,
  PROFILE_EMPTY,
  PROFILE_MISSING,
  PROFILE_TITLE,
  readProfile,
  UNPIN_LABEL,
  UNPINNED,
  usedLine,
} from "../src/memory-profile.js";
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
const LIST = [
  { id: 12, text: "Is building Jarvis, a local assistant.", saved_at: NOW - 300,
    provenance: "typed", device: "desktop" },
  { id: 11, text: "Owner is vegetarian", saved_at: NOW - 7200,
    provenance: "voice", device: "phone" },
];
const PINNED_11 = { facts: [{ id: 11, text: "Owner is vegetarian", added: NOW - 60 }] };

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the section's words are both apps' words, word for word", async () => {
  assert.equal(PROFILE_TITLE, "Always keep in mind");
  assert.equal(PROFILE_DETAIL, "Jarvis reads these with every question, word for word. Keep it short.");
  assert.equal(PIN_LABEL, "Pin");
  assert.equal(UNPIN_LABEL, "Unpin");
  assert.equal(usedLine(19, 1200), "19 of 1,200 characters used");
  assert.equal(usedLine(1200, 1200), "1,200 of 1,200 characters used");
  assert.equal(grouped(1234567), "1,234,567");
  assert.equal(grouped(-3), "0");
  // The window's own copy of the title and line.
  const html = read("src/brain.html");
  assert.match(html, /<h2>Always keep in mind<\/h2>/);
  assert.ok(html.includes(`>${PROFILE_DETAIL}</p>`));
  // The phone says the same (net/MemoryProfile.kt).
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/MemoryProfile.kt");
  const flat = kt.replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [PROFILE_TITLE, PROFILE_DETAIL, PIN_LABEL, UNPIN_LABEL, PINNED, UNPINNED,
    PROFILE_EMPTY, PROFILE_MISSING.replace(/"/g, '\\"')]) {
    assert.ok(flat.includes(`"${words}"`), `the phone does not say: ${words}`);
  }
  assert.ok(flat.includes("of \" + grouped(limit) + \" characters used")
    || flat.includes("characters used"), "the phone's used line");
});

await check("the PC's answer is read, and anything else is not a list", async () => {
  const v = readProfile({ facts: [{ id: 3, text: "Owner is vegetarian", added: 1.5 },
    { id: "4", text: "no whole-number id" }], chars: 19, limit: 1200 });
  assert.equal(v.available, true);
  assert.deepEqual(v.facts, [{ id: 3, text: "Owner is vegetarian", added: 1.5 }]);
  assert.equal(v.chars, 19);
  assert.ok(isPinned(v, 3) && !isPinned(v, 4));
  for (const nothing of [null, undefined, {}, { ok: true }, "x"]) {
    const n = readProfile(nothing);
    assert.equal(n.available, false, JSON.stringify(nothing));
    assert.equal(n.why, PROFILE_MISSING);
    assert.equal(n.ids.size, 0);
  }
  const old = readProfile({ available: false, why: "An older PC." });
  assert.equal(old.available, false);
  assert.equal(old.why, "An older PC.");
  const hidden = readProfile({ facts: [], hidden: true, hidden_count: 2, chars: 30, limit: 1200 });
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

await check("the section: title, its one line, characters used, each pinned fact with Unpin", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, profile: PINNED_11 });
  const card = page.locator("#memory-profile-card");
  const title = (await card.locator("h2").textContent()).trim();   // CSS writes it in capitals
  const note = await card.locator(".note").first().innerText();
  const used = await card.locator(".profile-used").innerText();
  const rows = await card.locator(".row-item").allInnerTexts();
  const buttons = await card.locator(".row-item button").allInnerTexts();
  await page.close();
  assert.equal(title, PROFILE_TITLE);
  assert.equal(note, PROFILE_DETAIL);
  assert.equal(used, "19 of 1,200 characters used");
  assert.equal(rows.length, 1);
  assert.match(rows[0], /Owner is vegetarian/);
  assert.deepEqual(buttons, [UNPIN_LABEL]);
});

await check("Pin / Unpin sits with Forget on every current fact, in both lists; none on a forgotten one", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, profile: PINNED_11 });
  const auto = [];
  const rows = page.locator("#memory-auto-list .row-item");
  for (let i = 0; i < await rows.count(); i++) auto.push(await rows.nth(i).locator("button").allInnerTexts());
  const current = await page.locator("#memory-facts .row-item").first().locator("button").allInnerTexts();
  const retired = await page.locator("#memory-facts .row-item").nth(2).locator("button").allInnerTexts();
  await page.close();
  assert.deepEqual(auto, [[PIN_LABEL, "Forget", "Erase the words"],
    [UNPIN_LABEL, "Forget", "Erase the words"]]);
  assert.deepEqual(current, [PIN_LABEL, "Reword", "Forget", "Erase the words"]);
  assert.ok(!retired.includes(PIN_LABEL) && !retired.includes(UNPIN_LABEL),
    `a forgotten fact offered ${retired}`);
});

await check("a tap sends ONE pin for that id, asks nothing, and the list shows it", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, profile: PINNED_11 });
  let asked = false;
  page.on("dialog", (d) => { asked = true; d.dismiss(); });
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: PIN_LABEL }).click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__memoryWrites);
  const listed = await page.locator("#memory-profile .row-item").allInnerTexts();
  const toast = await page.locator("#toast").innerText();
  const autoButtons = await page.locator("#memory-auto-list .row-item").first().locator("button").allInnerTexts();
  await page.close();
  assert.equal(asked, false, "pinning asked a question - it is the owner's own tap");
  assert.deepEqual(sent, [{ cmd: "brain_memory_pin", id: 12, pinned: true }]);
  assert.equal(listed.length, 2);
  assert.match(listed[1], /Is building Jarvis/);
  assert.equal(toast, PINNED);
  assert.equal(autoButtons[0], UNPIN_LABEL, "the row still says Pin after pinning");
});

await check("Unpin in the section sends one unpin, and the fact leaves the list", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, profile: PINNED_11 });
  await page.locator("#memory-profile").getByRole("button", { name: UNPIN_LABEL }).click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__memoryWrites);
  const empty = await page.locator("#memory-profile").innerText();
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.deepEqual(sent, [{ cmd: "brain_memory_pin", id: 11, pinned: false }]);
  assert.match(empty, new RegExp(PROFILE_EMPTY.replace(/[.]/g, "\\.")));
  assert.match(empty, /0 of 1,200 characters used/);
  assert.equal(toast, UNPINNED);
});

await check("a refused pin says the PC's words, and nothing is listed", async () => {
  const refuse = "That would make the list too long - unpin something first";
  const page = await memoryTab({ auto: { facts: LIST }, profile: { ...PINNED_11, refuse } });
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: PIN_LABEL }).click();
  await page.waitForTimeout(500);
  const toast = await page.locator("#toast").innerText();
  const listed = await page.locator("#memory-profile .row-item").count();
  await page.close();
  assert.equal(toast, refuse);
  assert.equal(listed, 1);
});

await check("on a stale link Pin and Unpin are greyed, like Forget", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, profile: PINNED_11, link: { stale: true } });
  const pin = await page.locator("#memory-auto-list").getByRole("button", { name: PIN_LABEL }).first().isDisabled();
  const unpin = await page.locator("#memory-profile").getByRole("button", { name: UNPIN_LABEL }).isDisabled();
  const inFacts = await page.locator("#memory-facts").getByRole("button", { name: PIN_LABEL }).first().isDisabled();
  await page.close();
  assert.equal(pin, true, "Pin was offered on a stale link");
  assert.equal(unpin, true, "Unpin was offered on a stale link");
  assert.equal(inFacts, true, "Pin was offered on a stale link (What Jarvis knows)");
});

await check("hidden with the other memory lists until Windows Hello says it is you", async () => {
  const page = await memoryTab({ auto: { facts: LIST }, profile: PINNED_11,
    security: { hidden: true } });
  const text = await page.locator("#memory-profile").innerText();
  await page.close();
  assert.doesNotMatch(text, /vegetarian/);
  assert.match(text, /hidden until Windows Hello/);
});

await check("a PC without the list: the section says so, and no fact offers Pin", async () => {
  const page = await memoryTab({ auto: { facts: LIST } });
  const text = await page.locator("#memory-profile").innerText();
  const pins = await page.getByRole("button", { name: PIN_LABEL, exact: true }).count();
  await page.close();
  assert.equal(text.trim(), PROFILE_MISSING);
  assert.equal(pins, 0);
});

/* ── CONTROL: the Rust ────────────────────────────────────────────────── */

await check("CONTROL: brain_memory_pin is held on a stale link, sends one id and one answer, Brain only", async () => {
  const rs = read("src-tauri/src/brain/profile.rs");
  const f = rs.slice(rs.indexOf("pub async fn brain_memory_pin("));
  const body = f.slice(0, f.indexOf("\n}\n"));
  assert.match(body, /id: i64,\s*pinned: bool,/);
  assert.ok(body.indexOf("require_link_live") >= 0
    && body.indexOf("require_link_live") < body.indexOf(".post("), "Pin is not held on a stale link");
  assert.match(rs, /serde_json::json!\(\{ "id": id, "pinned": pinned \}\)/);
  const list = rs.slice(rs.indexOf("pub async fn brain_memory_profile("));
  assert.match(list.slice(0, list.indexOf("\n}\n")), /private_hidden/,
    "the list is not hidden with the other memory lists");
  for (const cmd of ["brain_memory_profile", "brain_memory_pin"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::profile::${cmd},`));
    const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-memory"], cmd);
  }
  assert.match(read("src-tauri/src/brain/routes.rs"), /"\/api\/memory\/profile",/,
    "the write-route list the read allowlist is checked against lacks the profile route");
  assert.match(read("src-tauri/src/hud_bootstrap.js"), /sleep_time\|profile\)/,
    "the HUD page could pin a fact");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\n\"Always keep in mind\": one fact per tap, the list word for word, held on a stale link");
process.exit(fails.length ? 1 : 0);
