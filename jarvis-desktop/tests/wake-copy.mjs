/**
 * User-facing copy may only claim the wake phrase that actually ships.
 *
 * The owner's ruling of 2026-11-21 (Gemini's ruling 7; recorded in
 * decisions.d/2026-11-21-wake-copy-hey-jarvis.md):
 *
 *   "Standardize on `Hey Jarvis` everywhere until `Hey Atlas` actually ships.
 *    Drop `Hey Atlas is in training` from user-facing guides and in-app
 *    Settings copy - users shouldn't read about an unshipped model in daily UI.
 *    Keep the copy simple and factual: 'Wake phrase: Hey Jarvis.'"
 *
 * This suite is the guard, so the promise cannot come back quietly in a later
 * wording pass. It reads the copy a person actually sees - the desktop's own
 * pages, the strings its modules inject, the feature list, and README.md -
 * and it FAILS when that copy names "Hey Atlas" or says a wake phrase is in
 * training / being trained.
 *
 * WHAT IS DELIBERATELY ALLOWED, because the ruling says so: code comments and
 * dated records may still explain the history. So this suite scans only the
 * DISPLAYED text: HTML comments are removed before scanning, and a JavaScript
 * file is read down to its string literals (a comment between two quotes is
 * not a string). docs/ and decisions.d/ are records, not user-facing copy, and
 * are not scanned at all.
 *
 * WHAT IS NOT SCANNED, AND WHY (Gemini's ruling 5.4, 2026-11-21): the ruling is
 * that a wake-copy guard scans the new-user guide's SOURCE Markdown or
 * template, never the built PDF. There is no guide source in this repository
 * today - the 2026-11-21 guide was built outside the tree and only its PDF
 * exists - so there is no file here for this suite to read. That gap is said
 * plainly instead of being covered by a check that could not read anything.
 * When the guide's source lands in this repository, add it to COPY_FILES and
 * the same refusals apply to it; the binary PDF is never parsed in CI.
 *
 * Browser-free on purpose: it imports no Playwright, so it runs at a desk and
 * in CI's frontend job alike.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, extname, join, relative } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..");
const SRC = join(HERE, "..", "src");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── What counts as user-facing copy ─────────────────────────────────────── */

/** The desktop frontend's copy files: pages, the modules that write their
 *  words, and the generated feature list. */
function walkFrontend(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walkFrontend(full));
    else if ([".html", ".js", ".json"].includes(extname(entry))) out.push(full);
  }
  return out;
}

const COPY_FILES = [
  ...walkFrontend(SRC),
  // The README is the first user guide a person reads (the same ruling covers
  // it); a dated record or a design document may explain the history and is
  // never scanned here.
  join(REPO, "README.md"),
].sort();

/* ── Read each file down to what a person can see ────────────────────────── */

/** A JavaScript file reduced to the text of its string literals. Comments -
 *  where the ruling allows the history to be explained - never survive this. */
function jsStrings(src) {
  const strings = [];
  let quote = null;
  let buf = "";
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (quote) {
      if (c === "\\") { buf += c + (next || ""); i += 2; continue; }
      if (c === quote) { strings.push(buf); buf = ""; quote = null; i += 1; continue; }
      buf += c;
      i += 1;
      continue;
    }
    if (c === "/" && next === "/") { while (i < src.length && src[i] !== "\n") i += 1; continue; }
    if (c === "/" && next === "*") {
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) i += 1;
      i += 2;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") { quote = c; i += 1; continue; }
    i += 1;
  }
  return strings.join("\n");
}

/** An HTML page's visible text, with `<!-- ... -->` comments removed: the
 *  history may be explained in a comment, never shown. */
function htmlText(src) {
  return src.replace(/<!--[\s\S]*?-->/g, "");
}

/** The copy in one file, with its line offsets kept by a same-length blanking
 *  of what is not copy (so every failure can quote the copy's own line). */
function displayedCopy(full) {
  const raw = readFileSync(full, "utf8");
  const ext = extname(full);
  if (ext === ".js") return jsStrings(raw);
  if (ext === ".html") return htmlText(raw);
  return raw; // .json and .md: every string is copy
}

/* ── The ruling, as executable checks ────────────────────────────────────── */

const FORBIDDEN = [
  {
    re: /hey atlas/i,
    why: "names a wake phrase the shipped spotter cannot hear (the ruling says Hey Jarvis until the model ships)",
  },
  {
    re: /\bin training\b/i,
    why: "tells the owner a model is in training - the ruling drops that from user-facing copy",
  },
  {
    re: /\bbeing trained\b/i,
    why: "promises a wake phrase that is still being trained",
  },
  {
    re: /spoken name is atlas/i,
    why: "promises an unshipped spoken name",
  },
];

check(`every user-facing copy file is readable (${COPY_FILES.length} files)`, () => {
  assert.ok(COPY_FILES.length > 50, `only ${COPY_FILES.length} copy files found - the walk is broken`);
  for (const file of COPY_FILES) displayedCopy(file);
});

check("no user-facing copy names \"Hey Atlas\" or promises a phrase in training", () => {
  const problems = [];
  for (const file of COPY_FILES) {
    const text = displayedCopy(file);
    const lines = text.split("\n");
    for (const rule of FORBIDDEN) {
      lines.forEach((line, index) => {
        if (rule.re.test(line)) problems.push(`${relative(REPO, file)}:${index + 1} - ${rule.why}\n        ${line.trim()}`);
      });
    }
  }
  assert.equal(problems.length, 0, `the ruling is broken in user-facing copy:\n      ${problems.join("\n      ")}`);
});

check("Settings states the wake phrase as the ruling's factual sentence", () => {
  const settings = displayedCopy(join(SRC, "settings.html"));
  assert.ok(settings.includes("Wake phrase: Hey Jarvis."),
    "settings.html no longer says \"Wake phrase: Hey Jarvis.\" - Settings must state the phrase simply and factually");
});

check("the bar's wake-word control still names the phrase that ships", () => {
  const bar = displayedCopy(join(SRC, "index.html"));
  assert.match(bar, /hey Jarvis/i, "the bar's wake control no longer names \"Hey Jarvis\"");
});

if (fails.length) console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
else console.log("\nThe wake-phrase copy tells the truth");
process.exit(fails.length ? 1 : 0);
