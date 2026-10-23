/**
 * hud-edit-geometry.mjs - P0.6 (owner field test, 2026-10-23): Edit HUD in the
 * installed Studio layout must be a real three-column editor, not cards painted
 * over the live stage.
 *
 * What the owner saw on the installed 0.2.277 build: entering Edit HUD left the
 * shell's fixed/overlay rails in force while cards grew edit handles, so cards
 * painted over the stage, over the stage bar and over each other. This suite
 * drives the REAL page into Studio + Edit HUD and measures boxes, not
 * screenshots:
 *
 *   - #shell is exactly three in-flow columns: 300px | the stage | 370px;
 *   - neither rail is fixed/absolute and neither is transformed off-screen;
 *   - left rail / stage / right rail do not overlap, and the right rail ends at
 *     the window's right edge;
 *   - the Stage-top card region has its own row BELOW the stage bar and the
 *     editor banner, instead of painting over the bar (the field-test jumble);
 *   - every card stays inside its own rail and cannot cover the stage, and its
 *     drag handle is what a real click at its centre hits;
 *   - Escape puts Studio's own layout back (60px | 1fr | 0, right rail hidden,
 *     no edit-reveal class left behind).
 *
 * Run at 1920x1080 (the owner's screen) and at 1280x820 (the CSS viewport of a
 * 150%-DPI window on the same PC). Nothing here judges colour or fonts: the
 * monochrome-emoji half is checked in hud.mjs by the page's own DOM (VS15 plus
 * font-variant-emoji), because a Linux CI runner has no Segoe UI Emoji.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (error) { fails.push(name); console.log(`FAIL  ${name}\n      ${error.message}`); }
};

const near = (a, b, tol = 1) => Math.abs(a - b) <= tol;

const { base, close } = await K.serve();
const browser = await K.launch();

/**
 * The page as the desktop shell leaves it. The only IPC Edit HUD needs is the
 * layout store's two commands; without a shell the [Edit HUD] button hides
 * itself, which would make every check below vacuous.
 */
async function openStudioEdit(size) {
  const page = await K.open(browser, base, "jarvis_hud.html", {}, size);
  await page.addInitScript(() => {
    window.__TAURI__ = {
      core: {
        Channel: class { constructor() { this.onmessage = null; } },
        invoke: async (cmd, args) => {
          if (cmd === "get_hud_layout") return { layout: null, source: "none" };
          if (cmd === "set_hud_layout") return { layout: args && args.layout, saved: true, source: "saved" };
          return null;
        },
      },
    };
  });
  await page.reload();
  await page.waitForTimeout(900);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("jarvis:hud-shell", {
    detail: { shell_template: "split-stage", density: "comfortable", default_stage_tab: "galaxy" },
  })));
  await K.until(page, "the page to wear the Studio shell", async () =>
    (await page.evaluate(() => document.body.dataset.hudShell)) === "split-stage", { ms: 5000 });
  await page.waitForTimeout(300);
  await page.click("#hud-edit-toggle");
  await K.until(page, "Edit HUD to turn on", async () =>
    (await page.evaluate(() => document.body.getAttribute("data-hud-edit"))) === "on", { ms: 5000 });
  await page.waitForTimeout(300);
  return page;
}

/** Every box this suite reasons about, in CSS pixels. */
const measure = (page) => page.evaluate(() => {
  const rect = (selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return { x: r.x, y: r.y, w: r.width, h: r.height, right: r.right, bottom: r.bottom,
      display: cs.display, position: cs.position, transform: cs.transform };
  };
  const cards = [...document.querySelectorAll("[data-hud-card]")].map((card) => {
    const r = card.getBoundingClientRect();
    const region = card.closest("[data-hud-region]");
    const handle = card.querySelector("[data-hud-card-handle]");
    const hr = handle ? handle.getBoundingClientRect() : null;
    return {
      id: card.getAttribute("data-hud-card"),
      region: region ? region.getAttribute("data-hud-region") : null,
      visible: !card.hidden && r.width > 0 && r.height > 0,
      x: r.x, y: r.y, right: r.right, bottom: r.bottom,
      handle: hr ? { w: hr.width, h: hr.height } : null,
    };
  });
  return {
    vw: innerWidth,
    shellCols: getComputedStyle(document.getElementById("shell")).gridTemplateColumns,
    left: rect(".rail.left"), stage: rect("#stage"), right: rect("#rail-right"),
    bar: rect("#stage > .stage-bar"),
    banner: rect("#stage > .hud-edit-banner"),
    stageTop: rect('#stage > [data-hud-region="stage_top"]'),
    cards,
  };
});

/**
 * Is the drag handle at the middle of its own card the element a click hits?
 * Scrolls the card into the rail's view first - some cards start below the fold
 * in a short window - so "covered" means covered, not merely off-screen.
 */
const handlesReachable = (page) => page.evaluate(() => {
  const out = [];
  for (const card of document.querySelectorAll("[data-hud-card]")) {
    const handle = card.querySelector("[data-hud-card-handle]");
    if (!handle) { out.push({ id: card.getAttribute("data-hud-card"), hit: false, why: "no handle" }); continue; }
    card.scrollIntoView({ block: "nearest" });
    const hr = handle.getBoundingClientRect();
    if (hr.width < 8 || hr.height < 8) {
      out.push({ id: card.getAttribute("data-hud-card"), hit: false, why: "handle has no box" });
      continue;
    }
    const at = document.elementFromPoint(hr.x + hr.width / 2, hr.y + hr.height / 2);
    out.push({ id: card.getAttribute("data-hud-card"),
      hit: Boolean(at && (at === handle || handle.contains(at) || card.contains(at))) });
  }
  return out;
});

for (const [label, size] of [
  ["1920x1080 (the owner's screen)", { width: 1920, height: 1080 }],
  ["1280x820 (a 150%-DPI window)", { width: 1280, height: 820 }],
]) {
  await check(`P0.6: Studio Edit HUD is three non-overlapping in-flow columns at ${label}`, async () => {
    const page = await openStudioEdit(size);
    try {
      const m = await measure(page);
      const cols = m.shellCols.split(/\s+/).map((value) => parseFloat(value));
      assert.equal(cols.length, 3,
        `the edit shell is not three columns: ${m.shellCols}`);
      assert.ok(near(cols[0], 300) && near(cols[2], 370),
        `the edit columns are not 300px | stage | 370px: ${m.shellCols}`);

      assert.ok(m.left && m.stage && m.right, "a rail or the stage is missing");
      assert.equal(m.left.position, "static", "the left rail is still out of flow in Edit HUD");
      assert.equal(m.right.position, "static", "the right rail is still out of flow in Edit HUD");
      for (const rail of [m.left, m.right]) {
        assert.ok(!/translate|matrix/.test(rail.transform) || rail.transform === "none",
          `a rail is still transformed away: ${rail.transform}`);
        assert.equal(rail.display, "flex", "a revealed rail is not drawn as a column");
      }
      assert.ok(near(m.left.x, 0) && near(m.left.w, 300), `the left rail is not the first 300px column: ${JSON.stringify(m.left)}`);
      assert.ok(near(m.right.right, m.vw), `the right rail does not end at the window edge: ${m.right.right} vs ${m.vw}`);
      assert.ok(m.left.right <= m.stage.x + 1,
        `the left rail overlaps the stage (${m.left.right} > ${m.stage.x})`);
      assert.ok(m.stage.right <= m.right.x + 1,
        `the stage overlaps the right rail (${m.stage.right} > ${m.right.x})`);
      assert.ok(m.stage.w >= 600, `the stage is squeezed to ${m.stage.w}px`);

      assert.ok(m.bar && m.banner && m.stageTop, "the stage bar, editor banner or Stage-top region is missing");
      assert.ok(m.bar.bottom <= m.banner.y + 2,
        `the stage bar and the editor banner overlap (${m.bar.bottom} > ${m.banner.y})`);
      assert.ok(m.banner.bottom <= m.stageTop.y + 2,
        `the editor banner and the Stage-top cards overlap (${m.banner.bottom} > ${m.stageTop.y})`);
      assert.ok(m.stageTop.y >= m.bar.bottom - 1,
        `the Stage-top cards paint over the stage bar (${m.stageTop.y} < ${m.bar.bottom})`);

      const visible = m.cards.filter((card) => card.visible);
      assert.ok(visible.length >= 8, `only ${visible.length} usable cards were drawn`);
      for (const card of visible) {
        if (card.region === "left_rail") {
          assert.ok(card.right <= m.left.right + 1,
            `${card.id} spills out of the left rail (${card.right} > ${m.left.right})`);
          assert.ok(card.right <= m.stage.x + 1, `${card.id} covers the stage`);
        } else if (card.region === "right_rail") {
          assert.ok(card.x >= m.right.x - 1 && card.right <= m.right.right + 1,
            `${card.id} spills out of the right rail (${card.x}..${card.right})`);
          assert.ok(card.x >= m.stage.right - 1, `${card.id} covers the stage`);
        } else if (card.region === "stage_top") {
          assert.ok(card.y >= m.bar.bottom - 1, `${card.id} paints over the stage bar`);
          assert.ok(card.x >= m.stage.x - 1 && card.right <= m.stage.right + 1,
            `${card.id} spills out of the stage (${card.x}..${card.right})`);
        }
        assert.ok(card.handle && card.handle.w > 8 && card.handle.h > 8,
          `${card.id} has no usable drag handle`);
      }

      const reach = await handlesReachable(page);
      for (const row of reach) {
        assert.equal(row.hit, true,
          `card ${row.id}'s drag handle is covered in Edit HUD${row.why ? ` (${row.why})` : ""}`);
      }
    } finally {
      await page.close();
    }
  });

  await check(`P0.6: Escape puts Studio's own layout back at ${label}`, async () => {
    const page = await openStudioEdit(size);
    try {
      await page.keyboard.press("Escape");
      await page.waitForTimeout(400);
      const after = await page.evaluate(() => {
        const shell = document.getElementById("shell");
        const right = document.getElementById("rail-right");
        return {
          edit: document.body.getAttribute("data-hud-edit"),
          shell: document.body.dataset.hudShell,
          cols: getComputedStyle(shell).gridTemplateColumns,
          rightDisplay: getComputedStyle(right).display,
          rightClass: right.className,
          leftClass: document.querySelector(".rail.left").className,
        };
      });
      const cols = after.cols.split(/\s+/).map((value) => parseFloat(value));
      assert.equal(after.edit, "off", "Escape did not leave Edit HUD");
      assert.equal(after.shell, "split-stage", "Escape changed the view shape");
      assert.ok(near(cols[0], 60) && near(cols[2], 0),
        `Studio's own columns were not restored: ${after.cols}`);
      assert.equal(after.rightDisplay, "none", "the right rail is still drawn after Edit HUD");
      assert.ok(!/\bedit-reveal\b/.test(after.rightClass) && !/\bedit-reveal\b/.test(after.leftClass),
        "the edit-reveal class was left behind");
    } finally {
      await page.close();
    }
  });
}

await browser.close();
if (close) await close();

console.log(`\n${fails.length ? `${fails.length} failed` : "all passed"}`);
if (fails.length) { console.log(`failed: ${fails.join(", ")}`); process.exit(1); }
