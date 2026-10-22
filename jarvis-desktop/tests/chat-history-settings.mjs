/**
 * Settings -> Security -> "Chat history on this PC".
 *
 * Task-79 (owner requirement: every feature findable AND adjustable in
 * Settings) plus #734's typed `chat_history` and `chat_keep_days`, which had
 * their only UI in the Brain's History tab.
 *
 * WHAT MUST HOLD:
 * - the switch and retention read the PC's status and show the PC's own words;
 * - ON is the ONE existing route with one boolean, answers "waiting", and the
 *   page re-reads until the card is decided; OFF is immediate;
 * - the retention choice sends ONE `keep_days` field and asks before deleting
 *   older conversations at once;
 * - ON and a retention change are held on a stale link (rule 4); OFF never is;
 * - a PC without chat history is a sentence, never a dead control;
 * - the Settings page never sees a conversation: the Rust read keeps only the
 *   status fields, and there is no delete/search verb in the command;
 * - search finds the control by "chat history" and "how long my chats are kept";
 * - the command is Settings-only, declared, and granted to this window.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
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

const VIEW = { width: 900, height: 1600 };
const open = (data = {}) => {
  const page = K.open(browser, base, "settings.html", data, VIEW);
  return page;
};
const ready = async (page) => page.waitForFunction(
  () => {
    const body = document.getElementById("ch-body");
    const reading = document.getElementById("ch-state");
    return Boolean(body && !body.hidden) ||
      /does not keep|not keep/.test((reading && reading.textContent) || "");
  },
  { timeout: 8000 });

const state = (page) => page.evaluate(() => ({
  button: (document.getElementById("ch-switch") || {}).textContent || "",
  disabled: Boolean(document.getElementById("ch-switch")?.disabled),
  keepValue: (document.getElementById("ch-keep") || {}).value || "",
  keepOptions: [...document.querySelectorAll("#ch-keep option")]
    .map((o) => o.textContent),
  line: (document.getElementById("ch-line") || {}).textContent || "",
  note: (document.getElementById("ch-note") || {}).textContent || "",
  linkNote: (document.getElementById("ch-link-note") || {}).textContent || "",
  said: (document.getElementById("ch-status") || {}).textContent || "",
  bodyHidden: Boolean(document.getElementById("ch-body")?.hidden),
  reading: (document.getElementById("ch-state") || {}).textContent || "",
  calls: window.__historyCalls || [],
}));

await check("the switch and retention read the PC's real status", async () => {
  const page = await open({ chatHistory: { enabled: true, keep_days: 30,
    recording: true, why_not: "" } });
  await ready(page);
  const s = await state(page);
  assert.equal(s.bodyHidden, false);
  assert.equal(s.button.trim(), "Turn chat history off");
  assert.equal(s.keepValue, "30");
  assert.deepEqual(s.keepOptions,
    ["Keep until I delete them", "30 days", "90 days", "1 year"]);
  assert.match(s.line, /kept encrypted on this PC/i);
  assert.match(s.note, /chat history is kept/i);
  assert.deepEqual(s.calls, [{ action: "read", keepDays: undefined }]);
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await check("OFF is the one command, one boolean, immediate", async () => {
  const page = await open({ chatHistory: { enabled: true, keep_days: 0,
    recording: true, why_not: "" } });
  await ready(page);
  await page.evaluate(() => document.getElementById("ch-switch").click());
  await page.waitForFunction(
    () => /chat history is off/i.test(document.getElementById("ch-line").textContent),
    { timeout: 8000 });
  const s = await state(page);
  assert.deepEqual(s.calls.filter((c) => c.action === "off"),
    [{ action: "off", keepDays: undefined }]);
  assert.equal(s.button.trim(), "Turn chat history on");
  assert.match(s.line, /chat history is off/i);
  await page.close();
});

await check("ON is one card: the page says waiting and re-reads the status", async () => {
  const page = await open({ chatHistory: { enabled: false, keep_days: 0,
    recording: false, why_not: "off" } });
  await ready(page);
  assert.equal((await state(page)).button.trim(), "Turn chat history on");
  await page.evaluate(() => document.getElementById("ch-switch").click());
  await page.waitForFunction(
    () => /waiting for your approval card/i.test(
      document.getElementById("ch-status").textContent),
    { timeout: 8000 });
  const after = await state(page);
  assert.deepEqual(after.calls.filter((c) => c.action === "on"),
    [{ action: "on", keepDays: undefined }]);
  // The re-read sees it enabled (the mock PC applies it), and the button flips.
  await page.waitForFunction(
    () => /Turn chat history off/.test(
      document.getElementById("ch-switch").textContent),
    { timeout: 12000 });
  assert.ok((await state(page)).calls.filter((c) => c.action === "read").length >= 2,
    "the page never re-read the status after the card");
  await page.close();
});

await check("the retention choice sends ONE keep_days field, after asking", async () => {
  const page = await open({ chatHistory: { enabled: true, keep_days: 0,
    recording: true, why_not: "" } });
  await ready(page);
  const dialogs = [];
  page.on("dialog", async (dialog) => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });
  await page.locator("#ch-keep").selectOption("30");
  await page.waitForFunction(
    () => window.__historyCalls.some((c) => c.action === "keep"),
    { timeout: 8000 });
  const s = await state(page);
  assert.equal(dialogs.length, 1, "it deleted older chats without asking");
  assert.match(dialogs[0], /older than 30 days deleted NOW/i, dialogs[0]);
  assert.deepEqual(s.calls.filter((c) => c.action === "keep"),
    [{ action: "keep", keepDays: 30 }]);
  await page.waitForFunction(
    () => /kept for 30 days/i.test(document.getElementById("ch-status").textContent),
    { timeout: 8000 });
  assert.equal((await state(page)).keepValue, "30");
  await page.close();
});

await check("ON and a retention change wait for a live link; OFF does not", async () => {
  const page = await open({ link: { stale: true },
    chatHistory: { enabled: false, keep_days: 0, recording: false } });
  await ready(page);
  const s = await state(page);
  assert.equal(s.disabled, true, "ON was offered on a stale link");
  assert.match(s.linkNote, /connection is catching up/i, s.linkNote);
  assert.match(s.linkNote, /turning it off works at once/i, s.linkNote);
  await page.evaluate(() => document.getElementById("ch-switch").click());
  await page.waitForTimeout(200);
  const afterClick = await state(page);
  assert.ok(!afterClick.calls.some((c) => c.action === "on"),
    "the page called the PC while the link was stale");
  // The retention select is held too (it deletes older chats at once).
  const keepDisabled = await page.evaluate(
    () => document.getElementById("ch-keep").disabled);
  assert.equal(keepDisabled, true);
  await page.close();
});

await check("a PC without chat history says so and leaves no dead control", async () => {
  const page = await open({
    invokeFails: {
      history_settings: "This PC's Jarvis does not keep chat history yet.",
    },
    chatHistory: { enabled: true, keep_days: 0 },
  });
  await page.waitForFunction(
    () => /does not keep chat history/.test(
      document.getElementById("ch-state").textContent),
    { timeout: 8000 });
  const s = await state(page);
  assert.equal(s.bodyHidden, true);
  assert.match(s.reading, /does not keep chat history/);
  await page.close();
});

await check("search finds it by its ordinary words", async () => {
  const page = await open();
  await ready(page);
  const type = async (text) => {
    await page.locator("#settings-search-input").fill(text);
    await page.waitForTimeout(250);
  };
  for (const words of ["chat history", "how long my chats are kept"]) {
    await type(words);
    const showing = await page.evaluate(() =>
      [...document.querySelectorAll("main .card")]
        .filter((c) => !c.hidden).map((c) => c.id));
    assert.ok(showing.includes("security"),
      `"${words}" did not find the Security card: ${showing.join(",")}`);
  }
  await type("");
  await page.close();
});

/* ── The command: Settings-only, one field, and no conversation at all ────── */

await check("CONTROL: the command's verbs are read/on/off/keep, one field each", async () => {
  const rust = read("src-tauri/src/history_settings.rs");
  assert.match(rust, /pub\(crate\) const ACTIONS: &\[&str; 4\] = &\["read", "on", "off", "keep"\];/);
  assert.match(rust, /"on" => Ok\(serde_json::json!\(\{ "enabled": true \}\)\)/);
  assert.match(rust, /"off" => Ok\(serde_json::json!\(\{ "enabled": false \}\)\)/);
  assert.match(rust, /"keep" => match keep_days/);
  assert.match(rust, /const KEEP_DAYS: \[u32; 4\] = \[0, 30, 90, 365\];/);
  // No delete, no conversation list, no approval anywhere in it.
  assert.doesNotMatch(rust, /\/api\/history\/(delete|conversation|search)/);
  assert.doesNotMatch(rust, /decide_approval|answer_card/);
  // Only ON and a retention change are held on a stale link.
  assert.match(rust, /stale && \(action == "on" \|\| action == "keep"\)/);
});

await check("CONTROL: the read drops every conversation in Rust", async () => {
  const rust = read("src-tauri/src/history_settings.rs");
  assert.match(rust, /const STATUS_PATH: &str = "\/api\/history\?limit=1";/);
  assert.match(rust, /pub\(crate\) fn status_only/);
  // The status fields only; conversations never cross into the page.
  for (const key of ["enabled", "keep_days", "recording", "why_not"]) {
    assert.ok(rust.includes(`"${key}"`), `the status lost ${key}`);
  }
  assert.doesNotMatch(rust, /conversations.*insert|insert.*conversations/);
});

await check("CONTROL: declared, registered, and granted to Settings only", async () => {
  assert.match(read("src-tauri/build.rs"), /"history_settings",/,
    "the app manifest does not declare it - the call would be refused silently");
  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /pub mod history_settings;/);
  assert.match(lib, /history_settings::history_settings,/);
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /identifier = "history-settings"/);
  assert.match(read("src-tauri/capabilities/settings.json"), /"history-settings",/);
  for (const name of ["quickbar", "brain", "hud", "widget", "faces", "floating",
    "features", "onboarding", "live-badge", "watch-badge"]) {
    let cap = "";
    try {
      cap = read(`src-tauri/capabilities/${name}.json`);
    } catch {
      continue;
    }
    assert.doesNotMatch(cap, /history-settings/, `${name} can call it`);
  }
  assert.ok(read("src-tauri/permissions/autogenerated/history_settings.toml")
    .includes('identifier = "allow-history-settings"'));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nchat history's Settings controls hold");
process.exit(fails.length ? 1 : 0);
