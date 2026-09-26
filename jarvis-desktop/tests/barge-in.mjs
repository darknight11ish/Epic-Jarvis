/**
 * "Interrupt Jarvis while it talks" on the PC (barge-in.js), the desktop
 * twin of the phone's switch (StopWord.kt `BargeIn`).
 *
 * What it controls here: while this PC listens for "hey Jarvis", the words
 * "stop" and "hey Jarvis" cut a reply off (voice.rs emits
 * `voice-speech-started`), and a "hey Jarvis" sentence heard over the reply
 * is sent as a new question (`voice-heard`). ON, the default, keeps that -
 * it is how the PC always behaved. OFF: while Jarvis is talking, all of it is
 * ignored; the reply plays to the end, or until Esc closes the bar. Only
 * while talking: once the reply ends, "hey Jarvis" works as before.
 *
 * The same scenarios as tests/voice-speech.mjs's barge-in checks, with the
 * switch off.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";
import * as B from "../src/barge-in.js";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const quickbar = (data) => K.open(browser, base, "index.html", data);
const settings = () => K.open(browser, base, "settings.html", {}, { width: 760, height: 1400 });
const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });
const speakCalls = (page) => page.evaluate(() =>
  (window.__voiceCalls || []).filter((c) => Array.isArray(c) && c[0] === "speak").map((c) => c[1]));
const chats = (page) => page.evaluate(() =>
  (window.__calls || []).filter(([cmd]) => cmd === "stream_chat").length);
const spoken = (page) => page.evaluate(() =>
  [...document.querySelectorAll("[aria-live]")].map((n) => n.textContent).join(" | "));
const switchOff = (page) => page.evaluate((key) => localStorage.setItem(key, "off"), B.BARGE_IN_KEY);

/** A voice question whose three-sentence answer is being spoken slowly. */
async function talking(page) {
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(100);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(60);
}
const SLOW_ANSWER = {
  heard: K.HEARD_OWNER,
  chatReplies: [[delta("One. "), delta("Two. "), delta("Three. ")], [delta("Other. ")]],
  speakDelayMs: 150,
};

/* ── The setting ────────────────────────────────────────────────────────── */

await check("the setting: on unless saved off, and on when storage cannot be read", async () => {
  const mem = (v) => ({ getItem: () => v, setItem() {} });
  assert.equal(B.loadBargeIn(mem(null)), true);
  assert.equal(B.loadBargeIn(mem("on")), true);
  assert.equal(B.loadBargeIn(mem("off")), false);
  assert.equal(B.loadBargeIn({ getItem() { throw new Error("private mode"); } }), true);
  assert.equal(B.loadBargeIn(null), true);
  const store = new Map();
  const real = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  assert.equal(B.saveBargeIn(false, real), true);
  assert.equal(B.loadBargeIn(real), false);
  assert.equal(B.saveBargeIn(true, { setItem() { throw new Error("full"); } }), false);
  // Ignored only with the switch off AND Jarvis talking.
  assert.equal(B.ignoreWhileTalking(true, true), false);
  assert.equal(B.ignoreWhileTalking(false, false), false);
  assert.equal(B.ignoreWhileTalking(false, true), true);
  // The words say what happens on a PC: "ignored", never "not listening".
  assert.match(B.describeBargeIn(true), /^On: while Jarvis talks, this PC keeps listening\. Say "stop"/);
  assert.match(B.describeBargeIn(false), /^Off: while Jarvis talks, what this PC hears is ignored, even "stop" and "hey Jarvis"\./);
  assert.match(B.describeBargeIn(false), /press Esc in the Jarvis bar/);
  assert.doesNotMatch(B.describeBargeIn(false), /not listen/);
});

await check("Settings: the switch is on by default, says what it does, and turning it off is saved", async () => {
  const page = await settings();
  const before = await page.evaluate(() => ({
    checked: document.getElementById("voice-barge-in").checked,
    label: document.getElementById("voice-barge-in").closest("label").innerText,
  }));
  assert.equal(before.checked, true);
  assert.match(before.label, /Interrupt Jarvis while it talks/);
  assert.ok(before.label.includes(B.describeBargeIn(true)));
  await page.locator("#voice-barge-in").click();
  await page.waitForTimeout(100);
  const after = await page.evaluate((key) => ({
    checked: document.getElementById("voice-barge-in").checked,
    saved: localStorage.getItem(key),
    label: document.getElementById("voice-barge-in").closest("label").innerText,
  }), B.BARGE_IN_KEY);
  await page.reload();
  await page.waitForTimeout(300);
  const reopened = await page.evaluate(() => document.getElementById("voice-barge-in").checked);
  const errors = page.__errors;
  await page.close();
  assert.equal(after.checked, false);
  assert.equal(after.saved, "off");
  assert.ok(after.label.includes(B.describeBargeIn(false)));
  assert.equal(reopened, false, "the setting did not survive reopening Settings");
  assert.deepEqual(errors, []);
});

await check("Settings: the switch works even when Jarvis could not be asked about voice", async () => {
  const page = await K.open(browser, base, "settings.html",
    { voice: { getFails: "Jarvis is not answering at http://127.0.0.1:4719. Is it running?" } },
    { width: 760, height: 1400 });
  const s = await page.evaluate(() => ({
    hidden: document.getElementById("voice-barge-in").closest("label").offsetParent === null,
    disabled: document.getElementById("voice-barge-in").disabled,
  }));
  await page.close();
  assert.equal(s.hidden, false);
  assert.equal(s.disabled, false);
});

/* ── The Jarvis bar ─────────────────────────────────────────────────────── */

await check("ON (the default): \"stop\" or \"hey Jarvis\" still cuts a reply off, as before", async () => {
  const page = await quickbar(SLOW_ANSWER);
  await talking(page);
  await page.evaluate(() => window.__emit("voice-speech-started", null));
  await page.waitForTimeout(600);
  const said = await speakCalls(page);
  await page.close();
  assert.ok(!said.includes("Two.") && !said.includes("Three."), `not cut off: ${JSON.stringify(said)}`);
});

await check("OFF: \"stop\" or \"hey Jarvis\" heard while Jarvis talks is ignored, and the reply plays to the end", async () => {
  const page = await quickbar(SLOW_ANSWER);
  await switchOff(page);
  await talking(page);
  await page.evaluate(() => window.__emit("voice-speech-started", null));
  await page.waitForTimeout(900);
  const said = await speakCalls(page);
  await page.close();
  assert.deepEqual(said, ["One.", "Two.", "Three."], "the reply was cut off with the switch off");
});

await check("OFF: a \"hey Jarvis\" question heard while Jarvis talks is not sent", async () => {
  const page = await quickbar(SLOW_ANSWER);
  await switchOff(page);
  await talking(page);
  const first = await chats(page);
  await page.evaluate((heard) => window.__emit("voice-heard", { ...heard, text: "what time is it" }), K.HEARD_OWNER);
  await page.waitForTimeout(200);
  const after = await chats(page);
  await page.close();
  assert.equal(first, 1);
  assert.equal(after, 1, "a question heard over the reply was sent");
});

await check("OFF: once Jarvis has finished, \"hey Jarvis\" works as before", async () => {
  const page = await quickbar(SLOW_ANSWER);
  await switchOff(page);
  await talking(page);
  await page.waitForTimeout(1200); // all three sentences spoken
  await page.evaluate((heard) => window.__emit("voice-heard", { ...heard, text: "and tomorrow" }), K.HEARD_OWNER);
  await page.waitForTimeout(200);
  const n = await chats(page);
  await page.close();
  assert.equal(n, 2, "a question after the reply was dropped");
});

await check("OFF: the listening line says what is heard over a reply is ignored, instead of promising \"stop\"", async () => {
  const page = await quickbar({});
  await switchOff(page);
  await page.evaluate(() => {
    window.__listenInfo = { echoCancelling: true, microphone: "Microphone (USB Headset)", note: null };
  });
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(200);
  const line = await spoken(page);
  const errors = page.__errors;
  await page.close();
  assert.match(line, /Listening for "hey Jarvis" on Microphone \(USB Headset\)\. While Jarvis talks, what it hears is ignored/);
  assert.doesNotMatch(line, /Say "stop"/);
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\n\"Interrupt Jarvis while it talks\" holds");
process.exit(fails.length ? 1 : 0);
