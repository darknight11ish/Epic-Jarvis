/**
 * Settings -> Voice: the PC's "hey Jarvis" switch, both ways.
 *
 * Before this, the desktop could only ever post `{"enabled": true}` (voice.rs
 * `ensure_wake_ready`); only the phone could turn the PC's wake word off.
 * Now Settings has the phone's two buttons (ReadinessScreen.kt WakeWordCard):
 *
 * - "Turn the wake word off" while it is on: immediate, never held on a
 *   stale link, and it stops this PC's own listening first;
 * - "Turn on "hey Jarvis"" while it is off: raises ONE approval card and
 *   turns nothing on; held while the event stream is stale;
 * - neither while a card waits - the card is the decision.
 *
 * The statuses and the server's answers are REAL (K.VOICE, from
 * tools/gen_voice_status_cases.py). The CONTROL checks read the Rust.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const C = K.VOICE.cases;

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1400 };
const open = (voice) => K.open(browser, base, "settings.html", { voice }, VIEW);
const look = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  return {
    wakeState: $("voice").dataset.wake || "",
    wake: $("voice-wake").innerText,
    offShown: Boolean($("voice-wake-off")) && !$("voice-wake-off").hidden,
    onShown: Boolean($("voice-wake-on")) && !$("voice-wake-on").hidden,
    noteShown: Boolean($("voice-wake-on-note")) && !$("voice-wake-on-note").hidden,
    status: $("voice-wake-status") ? $("voice-wake-status").innerText : "",
    changes: window.__voice.changes,
  };
});

await check("wake word on: \"Turn the wake word off\" is offered, and pressing it turns it off at once", async () => {
  const page = await open({ status: C.ready_wake_on });
  const before = await look(page);
  assert.equal(before.wakeState, "on");
  assert.equal(before.offShown, true, "no way to turn it off");
  assert.equal(before.onShown, false);
  await page.locator("#voice-wake-off").click();
  await page.waitForTimeout(300);
  const after = await look(page);
  await page.close();
  assert.deepEqual(after.changes, [{ enabled: false }], "not exactly one OFF request");
  assert.equal(after.status, K.VOICE.answers.wake_off.message);
  assert.equal(after.wakeState, "off", "the page did not re-read what Jarvis says");
  assert.match(after.wake, /^Off\./);
  assert.equal(after.offShown, false);
  assert.equal(after.onShown, true);
});

await check("wake word off: \"Turn on\" raises a card and turns nothing on", async () => {
  const page = await open({ status: C.phone_trained });
  const before = await look(page);
  assert.equal(before.onShown, true);
  assert.equal(before.noteShown, true, "the approval-card note is missing");
  assert.equal(before.offShown, false);
  await page.locator("#voice-wake-on").click();
  await page.waitForTimeout(300);
  const after = await look(page);
  await page.close();
  assert.deepEqual(after.changes, [{ enabled: true }]);
  assert.match(after.status, /^Waiting for your approval\. Approve it in the Jarvis bar, on the widget, or on your phone's Home screen/);
  assert.equal(after.wakeState, "waiting", "the switch shows what was clicked, not what Jarvis says");
  assert.equal(after.onShown, false, "a second card could be asked for while one waits");
  assert.equal(after.offShown, false);
});

await check("a card already waiting: nothing to press, only where to approve it", async () => {
  const page = await open({ status: C.wake_waiting });
  const s = await look(page);
  await page.close();
  assert.equal(s.wakeState, "waiting");
  assert.equal(s.onShown, false);
  assert.equal(s.offShown, false);
});

await check("ON refused (the stale-link hold): the reason in words, and nothing changes", async () => {
  const held = "The connection to Jarvis is catching up, so \"hey Jarvis\" cannot be turned on until it does. Turning it off still works.";
  const page = await open({ status: C.phone_trained, setFails: held });
  await page.locator("#voice-wake-on").click();
  await page.waitForTimeout(300);
  const s = await look(page);
  await page.close();
  assert.equal(s.status, held);
  assert.equal(s.wakeState, "off");
});

await check("the server's own refusal (a card already waiting) is shown as a sentence", async () => {
  const page = await open({
    status: C.phone_trained,
    onAnswer: { ok: false, pending: true, error: "a card to turn the wake word on is already waiting" },
  });
  await page.locator("#voice-wake-on").click();
  await page.waitForTimeout(300);
  const s = await look(page);
  await page.close();
  assert.equal(s.status, "A card to turn the wake word on is already waiting.");
});

/* ── The Rust ───────────────────────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL (Rust): ON is held on a stale link before anything is sent; OFF never is, and stops listening first", async () => {
  const rust = read("src-tauri/src/voice.rs");
  const set = fnBody(rust, "pub async fn set_wake_word(");
  const hold = set.indexOf("app.state::<crate::stream::StreamState>().link().stale");
  const stop = set.indexOf("stop_listening_because(");
  const post = set.indexOf(".post(");
  assert.ok(hold > -1, "no stale-link hold");
  assert.ok(hold < post, "the hold comes after the POST");
  assert.match(set.slice(0, hold), /if enabled \{/, "the hold is not only for ON");
  assert.ok(stop > hold && stop < post, "OFF does not stop this PC's listening before the POST");
  assert.match(set.slice(hold, stop), /\} else \{/, "stopping the listener is not on the OFF branch");
  assert.doesNotMatch(set, /if !enabled[^\n]*stale/);
  assert.match(set, /serde_json::json!\(\{ "enabled": enabled \}\)/);
  assert.match(set, /format!\("\{base\}\/api\/voice\/wake"\)/);
  assert.match(set, /\.headers\(jarvis_headers\(&app\)\?\)/);
  assert.doesNotMatch(set, /println!|eprintln!|log::|tracing::|dbg!|logfile|token/i);
});

await check("CONTROL: only the settings window may flip the switch", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const holders = toml.split("[[set]]").slice(1)
    .filter((s) => s.includes('"allow-set-wake-word"'))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders, ["settings-surface"]);
  assert.ok(read("src-tauri/build.rs").includes('"set_wake_word"'));
  assert.ok(read("src-tauri/src/lib.rs").includes("voice::set_wake_word,"));
  assert.match(read("src-tauri/permissions/autogenerated/set_wake_word.toml"),
    /commands.allow = \["set_wake_word"\]/);
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await open({ status: C.ready_wake_on });
  await page.locator("#voice-wake-off").click();
  await page.waitForTimeout(300);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nThe \"hey Jarvis\" switch holds");
process.exit(fails.length ? 1 : 0);
