// Inline script guard. tauri.conf.json's script-src still carries
// 'unsafe-inline' because these pages still hold inline <script> blocks (the
// small theme-flash guard on every window, the 388 KB face page and the HUD's
// two big blocks, which faces.mjs / hud.mjs / shader_size.py and the phone's
// resolve vectors read from the HTML itself). Tauri hashes every inline script
// at build time and a hash turns 'unsafe-inline' off for that page, so the
// packaged pages already run under hashes - but a page with NO inline script
// would get no hash and would fall back to 'unsafe-inline'.
//
// This test pins the situation so it cannot get worse unnoticed:
//   1. no new inline <script> block appears in any src/*.html (the count per
//      page is listed below; lowering it is always fine);
//   2. no inline event-handler attribute (onclick=...) and no javascript: URL
//      in any page or script;
//   3. the day 'unsafe-inline' leaves script-src, NO inline script may remain
//      (this check then fails until every window's inline script is moved).
// No browser needed.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");

/** Inline <script> blocks each page has today. Never raise these. */
const ALLOWED_INLINE = {
  "brain.html": 1,
  "faces.html": 1,
  "index.html": 1,
  "jarvis_hud.html": 3,
  "live-badge.html": 1,
  "onboarding.html": 2,
  "settings.html": 1,
  "watch-badge.html": 1,
  "widget.html": 1,
  "floating.html": 0,
};

const conf = JSON.parse(readFileSync(join(ROOT, "src-tauri", "tauri.conf.json"), "utf8"));
const csp = conf.app.security.csp;
const scriptSrc = /script-src ([^;]*)/.exec(csp)?.[1] ?? "";
const unsafeInline = scriptSrc.split(/\s+/).includes("'unsafe-inline'");

let total = 0;
for (const f of readdirSync(SRC).filter((n) => n.endsWith(".html"))) {
  const html = readFileSync(join(SRC, f), "utf8").replace(/<!--[\s\S]*?-->/g, "");
  const inline = [...html.matchAll(/<script\b([^>]*)>/g)].filter((m) => !/\bsrc\s*=/.test(m[1]));
  total += inline.length;
  const allowed = unsafeInline ? (ALLOWED_INLINE[f] ?? 0) : 0;
  assert.ok(inline.length <= allowed, `${f} has ${inline.length} inline <script> block(s); at most ${allowed} allowed`);
  const handlers = [...html.matchAll(/<[a-z][^>]*\s(on[a-z]+)\s*=/gi)].map((m) => m[1]);
  assert.deepEqual(handlers, [], `${f} has inline event-handler attributes (blocked once unsafe-inline goes)`);
  assert.ok(!/(href|src|action)\s*=\s*["']?\s*javascript:/i.test(html), `${f} has a javascript: URL`);
}
for (const f of readdirSync(SRC).filter((n) => n.endsWith(".js"))) {
  const js = readFileSync(join(SRC, f), "utf8");
  const bad = /(?:href|src)\s*=\s*["'`]\s*javascript:|\.(?:href|src)\s*=\s*["'`]\s*javascript:|setAttribute\(\s*["']on[a-z]+["']/i;
  assert.ok(!bad.test(js), `${f} builds a javascript: URL or an inline handler`);
}
if (!unsafeInline) assert.equal(total, 0, "'unsafe-inline' is gone from script-src, but an inline <script> remains");
console.log(`ok: ${total} inline script blocks, none new; no inline handlers or javascript: URLs`);
