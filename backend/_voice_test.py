"""Test plumbing: a stand-in speaker model for the voice suites, and the two
states a machine can be in.

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
    with no_voice_models(V):         # a PC that has never downloaded one
        ...

`semantic_voice` also switches the STRONGER model off (there is none here, but
on the owner's PC there may be one, and a suite must not depend on it) and puts
the strictness settings in a temporary file, at their defaults.

`no_voice_models` is the other end of the same problem: a PC with nothing
installed at all. See its own docstring.
"""
import contextlib
import os
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


@contextlib.contextmanager
def no_voice_models(V):
    """A PC where NO voice model has ever been installed - the settings folder
    is an empty temporary one for the length of the block, so every path the
    voice code looks in is empty.

    WHY THIS EXISTS. Two suites describe exactly that PC and were reading the
    OWNER'S instead:

        test_voice_flow.py    "nothing installed: nothing to warm"   (1 failed)
        test_voice_enroll.py  "an older jarvis_voice.enroll (no
                               sample_rate) still works"            (1 failed)

    Every path either check decides on comes from the machine's own settings
    folder: `jarvis_speech._config_dir()` and `jarvis_voice._profile_dir()`
    both follow `jarvis_framework.CONFIG_DIR` (OPENJARVIS_CONFIG_DIR, else
    `~/.openjarvis`), and that is where the text-to-speech, speech-to-text,
    VAD and speaker-onnx models live. On the owner's PC all four are installed,
    so `_anything_installed()` answered True (nothing to warm became "there IS
    something to warm") and `jarvis_voice_enroll._embedder()` returned the real
    `EcapaEmbedder` (whose enrolment drops one of the suite's five synthetic
    tones as an outlier, so a 5-clip training made a 4-sample profile). Neither
    answer is a defect - both are right FOR THAT PC and wrong for the state the
    checks are about. Both suites are green on a CI runner for one reason only:
    a runner has no `~/.openjarvis`. An accident of the machine, not something
    either suite did for itself.

    So the state is BUILT rather than assumed, and each suite checks the
    premise it needs before the behaviour it came for:

        with no_voice_models(V):
            check("this run looks like a PC with no voice models", ...)
    """
    fw = getattr(V, "fw", None)
    folder = Path(tempfile.mkdtemp(prefix="jarvis-no-voice-models-"))
    patches = [mock.patch.dict(os.environ, {"OPENJARVIS_CONFIG_DIR": str(folder),
                                            "JARVIS_CONFIG_DIR": str(folder)})]
    if fw is not None:
        # The one lever both jarvis_voice and jarvis_speech read: they hold the
        # same jarvis_framework module object.
        patches.append(mock.patch.object(fw, "CONFIG_DIR", folder))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield folder
