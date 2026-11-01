/*
 * Build script for the Jarvis notes bridge plugin.
 *
 * The file Obsidian loads is `main.js`: one CommonJS bundle of `src/main.ts`
 * with `obsidian` (and the editor packages it pulls in) left external, because
 * Obsidian supplies them at runtime.
 *
 *   node esbuild.config.mjs            one production build, then exit
 *   node esbuild.config.mjs --watch    rebuild on every source change
 *
 * Why this spawns the esbuild command-line program instead of importing
 * esbuild's JavaScript API: the API starts a helper process with piped stdio,
 * and this repository's sandbox refuses named pipes (Node reports `EPERM` from
 * `spawn`). The command-line program is run with inherited stdio, which works
 * in the sandbox and is exactly what `npm run build` used in the spike.
 */
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const esbuildPackage = require.resolve("esbuild"); // .../node_modules/esbuild/lib/main.js
const esbuildBin = resolve(dirname(esbuildPackage), "..", "bin", "esbuild");

const watch = process.argv.includes("--watch");

const args = [
  "src/main.ts",
  "--bundle",
  "--format=cjs",
  "--target=es2018",
  "--platform=browser",
  "--external:obsidian",
  "--external:electron",
  "--external:@codemirror/*",
  "--external:@lezer/*",
  "--outfile=main.js",
  "--log-level=info",
  "--banner:js=/* Jarvis notes bridge - generated bundle. Source: obsidian-plugin/src/ */",
];

if (watch) args.push("--watch");

const result = spawnSync(process.execPath, [esbuildBin, ...args], {
  stdio: "inherit",
});

if (result.error) {
  console.error("Jarvis notes bridge: could not start esbuild:", result.error.message);
  process.exit(1);
}
process.exit(result.status === null ? 1 : result.status);
