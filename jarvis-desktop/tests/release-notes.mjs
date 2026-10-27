/**
 * "What changed in the update?" - the release-notes half.
 *
 *     node tests/release-notes.mjs
 *
 * The desktop updater's manifest carries one `notes` string. `latest.json`'s
 * was one sentence naming the commit until 2026-10-26; Settings showed it and
 * nothing could answer "what changed?". `scripts/release-notes.mjs` now builds
 * it from the repository's own record - `changelog.d/*.md` (one bullet per
 * merged pull request) and the rolled "Not in a numbered version yet" bullets -
 * and `backend/jarvis_quick.py` reads it back to answer in chat.
 *
 * This suite pins the property that matters: every bullet is a RECORDED
 * change, quoted; nothing is invented; an empty record says so; a long list is
 * trimmed and says how many are left. It also drives the real repository tree,
 * so a change to the fragment or changelog format shows up here.
 */
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  ROOT,
  buildNotes,
  bulletOf,
  plainWords,
  readEntries,
  rolledBullets,
  summaryOf,
} from "../scripts/release-notes.mjs";

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

const HEAD = "Jarvis Desktop 0.2.320, from commit 0c15f81 on main.";

/* ---- the words -------------------------------------------------------- */

check("markdown punctuation never reaches the owner's screen", () => {
  assert.equal(
    plainWords("- **The HUD keeps its place (2026-10-26).** See [the notes](https://x)."),
    "The HUD keeps its place (2026-10-26). See the notes."
  );
  assert.equal(plainWords("  -  already a bullet  "), "already a bullet");
});

check("a fragment's whole content becomes one bullet", () => {
  assert.equal(bulletOf("- **Thing.** It changed.\n"), "- Thing. It changed.");
  assert.equal(bulletOf("   \n"), "");
});

check("a bullet becomes its own summary sentence, not a paraphrase", () => {
  assert.equal(
    summaryOf("- **The screen keeps its place (2026-10-26).** Why, and one limit."),
    "- The screen keeps its place (2026-10-26)."
  );
  assert.equal(summaryOf("No full stop in this one"), "- No full stop in this one");
  assert.equal(summaryOf(""), "");
  const long = summaryOf(`- **${"word ".repeat(80)}**`);
  assert.ok(long.length <= 202, String(long.length));
  assert.ok(long.endsWith("..."), long.slice(-8));
});

/* ---- the sources ------------------------------------------------------ */

check("only the 'Not in a numbered version yet' section is read", () => {
  const md = [
    "# Changelog",
    "## Not in a numbered version yet",
    "- **Newer thing.** Said.",
    "- **Older thing.** Said.",
    "## 0.2.0 - 26 September 2026",
    "- **Already released.** Not this.",
  ].join("\n");
  const got = rolledBullets(md);
  assert.deepEqual(got, ["- Newer thing. Said.", "- Older thing. Said."]);
});

check("an empty changelog is an empty list, not a crash", () => {
  assert.deepEqual(rolledBullets(""), []);
  assert.deepEqual(rolledBullets(undefined), []);
});

check("fragments come newest first, and the rolled list is NOT mixed in", () => {
  const root = mkdtempSync(join(tmpdir(), "jarvis-notes-"));
  mkdirSync(join(root, "changelog.d"));
  writeFileSync(join(root, "changelog.d", "2026-10-24-older.md"),
    "- **Older fragment.** Said.\n");
  writeFileSync(join(root, "changelog.d", "2026-10-26-newer.md"),
    "- **Newer fragment.** Said.\n");
  writeFileSync(join(root, "changelog.d", "README.md"), "Not a fragment.\n");
  writeFileSync(join(root, "CHANGELOG.md"), [
    "## Not in a numbered version yet",
    "- **Rolled thing.** Said.",
    "## 0.2.0 - 26 September 2026",
    "- **Already released.** Not this.",
  ].join("\n"));
  assert.deepEqual(readEntries(root), [
    "- Newer fragment.",
    "- Older fragment.",
  ]);
});

check("straight after a roll (no fragments), the rolled bullets are used", () => {
  const root = mkdtempSync(join(tmpdir(), "jarvis-notes-rolled-"));
  mkdirSync(join(root, "changelog.d"));
  writeFileSync(join(root, "CHANGELOG.md"), [
    "## Not in a numbered version yet",
    "- **Rolled thing.** Said.",
    "- **Older rolled.** Said.",
    "## 0.2.0 - 26 September 2026",
    "- **Already released.** Not this.",
  ].join("\n"));
  assert.deepEqual(readEntries(root), [
    "- Rolled thing.",
    "- Older rolled.",
  ]);
});

check("a missing folder is not an error", () => {
  const root = mkdtempSync(join(tmpdir(), "jarvis-notes-empty-"));
  assert.deepEqual(readEntries(root), []);
});

/* ---- the notes -------------------------------------------------------- */

check("a release with changes names the version, the commit and the source", () => {
  const notes = buildNotes({
    version: "0.2.320",
    commit: "0c15f81e5",
    branch: "main",
    entries: ["- One. Said.", "- Two. Said."],
  });
  assert.ok(notes.startsWith(HEAD), notes);
  assert.match(notes, /What changed \(from the changelog, newest first\):/);
  assert.match(notes, /- One\. Said\./);
  assert.match(notes, /- Two\. Said\./);
});

check("an empty record says it cannot list the changes - it does not invent one", () => {
  const notes = buildNotes({
    version: "0.2.320", commit: "0c15f81", branch: "main", entries: [],
  });
  assert.ok(notes.startsWith(HEAD), notes);
  assert.match(notes, /cannot list its changes/);
  assert.ok(!/What changed \(/.test(notes), notes);
});

check("a long list is trimmed, and says how many were left out", () => {
  const entries = Array.from({ length: 30 }, (_, i) => `- Change ${i}.`);
  const notes = buildNotes({
    version: "0.2.320", commit: "0c15f81", branch: "main", entries,
    maxEntries: 20,
  });
  assert.equal((notes.match(/^- Change /gm) || []).length, 20);
  assert.match(notes, /and 10 more changes in the changelog/);
});

check("a very long entry list is also capped in characters", () => {
  const entries = Array.from({ length: 5 }, () => `- ${"x".repeat(900)}`);
  const notes = buildNotes({
    version: "0.2.320", commit: "0c15f81", branch: "main", entries,
  });
  assert.ok(notes.length < 2100, String(notes.length));
  assert.match(notes, /more changes in the changelog/);
});

check("a bad version or commit is refused, not shipped", () => {
  for (const bad of [{ version: "latest" }, { version: "1.2" }]) {
    assert.throws(() => buildNotes({ ...bad, commit: "0c15f81", entries: [] }));
  }
  assert.throws(() => buildNotes({ version: "1.2.3", commit: "not-a-sha", entries: [] }));
});

/* ---- the real tree ---------------------------------------------------- */

check("this repository's own changelog produces a usable list today", () => {
  const entries = readEntries(ROOT);
  assert.ok(entries.length > 0, "no changelog entries found");
  assert.ok(entries.every((e) => e.startsWith("- ")), "a bullet lost its dash");
  assert.ok(entries.every((e) => e.length > 3), "an empty bullet");
  assert.ok(!entries.some((e) => e.includes("**") || e.includes("`")),
    "markdown punctuation reached the notes");
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
