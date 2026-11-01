/*
 * Accessibility tests: the pure helpers, the source pins that stop them being
 * quietly removed, and the honesty of what the panel tells a keyboard/screen
 * reader user.
 *
 * NOT TESTED HERE, and never claimed: this suite does not open Obsidian, does
 * not run a screen reader, and cannot see focus or contrast. It proves the
 * attributes the plugin asks for are the ones the helpers set and that the UI
 * source still uses them; whether Obsidian's webview renders them correctly is
 * UNTESTED until somebody loads the plugin in a vault.
 *
 * Run:  node --experimental-test-isolation=none --test tests/accessibility.test.mjs
 */
import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import * as a11y from "../src/a11y.ts";

const { accessibleName, busy, group, hint, liveRegion } = a11y;

/** A stand-in for an element: records every setAttribute call, in order. */
function attrs() {
  const calls = [];
  return {
    calls,
    setAttribute(name, value) {
      calls.push([name, value]);
    },
    get(name) {
      const found = calls.filter(([key]) => key === name).at(-1);
      return found ? found[1] : undefined;
    },
  };
}

function readSource(name) {
  return readFileSync(fileURLToPath(new URL("../src/" + name, import.meta.url)), "utf8");
}

describe("the a11y helpers set the attributes a screen reader reads", () => {
  test("accessibleName sets aria-label and trims it", () => {
    const el = attrs();
    accessibleName(el, "  Ask a question about this note  ");
    assert.deepEqual(el.calls, [["aria-label", "Ask a question about this note"]]);
  });

  test("accessibleName refuses an empty name instead of leaving a control unnamed", () => {
    assert.throws(() => accessibleName(attrs(), ""), /must not be empty/);
    assert.throws(() => accessibleName(attrs(), "   "), /must not be empty/);
  });

  test("liveRegion is a polite, atomic status role by default", () => {
    const el = attrs();
    liveRegion(el);
    assert.equal(el.get("role"), "status");
    assert.equal(el.get("aria-live"), "polite");
    assert.equal(el.get("aria-atomic"), "true");
  });

  test("liveRegion can be assertive for a failure that must be heard now", () => {
    const el = attrs();
    liveRegion(el, "assertive");
    assert.equal(el.get("role"), "alert", "role and aria-live must agree: assertive is alert");
    assert.equal(el.get("aria-live"), "assertive");
  });

  test("group names a row of controls without changing its role away from group", () => {
    const el = attrs();
    group(el, "Edit the selection through Jarvis");
    assert.equal(el.get("role"), "group");
    assert.equal(el.get("aria-label"), "Edit the selection through Jarvis");
    assert.throws(() => group(attrs(), ""), /must not be empty/);
  });

  test("busy flips aria-busy true then false", () => {
    const el = attrs();
    busy(el, true);
    assert.equal(el.get("aria-busy"), "true");
    busy(el, false);
    assert.equal(el.get("aria-busy"), "false");
  });

  test("hint is a no-op for an empty sentence and never sets an empty title", () => {
    const el = attrs();
    hint(el, "   ");
    assert.deepEqual(el.calls, []);
    hint(el, " Select text in the note first. ");
    assert.equal(el.get("title"), "Select text in the note first.");
  });
});

describe("the UI source still uses the helpers where it matters", () => {
  const panel = readSource("panel.ts");
  const settings = readSource("settings.ts");
  const modals = readSource("modals.ts");
  const main = readSource("main.ts");
  const a11ySource = readSource("a11y.ts");

  test("the plugin's own controls all get an accessible name", () => {
    const labels = [
      [panel, "Ask a question about this note"],
      [panel, "Insert under which heading"],
      [panel, "Line to insert under the heading"],
      [panel, "Template for a new note"],
      [panel, "New note path in the vault"],
      [settings, "Jarvis backend URL"],
      [settings, "Token in SecretStorage - the secret's name"],
      [settings, "Fallback token - stored on this PC, not encrypted by Obsidian"],
      [settings, "Templates folder"],
      [modals, "Question"],
      [modals, "What to capture"],
      [modals, "Selected words (read only)"],
      [modals, "Replacement words"],
      [modals, "Tag name"],
    ];
    for (const [source, label] of labels) {
      assert.ok(
        source.includes('accessibleName(') && source.includes('"' + label + '"'),
        "expected accessibleName(..., \"" + label + '") in the source',
      );
    }
  });

  test("every answer/result area that changes after a request is a live region", () => {
    for (const [source, what] of [
      [panel, "the panel's ask answer and write result"],
      [settings, "the Test connection result and the non-loopback warning"],
      [modals, "each dialog's answer/result"],
    ]) {
      assert.ok(source.includes("liveRegion("), why(what));
    }
    assert.ok(/liveRegion\(answer\)/.test(panel), "the ask answer must be a live region");
    assert.ok(/liveRegion\(this\.resultEl\)/.test(panel), "the write result must be a live region");
    assert.ok(/liveRegion\(result\)/.test(settings), "the Test connection result must be a live region");
    assert.ok(/liveRegion\(loopbackWarning\)/.test(settings), "the non-loopback warning must be a live region");
  });

  test("answers are marked busy while the request runs, so a wait is announced", () => {
    assert.ok(/busy\(answer, true\)/.test(panel), "the panel answer must be busy while asking");
    assert.ok(/busy\(answer, false\)/.test(panel), "the panel answer must stop being busy when the answer lands");
    assert.ok(/busy\(said, true\)/.test(modals), "the capture answer must be busy while sending");
    assert.ok(/busy\(said, false\)/.test(modals), "the capture answer must stop being busy");
  });

  test("the selection buttons are one named group, and a stale disabled state is not used", () => {
    assert.ok(/group\(selectionRow, "Edit the selection through Jarvis"\)/.test(panel));
    assert.ok(/Select text in the note to use Bold/.test(panel), "the visible hint must still be there");
    // Selecting text does not re-render the panel, so the buttons must stay
    // reachable and refuse in the live result line instead of being disabled.
    assert.ok(!/button\.disabled = !selection/.test(panel));
    assert.ok(/this\.showResult\("Select some text first\."/.test(panel));
    assert.ok(/hint\(insertButton, "This note has no headings/.test(panel));
  });

  test("every action that disables its button gives focus back afterwards", () => {
    assert.ok(/if \(ask\.isConnected\) ask\.focus\(\)/.test(panel), "Ask must give focus back");
    assert.ok((panel.match(/if \(button\.isConnected\) button\.focus\(\)/g) || []).length >= 3, "panel buttons must give focus back");
    assert.ok((modals.match(/button\.buttonEl\.focus\(\)/g) || []).length >= 4, "every dialog button must give focus back");
    assert.ok(/button\.buttonEl\.focus\(\)/.test(settings), "Test connection must give focus back");
  });

  test("a panel is not rebuilt under the user's focus", () => {
    assert.ok(/el\.contains\(document\.activeElement\)/.test(panel), "render must bail out while the panel has focus");
  });

  test("a refusal is alert-level, not only a red border", () => {
    assert.ok(/isRefusalKind\(this\.lastResultKind\) \? "assertive" : "polite"/.test(panel));
    assert.ok(/liveRegion\(this\.resultEl, isRefusalKind\(kind\) \? "assertive" : "polite"\)/.test(modals));
    assert.ok(/role", politeness === "assertive" \? "alert" : "status"/.test(a11ySource));
  });

  test("the template preview is a live region and can be scrolled from the keyboard", () => {
    assert.ok(/liveRegion\(templatePreview\)/.test(panel));
    assert.ok(/templatePreview\.tabIndex = 0/.test(panel));
  });

  test("a command-palette failure is explained in the live panel line, not only in a toast", () => {
    assert.ok(/private tellPanel\(message: string, kind: WriteKind = "error"\): boolean/.test(main));
    assert.ok((main.match(/this\.explain\(/g) || []).length >= 5, "the command failures must use the live line");
    assert.ok(/private showFromCommand\(/.test(main), "write updates from a command must use the live line");
  });

  test("the validation sentence is not announced twice", () => {
    assert.ok(!/new Notice\(/.test(panel), "the panel's result line is live; a second Notice would repeat it");
    assert.ok(!/new Notice\(/.test(modals), "a dialog's result line is live; a second Notice would repeat it");
  });

  test("long values tell the truth about being clipped", () => {
    assert.ok(/and " \+ \(items\.length - cap\) \+ " more, not shown"/.test(panel), "a cut list must say how many are hidden");
    assert.ok(/first 400 characters of the exact text/.test(modals), "the replace preview must not claim to show all of a clipped target");
  });

  test("the status bar is a live region, not an icon with a hidden label", () => {
    assert.ok(/liveRegion\(this\.statusEl\)/.test(main));
    assert.ok(!/aria-label", "Jarvis connection"/.test(main), "a label must not hide the connection state");
  });

  test("placeholders are decoration, never the only label", () => {
    for (const source of [panel, settings, modals]) {
      assert.ok(!/setAttribute\("aria-label", ""\)/.test(source), "an empty accessible name is a lie");
    }
    // The template path has a placeholder too, so it must still carry a name.
    assert.ok(/accessibleName\(templatePath, "New note path in the vault"\)/.test(panel));
  });
});

function why(what) {
  return "expected a live region for " + what;
}
