// The Jarvis bar can approve things and control tasks, and it paints text a
// model wrote. The one thing standing between a model's words and the page is
// that every HTML sink is fed escaped or rendered-and-escaped text
// (`escapeHtml`, `renderMarkdown`) or a constant. This test walks src/*.js and
// fails on any innerHTML / outerHTML / insertAdjacentHTML / document.write /
// createContextualFragment whose right-hand side is not one of those, so a NEW
// sink has to be looked at by a person and added to SAFE_SITES below on
// purpose. No browser needed.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

/** Sites reviewed by a person. `rhs` matches the start of the value (whitespace
 *  collapsed); every `${...}` in it must start with escapeHtml( or
 *  renderMarkdown( or be listed in `exprs` exactly. Keyed by the file and the
 *  target, never by a line number. */
export const SAFE_SITES = [
  {
    file: "main.js",
    target: "dom.previousAnswerBody.innerHTML",
    rhs: /^pairs\.map\(/,
    // `line` is built one statement above from escapeHtml(THREAD_READS_FROM).
    exprs: ['above > 0 && i === above ? line : ""'],
  },
  {
    file: "main.js",
    target: "code.innerHTML",
    rhs: /^html$/,
    // decorateDiff(): `html` is rebuilt from escapeHtml(line) pieces only.
    exprs: [],
  },
];

const SINK =
  /(\.(?:innerHTML|outerHTML)\s*\+?=(?!=)|\.insertAdjacentHTML\s*\(|document\.write(?:ln)?\s*\(|createContextualFragment\s*\()/g;

function skipString(src, i) {
  const q = src[i];
  for (i++; i < src.length; i++) {
    if (src[i] === "\\") {
      i++;
      continue;
    }
    if (q === "`" && src[i] === "$" && src[i + 1] === "{") {
      let depth = 1;
      i += 2;
      while (i < src.length && depth) {
        const c = src[i];
        if (c === "'" || c === '"' || c === "`") i = skipString(src, i);
        else if (c === "{") depth++;
        else if (c === "}") depth--;
        i++;
      }
      i--;
      continue;
    }
    if (src[i] === q) return i;
  }
  return i;
}

/** The text of the statement that starts at `from`, up to its `;` outside any
 *  bracket or string. Good enough for this code base's style. */
function statementFrom(src, from) {
  let depth = 0;
  for (let i = from; i < src.length; i++) {
    const c = src[i];
    if (c === "'" || c === '"' || c === "`") {
      i = skipString(src, i);
      continue;
    }
    if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") i++;
      continue;
    }
    if (c === "/" && src[i + 1] === "*") {
      i = src.indexOf("*/", i + 2) + 1;
      continue;
    }
    if ("([{".includes(c)) depth++;
    else if (")]}".includes(c)) depth--;
    else if (c === ";" && depth <= 0) return src.slice(from, i);
    if (depth < 0) return src.slice(from, i);
  }
  return src.slice(from);
}

/** Every `${...}` expression inside the statement text, nesting respected. */
export function interpolations(text) {
  const out = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== "`") continue;
    const end = skipString(text, i);
    const body = text.slice(i + 1, end);
    for (let j = 0; j < body.length; j++) {
      if (body[j] === "$" && body[j + 1] === "{") {
        let depth = 1;
        let k = j + 2;
        while (k < body.length && depth) {
          const c = body[k];
          if (c === "'" || c === '"' || c === "`") k = skipString(body, k);
          else if (c === "{") depth++;
          else if (c === "}") depth--;
          k++;
        }
        const expr = body.slice(j + 2, k - 1).replace(/\s+/g, " ").trim();
        out.push(expr);
        j = k - 1;
      }
    }
    i = end;
  }
  return out;
}

/** null when the sink is fine, otherwise why not. */
export function judge(file, target, rhs) {
  const flat = rhs.replace(/\s+/g, " ").trim();
  if (/^(""|''|``)$/.test(flat)) return null;
  if (/^(["'`])(?:(?!\1)[^\\$]|\\.)*\1$/.test(flat)) return null; // a constant
  if (/^renderMarkdown\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)$/.test(flat)) return null;
  const site = SAFE_SITES.find((s) => s.file === file && s.target === target && s.rhs.test(flat));
  if (!site) return "not built from escapeHtml, renderMarkdown or a constant, and not in SAFE_SITES";
  for (const e of interpolations(rhs)) {
    if (/^(escapeHtml|renderMarkdown)\(/.test(e) || site.exprs.includes(e)) continue;
    return `interpolates \`${e}\`, which is not escapeHtml(...), renderMarkdown(...) or listed for this site`;
  }
  return null;
}

const problems = [];
let seen = 0;
for (const f of readdirSync(SRC).filter((n) => n.endsWith(".js"))) {
  const src = readFileSync(join(SRC, f), "utf8");
  for (const m of src.matchAll(SINK)) {
    const before = src.slice(0, m.index);
    const lineStart = before.lastIndexOf("\n") + 1;
    // A sink named inside a comment line is not a sink.
    if (/^\s*(\/\/|\*|\/\*)/.test(src.slice(lineStart, m.index + 1))) continue;
    const isAssign = m[0].endsWith("=");
    const targetStart = Math.max(before.search(/[A-Za-z_$][\w$.]*$/), 0);
    const target = (before.slice(targetStart) + m[0])
      .replace(/\s*\+?=$/, "")
      .replace(/\s*\($/, "");
    const rest = statementFrom(src, m.index + m[0].length);
    seen++;
    const why = isAssign
      ? judge(f, target, rest)
      : "a call-style HTML sink; add it to SAFE_SITES only after review";
    if (why) problems.push(`${f}: ${target} - ${why}`);
  }
}
assert.ok(seen >= 8, `expected to find the known sinks, found ${seen} (scanner broken?)`);
assert.deepEqual(problems, [], "an HTML sink is fed something that is not escaped");

// The judge itself: a model's text going straight in must fail.
assert.ok(judge("x.js", "el.innerHTML", "modelText"));
assert.ok(judge("x.js", "el.innerHTML", "`<p>${answer}</p>`"));
assert.ok(judge("x.js", "el.innerHTML", "`<p>${escapeHtml(answer)}</p>`"), "unlisted site fails until reviewed");
assert.equal(judge("x.js", "el.innerHTML", "renderMarkdown(text)"), null);
assert.equal(judge("x.js", "el.innerHTML", '""'), null);
assert.equal(judge("x.js", "el.innerHTML", "'<b>static</b>'"), null);
assert.ok(judge("x.js", "el.innerHTML", "renderMarkdown(a) + b"));
// A listed site with an unescaped piece added still fails.
assert.ok(judge("main.js", "code.innerHTML", "html + userText"));
assert.ok(judge("main.js", "dom.previousAnswerBody.innerHTML", "pairs.map((p) => `<p>${p.answer}</p>`).join(\"\")"));
console.log(`ok: ${seen} HTML sinks checked, all fed escaped text or constants`);
