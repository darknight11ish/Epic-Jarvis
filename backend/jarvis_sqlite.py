"""A sqlite3 connection that CLOSES when its `with` block ends.

WHY THIS MODULE EXISTS (2026-10-08: the same bug fixed by hand three times)

`sqlite3.Connection`'s own context manager COMMITS on the way out and never
closes the connection. So the shape a whole family of modules uses -

    with self._lock, self._db() as c:
        ...

- left an OPEN HANDLE on the database file behind until CPython happened to
collect the connection. That collection is immediate on a quiet line of code
and NOT immediate when a caught exception's traceback, a generator frame or a
temp-folder object still holds a reference - which is why the failure moved
from suite to suite and never happened twice in the same one.

On Windows an open handle makes the file undeletable, which is what the
runner's log said, twice, inside test_sayable.py's own group (run 2026-10-07,
PR #86):

    Exception ignored in: <finalize object at 0x23ea64114e0; dead>
      File "...\\tempfile.py", line 939, in _cleanup
        cls._rmtree(name, ignore_errors=ignore_errors)
      ...
      File "...\\tempfile.py", line 909, in onexc
        _os.unlink(path)
    PermissionError: [WinError 32] The process cannot access the file
    because it is being used by another process:
    'C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\tmpqw88ug3r\\schedule.json'

- raised by TemporaryDirectory's own cleanup, and repeated a moment later for
a second folder (tmpxh2pi8w1). It cost hours of misdiagnosis, twice, in two
different suites: the message names a temp folder, and the suite it landed on
kept changing.

THE FIX WAS WRITTEN BY HAND THREE TIMES, which is why this file is here.
jarvis_schedule.py grew its own private `_ClosingConnection` (PR #112), then
jarvis_goals.py and jarvis_projects.py each grew a second and third copy (PR
#129). A private copy in each module is how a fourth module comes to reinvent
it - or to miss it. This is the one copy they share.

`backend/test_sqlite_close_guard.py` is the repo-wide check that fails if the
raw shape comes back, and that fails if a second private copy appears.

Nothing else changes: `__exit__` still commits (or rolls back) exactly as
sqlite3 does, and a caller that keeps the connection outside a `with` still
sees it released when the object is collected, as before.
"""
from __future__ import annotations

import sqlite3


class _ClosingConnection(sqlite3.Connection):
    """A connection the `with ... as c:` blocks CLOSE, not just commit.

    `__exit__` does exactly what sqlite3's does - commit, or roll back on an
    exception - and then closes the connection in a `finally`, so the handle
    is gone even when the block raised.
    """

    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def connect(path, timeout: float = 30) -> sqlite3.Connection:
    """`sqlite3.connect`, with a connection that closes when its `with` ends.

    Use this wherever a connection is handed back to be used as
    `with ... as c:` - never a bare `sqlite3.connect`, which commits and
    leaves the handle open. `row_factory` is left to the caller, as each of the
    three modules set it before.

    There is deliberately no way to ask for a different factory: an argument
    that could switch the closing behaviour off is the bug again, one keyword
    away. A caller that needs its own subclass wants its own module, and
    test_sqlite_close_guard.py will have something to say about that.
    """
    return sqlite3.connect(path, timeout=timeout, factory=_ClosingConnection)
