/**
 * Theme guardrails: resolve every theme's custom properties in a real browser,
 * then do the WCAG arithmetic on the pairs that matter.
 *
 * Resolving in the browser rather than parsing CSS by hand is the point. The
 * themes use var() chains, and a regex over the stylesheet would check the
 * declarations rather than the values the user actually sees.
 *
 * The surfaces are semi-transparent over a TRANSPARENT native window, so every
 * ratio is computed twice: composited over black (the usual case, a dark
 * desktop) and over white (the worst case, a white window behind the overlay).
 * A pair passes only if it passes on both — that is what "it works wherever the
 * user put the window" means.
 */
import * as K from "./uikit.mjs";

const srgb = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
export const luminance = ([r, g, b]) => 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b);
export function ratio(fg, bg) {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}
/** Composite `over` (which may be translucent) onto an opaque backdrop. */
export function flatten([r, g, b, a], backdrop) {
  return [0, 1, 2].map(i => Math.round([r, g, b][i] * a + backdrop[i] * (1 - a)));
}

export function parseColor(text) {
  const m = String(text).match(/-?[\d.]+/g);
  if (!m) return null;
  const [r, g, b] = m.slice(0, 3).map(Number);
  const a = m.length > 3 ? Number(m[3]) : 1;
  return [r, g, b, a];
}

/**
 * Reads the computed value of every named custom property, under each theme.
 * Returns { theme: { prop: "rgb(...)" } }.
 */
export async function readTokens(page, props, themes) {
  const out = {};
  for (const theme of themes) {
    await page.evaluate((t) => {
      if (t === "default") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", t);
    }, theme);
    await page.waitForTimeout(60);
    out[theme] = await page.evaluate((names) => {
      // A custom property's computed value is the raw token, which for a
      // var() chain is not yet a colour. Painting it onto a probe element and
      // reading back `color` forces the browser to resolve it to rgb().
      const probe = document.createElement("span");
      probe.style.display = "none";
      document.body.append(probe);
      const got = {};
      for (const n of names) {
        probe.style.color = "";
        probe.style.color = `var(${n})`;
        got[n] = getComputedStyle(probe).color;
      }
      probe.remove();
      return got;
    }, props);
  }
  return out;
}

/** Every custom property declared anywhere in the loaded stylesheets. */
export async function declaredProps(page) {
  return page.evaluate(() => {
    const names = new Set();
    for (const sheet of document.styleSheets) {
      let rules;
      try { rules = sheet.cssRules; } catch { continue; }
      const walk = (list) => {
        for (const rule of list) {
          if (rule.style) {
            for (const p of rule.style) if (p.startsWith("--")) names.add(p);
          }
          if (rule.cssRules) walk(rule.cssRules);
        }
      };
      walk(rules);
    }
    return [...names].sort();
  });
}

export const BLACK = [0, 0, 0];
export const WHITE = [255, 255, 255];

/**
 * Checks one fg/bg pair under both backdrops.
 * `bg` may be translucent; `fg` is flattened over the composited bg.
 */
export function check(fgText, bgText, min) {
  const fg = parseColor(fgText), bg = parseColor(bgText);
  if (!fg || !bg) return { ok: false, why: "unparseable", fg: fgText, bg: bgText };
  const results = [BLACK, WHITE].map((backdrop) => {
    const solidBg = flatten(bg, backdrop);
    const solidFg = flatten(fg, solidBg);
    return ratio(solidFg, solidBg);
  });
  const worst = Math.min(...results);
  return {
    ok: worst >= min,
    worst: Number(worst.toFixed(2)),
    overBlack: Number(results[0].toFixed(2)),
    overWhite: Number(results[1].toFixed(2)),
    min, fg: fgText, bg: bgText,
  };
}

// ---- self-test: the arithmetic must be right before it judges anything ----
if (import.meta.url === `file://${process.argv[1]}`) {
  const eq = (got, want, what) => {
    const ok = Math.abs(got - want) < 0.02;
    console.log(`${ok ? "ok  " : "FAIL"}  ${what}: ${got} (expected ${want})`);
    if (!ok) process.exitCode = 1;
  };
  // Known WCAG values.
  eq(Number(ratio([255,255,255], [0,0,0]).toFixed(2)), 21, "white on black");
  eq(Number(ratio([0,0,0], [0,0,0]).toFixed(2)), 1, "black on black");
  eq(Number(ratio([119,119,119], [255,255,255]).toFixed(2)), 4.48, "#777 on white");
  eq(Number(ratio([0,0,255], [255,255,255]).toFixed(2)), 8.59, "blue on white");
  // Compositing: 50% white over black is #808080-ish (linear in sRGB space).
  const half = flatten([255,255,255,0.5], BLACK);
  eq(half[0], 128, "50% white over black -> 128");
  // A translucent surface really does behave differently over the two backdrops.
  const c = check("rgb(139,148,163)", "rgba(8,9,12,0.86)", 4.5);
  console.log(`   translucent surface: over black ${c.overBlack}, over white ${c.overWhite}`);
  if (c.overBlack === c.overWhite) { console.log("FAIL  backdrop made no difference"); process.exitCode = 1; }
}
