"""The pairing token is kept in Windows Credential Manager, never in a file.

CLAUDE.md rule 3: a key is "kept out of anything the app writes to disk in
plain text". token-file.patch broke it - the backend wrote its token to
~/.openjarvis/token. token-store.patch and jarvis_token_store.py move it into
Credential Manager, and move the old file in (then delete it).

What this proves, everywhere:
  - every branch of jarvis_token_store.resolve(), against a stand-in store:
    first run, a restart, the old file moved in and deleted, a file that
    disagrees (the file wins), a store that refuses or cannot be read back
    (the old file is kept, a new token is used for this run only), and
    HUD_TOKEN still winning. After EVERY case: no token file was written.
  - the banner never contains the token.
  - the name the backend files it under is the name the desktop reads
    (jarvis-desktop/src-tauri/src/token_store.rs BACKEND_TARGET).
  - token-store.patch applies on top of token-file, loopback-too and
    bind-wildcard (a rehearsal with _skeleton), reverses cleanly, and the
    patched _resolve_token - lifted and run - writes no file and never
    touches the real store.
On Windows, also a LIVE round trip through the real Credential Manager,
under a throwaway name that is deleted afterwards - never the real token.

    python3 test_token_store.py
"""
import ast
import os
import re
import secrets
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_token_store as ts  # noqa: E402
import _skeleton  # noqa: E402

REPO = HERE.parent
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class FakeStore:
    """Credential Manager, in memory. `refuse_write` / `refuse_read` make it
    say no the way the real one does (a StoreError with a code); `garble`
    makes a write land as something else, so the read-back check is tested."""

    def __init__(self, value=None, refuse_write=False, refuse_read=False, garble=False):
        self.value, self.writes = value, 0
        self.refuse_write, self.refuse_read, self.garble = refuse_write, refuse_read, garble

    def read(self):
        if self.refuse_read:
            raise ts.StoreError("reading failed (Windows error 1312)")
        return self.value

    def write(self, token):
        if self.refuse_write:
            raise ts.StoreError("saving failed (Windows error 1312)")
        self.writes += 1
        self.value = token + "-garbled" if self.garble else token

    def delete(self):
        had, self.value = self.value is not None, None
        return had


def scratch():
    d = Path(tempfile.mkdtemp()) / "cfg"
    d.mkdir(parents=True)
    return d, d / "token"


def files_in(d):
    return sorted(p.name for p in d.iterdir())


def no_secret_in_banner(name, got):
    text = "\n".join(got.banner())
    check(f"{name}: the banner does not contain the token",
          not got.token or got.token not in text, text)


# ------------------------------------------------------------- resolve()

def t_first_run_makes_one_in_the_store():
    d, f = scratch()
    store = FakeStore()
    got = ts.resolve(f, store=store, environ={}, make=lambda: "fresh-" + "x" * 40)
    check("first run: a token is made", got.token == "fresh-" + "x" * 40, repr(got.token))
    check("first run: kept in Credential Manager", got.where == "credential-manager" and store.value == got.token)
    check("first run: says it was made (so the banner can say how to pair)", got.made)
    check("first run: NO file is written", files_in(d) == [], files_in(d))
    no_secret_in_banner("first run", got)
    # A restart must give the same token, or every boot unpairs the phone.
    again = ts.resolve(f, store=store, environ={}, make=lambda: "a-different-one")
    check("restart: the SAME token comes back", again.token == got.token and not again.made)
    check("restart: still no file", files_in(d) == [])


def t_the_old_file_is_moved_in_and_deleted():
    d, f = scratch()
    f.write_text("old-plain-token\n", encoding="utf-8")
    (d / "token.tmp").write_text("half-written\n", encoding="utf-8")
    store = FakeStore()
    got = ts.resolve(f, store=store, environ={}, make=lambda: "never")
    check("old file: its token is kept (the phone stays paired)", got.token == "old-plain-token")
    check("old file: now in Credential Manager", store.value == "old-plain-token")
    check("old file: the plain-text file is deleted, and its .tmp", files_in(d) == [], files_in(d))
    check("old file: the banner says it moved", any("moved out of" in n for n in got.notes), got.notes)
    no_secret_in_banner("old file", got)


def t_a_file_that_disagrees_wins():
    """With the module in place the file is never written, so a file that
    exists was made by the old code after the move (e.g. after -Revert) -
    it is what the phone was last paired with."""
    d, f = scratch()
    f.write_text("newer-from-old-code", encoding="utf-8")
    store = FakeStore("older-in-store")
    got = ts.resolve(f, store=store, environ={})
    check("disagreeing file: the file's token wins", got.token == "newer-from-old-code")
    check("disagreeing file: and replaces the store's", store.value == "newer-from-old-code")
    check("disagreeing file: the file is deleted", files_in(d) == [])


def t_a_refusing_store_keeps_the_old_file():
    d, f = scratch()
    f.write_text("old-plain-token", encoding="utf-8")
    for label, store in (("refuses writes", FakeStore(refuse_write=True)),
                         ("refuses reads", FakeStore(refuse_read=True)),
                         ("reads back something else", FakeStore(garble=True)),
                         ("is not there at all", ts.Unavailable("there is no Windows Credential Manager"))):
        got = ts.resolve(f, store=store, environ={})
        check(f"store {label}: the old token is still used", got.token == "old-plain-token", repr(got))
        check(f"store {label}: the file is left, not deleted", f.is_file())
        check(f"store {label}: the banner says it is still plain text",
              got.where == "old-file" and any("still plain text" in n for n in got.notes), got.notes)
        no_secret_in_banner(f"store {label}", got)
    # The store already holds an OLDER token, and the move fails: the file
    # still wins (it is what the phone was last paired with) and stays.
    got = ts.resolve(f, store=FakeStore("older-in-store", garble=True), environ={})
    check("store holds another token and the move fails: the file's is used",
          got.token == "old-plain-token" and got.where == "old-file" and f.is_file(), repr(got))


def t_a_refusing_store_with_no_file_writes_nothing():
    for label, store in (("refuses writes", FakeStore(refuse_write=True)),
                         ("reads back something else", FakeStore(garble=True)),
                         ("is not there at all", ts.Unavailable("there is no Windows Credential Manager"))):
        d, f = scratch()
        got = ts.resolve(f, store=store, environ={}, make=lambda: "this-run-" + "y" * 40)
        check(f"no file, store {label}: a token is still used for this run",
              got.token == "this-run-" + "y" * 40 and got.where == "this-run-only")
        check(f"no file, store {label}: NOTHING is written to disk", files_in(d) == [], files_in(d))
        check(f"no file, store {label}: the banner says it will not survive a restart",
              any("pairing again" in n for n in got.notes), got.notes)
        no_secret_in_banner(f"no file, store {label}", got)


def t_the_environment_still_wins():
    d, f = scratch()
    store = FakeStore("in-store")
    got = ts.resolve(f, store=store, environ={"HUD_TOKEN": "  set-by-hand  "})
    check("HUD_TOKEN beats the store", got.token == "set-by-hand" and got.where == "environment")
    check("and the store is not overwritten by it", store.value == "in-store")
    got = ts.resolve(f, store=FakeStore("in-store"), environ={"HUD_TOKEN": "   "})
    check("an all-whitespace HUD_TOKEN falls through instead of disabling auth",
          got.token == "in-store")
    # The old file is still moved in when HUD_TOKEN is set, so it is not left
    # on disk just because the environment happened to win this time.
    f.write_text("old-plain-token", encoding="utf-8")
    store = FakeStore()
    got = ts.resolve(f, store=store, environ={"HUD_TOKEN": "set-by-hand"})
    check("HUD_TOKEN set: the old file is still moved in and deleted",
          store.value == "old-plain-token" and not f.exists() and got.token == "set-by-hand")


def t_blank_and_unreadable_files():
    d, f = scratch()
    f.write_text("   \n", encoding="utf-8")
    store = FakeStore()
    got = ts.resolve(f, store=store, environ={}, make=lambda: "fresh")
    check("a blank old file is not a token", got.token == "fresh")



def t_the_old_file_in_any_encoding_windows_writes():
    # Bug audit 3, CONN-5. PowerShell 5.1's `Out-File` and `>` write UTF-16
    # with a byte-order mark; `-Encoding UTF8` writes UTF-8 WITH one; Notepad
    # can save either. The file used to be read as plain UTF-8: UTF-16 raised
    # UnicodeDecodeError (the backend did not start), and a UTF-8 mark became
    # the token's first character (the phone never matched it again).
    cases = (
        ("UTF-8 with a byte-order mark", b"\xef\xbb\xbfold-plain-token\r\n"),
        ("UTF-16 little-endian with a mark (PowerShell 5.1's default)",
         "old-plain-token\r\n".encode("utf-16")),  # Python writes the LE mark here
        ("UTF-16 big-endian with a mark", b"\xfe\xff" + "old-plain-token\n".encode("utf-16-be")),
        ("plain UTF-8, spaces and a Windows line end", b"  old-plain-token \r\n"),
    )
    for name, data in cases:
        d, f = scratch()
        f.write_bytes(data)
        try:
            tok, problem = ts._read_file(f)
        except Exception as exc:
            tok, problem = None, f"RAISED {type(exc).__name__}"
        check(f"{name}: read as the token itself", tok == "old-plain-token" and problem is None,
              repr((tok, problem)))
        store = FakeStore()
        got = ts.resolve(f, store=store, environ={}, make=lambda: "fresh")
        check(f"{name}: moved into the store unchanged, and the file deleted",
              got.token == "old-plain-token" and store.value == "old-plain-token"
              and not f.exists(), repr((got.token, store.value, f.exists())))
    # Not text at all: a sentence, not an exception, and the file is kept.
    for name, data in (("bytes that are not UTF-8", b"old\xff\xfe\x80token"),
                       ("UTF-16 cut off mid-character", b"\xff\xfeo\x00l")):
        d, f = scratch()
        f.write_bytes(data)
        try:
            tok, problem = ts._read_file(f)
        except Exception as exc:
            tok, problem = None, f"RAISED {type(exc).__name__}"
        check(f"{name}: no token, a plain problem sentence, no exception",
              tok is None and problem and "RAISED" not in problem and "UTF" in problem,
              repr((tok, problem)))
        store = FakeStore()
        try:
            got = ts.resolve(f, store=store, environ={}, make=lambda: "fresh")
            ok = (got.token == "fresh" and f.exists()
                  and any("not UTF-8 or UTF-16" in n for n in got.notes))
            detail = repr((got.token, got.notes))
        except Exception as exc:
            ok, detail = False, f"resolve raised {type(exc).__name__}: {exc}"
        check(f"{name}: the backend still starts, says why, and leaves the file alone", ok, detail)

def t_errors_carry_codes_not_tokens():
    src = (HERE / "jarvis_token_store.py").read_text(encoding="utf-8")
    raises = re.findall(r"raise (?:StoreError|Unavailable)\((.*)\)", src)
    check("every error names a Windows error or a reason, never the token",
          raises and not any("token}" in r or "{token" in r or "{data" in r for r in raises), raises)
    check("the module writes no file anywhere",
          "write_text(" not in src and "open(" not in src, "a write_text/open crept in")


# ------------------------------------------------ backend and desktop agree

def t_the_desktop_reads_the_same_name():
    rs = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "token_store.rs").read_text(encoding="utf-8")
    m = re.search(r'pub const BACKEND_TARGET: &str = "([^"]+)";', rs)
    check("token_store.rs has BACKEND_TARGET", bool(m))
    check("the desktop reads the name the backend writes",
          bool(m) and m.group(1) == ts.TARGET, f"{m and m.group(1)!r} vs {ts.TARGET!r}")
    desk = re.search(r'pub const TARGET: &str = "([^"]+)";', rs)
    check("and it is NOT the desktop's own name (typed tokens stay separate)",
          bool(desk) and desk.group(1) != ts.TARGET)
    # Same format both ways: UTF-8 bytes, generic, per user on this PC.
    check("both store a generic credential",
          "CRED_TYPE_GENERIC" in rs and ts._CRED_TYPE_GENERIC == 1)
    check("both persist it for this user on this PC",
          "CRED_PERSIST_LOCAL_MACHINE" in rs and ts._CRED_PERSIST_LOCAL_MACHINE == 2)
    check("both store the token as UTF-8 bytes",
          "token.as_bytes()" in rs and "String::from_utf8(bytes)" in rs)


# -------------------------------------------------------- the patch itself

def _patched():
    ok, out = _skeleton.rehearse("token-store.patch", "token-file.patch",
                                 on_top=("loopback-too.patch", "bind-wildcard.patch"))
    if ok is None:
        raise AssertionError(out)
    return ok, out


def t_the_patch_applies_and_reverses():
    ok, out = _patched()
    check("token-store.patch applies over token-file, loopback-too and bind-wildcard, "
          "and reverses cleanly", ok, out if not ok else "")
    if not ok:
        return
    fn = out[out.index("def _resolve_token"):]
    fn = fn[:fn.index("\ndef ", 1)]
    check("the patched _resolve_token writes no file",
          "write_text" not in fn and ".replace(TOKEN_FILE)" not in fn and "chmod" not in fn)
    check("it asks jarvis_token_store", "jarvis_token_store.resolve(TOKEN_FILE)" in fn)
    check("the banner prints TOKEN_BANNER, never HUD_TOKEN",
          "for line in TOKEN_BANNER:" in out and "{HUD_TOKEN}" not in out)
    check("the old 'token      {TOKEN_FILE}' banner line is gone",
          "token      {TOKEN_FILE}" not in out)
    check("the refusal no longer says the token is in a file",
          "is normally made for you at {TOKEN_FILE}" not in out)
    check("HUD_TOKEN is still the resolved value", "HUD_TOKEN = _resolve_token()" in out)


def _lift(src, config_dir, module):
    tree = ast.parse(src[src.index("def _resolve_token"):].split("\n\ndef ", 1)[0])
    ns = {"os": os, "TOKEN_FILE": config_dir / "token", "TOKEN_BANNER": []}
    exec(compile(tree, "<patched _resolve_token>", "exec"), ns)
    saved = sys.modules.get("jarvis_token_store")
    if module is None:
        sys.modules["jarvis_token_store"] = None       # makes the import fail
    else:
        sys.modules["jarvis_token_store"] = module
    try:
        return ns["_resolve_token"](), ns
    finally:
        if saved is None:
            sys.modules.pop("jarvis_token_store", None)
        else:
            sys.modules["jarvis_token_store"] = saved


def t_the_patched_function_runs():
    ok, out = _patched()
    if not ok:
        check("the patched _resolve_token runs", False, out)
        return
    # The real resolve(), but on a stand-in store - this must never touch
    # the owner's real Credential Manager entry.
    store = FakeStore()
    stand_in = types.SimpleNamespace(
        resolve=lambda token_file: ts.resolve(token_file, store=store, environ={},
                                              make=lambda: "patched-" + "z" * 40))
    d, f = scratch()
    f.write_text("old-plain-token", encoding="utf-8")
    saved_env = os.environ.pop("HUD_TOKEN", None)
    try:
        tok, ns = _lift(out, d, stand_in)
        check("patched: the old file's token is used", tok == "old-plain-token")
        check("patched: and moved into the store, the file deleted",
              store.value == "old-plain-token" and files_in(d) == [], files_in(d))
        banner = "\n".join(ns["TOKEN_BANNER"])
        check("patched: TOKEN_BANNER is filled, without the token",
              "Credential Manager" in banner and tok not in banner, banner)
        d2, _ = scratch()
        tok, ns = _lift(out, d2, None)
        check("patched, module missing: no token, no file, and the banner says why",
              tok == "" and files_in(d2) == [] and "jarvis_token_store.py is missing"
              in "\n".join(ns["TOKEN_BANNER"]))
    finally:
        if saved_env is not None:
            os.environ["HUD_TOKEN"] = saved_env


def t_the_install_lists_have_it():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    patches = ps1[ps1.index("$PATCHES = @("):]
    patches = patches[:patches.index("\n)")]
    names = re.findall(r"'([\w-]+\.patch)'", patches)
    check("apply-patches.ps1 applies token-store.patch", "token-store.patch" in names)
    check("after token-file, loopback-too and bind-wildcard",
          all(names.index(p) < names.index("token-store.patch")
              for p in ("token-file.patch", "loopback-too.patch", "bind-wildcard.patch")))


# ------------------------------------------------------------ live, Windows

def t_live_windows_round_trip():
    if os.name != "nt":
        print("skip  live Credential Manager round trip (not Windows)")
        return
    name = f"Jarvis Backend/test {secrets.token_hex(6)}"      # never the real one
    store = ts.WindowsStore(target=name)
    try:
        check("live: nothing there to begin with", store.read() is None)
        tok = secrets.token_urlsafe(32)
        store.write(tok)
        check("live: written and read back identically", store.read() == tok)
        d, f = scratch()
        f.write_text("old-plain-live", encoding="utf-8")
        got = ts.resolve(f, store=store, environ={})
        check("live: the old file moved into the real store and deleted",
              got.token == "old-plain-live" and store.read() == "old-plain-live" and not f.exists())
        check("live: deleted", store.delete() is True and store.read() is None)
        check("live: deleting again is not an error", store.delete() is False)
    finally:
        try:
            store.delete()
        except ts.StoreError:
            pass


if __name__ == "__main__":
    for fn in (t_first_run_makes_one_in_the_store, t_the_old_file_is_moved_in_and_deleted,
               t_a_file_that_disagrees_wins, t_a_refusing_store_keeps_the_old_file,
               t_a_refusing_store_with_no_file_writes_nothing, t_the_environment_still_wins,
               t_blank_and_unreadable_files, t_the_old_file_in_any_encoding_windows_writes,
               t_errors_carry_codes_not_tokens,
               t_the_desktop_reads_the_same_name, t_the_patch_applies_and_reverses,
               t_the_patched_function_runs, t_the_install_lists_have_it,
               t_live_windows_round_trip):
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
