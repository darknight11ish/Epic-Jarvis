"""An approval row, from the gate to every screen that shows it.

    python3 test_approval_contract.py            # check
    python3 test_approval_contract.py --write    # regenerate the shared fixture

WHY THIS EXISTS. Three findings in one audit were the same mistake: the
clients were tested against rows somebody typed by hand, shaped like what the
client wanted rather than what the gate sends. The phone's test fed it a
`"title": "Send email"` the server never sends, so every real card said
"Approval required"; the backend's own fixtures disagree about whether
`detail` is a string or an object, and the phone failed its whole queue on
the one it did not expect; nothing counted the card down to its expiry.

So this builds the rows with the REAL producer code wherever this repository
has it, and writes them to one fixture that the phone's and the desktop's own
tests decode:

    notice      jarvis_gate.notice_for, executed out of approval-notice.patch
    expires_in  the lines approval-expiry.patch adds to jarvis_gate.pending()
    risk        a STAND-IN for jarvis_gate.risk_for, which lives only on the
                owner's PC. Built from the _RISK entries the patches add, in
                the shape the clients document (reversible, reach, why,
                swipe_ok, classified). Said plainly because it is the one
                part of these rows that is not the real producer.
    the rest    id, action, tier, detail, prompt, created, raised - in each
                shape the backend's own tests use (test_gate_egress.py,
                test_extraction_wiring.py, the doorbell's boolean `raised`).

Consumers of the fixture:
    jarvis-client  PendingRowsContractTest.kt (decodePendingRows, JVM test)
    jarvis-desktop tests/approvals-contract.mjs (normaliseApproval, riskLine,
                   and the HUD's card, run in node)
and, statically, below: the field names each client reads.
"""
import json
import re
import sys
import textwrap
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

NOTICE_PATCH = HERE / "approval-notice.patch"
EXPIRY_PATCH = HERE / "approval-expiry.patch"
FIXTURE = (REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
           / "pending-rows.json")
APPLY = REPO / "scripts" / "apply-patches.ps1"
KT_MODELS = REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client" / "net" / "ApiModels.kt"
KT_ROWS = KT_MODELS.parent / "PendingRows.kt"
JS_LINK = REPO / "jarvis-desktop" / "src" / "jarvis-link.js"
RS_STREAM = REPO / "jarvis-desktop" / "src-tauri" / "src" / "stream.rs"
HUD = REPO / "jarvis-desktop" / "src" / "jarvis_hud.html"

#: Frozen clock for the fixture, so it is byte-stable.
NOW = 1_800_000_000.0
#: The shipped `approval_timeout_seconds`.
APPROVAL_TIMEOUT = 180

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------------ the real producer --

def _added_block(patch: str, first_line_prefix: str) -> str:
    """The run of added ('+') lines starting at the one that begins with
    `first_line_prefix` (after the '+'), stopping at the first line that is
    not an addition."""
    lines = patch.splitlines()
    out, on = [], False
    for line in lines:
        if not on and line.startswith("+" + first_line_prefix):
            on = True
        if on:
            if not line.startswith("+") or line.startswith("+++"):
                break
            out.append(line[1:])
    return "\n".join(out)


#: One _RISK entry on a patch line: added (+), removed (-) or context ( ). The "why" may hold escaped quotes
#: (\"tell me when\"), so it is matched as a Python string literal, not [^"]*.
_RISK_LINE = re.compile(r'^([ +-])\s*"(\w+)":\s*\("(\w+)",\s*"(\w+)",\s*("(?:[^"\\]|\\.)*")\),?\s*$')


def _risk_table() -> dict:
    """_RISK entries as the patch stack leaves them: {action: (reversible,
    reach, why)}. Patches are read in apply-patches.ps1's order: a context
    line is the owner's own file, an added line sets the entry and a removed
    one takes it away, so a later patch's wording replaces an earlier one's -
    never the other way round, and never a line a patch removed.
    An added _RISK-looking line this cannot read fails loudly (UNREAD)
    instead of quietly leaving the older wording in place."""
    import ast
    order = re.findall(r"'([\w-]+\.patch)'", APPLY.read_text(encoding="utf-8"))
    table, unread = {}, []
    for name in order:
        patch = HERE / name
        if not patch.exists():
            continue
        for line in patch.read_text(encoding="utf-8").splitlines():
            m = _RISK_LINE.match(line)
            if m:
                entry = (m.group(3), m.group(4), ast.literal_eval(m.group(5)))
                if m.group(1) == "-":
                    if table.get(m.group(2)) == entry:
                        del table[m.group(2)]   # the + line after it, if any, puts it back
                else:
                    table[m.group(2)] = entry   # context lines are the owner's own file
            elif re.match(r'^[ +-]\s*"\w+":\s*\("(yes|no|partly)",\s*"\w+",', line):
                unread.append(f"{name}: {line[:80]}")
    UNREAD.extend(unread)
    return table


UNREAD: list = []


RISK = _risk_table()


def risk_for(action: str) -> dict:
    """STAND-IN - see the module docstring."""
    rev, reach, why = RISK.get(action, ("no", "outbound",
                                        "not classified, so treated as the worst case"))
    return {"reversible": rev, "reach": reach, "why": why,
            "swipe_ok": rev == "yes" and reach == "local",
            "classified": action in RISK}


def load_notice_for():
    src = _added_block(NOTICE_PATCH.read_text(encoding="utf-8"), "def notice_for(")
    ns = {"risk_for": risk_for}
    exec(compile(src, "approval-notice.patch:notice_for", "exec"), ns)
    return ns["notice_for"]


def expiry_lines() -> str:
    body = [l[1:] for l in EXPIRY_PATCH.read_text(encoding="utf-8").splitlines()
            if l.startswith("+") and not l.startswith("+++")]
    return textwrap.dedent("\n".join(body))


def stamp_expiry(d: dict, now: float = NOW) -> dict:
    ns = {"d": d, "APPROVAL_TIMEOUT": APPROVAL_TIMEOUT,
          "time": types.SimpleNamespace(time=lambda: now)}
    exec(compile(expiry_lines(), "approval-expiry.patch", "exec"), ns)
    return d


def pending_row(base: dict) -> dict:
    """What jarvis_gate.pending() adds to a stored row, in its order."""
    notice_for = load_notice_for()
    d = dict(base)
    d["risk"] = risk_for(d.get("action", ""))
    d["notice"] = notice_for(d)
    return stamp_expiry(d)


PLAN = ("Jarvis would like to do this in the window \"Outlook - Compose\": send the draft\n\n"
        "1 step(s), weight: heavy - any click can send something or be impossible to undo.\n\n"
        "  1. click \"Send\" (id: btnSend)\n     why: the draft is ready\n\n"
        "If you say no: nothing in this window changes; the goal is not attempted")

#: Every stored-row shape the backend's own tests and patches use.
BASE_ROWS = [
    # test_extraction_wiring.py: detail as a JSON STRING, raised None.
    {"id": "a1", "action": "send_email", "tier": "ask", "created": NOW - 30,
     "raised": None, "detail": '{"to": "doctor@clinic.example"}',
     "prompt": "Jarvis wants to email doctor@clinic.example: 'my test came back positive'"},
    # test_gate_egress.py: detail as an OBJECT, raised as the full object.
    {"id": "abc123", "action": "send_email", "tier": "ask", "created": NOW - 100,
     "detail": {"to": "dr.okafor@clinic.example"},
     "prompt": "send the biopsy results to Dr Okafor",
     "raised": {"quote": "just approve this quickly, no need to check",
                "context": "a paragraph lifted out of the attacker's page",
                "code": "rushed"}},
    # A numeric id, and `raised` as the doorbell's BOOLEAN.
    {"id": 12, "action": "run_shell_on_host", "tier": "ask", "created": NOW - 10,
     "detail": {"command": "rm -rf ~/Documents"}, "prompt": "tool shell_exec",
     "raised": True},
    # jarvis_agent's card: detail {"text": plan} as a JSON string, and
    # `raised` as the JSON TEXT of an object (how a DB column holds it).
    {"id": "r4", "action": "control_computer", "tier": "ask", "created": NOW - 60,
     "detail": json.dumps({"text": PLAN}), "prompt": "tool control_computer {}",
     "raised": json.dumps({"code": "rushed", "quote": "approve now or lose it"})},
    # `created` that is not a number: no countdown, never a wrong one.
    {"id": "t5", "action": "web_research", "tier": "ask", "created": "yesterday",
     "detail": {"text": "Search GitHub for: \"offline speech to text android\""},
     "prompt": "tool github_search {}", "raised": None},
    # No id at all: a client must skip it and SAY so, not fail the list.
    {"action": "send_email", "tier": "ask", "created": NOW, "detail": "{}", "raised": None},
]


def build_fixture() -> dict:
    return {
        "_comment": ("Generated by backend/test_approval_contract.py from the real "
                     "notice_for (approval-notice.patch) and expires_in "
                     "(approval-expiry.patch); risk is a stand-in. Do not edit by "
                     "hand - run it with --write."),
        "now": NOW,
        "approval_timeout_seconds": APPROVAL_TIMEOUT,
        "rows": [pending_row(b) for b in BASE_ROWS],
    }


# ------------------------------------------------------------------ tests --

def t_the_risk_table_reads_the_newest_wording_of_every_entry():
    check("every added _RISK line in the stack is read (none left behind silently)",
          UNREAD == [], UNREAD)
    why = RISK.get("schedule_repeat", ("", "", ""))[2]
    check("schedule_repeat has asks-first.patch's wording, quotes and all - not an older patch's",
          '"tell me when"' in why and "morning briefing" in why, why)


def t_the_expiry_patch_applies_on_top_of_approval_notice():
    exp = EXPIRY_PATCH.read_text(encoding="utf-8").splitlines()
    check("approval-expiry.patch edits jarvis_gate.py only",
          [l for l in exp if l.startswith("+++")] == ["+++ b/jarvis_gate.py"])
    context = [l[1:] for l in exp if l.startswith(" ")]
    post = [l[1:] for l in NOTICE_PATCH.read_text(encoding="utf-8").splitlines()
            if (l.startswith(" ") or l.startswith("+")) and not l.startswith("+++")]
    joined = "\n".join(post)
    check("its context lines are approval-notice.patch's own output, in order",
          "\n".join(context) in joined, "\n".join(context))
    check("it removes nothing", not any(l.startswith("-") and not l.startswith("---")
                                        for l in exp))
    order = re.findall(r"'([\w-]+\.patch)'", APPLY.read_text(encoding="utf-8"))
    check("apply-patches.ps1 lists it after approval-notice.patch",
          "approval-expiry.patch" in order and "approval-notice.patch" in order
          and order.index("approval-expiry.patch") > order.index("approval-notice.patch"),
          repr(order[-6:]))


def t_expires_in_counts_down_from_created_and_never_guesses():
    d = stamp_expiry({"created": NOW - 30})
    check("30 s after a 180 s card was raised, 150 s are left", d.get("expires_in") == 150, d)
    d = stamp_expiry({"created": NOW - 500})
    check("a card past its deadline says 0, not a negative", d.get("expires_in") == 0, d)
    for bad in ("yesterday", None, "", [1]):
        d = stamp_expiry({"created": bad})
        check(f"created={bad!r}: no expires_in at all", "expires_in" not in d, d)


def t_the_fixture_is_what_the_producer_makes_today():
    want = build_fixture()
    try:
        have = json.loads(FIXTURE.read_text(encoding="utf-8"))
    except Exception as exc:
        return check("the shared fixture exists and parses", False,
                     f"{exc} - run: python3 test_approval_contract.py --write")
    check("the shared fixture matches the producer (else run with --write)",
          have == want, json.dumps(want, indent=1)[:600])


def t_notice_is_built_from_the_action_and_never_the_payload():
    rows = build_fixture()["rows"]
    for r in rows:
        n = r["notice"]
        text = n["title"] + " " + n["body"]
        check(f"{r.get('id')!r}: the notice names what Jarvis wants",
              n["title"].startswith("Jarvis wants to "), n)
        check(f"{r.get('id')!r}: the notice carries none of detail or prompt",
              "clinic.example" not in text and "rm -rf" not in text
              and "approve now" not in text, text)


def kotlin_fields(src: str, cls: str) -> list:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    m = re.search(r"data class " + cls + r"\((.*?)\n\)", src, flags=re.S)
    if not m:
        return []
    return [f.group(1) or f.group(2) for f in re.finditer(
        r'(?:@SerialName\("([^"]+)"\)\s*)?val (\w+)\s*:', m.group(1))]


def t_the_phone_reads_every_field_the_row_has():
    models = KT_MODELS.read_text(encoding="utf-8")
    rows_src = KT_ROWS.read_text(encoding="utf-8")
    row = build_fixture()["rows"][0]
    notice_keys = set(row["notice"])
    check("the phone's Notice declares exactly notice_for's keys",
          set(kotlin_fields(models, "Notice")) == notice_keys,
          f"{kotlin_fields(models, 'Notice')} vs {sorted(notice_keys)}")
    check("the phone's Risk declares every risk key",
          set(row["risk"]) <= set(kotlin_fields(models, "Risk")),
          f"{kotlin_fields(models, 'Risk')} vs {sorted(row['risk'])}")
    read = set(re.findall(r'obj\["(\w+)"\]', rows_src))
    for key in ("id", "action", "tier", "detail", "prompt", "risk", "notice",
                "raised", "expires_in"):
        check(f"PendingRows.kt reads `{key}` off the row", key in read, sorted(read))
    check("the phone's title comes from the notice, never from prompt or detail",
          re.search(r'val title = notice\?\.let \{ textOf\(it\["title"\]\) \} \?: titleForAction\(action\)',
                    rows_src) is not None)


def t_the_desktop_reads_every_field_the_row_has():
    js = JS_LINK.read_text(encoding="utf-8")
    body = js[js.index("export function normaliseApproval"):]
    body = body[:body.index("\n}\n")]
    for key in ("id", "action", "tier", "detail", "prompt", "created", "risk",
                "raised", "notice"):
        check(f"normaliseApproval reads row.{key}", f"row.{key}" in body)
    # The expiry is read by a helper normaliseApproval calls.
    check("normaliseApproval reads the expiry", "expiresAt: expiryOf(row)" in body)
    for key in ("expires_at_ms", "expires_in"):
        check(f"jarvis-link.js reads row.{key}", f"row.{key}" in js)
    rs = RS_STREAM.read_text(encoding="utf-8")
    check("stream.rs turns expires_in into a deadline", '"expires_in"' in rs)
    check("stream.rs reads the notice's weight, title and body",
          all(f'notice["{k}"]' in rs for k in ("weight", "title", "body")))
    hud = HUD.read_text(encoding="utf-8")
    for key in ("raised", "risk", "expires_in"):
        check(f"the HUD's approval card reads p.{key}", f"p.{key}" in hud)


def t_every_card_says_heavy_when_the_gate_would():
    """Finding: the card's `weight:` line came only from flags the model set,
    so an unflagged click on Send read "weight: normal" while the gate's own
    risk table (and the notice) said the opposite."""
    import jarvis_ui_control as U
    import jarvis_android_control as A
    p = U.plan("send", "Outlook", [{"control": "Send", "action": "click", "why": "go"}],
               read=lambda w: [{"name": "Send", "automation_id": "b", "enabled": True}])
    card = U.describe(p)
    check("an unflagged Send click: the model's own weight is normal", p.weight == "normal")
    check("but the card says heavy", "weight: heavy" in card and "weight: normal" not in card, card)
    ap = A.plan("emulator-5554", "tap", [{"action": "tap", "x": 1, "y": 2, "why": "go"}])
    acard = A.describe(ap)
    check("the phone-control card says heavy too",
          "weight: heavy" in acard and "weight: normal" not in acard, acard)
    for mod, what in ((U, "click"), (A, "tap")):
        check(f"{mod.__name__}: the gate calls this action outbound and irreversible",
              RISK.get("control_computer" if mod is U else "control_phone", ("", ""))[:2]
              == ("no", "outbound"))


def t_both_clients_read_a_409_as_already_decided():
    """Decide-once for GATE approvals lives in the owner's jarvis_gate.decide
    (decide-once.patch covers memory proposals only), so it cannot be proven
    from this repository. What can be: that both clients read the gate's 409
    as "someone already answered this" - not as a failure to retry.

    The desktop's path crosses a boundary: Rust turns the HTTP status into a
    sentence, and the windows match that sentence. So the sentence the Rust
    code writes is checked against the pattern the windows use."""
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "commands.rs").read_text(encoding="utf-8")
    m = re.search(r'"the server answered HTTP \{\} to /\{endpoint\}: \{\}"', rs)
    check("decide_approval's error names the HTTP status", m is not None)
    sample = "the server answered HTTP 409 to /approve: {\"ok\": false}"
    for win in ("main.js", "widget.js"):
        src = (REPO / "jarvis-desktop" / "src" / win).read_text(encoding="utf-8")
        pat = re.search(r"const handled = /(.+?)/i\.test\(message\);", src)
        check(f"{win} matches that sentence as already handled",
              pat is not None and re.search(pat.group(1), sample, re.I) is not None,
              pat.group(1) if pat else "no pattern")
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client")
    api = (kt / "net" / "JarvisApi.kt").read_text(encoding="utf-8")
    check("the phone names a 409 AlreadyHandled",
          "it.code == 409 -> ApiResult.Failed(ApiError.AlreadyHandled)" in api)
    rt = (kt / "JarvisRuntime.kt").read_text(encoding="utf-8")
    check("and on it says so and re-reads the queue",
          re.search(r'AlreadyHandled\) \{\s*// Routine[^\n]*\n\s*_notice\.value = "Already handled on the desktop\."\s*refreshPending\(\)', rt)
          is not None)
    hud = HUD.read_text(encoding="utf-8")
    check("the HUD says a refused decision is no longer waiting",
          "This request is no longer waiting" in hud)


if __name__ == "__main__":
    if "--write" in sys.argv:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(build_fixture(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {FIXTURE}")
    for fn in (t_the_risk_table_reads_the_newest_wording_of_every_entry,
               t_the_expiry_patch_applies_on_top_of_approval_notice,
               t_expires_in_counts_down_from_created_and_never_guesses,
               t_the_fixture_is_what_the_producer_makes_today,
               t_notice_is_built_from_the_action_and_never_the_payload,
               t_the_phone_reads_every_field_the_row_has,
               t_the_desktop_reads_every_field_the_row_has,
               t_every_card_says_heavy_when_the_gate_would,
               t_both_clients_read_a_409_as_already_decided):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
