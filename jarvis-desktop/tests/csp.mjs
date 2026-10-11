/**
 * The CSP the PACKAGED app really sends - and what it silently refuses.
 *
 * WHY THIS SUITE EXISTS (a real incident, 2026-10-07). The owner reported the
 * face drawn far too large and clipped in the floating window and in the HUD.
 * Every browser test passed and every hand render was correct, because a page
 * served by the test harness carries NO Content-Security-Policy header - while
 * the packaged app does. Tauri rewrites the header before serving every page:
 * it replaces the `{SCRIPT_NONCE_TOKEN}` / `{STYLE_NONCE_TOKEN}` it put into the
 * page's own <style> and <script> tags with a random nonce, and appends
 * `'nonce-...'` to script-src and style-src (read in tauri 2.11.x
 * src/manager/mod.rs, `replace_csp_nonce`). A directive that carries a nonce
 * makes Chromium IGNORE `'unsafe-inline'`, so:
 *
 *   - the page's own <style> (nonced) applies          - allowed
 *   - a <style> element created at run time            - REFUSED (no nonce)
 *   - a style="..." ATTRIBUTE                          - REFUSED (no nonce)
 *   - `el.style.width = ...` (CSSOM)                   - allowed
 *
 * faces.html's bootDisplay() gave its canvas its size with a <style> it built at
 * run time, so in the packaged app the canvas fell back to its intrinsic size -
 * its own backing store - and grew: 1200 px inside a 232 px frame, with about a
 * fifth of the face in view. That is the "giant black disc with a white
 * crescent". The Widget's 120 px face and the floating window were broken by the
 * same cause; the editor was not, because `.card canvas{...}` lives in the
 * page's own nonced <style>.
 *
 * WHAT IS PINNED HERE, so neither half can come back:
 *   1. a display-mode frame's canvas is the size of its frame (the incident);
 *   2. the editor still sizes its tiles from the page's own stylesheet;
 *   3. inline style ATTRIBUTES apply - which needs `style-src-attr
 *      'unsafe-inline'` in tauri.conf.json, because Tauri does not touch that
 *      directive while its nonce on style-src kills `'unsafe-inline'`;
 *   4. no shipped page or script builds a <style> at run time (that path is
 *      still refused, on purpose - fixed in the page instead);
 *   5. the CSP has not been gutted to make 1-4 pass (`'unsafe-eval'` absent,
 *      object-src 'none', default-src 'self').
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import http from "node:http";
import { extname, join, normalize } from "node:path";
import * as K from "./uikit.mjs";

const NONCE = "TESTNONCE123";
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

// ---- the app's own CSP, and Tauri's rewriting of it ------------------------
const CONF = JSON.parse(readFileSync(join(K.ROOT, "..", "src-tauri", "tauri.conf.json"), "utf8"));
const CONFIGURED = CONF.app.security.csp;
assert.ok(CONFIGURED, "tauri.conf.json has no csp at all");

/** Tauri's own rewrite, line for line: it parses the header into directives and
 *  appends the nonce to the exact entries `script-src` and `style-src`
 *  (tauri-2.11.x src/manager/mod.rs, `replace_csp_nonce`), so a directive with a
 *  different name - `style-src-attr` - is left exactly as configured. */
function asPackaged(csp) {
  return csp
    .split(";")
    .map((part) => {
      const d = part.trim();
      const name = d.split(/\s+/)[0];
      return (name === "script-src" || name === "style-src") ? `${d} 'nonce-${NONCE}'` : d;
    })
    .join("; ");
}
const PACKAGED = asPackaged(CONFIGURED);

/** The nonce Tauri puts on every <style>/<script> in the page it serves. */
const tokenise = (html) => html
  .replace(/<style(?![^>]*\bnonce=)/g, `<style nonce="${NONCE}"`)
  .replace(/<script(?![^>]*\bnonce=)/g, `<script nonce="${NONCE}"`);

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml",
  ".png": "image/png", ".wav": "audio/wav", ".woff2": "font/woff2",
};

/** Serves jarvis-desktop/src the way the app does: nonces injected, CSP set. */
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split("?")[0]).replace(/^\/+/, "") || "index.html";
  const file = join(K.ROOT, normalize(rel));
  if (!file.startsWith(K.ROOT)) { res.writeHead(403); res.end("no"); return; }
  let body;
  try { body = readFileSync(file); } catch { res.writeHead(404); res.end("not found"); return; }
  const type = MIME[extname(file)] || "application/octet-stream";
  if (type.startsWith("text/html")) body = Buffer.from(tokenise(body.toString("utf8")), "utf8");
  res.writeHead(200, { "Content-Type": type, "Content-Security-Policy": PACKAGED });
  res.end(body);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await K.launch();
const pageAt = async (url, viewport) => {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  await page.goto(`${base}/${url}`, { waitUntil: "load" });
  return page;
};

// ---- 1. the incident ------------------------------------------------------
/** The canvas' CSS box, and the backing store it was given. */
const canvasBox = (page) => page.evaluate(() => {
  const c = document.querySelector("#display-canvas");
  if (!c) return null;
  const r = c.getBoundingClientRect();
  return { css: Math.round(r.width), cssH: Math.round(r.height), backing: c.width,
           computed: getComputedStyle(c).width };
});

await check("faces: a display-mode frame fills its frame (the 2026-10-07 incident)", async () => {
  for (const size of [200, 232]) {
    const page = await pageAt("faces.html?mode=display&feed=parent&face=spiral", { width: size, height: size });
    await page.waitForTimeout(2500);
    const box = await canvasBox(page);
    await page.close();
    assert.ok(box, `no display canvas at ${size}`);
    assert.equal(box.css, size, `canvas box is ${box.css} in a ${size}px frame (computed ${box.computed})`);
    assert.equal(box.cssH, size, `canvas box height is ${box.cssH} in a ${size}px frame`);
    // Supersampled backing store, as before: the box is what the window shows.
    assert.ok(box.backing > size, `backing store ${box.backing} is not supersampled for a ${size}px frame`);
  }
});

// ---- 2. the editor is not touched ----------------------------------------
await check("faces: the editor still sizes its tiles from the page's own stylesheet", async () => {
  const page = await pageAt("faces.html", { width: 1400, height: 1000 });
  await page.waitForTimeout(4000);
  const tile = await page.evaluate(() => {
    const card = [...document.querySelectorAll(".card")]
      .find((c) => /spiral/i.test(c.textContent || ""));
    if (!card) return null;
    const c = card.querySelector("canvas");
    const r = c.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), backing: c.width,
             displayMode: document.documentElement.classList.contains("display-mode") };
  });
  await page.close();
  assert.ok(tile, "the spiral tile was not found in the editor");
  assert.equal(tile.displayMode, false, "the editor must not be in display mode");
  assert.ok(Math.abs(tile.w - tile.h) <= 1, `tile is not square: ${tile.w}x${tile.h}`);
  assert.ok(tile.w > 100 && tile.w < 600, `tile is ${tile.w}px, which is not a tile any more`);
  assert.ok(tile.backing >= tile.w, "the tile's backing store is smaller than its box");
});

// ---- 3. inline style attributes (what style-src-attr is for) --------------
await check("CSP: inline style attributes apply, so style-src-attr must be configured", async () => {
  assert.match(CONFIGURED, /style-src-attr[^;]*'unsafe-inline'/,
    "style-src-attr 'unsafe-inline' is missing: every style=\"...\" attribute is silently dropped");
  // ...and prove it on a real element that carries one, not just in the text.
  const page = await pageAt("faces.html", { width: 1400, height: 1000 });
  await page.waitForTimeout(2500);
  const applied = await page.evaluate(() => {
    const el = document.querySelector("#save-state");   // style="margin-left:10px;color:var(--dim)"
    if (!el) return null;
    return { marginLeft: getComputedStyle(el).marginLeft, hasAttr: el.hasAttribute("style") };
  });
  await page.close();
  assert.ok(applied && applied.hasAttr, "#save-state no longer carries the style attribute this checks");
  assert.equal(applied.marginLeft, "10px", `the style attribute was not applied (margin-left ${applied.marginLeft})`);
});

// ---- 4. the refused path must not come back in code ----------------------
await check("CSP: no shipped page or script builds a <style> at run time", () => {
  const offenders = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) { walk(p); continue; }
      if (!/\.(html|js|mjs)$/.test(name)) continue;
      const src = readFileSync(p, "utf8");
      // A run-time stylesheet (or a style attribute written by script) has no
      // nonce and is refused by the packaged CSP; put the rules in the page's
      // own <style> instead, scoped to whatever class the page adds.
      const bad = /createElement\(\s*["'`]style["'`]\s*\)|setAttribute\(\s*["'`]style["'`]/.exec(src);
      if (bad) offenders.push(`${p.slice(K.ROOT.length + 1)}: ${bad[0]}`);
    }
  };
  walk(K.ROOT);
  assert.deepEqual(offenders, [],
    `these build a stylesheet at run time, which the packaged CSP refuses: ${offenders.join(", ")}`);
});

// ---- 5. and the CSP itself was not gutted to get here --------------------
await check("CSP: still self-only, still no inline script evaluation", () => {
  assert.match(CONFIGURED, /default-src 'self'/);
  assert.match(CONFIGURED, /object-src 'none'/);
  assert.match(CONFIGURED, /script-src 'self'/);
  assert.ok(!/'unsafe-eval'/.test(CONFIGURED), "'unsafe-eval' was added to script-src");
  assert.ok(!/script-src[^;]*\*/.test(CONFIGURED), "script-src was widened to a wildcard");
});

await browser.close();
server.close();
console.log(fails.length ? `\n${fails.length} FAILED` : "\nthe packaged CSP is understood and nothing else is refused");
process.exit(fails.length ? 1 : 0);
