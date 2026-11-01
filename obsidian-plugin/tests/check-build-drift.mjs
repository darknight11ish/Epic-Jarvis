/*
 * Build-drift check: the committed `main.js` must be EXACTLY the build of
 * `src/`. The bundle is committed on purpose, so the owner can copy the plugin
 * folder without installing Node or running a build - which means a `src/`
 * change that forgets to rebuild would ship a stale plugin. This check rebuilds
 * the bundle and fails if the file changes at all.
 *
 *   npm run check:build-drift        (or: node tests/check-build-drift.mjs)
 *
 * Why it spawns `node esbuild.config.mjs` instead of importing esbuild: this
 * repository's sandbox refuses the named pipes esbuild's JavaScript API uses
 * (`spawn EPERM`), and `esbuild.config.mjs` already spawns the command-line
 * program with inherited stdio, which works everywhere the plugin is built.
 *
 * Exit codes: 0 = no drift; 1 = build failed or the bundle changed.
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testsDir = dirname(fileURLToPath(import.meta.url));
const pluginDir = resolve(testsDir, "..");
const bundlePath = resolve(pluginDir, "main.js");
const buildScript = resolve(pluginDir, "esbuild.config.mjs");

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

let before;
try {
  before = sha256(bundlePath);
} catch (error) {
  console.error(
    "BUILD-DRIFT CHECK FAILED: cannot read the committed bundle " + bundlePath + " (" + error.message + ")",
  );
  process.exit(1);
}

console.log("Build-drift check: rebuilding main.js to prove it is the build of src/ ...");
const build = spawnSync(process.execPath, [buildScript], {
  cwd: pluginDir,
  stdio: "inherit",
});
if (build.error) {
  console.error("BUILD-DRIFT CHECK FAILED: could not start the build (" + build.error.message + ")");
  process.exit(1);
}
if (build.status !== 0) {
  console.error("BUILD-DRIFT CHECK FAILED: the build itself failed (exit " + build.status + ")");
  process.exit(1);
}

const after = sha256(bundlePath);
if (after !== before) {
  console.error("");
  console.error("BUILD-DRIFT CHECK FAILED: obsidian-plugin/main.js is not the build of src/.");
  console.error("  committed before: " + before);
  console.error("  rebuilt now:      " + after);
  console.error("");
  console.error("Run `npm run build` in obsidian-plugin\\ and commit the rebuilt main.js");
  console.error("together with the source change that produced it. Do NOT hand-edit main.js.");
  process.exit(1);
}

console.log("Build-drift check OK: main.js is byte-identical after a fresh build (" + after + ").");
