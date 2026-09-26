/**
 * Tests the markdown renderer the quickbar and the Brain's deep questions
 * share (src/markdown.js).
 *
 * It used to be sliced out of main.js by its section banners, because main.js
 * has top-level side effects that need a DOM. It now lives in its own module
 * with no side effects, so this imports the real file: still no copy, which is
 * the point - a copy would drift, and the bug this file exists to prevent was
 * invisible precisely because nothing executed the parser.
 *
 * The bug: the opening-fence regex accepted only a bare `[\w+-]` language, but
 * the paragraph branch excludes every line starting with a fence. A line that
 * matched neither advanced no index, so the loop spun for ever — and
 * `renderMarkdown` runs on every streamed token, in a frameless always-on-top
 * window with no titlebar and no taskbar entry. "```c#" was enough.
 *
 * Run with `node scripts/markdown-test.mjs` from `jarvis-desktop/`.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { renderMarkdown } from "../src/markdown.js";

// main.js must use this module, not grow its own renderer back.
const here = dirname(fileURLToPath(import.meta.url));
const mainSource = readFileSync(join(here, "..", "src", "main.js"), "utf8");
if (!mainSource.includes('from "./markdown.js"') || /function renderMarkdown\(/.test(mainSource)) {
  console.error("main.js no longer imports its renderer from markdown.js.");
  process.exit(2);
}

let failures = 0;
const check = (name, condition, detail) => {
  if (!condition) {
    failures += 1;
    console.error(`FAIL  ${name}${detail ? `\n      ${detail}` : ""}`);
  }
};

/* -------------------------------------------------------------------------
 * Termination. Every one of these hung the parser before the fix.
 * ---------------------------------------------------------------------- */
const previouslyHung = [
  "``` js",            // a space before the language
  "```c#",             // # is not in [\w+-]
  "````",              // four backticks
  "```js // hi",       // a trailing comment
  '```js title="a.js"', // an info string
  "~~~",               // tilde fence
  "~~~python",
  "   ```js",          // indented
];
for (const input of previouslyHung) {
  const out = renderMarkdown(input);
  check(`terminates: ${JSON.stringify(input)}`, typeof out === "string");
}

/* -------------------------------------------------------------------------
 * Rendering. The shapes a model actually emits.
 * ---------------------------------------------------------------------- */
const cases = [
  ["**bold**", "<strong>bold</strong>"],
  ["*em*", "<em>em</em>"],
  ["# Heading", "<h1>Heading</h1>"],
  ["#### Small", "<h4>Small</h4>"],
  ["- a\n- b", "<ul><li>a</li><li>b</li></ul>"],
  ["1. a\n2. b", "<ol><li>a</li><li>b</li></ol>"],
  ["> quoted", "<blockquote>"],
  ["\n| A | B |\n|---|---|\n| 1 | 2 |", "<table>"],
  ["```js\nconst x = 1;\n```", 'class="language-js"'],
  ["```js\nconst x = 1;\n```", "const x = 1;"],
  ["```c#\nvar x = 1;\n```", 'class="language-c#"'],
  ['```js title="a.js"\nlet y;\n```', 'class="language-js"'],
  ["~~~python\nprint(1)\n~~~", 'class="language-python"'],
  ["```\nplain\n```", "<pre><code>plain</code></pre>"],
  ["````\n```\nnested\n```\n````", "nested"],
  ["a `code` b", "<code>code</code>"],
  ["---", "<hr />"],
  ["[l](https://e.com)", 'href="https://e.com"'],
  ["text\n\nmore", "<p>text</p><p>more</p>"],
];
for (const [input, expected] of cases) {
  const out = renderMarkdown(input);
  check(
    `renders ${JSON.stringify(input).slice(0, 40)}`,
    out.includes(expected),
    `expected to contain ${JSON.stringify(expected)}, got ${JSON.stringify(out).slice(0, 160)}`
  );
}

/* -------------------------------------------------------------------------
 * Escaping. The renderer is escape-first and must stay that way.
 *
 * Asserting the output does not CONTAIN "onerror=" would be wrong: escaped
 * text legitimately contains it, as `&lt;img src=x onerror=alert(1)&gt;`, which
 * is inert. What matters is that every tag the output actually emits is one
 * the renderer meant to emit, and that no attribute outside its own vocabulary
 * appears. That is the invariant; the strings are incidental.
 * ---------------------------------------------------------------------- */
const ALLOWED_TAGS = new Set([
  "p", "strong", "em", "s", "code", "pre", "br", "hr",
  "h1", "h2", "h3", "h4", "ul", "ol", "li", "blockquote",
  "table", "thead", "tbody", "tr", "th", "td", "a", "span",
]);
const ALLOWED_ATTRS = new Set(["href", "class", "data-external"]);

function offences(html) {
  const found = [];
  // Only look inside tags the renderer actually emitted. Every `<` from the
  // input has been escaped to `&lt;` by this point, so anything matching here
  // is the renderer's own output — and an attribute-looking string in escaped
  // text (`&lt;img src=x onerror=…&gt;`) is inert prose, not an attribute.
  for (const match of html.matchAll(/<(\/?)([a-zA-Z][\w-]*)((?:"[^"]*"|[^>"])*)>/g)) {
    const [, closing, rawTag, attrs] = match;
    const tag = rawTag.toLowerCase();
    if (!ALLOWED_TAGS.has(tag)) {
      found.push(`<${closing}${tag}>`);
      continue;
    }
    if (closing) continue;
    for (const [, attr] of attrs.matchAll(/(?:^|\s)([a-zA-Z-]+)\s*=/g)) {
      if (!ALLOWED_ATTRS.has(attr.toLowerCase())) found.push(`${tag}[${attr}]`);
    }
  }
  for (const [, href] of html.matchAll(/href="([^"]*)"/g)) {
    if (/^\s*(javascript|data|vbscript):/i.test(href)) found.push(`href=${href}`);
  }
  return found;
}

const hostile = [
  "<img src=x onerror=alert(1)>",
  '"><script>alert(1)</script>',
  "<a href=\"javascript:alert(1)\">x</a>",
  "```diff\n+\"><img src=x onerror=alert(1)>\n```",
  "[l](javascript:alert(1))",
  "[l](\" onmouseover=\"alert(1))",
  "| <b>a</b> |\n|---|\n| <img src=x onerror=alert(1)> |",
  "> <svg onload=alert(1)>",
  "# <iframe src=//evil>",
  "`</code><script>alert(1)</script>`",
];
for (const input of hostile) {
  const bad = offences(renderMarkdown(input));
  check(
    `escapes ${JSON.stringify(input).slice(0, 44)}`,
    bad.length === 0,
    `emitted ${JSON.stringify(bad)} from ${JSON.stringify(renderMarkdown(input)).slice(0, 160)}`
  );
}

/* -------------------------------------------------------------------------
 * The URL must survive the emphasis passes intact.
 *
 * `__` and `*` inside a URL used to be rewritten before linkification saw
 * them, so the href ended up pointing somewhere the text did not say — and
 * that href is what `open_external_url` hands to the OS shell.
 * ---------------------------------------------------------------------- */
const hrefOf = (html) => (html.match(/href="([^"]*)"/) || [])[1];
const urlCases = [
  ["Read https://x.com/a__b__c now.", "https://x.com/a__b__c"],
  ["[docs](https://example.com/a__b__c)", "https://example.com/a__b__c"],
  ["See https://e.com/x**y**z", "https://e.com/x**y**z"],
  ["[l](https://e.com/p?a=1&b=2)", "https://e.com/p?a=1&amp;b=2"],
];
for (const [input, expected] of urlCases) {
  check(
    `href intact: ${JSON.stringify(input).slice(0, 40)}`,
    hrefOf(renderMarkdown(input)) === expected,
    `expected ${expected}, got ${hrefOf(renderMarkdown(input))}`
  );
}
check(
  "identifiers are not emphasised",
  !renderMarkdown("The field is user__name__id.").includes("<strong>"),
  renderMarkdown("The field is user__name__id.")
);

/* -------------------------------------------------------------------------
 * Placeholders are per-call, so model output cannot collide with them.
 * ---------------------------------------------------------------------- */
check(
  "placeholder collision is inert",
  renderMarkdown("Use `alpha` then literally @@JARVISCODE0@@ here.").includes(
    "@@JARVISCODE0@@"
  ),
  renderMarkdown("Use `alpha` then literally @@JARVISCODE0@@ here.")
);
check(
  "unmatched placeholder is not substituted",
  !renderMarkdown("Model writes @@JARVISCODE0@@ alone.").includes("undefined"),
  renderMarkdown("Model writes @@JARVISCODE0@@ alone.")
);

/* -------------------------------------------------------------------------
 * Fuzz. No input may fail to terminate — that is the structural guarantee the
 * parser now carries, and the only way to keep it is to keep trying to break it.
 * ---------------------------------------------------------------------- */
const alphabet = "` ~ # > - * + | _ 1. . [ ] ( ) \n a \\ ! : = \" '".split(" ");
alphabet.push("\n");
const ROUNDS = Number(process.env.MARKDOWN_FUZZ_ROUNDS || 50000);
for (let i = 0; i < ROUNDS; i++) {
  let input = "";
  const length = 1 + Math.floor(Math.random() * 16);
  for (let k = 0; k < length; k++) {
    input += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  try {
    renderMarkdown(input);
  } catch (error) {
    failures += 1;
    console.error(`FAIL  fuzz threw on ${JSON.stringify(input)}: ${error.message}`);
    break;
  }
}

const total = previouslyHung.length + cases.length + hostile.length + urlCases.length + 3;
if (failures) {
  console.error(`\n${failures} failure(s) across ${total} cases + ${ROUNDS} fuzz inputs`);
  process.exit(1);
}
console.log(`markdown: ${total} cases and ${ROUNDS} fuzz inputs pass`);
