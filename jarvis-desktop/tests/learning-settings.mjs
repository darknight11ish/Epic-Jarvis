/**
 * learning-settings.mjs - the Settings -> Learning card (2026-10-28, the
 * settings audit's G1; `learning-settings.js`, `settings.html#learning`,
 * `surfaces.toml`'s `learning-settings` set).
 *
 * Runs on plain Node with no browser:
 *
 *     node tests/learning-settings.mjs
 *
 * WHY IT EXISTS. The two learning switches had a real route and a spoken name
 * but no Settings row on either app; the audit's G1 is that gap. The card must
 * be wired through the Brain's OWN three commands (so a change here is the same
 * write path, not a second idea of learning), and the grant must stay narrow:
 * the switch state and the two switch writes, never a saved fact. This file
 * holds both halves to the source, and holds the card's two rows to their own
 * card (the settings audit's G3 lesson: a row in the wrong card can be hidden
 * with it).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const HTML = read("src/settings.html");
const JS = read("src/learning-settings.js");
const TOML = read("src-tauri/permissions/surfaces.toml");
const CAP = read("src-tauri/capabilities/settings.json");

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

/** The ids of the `<section>`/`<details>` containers open at `at`, nearest first. */
function containerIds(html, at) {
  const re = /<(\/?)(section|details)\b([^>]*)>/g;
  const stack = [];
  let m;
  while ((m = re.exec(html)) && m.index < at) {
    if (m[1] === "/") {
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i].tag === m[2]) {
          stack.splice(i, 1);
          break;
        }
      }
    } else {
      const id = /\bid="([^"]+)"/.exec(m[3]);
      stack.push({ tag: m[2], id: id ? id[1] : "" });
    }
  }
  return stack.map((s) => s.id).filter(Boolean);
}

await check("the Learning card exists, and both rows are drawn inside it", () => {
  assert.match(HTML, /<section class="card" id="learning">/,
    "settings.html has no #learning card");
  for (const id of ["learning-background", "learning-sensitive"]) {
    const at = HTML.indexOf(`id="${id}"`);
    assert.ok(at > 0, `#${id} is not on the page`);
    assert.ok(containerIds(HTML, at).includes("learning"),
      `#${id} is not inside #learning`);
  }
});

await check("the card is in the jump list as a real section", () => {
  assert.match(HTML, /<a href="#learning">Learning<\/a>/, "no jump link");
  assert.match(HTML, /<script type="module" src="learning-settings\.js"><\/script>/,
    "the module is not loaded");
});

await check("the module calls the Brain's own three commands and nothing else", () => {
  for (const cmd of ["brain_memory_learning_status", "brain_memory_learning",
    "brain_memory_learning_sensitive"]) {
    assert.ok(JS.includes(cmd), `${cmd} is not called`);
  }
  // The one grant is those three; the fact list, the saved ids, Forget and
  // export stay the Brain's. A settings page that could read a fact would make
  // this card a second memory surface, which it must not be.
  for (const forbidden of ["brain_memory_auto_list", "brain_memory_saved_unseen",
    "brain_memory_forget", "brain_memory_export", "decide_approval", "answer_approval"]) {
    assert.ok(!JS.includes(forbidden), `the Settings module calls ${forbidden}`);
  }
});

await check("the grant is exactly the three commands, and the settings window holds it", () => {
  const sets = TOML.split("[[set]]").slice(1);
  const learning = sets.find((s) => /identifier = "learning-settings"/.test(s));
  assert.ok(learning, "no learning-settings set in surfaces.toml");
  const granted = [...learning.matchAll(/"allow-([a-z-]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(granted, ["brain-memory-learning", "brain-memory-learning-sensitive",
    "brain-memory-learning-status"], `the set grants ${granted}`);
  assert.match(CAP, /"learning-settings"/, "settings.json does not hold the set");
  // The Brain keeps its own copy of the same commands: this is one path used
  // twice, not a second one.
  assert.match(TOML, /identifier = "brain-memory"[\s\S]*?allow-brain-memory-learning-status/);
});

await check("the wires say where each switch's value comes from", () => {
  // The status answer's own field names, as the Rust command sends them
  // (brain/auto_learn.rs, read by auto-learn.js): a switch drawn from a field
  // the PC does not send would read as off for ever.
  assert.match(JS, /raw\.enabled === true/, "background learning is not read from `enabled`");
  assert.match(JS, /raw\.auto_sensitive === true/, "the sensitive switch is not read from `auto_sensitive`");
  assert.match(JS, /raw\.sensitive_waiting === true/, "the waiting card is not read from `sensitive_waiting`");
  // ON raises a card and the answer says `waiting`, never "on".
  assert.match(JS, /out && out\.waiting/, "a waiting card is not handled");
});

await check("the card's note sends the fact list to the Brain, not here", () => {
  assert.match(HTML, /Everything it saved,[\s\S]*?are in the Brain/,
    "the card does not say where the saved facts are");
  assert.ok(!/brain_memory_auto_list|saved_unseen/.test(JS),
    "the card reaches for the fact list");
});

console.log(failed
  ? `\n${failed} failed: the Learning card is not wired as the audit's G1 requires`
  : `\nthe Learning card is the Brain's three commands, in its own card`);
process.exit(failed ? 1 : 0);
