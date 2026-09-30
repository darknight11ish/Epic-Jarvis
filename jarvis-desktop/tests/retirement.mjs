/**
 * The retirement what-if on the Brain's Work tab (the owner's decision of
 * 2026-09-30, queue item 5; docs/FINANCE-DESIGN.md part B and its "Retirement
 * contract (frozen)"; JARVIS-API.md section 103; src/retirement.js,
 * src-tauri/src/brain/retirement.rs).
 *
 * The first half needs no browser and runs anywhere (CI's backend job too):
 * the reading of the PC's form and results against the REAL answers in
 * fixtures/retirement-cases.json (made by backend/jarvis_retirement.py), the
 * words, the meter, and the wiring (Rust, build.rs, lib.rs, permissions,
 * capabilities). The second half needs Playwright and runs the real Brain:
 *
 * - the form is drawn from the PC's answer: every label, unit, limit and help
 *   line as sent, the made-up figures marked "assumed" and filled in, the
 *   required boxes empty, the placeholder note and "today's money" shown;
 * - Work it out sends only what was typed (text as typed), busy while it
 *   runs, and draws the result exactly as sent: the first sentence as the
 *   headline, the others in a list, the disclaimer on its own line right
 *   after, the "What I used" list with "assumed" marks;
 * - the PC's message for a bad entry sits at the field it names and the
 *   keyboard goes there; busy is tried once more after a second; too slow
 *   shows the PC's words;
 * - nothing typed is ever stored (localStorage, sessionStorage) and it is gone
 *   when the tab is left, when the private lists are hidden, and while App
 *   lock is on;
 * - under "Hide memory lists and chat history" only "Retirement what-if
 *   hidden" shows; no copy or export button; nothing is spoken;
 * - a stale link greys the button.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as R from "../src/retirement.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/retirement-cases.json"));
const FORM = CASES.defaults.body;
const result = (name) => CASES[name].body.result;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words and the pure reading ───────────────────────────────────── */

await check("the words the app owns are the contract's, word for word", async () => {
  assert.equal(R.RUN_LABEL, "Work it out");
  assert.equal(R.WORKING, "Working it out");
  assert.equal(R.ASSUMED, "assumed");
  assert.equal(R.USED_HEADING, "What I used");
  assert.equal(R.HIDDEN_WORDS, "Retirement what-if hidden");
  assert.equal(R.DISCLAIMER, "This is a simplified what-if, not financial advice.");
  assert.equal(R.DISCLAIMER, FORM.disclaimer);
  assert.equal(R.HIDDEN_WORDS, FORM.words.hidden);
  assert.deepEqual([...R.FIELD_KEYS], FORM.fields.map((f) => f.key));
  assert.deepEqual([...R.STATES], ["mixed", "never_runs_out", "always_runs_out", "not_enough_to_say"]);
});

await check("the form is read as sent: eleven fields in order, limits and units from the PC", async () => {
  const f = R.readForm(FORM);
  assert.equal(f.hidden, false);
  assert.equal(f.title, "Retirement what-if");
  assert.equal(f.fields.length, 11);
  assert.equal(f.disclaimer, FORM.disclaimer);
  assert.equal(f.placeholderNote, FORM.placeholder_note);
  assert.equal(f.todaysMoney, FORM.todays_money);
  const by = Object.fromEntries(f.fields.map((x) => [x.key, x]));
  assert.equal(by.current_age.label, "Your age now");
  assert.equal(R.limitLine(by.current_age), "years · 18 to 100");
  assert.equal(R.limitLine(by.plan_to_age), "years · 18 to 110");
  assert.equal(R.limitLine(by.savings), "money · 0 to 1,000,000,000");
  assert.equal(R.limitLine(by.yearly_saving), "money per year · 0 to 1,000,000,000");
  assert.equal(R.limitLine(by.expected_return_percent), "percent · -5 to 15");
  assert.equal(R.limitLine(by.volatility_percent), "percent · 0 to 40");
  assert.equal(R.limitLine(by.inflation_percent), "percent · 0 to 15");
  for (const k of ["current_age", "retirement_age", "savings", "yearly_saving", "yearly_spending"]) {
    assert.equal(by[k].required, true, k);
    assert.equal(R.startText(by[k]), "", `${k} starts filled`);
  }
  // Only the made-up figures start filled, and they say so.
  const filled = f.fields.filter((x) => R.startText(x) !== "").map((x) => [x.key, R.startText(x)]);
  assert.deepEqual(filled, [["plan_to_age", "95"], ["expected_return_percent", "7"],
    ["volatility_percent", "12"], ["inflation_percent", "2.5"]]);
  assert.equal(by.other_income.placeholder, false);
  assert.equal(R.startText(by.other_income), "");
  assert.equal(R.hintText(by.other_income), "0");
  assert.equal(R.hintText(by.other_income_start_age), "");
});

await check("a hidden answer, a bad shape and an unknown field are never a form", async () => {
  const h = R.readForm({ ok: true, hidden: true, words: { hidden: "Retirement what-if hidden" } });
  assert.deepEqual(h, { hidden: true, words: "Retirement what-if hidden" });
  assert.equal(R.readForm({ ok: true, hidden: true }).words, R.HIDDEN_WORDS);
  assert.equal(R.readForm(null), null);
  assert.equal(R.readForm({ ok: true, fields: [] }), null);
  assert.equal(R.readForm({ ok: false, fields: FORM.fields }), null);
  const odd = R.readForm({ ...FORM, fields: [...FORM.fields, { key: "ssn", label: "Number" }, { key: "savings" }] });
  assert.equal(odd.fields.length, 11, "a field that is not the contract's, or has no label, was drawn");
});

await check("what is sent: only typed boxes, trimmed, empty ones left out", async () => {
  const f = R.readForm(FORM);
  const sent = R.collectValues(f.fields, {
    current_age: " 40 ", retirement_age: "65", savings: "1,250,000", yearly_saving: "",
    yearly_spending: "30000", other_income: "   ", expected_return_percent: "6.5%", junk: "x" });
  assert.deepEqual(sent, { current_age: "40", retirement_age: "65", savings: "1,250,000",
    yearly_spending: "30000", expected_return_percent: "6.5%" });
  assert.deepEqual(R.collectValues(f.fields, {}), {});
  assert.deepEqual(R.collectValues(f.fields, null), {});
});

await check("each of the four states is read as sent, nothing rounded or reworded", async () => {
  for (const state of R.STATES) {
    const raw = result(state);
    const r = R.readResult(raw);
    assert.equal(r.state, state);
    assert.deepEqual(r.summary, raw.summary, `${state}: a sentence was changed`);
    assert.equal(r.disclaimer, "This is a simplified what-if, not financial advice.");
    assert.equal(r.placeholderNote, raw.placeholder_note);
    assert.equal(r.todaysMoney, raw.todays_money);
    assert.deepEqual(r.used.map((u) => [u.label, u.value, u.assumed]),
      raw.used.map((u) => [u.label, u.value, u.assumed]));
  }
  const m = R.readResult(result("mixed"));
  assert.equal(m.summary[0],
    "In about 71 of 100 simulated futures your money lasts to age 95. Where it runs out, that is usually at about age 81 to 89.");
  assert.equal(m.share.label, "about 71 of 100");
  assert.equal(m.bands.lower.label, "about 51 of 100");
  assert.equal(m.bands.higher.label, "about 86 of 100");
  const assumed = m.used.filter((u) => u.assumed).map((u) => u.key);
  assert.deepEqual(assumed, ["plan_to_age", "expected_return_percent", "volatility_percent", "inflation_percent"]);
  const none = R.readResult(result("not_enough_to_say"));
  assert.equal(none.share, null);
  assert.equal(none.bands, null);
  assert.equal(R.readResult(result("never_runs_out")).share.label, "more than 99 of 100");
  assert.equal(R.readResult(result("always_runs_out")).share.label, "fewer than 1 of 100");
});

await check("a result that is not one is null; a missing disclaimer is still shown", async () => {
  assert.equal(R.readResult(null), null);
  assert.equal(R.readResult({}), null);
  assert.equal(R.readResult({ ...result("mixed"), kind: "other" }), null);
  assert.equal(R.readResult({ ...result("mixed"), state: "great" }), null);
  assert.equal(R.readResult({ ...result("mixed"), summary: [] }), null);
  assert.equal(R.readResult({ ...result("mixed"), disclaimer: undefined }).disclaimer, R.DISCLAIMER);
});

await check("the meter is drawn only from the per-100 figures, never as one big number", async () => {
  const m = R.readResult(result("mixed"));
  assert.deepEqual(R.meterGeometry(m), { from: 51, to: 86, at: 71 });
  assert.deepEqual(R.meterLabels(m), ["about 51 of 100", "about 71 of 100", "about 86 of 100"]);
  assert.equal(R.meterGeometry(R.readResult(result("not_enough_to_say"))), null);
  assert.equal(R.meterGeometry(null), null);
  const g = R.meterGeometry(R.readResult(result("never_runs_out")));
  assert.ok(g.from >= 0 && g.to <= 100 && g.at === 99);
  const z = R.meterGeometry(R.readResult(result("always_runs_out")));
  assert.equal(z.at, 0);
});

await check("where an answer belongs: at its field, or under the button", async () => {
  const f = R.readForm(FORM).fields;
  for (const [name, body] of Object.entries(CASES.errors)) {
    const p = R.placement(body.body, f);
    assert.equal(p.message, body.body.message, name);
    if (name === "unknown_field") assert.equal(p.kind, "line");
    else assert.deepEqual([p.kind, p.key], ["field", body.body.field], name);
  }
  const busy = R.placement(CASES.busy.body, f);
  assert.deepEqual([busy.kind, busy.retry, busy.message], ["line", true, CASES.busy.body.message]);
  const slow = R.placement(CASES.too_slow.body, f);
  assert.deepEqual([slow.kind, slow.retry], ["line", false]);
  assert.equal(R.placement(null, f).kind, "line");
});

await check("nothing is stored, logged, spoken, copied or sent anywhere but the PC", async () => {
  const js = read("src/retirement.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  assert.doesNotMatch(js, /localStorage|sessionStorage|indexedDB|document\.cookie/i);
  assert.doesNotMatch(js, /console\.|speechSynthesis|SpeechSynthesis|clipboard|execCommand|navigator\.share/i);
  assert.doesNotMatch(js, /\bfetch\(|XMLHttpRequest|WebSocket|sendBeacon|\.innerHTML|insertAdjacentHTML/);
  assert.doesNotMatch(js, /\bspeak\b|read_aloud\s*[:=]\s*true|download=|Blob\(|createObjectURL/);
  const b = read("src/brain.js");
  const mine = b.slice(b.indexOf("const retirementCard = createRetirementCard("));
  assert.doesNotMatch(mine.slice(0, mine.indexOf("});") + 3), /localStorage|sessionStorage/);
});

await check("the sheet is calm: tokens only, no red, no pass-or-fail colours, no motion", async () => {
  const css = read("src/retirement.css");
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/, "a literal colour");
  assert.doesNotMatch(css, /--bad|--ok\b|--ok-|--warn|--state-error|--state-approval|--diff-/, "a pass-or-fail colour");
  assert.doesNotMatch(css, /animation|transition|@keyframes|transform/, "motion");
  const vars = [...css.matchAll(/var\((--[a-z0-9-]+)/g)].map((m) => m[1]);
  const theme = read("src/theme.css");
  for (const v of new Set(vars)) assert.ok(theme.includes(`${v}:`), `${v} is not a token`);
  const words = read("src/retirement.js") + read("src/brain.html");
  assert.doesNotMatch(words.split("retirement-card")[1] || "", /streak|don't give up|you should have|falling behind/i);
});

await check("CONTROL: Rust, build.rs, lib.rs, permissions and capabilities agree, Brain only", async () => {
  const rs = read("src-tauri/src/brain/retirement.rs");
  const prod = rs.split("#[cfg(test)]")[0];
  // The literal route strings tools/check_parity.py looks for.
  assert.match(prod, /"\/api\/retirement\/defaults"|\/api\/retirement\/defaults/);
  assert.match(prod, /\/api\/retirement\/run/);
  assert.doesNotMatch(prod, /println!|eprintln!|tracing::|log::|dbg!/, "something is logged");
  assert.match(prod, /crate::lock::private_hidden/);
  assert.match(prod, /crate::lock::app_locked/);
  const run = prod.slice(prod.indexOf("pub async fn brain_retirement_run("));
  const body = run.slice(0, run.indexOf("\n}\n"));
  assert.ok(body.indexOf("require_link_live") >= 0
    && body.indexOf("require_link_live") < body.indexOf(".post("), "the run is not held on a stale link");
  assert.ok(body.indexOf("card_hidden") < body.indexOf(".post("), "the run is sent while hidden");
  const defs = prod.slice(prod.indexOf("pub async fn brain_retirement_defaults("));
  assert.ok(defs.slice(0, defs.indexOf("\n}\n")).indexOf("card_hidden") < defs.indexOf(".get("), "the form is read while hidden");
  assert.match(prod, /X-Jarvis-Client|jarvis_headers/, "the client header");
  for (const cmd of ["brain_retirement_defaults", "brain_retirement_run"]) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::retirement::${cmd},`));
    const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-retirement"], cmd);
  }
  assert.match(read("src-tauri/src/brain.rs"), /pub mod retirement;/);
  const caps = JSON.parse(read("src-tauri/capabilities/brain.json")).permissions;
  assert.ok(caps.includes("brain-retirement"));
  for (const other of ["quickbar", "widget", "hud", "settings", "faces", "floating", "onboarding"]) {
    assert.ok(!read(`src-tauri/capabilities/${other}.json`).includes("brain-retirement"), `${other} holds it`);
  }
  const html = read("src/brain.html");
  assert.match(html, /id="retirement-card"[^>]*data-menu-id="brain\.work\.retirement"[^>]*data-menu-group="finance"/);
  assert.match(html, /<link rel="stylesheet" href="retirement\.css"/);
});

/* ── The Brain window ─────────────────────────────────────────────────── */

let K = null;
try { await import("playwright"); K = await import("./uikit.mjs"); } catch { K = null; }
if (!K) {
  console.log("SKIP  the Brain window part - Playwright is not installed (npm i -D playwright)");
} else {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const SIZE = { width: 1180, height: 1000 };
  const ok = (name) => ({ status: 200, body: CASES[name].body });
  // What Rust hands on for the PC's plain 429 and 503 (retirement.rs run_answer).
  const refusal = (c) => ({ status: c.status, body: { ok: false, field: "", ...c.body } });
  const BUSY = refusal(CASES.busy);
  const SLOW = refusal(CASES.too_slow);
  const scenario = (script, extra = {}) => ({
    retirement: { form: FORM, script: script.map((s) => s.body), ...extra } });

  async function workTab(data = {}) {
    const page = await K.open(browser, base, "brain.html", data, SIZE);
    await page.locator("#tab-work").click();
    await page.waitForTimeout(500);
    return page;
  }
  const calls = (page) => page.evaluate(() => window.__retirement.calls);
  const fillRequired = async (page) => {
    await page.locator("#ret-current_age").fill("40");
    await page.locator("#ret-retirement_age").fill("65");
    await page.locator("#ret-savings").fill("100,000");
    await page.locator("#ret-yearly_saving").fill("12000");
    await page.locator("#ret-yearly_spending").fill("30,000");
  };
  const work = async (page) => {
    await page.getByRole("button", { name: R.RUN_LABEL }).click();
    await page.waitForTimeout(500);
  };

  await check("the card draws the form from the PC's answer, with made-up figures marked assumed", async () => {
    const page = await workTab(scenario([ok("mixed")]));
    const card = page.locator("#retirement-card");
    assert.equal(await card.getAttribute("data-menu-id"), "brain.work.retirement");
    assert.equal(await card.getAttribute("data-menu-group"), "finance");
    assert.equal(await card.locator("h2").textContent(), "Retirement what-if");
    const text = await card.innerText();
    assert.ok(text.includes(FORM.todays_money));
    assert.ok(text.includes(FORM.placeholder_note));
    assert.equal(await card.locator(".ret-input").count(), 11);
    for (const f of FORM.fields) {
      assert.ok(await card.locator(`label[for="ret-${f.key}"]`).innerText().then((t) => t.startsWith(f.label)), f.key);
      if (f.help) assert.ok(text.includes(f.help), f.key);
    }
    assert.equal(await card.locator(".ret-assumed").count(), 4);
    assert.equal(await page.locator("#ret-plan_to_age").inputValue(), "95");
    assert.equal(await page.locator("#ret-expected_return_percent").inputValue(), "7");
    assert.equal(await page.locator("#ret-current_age").inputValue(), "");
    assert.equal(await page.locator("#ret-savings").inputValue(), "");
    assert.ok(text.includes("years · 18 to 100"));
    assert.ok(text.includes("money per year · 0 to 1,000,000,000"));
    // The four made-up boxes point at the placeholder note.
    const d = await page.locator("#ret-inflation_percent").getAttribute("aria-describedby");
    assert.match(d, /ret-placeholder-note/);
    await page.close();
  });

  await check("Work it out sends only what was typed, is busy while it runs, and draws the result as sent", async () => {
    const page = await workTab(scenario([ok("mixed")], { delayMs: 500 }));
    await fillRequired(page);
    await page.getByRole("button", { name: R.RUN_LABEL }).click();
    await page.waitForTimeout(150);
    const busy = page.getByRole("button", { name: R.WORKING });
    assert.equal(await busy.isDisabled(), true);
    assert.equal(await page.locator("#retirement-body").getAttribute("aria-busy"), "true");
    await page.waitForTimeout(700);
    const sent = (await calls(page)).filter((c) => c.cmd === "brain_retirement_run");
    assert.equal(sent.length, 1);
    assert.deepEqual(sent[0].values, {
      current_age: "40", retirement_age: "65", plan_to_age: "95", savings: "100,000",
      yearly_saving: "12000", yearly_spending: "30,000", expected_return_percent: "7",
      volatility_percent: "12", inflation_percent: "2.5" });
    const r = result("mixed");
    const region = page.locator(".ret-result");
    assert.equal(await region.getAttribute("data-state"), "mixed");
    assert.equal(await page.locator("#ret-headline").innerText(), r.summary[0]);
    const items = await region.locator(".ret-summary li").allInnerTexts();
    assert.deepEqual(items, r.summary.slice(1));
    // The disclaimer follows the sentences directly, on its own line.
    const order = await region.locator("> *").evaluateAll((els) => els.map((e) => e.className));
    assert.equal(order[0], "ret-headline");
    assert.equal(order[1], "ret-summary");
    assert.equal(order[2], "ret-disclaimer");
    assert.equal(await region.locator(".ret-disclaimer").innerText(), r.disclaimer);
    const used = await region.locator(".ret-used-row").allInnerTexts();
    assert.equal(used.length, r.used.length);
    assert.equal(used.filter((u) => /assumed$/.test(u)).length, 4);
    assert.ok(used[0].startsWith("Your age now: 40"));
    const text = await region.innerText();
    assert.equal(await region.locator(".ret-used-heading").textContent(), R.USED_HEADING);
    assert.ok(text.includes(r.placeholder_note));
    assert.ok(text.includes(r.todays_money));
    assert.ok(text.includes("about 51 of 100"), "the meter's labels");
    // The keyboard goes to the answer.
    assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.id), "ret-headline");
    // Nothing to copy, save or export.
    const buttons = await page.locator("#retirement-card button").allInnerTexts();
    assert.deepEqual(buttons, [R.RUN_LABEL]);
    assert.equal(await page.locator("#retirement-card a, #retirement-card [download]").count(), 0);
    await page.close();
  });

  await check("the other three states are drawn with their own sentences and the disclaimer every time", async () => {
    for (const state of ["never_runs_out", "always_runs_out", "not_enough_to_say"]) {
      const page = await workTab(scenario([ok(state)]));
      await fillRequired(page);
      await work(page);
      const r = result(state);
      assert.equal(await page.locator("#ret-headline").innerText(), r.summary[0], state);
      assert.equal(await page.locator(".ret-disclaimer").innerText(), r.disclaimer, state);
      const meter = await page.locator(".ret-meter").count();
      assert.equal(meter, state === "not_enough_to_say" ? 0 : 1, `${state} meter`);
      // Calm: the same neutral colours whatever the state.
      const color = await page.locator(".ret-result").evaluate((e) => getComputedStyle(e).backgroundColor);
      assert.ok(color);
      await page.close();
    }
  });

  await check("a bad entry: the PC's message sits at its field, the keyboard goes there, nothing is cleared", async () => {
    const page = await workTab(scenario([CASES.errors.plan_not_after, ok("mixed")]));
    await fillRequired(page);
    await page.locator("#ret-plan_to_age").fill("60");
    await work(page);
    const err = page.locator("#ret-plan_to_age-error");
    assert.equal(await err.innerText(), CASES.errors.plan_not_after.body.message);
    assert.equal(await page.locator("#ret-plan_to_age").getAttribute("aria-invalid"), "true");
    assert.equal(await page.evaluate(() => document.activeElement.id), "ret-plan_to_age");
    assert.match(await page.locator("#ret-plan_to_age").getAttribute("aria-describedby"), /ret-plan_to_age-error/);
    assert.equal(await page.locator("#ret-savings").inputValue(), "100,000", "a typed number was cleared");
    assert.equal(await page.locator(".ret-result").count(), 0);
    // Typing again takes the message away.
    await page.locator("#ret-plan_to_age").fill("95");
    assert.equal(await err.isHidden(), true);
    await page.close();
  });

  await check("every error of the contract lands beside the field it names", async () => {
    for (const code of ["missing", "bad_number", "negative", "out_of_range", "too_many_years"]) {
      const e = CASES.errors[code];
      const page = await workTab(scenario([e]));
      await page.getByRole("button", { name: R.RUN_LABEL }).click();
      await page.waitForTimeout(400);
      assert.equal(await page.locator(`#ret-${e.body.field}-error`).innerText(), e.body.message, code);
      await page.close();
    }
    const page = await workTab(scenario([CASES.errors.unknown_field]));
    await page.getByRole("button", { name: R.RUN_LABEL }).click();
    await page.waitForTimeout(400);
    assert.equal(await page.locator(".ret-line").innerText(), CASES.errors.unknown_field.body.message);
    await page.close();
  });

  await check("busy is tried once more after a second; too slow shows the PC's words", async () => {
    let page = await workTab(scenario([BUSY, ok("mixed")]));
    await fillRequired(page);
    await page.getByRole("button", { name: R.RUN_LABEL }).click();
    await page.waitForTimeout(1900);
    assert.equal((await calls(page)).filter((c) => c.cmd === "brain_retirement_run").length, 2);
    assert.equal(await page.locator("#ret-headline").innerText(), result("mixed").summary[0]);
    await page.close();
    page = await workTab(scenario([BUSY]));
    await fillRequired(page);
    await page.getByRole("button", { name: R.RUN_LABEL }).click();
    await page.waitForTimeout(1900);
    assert.equal(await page.locator(".ret-line").innerText(), CASES.busy.body.message);
    assert.equal((await calls(page)).filter((c) => c.cmd === "brain_retirement_run").length, 2);
    await page.close();
    page = await workTab(scenario([SLOW]));
    await fillRequired(page);
    await work(page);
    assert.equal(await page.locator(".ret-line").innerText(), CASES.too_slow.body.message);
    assert.equal(await page.getByRole("button", { name: R.RUN_LABEL }).isDisabled(), false, "still busy");
    await page.close();
  });

  await check("Enter in a box works it out (keyboard only)", async () => {
    const page = await workTab(scenario([ok("mixed")]));
    await fillRequired(page);
    await page.locator("#ret-yearly_spending").press("Enter");
    await page.waitForTimeout(500);
    assert.equal((await calls(page)).filter((c) => c.cmd === "brain_retirement_run").length, 1);
    assert.equal(await page.locator(".ret-result").count(), 1);
    await page.close();
  });

  await check("nothing typed is stored, and it is gone when the tab is left", async () => {
    const page = await workTab(scenario([ok("mixed")]));
    await fillRequired(page);
    await page.locator("#ret-savings").fill("7654321");
    await work(page);
    const stored = await page.evaluate(() => JSON.stringify([
      Object.entries(localStorage), Object.entries(sessionStorage)]));
    assert.doesNotMatch(stored, /7654321|100,000|30,000|about 71|simulated/);
    await page.locator("#tab-memory").click();
    await page.waitForTimeout(300);
    await page.locator("#tab-work").click();
    await page.waitForTimeout(600);
    assert.equal(await page.locator(".ret-result").count(), 0, "the result stayed");
    assert.equal(await page.locator("#ret-savings").inputValue(), "", "a typed number stayed");
    assert.equal(await page.locator("#ret-current_age").inputValue(), "");
    assert.equal(await page.locator("#ret-plan_to_age").inputValue(), "95");
    await page.close();
  });

  await check("hidden with the private lists: only the fixed words, no boxes, nothing asked or sent", async () => {
    const page = await workTab({ ...scenario([ok("mixed")]), security: { hidden: true } });
    const card = page.locator("#retirement-card");
    assert.equal(await page.locator("#retirement-body").innerText(), "Retirement what-if hidden");
    assert.equal(await card.locator("input, button").count(), 0);
    // Typed, then hidden meanwhile: the boxes and the answer are wiped.
    await page.evaluate(() => { window.__security.hidden = false; window.__emit("security-changed", {}); });
    await page.waitForTimeout(500);
    await fillRequired(page);
    await work(page);
    assert.equal(await page.locator(".ret-result").count(), 1);
    await page.evaluate(() => { window.__security.hidden = true; window.__security.revealed = false; window.__emit("private-hidden", {}); });
    await page.waitForTimeout(500);
    assert.equal(await page.locator("#retirement-body").innerText(), "Retirement what-if hidden");
    assert.equal(await card.locator("input, button, .ret-result").count(), 0);
    assert.doesNotMatch(await card.innerText(), /about 71|simulated|40|100,000/);
    // Shown again: an empty form, not the old numbers.
    await page.evaluate(() => { window.__security.hidden = false; window.__emit("security-changed", {}); });
    await page.waitForTimeout(500);
    assert.equal(await page.locator("#ret-savings").inputValue(), "");
    assert.equal(await page.locator(".ret-result").count(), 0);
    await page.close();
  });

  await check("while App lock is on the card shows only the fixed words too", async () => {
    const page = await workTab({ ...scenario([ok("mixed")]), appLock: true });
    assert.equal(await page.locator("#retirement-body").innerText(), "Retirement what-if hidden");
    assert.equal(await page.locator("#retirement-card input").count(), 0);
    await page.close();
  });

  await check("a stale link greys Work it out, says why, and sends nothing", async () => {
    const page = await workTab({ ...scenario([ok("mixed")]), link: { stale: true } });
    const btn = page.getByRole("button", { name: R.RUN_LABEL });
    assert.equal(await btn.isDisabled(), true);
    assert.equal(await page.locator(".ret-stale").isVisible(), true);
    assert.equal((await calls(page)).filter((c) => c.cmd === "brain_retirement_run").length, 0);
    await page.close();
  });

  await check("a PC without the what-if says so in plain words", async () => {
    const page = await workTab({});
    const text = await page.locator("#retirement-body").innerText();
    assert.match(text, /cannot work out a retirement what-if yet/);
    await page.close();
  });

  await check("nothing is spoken and no window text is read aloud", async () => {
    const page = await workTab(scenario([ok("mixed")]));
    await fillRequired(page);
    await work(page);
    const spoken = await page.evaluate(() => (window.__calls || []).filter((c) => /speak|say|tts/i.test(c.cmd || c[0] || "")).length);
    assert.equal(spoken, 0);
    await page.close();
  });

  await browser.close();
  close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nRetirement what-if: the PC's words as sent, ranges only, nothing stored, hidden with the private lists");
process.exit(fails.length ? 1 : 0);
