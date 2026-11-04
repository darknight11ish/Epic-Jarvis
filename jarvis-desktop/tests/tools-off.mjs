/**
 * The Tools page may turn OFF anything that is ON (D4, the owner, 2026-11-04;
 * src/asks-first.js, src/asks-first-settings.js, src-tauri/src/asks_first.rs;
 * backend/jarvis_asks_first.py). The old rule refused a tool outside the 21
 * in-app switches with a 403; the owner reversed the OFF half only.
 *
 * What must hold:
 * - every tool that is ON is listed, including one enabled in the settings
 *   file that the page has no switch row for, with its real state and the
 *   PC's own plain reason;
 * - such a row is an OFF switch: checked while on, always usable, and it
 *   sends the same set_tool_enabled verb every other tool switch uses;
 * - after OFF the row STAYS and says OFF - it is not silently gone - and it
 *   cannot be switched back on from the page (that is still a hand edit);
 * - a PC older than this sends no `extra`, and the page is unchanged.
 *
 * Runs on plain Node, no browser and no Playwright: the page's pure functions
 * are imported, and the wiring is read as text.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  extraToolsView,
  extraToolView,
  readAsksFirst,
  TOOLS_ELSEWHERE_LABEL,
  TOOLS_ELSEWHERE_OFF,
  TOOLS_SWITCHABLE,
} from "../src/asks-first.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/asks-first-cases.json"));
const C = CASES.cases;

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

check("the fixture really carries tools that are ON and have no switch row", () => {
  const view = readAsksFirst(C.pc_unlisted_tools_on);
  const rows = extraToolsView(view.tools);
  assert.deepEqual(rows.map((r) => r.id), ["plugin_scan", "web_search"],
    "the two tools enabled in the file but not among the 21 switches");
  assert.ok(rows.every((r) => r.on === true), "each is really ON");
  assert.ok(rows.every((r) => r.switchable === false), "none pretends an ON switch exists");
  assert.ok(rows.every((r) => r.why.length > 20), "each carries the PC's plain reason");
  assert.ok(rows.every((r) => r.title && r.title !== r.id),
    "each is drawn with its human label, never the raw id");
  assert.equal(view.tools.items.length, 21, "the 21 switch rows are unchanged");
  assert.ok(!TOOLS_SWITCHABLE.includes("web_search"));
  assert.ok(!TOOLS_SWITCHABLE.includes("plugin_scan"));
});

check("an ON row is an OFF switch: checked, usable, and the PC's reason under it", () => {
  const view = readAsksFirst(C.pc_unlisted_tools_on);
  const web = extraToolsView(view.tools).find((r) => r.id === "web_search");
  assert.deepEqual(extraToolView(web), {
    checked: true, disabled: false, lines: [web.why],
  }, "OFF is never held and never disabled - it only narrows what the model may do");
});

check("after OFF the row STAYS, says OFF, and cannot be turned on from here", () => {
  const view = readAsksFirst(C.pc_unlisted_tool_turned_off);
  const rows = extraToolsView(view.tools);
  const off = rows.find((r) => r.id === "plugin_scan");
  assert.ok(off, "the row the owner just turned off is still on the page");
  assert.equal(off.on, false, "and says OFF truthfully");
  const tv = extraToolView(off);
  assert.equal(tv.checked, false);
  assert.equal(tv.disabled, true, "putting it back is a hand edit, not a switch here");
  assert.match(tv.lines[0], /it is off now/);
  assert.match(tv.lines[0], /jarvis-framework\.toml/, "it says where to put it back, in plain words");
  const stillOn = rows.find((r) => r.id === "web_search");
  assert.ok(stillOn && stillOn.on === true, "a tool that is still ON is still shown as On");
});

check("a PC older than this sends no extra and the page is unchanged", () => {
  const view = readAsksFirst(C.pc_shipped);
  assert.deepEqual(view.tools.extra, [], "no extra rows");
  assert.deepEqual(extraToolsView(view.tools), [], "nothing is drawn for them");
  assert.equal(view.tools.items.length, 21);
});

check("the page draws the extra rows and sends OFF through the same verb", () => {
  const page = read("src/asks-first-settings.js");
  assert.match(page, /extraToolsView/);
  assert.match(page, /TOOLS_ELSEWHERE_LABEL/);
  assert.match(page, /extraToolView\(item\)/);
  // The row's switch calls the SAME changeTool path as every tool switch, so
  // the one permission shape (OFF instant) is not duplicated.
  const block = page.slice(page.indexOf("const elsewhere = extraToolsView(tools)"));
  assert.ok(block.length > 0, "the extra rows are drawn");
  assert.match(block.slice(0, 1200), /changeTool\(item\.id, want, box2\)/,
    "the extra row's toggle goes through changeTool");
  const change = page.slice(page.indexOf("async function changeTool"));
  assert.match(change.slice(0, 1200), /invoke\("set_tool_enabled", \{ tool, enabled \}\)/,
    "ONE command carries every tool switch");
  // And the container it is drawn into still exists, outside the Keywords card.
  const html = read("src/settings.html");
  assert.match(html, /<div id="af-tools"><\/div>/);
});

check("Rust sends OFF for a tool it has no switch row for, and still refuses ON", () => {
  const rust = read("src-tauri/src/asks_first.rs");
  assert.match(rust, /pub\(crate\) fn tool_body\(tool: &str, enabled: bool\)/);
  assert.match(rust, /if !plausible_tool_name\(tool\)/, "a malformed name is refused here");
  assert.match(rust, /if enabled && !TOOLS_SWITCHABLE\.contains\(&tool\)/,
    "only the ON direction is still refused before it is sent");
  assert.doesNotMatch(rust, /if !TOOLS_SWITCHABLE\.contains\(&tool\) \{\s*if tool\.is_empty\(\)/,
    "the old every-direction gate is gone");
  // The Rust test names the new rule so it cannot be silently dropped.
  assert.match(rust, /fn only_the_tiered_tools_can_be_turned_on_but_anything_on_can_be_turned_off/);
});

check("the OFF words name the file to put the tool back in", () => {
  assert.match(TOOLS_ELSEWHERE_OFF, /jarvis-framework\.toml/);
  assert.match(TOOLS_ELSEWHERE_OFF, /\[tools\]\.enabled/);
  assert.ok(TOOLS_ELSEWHERE_LABEL.length > 0);
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nThe Tools page can turn OFF anything that is on");
process.exit(fails.length ? 1 : 0);
