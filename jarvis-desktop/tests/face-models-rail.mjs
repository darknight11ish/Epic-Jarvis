/**
 * face-models-rail.mjs - the face models icon in the HUD's left column, and the
 * picker it opens (the owner's ask, 2026-10-28, verbatim):
 *
 *   "add a jarvis model icon to the left column of the jarvis desktop that has
 *    all of the jarvis models (face models)"
 *
 *     node tests/face-models-rail.mjs
 *
 * WHY THIS SUITE NEEDS NO BROWSER. The panel's rows and its marking are pure
 * functions in `src/hud-presets.js` (`faceRows`, `currentFaceId`), the save is
 * one function (`setFaceOnPc`), and the panel itself is driven here through a
 * small fake DOM - mount, open, click a row, push the shell's answer, Escape -
 * so the selection, the marking and the focus behaviour are exercised for
 * real. The page-level painting (a real WebView2 window, the panel's position
 * on screen) is `tests/hud-presets.mjs`'s half and needs Playwright, which is
 * deliberately not installed on this machine; the file says so instead of
 * pretending.
 *
 * WHAT IT PROVES, in order:
 *   1. the icon is in the left column's own `.rail-toolbar`, as a plain button
 *      in the existing pattern (`class="rail-toolbar-btn"`, a 24-unit `glyph`,
 *      `rt-label`, title and aria-label), and the group holds exactly the
 *      three buttons it should;
 *   2. it needs no style of its own: `.rail-toolbar-btn .glyph` sizes it and
 *      no rule names `#rail-faces`, so the split-stage (Studio) shrink works
 *      unchanged;
 *   3. it does not disturb HUD edit mode: it is not a card, `hud-edit.js`'s
 *      region map is untouched, and no `body[data-hud-edit="on"]` rule hides
 *      the toolbar it lives in;
 *   4. the menu lists EVERY face from the ONE canonical source - the rows are
 *      exactly `faces-spec.js`'s `faces` array, in its order, with its display
 *      names - and neither the page nor the module holds a copy (no face id,
 *      no face name);
 *   5. exactly one row is marked current, from `appearance.face` (or the
 *      spec's own first face when nothing was chosen), and it MOVES when the
 *      shell pushes a saved document - the mark is never set from the click;
 *   6. a click sends the HUD's ONE command, `hud_set_face`, with that face id
 *      and nothing else; clicking the face already worn sends nothing; a
 *      plain browser (no shell) leaves the icon hidden instead of failing;
 *   7. persistence is the EXISTING mechanism, pinned in the source: the
 *      command saves through `set_appearance` (the store first, then
 *      POST /api/appearance), startup reads that store back, and every page
 *      load is pushed the saved document - so a reload keeps the choice and
 *      the phone wears it too;
 *   8. it adds no route, no static asset and no inline script: the list is the
 *      file the Faces window already loads (already on the served whitelist),
 *      and the capability grows by one narrow set;
 *   9. the three vendored copies of the page and of `hud-presets.js` stay
 *      byte-identical.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as P from "../src/hud-presets.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const ROOT = join(HERE, "..", "..");
const read = (path) => readFileSync(path, "utf8");
const page = read(join(SRC, "jarvis_hud.html"));
const presetsSrc = read(join(SRC, "hud-presets.js"));
const appearanceRs = read(join(SRC, "..", "src-tauri", "src", "appearance.rs"));
const specRs = read(join(SRC, "..", "src-tauri", "src", "spec.rs"));
const libRs = read(join(SRC, "..", "src-tauri", "src", "lib.rs"));
const buildRs = read(join(SRC, "..", "src-tauri", "build.rs"));

let fails = 0;
let passed = 0;
function ok(name) { passed += 1; console.log(`ok    ${name}`); }
async function check(name, fn) {
  try {
    await fn();
    ok(name);
  } catch (error) {
    fails += 1;
    console.log(`FAIL  ${name}\n        ${error && error.message ? error.message : error}`);
  }
}

const ACCESSOR = (text) => text.replace(/\s+/g, " ").trim();

/** The fake DOM's selector grammar: `tag`, `.class`, and `[attr="value"]`.
 *  Declared up here because the checks run at top level (`await check(...)`)
 *  before the fake DOM below has been evaluated. */
const SELECTOR = /^([a-z0-9]*)((?:\.[A-Za-z0-9_-]+)*)(?:\[([A-Za-z0-9_-]+)="([^"]*)"\])?$/;

/* ── the canonical list, read the way the page gets it ───────────────────── */

/**
 * `faces-spec.js` is a classic script whose whole body is
 * `window.JARVIS_SPEC = Object.freeze({...});`. This reads the JSON out of it
 * rather than keeping a copy, so a face added to the spec appears in this test
 * with no edit here - and a change to the wrapper fails loudly instead of
 * quietly testing a stale list.
 */
function specFrom(path) {
  const text = read(path);
  const marker = "window.JARVIS_SPEC = Object.freeze(";
  const start = text.indexOf(marker);
  assert.notEqual(start, -1, `${path} is not the generated spec any more`);
  const open = start + marker.length;
  const end = text.lastIndexOf(");");
  assert.ok(end > open, `${path} has no closing \`);\``);
  return JSON.parse(text.slice(open, end));
}

const SPEC = specFrom(join(ROOT, "backend", "static", "faces-spec.js"));
const SPEC_COPY = specFrom(join(SRC, "faces-spec.js"));
const FACES = SPEC.faces;
const NAMES = FACES.map((face) => face.name);
const IDS = FACES.map((face) => face.id);

/* ── 1. The icon is in the left column, in the existing pattern ──────────── */

await check("the face models icon is the left rail's own toolbar button", () => {
  const toolbar = /<div class="rail-toolbar" id="rail-toolbar">([\s\S]*?)\n    <\/div>/.exec(page);
  assert.ok(toolbar, "the page has no #rail-toolbar group");
  const group = toolbar[1];
  assert.match(group, /id="rail-presets"/, "the Presets button left the toolbar");
  assert.match(group, /id="rail-live"/, "the Live button left the toolbar");
  assert.match(group, /id="rail-faces"/, "the toolbar has no #rail-faces button");
  // Four buttons now, in the page's own order: Presets, Live, Faces, and the
  // Calendar door (2026-10-29). The calendar's own card lives in the right
  // rail, which the Studio shell hides, so he can reach his calendar from this
  // toolbar - the same reason the Presets and Faces doors are here. It opens
  // the ONE #calendar-panel; it is not a stage tab and not a second calendar,
  // and tests/hud-calendar.mjs holds its own half.
  assert.match(group, /id="rail-calendar-open"/, "the toolbar has no #rail-calendar-open button");
  assert.deepEqual(
    [...group.matchAll(/<button[^>]*id="([^"]+)"/g)].map((m) => m[1]),
    ["rail-presets", "rail-live", "rail-faces", "rail-calendar-open"],
    "the toolbar's buttons are not the four this page draws");
});

await check("the icon is a plain button with the rail's own classes and an accessible name", () => {
  const tag = /<button[^>]*id="rail-faces"[^>]*>/.exec(page);
  assert.ok(tag, "the page has no #rail-faces button");
  const button = ACCESSOR(tag[0]);
  assert.match(button, /type="button"/, "the icon is not a plain button");
  assert.match(button, /class="rail-toolbar-btn"/, "the icon does not take the rail's button class");
  assert.match(button, /aria-haspopup="dialog"/, "the icon does not say it opens a panel");
  assert.match(button, /aria-expanded="false"/, "the icon starts claiming to be open");
  assert.match(button, /aria-label="Jarvis faces: all the face models, and the one it wears"/,
    "the icon's accessible name does not say what it opens");
  assert.match(button, /title="Jarvis faces: all the face models, and the one it wears"/,
    "the icon has no tooltip");
  // Hidden until the shell is there: a plain browser has no command to send.
  assert.match(button, /\bhidden\b/, "the icon is visible with no shell to switch the face");
  // The glyph is the page's own 24-unit line-drawn pattern, decorative.
  const glyph = /<svg class="glyph"[^>]*>([\s\S]*?)<\/svg>/.exec(
    page.slice(page.indexOf('id="rail-faces"')));
  assert.ok(glyph, "the icon has no glyph");
  assert.match(glyph[0], /viewBox="0 0 24 24"/, "the glyph is off the 24-unit grid");
  assert.match(glyph[0], /aria-hidden="true"/, "the glyph is not decorative");
  assert.match(glyph[0], /focusable="false"/, "the glyph can take focus in IE/old WebView");
  assert.match(glyph[0], /<circle cx="12" cy="12" r="8"\/>/, "the glyph is not a head");
  assert.match(page, /<span class="rt-label">Faces<\/span>/,
    "the button has no short label for the wide rail");
  // The label is "Faces", not "Models": the Current Models panel and the model
  // chip already own that word for the AI model answering.
  const slice = page.slice(page.indexOf('id="rail-faces"'), page.indexOf('id="rail-faces"') + 900);
  assert.equal(/rt-label">Models</.test(slice), false,
    "the face picker is labelled Models, which the HUD already uses for the AI model");
});

await check("the icon reuses the rail's rules, and the toolbar wraps instead of squeezing", () => {
  // Size, colour, hover, focus and the Studio shrink are the shared button
  // rules - the new icon adds none of them.
  assert.match(page, /\.rail-toolbar-btn \.glyph\{width:14px; height:14px;/,
    "the rail's glyph rule is gone, so the new icon has no size");
  assert.match(page, /html\[data-hud-shell="split-stage"\] \.rail-toolbar-btn\{[^}]*width:42px; height:38px;/,
    "the Studio shell no longer shrinks toolbar buttons to icons");
  assert.match(page, /html\[data-hud-shell="split-stage"\] \.rail-toolbar-btn \.rt-label\{display:none;\}/,
    "the Studio shell no longer hides the toolbar labels");
  // The two labelled buttons already fill a 212px (188px) rail, so the third
  // control made the toolbar wrap rather than squeeze all three; the face
  // button keeps its own width on the second row.
  assert.match(page, /\.rail-toolbar\{[^}]*flex-wrap:wrap;/, "the toolbar does not wrap at three buttons");
  assert.match(page, /\.rail-toolbar #rail-faces\{flex:0 1 auto;\}/,
    "the face button stretches over the toolbar's second row");
  // Its glyph takes the shared 14px size: one rule for the button, none for the
  // glyph.
  assert.equal(/#rail-faces\s+\.glyph\s*\{/.test(page), false,
    "the face icon's glyph grew a style of its own");
});

await check("the icon does not disturb HUD edit mode", () => {
  const edit = read(join(SRC, "hud-edit.js"));
  // Not a movable card: the editor's registry names the rail's sections, and
  // the toolbar is not one of them.
  assert.equal(/faces/i.test(edit), false,
    "hud-edit.js mentions faces - a new card id or region was invented for a toolbar button");
  assert.equal(/rail-toolbar/.test(edit), false,
    "hud-edit.js started managing the toolbar, which the face icon now shares");
  // Nothing in edit mode hides the group the icon lives in.
  assert.equal(/body\[data-hud-edit="on"\][^{]*\.rail-toolbar\b/.test(page), false,
    "edit mode hides .rail-toolbar, so the face icon disappears while editing");
  // And the button is not a card the editor would try to reparent.
  const tag = /<button[^>]*id="rail-faces"[^>]*>/.exec(page);
  assert.equal(/hud-card/.test(tag[0]), false, "the icon became an editable HUD card");
});

/* ── 2. The menu lists EVERY face from the canonical source ──────────────── */

await check("the panel is the page's existing popover, with its own title", () => {
  const at = presetsSrc.indexOf("── 6. The face models panel");
  assert.notEqual(at, -1, "hud-presets.js has no face models section");
  const section = presetsSrc.slice(at);
  assert.ok(section.includes('"hud-presets-menu hud-faces-panel"'),
    "the panel does not wear the page's existing popover classes");
  assert.ok(section.includes('nodeOf(doc, "p", "hud-presets-title", "Jarvis faces")'),
    "the panel has no title of its own");
  for (const cls of ["hud-presets-scroll", "hud-presets-item", "hud-presets-line",
    "hud-presets-empty", "hud-presets-close", "hud-models-actions"]) {
    assert.ok(section.includes(cls), `the panel does not reuse ${cls}`);
  }
  assert.match(section, /panel\.setAttribute\("role", "dialog"\)/, "the panel is not a dialog");
  assert.match(section, /aria-label", "Jarvis faces"/, "the panel has no accessible name");
  assert.match(page, /\.hud-faces-panel\{/, "the panel has no width rule");
  assert.match(page, /\.hud-faces-item\[aria-pressed="true"\]\{[\s\S]*?border-color:var\(--ice\)/,
    "the current face has no pressed style (the page's own ice-pressed look)");
});

await check("the rows are the spec's own list - every face, in its order, with its names", () => {
  const rows = P.faceRows(SPEC, null);
  assert.ok(FACES.length >= 20, `the spec lists only ${FACES.length} faces`);
  assert.equal(rows.length, FACES.length,
    `the menu draws ${rows.length} faces where the spec has ${FACES.length}`);
  assert.deepEqual(rows.map((row) => row.id), IDS,
    "the menu's faces are not the spec's faces, in the spec's order");
  assert.deepEqual(rows.map((row) => row.name), NAMES,
    "the menu's names are not the spec's display names");
  for (const row of rows) {
    assert.equal(typeof row.name, "string");
    assert.notEqual(row.name, row.id, `${row.id} has no display name (it shows the raw id)`);
  }
  // The page's served copy is the same list: the browser HUD reads the same
  // file, so there is no second list anywhere.
  assert.deepEqual(SPEC_COPY.faces.map((face) => face.id), IDS,
    "the served faces-spec.js and the copy the page loads disagree");
});

await check("the list is LOADED, never copied - no face id or name is written down", () => {
  // The module: one dynamic import of the spec file, no list of its own. (The
  // page cannot import it: the page loads the module, and the module loads the
  // spec - which is why the import is checked HERE.)
  assert.match(presetsSrc, /await import\("\.\/faces-spec\.js"\)/,
    "the panel does not load the spec file the Faces window loads");
  assert.equal(rowsWrittenDown(page), 0,
    "the page holds its own copy of the face list");
  assert.equal(rowsWrittenDown(presetsSrc), 0,
    "hud-presets.js holds its own copy of the face list");
  // The module renders from `spec.faces`, which is what makes the load work.
  assert.match(presetsSrc, /const faces = Array\.isArray\(spec && spec\.faces\) \? spec\.faces : \[\];/,
    "the rows are not built from the spec's own faces array");
});

/** How many of the spec's own ids/names appear as literals in a file. */
function rowsWrittenDown(text) {
  const needles = [...IDS.slice(0, 12), "Red Panda", "Pygmy Owl", "Sea Otter", "Kirkwood"];
  return needles.filter((needle) => text.includes(`"${needle}"`) || text.includes(`'${needle}'`)).length;
}

await check("the panel is mounted once, from the page's own module block", () => {
  assert.match(page, /import \{ mountFacePicker \} from "\.\/hud-presets\.js";/,
    "the page does not import mountFacePicker");
  assert.equal((page.match(/mountFacePicker\(/g) || []).length, 1,
    "the page mounts the face picker more than once (or never)");
  // No new <script> tag: the page's inline-script count and CSP are unchanged.
  assert.equal(/<script[^>]*hud-faces/.test(page), false, "the feature added a script tag");
});

/* ── 3. The current face is marked, from the shell's document ────────────── */

await check("exactly one row is current, from appearance.face", () => {
  const marked = (spec, appearance) => P.faceRows(spec, appearance).filter((row) => row.current);
  assert.deepEqual(marked(SPEC, { face: "redpanda" }).map((row) => row.id), ["redpanda"],
    "the chosen face is not the one and only marked row");
  for (const face of FACES) {
    const rows = marked(SPEC, { face: face.id });
    assert.equal(rows.length, 1, `${face.id} marked ${rows.length} rows`);
    assert.equal(rows[0].id, face.id, `the wrong row is marked for ${face.id}`);
  }
  // Nothing chosen yet -> the spec's own first face, the SAME fallback
  // faces.html uses when its URL carries no &face=.
  assert.deepEqual(marked(SPEC, null).map((row) => row.id), [FACES[0].id],
    "with no document the first face is not marked");
  assert.deepEqual(marked(SPEC, {}).map((row) => row.id), [FACES[0].id],
    "an empty document is not treated like no choice");
  // An id the spec does not have cannot be marked: the page would draw the
  // first face for it, so that is what the menu must say.
  assert.deepEqual(marked(SPEC, { face: "not-a-face" }).map((row) => row.id), [FACES[0].id],
    "an unknown face id marked nothing (or the wrong row)");
  assert.equal(P.currentFaceId(SPEC, { face: "not-a-face" }), FACES[0].id);
});

await check("the mark moves when the shell pushes a saved document", () => {
  assert.match(presetsSrc, /win\.addEventListener\("jarvis-appearance"/,
    "the panel does not listen for the shell's appearance push");
  assert.match(presetsSrc, /appearance = next;\s*\n\s*if \(panel && !panel\.hidden\) render\(\);/,
    "the push does not repaint the mark");
});

/* ── 4. The save is the ONE existing mechanism ───────────────────────────── */

await check("a click sends ONE command with ONE face id", async () => {
  const calls = [];
  const win = { __TAURI__: { core: { invoke: async (name, args) => { calls.push([name, args]); return { face: args.face }; } } } };
  await P.setFaceOnPc(win, "redpanda");
  assert.deepEqual(calls, [["hud_set_face", { face: "redpanda" }]],
    "the face is not switched through the HUD's one narrow command");
  // No shell -> the honest sentence, and nothing sent.
  await assert.rejects(() => P.setFaceOnPc({}, "redpanda"), /Jarvis desktop window/);
});

await check("the panel's save is that function, and a no-op on the face already worn", async () => {
  assert.match(presetsSrc, /const setFace = options\.setFace \|\| setFaceOnPc;/,
    "the panel does not save through setFaceOnPc");
  const { doc, win, door } = harness();
  const calls = [];
  const picker = P.mountFacePicker({
    document: doc, window: win, spec: SPEC,
    setFace: async (_win, id) => { calls.push(id); return { face: id, shared: true }; },
  });
  door.click();
  const button = rowNamed(picker, "Red Panda");
  button.click();
  await settle();
  assert.deepEqual(calls, ["redpanda"], "the row did not send its own face id");
  // Clicking the face already worn saves nothing. The row is re-read because
  // the save re-rendered the panel (the button the owner sees is the new one).
  rowNamed(picker, "Red Panda").click();
  await settle();
  assert.deepEqual(calls, ["redpanda"], "clicking the current face sent a pointless save");
  assert.match(picker.panel().querySelector(".hud-presets-line").textContent,
    /already the face Jarvis wears/);
});

await check("the save is the SAME set_appearance the Faces window uses, and a reload keeps it", () => {
  // The command: one face id, proved against the spec, then the existing save.
  const fn = /pub async fn hud_set_face\(([\s\S]*?)\n\}\n/.exec(appearanceRs);
  assert.ok(fn, "appearance.rs has no hud_set_face command");
  assert.match(fn[0], /let current = get_appearance\(app\.clone\(\)\)\.await;/,
    "the command does not read the stored document first (it would wipe bindings)");
  assert.match(fn[0], /let doc = with_face\(&current\.appearance, &face\)\?;/,
    "the command does not apply the face to the stored document");
  assert.match(fn[0], /set_appearance\(app, doc\)\.await/,
    "the command does not save through set_appearance");
  // ... and set_appearance is local-first, then adopts, then posts - the same
  // order the Faces window's own save relies on.
  const save = /pub async fn set_appearance\(([\s\S]*?)\n\}\n/.exec(appearanceRs);
  assert.ok(save, "set_appearance is gone");
  const body = save[0];
  const localAt = body.indexOf("save_local(&app, &doc)?;");
  const adoptAt = body.indexOf("adopt(&app, &doc);");
  const postAt = body.indexOf(".post(format!(\"{base}{ROUTE}\"))");
  assert.ok(localAt !== -1 && adoptAt !== -1 && postAt !== -1,
    "set_appearance no longer saves locally, adopts, and posts");
  assert.ok(localAt < adoptAt && adoptAt < postAt,
    "set_appearance no longer saves locally BEFORE it tells anyone or posts");
  // Reload: startup reads that same store, and every page load is pushed it.
  assert.match(appearanceRs, /pub fn adopt_at_startup[\s\S]*?if let Some\(doc\) = local\(app\)/,
    "startup no longer reads the saved appearance, so a reload would forget the face");
  assert.match(libRs, /push_to_hud\(app, "appearance", &appearance\)/,
    "a HUD page load is no longer handed the saved appearance document");
  // And the page puts that document's face into the face frame's URL.
  assert.match(page, /const face = appearance && typeof appearance\.face === "string" \? appearance\.face : "";/,
    "the HUD no longer loads the face its document names");
  assert.match(page, /"&face=" \+ encodeURIComponent\(face\)/,
    "the HUD no longer passes the face id to faces.html");
});

await check("the command refuses a face the spec does not define", () => {
  assert.match(specRs, /pub fn has_face\(face_id: &str\) -> bool/, "spec.rs has no has_face guard");
  assert.match(specRs, /root\["faces"\]\.as_array\(\)/, "spec.rs does not read the spec's faces");
  assert.match(appearanceRs, /if !crate::spec::has_face\(face\)/, "the command does not validate the id");
});

/* ── 5. The panel, driven: open, pick, mark, Escape ──────────────────────── */

await check("the door opens the one panel and says it is expanded", () => {
  const { doc, win, door } = harness();
  const picker = P.mountFacePicker({ document: doc, window: win, spec: SPEC });
  assert.equal(door.hidden, false, "the mount did not reveal the icon in the shell");
  assert.equal(door.getAttribute("aria-expanded"), "false");
  door.click();
  const panel = picker.panel();
  assert.ok(panel, "the door opened no panel");
  assert.equal(panel.hidden, false);
  assert.equal(door.getAttribute("aria-expanded"), "true",
    "the door does not say the panel is open");
  assert.equal(panel.getAttribute("role"), "dialog");
  assert.equal(panel.getAttribute("aria-label"), "Jarvis faces");
  const rows = panel.querySelectorAll(".hud-faces-item");
  assert.equal(rows.length, FACES.length,
    `the panel draws ${rows.length} rows where the spec has ${FACES.length}`);
  assert.deepEqual(rows.map((row) => row.dataset.face), IDS,
    "the panel's rows are not the spec's faces in order");
  const marked = rows.filter((row) => row.getAttribute("aria-pressed") === "true");
  assert.equal(marked.length, 1, "the panel marks more than one face current");
  assert.equal(marked[0].dataset.face, FACES[0].id);
  assert.equal(doc.activeElement, marked[0], "opening did not put focus on the current face");
});

await check("picking marks the face the shell says was saved - not the one clicked", async () => {
  const { doc, win, door } = harness();
  const picker = P.mountFacePicker({
    document: doc, window: win, spec: SPEC,
    // A save that REFUSES: the panel must not mark the click.
    setFace: async () => { throw new Error("Jarvis is not answering"); },
  });
  door.click();
  rowNamed(picker, "Red Panda").click();
  await settle();
  const rows = picker.panel().querySelectorAll(".hud-faces-item");
  const marked = rows.filter((row) => row.getAttribute("aria-pressed") === "true");
  assert.equal(marked.length, 1, "a failed save marked no face (or several)");
  assert.equal(marked[0].dataset.face, FACES[0].id,
    "a failed save moved the mark anyway");
  assert.match(picker.panel().querySelector(".hud-presets-line").textContent,
    /The face did not change: Jarvis is not answering/,
    "a failed save did not say so in the PC's own words");
  // The shell pushes the document it saved; THAT is what moves the mark.
  win.dispatch("jarvis-appearance", { detail: { face: "redpanda", bindings: {}, updated: 5 } });
  const after = picker.panel().querySelectorAll(".hud-faces-item")
    .filter((row) => row.getAttribute("aria-pressed") === "true");
  assert.deepEqual(after.map((row) => row.dataset.face), ["redpanda"],
    "the push did not move the mark to the face the shell saved");
});

await check("Escape closes it and gives focus back to the icon", () => {
  const { doc, win, door } = harness();
  const picker = P.mountFacePicker({ document: doc, window: win, spec: SPEC });
  door.click();
  doc.dispatch("keydown", keyEvent("Escape"));
  assert.equal(picker.panel().hidden, true, "Escape did not close the panel");
  assert.equal(door.getAttribute("aria-expanded"), "false",
    "the icon still claims the panel is open");
  assert.equal(doc.activeElement, door, "Escape did not return focus to the icon");
  // A second click on the door reopens it.
  door.click();
  assert.equal(picker.panel().hidden, false, "the icon no longer opens the panel");
});

await check("a plain browser keeps the icon hidden - there is no command to send", () => {
  const { doc, win, door } = harness();
  win.__TAURI__ = undefined;
  const picker = P.mountFacePicker({ document: doc, window: win, spec: SPEC });
  assert.equal(picker, null, "the picker mounted with no shell to save through");
  assert.equal(door.hidden, true, "the icon is offered by a page that cannot switch the face");
  assert.equal(doc.getElementById("hud-faces-menu"), null,
    "a panel was built with no shell to save through");
});

await check("the panel says when a save stayed on this machine", () => {
  assert.equal(P.faceSwitchWords({ name: "Red Panda" }, { shared: true }), "Now wearing Red Panda.");
  const localOnly = P.faceSwitchWords({ name: "Red Panda" }, {
    shared: false,
    note: "Saved on this machine. This backend has no /api/appearance, so the phone will not see it.",
  });
  assert.match(localOnly, /^Now wearing Red Panda\./, "the sentence does not name the face");
  assert.match(localOnly, /phone will not see it/,
    "a save that did not reach the PC claims the phone has the face too");
});

/* ── 6. No new route, no new static asset, one narrow capability ─────────── */

await check("the feature adds no route", () => {
  const section = presetsSrc.slice(presetsSrc.indexOf("── 6. The face models panel"));
  assert.equal(/apiUrlFor\(/.test(section), false, "the face panel names an API route of its own");
  assert.equal(/(?<![.\w])fetch\s*\(/.test(section), false, "the face panel calls fetch");
  assert.equal(/\.post\b/.test(section), false, "the face panel posts anything itself");
});

await check("the served whitelist already answers the spec file", () => {
  const served = read(join(ROOT, "jarvis-backend", "jarvis_hud.py"));
  assert.match(served, /"\/faces-spec\.js": \("faces-spec\.js", "text\/javascript; charset=utf-8"\)/,
    "the browser HUD cannot load the face list: /faces-spec.js is not served");
});

await check("one narrow capability set holds the ONE command", () => {
  const capability = JSON.parse(read(join(SRC, "..", "src-tauri", "capabilities", "hud.json")));
  assert.deepEqual(capability.permissions.filter((name) => name === "hud-faces"), ["hud-faces"],
    "the HUD window holds the face set zero times, or more than once");
  assert.match(capability.description, /hud-faces/,
    "the capability does not say what the face grant is");
  const surfaces = read(join(SRC, "..", "src-tauri", "permissions", "surfaces.toml"));
  const at = surfaces.indexOf('identifier = "hud-faces"');
  assert.notEqual(at, -1, "surfaces.toml has no hud-faces set");
  const set = surfaces.slice(at, surfaces.indexOf("[[set]]", at) === -1
    ? undefined : surfaces.indexOf("[[set]]", at));
  assert.match(set, /"allow-hud-set-face"/, "the set misses allow-hud-set-face");
  assert.equal(/allow-hud-get-appearance|allow-set-appearance|allow-get-appearance/.test(set), false,
    "the face set grants the whole appearance read/write to a page that holds no token");
  assert.match(buildRs, /"hud_set_face"/, "build.rs does not declare the command, so it has no permission");
  assert.match(libRs, /appearance::hud_set_face/, "lib.rs does not register the command");
});

/* ── 7. The three vendored copies stay identical ─────────────────────────── */

await check("the page and hud-presets.js are byte-identical in all three places", () => {
  const digest = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
  const pages = [
    join(SRC, "jarvis_hud.html"),
    join(ROOT, "backend", "jarvis_hud.html"),
    join(ROOT, "jarvis-backend", "jarvis_hud.html"),
  ];
  const modules = [
    join(SRC, "hud-presets.js"),
    join(ROOT, "backend", "static", "hud-presets.js"),
    join(ROOT, "jarvis-backend", "hud-presets.js"),
  ];
  assert.equal(new Set(pages.map(digest)).size, 1,
    "the three jarvis_hud.html copies are not byte-identical");
  assert.equal(new Set(modules.map(digest)).size, 1,
    "the three hud-presets.js copies are not byte-identical");
});

/* ── the fake DOM: just enough for the panel ─────────────────────────────── */

function matches(node, selector) {
  const found = SELECTOR.exec(selector);
  assert.ok(found, `the fake DOM cannot match ${selector}`);
  const [, tag, classes, attr, value] = found;
  if (tag && node.tagName !== tag.toUpperCase()) return false;
  for (const cls of classes.split(".").filter(Boolean)) {
    if (!String(node.className || "").split(/\s+/).includes(cls)) return false;
  }
  if (attr) {
    const got = attr === "class" ? node.className : node.getAttribute(attr);
    if (got !== value) return false;
  }
  return true;
}

function makeElement(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: "", id: "", type: "", title: "", hidden: false, disabled: false,
    dataset: {}, style: {}, children: [], parentNode: null, attrs: {}, listeners: {},
    _text: "",
    setAttribute(name, value) {
      if (name === "class") node.className = String(value);
      else node.attrs[name] = String(value);
    },
    getAttribute(name) {
      if (name === "class") return node.className;
      return Object.prototype.hasOwnProperty.call(node.attrs, name) ? node.attrs[name] : null;
    },
    appendChild(child) {
      child.parentNode = node;
      node.children.push(child);
      return child;
    },
    addEventListener(type, fn) {
      (node.listeners[type] = node.listeners[type] || []).push(fn);
    },
    dispatch(type, event) {
      for (const fn of node.listeners[type] || []) fn(event);
    },
    click() {
      node.dispatch("click", { target: node, preventDefault() {}, stopPropagation() {} });
    },
    focus() {
      doc.activeElement = node;
    },
    getBoundingClientRect() {
      return { left: 12, top: 200, bottom: 240, right: 54, width: 42, height: 40 };
    },
    contains(other) {
      for (let at = other; at; at = at.parentNode) if (at === node) return true;
      return false;
    },
    querySelectorAll(selector) {
      const found = [];
      const walk = (parent) => {
        for (const child of parent.children) {
          if (matches(child, selector)) found.push(child);
          walk(child);
        }
      };
      walk(node);
      return found;
    },
    querySelector(selector) {
      return node.querySelectorAll(selector)[0] || null;
    },
  };
  Object.defineProperty(node, "textContent", {
    get() {
      return node._text + node.children.map((child) => child.textContent).join("");
    },
    set(value) {
      node.children.length = 0;
      node._text = value === undefined || value === null ? "" : String(value);
    },
  });
  Object.defineProperty(node, "isConnected", {
    get() {
      for (let at = node; at; at = at.parentNode) if (at === doc.body) return true;
      return false;
    },
  });
  return node;
}

/** A document, a window and the icon, arranged as the real page has them. */
function harness() {
  const doc = {
    listeners: {},
    body: null,
    activeElement: null,
    createElement(tag) { return makeElement(doc, tag); },
    getElementById(id) {
      let found = null;
      const walk = (parent) => {
        for (const child of parent.children) {
          if (found) return;
          if (child.id === id) { found = child; return; }
          walk(child);
        }
      };
      walk(doc.body);
      return found;
    },
    addEventListener(type, fn) { (doc.listeners[type] = doc.listeners[type] || []).push(fn); },
    dispatch(type, event) {
      for (const fn of doc.listeners[type] || []) fn(event);
    },
  };
  doc.body = makeElement(doc, "body");
  doc.activeElement = doc.body;
  const toolbar = doc.createElement("div");
  toolbar.className = "rail-toolbar";
  const door = doc.createElement("button");
  door.className = "rail-toolbar-btn";
  door.id = "rail-faces";
  door.hidden = true;
  toolbar.appendChild(door);
  doc.body.appendChild(toolbar);
  const listeners = {};
  const win = {
    innerWidth: 1280,
    innerHeight: 900,
    __TAURI__: { core: { invoke: async (name, args) => ({ face: args && args.face }) } },
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    dispatch(type, event) { for (const fn of listeners[type] || []) fn(event); },
  };
  return { doc, win, door };
}

function rowNamed(picker, name) {
  const row = picker.panel().querySelectorAll(".hud-faces-item")
    .find((button) => button.textContent.startsWith(name));
  assert.ok(row, `the panel has no row for ${name}`);
  return row;
}

function keyEvent(key) {
  return { key, preventDefault() {}, stopPropagation() {} };
}

/** Let the panel's own promise chain finish (two microtask turns is enough). */
function settle() {
  return Promise.resolve().then(() => Promise.resolve()).then(() => Promise.resolve());
}

/* ── the verdict ─────────────────────────────────────────────────────────── */

console.log(`\n${passed} passed, ${fails} failed - the face models icon lists ${FACES.length} `
  + `faces from faces-spec.js (${IDS.join(", ")})`);
if (fails) process.exitCode = 1;
