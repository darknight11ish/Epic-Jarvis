/**
 * A Settings read that never answers must be SAID, not waited on for ever.
 *
 * WHY THIS SUITE EXISTS (the desktop Settings freeze, 2026-10-10). The owner
 * pressed the gear on the Jarvis bar and the app stopped responding
 * (Windows Application Hang 1002 / WER AppHangB1 for 0.2.129.0, 22:27:08).
 * The freeze itself was not reproduced, but the path it takes had a real,
 * provable gap: `TAURI.core.invoke` has no timeout anywhere in this window, so
 * a command that never settles leaves the loader's `await` pending for ever -
 * no catch runs, no line is drawn, and a section of Settings sits on
 * "Asking Jarvis…" with nothing to tell the owner. Silence is the one thing a
 * settings screen must never do (settings audit 2026-10-08).
 *
 * This drives the REAL `settings.html` through the suite's own bridge
 * (`tests/uikit.mjs`), makes ONE open-time read (`get_backend_capabilities`)
 * never settle, re-triggers the loader that reads it, and waits for the line
 * `settings.js` already uses for that failure to appear.
 *
 * Run by hand - it waits out a real 30 s budget, so it is deliberately NOT in
 * `npm run test:ui`:
 *
 *     node tests/settings-open-budget.mjs [budgetSeconds]
 *
 * Before this change the same probe reported `saidSomething: false` after 45 s
 * with `#caps-state` still hidden and its text stuck on "Asking Jarvis…".
 */
import { chromium } from "playwright";
import * as K from "./uikit.mjs";

/** Above `OPEN_READ_BUDGET_MS` (30 s) in src/settings.js, plus room to poll. */
const BUDGET_S = Number(process.argv[2] || 40);

const { base, close } = await K.serve();
const browser = await K.launch();
const page = await K.open(browser, base, "settings.html", {}, { width: 900, height: 1000 });
await page.evaluate(() => {
  for (const d of document.querySelectorAll("details")) d.open = true;
});

// The stuck command, installed before the loader is asked to run again.
await page.evaluate(() => {
  const core = window.__TAURI__.core;
  const real = core.invoke;
  window.__stuckCalls = 0;
  core.invoke = (cmd, args) => {
    if (cmd === "get_backend_capabilities") {
      window.__stuckCalls += 1;
      return new Promise(() => {}); // accepted, never answered
    }
    return real(cmd, args);
  };
  // The page re-reads it when the window comes back into view.
  Object.defineProperty(document, "hidden", { value: false, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
});

const started = Date.now();
let said = null;
while (Date.now() - started < BUDGET_S * 1000) {
  const now = await page.evaluate(() => {
    const el = document.getElementById("caps-state");
    return {
      hidden: Boolean(el && el.hidden),
      tone: (el && el.dataset && el.dataset.tone) || "",
      text: el ? (el.textContent || "").trim() : "",
    };
  });
  if (!now.hidden && now.text) {
    said = { ms: Date.now() - started, ...now };
    break;
  }
  await page.waitForTimeout(250);
}

const final = await page.evaluate(() => {
  const el = document.getElementById("caps-state");
  return {
    hidden: Boolean(el && el.hidden),
    tone: (el && el.dataset && el.dataset.tone) || "",
    text: el ? (el.textContent || "").trim() : "",
    stuckCalls: window.__stuckCalls,
  };
});

await browser.close();
close();

console.log(
  JSON.stringify(
    {
      budgetSeconds: BUDGET_S,
      saidSomething: Boolean(said),
      saidAfterMs: said ? said.ms : null,
      saidText: said ? said.text : "",
      finalState: final,
    },
    null,
    2
  )
);

// A word to the owner, not silence - and it must be the page's own words, not
// a bridge error or raw JavaScript.
if (!said) {
  console.log("\nFAILED: a read that never answers said nothing at all");
  process.exit(1);
}
if (/[{}<>]|undefined|null|Error:/.test(said.text)) {
  console.log(`\nFAILED: raw JavaScript reached the owner: ${said.text}`);
  process.exit(1);
}
console.log("\nthe page says so instead of waiting for ever");
