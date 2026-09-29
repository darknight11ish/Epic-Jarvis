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
 * - "Voice follows the face": an on/off switch with the PC's own words and
 *   line, no card either way, held on a stale link like every change;
 * - the last card's outcome and recent timings, in words;
 * - "Try it" never plays over Jarvis: refused while it talks or listens,
 *   stopped the moment a question or answer starts, one at a time on the
 *   PC, and in the phone's own words (CustomVoices.kt `TRY_*`).
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

await check("Jarvis's built-in voice: the PC's voices BY NAME and words, from every real status", async () => {
  for (const [name, st] of Object.entries(V)) {
    const sk = CV.speakerView(st);
    assert.equal(sk.show, true, `${name}: no speaker block`);
    assert.ok(sk.choices.length >= 9, `${name}: ${sk.choices.length} voices`);
    for (const c of sk.choices) {
      assert.match(c.id, /^([a-z]{2}|mix)(_[a-z]+)?$/, `${name}: "${c.id}" is a voice's name, not a number`);
    }
    assert.equal(sk.title, "Jarvis's built-in voice", name);
    noRaw([sk.title, sk.detail, sk.note, ...sk.choices.map((c) => c.label)].join(" "));
  }
  assert.equal(CV.speakerView(V.builtin_nothing_installed).choice, "af");
  assert.equal(CV.speakerView(V.speaker_chosen).choice, "bm_george");
  assert.equal(CV.speakerView({ voices: [] }).show, false, "an older PC has no speaker block: nothing shown");
  // The two packs: the old one offers nine, with the way to the new one in its
  // note; Kokoro v1.0 offers eleven (Heart first, the best rated), no note.
  const old = CV.speakerView(V.pack_old);
  assert.equal(old.choices.length, 9);
  assert.match(old.note, /^Better voices are available: Kokoro v1\.0 /);
  const v1 = CV.speakerView(V.pack_v1);
  assert.deepEqual(v1.choices.map((c) => c.id), ["af_heart", "af_bella", "af_nicole", "af_sarah", "am_michael",
    "am_fenrir", "am_puck", "bf_emma", "bf_isabella", "bm_george", "bm_lewis"]);
  assert.equal(v1.choice, "af_heart");
  assert.match(v1.note, /^Ashby and Clara, two voices made for Jarvis, are not made yet\. To make them, run the one line /,
    "the new pack, blends not made yet: the way to make them, in words");
  assert.ok(v1.choices.every((c) => c.detail === ""), "no plain line on a voice that is not one of the two");
  // The owner's old NUMBER carried over: 9 was George, and the animals' choices moved too.
  const carried = CV.speakerView(V.carried_over);
  assert.equal(carried.choice, "bm_george", "the saved 9 is still George");
  const animals = CV.animalVoicesView(V.carried_over).animals;
  assert.deepEqual(animals.map((a) => [a.face, a.speaker, a.changed]),
    [["redpanda", "af_bella", false], ["pygmyowl", "af_nicole", false], ["seaotter", "af_sarah", false],
      ["monkey", "bf_emma", true], ["robot", "bf_emma", false]], "the otter's saved Sky went back to its own voice");
  const reply = CV.voiceReply(P("speaker_george"), WHERE);
  assert.equal(reply.text, "Jarvis's built-in voice is now British (male) - George.");
  assert.equal(reply.waiting, false, "no card");
  assert.equal(CV.voiceReply(P("speaker_bad"), WHERE).text, "Choose one of the listed voices.",
    "a number is not a voice any more");
});

await check("Jarvis's built-in voice: one click, at once; held on a stale link", async () => {
  const page = await open(V.builtin_nothing_installed);
  const shown = await page.evaluate(() => ({
    hidden: document.getElementById("cv-speaker").hidden,
    checked: [...document.querySelectorAll("#cv-speaker-choices input")].find((r) => r.checked)?.value,
  }));
  await page.click('#cv-speaker-choices input[value="bm_george"]');
  await page.waitForTimeout(200);
  const sent = await calls(page, "set_voice_speaker");
  const said = await text(page, "cv-speaker-status");
  await page.close();
  assert.equal(shown.hidden, false);
  assert.equal(shown.checked, "af");
  assert.deepEqual(sent, [{ speaker: "bm_george" }]);
  assert.equal(said, "Jarvis's built-in voice is now British (male) - George.");
  assert.doesNotMatch(said, /approv/i, "no card for the voice choice");

  const stale = await open(V.builtin_nothing_installed, {}, { link: { stale: true } });
  const disabled = await stale.evaluate(() =>
    [...document.querySelectorAll("#cv-speaker-choices input")].every((r) => r.disabled));
  const none = await calls(stale, "set_voice_speaker");
  await stale.close();
  assert.equal(disabled, true, "held on a stale link");
  assert.deepEqual(none, []);
});

await check("voice follows the face: the PC's switch, words and line, from every real status", async () => {
  for (const [name, st] of Object.entries(V)) {
    const fv = CV.faceVoiceView(st);
    assert.equal(fv.show, true, `${name}: no face_voice block`);
    assert.equal(fv.title, "Voice follows the face", name);
    noRaw([fv.title, fv.detail, fv.line].join(" "));
    assert.match(fv.line, /[.!?)]$/, `${name}: "${fv.line}" is not a sentence`);
  }
  // OFF by default (the owner's 2026-09-28 decision), and it says so -
  // with no face saved, and with one showing: a face alone never turns it on.
  for (const st of [V.builtin_nothing_installed, V.face_default_off]) {
    const fv = CV.faceVoiceView(st);
    assert.equal(fv.enabled, false, "off by default");
    assert.equal(fv.speaking, false);
    assert.equal(fv.line, "Off: the built-in voice stays the same whatever the face.");
  }
  const panda = CV.faceVoiceView(V.face_showing);
  assert.equal(panda.speaking, true);
  assert.equal(panda.line, "Speaking as the Red Panda: Bella, a little higher.");
  // The built-in voice choice says the face's voice is standing in.
  assert.match(CV.speakerView(V.face_showing).note, /Red Panda face is showing, its own voice speaks instead/);
  assert.equal(CV.faceVoiceView(V.face_voice_off).enabled, false);
  assert.equal(CV.speakerView(V.face_voice_off).note, "", "switched off: the built-in choice is used, no note");
  assert.equal(CV.faceVoiceView({ voices: [] }).show, false, "an older PC has no face_voice block: nothing shown");
  const off = CV.voiceReply(P("face_off"), WHERE);
  assert.equal(off.text, "Jarvis's voice now stays the same whatever the face.");
  assert.equal(off.waiting, false, "no card");
  const on = CV.voiceReply(P("face_on"), WHERE);
  assert.equal(on.text, "Jarvis's voice now follows the face.");
  assert.equal(on.waiting, false, "no card");
  assert.equal(CV.voiceReply(P("face_bad"), WHERE).text, "Choose on or off.");
});

await check("voice follows the face: one click, at once; held on a stale link", async () => {
  const page = await open(V.face_showing);
  const shown = await page.evaluate(() => ({
    hidden: document.getElementById("cv-face").hidden,
    checked: document.getElementById("cv-face-switch").checked,
    title: document.getElementById("cv-face-title").textContent,
    line: document.getElementById("cv-face-line").textContent,
  }));
  await page.click("#cv-face-switch");
  await page.waitForTimeout(200);
  const sent = await calls(page, "set_voice_face");
  const said = await text(page, "cv-face-status");
  await page.close();
  assert.equal(shown.hidden, false);
  assert.equal(shown.checked, true);
  assert.equal(shown.title, "Voice follows the face");
  assert.equal(shown.line, "Speaking as the Red Panda: Bella, a little higher.");
  assert.deepEqual(sent, [{ enabled: false }]);
  assert.equal(said, "Jarvis's voice now stays the same whatever the face.");
  assert.doesNotMatch(said, /approv/i, "no card for the face's voice");

  const back = await open(V.face_voice_off);
  const wasOff = await back.evaluate(() => document.getElementById("cv-face-switch").checked);
  await back.click("#cv-face-switch");
  await back.waitForTimeout(200);
  const sentOn = await calls(back, "set_voice_face");
  await back.close();
  assert.equal(wasOff, false);
  assert.deepEqual(sentOn, [{ enabled: true }]);

  const stale = await open(V.face_showing, {}, { link: { stale: true } });
  const disabled = await stale.evaluate(() => document.getElementById("cv-face-switch").disabled);
  const none = await calls(stale, "set_voice_face");
  await stale.close();
  assert.equal(disabled, true, "held on a stale link");
  assert.deepEqual(none, []);
});

/* The one-time animal voice question (the owner, 2026-09-28). The shared
   fixtures may not carry `face_voice.offer` yet, so this test builds its own
   status on top of the real `face_voice_off` one, in the exact shape the
   PC's GET /api/voice/voices gives, and its own POST answer. */
const OFFER = {
  face: "redpanda",
  question: "The Red Panda has its own voice. Use it?",
  use: "Use it",
  keep: "Keep my voice",
};
const withOffer = (st, offer = OFFER) => {
  const copy = JSON.parse(JSON.stringify(st));
  copy.face_voice = { ...(copy.face_voice || {}), offer };
  return copy;
};

await check("the animal voice question: the PC's words as they are, or nothing", async () => {
  const v = CV.faceOfferView(withOffer(V.face_voice_off));
  assert.deepEqual(v, { show: true, ...OFFER });
  assert.equal(CV.faceOfferView(V.face_voice_off).show, false, "no offer: nothing shown");
  assert.equal(CV.faceOfferView(withOffer(V.face_voice_off, null)).show, false);
  assert.equal(CV.faceOfferView(withOffer(V.face_voice_off, { ...OFFER, face: "orbit" })).show, false,
    "only the animals and the robot have a voice of their own");
  assert.equal(CV.faceOfferView(withOffer(V.face_voice_off, { ...OFFER, keep: "" })).show, false);
  assert.equal(CV.faceOfferView({ voices: [] }).show, false, "an older PC: nothing shown");
  // The Rust checks the same shape for the Faces window.
  const rs = read("src-tauri/src/voice_training.rs");
  assert.ok(rs.includes('"/api/voice/voices/face_offer"'));
  const answer = rs.slice(rs.indexOf("pub async fn answer_face_voice_offer"));
  assert.ok(answer.slice(0, 600).includes("return Err(HELD_STALE.to_string())"), "held on a stale link");
});

await check("the animal voice question in Settings: one click answers it, no card; held on a stale link", async () => {
  const page = await open(withOffer(V.face_voice_off), {
    faceOfferAnswer: { ok: true, http: 200, message: "Jarvis's voice now follows the face",
      face_voice: { enabled: true, offer: null } },
  });
  const shown = await page.evaluate(() => ({
    hidden: document.getElementById("cv-face-offer").hidden,
    question: document.getElementById("cv-face-offer-question").textContent,
    use: document.getElementById("cv-face-offer-use").textContent,
    keep: document.getElementById("cv-face-offer-keep").textContent,
  }));
  await page.click("#cv-face-offer-use");
  await page.waitForTimeout(200);
  const sent = await calls(page, "answer_face_voice_offer");
  const said = await text(page, "cv-face-status");
  await page.close();
  assert.deepEqual(shown, { hidden: false, question: OFFER.question, use: OFFER.use, keep: OFFER.keep });
  assert.deepEqual(sent, [{ face: "redpanda", answer: "use" }]);
  assert.equal(said, "Jarvis's voice now follows the face.");
  assert.doesNotMatch(said, /approv/i, "no card");

  const keep = await open(withOffer(V.face_voice_off));
  await keep.click("#cv-face-offer-keep");
  await keep.waitForTimeout(200);
  const kept = await calls(keep, "answer_face_voice_offer");
  await keep.close();
  assert.deepEqual(kept, [{ face: "redpanda", answer: "keep" }]);

  const none = await open(V.face_voice_off);
  const hidden = await none.evaluate(() => document.getElementById("cv-face-offer").hidden);
  await none.close();
  assert.equal(hidden, true, "no question when the PC asks none");

  const stale = await open(withOffer(V.face_voice_off), {}, { link: { stale: true } });
  const greyed = await stale.evaluate(() => [
    document.getElementById("cv-face-offer-use").disabled,
    document.getElementById("cv-face-offer-keep").disabled,
  ]);
  await stale.close();
  assert.deepEqual(greyed, [true, true], "greyed on a stale link (rule 4)");
});

/* Changing your mind later (the owner, 2026-09-28): a small button on each
   animal's row once the one-time question was answered. Builds its own
   answers on top of the real `face_showing` status. */
const withAnswers = (answers) => {
  const copy = JSON.parse(JSON.stringify(V.face_showing));
  copy.face_voice.animals.forEach((a, i) => { a.answer = answers[i]; });
  return copy;
};
const mindButtons = (page) => page.evaluate(() =>
  [...document.querySelectorAll("#cv-animals-list .cv-animal")].map((r) => {
    const b = [...r.querySelectorAll("button")].find((x) => /^(Use its own voice|Keep my voice)$/.test(x.textContent));
    return b && !b.hidden ? { text: b.textContent, disabled: b.disabled } : null;
  }));

await check("change your mind: 'Use its own voice' after keep, 'Keep my voice' after use, nothing before an answer", async () => {
  const st = withAnswers(["keep", "use", null, "keep", null]);
  assert.deepEqual(CV.animalVoicesView(st).animals.map((a) => a.answer), ["keep", "use", null, "keep", null]);
  const page = await open(st, {
    faceOfferAnswer: { ok: true, http: 200, message: "The Red Panda speaks in its own voice now.",
      face_voice: { enabled: true } },
  });
  const shown = await mindButtons(page);
  await page.click('.cv-animal[data-face="redpanda"] button:text-is("Use its own voice")');
  await page.waitForTimeout(250);
  const first = await calls(page, "answer_face_voice_offer");
  const said = await page.evaluate(() =>
    document.querySelector('.cv-animal[data-face="redpanda"] .status').textContent);
  await page.click('.cv-animal[data-face="pygmyowl"] button:text-is("Keep my voice")');
  await page.waitForTimeout(250);
  const both = await calls(page, "answer_face_voice_offer");
  await page.close();
  assert.deepEqual(shown, [
    { text: "Use its own voice", disabled: false },
    { text: "Keep my voice", disabled: false },
    null,
    { text: "Use its own voice", disabled: false },
    null,
  ]);
  assert.deepEqual(first, [{ face: "redpanda", answer: "use" }]);
  assert.equal(said, "The Red Panda speaks in its own voice now.");
  assert.deepEqual(both, [{ face: "redpanda", answer: "use" }, { face: "pygmyowl", answer: "keep" }],
    "any animal, not only the one showing");

  const stale = await open(st, {}, { link: { stale: true } });
  const greyed = await mindButtons(stale);
  await stale.close();
  assert.deepEqual(greyed.map((b) => b && b.disabled), [true, true, null, true, null], "greyed on a stale link (rule 4)");
});

await check("each animal's voice: the PC's rows, choices and words, from every real status", async () => {
  for (const [name, st] of Object.entries(V)) {
    const av = CV.animalVoicesView(st);
    assert.equal(av.show, true, `${name}: no animals`);
    assert.deepEqual(av.animals.map((a) => a.face), ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"], name);
    assert.ok(av.voices.length >= 9, `${name}: ${av.voices.length} voices`);
    assert.ok(!av.voices.some((v) => /sky|adam/i.test(v.id)), `${name}: no animal may pick Sky or Adam`);
    assert.deepEqual(av.paces.map((p) => p.id), ["slower", "normal", "faster"], name);
    assert.deepEqual(av.pitch, { min: -3, max: 4, step: 0.5 }, name);
    noRaw([av.title, av.detail, ...av.animals.map((a) => a.line)].join(" "));
    for (const a of av.animals) assert.match(a.line, /[.!?)]$/, `${name}: "${a.line}" is not a sentence`);
  }
  const own = CV.animalVoicesView(V.face_showing).animals;
  assert.deepEqual(own.map((a) => [a.speaker, a.semitones, a.pace, a.changed]),
    [["af_bella", 2, "normal", false], ["af_nicole", 1, "slower", false], ["af_sarah", 3, "faster", false],
      ["am_michael", 1, "normal", false], ["bf_emma", 2, "faster", false]]);
  assert.equal(own[0].line, "Bella, 2 steps higher, at normal pace.");
  const panda = CV.animalVoicesView(V.animal_changed).animals[0];
  assert.deepEqual([panda.speaker, panda.semitones, panda.pace, panda.changed], ["af_sarah", -1.5, "faster", true]);
  assert.equal(panda.line, "Sarah, 1.5 steps deeper, a little faster.");
  assert.equal(CV.faceVoiceView(V.animal_changed).line, "Speaking as the Red Panda: Sarah, a little deeper.");
  assert.equal(CV.animalVoicesView({ voices: [], face_voice: { enabled: true } }).show, false,
    "an older PC has no animals: nothing shown");
  assert.equal(CV.voiceReply(P("animal_set"), WHERE).text,
    "The Red Panda's voice is now Sarah, 1.5 steps deeper, a little faster.");
  assert.equal(CV.voiceReply(P("animal_set"), WHERE).waiting, false, "no card");
  assert.equal(CV.voiceReply(P("animal_reset"), WHERE).text, "The Red Panda speaks in its own voice again.");
  assert.equal(CV.voiceReply(P("animal_bad"), WHERE).text,
    "The pitch must be from 3 steps deeper to 4 steps higher, in half steps.");
  assert.equal(CV.voiceReply(P("animal_try_bad"), WHERE).text,
    "Choose the Red Panda, the Pygmy Owl, the Sea Otter, the Monkey or the Robot.");
  assert.deepEqual([2, -1.5, 0, 1, 0.5].map(CV.pitchWords),
    ["2 steps higher", "1.5 steps deeper", "Normal pitch", "1 step higher", "0.5 steps higher"]);
  assert.deepEqual([2, -1.5, 0].map(CV.pitchShort), ["+2", "-1.5", "0"]);
});

await check("each animal's voice: pick, slide, pace, Try it and Reset - at once, no card", async () => {
  const page = await open(V.face_showing);
  const shown = await page.evaluate(() => {
    const rows = [...document.querySelectorAll("#cv-animals-list .cv-animal")];
    const r = rows[0];
    r.querySelector("select").dataset.mark = "kept";
    return {
      hidden: document.getElementById("cv-animals").hidden,
      faces: rows.map((x) => x.dataset.face),
      name: r.querySelector(".cv-animal-name").textContent,
      line: r.querySelector(".cv-animal-line").textContent,
      voice: r.querySelector("select").value,
      voiceLabel: r.querySelector("select").getAttribute("aria-label"),
      pitch: r.querySelector("input[type=range]").value,
      pitchText: r.querySelector("input[type=range]").getAttribute("aria-valuetext"),
      shown: r.querySelector("output").textContent,
      pace: r.querySelector('.choices [aria-pressed="true"]').dataset.value,
      reset: r.querySelector('button[aria-label^="Reset"]').disabled,
    };
  });
  assert.equal(shown.hidden, false);
  assert.deepEqual(shown.faces, ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"]);
  assert.equal(shown.name, "Red Panda");
  assert.equal(shown.line, "Bella, 2 steps higher, at normal pace.");
  assert.equal(shown.voice, "af_bella");
  assert.equal(shown.voiceLabel, "Red Panda's voice");
  assert.equal(shown.pitch, "2");
  assert.equal(shown.pitchText, "2 steps higher");
  assert.equal(shown.shown, "+2");
  assert.equal(shown.pace, "normal");
  assert.equal(shown.reset, true, "its own voice already: nothing to reset");

  await page.selectOption('.cv-animal[data-face="redpanda"] select', "af_sarah");
  await page.waitForTimeout(250);
  await page.click('.cv-animal[data-face="pygmyowl"] .choices button[data-value="faster"]');
  await page.waitForTimeout(250);
  await page.evaluate(() => {
    const r = document.querySelector('.cv-animal[data-face="seaotter"] input[type=range]');
    r.value = "-1.5";
    r.dispatchEvent(new Event("input"));
    r.dispatchEvent(new Event("change"));
  });
  await page.waitForTimeout(250);
  const sent = await calls(page, "set_voice_animal");
  const said = await page.evaluate(() =>
    document.querySelector('.cv-animal[data-face="redpanda"] .status').textContent);
  const kept = await page.evaluate(() =>
    document.querySelector('.cv-animal[data-face="redpanda"] select').dataset.mark);
  await page.click('.cv-animal[data-face="seaotter"] button[aria-label^="Try"]');
  await page.waitForTimeout(300);
  const tried = await calls(page, "try_voice_animal");
  const trySaid = await page.evaluate(() =>
    document.querySelector('.cv-animal[data-face="seaotter"] .status').textContent);
  await page.close();
  assert.deepEqual(sent, [
    { face: "redpanda", speaker: "af_sarah", semitones: 2, pace: "normal" },
    { face: "pygmyowl", speaker: "af_nicole", semitones: 1, pace: "faster" },
    { face: "seaotter", speaker: "af_sarah", semitones: -1.5, pace: "faster" },
  ]);
  assert.equal(said, "The Red Panda's voice is now Sarah, 1.5 steps deeper, a little faster.");
  assert.doesNotMatch(said, /approv/i, "no card for an animal's voice");
  assert.equal(kept, "kept", "a repaint keeps the same controls (and so the keyboard focus)");
  assert.deepEqual(tried, [{ face: "seaotter" }]);
  assert.doesNotMatch(trySaid, /try again|could not|not a sound/i, trySaid);

  const changed = await open(V.animal_changed);
  const canReset = await changed.evaluate(() =>
    !document.querySelector('.cv-animal[data-face="redpanda"] button[aria-label^="Reset"]').disabled);
  await changed.click('.cv-animal[data-face="redpanda"] button[aria-label^="Reset"]');
  await changed.waitForTimeout(250);
  const reset = await calls(changed, "reset_voice_animal");
  const resetSaid = await changed.evaluate(() =>
    document.querySelector('.cv-animal[data-face="redpanda"] .status').textContent);
  await changed.close();
  assert.equal(canReset, true);
  assert.deepEqual(reset, [{ face: "redpanda" }]);
  assert.equal(resetSaid, "The Red Panda speaks in its own voice again.");

  const stale = await open(V.animal_changed, {}, { link: { stale: true } });
  const held = await stale.evaluate(() => {
    const r = document.querySelector('.cv-animal[data-face="redpanda"]');
    return {
      voice: r.querySelector("select").disabled,
      pitch: r.querySelector("input[type=range]").disabled,
      pace: [...r.querySelectorAll(".choices button")].every((b) => b.disabled),
      reset: r.querySelector('button[aria-label^="Reset"]').disabled,
      tryIt: r.querySelector('button[aria-label^="Try"]').disabled,
    };
  });
  await stale.click('.cv-animal[data-face="redpanda"] button[aria-label^="Try"]');
  await stale.waitForTimeout(250);
  const staleTry = await calls(stale, "try_voice_animal");
  const none = await calls(stale, "set_voice_animal");
  await stale.close();
  assert.deepEqual(held, { voice: true, pitch: true, pace: true, reset: true, tryIt: false },
    "changes are held on a stale link; Try it changes nothing, so it is not");
  assert.deepEqual(staleTry, [{ face: "redpanda" }]);
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
  assert.match(fnBody(RUST, "pub async fn set_voice_speaker("), /if stale\(&app\) \{\s+return Err\(HELD_STALE/);
  assert.match(fnBody(RUST, "pub async fn set_voice_face("), /if stale\(&app\) \{\s+return Err\(HELD_STALE/);
  assert.match(fnBody(RUST, "pub async fn set_voice_animal("), /if stale\(&app\) \{\s+return Err\(HELD_STALE/);
  assert.match(fnBody(RUST, "pub async fn reset_voice_animal("), /if stale\(&app\) \{\s+return Err\(HELD_STALE/);
  assert.doesNotMatch(fnBody(RUST, "pub async fn try_voice_animal("), /stale/, "Try it changes nothing: never held");
  assert.ok(fnBody(RUST, "pub async fn try_voice_animal(").includes("/api/voice/voices/face_animal/try"));
  assert.doesNotMatch(fnBody(RUST, "pub async fn delete_custom_voice("), /stale/);
  for (const [fn, route] of [["create_custom_voice", "/api/voice/voices/create"], ["set_active_voice", "/api/voice/voices/active"],
    ["delete_custom_voice", "/api/voice/voices/delete"], ["set_better_voice", "/api/voice/voices/better"],
    ["set_voice_speed", "/api/voice/voices/speed"], ["set_voice_speaker", "/api/voice/voices/speaker"],
    ["set_voice_face", "/api/voice/voices/face"], ["set_voice_animal", "/api/voice/voices/face_animal"],
    ["reset_voice_animal", "/api/voice/voices/face_animal"]]) {
    assert.ok(fnBody(RUST, `pub async fn ${fn}(`).includes(`"${route}"`), `${fn} does not post to ${route}`);
  }
  assert.match(fnBody(RUST, "pub async fn get_custom_voices("), /\.headers\(jarvis_headers\(&app\)\?\)/);
});

/* ── "Try it" never plays over Jarvis ───────────────────────────────── */

/** `seconds` of silence as a 24 kHz mono 16-bit WAV data URI. */
const silence = (seconds) => {
  const n = Math.round(24000 * seconds);
  const b = Buffer.alloc(44 + n * 2);
  b.write("RIFF", 0); b.writeUInt32LE(36 + n * 2, 4); b.write("WAVE", 8);
  b.write("fmt ", 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22);
  b.writeUInt32LE(24000, 24); b.writeUInt32LE(48000, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write("data", 36); b.writeUInt32LE(n * 2, 40);
  return `data:audio/wav;base64,${b.toString("base64")}`;
};
const LONG_TRY = { animalTry: { ok: true, http: 200, audio: silence(4) } };
const rowSays = (page, face) => page.evaluate((f) =>
  document.querySelector(`.cv-animal[data-face="${f}"] .status`).textContent, face);
/** Counts every audio pause on the page (the Try it clip is never in the DOM). */
const countPauses = (page) => page.evaluate(() => {
  window.__paused = 0;
  const pause = HTMLMediaElement.prototype.pause;
  HTMLMediaElement.prototype.pause = function counted() { window.__paused += 1; return pause.call(this); };
});
const tryOn = (page, face) => page.click(`.cv-animal[data-face="${face}"] button[aria-label^="Try"]`);

await check("Try it: the same words as the phone, step by step", async () => {
  assert.equal(CV.TRY_ASKING, "Asking the PC for the sound…");
  assert.equal(CV.tryPlaying("Red Panda"), "Playing the Red Panda's voice.");
  assert.equal(CV.tryDone("Red Panda"), "That was the Red Panda's voice.");
  // The phone's own file says each of them, word for word.
  const kt = readFileSync(join(HERE, "..", "..", "jarvis-client", "app", "src", "main", "java",
    "com", "jarvis", "client", "net", "CustomVoices.kt"), "utf8");
  for (const [name, words] of [["TRY_ASKING", CV.TRY_ASKING], ["TRY_BUSY", CV.TRY_BUSY],
    ["TRY_STOPPED", CV.TRY_STOPPED], ["TRY_UPDATE", CV.TRY_UPDATE]]) {
    // Kotlin writes a backslash as two.
    const inKt = words.replace(/\\/g, "\\\\");
    assert.ok(kt.includes(`const val ${name} = "${inKt}"`), `the phone's ${name} is not "${words}"`);
  }
  assert.ok(kt.includes('fun tryPlaying(name: String): String = "Playing the $name\'s voice."'));
  assert.ok(kt.includes('fun tryDone(name: String): String = "That was the $name\'s voice."'));
  // The Rust says the busy and too-old sentences itself (voice_training.rs).
  for (const [name, words] of [["TRY_BUSY", CV.TRY_BUSY], ["TRY_UPDATE", CV.TRY_UPDATE]]) {
    const m = RUST.match(new RegExp(`pub\\(crate\\) const ${name}: &str =\\s*"([^"]+)";`));
    assert.ok(m, `voice_training.rs has no ${name}`);
    assert.equal(m[1].replace(/\\\\/g, "\\"), words, name);
  }

  const page = await open(V.face_showing, LONG_TRY);
  await tryOn(page, "redpanda");
  await page.waitForTimeout(400);
  const playing = await rowSays(page, "redpanda");
  await page.close();
  assert.equal(playing, "Playing the Red Panda's voice.");
  const short = await open(V.face_showing);
  await tryOn(short, "seaotter");
  await short.waitForTimeout(800);
  const done = await rowSays(short, "seaotter");
  await short.close();
  assert.equal(done, "That was the Sea Otter's voice.");
});

await check("Try it is refused while Jarvis speaks or answers - nothing is asked of the PC", async () => {
  // The Jarvis bar playing an answer (face-voice's clock, every window).
  const page = await open(V.face_showing);
  await page.evaluate(() => window.__emit("face-voice", { id: 1, n: 1, t: 0.4, at: Date.now(), playing: true, rate: 1 }));
  await tryOn(page, "redpanda");
  await page.waitForTimeout(250);
  const said = await rowSays(page, "redpanda");
  const asked = await calls(page, "try_voice_animal");
  // It ends: Try it works again.
  await page.evaluate(() => window.__emit("face-voice", { id: 1, n: 2, t: 1.2, at: Date.now(), playing: false, end: true, rate: 1 }));
  await tryOn(page, "redpanda");
  await page.waitForTimeout(250);
  const after = await calls(page, "try_voice_animal");
  await page.close();
  assert.equal(said, CV.TRY_BUSY);
  assert.deepEqual(asked, []);
  assert.deepEqual(after, [{ face: "redpanda" }]);

  // A question being answered (the link's activity), on a live link.
  const busy = await open(V.face_showing, {}, { link: { connected: true, stale: false, activity: "thinking" } });
  await tryOn(busy, "pygmyowl");
  await busy.waitForTimeout(250);
  const busySaid = await rowSays(busy, "pygmyowl");
  const busyAsked = await calls(busy, "try_voice_animal");
  await busy.close();
  assert.equal(busySaid, CV.TRY_BUSY);
  assert.deepEqual(busyAsked, []);

  // The talk button recording: the Rust refuses, and its words are shown as they are.
  const ptt = await open(V.face_showing, { fails: { try_voice_animal: CV.TRY_BUSY } });
  await tryOn(ptt, "redpanda");
  await ptt.waitForTimeout(250);
  const pttSaid = await rowSays(ptt, "redpanda");
  await ptt.close();
  assert.equal(pttSaid, CV.TRY_BUSY);

  // An older PC: the phone's sentence, not the general "update" one.
  const old = await open(V.face_showing, { fails: { try_voice_animal: CV.TRY_UPDATE } });
  await tryOn(old, "redpanda");
  await old.waitForTimeout(250);
  const oldSaid = await rowSays(old, "redpanda");
  await old.close();
  assert.equal(oldSaid, CV.TRY_UPDATE);

  // Two at once on the PC: its own words.
  const two = await open(V.face_showing, { animalTry: P("animal_try_busy") });
  await tryOn(two, "redpanda");
  await two.waitForTimeout(250);
  const twoSaid = await rowSays(two, "redpanda");
  await two.close();
  assert.equal(twoSaid, "The PC is still making another voice sample. Try again in a moment.");
});

await check("Try it stops the moment a question or an answer starts, and on Stop everything", async () => {
  for (const [event, payload] of [
    ["voice-capture-started", null],
    ["voice-speech-started", null],
    ["voice-heard", { available: true, text: "what time is it" }],
    ["face-voice", { id: 2, n: 1, t: 0, at: Date.now(), playing: true, rate: 1 }],
  ]) {
    const page = await open(V.face_showing, LONG_TRY);
    await countPauses(page);
    await tryOn(page, "redpanda");
    await page.waitForTimeout(400);
    const before = await rowSays(page, "redpanda");
    await page.evaluate(([e, p]) => window.__emit(e, p), [event, payload]);
    await page.waitForTimeout(150);
    const after = await rowSays(page, "redpanda");
    const paused = await page.evaluate(() => window.__paused);
    await page.close();
    assert.equal(before, "Playing the Red Panda's voice.", event);
    assert.equal(after, CV.TRY_STOPPED, event);
    assert.equal(paused, 1, `${event}: the clip was not paused`);
  }
  const page = await open(V.face_showing, LONG_TRY);
  await countPauses(page);
  await tryOn(page, "redpanda");
  await page.waitForTimeout(400);
  await page.evaluate(() => window.__emit("stop-everything", null));
  await page.waitForTimeout(150);
  const hushed = await rowSays(page, "redpanda");
  const paused = await page.evaluate(() => window.__paused);
  await page.close();
  assert.equal(hushed, "");
  assert.equal(paused, 1);
});

/* ── "Hear it": a button on every built-in voice (2026-09-29) ──────────── */

const hearButtons = (page) => page.evaluate(() =>
  [...document.querySelectorAll("#cv-speaker-choices .cv-choice button[data-hear]")].map((b) => b.dataset.hear));
// What was said beside the tapped voice (each voice has its own line).
const hearSays = (page) => page.evaluate(() =>
  [...document.querySelectorAll("#cv-speaker-choices .cv-hear-status")].map((e) => e.textContent).find((t) => t) || "");
const hearOn = (page, voice) => page.click(`#cv-speaker-choices button[data-hear="${voice}"]`);

/* ── Ashby and Clara: two voices blended for Jarvis (2026-09-29) ────────── */

await check("Ashby and Clara: listed first with the PC's one plain line, a Hear it on each, chosen like any voice", async () => {
  const st = V.pack_v1_blends;
  const sk = CV.speakerView(st);
  assert.deepEqual(sk.choices.map((c) => c.id).slice(0, 3), ["mix_ashby", "mix_clara", "af_heart"]);
  assert.deepEqual(sk.choices.slice(0, 2).map((c) => c.label), ["Ashby (made for Jarvis)", "Clara (made for Jarvis)"]);
  assert.match(sk.choices[0].detail, /^A warm British butler, calm and a little slower\./);
  assert.match(sk.choices[1].detail, /^A warm woman's voice that leans British\./);
  assert.ok(sk.choices.slice(2).every((c) => c.detail === ""), "only the two carry a line");
  assert.equal(sk.note, "", "made and loaded: nothing left to say");
  noRaw([sk.note, ...sk.choices.map((c) => `${c.label} ${c.detail}`)].join(" "));
  const page = await open(st, { speaker: P("pack_v1_ashby") });
  const shown = await page.evaluate(() => ({
    rows: [...document.querySelectorAll("#cv-speaker-choices .cv-choice")].map((w) => ({
      id: w.querySelector("input").value,
      blurb: w.querySelector(".theme-blurb")?.textContent || "",
      hear: w.querySelector("button[data-hear]")?.getAttribute("aria-label") || "",
    })),
  }));
  assert.deepEqual(shown.rows.slice(0, 2).map((r) => [r.id, r.hear]),
    [["mix_ashby", "Hear Ashby (made for Jarvis)"], ["mix_clara", "Hear Clara (made for Jarvis)"]]);
  assert.equal(shown.rows[0].blurb, sk.choices[0].detail, "the line is under the name");
  assert.ok(shown.rows.slice(2).every((r) => r.blurb === "" && r.hear), "the others: no line, still a Hear it");
  await page.click('#cv-speaker-choices input[value="mix_ashby"]');
  await page.waitForTimeout(200);
  const sent = await calls(page, "set_voice_speaker");
  const said = await text(page, "cv-speaker-status");
  await page.close();
  assert.deepEqual(sent, [{ speaker: "mix_ashby" }], "chosen by its name, like every voice");
  assert.equal(said, "Jarvis's built-in voice is now Ashby (made for Jarvis).");
  assert.doesNotMatch(said, /approv/i, "no card for a built-in voice");
});

await check("Ashby and Clara: Hear it asks the PC by name; the PC's refusals and the new-pack words are shown as they are", async () => {
  const page = await open(V.pack_v1_blends, LONG_TRY);
  await hearOn(page, "mix_clara");
  await page.waitForTimeout(400);
  const playing = await hearSays(page);
  const asked = await calls(page, "hear_voice_sample");
  const chosen = await calls(page, "set_voice_speaker");
  await page.close();
  assert.equal(playing, "Playing Clara (made for Jarvis).");
  assert.deepEqual(asked, [{ voice: "mix_clara" }]);
  assert.deepEqual(chosen, [], "Hear it never changes the voice Jarvis uses");
  // A voice that sounds like the owner: not listed any more, and it says why.
  const refused = CV.speakerView(V.pack_v1_ashby_refused_listed);
  assert.deepEqual(refused.choices.slice(0, 2).map((c) => c.id), ["mix_clara", "af_heart"]);
  assert.equal(refused.note, "Ashby sounds too close to your own voice, and a voice that sounds like you could pass Jarvis's own voice check. Jarvis will not use it, so the normal voice speaks.");
  assert.equal(CV.voiceReply(P("pack_v1_ashby_refused"), WHERE).text,
    "Ashby sounds too close to your own voice, and a voice that sounds like you could pass Jarvis's own voice check. Jarvis will not use it, so the normal voice speaks.");
  assert.equal(CV.voiceReply(P("pack_v1_sample_refused"), WHERE).text,
    "Ashby sounds too close to your own voice, and a voice that sounds like you could pass Jarvis's own voice check. Jarvis will not use it, so the normal voice speaks.");
  // The old pack: not listed, and the picker says they need the newer pack.
  const old = CV.speakerView(V.pack_old);
  assert.ok(!old.choices.some((c) => c.id.startsWith("mix_")));
  assert.ok(old.note.endsWith("Ashby and Clara, two voices made for Jarvis, need the newer voice pack (Kokoro v1.0)."), old.note);
  assert.equal(CV.voiceReply(P("pack_old_ashby"), WHERE).text, "Choose one of the listed voices.");
  // The animals cannot be given either: their list is the pack's own eleven.
  for (const st of [V.pack_v1_blends, V.pack_v1_ashby_chosen]) {
    const ids = CV.animalVoicesView(st).voices.map((v) => v.id);
    assert.ok(!ids.some((i) => i.startsWith("mix_")), `an animal's voice list has ${ids}`);
  }
  const chosen2 = CV.speakerView(V.pack_v1_ashby_chosen);
  assert.equal(chosen2.choice, "mix_ashby");
});

await check("Hear it: the same words as the phone, and a button on every voice", async () => {
  assert.equal(CV.HEAR_LABEL, "Hear it");
  assert.equal(CV.hearPlaying("American (female) - Bella"), "Playing American (female) - Bella.");
  assert.equal(CV.hearDone("American (female) - Bella"), "That was American (female) - Bella.");
  const kt = readFileSync(join(HERE, "..", "..", "jarvis-client", "app", "src", "main", "java",
    "com", "jarvis", "client", "net", "CustomVoices.kt"), "utf8");
  for (const [name, words] of [["HEAR_LABEL", CV.HEAR_LABEL], ["HEAR_BUSY", CV.HEAR_BUSY],
    ["HEAR_LOCKED", CV.HEAR_LOCKED], ["HEAR_UPDATE", CV.HEAR_UPDATE]]) {
    const inKt = words.replace(/\\/g, "\\\\");
    assert.ok(kt.includes(`const val ${name} = "${inKt}"`), `the phone's ${name} is not "${words}"`);
  }
  assert.ok(kt.includes('fun hearPlaying(label: String): String = "Playing $label."'));
  assert.ok(kt.includes('fun hearDone(label: String): String = "That was $label."'));
  // The Rust says the busy, locked and too-old sentences itself.
  for (const [name, words] of [["HEAR_BUSY", CV.HEAR_BUSY], ["HEAR_LOCKED", CV.HEAR_LOCKED],
    ["HEAR_UPDATE", CV.HEAR_UPDATE]]) {
    const m = RUST.match(new RegExp(`pub\\(crate\\) const ${name}: &str =\\s*"([^"]+)";`));
    assert.ok(m, `voice_training.rs has no ${name}`);
    assert.equal(m[1].replace(/\\\\/g, "\\"), words, name);
  }
  // The PC's own refusals, as it says them.
  assert.equal(CV.voiceReply(P("sample_bad"), WHERE).text, "Choose one of the listed voices.");
  assert.equal(CV.voiceReply(P("sample_busy"), WHERE).text,
    "The PC is still making another voice sample. Try again in a moment.");
  for (const st of [V.pack_old, V.pack_v1]) {
    const page = await open(st);
    const ids = await hearButtons(page);
    const radios = await page.evaluate(() =>
      [...document.querySelectorAll("#cv-speaker-choices input[type=radio]")].map((r) => r.value));
    const labelled = await page.evaluate(() =>
      [...document.querySelectorAll("#cv-speaker-choices button[data-hear]")].map((b) => [b.textContent, b.getAttribute("aria-label")]));
    await page.close();
    assert.deepEqual(ids, radios, "every voice has a Hear it, in the same order");
    assert.ok(labelled.every(([t, a]) => t === "Hear it" && /^Hear .+/.test(a)), JSON.stringify(labelled));
  }
});

await check("Hear it: asks the PC for that voice by name, plays it, and changes nothing", async () => {
  const page = await open(V.pack_v1, LONG_TRY);
  await hearOn(page, "am_fenrir");
  await page.waitForTimeout(400);
  const playing = await hearSays(page);
  // The words sit beside the tapped voice (its own row), and its button reads "Stop" while it plays.
  const beside = await page.evaluate(() => {
    const b = document.querySelector('#cv-speaker-choices button[data-hear="am_fenrir"]');
    return { button: b.textContent, own: b.parentElement.querySelector(".cv-hear-status").textContent };
  });
  const asked = await calls(page, "hear_voice_sample");
  const chosen = await calls(page, "set_voice_speaker");
  const stillTicked = await page.evaluate(() =>
    [...document.querySelectorAll("#cv-speaker-choices input")].find((r) => r.checked)?.value);
  await page.close();
  assert.equal(playing, "Playing American (male) - Fenrir.");
  assert.deepEqual(beside, { button: "Stop", own: "Playing American (male) - Fenrir." });
  assert.deepEqual(asked, [{ voice: "am_fenrir" }]);
  assert.deepEqual(chosen, [], "Hear it never changes the voice Jarvis uses");
  assert.equal(stillTicked, "af_heart");
  const short = await open(V.pack_v1);
  await hearOn(short, "bm_george");
  await short.waitForTimeout(800);
  const done = await hearSays(short);
  await short.close();
  assert.equal(done, "That was British (male) - George.");
});

await check("Hear it: never held on a stale link (it changes nothing), never over Jarvis", async () => {
  const stale = await open(V.pack_v1, {}, { link: { stale: true } });
  const allowed = await stale.evaluate(() =>
    [...document.querySelectorAll("#cv-speaker-choices button[data-hear]")].every((b) => !b.disabled));
  await hearOn(stale, "af_bella");
  await stale.waitForTimeout(250);
  const staleAsked = await calls(stale, "hear_voice_sample");
  await stale.close();
  assert.equal(allowed, true);
  assert.deepEqual(staleAsked, [{ voice: "af_bella" }]);

  // Jarvis speaking (the Jarvis bar's clock): refused, nothing asked of the PC.
  const page = await open(V.pack_v1);
  await page.evaluate(() => window.__emit("face-voice", { id: 1, n: 1, t: 0.4, at: Date.now(), playing: true, rate: 1 }));
  await hearOn(page, "af_bella");
  await page.waitForTimeout(250);
  const said = await hearSays(page);
  const asked = await calls(page, "hear_voice_sample");
  await page.close();
  assert.equal(said, CV.HEAR_BUSY);
  assert.deepEqual(asked, []);

  // A question being answered, on a live link.
  const busy = await open(V.pack_v1, {}, { link: { connected: true, stale: false, activity: "thinking" } });
  await hearOn(busy, "af_bella");
  await busy.waitForTimeout(250);
  const busySaid = await hearSays(busy);
  const busyAsked = await calls(busy, "hear_voice_sample");
  await busy.close();
  assert.equal(busySaid, CV.HEAR_BUSY);
  assert.deepEqual(busyAsked, []);

  // The Rust refuses too (talk button, Live, App lock): its words are shown as they are.
  for (const words of [CV.HEAR_BUSY, CV.HEAR_LOCKED, CV.HEAR_UPDATE]) {
    const p = await open(V.pack_v1, { fails: { hear_voice_sample: words } });
    await hearOn(p, "af_bella");
    await p.waitForTimeout(250);
    const got = await hearSays(p);
    await p.close();
    assert.equal(got, words);
  }
  // Two at once on the PC: its own words.
  const two = await open(V.pack_v1, { animalTry: P("sample_busy") });
  await hearOn(two, "af_bella");
  await two.waitForTimeout(250);
  const twoSaid = await hearSays(two);
  await two.close();
  assert.equal(twoSaid, "The PC is still making another voice sample. Try again in a moment.");
});

await check("Hear it stops the moment a question or an answer starts, and on Stop everything", async () => {
  for (const [event, payload] of [
    ["voice-capture-started", null],
    ["voice-speech-started", null],
    ["voice-heard", { available: true, text: "what time is it" }],
    ["face-voice", { id: 2, n: 1, t: 0, at: Date.now(), playing: true, rate: 1 }],
  ]) {
    const page = await open(V.pack_v1, LONG_TRY);
    await countPauses(page);
    await hearOn(page, "af_bella");
    await page.waitForTimeout(400);
    await page.evaluate(([e, p]) => window.__emit(e, p), [event, payload]);
    await page.waitForTimeout(150);
    const after = await hearSays(page);
    const paused = await page.evaluate(() => window.__paused);
    await page.close();
    assert.equal(after, CV.TRY_STOPPED, event);
    assert.equal(paused, 1, `${event}: the clip was not paused`);
  }
  const page = await open(V.pack_v1, LONG_TRY);
  await countPauses(page);
  await hearOn(page, "af_bella");
  await page.waitForTimeout(400);
  await page.evaluate(() => window.__emit("stop-everything", null));
  await page.waitForTimeout(150);
  const hushed = await hearSays(page);
  const paused = await page.evaluate(() => window.__paused);
  await page.close();
  assert.equal(hushed, "");
  assert.equal(paused, 1);
});

await check("CONTROL (Rust): Hear it is never held on a stale link, refuses the talk button, Live and App lock", async () => {
  const body = fnBody(RUST, "pub async fn hear_voice_sample(");
  assert.doesNotMatch(body, /stale/, "Hear it changes nothing: never held");
  assert.match(body, /crate::lock::app_locked\(&app\)[\s\S]*HEAR_LOCKED/);
  assert.match(body, /capture\.busy\(\) \|\| crate::live::on_here\(\)[\s\S]*HEAR_BUSY/);
  assert.match(body, /HEAR_UPDATE/, "an older PC's 404 is said in the phone's words");
  assert.ok(body.includes('"/api/voice/voices/sample"'));
  assert.ok(body.includes('json!({ "voice": voice })'), "only the voice's name is sent, never any words");
  assert.match(read("src-tauri/build.rs"), /"hear_voice_sample"/);
  assert.match(read("src-tauri/src/lib.rs"), /voice_training::hear_voice_sample/);
  assert.match(read("src-tauri/permissions/surfaces.toml"), /"allow-hear-voice-sample"/);
});

await check("CONTROL (Rust): Try it is refused while the talk button records, and the talk button tells Settings", async () => {
  const body = fnBody(RUST, "pub async fn try_voice_animal(");
  assert.match(body, /if capture\.busy\(\) \{\s+return Err\(TRY_BUSY\.to_string\(\)\);/);
  assert.match(body, /TRY_UPDATE/, "an older PC's 404 is said in the phone's words");
  const voice = read("src-tauri/src/voice.rs");
  const start = fnBody(voice, "pub fn start_voice_capture(");
  const told = start.indexOf("VOICE_CAPTURE_STARTED");
  assert.ok(told > -1, "start_voice_capture does not tell the other windows");
  assert.ok(told < start.indexOf("spawn_capture_thread"), "told only after the microphone opened");
  assert.match(read("src-tauri/src/lib.rs"), /pub const VOICE_CAPTURE_STARTED: &str = "voice-capture-started";/);
  const panel = read("src/voice-panel.js");
  for (const e of ["voice-capture-started", "voice-speech-started", "voice-heard", "face-voice", "stop-everything"]) {
    assert.ok(panel.includes(`"${e}"`), `Settings does not hear ${e}`);
  }
  assert.match(fnBody(panel, "async function startRecording("), /stopTry\(\)/,
    "a recording in Settings stops a Try it clip first");
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
