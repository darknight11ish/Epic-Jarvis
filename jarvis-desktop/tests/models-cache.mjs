/**
 * Brain -> Model, when Jarvis is not running
 * (docs/OFFLINE-MODELS-DESIGN-2026-09-27.md; src/models-cache.js,
 * src/brain.js's `renderModels`/`load`).
 *
 * Two parts: the pure cache functions, tested directly against a plain
 * in-memory `storage` the way `voice-flow.mjs` already tests
 * `loadMoment`/`saveMoment`; and the real page, in a headless Chromium,
 * checking that:
 *
 * - a successful read of "models" both paints and writes the cache, and
 *   strips it down to what section 5 of the design doc calls "honestly
 *   cacheable" (no `speed`, no `offload`);
 * - a failed read after a successful one - including one that happened in
 *   an EARLIER session, via `localStorage` surviving a reload - shows the
 *   cached list with a plain, visible "Jarvis isn't running" label and a
 *   real time, never silently as if it were live;
 * - a failed read with no cache at all (never once connected) says so
 *   plainly, and is not confused with a fault ("could not read this");
 * - the live-only fields (on/off the graphics card, recent speed, the
 *   live "current model" highlight) are hidden specifically on the stale
 *   path, and only there.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";
import * as C from "../src/models-cache.js";

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── The pure cache functions ────────────────────────────────────────── */

/** A plain in-memory `storage`, the same shape `voice-flow.mjs` uses. */
function memoryStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    _store: store,
  };
}

const REAL_BODY = {
  available: true,
  current: "qwen3:8b",
  previous: "llama3.1:8b",
  installed: [
    { ref: "qwen3:8b", size: 5_100_000_000, family: "qwen3" },
    { ref: "llama3.1:8b", size: 4_900_000_000, family: "llama" },
  ],
  // Live-only: must never survive into the cache.
  offload: { status: "cpu", note: "Spilled to the processor." },
  speed: { by_model: { "qwen3:8b": { median_words_per_s: 12 } } },
};

await check("nothing cached yet reads back null, and never throws on a bad storage", async () => {
  assert.equal(C.loadModelsCache(memoryStorage()), null);
  assert.equal(C.loadModelsCache({ getItem() { throw new Error("private window"); } }), null);
  assert.equal(C.loadModelsCache(null), null);
  assert.equal(C.saveModelsCache(REAL_BODY, 1000, { setItem() { throw new Error("full disk"); } }), false);
  assert.equal(C.saveModelsCache(REAL_BODY, 1000, null), false);
});

await check("a save strips speed and offload, and a load reads the same shape back", async () => {
  const storage = memoryStorage();
  const ok = C.saveModelsCache(REAL_BODY, 1758960000000, storage);
  assert.equal(ok, true);
  const raw = JSON.parse(storage.getItem(C.MODELS_CACHE_KEY));
  assert.equal(raw.at, 1758960000000);
  assert.deepEqual(Object.keys(raw.models).sort(), ["current", "installed", "previous"]);
  assert.ok(!("speed" in raw.models) && !("offload" in raw.models), "a live-only field was written to disk");
  const back = C.loadModelsCache(storage);
  assert.equal(back.at, 1758960000000);
  assert.deepEqual(back.models, {
    current: "qwen3:8b",
    previous: "llama3.1:8b",
    installed: [
      { ref: "qwen3:8b", size: 5_100_000_000, family: "qwen3" },
      { ref: "llama3.1:8b", size: 4_900_000_000, family: "llama" },
    ],
  });
});

await check("a string in `installed` (an older shape) is still a ref, and a nameless entry is dropped", async () => {
  const cached = C.cacheableModels({ current: "a", installed: ["a", { size: 1 }, { ref: "b", size: -1 }] });
  assert.deepEqual(cached.installed, [{ ref: "a" }, { ref: "b" }]);
});

await check("a hand-edited or older cache with an extra field on disk cannot smuggle it back onto the page", async () => {
  const storage = memoryStorage({
    [C.MODELS_CACHE_KEY]: JSON.stringify({
      at: 5000,
      models: { current: "a", installed: [{ ref: "a" }], offload: { status: "cpu" }, speed: {} },
    }),
  });
  const back = C.loadModelsCache(storage);
  assert.deepEqual(Object.keys(back.models).sort(), ["current", "installed", "previous"]);
});

await check("a cache with no `at`, or no `installed` array, is not a cache", async () => {
  const bad = (models) => memoryStorage({ [C.MODELS_CACHE_KEY]: JSON.stringify(models) });
  assert.equal(C.loadModelsCache(bad({ models: { installed: [] } })), null, "no at");
  assert.equal(C.loadModelsCache(bad({ at: 0, models: { installed: [] } })), null, "at is 0");
  assert.equal(C.loadModelsCache(bad({ at: 5000, models: {} })), null, "no installed array");
  assert.equal(C.loadModelsCache(bad("not even an object")), null);
  assert.equal(C.loadModelsCache(memoryStorage({ [C.MODELS_CACHE_KEY]: "{not json" })), null);
});

/* ── The real page ───────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

const FAILED_MODELS = {
  available: false,
  error: "could not reach the Jarvis server at http://127.0.0.1:4719",
  read: "failed",
};

async function faculties(brain) {
  const page = await K.open(browser, base, "brain.html", { brain: { ...K.BRAIN, ...brain } }, SIZE);
  await page.locator("#tab-faculties").click();
  await page.waitForTimeout(300);
  return page;
}

const modelsText = (page) => page.locator("#models").innerText();
const cacheRaw = (page) => page.evaluate((k) => localStorage.getItem(k), C.MODELS_CACHE_KEY);
/** Re-reads "models" the way the app itself does: leaving the tab and
 *  coming back, which re-runs `load()` for the Faculties view's sections -
 *  the same trigger `memory.mjs` already uses for a second read. */
async function reread(page) {
  await page.locator("#tab-memory").click();
  await page.waitForTimeout(100);
  await page.locator("#tab-faculties").click();
  await page.waitForTimeout(300);
}

await check("a successful read paints the list and writes the cache, stripped of speed and offload", async () => {
  const page = await faculties({ models: K.BRAIN.models });
  const text = await modelsText(page);
  const raw = await cacheRaw(page);
  const errors = page.__errors;
  await page.close();
  assert.match(text, /qwen3:8b/);
  assert.match(text, /llama3\.1:8b/);
  assert.doesNotMatch(text, /isn't running/, "marked stale on a good read");
  assert.ok(raw, "nothing was written to localStorage");
  const parsed = JSON.parse(raw);
  assert.ok(Number.isFinite(parsed.at) && parsed.at > 0);
  assert.equal(parsed.models.current, "qwen3:8b");
  assert.deepEqual(Object.keys(parsed.models).sort(), ["current", "installed", "previous"]);
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await check("a failed read after a successful one (still this session): the old list, plainly marked stale, live-only fields gone", async () => {
  const page = await faculties({ models: { ...K.BRAIN.models, offload: { status: "cpu" } } });
  const live = await modelsText(page);
  assert.match(live, /not on the graphics card/i, "the live pane should still show the offload note");
  await page.evaluate((failed) => { window.__brain.models = failed; }, FAILED_MODELS);
  await reread(page);
  const text = await modelsText(page);
  await page.close();
  assert.match(text, /isn't running/);
  assert.match(text, /qwen3:8b/, "the old list itself is still shown");
  assert.doesNotMatch(text, /not on the graphics card/i, "a live-only fact survived a stale read");
});

await check("a failed read with no prior cache at all: a plain \"nothing to show yet\", not \"could not read\"", async () => {
  const page = await faculties({ models: FAILED_MODELS });
  const text = await modelsText(page);
  const raw = await cacheRaw(page);
  await page.close();
  assert.match(text, /nothing to show yet/i);
  assert.match(text, /open this once while Jarvis is running/i);
  assert.doesNotMatch(text, /isn't running right now, so this list/i, "claimed to have stale data that does not exist");
  assert.doesNotMatch(text, /could not read this/i, "a first-ever failure read as a fault");
  assert.equal(raw, null, "a failed read must never write a cache");
});

await check("the backend saying outright it has no models module is not shown as stale, even with a cache on disk", async () => {
  const page = await faculties({ models: K.BRAIN.models });
  await page.evaluate((absent) => { window.__brain.models = absent; }, { available: false, read: "absent" });
  await reread(page);
  const text = await modelsText(page);
  await page.close();
  assert.match(text, /not on this backend/i);
  assert.doesNotMatch(text, /isn't running/);
});

await check("restarting the app (cache already on disk, the live read fails from the very first load): the cache still shows, clearly marked, with a real time", async () => {
  const page = await faculties({ models: K.BRAIN.models });
  const before = await cacheRaw(page);
  assert.ok(before, "the first, good read never wrote a cache");
  const cachedAt = JSON.parse(before).at;

  // A real restart tears down every JS object in the window (`state`,
  // included) but leaves `localStorage` exactly as it was. `page.reload()`
  // is the closest thing to that in one page: it re-runs every module from
  // its top, including the disk-cache seed in brain.js, while the actual
  // cache value written above sits untouched in the same origin's storage.
  // The extra `addInitScript` below only makes the LIVE read fail this
  // time, which is what "Jarvis is not running" looks like; it does not
  // touch localStorage.
  await page.addInitScript((failed) => { window.__brain.models = failed; }, FAILED_MODELS);
  await page.reload();
  await page.waitForTimeout(300);
  await page.locator("#tab-faculties").click();
  await page.waitForTimeout(300);
  const text = await modelsText(page);
  const after = await cacheRaw(page);
  const errors = page.__errors;
  await page.close();
  assert.match(text, /isn't running right now, so this list is from the last time it was/);
  assert.match(text, /qwen3:8b/, "the disk cache's own models");
  assert.match(text, /llama3\.1:8b/);
  assert.doesNotMatch(text, /not on the graphics card/i);
  assert.doesNotMatch(text, /Recent answers:/i, "the speed block, which was never on disk, was shown anyway");
  // A real clock time, not a raw number and not "just now"/"ago".
  assert.doesNotMatch(text, /\b\d{10,}\b/, "a raw timestamp leaked onto the page");
  assert.doesNotMatch(text, / ago\b/i);
  assert.ok(String(cachedAt).length > 8, "sanity: the cache really did carry a real timestamp");
  assert.equal(after, before, "a failed read must never overwrite the cache it is falling back to");
  assert.deepEqual(errors, [], JSON.stringify(errors));
});

await check("the live \"current model\" highlight and tag do not carry over stale: only the quieter note does", async () => {
  const page = await faculties({ models: K.BRAIN.models });
  const before = await page.evaluate(() =>
    document.querySelector('#models .row-tag[data-state="present"]')?.closest(".row-item")?.textContent || "");
  assert.match(before, /qwen3:8b/, "the live pane marks the current model");
  await page.evaluate((failed) => { window.__brain.models = failed; }, FAILED_MODELS);
  await reread(page);
  const activeTag = await page.evaluate(() => document.querySelectorAll('#models .row-tag[data-state="present"]').length);
  const text = await modelsText(page);
  await page.close();
  assert.equal(activeTag, 0, "a model is still drawn as the live current one while stale");
  assert.match(text, /As of that last connection, qwen3:8b was the one in use/);
});

await check("CONTROL: Use and Install stay on the page while stale (greyed by the stale link, not hidden), never a catalogue", async () => {
  const page = await faculties({ models: K.BRAIN.models });
  await page.evaluate((failed) => { window.__brain.models = failed; }, FAILED_MODELS);
  await reread(page);
  const install = await page.locator("#model-install").count();
  const lists = await page.locator("#models datalist, #models select").count();
  await page.close();
  assert.equal(lists, 0);
  assert.ok(install, "the install control disappeared instead of just being greyed");
});

await browser.close();
close();
console.log(
  fails.length
    ? `\n${fails.length} failed: ${fails.join(", ")}`
    : "\nThe Model pane tells the truth about what it knows, even with Jarvis off"
);
process.exit(fails.length ? 1 : 0);
