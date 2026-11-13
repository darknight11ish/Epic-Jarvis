"""Q7: the "New — currently off" pill inside Settings -> What asks first.

    python3 test_asks_first_new_off.py

THE OWNER'S RULING (2026-11-06 11:35 PT, Q7). The shipped template offers the
model 21 abilities (`[tools].enabled` in `backend/rebuilt/jarvis-framework.toml`);
the owner's live file names 14, because five were added after he last edited
that line. A feature he asked for is in the program and switched off, and
nothing tells him. The ruling: NO startup notification and NO unsolicited chat
card - instead a subtle "New — currently off" pill at the top of the tools card
in Settings -> What asks first, in both apps.

WHAT IS PROVEN HERE:

  * the 19-name constant in `jarvis_asks_first.py` is exactly the shipped
    template's own list, parsed from the template file - so the constant can
    never quietly drift from what ships;
  * with the owner's live 14-name list, the five new tools appear;
  * with a list that already contains them, none appear;
  * the payload is READ-ONLY: it writes no settings line, raises no card, and
    turning one on stays `request_tool_enable`'s one card (not this payload's).
"""
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_asks_first.py", "jarvis_home.py", "jarvis_agent.py",
                "jarvis_owner_check.py", "jarvis_card_words.py", "jarvis_local_http.py")
sys.path.append(str(HERE / "rebuilt"))

import jarvis_asks_first as AF  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-asks-first-new-off-"))
AF._config_dir = lambda: TMP


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: The five the ruling names - the packs work of 2026-11-05 and the
#: approval-policy reader.
THE_FIVE = ("approval_policy", "pack_list", "pack_inspect", "pack_install",
            "pack_remove")

#: The two local review gates the owner's Q-D/Q7 ruling enables by default in
#: BOTH shipped settings files. An EXISTING PC's file is never overwritten, so
#: the pill is exactly how a default reaches it: they are in the template and
#: absent from an older file, so they appear as "New - currently off".
REVIEW = ("review_changes", "check_records")


def template_tools() -> tuple:
    """The shipped template's own `[tools] enabled` list, in file order."""
    path = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^\[tools\][ \t]*$(.*?)(?=^\[)", text, re.M | re.S)
    if not m:
        return ()
    inside = m.group(1)
    line = re.search(r"^[ \t]*enabled[ \t]*=[ \t]*\[(?P<items>[^\[\]]*)\]",
                     inside, re.M)
    if not line:
        return ()
    return tuple(re.findall(r'"([^"]*)"', line.group("items")))


# --------------------------------------------------------------------------

def t_the_constant_is_the_shipped_template():
    names = template_tools()
    check("the shipped template's [tools] enabled list was found", bool(names),
          "no line matched; this suite is blind")
    check("the template offers 21 abilities (19 + the two review gates)",
          len(names) == 21, len(names))
    check("jarvis_asks_first.TEMPLATE_TOOLS is exactly the template's list",
          tuple(AF.TEMPLATE_TOOLS) == names, (tuple(AF.TEMPLATE_TOOLS), names))
    check("the five this build added are all in it",
          all(t in AF.TEMPLATE_TOOLS for t in THE_FIVE), THE_FIVE)


def t_with_the_live_list_the_five_and_the_review_gates_appear():
    live = tuple(t for t in AF.TEMPLATE_TOOLS
                 if t not in THE_FIVE and t not in REVIEW)
    check("the live fixture is the owner's own 14", len(live) == 14, len(live))
    rows = AF.newly_off_tools(set(live))
    ids = [r["id"] for r in rows]
    new_here = THE_FIVE + REVIEW
    check("the five new tools and the two review gates appear",
          sorted(ids) == sorted(new_here), ids)
    check("each carries a title for the pill", all(r.get("title") for r in rows), rows)
    check("in the template's own order, so the pill reads like the page",
          ids == [t for t in AF.TEMPLATE_TOOLS if t in new_here], ids)


def t_with_a_list_that_has_them_none_appear():
    check("with every shipped tool named, nothing is new",
          AF.newly_off_tools(set(AF.TEMPLATE_TOOLS)) == [],
          AF.newly_off_tools(set(AF.TEMPLATE_TOOLS)))
    rows = AF.newly_off_tools(set(THE_FIVE))
    check("with the five named, none OF THE FIVE is new",
          not [r for r in rows if r["id"] in THE_FIVE],
          [r["id"] for r in rows if r["id"] in THE_FIVE])
    check("... the rest of the template is still offered, because it is absent",
          len(rows) == len(AF.TEMPLATE_TOOLS) - len(THE_FIVE), len(rows))


def t_the_review_gates_are_offered_on_an_older_pc_template():
    """A PC whose settings file predates Q-D still gets the pill for the two
    review gates: their own file is never overwritten, so this is how "enabled
    by default" reaches an EXISTING install."""
    older = tuple(t for t in AF.TEMPLATE_TOOLS if t not in REVIEW)
    check("the older fixture is the old 19-name template", len(older) == 19,
          len(older))
    rows = AF.newly_off_tools(set(older))
    check("both review gates appear as new-and-off on an older PC",
          sorted(r["id"] for r in rows) == sorted(REVIEW),
          [r["id"] for r in rows])


def t_the_payload_carries_the_pill_and_is_read_only():
    live = tuple(t for t in AF.TEMPLATE_TOOLS if t not in THE_FIVE)
    keep = AF.tools_enabled_set
    AF.tools_enabled_set = lambda: set(live)
    wrote = []
    real_write = AF.set_tools_enabled

    def _boom(*a, **k):                     # pragma: no cover - must not run
        wrote.append((a, k))
        return {"ok": False}

    AF.set_tools_enabled = _boom
    try:
        tools = AF.tools_status(here=True)
        view = AF.view(here=True)
    finally:
        AF.tools_enabled_set = keep
        AF.set_tools_enabled = real_write
    new_off = tools.get("new_off") or {}
    check("the tools payload carries new_off", bool(new_off), sorted(tools))
    check("the pill's words are the ruling's own",
          new_off.get("label") == "New — currently off", new_off.get("label"))
    check("... with the five in it", sorted(r["id"] for r in new_off.get("items") or [])
          == sorted(THE_FIVE), new_off.get("items"))
    check("... and a plain reason", "approval card" in str(new_off.get("why")),
          new_off.get("why"))
    check("the whole page carries the same list",
          view["tools"]["new_off"] == tools["new_off"], view["tools"]["new_off"])
    check("the payload wrote nothing and raised no card", wrote == [], wrote)
    with AF._T_LOCK:
        pending = dict(AF._T_STATE["pending"])
    check("... no tool-switch card is pending", pending == {}, pending)


def t_the_payload_changes_nothing_on_disk():
    path = AF._toml_path()
    check("a settings file is in use", path is not None and Path(path).is_file(),
          path)
    if path is None:
        return
    before = Path(path).read_bytes()
    AF.tools_status(here=False)
    AF.view(here=False)
    check("two reads leave the settings file byte for byte as it was",
          Path(path).read_bytes() == before, "the settings file changed")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
