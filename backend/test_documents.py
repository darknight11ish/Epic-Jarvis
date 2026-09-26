"""test_documents.py - "Folders Jarvis may look in" (jarvis_documents.py,
documents.patch, the my_files tool in jarvis_agent.py; the owner's decisions
of 2026-09-26: asking about PDFs and Word files, and the Notion import).

    python3 backend/test_documents.py

Runs anywhere; no model, no network. MarkItDown is used only by the one
suite that converts real files, and that one says so and skips when it is
not installed. What it proves:

1. The list is empty by default; a damaged file means no folders.
2. Adding: only from this PC, refused for a drive's top, the whole user
   folder, Windows' folders and protected places, and otherwise ONE card
   (change_own_config, tier "ask" only) that names the folder - only a
   person's "approved" adds it. Removing is at once, and withdraws a
   waiting card for the same folder.
3. Every path the tool touches is inside a listed folder once links are
   followed, never in a hidden folder, never in a protected place
   (file_read's own list).
4. find, search and read: Notion's long ids hidden, snippets short, parts at
   most PART_TOKENS, split at headings with nothing lost, the part the words
   point to, a scanned PDF said plainly, the converter's text kept in memory.
5. The converter: a separate program with no secret in its environment, the
   document parts of MarkItDown only; requirements.txt never names [all],
   audio or YouTube.
6. The Notion import: a new folder, only notes, tables, documents and
   pictures; no "..", no absolute path, no link, no program; the caps count
   what is really written; a refused import leaves nothing behind; this PC
   only.
7. The chat loop: my_files is offered only while a folder is listed, is
   decided under file_read's action, its result is outside text (a note
   afterwards asks), and one answer reads at most FILES_PARTS_PER_TURN parts.
8. The routes and the patch: install() answers the four routes after the
   server's own checks and passes everything else on; documents.patch
   applies after the rest of the stack and reverses; the module is shipped.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
import types
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_documents.py", "jarvis_agent.py", "jarvis_child_env.py",
                "jarvis_owner_check.py")
sys.path.append(str(HERE / "rebuilt"))
import _stack  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_documents as D  # noqa: E402

FAILED, PASSED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-documents-"))
CONF = TMP / "config"
CONF.mkdir()
D._config_dir = lambda: CONF


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond
                                                        else ""))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier
        self.reason = outcome


def run_now(fn):
    fn()


def fresh():
    D._reset_for_tests()
    try:
        D.settings_path().unlink()
    except FileNotFoundError:
        pass


def folder(name: str) -> Path:
    p = TMP / "home" / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def listed(*paths) -> None:
    D._save([{"path": os.path.realpath(str(p)), "added": 1.0} for p in paths])


# ============================================================ 1. the list

def t_empty_by_default_and_damaged_means_none():
    fresh()
    v = D.view(here=False)
    check("no file: no folders", v["folders"] == [] and v["why"] == "")
    check("the words: title, empty line, the phone's line", v["title"] == D.TITLE
          and v["empty"] == D.EMPTY and v["phone_add"] == D.PHONE_ADD)
    check("the phone may not add", v["can_add"] is False and v["notion"]["can_import"] is False)
    D.settings_path().write_text("{not json", encoding="utf-8")
    v = D.view(here=True)
    check("a damaged file: no folders, and why", v["folders"] == [] and v["why"] == D._DAMAGED)
    D.settings_path().write_text(json.dumps({"folders": [{"path": 3}]}), encoding="utf-8")
    check("a wrong shape: no folders", D.folders() == [])
    fresh()


# ============================================================ 2. adding and removing

def t_adding_is_this_pc_only_and_one_card():
    fresh()
    docs = folder("Documents")
    code, out = D.request_add({"path": str(docs)}, here=False, spawn=run_now)
    check("another device: 403, pc_only", code == 403 and out.get("pc_only") is True, out)
    check("  and nothing was added", D.folders() == [])
    seen = []

    def gate(action, detail, prompt):
        seen.append((action, detail, prompt))
        return Verdict(True, "approved")
    code, out = D.request_add({"path": str(docs)}, here=True, gate=gate,
                              tier_of=lambda a: "ask", spawn=run_now)
    check("this PC: 202 and a card", code == 202 and len(seen) == 1, (code, out))
    check("the card is change_own_config", seen and seen[0][0] == "change_own_config")
    check("the card names the folder in full, and says removing is instant",
          seen and os.path.realpath(str(docs)) in seen[0][2]
          and "Removing the folder from the list is instant" in seen[0][2]
          and "outside text" in seen[0][2])
    check("approved: it is on the list", D.folders() == [os.path.realpath(str(docs))])
    check("the last card says added", D.view()["last"]["outcome"] == "added")
    code, out = D.request_add({"path": str(docs)}, here=True, gate=gate,
                              tier_of=lambda a: "ask", spawn=run_now)
    check("again: already on the list, no second card", code == 200
          and out["changed"] is False and len(seen) == 1)
    sub = folder("Documents/Taxes")
    code, out = D.request_add({"path": str(sub)}, here=True, gate=gate,
                              tier_of=lambda a: "ask", spawn=run_now)
    check("a folder inside a listed one: already covered", code == 200
          and "already covered" in out["message"] and len(seen) == 1, out)
    fresh()


def t_only_a_person_saying_yes_adds():
    for outcome, allowed, tier, want in (("denied", False, "ask", "denied"),
                                         ("timed_out", False, "ask", "timed_out"),
                                         (None, True, "auto", "refused"),
                                         ("approved", True, "auto", "refused")):
        fresh()
        docs = folder("Docs2")
        code, _ = D.request_add({"path": str(docs)}, here=True,
                                gate=lambda *a, o=outcome, al=allowed, t=tier: Verdict(al, o, t),
                                tier_of=lambda a: "ask", spawn=run_now)
        check(f"{outcome} at tier {tier}: nothing added ({want})",
              code == 202 and D.folders() == [] and D.view()["last"]["outcome"] == want,
              D.view()["last"])
    fresh()
    code, out = D.request_add({"path": str(folder("Docs3"))}, here=True,
                              tier_of=lambda a: "auto", spawn=run_now)
    check("change_own_config not 'ask' in the settings: refused, no card", code == 503, out)
    fresh()


def t_removing_is_at_once_and_withdraws_a_waiting_card():
    fresh()
    a, b = folder("A"), folder("B")
    listed(a, b)
    code, out = D.request_remove({"path": os.path.realpath(str(a))})
    check("removed at once", code == 200 and out["changed"] is True
          and D.folders() == [os.path.realpath(str(b))], out)
    held = []
    code, _ = D.request_add({"path": str(a)}, here=True, gate=lambda *x: Verdict(True, "approved"),
                            tier_of=lambda x: "ask", spawn=lambda fn: held.append(fn))
    check("a card waits", code == 202 and D.view()["waiting"] is not None)
    D.request_remove({"path": str(a)})
    held[0]()
    check("removed before the yes: not added, 'withdrawn'",
          os.path.realpath(str(a)) not in D.folders()
          and D.view()["last"]["outcome"] == "withdrawn", D.view()["last"])
    code, out = D.request_remove({"path": "C:\\not\\there"})
    check("not on the list: said so", code == 200 and out["changed"] is False)
    fresh()


def t_refused_folders():
    fresh()
    home = os.path.realpath(os.path.expanduser("~"))
    for path, why in (("relative/path", "full path"), ("", "which folder"),
                      (str(TMP / "nope"), "no folder"), ("/", "top of a drive"),
                      (home, "whole user folder"),
                      (str(folder("AppData/Roaming/x")), "belongs to Windows"),
                      (str(folder("Program Files/App")), "belongs to Windows"),
                      (str(folder("me/.ssh")), "never looks there"),
                      (str(folder("me/.openjarvis/data")), "never looks there"),
                      ("\\\\server\\share", "full path")):
        code, out = D.request_add({"path": path}, here=True, spawn=run_now,
                                  gate=lambda *a: Verdict(True, "approved"),
                                  tier_of=lambda a: "ask")
        check(f"refused: {path[-40:]!r} ({why})",
              code == 400 and why in out.get("error", "") and D.folders() == [], out)
    fresh()


# ============================================================ 3. where a path may be

def t_only_inside_a_listed_folder():
    fresh()
    root = folder("Lib")
    (root / "a.md").write_text("hello", encoding="utf-8")
    (root / ".hidden").mkdir(exist_ok=True)
    (root / ".hidden" / "b.md").write_text("secret", encoding="utf-8")
    (root / "id_rsa").write_text("KEY", encoding="utf-8")
    (root / ".env").write_text("X=1", encoding="utf-8")
    (root / "c.pem").write_text("KEY", encoding="utf-8")
    outside = folder("Elsewhere")
    (outside / "o.md").write_text("out", encoding="utf-8")
    roots = [os.path.realpath(str(root))]
    check("a file inside: allowed", D.allowed_path(str(root / "a.md"), roots) is not None)
    check("outside: refused", D.allowed_path(str(outside / "o.md"), roots) is None)
    check("'..' out of it: refused", D.allowed_path(str(root / ".." / "Elsewhere" / "o.md"),
                                                     roots) is None)
    check("a hidden folder: refused", D.allowed_path(str(root / ".hidden" / "b.md"), roots)
          is None)
    for n in ("id_rsa", ".env", "c.pem"):
        check(f"{n}: refused by file_read's own list",
              D.allowed_path(str(root / n), roots) is None)
    try:
        os.symlink(str(outside), str(root / "link"))
        check("a link pointing out of it: refused",
              D.allowed_path(str(root / "link" / "o.md"), roots) is None)
    except (OSError, NotImplementedError):
        check("(links cannot be made here - skipped)", True)
    check("no list: refused", D.allowed_path(str(root / "a.md"), []) is None)
    real = D.protected
    D.protected = lambda p: True
    try:
        check("without file_read's list (jarvis_agent.py missing): refused",
              D.allowed_path(str(root / "a.md"), roots) is None)
    finally:
        D.protected = real


# ============================================================ 4. find, search, read

NOTION = "Trip plan 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d"


def t_find_and_search():
    fresh()
    root = folder("Find")
    (root / f"{NOTION}.md").write_text("# Trip\nWe fly to Lisbon on Friday.", encoding="utf-8")
    (root / "Invoice March.pdf").write_bytes(b"%PDF-1.4")
    (root / "notes.txt").write_text("The boiler was serviced in August.", encoding="utf-8")
    (root / "table.csv").write_text("item,cost\nboiler,120\n", encoding="utf-8")
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "invoice.md").write_text("hidden invoice", encoding="utf-8")
    (root / "invoice.key").write_text("x", encoding="utf-8")
    roots = [os.path.realpath(str(root))]
    got = D.find("invoice", roots=roots)
    names = [h["name"] for h in got["found"]]
    check("find: the invoice by name", names == ["Invoice March.pdf"], got)
    check("  not in a hidden folder, not a key file", "invoice.md" not in names
          and "invoice.key" not in names)
    got = D.find("trip plan", roots=roots)
    check("find: Notion's long id is not shown", [h["name"] for h in got["found"]]
          == ["Trip plan.md"], got)
    check("  the path is the real one", got["found"][0]["path"].endswith(f"{NOTION}.md"))
    got = D.search("boiler", roots=roots)
    check("search: inside text and CSV files", sorted(r["name"] for r in got["results"])
          == ["notes.txt", "table.csv"], got)
    check("  snippets are short", all(len(r["snippet"]) <= D.SNIPPET_CHARS + 3
                                      for r in got["results"]))
    check("  says PDFs are not searched inside", "not searched inside" in got["note"])
    got = D.search("lisbon", roots=roots)
    check("search: a Notion page, its title without the id",
          [r["name"] for r in got["results"]] == ["Trip plan.md"], got)
    check("no words: said so", D.find("  ", roots=roots)["ok"] is False)
    check("the tool with no folders says where to add one",
          "Settings, Folders Jarvis may look in" in D.run_tool({"action": "find",
                                                                "words": "x"}, roots=[])["error"])
    big = [0]
    for i in range(30):
        (root / f"many invoice {i:02}.txt").write_text("x", encoding="utf-8")
        big[0] += 1
    got = D.find("invoice", roots=roots)
    check(f"find: at most {D.FIND_MAX} names", len(got["found"]) == D.FIND_MAX
          and got["matches"] > D.FIND_MAX)
    t = [0.0]

    def clock():
        t[0] += 1.0
        return t[0]
    got = D.find("invoice", roots=roots, clock=clock)
    check("a walk that runs too long stops and says so", "stopped_early" in got, got)


def t_split_parts_loses_nothing():
    text = "# One\n" + ("alpha " * 100) + "\n\n## Two\n" + ("beta words here. " * 900) \
        + "\n\n" + ("x" * 9000) + "\n# Three\nshort\n"
    parts = D.split_parts(text)
    check("every part within the limit", all(len(b) <= D.PART_CHARS for _, b in parts),
          [len(b) for _, b in parts])
    check("nothing lost or repeated", "".join(b for _, b in parts) == text)
    titles = [t for t, _ in parts]
    check("split at the headings, a long section marked continued",
          titles[0] == "One" and "Two" in titles and "Two (continued)" in titles
          and titles[-1] == "Three", titles)
    check("a heading-less text is still split", len(D.split_parts("word " * 5000)) > 1)


def t_read_one_part():
    fresh()
    root = folder("Read")
    body = "# Lease\nIntro.\n\n## Pets\nPets are allowed with a deposit.\n\n## Parking\n" \
        + ("Parking rules. " * 700)
    (root / "lease.md").write_text(body, encoding="utf-8")
    roots = [os.path.realpath(str(root))]
    p = str(root / "lease.md")
    got = D.read(p, roots=roots)
    check("read: part 1 of several, with the list of parts", got["ok"] and got["part"] == 1
          and got["parts"] > 2 and got["contents"][0].startswith("1. "), got.get("contents"))
    got = D.read(p, words="pets deposit", roots=roots)
    check("read: the words pick the part about pets", "Pets are allowed" in got["text"], got)
    got = D.read(p, part=got["parts"], roots=roots)
    check("read: a part by number", got["ok"] and got["part"] == got["parts"])
    got = D.read(p, part=99, roots=roots)
    check("read: a part that is not there is said", got["ok"] is False and "from 1 to" in
          got["error"])
    got = D.read(str(root / "x.exe"), roots=roots)
    check("read: never a program", got["ok"] is False)
    (root / "run.bat").write_text("echo", encoding="utf-8")
    got = D.read(str(root / "run.bat"), roots=roots)
    check("read: only the document and text kinds", got["ok"] is False and "only" in
          got["error"], got)
    calls = []

    def conv(path, ext):
        calls.append(ext)
        return {"ok": True, "text": "# Contract\nThe rent is 900 a month."}
    (root / "contract.pdf").write_bytes(b"%PDF fake")
    got = D.read(str(root / "contract.pdf"), roots=roots, convert=conv)
    check("a PDF goes through the converter", got["ok"] and "900 a month" in got["text"]
          and got["kind"] == "PDF", got)
    D.read(str(root / "contract.pdf"), roots=roots, convert=conv)
    check("  and is kept in memory: converted once for two reads", calls == [".pdf"], calls)
    (root / "scan.pdf").write_bytes(b"%PDF scan")
    got = D.read(str(root / "scan.pdf"), roots=roots,
                 convert=lambda p, e: {"ok": True, "text": "  \n"})
    check("a scanned PDF: 'no text was found', plainly", got["ok"] is False
          and "scanned" in got["error"], got)
    (root / "big.docx").write_bytes(b"x")
    got = D.read(str(root / "big.docx"), roots=roots,
                 convert=lambda p, e: {"ok": False, "missing": True,
                                       "error": D.CONVERTER_MISSING})
    check("no MarkItDown: said in plain words", got["ok"] is False
          and got["error"] == D.CONVERTER_MISSING)
    real = D.MAX_DOC_BYTES
    D.MAX_DOC_BYTES = 0
    try:
        (root / "huge.pptx").write_bytes(b"xy")
        got = D.read(str(root / "huge.pptx"), roots=roots, convert=conv)
        check("a document over the size limit is not converted", got["ok"] is False
              and calls == [".pdf"], got)
    finally:
        D.MAX_DOC_BYTES = real


# ============================================================ 5. the converter

def _minimal_pdf(text: str) -> bytes:
    content = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
            b"/Resources<</Font<</F1 5 0 R>>>>>>",
            b"<</Length " + str(len(content)).encode() + b">>stream\n" + content
            + b"\nendstream",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{x}\n%%EOF\n".encode()
    return bytes(out)


def _minimal_docx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="rels" ContentType="'
                   'application/vnd.openxmlformats-package.relationships+xml"/><Default '
                   'Extension="xml" ContentType="application/xml"/><Override PartName="/word/'
                   'document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                   'wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.'
                   'org/package/2006/relationships"><Relationship Id="rId1" Type="http://'
                   'schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument'
                   '" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml",
                   '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.'
                   'org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + text
                   + '</w:t></w:r></w:p></w:body></w:document>')


def t_the_converter_is_a_separate_program_without_secrets():
    secret_name = "JARVIS_" + "IMAP_" + "PASSWORD"
    os.environ[secret_name] = "hunter" + "2-" + "fake"
    os.environ["HUD_" + "TOKEN"] = "tok" + "en-" + "fake"
    try:
        env = D._child_env()
        check("the converter's environment has no password or token",
              secret_name not in env and ("HUD_" + "TOKEN") not in env
              and not any("fake" in v for v in env.values()), sorted(env))
    finally:
        os.environ.pop(secret_name, None)
        os.environ.pop("HUD_" + "TOKEN", None)
    code = D._CHILD
    check("only the four document converters are switched on",
          "enable_builtins=False" in code and "enable_plugins=False" in code
          and "PdfConverter" in code and "DocxConverter" in code
          and "YouTube" not in code and "Audio" not in code and "convert_uri" not in code
          and "http" not in code)
    check("the child runs isolated (-I) and with a time limit",
          "\"-I\"" in Path(D.__file__).read_text(encoding="utf-8")
          and D.CONVERT_SECONDS <= 300)
    req = (HERE / "requirements.txt").read_text(encoding="utf-8")
    line = next((l for l in req.splitlines() if l.lower().startswith("markitdown")), "")
    spec = line.split("#")[0].strip().lower()
    check("requirements.txt: MarkItDown pinned, with the document parts only",
          spec == "markitdown[pdf,docx,xlsx,pptx]==0.1.8", spec)
    check("requirements.txt never names MarkItDown's all, audio or YouTube parts",
          not any(("markitdown[" in l.split("#")[0].lower()
                   and any(x in l.split("#")[0].lower() for x in ("all", "audio", "youtube")))
                  for l in req.splitlines()))
    check("its hash is written down (a real one, 64 hex digits)",
          "de7375a50578a39bcbbf13b48c67d99033d988e0ae8ad25af46ed432dbe4cbab" in line)


def t_real_conversion_when_markitdown_is_here():
    D._READY.clear()
    if not D.converter_ready():
        check("(MarkItDown is not installed here - real conversion skipped)", True)
        return
    root = folder("Real")
    (root / "letter.pdf").write_bytes(_minimal_pdf("Pets are allowed here"))
    _minimal_docx(root / "memo.docx", "The meeting moved to Tuesday")
    roots = [os.path.realpath(str(root))]
    got = D.read(str(root / "letter.pdf"), roots=roots)
    check("a real PDF becomes text in the child program", got.get("ok")
          and "Pets are allowed" in got.get("text", ""), got)
    got = D.read(str(root / "memo.docx"), roots=roots)
    check("a real Word file becomes text", got.get("ok")
          and "Tuesday" in got.get("text", ""), got)
    (root / "broken.docx").write_bytes(b"not a zip at all")
    got = D.read(str(root / "broken.docx"), roots=roots)
    check("a broken file: an error, not a crash", got.get("ok") is False, got)


# ============================================================ 6. the Notion import

def _notion_zip(path: Path, extra=None) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"Export/{NOTION}.md", "# Trip\nLisbon")
        z.writestr(f"Export/{NOTION}/Packing 0123456789abcdef0123456789abcdef.md", "socks")
        z.writestr("Export/Budget 0123456789abcdef0123456789abcdef.csv", "a,b\n1,2\n")
        z.writestr("Export/pic.png", b"\x89PNG")
        z.writestr("Export/evil.exe", b"MZ")
        z.writestr("Export/run.ps1", "Remove-Item")
        z.writestr("Export/page.html", "<script>")
        z.writestr("../escape.md", "out")
        z.writestr("/abs.md", "out")
        z.writestr("C:/drive.md", "out")
        z.writestr("Export/con.md", "reserved")
        z.writestr("Export/a:b.md", "colon")
        link = zipfile.ZipInfo("Export/link.md")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(link, "/etc/passwd")
        inner = TMP / "inner.zip"
        with zipfile.ZipFile(inner, "w") as zi:
            zi.writestr("Part2/Notes 0123456789abcdef0123456789abcdef.md", "part two")
            zi.writestr("Part2/deeper.zip", b"PK")
        z.write(inner, "Export-Part-1.zip")
        for name, data in (extra or {}).items():
            z.writestr(name, data)


def t_the_notion_import():
    fresh()
    dest = folder("Notes")
    zp = TMP / "export.zip"
    _notion_zip(zp)
    roots = [os.path.realpath(str(dest))]
    code, out = D.request_import({"zip": str(zp), "into": roots[0]}, here=False)
    check("another device: refused", code == 403 and out.get("pc_only") is True)
    try:
        D.import_notion(str(zp), str(folder("NotListed")), roots=roots)
        check("into a folder not on the list: refused", False)
    except D.ImportRefused as exc:
        check("into a folder not on the list: refused", "on the list" in str(exc))
    out = D.import_notion(str(zp), roots[0], roots=roots, today="2026-09-26")
    new = Path(out["folder"])
    check("a NEW folder, named with the date", new.name == "Notion export 2026-09-26"
          and new.parent == Path(roots[0]), out)
    files = sorted(str(p.relative_to(new)).replace(os.sep, "/") for p in new.rglob("*")
                   if p.is_file())
    check("notes, tables, pictures and the inner part are brought in",
          f"Export/{NOTION}.md" in files and "Export/pic.png" in files
          and any(f.startswith("Part2/Notes") for f in files)
          and any(f.startswith("Export/Budget") for f in files), files)
    check("no program, script or web page", not any(f.endswith((".exe", ".ps1", ".html", ".zip"))
                                                     for f in files), files)
    check("nothing outside the new folder", not (dest / "escape.md").exists()
          and not (TMP / "escape.md").exists() and not Path("/abs.md").exists())
    check("Windows' reserved name and characters are made safe",
          "Export/_con.md" in files and "Export/a_b.md" in files, files)
    check("a link inside the zip is not written", "Export/link.md" not in files)
    check("no hidden working folder is left", not any(p.name.startswith(".jarvis-import")
                                                      for p in dest.iterdir()))
    check("the words say how many were left out", out["skipped"] >= 6
          and "left out" in out["said"], out)
    out2 = D.import_notion(str(zp), roots[0], roots=roots, today="2026-09-26")
    check("a second import never writes over the first", out2["folder"].endswith("(2)"))
    check("find reads the imported pages, without Notion's ids",
          [h["name"] for h in D.find("packing", roots=roots)["found"]][:1] == ["Packing.md"])
    real = D.IMPORT_MAX_FILES
    D.IMPORT_MAX_FILES = 2
    try:
        D.import_notion(str(zp), roots[0], roots=roots, today="2026-09-27")
        check("too many files: refused", False)
    except D.ImportRefused as exc:
        check("too many files: refused, and nothing is left behind",
              "more than" in str(exc) and not (dest / "Notion export 2026-09-27").exists()
              and not any(p.name.startswith(".jarvis-import") for p in dest.iterdir()))
    finally:
        D.IMPORT_MAX_FILES = real
    bomb = TMP / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("big.md", "a" * (3 * 1024 * 1024))
    real = D.IMPORT_MAX_BYTES
    D.IMPORT_MAX_BYTES = 1024 * 1024
    try:
        D.import_notion(str(bomb), roots[0], roots=roots, today="2026-09-28")
        check("more than the cap unpacked: refused", False)
    except D.ImportRefused as exc:
        check("the cap counts what is really written (a small zip that unpacks big)",
              "unpacks to more than" in str(exc)
              and not (dest / "Notion export 2026-09-28").exists())
    finally:
        D.IMPORT_MAX_BYTES = real
    (TMP / "notzip.zip").write_bytes(b"hello")
    try:
        D.import_notion(str(TMP / "notzip.zip"), roots[0], roots=roots)
        check("not a zip: refused", False)
    except D.ImportRefused:
        check("not a zip: refused", True)
    for bad in ("../x.md", "/x.md", "C:\\x.md", "a/../../x.md", ""):
        check(f"safe_parts refuses {bad!r}", D.safe_parts(bad) is None)
    check("safe_parts keeps an ordinary name", D.safe_parts("A/b c.md") == ["A", "b c.md"])
    fresh()


# ============================================================ 7. the chat loop

def t_the_tool_is_offered_only_with_a_folder():
    fresh()
    enabled = {"my_files", "calculator"}
    check("no folder: not offered", AG.offered_tools(enabled) == ["calculator"])
    listed(folder("Offer"))
    check("a folder: offered", "my_files" in AG.offered_tools(enabled))
    check("not in [tools].enabled: never offered, folder or not",
          "my_files" not in AG.offered_tools({"calculator"}))
    tool = AG.TOOLS["my_files"]
    check("decided under file_read's action", tool.gate_lookup_name({}) == "file_read")
    check("its words fit the tool budget", AG.estimate_tokens(tool.schema()) <= 300,
          AG.estimate_tokens(tool.schema()))
    check("it is a reading tool (outside text)", "my_files" not in AG._NOT_READING)
    fresh()


def t_its_result_is_outside_text_and_notes_then_ask():
    watch = AG._TurnWatch([{"role": "user", "content": "what does my lease say",
                            "provenance": "typed"}], tainted=False)
    before = watch.note_needs_a_person()
    labelled = watch.took_in("my_files", {"ok": True, "text": "Pets are allowed."})
    check("a clean turn: a note would not ask before", before == "")
    check("the result is labelled outside data", labelled.get(AG.OUTSIDE_FIELD)
          == AG.OUTSIDE_LABEL)
    check("after reading a file, a note asks first",
          watch.note_needs_a_person() == AG.NOTE_AFTER_READING)


def t_one_answer_reads_at_most_two_parts():
    watch = AG._TurnWatch([{"role": "user", "content": "read it", "provenance": "typed"}],
                          tainted=False)
    ran = []
    real = D.run_tool
    D.run_tool = lambda args, **k: (ran.append(args), {"ok": True, "text": "part"})[1]
    fresh()
    listed(folder("Parts"))
    try:
        convo, steps = [], []
        for i in range(4):
            call = {"id": f"c{i}", "function": {"name": "my_files", "arguments": json.dumps(
                {"action": "read", "path": "/x.md", "part": i + 1})}}
            AG._one_call(call, ["my_files"], convo, steps,
                         lambda *a: types.SimpleNamespace(allowed=True, outcome="allowed",
                                                          tier="auto"),
                         None, AG._Out(lambda b: None, sse=False), lambda *a, **k: None, watch=watch)
        find = {"id": "f", "function": {"name": "my_files", "arguments": json.dumps(
            {"action": "find", "words": "lease"})}}
        AG._one_call(find, ["my_files"], convo, steps,
                     lambda *a: types.SimpleNamespace(allowed=True, outcome="allowed",
                                                      tier="auto"),
                     None, AG._Out(lambda b: None, sse=False), lambda *a, **k: None, watch=watch)
    finally:
        D.run_tool = real
        fresh()
    reads = [a for a in ran if a.get("action") == "read"]
    check(f"{AG.FILES_PARTS_PER_TURN} parts read, the rest refused before the gate",
          len(reads) == AG.FILES_PARTS_PER_TURN
          and sum(1 for s in steps if s["outcome"] == "refused") == 2, (ran, steps))
    check("the refusal tells the model why", "working memory" in convo[2]["content"])
    check("finding a file is not a part", any(a.get("action") == "find" for a in ran))


# ============================================================ 8. the routes and the patch

class FakeHandler:
    def __init__(self, path, body=b"{}", peer="127.0.0.1"):
        self.path = path
        self.body = body
        self.client_address = (peer, 5000)
        self.sent = None
        self.connection = types.SimpleNamespace(getsockname=lambda: ("127.0.0.1", 8000))

    def do_GET(self):
        self.sent = ("original GET", None)

    def do_POST(self):
        self.sent = ("original POST", None)

    def _send(self, code, obj):
        self.sent = (code, obj)


def t_the_routes():
    fresh()

    class H(FakeHandler):
        pass
    line = D.install(H, origin_ok=lambda h: True, token_ok=lambda h: h.path != "/api/folders?bad",
                     read_body=lambda h: h.body)
    check("the banner line names it", line.startswith("  folders    Folders Jarvis may look in"))
    h = H("/api/folders")
    H.do_GET(h)
    check("GET /api/folders answered here", h.sent[0] == 200 and h.sent[1]["title"] == D.TITLE)
    h = H("/api/status")
    H.do_GET(h)
    check("any other GET goes to the server's own handler", h.sent[0] == "original GET")
    h = H("/api/stop_all")
    H.do_POST(h)
    check("any other POST too", h.sent[0] == "original POST")

    class Tok(FakeHandler):
        pass
    D.install(Tok, origin_ok=lambda h: True, token_ok=lambda h: False, read_body=lambda h: b"{}")
    h = Tok("/api/folders/remove")
    Tok.do_POST(h)
    check("no token: 401, nothing done", h.sent[0] == 401)
    h = H("/api/folders/add", body=json.dumps({"path": str(folder("Route"))}).encode(),
          peer="100.64.0.7")
    real = D._from_this_pc
    D._from_this_pc = lambda p, l: p == "127.0.0.1"
    try:
        H.do_POST(h)
        check("adding from the phone's address: 403", h.sent[0] == 403)
        h = H("/api/folders/import", body=b"{}", peer="100.64.0.7")
        H.do_POST(h)
        check("importing from the phone's address: 403", h.sent[0] == 403)
    finally:
        D._from_this_pc = real
    check("install twice wraps once", "already on" in D.install(
        H, origin_ok=lambda h: True, token_ok=lambda h: True, read_body=lambda h: b"{}"))
    fresh()


def t_the_patch():
    order = _stack.order()
    check("documents.patch is last in apply-patches.ps1's list, after stop-all.patch",
          order[-1] == "documents.patch" and order.index("stop-all.patch") < len(order) - 1,
          order[-3:])
    patch = (HERE / "documents.patch").read_text(encoding="utf-8")
    check("it patches jarvis_hud.py only",
          [l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/")]
          == ["jarvis_hud.py"])
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return
    text, log = _stack.stand_in("jarvis_hud.py", order[:-1])
    d = Path(tempfile.mkdtemp(prefix="jarvis-documents-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text(patch, encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                            text=True)
        back = (d / "jarvis_hud.py").read_text(encoding="utf-8") == text
        check("applies to what the earlier patches wrote, and reverses",
              r.returncode == 0 and r2.returncode == 0 and back, (r.stderr, r2.stderr))
        i = after.find("jarvis_documents.install(Handler")
        j = after.find("jarvis_stop_all.install(Handler")
        k = after.find("_loopback_companion(bind, HUD_PORT, Handler)\n    print(")
        check("installed after stop-all, before anything listens", -1 < j < i < k, (j, i, k))
        check("with the server's own origin and token checks",
              "origin_ok=_origin_ok" in after[i:i + 200] and "token_ok=_token_ok"
              in after[i:i + 200])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    import _where
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("the module is shipped: apply-patches.ps1 and _where.SHIPPED",
          "'jarvis_documents.py'" in ps1[ps1.index("$SHIPPED = @("):]
          and "jarvis_documents.py" in _where.SHIPPED)


def t_both_apps_read_the_current_contract():
    r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_folders_cases.py"), "--check"],
                       capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    check("folders-cases.json (desktop and phone) is what the backend says today "
          "(python3 tools/gen_folders_cases.py)", r.returncode == 0, r.stdout + r.stderr)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
