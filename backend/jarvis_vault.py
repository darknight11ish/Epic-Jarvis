"""jarvis_vault.py - a blind credential vault: the model handles a NAME, never
a value.

WHY THIS EXISTS

CLAUDE.md rule 3 lets an API key live in the app, on the same terms the pairing
token already gets: never logged, sent only to the one service it
authenticates against, and kept out of anything the app writes to disk in plain
text. Today the second half of that is already done - `jarvis_token_store` and
`jarvis_search.KEY_TARGETS` put every key in Windows Credential Manager, and
`jarvis_note_store`-style plain files are refused. What was missing is the
FIRST half at the point of use: a module that needs a key calls `_key()` and
holds the real string from that moment on, so the value is one `repr()` away
from a log line, an audit detail, an error message or a returned payload.

This module is the other way round. A caller writes a HANDLE where the value
goes:

    {"x-api-key": "{{vault:exa}}"}

and the real value is put in exactly once, at exactly one place - the line
that builds the outbound request - by `resolve()`. Anything that comes back
goes through `redact()`, which runs the project's own scrubber
(`jarvis_scrub`) over it, so a service that echoes the key back cannot leak it
into a tool result, an event payload or a log line.

The shape is borrowed from Meta's Muse and from the blind-credential-handle
idea generally: the model, the prompt, the card, the audit line and the event
all carry the NAME. Only the socket sees the value.

WHAT THIS IS NOT

  * NOT a second key store. `put()` writes to Windows Credential Manager
    through `jarvis_token_store.WindowsStore`, the same store, the same format
    and the same ctypes calls the pairing token and the Exa/Tavily/Brave/DeepSeek keys
    already use. There is no new mechanism here to keep in step with the old
    one; there is one mechanism, used one level up.
  * NOT a replacement for `jarvis_scrub`. `redact()` calls it. The scrubber
    owns "what does a secret look like"; this module owns "which named value
    did this turn actually use", which the scrubber cannot know.
  * NOT a log redactor. docs/ARCHITECTURE.md section 3 - redaction is
    per-destination - and `jarvis_gate._redact` still owns the audit log. What
    this module does is stop the value being in the thing that is logged.
  * NOT persistent metadata. The secret values are in Credential Manager; the
    names, which host each is bound to and when each was last used are in
    `<config folder>/vault.json`. That file never holds a value: the name of a
    credential is not the credential.

THE API

    put(name, value, for_host="")   store one value; False if it was refused
    get(name)                       the value, or None - for the moment of use
    handles()                       [{name, for_host, last_used}] - never a value
    resolve(text, host=None)        replace {{vault:name}} once, at point of use
    redact(text)                    put used values back behind their handles,
                                    then run the project's scrubber over it
    status()                        what the apps read - counts, never values

`resolve()` is bounded on purpose. A handle resolves only when the host the
value is bound to matches the host it is being resolved for, so a key saved for
one service cannot be substituted into a request to another: rule 3's "sent
only to the one service it authenticates against" is a property of this
function, not of every caller remembering. With no host given, a handle bound
to a host does not resolve at all - it fails closed.

WHAT `put()`/`get()` NEVER DO

Never log, never raise into the caller, never write a value into an audit line.
An audit line carries the NAME (`vault.put`, `{"name": ...}`) and nothing else.
Credential Manager refuses, there is no Credential Manager (this is not
Windows), the name is not a name - each is a `False` and a plain sentence in
`status()["why"]`, never a value in an exception.

Standard library only. Opens no socket, starts no process, and imports nothing
from the backend at module load.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = ["put", "get", "forget", "handles", "resolve", "redact", "status",
           "handle", "names_in", "HANDLE_RE", "PREFIX", "install", "headers_of"]

#: A vault name inside a header value, or anywhere else a string is built:
#: `{{vault:github}}`. The name is short and plain on purpose - it is a key
#: into a store, not a place to smuggle text (the same rule
#: jarvis_browser_control._SECRET_RE makes for `<secret>name</secret>`).
_VALUE = r"\{\{vault:([A-Za-z0-9_.\-]{1,64})\}\}"
HANDLE_RE = re.compile(_VALUE)

#: The one function that writes a handle. There is no second spelling, so a
#: caller cannot invent `{{vault: x}}` and silently get nothing.
def handle(name: str) -> str:
    """The handle for `name`, as it goes in a string. "" for a name that is
    not a name - an invalid handle is better than a wrong one."""
    n = _clean_name(name)
    return f"{{{{vault:{n}}}}}" if n else ""

#: The name a Credential Manager entry is filed under. Same shape as
#: jarvis_search.KEY_TARGETS ("Jarvis Backend/<name> key"), one namespace per
#: vault entry so two names cannot collide with an existing secret's target.
PREFIX = "Jarvis Backend/vault/"

#: Credential Manager's own limit for a generic credential's secret
#: (CRED_MAX_CREDENTIAL_BLOB_SIZE), the same number jarvis_token_store uses.
MAX_VALUE = 5 * 512
#: A name, a host name and the whole JSON document are all small.
MAX_NAME = 64
MAX_HOST = 253

#: The value is never in here. This sentence is what the apps show when the
#: config folder cannot be written.
_WHY_UNREADABLE = ("the vault's own list of names could not be read, so the names saved "
                   "in it are not being used. Add a secret again to rewrite it. No value "
                   "was ever in that file.")

_LOCK = threading.Lock()

#: name -> the epoch seconds it was last used IN THIS RUN. Never written: a
#: restart with no use is "not used yet", which is the truth worth showing.
_USED: dict = {}

#: name -> the value, for the values this process has actually handed out.
#: In memory only, for `redact()` - so putting a returned payload back behind
#: its handle does not have to read Credential Manager again (and does not
#: register the value a second time). It is the same lifetime the scrubber's
#: own `register_secret` has, and `_reset_for_tests` empties it.
_VALUES: dict = {}

#: Tests replace this with a factory of stand-in stores: target -> object with
#: read()/write(value)/delete(). The same shape jarvis_search._STORE_FACTORY
#: and jarvis_token_store._STORE_FACTORY already use.
_STORE_FACTORY: Optional[Callable[[str], object]] = None

#: Tests set this True. While it is set, `_store()` never reaches the REAL
#: Windows Credential Manager: it returns `_store_error()` instead.
#:
#: WHY THIS EXISTS, said plainly, because it already happened once: the first
#: version of backend/test_vault.py tested "a PC with no Credential Manager" by
#: setting `_STORE_FACTORY = None`, which makes `_store()` fall through to the
#: real store - and on the owner's own Windows PC the real store works. The
#: suite then wrote a REAL credential, under "Jarvis Backend/vault/github",
#: into the owner's live Credential Manager (deleted again the same minute).
#: A guard in the module is the fix that does not depend on every future test
#: author remembering.
TESTING = False

#: Tests replace this: (event, detail) -> None, the project's audit log. The
#: default imports jarvis_framework lazily, so importing this module is free.
_AUDIT: Optional[Callable[[str, dict], None]] = None


# --------------------------------------------------------------------------
#   Names, hosts and the document that holds them (never a value)
# --------------------------------------------------------------------------

def _clean_name(name: Any) -> str:
    n = str(name if name is not None else "").strip()
    if not n or len(n) > MAX_NAME or not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", n):
        return ""
    return n


def _clean_host(host: Any) -> str:
    """A host name, lower-cased, with no scheme, port or path. "" means "not
    bound to one", which is not the same as "bound to anything" - see resolve."""
    h = str(host if host is not None else "").strip().lower()
    if not h or len(h) > MAX_HOST:
        return ""
    if not re.fullmatch(r"[a-z0-9]([a-z0-9.\-]*[a-z0-9])?", h):
        return ""
    return h


def _config_dir() -> Path:
    """The same folder the rest of the backend uses, found the same way
    (jarvis_search._config_dir, which jarvis_accounts.py also mirrors - these
    files sit side by side)."""
    fw = sys.modules.get("jarvis_framework")
    if fw is None:
        try:
            import jarvis_framework as fw  # type: ignore
        except Exception:
            fw = None
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def vault_path() -> Path:
    return _config_dir() / "vault.json"


def _read() -> tuple:
    """(the document as a dict, why it could not be used). ({},"") when there
    is no file at all. A document is {"names": {name: {"for_host": ...,
    "used": <epoch>}}} - names and times, never a value."""
    try:
        raw = vault_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, ""
    except OSError:
        return {}, _WHY_UNREADABLE
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
        names = doc.get("names")
        if names is not None and not isinstance(names, dict):
            raise ValueError
    except Exception:
        return {}, _WHY_UNREADABLE
    return doc, ""


def _names() -> dict:
    doc, _why = _read()
    names = doc.get("names")
    return names if isinstance(names, dict) else {}


def _remember(name: str, *, for_host: str = "", used: float = 0.0) -> bool:
    """Add or update one row. True when the file was written. NEVER raises and
    never carries a value: what is written is a name, a host and a time.

    A row is only ever written when Credential Manager is usable here. A row
    for a value that is not in the store would be a name the owner never saved,
    shown by `handles()` and refused by `get()` - and off Windows there is no
    store at all, so the vault keeps NO name, which is the honest state."""
    try:
        if isinstance(_store(name), Exception):
            return False
        with _LOCK:
            doc, _why = _read()
            names = doc.get("names")
            names = dict(names) if isinstance(names, dict) else {}
            row = names.get(name)
            row = dict(row) if isinstance(row, dict) else {}
            if for_host:
                row["for_host"] = for_host
            if used:
                row["used"] = float(used)
            names[name] = row
            doc["names"] = names
            doc["changed"] = time.time()
            path = vault_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, path)
        return True
    except Exception:
        return False


def _forget_row(name: str) -> None:
    try:
        with _LOCK:
            doc, _why = _read()
            names = doc.get("names")
            if not isinstance(names, dict) or name not in names:
                return
            names = dict(names)
            names.pop(name, None)
            doc["names"] = names
            doc["changed"] = time.time()
            path = vault_path()
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, path)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The store - Windows Credential Manager, through jarvis_token_store
# --------------------------------------------------------------------------

def _store(name: str):
    """The store for one name, or the reason there is none. A StoreError
    instance is a value here, exactly as jarvis_token_store.default_store
    returns one - the caller checks, so nothing raises into a route."""
    target = PREFIX + name
    if _STORE_FACTORY is not None:
        try:
            return _STORE_FACTORY(target)
        except Exception as exc:
            return exc
    if TESTING:
        # Never the real Credential Manager while a suite is running - see
        # TESTING's own comment for the incident this prevents.
        return _store_error(target, "a suite must not reach the real credential store")
    try:
        import jarvis_token_store as T
    except Exception as exc:
        return exc
    try:
        return T.default_store(target)
    except Exception as exc:
        return exc


def _why_no_store() -> str:
    return ("Windows Credential Manager cannot be used on this PC, so no secret can be "
            "kept here. The vault refuses to store rather than write a key to a plain "
            "file (CLAUDE.md rule 3).")


def _store_error(target: str, why: str = "") -> Exception:
    """The "there is no store" value, in the project's own exception type when
    jarvis_token_store is here (`Unavailable`, exactly what its WindowsStore
    raises off Windows; `StoreError` for any other refusal) and a plain
    RuntimeError when it is not. Public because a suite needs to build one to
    stand in for a PC with no Credential Manager WITHOUT reaching the real
    store."""
    try:
        import jarvis_token_store as T
        return (T.StoreError(why) if why else
                T.Unavailable("there is no Windows Credential Manager on this system"))
    except Exception:
        return RuntimeError(why or "there is no credential store here")


def _audit(event: str, detail: dict) -> None:
    """Counts and names only. NEVER a value.

    The default imports jarvis_framework lazily and swallows every error: an
    audit line that cannot be written must not stop a secret being saved, and
    must never be the reason one is printed instead."""
    fn = _AUDIT
    if fn is not None:
        try:
            fn(event, detail)
            return
        except Exception:
            return
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


def _register_with_scrubber(value: str) -> None:
    """Hand the value to the project's scrubber, so it is hidden BY VALUE
    wherever it might appear for the rest of this run. Only ever called for a
    value this module read out of the store: the scrubber's own rule is that a
    value kept in plain text somewhere else (an environment variable) is left
    to its name-based scan instead. Never raises."""
    try:
        import jarvis_scrub
        jarvis_scrub.register_secret(value)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   put / get / forget - the three that touch a value
# --------------------------------------------------------------------------

def put(name: str, value: Any, *, for_host: str = "") -> bool:
    """Save one value under one name. True when it is in Credential Manager and
    reads back the same; False - never an exception - otherwise.

    Nothing is written unless the store accepted the value AND handed it back
    identical: a store that silently truncates a key must not look like a
    successful save. The value is never logged, never returned, never put in an
    audit line and never written to any file. The audit line carries the NAME.

    It is also a `False`, with the store entry removed again, when the HOST
    BINDING could not be written down: `resolve()` reads that binding back out
    of the document, so a value the vault cannot confine to one host is a value
    that would resolve for ANY host. Half a save is not a save; it is refused.
    """
    n = _clean_name(name)
    if not n:
        _audit("vault.put_refused", {"why": "the name is not a vault name"})
        return False
    v = value if isinstance(value, str) else ("" if value is None else str(value))
    if not v:
        _audit("vault.put_refused", {"name": n, "why": "empty"})
        return False
    if len(v.encode("utf-8", "replace")) > MAX_VALUE:
        _audit("vault.put_refused", {"name": n, "why": "too long"})
        return False
    st = _store(n)
    if isinstance(st, Exception):
        _audit("vault.put_refused", {"name": n, "why": "no store"})
        return False
    try:
        st.write(v)
        back = st.read()
    except Exception:
        # The exception's NAME only: some carry the value they were given.
        _audit("vault.put_refused", {"name": n, "why": "the store refused"})
        return False
    if (back if isinstance(back, str) else "") != v:
        _audit("vault.put_refused", {"name": n, "why": "read back did not match"})
        return False
    host = _clean_host(for_host)
    if not _remember(n, for_host=host):
        # The row written here is the ONLY thing that keeps this value to the
        # one service it authenticates against - `resolve()` reads it back out
        # of the document - and a value sitting in the store without one
        # resolves for ANY host. So a binding that could not be written is not
        # a partial save: the store entry goes back out, `_VALUES` is emptied so
        # `redact()` holds no copy of it either, and this is a refusal, which is
        # what the caller is told. On the NAME only - never the value, never its
        # length, never a prefix of it.
        try:
            st.delete()
        except Exception:
            pass
        with _LOCK:
            _VALUES.pop(n, None)
        _audit("vault.put_refused",
               {"name": n, "why": "the vault's own list of names could not be written"})
        return False
    _register_with_scrubber(v)
    with _LOCK:
        _VALUES[n] = v
    # The NAME. Never the value, never a length, never a prefix of it.
    _audit("vault.put", {"name": n, "for_host": host})
    return True


def get(name: str) -> Optional[str]:
    """The value saved under `name`, or None. NEVER raises, never logs.

    This is the one function that hands a value out. Its caller is the point of
    use - the line that builds the one outbound request that authenticates with
    it - and nothing else should call it: everything else carries the handle and
    goes through `resolve()`.
    """
    n = _clean_name(name)
    if not n:
        return None
    st = _store(n)
    if isinstance(st, Exception):
        return None
    try:
        value = st.read()
    except Exception:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    _register_with_scrubber(value)
    with _LOCK:
        _VALUES[n] = value
    _note_used(n)
    _audit("vault.get", {"name": n})
    return value


def forget(name: str) -> bool:
    """Delete one value. True when one was there to delete.

    Not named in the brief's API, and added because a vault nobody can empty is
    a vault that fills with dead keys. It deletes through the same store and
    writes the same NAME-only audit line. No route calls it: emptying a
    credential is the owner's own act, like `jarvis_search.py forget-key`.
    """
    n = _clean_name(name)
    if not n:
        return False
    st = _store(n)
    if isinstance(st, Exception):
        return False
    try:
        had = bool(st.delete())
    except Exception:
        return False
    if had:
        _forget_row(n)
        with _LOCK:
            _USED.pop(n, None)
        _audit("vault.forget", {"name": n})
    return had


# --------------------------------------------------------------------------
#   handles / resolve / redact - what the rest of the system uses
# --------------------------------------------------------------------------

def _note_used(name: str) -> None:
    """When this name was last used, in memory for the rest of this run and in
    the document so the apps can say it after a restart. A TIME only: the
    document still holds no value.

    `for_host=""` on purpose - the binding `put()` wrote is NOT the thing being
    changed here, and passing one would rewrite it to empty."""
    at = time.time()
    with _LOCK:
        _USED[name] = at
    _remember(name, used=at)


def _last_used(name: str) -> float:
    """This run's use, else the last one recorded in the document, else 0.0."""
    with _LOCK:
        run = float(_USED.get(name) or 0.0)
    row = _names().get(name)
    saved = float(row.get("used") or 0.0) if isinstance(row, dict) else 0.0
    return max(run, saved)


def handles() -> list:
    """Every name the vault holds, with the host it is bound to and when it was
    last used. NEVER a value and never a masked prefix of one.

    The names come from the document, not from the store: asking Credential
    Manager to enumerate is a different ctypes call this project does not make
    yet, and a name whose entry the owner deleted by hand is worth showing as
    "no value" rather than hiding."""
    rows = []
    for name, row in sorted(_names().items()):
        n = _clean_name(name)
        if not n:
            continue
        st = _store(n)
        has = False
        if not isinstance(st, Exception):
            try:
                has = bool(st.read())
            except Exception:
                has = False
        rows.append({
            "name": n,
            "handle": handle(n),
            "for_host": (_clean_host(row.get("for_host")) if isinstance(row, dict) else ""),
            "last_used": _last_used(n),
            "has_value": has,
        })
    return rows


def names_in(text: Any) -> list:
    """Every vault name named by a handle in `text`, in order, without repeats.
    The same shape jarvis_browser_control._secret_names has for `<secret>`."""
    if not isinstance(text, str):
        return []
    seen, out = set(), []
    for n in HANDLE_RE.findall(text):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def resolve(text: Any, *, host: Any = None) -> str:
    """`text` with every `{{vault:name}}` replaced by the value it names,
    exactly once, at the point of use.

    * No handle at all: the text is returned unchanged, and the store is never
      asked. That is the common case and it costs one regex.
    * A handle that names nothing, or a value the store will not hand over:
      left as the literal handle. Failing to a placeholder the caller can see
      beats failing to an empty string that quietly authenticates wrong.
    * The document of names could not be READ - unreadable, or present but
      corrupt: NOTHING resolves, whatever host is named. A binding that cannot
      be read is not the same thing as no binding, and substituting anyway is
      how a key saved for one service reaches a request to another. This is
      what `_read()`'s own reason is kept for; `_names()` throws it away.
    * A handle bound to a host resolves ONLY for that host (`host=` the host
      the request is going to). A handle bound to a host that is not given, or
      given as another host, does NOT resolve: rule 3's "sent only to the one
      service it authenticates against" is enforced here, so no caller has to
      remember it. A handle with no host bound resolves anywhere.
    * A value is substituted literally. A `$` or a backslash in a key is a
      character, not a group reference - there is no second parse of it.

    Never raises.
    """
    try:
        s = "" if text is None else (text if isinstance(text, str) else str(text))
        if "{{vault:" not in s:
            return s
        want = _clean_host(host)
        # `_read()` says WHY it could not be used, and that is not the same
        # thing as "no binding": a document that cannot be read may well hold a
        # host binding, and substituting anyway would send a key saved for one
        # service to whatever host this call happens to name. Unreadable
        # therefore means NO substitution at all - the handle travels and the
        # service refuses it, which is a visible failure rather than a silent
        # wrong destination.
        doc, why = _read()
        names = doc.get("names")
        bound = names if isinstance(names, dict) else {}

        def one(m) -> str:
            name = m.group(1)
            if why:
                _audit("vault.resolve_refused",
                       {"name": name, "why": "the name list could not be read"})
                return m.group(0)
            row = bound.get(name)
            bound_host = _clean_host(row.get("for_host")) if isinstance(row, dict) else ""
            if bound_host and bound_host != want:
                _audit("vault.resolve_refused", {"name": name, "why": "another host"})
                return m.group(0)
            value = get(name)
            if value is None:
                _audit("vault.resolve_missing", {"name": name})
                return m.group(0)
            return value

        return HANDLE_RE.sub(one, s)
    except Exception:
        # A value substituted is a value in the text; nothing here may be the
        # reason it comes back out un-redacted, so a failure returns the text
        # with its handles still in it.
        return "" if text is None else (text if isinstance(text, str) else str(text))


def redact(text: Any, *, used: Any = None) -> str:
    """Anything that comes back, made safe to return.

    Two steps, in this order:
      1. every value this module has handed out (or that the caller names in
         `used`, a {name: value} mapping like jarvis_browser_control.run's)
         is put back behind its own handle - longest first, so a value that
         contains another cannot leak a piece of it;
      2. the project's own scrubber (`jarvis_scrub.scrub_text`) runs over the
         result, which is the layer that catches a credential this module has
         never seen and any shape that looks like one.

    It is a string in and a string out, and it never raises: a value that
    cannot be redacted makes the whole text WITHHELD rather than passed
    through. The same rule jarvis_scrub itself follows.
    """
    try:
        s = "" if text is None else (text.decode("utf-8", "replace")
                                     if isinstance(text, bytes) else str(text))
        if not s:
            return s
        pairs: dict = {}
        if isinstance(used, dict):
            for k, v in used.items():
                if v:
                    pairs[str(v)] = _clean_name(k) or str(k)
        with _LOCK:
            for name, value in _VALUES.items():
                if value:
                    pairs.setdefault(value, name)
        if pairs:
            for value in sorted(pairs, key=len, reverse=True):
                if value and value in s:
                    s = s.replace(value, handle(pairs[value]) or "[redacted: a vault value]")
        try:
            import jarvis_scrub
            return jarvis_scrub.scrub_text(s)
        except Exception:
            return s
    except Exception:
        return "[redacted: text withheld - the vault could not clean it]"


# --------------------------------------------------------------------------
#   status - what the apps read
# --------------------------------------------------------------------------

def status() -> dict:
    """Counts and plain words, never a value and never part of one."""
    st = _store("probe-status-only")
    usable = not isinstance(st, Exception)
    _doc, why = _read()
    rows = handles()
    return {
        "available": usable,
        "why": why or ("" if usable else _why_no_store()),
        "handle_prefix": "{{vault:",
        "names": len(rows),
        "with_value": sum(1 for r in rows if r["has_value"]),
        "used_this_run": len(_USED),
        "bound": sum(1 for r in rows if r["for_host"]),
        "file": str(vault_path()),
        "note": ("names, the host each is bound to and when each was used live in this "
                 "file; the values are in Windows Credential Manager and are never "
                 "written here"),
    }


# --------------------------------------------------------------------------
#   The routes - GET /api/vault/handles, POST /api/vault/put
# --------------------------------------------------------------------------

class _Headers:
    """An http.client-style view of a prepared request's headers, so the one
    outbound line does not have to know which library built the request.

    WHY THIS EXISTS, said plainly: the obvious `req.headers` returns
    urllib.request's OWN dict, and `Request.add_unredirected_header` writes to
    `unredirected_hdrs` instead - so a substitution checked through
    `req.headers` reads back the handle, not the value, and a caller can
    believe it works while nothing was substituted. This view reads what
    `urllib` WILL ACTUALLY SEND, which is the two dicts with `unredirected_hdrs`
    winning - exactly `AbstractHTTPHandler.do_request_`'s own rule."""

    def __init__(self, req):
        self._req = req
        self._items = []
        for source in (getattr(req, "headers", None),
                       getattr(req, "unredirected_hdrs", None)):
            for key, value in (source or {}).items():
                self._set(key, value)

    def _set(self, key, value):
        for i, (k, _v) in enumerate(self._items):
            if k.lower() == str(key).lower():
                self._items[i] = (k, value)
                return
        self._items.append((str(key), value))

    def items(self):
        return list(self._items)

    def get(self, key, default=None):
        for k, v in self._items:
            if k.lower() == str(key).lower():
                return v
        return default

    def __iter__(self):
        return iter(self.items())

    def __contains__(self, key):
        return self.get(key, None) is not None

    def set(self, key, value):
        """Put the real value on the request, in the dict urllib really sends."""
        self._set(key, value)
        try:
            self._req.add_unredirected_header(str(key), value)
        except Exception:
            pass


def _headers_of(req):
    """`_Headers` for a urllib Request; whatever it has, for anything else."""
    if hasattr(req, "add_unredirected_header") or hasattr(req, "unredirected_hdrs"):
        return _Headers(req)
    return getattr(req, "headers", {}) or {}


#: The public name a caller reaches the view by. Same function - the underscore
#: one exists so the class can be read first.
headers_of = _headers_of


PATH = "/api/vault/handles"
PUT_PATH = "/api/vault/put"

#: The gate action POST /api/vault/put is asked under. `[autonomy.tiers]` gives
#: it "ask" - a line of its own since 2026-10-16, and the `unknown_action_tier`
#: fall-through it took before that is also "ask", so the card is unchanged. It
#: has no `_RISK` row, so that card stays the gate's own heavy one, risk
#: ("no", "outbound"). The route refuses anything that is not tier "ask" (see
#: _card_says_yes), so neither a later loosening of `unknown_action_tier` nor an
#: edited tier line can make this store a value unasked.
ACTION_PUT = "vault_put"

#: What the card says. Written here, never assembled from the body.
CARD_TITLE = "Jarvis wants to keep an API key or password for you"
CARD_WHY = ("A secret is kept in Windows Credential Manager, under a NAME. Jarvis then "
            "uses the NAME everywhere and the real value only in the one request that "
            "authenticates with it. Say no and nothing is stored.")

#: The plain words per outcome. `denied`, `timed_out` and `refused` all mean the
#: same thing to the owner: nothing was stored.
LAST_WORDS = {
    "stored": "Saved. Jarvis will use the name, never the value.",
    "denied": "Nothing was stored - you said no.",
    "timed_out": "Nothing was stored - the card timed out.",
    "refused": "Nothing was stored.",
    "failed": "Nothing was stored - something went wrong on the PC.",
}

#: How long the route waits for the gate, ON TOP of the gate's own deadline.
#: The gate stops waiting at `approval_timeout_seconds` (600 as shipped) and
#: answers timed_out; this only covers the moment between that and the thread
#: returning its verdict.
_WAIT_AFTER_GATE = 30.0

#: What the gate waits when its own setting cannot be read. The shipped
#: `approval_timeout_seconds` - `backend/test_approval_contract.py:60` says
#: "2026-10-13: 180 -> 600, ten minutes".
_GATE_TIMEOUT_FALLBACK = 600.0


def _gate_timeout() -> float:
    """How long jarvis_gate.check() will wait, read FROM the gate.

    Not a number of this module's own: the whole point is that this route must
    not give up before the card does, so that a person who takes their time and
    then says yes is obeyed rather than told "nothing was stored" for an answer
    they did give. Falls back to the shipped value when the gate is not here -
    and the vault only ever runs on a backend that has one."""
    try:
        import jarvis_gate
        seconds = float(getattr(jarvis_gate, "APPROVAL_TIMEOUT", 0) or 0)
        return seconds if seconds > 0 else _GATE_TIMEOUT_FALLBACK
    except Exception:
        return _GATE_TIMEOUT_FALLBACK


def _gate(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing CLOSED on any error - the same shape
    jarvis_sky._gate and jarvis_forget_range._gate use. The gate module is
    written by a patch and is not in this repository, so it may not be there at
    all: a route that cannot ask a person must not store anything."""
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier_of(action: str) -> str:
    try:
        import jarvis_framework as fw
        return str(fw.action_tier(action))
    except Exception:
        return "ask"


def _person_said_yes(v) -> bool:
    """A person's yes, and nothing weaker. `allowed` alone is not that:
    jarvis_gate.check() returns allowed=True on tier `notify` with nobody
    asked. The tier must BE "ask" and the outcome must be "approved" - the
    same test jarvis_sky._person_said_yes makes."""
    if getattr(v, "allowed", False) is not True:
        return False
    if getattr(v, "tier", None) != "ask":
        return False
    outcome = getattr(v, "outcome", None)
    return outcome == "approved"


def _card_says_yes(body: dict, gate, tier_of, spawn) -> tuple:
    """(True, "") only on a person's yes. (False, outcome) otherwise.

    The card is raised on a thread of its own, because jarvis_gate.check() has
    its own signature and its own waiting loop and the route needs to be able
    to put a deadline on it. THIS CALL DOES BLOCK THE REQUEST until the card is
    answered or the gate gives up - the same as every other route whose action
    waits for a person, and said plainly here rather than described as
    non-blocking.

    The deadline is the GATE'S OWN, read from it, plus `_WAIT_AFTER_GATE`
    seconds. A shorter deadline of this module's own was a real bug in the
    first draft (300 seconds, written before anyone checked): the gate waits
    `approval_timeout_seconds`, TEN MINUTES as shipped, so an owner who read
    the card for six minutes and then approved it met a route that had already
    given up and reported "nothing was stored" - a no that was never said.
    """
    name = str(body.get("name") or "")
    detail = {
        "what": "keep a secret in the vault under a name, in Windows Credential Manager",
        "name": name,
        "for_host": _clean_host(body.get("for_host")),
        "text": CARD_TITLE,
        "card": f"{CARD_TITLE}\n\n{CARD_WHY}\n\nName: {name}",
        "leaves_this_pc": False,
    }
    box: dict = {}

    def ask() -> None:
        try:
            box["verdict"] = gate(ACTION_PUT, detail, detail["card"])
        except Exception as exc:
            box["error"] = type(exc).__name__

    try:
        spawn(ask)
    except Exception:
        return False, "refused"
    deadline = time.time() + _gate_timeout() + _WAIT_AFTER_GATE
    while "verdict" not in box and "error" not in box and time.time() < deadline:
        time.sleep(0.02)
    if "error" in box or "verdict" not in box:
        return False, "refused"
    v = box["verdict"]
    if not _person_said_yes(v):
        outcome = getattr(v, "outcome", None)
        return False, outcome if outcome in ("denied", "timed_out") else "refused"
    if tier_of(ACTION_PUT) != "ask":
        # The gate answered a person's yes at some other tier, which means the
        # tier is no longer the one this route was written for. Refuse.
        return False, "refused"
    return True, ""


def handle_handles() -> tuple:
    """GET /api/vault/handles - the names, and when each was last used.

    Never a value, never a masked prefix of one, never a length."""
    try:
        st = status()
    except Exception as exc:
        return 503, {"available": False, "error": type(exc).__name__}
    return 200, {"available": bool(st.get("available")),
                 "why": st.get("why", ""),
                 "note": st.get("note", ""),
                 "handles": handles()}


def handle_put(body, *, gate=None, tier_of=None, spawn=None) -> tuple:
    """POST /api/vault/put - ONE secret, after ONE approval card at tier `ask`.

    Body: {"name": "github", "value": "...", "for_host": "api.github.com"}.

    The value is never echoed back, never in the answer to a refusal, and never
    in the audit line. A denied, timed-out or refused card stores nothing -
    nothing is stored before the answer either, because `put()` is not reached
    until the card has been decided.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "the request must be a JSON object",
                     "message": LAST_WORDS["refused"]}
    name = _clean_name(body.get("name"))
    if not name:
        return 400, {"ok": False,
                     "error": ("a vault name is 1 to 64 plain characters - letters, "
                               "digits, dot, dash or underscore"),
                     "message": LAST_WORDS["refused"]}
    value = body.get("value")
    if not isinstance(value, str) or not value.strip():
        return 400, {"ok": False, "error": "the value must be text",
                     "message": LAST_WORDS["refused"]}
    if len(value.encode("utf-8", "replace")) > MAX_VALUE:
        # Checked HERE, before the card: a card for something that cannot be
        # stored is a card that wastes the owner's decision.
        return 400, {"ok": False,
                     "error": (f"a secret longer than {MAX_VALUE} bytes is more than "
                               f"Windows Credential Manager will hold"),
                     "message": LAST_WORDS["refused"]}
    host = _clean_host(body.get("for_host"))
    gate = gate or _gate
    tier_of = tier_of or _tier_of
    spawn = spawn or _spawn
    try:
        yes, outcome = _card_says_yes({"name": name, "for_host": host},
                                      gate, tier_of, spawn)
    except Exception:
        yes, outcome = False, "refused"
    if not yes:
        code = 403 if outcome in ("denied", "timed_out") else 503
        # The NAME is fine to repeat - it is on the card the owner read. The
        # value is not in this answer and never was.
        return code, {"ok": False, "name": name, "outcome": outcome,
                      "error": "nothing was stored", "message": LAST_WORDS.get(outcome, "")}
    ok = put(name, value, for_host=host)
    if not ok:
        return 503, {"ok": False, "name": name, "outcome": "failed",
                     "error": "Windows Credential Manager refused, so nothing was stored",
                     "message": LAST_WORDS["failed"]}
    return 200, {"ok": True, "name": name, "handle": handle(name),
                 "for_host": host, "outcome": "stored",
                 "message": LAST_WORDS["stored"]}


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-vault-card", daemon=True).start()


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so /api/vault/handles and
    /api/vault/put are answered here, after the server's own origin and token
    checks. Every other request goes straight to the original - the same shape
    jarvis_card_summary.install and jarvis_sky.install use."""
    from urllib.parse import urlsplit

    get0, post0 = handler_cls.do_GET, handler_cls.do_POST

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_handles()
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PUT_PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"ok": False, "error": type(exc).__name__})
        try:
            code, out = handle_put(body)
        except Exception as exc:
            # The exception's NAME only. A value may be inside it.
            code, out = 503, {"ok": False, "outcome": "failed",
                              "error": type(exc).__name__,
                              "message": LAST_WORDS["failed"]}
        return self._send(code, out)

    do_GET._jarvis_vault = True
    do_POST._jarvis_vault = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    s = status()
    return (f"  vault      Secrets by name"
            + (f": {s['names']} name(s) known" if s["names"] else ": none saved yet")
            + ("" if s["available"] else " (no Credential Manager on this PC - it refuses to store)"))


def _reset_for_tests() -> None:
    global _STORE_FACTORY, _AUDIT
    with _LOCK:
        _USED.clear()
        _VALUES.clear()
    _STORE_FACTORY = None
    _AUDIT = None
