/**
 * Settings -> "Check my setup": run the live preflight and show its words.
 *
 * The owner's first priority (2026-10-11): `selftest.py --preflight` - "the
 * Jarvis that is RUNNING now, every chain end to end", read-only, ending
 * "N pass, N fail, N warn" - only ever ran for someone with the repository
 * checked out. He asked to press something and see the answer.
 *
 * WHY IT RUNS THE REPOSITORY'S COPY (measured 2026-10-11): the checker's most
 * valuable answer on this PC is the six lines that say his deployment is behind
 * (`work.patch`, `card-prefs.patch`, `pictures.patch` not in `jarvis_hud.py`,
 * and three modules absent). That check imports `_stack` (which imports
 * `_gitapply`) and reads 144 `backend/*.patch` files - none of which is in his
 * live backend folder. Shipping it would mean 148 files inside his running
 * install, including a duplicate patch tree that could compare against the
 * WRONG patches and report everything fine. So the command runs the command he
 * already has, from the clone, and this page shows both folders.
 *
 * WHAT IT NEVER DOES: the checker reads the pairing token itself; nothing here
 * passes, shows or logs one (`preflight.rs`'s own test holds that), and
 * `--preflight` approves nothing, sends nothing, unloads no model and changes
 * no setting. The page says so on its face, so nobody wires a "fix it" button
 * to it later.
 */

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  async function invoke(command, args = {}) {
    return TAURI.core.invoke(command, args);
  }

  /** The verdict line, e.g. "34 pass, 6 fail, 3 warn (5 skipped)". */
  function summaryLine(text) {
    const found = String(text || "").match(/^\s*\d+\s+pass,.*$/m);
    return found ? found[0].trim() : "";
  }

  /** Every failing or warning line, in the order the checker printed them. */
  function failingLines(text) {
    return String(text || "")
      .split("\n")
      .filter((line) => /^\s*(FAIL|WARN)\b/.test(line))
      .map((line) => line.trim());
  }

  /** Exactly what the page shows, so Copy copies what he can see. */
  function panelText(run) {
    const parts = [
      "Jarvis ran from: " + (run.ran_from || "(unknown)"),
      "Jarvis checked:  " + (run.checked || "(unknown)"),
      "",
    ];
    if (run.why) parts.push(run.why);
    else {
      parts.push(summaryLine(run.text) || "(the checker printed no verdict line)");
      const failing = failingLines(run.text);
      parts.push("", failing.length ? failing.join("\n") : "No failures.");
    }
    return parts.join("\n").trim();
  }

  function paint(run) {
    const state = $("pf-state");
    const body = $("pf-body");
    if (!run) {
      if (state) state.textContent = "Asking Jarvis…";
      return;
    }
    if (state) {
      state.textContent = run.why
        ? run.why
        : (run.ok ? "Everything that can be checked passed." : "Something is broken - see the lines below.");
    }
    if (body) body.hidden = false;
    const ranFrom = $("pf-ran-from");
    const checked = $("pf-checked");
    if (ranFrom) ranFrom.textContent = run.ran_from || "(unknown)";
    if (checked) checked.textContent = run.checked || "(unknown)";
    const summary = $("pf-summary");
    if (summary) {
      summary.textContent = run.why
        ? ""
        : (summaryLine(run.text) || "(the checker printed no verdict line)");
    }
    const lines = $("pf-lines");
    if (lines) {
      const failing = run.why ? [] : failingLines(run.text);
      lines.textContent = run.why ? "" : (failing.length ? failing.join("\n") : "No failures.");
    }
  }

  async function run() {
    const button = $("pf-run");
    const state = $("pf-state");
    if (button) button.disabled = true;
    if (state) state.textContent = "Checking… this can take a minute: one of the checks asks the model a question.";
    let result = null;
    try {
      result = await invoke("check_my_setup");
    } catch (exc) {
      result = { ran_from: "", checked: "", text: "", ok: false, code: null,
                 why: "The check could not start: " + (exc && exc.message ? exc.message : exc) };
    } finally {
      if (button) button.disabled = false;
    }
    lastRun = result;
    paint(result);
  }

  async function copy() {
    const state = $("pf-state");
    try {
      await navigator.clipboard.writeText(panelText(lastRun || {}));
      if (state) state.textContent = "Copied. Paste it anywhere - it is exactly what is on screen.";
    } catch (exc) {
      if (state) state.textContent = "Could not copy: " + (exc && exc.message ? exc.message : exc);
    }
  }

  let lastRun = null;

  function wire() {
    const button = $("pf-run");
    if (button) {
      button.title = "Read-only: this approves nothing and changes no setting.";
      button.addEventListener("click", run);
    }
    const copyButton = $("pf-copy");
    if (copyButton) copyButton.addEventListener("click", copy);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
