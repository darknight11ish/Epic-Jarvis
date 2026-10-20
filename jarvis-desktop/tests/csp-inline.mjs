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
//      (this check then fails until every window's inline script is moved);
//   4. every DOM sink inside a page's inline scripts is a constant clear, a
//      constant string, or a reviewed site in SAFE_HTML_SITES whose data goes
//      through an escaper (the 2026-10-20 DOM-sink audit; see the block at the
//      bottom), and the vendored HUD page is byte-identical to its twin.
// No browser needed.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");

/** Inline <script> blocks each page has today. Never raise these.
 *
 * RAISED ONCE, 2026-10-13, jarvis_hud.html 3 -> 4, and the reason is written
 * down because "never" is the point of the number: the fourth block is an
 * inline `type="module"` whose whole body is one import of the shared rule
 * `lane-warning.js` (the "the local model isn't running" line). It cannot be a
 * classic block: `import` is only legal in a module, and the script that
 * carries the rule must also carry its DOM half, which the other two windows
 * import from the same file - the alternative is the same sentence typed three
 * times, and this project has already paid for that. Tauri hashes inline
 * module scripts exactly as it hashes classic ones (tauri-codegen's
 * `inject_script_hashes` walks every inline `<script>`), which is the property
 * this file exists to protect. */
const ALLOWED_INLINE = {
  "brain.html": 1,
  "faces.html": 1,
  "index.html": 1,
  "jarvis_hud.html": 4,
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

/* --------------------------------------------------------------------------
 * 4. DOM sinks inside the pages' inline scripts, and the HUD twin.
 *
 * `tests/html-sinks.mjs` already walks src/*.js and fails on a sink that is not
 * escaped there. The pages' own inline scripts were NOT walked by anything
 * until the 2026-10-20 DOM-sink audit, which found 53 innerHTML/outerHTML/
 * insertAdjacentHTML/document.write USES across src/*.js, src/*.html and
 * jarvis-backend/jarvis_hud.html - 42 real sinks (11 were comment lines) and 35
 * template interpolations. Every interpolation is escaped by one of this
 * project's escapers (`escapeHtml`, `renderMarkdown`, `apprEscape`), is a
 * number/boolean, or comes from a compiled-in constant table; the rest are
 * listed in SAFE_HTML_SITES below ON PURPOSE, with the reason.
 *
 * This is the regression pin for the pages. It fails when:
 *   - a new HTML sink appears that is not a constant clear, a constant string,
 *     or one of the reviewed sites (no `insertAdjacentHTML`/`document.write`/
 *     `createContextualFragment` at all - there are none today);
 *   - a reviewed site gains an interpolation that is not escaped and not
 *     listed for that site (a raw model/server/email/search/filename string);
 *   - jarvis-desktop/src/jarvis_hud.html and jarvis-backend/jarvis_hud.html
 *     stop being byte-identical (that page is vendored from the backend).
 * ----------------------------------------------------------------------- */

const REPO = join(ROOT, "..");
const HUD_FILES = ["jarvis_hud.html", "jarvis-backend/jarvis_hud.html"];

/** Sites reviewed by a person on 2026-10-20. `rhs` matches the start of the
 *  value (whitespace collapsed). Every `${...}` in it must start with one of
 *  the escapers or be listed in `exprs` exactly. Keyed by file + value, never
 *  by line number. */
const SAFE_HTML_SITES = [
  {
    file: "faces.html",
    rhs: /^`<span class="sw"/,
    exprs: ["swatchFor(st.id)", "st.name"],
    why: "SPEC is window.JARVIS_SPEC, compiled from jarvis-visual-spec.json " +
      "(faces.html:254-258); swatchFor() resolves a colour from that static table.",
  },
  {
    file: "faces.html",
    rhs: /^`<div class="top">/,
    exprs: ["f.name", 'f.integrates_per_frame ? "sub-stepped" : f.dim'],
    why: "both fields are from the same compiled-in SPEC table, never server text.",
  },
  ...HUD_FILES.flatMap((file) => [
    {
      file,
      rhs: /^Object\.entries\(GROUPS\)/,
      exprs: ["swatchStyle(k)", "g.label", "counts[k]"],
      why: "GROUPS is this page's own constant; counts[k] is a number; " +
        "swatchStyle() returns a colour from the same table.",
    },
    {
      file,
      rhs: /^`<h4>Recalled/,
      exprs: [],
      why: "row() escapes the entity id and text with apprEscape (its own " +
        "comment above it explains the poisoned-entity XSS it prevents); the " +
        "rest is fixed words.",
    },
    {
      file,
      rhs: /^S\.traces\.map/,
      exprs: ["i", "t === S.activeTrace",
              "apprEscape(String(t.q).slice(0, 38))"],
      why: "the index and aria state are a number and a boolean; the owner's " +
        "question is truncated first and then escaped in full.",
    },
    {
      file,
      rhs: /^`<b>\$\{trace\.hits\.length\}<\/b>/,
      exprs: ["trace.hits.length", "trace.near.length"],
      why: "two array lengths - numbers.",
    },
    {
      file,
      rhs: /^`<div class="who">/,
      exprs: ["who"],
      why: "who is the fixed role ternary in addMessage, never server text; " +
        "the message body is set with textContent.",
    },
    {
      file,
      rhs: /^calls \.map/,
      exprs: [],
      why: "the one data field (the function name) is wrapped in apprEscape.",
    },
    {
      file,
      rhs: /^all\.map/,
      exprs: ["l.id===S.lane"],
      why: "lane id, label and tag are all escaped (the id sits inside the " +
        "quoted data-lane attribute); aria-pressed is a boolean.",
    },
    {
      file,
      rhs: /^status \?/,
      exprs: [],
      why: "two fixed sentences chosen by a boolean - no data.",
    },
    {
      file,
      rhs: /^'<div class="appr">/,
      exprs: [],
      why: "fixed words only (the session-expired card).",
    },
    {
      file,
      rhs: /^apprCardHtml\(/,
      exprs: [],
      why: "every data value inside apprCardHtml passes apprEscape: the title, " +
        "the raised text/quote/source, apprDescribe() and apprRiskLine().",
    },
    {
      file,
      rhs: /^html$/,
      exprs: [],
      why: "initCard is a forwarding sink: its three callers (the initiative " +
        "cards) put every data field through apprEscape; the scanner cannot " +
        "see through a parameter, so the callers are reviewed there.",
    },
  ]),
];

function sinkRegex() {
  return /(\.(?:innerHTML|outerHTML)\s*\+?=(?!=)|\.insertAdjacentHTML\s*\(|document\.write(?:ln)?\s*\(|createContextualFragment\s*\()/g;
}

/** Blanks JS comments (keeping line lengths so line numbers stay real). */
function blankJsComments(js) {
  const out = js.split("");
  for (let i = 0; i < js.length; i++) {
    const c = js[i];
    if (c === "'" || c === '"' || c === "`") { i = skipString(js, i); continue; }
    if (c === "/" && js[i + 1] === "/") {
      while (i < js.length && js[i] !== "\n") out[i++] = " ";
      continue;
    }
    if (c === "/" && js[i + 1] === "*") {
      out[i] = " "; out[i + 1] = " "; i += 2;
      while (i < js.length && !(js[i] === "*" && js[i + 1] === "/")) {
        if (js[i] !== "\n") out[i] = " ";
        i++;
      }
      if (i < js.length) { out[i] = " "; out[i + 1] = " "; i++; }
    }
  }
  return out.join("");
}

function skipString(src, i) {
  const q = src[i];
  for (i++; i < src.length; i++) {
    if (src[i] === "\\") { i++; continue; }
    if (q === "`" && src[i] === "$" && src[i + 1] === "{") {
      let depth = 1; i += 2;
      while (i < src.length && depth) {
        const c = src[i];
        if (c === '"' || c === "'" || c === "`") i = skipString(src, i);
        else if (c === "{") depth++;
        else if (c === "}") depth--;
        i++;
      }
      i--; continue;
    }
    if (src[i] === q) return i;
  }
  return i;
}

/** The text from `from` to the statement's `;` outside brackets/strings. */
function statementFrom(src, from) {
  let depth = 0;
  for (let i = from; i < src.length; i++) {
    const c = src[i];
    if (c === "'" || c === '"' || c === "`") { i = skipString(src, i); continue; }
    if ("([{".includes(c)) depth++;
    else if (")]}".includes(c)) depth--;
    else if (c === ";" && depth <= 0) return src.slice(from, i);
    if (depth < 0) return src.slice(from, i);
  }
  return src.slice(from);
}

/** Every `${...}` expression in a template literal, nesting respected. */
function interpolations(text) {
  const out = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== "`") continue;
    const end = skipString(text, i);
    const body = text.slice(i + 1, end);
    for (let j = 0; j < body.length; j++) {
      if (body[j] === "$" && body[j + 1] === "{") {
        let depth = 1, k = j + 2;
        while (k < body.length && depth) {
          const c = body[k];
          if (c === "'" || c === '"' || c === "`") k = skipString(body, k);
          else if (c === "{") depth++;
          else if (c === "}") depth--;
          k++;
        }
        out.push(body.slice(j + 2, k - 1).replace(/\s+/g, " ").trim());
        j = k - 1;
      }
    }
    i = end;
  }
  return out;
}

/** null when this sink is safe, otherwise why not. */
function judgeHtml(file, rhs, isAssign) {
  if (!isAssign) {
    return "a call-style HTML sink; none is allowed in a page - build the " +
      "nodes with DOM calls instead";
  }
  const flat = rhs.replace(/\s+/g, " ").trim();
  if (/^(""|''|``)$/.test(flat)) return null;
  if (/^(["'`])(?:(?!\1)[^\\$]|\\.)*\1$/.test(flat)) return null;
  if (/^(renderMarkdown|apprEscape|escapeHtml)\(/.test(flat)) return null;
  const sites = SAFE_HTML_SITES.filter((s) => s.file === file && s.rhs.test(flat));
  if (!sites.length) {
    return "not a constant and not in SAFE_HTML_SITES (a new sink must be " +
      "reviewed and listed on purpose)";
  }
  for (const e of interpolations(rhs)) {
    if (/^(escapeHtml|renderMarkdown|apprEscape|CSS\.escape)\(/.test(e)) continue;
    if (sites.some((s) => s.exprs.includes(e))) continue;
    return `interpolates \`${e}\`, which is neither escaped nor listed for this site`;
  }
  return null;
}

function scanInlinePage(file, html) {
  const problems = [];
  const noComments = html.replace(/<!--[\s\S]*?-->/g,
    (m) => m.replace(/[^\n]/g, " "));
  for (const block of noComments.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    if (/\bsrc\s*=/.test(block[1])) continue;
    const clean = blankJsComments(block[2]);
    const baseLine =
      noComments.slice(0, block.index + block[0].indexOf(">") + 1)
        .split("\n").length - 1;
    for (const m of clean.matchAll(sinkRegex())) {
      const lineNo = baseLine + clean.slice(0, m.index).split("\n").length;
      const lineStart = clean.lastIndexOf("\n", m.index) + 1;
      const target = clean.slice(lineStart, m.index).trim().slice(-50) + m[0];
      const isAssign = m[0].endsWith("=");
      const rhs = statementFrom(clean, m.index + m[0].length);
      const why = judgeHtml(file, rhs, isAssign);
      if (why) problems.push(`${file}:${lineNo} ${target.trim()} - ${why}`);
    }
  }
  return problems;
}

const htmlProblems = [];
let htmlSinks = 0;
for (const f of readdirSync(SRC).filter((n) => n.endsWith(".html"))) {
  const html = readFileSync(join(SRC, f), "utf8");
  htmlProblems.push(...scanInlinePage(f, html));
  const clean = html.replace(/<!--[\s\S]*?-->/g, "");
  for (const block of clean.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    if (/\bsrc\s*=/.test(block[1])) continue;
    htmlSinks += [...blankJsComments(block[2]).matchAll(sinkRegex())].length;
  }
}
htmlProblems.push(...scanInlinePage(
  "jarvis-backend/jarvis_hud.html",
  readFileSync(join(REPO, "jarvis-backend", "jarvis_hud.html"), "utf8")));
assert.ok(htmlSinks >= 20,
  `expected the known HTML sinks, found ${htmlSinks} (scanner broken?)`);
assert.deepEqual(htmlProblems, [],
  "an inline-script HTML sink is fed something that is not escaped");

const deskHud = readFileSync(join(SRC, "jarvis_hud.html"));
const baseHud = readFileSync(join(REPO, "jarvis-backend", "jarvis_hud.html"));
assert.ok(deskHud.equals(baseHud),
  "jarvis-desktop/src/jarvis_hud.html and jarvis-backend/jarvis_hud.html " +
  "must stay byte-identical (the page is vendored from the backend)");

// The judge itself: these are the bugs the 2026-10-20 audit found, and a raw
// value added to a reviewed card, so a judge that stopped biting is visible.
assert.ok(judgeHtml("x.html", "modelText", true),
  "a bare variable into innerHTML must fail");
const lanesCard = (attr) =>
  `all.map(l => \`<button class="lane" ${attr}>\`)`;
assert.ok(judgeHtml("jarvis_hud.html",
  lanesCard('data-lane="${l.id}"'), true),
  "an unescaped attribute interpolation must fail (this was a real one)");
assert.equal(judgeHtml("jarvis_hud.html",
  lanesCard('data-lane="${apprEscape(l.id)}"'), true), null);
assert.ok(judgeHtml("faces.html",
  '`<span class="sw" style="background:${swatchFor(st.id)}"></span>${evil}`', true),
  "a new unlisted interpolation at a reviewed site must fail");
assert.ok(judgeHtml("jarvis_hud.html",
  'el.insertAdjacentHTML("beforeend", html)', false),
  "a call-style sink must fail");

console.log(`ok: ${total} inline script blocks, none new; no inline handlers or ` +
  `javascript: URLs; ${htmlSinks} HTML-inline sinks escaped or reviewed; ` +
  `jarvis_hud.html twin identical`);

