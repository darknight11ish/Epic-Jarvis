/**
 * The Brain's "File history" drawer (Pillar 18's file guardian; JARVIS-API
 * section 140; LM-2C; docs/FILE-GUARDIAN-DESIGN.md).
 *
 * TWO HALVES, BOTH NODE
 *
 * 1. THE PURE RULES, driven against the REAL route shapes (`guardian.js`): the
 *    list is newest first and carries only the contract's fields (a future
 *    backend's extra field - say a file's contents - is dropped, not drawn);
 *    a hidden answer means the WHOLE drawer is one sentence with no rows; the
 *    diff is the module's own bounded text and says when it was cut; a restore
 *    sends exactly one {path, shaBefore}, and a refused restore asks for no
 *    second read because nothing changed.
 * 2. THE WIRING, read from the real files (the pictures.mjs shape): where the
 *    pane lives, that the page approves nothing and names no URL, that the
 *    hiding decision is RUST's and uses BOTH flags, that the list rides on the
 *    existing brain_read allowlist, that the two commands are granted to the
 *    Brain window only, and that parity/docs/ACL agree.
 *
 * No browser: the hiding decision is Rust's before any page sees an answer, so
 * the files that make the decision are what this checks.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  MAX_DIFF_VIEW_CHARS,
  WORDS,
  diffModel,
  hiddenModel,
  restoreModel,
  restoreRequest,
  sizeWords,
  snapshotModel,
} from "../src/guardian.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const read = (rel) => readFileSync(join(ROOT, rel), "utf8");

const readJson = (rel) => JSON.parse(read(rel));
const brainJson = readJson("jarvis-desktop/src-tauri/capabilities/brain.json");
const surfaces = read("jarvis-desktop/src-tauri/permissions/surfaces.toml");
const buildRs = read("jarvis-desktop/src-tauri/build.rs");
const libRs = read("jarvis-desktop/src-tauri/src/lib.rs");
const guardianRs = read("jarvis-desktop/src-tauri/src/brain/guardian.rs");
const brainRs = read("jarvis-desktop/src-tauri/src/brain.rs");
const routesRs = read("jarvis-desktop/src-tauri/src/brain/routes.rs");
const panel = read("jarvis-desktop/src/guardian-panel.js");
const pureJs = read("jarvis-desktop/src/guardian.js");
const projectsPanel = read("jarvis-desktop/src/projects-panel.js");
const brainHtml = read("jarvis-desktop/src/brain.html");
const parity = read("tools/check_parity.py");
const apiDoc = read("docs/JARVIS-API.md");
const arch = read("docs/ARCHITECTURE.md");
const design = read("docs/FILE-GUARDIAN-DESIGN.md");
const packageJson = read("jarvis-desktop/package.json");

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

// The REAL answer shape of GET /api/guardian/snapshots (JARVIS-API 140.1).
const ANSWER = {
  ok: true, refused: false, why: "", count: 2, total: 2, limit: 50, more: false,
  snapshots: [
    { path: "C:\\Notes\\first.md", label: "first.md", before_sha256: "AAAA",
      size: 2048, timestamp: 100, when: "2026-10-18 09:00", reason: "first edit",
      receipt_id: "rc1", contents: "SECRET-FILE-CONTENT" },
    { path: "C:\\Notes\\second.md", label: "second.md", before_sha256: "BBBB",
      size: 100, timestamp: 200, when: "2026-10-18 10:00", reason: "second edit",
      receipt_id: "rc2" },
  ],
  usage: { blob_bytes: 1, blobs: 2, quota_bytes: 10, pinned: 0, over_quota: false },
  words: "Showing the 2 most recent of 2 saved version(s).",
};

/* ── 1. the pure rules ────────────────────────────────────────────────── */

check("the list is NEWEST FIRST, whatever order the answer arrives in", () => {
  const model = snapshotModel(ANSWER);
  assert.deepEqual(model.rows.map((r) => r.sha256), ["bbbb", "aaaa"]);
  assert.deepEqual(model.rows.map((r) => r.when),
                   ["2026-10-18 10:00", "2026-10-18 09:00"]);
});

check("a row carries ONLY the contract's fields - never a file's contents", () => {
  const model = snapshotModel(ANSWER);
  assert.ok(!JSON.stringify(model).includes("SECRET-FILE-CONTENT"));
  assert.deepEqual(Object.keys(model.rows[0]).sort(), [
    "label", "path", "reason", "receiptId", "sha256", "size", "timestamp", "when",
  ]);
  assert.equal(model.rows[0].label, "second.md");
  assert.equal(model.rows[0].reason, "second edit");
});

check("a hidden answer hides the WHOLE drawer: one sentence, no rows, no path", () => {
  const model = snapshotModel({ ok: true, available: true, hidden: true,
                                keep_on_screen: true, title: "File history",
                                hidden_words: "Turn off Hide memory lists." });
  assert.equal(model.hidden, true);
  assert.deepEqual(model.rows, []);
  assert.equal(model.hiddenWords, "Turn off Hide memory lists.");
  assert.ok(!JSON.stringify(model).includes("C:\\"));
});

check("an older backend is missing, not an error; a refusal is the PC's words", () => {
  assert.equal(snapshotModel({ available: false, error: "older PC" }).missing, true);
  assert.equal(snapshotModel(null).missing, true);
  const refused = snapshotModel({ ok: false, refused: true, why: "not_this_pc",
                                  snapshots: [], words: "This PC only." });
  assert.equal(refused.hidden, false);
  assert.deepEqual(refused.rows, []);
  assert.equal(refused.words, "This PC only.");
});

check("the module's own diff is shown bounded and says when it was cut", () => {
  const answer = { ok: true, path: "C:\\a.md", diff: "-old\n+new\n",
                   truncated: false, binary: false, same: false,
                   words: "The file changed since that version was saved." };
  const model = diffModel(answer);
  assert.equal(model.text, "-old\n+new\n");
  assert.equal(model.truncated, false);
  const cut = diffModel({ ...answer, truncated: true, diff: "x".repeat(MAX_DIFF_VIEW_CHARS + 50) });
  assert.equal(cut.text.length, MAX_DIFF_VIEW_CHARS);
  assert.equal(cut.truncated, true);
});

check("a diff that changed nothing or cannot be shown is the PC's sentence", () => {
  const same = diffModel({ ok: true, same: true, diff: "",
                           words: "The file is exactly that saved version." });
  assert.equal(same.text, "");
  assert.ok(same.words.includes("exactly that saved version"));
  const binary = diffModel({ ok: true, binary: true, diff: "", words: "" });
  assert.ok(binary.words.length > 0);
  assert.equal(diffModel({ hidden: true, hidden_words: "Hidden." }).hidden, true);
});

check("a restore sends exactly ONE request: the row's path and saved version", () => {
  const [row] = snapshotModel(ANSWER).rows;
  assert.deepEqual(restoreRequest(row), { path: row.path, shaBefore: row.sha256 });
  assert.equal(restoreRequest(null), null);
  assert.equal(restoreRequest({ path: "", sha256: "AA" }), null);
});

check("a refused restore changes nothing, so nothing is re-read", () => {
  const denied = restoreModel({ ok: false, refused: true, gated: true,
                                outcome: "denied", words: "The card was turned down." });
  assert.equal(denied.refresh, false);
  assert.ok(denied.words.includes("turned down"));
  const accepted = restoreModel({ ok: true, changed: true, words: "Put back the version." });
  assert.equal(accepted.refresh, true);
  assert.equal(restoreModel({ ok: true, changed: false, same: true }).refresh, false);
  assert.equal(restoreModel({ hidden: true, hidden_words: "Hidden." }).hidden, true);
});

check("sizes are the same words the PC uses", () => {
  assert.equal(sizeWords(2048), "2.0 KB");
  assert.equal(sizeWords(512), "512 bytes");
  assert.equal(sizeWords(-1), "");
});

/* ── 2. the wiring in the real files ──────────────────────────────────── */

check("the drawer sits in the Projects view beside Progress and Pictures", () => {
  assert.match(brainHtml, /id="guardian-root"/);
  assert.match(projectsPanel,
    /import \{ refreshGuardian, setGuardianVisible \} from "\.\/guardian-panel\.js";/);
  assert.match(projectsPanel, /setGuardianVisible\(!state\.open\);/);
  assert.match(projectsPanel, /if \(!state\.open\) refreshGuardian\(\);/);
});

check("the page asks for NOTHING until shown, and approves nothing", () => {
  assert.match(pureJs, /export function snapshotModel/);
  assert.match(panel, /if \(!state\.visible\) return;/);
  assert.match(panel, /window\.confirm\(WORDS\.restore_ask\)/);
  assert.match(panel, /invoke\("brain_read", \{ sections: \["guardian_history"\] \}\)/);
  assert.equal((panel.match(/invoke\("guardian_restore"/g) || []).length, 1);
  assert.equal((panel.match(/invoke\("guardian_diff"/g) || []).length, 1);
  // The page never builds a URL and never names a route.
  assert.ok(!panel.includes("/api/") && !pureJs.includes("/api/"),
            "the page must never name a route");
  assert.match(panel, /TAURI\.event\.listen\("security-changed"/);
});

check("while hidden the page draws one sentence and no list", () => {
  const at = panel.indexOf("if (model.hidden)");
  assert.notEqual(at, -1);
  const branch = panel.slice(at, at + 220);
  assert.match(branch, /hiddenBlock/);
  assert.match(branch, /return;/);
});

check("the hiding decision is RUST's, and it uses BOTH flags", () => {
  assert.match(guardianRs, /crate::lock::app_locked\(app\)/);
  assert.match(guardianRs, /crate::lock::private_hidden\(app\)/);
  assert.match(guardianRs, /app_lock \|\| hide_lists/);
  assert.match(guardianRs, /"hidden": true/);
  // And while hidden the Brain does not even ask for the list section.
  assert.match(brainRs, /let hide_guardian = guardian::words_hidden\(&app\);/);
  assert.match(brainRs, /if hide_guardian && section == "guardian_history"/);
});

check("the list rides on the existing read allowlist; the two commands are granted", () => {
  assert.match(routesRs, /use super::guardian::SNAPSHOTS_PATH;/);
  assert.match(routesRs, /\("guardian_history", SNAPSHOTS_PATH\)/);
  assert.match(libRs, /brain::guardian::guardian_diff,/);
  assert.match(libRs, /brain::guardian::guardian_restore,/);
  assert.match(buildRs, /"guardian_diff",/);
  assert.match(buildRs, /"guardian_restore",/);
  assert.ok(brainJson.permissions.includes("brain-guardian"));
  const set = surfaces.slice(surfaces.indexOf('identifier = "brain-guardian"'));
  assert.ok(set.slice(0, 1200).includes('"allow-guardian-diff"'));
  assert.ok(set.slice(0, 1200).includes('"allow-guardian-restore"'));
});

check("the routing is literal in Rust, the path is escaped, the card waits", () => {
  assert.match(guardianRs, /pub\(crate\) const SNAPSHOTS_PATH: &str = "\/api\/guardian\/snapshots";/);
  assert.match(guardianRs, /pub\(crate\) const DIFF_PATH: &str = "\/api\/guardian\/diff";/);
  assert.match(guardianRs, /pub\(crate\) const RESTORE_PATH: &str = "\/api\/guardian\/restore";/);
  assert.match(guardianRs, /pub\(crate\) fn encode\(/);
  assert.match(guardianRs, /15 \* 60/);
});

check("parity calls all three routes deliberate, and the docs say the same", () => {
  for (const route of ["/api/guardian/snapshots", "/api/guardian/diff",
                       "/api/guardian/restore"]) {
    const at = parity.indexOf(`"${route}": ("deliberate"`);
    assert.notEqual(at, -1, `${route} is not deliberate in parity`);
  }
  assert.match(apiDoc, /### 140\.5 The desktop drawer/);
  assert.match(apiDoc, /Brain -> Projects -> File history/);
  assert.match(arch, /File history/);
  assert.ok(design.includes("File history drawer"));
});

check("guardian-drawer.mjs runs with the other node tests", () => {
  assert.ok(packageJson.includes("node tests/guardian-drawer.mjs"));
});

check("the hidden summary used when a flag changes names no file and no count", () => {
  const model = hiddenModel();
  assert.equal(model.hidden, true);
  assert.deepEqual(model.rows, []);
  assert.ok(model.hiddenWords.length > 0);
  assert.ok(!JSON.stringify(model).includes("C:\\\\"));
});

check("the restore command takes the same stale-link gate as the other writes", () => {
  const at = guardianRs.indexOf("pub async fn guardian_restore");
  assert.notEqual(at, -1);
  const body = guardianRs.slice(at);
  const gate = body.indexOf("require_link_live(&app)?");
  const send = body.indexOf("jarvis_client(Some(RESTORE_WAIT))");
  assert.notEqual(gate, -1, "the command must call require_link_live");
  assert.ok(gate < send, "the stale gate must run before anything is sent");
});

check("a restore answer is re-hidden after it returns, like the diff", () => {
  const at = guardianRs.indexOf("pub async fn guardian_restore");
  assert.notEqual(at, -1);
  const body = guardianRs.slice(at, at + 2000);
  assert.match(body, /shown\(&app, answer\)/);
});

check("a flag change clears the rows before the next read", () => {
  const at = panel.indexOf("security-changed");
  assert.notEqual(at, -1);
  const block = panel.slice(at, at + 900);
  const clear = block.indexOf("state.model = hiddenModel()");
  const paint = block.indexOf("paint();");
  const readAgain = block.indexOf("refreshGuardian();");
  assert.notEqual(clear, -1, "the rows must be replaced at once");
  assert.notEqual(paint, -1, "the drawer must be repainted at once");
  assert.notEqual(readAgain, -1);
  assert.ok(clear < readAgain && paint < readAgain,
            "the old rows must be gone before the next read is asked for");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall guardian drawer checks passed");
