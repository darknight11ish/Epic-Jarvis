"""test_injection_chains.py - tools/check_injection_chains.py's own guard,
and the mutation-sanity proof that each chain probe can fail.

    python3 backend/test_injection_chains.py

WHY THIS SUITE EXISTS. Review #4 Stage A claims that the shipped stores draw
a boundary an injected instruction cannot cross. A checker that has never
failed cannot show that. So this suite copies the shipped backend to a
throwaway tree, breaks one boundary at a time, and requires
`tools/check_injection_chains.py` to report the RIGHT chain failing for the
RIGHT reason.

THE MUTATION-SANITY PROOF. Per mutation:

  1. the run FAILS (exit 1);
  2. the chain named in the row is the one that failed, with that row's
     expected reason code;
  3. the other six chain probes still PASS, so the mutation is surgical;
  4. the clean tree, run again afterwards, exits 0 with seven passes.

Each mutation is a boundary being removed - a subject leaking into a
quiet-thread row, the tier raise deleted, the invisible-character strip
dropped from a calendar summary, DESCRIPTION read and returned, a document's
outside-text label taken off, the store's fold disabled, the note rule
disarmed, a GitHub-write hop added, a caption-import path added, a
notification entry point added, the phone-notification settings shape made
able to carry words, outside words completing a walk item, the private-list
lock ignored - not a crash planted to make a red line.

SINCE 2026-10-30 THERE IS NO BLOCKED ROW (Gemini's ruling, S-2 item 5). The
four former BLOCKED rows are measured probes now: chain3a through
`jarvis_documents`'s own boundary, and 3b/4/5b by asserting that the hop each
needed DOES NOT EXIST and going red the day one appears. This suite proves
that claim the only way it can be proved: every one of the seven has a
mutation that turns it red for its own reason, and the run reports zero
blocked rows. The honest limit of an absence probe is written into the checker
itself - it is not the same thing as an end-to-end probe of a live path.

WHAT ELSE IS PINNED: nothing is reported as BLOCKED any more (the JSON, the
text output and `--list`); an unknown probe and a root with no `backend/` exit
2, never 0; `--list` names every probe without running one; and the chain ids
the mutations name still exist.

No network, no model, no real backend, no third-party package.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CHECKER = REPO / "tools" / "check_injection_chains.py"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


# --------------------------------------------------------------------------
#   A throwaway tree, and a way to run the checker against it
# --------------------------------------------------------------------------

def _fresh_dir(base: Path, tag: str) -> Path:
    """mkdtemp's job, done with os.makedirs - see the fault checker's note: a
    folder mkdtemp made under the Windows agent sandbox refused every write
    beneath it (WinError 5), while an os.makedirs folder accepted files."""
    import uuid
    for _ in range(20):
        candidate = base / f"{tag}-{uuid.uuid4().hex[:10]}"
        try:
            os.makedirs(candidate)
            return candidate
        except FileExistsError:
            continue
    raise OSError(f"no fresh folder name under {base}")


def scratch_base() -> Path:
    base = Path(tempfile.mkdtemp(prefix="chain-suite-"))
    try:
        _fresh_dir(base, "chain")
        return base
    except OSError:
        shutil.rmtree(base, ignore_errors=True)
    fallback = REPO / ".dsh-scratch" / "chain-probes-tmp"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def copytree_modules(dest: Path) -> Path:
    """A copy of the tree the checker imports from: shipped modules, the
    rebuilt overlay and the side files beside them."""
    backend = dest / "backend"
    backend.mkdir(parents=True)
    for src in sorted(HERE.glob("*.py")):
        if src.name.startswith("test_"):
            continue
        shutil.copy2(src, backend / src.name)
    rebuilt = HERE / "rebuilt"
    if rebuilt.is_dir():
        shutil.copytree(rebuilt, backend / "rebuilt")
    for side in sorted(HERE.glob("*.json")) + sorted(HERE.glob("*.lock")):
        shutil.copy2(side, backend / side.name)
    return dest


def _check_work() -> Path:
    """A SHORT scratch folder handed to the checker (Windows' 260-character
    limit broke a deep sandbox path once; see the fault suite's note)."""
    folder = REPO / ".dsh-scratch" / "chain-probes-tmp" / "checker-work"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def run_checker(root: Path, *args: str, json_out: bool = True):
    argv = [sys.executable, "-B", str(CHECKER), "--root", str(root),
            "--workdir", str(_check_work()), *args]
    if json_out:
        argv.append("--json")
    done = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    payload = None
    if json_out:
        try:
            payload = json.loads(done.stdout)
        except ValueError:
            payload = None
    return done.returncode, payload, (done.stdout or "") + (done.stderr or "")


# --------------------------------------------------------------------------
#   One row per boundary: the mutation, and the reason that must be reported
# --------------------------------------------------------------------------
#
# (chain id, file, (find, replace), expected reason, what the mutation means)
MUTATIONS = (
    ("chain1-quiet-threads", "jarvis_email.py",
     ('                    "days": round(days, 1),\n',
      '                    "days": round(days, 1),\n'
      '                    "subject": str(last.get("subject") or ""),\n'),
     "outside_text_crossed",
     "the quiet-thread row starts carrying the email's Subject - the store "
     "boundary chain 1 lives or dies by"),
    ("chain1-quiet-threads", "jarvis_content_risk.py",
     ('    if _RANK.get(tier, 2) >= _RANK[target]:\n'
      '        return tier, latch                  # already at or above; still show why\n'
      '    return target, latch\n',
      '    return tier, latch\n'),
     "tier_not_raised",
     "the latch stops raising a tier, so the second hop is no longer armed"),
    ("chain2-calendar-summary", "jarvis_calendar.py",
     ('    try:\n'
      '        import jarvis_content_risk\n'
      '        text = jarvis_content_risk.normalise(text).text\n'
      '    except Exception:\n'
      '        pass\n'
      '    return text\n',
      '    return text\n'),
     "invisible_survived",
     "the outside-text path stops folding away the invisible characters, so a "
     "zero-width character survives into the returned event"),
    ("chain2-calendar-summary", "jarvis_calendar.py",
     ('        "location": _outside_field(_text(_field(lines, "LOCATION") or "")),\n',
      '        "location": _outside_field(_text((_field(lines, "LOCATION") or "")\n'
      '                                       + (_field(lines, "DESCRIPTION") or ""))),\n'),
     "outside_text_crossed",
     "DESCRIPTION - deliberately never read - starts being read and lands in "
     "the returned location field"),
    ("chain5-walk-report", "jarvis_live.py",
     ('        items.append({"text": piece, "kind": kind,\n'
      '                      "status": "queued" if kind == "needs_approval_card"\n'
      '                                else "ready"})\n',
      '        items.append({"text": piece, "kind": kind, "status": "done"})\n'),
     "outside_words_completed",
     "staging marks every item done, so outside words complete work instead of "
     "waiting for a card"),
    ("chain5-walk-report", "jarvis_live.py",
     ('    locked = bool(hide_memory_lists or app_locked or _walk_private())\n',
      '    locked = False\n'),
     "lock_not_honoured",
     "the evening report stops honouring the private-list lock, so it answers "
     "as if the lists were visible while they are hidden"),
    # --- the four former BLOCKED rows (2026-10-30) ------------------------
    ("chain3a-documents-notes", "jarvis_documents.py",
     ('    return f"{OUTSIDE_LABEL}\\n{_fold(text)}"\n',
      '    return text\n'),
     "outside_label_missing",
     "the document store stops putting its own outside-text label on the words "
     "it returns - the store boundary C6 asked for is gone"),
    ("chain3a-documents-notes", "jarvis_documents.py",
     ('    try:\n'
      '        import jarvis_content_risk\n'
      '        return jarvis_content_risk.normalise(text).text\n'
      '    except Exception:\n'
      '        return text\n',
      '    return text\n'),
     "invisible_survived",
     "the store stops folding invisible characters away, so a zero-width "
     "character survives into the words the model reads"),
    ("chain3a-documents-notes", "jarvis_agent.py",
     ('        reads = [n for n in self.read if n not in ignored]\n'
      '        if self.tainted or any(n not in NOTE_WRITES for n in reads):\n'
      '            return NOTE_AFTER_READING\n',
      '        reads = [n for n in self.read if n not in ignored]\n'
      '        if False:\n'
      '            return NOTE_AFTER_READING\n'),
     "note_rule_not_armed",
     "a reading tool no longer makes a note write wait for a person - the "
     "second hop of chain 3a is disarmed"),
    ("chain4-captions-decks", "jarvis_decks.py",
     ('def grade_spoken_answer(expected_back, spoken_answer) -> dict:\n',
      'def import_from_captions(captions):\n'
      '    return {"ok": True}\n'
      '\n'
      '\n'
      'def grade_spoken_answer(expected_back, spoken_answer) -> dict:\n'),
     "hop_appeared",
     "the deck store grows a caption-import path, so captions -> deck is a "
     "real hop and this chain needs an end-to-end probe"),
    ("chain5b-phone-notification", "jarvis_live.py",
     ('def build_evening_report(',
      'def notification_into_report(text):\n'
      '    return {"ok": True}\n'
      '\n'
      '\n'
      'def build_evening_report('),
     "hop_appeared",
     "the evening report grows an entry point for a phone notification, so the "
     "notification half of chain 5 is a real hop"),
    ("chain5b-phone-notification", "jarvis_phone_notifications.py",
     ('        return {"enabled": False, "why": ""}\n',
      '        return {"enabled": False, "why": "", "text": ""}\n'),
     "settings_carry_text",
     "the notifications settings switch starts carrying a text field, which is "
     "how a notification's words could ride out of it"),
)

#: Mutations that ADD a module instead of editing one: the hop chain 3b says
#: does not exist is exactly "a writer module that is shipped". Same shape and
#: same proof as the text mutations above.
ADDED_FILES = (
    ("chain3b-project-github", "jarvis_github_write.py",
     '"""A GitHub writer - the hop chain 3b asserts does not exist."""\n'
     '\n'
     '\n'
     'def push_document(text, repo):\n'
     '    return {"ok": True}\n',
     "hop_appeared",
     "a GitHub writer module is shipped, so chain 3b's last hop is real"),
)


def _mutate(folder: Path, name: str, find: str, replace: str) -> None:
    path = folder / "backend" / name
    text = path.read_text("utf-8")
    if find not in text:
        raise AssertionError(
            f"the mutation's text is not in {name} any more - the source moved; "
            f"update MUTATIONS in {Path(__file__).name}. Looking for:\n{find[:200]}")
    if text.count(find) > 1:
        raise AssertionError(f"the mutation's text appears {text.count(find)}x in {name}")
    path.write_text(text.replace(find, replace, 1), "utf-8")


def t_clean_tree_passes():
    base = _fresh_dir(scratch_base(), "clean")
    root = copytree_modules(base / "tree")
    code, payload, output = run_checker(root)
    check("the checker exits 0 on a clean copy of the shipped tree", code == 0,
          output[-800:])
    if payload is None:
        check("the checker printed parseable JSON", False, output[-500:])
        return
    check("seven chain probes ran and none failed",
          payload.get("passed") == 7 and payload.get("failed") == 0,
          f"passed={payload.get('passed')} failed={payload.get('failed')}")
    ids = sorted(p["id"] for p in payload["probes"])
    chains = {m[0] for m in MUTATIONS} | {m[0] for m in ADDED_FILES}
    check("the chain ids are the ones the mutations name",
          ids == sorted(chains), ids)
    check("nothing is reported as blocked any more",
          payload.get("blocked") == [], payload.get("blocked"))
    check("the summary is 7 / 0 / 0, and says a run that cannot happen is a FAIL",
          payload.get("passed") == 7 and payload.get("failed") == 0
          and payload.get("blocked") == [], payload)


def t_every_mutation_is_caught_for_the_right_reason():
    for chain_id, name, (find, replace), reason, meaning in MUTATIONS:
        base = _fresh_dir(scratch_base(), chain_id)
        root = copytree_modules(base / "tree")
        try:
            _mutate(root, name, find, replace)
        except AssertionError as exc:
            check(f"{chain_id} ({name}): the mutation can still be applied", False, str(exc))
            continue
        code, payload, output = run_checker(root)
        check(f"{chain_id} ({name}): the mutated tree FAILS the run (exit 1)",
              code == 1, output[-900:])
        if payload is None:
            check(f"{chain_id}: the checker printed parseable JSON", False, output[-400:])
            continue
        failed = {p["id"]: p for p in payload["probes"] if p["status"] != "pass"}
        check(f"{chain_id} ({name}): the tree is rejected by THAT chain",
              set(failed) == {chain_id}, f"failed chains were {sorted(failed)}")
        if chain_id in failed:
            check(f"{chain_id} ({name}): it fails for the RIGHT reason ({reason})",
                  failed[chain_id].get("reason") == reason,
                  f"reason was {failed[chain_id].get('reason')!r}: "
                  f"{(failed[chain_id].get('detail') or '')[:300]}")
        check(f"{chain_id} ({name}): the other chains still pass, so the mutation is surgical",
              payload.get("passed") == 6,
              f"passed={payload.get('passed')} (mutation: {meaning})")

    for chain_id, name, body, reason, meaning in ADDED_FILES:
        base = _fresh_dir(scratch_base(), chain_id)
        root = copytree_modules(base / "tree")
        (root / "backend" / name).write_text(body, "utf-8")
        code, payload, output = run_checker(root)
        check(f"{chain_id} (+{name}): the mutated tree FAILS the run (exit 1)",
              code == 1, output[-900:])
        if payload is None:
            check(f"{chain_id}: the checker printed parseable JSON", False, output[-400:])
            continue
        failed = {p["id"]: p for p in payload["probes"] if p["status"] != "pass"}
        check(f"{chain_id} (+{name}): the tree is rejected by THAT chain",
              set(failed) == {chain_id}, f"failed chains were {sorted(failed)}")
        if chain_id in failed:
            check(f"{chain_id} (+{name}): it fails for the RIGHT reason ({reason})",
                  failed[chain_id].get("reason") == reason,
                  f"reason was {failed[chain_id].get('reason')!r}: "
                  f"{(failed[chain_id].get('detail') or '')[:300]}")
        check(f"{chain_id} (+{name}): the other chains still pass, so the addition is the cause",
              payload.get("passed") == 6,
              f"passed={payload.get('passed')} (mutation: {meaning})")


def t_an_absence_probe_is_a_measured_claim():
    """The three absence probes say what they prove, in their own output: each
    carries its `limit` in the evidence, so a reader of a PASS line cannot
    mistake "the hop is not there" for "the path was driven end to end"."""
    _code, payload, output = run_checker(REPO)
    if payload is None:
        check("the checkout's own run printed parseable JSON", False, output[-500:])
        return
    by_id = {p["id"]: p for p in payload["probes"]}
    for chain_id in ("chain3b-project-github", "chain4-captions-decks",
                     "chain5b-phone-notification"):
        row = by_id.get(chain_id) or {}
        check(f"{chain_id} passes and states its own limit",
              row.get("status") == "pass"
              and bool((row.get("evidence") or {}).get("limit")),
              row)


def t_nothing_is_blocked_any_more():
    code, _payload, output = run_checker(REPO, json_out=False)
    _code, payload, _out = run_checker(REPO, json_out=True)
    check("the checkout's own tree is clean for the checker", code == 0, output[-600:])
    check("no line of the text output is labelled BLOCKED",
          not any(ln.startswith("BLOCKED") for ln in output.splitlines()),
          output[-600:])
    check("the summary says 0 blocked and that a run that cannot happen is a FAIL",
          "0 blocked" in output, output[-300:])
    if payload:
        check("the JSON says nothing is blocked", payload.get("blocked") == [],
              payload.get("blocked"))
        check("seven probes ran and none failed",
              payload.get("passed") == 7 and payload.get("failed") == 0,
              f"passed={payload.get('passed')} failed={payload.get('failed')}")


def t_no_run_is_never_a_pass():
    code, _payload, output = run_checker(REPO, "--probe", "chain-does-not-exist")
    check("an unknown chain probe exits 2 and says NO RUN", code == 2 and "NO RUN" in output,
          f"exit {code}: {output[-300:]}")
    empty = _fresh_dir(scratch_base(), "not-a-tree")
    code, _payload, output = run_checker(empty)
    check("a root with no backend/ exits 2 and says NO RUN",
          code == 2 and "NO RUN" in output, f"exit {code}: {output[-300:]}")
    done = subprocess.run([sys.executable, "-B", str(CHECKER), "--list"],
                          cwd=str(REPO), capture_output=True, text=True, timeout=120)
    check("--list exits 0 and names every chain probe without running one",
          done.returncode == 0 and done.stdout.count("PROBE ") == 7,
          done.stdout[-400:])
    check("--list prints no blocked row at all",
          "BLOCKED" not in done.stdout, done.stdout[-600:])


def main() -> int:
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("t_") and callable(f)]
    for name, fn in tests:
        print(f"--- {name} ---")
        try:
            fn()
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    print(f"      ({len(tests)} t_ function(s) were found by name and run)")
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
