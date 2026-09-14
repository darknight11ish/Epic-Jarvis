/**
 * The accessibility ship blockers, asserted against the real pages.
 *
 * Each of these shipped. The live-region ones are the subtle kind: the markup
 * looked correct and announced nothing, because a live region has to be
 * present and observed BEFORE its contents change, and four of them were
 * written to while `hidden`.
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

/** Records everything pushed into a live region, in order. */
const WATCH = () => {
  const seen = [];
  const regions = document.querySelectorAll("[aria-live]");
  for (const r of regions) {
    new MutationObserver(() => {
      const t = r.textContent.trim();
      if (t) seen.push({ live: r.getAttribute("aria-live"), text: t });
    }).observe(r, { childList: true, characterData: true, subtree: true });
  }
  window.__spoken = seen;
  window.__regionCount = regions.length;
};

await check("no live region is hidden when it is written", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: [], attention: K.ATTENTION_CLEAR }, { width: 750, height: 800 });
  const offenders = await page.evaluate(() =>
    [...document.querySelectorAll("[aria-live]")]
      .filter((el) => el.closest("[hidden]"))
      .map((el) => el.id || el.className));
  assert.deepEqual(offenders, [], `written while hidden: ${offenders.join(", ")}`);
  await page.close();
});

await check("an arriving gate is announced, with its risk", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: [], attention: K.ATTENTION_CLEAR }, { width: 750, height: 800 });
  await page.evaluate(WATCH);
  await page.evaluate((item) => window.__emit("approvals-changed",
    { count: 1, items: [item] }), K.APPROVAL_RAISED);
  await page.waitForTimeout(400);
  const spoken = await page.evaluate(() => window.__spoken);
  const hit = spoken.find((s) => /Approval required/.test(s.text));
  assert.ok(hit, `nothing announced. saw: ${JSON.stringify(spoken)}`);
  assert.equal(hit.live, "assertive", "a halted action should interrupt");
  assert.match(hit.text, /send_email/, "the action must be named");
  assert.match(hit.text, /no unsend|undo|machine/i, "the risk must be said");
  await page.close();
});

await check("parking says it decided nothing", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: [K.APPROVAL_RAISED], attention: K.ATTENTION_CLEAR },
    { width: 750, height: 800 });
  await page.waitForTimeout(400);
  await page.evaluate(WATCH);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);
  const spoken = await page.evaluate(() => window.__spoken);
  const hit = spoken.find((s) => /aside/i.test(s.text));
  assert.ok(hit, `parking was silent. saw: ${JSON.stringify(spoken)}`);
  assert.match(hit.text, /nothing was decided/i,
    "parking must be distinguishable from denying");
  await page.close();
});

await check("the streaming answer is not itself a live region", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: [] }, { width: 750, height: 600 });
  const live = await page.evaluate(() =>
    document.getElementById("answer").getAttribute("aria-live"));
  assert.equal(live, null,
    "#answer re-announces the whole buffer on every repaint if it is live");
  await page.close();
});

await check("the gate does not claim a modality it does not have", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: [K.APPROVAL_RAISED] }, { width: 750, height: 800 });
  await page.waitForTimeout(300);
  const info = await page.evaluate(() => {
    const el = document.getElementById("approval");
    return { role: el.getAttribute("role"), modal: el.getAttribute("aria-modal"),
             labelledby: el.getAttribute("aria-labelledby") };
  });
  if (info.role === "alertdialog" || info.role === "dialog") {
    assert.equal(info.modal, "true",
      "a dialog role without aria-modal and a focus trap teaches the wrong model");
  }
  assert.ok(info.labelledby, "the action being approved must be in the name");
  await page.close();
});

await check("both gate buttons describe the risk", async () => {
  const page = await K.open(browser, base, "index.html",
    { pending: [K.APPROVAL_RAISED] }, { width: 750, height: 800 });
  await page.waitForTimeout(300);
  for (const id of ["approval-approve", "approval-deny"]) {
    const d = await page.evaluate((x) =>
      document.getElementById(x).getAttribute("aria-describedby"), id);
    assert.ok(d, `${id} has no description, so tabbing to it says nothing about cost`);
  }
  await page.close();
});

await check("selecting a graph node is announced and keeps focus", async () => {
  const page = await K.open(browser, base, "brain.html", { pending: [] },
    { width: 1100, height: 700 });
  await page.waitForTimeout(2600);
  await page.evaluate(WATCH);
  await page.fill("#graph-search", "Reasoning");
  await page.waitForTimeout(500);
  const spoken = await page.evaluate(() => window.__spoken);
  assert.ok(spoken.some((s) => /Reasoning/.test(s.text)),
    `selection was silent. saw: ${JSON.stringify(spoken)}`);
  // Click a neighbour; focus must not fall to <body>.
  await page.locator("#node-links button").first().click();
  await page.waitForTimeout(300);
  const active = await page.evaluate(() => document.activeElement.tagName);
  assert.notEqual(active, "BODY", "clicking a neighbour destroyed the focused element");
  await page.close();
});

await check("the canvas label does not promise a control that does not exist", async () => {
  const page = await K.open(browser, base, "brain.html", { pending: [] },
    { width: 1000, height: 600 });
  const label = await page.evaluate(() =>
    document.getElementById("graph-canvas").getAttribute("aria-label"));
  if (/node list/i.test(label)) {
    const list = await page.evaluate(() =>
      document.querySelectorAll("#node-list li, .node-list li").length);
    assert.ok(list > 0, "the label promises a node list and there is none");
  }
  assert.match(label, /search/i, "the label must name the way in that does exist");
  await page.close();
});

/* ── The second round: below ship-blocker, above ignorable ───────────────── */

await check("every window has a heading", async () => {
  // A heading list is one of the two ways someone navigates a page without
  // reading it. The spotlight's and the widget's were empty.
  for (const [file, viewport] of [
    ["index.html", undefined],
    ["widget.html", { width: 320, height: 460 }],
    ["brain.html", { width: 1180, height: 780 }],
    ["settings.html", { width: 720, height: 720 }],
  ]) {
    const page = await K.open(browser, base, file, {}, viewport);
    const first = await page.evaluate(() => {
      const h = document.querySelector("h1, h2, h3");
      return h ? { level: h.tagName, text: h.textContent.trim() } : null;
    });
    await page.close();
    assert.ok(first, `${file} has no heading of any level`);
    assert.equal(first.level, "H1", `${file} starts at ${first.level}, not H1`);
    assert.ok(first.text, `${file}'s H1 is empty`);
  }
});

await check("the rail is one tab stop, and the arrows move inside it", async () => {
  const page = await K.open(browser, base, "brain.html", {}, { width: 1180, height: 780 });
  const roving = await page.evaluate(() =>
    [...document.querySelectorAll('[role="tab"]')].map((t) => t.tabIndex));
  assert.equal(roving.filter((t) => t === 0).length, 1,
    `${roving.filter((t) => t === 0).length} tabs are in the tab order; a tablist has exactly one`);

  await page.locator("#tab-galaxy").focus();
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(200);
  const after = await page.evaluate(() => ({
    focused: document.activeElement.id,
    selected: document.querySelector('[aria-selected="true"]').id,
    tab0: [...document.querySelectorAll('[role="tab"]')].filter((t) => t.tabIndex === 0).length,
  }));
  assert.equal(after.focused, "tab-live", "ArrowDown did not move to the next tab");
  assert.equal(after.selected, "tab-live", "selection did not follow focus");
  assert.equal(after.tab0, 1, "the roving tabindex did not rove");

  await page.keyboard.press("End");
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => document.activeElement.id), "tab-watch",
    "End did not reach the last tab");
  await page.close();
});

await check("state is never carried by hue alone", async () => {
  // Green-vs-red is the most common thing a colour-blind reader cannot read,
  // and these dots were the only thing on either surface saying whether a
  // local service answered.
  const page = await K.open(browser, base, "index.html", {});
  const shapes = await page.evaluate(() => {
    const out = [];
    for (const value of ["true", "false"]) {
      const dot = document.querySelector('[data-service="ollama"]');
      dot.dataset.online = value;
      const i = getComputedStyle(dot.querySelector("i"));
      out.push({ value, radius: i.borderTopLeftRadius, w: i.width, label: dot.getAttribute("aria-label") });
    }
    return out;
  });
  await page.close();
  assert.notEqual(shapes[0].radius, shapes[1].radius,
    "online and offline are the same shape, so only the hue tells them apart");
});

await check("the dots say their state in words too", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await page.waitForTimeout(400);
  const labels = await page.evaluate(() =>
    [...document.querySelectorAll(".service")].map((s) => s.getAttribute("aria-label")));
  await page.close();
  assert.ok(labels.some((l) => l && /online|not answering|live/i.test(l)),
    "a screen reader is told the service's name and nothing about its state");
});

await check("there is a way to make the text bigger", async () => {
  // Every size in these stylesheets is in `px`, and a Tauri window has no
  // browser chrome — so without this, nothing anywhere in the app scales.
  const page = await K.open(browser, base, "index.html", {});
  await page.keyboard.press("Control+Equal");
  await page.waitForTimeout(200);
  const zoom = await page.evaluate(() => {
    try { return localStorage.getItem("jarvis.zoom"); } catch { return null; }
  });
  await page.close();
  assert.ok(zoom && Number(zoom) > 1, `Ctrl+= left the zoom at ${zoom}`);
});

await check("Ctrl+0 comes back", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await page.keyboard.press("Control+Equal");
  await page.keyboard.press("Control+Equal");
  await page.keyboard.press("Control+Digit0");
  await page.waitForTimeout(200);
  const zoom = await page.evaluate(() => localStorage.getItem("jarvis.zoom"));
  await page.close();
  assert.equal(Number(zoom), 1, `Ctrl+0 left the zoom at ${zoom}`);
});

await check("CONTROL: a plain keypress is not a zoom", async () => {
  const page = await K.open(browser, base, "index.html", {});
  await page.locator("#prompt").focus();
  await page.keyboard.type("0-=");
  await page.waitForTimeout(150);
  const [zoom, typed] = await page.evaluate(() => [
    localStorage.getItem("jarvis.zoom"),
    document.getElementById("prompt").value,
  ]);
  await page.close();
  assert.ok(!zoom || Number(zoom) === 1, "typing changed the zoom");
  assert.equal(typed, "0-=", "the zoom handler swallowed ordinary typing");
});

await browser.close(); close();
console.log(fails.length ? `\n${fails.length} FAILED` : "\nall accessibility blockers held");
process.exit(fails.length ? 1 : 0);
