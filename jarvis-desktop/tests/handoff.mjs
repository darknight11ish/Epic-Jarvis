/**
 * "Solve it here" on the desktop (the owner's decision of 2026-09-28;
 * JARVIS-API.md section 87.8; src/handoff.js; backend/jarvis_handoff.py).
 *
 * What must hold:
 * - the words are the PC's (jarvis_handoff.WORDS) and the phone's, word for
 *   word (fixtures/handoff-cases.json, written by tools/gen_handoff_cases.py
 *   from the real routes);
 * - every real `handoff` answer reads: nothing waiting, a chatbot at a
 *   captcha, a support chat at a sign-in page, one being handed on now;
 * - the Brain's Work tab shows the PC's alert on the paused session only,
 *   pointing at the window on this PC;
 * - the desktop NEVER calls the picture or input routes: it has the real
 *   window, and the hand-off is the phone's (ARCHITECTURE.md section 8).
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { WORDS, STUCK, pcLine, readHandoff, reasonWords, stuckLine, stuckPcLine } from "../src/handoff.js";
import {
  DEFAULT_MODE,
  HANDOFF_MODE,
  HANDOFF_MODE_WORDS,
  MODE_PATH,
  MODES,
  isLoosening,
  modeBody,
  modeView,
} from "../src/handoff-mode-rules.js";
import { readChatbot } from "../src/chatbot.js";
import { readSupport } from "../src/support.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/handoff-cases.json"));
const CHATBOT = JSON.parse(read("tests/fixtures/chatbot-cases.json"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

check("the words are the PC's, word for word", () => {
  assert.deepEqual(WORDS, CASES.words);
});

check("the PC's own 'stuck' line is here, word for word", () => {
  assert.deepEqual(STUCK, CASES.stuck_words);
  assert.deepEqual(stuckLine("Gemini", "captcha"), {
    title: "Gemini is waiting on this PC",
    text: CASES.stuck_words.text.replace("{reason}", CASES.words.reason_captcha),
  });
  assert.match(stuckLine("Groupon", "login").text, /a sign-in page/);
  assert.match(stuckLine("Groupon", "login").title, /Groupon/);
});

check("the setting's two values, its default and every word are the PC's", () => {
  assert.deepEqual(MODES, CASES.modes);
  assert.equal(DEFAULT_MODE, CASES.mode_default);
  assert.equal(DEFAULT_MODE, "stop_early", "the default is the quick cut-off");
  assert.equal(CASES.mode_patient, "keep_offering");
  assert.deepEqual(HANDOFF_MODE_WORDS, CASES.mode_words);
  const v = modeView(CASES.mode_route_get.body);
  assert.equal(v.mode, "stop_early");
  assert.equal(v.line, CASES.mode_words.stop_early_detail);
  assert.equal(v.idleSeconds, 60);
  assert.equal(v.ceilingSeconds, 900);
});

check("the setting's route, and the GET it carries", () => {
  assert.equal(CASES.routes.mode, MODE_PATH);
  assert.equal(MODE_PATH, "/api/chatbot/handoff_mode");
  // Deliberately NOT one of the hand-off's own routes: this app names none of
  // those, and the CONTROL check at the bottom keeps it that way.
  assert.ok(!MODE_PATH.startsWith("/api/chatbot/handoff/"));
});

check("a damaged file reads as 'Stop early', in the PC's words", () => {
  const v = modeView({ ...CASES.mode_route_get.body, why: CASES.mode_words.damaged });
  assert.equal(v.mode, "stop_early");
  assert.equal(v.line, CASES.mode_words.damaged);
  assert.equal(modeView(undefined).mode, DEFAULT_MODE);
  assert.equal(modeView({ mode: "forever" }).available, false);
  assert.equal(modeView({}).line, HANDOFF_MODE.unread);
});

check("the body carries one of the two names and nothing else", () => {
  assert.deepEqual(JSON.parse(modeBody("stop_early")), { mode: "stop_early" });
  assert.deepEqual(JSON.parse(modeBody("keep_offering")), { mode: "keep_offering" });
  for (const bad of ["", "on", "off", "patient", "stop", null, 1]) {
    assert.equal(modeBody(bad), null, `${bad}`);
  }
});

check("choosing 'Keep offering it' is the loosening one", () => {
  assert.equal(isLoosening("keep_offering"), true);
  assert.equal(isLoosening("stop_early"), false);
});

check("nothing waiting, or another pause: no alert", () => {
  assert.equal(readHandoff(CASES.offer_none), null);
  assert.equal(readHandoff(CASES.offer_other_pause), null);
  assert.equal(readHandoff(CASES.offer_after_resume), null);
  assert.equal(readHandoff(undefined), null, "an older PC sends none");
});

check("a chatbot at a captcha: the PC's own alert, on that session only", () => {
  const h = readHandoff(CASES.offer_captcha);
  assert.deepEqual(h, { kind: "chatbot", id: "chat_000000000001", reason: "captcha",
    site: "Gemini", active: "", stuck: null });
  const line = pcLine(h, "chatbot", "chat_000000000001");
  assert.equal(line.title, "Gemini needs you on this PC");
  assert.match(line.text, /captcha/);
  assert.match(line.text, /browser window/);
  assert.match(line.text, /Resume/);
  assert.equal(pcLine(h, "chatbot", "chat_000000000002"), null);
  assert.equal(pcLine(h, "support", "chat_000000000001"), null);
  assert.equal(readHandoff(CASES.offer_active).active, "ho_0000000000000001");
});

check("a support chat at a sign-in page", () => {
  const h = readHandoff(CASES.offer_support);
  assert.equal(h.kind, "support");
  assert.equal(pcLine(h, "support", "sup_000000000001").title, "Groupon needs you on this PC");
  assert.equal(reasonWords("login"), "a sign-in page");
});

check("readChatbot and readSupport carry it (the real status answer)", () => {
  const body = { ...CHATBOT.running, handoff: CASES.offer_captcha };
  const v = readChatbot(body);
  assert.equal(v.handoff.site, "Gemini");
  assert.equal(readChatbot(CHATBOT.running).handoff, null);
  const s = readSupport({ ...CHATBOT.running, handoff: CASES.offer_support });
  if (s.available) assert.equal(s.handoff.kind, "support");
});

check("the Brain shows it on a PAUSED session, as a status, pointing at the window", () => {
  const brain = read("src/brain.js");
  assert.match(brain, /s\.state === "paused" \? handoffPcLine\(v\.handoff, "chatbot", s\.id\)/);
  assert.match(brain, /c\.state === "paused" \? handoffPcLine\(v\.handoff, "support", c\.id\)/);
  const fn = brain.slice(brain.indexOf("function handoffAlert("));
  assert.match(fn.slice(0, 400), /setAttribute\("role", "status"\)/);
});

check("under the default, the PC says which window Jarvis is stuck on", () => {
  // The real "Stop early" answer: offer_captcha is still available (the page is
  // still paused) and mode_idle_offer carries the PC's own stuck line.
  const h = readHandoff(CASES.mode_idle_offer);
  assert.ok(h && h.stuck, "the stuck line is read");
  assert.deepEqual(h.stuck, CASES.mode_idle_offer.stuck);
  const line = stuckPcLine(h, "chatbot", CASES.mode_idle_offer.id);
  assert.equal(line.title, CASES.stuck_words.title.replace("{site}", "Gemini"));
  assert.match(line.text, /stuck on/);
  assert.match(line.text, /browser window on this PC/);
  assert.equal(stuckPcLine(h, "chatbot", "chat_000000000002"), null);
  assert.equal(stuckPcLine(h, "support", CASES.mode_idle_offer.id), null);
  // Nothing stuck: no line at all (the offer that ended some other way).
  assert.equal(readHandoff(CASES.offer_captcha).stuck, null);
  assert.equal(stuckPcLine(readHandoff(CASES.offer_captcha), "chatbot",
    CASES.offer_captcha.id), null);
  // ... and the Brain really draws it, on both sessions.
  const brain = read("src/brain.js");
  assert.match(brain, /s\.state === "paused" \? stuckPcLine\(v\.handoff, "chatbot", s\.id\)/);
  assert.match(brain, /c\.state === "paused" \? stuckPcLine\(v\.handoff, "support", c\.id\)/);
  assert.match(brain, /handoffAlert\(stuckHere, "stuck"\)/);
});

check("CONTROL: the desktop never asks for a picture or passes input", () => {
  const files = [];
  const walk = (dir) => {
    for (const e of readdirSync(join(ROOT, dir), { withFileTypes: true })) {
      if (e.isDirectory()) walk(join(dir, e.name));
      else if (/\.(js|mjs|html|rs)$/.test(e.name)) files.push(join(dir, e.name));
    }
  };
  walk("src");
  walk("src-tauri/src");
  // The hand-off's OWN routes - /start, /frame, /input, /end - exactly. The
  // setting added on 2026-10-08 is `/api/chatbot/handoff_mode`, a SIBLING that
  // carries one word and is deliberately not under `/handoff/`; naming it is
  // how the desktop offers the owner the choice at all, so the pattern is
  // anchored to `/handoff/` with a route name after it.
  const own = /\/api\/chatbot\/handoff\/(?:start|frame|input|end)\b/;
  const hits = files.filter((f) => own.test(read(f)));
  assert.deepEqual(hits, [], `the desktop names the hand-off's own routes in ${hits.join(", ")}`);
  // ... and the setting's own route is named, so the control above is not
  // passing by accident (the choice really is on this app's Settings page).
  const setting = files.filter((f) => read(f).includes(MODE_PATH));
  assert.ok(setting.length > 0, "the setting's own route is named somewhere");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall passed");
