/**
 * preflight-panel.mjs - holds the Settings "Check my setup" panel to its shape.
 *
 *     node tests/preflight-panel.mjs
 *
 * Runs on plain Node, no browser: it reads the page and the panel's own script
 * as TEXT, the same way settings-catalogue.mjs holds the switch rows. What it
 * cannot see is the drawing itself, so it holds the things that WOULD be lost
 * silently: the card and its script tag, every element the panel writes into,
 * the two folders, the verdict and the failing lines, Copy being the same text
 * the page shows, the words that say it changes nothing - and that the panel's
 * CODE never mentions a pairing token (the checker reads it itself, and
 * preflight.rs's own test holds the Rust half of that claim).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const page = readFileSync(join(here, "..", "src", "settings.html"), "utf8");
const raw = readFileSync(join(here, "..", "src", "preflight-settings.js"), "utf8");
// The claims below are about CODE, not prose: a comment that explains why the
// panel never touches a token must not count as the panel touching one.
const code = raw
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

let failed = 0;
function check(name, ok, detail = "") {
  if (ok) console.log("ok   " + name);
  else {
    failed += 1;
    console.log("FAIL " + name + (detail ? "\n     " + detail : ""));
  }
}

check("the Settings page has the card", page.includes('id="preflight"'));
check("...and loads the panel's script", page.includes('src="preflight-settings.js"'));
check(
  "the button, the state and every field it writes into are on the page",
  ["pf-run", "pf-state", "pf-ran-from", "pf-checked", "pf-summary", "pf-lines", "pf-copy"]
    .every((id) => page.includes(`id="${id}"`)),
  ["pf-run", "pf-state", "pf-ran-from", "pf-checked", "pf-summary", "pf-lines", "pf-copy"]
    .filter((id) => !page.includes(`id="${id}"`)),
);
check(
  "the page says out loud that it is read-only",
  /Read-only/.test(page) && /approves nothing/.test(page),
);
check("the panel asks the Rust command by name", code.includes('invoke("check_my_setup")'));
check(
  "...and draws the verdict line AND the failing lines",
  code.includes("function summaryLine") && code.includes("function failingLines")
    && /FAIL\|WARN/.test(code),
);
check(
  "...and both folders, the one it ran from and the one it checked",
  code.includes("ran_from") && code.includes("checked"),
);
check(
  "Copy is the same text the page shows, not a second rendering",
  code.includes("function panelText") && /writeText\(panelText\(/.test(code),
);
check(
  "...including the lines that failed, so it can be pasted without retyping",
  /failing\.join/.test(code),
);
check("nothing in the panel's code touches a pairing token", !/token/i.test(code));
check(
  "and the folder it ran from is shown even when nothing ran",
  /ran_from/.test(code) && /why/.test(code),
);

console.log(`\n${failed} failed`);
process.exit(failed ? 1 : 0);
