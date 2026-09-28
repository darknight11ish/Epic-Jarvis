/**
 * Seasonal touches behind the character faces (the owner's decision of
 * 2026-09-28, CLAUDE.md "New animal behaviours": "seasonal touches from the
 * date (off by default)", one switch in the animal options, changeable by
 * asking Jarvis; the switch is `seasonal` in animal-shared.js).
 *
 * WHAT THIS FILE IS. Pure maths plus one drawing function:
 *   - which season it is and which of a few gentle holiday touches are due,
 *     from the device's own date and time (and, for the hemisphere, the sign
 *     of the sky's saved latitude - north when no town is set);
 *   - a SCENE: those touches laid out behind the face as a flat list of
 *     drawing steps (soft glows, dots, filled shapes, one thin line), as
 *     plain numbers;
 *   - `draw(g, w, h, scene)`, which paints a scene on a 2D canvas.
 * The phone runs a line-for-line Kotlin copy (`jarvis-client/.../face/
 * Season.kt`, drawn by `SeasonDraw.kt`). They share ANSWERS, not code:
 * `tools/gen_season.py` runs this file under node and writes
 * `season-golden.json`, and the phone's `SeasonTest` fails if the Kotlin
 * copy disagrees - the same pattern as the sky (sky.js, gen_sky.py).
 *
 * NOTHING GOES ONLINE, NOTHING IS STORED. The date, the time and the time
 * zone are the device's own clock; the hemisphere is one sign bit of the
 * place the sky already keeps. Nothing here is saved or sent anywhere.
 *
 * WHAT IS DRAWN - a short list on purpose, every piece small and calm:
 *   Seasons (meteorological, by whole months; the southern half of the world
 *   six months on):
 *     autumn  - a few leaves drifting down; fallen leaves gather in the
 *               corners as the season goes on
 *     winter  - light snowfall, a soft snow bank along the floor, and from
 *               mid-winter (15 December - 31 January in the north) a tiny
 *               snowman in the left corner
 *     spring  - blossom petals drifting on a light breeze
 *     summer  - a faint warm haze by day, a few fireflies at dusk and night
 *   Holidays (by the calendar, both halves of the world, nothing religious):
 *     a plain pumpkin in the right corner, 24-31 October;
 *     a string of soft lights along the top, 18 December - 1 January;
 *     a few slow sparkles once, in the first minute of 1 January.
 * Nothing flashes: every change of brightness is a slow sine (the lights
 * breathe over 9 seconds, a firefly over 5-8), and every colour is muted,
 * kept away from the state colours (no strong red, amber, violet or cyan),
 * so nothing reads as a state.
 *
 * WHEN IT SHOWS (the owner's rules for the new behaviours, CLAUDE.md
 * 2026-09-28: "Still and serious moments switch every one off; calm makes
 * them smaller ... never anything cute during an approval or error"):
 *   - `hide` 0..1 - "Keep the animal still" or a serious moment: everything
 *     fades out (the host eases it, about a second).
 *   - `hold` 0..1 - an approval or an error: everything that moves and every
 *     holiday piece fades out; only the still ground stays (the snow bank,
 *     the fallen leaves, the summer haze). See holdWeight().
 *   - `calm` - reduced motion: fewer pieces, all held still (like the sky's
 *     weather); a firefly or a light keeps one steady brightness.
 *   - standby: dims with the face (the host's dim covers it, as the sky).
 *   - A season or a holiday starts and ends at local midnight, faded over the
 *     first hour of the day, so nothing pops.
 *
 * Coordinates: the face's own units, 1 = half its shorter side, x to the
 * right, y UP, (0, 0) the middle - the sky's units (sky.js). Colours are
 * [r, g, b] 0..255 with a separate alpha 0..1.
 */
(function (root) {
  "use strict";

  const DAY_MS = 86400000;
  const TAU = 6.2832;

  // ---- Small helpers (the Kotlin copy has the same, in the same order) -----

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  function smoothstep(a, b, x) {
    const k = clamp((x - a) / (b - a), 0, 1);
    return k * k * (3 - 2 * k);
  }
  const mix = (a, b, k) => a + (b - a) * k;
  const frac = (x) => x - Math.floor(x);
  /** The animals' own hash (critter-pose.js hash01, sky.js hash01), 0..1. */
  function hash01(n) {
    let x = (n | 0) ^ 0x5bd1e995;
    x = Math.imul(x ^ (x >>> 15), 0x2c1b3c6d);
    x = Math.imul(x ^ (x >>> 12), 0x297a2d39);
    x ^= x >>> 15;
    return (x >>> 0) / 4294967296;
  }

  // ---- The calendar -----------------------------------------------------------

  /** Days since 1970-01-01 of a calendar date (proleptic Gregorian;
   *  H. Hinnant's "days_from_civil"). */
  function daysFromCivil(y, m, d) {
    const yy = m <= 2 ? y - 1 : y;
    const era = Math.floor(yy / 400);
    const yoe = yy - era * 400;
    const doy = Math.floor((153 * (m > 2 ? m - 3 : m + 9) + 2) / 5) + d - 1;
    const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
    return era * 146097 + doe - 719468;
  }

  /** The calendar date of a day number: [year, month 1-12, day 1-31]. */
  function civilFromDays(days) {
    const z = days + 719468;
    const era = Math.floor(z / 146097);
    const doe = z - era * 146097;
    const yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365);
    const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
    const mp = Math.floor((5 * doy + 2) / 153);
    const d = doy - Math.floor((153 * mp + 2) / 5) + 1;
    const m = mp < 10 ? mp + 3 : mp - 9;
    return [yoe + era * 400 + (m <= 2 ? 1 : 0), m, d];
  }

  /**
   * The device's local moment: `ms` (UTC milliseconds) plus the device's
   * offset from UTC at that moment, in minutes (east positive - JavaScript's
   * `-new Date(ms).getTimezoneOffset()`, Java's `TimeZone.getOffset(ms) /
   * 60000`). {t: local days since 1970 with the time of day as a fraction,
   * y, m, d, hour}.
   */
  function localOf(ms, tzMin) {
    const lms = ms + tzMin * 60000;
    const days = Math.floor(lms / DAY_MS);
    const c = civilFromDays(days);
    const t = lms / DAY_MS;
    return { t, y: c[0], m: c[1], d: c[2], hour: (t - days) * 24 };
  }

  /** How long a season or a holiday takes to fade in (after its first
   *  midnight) and out (after its last), in days: one hour. */
  const FADE_DAYS = 1 / 24;

  /**
   * How far a yearly window is showing at local moment `L`, 0..1, and how
   * many days it has been showing: from 00:00 on (sm, sd) up to 00:00 on
   * (em, ed) - the end day itself is not in it - each edge faded over the
   * first hour of its day. A window may run over New Year (18 Dec - 2 Jan).
   */
  function windowAt(L, sm, sd, em, ed) {
    let ys = L.y;
    let s = daysFromCivil(ys, sm, sd);
    if (s > L.t) { ys -= 1; s = daysFromCivil(ys, sm, sd); }
    let e = daysFromCivil(ys, em, ed);
    if (e <= s) e = daysFromCivil(ys + 1, em, ed);
    const w = smoothstep(0, FADE_DAYS, L.t - s) * (1 - smoothstep(0, FADE_DAYS, L.t - e));
    return { w, day: L.t - s };
  }

  /** The seasons, northern half of the world: [name, from month, to month].
   *  The southern half is six months on. */
  const SEASONS = [["spring", 3, 6], ["summer", 6, 9], ["autumn", 9, 12], ["winter", 12, 3]];
  /** The holidays and the mid-winter snowman: [name, month, day, to month,
   *  to day (not included)]. The snowman's dates are the north's; the
   *  south's are six months on. */
  const HOLIDAYS = [["pumpkin", 10, 24, 11, 1], ["lights", 12, 18, 1, 2]];
  const SNOWMAN = [12, 15, 2, 1];
  /** The New Year sparkle: seconds after local midnight on 1 January. */
  const SPARKLE_S = 60;

  const shift6 = (m) => ((m + 5) % 12) + 1;

  /** Which seasons and touches are showing, and how far (0..1 each). */
  function calendar(ms, tzMin, lat) {
    const L = localOf(ms, tzMin);
    const south = typeof lat === "number" && isFinite(lat) && lat < 0;
    const out = { south, local: [L.y, L.m, L.d, L.hour], seasons: {}, day: {}, items: {} };
    for (const [name, a, b] of SEASONS) {
      const w = windowAt(L, south ? shift6(a) : a, 1, south ? shift6(b) : b, 1);
      out.seasons[name] = w.w;
      out.day[name] = w.day;
    }
    for (const [name, sm, sd, em, ed] of HOLIDAYS) out.items[name] = windowAt(L, sm, sd, em, ed).w;
    const sn = SNOWMAN;
    out.items.snowman = windowAt(L, south ? shift6(sn[0]) : sn[0], sn[1], south ? shift6(sn[2]) : sn[2], sn[3]).w;
    const sec = (L.t - daysFromCivil(L.y, 1, 1)) * 86400;
    out.sparkleSec = sec;
    out.items.sparkle = smoothstep(0, 3, sec) * (1 - smoothstep(SPARKLE_S - 6, SPARKLE_S, sec));
    // The one season showing most (for tests and the page's readout).
    let best = "spring", bw = -1;
    for (const [name] of SEASONS) if (out.seasons[name] > bw) { bw = out.seasons[name]; best = name; }
    out.season = best;
    return out;
  }

  // ---- The layout ---------------------------------------------------------------

  const LAYOUT = {
    FLOOR: -0.93,      // where the corner pieces stand: the animals' floor
    LEFT_X: -0.80,     // the snowman's corner
    RIGHT_X: 0.80,     // the pumpkin's corner
    LIGHTS_TOP: 0.965, // the string's hooks: above every head and the monkey's vine (about 0.74-0.80)
    LIGHTS_SAG: 0.055,
  };

  // Muted colours, kept away from the state colours.
  const LEAF_RGB = [[196, 100, 52], [188, 150, 70], [172, 82, 48], [186, 120, 56]];
  const PETAL_RGB = [[248, 206, 218], [242, 186, 204], [250, 228, 234]];
  const BULB_RGB = [[255, 232, 196], [236, 168, 176], [168, 214, 170], [180, 184, 228], [255, 232, 196], [240, 212, 150]];
  const SNOW_RGB = [232, 238, 246];

  /** Seconds an approval or an error takes to hide the moving pieces, and
   *  to bring them back after. */
  const HOLD_EASE_S = 0.8;

  /**
   * How far the "attentive" hold is on, 0..1, from the state shown, the one
   * before it and the seconds since the change: an approval or an error
   * holds (`hold` is "approval" or "error"). Pure, so both apps agree.
   */
  function holdWeight(state, prevState, since) {
    const isH = state === "approval" || state === "error";
    const wasH = prevState === "approval" || prevState === "error";
    const e = smoothstep(0, HOLD_EASE_S, since);
    if (isH && wasH) return 1;
    if (isH) return e;
    if (wasH) return 1 - e;
    return 0;
  }

  // ---- Shapes (unit outlines, turned and placed by place()) ---------------------

  /** A leaf, long axis along x: half-length 1, half-width 1; 12 points. */
  function leafShape() {
    const pts = [];
    for (let i = 0; i <= 6; i++) {
      const u = -1 + i / 3;
      pts.push([u, (1 - u * u) * (1 + 0.25 * u)]);
    }
    for (let i = 5; i >= 1; i--) {
      const u = -1 + i / 3;
      pts.push([u, -(1 - u * u) * (1 + 0.25 * u)]);
    }
    return pts;
  }

  /** A petal, base at -1, rounded tip toward +1; 12 points. */
  function petalShape() {
    const pts = [];
    for (let i = 0; i <= 6; i++) {
      const s = i / 6;
      pts.push([2 * s - 1, Math.sin(Math.PI * Math.pow(s, 0.65))]);
    }
    for (let i = 5; i >= 1; i--) {
      const s = i / 6;
      pts.push([2 * s - 1, -Math.sin(Math.PI * Math.pow(s, 0.65))]);
    }
    return pts;
  }

  /** A four-pointed glint, radius 1, thin waist; 8 points. */
  function glintShape() {
    const pts = [];
    for (let i = 0; i < 8; i++) {
      const a = Math.PI / 2 - i * Math.PI / 4;
      const r = i % 2 === 0 ? 1 : 0.26;
      pts.push([r * Math.cos(a), r * Math.sin(a)]);
    }
    return pts;
  }

  /** An ellipse as n points. */
  function ellipse(cx, cy, rx, ry, n) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const a = TAU * i / n;
      pts.push([cx + rx * Math.cos(a), cy + ry * Math.sin(a)]);
    }
    return pts;
  }

  const LEAF = leafShape();
  const PETAL = petalShape();
  const GLINT = glintShape();

  /** A unit shape scaled by (sx, sy), turned by `ang` (radians, counter-
   *  clockwise, y up) and moved to (x, y): a flat [x0, y0, x1, y1, ...]. */
  function place(shape, x, y, sx, sy, ang) {
    const c = Math.cos(ang), s = Math.sin(ang);
    const out = [];
    for (const p of shape) {
      const u = p[0] * sx, v = p[1] * sy;
      out.push(x + u * c - v * s, y + u * s + v * c);
    }
    return out;
  }
  const flat = (pts) => pts.reduce((a, p) => { a.push(p[0], p[1]); return a; }, []);

  // ---- The scene ---------------------------------------------------------------------

  /** Drawing steps. k: 0 a soft glow (x, y, r, R, G, B, a: `a` at the
   *  centre, nothing at r); 1 a dot (x, y, r, R, G, B, a); 2 a filled shape
   *  (R, G, B, a, then x0, y0, x1, y1, ...); 3 a thin line (width, R, G, B,
   *  a, then the points). A step with almost no alpha is left out. */
  const GLOW = 0, DOT = 1, POLY = 2, LINE = 3;
  const MIN_A = 0.002;

  /**
   * The seasonal touches for a moment: pure numbers, no drawing.
   *
   * @param ms     wall-clock milliseconds since 1970 (UTC)
   * @param tzMin  the device's offset from UTC now, minutes, east positive
   * @param t      seconds for the movement (the same wall clock in seconds,
   *               so both apps' leaves fall alike)
   * @param opts   {lat: the sky's saved latitude or null (north);
   *               calm; hide 0..1; hold 0..1; ax, ay: the frame's half-width
   *               and half-height in face units (1 for a square); sunAlt:
   *               the sun's altitude for the saved place, or null (then the
   *               clock decides day and night); snow, rain: the weather the
   *               sky is drawing, 0..1 (real snow replaces the seasonal
   *               snowfall; rain puts out the fireflies and the haze)}
   */
  function scene(ms, tzMin, t, opts) {
    const o = opts || {};
    const ax = typeof o.ax === "number" && o.ax > 0 ? o.ax : 1;
    const ay = typeof o.ay === "number" && o.ay > 0 ? o.ay : 1;
    const num = (v) => (typeof v === "number" && isFinite(v) ? clamp(v, 0, 1) : 0);
    const calm = o.calm === true;
    const all = 1 - num(o.hide);
    const moving = all * (1 - num(o.hold));
    const snowW = num(o.snow), rainW = num(o.rain);
    const lat = typeof o.lat === "number" && isFinite(o.lat) ? o.lat : null;
    const sunAlt = typeof o.sunAlt === "number" && isFinite(o.sunAlt) ? o.sunAlt : null;
    const C = calendar(ms, tzMin, lat);
    const S = C.seasons, I = C.items;
    const L = LAYOUT;
    const tt = calm ? 0 : t;
    const hour = C.local[3];
    const ops = [];
    const put = (k, v) => ops.push({ k, v });
    const out = { ax, ay, season: C.season, south: C.south, local: C.local, seasons: S, items: I, ops };
    if (all <= 0) return out;
    const fall = 2 * ay + 0.2;

    // Summer by day: a faint warm haze high on one side.
    const dayW = sunAlt !== null ? smoothstep(4, 14, sunAlt)
      : Math.min(smoothstep(8, 10, hour), 1 - smoothstep(17, 19, hour));
    const hazeA = 0.07 * S.summer * dayW * (1 - smoothstep(0.1, 0.4, rainW)) * all;
    if (hazeA > MIN_A) put(GLOW, [0.55 * ax, 0.72, 1.1, 255, 226, 178, hazeA]);

    // Winter: a soft snow bank along the floor, higher in the corners.
    const bankA = S.winter * all;
    if (bankA > MIN_A) {
      const pts = [];
      const n = 24;
      for (let i = 0; i <= n; i++) {
        const x = -ax + 2 * ax * i / n;
        const bump = Math.exp(-Math.pow((x - L.LEFT_X) / 0.30, 2)) + 0.8 * Math.exp(-Math.pow((x - L.RIGHT_X) / 0.28, 2));
        pts.push(x, L.FLOOR + 0.015 + 0.07 * bump);
      }
      pts.push(ax, -ay - 0.05, -ax, -ay - 0.05);
      put(POLY, [226, 234, 242, 0.13 * bankA].concat(pts));
      // Its lit top edge, a touch brighter.
      const top = [];
      for (let i = 0; i <= n; i++) top.push(pts[2 * i], pts[2 * i + 1]);
      put(LINE, [0.012, 236, 242, 248, 0.10 * bankA].concat(top));
    }

    // Autumn: fallen leaves gathering in the corners - none for the first
    // ten days, all six by day sixty.
    const autumnA = S.autumn * all;
    if (autumnA > MIN_A) {
      const nFallen = Math.floor(6 * clamp((C.day.autumn - 10) / 50, 0, 1));
      for (let i = 0; i < nFallen; i++) {
        const side = i % 2 === 0 ? -1 : 1;
        const h1 = hash01(i * 7 + 1301), h2 = hash01(i * 7 + 1302), h3 = hash01(i * 7 + 1303);
        const c = LEAF_RGB[Math.floor(h3 * 4) % 4];
        const len = 0.05 + 0.015 * h2;
        put(POLY, [c[0] * 0.85, c[1] * 0.85, c[2] * 0.85, 0.55 * autumnA]
          .concat(place(LEAF, side * (0.64 + 0.28 * h1), L.FLOOR + 0.014 + 0.02 * h2, len, 0.32 * len, (h3 - 0.5) * 0.5)));
      }
    }

    // The pumpkin, 24-31 October: plain, no face, no glow. `u` is its size
    // unit (about 0.19 wide).
    const pumpA = I.pumpkin * moving;
    if (pumpA > MIN_A) {
      const u = 0.0155, x = L.RIGHT_X, y = L.FLOOR + 3.4 * u;
      put(POLY, [176, 90, 38, 0.8 * pumpA].concat(flat(ellipse(x - 2.5 * u, y, 3.1 * u, 3.1 * u, 20))));
      put(POLY, [176, 90, 38, 0.8 * pumpA].concat(flat(ellipse(x + 2.5 * u, y, 3.1 * u, 3.1 * u, 20))));
      put(POLY, [198, 106, 46, 0.85 * pumpA].concat(flat(ellipse(x, y, 3.4 * u, 3.4 * u, 20))));
      put(POLY, [96, 104, 60, 0.85 * pumpA].concat([x - 0.5 * u, y + 2.9 * u, x + 0.5 * u, y + 2.9 * u,
        x + 1.1 * u, y + 4.9 * u, x + 0.2 * u, y + 5.1 * u]));
    }

    // The snowman, mid-winter: two snowballs, coal eyes, a small nose, a
    // scarf and twig arms, standing in the snow bank. `u` is its size unit
    // (about 0.25 tall).
    const snA = I.snowman * S.winter * moving;
    if (snA > MIN_A) {
      const u = 0.0145, x = L.LEFT_X, by = L.FLOOR + 0.07 + 3.0 * u;
      const hy = by + 4.8 * u + 2.4 * u;
      put(LINE, [0.4 * u, 120, 92, 70, 0.7 * snA, x - 4 * u, by + 1.2 * u, x - 7.5 * u, by + 3.5 * u]);
      put(LINE, [0.4 * u, 120, 92, 70, 0.7 * snA, x + 4 * u, by + 1.2 * u, x + 7.5 * u, by + 4 * u]);
      put(DOT, [x, by, 4.8 * u, 236, 240, 246, 0.72 * snA]);
      put(DOT, [x, hy, 3.2 * u, 240, 243, 248, 0.76 * snA]);
      put(POLY, [110, 150, 160, 0.7 * snA, x - 3 * u, hy - 2.4 * u, x + 3 * u, hy - 2.4 * u,
        x + 2.8 * u, hy - 3.4 * u, x - 2.8 * u, hy - 3.4 * u]);
      put(DOT, [x - 1.1 * u, hy + 0.7 * u, 0.45 * u, 44, 46, 54, 0.8 * snA]);
      put(DOT, [x + 1.1 * u, hy + 0.7 * u, 0.45 * u, 44, 46, 54, 0.8 * snA]);
      put(POLY, [190, 118, 78, 0.8 * snA, x, hy + 0.2 * u, x + 2.6 * u, hy - 0.4 * u, x, hy - 0.6 * u]);
    }

    // A string of soft lights along the top, 18 December - 1 January. Three
    // hooks, two gentle sags; each light breathes slowly (9 seconds).
    const lightA = I.lights * moving;
    if (lightA > MIN_A) {
      const wire = (x) => L.LIGHTS_TOP - L.LIGHTS_SAG * Math.abs(Math.sin(Math.PI * (x + ax) / ax));
      const n = 32;
      const line = [0.004, 70, 74, 66, 0.5 * lightA];
      for (let i = 0; i <= n; i++) {
        const x = -ax + 2 * ax * i / n;
        line.push(x, wire(x));
      }
      put(LINE, line);
      const nb = Math.max(6, Math.round(2 * ax / 0.15));
      for (let i = 0; i < nb; i++) {
        const x = -ax + 2 * ax * (i + 0.5) / nb;
        const y = wire(x) - 0.013;
        const c = BULB_RGB[i % BULB_RGB.length];
        const b = calm ? 0.9 : 0.85 + 0.15 * Math.sin(tt * TAU / 9 + i * 1.1);
        put(GLOW, [x, y, 0.048, c[0], c[1], c[2], 0.18 * b * lightA]);
        put(DOT, [x, y, 0.012, c[0], c[1], c[2], 0.85 * b * lightA]);
      }
    }

    // Summer at dusk and night: a few fireflies, wandering slowly, each
    // glowing up and down over five to eight seconds.
    const nightW = sunAlt !== null ? 1 - smoothstep(-6, 3, sunAlt)
      : Math.max(smoothstep(19.5, 21, hour), 1 - smoothstep(4, 5.5, hour));
    const flyA = S.summer * nightW * (1 - smoothstep(0.1, 0.4, rainW)) * moving;
    if (flyA > MIN_A) {
      const n = calm ? 4 : 7;
      for (let i = 0; i < n; i++) {
        const hx = hash01(i * 11 + 1501), hy = hash01(i * 11 + 1502), hs = hash01(i * 11 + 1503), hr = hash01(i * 11 + 1504);
        const x = (-0.92 + 1.84 * hx) * ax + 0.10 * Math.sin(tt * 0.11 * (1 + hs) + hx * TAU) + 0.05 * Math.sin(tt * 0.23 + hr * TAU);
        const y = -0.78 + 1.1 * hy + 0.08 * Math.sin(tt * 0.13 * (1 + hr) + hy * TAU) + 0.04 * Math.sin(tt * 0.29 + hs * TAU);
        const g = 0.5 - 0.5 * Math.cos(tt * TAU / (5 + 3 * hs) + hr * TAU);
        const b = calm ? 0.6 : 0.25 + 0.75 * g * g;
        put(GLOW, [x, y, 0.055, 206, 236, 128, 0.24 * b * flyA]);
        put(DOT, [x, y, 0.011, 236, 250, 190, 0.85 * b * flyA]);
      }
    }

    // Autumn: leaves drifting down, turning and tumbling as they sway.
    const leafA = S.autumn * moving;
    if (leafA > MIN_A) {
      const n = calm ? 5 : 9;
      for (let i = 0; i < n; i++) {
        const hx = hash01(i * 13 + 1201), hy = hash01(i * 13 + 1202), hs = hash01(i * 13 + 1203);
        const hc = hash01(i * 13 + 1204), hr = hash01(i * 13 + 1205);
        const speed = 0.045 + 0.03 * hs;
        const ph = frac(tt * speed / fall + hy);
        const y = ay + 0.1 - ph * fall;
        const w = tt * (0.5 + 0.3 * hr) + hy * TAU;
        const sway = Math.sin(w) * (0.05 + 0.04 * hs);
        const x = -ax + frac(hx + (0.10 * ph * fall + sway) / (2 * ax)) * 2 * ax;
        const ang = hr * TAU + tt * 0.25 * (hr < 0.5 ? -1 : 1) * (0.5 + hs) + 0.5 * Math.cos(w);
        const len = 0.045 + 0.02 * hs;
        const tumble = 0.45 + 0.55 * Math.abs(Math.cos(tt * 0.7 * (0.6 + hr) + hx * TAU));
        const c = LEAF_RGB[Math.floor(hc * 4) % 4];
        put(POLY, [c[0], c[1], c[2], 0.6 * leafA].concat(place(LEAF, x, y, len, 0.55 * len * tumble, ang)));
      }
    }

    // Spring: blossom petals on a light breeze.
    const petalA = S.spring * moving;
    if (petalA > MIN_A) {
      const n = calm ? 5 : 10;
      for (let i = 0; i < n; i++) {
        const hx = hash01(i * 13 + 1601), hy = hash01(i * 13 + 1602), hs = hash01(i * 13 + 1603);
        const hc = hash01(i * 13 + 1604), hr = hash01(i * 13 + 1605);
        const speed = 0.035 + 0.02 * hs;
        const ph = frac(tt * speed / fall + hy);
        const y = ay + 0.1 - ph * fall;
        const w = tt * (0.6 + 0.3 * hr) + hy * TAU;
        const sway = Math.sin(w) * (0.06 + 0.03 * hs);
        const x = -ax + frac(hx + (0.18 * ph * fall + sway) / (2 * ax)) * 2 * ax;
        const ang = hr * TAU + tt * 0.35 * (hr < 0.5 ? -1 : 1) * (0.5 + hs) + 0.4 * Math.cos(w);
        const len = 0.03 + 0.012 * hs;
        const tumble = 0.5 + 0.5 * Math.abs(Math.cos(tt * 0.8 * (0.6 + hr) + hx * TAU));
        const c = PETAL_RGB[Math.floor(hc * 3) % 3];
        put(POLY, [c[0], c[1], c[2], 0.62 * petalA].concat(place(PETAL, x, y, len, 0.7 * len * tumble, ang)));
      }
    }

    // Winter: light snowfall - fewer and smaller flakes than the weather's,
    // and none while the sky is drawing real snow.
    const flakeA = S.winter * moving * (1 - smoothstep(0.02, 0.1, snowW));
    if (flakeA > MIN_A) {
      const n = calm ? 7 : 14;
      const fallS = 2 * ay + 0.1;
      for (let i = 0; i < n; i++) {
        const hx = hash01(i * 7 + 1701), hy = hash01(i * 7 + 1702), hs = hash01(i * 7 + 1703);
        const speed = 0.06 + 0.04 * hs;
        const ph = frac(tt * speed / fallS + hy);
        const y = ay + 0.05 - ph * fallS;
        const sway = Math.sin(tt * 0.5 + hy * TAU) * (0.02 + 0.015 * hs);
        const x = -ax + frac(hx + sway / (2 * ax)) * 2 * ax;
        put(DOT, [x, y, 0.008 + 0.008 * hs, SNOW_RGB[0], SNOW_RGB[1], SNOW_RGB[2], (0.32 + 0.12 * hs) * flakeA]);
      }
    }

    // New Year: a few slow sparkles, once, in the first minute of 1 January -
    // each fades up and down over ten seconds, three or four at a time.
    const spA = I.sparkle * moving;
    if (spA > MIN_A) {
      const n = calm ? 6 : 16;
      const sec = C.sparkleSec;
      for (let i = 0; i < n; i++) {
        const h1 = hash01(i * 9 + 1401), h2 = hash01(i * 9 + 1402), h3 = hash01(i * 9 + 1403), h4 = hash01(i * 9 + 1404);
        const u = (sec - h1 * 42) / 10;
        const a = calm ? 0.6 : (u > 0 && u < 1 ? Math.pow(Math.sin(Math.PI * u), 2) : 0);
        if (a * spA <= MIN_A) continue;
        // Off to the sides, where the face does not cover them.
        const x = (i % 2 === 0 ? -1 : 1) * (0.5 + 0.42 * h2) * ax;
        const y = 0.1 + 0.75 * h3 + (calm ? 0 : 0.05 * u);
        const r = (0.045 + 0.03 * h4) * (calm ? 1 : 0.8 + 0.2 * Math.sin(Math.PI * u));
        const c = i % 2 === 0 ? [255, 236, 180] : [240, 244, 255];
        put(GLOW, [x, y, 2.2 * r, c[0], c[1], c[2], 0.22 * a * spA]);
        put(POLY, [c[0], c[1], c[2], 0.85 * a * spA].concat(place(GLINT, x, y, r, r, h4 * Math.PI / 4)));
      }
    }

    // Drop what is too faint to see (the same rule in both apps).
    out.ops = ops.filter((op) => {
      const a = op.k === POLY ? op.v[3] : op.k === LINE ? op.v[4] : op.v[6];
      return a > MIN_A;
    });
    return out;
  }

  // ---- Drawing (desktop) -------------------------------------------------------------

  const rgba = (r, g, b, a) => `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${Math.max(0, Math.min(1, a)).toFixed(4)})`;

  /**
   * Paint `sc` (from scene()) on a 2D canvas context, BEHIND the face: after
   * the ground and the sky, before the face. `dim` (0..1, default 1) and
   * `ground` pull every colour toward the ground as the face dims - exact
   * for see-through paint, mix(ground, c, dim) - for a host whose own dim
   * does not cover this layer; faces.html's dimOver does, so it passes none.
   */
  function draw(g, w, h, sc, dim, ground) {
    if (!sc || !sc.ops || !sc.ops.length) return;
    const k = Math.min(w, h) / 2;
    const cx = w / 2, cy = h / 2;
    const X = (x) => cx + x * k, Y = (y) => cy - y * k;
    const dm = typeof dim === "number" ? clamp(dim, 0, 1) : 1;
    const gr = ground || [0, 0, 0];
    const col = (r, gg, b, a) => rgba(mix(gr[0], r, dm), mix(gr[1], gg, dm), mix(gr[2], b, dm), a);
    g.save();
    for (const op of sc.ops) {
      const v = op.v;
      if (op.k === GLOW) {
        const rg = g.createRadialGradient(X(v[0]), Y(v[1]), 0, X(v[0]), Y(v[1]), Math.max(1, v[2] * k));
        rg.addColorStop(0, col(v[3], v[4], v[5], v[6]));
        rg.addColorStop(1, col(v[3], v[4], v[5], 0));
        g.fillStyle = rg;
        g.beginPath(); g.arc(X(v[0]), Y(v[1]), v[2] * k, 0, Math.PI * 2); g.fill();
      } else if (op.k === DOT) {
        g.fillStyle = col(v[3], v[4], v[5], v[6]);
        g.beginPath(); g.arc(X(v[0]), Y(v[1]), Math.max(0.8, v[2] * k), 0, Math.PI * 2); g.fill();
      } else if (op.k === POLY) {
        g.fillStyle = col(v[0], v[1], v[2], v[3]);
        g.beginPath();
        for (let i = 4; i + 1 < v.length; i += 2) {
          if (i === 4) g.moveTo(X(v[i]), Y(v[i + 1])); else g.lineTo(X(v[i]), Y(v[i + 1]));
        }
        g.closePath();
        g.fill();
      } else if (op.k === LINE) {
        g.strokeStyle = col(v[1], v[2], v[3], v[4]);
        g.lineWidth = Math.max(1, v[0] * k);
        g.lineCap = "round"; g.lineJoin = "round";
        g.beginPath();
        for (let i = 5; i + 1 < v.length; i += 2) {
          if (i === 5) g.moveTo(X(v[i]), Y(v[i + 1])); else g.lineTo(X(v[i]), Y(v[i + 1]));
        }
        g.stroke();
      }
    }
    g.restore();
  }

  // ---- What the face pages need ---------------------------------------------------

  /**
   * Eases `hide` (Still or a serious moment) over about a second, and works
   * out `hold` (an approval or an error) from the state, for one surface.
   * `mem` is the host's own object for that surface (start with {}); `now`
   * is seconds; `want` is {state, still, serious}. Returns {hide, hold}.
   * The phone's FaceFrame already carries eased stillW and seriousW, so its
   * copy is only holdWeight().
   */
  function follow(mem, want, now) {
    const hideOn = !!(want && (want.still || want.serious));
    const st = (want && want.state) || "idle";
    if (mem.at === undefined) {
      mem.hide = hideOn ? 1 : 0; mem.st = st; mem.prev = st; mem.changed = -1e9; mem.at = now;
    }
    const dt = clamp(now - mem.at, 0, 0.25); mem.at = now;
    mem.hide = hideOn ? Math.min(1, mem.hide + dt) : Math.max(0, mem.hide - dt);
    if (st !== mem.st) { mem.prev = mem.st; mem.st = st; mem.changed = now; }
    const e = (r) => r * r * (3 - 2 * r);
    return { hide: e(mem.hide), hold: holdWeight(mem.st, mem.prev, now - mem.changed) };
  }

  const api = {
    VERSION: 1, LAYOUT, SEASONS, HOLIDAYS, SNOWMAN, SPARKLE_S, FADE_DAYS, HOLD_EASE_S,
    LEAF_RGB, PETAL_RGB, BULB_RGB, GLOW, DOT, POLY, LINE, MIN_A,
    hash01, smoothstep, daysFromCivil, civilFromDays, localOf, windowAt, calendar, holdWeight,
    leafShape, petalShape, glintShape, ellipse, place, scene, draw, follow,
  };
  root.JarvisSeason = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
