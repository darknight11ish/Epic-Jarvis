"""The Review #8 zero-jargon scanner's own tests - hermetic, and they bite.

    python3 backend/test_zero_jargon.py        (registered through run_suites.py)

Review #8 of the 10-Review Playbook asks for an automated check of every
user-facing string for leaked developer words (taint/latch/FTS5/HTTP 500/None/
...) and for bare refusals that tell the owner neither what happened nor what
to do next. `tools/check_zero_jargon.py` is that check. These tests prove the
scanner itself before anyone trusts the list it makes:

  * a synthetic file with a planted ``Traceback`` in a user-facing message is
    FOUND, with the right path and line, and the baseline ratchet FAILS on it;
  * allowlisted technical words (``HTTPS``, ``PIN``, ``Tailscale``, model names,
    the phrase ``API key``) pass - while a bare ``API`` in the same sentence
    still fails, so the allowlist cannot swallow a real finding;
  * docstrings and comments are developer text and are not reported;
  * all four surfaces are scanned: a HUD JS literal, a Rust command error, an
    Android ``strings.xml`` value and a Compose/``Text`` literal each produce a
    finding on their own surface;
  * a bare ``"error": "Failed"`` is reported separately as a bare refusal,
    while ``"status": "denied"`` (an enum value, not a message) is not;
  * the machine-readable report is valid JSON with path:line, word and the
    string, and its counts agree with its findings;
  * a file that cannot be parsed is REPORTED, never silently skipped;
  * the REAL tree is measured against the committed baseline (the ratchet
    passes today) - it is never asserted to be zero, because the cleanup that
    lowers it is a separate piece of work.

Every check is a real condition: no ``check("...", True)`` here (the project's
vacuous-check rule), and the fixtures are written to a fresh temporary folder -
no mailbox, no network, no owner files.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "check_zero_jargon.py"
BASELINE = REPO / "docs" / "REVIEW-8-ZERO-JARGON-BASELINE-2026-10-23.json"

if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))
import check_zero_jargon as Z  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    print(f"skip  {why}")


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def scan(root: Path, allowlist: Path | None = None) -> dict:
    return Z.scan(root, allowlist or (root / "no-allowlist.txt"))


def write_baseline(root: Path, total: int, bare: int) -> Path:
    path = root / "baseline.json"
    path.write_text(json.dumps({"counts": {"total": total,
                                           "bare_refusals": bare}}),
                    encoding="utf-8")
    return path


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-B", str(TOOL), "--root", str(root), *args],
        cwd=str(REPO), capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace", env=env)


def findings_of(report: dict, surface: str | None = None) -> list:
    return [f for f in report["findings"]
            if surface is None or f["surface"] == surface]


def terms_of(report: dict) -> set:
    return {f["term"] for f in report["findings"]}


# ---------------------------------------------------------------------------


def t_a_planted_traceback_is_found_and_the_ratchet_fails():
    with tempfile.TemporaryDirectory(prefix="zj-traceback-") as tmp:
        root = Path(tmp)
        write(root, "backend/jarvis_fake.py",
              "def reply():\n"
              '    return {"error": "Traceback (most recent call last): boom"}\n')
        report = scan(root)
        hits = findings_of(report, "backend")
        hit = [f for f in hits if f["term"] == "traceback"]
        check("a planted Traceback in a user-facing message is FOUND",
              len(hit) == 1, report["counts"])
        check("... at the right file and line",
              hit and hit[0]["path"] == "backend/jarvis_fake.py"
              and hit[0]["line"] == 2, hit)
        baseline = write_baseline(root, 0, 0)
        proc = run(root, "--check", "--baseline", str(baseline))
        check("... and the baseline ratchet FAILS on it (exit 1)",
              proc.returncode == 1, (proc.returncode, proc.stdout[-600:]))
        check("... naming the finding, not just a number",
              "traceback" in proc.stdout.lower()
              and "MORE" in proc.stdout, proc.stdout[-600:])


def t_allowlisted_technical_words_pass():
    with tempfile.TemporaryDirectory(prefix="zj-allow-") as tmp:
        root = Path(tmp)
        write(root, "backend/jarvis_fake.py",
              "def reply():\n"
              '    return {"error": "Tailscale is not running. Open it, then press '
              'HTTPS settings and type your PIN."}\n'
              '    return {"note": "Ollama is not answering; start it, then retry."}\n')
        allow = root / "allow.txt"
        allow.write_text("Tailscale\nHTTPS\nPIN\nOllama\n", encoding="utf-8")
        report = scan(root, allow)
        check("allowlisted words (Tailscale/HTTPS/PIN/Ollama) are not findings",
              report["counts"]["total"] == 0,
              (report["counts"], findings_of(report)))
        baseline = write_baseline(root, 0, 0)
        proc = run(root, "--check", "--baseline", str(baseline),
                   "--allowlist", str(allow))
        check("... and the ratchet passes on them (exit 0)",
              proc.returncode == 0, (proc.returncode, proc.stdout[-500:]))


def t_an_allowlist_phrase_does_not_swallow_a_bare_term():
    with tempfile.TemporaryDirectory(prefix="zj-phrase-") as tmp:
        root = Path(tmp)
        write(root, "backend/jarvis_fake.py",
              "def reply():\n"
              '    return {"error": "Your API key is saved."}\n'
              '    return {"error": "The API is not answering."}\n')
        allow = root / "allow.txt"
        allow.write_text("API key\n", encoding="utf-8")
        report = scan(root, allow)
        api_hits = [f for f in findings_of(report) if f["term"] == "API"]
        check("the phrase 'API key' passes", report["counts"]["total"] == 1,
              report["counts"])
        check("... but a bare API in the same sentence still fails",
              len(api_hits) == 1 and api_hits[0]["line"] == 3, api_hits)


def t_docstrings_and_comments_are_not_user_facing():
    with tempfile.TemporaryDirectory(prefix="zj-docs-") as tmp:
        root = Path(tmp)
        write(root, "backend/jarvis_fake.py",
              '"""Traceback, taint, latch and None are internal words."""\n'
              "\n"
              "def helper():\n"
              '    """Return None; a traceback here is a bug."""\n'
              "    return 1\n")
        write(root, "jarvis-desktop/src/hud-demo.js",
              "// internal: a taint latch and a null payload\n"
              "const x = 1; /* HTTP 500 is handled above */\n")
        report = scan(root)
        check("a docstring's developer words are not findings",
              report["counts"]["total"] == 0,
              (report["counts"], findings_of(report)))


def t_each_surface_is_scanned():
    with tempfile.TemporaryDirectory(prefix="zj-surfaces-") as tmp:
        root = Path(tmp)
        write(root, "jarvis-desktop/src/hud-demo.js",
              'document.getElementById("x").textContent = '
              '"HTTP 500 from Jarvis";\n')
        write(root, "jarvis-desktop/src-tauri/src/commands.rs",
              "fn refuse() -> Result<(), String> {\n"
              '    Err(format!("payload missing"))\n'
              "}\n")
        write(root, "jarvis-client/app/src/main/res/values/strings.xml",
              '<resources><string name="bad">A traceback appeared</string></resources>\n')
        write(root, "jarvis-client/app/src/main/java/demo/Ui.kt",
              'Text("The daemon is not running")\n')
        report = scan(root)
        surfaces = {f["surface"] for f in report["findings"]}
        check("the HUD page's JS literals are scanned", "hud" in surfaces, surfaces)
        check("Rust command errors are scanned", "rust" in surfaces, surfaces)
        check("Android resource strings and Compose literals are scanned",
              "android" in surfaces, surfaces)
        check("the planted words were found on every surface",
              {"HTTP", "payload", "traceback", "daemon"} <= terms_of(report),
              sorted(terms_of(report)))
        per_surface = {}
        for f in report["findings"]:
            per_surface.setdefault(f["surface"], []).append(f["path"])
        check("... each finding names the file it came from",
              all(any(p.endswith(name) for p in paths)
                  for name, paths in (("hud-demo.js", per_surface.get("hud", [])),
                                      ("commands.rs", per_surface.get("rust", [])),
                                      ("strings.xml", per_surface.get("android", [])),
                                      )), per_surface)


def t_bare_refusals_are_reported_separately():
    with tempfile.TemporaryDirectory(prefix="zj-bare-") as tmp:
        root = Path(tmp)
        write(root, "backend/jarvis_fake.py",
              "def reply():\n"
              '    return {"error": "Failed"}\n'
              '    return {"status": "denied"}\n')
        report = scan(root)
        bare = report["bare_refusals"]
        check("a bare 'Failed' error value is reported as a bare refusal",
              len(bare) == 1 and bare[0]["normalised"] == "failed", bare)
        check("... and an enum value ('status': 'denied') is NOT a bare refusal",
              all(b["string"] != "denied" for b in bare), bare)
        baseline = write_baseline(root, 0, 0)
        proc = run(root, "--check", "--baseline", str(baseline))
        check("... and a new bare refusal fails the ratchet",
              proc.returncode == 1 and "bare" in proc.stdout.lower(),
              (proc.returncode, proc.stdout[-500:]))


def t_the_report_is_machine_readable():
    with tempfile.TemporaryDirectory(prefix="zj-report-") as tmp:
        root = Path(tmp)
        write(root, "backend/jarvis_fake.py",
              'def reply():\n    return {"error": "None returned by the parser"}\n')
        out = root / "report.json"
        proc = run(root, "--report", str(out))
        check("--report writes a JSON file", out.is_file(), proc.stdout[-400:])
        data = json.loads(out.read_text(encoding="utf-8"))
        check("the report has the tool/review/counts/findings shape",
              {"tool", "review", "version", "counts", "findings",
               "bare_refusals", "files_scanned"} <= set(data), sorted(data))
        check("... its counts agree with the findings it lists",
              data["counts"]["total"] == len(data["findings"])
              and data["counts"]["bare_refusals"] == len(data["bare_refusals"]),
              data["counts"])
        wanted = {"path", "line", "term", "string", "surface", "category"}
        check("... every finding carries path, line, word and the string",
              data["findings"] and all(wanted <= set(f) for f in data["findings"]),
              data["findings"][:2])


def t_a_file_that_cannot_be_parsed_is_reported_not_skipped():
    with tempfile.TemporaryDirectory(prefix="zj-broken-") as tmp:
        root = Path(tmp)
        write(root, "backend/jarvis_broken.py",
              'def reply(:\n    return {"error": "Failed"}\n')
        report = scan(root)
        check("an unparseable backend module is reported, not skipped",
              bool(report["unreadable"]), report["unreadable"])
        baseline = write_baseline(root, 0, 0)
        proc = run(root, "--check", "--baseline", str(baseline))
        check("... and the ratchet treats it as a failure (never silent)",
              proc.returncode == 1, (proc.returncode, proc.stdout[-500:]))


def t_the_real_tree_is_measured_against_the_committed_baseline():
    check("the committed baseline report exists",
          BASELINE.is_file(), str(BASELINE))
    if not BASELINE.is_file():
        return
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    check("the baseline is a real measurement (files scanned, a count)",
          data.get("files_scanned_total", 0) >= 100
          and isinstance(data["counts"]["total"], int)
          and data["counts"]["total"] >= 0, data.get("files_scanned_total"))
    proc = run(REPO, "--check", "--baseline", str(BASELINE))
    check("the real tree is at or below the recorded baseline today",
          proc.returncode == 0, (proc.returncode, proc.stdout[-800:]))
    check("... and the check says so in words, not silence",
          "ok" in proc.stdout.lower() and "baseline" in proc.stdout.lower(),
          proc.stdout[-500:])


if __name__ == "__main__":
    for name, fn in sorted((n, f) for n, f in globals().items()
                           if n.startswith("t_") and callable(f)):
        print(f"\n--- {name} ---")
        try:
            fn()
        except Exception:
            FAILED.append(name)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        sys.exit(1)
