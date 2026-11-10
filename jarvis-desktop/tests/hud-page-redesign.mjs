/**
 * hud-page-redesign.mjs - the 2026-11-09 HUD page redesign, held to the page.
 *
 *     node tests/hud-page-redesign.mjs
 *
 * THE SPEC THIS PINS (Gemini's Q1-Q14 review, the HUD PAGE FILE slice):
 *
 *   §2.1  ONE authoritative navigation. Zone A is the centre-stage switcher:
 *         five plain-word tabs with icons - Talk, Memory Map, Waiting for You
 *         (N), Today & Reminders, Speed & GPUs - and it chooses only what the
 *         centre stage draws, through the page's own setView()/setTab().
 *         Zone B is the window header: AI Mode, Open Brain, Layout, Edit
 *         Layout, Settings - and the old BRAIN / PRESETS / GALAXY OPTIONS
 *         words are retired from the stage strip (their handlers stay, for the
 *         shell modules that bind to them).
 *   §2.2  ONE compact notification pill bar instead of stacked multi-line
 *         banners, and a count badge that stays readable while its tab is the
 *         open one.
 *   §4.1  The Memory tab's card hierarchy: a plain new fact gets
 *         [ Keep ] / [ Edit in Brain ] / [ Dismiss ]; a warned, replaced,
 *         retired or merged card gets a 1-line amber reason badge and
 *         [ Review in Brain ] / [ Dismiss ]. The KEEP ELIGIBILITY is still the
 *         page's own memoryDoorKeepable() and it is NOT re-tested by a copy.
 *   §4.2  When the full approval card is on screen, the right rail's duplicate
 *         "Cards waiting" card is marked data-duplicate-of-stage="true" and
 *         hidden - one card, one pair of buttons.
 *   §5.1  Plain words that live in the page.
 *   §5.2  Density: the schedule list and the rail column scroll instead of
 *         clipping their last row.
 *
 * The page half is driven in a real headless Chromium through tests/uikit.mjs
 * (the harness every neighbouring hud-*.mjs uses). Where a check needs data
 * the page would have fetched, this suite answers the request ITSELF with
 * page.route - never by inventing page state.
 *
 * Run: node tests/hud-page-redesign.mjs
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const ROOT = join(HERE, "..", "..");
const read = (file) => readFileSync(file, "utf8");
const readBytes = (file) => readFileSync(file);

const HUD = read(join(SRC, "jarvis_hud.html"));

let passed = 0;
const fails = [];
async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (error) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${error.message}`);
  }
}

/* ══════════════════════════════════════════════════════════════════════════
 * THE SOURCE HALF - the shapes a browser would have to be told to break.
 * ════════════════════════════════════════════════════════════════════════ */

/** The body of the LAST CSS rule for `selector` (`lastIndexOf`: the redesign
 *  rules are appended at the end of the page's one stylesheet, and a later
 *  rule is the one that really paints). */
function cssRule(selector) {
  let at = HUD.lastIndexOf("\n" + selector + "{");
  if (at < 0) at = HUD.indexOf(selector + "{");
  assert.ok(at >= 0, `the page has no ${selector} rule`);
  const open = HUD.indexOf("{", at);
  return HUD.slice(open + 1, HUD.indexOf("}", open));
}

/** The five Zone A tabs, as `{ key, words }`, in the order written. The page
 *  is HTML source, so its own entities are decoded here (`&amp;`). */
function stageNavTabs() {
  const at = HUD.indexOf('id="hud-stage-nav"');
  assert.ok(at >= 0, "the page has no #hud-stage-nav");
  const end = HUD.indexOf("</nav>", at);
  const block = HUD.slice(at, end);
  return [...block.matchAll(/<button\b[^>]*data-hud-nav="([a-z]+)"[^>]*>([\s\S]*?)<\/button>/g)]
    .map((m) => ({
      key: m[1],
      words: m[2].replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&")
        .replace(/\s+/g, " ").trim(),
      icon: /class="hud-nav-icon"/.test(m[2]) && /<svg\b/.test(m[2]),
    }));
}

await check("§2.1 Zone A: ONE centre-stage switcher, five plain-word tabs with icons", () => {
  const tabs = stageNavTabs();
  assert.deepEqual(tabs.map((t) => t.key),
    ["talk", "galaxy", "today", "reminders", "telemetry"],
    `the switcher is not the five stages, in order: ${JSON.stringify(tabs.map((t) => t.key))}`);
  const expected = ["Talk", "Memory Map", "Waiting for You", "Today & Reminders", "Speed & GPUs"];
  tabs.forEach((tab, index) => {
    assert.ok(tab.words.startsWith(expected[index]),
      `tab ${index + 1} reads "${tab.words}", not "${expected[index]}"`);
    assert.equal(tab.icon, true, `the "${tab.words}" tab has no icon`);
  });
  // The count is a real number and is never hidden while the tab is chosen:
  // it is its own element, painted from the queue, and the tab's own paint
  // does not touch its `hidden`.
  assert.match(HUD, /id="hud-nav-waiting-count"/);
  assert.match(HUD, /navCount\.hidden = n === 0;/,
    "the (N) badge is not driven by the queue count");
  assert.doesNotMatch(HUD, /navCount\.hidden = [^;]*(chosen|pressed|aria-pressed)/,
    "the (N) badge is hidden when its tab is the chosen one (the Fig 16 bug)");
  // Zone A is drawn in every shell that has a stage to switch, and hidden in
  // the two the spec keeps to the face and its return pill.
  const menu = cssRule("#stage-menu");
  assert.match(menu, /display:flex/, "the switcher's row is not drawn");
  assert.match(HUD,
    /html\[data-hud-shell="center-core"\] #stage-menu,\s*\n\s*html\[data-hud-shell="single-stage-bento"\] #stage-menu\{display:none;\}/,
    "Face Only / Mini View do not keep the row off their glass");
});

await check("§2.1 the old BRAIN / PRESETS / GALAXY OPTIONS words left the strip, handlers kept", () => {
  const rule = cssRule("#stage-words");
  assert.match(rule, /display:none !important;/,
    "the retired menu words are still drawn in the stage strip");
  // Their handlers stay reachable: the words themselves (the shell modules
  // bind to these ids) and the header's own doors.
  for (const id of ["stage-galaxy-options", "stage-presets", "stage-brain-window"]) {
    assert.ok(HUD.includes(`id="${id}"`), `the ${id} handler host was deleted, not retired`);
  }
  for (const id of ["hud-ai-mode-door", "hud-open-brain-door", "hud-settings-door"]) {
    assert.ok(HUD.includes(`id="${id}"`), `the header door ${id} is missing`);
  }
  // Zone B opens the ONE menu/gear the page already has: no second menu.
  assert.match(HUD, /jarvis:hud-presets-open/,
    "AI Mode does not open the page's one Presets menu");
  assert.match(HUD, /var gear = \$\("hud-settings"\);/,
    "the Settings door does not route to the shell's one Settings gear");
});

await check("§2.2 the pill bar is one line, and the memory pill is the same banner element", () => {
  const pill = cssRule(".hud-pill");
  assert.match(pill, /min-height:32px/, "the pill has no compact height");
  assert.match(pill, /white-space:nowrap/, "the pill is allowed to wrap into a paragraph again");
  assert.ok(HUD.includes('id="hud-pills"'), "there is no pill bar element");
  assert.ok(HUD.includes('id="hud-pill-approvals"'), "there is no approval pill");
  // The memory pill is the SAME #init-memory the banner was (one element, one
  // Dismiss, one count) - shrunk to one line and moved into the bar - so no
  // third surface could ever show a different number.
  assert.match(HUD, /const pills = document\.getElementById\("hud-pills"\);/,
    "the memory pill is not put in the pill bar");
  assert.match(HUD, /el\.classList\.add\("hud-pill"\)/,
    "the memory pill is not drawn as a pill");
  assert.doesNotMatch(HUD, /anything that looks slipped in/,
    "the two-sentence banner that truncated mid-word is still in the page");
  // #hud-safety stays exactly where it was: outside #shell, first, undimmed.
  const safety = HUD.indexOf('id="hud-safety"');
  const shell = HUD.indexOf('id="shell"');
  assert.ok(safety > 0 && safety < shell, "#hud-safety left its place above the shell");
  assert.match(HUD, /<div id="hud-safety" role="region" aria-label="Safety and connection" hidden>/,
    "the safety strip lost its own semantics");
});

await check("§4.2 the rail's Cards-waiting card is the duplicate that steps aside", () => {
  const rule = cssRule('#rail-waiting[data-duplicate-of-stage="true"]');
  assert.match(rule, /display:none !important;/,
    "the duplicate rail card is not hidden when the stage shows the card");
  assert.match(HUD, /box\.setAttribute\("data-duplicate-of-stage", shown \? "true" : "false"\)/,
    "the duplicate flag is not set from what is really on screen");
  assert.match(HUD, /var n = approvals \? approvals\.querySelectorAll\("\.appr"\)\.length : 0;/,
    "the flag does not read the page's own approval cards");
});

await check("§4.1 the Memory tab's three-button hierarchy, and Keep's one rule untouched", () => {
  // The plain new fact.
  assert.ok(HUD.includes('keep.textContent = "\\u2713 Keep"'),
    "the plain fact's first button is not [ Keep ]");
  assert.match(HUD, /"memory-door-review is-secondary"\s*\n\s*: "memory-door-review is-primary"/,
    "the Review button is not styled by whether the card is decidable here");
  assert.ok(HUD.includes('"Edit in Brain \\u2197"'),
    "the plain fact's second button is not [ Edit in Brain ]");
  assert.ok(HUD.includes('"Review in Brain \\u2197"'),
    "a warned card's first button is not [ Review in Brain ]");
  assert.match(HUD, /why\.className = "memory-door-why";/,
    "a warned card has no reason badge");
  assert.match(HUD, /memory-door-why\{[\s\S]{0,240}?white-space:nowrap/,
    "the reason badge is not one line");
  // Exactly ONE of each door per card - no second Review, no second Dismiss.
  const card = HUD.slice(HUD.indexOf("function memoryDoorCardEl(card)"),
    HUD.indexOf("/* The one navigation the list offers"));
  assert.equal((card.match(/createElement\("button"\)/g) || []).length, 3,
    "a memory card does not draw exactly three buttons");
  // The eligibility function and its one POST are UNTOUCHED.
  assert.match(HUD, /function memoryDoorKeepable\(row\)\{/);
  assert.match(HUD, /return memoryDoorKind\(row\) === "New fact";/);
  assert.match(HUD, /keep: memoryDoorKeepable\(row\),/);
  assert.match(HUD, /body: JSON\.stringify\(\{ id: id, accept: true \}\)/);
});

await check("§5.1/§5.2 the page's own plain words and the density rules", () => {
  assert.ok(HUD.includes(">Ask Jarvis a question to see speed stats<"),
    "the idle telemetry still shows a row of em dashes");
  assert.doesNotMatch(HUD, />No turns yet this session</,
    "the old developer-facing telemetry line is still there");
  for (const selector of ["#rail-reminders, #tab-reminders", "#rail-right"]) {
    const rule = cssRule(selector);
    assert.match(rule, /overflow-y:auto/, `${selector} cannot scroll`);
    assert.match(rule, /max-height:100%/, `${selector} is not capped to the column`);
    assert.match(rule, /padding-bottom:24px/, `${selector} has no room under its last row`);
  }
});

await check("the three copies of the HUD page stay byte-identical", () => {
  const files = [
    join(SRC, "jarvis_hud.html"),
    join(ROOT, "jarvis-backend", "jarvis_hud.html"),
    join(ROOT, "backend", "jarvis_hud.html"),
  ];
  const first = readBytes(files[0]);
  for (const file of files.slice(1)) {
    assert.ok(first.equals(readBytes(file)), `${file} is not byte-identical to the desktop page`);
  }
});

/* ══════════════════════════════════════════════════════════════════════════
 * THE PAGE HALF - the real page, in a real browser, with the two reads it
 * would have made answered here.
 * ════════════════════════════════════════════════════════════════════════ */

const PLAIN_APPROVAL = {
  id: "91", action: "send_email", tier: "ask", replaces: false, expires_in: 120,
};

const { base, close } = await K.serve();
const browser = await K.launch();

/** A HUD with one approval card waiting and two memory cards in the queue.
 *  `approvalCards` is mutable so one page can prove BOTH sides of §4.2. */
async function openHud() {
  const state = { cards: [PLAIN_APPROVAL] };
  const page = await K.open(browser, base, "jarvis_hud.html", {}, 
    { width: 1600, height: 1000 });
  await page.route("**/api/pending*", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ available: true, pending: state.cards, history: [] }),
  }));
  await page.route("**/api/memory/pending*", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({
      available: true, setup: { setup_complete: false, note: "" },
      pending: [
        { id: 41, text: "I like oat milk", source: "conversation",
          replaces: null, replaces_id: null, created: Date.now() / 1000 - 600 },
        { id: 42, text: "I moved to Porto", source: "conversation",
          replaces: "I live in Lisbon", replaces_id: 7,
          replaces_text: "I live in Lisbon", created: Date.now() / 1000 - 900 },
      ],
    }),
  }));
  await page.route("**/api/initiative*", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ available: true, items: [] }),
  }));
  // The reads above are answered from now on; the page's first poll already
  // ran against the harness's 404, so ask for one more beat.
  await page.evaluate(() => (typeof apprPoll === "function" ? apprPoll() : null));
  await page.evaluate(() => (typeof initPoll === "function" ? initPoll() : null));
  return { page, state };
}

/** What the real page drew, read once, in one place. */
const layout = (page) => page.evaluate(() => {
  const shown = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    return getComputedStyle(el).display !== "none" && rect.width > 1 && rect.height > 1;
  };
  const nav = document.getElementById("hud-stage-nav");
  return {
    shell: document.body.dataset.hudShell,
    navShown: shown(nav),
    navTabs: [...document.querySelectorAll("#hud-stage-nav [data-hud-nav]")].map((b) => ({
      key: b.dataset.hudNav,
      pressed: b.getAttribute("aria-pressed"),
      words: b.textContent.replace(/\s+/g, " ").trim(),
    })),
    stageWordsShown: shown(document.getElementById("stage-words")),
    aiModeShown: shown(document.getElementById("hud-ai-mode-door")),
    openBrainShown: shown(document.getElementById("hud-open-brain-door")),
    settingsDoorShown: shown(document.getElementById("hud-settings-door")),
    headerBarHas: ["hud-layout-badge", "hud-edit-toggle", "hud-ai-mode-door"]
      .filter((id) => {
        const el = document.getElementById(id);
        return Boolean(el && el.closest(".stage-bar"));
      }),
    approvals: document.querySelectorAll("#approvals .appr").length,
    pillShown: shown(document.getElementById("hud-pill-approvals")),
    pillWords: (document.getElementById("hud-pill-approvals") || {}).textContent || "",
    navCount: {
      shown: shown(document.getElementById("hud-nav-waiting-count")),
      words: (document.getElementById("hud-nav-waiting-count") || {}).textContent || "",
    },
    initiativeShown: shown(document.getElementById("initiative")),
    pillsShown: shown(document.getElementById("hud-pills")),
    memoryPill: (() => {
      const el = document.getElementById("init-memory");
      return { exists: Boolean(el), shown: shown(el), words: el ? el.innerText : "" };
    })(),
    dedupe: (() => {
      const box = document.getElementById("rail-waiting");
      return box ? { flag: box.getAttribute("data-duplicate-of-stage"),
                     shown: shown(box) } : null;
    })(),
  };
});

const ONE = await openHud();
const page = ONE.page;

await check("§2.1 the real page draws the 5-tab switcher, and Zone B is the header", async () => {
  await K.until(page, "the HUD to boot", async () =>
    (await page.evaluate(() => Boolean(document.getElementById("hud-stage-nav")))), { ms: 15000 });
  await page.waitForTimeout(400);
  const seen = await layout(page);
  assert.equal(seen.navShown, true, "the centre-stage switcher is not on screen");
  assert.deepEqual(seen.navTabs.map((t) => t.key),
    ["talk", "galaxy", "today", "reminders", "telemetry"]);
  assert.match(seen.navTabs[1].words, /Memory Map/);
  assert.match(seen.navTabs[4].words, /Speed & GPUs/);
  // The deprecated menu words are retired from the strip on the real screen.
  assert.equal(seen.stageWordsShown, false,
    "BRAIN / PRESETS / GALAXY OPTIONS are still drawn in the stage strip");
  // Zone B: the window-level actions live in the one header bar.
  assert.equal(seen.aiModeShown, true, "the header has no AI Mode door");
  assert.equal(seen.openBrainShown, true, "the header has no Open Brain door");
  assert.deepEqual(seen.headerBarHas, ["hud-layout-badge", "hud-edit-toggle", "hud-ai-mode-door"],
    `Layout / Edit Layout / AI Mode are not all in the header bar: ${JSON.stringify(seen.headerBarHas)}`);
  // No shell chrome is injected into this bare page, so the Settings door
  // (which routes to the shell's gear) stays out of sight rather than
  // offering a press that can do nothing.
  assert.equal(seen.settingsDoorShown, false,
    "the Settings door is drawn with no shell gear behind it");
});

await check("§2.1 a press chooses what the CENTRE STAGE draws", async () => {
  await page.click('#hud-stage-nav [data-hud-nav="galaxy"]');
  await page.waitForTimeout(250);
  const map = await page.evaluate(() => ({
    view: S.view, tab: document.body.dataset.hudTab,
    pressed: document.querySelector('#hud-stage-nav [data-hud-nav="galaxy"]')
      .getAttribute("aria-pressed"),
    brainOn: document.getElementById("brain").classList.contains("on"),
  }));
  assert.equal(map.view, "brain", "Memory Map did not open the Galaxy view");
  assert.equal(map.brainOn, true, "the Galaxy stage is not the one on screen");
  assert.equal(map.pressed, "true", "the Memory Map tab did not mark itself chosen");
  await page.click('#hud-stage-nav [data-hud-nav="reminders"]');
  await page.waitForTimeout(250);
  const rem = await page.evaluate(() => ({
    tab: document.body.dataset.hudTab,
    view: S.view,
    pressed: document.querySelector('#hud-stage-nav [data-hud-nav="reminders"]')
      .getAttribute("aria-pressed"),
    talkOn: document.getElementById("talk").classList.contains("on"),
  }));
  assert.equal(rem.tab, "reminders", "Today & Reminders did not choose its pane");
  assert.equal(rem.view, "talk", "Today & Reminders left the conversation");
  assert.equal(rem.talkOn, true, "the conversation is not the stage the tab left up");
  assert.equal(rem.pressed, "true", "the chosen tab is not marked");
  await page.click('#hud-stage-nav [data-hud-nav="talk"]');
  await page.waitForTimeout(200);
});

await check("§2.2/§4.2 the pill bar counts the real card, and the duplicate steps aside", async () => {
  await K.until(page, "the approval card", async () =>
    (await page.evaluate(() => document.querySelectorAll("#approvals .appr").length)) === 1,
    { ms: 15000 });
  await page.waitForTimeout(300);
  const withCard = await layout(page);
  assert.equal(withCard.approvals, 1, "the approval card is not drawn");
  assert.equal(withCard.pillShown, true, "no approval pill was drawn");
  assert.match(withCard.pillWords, /1 Approval Waiting/, `the pill says "${withCard.pillWords}"`);
  assert.match(withCard.pillWords, /Review/, "the pill offers no action word");
  assert.equal(withCard.navCount.shown, true, "the (N) badge is not shown for a waiting card");
  assert.equal(withCard.navCount.words.trim(), "1", "the (N) badge does not carry the real count");
  assert.equal(withCard.initiativeShown, true, "the pill bar has no container on screen");
  assert.equal(withCard.pillsShown, true, "the pill bar is not drawn");
  // §4.2: the full card is on screen, so the rail's copy is marked and hidden.
  assert.deepEqual(withCard.dedupe, { flag: "true", shown: false },
    `the duplicate Cards-waiting card is still drawn: ${JSON.stringify(withCard.dedupe)}`);
  // The full card itself is untouched: its decision words are the card's own.
  const cardWords = await page.evaluate(() =>
    (document.querySelector("#approvals .appr") || {}).innerText || "");
  assert.match(cardWords, /Approve/, "the approval card lost its Approve door");
  assert.match(cardWords, /Deny/, "the approval card lost its Deny door");
  // The badge stays readable while its own tab is the open one (Fig 16).
  await page.click('#hud-pill-approvals');
  await page.waitForTimeout(300);
  const open = await page.evaluate(() => ({
    tab: document.body.dataset.hudTab,
    count: (document.getElementById("hud-nav-waiting-count") || {}).hidden,
    pill: Boolean(document.getElementById("hud-pill-approvals")
      && !document.getElementById("hud-pill-approvals").hidden),
  }));
  assert.equal(open.tab, "today", "the approval pill did not open the Waiting-for-You tab");
  assert.equal(open.count, false, "the (N) badge hid when its tab opened");
  assert.equal(open.pill, true, "the pill vanished when its own tab opened");
});

await check("§4.2 the rail card comes back when the queue is empty", async () => {
  ONE.state.cards = [];
  await page.evaluate(() => (typeof apprPoll === "function" ? apprPoll() : null));
  await page.waitForTimeout(600);
  const empty = await layout(page);
  assert.equal(empty.approvals, 0, "the approval card was not cleared");
  assert.equal(empty.pillShown, false, "the approval pill stayed with nothing waiting");
  assert.deepEqual(empty.dedupe, { flag: "false", shown: true },
    `the rail card did not come back: ${JSON.stringify(empty.dedupe)}`);
});

await check("§2.2 the memory pill is one line, is in the bar, and opens the Memory tab", async () => {
  await K.until(page, "the memory pill", async () =>
    (await page.evaluate(() => Boolean(document.getElementById("init-memory")))), { ms: 15000 });
  const pill = await layout(page);
  assert.equal(pill.memoryPill.shown, true, "the memory pill is not on screen");
  assert.match(pill.memoryPill.words, /2 memory cards waiting/,
    `the pill's words are "${pill.memoryPill.words}"`);
  assert.match(pill.memoryPill.words, /Brain/,
    "the pill does not say where the queue lives");
  // ONE line: the card's height is a pill's, not a paragraph's.
  const height = await page.evaluate(() =>
    document.getElementById("init-memory").getBoundingClientRect().height);
  assert.ok(height > 20 && height <= 48,
    `the memory pill is ${Math.round(height)}px tall, not a one-line pill`);
  assert.equal(await page.evaluate(() =>
    document.getElementById("init-memory").closest("#hud-pills") !== null), true,
    "the memory pill is not in the pill bar");
  await page.click("#init-memory");
  await page.waitForTimeout(400);
  const went = await page.evaluate(() => ({
    tab: document.body.dataset.hudTab,
    door: !document.getElementById("memory-door").hidden,
  }));
  assert.equal(went.tab, "memory", "the memory pill did not switch to the Memory tab");
  assert.equal(went.door, true, "the Memory tab did not list the pending cards");
});

await check("§4.1 the Memory tab's cards carry the hierarchy, at runtime", async () => {
  await page.evaluate(() => {
    const door = window.__hudMemoryDoor;
    door.state.rows = [
      { id: 51, text: "I like oat milk", source: "conversation",
        replaces: null, replaces_id: null },
      { id: 52, text: "I moved to Porto", source: "conversation",
        replaces: "I live in Lisbon", replaces_id: 7,
        replaces_text: "I live in Lisbon" },
      { id: 53, text: "I drive a diesel", source: "feedback_retire",
        replaces_text: "I drive a diesel" },
    ];
    door.paint();
  });
  await page.waitForTimeout(250);
  const cards = await page.evaluate(() => [...document.querySelectorAll("#memory-door .memory-door-card")]
    .map((card) => ({
      kind: card.querySelector(".memory-door-kind").textContent,
      why: card.querySelector(".memory-door-why")
        ? card.querySelector(".memory-door-why").textContent : "",
      buttons: [...card.querySelectorAll(".memory-door-btns button")].map((b) => ({
        text: b.textContent.trim(),
        cls: b.className,
      })),
    })));
  assert.equal(cards.length, 3, `the door drew ${cards.length} cards`);
  const plain = cards[0];
  assert.equal(plain.kind, "New fact");
  assert.equal(plain.why, "", "a plain fact grew a warning badge");
  assert.deepEqual(plain.buttons.map((b) => b.text),
    ["\u2713 Keep", "Edit in Brain \u2197", "Dismiss"],
    `the plain fact's buttons are ${JSON.stringify(plain.buttons.map((b) => b.text))}`);
  assert.match(plain.buttons[0].cls, /memory-door-keep/);
  assert.match(plain.buttons[1].cls, /is-secondary/, "Edit in Brain is not the secondary button");
  assert.match(plain.buttons[2].cls, /memory-door-dismiss/, "Dismiss is not the quiet door");
  for (const warned of [cards[1], cards[2]]) {
    assert.ok(warned.why.length > 0, `a ${warned.kind} card has no reason badge`);
    assert.deepEqual(warned.buttons.map((b) => b.text),
      ["Review in Brain \u2197", "Dismiss"],
      `a ${warned.kind} card's buttons are ${JSON.stringify(warned.buttons.map((b) => b.text))}`);
    assert.match(warned.buttons[0].cls, /is-primary/,
      `a ${warned.kind} card's Review is not the primary door`);
  }
  assert.match(cards[1].why, /Updates an existing fact/,
    `a replacement card's badge says "${cards[1].why}"`);
  assert.match(cards[2].why, /forget an existing fact/,
    `a retire card's badge says "${cards[2].why}"`);
  // The count badge stays visible while this tab is the open one.
  const count = await page.evaluate(() => {
    const el = document.getElementById("memory-door-count");
    return { hidden: el.hidden, words: el.textContent };
  });
  assert.equal(count.hidden, false, "the Memory tab's count badge hid when the tab opened");
  assert.match(count.words, /3 cards waiting for you/);
});

await check("§1.2 Q5: the return pill is markup + CSS + one handler, and only Face Only / Mini View may show it", async () => {
  // THE MARKUP: one real <button>, outside #shell (so no layout/card/drag can
  // move it), declared with the words and the glyph the design asks for.
  const pillAt = HUD.indexOf('id="hud-return-pill"');
  assert.ok(pillAt > -1, "the page has no #hud-return-pill");
  const pill = HUD.slice(HUD.lastIndexOf("<button", pillAt), HUD.indexOf("</button>", pillAt));
  assert.match(pill, /type="button"/, "the return pill is not a real button");
  assert.match(pill, /\shidden(\s|>)/,
    "the pill is not hidden by default - a browser with no layout would draw it");
  assert.match(pill, /class="hud-return-pill"/, "the pill does not wear hud-layout.js's class");
  assert.match(pill, /Back to Command Center/, "the pill's words are not the design's");
  assert.match(pill, /&#10530;/, "the pill lost its \u2922 glyph");
  assert.ok(pillAt > HUD.indexOf('class="stage-bar"') && pillAt < HUD.indexOf('id="hud-stop"'),
    "the pill is not in the window header bar (it must sit at the bar's right end, " +
    "outside every card/region, and never as a fixed overlay over [Edit HUD])");
  // THE SECOND GATE: only the two face-only shells can ever draw it.
  assert.match(HUD,
    /html\[data-hud-shell="center-core"\] #hud-return-pill:not\(\[hidden\]\),\s*\n\s*html\[data-hud-shell="single-stage-bento"\] #hud-return-pill:not\(\[hidden\]\)\{display:inline-flex;\}/,
    "the pill is not gated to Face Only (center-core) and Mini View (single-stage-bento)");
  // THE ONE HANDLER AND THE ONE WRITE: returnPillFor decides, choosePreset
  // saves - the same write the Presets menu uses. No second layout key.
  assert.match(HUD, /import \{ RETURN_PILL, RETURN_PILL_LAYOUTS, returnPillFor, PRESET_ATTR \} from "\.\/hud-layout\.js";/,
    "the page does not import the pill's one declaration");
  assert.match(HUD, /import \{ choosePreset \} from "\.\/hud-layout-store\.js";/,
    "the page does not import the one layout write");
  assert.match(HUD, /RETURN_PILL_LAYOUTS\.indexOf\(base\) >= 0 \? RETURN_PILL : null/,
    "a saved copy of Face Only would lose its way back (base_preset is not honoured)");
  assert.match(HUD, /choosePreset\(target, layoutDoc\(\)\)/,
    "the pill does not save through the page's one layout write");
  assert.match(HUD, /new CustomEvent\("jarvis:hud-shell"/,
    "the pill does not hand the new shell to the page's own applyShell()");
});

await check("§1.2 Q6: the five-tab stage header is the ONE navigation, and #stage-tabs is retired", async () => {
  // ONE navigation: the legacy strip is gone (the five plain-word tabs of
  // §2.1 Zone A are the only stage header, in every shell that has one).
  assert.equal(HUD.includes('id="stage-tabs"'), false,
    "#stage-tabs is back - the retired Galaxy/Approvals/Reminders/Memory/Telemetry " +
    "strip is a second navigation");
  assert.equal(HUD.includes('aria-label="Inspector stage"'), false,
    "the old Inspector stage tablist is still declared somewhere");
  // The left rail is NOT a wall of unlabelled symbols: the Studio dock's six
  // shortcuts draw icon + plain words (spec §2.1), and the five stage tabs
  // carry the design's own words.
  const dockAt = HUD.indexOf('id="studio-dock"');
  const dock = HUD.slice(dockAt, HUD.indexOf("</nav>", dockAt));
  const labelled = [...dock.matchAll(/<span class="dock-label">([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(labelled,
    ["Memory Map", "Waiting for You", "Today &amp; Reminders", "Memory", "Speed &amp; GPUs"],
    `the dock's plain-words labels are ${JSON.stringify(labelled)}`);
  for (const plain of ["Talk", "Memory Map", "Waiting for You", "Today &amp; Reminders", "Speed &amp; GPUs"]) {
    assert.ok(HUD.includes(">" + plain) || HUD.includes(plain),
      `the stage header does not say "${plain}"`);
  }
  // The active layout's id is WRITTEN (hud-layout.js's PRESET_ATTR) - the
  // documented left-under. The two-column cockpit rule set that would consume
  // it is designed and deferred (see the page's own note): the HUD's default
  // layout is cockpit, so hiding the left column changes the default
  // navigation for suites that click the rail's presets.
  assert.match(HUD, /setAttribute\(PRESET_ATTR, id\)/,
    "nothing writes the active layout id");
  assert.equal(HUD.includes('html[data-hud-preset="cockpit"] body:not([data-hud-edit="on"]) #shell{'),
    false, "a half-landed two-column cockpit rule is in the page without its test adaptation");
});
await check("the safety strip is untouched", async () => {
  const safety = await page.evaluate(() => ({
    html: document.getElementById("hud-safety").outerHTML,
    text: document.getElementById("hud-safety").textContent,
    hidden: document.getElementById("hud-safety").hidden,
  }));
  assert.match(safety.text, /Always visible/,
    "the non-hideable safety strip lost its own sentence");
  assert.equal(safety.hidden, true,
    "the safety strip is drawn with no latch on (it only shows what is active)");
});

/* ── §1.2 Q5/Q6: the return pill and the two-column cockpit, on the page ── */

/** Put the page in one layout the way the shell bootstrap does: the event it
 *  sends carries the shell facts AND the base preset (the return pill and the
 *  PRESET_ATTR writer both read that one event). */
async function shellFacts(facts) {
  await page.evaluate((detail) => window.dispatchEvent(
    new CustomEvent("jarvis:hud-shell", { detail })), facts);
  await page.waitForTimeout(250);
}

const pillState = () => page.evaluate(() => {
  const el = document.getElementById("hud-return-pill");
  const bar = el.closest(".stage-bar");
  const box = el.getBoundingClientRect();
  const barBox = bar ? bar.getBoundingClientRect() : null;
  const style = getComputedStyle(el);
  return {
    hidden: el.hidden,
    shown: !el.hidden && style.display !== "none" && box.width > 1 && box.height > 1,
    words: el.textContent.replace(/\s+/g, " ").trim(),
    right: Math.round(box.right), barRight: barBox ? Math.round(barBox.right) : 0,
    top: Math.round(box.top), barTop: barBox ? Math.round(barBox.top) : 0,
    barBottom: barBox ? Math.round(barBox.bottom) : 0,
    preset: document.documentElement.getAttribute("data-hud-preset") || "",
  };
});

await check("Q5: the pill is drawn in Face Only and Mini View, and nowhere else", async () => {
  // The layout write needs the page's browser/desktop store; in this harness
  // the browser-web store is the honest one (no Tauri IPC here).
  await page.evaluate(() => { window.__JARVIS_WEB_MODE = true; });
  for (const [preset, shell] of [["ambient", "center-core"], ["minimal", "single-stage-bento"]]) {
    await shellFacts({ shell_template: shell, density: "comfortable",
      default_stage_tab: "talk", base_preset: preset });
    const state = await pillState();
    assert.equal(state.hidden, false, `${preset}: the way back is hidden`);
    assert.equal(state.shown, true,
      `${preset}: the pill is in the DOM but not on the glass`);
    assert.match(state.words, /Back to Command Center/, `${preset}: the pill's words changed`);
    // At the RIGHT END of the window header bar, which is the top-right
    // corner in both shells - and inside the bar, so it can never cover
    // [Edit HUD] (a fixed overlay here did, caught 2026-11-10).
    assert.ok(state.right <= state.barRight + 1 && state.right >= state.barRight - 20,
      `${preset}: the pill is not at the right end of the header bar ` +
      `(pill right ${state.right}, bar right ${state.barRight})`);
    assert.ok(state.top >= state.barTop && state.top <= state.barBottom,
      `${preset}: the pill is outside the header bar's own box (top ${state.top}, ` +
      `bar ${state.barTop}..${state.barBottom})`);
  }
  // A SAVED copy of Mini View keeps its way back: `base_preset` is what counts.
  await shellFacts({ shell_template: "single-stage-bento", density: "compact",
    default_stage_tab: "talk", base_preset: "minimal", name: "My mini" });
  assert.equal((await pillState()).shown, true,
    "the owner's saved copy of Mini View has no way back");
  // Every ordinary layout hides it.
  for (const [preset, shell] of [["second_brain", "three-column"], ["studio", "split-stage"],
    ["cockpit", "three-column"]]) {
    await shellFacts({ shell_template: shell, density: "comfortable",
      default_stage_tab: "talk", base_preset: preset });
    assert.equal((await pillState()).shown, false,
      `${preset}: the return pill is drawn outside Face Only / Mini View`);
  }
});

await check("Q5: one click on the pill lands in Command Center, through the page's one layout write", async () => {
  await page.evaluate(() => {
    window.__jarvisHudLayout = null;
    window.__hudLayoutWrites.length = 0;
  });
  await shellFacts({ shell_template: "center-core", density: "spacious",
    default_stage_tab: "talk", base_preset: "ambient" });
  assert.equal((await pillState()).shown, true, "Face Only has no way back to click");
  await page.click("#hud-return-pill");
  await page.waitForTimeout(500);
  const after = await page.evaluate(() => ({
    shell: document.body.dataset.hudShell,
    htmlShell: document.documentElement.getAttribute("data-hud-shell"),
    preset: document.documentElement.getAttribute("data-hud-preset"),
    pillHidden: document.getElementById("hud-return-pill").hidden,
    writes: window.__hudLayoutWrites.map((doc) => doc && doc.base_preset),
  }));
  assert.equal(after.shell, "three-column", "the click did not return to the three-column shell");
  assert.equal(after.htmlShell, "three-column", "the html shell and the body shell disagree");
  assert.equal(after.preset, "second_brain", "the page is not in Command Center after the click");
  // The ONE write: set_hud_layout, once, with Command Center - not a second
  // store, not a private key.
  assert.deepEqual(after.writes, ["second_brain"],
    `the click wrote ${JSON.stringify(after.writes)} through set_hud_layout`);
  assert.equal(after.pillHidden, true, "the pill stayed on screen after returning");
});

await page.close();
await close();
await browser.close().catch(() => {});

/* ══════════════════════════════════════════════════════════════════════════ */

if (fails.length) {
  console.log(`\n${fails.length} failed:`);
  for (const name of fails) console.log(`  - ${name}`);
  process.exit(1);
}
console.log(`\n${passed} passed, 0 failed`);
