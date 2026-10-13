"""Write docs/FIELD-TEST-MATRIX-2026-10-11.md from .matrix.json.

    py -3 write_matrix.py

Verdicts follow one rule, stated in the document itself:
  FIELD-TESTED       a PASS record (the 2026-10-11 phone pass README, or the
                     2026-10-10 desktop pass FINDINGS/gap-table/chat turn)
                     names it - the only artifacts here that recorded the app
                     RUNNING and a result per thing
  TEST-VERIFIED ONLY a suite in this repository names it, and no pass record
  NEVER TESTED       neither: nothing has ever run it
  NOT FOUND          not even its code could be found, said plainly
A mention in an audit or tour document is NOT a run: those stay in the REPORT
tier and can never produce FIELD-TESTED.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: THIS worktree. (The first run wrote into the main checkout's docs/ by
#: mistake - HERE.parent.parent is the main checkout, not this worktree.)
REPO = HERE
rows = json.loads((HERE / ".matrix.json").read_text(encoding="utf-8"))

#: Only a file whose NAME says it is a record counts as a review. Copied
#: sources, changelogs and notice files inside the audit folders are not
#: evidence of anything, and the first run cited them.
REPORTISH = ("readme", "report", "findings", "inventory", "tour", "audit",
             "pass", "transcript", "results", "summary", "notes")


def _reportish(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return any(k in name for k in REPORTISH)

PHONE_PASS = ".dsh-scratch/phone-pass-2026-10-11/README.md"
DESKTOP_PASS = ".dsh-scratch/desktop-pass-2026-10-11/"

#: How far behind main each build is, measured with
#: `git rev-list --count <build-base>..main` on 2026-10-11.
BUILDS = {
    "phone": ("phone, installed 2026-10-11 01:17:57, versionName 0.2.0 (APK from "
              "04af95c3 = merged main f8e96ab4)", "6947f458", 37),
    "desktop": ("desktop 0.2.129.0 built 2026-10-10 15:38 (the 2026-10-10 pass) / "
                "0.2.135 written 2026-10-11 02:28", "0f244f7b", 43),
}


def verdict(r: dict) -> tuple:
    """(status, build_cell, evidence_cell)"""
    if r["device"]:
        hits = r["device"]
        phone = [h for h in hits if "phone-pass" in h["file"]]
        desk = [h for h in hits if "desktop-pass" in h["file"]]
        where = []
        if phone:
            where.append(f"{phone[0]['file']}:{phone[0]['line']}")
        if desk:
            where.append(f"{desk[0]['file']}:{desk[0]['line']}")
        builds = []
        if phone:
            builds.append("phone 0.2.0 installed 2026-10-11 01:17 - **37 commits "
                          "behind main**")
        if desk:
            builds.append("desktop 0.2.129.0, 2026-10-10 - **older still**")
        return "FIELD-TESTED", " <br>".join(builds), "<br>".join(where)
    if r["suite"]:
        return ("TEST-VERIFIED ONLY", "never ran on a device", ", ".join(r["suite"]))
    reports = [h for h in r["report"] if _reportish(h["file"])]
    if reports:
        h = reports[0]
        return ("NEVER TESTED", "never ran on a device",
                f"only a review mentions it: {h['file']}:{h['line']}")
    return ("NOT FOUND", "never ran on a device",
            "no evidence either way: no pass record, no suite and no review names it")


out = []
counts = {"FIELD-TESTED": 0, "TEST-VERIFIED ONLY": 0, "NEVER TESTED": 0, "NOT FOUND": 0}
never, fielded, verified = [], [], []
for r in rows:
    st, build, ev = verdict(r)
    counts[st] += 1
    r["_st"], r["_build"], r["_ev"] = st, build, ev
    (fielded if st == "FIELD-TESTED" else never if st == "NEVER TESTED"
     else verified if st == "TEST-VERIFIED ONLY" else never).append(r)

L = []
A = L.append
A("# Field-test matrix - what has actually run on the owner's own devices")
A("")
A("**Written 2026-10-11. Checkout `.dsh-scratch/field-matrix` (branch "
  "`docs/field-test-matrix`) off `origin/main` `70077268`.**")
A("")
A("The owner asked: *\"are there any features that haven't been field tested on "
  "the real world jarvis android app or desktop app? Or conversation driven "
  "features that haven't been? I want thorough testing on everything.\"*")
A("")
A("`features/features.json` holds **127 features in 9 groups and has no "
  "`tested`, `verified` or `status` field at all** - so this document cannot be "
  "read from a file. Every verdict below was built from a dated artifact, and "
  "every row names the one it came from.")
A("")
A("## The counts")
A("")
A(f"| verdict | features |")
A(f"|---|---|")
for k in ("FIELD-TESTED", "TEST-VERIFIED ONLY", "NEVER TESTED", "NOT FOUND"):
    A(f"| {k} | **{counts[k]}** |")
A(f"| **total** | **{len(rows)}** |")
A("")
A("## What each verdict means here, exactly")
A("")
A("- **FIELD-TESTED** - a *pass record* names it: one of the two artifacts that "
  "recorded the app RUNNING and a result per thing.")
A("  - the phone pass, `.dsh-scratch/phone-pass-2026-10-11/README.md` "
  "(2026-10-11, phone `f0a5b32b`, APK from `04af95c3` = merged main `f8e96ab4`);")
A("  - the desktop pass, `.dsh-scratch/desktop-pass-2026-10-11/`: `FINDINGS.md`, "
  "`gap-table.md`, `sweep-results.tsv` and `chat-turn.log` (2026-10-10 "
  "21:57-22:30, desktop **0.2.129.0**).")
A("- **TEST-VERIFIED ONLY** - a suite or checker in this repository names it and "
  "no pass record does. **Suites passing is not field testing.**")
A("- **NEVER TESTED** - no pass record and no suite. A mention in an audit or "
  "tour document does not change this: those read the code and the screens, "
  "they did not drive the feature.")
A("- **NOT FOUND** - no evidence either way: no pass record, no suite, and no review even names it. It says so rather than guessing.")
A("")
A("**A mention is not a run.** The first pass of this work matched the feature's "
  "own words against every file in the audit folders and called **118** features "
  "field-tested. That was wrong: it was matching copied `.kt` source and tour "
  "documents. The device tier was then cut to the two pass records above, which "
  "is where the 80 below comes from. The scan, its input list and the rule are "
  "in `.dsh-scratch/field-matrix/build_matrix.py`.")
A("")
A("## Build freshness - the column that matters most")
A("")
A("| | version / when | base commit | commits behind main `70077268` |")
A("|---|---|---|---|")
A(f"| **phone** | 0.2.0, installed 2026-10-11 01:17:57 (`adb shell dumpsys package "
  f"com.jarvis.client`, device `f0a5b32b`) | `6947f458` | **37** |")
A(f"| **desktop** | 0.2.129.0, built 2026-10-10 15:38 (the pass below; 0.2.135 was "
  f"written 2026-10-11 02:28) | `0f244f7b` | **43** |")
A("")
A("Measured, not assumed: `git rev-list --count 6947f458..main` = 37 and "
  "`git rev-list --count 0f244f7b..main` = 43.")
A("")
A("**So: nothing merged in the last 37 commits has ever run on the phone, and "
  "nothing in the last 43 has run on the desktop.** Every phone verdict below is "
  "against a build 37 commits old; every desktop verdict is older still. The "
  "phone's own install time (`lastUpdateTime`) and `firstInstallTime` "
  "(`2026-10-09 22:14:29`) were read from the device itself.")
A("")
A("## The headline: features that have NEVER run on a real device")
A("")
A("The whole NEVER TESTED and NOT FOUND set - this is the testing queue from the "
  "device side:")
A("")
for r in never:
    A(f"- **{r['title']}** (`{r['id']}`, {r['group']}, {r['surface']}) - {r['_ev']}")
A("")
A("## Conversation-driven gaps (the list the owner asked for by name)")
A("")
A("See the table at the end: every entry there says whether the **preflight** "
  "covers it and whether a **real turn** has ever driven it. The short version: "
  "the preflight last reported **35 pass / 0 fail / 3 warn (5 skipped)** against "
  "the backend of 2026-10-10 (`.dsh-scratch/preflight2.txt`, quoted in "
  "`.dsh-scratch/desktop-pass-2026-10-11/FINDINGS.md` line 30 and in "
  "`.dsh-scratch/gate-fix-msg.txt` line 65) - i.e. **before the 43 commits since**. "
  "A green preflight is a real chain test; it is still not a spoken turn, and "
  "several conversation features are not in it at all.")
A("")
A("## The 127 features")
A("")
A("`surface` is the repo's own field. `evidence` names the file and line the "
  "verdict came from.")
A("")
A("| # | feature | group | surface | status | build it ran against | evidence |")
A("|---|---|---|---|---|---|---|")
for i, r in enumerate(rows, 1):
    A(f"| {i} | {r['title']} (`{r['id']}`) | {r['group']} | {r['surface']} | "
      f"**{r['_st']}** | {r['_build']} | {r['_ev']} |")
A("")
A("## Method, and its limits, said plainly")
A("")
A("1. The 127 entries come from `features/features.json`; no field in it records "
  "testing, so nothing here is read from the repo's own claim.")
A("2. The scan is keyword-based (each feature's id, its title's longer words, and "
  "a short alias table) over the dated artifacts. **False negatives are "
  "possible**: a pass record may describe a feature in words the scan does not "
  "know. False positives are the thing this document exists to avoid, so the "
  "device tier holds only the two pass records and every row cites its line.")
A("3. `TEST-VERIFIED ONLY` says a suite names it. It does **not** say the suite "
  "passes today; that is CI's job and `main`'s state is a separate question.")
A("4. **The device-tour transcripts (2026-10-09) are shown as mentions, not as "
  "runs.** They are a real record of a device, but the tour is older than either "
  "pass record, so a feature that appears only there is NEVER TESTED with the "
  "transcript named in its evidence column - a person should re-check those rows "
  "first, and they are the ones most likely to move up.")
A("5. The conversation-driven table below was written by hand from the same "
  "artifacts, because those features are driven by words and a word is not a "
  "keyword.")
A("")
A("## Conversation-driven features - preflight coverage and real turns")
A("")
A("`preflight` = named in `backend/selftest.py --preflight`. `real turn` = an "
  "artifact records the owner (or a tester) actually saying or typing it on the "
  "PC or phone.")
A("")
A("| conversation feature | preflight covers it? | a real turn ever? | evidence |")
A("|---|---|---|---|")
CONV = [
    ("timers, alarms, reminders (spoken/typed)", "yes, a chain check",
     "**no spoken or typed turn found**", "no transcript drives a timer; "
     "selftest chain only"),
    ("memory saving (\"remember that...\")", "partly",
     "yes - the phone pass drove the Brain's learning plates",
     "phone-pass README, Brain/Memory rows"),
    ("\"what asks first\"", "yes", "read and switched, not driven by a turn",
     "settings-audit/INVENTORY.md; desktop-pass sweep"),
    ("focus sessions", "unknown", "**no**", "no artifact drives one"),
    ("\"Coach this\"", "yes", "**no** - only its setting is checked",
     "desktop-pass gap-table.md (the setting route answered 404)"),
    ("\"Look at this\" / \"Watch with me\"", "partly", "the screen feature was "
     "built and shown, but no artifact records a real look on the PC",
     "docs/SCREEN-DESIGN.md; phone XML dumps"),
    ("web search and its ask-first rules", "yes", "partly - the search route "
     "answered in the sweep; no real search turn was kept",
     "desktop-pass sweep-results.tsv"),
    ("email / calendar / notes reads", "yes", "**no real mailbox or calendar "
     "read found**", "inbox tidy was \"tried against a stand-in mail server, "
     "never a real mailbox\" (CLAUDE.md)"),
    ("note writes (Obsidian / Logseq / Joplin)", "partly", "**no**",
     "no artifact writes a real note"),
    ("inbox tidy by voice", "partly", "**no** - stand-in mail server only",
     "CLAUDE.md, 2026-09-28"),
    ("\"Forget a time frame\"", "yes", "**no**", "no artifact approves one"),
    ("crisis handling", "yes", "**no** - never driven by a real crisis turn, "
     "and it should not be provoked", "test_wellbeing.py only"),
    ("model switch / install", "yes", "**no** - the routes answered in the "
     "sweep, no switch was approved", "desktop-pass gap-table.md"),
    ("Jarvis Live", "partly", "**no**", "no artifact records a Live session"),
    ("\"from now on...\" rules", "unknown", "**no**", "no artifact"),
]
for name, pf, real, ev in CONV:
    A(f"| {name} | {pf} | {real} | {ev} |")
A("")
A("**Read the `real turn` column as the second half of the testing queue.** "
  "Everything marked **no** there has never been driven by the owner's own words "
  "on his own machine, whatever the suites say.")
A("")

doc = "\n".join(L)
(REPO / "docs" / "FIELD-TEST-MATRIX-2026-10-11.md").write_text(doc, encoding="utf-8")
print("counts:", counts)
print("never tested + not found:", len(never))
print("wrote docs/FIELD-TEST-MATRIX-2026-10-11.md", len(doc), "bytes")
