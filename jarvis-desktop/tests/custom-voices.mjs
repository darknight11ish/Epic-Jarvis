/**
 * Settings -> Jarvis's voice: custom voices (custom-voices.js,
 * voice-panel.js, voice_training.rs).
 *
 * Every status and answer is REAL: `K.TRAINING.voices` is
 * jarvis_voices.status() and `K.TRAINING.voice_posts` its routes' answers,
 * written by tools/gen_voice_training_cases.py.
 *
 * What must hold (docs/JARVIS-API.md section 15):
 * - the list, which voice speaks, what makes the next sentence, and why the
 *   built-in voice is used when it is;
 * - adding a voice and switching to one only raise a card ("waiting for
 *   your approval"), held on a stale link; back to the built-in voice is at
 *   once and never held; deleting asks first, then happens at once;
 * - a recording's words are the sentence SHOWN - this app transcribes
 *   nothing; a file's words are what the owner typed;
 * - "This sounds like you, so Jarvis won't copy it." for the owner's voice;
 * - the better voice only with a capable second card; ON a card, OFF at once;
 * - how fast Jarvis speaks: the PC's own three choices and words, no card
 *   either way, held on a stale link like every change;
 * - the last card's outcome and recent timings, in words.
 */
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import * as CV from "../src/custom-voices.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const T = K.TRAINING;
const V = T.voices;
const P = (name) => K.TRAINING.answer(T.voice_posts[name]);
const WHERE = "in the Jarvis bar, on the widget, or on your phone's Home screen";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const VIEW = { width: 760, height: 2600 };
const open = (voices, vt = {}, extra = {}) =>
  K.open(browser, base, "settings.html", { vt: { voices, ...vt }, ...extra }, VIEW);
const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|null|undefined|\[object|NaN/, `raw data on the page: ${text}`);
};
const calls = (page, cmd) => page.evaluate((c) => window.__vt.calls.filter((x) => x[0] === c).map((x) => x[1]), cmd);
const text = (page, id) => page.evaluate((i) => document.getElementById(i).innerText, id);

/* ── The words ──────────────────────────────────────────────────────── */

await check("every real voices status reads as sentences, with no raw data", async () => {
  for (const [name, st] of Object.entries(V)) {
    const b = CV.betterView(st, WHERE);
    const lines = [CV.speakingLine(st), CV.fallbackLine(st), CV.pendingLine(st, WHERE), CV.lastLine(st),
      ...CV.voiceRows(st).map((r) => r.detail), ...b.lines.map((l) => l.text), ...CV.timingLines(st)]
      .filter(Boolean);
    for (const line of lines) {
      noRaw(line);
      assert.match(line, /[.!?)]$/, `${name}: "${line}" is not a sentence`);
    }
  }
  for (const [name, a] of Object.entries(T.voice_posts)) {
    const r = CV.voiceReply(P(name), WHERE);
    noRaw(`${r.text} ${r.detail}`);
  }
});

await check("which voice speaks, what makes it, and why the built-in voice is used instead", async () => {
  assert.equal(CV.speakingLine(V.speaking_custom),
    "Jarvis speaks in \"Grandpa\". The next sentence is made with the chosen voice, made on this PC's processor.");
  assert.equal(CV.speakingLine(V.voice_added), "Jarvis speaks in its built-in voice.");
  assert.equal(CV.fallbackLine(V.fallback), `Jarvis is using its built-in voice instead, because ${V.fallback.fallback}.`);
  assert.equal(CV.fallbackLine(V.speaking_custom), null);
  assert.equal(CV.pendingLine(V.switch_waiting, WHERE),
    `Waiting for your approval to speak in "Grandpa". Approve it ${WHERE} — nothing changes until you do.`);
  assert.equal(CV.lastLine(V.switch_withdrawn), V.switch_withdrawn.last.why);
  assert.deepEqual(CV.voiceRows(V.voice_added).map((r) => [r.id, r.detail, r.active]), [
    ["builtin", "Jarvis's own voice. Always there to fall back on.", true],
    ["grandpa", "A 5.0-second recording.", false],
  ]);
  assert.deepEqual(CV.timingLines(V.fallback), [
    `The built-in voice: 0.8 s to make 2.0 s of speech (13 characters). The chosen voice was not used, because ${V.fallback.timings[0].fallback}.`,
  ]);
});

await check("the answers, in words: a card, at once, the owner's voice refused", async () => {
  assert.deepEqual(CV.voiceReply(P("create_owner_voice"), WHERE), {
    text: "This sounds like you, so Jarvis won't copy it.",
    detail: CV.sentence(T.voice_posts.create_owner_voice.body.error),
    tone: "bad", waiting: false,
  });
  for (const name of ["create_accepted", "switch_pending", "better_on_pending"]) {
    assert.equal(CV.voiceReply(P(name), WHERE).waiting, true, name);
  }
  assert.equal(CV.voiceReply(P("builtin"), WHERE).text, "Jarvis speaks in its built-in voice.");
  assert.equal(CV.voiceReply(P("delete"), WHERE).text, "Deleted.");
  assert.match(CV.voiceReply(P("better_no_card"), WHERE).text, /^The better voice cannot be turned on/);
});

await check("the better voice is offered only with a capable second card", async () => {
  assert.equal(CV.betterView(V.voice_added, WHERE).show, false);
  const capable = CV.betterView(V.better_capable, WHERE);
  assert.equal(capable.show, true);
  assert.equal(capable.on, false);
  const waiting = CV.betterView(V.better_waiting, WHERE);
  assert.equal(waiting.waiting, true);
  assert.match(waiting.lines[0].text, /^Waiting for your approval to turn it on\./);
  const on = CV.betterView(V.better_on, WHERE);
  assert.equal(on.on, true);
  assert.equal(on.lines.filter((l) => l.text.includes("F5-TTS model files")).length, 1, "the files' reason is said once");
});

/* ── The page ───────────────────────────────────────────────────────── */

await check("the list, and switching: a custom voice is a card, the built-in voice is at once", async () => {
  const page = await open(V.voice_added);
  const list = await text(page, "cv-list");
  await page.click('#cv-list input[value="grandpa"]');
  await page.waitForTimeout(200);
  const asked = await calls(page, "set_active_voice");
  const said = await text(page, "cv-status");
  const checked = await page.evaluate(() => document.querySelector('#cv-list input:checked').value);
  await page.close();
  assert.match(list, /Built-in voice[\s\S]*Grandpa\s+A 5\.0-second recording\./);
  assert.deepEqual(asked, [{ voice: "grandpa" }]);
  assert.equal(said, `Waiting for your approval. Approve it ${WHERE} — nothing changes until you do.`);
  assert.equal(checked, "builtin", "the list shows what Jarvis says, not what was clicked");

  const back = await open(V.speaking_custom, {}, { link: { stale: true } });
  await back.click('#cv-list input[value="builtin"]');
  await back.waitForTimeout(200);
  const b = await calls(back, "set_active_voice");
  await back.click('#cv-list input[value="grandpa"]').catch(() => {});
  await back.waitForTimeout(100);
  await back.close();
  assert.deepEqual(b, [{ voice: "builtin" }], "going back is never held, not even on a stale link");
});

await check("a custom voice is not asked for on a stale link", async () => {
  const page = await open(V.voice_added, {}, { link: { stale: true } });
  await page.click('#cv-list input[value="grandpa"]');
  await page.waitForTimeout(200);
  const asked = await calls(page, "set_active_voice");
  const said = await text(page, "cv-status");
  await page.close();
  assert.deepEqual(asked, []);
  assert.match(said, /catching up/);
});

await check("deleting asks first; no means nothing is sent", async () => {
  const page = await open(V.voice_added);
  page.once("dialog", (d) => d.dismiss());
  await page.click('#cv-list li[data-voice="grandpa"] button');
  await page.waitForTimeout(150);
  assert.deepEqual(await calls(page, "delete_custom_voice"), []);
  let question = "";
  page.once("dialog", (d) => { question = d.message(); d.accept(); });
  await page.click('#cv-list li[data-voice="grandpa"] button');
  await page.waitForTimeout(200);
  const del = await calls(page, "delete_custom_voice");
  const said = await text(page, "cv-status");
  await page.close();
  assert.equal(question, "Delete the voice \"Grandpa\" for good? Its recording is deleted from your PC.");
  assert.deepEqual(del, [{ voice: "grandpa" }]);
  assert.equal(said, "Deleted.");
});

await check("adding by recording: the words sent are the sentence SHOWN, and a card is up", async () => {
  const page = await open(V.voice_added, { take: { seconds: 5.2, peak: 0.5 } });
  await page.fill("#cv-name", "Grandpa's voice");
  await page.click("#cv-another");
  const shown = (await text(page, "cv-sentence")).trim();
  await page.click("#cv-rec");
  await page.waitForTimeout(80);
  assert.equal((await text(page, "cv-rec")).trim(), "Stop");
  await page.click("#cv-rec");
  await page.waitForTimeout(80);
  await page.click("#cv-add");
  await page.waitForTimeout(200);
  const sent = await calls(page, "create_custom_voice");
  const starts = await calls(page, "start_voice_sample");
  const said = await text(page, "cv-add-status");
  await page.close();
  assert.equal(shown, V.voice_added.sentences[1]);
  assert.deepEqual(starts, [{ slot: "voice" }]);
  assert.deepEqual(sent, [{ name: "Grandpa's voice", transcript: shown, slot: "voice" }]);
  assert.equal(said, `Waiting for your approval. Approve it ${WHERE} — nothing changes until you do.`);
});

await check("the owner's own voice: a plain sentence, and the PC's reason under it", async () => {
  const page = await open(V.voice_added, { take: { seconds: 5.2, peak: 0.5 }, create: P("create_owner_voice") });
  await page.fill("#cv-name", "Me");
  await page.click("#cv-rec");
  await page.waitForTimeout(80);
  await page.click("#cv-rec");
  await page.waitForTimeout(80);
  await page.click("#cv-add");
  await page.waitForTimeout(200);
  const said = await text(page, "cv-add-status");
  const detail = await text(page, "cv-add-detail");
  await page.close();
  assert.equal(said, "This sounds like you, so Jarvis won't copy it.");
  assert.match(detail, /^This recording sounds too much like YOUR voice/);
});

await check("adding from a WAV file: its bytes and the typed words; nothing added without them", async () => {
  const dir = mkdtempSync(join(tmpdir(), "cv-"));
  const wav = Buffer.concat([Buffer.from("RIFF"), Buffer.alloc(4), Buffer.from("WAVEfmt "), Buffer.alloc(40, 7)]);
  const file = join(dir, "grandma.wav");
  writeFileSync(file, wav);
  const page = await open(V.voice_added);
  await page.click('#cv-way button[data-value="file"]');
  await page.fill("#cv-name", "Grandma");
  await page.setInputFiles("#cv-file", file);
  await page.waitForTimeout(80);
  const blocked = await page.evaluate(() => ({
    disabled: document.getElementById("cv-add").disabled,
    said: document.getElementById("cv-add-status").innerText,
  }));
  await page.fill("#cv-words", "Hello dear, did you remember your coat today?");
  await page.click("#cv-add");
  await page.waitForTimeout(250);
  const sent = await calls(page, "create_custom_voice");
  await page.close();
  assert.equal(blocked.disabled, true);
  assert.equal(blocked.said, "Type exactly what is said in the recording.");
  assert.equal(sent.length, 1);
  assert.equal(sent[0].name, "Grandma");
  assert.equal(sent[0].transcript, "Hello dear, did you remember your coat today?");
  assert.equal(sent[0].file, wav.toString("base64"));
  assert.equal(sent[0].slot, undefined);
});

await check("the better voice: hidden without a capable card; ON is a card, OFF at once", async () => {
  const none = await open(V.voice_added);
  const hidden = await none.evaluate(() => document.getElementById("cv-better").hidden);
  const why = await text(none, "cv-better-why");
  await none.close();
  assert.equal(hidden, true);
  assert.match(why, /^The better voice: Needs a capable second graphics card/);

  const page = await open(V.better_capable);
  await page.click("#cv-better-switch");
  await page.waitForTimeout(200);
  const on = await calls(page, "set_better_voice");
  const said = await text(page, "cv-better-status");
  await page.close();
  assert.deepEqual(on, [{ enabled: true }]);
  assert.equal(said, `Waiting for your approval. Approve it ${WHERE} — nothing changes until you do.`);

  const off = await open(V.better_on, {}, { link: { stale: true } });
  await off.click("#cv-better-switch");
  await off.waitForTimeout(200);
  const o = await calls(off, "set_better_voice");
  await off.close();
  assert.deepEqual(o, [{ enabled: false }], "OFF is never held");
});

await check("how fast Jarvis speaks: the PC's three choices and words, from every real status", async () => {
  for (const [name, st] of Object.entries(V)) {
    const sp = CV.speedView(st);
    assert.equal(sp.show, true, `${name}: no speed block`);
    assert.deepEqual(sp.choices.map((c) => c.label), ["Slower", "Normal", "Faster"], name);
    assert.equal(sp.title, "How fast Jarvis speaks", name);
    assert.match(sp.detail, /never asks first/, name);
    noRaw([sp.title, sp.detail, sp.note, ...sp.choices.map((c) => c.label)].join(" "));
  }
  assert.equal(CV.speedView(V.builtin_nothing_installed).choice, "normal");
  assert.equal(CV.speedView(V.speed_chosen).choice, "faster");
  assert.equal(CV.speedView({ voices: [] }).show, false, "an older PC has no speed block: nothing shown");
  const reply = CV.voiceReply(P("speed_faster"), WHERE);
  assert.equal(reply.text, "Jarvis now speaks faster.");
  assert.equal(reply.waiting, false, "no card");
  assert.equal(CV.voiceReply(P("speed_bad"), WHERE).text, "The speed must be slower, normal or faster.");
});

await check("how fast Jarvis speaks: one click, at once; held on a stale link", async () => {
  const page = await open(V.builtin_nothing_installed);
  const shown = await page.evaluate(() => ({
    hidden: document.getElementById("cv-speed").hidden,
    radios: [...document.querySelectorAll("#cv-speed-choices input")].map((r) => [r.value, r.checked]),
  }));
  await page.click('#cv-speed-choices input[value="faster"]');
  await page.waitForTimeout(200);
  const sent = await calls(page, "set_voice_speed");
  const said = await text(page, "cv-speed-status");
  await page.close();
  assert.equal(shown.hidden, false);
  assert.deepEqual(shown.radios, [["slower", false], ["normal", true], ["faster", false]]);
  assert.deepEqual(sent, [{ speed: "faster" }]);
  assert.equal(said, "Jarvis now speaks faster.");
  assert.doesNotMatch(said, /approv/i, "no card for the speed");

  const stale = await open(V.builtin_nothing_installed, {}, { link: { stale: true } });
  const disabled = await stale.evaluate(() =>
    [...document.querySelectorAll("#cv-speed-choices input")].every((r) => r.disabled));
  const none = await calls(stale, "set_voice_speed");
  await stale.close();
  assert.equal(disabled, true, "held on a stale link");
  assert.deepEqual(none, []);
});

await check("the fallback, a waiting card, the last card and the timings are on the page", async () => {
  const page = await open(V.fallback);
  const all = await text(page, "voices");
  await page.close();
  assert.match(all, /Jarvis is using its built-in voice instead, because the ZipVoice model files are not on this PC yet/);
  assert.match(all, /Jarvis now speaks in "Grandpa"\./);
  assert.match(all, /The built-in voice: 0\.8 s to make 2\.0 s of speech \(13 characters\)\./);
  noRaw(all);
  const waiting = await open(V.switch_waiting);
  const w = await text(waiting, "cv-pending");
  await waiting.close();
  assert.match(w, /^Waiting for your approval to speak in "Grandpa"\./);
});

await check("an older backend is a sentence; the `voices` event reads the list again", async () => {
  const old = await open(V.voice_added, { voicesUnavailable: true });
  const state = await text(old, "cv-state");
  const bodyHidden = await old.evaluate(() => document.getElementById("cv-body").hidden);
  await old.close();
  assert.match(state, /does not have custom voices yet\. Update the backend by running apply-patches\.ps1/);
  assert.equal(bodyHidden, true);
  const page = await open(V.voice_added);
  const first = await page.evaluate(() => window.__vt.reads);
  await page.evaluate(() => window.__emit("jarvis-event", { kind: "voices", data: { what: "create", outcome: "created" } }));
  await page.waitForTimeout(150);
  const later = await page.evaluate(() => window.__vt.reads);
  await page.close();
  assert.ok(later > first, "no re-read on the voices event");
});

/* ── The Rust ───────────────────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};
const RUST = read("src-tauri/src/voice_training.rs");

await check("CONTROL (Rust): only what raises a card is held on a stale link", async () => {
  assert.match(fnBody(RUST, "pub async fn create_custom_voice("), /if stale\(&app\) \{\s+return Err\(HELD_STALE/);
  assert.match(fnBody(RUST, "pub async fn set_active_voice("), /if voice != "builtin" && stale\(&app\)/);
  assert.match(fnBody(RUST, "pub async fn set_better_voice("), /if enabled && stale\(&app\)/);
  assert.match(fnBody(RUST, "pub async fn set_voice_speed("), /if stale\(&app\) \{\s+return Err\(HELD_STALE/);
  assert.doesNotMatch(fnBody(RUST, "pub async fn delete_custom_voice("), /stale/);
  for (const [fn, route] of [["create_custom_voice", "/api/voice/voices/create"], ["set_active_voice", "/api/voice/voices/active"],
    ["delete_custom_voice", "/api/voice/voices/delete"], ["set_better_voice", "/api/voice/voices/better"],
    ["set_voice_speed", "/api/voice/voices/speed"]]) {
    assert.ok(fnBody(RUST, `pub async fn ${fn}(`).includes(`"${route}"`), `${fn} does not post to ${route}`);
  }
  assert.match(fnBody(RUST, "pub async fn get_custom_voices("), /\.headers\(jarvis_headers\(&app\)\?\)/);
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await open(V.speaking_custom);
  await page.waitForTimeout(200);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nCustom voices hold");
process.exit(fails.length ? 1 : 0);
