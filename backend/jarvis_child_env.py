"""jarvis_child_env.py - what a program Jarvis starts is allowed to inherit.

WHAT WENT WRONG (bug audit 3, CONN-2)
When Jarvis starts a program - the second Ollama (jarvis_second_card.lane_env)
or colibri, the big model (jarvis_big_model.engine_env) - that program gets
an environment: a list of NAME=value settings. Both used to hand over a copy
of Jarvis's WHOLE environment, minus a few names. Jarvis's environment holds
the pairing token (`HUD_TOKEN`, `JARVIS_TOKEN`), the Joplin token, the
Obsidian key, and whatever `*_KEY`, `*_PASSWORD` or `*_SECRET` the owner has
set for other things. So every one of them went to Ollama and to colibri,
neither of which needs any of them. CLAUDE.md rule 3: a key is "sent only
to the one service it authenticates against".

THE FIX: AN ALLOWLIST, NOT A BLOCKLIST
`inherited()` starts from nothing and copies over only the names on the list
below: what Windows itself needs for a program to start and find its files
(and the POSIX equivalents, so the tests run here), plus whatever names the
caller asks for by name or prefix - `OLLAMA_MODELS` for the second Ollama,
so it finds the models the owner already downloaded. The caller then adds
its own settings on top (`OLLAMA_HOST`, `CUDA_VISIBLE_DEVICES`,
`COLI_API_KEY`, ...), which are not "inherited" and so are not filtered.

A blocklist ("drop anything called *_TOKEN") would miss the next secret
with an unusual name. Belt and braces, though: even an allowed name is
dropped if it LOOKS like a secret (`_looks_secret`), so a prefix such as
`CUDA_` can never carry `CUDA_SOMETHING_TOKEN` through by accident.

Windows compares environment names without regard to case, and Python on
Windows upper-cases them in `os.environ` ("ProgramFiles" is "PROGRAMFILES"
there), so the comparison here is case-blind. The value, and the name's own
spelling, are passed on unchanged.

Standard library only.
"""
from __future__ import annotations

import os
from typing import Iterable, Mapping, Optional

#: Names a program needs to start and find its files, copied when present.
#: Windows: the system folders, the search path, the temp folders, the user's
#: profile folders, the machine and user name, the processor description and
#: the command interpreter. POSIX: the home folder and the language settings.
ESSENTIAL = frozenset(n.upper() for n in (
    "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE",
    "LOCALAPPDATA", "APPDATA", "HOMEDRIVE", "HOMEPATH", "COMPUTERNAME", "USERNAME",
    "NUMBER_OF_PROCESSORS", "OS", "ProgramData", "SystemDrive", "ComSpec",
    # POSIX
    "HOME", "LANG",
))

#: Name prefixes copied when present: PROCESSOR_ARCHITECTURE and friends,
#: ProgramFiles and ProgramFiles(x86), and the POSIX LC_* language settings.
ESSENTIAL_PREFIXES = tuple(p.upper() for p in ("PROCESSOR_", "ProgramFiles", "LC_"))

#: Words that mark a name as a secret. Checked on every inherited name, even
#: an allowed one.
_SECRET_WORDS = ("TOKEN", "KEY", "PASSWORD", "PASSWD", "SECRET", "CREDENTIAL", "AUTH")


def _looks_secret(name: str) -> bool:
    up = name.upper()
    return any(w in up for w in _SECRET_WORDS)


def inherited(base: Optional[Mapping[str, str]] = None, *, names: Iterable[str] = (),
              prefixes: Iterable[str] = ()) -> dict:
    """The part of `base` (default: this process's environment) a child
    program may inherit: ESSENTIAL and ESSENTIAL_PREFIXES, plus the extra
    `names` and `prefixes` given, never anything that looks like a secret.

    The caller adds its own settings to the returned dict afterwards."""
    src = os.environ if base is None else base
    want = ESSENTIAL | {n.upper() for n in names}
    pre = ESSENTIAL_PREFIXES + tuple(p.upper() for p in prefixes)
    out = {}
    for k, v in src.items():
        up = str(k).upper()
        if (up in want or up.startswith(pre)) and not _looks_secret(up):
            out[k] = v
    return out
