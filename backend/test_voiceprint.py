"""Write Like Me (jarvis_voiceprint.py): the stripping guarantee, the empty
block, the fail-closed scrubber guard, and the question Forget asks first.

    python3 test_voiceprint.py

What is proven, and why each one is here rather than left to a reader:

  - **NO DIGIT SURVIVES** stripping, for every row of the module's own
    docstring table and for the wider corpus below. This is the spine: the
    earlier engine left the day of a slash-date, an area code, a PIN and an
    order number in the text it handed to a model, and the owner asked for
    those gaps closed (2026-10-15).
  - the docstring's table IS the measured table - parsed out of the module and
    compared row by row, so the documentation cannot drift away from the code.
  - `_DATE` runs BEFORE `_PATH`, and the wrong order really does reproduce the
    old leak. That second half is the bite-proof: a check that cannot fail is
    not a check.
  - every label is lowercase, as the brief specifies.
  - zero exemplars returns "" and the rules header is NEVER emitted without
    exemplars under it.
  - the scrubber guard FAILS CLOSED: with no jarvis_scrub, nothing is written
    and no store file appears at all.
  - a password, key or one-time code in a sample is refused.
  - Forget refuses without `"confirm": true` and the row is still there
    afterwards (the owner's 2026-09-24 decision: it asks "are you sure?"
    first, because forgetting cannot be undone).
  - the engine does NOT import jarvis_style. The owner's decision is that the
    undelivered file is left alone; a `try: import jarvis_style` fallback would
    run the OLD code on the one machine that has it.

Everything runs against a scratch store in a temporary folder. Nothing here
touches `~/.openjarvis/voiceprint.db`.
"""
import ast
import os
import re
import shutil
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, require_shipped  # noqa: E402

require_shipped("jarvis_voiceprint.py")

# The store must be scratch before the module is imported: DB_ENV is read per
# call, but a test that forgets one of these would write to the owner's folder.
# The pattern is test_receipts.py:61-66 - a folder beside this suite, made
# fresh at the start and removed at the end - rather than tempfile.mkdtemp,
# which on Windows can produce a folder the confined process cannot open.
SCRATCH = HERE / "_voiceprint_test_tmp"
shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_VOICEPRINT_DB"] = str(SCRATCH / "voiceprint.db")

import jarvis_voiceprint as V  # noqa: E402

FAILED, PASSED = [], []

#: (input, expected output). The module's docstring carries this same table;
#: `t_the_docstring_table_is_the_measured_table` proves the two agree.
TABLE = [
    ("due 14/03/2026 today", "due [date] today"),
    ("due 03/14/2026 today", "due [date] today"),
    ("due 1/2/26 today", "due [date] today"),
    ("due 14-03-2026 today", "due [date] today"),
    ("due 2026-03-14 today", "due [number] today"),
    ("Meeting moved to 9:30 on Friday.", "Meeting moved to [time] on Friday."),
    ("the file is /home/user/notes.txt", "the file is [path]"),
    ("Send it to john.smith@example.com", "Send it to [email]"),
    ("ping me @mario on https://x.example", "ping me [handle] on [link]"),
    ("The budget is $12,500.", "The budget is [amount]."),
    ("The invoice for Acme Ltd is 89.99.", "The invoice for [name] [name] is [amount]."),
    ("I paid 1,200 for the boiler.", "I paid [amount] for the boiler."),
    ("I paid 4500 for the boiler.", "I paid [number] for the boiler."),
    ("The PIN is 4821.", "The PIN is [number]."),
    ("Order 55123 arrived.", "Order [number] arrived."),
    ("My postcode is CB1 2AB.", "My postcode is [postcode]."),
    ("Ring the dentist on 01223 456789.", "Ring the dentist on [number]."),
    ("Priya's number is 07700 900123.", "[name] number is [number]."),
    ("Account 44332211 with Barclays.", "Account [number] with [name]."),
    ("Send it to 12 Oak Street, Cambridge.", "Send it to [number] [name] [name], [name]."),
]

#: The cases Phase 1 measured as leaks in the earlier engine, named one by one
#: so a regression here is visible by name rather than as one aggregate number.
LEAK_CASES = [
    "due 14/03/2026 today",
    "due 03/14/2026 today",
    "due 1/2/26 today",
    "I paid 4500 for the boiler.",
    "I paid 1,200 for the boiler.",
    "The invoice for Acme Ltd is 89.99.",
    "The PIN is 4821.",
    "Order 55123 arrived.",
    "My postcode is CB1 2AB.",
    "Meeting moved to 9:30 on Friday.",
    "Ring the dentist on 01223 456789.",
    "Priya's number is 07700 900123.",
    "Send it to 12 Oak Street, Cambridge.",
]

#: Wider corpus: real-shaped prose, so the guarantee is not only about the
#: twenty rows somebody thought to write down.
WIDER = [
    "Invoice 88421 is due on 30/11/2026, reference AB-9931.",
    "Call me on +44 7700 900123 or 0161 496 0000.",
    "The meeting is at 14:45 in room 12, then 9.30am tomorrow.",
    "Budget approved: GBP 24,000, or about 18,750 after VAT at 20%.",
    "Server 10.0.0.4:8080 returned 503 twice on 2026-01-02 at 08:15.",
    "My NI number is QQ123456C and my postcode SW1A 1AA.",
    "Order #100234567 shipped from unit 4, 221B Baker Street.",
    "Version 3.11.2 fixed 17 of 22 issues (77.3%).",
]

#: The earlier engine's substitution order, kept here as the CONTROL. Applying
#: _PATH before _DATE is what produced 'due 14[path] today'; if this control
#: ever stops reproducing the leak, the bug is gone for a different reason and
#: the assertion below it is testing nothing.
_WRONG_ORDER = (V._URL, V._EMAIL, V._PATH, V._HANDLE, V._MONEY, V._DATE,
                V._PHONE, V._LONGNUM)


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _digits(text: str) -> str:
    return "".join(ch for ch in (text or "") if ch.isdigit())


def t_no_digit_survives_the_table():
    for raw, want in TABLE:
        got, _n = V.strip_entities(raw)
        check(f"no digit survives: {raw!r}", not _digits(got), f"got {got!r}")
        check(f"and the text is what the table says: {raw!r}", got == want,
              f"got {got!r}\nwant {want!r}")


def t_no_digit_survives_the_leak_cases_by_name():
    for raw in LEAK_CASES:
        got, _n = V.strip_entities(raw)
        check(f"closed leak: {raw!r}", not _digits(got), f"got {got!r}")


def t_no_digit_survives_the_wider_corpus():
    for raw in WIDER:
        got, _n = V.strip_entities(raw)
        check(f"wider corpus: {raw!r}", not _digits(got), f"got {got!r}")


def t_no_digit_survives_the_module_docstring():
    # The strongest form: every line of the module's own prose, stripped.
    dirty = [ln for ln in (V.__doc__ or "").splitlines()
             if V.has_digits(V.strip_entities(ln)[0])]
    check("every line of the module docstring strips to no digits", not dirty,
          f"{len(dirty)} line(s), first: {dirty[:1]}")


def t_the_docstring_table_is_the_measured_table():
    """Parse the table out of the docstring and compare it with TABLE."""
    def unquote(s: str):
        s = s.strip()
        for q in ("'", '"'):
            if len(s) > 1 and s.startswith(q) and s.endswith(q):
                return s[1:-1]
        return None

    parsed, unparsed = [], []
    for line in (V.__doc__ or "").splitlines():
        m = re.match(r"^\s{4}(\S.*?)\s{2,}(\S.*?)\s*$", line)
        if not m:
            continue
        left, right = unquote(m.group(1)), unquote(m.group(2))
        if left is None or right is None:
            continue
        (parsed if left and right else unparsed).append((left, right))
    check("the docstring's table was parsed at all (else this proves nothing)",
          len(parsed) >= len(TABLE), f"parsed {len(parsed)} row(s)")
    check("the docstring's table IS the measured table, row for row",
          parsed == TABLE,
          f"only in docstring: {[r for r in parsed if r not in TABLE]}; "
          f"only in the suite: {[r for r in TABLE if r not in parsed]}; "
          f"unparsed: {unparsed}")


def t_a_slash_date_does_not_leak_its_leading_number():
    for raw in ("due 14/03/2026 today", "due 03/14/2026 today", "due 1/2/26 today"):
        got, _n = V.strip_entities(raw)
        check(f"{raw!r} becomes [date], not a path with the day left in front",
              got == "due [date] today", f"got {got!r}")


def t_the_date_runs_before_the_path():
    # The ORDER, asserted directly...
    order = [rx for rx, _lab in V.SUBSTITUTIONS]
    check("_DATE is applied before _PATH", order.index(V._DATE) < order.index(V._PATH),
          f"date at {order.index(V._DATE)}, path at {order.index(V._PATH)}")
    # ...and the bite-proof: the wrong order really does reproduce the leak.
    control = "due 14/03/2026 today"
    for rx, lab in zip(_WRONG_ORDER,
                       ("[link]", "[email]", "[path]", "[handle]", "[amount]",
                        "[date]", "[number]", "[number]")):
        control = rx.sub(lab, control)
    check("the control (date AFTER path) still reproduces the old leak",
          control == "due 14[path] today",
          f"the control produced {control!r}; if this is not the old leak, the "
          f"assertion above is not proving what it claims")


def t_labels_are_lowercase():
    labels = {lab for _rx, lab in V.SUBSTITUTIONS}
    check("every substitution label is lowercase and bracketed",
          all(lab == lab.lower() and lab.startswith("[") and lab.endswith("]")
              for lab in labels), f"{sorted(labels)}")
    check("no output label is ever uppercase", not any(
        lab != lab.lower() for _rx, lab in V.SUBSTITUTIONS))
    for raw, want in TABLE:
        got, _n = V.strip_entities(raw)
        check(f"lowercase only in {raw!r}", want == got, f"got {got!r}")
    check("the carried set is the 8 the earlier engine had, plus the new ones",
          len(V.SUBSTITUTIONS) == 11, f"{len(V.SUBSTITUTIONS)}")


def t_zero_exemplars_returns_empty():
    class Empty:
        def search(self, q, k=8, **kw):
            return []

    check("prompt_block with zero exemplars is the empty string",
          V.prompt_block("anything", store=Empty()) == "",
          repr(V.prompt_block("anything", store=Empty())))
    check("exemplars() with zero rows is an empty list",
          V.exemplars("anything", store=Empty()) == [])
    check("...and with an empty question too", V.prompt_block("", store=Empty()) == "")


def t_no_rules_header_without_exemplars():
    class Empty:
        def search(self, q, k=8, **kw):
            return []

    class One:
        def search(self, q, k=8, **kw):
            return [{"text": "Thanks for the note about the trip, I will sort it Friday.",
                     "source": "memory", "at": 1.0}]

    rules = V.rules_block()
    check("the rules header is a real, non-empty block", bool(rules.strip()))
    for question in ("", "anything", "a very specific question about Lisbon"):
        block = V.prompt_block(question, store=Empty())
        check(f"no rules header with no exemplars under it: {question!r}",
              rules not in block, repr(block[:120]))
        check(f"and the block is empty: {question!r}", block == "")
    block = V.prompt_block("Lisbon", store=One())
    check("with an exemplar, the rules header IS there", rules in block, repr(block[:160]))
    check("and the exemplar is under it", "[name] trip" in block or "trip" in block,
          repr(block))


def t_the_scrub_guard_fails_closed():
    real = V._scrubber
    fresh = SCRATCH / "never-written.db"
    if fresh.exists():
        fresh.unlink()
    os.environ["JARVIS_VOICEPRINT_DB"] = str(fresh)
    # NOTE: V.count() would itself open (and so create) the store, so the
    # existence check has to come before anything touches it.
    check("the scratch store does not exist yet", not fresh.exists(), f"{fresh}")
    try:
        V._scrubber = lambda: None
        check("no scrubber: the module knows it", V._scrubber() is None)
        check("no scrubber: add() writes nothing", V.add(V.KIND_SAMPLE, "Hello there.") == "")
        check("no scrubber: the store file was never created", not fresh.exists(),
              f"{fresh} exists")
        check("no scrubber: the count did not move", V.count() == 0, f"{V.count()}")
        code, out = V.handle_post(V.SAMPLE_PATH, {"text": "Hello there."})
        check("no scrubber: the route refuses rather than pretending",
              code == 503 and out.get("error") == "no_scrubber", f"{code} {out}")
    finally:
        V._scrubber = real
        os.environ["JARVIS_VOICEPRINT_DB"] = str(SCRATCH / "voiceprint.db")


def t_a_secret_is_never_stored():
    real = V._secret_in
    try:
        # Stand in for the project's own reader, so this test does not depend
        # on the shape of a real key.
        V._secret_in = lambda text: "hunter2" in text
        before = V.count()
        code, out = V.handle_post(V.SAMPLE_PATH,
                                 {"text": "my password is hunter2 by the way"})
        check("a sample holding a secret is refused", code == 400 and out.get("error") == "secret",
              f"{code} {out}")
        check("and nothing was written", V.count() == before)
        code, out = V.handle_post(V.EDIT_PATH,
                                 {"before": "draft", "after": "my password is hunter2"})
        check("an edit holding a secret is refused too",
              code == 400 and out.get("error") == "secret", f"{code} {out}")
        direct_before = V.count()
        check("add() ITSELF refuses a secret, not only the route",
              V.add(V.KIND_SAMPLE, "my password is hunter2 by the way") == "")
        check("... and a direct call wrote nothing", V.count() == direct_before)
    finally:
        V._secret_in = real


def t_exemplars_reads_the_owners_own_samples():
    """2026-10-20 audit Part I, catch 2A: exemplars() never queried
    voiceprint.db, so every calibration sample and edited draft the owner saved
    was invisible to prompt_block()."""
    class Empty:
        def search(self, q, k=8, **kw):
            return []

    sid = V.add(V.KIND_SAMPLE,
                "I will send the budget tomorrow morning as agreed.")
    check("the sample was stored in voiceprint.db", bool(sid), repr(sid))
    out = V.exemplars("budget tomorrow", store=Empty())
    check("exemplars() finds the owner's stored sample with NO memory store",
          any("budget" in e.text for e in out),
          [e.text[:60] for e in out])
    check("... and the returned text has been entity-stripped",
          all(not any(ch.isdigit() for ch in e.text) for e in out),
          [e.text[:60] for e in out])


def t_a_remote_device_cannot_add_or_forget():
    """2026-10-20 audit Part I, catch 2C: mutating POSTs must be this PC only."""
    class Remote(FakeHandler):
        client_address = ("100.101.102.103", 5555)

        class connection:                     # noqa: N801 - handler attribute
            @staticmethod
            def getsockname():
                # A DIFFERENT address from the caller's: the PC's own LAN
                # address, so only the peer can look like a phone on the mesh.
                return ("192.168.1.10", 4719)

    before = V.count()
    V.install(Remote, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: b'{"text": "A sample a phone tried to add."}')
    h = Remote()
    h.path = V.SAMPLE_PATH
    h.do_POST()
    check("a mutating POST from another device is refused",
          h.sent[0] == 403, getattr(h, "sent", None))
    check("... and nothing was written", V.count() == before)


def t_a_sample_is_learned_and_listed():
    sid = V.add(V.KIND_CALIBRATION, "A short message asking them to be quick about it.",
                prompt="a message")
    check("a sample gets an id", bool(sid), repr(sid))
    rows = V.samples()
    check("it is in the list", any(r["id"] == sid for r in rows), f"{rows[:1]}")
    check("the list carries the text and the kind",
          any(r["id"] == sid and r["kind"] == V.KIND_CALIBRATION for r in rows))
    prof = V.profile()
    check("a voiceprint can be worked out once there is a sample",
          bool(prof) and prof.get("words", 0) > 0, f"{prof}")
    got = V.score_style_compliance("A short message asking them to be quick about it.", prof)
    check("a text identical to the sample scores at the top",
          got.get("score") == 1.0, f"{got}")
    return sid


def t_forget_asks_first():
    sid = V.add(V.KIND_SAMPLE, "Something I would like to be able to forget later.")
    check("there is something to forget", bool(sid))
    out = V.forget(sid)
    check("forget without confirm refuses", out.get("ok") is False, f"{out}")
    check("...and says what is missing", out.get("needs") == "confirm", f"{out}")
    check("...and says why in plain words",
          "cannot be undone" in str(out.get("message", "")), f"{out}")
    check("...and the sample is STILL there", any(r["id"] == sid for r in V.samples()))
    out = V.forget(sid, confirm=True)
    check("forget with confirm goes through", out.get("ok") is True, f"{out}")
    check("...and the sample is gone", not any(r["id"] == sid for r in V.samples()))
    check("forgetting the same id again is refused, not an error",
          V.forget(sid, confirm=True).get("ok") is False)


def t_forget_asks_first_over_the_route():
    sid = V.add(V.KIND_SAMPLE, "A second thing, reached through the route this time.")
    h = FakeHandler()
    h.path = V.FORGET_PATH
    h.body = {}
    code, out = h.do_POST()
    check("the route refuses an unconfirmed forget", out.get("ok") is False and out.get("needs") == "confirm",
          f"{code} {out}")
    check("...and the row survived the refusal", any(r["id"] == sid for r in V.samples()))
    h.body = {"id": sid, "confirm": True}
    code, out = h.do_POST()
    check("the route forgets with confirm: true", out.get("ok") is True, f"{code} {out}")
    check("...and the row is gone", not any(r["id"] == sid for r in V.samples()))


def t_the_engine_does_not_import_jarvis_style():
    """The owner's decision, as a check: jarvis_style.py is undelivered, so
    importing it here would run the OLD code on the owner's PC."""
    src = (BACKEND / "jarvis_voiceprint.py").read_text(encoding="utf-8")
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    check("jarvis_voiceprint does not import jarvis_style", "jarvis_style" not in names,
          f"imports: {sorted(n for n in names if n.startswith('jarvis_'))}")
    # "not even inside a try": ast.walk finds an import wherever it is nested,
    # so the check above already covers a lazy import. This second check looks
    # at the string constants, where a bare name would also be a coupling - and
    # it deliberately ignores the docstring, which QUOTES the forbidden import
    # while explaining why it is forbidden.
    strings = {n.value for n in ast.walk(ast.parse(src))
               if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    check("...and no string constant names it either", "jarvis_style" not in strings,
          f"{sorted(s for s in strings if 'jarvis' in str(s))[:4]}")


def t_compute_voiceprint_is_pure_and_total():
    empty = V.compute_voiceprint([])
    check("an empty input gives numbers, not an exception",
          isinstance(empty, dict) and empty.get("documents") == 0, f"{empty}")
    check("...with the same keys a real one has",
          set(empty) == set(V.compute_voiceprint("One short sentence.")), f"{sorted(empty)}")
    a = V.compute_voiceprint("One short sentence. Another one, with a comma.")
    b = V.compute_voiceprint("One short sentence. Another one, with a comma.")
    check("the same text gives the same numbers twice", a == b)
    check("a sentence count is really counted", a["sentences"] == 2, f"{a['sentences']}")
    check("questions are counted", V.compute_voiceprint("Is it? Yes.")["questions_per_100_sentences"] == 50.0)
    check("no profile means no score, said in words",
          V.score_style_compliance("anything", {})["score"] is None)
    check("ten calibration prompts, as the design says",
          len(V.CALIBRATION_PROMPTS) == 10, f"{len(V.CALIBRATION_PROMPTS)}")


def t_the_install_wraps_both_verbs_and_is_idempotent():
    class Fresh:
        def do_GET(self):
            return "orig-get"

        def do_POST(self):
            return "orig-post"

        def _send(self, code, out):
            self.sent = (code, out)
            return code, out

    first = V.install(Fresh, origin_ok=lambda h: True, token_ok=lambda h: True,
                      read_body=lambda h: b"{}")
    check("install() says what it did", isinstance(first, str) and "voiceprint" in first, first)
    check("it wrapped do_GET", getattr(Fresh.do_GET, "_jarvis_voiceprint", False))
    check("it wrapped do_POST", getattr(Fresh.do_POST, "_jarvis_voiceprint", False))
    second = V.install(Fresh, origin_ok=lambda h: True, token_ok=lambda h: True,
                       read_body=lambda h: b"{}")
    check("installing twice is harmless and says so", "already on" in second, second)
    h = Fresh()
    h.path = "/api/voiceprint"
    code, out = h.do_GET()
    check("GET /api/voiceprint is answered here", code == 200 and out.get("ok") is True,
          f"{code} {out}")
    check("...and it carries the samples, the voiceprint and the status",
          {"samples", "voiceprint", "status"} <= set(out), f"{sorted(out)}")
    h.path = "/api/something/else"
    check("every other GET goes straight to the original", h.do_GET() == "orig-get")
    h.path = "/api/something/else"
    check("every other POST goes straight to the original", h.do_POST() == "orig-post")


def t_a_cross_origin_request_is_refused():
    class Fresh:
        def do_GET(self):
            return "orig-get"

        def do_POST(self):
            return "orig-post"

        def _send(self, code, out):
            self.sent = (code, out)
            return code, out

    V.install(Fresh, origin_ok=lambda h: False, token_ok=lambda h: True,
              read_body=lambda h: b"{}")
    h = Fresh()
    h.path = "/api/voiceprint"
    # A refusal sends its own reply and returns None, so the reply is read from
    # the handler rather than from the return value (jarvis_receipts' shape).
    h.do_GET()
    code, out = h.sent
    check("a cross-origin request is refused before anything is read",
          code == 403, f"{code} {out}")


class FakeHandler:
    """The two verbs `install()` wraps, with `_send` recording the reply."""
    path = "/"
    body = {}
    client_address = ("127.0.0.1", 5555)

    class connection:                         # noqa: N801 - handler attribute
        @staticmethod
        def getsockname():
            return ("127.0.0.1", 4719)

    def do_GET(self):
        return "orig-get"

    def do_POST(self):
        return "orig-post"

    def _send(self, code, out):
        self.sent = (code, out)
        return code, out


def t_sentence_opening_names_are_stripped():
    """Area 5 / Write-Like-Me audit: names open sentences constantly. All four
    rules replace the name; It's/Thanks and the no-digit rule survive."""
    cases = (
        ("Priya's number is 01223 456789.", "Priya", "[name]"),
        ("Sam, can you send the report?", "Sam", "[name]"),
        ("Hi Sam, can you send the report?", "Sam", "[name]"),
        ("Dr. Patel called at 9:30.", "Patel", "[name]"),
        ("Sam said hello. Sam left.", "Sam", "[name]"),
    )
    for src, name, label in cases:
        out, count = V.strip_entities(src)
        check(f"the opening name in {src!r} is gone", name not in out, out)
        check(f"... and replaced with {label}", label in out, out)
        check(f"... and no digit survives ({src!r})", not V.has_digits(out), out)
        check(f"... and the replacement was counted ({src!r})", count >= 1, count)
    for kept in ("It's ready.", "Thanks, I'll check."):
        out, _n = V.strip_entities(kept)
        check(f"{kept!r} is left intact", kept.split(",")[0] in out, out)
        check(f"... and still has no digit ({kept!r})", not V.has_digits(out), out)


def t_a_leaked_placeholder_is_flagged_by_the_scorer():
    profile = V.compute_voiceprint(["A normal sentence. Another short one."])
    good = V.score_style_compliance("A normal sentence.", profile)
    check("a clean draft reports no leaked placeholder", good.get("leaked_placeholder") is False,
          good.get("leaked"))
    bad = V.score_style_compliance("Hi [name], the amount is [amount].", profile)
    check("a draft carrying a stripped placeholder is FLAGGED",
          bad.get("leaked_placeholder") is True, bad.get("leaked"))
    check("... and its score is zero whatever else it reads like",
          bad.get("score") == 0.0, bad.get("score"))
    check("... and the leaked tokens are named",
          set(bad.get("leaked") or []) == {"[name]", "[amount]"}, bad.get("leaked"))


def t_control_markers_never_reach_the_store():
    V.add(V.KIND_SAMPLE, "<|im_start|>Hello 12345<tool_call> world<think>not a thought")
    rows = V.samples()
    text = rows[0]["text"] if rows else ""
    check("a stored sample has no chat-control marker",
          "<|im_start|>" not in text and "<tool_call>" not in text
          and "<think>" not in text, text)
    check("... and the sample is still readable text", "Hello" in text and "world" in text,
          text)


def t_drafting_request_and_register_are_narrow():
    for text in ("draft an email to Sam about the budget",
                 "write this in my voice",
                 "rewrite it in my own voice",
                 "reply to the client"):
        check(f"a drafting request is recognised: {text!r}", V.drafting_request(text))
    for text in ("what is the weather", "how many files are there", "turn off the lights"):
        check(f"an ordinary question is NOT drafting: {text!r}",
              V.drafting_request(text) is False)
    check("work email register", V.infer_register("draft an email to the client") == "work_email")
    check("casual register", V.infer_register("text my friend a message") == "casual_text")
    check("pushback register", V.infer_register("write a reply to decline the offer") == "firm_pushback")
    check("technical register", V.infer_register("write the api spec document") == "technical_doc")
    check("default register", V.infer_register("write this in my voice") == "general")
    check("the register set is the closed one the audit names",
          set(V.REGISTERS) == {"general", "casual_text", "work_email",
                               "technical_doc", "firm_pushback"})


def t_drafting_block_is_guarded_and_latches_only_when_used():
    import types
    store = types.SimpleNamespace(search=lambda q, k=0: [
        {"text": "A sentence written with enough words to carry a real style.", "source": "memory"}])
    real_cfg, real_count = V._cfg, V.count
    V._cfg = lambda key, default: (True if key == "enabled" else real_cfg(key, default))
    V.count = lambda: 2
    calls = []
    real = V._latch
    V._latch = lambda why="": calls.append(why)
    try:
        block = V.drafting_block("draft an email to Sam", store=store)
        check("enabled + a sample injects a style block",
              bool(block) and "Here is how the owner has written" in block, block[:90])
        check("... and the block is the rules + examples", "- " in block, block)
        check("... and the turn is latched local exactly once",
              calls == ["voiceprint_exemplars"], calls)

        calls.clear()
        check("Temporary chat injects NOTHING",
              V.drafting_block("draft an email", temporary=True, store=store) == "")
        check("... and a Temporary turn does not latch", calls == [], calls)

        check("an external-chatbot path injects NOTHING",
              V.drafting_block("draft an email", external=True, store=store) == "")
        check("... and the external path does not latch", calls == [], calls)

        V._cfg = lambda key, default: (False if key == "enabled" else real_cfg(key, default))
        check("the feature OFF injects nothing",
              V.drafting_block("draft an email", store=store) == "")
        check("... and OFF does not latch", calls == [], calls)
        V._cfg = lambda key, default: (True if key == "enabled" else real_cfg(key, default))

        V.count = lambda: 0
        check("no stored sample injects nothing",
              V.drafting_block("draft an email", store=store) == "")
        check("... and no sample does not latch", calls == [], calls)
    finally:
        V._latch = real
        V._cfg, V.count = real_cfg, real_count


if __name__ == "__main__":
    # The routes need the real wrapper in place for the two route tests.
    V.install(FakeHandler, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=lambda h: __import__("json").dumps(h.body).encode())
    for fn in (t_no_digit_survives_the_table,
               t_no_digit_survives_the_leak_cases_by_name,
               t_no_digit_survives_the_wider_corpus,
               t_no_digit_survives_the_module_docstring,
               t_the_docstring_table_is_the_measured_table,
               t_a_slash_date_does_not_leak_its_leading_number,
               t_the_date_runs_before_the_path,
               t_labels_are_lowercase,
               t_zero_exemplars_returns_empty,
               t_no_rules_header_without_exemplars,
               t_the_scrub_guard_fails_closed,
               t_a_secret_is_never_stored,
               t_exemplars_reads_the_owners_own_samples,
               t_a_remote_device_cannot_add_or_forget,
               t_a_sample_is_learned_and_listed,
               t_forget_asks_first,
               t_forget_asks_first_over_the_route,
               t_the_engine_does_not_import_jarvis_style,
               t_compute_voiceprint_is_pure_and_total,
               t_the_install_wraps_both_verbs_and_is_idempotent,
               t_a_cross_origin_request_is_refused,
               t_drafting_request_and_register_are_narrow,
               t_drafting_block_is_guarded_and_latches_only_when_used,
               t_sentence_opening_names_are_stripped,
               t_a_leaked_placeholder_is_flagged_by_the_scorer,
               t_control_markers_never_reach_the_store):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    # Leave no scratch behind, exactly as test_receipts.py:792 does.
    os.environ["JARVIS_VOICEPRINT_DB"] = str(SCRATCH / "voiceprint.db")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    sys.exit(1 if FAILED else 0)
