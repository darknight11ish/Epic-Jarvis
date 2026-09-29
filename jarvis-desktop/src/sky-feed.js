/**
 * Keeps this computer's copy of the sky settings fresh for the face pages.
 *
 * The face frames (faces.html in the Widget, the floating face and the HUD,
 * and the Faces window) hold no Tauri command at all. So the windows that
 * may read the sky (`get_sky`: Settings, the Widget and the floating face -
 * capabilities `settings-surface` and `sky-read`) ask the PC and keep what
 * drawing needs in localStorage (`JarvisSky.STORE_KEY`), which every page on
 * this origin shares - the same way "Keep the animal still" reaches them
 * (face-tuning.js). What is kept: on or off, the position rounded to 0.1
 * degree, and the weather as five numbers with the time it was read. Never
 * the town's name, never anything else.
 *
 * Asking the PC also lets it read the weather (it reads only while an app
 * asks, at most every 20 minutes). Several windows share one clock: a window
 * skips its turn when another asked less than FEED_MS ago.
 *
 * @module sky-feed
 */

export const STORE_KEY = "jarvis.sky.v1";
export const FEED_MS = 10 * 60 * 1000;

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);

const round1 = (x) => Math.round(x * 10) / 10;
const num01 = (v) => (typeof v === "number" && isFinite(v) ? Math.max(0, Math.min(1, v)) : 0);

/** The part of GET /api/sky a face page needs - nothing more. */
export function storedFrom(view, nowMs) {
  const doc = { show: false, place: null, weather: null, fetched: nowMs };
  if (!view || typeof view !== "object" || view.available === false) return doc;
  doc.show = view.show === true;
  const p = view.place;
  if (p && isFinite(p.lat) && isFinite(p.lon) && Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180) {
    doc.place = { lat: round1(p.lat), lon: round1(p.lon) };
  }
  const now = view.weather && view.weather.now;
  if (now && typeof now === "object" && isFinite(now.at)) {
    doc.weather = { now: { rain: num01(now.rain), snow: num01(now.snow), wind: num01(now.wind),
      cloud: num01(now.cloud), fog: num01(now.fog), dir: now.dir === -1 ? -1 : 1, at: now.at } };
  }
  return doc;
}

function readStored() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch { return null; }
}

/** Keep `view` (a GET /api/sky answer, or a POST's `view`) for the faces. */
export function storeSky(view) {
  try {
    const next = storedFrom(view, Date.now());
    const before = readStored();
    const same = before && JSON.stringify({ ...before, fetched: 0 }) === JSON.stringify({ ...next, fetched: 0 });
    localStorage.setItem(STORE_KEY, JSON.stringify(next));
    return !same;
  } catch {
    return false;
  }
}

/** Ask the PC now (unless another window just did), and every FEED_MS. */
export function startSkyFeed({ invoke } = {}) {
  const call = invoke || (IS_TAURI ? (c, a) => TAURI.core.invoke(c, a) : null);
  if (!call) return () => {};
  let stopped = false;
  const tick = async (force) => {
    if (stopped) return;
    const before = readStored();
    if (!force && before && Date.now() - (before.fetched || 0) < FEED_MS - 30000) return;
    try {
      const view = await call("get_sky");
      if (view && view.available === false) {
        // An older PC: nothing to draw.
        storeSky(null);
        return;
      }
      storeSky(view);
    } catch {
      // Not reachable right now: keep what is stored. The faces keep the sun
      // and moon (worked out here) and drop weather older than 90 minutes.
    }
  };
  tick(false);
  const id = setInterval(() => tick(false), FEED_MS);
  return () => { stopped = true; clearInterval(id); };
}
