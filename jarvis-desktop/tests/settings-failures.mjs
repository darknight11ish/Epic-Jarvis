/**
 * A Settings control that cannot reach the PC must SAY so.
 *
 * WHY THIS SUITE EXISTS (settings audit, 2026-10-08). Four controls failed in
 * silence, and silence is the one thing a settings screen must never do: it
 * leaves the owner believing a switch took effect while nothing changed. Every
 * one of these was proven by driving the real page with the command made to
 * fail (`invokeFails`, the hook in tests/uikit.mjs) - the switches sprang back
 * with no words, the theme stayed painted on a value the store never took, and
 * four notification switches could be saved OFF while the PC kept notifying.
 *
 * The failure path is the whole point: a scenario that only ever sees successes
 * cannot catch any of this, which is why these survived 43 passing suites.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const open = async (invokeFails) => {
  const page = await K.open(browser, base, "settings.html", { invokeFails }, { width: 900, height: 1000 });
  // Cards fold (the 28 Fold buttons); a folded control cannot be clicked, and
  // what is being tested is the reporting, not the disclosure.
  await page.evaluate(() => {
    for (const d of document.querySelectorAll("details")) d.open = true;
  });
  return page;
};

const text = (page, id) => page.locator(`#${id}`).innerText().then((s) => (s || "").trim());

await check("a refused theme change puts the theme back AND says so", async () => {
  const page = await open({ set_theme: "the PC refused it" });
  await page.waitForTimeout(400);
  const before = await page.evaluate(() => ({
    theme: document.documentElement.getAttribute("data-theme"),
    painted: getComputedStyle(document.documentElement).getPropertyValue("--bg").trim(),
  }));
  const other = await page.evaluate(() => {
    const now = document.documentElement.getAttribute("data-theme");
    const row = [...document.querySelectorAll('#theme-list input[name="theme"]')]
      .find((i) => i.value !== now);
    return row ? row.value : null;
  });
  assert.ok(other, "no second theme to pick");
  // A plain click, not `.check()`: the page is SUPPOSED to put the tick back
  // when the save is refused, so `.check()`'s own "did the state change?"
  // assertion is exactly what must not hold here.
  await page.locator(`#theme-list input[value="${other}"]`).click();
  await page.waitForTimeout(500);
  const after = await page.evaluate(() => ({
    theme: document.documentElement.getAttribute("data-theme"),
    painted: getComputedStyle(document.documentElement).getPropertyValue("--bg").trim(),
  }));
  const said = await text(page, "appearance-status");
  await page.close();
  assert.equal(after.theme, before.theme,
    `the window is painted ${after.theme} while the PC still has ${before.theme}`);
  assert.equal(after.painted, before.painted, "the colours changed to a theme that was never saved");
  assert.ok(said.length > 0, "the refused theme change said nothing at all");
});

await check("a refused Match Windows toggle springs back AND says so", async () => {
  const page = await open({ set_theme_follow_system: "the PC refused it" });
  await page.waitForTimeout(400);
  const was = await page.locator("#follow-system").isChecked();
  await page.locator("#follow-system").click();
  await page.waitForTimeout(400);
  const now = await page.locator("#follow-system").isChecked();
  const said = await text(page, "appearance-status");
  await page.close();
  assert.equal(now, was, "the box did not spring back");
  assert.ok(said.length > 0, "the switch sprang back with no words");
});

await check("a refused Floating face toggle springs back AND says so", async () => {
  const page = await open({ set_floating: "the PC refused it" });
  await page.waitForTimeout(400);
  const was = await page.locator("#floating-enabled").isChecked();
  await page.locator("#floating-enabled").click();
  await page.waitForTimeout(400);
  const now = await page.locator("#floating-enabled").isChecked();
  const said = await text(page, "appearance-status");
  await page.close();
  assert.equal(now, was, "the box did not spring back");
  assert.ok(said.length > 0, "the switch sprang back with no words");
});

await check("a notification switch that cannot reach the PC says so", async () => {
  const page = await open({ set_notification_prefs: "the PC refused it" });
  await page.waitForTimeout(400);
  // The boot-time carry-over push fails too, and says so; clear that first, so
  // this check is about the SAVE reporting, not about the page having spoken
  // once at load.
  await page.evaluate(() => { document.getElementById("notif-status").textContent = ""; });
  const was = await page.locator("#notif-alarms").isChecked();
  await page.locator("#notif-alarms").click();
  await page.waitForTimeout(500);
  const now = await page.locator("#notif-alarms").isChecked();
  const said = await text(page, "notif-status");
  await page.close();
  assert.notEqual(now, was, "the switch never moved, so the save was not exercised");
  assert.ok(said.length > 0,
    "a switch was saved OFF (or ON) while the PC never got it, and nothing was said");
});

await check("the notification switches still save quietly when the PC does take them", async () => {
  // The control for the check above: with no failure injected the status line
  // must stay empty, or the warning would be noise the owner learns to ignore.
  const page = await open({});
  await page.waitForTimeout(400);
  await page.locator("#notif-alarms").click();
  await page.waitForTimeout(500);
  const said = await text(page, "notif-status");
  await page.close();
  assert.equal(said, "", `a save that worked still complained: ${said}`);
});

await check("a failed Find it for me is reported in plain words, never raw JavaScript", async () => {
  // Two ways this used to leak: the call itself failing, and an answer with no
  // shape (`result.found` on null threw inside the handler).
  for (const [label, data] of [
    ["the call refused", { find_python: "Cannot read properties of null (reading 'found')" }],
    ["an answer with no shape", {}],
  ]) {
    const page = await open(data);
    await page.waitForTimeout(300);
    await page.locator("#find-python").click();
    await page.waitForTimeout(500);
    const said = await text(page, "find-python-status");
    await page.close();
    assert.ok(said.length > 0, `${label}: the failure said nothing`);
    assert.doesNotMatch(said, /Cannot read|undefined|null|[{}<>]|::/,
      `${label}: raw JavaScript reached the owner: ${said}`);
  }
});

await browser.close(); close();
console.log(fails.length ? `\n${fails.length} FAILED` : "\nevery failing settings control speaks");
process.exit(fails.length ? 1 : 0);
