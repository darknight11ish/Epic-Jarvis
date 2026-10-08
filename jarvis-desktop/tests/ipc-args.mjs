/**
 * The argument names of the app's IPC calls.
 *
 * WHY THIS SUITE EXISTS (click audit, 2026-10-08). Tauri renames a command's
 * arguments at the IPC boundary: a plain `#[tauri::command]` gets
 * `ArgumentCase::Camel` (tauri-macros' wrapper.rs, the default) and
 * `key.to_lower_camel_case()` is applied to every key, so a Rust argument named
 * `valid_to` is read from the key `validTo`. A key Tauri does not recognise is
 * not an error: for an `Option<T>` argument it deserializes to `None`
 * (tauri's ipc/command.rs, `None => visitor.visit_none()`).
 *
 * Two real bugs came from that, and both were invisible because the test
 * harnesses record the payload the page SENDS, not the key the Rust READS:
 *
 *   - brain.js sent `valid_to` to Forget and Reword, so the date the owner
 *     typed into "When did this actually stop being true?" was dropped and the
 *     fact was retired as of now;
 *   - jarvis-link.js sent `option_id` to decide_approval, so the deliberate
 *     refusal for "approve one option out of several" could never fire.
 *
 * So this suite reads the sources and fails on the shapes that get dropped. It
 * needs no browser and no backend: it is a naming rule, and the rule is the
 * whole check.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");
const RUST = join(ROOT, "src-tauri", "src");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** Every .js under src/, with its text. */
function jsFiles() {
  const out = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) { walk(p); continue; }
      if (name.endsWith(".js")) out.push(p);
    }
  };
  walk(SRC);
  return out;
}

/** An IPC argument key in snake_case: `some_thing:` or `args.some_thing =`. */
const SNAKE_ASSIGN = /\bargs\.([a-z][a-z0-9]*_[a-z0-9_]+)\s*=/g;
const SNAKE_KEY = /(^|[{,\s])([a-z][a-z0-9]*_[a-z0-9_]+)\s*:/g;

check("no invoke payload is built with a snake_case key (`args.some_thing = ...`)", () => {
  const offenders = [];
  for (const file of jsFiles()) {
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(SNAKE_ASSIGN)) {
      const line = text.slice(0, m.index).split("\n").length;
      offenders.push(`${file.slice(SRC.length + 1)}:${line} sets args.${m[1]}`);
    }
  }
  assert.deepEqual(offenders, [],
    `Tauri reads these as camelCase, so the key is dropped with no error:\n      ${offenders.join("\n      ")}`);
});

check("no object literal handed straight to `invoke(...)` uses a snake_case key", () => {
  const offenders = [];
  for (const file of jsFiles()) {
    const text = readFileSync(file, "utf8");
    for (const call of text.matchAll(/invoke(?:Strict)?\(\s*["'`]([a-z0-9_]+)["'`]\s*,\s*\{/g)) {
      // Take the balanced braces of that second argument.
      let depth = 0, i = call.index + call[0].length - 1, end = -1;
      for (; i < text.length; i++) {
        if (text[i] === "{") depth++;
        else if (text[i] === "}") { depth--; if (depth === 0) { end = i; break; } }
      }
      if (end < 0) continue;
      const body = text.slice(call.index + call[0].length - 1, end + 1);
      for (const key of body.matchAll(SNAKE_KEY)) {
        const line = text.slice(0, call.index).split("\n").length;
        offenders.push(`${file.slice(SRC.length + 1)}:${line} ${call[1]} got key \`${key[2]}\``);
      }
    }
  }
  assert.deepEqual(offenders, [],
    `Tauri reads these as camelCase, so the key is dropped with no error:\n      ${offenders.join("\n      ")}`);
});

check("the Rust side really does rename: a plain #[tauri::command] is camelCase", () => {
  // The check above is only true while the macro default holds, and while no
  // command opts into snake_case. Both are pinned here so the rule cannot rot
  // silently into a false alarm - or a missed one.
  const rust = readdirSync(RUST).filter((f) => f.endsWith(".rs"))
    .map((f) => readFileSync(join(RUST, f), "utf8")).join("\n");
  const snake = [...rust.matchAll(/#\[tauri::command\(([^)]*rename_all\s*=\s*"snake_case"[^)]*)\)\]/g)];
  assert.deepEqual(snake.map((m) => m[1]), [],
    "a command opted into snake_case: the JS keys for it must be snake_case too");
  // And the two commands this suite was written for still take those arguments,
  // so the keys checked above are the keys they need.
  const brain = readFileSync(join(RUST, "brain.rs"), "utf8");
  assert.match(brain, /valid_to:\s*Option<f64>/, "brain.rs no longer takes valid_to");
  const commands = readFileSync(join(RUST, "commands.rs"), "utf8");
  assert.match(commands, /option_id:\s*Option<String>/, "decide_approval no longer takes option_id");
});

check("the two fixed call sites send the camelCase key", () => {
  const brain = readFileSync(join(SRC, "brain.js"), "utf8");
  assert.equal((brain.match(/args\.validTo\s*=/g) || []).length, 2,
    "Forget and Reword must both send validTo");
  assert.ok(!/args\.valid_to\s*=/.test(brain), "brain.js still sets the dropped key");
  const link = readFileSync(join(SRC, "jarvis-link.js"), "utf8");
  assert.match(link, /args\.optionId\s*=/);
  assert.ok(!/args\.option_id\s*=/.test(link), "jarvis-link.js still sets the dropped key");
});

console.log(fails.length ? `\n${fails.length} FAILED` : "\nevery IPC argument key is one Tauri will read");
process.exit(fails.length ? 1 : 0);
