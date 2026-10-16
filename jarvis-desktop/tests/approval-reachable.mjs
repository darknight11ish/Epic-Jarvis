/**
 * The card opened from a notification must be READABLE and ANSWERABLE in the
 * Jarvis bar.
 *
 * The owner's report, 2026-10-16: "when i click open the card from the
 * notification, it opens the jarvis bar with no additional information. it
 * should open the card itself." The screenshot with it shows the bar exactly
 * one input row tall floating over the HUD's card, with the card's own buttons
 * absent there and its Approve and Deny out of reach here.
 *
 * The mechanism, measured by these checks rather than assumed: Rust collapses
 * the quickbar to its base height every time it is summoned from hidden
 * (`windows.rs`, `QUICKBAR_BASE_HEIGHT` = 80, `show_quickbar_unlocked`) and
 * then emits `focus-input`; the page answers by asking Rust to size the window
 * to what it measures (`main.js` `syncWindowHeight` -> `resize_quickbar`).
 * `.shell { max-height: 100vh }` capped that measurement at the window's OWN
 * height, so the page reported 80 back to Rust, Rust set 80, and the loop
 * stopped there: the card below the input row - and the sticky footer holding
 * Approve and Deny - sat outside an 80px window, and the stack's scroller had
 * no height left to scroll in, so it could not be reached by scrolling either.
 *
 * **Why no other suite caught it.** Every other test opens the page at a fixed
 * viewport and leaves it there, so `.shell` is free to measure its content and
 * the bar looks like it grows. This one drives the loop the way Rust does:
 * whatever the page asks for, the viewport is set to it, clamped to the same
 * 80..720 the Rust command clamps to. On the unfixed tree the only height the
 * page ever asks for is 80.
 *
 *   node tests/approval-reachable.mjs      (needs Playwright, like the others)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const RUST = join(HERE, "..", "src-tauri", "src");
const BASE = 80;   // windows.rs QUICKBAR_BASE_HEIGHT
const CLAMP = 720; // windows.rs QUICKBAR_MAX_HEIGHT

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/**
 * A card taller than the window's clamp: a long plan, a raise, four options
 * and a body that wraps. Measured at 720px of shell with 747px of stack
 * content - the clamp binding, so the stack carries the rest.
 *
 * It carries options on purpose: a card with options decides by the options
 * (the static Approve is hidden then, by design), so the buttons this check
 * holds to account are Deny and the options themselves.
 */
const TALL = {
  ...K.APPROVAL_WITH_OPTIONS,
  id: "tall1",
  raised: K.RAISED,
  options: [
    ...K.APPROVAL_WITH_OPTIONS.options,
    { id: "opt_third", label: "Wait for the supplier to answer", summary: "3 steps: a, b, c.", weight: "normal" },
    { id: "opt_fourth", label: "Escalate it and ask for a refund", summary: "4 steps: a, b, c, d.", weight: "heavy" },
  ],
  notice: { title: "Jarvis wants to reply to the support chat", weight: "heavy", deny_ok: true, approve_ok: false,
            body: "A long body line that wraps over a couple of lines because it keeps going and going and going." },
  detail: JSON.stringify({
    text: Array.from({ length: 40 }, (_, i) => `Step ${i + 1}: read the page and act on it.`).join("\n"),
  }),
};

/** Every height the page has asked Rust for, in order. */
const asks = (page) => page.evaluate(() =>
  window.__calls.filter((c) => c[0] === "resize_quickbar").map((c) => c[1].height));

/** The bar as a person meets it: what is inside the window, and what a click
 *  at the centre of a control actually lands on. */
const seen = (page) => page.evaluate(() => {
  const box = (sel) => {
    const el = document.querySelector(sel);
    if (!el || el.closest("[hidden]") || el.hidden) return null;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    return { top: Math.round(r.top), bottom: Math.round(r.bottom) };
  };
  const lands = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return "no element";
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return "not drawn";
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (hit === el || el.contains(hit)) return true;
    return hit ? (hit.id || hit.className || hit.tagName) : "nothing (outside the window)";
  };
  const stack = document.querySelector("#stack");
  const shell = document.querySelector("#shell").getBoundingClientRect();
  return {
    viewport: window.innerHeight,
    shell: { top: Math.round(shell.top), bottom: Math.round(shell.bottom) },
    card: box("#approval"),
    approve: box("#approval-approve"),
    approveHidden: document.querySelector("#approval-approve").hidden,
    deny: box("#approval-deny"),
    approveLands: lands("#approval-approve"),
    denyLands: lands("#approval-deny"),
    optionLands: lands("#approval-options button"),
    stack: { scrollHeight: stack.scrollHeight, clientHeight: stack.clientHeight },
    actions: box(".approval-actions"),
  };
});

const inside = (rect, viewport) => rect && rect.top >= 0 && rect.bottom <= viewport;

/**
 * Rust's half of the loop: `resize_quickbar` clamps what the page asked for to
 * 80..720 and sets the window to it, and the page then measures again because
 * the viewport changed. Returns every height asked for, and where it settled.
 */
async function rustSizesTheBar(page, rounds = 6) {
  let heights = await asks(page);
  for (let i = 0; i < rounds; i++) {
    const want = Math.max(BASE, Math.min(CLAMP, Math.ceil(heights[heights.length - 1] || BASE)));
    const now = await page.evaluate(() => window.innerHeight);
    if (want === now) return { asked: heights, settled: now, rounds: i };
    await page.setViewportSize({ width: 750, height: want });
    await page.waitForTimeout(300);
    heights = await asks(page);
  }
  return { asked: heights, settled: await page.evaluate(() => window.innerHeight), rounds };
}

/** A bar summoned from hidden: Rust has just collapsed it to BASE and told the
 *  page it is on screen. Every check starts here, because that is where the
 *  owner's card arrives. */
async function summonedBar(page) {
  await page.evaluate(() => window.__emit("focus-input", {}));
  await page.waitForTimeout(400);
  return rustSizesTheBar(page);
}

/* ── The card the owner could not see ────────────────────────────────────── */

await check("a summoned bar grows to the card it was opened for", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: [K.APPROVAL_PLAIN], attention: K.ATTENTION_CLEAR },
    { width: 750, height: BASE });
  const { asked, settled } = await summonedBar(page);
  const out = await seen(page);
  await page.close();

  assert.ok(asked.some((h) => h > BASE),
    `the bar never asked to be taller than its base height (asks: ${JSON.stringify(asked)})`);
  assert.ok(out.card, "the approval card is not on screen at all");
  assert.ok(inside(out.card, out.viewport),
    `the card runs past the window: it ends at ${out.card.bottom}, the window is ${out.viewport}`);
  assert.equal(settled, out.viewport, "the loop did not settle");
  assert.ok(out.viewport > BASE,
    `the window is still one input row tall (${out.viewport}px) with a card waiting`);
});

await check("Approve and Deny can actually be clicked, not just drawn", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: [K.APPROVAL_PLAIN], attention: K.ATTENTION_CLEAR },
    { width: 750, height: BASE });
  await summonedBar(page);
  const out = await seen(page);
  await page.close();

  for (const [what, rect, land] of [
    ["Approve", out.approve, out.approveLands],
    ["Deny", out.deny, out.denyLands],
  ]) {
    assert.ok(rect, `${what} is not drawn`);
    assert.ok(inside(rect, out.viewport),
      `${what} is outside the window (${rect.top}..${rect.bottom} of ${out.viewport}) - nothing can press it`);
    assert.equal(land, true, `a click at the centre of ${what} lands on ${land}, not the button`);
  }
  assert.ok(inside(out.actions, out.viewport), "the decision row is outside the window");
});

/* ── The clamp still does its job ────────────────────────────────────────── */

await check("a card taller than the clamp scrolls, and its controls stay on screen", async () => {
  // The reason the cap exists at all (style.css): past 720 the stack must
  // scroll INSIDE the window rather than pushing the decision past the cut.
  // Growing the window is the fix for the small case; this is the check that
  // the tall case did not become the price of it.
  const page = await K.open(browser, base, "index.html",
    { pending: [TALL], attention: K.ATTENTION_CLEAR },
    { width: 750, height: BASE });
  const { settled } = await summonedBar(page);
  const out = await seen(page);
  await page.close();

  assert.equal(settled, CLAMP, `a card taller than the clamp settled at ${settled}, not ${CLAMP}`);
  assert.ok(out.stack.scrollHeight > out.stack.clientHeight,
    "the stack is not scrolling, so the hidden part of the card cannot be reached");
  assert.ok(inside(out.actions, out.viewport),
    `the decision row is below the window (${out.actions.bottom} of ${out.viewport})`);
  assert.ok(out.deny && inside(out.deny, out.viewport), "Deny is outside the window");
  assert.equal(out.denyLands, true, `a click at the centre of Deny lands on ${out.denyLands}`);
  assert.equal(out.optionLands, true,
    `a click at the centre of the first option lands on ${out.optionLands}`);
  assert.equal(out.approveHidden, true,
    "a card with options shows the static Approve as well, which is not how this card decides");
});

/* ── The empty bar is still sized to itself ──────────────────────────────── */

await check("CONTROL: with nothing waiting, the bar is its own content, not the clamp", async () => {
  // The fix must not turn "grow to fit" into "ask for the maximum": the bar's
  // empty state (the primer) is 632px of content, and it should be exactly
  // that - and the card must not be on screen at all.
  const page = await K.open(browser, base, "index.html",
    { pending: [], attention: K.ATTENTION_CLEAR }, { width: 750, height: BASE });
  const { asked, settled } = await summonedBar(page);
  const out = await seen(page);
  await page.close();

  assert.equal(out.card, null, "a card is on screen with nothing waiting");
  assert.ok(settled < CLAMP, `the empty bar asked for the clamp (${settled})`);
  assert.ok(out.shell.bottom <= out.viewport,
    `the bar's own content is clipped (${out.shell.bottom} of ${out.viewport})`);
  assert.ok(asked.some((h) => h > BASE), "the primer is taller than the input row and was not asked for");
});

/* ── The two numbers that must not drift ─────────────────────────────────── */

await check("the stylesheet's clamp is the one Rust enforces", async () => {
  // `.shell` must be able to grow to any height Rust will grant it. A cap
  // smaller than QUICKBAR_MAX_HEIGHT would clip the tallest cards again; a cap
  // of `100vh` (which this used to be) makes the measurement the window's own
  // height and stops the loop - the defect these checks exist for.
  const css = readFileSync(join(SRC, "style.css"), "utf8");
  const shell = css.slice(css.indexOf(".shell {"), css.indexOf("}", css.indexOf(".shell {")));
  const cap = /max-height:\s*(\d+)px;/.exec(shell);
  const rust = readFileSync(join(RUST, "windows.rs"), "utf8");
  const max = /const QUICKBAR_MAX_HEIGHT: f64 = (\d+)/.exec(rust);
  const base = /const QUICKBAR_BASE_HEIGHT: f64 = (\d+)/.exec(rust);
  assert.ok(cap, "`.shell` no longer states a pixel max-height (100vh breaks the growth loop)");
  assert.ok(max, "windows.rs no longer declares QUICKBAR_MAX_HEIGHT");
  assert.ok(base, "windows.rs no longer declares QUICKBAR_BASE_HEIGHT");
  assert.equal(cap[1], max[1],
    `the stylesheet caps the bar at ${cap[1]}px and Rust clamps it at ${max[1]}px`);
  assert.equal(Number(base[1]), BASE);
  assert.equal(Number(max[1]), CLAMP);
});

console.log(fails.length ? `\n${fails.length} failed` : "\nall reachability checks passed");
await browser.close();
await close();
process.exit(fails.length ? 1 : 0);
