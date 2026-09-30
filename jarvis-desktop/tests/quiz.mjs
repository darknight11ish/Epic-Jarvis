/**
 * Quiz me on a text on the Brain's Work tab (the owner's "go ahead",
 * 2026-09-30; docs/STUDY-FROM-TEXT-DESIGN.md section 11; JARVIS-API.md
 * section 98; src/quiz.js, brain.js paintQuiz, src-tauri/src/brain/quiz.rs).
 *
 * What must hold:
 * - the section says what it is in the shared words (title, intro, outside
 *   text line, buttons), word for word;
 * - a paste box with a live count; under 200 or over 20,000 characters is
 *   refused with a plain sentence and nothing is sent;
 * - Write questions sends the text once (brain_quiz_start), then the box is
 *   emptied - the text is not kept in this window;
 * - one question at a time with an answer box (1-2000); Check my answer sends
 *   ONE answer for that question; the mark reads Got it / Partly / Not yet
 *   with the comment and the source passage, and "Jarvis's guess" while the
 *   grader is not verified (and not once it is);
 * - a progress line; Finish shows "Look at these again" with the question
 *   numbers (or "Nothing to look at again."); Stop and forget this quiz
 *   forgets it;
 * - every error code has a plain sentence;
 * - every change is held on a stale link (greyed here, refused in Rust);
 * - nothing is stored in localStorage or sessionStorage - no text, answers,
 *   marks or draft;
 * - with the private lists hidden the questions, comments and passages are
 *   not shown (Rust takes them out) and "Show" brings them back;
 * - CONTROL: the Rust/JS/permissions wiring agrees, on the Brain window only.
 *
 * Needs Playwright (see tests/README.md); unexecuted where it is unavailable.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  AGAIN_EMPTY,
  AGAIN_HEADING,
  ANSWER_LABEL,
  againLine,
  answerCount,
  CLOSE_LABEL,
  HIDDEN_WORDS,
  KIND_LABELS,
  countsLine,
  crisisParagraphs,
  isCrisis,
  readCrisis,
  ERROR_WORDS,
  errorWords,
  FINISH_LABEL,
  GUESS_LABEL,
  LEVEL_LABELS,
  nextQuestion,
  OUTSIDE_LINE,
  progressLine,
  QUIZ_INTRO,
  QUIZ_TITLE,
  readMark,
  readQuiz,
  readSummary,
  START_LABEL,
  STOP_LABEL,
  textCount,
} from "../src/quiz.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const PASTE = "Bread is made from flour, water, salt and yeast. ".repeat(6);

/* ── The words and the pure reading ───────────────────────────────────── */

await check("the shared words, word for word, in the page", async () => {
  assert.equal(QUIZ_TITLE, "Quiz me on a text");
  assert.equal(START_LABEL, "Write questions");
  assert.equal(ANSWER_LABEL, "Check my answer");
  assert.equal(FINISH_LABEL, "Finish");
  assert.equal(STOP_LABEL, "Stop and forget this quiz");
  assert.equal(AGAIN_HEADING, "Look at these again");
  assert.equal(AGAIN_EMPTY, "Nothing to look at again.");
  assert.equal(GUESS_LABEL, "Jarvis's guess");
  assert.deepEqual(LEVEL_LABELS, { got_it: "Got it", partly: "Partly", not_yet: "Not yet" });
  assert.equal(QUIZ_INTRO,
    "Paste some text and Jarvis writes a few questions about it. Your answers are marked by the model on this PC. Nothing is saved or learned, and nothing leaves this PC.");
  assert.equal(OUTSIDE_LINE,
    "This text is treated as outside text: Jarvis never learns facts from it.");
  const html = read("src/brain.html");
  assert.match(html, /<h2>Quiz me on a text<\/h2>/);
  assert.ok(html.includes(`>${QUIZ_INTRO}</p>`));
  assert.ok(html.includes(`>${OUTSIDE_LINE}</p>`));
  assert.match(html, />Write questions<\/button>/);
});

await check("every error code of the contract has a plain sentence", async () => {
  const codes = ["text_too_short", "text_too_long", "bad_count", "too_many_quizzes", "not_found",
    "bad_question", "already_answered", "answer_empty", "answer_too_long", "model_unavailable"];
  for (const c of codes) {
    assert.ok(ERROR_WORDS[c] && ERROR_WORDS[c].length > 10, c);
    assert.doesNotMatch(ERROR_WORDS[c], /_|\{|\}|error|HTTP/i, `${c} is not plain words`);
    assert.equal(errorWords({ ok: false, error: c, message: "x" }), ERROR_WORDS[c]);
  }
  assert.match(ERROR_WORDS.model_unavailable, /Nothing was lost/);
  assert.equal(errorWords({ ok: false, error: "brand_new", message: "The PC says so." }), "The PC says so.");
  assert.match(errorWords(null), /could not/);
});

await check("reading the PC's quiz: questions, marks, the guess flag and a summary", async () => {
  const q = readQuiz({ id: "q1", title: "T", grader_verified: false, answered: 1, questions: [
    { n: 1, kind: "recall", prompt: "A?", mark: { level: "partly", comment: "c", passage: "p" } },
    { n: 2, kind: "weird", prompt: "B?", mark: null },
    { n: "x", prompt: "dropped" }] });
  assert.equal(q.questions.length, 2, "a question without a number was kept");
  assert.equal(q.verified, false);
  assert.equal(q.questions[1].kind, "recall", "an unknown kind falls back");
  // An older PC sends no marked_by / expected / key_label: its marks are the model's.
  assert.deepEqual(q.questions[0].mark, { level: "partly", comment: "c", passage: "p",
    markedBy: "model", expected: null, keyLabel: null });
  assert.equal(q.mode, "", "no mode means an older PC (JARVIS-API 102.4)");
  assert.equal(q.level, null);
  assert.equal(q.notice, "");
  assert.equal(nextQuestion(q).n, 2);
  assert.equal(progressLine(q), "Question 2 of 2 · 1 answered");
  assert.equal(readMark({ level: "A+" }), null, "a letter grade was accepted");
  assert.equal(readQuiz({}), null);
  assert.equal(readQuiz(null), null);
  assert.equal(readQuiz({ id: "q", grader_verified: true, questions: [] }).verified, true);
  const s = readSummary({ counts: { got_it: 1, partly: 2, not_yet: 3 }, again: [2, 3, "x", 0] });
  assert.deepEqual(s.again, [2, 3]);
  assert.equal(countsLine(s), "1 Got it · 2 Partly · 3 Not yet");
  assert.doesNotMatch(countsLine(s), /%|streak|score/i);
});

await check("the limits: 200-20000 for the text, 1-2000 for an answer", async () => {
  assert.equal(textCount("x".repeat(199)).ok, false);
  assert.equal(textCount("x".repeat(200)).ok, true);
  assert.equal(textCount("x".repeat(20000)).ok, true);
  assert.equal(textCount("x".repeat(20001)).ok, false);
  // the PC checks the TRIMMED length, so the count and the verdict do too
  assert.equal(textCount(" ".repeat(250)).ok, false, "250 spaces were accepted");
  assert.equal(textCount(" ".repeat(250)).n, 0);
  assert.equal(textCount("  " + "x".repeat(199) + "  ").ok, false);
  assert.equal(textCount("  " + "x".repeat(200) + "  ").ok, true);
  assert.equal(textCount("").note, "0 / 20,000 characters · at least 200 needed");
  assert.match(textCount("x".repeat(20001)).note, /too long/);
  assert.equal(answerCount("").ok, false);
  assert.equal(answerCount("   ").ok, false);
  assert.equal(answerCount("a").ok, true);
  assert.equal(answerCount("a".repeat(2001)).ok, false);
});

await check("the words both apps share beyond the first list", async () => {
  assert.deepEqual(KIND_LABELS, { recall: "Remember", explain: "Explain why", apply: "Apply",
    translate: "Translate", blank: "Fill the blank", complete: "Finish the sentence" });
  assert.equal(CLOSE_LABEL, "Close");
  assert.equal(HIDDEN_WORDS, "(hidden)");
  const q = { questions: [{ n: 1, prompt: "Why?" }, { n: 3, prompt: "" }] };
  assert.equal(againLine(1, q), "1. Why?");
  assert.equal(againLine(3, q), "3. (hidden)");
  assert.equal(againLine(2, q), "2. (hidden)");
  assert.equal(againLine(2, null), "2. (hidden)");
  assert.equal(countsLine({ counts: { got_it: 2, partly: 1, not_yet: 0 } }), "2 Got it · 1 Partly · 0 Not yet");
  assert.equal(progressLine({ questions: [{ n: 1, mark: {} }, { n: 2, mark: null }] }), "Question 2 of 2 · 1 answered");
});

await check("a crisis answer is read from the PC's words, never written here", async () => {
  assert.equal(readCrisis({ ok: true, crisis: true, message: "  Help words.  " }), "Help words.");
  assert.equal(readCrisis({ ok: true, mark: { level: "got_it" } }), "");
  assert.equal(readCrisis({ ok: true, crisis: false, message: "x" }), "");
  assert.equal(readCrisis(null), "");
  assert.equal(isCrisis({ crisis: true }), true);
  assert.equal(isCrisis({ ok: true }), false);
  assert.deepEqual(crisisParagraphs("A **988** b.\n\nSecond."),
    [[{ text: "A ", bold: false }, { text: "988", bold: true }, { text: " b.", bold: false }],
     [{ text: "Second.", bold: false }]]);
  const src = read("src/quiz.js") + read("src/brain.js");
  assert.doesNotMatch(src, /Suicide|Crisis Lifeline|call 911/i, "help words are hard-coded in the app");
});

/* ── The Brain window ─────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

async function workTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(400);
  return page;
}
const calls = (page) => page.evaluate(() => window.__quiz.calls);
const start = async (page, text = PASTE) => {
  await page.locator("#quiz-text").fill(text);
  await page.locator("#quiz-start").click();
  await page.waitForTimeout(400);
};

await check("the section shows its words and a live count under the paste box", async () => {
  const page = await workTab({ quiz: {} });
  const card = page.locator("#quiz-card");
  const title = (await card.locator("h2").textContent()).trim();
  const notes = await card.locator(".note").allInnerTexts();
  const before = (await page.locator("#quiz-text-count").innerText()).trim();
  await page.locator("#quiz-text").fill("x".repeat(250));
  const after = (await page.locator("#quiz-text-count").innerText()).trim();
  await page.close();
  assert.equal(title, QUIZ_TITLE);
  assert.ok(notes.includes(QUIZ_INTRO));
  assert.ok(notes.includes(OUTSIDE_LINE));
  assert.match(before, /^0 \/ 20,000 characters/);
  assert.match(before, /at least 200/);
  assert.equal(after, "250 / 20,000 characters");
});

await check("a text that is too short is refused in plain words and nothing is sent", async () => {
  const page = await workTab({ quiz: {} });
  await start(page, "too short");
  const text = await page.locator("#quiz-run").innerText();
  const sent = await calls(page);
  await page.close();
  assert.match(text, /too short/);
  assert.deepEqual(sent, []);
});

await check("Write questions sends the text once, then empties the box", async () => {
  const page = await workTab({ quiz: {} });
  await start(page);
  const sent = await calls(page);
  const left = await page.locator("#quiz-text").inputValue();
  const text = await page.locator("#quiz-run").innerText();
  const formHidden = await page.locator("#quiz-start-form").isHidden();
  await page.close();
  assert.deepEqual(sent, [{ cmd: "brain_quiz_start", text: PASTE }]);
  assert.equal(left, "", "the pasted text stayed in the box");
  assert.match(text, /Question 1 of 3 · 0 answered/);
  assert.match(text, /Question text number 1\?/);
  assert.equal(formHidden, true);
});

await check("one question at a time: Check my answer sends ONE answer, then the mark, comment and passage", async () => {
  const page = await workTab({ quiz: { levels: ["partly"] } });
  await start(page);
  await page.locator("#quiz-run textarea").fill("Flour and water.");
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(400);
  const sent = (await calls(page)).filter((c) => c.cmd === "brain_quiz_answer");
  const text = await page.locator("#quiz-run").innerText();
  await page.close();
  assert.deepEqual(sent, [{ cmd: "brain_quiz_answer", id: "qz0001", n: 1, answer: "Flour and water." }]);
  assert.match(text, /Partly/);
  assert.match(text, /The passage says otherwise\./);
  assert.match(text, /SOURCE PASSAGE 1/);
  assert.match(text, new RegExp(GUESS_LABEL), "Jarvis's guess is missing while the grader is not verified");
  assert.doesNotMatch(text, /\d+ ?%|streak|score/i);
});

await check("a crisis answer shows the PC's words calmly, no mark, keeps the question open, keeps no text", async () => {
  const page = await workTab({ quiz: { crisisWord: "HELPME" } });
  await start(page);
  const box = page.locator("#quiz-run textarea");
  await box.fill("HELPME I feel awful");
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(400);
  const text = await page.locator("#quiz-run").innerText();
  const bold = await page.locator("#quiz-run .quiz-crisis strong").allInnerTexts();
  const left = await page.locator("#quiz-run textarea").inputValue();
  const stillQ1 = /Question 1 of 3 · 0 answered/.test(text);
  const html = await page.locator("#quiz-run").innerHTML();
  // the same question can be answered afterwards and is marked normally
  await page.locator("#quiz-run textarea").fill("Flour.");
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(400);
  const after = await page.locator("#quiz-run").innerText();
  const storage = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]));
  await page.close();
  assert.match(text, /STAND-IN HELP WORDS\./);
  assert.deepEqual(bold, ["988"]);
  assert.doesNotMatch(text, /Not yet|Got it|Partly/);
  assert.doesNotMatch(text, new RegExp(GUESS_LABEL));
  assert.ok(stillQ1, "the quiz did not stay on question 1");
  assert.equal(left, "", "the typed words stayed in the answer box");
  assert.doesNotMatch(html, /HELPME|feel awful|color: ?red/);
  assert.match(after, /Got it/);
  assert.doesNotMatch(after, /STAND-IN HELP WORDS/);
  assert.doesNotMatch(storage, /HELPME|awful/);
});

await check("\"Jarvis's guess\" is gone once the grader is verified", async () => {
  const page = await workTab({ quiz: { verified: true } });
  await start(page);
  await page.locator("#quiz-run textarea").fill("An answer.");
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(400);
  const text = await page.locator("#quiz-run").innerText();
  await page.close();
  assert.match(text, /Got it/);
  assert.doesNotMatch(text, new RegExp(GUESS_LABEL));
});

await check("an empty answer is refused in plain words and nothing is sent", async () => {
  const page = await workTab({ quiz: {} });
  await start(page);
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(300);
  const text = await page.locator("#quiz-run").innerText();
  const sent = (await calls(page)).filter((c) => c.cmd === "brain_quiz_answer");
  await page.close();
  assert.match(text, /Type an answer first/);
  assert.deepEqual(sent, []);
});

await check("Next question, then Finish shows \"Look at these again\" with the question numbers", async () => {
  const page = await workTab({ quiz: { questions: 2, levels: ["got_it", "not_yet"] } });
  await start(page);
  for (let i = 0; i < 2; i++) {
    await page.locator("#quiz-run textarea").fill(`answer ${i}`);
    await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
    await page.waitForTimeout(300);
    if (i === 0) await page.locator("#quiz-run").getByRole("button", { name: "Next question" }).click();
  }
  const progress = await page.locator("#quiz-run").innerText();
  await page.locator("#quiz-run").getByRole("button", { name: FINISH_LABEL }).click();
  await page.waitForTimeout(300);
  const text = await page.locator("#quiz-run").innerText();
  await page.close();
  assert.match(progress, /Not yet/);
  assert.match(text, new RegExp(AGAIN_HEADING));
  assert.match(text, /1 Got it · 0 Partly · 1 Not yet/);
  assert.match(text, /2\. Question text number 2\?/, "the summary does not list the question's words");
  assert.match(text, /^Close$/m);
});

await check("a skipped question is listed under \"Look at these again\" but not counted", async () => {
  const page = await workTab({ quiz: { questions: 3, levels: ["got_it"] } });
  await start(page);
  await page.locator("#quiz-run textarea").fill("right");
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(300);
  await page.locator("#quiz-run").getByRole("button", { name: FINISH_LABEL }).click();
  await page.waitForTimeout(300);
  const text = await page.locator("#quiz-run").innerText();
  await page.close();
  assert.match(text, /1 Got it · 0 Partly · 0 Not yet/);
  assert.match(text, /2\. Question text number 2\?/);
  assert.match(text, /3\. Question text number 3\?/);
  assert.doesNotMatch(text, /1\. Question text/);
});

await check("a finished quiz with everything right says there is nothing to look at again", async () => {
  const page = await workTab({ quiz: { questions: 1, levels: ["got_it"] } });
  await start(page);
  await page.locator("#quiz-run textarea").fill("right");
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(300);
  await page.locator("#quiz-run").getByRole("button", { name: FINISH_LABEL }).click();
  await page.waitForTimeout(300);
  const text = await page.locator("#quiz-run").innerText();
  await page.close();
  assert.match(text, new RegExp(AGAIN_EMPTY.replace(".", "\\.")));
});

await check("Stop and forget this quiz: one call, the quiz is gone, the paste box is back", async () => {
  const page = await workTab({ quiz: {} });
  await start(page);
  await page.locator("#quiz-run").getByRole("button", { name: STOP_LABEL }).click();
  await page.waitForTimeout(300);
  const sent = (await calls(page)).filter((c) => c.cmd === "brain_quiz_stop");
  const formShown = await page.locator("#quiz-start-form").isVisible();
  const run = (await page.locator("#quiz-run").innerText()).trim();
  await page.close();
  assert.deepEqual(sent, [{ cmd: "brain_quiz_stop", id: "qz0001" }]);
  assert.equal(formShown, true);
  assert.equal(run, "");
});

await check("the PC's refusals are put in plain words (model down, too many quizzes)", async () => {
  for (const code of ["model_unavailable", "too_many_quizzes"]) {
    const page = await workTab({ quiz: { refuse: { brain_quiz_start: code } } });
    await start(page);
    const text = await page.locator("#quiz-run").innerText();
    const kept = await page.locator("#quiz-text").inputValue();
    await page.close();
    assert.ok(text.includes(ERROR_WORDS[code]), code);
    assert.equal(kept, PASTE, "a refused start threw the owner's paste away");
  }
});

await check("a quiz the PC no longer holds ends the session with a plain line", async () => {
  const page = await workTab({ quiz: {} });
  await start(page);
  await page.evaluate(() => { window.__quiz.refuse = { brain_quiz_answer: "not_found" }; });
  await page.locator("#quiz-run textarea").fill("hello");
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(300);
  const text = await page.locator("#quiz-run").innerText();
  const formShown = await page.locator("#quiz-start-form").isVisible();
  await page.close();
  assert.ok(text.includes(ERROR_WORDS.not_found));
  assert.equal(formShown, true);
});

await check("a PC without Quiz says so in words", async () => {
  const page = await workTab({});
  await start(page);
  const text = await page.locator("#quiz-run").innerText();
  await page.close();
  assert.match(text, /does not have Quiz yet/);
});

await check("held on a stale link: Write questions is greyed, and every quiz button is a live one", async () => {
  const page = await workTab({ quiz: {}, link: { stale: true } });
  const startDisabled = await page.locator("#quiz-start").isDisabled();
  await page.close();
  assert.equal(startDisabled, true);
  const js = read("src/brain.js");
  const section = js.split("Quiz me on a text (the owner")[1].split("// Private answers turned on or off")[0];
  for (const label of ["QUIZ_ANSWER_LABEL", "QUIZ_FINISH", "QUIZ_STOP"]) {
    assert.match(section, new RegExp(`button\\(${label},[^\\n]*\\{[^}]*live: true`), `${label} is not a live button`);
  }
  assert.match(section, /canAct/, "the calls do not check the link");
});

await check("nothing is stored: no text, answer, mark or draft in localStorage or sessionStorage", async () => {
  const page = await workTab({ quiz: {} });
  await page.locator("#quiz-text").fill(PASTE);
  await start(page);
  await page.locator("#quiz-run textarea").fill("SECRET ANSWER WORDS");
  await page.locator("#quiz-run").getByRole("button", { name: ANSWER_LABEL }).click();
  await page.waitForTimeout(300);
  const stored = await page.evaluate(() => JSON.stringify([
    Object.entries(localStorage), Object.entries(sessionStorage)]));
  await page.close();
  assert.doesNotMatch(stored, /SECRET ANSWER|Bread is made|SOURCE PASSAGE|already|Question text/);
  const src = read("src/quiz.js") + read("src/brain.js").split("Quiz me on a text (the owner")[1]
    .split("// Private answers turned on or off")[0];
  assert.doesNotMatch(src, /localStorage|sessionStorage|indexedDB/i);
});

await check("the words are hidden with the private lists and come back after Show", async () => {
  const page = await workTab({ quiz: {}, security: { hidden: true } });
  await start(page);
  const hidden = await page.locator("#quiz-card").innerText();
  await page.evaluate(() => { window.__security.revealed = true; });
  await page.evaluate(() => window.__emit("security-changed", {}));
  await page.waitForTimeout(500);
  const shown = await page.locator("#quiz-card").innerText();
  await page.close();
  assert.doesNotMatch(hidden, /Question text number/);
  assert.match(hidden, /Hidden until Windows Hello confirms it is you\./);
  assert.match(hidden, new RegExp(FINISH_LABEL), "Finish is gone while the lists are hidden");
  assert.match(hidden, new RegExp(STOP_LABEL));
  assert.match(shown, /Question text number 1\?/);
});

await check("CONTROL: every write is held on a stale link, Rust redacts, and the wiring agrees", async () => {
  const rs = read("src-tauri/src/brain/quiz.rs");
  for (const cmd of ["brain_quiz_start", "brain_quiz_answer", "brain_quiz_finish", "brain_quiz_stop"]) {
    const f = rs.slice(rs.indexOf(`pub async fn ${cmd}(`));
    const body = f.slice(0, f.indexOf("\n}\n"));
    assert.ok(body.indexOf("require_link_live") >= 0
      && body.indexOf("require_link_live") < body.indexOf("post("),
      `${cmd} is not held on a stale link`);
  }
  assert.match(rs, /crate::lock::private_hidden/);
  assert.doesNotMatch(rs.split("#[cfg(test)]")[0], /println!|eprintln!|tracing::|log::/);
  const all = ["brain_quiz_start", "brain_quiz_get", "brain_quiz_answer", "brain_quiz_finish", "brain_quiz_stop"];
  for (const cmd of all) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::quiz::${cmd},`));
    const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-quiz"], cmd);
  }
  const caps = JSON.parse(read("src-tauri/capabilities/brain.json")).permissions;
  assert.ok(caps.includes("brain-quiz"));
  for (const other of ["quickbar", "widget", "hud", "settings", "faces", "floating", "onboarding"]) {
    assert.ok(!read(`src-tauri/capabilities/${other}.json`).includes("brain-quiz"), `${other} holds brain-quiz`);
  }
  assert.match(rs, /\/api\/quiz\/\{id\}\/answer/);
  assert.match(rs, /\/api\/quiz\/\{id\}\/finish/);
  assert.match(rs, /\/api\/quiz\/\{id\}\/stop/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nQuiz: no card, nothing stored, marks labelled Jarvis's guess until the grader is verified, hidden with the private lists");
process.exit(fails.length ? 1 : 0);
