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
  //
  // It WAITS FOR the drawing, rather than sleeping a fixed time and hoping.
  // The first version scrolled every 450 ms and settled for 1.2 s; on a busy
  // machine the first frame of a card can take longer than that, and the
  // test failed on a page that was fine. Now each scroll step waits until
  // every card on screen has drawn (up to 10 s a step), and a card counts as
  // painted the first time any pixel of it is seen - so a card that stops
  // animating once it scrolls away still counts.
  const page = await open();
  await page.waitForFunction(() => document.querySelectorAll("#grid canvas").length >= 20,
    null, { timeout: 30000 });
  const got = await page.evaluate(async () => {
    const canvases = [...document.querySelectorAll("#grid canvas")];
    const seen = new Set();
    const drew = (c) => {
      const ctx = c.getContext("2d");
      if (!ctx || !c.width || !c.height) return false;
      const d = ctx.getImageData(0, 0, c.width, c.height).data;
      for (let i = 3; i < d.length; i += 4) if (d[i] !== 0) return true;
      return false;
    };
    const note = () => canvases.forEach((c, i) => { if (!seen.has(i) && drew(c)) seen.add(i); });
    const onScreen = () => canvases
      .map((c, i) => [c.getBoundingClientRect(), i])
      .filter(([r]) => r.bottom > 0 && r.top < window.innerHeight)
      .map(([, i]) => i);
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const step = window.innerHeight * 0.8;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      const until = performance.now() + 10000;
      for (;;) {
        note();
        if (onScreen().every((i) => seen.has(i)) || performance.now() > until) break;
        await wait(100);
      }
    }
    note();
    return {
      n: seen.size,
      total: canvases.length,
      missing: canvases.map((_, i) => i).filter((i) => !seen.has(i)),
    };
  });
  await page.close();
  assert.equal(got.n, 20,
    `${got.n} of ${got.total} canvases drew anything (never painted: #${got.missing.join(", #")})`);
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

await check("the spec's own defaults survive a save unchanged", async () => {
  // The strongest statement of the round trip: open the window, change
  // nothing, save, and the document must be exactly what the spec says. Three
  // of the eight states live entirely in `params` — `thinking` is `sweep`
  // narrowed to a 58 degree cool band — and a params bug renders all three as
  // their pattern's generic default on every surface.
  const page = await open();
  await page.waitForTimeout(2500);
  await page.locator("#save").click();
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() =>
    (window.__calls.find((c) => c[0] === "__saved") || [])[1]);
  await page.close();

  const spec = JSON.parse(read("src/jarvis-visual-spec.json"));
  for (const st of spec.states) {
    const want = st.default || {};
    const got = saved.bindings[st.id];
    assert.ok(got, `${st.id} was not saved at all`);
    assert.equal(got.pattern, want.pattern, `${st.id}: pattern`);
    assert.deepEqual(got.params || {}, want.params || {},
      `${st.id}: params did not survive — got ${JSON.stringify(got.params)}`);
  }
});

await check("the kit's private bookkeeping is never sent", async () => {
  // The randomiser writes `_fam` onto a binding to remember which hue family
  // it drew from. It means nothing to the phone and must not travel.
  const page = await open();
  await page.waitForTimeout(2500);
  await page.locator("#randomise").click();
  await page.waitForTimeout(300);
  await page.locator("#save").click();
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() =>
    (window.__calls.find((c) => c[0] === "__saved") || [])[1]);
  await page.close();
  for (const [state, binding] of Object.entries(saved.bindings)) {
    for (const key of Object.keys(binding)) {
      assert.ok(["pattern", "color", "params"].includes(key),
        `${state} carried an unexpected key: ${key}`);
    }
    assert.ok(!("_fam" in (binding.params || {})), `${state}: _fam leaked into params`);
  }
});

await check("a loaded document renders, rather than falling back to defaults", async () => {
  // The mirror bug: spreading params to the top level left BIND with no
  // `params` key, so the editor itself drew the pattern's generic default
  // after loading a document that specified otherwise.
  const page = await K.open(browser, base, "faces.html", {
    appearance: {
      face: null, updated: 1, source: "server", shared: true,
      bindings: { thinking: { pattern: "sweep", params: { offset_deg: 10, span_deg: 20 } } },
    },
  }, { width: 1300, height: 950 });
  await page.waitForTimeout(2500);
  const bind = await page.evaluate(() => {
    // Round-trip it back out: if the load flattened the params, the save
    // cannot put them back.
    document.getElementById("save").click();
    return null;
  });
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() =>
    (window.__calls.find((c) => c[0] === "__saved") || [])[1]);
  await page.close();
  assert.deepEqual(saved.bindings.thinking.params, { offset_deg: 10, span_deg: 20 },
    `round-tripped to ${JSON.stringify(saved.bindings.thinking)}`);
});

await check("Iris no longer draws its two specular highlight blobs", async () => {
  // Iris drew a wet-eye catchlight as two opaque white shapes on top of
  // everything else - a big ellipse at roughly 10-11 o'clock and a small
  // dot at roughly 4-5 o'clock. Both were removed; check the pixels where
  // they used to sit rather than just the source, since a live render is
  // what actually proves nothing else still paints white there.
  const page = await open();
  await page.waitForTimeout(1500);
  await page.locator('.card:has(.nm:text-is("Iris")) canvas').click();
  await page.waitForTimeout(400);
  const px = await page.evaluate(() => {
    const cv = document.getElementById("solo-canvas");
    const ctx = cv.getContext("2d");
    const R = Math.min(cv.width, cv.height) * 0.44;
    const cx = cv.width / 2, cy = cv.height / 2;
    const at = (x, y) => Array.from(ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data);
    return {
      bigHighlight: at(cx - R * 0.30, cy - R * 0.34),
      smallHighlight: at(cx + R * 0.26, cy + R * 0.30),
    };
  });
  await page.close();
  const nearWhite = ([r, g, b, a]) => r > 235 && g > 235 && b > 235 && a > 150;
  assert.ok(!nearWhite(px.bigHighlight), `big highlight still there: ${px.bigHighlight}`);
  assert.ok(!nearWhite(px.smallHighlight), `small highlight still there: ${px.smallHighlight}`);
});

await check("Membrane no longer draws the outer rim circle", async () => {
  // The rim was one stroked circle drawn identically after either render
  // path (GPU mesh or CPU quads) - a live pixel test would have to account
  // for perspective, rotation and which path this environment falls back
  // to, none of which the fix touches. What the fix actually changed is
  // that `rim()` and both of its call sites are gone; check that directly.
  for (const src of [read("src/faces.html"), read("../docs/reference/jarvis-reactor-kit.html")]) {
    assert.ok(!src.includes("this.rim("), "a call to the removed rim() method is still present");
    assert.ok(!/\brim\(g, w, h, mid,/.test(src), "the removed rim() method definition is still present");
  }
});

await check("solo view can cycle through every state slowly, and stop", async () => {
  const page = await open();
  await page.waitForTimeout(1500);
  await page.locator('.card:has(.nm:text-is("Iris")) canvas').click();
  await page.waitForTimeout(400);
  assert.equal(await page.locator("#solo-cycle").count(), 1, "no cycle-states control in the solo toolbar");
  const pressedState = () => page.evaluate(() =>
    [...document.querySelectorAll("#states .chip")]
      .find((b) => b.getAttribute("aria-pressed") === "true")?.dataset.s);
  const first = await pressedState();
  await page.locator("#solo-cycle").click();
  assert.equal(await page.locator("#solo-cycle").getAttribute("aria-pressed"), "true",
    "the button does not show itself as on");
  await page.waitForTimeout(4300);
  const second = await pressedState();
  assert.notEqual(second, first, "cycling did not move to a different state");
  await page.locator("#solo-cycle").click();
  assert.equal(await page.locator("#solo-cycle").getAttribute("aria-pressed"), "false",
    "the button does not show itself as off");
  const atOff = await pressedState();
  await page.waitForTimeout(4300);
  const afterOff = await pressedState();
  await page.close();
  assert.equal(afterOff, atOff, "the state kept advancing after cycling was turned off");
});

await check("the Widget's face draws at full sharpness, like the kit's solo view", async () => {
  // Display mode (the Widget's live face) runs its own frame loop and never
  // calls budget(), so it used to stay on the "medium" tier the editor only
  // STARTS on: shader faces ray-marched 80% of the device pixels and were
  // stretched to fit, and every face drew with less geometry (detail 1.6)
  // than the same face in the solo view (1.9). Nucleus is a shader face, so
  // it is the one that shows the gap.
  const page = await K.open(browser, base, "faces.html?mode=display&face=nucleus", {},
                            { width: 120, height: 120 });
  await page.waitForTimeout(1500);
  const got = await page.evaluate(() => ({
    canvases: document.querySelectorAll("canvas").length,
    grid: Boolean(document.getElementById("grid")),
    css: Math.round(document.getElementById("display-canvas").getBoundingClientRect().width),
    dpr: window.devicePixelRatio, tier: QNAME, gpu: Q.gpu, gpupx: GPUPX, detail: QUALITY,
  }));
  await page.close();
  assert.equal(got.canvases, 1, "display mode should draw exactly one face");
  assert.equal(got.grid, false, "display mode built the editor's grid");
  assert.equal(got.tier, "high");
  assert.equal(got.gpu, 1, `the shader is asked for ${got.gpu * 100}% of the device pixels`);
  assert.equal(got.gpupx, Math.round(got.css * Math.min(got.dpr, 3)),
    `shader renders ${got.gpupx}px into a ${got.css}px box at ${got.dpr}x`);
  assert.ok(got.detail >= 1.9, `geometry detail ${got.detail}, the solo view uses 1.9`);
});

await check("the Widget's face slows to 10 redraws a second under reduced motion", async () => {
  // The editor paces itself to CALM_HZ when the OS asks for less motion;
  // display mode (the Widget's face, and the HUD's) used to run at the
  // panel's full rate regardless. Counted at drawSurface, so a frame that
  // happens to look like the last one still counts.
  const page = await K.open(browser, base, "faces.html?mode=display&face=arc", {},
                            { width: 120, height: 120 });
  await page.waitForTimeout(500);
  const rate = () => page.evaluate(() => new Promise((done) => {
    let n = 0;
    const real = drawSurface;
    drawSurface = function (...a) { n++; return real.apply(this, a); };
    setTimeout(() => { drawSurface = real; done(n / 1.5); }, 1500);
  }));
  const normal = await rate();
  await page.emulateMedia({ reducedMotion: "reduce" });
  const calm = await rate();
  await page.close();
  assert.ok(normal > 20, `${normal} draws a second with no reduced-motion setting`);
  assert.ok(calm > 0, "the face stopped drawing altogether - reduce means reduce, not remove");
  assert.ok(calm <= 12, `${calm} draws a second under prefers-reduced-motion`);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe faces window holds");
process.exit(fails.length ? 1 : 0);
