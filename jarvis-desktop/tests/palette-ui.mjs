/**
 * palette-ui.mjs - the command palette worked from the keyboard alone, in the
 * real Jarvis bar.
 *
 *     node tests/palette-ui.mjs
 *
 * tests/a11y.mjs is the project's own accessibility suite and this file sits
 * beside it on purpose: the palette is a new surface, and the three things
 * that have gone wrong on surfaces like it are all checked here against the
 * real page rather than against the source text.
 *
 *   * THE FOCUS TRAP. A dialog that leaks the keyboard lets a Tab land on the
 *     Approve button behind it - the widget had the same bug (bug audit).
 *   * THE LIVE REGION. A count written while its region is `hidden` announces
 *     nothing at all: tests/a11y.mjs's own opening check. The palette's own
 *     flag for this is that the region is inside the panel, which is
 *     un-hidden BEFORE anything is written into it.
 *   * THE GATE. With an approval waiting, the card is the surface that
 *     matters; the palette must refuse to open rather than cover it.
 *
 * tests/palette.mjs (no browser) owns the list: that every row comes from the
 * generated catalogue and opens something real.
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

const openBar = (data = {}) =>
  K.open(browser, base, "index.html", { pending: [], attention: K.ATTENTION_CLEAR, ...data },
    { width: 750, height: 800 });

/** Everything the palette is, from the DOM: its state, its rows and the
 *  region a screen reader hears. */
const paletteState = (page) => page.evaluate(() => {
  const panel = document.getElementById("palette");
  const rows = [...document.querySelectorAll("#palette-list .palette-row")];
  return {
    hidden: panel.hidden,
    open: document.documentElement.dataset.palette === "open",
    role: panel.getAttribute("role"),
    modal: panel.getAttribute("aria-modal"),
    labelledby: panel.getAttribute("aria-labelledby"),
    labelled: (document.getElementById(panel.getAttribute("aria-labelledby")) || {}).textContent,
    focus: document.activeElement.id,
    selected: rows.findIndex((r) => r.getAttribute("aria-selected") === "true"),
    rowCount: rows.length,
    titles: rows.map((r) => r.querySelector(".palette-row-title").textContent),
    firstTitle: rows[0] ? rows[0].querySelector(".palette-row-title").textContent : null,
    firstId: rows[0] ? rows[0].dataset.id : null,
    status: document.getElementById("palette-status").textContent,
    live: document.getElementById("palette-status").getAttribute("aria-live"),
    emptyHidden: document.getElementById("palette-empty").hidden,
    emptyTitle: document.getElementById("palette-empty-title").textContent,
    emptyBody: document.getElementById("palette-empty-body").textContent,
  };
});

/** What the region is written with, in order - the same observer tests/a11y.mjs
 *  uses, so "it announced" is a fact about the DOM and not about the code. */
const WATCH = () => {
  const seen = [];
  for (const r of document.querySelectorAll("[aria-live]")) {
    new MutationObserver(() => {
      const t = r.textContent.trim();
      if (t) seen.push({ live: r.getAttribute("aria-live"), text: t,
        hidden: Boolean(r.closest("[hidden]")) });
    }).observe(r, { childList: true, characterData: true, subtree: true });
  }
  window.__spoken = seen;
};

/* ── Opening ─────────────────────────────────────────────────────────────── */

await check("an empty box opens the palette on / and shows the catalogue", async () => {
  const page = await openBar();
  const before = await paletteState(page);
  assert.equal(before.hidden, true, "the palette is on screen before anything asked for it");

  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(200);
  const after = await paletteState(page);
  // The "/" must not also land in the box behind the palette.
  const typed = await page.evaluate(() => document.getElementById("prompt").value);
  await page.close();

  assert.equal(after.hidden, false, "/ did nothing");
  assert.equal(after.open, true, "the shell does not know the palette is open");
  assert.equal(after.role, "dialog", "the palette is not a dialog");
  assert.equal(after.modal, "true", "a modal dialog without aria-modal teaches the wrong model");
  assert.ok(after.labelledby && after.labelled, "the dialog has no accessible name");
  assert.equal(after.focus, "palette-search", "the keyboard was not put in the search field");
  assert.ok(after.rowCount > 50, `only ${after.rowCount} rows were listed`);
  assert.ok(after.selected === 0, "no row is marked as the one Enter would open");
  assert.equal(typed, "", "the / that opened the palette also landed in the box behind it");
});

await check("the live region says how many things there are to find", async () => {
  const page = await openBar();
  await page.evaluate(WATCH);
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(300);
  const spoken = await page.evaluate(() => window.__spoken);
  await page.close();
  const hit = spoken.find((s) => /things Jarvis can do|find anything/i.test(s.text));
  assert.ok(hit, `opening was silent. saw: ${JSON.stringify(spoken)}`);
  assert.equal(hit.live, "polite", "a finder should not interrupt");
  assert.equal(hit.hidden, false,
    "the count was written into a hidden region, which announces nothing");
});

await check("typing filters the list, and the count changes with it", async () => {
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  const all = await paletteState(page);

  await page.keyboard.type("backup");
  await page.waitForTimeout(250);
  const typed = await paletteState(page);
  await page.close();

  assert.ok(typed.rowCount > 0, `"backup" matched nothing (${typed.rowCount} rows)`);
  assert.ok(typed.rowCount < all.rowCount, "the list did not narrow");
  assert.match(typed.titles.join(" | "), /Backup/i, "Backups is not in the results");
  assert.match(typed.status, new RegExp(String(typed.rowCount)), "the count line is not the count");
});

await check("the search reads the catalogue, not a copy of the words", async () => {
  // If the palette carried its own list of names (the drift this whole change
  // is written against), a title it invented would show up here and a real
  // catalogue title would not. tests/palette.mjs checks the source; this
  // checks what actually reached the screen.
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.type("what jarvis can reach");
  await page.waitForTimeout(250);
  const state = await paletteState(page);
  await page.close();
  assert.equal(state.firstTitle, "What Jarvis can reach",
    `the first result is "${state.firstTitle}"`);
  assert.equal(state.firstId, "settings.reach", "the row is not the catalogue's own id");
});

/* ── Moving ──────────────────────────────────────────────────────────────── */

await check("the arrows move the tick, and it wraps at both ends", async () => {
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  const start = await page.evaluate(() => document.activeElement.id);

  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(120);
  const down = await paletteState(page);
  await page.keyboard.press("ArrowUp");
  await page.waitForTimeout(120);
  const back = await paletteState(page);
  // Up from the first row is the last row, not a stuck cursor.
  await page.keyboard.press("ArrowUp");
  await page.waitForTimeout(120);
  const wrapped = await paletteState(page);
  // End and Home are the two ends of the same list.
  await page.keyboard.press("Home");
  await page.waitForTimeout(120);
  const home = await paletteState(page);
  // The focus STAYS in the field: the rows are named by aria-activedescendant,
  // which is how a listbox is meant to be driven, so typing never stops.
  const active = await page.evaluate(() => document.activeElement.id);
  await page.close();

  assert.equal(start, "palette-search", "typing lost the search field");
  assert.equal(back.selected, 0, "ArrowUp did not come back to the first row");
  assert.equal(down.selected, 1, `ArrowDown selected row ${down.selected}`);
  assert.equal(wrapped.selected, wrapped.rowCount - 1,
    "ArrowUp from the first row did not wrap to the last");
  assert.equal(home.selected, 0, "Home did not come back to the first row");
  assert.equal(active, "palette-search", "the arrows moved the DOM focus out of the field");
});

await check("a row the catalogue hides is listed, and says so", async () => {
  const page = await openBar({
    storage: { "jarvis.menus.hidden": JSON.stringify(["settings.faq"]) },
  });
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.type("faq");
  await page.waitForTimeout(250);
  const state = await paletteState(page);
  const badge = await page.evaluate(() =>
    document.querySelector("#palette-list .palette-row-hidden")?.textContent);
  await page.close();
  assert.equal(state.firstId, "settings.faq", "a hidden menu cannot be searched for");
  assert.equal(badge, "hidden", "the row does not say it is hidden on this computer");
});

/* ── Opening a row ───────────────────────────────────────────────────────── */

await check("Enter on a Settings row asks Rust to open Settings there", async () => {
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.type("web search");
  await page.waitForTimeout(250);
  const first = await paletteState(page);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  const out = await page.evaluate(() => ({
    calls: window.__calls.filter((c) => c[0] === "open_fix_place").map((c) => c[1] && c[1].place),
    place: JSON.parse(localStorage.getItem("jarvis.settings.place") || "null"),
    hidden: document.getElementById("palette").hidden,
    focus: document.activeElement.id,
  }));
  await page.close();

  assert.equal(first.firstId, "settings.web-search", `the first row was ${first.firstId}`);
  assert.deepEqual(out.calls, ["settings"], `Rust was asked for: ${JSON.stringify(out.calls)}`);
  assert.ok(out.place && out.place.place === "web-search",
    `Settings would open at ${JSON.stringify(out.place)}`);
  assert.equal(out.hidden, true, "the palette stayed on screen after opening a row");
  // Closing puts the keyboard back where it was, not on <body>.
  assert.equal(out.focus, "prompt", `the focus landed on ${out.focus}`);
});

await check("Enter on a Brain row writes the place the Brain already reads", async () => {
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.type("retirement");
  await page.waitForTimeout(250);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  const out = await page.evaluate(() => ({
    calls: window.__calls.filter((c) => c[0] === "open_fix_place").map((c) => c[1] && c[1].place),
    brain: JSON.parse(localStorage.getItem("jarvis.brain.place") || "null"),
  }));
  await page.close();
  assert.deepEqual(out.calls, ["brain"], `Rust was asked for: ${JSON.stringify(out.calls)}`);
  assert.ok(out.brain && out.brain.place === "brain.work.retirement",
    `the Brain would open at ${JSON.stringify(out.brain)}`);
});

await check("CONTROL: opening a row runs no command beyond opening a window", async () => {
  // "It offers only what already exists": nothing here decides an approval,
  // starts a chat or changes a setting.
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.type("backup");
  await page.waitForTimeout(200);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(200);
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  await page.close();
  const banned = ["decide_approval", "stream_chat", "set_appearance", "set_animal",
    "brain_memory_forget", "capture_note", "stop_everything"];
  for (const name of banned) {
    assert.ok(!calls.includes(name), `opening a row called ${name}`);
  }
});

/* ── The keyboard trap, the gate, and the empty state ────────────────────── */

await check("Tab cannot leave the palette while it is open", async () => {
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.type("backup");
  await page.waitForTimeout(200);
  let inside = true;
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    const where = await page.evaluate(() =>
      document.activeElement.closest("#palette") ? "inside" : "outside");
    if (where !== "inside") inside = false;
  }
  await page.keyboard.press("Shift+Tab");
  const back = await page.evaluate(() => document.activeElement.closest("#palette") ? "inside" : "outside");
  await page.close();
  assert.equal(inside, true, "Tab left the palette for the page behind it");
  assert.equal(back, "inside", "Shift+Tab left the palette");
});

await check("Escape closes the palette and not the whole bar", async () => {
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);
  const out = await page.evaluate(() => ({
    hidden: document.getElementById("palette").hidden,
    prompt: document.getElementById("prompt").value,
    focus: document.activeElement.id,
  }));
  await page.close();
  assert.equal(out.hidden, true, "Escape left the palette on screen");
  assert.equal(out.focus, "prompt", `Escape put the focus on ${out.focus}`);
});

await check("the palette refuses to cover a gate, and the gate still works", async () => {
  // Esc must still park the card rather than open a finder over it.
  const page = await openBar({ pending: [K.APPROVAL_RAISED] });
  await page.waitForTimeout(300);
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(250);
  const refused = await paletteState(page);
  await page.close();

  const page2 = await openBar({ pending: [K.APPROVAL_RAISED] });
  await page2.waitForTimeout(300);
  await page2.keyboard.press("Escape");
  await page2.waitForTimeout(250);
  const parked = await page2.evaluate(() =>
    document.getElementById("approval").hidden && !document.getElementById("parked").hidden);
  const spoken = await page2.evaluate(() =>
    [...document.querySelectorAll("[aria-live]")].map((r) => r.textContent).join(" | "));
  await page2.close();

  assert.equal(refused.hidden, true, "the palette opened over a waiting card");
  assert.equal(parked, true, "Escape no longer parks the gate");
  assert.match(spoken, /nothing was decided/i, "parking went silent");
});

await check("a search that matches nothing says so in words", async () => {
  const page = await openBar();
  await page.evaluate(WATCH);
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.type("zzzqqq");
  await page.waitForTimeout(300);
  const state = await paletteState(page);
  const spoken = await page.evaluate(() => window.__spoken);
  await page.close();

  assert.equal(state.rowCount, 0, "a nonsense word matched something");
  assert.equal(state.emptyHidden, false, "the no-match state did not appear");
  assert.ok(state.emptyTitle.length > 5 && state.emptyBody.length > 20,
    `the no-match state says nothing: "${state.emptyTitle}" / "${state.emptyBody}"`);
  assert.ok(!/^\s*0\s*$/.test(state.status), "the count line is a bare zero");
  assert.ok(spoken.some((s) => /nothing matches/i.test(s.text)),
    `the no-match count was not announced. saw: ${JSON.stringify(spoken)}`);
});

await check("the bar's own Find button opens it, and Enter in the box still sends", async () => {
  const page = await openBar();
  await page.locator("#palette-hint button").click();
  await page.waitForTimeout(250);
  const opened = await paletteState(page);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  // ...and with the palette closed, typing then Enter is still an ordinary send.
  await page.locator("#prompt").click();
  await page.keyboard.type("hello");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(250);
  const calls = await page.evaluate(() => window.__calls.map((c) => c[0]));
  await page.close();
  assert.equal(opened.hidden, false, "the Find button did nothing");
  assert.equal(opened.focus, "palette-search", "the Find button did not move the keyboard in");
  assert.ok(calls.includes("stream_chat"), "Enter in the box no longer sends");
});

await check("CONTROL: no page threw while any of this ran", async () => {
  const page = await openBar();
  await page.locator("#prompt").focus();
  await page.keyboard.press("/");
  await page.waitForTimeout(150);
  await page.keyboard.type("brain");
  await page.waitForTimeout(200);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await browser.close(); close();
console.log(fails.length ? `\n${fails.length} FAILED` : "\nthe palette works from the keyboard alone");
process.exit(fails.length ? 1 : 0);
