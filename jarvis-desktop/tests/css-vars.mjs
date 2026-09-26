// Every CSS variable a window uses must be defined somewhere that window
// loads. No browser needed.
//
// Why: Settings, the widget and Brain used --surface-raised, --hairline and
// --hairline-strong, which only style.css (the Jarvis bar's sheet) defines.
// Those windows never load style.css, so the values were empty: disabled
// buttons and the Settings hotkey boxes drew see-through. tokens.mjs and
// themecheck.mjs both passed, because neither asks "is this name defined in
// THIS window?" (UI audit, 2026-09-26).
//
// A var() with a fallback - var(--x, 1px) - is allowed to be undefined, and so
// is a name the window's own scripts set at run time.
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const read = (f) => readFileSync(join(SRC, f), "utf8");
const noComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, "");

let failed = 0;
for (const html of readdirSync(SRC).filter((f) => f.endsWith(".html")).sort()) {
  const page = read(html);
  const sheets = [...page.matchAll(/href="([^"]+\.css)"/g)]
    .map((m) => m[1])
    .filter((f) => existsSync(join(SRC, f)))
    .map(read);
  const inline = [...page.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]);
  const css = noComments([...sheets, ...inline].join("\n"));
  const scripts = [...page.matchAll(/src="([^"]+\.js)"/g)]
    .map((m) => m[1])
    .filter((f) => existsSync(join(SRC, f)))
    .map(read)
    .join("\n") + page;
  const defined = new Set([...css.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
  const setByScript = new Set([...scripts.matchAll(/["'`](--[\w-]+)["'`]/g)].map((m) => m[1]));
  const used = new Set([...css.matchAll(/var\(\s*(--[\w-]+)\s*\)/g)].map((m) => m[1]));
  const missing = [...used].filter((n) => !defined.has(n) && !setByScript.has(n)).sort();
  if (missing.length) {
    failed++;
    console.log(`FAIL ${html}: uses ${missing.join(", ")} but nothing it loads defines them`);
  } else {
    console.log(`ok   ${html}: every CSS variable it uses is defined`);
  }
}
process.exit(failed ? 1 : 0);
