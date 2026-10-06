/**
 * Finding Python, and saying so when it is not there.
 *
 * Several suites run the REAL backend modules to produce what they check the
 * page against, rather than a fixture this repository wrote by hand. That
 * means running an interpreter, and "the interpreter" is not one thing:
 *
 *   - Linux and CI name it `python3`;
 *   - the owner's Windows PC has Python 3.12 as `python`, and has no
 *     `python3` at all.
 *
 * Until now each suite ran `execFileSync("python3", …)` and dealt with the
 * missing binary its own way. Two of them did not deal with it at all: the
 * exception came from `execFileSync` during the check, escaped the `check()`
 * wrapper, and killed the whole suite part-way through - taking every later
 * check with it. `memory.mjs` died this way at check 15 and `voice-training.mjs`
 * at check 34, so everything after those lines had never run on Windows.
 *
 * The rule this module exists to enforce:
 *
 *   A check this machine cannot run must SAY SO and be counted as SKIPPED.
 *   It must never crash the suite, and it must never print as a pass.
 *
 * So: resolve the interpreter once (`python3` if it exists, else `python`),
 * never scatter `process.platform === "win32" ? … : …` through the suites,
 * and give every skip a real line and a counter so a skipped suite cannot
 * quietly look like a green one.
 *
 * This file lives in `tests/lib/` on purpose. CI runs every `tests/*.mjs` as
 * a suite, so a helper sitting directly in `tests/` would be executed as a
 * test that never prints anything - the very "test that lies" shape this
 * whole pass is about. A subdirectory is not matched by that glob.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, join, resolve } from "node:path";

/**
 * Is `name` a program this machine can actually start?
 *
 * `__dirname`/`__filename` are not in scope in an ES module, so this is the
 * PATH walk by hand. `PATHEXT` is honoured because on Windows an executable is
 * `python.EXE`, and a bare PATH entry does not exist under its plain name.
 */
export function toolOnPath(name) {
  const exts = process.platform === "win32"
    ? (process.env.PATHEXT || ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)
    : [""];
  for (const dir of (process.env.PATH || "").split(delimiter)) {
    if (!dir) continue;
    for (const ext of exts) {
      try {
        if (existsSync(join(dir, name + ext))) return true;
      } catch { /* an unreadable PATH entry is not this program */ }
    }
  }
  return false;
}

/** `python3` where it exists (Linux, CI), else `python` (the owner's PC). */
export function findPython() {
  for (const name of ["python3", "python"]) if (toolOnPath(name)) return name;
  return null;
}

/**
 * Thrown by `skip()` so the check wrapper stops running the body at once.
 *
 * It has to be a throw rather than a plain return for two reasons. A body that
 * merely returns early still runs under the wrapper, which then prints `ok`
 * for a check that never ran - a skip printed as a pass, the exact lie this
 * pass exists to remove. And a check that reads a module-scope fixture
 * (`OFFER.title` where the fixture is `null` with no interpreter) blows up at
 * a point no guard can reach, which is the crash being fixed, only moved.
 *
 * Each suite's wrapper recognises this class and records a skip, not a
 * failure.
 */
export class Skip extends Error {
  constructor(what, why) {
    super(why);
    this.name = "Skip";
    this.what = what;
    this.why = why;
  }
}

/**
 * An interpreter helper for one suite.
 *
 * @param {string} backendDir  absolute path to the repository's `backend/`
 * @returns {{
 *   cmd: string|null,
 *   have: boolean,
 *   skipped: () => number,
 *   ran: () => number,
 *   noteRan: () => void,
 *   caught: (name: string, error: any) => boolean,
 *   skip: (what: string, why?: string) => never,
 *   summary: () => string,
 *   run: (code: string, opts?: object) => any,
 * }}
 */
export function pythonFor(backendDir) {
  const cmd = findPython();
  const backend = resolve(backendDir);
  let skipped = 0;
  let ran = 0;
  /** Why each check was skipped. A suite can skip for more than one reason -
   *  faces.mjs also skips when glslangValidator is absent - and printing "no
   *  Python" for that would be a small lie of exactly the kind being fixed. */
  const reasons = new Set();

  /** Where the backend's modules are importable from, absolute so it does not
   *  depend on the child's cwd, and joined with the platform's separator (a
   *  `:`-joined list is one long nonsense path on Windows). */
  const pythonPath = [join(backend, "rebuilt"), backend].join(delimiter);

  const api = {
    cmd,
    have: cmd !== null,

    /** Records one skipped check and stops the body. Counted by `summary()`
     *  and printed once by the wrapper's `caught()` - so a suite that skipped
     *  work cannot read as a green one, and a skip never prints as an `ok`. */
    skip(what, why) {
      skipped += 1;
      const reason = why || `no Python here - ${cmd || "python3"} was not found on PATH`;
      reasons.add(reason);
      throw new Skip(what, reason);
    },

    /** How many checks have been skipped so far. */
    skipped: () => skipped,

    /** How many checks ran to the end (the wrapper calls this on success, so
     *  a check that failed or was skipped is not counted). */
    ran: () => ran,
    noteRan: () => { ran += 1; },

    /**
     * The `check` wrapper's shared tail: recognise a skip thrown by `skip()`,
     * count it, and print it as a skip - never "ok", never "FAIL". Returns
     * true when the error was a skip and the wrapper should stop.
     */
    caught: (name, error) => {
      if (!(error instanceof Skip)) return false;
      console.log(`SKIP  ${name}`);
      console.log(`      (${error.why})`);
      return true;
    },

    /** The lines to print before the suite's own verdict. Empty when nothing
     *  was skipped, so a complete run looks exactly as it did before. The
     *  counts are in the shape the other desktop suites use (`browser-engine.mjs`
     *  prints "N passed, N failed"), with skips called out beside them and
     *  every reason named, so a skip can never read as a pass and can never be
     *  blamed on the wrong missing thing. */
    summary: () => (skipped === 0 ? ""
      : `\n${ran} passed, ${skipped} skipped (a skip is not a pass):\n`
        + [...reasons].map((r) => `  - ${r}`).join("\n")),

    /**
     * Runs `code` with the interpreter found above and returns the parsed JSON
     * it printed. Used at module scope, before `check()` exists, so it returns
     * `null` rather than throwing when there is no interpreter - the checks
     * that need the result then say SKIP in their own words.
     */
    run(code, { env = {}, cwd = backend } = {}) {
      if (!cmd) return null;
      try {
        const out = execFileSync(cmd, ["-c", code], {
          cwd,
          env: {
            ...process.env,
            PYTHONPATH: pythonPath,
            // The backend defaults its config into the owner's real
            // %APPDATA%; a test must not write there.
            OPENJARVIS_CONFIG_DIR: mkdtempSync(join(tmpdir(), "jarvis-suite-")),
            ...env,
          },
          encoding: "utf8",
        });
        return JSON.parse(out);
      } catch (error) {
        if (error.code === "ENOENT") return null; // vanished between the check and the call
        throw error;
      }
    },
  };
  return api;
}
