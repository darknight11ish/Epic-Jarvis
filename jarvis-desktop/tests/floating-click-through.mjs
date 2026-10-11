/**
 * floating-click-through.mjs - "clicks pass through the floating face to
 * whatever is behind it, except on the animal" (2026-10-10, the integration
 * evaluation: docs/INTEGRATION-EVAL-2026-10-10.md, borrowing the idea from
 * AI-Desktop-Pet and no code from it).
 *
 *     node tests/floating-click-through.mjs
 *
 * The owner asked for this off by default, as a setting, applied at once;
 * and for the animal never to become unclickable. Those three are what this
 * file holds to, plus the one hard thing in the feature: where "the animal"
 * actually is.
 *
 * HOW THE HIT TEST WORKS, and why these checks are shaped the way they are:
 *
 *   * Rust owns the switch. Tauri 2.11.6 has exactly one way to make a window
 *     transparent to the pointer - `set_ignore_cursor_events` - and it is
 *     all-or-nothing. So windows.rs watches the pointer and flips it.
 *   * The PAGE owns the geometry. `floating.js` measures its own drawn
 *     picture into a 32x32 grid and sends it back on `floating-hit-mask`.
 *     Measuring was not the first choice: a circle worked out from the
 *     shader's camera was, and it cannot work - measured with the real
 *     shader at the floating window's own framing, all five faces reach the
 *     edge of their square in some pose (see windows.rs's own note).
 *   * Every doubt is "the animal keeps the click". No grid yet, a pointer
 *     that cannot be read, a payload that is not exactly one grid - all of
 *     them leave the window taking every click.
 *
 * The browser half runs the REAL floating.html and reads the REAL grid it
 * sends. Without Playwright the browser-free half still runs (tests/README.md:
 * several suites do this); CI's frontend job has Playwright, so there it all
 * runs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const RUST = read("src-tauri/src/windows.rs");
const COMMANDS = read("src-tauri/src/commands.rs");
const LIB = read("src-tauri/src/lib.rs");
const CAPABILITY = JSON.parse(read("src-tauri/capabilities/floating.json"));
const PAGE = read("src/floating.js");
const SETTINGS = read("src/settings.js");
const HTML = read("src/settings.html");
const FIX = JSON.parse(read("tests/fixtures/settings-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── The setting, and where it is declared ───────────────────────────────── */

await check("the switch is declared in the one settings table, not written into the page by hand", async () => {
  const row = FIX.rows.find((r) => r.id === "floating-click-through");
  assert.ok(row, "no `floating-click-through` row in the generated contract");
  assert.equal(row.owner, "desktop", "the phone has no floating window to pass clicks through");
  assert.equal(row.section, "appearance-card", "it belongs with the floating face's own row");
  assert.equal(row.order, 3, "directly under 'Floating face'");
  assert.equal(row.setting, null, "a cosmetic switch: no spoken 'adjust' to dispatch");
  assert.equal(row.checked, false, "OFF by default - the owner's call");
  assert.equal(row.fallback, false, "its words are the page's own, not sent by the PC");
  assert.equal(row.detail_span, "floating-click-through-detail");
  // ...and the page really carries it, with the row before it still there.
  const ids = [...HTML.matchAll(/<input id="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(ids[ids.indexOf("floating-click-through") - 1], "floating-enabled",
    "it must sit under the floating face's own switch");
  assert.match(HTML, /id="floating-click-through-label"/, "the row's words are reachable by id");
});

await check("neither box asks for an approval card, and both go through ONE command", async () => {
  // A cosmetic switch applies at once (the house rule): nothing here may
  // reach for a card, a gate or Windows Hello. Comments are stripped first -
  // this very check's own note in settings.js says "approval card".
  const at = SETTINGS.indexOf('const floatingEnabled');
  const block = SETTINGS.slice(at, SETTINGS.indexOf("open-faces", at))
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/\/\/[^\n]*/g, " ");
  assert.ok(block.includes('$("floating-click-through")'), "the new box is wired up");
  assert.match(block, /invoke\("set_floating",\s*\{[\s\S]*?enabled: next\.enabled,[\s\S]*?clickThrough: next\.clickThrough,/,
    "ONE call carries both halves, or changing one box would reset the other");
  assert.doesNotMatch(block, /decide_approval|approval|windows_hello|reveal_/, "no card, no gate");
  // Both boxes send both halves, so the command can be a plain setter.
  assert.equal((block.match(/setFloating\(/g) || []).length, 3,
    "two change handlers plus the declaration");
});

/* ── Rust: the call, and the fail-safe direction ─────────────────────────── */

await check("it uses the one call Tauri 2.11.6 actually has, and says so", async () => {
  assert.match(RUST, /`WebviewWindow::set_ignore_cursor_events\(bool\)`/,
    "the comment has to name the call it used, because this is the whole "
    + "reason the hit test lives here rather than in Tauri");
  // Exactly ONE call site: two would mean two places deciding.
  assert.equal((RUST.match(/\.set_ignore_cursor_events\(/g) || []).length, 1,
    "the window's own all-or-nothing click-through, called from one place");
  assert.match(RUST, /window\.cursor_position\(\)/, "the pointer's own screen position");
  assert.match(RUST, /window\.inner_position\(\)/);
  assert.match(RUST, /window\.inner_size\(\)/);
});

await check("every doubt leaves the animal clickable", async () => {
  // The pointer/grid lookup is Option: None must mean "let the window have
  // the click", never "pass it on".
  assert.match(RUST, /pointer_over_face\(&window, &handle\)[\s\S]{0,80}?\.map\(\|over\| !over\)[\s\S]{0,40}?\.unwrap_or\(false\)/,
    "an unreadable pointer or a missing grid must come out as `do not ignore`");
  assert.match(RUST, /let mask = app\.state::<FloatingState>\(\)\.hit_mask\(\)\?;/,
    "no grid yet is not an answer");
  assert.match(RUST, /if !\(0\.0\.\.1\.0\)\.contains\(&fx\)[\s\S]{0,600}?return Some\(false\);/,
    "off the window is a miss, decided from the real pointer position");
  // A grid that is not exactly one grid is no grid at all.
  assert.match(RUST, /grid\.len\(\) == FLOATING_HIT_GRID \* FLOATING_HIT_GRID/);
  assert.match(RUST, /fn parse_hit_mask\(grid: &str\) -> Option<Vec<bool>>/);
});

await check("the window is never made click-through before a grid has arrived", async () => {
  // `set_floating` must NOT flip the window itself: only the watcher knows
  // where the animal is, and until it does the window keeps every click.
  const at = COMMANDS.indexOf("pub async fn set_floating");
  const body = COMMANDS.slice(at, COMMANDS.indexOf("\n}\n", at));
  assert.doesNotMatch(body, /set_ignore_cursor_events/,
    "the command would be guessing at the animal's shape");
  assert.match(body, /click_through: Option<bool>/, "an optional second half, so old callers still work");
  assert.match(body, /prefs\.click_through = click_through/);
});

await check("the grid travels on a granted command, and only the floating window may send it", async () => {
  // NOT an event, and that is the security suite's doing: apps security audit
  // M1 forbids `core:event:allow-emit` to every window, because the quickbar
  // trusts what it hears (`tests/security.mjs` guards it).
  assert.match(PAGE, /invoke\("note_floating_hit_mask", \{ grid: measureHitGrid\(\) \}\)/,
    "the page tells Rust where its picture is drawn");
  assert.match(COMMANDS, /pub fn note_floating_hit_mask\(app: AppHandle, grid: String\)/,
    "the command exists");
  assert.match(COMMANDS, /windows::note_floating_hit_mask\(&app, &grid\)/);
  assert.match(read("src-tauri/build.rs"), /"note_floating_hit_mask",/,
    "a command missing from build.rs's export list has no permission at all");
  assert.match(read("src-tauri/permissions/surfaces.toml"),
    /identifier = "floating-hit-mask"[\s\S]{0,200}?permissions = \["allow-note-floating-hit-mask"\]/,
    "the set the capability grants by name");
  assert.ok(CAPABILITY.permissions.includes("floating-hit-mask"), "granted to this window");
  assert.ok(CAPABILITY.permissions.includes("core:event:allow-listen"),
    "the window still has to hear its own state");
  for (const other of ["settings.json", "quickbar.json", "widget.json", "faces.json", "brain.json"]) {
    const caps = read(`src-tauri/capabilities/${other}`);
    assert.doesNotMatch(caps, /allow-emit|floating-hit-mask/,
      `${other} must not gain either way of talking to Rust`);
  }
});

/* ── The page half, in a real browser ───────────────────────────────────── */

let K = null;
try { K = await import("./uikit.mjs"); } catch { K = null; }
if (!K) {
  console.log("skip  the page checks: Playwright is not installed (tests/README.md)");
} else {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const page = await K.open(browser, base, "floating.html", {}, { width: 200, height: 200 });
  // The harness records every command a page invokes in `window.__calls`, as
  // `[command, args]`. Nothing to patch: the grid has to arrive on the real
  // call, the way the real window makes it.
  let got = null;
  await K.until(page, "the floating face to report where its picture is drawn", async () => {
    got = await page.evaluate(() =>
      (window.__calls || []).filter((c) => c[0] === "note_floating_hit_mask").pop() || null);
    return Boolean(got);
  }, { ms: 15000 }).catch((e) => { console.log(`      (${e.message})`); });

  await check("the real page sends a 32x32 grid of its own picture", async () => {
    assert.ok(got, "nothing was sent - the grid never reaches Rust, so nothing passes through");
    const grid = got[1] && got[1].grid;
    assert.equal(typeof grid, "string", "the command takes `{ grid }`");
    assert.equal(grid.length, 32 * 32, `the grid is 32x32 cells, got ${grid && grid.length}`);
    assert.match(grid, /^[01]+$/, "one character per cell: 1 drawn, 0 background");
    const ones = [...grid].filter((c) => c === "1").length;
    assert.ok(ones > 0, "no cell is drawn - every click would pass through the animal");
    assert.ok(ones < grid.length,
      "every cell is drawn - the window would still swallow every click, so the setting would do nothing");
    // The middle of a 200x200 face window always has the face on it...
    assert.equal(grid[16 * 32 + 16], "1", "the face is not where the middle of the window is");
  });

  await check("what passes through is the background, not the animal", async () => {
    // Read the frame's own canvas and check the grid against the PICTURE,
    // rather than against the code that made it.
    const seen = await page.evaluate(() => {
      const f = document.getElementById("face-frame");
      const cv = f && f.contentDocument && f.contentDocument.getElementById("display-canvas");
      if (!cv) return { noCanvas: true };
      const g = cv.getContext("2d", { willReadFrequently: true });
      const at = (fx, fy) => {
        const d = g.getImageData(Math.floor(fx * cv.width), Math.floor(fy * cv.height), 1, 1).data;
        return [d[0], d[1], d[2]];
      };
      return { corner: at(0.01, 0.01), centre: at(0.5, 0.5), size: [cv.width, cv.height] };
    });
    assert.ok(!seen.noCanvas, "the face frame never drew anything");
    const grid = got && got[1] && got[1].grid;
    assert.ok(grid, "no grid to check");
    // The default face is a dark background with a ring on it: its top-left
    // pixel is the background the grid calibrates against, so the four corner
    // CELLS must be background too - that is the area the setting opens up.
    for (const [name, i] of [["top-left", 0], ["top-right", 31],
      ["bottom-left", 31 * 32], ["bottom-right", 32 * 32 - 1]]) {
      assert.equal(grid[i], "0", `the ${name} corner is marked as the face, so nothing would pass through there`);
    }
    // ...and the middle is genuinely not the background.
    const { corner, centre } = seen;
    assert.notDeepEqual(centre, corner, "the middle of the picture is the flat background");
  });

  await check("the floating window paints no background of its own - and the Widget and the HUD still do", async () => {
    // 2026-10-11, the measured gap this closes: the click-through worked, but
    // the window was still a visible dark square - its page painted the face's
    // background edge to edge (`#04070c`, alpha 255 at the corner). A
    // transparent WINDOW needs a page that paints nothing behind the face.
    //
    // The scoping is the whole point of this check. The eleven webviews share
    // these files, and the Widget's round tray and the HUD embed the SAME
    // faces.html: only `floating.html` asks for the clear background
    // (`&clear=1`), so only its frame may come out see-through. A change that
    // made the others transparent would be a worse bug than the one fixed.
    //
    // Real pixels, not computed styles: a screenshot with the page's own
    // background left out, decoded and read back, is what the owner sees.
    const cornerOf = async (file) => {
      const p = await K.open(browser, base, file, {}, { width: 200, height: 200 });
      await K.until(p, `the face in ${file} to draw`, async () => p.evaluate(() => {
        const f = document.getElementById("face-frame");
        const cv = (f && f.contentDocument ? f.contentDocument : document)
          .getElementById("display-canvas");
        return Boolean(cv && cv.width);
      }), { ms: 15000 }).catch(() => {});
      const png = await p.screenshot({ omitBackground: true });
      const probe = await browser.newPage();
      const at = await probe.evaluate(async (b64) => {
        const img = new Image();
        img.src = "data:image/png;base64," + b64;
        await img.decode();
        const c = document.createElement("canvas");
        c.width = img.width; c.height = img.height;
        const g = c.getContext("2d", { willReadFrequently: true });
        g.drawImage(img, 0, 0);
        const d = g.getImageData(0, 0, 1, 1).data;
        return [d[0], d[1], d[2], d[3]];
      }, png.toString("base64"));
      await probe.close();
      await p.close();
      return at;
    };
    const floating = await cornerOf("floating.html");
    assert.equal(floating[3], 0, `the floating window's own corner is still painted: rgba(${floating})`);
    for (const [who, file] of [
      ["the Widget's round tray", "faces.html?mode=display&feed=parent&clip=circle"],
      ["the HUD's face", "faces.html?mode=display&feed=parent"],
    ]) {
      const opaque = await cornerOf(file);
      assert.equal(opaque[3], 255,
        `${who} lost its background: rgba(${opaque}) - the clear background leaked out of the floating window`);
    }
  });

  await browser.close();
  close();
}

console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe floating face passes clicks through everywhere but the animal");
process.exit(fails.length ? 1 : 0);
