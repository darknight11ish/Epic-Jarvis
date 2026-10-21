/**
 * tests/voiceprint-ui.mjs - the "Write like me" settings page's own contract.
 *
 * No DOM, no Tauri: parseStatus, forgetAsk and boundedInvoke are pure, and the
 * source is checked for the sinks that would make PC text dangerous - and for
 * the wiring itself: every command the page calls must be registered in
 * lib.rs AND build.rs, granted to the Settings window by exactly one set, and
 * have a generated permission file. That is the class of bug this project has
 * shipped before (a button that silently does nothing, refused at the ACL).
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  BLOCKED,
  DETAIL,
  EMPTY,
  MAX_TEXT,
  TITLE,
  boundedInvoke,
  forgetAsk,
  parseStatus,
  problemWords,
  sampleProblem,
} from "../src/voiceprint-settings.js";

const HERE = dirname(fileURLToPath(import.meta.url));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const ok = (name, cond, detail = "") => assert.ok(cond, `${name}${detail ? `: ${detail}` : ""}`);

test("words are the feature's own", () => {
  ok("title", TITLE === "Write like me");
  ok("detail names the promise", DETAIL.includes("draft") && DETAIL.includes("chatbot"));
});

// The fixture is the answer `jarvis_voiceprint.handle_get("/api/voiceprint")`
// really gives (measured 2026-10-20): samples/count at the top level, and the
// switch, available and scrubber inside "status". A flat fixture is what let a
// switch that always rendered OFF look tested.
test("parseStatus keeps only what it can render", () => {
  const v = parseStatus({
    ok: true, count: 2,
    status: { available: true, enabled: true, scrubber: true, samples: 2 },
    samples: [
      { id: "vp1", text: "Hello [name]", kind: "sample", prompt: "" },
      { id: "vp2", text: "Second", kind: "edit" },
      { nope: true },
    ],
  });
  ok("enabled comes from the PC's own status block", v.enabled === true);
  ok("two valid rows survive", v.samples.length === 2, String(v.samples.length));
  ok("id and text are kept", v.samples[0].id === "vp1" && v.samples[0].text === "Hello [name]");
  ok("a malformed row is dropped, not rendered", !JSON.stringify(v).includes("nope"));
  ok("empty list says so", parseStatus({ samples: [] }).message === EMPTY);
  ok("the switch defaults OFF", parseStatus({}).enabled === false);
  ok("available and scrubber default ON", parseStatus({}).available === true
    && parseStatus({}).scrubber === true);
});

test("forget always asks first, with the sample's own first words", () => {
  const ask = forgetAsk({ id: "vp1", text: "Please send the invoice to Priya at work" });
  ok("asks the question", ask.startsWith("Forget this sample?"));
  ok("quotes the sample", ask.includes("Please send the invoice"));
  ok("says it cannot be undone", ask.includes("cannot be undone"));
});

test("the sample guard refuses empty and over-long text", () => {
  ok("empty refused", sampleProblem("   ") !== "");
  ok("over-long refused", sampleProblem("x".repeat(MAX_TEXT + 1)) !== "");
  ok("ordinary text allowed", sampleProblem("A normal message.") === "");
});

test("problemWords never leaks a bridge error", () => {
  ok("json refused", problemWords('{"error":"x"}') === BLOCKED);
  ok("plain words kept", problemWords("The PC is busy.") === "The PC is busy.");
});

test("boundedInvoke resolves a fast answer and rejects a stalled one in plain words", async () => {
  const fast = await boundedInvoke((cmd, args) => Promise.resolve({ cmd, args }), "voiceprint_status", null);
  ok("fast answer arrives", fast.cmd === "voiceprint_status");
  let rejected = "";
  try {
    await boundedInvoke(() => new Promise(() => {}), "voiceprint_status", null, 20);
  } catch (e) { rejected = String(e.message || e); }
  ok("a stalled invoke is cut off", rejected.includes("30 seconds") || rejected.includes("did not answer"));
  ok("the module bounds the real deadline at 30 s",
    readFileSync(join(HERE, "..", "src", "voiceprint-settings.js"), "utf8").includes("TIMEOUT_MS = 30_000"));
});

test("the page never uses innerHTML on PC text", () => {
  const src = readFileSync(join(HERE, "..", "src", "voiceprint-settings.js"), "utf8");
  ok("no innerHTML sink", !src.includes(".innerHTML"));
  ok("no outerHTML sink", !src.includes(".outerHTML"));
  ok("no insertAdjacentHTML sink", !src.includes("insertAdjacentHTML("));
  ok("text is placed with textContent", src.includes("textContent"));
});

// The mount needs a DOM, so these two wiring rules are pinned as text. Both
// are bugs that type-check, pass every grant check, and fail at runtime:
//
//  * the Tauri command's argument is `on` (voiceprint.rs's own signature, the
//    same word set_humor takes) - sending `enabled`, the HTTP body's field,
//    is refused by Tauri with "missing required key on", so the toggle looks
//    wired and does nothing;
//  * a write must be held while the event stream is stale (rule 4); a read is
//    never held.
test("the switch sends the argument the Rust command really takes", () => {
  const src = readFileSync(join(HERE, "..", "src", "voiceprint-settings.js"), "utf8");
  const call = /boundedInvoke\(invoke,\s*"voiceprint_set_enabled",\s*\{([^}]*)\}/.exec(src);
  ok("the switch invokes voiceprint_set_enabled", Boolean(call));
  ok("it sends `on`", Boolean(call) && /\bon\s*:/.test(call[1]));
  ok("it does not send `enabled` instead", Boolean(call) && !/\benabled\s*:/.test(call[1]));
});

test("a stale link holds the three writes, never the read", () => {
  const src = readFileSync(join(HERE, "..", "src", "voiceprint-settings.js"), "utf8");
  ok("the mount takes an isStale check", /isStale = \(\) => false/.test(src));
  ok("the read is not behind the hold",
    /boundedInvoke\(invoke, "voiceprint_status"\)/.test(src));
  const guarded = (name) => {
    const at = src.indexOf(`"${name}"`);
    if (at < 0) return false;
    // The handler's own `if (!live())` guard is the first thing it does.
    return src.slice(Math.max(0, at - 400), at).includes("if (!live())");
  };
  ok("Keep this sample is held", guarded("voiceprint_add"));
  ok("Forget this sample is held", guarded("voiceprint_forget"));
  ok("the switch is held", guarded("voiceprint_set_enabled"));
});

// The ACL half - the bug class this check exists for: a page that invokes a
// command which lib.rs registers but build.rs never exports has NO permission,
// so every call is refused at runtime and the control silently does nothing.
// The page, the Rust registration, the four generated permission files, the
// surfaces.toml set and the ONE capability that grants it all have to agree.
test("the page, the commands, the grants and the capability agree", () => {
  const root = join(HERE, "..");
  const read = (p) => readFileSync(join(root, p), "utf8");
  const html = read("src/settings.html");
  const manner = read("src/manner-settings.js");
  const lib = read("src-tauri/src/lib.rs");
  const build = read("src-tauri/build.rs");
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  const commands = [
    "voiceprint_status", "voiceprint_add", "voiceprint_forget", "voiceprint_set_enabled",
  ];
  const kebab = (c) => c.replace(/_/g, "-");

  // 1. The page has the empty section and loads the module...
  ok("settings.html has the empty section",
    html.includes('<section id="voiceprint" class="block"></section>'));
  ok("settings.html loads the module",
    html.includes('<script type="module" src="voiceprint-settings.js"></script>'));
  // ...and the card's own module is what mounts it, with the real bridge.
  ok("manner-settings.js imports the mount",
    manner.includes('import { mount as mountVoiceprint } from "./voiceprint-settings.js";'));
  ok("manner-settings.js mounts it into #voiceprint",
    /mountVoiceprint\(document\.getElementById\("voiceprint"\)/.test(manner));
  ok("the mount gets the link's staleness", /isStale:/.test(manner));

  // 2. lib.rs registers the module and every command, and build.rs exports each
  //    one (the generated allow-*/deny-* pair exists only when it does).
  ok("lib.rs declares the module", /pub mod voiceprint;/.test(lib));
  for (const c of commands) {
    ok(`${c} is in generate_handler!`, lib.includes(`voiceprint::${c},`));
    ok(`${c} is in build.rs's commands list`, build.includes(`"${c}"`));
    const file = `src-tauri/permissions/autogenerated/${c}.toml`;
    ok(`${c} has a generated permission file`, existsSync(join(root, file)));
    if (existsSync(join(root, file))) {
      const toml = read(file);
      ok(`${c}'s permission allows exactly it`,
        toml.includes(`commands.allow = ["${c}"]`));
      ok(`${c}'s deny pair exists`, toml.includes(`commands.deny = ["${c}"]`));
    }
  }

  // 3. ONE set names the four allow-* names, and ONE window - Settings - is
  //    granted it; no other capability file mentions the set.
  const block = /\[\[set\]\]\s*identifier = "voiceprint"(.*?)(?=\n\[\[set\]\]|\Z)/s.exec(surfaces);
  ok("surfaces.toml has a voiceprint set", Boolean(block));
  if (block) {
    for (const c of commands) {
      ok(`the voiceprint set allows ${kebab(c)}`,
        block[1].includes(`"allow-${kebab(c)}"`));
    }
  }
  const caps = ["settings", "brain", "hud", "quickbar", "faces", "widget", "floating",
    "live-badge", "watch-badge", "features", "onboarding"];
  for (const name of caps) {
    const path = `src-tauri/capabilities/${name}.json`;
    if (!existsSync(join(root, path))) continue;
    const granted = JSON.parse(read(path)).permissions.includes("voiceprint");
    ok(name === "settings" ? "Settings grants the voiceprint set" : `${name} does not`,
      name === "settings" ? granted : !granted);
  }
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL ${name}\n     ${e && e.message ? e.message : e}`);
  }
}
console.log(`\n${tests.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
