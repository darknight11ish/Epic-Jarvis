/**
 * The words and the rules of Settings -> "Browser without a window (Obscura)" (the
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
  title: "Browser without a window (Obscura)",
  subtitle: "a browser Jarvis uses without opening a window",
  detail:
    "Jarvis normally works a web page in a browser window you can see. This adds a second way: Obscura, a small browser with no window, for plain reading and quick lookups. Jarvis chooses for each task. It uses the visible browser when you might need to sign in or take over, and the windowless browser for simple reading. Every page it opens and every step it takes is still listed on an approval card first. What it reads is outside text: Jarvis reads it but never follows instructions in it, and never remembers it as a fact. It cannot reach your own network (this PC, your home network, Tailscale), uses no proxy, keeps no cookies and saves no files. It is off until you turn it on. Turning it on asks first, because it is a new program on your PC that reaches the web.",
  switch: "Let Jarvis use the windowless browser (Obscura)",
  modeTitle: "Which browser Jarvis uses",
  modes: Object.freeze({
    auto: "Automatic (recommended)",
    visible: "Always the visible browser",
    headless: "The windowless browser when it can run",
  }),
  modeHelp: Object.freeze({
    auto: "Jarvis picks for each task: the visible browser whenever you might need to sign in or take over, the windowless browser for plain reading.",
    visible:
      "Jarvis always opens the browser window you can see and take over.",
    headless:
      "Jarvis uses the windowless browser whenever it can run, except when the task looks like a sign-in, a payment or a captcha. If it cannot run, Jarvis says so and uses the visible browser.",
  }),
  stealth:
    "This browser pretends to be an ordinary Chrome so fewer sites turn it away. That does not stop a site from blocking it, or from closing an account you sign in to. So Jarvis never types a password with it and never solves a captcha. When it reaches a captcha or sign-in page it stops and hands the job to the browser window you can see. A sign-in that starts with only a username or email box may not be spotted.",
  offLine: "Off. Jarvis uses the visible browser only.",
  waitingLine: "Waiting for your yes on the card. Nothing has changed yet.",
  unread: "Could not read this setting.",
  missing:
    "This PC's Jarvis is missing this feature. In PowerShell on the PC, in the Jarvis folder, run: .\\scripts\\apply-patches.ps1 . Then restart Jarvis.",
  waitingLink: "Waiting for the connection to your PC.",
  modeNote: "This does nothing until the switch above is on.",
  couldNotTurnOn: "Could not turn it on: ",
  stepsTitle:
    "To install it, paste this one line into PowerShell (the Windows command window) on your PC:",
  stepsNote:
    "It downloads one named release of Obscura's Windows program from its GitHub releases (github.com/h4ckf0r0day/obscura, Apache-2.0), unpacks it into Jarvis's own folder and prints its checksums (long codes that fingerprint the file) for you to compare with the release page. It does not run the program. The line then prints a second command that checks it: version, stealth on, and that it refuses to visit your own network. Jarvis never downloads it by itself.",
  copy: "Copy the line",
  copied: "Copied. Paste it into PowerShell.",
  asking: "Asking...",
  turningOff: "Turning it off...",
  askedCard:
    "A card is waiting for your yes in the Jarvis bar. The windowless browser stays off until you say yes.",
  off: "The windowless browser is off. Jarvis uses the visible browser only.",
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
    line:
      words(o.line) ||
      (waiting ? BROWSER.waitingLine : !on ? BROWSER.offLine : ""),
    status: words(o.status_line),
    installLine: words(o.install_line),
  };
}
