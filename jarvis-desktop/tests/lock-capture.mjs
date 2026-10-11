/**
 * The desktop keeps its own windows out of a screen capture while App lock is
 * on (the owner's decision, 2026-10-11).
 *
 * The phone has done this since 2026-09-25: `FLAG_SECURE` while App lock or
 * "Hide memory lists and chat history" is on
 * (`jarvis-client/.../data/Security.kt`, `SecurityRules.blockScreenCapture`).
 * `docs/ARCHITECTURE.md` recorded the desktop as "**Undecided on the desktop -
 * the owner's call**"; the owner answered yes, so this is a decided feature and
 * not a new switch. It follows the two settings that already exist, exactly as
 * the phone's rule does.
 *
 * What this file checks, all read from the real Rust:
 *
 * - the rule is the phone's rule - App lock OR the hide-lists setting - and it
 *   is ON when the lock would ask for Windows Hello and OFF while the owner is
 *   there, so a locked screen is not capturable and an unlocked one is;
 * - it reaches every window Jarvis can put its words in, named one by one, so a
 *   window added later is a deliberate choice and not a silent hole - the
 *   floating face and the widget (the approval card) included, which are the
 *   ones that stay on screen once the lock has hidden the rest;
 * - the switch is the single Win32 call `SetWindowDisplayAffinity` with
 *   `WDA_EXCLUDEFROMCAPTURE`, never `set_content_protected` (which on Windows
 *   rebuilds the window - that closed Settings the moment a pairing succeeded,
 *   the owner's report of 2026-10-07), and never a second copy of it;
 * - the pairing panel's own capture guard (devices.rs) defers to the lock
 *   while the lock is on, so its "off" cannot clear a block the lock still
 *   wants;
 * - the two status badges - "Jarvis is watching", the Live badge - are NOT
 *   excluded: their whole job is to be seen, and a capture that missed them
 *   would hide the notice instead of the secret.
 *
 * Pure node, no browser: CI runs it (`for f in tests/*.mjs`). What it cannot
 * show is that Windows really hides the pixels - `lock.rs`'s own
 * `the_exclusion_is_real_and_reversible_on_this_pc` does that with a real
 * window and a real screen capture, on Windows, in `cargo test`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const LOCK = read("src-tauri/src/lock.rs");
const RULES = read("src-tauri/src/lock/rules.rs");
const DEVICES = read("src-tauri/src/devices.rs");
const WINDOWS = read("src-tauri/src/windows.rs");
const LIB = read("src-tauri/src/lib.rs");
const CONFIG = JSON.parse(read("src-tauri/tauri.conf.json"));

const fails = [];
let total = 0;
const check = async (name, fn) => {
  total += 1;
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** Comments out of the way, so a comment that mentions a call cannot satisfy a
 *  check for the call, and one that explains why a call is NOT used cannot
 *  break a check that it is not. */
const uncommented = (text) => text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

const CODE = uncommented(LOCK);
const RULES_CODE = uncommented(RULES);
const DEVICES_CODE = uncommented(DEVICES);
const WINDOWS_CODE = uncommented(WINDOWS);
const LIB_CODE = uncommented(LIB);

/** The body of one `fn`, by matching braces from its opening line - not by
 *  looking for the first line that is a `}` alone, which stops early on any
 *  body with a nested block of its own (a `#[cfg]`, an `if let ... { ... }`). */
function fnBody(src, opening) {
  const at = src.indexOf(opening);
  assert.ok(at >= 0, `no ${opening} in that file`);
  const open = src.indexOf("{", at);
  assert.ok(open > 0, `${opening} has no body`);
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    const c = src[i];
    if (c === '"') {                      // step over a string literal
      i += 1;
      while (i < src.length && src[i] !== '"') i += src[i] === "\\" ? 2 : 1;
      continue;
    }
    if (c === "{") depth += 1;
    else if (c === "}") {
      depth -= 1;
      if (depth === 0) return src.slice(at, i + 1);
    }
  }
  throw new Error(`${opening} has no closing brace`);
}

/** The nine labels in `SNAPSHOT_LABELS`, as written. */
function snapshotLabels() {
  const body = CODE.slice(CODE.indexOf("pub const SNAPSHOT_LABELS"));
  const list = body.slice(body.indexOf("["), body.indexOf("];") + 1);
  return [...list.matchAll(/crate::(?:windows::)?([A-Z_]+_LABEL)/g)].map((m) => m[1]);
}

/* ── the rule is the phone's rule ─────────────────────────────────────────── */

await check("both settings block a capture, and each one alone does", async () => {
  // The phone's rule is `s.appLock || s.privateLists` (Security.kt
  // blockScreenCapture). The desktop's is five lines away in lock/rules.rs.
  const rule = fnBody(RULES_CODE, "pub fn blocks_capture(&self");
  assert.match(rule, /self\.app_lock/, "App lock no longer blocks a capture");
  assert.match(rule, /self\.private_answers/, "the hide-lists setting no longer blocks a capture");
  assert.match(rule, /owner_here/, "nothing decides whether the owner is at the PC");
  assert.match(
    rule,
    /if\s+owner_here\s*\{[\s\S]*?return false/,
    "an owner sitting at their own PC must still be able to capture it",
  );
});

await check("a locked app blocks, an unlocked one does not", async () => {
  // The two cases the owner asked for, stated as the Rust states them. The
  // real proof that the setting reaches a window is the two checks below; this
  // is the rule those are wired to.
  const rule = fnBody(CODE, "pub fn capture_blocked");
  assert.match(rule, /app_locked\(app\)/, "the lock's own state is not consulted");
  assert.match(rule, /private_hidden\(app\)/, "hidden memory lists are not consulted");
  assert.match(
    rule,
    /blocks_capture\(owner_here\)/,
    "the rule in lock/rules.rs is not the one being used",
  );
  assert.match(
    CODE,
    /let owner_here = !app_locked\(app\)/,
    "the owner's presence is not taken from the lock that already decides it",
  );
});

/* ── it is turned on when it locks and off when it unlocks ───────────────── */

await check("the block is applied on lock, on unlock, and as a window appears", async () => {
  // ON when the lock turns on: the watch that already hides the covered
  // windows runs `sweep` on every tick, whatever the settings say, so a lock
  // switched on in Settings cannot be missed.
  const watch = fnBody(CODE, "pub fn spawn_watch");
  assert.match(watch, /sweep\(&app\)/, "the watch never applies the capture block");
  // ...and BEFORE the two `continue`s, or a tick with the lock off - which is
  // exactly the tick that has to clear it - would skip it.
  const sweepAt = watch.indexOf("sweep(&app)");
  const firstContinue = watch.indexOf("continue;");
  assert.ok(
    firstContinue > 0 && sweepAt < firstContinue,
    "sweep must run before the watch starts skipping, or turning the lock off leaves the block on",
  );
  // OFF when the owner comes back: the one path that follows a passed Windows
  // Hello, which is the moment `app_locked` stops being true.
  assert.match(fnBody(CODE, "fn start_unlock"), /sweep\(&app\)/, "unlocking never clears the block");
  // And a window built while the lock is already on must not wait up to five
  // seconds for the next tick.
  assert.match(
    fnBody(WINDOWS_CODE, "pub fn show_floating"),
    /crate::lock::sweep\(app\)/,
    "the floating face can appear while locked without being excluded",
  );
});

/* ── every window Jarvis puts its words in ──────────────────────────────── */

await check("every window labelled is one this app really builds", async () => {
  // The one Tauri declares...
  const declared = new Set(CONFIG.app.windows.map((w) => w.label));
  assert.ok(declared.size > 0, "no windows in tauri.conf.json");
  // ...and the ones it builds on demand, by the constants named in the list.
  const built = new Set(["quickbar", "widget", "hud", "brain", "settings", "faces",
    "features", "onboarding", "floating"]);
  const labels = snapshotLabels();
  assert.equal(labels.length, 9, `expected nine windows, found ${labels.length}: ${labels}`);
  for (const name of labels) {
    const label = { QUICKBAR_LABEL: "quickbar", HUD_LABEL: "hud", WIDGET_LABEL: "widget",
      FLOATING_LABEL: "floating", BRAIN_LABEL: "brain", SETTINGS_LABEL: "settings",
      FACES_LABEL: "faces", FEATURES_LABEL: "features", ONBOARDING_LABEL: "onboarding" }[name];
    assert.ok(label, `${name} is not a Jarvis window constant`);
    assert.ok(built.has(label), `${label} is not a window this app builds`);
    assert.ok(
      declared.has(label)
        || new RegExp(`(pub )?const ${name}\\b`).test(WINDOWS_CODE + LIB_CODE + CODE),
      `${label} is named but no constant defines it`,
    );
  }
});

await check("the windows that stay visible while locked are in the list", async () => {
  // The gap this feature closes: App lock HIDES the Jarvis bar, the Brain,
  // Settings and the HUD, but the widget and the floating face stay on screen -
  // the widget because its approval card is the point of it, the floating face
  // because the owner put it there. Both show Jarvis, so both are excluded.
  const labels = snapshotLabels();
  for (const must of ["WIDGET_LABEL", "FLOATING_LABEL", "QUICKBAR_LABEL", "HUD_LABEL",
    "BRAIN_LABEL", "SETTINGS_LABEL"]) {
    assert.ok(labels.includes(must), `${must} is not excluded from a capture`);
  }
});

await check("the badges that say Jarvis is watching are NOT excluded", async () => {
  // Deliberate, and the opposite way round from every other window here: a
  // capture that missed "Jarvis is watching" would hide the notice that Jarvis
  // is looking, which is the one thing those windows exist to say.
  const labels = snapshotLabels();
  assert.ok(!labels.includes("BADGE_LABEL"), "a watching badge is excluded from a capture");
  const live = uncommented(read("src-tauri/src/live.rs"));
  const look = uncommented(read("src-tauri/src/look.rs"));
  assert.match(live, /pub const BADGE_LABEL: &str = "live-badge"/);
  assert.match(look, /pub const BADGE_LABEL: &str = "watch-badge"/);
});

/* ── one call, the safe one, used by everyone ───────────────────────────── */

await check("the Win32 call is the direct one, and there is only one of it", async () => {
  assert.match(CODE, /SetWindowDisplayAffinity/, "the exclusion is not being applied at all");
  assert.match(CODE, /WDA_EXCLUDEFROMCAPTURE/, "the weaker WDA_MONITOR is not what was asked for");
  assert.match(CODE, /WDA_NONE/, "there is no way back to a capturable window");
  // No second implementation anywhere in the crate: two copies of this call
  // are two things to keep in step. The call's own bracket, so a comment that
  // names it does not count as one.
  for (const [name, src] of [["devices.rs", DEVICES], ["windows.rs", WINDOWS]]) {
    assert.ok(
      !/SetWindowDisplayAffinity\s*\(/.test(uncommented(src)),
      `${name} keeps its own copy of the Win32 capture call`,
    );
  }
  // And never the Tauri call that rebuilds the window - the bug that closed
  // Settings the moment a pairing succeeded (the owner, 2026-10-07).
  assert.ok(
    !/set_content_protected\s*\(/.test(uncommented(LOCK)),
    "the recreating call must not come back",
  );
});

await check("the pairing panel's own guard cannot clear the lock's block", async () => {
  // devices.rs hides the settings window while a pairing code is on screen and
  // puts it back when the panel closes. That "back" runs after a pairing ends,
  // which can be long after the owner walked away - so it must do nothing at
  // all while the lock is on.
  const guard = fnBody(DEVICES_CODE, "fn guard_capture");
  assert.match(
    guard,
    /capture_blocked\(app\)/,
    "the pairing guard no longer asks the lock before clearing",
  );
  const ask = guard.indexOf("capture_blocked(app)");
  const apply = guard.indexOf("set_affinity");
  assert.ok(ask > 0 && apply > ask, "the guard clears the block before asking the lock");
  assert.match(guard, /return;/, "the guard does not stop while the lock owns the window");
});

/* ── the honest limits, written down where the code is ─────────────────── */

await check("the code says plainly what this does not stop", async () => {
  // Not decoration: the whole point of the owner's note was that the limits be
  // stated rather than hidden, and the next person to touch this file reads the
  // code, not the doc.
  assert.match(LOCK, /camera pointed at the screen/i, "the camera is not mentioned");
  assert.match(LOCK, /Windows 10 2004/, "the Windows build this needs is not named");
  assert.match(LOCK, /whole desktop|WHOLE desktop/i, "a full-desktop capture is not mentioned");
});

const passed = total - fails.length;
console.log(`\n${passed} passed${fails.length ? `, ${fails.length} FAILED: ${fails.join(", ")}` : ""}`);
if (fails.length) process.exit(1);
