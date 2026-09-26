/**
 * Deep questions, in the Brain window - backend/big-model.patch.
 *
 * Every answer here is the backend's own: `K.BIG_MODEL` is
 * tests/fixtures/big-model-cases.json, written by
 * tools/gen_big_model_cases.py from jarvis_big_model itself (deep_status()
 * as `deep_*`, the POST answers as `ask_*`). One check changes the TEXT of a
 * real answer to something hostile, to prove it is rendered and not
 * injected; it never changes the shape.
 *
 * What must hold (JARVIS-API.md section 14, ARCHITECTURE.md section 6):
 * - a question can be asked only when GET /api/deep says `available`;
 *   otherwise the backend's `why` is shown;
 * - "Ask slowly" sends one question, raises no card, and is greyed on a
 *   stale link (rule 4);
 * - each job shows its question, state and why, and when done the time it
 *   took, the words a second, and the answer rendered as text;
 * - the `deep` event makes the list read again - no poll needed - and the
 *   page polls, gently, only while a question is still going;
 * - an older backend is "update with apply-patches.ps1".
 *
 * Two halves, like wiki.mjs: the plate's logic (src/deep.js) on its own,
 * then the Brain window in a real browser, fed by the uikit `deep` option.
 * CONTROL checks read the Rust.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { askDeep, duration, leadLine, POLL_MS, readDeep, runningCount, speedLine, STATES }
  from "../src/deep.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const BM = K.BIG_MODEL;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The plate's logic, against the backend's real answers ─────────────── */

await check("every real deep_status() is read as the PC sent it", async () => {
  for (const name of Object.keys(BM).filter((k) => k.startsWith("deep_"))) {
    const v = readDeep(BM[name]);
    assert.equal(v.available, BM[name].available, name);
    assert.equal(v.why, BM[name].why, name);
    assert.equal(v.update, false, name);
    assert.equal(v.questionChars, BM[name].limits.question_chars, name);
    assert.equal(v.queue, BM[name].limits.queue, name);
    assert.equal(v.jobs.length, BM[name].jobs.length, name);
    for (const j of v.jobs) assert.ok(STATES[j.state], `${name}: no words for ${j.state}`);
  }
  const done = readDeep(BM.deep_done).jobs[0];
  assert.equal(done.answer, BM.deep_done.jobs[0].answer);
  assert.equal(speedLine(done), "Took 8 s, 1.12 words a second.");
  assert.equal(readDeep(BM.deep_thinking).jobs[0].answer, "", "an answer before done");
  assert.equal(speedLine(readDeep(BM.deep_failed).jobs[0]), "");
  assert.equal(runningCount(readDeep(BM.deep_loading)), 1);
  assert.equal(runningCount(readDeep(BM.deep_done)), 0);
  assert.equal(duration(725), "12 min 5 s");
  assert.equal(duration(3780), "1 h 3 min");
});

await check("off: the backend's why, and where to turn it on", async () => {
  const line = leadLine(readDeep(BM.deep_off));
  assert.match(line, /^The big-model switch is off\. To use it, open Settings, go to "Big model \(slow\)"/);
  const old = readDeep({ available: false, why: "Update the backend by running apply-patches.ps1." });
  assert.equal(old.update, true);
  assert.equal(leadLine(old), "Update the backend by running apply-patches.ps1.");
});

await check("asking: the backend's own words, queued or refused", async () => {
  const calls = [];
  const ok = await askDeep(async (c, a) => { calls.push([c, a]); return BM.ask_accepted.body; },
    "  Why is the sky blue?  ");
  assert.deepEqual(calls, [["ask_deep", { question: "Why is the sky blue?" }]]);
  assert.deepEqual(ok, { text: BM.ask_accepted.body.message, tone: "ok", queued: true });
  for (const name of ["ask_refused_off", "ask_too_long_400", "ask_empty_400"]) {
    const said = await askDeep(async () => BM[name].body, "x");
    assert.deepEqual(said, { text: BM[name].body.error, tone: "bad", queued: false }, name);
  }
  const blank = await askDeep(async () => { throw new Error("not called"); }, "   ");
  assert.equal(blank.text, "Type a question first.");
  const stale = await askDeep(async () => {
    throw new Error("The connection to Jarvis is catching up, so nothing can be asked until it does.");
  }, "x");
  assert.match(stale.text, /catching up/);
});

/* ── The Brain window, in a browser ───────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1600 };

/** brain.html on its Memory tab (the one it opens on), deep questions fed. */
async function brain(deep, extra = {}) {
  const page = await K.open(browser, base, "brain.html", { deep, ...extra }, SIZE);
  await page.waitForTimeout(400);
  return page;
}

const plate = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const jobs = [...document.querySelectorAll("#deep-jobs .row-item")].map((r) => ({
    id: r.dataset.id,
    tag: r.querySelector(".row-tag").textContent,
    question: r.querySelector(".row-title").textContent,
    meta: [...r.querySelectorAll(".row-meta")].map((m) => m.textContent),
    open: Boolean(r.querySelector("details[open]")),
    answer: r.querySelector(".deep-answer-body")?.innerText ?? null,
  }));
  return {
    lead: $("deep-state").innerText,
    askHidden: $("deep-ask").hidden,
    button: $("deep-ask-button"),
    buttonDisabled: $("deep-ask-button")?.disabled,
    count: $("deep-count").innerText,
    maxLength: $("deep-question").maxLength,
    said: $("deep-said").innerText,
    jobs,
    list: $("deep-jobs").innerText,
    all: $("deep-card").innerText,
    reads: window.__deep.reads,
    asks: window.__deep.asks,
  };
});

await check("the plate sits on the Memory tab, right after the wiki", async () => {
  const page = await brain({ status: BM.deep_done });
  const order = await page.evaluate(() =>
    [...document.querySelectorAll("#view-memory .card h2")].map((h) => h.textContent.trim()));
  const errors = page.__errors;
  await page.close();
  assert.equal(order[order.indexOf("Wiki") + 1], "Deep questions");
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await check("done: question, state, why, time and words a second, and the answer as text", async () => {
  const page = await brain({ status: BM.deep_done });
  const s = await plate(page);
  await page.close();
  const job = BM.deep_done.jobs[0];
  assert.equal(s.lead, BM.deep_done.why);
  assert.equal(s.askHidden, false);
  assert.equal(s.jobs.length, 1);
  assert.deepEqual(s.jobs[0].tag, "done");
  assert.equal(s.jobs[0].question, job.question);
  assert.deepEqual(s.jobs[0].meta, [job.why, "Took 8 s, 1.12 words a second."]);
  assert.equal(s.jobs[0].open, true, "the newest answer is not open");
  assert.equal(s.jobs[0].answer, job.answer);
});

await check("hidden with the private lists: no question, no answer, a Show button; the state stays", async () => {
  // What Rust sends while "Hide memory lists and chat history" hides them
  // (commands.rs redact_deep): the words taken out, `hidden` set.
  const hidden = JSON.parse(JSON.stringify(BM.deep_done));
  hidden.hidden = true;
  hidden.hidden_count = hidden.jobs.length;
  for (const j of hidden.jobs) { j.question = ""; j.answer = ""; j.hidden = true; }
  const page = await brain({ status: hidden });
  const s = await plate(page);
  const show = await page.locator("#deep-jobs .private-hidden button").count();
  await page.close();
  const job = BM.deep_done.jobs[0];
  assert.equal(s.jobs[0].question, "Question hidden");
  assert.equal(s.jobs[0].tag, "done");
  assert.equal(s.jobs[0].answer, null, "an answer is offered while hidden");
  assert.ok(!s.all.includes(job.question), "the question shows while hidden");
  assert.match(s.list, /Hidden until Windows Hello confirms it is you\./);
  assert.equal(show, 1, "no Show button");
  const rs = read("src-tauri/src/commands.rs");
  const f = rs.slice(rs.indexOf("pub async fn get_deep("));
  assert.match(f.slice(0, f.indexOf("\n}\n")), /private_hidden\(&app\)[\s\S]*redact_deep\(answer\)/,
    "get_deep does not hide the words in Rust");
});

await check("failed, queued, loading, thinking: each in the backend's words, and no answer before done", async () => {
  const want = { deep_failed: ["failed", "done"], deep_queued: ["queued"],
    deep_loading: ["loading"], deep_thinking: ["thinking"] };
  for (const [name, tags] of Object.entries(want)) {
    const page = await brain({ status: BM[name] });
    const s = await plate(page);
    await page.close();
    assert.deepEqual(s.jobs.map((j) => j.tag), tags, name);
    BM[name].jobs.forEach((job, i) => {
      assert.equal(s.jobs[i].question, job.question, name);
      assert.equal(s.jobs[i].meta[0], job.why, name);
      if (job.state !== "done") assert.equal(s.jobs[i].answer, null, `${name}: an answer before done`);
    });
  }
});

await check("the answer is rendered, never injected: markup is text, links are plain, nothing runs", async () => {
  // The real deep_done, with only the answer's TEXT changed.
  const hostile = JSON.parse(JSON.stringify(BM.deep_done));
  hostile.jobs[0].answer = "Look: <img src=x onerror=\"window.__pwned=1\"> and "
    + "<script>window.__pwned=2</script>\n\n**Rayleigh** scattering, see "
    + "[the page](https://example.com/sky) or javascript:alert(1).\n\n- one\n- two\n\n"
    + "```html\n<b>not bold</b>\n```";
  const page = await brain({ status: hostile });
  await page.waitForTimeout(200);
  const got = await page.evaluate(() => {
    const body = document.querySelector("#deep-jobs .deep-answer-body");
    return {
      text: body.innerText,
      tags: [...body.querySelectorAll("*")].map((n) => n.tagName.toLowerCase()),
      pwned: window.__pwned,
      url: location.href,
    };
  });
  await page.close();
  assert.equal(got.pwned, undefined, "model text ran as script");
  for (const tag of ["img", "script", "a", "b", "iframe"]) {
    assert.ok(!got.tags.includes(tag), `a <${tag}> came from the model's text`);
  }
  assert.ok(got.tags.includes("strong") && got.tags.includes("li") && got.tags.includes("pre"),
    `Markdown was not rendered: ${got.tags}`);
  assert.match(got.text, /<img src=x onerror=/);
  assert.match(got.text, /the page \(https:\/\/example\.com\/sky\)/);
  assert.match(got.text, /<b>not bold<\/b>/);
  assert.match(got.url, /brain\.html$/);
});

await check("Ask slowly: one question, no card, the backend's words, the box cleared, the list read again", async () => {
  const page = await brain({ status: BM.deep_done, askAnswers: [BM.ask_accepted.body] });
  const before = await page.evaluate(() => window.__deep.reads);
  await page.locator("#deep-question").fill("  Why are sunsets red?  ");
  await page.locator("#deep-ask-button").click();
  await page.waitForTimeout(300);
  const s = await plate(page);
  const calls = await page.evaluate(() => window.__calls.map(([c]) => c));
  const box = await page.locator("#deep-question").inputValue();
  await page.close();
  assert.deepEqual(s.asks, ["Why are sunsets red?"]);
  assert.equal(calls.filter((c) => c === "ask_deep").length, 1);
  assert.ok(!calls.includes("decide_approval") && !calls.includes("set_big_model"),
    "asking did something else too");
  assert.equal(s.said, BM.ask_accepted.body.message);
  assert.equal(box, "");
  assert.ok(s.reads > before, "the list was not read again");
});

await check("Ctrl+Enter asks; Enter alone is a new line", async () => {
  const page = await brain({ status: BM.deep_done });
  await page.locator("#deep-question").fill("line one");
  await page.locator("#deep-question").press("Enter");
  await page.waitForTimeout(100);
  const none = await page.evaluate(() => window.__deep.asks.length);
  await page.locator("#deep-question").press("Control+Enter");
  await page.waitForTimeout(300);
  const asks = await page.evaluate(() => window.__deep.asks);
  await page.close();
  assert.equal(none, 0);
  assert.deepEqual(asks, ["line one"]);
});

await check("a refusal is the backend's sentence, and the question stays in the box", async () => {
  const page = await brain({ status: BM.deep_done, askAnswers: [BM.ask_refused_off.body] });
  await page.locator("#deep-question").fill("Why?");
  await page.locator("#deep-ask-button").click();
  await page.waitForTimeout(300);
  const s = await plate(page);
  const box = await page.locator("#deep-question").inputValue();
  const tone = await page.locator("#deep-said").getAttribute("data-tone");
  await page.close();
  assert.equal(s.said, BM.ask_refused_off.body.error);
  assert.equal(tone, "bad");
  assert.equal(box, "Why?");
});

await check("the box is capped at the backend's limit and counts as you type", async () => {
  const page = await brain({ status: BM.deep_done });
  await page.locator("#deep-question").fill("Why is the sky blue?");
  const s = await plate(page);
  await page.close();
  assert.equal(s.maxLength, BM.deep_done.limits.question_chars);
  assert.equal(s.count, "20 / 4,000 characters");
});

await check("off: no box, the backend's why, and where to turn it on", async () => {
  const page = await brain({ status: BM.deep_off });
  const s = await plate(page);
  await page.close();
  assert.equal(s.askHidden, true);
  assert.match(s.lead, /^The big-model switch is off\. To use it, open Settings/);
  assert.match(s.list, /No deep questions yet\./);
});

await check("an older backend: says to run apply-patches.ps1, and offers no box", async () => {
  const page = await brain({ status: BM.deep_off, unavailable: true });
  const s = await plate(page);
  await page.close();
  assert.equal(s.askHidden, true);
  assert.match(s.lead, /Update the backend by running apply-patches\.ps1/);
  assert.doesNotMatch(s.all, /[{}]|undefined|null/);
});

await check("Jarvis not answering: a sentence", async () => {
  const page = await brain({ status: BM.deep_done,
    getFails: "Jarvis is not answering at http://127.0.0.1:4719. Is it running?" });
  const s = await plate(page);
  await page.close();
  assert.equal(s.askHidden, true);
  assert.match(s.lead, /^Could not read the deep questions: Jarvis is not answering at/);
});

await check("a stale link greys Ask slowly (rule 4)", async () => {
  const page = await brain({ status: BM.deep_done }, { link: { stale: true } });
  const s = await plate(page);
  await page.close();
  assert.equal(s.buttonDisabled, true);
});

await check("the deep event reads the list again, so a finished answer shows without polling", async () => {
  const page = await brain({ status: BM.deep_thinking });
  const before = await plate(page);
  await page.evaluate((next) => {
    window.__deep.status = next;
    window.__emit("jarvis-event", { kind: "deep", id: 41, data: { id: "deep_000001", state: "done" } });
  }, BM.deep_done);
  await page.waitForTimeout(300);
  const after = await plate(page);
  await page.close();
  assert.equal(before.jobs[0].tag, "thinking");
  assert.equal(after.reads, before.reads + 1, "the event did not make exactly one read");
  assert.equal(after.jobs[0].tag, "done");
  assert.equal(after.jobs[0].answer, BM.deep_done.jobs[0].answer);
});

await check("the Live trace shows the deep event as an id and how it ended - never the question", async () => {
  const page = await brain({ status: BM.deep_done });
  await page.locator("#rail-advanced-toggle").click();
  await page.locator("#tab-live").click();
  await page.waitForTimeout(150);
  await page.evaluate(() => window.__emit("jarvis-event",
    { kind: "deep", id: 42, data: { id: "deep_000002", state: "failed" } }));
  await page.waitForTimeout(150);
  const rows = await page.evaluate(() => [...document.querySelectorAll("#trace li")].map((li) => ({
    kind: li.querySelector(".trace-kind")?.textContent,
    body: li.querySelector(".trace-body")?.textContent,
  })));
  await page.close();
  const mine = rows.filter((r) => r.kind === "deep");
  assert.deepEqual(mine, [{ kind: "deep", body: "question deep_000002 failed" }]);
});

await check("polls gently only while a question is going", async () => {
  assert.ok(POLL_MS >= 10000, `polls every ${POLL_MS} ms - not gentle`);
  const [going, quiet] = await Promise.all([brain({ status: BM.deep_thinking }),
    brain({ status: BM.deep_done })]);
  const a = await Promise.all([going, quiet].map((p) => p.evaluate(() => window.__deep.reads)));
  await going.waitForTimeout(POLL_MS + 800);
  const b = await Promise.all([going, quiet].map((p) => p.evaluate(() => window.__deep.reads)));
  await going.close();
  await quiet.close();
  assert.ok(b[0] - a[0] >= 1 && b[0] - a[0] <= 2, `read ${b[0] - a[0]} times while one was going`);
  assert.equal(b[1], a[1], "polled with nothing going");
});

await browser.close();
close();

/* ── Controls: the Rust ────────────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL: both commands send X-Jarvis-Client: hud and the token the usual way, to the configured backend, and log nothing", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /const JARVIS_CLIENT: &str = "hud";/);
  for (const [sig, path] of [["pub async fn get_deep(", "DEEP_PATH"], ["pub async fn ask_deep(", "DEEP_ASK_PATH"]]) {
    const body = fnBody(rust, sig);
    assert.match(body, /\.headers\(jarvis_headers\(&app\)\?\)/, `${sig} does not send the usual headers`);
    assert.ok(body.includes(`format!("{base}{${path}}")`), `${sig} builds its own URL`);
    assert.match(body, /let base = jarvis_base\(&app\);/);
    assert.doesNotMatch(body, /println!|eprintln!|log::|tracing::|dbg!/, `${sig} logs`);
    assert.doesNotMatch(body, /token/i, `${sig} touches the token itself`);
  }
  assert.match(rust, /pub\(crate\) const DEEP_PATH: &str = "\/api\/deep";/);
  assert.match(rust, /pub\(crate\) const DEEP_ASK_PATH: &str = "\/api\/deep\/ask";/);
});

await check("CONTROL: the question is built in Rust, capped at the backend's limit, and held on a stale link", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const ask = fnBody(rust, "pub async fn ask_deep(");
  assert.match(ask, /question: String\) -> Result/);
  assert.match(ask, /let question = deep_question\(&question\)\?;/);
  assert.match(ask, /\.json\(&serde_json::json!\(\{ "question": question \}\)\)/);
  const stale = ask.indexOf(".link().stale");
  const send = ask.indexOf(".send()");
  assert.ok(stale > -1 && stale < send, "asking is not held on a stale link before it is sent");
  const limit = rust.match(/pub\(crate\) const DEEP_QUESTION_CHARS: usize = (\d+);/);
  assert.ok(limit, "no cap");
  assert.equal(Number(limit[1]), BM.deep_done.limits.question_chars);
  assert.match(read("../backend/jarvis_big_model.py"), new RegExp(`^MAX_QUESTION_CHARS = ${limit[1]}$`, "m"));
  assert.match(fnBody(rust, "pub(crate) fn deep_question("), /q\.chars\(\)\.count\(\)/);
});

await check("CONTROL: only the Brain window may read or ask deep questions, and it cannot switch the big model", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  const holders = (perm) => sets.filter((s) => s.includes(`"${perm}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  for (const perm of ["allow-get-deep", "allow-ask-deep"]) {
    assert.deepEqual(holders(perm), ["brain-deep"], `${perm} is held by ${holders(perm)}`);
  }
  const deepSet = sets.find((s) => /identifier = "brain-deep"/.test(s));
  assert.doesNotMatch(deepSet, /big-model/, "brain-deep can reach the switches");
  for (const c of ["brain", "faces", "hud", "onboarding", "quickbar", "settings", "widget"]) {
    const json = read(`src-tauri/capabilities/${c}.json`);
    assert.equal(json.includes("\"brain-deep\""), c === "brain", `${c} and brain-deep`);
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const cmd of ["get_deep", "ask_deep"]) {
    assert.ok(build.includes(`"${cmd}"`), `${cmd} is not in build.rs, so no window can call it`);
    assert.ok(lib.includes(`commands::${cmd},`), `${cmd} is not registered`);
    const gen = read(`src-tauri/permissions/autogenerated/${cmd}.toml`);
    assert.match(gen, new RegExp(`commands.allow = \\["${cmd}"\\]`));
  }
});

await check("CONTROL: the deep event is named where the stream reads events, and the Brain answers it", async () => {
  const stream = read("src-tauri/src/stream.rs");
  assert.match(stream, /\n\s+"deep" => \{\}/);
  const brainJs = read("src/brain.js");
  assert.match(brainJs, /if \(kind === "deep"\) \{[\s\S]{0,200}loadDeep\(\)/);
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\ndeep questions are asked slowly, answered as text, and read again when they finish");
process.exit(fails.length ? 1 : 0);
