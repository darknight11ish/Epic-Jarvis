"""A stand-in IMAP server, in memory, that behaves the way the real ones are
documented to - and that FAILS LOUDLY when the code under test does the one
thing inbox tidy must never do.

Not a test (no `test_` prefix); test_inbox_tidy.py imports it. It speaks
imaplib's own Python interface (`uid()`, `select()`, `list()`, ...), not the
wire, so what is proved is the sequence of IMAP commands jarvis_inbox_tidy
sends and what each does to a mailbox, not the bytes.

What it models
  * Folders, each with a UIDVALIDITY and its own UIDs. A message lives in
    one folder (ordinary servers: COPY makes a new message, MOVE moves it),
    or carries several labels at once (Gmail: `gmail=True`, where COPY adds
    a label and X-GM-LABELS adds and removes them).
  * The capabilities the server admits to (MOVE, UIDPLUS, X-GM-EXT-1) - a
    command it did not admit to answers BAD, as a real one would.
  * FLAGS, and BODY.PEEK never setting \\Seen (a plain BODY[...] would).
  * A read-only folder (EXAMINE) refusing every change.

What it treats as a bug in the caller (raises AssertionError, and records it)
  * a plain EXPUNGE, or CLOSE: either can permanently remove every message
    marked \\Deleted in the folder, including ones the owner marked;
  * `UID EXPUNGE` of a message that has no other copy anywhere - the only
    way a "move" can lose an email;
  * `UID EXPUNGE` of a message that is not marked \\Deleted.
"""
from __future__ import annotations

import re

SEEN, FLAGGED, DELETED = "\\Seen", "\\Flagged", "\\Deleted"


class Msg:
    def __init__(self, msgid, frm, subject, date="Mon, 21 Sep 2026 10:00:00 +0000",
                 flags=(), unsub=False, body="hello"):
        self.msgid, self.frm, self.subject, self.date = msgid, frm, subject, date
        self.flags = set(flags)
        self.unsub, self.body = unsub, body
        self.labels: set = set()
        self.uids: dict = {}

    def headers(self, fields) -> bytes:
        out = []
        want = {f.upper() for f in fields}
        if "FROM" in want:
            out.append(f"From: {self.frm}")
        if "SUBJECT" in want:
            out.append(f"Subject: {self.subject}")
        if "DATE" in want:
            out.append(f"Date: {self.date}")
        if "MESSAGE-ID" in want and self.msgid:
            out.append(f"Message-ID: {self.msgid}")
        return ("\r\n".join(out) + "\r\n\r\n").encode("utf-8")

    def full_headers(self) -> str:
        h = (f"From: {self.frm}\r\nSubject: {self.subject}\r\nDate: {self.date}\r\n"
             + (f"Message-ID: {self.msgid}\r\n" if self.msgid else "")
             + ("List-Unsubscribe: <mailto:u@example.com>\r\n" if self.unsub else ""))
        return h


class FakeServer:
    def __init__(self, *, gmail=False, move=True, uidplus=True, copyuid=True,
                 special_use=True, archive_folder=True, flags_after_body=False):
        self.gmail, self.move, self.uidplus, self.copyuid = gmail, move, uidplus, copyuid
        self.special_use, self.flags_after_body = special_use, flags_after_body
        self.names = ["INBOX", "Sent", "Trash"]
        if gmail:
            self.names = ["INBOX", "[Gmail]/All Mail", "[Gmail]/Trash", "[Gmail]/Sent Mail"]
        elif archive_folder:
            self.names.append("Archive")
        self.validity = {n: 7000 + i for i, n in enumerate(self.names)}
        self.msgs: list = []
        self.next_uid: dict = {n: 100 for n in self.names}
        self.log: list = []              # every command, as a tuple
        self.bugs: list = []             # what the caller did that it must not
        self.logins: list = []
        self.fail_after = None           # raise OSError on the Nth change command
        self._changes = 0

    # -- building a mailbox ---------------------------------------------------
    def add(self, folder: str, msg: Msg) -> Msg:
        msg.labels.add(folder)
        msg.uids[folder] = self._uid(folder)
        self.msgs.append(msg)
        return msg

    def _uid(self, folder: str) -> int:
        self.next_uid[folder] += 1
        return self.next_uid[folder]

    def folders_of(self, m: Msg) -> frozenset:
        """Where a person would find it. On Gmail every message that is not in
        Trash is also in All Mail, whatever labels it has."""
        out = set(m.labels)
        if self.gmail and "[Gmail]/Trash" not in m.labels:
            out.add("[Gmail]/All Mail")
        return frozenset(out)

    def members(self, folder: str) -> list:
        """[(uid, msg)] in the folder, oldest UID first."""
        got = [m for m in self.msgs if folder in self.folders_of(m)]
        for m in got:
            m.uids.setdefault(folder, self._uid(folder))
        return sorted(((m.uids[folder], m) for m in got), key=lambda t: t[0])

    def snapshot(self) -> dict:
        """{msgid: [(folders, flags)]} - what a person sees."""
        out = {}
        for m in self.msgs:
            f = self.folders_of(m)
            if f:
                out.setdefault(m.msgid or id(m), []).append((f, frozenset(m.flags)))
        return {k: sorted(v, key=lambda t: sorted(t[0])) for k, v in out.items()}

    def where(self, msgid: str) -> list:
        return sorted({f for m in self.msgs if m.msgid == msgid for f in self.folders_of(m)})

    def cmds(self, *names) -> list:
        return [c for c in self.log if c[0] in names]

    def connection(self) -> "FakeConn":
        return FakeConn(self)


def _unq(s: str) -> str:
    s = str(s)
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] == '"' else s


class FakeConn:
    def __init__(self, server: FakeServer):
        self.s = server
        self.selected = None
        self.readonly = False
        self.state = "authenticated"

    # -- the session ----------------------------------------------------------
    def login(self, user, password):
        self.s.logins.append((user, password))
        return "OK", [b"logged in"]

    def logout(self):
        self.s.log.append(("LOGOUT",))
        return "BYE", [b"bye"]

    def capability(self):
        caps = ["IMAP4rev1", "IDLE", "NAMESPACE"]
        if self.s.move:
            caps.append("MOVE")
        if self.s.uidplus:
            caps.append("UIDPLUS")
        if self.s.gmail:
            caps.append("X-GM-EXT-1")
        return "OK", [" ".join(caps).encode()]

    def list(self):
        rows = []
        for n in self.s.names:
            flags = ["\\HasNoChildren"]
            if self.s.special_use:
                if n.endswith("Trash"):
                    flags.append("\\Trash")
                elif n == "Archive":
                    flags.append("\\Archive")
                elif n == "[Gmail]/All Mail":
                    flags.append("\\All")
                elif n.startswith("Sent") or n.endswith("Sent Mail"):
                    flags.append("\\Sent")
            rows.append(f'({" ".join(flags)}) "/" "{n}"'.encode())
        return "OK", rows

    def select(self, mailbox, readonly=False):
        name = _unq(mailbox)
        self.s.log.append(("EXAMINE" if readonly else "SELECT", name))
        if name not in self.s.names:
            return "NO", [b"no such mailbox"]
        self.selected, self.readonly = name, readonly
        return "OK", [str(len(self.s.members(name))).encode()]

    def response(self, code):
        if code == "UIDVALIDITY" and self.selected:
            return code, [str(self.s.validity[self.selected]).encode()]
        return code, [None]

    def close(self):                                   # never allowed
        self.s.bugs.append("CLOSE")
        raise AssertionError("CLOSE would expunge every \\Deleted message in the folder")

    def expunge(self):                                 # never allowed
        self.s.bugs.append("EXPUNGE")
        raise AssertionError("a plain EXPUNGE removes every \\Deleted message in the folder")

    # -- UID commands ---------------------------------------------------------
    def uid(self, command, *args):
        cmd = command.upper()
        import imaplib
        # What Python's own imaplib would say before sending anything.
        if cmd not in imaplib.Commands or "SELECTED" not in imaplib.Commands[cmd]:
            raise imaplib.IMAP4.error(f"Unknown IMAP4 UID command: {cmd}")
        if any(not isinstance(a, str) for a in args):
            raise TypeError("imaplib takes strings here")
        self.s.log.append(("UID " + cmd,) + tuple(str(a) for a in args))
        if self.selected is None:
            return "BAD", [b"no folder selected"]
        if cmd == "SEARCH":
            return self._search(list(args))
        if cmd == "FETCH":
            return self._fetch(int(args[0]), str(args[1]))
        if cmd in ("STORE", "COPY", "MOVE", "EXPUNGE"):
            return self._change(cmd, args)
        return "BAD", [b"unknown"]

    def _by_uid(self, uid: int):
        for u, m in self.s.members(self.selected):
            if u == uid:
                return m
        return None

    def _search(self, crit):
        i, keep = 0, []
        members = self.s.members(self.selected)
        while i < len(crit):
            t = str(crit[i]).upper()
            if t in ("UNDELETED", "UNSEEN", "UNFLAGGED"):
                keep.append((t, None))
                i += 1
            elif t in ("FROM", "SUBJECT", "TEXT", "SINCE", "BEFORE"):
                keep.append((t, _unq(crit[i + 1])))
                i += 2
            elif t == "HEADER":
                keep.append(("HEADER", (str(crit[i + 1]).lower(), _unq(crit[i + 2]))))
                i += 3
            else:
                return "BAD", [b"unknown criterion"]
        from datetime import datetime
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                  "dec"]

        def when(m):
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(m.date).date()

        def ok(m):
            for t, v in keep:
                if t == "UNDELETED" and DELETED in m.flags:
                    return False
                if t == "UNSEEN" and SEEN in m.flags:
                    return False
                if t == "UNFLAGGED" and FLAGGED in m.flags:
                    return False
                if t == "FROM" and v.lower() not in m.frm.lower():
                    return False
                if t == "SUBJECT" and v.lower() not in m.subject.lower():
                    return False
                if t == "TEXT" and v.lower() not in (m.subject + " " + m.body).lower():
                    return False
                if t in ("SINCE", "BEFORE"):
                    d, mon, y = v.split("-")
                    lim = datetime(int(y), months.index(mon.lower()) + 1, int(d)).date()
                    if t == "SINCE" and when(m) < lim:
                        return False
                    if t == "BEFORE" and when(m) >= lim:
                        return False
                if t == "HEADER":
                    name, val = v
                    if name == "list-unsubscribe" and not m.unsub:
                        return False
                    if name == "message-id" and m.msgid != val:
                        return False
            return True
        return "OK", [" ".join(str(u) for u, m in members if ok(m)).encode()]

    def _fetch(self, uid, spec):
        m = self._by_uid(uid)
        if m is None:
            return "OK", [None]
        fm = re.search(r"HEADER\.FIELDS \(([^)]*)\)", spec)
        fields = fm.group(1).split() if fm else []
        head = m.headers(fields)
        flags = " ".join(sorted(m.flags))
        if "BODY.PEEK" not in spec and "BODY[" in spec:
            m.flags.add(SEEN)                          # a plain BODY[] sets \Seen
        if self.s.flags_after_body:
            first = f"1 (UID {uid} BODY[HEADER.FIELDS ({' '.join(fields)})] {{{len(head)}}}".encode()
            return "OK", [(first, head), f" FLAGS ({flags}))".encode()]
        first = (f"1 (UID {uid} FLAGS ({flags}) BODY[HEADER.FIELDS "
                 f"({' '.join(fields)})] {{{len(head)}}}").encode()
        return "OK", [(first, head), b")"]

    def _change(self, cmd, args):
        if self.readonly:
            return "NO", [b"mailbox is read-only"]
        self.s._changes += 1
        if self.s.fail_after is not None and self.s._changes > self.s.fail_after:
            raise OSError("connection reset by peer with the secret text in it")
        uid = int(args[0])
        m = self._by_uid(uid)
        if m is None:
            return "NO", [b"no such message"]
        if cmd == "STORE":
            op, val = str(args[1]).upper(), str(args[2]).strip("()")
            if op.endswith("X-GM-LABELS"):
                if not self.s.gmail:
                    return "BAD", [b"not gmail"]
                label = {"\\Inbox": "INBOX", "\\Trash": "[Gmail]/Trash"}.get(val, val)
                if op.startswith("+"):
                    m.labels.add(label)
                    m.uids.setdefault(label, self.s._uid(label))
                else:
                    m.labels.discard(label)
                return "OK", [b"done"]
            flags = set(val.split())
            if op.startswith("+"):
                m.flags |= flags
            else:
                m.flags -= flags
            return "OK", [b"done"]
        if cmd == "COPY":
            dst = _unq(args[1])
            if dst not in self.s.names:
                return "NO", [b"[TRYCREATE] no such mailbox"]
            new_uid = self.s._uid(dst)
            if self.s.gmail:
                m.labels.add(dst)
                m.uids[dst] = new_uid
            else:
                c = Msg(m.msgid, m.frm, m.subject, m.date, m.flags, m.unsub, m.body)
                c.labels.add(dst)
                c.uids[dst] = new_uid
                self.s.msgs.append(c)
            text = f"[COPYUID {self.s.validity[dst]} {uid} {new_uid}] done" \
                if self.s.copyuid else "done"
            return "OK", [text.encode()]
        if cmd == "MOVE":
            if not self.s.move:
                return "BAD", [b"MOVE not supported"]
            dst = _unq(args[1])
            if dst not in self.s.names:
                return "NO", [b"[TRYCREATE] no such mailbox"]
            new_uid = self.s._uid(dst)
            m.labels.discard(self.selected)
            m.uids.pop(self.selected, None)
            m.labels.add(dst)
            m.uids[dst] = new_uid
            text = f"[COPYUID {self.s.validity[dst]} {uid} {new_uid}] done" \
                if self.s.copyuid else "done"
            return "OK", [text.encode()]
        if cmd == "EXPUNGE":
            if not self.s.uidplus:
                return "BAD", [b"UID EXPUNGE needs UIDPLUS"]
            if DELETED not in m.flags:
                self.s.bugs.append("UID EXPUNGE of a message not marked deleted")
                raise AssertionError("UID EXPUNGE of a message that was not marked \\Deleted")
            others = [x for x in self.s.msgs if x is not m and x.msgid == m.msgid
                      and x.labels]
            if self.s.gmail:
                self.s.bugs.append("UID EXPUNGE on Gmail")
                raise AssertionError("Gmail archives and trashes by label - never by expunge")
            if not others:
                self.s.bugs.append("UID EXPUNGE with no copy anywhere")
                raise AssertionError("UID EXPUNGE of an email with no other copy: it is lost")
            m.labels.discard(self.selected)
            m.uids.pop(self.selected, None)
            return "OK", [b"expunged"]
        return "BAD", [b"unknown"]
