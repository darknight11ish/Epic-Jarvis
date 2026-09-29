/**
 * The second chat audit (2026-09-28; docs/studio-2026-09-28/chat-audit2-*.md),
 * on the desktop: the Jarvis bar's thread and the Brain's History, run in the
 * real frontend over the fake bridge.
 *
 *   node tests/chat-thread.mjs      (needs Playwright, like the other UI tests)
 *
 * The owner's decisions: the scrollable thread hides under "Hide memory lists
 * and chat history"; a line says where Jarvis reads from; the delete dialogs
 * say what stays. And the play-test fixes: the question shown above its
 * answer, the thread opening on its newest end, a chat that ended saying so
 * (and saying nothing was kept for a game), row-named buttons, a search that
 * keeps each row's kind and the "Show" filter, and the facts a chat taught on
 * the opened chat.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";
import * as CH from "../src/chat-history.js";
import { chatFactsTaught, chatFactsTaughtHidden } from "../src/history-view.js";
import { eraseAlsoChatNamedConfirm } from "../src/auto-learn.js";

const fails = [];
async function check(name, fn) {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
}

/* -- the words and rules, no browser ------------------------------------- */

await check("where Jarvis reads from: the pairs above the line", async () => {
  assert.equal(CH.pairsAboveReadLine(12, 7), 5);
  assert.equal(CH.pairsAboveReadLine(3, 3), 0, "all of it is read: no line");
  assert.equal(CH.pairsAboveReadLine(3, 9), 0);
  assert.equal(CH.pairsAboveReadLine(0, 0), 0);
  assert.equal(CH.pairsAboveReadLine(undefined, 4), 0);
  assert.equal(CH.THREAD_READS_FROM,
    "Jarvis reads from here down. What is above stays on screen only.");
});

await check("Continue is refused while Live is on here, in the phone's words", async () => {
  assert.equal(CH.CONTINUE_LIVE, "Jarvis Live is on here. End Live first, then continue the chat.");
  assert.match(await (await import("node:fs/promises")).readFile(new URL("../src/main.js", import.meta.url), "utf8"),
    /if \(!moved && liveOnHere\(\)\) \{[\s\S]{0,300}CONTINUE_LIVE/);
});

await check("the delete sentences say what stays, the same in every dialog", async () => {
  assert.equal(CH.DELETE_STAYS,
    "Facts Jarvis learned stay. Copies in older backups stay until they age out.");
  assert.equal(CH.DELETE_STAYS_TICKED,
    "Facts you did not tick stay. Copies in older backups stay until they age out.");
  const named = eraseAlsoChatNamedConfirm({ title: "Dentist", kind: "chat" }, "Today 14:05", 3);
  assert.match(named, /3 other facts Jarvis learned in that chat stay\. Copies in older backups stay until they age out\./);
  const one = eraseAlsoChatNamedConfirm({ title: "Dentist", kind: "chat" }, "Today 14:05", 1);
  assert.match(one, /1 other fact Jarvis learned in that chat stays\./);
  const none = eraseAlsoChatNamedConfirm({ title: "Dentist", kind: "chat" }, "Today 14:05");
  assert.ok(none.includes(CH.DELETE_STAYS), "no count: the general sentence");
  const sup = eraseAlsoChatNamedConfirm({ title: "Refund", kind: "support" }, "Today 14:05", 0);
  assert.match(sup, /customer-support chat/);
  assert.ok(named.endsWith("OK: delete that chat too.\nCancel: keep the chat."));
});

await check("what a chat taught, read only", async () => {
  assert.equal(chatFactsTaught(0), "Jarvis is not using any fact it learned from this chat.");
  assert.equal(chatFactsTaught(1), "Jarvis learned 1 fact from this chat, and still uses it:");
  assert.equal(chatFactsTaught(3), "Jarvis learned 3 facts from this chat, and still uses them:");
  assert.match(chatFactsTaughtHidden(2), /hidden, so they are not shown here\./);
});

/* -- the real frontend ---------------------------------------------------- */

const { base, close } = await K.serve();
const browser = await K.launch();
const route = (r) => "\u001fjarvis-route:" + JSON.stringify(r);
const NOW = Math.floor(Date.now() / 1000);

async function bar(extra = {}) {
  const page = await K.open(browser, base, "index.html", { chatReplies: [], ...extra },
    { width: 760, height: 900 });
  await page.waitForTimeout(250);
  return page;
}
async function ask(page, text) {
  await page.fill("#prompt", text);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(350);
}

await check("the bar: the question is shown above its answer, and the thread opens on its newest end", async () => {
  const replies = Array.from({ length: 12 }, (_, i) => `Answer ${i + 1}.`);
  const page = await bar({ chatReplies: replies });
  for (let i = 1; i <= 12; i++) await ask(page, `Question ${i}?`);
  const you = await page.locator("#you-line").innerText();
  const summary = await page.locator("#previous-answer-summary").innerText();
  await page.locator("#previous-answer-summary").click();
  await page.waitForTimeout(250);
  const line = await page.locator(".thread-reads-from").allInnerTexts();
  const above = await page.locator(".thread-reads-from").evaluate(
    (n) => [...n.parentElement.children].slice(0, [...n.parentElement.children].indexOf(n))
      .filter((c) => c.classList.contains("thread-turn")).length);
  const scroll = await page.locator("#previous-answer-body").evaluate(
    (n) => ({ atEnd: n.scrollTop + n.clientHeight >= n.scrollHeight - 4, scrolls: n.scrollHeight > n.clientHeight }));
  const role = await page.locator("#previous-answer-body").getAttribute("role");
  const label = await page.locator("#previous-answer-body").getAttribute("aria-label");
  const tab = await page.locator("#previous-answer-body").getAttribute("tabindex");
  await page.close();
  assert.equal(you, "You: Question 12?");
  assert.equal(summary, "Earlier in this chat · 11 questions");
  assert.deepEqual(line, [CH.THREAD_READS_FROM]);
  assert.equal(above, 5, "the line is drawn where the model's window starts (12 in the thread, 7 re-sent)");
  assert.equal(scroll.scrolls, true, "the test thread is too short to scroll");
  assert.equal(scroll.atEnd, true, "the thread opened on its OLDEST end");
  assert.equal(role, "region");
  assert.equal(label, "Earlier in this chat");
  assert.equal(tab, "0", "a scrolling region the keyboard cannot reach");
});

await check("the bar: a crisis question and its answer never join the thread or the model's history", async () => {
  const HELP = "I'm really sorry you're going through this. In the US, call or text **988**.";
  const page = await bar({ chatReplies: ["Tuesday at 3.", [route({ wellbeing: "crisis" }), HELP], "Fine, thanks."] });
  await ask(page, "when is the dentist?");
  await ask(page, "I want to hurt myself");
  // The help answer shows once, on screen, as the current answer.
  const shown = await page.locator("#answer").innerText();
  const panel = await page.locator("#answer").evaluate((n) => n.classList.contains("wellbeing-crisis"));
  const foldedNow = await page.locator("#previous-answer-body").textContent();
  await ask(page, "how are you?");
  const thread = await page.locator("#previous-answer-body").textContent();
  const summary = await page.locator("#previous-answer-summary").innerText();
  const answerNow = await page.locator("#answer").innerText();
  const sent = await page.evaluate(() => (window.__calls || []).filter((c) => c[0] === "stream_chat").map((c) => c[1]));
  await page.close();
  assert.match(shown, /988/);
  assert.equal(panel, true, "the help answer is not drawn as the calm panel");
  assert.doesNotMatch(foldedNow, /hurt myself|988/, "the crisis pair was in the thread while it was on screen");
  assert.match(thread, /when is the dentist\?/);
  assert.doesNotMatch(thread, /hurt myself|988|sorry you're going through/, "the crisis pair stayed in the thread");
  assert.equal(summary, "Earlier in this chat · 1 question");
  assert.doesNotMatch(answerNow, /988/, "the help answer stayed on screen after the next question");
  const third = JSON.stringify(sent.at(-1));
  assert.ok(!third.includes("hurt myself") && !third.includes("988"), "the crisis pair was re-sent to the model");
  assert.ok(third.includes("when is the dentist?"), "an ordinary earlier question is still re-sent");
});

await check("the bar: no thread under Hide memory lists, until Show; the answer on screen stays", async () => {
  const hidden = await bar({ chatReplies: ["One.", "Two."], security: { hidden: true } });
  await ask(hidden, "First?");
  await ask(hidden, "Second?");
  const folded = await hidden.locator("#previous-answer").isHidden();
  const youHidden = await hidden.locator("#you-line").innerText();
  const answer = await hidden.locator("#answer").innerText();
  await hidden.close();
  const shown = await bar({ chatReplies: ["One.", "Two."], security: { hidden: true, revealed: true } });
  await ask(shown, "First?");
  await ask(shown, "Second?");
  const visible = await shown.locator("#previous-answer").isVisible();
  await shown.close();
  assert.equal(folded, true, "the thread of earlier answers was drawn while the lists are hidden");
  assert.equal(youHidden, "You: Second?", "the question being answered is not chat history");
  assert.match(answer, /Two\./);
  assert.equal(visible, true, "shown lists: the thread comes back");
});

await check("the bar: New conversation says where the chat went, and a game says nothing was kept", async () => {
  const page = await bar({ chatReplies: ["Tuesday at 3."] });
  await ask(page, "when is the dentist?");
  await page.locator("#new-conversation").click();
  await page.waitForTimeout(200);
  const note = await page.locator("#chat-ended-note").innerText();
  const youGone = await page.locator("#you-line").isHidden();
  await page.close();
  assert.equal(note, CH.ENDED_SAVED, "New conversation ended a kept chat without a word");
  assert.equal(youGone, true);

  const game = await bar({ chatReplies: [[route({ temporary: true, lane: "qwen3:8b", where: "local" }),
    "The dragon roars."]] });
  await ask(game, "let's play a text adventure");
  const strip = await game.locator("#temporary-strip").innerText();
  const state = await game.locator("#temporary-strip").getAttribute("data-state");
  await game.keyboard.press("Escape");
  await game.waitForTimeout(200);
  const ended = await game.locator("#chat-ended-note").innerText();
  const stripGone = await game.locator("#temporary-strip").isHidden();
  await game.close();
  assert.match(strip, /^Temporary chat/);
  assert.match(strip, /looks like a game/);
  assert.equal(state, "game");
  assert.equal(ended, CH.ENDED_TEMPORARY, "a game ending said Kept chats are in History");
  assert.equal(stripGone, true);
});

await check("the bar: coming back to it grows it to its content again", async () => {
  const page = await bar({ chatReplies: ["Tuesday at 3."] });
  await ask(page, "when is the dentist?");
  const before = await page.evaluate(() => (window.__calls || [])
    .filter((c) => c[0] === "resize_quickbar").map((c) => c[1].height));
  await page.evaluate(() => window.__emit("focus-input", {}));
  await page.waitForTimeout(300);
  const after = await page.evaluate(() => (window.__calls || [])
    .filter((c) => c[0] === "resize_quickbar").map((c) => c[1].height));
  await page.close();
  assert.ok(after.length > before.length, "Rust sets the bar short when it is shown, and nothing grew it back");
  assert.ok(after.at(-1) > 100, `the height sent was ${after.at(-1)}`);
});

/* -- the Brain's History --------------------------------------------------- */

const LIST = [
  { id: "conv-live-0001", title: "Planning the weekend", started: NOW - 7200, updated: NOW - 6480, turns: 8,
    device: "desktop", has_voice: true, tainted: false, kind: "live" },
  { id: "conv-supp-0001", title: "Groupon refund", started: NOW - 9000, updated: NOW - 8800, turns: 12,
    device: "desktop", has_voice: false, tainted: true, kind: "support" },
  { id: "conv-chat-0001", title: "Dentist on Tuesday", started: NOW - 9600, updated: NOW - 9500, turns: 2,
    device: "phone", has_voice: false, tainted: false, kind: "chat" },
];
const TRANSCRIPTS = {
  "conv-live-0001": { id: "conv-live-0001", title: "Planning the weekend", kind: "live", tainted: false,
    turns: [{ role: "user", text: "the dentist called about the weekend", at: NOW - 7000, provenance: "voice" },
      { role: "assistant", text: "Noted.", at: NOW - 6990 }] },
  "conv-supp-0001": { id: "conv-supp-0001", title: "Groupon refund", kind: "support", tainted: true,
    continuable: false, continue_why: "A customer-support record can't be continued.",
    turns: [{ role: "support", text: "We can refund the dentist voucher", provenance: "support_company",
      read_outside: true, at: NOW - 8900 }] },
  "conv-chat-0001": { id: "conv-chat-0001", title: "Dentist on Tuesday", kind: "chat", tainted: true,
    turns: [{ role: "user", text: "when is the dentist?", at: NOW - 9550, provenance: "typed", read_outside: true },
      { role: "assistant", text: "Tuesday at 3.", at: NOW - 9540 }] },
};

async function historyTab(history = {}, extra = {}) {
  const page = await K.open(browser, base, "brain.html", { history, ...extra },
    { width: 1000, height: 900 });
  await page.locator("#tab-history").click();
  await page.waitForTimeout(300);
  return page;
}

await check("History: every row's Open and Delete name their chat", async () => {
  const page = await historyTab({ conversations: LIST, transcripts: TRANSCRIPTS });
  const names = await page.locator("#history-list .row-item button").evaluateAll(
    (bs) => bs.map((b) => b.getAttribute("aria-label")));
  await page.close();
  assert.deepEqual(names, [
    "Open Planning the weekend", "Delete Planning the weekend",
    "Open Groupon refund", "Delete Groupon refund",
    "Open Dentist on Tuesday", "Delete Dentist on Tuesday"]);
});

await check("History: a search keeps each row's kind, and combines with Show", async () => {
  const page = await historyTab({ conversations: LIST, transcripts: TRANSCRIPTS });
  await page.fill("#history-filter", "dentist");
  await page.waitForTimeout(700);
  const all = await page.locator("#history-list .row-item").allInnerTexts();
  const kinds = await page.evaluate(() => window.__history.searchKinds);
  await page.locator("#history-kind").selectOption("live");
  await page.waitForTimeout(900);
  const live = await page.locator("#history-list .row-item").allInnerTexts();
  const kinds2 = await page.evaluate(() => window.__history.searchKinds);
  await page.close();
  assert.equal(all.length, 3, "three kinds all mention the dentist");
  assert.ok(all.some((t) => /Support chat/.test(t)), "a search result lost its kind tag");
  assert.ok(all.some((t) => /Live · /.test(t)), "a Live result lost its length");
  assert.equal(kinds.at(0), null, "no kind chosen: none asked for");
  assert.equal(kinds2.at(-1), "live", "Show did not reach the search");
  assert.equal(live.length, 1);
  assert.match(live[0], /Planning the weekend/);
});

await check("History: deleting a support chat from a search result still asks its own question", async () => {
  const page = await historyTab({ conversations: LIST, transcripts: TRANSCRIPTS });
  await page.fill("#history-filter", "voucher");
  await page.waitForTimeout(700);
  const asked = [];
  page.on("dialog", (d) => { asked.push(d.message()); d.dismiss(); });
  await page.locator("#history-list .row-item", { hasText: "Groupon" })
    .getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(300);
  const deleted = await page.evaluate(() => window.__history.deleted);
  await page.close();
  assert.equal(asked.length, 1);
  assert.match(asked[0], /customer-support chat/);
  assert.deepEqual(deleted, [], "a support record was deleted without asking");
});

await check("History: an opened chat says what it taught, read only; a support record says nothing", async () => {
  const facts = { "conv-chat-0001": [
    { id: 41, text: "Owner's dentist is on Mill Road", created: NOW - 600, source: "auto" },
    { id: 42, text: "Owner sees the dentist on Tuesdays", created: NOW - 500, source: "auto" }] };
  const page = await historyTab({ conversations: LIST, transcripts: TRANSCRIPTS, chatFacts: facts });
  await page.getByRole("button", { name: "Open Dentist on Tuesday" }).click();
  await page.waitForTimeout(400);
  const taught = await page.locator(".history-facts-taught").innerText();
  const buttons = await page.locator(".history-facts-taught button").count();
  await page.getByRole("button", { name: "Close Dentist on Tuesday" }).click();
  await page.getByRole("button", { name: "Open Groupon refund" }).click();
  await page.waitForTimeout(400);
  const support = await page.locator(".history-facts-taught").count();
  await page.close();
  assert.match(taught, /Jarvis learned 2 facts from this chat, and still uses them:/);
  assert.match(taught, /Owner's dentist is on Mill Road/);
  assert.equal(buttons, 0, "an opened chat's list is for reading, not for changing");
  assert.equal(support, 0);
  const none = await historyTab({ conversations: LIST, transcripts: TRANSCRIPTS, chatFacts: {} });
  await none.getByRole("button", { name: "Open Dentist on Tuesday" }).click();
  await none.waitForTimeout(400);
  const noneText = await none.locator(".history-facts-taught").innerText();
  await none.close();
  assert.equal(noneText, "Jarvis is not using any fact it learned from this chat.");
});

await check("History: 'read outside text' marks the answer that read it, and a record says whose words", async () => {
  const page = await historyTab({ conversations: LIST, transcripts: TRANSCRIPTS });
  await page.getByRole("button", { name: "Open Dentist on Tuesday" }).click();
  await page.waitForTimeout(300);
  const turns = await page.locator("#history-transcript .history-turn").evaluateAll(
    (els) => els.map((e) => [e.dataset.role, e.querySelector(".history-mark-taint") !== null]));
  const chatNote = await page.locator("#history-transcript .history-taint-note").innerText();
  await page.getByRole("button", { name: "Close Dentist on Tuesday" }).click();
  await page.getByRole("button", { name: "Open Groupon refund" }).click();
  await page.waitForTimeout(300);
  const supportNote = await page.locator("#history-transcript .history-taint-note").innerText();
  await page.close();
  assert.deepEqual(turns, [["user", false], ["assistant", true]]);
  assert.match(chatNote, /a web page, a file, an email/);
  assert.match(supportNote, /company's words/);
  assert.doesNotMatch(supportNote, /web page/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe thread and History are as the second chat audit asked");
process.exit(fails.length ? 1 : 0);
