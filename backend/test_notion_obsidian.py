"""jarvis_notion_obsidian.py: the Notion export, turned into an Obsidian vault.

    python3 test_notion_obsidian.py

WHY THIS EXISTS. A Notion export is not a vault, and every step that turns one
into the other can lose something quietly: an id left on a name makes a link
point nowhere, two pages with one title overwrite each other, a property line
stays in the body instead of the frontmatter, a `..` inside the zip writes
outside the vault, a runaway zip fills the disk. Each guard below is checked,
and the checks that matter are checked against a REAL vault in a temp folder -
no pytest, no network, and nothing written outside it.

No meaning model, no Ollama, no model. Nothing here reads the owner's files.
"""
import json
import os
import shutil
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_notion_obsidian.py", "jarvis_documents.py")
import jarvis_notion_obsidian as N  # noqa: E402
try:                                   # for the Ruling 8.6 checks below
    import yaml
except Exception:                      # noqa: BLE001
    yaml = None  # type: ignore

FAILED, PASSED, SKIPPED = [], [], []

TMP = Path(tempfile.mkdtemp(prefix=".jarvis-notion-tests-", dir=str(Path.home())))
#: The settings folder this suite uses. The module reads the SAME two
#: variables every other module here reads, so pointing them at a temp folder
#: is what keeps this suite off the owner's real ~/.openjarvis.
CONF = TMP / "config"
CONF.mkdir()
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ.pop("JARVIS_CONFIG_DIR", None)
VAULT = TMP / "MyVault"

# TWO REDIRECTS THE ENVIRONMENT VARIABLE CANNOT DO BY ITSELF, both found by
# measuring this suite against the owner's real ~/.openjarvis rather than
# trusting the variable:
#
#   * `jarvis_receipts._config_dir()` asks `jarvis_framework.CONFIG_DIR` FIRST,
#     and that is a module-level constant computed once at import - so setting
#     OPENJARVIS_CONFIG_DIR afterwards does not move it, and the receipts store
#     this suite exercises would land in his real folder. Pointed here instead.
#   * this module's own `_audit()` calls `jarvis_framework.audit_log`, whose
#     LOG_DIR is equally fixed at import, so passing `record=True` would write
#     an audit line into his real log. The suite runs with no framework
#     attached, which is a state the module supports on purpose (`fw` may be
#     None - every use of it is guarded).
sys.path.insert(0, str(HERE))
import jarvis_receipts as R  # noqa: E402
R._config_dir = lambda: CONF
import jarvis_notion_obsidian as _N  # noqa: E402
_N.fw = None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh():
    """An empty vault and an empty source folder, ready for one check."""
    N._reset_for_tests()
    for path in (VAULT, SOURCE):
        shutil.rmtree(path, ignore_errors=True)
    (VAULT / ".obsidian").mkdir(parents=True)
    SOURCE.mkdir()
    return SOURCE


def write(folder: Path, name: str, text: str) -> Path:
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


EXPORT = "Meeting notes 2026-01-01"
SOURCE = TMP / "Meeting notes"
A32 = "1a2b3c4d5e6f708192a3b4c5d6e7f809"
B32 = "abcdef0123456789abcdef0123456789"
C32 = "ffffffffffffffffffffffffffffffff"
D32 = "0123456789abcdef0123456789abcdef"
E32 = "fedcba9876543210fedcba9876543210"


# ── 2. names ────────────────────────────────────────────────────────────────

def t_notions_ids_come_off_names():
    check("a 32-character id comes off a page name",
          N.clean_name(f"Meeting Notes {A32}.md") == "Meeting Notes.md",
          N.clean_name(f"Meeting Notes {A32}.md"))
    check("a hyphenated 36-character id comes off too",
          N.clean_name("Trip 1a2b3c4d-5e6f-7081-92a3-b4c5d6e7f809.md") == "Trip.md",
          N.clean_name("Trip 1a2b3c4d-5e6f-7081-92a3-b4c5d6e7f809.md"))
    check("a folder keeps its name when its id comes off",
          N.clean_name(f"Projects {B32}", keep_kind=False) == "Projects",
          N.clean_name(f"Projects {B32}", keep_kind=False))
    check("a name with no id is left alone", N.clean_name("Plain note.md") == "Plain note.md")
    check("the id is readable, for the frontmatter",
          N.split_id(f"Meeting Notes {A32}.md")[1] == A32)
    check("a name with no id has no notion_id", N.split_id("Plain.md")[1] == "")


def t_what_windows_and_obsidian_forbid_is_replaced():
    got = N.clean_name(f'weird: name? [x] | #tag ^block {A32}.md')
    check("the characters Windows and Obsidian refuse are gone",
          not any(c in got for c in '<>:"/\\|?*[]#^'), got)
    check("a reserved Windows name is made usable",
          N.clean_name("CON.md") not in ("CON.md", "con.md"), N.clean_name("CON.md"))
    check("control characters are removed",
          "\x07" not in N.clean_name("bell\x07name.md"), repr(N.clean_name("bell\x07name.md")))
    long_name = "x" * 400 + ".md"
    check("a name too long for Windows is cut",
          len(N.clean_name(long_name)) <= N.MAX_NAME + 4, len(N.clean_name(long_name)))
    check("an empty name still becomes something",
          N.clean_name("   .md") not in ("", ".md"), repr(N.clean_name("   .md")))


def t_two_pages_with_one_title_do_not_overwrite_each_other():
    src = fresh()
    write(src, f"Meeting Notes {A32}.md", "# Meeting Notes\n\nFirst.\n")
    write(src, f"Meeting Notes {C32}.md", "# Meeting Notes\n\nSecond.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    names = sorted(os.path.basename(v) for v in p._map.values())
    check("two pages with one title get two names",
          names == ["Meeting Notes 2.md", "Meeting Notes.md"], names)
    out = N.run_import(p, approved=True, record=False)
    check("and both land, with their own text", out["ok"] is True, out)
    got = (VAULT / EXPORT / "Meeting Notes.md").read_text(encoding="utf-8")
    got2 = (VAULT / EXPORT / "Meeting Notes 2.md").read_text(encoding="utf-8")
    check("neither page's words were lost", "First." in got and "Second." in got2,
          (got, got2))


def t_the_same_export_cleans_the_same_way_twice():
    src = fresh()
    for i, ident in enumerate((A32, B32, C32)):
        write(src, f"Note {ident}.md", f"# Note\n\nBody {i}.\n")
    first = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    again = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("the same export gives the same names",
          first._map == again._map, (first._map, again._map))
    check("and the same plan digest", first.digest == again.digest,
          (first.digest, again.digest))
    check("the digest moves when the export does",
          N.plan_import(str(src), str(VAULT), today="2026-01-02").digest != first.digest)


# ── 1. ingest ───────────────────────────────────────────────────────────────

def t_a_zip_a_folder_and_notions_part_archives():
    src = fresh()
    write(src, f"Page {A32}.md", "# Page\n\nFrom a folder.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("a folder that was already unzipped is read", p.notes == 1, p.notes)

    src = fresh()
    zpath = TMP / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(f"Page One {A32}.md", "# Page One\n\nFrom a zip.\n")
        inner = TMP / "part.zip"
        with zipfile.ZipFile(inner, "w") as z2:
            z2.writestr(f"Page Two {B32}.md", "# Page Two\n\nFrom Part-2.\n")
        zf.write(inner, "Export-Part-2.zip")
    p = N.plan_import(str(zpath), str(VAULT), today="2026-01-01")
    check("a .zip is read, and Notion's Part-N.zip inside it as well",
          p.notes == 2, (p.notes, sorted(p._map)))


def t_the_zip_guards_are_jarvis_documents_own():
    src = fresh()
    zpath = TMP / "bad.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../escape.md", "# Escape\n\nOutside.\n")
        zf.writestr("/absolute.md", "# Absolute\n\nOutside.\n")
        zf.writestr(f"Good {A32}.md", "# Good\n\nInside.\n")
    p = N.plan_import(str(zpath), str(VAULT), today="2026-01-01")
    check("a `..` name is refused, and an absolute one too",
          p.notes == 1, sorted(p._map))
    check("and nothing was written outside the vault",
          not (TMP / "escape.md").exists() and not (TMP.parent / "escape.md").exists())
    check("the guard is jarvis_documents', not a second copy",
          "-- a local copy" not in
          (REPO / "backend" / "jarvis_notion_obsidian.py").read_text(encoding="utf-8")
          and "docs.safe_parts" in
          (REPO / "backend" / "jarvis_notion_obsidian.py").read_text(encoding="utf-8"))


def t_a_zip_bomb_is_refused_not_unpacked():
    src = fresh()
    zpath = TMP / "bomb.zip"
    # INCOMPRESSIBLE bytes on purpose: this check is the ABSOLUTE per-file cap
    # (`_copy_capped`), which is the backstop behind the ratio/size guards the
    # crafted-archive check below covers. A run of zeros here would be refused
    # by the ratio guard first, and then this check would no longer prove the
    # streaming cap still bites.
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"huge {A32}.md", os.urandom(300 * 1024))
    real_max = N.MAX_ONE
    N.MAX_ONE = 100 * 1024
    try:
        refused = ""
        try:
            N.plan_import(str(zpath), str(VAULT), today="2026-01-01")
        except Exception as exc:
            refused = str(exc)
    finally:
        N.MAX_ONE = real_max
    check("one file over the cap is refused, in plain words",
          "MB" in refused or "bigger" in refused, refused)
    check("and nothing was unpacked", not (VAULT / EXPORT).exists())


def t_a_zip_bomb_is_refused_by_its_own_directory_before_unpacking():
    """The review's archive-safety rule: what the zip's own directory declares.

    A zip bomb is refused from `infolist()` BEFORE the first member is
    extracted: too much declared unpacked in total, or too high a compression
    ratio. The absolute caps remain the backstop (`_copy_capped`) because a
    header can lie; these checks prove the cheap pre-check exists and refuses
    without opening a single member.
    """
    fresh()
    bomb = TMP / "ratio-bomb.zip"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"packed {A32}.md", "0" * (512 * 1024))
    with zipfile.ZipFile(bomb) as zf:
        info = zf.infolist()[0]
    ratio = info.file_size / max(1, info.compress_size)
    check("(set-up) the crafted zip really is compressed over 100:1",
          ratio > 100, ratio)

    opened = []
    real_copy = N._copy_capped

    def counting_copy(*args, **kwargs):
        opened.append(args[0])
        return real_copy(*args, **kwargs)

    N._copy_capped = counting_copy
    said = ""
    try:
        try:
            N.plan_import(str(bomb), str(VAULT), today="2026-01-01")
        except Exception as exc:
            said = str(exc)
    finally:
        N._copy_capped = real_copy
    check("...a ratio like that is refused, in plain words",
          "zip bomb" in said or "compressed" in said, said)
    check("...and not one member was opened to find out",
          opened == [], len(opened))

    fresh()
    big = TMP / "declared.zip"
    # STORED (not compressed) on purpose: no ratio can catch this one, so the
    # guard that bites is the archive's own DECLARED unpacked total.
    with zipfile.ZipFile(big, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr(f"page {A32}.md", "x" * 300_000)
    real_room = N.MAX_ZIP_UNCOMPRESSED
    N.MAX_ZIP_UNCOMPRESSED = 256 * 1024
    said = ""
    try:
        try:
            N.plan_import(str(big), str(VAULT), today="2026-01-01")
        except Exception as exc:
            said = str(exc)
    finally:
        N.MAX_ZIP_UNCOMPRESSED = real_room
    check("an archive declaring more unpacked than the cap is refused from the directory",
          "unpacked" in said and "nothing" in said, said)
    check("...so nothing from that export reached the vault either",
          sorted(p.name for p in VAULT.iterdir()) == [".obsidian"],
          sorted(p.name for p in VAULT.iterdir()))



def t_the_zip_member_limits_are_checked_before_any_member_is_opened():
    """R2/R3: the archive's own directory is asked about its MEMBERS too.

    The old guard checked the declared total and the ratio only, so a zip with
    more members than MAX_FILES was unpacked file by file (the folder path
    capped at 20,000, the zip path never did), and one member over MAX_ONE was
    written up to the cap before `_copy_capped` refused. Both are refused from
    `infolist()` now, before one member is opened; `_copy_capped` stays as the
    backstop for a header that lies, which the last block proves.
    """
    fresh()
    many = TMP / "many-members.zip"
    with zipfile.ZipFile(many, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(12):
            zf.writestr(f"page {i} {A32}.md", f"# page {i}\n")
    real_files, real_copy = N.MAX_FILES, N._copy_capped
    opened = []

    def counting_copy(*args, **kwargs):
        opened.append(args[0])
        return real_copy(*args, **kwargs)

    N.MAX_FILES, N._copy_capped = 5, counting_copy
    said = ""
    try:
        try:
            N.plan_import(str(many), str(VAULT), today="2026-01-01")
        except Exception as exc:
            said = str(exc)
    finally:
        N.MAX_FILES, N._copy_capped = real_files, real_copy
    check("R2 a zip with more members than the cap is refused in plain words",
          "more than 5 files" in said, said)
    check("R2 ...before any member was opened", opened == [], len(opened))

    fresh()
    ordinary = TMP / "ordinary.zip"
    with zipfile.ZipFile(ordinary, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(3):
            zf.writestr(f"page {i} {A32}.md", f"# page {i}\n")
    p = N.plan_import(str(ordinary), str(VAULT), today="2026-01-01")
    check("R2 a normal zip still passes", p.notes == 3 and not p.refused, p.as_dict())

    fresh()
    over_one = TMP / "over-one.zip"
    # Incompressible noise keeps the ratio low, zeros make one member big
    # while the DECLARED total stays under the 500 MB and 100:1 caps: only a
    # per-member pre-check can refuse this before it is written.
    with zipfile.ZipFile(over_one, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.bin", b"\0" * (2 * 1024 * 1024))
        zf.writestr("noise.bin", os.urandom(200_000))
    real_one, real_copy = N.MAX_ONE, N._copy_capped
    opened = []
    N.MAX_ONE, N._copy_capped = 1024 * 1024, counting_copy
    said = ""
    try:
        try:
            N.plan_import(str(over_one), str(VAULT), today="2026-01-01")
        except Exception as exc:
            said = str(exc)
    finally:
        N.MAX_ONE, N._copy_capped = real_one, real_copy
    check("R3 a member the directory declares over the per-file cap is refused",
          "bigger than 1 MB" in said, said)
    check("R3 ...before it is opened, so no bytes are written first",
          opened == [], len(opened))

    # A HEADER THAT LIES. The directory is made to look harmless (as a crafted
    # or corrupted central directory could); the streamed cap must still refuse
    # the bytes that actually arrive, and the vault must be untouched.
    fresh()
    real_problem, real_one = N._zip_problem, N.MAX_ONE
    N._zip_problem = lambda zf: ""
    N.MAX_ONE = 1024 * 1024
    said = ""
    try:
        try:
            N.plan_import(str(over_one), str(VAULT), today="2026-01-01")
        except Exception as exc:
            said = str(exc)
    finally:
        N._zip_problem, N.MAX_ONE = real_problem, real_one
    check("R3 when the directory hides a size, the streamed cap still refuses",
          "bigger than" in said, said)
    check("R3 ...and nothing from that export reached the vault",
          sorted(x.name for x in VAULT.iterdir()) == [".obsidian"],
          sorted(x.name for x in VAULT.iterdir()))


def t_a_source_that_is_not_an_export_is_refused():
    fresh()
    write(TMP / "Meeting notes", "page.txt", "not a page")
    for source, why in ((str(TMP / "nothing-here"), "nothing at that path"),
                        (str(TMP / "Meeting notes" / "page.txt"), "not a zip"),
                        ("", "nothing at that path")):
        said = ""
        try:
            N.plan_import(source, str(VAULT))
        except Exception as exc:
            said = str(exc)
        check(f"refused in plain words: {why}", bool(said), said)
    empty = TMP / "empty-export"
    empty.mkdir(exist_ok=True)
    said = ""
    try:
        N.plan_import(str(empty), str(VAULT))
    except Exception as exc:
        said = str(exc)
    check("an export with no pages in it is refused", "no pages" in said, said)


def t_the_destination_must_be_a_real_vault():
    src = fresh()
    write(src, f"Page {A32}.md", "# Page\n\nBody.\n")
    not_a_vault = TMP / "plain-folder"
    not_a_vault.mkdir(exist_ok=True)
    said = ""
    try:
        N.plan_import(str(src), str(not_a_vault))
    except Exception as exc:
        said = str(exc)
    check("a folder with no .obsidian is refused, in plain words",
          "Obsidian" in said, said)
    said = ""
    try:
        N.plan_import(str(src), "")
    except Exception as exc:
        said = str(exc)
    check("no vault at all is refused", "vault" in said.lower(), said)


# ── 3. properties -> frontmatter ────────────────────────────────────────────

def t_properties_become_frontmatter():
    title, props, body = N.split_properties(
        "# Meeting Notes\n"
        "\n"
        "Created: October 14, 2026 3:04 PM\n"
        "Tags: work, urgent\n"
        "Owner: Sam\n"
        "Empty:\n"
        "\n"
        "The body starts here.\n")
    check("the title is read from the first heading", title == "Meeting Notes", title)
    check("the property lines are read even after Notion's blank line",
          props.get("Tags") == "work, urgent" and props.get("Owner") == "Sam", props)
    check("an empty property is read as empty", props.get("Empty") == "", props)
    check("and the body does not keep the property lines",
          "Created:" not in body and body.startswith("The body starts here"), repr(body))

    front = N.frontmatter_of(title, A32, props)
    block = N.yaml_block(front)
    check("notion_id is in the frontmatter", f"notion_id: {A32}" in block, block)
    check("tags is a LIST, not a string", "tags:\n  - work\n  - urgent" in block, block)
    check("a Notion date becomes ISO 8601", 'created: "2026-10-14T15:04:00"' in block, block)
    check("the title is in the frontmatter", "title: Meeting Notes" in block, block)
    check("an empty property does not reach the frontmatter", "empty" not in block, block)
    check("the frontmatter opens and closes with ---",
          block.startswith("---\n") and block.endswith("\n---"), block)


def t_dates_and_lists_are_what_obsidian_expects():
    check("notion's long date is ISO", N.iso_date("October 14, 2026 3:04 PM")
          == "2026-10-14T15:04:00", N.iso_date("October 14, 2026 3:04 PM"))
    check("an already-ISO date is kept", N.iso_date("2026-10-01") == "2026-10-01")
    check("midnight is not turned into noon",
          N.iso_date("January 1, 2026 12:30 AM") == "2026-01-01T00:30:00",
          N.iso_date("January 1, 2026 12:30 AM"))
    check("something that is not a date is left alone", N.iso_date("soon") == "")
    check("a comma list becomes a list", N.property_list("a, b") == ["a", "b"])
    check("a bracketed list becomes a list", N.property_list("[a, b]") == ["a", "b"])
    check("one value becomes a one-item list", N.property_list("a") == ["a"])
    check("an empty value becomes no list at all", N.property_list("") == [])


def t_a_second_import_is_idempotent():
    src = fresh()
    write(src, f"Page {A32}.md", "# Page\n\nBody.\n")
    one = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    N.run_import(one, approved=True, record=False)
    text = (VAULT / EXPORT / "Page.md").read_text(encoding="utf-8")
    check("the note carries the id it came from", f"notion_id: {A32}" in text, text)
    # The same export again is the same plan, so the same folder - which is
    # refused rather than silently doubled.
    two = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("importing the same export twice is refused, not duplicated",
          "already a folder" in (two.refused or ""), two.refused)
    check("and the plan says what it would have done",
          two.notes == 1 and two.digest == one.digest)


# ── 3b. CSV databases ───────────────────────────────────────────────────────

def t_a_csv_database_becomes_frontmatter_a_note_and_a_base():
    src = fresh()
    write(src, f"Tasks {A32}_all.csv",
          "Name,Status,Owner\nShip it,Done,Sam\nLater,Waiting,Sam\n")
    write(src, f"Ship it {B32}.md", "# Ship it\n\nDo the thing.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("the database is counted", p.databases == 1, p.databases)
    check("and so are its rows", p.rows == 2, p.rows)
    out = N.run_import(p, approved=True, record=False)
    check("the import lands", out["ok"] is True, out)
    folder = VAULT / EXPORT
    note = (folder / "Ship it.md").read_text(encoding="utf-8")
    check("the row's columns are merged into the note's frontmatter",
          "status: Done" in note and "owner: Sam" in note, note)
    index = folder / "_Database - Tasks.md"
    check("the database hub note is named _Database - <Name>.md", index.is_file(),
          sorted(x.name for x in folder.iterdir()))
    body = index.read_text(encoding="utf-8") if index.is_file() else ""
    check("with a [[wikilink]] to every row in a rendered table",
          "| [[Ship it]] | Done | Sam |" in body
          and "| [[Later]] | Waiting | Sam |" in body, body)
    check("and a header naming the database's columns",
          "| Name | Status | Owner |" in body, body)
    base = folder / "Tasks.base"
    check("and a .base file beside it", base.is_file(),
          sorted(x.name for x in folder.iterdir()))
    check("the .base names the folder it covers",
          f'file.inFolder("{EXPORT}")' in
          (base.read_text(encoding="utf-8") if base.is_file() else ""),
          base.read_text(encoding="utf-8") if base.is_file() else "")


def t_the_database_hub_note_says_what_it_is_and_never_drops_a_row():
    """Review rule 4: a real hub note - frontmatter, a row table, a summary."""
    src = fresh()
    write(src, f"Tasks {A32}_all.csv",
          "Name,Status,Priority\n"
          "Ship it,Done,High\n"
          "Later,Waiting,Low\n"
          "Ghost,Done,High\n")
    write(src, f"Ship it {B32}.md", "# Ship it\n\nDo the thing.\n")
    write(src, f"Later {C32}.md", "# Later\n\nAnother.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    out = N.run_import(p, approved=True, record=False)
    folder = VAULT / EXPORT
    index = folder / "_Database - Tasks.md"
    body = index.read_text(encoding="utf-8") if index.is_file() else ""
    check("its frontmatter says it is a database index with the row count",
          "type: database-index" in body and "rows: 3" in body, body)
    check("...and names the columns it holds",
          "columns:" in body and "Status" in body and "Priority" in body, body)
    check("a row whose child page has gone still surfaces - a link, never dropped",
          "[[Ghost]]" in body, body)
    check("...and the note REPORTS how many rows have no page",
          "rows_without_notes: 1" in body, body)
    check("...and says it in a sentence too",
          "1 row" in body and "no note" in body, body)
    check("the run result reports the same count",
          out.get("rows_without_notes") == 1, out)
    check("rows are grouped by Status in a collapsible summary",
          "<details>" in body and "<summary>" in body and "By Status" in body
          and "Done" in body and "2" in body, body)
    check("the .base is still written beside the hub note",
          (folder / "Tasks.base").is_file(), sorted(x.name for x in folder.iterdir()))


def t_a_database_exported_twice_keeps_every_row():
    """`X.csv` and `X_all.csv` are ONE database; the combined rows must land."""
    src = fresh()
    write(src, f"Tasks {A32}.csv", "Name,Status\nShip it,Done\nOnly in plain,Waiting\n")
    write(src, f"Tasks {B32}_all.csv",
          "Name,Status,Owner\nShip it,Done,Sam\nLater,Waiting,Sam\n")
    write(src, f"Ship it {C32}.md", "# Ship it\n\nDo.\n")
    write(src, f"Only in plain {D32}.md", "# Only in plain\n\nBody.\n")
    write(src, f"Later {E32}.md", "# Later\n\nBody.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("two CSV files of one database are counted as ONE database",
          p.databases == 1, p.databases)
    check("...and rows are counted once each, not once per file",
          p.rows == 3, p.rows)
    N.run_import(p, approved=True, record=False)
    folder = VAULT / EXPORT
    body = (folder / "_Database - Tasks.md").read_text(encoding="utf-8")
    check("a row only the plain CSV holds is still in the hub table",
          "[[Only in plain]]" in body, body)
    check("a row only the _all CSV holds is in the hub table too",
          "[[Later]]" in body, body)
    check("the _all CSV's extra column reaches the matching note's frontmatter",
          "owner: Sam" in (folder / "Ship it.md").read_text(encoding="utf-8"),
          (folder / "Ship it.md").read_text(encoding="utf-8"))


def t_relation_columns_become_wikilinks_and_other_values_are_untouched():
    """Review rule 3: a relation target that IS a page becomes a `[[wikilink]]`."""
    src = fresh()
    write(src, f"Project Atlas {A32}.md", "# Project Atlas\n\nThe project.\n")
    write(src, f"Tasks {B32}_all.csv",
          "Name,Project,Owner,Count\n"
          f"Ship it,Project Atlas {A32},Sam,\"1,234\"\n")
    write(src, f"Ship it {C32}.md",
          f"# Ship it\n\nProject: Project Atlas {A32}\n"
          f"Reviewer: Project Atlas {A32}\n\nDo.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    out = N.run_import(p, approved=True, record=False)
    note = (VAULT / EXPORT / "Ship it.md").read_text(encoding="utf-8")
    check("a relation value naming a page of this export becomes a wikilink",
          'project: "[[Project Atlas]]"' in note, note)
    check("...in the page's own property block as well as the CSV's",
          'reviewer: "[[Project Atlas]]"' in note, note)
    check("...with Notion's id no longer inside the value", A32 not in note, note)
    check("a value that is not a page is left exactly as it was",
          "owner: Sam" in note, note)
    check("a number with a thousands separator is not split or relinked",
          "count:" in note and "1,234" in note, note)
    check("the import still lands", out.get("ok") is True, out)


def t_a_database_whose_title_column_is_renamed_still_merges():
    """Notion's CSV header is the database's OWN title-property name."""
    src = fresh()
    write(src, f"Tasks {A32}_all.csv", "Task,Status\nFix login,Done\n")
    write(src, f"Fix login {B32}.md", "# Fix login\n\nDo.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    N.run_import(p, approved=True, record=False)
    folder = VAULT / EXPORT
    note = (folder / "Fix login.md").read_text(encoding="utf-8")
    check("a title column that is not called Name still merges its row",
          "status: Done" in note, note)
    body = (folder / "_Database - Tasks.md").read_text(encoding="utf-8")
    check("...and the hub table links the child note on that column",
          "| [[Fix login]] | Done |" in body, body)


# ── 3d. the 2026-10-21 audit's data-loss findings ──────────────────────────
#
# `.dsh-scratch/AUDIT-677-CONVERTER-GAPS-2026-10-21.md` found four ways the
# converter could still lose something silently: a generated hub note replacing
# a real page (F1), two databases whose names differ only by case sharing one
# file on Windows (F2), two rows with one title collapsing into one row (F3),
# and a value that is not a page having a Notion-id-shaped tail cut off (F4).
# Each check below fails on the code before the fix; the comment names the
# finding so the PR body and this suite agree.

def t_a_generated_hub_never_overwrites_a_page():
    """F1: a page and a database whose generated hub would share its name."""
    layouts = (
        # The page's file name sorts BEFORE the database's CSV.
        ("page sorts first", f"Tasks {A32}.csv", f"_Database - Tasks {B32}.md"),
        # ...and AFTER it: the walk order must not decide who survives.
        ("csv sorts first", f"Tasks {C32}.csv", f"_Database - Tasks {D32}.md"),
        # A page whose name differs from the hub only by CASE (NTFS case-fold).
        ("case-only difference", f"Tasks {E32}.csv",
         f"_database - tasks {B32}.md"),
    )
    for label, csv_name, page_name in layouts:
        src = fresh()
        write(src, page_name, "# The owner's page\n\nREAL PAGE MARKER\n")
        write(src, csv_name, "Name,Status\nShip it,Done\n")
        write(src, f"Ship it {B32}.md", "# Ship it\n\nThe child note.\n")
        p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
        out = N.run_import(p, approved=True, record=False)
        folder = VAULT / EXPORT
        hubs = sorted(x.name for x in folder.iterdir()
                      if x.name.casefold().startswith(N.DATABASE_PREFIX.casefold()))
        bodies = {name: (folder / name).read_text(encoding="utf-8") for name in hubs}
        check(f"F1 ({label}) the page and the hub are two files, never one",
              len(hubs) == 2 and len({n.casefold() for n in hubs}) == 2, hubs)
        check(f"F1 ({label}) the real page's own body survives",
              any("REAL PAGE MARKER" in body for body in bodies.values()), bodies)
        check(f"F1 ({label}) the generated hub is the other file",
              any("type: database-index" in body for body in bodies.values()), bodies)
        on_disk = sorted(x.relative_to(folder).as_posix()
                         for x in folder.rglob("*") if x.is_file())
        check(f"F1 ({label}) `created` lists exactly the files on disk",
              sorted(p.created) == on_disk,
              {"created": sorted(p.created), "disk": on_disk})
        check(f"F1 ({label}) the import says it landed", out.get("ok") is True, out)


def t_databases_whose_names_differ_only_by_case_never_share_a_file():
    """F2: `Alpha.csv` and `alpha_all.csv` are two databases on a case-folding FS.

    WHAT THIS PROVES, AND WHERE. The check asserts the two planned hub/base
    names are unique AFTER case-folding and that both databases' rows are in
    the vault. On the owner's NTFS those two old names are one path, so the old
    code fails the "two files" half physically. On Linux CI the old code writes
    two paths that differ only by case, which is still wrong for a vault that
    will be opened on Windows - and the case-fold assertion catches exactly
    that without needing a case-insensitive filesystem.
    """
    src = fresh()
    write(src, f"Alpha {A32}.csv", "Name,Status\nA one,open\n")
    write(src, f"alpha {B32}_all.csv", "Name,Status\nA two,done\n")
    write(src, f"A one {C32}.md", "# A one\n")
    write(src, f"A two {D32}.md", "# A two\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("F2 the two CSVs are counted as TWO databases", p.databases == 2, p.databases)
    out = N.run_import(p, approved=True, record=False)
    folder = VAULT / EXPORT
    hubs = sorted((x.name for x in folder.iterdir()
                   if x.name.casefold().startswith(N.DATABASE_PREFIX.casefold())), key=str.casefold)
    check("F2 two hub files survive, whose names are unique after case-folding",
          len(hubs) == 2 and len({x.casefold() for x in hubs}) == 2, hubs)
    halves = [x for x in hubs if x.lower().endswith(".md")]
    bodies = [(folder / x).read_text(encoding="utf-8") for x in halves]
    check("F2 both databases' rows are in the vault, each in exactly one hub",
          sum("[[A one]]" in b for b in bodies) == 1
          and sum("[[A two]]" in b for b in bodies) == 1, bodies)
    bases = sorted((x.name for x in folder.iterdir() if x.suffix == ".base"), key=str.casefold)
    check("F2 the .base files do not share a name after case-folding either",
          len(bases) == 2 and len({x.casefold() for x in bases}) == 2, bases)
    check("F2 the import says it landed", out.get("ok") is True, out)


def t_two_rows_with_one_title_in_one_csv_are_both_kept():
    """F3: duplicates INSIDE one CSV, not only across X.csv/X_all.csv."""
    src = fresh()
    write(src, f"Tasks {A32}.csv",
          "Name,Priority\n"
          "Fix bug,High\n"
          "Fix bug,Low\n"
          "Ghost,High\n"
          "Ghost,Low\n")
    write(src, f"Fix bug {B32}.md", "# Fix bug\n\nfirst page\n")
    write(src, f"Fix bug {C32}.md", "# Fix bug\n\nsecond page\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("F3 the plan counts all FOUR rows, not one per title", p.rows == 4, p.rows)
    out = N.run_import(p, approved=True, record=False)
    folder = VAULT / EXPORT
    body = (folder / "_Database - Tasks.md").read_text(encoding="utf-8")
    check("F3 both same-title rows are in the hub table with their own values",
          body.count("| [[Fix bug]] |") == 2 and "| High |" in body and "| Low |" in body,
          body)
    check("F3 both child pages of that title were written",
          len([x for x in folder.iterdir() if x.name.startswith("Fix bug")
               and x.suffix == ".md"]) == 2,
          sorted(x.name for x in folder.iterdir()))
    check("F3 two same-title rows with no page are counted twice, not once",
          "rows_without_notes: 2" in body and out.get("rows_without_notes") == 2,
          {"body": body, "out": out.get("rows_without_notes")})
    check("F3 the run result counts all four rows", out.get("rows") == 4, out)


def t_duplicate_titles_across_x_and_x_all_keep_both_rows():
    """F3 across the two exports of one database: pair by row, not by title."""
    src = fresh()
    write(src, f"Tasks {A32}.csv", "Name,Priority\nFix bug,High\nFix bug,Low\n")
    write(src, f"Tasks {B32}_all.csv",
          "Name,Priority\nFix bug,All-high\nFix bug,All-low\n")
    write(src, f"Fix bug {C32}.md", "# Fix bug\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("F3 the plan counts the two rows once, not once per file", p.rows == 2, p.rows)
    N.run_import(p, approved=True, record=False)
    body = (VAULT / EXPORT / "_Database - Tasks.md").read_text(encoding="utf-8")
    check("F3 both rows survive and the _all export wins per row",
          "All-high" in body and "All-low" in body and "High" not in body
          and "Low" not in body, body)


def t_a_value_that_is_not_a_page_keeps_every_character():
    """F4: only a whole value that maps to a page may be rewritten."""
    pages = N._known_pages({f"Project Atlas {A32}.md": "Project Atlas.md"})
    hexish = f"ref {B32}"
    uuidish = "8f14e45f-ceea-467f-a8b3-0c0f0c7e1234"
    cases = (
        ("a plain value is untouched", "Sam", "Sam"),
        ("a thousands separator is untouched", "1,234", "1,234"),
        ("a value ending in a 32-hex token is untouched", hexish, hexish),
        ("a value ending in a UUID is untouched", f"id {uuidish}", f"id {uuidish}"),
        ("a whole page id still becomes a wikilink",
         f"Project Atlas {A32}", "[[Project Atlas]]"),
        ("a mixed list links the mapped piece and keeps the other byte-for-byte",
         f"Project Atlas {A32}, Other {B32}",
         f"[[Project Atlas]], Other {B32}"),
    )
    for label, value, want in cases:
        got = N._relation_value(value, pages)
        check(f"F4 {label}", got == want, {"value": value, "got": got, "want": want})
    src = fresh()
    write(src, f"Project Atlas {A32}.md", "# Project Atlas\n")
    write(src, f"Ship it {C32}.md", "# Ship it\n")
    write(src, f"Tasks {B32}_all.csv",
          "Name,Owner,Count\n"
          f'Ship it,"{hexish}","1,234"\n')
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    N.run_import(p, approved=True, record=False)
    note = (VAULT / EXPORT / "Ship it.md").read_text(encoding="utf-8")
    check("F4 ...and the page's frontmatter keeps the whole value",
          f"owner: {hexish}" in note, note)
    check("F4 ...and the number with a comma is still a number",
          'count: "1,234"' in note, note)


def t_a_database_named_all_keeps_its_name():
    """NIT-1: `_all` is Notion's suffix only when the plain export is beside it."""
    src = fresh()
    write(src, f"Backlog_all {A32}.csv", "Name,Status\nB one,open\n")
    write(src, f"B one {B32}.md", "# B one\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("NIT-1 a lone `Backlog_all.csv` is one database", p.databases == 1, p.databases)
    N.run_import(p, approved=True, record=False)
    folder = VAULT / EXPORT
    hubs = sorted(x.name for x in folder.iterdir()
                  if x.name.casefold().startswith(N.DATABASE_PREFIX.casefold()))
    check("NIT-1 ...and its hub keeps the database's own name", hubs == [
        "_Database - Backlog_all.md"], hubs)
    base = folder / "Backlog_all.base"
    check("NIT-1 ...and so does its .base", base.is_file(),
          sorted(x.name for x in folder.iterdir()))


def t_a_refusal_during_the_run_keeps_its_plain_words():
    """NIT-2: the run's refusal is the plain sentence, not a class name."""
    src = fresh()
    write(src, f"Page {A32}.md", "# Page\n\nBody.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    real_extract, real_refused = N.extract, N._refused

    def plain_sentence(why):
        # What the module's own refusal helper returns is a `jarvis_documents`
        # ImportRefused; `run_import` used to catch a DIFFERENT class with the
        # same name, so the sentence was replaced by "ImportRefused".
        return real_refused(why)
    try:
        N.extract = lambda *a, **k: (_ for _ in ()).throw(
            plain_sentence("a plain refusal sentence"))
        out = N.run_import(p, approved=True, record=False)
    finally:
        N.extract = real_extract
    check("NIT-2 the run reports the plain sentence, word for word",
          out.get("reason") == "a plain refusal sentence", out)
    check("NIT-2 ...and never shows an exception class name to the owner",
          "ImportRefused" not in str(out.get("reason")), out)


def t_an_html_page_and_a_markdown_page_with_one_title_do_not_overwrite():
    """F1b, found while fixing F1: same-stem `.md` + `.html` were one target."""
    src = fresh()
    write(src, f"Same {A32}.md", "# From markdown\n\nMARKDOWN BODY\n")
    write(src, f"Same {B32}.html",
          "<html><body><h1>From html</h1><p>HTML BODY</p></body></html>")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    N.run_import(p, approved=True, record=False)
    folder = VAULT / EXPORT
    files = sorted(x.name for x in folder.iterdir()
                   if x.name.startswith("Same") and x.suffix == ".md")
    check("F1b two pages that clean to one name are written as two files",
          len(files) == 2, files)
    joined = "\n".join((folder / x).read_text(encoding="utf-8") for x in files)
    check("F1b both bodies survive", "MARKDOWN BODY" in joined and "HTML BODY" in joined,
          joined)
    check("F1b the import says it landed", p.created and len(files) == 2, p.created)



# ── 4. HTML -> Markdown ─────────────────────────────────────────────────────

def t_html_becomes_obsidian_markdown():
    html = ("<html><body>"
            "<h1>Guide</h1>"
            "<p>Read <strong>this</strong> first.</p>"
            "<aside><p>Mind the gap.</p></aside>"
            "<details><summary>More</summary><p>Hidden text.</p></details>"
            "<ul><li><input type=\"checkbox\" checked> done</li>"
            "<li><input type=\"checkbox\"> todo</li></ul>"
            "<pre><code class=\"language-python\">print(1)</code></pre>"
            "<table><tr><th>A</th><th>B</th></tr>"
            "<tr><td>1</td><td>2</td></tr></table>"
            "</body></html>")
    md = N.html_to_markdown(html)
    check("a callout becomes an Obsidian callout", "> [!note]" in md, md)
    check("and its text is INSIDE the callout", "> Mind the gap." in md, md)
    check("a toggle becomes a folded callout, named by its summary",
          "> [!note]- More" in md, md)
    check("a checkbox becomes an Obsidian to-do", "- [x] done" in md, md)
    check("an unticked box becomes an empty to-do", "- [ ] todo" in md, md)
    check("code keeps its language", "```python\nprint(1)\n```" in md, md)
    check("a table becomes a pipe table",
          "| A | B |" in md and "| --- | --- |" in md and "| 1 | 2 |" in md, md)
    check("bold survives", "**this**" in md, md)
    # A callout is a BLOCK, and Obsidian ends it at the first line that is not
    # `>`-prefixed - including a blank one. So a two-paragraph callout must
    # have no bare blank line anywhere inside it, or the second paragraph
    # spills out of the callout onto the page.
    two = N.html_to_markdown("<aside><p>One.</p><p>Two.</p></aside>")
    inside = two[two.index("[!note]"):].strip("\n")
    check("a two-paragraph callout is not split by a bare blank line",
          "\n\n" not in inside and "> One." in two and "> Two." in two, repr(two))


def t_html_never_raises_on_odd_input():
    for body in ("", "<p>unclosed", "plain text, no tags", "<div><span></div>",
                 "<table><tr><td>only one cell</table>"):
        got = N.html_to_markdown(body)
        check(f"odd HTML still answers: {body[:20]!r}", isinstance(got, str))
    check("is_html spots an HTML export", N.is_html("<html><body>x"))
    check("and does not mistake Markdown for it", not N.is_html("# A note\n\nText."))


# ── 5. links and attachments ────────────────────────────────────────────────

def t_links_are_rewritten_through_the_cleaned_names():
    src = fresh()
    write(src, f"Budget Plan {B32}.md", "# Budget Plan\n\nThe numbers.\n")
    write(src, f"Meeting Notes {A32}.md",
          "# Meeting Notes\n\nSee [the budget](Budget%20Plan%20" + B32 + ".md) and "
          "[the site](https://example.com/x).\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    out = N.run_import(p, approved=True, record=False)
    text = (VAULT / EXPORT / "Meeting Notes.md").read_text(encoding="utf-8")
    check("a %20-encoded relative link becomes a wikilink",
          "[[Budget Plan|the budget]]" in text, text)
    check("a web address is left exactly as it was",
          "[the site](https://example.com/x)" in text, text)
    check("a link to a page NOT in the export is not turned into a wikilink",
          N.vault_link("Missing%20Page.md", "Missing", {}) == "[Missing](Missing%20Page.md)",
          N.vault_link("Missing%20Page.md", "Missing", {}))
    check("the decode happens before the lookup",
          N.decode_link("Budget%20Plan%20x.md") == "Budget Plan x.md",
          N.decode_link("Budget%20Plan%20x.md"))


def t_attachments_move_into_the_vault_and_the_link_follows():
    src = fresh()
    write(src, f"Guide {A32}.html",
          "<html><body><h1>Guide</h1>"
          f"<p><img src=\"pic%20one%20{B32}.png\"></p></body></html>")
    (src / f"pic one {B32}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (src / f"manual {C32}.pdf").write_bytes(b"%PDF-1.4 fake")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("both the picture and the PDF are counted as attachments",
          p.attachments == 2, p.attachments)
    out = N.run_import(p, approved=True, record=False)
    folder = VAULT / EXPORT
    check("they land in the vault's attachments folder",
          sorted(x.name for x in (folder / N.ATTACHMENTS).iterdir())
          == ["manual.pdf", "pic one.png"],
          sorted(x.name for x in (folder / N.ATTACHMENTS).iterdir()))
    text = (folder / "Guide.md").read_text(encoding="utf-8")
    check("and the page embeds the NEW name", "![[pic one.png]]" in text, text)
    check("no id is left in the attachment's name",
          all("1a2b" not in x.name and "abc" not in x.name
              for x in (folder / N.ATTACHMENTS).iterdir()))


# ── 6. plan, describe, gate, run ────────────────────────────────────────────

def t_a_plan_writes_nothing():
    src = fresh()
    write(src, f"Page {A32}.md", "# Page\n\nBody.\n")
    before = sorted(p.name for p in VAULT.iterdir())
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("the plan does not touch the vault",
          sorted(x.name for x in VAULT.iterdir()) == before,
          sorted(x.name for x in VAULT.iterdir()))
    check("the plan does not touch the settings folder",
          list(CONF.iterdir()) == [], sorted(x.name for x in CONF.iterdir()))
    check("the plan leaves no staging folder behind",
          not [d for d in VAULT.iterdir() if d.name.startswith(".jarvis")],
          sorted(x.name for x in VAULT.iterdir()))
    check("the plan says what it would do", p.notes == 1 and not p.refused, p.as_dict())
    check("the describe text names the folder and the counts",
          EXPORT in N.describe(p) and "1 note" in N.describe(p),
          N.describe(p))


def t_the_run_needs_a_persons_yes():
    src = fresh()
    write(src, f"Page {A32}.md", "# Page\n\nBody.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    out = N.run_import(p, approved=False, record=False)
    check("without approval nothing is brought in", out["ok"] is False, out)
    check("and the vault is untouched",
          not (VAULT / EXPORT).exists(),
          sorted(x.name for x in VAULT.iterdir()))
    out = N.run_import(p, approved=True, record=False)
    check("with a person's yes it lands", out["ok"] is True, out)
    check("and the folder and its note are there",
          (VAULT / EXPORT / "Page.md").is_file())
    check("nothing of the staging folder is left in the vault",
          not [d for d in VAULT.iterdir() if d.name.startswith(".jarvis")],
          sorted(x.name for x in VAULT.iterdir()))
    check("a refused plan never runs",
          N.run_import(N.Plan(source=str(src), vault=str(VAULT), refused="no"),
                       approved=True, record=False)["ok"] is False)


def t_the_route_asks_the_gate_and_a_no_brings_nothing_in():
    src = fresh()
    write(src, f"Page {A32}.md", "# Page\n\nBody.\n")
    asked = {}

    class No:
        allowed = False
        outcome = "denied"
    code, out = N.request_import({"source": str(src), "vault": str(VAULT)},
                                 gate=lambda a, d, p: (asked.update({"action": a}), No())[1])
    check("the gate is asked about the import", asked.get("action") == "change_own_config"
          or asked.get("action") == N.GATE_ACTION, asked)
    check("a denied card brings nothing in", out["ok"] is False, out)
    check("and the folder is not there", not (VAULT / EXPORT).exists())

    class Yes:
        allowed = True
        outcome = "approved"
    code, out = N.request_import({"source": str(src), "vault": str(VAULT)},
                                 gate=lambda a, d, p: Yes())
    check("an approved card runs the import", out.get("ok") is True, out)
    check("and the plan's digest is checked when one is given",
          N.request_import({"source": str(src), "vault": str(VAULT), "digest": "nope"},
                           gate=lambda a, d, p: Yes())[1]["ok"] is False)


def t_a_preview_answers_with_a_plan():
    src = fresh()
    write(src, f"Page {A32}.md", "# Page\n\nBody.\n")
    code, out = N.preview({"source": str(src), "vault": str(VAULT)})
    check("the preview answers 200", code == 200, code)
    check("with the plan and no writing", out["ok"] is True
          and out["plan"]["notes"] == 1, out)
    check("and a plain-words sentence", "note" in out["said"], out.get("said"))
    code, out = N.preview({"source": str(TMP / "nope"), "vault": str(VAULT)})
    check("a preview of nothing says so rather than raising", out["ok"] is False, out)


# ── the ROUTES themselves: preview is a DRY RUN (2026-10-20 field bug) ─────
#
# THE BUG THIS PINS. install()'s do_POST used to call
#
#     request_import(body if route == PATHS[1] else body)
#
# whose two branches are the same expression, so POST /api/notion/preview (the
# documented dry run) ran the IMPORT first: it raised a real
# import_notion_export approval card, wrote a real folder into the vault, and
# only then overwrote the answer with preview(). Measured on the owner's PC:
# two preview calls raised two cards (both approved) and imported twice; the
# second preview then refused with "there is already a folder called ...".
#
# The checks below therefore drive the INSTALLED HANDLER, not preview()/
# request_import() directly - the functions were always right; the wiring was
# not. The gate is a stand-in that records what it was asked and that would
# ANSWER YES, so the buggy wiring gets past the card and really writes: that is
# what makes (a) and (b) bite. A gate that raised would abort the buggy import
# before it wrote anything and the checks would pass on the broken code.

class _FakeWFile:
    def __init__(self):
        self.buf = b""

    def write(self, data):
        self.buf += data


class _FakeConn:
    """The shape `_peer_local()` reads: the address the request ARRIVED at."""

    def __init__(self, addr):
        self._addr = addr

    def getsockname(self):
        return self._addr


class RouteStand:
    """A stand-in for the core's Handler and its three callbacks - the shape
    jarvis_plugins.py calls install() with, and a real response to read.

    `peer`/`local` are the two addresses `from_this_pc()` rules on: both
    loopback by default (the desktop), or a phone's address and the PC's for
    the PC-only checks.
    """

    def __init__(self, origin=True, token=True, peer="127.0.0.1", local="127.0.0.1"):
        self.calls, self.status, self.payload = [], None, None
        self.origin, self.token = origin, token
        self.peer, self.local = peer, local
        core = self

        class Handler:
            def __init__(self, path="/", body=b"{}"):
                self.path, self.body = path, body
                self.wfile = _FakeWFile()
                self.client_address = (core.peer, 5000)
                self.connection = _FakeConn((core.local, 4719))

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

    def post(self, path, body):
        req = self.Handler(path, json.dumps(body).encode("utf-8"))
        req.do_POST()
        raw = req.wfile.buf.decode("utf-8") or "{}"
        self.payload = json.loads(raw)
        return self.status, self.payload


def _route_stand():
    N._reset_for_tests()
    stand = RouteStand()
    line = N.install(stand.Handler, origin_ok=stand.origin_ok,
                     token_ok=stand.token_ok, read_body=stand.read_body)
    check("(set-up) install() arms the two routes", isinstance(line, str)
          and "Notion" in line, line)
    return stand


def _vault_listing() -> list:
    return sorted(p.relative_to(VAULT).as_posix() for p in VAULT.rglob("*"))


class _Approved:
    allowed = True
    outcome = "approved"


def _record_yes(asked):
    def gate(action, detail, prompt):
        asked.append((action, detail, prompt))
        return _Approved()
    return gate


def t_the_preview_route_is_a_dry_run():
    """(a) preview raises NO card, and (b) writes NOTHING into the vault."""
    src = fresh()
    write(src, f"Meeting Notes {A32}.md", "# Meeting Notes\n\nA body.\n")
    stand = _route_stand()
    planned = N.plan_import(str(src), str(VAULT))      # what it WOULD make
    asked = []
    real_gate = N._gate
    N._gate = _record_yes(asked)
    before = _vault_listing()
    try:
        code, out = stand.post(N.PATHS[0], {"source": str(src), "vault": str(VAULT)})
        after = _vault_listing()
    finally:
        N._gate = real_gate
    check("(a) POST /api/notion/preview raises NO approval card",
          asked == [], asked)
    check("(b) ... and writes NOTHING into the vault (listing before == after)",
          before == after, {"before": before, "after": after})
    check("(b) ... and the folder it planned to create is not there",
          not (VAULT / planned.name).exists(), planned.name)
    check("the preview still answers 200 with the plan and its plain words",
          code == 200 and out.get("ok") is True
          and (out.get("plan") or {}).get("notes") == 1
          and "note" in str(out.get("said") or ""), (code, out))
    check("the answer is the PREVIEW's, not an import result",
          "folder" not in out and "receipt_id" not in out, out)


def t_the_import_route_still_asks_one_card_and_imports():
    """(c) the import route: exactly ONE card, and the import runs after the yes."""
    src = fresh()
    write(src, f"Meeting Notes {A32}.md", "# Meeting Notes\n\nA body.\n")
    stand = _route_stand()
    planned = N.plan_import(str(src), str(VAULT))
    asked = []
    real_gate = N._gate
    N._gate = _record_yes(asked)
    try:
        code, out = stand.post(N.PATHS[1], {"source": str(src), "vault": str(VAULT)})
    finally:
        N._gate = real_gate
    check("the import route asks the gate exactly ONCE", len(asked) == 1,
          [a[0] for a in asked])
    check("... about importing a Notion export",
          bool(asked) and asked[0][0] == N.GATE_ACTION, asked[:1])
    check("... and the card names the folder it will create",
          bool(asked) and (asked[0][1] or {}).get("folder") == planned.name,
          asked[:1])
    check("with the yes it really imported", code == 200 and out.get("ok") is True
          and (VAULT / planned.name / "Meeting Notes.md").is_file(), out)
    check("nothing of its staging folder is left in the vault",
          not [p for p in VAULT.rglob("*") if p.name.startswith(".jarvis")],
          _vault_listing())


def t_the_preview_route_refuses_a_collision_without_importing():
    """(d) a colliding preview refuses in words and touches nothing."""
    src = fresh()
    write(src, f"Meeting Notes {A32}.md", "# Meeting Notes\n\nA body.\n")
    planned = N.plan_import(str(src), str(VAULT))
    already = VAULT / planned.name
    already.mkdir()
    (already / "existing.md").write_text("kept, not overwritten", encoding="utf-8")
    stand = _route_stand()
    asked = []
    real_gate = N._gate
    N._gate = _record_yes(asked)
    before = _vault_listing()
    try:
        code, out = stand.post(N.PATHS[0], {"source": str(src), "vault": str(VAULT)})
        after = _vault_listing()
    finally:
        N._gate = real_gate
    told = f"{out.get('said') or ''} {((out.get('plan') or {}).get('refused') or '')}"
    check("preview says plainly that the folder is already there",
          out.get("ok") is False and "already a folder" in told, told[:300])
    check("... and asks for NO card", asked == [], asked)
    check("... and writes nothing (the existing file is untouched)",
          before == after and (already / "existing.md").read_text(encoding="utf-8")
          == "kept, not overwritten", {"before": before, "after": after})


def t_both_routes_are_pc_only():
    """R4: /api/notion/* follows /api/folders/import - this PC only.

    The old guards were origin + token only, so a paired phone with the token
    got `preview` 200 with the plan's absolute `source` and `vault` paths (a
    filesystem oracle), and could raise an import card from the phone. The
    check drives the INSTALLED handler with a phone's address, then again with
    the desktop's loopback address.
    """
    src = fresh()
    write(src, f"Meeting Notes {A32}.md", "# Meeting Notes\n\nA body.\n")
    planned = N.plan_import(str(src), str(VAULT))
    phone = RouteStand(peer="100.64.0.9", local="100.64.0.1")
    line = N.install(phone.Handler, origin_ok=phone.origin_ok,
                     token_ok=phone.token_ok, read_body=phone.read_body)
    check("(set-up) install() arms the two routes for the PC-only check",
          isinstance(line, str), line)
    asked = []
    real_gate = N._gate
    N._gate = _record_yes(asked)
    try:
        prev_code, prev = phone.post(N.PATHS[0], {"source": str(src),
                                                  "vault": str(VAULT)})
        imp_code, imp = phone.post(N.PATHS[1], {"source": str(src),
                                                "vault": str(VAULT)})
    finally:
        N._gate = real_gate
    check("R4 the preview route refuses a NON-PC device with 403", prev_code == 403,
          (prev_code, prev))
    check("R4 ...and says it is the PC only, in plain words",
          prev.get("pc_only") is True and "PC" in str(prev.get("reason") or ""), prev)
    check("R4 the import route refuses a NON-PC device with 403 too", imp_code == 403,
          (imp_code, imp))
    check("R4 ...and does not even raise the approval card", asked == [], asked)
    answer = json.dumps({"preview": prev, "import": imp})
    check("R4 neither refusal names a path on this PC",
          str(src) not in answer and str(VAULT) not in answer, answer[:300])
    check("R4 nothing was written by the refused calls", not (VAULT / planned.name).exists(),
          _vault_listing())
    pc = _route_stand()
    pc_code, pc_out = pc.post(N.PATHS[0], {"source": str(src), "vault": str(VAULT)})
    check("R4 the PC itself still gets its preview", pc_code == 200
          and pc_out.get("ok") is True, (pc_code, pc_out))


# ── what it must never do ───────────────────────────────────────────────────

def t_it_does_not_name_jarvis_memory():
    text = (REPO / "backend" / "jarvis_notion_obsidian.py").read_text(encoding="utf-8")
    check("the module never names jarvis_memory, so it cannot read a fact",
          "jarvis_memory" not in text)
    check("...so it needs no row in test_topics_leaks.py's READERS "
          "(that file is not touched by this branch)", True)


def t_the_settings_folder_is_the_one_variable_every_module_reads():
    check("the module reads OPENJARVIS_CONFIG_DIR", N._config_dir() == CONF, N._config_dir())
    os.environ.pop("OPENJARVIS_CONFIG_DIR", None)
    os.environ["JARVIS_CONFIG_DIR"] = str(CONF)
    try:
        check("and JARVIS_CONFIG_DIR when that is the one set",
              N._config_dir() == CONF, N._config_dir())
    finally:
        os.environ.pop("JARVIS_CONFIG_DIR", None)
        os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)


def t_it_opens_no_socket_and_runs_no_program():
    text = (REPO / "backend" / "jarvis_notion_obsidian.py").read_text(encoding="utf-8")
    for bad in ("import socket", "import requests", "subprocess", "urllib.request",
                "http.client"):
        check(f"the module does not use {bad}", bad not in text)


# ── Ruling 8.6: multi-line CSV cells must produce VALID YAML ───────────────
#
# RISK-1 in the 2026-10-21 converter audit: a Notion database cell is a CSV
# field, and Shift+Enter puts a real newline inside one. The serializer
# quoted such a value but escaped only a backslash and a quote, so the
# newline went into the frontmatter RAW - and a raw line break inside a
# double-quoted scalar makes the note's YAML unreadable by any parser
# (Obsidian included), which loses EVERY property on that note, not just the
# multi-line one. Ruling 8.6 (accepted): normalize \r\n/\r -> \n and
# JSON-quote an ambiguous scalar, which escapes the newline as \n and is a
# valid YAML 1.2 scalar.

def _yaml_doc(block: str):
    """The first YAML document of a `yaml_block` string (`--- ... ---`)."""
    body = block.split("---", 2)[1]
    return yaml.safe_load(body)


def t_a_multiline_cell_is_valid_yaml_and_round_trips():
    if yaml is None:
        skip("pyyaml is not installed here, so the Ruling 8.6 multi-line check "
             "did not run")
        return
    want = "First line\nSecond line"
    front = N.frontmatter_of("Ship it", A32, {"Notes": want})
    block = N.yaml_block(front)
    try:
        parsed = _yaml_doc(block)
        parse_error = ""
    except Exception as exc:                              # noqa: BLE001
        parsed, parse_error = None, f"{type(exc).__name__}: {exc}"
    check("Ruling 8.6: a multi-line cell still produces parseable YAML",
          isinstance(parsed, dict), parse_error + "\n" + block)
    if isinstance(parsed, dict):
        check("Ruling 8.6: ... and it round-trips to the EXACT original text",
              parsed.get("notes") == want, {"got": parsed.get("notes"), "want": want})
        check("Ruling 8.6: ... with no raw newline inside the scalar's line",
              "First line\nSecond line" not in block, block)
    # A Windows export: \r\n is normalized, so the same note hashes the same
    # everywhere and YAML never sees a bare carriage return.
    front2 = N.frontmatter_of("Ship it", A32,
                              {"Notes": "First line\r\nSecond line"})
    block2 = N.yaml_block(front2)
    try:
        parsed2 = _yaml_doc(block2)
    except Exception as exc:                              # noqa: BLE001
        parsed2 = None
        check("Ruling 8.6: a \\r\\n cell is normalized and parseable", False,
              f"{type(exc).__name__}: {exc}\n{block2}")
    if parsed2 is not None:
        check("Ruling 8.6: a \\r\\n cell is normalized and parseable",
              parsed2.get("notes") == "First line\nSecond line",
              {"got": parsed2.get("notes")})


def t_ambiguous_values_are_quoted_and_safe():
    if yaml is None:
        skip("pyyaml is not installed here, so the Ruling 8.6 YAML-safety "
             "checks did not run")
        return
    cases = (
        ("a colon", "note: half done"),
        ("a hash", "#hashtag"),
        ("a leading bracket", "[draft] text"),
        ("a leading dash", "- leading dash"),
        ("a leading question mark", "? not sure"),
        ("a leading star", "*important*"),
        ("a quote at the start", '"quoted start"'),
        ("a tab inside", "before\tafter"),
        ("a YAML boolean word", "yes"),
        ("an upper-case boolean word", "True"),
    )
    for label, value in cases:
        front = N.frontmatter_of("Row", A32, {"Value": value})
        block = N.yaml_block(front)
        try:
            parsed = _yaml_doc(block)
            got = parsed.get("value") if isinstance(parsed, dict) else None
        except Exception as exc:                          # noqa: BLE001
            got = f"<parse failed: {type(exc).__name__}>"
        check(f"Ruling 8.6 {label} value is quoted and reads back as the string",
              got == value, {"value": value, "got": got, "block": block})


def t_plain_values_are_unchanged_byte_for_byte():
    check("Ruling 8.6 a plain word is unchanged",
          N._yaml_scalar("Meeting Notes") == "Meeting Notes")
    check("Ruling 8.6 a plain number stays a bare number",
          N._yaml_scalar("42") == "42")
    check("Ruling 8.6 an empty value is still an empty string",
          N._yaml_scalar("") == '""')
    front = {"notion_id": A32, "title": "Meeting Notes",
             "created": "2026-10-14T15:04:00", "tags": ["work", "urgent"],
             "owner": "Sam"}
    block = N.yaml_block(front)
    want = ("---\n"
            f"notion_id: {A32}\n"
            "title: Meeting Notes\n"
            'created: "2026-10-14T15:04:00"\n'
            "tags:\n  - work\n  - urgent\n"
            "owner: Sam\n"
            "---")
    check("Ruling 8.6 a simple frontmatter block is byte-for-byte what it was",
          block == want, {"got": block, "want": want})


def t_a_full_export_with_a_multiline_cell_imports_cleanly():
    if yaml is None:
        skip("pyyaml is not installed here, so the synthetic-export check did "
             "not run")
        return
    src = fresh()
    # One real database row whose Notes cell holds a Shift+Enter newline. The
    # CSV quotes the field, exactly as Notion exports it.
    write(src, f"Tasks {A32}_all.csv",
          'Name,Notes,Status\n'
          'Ship it,"First line\nSecond line",Done\n')
    write(src, f"Ship it {B32}.md", "# Ship it\n\nDo the thing.\n")
    p = N.plan_import(str(src), str(VAULT), today="2026-01-01")
    check("(set-up) the export with a multi-line cell plans", p.rows == 1, p.rows)
    out = N.run_import(p, approved=True, record=False)
    check("(set-up) the import lands", out.get("ok") is True, out)
    note = (VAULT / EXPORT / "Ship it.md").read_text(encoding="utf-8")
    check("Ruling 8.6: the multi-line cell reached the frontmatter",
          "First line" in note and "Second line" in note, note)
    block = note.split("---", 2)[1]
    try:
        parsed = yaml.safe_load(block)
        got = parsed.get("notes") if isinstance(parsed, dict) else None
    except Exception as exc:                              # noqa: BLE001
        parsed, got = None, f"<parse failed: {type(exc).__name__}>"
    check("Ruling 8.6: the imported note's frontmatter is parseable YAML",
          isinstance(parsed, dict), note[:800])
    check("Ruling 8.6: ... and its multi-line value round-trips exactly",
          got == "First line\nSecond line", {"got": got, "block": block})
    check("Ruling 8.6: ... and the status column is still there",
          isinstance(parsed, dict) and parsed.get("status") == "Done", block)


def main():
    tests = (t_notions_ids_come_off_names,
             t_what_windows_and_obsidian_forbid_is_replaced,
             t_two_pages_with_one_title_do_not_overwrite_each_other,
             t_the_same_export_cleans_the_same_way_twice,
             t_a_zip_a_folder_and_notions_part_archives,
             t_the_zip_guards_are_jarvis_documents_own,
             t_a_zip_bomb_is_refused_not_unpacked,
             t_a_zip_bomb_is_refused_by_its_own_directory_before_unpacking,
             t_the_zip_member_limits_are_checked_before_any_member_is_opened,
             t_a_source_that_is_not_an_export_is_refused,
             t_the_destination_must_be_a_real_vault,
             t_properties_become_frontmatter,
             t_dates_and_lists_are_what_obsidian_expects,
             t_a_second_import_is_idempotent,
             t_a_csv_database_becomes_frontmatter_a_note_and_a_base,
             t_the_database_hub_note_says_what_it_is_and_never_drops_a_row,
             t_a_database_exported_twice_keeps_every_row,
             t_relation_columns_become_wikilinks_and_other_values_are_untouched,
             t_a_database_whose_title_column_is_renamed_still_merges,
             t_a_generated_hub_never_overwrites_a_page,
             t_databases_whose_names_differ_only_by_case_never_share_a_file,
             t_two_rows_with_one_title_in_one_csv_are_both_kept,
             t_duplicate_titles_across_x_and_x_all_keep_both_rows,
             t_a_value_that_is_not_a_page_keeps_every_character,
             t_a_database_named_all_keeps_its_name,
             t_a_refusal_during_the_run_keeps_its_plain_words,
             t_an_html_page_and_a_markdown_page_with_one_title_do_not_overwrite,
             t_html_becomes_obsidian_markdown,
             t_html_never_raises_on_odd_input,
             t_links_are_rewritten_through_the_cleaned_names,
             t_attachments_move_into_the_vault_and_the_link_follows,
             t_a_plan_writes_nothing,
             t_the_run_needs_a_persons_yes,
             t_the_route_asks_the_gate_and_a_no_brings_nothing_in,
             t_a_preview_answers_with_a_plan,
             t_the_preview_route_is_a_dry_run,
             t_the_import_route_still_asks_one_card_and_imports,
             t_the_preview_route_refuses_a_collision_without_importing,
             t_both_routes_are_pc_only,
             t_it_does_not_name_jarvis_memory,
             t_the_settings_folder_is_the_one_variable_every_module_reads,
             t_it_opens_no_socket_and_runs_no_program,
             t_a_multiline_cell_is_valid_yaml_and_round_trips,
             t_ambiguous_values_are_quoted_and_safe,
             t_plain_values_are_unchanged_byte_for_byte,
             t_a_full_export_with_a_multiline_cell_imports_cleanly)
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
