/**
 * "Update Jarvis" answered in chat - the HUD WINDOW's half.
 *
 *     node tests/update-chat.mjs
 *
 * The feature (2026-10-26, the owner's ask: "can jarvis talk about an update
 * if theres one availabale and the changes? and start the update process for
 * me?" - "if i ask in chat"):
 *
 *   * the backend ANSWERS the two questions from the public release manifest
 *     (backend/test_update_chat.py proves that half);
 *   * "update Jarvis" raises ONE approval card, PC-only and Windows Hello;
 *   * the owner's Approve is what makes the SHELL run its own updater
 *     (commands.rs `answer_approval` -> update.rs `run_approved_update`);
 *   * each half's step comes back to this page on the feed's `update` channel
 *     and is drawn as a SYSTEM line in the chat.
 *
 * This suite pins the design where a future edit could quietly undo it:
 *
 * 1. `updateLine` draws the shell's own words, and NOTHING when there is no
 *    sentence (an empty payload never becomes an empty bubble).
 * 2. The feed routes `update` to it, and it draws through the page's own
 *    `addMessage` under the "system" role - never as Jarvis's answer.
 * 3. The HUD window gained NO update command. `capabilities/hud.json` has no
 *    update permission and the bootstrap never calls one: a page cannot start
 *    an install, and this feature did not give it one.
 * 4. The bootstrap invents no claims of its own: every word it draws came from
 *    Rust's `detail`.
 *
 * No browser here: the pure function is LIFTED out of
 * `src-tauri/src/hud_bootstrap.js` and driven directly, exactly the way
 * `hud-replace-confirm.mjs` lifts its rule. The wiring is pinned as source
 * text, which is how this repository holds a page it does not fork.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src-tauri", "src");
const BOOTSTRAP = readFileSync(join(SRC, "hud_bootstrap.js"), "utf8");
const CAPABILITY = readFileSync(
  join(HERE, "..", "src-tauri", "capabilities", "hud.json"),
  "utf8"
);

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

/** One `function name(...)...` body, lifted as source text. */
const lift = (name) => {
  const m = BOOTSTRAP.match(
    new RegExp(`function ${name}\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n  \\}\\n`)
  );
  assert.ok(m, `hud_bootstrap.js has no function ${name}`);
  return m[0];
};

/* ---- 1. the words ------------------------------------------------------ */

const updateLine = (() => {
  const body = lift("updateLine");
  // eslint-disable-next-line no-new-func
  return new Function(`${body}; return updateLine;`)();
})();

check("a step's own sentence is drawn as it came", () => {
  const said = "Jarvis Desktop 0.2.320 is installed and restarts as 0.2.320.";
  assert.equal(updateLine({ state: "ok", detail: said }), said);
});

check("a running half's words are drawn too", () => {
  const said = "Patching the backend folder at the Balanced pace.";
  assert.equal(updateLine({ state: "running", detail: said }), said);
});

check("surrounding whitespace is trimmed, not kept", () => {
  assert.equal(updateLine({ state: "ok", detail: "  done  " }), "done");
});

check("no sentence, no line - never an empty bubble", () => {
  for (const empty of [null, undefined, {}, { detail: "" }, { detail: "   " },
    { detail: 7 }, "text", { state: "ok" }]) {
    assert.equal(updateLine(empty), "", JSON.stringify(empty));
  }
});

/* ---- 2. the wiring ----------------------------------------------------- */

check("the feed routes the update channel to updateProgress", () => {
  assert.match(BOOTSTRAP, /channel === "update"\)\s*updateProgress\(payload\)/);
});

check("progress is drawn as a SYSTEM line through the page's own addMessage", () => {
  const body = lift("updateProgress");
  assert.match(body, /window\.addMessage\("system", text\)/);
  assert.match(body, /updateLine\(payload\)/);
});

check("the system role is the only one it draws as", () => {
  const body = lift("updateProgress");
  for (const wrong of ['"jarvis"', '"user"', '"sample"', "'jarvis'"]) {
    assert.ok(!body.includes(wrong), `updateProgress draws as ${wrong}`);
  }
});

check("the bootstrap invents no claim of its own", () => {
  const body = lift("updateProgress");
  // Every word comes from Rust's `detail`; the page adds none. A hard-coded
  // "installed" or "updated" here would be the page claiming something the
  // shell did not do.
  for (const claim of ["installed", "updated", "restarting", "success"]) {
    assert.ok(
      !body.toLowerCase().includes(claim),
      `updateProgress hard-codes ${claim}`
    );
  }
});

/* ---- 3. no new command for this window -------------------------------- */

check("the HUD holds no update command in its capability file", () => {
  for (const name of [
    "allow-update-status",
    "allow-check-for-update",
    "allow-install-update",
    "allow-update-both",
    "allow-restart-app",
  ]) {
    assert.ok(
      !CAPABILITY.includes(name),
      `capabilities/hud.json now grants ${name} - a page must not start an install`
    );
  }
});

check("the bootstrap never calls an update command", () => {
  // Only the CALL forms: the file's own comment explains which commands it
  // deliberately does not have, and naming one there is not calling it.
  for (const call of [
    'invoke("install_update"',
    'invoke("update_both"',
    'invoke("check_for_update"',
    'invoke("restart_app"',
    'shellInvoke("install_update"',
    'shellInvoke("update_both"',
    'shellInvoke("check_for_update"',
    'shellInvoke("restart_app"',
  ]) {
    assert.ok(
      !BOOTSTRAP.includes(call),
      `hud_bootstrap.js calls ${call} - the shell starts updates, not the page`
    );
  }
});

/* ---- 4. the approval still goes through the one command --------------- */

check("Approve still goes through decide_approval, not a page POST", () => {
  assert.match(BOOTSTRAP, /shellInvoke\("decide_approval", \{ id: id, approved: approved \}\)/);
  // ...and the page's own POST to /api/approve is still refused by the shim.
  assert.match(BOOTSTRAP, /the HUD window cannot send that|an approval is answered through/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
