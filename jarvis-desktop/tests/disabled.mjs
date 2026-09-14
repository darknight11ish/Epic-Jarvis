/**
 * Disabled controls, measured rather than assumed.
 *
 * WCAG exempts a disabled control from its contrast minimum. That exemption is
 * how four stylesheets ended up at 0.45-0.6 opacity: permitted, and unreadable.
 * A reader who cannot tell what the greyed-out button *would* have done cannot
 * tell why it is greyed out either.
 *
 * So: composite each disabled control's real computed colour, at its real
 * opacity, over what is actually behind it, in every theme, and require 3:1.
 * That is the large-text minimum, deliberately: these are not controls anyone
 * has to read for long, but they do have to be readable at all.
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

const THEMES = ["deep-space", "ember", "paper", "high-contrast"];

/**
 * In the page: disable a control, then read what it actually renders as.
 *
 * Opacity and `filter: saturate()` are composition, not colour — `getComputedStyle`
 * reports the colour BEFORE either is applied, so both have to be re-applied
 * here or the measurement is of a control that is not on screen.
 */
const MEASURE = (selector) => {
  const el = document.querySelector(selector);
  if (!el) return null;
  const cs = getComputedStyle(el);

  const parse = (value) => {
    const n = value.match(/[\d.]+/g);
    if (!n) return null;
    return { r: +n[0], g: +n[1], b: +n[2], a: n[3] === undefined ? 1 : +n[3] };
  };

  // What is behind it: the first ancestor with a non-transparent background,
  // and failing that the window's own ground.
  let behind = { r: 0, g: 0, b: 0, a: 1 };
  for (let node = el; node; node = node.parentElement) {
    const bg = parse(getComputedStyle(node).backgroundColor);
    if (bg && bg.a > 0.9) { behind = bg; break; }
  }

  const fg = parse(cs.color);
  const fill = parse(cs.backgroundColor);
  const opacity = Number(cs.opacity) || 1;
  const sat = Number((cs.filter.match(/saturate\(([\d.]+)\)/) || [])[1] ?? 1);

  return { fg, fill, behind, opacity, sat, text: el.textContent.trim() };
};

/** sRGB relative luminance. */
const luma = (c) => {
  const ch = (v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b);
};
const ratio = (x, y) => {
  const [a, b] = [luma(x), luma(y)].sort((p, q) => q - p);
  return (a + 0.05) / (b + 0.05);
};
/** The `saturate()` filter, as the sRGB matrix browsers actually use. */
const saturate = (c, s) => {
  const m = (r0, g0, b0) => Math.max(0, Math.min(255, r0 * c.r + g0 * c.g + b0 * c.b));
  return {
    r: m(0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s),
    g: m(0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s),
    b: m(0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s),
    a: c.a,
  };
};
const over = (fg, bg) => ({
  r: fg.r * fg.a + bg.r * (1 - fg.a),
  g: fg.g * fg.a + bg.g * (1 - fg.a),
  b: fg.b * fg.a + bg.b * (1 - fg.a),
  a: 1,
});

/** What the reader sees: the label against whatever is immediately under it. */
function measured(m) {
  const s = m.sat;
  // The element is composited as a group: fill over the page, then the label
  // over the fill, then the whole thing at `opacity` over the page again.
  const ground = m.behind;
  const fill = m.fill.a > 0 ? over(saturate(m.fill, s), ground) : ground;
  const label = over(saturate(m.fg, s), fill);
  const flat = (c) => over({ ...c, a: m.opacity }, ground);
  return ratio(flat(label), flat(fill));
}

const CASES = [
  ["index.html", "#approval-approve", { pending: [K.APPROVAL_RAISED] }, undefined],
  ["index.html", "#approval-deny", { pending: [K.APPROVAL_RAISED] }, undefined],
  ["widget.html", "#btn-appr-yes", { pending: [K.APPROVAL_PLAIN] }, { width: 320, height: 460 }],
  ["widget.html", "#btn-appr-no", { pending: [K.APPROVAL_PLAIN] }, { width: 320, height: 460 }],
  ["brain.html", ".btn", {}, { width: 1180, height: 780 }],
];

for (const theme of THEMES) {
  for (const [file, selector, data, viewport] of CASES) {
    await check(`${theme}: ${file} ${selector} is still readable when disabled`, async () => {
      const page = await K.open(browser, base, file, { ...data, theme }, viewport);
      // Disable, THEN wait. These buttons transition background, colour and
      // border over 140ms, and `getComputedStyle` during a transition returns
      // the animated value — which at t=0 is the colour the button had while
      // it was still live. Measuring in the same tick measures the old button
      // and reports that nothing changed.
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (el) el.disabled = true;
      }, selector);
      await page.waitForTimeout(300);
      const m = await page.evaluate(MEASURE, selector);
      await page.close();
      if (!m) return; // the control is not on this surface in this scenario
      const r = measured(m);
      assert.ok(r >= 3, `"${m.text}" measures ${r.toFixed(2)}:1 when disabled, under 3:1`);
    });
  }
}

/* ── Control: disabled must still LOOK disabled ──────────────────────────── */

await check("CONTROL: a disabled control is still visibly inert", async () => {
  // Readable and inert are two requirements, and the fix for the first can
  // quietly break the second: a disabled button that renders exactly like a
  // live one is worse than an unreadable one.
  for (const [file, selector, data, viewport] of [
    ["index.html", "#approval-approve", { pending: [K.APPROVAL_RAISED] }, undefined],
    ["widget.html", "#btn-appr-yes", { pending: [K.APPROVAL_PLAIN] }, { width: 320, height: 460 }],
  ]) {
    const page = await K.open(browser, base, file, data, viewport);
    const read = (sel) => {
      const cs = getComputedStyle(document.querySelector(sel));
      return `${cs.backgroundColor}|${cs.color}|${cs.borderTopColor}|${cs.opacity}`;
    };
    const live = await page.evaluate(read, selector);
    await page.evaluate((sel) => {
      document.querySelector(sel).disabled = true;
    }, selector);
    // Same reason as above: the change is transitioned, so it is not on screen
    // in the tick that sets it.
    await page.waitForTimeout(300);
    const dead = await page.evaluate(read, selector);
    const seen = { live, dead };
    await page.close();
    assert.notEqual(seen.dead, seen.live,
      `${file} ${selector}: disabled and enabled render identically`);
  }
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nevery disabled control is still readable");
process.exit(fails.length ? 1 : 0);
