"""jarvis_vault_organizer.py: a read-only plan for an Obsidian vault.

    python3 backend/test_vault_organizer.py

WHAT THIS SUITE IS FOR. The Phase-2 batch vault organizer (the owner's
decision, 2026-10-20) has to be safe BEFORE it is useful: the plan must be a
genuine dry run (it opens notes for reading and writes nothing anywhere), the
scheme default must be the least destructive one (`mocs_only`, which moves no
file), the tag preview must merge without ever erasing the owner's own tags,
and duplicates and empty stubs must be listed rather than deleted. The writer
half (`/api/vault/organize`, ONE card, file-guardian snapshots, one-click
Undo) is the FOLLOW-UP SLICE and is deliberately not claimed here.

EACH CHECK CAN FAIL, and the two instruments are themselves proved:
  * `t_the_read_only_instrument_bites` shows the before/after tree hash really
    notices a write;
  * `t_the_digest_instrument_bites` shows the digest moves when the vault does.
During development the feature was REVERT-CHECKED by hand: a single write
added to the planner made `t_plan_is_completely_read_only`,
`t_mocs_preview...` and the tag test fail; removing it turned them green
again. That measurement is written into the PR, not asserted here (a test does
not edit the module it ships).

RUNS ANYWHERE: the vault and the settings folder are temporary folders, the
config is the SAME two environment variables every module here reads, and no
network, model, embeddings or owner's file is touched. `jarvis_gate` is not in
this repository (it is the live backend's), so the switch's card is a stand-in
here; the plan route raises no card at all by design.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_vault_organizer.py", "jarvis_notes.py")

TMP = Path(tempfile.mkdtemp(prefix=".jarvis-vault-organizer-tests-",
                            dir=str(Path.home())))
CONF = TMP / "config"
CONF.mkdir()
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["OPENJARVIS_HOME"] = str(TMP / "home")
(TMP / "home").mkdir()
os.environ.pop("JARVIS_CONFIG_DIR", None)
os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
os.environ.pop("JARVIS_BACKEND", None)
os.environ["JARVIS_NO_EMBED"] = "1"          # the clusterer never embeds; this proves it

import jarvis_vault_organizer as V  # noqa: E402
import jarvis_receipts as R  # noqa: E402

VAULT = TMP / "Vault"
FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh():
    """An empty vault with Obsidian's marker folder, and the switch off."""
    V.reset_for_tests()
    shutil.rmtree(VAULT, ignore_errors=True)
    (VAULT / ".obsidian").mkdir(parents=True)
    try:
        V.state_path().unlink()
    except FileNotFoundError:
        pass
    return VAULT


def write(rel: str, text: str) -> Path:
    p = VAULT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def tree(root: Path) -> list:
    """Every file under `root` as (relative path, sha256, size) - the read-only
    instrument: a plan may not add, remove, move or change one byte."""
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(root).as_posix()
        try:
            raw = p.read_bytes()
        except OSError as exc:                            # noqa: BLE001
            out.append((rel, f"unreadable {type(exc).__name__}", -1))
            continue
        out.append((rel, hashlib.sha256(raw).hexdigest(), len(raw)))
    return out


def listing(root: Path) -> list:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file())


class Framework:
    """A stand-in for jarvis_framework, for the two things this module reads:
    the `[vault_organizer] enabled` template value and the tier table."""

    def __init__(self, enabled=False, tier="ask"):
        self.enabled = enabled
        self.tier = tier
        self.audit = []
        self.module = types.ModuleType("jarvis_framework")
        self.module.load_framework = lambda *a, **k: {
            "vault_organizer": {"enabled": bool(self.enabled)}}
        self.module.action_tier = lambda action: self.tier
        self.module.audit_log = lambda event, detail=None, **k: self.audit.append(
            (event, detail))
        self.saved = None

    def __enter__(self):
        self.saved = sys.modules.get("jarvis_framework")
        sys.modules["jarvis_framework"] = self.module
        return self

    def __exit__(self, *exc):
        if self.saved is None:
            sys.modules.pop("jarvis_framework", None)
        else:
            sys.modules["jarvis_framework"] = self.saved


class Gate:
    """The gate's answer, recorded. The plan route must never ask it."""

    class Verdict:
        def __init__(self, outcome="approved", tier="ask"):
            self.tier, self.outcome = tier, outcome
            self.allowed = outcome == "approved"

    def __init__(self, outcome="approved"):
        self.outcome = outcome
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        return self.Verdict(self.outcome)


class GateModule:
    """`jarvis_gate` stood in for: `check` answers an approved card at tier ask,
    and `latch_taint` records that the writer marked the turn private."""

    class Yes:
        allowed = True
        outcome = "approved"
        tier = "ask"

    def __init__(self):
        self.cards, self.latches = [], []
        self.module = types.ModuleType("jarvis_gate")
        self.module.check = lambda action, detail, prompt=None: (
            self.cards.append(action), GateModule.Yes())[1]
        self.module.latch_taint = lambda why="": (self.latches.append(why),
                                                  True)[1]
        self.saved = None

    def __enter__(self):
        self.saved = sys.modules.get("jarvis_gate")
        sys.modules["jarvis_gate"] = self.module
        return self

    def __exit__(self, *exc):
        if self.saved is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = self.saved


def run_now(fn):
    fn()


class RouteStand:
    """A stand-in for the core's Handler and its three callbacks - the shape
    jarvis_plugins.py calls install() with, plus a real response to read."""

    class WFile:
        def __init__(self):
            self.buf = b""

        def write(self, data):
            self.buf += data

    def __init__(self, origin=True, token=True):
        self.calls, self.status, self.payload = [], None, None
        self.origin, self.token = origin, token
        core = self

        class Handler:
            def __init__(self, path="/", body=b"{}", peer="127.0.0.1",
                         local="127.0.0.1"):
                self.path, self.body = path, body
                self.wfile = RouteStand.WFile()
                self.client_address = (peer, 50000)
                self.connection = types.SimpleNamespace(
                    getsockname=lambda: (local, 4719))

            def do_GET(self):
                core.calls.append(("GET", self.path))

            def do_POST(self):
                core.calls.append(("POST", self.path))

            def send_response(self, code):
                core.status = code

            def send_header(self, *args):
                pass

            def end_headers(self):
                pass

        self.Handler = Handler

    def origin_ok(self, req):
        return self.origin

    def token_ok(self, req):
        return self.token

    def read_body(self, req):
        return req.body

    def post(self, path, body, peer="127.0.0.1", local="127.0.0.1"):
        req = self.Handler(path, json.dumps(body).encode("utf-8"), peer, local)
        req.do_POST()
        self.payload = json.loads(req.wfile.buf.decode("utf-8") or "{}")
        return self.status, self.payload

    def get(self, path):
        req = self.Handler(path)
        req.do_GET()
        self.payload = json.loads(req.wfile.buf.decode("utf-8") or "{}")
        return self.status, self.payload


def plan(**kwargs) -> dict:
    """A plan on the fixture vault, with the organizer ON (the plan function
    itself does not consult the switch - the ROUTE does; see the route test)."""
    return V.plan_vault_organization(str(VAULT), **kwargs)


def fixture_vault():
    write("Work/Alpha.md",
          "---\ntags: [owner-thing]\n---\n# Alpha\n\n"
          "The boiler was serviced in August and it went well.\n\n"
          "- [ ] replace the filter\n")
    write("Work/Beta.md",
          "# Beta\n\nThe radiator valve was replaced last week.\n")
    write("Garden/Gnomes.md",
          "# Gnomes\n\nThere are three gnomes by the shed.\n")
    return VAULT


# --------------------------------------------------------------------------
#   Read-only: the whole point of this slice
# --------------------------------------------------------------------------

def t_plan_is_completely_read_only():
    fresh()
    fixture_vault()
    before = tree(VAULT)
    before_conf = listing(CONF)
    started = time.time()
    out = plan()
    check("the plan succeeds on a real vault", out.get("ok") is True, out)
    after = tree(VAULT)
    after_conf = listing(CONF)
    check("PLAN IS READ-ONLY: the vault tree is byte-identical after planning",
          before == after,
          {"added": [x for x in after if x not in before][:5],
           "removed": [x for x in before if x not in after][:5]})
    check("... and it wrote nothing into the settings folder",
          before_conf == after_conf, {"before": before_conf, "after": after_conf})
    check("... and it took a bounded time, not minutes",
          (time.time() - started) < V.MAX_SECONDS + 5.0, time.time() - started)


def t_the_read_only_instrument_bites():
    """The check above must be able to FAIL: a write really moves the hash."""
    fresh()
    write("one.md", "# One\n\nA note.\n")
    before = tree(VAULT)
    write("two.md", "# Two\n\nAnother note.\n")
    check("the read-only instrument notices an added file", tree(VAULT) != before)


def t_plan_payload_is_the_preview_the_next_slice_needs():
    fresh()
    fixture_vault()
    out = plan()
    summary = out.get("summary") or {}
    check("the plan names a plan_id and a digest",
          str(out.get("plan_id", "")).startswith("vplan_")
          and isinstance(out.get("digest"), str) and len(out["digest"]) == 16, out)
    check("the default scheme is the SAFEST one, mocs_only",
          out.get("scheme") == "mocs_only", out.get("scheme"))
    check("... and mocs_only previews NO file moves",
          out.get("moves_preview") == [], out.get("moves_preview"))
    check("the summary carries every count the card will state",
          set(summary) == {"notes_scanned", "notes_moved", "notes_tagged",
                           "mocs_to_create", "databases_indexed",
                           "links_rewritten", "duplicates_found",
                           "empty_stubs_found"}, sorted(summary))
    check("the summary counts the real vault",
          summary["notes_scanned"] == 3 and summary["mocs_to_create"] >= 2,
          summary)
    check("the MOC previews carry a name and rendered text",
          all(m.get("name", "").startswith(V.MOC_PREFIX)
              and m.get("body", "").startswith("# ") for m in out["mocs_preview"]),
          out.get("mocs_preview"))
    check("the Home preview is the vault-home note",
          out.get("home_preview", {}).get("name") == V.HOME_NAME, out.get("home_preview"))
    check("the plan says in plain words that nothing has changed",
          "Nothing has been changed yet." in str(out.get("said")), out.get("said"))


def t_mocs_link_every_note_and_the_notes_point_up():
    fresh()
    write("Work/Alpha.md",
          "# Alpha\n\nThe boiler was serviced.\n\n- [ ] replace the filter\n")
    write("Work/Beta.md", "# Beta\n\nThe radiator valve was replaced.\n")
    out = plan()
    mocs = {m["name"]: m["body"] for m in out["mocs_preview"]}
    work = mocs.get("_MOC - Work.md", "")
    check("a MOC exists for the folder's topic", bool(work), sorted(mocs))
    check("the MOC links every note in it",
          "[[Alpha]]" in work and "[[Beta]]" in work, work)
    check("the MOC counts its notes and rolls up open tasks",
          "2 note(s)" in work and "Open tasks" in work and "[[Alpha]] - 1 open" in work,
          work)
    check("every note is given an `up:` link to its own MOC",
          all(row["up"] == "[[{}]]".format(row["moc"][:-3])
              for row in out["tag_plan"]), out["tag_plan"])
    home = (out.get("home_preview") or {}).get("body", "")
    check("the Vault Home links every MOC", "[[_MOC - Work]]" in home, home)
    check("... and carries the Review Queue section",
          "Review Queue: Duplicates & Empty Stubs" in home, home)


def t_tag_merge_never_erases_the_owners_tags():
    fresh()
    write("Work/Alpha.md",
          "---\ntags: [Owner-Thing, second, owner-thing]\n---\n"
          "# Alpha\n\nThe boiler was serviced.\n")
    out = plan()
    row = [r for r in out["tag_plan"] if r["path"] == "Work/Alpha.md"][0]
    check("the owner's tags are kept exactly (case and order)",
          row["tags_before"] == ["Owner-Thing", "second"], row["tags_before"])
    check("... new tags are appended, never replacing them",
          row["tags_after"][:2] == ["Owner-Thing", "second"]
          and len(row["tags_after"]) > 2, row["tags_after"])
    check("... and a tag the owner already has is not added twice, in any case",
          len([t for t in row["tags_after"] if t.lower() == "owner-thing"]) == 1,
          row["tags_after"])
    check("the inferred tags are clean lowercase kebab-case",
          all(t == t.lower() and " " not in t for t in row["tags_added"]),
          row["tags_added"])


def t_duplicates_and_empty_stubs_are_listed_never_deleted():
    fresh()
    write("Work/One.md", "# One\n\nThe same words in both notes.\n")
    write("Work/Two.md", "# One\n\nThe same words in both notes.\n")
    write("Work/Stub.md", "# Stub\n")
    before = tree(VAULT)
    out = plan()
    review = out.get("duplicates_and_stubs") or {}
    check("two notes with identical bodies are flagged as duplicates",
          len(review.get("duplicates") or []) == 1, review)
    check("... naming both the copy to keep and the duplicate",
          set((review["duplicates"][0]["keep"],
               review["duplicates"][0]["duplicate"])) == {"Work/One.md", "Work/Two.md"},
          review["duplicates"])
    check("a note with no words is listed as an empty stub",
          review.get("empty_stubs") == ["Work/Stub.md"], review.get("empty_stubs"))
    plan_keys = set(out) | set(out.get("summary") or {})
    check("the plan carries no delete ACTION of any kind",
          not any(str(k).lower().startswith("delete") for k in plan_keys),
          sorted(plan_keys))
    check("... and the only sentence about deletion is the promise not to",
          all(("nothing is deleted" in line.lower()
               or "never deleted" in line.lower())
              for line in json.dumps(out).lower().split('"')
              if "delet" in line),
          "a deletion was described as an action")
    check("nothing was archived or removed: the vault is byte-identical",
          tree(VAULT) == before)
    check("the default does not archive stubs (recorded, and nothing moved)",
          review.get("archive_empty_stubs") is False, review)


def t_the_same_vault_plans_byte_identically_twice():
    fresh()
    fixture_vault()
    first = plan()
    second = plan()
    check("two plans of one unchanged vault carry the same plan_id and digest",
          (first["plan_id"], first["digest"]) == (second["plan_id"], second["digest"]),
          (first["plan_id"], second["plan_id"]))
    check("... and the same previews (moves, MOCs, tags, home)",
          first["moves_preview"] == second["moves_preview"]
          and first["mocs_preview"] == second["mocs_preview"]
          and first["tag_plan"] == second["tag_plan"]
          and first["home_preview"] == second["home_preview"])
    check("... and the same plain words",
          first["said"] == second["said"])


def t_the_digest_instrument_bites():
    fresh()
    write("Garden/Gnomes.md", "# Gnomes\n\nThree gnomes by the shed.\n")
    before = plan()["digest"]
    write("Garden/Gnomes.md", "# Gnomes\n\nFour gnomes by the shed now.\n")
    check("the digest moves when a note's words change",
          plan()["digest"] != before)


# --------------------------------------------------------------------------
#   The two moving schemes are previewed too (apply is the next slice)
# --------------------------------------------------------------------------

def t_topic_folders_previews_safe_moves():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    write("Gardening/Gnomes.md", "# Gnomes\n\nThree gnomes by the shed.\n")
    write("Projects/_Database - Projects.md",
          "# Projects\n\nThe Projects database.\n")
    write("Projects/Launch.md",
          "---\ndatabase: Projects\n---\n# Launch\n\nThe launch plan.\n")
    before = tree(VAULT)
    out = plan(scheme="topic_folders")
    moves = out.get("moves_preview") or []
    check("topic_folders previews moves", len(moves) >= 2, moves)
    to_paths = [m["to_path"] for m in moves]
    check("every destination is a relative .md path inside the vault",
          all(p.endswith(".md") and not p.startswith(("/", "\\"))
              and ".." not in p.split("/") for p in to_paths), to_paths)
    check("... and no two notes are sent to one path", len(to_paths) == len(set(to_paths)))
    on_disk = set(listing(VAULT))
    check("... and each move names a note that really exists now",
          all(m["from_path"] in on_disk for m in moves),
          [m["from_path"] for m in moves])
    check("... and nothing from the vault is left out of the plan entirely",
          {n for n in on_disk if n.endswith(".md")}
          == {m["from_path"] for m in moves}, (on_disk, moves))
    by_from = {m["from_path"]: m["to_path"] for m in moves}
    check("a database's child page goes under Databases/<Name>/",
          str(by_from.get("Projects/Launch.md", "")).startswith(
              "Databases/Projects/"), by_from)
    check("... and the database index note goes there too",
          str(by_from.get("Projects/_Database - Projects.md", "")).startswith(
              "Databases/Projects/"), by_from)
    check("the moving plan is read-only as well", tree(VAULT) == before)


def t_para_classifies_by_what_the_note_is():
    fresh()
    write("Tasks/Active.md",
          "---\nstatus: In Progress\nproject: Atlas\n---\n"
          "# Active\n\nWork in progress.\n\n- [ ] a step\n")
    write("Old/Done.md", "---\nstatus: Done\n---\n# Done\n\nFinished.\n")
    write("Refs/Plain.md", "---\narea: Reference\n---\n# Plain\n\nA reference note.\n")
    out = plan(scheme="para")
    move = {m["from_path"]: m["to_path"] for m in out["moves_preview"]}
    check("a note with an open task goes under Projects",
          str(move.get("Tasks/Active.md", "")).startswith("1 - Projects/"), move)
    check("a finished note goes under Archives",
          str(move.get("Old/Done.md", "")).startswith("4 - Archives/"), move)
    check("every PARA destination is one of the four buckets",
          all(p.split("/")[0] in V.PARA_BUCKETS for p in move.values()), move)


def t_an_unknown_scheme_is_refused_in_plain_words():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nA note.\n")
    out = plan(scheme="alphabetical")
    check("an unknown scheme is refused, not guessed",
          out.get("ok") is False and "unknown scheme" in str(out.get("error")), out)
    check("... and the answer lists the schemes that exist",
          out.get("schemes") == list(V.SCHEMES), out.get("schemes"))


# --------------------------------------------------------------------------
#   Path safety, caps, empty vault
# --------------------------------------------------------------------------

def t_a_symlink_out_of_the_vault_is_refused():
    fresh()
    outside = TMP / "outside-the-vault.md"
    outside.write_text("# Outside\n\nSecret words.\n", encoding="utf-8")
    link = VAULT / "escape.md"
    try:
        os.symlink(str(outside), str(link))
    except (OSError, AttributeError) as exc:              # noqa: BLE001
        skip(f"symlinks cannot be made here ({type(exc).__name__}), so the "
             f"symlink-escape check did not run")
        return
    try:
        out = plan()
        check("a link that points outside the vault is refused, not followed",
              all("escape.md" not in (r.get("path") or "")
                  for r in out.get("tag_plan") or [])
              and any("refused" in w for w in out.get("warnings") or []),
              (out.get("warnings"), out.get("tag_plan")))
        check("... and the file outside the vault was never modified",
              outside.read_text(encoding="utf-8") == "# Outside\n\nSecret words.\n")
    finally:
        try:
            link.unlink()
        except OSError:
            pass


def t_caps_make_a_partial_plan_say_so():
    fresh()
    for i in range(5):
        write(f"Bulk/Note {i}.md", f"# Note {i}\n\nText number {i}.\n")
    real = V.MAX_FILES
    V.MAX_FILES = 2
    try:
        out = plan()
    finally:
        V.MAX_FILES = real
    check("hitting the file cap is reported as partial, not silently ignored",
          bool(out.get("partial")), out.get("partial"))
    check("... and the plan says what was left out in plain words",
          any("notes were read" in line for line in out.get("partial") or []),
          out.get("partial"))


def t_an_empty_vault_is_a_clean_no_op():
    fresh()
    before = tree(VAULT)
    out = plan()
    check("an empty vault plans successfully", out.get("ok") is True, out)
    check("... with zero notes, zero MOCs and no Home note",
          out["summary"]["notes_scanned"] == 0 and out["mocs_preview"] == []
          and out["home_preview"] == {}, out["summary"])
    check("... and says so instead of pretending to work",
          any("no notes" in w for w in out.get("warnings") or []), out.get("warnings"))
    check("... and still writes nothing", tree(VAULT) == before)


def t_planning_writes_nothing_to_memory():
    fresh()
    fixture_vault()
    conf_before = listing(CONF)
    out = plan()
    check("the plan does not import jarvis_memory at all",
          sys.modules.get("jarvis_memory") is None,
          "jarvis_memory was imported during a plan")
    check("... and the settings folder gains no memory.db",
          not any("memory.db" in name for name in listing(CONF)),
          listing(CONF))
    check("... and the settings folder is unchanged by a plan",
          conf_before == listing(CONF), (conf_before, listing(CONF)))
    check("the plan is still ok, so this is not a test of nothing",
          out.get("ok") is True and out["summary"]["notes_scanned"] == 3, out.get("summary"))


# --------------------------------------------------------------------------
#   The switch: OFF by default, ON is ONE card, OFF is immediate
# --------------------------------------------------------------------------

def t_the_switch_is_off_by_default_and_one_card_to_turn_on():
    fresh()
    with Framework(enabled=False):
        check("the shipped default is OFF", V.enabled() is False)
        gate = Gate()
        code, out = V.request_enabled(True, gate=gate, tier_of=lambda a: "ask",
                                      spawn=run_now)
        check("turning it ON raises exactly ONE approval card",
              code == 202 and len(gate.calls) == 1, (code, len(gate.calls)))
        check("... for the EXISTING change_own_config action, at ask",
              gate.calls[0][0] == V.SWITCH_ACTION, gate.calls[0][0])
        check("... and it really turned on after the yes", V.enabled() is True)
        check("the card's words say it is PC-only, deletes nothing and can be "
              "turned off again",
              "this PC" in V.SWITCH_CARD and "deleted" in V.SWITCH_CARD
              and "off again" in V.SWITCH_CARD, V.SWITCH_CARD)
    # OFF is immediate and raises no card
    gate = Gate()
    code, out = V.request_enabled(False, gate=gate, tier_of=lambda a: "ask",
                                  spawn=run_now)
    check("turning it OFF is immediate and asks no card",
          code == 200 and out.get("enabled") is False and gate.calls == [],
          (code, gate.calls))
    check("... and it really is off", V.enabled() is False)


def t_a_denied_card_leaves_the_switch_off():
    fresh()
    gate = Gate(outcome="denied")
    V.request_enabled(True, gate=gate, tier_of=lambda a: "ask", spawn=run_now)
    check("a denied card leaves the organizer OFF", V.enabled() is False)


def t_a_tier_that_is_not_ask_is_not_a_person_saying_yes():
    fresh()
    gate = Gate()
    V.request_enabled(True, gate=gate, tier_of=lambda a: "auto", spawn=run_now)
    check("a switch that would resolve below 'ask' turns nothing on",
          V.enabled() is False)


# --------------------------------------------------------------------------
#   The routes: plan is PC-only and flag-gated; status is honest
# --------------------------------------------------------------------------

def t_the_plan_route_is_pc_only():
    fresh()
    fixture_vault()
    with Framework(enabled=True):
        code, out = V.handle_post(V.PLAN_PATH, {"vault": str(VAULT)},
                                  peer="100.101.102.103", local="192.168.1.10")
        check("a preview from another device on the network is REFUSED",
              code == 403 and out.get("error") == "not_this_pc", (code, out))
        code, out = V.handle_post(V.PLAN_PATH, {"vault": str(VAULT)},
                                  peer="127.0.0.1", local="127.0.0.1")
        check("the same request from this PC answers the plan",
              code == 200 and out.get("ok") is True, (code, out))


def t_the_plan_route_is_gated_by_the_switch():
    fresh()
    fixture_vault()
    with Framework(enabled=False):
        code, out = V.handle_post(V.PLAN_PATH, {"vault": str(VAULT)},
                                  peer="127.0.0.1", local="127.0.0.1")
        check("with the organizer OFF the plan route answers 'off', plainly",
              code == 200 and out.get("ok") is False
              and out.get("enabled") is False and "off" in str(out.get("why")).lower(),
              (code, out))
    code, out = V.handle_post(V.PLAN_PATH, {"vault": str(VAULT)},
                              peer="127.0.0.1", local="127.0.0.1")
    check("... and no plan is produced while it is off",
          out.get("ok") is False and "plan_id" not in out, out)


def t_the_status_route_reports_the_switch_honestly():
    fresh()
    code, out = V.handle_get(V.STATUS_PATH)
    check("the status route answers", code == 200 and out.get("ok") is True, out)
    check("... with the switch, its action and the default scheme",
          out.get("enabled") is False and out.get("action") == V.SWITCH_ACTION
          and out.get("default_scheme") == "mocs_only", out)
    check("... and the schemes a caller can pick", out.get("schemes") == list(V.SCHEMES))


def t_install_wraps_the_routes_and_falls_through():
    fresh()
    fixture_vault()
    with Framework(enabled=True):
        stand = RouteStand()
        banner = V.install(stand.Handler, origin_ok=stand.origin_ok,
                           token_ok=stand.token_ok, read_body=stand.read_body)
        check("install() returns a banner line naming the feature",
              isinstance(banner, str) and "vault" in banner.lower(), banner)
        check("... and a second install() says it is already on, without double-wrap",
              "already on" in V.install(stand.Handler, origin_ok=stand.origin_ok,
                                        token_ok=stand.token_ok,
                                        read_body=stand.read_body))
        code, out = stand.get(V.STATUS_PATH)
        check("GET /api/vault/organizer answers through the installed handler",
              code == 200 and out.get("ok") is True, (code, out))
        code, out = stand.post(V.PLAN_PATH, {"vault": str(VAULT)})
        check("POST /api/vault/organize-plan answers a plan through it",
              code == 200 and out.get("ok") is True and "mocs_preview" in out,
              (code, out))
        code, out = stand.post("/api/not-a-vault-route", {})
        check("an unrelated POST reaches the core handler untouched",
              ("POST", "/api/not-a-vault-route") in stand.calls, stand.calls)
        wrong = RouteStand(token=False)
        V.install(wrong.Handler, origin_ok=wrong.origin_ok,
                  token_ok=wrong.token_ok, read_body=wrong.read_body)
        code, out = wrong.post(V.PLAN_PATH, {"vault": str(VAULT)})
        check("a bad token is refused before any plan runs",
              code == 403 and out.get("ok") is False, (code, out))




# --------------------------------------------------------------------------
#   THE WRITER: ONE card, snapshots, one receipt, one Undo
# --------------------------------------------------------------------------

def backups():
    return sorted(p.name for p in (CONF / V.BACKUP_ROOT).glob("*")
                  if (p / "manifest.json").is_file()) if (CONF / V.BACKUP_ROOT).is_dir() else []


def unchanged(before: list) -> bool:
    return tree(VAULT) == before


def plan_and_apply(scheme="mocs_only", gate=None, **kwargs):
    out = plan(scheme=scheme, **kwargs)
    check("(set-up) the plan is ok", out.get("ok") is True, out)
    res = V.apply_plan(out["plan_id"], out["digest"], gate=gate or Gate(),
                       tier_of=lambda action: "ask")
    return out, res


def t_the_writer_does_exactly_what_the_plan_promised():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    write("Work/Beta.md", "# Beta\n\nThe radiator valve was replaced.\n")
    before = tree(VAULT)
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("the writer succeeds", res.get("ok") is True, res)
    planned_notes = {row["path"] for row in out["tag_plan"]}
    planned_creates = {m["name"] for m in out["mocs_preview"]}
    if out.get("home_preview"):
        planned_creates.add(out["home_preview"]["name"])
    after = tree(VAULT)
    changed = {rel for rel, sha, _size in after if (rel, sha, _size) not in before}
    check("every file it changed was IN the plan (and every planned file changed)",
          changed == planned_notes | planned_creates,
          {"missing_from_change": sorted((planned_notes | planned_creates) - changed),
           "unplanned": sorted(changed - (planned_notes | planned_creates))})
    check("... and it applied the exact number the plan counted",
          res["changed"] == len(planned_notes) + len(planned_creates), res)
    check("... it moved nothing under mocs_only", res["moved"] == 0, res)
    check("... and it tells the truth about the receipt and the copy",
          bool(res.get("receipt_id")) and (Path(res["backup"]) / "manifest.json").is_file(),
          res)


def t_the_card_is_one_card_and_says_what_it_does():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    out = plan()
    gate = Gate()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=gate,
                       tier_of=lambda a: "ask")
    check("an organize raises exactly ONE card", len(gate.calls) == 1, gate.calls)
    check("... for the existing organize action", gate.calls[0][0] == V.GATE_ACTION,
          gate.calls[0][0])
    action, detail, prompt = gate.calls[0]
    check("the card says nothing is deleted", "Nothing is deleted" in prompt, prompt)
    check("the card says ONE Undo puts the vault back",
          "Undo" in prompt and "back" in prompt, prompt)
    check("the card carries the file count it really touches",
          str(len(out["tag_plan"]) + len(out["mocs_preview"])) in prompt, prompt)
    check("the detail says undo is offered, nothing deleted, nothing leaves the PC",
          detail.get("undo") is True and detail.get("deletes") is False
          and detail.get("leaves_this_pc") is False, detail)
    check("the writer succeeded", res.get("ok") is True, res)


def t_a_denied_card_changes_nothing():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    before = tree(VAULT)
    before_backups = backups()
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(outcome="denied"),
                       tier_of=lambda a: "ask")
    check("a denied card refuses the whole batch",
          res.get("ok") is False and res.get("gated") is True, res)
    check("... and the vault is byte-identical", unchanged(before))
    check("... and no copy was made for a batch that never ran",
          backups() == before_backups, backups())
    check("... and it says so in plain words", "nothing changed" in res.get("why", ""),
          res.get("why"))


def t_a_low_tier_is_not_a_person_saying_yes():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    before = tree(VAULT)
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "auto")
    check("a gate resolving below 'ask' writes nothing",
          res.get("ok") is False and unchanged(before), res)


def t_a_card_that_cannot_be_shown_changes_nothing():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    before = tree(VAULT)
    out = plan()

    def broken(action, detail, prompt):
        raise RuntimeError("no card surface")
    res = V.apply_plan(out["plan_id"], out["digest"], gate=broken,
                       tier_of=lambda a: "ask")
    check("a gate that raises refuses plainly and writes nothing",
          res.get("ok") is False and "nothing changed" in res.get("why", "")
          and unchanged(before), res)


def t_a_stale_plan_is_refused_and_writes_nothing():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    out = plan()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\nExtra words.\n")
    before = tree(VAULT)
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("a vault edited after the preview is refused as STALE",
          res.get("ok") is False and res.get("stale") is True, res)
    check("... and the edited vault is untouched by the writer", unchanged(before))
    check("... and the words say to make a new plan",
          "new plan" in res.get("why", ""), res.get("why"))


def t_a_wrong_digest_or_unknown_plan_refuses():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    out = plan()
    before = tree(VAULT)
    res = V.apply_plan(out["plan_id"], "0" * 16, gate=Gate(), tier_of=lambda a: "ask")
    check("a digest that is not the plan's is refused",
          res.get("ok") is False and "digest" in res.get("why", ""), res)
    check("... and nothing is written", unchanged(before))
    res = V.apply_plan("vplan_nope", out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("an unknown plan_id is refused (a restart forgets plans)",
          res.get("ok") is False and "not in memory" in res.get("why", ""), res)
    res = V.apply_plan("", "", gate=Gate(), tier_of=lambda a: "ask")
    check("the writer needs both the plan_id and the digest",
          res.get("ok") is False and "plan_id" in res.get("why", ""), res)


def t_the_frontmatter_and_mocs_are_the_planned_ones():
    fresh()
    write("Work/Alpha.md",
          "---\ntags: [owner-thing]\n---\n# Alpha\n\nThe boiler was serviced.\n")
    out = plan()
    row = [r for r in out["tag_plan"] if r["path"] == "Work/Alpha.md"][0]
    V.apply_plan(out["plan_id"], out["digest"], gate=Gate(), tier_of=lambda a: "ask")
    text = (VAULT / "Work/Alpha.md").read_text(encoding="utf-8")
    check("the owner's tag survives the write, exactly", "owner-thing" in text, text)
    check("... and every planned tag is in the note",
          all(t in text for t in row["tags_after"]), row["tags_after"])
    check("... and the planned up: link is there",
          'up: "{}"'.format(row["up"]) in text, text.splitlines()[:6])
    moc = (VAULT / row["moc"]).read_text(encoding="utf-8")
    check("the MOC is a real hub linking the note", "[[Alpha]]" in moc, moc)
    check("the Vault Home is there and links the MOC",
          (VAULT / V.HOME_NAME).is_file()
          and "[[{}]]".format(row["moc"][:-3]) in (VAULT / V.HOME_NAME).read_text(encoding="utf-8"))
    check("the note's other frontmatter keys are untouched",
          text.startswith("---") and text.count("---") >= 2, text[:40])


def t_mocs_only_never_moves_a_note():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    write("Garden/Gnomes.md", "# Gnomes\n\nThree gnomes by the shed.\n")
    before_paths = {rel for rel, _sha, _size in tree(VAULT)}
    out = plan()
    V.apply_plan(out["plan_id"], out["digest"], gate=Gate(), tier_of=lambda a: "ask")
    after = {rel for rel, _sha, _size in tree(VAULT)}
    check("every note is still at its own path after a mocs_only apply",
          before_paths <= after, sorted(before_paths - after))


def t_a_moving_scheme_keeps_the_files_and_undo_restores_paths():
    fresh()
    write("Notes/Alpha.md", "# Alpha\n\nLink to [[Beta]].\n")
    write("Notes/Beta.md", "# Beta\n\nThe radiator valve was replaced.\n")
    before = tree(VAULT)
    out = plan(scheme="topic_folders")
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("the moving scheme really moved notes", res.get("moved") == 2, res)
    moved_as_planned = {Path(m["to_path"]).as_posix() for m in out["moves_preview"]}
    check("... to the paths the plan promised",
          all((VAULT / rel).is_file() for rel in moved_as_planned), moved_as_planned)
    undo = R.undo(res["receipt_id"])
    check("Undo puts the whole vault back", undo.get("ok") is True, undo)
    check("... byte-for-byte and path-for-path", tree(VAULT) == before)
    check("... and takes its own empty folders back off",
          not (VAULT / "02 - Areas & Topics").exists(), "folder left behind")


def t_link_rewrites_keep_aliases_and_headings():
    check("a plain link is rewritten",
          V._rewrite_link("see [[Old]] now", "Old", "New") == "see [[New]] now")
    check("an alias is kept",
          V._rewrite_link("[[Old|the old one]]", "Old", "New") == "[[New|the old one]]")
    check("a heading is kept",
          V._rewrite_link("[[Old#Parts]]", "Old", "New") == "[[New#Parts]]")
    check("a folder prefix in the link text is dropped with the move",
          V._rewrite_link("[[Folder/Old]]", "Old", "New") == "[[New]]")
    check("a link to another note is not touched",
          V._rewrite_link("[[Other]]", "Old", "New") == "[[Other]]")


def t_an_ambiguous_title_is_not_rewritten():
    fresh()
    write("Work/One/Same.md", "# Same\n\nFirst copy.\n")
    write("Work/Two/Same.md", "# Same\n\nSecond copy.\n")
    out = plan(scheme="topic_folders")
    moves = {m["from_path"]: m["to_path"] for m in out["moves_preview"]}
    check("(set-up) two same-title notes collide and one is renamed",
          len(set(moves.values())) == 2, moves)
    rows = V._link_rewrites(V.get_plan(out["plan_id"]))
    check("an ambiguous title is NOT rewritten (no wrong guess)",
          all(old != "Same" for _rel, old, _new in rows), rows)


def t_the_snapshot_is_taken_for_every_changed_file():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    write("Work/Beta.md", "# Beta\n\nThe radiator valve was replaced.\n")
    seen = []
    real = V._snapshot_before_write

    def counting(path, vault):
        seen.append(path)
        return real(path, vault)
    V._snapshot_before_write = counting
    try:
        out, res = plan_and_apply()
    finally:
        V._snapshot_before_write = real
    existing = len(out["tag_plan"])
    check("the guardian was asked for a copy of EVERY existing file the writer changes",
          len(seen) == existing == res["snapshots"], (len(seen), existing, res["snapshots"]))
    check("... and each asked copy is a real guardian snapshot",
          all(s.get("ok") is True for s in
              (real(p, str(VAULT)) for p in seen)))


def t_a_snapshot_failure_refuses_the_whole_batch():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    before = tree(VAULT)
    before_backups = backups()
    out = plan()
    real = V._snapshot_before_write
    V._snapshot_before_write = lambda path, vault: {
        "ok": False, "error": "guardian_unavailable",
        "words": "the time machine is not here"}
    try:
        res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                           tier_of=lambda a: "ask")
    finally:
        V._snapshot_before_write = real
    check("a snapshot that cannot be taken refuses the WHOLE batch",
          res.get("ok") is False and res.get("snapshots_failed") is True, res)
    check("... before a single byte was written", unchanged(before))
    check("... and no NEW copy was left for a batch that never ran",
          backups() == before_backups, backups())


def t_undo_restores_the_exact_tree():
    fresh()
    write("Work/Alpha.md",
          "---\ntags: [owner-thing]\n---\n# Alpha\n\nThe boiler was serviced.\n")
    write("Garden/Gnomes.md", "# Gnomes\n\nThree gnomes by the shed.\n")
    before = tree(VAULT)
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("(set-up) the batch applied", res.get("ok") is True, res)
    check("(set-up) the vault really changed", tree(VAULT) != before)
    undo = R.undo(res["receipt_id"])
    check("ONE Undo puts every byte back", undo.get("ok") is True, undo)
    check("... exactly: no added, missing or changed file", tree(VAULT) == before,
          {"added": [a for a in tree(VAULT) if a not in before],
           "missing": [b for b in before if b not in tree(VAULT)]})
    check("... and the created MOC and Home are gone",
          not (VAULT / V.HOME_NAME).exists()
          and not any(p.name.startswith(V.MOC_PREFIX) for p in VAULT.rglob("*.md")))


def t_undo_works_after_a_restart():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    before = tree(VAULT)
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("(set-up) the batch applied", res.get("ok") is True, res)
    with R._LOCK:
        R._CALLABLES.pop(res["receipt_id"], None)     # a new process has none
    undo = R.undo(res["receipt_id"])
    check("Undo works from the receipt's own saved copy, after a restart",
          undo.get("ok") is True and undo.get("path") == "snapshot", undo)
    check("... and the vault is byte-identical again", tree(VAULT) == before,
          [a for a in tree(VAULT) if a not in before])


def t_a_second_undo_refuses():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    R.undo(res["receipt_id"])
    again = R.undo(res["receipt_id"])
    check("the same Undo twice refuses the second time",
          again.get("ok") is False and again.get("already_undone") is True, again)


def t_the_second_apply_of_the_same_plan_writes_nothing():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    out = plan()
    first = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                         tier_of=lambda a: "ask")
    check("(set-up) the first apply succeeded", first.get("ok") is True, first)
    settled = tree(VAULT)
    second = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                          tier_of=lambda a: "ask")
    check("applying the same plan again refuses (the vault no longer matches it)",
          second.get("ok") is False, second)
    check("... and writes nothing at all", tree(VAULT) == settled)


def t_nothing_is_ever_deleted():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    write("Work/Dup.md", "# Alpha\n\nThe boiler was serviced.\n")
    write("Work/Stub.md", "# Stub\n")
    before = tree(VAULT)
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("(set-up) the batch applied even with a duplicate and a stub",
          res.get("ok") is True, res)
    after_rels = {rel for rel, _sha, _size in tree(VAULT)}
    check("NO note is deleted - every original path still exists",
          {rel for rel, _sha, _size in before} <= after_rels,
          sorted({rel for rel, _sha, _size in before} - after_rels))
    check("... the duplicate and the stub are still there, untouched in number",
          (VAULT / "Work/Dup.md").is_file() and (VAULT / "Work/Stub.md").is_file())
    check("... the plan listed them instead of acting on them",
          out["duplicates_and_stubs"]["duplicates"]
          or out["duplicates_and_stubs"]["empty_stubs"])


def t_a_partial_failure_is_honest_and_undoable():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    write("Work/Beta.md", "# Beta\n\nThe radiator valve was replaced.\n")
    before = tree(VAULT)
    out = plan()
    real = V._write_bytes_atomic

    def half_failing(path, data):
        if str(path).endswith("Work" + os.sep + "Beta.md"):
            raise OSError("disk full (simulated)")
        return real(path, data)
    V._write_bytes_atomic = half_failing
    try:
        res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                           tier_of=lambda a: "ask")
    finally:
        V._write_bytes_atomic = real
    check("a write that fails part-way is reported PARTIAL, with the copy and receipt",
          res.get("ok") is False and res.get("partial") is True
          and bool(res.get("receipt_id"))
          and (Path(res["backup"]) / "manifest.json").is_file(), res)
    check("... it says how many files were written before it stopped",
          res.get("changed") >= 1 and "part-way" in res.get("why", ""), res)
    undo = R.undo(res["receipt_id"])
    check("... and ONE Undo still puts the whole vault back",
          undo.get("ok") is True and tree(VAULT) == before, undo)


def t_taint_is_latched_by_the_writer_and_not_the_plan():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    with GateModule() as gate:
        out = plan()
        check("the PLAN reads notes but does not latch the turn",
              gate.latches == [], gate.latches)
        V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                     tier_of=lambda a: "ask")
        check("the WRITER latches the taint exactly once, with a plain reason",
              len(gate.latches) == 1 and gate.latches[0] == V.TAINT_WHY,
              gate.latches)


def t_the_writer_writes_no_memory_rows():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("(set-up) the batch applied", res.get("ok") is True, res)
    check("the writer imports jarvis_memory nowhere it can write a fact",
          sys.modules.get("jarvis_memory") is None, "jarvis_memory was imported")
    check("... and no memory.db appears in the settings folder",
          not any("memory.db" in name for name in listing(CONF)), listing(CONF))


def t_the_organize_route_is_pc_only_and_flag_gated():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    with Framework(enabled=False):
        code, out = V.handle_post(V.ORGANIZE_PATH,
                                  {"plan_id": "x", "digest": "y"},
                                  peer="127.0.0.1", local="127.0.0.1")
        check("with the organizer OFF the writer route answers 'off'",
              code == 200 and out.get("ok") is False
              and out.get("enabled") is False, (code, out))
    with Framework(enabled=True):
        code, out = V.handle_post(V.ORGANIZE_PATH, {"plan_id": "x", "digest": "y"},
                                  peer="100.101.102.103", local="192.168.1.10")
        check("another device may not organize this PC's vault",
              code == 403 and out.get("error") == "not_this_pc", (code, out))
        code, out = V.handle_post(V.ORGANIZE_PATH, {},
                                  peer="127.0.0.1", local="127.0.0.1")
        check("the writer route refuses without a plan_id and digest",
              code == 400 and "plan_id" in str(out.get("error")), (code, out))


def t_the_organize_route_works_end_to_end_through_install():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    V.set_enabled(True)
    with GateModule(), Framework(enabled=True):
        stand = RouteStand()
        V.install(stand.Handler, origin_ok=stand.origin_ok,
                  token_ok=stand.token_ok, read_body=stand.read_body)
        code, planned = stand.post(V.PLAN_PATH, {"vault": str(VAULT)})
        check("(set-up) the plan route answered", code == 200
              and planned.get("ok") is True, (code, planned))
        code, applied = stand.post(V.ORGANIZE_PATH,
                                   {"plan_id": planned["plan_id"],
                                    "digest": planned["digest"]})
        check("the writer route applies that plan through the installed handler",
              code == 200 and applied.get("ok") is True, (code, applied))
        check("... and the vault really changed",
              (VAULT / V.HOME_NAME).is_file()
              and "[[_MOC - Work]]" in (VAULT / V.HOME_NAME).read_text(encoding="utf-8"))


def t_the_status_route_reports_the_writer():
    fresh()
    with Framework(enabled=True):
        code, out = V.handle_get(V.STATUS_PATH)
    check("the status route says the writer exists, its action and its tier",
          code == 200 and out.get("can_apply") is True
          and out.get("apply_action") == V.GATE_ACTION
          and out.get("apply_tier") == "ask", out)
    check("... and it still reports the plan switch and default scheme",
          out.get("default_scheme") == "mocs_only" and "enabled" in out, out)


def t_an_existing_moc_is_snapshotted_then_undone_exactly():
    fresh()
    write("Work/Alpha.md", "# Alpha\n\nThe boiler was serviced.\n")
    write("_MOC - Work.md", "# my own hub\n\nDo not lose these words.\n")
    before = tree(VAULT)
    out = plan()
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("(set-up) the batch applied over an existing MOC",
          res.get("ok") is True, res)
    check("the existing MOC was snapshotted before being replaced",
          res["snapshots"] == len(out["tag_plan"]) + 1, res["snapshots"])
    check("... and the new one is the generated hub",
          "# Work" in (VAULT / "_MOC - Work.md").read_text(encoding="utf-8"))
    R.undo(res["receipt_id"])
    check("Undo puts the owner's own MOC words back, byte for byte",
          tree(VAULT) == before, tree(VAULT))


def t_a_database_child_page_lands_under_databases():
    fresh()
    write("Projects/_Database - Projects.md", "# Projects\n\nThe database.\n")
    write("Projects/Launch.md",
          "---\ndatabase: Projects\n---\n# Launch\n\nThe launch plan.\n")
    out = plan(scheme="topic_folders")
    res = V.apply_plan(out["plan_id"], out["digest"], gate=Gate(),
                       tier_of=lambda a: "ask")
    check("(set-up) the batch applied", res.get("ok") is True, res)
    check("a database's child page is filed under Databases/<Name>/",
          (VAULT / "Databases" / "Projects" / "Launch.md").is_file(),
          sorted(p.relative_to(VAULT).as_posix() for p in VAULT.rglob("*.md")))
    check("... and the database index note too",
          (VAULT / "Databases" / "Projects" / "_Database - Projects.md").is_file())


# --------------------------------------------------------------------------
#   Runner
# --------------------------------------------------------------------------

def main() -> int:
    print(f"tree: {HERE}")
    for fn in (t_plan_is_completely_read_only,
               t_the_read_only_instrument_bites,
               t_plan_payload_is_the_preview_the_next_slice_needs,
               t_mocs_link_every_note_and_the_notes_point_up,
               t_tag_merge_never_erases_the_owners_tags,
               t_duplicates_and_empty_stubs_are_listed_never_deleted,
               t_the_same_vault_plans_byte_identically_twice,
               t_the_digest_instrument_bites,
               t_topic_folders_previews_safe_moves,
               t_para_classifies_by_what_the_note_is,
               t_an_unknown_scheme_is_refused_in_plain_words,
               t_a_symlink_out_of_the_vault_is_refused,
               t_caps_make_a_partial_plan_say_so,
               t_an_empty_vault_is_a_clean_no_op,
               t_planning_writes_nothing_to_memory,
               t_the_switch_is_off_by_default_and_one_card_to_turn_on,
               t_a_denied_card_leaves_the_switch_off,
               t_a_tier_that_is_not_ask_is_not_a_person_saying_yes,
               t_the_plan_route_is_pc_only,
               t_the_plan_route_is_gated_by_the_switch,
               t_the_status_route_reports_the_switch_honestly,
               t_install_wraps_the_routes_and_falls_through,
               t_the_writer_does_exactly_what_the_plan_promised,
               t_the_card_is_one_card_and_says_what_it_does,
               t_a_denied_card_changes_nothing,
               t_a_low_tier_is_not_a_person_saying_yes,
               t_a_card_that_cannot_be_shown_changes_nothing,
               t_a_stale_plan_is_refused_and_writes_nothing,
               t_a_wrong_digest_or_unknown_plan_refuses,
               t_the_frontmatter_and_mocs_are_the_planned_ones,
               t_mocs_only_never_moves_a_note,
               t_a_moving_scheme_keeps_the_files_and_undo_restores_paths,
               t_link_rewrites_keep_aliases_and_headings,
               t_an_ambiguous_title_is_not_rewritten,
               t_the_snapshot_is_taken_for_every_changed_file,
               t_a_snapshot_failure_refuses_the_whole_batch,
               t_undo_restores_the_exact_tree,
               t_undo_works_after_a_restart,
               t_a_second_undo_refuses,
               t_the_second_apply_of_the_same_plan_writes_nothing,
               t_nothing_is_ever_deleted,
               t_a_partial_failure_is_honest_and_undoable,
               t_taint_is_latched_by_the_writer_and_not_the_plan,
               t_the_writer_writes_no_memory_rows,
               t_the_organize_route_is_pc_only_and_flag_gated,
               t_the_organize_route_works_end_to_end_through_install,
               t_the_status_route_reports_the_writer,
               t_an_existing_moc_is_snapshotted_then_undone_exactly,
               t_a_database_child_page_lands_under_databases):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:                                 # noqa: BLE001
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
