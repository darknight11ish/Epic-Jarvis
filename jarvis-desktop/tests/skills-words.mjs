/**
 * skills-words.mjs - the Brain's Skills card reports the PC's measured skill
 * state, and never guesses at a quarantine (Wave-9 Lane 2; the owner's report
 * that "No skills installed, or the scanner has quarantined them all." told
 * him nothing true).
 *
 *     node tests/skills-words.mjs
 *
 * WHAT THIS PINS, with no browser:
 *
 *   1. The count line is built from the PC's OWN `/api/skills` answer:
 *      `stats.installed` and `stats.quarantined` from `jarvis_skills.stats()`,
 *      falling back to the list's length only when the PC did not send its own
 *      total - and saying which it used.
 *   2. A count the PC did NOT report is said to be unreported. "0 quarantined"
 *      is printed only when `stats.quarantined` really is 0 - never as a
 *      default for a missing field.
 *   3. The empty state says what a quarantine IS (kept out of the load, not in
 *      the list), that it is measured, and how a skill arrives (a folder or
 *      .zip on this PC, installed from Settings, Skills with one approval
 *      card; no marketplace, no download).
 *   4. The old misleading sentence is GONE from brain.js and the card really
 *      draws these lines, through the pure module (source pins).
 *   5. The counts are read from the payload shape the backend really sends:
 *      `_skills_view()` returns `skills` + `stats` from `SK.stats()`, and
 *      `stats()` includes `quarantined`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as S from "../src/skills-words.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const REPO = join(HERE, "..", "..");
const read = (p) => readFileSync(p, "utf8");

const BRAIN = read(join(SRC, "brain.js"));
const BRAIN_HTML = read(join(SRC, "brain.html"));
const HUD_BACKEND = read(join(REPO, "jarvis-backend", "jarvis_hud.py"));
const SKILLS_BACKEND = read(join(REPO, "jarvis-backend", "jarvis_skills.py"));

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

/* ── 1. The measured zero ────────────────────────────────────────────────── */

check("an empty list with the PC's own counts says both, in the owner's words", () => {
  const body = { available: true, skills: [], stats: { installed: 0, quarantined: 0 } };
  assert.equal(S.countLine(body), "0 skills installed · 0 quarantined by the scanner.");
  const empty = S.emptyWords(body);
  assert.equal(empty.line, "0 skills installed · 0 quarantined by the scanner.");
  assert.match(empty.means, /quarantine/i);
  assert.match(empty.means, /kept out of the load/);
  assert.match(empty.means, /quarantined none/, "a measured zero is not said");
});

check("the empty state says how a skill arrives - no marketplace, no download", () => {
  const body = { skills: [], stats: { installed: 0, quarantined: 0 } };
  const arrives = S.arrivalLine();
  assert.match(arrives, /folder or a \.zip already on this PC/);
  assert.match(arrives, /Settings, Skills/);
  assert.match(arrives, /one approval card/);
  assert.match(arrives, /never downloads one/);
  assert.match(arrives, /no marketplace/);
  assert.match(S.emptyWords(body).arrives, /scanner runs first/);
});

/* ── 2. A real quarantine is counted, never guessed ──────────────────────── */

check("a quarantined folder is counted and explained, singular and plural", () => {
  const one = { skills: [{ name: "a" }, { name: "b" }], stats: { installed: 2, quarantined: 1 } };
  assert.equal(S.countLine(one), "2 skills installed · 1 quarantined by the scanner.");
  assert.match(S.meansLine(one), /1 skill is\s+quarantined/);
  const many = { skills: [], stats: { installed: 0, quarantined: 3 } };
  assert.equal(S.countLine(many), "0 skills installed · 3 quarantined by the scanner.");
  assert.match(S.meansLine(many), /3 skills are\s+quarantined/);
});

/* ── 3. What the PC did NOT report is said, never defaulted ──────────────── */

check("a missing quarantine count is never printed as zero", () => {
  const noStats = { available: true, skills: [{ name: "a" }] };
  assert.equal(S.countLine(noStats),
    "1 skill installed. (Counted from the list the PC sent, which did not report its own total.)");
  assert.doesNotMatch(S.countLine(noStats), /quarantined by the scanner/,
    "a quarantine count nobody reported was printed");
  assert.match(S.meansLine(noStats), /did not report a quarantine count/);
  const statsNoQuarantine = { skills: [], stats: { installed: 0 } };
  assert.equal(S.countLine(statsNoQuarantine), "0 skills installed.");
  assert.doesNotMatch(S.countLine(statsNoQuarantine), /0 quarantined/);
});

check("nothing readable at all says so, rather than drawing a hopeful zero", () => {
  for (const body of [null, undefined, {}, [], "skills", 0]) {
    assert.match(S.countLine(body), /did not report a skill count/);
    assert.match(S.meansLine(body), /did not report a quarantine count/);
    assert.equal(S.summaryLine(body), "");
  }
});

check("counts must be real whole numbers, or they are not used", () => {
  const weird = { skills: [], stats: { installed: "2", quarantined: -1 } };
  assert.equal(S.countLine(weird), "0 skills installed. (Counted from the list the PC sent, " +
    "which did not report its own total.)");
  assert.equal(S.skillCounts(weird).quarantined, null, "a negative count was printed");
  const floats = { skills: [], stats: { installed: 1.5, quarantined: 2.5 } };
  // A junk total falls back to the LIST the PC sent (0 here), and says so; the
  // quarantine count has no list to fall back to, so it stays unreported.
  assert.equal(S.skillCounts(floats).installed, 0);
  assert.equal(S.skillCounts(floats).installedFrom, "list");
  assert.equal(S.skillCounts(floats).quarantined, null);
});

/* ── 4. The page really draws these lines, and the old sentence is gone ──── */

check("brain.js imports and draws the pure words, and the misleading line is gone", () => {
  assert.match(BRAIN, /import \* as Skills from "\.\/skills-words\.js"/,
    "brain.js does not import the words module");
  assert.match(BRAIN, /Skills\.emptyWords\(body\)/, "the empty state is not built from the module");
  assert.match(BRAIN, /Skills\.summaryLine\(body\)/, "the summary line is not built from the module");
  assert.match(BRAIN, /el\("p", "note", honest\.means\)/);
  assert.match(BRAIN, /el\("p", "note", honest\.arrives\)/);
  assert.match(BRAIN, /line\.id = "skills-count-line"/, "the measured line has no testable id");
  assert.doesNotMatch(BRAIN, /No skills installed, or the scanner has quarantined them all/,
    "the old two-facts-joined-by-or sentence is still in brain.js");
});

check("the Skills card keeps its server-side truth about quarantined skills", () => {
  assert.match(BRAIN_HTML, /Quarantined skills are not listed/,
    "the card's own honest note about withheld skills was removed");
  assert.match(BRAIN_HTML, /id="skills"/, "the Skills list container is gone");
});

/* ── 5. The counts come from the payload the backend really sends ────────── */

check("the backend /api/skills really carries stats.quarantined", () => {
  const view = HUD_BACKEND.slice(HUD_BACKEND.indexOf("def _skills_view"),
                                 HUD_BACKEND.indexOf("def _skills_view") + 1200);
  assert.match(view, /out\["stats"\] = SK\.stats\(\)/,
    "_skills_view no longer serves SK.stats() - the count has no source");
  assert.match(view, /out\["skills"\] = SK\.cards\(\)/);
  const stats = SKILLS_BACKEND.slice(SKILLS_BACKEND.indexOf("def stats()"),
                                     SKILLS_BACKEND.indexOf("def stats()") + 900);
  for (const field of ['"installed"', '"quarantined"']) {
    assert.ok(stats.includes(field), `jarvis_skills.stats() no longer reports ${field}`);
  }
});

console.log(`\n${fails.length ? fails.length + " failed" : "all checks passed"}: ` +
  `${fails.length ? fails.join(", ") : "the Skills card reports only what the PC measured"}`);
process.exit(fails.length ? 1 : 0);
