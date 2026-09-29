/**
 * The words and the rules of Settings -> "Headless browser (Obscura)" (the
 * owner's decision of 2026-09-29; backend/jarvis_browser_engine.py; JARVIS-API
 * section 97). Pure: no page, no Tauri, so tests/browser-engine.mjs can run it.
 *
 * The words are fixed on the PC (`WORDS` in jarvis_browser_engine.py) and held
 * here to the same text by that test (tools/gen_browser_cases.py writes the
 * table), so the phone (net/BrowserEngine.kt) says exactly the same.
 *
 * @module browser-engine-rules
 */

export const BROWSER = Object.freeze({
  title: "Headless browser (Obscura)",
  detail:
    "Jarvis normally works a web page in a browser window you can see. This adds a second way: Obscura, a small " +
    "browser with no window, for plain reading and quick lookups. Jarvis chooses per task - the visible window when " +
    "you might need to sign in or take over, the headless browser for simple reading. Every page it opens and every " +
    "step it takes is still listed on an approval card first. What it reads is outside text: it never becomes a fact " +
    "Jarvis remembers. It cannot reach your own network (this PC, your home network, Tailscale), uses no proxy, keeps " +
    "no cookies and saves no files. Off by default. Turning it on asks first, because it is a new program on your PC " +
    "that reaches the web.",
  switch: "Let Jarvis use the headless browser (Obscura)",
  modeTitle: "Which browser Jarvis uses",
  modes: Object.freeze({
    auto: "Automatic (recommended)",
    visible: "Always the visible browser",
    headless: "The headless browser when it can run",
  }),
  modeHelp: Object.freeze({
    auto: "Jarvis picks per task: the visible window whenever you might need to sign in or take over, the headless browser for plain reading.",
    visible: "Jarvis always opens the browser window you can see and take over.",
    headless:
      "Jarvis uses the headless browser whenever it can run, but never for a sign-in. If it cannot run, Jarvis says so and uses the visible browser.",
  }),
  stealth:
    "Stealth is always on for the headless browser. It makes the browser look like an ordinary Chrome. It does not " +
    "solve captchas, and sites can still block or ban it. Signing in to a real account with it could get that account " +
    "closed under a site's terms, so Jarvis never signs in with it and never solves a captcha: at one it stops and " +
    "hands the job to the visible browser.",
  offLine: "Off. Jarvis uses the visible browser window only.",
  waitingLine: "Waiting for your yes on the card. Nothing has changed yet.",
  unread: "Could not read this setting.",
  missing: "This PC's Jarvis does not have the headless browser yet. Run scripts\\apply-patches.ps1 on the PC to add it.",
  stepsTitle: "To install it, paste this one line into PowerShell on your PC:",
  stepsNote:
    "It downloads Obscura's Windows program from its GitHub releases (github.com/h4ckf0r0day/obscura, Apache-2.0), " +
    "unpacks it into Jarvis's own folder and checks it: version, stealth on, and that it refuses to visit your own " +
    "network. Jarvis never downloads it by itself.",
  copy: "Copy the line",
  copied: "Copied. Paste it into PowerShell.",
  asking: "Asking...",
  turningOff: "Turning it off...",
  askedCard: "A card is waiting for your yes in the Jarvis bar. The headless browser stays off until you say yes.",
  off: "The headless browser is off. Jarvis uses the visible browser only.",
  modeSaved: "Saved.",
});

export const MODE_IDS = Object.freeze(["auto", "visible", "headless"]);

/** A trimmed string, or "". */
export function words(x) {
  return typeof x === "string" ? x.trim() : "";
}

/**
 * What Settings shows for one GET /api/browser/engine answer. The reference is
 * `panel()` in backend/jarvis_browser_engine.py (tools/gen_browser_cases.py
 * writes its cases): the switch looks ON while its card waits, so it can be
 * turned back off, but the line says it is only waiting.
 * -> {available, obscura, waiting, checked, mode, line, status, installLine}
 */
export function browserView(out) {
  const o = out && typeof out === "object" && !Array.isArray(out) ? out : {};
  if (typeof o.obscura !== "boolean") {
    return {
      available: false,
      obscura: false,
      waiting: false,
      checked: false,
      mode: "auto",
      line: BROWSER.unread,
      status: "",
      installLine: "",
    };
  }
  const on = o.obscura;
  const waiting = o.waiting === true && !on;
  return {
    available: true,
    obscura: on,
    waiting,
    checked: on || waiting,
    mode: MODE_IDS.includes(o.mode) ? o.mode : "auto",
    line: words(o.line) || (waiting ? BROWSER.waitingLine : !on ? BROWSER.offLine : ""),
    status: words(o.status_line),
    installLine: words(o.install_line),
  };
}
