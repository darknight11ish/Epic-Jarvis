/**
 * Settings -> Voice: what the PC says about listening to the owner.
 *
 * Every status here is REAL: `K.VOICE.cases` is
 * tests/fixtures/voice-status-cases.json, jarvis_speech.status() in named
 * cases, written by tools/gen_voice_status_cases.py (and checked fresh by
 * backend/test_voice_contract.py). Nothing is hand-made.
 *
 * What must hold (the phone's Platform checks -> "Your voice" and wake-word
 * cards are the model, VoiceTraining.kt and ReadinessScreen.kt):
 * - each microphone's voice print is shown, trained or not, and an untrained
 *   PC microphone is said to use the phone's print;
 * - which voice check is installed, in the phone's words for the basic one;
 * - the owner's own "hey Jarvis" check, the wake word, "stop", Smart Turn and
 *   the talk button, each in words;
 * - training is NOT offered here; the page says it is on the phone;
 * - an older backend, or no answer, is a sentence - never a code or JSON.
 *
 * The CONTROL checks read the Rust: the header and token, and that only the
 * settings window may call the command.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import * as W from "../src/voice-settings.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const C = K.VOICE.cases;
const WHERE = "in the Jarvis bar, on the widget, or on your phone's Home screen";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1400 };
const open = (voice) => K.open(browser, base, "settings.html", { voice }, VIEW);

/** Everything the section shows, read off the page. */
const section = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const shown = (id) => ($(id) && !$(id).hidden ? $(id).innerText : null);
  return {
    stateHidden: $("voice-state").hidden,
    state: $("voice-state").innerText,
    bodyHidden: $("voice-body").hidden,
    summary: shown("voice-summary"),
    summaryTone: $("voice-summary").dataset.tone || "",
    prints: [...document.querySelectorAll("#voice-prints li")].map((li) => ({
      mic: li.dataset.mic, tone: li.dataset.tone || "", text: li.innerText,
    })),
    check: shown("voice-check"),
    last: shown("voice-last"),
    talk: shown("voice-talk"),
    wake: shown("voice-wake"),
    wakeState: $("voice").dataset.wake || "",
    verifier: shown("voice-verifier"),
    stopWord: shown("voice-stop-word"),
    turn: shown("voice-turn"),
    buttons: [...$("voice").querySelectorAll("button")].map((b) => b.innerText),
    all: $("voice").innerText,
    reads: window.__voice.reads,
  };
});
const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|null|undefined|\[object|NaN/,
    `raw data on the page: ${text}`);
};
const print = (s, mic) => s.prints.find((p) => p.mic === mic);

/* ── The words, against every real status ───────────────────────────────── */

await check("every real status reads as sentences, with no raw data", async () => {
  for (const [name, status] of Object.entries(C)) {
    const lines = [
      W.summaryLine(status, WHERE),
      ...W.printLines(status).map((l) => `${l.name}: ${l.text}`),
      W.checkLine(status)?.text, W.talkLine(status).text, W.wakeInfo(status, WHERE).text,
      W.verifierLine(status)?.text, W.stopWordLine(status)?.text, W.turnLine(status)?.text,
      W.lastTrainingLine(status.gate.training.last),
    ].filter(Boolean);
    for (const line of lines) {
      noRaw(line);
      assert.match(line, /[.!?)]$/, `${name}: "${line}" is not a sentence`);
    }
  }
});

await check("not trained: every print says so, and the talk button's reason is the PC's own", async () => {
  const st = C.not_trained;
  assert.equal(W.summaryLine(st, WHERE), "Not trained yet. Until it is, Jarvis will not act on anyone's voice.");
  const prints = W.printLines(st);
  assert.deepEqual(prints.map((p) => p.id), ["phone", "desktop"], "the older print is shown although untrained");
  assert.equal(prints[0].text, "not trained yet.");
  assert.equal(prints[1].text, "not trained yet.");
  assert.equal(W.talkLine(st).text,
    `Talk button (hold to talk): not ready yet. ${st.listening.push_to_talk_why}`);
  // The phone's basicCheckLine, word for word.
  assert.equal(W.checkLine(st).text,
    "Using the basic voice check, which cannot reliably tell two people apart. Install the better one on your PC for more reliable results.");
});

await check("trained on the phone: the PC's microphone uses the phone's print until it is trained", async () => {
  const st = C.phone_trained;
  assert.equal(W.summaryLine(st, WHERE), "Trained on your phone, from 3 samples.");
  const [phone, pc] = W.printLines(st);
  assert.equal(phone.text, "trained, from 3 samples.");
  assert.equal(phone.tone, "ok");
  assert.equal(pc.text, "not trained on its own. It uses your phone's voice print until it is.");
});

await check("both microphones trained, everything installed, wake word on", async () => {
  const st = C.ready_wake_on;
  const [, pc] = W.printLines(st);
  assert.equal(pc.text, "trained, from 4 samples.");
  assert.equal(W.talkLine(st).text, "Talk button (hold to talk): ready.");
  assert.equal(W.wakeInfo(st, WHERE).state, "on");
  assert.match(W.wakeInfo(st, WHERE).text, /^On\. Your PC takes "hey Jarvis"\./);
  assert.doesNotMatch(W.wakeInfo(st, WHERE).text, /cannot hear/);
  assert.match(W.verifierLine(st).text, /built from your training/);
  assert.match(W.stopWordLine(st).text, /this PC can hear it/);
  assert.match(W.turnLine(st).text, /: on\./);
});

await check("the older single print is shown, and said to be replaced by the next training", async () => {
  const lines = W.printLines(C.older_single_print);
  assert.deepEqual(lines.map((l) => l.id), ["phone", "desktop", "general"]);
  assert.match(lines[2].text, /^trained, from 4 samples\. It is used for any microphone without its own/);
  assert.equal(lines[1].text, "not trained on its own. It uses your phone's voice print until it is.");
  assert.equal(W.summaryLine(C.older_single_print, WHERE), "Trained, from 4 samples.");
});

await check("a print made with another voice check: train again, on the phone", async () => {
  const st = C.needs_retraining;
  assert.equal(W.summaryLine(st, WHERE),
    "Your PC's voice check changed since you trained it. Train your voice again on your phone.");
  assert.equal(W.isTrained(st), false);
  const general = W.printLines(st).find((l) => l.id === "general");
  assert.match(general.text, /needs training again/);
  assert.equal(general.tone, "warn");
});

await check("a training approved on its card: how it ended, with the PC's reason for the \"hey Jarvis\" check", async () => {
  const last = C.trained_by_card.gate.training.last;
  assert.equal(W.lastTrainingLine(last),
    "Last training was approved: 3 samples saved. Its \"hey Jarvis\" check was not built " +
    "(the wake-word model files are not on disk yet (looked in ~/.openjarvis/voice-models/wakeword)).");
  // The phone's other outcomes, word for word.
  assert.equal(W.lastTrainingLine({ outcome: "denied" }), "Last training was denied on the card. Nothing changed.");
  assert.equal(W.lastTrainingLine({ outcome: "timed_out" }),
    "Nobody answered the last training card in time. Nothing changed.");
  assert.equal(W.lastTrainingLine({ outcome: "failed", reason: "disk full." }), "The last training failed: disk full.");
  assert.equal(W.lastTrainingLine(undefined), null);
});

await check("a card to turn the wake word on is waiting: said, with where to approve it", async () => {
  const w = W.wakeInfo(C.wake_waiting, WHERE);
  assert.equal(w.state, "waiting");
  assert.equal(w.text, `A card to turn it on is waiting. Approve it ${WHERE}. Nothing listens until you do.`);
  assert.equal(W.wakeInfo(C.wake_off_after_waiting, WHERE).state, "off");
});

/* ── The page ───────────────────────────────────────────────────────────── */

await check("the section shows the real status, with training pointed at the phone and no training button", async () => {
  const page = await open({ status: C.phone_trained });
  const s = await section(page);
  await page.close();
  assert.equal(s.stateHidden, true);
  assert.equal(s.bodyHidden, false);
  assert.equal(s.summary, "Trained on your phone, from 3 samples.");
  assert.equal(s.summaryTone, "ok");
  assert.match(print(s, "phone").text, /Your phone's microphone\s+Trained, from 3 samples\./);
  assert.match(print(s, "desktop").text, /This PC's microphone\s+Not trained on its own\. It uses your phone's voice print until it is\./);
  assert.match(s.check, /basic voice check/);
  // With only the basic voice check, the stricter check (2026-09-24) refuses
  // every voice, and that is the first reason the PC gives.
  assert.match(s.talk, /not ready yet\. The PC has no voice-ID model installed/);
  assert.equal(s.wakeState, "off");
  assert.match(s.wake, /^Off\. Nothing can wake Jarvis by speaking a phrase/);
  assert.match(s.verifier, /not built\. Not trained yet/);
  assert.match(s.stopWord, /cannot hear it yet/);
  assert.match(s.turn, /not installed on this PC/);
  assert.equal(s.last, null);
  assert.match(s.all, /use your phone for now: open Platform checks and tap Train my voice/);
  assert.ok(!s.buttons.some((b) => /train/i.test(b)), `a training button: ${s.buttons}`);
  noRaw(s.all);
});

await check("everything ready: the PC's own print, the \"hey Jarvis\" check, stop and Smart Turn", async () => {
  const page = await open({ status: C.ready_wake_on });
  const s = await section(page);
  await page.close();
  assert.match(print(s, "desktop").text, /Trained, from 4 samples\./);
  assert.equal(print(s, "desktop").tone, "ok");
  assert.equal(s.wakeState, "on");
  assert.match(s.talk, /ready\.$/);
  assert.match(s.verifier, /built from your training/);
  assert.match(s.stopWord, /this PC can hear it/);
  assert.match(s.turn, /on\. Jarvis waits until you have finished/);
  noRaw(s.all);
});

await check("a training that ended is said, and a waiting wake-word card is said with where to approve it", async () => {
  const page = await open({ status: C.trained_by_card });
  const s = await section(page);
  await page.close();
  assert.match(s.last, /^Last training was approved: 3 samples saved\./);
  const wait = await open({ status: C.wake_waiting });
  const w = await section(wait);
  await wait.close();
  assert.equal(w.wakeState, "waiting");
  assert.match(w.wake, /A card to turn it on is waiting\. Approve it in the Jarvis bar, on the widget, or on your phone's Home screen\./);
});

await check("an older backend, or no answer, is a sentence and nothing else", async () => {
  const old = await open({ unavailable: true });
  const s = await section(old);
  await old.close();
  assert.equal(s.bodyHidden, true);
  assert.equal(s.stateHidden, false);
  assert.match(s.state, /does not report its voice settings yet\. Update the backend by running apply-patches\.ps1/);
  const down = await open({ getFails: "Jarvis is not answering at http://127.0.0.1:4719. Is it running?" });
  const d = await section(down);
  await down.close();
  assert.equal(d.bodyHidden, true);
  assert.match(d.state, /^Jarvis could not be asked about voice\. Jarvis is not answering at/);
  noRaw(s.state);
});

await check("while a wake-word card waits, the page re-reads when the approval queue changes", async () => {
  const page = await open({ status: C.wake_waiting });
  const first = await page.evaluate(() => window.__voice.reads);
  await page.evaluate(() => window.__emit("approvals-changed", { approvals: [] }));
  await page.waitForTimeout(200);
  const later = await page.evaluate(() => window.__voice.reads);
  await page.close();
  assert.ok(later > first, "no re-read when the queue changed");
});

/* ── The Rust ───────────────────────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL (Rust): get_voice_status sends X-Jarvis-Client: hud and the token the usual way, and logs nothing", async () => {
  const commands = read("src-tauri/src/commands.rs");
  assert.match(commands, /const JARVIS_CLIENT: &str = "hud";/);
  const rust = read("src-tauri/src/voice.rs");
  const body = fnBody(rust, "pub async fn get_voice_status(");
  assert.match(body, /\.headers\(jarvis_headers\(&app\)\?\)/);
  assert.match(body, /let base = jarvis_base\(&app\);/);
  assert.match(body, /format!\("\{base\}\/api\/voice\/status"\)/);
  assert.match(body, /\.get\(/);
  assert.doesNotMatch(body, /println!|eprintln!|log::|tracing::|dbg!|logfile/);
  assert.doesNotMatch(body, /token/i);
});

await check("CONTROL: only the settings window may read the voice status", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  const holders = sets.filter((s) => s.includes('"allow-get-voice-status"'))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders, ["settings-surface"], `allow-get-voice-status is held by ${holders}`);
  assert.ok(read("src-tauri/build.rs").includes('"get_voice_status"'), "not in build.rs");
  assert.ok(read("src-tauri/src/lib.rs").includes("voice::get_voice_status,"), "not registered");
  assert.match(read("src-tauri/permissions/autogenerated/get_voice_status.toml"),
    /commands.allow = \["get_voice_status"\]/);
});

await check("CONTROL: no page error from any of the above", async () => {
  const page = await open({ status: C.ready_wake_on });
  await page.waitForTimeout(200);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, []);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nSettings -> Voice holds");
process.exit(fails.length ? 1 : 0);
