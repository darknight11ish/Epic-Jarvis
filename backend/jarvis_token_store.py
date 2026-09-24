"""jarvis_token_store.py - the backend's pairing token, kept in Windows
Credential Manager instead of a plain file.

WHY
CLAUDE.md rule 3: a key is "kept out of anything the app writes to disk in
plain text". Until this module the backend broke that rule itself:
token-file.patch made a random token on first run and wrote it to
`~/.openjarvis/token` as plain text, where the desktop app read it back. The
desktop already kept a token typed into its Settings in Credential Manager
(jarvis-desktop/src-tauri/src/token_store.rs); now the backend's own token
lives there too, under TARGET, in the same format (a generic credential, the
token as UTF-8 bytes, saved for this Windows user on this PC). Credential
Manager encrypts it to the signed-in Windows account (DPAPI). The owner can
see and delete it in Control Panel -> Credential Manager -> Windows
Credentials.

What this does NOT change, said plainly: any program running as the same
Windows user can still ask Credential Manager for it, exactly as it could
read the old file. What changes is that it is no longer sitting on disk as
readable text - in a backup, a copied profile folder, a synced folder, or a
file search.

WHAT resolve() DOES, IN ORDER
1. An old `~/.openjarvis/token` file is moved in: written to Credential
   Manager, read back, and deleted only when the read-back matches. If the
   file and Credential Manager disagree, the FILE wins: with this module in
   place the file is never written, so a file that exists was made by the
   old code after the move (for example after `apply-patches.ps1 -Revert`),
   and it is the token the phone was last paired with.
   If Credential Manager cannot be used, the file is left where it is and
   the banner says why - deleting it would unpair the phone.
2. `HUD_TOKEN` in the environment wins, unchanged - someone who set it meant
   it (and the desktop app passes its own token this way when it starts the
   backend).
3. Otherwise the token in Credential Manager.
4. Otherwise a new random one is made and saved there, then read back.
   If Credential Manager refuses, the token is used for this run only and
   NOT written anywhere; the banner says the phone will need pairing again
   after a restart, and how to avoid that (set HUD_TOKEN yourself).

This module never writes a token to any file, never prints or logs one
(except `show`, below, which the owner runs on purpose), and never puts one
in an error message - errors carry the Windows error number only.

FOR THE OWNER, in the backend folder:
    py -3 jarvis_token_store.py show     print the token, to type into the phone
    py -3 jarvis_token_store.py where    say where it is kept (never the token)
    py -3 jarvis_token_store.py forget   delete it; the next start makes a new
                                         one, and every device must pair again
"""

from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# The name it is filed under in Credential Manager. Must match
# BACKEND_TARGET in jarvis-desktop/src-tauri/src/token_store.rs, which reads
# it; test_token_store.py checks the two are the same text.
TARGET = "Jarvis Backend/pairing token"

# Credential Manager's own limit for a generic credential's secret
# (CRED_MAX_CREDENTIAL_BLOB_SIZE).
_MAX_BLOB = 5 * 512

_ERROR_NOT_FOUND = 1168
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2


class StoreError(Exception):
    """Credential Manager said no. Carries the Windows error number, never
    the token."""


class Unavailable(StoreError):
    """There is no Credential Manager here (not Windows)."""


# --------------------------------------------------------- Credential Manager

class WindowsStore:
    """advapi32's CredReadW / CredWriteW / CredDeleteW, through ctypes - the
    standard library, so there is no new package to install or audit. The
    same three calls token_store.rs makes, with the same arguments."""

    def __init__(self, target: str = TARGET):
        if os.name != "nt":
            raise Unavailable("there is no Windows Credential Manager on this system")
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD),
                        ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD),
                        ("Type", wintypes.DWORD),
                        ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR),
                        ("LastWritten", FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD),
                        ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        api = ctypes.WinDLL("advapi32", use_last_error=True)
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        self._ctypes, self._api, self._cred = ctypes, api, CREDENTIALW
        self.target = target

    def read(self) -> Optional[str]:
        c = self._ctypes
        ptr = c.POINTER(self._cred)()
        if not self._api.CredReadW(self.target, _CRED_TYPE_GENERIC, 0, c.byref(ptr)):
            code = c.get_last_error()
            if code == _ERROR_NOT_FOUND:
                return None
            raise StoreError(f"reading failed (Windows error {code})")
        try:
            cred = ptr.contents
            size = int(cred.CredentialBlobSize)
            raw = c.string_at(cred.CredentialBlob, size) if size and cred.CredentialBlob else b""
        finally:
            self._api.CredFree(c.cast(ptr, c.c_void_p))
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise StoreError("the stored token is not valid text") from None
        return text or None

    def write(self, token: str) -> None:
        c = self._ctypes
        data = token.encode("utf-8")
        if len(data) > _MAX_BLOB:
            raise StoreError(f"the token is longer than Credential Manager allows ({_MAX_BLOB} bytes)")
        blob = (c.c_ubyte * len(data)).from_buffer_copy(data)
        cred = self._cred()
        cred.Type = _CRED_TYPE_GENERIC
        cred.TargetName = self.target
        cred.UserName = "jarvis"
        cred.CredentialBlobSize = len(data)
        cred.CredentialBlob = c.cast(blob, c.POINTER(c.c_ubyte))
        cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
        ok = self._api.CredWriteW(c.byref(cred), 0)
        code = c.get_last_error()
        c.memset(blob, 0, len(data))       # do not leave the copy lying about
        if not ok:
            raise StoreError(f"saving failed (Windows error {code})")

    def delete(self) -> bool:
        """True if there was one to delete."""
        c = self._ctypes
        if self._api.CredDeleteW(self.target, _CRED_TYPE_GENERIC, 0):
            return True
        code = c.get_last_error()
        if code == _ERROR_NOT_FOUND:
            return False
        raise StoreError(f"deleting failed (Windows error {code})")


def default_store():
    """The real store, or the reason there is none (a StoreError instance)."""
    try:
        return WindowsStore()
    except StoreError as e:
        return e
    except Exception as e:                       # ctypes itself failed to load
        return StoreError(f"Credential Manager could not be opened ({type(e).__name__})")


# ------------------------------------------------------------------ resolve

@dataclass
class Resolved:
    token: str                 # "" only when there is none at all
    where: str                 # "environment" | "credential-manager" | "old-file" | "this-run-only" | "none"
    made: bool = False         # a new one was made this run
    notes: list = field(default_factory=list)   # plain-English lines, never the token

    def banner(self) -> list:
        """The boot banner's `token` lines. Says where, never what."""
        head = {
            "environment": "from HUD_TOKEN in the environment",
            "credential-manager": f'in Windows Credential Manager, as "{TARGET}"',
            "old-file": "STILL IN THE OLD PLAIN-TEXT FILE (see below)",
            "this-run-only": "NOT SAVED - this run only (see below)",
            "none": "NONE - only this PC can connect",
        }[self.where]
        out = [f"  token      {head}"]
        if self.made and self.where == "credential-manager":
            out.append("             (made on first run; pair the phone with it: the desktop app's")
            out.append("              Settings > Show the token for my phone, or")
            out.append("              py -3 jarvis_token_store.py show  in this folder)")
        out += [f"             {n}" for n in self.notes]
        return out


#: Byte-order marks: the few bytes some editors put at the very start of a
#: text file to say how it is encoded. Windows PowerShell 5.1 writes UTF-16
#: with one by default (`Out-File`, `>`), and UTF-8 with one when asked for
#: `-Encoding UTF8`; Notepad can save either.
_BOMS = ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


def _read_file(path: Path):
    """(token or None, problem or None). Never raises.

    Read as bytes, then decoded by what the file says it is (bug audit 3,
    CONN-5): a UTF-8 byte-order mark is dropped rather than becoming the
    first character of the token, UTF-16 (either byte order) is decoded as
    UTF-16, and anything else must be UTF-8. A file that is none of those is
    a `problem` sentence - it used to be a UnicodeDecodeError that stopped
    the backend from starting at all. Surrounding spaces and line breaks are
    dropped either way."""
    try:
        if not path.is_file():
            return None, None
        raw = path.read_bytes()
    except OSError as e:
        return None, f"the old token file could not be read ({type(e).__name__})"
    codec = "utf-8"
    for bom, name in _BOMS:
        if raw.startswith(bom):
            raw, codec = raw[len(bom):], name
            break
    try:
        text = raw.decode(codec).strip()
    except UnicodeDecodeError:
        return None, (f"the old token file {path} is not UTF-8 or UTF-16 text, so it was "
                      f"ignored and left where it is")
    return (text or None), None


def _remove(path: Path):
    """None, or why it could not be removed. A leftover `.tmp` beside it (the
    old code wrote there first) goes too."""
    problem = None
    for p in (path, path.with_suffix(".tmp")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            problem = f"could not delete {p} ({type(e).__name__})"
    return problem


def resolve(token_file, *, store=None, environ=None,
            make: Callable[[], str] = lambda: secrets.token_urlsafe(32)) -> Resolved:
    """The token the backend should use, and where it lives. See the module
    docstring for the order. `store` defaults to Windows Credential Manager;
    tests pass a stand-in with read/write/delete. Writes no file, ever."""
    token_file = Path(token_file)
    env = os.environ if environ is None else environ
    if store is None:
        store = default_store()
    broken = str(store) if isinstance(store, StoreError) else None
    notes: list = []

    stored = None
    if not broken:
        try:
            stored = store.read()
        except StoreError as e:
            broken = str(e)

    # 1. The old plain-text file, moved in and removed.
    old, problem = _read_file(token_file)
    if problem:
        notes.append(problem + ".")
    kept_old = False
    if old is not None:
        if broken:
            kept_old = True
            notes.append(f"{token_file} is still plain text, because {broken}.")
            notes.append("It was left in place so the phone stays paired.")
        else:
            try:
                if stored != old:
                    store.write(old)
                back = store.read()
            except StoreError as e:
                back, broken = None, str(e)
            if back == old:
                stored = old
                gone = _remove(token_file)
                notes.append(f"moved out of the plain-text file {token_file}" +
                             (f" - but {gone}; delete it by hand." if gone else ", which was deleted."))
            else:
                kept_old = True
                why = broken or "the copy read back from Credential Manager did not match"
                notes.append(f"{token_file} is still plain text, because {why}.")
                notes.append("It was left in place so the phone stays paired.")

    # 2. The environment wins.
    from_env = env.get("HUD_TOKEN", "").strip()
    if from_env:
        return Resolved(from_env, "environment", notes=notes)

    # 3. The old file, when it could not be moved (it wins, as in step 1),
    # then what Credential Manager holds.
    if kept_old:
        return Resolved(old, "old-file", notes=notes)
    if stored:
        return Resolved(stored, "credential-manager", notes=notes)

    # 4. A new one.
    try:
        made = make()
    except Exception:
        notes.append("a new token could not be made.")
        return Resolved("", "none", notes=notes)
    if not broken:
        try:
            store.write(made)
            if store.read() == made:
                return Resolved(made, "credential-manager", made=True, notes=notes)
            broken = "the copy read back from Credential Manager did not match"
        except StoreError as e:
            broken = str(e)
    notes.append(f"It could not be saved, because {broken}.")
    notes.append("Nothing was written to disk. The phone will need pairing again after every")
    notes.append("restart - or set HUD_TOKEN yourself to keep one token.")
    return Resolved(made, "this-run-only", made=True, notes=notes)


# ---------------------------------------------------------------- the owner

def _main(argv) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd not in ("show", "where", "forget"):
        print(__doc__.split("FOR THE OWNER", 1)[1].split('"""', 1)[0].strip("\n: "))
        return 2
    store = default_store()
    if isinstance(store, StoreError):
        print(f"Cannot reach Credential Manager: {store}")
        return 1
    try:
        if cmd == "forget":
            had = store.delete()
            print('Deleted. The next start makes a new token; pair every device again.'
                  if had else "There was no saved token.")
            return 0
        tok = store.read()
    except StoreError as e:
        print(f"Credential Manager refused: {e}")
        return 1
    if tok is None:
        print("There is no saved token yet. Start Jarvis once and it makes one.")
        return 1
    if cmd == "where":
        print(f'Windows Credential Manager > Windows Credentials > "{TARGET}"')
    else:
        print(tok)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
