/**
 * Settings -> "What this backend supports" (its own card, after About): the capability names
 * GET /api/version reports, as the phone lists them under "This backend"
 * (BrainScreen.kt: sorted, what it has, then "Not on this backend").
 *
 * Which names count as "has it" is decided in the Rust
 * (commands.rs `capability_present`, a port of the phone's
 * `asCapabilityFlag`); its Rust tests pin that rule and the real
 * jarvis_events.hello() shape. This checks the page, and reads the Rust for
 * the rule, the headers and who may call it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1400 };
const open = (caps) => K.open(browser, base, "settings.html", caps ? { caps } : {}, VIEW);
const look = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const items = (id) => ($(id) && !$(id).hidden ? [...$(id).querySelectorAll("li")].map((l) => l.innerText) : []);
  return {
    heading: $("caps-heading") ? $("caps-heading").textContent.trim() : null,
    stateHidden: $("caps-state").hidden,
    state: $("caps-state").innerText,
    bodyHidden: $("caps-body").hidden,
    server: $("caps-server-row").hidden ? null : $("caps-server").innerText,
    api: $("caps-api").innerText,
    on: items("caps-on"),
    off: items("caps-off"),
    offHeading: $("caps-off-heading").hidden ? null : $("caps-off-heading").textContent.trim(),
    none: !$("caps-none").hidden,
  };
});

await check("the list: the server, the API number, what it has and what it does not, in order", async () => {
  const page = await open();
  const s = await look(page);
  const errors = page.__errors;
  await page.close();
  assert.equal(s.heading, "What this backend supports");
  assert.equal(s.stateHidden, true);
  assert.equal(s.bodyHidden, false);
  assert.equal(s.server, "jarvis-hud");
  assert.equal(s.api, "1");
  assert.deepEqual(s.on, ["memory", "power", "voice"]);
  assert.equal(s.offHeading, "Not on this backend");
  assert.deepEqual(s.off, ["appearance", "approvals", "connectors", "models", "persona", "skills"]);
  assert.equal(s.none, false);
  assert.deepEqual(errors, []);
});

await check("nothing reported: \"None reported.\", and no empty \"not on this backend\" heading", async () => {
  const page = await open({ answer: { server: "", api: null, on: [], off: [] } });
  const s = await look(page);
  await page.close();
  assert.equal(s.none, true);
  assert.equal(s.offHeading, null);
  assert.equal(s.server, null, "an empty server name is shown");
  assert.equal(s.api, "not reported");
});

await check("no answer: a sentence, not a code", async () => {
  const page = await open({ fails: "Jarvis is not answering at http://127.0.0.1:4719. Is it running?" });
  const s = await look(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.equal(s.state, "Jarvis could not be asked what it supports. Jarvis is not answering at http://127.0.0.1:4719. Is it running?");
});

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL (Rust): the phone's rule for \"has it\", names only, the usual headers, nothing logged", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const rule = fnBody(rust, "pub(crate) fn capability_present(");
  assert.match(rule, /Value::Bool\(b\) => \*b/);
  assert.match(rule, /Value::String\(s\) => !s\.is_empty\(\) && !s\.eq_ignore_ascii_case\("false"\)/);
  assert.match(rule, /Value::Object\(m\) => !m\.is_empty\(\)/);
  assert.match(rule, /_ => false/);
  const answer = fnBody(rust, "pub(crate) fn capabilities_answer(");
  assert.match(answer, /"on": on,/);
  assert.doesNotMatch(answer, /"capabilities":/, "the capability VALUES are passed to the page");
  const cmd = fnBody(rust, "pub async fn get_backend_capabilities(");
  assert.match(cmd, /\.headers\(jarvis_headers\(&app\)\?\)/);
  assert.match(cmd, /format!\("\{base\}\/api\/version"\)/);
  assert.doesNotMatch(cmd, /println!|eprintln!|log::|tracing::|dbg!|logfile|token/i);
  // The phone's own rule, for comparison: the port must say the same.
  const kt = readFileSync(join(HERE, "..", "..", "jarvis-client", "app", "src", "main", "java", "com",
    "jarvis", "client", "net", "ApiModels.kt"), "utf8");
  assert.match(kt, /is JsonPrimitive -> booleanOrNull \?: \(isString && content\.isNotEmpty\(\) && content != "false"\)/,
    "the phone's rule changed; change capability_present to match");
  assert.match(kt, /is JsonObject -> isNotEmpty\(\)/);
});

await check("CONTROL: only the settings window may read it", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const holders = toml.split("[[set]]").slice(1)
    .filter((s) => s.includes('"allow-get-backend-capabilities"'))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders, ["settings-surface"]);
  assert.ok(read("src-tauri/build.rs").includes('"get_backend_capabilities"'));
  assert.ok(read("src-tauri/src/lib.rs").includes("commands::get_backend_capabilities,"));
  assert.match(read("src-tauri/permissions/autogenerated/get_backend_capabilities.toml"),
    /commands.allow = \["get_backend_capabilities"\]/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\n\"What this backend supports\" holds");
process.exit(fails.length ? 1 : 0);
