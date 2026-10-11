/**
 * Builds `jarvis-desktop/src-old/` for `tests/poll-hygiene-measure.mjs`: a copy
 * of `src/` with the three files the poll-hygiene fix changed put back to
 * their HEAD versions, and the two files it added removed. Serving that
 * directory gives the measurement a true BEFORE side through the same harness.
 *
 *   node tests/make-before-overlay.mjs
 *
 * Scratch only - `src-old/` is not imported by anything and can be deleted.
 */
import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));       // jarvis-desktop/tests
const APP = join(HERE, "..");                              // jarvis-desktop
const SRC = join(APP, "src");
const OLD = join(APP, "src-old");

rmSync(OLD, { recursive: true, force: true });
cpSync(SRC, OLD, { recursive: true });

for (const f of ["main.js", "widget.js", "devices.js"]) {
  const text = execFileSync("git", ["show", `HEAD:jarvis-desktop/src/${f}`], {
    cwd: join(APP, ".."), encoding: "utf8", maxBuffer: 32 * 1024 * 1024,
  });
  writeFileSync(join(OLD, f), text, "utf8");
}
// The two new files did not exist at HEAD; removing them keeps the BEFORE side
// from accidentally loading the fix.
for (const f of ["clock-timer.js", "devices-pair-poll.js"]) rmSync(join(OLD, f), { force: true });
console.log(`before-overlay ready: ${OLD}`);
