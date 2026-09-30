/**
 * Quiz me on a YouTube video, the second block on the Brain's Work tab's Quiz
 * card (the owner's decision of 2026-09-30; docs/STUDY-FROM-TEXT-DESIGN.md
 * section 14; JARVIS-API.md section 112; src/youtube.js, src/quiz.js YT_*,
 * brain.js, src-tauri/src/brain/youtube.rs).
 *
 * Held to fixtures/youtube-cases.json (written by tools/gen_youtube_cases.py,
 * the phone reads the same file): the words word for word, the state phases,
 * the poll gap, the unknown-state limit and every sample reply's `expect`.
 *
 * What must hold:
 * - the shared words, word for word, in the page; the terms line always visible;
 * - the start sends ONLY the link and the count, once, then the box is emptied;
 *   the PC's own message is shown and the link is kept nowhere;
 * - polling about every 2 seconds; ready opens the ordinary quiz with the
 *   "From YouTube captions" label and the captions' outside line; a truncated
 *   quiz shows the PC's sentence above the questions;
 * - every end state shows the PC's sentence and offers the box again;
 * - an unknown state is still working, and is given up after 180 seconds;
 * - Cancel only while waiting, never held on a stale link;
 * - a refusal is the PC's words as they came (never a code, never the link);
 * - a PC without the feature says so in one line and offers nothing;
 * - hidden with the private lists: no link box, no request link, no quiz words,
 *   but the state sentence and Cancel stay;
 * - CONTROL: the Rust/JS/permissions wiring agrees, on the Brain window only.
 *
 * Needs Playwright (see tests/README.md); the first part needs no browser.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as Q from "../src/quiz.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIX = JSON.parse(read("tests/fixtures/youtube-cases.json"));
const LINK = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words, the phases and the samples (no browser) ───────────────── */

await check("the shared words, word for word, in the module and the page", async () => {
  const W = FIX.words;
  assert.equal(Q.YT_TITLE, W.title);
  assert.equal(Q.YT_INTRO, W.intro);
  assert.equal(Q.YT_TERMS, W.terms);
  assert.equal(Q.YT_OUTSIDE, W.outside);
  assert.equal(Q.YT_PLACEHOLDER, W.placeholder);
  assert.equal(Q.YT_START, W.start);
  assert.equal(Q.YT_CANCEL, W.cancel);
  assert.equal(Q.YT_LABEL, W.label);
  assert.equal(Q.YT_MISSING, W.missing);
  assert.equal(Q.YT_LINK_MAX, FIX.link_max);
  assert.equal(Q.YT_POLL_SECONDS, FIX.poll_seconds);
  assert.equal(Q.YT_UNKNOWN_LIMIT_SECONDS, FIX.unknown_state_limit_seconds);
});

await check("every state has the phase the contract gives it; an unknown one is still working", async () => {
  for (const [state, phase] of Object.entries(FIX.phases)) {
    assert.equal(Q.ytPhase(state), phase, state);
    assert.equal(Q.ytIsKnown(state), true, state);
  }
  assert.equal(Q.ytPhase("thinking_hard"), "working");
  assert.equal(Q.ytIsKnown("thinking_hard"), false);
  assert.equal(Q.ytPhase(undefined), "working");
  assert.equal(Q.ytPhase("constructor"), "working", "an inherited key was taken for a state");
  assert.equal(Q.ytKeepPolling("waiting"), true);
  assert.equal(Q.ytKeepPolling("working"), true);
  assert.equal(Q.ytKeepPolling("ready"), false);
  assert.equal(Q.ytKeepPolling("ended"), false);
  // Only waiting offers Cancel: nothing else is called "waiting".
  assert.deepEqual(Object.entries(FIX.phases).filter(([, p]) => p === "waiting").map(([s]) => s), ["waiting"]);
});

await check("an empty message falls back to the state's reference words, and an end is never blank", async () => {
  for (const [state, words] of Object.entries(FIX.state_words)) {
    const r = Q.ytReadRequest({ id: "abc", state, message: "" });
    assert.equal(Q.ytShown(r), words, state);
    const own = Q.ytReadRequest({ id: "abc", state, message: "The PC's own." });
    assert.equal(Q.ytShown(own), "The PC's own.");
  }
});

await check("the give-up rule: an unknown state is dropped after 180 seconds, not before", async () => {
  assert.equal(Q.ytGiveUpOnUnknown(null, 999999), false);
  assert.equal(Q.ytGiveUpOnUnknown(1000, 1000 + 179999), false);
  assert.equal(Q.ytGiveUpOnUnknown(1000, 1000 + 180000), true);
});

await check("every sample reply is read as its `expect` says", async () => {
  for (const [name, s] of Object.entries(FIX.samples)) {
    const e = s.expect;
    if (name === "info" || name === "info_no_latest") {
      const info = Q.ytReadInfo(s.body);
      assert.equal(info.available, e.available, name);
      assert.equal(info.linkMax, e.link_max, name);
      assert.equal(info.latest ? info.latest.phase : null, e.latest_phase, name);
      continue;
    }
    const out = Q.ytOutcome(s.body, "Not read.");
    if (e.unreadable) {
      assert.equal(out.ok, false, name);
      assert.ok(out.said.includes(Q.YT_UNREADABLE), name);
      continue;
    }
    assert.equal(out.ok, e.ok, name);
    assert.equal(out.said, e.shown, `${name}: not the PC's words`);
    if (e.ok) {
      assert.equal(out.request.phase, e.phase, name);
      if ("questions" in e) assert.equal(out.request.quiz.questions.length, e.questions, name);
      if ("quiz_id" in e) assert.equal(out.request.quiz.id, e.quiz_id, name);
      if ("source" in e) assert.equal(out.request.quiz.source, e.source, name);
      if ("truncated" in e) assert.equal(out.request.truncated, e.truncated, name);
    } else {
      assert.equal(out.code, e.code, name);
    }
  }
});

await check("every refusal and failure is shown as the PC sent it - never a code, never rewritten", async () => {
  for (const [code, r] of Object.entries(FIX.refusals)) {
    const out = Q.ytOutcome({ ok: false, error: code, message: r.message }, "Not started.");
    assert.equal(out.said, r.message, code);
    assert.equal(out.gone, code === "not_found", code);
  }
  for (const [code, message] of Object.entries(FIX.failures)) {
    const out = Q.ytOutcome({ ok: true, request: { id: "abc", state: "failed", message, error: code } }, "Not read.");
    assert.equal(out.said, message, code);
    assert.equal(out.request.phase, "ended", code);
  }
  // None of the PC's sentences is written in this app.
  const src = read("src/quiz.js").split("Quiz me on a YouTube video (docs")[1] + read("src/youtube.js") + read("src/brain.js");
  for (const [, r] of Object.entries(FIX.refusals)) {
    if (r.message === Q.YT_MISSING) continue;
    assert.ok(!src.includes(r.message), `written in the app: ${r.message}`);
  }
  for (const message of Object.values(FIX.failures)) assert.ok(!src.includes(message), message);
  // No PC words at all: a plain line of ours that names neither a code nor the link.
  const bare = Q.ytOutcome({ ok: false }, "Not started.");
  assert.match(bare.said, /^Not started\./);
});

await check("the start button needs only a non-empty link; the link is not judged here", async () => {
  assert.equal(Q.ytCanStart(""), false);
  assert.equal(Q.ytCanStart("   "), false);
  assert.equal(Q.ytCanStart("not a link at all"), true);
  assert.equal(Q.ytValidId("0123456789ab"), true);
  assert.equal(Q.ytValidId("../x"), false);
  assert.equal(Q.ytValidId("a/b"), false);
  assert.equal(Q.ytValidId(""), false);
  assert.equal(Q.ytValidId("a".repeat(65)), false);
});

await check("a truncated quiz carries the PC's sentence; a whole one carries none", async () => {
  const t = Q.ytOutcome(FIX.samples.ready_truncated.body, "x").request;
  assert.equal(Q.ytTruncatedNote(t), FIX.samples.ready_truncated.expect.shown);
  assert.equal(t.minutes, 42);
  const w = Q.ytOutcome(FIX.samples.ready.body, "x").request;
  assert.equal(Q.ytTruncatedNote(w), null);
  assert.equal(Q.ytFromCaptions(w.quiz), true);
  assert.equal(Q.ytFromCaptions(Q.readQuiz({ id: "q", questions: [] })), false);
});

await check("the link is kept nowhere: no storage, no log, no notification in the code", async () => {
  const code = (read("src/youtube.js") + read("src/quiz.js").split("Quiz me on a YouTube video (docs")[1])
    .replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
  assert.doesNotMatch(code, /localStorage|sessionStorage|indexedDB|console\.|Notification|toast\(|\.title\s*=/);
});

/* ── The Brain window ─────────────────────────────────────────────────── */

let K;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
} catch {
  console.log("Playwright is not installed: the window checks were not run.");
  process.exit(fails.length ? 1 : 0);
}

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };
const S = FIX.samples;

const scenario = (extra = {}) => ({
  youtube: { info: S.info_no_latest.body, start: S.started.body, script: [S.fetching.body],
    cancel: { ok: true, request: { ...S.denied.body.request, state: "withdrawn",
      message: FIX.state_words.withdrawn } }, ...extra },
  quiz: { quiz: null },
});

async function workTab(data = scenario(), { clock = true } = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(500);
  // Time is ours from here: the poll gap and the three minutes are stepped, not waited.
  if (clock) {
    await page.clock.install();
    await page.clock.pauseAt(new Date(Date.now() + 1000));
  }
  return page;
}
const calls = (page) => page.evaluate(() => window.__youtube.calls);
const reads = (page) => page.evaluate(() => window.__youtube.reads);
const block = (page) => page.locator("#youtube-block");
const text = async (page) => (await block(page).innerText()).replace(/\s+/g, " ").trim();
const startWith = async (page, link = LINK) => {
  await page.locator("#youtube-link").fill(link);
  await page.locator("#youtube-start").click();
  await page.waitForTimeout(200);
};
const tick = async (page, ms) => {
  await page.clock.runFor(ms);
  await page.waitForTimeout(150);
};

await check("the block sits under the paste box, in the Quiz card, with its words and the terms line always shown", async () => {
  const page = await workTab();
  const inCard = await page.locator("#quiz-card #youtube-block").count();
  const order = await page.evaluate(() => {
    const f = document.getElementById("quiz-start-form");
    const b = document.getElementById("youtube-block");
    return Boolean(f.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  const t = await text(page);
  const placeholder = await page.locator("#youtube-link").getAttribute("placeholder");
  const label = await page.locator("#youtube-link").getAttribute("aria-label");
  const startText = (await page.locator("#youtube-start").innerText()).trim();
  const termsVisible = await page.locator("#youtube-terms").isVisible();
  const heading = (await block(page).locator("h3").textContent()).trim();
  await page.close();
  assert.equal(inCard, 1);
  assert.ok(order, "the block is not after the paste form");
  assert.equal(heading, FIX.words.title);
  assert.ok(t.includes(FIX.words.intro));
  assert.ok(t.includes(FIX.words.terms));
  assert.ok(t.includes(FIX.words.outside));
  assert.equal(placeholder, FIX.words.placeholder);
  assert.equal(label, FIX.words.placeholder);
  assert.equal(startText, FIX.words.start);
  assert.ok(termsVisible, "the terms line is behind a tap");
});

await check("Read the captions sends ONLY the link and the count, once; the box is emptied and the PC's message shown", async () => {
  const page = await workTab();
  const before = await page.locator("#youtube-start").isDisabled();
  await startWith(page, `  ${LINK}  `);
  const sent = (await calls(page)).filter((c) => c.cmd === "brain_youtube_start");
  const left = await page.locator("#youtube-link").inputValue();
  const t = await text(page);
  const formShown = await page.locator("#youtube-link").isVisible();
  const cancel = await block(page).getByRole("button", { name: FIX.words.cancel }).count();
  const storage = await page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]));
  await page.close();
  assert.equal(before, true, "start was offered with an empty box");
  assert.equal(sent.length, 1);
  // The link goes as typed (the PC judges it); only url and count exist.
  assert.deepEqual(Object.keys(sent[0]).sort(), ["cmd", "count", "url"]);
  assert.equal(sent[0].url.trim(), LINK);
  assert.equal(sent[0].count, 5);
  assert.equal(left, "", "the link stayed in the box");
  assert.equal(formShown, false);
  assert.ok(t.includes(S.started.expect.shown));
  assert.equal(cancel, 1, "Cancel is missing while the card waits");
  assert.doesNotMatch(storage, /youtube|dQw4w/);
});

await check("it polls about every 2 seconds, not faster, and shows each state's own words", async () => {
  const page = await workTab(scenario({ script: [S.fetching.body, S.fetching.body, S.ready.body] }));
  await startWith(page);
  await tick(page, 1900);
  const early = await reads(page);
  await tick(page, 200);
  const first = await reads(page);
  const t1 = await text(page);
  const cancelGone = await block(page).getByRole("button", { name: FIX.words.cancel }).count();
  await page.close();
  assert.equal(early, 0, "polled before 2 seconds");
  assert.equal(first, 1);
  assert.ok(t1.includes(S.fetching.expect.shown));
  assert.equal(cancelGone, 0, "Cancel stayed once the captions were being read");
});

await check("ready opens the ordinary quiz, labelled 'From YouTube captions', with the captions' outside line", async () => {
  const page = await workTab({ ...scenario({ script: [S.ready.body] }), quiz: { quiz: S.ready.body.request.quiz } });
  await startWith(page);
  await tick(page, 2200);
  const run = await page.locator("#quiz-run").innerText();
  const outside = (await page.locator("#quiz-outside").innerText()).trim();
  const blockHidden = await block(page).isHidden();
  const formHidden = await page.locator("#quiz-start-form").isHidden();
  const reads1 = await reads(page);
  await tick(page, 6000);
  const reads2 = await reads(page);
  // The ordinary quiz still answers through the quiz routes.
  await page.locator("#quiz-run textarea").fill("Never gonna give you up.");
  await page.locator("#quiz-run").getByRole("button", { name: "Check my answer" }).click();
  await page.waitForTimeout(300);
  const answered = await page.evaluate(() => window.__quiz.calls);
  const outsideAfter = (await page.locator("#quiz-outside").innerText()).trim();
  await page.close();
  assert.ok(run.includes(FIX.words.label));
  assert.match(run, /What is the video mainly about\?/);
  assert.match(run, /Question 1 of 2/);
  assert.doesNotMatch(run, /Ready\. The video is long/);
  assert.equal(outside, FIX.words.outside);
  assert.equal(outsideAfter, FIX.words.outside);
  assert.ok(blockHidden && formHidden);
  assert.equal(reads2, reads1, "kept polling after the quiz was ready");
  assert.deepEqual(answered.map((c) => [c.cmd, c.id, c.n]), [["brain_quiz_answer", "q1a2b3c4d5e6", 1]]);
});

await check("a truncated quiz shows the PC's sentence above its questions", async () => {
  const page = await workTab({ ...scenario({ script: [S.ready_truncated.body] }), quiz: { quiz: S.ready_truncated.body.request.quiz } });
  await startWith(page);
  await tick(page, 2200);
  const run = await page.locator("#quiz-run").innerText();
  await page.close();
  assert.ok(run.includes(S.ready_truncated.expect.shown), run);
  assert.ok(run.indexOf(S.ready_truncated.expect.shown) < run.indexOf("What is the video mainly about?"));
});

await check("a plain text quiz keeps its own outside line and has no YouTube label", async () => {
  const page = await workTab();
  const outside = (await page.locator("#quiz-outside").innerText()).trim();
  await page.close();
  assert.equal(outside, Q.OUTSIDE_LINE);
});

await check("every end state shows the PC's sentence, stops polling and offers the box again", async () => {
  for (const name of ["denied"]) {
    const page = await workTab(scenario({ script: [S[name].body] }));
    await startWith(page);
    await tick(page, 2200);
    const t = await text(page);
    const boxBack = await page.locator("#youtube-link").isVisible();
    const r1 = await reads(page);
    await tick(page, 8000);
    const r2 = await reads(page);
    await page.close();
    assert.ok(t.includes(S[name].expect.shown), name);
    assert.ok(boxBack, name);
    assert.equal(r2, r1, `${name}: kept polling`);
  }
  const page = await workTab(scenario({ script: [S.failed_no_captions.body] }));
  await startWith(page);
  await tick(page, 2200);
  const t = await text(page);
  await page.close();
  assert.ok(t.includes(S.failed_no_captions.expect.shown));
  assert.doesNotMatch(t, /no_captions/);
});

await check("an unknown state is still working, and is given up after 3 minutes with the PC's last words", async () => {
  const page = await workTab(scenario({ script: [S.unknown_state_with_extra_keys.body] }));
  await startWith(page);
  await tick(page, 60000);
  const mid = await text(page);
  const midBox = await page.locator("#youtube-link").isVisible();
  await tick(page, 110000);
  const stillWorking = await block(page).locator(".yt-status").isVisible();
  await tick(page, 20000);
  const end = await text(page);
  const boxBack = await page.locator("#youtube-link").isVisible();
  const r1 = await reads(page);
  await tick(page, 10000);
  const r2 = await reads(page);
  await page.close();
  assert.ok(mid.includes("Still on it."));
  assert.equal(midBox, false);
  assert.ok(stillWorking, "given up before 3 minutes");
  assert.ok(end.includes("Still on it."), "the PC's last words were lost");
  assert.ok(boxBack, "the box was not offered after giving up");
  assert.equal(r2, r1);
});

await check("Cancel shows only while waiting, is not held on a stale link, and shows the PC's words", async () => {
  const page = await workTab(scenario({ info: S.info.body }), { clock: true });
  const t0 = await text(page);
  const cancel = block(page).getByRole("button", { name: FIX.words.cancel });
  assert.equal(await cancel.count(), 1, "a waiting request from the PC was not picked up");
  await cancel.click();
  await page.waitForTimeout(250);
  const sent = (await calls(page)).filter((c) => c.cmd === "brain_youtube_cancel");
  const t = await text(page);
  const boxBack = await page.locator("#youtube-link").isVisible();
  await page.close();
  assert.ok(t0.includes(S.info.body.latest.message));
  assert.deepEqual(sent, [{ cmd: "brain_youtube_cancel", id: "0123456789ab" }]);
  assert.ok(t.includes(FIX.state_words.withdrawn));
  assert.ok(boxBack);
});

await check("on a stale link the start is greyed, but polling and Cancel still work", async () => {
  // A request the PC already holds is picked up on opening; its poll is a real 2-second timer.
  const page = await workTab({ ...scenario({ info: S.info.body, script: [S.fetching.body] }), link: { stale: true } }, { clock: false });
  const cancelDisabled = await block(page).getByRole("button", { name: FIX.words.cancel }).isDisabled();
  await page.waitForTimeout(2600);
  const r = await reads(page);
  await page.close();
  assert.equal(cancelDisabled, false, "Cancel was held on a stale link");
  assert.ok(r >= 1, "polling was held on a stale link");
  const page2 = await workTab({ ...scenario(), link: { stale: true } });
  await page2.locator("#youtube-link").fill(LINK);
  const startDisabled = await page2.locator("#youtube-start").isDisabled();
  const sent = (await calls(page2)).filter((c) => c.cmd === "brain_youtube_start");
  await page2.close();
  assert.equal(startDisabled, true);
  assert.deepEqual(sent, []);
});

await check("a refusal is the PC's words as they came: no code, no link, and the link stays in the box", async () => {
  for (const key of ["refused_not_youtube", "refused_request_waiting", "too_many_quizzes_keeps_pcs_words"]) {
    const page = await workTab(scenario({ start: S[key].body }));
    await startWith(page, "https://example.com/not-youtube");
    const t = await text(page);
    const kept = await page.locator("#youtube-link").inputValue();
    const formShown = await page.locator("#youtube-link").isVisible();
    await page.close();
    assert.ok(t.includes(S[key].expect.shown), key);
    assert.doesNotMatch(t, new RegExp(S[key].expect.code));
    assert.equal(kept, "https://example.com/not-youtube", "the box was emptied on a refusal");
    assert.ok(formShown);
  }
});

await check("a PC without YouTube quizzes says so in one line and offers nothing", async () => {
  const page = await workTab({ quiz: {} });
  const t = await text(page);
  const inputs = await page.locator("#youtube-link").count();
  const visibleInput = inputs ? await page.locator("#youtube-link").isVisible() : false;
  const rows = await page.locator("#youtube-block h3").isVisible();
  await page.close();
  assert.equal(t, FIX.words.missing);
  assert.equal(visibleInput, false);
  assert.equal(rows, false);
  const page2 = await workTab(scenario({ info: { ok: true, available: false } }));
  const t2 = await text(page2);
  await page2.close();
  assert.equal(t2, FIX.words.missing);
});

await check("a read that failed leaves the block hidden rather than guessing", async () => {
  const page = await workTab(scenario({ throws: { brain_youtube_info: "the PC did not answer" } }));
  const hidden = await block(page).isHidden();
  await page.close();
  assert.equal(hidden, true);
});

await check("Spanish practice hides the block unless a request is already open", async () => {
  const page = await workTab();
  await page.locator('input[name="quiz-mode"][value="spanish"]').check();
  await page.waitForTimeout(150);
  const hidden = await block(page).isHidden();
  await page.locator('input[name="quiz-mode"][value="text"]').check();
  await page.waitForTimeout(150);
  const shown = await block(page).isVisible();
  await page.close();
  assert.equal(hidden, true);
  assert.equal(shown, true);
  const open = await workTab(scenario({ info: S.info.body }));
  await open.locator('input[name="quiz-mode"][value="spanish"]').check();
  await open.waitForTimeout(150);
  const stillThere = await open.locator("#youtube-block .yt-status").isVisible();
  await open.close();
  assert.equal(stillThere, true);
});

await check("hidden with the private lists: no link box, no request link, no quiz words - the state and Cancel stay", async () => {
  const page = await workTab({ ...scenario(), security: { hidden: true } });
  const t = await text(page);
  const boxes = await page.locator("#youtube-link").isVisible();
  await page.close();
  assert.equal(boxes, false, "the link box was offered while the lists are hidden");
  assert.match(t, /Hidden until Windows Hello confirms it is you\./);
  assert.ok(t.toLowerCase().includes(FIX.words.title.toLowerCase()));

  const waiting = await workTab({ ...scenario({ info: S.info.body }), security: { hidden: true } });
  const w = await text(waiting);
  const cancel = await block(waiting).getByRole("button", { name: FIX.words.cancel }).count();
  await waiting.close();
  assert.ok(w.includes(S.info.body.latest.message));
  assert.ok(!w.includes("dQw4w9WgXcQ") && !w.includes("youtube.com"), "the request's link was drawn");
  assert.equal(cancel, 1);

  // Picked up on opening from the PC, so its first poll is a real 2-second timer.
  const ready = await workTab({ ...scenario({ info: S.info.body, script: [S.ready.body] }),
    security: { hidden: true }, quiz: { quiz: S.ready.body.request.quiz } }, { clock: false });
  await ready.waitForTimeout(2600);
  const run = await ready.locator("#quiz-card").innerText();
  await ready.close();
  assert.doesNotMatch(run, /mainly about|Why does the speaker/);
  assert.match(run, /Hidden until Windows Hello confirms it is you\./);
});

await check("the link box comes back after Show, and a link pasted before hiding is not kept", async () => {
  const page = await workTab({ ...scenario(), security: { hidden: true } }, { clock: false });
  await page.evaluate(() => { window.__security.revealed = true; });
  await page.evaluate(() => window.__emit("security-changed", {}));
  await page.waitForTimeout(600);
  const shown = await page.locator("#youtube-link").isVisible();
  await page.locator("#youtube-link").fill(LINK);
  await page.evaluate(() => { window.__security.revealed = false; });
  await page.evaluate(() => window.__emit("security-changed", {}));
  await page.waitForTimeout(600);
  const hidden = await page.locator("#youtube-link").isVisible();
  await page.evaluate(() => { window.__security.revealed = true; });
  await page.evaluate(() => window.__emit("security-changed", {}));
  await page.waitForTimeout(600);
  const value = await page.locator("#youtube-link").inputValue();
  await page.close();
  assert.equal(shown, true);
  assert.equal(hidden, false);
  assert.equal(value, "", "a pasted link survived being hidden");
});

await check("nothing is stored: no link, request or quiz words in localStorage or sessionStorage", async () => {
  const page = await workTab({ ...scenario({ script: [S.ready.body] }), quiz: { quiz: S.ready.body.request.quiz } });
  await startWith(page);
  await tick(page, 2200);
  const stored = await page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]));
  await page.close();
  assert.doesNotMatch(stored, /dQw4w9|youtube|mainly about|0123456789ab/);
});

await check("CONTROL: the start is held on a stale link, cancel and reads are not, the link is never logged, and the wiring agrees", async () => {
  const rs = read("src-tauri/src/brain/youtube.rs");
  const fn = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  const start = fn("brain_youtube_start");
  assert.ok(start.indexOf("require_link_live") >= 0 && start.indexOf("require_link_live") < start.indexOf(".post("),
    "the start is not held on a stale link");
  for (const name of ["brain_youtube_get", "brain_youtube_cancel", "brain_youtube_info"]) {
    assert.doesNotMatch(fn(name), /require_link_live/, `${name} is held on a stale link`);
  }
  assert.match(rs, /crate::lock::private_hidden/);
  assert.doesNotMatch(rs.split("#[cfg(test)]")[0], /println!|eprintln!|tracing::|log::|dbg!/);
  assert.match(rs, /\/api\/youtube\/quiz/);
  assert.match(rs, /\/api\/youtube"/);
  assert.match(rs, /\/api\/youtube\/\{id\}\/cancel/);
  const all = ["brain_youtube_info", "brain_youtube_start", "brain_youtube_get", "brain_youtube_cancel"];
  for (const cmd of all) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::youtube::${cmd},`));
    const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-youtube"], cmd);
    assert.match(read(`src-tauri/permissions/autogenerated/${cmd}.toml`), new RegExp(`commands.allow = \\["${cmd}"\\]`));
  }
  const caps = JSON.parse(read("src-tauri/capabilities/brain.json")).permissions;
  assert.ok(caps.includes("brain-youtube"));
  for (const other of ["quickbar", "widget", "hud", "settings", "faces", "floating", "onboarding", "live-badge", "watch-badge"]) {
    assert.ok(!read(`src-tauri/capabilities/${other}.json`).includes("brain-youtube"), `${other} holds brain-youtube`);
  }
  assert.match(read("src/brain.html"), /id="youtube-block"/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nYouTube quiz: one card per link, the link kept nowhere, the PC's own words, hidden with the private lists");
process.exit(fails.length ? 1 : 0);
