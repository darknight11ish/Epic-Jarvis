/**
 * hud-galaxy-options.mjs - the ONE Galaxy options surface, in the HUD page's
 * own source, without a browser.
 *
 *     node tests/hud-galaxy-options.mjs
 *
 * The owner, 2026-10-27, in their own words:
 *
 *   "i would to simplify all the galaxy options in the screenshot im attaching
 *    to have it under Galaxy options"
 *   "have that as a new icon on the left column of the jarvis hud"
 *   "and an option next to the word telemetry"
 *   "also add presets as a word in the right order next to the galaxy,
 *    approvals, reminders and other menu options"
 *   "also, add an option to hide the galaxy under the Galaxy Options menu"
 *
 * WHAT THIS PROVES. The picture-driving half is driven for real by
 * tests/hud-galaxy-looks.mjs (which needs Playwright). This suite is the half
 * that runs anywhere, in a second, and catches the structural failures:
 *
 *   1. the three byte-identical copies of the page still agree (a change to
 *      one copy only is the failure backend/test_base_matches_repo.py catches
 *      in CI, and there is no reason to wait for it);
 *   2. every galaxy-only control that used to float over the picture is inside
 *      #galaxy-options now, and NONE of them is still on the stage;
 *   3. the surface has a door in the left column (the dock's new icon), a word
 *      beside Telemetry in the stage words row, and a word beside the Telemetry
 *      toggle in the other shells - and the words row reads Galaxy, Approvals,
 *      Reminders, Memory, Telemetry, Galaxy options, Presets, in that order;
 *   4. "Presets" is wired as a door to the ONE existing Presets menu
 *      (hud-presets.js), never a second menu;
 *   5. Hide the galaxy is a device-local VIEW preference: it writes
 *      `jarvis.galaxy.hidden`, marks <html data-galaxy-hidden>, stops the one
 *      drawing loop, leaves a way back in the panel AND on the map's place
 *      holder, and clears the key when the galaxy comes back. No route, no
 *      command, no approval card, no backend.
 *
 * Nothing here judges how it looks; the owner's screen judges that, and the
 * PR says so.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const HUD = read("src/jarvis_hud.html");
const PRESETS = read("src/hud-presets.js");

const fails = [];
const check = (name, fn) => {
  try {
    fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/** The source between two markers, both of which must exist. */
function between(source, start, end, span = 4000) {
  const at = source.indexOf(start);
  assert.notEqual(at, -1, `"${start}" is not in the file`);
  const stop = source.indexOf(end, at);
  assert.notEqual(stop, -1, `"${end}" does not follow "${start}"`);
  return source.slice(at, Math.min(stop, at + span));
}

/* ── 1. The three copies ─────────────────────────────────────────────────── */

check("the three copies of the HUD page are byte-identical", () => {
  const sha = (text) => createHash("sha256").update(text, "utf8").digest("hex");
  const first = sha(HUD);
  for (const path of ["../backend/jarvis_hud.html", "../jarvis-backend/jarvis_hud.html"]) {
    assert.equal(sha(read(path)), first,
      `${path} is not byte-identical to src/jarvis_hud.html`);
  }
});

/* ── 2. One surface, every galaxy control inside it ──────────────────────── */

check("the Galaxy options panel exists once and holds every galaxy-only control", () => {
  assert.equal((HUD.match(/id="galaxy-options"/g) || []).length, 1,
    "the page declares more than one #galaxy-options");
  const panel = between(HUD, 'id="galaxy-options"', "</section>", 12000);
  assert.match(panel, /role="dialog"/, "the panel is not a dialog");
  assert.match(panel, /aria-labelledby="galaxy-options-title"/,
    "the panel has no accessible name");
  assert.match(panel, />Galaxy options</, "the panel does not say 'Galaxy options'");
  for (const id of ["gsearch", "g-reset", "g-spin", "galaxy-look-pick",
    "galaxy-look", "galaxy-counts", "galaxy-hide", "galaxy-show",
    "galaxy-options-close"]) {
    assert.ok(panel.includes(`id="${id}"`), `#${id} is not in the one panel`);
  }
  assert.equal((panel.match(/data-galaxy-lens=/g) || []).length, 3,
    "the three lenses are not in the panel");
  for (const label of ["Memory", "Neural", "Unified", "Reset view", "Pause spin",
    "Search the brain…"]) {
    assert.ok(panel.includes(label), `the panel lost "${label}"`);
  }
});

check("nothing galaxy-only is still loose on the stage", () => {
  const brain = between(HUD, 'id="brain"', "</section>", 9000);
  for (const id of ["gsearch", "g-reset", "g-spin", "galaxy-look", "galaxy-counts"]) {
    assert.ok(!brain.includes(`id="${id}"`),
      `#${id} is still on the stage as well as in the panel`);
  }
  for (const lens of ["data-galaxy-lens", "lens-group"]) {
    assert.ok(!brain.includes(lens), `the stage still draws the lenses (${lens})`);
  }
  assert.ok(!brain.includes("brain-search"),
    "the old floating galaxy bar class is still on the stage");
});

/* ── 3. The doors, and the words order ───────────────────────────────────── */

check("the dock's new icon is the left-column door, after the five sections", () => {
  const dock = between(HUD, 'id="studio-dock"', "</nav>", 4000);
  assert.match(dock, /id="dock-galaxy-options"/,
    "the Studio dock has no Galaxy options icon");
  assert.ok(dock.indexOf('id="dock-galaxy-options"')
    > dock.indexOf('data-hud-tab-choice="telemetry"'),
  "the new icon is not last in the dock's order");
  const button = between(dock, 'id="dock-galaxy-options"', "</button>", 600);
  assert.match(button, /aria-haspopup="dialog"/, "the icon does not say it opens a dialog");
  assert.match(button, /aria-label="Galaxy options/, "the icon has no plain accessible name");
  assert.doesNotMatch(button, /data-hud-tab-choice/,
    "the icon became a sixth section tab - it opens a menu, not a panel");
});

check("the stage words read Galaxy, Approvals, Reminders, Memory, Telemetry, Galaxy options, Presets", () => {
  const tabs = between(HUD, 'id="stage-tabs"', "</div>", 3000);
  const tabWords = [...tabs.matchAll(/data-hud-tab-choice="([a-z]+)"[^>]*>([^<]+)<\/button>/g)]
    .map((m) => m[2].trim());
  assert.deepEqual(tabWords, ["Galaxy", "Approvals", "Reminders", "Memory", "Telemetry"],
    "the five section tabs changed");
  const words = between(HUD, 'id="stage-words"', "</div>", 1200);
  const wordsList = [...words.matchAll(/<button\b[^>]*>([^<]+)<\/button>/g)]
    .map((m) => m[1].trim());
  assert.deepEqual(wordsList, ["Galaxy options", "Presets"],
    "the words row does not end with Galaxy options, then Presets, in that order");
  assert.ok(HUD.indexOf('id="stage-words"') > HUD.indexOf('data-hud-tab-choice="telemetry"'),
    "the words do not sit after the Telemetry tab");
  assert.match(words, /id="stage-galaxy-options"/, "the Galaxy options word is gone");
  assert.match(words, /id="stage-presets"/, "the Presets word is gone");
  // They are menu doors, not tabs (a tablist holds only tabs).
  assert.doesNotMatch(words, /data-hud-tab-choice/,
    "a menu word is wired as a stage tab");
});

check("a second word sits beside the Telemetry toggle in the other shells", () => {
  assert.match(HUD, /id="stage-bar-galaxy-options"[\s\S]{0,240}>Galaxy options</,
    "the stage bar has no Galaxy options word");
  assert.match(HUD,
    /html\[data-hud-shell="split-stage"\] #stage-bar-galaxy-options\{display:none;\}/,
    "the Studio shell would draw two Galaxy options words beside Telemetry");
});

check("the rail carries the same left-column icon in the shells without a dock", () => {
  assert.match(HUD,
    /<button type="button" class="rail-menu-mode" id="rail-galaxy-options"/,
    "the rail's Galaxy options door does not wear its own menu style");
  const button = between(HUD, 'id="rail-galaxy-options"', "</button>", 1200);
  assert.match(button, /aria-haspopup="dialog"/,
    "the rail's door does not say it opens a dialog");
  assert.match(button, /aria-label="Galaxy options/, "the rail door has no accessible name");
  assert.doesNotMatch(button, /data-view=|role="tab"|aria-selected=/,
    "the rail door claims to be a view or a tab - it opens a menu");
  assert.match(HUD, /html\[data-hud-shell="split-stage"\] \.rail-menu-mode\{display:none;\}/,
    "the Studio shell would show both left-column Galaxy options icons");
});

/* ── 4. The Presets word is a door to the ONE menu ───────────────────────── */

check("Presets uses the existing one-door event and opens no second menu", () => {
  assert.equal((HUD.match(/id="hud-presets-menu"/g) || []).length, 0,
    "the page declares its own Presets menu");
  assert.ok(PRESETS.includes('doc.getElementById("stage-presets")'),
    "hud-presets.js does not find the stage's Presets word");
  const door = between(PRESETS, 'stageDoor.dataset.hudPresets !== "1"', "});", 900);
  assert.match(door, /win\.dispatchEvent\(new CustomEvent\("jarvis:hud-presets-open"/,
    "the stage word does not dispatch the badge's own event");
  assert.match(door, /detail:\s*\{\s*anchor:\s*stageDoor\s*\}/,
    "the stage word does not carry itself as the anchor");
  assert.equal((PRESETS.match(/menu\.id = MENU_ID/g) || []).length, 1,
    "hud-presets.js no longer creates exactly one menu");
  assert.ok(PRESETS.includes("stageDoor.contains(target)"),
    "the stage word is not exempt from the menu's outside-click dismiss");
});

/* ── 5. Hide the galaxy: device-local, reversible, no route ─────────────── */

check("Hide the galaxy is a checkbox in the panel", () => {
  const panel = between(HUD, 'id="galaxy-options"', "</section>", 12000);
  assert.match(panel, /<input type="checkbox" id="galaxy-hide">/,
    "there is no Hide the galaxy checkbox");
  assert.match(panel, /<span>Hide the galaxy<\/span>/, "the checkbox has no visible word");
  assert.match(panel, /id="galaxy-show"[^>]*hidden>Show the galaxy</,
    "the panel has no way back");
});

check("the hide preference is device-local and read before the map runs", () => {
  const script = between(HUD, "function galaxyOptions()", "}());", 9000);
  assert.match(script, /jarvis\.galaxy\.hidden/,
    "the hide choice has no localStorage key");
  assert.match(script, /localStorage\.setItem\(HIDDEN_KEY, "1"\)/,
    "hiding does not remember the choice");
  assert.match(script, /localStorage\.removeItem\(HIDDEN_KEY\)/,
    "showing the galaxy does not clear the choice");
  assert.match(script, /toggleAttribute\("data-galaxy-hidden", hidden\)/,
    "nothing marks the page as hiding the galaxy");
  assert.match(script, /galaxy\.syncRunning\(\)/,
    "the one drawing loop is not stopped/started with the hide");
  assert.match(script, /applyHidden\(storedHidden\(\), false\)/,
    "the stored choice is not applied at boot");
  for (const id of ["galaxy-hide", "galaxy-show", "galaxy-show-placeholder"]) {
    assert.ok(script.includes(id), `#${id} has no handler`);
  }
  assert.doesNotMatch(script, /jfetch|fetch\(|invoke\(/,
    "hiding the galaxy reaches the network or a Tauri command");
  // One attribute, one CSS home: the picture and its furniture, not the mode.
  assert.match(HUD, /html\[data-galaxy-hidden\] #brain > #galaxy,/,
    "the CSS does not hide the galaxy canvas");
  assert.match(HUD, /html\[data-galaxy-hidden\] \.galaxy-off\{display:flex !important;\}/,
    "the place holder does not come back when the galaxy is hidden");
});

check("the drawing loop treats a hidden galaxy as a reason to stop", () => {
  const shouldRun = between(HUD, "function shouldRun(){", "}", 600);
  assert.match(shouldRun, /data-galaxy-hidden/,
    "shouldRun() does not know the galaxy can be hidden");
});

/* ── 7. The look is SHARED now (2026-10-28) ──────────────────────────────── */

// The owner: "including changing the jarvis face model and galaxy models".
// The look used to be this device's own `localStorage` key and nothing else.
// It is now `galaxy` in the same appearance document the face uses, so the
// phone draws it and the Brain window can see it. The browser half of this
// (a look really repaints the picture) is tests/hud-galaxy-looks.mjs; these are
// the structural halves that run anywhere, in a second.

check("the Look switch writes the shared look through ONE command", () => {
  const setLook = between(HUD, "function setLook(id, tellPc){", "\n  }", 2400);
  assert.match(setLook, /lookRemember\(want\)/,
    "the switch stopped remembering the choice on this device (a plain browser has no shell)");
  assert.match(setLook, /__jarvisGalaxyLook/,
    "the switch does not tell the PC, so the phone cannot follow it");
  // The one write is a command and an id. No route, no token, no whole document.
  assert.doesNotMatch(setLook, /fetch\(|jfetch|postAppearance|set_appearance/,
    "the Look switch writes a document or reaches the network instead of the one narrow command");
  assert.match(PRESETS, /export async function setGalaxyLookOnPc\(win, id\)/,
    "hud-presets.js has no setGalaxyLookOnPc()");
  assert.match(PRESETS, /call\("hud_set_galaxy_look", \{ look: id \}/,
    "setGalaxyLookOnPc() does not send exactly one look id through hud_set_galaxy_look");
});

check("a look chosen elsewhere arrives on the appearance event", () => {
  // The adoption lives in the module that OWNS the look (`adoptLook`, beside
  // lookStored), not in the reactor's `adopt()`. It used to sit in `adopt()`,
  // which is another function's scope: `lookEngine`, `lookId` and `setLook`
  // were not in it, so every push threw ReferenceError and the switcher never
  // painted at all (measured 2026-10-29 by tests/hud.mjs and
  // hud-galaxy-looks.mjs). What this check pins is the BEHAVIOUR - a pushed
  // document applies the look and is not written back - wherever the code that
  // does it lives.
  const adopt = between(HUD, "function adoptLook(){", "\n  }", 900);
  assert.match(adopt, /ownerLook\(\)/,
    "the page ignores the document's galaxy, so a look chosen on the phone never reaches this window");
  assert.match(adopt, /setLook\(want, false\)/,
    "the page applies the document's look either not at all or by writing it back");
  assert.match(HUD, /addEventListener\("jarvis-appearance", adoptLook\)/,
    "nothing listens for the appearance event, so a pushed look never arrives");
  // The shared value WINS over this device's key, or the phone's choice would
  // be overwritten by whatever this window last stored.
  const stored = between(HUD, "function lookStored(){", "\n  }", 900);
  assert.match(stored, /storedPreset\(shared\)/,
    "lookStored() still prefers this device's own key over the owner's shared look");
});

check("a look the PC did not take is SAID, not left silent", () => {
  assert.ok(HUD.includes('id="galaxy-look-note"'),
    "there is no status line for a look that stayed on this device");
  assert.match(HUD, /Saved on this device\. The PC could not be told/,
    "a failed look save says nothing, so the window claims a sync it did not get");
});

console.log();
if (fails.length) {
  console.log(`${fails.length} FAILED:`);
  for (const name of fails) console.log(`  - ${name}`);
  process.exit(1);
}
console.log("Every HUD Galaxy options check passed.");
