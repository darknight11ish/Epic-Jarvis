/**
 * The assistant's display name is Atlas, and the role KEY is still "jarvis".
 *
 *     node tests/assistant-name-atlas.mjs
 *
 * The owner's ruling (2026-11-18): the product is Atlas wherever a person
 * reads it. The HUD transcript labelled the assistant's turn "jarvis"
 * (`src/jarvis_hud.html`, `addMessage`'s `.who` line) and every sibling
 * surface that printed the same label said it too. What must NOT move is the
 * KEY: the PC's own turns, the `.msg.jarvis` styling, every
 * `addMessage("jarvis", ...)` call site and the phone's wire roles still say
 * "jarvis".
 *
 * WHY A LIFTED FUNCTION RATHER THAN THE DOM. The page's own label map and its
 * `roleName()` are lifted out of `src/jarvis_hud.html` and EXECUTED here, so
 * the check is "what would the transcript draw", not "does the text look
 * right". The wiring around it (the call site, the class, the callers' role
 * key) is pinned as source text - the way this repository holds a page it
 * does not fork (`tests/wake-copy.mjs`, `tests/update-chat.mjs`).
 *
 * Browser-free on purpose: it imports no Playwright, so it runs at a desk and
 * in CI's frontend job alike. The real page is still driven by the Playwright
 * cases in `tests/hud.mjs`; those assert the same label in the real DOM.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..");
const SRC = join(HERE, "..", "src");
const read = (file) => readFileSync(file, "utf8");

const PAGE = read(join(SRC, "jarvis_hud.html"));
const HISTORY = read(join(SRC, "hud-history.js"));
const HISTORY_VIEW = read(join(SRC, "history-view.js"));
const PHONE_HOME = read(join(REPO, "jarvis-client", "app", "src", "main", "java",
  "com", "jarvis", "client", "ui", "screens", "HomeScreen.kt"));
const PHONE_HISTORY = read(join(REPO, "jarvis-client", "app", "src", "main", "java",
  "com", "jarvis", "client", "ui", "screens", "HistoryScreen.kt"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** One `function name(...) { ... }` body, lifted as source text. */
const lift = (src, name) => {
  const m = src.match(new RegExp(`function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n  \\}`));
  assert.ok(m, `the page's ${name}() is gone`);
  return m[0];
};

/** The page's own label map + roleName(), lifted and RUN. */
function transcriptLabel() {
  const map = PAGE.match(/const ROLE_NAMES = Object\.freeze\(\{[\s\S]*?\n\}\);/);
  assert.ok(map, "the page's ROLE_NAMES map is gone");
  const fn = PAGE.match(/function roleName\(role\)\{[\s\S]*?\n\}/);
  assert.ok(fn, "the page's roleName(role) is gone");
  return new Function(`${map[0]}\n${fn[0]}\nreturn roleName;`)();
}

/** The History module's Copy/Export role word, lifted and RUN. `norm` is the
 *  module's own helper, stubbed to the same job its callers rely on. */
function historyRoleWord(role) {
  const body = lift(HISTORY, "roleWord");
  const fn = new Function(
    "norm", `${body}\nreturn roleWord;`
  );
  return fn((v) => String(v == null ? "" : v).toLowerCase().trim())(role);
}

check("the transcript draws Atlas for the assistant role and still keys on jarvis", () => {
  const name = transcriptLabel();
  assert.equal(name("jarvis"), "Atlas",
    "the assistant's transcript line is not labelled Atlas");
  assert.equal(name("user"), "you", "the owner's own words stopped being labelled 'you'");
  assert.equal(name("system"), "system", "a system line stopped being labelled 'system'");
  assert.match(name("sample"), /not from Atlas/,
    "the offline sample is not labelled against Atlas");

  // The KEY did not move: the page still asks for the assistant by "jarvis",
  // and the message class is still keyed by the role itself (so
  // `.msg.jarvis` styling, the PC's own turns and every older caller work).
  assert.match(PAGE, /const who = roleName\(role\);/,
    "addMessage does not draw its speaker name through the label function");
  assert.match(PAGE, /addMessage\("jarvis"/,
    'the page no longer keys the assistant\'s turns on "jarvis"');
  assert.match(PAGE, /el\.className = "msg " \+ role;/,
    "the message class stopped being keyed by the role");
  assert.match(PAGE, /jarvis: "Atlas"/,
    'the label map\'s KEY stopped being "jarvis"');
});

check("no display string that prints the assistant's name prints the old one", () => {
  const name = transcriptLabel();

  // The offline sample's whole body, lifted from the page, so its words are
  // read from the code that really writes them.
  const sampleBody = PAGE.match(/function sampleReply\(\)\{[\s\S]*?\n\}/);
  assert.ok(sampleBody, "the page's sampleReply() is gone");
  assert.match(sampleBody[0], /Atlas is not connected/,
    "the offline sample no longer names Atlas as the one that is not connected");

  // The page's two "could not answer" lines, read as the code writes them.
  const errLine = PAGE.match(
    /addMessage\("system", \(err && err\.fromServer \? "([^"]+)" : "([^"]+)"\)/);
  assert.ok(errLine, 'the page\'s "could not answer" line is gone');

  const shown = {
    "the transcript's speaker label": name("jarvis"),
    "the offline sample's label": name("sample"),
    "the offline sample's words": sampleBody[0],
    "the PC's own error prefix": errLine[1],
    "the unreachable error prefix": errLine[2],
    "the History Copy/Export role word": historyRoleWord("assistant"),
  };
  for (const [where, text] of Object.entries(shown)) {
    assert.doesNotMatch(text, /\bjarvis(?:'s)?\b/i,
      `${where} still prints the old name: ${text}`);
  }

  // The History transcript's own labels (Brain's History tab): the turn head,
  // the search-snippet prefix and the fork button's accessible label.
  const head = HISTORY_VIEW.match(/: t\.role === "user" \? "You" : "([^"]*)"\)\);/);
  assert.ok(head, "the History turn-head label is gone");
  assert.equal(head[1], "Atlas", "the History turn-head still prints something else");
  const snippet = HISTORY_VIEW.match(/snippet\.role === "assistant" \? "([^"]*): "/);
  assert.ok(snippet, "the History search-snippet label is gone");
  assert.equal(snippet[1], "Atlas", "the History search snippet still prints something else");
  const fork = HISTORY_VIEW.match(/assistant: "([^"]*)",/);
  assert.ok(fork, "the fork button's accessible label is gone");
  assert.match(fork[1], /^Fork from here, after Atlas's answer$/,
    "the fork button still names the old assistant");

  // The phone's chat bubbles say the same thing (the owner reads both apps).
  assert.doesNotMatch(PHONE_HOME, /Kicker\("Jarvis"/,
    "the phone's answer bubble still prints the old name");
  assert.match(PHONE_HOME, /Kicker\("Atlas", color = if \(streaming\)/,
    "the phone's newest answer is not labelled Atlas");
  assert.match(PHONE_HOME, /Kicker\("Atlas"\)/,
    "the phone's folded earlier answers are not labelled Atlas");
  assert.doesNotMatch(PHONE_HISTORY, /else -> "Jarvis"/,
    "the phone's History transcript still prints the old name");
  assert.match(PHONE_HISTORY, /else -> "Atlas"/,
    "the phone's History transcript is not labelled Atlas");
});

console.log("");
if (fails.length) {
  console.log(`${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("2 passed, 0 skipped, 0 failed");
