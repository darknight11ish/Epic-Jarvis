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

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe faces window holds");
process.exit(fails.length ? 1 : 0);
