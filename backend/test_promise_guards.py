"""Every promise this project makes, and the guard that keeps it - asserted.

    py -3 backend/test_promise_guards.py

WHY THIS FILE EXISTS

The 2026-10-04 handoff (docs/HANDOFF-2026-10-04-test-suite-fixes.md, section 7
item 1) records an audit of "promises vs tests": for every promise the
project makes, find the test that would go red if the promise broke, break it
on purpose, and confirm. It was written because of the erase hole - *"Erase
the words" wipes the fact's text for good* had a test that read the file as
raw bytes, and the product still kept the words. The test was real; the
promise was broken; nothing told anyone for long enough that a whole handoff
was written about it.

That audit left behind a table (dshwork/audit-2026-10-04/audit-01-promises.md)
and a problem: a table in a document is prose about code, and prose about code
is the thing that goes stale first. This suite is the table with teeth. For
every promise it asserts TWO things:

  1. **the product guard still exists** - the named function, class or
     constant is still in the named module, read with `ast` so a comment
     cannot stand in for code (see test_gate_outcome's `_code_only`, and the
     handoff's own "a test that cannot tell code from prose about code is
     worse than no test");
  2. **the test that owns it still exists** - the named `t_...` function (or
     `test_...` method) is still defined in the named suite file.

Delete the guard, or delete the test that proves it, and this suite goes red.
That is the whole point: the pair is the promise. A guard nobody tests is how
the erase hole survived, and a test with no guard is a test of nothing.

WHERE IT READS FROM

`BACKEND` is where the modules the backend actually runs live
(`JARVIS_BACKEND` on the owner's PC, this folder in the dev container) - the
same two-roots rule every suite in here follows (`_where.py`). A module this
repository ships whole is also readable at `backend/rebuilt/<name>`; when the
backend folder has no copy, that one is read and the check says which copy it
read. `REPO` is always this repository, which is where the suites are.

`require_shipped()` is deliberately NOT called. That helper refuses to run
when the backend's copy of a shipped module differs from this repository's -
which is exactly the situation this suite must still be able to report on. A
backend running an older module is a finding here, not a reason to say
nothing.

HONEST SKIPS

`jarvis_hud.py`, `jarvis_gate.py` and `jarvis_memory.py`'s patched cousins are
owner-only files: they are not in this repository, because they are what the
patches are applied TO. Run in the dev container (no `JARVIS_BACKEND`) and the
promises whose guard lives in one of them are SKIPPED, with the reason, rather
than quietly passed. `explain()` says where they were looked for.
"""
from __future__ import annotations

import ast
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder in the
# dev container, $JARVIS_BACKEND on a real install. REPO is this repository.
from _where import BACKEND, REPO, explain  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """An honest SKIP. Not counted as passed and not as failed: the thing was
    never checked, and saying so is the point."""
    SKIPPED.append(name)
    print(f"SKIP  {name}\n        {why}")


# --------------------------------------------------------------------------
#   Reading the product and the suites
# --------------------------------------------------------------------------

_PARSED: dict = {}


def _parse(path: Path):
    key = str(path)
    if key not in _PARSED:
        try:
            _PARSED[key] = ast.parse(path.read_text(encoding="utf-8"))
        except Exception as exc:  # a module that will not parse is a finding
            _PARSED[key] = exc
    return _PARSED[key]


def _product_path(module: str):
    """The copy of `module` the backend runs, or the one this repository ships.

    Returns (path or None, why). A shipped module lands beside jarvis_hud.py on
    the owner's PC under its own name; in this repository it lives at
    backend/rebuilt/<name>. Both are the product; the first is the one running.
    """
    running = BACKEND / module
    if running.is_file():
        return running, f"the backend's own {module}"
    shipped = REPO / "backend" / "rebuilt" / module
    if shipped.is_file():
        return shipped, f"this repository's shipped copy ({shipped.parent.name}/{module})"
    return None, (f"{module} is in neither {BACKEND} nor {shipped.parent}. "
                  f"{explain()}")


def _tree_of(module: str, why: str):
    """(tree, where) for a module, or (None, None) with a SKIP already printed."""
    path, where = _product_path(module)
    if path is None:
        skip(f"{module}: the guard in it was NOT checked", why)
        return None, None
    tree = _parse(path)
    if isinstance(tree, Exception):
        check(f"{module} parses as Python", False, f"{type(tree).__name__}: {tree}")
        return None, None
    return tree, where


def _find_def(tree, name: str):
    """A function defined anywhere in the tree (module level or a class body:
    test_rebuilt's stale checks are unittest methods)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _find_class(tree, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _find_assign(tree, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == name:
            return node
    return None


def _defines(module: str, name: str, kind: str = "function"):
    """Whether the module defines `name`. SKIPs (with the reason) when the
    module is not readable here, so an owner-only file never reads as a pass."""
    tree, where = _tree_of(module, _product_path(module)[1])
    if tree is None:
        return None
    node = {"function": _find_def, "class": _find_class, "constant": _find_assign}[kind](tree, name)
    check(f"{module} still defines {name}()", node is not None,
          f"not found in {where}")
    return node


def _source_of(module: str, name: str):
    """(source segment of `name`, where) - or (None, None) if it is gone."""
    path, where = _product_path(module)
    if path is None:
        return None, None
    tree = _parse(path)
    if isinstance(tree, Exception):
        return None, None
    node = _find_def(tree, name) or _find_class(tree, name)
    if node is None:
        return None, where
    return ast.get_source_segment(path.read_text(encoding="utf-8"), node), where


def _suite_has(suite: str, name: str):
    """The named test still exists in the named suite in this repository."""
    path = REPO / "backend" / suite
    if not path.is_file():
        check(f"{suite} still exists (the suite that owns this promise)",
              False, f"no {path}")
        return False
    tree = _parse(path)
    if isinstance(tree, Exception):
        check(f"{suite} parses as Python", False, f"{type(tree).__name__}: {tree}")
        return False
    found = _find_def(tree, name) is not None
    check(f"{suite} still has {name}()", found,
          "the test that would go red for this promise was deleted or renamed")
    return found


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _code_only(text: str) -> str:
    """The source with comments and docstrings removed.

    Same technique as test_gate_outcome: `ast.unparse` drops comments outright
    and docstring nodes are replaced, so what is left is executable code plus
    the string literals actually used as values. A test that cannot tell code
    from prose about code will be silenced rather than fixed.
    """
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body[0] = ast.Pass()
    return ast.unparse(tree)


def _norm(text: str) -> str:
    """Whitespace-collapsed, so a promise that wraps across lines is one
    string - the promise, not the line breaks."""
    return " ".join(text.split())


# --------------------------------------------------------------------------
#   The promises. Each entry is the mapping the audit proved by breaking it.
#
#   promise  the project's own words (checked against the file named in `doc`)
#   doc      where those words are written
#   module   the product module holding the guard
#   symbols  the guard: (name, kind) pairs that must still be defined
#   suite    the suite that owns the promise, and the test function(s) in it
#   proved   what the audit did to prove the mapping (kept here so the evidence
#            file and the claim cannot drift apart)
# --------------------------------------------------------------------------

PROMISES = (
    {
        "id": "P1",
        "promise": "wipes the fact's text for good (and its search entry)",
        "doc": "CLAUDE.md",
        "module": "jarvis_memory.py",
        "symbols": (("_scrub_file", "function"), ("erase", "function")),
        "suite": "test_memory_erase.py",
        "tests": ("t_the_file_holds_no_words",),
        "proved": "P01-erase-red.txt (VACUUM removed from _scrub_file -> 3 failed)",
    },
    {
        "id": "P2",
        "promise": "The app never auto-approves anything",
        "doc": "CLAUDE.md",
        "module": "jarvis_gate.py",
        "symbols": (("confirm_auto", "function"), ("Verdict", "class")),
        "suite": "test_gate_outcome.py",
        "tests": ("t_there_is_still_no_approve_all",
                  "t_the_auto_approve_flag_does_not_bypass_anything"),
        "proved": "P02-no-auto-approve-red.txt (confirm_auto returns True -> 4 failed)",
    },
    {
        "id": "P3",
        "promise": "blocks acting when the event stream is stale",
        "doc": "CLAUDE.md",
        "module": "jarvis_events.py",
        "symbols": (("stream", "function"), ("hello", "function")),
        "suite": "test_rebuilt.py",
        "tests": ("test_a_stale_client_is_told_so_and_not_replayed",),
        "proved": "P03-stale-signal-red.txt (the stale signal is forced False -> 1 failed)",
    },
    {
        "id": "P4",
        "promise": "Never log the token.",
        "doc": "CLAUDE.md",
        "module": "jarvis_scrub.py",
        "symbols": (("install", "function"), ("scrub_text", "function"),
                    ("_replace_known", "function"), ("register_secret", "function")),
        "suite": "test_scrub.py",
        "tests": ("t_known_values", "t_install_registers_the_pairing_token", "t_stream"),
        "proved": "P04-token-in-log-red.txt (no value is replaced -> 10 failed)",
    },
    {
        "id": "P5",
        "promise": "The app never opens a public tunnel.",
        "doc": "CLAUDE.md",
        "module": "jarvis_hud.py",
        "symbols": (("_refuse_every_interface", "function"),),
        "suite": "test_bind_wildcard.py",
        "tests": ("t_the_table_is_true_and_every_wildcard_is_refused",
                  "t_no_second_listener_for_any_wildcard_spelling"),
        "proved": "P05-public-tunnel-bind-red.txt (the SystemExit is removed -> 4 failed)",
    },
    {
        "id": "P6",
        "promise": "The apps accept a server address on the owner's own networks only",
        "doc": "CLAUDE.md",
        "module": "jarvis_local_http.py",
        "symbols": (("_own_network", "function"), ("_OWN_NETS", "constant"),
                    ("_OWN_SUFFIXES", "constant")),
        "suite": "test_own_network_cases.py",
        "tests": ("t_the_cases_the_rule_exists_for", "t_both_copies_are_current"),
        "proved": "P06-own-network-red.txt (_own_network returns True -> 16 failed)",
    },
    {
        "id": "P7",
        "promise": "kept out of anything the app writes to disk in plain text",
        "doc": "CLAUDE.md",
        "module": "jarvis_token_store.py",
        "symbols": (("resolve", "function"), ("_remove", "function"),
                    ("WindowsStore", "class"), ("Unavailable", "class")),
        "suite": "test_token_store.py",
        "tests": ("t_the_old_file_is_moved_in_and_deleted",
                  "t_a_refusing_store_with_no_file_writes_nothing",
                  "t_errors_carry_codes_not_tokens"),
        "proved": "P07-key-plain-text-red.txt (the plain-text file is never deleted -> 9 failed)",
    },
    {
        "id": "P8",
        "promise": "A client must not do speech-to-text.",
        "doc": "CLAUDE.md",
        "module": "jarvis_hud.py",
        "symbols": (("_no_speech", "function"),),
        "suite": "test_voice_503.py",
        "tests": ("t_each_route_answers_for_itself", "t_the_shape"),
        "proved": "P08-client-stt-red.txt (fallback_ok=True on /api/voice/utterance -> 2 failed)",
    },
    {
        "id": "P9",
        "promise": "Send `X-Jarvis-Client: hud` on every request.",
        "doc": "CLAUDE.md",
        "module": "jarvis_hud.py",
        "symbols": (("_origin_ok", "function"),),
        "suite": "../jarvis-desktop/tests/deep.mjs",
        "tests": ("CONTROL: both commands send X-Jarvis-Client: hud and the token "
                  "the usual way, to the configured backend, and log nothing",),
        "proved": "NOT PROVED HERE - see the report: the owning check is a Node "
                  "check and Playwright is not installed.",
    },
    {
        "id": "P10",
        "promise": "Never build a control that clears a rush latch or approves in bulk.",
        "doc": "CLAUDE.md",
        "module": "jarvis_widgets.py",
        "symbols": (("ACTIONS", "constant"), ("validate", "function")),
        "suite": "test_widgets.py",
        "tests": ("t_the_buttons_are_the_tile_actions",),
        "proved": "P10-widget-rush-latch-red.txt (clear_rush added to ACTIONS -> 2 failed)",
    },
    {
        "id": "P11",
        "promise": "Crisis messages are never learned from and never counted.",
        "doc": "CLAUDE.md",
        "module": "jarvis_wellbeing.py",
        "symbols": (("crisis", "function"), ("CRISIS_PHRASES_EN", "constant")),
        "suite": "test_wellbeing.py",
        "tests": ("t_a_crisis_turn_is_excluded_from_owner_turns",
                  "t_a_crisis_answer_marked_wrong_is_not_counted"),
        "proved": "P11-crisis-red.txt (crisis() always False -> 38 failed)",
    },
    {
        "id": "P12",
        "promise": "and passwords/PINs/account/ID numbers, still wait for a yes",
        "doc": "CLAUDE.md",
        "module": "jarvis_auto_learn.py",
        "symbols": (("check_sensitive", "function"),),
        "suite": "test_auto_learn.py",
        "tests": ("t_sensitive_topics_wait_unless_allowed",
                  "t_passwords_pins_account_and_id_numbers_always_wait"),
        "proved": "P12-sensitive-red.txt (check_sensitive never asks -> 76 failed)",
    },
    {
        "id": "P13",
        "promise": "A risky approval from this PC needs Windows Hello at the backend.",
        "doc": "docs/ARCHITECTURE.md",
        "module": "jarvis_owner_check.py",
        "symbols": (("approve_check", "function"), ("is_risky", "function"),
                    ("verify", "function"), ("take_stamp", "function"),
                    ("_signed_check", "function"),
                    ("PC_ONLY_ACTIONS", "constant")),
        "suite": "test_owner_check.py",
        "tests": ("t_a_risky_approval_from_this_pc_asks_windows_hello_first",
                  "t_no_windows_hello_no_risky_approval",
                  "t_the_gate_believes_no_approved_row_without_a_stamp"),
        "proved": "P13a-gate-unstamped-red.txt, P13b-hello-skipped-red.txt and "
                  "P13c-signed-approval-red.txt (3 failed, 14 failed, 27 failed)",
    },
)

#: Promises whose guard or owning test lives in a second file too. Kept apart
#: from the table above so a missing one is a SKIP with its own reason.
ALSO_IN = {
    "P10": (("test_gate_outcome.py", "t_there_is_still_no_approve_all"),),
    "P11": (("test_auto_learn.py", "t_a_crisis_chat_is_not_put_back"),),
    "P12": (("test_sensitive.py",
             "t_everyday_facts_about_people_save_private_ones_still_ask"),),
    "P13": (("test_gate_outcome.py", "t_an_approval_nobody_stamped_is_refused"),
            ("test_approval_sign.py", "t_a_removed_device_or_no_approval_key"),
            ("test_approval_sign.py",
             "t_nothing_or_junk_in_place_of_a_signature_is_refused")),
}


# --------------------------------------------------------------------------
#   The promises' own words
# --------------------------------------------------------------------------

def t_the_promise_sentences_are_still_written():
    """The inventory is built from the project's own words, so the words are
    checked too. A promise quietly reworded is how one stops being a promise.

    Whitespace is collapsed first: these sentences wrap across lines, and it is
    the sentence that matters, not where the line breaks fell.
    """
    for p in PROMISES:
        path = REPO / p["doc"]
        if not path.is_file():
            skip(f"{p['id']}: {p['doc']} is readable", f"no {path}")
            continue
        check(f"{p['id']}: {p['doc']} still says it ({p['promise'][:52]}...)",
              p["promise"] in _norm(_text(path)),
              f"the sentence is no longer in {p['doc']}: reworded, or moved")


def t_the_audit_table_is_here():
    """The report the audit wrote, kept beside the evidence. Its absence is
    not a product fault, so this SKIPs rather than failing - but the mapping
    above says which run proves it, and that run has to be findable."""
    table = REPO / "dshwork" / "audit-2026-10-04" / "audit-01-promises.md"
    if not table.is_file():
        skip("the audit table is here", f"no {table}")
        return
    evidence = REPO / "dshwork" / "audit-2026-10-04" / "audit-01-evidence"
    for p in PROMISES:
        head = p["proved"].split(" ")[0]
        if not head.endswith(".txt"):
            continue                      # P9's entry names no run on purpose
        check(f"{p['id']}: the red run it names is on disk ({head})",
              (evidence / head).is_file(),
              f"no {evidence / head}")


# --------------------------------------------------------------------------
#   The guards, one promise at a time
# --------------------------------------------------------------------------

def t_p1_erase_wipes_the_words_for_good():
    """The guard is not only `erase` calling `_scrub_file`: it is the VACUUM
    inside it. secure_delete does not cover a row that moved to an overflow
    page, and that is the half that was missing - the audit broke exactly this
    line and test_memory_erase went red with 3 failures."""
    _defines("jarvis_memory.py", "erase")
    _defines("jarvis_memory.py", "_scrub_file")
    src, where = _source_of("jarvis_memory.py", "_scrub_file")
    if src is None:
        skip("jarvis_memory._scrub_file is readable", where or "the module is gone")
    else:
        tree = ast.parse(src)
        vacuum = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and getattr(n.func, "attr", "") == "execute"
                  and n.args and isinstance(n.args[0], ast.Constant)
                  and n.args[0].value == "VACUUM"]
        check("jarvis_memory._scrub_file still VACUUMs the file it erased from",
              bool(vacuum),
              f"no c.execute('VACUUM') left in _scrub_file ({where}) - "
              f"secure_delete alone leaves the words in the file")
    _suite_has("test_memory_erase.py", "t_the_file_holds_no_words")


def t_p2_nothing_ever_auto_approves():
    """Two halves, because the promise has two: `confirm_auto` must delegate
    rather than return True, and no blanket-grant identifier may exist in the
    gate's CODE. Comments and docstrings in that module talk about
    approve-alls on purpose - that is why this reads `ast.unparse` output."""
    _defines("jarvis_gate.py", "Verdict", "class")
    node = _defines("jarvis_gate.py", "confirm_auto")
    if node is not None:
        body = ast.unparse(node)
        check("jarvis_gate.confirm_auto still delegates to confirm()",
              "return confirm(prompt)" in body,
              "it used to `return True` for tier ask with nobody asked")
        check("jarvis_gate.confirm_auto still warns once on stderr",
              "auto_flag_ignored" in body or "_AUTO_FLAG_WARNED" in body,
              "a flag that silently stopped working is its own kind of lie")
    path, where = _product_path("jarvis_gate.py")
    if path is not None:
        code = _code_only(_text(path))
        banned = ["approve_all", "approveAll", "allow_all", "allowAll",
                  "yolo", "autoApprove", "bypass_approvals"]
        found = [b for b in banned if b in code]
        check("no blanket-grant identifier exists in the gate's code", not found,
              f"found {found} in {where}")
        check("only auto, notify and approved may carry allowed=True",
              "'auto', 'notify', 'approved'" in code)
    for name in ("t_there_is_still_no_approve_all",
                 "t_the_auto_approve_flag_does_not_bypass_anything"):
        _suite_has("test_gate_outcome.py", name)


def t_p3_acting_is_held_on_a_stale_stream():
    """The backend's half is the SIGNAL: `stream()` works out `stale` from the
    client's cursor and hands it over in the hello frame - a client cannot hold
    what it was never told. The holding itself is in the desktop's Rust
    (`decide_approval` and friends read `link().stale`), which is why the last
    checks read those files as text and name the Rust tests that own them: this
    suite cannot run `cargo test`, and pretending a text match is a red run
    would be the prose-about-code mistake this audit exists to catch."""
    _defines("jarvis_events.py", "hello")
    node = _defines("jarvis_events.py", "stream")
    if node is not None:
        body = ast.unparse(node)
        check("jarvis_events.stream still computes `stale` from the cursor",
              "stale = bool(" in body and "oldest" in body,
              "a client that is not told it fell off the ring cannot re-fetch")
        check("a stale client is still not replayed the ring",
              "if stale or not cursor" in body,
              "replaying a ring the client fell off tells it nothing useful")
        check("the hello frame still carries `stale`",
              "'stale'" in body or '"stale"' in body)
    _suite_has("test_rebuilt.py", "test_a_stale_client_is_told_so_and_not_replayed")

    src = REPO / "jarvis-desktop" / "src-tauri" / "src"
    if not src.is_dir():
        skip("the desktop's stale hold is in the Rust source", f"no {src}")
        return
    holds = sorted(p.name for p in src.glob("*.rs") if "link().stale" in _text(p))
    check("the desktop still holds on link().stale (rule 4, acting blocked)",
          len(holds) >= 5, f"only {holds} mention it")
    for rust, test in (("backup.rs", "fn setting_the_folder_restoring_and_deleting_older_wait_for_a_live_link"),
                       ("folders.rs", "fn adding_and_importing_wait_for_a_live_link_removing_never_does"),
                       ("live.rs", "fn the_microphone_closes_for_everything_but_a_voice_pause")):
        path = src / rust
        check(f"{rust} still has the Rust test that owns its stale hold",
              path.is_file() and test in _text(path),
              f"{test} is gone (this suite cannot run cargo test; the name is the check)")


def t_p4_the_token_is_never_logged():
    """Redaction is by VALUE, not by shape: a pairing token has no shape. The
    behaviour check below is the promise itself - register a secret, hand the
    scrubber text containing it, get text back that does not."""
    for name in ("install", "scrub_text", "_replace_known", "register_secret"):
        _defines("jarvis_scrub.py", name)
    src, where = _source_of("jarvis_scrub.py", "_replace_known")
    if src is not None:
        check("jarvis_scrub._replace_known still replaces every known value",
              "_mark(label)" in src and "text.replace" in src,
              f"the replacement is gone from {where}")
    try:
        import jarvis_scrub as S
        S.register_secret("promise-guard-token-0123456789")
        out = S.scrub_text("paired with promise-guard-token-0123456789 today")
        check("a registered secret does not survive scrub_text()",
              "promise-guard-token-0123456789" not in out, out)
    except Exception as exc:
        check("jarvis_scrub can be imported from the backend folder", False,
              f"{type(exc).__name__}: {exc}")
    for name in ("t_known_values", "t_install_registers_the_pairing_token", "t_stream"):
        _suite_has("test_scrub.py", name)


def t_p5_no_public_tunnel():
    """One bind address is the whole promise: `0.0.0.0` (in every spelling the
    OS's resolver accepts) is every network interface, so the backend refuses
    to start rather than quietly answering on the cafe's Wi-Fi."""
    node = _defines("jarvis_hud.py", "_refuse_every_interface")
    if node is not None:
        check("jarvis_hud._refuse_every_interface still raises SystemExit(2)",
              "raise SystemExit(2)" in ast.unparse(node),
              "a refusal that returns instead of exiting starts the server anyway")
    _suite_has("test_bind_wildcard.py", "t_the_table_is_true_and_every_wildcard_is_refused")
    _suite_has("test_bind_wildcard.py", "t_no_second_listener_for_any_wildcard_spelling")


def t_p6_own_networks_only():
    """Neither app has a rule of its own: both follow the backend's
    `_own_network`, through a case table `tools/gen_own_network_cases.py` makes
    by running it. So the guard and the table are the same claim twice, and
    the behaviour checks below are the tunnels the promise names."""
    for name, kind in (("_own_network", "function"), ("_OWN_NETS", "constant"),
                       ("_OWN_SUFFIXES", "constant")):
        _defines("jarvis_local_http.py", name, kind)
    try:
        import jarvis_local_http as L
        for host, own in (("abc123.ngrok-free.app", False),
                          ("my-jarvis.trycloudflare.com", False),
                          ("8.8.8.8", False),
                          ("100.63.255.255", False),
                          ("localhost.evil.com", False),
                          ("127.0.0.1", True),
                          ("100.64.0.0", True),
                          ("desktop.tail1234.ts.net", True),
                          ("my-pc.nord", True)):
            check(f"_own_network({host!r}) is {own}", L._own_network(host) is own,
                  "the pairing key would travel there")
    except Exception as exc:
        check("jarvis_local_http can be imported from the backend folder", False,
              f"{type(exc).__name__}: {exc}")
    _suite_has("test_own_network_cases.py", "t_the_cases_the_rule_exists_for")
    _suite_has("test_own_network_cases.py", "t_both_copies_are_current")


def t_p7_keys_are_not_written_in_plain_text():
    """The store is Credential Manager and the module's own docstring says
    "Writes no file, ever". The load-bearing half is the OTHER direction: an
    old plain-text file is moved in and then DELETED, and a store that cannot
    take it leaves the file (refusing to lose the pairing) rather than writing
    a copy anywhere new."""
    for name, kind in (("resolve", "function"), ("_remove", "function"),
                       ("WindowsStore", "class"), ("Unavailable", "class")):
        _defines("jarvis_token_store.py", name, kind)
    src, where = _source_of("jarvis_token_store.py", "resolve")
    if src is not None:
        check("jarvis_token_store.resolve still deletes the old plain-text file",
              "_remove(" in src,
              f"resolve no longer removes the file it moved out of ({where})")
    for name in ("t_the_old_file_is_moved_in_and_deleted",
                 "t_a_refusing_store_with_no_file_writes_nothing",
                 "t_errors_carry_codes_not_tokens"):
        _suite_has("test_token_store.py", name)


def t_p8_a_client_never_does_speech_to_text():
    """Reading speech and speaking text are opposite directions, and the
    backend answers them differently: `/api/voice/say` may offer the client its
    own synthesiser, `/api/voice/utterance` may NOT offer its own recogniser -
    that would move the privacy boundary and disarm the owner-voice gate.

    So the check is per route, not a count: a sixth route, or two routes
    swapping their flags, has to be caught."""
    _defines("jarvis_hud.py", "_no_speech")
    path, where = _product_path("jarvis_hud.py")
    if path is None:
        skip("the utterance route's own answer is readable", where)
    else:
        tree = _parse(path)
        src = _text(path)
        for n in ast.walk(tree):
            if not isinstance(n, ast.If):
                continue
            named = [c.value for c in ast.walk(n.test)
                     if isinstance(c, ast.Constant) and isinstance(c.value, str)
                     and c.value.startswith("/api/voice/")]
            if "/api/voice/utterance" not in named:
                continue
            value = None
            for call in ast.walk(n):
                if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "_no_speech":
                    kw = {k.arg: k.value for k in call.keywords}
                    if "fallback_ok" in kw:
                        value = getattr(kw["fallback_ok"], "value", None)
            check("the utterance route refuses the client's own speech-to-text",
                  value is False,
                  f"fallback_ok is {value!r} there: a client that guessed would "
                  f"move the privacy boundary")
            segment = ast.get_source_segment(src, n) or ""
            check("and it says so in words the client shows",
                  "do NOT recognise this yourself" in segment)
            break
        else:
            check("the /api/voice/utterance route is still there to check", False,
                  "the route is gone, so nothing refuses a client recogniser")
    _suite_has("test_voice_503.py", "t_each_route_answers_for_itself")
    _suite_has("test_voice_503.py", "t_the_shape")


def t_p9_every_request_carries_the_hud_header():
    """This promise is kept by the CLIENT, so its guard is Rust and its owning
    test is a Node check. Both are asserted here by name; the audit could not
    run the Node check (Playwright is not installed - uikit.mjs exits without
    it), and the report says so rather than implying a red run happened.

    The backend's half is checked too: a request with no Origin is accepted
    only when it carries `X-Jarvis-Client: hud`, which is what forces a CORS
    preflight. **No test would go red if that line alone were deleted** - the
    report carries that as a finding."""
    rust = REPO / "jarvis-desktop" / "src-tauri" / "src" / "commands.rs"
    if not rust.is_file():
        skip("the desktop's header builder is readable", f"no {rust}")
    else:
        text = _text(rust)
        check('commands.rs still sets the client name to "hud"',
              'const JARVIS_CLIENT: &str = "hud";' in text)
        check("commands.rs still builds every request's headers in one place",
              "pub fn jarvis_headers(" in text)
    mjs = REPO / "jarvis-desktop" / "tests" / "deep.mjs"
    if not mjs.is_file():
        skip("the Node check that owns this promise is readable", f"no {mjs}")
    else:
        check("deep.mjs still checks the header on every request",
              "send X-Jarvis-Client: hud" in _text(mjs))
    node = _defines("jarvis_hud.py", "_origin_ok")
    if node is not None:
        check("jarvis_hud._origin_ok still requires the header with no Origin",
              'X-Jarvis-Client' in ast.unparse(node),
              "this is the fallback a drive-by simple request cannot produce")


def t_p10_no_rush_latch_control_and_no_bulk_approve():
    """A widget's button is the one surface where a model chooses an action and
    a tap fires it, so the allowlist is the guard: exactly the five tile
    actions, never Approve, Deny, approve-all or anything that clears a rush
    latch. The bulk half is `decide()` taking ONE id - a decide() over a list
    would be an approve-all by another name."""
    _defines("jarvis_widgets.py", "validate")
    node = _defines("jarvis_widgets.py", "ACTIONS", "constant")
    if node is not None:
        try:
            import jarvis_widgets as W
            check("the widget buttons are still exactly the five tile actions",
                  list(W.ACTIONS) == ["focus", "timer", "brief_me",
                                      "stop_everything", "pc_play_pause"],
                  f"got {list(W.ACTIONS)}")
            for bad in ("approve", "deny", "approve_all", "clear_latch", "clear_rush"):
                try:
                    W.validate({"name": "x", "blocks": [{"type": "button", "action": bad}]})
                    refused = False
                except W.Refused:
                    refused = True
                except Exception:
                    refused = True
                check(f"a widget button cannot be {bad!r}", refused)
        except Exception as exc:
            check("jarvis_widgets can be imported from the backend folder", False,
                  f"{type(exc).__name__}: {exc}")
    src, where = _source_of("jarvis_gate.py", "decide")
    if src is None:
        skip("jarvis_gate.decide still takes one id",
             where or "jarvis_gate.py is not in the backend folder")
    else:
        args = [a.arg for a in ast.parse(src).body[0].args.args]
        check("jarvis_gate.decide still decides ONE request id",
              args[:1] == ["request_id"],
              f"a decide() over a list would be an approve-all by another name ({args})")
    _suite_has("test_widgets.py", "t_the_buttons_are_the_tile_actions")


def t_p11_crisis_is_never_learned_from_or_counted():
    """Crisis handling is the one place the project asks the model to stop
    working: no tools, nothing learned, nothing counted - and since
    2026-09-28 a thumbs-down on a crisis answer does not count toward "suggest
    the bigger model" either. The check is a pure function of the text, which
    is what makes it testable."""
    for name, kind in (("crisis", "function"), ("CRISIS_PHRASES_EN", "constant")):
        _defines("jarvis_wellbeing.py", name, kind)
    _defines("jarvis_agent.py", "note_crisis_turn")
    try:
        import jarvis_wellbeing as WB
        check("a plain crisis phrase is still recognised",
              WB.crisis("I want to end my life") is True)
        check("and an ordinary sentence is not",
              WB.crisis("I like biscuits with my tea") is False)
        check("crisis() never raises on rubbish", WB.crisis(None) is False)
    except Exception as exc:
        check("jarvis_wellbeing can be imported from the backend folder", False,
              f"{type(exc).__name__}: {exc}")
    for name in ("t_a_crisis_turn_is_excluded_from_owner_turns",
                 "t_a_crisis_answer_marked_wrong_is_not_counted"):
        _suite_has("test_wellbeing.py", name)
    _suite_has("test_auto_learn.py", "t_a_crisis_chat_is_not_put_back")


def t_p12_sensitive_facts_wait_for_a_yes():
    """Two settings and one floor: "Also remember sensitive topics
    automatically" is off by default and covers health, money and other
    sensitive topics - and passwords, PINs, account and ID numbers ALWAYS wait,
    even with that setting on. `jarvis_sensitive.always_asks` is that floor, and
    `jarvis_auto_learn.check_sensitive` is where it is applied."""
    node = _defines("jarvis_auto_learn.py", "check_sensitive")
    _defines("jarvis_sensitive.py", "always_asks")
    if node is not None:
        body = ast.unparse(node)
        check("check_sensitive still goes through the always-asks floor",
              "always_asks" in body,
              "without it, 'Also remember sensitive topics automatically' would "
              "cover passwords and PINs too")
        check("check_sensitive fails closed when jarvis_sensitive is missing",
              "not installed" in body)
    _suite_has("test_auto_learn.py", "t_sensitive_topics_wait_unless_allowed")
    _suite_has("test_auto_learn.py", "t_passwords_pins_account_and_id_numbers_always_wait")


def t_p13_a_risky_approval_needs_a_lock():
    """The approval gap's step 1 and the phone's half, all three parts.
    `approve_check` asks Windows Hello for a risky card from this PC and
    refuses if there is none; `stamp` records that THIS process accepted it;
    `jarvis_gate._approval_stamped` believes an "approved" row only when that
    stamp is there - so a row written straight into approvals.db by another
    program counts for nothing; and `_signed_check` makes a risky card approved
    from another DEVICE carry that device's signature (the Keystore key the
    fingerprint unlocks, phase 2).

    All three were broken on purpose: the stamp (3 failures in
    test_gate_outcome), the Hello prompt (14 failures in test_owner_check) and
    the signature (27 failures in test_approval_sign). What no backend test can
    cover is the phone's own fingerprint PROMPT - that is Keystore and Kotlin,
    and it lives in the app."""
    for name, kind in (("approve_check", "function"), ("is_risky", "function"),
                       ("verify", "function"), ("stamp", "function"),
                       ("take_stamp", "function"),
                       ("PC_ONLY_ACTIONS", "constant")):
        _defines("jarvis_owner_check.py", name, kind)
    src, where = _source_of("jarvis_owner_check.py", "approve_check")
    if src is not None:
        check("approve_check still asks Windows Hello for a risky card here",
              "verify(" in src, f"the prompt is gone from {where}")
        check("and still stamps what it accepted", "stamp(" in src)
    signed, swhere = _source_of("jarvis_owner_check.py", "_signed_check")
    if signed is None:
        skip("a risky approval from another device still needs that device's signature",
             swhere or "jarvis_owner_check.py is not in the backend folder")
    else:
        check("_signed_check still asks the device registry for the signature",
              "check_signed_approval(" in signed)
        check("and still fails closed when it cannot check",
              "cannot_check" in signed,
              "a check that cannot run must refuse, never wave the card through")
    gate, gwhere = _source_of("jarvis_gate.py", "_approval_stamped")
    if gate is None:
        skip("the gate still believes only a stamped approval",
             gwhere or "jarvis_gate.py is not in the backend folder")
    else:
        check("the gate still asks for the stamp before it believes a row",
              "take_stamp(" in gate,
              "an 'approved' written straight into the database would count")
    for name in ("t_a_risky_approval_from_this_pc_asks_windows_hello_first",
                 "t_no_windows_hello_no_risky_approval",
                 "t_the_gate_believes_no_approved_row_without_a_stamp"):
        _suite_has("test_owner_check.py", name)
    _suite_has("test_gate_outcome.py", "t_an_approval_nobody_stamped_is_refused")


def t_the_rest_of_the_mapping_is_still_where_it_was():
    """Some promises are owned by a second suite as well (a crisis chat not put
    back, the always-asks floor, the bulk half of approve-all). Deleting any of
    those loses half the proof, so they are checked by name too."""
    for _pid, pairs in sorted(ALSO_IN.items()):
        for suite, name in pairs:
            _suite_has(suite, name)


def t_the_guards_are_not_the_whole_story():
    """CONTROL on this suite: it must be checking a real inventory, not an
    empty one. An empty PROMISES tuple would make every loop above pass
    silently - the failure mode this file exists to catch, one level up."""
    check("the inventory is not empty", len(PROMISES) >= 10, len(PROMISES))
    check("every promise names a guard", all(p["symbols"] for p in PROMISES))
    check("every promise names a suite and a test",
          all(p["suite"] and p["tests"] for p in PROMISES))
    ids = [p["id"] for p in PROMISES]
    check("the ids are unique and ordered", ids == sorted(set(ids), key=ids.index), ids)


RUNNER = (
    t_the_promise_sentences_are_still_written,
    t_the_audit_table_is_here,
    t_p1_erase_wipes_the_words_for_good,
    t_p2_nothing_ever_auto_approves,
    t_p3_acting_is_held_on_a_stale_stream,
    t_p4_the_token_is_never_logged,
    t_p5_no_public_tunnel,
    t_p6_own_networks_only,
    t_p7_keys_are_not_written_in_plain_text,
    t_p8_a_client_never_does_speech_to_text,
    t_p9_every_request_carries_the_hud_header,
    t_p10_no_rush_latch_control_and_no_bulk_approve,
    t_p11_crisis_is_never_learned_from_or_counted,
    t_p12_sensitive_facts_wait_for_a_yes,
    t_p13_a_risky_approval_needs_a_lock,
    t_the_rest_of_the_mapping_is_still_where_it_was,
    t_the_guards_are_not_the_whole_story,
)


def main():
    print(f"product modules: {BACKEND}")
    print(f"this repository: {REPO}")
    for fn in RUNNER:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed"
          + (f", {len(SKIPPED)} skipped (not proven here)" if SKIPPED else ""))
    if SKIPPED:
        print("skipped (nothing was claimed about these):")
        for s in SKIPPED:
            print(f"  - {s}")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
