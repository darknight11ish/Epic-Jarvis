/**
 * The tab strips on the two settings cards that hold a key apiece - "Chatbot
 * API keys" and the web-search services (Exa, Tavily, Brave, DeepSeek). The owner's
 * request of 2026-10-11: "a tab for chatgpt, a tab for deepseek, etc ... opening
 * the tabs gives their specific menu".
 *
 * WHAT THIS HOLDS, and how:
 *
 * - the strip's BEHAVIOUR is driven in a real browser, on the real Settings
 *   page, through `window.JarvisSettingsTabs` - the same code both cards call:
 *   one button per service, exactly one panel visible and it is the selected
 *   one, Tab reaches every tab button, Left/Right and Home/End move the
 *   selection;
 * - the FAILURE claim, which is the one a tab strip can most easily break:
 *   panels are hidden, never removed, and a control that cannot reach the PC
 *   still says so with its panel CLOSED. A card-level status line lives outside
 *   the strip and stays readable; a message inside a closed panel stays in the
 *   document (so nothing that speaks is deleted), and the panel is opened when
 *   its control is used, so the words are on screen when the failure happens;
 * - the WIRING (that both cards really build a strip, with the app's own names,
 *   and that each falls back to the plain column when the helper is absent) is
 *   asserted against the two source files, the way this repo's browser-free
 *   halves already do. A test that only drove the helper could pass while
 *   neither card used it.
 *
 * Runs where Playwright is installed (`npm install --no-save playwright &&
 * npx playwright install chromium`); it is not needed by anything else here.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const { base, close } = await K.serve();
const browser = await K.launch();
const page = await K.open(browser, base, "settings.html", {}, { width: 900, height: 1400 });
await page.waitForTimeout(400);

/* ── The strip's behaviour, driven for real ──────────────────────────────── */

/** Build a strip in the live page and hand back what it looks like. */
const build = (label, names) => page.evaluate(({ label, names }) => {
  const host = document.createElement("div");
  host.id = "tt-host";
  const old = document.getElementById("tt-host");
  if (old) old.remove();
  document.body.append(host);
  const made = window.JarvisSettingsTabs.build({
    mount: host,
    items: names,
    idOf: (n) => `tt-${n}`,
    labelOf: (n) => n,
    panelOf: (n) => {
      const box = document.createElement("div");
      box.className = "sc-switch";
      // A control and its own line of words, exactly like a real row.
      const line = document.createElement("p");
      line.className = "sc-line";
      line.textContent = `${n} status`;
      box.append(line);
      return [box];
    },
    label,
  });
  const tabs = [...host.querySelectorAll('[role="tab"]')];
  return {
    made: Boolean(made),
    count: tabs.length,
    names: tabs.map((t) => t.textContent.trim()),
    selected: tabs.map((t) => t.getAttribute("aria-selected")),
    tabIndex: tabs.map((t) => t.tabIndex),
    visiblePanels: [...host.querySelectorAll('[role="tabpanel"]')].filter((p) => !p.hidden).length,
    panels: [...host.querySelectorAll('[role="tabpanel"]')].length,
    visibleNames: [...host.querySelectorAll('[role="tabpanel"]')]
      .filter((p) => !p.hidden).map((p) => p.textContent.trim()),
  };
}, { label, names });

await check("the helper is on the real Settings page", async () => {
  const present = await page.evaluate(() => Boolean(window.JarvisSettingsTabs
    && typeof window.JarvisSettingsTabs.build === "function"));
  assert.equal(present, true, "settings.html did not load src/settings-tabs.js");
});

await check("six services make six tabs, named with the app's own words", async () => {
  const six = ["ChatGPT", "DeepSeek", "Mistral", "Grok", "OpenRouter", "Groq"];
  const got = await build("Chatbot API keys", six);
  assert.equal(got.count, 6, `expected six tabs, saw ${got.count}: ${got.names}`);
  assert.deepEqual(got.names, six);
  assert.equal(got.panels, 6);
});

await check("...and three keyed search services make three", async () => {
  const three = ["Exa", "Tavily", "Brave"];
  const got = await build("Web search keys", three);
  assert.equal(got.count, 3, `expected three tabs, saw ${got.count}`);
  assert.deepEqual(got.names, three);
});

await check("exactly one panel is visible, and it is the selected one", async () => {
  const got = await build("Web search keys", ["Exa", "Tavily", "Brave"]);
  assert.equal(got.visiblePanels, 1, `${got.visiblePanels} panels visible`);
  assert.deepEqual(got.selected, ["true", "false", "false"]);
  assert.match(got.visibleNames[0] || "", /Exa status/, `visible panel was ${got.visibleNames}`);
});

await check("Tab reaches EVERY tab button (one of them, and only it, is in the tab order)", async () => {
  const got = await build("Web search keys", ["Exa", "Tavily", "Brave"]);
  // A roving tabindex: exactly one tab is reachable by Tab, the arrows move
  // inside. Tab must not skip the strip, and must not walk all three.
  assert.equal(got.tabIndex.filter((i) => i === 0).length, 1,
    `tabindex values were ${got.tabIndex}`);
  await page.focus("#tt-host [role=tab]");
  const focused = await page.evaluate(() => document.activeElement
    && document.activeElement.getAttribute("role"));
  assert.equal(focused, "tab", "Tab did not land on the strip's tab button");
});

await check("Left/Right and Home/End move the selection", async () => {
  await build("Web search keys", ["Exa", "Tavily", "Brave"]);
  await page.focus("#tt-host [role=tab]");
  const sel = () => page.evaluate(() => {
    const tabs = [...document.querySelectorAll("#tt-host [role=tab]")];
    return { at: tabs.findIndex((t) => t.getAttribute("aria-selected") === "true"),
             focused: tabs.findIndex((t) => t === document.activeElement) };
  });
  await page.keyboard.press("ArrowRight");
  assert.deepEqual(await sel(), { at: 1, focused: 1 }, "ArrowRight did not move to the second tab");
  await page.keyboard.press("End");
  assert.deepEqual(await sel(), { at: 2, focused: 2 }, "End did not jump to the last tab");
  await page.keyboard.press("ArrowRight");
  assert.deepEqual(await sel(), { at: 0, focused: 0 }, "ArrowRight on the last tab did not wrap");
  await page.keyboard.press("ArrowLeft");
  assert.deepEqual(await sel(), { at: 2, focused: 2 }, "ArrowLeft on the first tab did not wrap");
  await page.keyboard.press("Home");
  assert.deepEqual(await sel(), { at: 0, focused: 0 }, "Home did not jump to the first tab");
});

await check("a panel is HIDDEN, never removed", async () => {
  const gone = await page.evaluate(() => {
    const tabs = [...document.querySelectorAll("#tt-host [role=tab]")];
    tabs[1].click();
    const panels = [...document.querySelectorAll("#tt-host [role=tabpanel]")];
    const hidden = panels.filter((p) => p.hidden);
    return {
      count: panels.length,
      hidden: hidden.length,
      // The closed panel's contents are still in the document - nothing that
      // has to speak was thrown away.
      text: hidden.map((p) => p.textContent.trim()),
    };
  });
  assert.equal(gone.count, 3, "a panel was removed rather than hidden");
  assert.equal(gone.hidden, 2);
  assert.ok(gone.text.some((t) => /Exa status/.test(t)),
    `the closed panel lost its words: ${JSON.stringify(gone.text)}`);
});

await check("THE ONE THAT MATTERS: a failure in a CLOSED panel is still spoken", async () => {
  // A real Settings card puts the failure in the panel's own status line AND
  // reports at card level (outside the strip). Reproduce both: a failing
  // control inside the closed panel, and the card's own status line.
  const seen = await page.evaluate(() => {
    const host = document.getElementById("tt-host");
    host.replaceChildren();
    const card = document.createElement("div");
    const outside = document.createElement("p");
    outside.className = "sc-line";
    outside.id = "tt-card-status";
    const mount = document.createElement("div");
    card.append(outside, mount);
    host.append(card);
    window.JarvisSettingsTabs.build({
      mount,
      items: ["Exa", "Tavily"],
      idOf: (n) => `tt-${n}`,
      labelOf: (n) => n,
      panelOf: (n) => {
        const box = document.createElement("div");
        const line = document.createElement("p");
        line.className = "sc-line";
        line.id = `tt-line-${n}`;
        line.textContent = `${n}: nothing saved yet`;
        box.append(line);
        return [box];
      },
      label: "Web search keys",
    });
    // The owner presses Save on the SECOND service, whose panel is closed: the
    // strip opens it first (a control can only be used from its own panel).
    document.querySelectorAll("#tt-host [role=tab]")[1].click();
    const line = document.getElementById("tt-line-Tavily");
    line.textContent = "Tavily: the PC refused the key";
    outside.textContent = "The PC refused the key.";
    return {
      panelOpen: !document.getElementById("panel-tt-Tavily").hidden,
      insideText: line.textContent,
      // Readable on screen: the element is in a panel that is NOT hidden.
      insideVisible: !line.closest("[role=tabpanel]").hidden,
      outside: outside.textContent,
      outsideVisible: outside.offsetParent !== null,
      selected: document.querySelectorAll('#tt-host [role="tab"][aria-selected="true"]')[0]
        .textContent.trim(),
    };
  });
  assert.equal(seen.selected, "Tavily", "the failing service's own tab was not opened");
  assert.equal(seen.panelOpen, true, "the panel holding the failure stayed closed");
  assert.equal(seen.insideVisible, true, "the failure's words are not on screen");
  assert.match(seen.insideText, /refused the key/);
  assert.equal(seen.outsideVisible, true, "the card-level status went away");
  assert.match(seen.outside, /refused the key/);
});

/* ── The wiring, asserted against the two cards (browser-free half) ──────── */

const chatbot = read("src/chatbot-api-keys-settings.js");
const search = read("src/web-search-settings.js");
const html = read("src/settings.html");

await check("both cards really build a strip, with the app's own names", async () => {
  assert.match(chatbot, /JarvisSettingsTabs\.build\(/, "the chatbot card builds no strip");
  assert.match(chatbot, /labelOf:\s*\(entry\)\s*=>\s*LABEL\[entry\.service\]/,
    "the chatbot card does not use the app's own service names");
  assert.match(search, /JarvisSettingsTabs\.build\(/, "the web-search card builds no strip");
  assert.match(search, /labelOf:\s*\(p\)\s*=>\s*p\.label/,
    "the web-search card does not use the app's own service names");
});

await check("each card falls back to the plain column when the helper is missing", async () => {
  assert.match(chatbot, /if \(!tabs\) as\.body\.replaceChildren\(\.\.\.entries\.map\(row\)\)/,
    "the chatbot card has no fallback - a missing strip would cost a setting");
  assert.match(search, /if \(!tabs\) ws\.keys\.replaceChildren\(\.\.\.boxes\)/,
    "the web-search card has no fallback");
});

await check("the helper is a plain script, loaded before the module scripts", async () => {
  const helper = html.indexOf('<script src="settings-tabs.js"></script>');
  const firstModule = html.indexOf('<script type="module"');
  assert.ok(helper > -1, "settings.html does not load src/settings-tabs.js");
  assert.ok(helper < firstModule,
    "the helper is loaded after the modules, so the cards would not find it");
});

await check("no panel that has to speak was made unreachable by the strip", async () => {
  // The rows inside both cards are built by JavaScript; the static rows of the
  // page (which the catalogue holds in order) are untouched, and no static
  // toggle row moved. This is the check that the tabs did not hide a catalogue
  // row behind a tab.
  assert.match(chatbot, /panelOf:\s*\(entry\)\s*=>\s*\[row\(entry\)\]/,
    "the chatbot rows are no longer inside their panels");
  assert.match(search, /panelOf:\s*\(p\)\s*=>\s*\[boxes\[keyed\.indexOf\(p\)\]\]/,
    "the web-search key rows are no longer inside their panels");
});

await browser.close();
if (close) await close();

console.log(`\n${fails.length} failed`);
process.exit(fails.length ? 1 : 0);
