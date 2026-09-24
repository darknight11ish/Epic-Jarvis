/**
 * The wiki builder's plate on the Brain's Memory tab - backend/wiki.patch.
 *
 * Every answer here is the backend's own: tests/fixtures/wiki-cases.json is
 * written by tools/gen_wiki_cases.py from backend/jarvis_wiki.py itself, and
 * backend/test_wiki.py fails when it is stale. So the plate is tested
 * against what the PC really sends, not against shapes this file invented.
 *
 * Two halves, like notes.mjs: the plate's logic (src/wiki.js) on its own,
 * then the Brain window in a real browser, with the bridge from uikit.mjs
 * and the wiki commands answering from the fixture.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { addToWiki, canAdd, describeJob, readWiki, STATES } from "../src/wiki.js";
import * as K from "./uikit.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(fs.readFileSync(path.join(HERE, "fixtures", "wiki-cases.json"),
  "utf8")).cases;
const body = (name) => CASES[name].body;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The plate's logic, against the backend's real answers ─────────────── */

await check("the ready answer is read as the PC sent it", async () => {
  const v = readWiki(body("status_ready"));
  assert.equal(v.available, true);
  assert.equal(v.folderOk, true);
  assert.equal(v.pages, 1);
  assert.deepEqual(v.sources.map((s) => [s.name, s.state]), [
    ["old-minutes.md", "too_big"], ["planting-dates.md", "changed"],
    ["plot-map.pdf", "unreadable"], ["seed-list.txt", "in_wiki"],
    ["spring-meeting.md", "new"]]);
  assert.deepEqual(v.recent, ["## [2026-09-20] ingest | seed-list.txt"]);
  for (const s of v.sources) assert.ok(STATES[s.state], `no words for state ${s.state}`);
});

await check("Add is offered for new and changed only, and only when it can run", async () => {
  const v = readWiki(body("status_ready"));
  const offered = v.sources.filter((s) => canAdd(v, s)).map((s) => s.name);
  assert.deepEqual(offered, ["planting-dates.md", "spring-meeting.md"]);
  const off = readWiki(body("status_off"));
  assert.deepEqual(off.sources.filter((s) => canAdd(off, s)), [], "offered while off");
  const busy = readWiki(body("status_running"));
  assert.deepEqual(busy.sources.filter((s) => canAdd(busy, s)), [], "offered while one runs");
});

await check("every job state is said in the PC's words, and only done reads as done", async () => {
  const want = {
    job_reading: [null, false], job_waiting: [null, false], job_done: ["ok", true],
    job_denied: ["bad", true], job_failed: ["bad", true], job_model_refused: ["bad", true],
  };
  for (const [name, [tone, final]] of Object.entries(want)) {
    const d = describeJob(body(name));
    assert.equal(d.tone, tone, name);
    assert.equal(d.final, final, name);
    assert.equal(d.text, body(name).message, name);
  }
  for (const name of ["ingest_in_wiki", "ingest_busy", "ingest_off", "ingest_too_big",
                      "ingest_unreadable"]) {
    const d = describeJob(body(name));
    assert.equal(d.text, body(name).error, name);
    assert.equal(d.tone, "bad", name);
  }
  assert.equal(describeJob({ state: "weird", message: "Added!" }).tone, "bad");
});

await check("a job is followed until it ends", async () => {
  const answers = [body("ingest_started"), body("job_waiting"), body("job_done")];
  const calls = [];
  const invoke = async (cmd, args) => { calls.push([cmd, args]); return answers.shift(); };
  const seen = [];
  const last = await addToWiki(invoke, "spring-meeting.md", (d) => seen.push(d.text),
    { pollMs: 1 });
  assert.deepEqual(calls.map((c) => c[0]), ["wiki_ingest", "wiki_ingest_status",
                                           "wiki_ingest_status"]);
  assert.deepEqual(calls[0][1], { source: "spring-meeting.md" });
  assert.deepEqual(calls[1][1], { id: body("ingest_started").id });
  assert.equal(last.tone, "ok");
  assert.match(seen[1], /Waiting for your approval/);
});

// CONN-8 (audit 3): the follow ended for good at the first failed poll.
await check("one or two failed polls in a row are retried; the follow goes on to the end", async () => {
  const answers = [body("ingest_started"), new Error("timed out"), new Error("timed out"),
                   body("job_waiting"), new Error("reset"), body("job_done")];
  const calls = [];
  const invoke = async (cmd) => {
    calls.push(cmd);
    const next = answers.shift();
    if (next instanceof Error) throw next;
    return next;
  };
  const seen = [];
  const last = await addToWiki(invoke, "x.md", (d) => seen.push(d), { pollMs: 1 });
  assert.equal(calls.length, 6, JSON.stringify(calls));
  assert.equal(last.tone, "ok", `the follow did not reach the end: ${last.text}`);
  const retry = seen.find((d) => /Trying again/.test(d.text));
  assert.ok(retry && retry.final === false && retry.tone !== "bad", JSON.stringify(seen));
});

await check("CONTROL: three failed polls in a row do end it, and say so", async () => {
  const answers = [body("ingest_started"), new Error("a"), new Error("b"), new Error("c"),
                   body("job_done")];
  const invoke = async () => {
    const next = answers.shift();
    if (next instanceof Error) throw next;
    return next;
  };
  const last = await addToWiki(invoke, "x.md", () => {}, { pollMs: 1 });
  assert.equal(last.final, true);
  assert.equal(last.tone, "bad");
  assert.match(last.text, /Lost track of it \(c\)/);
  assert.equal(answers.length, 1, "it kept polling after the third failure");
});

await check("while the link is down no poll is sent, nothing is counted, and the follow resumes", async () => {
  const answers = [body("ingest_started"), body("job_waiting"), body("job_done")];
  const calls = [];
  const invoke = async (cmd) => { calls.push(cmd); return answers.shift(); };
  let ticks = 0;
  // Down for the first ten ticks - far more than three - then back.
  const linkDown = () => ++ticks <= 10;
  const seen = [];
  const last = await addToWiki(invoke, "x.md", (d) => seen.push(d), { pollMs: 1, linkDown });
  assert.deepEqual(calls, ["wiki_ingest", "wiki_ingest_status", "wiki_ingest_status"],
    "a poll was sent while the link was down");
  assert.equal(last.tone, "ok");
  assert.equal(seen.filter((d) => /link to the PC/.test(d.text)).length, 1,
    "the link line was said more than once, or never");
});

await check("CONTROL: the Brain tells the follow when the link is down", async () => {
  const brainJs = fs.readFileSync(path.join(HERE, "..", "src", "brain.js"), "utf8");
  assert.match(brainJs, /addToWiki\(invoke, source, [\s\S]*?\{ linkDown: \(\) => !currentLink\(\)\.connected \}\)/);
});

await check("giving up says nothing is written, not that it was", async () => {
  const invoke = async () => body("job_waiting");
  const last = await addToWiki(invoke, "x.md", () => {}, { pollMs: 1, giveUpMs: 5 });
  assert.match(last.text, /Nothing is written until you approve/);
  assert.notEqual(last.tone, "ok");
});

/* ── The Brain window, in a browser ───────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1400 };

/**
 * Opens brain.html with the wiki commands answering from the fixture:
 * `status` names the GET case, `jobs` the POST answer then each status poll.
 * Registered after uikit's bridge and applied by a reload, so uikit.mjs
 * itself is untouched.
 */
async function brain(status, jobs = [], data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.addInitScript(({ statusBody, jobBodies }) => {
    const inner = window.__TAURI__.core.invoke;
    const queue = [...jobBodies];
    window.__wikiCalls = [];
    window.__TAURI__.core.invoke = async (cmd, args) => {
      if (!String(cmd).startsWith("wiki_")) return inner(cmd, args);
      window.__wikiCalls.push([cmd, args]);
      if (cmd === "wiki_status") return statusBody;
      if (cmd === "wiki_open_folder") return null;
      return queue.length > 1 ? queue.shift() : queue[0];
    };
  }, { statusBody: body(status), jobBodies: jobs.map(body) });
  await page.reload();
  await page.waitForTimeout(600);
  return page;
}

const addButtons = (page) => page.evaluate(() =>
  [...document.querySelectorAll("#wiki .row-item")]
    .filter((r) => [...r.querySelectorAll("button")].some((b) => b.textContent === "Add to wiki"))
    .map((r) => r.querySelector(".row-title").textContent));

await check("ready: every source with its state, Add on new and changed only", async () => {
  const page = await brain("status_ready");
  const rows = await page.evaluate(() => [...document.querySelectorAll("#wiki .row-item")]
    .map((r) => [r.querySelector(".row-title").textContent,
                 r.querySelector(".row-tag").textContent]));
  const adds = await addButtons(page);
  const lead = await page.locator("#wiki .wiki-state").innerText();
  const recent = await page.locator("#wiki .wiki-recent").innerText();
  const open = await page.locator("#wiki button", { hasText: "Open the wiki folder" }).count();
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(rows, [["old-minutes.md", "too big"], ["planting-dates.md", "changed"],
                          ["plot-map.pdf", "can't read"], ["seed-list.txt", "in wiki"],
                          ["spring-meeting.md", "new"]]);
  assert.deepEqual(adds, ["planting-dates.md", "spring-meeting.md"]);
  assert.match(lead, /^Ready: Wiki builder: qwen3:14b/);
  assert.match(recent, /\[2026-09-20\] ingest \| seed-list\.txt/);
  assert.equal(open, 1);
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await check("off: the reason, the list, and no Add anywhere", async () => {
  const page = await brain("status_off");
  const lead = await page.locator("#wiki .wiki-state").innerText();
  const adds = await addButtons(page);
  await page.close();
  assert.match(lead, /runs only on the second graphics card/);
  assert.deepEqual(adds, []);
});

await check("no wiki folder yet: says what to make", async () => {
  const page = await brain("status_no_wiki_folder");
  const text = await page.locator("#wiki").innerText();
  await page.close();
  assert.match(text, /Make a folder called "Jarvis Wiki" in your Obsidian vault/);
});

await check("Add to wiki: raises the card, follows it, says done in the PC's words", async () => {
  const page = await brain("status_ready", ["ingest_started", "job_waiting", "job_done"]);
  await page.locator("#wiki .row-item", { hasText: "spring-meeting.md" })
    .getByRole("button", { name: "Add to wiki" }).click();
  await page.waitForTimeout(400);
  const during = await page.locator("#wiki .wiki-job").innerText();
  await page.waitForFunction(() => /Added/.test(
    (document.querySelector("#wiki .wiki-job") || {}).textContent || ""), null, { timeout: 12000 });
  const after = await page.locator("#wiki .wiki-job").innerText();
  const calls = await page.evaluate(() => window.__wikiCalls.map((c) => c[0]));
  const sent = await page.evaluate(() => window.__wikiCalls.find((c) => c[0] === "wiki_ingest")[1]);
  await page.close();
  assert.deepEqual(sent, { source: "spring-meeting.md" });
  assert.match(during, /spring-meeting\.md: (The model|Waiting for your approval)/);
  assert.match(after, /Added "spring-meeting\.md" to the wiki: 1 new page, 1 changed\./);
  assert.ok(calls.filter((c) => c === "wiki_ingest").length === 1, "asked twice");
});

await check("a refused add says why and does not claim anything was added", async () => {
  const page = await brain("status_ready", ["ingest_started", "job_denied"]);
  await page.locator("#wiki .row-item", { hasText: "planting-dates.md" })
    .getByRole("button", { name: "Add to wiki" }).click();
  await page.waitForFunction(() => /said no/.test(
    (document.querySelector("#wiki .wiki-job") || {}).textContent || ""), null, { timeout: 12000 });
  const line = page.locator("#wiki .wiki-job");
  const text = await line.innerText();
  const tone = await line.getAttribute("data-tone");
  await page.close();
  assert.match(text, /You said no, so nothing was written\./);
  assert.equal(tone, "bad");
});

await check("a stale link greys Add to wiki (rule 4)", async () => {
  const page = await brain("status_ready", [], { link: { stale: true } });
  const disabled = await page.locator("#wiki button", { hasText: "Add to wiki" })
    .evaluateAll((bs) => bs.map((b) => b.disabled));
  await page.close();
  assert.ok(disabled.length === 2 && disabled.every(Boolean), JSON.stringify(disabled));
});

await check("Open the wiki folder asks Rust, never with a path from the page", async () => {
  const page = await brain("status_ready");
  await page.getByRole("button", { name: "Open the wiki folder" }).click();
  await page.waitForTimeout(200);
  const call = await page.evaluate(() => window.__wikiCalls.find((c) => c[0] === "wiki_open_folder"));
  await page.close();
  assert.ok(call, "wiki_open_folder was not called");
  assert.ok(!call[1] || Object.keys(call[1]).length === 0, JSON.stringify(call[1]));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe wiki plate shows only what the PC said, and asks before anything is written");
process.exit(fails.length ? 1 : 0);
