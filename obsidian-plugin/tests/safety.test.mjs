/*
 * Safety invariants, proved against the plugin's own source text.
 *
 * This is a source-text test on purpose: the plugin runs inside Obsidian, so
 * the things that must NOT be there (an approval call, a vault write, a log
 * line, a second network door) are best checked where they would be written.
 *
 * Comments are stripped before scanning. Several files explain the rule in
 * prose ("no /api/approve", "similar to fetch()"), and a prose mention is not
 * a call; the scanner keeps every string literal and every code character, so
 * a real call or a real route string still fails, with its file and line.
 *
 * The scan is deliberately one-directional: it proves absence, so a file that
 * is missing is a hard failure, never a silent pass.
 *
 * No build step: the route table is imported from `src/protocol.ts` directly
 * (Node 22.18+ strips the TypeScript types).
 * Run:          node --test tests/safety.test.mjs
 */
import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testsDir = dirname(fileURLToPath(import.meta.url));
const pluginDir = resolve(testsDir, "..");
const srcDir = resolve(pluginDir, "src");

/** Every file the safety proof covers. A missing one fails loudly below. */
const SOURCE_FILES = [
  "main.ts",
  "client.ts",
  "panel.ts",
  "settings.ts",
  "modals.ts",
  "protocol.ts",
  "templates.ts",
];

/** The only route paths the plugin may use. */
const ALLOWED_ROUTES = new Set([
  "/api/chat",
  "/api/notes/capture",
  "/api/notes/read",
  "/api/notes/templates",
  "/api/notes/insert",
  "/api/notes/format",
  "/api/notes/replace",
  "/api/notes/customize",
  "/api/notes/tag",
  "/api/notes/create",
  "/api/notes/change",
]);

/**
 * Blank out `//` and block comments, keeping every other character (and every
 * newline) so line numbers still point at the real file. String and template
 * literals are copied through untouched, so `"http://..."` is not a comment
 * and a banned word inside a string is still found.
 */
function stripComments(source) {
  const out = [];
  let index = 0;
  let mode = "code"; // code | line | block | single | double | template
  const braceDepth = []; // one entry per open ${ ... } in a template literal
  while (index < source.length) {
    const ch = source[index];
    const next = source[index + 1];

    if (mode === "line") {
      if (ch === "\n") {
        mode = "code";
        out.push("\n");
      } else {
        out.push(" ");
      }
      index += 1;
      continue;
    }

    if (mode === "block") {
      if (ch === "*" && next === "/") {
        out.push("  ");
        index += 2;
        mode = "code";
        continue;
      }
      out.push(ch === "\n" ? "\n" : " ");
      index += 1;
      continue;
    }

    if (mode === "single" || mode === "double") {
      out.push(ch);
      if (ch === "\\" && index + 1 < source.length) {
        out.push(source[index + 1] === "\n" ? "\n" : source[index + 1]);
        index += 2;
        continue;
      }
      if ((mode === "single" && ch === "'") || (mode === "double" && ch === '"')) {
        mode = "code";
      }
      index += 1;
      continue;
    }

    if (mode === "template") {
      out.push(ch);
      if (ch === "\\" && index + 1 < source.length) {
        out.push(source[index + 1] === "\n" ? "\n" : source[index + 1]);
        index += 2;
        continue;
      }
      if (ch === "`") {
        mode = "code";
        index += 1;
        continue;
      }
      if (ch === "$" && next === "{") {
        out.push("{");
        braceDepth.push(0);
        mode = "code";
        index += 2;
        continue;
      }
      index += 1;
      continue;
    }

    // mode === "code"
    if (ch === "/" && next === "/") {
      out.push("  ");
      mode = "line";
      index += 2;
      continue;
    }
    if (ch === "/" && next === "*") {
      out.push("  ");
      mode = "block";
      index += 2;
      continue;
    }
    if (ch === "'") {
      out.push(ch);
      mode = "single";
      index += 1;
      continue;
    }
    if (ch === '"') {
      out.push(ch);
      mode = "double";
      index += 1;
      continue;
    }
    if (ch === "`") {
      out.push(ch);
      mode = "template";
      index += 1;
      continue;
    }
    if (braceDepth.length) {
      const last = braceDepth.length - 1;
      if (ch === "{") {
        braceDepth[last] += 1;
      } else if (ch === "}") {
        if (braceDepth[last] === 0) {
          braceDepth.pop();
          mode = "template";
          out.push(ch);
          index += 1;
          continue;
        }
        braceDepth[last] -= 1;
      }
    }
    out.push(ch);
    index += 1;
  }
  return out.join("");
}

let cache = null;

/**
 * Read every source once. `code` is the comment-stripped text; `lines` are the
 * real file's lines, so a failure prints the line a reader can open.
 */
function sources() {
  if (cache) return cache;
  const missing = SOURCE_FILES.filter((name) => !existsSync(resolve(srcDir, name)));
  assert.deepEqual(
    missing,
    [],
    "the safety proof needs every plugin source file, and these are missing: " +
      missing.join(", ") +
      ". This test runs after the Lead writes the plugin sources; src/ is not ours to edit.",
  );
  cache = SOURCE_FILES.map((name) => {
    const file = resolve(srcDir, name);
    const raw = readFileSync(file, "utf8");
    return {
      name,
      file,
      raw,
      code: stripComments(raw),
      lines: raw.split(/\r?\n/),
    };
  });
  return cache;
}

/** file:line: text for one index into the stripped code. */
function where(source, codeIndex) {
  const line = source.code.slice(0, codeIndex).split("\n").length;
  return source.name + ":" + line + ": " + (source.lines[line - 1] ?? "").trim();
}

function report(hits, why) {
  assert.equal(hits.length, 0, why + "\nOffending source lines:\n" + hits.join("\n"));
}

/** No occurrence of an exact string in the plugin's code. */
function assertNoText(files, needle, why) {
  const hits = [];
  for (const source of files) {
    let index = source.code.indexOf(needle);
    while (index !== -1) {
      hits.push(where(source, index));
      index = source.code.indexOf(needle, index + needle.length);
    }
  }
  report([...new Set(hits)], why);
}

/** No match of a regular expression (must carry the `g` flag) in code. */
function assertNoPattern(files, pattern, why) {
  const hits = [];
  for (const source of files) {
    const regex = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g");
    for (const match of source.code.matchAll(regex)) {
      hits.push(where(source, match.index));
    }
  }
  report([...new Set(hits)], why);
}

/** The code must contain a match, or the safety proof is checking nothing. */
function assertHasPattern(files, pattern, why) {
  const hits = [];
  for (const source of files) {
    const regex = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g");
    for (const match of source.code.matchAll(regex)) {
      hits.push(where(source, match.index));
    }
  }
  assert.ok(hits.length > 0, why + "\nFound none in: " + files.map((file) => file.name).join(", "));
  return hits;
}

describe("safety: cards are answered nowhere but Jarvis", () => {
  test("no /api/approve or /api/deny call exists in src/", () => {
    const files = sources();
    assertNoText(files, "/api/approve", "the plugin must never call /api/approve: a card is approved in Jarvis only");
    assertNoText(files, "/api/deny", "the plugin must never call /api/deny: a card is denied in Jarvis only");
    // The proof is only worth something if the routes that DO exist are there.
    assertHasPattern(files, /ROUTES\.(insert|format|replace|customize|tag|create|change)\b/, "the plugin's writes must go through ROUTES");
  });
});

describe("safety: the vault is never written", () => {
  test("no vault write API is called", () => {
    const files = sources();
    for (const banned of [
      "vault.modify",
      "vault.process",
      "vault.create",
      "vault.append",
      "vault.delete",
      "adapter.write",
      "adapter.append",
      "fileManager.processFrontMatter",
      "processFrontMatter",
    ]) {
      assertNoText(files, banned, "the plugin must never write the vault, and " + banned + " is a vault write");
    }
  });

  test("no editor write method is called", () => {
    const files = sources();
    // main.ts's own header promises this; an editor write would change a note
    // without Jarvis, its card, or its undo.
    for (const banned of ["editor.replaceSelection", "editor.replaceRange", "editor.insertText"]) {
      assertNoText(files, banned, "the plugin must never edit the open note itself (" + banned + ")");
    }
    // It may still READ the selection, or this test would be checking a plugin
    // that cannot do its job.
    assertHasPattern(files, /editor\.getSelection\(|editor\.getLine\(/, "the plugin must still read the selection read-only");
  });

  test("reads are still allowed, so the plugin is not stranded", () => {
    const files = sources();
    assertHasPattern(files, /vault\.(cachedRead|read|getAbstractFileByPath)\(|vault\.getMarkdownFiles\(/, "the plugin reads the vault read-only");
  });
});

describe("safety: nothing calls out through another door", () => {
  test("no obsidian:// URI is built", () => {
    assertNoText(sources(), "obsidian://", "the plugin must never open an obsidian:// URI");
  });

  test("the only network call is requestUrl", () => {
    const files = sources();
    assertNoPattern(files, /\bfetch\s*\(/, "the only network call may be Obsidian's requestUrl; fetch( is banned");
    assertNoPattern(files, /\bXMLHttpRequest\b/, "no XMLHttpRequest: the only network call may be requestUrl");
    assertNoPattern(files, /\bWebSocket\b/, "no WebSocket: the only network call may be requestUrl");
    assertNoPattern(files, /\bsendBeacon\b/, "no sendBeacon: the only network call may be requestUrl");
    assertHasPattern(files, /requestUrl/, "the plugin's one network door must be requestUrl");
  });
});

describe("safety: nothing is logged, so nothing can leak", () => {
  test("no console.log / console.debug / console.info exists", () => {
    const files = sources();
    for (const banned of ["console.log(", "console.debug(", "console.info("]) {
      assertNoText(files, banned, "nothing may be logged (" + banned + "), so the token cannot reach a log");
    }
  });

  test("no console call of any kind exists (the token must never be printed)", () => {
    // The task's token-in-a-log rule reduces to this: there is no log call at
    // all, so no template literal, concatenation or value can be logged.
    assertNoPattern(sources(), /\bconsole\s*\./, "no console call of any kind may exist in src/");
  });
});

describe("safety: the standing headers are sent", () => {
  test("protocol.ts sends X-Jarvis-Client: hud and X-Jarvis-Surface: desktop", () => {
    const files = sources();
    const protocol = files.filter((file) => file.name === "protocol.ts");
    assertHasPattern(protocol, /["']X-Jarvis-Client["']\s*:\s*["']hud["']/, "X-Jarvis-Client must be sent as hud");
    assertHasPattern(protocol, /["']X-Jarvis-Surface["']\s*:\s*["']desktop["']/, "X-Jarvis-Surface must be sent as desktop");
    assertHasPattern(protocol, /["']X-Jarvis-Token["']/, "the token must travel as X-Jarvis-Token");
  });
});

describe("safety: the only routes are /api/chat and /api/notes/...", () => {
  test("every route in ROUTES is an allowed route", async () => {
    const { ROUTES } = await import("../src/protocol.ts");
    const entries = Object.entries(ROUTES);
    assert.ok(entries.length > 0, "ROUTES must not be empty");
    for (const [name, route] of entries) {
      assert.ok(
        typeof route === "string" && route.startsWith("/api/"),
        "ROUTES." + name + " is not a route path: " + JSON.stringify(route),
      );
      assert.ok(ALLOWED_ROUTES.has(route), "ROUTES." + name + " = " + route + " is not an allowed route");
    }
  });

  test("no route outside the allowed list appears anywhere in src/", () => {
    const files = sources();
    const hits = [];
    const routePattern = /\/api\/[A-Za-z0-9_\/-]*/g;
    for (const source of files) {
      for (const match of source.code.matchAll(routePattern)) {
        const route = match[0];
        if (!ALLOWED_ROUTES.has(route)) {
          hits.push(source.name + ": " + route + "  <- " + where(source, match.index));
        }
      }
    }
    report(
      [...new Set(hits)],
      "only /api/chat and the /api/notes/... routes may appear in src/ " +
        "(allowed: " + [...ALLOWED_ROUTES].join(", ") + ")",
    );
  });

  test("no double-quoted route string outside the allowed list appears in src/", () => {
    const files = sources();
    const hits = [];
    for (const source of files) {
      for (const match of source.code.matchAll(/"(\/api\/[^"]*)"/g)) {
        if (!ALLOWED_ROUTES.has(match[1])) {
          hits.push(source.name + ": \"" + match[1] + "\"  <- " + where(source, match.index));
        }
      }
    }
    report([...new Set(hits)], "a quoted route string names a route outside the allowed list");
  });
});
