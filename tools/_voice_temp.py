r"""Temporary folders for the voice-case producers (`tools/gen_voice_*_cases.py`).

WHY THIS EXISTS (2026-10-20, from Gemini's review of the Windows run). The
producers are tested on a deliberately LONG `%TEMP%`: `backend/test_voice_contract.py`
renders each one in a fresh interpreter whose temporary root is the real
`%TEMP%` and then a root 120 characters deeper, and requires the SAME bytes
from both. On Windows, paths are limited to 260 characters unless they are
handed to the OS in their extended-length form (`\\?\C:\...`). A deep `%TEMP%`
made every nested folder the producers create - for example
`...\tmpXXXXXXXX\voice-models\wakeword` - longer than 260 characters, so:

  * `gen_voice_status_cases.py` crashed in `World.__enter__` with
    `FileNotFoundError: [WinError 206] The filename or extension is too long`;
  * `gen_phone_voice_cases.py` stopped with "Could not make the file";
  * `gen_voice_training_cases.py` silently failed to save a voice earlier in
    its cases and then died seven lines later with a raw
    `KeyError: 'id'` - the failure Gemini asked us to stop hiding (that
    producer now checks its own precondition and says WHY).

THE FIX. Create the temporary folder through the extended-length form of its
path. `\\?\` is the Windows API's own opt-out from the legacy limit: it needs
no registry change, no administrator, and no new dependency. Only the folder
the producers create is changed; every path they PRINT is scrubbed to
`~/.openjarvis` before it reaches a fixture, so the committed fixture bytes do
not change (measured: all three producers render byte-identical fixtures with
an extended long root).

OTHER PLATFORMS are untouched: `temp_root()` returns `tempfile.gettempdir()`.
"""
from __future__ import annotations

import os
import tempfile

#: The Windows API's extended-length path prefix. Two backslashes and a
#: question mark, then an absolute path: `\\?\C:\...`.
_EXTENDED = "\\\\?\\"


def temp_root() -> str:
    """The temporary root to put this run's folders under.

    On Windows this is the extended-length form of `tempfile.gettempdir()`, so
    a nested folder in it is not silently limited to 260 characters. Everywhere
    else it is `tempfile.gettempdir()` unchanged."""
    root = tempfile.gettempdir()
    if os.name != "nt":
        return root
    absolute = os.path.abspath(root)
    if absolute.startswith(_EXTENDED):
        return absolute
    return _EXTENDED + absolute


def temporary_dir(**kwargs) -> tempfile.TemporaryDirectory:
    """`tempfile.TemporaryDirectory(...)` under `temp_root()`.

    Callers may still pass `dir=`; only the default is chosen here."""
    kwargs.setdefault("dir", temp_root())
    return tempfile.TemporaryDirectory(**kwargs)
