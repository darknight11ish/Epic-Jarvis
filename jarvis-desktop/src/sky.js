/**
 * The sun, the moon and the weather behind the animal faces (the owner's
 * decisions of 2026-09-28, CLAUDE.md: "Sun and moon behind the animals" and
 * "Weather in the animals' scene" - both optional, both off by default).
 *
 * WHAT THIS FILE IS. Pure maths plus one drawing function:
 *   - where the real sun and moon are in the sky for a moment and a place
 *     (altitude, direction, the moon's phase, how much of it is lit and which
 *     way its bright side faces), and when each next rises and sets;
 *   - a SCENE: that sky laid out behind the animal - a calm tint, the sun or
 *     the moon on a slow arc, clouds, rain, snow or wind - as plain numbers;
 *   - `draw(g, w, h, scene)`, which paints a scene on a 2D canvas.
 * The phone runs a line-for-line Kotlin copy (`jarvis-client/.../face/
 * Sky.kt`, drawn by `SkyDraw.kt`). They share ANSWERS, not code:
 * `tools/gen_sky.py` runs this file under node and writes `sky-golden.json`,
 * and the phone's `SkyTest` fails if the Kotlin copy disagrees - the same
 * pattern as the animals' pose code (critter-pose.js, gen_critters.py).
 *
 * NOTHING GOES ONLINE HERE. The place is a latitude and longitude (rounded to
 * 0.1 degree, about 11 km) that the owner typed once on the PC as a town
 * name; the PC turns the name into numbers from a list it carries
 * (backend/jarvis_sky.py). Everything below is worked out on the device.
 *
 * THE FORMULAS, and where they come from (implemented from the published
 * formulas; no code was copied):
 *   - The sun: NOAA's Solar Calculator ("General Solar Position
 *     Calculations", NOAA Global Monitoring Division), which is Jean Meeus,
 *     "Astronomical Algorithms" (2nd ed., 1998), chapters 22 and 25, in
 *     their low-precision form: about 0.01 degree, a minute of time.
 *   - The moon: the low-precision lunar formulas of "The Astronomical
 *     Almanac" (US Naval Observatory / HM Nautical Almanac Office, section D,
 *     "Low-precision formulas for the Moon's coordinates"): about 0.3 degree
 *     in position - a few minutes in when it rises. Its phase and the angle
 *     of its bright side: Meeus chapters 48 (illuminated fraction, position
 *     angle of the bright limb) and 14 (the parallactic angle, which turns
 *     that angle from "north on the sky" to "up on the screen").
 *   - Sidereal time: Meeus chapter 12 (formula 12.4).
 *   - Rising and setting: the moment the body's centre crosses -0.833
 *     degree (the sun: refraction plus its half-width) or 0.7275 x parallax
 *     - 0.5667 degree (the moon), Meeus chapter 15 - found here by stepping
 *     through the day and halving the gap, rather than by his closed form,
 *     so one search serves both bodies, the poles included.
 *
 * HOW IT LOOKS. The frame looks toward the equator - south in the northern
 * half of the world, north in the southern half - so the sun rises on the
 * left in the north, on the right in the south, as it does to someone
 * standing outside. Each body travels a slow arc round the animal, from its
 * rising side, over the top, to its setting side, timed by its real hour
 * angle (the arc is a picture of the day, not a camera view: a winter sun
 * climbs over the animal at noon just as a summer one does; the season
 * shows in when it rises and sets). It fades in and out at its real rising
 * and setting. The arc tops out above the animals' heads and above the
 * monkey's vine, so a noon sun or a midnight moon is seen, not hidden
 * behind the animal; the vine passes in front of it twice a day. The tint stays dark, so the animal and the app's dark theme
 * stay readable. It moves with real time only - the sun crosses the frame in
 * a day - and the weather is a pure function of the clock, the weather and a
 * hash, never of the frame before, so both apps draw the same rain.
 *
 * Coordinates: angles in degrees unless named `...R`; the scene is in the
 * face's own units, 1 = half its shorter side, x to the right, y UP, (0, 0)
 * the middle - the same units as the sleeping Zs (critter-pose.js zs()).
 */
(function (root) {
  "use strict";

  const D = Math.PI / 180;
  const DAY_MS = 86400000;

  // ---- Small helpers (the Kotlin copy has the same, in the same order) -----

  function norm360(x) {
    const y = x % 360;
    return y < 0 ? y + 360 : y;
  }
  /** -180 up to (not including) 180. */
  function wrap180(x) {
    return norm360(x + 180) - 180;
  }
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  function smoothstep(a, b, x) {
    const k = clamp((x - a) / (b - a), 0, 1);
    return k * k * (3 - 2 * k);
  }
  const mix = (a, b, k) => a + (b - a) * k;
  const frac = (x) => x - Math.floor(x);
  /** The animals' own hash (critter-pose.js hash01), 0..1. */
  function hash01(n) {
    let x = (n | 0) ^ 0x5bd1e995;
    x = Math.imul(x ^ (x >>> 15), 0x2c1b3c6d);
    x = Math.imul(x ^ (x >>> 12), 0x297a2d39);
    x ^= x >>> 15;
    return (x >>> 0) / 4294967296;
  }

  // ---- Time -----------------------------------------------------------------

  /** Julian Day from milliseconds since 1970 (UTC). */
  function julianDay(ms) {
    return ms / DAY_MS + 2440587.5;
  }
  /** Julian centuries since J2000.0. */
  function centuries(ms) {
    return (julianDay(ms) - 2451545.0) / 36525;
  }
  /** Greenwich mean sidereal time, degrees (Meeus 12.4). */
  function gmst(ms) {
    const d = julianDay(ms) - 2451545.0;
    const T = d / 36525;
    return norm360(280.46061837 + 360.98564736629 * d + 0.000387933 * T * T - T * T * T / 38710000);
  }

  // ---- Coordinates ------------------------------------------------------------

  /** Ecliptic (longitude, latitude) to equatorial (right ascension, declination). */
  function toEquatorial(lambda, beta, eps) {
    const l = lambda * D, b = beta * D, e = eps * D;
    const ra = Math.atan2(Math.sin(l) * Math.cos(e) - Math.tan(b) * Math.sin(e), Math.cos(l)) / D;
    const dec = Math.asin(Math.sin(b) * Math.cos(e) + Math.cos(b) * Math.sin(e) * Math.sin(l)) / D;
    return { ra: norm360(ra), dec };
  }

  /** Altitude, azimuth (from north, toward east) and hour angle, all degrees.
   *  Latitude is held inside +-89.9 so the pole's own maths stay finite. */
  function toHorizontal(ra, dec, ms, lat, lon) {
    const H = wrap180(gmst(ms) + lon - ra);
    const f = clamp(lat, -89.9, 89.9) * D, d = dec * D, h = H * D;
    const alt = Math.asin(clamp(Math.sin(f) * Math.sin(d) + Math.cos(f) * Math.cos(d) * Math.cos(h), -1, 1)) / D;
    const az = norm360(Math.atan2(Math.sin(h), Math.cos(h) * Math.sin(f) - Math.tan(d) * Math.cos(f)) / D + 180);
    return { alt, az, H };
  }

  // ---- The sun (NOAA / Meeus 25, low precision) ------------------------------

  function sunEcliptic(T) {
    const L0 = norm360(280.46646 + T * (36000.76983 + T * 0.0003032));
    const M = (357.52911 + T * (35999.05029 - 0.0001537 * T)) * D;
    const C = Math.sin(M) * (1.914602 - T * (0.004817 + 0.000014 * T))
      + Math.sin(2 * M) * (0.019993 - 0.000101 * T) + Math.sin(3 * M) * 0.000289;
    const omega = (125.04 - 1934.136 * T) * D;
    const lambda = norm360(L0 + C - 0.00569 - 0.00478 * Math.sin(omega));
    const eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60;
    const eps = eps0 + 0.00256 * Math.cos(omega);
    return { lambda, eps };
  }

  /** The sun for a moment and place: {alt, az, H, ra, dec, lambda}. */
  function sun(ms, lat, lon) {
    const T = centuries(ms);
    const e = sunEcliptic(T);
    const q = toEquatorial(e.lambda, 0, e.eps);
    const h = toHorizontal(q.ra, q.dec, ms, lat, lon);
    return { alt: h.alt, az: h.az, H: h.H, ra: q.ra, dec: q.dec, lambda: e.lambda };
  }

  // ---- The moon (The Astronomical Almanac, low precision) ---------------------

  function moonEcliptic(T) {
    const s = (a, b) => Math.sin((a + b * T) * D);
    const c = (a, b) => Math.cos((a + b * T) * D);
    const lambda = norm360(218.32 + 481267.881 * T
      + 6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36)
      + 0.66 * s(235.7, 890534.22) + 0.21 * s(269.9, 954397.74)
      - 0.19 * s(357.5, 35999.05) - 0.11 * s(186.5, 966404.03));
    const beta = 5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89)
      - 0.28 * s(318.3, 6003.15) - 0.17 * s(217.6, -407332.21);
    const parallax = 0.9508 + 0.0518 * c(135.0, 477198.87) + 0.0095 * c(259.3, -413335.36)
      + 0.0078 * c(235.7, 890534.22) + 0.0028 * c(269.9, 954397.74);
    return { lambda, beta, parallax };
  }

  /** The eight names, in order round the month (new moon first). */
  const PHASES = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
    "Full moon", "Waning gibbous", "Last quarter", "Waning crescent"];

  /** Which name, from the moon's longitude ahead of the sun (0..360). The
   *  four moments (new, quarters, full) are named for about a day either
   *  side (12 degrees - the moon gains about 12.2 a day). */
  function phaseIndex(elong) {
    const e = norm360(elong);
    for (let i = 0; i < 4; i++) {
      if (Math.abs(wrap180(e - i * 90)) < 12) return i * 2;
    }
    return 1 + 2 * Math.floor(e / 90);
  }

  /**
   * The moon for a moment and place: {alt (seen from the ground, parallax
   * taken off), altGeo, az, H, ra, dec, parallax, elong (0 new .. 180 full
   * .. 360), fraction lit (0..1), waxing, phase (index into PHASES), chi (the
   * bright side's position angle, from north toward east), tilt (the same
   * angle measured from straight UP on the screen, counter-clockwise)}.
   */
  function moon(ms, lat, lon) {
    const T = centuries(ms);
    const se = sunEcliptic(T);
    const m = moonEcliptic(T);
    const q = toEquatorial(m.lambda, m.beta, se.eps);
    const h = toHorizontal(q.ra, q.dec, ms, lat, lon);
    const sq = toEquatorial(se.lambda, 0, se.eps);
    const elong = norm360(m.lambda - se.lambda);
    // Meeus 48.2 and 48.3, with the phase angle taken as 180 - elongation
    // (a difference of at most about 0.15 degree).
    const cosPsi = Math.cos(m.beta * D) * Math.cos((m.lambda - se.lambda) * D);
    const fraction = clamp((1 - cosPsi) / 2, 0, 1);
    // Meeus 48.5: the bright limb's position angle.
    const a0 = sq.ra * D, d0 = sq.dec * D, a = q.ra * D, d = q.dec * D;
    const chi = norm360(Math.atan2(Math.cos(d0) * Math.sin(a0 - a),
      Math.sin(d0) * Math.cos(d) - Math.cos(d0) * Math.sin(d) * Math.cos(a0 - a)) / D);
    // Meeus 14.1: the parallactic angle, zenith's position angle.
    const f = clamp(lat, -89.9, 89.9) * D, hr = h.H * D;
    const pq = Math.atan2(Math.sin(hr), Math.tan(f) * Math.cos(d) - Math.sin(d) * Math.cos(hr)) / D;
    const alt = h.alt - m.parallax * Math.cos(h.alt * D);
    return {
      alt, altGeo: h.alt, az: h.az, H: h.H, ra: q.ra, dec: q.dec, parallax: m.parallax,
      elong, fraction, waxing: elong < 180, phase: phaseIndex(elong),
      chi, tilt: norm360(chi - pq),
    };
  }

  // ---- Rising and setting ----------------------------------------------------

  const SUN_H0 = -0.833;
  /** How far above (+) or below (-) its rising line a body is, degrees. */
  function aboveLine(body, ms, lat, lon) {
    if (body === "sun") return sun(ms, lat, lon).alt - SUN_H0;
    const m = moon(ms, lat, lon);
    return m.altGeo - (0.7275 * m.parallax - 0.5667);
  }

  const STEP_MS = 10 * 60 * 1000;
  const HALVINGS = 14;

  function cross(body, a, b, lat, lon, up) {
    for (let i = 0; i < HALVINGS; i++) {
      const mid = (a + b) / 2;
      const v = aboveLine(body, mid, lat, lon);
      if ((v >= 0) === up) b = mid;
      else a = mid;
    }
    return Math.round((a + b) / 2);
  }

  /**
   * The next rising and setting of "sun" or "moon" after `ms`, within
   * `hours` (default 30): {rise, set} in milliseconds, each null when it
   * does not happen in that time (a polar day or night, or a moon that skips
   * a day), plus `up`: whether it is above its line at `ms`.
   */
  function nextRiseSet(body, ms, lat, lon, hours) {
    const n = Math.ceil(((hours || 30) * 3600000) / STEP_MS);
    let prev = aboveLine(body, ms, lat, lon);
    const up = prev >= 0;
    let rise = null, set = null;
    for (let i = 1; i <= n && (rise === null || set === null); i++) {
      const t = ms + i * STEP_MS;
      const v = aboveLine(body, t, lat, lon);
      if (prev < 0 && v >= 0 && rise === null) rise = cross(body, t - STEP_MS, t, lat, lon, true);
      if (prev >= 0 && v < 0 && set === null) set = cross(body, t - STEP_MS, t, lat, lon, false);
      prev = v;
    }
    return { rise, set, up };
  }

  /** Everything the settings line says, as numbers; each app words the times
   *  in its own clock. */
  function summary(ms, lat, lon) {
    const s = nextRiseSet("sun", ms, lat, lon);
    const m = nextRiseSet("moon", ms, lat, lon);
    const mo = moon(ms, lat, lon);
    return {
      sunUp: s.up, sunrise: s.rise, sunset: s.set,
      moonUp: m.up, moonrise: m.rise, moonset: m.set,
      phase: mo.phase, phaseName: PHASES[mo.phase], percent: Math.round(mo.fraction * 100),
      waxing: mo.waxing,
    };
  }

  /**
   * The settings line under "Your town", the same words in both apps:
   * "Sun rises 06:41, sets 19:02. Moon: waxing gibbous, 78% lit, rises
   * 15:20." `fmt` turns milliseconds into the app's own clock time.
   */
  function todayWords(sm, fmt) {
    const sun = [];
    if (sm.sunrise !== null) sun.push(`rises ${fmt(sm.sunrise)}`);
    if (sm.sunset !== null) sun.push(`sets ${fmt(sm.sunset)}`);
    const first = sun.length ? `Sun ${sun.join(", ")}.`
      : sm.sunUp ? "The sun stays up all day." : "The sun stays down all day.";
    const moon = [];
    if (sm.moonrise !== null) moon.push(`rises ${fmt(sm.moonrise)}`);
    if (sm.moonset !== null) moon.push(`sets ${fmt(sm.moonset)}`);
    return `${first} Moon: ${sm.phaseName.toLowerCase()}, ${sm.percent}% lit`
      + (moon.length ? `, ${moon.join(", ")}` : "") + ".";
  }

  // ---- The scene ---------------------------------------------------------------

  /** The layout, in the face's units (1 = half its shorter side, y up). */
  const LAYOUT = {
    HORIZON: -0.32,   // where a body rises and sets: behind the animal's lower body
    RX: 0.84,         // the arc's half-width
    RY: 1.21,         // its height: tops out at 0.89, above the heads and the monkey's vine
    SUN_R: 0.075,
    MOON_R: 0.066,
  };

  // The tint, by the sun's altitude: [alt, top r, g, b, a, bottom r, g, b, a].
  // Dark by design: the most it adds over the app's own dark ground is about a
  // fifth, so the animal and the dark theme stay readable. Blue hour, then a
  // warm low band at dawn and dusk, then a quiet day blue.
  const TINT = [
    [-18, 12, 18, 40, 0.10, 12, 18, 40, 0.04],
    [-8, 22, 32, 74, 0.16, 40, 40, 80, 0.10],
    [-2, 30, 44, 90, 0.18, 120, 70, 60, 0.16],
    [6, 36, 70, 118, 0.20, 140, 96, 70, 0.14],
    [20, 36, 78, 122, 0.20, 60, 100, 138, 0.12],
  ];

  function tintAt(alt) {
    const a = clamp(alt, TINT[0][0], TINT[TINT.length - 1][0]);
    let i = 0;
    while (i < TINT.length - 2 && a > TINT[i + 1][0]) i++;
    const lo = TINT[i], hi = TINT[i + 1];
    const k = (a - lo[0]) / (hi[0] - lo[0]);
    const out = [];
    for (let j = 1; j < 9; j++) out.push(mix(lo[j], hi[j], k));
    return out;
  }

  /**
   * Where on its arc a body is: the share of its time above the horizon
   * that has gone (0 rising .. 1 setting; below 0 or above 1 it is under
   * the horizon), from its hour angle and the hour angle it rises at.
   */
  function arcShare(H, dec, lat, h0) {
    const f = clamp(lat, -89.9, 89.9) * D, d = dec * D;
    const c = (Math.sin(h0 * D) - Math.sin(f) * Math.sin(d)) / (Math.cos(f) * Math.cos(d));
    const H0 = Math.max(1, Math.acos(clamp(c, -1, 1)) / D);
    return { s: (H + H0) / (2 * H0), H0 };
  }

  /** A point on the arc, and a fade at a polar day's midnight wrap. The
   *  arc is one fixed shape for every season: at its top the body sits
   *  above every animal's head and above the monkey's vine (never on it),
   *  so the sun at noon and the moon at midnight are seen, not hidden
   *  behind the animal. The season shows in when it rises and sets. */
  function arcPoint(share, H0, lat) {
    const L = LAYOUT;
    // The frame looks toward the equator, so rising is on the left in the
    // northern half of the world and on the right in the southern.
    const ang = Math.PI * (1 - share.s);
    const east = lat >= 0 ? 1 : -1;
    const x = east * L.RX * Math.cos(ang);
    const y = L.HORIZON + L.RY * Math.sin(ang);
    const wrapFade = H0 >= 179.9 ? clamp(Math.min(share.s, 1 - share.s) / 0.03, 0, 1) : 1;
    return { x, y, wrapFade };
  }

  /** Weather, as numbers 0..1 (see backend jarvis_sky.py `weather_now`):
   *  rain, snow, wind, cloud, fog, and dir (+1 the wind drifts to the right
   *  on screen, -1 to the left). Anything missing counts as none. */
  function cleanWeather(w) {
    const n = (v) => (typeof v === "number" && isFinite(v) ? clamp(v, 0, 1) : 0);
    if (!w || typeof w !== "object") return { rain: 0, snow: 0, wind: 0, cloud: 0, fog: 0, dir: 1 };
    return { rain: n(w.rain), snow: n(w.snow), wind: n(w.wind), cloud: n(w.cloud), fog: n(w.fog),
      dir: w.dir === -1 ? -1 : 1 };
  }

  /** How far the particles move: under calm (reduced) motion they hold
   *  still, and the clouds too. */
  function particleClock(t, calm) {
    return calm ? 0 : t;
  }

  /**
   * The scene for a moment: pure numbers, no drawing.
   *
   * @param ms     wall-clock milliseconds since 1970 (UTC) - the real time
   * @param t      seconds for the weather's movement (the same wall clock,
   *               in seconds, so both apps' rain falls alike)
   * @param place  {lat, lon}, or null: then only the weather is drawn
   * @param weather see cleanWeather; null for none
   * @param opts   {calm, ax, ay}: calm (reduced) motion; the frame's
   *               half-width and half-height in face units (1 for a square)
   */
  function scene(ms, t, place, weather, opts) {
    const o = opts || {};
    const ax = typeof o.ax === "number" && o.ax > 0 ? o.ax : 1;
    const ay = typeof o.ay === "number" && o.ay > 0 ? o.ay : 1;
    const W = cleanWeather(weather);
    const out = { ax, ay, tint: null, glow: null, sun: null, moon: null,
      clouds: [], fog: 0, rain: [], snow: [], wisps: [] };
    let dayW = 0, sunAlt = -90;
    const L = LAYOUT;
    if (place && isFinite(place.lat) && isFinite(place.lon)) {
      const lat = clamp(place.lat, -90, 90), lon = place.lon;
      const s = sun(ms, lat, lon);
      sunAlt = s.alt;
      dayW = smoothstep(-4, 10, s.alt);
      out.tint = tintAt(s.alt);
      const sh = arcShare(s.H, s.dec, lat, SUN_H0);
      const sp = arcPoint(sh, sh.H0, lat);
      const clouded = 1 - 0.65 * W.cloud;
      const sunVis = smoothstep(-1.2, 0.8, s.alt) * sp.wrapFade;
      const warm = 1 - smoothstep(2, 14, s.alt);
      out.sun = {
        x: sp.x, y: sp.y, r: L.SUN_R,
        alpha: sunVis * clouded,
        glow: 0.28 * sunVis * (1 - 0.8 * W.cloud),
        warm,
      };
      // The warm glow along the horizon near the sun, from a little before
      // sunrise to a little after, and the same round sunset.
      const bell = smoothstep(-10, -3, s.alt) * (1 - smoothstep(3, 12, s.alt));
      if (bell > 0) {
        out.glow = { x: clamp(sp.x, -0.95 * ax, 0.95 * ax), y: L.HORIZON, r: 0.95,
          alpha: 0.20 * bell * (1 - 0.6 * W.cloud) };
      }
      const m = moon(ms, lat, lon);
      const mh = arcShare(m.H, m.dec, lat, 0.7275 * m.parallax - 0.5667);
      const mp = arcPoint(mh, mh.H0, lat);
      const moonVis = smoothstep(-1.0, 1.0, m.alt) * mp.wrapFade;
      const tr = m.tilt * D;
      out.moon = {
        x: mp.x, y: mp.y, r: L.MOON_R,
        // By day the moon is paler, as it is outside.
        alpha: moonVis * mix(1, 0.45, dayW) * clouded,
        glow: 0.16 * m.fraction * moonVis * (1 - dayW) * (1 - 0.8 * W.cloud),
        fraction: m.fraction, phase: m.phase,
        // Which way the lit side faces on screen: a unit vector, y up.
        bx: -Math.sin(tr), by: Math.cos(tr),
      };
    }
    const tt = particleClock(t, o.calm === true);
    // Clouds: a few soft puffs drifting very slowly with the wind (minutes
    // to cross the frame), in front of the sun and the moon.
    if (W.cloud > 0.15) {
      const n = 2 + Math.round(3 * W.cloud);
      const speed = 0.004 + 0.010 * W.wind;
      const span = 2 * ax + 0.8;
      for (let i = 0; i < n; i++) {
        const hx = hash01(i * 11 + 101), hy = hash01(i * 11 + 102), hs = hash01(i * 11 + 103);
        const x = -ax - 0.4 + frac(hx + W.dir * tt * speed * (0.7 + 0.6 * hs) / span) * span;
        out.clouds.push([x, 0.22 + 0.5 * hy, 0.26 + 0.12 * hs, 0.09 + 0.04 * hs,
          (0.08 + 0.10 * W.cloud) * (0.7 + 0.3 * hs)]);
      }
    }
    out.cloudDay = dayW;
    out.fog = 0.10 * W.fog;
    // Rain: soft falling streaks, slanted by the wind.
    if (W.rain > 0.02) {
      const n = Math.round(8 + 36 * W.rain);
      const slant = W.wind * 0.55 * W.dir;
      const fall = 2 * ay + 0.3;
      for (let i = 0; i < n; i++) {
        const hx = hash01(i * 7 + 1), hy = hash01(i * 7 + 2), hs = hash01(i * 7 + 3);
        const speed = 0.9 + 0.5 * hs;
        const ph = frac(tt * speed / fall + hy);
        const y = ay + 0.15 - ph * fall;
        const x = -ax + frac(hx + slant * ph * fall / (2 * ax)) * 2 * ax;
        const len = 0.07 + 0.04 * hs;
        out.rain.push([x, y, slant * len, len, 0.16 + 0.12 * W.rain]);
      }
    }
    // Snow: slow drifting flakes, a gentle sway, carried by the wind.
    if (W.snow > 0.02) {
      const n = Math.round(10 + 30 * W.snow);
      const fall = 2 * ay + 0.1;
      for (let i = 0; i < n; i++) {
        const hx = hash01(i * 7 + 501), hy = hash01(i * 7 + 502), hs = hash01(i * 7 + 503);
        const speed = 0.10 + 0.08 * hs;
        const ph = frac(tt * speed / fall + hy);
        const y = ay + 0.05 - ph * fall;
        const sway = Math.sin(tt * 0.6 + hy * 6.2832) * (0.03 + 0.02 * hs);
        const x = -ax + frac(hx + (W.wind * 0.25 * W.dir * ph * fall + sway) / (2 * ax)) * 2 * ax;
        out.snow.push([x, y, 0.010 + 0.010 * hs, 0.35 + 0.25 * W.snow]);
      }
    }
    // Wind on its own: a few faint lines of air drifting across.
    if (W.wind > 0.25) {
      const n = Math.round(6 * W.wind);
      const span = 2 * ax + 0.5;
      for (let i = 0; i < n; i++) {
        const hx = hash01(i * 5 + 901), hy = hash01(i * 5 + 902), hs = hash01(i * 5 + 903);
        const speed = 0.12 + 0.10 * W.wind;
        const x = -ax - 0.25 + frac(hx + W.dir * tt * speed * (0.8 + 0.4 * hs) / span) * span;
        out.wisps.push([x, -0.7 + 1.4 * hy, 0.14 + 0.08 * hs, 0.07 * W.wind]);
      }
    }
    out.sunAlt = sunAlt;
    return out;
  }

  /**
   * The lit part of the moon as a closed outline: `n` points down the
   * bright edge, then `n` back up the shadow's edge (an ellipse, the
   * terminator), in the moon's own units (radius 1), with the bright side
   * facing (bx, by), y up. Fraction 0 is nothing lit; 1, the whole disc.
   */
  function moonOutline(fraction, bx, by, n) {
    const e = 2 * clamp(fraction, 0, 1) - 1;
    const pts = [];
    const put = (u, v) => pts.push([u * bx - v * by, u * by + v * bx]);
    for (let i = 0; i <= n; i++) {
      const a = Math.PI / 2 - Math.PI * i / n;        // top, round the bright side, to the bottom
      put(Math.cos(a), Math.sin(a));
    }
    for (let i = 1; i < n; i++) {
      const a = -Math.PI / 2 + Math.PI * i / n;       // back up along the terminator
      put(-e * Math.cos(a), Math.sin(a));
    }
    return pts;
  }

  // ---- Drawing (desktop) ---------------------------------------------------------

  const rgba = (r, g, b, a) => `rgba(${Math.round(r)},${Math.round(g)},${Math.round(b)},${Math.max(0, Math.min(1, a)).toFixed(4)})`;

  /**
   * Paint `sc` (from scene()) on a 2D canvas context, BEHIND the face: call
   * it after the ground is filled and before the animal is drawn. Everything
   * is soft and see-through; nothing here flashes.
   */
  function draw(g, w, h, sc) {
    if (!sc) return;
    const k = Math.min(w, h) / 2;
    const cx = w / 2, cy = h / 2;
    const X = (x) => cx + x * k, Y = (y) => cy - y * k;
    g.save();
    if (sc.tint) {
      const t = sc.tint;
      const grad = g.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, rgba(t[0], t[1], t[2], t[3]));
      grad.addColorStop(1, rgba(t[4], t[5], t[6], t[7]));
      g.fillStyle = grad;
      g.fillRect(0, 0, w, h);
    }
    if (sc.glow && sc.glow.alpha > 0.002) {
      const gl = sc.glow;
      const rg = g.createRadialGradient(X(gl.x), Y(gl.y), 0, X(gl.x), Y(gl.y), gl.r * k);
      rg.addColorStop(0, rgba(255, 150, 80, gl.alpha));
      rg.addColorStop(1, rgba(255, 150, 80, 0));
      g.fillStyle = rg;
      g.fillRect(0, 0, w, h);
    }
    const s = sc.sun;
    if (s && s.alpha > 0.002) {
      const r = s.r * k;
      const cr = mix(255, 255, s.warm), cg = mix(241, 179, s.warm), cb = mix(201, 107, s.warm);
      if (s.glow > 0.002) {
        const rg = g.createRadialGradient(X(s.x), Y(s.y), r * 0.5, X(s.x), Y(s.y), r * 4.2);
        rg.addColorStop(0, rgba(255, 200, 120, s.glow));
        rg.addColorStop(1, rgba(255, 200, 120, 0));
        g.fillStyle = rg;
        g.beginPath(); g.arc(X(s.x), Y(s.y), r * 4.2, 0, Math.PI * 2); g.fill();
      }
      const rg2 = g.createRadialGradient(X(s.x), Y(s.y), 0, X(s.x), Y(s.y), r);
      rg2.addColorStop(0, rgba(255, 250, 235, s.alpha));
      rg2.addColorStop(0.7, rgba(cr, cg, cb, s.alpha));
      rg2.addColorStop(1, rgba(cr, cg, cb, s.alpha * 0.55));
      g.fillStyle = rg2;
      g.beginPath(); g.arc(X(s.x), Y(s.y), r, 0, Math.PI * 2); g.fill();
    }
    const m = sc.moon;
    if (m && m.alpha > 0.002) {
      const r = m.r * k;
      if (m.glow > 0.002) {
        const rg = g.createRadialGradient(X(m.x), Y(m.y), r * 0.6, X(m.x), Y(m.y), r * 3.4);
        rg.addColorStop(0, rgba(200, 215, 235, m.glow));
        rg.addColorStop(1, rgba(200, 215, 235, 0));
        g.fillStyle = rg;
        g.beginPath(); g.arc(X(m.x), Y(m.y), r * 3.4, 0, Math.PI * 2); g.fill();
      }
      // The unlit side, faintly (earthshine), so the moon reads as a disc.
      g.fillStyle = rgba(226, 232, 240, 0.07 * m.alpha);
      g.beginPath(); g.arc(X(m.x), Y(m.y), r, 0, Math.PI * 2); g.fill();
      if (m.fraction > 0.005) {
        const pts = moonOutline(m.fraction, m.bx, m.by, 24);
        g.fillStyle = rgba(226, 232, 240, 0.9 * m.alpha);
        g.beginPath();
        pts.forEach((p, i) => {
          const px = X(m.x + p[0] * m.r), py = Y(m.y + p[1] * m.r);
          if (i === 0) g.moveTo(px, py); else g.lineTo(px, py);
        });
        g.closePath();
        g.fill();
      }
    }
    for (const c of sc.clouds) {
      const cr = mix(70, 150, sc.cloudDay), cg = mix(80, 165, sc.cloudDay), cb = mix(95, 180, sc.cloudDay);
      g.save();
      g.translate(X(c[0]), Y(c[1]));
      g.scale(1, c[3] / c[2]);
      const rg = g.createRadialGradient(0, 0, 0, 0, 0, c[2] * k);
      rg.addColorStop(0, rgba(cr, cg, cb, c[4]));
      rg.addColorStop(1, rgba(cr, cg, cb, 0));
      g.fillStyle = rg;
      g.beginPath(); g.arc(0, 0, c[2] * k, 0, Math.PI * 2); g.fill();
      g.restore();
    }
    if (sc.fog > 0.002) {
      g.fillStyle = rgba(120, 130, 140, sc.fog);
      g.fillRect(0, 0, w, h);
    }
    if (sc.rain.length) {
      g.lineCap = "round";
      g.lineWidth = Math.max(1, 0.006 * k);
      for (const d of sc.rain) {
        g.strokeStyle = rgba(150, 180, 210, d[4]);
        g.beginPath();
        g.moveTo(X(d[0]), Y(d[1]));
        g.lineTo(X(d[0] - d[2]), Y(d[1] + d[3]));
        g.stroke();
      }
    }
    for (const f of sc.snow) {
      g.fillStyle = rgba(230, 238, 245, f[3]);
      g.beginPath(); g.arc(X(f[0]), Y(f[1]), Math.max(0.8, f[2] * k), 0, Math.PI * 2); g.fill();
    }
    if (sc.wisps.length) {
      g.lineCap = "round";
      g.lineWidth = Math.max(1, 0.005 * k);
      for (const wv of sc.wisps) {
        g.strokeStyle = rgba(190, 205, 220, wv[3]);
        g.beginPath();
        g.moveTo(X(wv[0]), Y(wv[1]));
        g.lineTo(X(wv[0] + wv[2]), Y(wv[1]));
        g.stroke();
      }
    }
    g.restore();
  }

  // ---- What the face pages read -------------------------------------------------

  /**
   * The sky as Settings last read it from the PC (GET /api/sky), kept in this
   * computer's localStorage so every face page - the Widget's, the floating
   * face's, the HUD's and the Faces window - can draw it, the same way they
   * read "Keep the animal still" (face-tuning.js). Only what drawing needs:
   * on or off, the place rounded to 0.1 degree, and the weather as numbers
   * with the time it was read.
   */
  const STORE_KEY = "jarvis.sky.v1";
  /** Weather older than this is not drawn (the PC reads it every 20-30
   *  minutes while a face is showing; a stale shower should not rain for
   *  ever on a machine that stopped hearing). */
  const WEATHER_STALE_MS = 90 * 60 * 1000;

  /** A stored or received document, checked: {show, place, weather, at}. */
  function fromDoc(doc) {
    const out = { show: false, place: null, weather: null, weatherAt: 0 };
    if (!doc || typeof doc !== "object") return out;
    out.show = doc.show === true;
    const p = doc.place;
    if (p && typeof p === "object" && isFinite(p.lat) && isFinite(p.lon)
        && Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180) {
      out.place = { lat: Math.round(p.lat * 10) / 10, lon: Math.round(p.lon * 10) / 10 };
    }
    const w = doc.weather;
    if (w && typeof w === "object" && w.now && typeof w.now === "object") {
      out.weather = cleanWeather(w.now);
      out.weatherAt = isFinite(w.now.at) ? w.now.at * 1000 : 0;
    }
    return out;
  }

  /** What to draw now, from a stored document: null when nothing is. */
  function liveInput(stored, nowMs) {
    const s = fromDoc(stored);
    if (!s.show && !s.weather) return null;
    const weather = s.weather && nowMs - s.weatherAt <= WEATHER_STALE_MS ? s.weather : null;
    const place = s.show ? s.place : null;
    if (!place && !weather) return null;
    return { place, weather };
  }

  const api = {
    VERSION: 1, D, PHASES, LAYOUT, TINT, STORE_KEY, WEATHER_STALE_MS, SUN_H0, STEP_MS,
    norm360, wrap180, smoothstep, hash01, julianDay, centuries, gmst,
    toEquatorial, toHorizontal, sun, moon, phaseIndex, nextRiseSet, summary, todayWords,
    tintAt, arcShare, arcPoint, cleanWeather, scene, moonOutline, draw,
    fromDoc, liveInput,
  };
  root.JarvisSky = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
