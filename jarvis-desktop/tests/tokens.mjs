/**
 * The token contract, checked in a real engine rather than by reading the CSS.
 *
 * Seventy-five literal colours were replaced with `rgb(var(--hue-rgb) / a)`.
 * That form is worth a test of its own for two reasons:
 *
 *   1. If the browser does not accept it, the declaration becomes `unset` and
 *      the element renders with NO background rather than with a wrong one —
 *      a failure that looks like a missing element, not like a colour bug.
 *   2. If a hue triple is wrong by a digit, every surface using it shifts and
 *      nothing else notices, because the contrast tests measure tokens and
 *      these are alpha-tinted derivatives of tokens.
 *
 * So: resolve the form in the page, and check it against the value the old
 * literal had, on the theme those literals were written for.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", "src", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The hues as `deep-space` had them, before the migration. */
const WAS = {
  "--accent-rgb": [56, 240, 255],
  "--ok-rgb": [61, 220, 151],
  "--warn-rgb": [255, 200, 96],
  "--bad-rgb": [255, 107, 122],
  "--info-rgb": [185, 139, 255],
  "--muted-rgb": [139, 148, 163],
  "--sheen-rgb": [255, 255, 255],
  "--shade-rgb": [0, 0, 0],
};

await check("every raw channel still holds the colour it replaced", async () => {
  const page = await K.open(browser, base, "index.html", {});
  const got = await page.evaluate((names) => {
    const cs = getComputedStyle(document.documentElement);
    return Object.fromEntries(names.map((n) => [n, cs.getPropertyValue(n).trim()]));
  }, Object.keys(WAS));
  await page.close();
  for (const [name, rgb] of Object.entries(WAS)) {
    assert.equal(got[name], rgb.join(" "), `${name} is "${got[name]}", was ${rgb.join(" ")}`);
  }
});

await check("the rgb(var(...) / a) form actually resolves", async () => {
  // The failure being guarded against is silent: an unsupported value leaves
  // the property `unset`, so the element renders with no background at all.
  const page = await K.open(browser, base, "index.html", {});
  const probe = await page.evaluate(() => {
    const el = document.createElement("div");
    el.style.background = "rgb(var(--accent-rgb) / 0.07)";
    el.style.color = "rgb(var(--bad-rgb) / 1)";
    document.body.append(el);
    const cs = getComputedStyle(el);
    const out = { bg: cs.backgroundColor, fg: cs.color };
    el.remove();
    return out;
  });
  await page.close();
  assert.equal(probe.bg, "rgba(56, 240, 255, 0.07)", `the tinted form resolved to ${probe.bg}`);
  assert.equal(probe.fg, "rgb(255, 107, 122)", `the opaque form resolved to ${probe.fg}`);
});

await check("no migrated declaration ended up transparent", async () => {
  // Every rule that used to paint a tint still paints one. A `var()` typo makes
  // the whole declaration invalid at computed-value time, and the element then
  // renders with the initial value — transparent — which is easy to miss.
  const CASES = [
    ["index.html", "#route", "borderTopColor", {}, undefined],
    ["index.html", ".approval-approve", "backgroundColor", { pending: [K.APPROVAL_RAISED] }, undefined],
    ["index.html", ".approval-deny", "borderTopColor", { pending: [K.APPROVAL_RAISED] }, undefined],
    ["index.html", "#offline", "backgroundColor", { link: { connected: false } }, undefined],
    ["widget.html", ".route-pill", "borderTopColor", {}, { width: 320, height: 460 }],
    ["widget.html", ".btn-deny", "borderTopColor", { pending: [K.APPROVAL_PLAIN] }, { width: 320, height: 460 }],
  ];
  for (const [file, selector, prop, data, viewport] of CASES) {
    const page = await K.open(browser, base, file, data, viewport);
    const value = await page.evaluate(([s, p]) => {
      const el = document.querySelector(s);
      return el ? getComputedStyle(el)[p] : "MISSING";
    }, [selector, prop]);
    await page.close();
    assert.notEqual(value, "MISSING", `${file} ${selector} is not on the page`);
    assert.ok(
      value !== "rgba(0, 0, 0, 0)" && value !== "transparent",
      `${file} ${selector} ${prop} is transparent — the declaration did not survive`
    );
  }
});

await check("a light theme actually moves the neutral washes", async () => {
  // The point of `--sheen-rgb`: `rgba(255,255,255,0.05)` as a hover state is
  // invisible on `paper`, and no theme could reach it while it was a literal.
  const page = await K.open(browser, base, "index.html", { theme: "paper" });
  const sheen = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--sheen-rgb").trim());
  await page.close();
  assert.notEqual(sheen, "255 255 255", "paper still lifts its surfaces with white");
});

await check("the widget's Approve button matches the Jarvis bar's", async () => {
  // 2026-09-27 (Q7): the widget's Approve used to be solid bright green
  // (`background: var(--ok)`, `color: var(--text-on-accent)`), which pulled
  // the eye harder than the bar's own softer, tinted Approve
  // (`.approval-approve` in `style.css`: `--ok-edge` / `--ok-fill` /
  // `--ok-text`). The owner chose to make the widget match the bar, by
  // reusing that same token triple rather than picking a new colour that
  // merely looks similar — so this checks the two buttons resolve to
  // IDENTICAL colours in every theme, not just similar ones. A future edit
  // that gives either button its own literal, or points it at a different
  // token, fails here before it ships a drift between the two.
  for (const theme of ["deep-space", "paper", "high-contrast"]) {
    const widget = await K.open(browser, base, "widget.html",
      { theme, pending: [K.APPROVAL_PLAIN] }, { width: 320, height: 460 });
    const widgetColors = await widget.evaluate(() => {
      const cs = getComputedStyle(document.querySelector(".btn-approve"));
      return { bg: cs.backgroundColor, fg: cs.color, border: cs.borderColor };
    });
    await widget.close();

    const bar = await K.open(browser, base, "index.html",
      { theme, pending: [K.APPROVAL_RAISED] }, { width: 750, height: 800 });
    const barColors = await bar.evaluate(() => {
      const cs = getComputedStyle(document.querySelector(".approval-approve"));
      return { bg: cs.backgroundColor, fg: cs.color, border: cs.borderColor };
    });
    await bar.close();

    assert.equal(widgetColors.bg, barColors.bg, `${theme}: Approve fill drifted from the bar`);
    assert.equal(widgetColors.fg, barColors.fg, `${theme}: Approve text drifted from the bar`);
    assert.equal(widgetColors.border, barColors.border, `${theme}: Approve edge drifted from the bar`);
  }
});

await check("CONTROL: no literal colour is left outside a defining block", async () => {
  // The same rule `scripts/check-tokens.py` enforces, asserted here too so a
  // regression fails the JS suite rather than only the Python one.
  const DEFINING = /(?::root\b|\[data-theme[^\]]*\])[^{]*\{/g;
  for (const name of ["style.css", "widget.css", "settings.css", "brain.css", "theme.css"]) {
    let src = read(name).replace(/\/\*[\s\S]*?\*\//g, (m) => " ".repeat(m.length));
    const spans = [];
    for (const m of src.matchAll(DEFINING)) {
      let i = src.indexOf("{", m.index);
      let depth = 0;
      let j = i;
      for (; j < src.length; j += 1) {
        if (src[j] === "{") depth += 1;
        else if (src[j] === "}" && --depth === 0) break;
      }
      spans.push([m.index, j + 1]);
    }
    // `\b` alone treats `-` as a boundary, so an ID selector like
    // `#face-frame` reads as the hex colour `#face` followed by `-frame` -
    // the same false positive scripts/check-tokens.py had. CSS identifiers
    // continue past a hyphen; the colour match must not.
    for (const m of src.matchAll(/#[0-9a-fA-F]{3,8}\b(?![-\w])/g)) {
      const inside = spans.some(([a, b]) => a <= m.index && m.index < b);
      assert.ok(inside, `${name}: ${m[0]} at ${m.index} is outside every defining block`);
    }
  }
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe token contract holds");
process.exit(fails.length ? 1 : 0);
