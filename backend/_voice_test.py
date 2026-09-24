"""Test plumbing: a stand-in speaker model for the voice suites.

Not shipped (test_shipped_modules.NOT_SHIPPED says so).

WHY. Since 2026-09-24 the basic spectral check never lets anyone in, in
owner mode (jarvis_voice, "hole 1"): it cannot tell two people apart. The
suites used it as their "speaker model" - enrol with Embedder(), then expect
the owner to pass - and every such test now (correctly) sees a refusal.
They need something that behaves like a speaker model: `semantic = True`,
one stable name, and vectors that separate "voices". This is the spectral
signature of the first second of a clip - so a clip's LENGTH no longer
changes its vector - marked semantic. It separates the suites' synthetic
voices by pitch (180 Hz vs 300 Hz: similarity 0.0), which is all they ask.

    with semantic_voice(V):          # hear() and enrol both use it
        ...

It also switches the STRONGER model off (there is none here, but on the
owner's PC there may be one, and a suite must not depend on it) and puts
the strictness settings in a temporary file, at their defaults.
"""
import contextlib
import tempfile
from pathlib import Path
from unittest import mock


def stand_in(V):
    """The class, built on this jarvis_voice module's own Embedder."""

    base = V.Embedder

    class Voiceish(base):
        name = "test-voice"
        semantic = True

        def embed(self, audio):
            return base.embed(self, V._pcm(audio)[:16000])

    return Voiceish


@contextlib.contextmanager
def semantic_voice(V, settings_dir=None):
    cls = stand_in(V)
    d = Path(settings_dir or tempfile.mkdtemp(prefix="jarvis-voice-settings-"))
    patches = [mock.patch.object(V, "EcapaEmbedder", cls)]
    if hasattr(V, "strong_embedder"):
        patches.append(mock.patch.object(V, "strong_embedder", lambda *a, **k: None))
    if hasattr(V, "settings_path"):
        patches.append(mock.patch.object(V, "settings_path",
                                         lambda: d / "voice-settings.json"))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield cls
