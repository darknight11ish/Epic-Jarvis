/**
 * personalities.mjs - the Personality Presets page data, held pure.
 *
 * Runs on plain Node (no browser, no Tauri):
 *
 *     node tests/personalities.mjs
 *
 * WHY THIS EXISTS (2026-10-23, Personality Presets SLICE 2a). The eight
 * built-in presets, the four tuning dials, the "My personalities" limits and
 * the bodies sent to the PC's `/api/manner` live in src/personalities.js.
 * This file holds that module to the blueprint's own table (section 2) and to
 * the page's rules:
 *
 *   - the eight ids, in order, and each one's paired voice and speed;
 *   - the four dials' accepted values, and nothing else;
 *   - the PC's answer WINS when it carries the fields (and only then is the
 *     page allowed to switch anything);
 *   - a PC without the fields answers the local copy, marked `pc: false`;
 *   - the 240-character limit on a custom line, the 60-character name limit,
 *     a duplicate-proof id, and the explicit confirm the delete carries;
 *   - the sample request carries exactly the preset's base voice and nothing
 *     else (the PC's sample route accepts `{"voice"}` only; a blended-voice
 *     preview is deferred to the Kokoro/Live slice), and the badge's
 *     "Blend · 1.02x" words keep saying what the character stores.
 *
 * What it does NOT prove: how the page looks, that a real PC accepts the
 * bodies, or that a sample plays. Those need the app running.
 */

import assert from "node:assert/strict";
import * as P from "../src/personalities.js";

const fails = [];
const check = (name, fn) => {
  try {
    fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── 1. The eight built-in presets (blueprint section 2, in order) ─────── */

check("the eight preset ids are the blueprint's, in its order", () => {
  assert.deepEqual([...P.PRESET_IDS], [
    "warm_peer", "classic_butler", "tactical_ops", "dry_wit",
    "friday_partner", "socratic_mentor", "devils_advocate", "calm_stoic",
  ]);
  assert.equal(P.PRESETS.length, 8);
});

check("every preset has a title, one-line description, sample line and switch line", () => {
  for (const preset of P.PRESETS) {
    assert.ok(preset.title.length > 3, `${preset.id}: title`);
    assert.ok(preset.description.length > 10, `${preset.id}: description`);
    assert.ok(preset.quote.length > 5, `${preset.id}: quote`);
    assert.ok(preset.switchAck.length > 10, `${preset.id}: switch line`);
    assert.ok(preset.badge.length > 0, `${preset.id}: badge`);
  }
});

check("every preset's voice blend is two named voices that sum to one", () => {
  for (const preset of P.PRESETS) {
    const parts = preset.voice.blend.split("+");
    assert.equal(parts.length, 2, `${preset.id}: two voices`);
    let sum = 0;
    for (const part of parts) {
      const [name, weight] = part.split(":");
      assert.match(name, /^[a-z]{2}_[a-z]+$/, `${preset.id}: voice name`);
      sum += Number(weight);
    }
    assert.ok(Math.abs(sum - 1) < 1e-9, `${preset.id}: weights sum to 1, got ${sum}`);
    assert.match(preset.voice.fallback, /^[a-z]{2}_[a-z]+$/, `${preset.id}: fallback`);
    assert.ok(preset.voice.speed >= 0.9 && preset.voice.speed <= 1.1,
      `${preset.id}: speed ${preset.voice.speed}`);
  }
});

check("the blueprint's own pairings survive (spot checks)", () => {
  const by = (id) => P.PRESETS.find((p) => p.id === id);
  assert.equal(by("classic_butler").voice.blend, "bm_george:0.65+bm_lewis:0.35");
  assert.equal(by("classic_butler").voice.fallback, "bm_george");
  assert.equal(by("classic_butler").voice.speed, 1.02);
  assert.equal(P.voiceBadge(by("classic_butler")), "British Baritone Blend \u00b7 1.02x");
  assert.equal(by("calm_stoic").voice.speed, 0.94);
  assert.equal(by("tactical_ops").voice.speed, 1.1);
  assert.equal(by("dry_wit").voice.blend, "bm_lewis:0.70+am_adam:0.30");
});

check("the page never invents a blank voice badge", () => {
  assert.equal(P.voiceBadge(null), "Voice blend");
  assert.equal(P.voiceBadge({ voice: { label: "Mine" } }), "Mine");
});

/* ── 2. The four dials ─────────────────────────────────────────────────── */

check("the four dials are the blueprint's, in the page's order", () => {
  assert.deepEqual([...P.DIAL_KEYS], ["humor", "brevity", "formality", "address"]);
  assert.deepEqual(P.DIALS.humor.choices.map((c) => c.id), [0, 1, 2, 3]);
  assert.deepEqual(P.DIALS.brevity.choices.map((c) => c.id),
    ["concise", "balanced", "thorough"]);
  assert.deepEqual(P.DIALS.formality.choices.map((c) => c.id),
    ["casual", "warm_peer", "formal_butler", "tactical"]);
  assert.deepEqual(P.DIALS.address.choices.map((c) => c.id),
    ["first_name", "sir", "ma'am", "boss", "captain", "none"]);
});

check("validDial accepts exactly the listed values and nothing else", () => {
  assert.ok(P.validDial("humor", 0) && P.validDial("humor", 3));
  assert.ok(!P.validDial("humor", 4) && !P.validDial("humor", "2"));
  assert.ok(P.validDial("brevity", "thorough") && !P.validDial("brevity", "long"));
  assert.ok(!P.validDial("address", "Sir") && P.validDial("address", "sir"));
  assert.ok(!P.validDial("nope", 1));
});

check("readDials keeps the good values and fills the rest from the preset", () => {
  const got = P.readDials({ humor: 3, brevity: "nonsense" },
    { dials: { humor: 1, brevity: "balanced", formality: "warm_peer",
               address: "first_name" } });
  assert.deepEqual(got, { humor: 3, brevity: "balanced", formality: "warm_peer",
                          address: "first_name" });
});

check("the default preset is warm_peer, and the legacy names map to presets", () => {
  assert.equal(P.DEFAULT_PRESET, "warm_peer");
  assert.equal(P.normalizeId("warm"), "warm_peer");
  assert.equal(P.normalizeId("plain"), "tactical_ops");
  assert.equal(P.normalizeId("dry_wit"), "dry_wit");
  assert.equal(P.presetTitle("classic_butler"), "Classic British Butler");
});

/* ── 3. The PC's answer wins, and only then may the page switch ────────── */

check("a PC with the fields overrides this file's copy, field by field", () => {
  const got = P.readPersonalities({
    available: true,
    personality: "plain",
    dials: { humor: 2, brevity: "thorough", formality: "casual", address: "boss" },
    voice_sync: true,
    personalities: [{ id: "warm_peer", title: "PC Warm", description: "The PC's words",
                      quote: "PC quote", switch_ack: "PC switch line",
                      voice: { label: "PC Voice", speed: 1.03 } }],
    custom_personalities: [{ id: "mine-one", name: "Mine", line: "A line",
                             example: "You: hi", based_on: "calm_stoic",
                             dials: { humor: 0 } }],
  });
  assert.equal(got.pc, true);
  const warm = got.presets.find((p) => p.id === "warm_peer");
  assert.equal(warm.title, "PC Warm");
  assert.equal(warm.description, "The PC's words");
  assert.equal(warm.voice.speed, 1.03);
  assert.equal(got.active, "tactical_ops", "legacy plain maps to the preset");
  assert.deepEqual(got.dials, { humor: 2, brevity: "thorough", formality: "casual",
                                address: "boss" });
  assert.equal(got.voiceSync, true);
  assert.equal(got.custom.length, 1);
  assert.equal(got.custom[0].title, "Mine");
});

check("a PC without the fields answers the local copy, marked pc: false", () => {
  const got = P.readPersonalities({ available: true, manner: "warm",
                                    choices: [{ id: "warm" }, { id: "plain" }] });
  assert.equal(got.pc, false);
  assert.equal(got.presets.length, 8);
  assert.equal(got.active, "", "an old answer does not name a preset");
  assert.deepEqual(got.dials, P.defaultDials());
  assert.equal(got.custom.length, 0);
  assert.ok(P.UPDATE_SENTENCE.includes("apply-patches.ps1"));
});

check("no answer at all is never drawn as a preset choice", () => {
  for (const raw of [null, undefined, {}, { available: false, why: "old" }]) {
    const got = P.readPersonalities(raw);
    assert.equal(got.pc, false);
    assert.equal(got.presets.length, 8);
    if (raw && raw.available === false) assert.equal(got.available, false);
  }
});

/* ── 4. "My personalities": caps, ids and the explicit delete confirm ───── */

check("a custom personality is cleaned, capped and given a safe id", () => {
  const made = P.customPersonality({
    name: "  My   Calm  ",
    line: "x".repeat(400),
    example: "You: hi\nJarvis: hello",
    dials: { humor: 0, brevity: "concise", formality: "warm_peer",
             address: "first_name" },
  }, P.PRESETS[7]);
  assert.equal(made.name, "My Calm");
  assert.equal(made.line.length, P.LIMITS.line);
  assert.equal(made.example, "You: hi Jarvis: hello");
  assert.match(made.id, /^mine-[a-z0-9-]+$/);
  assert.equal(made.basedOn, "calm_stoic");
  assert.deepEqual(made.dials, { humor: 0, brevity: "concise",
                                 formality: "warm_peer", address: "first_name" });
});

check("a custom personality with no name is refused in plain words", () => {
  const made = P.customPersonality({ name: "   " }, null);
  assert.ok(made.why.includes("name"));
});

check("the save body carries only the bounded fields; the delete body confirms", () => {
  const save = P.saveCustomBody({
    id: "mine-tester", name: "Tester", line: "Calm.", example: "On it.",
    dials: P.defaultDials(), basedOn: "calm_stoic",
  });
  assert.deepEqual(Object.keys(save), ["custom"]);
  assert.equal(save.custom.op, "save");
  assert.equal(save.custom.based_on, "calm_stoic");
  const del = P.deleteCustomBody("mine-tester");
  assert.deepEqual(del, { custom: { op: "delete", id: "mine-tester", confirm: true } });
});

check("the page's limits are the blueprint's 240-character lines and a 60-character name", () => {
  assert.equal(P.LIMITS.line, 240);
  assert.equal(P.LIMITS.name, 60);
  assert.equal(P.cleanLine("a\nb\tc"), "a b c");
  assert.equal(P.cleanLine("x".repeat(500)).length, 240);
});

check("a custom id that came from the PC is kept verbatim, so Use and Delete reach it", () => {
  const got = P.readPersonalities({ available: true, custom_personalities: [
    { id: "custom-my-mix", name: "Server Mix", base_preset: "calm_stoic" },
  ] });
  assert.equal(got.custom.length, 1);
  assert.equal(got.custom[0].id, "custom-my-mix",
    "the PC's own id must survive the read unchanged (customId used to rewrite it)");
  assert.deepEqual(P.usePresetBody(got.custom[0]), { personality: "custom-my-mix" });
  assert.deepEqual(P.deleteCustomBody(got.custom[0].id),
    { custom: { op: "delete", id: "custom-my-mix", confirm: true } });
  // The PC's own id rule, exposed so a future caller cannot guess it.
  assert.equal(P.serverIdOf("custom-my-mix"), "custom-my-mix");
  assert.equal(P.serverIdOf("mine-mix"), "mine-mix");
  assert.equal(P.serverIdOf("Not A Valid Id"), "");
  assert.equal(P.serverIdOf(""), "");
  // A first save still gets a page-made id: nothing to keep yet.
  assert.equal(P.customPersonality({ name: "Server Mix" }, P.PRESETS[7]).id,
    "mine-server-mix");
});

/* ── 5. The sample request and the one-field change bodies ─────────────── */

check("the sample request carries exactly the base voice and nothing else", () => {
  const preset = P.PRESETS[1];
  const args = P.sampleArgs(preset);
  assert.deepEqual(args, { voice: "bm_george" });
  assert.deepEqual(Object.keys(args), ["voice"],
    "the PC's /api/voice/voices/sample accepts set(body) == {'voice'}; any extra field is a 400");
  // The character still STORES its blend and speed (the badge says so, and a
  // later Kokoro/Live slice will preview them) - they are just not sent here.
  assert.equal(preset.voice.blend, "bm_george:0.65+bm_lewis:0.35");
  assert.equal(preset.voice.speed, 1.02);
  assert.match(P.HEAR_BASE_VOICE_NOTE, /base voice/i);
  assert.match(P.HEAR_BASE_VOICE_NOTE, /blended/i);
});

check("a preset switch sends the personality alone (never a whole answer)", () => {
  assert.deepEqual(P.usePresetBody(P.PRESETS[3]), { personality: "dry_wit" });
});

console.log(fails.length ? `\n${fails.length} failed` : "\nall passed");
process.exit(fails.length ? 1 : 0);
