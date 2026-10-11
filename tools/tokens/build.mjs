#!/usr/bin/env node
/**
 * Builds both clients' palettes from one file.
 *
 *     node tools/tokens/build.mjs            write the generated files
 *     node tools/tokens/build.mjs --check    fail if either is out of date
 *
 * WHY. `jarvis-desktop/src/theme.css` and the phone's
 * `ui/theme/Themes.kt` used to carry the same colours typed out twice, in two
 * languages. A test could see the theme NAMES agree; nothing could see the
 * VALUES. A measurement on 2026-10-09 found 36 of 51 same-role values had
 * drifted apart (`docs/THEME-VALUE-PARITY-FINDINGS.md`). This makes drift
 * impossible instead of merely detectable: neither file is edited by hand any
 * more, and `--check` is what CI and `tests/tokens.mjs` run.
 *
 * WHAT IT READS. `tokens/themes.tokens.json`, in DTCG shape - a token is any
 * node carrying `$value`, a group is any node without one, and an alias is
 * `{group.token}`. Zero dependencies on purpose: this repository has exactly
 * one build dependency (`@tauri-apps/cli`) and no bundler, and a token pipeline
 * is not a good reason to acquire one.
 *
 * THE ONE HONESTY. The two clients do NOT hold every colour identically, and
 * this file does not pretend otherwise. Where the phone genuinely differs - its
 * surfaces are opaque where the desktop's windows are translucent; the phone's
 * semantics come from the spec's palette ramps where the desktop's are bespoke -
 * the token carries a `$extensions.phone.$value` WITH THE REASON WRITTEN OUT.
 * That is a declared divergence, in one place, instead of an accident. Nothing
 * here quietly picks a winner.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const TOKENS = path.join(ROOT, "tokens", "themes.tokens.json");
const CSS_OUT = path.join(ROOT, "jarvis-desktop", "src", "theme.css");
const KT_OUT = path.join(ROOT, "jarvis-client", "app", "src", "main", "java", "com", "jarvis", "client", "ui", "theme", "Themes.kt");

const CHECK = process.argv.includes("--check");

/* ── 1. Read and index ───────────────────────────────────────────────────── */

const file = JSON.parse(fs.readFileSync(TOKENS, "utf8"));

/** Every node carrying `$value`, keyed by its dotted path. */
const all = new Map();
(function walk(node, trail) {
  if (node === null || typeof node !== "object" || Array.isArray(node)) return;
  if ("$value" in node) { all.set(trail.join("."), node); return; }
  for (const [key, child] of Object.entries(node)) {
    if (key.startsWith("$")) continue;
    walk(child, [...trail, key]);
  }
})(file, []);
all.delete(""); // the file root, if it ever grows one

function token(path) {
  const node = all.get(path);
  if (!node) throw new Error(`no such token: ${path}`);
  return node;
}

/** Follows `{a.b.c}` aliases, refusing a cycle rather than recursing for ever. */
function resolve(path, seen = []) {
  const raw = token(path).$value;
  if (typeof raw !== "string") return raw;
  const m = /^\{([^}]+)\}$/.exec(raw.trim());
  if (!m) return raw;
  if (seen.includes(path)) throw new Error(`alias cycle: ${[...seen, path].join(" -> ")}`);
  return resolve(m[1], [...seen, path]);
}

/** The value this token has on the phone: its declared override, else the
 *  shared one. */
function phoneValue(path) {
  const node = token(path);
  const ext = node.$extensions?.phone;
  if (!ext) return { text: null, value: resolve(path), overridden: false };
  return { text: ext.$value, value: resolve(path), overridden: true, reason: ext.reason };
}

/* ── 2. Names ────────────────────────────────────────────────────────────── */

/** `durInstant` -> `--dur-instant`; `text2xs` -> `--text-2xs`. */
function kebab(name) {
  return "--" + name.replace(/([a-z])([A-Z0-9])/g, "$1-$2").toLowerCase();
}

/** Root tokens whose CSS property name the kebab rule would get wrong. */
const ROOT_CSS = {
  stateIdle: "--state-idle", stateListening: "--state-listening", stateThinking: "--state-thinking",
  stateSpeaking: "--state-speaking", stateApproval: "--state-approval", stateStandby: "--state-standby",
  stateError: "--state-error", stateBanked: "--state-banked",
  swatchReactorGround: "--swatch-reactor-ground", swatchReactorInk: "--swatch-reactor-ink",
  swatchDaylightGround: "--swatch-daylight-ground", swatchDaylightInk: "--swatch-daylight-ink",
  swatchContrastGround: "--swatch-contrast-ground", swatchContrastInk: "--swatch-contrast-ink",
  text2xs: "--text-2xs", textXs: "--text-xs", textSm: "--text-sm", textMd: "--text-md", textLg: "--text-lg",
  easeOut: "--ease-out", durInstant: "--dur-instant", durQuick: "--dur-quick", durSettle: "--dur-settle",
  // The bare channel tokens: `--accent-rgb`, not `--accent-rgb-rgb`.
  accentRgb: "--accent-rgb", okRgb: "--ok-rgb", warnRgb: "--warn-rgb", badRgb: "--bad-rgb",
  infoRgb: "--info-rgb", mutedRgb: "--muted-rgb", sheenRgb: "--sheen-rgb", shadeRgb: "--shade-rgb",
};

/** The one place a token path becomes a CSS custom property, used for the
 *  declaration AND for whatever an alias points at, so the two cannot disagree.
 *  The token file itself carries the names the kebab rule gets wrong
 *  (`meta.$cssNames`), because `--text` and `--bg-window` are not derivable from
 *  `textHi` and `surface0`. */
const THEME_CSS = file.meta.$cssNames.$value;

function cssNameOf(tokenPath) {
  const parts = tokenPath.split(".");
  const last = parts[parts.length - 1];
  if (parts[0] === "root") return ROOT_CSS[last] ?? kebab(last);
  return THEME_CSS[last] ?? kebab(last);
}

/* ── 3. theme.css ────────────────────────────────────────────────────────── */

/** The `R G B` channels: written in each theme block, because `--sheen` and
 *  `--shade` genuinely move between a dark and a light theme. */
const CHANNELS = ["accentRgb", "okRgb", "warnRgb", "badRgb", "infoRgb", "mutedRgb", "sheenRgb", "shadeRgb"];

/** The order a theme block writes its tokens in. Explicit, so the generated CSS
 *  is diffable and still reads in the order the hand-written file used. */
const CSS_ORDER = [
  "prose", "proseStrong", "proseEm",
  "surface0", "surface1", "surface2", "surfaceSunken", "surfaceHover", "surfaceActive",
  "hairline", "hairlineStrong", "hairlineFocus", "borderAccent",
  "textHi", "textMid", "textLo", "textOnAccent",
  "accent", "accentBright", "accentDim", "accentFaint", "accentText",
  "ok", "warn", "bad", "info",
  "okFaint", "warnFaint", "badFaint", "infoFaint",
  "okFill", "okEdge", "okText", "badFill", "badText",
  "codeBg", "codeText", "diffAdd", "diffRemove",
  "shadowCard", "shadowPane", "glowAccent",
  "edge", "edgeActive",
  "nodeH1", "nodeH2", "nodeH3", "nodeH4", "nodeH5",
  "tag0", "tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tagTint",
  "radiusWindow", "radiusCard", "radiusControl", "strokeHair",
];

/** A token's comment, verbatim. The file this replaces puts real reasoning in
 *  these comments - measurements, why a value is what it is - so they are
 *  content, not decoration, and a generator that dropped them would be a
 *  downgrade. */
function cssComment(node, indent) {
  const d = node?.$description;
  if (!d) return [];
  const body = String(d).replace(/\r/g, "").split("\n").map((l) => l.trimEnd());
  if (body.length === 1) return [`${indent}/* ${body[0].trim()} */`];
  return [`${indent}/* ${body[0].trim()}`, ...body.slice(1).map((l) => `${indent}   ${l.trim()}`), `${indent}   */`];
}

/** A token's value as CSS. A whole-value alias becomes `var(--other)`; an alias
 *  embedded in a longer value (a shadow that names a colour) is resolved to the
 *  colour, because `var()` mid-value is invalid at computed-value time. */
function cssValue(path, value, seen = []) {
  const text = String(value);
  return text.replace(/\{([^}]+)\}/g, (_m, target) => {
    if (!all.has(target)) throw new Error(`${path}: alias points at nothing: {${target}}`);
    const inner = token(target).$value;
    if (typeof inner === "string" && !inner.includes("{")) return cssValue(target, inner, seen);
    return `var(${cssNameOf(target)})`;
  });
}

function declaration(path, indent) {
  return `${indent}${cssNameOf(path)}: ${cssValue(path, token(path).$value)};`;
}

/** Writes a token (or the `tag` group's members) into the array `L`. */
function writeToken(L, path, name, indent) {
  const node = token(`${path}.${name}`);
  if (name === "tag") {
    L.push(...cssComment(node, indent));
    for (let i = 0; i < 8; i++) L.push(declaration(`${path}.tag.tag${i}`, indent));
    return;
  }
  L.push(...cssComment(node, indent));
  L.push(declaration(`${path}.${name}`, indent));
}

function buildCss() {
  const L = [];
  const push = (...xs) => L.push(...xs);

  push(
    "/* ==========================================================================",
    "   The token contract",
    "   --------------------------------------------------------------------------",
    "   One file that every surface imports, and the only place a colour is allowed",
    "   to be written down.",
    "",
    "   GENERATED - DO NOT EDIT. `tools/tokens/build.mjs` writes this file from",
    "   `tokens/themes.tokens.json`, and writes the phone's `Themes.kt` from the",
    "   same tokens. The two clients used to carry these values typed out twice;",
    "   36 of 51 same-role values had drifted apart before this",
    "   (docs/THEME-VALUE-PARITY-FINDINGS.md). Change the token file, then run:",
    "",
    "       node tools/tokens/build.mjs",
    "",
    "   `node tools/tokens/build.mjs --check` fails when this file and the token",
    "   file disagree, which is what CI and tests/tokens.mjs run.",
    "",
    "   THE RULE. A literal colour belongs in `:root` or in a `[data-theme]` block",
    "   in this file. Anywhere else it is a bug, and `scripts/check-tokens.py`",
    "   fails the build for it.",
    "",
    "   HOW A THEME IS APPLIED. `data-theme` on `<html>`, set before first paint by",
    "   the inline bootstrap in each page so there is no flash of the wrong",
    "   palette. A theme block only needs to redefine the tokens it changes;",
    "   everything else inherits from `:root`.",
    "",
    "   CONTRAST. Every text-on-surface pair below is checked against BOTH a black",
    "   and a white backdrop, because these windows are transparent and the desktop",
    "   behind them is not ours to choose. A pair that passes over black and fails",
    "   over white is a pair that fails on somebody's wallpaper.",
    "   ========================================================================== */",
    "",
    ":root {",
  );

  const R = "root";
  const groups = [
    ["---- Raw channels", "root.accentRgb", ["accentRgb", "okRgb", "warnRgb", "badRgb", "infoRgb"]],
    ["---- Face states", "root.stateIdle", ["stateIdle", "stateListening", "stateThinking", "stateSpeaking", "stateApproval", "stateStandby", "stateError", "stateBanked"]],
    ["---- Theme swatches", "root.swatchReactorGround", ["swatchReactorGround", "swatchReactorInk", "swatchDaylightGround", "swatchDaylightInk", "swatchContrastGround", "swatchContrastInk"]],
    ["---- Shape", "root.radiusWindow", ["radiusWindow", "radiusCard", "radiusControl", "radiusChip", "strokeHair"]],
    ["---- Type", "root.fontUi", ["fontUi", "fontDisplay", "fontMono"]],
    ["---- Type scale", "root.text2xs", ["text2xs", "textXs", "textSm", "textMd", "textLg"]],
    ["---- Motion", "root.ease", ["ease", "easeOut", "durInstant", "durQuick", "durSettle"]],
  ];

  for (const [title, groupPath, names] of groups) {
    push("", `  /* ${title} ${"-".repeat(Math.max(0, 68 - title.length))} */`);
    push(...cssComment(all.get(groupPath), "  "));
    for (const name of names) writeToken(L, R, name, "  ");
  }
  push("}", "");

  const blocks = [
    ["deep-space", [":root,", '[data-theme="deep-space"]'], "Reactor (`deep-space`) - the default: near-black so an OLED panel draws no power for the background, one cyan accent, everything else grey."],
    ["paper", ['[data-theme="paper"]'], "Daylight (`paper`) - genuinely light, not an inversion. The surfaces are opaque here on purpose: a translucent light pane over a dark wallpaper is unreadable, and the contrast check over black is what catches that."],
    ["high-contrast", ['[data-theme="high-contrast"]'], "High Contrast (`high-contrast`) - for reading across a room, and for anyone the other themes do not serve. Not a \"dark theme with more punch\": every pair here clears 7:1, the AAA floor."],
  ];

  for (const [id, selectors, blurb] of blocks) {
    const themePath = `themes.${id}`;
    push("/* " + blurb + " */");
    push(...selectors.slice(0, -1));
    push(`${selectors[selectors.length - 1]} {`);
    push(`  color-scheme: ${token(`${themePath}.dark`).$value ? "dark" : "light"};`);

    // The channels first: the same colours as the tokens below, so a component
    // that needs a hue at 7% alpha does not weld a literal into a rule.
    // `--sheen` and `--shade` are the two neutrals - the wash that LIFTS a
    // surface and the one that SINKS it. On a dark theme the lift is white; on
    // `paper` it is ink, which is why a component may not write
    // `rgba(255, 255, 255, 0.05)` for a hover state.
    for (const channel of CHANNELS) {
      if (!all.has(`${themePath}.${channel}`)) continue;
      push(...cssComment(all.get(`${themePath}.${channel}`), "  "));
      push(declaration(`${themePath}.${channel}`, "  "));
    }
    for (const name of CSS_ORDER) {
      if (CHANNELS.includes(name)) continue;
      if (!all.has(`${themePath}.${name}`)) continue;
      writeToken(L, themePath, name, "  ");
    }
    push("}", "");
  }

  push(
    "/* ==========================================================================",
    "   Reduced motion",
    "   --------------------------------------------------------------------------",
    "   Collapsed at the token level so it reaches every surface at once, including",
    "   any component that has not thought about it. Individual pages still need",
    "   their own `@media` block for keyframe animations, which a duration token",
    "   cannot switch off.",
    "   ========================================================================== */",
    "",
    "@media (prefers-reduced-motion: reduce) {",
    "  :root {",
    "    --dur-instant: 1ms;",
    "    --dur-quick: 1ms;",
    "    --dur-settle: 1ms;",
    "  }",
    "}",
    "",
  );
  return L.join("\n");
}

/* ── 4. Themes.kt ────────────────────────────────────────────────────────── */

/** The `Chrome` fields, in the order the data class declares them. */
const CHROME_FIELDS = [
  "surface0", "surface1", "surface2", "well",
  "textHi", "textMid", "textLo",
  "hairline", "hairlineStrong", "hairlineFocus",
  "okInk", "warnInk", "badInk",
  "okMark", "warnMark", "badMark",
  "cloudInk",
];

/** The phone's own role -> token map. Named here rather than guessed from the
 *  desktop's, because the desktop has ONE token where the phone has an ink tier
 *  and a mark tier (Chrome.kt:86-107). */
const PHONE_ROLE = {
  surface0: "surface0", surface1: "surface1", surface2: "surface2",
  textHi: "textHi", textMid: "textMid", textLo: "textLo",
  hairline: "hairline", hairlineStrong: "hairlineStrong", hairlineFocus: "hairlineFocus",
  okInk: "ok", warnInk: "warn", badInk: "bad",
  okMark: "ok", warnMark: "warn", badMark: "bad",
  cloudInk: "info",
};

/** The well is the face's ground, not a chrome surface, and it is the one thing
 *  the phone may not vary per theme: faces composite additively, so a light well
 *  erases the glow, and `Chrome.wellIsLegal` asserts it stays essentially black.
 *  That is why `Daylight` keeps a dark well on the phone. It is a spec constant,
 *  not a divergence, so it is not a phone override. */
const WELL = "#04070c";

/** The phone's value for a token: its declared override, else the shared value.
 *  A `mark` override is the phone's second tier (icons and fills) where the
 *  desktop has one token for both, so it is read for the mark fields. */
function phoneField(themePath, tokenName, { mark = false } = {}) {
  const node = token(`${themePath}.${tokenName}`);
  const ext = node.$extensions?.phone;
  const raw = mark && ext?.mark ? ext.mark : ext?.$value;
  if (raw === undefined) return toKotlin(resolve(`${themePath}.${tokenName}`), `${themePath}.${tokenName}`);
  const m = /^\{palette\.([a-z]+)\.(\d)\}$/.exec(String(raw).trim());
  if (m) return `Palette.${m[1].toUpperCase()}_${m[2]}`;
  return toKotlin(String(raw), `${themePath}.${tokenName}`);
}

/** `#RRGGBB` or `rgb(r, g, b)` -> `Color(0xFFRRGGBB)`. A translucent value
 *  reaching here is a real bug, not a formatting problem: the phone has no
 *  translucent surface. */
function toKotlin(value, where) {
  const hex = /^#([0-9a-fA-F]{6})$/.exec(String(value).trim());
  if (hex) return `Color(0xFF${hex[1].toUpperCase()})`;
  const rgb = /^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/.exec(String(value).trim());
  if (rgb) {
    const h = (n) => Number(n).toString(16).padStart(2, "0").toUpperCase();
    return `Color(0xFF${h(rgb[1])}${h(rgb[2])}${h(rgb[3])})`;
  }
  throw new Error(`${where}: the phone cannot take "${value}" - it is translucent, or not a colour`);
}

function buildKotlin() {
  const raw = fs.readFileSync(KT_OUT, "utf8");
  let HEADER = raw.split("object Themes {")[0].replace(/\s+$/, "");
  // The header is hand-written prose, kept verbatim; this one line is the only
  // thing the generator adds to it, so a reader of the Kotlin file is told where
  // the values come from without having to find this script.
  if (!HEADER.includes("GENERATED")) {
    HEADER +=
      "\n\n// GENERATED - DO NOT EDIT. `tools/tokens/build.mjs` writes the three\n" +
      "// `Chrome(...)` blocks below from `tokens/themes.tokens.json`, and writes the\n" +
      "// desktop's `theme.css` from the same tokens. A colour that differs from the\n" +
      "// desktop's carries its reason in the token file, because a difference is a\n" +
      "// decision and never an accident. Change the token file, then run:\n" +
      "//\n" +
      "//     node tools/tokens/build.mjs";
  }
  const L = [HEADER, "", "object Themes {"];
  const desktopIds = Object.keys(file.themes).filter((k) => !k.startsWith("$"));

  for (const id of desktopIds) {
    const themePath = `themes.${id}`;
    const phoneId = token(`${themePath}.phoneId`).$value;
    L.push("", `    val ${phoneId.toUpperCase()} = Chrome(`);
    L.push(`        id = "${phoneId}",`);
    L.push(`        label = "${token(`${themePath}.label`).$value}",`);
    L.push(`        blurb = "${token(`${themePath}.blurb`).$value}",`);
    L.push(`        dark = ${token(`${themePath}.dark`).$value},`);

    for (const field of CHROME_FIELDS) {
      if (field === "surface0") L.push("", "        // Class A ------------------------------------------------------------");
      if (field === "okInk") L.push("", "        // Class B ------------------------------------------------------------");
      if (field === "cloudInk") L.push("", "        // Class B in spirit: the words that say \"this is leaving your machine\".");
      if (field === "well") {
        L.push(`        well = ${phoneField(themePath, "well")},   // the face's ground; must stay essentially black (wellIsLegal)`);
        continue;
      }
      const tokenName = PHONE_ROLE[field];
      const isMark = field === "okMark" || field === "warnMark" || field === "badMark";
      const node = token(`${themePath}.${tokenName}`);
      const ext = node.$extensions?.phone;
      const overridden = Boolean(isMark ? ext?.mark : ext?.$value);
      L.push(`        ${field} = ${phoneField(themePath, tokenName, { mark: isMark })},${overridden ? "   // differs from the desktop; the token file says why" : ""}`);
    }
    L.push("    )");
  }

  L.push(
    "",
    "    val ALL: List<Chrome> = listOf(REACTOR, DAYLIGHT, CONTRAST)",
    "",
    "    val DEFAULT: Chrome = REACTOR",
    "",
    "    fun byId(id: String?): Chrome = ALL.firstOrNull { it.id == id } ?: DEFAULT",
    "",
    "    /** The theme a \"follow the system\" setting maps to for each OS mode. */",
    "    fun forSystem(systemDark: Boolean, preferredDark: Chrome): Chrome =",
    "        if (systemDark) preferredDark else DAYLIGHT",
    "}",
    "",
  );
  return L.join("\n");
}

/* ── 5. Write, or check ──────────────────────────────────────────────────── */

const outputs = [
  { file: CSS_OUT, text: buildCss(), what: "theme.css" },
  { file: KT_OUT, text: buildKotlin(), what: "Themes.kt" },
];

if (CHECK) {
  const stale = outputs.filter((o) => !fs.existsSync(o.file) || fs.readFileSync(o.file, "utf8") !== o.text);
  if (stale.length) {
    console.error("stale generated theme files - run: node tools/tokens/build.mjs");
    for (const s of stale) console.error(`  ${path.relative(ROOT, s.file)}`);
    process.exit(1);
  }
  console.log("tokens: theme.css and Themes.kt both match tokens/themes.tokens.json");
} else {
  for (const o of outputs) {
    fs.mkdirSync(path.dirname(o.file), { recursive: true });
    const before = fs.existsSync(o.file) ? fs.readFileSync(o.file, "utf8") : null;
    fs.writeFileSync(o.file, o.text);
    console.log(`tokens: ${before === null ? "created" : before === o.text ? "unchanged" : "written"} ${path.relative(ROOT, o.file)}`);
  }
}
