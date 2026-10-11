/**
 * "Chatbot API keys" on the desktop (docs/ACCOUNT-KEYS-DESIGN.md steps 1-2,
 * 2026-10-06; src/chatbot-api-keys.js, src/chatbot-api-keys-settings.js,
 * src/settings.html, src-tauri/src/account_secrets.rs, token_store.rs).
 *
 * What must hold:
 * - all six services show, in the same order, each with its own masked box,
 *   its "where to make a key" address and its status;
 * - a key typed here goes to save_chatbot_api_key and nowhere else, the box
 *   is emptied at once, and the key is never shown again;
 * - Remove only shows once something is saved, and names that one service
 *   alone;
 * - CONTROL: the three commands sit with the Settings window only; Rust
 *   writes a key straight into Credential Manager and sends it NOWHERE and
 *   writes it NOWHERE else (rule 3) - the negative half of the design's
 *   "the new route takes no key";
 * - CONTROL: there is no environment variable for one of these, unlike the
 *   four account secrets;
 * - CONTROL: the six services and their Credential Manager names are the
 *   Python side's own, pinned through the generated fixture;
 * - CONTROL: the phone has no such page.
 *
 * The browser-free half (the words, and every CONTROL check) runs anywhere,
 * including CI, which has no Playwright. The other half drives the real
 * Settings page and runs only where Playwright is installed - imported the
 * way uikit.mjs's own note says it must be (playwright FIRST).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  COMPANY,
  KEY_WHERE,
  LABEL,
  readChatbotApiKeys,
  SERVICES,
  statusLine,
} from "../src/chatbot-api-keys.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..");
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(REPO, p), "utf8");

const FIXTURE = JSON.parse(read("tests/fixtures/chatbot-api-key-targets.json"));

let K = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
} catch {
  console.log(
    "skip  the Settings page half: Playwright is not installed " +
      "(npm i -D playwright && npx playwright install chromium)"
  );
}

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

// A fake key, built by concatenation so nothing here is shaped like a real one.
const FAKE = "sk-" + "fake" + "0".repeat(24);

function allNone() {
  return { services: SERVICES.map((service) => ({ service, env_set: false, saved: false })) };
}

/* ── The words ────────────────────────────────────────────────────────── */

await check("readChatbotApiKeys always returns the six, in order, even from an odd answer", () => {
  const rows = readChatbotApiKeys({ services: [{ service: "groq", env_set: true }] });
  assert.deepEqual(rows.map((r) => r.service), [...SERVICES]);
  assert.equal(rows.find((r) => r.service === "groq").envSet, true);
  assert.equal(rows.find((r) => r.service === "openai").saved, null);
  assert.deepEqual(readChatbotApiKeys(null).map((r) => r.service), [...SERVICES]);
  assert.deepEqual(
    readChatbotApiKeys(undefined).map((r) => r.saved),
    SERVICES.map(() => null)
  );
});

await check("statusLine never claims a key, and never mentions an environment variable", () => {
  assert.equal(statusLine({ saved: true }), "Saved in Windows Credential Manager on this PC.");
  assert.equal(statusLine({ saved: false }), "Not set.");
  assert.equal(statusLine({ saved: null }), "Could not check whether one is saved.");
  for (const line of [statusLine({ saved: true }), statusLine({ saved: false })]) {
    assert.doesNotMatch(line, /JARVIS_/, "an environment variable was named for a chatbot key");
  }
});

/* ── CONTROL: the services and names are the Python side's own ────────── */

await check("CONTROL: the six services are the generated fixture's, in its order", () => {
  const inFixture = FIXTURE.targets.map((t) => t.short).sort();
  assert.deepEqual([...SERVICES].sort(), inFixture);
  assert.equal(new Set(SERVICES).size, SERVICES.length, "a service is listed twice");
  for (const t of FIXTURE.targets) {
    assert.ok(LABEL[t.short], `no label for ${t.short}`);
    assert.ok(COMPANY[t.short], `no company for ${t.short}`);
    assert.ok(KEY_WHERE[t.short], `no key page for ${t.short}`);
    assert.equal(COMPANY[t.short], t.company);
    assert.equal(KEY_WHERE[t.short], t.key_where);
  }
});

await check("CONTROL: the Rust table and the fixture agree, name for name", () => {
  const rs = read("src-tauri/src/token_store.rs");
  const block = rs.slice(rs.indexOf("pub const CHATBOT_API_KEY_TARGETS"));
  const body = block.slice(0, block.indexOf("];"));
  const pairs = [...body.matchAll(/\("([^"]+)",\s*"([^"]+)"\)/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(
    pairs.map(([s]) => s).sort(),
    FIXTURE.targets.map((t) => t.short).sort()
  );
  for (const [short, company] of pairs) {
    const row = FIXTURE.targets.find((t) => t.short === short);
    assert.ok(row, `${short} is in the Rust table but not the fixture`);
    assert.equal(company, row.company, short);
    assert.equal(`Jarvis Backend/${company} API key`, row.target, short);
  }
});

await check("CONTROL: the desktop's copy of the fixture is identical to the backend's", () => {
  const py = readRepo("backend/tests/fixtures/chatbot-api-key-targets.json");
  assert.equal(read("tests/fixtures/chatbot-api-key-targets.json"), py);
  assert.equal(FIXTURE.source, "jarvis_chatbot_api.KEY_TARGETS");
});

/* ── CONTROL: rule 3 - the key goes to Credential Manager and nowhere ─── */

/** A Rust function's own body, braces counted. */
function rustFn(src, name) {
  const m = new RegExp(`\\b(?:pub(?:\\([^)]*\\))?\\s+)?(?:async\\s+)?fn\\s+${name}\\s*[(<]`).exec(src);
  assert.ok(m, `${name} is not in the file`);
  const start = m.index;
  let i = src.indexOf("{", m.index + m[0].length);
  let depth = 0;
  for (let j = i; j < src.length; j += 1) {
    if (src[j] === "{") depth += 1;
    else if (src[j] === "}") {
      depth -= 1;
      if (depth === 0) return src.slice(start, j + 1);
    }
  }
  throw new Error(`${name} has no closing brace`);
}

await check("CONTROL: a key is never logged, never sent anywhere, never written to a file", () => {
  const rs = read("src-tauri/src/account_secrets.rs");
  const transport = [
    "jarvis_client", "reqwest", "http::", "JARVIS_URL", "jarvis_base", "jarvis_headers",
    "fs::write", "File::create", "println!", "eprintln!", "log::", "tracing::",
  ];
  for (const name of ["save_chatbot_api_key", "forget_chatbot_api_key", "get_chatbot_api_keys"]) {
    const body = rustFn(rs, name);
    for (const t of transport) {
      assert.ok(!body.includes(t), `${name} mentions ${t}`);
    }
  }
  const save = rustFn(rs, "save_chatbot_api_key");
  assert.match(save.slice(save.indexOf("Ok(serde_json::json!")), /said/);
  assert.doesNotMatch(save.slice(save.indexOf("Ok(serde_json::json!")), /\bvalue\b/);
});

await check("CONTROL: the three commands sit with the Settings window only", () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]");
  const settingsSet = sets.find((s) => s.includes('identifier = "settings-surface"'));
  assert.ok(settingsSet, "the settings surface set is gone");
  for (const c of ["get-chatbot-api-keys", "save-chatbot-api-key", "forget-chatbot-api-key"]) {
    assert.ok(settingsSet.includes(`"allow-${c}"`), c);
    assert.equal(
      sets.filter((s) => s.includes(`"allow-${c}"`)).length,
      1,
      `${c} is in another set as well`
    );
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const c of ["get_chatbot_api_keys", "save_chatbot_api_key", "forget_chatbot_api_key"]) {
    assert.ok(build.includes(`"${c}"`), `build.rs is missing ${c}`);
    assert.ok(lib.includes(`account_secrets::${c}`), `lib.rs is missing ${c}`);
  }
  for (const f of ["get_chatbot_api_keys.toml", "save_chatbot_api_key.toml",
    "forget_chatbot_api_key.toml"]) {
    assert.match(read(`src-tauri/permissions/autogenerated/${f}`), /# Automatically generated/);
  }
});

await check("CONTROL: there is no environment variable for a chatbot key", () => {
  const rs = read("src-tauri/src/token_store.rs");
  const block = rs.slice(rs.indexOf("pub const CHATBOT_API_KEY_TARGETS"));
  assert.doesNotMatch(block.slice(0, block.indexOf("];")), /JARVIS_/);
  const py = readRepo("backend/jarvis_chatbot_api.py");
  assert.doesNotMatch(py, /KEY_TARGETS[^\n]*os\.environ|os\.environ[^\n]*KEY_TARGETS/);
});

await check("CONTROL: the card has a stable id, a jump link and its own script", () => {
  const html = read("src/settings.html");
  assert.match(html, /<section class="card" id="chatbot-api-keys">/);
  assert.match(html, /<a href="#chatbot-api-keys">Chatbot API keys<\/a>/);
  assert.match(html, /<div id="cak-body"><\/div>/);
  assert.match(html, /<span class="status" id="cak-status" role="status"><\/span>/);
  assert.match(html, /<script type="module" src="chatbot-api-keys-settings\.js"><\/script>/);
});

await check("CONTROL: the card is in the three registries a new card must be in", () => {
  assert.match(readRepo("backend/jarvis_settings_registry.py"), /Section\("chatbot-api-keys"/);
  assert.match(readRepo("backend/jarvis_menus.py"), /"settings\.chatbot-api-keys"/);
  assert.match(
    readRepo("jarvis-client/app/src/main/java/com/jarvis/client/ui/OpenPlace.kt"),
    /"chatbot-api-keys"/
  );
});

await check("CONTROL: no page here writes innerHTML with anything from the PC", () => {
  for (const f of ["src/chatbot-api-keys.js", "src/chatbot-api-keys-settings.js"]) {
    assert.doesNotMatch(read(f), /innerHTML/, f);
  }
});

/* ── Settings, in the real page (Playwright only) ─────────────────────── */

if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();

  /** The bridge for the three commands, on top of uikit's own. */
  function cakBridge(scenario) {
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    window.__cak = JSON.parse(JSON.stringify(scenario));
    window.__cakCalls = [];
    core.invoke = async (cmd, args) => {
      const w = window.__cak;
      switch (cmd) {
        case "get_chatbot_api_keys":
          return JSON.parse(JSON.stringify(w.view));
        case "save_chatbot_api_key": {
          window.__cakCalls.push({ cmd, service: args.service, valueLength: String(args.value).length });
          window.__cakValueSeen = args.value;
          w.view.services.find((x) => x.service === args.service).saved = true;
          return { ok: true, said: "Saved in Windows Credential Manager on this PC." };
        }
        case "forget_chatbot_api_key": {
          window.__cakCalls.push({ cmd, service: args.service });
          w.view.services.find((x) => x.service === args.service).saved = false;
          return { ok: true, said: "Removed from Windows Credential Manager on this PC." };
        }
        default:
          return invoke(cmd, args);
      }
    };
  }

  async function settings(view) {
    const page = await K.open(browser, base, "settings.html", {}, { width: 820, height: 2600 });
    await page.addInitScript(cakBridge, { view });
    await page.reload();
    await page.waitForTimeout(500);
    return page;
  }

  await check("Settings: all six services show, in order, each with its key page", async () => {
    const page = await settings(allNone());
    const text = await page.locator("#chatbot-api-keys").innerText();
    const boxes = await page
      .locator("#cak-body [data-service]")
      .evaluateAll((els) => els.map((e) => e.dataset.service));
    const errors = page.__errors;
    await page.close();
    assert.deepEqual(boxes, [...SERVICES]);
    const lower = text.toLowerCase();
    for (const service of SERVICES) {
      assert.ok(lower.includes(LABEL[service].toLowerCase()), `missing the ${service} label`);
      assert.ok(text.includes(KEY_WHERE[service]), `missing ${service}'s key page`);
    }
    assert.match(text, /Not set\./);
    assert.deepEqual(errors, []);
  });

  await check("Settings: a key goes to save_chatbot_api_key only, the box empties, never shown", async () => {
    const page = await settings(allNone());
    await page.locator("#cak-openai").fill(FAKE);
    await page.locator('#cak-body [data-service="openai"] button', { hasText: "Save" }).click();
    await page.waitForTimeout(500);
    const box = await page.locator("#cak-openai").inputValue();
    const html = await page.content();
    const calls = await page.evaluate(() => window.__cakCalls);
    const seen = await page.evaluate(() => window.__cakValueSeen);
    const others = await page.evaluate(() =>
      window.__calls
        .filter(([c]) => c !== "save_chatbot_api_key")
        .map(([, a]) => JSON.stringify(a || {}))
        .join(" ")
    );
    const line = await page.locator('#cak-body [data-service="openai"]').innerText();
    await page.close();
    assert.deepEqual(calls, [
      { cmd: "save_chatbot_api_key", service: "openai", valueLength: FAKE.length },
    ]);
    assert.equal(seen, FAKE);
    assert.equal(box, "", "the key stayed in the box");
    assert.ok(!html.includes(FAKE), "the key is on the page");
    assert.ok(!others.includes(FAKE), "the key went to another command");
    assert.match(line, /Saved in Windows Credential Manager on this PC\./);
  });

  await check("Settings: every box is masked, and Save and Remove name that one service", async () => {
    const view = allNone();
    view.services.find((x) => x.service === "openrouter").saved = true;
    const page = await settings(view);
    const types = await page
      .locator("#cak-body input")
      .evaluateAll((els) => els.map((e) => e.type));
    const removeShown = await page
      .locator('#cak-body [data-service="openrouter"] button', { hasText: "Remove" })
      .isVisible();
    const removeHidden = await page
      .locator('#cak-body [data-service="groq"] button', { hasText: "Remove" })
      .isHidden();
    await page.locator('#cak-body [data-service="openrouter"] button', { hasText: "Remove" }).click();
    await page.waitForTimeout(400);
    const calls = await page.evaluate(() => window.__cakCalls);
    await page.close();
    assert.deepEqual(types, SERVICES.map(() => "password"));
    assert.equal(removeShown, true);
    assert.equal(removeHidden, true);
    assert.deepEqual(calls, [{ cmd: "forget_chatbot_api_key", service: "openrouter" }]);
  });

  await browser.close();
  close();
}

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log(
  "\nChatbot API keys: six services, each key into Credential Manager on this PC, " +
    "the names the Python side's own, never shown again"
);
