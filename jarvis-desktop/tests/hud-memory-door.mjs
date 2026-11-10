/**
 * The Memory tab's pending-card door - the half that needs no browser.
 *
 * The page half is `jarvis-desktop/src/jarvis_hud.html` (vendored byte-for-byte
 * into the backend folder). These checks hold the pieces a browser test cannot
 * misread: the queue read is the phone's own two-flag read, the four kind
 * words are exact, Dismiss is ONE shared local function used by the banner and
 * the list, Review uses the existing `open_fix_place` navigation and invents no
 * "memory" place, the ONE new Keep is drawn only on a plain new fact and sends
 * exactly one integer id with accept:true, every other memory write is still
 * absent, and the hidden state draws the sentence and no titles. `hud.mjs`
 * drives the same page in a browser for the visual half.
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

check("the Memory panel has its own list, refusal line, empty sentence and hidden sentence", () => {
  assert.match(HUD, /id="memory-door"/);
  assert.match(HUD, /id="memory-door-list"/);
  assert.match(HUD, /id="memory-door-note" role="status"/);
  assert.match(HUD, /id="memory-door-empty"/);
  assert.match(HUD, /id="memory-door-hidden"/);
  assert.match(HUD, /id="memory-door-where"/);
});

check("the Memory panel's own line tells the truth about the Keep it draws", () => {
  // DEF-064 (2026-11-10): the old line sent the owner to the Brain window to
  // decide every card, while this very plate draws the ONE Keep for a plain
  // new fact (memoryDoorKeepable) and posts that decision from here. The line
  // and the button must not contradict each other.
  const line = (HUD.match(/id="memory-door-where">([^<]*)</) || [])[1] || "";
  assert.match(line, /Keep a plain new fact here/,
    "the Memory panel's line does not say its Keep lives here");
  assert.match(line, /anything else is decided in the Memory tab in the Brain window/,
    "the Memory panel's line does not say where the other cards are decided");
  assert.doesNotMatch(line, /decide each card there/,
    "the Memory panel's line still sends every card away");
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

check("Keep is drawn only for a plain new fact, and only from the one rule", () => {
  // The owner's ruling (2026-11-09, "Keep on plain facts only"): a card the
  // Brain would warn about is not decided here. The rule is in the Brain's own
  // terms - a NEW FACT, no flags, no replacement, not the sleep offer - and it
  // is applied ONCE, in paintMemoryDoor, never beside the button.
  assert.match(DOOR, /function memoryDoorKeepable\(row\)/);
  assert.match(DOOR, /source === "feedback_retire"\) return false/);
  assert.match(DOOR, /if\(rid !== null && rid !== undefined[\s\S]{0,90}return false;/);
  assert.match(DOOR, /if\(!Array\.isArray\(row\.flags\) \|\| row\.flags\.length > 0\) return false/);
  assert.match(DOOR, /String\(row\.id\) === "sleep_offer"\) return false/);
  assert.match(DOOR, /return memoryDoorKind\(row\) === "New fact"/);
  assert.match(DOOR, /keep: memoryDoorKeepable\(row\)/);
  assert.match(DOOR, /if\(card\.keep === true\)/);
  // The offer never carries a keep field, so it can never grow a button.
  assert.match(DOOR, /return \{ id:"sleep_offer", kind:"Sleep offer",/);
});

check("one Keep is ONE POST of one integer id with accept:true, and nothing else", () => {
  // Exactly one mention of the route, one POST, one body shape, and the shell
  // header this page always sends. No list, no "keep all", no second call.
  // One CALL, not one mention: the block's own comment names the route, and a
  // second call is what would be a second door.
  assert.equal((DOOR.match(/jfetch\("\/api\/memory\/decide"/g) || []).length, 1,
    "the door calls the decision route more than once");
  assert.match(DOOR, /method: "POST",/);
  assert.match(DOOR, /body: JSON\.stringify\(\{ id: id, accept: true \}\)/);
  assert.match(DOOR, /"Content-Type": "application\/json", "X-Jarvis-Client": "hud"/);
  assert.equal((DOOR.match(/accept: true/g) || []).length, 1,
    "the door sends more than one accept");
  assert.equal((DOOR.match(/jfetch\(/g) || []).length, 2,
    "the door should fetch only the queue read and the one decision");
  // A stale link holds the press before anything is sent (rule 4), and the
  // page's signal is the shell's own push.
  assert.match(DOOR, /function memoryDoorLinkStale\(\)/);
  assert.match(DOOR, /window\.__hudLinkStatus/);
  assert.match(DOOR, /if\(memoryDoorLinkStale\(\)\)\{[\s\S]*?return;/);
  // Success removes the row locally; a refusal keeps it and says the PC's
  // own sentence. The button is only re-enabled on the failure path.
  assert.match(DOOR, /if\(r\.ok && j && j\.ok !== false\)\{[\s\S]*?memoryDismiss\(li\)/);
  assert.match(DOOR, /memoryDoorNote\(memoryDoorRefusal\(j, r\.status\)\)/);
  assert.match(DOOR, /button\.disabled = false/);
});

check("every OTHER memory decision, approval and send route is still absent", () => {
  for (const route of ["/api/memory/keep_both", "/api/memory/sleep_time",
                       "/api/memory/forget", "/api/memory/erase", "/api/memory/edit",
                       "/api/memory/profile", "/api/memory/shared",
                       "/api/approve", "/api/deny", "/api/files/send"]) {
    assert.ok(!DOOR.includes(route), `${route} is referenced by the HUD's memory door`);
  }
  // One POST, the decide. A second one anywhere in the block is a second door.
  assert.equal((DOOR.match(/method: "POST"/g) || []).length, 1,
    "the door POSTs more than the one decision");
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
console.log(`\n${11 - fails.length} passed, 0 failed`);
