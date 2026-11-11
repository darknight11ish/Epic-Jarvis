/**
 * The Tools page turns OFF anything that is ON (D4, the owner, 2026-11-04) and
 * turns ON every tool the model can be offered (the same day's second
 * decision). src/asks-first.js, src/asks-first-settings.js,
 * src-tauri/src/asks_first.rs; backend/jarvis_asks_first.py.
 *
 * What must hold:
 * - every tool the model can be offered is drawn with an ON switch, the raw
 *   Tier C set and the everyday helpers included (65 at 2026-11-10, 62 at
 *   2026-11-09, 60 at 2026-11-05, 48 before);
 * - a name this PC does not know, or one of the five whose own switch decides
 *   it, is still listed when it is ON, with its real state and the PC's own
 *   plain reason, and that row is an OFF switch only;
 * - after OFF such a row STAYS and says OFF - it is not silently gone;
 * - Rust sends OFF for any real tool name and refuses ON only for a name it
 *   does not know (or one of the five, with the PC's own sentence);
 * - a PC with nothing else ON sends no `extra`, and the page is unchanged.
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
  toolSwitchView,
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

check("every formerly locked tool is a switch row with an ON switch", () => {
  const view = readAsksFirst(C.pc_shipped);
  const byId = new Map(view.tools.items.map((i) => [i.id, i]));
  for (const id of ["shell_exec", "control_computer", "control_phone",
    "browser_control", "read_web_page", "connect_account", "rea_investigate",
    "calculator", "propose_plan", "web_search", "file_read", "feature_guide"]) {
    const item = byId.get(id);
    assert.ok(item, `${id} is drawn as a switch`);
    const tv = toolSwitchView(item, view.tools, true);
    assert.ok(tv && tv.disabled === false,
      `${id} can be switched on from the PC: ${JSON.stringify(tv)}`);
    assert.ok(TOOLS_SWITCHABLE.includes(id), `${id} is in the switchable list`);
  }
  assert.equal(view.tools.items.length, 65,
    "65 switches, every tool the model can be offered (seven GitHub tools - the carded repository create added 2026-11-09 - the cardless project_read added the same day, and wave 16's read-only PR cockpit, carded merge and carded fix-and-push - send_text_message, the approval-policy row and four pack tools since 2026-11-05)");
});

check("the fixture really carries the name this PC does not know", () => {
  const view = readAsksFirst(C.pc_unlisted_tools_on);
  const rows = extraToolsView(view.tools);
  assert.deepEqual(rows.map((r) => r.id), ["plugin_scan"],
    "the one enabled name the PC has no row for (web_search is a switch now)");
  assert.ok(rows.every((r) => r.on === true), "it is really ON");
  assert.ok(rows.every((r) => r.switchable === false), "it pretends no ON switch exists");
  assert.ok(rows.every((r) => r.why.length > 20), "it carries the PC's plain reason");
  assert.ok(rows.every((r) => r.title && r.title !== r.id),
    "it is drawn with its human label, never the raw id");
  assert.equal(view.tools.items.length, 65, "the switch rows are unchanged");
  assert.ok(TOOLS_SWITCHABLE.includes("web_search"));
  assert.ok(!TOOLS_SWITCHABLE.includes("plugin_scan"));
});

check("an ON row is an OFF switch: checked, usable, and the PC's reason under it", () => {
  const view = readAsksFirst(C.pc_unlisted_tools_on);
  const row = extraToolsView(view.tools).find((r) => r.id === "plugin_scan");
  assert.deepEqual(extraToolView(row), {
    checked: true, disabled: false, lines: [row.why],
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
  const stillOn = view.tools.items.find((r) => r.id === "calendar_read");
  assert.ok(stillOn && stillOn.on === true, "a tool that is still ON is still shown as On");
});

check("a PC with nothing else ON sends no extra and draws no extra rows", () => {
  const view = readAsksFirst(C.pc_shipped);
  assert.deepEqual(view.tools.extra, [], "no extra rows");
  assert.deepEqual(extraToolsView(view.tools), [], "nothing is drawn for them");
  assert.equal(view.tools.items.length, 65);
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

check("Rust refuses ON only for a name the PC does not know, and sends every OFF", () => {
  const rust = read("src-tauri/src/asks_first.rs");
  assert.match(rust, /pub\(crate\) fn tool_body\(tool: &str, enabled: bool\)/);
  assert.match(rust, /if !plausible_tool_name\(tool\)/, "a malformed name is refused here");
  assert.match(rust, /if enabled && !TOOLS_SWITCHABLE\.contains\(&tool\)/,
    "only the ON direction is refused before it is sent");
  assert.match(rust, /TOOLS_NO_SWITCH\.iter\(\)\.find/,
    "a known tool with no switch of its own gets its own sentence, not 'does not know'");
  assert.match(rust, /pub\(crate\) const TOOLS_NO_SWITCH: \[\(&str, &str\); 5\]/);
  assert.doesNotMatch(rust, /TOOLS_TOML_ONLY_NOTE/,
    "the old 'not offered in-app by this slice' refusal is gone");
  // The Rust test names the new rule so it cannot be silently dropped.
  assert.match(rust, /fn every_known_tool_can_be_turned_on_but_anything_on_can_be_turned_off/);
});

check("the OFF words name the file to put the tool back in", () => {
  assert.match(TOOLS_ELSEWHERE_OFF, /jarvis-framework\.toml/);
  assert.match(TOOLS_ELSEWHERE_OFF, /\[tools\]\.enabled/);
  assert.ok(TOOLS_ELSEWHERE_LABEL.length > 0);
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nThe Tools page can turn OFF anything that is on, and ON every known tool");
process.exit(fails.length ? 1 : 0);
