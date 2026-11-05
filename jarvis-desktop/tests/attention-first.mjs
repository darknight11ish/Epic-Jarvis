/**
 * Attention-first sorting in the Work pane (2026-11-04, pattern 4 of the
 * owner-forwarded `gemini_rulings_1253_and_superagent_spec_2026_11_04.md`).
 *
 * Two promises, both easy to lose in a later edit:
 *
 *  1. A job waits for a person only when a person really is what it is
 *     waiting on - an approval, a blocked/`needs_input` question, or a failure
 *     the owner has not put aside. Everything else is quiet. When the PC sends
 *     its own `waits_for_person` boolean it wins, and when it does not (every
 *     backend shipped before this slice) the same answer is DERIVED from the
 *     state, so an older PC does not make the pane look broken.
 *  2. The empty state costs ZERO pixels. No "Needs you" heading, no empty box,
 *     no reserved gap - the section is simply not created. The quiet half is
 *     ONE line until it is opened, and opening it only unfolds a list: no
 *     polling and no approval is added anywhere.
 *
 * The predicate lives in `src/attention.js`, in ONE place for this platform;
 * the truth table below is what pins it. The phone's Kotlin twin is
 * `com.jarvis.client.net.Attention`, with its own truth table in
 * `AttentionFirstTest.kt`, and both draw the same two headings.
 *
 * The DOM checks need Chromium, so they are attempted only when Playwright is
 * importable and otherwise say so - the shape the repo's own bug audit (F2,
 * 2026-10-05) asked every suite to use.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  HIDE,
  NEEDS_YOU,
  QUIET_HEALTHY,
  SHOW,
  agoWords,
  jobStatus,
  partitionJobs,
  quietSummary,
  waitsForPerson,
} from "../src/attention.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const BRAIN_JS = read("src/brain.js");
const BRAIN_CSS = read("src/brain.css");

/* ── 1. The truth table the spec gave us ─────────────────────────────────── */

await check("the three waiting states always wait for a person", () => {
  for (const state of ["waiting_approval", "blocked", "needs_input"]) {
    assert.equal(waitsForPerson({ id: "j", state }), true, state);
  }
});

await check("a failure waits unless the owner has put it aside", () => {
  assert.equal(waitsForPerson({ id: "j", state: "failed" }), true);
  assert.equal(waitsForPerson({ id: "j", state: "failed", dismissed_by_owner: false }), true);
  assert.equal(waitsForPerson({ id: "j", state: "failed", dismissed_by_owner: true }), false);
});

await check("a malformed dismissal never hides a failure", () => {
  // A string "true" is not the boolean the contract names. Showing a failure
  // the owner may already know about is the safe way to be wrong; hiding one
  // is the unsafe way, so only a real JSON true counts.
  assert.equal(waitsForPerson({ state: "failed", dismissed_by_owner: "true" }), true);
  assert.equal(waitsForPerson({ state: "failed", dismissed_by_owner: 1 }), true);
});

await check("everything else is quiet", () => {
  for (const state of ["queued", "running", "done", "cancelled", "paused", "something-new", ""]) {
    assert.equal(waitsForPerson({ id: "j", state }), false, state || "(blank)");
  }
  assert.equal(waitsForPerson({}), false);
  assert.equal(waitsForPerson(null), false);
  assert.equal(waitsForPerson(undefined), false);
  assert.equal(waitsForPerson("a job"), false);
});

await check("the server's own boolean wins when the payload carries it", () => {
  // The PC knows things this file cannot see. A server that says a running job
  // is waiting on a person (a card raised elsewhere, say) must not be
  // overridden; one that says a parked row is already handled must be trusted.
  assert.equal(waitsForPerson({ state: "running", waits_for_person: true }), true);
  assert.equal(waitsForPerson({ state: "waiting_approval", waits_for_person: false }), false);
  assert.equal(waitsForPerson({ state: "failed", waits_for_person: false }), false);
  // Anything that is not a real boolean is "no field" and falls back.
  assert.equal(waitsForPerson({ state: "waiting_approval", waits_for_person: "false" }), true);
  assert.equal(waitsForPerson({ state: "waiting_approval", waits_for_person: null }), true);
});

await check("the state is read under either name, and `state` wins", () => {
  assert.equal(jobStatus({ state: "running" }), "running");
  assert.equal(jobStatus({ status: "blocked" }), "blocked");
  assert.equal(jobStatus({ state: "running", status: "waiting_approval" }), "running");
  assert.equal(jobStatus({}), "");
  // A row with only `status` is still understood: the predicate was specified
  // in terms of `status`, and a future feed may use that name alone.
  assert.equal(waitsForPerson({ status: "needs_input" }), true);
});

/* ── 2. The split is stable ──────────────────────────────────────────────── */

await check("the split keeps the payload's own order on BOTH sides", () => {
  const jobs = [
    { id: "a", state: "running" },
    { id: "b", state: "waiting_approval" },
    { id: "c", state: "done" },
    { id: "d", state: "failed" },
    { id: "e", state: "queued" },
    { id: "f", state: "blocked" },
  ];
  const { needs, quiet } = partitionJobs(jobs);
  assert.deepEqual(needs.map((j) => j.id), ["b", "d", "f"]);
  assert.deepEqual(quiet.map((j) => j.id), ["a", "c", "e"]);
  // Same answer twice: a re-read of the same list must not reorder rows.
  assert.deepEqual(partitionJobs(jobs), partitionJobs(jobs));
});

await check("a body with no list is two empty sections, not a crash", () => {
  for (const value of [null, undefined, {}, "jobs"]) {
    const { needs, quiet } = partitionJobs(value);
    assert.deepEqual(needs, []);
    assert.deepEqual(quiet, []);
  }
});

/* ── 3. The one-line quiet summary ───────────────────────────────────────── */

await check("no quiet jobs means no bar at all", () => {
  assert.equal(quietSummary([]), "");
  assert.equal(quietSummary(null), "");
});

await check("the summary names the section, the count and only real facts", () => {
  assert.equal(
    quietSummary([{ id: "a", state: "running" }], 1000),
    `${QUIET_HEALTHY} · 1 background job — 1 still running`,
  );
  assert.equal(
    quietSummary([{ state: "running" }, { state: "done" }], 1000),
    `${QUIET_HEALTHY} · 2 background jobs — 1 still running, 1 finished`,
  );
  // A queued job has not started; it is still "still running" in plain words
  // because it is work in flight, and it must not be called finished.
  assert.equal(
    quietSummary([{ state: "queued" }], 1000),
    `${QUIET_HEALTHY} · 1 background job — 1 still running`,
  );
});

await check("the last finish is shown, and nothing is invented when it is absent", () => {
  const now = 10_000;
  const jobs = [
    { state: "done", finished: now - 600 },
    { state: "done", finished: now - 120 },
    { state: "running" },
  ];
  assert.equal(
    quietSummary(jobs, now),
    `${QUIET_HEALTHY} · 3 background jobs — 1 still running, 2 finished · last finished 2m ago`,
  );
  // No `finished` on any row: the sentence stops after the counts.
  assert.equal(
    quietSummary([{ state: "running" }], now),
    `${QUIET_HEALTHY} · 1 background job — 1 still running`,
  );
});

await check("a dismissed failure is still counted, in plain words", () => {
  assert.equal(
    quietSummary([{ state: "failed", dismissed_by_owner: true, finished: 940 }], 1000),
    `${QUIET_HEALTHY} · 1 background job — 1 failed · last finished 1m ago`,
  );
});

await check("ages are whole words and never negative", () => {
  assert.equal(agoWords(0, 1000), "");
  assert.equal(agoWords(-5, 1000), "");
  assert.equal(agoWords("nope", 1000), "");
  assert.equal(agoWords(995, 1000), "just now");
  assert.equal(agoWords(980, 1000), "just now");
  assert.equal(agoWords(1_000_000 - 60, 1_000_000), "1m ago");
  assert.equal(agoWords(1_000_000 - 3600, 1_000_000), "1h ago");
  assert.equal(agoWords(1_000_000 - 86400, 1_000_000), "1d ago");
  // A clock behind the payload (this PC's clock can lag) reads "just now",
  // never "-3m ago".
  assert.equal(agoWords(2000, 1000), "just now");
});

/* ── 4. The page draws it, and only where it belongs ─────────────────────── */

await check("the Work pane imports the ONE predicate, and partitions with it", () => {
  assert.match(BRAIN_JS, /from "\.\/attention\.js"/);
  assert.match(BRAIN_JS, /partitionJobs\(list\)/,
    "renderJobs must split with the shared predicate, not its own copy");
  // No second copy of the state list on the page.
  for (const state of ["waiting_approval", "needs_input"]) {
    assert.ok(!BRAIN_JS.includes(`"${state}", "blocked"`),
      `the state list is copied into brain.js (${state})`);
  }
});

await check("the Needs-you section is CONDITIONAL, so an empty one is zero pixels", () => {
  const fn = BRAIN_JS.slice(BRAIN_JS.indexOf("function renderNeedsYou("));
  const body = fn.slice(0, fn.indexOf("\nfunction renderQuietBar("));
  assert.ok(body.length > 0, "renderNeedsYou is missing");
  assert.match(body, /attention-head/);
  const jobs = BRAIN_JS.slice(BRAIN_JS.indexOf("function renderJobs("));
  const render = jobs.slice(0, jobs.indexOf("\nfunction renderUndo("));
  assert.match(render, /if \(needs\.length\) dom\.jobs\.append\(renderNeedsYou\(/,
    "the section must only be created when it has a row");
  assert.ok(!/else\s*\{[^}]*renderNeedsYou/.test(render),
    "there must be no empty-state branch for the needs section");
  // The old unconditional list is gone: `rows(dom.jobs, list, ...)` painted
  // "No background jobs." for an empty list, which is the empty box the spec
  // forbids. The remaining `rows()` call is the UNAVAILABLE branch, where the
  // PC has no job route at all - a different fact, said in its own words.
  assert.ok(!/rows\(\s*dom\.jobs,\s*list,/.test(render),
    "renderJobs still paints the job list through rows(), which always emits a node");
});

await check("the quiet half is ONE collapsed line that opens on a click", () => {
  const fn = BRAIN_JS.slice(BRAIN_JS.indexOf("function renderQuietBar("));
  const body = fn.slice(0, fn.indexOf("\nfunction renderJobs("));
  assert.ok(body.length > 0, "renderQuietBar is missing");
  assert.match(body, /quietSummary\(jobs\)/);
  assert.match(body, /bar\.setAttribute\("aria-expanded", "false"\)/,
    "the bar must start closed, and say so to a screen reader");
  assert.match(body, /list\.hidden = true/,
    "the full list must be hidden until the bar is clicked");
  assert.match(body, /addEventListener\("click"/);
  // The two words are the shared constants, imported above - not a second
  // copy of "Show"/"Hide" typed into the page.
  assert.match(body, /\bSHOW\b/);
  assert.match(body, /\bHIDE\b/);
  // Folding a list must never reach the server.
  for (const banned of ["invoke(", "fetch(", "await ", "setInterval", "setTimeout"]) {
    assert.ok(!body.includes(banned), `the quiet bar does ${banned}`);
  }
});

await check("the quiet bar is one line in CSS, and the needs block reserves no room", () => {
  const quiet = BRAIN_CSS.slice(BRAIN_CSS.indexOf(".quiet-words {"));
  const words = quiet.slice(0, quiet.indexOf("}"));
  assert.match(words, /white-space:\s*nowrap/);
  assert.match(words, /text-overflow:\s*ellipsis/);
  assert.match(words, /overflow:\s*hidden/);
  const needs = BRAIN_CSS.slice(BRAIN_CSS.indexOf(".attention-needs {"));
  const block = needs.slice(0, needs.indexOf("}"));
  assert.ok(!/min-height|padding|border/.test(block),
    "the needs block must not draw a box when it has nothing in it");
});

await check("nothing in this feature reaches an approval route or adds polling", () => {
  for (const banned of ["/api/approve", "/api/deny", "brain_approve", "answer_approval"]) {
    assert.ok(!BRAIN_JS.includes(banned), `brain.js reaches ${banned}`);
  }
  // The two new renderers only build nodes; a polling loop would live here.
  for (const name of ["function renderNeedsYou(", "function renderQuietBar("]) {
    const fn = BRAIN_JS.slice(BRAIN_JS.indexOf(name));
    const body = fn.slice(0, fn.indexOf("\n}\n"));
    assert.ok(!/setInterval|setTimeout/.test(body), `${name} starts a timer`);
  }
});

await check("the two headings are the spec's words", () => {
  assert.equal(NEEDS_YOU, "Needs you");
  assert.equal(QUIET_HEALTHY, "Quiet / healthy");
  assert.equal(SHOW, "Show");
  assert.equal(HIDE, "Hide");
});

/* ── 5. The DOM, when a browser is available ─────────────────────────────── */

let playwright = null;
try {
  playwright = await import("playwright");
} catch {
  console.log("\n      (the DOM checks need Playwright; skipping them here - they run in CI)");
}

if (playwright) {
  const K = await import("./uikit.mjs");
  const { base, close } = await K.serve();
  const browser = await K.launch();

  const TASKS = { available: true, tasks: [], waiting: 0, running: 0, blocked: 0, stop: false };
  const TICKING = { handlers: ["watch_github"], pending_grants: 0 };

  /**
   * One page, opened on the Work tab. A payload with a NEEDS row and a quiet
   * row on each side of it proves the split and the order.
   */
  const MIXED = {
    available: true,
    ticking: true,
    status: TICKING,
    grants: [],
    jobs: [
      { id: "q1", label: "nightly backup", state: "done", finished: 1 },
      { id: "n1", label: "ask about the email", state: "waiting_approval", created: 1 },
      { id: "q2", label: "watch the repo", state: "running", created: 1 },
    ],
  };
  const page = await K.open(browser, base, "brain.html",
    { brain: { ...K.BRAIN, jobs: MIXED, tasks: TASKS } },
    { width: 900, height: 1400 });
  await page.locator("#tab-work").click();
  await page.locator(".quiet-bar").waitFor({ timeout: 10000 });

  await check("a job that waits for a person is drawn first, under Needs you", async () => {
    const head = await page.locator(".attention-head").first().innerText();
    assert.match(head, /needs you/i, head);
    const needs = page.locator(".attention-needs .row-item");
    assert.equal(await needs.count(), 1, "one needs-you job, not the whole list");
    assert.match(await needs.first().innerText(), /ask about the email/);
  });

  await check("a quiet job is NOT drawn expanded until the bar is clicked", async () => {
    assert.equal(await page.locator(".quiet-list .row-item").count(), 2,
      "both quiet rows are built");
    assert.ok(await page.locator(".quiet-list").isHidden(),
      "the quiet list must be folded away on first draw");
    assert.equal(await page.locator(".quiet-bar").getAttribute("aria-expanded"), "false");
    const bar = await page.locator(".quiet-bar").innerText();
    assert.match(bar, /Quiet \/ healthy/i, bar);
    assert.match(bar, /2 background jobs/i, bar);
    assert.match(bar, /1 still running, 1 finished/i, bar);
    // ONE line, enforced by CSS rather than by the words being short.
    const nowrap = await page.locator(".quiet-words").evaluate(
      (n) => getComputedStyle(n).whiteSpace);
    assert.equal(nowrap, "nowrap");
  });

  await check("clicking the bar opens the list and sends nothing", async () => {
    const before = await page.evaluate(() => window.__calls.length);
    await page.locator(".quiet-bar").click();
    await page.waitForFunction(
      () => document.querySelector(".quiet-bar").getAttribute("aria-expanded") === "true");
    assert.ok(await page.locator(".quiet-list").isVisible());
    assert.equal(await page.locator(".quiet-bar").getAttribute("aria-expanded"), "true");
    assert.match(await page.locator(".quiet-bar").innerText(), /hide/i);
    const after = await page.evaluate(() => window.__calls.length);
    assert.equal(after, before, "opening a list on this PC must not call the server");
    // Close it again: the state is the owner's click, nothing else.
    await page.locator(".quiet-bar").click();
    await page.waitForFunction(
      () => document.querySelector(".quiet-bar").getAttribute("aria-expanded") === "false");
    assert.ok(await page.locator(".quiet-list").isHidden());
  });

  await check("no approval control appears anywhere in the jobs card", async () => {
    const buttons = await page.locator("#jobs button").allTextContents();
    assert.ok(!buttons.some((b) => /\bapprove\b|\bdeny\b/i.test(b)), buttons.join(","));
  });

  await page.close();

  /* Zero pixels: a backend answer with nothing waiting for the owner. */
  const QUIET_ONLY = {
    available: true,
    ticking: true,
    status: TICKING,
    grants: [],
    jobs: [
      { id: "q1", label: "nightly backup", state: "done", finished: 1 },
      { id: "q2", label: "watch the repo", state: "running", created: 1 },
    ],
  };
  const quietPage = await K.open(browser, base, "brain.html",
    { brain: { ...K.BRAIN, jobs: QUIET_ONLY, tasks: TASKS } },
    { width: 900, height: 1400 });
  await quietPage.locator("#tab-work").click();
  await quietPage.locator(".quiet-bar").waitFor({ timeout: 10000 });

  await check("with nothing waiting, Needs you is ZERO pixels (not one)", async () => {
    assert.equal(await quietPage.locator(".attention-needs").count(), 0,
      "the whole section must be absent from the DOM");
    assert.equal(await quietPage.locator(".attention-head").count(), 0,
      "the heading must not be drawn");
    // And no empty-state box took its place: the next node after the form is
    // the quiet bar.
    const order = await quietPage.locator("#jobs > *").evaluateAll(
      (nodes) => nodes.map((n) => n.className));
    assert.equal(order[0], "job-start", order.join(" | "));
    assert.equal(order[1], "attention-quiet", order.join(" | "));
    // The section really occupies no room: it is not in the document at all,
    // and there is no placeholder node holding its place.
    const needsNode = await quietPage.evaluate(
      () => document.querySelector(".attention-needs") !== null);
    assert.equal(needsNode, false, "an empty Needs-you section must not be in the DOM");
  });

  await check("the quiet bar is still the one line, and still closed", async () => {
    const bar = await quietPage.locator(".quiet-bar").innerText();
    assert.match(bar, /Quiet \/ healthy · 2 background jobs/i, bar);
    assert.ok(await quietPage.locator(".quiet-list").isHidden());
  });

  await quietPage.close();

  /* An older PC: the jobs already carry no `waits_for_person` field at all. */
  const OLD = {
    available: true,
    ticking: true,
    status: TICKING,
    grants: [],
    jobs: [{ id: "n1", label: "ask about the email", state: "waiting_approval", created: 1 }],
  };
  const oldPage = await K.open(browser, base, "brain.html",
    { brain: { ...K.BRAIN, jobs: OLD, tasks: TASKS } },
    { width: 900, height: 1400 });
  await oldPage.locator("#tab-work").click();
  await oldPage.locator(".attention-head").waitFor({ timeout: 10000 });

  await check("a body with no waits_for_person still lands in Needs you", async () => {
    assert.equal(await oldPage.locator(".attention-needs .row-item").count(), 1);
    assert.equal(await oldPage.locator(".attention-quiet").count(), 0,
      "one parked job leaves nothing quiet, so there is no bar either");
  });

  await oldPage.close();

  await browser.close();
  await close();
}

console.log(`\n${fails.length ? "FAILED" : "ok"} - ${fails.length} failed`);
if (fails.length) {
  console.log(fails.map((f) => `  - ${f}`).join("\n"));
  process.exit(1);
}
