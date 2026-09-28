/**
 * Seasonal touches behind the character faces (season.js) - the owner's
 * decision of 2026-09-28, "seasonal touches from the date (off by
 * default)", with the rules every new behaviour follows: Still and serious
 * moments switch it off, calm makes it smaller, nothing cute during an
 * approval or an error, calm and never busy.
 *
 * Part 1 needs no browser: the calendar (every season in both halves of the
 * world, each holiday's first and last hour, time zones), what shows when,
 * and the promises about how it looks and moves - behind the face, clear of
 * the monkey's vine, slow, never flashing, never a state colour, a pure
 * function of the clock.
 *
 * Part 2 (a browser, Playwright): draw() paints what scene() says, dims
 * toward the ground, and - once faces.html draws the layer (the host
 * integration) - the switch reaches the face pages, off draws nothing, and
 * Still hides it.
 *
 *     node tests/season.mjs
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const S = require("../src/season.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
/** UTC milliseconds of a local wall-clock moment at `tz` minutes east of UTC. */
const local = (y, mo, d, h = 12, mi = 0, s = 0, tz = -300) => Date.UTC(y, mo - 1, d, h, mi, s) - tz * 60000;
const cal = (y, mo, d, h, mi, s, tz, lat) => S.calendar(local(y, mo, d, h, mi, s, tz), tz, lat);
const scene = (ms, tz, opts, t) => S.scene(ms, tz, t === undefined ? ms / 1000 : t, opts);
// The state colours (faces.html's animal defaults): nothing here may look like one.
const STATE_HOT = { idle: [127, 227, 255], listening: [255, 138, 61], thinking: [143, 123, 255],
  speaking: [159, 240, 255], approval: [255, 193, 77], error: [255, 90, 122] };
const rgbOf = (op) => op.k === S.POLY ? op.v.slice(0, 3) : op.k === S.LINE ? op.v.slice(1, 4) : op.v.slice(3, 6);
const alphaOf = (op) => op.k === S.POLY ? op.v[3] : op.k === S.LINE ? op.v[4] : op.v[6];
const pointsOf = (op) => {
  const v = op.v;
  if (op.k === S.GLOW || op.k === S.DOT) return [[v[0], v[1], v[2]]];
  const from = op.k === S.POLY ? 4 : 5, out = [];
  for (let i = from; i + 1 < v.length; i += 2) out.push([v[i], v[i + 1], 0]);
  return out;
};
// A moment for every touch, New York (EST -300, EDT -240).
const MOMENTS = {
  autumn: [local(2026, 11, 20, 15), -300], halloween: [local(2026, 10, 28, 15, 0, 0, -240), -240],
  winter: [local(2027, 2, 10, 15), -300], december: [local(2026, 12, 24, 20), -300],
  newyear: [local(2027, 1, 1, 0, 0, 25), -300], spring: [local(2027, 4, 20, 15, 0, 0, -240), -240],
  summerDay: [local(2027, 7, 10, 14, 0, 0, -240), -240], summerNight: [local(2027, 7, 10, 22, 30, 0, -240), -240],
};

// ---- Part 1: the calendar and the promises ------------------------------------------

await check("the calendar agrees with JavaScript's own dates, leap days included", () => {
  for (let d = -800; d < 40000; d += 37) {
    const dt = new Date(d * 86400000);
    assert.deepEqual(S.civilFromDays(d), [dt.getUTCFullYear(), dt.getUTCMonth() + 1, dt.getUTCDate()], `day ${d}`);
    assert.equal(S.daysFromCivil(...S.civilFromDays(d)), d);
  }
  assert.deepEqual(S.civilFromDays(S.daysFromCivil(2024, 2, 29)), [2024, 2, 29]);
  assert.deepEqual(S.civilFromDays(S.daysFromCivil(2100, 3, 1) - 1), [2100, 2, 28], "2100 is not a leap year");
});

await check("the seasons by month, northern half (no town set counts as north)", () => {
  const want = { 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring", 6: "summer",
    7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn", 12: "winter" };
  for (let m = 1; m <= 12; m++) {
    for (const lat of [null, 40.7, 0]) {
      const c = cal(2026, m, 15, 12, 0, 0, -300, lat);
      assert.equal(c.season, want[m], `month ${m} lat ${lat}`);
      assert.equal(c.seasons[want[m]], 1);
    }
  }
});

await check("the southern half of the world is six months on", () => {
  const want = { 1: "summer", 4: "autumn", 7: "winter", 10: "spring", 12: "summer" };
  for (const [m, s] of Object.entries(want)) assert.equal(cal(2026, +m, 15, 12, 0, 0, 600, -33.9).season, s, `month ${m}`);
  // Mid-winter snowman in the south: July, not December.
  assert.equal(cal(2026, 7, 1, 12, 0, 0, 600, -33.9).items.snowman, 1);
  assert.equal(cal(2026, 12, 24, 12, 0, 0, 600, -33.9).items.snowman, 0);
  // Holidays follow the calendar in both halves.
  assert.equal(cal(2026, 10, 28, 12, 0, 0, 600, -33.9).items.pumpkin, 1);
  assert.equal(cal(2026, 12, 24, 12, 0, 0, 600, -33.9).items.lights, 1);
});

await check("each holiday: its first and last hour fade, and nothing outside it", () => {
  const p = (d, h, mi) => cal(2026, 10 + (d > 31 ? 1 : 0), d > 31 ? d - 31 : d, h, mi, 0, -240, 40).items.pumpkin;
  assert.equal(p(23, 23, 59), 0, "23 October");
  assert.ok(p(24, 0, 30) > 0.2 && p(24, 0, 30) < 0.8, "fading in on 24 October");
  assert.equal(p(24, 1, 0), 1);
  assert.equal(p(31, 23, 59), 1, "31 October, all day");
  assert.ok(p(32, 0, 30) > 0.2 && p(32, 0, 30) < 0.8, "fading out in the first hour of 1 November");
  assert.equal(p(32, 1, 0), 0);
  const l = (y, m, d, h) => cal(y, m, d, h, 0, 0, -300, 40).items.lights;
  assert.equal(l(2026, 12, 17, 23), 0);
  assert.equal(l(2026, 12, 18, 2), 1);
  assert.equal(l(2027, 1, 1, 23), 1, "New Year's Day");
  assert.equal(l(2027, 1, 2, 2), 0);
  assert.equal(l(2027, 6, 1, 12), 0);
});

await check("the New Year sparkle plays once, in the first minute of 1 January only", () => {
  const sp = (y, m, d, h, mi, s) => cal(y, m, d, h, mi, s, -300, 40).items.sparkle;
  assert.equal(sp(2026, 12, 31, 23, 59, 59), 0);
  assert.equal(sp(2027, 1, 1, 0, 0, 20), 1);
  assert.ok(sp(2027, 1, 1, 0, 1, 0) < 1e-9, "over after a minute");
  assert.equal(sp(2027, 1, 1, 12, 0, 0), 0);
  assert.equal(sp(2027, 7, 1, 0, 0, 20), 0);
  // Some glint is showing through most of the minute.
  let shown = 0;
  for (let s = 3; s < 55; s++) {
    const sc = scene(local(2027, 1, 1, 0, 0, s), -300, { lat: 40 });
    if (sc.ops.some((o) => o.k === S.POLY && o.v.length === 20 && o.v[3] > 0.2)) shown++;
  }
  assert.ok(shown > 35, `a glint in ${shown} of 52 seconds`);
});

await check("the device's own time zone decides the date", () => {
  // 03:30 UTC on 1 November: still 31 October in New York, already 1 November in Tokyo.
  const ms = Date.UTC(2026, 10, 1, 3, 30);
  assert.equal(S.calendar(ms, -240, 40).items.pumpkin, 1, "New York");
  assert.equal(S.calendar(ms, 540, 35).items.pumpkin, 0, "Tokyo");
  // Half-hour zones: India at 00:30 on 24 October is half way through the fade.
  const ind = S.calendar(Date.UTC(2026, 9, 23, 19, 0), 330, 20);
  assert.deepEqual(ind.local.slice(0, 3), [2026, 10, 24]);
  assert.ok(Math.abs(ind.items.pumpkin - 0.5) < 1e-9, `${ind.items.pumpkin}`);
});

await check("a season changes over in the first hour of the day, never at once", () => {
  const c = cal(2026, 12, 1, 0, 30, 0, -300, 40);
  assert.ok(Math.abs(c.seasons.autumn - 0.5) < 1e-9 && Math.abs(c.seasons.winter - 0.5) < 1e-9);
  const w = scene(local(2026, 12, 1, 0, 30), -300, { lat: 40 });
  assert.ok(w.ops.length > 0);
});

await check("each touch draws in its own season, and nothing else", () => {
  const kinds = (sc) => ({
    leaves: sc.ops.filter((o) => o.k === S.POLY && o.v.length === 4 + 24 && S.LEAF_RGB.some((c) => c[0] === o.v[0])).length,
    petals: sc.ops.filter((o) => o.k === S.POLY && S.PETAL_RGB.some((c) => c[0] === o.v[0] && c[1] === o.v[1])).length,
    pumpkin: sc.ops.filter((o) => o.k === S.POLY && o.v[0] === 198 && o.v[1] === 106).length,
    lights: sc.ops.filter((o) => o.k === S.LINE && o.v[1] === 70).length,
    snowman: sc.ops.filter((o) => o.k === S.DOT && o.v[3] === 236 && o.v[4] === 240).length,
    fireflies: sc.ops.filter((o) => o.k === S.DOT && o.v[3] === 236 && o.v[4] === 250).length,
    glints: sc.ops.filter((o) => o.k === S.POLY && o.v.length === 20).length,
  });
  const k = Object.fromEntries(Object.entries(MOMENTS).map(([n, [ms, tz]]) => [n, kinds(scene(ms, tz, { lat: 40.7 }))]));
  assert.ok(k.autumn.leaves >= 9 && k.autumn.pumpkin === 0 && k.autumn.petals === 0, JSON.stringify(k.autumn));
  assert.ok(k.halloween.pumpkin === 1 && k.halloween.leaves > 0, JSON.stringify(k.halloween));
  assert.ok(k.winter.snowman === 0 && k.winter.lights === 0 && k.winter.leaves === 0, JSON.stringify(k.winter));
  assert.ok(k.december.snowman === 1 && k.december.lights === 1, JSON.stringify(k.december));
  assert.ok(k.newyear.glints > 0 && k.newyear.lights === 1, JSON.stringify(k.newyear));
  assert.ok(k.spring.petals >= 5 && k.spring.leaves === 0, JSON.stringify(k.spring));
  assert.ok(k.summerDay.fireflies === 0 && k.summerNight.fireflies >= 5, JSON.stringify([k.summerDay, k.summerNight]));
  assert.ok(scene(...MOMENTS.summerDay, { lat: 40.7 }).ops.some((o) => o.k === S.GLOW), "the summer haze by day");
  // With the sun's altitude known, it decides night, not the clock.
  const [ms, tz] = MOMENTS.summerNight;
  assert.equal(kinds(scene(ms, tz, { lat: 40.7, sunAlt: 20 })).fireflies, 0);
  // Rain puts out the fireflies; real snow replaces the seasonal snowfall.
  assert.equal(kinds(scene(ms, tz, { lat: 40.7, rain: 0.8 })).fireflies, 0);
  const flakes = (o) => scene(...MOMENTS.winter, o).ops.filter((p) => p.k === S.DOT && p.v[3] === 232).length;
  assert.ok(flakes({ lat: 40.7 }) >= 10 && flakes({ lat: 40.7, snow: 0.6 }) === 0);
});

await check("Still and serious moments (hide): nothing at all", () => {
  for (const [ms, tz] of Object.values(MOMENTS)) assert.equal(scene(ms, tz, { lat: 40.7, hide: 1 }).ops.length, 0);
});

await check("an approval or an error (hold): nothing moves, no holiday piece; the still ground stays", () => {
  for (const [name, [ms, tz]] of Object.entries(MOMENTS)) {
    const held = scene(ms, tz, { lat: 40.7, hold: 1 });
    const later = scene(ms + 7000, tz, { lat: 40.7, hold: 1 });
    assert.deepEqual(held.ops, later.ops, `${name}: something moved during the hold`);
    assert.ok(!held.ops.some((o) => o.k === S.POLY && (o.v[0] === 198 || o.v.length === 20)), `${name}: a holiday piece`);
    assert.ok(!held.ops.some((o) => o.k === S.DOT && o.v[3] === 236), `${name}: the snowman or a firefly`);
  }
  const winter = scene(...MOMENTS.december, { lat: 40.7, hold: 1 });
  assert.ok(winter.ops.some((o) => o.k === S.POLY && o.v[0] === 226), "the snow bank stays");
  // The hold eases in and out over HOLD_EASE_S, from the state alone.
  assert.equal(S.holdWeight("approval", "idle", 0), 0);
  assert.equal(S.holdWeight("approval", "idle", S.HOLD_EASE_S), 1);
  assert.equal(S.holdWeight("idle", "error", S.HOLD_EASE_S), 0);
  assert.equal(S.holdWeight("error", "approval", 0), 1, "approval to error stays held");
  assert.equal(S.holdWeight("speaking", "idle", 0), 0);
  const m = {};
  assert.equal(S.follow(m, { state: "idle" }, 10).hold, 0);
  S.follow(m, { state: "approval" }, 10.1);
  assert.ok(S.follow(m, { state: "approval" }, 10.1 + S.HOLD_EASE_S).hold > 0.999);
  assert.ok(S.follow(m, { state: "approval", still: true }, 11.2).hide > 0);
});

await check("calm motion: fewer pieces, and they hold still", () => {
  for (const [name, [ms, tz]] of Object.entries(MOMENTS)) {
    const a = scene(ms, tz, { lat: 40.7, calm: true }, 10), b = scene(ms, tz, { lat: 40.7, calm: true }, 999);
    assert.deepEqual(a.ops, b.ops, name);
    const full = scene(ms, tz, { lat: 40.7 });
    if (name !== "newyear") assert.ok(a.ops.length <= full.ops.length, `${name}: ${a.ops.length} > ${full.ops.length}`);
  }
});

await check("a pure function of the clock: the same moment draws the same, both apps' leaves fall alike", () => {
  const [ms, tz] = MOMENTS.autumn;
  assert.deepEqual(scene(ms, tz, { lat: 40.7 }), scene(ms, tz, { lat: 40.7 }));
  assert.notDeepEqual(scene(ms, tz, { lat: 40.7 }, 100).ops, scene(ms, tz, { lat: 40.7 }, 101).ops);
});

await check("slow: nothing crosses the picture in under about fifteen seconds", () => {
  // Follow each moving piece's first point over a tenth of a second.
  for (const n of ["autumn", "spring", "winter", "summerNight", "december"]) {
    const [ms, tz] = MOMENTS[n];
    for (let t0 = 1000; t0 < 1060; t0 += 7.3) {
      const a = scene(ms, tz, { lat: 40.7 }, t0).ops, b = scene(ms, tz, { lat: 40.7 }, t0 + 0.1).ops;
      assert.equal(a.length, b.length);
      for (let i = 0; i < a.length; i++) {
        const p = pointsOf(a[i])[0], q = pointsOf(b[i])[0];
        const d = Math.hypot(p[0] - q[0], p[1] - q[1]);
        if (d < 0.5) assert.ok(d / 0.1 < 0.15, `${n} step ${i} moves ${(d / 0.1).toFixed(3)} a second`);
      }
    }
  }
});

await check("never flashes: every light and firefly changes brightness slowly", () => {
  for (const n of ["december", "summerNight", "newyear"]) {
    const [ms, tz] = MOMENTS[n];
    let worst = 0;
    for (let f = 0; f < 30 * 20; f++) {
      const t0 = 5000 + f / 30;
      const a = scene(ms + f * 33, tz, { lat: 40.7 }, t0).ops, b = scene(ms + f * 33 + 33, tz, { lat: 40.7 }, t0 + 1 / 30).ops;
      if (a.length !== b.length) continue;
      for (let i = 0; i < a.length; i++) {
        if (a[i].k !== b[i].k) continue;
        worst = Math.max(worst, Math.abs(alphaOf(a[i]) - alphaOf(b[i])) * 30);
      }
    }
    // Under 0.6 of full alpha per second: from dark to bright takes over a
    // second and a half - far from the three-a-second flashing threshold.
    assert.ok(worst < 0.6, `${n}: alpha changes ${worst.toFixed(3)} a second`);
  }
});

await check("behind the face: corner pieces low in the corners, the lights above the monkey's vine", () => {
  const L = S.LAYOUT;
  for (const n of ["halloween", "december"]) {
    const sc = scene(...MOMENTS[n], { lat: 40.7 });
    for (const o of sc.ops) {
      const pts = pointsOf(o);
      if (o.k === S.POLY && o.v[0] === 198) pts.forEach((p) => assert.ok(p[1] < -0.72 && p[0] > 0.6, `pumpkin ${p}`));
      if (o.k === S.DOT && o.v[3] === 236 && o.v[4] === 240) pts.forEach((p) => assert.ok(p[1] + p[2] < -0.64 && p[0] < -0.6, `snowman ${p}`));
      // The monkey's vine is drawn at about y 0.74-0.80 (docs/critters/monkey-states.png).
      if (o.k === S.LINE && o.v[1] === 70) pts.forEach((p) => assert.ok(p[1] > 0.9, `wire ${p}`));
      if (o.k === S.DOT && o.v[2] === 0.012) pts.forEach((p) => assert.ok(p[1] - p[2] > 0.84, `bulb ${p}`));
    }
  }
  assert.ok(L.LIGHTS_TOP - L.LIGHTS_SAG - 0.013 - 0.012 > 0.84);
  // Everything stays inside the frame, square, wide or tall.
  for (const [ax, ay] of [[1, 1], [1.6, 1], [1, 1.9]]) {
    for (const [n, [ms, tz]] of Object.entries(MOMENTS)) {
      for (const o of scene(ms, tz, { lat: 40.7, ax, ay }).ops) {
        for (const p of pointsOf(o)) {
          assert.ok(Math.abs(p[0]) <= ax + 0.15 && p[1] <= ay + 0.15 && p[1] >= -ay - 0.2, `${n} ${ax}x${ay}: ${p}`);
        }
      }
    }
  }
});

await check("never a state colour: glows are pale and faint, nothing matches a state's colour", () => {
  for (const [n, [ms, tz]] of Object.entries(MOMENTS)) {
    for (const o of scene(ms, tz, { lat: 40.7 }).ops) {
      const c = rgbOf(o);
      for (const [st, h] of Object.entries(STATE_HOT)) {
        const d = Math.hypot(c[0] - h[0], c[1] - h[1], c[2] - h[2]);
        assert.ok(d > 60, `${n}: ${c} is ${d.toFixed(0)} from ${st}'s ${h}`);
      }
      if (o.k === S.GLOW) {
        const mx = Math.max(...c), mn = Math.min(...c);
        assert.ok((mx - mn) / mx < 0.5, `${n}: a saturated glow ${c}`);
        assert.ok(o.v[6] <= 0.25, `${n}: a bright glow ${o.v[6]}`);
      }
      assert.ok(alphaOf(o) <= 0.9, `${n}: ${alphaOf(o)}`);
    }
  }
});

await check("short and calm: a handful of pieces at any moment", () => {
  for (const [n, [ms, tz]] of Object.entries(MOMENTS)) {
    const sc = scene(ms, tz, { lat: 40.7 });
    const moving = sc.ops.filter((o) => o.k === S.POLY || o.k === S.DOT).length;
    assert.ok(moving <= 40, `${n}: ${moving} pieces`);
  }
});

// ---- Part 2: drawing, and the face pages (needs Playwright) -------------------------

let K = null;
// Playwright first: uikit.mjs exits the process (code 2) as it loads when
// Playwright is missing, which no try/catch can catch - so load it only
// once we know Playwright is there.
try { await import("playwright"); K = await import("./uikit.mjs"); } catch (e) { K = null; }
if (!K) {
  console.log("skip  drawing and the face pages (Playwright is not installed - see tests/README.md)");
} else {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const page = await browser.newPage({ viewport: { width: 400, height: 400 } });
  await page.goto(`${base}/faces.html?mode=display&feed=parent&face=redpanda`);
  await page.waitForFunction(() => typeof drawSurface === "function", null, { timeout: 60000 });
  // Until faces.html loads season.js itself (the host integration), add it.
  if (await page.evaluate(() => typeof JarvisSeason === "undefined")) {
    await page.addScriptTag({ url: `${base}/season.js` });
  }
  await check("draw() paints the pumpkin where scene() puts it, and dims toward the ground", async () => {
    const r = await page.evaluate((ms) => {
      const px = (dim) => {
        const cv = document.createElement("canvas"); cv.width = 200; cv.height = 200;
        const g = cv.getContext("2d");
        g.fillStyle = "rgb(4,7,12)"; g.fillRect(0, 0, 200, 200);
        const sc = JarvisSeason.scene(ms, -240, ms / 1000, { lat: 40.7, calm: true });
        JarvisSeason.draw(g, 200, 200, sc, dim, [4, 7, 12]);
        // The pumpkin's middle: (0.80, FLOOR + 3.4 u) in face units.
        const x = Math.round(100 + 0.80 * 100), y = Math.round(100 - (-0.93 + 3.4 * 0.0155) * 100);
        return Array.from(g.getImageData(x, y, 1, 1).data);
      };
      return { full: px(1), half: px(0.5), none: px(0) };
    }, MOMENTS.halloween[0]);
    assert.ok(r.full[0] > 150 && r.full[0] > r.full[2] + 80, `pumpkin ${r.full}`);
    assert.ok(r.half[0] < r.full[0] - 40 && r.half[0] > 40, `half dim ${r.half}`);
    assert.ok(r.none[0] <= 8, `dim 0 is the ground: ${r.none}`);
  });
  const html = readFileSync(new URL("../src/faces.html", import.meta.url), "utf8");
  if (!/src="season\.js"/.test(html)) {
    console.log("skip  the face pages (faces.html does not draw the seasonal touches yet - the host integration)");
  } else {
    // A corner pixel's colour for one frame of the panda at `ms`, with the
    // shared switch as given.
    const sample = (animal, ms) => page.evaluate(({ animal, ms }) => {
      localStorage.setItem("jarvis.animal.v1", JSON.stringify(animal));
      window.dispatchEvent(new StorageEvent("storage", { key: "jarvis.animal.v1" }));
      Date.now = () => ms;
      const cv = document.createElement("canvas");
      cv.style.width = "240px"; cv.style.height = "240px";
      document.body.appendChild(cv);
      const s = makeSurface(THEME.redpanda, cv, null);
      s.seed = 7; s.ss = 1; sizeSurface(s);
      for (let i = 0; i < 3; i++) drawSurface(s, 0.05, "idle");
      const g = cv.getContext("2d");
      const w = cv.width;
      // The pumpkin's corner.
      const d = g.getImageData(Math.round(w * 0.86), Math.round(w * 0.93), Math.round(w * 0.06), Math.round(w * 0.04)).data;
      let r = 0; for (let i = 0; i < d.length; i += 4) r = Math.max(r, d[i]);
      cv.remove();
      return { red: r, drawn: window.__faceSeason || null };
    }, { animal, ms });
    const oct = MOMENTS.halloween[0];
    await check("off (the default): the face is drawn exactly as before", async () => {
      const off = await sample({ seasonal: false }, oct);
      assert.ok(!off.drawn || off.drawn.ops === 0, JSON.stringify(off.drawn));
    });
    await check("on: the pumpkin shows in its corner in Halloween week", async () => {
      const off = await sample({ seasonal: false }, oct);
      const on = await sample({ seasonal: true }, oct);
      assert.ok(on.drawn && on.drawn.ops > 0, "the page says it drew the touches");
      assert.ok(on.red > off.red + 60, `corner red ${off.red} -> ${on.red}`);
    });
    await check("Still hides it", async () => {
      const still = await sample({ seasonal: true, still: true }, oct);
      await page.waitForTimeout(1500);
      const later = await sample({ seasonal: true, still: true }, oct);
      assert.ok(!later.drawn || later.drawn.ops === 0 || later.red < 60, JSON.stringify([still, later]));
    });
  }
  await browser.close();
  close();
}

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
