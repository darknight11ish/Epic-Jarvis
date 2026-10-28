/**
 * hud-text-size.mjs — the HUD follows the app's text size, and never breaks
 * when it is served on its own.
 *
 * WHY THIS FILE EXISTS (2026-10-27 accessibility audit, finding 3)
 *
 * Every size in these windows is a `px` value, and a Tauri WebView2 window has
 * no browser chrome, so Ctrl+= reaches nothing there. `jarvis-link.js` is the
 * one text-size control: `followZoom` restores the remembered zoom, binds
 * Ctrl+= / Ctrl+- / Ctrl+0, and listens for the `storage` write Settings' own
 * "Text size" buttons make in another window. Every window that has one calls
 * it - the bar, the widget, the badge and Brain - and the HUD did not, so a
 * reader who had set 150% everywhere else still got 14px in the largest
 * window in the app.
 *
 * WHAT THIS FILE PROVES, without a browser:
 *
 *   1. the page calls the SHARED `followZoom` - not a HUD-sized second copy of
 *      the zoom steps, the storage key or the keyboard shortcuts;
 *   2. it reaches it with a DYNAMIC import whose failure is caught, and not
 *      with a static `import { followZoom } from "./jarvis-link.js"` - because
 *      the HUD page is also served on its own by the backend from a CLOSED
 *      asset whitelist, and one module it cannot fetch would fail the whole
 *      module graph: every mount above (the safety rail, the editor, the
 *      presets, Current Models, Live) would stop with it;
 *   3. the guard really behaves: a module with `followZoom` gets exactly one
 *      call in the shell, and a module that is missing, null, empty, shapeless
 *      or throws synchronously is swallowed - the page keeps running, exactly
 *      as it did before this line;
 *   4. a page with NO webview to zoom (the backend-served HUD opened in a real
 *      browser) is left alone, so the browser's own Ctrl+= / Ctrl+- / Ctrl+0
 *      still work - `followZoom` calls `preventDefault()` on them, and would
 *      otherwise announce a size that never changed;
 *   5. the capability is already held, so no new grant rides along with this
 *      (`capabilities/hud.json` has `core:webview:allow-set-webview-zoom`).
 *
 * The guard itself is extracted from the page and called in Node, in the same
 * style `hud-live-read-aloud.mjs` uses for the page's own `readAloudIconsOn`,
 * so a regression fails here rather than only in the Lead's CI (which runs
 * every tests/*.mjs suite in a headless Chromium, but cannot prove the
 * missing-file fallback without that file actually missing).
 *
 *     node tests/hud-text-size.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");
const HUD = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");
const LINK = readFileSync(join(SRC, "jarvis-link.js"), "utf8");

const fails = [];
async function check(name, fn) {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (error) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${error.message}`);
  }
}

/** The source of the named function declaration in `source`, braces matched. */
function functionSource(source, name) {
  const at = source.indexOf(`function ${name}(`);
  assert.notEqual(at, -1, `the page no longer defines ${name}()`);
  const open = source.indexOf("{", at);
  assert.notEqual(open, -1, `${name} has no body`);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(at, i + 1);
    }
  }
  throw new Error(`${name}'s body is not closed`);
}

const guard = functionSource(HUD, "followTextSize");

/** Run the page's own guard with a stand-in loader. `canZoom` is what the page
 *  would work out for itself: true only in a shell with a webview to zoom. */
function runGuard(load, canZoom) {
  // eslint-disable-next-line no-new-func
  return new Function("load", "canZoom", `${guard}\nreturn followTextSize(load, canZoom);`)(load, canZoom);
}

/* ── 1. The shared function, called from the page ─────────────────────────── */

await check("the HUD calls the SHARED followZoom, not a copy of it", () => {
  assert.match(LINK, /export function followZoom\s*\(/,
    "jarvis-link.js no longer exports followZoom - the one text-size control moved");
  // The call is unconditional at load: a remembered zoom has to be applied to
  // the window even before anything is clicked.
  assert.match(HUD, /\nfollowTextSize\(\);\s*\n/,
    "the page no longer calls followTextSize() at load");
  // And the page holds no second copy of the zoom rules. The key, the steps,
  // the Ctrl handling and the webview zoom all live in jarvis-link.js only.
  assert.ok(!HUD.includes('"jarvis.zoom"'),
    "the page spells the zoom storage key itself instead of using jarvis-link.js");
  assert.ok(!HUD.includes("ZOOM_STEPS"),
    "the page keeps its own zoom steps instead of using jarvis-link.js");
  assert.ok(!/setZoom\s*\(/.test(HUD),
    "the page calls setZoom itself - it must go through followZoom, or it " +
    "would apply the zoom without remembering it or hearing the next change");
});

/* ── 2. A dynamic, guarded import - never a static one ────────────────────── */

await check("the import is dynamic and guarded, so one 404 cannot stop the page", () => {
  assert.match(guard, /import\("\.\/jarvis-link\.js"\)/,
    "the guard does not import ./jarvis-link.js");
  assert.match(guard, /\.catch\(/,
    "the guard has no .catch: a page served without ./jarvis-link.js would " +
    "reject and (as an unhandled import failure) lose the rest of the module");
  // The failure mode this exists to prevent: a STATIC import of the same
  // module. A module graph that cannot fetch one of its imports does not run
  // at all, so every mount in the page would silently disappear on the
  // backend-served page - the opposite of what this guard is for.
  assert.doesNotMatch(HUD, /import\s*\{[^}]*followZoom[^}]*\}\s*from\s*"\.\/jarvis-link\.js"/,
    "the page takes followZoom with a STATIC import - a page without " +
    "./jarvis-link.js would then lose its whole module graph, not one call");
});

/* ── 3. The guard's behaviour, driven for real ────────────────────────────── */

await check("a module with followZoom gets exactly one call in the shell", async () => {
  let calls = 0;
  const mod = { followZoom() { calls += 1; } };
  const answer = await runGuard(() => Promise.resolve(mod), true);
  assert.equal(answer, undefined, "the guard returned a value");
  assert.equal(calls, 1, `followZoom ran ${calls} times, not once`);
});

await check("a plain browser knows only its own Ctrl+= zoom, so it is left alone", async () => {
  // `followZoom` calls `preventDefault()` on Ctrl+= / Ctrl+- / Ctrl+0. On a
  // page served by the backend in a real browser there is no webview to zoom,
  // so running it would take the browser's own zoom away and announce a size
  // that never changed. The page must not call it there.
  let calls = 0;
  const mod = { followZoom() { calls += 1; } };
  await runGuard(() => Promise.resolve(mod), false);
  assert.equal(calls, 0, "followZoom ran on a page with no webview to zoom");
  // And the page works that out for itself from the shell object, rather than
  // being told: with no `window` at all (exactly this Node process) it must
  // reach the same answer. This is the default the `followTextSize()` call at
  // load takes on every page.
  await runGuard(() => Promise.resolve(mod));
  assert.equal(calls, 0, "a page with no shell object still followed a zoom");
  assert.match(guard, /__TAURI__[\s\S]*webview/,
    "the guard does not ask the shell whether there is a webview to zoom");
});

await check("a page with no module beside it keeps working, silently", async () => {
  const refused = () => Promise.reject(new Error("404: not found"));
  await runGuard(refused, true);        // must not throw
  await runGuard(() => Promise.resolve(null), true);   // an empty answer
  await runGuard(() => Promise.resolve({}), true);     // a module without the export
  await runGuard(() => Promise.resolve({ followZoom: "not a function" }), true);
});

await check("a loader that throws synchronously is caught too", async () => {
  // `import()` cannot throw synchronously, but a guard is only a guard if it
  // holds for the bad loader as well - this is why the page defers the load
  // to a microtask before calling it.
  await runGuard(() => { throw new Error("no module"); }, true);
});

/* ── 4. No new grant rides along ──────────────────────────────────────────── */

await check("the HUD's capability already allows a webview zoom", () => {
  const capability = JSON.parse(readFileSync(join(TAURI, "capabilities", "hud.json"), "utf8"));
  assert.ok(capability.permissions.includes("core:webview:allow-set-webview-zoom"),
    "capabilities/hud.json no longer grants core:webview:allow-set-webview-zoom, " +
    "so followZoom would log a refusal and the text size would not reach this window");
});

/* ── Result ──────────────────────────────────────────────────────────────── */

if (fails.length) {
  console.log(`\n${fails.length} failed:`);
  for (const name of fails) console.log(`  - ${name}`);
  process.exit(1);
}
console.log("\nok: the HUD follows the app's text size through the shared followZoom, " +
  "and a page served without ./jarvis-link.js never breaks");
