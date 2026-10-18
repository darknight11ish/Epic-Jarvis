/**
 * The data and maths sandbox's Settings card (LM-1C, 2026-10-18;
 * sandbox-settings.js, sandbox-rules.js, sandbox_exec.rs, settings.html;
 * backend/jarvis_sandbox_exec.py, plugins/ready/sandbox/).
 *
 * Part 1 holds the pure rules to what they promise (the "not known" answer is
 * never shown as off; an old PC's 404/501 becomes one plain sentence). Part 2
 * reads the Rust and the page for the wiring, and for what must NOT be there:
 * no script, no file, no data, no second field on the POST. No browser is
 * needed for either.
 */
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as R from "../src/sandbox-rules.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

let failed = 0;
let passed = 0;
const check = async (name, fn) => {
  try {
    await fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── 1. The pure rules ──────────────────────────────────────────────── */

await check("an answer that is not a settings object is 'not known', never 'off'", () => {
  for (const bad of [null, undefined, {}, [], "off", 0]) {
    assert.equal(R.sandboxView(bad), null, JSON.stringify(bad));
  }
});

await check("OFF, waiting and ON map to the switch and keep the PC's own lines", () => {
  const off = R.sandboxView({
    enabled: false,
    waiting: false,
    line: "Off. The AI model is not offered the data and maths sandbox.",
  });
  assert.equal(off.enabled, false);
  assert.equal(off.checked, false);
  assert.match(off.line, /^Off\./);

  const waiting = R.sandboxView({
    enabled: false,
    waiting: true,
    line: "Waiting for your approval.",
  });
  assert.equal(waiting.checked, true, "a waiting card shows the switch on, so it can be taken back");
  assert.equal(waiting.enabled, false);
  assert.match(waiting.line, /Waiting/);

  const on = R.sandboxView({
    enabled: true,
    waiting: false,
    line: "On. The AI model is offered the data and maths sandbox.",
  });
  assert.equal(on.checked, true);
  assert.equal(on.enabled, true);
});

await check("what the card did is the PC's sentence, not a word this page makes up", () => {
  const denied = R.sandboxView({
    enabled: false,
    waiting: false,
    line: "The card was turned down, so the AI model is still not offered the data sandbox.",
    status: "The card was turned down, so the AI model is still not offered the data sandbox.",
  });
  assert.match(denied.line, /turned down/);
  assert.equal(denied.checked, false);
  // A line this page cannot read is "" - an empty line, never a made-up state.
  assert.equal(R.sandboxView({ enabled: false, line: 7 }).line, "");
});

await check("an old PC's 404 or 501 becomes one sentence naming the one command", () => {
  for (const why of ["HTTP 404", "HTTP 501", new Error("HTTP 404 Not Found")]) {
    const said = R.refusedWords(why);
    assert.equal(said, R.MISSING);
    assert.match(said, /add-plugin\.ps1 -Name sandbox/);
  }
});

await check("a JSON refusal is shown in its own words; a bridge error is not dumped raw", () => {
  const said = R.refusedWords(
    'HTTP 500 {"ok": false, "error": "the switch could not be saved (AccessDenied)"}',
  );
  assert.equal(said, "the switch could not be saved (AccessDenied)");
  assert.doesNotMatch(R.refusedWords("HTTP 500"), /HTTP/);
  assert.doesNotMatch(R.refusedWords("undefined"), /undefined/);
});

/* ── 2. The wiring, read from the real files ───────────────────────── */

await check("the page draws the row and loads the script, in its own card", () => {
  const html = read("src/settings.html");
  assert.ok(html.includes('id="sandbox"'), "no sandbox card");
  const start = html.indexOf('id="sandbox"');
  const card = html.slice(start, html.indexOf("</section>", start));
  assert.ok(card.includes('id="sbx-switch"'), "no switch");
  assert.ok(card.includes('id="sbx-switch-label"'), "no label");
  assert.ok(card.includes('id="sbx-line"'), "no state line");
  assert.ok(html.includes('src="sandbox-settings.js"'), "the page does not load the script");
  assert.ok(html.includes('href="#sandbox"'), "the jump list cannot reach it");
  // Nothing to type into, and nothing about a script or a file: this is a
  // switch, and the PC's words are already decided there.
  assert.ok(!/type="(text|url|password)"(?![^>]*readonly)/.test(card), "an editable box");
  assert.ok(!/\btextarea\b/.test(card), "a text area");
});

await check("the page calls ONE command, and the POST carries only a boolean", () => {
  const js = read("src/sandbox-settings.js");
  const calls = [...js.matchAll(/invoke\("([a-z_]+)"/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(calls)], ["sandbox_exec"], calls);
  assert.match(js, /action: on \? "on" : "off"/);
  assert.ok(!/run_data_script|python|files|code/.test(js), "the page mentions a script or a file");
  const rs = read("src-tauri/src/sandbox_exec.rs");
  assert.match(rs, /"on" => serde_json::json!\(\{ "enabled": true \}\)/);
  assert.match(rs, /"off" => serde_json::json!\(\{ "enabled": false \}\)/);
  assert.equal([...rs.matchAll(/PATH: &str = "([^"]+)"/g)].map((m) => m[1])[0], "/api/sandbox");
});

await check("turning it on is held on a stale link; turning it off never is", () => {
  const rs = read("src-tauri/src/sandbox_exec.rs");
  assert.match(rs, /if action == "on" && look::stale\(&app\)/);
  assert.ok(!/action == "off" && look::stale/.test(rs), "OFF must never be held");
});

await check("the command is registered in Rust, permitted, and granted to Settings only", () => {
  assert.match(read("src-tauri/src/lib.rs"), /sandbox_exec::sandbox_exec,/);
  assert.match(read("src-tauri/build.rs"), /"sandbox_exec",/);
  assert.ok(existsSync(join(HERE, "..", "src-tauri/permissions/autogenerated/sandbox_exec.toml")));
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /identifier = "sandbox-exec"/);
  assert.match(surfaces, /\["allow-sandbox-exec"\]/);
  assert.ok(JSON.parse(read("src-tauri/capabilities/settings.json")).permissions.includes("sandbox-exec"));
  for (const f of ["brain.json", "hud.json", "quickbar.json", "widget.json", "faces.json",
                   "floating.json", "live-badge.json", "onboarding.json", "watch-badge.json"]) {
    const path = join(HERE, "..", "src-tauri/capabilities", f);
    if (!existsSync(path)) continue;
    const cap = JSON.parse(readFileSync(path, "utf8"));
    assert.ok(!cap.permissions.includes("sandbox-exec"), `${f} must not hold the sandbox switch`);
  }
});

await check("the settings catalogue carries the row, and both apps read one generated file", () => {
  const cases = JSON.parse(read("tests/fixtures/settings-cases.json"));
  const row = cases.rows.find((r) => r.id === "sbx-switch");
  assert.ok(row, "the generated catalogue has no sbx-switch row");
  assert.equal(row.section, "sandbox");
  assert.equal(row.setting, "sandbox_exec");
  const phone = readFileSync(
    join(HERE, "..", "..", "jarvis-client", "app", "src", "test", "resources", "contract",
         "settings-cases.json"),
  );
  assert.deepEqual(phone, readFileSync(join(HERE, "..", "tests", "fixtures", "settings-cases.json")));
});

await check("the sandbox tool is described by the PC, not by this page", () => {
  const js = read("src/sandbox-settings.js");
  const rules = read("src/sandbox-rules.js");
  for (const src of [js, rules]) {
    assert.ok(!/Off\. The AI model is not offered/.test(src),
              "a state sentence is typed into the page instead of read from the PC");
  }
  // No route of its own, no fetch, no token: every call goes through Rust.
  assert.ok(!/\bfetch\(|X-Jarvis-Token|Authorization/.test(js + rules));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
