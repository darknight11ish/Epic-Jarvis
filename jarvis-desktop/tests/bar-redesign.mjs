/**
 * The bar's redesign (2026-10-20): the real rendering of it, not the work
 * order's screenshot claims.
 *
 *   node tests/bar-redesign.mjs
 *
 * WHY THIS EXISTS. The work order says the bar's far-left mark is an
 * "orb canvas" with a solid #000000 background. It is not: there is no
 * `.orb` / `#bar-orb` / avatar element anywhere on the page - the slot is
 * `#reactor` holding the project's own `faces.html?mode=display` frame (the
 * same one the widget, the floating face and the HUD embed), and the dark
 * square the owner saw is that frame's own opaque canvas, clipped square
 * inside the rounded pill. The fix is a circular clip on the container, and
 * this suite pins it so a later "restyle" cannot quietly un-clip it. It also
 * pins the rest of the redesign where it is a real, checkable property:
 *
 *   - the face slot is circular and clips; the frame stays the same square;
 *   - the mini-core's glow is driven by the bar's ONE state source
 *     (html[data-state] / html[data-voice]), not by a second one;
 *   - the five mode controls are labelled with one visible word each, and
 *     their ids/aria meanings are unchanged;
 *   - the preset chip and the lane badge are one compound control made of
 *     BOTH original nodes, joined only while the preset half is really there;
 *   - the window utilities are one group, close last, with the Esc badge;
 *   - the submit keycap sits on the input row and Enter still submits.
 *
 * NOT here, because it needs a real desktop window: how it looks over the
 * owner's wallpaper, and the real WebView2's painting. The shapes below are
 * measured in the same shipped page and stylesheet the app loads.
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const open = (data = {}, viewport = { width: 750, height: 84 }) =>
  K.open(browser, base, "index.html", data, viewport);

/* ── The slot that actually holds the face ──────────────────────────────── */

await check("the bar's mark is #reactor holding the real face frame, not an orb", async () => {
  const page = await open();
  const got = await page.evaluate(() => ({
    reactor: Boolean(document.querySelector(".reactor#reactor")),
    frame: Boolean(document.querySelector("#reactor .reactor#reactor #reactor-face")) ||
           Boolean(document.querySelector("#reactor-face")),
    frameSrc: document.querySelector("#reactor-face")?.getAttribute("src") || "",
    orbLike: [...document.querySelectorAll("*")].filter((el) =>
      /(^|[\s-])orb([\s-]|$)|avatar|mini-core/i.test(`${el.id} ${el.className}`)).length,
  }));
  await page.close();
  assert.equal(got.reactor, true, "the bar lost #reactor");
  assert.equal(got.frame, true, "the face frame is gone from the slot");
  assert.match(got.frameSrc, /faces\.html\?mode=display/, "the slot no longer embeds the project's face");
  assert.equal(got.orbLike, 0,
    "an orb/avatar element appeared - the real slot is #reactor, and a second drawing would drift from the face every other surface shows");
});

await check("the face slot is clipped to a circle, and the frame is still square", async () => {
  const page = await open();
  const got = await page.evaluate(() => {
    const r = document.querySelector("#reactor");
    const f = document.querySelector("#reactor-face");
    const cs = getComputedStyle(r);
    const b = r.getBoundingClientRect();
    const fb = f.getBoundingClientRect();
    return { radius: cs.borderRadius, overflow: cs.overflow,
             w: Math.round(b.width), h: Math.round(b.height),
             fw: Math.round(fb.width), fh: Math.round(fb.height) };
  });
  await page.close();
  /* The black square was a SQUARE opaque canvas inside a rounded pill: the
     clip is the fix. A later rule that drops overflow or the radius brings
     the hard corners back, and nothing else would notice. */
  assert.equal(got.radius, "50%", `the slot is ${got.radius}, not a circle`);
  assert.equal(got.overflow, "hidden", "the circle no longer clips its frame");
  assert.equal(got.w, 40, `the slot is ${got.w}px wide, not the 40px miniature`);
  assert.equal(got.h, got.w, "the slot is no longer square");
  assert.equal(got.fw, got.w, "the frame no longer fills its slot");
  assert.equal(got.fh, got.fw, "the frame is being squeezed inside the slot");
});

await check("the mini-core glow follows the bar's one state source", async () => {
  const page = await open();
  const core = () => page.evaluate(() => {
    const r = document.querySelector("#reactor");
    const cs = getComputedStyle(r);
    return { glow: cs.getPropertyValue("--core-glow").trim(), shadow: cs.boxShadow };
  });
  const idle = await core();
  await page.evaluate(() => { document.documentElement.dataset.voice = "listening"; });
  await page.waitForTimeout(320);
  const listening = await core();
  await page.evaluate(() => { document.documentElement.dataset.voice = ""; document.documentElement.dataset.state = "approval"; });
  await page.waitForTimeout(320);
  const approval = await core();
  await page.close();
  assert.ok(idle.glow, "the mini-core has no glow colour at rest");
  assert.notEqual(listening.glow, idle.glow,
    "listening did not reach the mini-core - it would keep the idle colour while the microphone is live");
  assert.notEqual(approval.glow, listening.glow,
    "waiting for the owner's decision did not reach the mini-core");
  assert.notEqual(approval.shadow, idle.shadow, "the glow's spread/strength never changes with the state");
});

/* ── The labelled modes ─────────────────────────────────────────────────── */

await check("each primary mode is one icon plus one visible word", async () => {
  const page = await open();
  const rows = await page.evaluate(() => {
    const strip = document.querySelector(".mode-strip");
    if (!strip) return null;
    return [...strip.querySelectorAll(":scope > button")].map((b) => {
      const label = b.querySelector(".chip-label");
      const svg = b.querySelector("svg");
      return {
        id: b.id,
        word: label ? label.textContent.trim() : "",
        labelledForTheEyeOnly: label ? label.getAttribute("aria-hidden") : null,
        icon: svg ? Math.round(svg.getBoundingClientRect().width) : 0,
        aria: b.getAttribute("aria-label") || "",
      };
    });
  });
  await page.close();
  assert.ok(rows, "there is no .mode-strip holding the modes");
  const want = [
    ["mic", "Voice"],
    ["voice-auto", "Auto"],
    ["jarvis-live-toggle", "Live"],
    ["watch-toggle", "Watch"],
    ["temporary", "Temp"],
  ];
  for (const [id, word] of want) {
    const row = rows.find((r) => r.id === id);
    assert.ok(row, `#${id} left the mode row`);
    assert.equal(row.word, word, `#${id}'s visible word is "${row.word}", not "${word}"`);
    assert.equal(row.labelledForTheEyeOnly, "true",
      `#${id}'s new label is not aria-hidden - it would become part of the button's accessible name`);
    assert.ok(row.icon >= 14 && row.icon <= 18, `#${id}'s icon is ${row.icon}px, not a 16px glyph`);
  }
  assert.equal(rows.some((r) => /screen/i.test(r.word)), false,
    "a Screen control appeared in the bar: \"Look at this\" is a KEY on purpose - a button here would cover the screen it is about to look at");
});

await check("the mode ids and their names are the ones the suites know", async () => {
  const page = await open();
  const got = await page.evaluate(() => ({
    liveAria: document.querySelector("#jarvis-live-toggle").getAttribute("aria-label"),
    watchAria: document.querySelector("#watch-toggle").getAttribute("aria-label"),
    micName: document.querySelector("#mic-label")?.textContent || "",
    tempName: document.querySelector("#temporary .sr-only")?.textContent || "",
    voicePressed: document.querySelector("#voice-auto").getAttribute("aria-pressed"),
  }));
  await page.close();
  assert.equal(got.liveAria, "Jarvis Live");
  assert.equal(got.watchAria, "Watch with me");
  assert.match(got.micName, /Hold to talk to Jarvis/);
  assert.equal(got.tempName, "Incognito");
  assert.equal(got.voicePressed, "false");
});

/* ── The compound model + lane pill ─────────────────────────────────────── */

await check("the compound pill is both original nodes, joined only when a preset exists", async () => {
  const page = await open();
  const joined = () => page.evaluate(() => {
    const pill = document.querySelector(".model-pill");
    const chip = document.querySelector("#preset-chip");
    const route = document.querySelector("#route");
    const sep = document.querySelector(".model-pill-sep");
    const cs = getComputedStyle(chip);
    const rs = getComputedStyle(route);
    return {
      inside: Boolean(pill && chip && route && pill.contains(chip) && pill.contains(route)),
      sepDisplay: sep ? getComputedStyle(sep).display : "MISSING",
      chipHidden: chip.hidden,
      chipInner: [cs.borderTopRightRadius, cs.borderBottomRightRadius],
      chipOuter: [cs.borderTopLeftRadius, cs.borderBottomLeftRadius],
      routeInner: [rs.borderTopLeftRadius, rs.borderBottomLeftRadius],
      routeOuter: [rs.borderTopRightRadius, rs.borderBottomRightRadius],
      oneRow: chip.hidden || !route.offsetParent ? null :
        Math.abs(chip.getBoundingClientRect().y - route.getBoundingClientRect().y) < 2,
    };
  });
  const hidden = await joined();
  /* The PC has not named a preset in this stub: the chip is hidden and the
     pill must be the lane badge alone, exactly as the bar looked before. */
  assert.equal(hidden.inside, true, "the preset chip and lane badge are no longer one compound control");
  assert.equal(hidden.chipHidden, true, "the bar is asserting a preset with no reading");
  assert.equal(hidden.sepDisplay, "none", "the hairline is drawn between one half and nothing");
  assert.deepEqual(hidden.routeInner, ["999px", "999px"],
    "with no preset half, the lane badge is not a whole rounded pill");

  /* The state the PC really sends when it HAS named one: focus-presets-bar.js
     unhides the chip and writes its label. Both halves must then read as one
     joined control - the chip's name and behaviour are still its own. */
  await page.evaluate(() => {
    const chip = document.getElementById("preset-chip");
    chip.hidden = false;
    document.getElementById("preset-chip-label").textContent = "Deep Work";
  });
  await page.waitForTimeout(120);
  const shown = await joined();
  await page.close();
  assert.equal(shown.sepDisplay, "block", "the hairline never appears between the two halves");
  assert.equal(shown.oneRow, true, "the two halves are not on one row");
  assert.deepEqual(shown.chipInner, ["0px", "0px"],
    `the preset half's inner corners are ${shown.chipInner} - not joined`);
  assert.deepEqual(shown.chipOuter, ["999px", "999px"], "the preset half's outer edge is not rounded");
  assert.deepEqual(shown.routeInner, ["0px", "0px"],
    `the lane half's inner corners are ${shown.routeInner} - not joined`);
  assert.deepEqual(shown.routeOuter, ["999px", "999px"], "the lane half's outer edge is not rounded");
});

/* ── The utility cluster ────────────────────────────────────────────────── */

await check("the window utilities are one group, close last, with the Esc badge", async () => {
  const page = await open();
  const got = await page.evaluate(() => {
    const group = document.querySelector(".utility-cluster");
    if (!group) return null;
    const ids = [...group.querySelectorAll(":scope > button")].map((b) => b.id);
    const badge = group.querySelector(".key-badge");
    return {
      role: group.getAttribute("role"),
      label: group.getAttribute("aria-label"),
      ids,
      last: ids[ids.length - 1],
      badge: badge ? { text: badge.textContent.trim(), hidden: badge.getAttribute("aria-hidden") } : null,
    };
  });
  await page.close();
  assert.ok(got, "the bar has no utility cluster");
  assert.equal(got.role, "group");
  assert.ok(got.label, "the cluster has no name for a screen reader");
  assert.deepEqual(got.ids, ["sayable-toggle", "pin", "open-settings", "hide-bar"]);
  assert.equal(got.last, "hide-bar", "the close is no longer the last control (it already was at the right end, not mid-bar)");
  assert.deepEqual(got.badge, { text: "Esc", hidden: "true" },
    "the bar's one documented shortcut (Esc hides it) is not shown beside the close");
});

/* ── The submit keycap ──────────────────────────────────────────────────── */

await check("the submit keycap sits on the input row and Enter still submits", async () => {
  const page = await open();
  const place = await page.evaluate(() => {
    const k = document.querySelector("#submit-hint");
    const field = document.querySelector("#prompt-field");
    return {
      parent: k ? k.parentElement.id : "MISSING",
      sameRow: k && field
        ? Math.abs(k.getBoundingClientRect().y - field.getBoundingClientRect().y) < 12
        : false,
      title: k ? k.getAttribute("title") : "",
      border: k ? getComputedStyle(k).borderTopColor : "",
      tag: k ? k.tagName.toLowerCase() : "",
    };
  });
  assert.equal(place.parent, "bar", "the keycap is not on the input row");
  assert.equal(place.sameRow, true, "the keycap is not level with the input");
  assert.equal(place.tag, "kbd");
  assert.match(place.title, /Enter/, "the keycap does not say which key it is");
  assert.notEqual(place.border, "rgba(0, 0, 0, 0)",
    "the keycap lost its accent edge and no longer reads as the primary action");

  await page.locator("#prompt").fill("what is 2 + 2");
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(300);
  const after = await page.locator("#prompt").inputValue();
  await page.close();
  assert.equal(after, "", "Enter no longer submits - moving the keycap changed the one submit path");
});

/* ── The shell/stack guardrail, and all three themes ────────────────────── */

await check("the bar is still 80px tall with its two rows, under the 720px shell clamp", async () => {
  const page = await open();
  const got = await page.evaluate(() => {
    const bar = document.getElementById("bar").getBoundingClientRect();
    const shell = getComputedStyle(document.getElementById("shell"));
    return { barH: Math.round(bar.height), maxH: shell.maxHeight,
             stack: Boolean(document.getElementById("stack")),
             zones: [...document.querySelector(".bar-meta").children]
               .map((el) => el.className.split(" ")[0]) };
  });
  await page.close();
  assert.equal(got.barH, 80, `the bar is ${got.barH}px tall - the window's 80px row moved`);
  assert.equal(got.maxH, "720px", "the shell clamp the Rust side enforces moved");
  assert.equal(got.stack, true, "#stack is gone - answer cards would have nowhere to go");
  assert.deepEqual(got.zones, ["model-pill", "mode-strip", "utility-cluster"],
    "the bar's second row is not the three zones the redesign is");
});

for (const theme of ["deep-space", "paper", "high-contrast"]) {
  await check(`the redesign survives the ${theme} theme`, async () => {
    const page = await open({ theme });
    const got = await page.evaluate(() => {
      const r = getComputedStyle(document.querySelector("#reactor"));
      const shell = getComputedStyle(document.getElementById("shell"));
      return { radius: r.borderRadius, overflow: r.overflow,
               shellBg: shell.backgroundColor, barH: Math.round(document.getElementById("bar").getBoundingClientRect().height) };
    });
    await page.close();
    assert.equal(got.radius, "50%");
    assert.equal(got.overflow, "hidden");
    assert.notEqual(got.shellBg, "rgba(0, 0, 0, 0)", `${theme}: the shell has no surface at all`);
    assert.equal(got.barH, 80, `${theme}: the bar changed height`);
  });
}

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe bar's redesign holds: circular core, one state colour, labelled modes, compound pill, utility cluster");
process.exit(fails.length ? 1 : 0);
