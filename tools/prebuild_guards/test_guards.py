"""Adversarial tests for the six pre-build guards. Standard library only.

Run from the repository root:

    py -3 -B tools/prebuild_guards/test_guards.py

Every test drives the guard itself. If a guard is removed, the test fails (or
errors on the missing name); none of them pins source text. No test touches the
network, and the biggest archive built here is 4 MiB of zeros - small enough to
show a real high-ratio zip bomb without ever allocating gigabytes.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import stat
import struct
import subprocess
import sys
import types
import unicodedata
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

#: ``%TEMP%`` on this PC refuses writes (the same limit the Rust suite records),
#: so the tests make their folders in the ignored ``.dsh-scratch`` area of the
#: checkout instead. Nothing here is committed.
TEST_TMP = HERE.parent.parent / ".dsh-scratch" / "prebuild-guard-tests"
TEST_TMP.mkdir(parents=True, exist_ok=True)


def make_temp_dir() -> Path:
    """A throwaway folder that this sandbox can actually write inside.

    ``tempfile`` creates its folders with mode 0o700; under this Windows sandbox
    that mode produces a folder even the creating user cannot write in, so the
    tests make the folder with the default mode and remove it themselves.
    """
    path = TEST_TMP / f"t-{uuid.uuid4().hex[:12]}"
    path.mkdir()
    return path


@contextlib.contextmanager
def temp_dir():
    path = make_temp_dir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

import filesystem_walk as FW          # noqa: E402
import github_tree as GT              # noqa: E402
import html_sanitize as HS            # noqa: E402
import safe_archive as SA             # noqa: E402
import windows_names as WN            # noqa: E402


# ---------------------------------------------------------------------------
#   Trap 1 - Office / EPUB zip and XML bombs
# ---------------------------------------------------------------------------


class FakeInfo:
    def __init__(self, name, size, packed, *, flag_bits=0):
        self.filename = name
        self.file_size = size
        self.compress_size = packed
        self.flag_bits = flag_bits

    def is_dir(self):
        return False


class FakeZip:
    """A zip-shaped object whose member really yields more bytes than it says."""

    def __init__(self, info, payload):
        self.info = info
        self.payload = payload

    def infolist(self):
        return [self.info]

    def open(self, info):
        return io.BytesIO(self.payload)


class SafeArchiveTests(unittest.TestCase):
    XML = b'<?xml version="1.0"?><root><a>hi</a></root>'

    @staticmethod
    def build(members):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, payload in members:
                zf.writestr(name, payload)
        return buf.getvalue()

    @staticmethod
    def patch_central_sizes(raw, sizes):
        """Rewrite each central-directory record's declared uncompressed size."""
        data = bytearray(raw)
        pos = 0
        index = 0
        while True:
            at = data.find(b"PK\x01\x02", pos)
            if at < 0:
                break
            if index < len(sizes):
                struct.pack_into("<I", data, at + 24, sizes[index])
            index += 1
            pos = at + 4
        return bytes(data)

    def refused(self, raw, member="word/document.xml", **kwargs):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            with self.assertRaises(SA.GuardRefusal) as ctx:
                SA.read_xml_member(zf, member, **kwargs)
        return str(ctx.exception)

    def test_a_normal_document_part_is_parsed(self):
        raw = self.build([("word/document.xml", self.XML)])
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            root = SA.read_xml_member(zf, "word/document.xml")
        self.assertEqual(root.tag, "root")
        self.assertEqual(root.findtext("a"), "hi")

    def test_too_many_members_is_refused(self):
        raw = self.build([(f"part{i}.xml", b"<x/>") for i in range(2001)])
        text = self.refused(raw)
        self.assertIn("2,000", text)
        self.assertIn("more than", text)
        self.assertIn("Nothing was opened", text)

    def test_a_declared_total_over_the_cap_is_refused(self):
        # Five parts, each under the 25 MB per-part cap, together claiming
        # 105 MB - over the 100 MB total. The archive itself is tiny.
        raw = self.build([(f"part{i}.xml", b"<x/>") for i in range(5)])
        raw = self.patch_central_sizes(raw, [21 * 1024 * 1024] * 5)
        text = self.refused(raw)
        self.assertIn("100 MB", text)
        self.assertIn("zip bomb", text)

    def test_a_real_high_ratio_zip_is_refused(self):
        # 4 MiB of zeros compresses to a few kilobytes: a real high-ratio zip,
        # small enough that the test never holds a gigabyte.
        payload = b"<root>" + b"\x00" * (4 * 1024 * 1024) + b"</root>"
        raw = self.build([("word/document.xml", payload)])
        self.assertLess(len(raw), 200 * 1024, "the crafted zip should stay small")
        text = self.refused(raw)
        self.assertIn("zip bomb", text)
        self.assertIn("Nothing was opened", text)

    def test_a_header_that_lies_about_size_is_refused(self):
        payload = b"<root>" + b"\x00" * (1024 * 1024) + b"</root>"
        raw = self.build([("word/document.xml", payload)])
        raw = self.patch_central_sizes(raw, [1])       # the header now says one byte
        text = self.refused(raw)
        self.assertIn("Jarvis will not open this file", text)

    def test_the_bytes_actually_read_are_capped_even_when_the_header_lies(self):
        # The declared size is 10 bytes; the stream yields 4,097. The guard must
        # decide on what it read, not on what the header claimed.
        fake = FakeZip(FakeInfo("word/document.xml", 10, 5),
                       b"<root>" + b"a" * 4096 + b"</root>")
        with self.assertRaises(SA.GuardRefusal) as ctx:
            SA.read_xml_member(fake, "word/document.xml", max_member_bytes=1024)
        self.assertIn("1,024 bytes", str(ctx.exception))
        self.assertIn("bigger than", str(ctx.exception))

    def test_member_names_that_escape_are_refused(self):
        escapes = ["../escape.txt", "/abs.txt", "C:/x.txt", "a/../../b.txt"]
        for name in escapes:
            with self.subTest(name=name):
                raw = self.build([(name, b"<x/>")])
                text = self.refused(raw)
                self.assertIn("Nothing was opened", text)
                self.assertTrue(
                    any(word in text.lower() for word in
                        ("outside", "top of the disk", "drive letter")),
                    text)
        # zipfile rewrites "\\" to "/" while writing, so a raw backslash name
        # is made with the fake archive instead.
        fake = FakeZip(FakeInfo("..\\escape.txt", 5, 5), b"<x/>")
        with self.assertRaises(SA.GuardRefusal) as ctx:
            SA.read_xml_member(fake, "word/document.xml")
        self.assertIn("backslash", str(ctx.exception))

    def test_doctype_is_refused_before_the_parser(self):
        bomb = (b'<?xml version="1.0"?>'
                b'<!DOCTYPE x [<!ENTITY a "boom">]><x>&a;</x>')
        raw = self.build([("word/document.xml", bomb)])
        text = self.refused(raw)
        self.assertIn("DOCTYPE", text)
        self.assertIn("ENTITY", text)
        self.assertIn("Nothing was opened", text)

    def test_utf16_doctype_is_refused_too(self):
        # A plain byte search misses this: every character is followed by 0x00.
        bomb = ('<?xml version="1.0" encoding="utf-16"?>'
                '<!DOCTYPE x [<!ENTITY a "boom">]><x>&a;</x>').encode("utf-16")
        raw = self.build([("word/document.xml", bomb)])
        text = self.refused(raw)
        self.assertIn("DOCTYPE", text)

    def test_a_large_non_xml_member_does_not_block_the_xml_read(self):
        # A Word file may hold a picture that this reader never parses. A part
        # that is bigger than the per-XML-member cap, but is not the part being
        # read, must not refuse the small XML part that is.
        raw = self.build([("word/document.xml", self.XML),
                          ("word/media/image1.png", b"\x89PNG")])
        raw = self.patch_central_sizes(raw, [len(self.XML), 4 * 1024])
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            root = SA.read_xml_member(zf, "word/document.xml",
                                      max_member_bytes=2 * 1024)
        self.assertEqual(root.findtext("a"), "hi")

    def test_a_missing_member_is_refused(self):
        raw = self.build([("word/other.xml", self.XML)])
        text = self.refused(raw)
        self.assertIn("no part called", text)
        self.assertIn("word/document.xml", text)

    def test_an_encrypted_member_is_refused(self):
        raw = self.build([("word/document.xml", self.XML)])
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            zf.infolist()[0].flag_bits |= 0x1
            with self.assertRaises(SA.GuardRefusal) as ctx:
                SA.read_xml_member(zf, "word/document.xml")
        self.assertIn("password", str(ctx.exception))


# ---------------------------------------------------------------------------
#   Trap 2 - phone upload names and safe_join
# ---------------------------------------------------------------------------


class WindowsNamesTests(unittest.TestCase):
    def assert_refused(self, raw, *needles):
        with self.assertRaises(WN.GuardRefusal) as ctx:
            WN.sanitize_upload_name(raw)
        text = str(ctx.exception)
        for needle in needles:
            self.assertIn(needle.lower(), text.lower())
        return text

    def test_reserved_device_names_are_refused(self):
        for raw in ("CON", "con.txt", "NUL.md", "COM1.pdf", "LPT9.txt",
                    "CONIN$.txt"):
            with self.subTest(name=raw):
                self.assert_refused(raw, "device")

    def test_a_colon_is_refused(self):
        self.assert_refused("report.pdf:zone.identifier", "colon")

    def test_a_trailing_dot_or_space_is_refused(self):
        self.assert_refused("invoice.pdf.", "dot or a space")
        self.assert_refused("invoice.pdf ", "space")

    def test_path_separators_are_refused(self):
        self.assert_refused("../settings.json", "separator")
        self.assert_refused("..\\settings.json", "separator")
        self.assert_refused("sub\\notes.pdf", "separator")
        self.assert_refused("C:\\Users\\me\\invoice.pdf", "colon")

    def test_an_encoded_path_is_refused(self):
        self.assert_refused("..%2f..%2fsettings.json", "written in code")
        self.assert_refused("%2e%2e%5csettings.json", "written in code")

    def test_control_and_empty_names_are_refused(self):
        self.assert_refused("", "no file name")
        self.assert_refused(".", "folder")
        self.assert_refused("..", "folder")
        self.assert_refused("...", "folder")
        self.assert_refused("a\x00.pdf", "cannot see")
        self.assert_refused("a\n.pdf", "cannot see")

    def test_the_extension_allow_list_is_enforced(self):
        self.assert_refused("notes.exe", "can only keep")
        self.assert_refused("noext", "can only keep")
        self.assert_refused("file.pdf.exe", "can only keep")
        self.assertEqual(WN.sanitize_upload_name("notes.txt"), "notes.txt")

    def test_unicode_is_normalised_before_the_checks(self):
        # Full-width CON and a full-width colon are the same dangers once the
        # name is normalised; a full-width leading space is still a space.
        self.assert_refused("\uff43\uff4f\uff4e.txt", "device")
        self.assert_refused("notes\uff1a1.pdf", "colon")
        self.assert_refused("\u3000notes.pdf", "space")

    def test_ordinary_names_survive(self):
        self.assertEqual(WN.sanitize_upload_name("Project notes (final).pdf"),
                         "Project notes (final).pdf")
        self.assertEqual(WN.sanitize_upload_name("REPORT.PDF"), "REPORT.pdf")
        decomposed = "Cafe\u0301.pdf"
        cleaned = WN.sanitize_upload_name(decomposed)
        self.assertTrue(unicodedata.is_normalized("NFC", cleaned), cleaned)

    def test_a_long_name_keeps_its_extension(self):
        cleaned = WN.sanitize_upload_name("a" * 300 + ".pdf")
        self.assertLessEqual(len(cleaned), WN.MAX_UPLOAD_NAME_CHARS)
        self.assertTrue(cleaned.endswith(".pdf"))
        self.assertEqual(cleaned, WN.sanitize_upload_name(cleaned))

    def test_safe_join_stays_under_the_root(self):
        with temp_dir() as tmp:
            root = Path(tmp)
            self.assertEqual(WN.safe_join(root, "notes.pdf"), root / "notes.pdf")
            with self.assertRaises(WN.GuardRefusal):
                WN.safe_join(root, "../escape.pdf")
            with self.assertRaises(WN.GuardRefusal):
                WN.safe_join(root, "sub/notes.pdf")

    def test_safe_join_refuses_a_path_that_resolves_outside(self):
        with temp_dir() as tmp:
            root = Path(tmp)
            (root / "link.pdf").write_bytes(b"x")
            real_resolve = Path.resolve
            outside = root.parent / "outside.pdf"

            def fake_resolve(self, *args, **kwargs):
                if self.name == "link.pdf":
                    return outside
                return real_resolve(self, *args, **kwargs)

            with mock.patch.object(Path, "resolve", fake_resolve):
                with self.assertRaises(WN.GuardRefusal) as ctx:
                    WN.safe_join(root, "link.pdf")
            self.assertIn("outside", str(ctx.exception))


# ---------------------------------------------------------------------------
#   Trap 4 - GitHub base_tree and unasked deletes
# ---------------------------------------------------------------------------


class GithubTreeTests(unittest.TestCase):
    README = {"path": "README.md", "content": "# hi"}

    def test_a_payload_with_no_base_tree_is_refused(self):
        with self.assertRaises(GT.GuardRefusal) as ctx:
            GT.build_tree_payload([self.README])
        text = str(ctx.exception)
        self.assertIn("which version", text)
        self.assertIn("every other file", text)

    def test_a_blank_base_tree_is_refused(self):
        with self.assertRaises(GT.GuardRefusal):
            GT.build_tree_payload([self.README], base_tree="   ")

    def test_a_misspelled_base_tree_is_refused(self):
        with self.assertRaises(GT.GuardRefusal) as ctx:
            GT.validate_tree_payload({"tree": [self.README], "baseTree": "abc"})
        self.assertIn("baseTree", str(ctx.exception))

    def test_a_valid_payload_keeps_the_base_tree(self):
        payload = GT.build_tree_payload([self.README], base_tree="abc123")
        self.assertEqual(payload["base_tree"], "abc123")
        self.assertEqual(payload["tree"][0]["path"], "README.md")
        self.assertEqual(payload["tree"][0]["mode"], "100644")

    def test_only_a_new_repository_may_omit_the_base_tree(self):
        payload = GT.build_tree_payload(
            [self.README], updating_existing_branch=False)
        self.assertNotIn("base_tree", payload)

    def test_bad_entries_are_refused(self):
        bad = [
            [{"path": "../evil.md", "content": "x"}],
            [{"path": "a\\b.md", "content": "x"}],
            [{"path": "same.md", "content": "x"},
             {"path": "same.md", "content": "y"}],
            [{"path": "both.md", "content": "x", "sha": "abc"}],
            [{"path": "dir", "type": "tree", "mode": "100644", "sha": "abc"}],
        ]
        for entries in bad:
            with self.subTest(entries=entries):
                with self.assertRaises(GT.GuardRefusal):
                    GT.build_tree_payload(entries, base_tree="abc")

    def test_a_payload_that_deletes_a_file_is_refused(self):
        current = {"README.md": "old", "src/app.py": "blob2"}
        with self.assertRaises(GT.GuardRefusal) as ctx:
            GT.compare_trees([{"path": "README.md", "sha": "old"}], current)
        text = str(ctx.exception)
        self.assertIn("delete", text)
        self.assertIn("src/app.py", text)
        self.assertIn("Nothing was sent", text)

    def test_an_explicitly_requested_delete_is_allowed_and_counted(self):
        current = {"README.md": "old", "src/app.py": "blob2"}
        report = GT.compare_trees(
            [{"path": "README.md", "sha": "old"}], current,
            deletion_requested=("src/app.py",))
        self.assertEqual(report["deleted"], 1)
        self.assertEqual(report["deleted_paths"], ["src/app.py"])
        self.assertEqual(GT.counts_line(report),
                         "Added: 0 · Modified: 0 · Deleted: 1")

    def test_added_modified_unchanged_and_deleted_are_exact(self):
        current = {"README.md": "old", "same.md": "same", "gone.md": "g"}
        proposed = [
            {"path": "README.md", "sha": "new"},
            {"path": "same.md", "sha": "same"},
            {"path": "new.md", "content": "x"},
        ]
        report = GT.compare_trees(proposed, current,
                                  deletion_requested=("gone.md",))
        self.assertEqual(report["added"], 1)
        self.assertEqual(report["modified"], 1)
        self.assertEqual(report["unchanged"], 1)
        self.assertEqual(report["deleted"], 1)
        self.assertEqual(report["added_paths"], ["new.md"])
        self.assertEqual(report["modified_paths"], ["README.md"])
        self.assertEqual(GT.counts_line(report),
                         "Added: 1 · Modified: 1 · Deleted: 1")


# ---------------------------------------------------------------------------
#   Trap 5 - junctions / reparse points
# ---------------------------------------------------------------------------


class FilesystemWalkTests(unittest.TestCase):
    def make_tree(self):
        root = make_temp_dir()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "a.txt").write_text("a", encoding="utf-8")
        (root / "sub").mkdir()
        (root / "sub" / "b.txt").write_text("b", encoding="utf-8")
        return root

    @staticmethod
    def patch_lstat_for(target, info):
        target = os.path.normcase(os.path.abspath(os.fspath(target)))
        real_lstat = os.lstat

        def fake(path, *args, **kwargs):
            here = os.path.normcase(os.path.abspath(os.fspath(path)))
            if here == target:
                return info
            return real_lstat(path, *args, **kwargs)

        return mock.patch("os.lstat", fake)

    def test_a_normal_tree_walks(self):
        root = self.make_tree()
        self.assertEqual(FW.walk_project_files(root), ["a.txt", "sub/b.txt"])

    def test_the_root_must_be_a_folder(self):
        root = self.make_tree()
        with self.assertRaises(FW.GuardRefusal):
            FW.walk_project_files(root / "a.txt")
        with self.assertRaises(FW.GuardRefusal):
            FW.walk_project_files(root / "not-there")

    def test_a_file_symlink_is_refused_by_its_mode(self):
        root = self.make_tree()
        fake = types.SimpleNamespace(st_mode=stat.S_IFLNK,
                                     st_file_attributes=0)
        with self.patch_lstat_for(root / "a.txt", fake):
            with self.assertRaises(FW.GuardRefusal) as ctx:
                FW.walk_project_files(root)
        self.assertIn("shortcut", str(ctx.exception))

    def test_a_reparse_flagged_folder_is_refused_by_its_attributes(self):
        root = self.make_tree()
        fake = types.SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=FW.FILE_ATTRIBUTE_REPARSE_POINT)
        with self.patch_lstat_for(root / "sub", fake):
            with self.assertRaises(FW.GuardRefusal) as ctx:
                FW.walk_project_files(root)
        self.assertIn("shortcut", str(ctx.exception))

    def test_a_file_that_resolves_outside_is_refused(self):
        root = self.make_tree()
        outside = root.parent / "outside.txt"
        real_resolve = Path.resolve

        def fake_resolve(self, *args, **kwargs):
            if self.name == "a.txt":
                return outside
            return real_resolve(self, *args, **kwargs)

        with mock.patch.object(Path, "resolve", fake_resolve):
            with self.assertRaises(FW.GuardRefusal) as ctx:
                FW.walk_project_files(root)
        self.assertIn("outside", str(ctx.exception))

    def test_a_special_file_is_refused(self):
        root = self.make_tree()
        fake = types.SimpleNamespace(st_mode=stat.S_IFIFO, st_file_attributes=0)
        with self.patch_lstat_for(root / "a.txt", fake):
            with self.assertRaises(FW.GuardRefusal) as ctx:
                FW.walk_project_files(root)
        self.assertIn("not an ordinary file", str(ctx.exception))

    def test_the_file_cap_is_enforced(self):
        root = self.make_tree()
        (root / "c.txt").write_text("c", encoding="utf-8")
        with self.assertRaises(FW.GuardRefusal) as ctx:
            FW.walk_project_files(root, max_files=2)
        self.assertIn("2 files", str(ctx.exception))

    def test_the_time_cap_is_enforced(self):
        root = self.make_tree()
        ticks = iter([0.0, 0.0] + [100.0] * 20)
        with self.assertRaises(FW.GuardRefusal) as ctx:
            FW.walk_project_files(root, max_seconds=1, clock=lambda: next(ticks))
        self.assertIn("longer than 1 second", str(ctx.exception))

    def test_the_project_folder_itself_must_not_be_a_shortcut(self):
        root = self.make_tree()
        fake = types.SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=FW.FILE_ATTRIBUTE_REPARSE_POINT)
        with self.patch_lstat_for(root, fake):
            with self.assertRaises(FW.GuardRefusal) as ctx:
                FW.walk_project_files(root)
        self.assertIn("folder itself is a shortcut", str(ctx.exception))

    def test_a_real_junction_is_refused_or_not_testable(self):
        """A real junction/symlink pointing out of the project must be refused.

        Creating a junction can need a privilege this machine does not grant.
        When it cannot be made, the test is reported NOT-TESTABLE and skipped;
        it is never counted as a pass.
        """
        base = make_temp_dir()
        project = base / "project"
        project.mkdir()
        (project / "a.txt").write_text("a", encoding="utf-8")
        outside = base / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret", encoding="utf-8")
        link = project / "linked"

        def cleanup_base():
            # Remove the link FIRST, and never recurse if that fails: walking a
            # junction with rmtree would delete the folder it points at.
            try:
                if os.name == "nt":
                    if os.path.lexists(link):
                        os.rmdir(link)
                elif os.path.lexists(link):
                    link.unlink()
            except OSError:
                return
            shutil.rmtree(base, ignore_errors=True)

        self.addCleanup(cleanup_base)
        made = False
        if os.name == "nt":
            try:
                done = subprocess.run(
                    [os.environ.get("COMSPEC", "cmd"), "/c", "mklink", "/J",
                     str(link), str(outside)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False)
                made = done.returncode == 0 and link.exists()
            except OSError:
                made = False
        else:
            try:
                os.symlink(outside, link, target_is_directory=True)
                made = True
            except OSError:
                made = False
        if not made:
            self.skipTest("NOT-TESTABLE: this machine did not let the test "
                          "create a real junction or folder link, so the "
                          "real-shortcut branch was NOT exercised")
        with self.assertRaises(FW.GuardRefusal) as ctx:
            FW.walk_project_files(project)
        self.assertIn("shortcut", str(ctx.exception))


# ---------------------------------------------------------------------------
#   Trap 6 - EPUB / KDP XHTML and local-file reads
# ---------------------------------------------------------------------------


class HtmlSanitizeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = make_temp_dir()
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.assets = self._tmp / "assets"
        (self.assets / "pics").mkdir(parents=True)
        (self.assets / "pics" / "cover.png").write_bytes(b"\x89PNG")

    def clean(self, markup):
        return HS.sanitize_xhtml(markup, assets_dir=self.assets)

    def test_script_and_event_handlers_are_removed(self):
        out = self.clean(
            '<p onclick="steal()">Hi<script>alert(1)</script>'
            '<img src="pics/cover.png" onerror="boom()" /></p>')
        low = out.lower()
        self.assertNotIn("<script", low)
        self.assertNotIn("alert(1)", out)
        self.assertNotIn("onclick", low)
        self.assertNotIn("onerror", low)
        self.assertIn('<img src="pics/cover.png"', out)
        self.assertIn("Hi", out)

    def test_a_file_url_picture_is_refused(self):
        with self.assertRaises(HS.GuardRefusal) as ctx:
            self.clean('<img src="file:///C:/Users/me/secret.png" />')
        self.assertIn("file on this PC", str(ctx.exception))

    def test_a_path_above_the_assets_folder_is_refused(self):
        with self.assertRaises(HS.GuardRefusal) as ctx:
            self.clean('<img src="../../secret.png" />')
        self.assertIn("folder above", str(ctx.exception))

    def test_a_percent_encoded_escape_is_refused(self):
        with self.assertRaises(HS.GuardRefusal):
            self.clean('<img src="..%2f..%2fsecret.png" />')

    def test_absolute_and_unc_pictures_are_refused(self):
        for src in ("/etc/passwd", "\\\\server\\share\\x.png",
                    "C:/Users/me/secret.png"):
            with self.subTest(src=src):
                with self.assertRaises(HS.GuardRefusal):
                    self.clean(f'<img src="{src}" />')

    def test_a_javascript_link_loses_its_href(self):
        out = self.clean('<a href="javascript:alert(1)">click</a>')
        self.assertEqual(out, "<a>click</a>")
        self.assertNotIn("javascript", out.lower())

    def test_harmless_markup_and_entities_survive(self):
        source = ('<p title="a &amp; b &quot;q&quot;">x &lt; y &amp; '
                  '<strong>z</strong></p>')
        self.assertEqual(
            self.clean(source),
            '<p title="a &amp; b &quot;q&quot;">x &lt; y &amp; '
            '<strong>z</strong></p>')

    def test_a_picture_inside_the_assets_folder_is_kept(self):
        out = self.clean('<img src="pics/cover.png" alt="cover" width="10" />')
        self.assertEqual(out, '<img src="pics/cover.png" alt="cover" width="10" />')

    def test_mismatched_markup_is_refused(self):
        with self.assertRaises(HS.GuardRefusal) as ctx:
            self.clean("<p><em>x</p>")
        self.assertIn("closed properly", str(ctx.exception))

    def test_a_picture_that_resolves_outside_the_assets_folder_is_refused(self):
        real_resolve = Path.resolve
        outside = self._tmp / "outside.png"

        def fake_resolve(self, *args, **kwargs):
            if self.name == "cover.png":
                return outside
            return real_resolve(self, *args, **kwargs)

        with mock.patch.object(Path, "resolve", fake_resolve):
            with self.assertRaises(HS.GuardRefusal) as ctx:
                self.clean('<img src="pics/cover.png" />')
        self.assertIn("outside", str(ctx.exception))

    def test_dangerous_containers_are_dropped_with_their_contents(self):
        out = self.clean(
            '<iframe src="file:///C:/x"></iframe>'
            '<object data="x">fallback</object>'
            '<embed src="x">'
            '<form action="file:///C:/x"><input name="a">label</form>'
            '<p>ok</p>')
        low = out.lower()
        for bad in ("<iframe", "<object", "<embed", "<form", "<input"):
            self.assertNotIn(bad, low)
        self.assertNotIn("fallback", out)
        self.assertNotIn("label", out)
        self.assertIn("<p>ok</p>", out)

    def test_a_void_tag_inside_a_dropped_container_does_not_swallow_the_rest(self):
        # <frame> has no closing tag; counting it as an opening tag would leave
        # the "skip the form" counter stuck and hide every paragraph after it.
        out = self.clean('<frameset><frame src="x"></frameset><p>ok</p>')
        self.assertIn("<p>ok</p>", out)

    def test_a_full_document_keeps_its_structure_but_loses_style_and_link(self):
        out = self.clean(
            '<html><head><title>T</title><style>body{}</style>'
            '<link rel="stylesheet" href="file:///C:/x.css" /></head>'
            '<body><p>hi</p></body></html>')
        self.assertEqual(
            out, "<html><head><title>T</title></head><body><p>hi</p></body></html>")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    bad = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    passed = result.testsRun - bad - skipped
    print(f"\nSUMMARY: {result.testsRun} tests run, {passed} passed, "
          f"{bad} failed, {skipped} NOT-TESTABLE/skipped "
          f"(a skip is never counted as a pass)")
    sys.exit(0 if bad == 0 else 1)
