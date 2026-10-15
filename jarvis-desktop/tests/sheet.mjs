/** Contact sheet: every state, one image, on a checkerboard so the window
 *  transparency is part of what is being judged. `node tests/sheet.mjs [theme]`
 *
 *  The inputs are the shots `tests/shots.mjs` renders into `shots/<theme>/`
 *  and the repository commits - one picture per scene, so a whole change can
 *  be looked at at once. This file only composes them; the scenes are read out
 *  of `tests/shots.mjs` rather than retyped here.
 *
 *  What it holds (2026-10-14), so that a sheet of the wrong pictures cannot
 *  read as a good one:
 *  - `shots/<theme>/` holds every scene `shots.mjs` declares, and no other
 *    picture - a shot that was never rendered, or one left behind by a scene
 *    that was renamed, is named in the failure;
 *  - every input is a real PNG, with a size a decoder would agree with;
 *  - the page really drew one cell per shot, every picture in it decoded, and
 *    every one is labelled with the state it is;
 *  - the sheet that came out is a real PNG, the width of the grid, and at
 *    least as tall as its tallest picture.
 *
 *  Until 2026-10-14 it read whatever PNGs happened to be in the folder, wrote
 *  a blank sheet when there were none, printed the path and exited 0 - which
 *  reads exactly like success. The checks that need no browser run before
 *  Chromium is launched, so an empty or missing `shots/<theme>/` says which
 *  command to run rather than failing inside the browser.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const OUT = fileURLToPath(new URL("./shots", import.meta.url));
const SHOTS = fileURLToPath(new URL("./shots.mjs", import.meta.url));
const theme = process.argv[2] || "default";
const dir = path.join(OUT, theme);

let passed = 0;
let failed = 0;
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

const PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
/** The width and height a decoder reads out of the file, or a plain refusal. */
const pngSize = (file) => {
  const b = fs.readFileSync(file);
  const name = path.basename(file);
  assert.ok(b.length > 33, `${name} is ${b.length} bytes - not a picture at all`);
  assert.ok(b.subarray(0, 8).equals(PNG_SIG), `${name} does not begin with the PNG signature`);
  assert.equal(b.subarray(12, 16).toString("latin1"), "IHDR", `${name} has no IHDR chunk`);
  return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
};

// Each scenario's `id` is the name of the shot it writes, so the scene list is
// the list of pictures a sheet of this theme must contain.
const sceneIds = [...fs.readFileSync(SHOTS, "utf8").matchAll(/^\s*\{ id: "([^"]+)",/gm)]
  .map((m) => m[1]);

await check("tests/shots.mjs still declares the scenes this sheet is a sheet of", () => {
  assert.ok(sceneIds.length > 1, `shots.mjs declares ${sceneIds.length} scenes`);
  assert.equal(new Set(sceneIds).size, sceneIds.length, "a scene is declared twice");
});

let files = [];
await check(`shots/${theme}/ holds every scene's shot, and no other picture`, () => {
  assert.ok(fs.existsSync(dir),
    `shots/${theme}/ does not exist - run \`node tests/shots.mjs${
      theme === "default" ? "" : " " + theme}\` first`);
  files = fs.readdirSync(dir).filter((f) => f.endsWith(".png")).sort();
  const want = sceneIds.map((id) => `${id}.png`).sort();
  assert.deepEqual(
    { missing: want.filter((f) => !files.includes(f)), extra: files.filter((f) => !want.includes(f)) },
    { missing: [], extra: [] },
    `shots/${theme}/ is not the set of pictures shots.mjs renders`);
});

await check(`every picture in shots/${theme}/ is a real PNG of a real size`, () => {
  for (const f of files) {
    const s = pngSize(path.join(dir, f));
    assert.ok(s.width > 0 && s.height > 0, `${f} is ${s.width}x${s.height}`);
  }
});

if (failed) {
  console.log("\nNothing was drawn: a contact sheet is only ever a picture of the shots above.");
  console.log(`\nThe contact sheet: ${passed} passed, ${failed} failed`);
  process.exit(1);
}

const cells = files.map((f) => ({
  label: f.replace(/\.png$/, "").replace(/^\d+-/, ""),
  data: "data:image/png;base64," + fs.readFileSync(path.join(dir, f)).toString("base64"),
}));

const browser = await K.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 400 } });
await page.setContent(`<style>
  body{margin:0;background:#15171c;font:12px "Segoe UI",system-ui,sans-serif;color:#cfd6e0}
  .g{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding:18px}
  figure{margin:0} figcaption{padding:0 0 6px;font-size:10px;letter-spacing:.06em;
    text-transform:uppercase;color:#7d8899}
  .plate{background-color:#fff;background-image:
      linear-gradient(45deg,#d8dde4 25%,transparent 25%,transparent 75%,#d8dde4 75%),
      linear-gradient(45deg,#d8dde4 25%,transparent 25%,transparent 75%,#d8dde4 75%);
    background-size:16px 16px;background-position:0 0,8px 8px;border-radius:8px;overflow:hidden}
  .plate img{display:block;width:100%}
</style><div class="g">${cells.map((c) =>
  `<figure><figcaption>${c.label}</figcaption><div class="plate"><img src="${c.data}"></div></figure>`
).join("")}</div>`);

let drawn = { figures: 0, imgs: [] };
await check("the page drew one cell per shot, and every picture in it decoded", async () => {
  // Waited on rather than slept through: the sheet's own height is the page's
  // layout, and a picture that has not decoded yet has no height to give it.
  await page.waitForFunction((n) =>
    document.images.length === n
      && [...document.images].every((i) => i.complete && i.naturalWidth > 0),
  cells.length, { timeout: 15000 });
  drawn = await page.evaluate(() => ({
    figures: document.querySelectorAll("figure").length,
    imgs: [...document.images].map((i) => ({ w: i.naturalWidth, h: i.naturalHeight })),
  }));
  assert.equal(drawn.figures, cells.length, "a shot has no cell of its own");
  assert.equal(drawn.imgs.length, cells.length, "a cell has no picture inside it");
  for (const [n, i] of drawn.imgs.entries()) {
    assert.ok(i.w > 0 && i.h > 0, `${files[n]} decoded to ${i.w}x${i.h}`);
  }
});

await check("every picture is labelled with the state it is", async () => {
  const captions = await page.evaluate(() =>
    [...document.querySelectorAll("figcaption")].map((f) => f.textContent));
  assert.deepEqual(captions, cells.map((c) => c.label));
});

const out = path.join(OUT, `sheet-${theme}.png`);
await page.screenshot({ path: out, fullPage: true });
await browser.close();
console.log(out);

await check(`shots/sheet-${theme}.png is a real PNG, the width of the grid and a picture tall`, () => {
  const s = pngSize(out);
  assert.equal(s.width, 1500, `the sheet came out ${s.width} wide`);
  // Three columns inside 18px of padding and 18px of gap either side, so every
  // picture is drawn 476px wide and its own height decides its cell's. A sheet
  // shorter than the tallest of them lost pictures rather than drawing them.
  const tallest = Math.max(...drawn.imgs.map((i) => (i.h * 476) / i.w));
  assert.ok(s.height >= tallest,
    `the sheet is ${s.height} tall, and its tallest picture is drawn ${Math.round(tallest)}`);
});

console.log(`\nThe contact sheet: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
