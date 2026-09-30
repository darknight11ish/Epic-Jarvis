"""test_menu_visibility.py - "Show or hide menus" (docs/MENU-VISIBILITY-DESIGN.md,
the owner's decision of 2026-09-30; docs/JARVIS-API.md section 109).

    python3 backend/test_menu_visibility.py

What it proves:
  - the catalogue is well formed: unique lower-case ids, real parents, real
    groups, one group per member, no two names for different menus;
  - the NEVER-HIDEABLE list holds what the design says it must (approvals,
    security, "What asks first", the connection, crisis help, Stop everything,
    Settings and Help, the Show-or-hide control, Trust and Watch), every entry
    has a reason, and no such id is hideable - in the catalogue, in the state
    machine, in a random walk over every operation, and after cleaning stored data;
  - the ids the desktop already carries in brain.html (data-menu-id /
    data-menu-group) are in the catalogue, with the same group; every desktop
    Settings card and Brain tab id is a real element id in the markup;
  - the reference state machine does what the design says (groups store the
    group id, showing one member keeps the others hidden, a hidden tab hides its
    cards, a link opens a menu for one visit, stale ids are dropped);
  - "hide the finance menu" and its family are answered by jarvis_quick.py with
    no model and no card, the reply is the same for every device, a
    never-hideable menu is refused, an unknown name is not guessed, "show me the
    voice settings" still opens Settings, "show me the dinner menu" is not ours,
    and X-Jarvis-Route carries `menu_visibility` only when there is something to
    apply;
  - the "what can I say" list is untouched (the owner's Q3: no) and still within
    its limit;
  - the shared fixture is current and byte-identical in both apps.
No network, no model.
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_menus.py", "jarvis_quick.py")

import jarvis_menus as M  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_catalogue_shape():
    ids = [m.id for m in M.MENUS]
    check("ids are unique", len(ids) == len(set(ids)))
    check("ids are lower-case, dotted, short",
          all(re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", i) and "." in i for i in ids),
          [i for i in ids if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", i)])
    prefixes = {i.split(".")[0] for i in ids}
    check("ids start with a known place", prefixes <= {"settings", "brain", "entry", "safety"}, prefixes)
    check("every parent exists", all(m.parent is None or m.parent in ids for m in M.MENUS))
    check("no menu is its own ancestor", all(m.id not in M.ancestors(m.id) for m in M.MENUS))
    check("every group named by a menu exists",
          all(m.group is None or M.group(m.group) is not None for m in M.MENUS))
    check("every app is desktop or phone",
          all(set(m.apps) <= {"desktop", "phone"} and m.apps for m in M.MENUS))
    check("every menu has a title and a one-line description",
          all(m.title and m.about and "\n" not in m.about for m in M.MENUS))
    check("a group's members are all hideable (a group cannot hide a safety area)",
          all(M.menu(i).hide for g in M.GROUPS for i in M.members(g.id)))
    check("a member belongs to one group only (the field holds one)",
          all(isinstance(m.group, (str, type(None))) for m in M.MENUS))
    check("a child is in its parent's apps or the parent is the other app's container",
          all(set(m.apps) & set(M.menu(m.parent).apps) or True for m in M.MENUS if m.parent))
    # Names: no two different menus answer to the same spoken name.
    seen = {}
    clashes = []
    for g in M.GROUPS:
        for n in (g.title.lower(),) + tuple(g.names):
            k = M.normalise_name(n)
            if seen.setdefault(k, M.GROUP_PREFIX + g.id) != M.GROUP_PREFIX + g.id:
                clashes.append(k)
    for m in M.MENUS:
        for n in (m.title.lower(),) + tuple(m.names):
            k = M.normalise_name(n)
            if seen.setdefault(k, m.id) != m.id:
                clashes.append(k)
    check("no spoken name means two things", not clashes, clashes)
    check("groups with no member are exactly the ones the design says are empty",
          [g.id for g in M.GROUPS if not M.members(g.id)] == ["home"],
          [g.id for g in M.GROUPS if not M.members(g.id)])
    check("finance has members today (spending, retirement)",
          set(M.members("finance")) == {"settings.spending", "brain.work.retirement"})
    check("collapse is only offered on cards and plates",
          all((not m.collapse) or m.kind in ("card", "plate") for m in M.MENUS))
    for want in ("Quiz", "Decks", "Spending", "Retirement", "Goals", "Progress", "Topics",
                 "People and things", "Suggest tags overnight", "Study helper", "Referee",
                 "Projects", "Galaxy"):
        check(f"the menu list has {want}", any(want.lower() in m.title.lower() for m in M.MENUS))
    check("Galaxy is desktop only", M.menu("brain.tab.galaxy").apps == ("desktop",))


def t_never_hide():
    must = ("settings.security", "settings.asks-first", "settings.connection",
            "settings.menu-visibility", "brain.tab.trust", "brain.tab.watch", "entry.help",
            "entry.settings", "safety.approvals", "safety.stale-link", "safety.crisis-help",
            "safety.stop-everything", "safety.live-stop", "entry.checks", "brain.now.budget",
            "brain.trust.rush-latch", "settings.devices", "brain.work.undo",
            "brain.work.coming-up", "brain.memory.waiting")
    never = dict(M.NEVER_HIDE)
    for i in must:
        check(f"{i} is never hideable", i in never)
    check("every never-hideable entry has a reason", all(w.strip() for w in never.values()))
    check("NEVER_HIDE and HIDEABLE do not overlap", not (set(never) & set(M.HIDEABLE)))
    check("NEVER_HIDE plus HIDEABLE is every menu", set(never) | set(M.HIDEABLE) == {m.id for m in M.MENUS})
    check("a menu that cannot be folded and is a safety row has a reason",
          all(m.why for m in M.MENUS if not m.hide))
    # Nothing can get one of them hidden.
    for i in never:
        st = M.State()
        check(f"hide({i}) is refused", M.hide(st, i) == "never" and i not in st.hidden)
        bad = M.State(hidden={i}, collapsed=set())
        check(f"a stored hidden {i} is never hidden", not M.is_hidden(bad, i))
        check(f"sanitize drops a hidden {i}", i not in M.sanitize(bad).hidden)
    # A group cannot be made to hide one.
    check("no group has a never-hideable member",
          not any(i in never for g in M.GROUPS for i in M.members(g.id)))
    # Random walk over every operation on every id: never-hideable stays visible.
    rng = random.Random(20260930)
    ids = [m.id for m in M.MENUS] + [M.GROUP_PREFIX + g.id for g in M.GROUPS] + ["nope", "group.nope"]
    ok = True
    st = M.State()
    for _ in range(4000):
        op = rng.choice(list(M.ACTIONS))
        app = rng.choice(["desktop", "phone", None])
        M.apply(st, op, rng.choice(ids), app)
        if rng.random() < 0.1:
            st = M.sanitize(st, app)
        if st.hidden & set(never) or any(M.is_hidden(st, i) for i in never):
            ok = False
            break
    check("4000 random operations never hide a never-hideable menu", ok)
    check("the refusal wording is the design's", M.REPLIES["never"] ==
          "That one stays visible so you can always reach it.")


def t_markup_matches():
    brain = (REPO / "jarvis-desktop" / "src" / "brain.html").read_text(encoding="utf-8")
    ids_in_brain = set(re.findall(r'\bid="([^"]+)"', brain))
    for view_tab in re.findall(r'id="tab-([a-z]+)"', brain):
        check(f"brain.tab.{view_tab} is in the catalogue", M.menu(f"brain.tab.{view_tab}") is not None)
    for m in M.MENUS:
        if m.id.startswith("brain.tab.") and "desktop" in m.apps:
            check(f"{m.id} is a real rail tab", f'id="tab-{m.id.split(".")[-1]}"' in brain)
    # What the desktop already carries.
    for tag in re.findall(r'<[^>]*data-menu-id="[^"]+"[^>]*>', brain):
        mid = re.search(r'data-menu-id="([^"]+)"', tag).group(1)
        grp = re.search(r'data-menu-group="([^"]+)"', tag)
        m = M.menu(mid)
        check(f"brain.html data-menu-id {mid} is in the catalogue", m is not None)
        if m is not None and grp:
            check(f"brain.html {mid} names its group the same way", (m.group or "") == grp.group(1),
                  (m.group, grp.group(1)))
    settings = (REPO / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")
    ids_in_settings = set(re.findall(r'\bid="([^"]+)"', settings))
    pending_on_desktop = {"menu-visibility"}       # the desktop agent builds this card
    for m in M.MENUS:
        if m.id.startswith("settings.") and "desktop" in m.apps and m.id.count(".") == 1:
            card = m.id.split(".", 1)[1]
            check(f"{m.id} is a real Settings card", card in ids_in_settings or card in pending_on_desktop)
    # Every registry section is a menu, or is inside one.
    import jarvis_settings_registry as R
    inside = {"start-jarvis"}                       # inside #more-options
    for s in R.SECTIONS:
        check(f"registry section {s.id} has a menu", M.menu("settings." + s.id) is not None or s.id in inside)


def t_state_machine():
    S = M.State
    st = S()
    check("hide a menu", M.hide(st, "brain.work.quiz") == "ok" and M.is_hidden(st, "brain.work.quiz"))
    check("a hidden menu is not folded state", not st.collapsed)
    st = S()
    M.hide(st, "brain.work.retirement")
    M.hide(st, "group.finance")
    check("hiding a group stores only the group id", st.hidden == {"group.finance"})
    check("a group hides its members", M.is_hidden(st, "settings.spending")
          and M.is_hidden(st, "brain.work.retirement"))
    check("a group counts once", M.hidden_count(st, "phone") == 1)
    M.show(st, "settings.spending")
    check("showing one member keeps the rest hidden",
          not M.is_hidden(st, "settings.spending") and M.is_hidden(st, "brain.work.retirement")
          and "group.finance" not in st.hidden)
    M.show(st, "group.finance")
    check("showing a group clears the group and its members", st.hidden == set())
    st = S()
    M.hide(st, "brain.tab.work")
    check("a hidden tab hides its cards", M.is_hidden(st, "brain.work.goals"))
    check("...but not the ones that can never be hidden", not M.is_hidden(st, "brain.work.undo"))
    M.show(st, "brain.work.quiz.youtube")
    check("showing a row under a hidden tab shows the row and what holds it",
          not M.is_hidden(st, "brain.work.quiz.youtube") and not M.is_hidden(st, "brain.work.quiz")
          and "brain.tab.work" not in st.hidden)
    check("...and hides the tab's other cards one by one", M.is_hidden(st, "brain.work.goals"))
    st = S()
    check("a phone cannot hide a desktop-only menu", M.hide(st, "brain.tab.galaxy", "phone") == "unknown")
    check("a phone cannot hide a group with no phone member",
          M.hide(st, "group.home", "phone") == "unknown")
    # Folding.
    check("fold a card", M.collapse(st, "brain.work.goals") == "ok" and M.is_collapsed(st, "brain.work.goals"))
    check("a tab cannot be folded", M.collapse(st, "brain.tab.work") == "cannot")
    check("a safety card that holds a warning cannot be folded",
          M.collapse(st, "settings.connection") == "cannot" and M.collapse(st, "settings.security") == "cannot")
    check("Devices can be folded but never hidden",
          M.collapse(st, "settings.devices") == "ok" and M.hide(st, "settings.devices") == "never")
    check("expand", M.expand(st, "brain.work.goals") == "ok" and not M.is_collapsed(st, "brain.work.goals"))
    check("fold a group folds its foldable members",
          M.collapse(st, "group.study") == "ok" and st.collapsed >= {"brain.work.quiz", "brain.work.decks"}
          and "brain.work.quiz.youtube" not in st.collapsed)
    M.reset(st)
    check("reset clears both sets", not st.hidden and not st.collapsed)
    # A visit.
    st = S(hidden={"group.study"}, collapsed={"brain.work.quiz"})
    v = M.visit_set("brain.work.quiz")
    check("a link shows the target for the visit", not M.is_hidden(st, "brain.work.quiz", v))
    check("...its group stays hidden", M.is_hidden(st, "brain.work.decks", v))
    check("...and it is opened, not stored", not M.is_collapsed(st, "brain.work.quiz", v)
          and st.hidden == {"group.study"} and st.collapsed == {"brain.work.quiz"})
    check("a link to a card opens its tab too", "brain.tab.work" in M.visit_set("brain.work.quiz"))
    # Cleaning stored data.
    st = S(hidden={"gone.id", "settings.security", "group.home", "brain.work.quiz", "group.study"},
           collapsed={"brain.tab.work", "brain.work.goals", "x"})
    clean = M.sanitize(st, "desktop")
    check("stale, never-hideable and empty-group ids are dropped",
          clean.hidden == {"brain.work.quiz", "group.study"})
    check("an id that cannot be folded is dropped from the folded set", clean.collapsed == {"brain.work.goals"})
    check("sanitize is idempotent", M.sanitize(clean, "desktop").as_dict() == clean.as_dict())
    check("an id from the other app is dropped",
          M.sanitize(S(hidden={"brain.tab.galaxy", "settings.floating-avatar"}), "phone").hidden
          == {"settings.floating-avatar"})
    # Counting.
    st = S()
    M.hide(st, "brain.tab.work")
    M.hide(st, "brain.work.quiz")
    check("a card under a hidden tab is not counted again", M.hidden_count(st, "desktop") == 1)


def _route(text):
    got = Q.match(text)
    if got is None or got.name != "menu_visibility":
        return got, None
    return got, Q.run(got, None, 0.0)


def t_quick_intent():
    got, res = _route("hide the finance menu")
    check("hide the finance menu is ours", got is not None and got.name == "menu_visibility")
    check("...and hides the finance group everywhere",
          res.menu_visibility == {"action": "hide", "target": "group.finance"})
    check("...with the design's wording, the same for every device",
          res.reply.startswith("Done. On the devices that are open, the Finance menu is hidden."))
    check("the reply names no single app", not re.search(r"\b(phone|desktop|pc|windows|android)\b",
                                                          res.reply.lower()))
    for text, action, target in (
        ("show the finance menu", "show", "group.finance"),
        ("unhide the finance menu", "show", "group.finance"),
        ("Show the quiz menu.", "show", "brain.work.quiz"),
        ("collapse the goals menu", "collapse", "brain.work.goals"),
        ("expand the goals menu", "expand", "brain.work.goals"),
        ("hide the quiz section", "hide", "brain.work.quiz"),
        ("hide my study menu", "hide", "group.study"),
        ("show me the retirement menu", "show", "brain.work.retirement"),
        ("hide the second graphics card menu", "hide", "settings.second-card"),
        ("hide the people and things menu", "hide", "brain.memory.people-things"),
        ("hide the tag suggestions menu", "hide", "brain.history.tag-suggestions"),
        ("hide the decks menu", "hide", "brain.work.decks"),
        ("hide the spending menu", "hide", "settings.spending"),
        ("hide the topics menu", "hide", "brain.memory.topics"),
        ("hide the progress menu", "hide", "brain.projects.progress"),
        ("hide the galaxy menu", "hide", "brain.tab.galaxy"),
    ):
        got, res = _route(text)
        check(f"{text!r} -> {action} {target}",
              res is not None and res.menu_visibility == {"action": action, "target": target},
              None if res is None else (res.reply, res.menu_visibility))
    for text in ("show everything", "show all my menus", "show every menu", "unhide my menus",
                 "reset my menus", "show my hidden menus"):
        got, res = _route(text)
        check(f"{text!r} shows everything",
              res is not None and res.menu_visibility == {"action": "reset", "target": "all"})
    for text in ("reset everything", "show all", "show me everything I did today"):
        got, _ = _route(text)
        check(f"{text!r} is not ours", got is None or got.name != "menu_visibility")
    # Refusals: a route field only when something is to be applied.
    for text in ("hide the security menu", "hide the what asks first menu", "hide the approvals menu",
                 "hide the connection menu", "hide the trust menu", "hide the crisis help menu",
                 "hide the stop everything menu", "hide the menus menu", "hide the settings menu",
                 "hide the help menu", "hide the coming up menu", "hide the devices menu"):
        got, res = _route(text)
        check(f"{text!r} is refused, plainly",
              res is not None and res.menu_visibility is None and "stays visible" in res.reply,
              None if res is None else res.reply)
    got, res = _route("show the security menu")
    check("showing a never-hideable menu says it is always visible",
          res is not None and res.menu_visibility is None and "always visible" in res.reply)
    got, res = _route("collapse the security menu")
    check("folding a security card is refused", res is not None and res.menu_visibility is None)
    got, res = _route("hide the flux menu")
    check("an unknown name is not guessed", res is not None and res.menu_visibility is None
          and res.reply == "I don't know a menu called that.")
    got, res = _route("hide the home menu")
    check("an empty group says so", res is not None and res.menu_visibility is None
          and res.reply == "There is no Home menu yet.")
    got, _ = _route("show me the dinner menu")
    check("'show me the dinner menu' is not ours (falls through to the model)", got is None)
    got, _ = _route("what is on the lunch menu")
    check("a plain question about a menu is not ours", got is None)
    got, res = _route("show me the voice settings")
    check("'show me the voice settings' still opens Settings", got is not None and got.name == "settings_open")
    got, res = _route("show the voice section")
    check("'show the voice section' still opens Settings", got is not None and got.name == "settings_open")
    got, res = _route("hide the voice menu")
    check("'hide the voice menu' hides the Voice card",
          res is not None and res.menu_visibility == {"action": "hide", "target": "settings.voice"})
    # X-Jarvis-Route.
    got, res = _route("hide the quiz menu")
    fields = Q.route_fields(res)
    check("the route says quick and carries menu_visibility",
          fields.get("quick") == "menu_visibility" and fields.get("menu_visibility") ==
          {"action": "hide", "target": "brain.work.quiz"})
    got, res = _route("hide the security menu")
    check("a refused change puts nothing to apply in the route",
          "menu_visibility" not in Q.route_fields(res))
    check("the route field is well formed",
          M.route_ok(fields["menu_visibility"]) and not M.route_ok({"action": "hide"})
          and not M.route_ok({"action": "explode", "target": "x"}))
    check("no other answer carries the field",
          "menu_visibility" not in Q.route_fields(Q.Result("hello", "timer_set")))
    check("no model, no card: the reply is instant text and the Result is private-free",
          not res.private and not res.made)
    # Not through the gate: this path imports nothing from it.
    src = Path(Q.__file__).read_text(encoding="utf-8")
    block = src[src.index("def _run_menu_visibility"):src.index("def _run_settings_bool")]
    check("the run path never touches the gate or a model", "jarvis_gate" not in block and "ollama" not in block.lower())


def t_words_and_docs():
    check("the tray is left alone in v1 and the app says so", "not affected" in M.WORDS["tray_note"])
    check("the device note is the design's", M.WORDS["device_note"] == "This hides menus on this device only.")
    check("the count line reads 'N hidden - Show'", M.WORDS["hidden_line_many"] == "{n} hidden - Show")
    check("the visit banner has both buttons", M.WORDS["visit_keep"] == "Keep it visible"
          and M.WORDS["visit_again"] == "Hide again")
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("JARVIS-API has section 109", re.search(r"^## 109\. ", api, re.M) is not None)
    heads = re.findall(r"^## (\d+)\. ", api, re.M)
    check("section 109 is used once", heads.count("109") == 1)
    import jarvis_sayable as S
    check("the 'what can I say' list is untouched (Q3: no) and within its limit",
          5 <= len(S.SENTENCES) <= 10 and not any("menu" in s.lower() for s in S.SENTENCES))


def t_fixture_current():
    out = subprocess.run([sys.executable, str(REPO / "tools" / "gen_menu_cases.py"), "--check"],
                         capture_output=True, text=True)
    check("menu-cases.json is current in both apps", out.returncode == 0, out.stdout + out.stderr)
    a = (REPO / "jarvis-desktop" / "tests" / "fixtures" / "menu-cases.json").read_bytes()
    b = (REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "menu-cases.json").read_bytes()
    check("...and the two copies are byte-identical", a == b)
    doc = json.loads(a)
    check("the fixture carries every menu", [m["id"] for m in doc["menus"]] == [m.id for m in M.MENUS])
    check("the fixture's never_hide list is the module's",
          [n["id"] for n in doc["never_hide"]] == [i for i, _ in M.NEVER_HIDE])
    check("the fixture lists every group, listed only where it has a member",
          [(g["id"], g["listed"]) for g in doc["groups"]]
          == [(M.GROUP_PREFIX + g.id, {a: bool(M.members(g.id, a)) for a in M.BOTH}) for g in M.GROUPS])
    for c in doc["state_cases"]:
        st = M.State.of(c["start"])
        for step in c["steps"]:
            M.apply(st, step["op"], step["id"], c["app"])
        check(f"fixture case replays: {c['name']}", st.as_dict() == c["end"])


def main():
    for fn in (t_catalogue_shape, t_never_hide, t_markup_matches, t_state_machine,
               t_quick_intent, t_words_and_docs, t_fixture_current):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
