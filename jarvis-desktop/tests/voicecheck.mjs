/**
 * The speech envelope — section B of the work order.
 *
 * Two things are being asserted, and the first matters more than the second.
 *
 *   1. The constants in `src/voice.js` are still the ones in
 *      `jarvis-visual-spec.json` → `speech`. A hand-tuned "that felt better"
 *      is exactly how a client stops matching the spec it claims to implement,
 *      and nothing else in the build would notice.
 *   2. The envelope actually behaves like an envelope: it rises in ~40ms,
 *      falls in ~120ms, gates hiss, floors a speaking face above idle, and the
 *      fallback rests when the spec says it rests.
 *
 * A screenshot cannot see a 40ms rise, so this drives the pure half directly
 * with a synthetic clock.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const spec = JSON.parse(readFileSync(join(SRC, "jarvis-visual-spec.json"), "utf8")).speech;
const source = readFileSync(join(SRC, "voice.js"), "utf8");

const V = await import(new URL("../src/voice.js", import.meta.url));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** Reads a `const NAME = <number>;` out of the module source. */
const constant = (name) => {
  const m = source.match(new RegExp(`const ${name} = ([0-9.]+);`));
  assert.ok(m, `voice.js has no constant named ${name}`);
  return Number(m[1]);
};

/* ── 1. The constants are the spec's ─────────────────────────────────────── */

check("envelope attack matches speech.envelope.attack_s", () => {
  assert.equal(constant("SPEECH_ATTACK_S"), spec.envelope.attack_s);
});
check("envelope release matches speech.envelope.release_s", () => {
  assert.equal(constant("SPEECH_RELEASE_S"), spec.envelope.release_s);
});
check("gate matches speech.envelope.gate", () => {
  assert.equal(constant("GATE"), spec.envelope.gate);
});
check("scale matches speech.scale", () => {
  assert.equal(constant("SCALE"), spec.scale);
});
check("brightness lift matches speech.brightness_lift", () => {
  assert.equal(constant("BRIGHTNESS_LIFT"), spec.brightness_lift);
});
check("speak floor matches speech.speak_floor", () => {
  assert.equal(constant("SPEAK_FLOOR"), spec.speak_floor);
});
check("the mic envelope matches listening_uses_same_path", () => {
  // "The microphone envelope (attack 30ms / release 220ms)".
  const text = String(spec.listening_uses_same_path);
  const ms = text.match(/attack (\d+)ms \/ release (\d+)ms/);
  assert.ok(ms, "the spec sentence no longer states the two numbers");
  assert.equal(constant("MIC_ATTACK_S"), Number(ms[1]) / 1000);
  assert.equal(constant("MIC_RELEASE_S"), Number(ms[2]) / 1000);
});
check("the fallback matches speech.fallback", () => {
  // "If no level has arrived for 0.5s while speaking, a synthetic envelope
  //  stands in: syllables at 4.2Hz with varying weight and a 220ms rest every
  //  2.3s."
  const text = String(spec.fallback);
  const after = text.match(/for ([0-9.]+)s/);
  const hz = text.match(/at ([0-9.]+)Hz/);
  const rest = text.match(/(\d+)ms rest every ([0-9.]+)s/);
  assert.ok(after && hz && rest, "the spec sentence no longer states the numbers");
  assert.equal(constant("FALLBACK_AFTER_S"), Number(after[1]));
  assert.equal(constant("SYLLABLE_HZ"), Number(hz[1]));
  assert.equal(constant("REST_FOR_S"), Number(rest[1]) / 1000);
  assert.equal(constant("REST_EVERY_S"), Number(rest[2]));
});

/* ── 2. The envelope behaves ─────────────────────────────────────────────── */

const DT = 1 / 120;

/** Runs the follower for `seconds`, feeding `level` every frame. */
const run = (seconds, level, feed = V.setSpeechLevel) => {
  let out = 0;
  for (let t = 0; t < seconds; t += DT) {
    if (level !== null) feed(level);
    out = V.advance(DT);
  }
  return out;
};

check("a syllable is ~63% up after one attack constant", () => {
  V.stopVoice();
  V.setVoiceMode("speaking");
  // One time constant of a one-pole follower is 1 - 1/e = 0.632 of the way.
  // The floor is already 0.18, so the reachable distance is 1 - 0.18.
  const at = run(spec.envelope.attack_s, 1);
  const want = spec.speak_floor + (1 - spec.speak_floor) * (1 - Math.exp(-1));
  assert.ok(Math.abs(at - want) < 0.06, `after 40ms env=${at.toFixed(3)}, wanted ~${want.toFixed(3)}`);
});

check("a syllable is essentially up after four attack constants", () => {
  V.stopVoice();
  V.setVoiceMode("speaking");
  const at = run(spec.envelope.attack_s * 4, 1);
  assert.ok(at > 0.95, `after 160ms env=${at.toFixed(3)}, wanted > 0.95`);
});

check("release is slower than attack, by the spec's ratio", () => {
  V.stopVoice();
  V.setVoiceMode("speaking");
  run(0.3, 1);
  const before = V.voiceLevel();
  // Fall towards the floor, not towards zero: this is still a speaking face.
  const after = run(spec.envelope.release_s, 0);
  const fell = before - after;
  const reach = before - spec.speak_floor;
  const want = reach * (1 - Math.exp(-1));
  assert.ok(Math.abs(fell - want) < 0.06, `fell ${fell.toFixed(3)}, wanted ~${want.toFixed(3)}`);
});

check("the gate holds hiss at the floor", () => {
  V.stopVoice();
  V.setVoiceMode("speaking");
  // Anything under the gate is not a syllable, so the face sits at the floor.
  const at = run(0.5, spec.envelope.gate - 0.005);
  assert.ok(Math.abs(at - spec.speak_floor) < 0.005, `env=${at.toFixed(3)}, wanted the floor`);
});

check("a speaking face never falls below the floor", () => {
  V.stopVoice();
  V.setVoiceMode("speaking");
  const at = run(2, 0);
  assert.ok(at >= spec.speak_floor - 0.001, `env=${at.toFixed(3)} is below the floor`);
});

check("a listening face falls to nothing, and invents no level", () => {
  V.stopVoice();
  V.setVoiceMode("listening");
  // Listening deliberately has no fallback: a synthetic microphone level would
  // claim Jarvis can hear the room when nothing is being captured.
  const at = run(0.6, 0, V.setLevel);
  assert.ok(at < 0.01, `env=${at.toFixed(3)}, wanted silence`);
});

check("the microphone releases more slowly than the voice", () => {
  V.stopVoice();
  V.setVoiceMode("listening");
  run(0.4, 1, V.setLevel);
  const loud = V.voiceLevel();
  const quiet = run(0.12, 0.0, V.setLevel);
  // 120ms is one full speech release but only half a microphone one, so the
  // mic must still be visibly up where the voice would be most of the way down.
  assert.ok(quiet > loud * 0.5, `mic fell to ${quiet.toFixed(3)} from ${loud.toFixed(3)} in 120ms`);
});

check("the fallback rests for 220ms every 2.3s", () => {
  const rest = spec.speak_floor;
  // Sample the whole cycle at 1ms and find where it sits flat on the floor.
  let resting = 0;
  for (let ms = 0; ms < 2300; ms += 1) {
    if (Math.abs(V.synth(ms / 1000) - rest) < 1e-9) resting += 1;
  }
  assert.ok(Math.abs(resting - 220) <= 2, `rested ${resting}ms in a 2.3s cycle, wanted 220`);
});

check("the fallback is never below the floor and never above one", () => {
  for (let ms = 0; ms < 9200; ms += 1) {
    const v = V.synth(ms / 1000);
    assert.ok(v >= spec.speak_floor - 1e-9 && v <= 1 + 1e-9, `synth(${ms}ms) = ${v}`);
  }
});

check("the fallback actually reaches a loud syllable", () => {
  let peak = 0;
  for (let ms = 0; ms < 9200; ms += 1) peak = Math.max(peak, V.synth(ms / 1000));
  assert.ok(peak > 0.9, `the loudest synthetic syllable was ${peak.toFixed(3)}`);
});

/* ── 3. Control: the wiring exists ───────────────────────────────────────── */

check("CONTROL: the reactor consumes the envelope", () => {
  const css = readFileSync(join(SRC, "style.css"), "utf8");
  assert.match(css, /--voice-scale/, "nothing scales with the voice");
  assert.match(css, /--voice-lift/, "nothing brightens with the voice");
});

check("CONTROL: something sets the mode from the link", () => {
  const main = readFileSync(join(SRC, "main.js"), "utf8");
  assert.match(main, /setVoiceMode\(faceState\(link\)\)/,
    "the envelope is never told what Jarvis is doing");
  assert.match(main, /startVoice\(/, "the envelope is never started");
});

check("CONTROL: reduced motion silences the push", () => {
  assert.match(source, /prefers-reduced-motion/, "voice.js ignores reduced motion");
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nall voice checks passed");
process.exit(fails.length ? 1 : 0);
