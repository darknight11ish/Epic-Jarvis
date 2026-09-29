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
import { WORDS, pcLine, readHandoff, reasonWords } from "../src/handoff.js";
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

check("nothing waiting, or another pause: no alert", () => {
  assert.equal(readHandoff(CASES.offer_none), null);
  assert.equal(readHandoff(CASES.offer_other_pause), null);
  assert.equal(readHandoff(CASES.offer_after_resume), null);
  assert.equal(readHandoff(undefined), null, "an older PC sends none");
});

check("a chatbot at a captcha: the PC's own alert, on that session only", () => {
  const h = readHandoff(CASES.offer_captcha);
  assert.deepEqual(h, { kind: "chatbot", id: "chat_000000000001", reason: "captcha",
    site: "Gemini", active: "" });
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
  const hits = files.filter((f) => /\/api\/chatbot\/handoff/.test(read(f)));
  assert.deepEqual(hits, [], `the desktop names the hand-off routes in ${hits.join(", ")}`);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nall passed");
