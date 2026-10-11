/**
 * "Prompt coach" on the desktop (2026-10-08, extended 2026-10-09;
 * src/prompt-coach-settings.js, src/prompt-coach-panel.js,
 * src-tauri/src/prompt_coach.rs, backend/jarvis_prompt_coach.py,
 * prompt-coach.patch).
 *
 * WHAT THIS SUITE IS FOR. The coach used to be one on/off switch, and the
 * owner's verdict was that it had to be *"effective and have multiple
 * settings, including an enable and disable"*. Four arrived on 2026-10-09 -
 * when it speaks up, how blunt it is, what it coaches on, per-platform
 * behaviour - and every word of them comes from the PC. So what must hold:
 *
 * - Settings draws one row per setting the PC sent, in the PC's own order,
 *   with the PC's own names and lines - and INVENTS NOTHING. A PC that sends
 *   no rows (an older backend) draws the switch alone, exactly as before;
 * - a row with no key, no choices, or a value that is not one of its own
 *   choices is DROPPED rather than drawn: half a row is a picker nothing is
 *   selected in, which looks built and says nothing;
 * - picking a choice sends `{key, value}` - the pair, never a direction and
 *   never a second copy of the list;
 * - the PC's own refusal (an unknown key or value) is shown in its words, and
 *   the picker goes back to what the PC last said rather than keeping a choice
 *   the PC refused;
 * - the master switch still works exactly as it did, including for a PC that
 *   answers with none of the four;
 * - CONTROL: both calls sit with the Settings window only, the read is a GET
 *   and the write is a POST to the settings route, and there is exactly ONE
 *   write call site.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readGroup, readGroups, readPromptCoach } from "../src/prompt-coach-settings.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** A real answer, in the shape `jarvis_prompt_coach.status()` writes it. */
const VIEW = {
  ok: true,
  on: true,
  why: "",
  label: "Prompt coach",
  detail: "Off (the default): nothing is read and there is no Coach this button.",
  heading: "Prompt coach",
  button: "Coach this",
  send_mine: "Send mine",
  send_suggestion: "Send the suggestion",
  targets: ["local", "openai_api", "gemini_web"],
  stale_days: 180,
  settings: [
    {
      key: "speaks_up",
      name: "when it speaks up",
      value: "any",
      default: "any",
      choices: [
        { value: "any", name: "Whenever it has something to say", detail: "Every gap it can see." },
        { value: "weak", name: "Only when the prompt is weak", detail: "A 7 or more is passed." },
      ],
    },
    {
      key: "bluntness",
      name: "how blunt it is",
      value: "gentle",
      default: "gentle",
      choices: [
        { value: "gentle", name: "A gentle nudge", detail: "Suggestions." },
        { value: "direct", name: "Direct about what is wrong", detail: "Said plainly." },
      ],
    },
    {
      key: "coaches_on",
      name: "what it coaches on",
      value: "shape",
      default: "shape",
      choices: [
        { value: "shape", name: "Shape only - length and clarity", detail: "How it is built." },
        { value: "content", name: "Content too", detail: "And whether it asked the right thing." },
      ],
    },
    {
      key: "platform",
      name: "per-platform behaviour",
      value: "same",
      default: "same",
      choices: [
        { value: "same", name: "The phone behaves the same as the PC", detail: "One setting, both apps." },
        { value: "quieter_phone", name: "Quieter on the phone", detail: "Two gaps at most there." },
      ],
    },
  ],
};

/* ── The reading half ─────────────────────────────────────────────────── */

await check("the PC's rows survive, in the PC's order, in the PC's words", async () => {
  const v = readPromptCoach(VIEW);
  assert.equal(v.available, true);
  assert.equal(v.on, true);
  assert.deepEqual(v.groups.map((g) => g.key),
    ["speaks_up", "bluntness", "coaches_on", "platform"]);
  assert.equal(v.groups[0].name, "when it speaks up");
  assert.deepEqual(v.groups[0].choices.map((c) => c.value), ["any", "weak"]);
  assert.equal(v.groups[0].choices[1].name, "Only when the prompt is weak");
  assert.equal(v.groups[0].value, "any");
  // The AIs it knows about, and the number behind "may be out of date".
  assert.deepEqual(v.targets, ["local", "openai_api", "gemini_web"]);
  assert.equal(v.staleDays, 180);
});

await check("an older PC draws no pickers, and still works", async () => {
  const old = readPromptCoach({
    ok: true, on: false, why: "", label: "Prompt coach",
    detail: "Off (the default): nothing is read.",
  });
  assert.equal(old.available, true);
  assert.deepEqual(old.groups, [], "no settings list: the switch alone, as before");
  assert.deepEqual(old.targets, []);
  const gone = readPromptCoach({ available: false, why: "run apply-patches.ps1 on the PC." });
  assert.equal(gone.available, false);
  assert.deepEqual(gone.groups, []);
});

await check("half a row is dropped, never drawn as an empty picker", async () => {
  assert.equal(readGroup({ name: "no key", value: "a", choices: [{ value: "a" }] }), null);
  assert.equal(readGroup({ key: "k", value: "a", choices: [] }), null);
  assert.equal(readGroup({ key: "k", value: "a" }), null);
  // A current value that is not one of its own choices is not a state this
  // page can show, so nothing is shown.
  assert.equal(readGroup({ key: "k", value: "z", choices: [{ value: "a" }] }), null);
  assert.equal(readGroup("nope"), null);
  assert.equal(readGroup(null), null);
  // A choice with no value is not a choice; one with no name falls back to the
  // value rather than to a blank line.
  const g = readGroup({ key: "k", value: "a", choices: [{ value: "a" }, { name: "no value" }] });
  assert.deepEqual(g.choices, [{ value: "a", name: "a", detail: "" }]);
  assert.deepEqual(readGroups("not a list"), []);
  assert.deepEqual(readGroups([{ key: "k", value: "z", choices: [{ value: "a" }] },
                               { key: "j", value: "a", choices: [{ value: "a" }] }]).map((x) => x.key),
    ["j"], "the good row beside a bad one is still drawn");
});

/* ── Settings, in a real page ─────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

/**
 * The bridge, and the one thing about it that is easy to get wrong.
 *
 * `set_prompt_coach` takes ONE `change` object (`CoachChange` in
 * prompt_coach.rs), and this mock binds a page's arguments to the command's
 * parameters POSITIONALLY, exactly the way tests/uikit.mjs's own bridge does.
 * That is not decoration: with the first version of this - three loose
 * `Option`s declared `(enabled, key, value)` - a page sending `{key, value}`
 * arrived as `enabled = <the key>`, and this suite is where that was seen.
 * `window.__coachCalls` records the BOUND result, because that is what the
 * Rust side actually receives.
 */
function coachBridge(data = {}) {
  const core = window.__TAURI__.core;
  const invoke = core.invoke;
  window.__coachCalls = [];
  window.__coachView = data.view === "old" ? "old" : JSON.parse(JSON.stringify(data.view));
  window.__coachRefuse = data.refuse === true;
  core.invoke = async (cmd, args) => {
    if (cmd === "get_prompt_coach") {
      if (window.__coachView === "old") {
        return { available: false, why: "Your PC's Jarvis cannot show the prompt coach yet - run apply-patches.ps1 on the PC." };
      }
      return JSON.parse(JSON.stringify(window.__coachView));
    }
    if (cmd === "set_prompt_coach") {
      // The command's one parameter, `change`, holding only what was typed.
      const change = args?.change || {};
      window.__coachCalls.push({ cmd, change: JSON.parse(JSON.stringify(change)) });
      if (window.__coachRefuse) {
        throw new Error("\"shouty\" is not one of the choices for bluntness; it has: gentle, direct.");
      }
      // A real PC answers with the whole state, so the page can paint the
      // truth from the reply rather than from what it hoped.
      const out = JSON.parse(JSON.stringify(window.__coachView));
      if (typeof change.enabled === "boolean") out.on = change.enabled;
      if (typeof change.key === "string" && change.key) {
        for (const g of out.settings || []) if (g.key === change.key) g.value = change.value;
      }
      window.__coachView = out;
      return JSON.parse(JSON.stringify(out));
    }
    return invoke(cmd, args);
  };
}

async function settings(data = {}) {
  const page = await K.open(browser, base, "settings.html", {}, { width: 900, height: 2000 });
  await page.addInitScript(coachBridge, data);
  await page.reload();
  // Wait for the card to have ANSWERED rather than for a fixed time.
  await page
    .waitForFunction(
      () => {
        const groups = document.querySelectorAll("#coach-groups .coach-group").length;
        const state = (document.getElementById("coach-state") || {}).textContent || "";
        return groups > 0 || state.trim().length > 0;
      },
      null,
      { timeout: 15000 },
    )
    .catch(() => {});
  return page;
}

/** Waits until `fn` is true in the page. If it never is, the assertion says why. */
async function settled(page, fn, timeout = 10000) {
  await page.waitForFunction(fn, null, { timeout }).catch(() => {});
}

await check("Settings: one row per setting, every word the PC's", async () => {
  const page = await settings({ view: VIEW });
  const text = await page.locator("#prompt-coach").innerText();
  const keys = await page.locator("#coach-groups .coach-group").evaluateAll((els) => els.map((e) => e.dataset.key));
  const picked = await page.locator("#coach-groups input:checked").evaluateAll((els) => els.map((e) => `${e.dataset.key}=${e.value}`));
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(keys, ["speaks_up", "bluntness", "coaches_on", "platform"]);
  assert.deepEqual(picked, ["speaks_up=any", "bluntness=gentle", "coaches_on=shape", "platform=same"]);
  assert.ok(text.includes("when it speaks up"), "the row's own name");
  assert.ok(text.includes("Only when the prompt is weak"), "a choice's own name");
  assert.ok(text.includes("A 7 or more is passed."), "a choice's own line");
  assert.ok(text.includes("Prompt coach"), "the switch is still there");
  assert.deepEqual(errors, []);
});

await check("Settings: picking a choice sends the pair, once", async () => {
  const page = await settings({ view: VIEW });
  await page.locator('#coach-groups .coach-group[data-key="bluntness"] input[value="direct"]').click();
  await settled(page, () => (window.__coachCalls || []).length > 0);
  const calls = await page.evaluate(() => window.__coachCalls);
  await page.close();
  // THE ARGUMENT SHAPE IS A CONTRACT, not a preference. One nested `change`
  // object, because Tauri binds a page's arguments onto the command's
  // parameters POSITIONALLY: three loose `Option`s meant `{key, value}`
  // reached a `(enabled, key, value)` command as `enabled = <the key>`. That
  // is not a guess - it is what this suite saw when the Rust was written the
  // other way round, and it is why the command now takes one struct.
  assert.deepEqual(calls, [{ cmd: "set_prompt_coach",
    change: { key: "bluntness", value: "direct" } }]);
});
await check("Settings: the PC's refusal is its own sentence, and the picker goes back", async () => {
  const page = await settings({ view: VIEW, refuse: true });
  await page.locator('#coach-groups .coach-group[data-key="bluntness"] input[value="direct"]').click();
  await settled(page, () => {
    const said = ((document.getElementById("coach-status") || {}).textContent || "").trim();
    return said.length > 0 && said !== "Sending…";
  });
  const status = await page.locator("#coach-status").innerText();
  const picked = await page.locator('#coach-groups .coach-group[data-key="bluntness"] input:checked')
    .evaluate((e) => e.value);
  await page.close();
  assert.equal(status, "\"shouty\" is not one of the choices for bluntness; it has: gentle, direct.");
  assert.equal(picked, "gentle", "the picker shows what the PC has, not what was refused");
});

await check("Settings: the master switch still works, alone on an older PC", async () => {
  const page = await settings({ view: VIEW });
  await page.locator("#coach-enabled").click();
  await settled(page, () => (window.__coachCalls || []).length > 0);
  const calls = await page.evaluate(() => window.__coachCalls);
  await page.close();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].cmd, "set_prompt_coach");
  // The switch's own call, unchanged in meaning: one field, and no key or
  // value at all.
  assert.deepEqual(calls[0].change, { enabled: false });
  // A PC that answers with a switch and no settings at all: no picker is
  // drawn, and no empty box is left behind either.
  const old = await settings({ view: { ok: true, on: true, why: "", label: "Prompt coach", detail: "x" } });
  const hidden = await old.locator("#coach-groups").isHidden();
  const switchOn = await old.locator("#coach-enabled").isChecked();
  await old.close();
  assert.equal(hidden, true, "nothing is drawn where the four would be");
  assert.equal(switchOn, true);
});

await check("Settings: a PC with no such route says so in its own words", async () => {
  const page = await settings({ view: "old" });
  const state = await page.locator("#coach-state").innerText();
  const hidden = await page.locator("#coach-body").isHidden();
  await page.close();
  assert.match(state, /apply-patches\.ps1/);
  assert.equal(hidden, true);
});

await browser.close();
close();

/* ── CONTROL ───────────────────────────────────────────────────────────── */

await check("CONTROL: both calls sit with Settings only, read GET / write POST", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]");
  const settingsSet = sets.find((s) => s.includes('identifier = "settings-surface"'));
  for (const perm of ['"allow-get-prompt-coach"', '"allow-set-prompt-coach"']) {
    assert.ok(settingsSet.includes(perm), perm);
    assert.equal(sets.filter((s) => s.includes(perm)).length, 1, `${perm} is granted once`);
  }
  const build = read("src-tauri/build.rs");
  assert.ok(build.includes('"get_prompt_coach"') && build.includes('"set_prompt_coach"'));
  const rs = read("src-tauri/src/prompt_coach.rs");
  assert.match(rs, /\.get\(format!\("\{base\}\{PROMPT_COACH_PATH\}"\)\)/);
  assert.match(rs, /\.post\(format!\("\{base\}\{SETTING_PATH\}"\)\)/);
  // The one write carries only what it was given, so the switch's own call
  // still sends exactly {"enabled": bool}.
  assert.match(rs, /if let Some\(on\) = change\.enabled \{/);
  assert.match(rs, /if let Some\(name\) = change\.key \{/);
  // The Rust side takes ONE `change` struct, `#[serde(default)]` on every
  // field, so a request that names only one still deserialises - and there is
  // no parameter order for the bridge to get wrong.
  assert.match(rs, /pub struct CoachChange \{/);
  assert.match(rs, /#\[serde\(default\)\]/);
  assert.match(rs, /pub enabled: Option<bool>/);
  assert.match(rs, /pub key: Option<String>/);
  assert.match(rs, /pub value: Option<String>/);
  // The command's own signature, spelled out: the AppHandle and the ONE
  // struct, and no loose Option params for the bridge to line up by position.
  assert.ok(
    rs.includes("pub async fn set_prompt_coach(\n    app: AppHandle,\n    change: CoachChange,\n)"),
    "the command takes `change: CoachChange` and nothing else",
  );
});
await check("CONTROL: one write call site, and it sends a key and a value", async () => {
  const js = read("src/prompt-coach-settings.js");
  const sends = js.match(/invoke\("set_prompt_coach"[^\n]*/g) || [];
  assert.equal(sends.length, 2, "the switch's own call and the choice's");
  assert.match(sends[0], /\{ change: \{ enabled: on \} \}/);
  assert.match(sends[1], /\{ change: \{ key, value \} \}/);
  // And no direction is ever implied: the page sends the value it was told.
  for (const s of sends) assert.doesNotMatch(s, /loosen|stricter|direction|raise|lower\b/i);
  // The four's own names live nowhere in this app: one source, on the PC.
  for (const word of ["Only when the prompt is weak", "A gentle nudge", "Quieter on the phone",
                      "Shape only"]) {
    assert.ok(!js.includes(word), `"${word}" is the PC's line, not this file's`);
    assert.ok(!read("src/settings.html").includes(word), `"${word}" is the PC's line, not the page's`);
  }
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nPrompt coach: one switch, four settings, every word the PC's");
