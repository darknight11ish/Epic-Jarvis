/**
 * Automatic learning, on the Brain's Memory tab (JARVIS-API.md section 19;
 * src/auto-learn.js, brain.js "Automatic learning",
 * src-tauri/src/brain/auto_learn.rs).
 *
 * What must hold (section 5 of the contract, and the rules around it):
 * - "Learn automatically" (on by default) and "Also remember sensitive
 *   topics automatically" (off by default), in the contract's words, next
 *   to the learning switch;
 * - either ON raises a card and shows "Waiting for your approval" until the
 *   card leaves the queue - a card raised on the phone too; OFF is
 *   immediate; ON is greyed (and held in Rust) on a stale link, OFF never;
 * - "Saved automatically": newest first, the fact, when, a "said aloud"
 *   mark for voice, Forget on each after a confirm, and "Load older";
 * - on `memory_saved` ({ids} only) a quiet line, "Jarvis remembered 2
 *   things", that opens the list - never the fact's words, never a pop-up;
 * - a card that stayed a card says why, in the PC's words;
 * - "Windows Hello for memory lists and chat history" hides this list too.
 *
 * Two halves, like history.mjs: the pure module, then the Brain window in a
 * real browser on the uikit mock. The answers are the contract's shapes
 * (section 4); the backend is built to the same contract in parallel.
 * CONTROL checks read the Rust.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  addPage,
  AUTO_DETAIL,
  AUTO_LABEL,
  AUTO_OFF,
  cardReason,
  EMPTY,
  factMeta,
  FORGOTTEN,
  forgetQuestion,
  HISTORY_NOTE,
  lastLine,
  lastLineNow,
  LEARNING_OFF_NOTE,
  olderThan,
  readAuto,
  refreshRows,
  rememberedLine,
  savedIds,
  SENSITIVE_DETAIL,
  SENSITIVE_LABEL,
  SENSITIVE_NEEDS_AUTO,
  stillOffLine,
  SWITCHES,
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
/** `n` auto-saved facts, one a minute apart, newest first. */
function many(n, extra = () => ({})) {
  return Array.from({ length: n }, (_, i) => ({
    id: 100 + i, text: `Fact number ${i}.`, saved_at: NOW - 60 * (i + 1) + 0.25,
    provenance: "typed", device: i % 2 ? "phone" : "desktop", ...extra(i),
  }));
}
const LIST = {
  auto: true, auto_sensitive: false,
  facts: [
    { id: 12, text: "Is building Jarvis, a local assistant.", saved_at: NOW - 300.5,
      provenance: "typed", device: "desktop" },
    { id: 11, text: "Prefers tea to coffee.", saved_at: NOW - 7200,
      provenance: "voice", device: "phone" },
  ],
};

/* ── The pure module ───────────────────────────────────────────────────── */

await check("the wording is the contract's, word for word (section 5)", async () => {
  assert.equal(AUTO_LABEL, "Learn automatically");
  assert.equal(AUTO_DETAIL, "Jarvis saves facts about you and your projects from what you type or say " +
    "to it - never from web pages, emails, documents or notes. You can forget any of them here.");
  assert.equal(SENSITIVE_LABEL, "Also remember sensitive topics automatically");
  assert.equal(SENSITIVE_DETAIL, "Health, money, and private details about other people. When this " +
    "is off, Jarvis asks you first. Passwords, PINs, account and ID numbers always wait for your yes.");
  assert.equal(rememberedLine(2), "Jarvis remembered 2 things");
  assert.equal(rememberedLine(1), "Jarvis remembered 1 thing");
  assert.equal(rememberedLine(0), "");
  assert.equal(SWITCHES.auto.action, "learning_auto_enable");
  assert.equal(SWITCHES.sensitive.action, "learning_sensitive_enable");
});

await check("the list is read as the PC sends it; a switch is on only when the PC says true", async () => {
  const v = readAuto(LIST);
  assert.equal(v.available, true);
  assert.equal(v.auto, true);
  assert.equal(v.sensitive, false);
  assert.deepEqual(v.facts[0], { id: 12, text: "Is building Jarvis, a local assistant.",
    savedAt: NOW - 300.5, provenance: "typed", device: "desktop" });
  // Missing or damaged: off, never assumed on.
  const bare = readAuto({ facts: [] });
  assert.equal(bare.auto, false);
  assert.equal(bare.sensitive, false);
  assert.equal(readAuto({ auto: "yes", facts: [] }).auto, false);
  // A row without a whole-number id cannot be forgotten, so it is not shown.
  assert.equal(readAuto({ facts: [{ id: "12", text: "x" }, { text: "y" }] }).facts.length, 0);
  const hidden = readAuto({ auto: true, facts: [], hidden: true, hidden_count: 4 });
  assert.equal(hidden.hidden, true);
  assert.equal(hidden.hiddenCount, 4);
});

await check("the switches come from GET /api/memory/learning, else from the list, else it says so", async () => {
  const STATUS = { enabled: false, auto: false, auto_sensitive: true, auto_waiting: true,
                   sensitive_waiting: false, auto_last: null, sensitive_last: null };
  // The learning route wins over the list's own copy.
  const v = readAuto(LIST, STATUS);
  assert.equal(v.switches, true);
  assert.equal(v.auto, false);
  assert.equal(v.sensitive, true);
  assert.equal(v.autoWaiting, true);
  assert.equal(v.sensitiveWaiting, false);
  assert.equal(v.learning, false);
  assert.equal(v.facts.length, 2);
  // An older PC without the route (Rust: {available: false}), or a failed
  // read (null): the list's `auto` / `auto_sensitive`.
  for (const status of [{ available: false }, null]) {
    const f = readAuto(LIST, status);
    assert.equal(f.switches, true);
    assert.equal(f.auto, true);
    assert.equal(f.autoWaiting, false);
    assert.equal(f.learning, null);
  }
  // Neither: the phone's words.
  const none = readAuto({ available: false }, { available: false });
  assert.equal(none.switches, false);
  assert.equal(none.available, false);
  assert.equal(none.why, "Your PC's Jarvis does not have automatic learning yet.");
  // A list that could not be read, with the route there: switches, no facts.
  const noList = readAuto(null, STATUS);
  assert.equal(noList.switches, true);
  assert.deepEqual(noList.facts, []);
});

await check("memory_saved carries ids only, and only whole numbers count", async () => {
  assert.deepEqual(savedIds({ ids: [3, 4] }), [3, 4]);
  assert.deepEqual(savedIds({ ids: [3, "4", 5.5, null] }), [3]);
  assert.deepEqual(savedIds({}), []);
  assert.deepEqual(savedIds(null), []);
});

await check("paging: the next page goes under, never twice, and asks from the oldest shown", async () => {
  const first = readAuto({ ...LIST, facts: many(3) }).facts;
  const rows = addPage(first, [first[2], ...readAuto({ ...LIST, facts: many(5) }).facts.slice(3)]);
  assert.deepEqual(rows.map((r) => r.id), [100, 101, 102, 103, 104]);
  assert.equal(olderThan(first), NOW - 180 + 0.25);
  assert.equal(olderThan([]), null);
  // The re-read keeps older pages under a full first page, drops them under a short one.
  const page = readAuto({ ...LIST, facts: many(30) }).facts;
  const older = readAuto({ ...LIST, facts: many(32) }).facts.slice(30);
  assert.equal(refreshRows([...page, ...older], page, 30, true).rows.length, 32);
  assert.deepEqual(refreshRows([...page, ...older], page.slice(0, 3), 30, true),
    { rows: page.slice(0, 3), more: false });
});

await check("a row says when and where; Forget asks today's question; a card says why", async () => {
  // History's device names, as the phone says them (FIXLIST 9).
  assert.equal(factMeta({ savedAt: NOW - 120, device: "phone" }, NOW * 1000), "2 min ago · from the phone");
  assert.equal(factMeta({ savedAt: NOW - 120, device: "desktop" }, NOW * 1000), "2 min ago · from the PC");
  assert.equal(factMeta({ savedAt: NOW - 120, device: "hud" }, NOW * 1000), "2 min ago · from the HUD");
  assert.equal(factMeta({ savedAt: NOW - 30, device: "" }, NOW * 1000), "just now");
  // Both apps' Forget words (FIXLIST 25); the question itself stays
  // (the owner's decision 24).
  assert.equal(forgetQuestion({ text: "Prefers tea." }),
    "Stop recalling this?\n\nPrefers tea.\n\nJarvis keeps a record that it once knew this, but will not use it " +
    "again. This cannot be undone.");
  assert.equal(FORGOTTEN, "Forgotten. Jarvis will not use it again.");
  assert.equal(cardReason({ auto_reason: "from pasted text" }), "Not saved automatically: from pasted text");
  assert.equal(cardReason({}), "");
});

/* ── The Brain window ──────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

async function memoryTab(auto = {}, extra = {}) {
  const page = await K.open(browser, base, "brain.html", { auto, ...extra }, SIZE);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(350);
  return page;
}
const settingsText = (page) => page.locator("#memory-auto").innerText();
const listText = (page) => page.locator("#memory-auto-list").innerText();
const autoState = (page) => page.evaluate(() => window.__auto);

await check("both switches sit with the learning switch, in the contract's words, as the PC has them", async () => {
  const page = await memoryTab({ facts: LIST.facts });
  const inLearning = await page.locator("#view-memory .card", { has: page.locator("#memory-learning") })
    .locator("#memory-auto").count();
  const text = await settingsText(page);
  const auto = await page.locator("#memory-auto-on").isChecked();
  const sensitive = await page.locator("#memory-sensitive-on").isChecked();
  const roles = await page.locator("#memory-auto [role=switch]").count();
  const heading = await page.locator("#memory-auto-card h2").textContent();
  const errors = page.__errors;
  await page.close();
  assert.equal(inLearning, 1, "the switches are not in the Learning card");
  assert.ok(text.includes(AUTO_LABEL) && text.includes(AUTO_DETAIL), text);
  assert.ok(text.includes(SENSITIVE_LABEL) && text.includes(SENSITIVE_DETAIL), text);
  assert.equal(auto, true);
  assert.equal(sensitive, false);
  assert.equal(roles, 2);
  assert.equal(heading, "Saved automatically");
  assert.deepEqual(errors, []);
});

await check("the list: newest first, the fact, when, a 'said aloud' mark for voice only - as text", async () => {
  const facts = [...LIST.facts, { id: 13, text: "<b>Works nights</b>", saved_at: NOW - 60,
    provenance: "typed", device: "desktop" }];
  const page = await memoryTab({ facts });
  const rows = await page.locator("#memory-auto-list .row-item").allInnerTexts();
  const bold = await page.locator("#memory-auto-list b").count();
  const markTitle = await page.locator("#memory-auto-list .history-mark-voice").getAttribute("title");
  await page.close();
  assert.equal(rows.length, 3);
  assert.match(rows[0], /<b>Works nights<\/b>/);
  assert.match(rows[1], /Is building Jarvis/);
  assert.match(rows[1], /5 min ago · from the PC/);
  assert.doesNotMatch(rows[1], /said aloud/);
  assert.match(rows[2], /Prefers tea to coffee/);
  assert.match(rows[2], /said aloud/);
  assert.match(rows[2], /from the phone/);
  assert.equal(bold, 0, "a fact's text became markup");
  assert.match(markTitle, /said aloud/);
});

await check("Forget asks first with the fact, sends one id, and a no sends nothing", async () => {
  const page = await memoryTab({ facts: LIST.facts });
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.dismiss(); });
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: "Forget" }).click();
  await page.waitForTimeout(200);
  const afterNo = await page.evaluate(() => window.__memoryWrites);
  page.once("dialog", (d) => d.accept());
  await page.locator("#memory-auto-list .row-item").first().getByRole("button", { name: "Forget" }).click();
  await page.waitForTimeout(400);
  const afterYes = await page.evaluate(() => window.__memoryWrites);
  const left = await page.locator("#memory-auto-list .row-item").allInnerTexts();
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.equal(asked, forgetQuestion({ text: "Is building Jarvis, a local assistant." }));
  assert.deepEqual(afterNo, [], "dismissing the confirm still forgot");
  assert.deepEqual(afterYes, [{ cmd: "brain_memory_forget", id: 12 }]);
  assert.equal(left.length, 1);
  assert.match(left[0], /Prefers tea/);
  assert.equal(toast, FORGOTTEN);
});

await check("Load older asks for the page before the oldest shown, and adds it underneath", async () => {
  const page = await memoryTab({ facts: many(31) });
  const before = await page.locator("#memory-auto-list .row-item").count();
  await page.locator("#memory-auto-list").getByRole("button", { name: "Load older" }).click();
  await page.waitForTimeout(250);
  const after = await page.locator("#memory-auto-list .row-item").count();
  const reads = (await autoState(page)).reads;
  const more = await page.locator("#memory-auto-list").getByRole("button", { name: "Load older" }).count();
  await page.close();
  assert.equal(before, 30);
  assert.equal(after, 31);
  assert.deepEqual(reads.at(-1), { before: NOW - 60 * 30 + 0.25, limit: 30 });
  assert.equal(more, 0, "offered more after a short page");
});

await check("turning sensitive topics ON raises a card and shows waiting - it is not on yet", async () => {
  const page = await memoryTab({ waits: ["sensitive"] });
  await page.locator("#memory-sensitive-on").click();
  await page.waitForTimeout(400);
  const sent = (await autoState(page)).switches;
  const line = await page.locator("#memory-auto .learning-waiting").allInnerTexts();
  const checked = await page.locator("#memory-sensitive-on").isChecked();
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.deepEqual(sent, [{ which: "sensitive", enabled: true }]);
  assert.equal(line.length, 1);
  assert.match(line[0], /^Waiting for your approval to remember sensitive topics automatically\. Approve it in the Jarvis bar/);
  assert.equal(checked, false, "shown as on before the card was approved");
  assert.match(toast, /Waiting for your approval/);
});

await check("a card raised on the phone shows the waiting line, and it goes with the card", async () => {
  const CARD = { id: "gate-auto-7", action: "learning_auto_enable", tier: "ask", detail: {}, created: 1 };
  const page = await memoryTab({ status: { auto: false } });
  const before = await page.locator("#memory-auto .learning-waiting").count();
  await page.evaluate((card) => window.__emit("approvals-changed", { count: 1, items: [card] }), CARD);
  await page.waitForTimeout(150);
  const line = await page.locator("#memory-auto .learning-waiting").allInnerTexts();
  await page.evaluate((card) => window.__emit("approvals-changed",
    { count: 1, items: [{ ...card, id: "gate-other", action: "learning_enable" }] }), CARD);
  await page.waitForTimeout(150);
  const other = await page.locator("#memory-auto .learning-waiting").count();
  await page.close();
  assert.equal(before, 0);
  assert.equal(line.length, 1, "no waiting line for a card raised on the phone");
  assert.match(line[0], /^Waiting for your approval to turn on learning automatically\./);
  assert.equal(other, 0, "the line stayed after the card left");
});

await check("the card leaving the queue unapproved ends the wait and says so", async () => {
  const CARD = { id: "gate-auto-1", action: "learning_auto_enable", tier: "ask", detail: {}, created: 1 };
  const page = await memoryTab({ waits: ["auto"], status: { auto: false } });
  await page.evaluate((card) => { window.__pendingNow = [card]; }, CARD);
  await page.locator("#memory-auto-on").click();
  await page.waitForTimeout(300);
  await page.evaluate((card) => window.__emit("approvals-changed", { count: 1, items: [card] }), CARD);
  await page.waitForTimeout(100);
  const before = await settingsText(page);
  // Denied: the card goes, and the PC says not waiting, and how it ended.
  await page.evaluate(() => {
    window.__pendingNow = [];
    window.__auto.status.auto_waiting = false;
    window.__auto.status.auto_last = { outcome: "denied", why: "", message: "", at: 1 };
    window.__emit("approvals-changed", { count: 0, items: [] });
  });
  await page.waitForTimeout(3600); // the grace an approval gets to land
  const after = await settingsText(page);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.match(before, /Waiting for your approval/);
  assert.doesNotMatch(after, /Waiting for your approval/, "still claims a card is waiting");
  assert.equal(toast, "You said no, so \"Learn automatically\" stays off.");
  assert.match(after, /You said no, so "Learn automatically" stays off\./);
});

await check("a card the PC refused says the PC's plain words - never \"denied or ran out of time\"", async () => {
  const CARD = { id: "gate-sens-2", action: "learning_sensitive_enable", tier: "ask", detail: {}, created: 1 };
  const MESSAGE = "Your PC's settings do not let this be approved, so it stayed off.";
  const page = await memoryTab({ waits: ["sensitive"] });
  await page.evaluate((card) => { window.__pendingNow = [card]; }, CARD);
  await page.locator("#memory-sensitive-on").click();
  await page.waitForTimeout(300);
  await page.evaluate((card) => window.__emit("approvals-changed", { count: 1, items: [card] }), CARD);
  await page.waitForTimeout(100);
  await page.evaluate((message) => {
    window.__pendingNow = [];
    window.__auto.status.sensitive_waiting = false;
    window.__auto.status.sensitive_last = { outcome: "refused", message, at: 1,
      why: "the gate answered at tier 'auto', which is not a person saying yes" };
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, MESSAGE);
  await page.waitForTimeout(3600);
  const toast = await page.locator("#toast").innerText();
  const line = await page.locator("#memory-auto .auto-last").allInnerTexts();
  const title = await page.locator("#memory-auto .auto-last").getAttribute("title");
  await page.close();
  assert.equal(toast, MESSAGE);
  assert.deepEqual(line, [MESSAGE]);
  assert.doesNotMatch(toast + line.join(" "), /denied or ran out of time|tier/);
  // The PC's reason is kept for anyone who looks, out of the line itself.
  assert.match(title, /tier 'auto'/);
});

await check("how the last card ended, in both apps' words, and only where it fits the switch", async () => {
  const L = (outcome, extra = {}) => ({ outcome, why: "", message: "", ...extra });
  assert.equal(lastLine("auto", L("enabled")), "Approved: \"Learn automatically\" is on now.");
  assert.equal(lastLine("sensitive", L("denied")),
    "You said no, so \"Also remember sensitive topics automatically\" stays off.");
  assert.equal(lastLine("auto", L("timed_out")), "Nobody answered the card in time, so nothing changed.");
  assert.equal(lastLine("auto", L("withdrawn")),
    "You turned it off while the card waited, so approving it changed nothing.");
  assert.equal(lastLine("auto", L("refused")), "Your PC's settings do not let this be approved, so it stayed off.");
  assert.equal(lastLine("auto", L("failed", { message: "Jarvis could not save the setting." })),
    "Jarvis could not save the setting.");
  assert.equal(lastLine("auto", L("failed", { why: "OSError" })), "Your PC could not turn it on, so it stayed off.");
  assert.equal(lastLine("auto", L("something new")), "");
  assert.equal(lastLine("auto", null), "");
  assert.equal(stillOffLine("auto"), "\"Learn automatically\" stays off. The card was not approved.");
  // Read from the learning route; only the newest card, as the PC keeps it.
  const STATUS = { enabled: true, auto: false, auto_sensitive: false, auto_waiting: false, sensitive_waiting: false,
    auto_last: { outcome: "timed_out", why: "", at: 1 }, sensitive_last: { outcome: "enabled", why: "", at: 2 } };
  const v = readAuto(LIST, STATUS);
  assert.deepEqual(v.autoLast, { outcome: "timed_out", why: "", message: "" });
  assert.equal(lastLineNow("auto", v), "Nobody answered the card in time, so nothing changed.");
  // "Approved" under a switch that is off (turned off since) says nothing.
  assert.equal(lastLineNow("sensitive", v), "");
  // Nor anything while a card waits: the waiting line says it.
  assert.equal(lastLineNow("auto", readAuto(LIST, { ...STATUS, auto_waiting: true })), "");
  assert.equal(readAuto(LIST, { ...STATUS, auto_last: { why: "x" } }).autoLast, null, "no outcome, no line");
});

await check("a damaged settings file: the PC's sentence under \"Learn automatically\"", async () => {
  const WHY = "The automatic-learning settings file was damaged, so \"Learn automatically\" is off. " +
    "Turn \"Learn automatically\" on again to rewrite it.";
  assert.equal(readAuto(LIST, { enabled: true, auto: false, auto_sensitive: false, why: WHY }).fileWhy, WHY);
  const page = await memoryTab({ status: { auto: false, why: WHY } });
  const line = await page.locator("#memory-auto .auto-file-why").allInnerTexts();
  await page.close();
  const fine = await memoryTab({});
  const none = await fine.locator("#memory-auto .auto-file-why").count();
  await fine.close();
  assert.deepEqual(line, [WHY]);
  assert.equal(none, 0);
});

await check("the sensitive switch says it does nothing while \"Learn automatically\" is off", async () => {
  assert.equal(SENSITIVE_NEEDS_AUTO, "\"Learn automatically\" is off, so this changes nothing until it is on.");
  const off = await memoryTab({ status: { auto: false } });
  const offText = await settingsText(off);
  await off.close();
  const on = await memoryTab({});
  const onText = await settingsText(on);
  await on.close();
  assert.ok(offText.includes(SENSITIVE_NEEDS_AUTO), offText);
  assert.ok(!onText.includes(SENSITIVE_NEEDS_AUTO), onText);
});

await check("while a card waits the switch is greyed; Cancel turns it OFF, withdraws the card, and is never held", async () => {
  const CARD = { id: "gate-auto-5", action: "learning_auto_enable", tier: "ask", detail: {}, created: 1 };
  const page = await memoryTab({ waits: ["auto"], status: { auto: false } }, { link: { stale: false } });
  await page.evaluate((card) => { window.__pendingNow = [card]; }, CARD);
  await page.locator("#memory-auto-on").click();
  await page.waitForTimeout(300);
  await page.evaluate((card) => window.__emit("approvals-changed", { count: 1, items: [card] }), CARD);
  await page.waitForTimeout(150);
  const greyed = await page.locator("#memory-auto-on").isDisabled();
  const cancel = page.locator("#memory-auto .auto-waiting").getByRole("button", { name: "Cancel the request" });
  const cancelOnStale = await cancel.isDisabled();
  await cancel.click();
  await page.waitForTimeout(400);
  const sent = (await autoState(page)).switches;
  // The withdrawn card is still in the queue (the PC lets go of it; it
  // leaves when answered or out of time) - and is not "waiting" any more.
  await page.evaluate((card) => window.__emit("approvals-changed", { count: 1, items: [card] }), CARD);
  await page.waitForTimeout(150);
  const waitingAfter = await page.locator("#memory-auto .auto-waiting").count();
  const usable = await page.locator("#memory-auto-on").isDisabled();
  const toast = await page.locator("#toast").innerText();
  // A NEW card (raised on the phone) is waiting again.
  await page.evaluate((card) => window.__emit("approvals-changed",
    { count: 2, items: [card, { ...card, id: "gate-auto-6" }] }), CARD);
  await page.waitForTimeout(150);
  const newCard = await page.locator("#memory-auto .auto-waiting").count();
  await page.close();
  assert.equal(greyed, true, "a second ON could be asked for while the card waits");
  assert.equal(cancelOnStale, false);
  assert.deepEqual(sent, [{ which: "auto", enabled: true }, { which: "auto", enabled: false }]);
  assert.equal(waitingAfter, 0, "a withdrawn card still reads as waiting");
  assert.equal(usable, false, "the switch stayed greyed after the card was withdrawn");
  assert.equal(toast, "\"Learn automatically\" is off. Every fact waits for your yes.");
  assert.equal(newCard, 1, "a new card raised elsewhere was not shown");
  // Cancel is OFF: it is offered on a stale link too.
  const stale = await memoryTab({ status: { auto: false, auto_waiting: true } }, { link: { stale: true } });
  const staleCancel = await stale.locator("#memory-auto .auto-waiting")
    .getByRole("button", { name: "Cancel the request" }).isDisabled();
  await stale.close();
  assert.equal(staleCancel, false, "OFF was held on a stale link");
});

await check("OFF says the PC's own sentence, and the app's own only when the PC sent none", async () => {
  const page = await memoryTab({ offMessage: "Sensitive topics now wait for your yes." , status: { auto_sensitive: true } });
  await page.locator("#memory-sensitive-on").click();
  await page.waitForTimeout(400);
  const said = await page.locator("#toast").innerText();
  await page.close();
  const older = await memoryTab({ offSilent: true, status: { auto_sensitive: true } });
  await older.locator("#memory-sensitive-on").click();
  await older.waitForTimeout(400);
  const own = await older.locator("#toast").innerText();
  await older.close();
  assert.equal(said, "Sensitive topics now wait for your yes.");
  assert.equal(own, SWITCHES.sensitive.off);
});

await check("the empty list, on and off, and the History line under Saved automatically", async () => {
  assert.equal(EMPTY, "Nothing has been saved automatically yet.");
  assert.equal(AUTO_OFF, "\"Learn automatically\" is off.");
  const on = await memoryTab({});
  const onText = (await listText(on)).trim();
  const note = await on.locator("#memory-auto-card .note").first().innerText();
  await on.close();
  const off = await memoryTab({ status: { auto: false } });
  const offText = (await listText(off)).trim();
  await off.close();
  assert.equal(onText, EMPTY);
  assert.equal(offText, `${EMPTY} ${AUTO_OFF}`);
  assert.equal(note, HISTORY_NOTE);
  assert.equal(HISTORY_NOTE,
    "Deleting a conversation from History does not forget facts learned from it - use Forget here.");
  assert.equal(LEARNING_OFF_NOTE,
    "Background learning is off, so nothing is saved automatically. Start learning above to use this.");
});

await check("saves while the Brain was closed are counted: Rust hands them over, and opening the list clears both", async () => {
  const page = await memoryTab({ facts: LIST.facts, unseen: [11, 12] });
  const line = await page.locator("#memory-saved-line").innerText();
  // The same id live again is not counted twice.
  await page.evaluate(() => window.__emit("jarvis-event", { kind: "memory_saved", id: 60, data: { ids: [12, 13] } }));
  await page.waitForTimeout(300);
  const line2 = await page.locator("#memory-saved-line").innerText();
  await page.locator("#memory-saved-line button").click();
  await page.waitForTimeout(250);
  const calls = (await autoState(page)).unseenCalls;
  await page.close();
  assert.equal(line.trim(), "Jarvis remembered 2 things");
  assert.equal(line2.trim(), "Jarvis remembered 3 things");
  assert.deepEqual(calls, [false, true], "the count was not read on open, or not cleared when seen");
  // CONTROL: the Rust keeps them from the event stream, ids only.
  const stream = read("src-tauri/src/stream.rs");
  assert.match(stream, /"memory_saved" => crate::brain::auto_learn::note_saved\(&event\.data\)/);
  const rust = read("src-tauri/src/brain/auto_learn.rs");
  assert.match(rust, /pub fn brain_memory_saved_unseen\(seen: bool\) -> serde_json::Value/);
  assert.match(read("src-tauri/src/windows.rs"), /pub\(crate\) fn show_brain_unlocked/);
});

await check("the learning card says \"background learning\", and a \"Remember:\" saved without a card says so", async () => {
  const pending = { ...K.BRAIN.memory_pending, setup: { ...K.BRAIN.memory_pending.setup,
    remember_last: { queued: false, auto_saved: true, note: "Saved without a card: it was in your own words." } } };
  const page = await memoryTab({}, { brain: { ...K.BRAIN, memory_pending: pending } });
  const learning = await page.locator("#memory-learning").innerText();
  await page.close();
  assert.match(learning, /Background learning/);
  assert.match(learning, /Saved without a card: it was in your own words\./);
  // CONTROL: a queued "Remember:" (a card) has nothing to add.
  const queued = { ...pending, setup: { ...pending.setup,
    remember_last: { queued: true, auto_saved: false, note: "Made a card." } } };
  const q = await memoryTab({}, { brain: { ...K.BRAIN, memory_pending: queued } });
  const qText = await q.locator("#memory-learning").innerText();
  await q.close();
  assert.doesNotMatch(qText, /Made a card/);
});

await check("turning Learn automatically OFF is immediate, and what was saved stays listed", async () => {
  const page = await memoryTab({ facts: LIST.facts });
  await page.locator("#memory-auto-on").click();
  await page.waitForTimeout(400);
  const sent = (await autoState(page)).switches;
  const toast = await page.locator("#toast").innerText();
  const checked = await page.locator("#memory-auto-on").isChecked();
  const rows = await page.locator("#memory-auto-list .row-item").count();
  await page.close();
  assert.deepEqual(sent, [{ which: "auto", enabled: false }]);
  assert.equal(toast, SWITCHES.auto.off);
  assert.equal(checked, false);
  assert.equal(rows, 2, "what was saved stays until forgotten");
});

await check("on a stale link ON is greyed and Forget with it; OFF never is", async () => {
  const page = await memoryTab({ facts: LIST.facts }, { link: { stale: true } });
  const sensitiveOn = await page.locator("#memory-sensitive-on").isDisabled();
  const autoOff = await page.locator("#memory-auto-on").isDisabled();
  const forget = await page.locator("#memory-auto-list").getByRole("button", { name: "Forget" }).first().isDisabled();
  await page.close();
  assert.equal(sensitiveOn, true, "ON could be asked for on a stale link");
  assert.equal(autoOff, false, "OFF was held on a stale link");
  assert.equal(forget, true, "Forget was offered on a stale link");
});

await check("memory_saved: a quiet line with the count, the list read again, no fact text, no pop-up", async () => {
  const page = await memoryTab({ facts: LIST.facts });
  const readsBefore = (await autoState(page)).reads.length;
  let popped = false;
  page.on("dialog", (d) => { popped = true; d.dismiss(); });
  await page.evaluate((now) => {
    window.__auto.facts.push({ id: 20, text: "Has a dentist on Fridays.", saved_at: now, provenance: "typed", device: "desktop" },
                             { id: 21, text: "Uses Logseq for notes.", saved_at: now - 1, provenance: "voice", device: "phone" });
    window.__emit("jarvis-event", { kind: "memory_saved", id: 40, data: { ids: [20, 21] } });
  }, NOW);
  await page.waitForTimeout(400);
  const line = await page.locator("#memory-saved-line").innerText();
  const rows = await page.locator("#memory-auto-list .row-item").allInnerTexts();
  const readsAfter = (await autoState(page)).reads.length;
  const toastShown = await page.locator("#toast").isVisible();
  // The same ids again are not counted twice; a new one is.
  await page.evaluate(() => {
    window.__emit("jarvis-event", { kind: "memory_saved", id: 41, data: { ids: [21, 22] } });
    window.__emit("jarvis-event", { kind: "memory_saved", id: 42, data: {} });
  });
  await page.waitForTimeout(250);
  const line2 = await page.locator("#memory-saved-line").innerText();
  await page.locator("#memory-saved-line button").click();
  await page.waitForTimeout(250);
  const cleared = await page.locator("#memory-saved-line").innerText();
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
  await page.close();
  assert.equal(line.trim(), "Jarvis remembered 2 things");
  assert.doesNotMatch(line, /dentist|Logseq/);
  assert.ok(readsAfter > readsBefore, "the list was not read again");
  assert.match(rows[0], /Has a dentist on Fridays/);
  assert.equal(rows.length, 4);
  assert.equal(toastShown, false, "a pop-up for a saved fact");
  assert.equal(popped, false);
  assert.equal(line2.trim(), "Jarvis remembered 3 things");
  assert.equal(cleared.trim(), "", "opening the list left the line");
  assert.equal(focused, "memory-auto-list", "the line did not open the list");
});

await check("a memory_saved on another tab waits for the Memory tab, and the list is read then", async () => {
  const page = await K.open(browser, base, "brain.html", { auto: { facts: [] } }, SIZE);
  await page.locator("#tab-history").click();
  await page.waitForTimeout(200);
  await page.evaluate((now) => {
    window.__auto.facts.push({ id: 30, text: "Drives a blue car.", saved_at: now, provenance: "typed", device: "desktop" });
    window.__emit("jarvis-event", { kind: "memory_saved", id: 50, data: { ids: [30] } });
  }, NOW);
  await page.waitForTimeout(200);
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(400);
  const line = await page.locator("#memory-saved-line").innerText();
  const rows = await listText(page);
  await page.close();
  assert.equal(line.trim(), "Jarvis remembered 1 thing");
  assert.match(rows, /Drives a blue car/);
});

await check("private answers hide the list, keep the count and the switches, and Show brings it back", async () => {
  const page = await memoryTab({ facts: many(3) }, { security: { hidden: true } });
  const hidden = await listText(page);
  const switches = await page.locator("#memory-auto [role=switch]").count();
  await page.locator("#memory-auto-list button", { hasText: "Show" }).click();
  await page.waitForTimeout(350);
  const shown = await page.locator("#memory-auto-list .row-item").count();
  await page.close();
  assert.match(hidden, /3 facts, hidden until Windows Hello confirms it is you/);
  assert.doesNotMatch(hidden, /Fact number/);
  assert.equal(switches, 2);
  assert.equal(shown, 3);
});

await check("with background learning off, it says automatic learning waits for it", async () => {
  const brain = { ...K.BRAIN, memory_facts: { ...K.BRAIN.memory_facts, learning: false } };
  // The learning route's `enabled`, and an older PC's facts-list flag.
  const off = await memoryTab({ status: { enabled: false } }, { brain });
  const offText = await settingsText(off);
  await off.close();
  const older = await memoryTab({ statusMissing: true }, { brain });
  const olderText = await settingsText(older);
  await older.close();
  const on = await memoryTab({});
  const onText = await settingsText(on);
  await on.close();
  assert.match(offText, /Background learning is off, so nothing is saved automatically/);
  assert.match(olderText, /Background learning is off, so nothing is saved automatically/);
  assert.doesNotMatch(onText, /Background learning is off/);
});

await check("the PC's own 'waiting' shows the line even before the queue has the card", async () => {
  const page = await memoryTab({ status: { auto_sensitive: false, sensitive_waiting: true } });
  const line = await page.locator("#memory-auto .learning-waiting").allInnerTexts();
  const reads = (await autoState(page)).statusReads;
  await page.close();
  assert.equal(line.length, 1);
  assert.match(line[0], /remember sensitive topics automatically/);
  assert.ok(reads >= 1, "the switches were not read from GET /api/memory/learning");
});

await check("an older PC without the learning route: the switches come from the list", async () => {
  const page = await memoryTab({ statusMissing: true, status: { auto: false, auto_sensitive: true } });
  const auto = await page.locator("#memory-auto-on").isChecked();
  const sensitive = await page.locator("#memory-sensitive-on").isChecked();
  await page.close();
  assert.equal(auto, false);
  assert.equal(sensitive, true);
});

await check("a card that stayed a card says why, in the PC's words", async () => {
  const pending = { ...K.BRAIN.memory_pending, pending: [
    { id: 51, text: "Takes 20mg of something daily.", source: "conversation", confidence: 0.9,
      created: NOW - 60, auto_reason: "sensitive: health" }] };
  const page = await memoryTab({}, { brain: { ...K.BRAIN, memory_pending: pending } });
  const card = await page.locator("#memory-proposals .row-item").first().innerText();
  await page.close();
  assert.match(card, /Not saved automatically: sensitive: health/);
});

await check("a PC without automatic learning at all says so, in the phone's words", async () => {
  const page = await memoryTab({ missing: true, statusMissing: true });
  const text = await settingsText(page);
  const list = await listText(page);
  const switches = await page.locator("#memory-auto [role=switch]").count();
  await page.close();
  assert.equal(text.trim(), "Your PC's Jarvis does not have automatic learning yet.");
  assert.equal(switches, 0);
  assert.doesNotMatch(text + list, /[{}]|undefined|null/);
});

await check("CONTROL: only the Brain holds the commands; ON and Forget are held on a stale link, OFF never", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  const holders = (perm) => sets.filter((s) => s.includes(`"${perm}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  const cmds = ["brain_memory_learning_status", "brain_memory_auto_list", "brain_memory_learning_auto",
    "brain_memory_learning_sensitive", "brain_memory_saved_unseen"];
  for (const cmd of cmds) {
    const perm = `allow-${cmd.replace(/_/g, "-")}`;
    assert.deepEqual(holders(perm), ["brain-memory"], `${perm} is held by ${holders(perm)}`);
  }
  for (const c of ["brain", "faces", "hud", "onboarding", "quickbar", "settings", "widget"]) {
    const json = read(`src-tauri/capabilities/${c}.json`);
    assert.equal(json.includes("\"brain-memory\""), c === "brain", `${c} and brain-memory`);
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const cmd of cmds) {
    assert.match(build, new RegExp(`"${cmd}"`), `${cmd} missing from build.rs`);
    assert.match(lib, new RegExp(`brain::auto_learn::${cmd},`), `${cmd} missing from lib.rs`);
  }
  const rust = read("src-tauri/src/brain/auto_learn.rs");
  const set = rust.slice(rust.indexOf("async fn set("));
  assert.match(set, /if enabled \{\s*require_link_live\(app\)\?;\s*\}/, "ON is not held, or OFF is");
  assert.ok(set.indexOf("require_link_live") < set.indexOf(".post("), "the hold comes after the send");
  const list = rust.slice(rust.indexOf("pub async fn brain_memory_auto_list("));
  assert.match(list, /private_hidden\(&app\)/, "the list is not hidden with the other memory lists");
  assert.match(rust, /"\/api\/memory\/learning\/auto"/);
  assert.match(rust, /"\/api\/memory\/learning\/sensitive"/);
  assert.doesNotMatch(rust, /Vec<i64>|Vec<String>/, "a list of ids reaches an automatic-learning command");
  const forget = read("src-tauri/src/brain.rs");
  const f = forget.slice(forget.indexOf("pub async fn brain_memory_forget("));
  assert.ok(f.indexOf("require_link_live") < f.indexOf("post("), "Forget is not held on a stale link");
});

await check("the first-run walkthrough says what memory really does, and is shown again once", async () => {
  // Version 1 said "Jarvis only remembers what you approve", which stopped
  // being true when learning became automatic (2026-09-24).
  const page = read("src/onboarding.html");
  const screen = page.slice(page.indexOf('id="screen-3"'), page.indexOf("</section>", page.indexOf('id="screen-3"')));
  assert.doesNotMatch(screen, /only remembers what you approve|doesn't save it right away/i);
  assert.match(screen, /your own words/);
  assert.match(screen, /Forget/);
  assert.match(screen, /wait for your\s+yes/);
  // The "seen" marker is a version, raised with that change (commands.rs).
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /pub const ONBOARDING_VERSION: u64 = 2;/);
  assert.doesNotMatch(rust, /store\.set\("onboarding_seen"/, "the old yes/no marker is still written");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nautomatic learning is shown, and forgettable one at a time");
process.exit(fails.length ? 1 : 0);
