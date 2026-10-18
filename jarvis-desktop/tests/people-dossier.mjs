/**
 * LM-4 - the people-dossier click door, pinned without a window.
 *
 * The dossier is the PC's own records, so the rules that matter are the ones
 * the page cannot bypass: the hidden sentence comes from Rust and the page
 * draws EXACTLY what it is handed; while App lock or the hidden lists are on,
 * Rust asks the PC for nothing; the command is granted to the Brain window
 * only; and the backend refuses another device before the module is imported
 * or the name is read.
 *
 * Read the pure part through the real module; everything else is pinned
 * against the real files, the way tests/selection-chip.mjs pins the bar's chip.
 * No browser: the privacy decision is Rust's before any page sees an answer.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  HIDDEN_LINE,
  MISSING_LINE,
  UNREADABLE_LINE,
  dossierBody,
  dossierTitle,
  isWithheld,
} from "../src/people-dossier.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
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

const real = {
  ok: true,
  withheld: false,
  name: "Priya",
  private: true,
  active_facts: [{ id: 1, text: "Sister, lives in Lisbon" }],
  retired_facts: [],
  recent_chat: [],
  recent_email: [{ from: "priya@example.com", subject: "Lunch", preview: "Thursday?" }],
  commitments: [{ text: "Send the photos" }],
  next_event: { when: "Friday 12:00", summary: "Lunch with Priya" },
  states: { facts: "ok" },
  why: {},
  read: [],
  counts: { active_facts: 1 },
  text: "Priya - person dossier.\n- Sister, lives in Lisbon",
};

const withheld = {
  ok: false,
  withheld: true,
  why: HIDDEN_LINE,
  text: HIDDEN_LINE,
  name: "",
  private: true,
  made: 0.0,
  states: {},
  read: [],
};

check("the PC's own dossier text is drawn as it is", () => {
  assert.equal(dossierBody(real), real.text);
  assert.match(dossierTitle("Priya", real), /Priya/);
  assert.equal(isWithheld(real), false);
});

check("a withheld answer draws ONE sentence - never the name, facts or counts", () => {
  // Even if a compromised answer carried a name and facts alongside the
  // withheld flag, only the PC's sentence is drawn.
  const poisoned = {
    ...withheld,
    name: "Priya",
    active_facts: [{ id: 1, text: "Sister, lives in Lisbon" }],
    recent_email: [{ from: "priya@example.com", subject: "Lunch" }],
  };
  assert.equal(isWithheld(poisoned), true);
  const body = dossierBody(poisoned);
  assert.equal(body, HIDDEN_LINE);
  assert.doesNotMatch(body, /Priya|Lisbon|Lunch|priya@example/);
  const title = dossierTitle("Priya", poisoned);
  assert.equal(title, "Person dossier");
  assert.doesNotMatch(title, /Priya/);
});

check("an allowed-but-empty dossier says so plainly", () => {
  const empty = { ok: true, withheld: false, name: "Nobody", text: "" };
  assert.equal(dossierBody(empty), "Jarvis has no saved facts about them.");
});

check("what is not an answer is one plain sentence, never invented words", () => {
  assert.equal(dossierBody(null), UNREADABLE_LINE);
  assert.equal(dossierBody({ ok: false, why: MISSING_LINE }), MISSING_LINE);
  assert.equal(dossierBody({ ok: false }), UNREADABLE_LINE);
});

check("the page asks the one command by its literal name and draws its answer", () => {
  const brain = read("jarvis-desktop/src/brain.js");
  assert.match(brain, /invoke\("people_dossier", \{ name: peopleL\.name \}\)/);
  assert.match(brain, /import \{ dossierBody, dossierTitle \} from "\.\/people-dossier\.js"/);
  assert.match(brain, /dossierBody\(peopleL\.view\)/, "the card must draw the PC's own text");
  // The panel's per-row "Open in Memory" action is NOT a dossier door: it
  // keeps opening the About page for every row (the regression galaxy-panel
  // caught). A PERSON opens the dossier from their node click and from the
  // inspector's own button, and only there.
  assert.match(brain, /onOpen: \(entityId\) => openAboutFromGalaxy\(entityId\),/);
  assert.match(brain, /node\.group === "person"/, "only a person opens a dossier");
  assert.match(brain, /if \(node\.group === "person"\) openPersonDossier\(node\.label\);/,
    "a person's node click is one of the two dossier doors");
  assert.match(brain, /nodeButtons\.push\(button\("Person dossier", \(\) => openPersonDossier\(node\.label\)/,
    "the inspector's own button is the other door");
  assert.match(brain, /listen\("private-hidden", \(\) => closePersonDossier\(\)\)/);
  assert.match(brain, /listen\("security-changed", \(\) => closePersonDossier\(\)\)/);
  const html = read("jarvis-desktop/src/brain.html");
  assert.match(html, /id="person-dossier-card" hidden/);
  assert.match(html, /id="person-dossier"/);
});

check("Rust hides it on BOTH switches, before asking the PC, and re-checks after", () => {
  const rs = read("jarvis-desktop/src-tauri/src/brain/people.rs");
  assert.match(rs, /pub\(crate\) fn hidden_flags\(app_lock: bool, hide_lists: bool\) -> bool \{\s*app_lock \|\| hide_lists/);
  assert.match(rs, /if words_hidden\(&app\) \{\s*return Ok\(withheld_answer\(HIDDEN_WORDS\)\);/,
               "the command must withhold BEFORE the request");
  assert.match(rs, /if words_hidden\(&app\) \{\s*return Ok\(withheld_answer\(HIDDEN_WORDS\)\);/g,
               "the same check must run after the answer arrives");
  assert.doesNotMatch(rs, /HIDDEN_WORDS\.replace|format!\(HIDDEN_WORDS/, "no name in the sentence");
  assert.match(rs, /pub\(crate\) const HIDDEN_WORDS: &str =/);
  assert.match(rs, /pub async fn people_dossier\(/);
  assert.match(rs, /dossier_path\(&name\)/);
  assert.match(rs, /encode\(name\)/, "the name is percent-encoded, never glued in raw");
});

check("the command is granted to the Brain window only, and registered once", () => {
  const lib = read("jarvis-desktop/src-tauri/src/lib.rs");
  assert.match(lib, /brain::people::people_dossier/);
  const build = read("jarvis-desktop/src-tauri/build.rs");
  assert.match(build, /"people_dossier",/);
  const surfaces = read("jarvis-desktop/src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /identifier = "brain-people"[\s\S]*?"allow-people-dossier"/);
  const caps = read("jarvis-desktop/src-tauri/capabilities/brain.json");
  assert.match(caps, /"brain-people"/);
  const auto = read("jarvis-desktop/src-tauri/permissions/autogenerated/people_dossier.toml");
  assert.match(auto, /identifier = "allow-people-dossier"/);
});

check("the backend refuses another device BEFORE the module or the name", () => {
  const py = read("backend/jarvis_brain_reads.py");
  assert.match(py, /PEOPLE_DOSSIER_PATH = "\/api\/people\/dossier"/);
  assert.match(py, /PEOPLE_DOSSIER_PATH\)/, "the route is in PATHS");
  const branch = py.slice(py.indexOf("if path == PEOPLE_DOSSIER_PATH:"));
  const owner = branch.indexOf("if not _from_this_pc(peer, local):");
  const importAt = branch.indexOf("import jarvis_people_crm");
  const readName = branch.indexOf('get("name")');
  assert.ok(owner !== -1, "the owner check is present");
  assert.ok(importAt !== -1 && owner < importAt, "owner check comes before the import");
  assert.ok(readName !== -1 && owner < readName, "owner check comes before the name is read");
  assert.match(py, /_dossier_refusal\("not_this_pc", PEOPLE_NOT_THIS_PC\)/);
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe dossier always comes from the PC, and the switch is Rust's");
process.exit(fails.length ? 1 : 0);
