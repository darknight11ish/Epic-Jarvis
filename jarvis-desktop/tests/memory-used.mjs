/**
 * Temporary chat and "Used in this answer", in the quickbar - the owner's
 * decisions of 2026-09-25 (JARVIS-API.md sections 4, 6 and 18.1;
 * src/memory-used.js, src/answer-memory.js, commands.rs stream_chat /
 * temporary_chat_available / route_line_from_header, brain/used.rs).
 *
 * What must hold:
 * - one tap starts a temporary chat - but only on a PC that says it has
 *   one; an older PC says so plainly and the mode stays off;
 * - a marker for the whole chat, and the one line on the empty chat;
 * - every question of it goes with `temporary: true`, and turning it on or
 *   off starts a new conversation (nothing re-sent across);
 * - an answer whose route does not confirm it is temporary says so;
 *   a "Remember:" says Remember is off;
 * - under an answer that used memories, "Used 2 memories" opens those facts
 *   (words read by id), a pinned one marked, each with Forget and Erase,
 *   asked about first, one fact per call, held on a stale link, hidden
 *   under Windows Hello.
 *
 * The pure words first, then the quickbar in a real browser on the uikit
 * mock, then CONTROL checks that read the Rust and the phone.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  hiddenLine,
  missingLine,
  readUsed,
  REMEMBER_OFF,
  REMEMBERED_TITLE,
  rowActions,
  TEMPORARY_LABEL,
  TEMPORARY_LINE,
  TEMPORARY_NOT_CONFIRMED,
  TEMPORARY_UNAVAILABLE,
  temporaryOutcome,
  USED_MISSING,
  USED_TITLE,
  usedIds,
  usedLine,
} from "../src/memory-used.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the words are both apps' words, word for word", async () => {
  assert.equal(TEMPORARY_LINE,
    "Temporary chat: Jarvis won't use or learn from your memory, and this chat isn't kept.");
  assert.equal(REMEMBER_OFF, "Remember: is off in a temporary chat.");
  assert.equal(usedLine(1), "Used 1 memory");
  assert.equal(usedLine(2), "Used 2 memories");
  assert.equal(usedLine(0), "");
  assert.equal(missingLine(1), "1 of them is no longer on this PC.");
  // commands.rs says the unavailable sentence itself (stream_chat refuses).
  const rust = read("src-tauri/src/commands.rs").replace(/\\\n\s*/g, "");
  assert.ok(rust.includes(TEMPORARY_UNAVAILABLE), "commands.rs TEMPORARY_UNAVAILABLE differs");
  assert.ok(read("src-tauri/src/brain/used.rs").replace(/\\\n\s*/g, "").includes(USED_MISSING));
  // The phone says the same (net/MemoryUsed.kt).
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/MemoryUsed.kt");
  const flat = kt.replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [TEMPORARY_LABEL, TEMPORARY_LINE, TEMPORARY_UNAVAILABLE,
    TEMPORARY_NOT_CONFIRMED, REMEMBER_OFF, USED_TITLE, REMEMBERED_TITLE, USED_MISSING,
    "Used ", "1 of them is no longer on this PC."]) {
    assert.ok(flat.includes(words.replace(/"/g, '\\"')), `the phone does not say: ${words}`);
  }
});

await check("the route and the PC's answer are read, and nothing else counts", async () => {
  assert.deepEqual(usedIds({ memory_ids: [12, 7, 12, -1, 1.5, "3", 0] }), [12, 7]);
  assert.deepEqual(usedIds(null), []);
  assert.equal(temporaryOutcome(false, { temporary: true }), "");
  assert.equal(temporaryOutcome(true, { temporary: true }), "confirmed");
  assert.equal(temporaryOutcome(true, { temporary: "true" }), "unconfirmed");
  assert.equal(temporaryOutcome(true, null), "unconfirmed");
  const v = readUsed({ facts: [
    { id: 3, text: "Owner is vegetarian", current: true, pinned: true },
    { id: 4, text: "Owner lives in Harrogate", current: false, valid_to: 1.5 },
    { id: 5, text: "[erased]", current: false, erased_at: 1790000000 },
    { id: "6", text: "no whole-number id" }], missing: [9] });
  assert.deepEqual(v.facts.map((f) => f.id), [3, 4, 5]);
  assert.equal(v.facts[2].text, "", "an erased fact's marker was kept");
  assert.deepEqual(v.missing, [9]);
  assert.deepEqual(rowActions(v.facts[0]), { forget: true, erase: true });
  assert.deepEqual(rowActions(v.facts[1]), { forget: false, erase: true });
  assert.deepEqual(rowActions(v.facts[2]), { forget: false, erase: false });
  const old = readUsed({ available: false, why: "older" });
  assert.equal(old.available, false);
  assert.equal(readUsed(null).why, USED_MISSING);
  assert.match(hiddenLine(2), /hidden until Windows Hello confirms it is you - press Show/);
});

/* ── The quickbar ─────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 520, height: 640 };
const route = (r) => "\u001fjarvis-route:" + JSON.stringify(r);
const LOCAL = { lane: "qwen3:8b", where: "local", gate: "complexity" };

async function quickbar(data = {}, setup = {}) {
  const page = await K.open(browser, base, "index.html", data, SIZE);
  await page.evaluate((s) => Object.assign(window, s), setup);
  return page;
}
const submit = async (page, text) => {
  await page.locator("#prompt").fill(text);
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(250);
};
const chats = (page) => page.evaluate(() =>
  window.__calls.filter((c) => c[0] === "stream_chat")
    .map((c) => ({ temporary: c[1].temporary, conversationId: c[1].conversationId,
                   messages: c[1].messages.map((m) => m.content) })));

await check("an older PC: the mode stays off, says why, and nothing is sent as temporary", async () => {
  const page = await quickbar({ chatReplies: ["Hi."] }, { __temporaryOk: false });
  await page.locator("#temporary").click();
  await page.waitForTimeout(200);
  const pressed = await page.locator("#temporary").getAttribute("aria-pressed");
  const strip = await page.locator("#temporary-strip").innerText();
  await submit(page, "hello");
  const sent = await chats(page);
  await page.close();
  assert.equal(pressed, "false");
  assert.equal(strip.trim(), TEMPORARY_UNAVAILABLE);
  assert.equal(sent[0].temporary, false);
});

await check("on: a marker for the whole chat, the one line while it is empty, and every question temporary", async () => {
  const page = await quickbar({ chatReplies: ["Hello.", "Still here."] }, { __temporaryOk: true });
  await page.locator("#temporary").click();
  await page.waitForTimeout(200);
  const pressed = await page.locator("#temporary").getAttribute("aria-pressed");
  const empty = await page.locator("#temporary-strip").innerText();
  const marked = await page.locator("#shell").getAttribute("data-temporary");
  await submit(page, "hi");
  await submit(page, "and again");
  const strip = await page.locator("#temporary-strip").innerText();
  const sent = await chats(page);
  await page.close();
  assert.equal(pressed, "true");
  assert.equal(marked, "true");
  assert.match(empty, new RegExp(`^${TEMPORARY_LABEL}`));
  assert.ok(empty.includes(TEMPORARY_LINE), empty);
  assert.equal(strip.trim(), TEMPORARY_LABEL, "the marker went, or the empty-chat line stayed");
  assert.deepEqual(sent.map((s) => s.temporary), [true, true]);
  assert.equal(sent[1].conversationId, sent[0].conversationId);
  assert.deepEqual(sent[1].messages, ["hi", "Hello.", "and again"]);
});

await check("turning it on or off starts a new conversation: nothing is re-sent across", async () => {
  const page = await quickbar({ chatReplies: ["A.", "B.", "C."] }, { __temporaryOk: true });
  await submit(page, "normal question");
  await page.locator("#temporary").click();
  await page.waitForTimeout(200);
  await submit(page, "private question");
  await page.locator("#temporary").click();
  await page.waitForTimeout(200);
  await submit(page, "normal again");
  const sent = await chats(page);
  await page.close();
  assert.deepEqual(sent.map((s) => s.messages), [["normal question"], ["private question"],
    ["normal again"]]);
  assert.deepEqual(sent.map((s) => s.temporary), [false, true, false]);
  assert.equal(new Set(sent.map((s) => s.conversationId)).size, 3, "a conversation id was reused");
});

await check("confirmed: no memories line; a Remember: says Remember is off", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, temporary: true,
    remember_off: true, injected_facts: 0 }), "I can't keep that here."]] },
  { __temporaryOk: true });
  await page.locator("#temporary").click();
  await page.waitForTimeout(200);
  await submit(page, "Remember: my locker is 12");
  const note = await page.locator("#answer-memory-note").innerText();
  const used = await page.locator("#answer-used").isVisible();
  await page.close();
  assert.equal(note.trim(), REMEMBER_OFF);
  assert.equal(used, false);
});

await check("a PC that does not confirm a temporary chat is never pretended to have", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, injected_facts: 1,
    memory_ids: [3] }), "You like tea."]] }, { __temporaryOk: true });
  await page.locator("#temporary").click();
  await page.waitForTimeout(200);
  await submit(page, "what do I drink?");
  const note = await page.locator("#answer-memory-note").innerText();
  await page.close();
  assert.equal(note.trim(), TEMPORARY_NOT_CONFIRMED);
});

const USED = {
  12: { id: 12, text: "Owner is vegetarian", current: true, pinned: true, erased_at: null },
  7: { id: 7, text: "Owner lives in Harrogate", current: false, pinned: false,
       valid_to: 1780000000, erased_at: null },
};

await check("\"Used 2 memories\" opens those facts, read by id, a pinned one marked", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, injected_facts: 2,
    memory_ids: [12, 7] }), "Try a lentil curry."]] }, { __usedFacts: USED });
  await submit(page, "what should I cook?");
  const line = await page.locator("#answer-used-line").innerText();
  const before = await page.evaluate(() => window.__usedReads || []);
  await page.locator("#answer-used-line").click();
  await page.waitForTimeout(250);
  const rows = await page.locator(".answer-used-item").allInnerTexts();
  const asked = await page.evaluate(() => window.__usedReads);
  const expanded = await page.locator("#answer-used-line").getAttribute("aria-expanded");
  await page.close();
  assert.equal(line.trim(), "Used 2 memories");
  assert.deepEqual(before, [], "the words were read before the line was opened");
  assert.deepEqual(asked, [[12, 7]]);
  assert.equal(expanded, "true");
  assert.match(rows[0], /Owner is vegetarian[\s\S]*pinned[\s\S]*Forget[\s\S]*Erase the words/);
  assert.match(rows[1], /Owner lives in Harrogate[\s\S]*no longer in use/);
  assert.doesNotMatch(rows[1], /Forget/, "Forget offered on a fact no longer in use");
});

await check("Forget and Erase: asked first, ONE fact per call, and the list says what happened", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, injected_facts: 1,
    memory_ids: [12] }), "Lentils."]] }, { __usedFacts: JSON.parse(JSON.stringify(USED)) });
  const asked = [];
  page.on("dialog", (d) => { asked.push(d.message()); d.accept(); });
  await submit(page, "what should I cook?");
  await page.locator("#answer-used-line").click();
  await page.waitForTimeout(200);
  await page.locator(".answer-used-item button", { hasText: "Forget" }).click();
  await page.waitForTimeout(300);
  const afterForget = await page.locator(".answer-used-item").innerText();
  await page.locator(".answer-used-item button", { hasText: "Erase the words" }).click();
  await page.waitForTimeout(300);
  const afterErase = await page.locator(".answer-used-item").innerText();
  const writes = await page.evaluate(() => window.__memoryWrites);
  await page.close();
  assert.equal(asked.length, 2);
  assert.match(asked[0], /^Stop recalling this\?\n\nOwner is vegetarian/);
  assert.match(asked[1], /^Erase the words of this fact from your PC for good\?/);
  assert.deepEqual(writes, [{ cmd: "brain_memory_forget", id: 12 },
    { cmd: "brain_memory_erase", id: 12 }]);
  assert.match(afterForget, /no longer in use/);
  assert.doesNotMatch(afterForget, /Forget/);
  assert.match(afterErase, /^Erased on /);
  assert.doesNotMatch(afterErase, /vegetarian|Erase the words/);
});

await check("declining the question sends nothing", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, memory_ids: [12] }), "x"]] },
    { __usedFacts: USED });
  page.on("dialog", (d) => d.dismiss());
  await submit(page, "q");
  await page.locator("#answer-used-line").click();
  await page.waitForTimeout(200);
  await page.locator(".answer-used-item button", { hasText: "Forget" }).click();
  await page.waitForTimeout(200);
  const writes = await page.evaluate(() => window.__memoryWrites);
  await page.close();
  assert.deepEqual(writes, []);
});

await check("on a stale link Forget and Erase are greyed", async () => {
  const page = await quickbar({ link: { stale: true },
    chatReplies: [[route({ ...LOCAL, memory_ids: [12] }), "x"]] }, { __usedFacts: USED });
  await submit(page, "q");
  await page.locator("#answer-used-line").click();
  await page.waitForTimeout(200);
  const disabled = await page.locator(".answer-used-item button").evaluateAll(
    (bs) => bs.map((b) => b.disabled));
  await page.close();
  assert.deepEqual(disabled, [true, true]);
});

await check("hidden under Windows Hello: how many, never the words", async () => {
  const page = await quickbar({ security: { hidden: true },
    chatReplies: [[route({ ...LOCAL, memory_ids: [12, 7] }), "x"]] }, { __usedFacts: USED });
  await submit(page, "q");
  await page.locator("#answer-used-line").click();
  await page.waitForTimeout(200);
  const list = await page.locator("#answer-used-list").innerText();
  await page.close();
  assert.match(list, /These facts are hidden until Windows Hello confirms it is you/);
  assert.doesNotMatch(list, /vegetarian|Harrogate/);
});

await check("an answer that used nothing, or an older PC's list, says so plainly", async () => {
  const none = await quickbar({ chatReplies: [[route(LOCAL), "x"]] });
  await submit(none, "q");
  const shown = await none.locator("#answer-used").isVisible();
  await none.close();
  assert.equal(shown, false);
  const old = await quickbar({ chatReplies: [[route({ ...LOCAL, memory_ids: [12] }), "x"]] },
    { __usedMissingRoute: true });
  await submit(old, "q");
  await old.locator("#answer-used-line").click();
  await old.waitForTimeout(200);
  const list = await old.locator("#answer-used-list").innerText();
  await old.close();
  assert.ok(list.includes(USED_MISSING), list);
});

/* ── The Brain: "Jarvis remembered 2 things" ──────────────────────────── */

async function brainWithSaved(setup = {}, data = {}) {
  const page = await K.open(browser, base, "brain.html",
    { auto: { facts: [
      { id: 20, text: "Has a dentist on Fridays.", saved_at: 1790000000, provenance: "typed", device: "desktop" },
      { id: 21, text: "Uses Logseq for notes.", saved_at: 1789999999, provenance: "voice", device: "phone" },
    ] }, ...data }, { width: 1180, height: 820 });
  await page.evaluate((s) => Object.assign(window, s), setup);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(300);
  await page.evaluate(() =>
    window.__emit("jarvis-event", { kind: "memory_saved", id: 70, data: { ids: [20, 21] } }));
  await page.waitForTimeout(300);
  await page.locator("#memory-saved-line button").click();
  await page.waitForTimeout(300);
  return page;
}

await check("Brain: the line opens those two facts, each with Forget - one fact per tap, asked first", async () => {
  const page = await brainWithSaved();
  const asked = [];
  page.on("dialog", (d) => { asked.push(d.message()); d.accept(); });
  const title = await page.locator(".memory-saved-title").innerText();
  const rows = await page.locator("#memory-saved-line .row-item").allInnerTexts();
  await page.locator("#memory-saved-line .row-item").nth(1)
    .getByRole("button", { name: "Forget" }).click();
  await page.waitForTimeout(400);
  const writes = await page.evaluate(() => window.__memoryWrites);
  const after = await page.locator("#memory-saved-line .row-item").nth(1).innerText();
  await page.close();
  assert.equal(title, REMEMBERED_TITLE);
  assert.equal(rows.length, 2);
  assert.match(rows[0], /Has a dentist on Fridays/);
  assert.equal(asked.length, 1);
  assert.match(asked[0], /^Stop recalling this\?\n\nUses Logseq for notes\./);
  assert.deepEqual(writes, [{ cmd: "brain_memory_forget", id: 21 }]);
  assert.doesNotMatch(after, /Forget/, "a forgotten fact still offers Forget");
});

await check("Brain: hidden under Windows Hello, the facts are not shown", async () => {
  const page = await brainWithSaved({}, { security: { hidden: true } });
  const text = await page.locator("#memory-saved-line").innerText();
  await page.close();
  assert.match(text, /2 facts, hidden until Windows Hello confirms it is you/);
  assert.doesNotMatch(text, /dentist|Logseq/);
});

await browser.close();
await close();

/* ── CONTROL: the Rust ───────────────────────────────────────────────── */

await check("CONTROL: stream_chat sends temporary only to a PC that has it; memory_used hides under Hello", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const f = rust.slice(rust.indexOf("pub async fn stream_chat("));
  const body = f.slice(0, f.indexOf("\n}\n"));
  const check = body.indexOf("temporary_chat_supported(&app)");
  assert.ok(check > 0 && check < body.indexOf("pump_chat("), "no capability check before sending");
  assert.ok(/if supported != Ok\(true\) \{[\s\S]*?TEMPORARY_UNAVAILABLE/.test(body),
    "an older PC is not refused");
  assert.ok(body.indexOf('body.insert("temporary".into(), serde_json::json!(true))') > check);
  assert.match(rust, /out\.insert\("memory_ids"\.to_string\(\), serde_json::json!\(ids\)\)/);
  const used = read("src-tauri/src/brain/used.rs");
  assert.match(used, /if crate::lock::private_hidden\(&app\) \{\s*redact_used\(answer\)/);
  const caps = read("src-tauri/capabilities/quickbar.json");
  assert.ok(caps.includes('"memory-used"'));
  const sets = read("src-tauri/permissions/surfaces.toml");
  const set = sets.slice(sets.indexOf('identifier = "memory-used"'));
  assert.match(set.slice(0, 900), /"allow-memory-used",\s*"allow-brain-memory-forget",\s*"allow-brain-memory-erase",\s*\]/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\ntemporary chat and \"Used in this answer\": nothing pretended, one fact per tap");
