/**
 * The activity heatmap and the balance chart on the desktop (the owner's tick
 * of 2026-09-30; docs/GOALS-PROGRESS-DESIGN.md part C and its "Progress
 * contract (frozen)"; JARVIS-API.md section 105; src/progress.js,
 * src/progress-panel.js, src/projects.css, src-tauri/src/brain/progress.rs).
 *
 * What must hold:
 * - the words are the contract's, key for key (fixtures/progress-cases.json,
 *   written by tools/gen_progress_cases.py from the real backend) and the
 *   phone's;
 * - the geometry is the contract's: every heatmap square of every worked
 *   answer, every radar polygon, spoke, label and ring, within 0.01;
 * - no forbidden word (streak, run of days, longest, missed, share of days,
 *   average, points) in any string of this feature, nor in what it draws;
 * - the page: 12 weeks of squares (level 0 an outline only, levels 1 to 4 the
 *   accent at 0.40, 0.58, 0.79, 1, measured in every theme, no red), a week-per-row table for a
 *   screen reader, the radar (rings at 25/50/75/100 per cent, the target ring
 *   dashed amber, spokes up then clockwise, a centre circle for "no numbers
 *   yet", no overall score), the list under it, and the picker (3 to 8, a name
 *   for each, the PC's refusal shown as sent, held on a stale link);
 * - a health or money picture is hidden with the private lists (only the PC's
 *   words and Show), a private picker row reads "(hidden)";
 * - nothing is stored, spoken or sent to a model;
 * - CONTROL: the three commands are the Brain's alone, the save is held on a
 *   stale link in Rust, and the private answer is taken out in Rust.
 *
 * The first part is pure node; the page checks need Playwright (see
 * tests/README.md) and are skipped, said so, where it is unavailable.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  balanceList,
  canPickMore,
  heatRects,
  heatRows,
  heatSize,
  levelWords,
  LIMITS,
  pickBody,
  polygonAttr,
  radar,
  readActivity,
  readBalance,
  saveState,
  SCREEN_WORDS,
  shadeAlpha,
  WORDS,
} from "../src/progress.js";

/** jarvis_progress.FORBIDDEN_WORDS: no string of this feature may hold one. */
const FORBIDDEN = ["streak", "in a row", "longest", "missed", "keep it up", "don't break",
  "percent", "average", "points"];

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const C = JSON.parse(read("tests/fixtures/progress-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const near = (a, b, msg) => assert.ok(Math.abs(a - b) <= 0.01, `${msg}: ${a} vs ${b}`);
const HEAT = Object.keys(C.heat);
const BAL = Object.keys(C.balance);

/* ── Pure: words, geometry, reading ───────────────────────────────────── */

await check("the words are the contract's, key for key, and the phone's", async () => {
  assert.deepEqual(WORDS, C.words);
  let kt = "";
  try { kt = read("../jarvis-client/app/src/main/java/com/jarvis/client/net/Progress.kt"); } catch { /* not built yet */ }
  if (kt) {
    const flat = kt.replace(/"\s*\+\s*\n\s*"/g, "");
    for (const [key, words] of Object.entries(C.words)) {
      assert.ok(flat.includes(words.replace(/\\/g, "\\\\").replace(/"/g, '\\"')), `the phone lacks ${key}`);
    }
  }
});

await check("the limits and the shading are the contract's", async () => {
  assert.deepEqual(LIMITS, C.limits);
  assert.deepEqual([0, 1, 2, 3, 4].map(shadeAlpha), C.shading.alpha);
  for (let i = 1; i < 5; i += 1) {
    assert.ok(shadeAlpha(i) - shadeAlpha(i - 1) >= C.shading.min_step - 1e-9, `step ${i}`);
  }
  assert.equal(shadeAlpha(99), 1);
  assert.equal(shadeAlpha(-1), 0);
  assert.deepEqual(C.levels.map(levelWords), ["0", "1", "2", "3-4", "5+"]);
});

await check("the heatmap grid: cell 14, gap 3, and every worked answer's squares", async () => {
  assert.equal(C.heat_grid.cell, 14);
  assert.equal(C.heat_grid.gap, 3);
  for (const [weeks, size] of Object.entries(C.heat_grid.sizes)) {
    assert.deepEqual(heatSize(Number(weeks)), { width: size.width, height: size.height }, weeks);
  }
  for (const name of HEAT) {
    const answer = C.heat[name];
    assert.deepEqual(heatRects(answer.days), answer.rects, name);
    assert.deepEqual(heatSize(answer.weeks), { width: answer.size.width, height: answer.size.height }, name);
  }
});

await check("the radar: five worked polygons, spoke by spoke, within 0.01", async () => {
  for (const [name, w] of Object.entries(C.radar_worked)) {
    const g = radar(w.fractions);
    assert.equal(g.size, w.size);
    assert.deepEqual(g.rings, w.rings, name);
    assert.equal(g.radius, w.radius);
    assert.deepEqual(g.center, w.center);
    for (const key of ["spokes", "polygon", "labels"]) {
      assert.equal(g[key].length, w[key].length, `${name} ${key}`);
      g[key].forEach((p, i) => {
        near(p.x, w[key][i].x, `${name} ${key}[${i}].x`);
        near(p.y, w[key][i].y, `${name} ${key}[${i}].y`);
        if (key === "polygon") assert.equal(p.dot, w.polygon[i].dot, `${name} dot ${i}`);
        if (key === "labels") assert.equal(p.anchor, w.labels[i].anchor, `${name} anchor ${i}`);
      });
    }
  }
});

await check("spokes start straight up and run clockwise", async () => {
  const g = radar([1, 1, 1, 1]);
  assert.deepEqual(g.spokes.map((s) => [s.x, s.y]), [[130, 50], [210, 130], [130, 210], [50, 130]]);
  const centre = radar([null, null, null]);
  assert.ok(centre.polygon.every((p) => p.dot && p.x === 130 && p.y === 130));
  const wild = radar([2, -1, Number.NaN, "x"]);
  assert.deepEqual(wild.fractions, [1, 0, null, null], "kept between 0 and 1, junk is a centre dot");
});

await check("every balance answer's radar is the contract's", async () => {
  for (const name of BAL) {
    const answer = C.balance[name];
    const b = readBalance(answer);
    const g = radar(b.axes.map((a) => a.fraction));
    assert.equal(g.fractions.length, answer.radar.fractions.length, name);
    g.polygon.forEach((p, i) => {
      near(p.x, answer.radar.polygon[i].x, `${name} x${i}`);
      near(p.y, answer.radar.polygon[i].y, `${name} y${i}`);
      assert.equal(p.dot, answer.radar.polygon[i].dot);
    });
    assert.equal(polygonAttr(g).split(" ").filter(Boolean).length, b.axes.length);
  }
});

await check("every real answer reads, and a missing key gets its empty value", async () => {
  for (const name of HEAT) {
    const a = readActivity(C.heat[name]);
    assert.equal(a.words, C.heat[name].words, name);
    assert.equal(a.keepOnScreen, C.heat[name].keep_on_screen, name);
    assert.equal(a.days.length, C.heat[name].days.length, name);
  }
  assert.equal(readActivity(C.heat.private_number).keepOnScreen, true);
  const none = readActivity(null);
  assert.deepEqual([none.days, none.columns, none.total, none.words, none.keepOnScreen], [[], [], 0, "", false]);
  assert.equal(none.note, C.words.heat_undated);
  assert.equal(none.hiddenWords, C.words.hidden);
  const bal = readBalance(null);
  assert.deepEqual([bal.axes, bal.choices, bal.drawable, bal.min, bal.max], [[], [], false, 3, 8]);
  assert.equal(readBalance({ axes: [{ label: "A", state: "bogus", fraction: 3 }] }).axes[0].state, "progress");
  assert.equal(readBalance({ axes: [{ label: "A", fraction: 3 }] }).axes[0].fraction, 1);
  assert.equal(readBalance({ available: false }).available, false);
});

await check("the screen-reader table: a row per week, seven days Monday first, none after today", async () => {
  for (const name of HEAT) {
    const a = readActivity(C.heat[name]);
    const rows = heatRows(a);
    assert.deepEqual(rows.map((r) => r.label), C.heat[name].columns.map((c) => c.label), name);
    const cells = rows.flatMap((r) => r.cells);
    assert.equal(cells.length, a.days.length, `${name}: one cell for each day the PC sent`);
    assert.deepEqual(cells, C.heat[name].days.map((d) => d.words), name);
    for (const r of rows) assert.ok(r.cells.length <= 7);
  }
  const last = heatRows(readActivity(C.heat.one_day)).at(-1);
  assert.ok(last.label.startsWith("Week of"));
});

await check("the list under the balance chart: every area with its value, in the order sent, no total", async () => {
  const b = readBalance(C.balance.five_areas_mixed);
  const list = balanceList(b);
  assert.deepEqual(list.map((r) => r.text), [
    "Body weight: 72.5 of 70 kg", "Weekly distance: 12.5 of 20 km", "Emergency fund: $400 of $1000",
    "Books read: 12 of 12", "Sleep target: no numbers yet"]);
  assert.equal(list.length, b.axes.length);
  assert.deepEqual(list.map((r) => r.private), b.axes.map((a) => a.keepOnScreen));
  assert.equal(balanceList(readBalance(C.balance.nothing_picked)).length, 0);
  const text = list.map((r) => r.text).join(" ");
  assert.doesNotMatch(text, /total|score|overall/i);
});

await check("the picker's rules: the ninth is off, 3 to 8 saves, none clears", async () => {
  assert.equal(canPickMore(7), true);
  assert.equal(canPickMore(8), false);
  assert.deepEqual([0, 1, 2, 3, 8, 9].map((n) => saveState(n)), ["clear", "off", "off", "save", "save", "off"]);
  const body = pickBody([
    { picked: true, kind: "bench", ref: "a", name: "Weight", label: "Weight" },
    { picked: false, kind: "bench", ref: "b", name: "Books", label: "x" },
    { picked: true, kind: "goal", ref: "g", name: "Insulate the garage", label: " Garage " },
    { picked: true, kind: "bench", ref: "c", name: "Sleep", label: "" },
  ]);
  assert.deepEqual(body, [{ kind: "bench", ref: "a" }, { kind: "goal", ref: "g", label: "Garage" },
    { kind: "bench", ref: "c" }]);
});

await check("the chart keeps its order; new ticks go after it in the order ticked (the phone does the same)", async () => {
  // On the chart now: goal G, bench B, bench A (that order). The picker lists benches first.
  const rows = [
    { picked: true, kind: "bench", ref: "A", name: "A", label: "A", at: 2, tick: 0 },
    { picked: true, kind: "bench", ref: "B", name: "B", label: "B", at: 1, tick: 0 },
    { picked: true, kind: "bench", ref: "N2", name: "N2", label: "N2", at: -1, tick: 2 },
    { picked: true, kind: "bench", ref: "N1", name: "N1", label: "N1", at: -1, tick: 1 },
    { picked: true, kind: "goal", ref: "G", name: "G", label: "G", at: 0, tick: 0 },
    { picked: false, kind: "bench", ref: "Z", name: "Z", label: "Z", at: -1, tick: 0 },
  ];
  assert.deepEqual(pickBody(rows).map((a) => a.ref), ["G", "B", "A", "N1", "N2"]);
  // An area unticked and ticked again goes to the end, like the phone's list.
  rows[1].at = -1;
  rows[1].tick = 3;
  assert.deepEqual(pickBody(rows).map((a) => a.ref), ["G", "A", "N1", "N2", "B"]);
});

await check("no forbidden word in this feature's strings or the PC's real sentences", async () => {
  const strings = [...Object.values(WORDS), ...Object.values(SCREEN_WORDS).flat()];
  for (const name of HEAT) strings.push(C.heat[name].words, C.heat[name].summary, C.heat[name].note,
    ...C.heat[name].days.map((d) => d.words));
  for (const name of BAL) strings.push(C.balance[name].words, C.balance[name].summary,
    ...C.balance[name].axes.map((a) => a.value_words));
  for (const s of strings) {
    for (const bad of FORBIDDEN) assert.ok(!String(s).toLowerCase().includes(bad), `"${s}" has "${bad}"`);
  }
  for (const file of ["src/progress.js", "src/progress-panel.js"]) {
    // SVG's own attribute is called "points"; the word is not this feature's.
    const src = read(file).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "")
      .replace(/\bpoints: polygonAttr/g, "shape: polygonAttr");
    for (const bad of FORBIDDEN) assert.ok(!src.toLowerCase().includes(bad), `${file} has "${bad}"`);
  }
});

/* ── CONTROL: the wiring ──────────────────────────────────────────────── */

await check("CONTROL: three commands, the Brain's alone; the save is held; the picture is taken out in Rust", async () => {
  const rs = read("src-tauri/src/brain/progress.rs");
  const cmds = ["brain_progress_activity", "brain_progress_balance", "brain_progress_balance_save"];
  const body = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  assert.ok(body("brain_progress_balance_save").includes("require_link_live(&app)?;"), "the save is not held");
  assert.ok(body("brain_progress_balance_save").indexOf("require_link_live") < body("brain_progress_balance_save").indexOf(".post("));
  assert.ok(!body("brain_progress_activity").includes("require_link_live"), "a read is held");
  assert.match(rs, /fn words_hidden[\s\S]*private_hidden\(app\)[\s\S]*app_locked\(app\)/);
  assert.match(rs, /fn hide_private/);
  for (const cmd of cmds) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::progress::${cmd},`));
  }
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  for (const cmd of cmds) {
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-progress"], cmd);
  }
  const caps = (win) => JSON.parse(read(`src-tauri/capabilities/${win}.json`)).permissions;
  assert.ok(caps("brain").includes("brain-progress"));
  for (const other of ["quickbar", "hud", "settings", "faces", "floating", "onboarding", "widget"]) {
    assert.ok(!caps(other).includes("brain-progress"), `${other} holds brain-progress`);
  }
  // Literal route strings, so tools/check_parity.py sees them.
  assert.match(rs, /\/api\/progress\/activity/);
  assert.match(rs, /\/api\/progress\/balance/);
  // Nothing speaks, nothing is stored, no outside library, no markup from the PC.
  for (const file of ["src/progress.js", "src/progress-panel.js"]) {
    const src = read(file);
    for (const never of ["speak_reply", "speak(", "innerHTML", "localStorage", "sessionStorage",
      "indexedDB", "https://", "fetch(", "XMLHttpRequest", "import("]) {
      assert.ok(!src.includes(never), `${file} mentions ${never}`);
    }
    assert.doesNotMatch(src, /invoke\("(approve|deny|decide|resolve)/);
  }
  for (const other of ["chat", "quickbar", "speech"]) {
    assert.ok(!read("src/projects-panel.js").includes(`progress-panel.js").${other}`));
  }
  // The section carries its menu id, so "Show or hide menus" can hide it later.
  assert.match(read("src/brain.html"), /id="progress-root"[^>]*data-menu-id="brain\.projects\.progress"/);
  // Colours: theme tokens only, and none of the chart's classes is red.
  const css = read("src/projects.css");
  const block = css.slice(css.lastIndexOf("/*", css.indexOf("Progress: the activity heatmap"))).replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(block, /#[0-9a-fA-F]{3,8}\b|rgba?\((?!var)/, "a literal colour");
  const chart = block.slice(0, block.indexOf(".pg-said"))
    + block.slice(block.indexOf(".pg-radar"), block.indexOf(".pg-list"));
  assert.doesNotMatch(chart, /--bad|--danger|red/i, "the chart uses a red token");
});

/* ── The window ───────────────────────────────────────────────────────── */

let K = null;
let contrast = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
  contrast = await import("./contrast.mjs");
} catch {
  console.log("skip  the page checks: Playwright is not installed (tests/README.md)");
}

if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const SIZE = { width: 1180, height: 1000 };

  const tab = async ({ progress = null, link = {}, security = null, appLock = false } = {}) => {
    const data = { link, appLock };
    if (progress) data.progress = progress;
    if (security) data.security = security;
    const page = await K.open(browser, base, "brain.html", data, SIZE);
    await page.locator("#tab-projects").click();
    await page.waitForTimeout(500);
    return page;
  };
  const calls = (page) => page.evaluate(() => window.__progress.calls);
  const ok = (extra = {}) => ({ activity: C.heat.mixed_levels, balance: C.balance.five_areas_mixed, ...extra });

  await check("an older PC has no such route: the section is not shown at all", async () => {
    const page = await tab();
    const hidden = await page.locator("#progress-root").evaluate((n) => n.hidden || n.children.length === 0);
    const errors = page.__errors;
    await page.close();
    assert.ok(hidden);
    assert.deepEqual(errors, []);
  });

  await check("the heatmap: squares where the contract puts them, shaded by level, in words", async () => {
    const page = await tab({ progress: ok() });
    const heading = await page.locator("#progress-heading").textContent();
    const rects = await page.locator("#progress-root .pg-grid .pg-cell").evaluateAll((els) => els.map((e) => ({
      x: Number(e.getAttribute("x")), y: Number(e.getAttribute("y")), size: Number(e.getAttribute("width")),
      h: Number(e.getAttribute("height")), rx: e.getAttribute("rx"), cls: e.getAttribute("class"),
    })));
    const svg = await page.locator("#progress-root .pg-grid").evaluate((e) => ({
      hidden: e.getAttribute("aria-hidden"), vb: e.getAttribute("viewBox"), w: e.getAttribute("width"),
      focus: e.getAttribute("focusable"),
    }));
    const title = await page.locator("#progress-root .pg-grid .pg-day title").allTextContents();
    const words = await page.locator("#progress-root .pg-heat .pg-words").textContent();
    const undated = await page.locator("#progress-root .pg-undated").textContent();
    const legend = await page.locator("#progress-root .pg-legend .pg-cell").count();
    const errors = page.__errors;
    await page.close();
    const want = C.heat.mixed_levels;
    assert.equal(heading, "Progress");
    assert.equal(rects.length, want.rects.length);
    rects.forEach((r, i) => {
      assert.deepEqual([r.x, r.y, r.size, r.h, r.rx], [want.rects[i].x, want.rects[i].y, 14, 14, "3"], `square ${i}`);
      assert.match(r.cls, new RegExp(`pg-l${want.rects[i].level}$`), `level of ${i}`);
    });
    assert.equal(svg.hidden, "true");
    assert.equal(svg.vb, `0 0 ${want.size.width} ${want.size.height}`);
    assert.deepEqual(title, want.days.map((d) => d.words), "the hover words are the day's words as sent");
    assert.equal(words, want.words);
    assert.equal(undated, C.words.heat_undated);
    assert.equal(legend, 5, "five swatches");
    assert.deepEqual(errors, []);
  });

  await check("level 0 is an outline only; levels 1 to 4 are the accent at the contract's alphas, and distinguishable in every theme", async () => {
    const page = await tab({ progress: ok({ activity: C.heat.mixed_levels }) });
    // The legend holds one swatch of every level, so all five are measured.
    const out = {};
    for (const theme of ["deep-space", "paper", "high-contrast"]) {
      out[theme] = await page.evaluate((t) => {
        document.documentElement.setAttribute("data-theme", t);
        const style = (sel) => getComputedStyle(document.querySelector(sel));
        const pick = (l) => {
          const s = style(`#progress-root .pg-legend .pg-l${l}`);
          return { fill: s.fill, stroke: s.stroke, strokeWidth: s.strokeWidth };
        };
        const probe = document.createElement("span");
        document.body.append(probe);
        const tok = (name) => { probe.style.color = `var(${name})`; return getComputedStyle(probe).color; };
        const res = {
          levels: [0, 1, 2, 3, 4].map(pick), surface: tok("--surface-2"), accent: tok("--accent"),
          border: tok("--border-strong"), card: tok("--surface-1"),
        };
        probe.remove();
        return res;
      }, theme);
    }
    await page.close();
    const need = C.shading.require;
    for (const [theme, v] of Object.entries(out)) {
      assert.equal(v.levels[0].fill, "none", `${theme}: level 0 has a fill`);
      assert.equal(v.levels[0].stroke, v.border, `${theme}: level 0's outline is not border-strong`);
      assert.equal(v.levels[0].strokeWidth, "1px");
      const composed = [];
      const under = contrast.flatten(contrast.parseColor(v.surface), contrast.BLACK);
      for (let l = 1; l <= 4; l += 1) {
        const c = contrast.parseColor(v.levels[l].fill);
        assert.ok(Math.abs(c[3] - C.shading.alpha[l]) < 0.005, `${theme}: level ${l} alpha ${c[3]}`);
        assert.equal(v.levels[l].stroke, "none");
        composed.push(contrast.flatten(c, under));
      }
      const acc = contrast.parseColor(v.accent);
      // The owner's rule (2026-09-30): the ladder can be told apart. Level 1 is
      // clearly there over the surface, every neighbouring pair is a visible
      // step, and the top level reads as text-strength.
      const first = contrast.ratio(composed[0], under);
      assert.ok(first >= need.first_over_surface, `${theme}: level 1 is only ${first.toFixed(2)}:1 over the surface`);
      for (let l = 1; l < 4; l += 1) {
        const r = contrast.ratio(composed[l], composed[l - 1]);
        assert.ok(r >= need.neighbour, `${theme}: levels ${l} and ${l + 1} read ${r.toFixed(2)}:1`);
      }
      const top = contrast.ratio(composed[3], under);
      assert.ok(top >= need.top, `${theme}: the top level is only ${top.toFixed(2)}:1 over the surface`);
      assert.deepEqual(composed[3], acc.slice(0, 3), `${theme}: level 4 is the accent itself`);
      // The fixture's own measured numbers (made from theme.css by the generator) agree.
      const fx = C.shading.themes[theme];
      assert.deepEqual(fx.surface, under, `${theme}: the fixture's surface`);
      assert.deepEqual(fx.over_surface.map((x) => Math.round(x * 100)),
        composed.map((c) => Math.round(contrast.ratio(c, under) * 100)), `${theme}: the fixture's ratios`);
      // No red anywhere in the ladder: the hue is the accent's, never the error's.
      for (let l = 1; l <= 4; l += 1) {
        const [r, g, b] = contrast.parseColor(v.levels[l].fill);
        assert.deepEqual([r, g, b], acc.slice(0, 3), `${theme}: level ${l} is not the accent`);
      }
    }
    assert.notDeepEqual(out["deep-space"].surface, out.paper.surface, "the ladder did not follow the theme");
  });

  await check("a screen reader gets a week-per-row table; the squares are hidden from it", async () => {
    const page = await tab({ progress: ok() });
    const caption = await page.locator("#progress-root .pg-table caption").textContent();
    const rows = await page.locator("#progress-root .pg-table tbody tr").evaluateAll((trs) => trs.map((tr) => ({
      head: tr.querySelector("th").textContent, scope: tr.querySelector("th").scope,
      cells: [...tr.querySelectorAll("td")].map((td) => td.textContent),
    })));
    const heads = await page.locator("#progress-root .pg-table thead th").allTextContents();
    const seen = await page.locator("#progress-root .pg-table").evaluate((t) => {
      const r = t.parentElement.getBoundingClientRect();
      return { w: r.width, h: r.height, cls: t.parentElement.className };
    });
    await page.close();
    const want = C.heat.mixed_levels;
    assert.equal(caption, want.summary);
    assert.deepEqual(rows.map((r) => r.head), want.columns.map((c) => c.label));
    assert.ok(rows.every((r) => r.scope === "row"));
    assert.deepEqual(rows.flatMap((r) => r.cells), want.days.map((d) => d.words));
    assert.ok(rows.every((r) => r.cells.length <= 7));
    assert.deepEqual(heads, ["Week", ...SCREEN_WORDS.days]);
    assert.match(seen.cls, /sr-only/);
    assert.ok(seen.w <= 1 && seen.h <= 1, "the table is visually hidden");
  });

  await check("an empty heatmap says so and still draws a neutral grid", async () => {
    const page = await tab({ progress: ok({ activity: C.heat.empty }) });
    const words = await page.locator("#progress-root .pg-heat .pg-words").textContent();
    const levels = await page.locator("#progress-root .pg-grid .pg-cell").evaluateAll((els) =>
      els.map((e) => e.getAttribute("class").replace("pg-cell ", "")));
    const text = await page.locator("#progress-root .pg-heat").innerText();
    await page.close();
    assert.equal(words, C.heat.empty.words);
    assert.equal(levels.length, C.heat.empty.days.length);
    assert.ok(levels.every((l) => l === "pg-l0"));
    assert.doesNotMatch(text, /streak|missed|%/i);
  });

  await check("the radar: rings at a quarter, half, three quarters and the target; the shape as the contract draws it", async () => {
    const page = await tab({ progress: ok({ balance: C.balance.five_areas_mixed }) });
    const info = await page.evaluate(() => {
      const svg = document.querySelector("#progress-root .pg-radar");
      const rings = [...svg.querySelectorAll(".pg-ring")].map((c) => ({
        r: Number(c.getAttribute("r")), cls: c.getAttribute("class"),
        dash: getComputedStyle(c).strokeDasharray, stroke: getComputedStyle(c).stroke,
      }));
      const probe = document.createElement("span");
      document.body.append(probe);
      probe.style.color = "var(--warn)";
      const warn = getComputedStyle(probe).color;
      probe.remove();
      return {
        hidden: svg.getAttribute("aria-hidden"), role: svg.getAttribute("role"), rings, warn,
        spokes: [...svg.querySelectorAll(".pg-spoke")].map((l) => [l.getAttribute("x2"), l.getAttribute("y2")]),
        shape: svg.querySelector(".pg-shape").getAttribute("points"),
        shapeStroke: getComputedStyle(svg.querySelector(".pg-shape")).strokeWidth,
        dots: svg.querySelectorAll(".pg-vertex").length,
        hollow: [...svg.querySelectorAll(".pg-empty-dot")].map((c) => ({
          cx: c.getAttribute("cx"), cy: c.getAttribute("cy"), r: c.getAttribute("r"),
          fill: getComputedStyle(c).fill })),
        labels: [...svg.querySelectorAll(".pg-label")].map((t) => ({
          short: t.firstChild.textContent, value: t.querySelector(".pg-value").textContent,
          anchor: t.getAttribute("text-anchor") })),
        caption: document.querySelector("#progress-root .pg-balance figcaption").textContent,
      };
    });
    const errors = page.__errors;
    await page.close();
    const want = C.balance.five_areas_mixed;
    assert.equal(info.hidden, "true");
    assert.deepEqual(info.rings.map((r) => r.r), [20, 40, 60, 80]);
    assert.ok(info.rings.slice(0, 3).every((r) => r.dash === "none"), "inner rings are solid");
    assert.notEqual(info.rings[3].dash, "none", "the target ring is dashed");
    assert.equal(info.rings[3].stroke, info.warn, "the target ring is the warn colour");
    assert.match(info.rings[3].cls, /pg-target/);
    assert.equal(info.spokes.length, 5);
    info.spokes.forEach(([x, y], i) => {
      near(Number(x), want.radar.spokes[i].x, `spoke ${i}`);
      near(Number(y), want.radar.spokes[i].y, `spoke ${i}`);
    });
    info.shape.split(" ").forEach((p, i) => {
      const [x, y] = p.split(",").map(Number);
      near(x, want.radar.polygon[i].x, `corner ${i}`);
      near(y, want.radar.polygon[i].y, `corner ${i}`);
    });
    assert.equal(info.shapeStroke, "2px");
    assert.equal(info.dots, 4, "a dot on every corner but the empty one");
    assert.equal(info.hollow.length, 1, "one hollow circle for the area with no numbers");
    assert.deepEqual([info.hollow[0].cx, info.hollow[0].cy, info.hollow[0].r], ["130", "130", "4"]);
    assert.equal(info.hollow[0].fill, "none");
    assert.deepEqual(info.labels.map((l) => l.short), want.axes.map((a) => a.short));
    assert.deepEqual(info.labels.map((l) => l.value), want.axes.map((a) => a.value_words));
    assert.deepEqual(info.labels.map((l) => l.anchor), want.radar.labels.map((l) => l.anchor));
    assert.equal(info.caption, want.summary);
    assert.deepEqual(errors, []);
  });

  await check("the list under the chart carries every area, private ones marked, and no total", async () => {
    const page = await tab({ progress: ok({ balance: C.balance.five_areas_mixed }) });
    const items = await page.locator("#progress-root .pg-list li").allTextContents();
    const privates = await page.locator("#progress-root .pg-list li .pg-private").count();
    const section = await page.locator("#progress-root .pg-balance").innerText();
    await page.close();
    const want = C.balance.five_areas_mixed;
    assert.equal(items.length, want.axes.length);
    want.axes.forEach((a, i) => {
      assert.ok(items[i].startsWith(`${a.label}: ${a.value_words}`), `${items[i]}`);
    });
    assert.equal(privates, want.axes.filter((a) => a.keep_on_screen).length);
    assert.match(items[4], /^Sleep target: no numbers yet/);
    // The contract's own two sentences say there is none ("There is no total.",
    // "No overall score."); nothing else on the section may speak of one.
    const rest = section.replace(C.words.balance_under, "").replace(want.summary, "");
    assert.doesNotMatch(rest, /overall|total|score|average|%/i);
  });

  await check("fewer than 3 areas: the words and the list, no picture; none: the empty words", async () => {
    const few = await tab({ progress: ok({ balance: C.balance.after_a_benchmark_is_deleted }) });
    const words = await few.locator("#progress-root .pg-balance .pg-words").textContent();
    const radarCount = await few.locator("#progress-root .pg-radar").count();
    const list = await few.locator("#progress-root .pg-list li").count();
    await few.close();
    assert.equal(words, "Pick at least 3 to see the chart.");
    assert.equal(radarCount, 0);
    assert.equal(list, 2);
    const none = await tab({ progress: ok({ balance: C.balance.nothing_picked }) });
    const w = await none.locator("#progress-root .pg-balance .pg-words").textContent();
    const l = await none.locator("#progress-root .pg-list li").count();
    await none.close();
    assert.equal(w, "Nothing picked yet.");
    assert.equal(l, 0);
  });

  await check("hidden with the private lists: only the PC's words and Show, then the picture", async () => {
    const page = await tab({
      progress: ok({ activity: C.heat.private_number, balance: C.balance.three_areas }),
      security: { hidden: true },
    });
    const text = await page.locator("#progress-root").innerText();
    const svgs = await page.locator("#progress-root svg").count();
    const tables = await page.locator("#progress-root table").count();
    const shows = await page.locator("#progress-root .pg-hidden button").allTextContents();
    const hiddenWords = await page.locator("#progress-root .pg-hidden .empty").allTextContents();
    const edit = await page.getByRole("button", { name: C.words.balance_edit }).count();
    await page.locator("#progress-root .pg-hidden[data-kind=activity] button").click();
    await page.waitForTimeout(400);
    const after = await page.locator("#progress-root .pg-grid .pg-cell").count();
    const stillHidden = await page.locator("#progress-root .pg-hidden").count();
    const editOffered = await page.getByRole("button", { name: C.words.balance_edit }).count();
    const errors = page.__errors;
    await page.close();
    assert.equal(svgs, 0, "a picture is drawn while hidden");
    assert.equal(tables, 0);
    assert.deepEqual(shows, ["Show", "Show"]);
    assert.deepEqual(hiddenWords, [C.words.hidden, C.words.hidden]);
    assert.doesNotMatch(text, /Emergency|Body weight|Garage|Running|thing on/);
    assert.equal(edit, 0, "the picker is offered on a picture that is hidden");
    assert.equal(after, C.heat.private_number.days.length, "Show brings the picture back");
    assert.equal(stillHidden, 0, "Show is the owner's one Windows Hello: both pictures come back");
    assert.equal(editOffered, 1, "and the picker with them");
    assert.deepEqual(errors, []);
  });

  await check("App lock locked hides a private picture the same way; an ordinary one stays", async () => {
    const page = await tab({
      progress: ok({ activity: C.heat.private_number, balance: C.balance.nothing_picked }),
      appLock: true,
    });
    const hiddenCount = await page.locator("#progress-root .pg-hidden").count();
    const balance = await page.locator("#progress-root .pg-balance .pg-words").textContent();
    await page.close();
    assert.equal(hiddenCount, 1);
    assert.equal(balance, "Nothing picked yet.");
  });

  await check("nothing is stored: no localStorage or sessionStorage key, and nothing spoken", async () => {
    const page = await tab({ progress: ok() });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    const stored = await page.evaluate(() => JSON.stringify([
      Object.keys(localStorage), Object.keys(sessionStorage)]));
    const spoken = await page.evaluate(() => (window.__voiceCalls || []).length);
    await page.close();
    assert.doesNotMatch(stored, /progress|balance|activity|heat/i);
    assert.equal(spoken, 0);
  });

  /* The picker ---------------------------------------------------------- */

  const nine = () => {
    const b = JSON.parse(JSON.stringify(C.balance.five_areas_mixed));
    b.choices = Array.from({ length: 9 }, (_, i) => ({
      kind: "bench", ref: `0000000000000000000000000000000${i}`, project: "p", project_name: "Life",
      name: `Area ${i + 1}`, picked: false, keep_on_screen: false,
    }));
    b.axes = []; b.drawable = false; b.words = "Nothing picked yet.";
    return b;
  };

  await check("the picker lists every choice with its project, ticks what is picked and names it", async () => {
    const page = await tab({ progress: ok({ balance: C.balance.three_areas }) });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    const rows = await page.locator("#progress-root .pg-pick").evaluateAll((els) => els.map((e) => ({
      name: e.querySelector(".pg-pick-name").textContent,
      project: (e.querySelector(".pg-pick-project") || {}).textContent || "",
      checked: e.querySelector("input[type=checkbox]").checked,
      rename: e.querySelector(".pg-rename") && !e.querySelector(".pg-rename").hidden
        ? e.querySelector(".pg-rename").value : null,
      label: e.querySelector(".pg-rename") && e.querySelector(".pg-rename").getAttribute("aria-label"),
    })));
    const save = await page.locator("#progress-save").textContent();
    const limit = await page.locator("#progress-root .pg-editor .note").textContent();
    await page.close();
    const want = C.balance.three_areas;
    assert.deepEqual(rows.map((r) => r.name), want.choices.map((c) => c.name), "no hiding while the lists are shown");
    assert.deepEqual(rows.map((r) => r.checked), want.choices.map((c) => c.picked));
    assert.deepEqual(rows.filter((r) => r.rename !== null).map((r) => r.rename), ["Running", "Emergency fund", "Garage"]);
    assert.ok(rows.filter((r) => r.label).every((r) => r.label.startsWith("Name on the chart: ")));
    assert.equal(save, "Save the chart");
    assert.equal(limit, "Pick 3 to 8 areas, or none to clear the chart.");
  });

  await check("Save is on at 3 to 8, off at 1 or 2, 'Clear the chart' at none; the ninth box is off", async () => {
    const page = await tab({ progress: { activity: C.heat.empty, balance: nine() } });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    const boxes = page.locator("#progress-root .pg-pick input[type=checkbox]");
    const save = page.locator("#progress-save");
    const state = async () => ({ text: await save.textContent(), off: await save.isDisabled() });
    const seen = [await state()];
    for (let i = 0; i < 8; i += 1) {
      await boxes.nth(i).check();
      seen.push(await state());
    }
    const ninthOff = await boxes.nth(8).isDisabled();
    await boxes.nth(7).uncheck();
    const ninthOn = await boxes.nth(8).isEnabled();
    await page.close();
    // Nothing ticked: "Clear the chart", enabled (it clears what is saved).
    assert.deepEqual(seen[0], { text: "Clear the chart", off: false });
    assert.deepEqual(seen.slice(1, 3).map((s) => s.off), [true, true], "1 or 2 ticked");
    assert.ok(seen.slice(3).every((s) => !s.off && s.text === "Save the chart"), "3 to 8 ticked");
    assert.equal(ninthOff, true, "the ninth cannot be ticked");
    assert.equal(ninthOn, true, "and can once one is unticked");
  });

  await check("Save sends the picks in order with a typed name only, and the chart is redrawn from the answer", async () => {
    const saved = JSON.parse(JSON.stringify(C.balance.three_areas));
    const page = await tab({ progress: { activity: C.heat.empty, balance: nine(), saved } });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    const boxes = page.locator("#progress-root .pg-pick input[type=checkbox]");
    for (const i of [2, 0, 5]) await boxes.nth(i).check();
    await page.locator("#progress-root .pg-rename").nth(1).waitFor({ state: "hidden" }).catch(() => {});
    const renames = page.locator("#progress-root .pg-rename:visible");
    await renames.nth(1).fill("Garage");
    await page.locator("#progress-save").click();
    await page.waitForTimeout(400);
    const sent = (await calls(page)).filter((c) => c.cmd === "brain_progress_balance_save");
    const editorGone = await page.locator("#progress-root .pg-editor").count();
    const items = await page.locator("#progress-root .pg-list li").count();
    const said = await page.locator("#progress-said").textContent();
    const focus = await page.evaluate(() => document.activeElement && document.activeElement.dataset.fkey);
    await page.close();
    assert.equal(sent.length, 1, "one save");
    // Nothing was on the chart, so the ticks go in the order they were made: 2, 0, 5.
    assert.deepEqual(sent[0].axes, [
      { kind: "bench", ref: "00000000000000000000000000000002", label: "Garage" },
      { kind: "bench", ref: "00000000000000000000000000000000" },
      { kind: "bench", ref: "00000000000000000000000000000005" },
    ]);
    assert.equal(editorGone, 0);
    assert.equal(items, 3);
    assert.equal(said, "Chart saved.");
    assert.equal(focus, "edit-open", "the keyboard is put back on the button that opened the picker");
  });

  await check("saving keeps the chart's order and adds a new tick after it", async () => {
    const want = C.balance.three_areas;
    const page = await tab({ progress: { activity: C.heat.empty, balance: want, saved: want } });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    const boxes = page.locator("#progress-root .pg-pick input[type=checkbox]");
    const firstOff = want.choices.findIndex((c) => !c.picked);
    await boxes.nth(firstOff).check();
    await page.locator("#progress-save").click();
    await page.waitForTimeout(300);
    const sent = (await calls(page)).filter((c) => c.cmd === "brain_progress_balance_save");
    await page.close();
    const chartOrder = want.axes.map((a) => a.ref);
    assert.deepEqual(sent[0].axes.map((a) => a.ref), [...chartOrder, want.choices[firstOff].ref]);
  });

  await check("none ticked clears the chart: an empty list is sent", async () => {
    const page = await tab({ progress: { activity: C.heat.empty, balance: C.balance.three_areas,
      saved: C.balance.nothing_picked } });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    const boxes = page.locator("#progress-root .pg-pick input[type=checkbox]");
    for (const i of [1, 2, 5]) await boxes.nth(i).uncheck();
    const label = await page.locator("#progress-save").textContent();
    await page.locator("#progress-save").click();
    await page.waitForTimeout(300);
    const sent = (await calls(page)).filter((c) => c.cmd === "brain_progress_balance_save");
    const words = await page.locator("#progress-root .pg-balance .pg-words").textContent();
    await page.close();
    assert.equal(label, "Clear the chart");
    assert.deepEqual(sent.map((s) => s.axes), [[]]);
    assert.equal(words, "Nothing picked yet.");
  });

  await check("a refusal is shown as sent beside the picker, which stays open with the ticks kept", async () => {
    const sentence = C.refusals.no_target.error;
    const page = await tab({ progress: { activity: C.heat.empty, balance: nine(), saveError: sentence } });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    const boxes = page.locator("#progress-root .pg-pick input[type=checkbox]");
    for (const i of [0, 1, 2]) await boxes.nth(i).check();
    await page.locator("#progress-save").click();
    await page.waitForTimeout(300);
    const shown = await page.locator("#progress-edit-error").textContent();
    const alert = await page.locator("#progress-edit-error").getAttribute("role");
    const open = await page.locator("#progress-root .pg-editor").count();
    const stillTicked = await page.locator("#progress-root .pg-pick input:checked").count();
    const items = await page.locator("#progress-root .pg-list li").count();
    await page.close();
    assert.equal(shown, sentence);
    assert.equal(alert, "alert");
    assert.equal(open, 1);
    assert.equal(stillTicked, 3);
    assert.equal(items, 0, "a refused save changed nothing on screen");
  });

  await check("a stale link greys the save (rule 4) but not reading or Cancel", async () => {
    const page = await tab({ progress: { activity: C.heat.empty, balance: nine() }, link: { stale: true } });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    const boxes = page.locator("#progress-root .pg-pick input[type=checkbox]");
    for (const i of [0, 1, 2]) await boxes.nth(i).check();
    const off = await page.locator("#progress-save").isDisabled();
    const title = await page.locator("#progress-save").getAttribute("title");
    const cancel = await page.getByRole("button", { name: "Cancel" }).isEnabled();
    await page.getByRole("button", { name: "Cancel" }).click();
    const closed = await page.locator("#progress-root .pg-editor").count();
    const reads = (await calls(page)).filter((c) => c.cmd !== "brain_progress_balance_save").length;
    await page.close();
    assert.equal(off, true);
    assert.match(title, /not confirmed live/);
    assert.equal(cancel, true);
    assert.equal(closed, 0);
    assert.ok(reads >= 2, "both pictures were read");
  });

  await check("while the lists are hidden there is no picker at all, and a save is refused in Rust and here", async () => {
    const b = JSON.parse(JSON.stringify(C.balance.three_areas));
    b.keep_on_screen = false;
    b.axes.forEach((a) => { a.keep_on_screen = false; });
    const page = await tab({ progress: { activity: C.heat.empty, balance: b }, security: { hidden: true } });
    const edit = await page.getByRole("button", { name: C.words.balance_edit }).count();
    const list = await page.locator("#progress-root .pg-list li").count();
    const editor = await page.locator("#progress-root .pg-editor").count();
    // The command itself refuses too (a page script could call it directly).
    const refused = await page.evaluate(async () => {
      try {
        await window.__TAURI__.core.invoke("brain_progress_balance_save", { axes: [] });
        return "";
      } catch (e) { return String((e && e.message) || e); }
    });
    await page.close();
    assert.equal(edit, 0, "a picker is offered while the lists are hidden");
    assert.equal(editor, 0);
    assert.equal(list, b.axes.length, "an ordinary chart is still drawn");
    assert.equal(refused, C.words.hidden);
  });

  await check("Show cannot lift App lock: the picture stays hidden and the line says to unlock first", async () => {
    const page = await tab({
      progress: ok({ activity: C.heat.private_number, balance: C.balance.nothing_picked }),
      appLock: true,
    });
    const before = await page.locator("#progress-root .pg-hidden[data-kind=activity]").count();
    await page.locator("#progress-root .pg-hidden[data-kind=activity] button").click();
    await page.waitForTimeout(400);
    const after = await page.locator("#progress-root .pg-hidden[data-kind=activity]").count();
    const said = await page.locator("#progress-said").textContent();
    const edit = await page.getByRole("button", { name: C.words.balance_edit }).count();
    await page.close();
    assert.equal(before, 1);
    assert.equal(after, 1, "still hidden");
    assert.equal(said, C.words.still_hidden);
    assert.equal(edit, 0, "no picker while App lock hides the lists");
  });

  await check("Refresh reads both pictures again", async () => {
    const page = await tab({ progress: ok() });
    const before = (await calls(page)).length;
    await page.locator("#progress-root").getByRole("button", { name: C.words.refresh }).click();
    await page.waitForTimeout(300);
    const after = (await calls(page)).length;
    await page.close();
    assert.equal(after - before, 2);
  });

  await check("the keyboard: Enter opens the picker, Tab reaches a box, Space ticks it and focus stays", async () => {
    const page = await tab({ progress: { activity: C.heat.empty, balance: nine() } });
    await page.getByRole("button", { name: C.words.balance_edit }).focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Tab");
    const first = await page.evaluate(() => document.activeElement.dataset.fkey);
    await page.keyboard.press("Space");
    const ticked = await page.locator("#progress-root .pg-pick input:checked").count();
    const stillFocused = await page.evaluate(() => document.activeElement.dataset.fkey);
    await page.close();
    assert.match(first, /^pick:bench:/);
    assert.equal(ticked, 1);
    assert.equal(stillFocused, first, "Space ticked the box without moving the keyboard");
  });

  await check("reduced motion: nothing on this section animates", async () => {
    const page = await tab({ progress: ok() });
    await page.getByRole("button", { name: C.words.balance_edit }).click();
    await page.emulateMedia({ reducedMotion: "reduce" });
    const moving = await page.locator("#progress-root").evaluate((root) =>
      [...root.querySelectorAll("[class*=pg-]")].filter((n) => {
        const s = getComputedStyle(n);
        return (s.animationName && s.animationName !== "none") ||
          (s.transitionDuration && !/^0s(, 0s)*$/.test(s.transitionDuration) && s.transitionProperty !== "all");
      }).length);
    await page.close();
    assert.equal(moving, 0);
  });

  await check("the section shows on the Projects list", async () => {
    const page = await tab({ progress: ok() });
    const shown = await page.locator("#progress-root").isVisible();
    await page.close();
    assert.equal(shown, true);
  });

  await browser.close();
  close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe progress pictures hold");
process.exit(fails.length ? 1 : 0);
