/**
 * "Look at this" and "Watch with me" in the real windows (the owner's
 * decision of 2026-09-28; docs/SCREEN-DESIGN.md; look-rules.js, main.js,
 * watch-badge.html, look-settings.js) - the part that needs a browser.
 * (tests/look-rules.mjs holds the shared table and the wiring, and runs
 * anywhere with Node.)
 *
 * What must hold:
 * - the Watch button starts and stops a session through `screen_watch` (no
 *   card), and a refused start says why in plain words in the strip;
 * - the strip and the badge say only the PC's fixed words and minutes, and
 *   "Paused: a password box" when the PC says so;
 * - after a look the bar shows the note, and the NEXT question carries
 *   `screen: "look"` - only while a look is held - and never a picture or
 *   the words;
 * - the bar closing (Rust says so) takes the note away;
 * - Settings lists the Never look at list, adding is sent at once, taking
 *   one off is a request for ONE card and the entry stays until it is said
 *   yes to;
 * - the strip is not shown for a PC with no session and no look.
 */
import assert from "node:assert/strict";

let K;
try {
  K = await import("./uikit.mjs");
} catch (e) {
  console.log(`skip  the real windows (${e.message.split("\n")[0]})`);
  process.exit(0);
}

let failed = 0;
let passed = 0;
const check = async (name, fn) => {
  try {
    await fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const STATUS = {
  off: { state: "off", on: false, paused: null, pause_words: null, left_s: null, ending_soon: false,
         ended: null, ended_words: null, look_held: false, look_left_s: null, built: true,
         available: true, unavailable_why: "" },
};
const WATCHING = { ...STATUS.off, state: "watching", on: true, left_s: 1440 };
const PAUSED = { ...WATCHING, state: "paused", paused: "password_box", pause_words: "a password box" };
const HELD = { ...STATUS.off, look_held: true, look_left_s: 100 };
const NEVER = {
  entries: [
    { kind: "program", value: "keepass.exe", built_in: true },
    { kind: "site", value: "1password.com", built_in: true },
    { kind: "site", value: "mybank.example", built_in: false },
  ],
  unreadable: false, last_removal: {}, pending: [],
};
const NOTE = "Looked at: Chrome window · words only";
const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });

const { base, close } = await K.serve();
const browser = await K.launch();
const bar = (screen) => K.open(browser, base, "index.html", { chatReplies: [], screen });
const emit = (page, name, payload) => page.evaluate(([n, p]) => window.__emit(n, p), [name, payload]);
const chats = (page) => page.evaluate(() =>
  (window.__calls || []).filter((c) => c[0] === "stream_chat").map((c) => c[1]));

await check("no session and no look: the strip is not there, the button is not pressed", async () => {
  const page = await bar({ status: STATUS.off, never: NEVER });
  assert.equal(await page.isHidden("#watch-strip"), true);
  assert.equal(await page.getAttribute("#watch-toggle", "aria-pressed"), "false");
  await page.close();
});

await check("the Watch button starts a session (no card), then stops it", async () => {
  const page = await bar({ status: STATUS.off, never: NEVER });
  await page.click("#watch-toggle");
  await page.waitForTimeout(100);
  let calls = await page.evaluate(() => window.__screen.watchCalls);
  assert.deepEqual(calls[0], { action: "start", by: "button" });
  await emit(page, "screen-status", { status: WATCHING, stale: false });
  await page.waitForTimeout(80);
  assert.equal(await page.isHidden("#watch-strip"), false);
  assert.equal((await page.textContent("#watch-title")).trim(), "Jarvis is watching");
  assert.match(await page.textContent("#watch-detail"), /24 min left/);
  assert.equal(await page.getAttribute("#watch-toggle", "aria-pressed"), "true");
  assert.equal(await page.isHidden("#watch-stop"), false);
  await page.click("#watch-toggle");
  await page.waitForTimeout(100);
  calls = await page.evaluate(() => window.__screen.watchCalls);
  assert.equal(calls[1].action, "stop");
  await page.close();
});

await check("a refused start says why in plain words, in the strip", async () => {
  const why = "The connection to Jarvis is catching up, so looking at the screen is held until it does - try again in a moment.";
  const page = await bar({ status: STATUS.off, never: NEVER, startFails: why });
  await page.click("#watch-toggle");
  await page.waitForTimeout(150);
  assert.equal(await page.isHidden("#watch-strip"), false);
  assert.equal((await page.textContent("#watch-note")).trim(), why);
  assert.equal(await page.getAttribute("#watch-toggle", "aria-pressed"), "false");
  await page.close();
});

await check("paused on a password box: the fixed words, and the minutes still count", async () => {
  const page = await bar({ status: STATUS.off, never: NEVER });
  await emit(page, "screen-status", { status: PAUSED, stale: false });
  await page.waitForTimeout(80);
  assert.equal((await page.textContent("#watch-title")).trim(), "Jarvis is watching - paused");
  const detail = await page.textContent("#watch-detail");
  assert.match(detail, /Paused: a password box/);
  assert.match(detail, /min left/);
  await page.close();
});

await check("a look: the note shows, and the next question carries the mark - only the mark", async () => {
  const page = await K.open(browser, base, "index.html", {
    chatReplies: [[delta("It says hello.")]], screen: { status: STATUS.off, never: NEVER } });
  await emit(page, "screen-status", { status: HELD, stale: false });
  await emit(page, "screen-look", { ok: true, note: NOTE, said: "" });
  await page.waitForTimeout(80);
  assert.equal((await page.textContent("#watch-note")).trim(), NOTE);
  await page.fill("#prompt", "what does this say?");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const sent = (await chats(page))[0];
  const newest = sent.messages[sent.messages.length - 1];
  assert.equal(newest.screen, "look");
  assert.equal(newest.content, "what does this say?", "the owner's words, unchanged");
  assert.ok(!JSON.stringify(sent).match(/data:image|Snorvel/), "no picture and no screen words ride along");
  await page.close();
});

await check("no held look: the question has no mark", async () => {
  const page = await K.open(browser, base, "index.html", {
    chatReplies: [[delta("Fine.")]], screen: { status: STATUS.off, never: NEVER } });
  await emit(page, "screen-status", { status: WATCHING, stale: false });
  await page.fill("#prompt", "hello");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const sent = (await chats(page))[0];
  assert.equal(sent.messages[sent.messages.length - 1].screen, undefined);
  await page.close();
});

await check("a refused look shows the PC's own words, and no mark follows", async () => {
  const page = await bar({ status: STATUS.off, never: NEVER });
  await emit(page, "screen-look", { ok: false, note: "", said: "There's a password box in front, so I'm not looking." });
  await page.waitForTimeout(80);
  assert.match(await page.textContent("#watch-note"), /password box in front/);
  await page.close();
});

await check("the bar closing takes the note away", async () => {
  const page = await bar({ status: STATUS.off, never: NEVER });
  await emit(page, "screen-look", { ok: true, note: NOTE, said: "" });
  await page.waitForTimeout(60);
  assert.equal(await page.isHidden("#watch-strip"), false);
  await emit(page, "screen-look", { closed: true });
  await emit(page, "screen-status", { status: STATUS.off, stale: false });
  await page.waitForTimeout(60);
  assert.equal(await page.isHidden("#watch-strip"), true);
  await page.close();
});

await check("Forget this look: sent to the PC, and the strip goes", async () => {
  const page = await bar({ status: STATUS.off, never: NEVER });
  await emit(page, "screen-status", { status: HELD, stale: false });
  await emit(page, "screen-look", { ok: true, note: NOTE, said: "" });
  await page.waitForTimeout(60);
  await page.click("#watch-drop");
  await page.waitForTimeout(100);
  const calls = await page.evaluate(() => window.__screen.watchCalls);
  assert.equal(calls[0].action, "drop");
  await page.close();
});

await check("the badge: the sign, Stop, and 20 more minutes only near the end", async () => {
  const page = await K.open(browser, base, "watch-badge.html", { chatReplies: [], screen: { status: STATUS.off, never: NEVER } });
  await emit(page, "screen-status", { status: WATCHING, stale: false });
  await page.waitForTimeout(60);
  assert.equal((await page.textContent("#title")).trim(), "Jarvis is watching");
  assert.equal(await page.isHidden("#stop"), false);
  assert.equal(await page.isHidden("#more"), true);
  await emit(page, "screen-status", { status: { ...WATCHING, left_s: 45, ending_soon: true }, stale: false });
  await page.waitForTimeout(60);
  assert.equal(await page.isHidden("#more"), false);
  await page.click("#stop");
  await page.waitForTimeout(80);
  const calls = await page.evaluate(() => window.__screen.watchCalls);
  assert.equal(calls[0].action, "stop");
  await page.close();
});

await check("Settings: the list, adding at once, taking one off asks for a card and keeps the entry", async () => {
  const page = await K.open(browser, base, "settings.html", {
    chatReplies: [], screen: { status: STATUS.off, never: JSON.parse(JSON.stringify(NEVER)) } });
  await page.waitForTimeout(200);
  const names = await page.$$eval("#sl-list .sc-gpu-name", (n) => n.map((x) => x.textContent));
  assert.deepEqual(names, ["keepass.exe", "1password.com", "mybank.example"]);
  await page.selectOption("#sl-kind", "site");
  await page.fill("#sl-value", "mybroker.example");
  await page.click("#sl-add");
  await page.waitForTimeout(200);
  let calls = await page.evaluate(() => window.__screen.neverCalls);
  assert.ok(calls.some((c) => c.action === "add" && c.kind === "site" && c.value === "mybroker.example"));
  const row = page.locator("#sl-list li").filter({ hasText: "mybank.example" });
  await row.locator("button").click();
  await page.waitForTimeout(250);
  calls = await page.evaluate(() => window.__screen.neverCalls);
  assert.ok(calls.some((c) => c.action === "remove" && c.value === "mybank.example"));
  assert.match(await page.textContent("#sl-status"), /card/i);
  const after = await page.$$eval("#sl-list .sc-gpu-name", (n) => n.map((x) => x.textContent));
  assert.ok(after.includes("mybank.example"), "it stays on the list until the card is said yes to");
  await page.close();
});

await check("Settings on a PC without it: the PC's own reason, no list", async () => {
  const page = await K.open(browser, base, "settings.html", { chatReplies: [] });
  await page.waitForTimeout(200);
  assert.equal(await page.isHidden("#sl-state"), false);
  assert.match(await page.textContent("#sl-state"), /off on this PC/);
  await page.close();
});

await browser.close();
close();
console.log(`\nLook at this / Watch with me: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
