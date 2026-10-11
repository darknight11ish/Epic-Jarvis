/**
 * The measurement behind the poll-hygiene commit (2026-10-08 cohesion audit,
 * findings 1 and 2). Not part of `npm run test:*` - it takes about a minute -
 * but it is what produced the numbers in the commit message, so they can be
 * reproduced rather than taken on trust.
 *
 *   node tests/poll-hygiene-measure.mjs          # the fixed sources
 *   node tests/poll-hygiene-measure.mjs old      # the BEFORE overlay
 *
 * The BEFORE side is built by `tests/make-before-overlay.mjs`, which copies
 * `src/` to `src-old/` and puts HEAD's `main.js`, `widget.js` and `devices.js`
 * back over the top - so both sides run the same harness.
 *
 * WHAT IS COUNTED. Not how many times a callback fired after the fact (that
 * measures the harness: Playwright's fake clock yields a real macrotask
 * between timer callbacks and keeps syncing real time, so "runFor(1000) x 60"
 * is not one clean simulated minute). Instead, the waits the app itself ASKS
 * FOR are recorded at the call site, and the wake-ups in a window are read off
 * them: an interval of d fires floor(W/d) times, and a timeout chain fires the
 * longest prefix of waits that fits in W.
 *
 * The pairing poll is counted the other way, because it is an IPC fact rather
 * than a timer one: `pair_session` reads per simulated minute, read from the
 * harness's own call log.
 */
import * as K from "./uikit.mjs";
import { resolve } from "node:path";

const NOW = 1_700_000_000_000;
const WINDOW_S = 60;
const OLD = process.argv[2] === "old";
const DIR = OLD ? "src-old" : "src";
const root = resolve(import.meta.dirname, "..", DIR);

const APPROVAL = {
  id: "a1", action: "switch_model", tier: "ask", created: 1,
  detail: JSON.stringify({ ref: "qwen3:8b" }), prompt: "Switch the active model?",
  risk: { reversible: "yes", reach: "local", swipe_ok: true, why: "", classified: true },
  raised: null, expires_in: 3600,
  notice: { title: "Switch the model", weight: "normal", deny_ok: true, approve_ok: false,
            body: "Nothing has happened yet." },
};
const DEVICES = {
  devices: {
    list: { available: true, you: "pc",
            devices: [{ id: "pc", name: "This PC", kind: "pc", removable: false }],
            shared: { retired: false, last_other_seen: null, can_bring_back_here: true },
            pairing: { available: true, why_not: null } },
    address: { address: "jarvis-pc.tail1234.ts.net", source: "tailscale" },
    start: { ok: true, qr_svg: "data:image/svg+xml;base64,PHN2Zy8+", code: "K7QM-4TXD",
             expires_in: 600, tries_left: 3 },
    sessions: [{ state: "waiting_for_phone", expires_in: 590, tries_left: 3, device_name: null,
                 words: null, wrong_tries_from: [], message: "Waiting for your phone..." }],
  },
};

/** Watches the scheduling calls and logs the wait each one asked for. */
function watch(keys) {
  window.__asked = [];
  const realSetTimeout = window.setTimeout;
  const realSetInterval = window.setInterval;
  const hit = (fn) => keys.find((k) => String(fn).includes(k));
  const wrap = (fn) => { const k = hit(fn); return k ? function (...a) { return fn.apply(this, a); } : fn; };
  window.setTimeout = function (fn, ms, ...a) {
    const w = wrap(fn);
    if (w !== fn) window.__asked.push(["timeout", ms]);
    return realSetTimeout.call(this, w, ms, ...a);
  };
  window.setInterval = function (fn, ms, ...a) {
    const w = wrap(fn);
    if (w !== fn) window.__asked.push(["interval", ms]);
    return realSetInterval.call(this, w, ms, ...a);
  };
}

/** Wake-ups in `w` ms from the waits the app asked for. */
function wakeUps(asked, w) {
  let n = 0;
  for (const [kind, ms] of asked) {
    if (kind === "interval") n += ms > 0 ? Math.floor(w / ms) : w;
  }
  let sum = 0;
  for (const [kind, ms] of asked) {
    if (kind !== "timeout") continue;
    sum += Math.max(ms, 1);
    if (sum > w) break;
    n += 1;
  }
  return n;
}

const KEYS = OLD
  ? ["if (state.approval && !dom.approval.hidden) paintApprovalClock();",
     "if (state.approval && !dom.apprCard.hidden) paintApprovalClock();"]
  : ["isHidden()) return arm()"];

const { base, close } = await K.serve(root);
const browser = await K.launch();
const out = { sources: DIR, clock: [] };

for (const [file, viewport, cardVisible] of [
  ["index.html", { width: 760, height: 1600 }, true],
  ["index.html", { width: 760, height: 1600 }, false],
  ["widget.html", { width: 320, height: 520 }, true],
  ["widget.html", { width: 320, height: 520 }, false],
]) {
  const page = await K.open(browser, base, file, { pending: cardVisible ? [APPROVAL] : [] }, viewport);
  await page.clock.install({ time: new Date(NOW) });
  await page.addInitScript(watch, KEYS);
  await page.reload();
  await page.waitForTimeout(700);
  await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 500)));
  for (let i = 0; i < WINDOW_S; i++) { await page.clock.runFor(1000); await page.waitForTimeout(2); }
  const asked = await page.evaluate(() => window.__asked);
  const text = await page.evaluate(() => {
    const line = document.querySelector("#approval .approval-reassure")
      || document.getElementById("appr-risk");
    return line ? line.textContent : null;
  });
  await page.close();
  out.clock.push({
    window: file,
    cardOnScreen: cardVisible,
    wakeUpsInOneMinute: wakeUps(asked, WINDOW_S * 1000),
    waitsAskedFor: [...new Set(asked.map((a) => a[1]))].sort((a, b) => a - b),
    line: text,
  });
}

{
  const page = await K.open(browser, base, "settings.html", DEVICES, { width: 760, height: 1600 });
  await page.clock.install({ time: new Date(NOW) });
  await page.reload();
  await page.waitForTimeout(700);
  await page.locator("#dv-pair").click({ force: true, timeout: 20000 });
  await page.waitForTimeout(300);
  await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 500)));
  const reads = () => page.evaluate(
    () => (window.__calls || []).filter((c) => c[0] === "pair_session").length);
  const perMinute = [];
  for (let m = 0; m < 3; m++) {
    const before = await reads();
    for (let i = 0; i < WINDOW_S; i++) { await page.clock.runFor(1000); await page.waitForTimeout(2); }
    perMinute.push((await reads()) - before);
  }
  await page.close();
  out.pairingPoll = {
    pairSessionReadsPerMinute: perMinute,
    note: "the code's own window is 10 minutes; the first minute is the QR moment",
  };
}

console.log(JSON.stringify(out, null, 2));
await browser.close();
close();
