/**
 * Settings -> Second graphics card, and the two other places the desktop
 * meets the second card: the picture check and the model badge.
 *
 * Every status here is REAL: `K.SECOND_CARD` is
 * tests/fixtures/second-card-cases.json, jarvis_second_card.status() for six
 * cases, written by tools/gen_second_card_cases.py. Nothing is hand-made.
 *
 * What must hold (docs/SECOND-CARD.md, JARVIS-API.md section 12):
 * - every switch is visible, and none can be turned on without a capable
 *   second card - the reason is said in the backend's own words;
 * - turning a switch ON sends one request and raises a card; the switch
 *   stays off and says it is waiting until the card is decided;
 * - the page re-reads when the approval queue changes and, gently, while a
 *   card waits - there is no event for the decision;
 * - turning a switch OFF is immediate;
 * - an older backend, or no answer, is a sentence - never a code or JSON.
 *
 * The CONTROL checks read the Rust: the header and token, and that only the
 * settings window may call these commands.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const SC = K.SECOND_CARD;

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1400 };
const open = (secondCard) => K.open(browser, base, "settings.html", { secondCard }, VIEW);

/** Everything the section shows, read off the page. */
const section = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const rows = [...document.querySelectorAll("#sc-switches .sc-switch")].map((row) => {
    const input = row.querySelector("input[type=checkbox]");
    return {
      id: row.dataset.id,
      state: row.dataset.state,
      checked: input.checked,
      disabled: input.disabled,
      text: row.innerText,
      describedBy: input.getAttribute("aria-describedby") || "",
    };
  });
  return {
    stateHidden: $("sc-state").hidden,
    state: $("sc-state").innerText,
    bodyHidden: $("sc-body").hidden,
    found: $("sc-found").innerText,
    cards: [...document.querySelectorAll("#sc-cards li")].map((li) => li.innerText),
    blockedHidden: $("sc-blocked").hidden,
    blocked: $("sc-blocked").innerText,
    rows,
    status: $("sc-status").innerText,
    lane: $("sc-lane").innerText,
    pinned: $("sc-pinned").innerText,
    pinHidden: $("sc-pin").hidden,
    pinCommand: $("sc-pin-command").value,
    pinReadOnly: $("sc-pin-command").readOnly,
    all: $("second-card").innerText,
    reads: window.__secondCard.reads,
    changes: window.__secondCard.changes,
  };
});
const row = (s, id) => s.rows.find((r) => r.id === id);
const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|null|undefined|\[object/,
    `raw data on the page: ${text}`);
};

/* ── What was found ─────────────────────────────────────────────────────── */

await check("one card (today's PC): found in words, every switch shown and none can be turned on", async () => {
  const page = await open({ status: SC.one_card });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, false);
  assert.match(s.found, /Only one graphics card found \(the NVIDIA GeForce RTX 2080 SUPER\)\./);
  assert.equal(s.cards.length, 1);
  assert.match(s.cards[0], /NVIDIA GeForce RTX 2080 SUPER \(8 GB\)/);
  assert.match(s.cards[0], /The one chat runs on\. Everyday chat runs here: a monitor is plugged into it\./);
  assert.equal(s.blockedHidden, false);
  assert.match(s.blocked, /10 GB or more\): only one graphics card found \(the NVIDIA GeForce RTX 2080 SUPER\)\. /);
  // The master switch and all five features, in the backend's order.
  assert.deepEqual(s.rows.map((r) => r.id),
    ["master", ...SC.one_card.features.map((f) => f.id)]);
  for (const r of s.rows) {
    assert.equal(r.disabled, true, `${r.id} can be turned on with no capable card`);
    assert.equal(r.checked, false, `${r.id} is on`);
    assert.match(r.describedBy, /sc-blocked/, `${r.id} is not tied to the reason it is off`);
  }
  assert.match(row(s, "master").text, /Use the second graphics card/);
  for (const f of SC.one_card.features) {
    const r = row(s, f.id);
    assert.ok(r.text.includes(f.name), `${f.id}: no name`);
    assert.ok(r.text.includes(f.what), `${f.id}: no "what"`);
    assert.ok(r.text.includes(f.why), `${f.id}: no "why"`);
  }
  // No pin command with one card; the note says why.
  assert.equal(s.pinHidden, true);
  assert.match(s.pinned, /Only one graphics card, so there is nothing to keep apart yet\./);
  assert.match(s.lane, /^Off\. No capable second card/);
  noRaw(s.all);
});

await check("an old second card: listed as not used, with the backend's reason", async () => {
  const page = await open({ status: SC.not_capable_old_card });
  const s = await section(page);
  await page.close();
  assert.equal(s.cards.length, 2);
  assert.match(s.cards[1], /NVIDIA GeForce GTX 1080 \(8 GB\)/);
  assert.match(s.cards[1], /Not used\. The NVIDIA GeForce GTX 1080 is older than Turing/);
  assert.match(s.blocked, /older than Turing/);
  assert.ok(s.rows.every((r) => r.disabled), "a switch can be turned on beside an old card");
  noRaw(s.all);
});

await check("a capable card, all off: only the main switch can be turned on, and the rest say why", async () => {
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  await page.close();
  assert.match(s.found, /The NVIDIA GeForce RTX 2060 \(12 GB\) can take the second-card features/);
  assert.match(s.cards[0], /The one chat runs on/);
  assert.match(s.cards[1], /NVIDIA GeForce RTX 2060 \(12 GB\)/);
  assert.match(s.cards[1], /The second card\. The second-card features would run here\./);
  assert.equal(s.blockedHidden, true);
  assert.equal(row(s, "master").disabled, false, "the main switch cannot be turned on");
  for (const f of SC.capable_off.features) {
    const r = row(s, f.id);
    assert.equal(r.disabled, true, `${f.id} can be turned on with the main switch off`);
    assert.match(r.text, /Turn on "Use the second graphics card" first\./);
  }
});

await check("each feature says its model, whether it is installed, the exact name to install, and its memory", async () => {
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  await page.close();
  const vision = row(s, "vision").text;
  assert.match(vision, /Model: qwen2\.5vl:7b, not installed yet\./);
  assert.match(vision, /open the Brain window, go to Faculties, then Models, type qwen2\.5vl:7b in the Install box/);
  assert.match(vision, /Uses about 7\.2 GB of the second card's memory\./);
  const long = row(s, "long_context").text;
  assert.match(long, /Model: qwen3:8b, installed\./);
  assert.match(long, /Uses about 7\.7 GB/);
  assert.doesNotMatch(long, /Install box/);
  // Browser control needs Longer conversations: the backend's own line says so.
  const browserText = row(s, "browser_control").text;
  assert.match(browserText, /Needs Longer conversations on first\./);
  assert.equal((browserText.match(/Needs/g) || []).length, 1, "the same need is said twice");
  // No catalogue: nothing on the page offers models to choose from.
  const html = await (await open({ status: SC.capable_off })).content();
  assert.doesNotMatch(html, /<select[^>]*sc-/, "a model picker appeared");
});

await check("the pin command: exactly the backend's line, read-only, with Copy and what it does", async () => {
  const page = await open({ status: SC.capable_off });
  const s = await section(page);
  const copy = await page.locator("#sc-pin-copy").innerText();
  await page.locator("#sc-pin-copy").click();
  await page.waitForTimeout(200);
  const said = await page.locator("#sc-pin-status").innerText();
  await page.close();
  assert.equal(s.pinHidden, false);
  assert.equal(s.pinCommand, SC.capable_off.pin_command);
  assert.equal(s.pinReadOnly, true);
  assert.equal(copy, "Copy");
  assert.match(said, /Copied|Ctrl\+C/);
  assert.match(s.all, /sets one Windows setting for your user account/);
  assert.match(s.all, /Nothing is written to any file/);
  assert.match(s.pinned, /The everyday Ollama is not pinned/);
});

/* ── Switching ─────────────────────────────────────────────────────────── */

await check("turning the main switch ON sends one request, raises a card, and stays off while it waits", async () => {
  const page = await open({ status: SC.capable_off });
  // click(), not check(): the box must NOT stay ticked, and check() insists it does.
  await page.locator("#sc-switch-master").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  const calls = await page.evaluate(() => window.__calls.map(([c]) => c));
  await page.close();
  assert.deepEqual(s.changes, [{ feature: "master", enabled: true }]);
  assert.ok(!calls.includes("decide_approval"), "the page answered its own card");
  const master = row(s, "master");
  assert.equal(master.checked, false, "shown as on before the card was approved");
  assert.equal(master.disabled, true, "a second card could be raised for the same switch");
  assert.equal(master.state, "waiting");
  assert.match(master.text, /Waiting for your approval\. The card is in the Jarvis bar and on the widget/);
  assert.match(s.status, /Waiting for your approval/);
  // The same words the Brain's model install uses while its card waits.
  assert.ok(read("src/brain.js").includes(
    "The card is in the Jarvis bar and on the widget — nothing changes until you approve it there."));
});

await check("a card already waiting: that switch says so, and the others stay usable", async () => {
  const page = await open({ status: SC.capable_pending });
  const s = await section(page);
  await page.close();
  const long = row(s, "long_context");
  assert.equal(long.state, "waiting");
  assert.equal(long.disabled, true);
  assert.equal(long.checked, false);
  assert.match(long.text, /Waiting for your approval/);
  assert.equal(row(s, "master").checked, true);
  assert.equal(row(s, "vision").disabled, false, "Pictures cannot be asked for while another card waits");
  assert.equal(row(s, "browser_control").disabled, true);
  assert.match(row(s, "browser_control").text, /Needs Longer conversations on first/);
});

await check("when the approval queue changes, the page re-reads and shows what the card decided", async () => {
  const page = await open({ status: SC.capable_pending });
  const before = await page.evaluate(() => window.__secondCard.reads);
  // The card was approved: the backend now reports the real running case.
  await page.evaluate((next) => {
    window.__secondCard.status = next;
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, SC.running_long_context);
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.ok(s.reads > before, "the decision did not make the page read again");
  const long = row(s, "long_context");
  assert.equal(long.checked, true);
  assert.equal(long.state, "on");
  assert.match(long.text, /Working: qwen3:8b on the NVIDIA GeForce RTX 2060/);
  assert.match(s.status, /"Longer conversations" is on\./);
  assert.match(s.lane, /^Running\. Running on 127\.0\.0\.1:11435 \(this PC only\)/);
  assert.match(s.pinned, /Ollama is set to use only the NVIDIA GeForce RTX 2080 SUPER/);
});

await check("a denied card: the switch is still off, and the page says it was not turned on", async () => {
  const page = await open({ status: SC.capable_pending });
  await page.evaluate((next) => {
    window.__secondCard.status = next;
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, { ...SC.capable_pending, pending: [] });
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.equal(row(s, "long_context").checked, false);
  assert.match(s.status, /"Longer conversations" was not turned on/);
});

await check("while a card waits and nothing else happens, the page re-reads gently on its own", async () => {
  const page = await open({ status: SC.capable_pending });
  const first = await page.evaluate(() => window.__secondCard.reads);
  await page.waitForTimeout(5600);
  const later = await page.evaluate(() => window.__secondCard.reads);
  await page.close();
  assert.ok(later > first, "no re-read while the card waited");
  assert.ok(later - first <= 2, `re-read ${later - first} times in under six seconds - not gentle`);
  // And with nothing waiting, it does not poll at all.
  const quiet = await open({ status: SC.capable_off });
  const a = await quiet.evaluate(() => window.__secondCard.reads);
  await quiet.waitForTimeout(5600);
  const b = await quiet.evaluate(() => window.__secondCard.reads);
  await quiet.close();
  assert.equal(b, a, "polled with no card waiting");
});

await check("turning a switch OFF is immediate", async () => {
  const page = await open({ status: SC.running_long_context });
  await page.locator("#sc-switch-long_context").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.changes, [{ feature: "long_context", enabled: false }]);
  assert.equal(row(s, "long_context").checked, false);
  assert.equal(row(s, "long_context").state, "off");
  assert.match(s.status, /"Longer conversations" is off\./);
});

await check("a switch whose card has gone stays on-but-waiting, and can still be turned off", async () => {
  const page = await open({ status: SC.card_missing_but_enabled });
  const s = await section(page);
  await page.close();
  for (const id of ["long_context", "vision"]) {
    const r = row(s, id);
    assert.equal(r.checked, true, `${id} was flipped off`);
    assert.equal(r.disabled, false, `${id} cannot be turned off`);
    assert.match(r.text, /On, but it cannot run: only one graphics card found/);
  }
  assert.equal(row(s, "learning").disabled, true);
  assert.equal(row(s, "master").checked, true);
  assert.match(row(s, "master").text, /On, but it cannot run: only one graphics card found/);
  assert.equal(s.blockedHidden, false);
});

await check("a refusal is the backend's own sentence, and the switch goes back to what Jarvis says", async () => {
  const refusal = "A card to turn on \"Pictures\" is already waiting - approve or deny that one";
  const page = await open({ status: SC.capable_pending, setFails: refusal });
  await page.locator("#sc-switch-vision").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.equal(s.status, refusal);
  assert.equal(row(s, "vision").checked, false);
});

/* ── When it cannot be read ────────────────────────────────────────────── */

await check("an older backend (404, or 503 with no module): says to run apply-patches.ps1", async () => {
  const page = await open({ status: SC.one_card, unavailable: true });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.equal(s.stateHidden, false);
  assert.match(s.state, /Update the backend by running apply-patches\.ps1/);
  noRaw(s.state);
});

await check("Jarvis not answering: a sentence, never an error dump", async () => {
  const page = await open({ status: SC.one_card,
    getFails: "Jarvis is not answering at http://127.0.0.1:4719. Is it running?" });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.match(s.state, /Jarvis could not be asked about your graphics cards\. Jarvis is not answering at http:\/\/127\.0\.0\.1:4719\. Is it running\?/);
});

await check("an error that is not a sentence is not shown as is", async () => {
  const page = await open({ status: SC.one_card,
    getFails: "{\"error\": \"Traceback (most recent call last)\"}" });
  const s = await section(page);
  await page.close();
  assert.doesNotMatch(s.state, /Traceback|\{/);
  assert.match(s.state, /Try again in a moment/);
});

await check("an answer that is not status() is not drawn", async () => {
  const page = await open({ status: { ok: true } });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.match(s.state, /could not be read/);
  noRaw(s.state);
});

/* ── The model badge and the picture check ─────────────────────────────── */

const CHAT = JSON.parse(read("tests/fixtures/chat-stream-cases.json"));
/** The route line commands.rs route_line_from_header sends: lane, where, gate
 *  and second_card, each only when it is a string. */
const routeLine = (header) => {
  const h = JSON.parse(header);
  const out = {};
  for (const k of ["lane", "where", "gate", "second_card"]) if (typeof h[k] === "string") out[k] = h[k];
  return "\u001fjarvis-route:" + JSON.stringify(out);
};
/** The REAL local header, with exactly the two changes second-card.patch
 *  makes: `lane` = the model answering, `second_card` = the feature. */
const local = CHAT.route_headers.find((r) => r.expect.where === "local");
const secondHeader = (model, feature) =>
  JSON.stringify({ ...JSON.parse(local.header), lane: model, second_card: feature });
const okBody = CHAT.cases.find((c) => c.name === "local turn").body;
const pumpLines = (body) => body.split("\n").map((l) => l.replace(/\r$/, "")).filter((l) => l.trim());

async function badge(header) {
  const page = await K.open(browser, base, "index.html",
    { chatReplies: [[routeLine(header), ...pumpLines(okBody)]] }, { width: 750, height: 600 });
  await page.locator("#prompt").fill("hi");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => ({
    tier: document.getElementById("route-tier").textContent,
    model: document.getElementById("route-model").textContent,
  }));
  await page.close();
  return got;
}

await check("the badge says 'on the second graphics card' when the second card answered, and is still Local", async () => {
  const long = await badge(secondHeader("qwen3:14b", "long_context"));
  assert.equal(long.tier, "Local");
  assert.equal(long.model, "qwen3:14b on the second graphics card");
  const pic = await badge(secondHeader("qwen2.5vl:7b", "vision"));
  assert.equal(pic.model, "qwen2.5vl:7b on the second graphics card");
  const plain = await badge(local.header);
  assert.equal(plain.model, local.expect.lane, "an ordinary turn gained the words");
});

await check("pictures on the second card: the check vision.rs returns sends the picture straight away", async () => {
  const page = await K.open(browser, base, "index.html", { vision: {
    model: "qwen2.5vl:7b", vision: true,
    reason: "Pictures go to qwen2.5vl:7b on the second graphics card." } });
  await page.evaluate(() => window.__emit("screen-captured", {
    dataUri: "data:image/gif;base64,R0lGODlhAQABAAAAACw=", width: 1, height: 1, bytes: 634, elapsedMs: 12 }));
  await page.waitForTimeout(100);
  await page.fill("#prompt", "What is this?");
  await page.press("#prompt", "Enter");
  await page.waitForTimeout(300);
  const sent = await page.evaluate(() => window.__calls.filter(([c]) => c === "stream_chat").map(([, a]) => a));
  const noticeHidden = await page.locator("#picture-notice").isHidden();
  await page.close();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].hasImage, true);
  assert.equal(noticeHidden, true);
});

/* ── Controls: the Rust ────────────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL: both commands send X-Jarvis-Client: hud and the token the usual way, and log nothing", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /const JARVIS_CLIENT: &str = "hud";/);
  const headers = fnBody(rust, "pub fn jarvis_headers(");
  assert.match(headers, /"X-Jarvis-Client"/);
  assert.match(headers, /"X-Jarvis-Token"/);
  for (const sig of ["pub async fn get_second_card(", "pub async fn set_second_card("]) {
    const body = fnBody(rust, sig);
    assert.match(body, /\.headers\(jarvis_headers\(&app\)\?\)/, `${sig} does not send the usual headers`);
    // Only the configured backend: no other address can be reached.
    assert.match(body, /format!\("\{base\}\{SECOND_CARD_PATH\}"\)/, `${sig} builds its own URL`);
    assert.match(body, /let base = jarvis_base\(&app\);/);
    assert.doesNotMatch(body, /println!|eprintln!|log::|tracing::|dbg!/, `${sig} logs`);
    assert.doesNotMatch(body, /token/i, `${sig} touches the token itself`);
  }
  assert.match(rust, /pub\(crate\) const SECOND_CARD_PATH: &str = "\/api\/second-card";/);
  // Transport errors are sentences built here, never reqwest's text.
  const unreachable = fnBody(rust, "fn second_card_unreachable(");
  assert.doesNotMatch(unreachable, /\{err\}|\{e\}|err\.to_string/);
});

await check("CONTROL: only the settings window may read or change the second card", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  for (const perm of ["allow-get-second-card", "allow-set-second-card"]) {
    const holders = sets.filter((s) => s.includes(`"${perm}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["settings-surface"], `${perm} is held by ${holders}`);
  }
  assert.match(read("src-tauri/capabilities/settings.json"), /"settings-surface"/);
  for (const c of ["brain", "faces", "hud", "onboarding", "quickbar", "widget"]) {
    const json = read(`src-tauri/capabilities/${c}.json`);
    assert.ok(!json.includes("settings-surface"), `${c} holds settings-surface`);
    assert.ok(!json.includes("second-card"), `${c} can reach the second card`);
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const cmd of ["get_second_card", "set_second_card"]) {
    assert.ok(build.includes(`"${cmd}"`), `${cmd} is not in build.rs, so no window can call it`);
    assert.ok(lib.includes(`commands::${cmd},`), `${cmd} is not registered`);
    const gen = read(`src-tauri/permissions/autogenerated/${cmd}.toml`);
    assert.match(gen, new RegExp(`commands.allow = \\["${cmd}"\\]`));
  }
});

await check("CONTROL: the picture check asks the second card first, and only a working Pictures switch says yes", async () => {
  const rust = read("src-tauri/src/vision.rs");
  const cmd = fnBody(rust, "pub async fn local_model_vision(");
  const second = cmd.indexOf("read_second_card_picture_model(");
  const current = cmd.indexOf("read_current_model(");
  assert.ok(second > -1 && second < current, "the second card is not asked before the current model");
  const pick = fnBody(rust, "pub fn second_card_picture_model(");
  assert.match(pick, /Some\("vision"\)/);
  assert.match(pick, /get\("available"\)\.and_then\(\|a\| a\.as_bool\(\)\) != Some\(true\)/);
  assert.match(rust, /Pictures go to \{model\} on the second graphics card\./);
  // Same client (loopback Jarvis only) and the same headers as the rest.
  const reader = fnBody(rust, "async fn read_second_card_picture_model(");
  assert.match(reader, /jarvis_base\(app\)/);
  assert.match(reader, /jarvis_headers\(app\)/);
});

await check("CONTROL: the route line passes second_card on, and nothing more", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const fn = fnBody(rust, "pub fn route_line_from_header(");
  assert.match(fn, /for key in \["lane", "where", "gate", "second_card"\]/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nThe second graphics card holds");
process.exit(fails.length ? 1 : 0);
