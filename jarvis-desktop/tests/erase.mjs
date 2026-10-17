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
  ERASE_ALSO_CHAT_CONFIRM,
  ERASE_CONFIRM,
  ERASE_LABEL,
  ERASED,
  ERASED_AND_CHAT_DELETED,
  ERASED_NO_CHAT,
  erasedAt,
  erasedLine,
  eraseQuestion,
  eraseSaid,
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

await check("the 'also delete the chat' question says what OK and Cancel each do", async () => {
  // Play tester, 2026-09-27: Cancel read as "cancel the erase". A native
  // dialog cannot rename its buttons, so the words say it instead.
  assert.ok(ERASE_ALSO_CHAT_CONFIRM.startsWith("The fact's words will be erased either way."));
  assert.ok(ERASE_ALSO_CHAT_CONFIRM.endsWith("OK: delete that chat too.\nCancel: keep the chat."));
  assert.match(ERASE_ALSO_CHAT_CONFIRM, /Also delete the chat this fact came from\?/);
});

await check("only a real erased_at makes a fact erased", async () => {
  assert.equal(erasedAt({ erased_at: 1790000000.5 }), 1790000000.5);
  for (const v of [null, undefined, "1790000000", 0, NaN, true]) {
    assert.equal(erasedAt({ erased_at: v }), null, String(v));
  }
  assert.equal(erasedAt(null), null);
  assert.match(erasedLine(1790000000), /^Erased on \S.*\d{4}$/);
});

/* ── "Erased." is only true when the PC says the file was rebuilt ──────── */

/**
 * The PC's own sentence for the case it could not finish, read OUT of the
 * backend rather than typed here, so the fixture and the server can never
 * drift apart. `jarvis_memory.handle_erase` builds one `note`: the short
 * "Erased. The words are gone..." and, when `file_clean` is false, a second
 * sentence saying an older copy may stay on disk. Python writes it as
 * adjacent string literals, so the quotes and newlines between them are
 * joined the way Python joins them.
 */
const NOT_CLEAN_NOTE = (() => {
  const src = read("../backend/rebuilt/jarvis_memory.py");
  const from = src.indexOf("Erased. The words are gone from Jarvis's memory");
  const to = src.indexOf("is erased again.", from);
  assert.ok(from > 0 && to > from,
    "the PC's erase note moved - read handle_erase() in jarvis_memory.py again");
  return src.slice(from, to + "is erased again.".length)
    .replace(/"\s*\n\s*"/g, "").replace(/\s+/g, " ").trim();
})();

await check("the PC's not-clean sentence is the one the backend really sends", async () => {
  // Without this the test could pass on a sentence nobody sends.
  assert.match(NOT_CLEAN_NOTE, /^Erased\. The words are gone from Jarvis's memory on this PC;/);
  assert.match(NOT_CLEAN_NOTE,
    /Another part of Jarvis was reading the memory file at that moment, so it could not be rebuilt: an older copy of these words may stay in memory\.db or memory\.db-wal until the fact is erased again\.$/);
});

await check("eraseSaid: the PC's note replaces 'Erased.' only when file_clean is false", async () => {
  // file_clean false, with the PC's own words -> the PC's own words.
  assert.equal(eraseSaid({ ok: true, file_clean: false, note: NOT_CLEAN_NOTE }, ERASED),
    NOT_CLEAN_NOTE, "the note the PC sent was not what the owner is shown");
  // ... and it wins over the longer "and the chat was deleted too" line: the
  // words may still be on disk is the more important sentence.
  assert.equal(eraseSaid({ ok: true, file_clean: false, note: NOT_CLEAN_NOTE,
                           chat_deleted: true }, ERASED_AND_CHAT_DELETED), NOT_CLEAN_NOTE);
  // CONTROL: a clean erase keeps the short line - the fix must not make every
  // erase alarming.
  assert.equal(eraseSaid({ ok: true, file_clean: true, note: NOT_CLEAN_NOTE }, ERASED), ERASED);
  assert.equal(eraseSaid({ ok: true, file_clean: true }, ERASED_AND_CHAT_DELETED),
    ERASED_AND_CHAT_DELETED);
  // CONTROL: a PC too old to send the field at all answers exactly as before.
  assert.equal(eraseSaid({ ok: true, chat_deleted: false }, ERASED), ERASED);
  assert.equal(eraseSaid({ ok: true, chat_deleted: false }, ERASED_NO_CHAT), ERASED_NO_CHAT);
  assert.equal(eraseSaid(null, ERASED), ERASED, "no reply at all is not a reason to say less");
  // A false flag with an empty note must not blank the message out.
  assert.equal(eraseSaid({ ok: true, file_clean: false, note: "   " }, ERASED), ERASED);
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

await check("it asks first; a no sends nothing; a yes offers to also delete the chat and says so", async () => {
  const page = await memoryTab({ auto: { facts: LIST } });
  const asked = [];
  page.on("dialog", (d) => { asked.push(d.message()); d.dismiss(); });
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(200);
  const afterNo = await page.evaluate(() => window.__memoryWrites);
  page.removeAllListeners("dialog");
  assert.deepEqual(asked, [eraseQuestion({ text: "Is building Jarvis, a local assistant." })],
    "dismissing the first confirm must never show the second (also delete the chat)");
  assert.deepEqual(afterNo, [], "dismissing the confirm sent nothing");

  const askedYes = [];
  page.on("dialog", (d) => { askedYes.push(d.message()); d.accept(); }); // both: erase, and also the chat
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(400);
  const afterYes = await page.evaluate(() => window.__memoryWrites);
  const left = await page.locator("#memory-auto-list .row-item").allInnerTexts();
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.deepEqual(askedYes, [eraseQuestion({ text: "Is building Jarvis, a local assistant." }),
    ERASE_ALSO_CHAT_CONFIRM]);
  assert.deepEqual(afterYes, [{ cmd: "brain_memory_erase", id: 12, also_delete_conversation: true }]);
  assert.equal(left.length, 1, "the erased fact stayed in Saved automatically");
  assert.match(left[0], /Prefers tea/);
  assert.equal(toast, ERASED_AND_CHAT_DELETED, "the toast says the chat was also deleted");
});

await check("declining 'also delete the chat' still erases the words, and says only Erased.", async () => {
  const page = await memoryTab({ auto: { facts: LIST } });
  let n = 0;
  page.on("dialog", (d) => { n += 1; if (n === 1) d.accept(); else d.dismiss(); });
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__memoryWrites);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.deepEqual(sent, [{ cmd: "brain_memory_erase", id: 12, also_delete_conversation: false }]);
  assert.equal(toast, ERASED);
});

await check("a PC that could not rebuild the file says so, instead of 'Erased.'", async () => {
  // Measured 2026-10-16: another connection open across the erase left 21
  // occurrences of the erased words in memory.db and its -wal. The PC answers
  // file_clean:false and explains; the page used to print "Erased." and never
  // read either field, so the one case where the promise was not kept was the
  // one case the owner was told nothing about.
  const page = await memoryTab({ auto: { facts: LIST }, eraseNotClean: NOT_CLEAN_NOTE });
  page.on("dialog", (d) => d.accept());   // both: erase, and also the chat
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(400);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.equal(toast, NOT_CLEAN_NOTE, "the owner was not shown the PC's own reason");
  assert.notEqual(toast, ERASED, "'Erased.' was shown for an erase that did not finish");
  assert.notEqual(toast, ERASED_AND_CHAT_DELETED);
});

await check("CONTROL: a PC that DID rebuild the file still says the short 'Erased.'", async () => {
  // The other half: the fix must not make every erase alarming. Same click,
  // same two dialogs, an ordinary reply.
  const page = await memoryTab({ auto: { facts: LIST } });
  let n = 0;
  page.on("dialog", (d) => { n += 1; if (n === 1) d.accept(); else d.dismiss(); });
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(400);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.equal(toast, ERASED, "an ordinary erase started showing the long note");
  assert.notEqual(toast, NOT_CLEAN_NOTE);
});

await check("What Jarvis knows: a current fact has Forget and Erase; a forgotten one has Erase only", async () => {
  const page = await memoryTab();
  const current = await page.locator("#memory-facts .row-item").first().locator("button").allInnerTexts();
  const retired = page.locator("#memory-facts .row-item").nth(2);
  const tag = await retired.locator(".row-tag").innerText();
  const retiredButtons = await retired.locator("button").allInnerTexts();
  page.on("dialog", (d) => d.accept());
  await retired.getByRole("button", { name: ERASE_LABEL }).click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__memoryWrites);
  await page.close();
  assert.deepEqual(current, ["Reword", "Forget", ERASE_LABEL]);
  assert.equal(tag.trim().toLowerCase(), "retired");
  assert.deepEqual(retiredButtons, [ERASE_LABEL], "a forgotten fact cannot have its words erased");
  assert.deepEqual(sent, [{ cmd: "brain_memory_erase", id: 4, also_delete_conversation: true }]);
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

await check("CONTROL: BOTH places that erase ask eraseSaid, so neither can say 'Erased.' alone", async () => {
  // The Memory tab (brain.js eraseFact) and the quickbar's "Used in this
  // answer" (answer-memory.js) are two separate call sites of the same
  // command. The fix is only worth anything if BOTH ask: a reverted one looks
  // exactly like the bug this pair of tests exists for.
  for (const f of ["src/brain.js", "src/answer-memory.js"]) {
    const src = read(f);
    assert.match(src, /eraseSaid\(/, `${f} does not call eraseSaid`);
    assert.match(src, /^\s*eraseSaid,$/m, `${f} does not import eraseSaid`);
  }
  const lib = read("src/auto-learn.js");
  assert.match(lib, /export function eraseSaid\(/, "eraseSaid is not exported from auto-learn.js");
});

await check("CONTROL: brain_memory_erase is held on a stale link, sends one id, Brain and the quickbar's \"Used in this answer\" only", async () => {
  const rs = read("src-tauri/src/brain.rs");
  const f = rs.slice(rs.indexOf("pub async fn brain_memory_erase("));
  const body = f.slice(0, f.indexOf("\n}\n"));
  assert.match(body, /app: AppHandle,\s*\n\s*id: i64,\s*\n\s*also_delete_conversation: Option<bool>,/,
    "the command takes an id and the also-delete-conversation flag, and nothing else");
  assert.ok(body.indexOf("require_link_live") >= 0
    && body.indexOf("require_link_live") < body.indexOf("post("), "Erase is not held on a stale link");
  assert.match(body, /let mut body = serde_json::json!\(\{ "id": id \}\);/);
  assert.match(body, /body\["also_delete_conversation"\] = serde_json::json!\(also\);/);
  assert.match(body, /"\/api\/memory\/erase", body\)/);
  assert.match(read("src-tauri/build.rs"), /"brain_memory_erase"/);
  assert.match(read("src-tauri/src/lib.rs"), /brain::brain_memory_erase,/);
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  const holders = sets.filter((s) => s.includes('"allow-brain-memory-erase"'))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  // Since 2026-09-25 also "memory-used": Forget and Erase beside each fact
  // under an answer (the quickbar) and under "Jarvis remembered N things".
  // Held on a stale link in Rust either way; no other window has it.
  assert.deepEqual(holders, ["memory-used", "brain-memory"]);
  const windows = ["brain", "quickbar", "hud", "widget", "settings", "faces", "floating", "onboarding"]
    .filter((w) => read(`src-tauri/capabilities/${w}.json`).includes('"memory-used"'));
  assert.deepEqual(windows, ["brain", "quickbar"]);
  assert.match(read("src-tauri/src/brain/routes.rs"), /"\/api\/memory\/erase",/,
    "the write-route list the read allowlist is checked against lacks erase");
  assert.match(read("src-tauri/src/hud_bootstrap.js"), /forget\|erase\|/,
    "the HUD page could send an erase");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nerasing a fact's words asks first, sends one id, and never shows the words again");
process.exit(fails.length ? 1 : 0);
