/**
 * The sun, the moon and the weather behind the animals (sky.js) - the
 * owner's decisions of 2026-09-28, "Sun and moon behind the animals" and
 * "Weather in the animals' scene".
 *
 * Part 1 needs no browser: the astronomy against published times, and the
 * scene's promises (dark, calm, behind the animal, below the monkey's vine,
 * a pure function of the clock).
 *
 * Where the reference numbers come from:
 *   - Moon phases: NASA's published phase times (Fred Espenak's "Phases of
 *     the Moon" tables, eclipse.gsfc.nasa.gov / NASA Science): full moon
 *     2024-01-25 17:54 UTC; first quarter 2024-01-18 03:52 UTC; new moon
 *     2024-04-08 18:21 UTC (the day of the total solar eclipse); full moon
 *     2025-03-14 06:55 UTC (the total lunar eclipse).
 *   - Sunrise and sunset in London on the 2024 June solstice: 04:43 and
 *     21:21 British Summer Time (03:43 and 20:21 UTC), as published by
 *     timeanddate.com and the UK Met Office.
 *   - The other rise and set times: PyEphem 4.2.1 (Brandon Rhodes'
 *     Python wrapper of the XEphem high-precision code), computed
 *     2026-09-28 with no atmosphere model other than the standard -0:34
 *     horizon: an independent program, not this file's formulas.
 *     Low-precision formulas are allowed 2 minutes for the sun and 6 for the
 *     moon (the Astronomical Almanac's own stated accuracy is about 0.3
 *     degree for the moon, a few minutes of rising time).
 *
 * Part 2 (a browser, Playwright) - the face pages draw it: "Show the sun and
 * moon" in this computer's store reaches the Widget's face frame, the sky is
 * behind the animal and dims with it, and it draws nothing when off.
 *
 *     node tests/sky.mjs
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const S = require("../src/sky.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const utc = (y, mo, d, h, mi) => Date.UTC(y, mo - 1, d, h || 0) + (mi || 0) * 60000;
const minutes = (a, b) => Math.abs(a - b) / 60000;

// ---- Part 1: the maths ---------------------------------------------------------

await check("moon phases land on NASA's published times", () => {
  const full = S.moon(utc(2024, 1, 25, 17, 54), 0, 0);
  assert.ok(full.fraction > 0.995, `full moon 2024-01-25: ${full.fraction}`);
  assert.equal(S.PHASES[full.phase], "Full moon");
  const nm = S.moon(utc(2024, 4, 8, 18, 21), 0, 0);
  assert.ok(nm.fraction < 0.005, `new moon 2024-04-08: ${nm.fraction}`);
  assert.equal(S.PHASES[nm.phase], "New moon");
  const fq = S.moon(utc(2024, 1, 18, 3, 52), 0, 0);
  assert.ok(Math.abs(fq.fraction - 0.5) < 0.01, `first quarter: ${fq.fraction}`);
  assert.equal(S.PHASES[fq.phase], "First quarter");
  assert.equal(fq.waxing, true);
  const f2 = S.moon(utc(2025, 3, 14, 6, 55), 0, 0);
  assert.ok(f2.fraction > 0.995, `full moon 2025-03-14: ${f2.fraction}`);
  // Two days after full: waning gibbous; five days before new: waning crescent.
  assert.equal(S.PHASES[S.moon(utc(2024, 1, 28, 12), 0, 0).phase], "Waning gibbous");
  assert.equal(S.PHASES[S.moon(utc(2024, 4, 4, 12), 0, 0).phase], "Waning crescent");
  assert.equal(S.PHASES[S.moon(utc(2024, 4, 11, 12), 0, 0).phase], "Waxing crescent");
});

await check("London's solstice sunrise and sunset (03:43 and 20:21 UTC)", () => {
  const r = S.nextRiseSet("sun", utc(2024, 6, 21, 0), 51.48, 0.0);
  assert.ok(minutes(r.rise, utc(2024, 6, 21, 3, 43)) < 2, new Date(r.rise).toISOString());
  assert.ok(minutes(r.set, utc(2024, 6, 21, 20, 21)) < 2, new Date(r.set).toISOString());
});

// [place, lat, lon, from, sunrise, sunset, moonrise, moonset] - PyEphem 4.2.1.
const EPHEM = [
  ["New York", 40.71, -74.01, utc(2024, 12, 21, 5),
    utc(2024, 12, 21, 12, 16.8), utc(2024, 12, 21, 21, 32.1), utc(2024, 12, 22, 4, 13.1), utc(2024, 12, 21, 16, 28.3)],
  ["Denver", 39.74, -104.99, utc(2025, 3, 20, 7),
    utc(2025, 3, 20, 13, 2.8), utc(2025, 3, 21, 1, 12.4), utc(2025, 3, 21, 7, 54.8), utc(2025, 3, 20, 15, 55.1)],
  ["Sydney", -33.87, 151.21, utc(2024, 6, 20, 14),
    utc(2024, 6, 20, 21, 0.1), utc(2024, 6, 21, 6, 53.9), utc(2024, 6, 21, 5, 49.9), utc(2024, 6, 20, 20, 8.9)],
  ["Singapore", 1.35, 103.82, utc(2025, 9, 1, 16),
    utc(2025, 9, 1, 23, 0.4), utc(2025, 9, 2, 11, 8.4), utc(2025, 9, 2, 6, 32.7), utc(2025, 9, 1, 17, 58.7)],
];
for (const [name, lat, lon, from, sr, ss, mr, ms] of EPHEM) {
  await check(`${name}: rises and sets agree with an independent program`, () => {
    const s = S.nextRiseSet("sun", from, lat, lon);
    const m = S.nextRiseSet("moon", from, lat, lon);
    assert.ok(minutes(s.rise, sr) < 2, `sunrise ${new Date(s.rise).toISOString()}`);
    assert.ok(minutes(s.set, ss) < 2, `sunset ${new Date(s.set).toISOString()}`);
    assert.ok(minutes(m.rise, mr) < 6, `moonrise ${new Date(m.rise).toISOString()}`);
    assert.ok(minutes(m.set, ms) < 6, `moonset ${new Date(m.set).toISOString()}`);
  });
}

await check("a polar night has no sunrise, a polar day no sunset", () => {
  const night = S.nextRiseSet("sun", utc(2024, 12, 21, 0), 78.2, 15.6);   // Longyearbyen
  assert.equal(night.rise, null); assert.equal(night.up, false);
  const day = S.nextRiseSet("sun", utc(2024, 6, 21, 0), 78.2, 15.6);
  assert.equal(day.set, null); assert.equal(day.up, true);
});

await check("the moon's bright side faces the sun on screen, in both halves of the world", () => {
  // A waxing crescent after sunset: the sun has set in the west. New York
  // faces south (west on the right); Sydney faces north (west on the left).
  const ny = S.scene(utc(2024, 1, 14, 23), 0, { lat: 40.71, lon: -74.01 }, null, {}).moon;
  assert.ok(ny.bx > 0.3 && ny.by < 0, `New York ${ny.bx}, ${ny.by}`);
  const syd = S.scene(utc(2024, 1, 14, 9, 30), 0, { lat: -33.87, lon: 151.21 }, null, {}).moon;
  assert.ok(syd.bx < -0.3 && syd.by < 0, `Sydney ${syd.bx}, ${syd.by}`);
});

await check("the sun rises on the east side of the frame and sets on the west", () => {
  const dawn = S.scene(utc(2024, 6, 21, 3, 50), 0, { lat: 51.48, lon: 0 }, null, {}).sun;
  const noon = S.scene(utc(2024, 6, 21, 12, 0), 0, { lat: 51.48, lon: 0 }, null, {}).sun;
  const dusk = S.scene(utc(2024, 6, 21, 20, 10), 0, { lat: 51.48, lon: 0 }, null, {}).sun;
  assert.ok(dawn.x < -0.6 && dusk.x > 0.6, `${dawn.x} .. ${dusk.x}`);
  assert.ok(Math.abs(noon.x) < 0.1 && noon.y > 0.85, `noon ${noon.x}, ${noon.y}`);
  assert.ok(dawn.alpha > 0.3 && noon.alpha > 0.99, "visible while up");
  const night = S.scene(utc(2024, 6, 21, 23, 59), 0, { lat: 51.48, lon: 0 }, null, {}).sun;
  assert.ok(night.alpha < 0.001, "gone at night");
  // Southern half: rising on the RIGHT.
  const sydDawn = S.scene(utc(2024, 6, 20, 21, 10), 0, { lat: -33.87, lon: 151.21 }, null, {}).sun;
  assert.ok(sydDawn.x > 0.6, `Sydney dawn ${sydDawn.x}`);
});

await check("the sun and moon stay in the frame, and at the top sit above the heads and the monkey's vine", () => {
  // The monkey's vine is drawn at about y 0.74-0.80 (docs/critters/monkey-states.png).
  let top = -9, apexLow = 9;
  for (let h = 0; h < 24 * 30; h += 1) {
    for (const lat of [-60, -20, 0, 20, 45, 70]) {
      const sc = S.scene(utc(2025, 1, 1) + h * 3600000, 0, { lat, lon: 10 }, null, {});
      for (const b of [sc.sun, sc.moon]) {
        if (b.alpha <= 0.01) continue;
        top = Math.max(top, b.y + b.r);
        if (Math.abs(b.x) < 0.1) apexLow = Math.min(apexLow, b.y - b.r);
      }
    }
  }
  assert.ok(top < 1, `highest edge ${top}`);
  assert.ok(apexLow > 0.8, `at the top of the arc the lowest edge is ${apexLow}`);
});

await check("the sky tint stays dark: at most about a fifth over the ground", () => {
  for (let a = -30; a <= 90; a += 1) {
    const t = S.tintAt(a);
    assert.ok(t[3] <= 0.2 + 1e-9 && t[7] <= 0.2 + 1e-9, `alt ${a}: ${t}`);
    // Over the app's black ground, the brightest channel stays under 50/255.
    for (const [c, al] of [[t.slice(0, 3), t[3]], [t.slice(4, 7), t[7]]]) {
      assert.ok(Math.max(...c) * al < 50, `alt ${a}: ${c} at ${al}`);
    }
  }
});

await check("the weather is a pure function of the clock: same inputs, same rain", () => {
  const w = { rain: 0.7, snow: 0, wind: 0.5, cloud: 0.8, fog: 0, dir: -1 };
  const a = S.scene(utc(2025, 1, 1), 1234.5, null, w, {});
  const b = S.scene(utc(2025, 1, 1), 1234.5, null, w, {});
  assert.deepEqual(a, b);
  const c = S.scene(utc(2025, 1, 1), 1235.5, null, w, {});
  assert.notDeepEqual(a.rain, c.rain);
  assert.ok(a.rain.length >= 8 && a.clouds.length >= 2, "rain and clouds drawn");
  assert.equal(a.sun, null, "no place: no sun or moon, only weather");
});

await check("reduced motion: the rain, snow, clouds and wind hold still", () => {
  const w = { rain: 0.6, snow: 0.6, wind: 0.8, cloud: 0.7, fog: 0.2, dir: 1 };
  const a = S.scene(utc(2025, 1, 1), 10, null, w, { calm: true });
  const b = S.scene(utc(2025, 1, 1), 99, null, w, { calm: true });
  assert.deepEqual(a.rain, b.rain); assert.deepEqual(a.snow, b.snow);
  assert.deepEqual(a.clouds, b.clouds); assert.deepEqual(a.wisps, b.wisps);
});

await check("the weather moves gently: snow takes over ten seconds to fall across, clouds minutes", () => {
  const w = { rain: 0, snow: 1, wind: 1, cloud: 1, fog: 0, dir: 1 };
  const a = S.scene(0, 100, null, w, {}), b = S.scene(0, 100.1, null, w, {});
  for (let i = 0; i < a.snow.length; i++) {
    const dy = Math.abs(a.snow[i][1] - b.snow[i][1]);
    if (dy < 1) assert.ok(dy / 0.1 < 0.2, `flake ${i} falls ${dy / 0.1} a second`);
  }
  for (let i = 0; i < a.clouds.length; i++) {
    const dx = Math.abs(a.clouds[i][0] - b.clouds[i][0]);
    if (dx < 1) assert.ok(dx / 0.1 < 0.02, `cloud ${i} drifts ${dx / 0.1} a second`);
  }
});

await check("the moon's lit shape: nothing at new, a half at quarter, all at full", () => {
  const area = (pts) => Math.abs(pts.reduce((s, p, i) => {
    const q = pts[(i + 1) % pts.length];
    return s + p[0] * q[1] - q[0] * p[1];
  }, 0)) / 2;
  assert.ok(area(S.moonOutline(0, 1, 0, 48)) < 0.01);
  assert.ok(Math.abs(area(S.moonOutline(0.5, 1, 0, 48)) / Math.PI - 0.5) < 0.01);
  assert.ok(Math.abs(area(S.moonOutline(1, 0, 1, 48)) / Math.PI - 1) < 0.01);
  // The bright side is the side it was told: lit points are on +x.
  const cres = S.moonOutline(0.2, 1, 0, 24);
  assert.ok(cres.every((p) => p[0] > -0.61), "a crescent sits on its bright side");
});

await check("what the face pages read: off draws nothing; a stale shower is dropped", () => {
  assert.equal(S.liveInput(null, 0), null);
  assert.equal(S.liveInput({ show: false, place: { lat: 40, lon: -74 } }, 0), null);
  const on = S.liveInput({ show: true, place: { lat: 40.71, lon: -74.01 } }, 0);
  assert.deepEqual(on.place, { lat: 40.7, lon: -74 });
  const now = utc(2025, 1, 1);
  const fresh = S.liveInput({ show: false, weather: { now: { rain: 0.5, at: now / 1000 - 600 } } }, now);
  assert.equal(fresh.weather.rain, 0.5);
  assert.equal(fresh.place, null, "weather without the sun and moon");
  const stale = S.liveInput({ show: false, weather: { now: { rain: 0.5, at: now / 1000 - 4 * 3600 } } }, now);
  assert.equal(stale, null);
  // Nonsense is refused, never drawn.
  assert.equal(S.liveInput({ show: true, place: { lat: 400, lon: 0 } }, 0), null);
  assert.equal(S.cleanWeather({ rain: 7, dir: 3 }).rain, 1);
});

// ---- Part 2: on the face pages (needs Playwright) -------------------------------------

let K = null;
// Playwright first: uikit.mjs exits the process (code 2) as it loads when
// Playwright is missing, which no try/catch can catch - so load it only
// once we know Playwright is there.
try { await import("playwright"); K = await import("./uikit.mjs"); } catch (e) { K = null; }
if (!K) {
  console.log("skip  the face pages (Playwright is not installed - see tests/README.md)");
} else {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  // Draws one frame of the panda at a fixed moment and returns the average
  // colour of a corner (sky) and of the middle (the animal).
  async function sample(page, doc, state = "idle") {
    return page.evaluate(({ doc, key, state }) => {
      localStorage.setItem(key, JSON.stringify(doc));
      window.dispatchEvent(new StorageEvent("storage", { key }));
      const cv = document.createElement("canvas");
      cv.style.width = "240px"; cv.style.height = "240px";
      document.body.appendChild(cv);
      const s = makeSurface(THEME.redpanda, cv, null);
      s.seed = 7; s.ss = 1; sizeSurface(s);
      for (let i = 0; i < 3; i++) drawSurface(s, 0.05, state);
      const g = cv.getContext("2d");
      const px = (x, y, n) => {
        const d = g.getImageData(x, y, n, n).data;
        let r = 0, gg = 0, b = 0;
        for (let i = 0; i < d.length; i += 4) { r += d[i]; gg += d[i + 1]; b += d[i + 2]; }
        const c = d.length / 4;
        return [r / c, gg / c, b / c];
      };
      const w = cv.width;
      const out = { corner: px(Math.round(w * 0.04), Math.round(w * 0.04), Math.round(w * 0.1)),
        sky: window.__faceSky || null };
      cv.remove();
      return out;
    }, { doc, key: "jarvis.sky.v1", state });
  }
  const page = await browser.newPage({ viewport: { width: 400, height: 400 } });
  await page.goto(`${base}/faces.html?mode=display&feed=parent&face=redpanda`);
  await page.waitForFunction(() => typeof drawSurface === "function" && typeof JarvisSky !== "undefined",
    null, { timeout: 60000 });
  // Noon in London at midsummer: a day sky.
  await page.evaluate(() => { const real = Date.now; Date.now = () => Date.UTC(2024, 5, 21, 12, 0); window.__realNow = real; });
  await check("off: the face is drawn exactly as before (no sky)", async () => {
    const off = await sample(page, { show: false });
    assert.equal(off.sky, null);
  });
  await check("on: a day sky is drawn behind the panda (the corner is tinted blue)", async () => {
    const off = await sample(page, { show: false });
    const on = await sample(page, { show: true, place: { lat: 51.5, lon: -0.1 } });
    assert.ok(on.sky && on.sky.drawn === true, "the page says it drew the sky");
    assert.ok(on.corner[2] > off.corner[2] + 4, `blue ${off.corner[2]} -> ${on.corner[2]}`);
    assert.ok(Math.max(...on.corner) < 60, `still dark: ${on.corner}`);
  });
  await check("the sky dims with the animal on standby", async () => {
    const idle = await sample(page, { show: true, place: { lat: 51.5, lon: -0.1 } }, "idle");
    const sb = await sample(page, { show: true, place: { lat: 51.5, lon: -0.1 } }, "standby");
    assert.ok(sb.corner[2] < idle.corner[2] - 1, `standby ${sb.corner[2]} vs idle ${idle.corner[2]}`);
  });
  await check("rain from the PC is drawn, and a face that is not an animal has no sky", async () => {
    const now = Date.UTC(2024, 5, 21, 12, 0) / 1000;
    const r = await sample(page, { show: false, weather: { now: { rain: 0.8, cloud: 0.9, at: now - 60 } } });
    assert.ok(r.sky && r.sky.rain > 0, "rain streaks drawn");
    const arc = await page.evaluate(() => {
      window.__faceSky = null;
      const cv = document.createElement("canvas");
      cv.style.width = "200px"; cv.style.height = "200px";
      document.body.appendChild(cv);
      const s = makeSurface(THEME.arc, cv, null); sizeSurface(s);
      drawSurface(s, 0.05, "idle");
      cv.remove();
      return window.__faceSky;
    });
    assert.equal(arc, null);
  });
  // Settings -> Appearance -> "Sun, moon and weather", with a fake PC.
  const VIEW = (over) => Object.assign({
    available: true, title: "Sun, moon and weather", show: false,
    show_label: "Show the sun and moon behind the face", show_detail: "detail",
    place: null, place_label: "Your town", place_detail: "Type it once on the PC.",
    place_none: "No town yet.", forget_label: "Forget my town", can_set_place: true,
    weather: { source: "off", now: null, status: "Off.", waiting: false, last: null,
      label: "Weather behind the face", detail: "Rain, snow or wind.",
      choices: [{ id: "off", label: "Off (default)", why: "No weather is drawn." },
        { id: "home_assistant", label: "My Home Assistant", why: "home" },
        { id: "open_meteo", label: "Open-Meteo (online)", why: "online" }] },
  }, over);
  const sp = await K.open(browser, base, "settings.html", {}, { width: 900, height: 1200 });
  await sp.evaluate((views) => {
    window.__skySent = [];
    let v = views.off;
    const real = window.__TAURI__.core.invoke;
    window.__TAURI__.core.invoke = async (cmd, args) => {
      if (cmd === "get_sky") return v;
      if (cmd === "set_sky") {
        window.__skySent.push(args.change);
        if (args.change.place) v = views.placed;
        if (args.change.show === true) v = Object.assign({}, v, { show: true });
        return { ok: true, said: "Set.", view: v };
      }
      return real(cmd, args);
    };
    document.dispatchEvent(new Event("visibilitychange"));
  }, { off: VIEW({}), placed: VIEW({ place: { name: "Denver, Colorado, United States", lat: 39.7, lon: -105 } }) });
  await check("Settings shows the section in the PC's words, off by default", async () => {
    await sp.waitForFunction(() => !document.getElementById("sky-body").hidden, null, { timeout: 10000 });
    assert.equal(await sp.isChecked("#sky-show"), false);
    assert.equal(await sp.textContent("#sky-show-label"), "Show the sun and moon behind the face");
    assert.equal(await sp.isChecked('input[name="sky-weather"][value="off"]'), true);
  });
  await check("typing a town sends ONE change, and the faces' copy is kept", async () => {
    await sp.fill("#sky-place", "Denver");
    await sp.click("#sky-place-set");
    await sp.waitForFunction(() => /Denver/.test(document.getElementById("sky-place-now").textContent));
    const sent = await sp.evaluate(() => window.__skySent);
    assert.deepEqual(sent, [{ place: "Denver" }]);
    const stored = await sp.evaluate(() => JSON.parse(localStorage.getItem("jarvis.sky.v1")));
    assert.deepEqual(stored.place, { lat: 39.7, lon: -105 }, "only the rounded position, never the name");
    assert.ok(!JSON.stringify(stored).includes("Denver"));
    assert.match(await sp.textContent("#sky-today"), /^Sun rises \d\d:\d\d|^Sun sets|Moon:/);
  });
  await sp.close();
  await browser.close();
  close();
}

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
