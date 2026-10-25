/**
 * "Ask for a picture, and keep it" on the desktop (the owner's decision of
 * 2026-09-27: *"12 GB card: longer conversations with picture understanding
 * first, and making pictures too (swapped in when asked, since both cannot sit
 * on the card at once)"*; JARVIS-API.md section 124;
 * src/pictures-panel.js, src-tauri/src/brain/pictures.rs, backend
 * jarvis_pictures.py, docs/JARVIS-API.md section 124).
 *
 * WHY THERE IS NO BROWSER CHECK IN THIS FILE
 *
 * `src/pictures-panel.js` needs a DOM, a Tauri bridge and a live link before
 * its first line of drawing runs, and the thing this file most has to prove -
 * that NOT ONE PROMPT SURVIVES while the private lists are hidden - is decided
 * in RUST, before the page ever sees the answer. So this checks the two files
 * that make the decision, in the exact words they use, rather than a page that
 * could only show the result. The behaviour of the answer-reading functions is
 * pinned by `brain/pictures.rs`'s own `#[cfg(test)]` unit tests, which
 * `cargo test` runs.
 *
 * WHAT IT PROVES
 *
 *  1. the switch is OFF by default, and the feature needs a program the owner
 *     installs - both in the backend the PC ships;
 *  2. no approval is ever raised from this app for a picture, and the routes
 *     that could be a way out of the PC are not named anywhere in it;
 *  3. the three routes are literal in Rust (never built from a page's string);
 *  4. every write waits for a live link, and the two reads do not;
 *  5. THE HIDING RULE: the gallery is taken out whole in Rust while the private
 *     lists are hidden, and the page's own branch fetches nothing at all;
 *  6. the prompt is only ever the owner's own words: no file, no memory, no
 *     page and no model turn is reachable from either file;
 *  7. a picture's id is a bare file stem, so no page can ask the PC for
 *     another path;
 *  8. the phone's half is the app's own file, and it has no field for the
 *     switch, the program or the folder;
 *  9. a drawing is allowed to take minutes on this PC: the make call gets its
 *     own 1,200 s budget (a real draw was measured at 274 s) and every other
 *     pictures write keeps the 20 s one;
 * 10. THE TWO-STEP CONFIRM: when the everyday chat is holding the 12 GB card
 *     the PC answers 409 `needs: "free_card"` and NOTHING IS DRAWN - the page
 *     asks with a confirm button and never retries on its own, the confirm is
 *     the one place `free_card: true` is sent, the wait says how many minutes,
 *     and success reads the gallery back and shows the PC's sentence once.
 *
 * The first parts are pure node. `node tests/pictures.mjs`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");

const RUST = join(ROOT, "jarvis-desktop", "src-tauri", "src", "brain", "pictures.rs");
const PANEL = join(ROOT, "jarvis-desktop", "src", "pictures-panel.js");
const HTML = join(ROOT, "jarvis-desktop", "src", "brain.html");
const BACKEND = join(ROOT, "backend", "jarvis_pictures.py");
const PHONE = join(
  ROOT, "jarvis-client", "app", "src", "main", "java", "com", "jarvis", "client",
  "net", "Pictures.kt",
);
const PHONE_PLATE = join(
  ROOT, "jarvis-client", "app", "src", "main", "java", "com", "jarvis", "client",
  "ui", "screens", "PicturesPlate.kt",
);
const SHIPPED = join(ROOT, "backend", "_where.py");
const APPLY = join(ROOT, "scripts", "apply-patches.ps1");
const API_DOC = join(ROOT, "docs", "JARVIS-API.md");

const rust = readFileSync(RUST, "utf8");
const panel = readFileSync(PANEL, "utf8");
const html = readFileSync(HTML, "utf8");
const backend = readFileSync(BACKEND, "utf8");
const phone = readFileSync(PHONE, "utf8");
const plate = readFileSync(PHONE_PLATE, "utf8");
const shipped = readFileSync(SHIPPED, "utf8");
const apply = readFileSync(APPLY, "utf8");
const apiDoc = readFileSync(API_DOC, "utf8");

let passed = 0;
const failed = [];

function check(name, ok, detail = "") {
  if (ok) {
    passed += 1;
    console.log(`ok   ${name}`);
  } else {
    failed.push(name);
    console.log(`FAIL ${name}`);
    if (detail) console.log(`        ${detail}`);
  }
}

/**
 * A source file with its comments taken out: `//`, `///`, `//!` and block.
 * What is left is the code that runs, which is what this file asserts about -
 * a promise in a comment is not a promise the program keeps.
 */
function bare(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("//"))
    .join("\n");
}

const rustCode = bare(rust);
const panelCode = bare(panel);

console.log("\n--- 1. the switch is off, and a program has to be installed ---");

check(
  "the backend's own defaults are OFF and nothing chosen",
  /DEFAULTS\s*=\s*\{[\s\S]*?"enabled":\s*False[\s\S]*?"runtime":\s*None/.test(backend),
  "jarvis_pictures.DEFAULTS",
);
check(
  "... and a missing or half-written settings file reads as OFF too",
  /except Exception:\s*\n\s*raw = None/.test(backend),
  "load_settings must never raise",
);
check(
  "... and the one plain sentence names BOTH programs to install",
  backend.includes("ComfyUI (https://github.com/comfyanonymous/ComfyUI)")
    && backend.includes("stable-diffusion.cpp's server (https://github.com/leejet/stable-diffusion.cpp)"),
  "NOT_CONFIGURED",
);
check(
  "... and says where to choose one",
  /Settings, under Pictures/.test(backend),
  "NOT_CONFIGURED",
);
check(
  "the two supported runtimes are exactly comfyui and sd_cpp, each on this PC",
  /RUNTIMES = \{[\s\S]*?"comfyui"[\s\S]*?"sd_cpp"[\s\S]*?\n\}/.test(backend)
    && (backend.match(/http:\/\/127\.0\.0\.1:/g) || []).length >= 2,
  "RUNTIMES",
);

console.log("\n--- 2. no approval, and no way out of the PC ---");

// The forbidden words are built, never typed: a literal in THIS file would be
// found by the very scan below, and the check would fail on itself.
const APPROVE = "/api/" + "approve";
const DENY = "/api/" + "deny";
const OWNER_CHECK = "owner" + "_check";
const FS = "std::" + "fs";
const MEMORY = "jarvis_" + "memory";
const HISTORY = "brain_" + "history";
const RAW_GET = "reqwest::" + "get(";

for (const forbidden of [APPROVE, DENY, "PC_ONLY_ACTIONS", OWNER_CHECK]) {
  check(
    `pictures.rs never names ${forbidden}: a picture needs no card`,
    !rustCode.includes(forbidden),
    "the gate is the PC's, not this app's",
  );
}
for (const forbidden of ["smtplib", "api.telegram", "api.openai", "generativelanguage"]) {
  check(
    `jarvis_pictures.py holds no ${forbidden}`,
    !backend.toLowerCase().includes(forbidden),
  );
}
check(
  "... and the module says so itself, in the words the apps show",
  backend.includes("A picture is never sent anywhere by Jarvis"),
  "WORDS.not_kept",
);
check(
  "... and neither file has a share, upload or send function",
  !/def (send|upload|email|share)_/.test(backend)
    && !/(send|upload|email|share)[A-Za-z]*\(/.test(panelCode),
  "no route, no button",
);
check(
  "... and neither names a sharing or upload route",
  !/api\/(share|upload|picture\/send)/.test(rustCode + panelCode),
);

console.log("\n--- 3. the routes are literal in Rust ---");

for (const route of ["/api/pictures", "/api/pictures/file", "/api/pictures/settings"]) {
  check(`pictures.rs builds the URL for ${route} literally`, rust.includes(route), route);
}
check(
  "... and the panel never builds a route of its own",
  !panelCode.includes("/api/") && panelCode.includes('invoke("brain_pictures"'),
  "every call goes through a command",
);
check(
  "... and the panel calls the three commands the gallery needs",
  ["brain_pictures", "brain_pictures_file", "brain_pictures_make"]
    .every((c) => panelCode.includes(`"${c}"`)),
);
// The switch, the drawing program and the folder are the Settings card's, on
// the PC only - the pane reads their STATE and says where to change them.
const settings = readFileSync(join(ROOT, "jarvis-desktop", "src", "pictures-settings.js"), "utf8");
check(
  "... and the Settings card is the only place they change",
  settings.includes('invoke("brain_pictures_settings"')
    && settings.includes('invoke("choose_pictures_folder"')
    && !panelCode.includes("brain_pictures_settings"),
  "one path per change",
);
check(
  "... and the pane says where that is, rather than offering a second set",
  panel.includes("in Settings, under Pictures"),
);

console.log("\n--- 4. every write waits for a live link ---");

check(
  "pictures.rs gates three commands on a live link, and the drawing one is",
  (rustCode.match(/require_link_live\(&app\)\?;/g) || []).length === 3
    && /if !valid_id\(&id\)/.test(rustCode),
  String((rustCode.match(/require_link_live\(&app\)\?;/g) || []).length)
    + " gate(s); brain_pictures_make, brain_pictures_settings and "
    + "choose_pictures_folder are the three writes",
);
check(
  "... and the two reads are not gated (they change nothing)",
  /pub async fn brain_pictures\(app: AppHandle\)/.test(rust)
    && !/fn brain_pictures\(app: AppHandle\)[\s\S]{0,200}require_link_live/.test(rust),
);
check(
  "... and the panel greys its acting buttons while the link is stale",
  panelCode.includes("syncLive") && panelCode.includes("currentLink"),
);
check(
  "... and the drawings say so while they work",
  panel.includes("Drawing…"),
);

console.log("\n--- 5. the hiding rule: not one prompt survives ---");

check(
  "pictures.rs asks the same two questions every private surface asks",
  rustCode.includes("crate::lock::private_hidden(app)")
    && rustCode.includes("crate::lock::app_locked(app)"),
  "private_hidden || app_locked",
);
check(
  "... and takes the WHOLE gallery out, not just the words",
  /pub\(crate\) fn hide_private\(answer: serde_json::Value\) -> serde_json::Value/.test(rust)
    && rustCode.includes('"hidden": true')
    && rustCode.includes('"keep_on_screen": true'),
  "hide_private",
);
// Built, like the other forbidden literals: a literal in this file would be
// found by a scan of this file and the check would fail on itself.
const FOLDER_KEY = '"' + "folder" + '": ""';

check(
  "... and a hidden answer keeps no folder, no count and no size either - " +
    "there is no such key at all, so a page cannot draw one",
  /"hidden_words": words,/.test(rust) && !rust.includes(FOLDER_KEY),
  "hidden_answer",
);
check(
  "... and the bytes are never fetched while the lists are hidden",
  /if words_hidden\(&app\) \{\s*\n\s*return Ok\(hidden_answer/.test(rust),
  "brain_pictures_file returns before any request",
);
check(
  "... and the page draws the PC's own line, with no picture and no prompt",
  panel.includes("hiddenBlock") && panel.includes("hidden_words")
    && /if \(d\.hidden\) \{[\s\S]{0,80}hiddenBlock/.test(panel),
);
check(
  "... and the panel offers the app's own Show, the same one Progress uses",
  panelCode.includes('invoke("reveal_private_answers")'),
);
check(
  "... and while hidden it builds no gallery and no ask box",
  /if \(d\.hidden\) \{[\s\S]*?return;\s*\}/.test(panelCode),
  "the hidden branch returns before askBlock/gallery",
);
check(
  "the desktop panel is guarded by the same menu id the feature list names",
  html.includes('id="pictures-root"') && html.includes('data-menu-id="brain.projects.pictures"'),
);

console.log("\n--- 6. the prompt is only ever the owner's own words ---");

for (const forbidden of [FS, MEMORY, HISTORY, RAW_GET]) {
  check(`pictures.rs reads no ${forbidden}`, !rustCode.includes(forbidden));
}
check(
  "... and nothing in either file hands a picture or a prompt to a model",
  !/model_turn|run_local_turn|jarvis_agent/.test(rustCode + panelCode),
);
check(
  "... and the backend is not a tool the model can call",
  backend.includes("fails if any model path starts importing"),
  "test_pictures.py's own rule, stated in the module",
);
check(
  "... and the prompt is trimmed and bounded before anything is sent",
  /let text = prompt\.trim\(\);/.test(rust) && rust.includes("MAX_PROMPT: usize = 2000"),
);
check(
  "... and the backend caps it at the same number",
  /MAX_PROMPT = 2000/.test(backend),
);

console.log("\n--- 7. an id is a bare file stem ---");

check(
  "pictures.rs refuses anything that is not one of its own names",
  rustCode.includes("pub(crate) fn valid_id") && rust.includes('id.contains("..")'),
);
check(
  "... and it is checked BEFORE any request is sent",
  /if !valid_id\(&id\) \{\s*\n\s*return Err\(/.test(rust),
);
check(
  "... and the phone checks the same thing in its own file",
  phone.includes("fun filePath(id: String)") && phone.includes('text.contains("..")'),
);

console.log("\n--- 8. the phone's half, and what it does NOT have ---");

check(
  "the phone has its own net file and its own screen",
  phone.includes("object Pictures") && plate.includes("internal fun PicturesSection"),
);
check(
  "... and it calls the two routes it may call and no third",
  phone.includes('const val PATH = "/api/pictures"')
    && phone.includes('const val FILE_PATH = "/api/pictures/file"')
    && !phone.includes("/api/pictures/settings"),
  "the settings route is the PC's alone",
);
check(
  "... and it has no field for the switch, the program or the folder",
  // The phone MAY read the switch and the folder (its gallery says so); what
  // it must never have is a way to CHANGE any of them. The settings route's
  // own action names are the thing that would be one.
  !/"action"|settingsBody|picturesSettings/.test(bare(phone)),
  "nothing to send: the PC refuses those from anywhere but itself",
);
check(
  "... and it hides with the private lists and fetches nothing then",
  plate.includes("if (hidden)") && plate.includes("reply = null"),
);
check(
  "... and it saves to the PHONE's own Pictures collection, not anywhere else",
  plate.includes("MediaStore.Images.Media.EXTERNAL_CONTENT_URI")
    && plate.includes('"Pictures/Jarvis"'),
);
check(
  "... and it never puts a model, a catalogue or a program picker on the phone",
  !/RuntimeClass|comfyui|sd_cpp|Program\(/i.test(bare(plate)),
  "no drawing program on the phone",
);

console.log("\n--- 9. the registry and the docs say the same thing ---");

check(
  "jarvis_pictures.py is in the shipped list",
  shipped.includes('"jarvis_pictures.py"'),
  "backend/_where.py SHIPPED",
);
check(
  "... and apply-patches.ps1 both ships it and applies its patch",
  apply.includes("'jarvis_pictures.py'") && apply.includes("'pictures.patch'"),
);
// The repository's rule, held by test_gate_touches.py and
// test_uncensored_optins.py: plugin-loader.patch is LAST OF ALL, and every core
// patch sits above it. This check asserted the OPPOSITE until 2026-10-11
// ("the patch is LAST, after plugin-loader.patch"), which is exactly how the
// branch went red in CI; the position is now the real one, and the loader's own
// "last of all" is asserted beside it rather than assumed.
//
// It used to assert ADJACENCY as well - that pictures.patch was the loader's
// immediate predecessor - and that is a fact about the list's shape which
// nothing depends on: this patch's block is anchored on progress.patch's own,
// not on the loader's, so any core patch may sit between the two. That is
// exactly what happened on 2026-10-15, when initiative-payload.patch (the
// phone's `checks` count on /api/initiative) was appended in front of the
// loader and pushed pictures.patch up one: the backend suites that pin order
// read POSITION, and test_uncensored_optins.py says in as many words why
// ("Asserting adjacency would be asserting a fact about the list's shape that
// nothing depends on"). This check reads the same way now.
const patchBlock = apply.slice(
  apply.indexOf("$PATCHES = @("),
  apply.indexOf("\n)", apply.indexOf("$PATCHES = @(")),
);
const patchNames = patchBlock
  .split("\n")
  .map((line) => (line.match(/^\s*'([^']+\.patch)'\s*$/) || [])[1])
  .filter(Boolean);
check(
  "... and it sits BEFORE plugin-loader.patch, which stays last of all",
  patchNames.length > 1
    && patchNames[patchNames.length - 1] === "plugin-loader.patch"
    && patchNames.indexOf("pictures.patch") >= 0
    && patchNames.indexOf("pictures.patch") < patchNames.indexOf("plugin-loader.patch"),
  `the stack ends: ${patchNames.slice(-3).join(", ")}, pictures.patch at `
    + `${patchNames.indexOf("pictures.patch")} of ${patchNames.length}`,
);
// This branch's own section moved 124 -> 126 on 2026-10-11: main's 124 is the
// picture-CARD module and 125 the uncensored opt-ins, so the next free number
// is 126. Slicing from "## 124." now reads MAIN'S section, so every check below
// reads this feature's own heading and stops at the next one.
const sectionAt = apiDoc.indexOf("## 129.");
const nextHeading = apiDoc.indexOf("\n## ", sectionAt + 1);
const section = sectionAt < 0 ? "" : apiDoc.slice(sectionAt, nextHeading < 0 ? undefined : nextHeading);
check(
  "the API document has section 129 with all three routes",
  sectionAt >= 0 && section.includes("/api/pictures")
    && section.includes("/api/pictures/file") && section.includes("/api/pictures/settings"),
);
check(
  "... and says a picture needs no approval card, and why",
  /no approval card/i.test(section),
);
check(
  "... and says nothing leaves the PC",
  section.includes("Nothing leaves the PC"),
);
check(
  "... and says the switch starts off",
  /default OFF|OFF by default|starts `false`|starts off/i.test(section),
);

console.log("\n--- 10. a drawing takes minutes, and the chat moves only when asked ---");

const BRAIN_RUST = join(ROOT, "jarvis-desktop", "src-tauri", "src", "brain.rs");
const brain = readFileSync(BRAIN_RUST, "utf8");
// The module's own code, without its `#[cfg(test)]` block: the Rust tests
// below build their literals in pieces, and a scan that read them would find
// itself instead of the code that runs.
const rustModule = bare(rust).split("#[cfg(test)]")[0];

/** ONE Rust command, from `pub async fn name` to its own closing brace. */
function rustFn(name) {
  const at = rustModule.indexOf(`pub async fn ${name}(`);
  if (at < 0) return "";
  return (rustModule.slice(at).match(/^[\s\S]*?\n\}/) || [""])[0];
}

/** ONE JS function, by brace matching, so a check cannot read a neighbour. */
function jsFn(name) {
  const at = panelCode.indexOf(`function ${name}(`);
  if (at < 0) return "";
  const open = panelCode.indexOf("{", at);
  let depth = 0;
  for (let i = open; i >= 0 && i < panelCode.length; i += 1) {
    if (panelCode[i] === "{") depth += 1;
    else if (panelCode[i] === "}") {
      depth -= 1;
      if (depth === 0) return panelCode.slice(at, i + 1);
    }
  }
  return "";
}

// (i) THE BUG THIS FIXES: 20 s would time out every real drawing. A draw was
// measured at 274 s on this PC, so the make call has a budget of its own.
check(
  "brain.rs gives a drawing its own long budget, in the shape the other one uses",
  /const PICTURE_TIMEOUT: Duration = Duration::from_secs\(1_200\);/.test(brain)
    && /const REPEAT_EDIT_TIMEOUT: Duration = Duration::from_secs\(1_200\);/.test(brain),
  "PICTURE_TIMEOUT next to REPEAT_EDIT_TIMEOUT",
);
const makeRust = rustFn("brain_pictures_make");
check(
  "(i) the make call uses it - 274 s measured, and 20 s would time out mid-draw",
  makeRust.includes("commands::jarvis_client(Some(PICTURE_TIMEOUT))")
    && !makeRust.includes("WRITE_TIMEOUT"),
  makeRust.match(/jarvis_client\([^)]*\)/) ? makeRust.match(/jarvis_client\([^)]*\)/)[0] : "no client",
);
check(
  "... and every other pictures write keeps the 20 s budget",
  (rustModule.match(/Some\(WRITE_TIMEOUT\)/g) || []).length === 1
    && rustFn("brain_pictures_settings").includes("Some(WRITE_TIMEOUT)"),
  "one WRITE_TIMEOUT left: the settings change",
);
check(
  "... and free_card is added to the body only when the page asks for it",
  makeRust.includes("free_card: Option<bool>")
    && /if free_card == Some\(true\) \{\s*\n\s*body\["free_card"\] = serde_json::json!\(true\);/
      .test(rustModule),
  "prompt_body(prompt, free_card)",
);
check(
  "... and a drawn picture is read by its STRING name, not the gallery's array",
  /if \(200\.\.300\)\.contains\(&status\) \{\s*\n\s*return parsed\(body\)[\s\S]{0,320}x\.is_string\(\)/
    .test(rustModule)
    && !/pictures_answer\(status, &text, "name"\)/.test(rustModule),
  "make_answer",
);

// (ii) THE TWO-STEP CONFIRM: nothing is retried silently.
const makeJs = jsFn("makePicture");
const answerJs = jsFn("handleMakeAnswer");
const askJs = jsFn("askToSetAside");
const retryJs = jsFn("setChatAsideAndDraw");
const blockJs = jsFn("pendingBlock");
const cancelJs = jsFn("cancelPending");

check(
  "(ii) the first request carries the prompt alone - no free_card anywhere in it",
  makeJs.includes('invoke("brain_pictures_make", { prompt: text })')
    && !makeJs.includes("freeCard")
    && (makeJs.match(/invoke\("brain_pictures_make"/g) || []).length === 1,
  "makePicture sends once",
);
check(
  "(ii) a 409 free_card becomes a QUESTION, and this function sends nothing",
  answerJs.includes('if (out.needs === "free_card")')
    && answerJs.includes("askToSetAside(out, prompt)")
    && !answerJs.includes("invoke("),
  "handleMakeAnswer",
);
check(
  "... and the question is drawn with a confirm and a cancel, and no request of its own",
  askJs.length > 0
    && !askJs.includes("invoke(")
    && blockJs.includes("button(setAsideLabel(state.pending.seconds), setChatAsideAndDraw")
    && blockJs.includes("button(WORDS.set_aside_no, cancelPending"),
  "pendingBlock",
);
check(
  "... and both answers are real <button>s, so the keyboard reaches them",
  blockJs.includes("button(")
    && panelCode.includes('const b = el("button", "btn small", label);')
    && panelCode.includes('b.type = "button";'),
  "no clickable div",
);
check(
  "(ii) the confirm click is the ONE place free_card: true is sent",
  retryJs.includes("freeCard: true")
    && (panelCode.match(/freeCard/g) || []).length === 1
    && (retryJs.match(/invoke\("brain_pictures_make"/g) || []).length === 1,
  "setChatAsideAndDraw",
);
check(
  "... and the argument key is camelCase, which is how a command takes it",
  !/free_card\s*:/.test(panelCode) && retryJs.includes("freeCard: true"),
  "freeCard, not free_card",
);
check(
  "... and nothing anywhere arms a retry on its own",
  !panelCode.includes("setTimeout") && !panelCode.includes("setInterval"),
);
check(
  "... and Not now sends nothing, and says nothing was drawn",
  cancelJs.includes("state.pending = null")
    && cancelJs.includes("WORDS.set_aside_stopped")
    && !cancelJs.includes("invoke(")
    && panel.includes("Nothing was drawn - your everyday chat stays where it is."),
  "cancelPending",
);

// (iii) THE WAITING STATE, AND WHAT SUCCESS SHOWS.
check(
  "(iii) while it runs the page says so, with the minutes the PC estimated",
  retryJs.includes("say(drawingWords(pending.seconds))")
    && panelCode.includes("Your everyday chat will come back when it is done.")
    && panelCode.includes("estimate.chat_away_seconds")
    && retryJs.includes("state.making = true"),
  "drawingWords",
);
check(
  "... and the confirm's own label carries the estimate, never a guess",
  panelCode.includes("Set the chat aside and draw")
    && /about \$\{minutes\} \$\{minutes === 1 \? "minute" : "minutes"\}/.test(panelCode),
  "setAsideLabel",
);
check(
  "... and Make stays greyed for the whole draw, even if the link changes",
  /if \(state\.making\) \{\s*\n\s*make\.dataset\.busy = "true";/.test(panelCode)
    && panelCode.includes('make.textContent = "Drawing…"'),
  "busy + disabled",
);
check(
  "(iii) success refreshes the gallery and shows the PC's sentence once, not twice",
  retryJs.includes("finally")
    && retryJs.includes("await refreshPictures()")
    && answerJs.includes("out.words")
    && !answerJs.includes('say(said.join(" "))')
    && answerJs.includes("say(said)"),
  "out.words only, after a re-read",
);
check(
  "(iii) the status line is the panel's own #pictures-said, not a new one",
  panelCode.includes('document.getElementById("pictures-said")')
    && panelCode.includes("announce(state.said, \"polite\")"),
  "say()",
);
check(
  "... and a 409 for ANY other need is its own sentence, with no confirm",
  /if \(out\.needs\) \{[\s\S]{0,220}say\(out\.error \|\| ""\)/.test(answerJs)
    && answerJs.indexOf('out.needs === "free_card"') < answerJs.indexOf("if (out.needs) {"),
  "card_none",
);
check(
  "... and the whole question block is drawn only where the ask box is",
  /if \(d\.enabled && state\.pending\) card\.append\(pendingBlock\(\)\)/.test(panelCode),
  "paint",
);

console.log("\n--- 11. the handshake, RUN with a stubbed bridge ---");

// The pins above read the page. This runs it. The handshake is plain functions
// of (state, answer) - no browser, no webview - so the module is evaluated with
// its one import stubbed, a bridge that records every call, and no DOM at all
// (`say()` still keeps the same state `#pictures-said` would show). A silent
// retry would appear here as a SECOND `brain_pictures_make` call, which is
// exactly what this section is for. The repo has this shape elsewhere
// (`approvals-contract.mjs`, `flashgov.mjs` both lift a page's functions and
// run them); nothing new is installed for it.
const STUB = [
  "const announce = (text) => { globalThis.__picturesAnnounced.push(text); };",
  'const currentLink = () => ({ stale: false });',
  'const linkWords = () => "the link is stale";',
  "const onLink = () => {};",
].join("\n");
const runnable = bare(panel)
  .replace(/^import[^\n]*\n/m, `${STUB}\n`)
  .replace(/^export /gm, "");
check(
  "(setup) the panel is runnable: its one import is stubbed and its exports stripped",
  runnable.includes("const onLink = () => {};") && !/^\s*(import|export) /m.test(runnable),
  "pictures-panel.js's module shape changed; update this section",
);

globalThis.__picturesAnnounced = [];
const calls = [];
let answer = null;
globalThis.__TAURI__ = {
  core: {
    invoke: async (command, args = {}) => {
      calls.push({ command, args });
      if (command === "brain_pictures_make") return answer;
      if (command === "brain_pictures") {
        return { ok: true, available: true, enabled: true, pictures: [] };
      }
      return null;
    },
  },
};
globalThis.document = {
  getElementById: () => null,
  createElement: () => ({
    append() {}, setAttribute() {}, addEventListener() {}, replaceWith() {}, style: {},
  }),
};
const page = new Function(
  `${runnable}\nreturn { makePicture, setChatAsideAndDraw, cancelPending, state };`,
)();
const makeCalls = () => calls.filter((c) => c.command === "brain_pictures_make");

// A 409 free_card is a QUESTION: one call went out, and nothing else does.
calls.length = 0;
answer = {
  ok: false,
  available: true,
  needs: "free_card",
  error: "Your everyday chat is using the 12 GB card.",
  option: "A",
  estimate: { draw_seconds: 274, chat_away_seconds: 300 },
};
await page.makePicture("a red panda");
check(
  "(ii) RUN: a 409 free_card sends exactly ONE make call - no silent retry",
  makeCalls().length === 1,
  `${makeCalls().length} make call(s)`,
);
check(
  "(ii) RUN: ... and the first call carries the prompt alone",
  !("freeCard" in calls[0].args),
  JSON.stringify(calls[0].args),
);
check(
  "(ii) RUN: ... and the PC's sentence becomes a pending question, with its estimate",
  page.state.pending !== null
    && page.state.pending.prompt === "a red panda"
    && page.state.pending.seconds === 300,
  JSON.stringify(page.state.pending),
);
check(
  "(ii) RUN: ... and the sentence is announced rather than swallowed",
  globalThis.__picturesAnnounced.includes("Your everyday chat is using the 12 GB card."),
);

// The confirm click is the only thing that retries, and the wait says so.
// The body below is the REAL body a handshake answers with
// (backend/jarvis_pictures.py: `words` is the "drawn in ..." sentence with the
// swap sentence appended, and `card.words` is that same swap sentence again).
// The old fixture invented a `words` WITHOUT the swap, which hid a real bug:
// the page joined `words` + `card.words` and printed the swap twice every draw.
calls.length = 0;
const swapSentence =
  "Your everyday chat stepped aside for 300.0 seconds and is back on the card after 41.0 seconds.";
const drawnWords =
  "Drawn in 274.0 seconds and saved as 2026-10-24-101010-a-red-panda.png.";
answer = {
  ok: true,
  available: true,
  name: "2026-10-24-101010-a-red-panda.png",
  words: `${drawnWords} ${swapSentence}`,
  card: {
    option: "A",
    chat_away_seconds: 300,
    chat_back_seconds: 41,
    words: swapSentence,
  },
};
const click = page.setChatAsideAndDraw();
check(
  "(iii) RUN: while it draws, the page says how long and that the chat comes back",
  page.state.said
    === "Drawing - this takes about 5 minutes. Your everyday chat will come back when it is done.",
  page.state.said,
);
check(
  "(iii) RUN: ... and the question is gone while it waits",
  page.state.pending === null,
);
await click;
check(
  "(ii) RUN: the confirm click sends ONE retry, with freeCard: true",
  makeCalls().length === 1 && makeCalls()[0].args.freeCard === true,
  JSON.stringify(makeCalls().map((c) => c.args)),
);
check(
  "(iii) RUN: ... then the gallery is read back from the PC",
  calls.some((c) => c.command === "brain_pictures"),
  JSON.stringify(calls.map((c) => c.command)),
);
check(
  "(iii) RUN: ... and the PC's whole sentence is shown ONCE - the swap sentence is never doubled",
  page.state.said === `${drawnWords} ${swapSentence}`
    && page.state.said.split(swapSentence).length === 2,
  page.state.said,
);

// card_none is a sentence, not a question.
calls.length = 0;
answer = {
  ok: false,
  needs: "card_none",
  error: "None of the three ways of making pictures is switched on.",
};
await page.makePicture("a red panda");
check(
  "(iii) RUN: a card_none 409 is its own sentence, with no question offered",
  page.state.pending === null
    && page.state.said === "None of the three ways of making pictures is switched on.",
  `${page.state.said} | pending=${JSON.stringify(page.state.pending)}`,
);

// Not now sends nothing at all.
page.state.pending = { prompt: "a red panda", error: "", option: "A", seconds: 300 };
calls.length = 0;
page.cancelPending();
check(
  "(ii) RUN: Not now sends nothing, and says nothing was drawn",
  calls.length === 0
    && page.state.said === "Nothing was drawn - your everyday chat stays where it is.",
  `${calls.length} call(s), said=${page.state.said}`,
);

console.log(`\n${passed} passed, ${failed.length} failed`);
if (failed.length) {
  console.log("failed: " + failed.join("; "));
  process.exit(1);
}
