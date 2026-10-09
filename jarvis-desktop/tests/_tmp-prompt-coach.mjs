/**
 * TEMPORARY - the prompt coach's slice of the Jarvis bar, driven in a real
 * browser against the real page with a stub bridge. Deleted after the run.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW_ON = {
  ok: true, on: true, why: "", label: "Prompt coach",
  detail: "On: a Coach this button appears beside the box where you type.",
  heading: "Prompt coach", button: "Coach this", send_mine: "Send mine",
  send_suggestion: "Send the suggestion",
};
const VIEW_OFF = { ...VIEW_ON, on: false };
const MISSING_LINE =
  "Your PC's Jarvis cannot show the prompt coach yet - run apply-patches.ps1 on the PC.";

const CRITIQUE = {
  ok: true,
  coach: {
    score: 4, clear: false,
    issues: [{ what: "No output shape", why: "The answer could be prose or a list",
               fix: "Say: a table, one row per model." }],
    missing: ["Which PC is this for?"],
    suggestion: "Compare qwen3:8b and llama3.1:8b on my RTX 2080, as a table.",
  },
};

/** The stub bridge: the coach's two commands, and a record of everything. */
async function coachBridge(page, { view = VIEW_ON, answer = CRITIQUE, coachFails = null } = {}) {
  await page.evaluate(({ view, answer, coachFails }) => {
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    window.__coach = [];
    core.invoke = async (cmd, args) => {
      if (cmd === "get_prompt_coach") {
        window.__coach.push({ cmd });
        if (view === null) throw new Error("boom");
        return JSON.parse(JSON.stringify(view));
      }
      if (cmd === "coach_prompt") {
        window.__coach.push({ cmd, ...args });
        if (coachFails) throw new Error(coachFails);
        return JSON.parse(JSON.stringify(answer));
      }
      return invoke(cmd, args);
    };
  }, { view, answer, coachFails });
}

const coachCalls = (page) => page.evaluate(() => window.__coach.filter((c) => c.cmd === "coach_prompt"));
const readCalls = (page) => page.evaluate(() => window.__coach.filter((c) => c.cmd === "get_prompt_coach").length);

/** The last `stream_chat` payload this page sent (null if none). */
const lastTurn = (page) => page.evaluate(() => {
  const calls = (window.__calls || []).filter((c) => c[0] === "stream_chat");
  const call = calls[calls.length - 1];
  if (!call) return null;
  return { count: calls.length, messages: call[1].messages };
});

const { base, close } = await K.serve();
const browser = await K.launch();

async function open(data = {}, stub = {}) {
  const page = await K.open(browser, base, "index.html", data);
  await coachBridge(page, stub);
  // The panel's read happens on mount, before this stub existed; ask again so
  // the button is drawn from it (the same read the window does on focus).
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForFunction(() => {
    const b = document.getElementById("coach-this");
    return b && !b.hidden;
  }, null, { timeout: 4000 }).catch(() => {});
  return page;
}

/* ── 1. off by default: no button at all ──────────────────────────────── */

await check("coach OFF: there is no button at all, and the panel is not there", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await page.waitForTimeout(400);
  const off = await page.locator("#coach-this").count();
  const hidden = await page.locator("#coach-this").isHidden().catch(() => true);
  const panel = await page.locator("#coach-panel").isHidden();
  const errors = page.__errors;
  await page.close();
  assert.equal(off <= 1 && hidden, true, `the button is not shown (count=${off})`);
  assert.equal(panel, true, "the panel is hidden");
  assert.deepEqual(errors, []);
});

await check("a PC with NO such route: still no button, and the bar is otherwise the same", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await coachBridge(page, { view: { available: false, why: MISSING_LINE, on: false } });
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForTimeout(200);
  const hidden = await page.locator("#coach-this").isHidden();
  const title = await page.locator("#coach-this").getAttribute("title");
  const errors = page.__errors;
  await page.close();
  assert.equal(hidden, true, "no broken button");
  assert.equal(title, MISSING_LINE, "the PC's own line is on the button, not a made-up one");
  assert.deepEqual(errors, []);
});

/* ── 2. on: the button appears, above the box, and sends the right body ─ */

await check("coach ON: the button shows with the PC's own word, ABOVE the box", async () => {
  const page = await open({}, { view: VIEW_ON });
  const words = await page.locator("#coach-this").innerText();
  const box = await page.locator("#prompt").boundingBox();
  const button = await page.locator("#coach-this").boundingBox();
  const errors = page.__errors;
  await page.close();
  assert.equal(words, "Coach this");
  assert.ok(button && box, "both are drawn");
  assert.ok(button.y + button.height <= box.y + 1,
    `the button sits above the box (button bottom ${button.y + button.height}, box top ${box.y})`);
  assert.deepEqual(errors, []);
});

await check("pressing it sends the box's words and the last few turns, and NOTHING else", async () => {
  const page = await open({}, { view: VIEW_ON });
  // Say them through the real composer so state.thread is real: two turns,
  // each with an answer (a turn with no answer is never added to the thread).
  await page.evaluate(() => { window.__chatReplies = ["Yes, two things.", "The dentist at ten."]; });
  await page.fill("#prompt", "what is on my calendar");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(150);
  await page.fill("#prompt", "and tomorrow?");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const turnsBefore = await lastTurn(page);
  await page.fill("#prompt", "compare qwen3:8b and llama3.1:8b");
  await page.click("#coach-this");
  await page.waitForTimeout(300);
  const calls = await coachCalls(page);
  const errors = page.__errors;
  await page.close();
  assert.equal(turnsBefore.count, 2, "two real turns ran first");
  assert.equal(calls.length, 1, "exactly one critique asked for");
  assert.equal(calls[0].text, "compare qwen3:8b and llama3.1:8b", "the words in the box, as typed");
  assert.ok(Array.isArray(calls[0].history), "history is a list");
  assert.ok(calls[0].history.length <= 6, `history capped at 6 (got ${calls[0].history.length})`);
  for (const t of calls[0].history) {
    assert.deepEqual(Object.keys(t).sort(), ["text", "who"], "each turn is {who, text} only");
    assert.ok(["owner", "jarvis"].includes(t.who), `who is owner|jarvis, got ${t.who}`);
    assert.equal(typeof t.text, "string");
  }
  assert.equal(calls[0].history.at(-1).who, "owner", "the newest turn is the owner's question");
  assert.ok(calls[0].history.some((t) => t.who === "jarvis"), "Jarvis's answers are there too");
  assert.deepEqual(errors, []);
});

/* ── 3. the panel: order, the score, the full rewrite ─────────────────── */

await check("the panel shows score, the gap, the question, and the rewrite IN FULL, in order", async () => {
  const long = `${"- word".repeat(400)}END`;
  const page = await open({}, {
    view: VIEW_ON,
    answer: { ok: true, coach: { ...CRITIQUE.coach, score: 1, suggestion: long } },
  });
  await page.fill("#prompt", "compare the two models");
  await page.click("#coach-this");
  await page.waitForTimeout(300);
  const text = await page.locator("#coach-panel").innerText();
  // The headings are drawn uppercase by CSS (text-transform), so compare
  // case-insensitively; the words themselves are the panel's own.
  const lower = text.toLowerCase();
  const score = await page.locator(".coach-score").innerText();
  const shown = await page.locator(".coach-suggestion-text").innerText();
  const sendSuggestion = await page.locator(".coach-send-suggestion").isDisabled();
  const errors = page.__errors;
  await page.close();
  assert.equal(score, "Score: 1 out of 10");
  assert.ok(text.includes("No output shape"), "what is missing");
  assert.ok(text.includes("Why it matters: The answer could be prose or a list"), "why");
  assert.ok(text.includes("Smallest fix: Say: a table, one row per model."), "the smallest fix");
  assert.ok(lower.includes("it would have to ask you"), "the questions heading");
  assert.ok(text.includes("Which PC is this for?"), "the question itself");
  assert.ok(lower.includes("the rewritten prompt"), "the rewrite heading");
  assert.equal(shown, long, "the rewritten prompt is shown in FULL, not trimmed");
  assert.equal(sendSuggestion, false, "a 1 out of 10 is still sendable: the suggestion button is live");
  const order = [text.indexOf("Score:"), text.indexOf("No output shape"),
                 lower.indexOf("it would have to ask you"), lower.indexOf("the rewritten prompt")];
  assert.deepEqual(order, [...order].sort((a, b) => a - b), "in that order");
  assert.deepEqual(errors, []);
});

/* ── 4. a refusal shows the PC's own sentence, never a blank panel ────── */

await check("a refusal (409) shows the PC's own sentence, word for word", async () => {
  const said = "That is too short to coach - write a little more and try again.";
  const page = await open({}, { view: VIEW_ON, coachFails: said });
  await page.fill("#prompt", "hi");
  await page.click("#coach-this");
  await page.waitForTimeout(300);
  const note = await page.locator(".coach-note").innerText();
  const visible = await page.locator("#coach-panel").isVisible();
  const errors = page.__errors;
  await page.close();
  assert.equal(visible, true, "the panel is shown, not blank");
  assert.equal(note, said, "the PC's sentence, as it came");
  assert.deepEqual(errors, []);
});

/* ── 5. the two buttons: nothing is sent without one of them ──────────── */

await check("nothing is sent by pressing Coach this, closing, or reading a critique", async () => {
  const page = await open({}, { view: VIEW_ON });
  await page.fill("#prompt", "compare the two models");
  await page.click("#coach-this");
  await page.waitForTimeout(250);
  await page.click(".coach-close");
  await page.waitForTimeout(100);
  const turns = await lastTurn(page);
  const errors = page.__errors;
  await page.close();
  assert.equal(turns, null, "no turn was sent");
  assert.deepEqual(errors, []);
});

await check("Send mine sends exactly what is in the box, unchanged", async () => {
  const page = await open({}, { view: VIEW_ON });
  const mine = "compare qwen3:8b and llama3.1:8b  with  double spaces";
  await page.fill("#prompt", mine);
  await page.click("#coach-this");
  await page.waitForTimeout(250);
  await page.click(".coach-send-mine");
  await page.waitForTimeout(250);
  const turns = await lastTurn(page);
  const errors = page.__errors;
  await page.close();
  const last = turns.messages[turns.messages.length - 1];
  assert.equal(turns.count, 1, "one turn sent");
  assert.equal(last.content, mine, "the owner's own words, unchanged");
  assert.deepEqual(errors, []);
});

await check("Send the suggestion puts the rewrite in the box and sends THAT", async () => {
  const page = await open({}, { view: VIEW_ON });
  await page.fill("#prompt", "compare the two models");
  await page.click("#coach-this");
  await page.waitForTimeout(250);
  await page.click(".coach-send-suggestion");
  await page.waitForTimeout(250);
  const turns = await lastTurn(page);
  const errors = page.__errors;
  await page.close();
  const last = turns.messages[turns.messages.length - 1];
  assert.equal(turns.count, 1, "one turn sent");
  assert.equal(last.content, CRITIQUE.coach.suggestion, "the rewritten prompt was sent");
});

await check("the two buttons wear the PC's own words", async () => {
  const page = await open({}, { view: { ...VIEW_ON, send_mine: "Send mine", send_suggestion: "Send the suggestion" } });
  await page.fill("#prompt", "compare the two models");
  await page.click("#coach-this");
  await page.waitForTimeout(250);
  const mine = await page.locator(".coach-send-mine").innerText();
  const suggestion = await page.locator(".coach-send-suggestion").innerText();
  await page.close();
  assert.equal(mine, "Send mine");
  assert.equal(suggestion, "Send the suggestion");
});

/* ── 6. the switch, read while the window is open ─────────────────────── */

await check("turning the coach on in Settings brings the button without a reload", async () => {
  const page = await K.open(browser, base, "index.html", {});
  let on = false;
  await page.evaluate(() => {
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    window.__coachOn = false;
    core.invoke = async (cmd, args) => {
      if (cmd === "get_prompt_coach") {
        return {
          ok: true, on: window.__coachOn, why: "", label: "Prompt coach",
          heading: "Prompt coach", button: "Coach this", send_mine: "Send mine",
          send_suggestion: "Send the suggestion",
        };
      }
      return invoke(cmd, args);
    };
  });
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForTimeout(150);
  const before = await page.locator("#coach-this").isHidden();
  on = true;
  await page.evaluate(() => { window.__coachOn = true; window.dispatchEvent(new Event("focus")); });
  await page.waitForTimeout(200);
  const after = await page.locator("#coach-this").isHidden();
  const errors = page.__errors;
  await page.close();
  assert.equal(before, true, "off: no button");
  assert.equal(after, false, "on: the button appears");
  assert.deepEqual(errors, []);
});

await browser.close();
close();

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nprompt coach: the button, the panel and the two send buttons");
