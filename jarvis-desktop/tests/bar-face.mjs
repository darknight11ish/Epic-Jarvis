/**
 * The miniature in the bar (the owner's request, 2026-10-10).
 *
 * The bar's far-left mark used to be an abstract SVG: two dashed rings, eight
 * vanes and a glowing core, coloured per state by `style.css`. It was never
 * decoration - it showed listening (ember), waiting on you (an amber ring
 * knocking), an error (red rings turning backward) and a reply streaming (a
 * spin) - so replacing it had to keep that meaning, not just look nicer.
 *
 * The owner asked for a miniature of the face they chose instead. What must
 * hold:
 * - the slot holds the project's OWN face renderer - the same
 *   `faces.html?mode=display` the widget, the floating face and the HUD embed -
 *   never a second drawing and never a picture on disk (a stale image could not
 *   follow the owner's choice);
 * - the bar hands it the same state every other face surface is handed
 *   (`faceSignal`), so the bar cannot disagree with the widget, the floating
 *   face or the HUD: the hollow ring when Jarvis cannot be reached, the focus
 *   session's awake rest, the serious weight of a crisis moment;
 * - the owner's chosen face reaches it, from the read-only command the bar's
 *   own permission set already allows;
 * - "Caught it" (the contraction on release) and the speech envelope still
 *   drive it, and the abstract shapes those rules addressed are gone rather
 *   than left as dead selectors.
 *
 * The browser half drives the real frame in a real browser and reads what it
 * was told - a message that is posted but not understood looks exactly like a
 * message that was never posted otherwise.
 *
 *     node tests/bar-face.mjs
 *
 * Needs Playwright (tests/README.md); the source half runs without it.
 */
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The markup and the stylesheet ───────────────────────────────────────── */

await check("the bar's first slot is the face frame, not the abstract mark", async () => {
  const html = read("src/index.html");
  const slot = html.slice(html.indexOf('id="reactor"'), html.indexOf("</div>", html.indexOf('id="reactor"')));
  assert.match(slot, /<iframe[^>]+id="reactor-face"/, "the slot is not a face frame");
  assert.match(slot, /src="faces\.html\?mode=display&amp;feed=parent"|src="faces\.html\?mode=display&feed=parent"/,
    "the frame does not load the project's own display-mode face");
  // The old mark's parts, none of which may survive as dead markup.
  for (const gone of ["reactor-halo", "reactor-ring", "reactor-vanes", "reactor-core", "core-glow"]) {
    assert.ok(!html.includes(gone), `the abstract mark's \`${gone}\` is still in the markup`);
  }
  // Decorative and unreachable, exactly as the mark was: the bar's own words
  // (the heading, the link strip) are what a screen reader is given.
  assert.match(slot, /aria-hidden="true"/, "the face frame is exposed to screen readers");
  assert.match(slot, /tabindex="-1"/, "the face frame is in the tab order");
});

await check("nothing in the stylesheet still addresses the removed shapes", async () => {
  const css = read("src/style.css");
  for (const gone of ["reactor-halo", "reactor-ring", "reactor-vanes", "reactor-core",
                      "reactor-knock", "halo-breathe", "core-pulse"]) {
    assert.ok(!css.includes(gone), `style.css still styles \`${gone}\`, which no longer exists`);
  }
});

await check("the face frame keeps the two things the mark's rules carried", async () => {
  const css = read("src/style.css");
  // "Caught it" - the contraction on release - and the speech envelope.
  assert.match(css, /\.reactor\.inhale #reactor-face/, "\"Caught it\" no longer reaches the frame");
  assert.match(css, /#reactor-face[^}]*--voice-scale/s, "the speech envelope no longer reaches the frame");
  assert.match(css, /#reactor-face[^}]*--voice-lift/s, "the brightness lift no longer reaches the frame");
  // The slot's size: 40 px in an 80 px bar (windows.rs QUICKBAR_BASE_HEIGHT).
  const size = css.match(/\.reactor\s*\{[^}]*width:\s*(\d+)px/s);
  assert.ok(size, "the slot has no width");
  assert.ok(Number(size[1]) >= 28 && Number(size[1]) <= 64,
    `the slot is ${size[1]}px, which is not a miniature in an 80px bar`);
});

/* ── The bar tells the face what to show ─────────────────────────────────── */

await check("the bar hands the face the same state every other surface gets", async () => {
  const main = read("src/main.js");
  assert.match(main, /import\s*\{[\s\S]*?\bfaceSignal\b[\s\S]*?\}\s*from\s*"\.\/jarvis-link\.js"/,
    "faceSignal is not imported - the bar would compose its own state");
  assert.match(main, /function paintBarFace\(link\)[\s\S]*?faceSignal\(link\)/,
    "paintBarFace does not use faceSignal");
  // The one function that already decides both of these for every surface.
  const src = read("src/jarvis-link.js");
  assert.match(src, /export function faceSignal/);
  assert.match(src, /offline/, "faceSignal no longer says whether Jarvis is reachable");
  // And it is actually called on a state change.
  assert.match(main, /onLink\(\(link\)\s*=>\s*\{[\s\S]{0,400}?paintBarFace\(link\)/,
    "the link's changes never reach the bar's face");
});

await check("the owner's chosen face reaches it, through a command the bar may already call", async () => {
  const main = read("src/main.js");
  assert.match(main, /invoke\("appearance_snapshot"\)/,
    "the bar never reads which face to wear - it would show the spec's default");
  // `get_appearance` would need a wider grant than the bar holds; the
  // read-only snapshot is the one its permission set already carries.
  assert.ok(!/invoke\("get_appearance"\)/.test(main),
    "the bar asks for get_appearance, which its capability does not allow");
  const caps = JSON.parse(read("src-tauri/capabilities/quickbar.json"));
  assert.ok(caps.permissions.includes("jarvis-link"), "the bar lost its jarvis-link set");
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  const link = sets.find((s) => /identifier = "jarvis-link"/.test(s));
  assert.match(link, /"allow-appearance-snapshot"/,
    "jarvis-link no longer allows appearance_snapshot - the bar's read would be refused");
});

/* ── The real frame, in a real browser ───────────────────────────────────── */

let K = null;
try { K = await import("./uikit.mjs"); } catch { K = null; }

if (!K) {
  console.log("skip  the browser half: Playwright is not installed (tests/README.md)");
} else {
  // A real origin, served from the app's own `src/`, because an
  // `about:blank` page has origin `null` and the face frame refuses both its
  // messages and its own `postMessage` target origin. The stub is the bar's
  // slot and nothing else: the frame it drives is the real one.
  const STUB = ".test-bar-face-stub.html";
  const stubPath = join(ROOT, "src", STUB);
  const { base, close } = await K.serve();
  writeFileSync(stubPath, `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>bar face stub</title>
<style>html,body{margin:0;padding:0;background:#0a1119;overflow:hidden}
.reactor{width:40px;height:40px;display:grid;place-items:center}
#reactor-face{width:100%;height:100%;border:0;background:transparent;pointer-events:none}</style>
</head><body>
<div class="reactor" id="reactor" aria-hidden="true">
  <iframe id="reactor-face" title="" tabindex="-1" aria-hidden="true"></iframe>
</div>
<script>
  window.__sent = [];
  window.__ready = false;
  const frame = document.getElementById("reactor-face");
  frame.src = "faces.html?mode=display&feed=parent";
  window.__send = (message) => {
    window.__sent.push(message);
    frame.contentWindow.postMessage(message, location.origin);
  };
  frame.addEventListener("load", () => setTimeout(() => { window.__ready = true; }, 2500));
</script>
</body></html>
`);
  const browser = await K.launch();
  const page = await browser.newPage({ viewport: { width: 300, height: 80 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${base}/${STUB}`);
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 40000 });

  /** What the frame itself was told and is showing. */
  const shown = () => page.evaluate(() => {
    const d = document.getElementById("reactor-face").contentDocument;
    const cv = d.getElementById("display-canvas");
    return {
      driven: d.documentElement.getAttribute("data-hud-face"),
      label: cv ? cv.getAttribute("aria-label") : null,
      offline: d.documentElement.getAttribute("data-face-offline"),
      face: d.defaultView.__faceSwitch ? d.defaultView.__faceSwitch.now().face : null,
      state: d.defaultView.__faceVoice ? d.defaultView.__faceVoice.lastState : null,
      css: cv ? cv.clientWidth : null,
    };
  });
  /** Exactly what main.js's paintBarFace posts. */
  const post = (state, extra = {}) => page.evaluate(({ state, extra }) => window.__send({
    type: "jarvis-hud-face", state, offline: false, focus: false, waiting: 0, serious: false, ...extra,
  }), { state, extra });

  await check("the frame is the app's real face renderer, and it draws", async () => {
    const s = await shown();
    assert.equal(s.driven, "ready", "the frame never marked itself as driven");
    assert.ok(s.css >= 28 && s.css <= 64, `the face is drawn at ${s.css} CSS px`);
    assert.ok(/^Jarvis (is|isn't)/.test(String(s.label)), `the picture has no spoken label: ${s.label}`);
    assert.equal(errors.length, 0, `the frame logged errors: ${errors.join(" | ")}`);
  });

  await check("each state the mark used to show still reaches the face", async () => {
    const seen = {};
    for (const state of ["idle", "listening", "thinking", "speaking", "approval", "error", "standby", "banked"]) {
      await post(state);
      await page.waitForTimeout(350);
      seen[state] = await shown();
    }
    // A state the frame has never heard of is ignored, not guessed at, and the
    // last one it did hear stands.
    await post("dancing");
    await page.waitForTimeout(250);
    seen.unknown = await shown();
    for (const state of ["listening", "thinking", "speaking", "approval", "error", "standby", "banked"]) {
      assert.equal(seen[state].state, state, `${state} never reached the face`);
    }
    assert.equal(seen.unknown.state, "banked", "an unknown state was passed through");
    assert.equal(seen.idle.label, "Jarvis is idle");
    assert.equal(seen.error.label, "Jarvis has a problem");
    assert.equal(seen.approval.label, "Jarvis is waiting for your decision");
  });

  await check("not connected shows the hollow ring, not an error and not a doze", async () => {
    await post("standby", { offline: true });
    await page.waitForTimeout(400);
    const s = await shown();
    assert.equal(s.offline, "true", "the frame was not told it is offline");
    assert.equal(s.label, "Jarvis isn't connected");
    // The ring is the app's own (drawOfflineRing); this proves the flag that
    // turns it on arrived, which is all the bar is responsible for.
    assert.equal(s.state, "standby");
    await post("idle");
    await page.waitForTimeout(300);
    assert.equal((await shown()).offline, "false", "the ring would stay on after reconnecting");
  });

  await check("the owner's chosen face arrives, and changing it changes the picture", async () => {
    const before = (await shown()).face;
    await page.evaluate(() => window.__send({
      type: "jarvis-hud-face", appearance: { face: "pygmyowl", bindings: {} },
    }));
    await page.waitForTimeout(1400);
    const after = await shown();
    assert.notEqual(after.face, before, "the frame kept the spec's default face");
    assert.equal(after.face, "pygmyowl", `the frame wears ${after.face}`);
    assert.equal(errors.length, 0, `switching face logged errors: ${errors.join(" | ")}`);
  });

  await browser.close();
  close();
  // The stub is this suite's own, and only while it runs: nothing under
  // src/ is left behind for a packaging step to pick up.
  rmSync(stubPath, { force: true });
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe bar's face: one renderer, the owner's choice, and every honest state");
process.exit(fails.length ? 1 : 0);
