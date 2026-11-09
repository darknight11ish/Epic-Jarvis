/**
 * The Memory tab's pending-card door - the half that needs no browser.
 *
 * The page half is `jarvis-desktop/src/jarvis_hud.html` (vendored byte-for-byte
 * into the backend folder). These checks hold the pieces a browser test cannot
 * misread: the queue read is the phone's own two-flag read, the four kind
 * words are exact, Dismiss is ONE shared local function used by the banner and
 * the list, Review uses the existing `open_fix_place` navigation and invents no
 * "memory" place, the list references no memory-decision route, and the hidden
 * state draws the sentence and no titles. `hud.mjs` drives the same page in a
 * browser for the visual half.
 *
 * Run: node tests/hud-memory-door.mjs
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const HUD = readFileSync(join(HERE, "..", "src", "jarvis_hud.html"), "utf8");
const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const doorStart = HUD.indexOf("/* == memory door begin == */");
const doorEnd = HUD.indexOf("/* == memory door end == */");
assert.ok(doorStart >= 0 && doorEnd > doorStart, "the memory door block is not in the page");
const DOOR = HUD.slice(doorStart, doorEnd);

check("the Memory panel has its own list, empty sentence and hidden sentence", () => {
  assert.match(HUD, /id="memory-door"/);
  assert.match(HUD, /id="memory-door-list"/);
  assert.match(HUD, /id="memory-door-empty"/);
  assert.match(HUD, /id="memory-door-hidden"/);
  assert.match(HUD, /id="memory-door-where"/);
});

check("the list reads the phone's own queue read and refreshes on the banner's beat", () => {
  assert.match(DOOR, /"\/api\/memory\/pending\?retire_cards=1&sleep_offer=1"/);
  assert.match(DOOR, /"\/api\/memory\/pending\?retire_cards=1"/);
  assert.match(HUD, /__hudMemoryDoor\.beat\(\)/);
  assert.match(HUD, /__hudMemoryDoor\.tabChanged\(\)/);
});

check("the four kinds are the exact words", () => {
  assert.match(DOOR, /source === "feedback_retire"\) return "Retire"/);
  assert.match(DOOR, /String\(rid\) !== "0"[\s\S]*?return "Correction"/);
  assert.match(DOOR, /return "New fact"/);
  assert.match(DOOR, /kind:"Sleep offer"/);
});

check("Dismiss is ONE shared local function, used by the banner and the list", () => {
  assert.equal((DOOR.match(/function memoryDismiss\(/g) || []).length, 1,
    "Dismiss has more than one implementation");
  assert.match(DOOR, /function memoryDismiss\(el\)/);
  assert.match(HUD, /el\.querySelector\("\.no"\)\.onclick = \(\) => memoryDismiss\(el\)/);
  assert.match(DOOR, /memoryDismiss\(li\)/);
});

check("Review opens the Brain through the existing open_fix_place, no invented place", () => {
  assert.match(DOOR, /core\.invoke\("open_fix_place", \{place:"brain"\}\)/);
  assert.doesNotMatch(DOOR, /place\s*:\s*"memory"/);
  const places = DOOR.match(/place\s*:\s*"([^"]+)"/g) || [];
  assert.deepEqual(places, ['place:"brain"']);
});

check("the list has no memory decision, approval or send route", () => {
  for (const route of ["/api/memory/decide", "/api/memory/keep_both", "/api/memory/sleep_time",
                       "/api/memory/forget", "/api/memory/erase", "/api/memory/edit",
                       "/api/approve", "/api/deny", "/api/files/send"]) {
    assert.ok(!DOOR.includes(route), `${route} is referenced by the HUD's memory door`);
  }
  assert.ok(!/method:\s*"POST"/i.test(DOOR), "the door POSTs something");
  assert.ok(!/jfetch\([^)]*method/i.test(DOOR), "the door sends a non-GET request");
});

check("hidden mode draws the owner-independent sentence and no card titles", () => {
  assert.match(DOOR, /window\.__hudHiddenWords/);
  assert.match(DOOR, /Memory lists are hidden until you unlock\./);
  assert.match(DOOR, /hiddenEl\.textContent = hidden \? memoryHiddenSentence\(\) : ""/);
  // The rows are only built inside the not-hidden branch.
  assert.match(DOOR, /if\(!hidden\)\{[\s\S]*?MEMORY_DOOR\.rows/);
  assert.match(DOOR, /if\(!hidden\)\{[\s\S]*?listEl\.appendChild/);
});

check("every desktop read of the queue asks for retire cards (Q2 section 1.5)", () => {
  // The Brain's own route names the flag in its literal...
  const routes = readFileSync(
    join(HERE, "..", "src-tauri", "src", "brain", "routes.rs"), "utf8");
  assert.match(routes,
    /"\/api\/memory\/pending\?retire_cards=1&sleep_offer=1(&merge_cards=1)?"/,
    "the Brain's pending read stopped asking for retire cards");
  // ...and the HUD page's own three reads do too. Since ruling Q7 (2026-11-08)
  // the count-only banner read types the flag as well, so no desktop fetch of
  // this queue leaves a retire card out; hud_proxy still rebuilds a bare read
  // as the retire-aware refresh as a belt-and-braces guard.
  assert.match(DOOR, /retire_cards=1/);
  const hudPage = readFileSync(join(HERE, "..", "src", "jarvis_hud.html"), "utf8");
  assert.match(hudPage, /jfetch\("\/api\/memory\/pending\?retire_cards=1"/,
    "the HUD's count-only pending read stopped asking for retire cards");
  const proxy = readFileSync(join(HERE, "..", "src-tauri", "src", "hud_proxy.rs"), "utf8");
  assert.match(proxy, /MEMORY_PENDING_RETIRE_QUERY: &str = "retire_cards=1"/);
  assert.match(proxy,
    /None => Some\(format!\(\s*"\{MEMORY_PENDING_PATH\}\?\{MEMORY_PENDING_RETIRE_QUERY\}"\s*\)\)/,
    "a bare desktop pending read is no longer rebuilt as the retire-aware refresh");
  // A NEW call site added later must be on this list - the only files allowed
  // to name the route are the page (whose bare read the proxy normalises), the
  // proxy itself, and the Brain's route.
  // lock/rules.rs names the route only in its own redaction TEST (proving the
  // HUD's count read is not blanked while App lock is on); it fetches nothing.
  const allowed = new Set([
    "src/jarvis_hud.html",
    "src-tauri/src/hud_proxy.rs",
    "src-tauri/src/brain/routes.rs",
    "src-tauri/src/lock/rules.rs",
  ]);
  const found = new Set();
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) { walk(p); continue; }
      if (!/\.(js|html|rs)$/.test(name)) continue;
      const text = readFileSync(p, "utf8");
      // Only a path inside a STRING LITERAL is a built URL; a comment that
      // merely names the route (auto-learn.js's prose) is not a call site.
      if (!/["']\/api\/memory\/pending/.test(text)) continue;
      const rel = p.slice(join(HERE, "..").length + 1).replace(/\\/g, "/");
      found.add(rel);
      assert.ok(allowed.has(rel),
        `${rel} reads /api/memory/pending without being on the retire-aware list`);
    }
  };
  walk(join(HERE, "..", "src"));
  walk(join(HERE, "..", "src-tauri", "src"));
  assert.deepEqual([...found].sort(), [...allowed].sort(),
    "the set of files that read the memory queue changed - add the flag and this list");
});

check("the three copies of the HUD page are still byte-identical", () => {
  const here = join(HERE, "..", "src", "jarvis_hud.html");
  const backend = join(HERE, "..", "..", "backend", "jarvis_hud.html");
  const base = join(HERE, "..", "..", "jarvis-backend", "jarvis_hud.html");
  const a = readFileSync(here);
  assert.deepEqual(readFileSync(backend), a, "backend/jarvis_hud.html differs from the desktop page");
  assert.deepEqual(readFileSync(base), a, "jarvis-backend/jarvis_hud.html differs from the desktop page");
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log(`\n${8 - fails.length} passed, 0 failed`);
