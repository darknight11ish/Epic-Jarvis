/**
 * The Faces window.
 *
 * This is the reactor kit — 3,800 lines of hand-written Canvas 2D that draw
 * twenty procedural faces — brought in from `docs/reference/` where it was a
 * standalone page. Almost none of it is mine and none of it is touched, so
 * these tests are not about the drawing. They are about the three things that
 * were wrong with it as a page and would have stayed wrong as a window, plus
 * the one rule that keeps it from drifting again.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const open = () => K.open(browser, base, "faces.html", {}, { width: 1300, height: 950 });

/* ── One spec, not two ───────────────────────────────────────────────────── */

await check("the window binds every state the spec defines", async () => {
  // The kit pasted the spec inline, and that copy had drifted to seven states
  // against the live eight — so `banked` could not be bound at all, on the one
  // surface whose entire job is binding. Nothing could have caught it: two
  // hand-maintained copies of the same data do not complain.
  const spec = JSON.parse(read("src/jarvis-visual-spec.json"));
  const page = await open();
  await page.waitForTimeout(2500);
  const shown = await page.evaluate(() =>
    [...document.querySelectorAll("#states .chip")].map((b) => b.dataset.s));
  await page.close();
  assert.deepEqual(shown, spec.states.map((s) => s.id));
  assert.ok(shown.includes("banked"), "banked is still unbindable");
});

await check("the generated spec script matches the JSON it came from", async () => {
  // Regenerate and compare. If this fails, someone edited the generated file
  // or changed the JSON without re-running the generator.
  const before = read("src/faces-spec.js");
  execFileSync("python3", [join(ROOT, "scripts", "build-faces-spec.py")], { cwd: ROOT });
  assert.equal(read("src/faces-spec.js"), before,
    "src/faces-spec.js is out of date — run `npm run faces:spec`");
});

await check("every face and pattern in the spec has a card or a chip", async () => {
  const spec = JSON.parse(read("src/jarvis-visual-spec.json"));
  const page = await open();
  await page.waitForTimeout(2500);
  const got = await page.evaluate(() => ({
    cards: document.querySelectorAll("#grid .card").length,
    patterns: [...document.querySelectorAll("#patterns .chip")].map((b) => b.dataset.p),
  }));
  await page.close();
  assert.equal(got.cards, spec.faces.length, `${got.cards} cards for ${spec.faces.length} faces`);
  assert.deepEqual(got.patterns, spec.patterns.map((p) => p.id));
});

/* ── The two defects it arrived with ─────────────────────────────────────── */

await check("the page declares its encoding", async () => {
  // It never had a charset. Every `·` and `—` rendered as mojibake, which is
  // most of the labels on the page.
  const html = read("src/faces.html");
  assert.match(html.slice(0, 200), /<meta charset="utf-8"/i);
  const page = await open();
  const kicker = await page.evaluate(() => document.querySelector(".lbl")?.textContent || "");
  await page.close();
  assert.ok(kicker.includes("·"), `the separator rendered as "${kicker}"`);
  assert.ok(!/Â|â€/.test(kicker), `mojibake survives: "${kicker}"`);
});

await check("nothing is fetched from the network", async () => {
  // The kit linked Google Fonts. The content security policy blocks a remote
  // stylesheet, so in the app it would have silently fallen back to system
  // fonts — the same bug already recorded for the HUD as entry 8.
  const html = read("src/faces.html");
  assert.ok(!/https?:\/\//.test(html.replace(/<!--[\s\S]*?-->/g, "")),
    "the page still references a remote URL");
  assert.match(html, /fonts\/fonts\.css/, "it does not use the bundled fonts");
});

/* ── It actually draws ───────────────────────────────────────────────────── */

await check("the faces are painted once they are on screen", async () => {
  // Only visible cards animate — an intersection observer, and the right call
  // for twenty procedural canvases several of which integrate a physics step
  // per frame. So this scrolls the grid past every one of them and then asks
  // whether each drew, which also exercises the lazy path itself.
  const page = await open();
  await page.waitForTimeout(2000);
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.8;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 450));
    }
  });
  await page.waitForTimeout(1200);
  const painted = await page.evaluate(() => {
    let n = 0;
    for (const c of document.querySelectorAll("#grid canvas")) {
      const ctx = c.getContext("2d");
      if (!ctx) continue;
      const d = ctx.getImageData(0, 0, c.width, c.height).data;
      for (let i = 3; i < d.length; i += 4) {
        if (d[i] !== 0) { n += 1; break; }
      }
    }
    return n;
  });
  await page.close();
  assert.equal(painted, 20, `${painted} of 20 canvases drew anything`);
});

await check("a card that is off screen is not being animated", async () => {
  // The other half of the same fact, and the one worth protecting: twenty
  // canvases animating unseen is a laptop fan.
  const page = await open();
  await page.waitForTimeout(2500);
  const live = await page.evaluate(() => document.body.innerText.match(/(\d+) live/)?.[1]);
  await page.close();
  assert.ok(live, "the page no longer reports how many faces are live");
  assert.ok(Number(live) < 20, `all ${live} faces animate with most of them off screen`);
});

await check("CONTROL: the page threw nothing", async () => {
  const page = await open();
  await page.waitForTimeout(3000);
  const errs = page.__errors.filter((e) => !/favicon/i.test(e));
  await page.close();
  assert.deepEqual(errs, [], errs.join(" | "));
});

/* ── Reach ───────────────────────────────────────────────────────────────── */

await check("CONTROL: the window is reachable and narrowly permitted", async () => {
  const tray = read("src-tauri/src/tray.rs");
  assert.match(tray, /ID_SHOW_FACES/, "no tray row opens it");
  const cap = JSON.parse(read("src-tauri/capabilities/faces.json"));
  // It draws. It has no business holding the stream, the queue or the settings.
  for (const denied of ["jarvis-link", "approvals", "settings-surface", "brain-read"]) {
    assert.ok(!cap.permissions.includes(denied),
      `the faces window was granted ${denied}`);
  }
});

/* ── The bindings are a document, and it is shared ───────────────────────── */

await check("what the editor saves is what the spec can read back", async () => {
  const page = await open();
  await page.waitForTimeout(2500);
  // Bind `banked` to something deliberate, then save and inspect the document.
  await page.locator('#states .chip[data-s="banked"]').click();
  await page.locator('#patterns .chip[data-p="solid"]').click();
  await page.locator("#save").click();
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() =>
    (window.__calls.find((c) => c[0] === "__saved") || [])[1]);
  await page.close();
  assert.ok(saved, "save sent nothing");
  const spec = JSON.parse(read("src/jarvis-visual-spec.json"));
  const ids = new Set(spec.states.map((s) => s.id));
  const patterns = new Set(spec.patterns.map((p) => p.id));
  for (const [state, binding] of Object.entries(saved.bindings)) {
    assert.ok(ids.has(state), `saved a state the spec does not have: ${state}`);
    assert.ok(patterns.has(binding.pattern),
      `saved a pattern the spec does not have: ${binding.pattern}`);
  }
  assert.equal(saved.bindings.banked.pattern, "solid");
});

await check("a hue-generating pattern is saved without a colour", async () => {
  // `rainbow` ignores the colour. Writing one would tell the phone it matters.
  const page = await open();
  await page.waitForTimeout(2500);
  await page.locator('#states .chip[data-s="idle"]').click();
  await page.locator('#patterns .chip[data-p="rainbow"]').click();
  await page.locator("#save").click();
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() =>
    (window.__calls.find((c) => c[0] === "__saved") || [])[1]);
  await page.close();
  assert.equal(saved.bindings.idle.pattern, "rainbow");
  assert.ok(!("color" in saved.bindings.idle),
    `a colour was stored anyway: ${JSON.stringify(saved.bindings.idle)}`);
});

await check("it says whether the phone will see the change", async () => {
  // Saved and shared are different facts. Claiming the phone changed when it
  // did not is worse than admitting the route is missing.
  const page = await open();
  await page.waitForTimeout(2500);
  await page.locator("#save").click();
  await page.waitForTimeout(300);
  const shared = await page.locator("#save-state").innerText();
  await page.close();
  assert.match(shared, /phone sees this too/i, `said "${shared}"`);
});

await check("with no backend route it says so instead of claiming success", async () => {
  const page = await K.open(browser, base, "faces.html", { noRoute: true },
    { width: 1300, height: 950 });
  await page.waitForTimeout(2500);
  await page.locator("#save").click();
  await page.waitForTimeout(300);
  const said = await page.locator("#save-state").innerText();
  await page.close();
  assert.match(said, /this machine/i, `said "${said}"`);
  assert.doesNotMatch(said, /phone sees this too/i,
    "it claimed the phone would see a change that went nowhere");
});

await check("a saved document is applied when the window reopens", async () => {
  const page = await K.open(browser, base, "faces.html", {
    appearance: {
      face: "orbit", updated: 1, source: "server", shared: true,
      bindings: { idle: { pattern: "pulse", color: "violet-4" } },
    },
  }, { width: 1300, height: 950 });
  await page.waitForTimeout(2500);
  const bound = await page.evaluate(() => {
    document.querySelector('#states .chip[data-s="idle"]').click();
    const on = document.querySelector('#patterns .chip[aria-pressed="true"]');
    return on ? on.dataset.p : null;
  });
  await page.close();
  assert.equal(bound, "pulse", "the stored binding was not applied");
});

await check("CONTROL: a state the spec does not have is ignored, not thrown on", async () => {
  // The phone may be a version ahead. Refusing the whole document over one
  // unknown key would make the older client unusable.
  const page = await K.open(browser, base, "faces.html", {
    appearance: {
      face: null, updated: 1, source: "server", shared: true,
      bindings: { idle: { pattern: "solid", color: "ice-3" }, daydreaming: { pattern: "solid" } },
    },
  }, { width: 1300, height: 950 });
  await page.waitForTimeout(2500);
  const errs = page.__errors.filter((e) => !/favicon/i.test(e));
  await page.close();
  assert.deepEqual(errs, [], errs.join(" | "));
});

await check("a face can be chosen, and the choice is saved", async () => {
  // Until now nothing in the UI set `face`: the field existed, was sent as
  // null every time, and the "full editor" could bind states but not pick the
  // thing being bound.
  const page = await open();
  await page.waitForTimeout(2500);
  await page.locator("#grid .card canvas").first().click();
  await page.waitForTimeout(400);
  await page.locator("#solo-use").click();
  // The solo view is a full overlay and Save is behind it.
  await page.locator("#solo-close").click();
  await page.waitForTimeout(200);
  await page.locator("#save").click();
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() =>
    (window.__calls.find((c) => c[0] === "__saved") || [])[1]);
  await page.close();
  const spec = JSON.parse(read("src/jarvis-visual-spec.json"));
  assert.ok(saved.face, "no face was saved");
  assert.ok(spec.faces.some((f) => f.id === saved.face),
    `saved a face the spec does not have: ${saved.face}`);
});

await check("choosing the same face again clears the choice", async () => {
  // No choice is not the same as choosing the default: an absent `face` leaves
  // each client on its own, and a phone whose default differs should keep it.
  const page = await open();
  await page.waitForTimeout(2500);
  await page.locator("#grid .card canvas").first().click();
  await page.waitForTimeout(400);
  await page.locator("#solo-use").click();
  await page.locator("#solo-use").click();
  // The solo view is a full overlay and Save is behind it.
  await page.locator("#solo-close").click();
  await page.waitForTimeout(200);
  await page.locator("#save").click();
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() =>
    (window.__calls.find((c) => c[0] === "__saved") || [])[1]);
  await page.close();
  assert.equal(saved.face, null, `face was ${JSON.stringify(saved.face)}`);
});

await check("the window says where a face choice actually lands", async () => {
  // Nothing on this desktop draws a spec face — the tray is a disc and the
  // spotlight has its own SVG reactor — so a chosen face reaches the phone
  // and changes nothing here. Saying so is the difference between a feature
  // and a lie.
  const page = await open();
  await page.waitForTimeout(1500);
  const text = await page.evaluate(() => document.body.innerText);
  await page.close();
  assert.match(text, /nothing on this desktop draws one yet/i,
    "the page does not say that a chosen face does not apply here");
});

await check("CONTROL: the tray reads the saved bindings, not just the spec", async () => {
  // The bug this pass found: the editor edited a document nothing else read.
  const tray = read("src-tauri/src/tray.rs");
  assert.match(tray, /AppearanceState>\(\)\s*\n?\s*\.binding\(id\)/,
    "binding_for still reads the spec alone");
  assert.match(tray, /pub fn on_appearance_changed/,
    "nothing repaints the tray when the document changes");
  const rust = read("src-tauri/src/appearance.rs");
  assert.match(rust, /fn adopt\(/, "no path puts a saved document into the cache");
  assert.match(rust, /pub fn adopt_at_startup/, "the stored document is not loaded at startup");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe faces window holds");
process.exit(fails.length ? 1 : 0);
