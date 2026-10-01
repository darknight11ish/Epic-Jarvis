/**
 * The finish-time range on a benchmark chart (docs/GOALS-PROGRESS-DESIGN.md
 * "Slice contract (frozen)" section 3; JARVIS-API.md section 101.4;
 * src/projects.js readForecast / forecastExtent / chartGeometry / chartSummary,
 * src/projects-panel.js chart()) - the part that needs no browser.
 *
 * What must hold, against `forecast_cases` in the contract file (the real
 * backend's answers, made by tools/gen_projects_cases.py):
 * - the chart's edges (`extent`) are the shared reference's, for all 16 cases;
 * - the screen-reader text is the chart summary, a space, then the PC's
 *   `words`, as sent (`summary`);
 * - a state with no line draws nothing (no_target, reached, not_enough,
 *   never), and `never` is never turned into "0 weeks";
 * - the dashed line and the band's corners land where the PC put them,
 *   a clipped end gets an arrow, a bracket needs both ends on the target
 *   and the open slow end has none;
 * - the words are never rebuilt here.
 *
 * The browser half (the SVG, both themes, the screen-reader label) is in
 * tests/projects.mjs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  chartGeometry,
  chartSummary,
  forecastExtent,
  FORECAST_STATES,
  readBench,
  readForecast,
} from "../src/projects.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(readFileSync(join(HERE, "fixtures", "projects-cases.json"), "utf8"));
const FC = CASES.forecast_cases;

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const near = (a, b, what) => assert.ok(Math.abs(a - b) < 1e-6 * Math.max(1, Math.abs(b)), `${what}: ${a} vs ${b}`);

const benchOf = (c) => readBench({
  id: "x", name: "5k time", unit: c.unit, better: c.better, target: c.target,
  results: c.points.length,
  latest: c.points.length ? { id: "l", value: c.points[c.points.length - 1].value,
    at: c.points[c.points.length - 1].at } : null,
  points: c.points, forecast: c.forecast,
});

await check("the sixteen worked cases cover every state", async () => {
  assert.equal(FC.length, 16);
  assert.deepEqual([...new Set(FC.map((c) => c.forecast.state))].sort(), [...FORECAST_STATES].sort());
});

await check("the chart's edges are the shared reference's for every case", async () => {
  for (const c of FC) {
    const f = readForecast(c.forecast);
    const got = forecastExtent(c.points, f, c.target);
    near(got.x[0], c.extent.x[0], `${c.name} x lo`);
    near(got.x[1], c.extent.x[1], `${c.name} x hi`);
    near(got.y[0], c.extent.y[0], `${c.name} y lo`);
    near(got.y[1], c.extent.y[1], `${c.name} y hi`);
    // The geometry uses the same edges.
    const g = chartGeometry(c.points, c.target, 320, 120, 8, f);
    near(g.lo, c.extent.y[0], `${c.name} geometry lo`);
    near(g.hi, c.extent.y[1], `${c.name} geometry hi`);
  }
});

await check("the screen-reader text is the summary, a space, then the PC's words as sent", async () => {
  for (const c of FC) {
    assert.equal(chartSummary(benchOf(c)), c.summary, c.name);
  }
  const drawn = FC.find((c) => c.name === "steady_fall");
  assert.equal(chartSummary(benchOf(drawn)), "5 numbers. Latest: 76 min. About 6 weeks at this pace.");
  // No forecast (an older PC, or a read without points): the plain summary.
  const plain = { ...benchOf(drawn), forecast: null };
  assert.equal(chartSummary(plain), "5 numbers. Latest: 76 min.");
});

await check("the words are kept exactly as sent, and never is never '0 weeks'", async () => {
  for (const c of FC) {
    const f = readForecast(c.forecast);
    assert.equal(f.words, c.forecast.words, c.name);
    assert.equal(f.basis, c.forecast.basis, c.name);
  }
  for (const name of ["flat", "wrong_way"]) {
    const f = readForecast(FC.find((c) => c.name === name).forecast);
    assert.equal(f.state, "never");
    assert.equal(f.words, "Not reached at this pace.");
    assert.equal(f.lowWeeks, null);
    assert.equal(f.highWeeks, null);
    assert.doesNotMatch(f.words, /\b0 weeks?\b/);
  }
  assert.equal(readForecast(null), null);
  assert.equal(readForecast({ state: "soon" }), null, "an unknown state is not drawn");
  assert.equal(readForecast(undefined), null);
});

await check("only range and open_ended draw a line and a band", async () => {
  for (const c of FC) {
    const f = readForecast(c.forecast);
    const g = chartGeometry(c.points, c.target, 320, 120, 8, f);
    const draws = ["range", "open_ended"].includes(c.forecast.state);
    assert.equal(g.forecast !== null, draws, c.name);
    assert.equal(f.line !== null, draws, c.name);
  }
});

await check("the dashed line and the band's corners land where the PC put them", async () => {
  for (const c of FC.filter((x) => x.forecast.line)) {
    const f = readForecast(c.forecast);
    const g = chartGeometry(c.points, c.target, 320, 120, 8, f);
    const [xlo, xhi] = c.extent.x;
    const [ylo, yhi] = c.extent.y;
    const px = (at) => 8 + ((at - xlo) / (xhi - xlo)) * 304;
    const py = (v) => 8 + 104 - ((v - ylo) / (yhi - ylo)) * 104;
    const fc = g.forecast;
    near(fc.line.x1, px(c.forecast.line.from.at), `${c.name} line x1`);
    near(fc.line.y1, py(c.forecast.line.from.value), `${c.name} line y1`);
    near(fc.line.x2, px(c.forecast.line.to.at), `${c.name} line x2`);
    near(fc.line.y2, py(c.forecast.line.to.value), `${c.name} line y2`);
    const b = c.forecast.band;
    [b.from, b.fast, b.slow].forEach((p, i) => {
      near(fc.band[i].x, px(p.at), `${c.name} band ${i} x`);
      near(fc.band[i].y, py(p.value), `${c.name} band ${i} y`);
    });
    // Nothing is drawn outside the box, so a line can never leave the picture.
    for (const p of fc.band) assert.ok(p.x >= 8 - 1e-6 && p.x <= 312 + 1e-6, `${c.name} band x in the box`);
    assert.ok(fc.line.x2 <= 312 + 1e-6, `${c.name} line ends inside`);
    // The points sit left of the guess; the newest is not at the far right any more.
    const last = g.points[g.points.length - 1];
    assert.ok(last.x < fc.line.x2 + 1e-6, `${c.name}: the numbers come first, the guess after`);
  }
});

await check("arrows on clipped ends; a bracket only with both ends on the target", async () => {
  const by = Object.fromEntries(FC.map((c) => [c.name, c]));
  const geo = (name) => {
    const c = by[name];
    return chartGeometry(c.points, c.target, 320, 120, 8, readForecast(c.forecast)).forecast;
  };
  // Both ends on the target: a bracket, no arrow.
  const steady = geo("steady_fall");
  assert.ok(steady.bracket, "steady_fall has a bracket");
  assert.equal(steady.arrows.length, 0);
  assert.ok(steady.bracket.x1 <= steady.bracket.x2, "both ends land together when the range is one instant");
  const tY = chartGeometry(by.steady_fall.points, by.steady_fall.target, 320, 120, 8,
    readForecast(by.steady_fall.forecast)).target;
  near(steady.bracket.y, tY, "the bracket sits on the target level");
  // A clipped slow end: an arrow, no bracket (there is no upper end to close it).
  const scattered = geo("scattered_fall");
  assert.equal(scattered.bracket, null);
  assert.ok(scattered.arrows.length >= 1);
  // The open slow end: an arrow and no bracket.
  const open = geo("very_scattered");
  assert.equal(open.bracket, null);
  assert.ok(open.arrows.length >= 1);
  // Every case: a clipped end has an arrow at its corner.
  for (const c of FC.filter((x) => x.forecast.band)) {
    const g = geo(c.name);
    const b = c.forecast.band;
    const clipped = [b.fast.clipped, b.slow.clipped || b.slow.open, c.forecast.line.clipped].some(Boolean);
    assert.equal(g.arrows.length > 0, clipped, c.name);
    const both = c.forecast.cross_low_at !== null && c.forecast.cross_high_at !== null && !b.slow.open;
    assert.equal(g.bracket !== null, both, `${c.name} bracket`);
  }
});

await check("the higher-is-better case draws upward and the y scale holds the whole guess", async () => {
  const c = FC.find((x) => x.name === "rising_goal_higher");
  const f = readForecast(c.forecast);
  const g = chartGeometry(c.points, c.target, 320, 120, 8, f);
  assert.ok(g.forecast.line.y2 < g.forecast.line.y1, "a rising line goes up the page");
  for (const p of g.forecast.band) assert.ok(p.y >= 8 - 1e-6 && p.y <= 112 + 1e-6);
});

await check("without a forecast the chart is exactly what it was", async () => {
  const c = FC.find((x) => x.name === "steady_fall");
  const before = chartGeometry(c.points, c.target, 320, 120);
  const nul = chartGeometry(c.points, c.target, 320, 120, 8, null);
  assert.deepEqual(nul, before);
  assert.equal(before.forecast, null);
  assert.equal(before.points[0].x, 8);
  assert.equal(before.points[before.points.length - 1].x, 312);
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nForecast: edges, words and drawing all read from the contract; nothing rebuilt here");
process.exit(fails.length ? 1 : 0);
