/**
 * Settings -> Big model (slow) - backend/big-model.patch, docs/BIG-MODEL.md.
 *
 * Every status here is REAL: `K.BIG_MODEL` is
 * tests/fixtures/big-model-cases.json, jarvis_big_model.status() for each
 * named case plus the POST answers, written by tools/gen_big_model_cases.py.
 * Nothing is hand-made.
 *
 * What must hold (the owner's decisions, JARVIS-API.md section 14):
 * - off by default, and nothing can be turned on until the backend's
 *   `detected.capable` is true - the reason in the backend's own words;
 * - each ON sends one request and raises a card; the switch stays off and
 *   says it is waiting until the card is decided; OFF is immediate;
 * - background jobs only: the page says so, and offers nothing else;
 * - "none of colibri's speed claims are verified on this PC" is visible,
 *   and an unmeasured job says "not measured on this PC yet";
 * - where the key is kept is shown, never a key;
 * - an older backend, or no answer, is a sentence - never a code or JSON.
 *
 * The CONTROL checks read the Rust: the header and token, the configured
 * backend only, the typed body, and that only the settings window may call
 * these two commands.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const BM = K.BIG_MODEL;

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1800 };
const open = (bigModel, extra = {}) =>
  K.open(browser, base, "settings.html", { bigModel, ...extra }, VIEW);

/** Everything the section shows, read off the page. */
const section = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  const rows = [...document.querySelectorAll("#bm-switches .sc-switch")].map((row) => {
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
  const list = (id) => [...document.querySelectorAll(`#${id} li`)].map((li) => li.innerText);
  return {
    stateHidden: $("bm-state").hidden,
    state: $("bm-state").innerText,
    bodyHidden: $("bm-body").hidden,
    found: $("bm-found").innerText,
    parts: list("bm-parts"),
    models: list("bm-models"),
    blockedHidden: $("bm-blocked").hidden,
    blocked: $("bm-blocked").innerText,
    rows,
    status: $("bm-status").innerText,
    engine: $("bm-engine").innerText,
    address: $("bm-address").innerText,
    cuda: $("bm-cuda").innerText,
    cudaTone: $("bm-cuda").dataset.tone || "",
    key: $("bm-key").innerText,
    measured: list("bm-measured"),
    unverified: $("bm-unverified").innerText,
    note: $("bm-unverified-note").innerText,
    all: $("big-model").innerText,
    order: [...document.querySelectorAll("section.card h2")].map((h) => h.textContent.trim()),
    reads: window.__bigModel.reads,
    changes: window.__bigModel.changes,
  };
});
const row = (s, id) => s.rows.find((r) => r.id === id);
const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|null|undefined|\[object|NaN/,
    `raw data on the page: ${text}`);
};

/* ── Where it is, and what it says before anything is read ───────────── */

await check("the section sits right after \"Second graphics card\", and says what it is for", async () => {
  const page = await open({ status: BM.status_ready_off });
  const s = await section(page);
  const errors = page.__errors;
  await page.close();
  const at = s.order.indexOf("Second graphics card");
  assert.ok(at > -1, "no second-card section");
  assert.equal(s.order[at + 1], "Big model (slow)");
  assert.match(s.all, /the wiki builder, and "deep questions"/);
  assert.match(s.all, /never used for chat, voice or approvals/);
  assert.match(s.all, /expect minutes per answer/);
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await check("\"none of colibri's speed claims are verified\" is on screen - even with no backend", async () => {
  const page = await open({ status: BM.status_ready_off, unavailable: true });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.match(s.note, /None of colibri's speed claims have been checked on this PC/);
});

/* ── What was found ─────────────────────────────────────────────────────── */

await check("today's PC (colibri not installed): found in words, every switch shown and none can be turned on", async () => {
  const st = BM.status_not_installed;
  const page = await open({ status: st });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, false);
  assert.ok(s.found.includes("there is no coli.cmd in that folder"), s.found);
  assert.match(s.parts[0], /^colibri: not found/);
  assert.ok(s.parts[0].includes(st.detected.colibri.why), s.parts[0]);
  // Python is not looked for until colibri is found: not "not found".
  assert.match(s.parts[1], /^Python 3: not checked yet/);
  assert.match(s.parts[2], /31\.9 GB in total, 25\.3 GB free right now\./);
  assert.equal(s.blockedHidden, false);
  assert.ok(s.blocked.includes("there is no coli.cmd"), s.blocked);
  assert.deepEqual(s.rows.map((r) => r.id), ["master", ...st.switches.map((w) => w.id)]);
  for (const r of s.rows) {
    assert.equal(r.disabled, true, `${r.id} can be turned on with nothing found`);
    assert.equal(r.checked, false, `${r.id} is on`);
    assert.match(r.describedBy, /bm-blocked/, `${r.id} is not tied to the reason it is off`);
  }
  noRaw(s.all);
});

await check("each model: its folder, drive, free space, memory it needs, why and note", async () => {
  const st = BM.status_ready_off;
  const page = await open({ status: st });
  const s = await section(page);
  await page.close();
  assert.equal(s.models.length, st.detected.models.length);
  const [qwen, dsv4] = s.models;
  assert.match(qwen, /^Qwen3\.6-35B-A3B \(medium model\)/);
  assert.match(qwen, /Folder: D:\\models\\qwen36_i4_gs64/);
  assert.match(qwen, /On D: \(SATA SSD\), 3,100 GB free\./);
  assert.match(qwen, /Needs about 24 GB of free memory to run\./);
  assert.match(qwen, /Ready to use: 25\.3 GB of memory free, 24 GB needed\./);
  assert.match(dsv4, /^DeepSeek V4 Flash \(giant model\)/);
  assert.match(dsv4, /On E: \(NVMe\), 290 GB free\./);
  assert.match(dsv4, /Needs about 16 GB/);
  noRaw(s.all);
});

await check("a giant model on a SATA drive: the backend's note is shown as a warning", async () => {
  const st = BM.status_giant_on_sata;
  const page = await open({ status: st });
  const s = await section(page);
  const warn = await page.locator("#bm-models .bm-warn").allInnerTexts();
  await page.close();
  assert.equal(warn.length, 1);
  assert.match(warn[0], /^D: is a SATA SSD drive\./);
  assert.match(warn[0], /keep it on the NVMe drive\.$/);
  // Capable: the main switch can be turned on, with the warning beside it.
  assert.equal(row(s, "master").disabled, false);
});

await check("a missing model folder, no Python, too little memory: each says why, in the backend's words", async () => {
  for (const [name, want] of [
    ["status_model_folder_missing", /the folder D:\\models\\qwen36_i4_gs64 does not exist/],
    ["status_no_python", /Python 3 was not found/],
  ]) {
    const page = await open({ status: BM[name] });
    const s = await section(page);
    await page.close();
    assert.match(s.found, want, name);
    assert.ok(s.rows.every((r) => r.disabled), `${name}: a switch can be turned on`);
    noRaw(s.all);
  }
  const page = await open({ status: BM.status_too_little_memory });
  const s = await section(page);
  await page.close();
  assert.match(s.models[0], /This PC has 16 GB of memory, and a medium model needs 24 GB/);
  assert.match(s.parts[2], /16 GB in total, 11 GB free right now\./);
  // The backend still calls it capable (the giant one fits), so ON is allowed.
  assert.equal(row(s, "master").disabled, false);
});

/* ── The switches ──────────────────────────────────────────────────────── */

await check("capable and all off: only the main switch can be turned on; each job says what, why and its model", async () => {
  const st = BM.status_ready_off;
  const page = await open({ status: st });
  const s = await section(page);
  await page.close();
  assert.equal(s.blockedHidden, true);
  assert.equal(row(s, "master").disabled, false, "the main switch cannot be turned on");
  assert.match(row(s, "master").text, /Use the big model/);
  for (const sw of st.switches) {
    const r = row(s, sw.id);
    assert.equal(r.disabled, true, `${sw.id} can be turned on with the main switch off`);
    assert.ok(r.text.includes(sw.name), `${sw.id}: no name`);
    assert.ok(r.text.includes(sw.what), `${sw.id}: no "what"`);
    assert.ok(r.text.includes(sw.why), `${sw.id}: no "why"`);
    assert.ok(r.text.includes(`Model: ${sw.model_name}.`), `${sw.id}: no model name`);
    // The backend's own line already says to turn the main switch on first.
    assert.equal((r.text.match(/first/g) || []).length, 1, `${sw.id} says it twice`);
  }
});

await check("turning the main switch ON sends one request, raises a card, and stays off while it waits", async () => {
  const page = await open({ status: BM.status_ready_off });
  // click(), not check(): the box must NOT stay ticked.
  await page.locator("#bm-switch-master").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  const calls = await page.evaluate(() => window.__calls.map(([c]) => c));
  await page.close();
  assert.deepEqual(s.changes, [{ switch: "master", enabled: true }]);
  assert.ok(!calls.includes("decide_approval"), "the page answered its own card");
  const master = row(s, "master");
  assert.equal(master.checked, false, "shown as on before the card was approved");
  assert.equal(master.disabled, true, "a second card could be raised for the same switch");
  assert.equal(master.state, "waiting");
  assert.match(master.text, /Waiting for your approval\. Approve it in the Jarvis bar, on the widget, or on your phone's Home screen/);
  assert.match(s.status, /Waiting for your approval/);
  // The desktop's existing waiting words: the Brain's model install says them.
  assert.ok(read("src/brain.js").includes(
    "Approve it ${APPROVE_WHERE} — nothing changes until you do."));
});

await check("a card already waiting (the real pending case): says so, and the jobs stay off", async () => {
  const page = await open({ status: BM.status_pending });
  const s = await section(page);
  await page.close();
  const master = row(s, "master");
  assert.equal(master.state, "waiting");
  assert.equal(master.disabled, true);
  assert.match(master.text, /Waiting for your approval/);
  assert.ok(s.rows.filter((r) => r.id !== "master").every((r) => r.disabled));
});

await check("when the approval queue changes, the page re-reads and shows what the card decided", async () => {
  const page = await open({ status: BM.status_pending });
  const before = await page.evaluate(() => window.__bigModel.reads);
  await page.evaluate((next) => {
    window.__bigModel.status = next;
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, BM.status_on_idle);
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.ok(s.reads > before, "the decision did not make the page read again");
  assert.equal(row(s, "master").checked, true);
  assert.match(s.status, /"Use the big model" is on\./);
  assert.match(row(s, "deep_questions").text, /On\. DeepSeek V4 Flash starts when this job next has work/);
});

await check("a denied card: the switch is still off, and the page says it was not turned on", async () => {
  const page = await open({ status: BM.status_pending });
  await page.evaluate((next) => {
    window.__bigModel.status = next;
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, BM.status_ready_off);
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.equal(row(s, "master").checked, false);
  assert.match(s.status, /"Use the big model" was not turned on/);
});

// AP-6 (audit 3): what the card really did, from status().last when the
// backend has it; the old words when it does not.
const bmEndedWith = async (last) => {
  const page = await open({ status: BM.status_pending });
  await page.evaluate(({ next, last }) => {
    if (last) next.last = { at: Date.now() / 1000, ...last };
    window.__bigModel.status = next;
    window.__emit("approvals-changed", { count: 0, items: [] });
  }, { next: BM.status_ready_off, last });
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  return s.status;
};

await check("how the big model's card ended comes from `last` when the backend sends it", async () => {
  assert.match(await bmEndedWith({ feature: "master", outcome: "denied" }),
    /"Use the big model" was not turned on: the card was denied\./);
  assert.match(await bmEndedWith({ feature: "master", outcome: "refused", why: "colibri is not installed" }),
    /Jarvis refused it\. Colibri is not installed\./);
  assert.match(await bmEndedWith({ feature: "master", outcome: "expired" }), /ran out of time before anyone answered it/);
  assert.match(await bmEndedWith(null), /"Use the big model" was not turned on: the card was denied or ran out of time\./);
});

await check("while a card waits it re-reads gently; with nothing waiting it does not poll", async () => {
  const page = await open({ status: BM.status_pending });
  const first = await page.evaluate(() => window.__bigModel.reads);
  await page.waitForTimeout(5600);
  const later = await page.evaluate(() => window.__bigModel.reads);
  await page.close();
  assert.ok(later > first, "no re-read while the card waited");
  assert.ok(later - first <= 2, `re-read ${later - first} times in under six seconds - not gentle`);
  const quiet = await open({ status: BM.status_ready_off });
  const a = await quiet.evaluate(() => window.__bigModel.reads);
  await quiet.waitForTimeout(5600);
  const b = await quiet.evaluate(() => window.__bigModel.reads);
  await quiet.close();
  assert.equal(b, a, "polled with nothing waiting");
});

await check("turning a job OFF is immediate", async () => {
  const page = await open({ status: BM.status_on_idle });
  await page.locator("#bm-switch-deep_questions").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.changes, [{ switch: "deep_questions", enabled: false }]);
  assert.equal(row(s, "deep_questions").checked, false);
  assert.equal(row(s, "deep_questions").state, "off");
  assert.match(s.status, /"Deep questions" is off\./);
});

await check("the main switch OFF is immediate, in the backend's words", async () => {
  const page = await open({ status: BM.status_on_idle });
  await page.locator("#bm-switch-master").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.changes, [{ switch: "master", enabled: false }]);
  assert.equal(s.status, BM.post_master_off.body.message);
  assert.equal(row(s, "master").checked, false);
});

await check("on, but not enough memory free right now: stays on, says why, and can be turned off", async () => {
  const st = BM.status_not_enough_free_memory;
  const page = await open({ status: st });
  const s = await section(page);
  await page.close();
  for (const sw of st.switches) {
    const r = row(s, sw.id);
    assert.equal(r.checked, true, `${sw.id} was flipped off`);
    assert.equal(r.disabled, false, `${sw.id} cannot be turned off`);
  }
  assert.match(row(s, "wiki").text, /needs 24 GB of free memory and 12\.4 GB is free right now/);
  // The backend's line ends "wait.." - shown with one full stop.
  assert.doesNotMatch(row(s, "deep_questions").text, /\.\./);
  assert.match(s.engine, /^Failed\. Not started: Qwen3\.6-35B-A3B needs 24 GB/);
});

await check("a refusal is the backend's own sentence, and the switch goes back to what Jarvis says", async () => {
  const refusal = "A card to turn on the big model is already waiting - approve or deny that one";
  const page = await open({ status: BM.status_ready_off, setFails: refusal });
  await page.locator("#bm-switch-master").click();
  await page.waitForTimeout(300);
  const s = await section(page);
  await page.close();
  assert.equal(s.status, refusal);
  assert.equal(row(s, "master").checked, false);
});

/* ── The engine, the graphics card, the key, the speed ────────────────── */

await check("the engine: off, loading, ready, failed - with why, where it listens and when it stops", async () => {
  const want = {
    status_ready_off: /^Off\. Not running - it starts only when a background job needs it\./,
    status_loading: /^Loading\. Loading DeepSeek V4 Flash from E: - this can take several minutes\./,
    status_running: /^Ready\. Running DeepSeek V4 Flash on 127\.0\.0\.1:8765 \(this PC only\)/,
    status_cuda_refused: /^Failed\. \[big_model\] cuda is "on", but there is no capable second card/,
  };
  for (const [name, re] of Object.entries(want)) {
    const page = await open({ status: BM[name] });
    const s = await section(page);
    await page.close();
    assert.match(s.engine, re, name);
    assert.equal(s.address, "Listens on 127.0.0.1:8765 - this computer only. Stops 10 minutes after its last job.", name);
  }
});

await check("while colibri is loading the page re-reads gently, so Ready shows without reopening", async () => {
  const page = await open({ status: BM.status_loading });
  const first = await page.evaluate(() => window.__bigModel.reads);
  await page.evaluate((next) => { window.__bigModel.status = next; }, BM.status_running);
  await page.waitForTimeout(5600);
  const s = await section(page);
  await page.close();
  assert.ok(s.reads > first, "no re-read while loading");
  assert.match(s.engine, /^Ready\./);
});

await check("the graphics card line is the backend's cuda.why, and a refused setting is marked", async () => {
  const off = await open({ status: BM.status_ready_off });
  const a = await section(off);
  await off.close();
  assert.match(a.cuda, /^Not used: \[big_model\] cuda is "off", so colibri runs on the processor/);
  assert.equal(a.cudaTone, "");
  const on = await open({ status: BM.status_cuda_refused });
  const b = await section(on);
  await on.close();
  assert.match(b.cuda, /colibri is never put on the main card: that one is everyday chat\.$/);
  assert.equal(b.cudaTone, "bad");
});

await check("where the key is kept is shown, never a key", async () => {
  const kept = await open({ status: BM.status_running });
  const a = await section(kept);
  await kept.close();
  assert.equal(a.key, 'Kept in Windows Credential Manager, "Jarvis Big Model/api key". ' +
    "The key itself is never shown here, and only colibri on this PC is given it.");
  const notYet = await open({ status: BM.status_ready_off });
  const b = await section(notYet);
  await notYet.close();
  assert.match(b.key, /^Not made yet\. It is made when colibri first starts, then kept in Windows Credential Manager/);
  // status() has no key in it to show, and the page asks for nothing else.
  for (const st of Object.entries(BM).filter(([k]) => k.startsWith("status_")).map(([, v]) => v)) {
    assert.deepEqual(Object.keys(st).filter((k) => /key/.test(k)).sort(), ["key_kept", "key_where"]);
  }
});

await check("speed: \"not measured on this PC yet\" until there are numbers, and the unverified line always", async () => {
  const st = BM.status_ready_off;
  const page = await open({ status: st });
  const s = await section(page);
  await page.close();
  assert.equal(st.verified, false);
  assert.equal(s.measured.length, 2);
  for (const m of s.measured) assert.match(m, /Not measured on this PC yet\./);
  assert.equal(s.unverified, st.unverified);
});

await check("speed: the measured numbers when there are some - words a second, tokens, time, model", async () => {
  const st = BM.status_after_one_answer;
  const page = await open({ status: st });
  const s = await section(page);
  await page.close();
  const [wiki, deep] = s.measured;
  assert.match(wiki, /^Wiki builder\nNot measured on this PC yet\./);
  assert.match(deep, /^Deep questions\n1\.12 words a second \(1\.5 tokens a second\)\./);
  assert.match(deep, /12 tokens in 8 s, by DeepSeek V4 Flash/);
  assert.equal(s.unverified, st.unverified);
  assert.match(s.unverified, /None of colibri's speed figures have been checked on this PC/);
  noRaw(s.all);
});

/* ── When it cannot be read ────────────────────────────────────────────── */

await check("an older backend (404, or 503 with no module): says to run apply-patches.ps1", async () => {
  const page = await open({ status: BM.status_ready_off, unavailable: true });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.equal(s.stateHidden, false);
  assert.match(s.state, /Update the backend by running apply-patches\.ps1/);
  noRaw(s.state);
});

await check("Jarvis not answering: a sentence, never an error dump", async () => {
  const page = await open({ status: BM.status_ready_off,
    getFails: "Jarvis is not answering at http://127.0.0.1:4719. Is it running?" });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.match(s.state, /^Jarvis could not be asked about the big model\. Jarvis is not answering at http:\/\/127\.0\.0\.1:4719\. Is it running\?$/);
});

await check("an error that is not a sentence is not shown as is", async () => {
  const page = await open({ status: BM.status_ready_off,
    getFails: "{\"error\": \"Traceback (most recent call last)\"}" });
  const s = await section(page);
  await page.close();
  assert.doesNotMatch(s.state, /Traceback|\{/);
  assert.match(s.state, /Try again in a moment/);
});

await check("an answer that is not status() is not drawn", async () => {
  const page = await open({ status: BM.deep_done });
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.match(s.state, /could not be read/);
  noRaw(s.state);
});

/* ── Controls: the Rust ────────────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};

await check("CONTROL: both commands send X-Jarvis-Client: hud and the token the usual way, to the configured backend, and log nothing", async () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /const JARVIS_CLIENT: &str = "hud";/);
  const headers = fnBody(rust, "pub fn jarvis_headers(");
  assert.match(headers, /"X-Jarvis-Client"/);
  assert.match(headers, /"X-Jarvis-Token"/);
  for (const sig of ["pub async fn get_big_model(", "pub async fn set_big_model("]) {
    const body = fnBody(rust, sig);
    assert.match(body, /\.headers\(jarvis_headers\(&app\)\?\)/, `${sig} does not send the usual headers`);
    assert.match(body, /format!\("\{base\}\{BIG_MODEL_PATH\}"\)/, `${sig} builds its own URL`);
    assert.match(body, /let base = jarvis_base\(&app\);/);
    assert.doesNotMatch(body, /println!|eprintln!|log::|tracing::|dbg!/, `${sig} logs`);
    assert.doesNotMatch(body, /token/i, `${sig} touches the token itself`);
  }
  assert.match(rust, /pub\(crate\) const BIG_MODEL_PATH: &str = "\/api\/big-model";/);
});

await check("CONTROL: the switch body is built in Rust from one of three names, and ON is held on a stale link", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const set = fnBody(rust, "pub async fn set_big_model(");
  assert.match(set, /switch: String,\n\s+enabled: bool,/);
  assert.match(set, /let switch = big_model_switch\(&switch\)\?;/);
  assert.match(set, /\.json\(&serde_json::json!\(\{ "switch": switch, "enabled": enabled \}\)\)/);
  assert.match(set, /if enabled && app\.state::<crate::stream::StreamState>\(\)\.link\(\)\.stale/);
  assert.match(rust, /pub\(crate\) const BIG_MODEL_SWITCHES: \[&str; 3\] = \["master", "wiki", "deep_questions"\];/);
  // It approves nothing: no approval route anywhere near it.
  assert.doesNotMatch(set, /approve|decide/i);
});

await check("CONTROL: only the settings window may read or change the big model", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  for (const perm of ["allow-get-big-model", "allow-set-big-model"]) {
    const holders = sets.filter((s) => s.includes(`"${perm}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["settings-surface"], `${perm} is held by ${holders}`);
  }
  assert.match(read("src-tauri/capabilities/settings.json"), /"settings-surface"/);
  for (const c of ["brain", "faces", "hud", "onboarding", "quickbar", "widget"]) {
    const json = read(`src-tauri/capabilities/${c}.json`);
    assert.ok(!json.includes("settings-surface"), `${c} holds settings-surface`);
    assert.ok(!json.includes("big-model"), `${c} can reach the big model's switches`);
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const cmd of ["get_big_model", "set_big_model"]) {
    assert.ok(build.includes(`"${cmd}"`), `${cmd} is not in build.rs, so no window can call it`);
    assert.ok(lib.includes(`commands::${cmd},`), `${cmd} is not registered`);
    const gen = read(`src-tauri/permissions/autogenerated/${cmd}.toml`);
    assert.match(gen, new RegExp(`commands.allow = \\["${cmd}"\\]`));
  }
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nThe big model is off until it is asked for, and says how slow it really is");
process.exit(fails.length ? 1 : 0);
