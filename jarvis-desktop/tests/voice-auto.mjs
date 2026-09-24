/**
 * Automatic (VAD) listening: the #voice-auto toggle, its mutual exclusion
 * with push-to-talk, and the voice-heard event it drives - all against the
 * mock, since none of this has run against a real microphone.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const quickbar = (data) => K.open(browser, base, "index.html", data);
const calls = (page) => page.evaluate(() => window.__voiceCalls || []);
const invokes = (page) => page.evaluate(() => window.__calls || []);

await check("toggling #voice-auto on starts automatic listening", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const micAuto = await page.locator("#mic").getAttribute("data-auto");
  const voice = await calls(page);
  await page.close();
  assert.equal(pressed, "true");
  assert.equal(micAuto, "true");
  assert.ok(voice.includes("auto-start"), JSON.stringify(voice));
});

await check("toggling it off again stops automatic listening", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const micAuto = await page.locator("#mic").getAttribute("data-auto");
  const voice = await calls(page);
  await page.close();
  assert.equal(pressed, "false");
  assert.equal(micAuto, null);
  assert.deepEqual(voice, ["auto-start", "auto-stop"]);
});

await check("a failed start leaves the toggle unpressed", async () => {
  const page = await quickbar({ autoListenFails: "no microphone was found" });
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const micAuto = await page.locator("#mic").getAttribute("data-auto");
  await page.close();
  assert.equal(pressed, "false");
  assert.equal(micAuto, null);
});

await check("while automatic listening is on, holding #mic does not start push-to-talk", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(120);
  await page.mouse.up();
  await page.waitForTimeout(100);
  const voice = await calls(page);
  await page.close();
  assert.deepEqual(voice, ["auto-start"], "push-to-talk ran while automatic listening owned the mic");
});

await check("a voice-heard event from the owner sends a real chat turn", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(200);
  const sent = await invokes(page);
  await page.close();
  const chat = sent.find(([cmd]) => cmd === "stream_chat");
  assert.ok(chat, "no stream_chat call was made");
  assert.ok(JSON.stringify(chat[1]).includes(K.HEARD_OWNER.text));
});

await check("a voice-heard event from a stranger sends nothing", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_STRANGER);
  await page.waitForTimeout(200);
  const sent = await invokes(page);
  await page.close();
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"), "ambient speech from someone else reached the chat turn");
});

await check('"hey Jarvis." on its own (awake) sends nothing and keeps listening', async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard),
    { ...K.HEARD_OWNER, text: "", wakeHeard: true, awake: true, awakeSeconds: 8 });
  await page.waitForTimeout(200);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const sent = await invokes(page);
  await page.close();
  assert.equal(pressed, "true");
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"), "an empty wake-only clip reached the chat");
});

await check("the toggle names the wake word, not 'automatic'", async () => {
  const page = await quickbar({});
  const title = await page.locator("#voice-auto").getAttribute("title");
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  const micTitle = await page.locator("#mic").getAttribute("title");
  await page.close();
  assert.ok(title.includes("hey Jarvis"), title);
  assert.ok(micTitle.includes("hey Jarvis"), micTitle);
});

await check("an unavailable engine turns automatic listening off and sends nothing", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_UNAVAILABLE);
  await page.waitForTimeout(200);
  const pressed = await page.locator("#voice-auto").getAttribute("aria-pressed");
  const voice = await calls(page);
  const sent = await invokes(page);
  await page.close();
  assert.equal(pressed, "false", "automatic listening should have turned itself off");
  assert.ok(voice.includes("auto-stop"), JSON.stringify(voice));
  assert.ok(!sent.some(([cmd]) => cmd === "stream_chat"));
});

// T2 (audit 3): the loopback rule was checked only when listening started,
// while every clip and every Smart Turn check read the address again. These
// read the Rust: the rule must run before EACH send, on the very address
// the send then uses, and a changed address must stop listening.
const rustSrc = (rel) => fs.readFileSync(new URL(`../src-tauri/src/${rel}`, import.meta.url), "utf8");
const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL (Rust): every wake-word clip and turn check is re-checked for loopback, on the address it is sent to", async () => {
  const voice = rustSrc("voice.rs");
  const loop = fnBody(voice, "fn run_vad_loop(");
  for (const send of ["ask_turn(", "post_utterance("]) {
    const at = loop.indexOf(send);
    assert.ok(at > -1, `run_vad_loop no longer calls ${send}`);
    const before = loop.slice(0, at);
    const check = before.lastIndexOf("wake_audio_refusal(&base)");
    const read = before.lastIndexOf("let base = jarvis_base(app);");
    assert.ok(check > -1 && read > -1 && read < check, `${send} is not preceded by its own loopback check`);
    // Nothing between the check and the send may read the address again.
    assert.doesNotMatch(before.slice(check), /jarvis_base\(/, `${send} re-reads the address after the check`);
    assert.match(before.slice(check), /stop_listening_because\(app, why\);\s*return;/);
  }
  assert.match(loop, /ask_turn\(\s*app, &base,/);
  assert.match(loop, /post_utterance\(\s*&app,\s*&base,/);
  // The senders use the address they are given, never their own read.
  for (const sig of ["async fn ask_turn(", "async fn post_utterance("]) {
    assert.doesNotMatch(fnBody(voice, sig), /jarvis_base\(/, `${sig} reads the address itself`);
  }
  // Start uses the same rule.
  assert.match(fnBody(voice, "async fn ensure_wake_ready("), /wake_audio_refusal\(&base\)/);
});

// AP-2 / CONN-4 (audit 3): asking to turn the wake word on raises an
// approval card, and was not held on a stale link.
await check("CONTROL (Rust): asking to turn \"hey Jarvis\" on is held on a stale link, before its POST", async () => {
  const ready = fnBody(rustSrc("voice.rs"), "async fn ensure_wake_ready(");
  const off = ready.indexOf("WakeReadiness::Off => {");
  assert.ok(off > -1);
  const branch = ready.slice(off);
  const hold = branch.indexOf("app.state::<crate::stream::StreamState>().link().stale");
  const post = branch.indexOf('.post(format!("{base}/api/voice/wake"))');
  assert.ok(hold > -1, "the Off branch has no stale-link hold");
  assert.ok(post > -1 && hold < post, "the stale-link hold comes after the POST");
  // Only the ON request is held: the Ready branch (already on) is not.
  assert.doesNotMatch(ready.slice(0, off), /link\(\)\.stale/);
});

await check("CONTROL (Rust): changing the server address in Settings stops \"hey Jarvis\" listening", async () => {
  const set = fnBody(rustSrc("commands.rs"), "pub fn set_api_settings(");
  const save = set.lastIndexOf(".save()");
  const stop = set.indexOf("crate::voice::stop_listening_because(");
  assert.ok(stop > save, "set_api_settings does not stop listening after the address changes");
  assert.match(set, /if base_after != base_before \{/);
  // And the stop reaches the quickbar in the shape it already acts on.
  const stopFn = fnBody(rustSrc("voice.rs"), "pub(crate) fn stop_listening_because(");
  assert.match(stopFn, /app\.emit\(VOICE_HEARD, HeardReply::unavailable\(why\)\)/);
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await page.waitForTimeout(200);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nautomatic listening: on, off, mutually exclusive with push-to-talk, and honest about a broken engine");
process.exit(fails.length ? 1 : 0);
