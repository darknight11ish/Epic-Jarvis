/**
 * Colours that mean different things must LOOK different — including to the
 * one man in twelve who cannot use hue the way the rest of the palette assumes.
 *
 * Contrast checking never catches this. Every colour in a set can clear 4.5:1
 * against the background and still be indistinguishable from its neighbour.
 * The previous ten-hue graph palette passed every contrast check in the suite
 * while measuring CIEDE2000 6.0 between `core` and `cluster` in normal vision
 * and 1.0 under deuteranopia — and in high contrast the two were the same hex.
 *
 * Threshold: 15, worst of normal / deuteranopia / protanopia. The visual spec's
 * own scale calls under 2 indistinguishable and ~10 obviously different at
 * arm's length, so 15 leaves headroom for a 6px dot.
 */
import * as K from "./uikit.mjs";
import { readTokens, parseColor } from "./contrast.mjs";

/**
 * Two floors, because a set that carries a second channel does not need its
 * colours to do all the work.
 *
 * `redundant` names the channel and is not decoration — it is the claim being
 * relied on, so it has to be true. If someone removes the word from
 * `.row-tag`, this line is the thing that should have stopped them.
 */
const SETS = [
  {
    name: "graph hues",
    // Five hues each carrying two groups, told apart by disc vs ring in
    // `drawNode`. The FORM is the redundant channel; the hues still have to be
    // separable from each other, so this set keeps the strict floor.
    tokens: ["--node-h1", "--node-h2", "--node-h3", "--node-h4", "--node-h5"],
    normal: 15,
    cvd: 15,
  },
  {
    name: "semantic states",
    tokens: ["--ok", "--warn", "--bad", "--info"],
    // Every appearance of these is labelled: `.row-tag` renders the state as a
    // word, digest rows carry the kind as text, the link pill says "stream
    // live" or "offline". So the colour is confirmation, not the message.
    redundant: "the state is always rendered as a word beside the colour",
    normal: 10,
    cvd: 5,
  },
];
const THEMES = ["default", "paper", "high-contrast"];

const srgb = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const gamma = (v) => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);

// Machado et al. 2009, severity 1.0.
const MACHADO = {
  deuteranopia: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
  protanopia:   [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
};
function simulate(rgb, kind) {
  const lin = rgb.map(srgb);
  return MACHADO[kind].map((row) => {
    const v = Math.max(0, Math.min(1, row[0] * lin[0] + row[1] * lin[1] + row[2] * lin[2]));
    return gamma(v) * 255;
  });
}
function toLab([r, g, b]) {
  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : (841 / 108) * t + 4 / 29);
  const [R, G, B] = [srgb(r), srgb(g), srgb(b)];
  const X = (0.4124 * R + 0.3576 * G + 0.1805 * B) / 0.95047;
  const Y = 0.2126 * R + 0.7152 * G + 0.0722 * B;
  const Z = (0.0193 * R + 0.1192 * G + 0.9505 * B) / 1.08883;
  const [fx, fy, fz] = [f(X), f(Y), f(Z)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}
function de2000(c1, c2) {
  const [L1, a1, b1] = toLab(c1), [L2, a2, b2] = toLab(c2);
  const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2), Cb = (C1 + C2) / 2;
  const G = Cb > 0 ? 0.5 * (1 - Math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7))) : 0;
  const a1p = (1 + G) * a1, a2p = (1 + G) * a2;
  const C1p = Math.hypot(a1p, b1), C2p = Math.hypot(a2p, b2);
  const h = (ap, bp) => (ap || bp ? ((Math.atan2(bp, ap) * 180) / Math.PI + 360) % 360 : 0);
  const h1 = h(a1p, b1), h2 = h(a2p, b2);
  const dLp = L2 - L1, dCp = C2p - C1p;
  const dh = C1p * C2p === 0 ? 0 : (((h2 - h1 + 180) % 360) - 180);
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dh * Math.PI) / 360);
  const Lb = (L1 + L2) / 2, Cbp = (C1p + C2p) / 2;
  let hb;
  if (C1p * C2p === 0) hb = h1 + h2;
  else if (Math.abs(h1 - h2) <= 180) hb = (h1 + h2) / 2;
  else hb = h1 + h2 < 360 ? (h1 + h2 + 360) / 2 : (h1 + h2 - 360) / 2;
  const rad = (d) => (d * Math.PI) / 180;
  const T = 1 - 0.17 * Math.cos(rad(hb - 30)) + 0.24 * Math.cos(rad(2 * hb))
            + 0.32 * Math.cos(rad(3 * hb + 6)) - 0.20 * Math.cos(rad(4 * hb - 63));
  const Sl = 1 + (0.015 * (Lb - 50) ** 2) / Math.sqrt(20 + (Lb - 50) ** 2);
  const Sc = 1 + 0.045 * Cbp, Sh = 1 + 0.015 * Cbp * T;
  const Rt = -2 * Math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
             * Math.sin(rad(60 * Math.exp(-(((hb - 275) / 25) ** 2))));
  return Math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                   + Rt * (dCp / Sc) * (dHp / Sh));
}
// eslint-disable-next-line no-unused-vars
const worst = (a, b) => Math.min(
  de2000(a, b),
  de2000(simulate(a, "deuteranopia"), simulate(b, "deuteranopia")),
  de2000(simulate(a, "protanopia"), simulate(b, "protanopia"))
);

const { base, close } = await K.serve();
const browser = await K.launch();
const page = await K.open(browser, base, "brain.html", { pending: [] },
  { width: 900, height: 600 });
const props = [...new Set(SETS.flatMap((s) => s.tokens))];
const tokens = await readTokens(page, props, THEMES);
await page.close();
await browser.close();
close();

let fails = 0, checks = 0;
for (const theme of THEMES) {
  const bad = [];
  for (const set of SETS) {
    for (let i = 0; i < set.tokens.length; i++) {
      for (let j = i + 1; j < set.tokens.length; j++) {
        const a = parseColor(tokens[theme][set.tokens[i]]);
        const b = parseColor(tokens[theme][set.tokens[j]]);
        checks++;
        if (!a || !b) { bad.push([set, set.tokens[i], set.tokens[j], NaN, NaN]); fails++; continue; }
        const A = a.slice(0, 3), B = b.slice(0, 3);
        const dn = de2000(A, B);
        const dc = Math.min(
          de2000(simulate(A, "deuteranopia"), simulate(B, "deuteranopia")),
          de2000(simulate(A, "protanopia"), simulate(B, "protanopia"))
        );
        if (dn < set.normal || dc < set.cvd) {
          bad.push([set, set.tokens[i], set.tokens[j], dn, dc]);
          fails++;
        }
      }
    }
  }
  console.log(`[${theme}]${bad.length ? "" : "  all pairs distinct"}`);
  for (const [set, x, y, dn, dc] of bad) {
    console.log(
      `  FAIL ${set.name}: ${x} vs ${y} — dE normal ${dn.toFixed(1)} ` +
      `(need ${set.normal}), CVD ${dc.toFixed(1)} (need ${set.cvd})` +
      (set.redundant ? `\n       relaxed floor because ${set.redundant}` : "")
    );
  }
}
console.log(`\n${checks} pairs, ${fails} too close.`);
process.exit(fails ? 1 : 0);
