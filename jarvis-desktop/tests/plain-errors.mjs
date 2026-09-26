/**
 * Plain words when something goes wrong, and "How Jarvis talks" (the
 * creativity audit, 2026-09-25; JARVIS-API.md sections 4 and 24;
 * src/plain-errors.js, src/manner.js, src/manner-settings.js,
 * src-tauri/src/plain_errors.rs).
 *
 * What must hold:
 * - every word is the contract file's (tests/fixtures/plain-error-cases.json,
 *   made by tools/gen_plain_error_cases.py - the phone checks the same file):
 *   the kinds, the buttons, the waits, the codes, the manner words - and the
 *   Rust side's own copies too;
 * - each failure picks the kind the contract says (the same cases the
 *   phone's classifier runs);
 * - Details never shows a token, key, password, email address or Windows
 *   user name, and keeps what a bug report needs;
 * - the answer card: a failure shows the plain words, ONE fix button and
 *   Details; "Waking up the model…" while the PC says it is loading;
 *   "Answering…", never "Streaming", and no chunk count;
 * - Settings -> How Jarvis talks: the PC's words, ONE change per tap, no
 *   card either way, greyed on a stale link;
 * - CONTROL: the manner commands sit with the Settings window only, the fix
 *   button's command with the quickbar only, and it opens two places.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  BUTTONS, classify, CODES, DETAILS_MAX, ERROR_LINE_PREFIX, fromChatFailure, fromStreamError,
  KINDS, scrubDetails, shown, STATUSES,
} from "../src/plain-errors.js";
import { DETAIL, LABEL, MANNERS, readManner, SAID, SPOKEN, TITLE, WHY } from "../src/manner.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/plain-error-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words ────────────────────────────────────────────────────────── */

await check("every kind's words are the contract's, word for word", async () => {
  assert.deepEqual(Object.keys(KINDS).sort(), Object.keys(CASES.kinds).sort());
  for (const [kind, k] of Object.entries(CASES.kinds)) {
    assert.deepEqual({ ...KINDS[kind] }, k, kind);
  }
  assert.deepEqual({ ...BUTTONS }, CASES.buttons);
  assert.deepEqual({ ...STATUSES }, CASES.statuses);
  assert.deepEqual({ ...CODES }, CASES.codes);
  assert.equal(DETAILS_MAX, CASES.details_max);
});

await check("no word a beginner would not know in what is shown", async () => {
  for (const [kind, k] of Object.entries(CASES.kinds)) {
    const text = `${k.says} ${k.fix} ${k.button}`;
    assert.ok(!/\b(HTTP|503|404|stale|chunk|stream|exception|errno|socket|tier)\b/i.test(text),
      `${kind}: ${text}`);
    if (kind !== "pc_said") {
      assert.ok(k.says && k.fix, `${kind} has what happened AND what to do`);
    }
  }
  assert.ok(!/stream/i.test(Object.values(STATUSES).join(" ")));
});

await check("the Rust side's own copies are the contract's words", async () => {
  const rs = read("src-tauri/src/plain_errors.rs");
  const konst = (name) => {
    const m = rs.match(new RegExp(`const ${name}: &str =\\s*"((?:[^"\\\\]|\\\\.)*)"`, "s"));
    assert.ok(m, name);
    return m[1].replace(/\\\n\s*/g, "").replace(/\\"/g, "\"");
  };
  const pairs = { NOT_RUNNING: "jarvis_not_running", TIMEOUT: "timeout", DROPPED: "connection_dropped",
                  KEY_STORE: "key_store_refused" };
  for (const [name, kind] of Object.entries(pairs)) {
    assert.equal(konst(`${name}_SAYS`), CASES.kinds[kind].says, name);
    assert.equal(konst(`${name}_FIX`), CASES.kinds[kind].fix, name);
  }
  assert.ok(rs.includes(`"${ERROR_LINE_PREFIX.replace("\u001f", "\\u{1f}")}`));
});

await check("each failure picks the kind the contract says (the phone runs the same cases)", async () => {
  for (const c of CASES.classify) {
    assert.equal(classify(c.input), c.kind, c.name);
  }
});

await check("the PC's own sentence is shown as it is, first letter raised", async () => {
  const s = shown("pc_said", "the second card is not detected");
  assert.equal(s.says, "The second card is not detected.");
  assert.equal(s.button, "");
  assert.equal(shown("model_missing").button, "Choose a model");
});

/* ── Details ──────────────────────────────────────────────────────────── */

await check("Details: every secret gone, what a bug report needs kept", async () => {
  for (const c of CASES.scrub) {
    const out = scrubDetails(c.input);
    for (const g of c.gone) assert.ok(!out.includes(g), `${g} survived: ${out}`);
    for (const k of c.kept) assert.ok(out.includes(k), `${k} was lost: ${out}`);
  }
  const t = CASES.scrub_known_token;
  const out = scrubDetails(t.input, t.token);
  for (const g of t.gone) assert.ok(!out.includes(g), out);
  for (const k of t.kept) assert.ok(out.includes(k), out);
  assert.ok(scrubDetails("x".repeat(5000)).length <= CASES.details_max);
});

await check("a failed chat's tagged facts become the plain words, the detail scrubbed", async () => {
  const secret = "tv" + "ly-" + "abcdefghijklmnop";
  const line = ERROR_LINE_PREFIX + JSON.stringify({ http: 503, detail: `key ${secret}` });
  const p = fromChatFailure(line);
  assert.equal(p.kind, "feature_off");
  assert.equal(p.says, CASES.kinds.feature_off.says);
  assert.ok(p.details.includes("HTTP 503") && !p.details.includes(secret), p.details);
  const q = fromChatFailure(ERROR_LINE_PREFIX + JSON.stringify({ network: "refused", detail: "x" }));
  assert.equal(q.kind, "jarvis_not_running");
  // An older build's plain sentence is shown as it is.
  assert.equal(fromChatFailure("Temporary chat isn't available.").kind, "pc_said");
  const s = fromStreamError({ message: "The local model is not running.", code: "model_not_running" });
  assert.equal(s.says, CASES.kinds.model_not_running.says);
  assert.ok(s.details.includes("The local model is not running."));
});

/* ── The manner words ─────────────────────────────────────────────────── */

await check("How Jarvis talks: the PC's words, word for word", async () => {
  const m = CASES.manner;
  assert.equal(TITLE, m.title);
  assert.equal(DETAIL, m.detail);
  assert.equal(SPOKEN, m.spoken);
  assert.deepEqual([...MANNERS], m.choices.map((c) => c.id));
  for (const c of m.choices) {
    assert.equal(LABEL[c.id], c.label, c.id);
    assert.equal(WHY[c.id], c.why, c.id);
  }
  assert.deepEqual({ ...SAID }, m.said);
  assert.equal(m.default, "warm");
  const v = readManner({ available: true, manner: "plain", choices: m.choices });
  assert.equal(v.manner, "plain");
  assert.equal(readManner({ choices: [] }).manner, "warm", "no setting in the answer: the default");
  assert.equal(readManner(null).available, false, "no answer: never drawn as a choice");
  assert.equal(readManner({ available: false, why: "old" }).available, false);
});

/* ── The answer card ──────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

async function ask(replies, before) {
  const page = await K.open(browser, base, "index.html", { chatReplies: [replies] },
    { width: 750, height: 600 });
  await page.evaluate(() => {
    window.__statuses = [];
    const el = document.getElementById("card-status-text");
    new MutationObserver(() => window.__statuses.push(el.textContent))
      .observe(el, { childList: true, characterData: true, subtree: true });
  });
  if (before) await before(page);
  await page.locator("#prompt").fill("hi");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => ({
    answer: document.getElementById("answer").textContent.trim(),
    status: document.getElementById("card-status-text").textContent,
    stat: document.getElementById("card-stat").textContent,
    statuses: window.__statuses,
    problemShown: !document.getElementById("answer-problem").hidden,
    button: document.getElementById("problem-action").hidden
      ? "" : document.getElementById("problem-action").textContent,
    details: document.getElementById("problem-details-text").textContent,
  }));
  return { page, got };
}

await check("an answer says Answering…, never Streaming, and counts no chunks", async () => {
  const { page, got } = await ask(["data: {\"choices\":[{\"delta\":{\"content\":\"Hello.\"}}]}",
    "data: [DONE]"]);
  await page.close();
  assert.ok(got.statuses.includes(STATUSES.answering), JSON.stringify(got.statuses));
  assert.ok(!got.statuses.some((s) => /Streaming/.test(s)));
  assert.equal(got.stat, "");
  assert.equal(got.problemShown, false);
});

await check("the PC says the model is loading: Waking up the model…", async () => {
  const { page, got } = await ask([": jarvis-status loading",
    "data: {\"choices\":[{\"delta\":{\"content\":\"Morning.\"}}]}", "data: [DONE]"]);
  await page.close();
  assert.ok(got.statuses.includes(STATUSES.loading), JSON.stringify(got.statuses));
});

await check("a failure: the plain words, ONE fix button, the PC's sentence behind Details", async () => {
  const body = "data: " + JSON.stringify({ error: { message: "The model “qwen3:14b” is not "
    + "installed on this PC.", type: "jarvis", code: "model_missing" } });
  const { page, got } = await ask([body], async (pg) => {
    await pg.evaluate(() => {
      window.__opened = [];
      const core = window.__TAURI__.core;
      const inner = core.invoke;
      core.invoke = async (cmd, args) => {
        if (cmd === "open_fix_place") { window.__opened.push(args.place); return null; }
        return inner(cmd, args);
      };
    });
  });
  assert.ok(got.answer.includes(CASES.kinds.model_missing.says), got.answer);
  assert.ok(got.answer.includes(CASES.kinds.model_missing.fix), got.answer);
  assert.equal(got.button, "Choose a model");
  assert.ok(got.details.includes("qwen3:14b"), got.details);
  // Selectable for a bug report (ease-of-use audit #6); the rest of the bar is not.
  const select = await page.evaluate(() => [
    getComputedStyle(document.getElementById("problem-details-text")).userSelect,
    getComputedStyle(document.body).userSelect]);
  assert.deepEqual(select, ["text", "none"]);
  await page.locator("#problem-action").click();
  const opened = await page.evaluate(() => window.__opened);
  await page.close();
  assert.deepEqual(opened, ["brain"]);
});

await check("Try again sends the same question, with the same tag", async () => {
  const line = ERROR_LINE_PREFIX + JSON.stringify({ network: "refused", detail: "x" });
  const page = await K.open(browser, base, "index.html",
    // The first stream_chat is refused below before it reads a reply, so
    // the one scripted reply is the second call's.
    { chatReplies: [["data: {\"choices\":[{\"delta\":{\"content\":\"Back.\"}}]}", "data: [DONE]"]] },
    { width: 750, height: 600 });
  await page.evaluate((l) => {
    window.__asked = [];
    const core = window.__TAURI__.core;
    const inner = core.invoke;
    let first = true;
    core.invoke = async (cmd, args) => {
      if (cmd === "stream_chat") {
        window.__asked.push(JSON.stringify(args.messages[args.messages.length - 1]));
        if (first) { first = false; throw new Error(l); }
      }
      return inner(cmd, args);
    };
  }, line);
  await page.locator("#prompt").fill("what's on today");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(300);
  const said = await page.locator("#answer").textContent();
  assert.ok(said.includes(CASES.kinds.jarvis_not_running.says), said);
  assert.equal(await page.locator("#problem-action").textContent(), "Try again");
  await page.locator("#problem-action").click();
  await page.waitForTimeout(300);
  const asked = await page.evaluate(() => window.__asked);
  const after = await page.locator("#answer").textContent();
  const problemHidden = await page.locator("#answer-problem").isHidden();
  await page.close();
  assert.equal(asked.length, 2);
  assert.equal(asked[0], asked[1], "the same words and the same provenance");
  assert.ok(after.includes("Back."), after);
  assert.ok(problemHidden, "the old fix button stays after a good answer");
});

await check("\"Jarvis isn't running\": a second button opens Settings at Starting Jarvis for you", async () => {
  // Ease-of-use audit 2026-09-27 #2: the fix names the real place, and the
  // desktop opens it - "More options" open, the card scrolled to.
  const line = ERROR_LINE_PREFIX + JSON.stringify({ network: "refused", detail: "x" });
  const page = await K.open(browser, base, "index.html", {}, { width: 750, height: 600 });
  await page.evaluate((l) => {
    window.__opened = [];
    const core = window.__TAURI__.core;
    const inner = core.invoke;
    core.invoke = async (cmd, args) => {
      if (cmd === "stream_chat") throw new Error(l);
      if (cmd === "open_fix_place") { window.__opened.push(args.place); return null; }
      return inner(cmd, args);
    };
  }, line);
  await page.locator("#prompt").fill("hi");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(300);
  const said = await page.locator("#answer").textContent();
  assert.ok(said.includes("More options") && said.includes("Starting Jarvis for you"), said);
  assert.equal(await page.locator("#problem-action").textContent(), "Try again");
  assert.equal(await page.locator("#problem-where").isVisible(), true);
  await page.locator("#problem-where").click();
  const opened = await page.evaluate(() => window.__opened);
  const left = await page.evaluate(() => JSON.parse(localStorage.getItem("jarvis.settings.place")));
  await page.close();
  assert.deepEqual(opened, ["settings"]);
  assert.equal(left.place, "start-jarvis");

  const sp = await K.open(browser, base, "settings.html", {}, { width: 900, height: 900 });
  await sp.evaluate(() => localStorage.setItem("jarvis.settings.place",
    JSON.stringify({ place: "start-jarvis", at: Date.now() })));
  await sp.reload();
  await sp.waitForTimeout(400);
  const got = await sp.evaluate(() => ({
    open: document.getElementById("more-options").open,
    top: document.getElementById("start-jarvis").getBoundingClientRect().top,
    kept: localStorage.getItem("jarvis.settings.place"),
  }));
  await sp.close();
  assert.equal(got.open, true, "More options opens");
  assert.ok(got.top >= -2 && got.top < 200, `the card is in view (top ${got.top})`);
  assert.equal(got.kept, null, "the place is taken once");
});

await check("another failure shows no \"Show me where\"", async () => {
  const body = "data: " + JSON.stringify({ error: { message: "x", type: "jarvis", code: "model_missing" } });
  const { page } = await ask([body]);
  const where = await page.locator("#problem-where").isVisible();
  await page.close();
  assert.equal(where, false);
});

/* ── Settings -> How Jarvis talks ─────────────────────────────────────── */

/** The bridge for the two manner commands, on top of uikit's. */
function mannerBridge({ m, choices }) {
  const core = window.__TAURI__.core;
  const inner = core.invoke;
  window.__manner = { manner: m, sets: [] };
  core.invoke = async (cmd, args) => {
    if (cmd === "get_manner") {
      return { available: true, manner: window.__manner.manner, default: "warm",
               title: "How Jarvis talks", detail: "PC detail", spoken: "PC spoken", choices };
    }
    if (cmd === "set_manner") {
      window.__manner.sets.push(args);
      window.__manner.manner = args.manner;
      return { ok: true, said: "PC said it." };
    }
    return inner(cmd, args);
  };
}

async function settings(manner = "warm", data = {}) {
  const page = await K.open(browser, base, "settings.html", data, { width: 900, height: 1800 });
  await page.addInitScript(mannerBridge, { m: manner, choices: CASES.manner.choices });
  await page.reload();
  await page.waitForTimeout(700);
  return page;
}

await check("Settings shows the PC's words for both choices, with the one in use ticked", async () => {
  const page = await settings("warm");
  const got = await page.evaluate(() => ({
    rows: [...document.querySelectorAll("#mn-choices .theme-row")].map((r) => ({
      id: r.dataset.choice, text: r.textContent, checked: r.querySelector("input").checked })),
    detail: document.getElementById("mn-detail").textContent,
    spoken: document.getElementById("mn-spoken").textContent,
    heading: document.querySelector("#manner h2").textContent,
  }));
  await page.close();
  assert.equal(got.heading, CASES.manner.title);
  assert.equal(got.detail, "PC detail");
  assert.equal(got.spoken, "PC spoken");
  assert.deepEqual(got.rows.map((r) => r.id), ["warm", "plain"]);
  assert.ok(got.rows[0].checked && !got.rows[1].checked);
  for (const [i, c] of CASES.manner.choices.entries()) {
    assert.ok(got.rows[i].text.includes(c.label) && got.rows[i].text.includes(c.why), c.id);
  }
});

await check("one tap sends ONE change, and no card is mentioned", async () => {
  const page = await settings("warm");
  await page.locator('#mn-choices input[value="plain"]').check();
  await page.waitForTimeout(300);
  const got = await page.evaluate(() => ({
    sets: window.__manner.sets,
    status: document.getElementById("mn-status").textContent,
    checked: document.querySelector('#mn-choices input[value="plain"]').checked,
  }));
  await page.close();
  assert.deepEqual(got.sets, [{ manner: "plain" }]);
  assert.equal(got.status, "PC said it.");
  assert.ok(got.checked);
  assert.ok(!/approv|card/i.test(read("src/manner-settings.js").split("*/").slice(1).join("")),
    "the page never talks about a card");
});

await check("greyed on a stale link", async () => {
  const page = await settings("warm", { link: { stale: true } });
  const disabled = await page.evaluate(() =>
    [...document.querySelectorAll("#mn-choices input")].every((i) => i.disabled));
  await page.close();
  assert.ok(disabled);
});

/* ── Control ──────────────────────────────────────────────────────────── */

await check("the manner commands are Settings-only; the fix button's is the quickbar's", async () => {
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  const holders = (cmd) => sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  assert.deepEqual(holders("get_manner"), ["settings-surface"]);
  assert.deepEqual(holders("set_manner"), ["settings-surface"]);
  assert.deepEqual(holders("open_fix_place"), ["quickbar-surface"]);
  const rs = read("src-tauri/src/plain_errors.rs");
  const fix = rs.slice(rs.indexOf("pub fn open_fix_place"));
  assert.match(fix, /"settings" =>/);
  assert.match(fix, /"brain" =>/);
  assert.match(fix, /_ => Err/);
  const set = rs.slice(rs.indexOf("pub async fn set_manner"), rs.indexOf("pub fn open_fix_place"));
  assert.match(set, /link\(\)\.stale/, "set_manner is held on a stale link");
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
