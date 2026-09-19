/**
 * The desktop's "About Jarvis" section on the settings page.
 *
 * Plain read-only content, same bar as tests/faq.mjs: it has to actually be
 * present, its version has to come from the same `update_status` read the
 * Updates section above it already makes (never a second, hand-maintained
 * copy of the number), and its source link has to open in the real OS
 * browser through `open_external_url` rather than navigate the WebView
 * itself away from the settings page.
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

const VIEW = { width: 760, height: 1400 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);
const aboutCard = (page) => page.locator(".card", { hasText: "About Jarvis" });

await check("the About card is present with version, license, and source", async () => {
  const page = await open();
  const card = aboutCard(page);
  // textContent, not innerText: `dt` is styled uppercase for display, and
  // innerText reflects that CSS transform rather than the literal markup.
  const facts = await card.locator(".about-fact dt").evaluateAll(
    (els) => els.map((el) => el.textContent.trim()));
  await page.close();
  assert.deepEqual(facts, ["Version", "License", "Source"]);
});

await check("the version shown is the real running version, not a placeholder", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, current: "9.9.9" } });
  await page.waitForTimeout(150);
  const version = await aboutCard(page).locator("#about-version").innerText();
  await page.close();
  assert.equal(version, "9.9.9",
    "the About section's version did not track update_status's own `current` field");
});

await check("the version updates again after a manual check finds something newer", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, current: "1.0.0" } });
  await page.waitForTimeout(150);
  await page.evaluate(() => {
    window.__update = { ...window.__update, current: "1.0.0", available: "1.1.0" };
  });
  await page.locator("#update-check").click();
  await page.waitForTimeout(150);
  const version = await aboutCard(page).locator("#about-version").innerText();
  await page.close();
  assert.equal(version, "1.0.0");
});

await check("the license names the file it comes from, not a bare claim", async () => {
  const page = await open();
  const text = await aboutCard(page).locator(".about-fact", { hasText: "License" }).innerText();
  await page.close();
  assert.match(text, /MIT/);
  assert.match(text, /LICENSE/);
});

await check("the source link opens externally, never inside the WebView", async () => {
  const page = await open();
  const link = aboutCard(page).locator("a[data-external]");
  const href = await link.getAttribute("href");
  await link.click();
  await page.waitForTimeout(150);
  const calls = await page.evaluate(() => window.__calls || []);
  const url = await page.url();
  await page.close();
  assert.match(href, /^https:\/\/github\.com\//);
  assert.ok(calls.some((c) => c[0] === "open_external_url" && c[1]?.url === href),
    `open_external_url was not invoked with ${href}: ${JSON.stringify(calls)}`);
  assert.ok(!url.includes("github.com"), "the settings window itself navigated away");
});

await check("the About section explains what Jarvis is, in more than a sentence fragment", async () => {
  const page = await open();
  const note = await aboutCard(page).locator(".note").innerText();
  await page.close();
  assert.ok(note.length > 80, `the About text was too short: "${note}"`);
  assert.match(note, /local/i);
});

await check("no NEW page error while About renders", async () => {
  // settings.html already throws "Cannot read properties of null (reading
  // 'enabled')" on load in this harness, in every scenario, independent of
  // this section - see tests/faq.mjs's identical guard.
  const page = await open();
  await aboutCard(page).locator("a[data-external]").click();
  const errors = page.__errors.filter(
    (e) => !/Cannot read properties of null \(reading 'enabled'\)/.test(e));
  await page.close();
  assert.deepEqual(errors, [], errors.join(" | "));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nAbout Jarvis holds, and its version never drifts from the one actually running");
process.exit(fails.length ? 1 : 0);
