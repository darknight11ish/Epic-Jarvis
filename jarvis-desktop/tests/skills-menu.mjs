/**
 * Settings -> "Skills": the skills menu (the owner's decision of 2026-11-02,
 * scope B; skills-menu-settings.js, skills-menu-rules.js, skills_menu.rs,
 * settings.html; backend/jarvis_skill_menu.py, plugins/ready/skill-menu/;
 * JARVIS-API.md section 177).
 *
 * Part 1 holds the pure rules to what they promise: the owner's sentence about
 * a `scripts/` folder word for word, a refused skill never offered for import,
 * and only the PC's own words shown. Part 2 reads the page, the Rust and the
 * permission tables for the wiring, and for what must NOT be there: no
 * download, no marketplace, no "install all", no second removal path.
 *
 * No browser is needed for either.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as R from "../src/skills-menu-rules.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

let failed = 0;
let passed = 0;
const check = async (name, fn) => {
  try {
    await fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── 1. The owner's sentence, word for word ─────────────────────────────── */

await check("the scripts/ sentence is the owner's, character for character", () => {
  assert.equal(
    R.inertLine(3),
    "Imported SKILL.md instructions (3 file(s) in scripts/ are kept inert and never run " +
      "automatically).",
  );
  assert.equal(
    R.inertLine(1),
    "Imported SKILL.md instructions (1 file(s) in scripts/ are kept inert and never run " +
      "automatically).",
  );
});

await check("no scripts/ folder means no sentence about one", () => {
  for (const n of [0, -1, null, undefined, "x", NaN]) {
    assert.equal(R.inertLine(n), "", String(n));
  }
});

/* ── 2. The PC's answers, made safe for the page ────────────────────────── */

await check("a skill's row keeps the PC's own sentence, and builds it from the count", () => {
  const view = R.menuView({
    ok: true,
    skills: [
      { name: "a", scripts: 2, inert: "" },
      { name: "b", scripts: 0 },
      { name: "c", scripts: 1, inert: "the PC's own words" },
    ],
    off: [],
    hermes: { available: true, root: "C:\\Users\\x\\.hermes\\skills" },
  });
  assert.equal(view.skills.length, 3);
  assert.ok(view.skills[0].inert.includes("(2 file(s) in scripts/"));
  assert.equal(view.skills[1].inert, "");
  assert.equal(view.skills[2].inert, "the PC's own words");
  assert.equal(view.hermes.available, true);
});

await check("an answer that is not a menu is refused rather than shown", () => {
  for (const bad of [null, undefined, {}, [], "skills", 0]) {
    assert.equal(R.menuView(bad), null, JSON.stringify(bad));
  }
});

await check("a PC without the module says which command to run, never an HTTP code", () => {
  const view = R.menuView({ ok: false, reason: "jarvis_skills.py is not beside this file" });
  assert.equal(view.available, false);
  assert.ok(view.why.includes("jarvis_skills.py"));
  assert.ok(!/HTTP \d/.test(view.why));
  assert.ok(R.refusedWords("HTTP 404 Not Found").includes("apply-patches.ps1"));
  assert.ok(!/HTTP \d/.test(R.refusedWords(new Error("HTTP 503"))));
});

await check("a scan shows the verdict, the findings and whether warnings must be accepted", () => {
  const clean = R.scanView({
    ok: true,
    name: "a-skill",
    verdict: "clean",
    summary: "a-skill is clean: nothing in it matches a known attack pattern.",
    findings: [{ severity: "note", code: "no_license", message: "no license field" }],
    scripts: 1,
    needs_warnings: false,
  });
  assert.equal(clean.verdict, "clean");
  assert.equal(clean.blocking.length, 0);
  assert.equal(clean.warnings.length, 0);
  assert.equal(clean.needsWarnings, false);
  assert.ok(clean.inert.includes("(1 file(s) in scripts/"));
  const warned = R.scanView({
    ok: true,
    verdict: "review",
    findings: [{ severity: "warn", code: "raw_ip_url", message: "downloads from a bare IP" }],
    needs_warnings: true,
  });
  assert.equal(warned.warnings.length, 1);
  assert.equal(warned.needsWarnings, true);
  const refused = R.scanView({ ok: false, verdict: "refuse", reason: "was refused" });
  assert.equal(refused.ok, false);
  assert.equal(refused.reason, "was refused");
});

await check("a refused Hermes skill is listed and CANNOT be imported", () => {
  const view = R.importView({
    ok: true,
    available: true,
    found: [
      { folder: "ok-one", name: "ok-one", verdict: "clean", scripts: 0 },
      { folder: "warn-one", name: "warn-one", verdict: "review", scripts: 1 },
      { folder: "bad-one", name: "bad-one", verdict: "refuse", scripts: 0 },
      { folder: "odd-one", name: "odd-one", verdict: "malformed", scripts: 0 },
    ],
  });
  assert.equal(view.folders.length, 4);
  const by = Object.fromEntries(view.folders.map((f) => [f.folder, f]));
  assert.equal(by["ok-one"].canImport, true);
  assert.equal(by["warn-one"].canImport, true);
  assert.equal(by["bad-one"].canImport, false);
  assert.equal(by["odd-one"].canImport, false);
});

await check("the answer's own words are what is shown, and a cancel says nothing", () => {
  assert.equal(R.answerWords({ ok: true, message: "a-skill installed" }), "a-skill installed");
  assert.equal(R.answerWords({ ok: false, reason: "read it first" }), "read it first");
  assert.equal(R.answerWords({ cancelled: true }), "");
  assert.equal(R.answerWords({ ok: true }), "Done.");
});

/* ── 3. The page, the Rust, and the permission tables ───────────────────── */

const PAGE = read("src/skills-menu-settings.js");
const RULES = read("src/skills-menu-rules.js");
const HTML = read("src/settings.html");
const RUST = read("src-tauri/src/skills_menu.rs");
const LIB = read("src-tauri/src/lib.rs");
const SURFACES = read("src-tauri/permissions/surfaces.toml");
const CAPS = read("src-tauri/capabilities/settings.json");

await check("the Rust plans exactly the actions the page knows about", () => {
  const arms = [...RUST.matchAll(/"([a-z_]+)"\s*(?:\||=>)/g)].map((m) => m[1]);
  const got = new Set(arms.filter((a) => R.ACTIONS.includes(a)));
  assert.deepEqual([...got].sort(), [...R.ACTIONS].sort());
});

await check("the three doors that raise a card are the ones held on a stale link", () => {
  assert.deepEqual(R.CARD_ACTIONS.slice().sort(), ["edit", "enable", "install"]);
  assert.ok(RUST.includes('matches!(action, "install" | "enable" | "edit")'));
});

await check("the page asks its one command, and removes through the PC's existing one", () => {
  assert.ok(PAGE.includes('invoke("skills_menu"'));
  assert.ok(PAGE.includes('invoke("brain_remove_skill"'));
  for (const bad of ["fetch(", "XMLHttpRequest", "http://", "https://", "download("]) {
    assert.ok(!PAGE.includes(bad), `the page must not contain ${bad}`);
  }
});

await check("no download, no marketplace and no auto-install anywhere", () => {
  for (const text of [PAGE, RULES, RUST]) {
    for (const bad of ["clawhub", "skills.sh", "os.system", "subprocess", "Popen(",
                       "http://", "https://"]) {
      assert.ok(!text.toLowerCase().includes(bad.toLowerCase()), `found ${bad}`);
    }
  }
  // The denials themselves ("no marketplace", "no auto-install") are worth
  // having on the page, so the word alone is not the test: what must not exist
  // is the machinery. No action can ever mean "go and get one".
  for (const action of R.ACTIONS) {
    assert.ok(!/download|fetch|remote|hub|market/i.test(action), `no remote action: ${action}`);
  }
});

await check("there is no bulk control: one skill, one button, one card", () => {
  // Not a prose check: a "yes to all" needs a control, so what must not exist
  // is an id or a label for one. Every import row builds its OWN button.
  for (const html of [HTML, PAGE]) {
    for (const bad of ["sk-import-all", "sk-install-all", "sk-approve-all", "yes-to-all"]) {
      assert.ok(!html.includes(bad), `found ${bad}`);
    }
  }
  assert.ok(PAGE.includes("sk-import-list"));
  assert.equal((PAGE.match(/ask\("install"/g) || []).length, 2,
    "one install path from a picked folder/.zip, one per Hermes row");
});

await check("the window's permission is granted by the settings set and its capability", () => {
  assert.ok(SURFACES.includes('"allow-skills-menu"'));
  const at = SURFACES.indexOf('identifier = "settings-surface"');
  const next = SURFACES.indexOf('\n[[set]]', at);
  const block = SURFACES.slice(at, next === -1 ? undefined : next);
  assert.ok(block.includes('"allow-skills-menu"'), "it belongs to the settings surface");
  // The window is granted the SET (`settings-surface`) - a capability refers to
  // permission sets and allow-* ids only, never to a feature name.
  assert.ok(CAPS.includes('"settings-surface"'), "the settings window holds the set");
  assert.ok(!CAPS.includes('"skills-menu"'), "a bare feature name is not a permission");
});

await check("the command is registered with the app", () => {
  assert.ok(LIB.includes("pub mod skills_menu;"));
  assert.ok(LIB.includes("skills_menu::skills_menu,"));
});

await check("the page's own ids all exist in settings.html", () => {
  for (const id of [
    "skills-menu",
    "sk-state",
    "sk-body",
    "sk-list",
    "sk-off-title",
    "sk-off-list",
    "sk-empty",
    "sk-install-folder",
    "sk-install-zip",
    "sk-hermes",
    "sk-hermes-why",
    "sk-hermes-root",
    "sk-import-list",
    "sk-import-note",
    "sk-pick-title",
    "sk-pick-detail",
    "sk-pick-inert",
    "sk-pick-findings",
    "sk-pick-findings-none",
    "sk-pick-go",
    "sk-pick-cancel",
    "sk-edit-title",
    "sk-edit-text",
    "sk-edit-inert",
    "sk-edit-note",
    "sk-edit-save",
    "sk-edit-cancel",
    "sk-status",
  ]) {
    assert.ok(HTML.includes(`id="${id}"`), `settings.html has ${id}`);
  }
  assert.ok(HTML.includes('<script type="module" src="skills-menu-settings.js"></script>'));
});

await check("the page says what it does NOT do, in the owner's words", () => {
  assert.ok(PAGE.includes("never run"));
  assert.ok(PAGE.includes("ONE approval card") || PAGE.includes("ONE card"));
  assert.ok(HTML.includes("Nothing here installs"));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
