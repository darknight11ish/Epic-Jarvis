"""jarvis_kokoro.py - which Kokoro voice pack is on this PC, and its voices BY NAME.

NEW MODULE, shipped whole beside jarvis_voices.py and jarvis_speech.py
(apply-patches.ps1 copies it). No patch: nothing in it is a route.

WHAT IT IS FOR, in plain words. Jarvis's built-in voice is Kokoro, and until
now the owner's choice of WHICH Kokoro voice was saved as a bare number
("9"). A number means a different voice in a different pack: number 9 was
George in the pack Jarvis shipped with (kokoro-en-v0_19, 11 voices) and is
Sarah in Kokoro v1.0 (54 voices). So the choice is now saved as the voice's
NAME ("bm_george"), and this module is the one place that knows, for the pack
that is actually installed:

    * which voices it has, and each one's number for sherpa-onnx (`sid`);
    * the owner's OLD numbers, and what name each one meant (LEGACY_NAME) -
      so the choice carries over once, unchanged;
    * the voices offered in the pickers (best rated first, never the ones
      whose names match a voice another company withdrew);
    * the accent: British voices are asked for espeak's British English
      ("en-gb-x-rp"), American ones for the engine's own default ("en-us");
    * the pinned download of the v1.0 pack (V1_PACK) and the one PowerShell
      line that installs it.

WHAT WAS CHECKED, and how (2026-09-29, in the build container - not the
owner's PC):

    * The names and their order, for BOTH packs, were read off the real
      files: every voice row of each pack's `voices.bin` was compared with
      the voice arrays kokoro-onnx publishes under names (voices.json for
      v0.19, voices-v1.0.bin for v1.0). All 11 and all 54 matched exactly,
      number for number - so V019_NAMES and V1_NAMES are not remembered,
      they were matched. (v1.0's order is alphabetical, then `em_santa`
      last: it is index 53, not next to `em_alex`.)
    * The pinned file (V1_PACK) is the release file sherpa-onnx publishes,
      downloaded from GitHub's own release URL: 349,906,910 bytes, the size
      GitHub reported before the download. The same download route gave the
      SAME SHA-256 for the old v0.19 file as the one the README already
      pinned (912804...), which is the reason to trust the method. It was
      extracted and the model loaded and spoke, with sherpa-onnx 1.13.8, in
      every voice named here. The SHA-256 came from that one download; no
      second source (such as GitHub's release page, which this container
      cannot read) was compared. The install line checks it again on the
      owner's PC and installs nothing if it differs.
    * What was NOT done: nobody listened. Pitch and pace of the animals'
      voices were MEASURED, not judged by ear (docs/CRITTERS.md).

Standard library only. Never prints except as a command-line tool.
"""
from __future__ import annotations

import os
from typing import Optional

# --------------------------------------------------------------------------
#   THE PIN - the ONE place the v1.0 download is written down
# --------------------------------------------------------------------------
#
# Change a value here and NOTHING else: install_line() writes the PowerShell
# line from it, backend/README.md's copy of that line is checked against it
# by test_kokoro.py, and status() names the pack from it. If a value cannot
# be confirmed, leave `sha256` as "" - install_line() then refuses to give a
# line at all (an install with no checksum is not offered).
V1_PACK = {
    "name": "Kokoro v1.0",
    #: The folder the archive unpacks to (its top level).
    "folder": "kokoro-multi-lang-v1_0",
    "url": ("https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
            "kokoro-multi-lang-v1_0.tar.bz2"),
    "bytes": 349_906_910,
    "sha256": "c5f7e2d2caf082bc1d20fb70334a61d99d20b484500aad32e7cf84c128ea3298",
}

#: The voice model INSIDE V1_PACK (`model.onnx` in the folder above), read
#: off the file that the pinned download unpacks to (2026-09-29): 325,560,556
#: bytes. jarvis_mouth.py's one-time step (`--prepare`) makes the animals'
#: exact mouth timing from this file and refuses any other, so the timing is
#: only ever paired with the model it was checked against.
V1_MODEL = {
    "file": "model.onnx",
    "bytes": 325_560_556,
    "sha256": "b40f62b166ac8164b0627ef48a0b358eda0985e272fb03ef5252e7206305da11",
}

#: The pack Jarvis shipped with (its own line stays in backend/README.md).
V019_PACK = {
    "name": "Kokoro v0.19",
    "folder": "kokoro-en-v0_19",
    "sha256": "912804855a04745fa77a30be545b3f9a5d15c4d66db00b88cbcd4921df605ac7",
}

# --------------------------------------------------------------------------
#   The two packs, and their voices in sherpa-onnx's own order (`sid`)
# --------------------------------------------------------------------------

V019 = "v019"
V1 = "v1"

#: kokoro-en-v0_19: 11 voices. Matched against the real file (see above).
#: "af" is Kokoro's own default American voice - a mix of Bella and Sarah.
V019_NAMES = ("af", "af_bella", "af_nicole", "af_sarah", "af_sky", "am_adam", "am_michael",
              "bf_emma", "bf_isabella", "bm_george", "bm_lewis")

#: kokoro-multi-lang-v1_0: 54 voices. Matched against the real file.
V1_NAMES = (
    "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole",
    "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx",
    "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    "ef_dora", "em_alex", "ff_siwis", "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    "if_sara", "im_nicola", "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro",
    "jm_kumo", "pf_dora", "pm_alex", "pm_santa",
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    "em_santa",
)

_NAMES = {V019: V019_NAMES, V1: V1_NAMES}
#: Rows in a pack's voices.bin per voice (v0.19 has 511, v1.0 has 510 - one
#: style vector for each length of sentence), 256 numbers of 4 bytes each.
_ROWS = {V019: 511, V1: 510}
_ROW_BYTES = 256 * 4

#: The owner's OLD saved choice: a number, in the numbering of the pack
#: Jarvis shipped with. What each one meant.
LEGACY_NAME = {str(i): n for i, n in enumerate(V019_NAMES)}

#: The voice that stands in for another pack's default. v0.19's "af" and
#: v1.0's "af_heart" are the same kind of voice - the pack's own default
#: American woman - and MEASURED alike: the middle pitch of one sentence in
#: each was 205 Hz and 203 Hz.
_ALIAS = {V1: {"af": "af_heart"}, V019: {"af_heart": "af"}}

#: Each pack's default voice for someone who has chosen nothing.
DEFAULT = {V019: "af", V1: "af_heart", "": "af"}

# --------------------------------------------------------------------------
#   The voices the pickers offer
# --------------------------------------------------------------------------
#
# Kokoro's own gradings (VOICES.md, as recorded in
# docs/studio-2026-09-27/voice-lineup.md - the file itself could not be read
# again here) put these first: Heart A, Bella A-, Nicole B-, Emma B-, then a
# group at C+ / C. Kept so both packs still offer eleven-ish voices, the ones
# the owner already knew (Bella, Nicole, Sarah, Michael, Emma, Isabella,
# George, Lewis) and the three v1.0 adds that grade as well as Michael
# (Heart, Fenrir, Puck).
#
# LEFT OUT of the pickers, on purpose:
#   * af_sky and am_adam: Sky's name matches the voice OpenAI withdrew in
#     2024 over a likeness complaint (the owner's rule for the sea otter, and
#     the studio kept the whole family of look-alike names out); Adam grades
#     F+. Both still WORK for an owner who already chose one - it stays their
#     choice and is listed once as "your current choice" - but no animal may
#     use either.
#   * af_alloy, am_echo, am_onyx, af_nova, bm_fable: names that match OpenAI's
#     voices; the studio kept them out too. And every voice graded D or lower.
#   * every non-English voice: Jarvis speaks English.
V1_PICK = ("af_heart", "af_bella", "af_nicole", "af_sarah", "am_michael", "am_fenrir",
           "am_puck", "bf_emma", "bf_isabella", "bm_george", "bm_lewis")
V019_PICK = ("af", "af_bella", "af_nicole", "af_sarah", "am_michael", "bf_emma",
             "bf_isabella", "bm_george", "bm_lewis")
_PICK = {V019: V019_PICK, V1: V1_PICK, "": V019_PICK}

#: Never a choice for any animal, whatever the owner's old state says.
NEVER_FOR_ANIMALS = ("af_sky", "am_adam")

_ACCENT = {"a": "American", "b": "British"}
_SEX = {"f": "female", "m": "male"}

#: Spoken English for the British voices: espeak-ng's Received Pronunciation
#: voice. Checked against the real v1.0 pack: "en-gb" alone is refused by the
#: pack's bundled espeak data ("Failed to set eSpeak-ng voice"); "en-gb-x-rp"
#: works and changes the sound (the same sentence in bm_george came out
#: 2.91 s against 2.97 s under en-us). `[voice] tts_lang_british` may name
#: another espeak voice.
BRITISH_LANG = "en-gb-x-rp"


def label_of(name: str) -> str:
    """"American (female) - Bella" for "af_bella"; "American (female)" for
    v0.19's own default "af"; the name itself for a voice that is not one of
    the four English groups."""
    if not isinstance(name, str) or len(name) < 2:
        return str(name)
    head = f"{_ACCENT.get(name[0], '')} ({_SEX.get(name[1], '')})".strip()
    if name[0] not in _ACCENT or name[1] not in _SEX or name[2:3] not in ("", "_"):
        return f"Voice {name}"
    who = name[3:].replace("_", " ").title()
    return f"{head} - {who}" if who else head


def known(name) -> bool:
    """`name` is a voice of either pack (a saved choice may be checked
    without knowing which pack is installed)."""
    return isinstance(name, str) and (name in V1_NAMES or name in V019_NAMES)


def normalise(value) -> Optional[str]:
    """A saved voice value - an old number ("9") or a name - as a NAME of
    either pack, or None when it is neither. The one-time carry-over: a
    number becomes what it meant in the pack Jarvis shipped with."""
    if isinstance(value, bool) or not isinstance(value, str):
        return None
    if value in LEGACY_NAME:
        return LEGACY_NAME[value]
    return value if known(value) else None


def is_legacy_number(value) -> bool:
    return isinstance(value, str) and value in LEGACY_NAME


# --------------------------------------------------------------------------
#   Which pack is installed
# --------------------------------------------------------------------------

def kind_of_file(path) -> str:
    """"v1", "v019", or "" for a voices.bin - by its size alone (no model is
    loaded): a whole number of voices of one pack. "" too when the file is
    missing or is neither pack (a v1.1 pack, or a damaged file)."""
    try:
        size = os.path.getsize(path)
    except (OSError, TypeError, ValueError):
        return ""
    for kind in _NAMES:
        if size == voices_file_size(kind):
            return kind
    return ""


def voices_file_size(kind: str) -> int:
    """How many bytes a pack's voices.bin is (what kind_of_file() looks for).
    Tests write a file of this size to stand in for the pack."""
    return len(_NAMES[kind]) * _ROWS[kind] * _ROW_BYTES


def names(kind: str) -> tuple:
    return _NAMES.get(kind, V019_NAMES)


def resolve(kind: str, name) -> Optional[str]:
    """The name to use in this pack for a saved `name`: itself when the pack
    has it, its stand-in (af <-> af_heart) when it does not, else None."""
    if not isinstance(name, str):
        return None
    pack = names(kind)
    if name in pack:
        return name
    alias = _ALIAS.get(kind if kind in _ALIAS else V019, {}).get(name)
    return alias if alias in pack else None


def sid_of(kind: str, name) -> Optional[int]:
    """sherpa-onnx's number for `name` in this pack (after resolve())."""
    got = resolve(kind, name)
    return names(kind).index(got) if got is not None else None


def name_of(kind: str, sid) -> Optional[str]:
    pack = names(kind)
    if isinstance(sid, bool) or not isinstance(sid, int) or not 0 <= sid < len(pack):
        return None
    return pack[sid]


def default_name(kind: str) -> str:
    return DEFAULT.get(kind, "af")


def default_sid(kind: str) -> int:
    return names(kind).index(default_name(kind)) if kind else 0


def pickable(kind: str) -> tuple:
    """The names the pickers offer for this pack, best rated first."""
    return _PICK.get(kind, V019_PICK)


def pickable_for_animals() -> tuple:
    """Every name any pack offers to an animal - what a saved animal choice
    is checked against without knowing the pack."""
    seen = []
    for n in V1_PICK + V019_PICK:
        if n not in seen and n not in NEVER_FOR_ANIMALS:
            seen.append(n)
    return tuple(seen)


def offered(kind: str, current: Optional[str] = None) -> list:
    """The picker rows for this pack: [{"id", "label"}], the offered voices
    then - only if it is not one of them - the owner's current choice, so a
    choice that carried over never vanishes from the list."""
    rows = [{"id": n, "label": label_of(n)} for n in pickable(kind)]
    if current and current not in pickable(kind) and current in names(kind):
        rows.append({"id": current, "label": f"{label_of(current)} (your current choice)"})
    return rows


def accent_lang(kind: str, name, british: Optional[str] = None) -> Optional[str]:
    """The espeak voice to ask for with this voice, or None for the engine's
    own default (American English). Only Kokoro v1.0 takes a language per
    call; v0.19's speech is always American, so None there."""
    if kind != V1 or not isinstance(name, str) or not name.startswith("b"):
        return None
    return (british or "").strip() or BRITISH_LANG


def pack_words(kind: str) -> dict:
    """{"kind", "name", "voices"}: what is installed, in words."""
    if kind == V1:
        return {"kind": V1, "name": V1_PACK["name"], "voices": len(V1_NAMES)}
    if kind == V019:
        return {"kind": V019, "name": V019_PACK["name"], "voices": len(V019_NAMES)}
    return {"kind": "", "name": "", "voices": 0}


# --------------------------------------------------------------------------
#   The install line
# --------------------------------------------------------------------------

def install_line() -> str:
    """The ONE PowerShell line that installs the v1.0 pack on the owner's PC,
    written from V1_PACK - or "" when V1_PACK has no checksum (an install
    with nothing to check the download against is never offered).

    It downloads, checks the SHA-256 and installs NOTHING if it differs, keeps
    the old pack beside the new one (tts-old-<date>, so going back is a
    rename), and unpacks over nothing else. Same shape as the line that
    installed v0.19 (backend/README.md)."""
    pin = V1_PACK
    if not str(pin.get("sha256") or "").strip() or not str(pin.get("url") or "").strip():
        return ""
    mb = round(int(pin["bytes"]) / 1_000_000)
    return (
        "$ProgressPreference = 'SilentlyContinue'; "
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
        "$base = if ($env:OPENJARVIS_CONFIG_DIR) { $env:OPENJARVIS_CONFIG_DIR } "
        "elseif ($env:JARVIS_CONFIG_DIR) { $env:JARVIS_CONFIG_DIR } "
        "else { \"$env:USERPROFILE\\.openjarvis\" }; "
        "$m = Join-Path $base 'voice-models'; "
        "New-Item -ItemType Directory -Force -Path $m | Out-Null; "
        "$f = Join-Path $env:TEMP 'jarvis-tts-v1.tar.bz2'; "
        f"Write-Host 'Downloading the new voices ({mb} MB)...'; "
        f"Invoke-WebRequest -UseBasicParsing -Uri '{pin['url']}' -OutFile $f; "
        f"if ((Get-FileHash $f -Algorithm SHA256).Hash -ne '{str(pin['sha256']).upper()}') "
        "{ Remove-Item $f; Write-Host 'That is not the expected file, so nothing was "
        "installed. Run this line again.' -ForegroundColor Red } "
        "else { tar -xjf $f -C $m; Remove-Item $f; "
        "$d = Join-Path $m 'tts'; "
        "if (Test-Path $d) { Rename-Item $d ('tts-old-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }; "
        f"Rename-Item (Join-Path $m '{pin['folder']}') 'tts'; "
        "Write-Host \"OK - the new voices are in $d. Restart Jarvis to hear them.\" "
        "-ForegroundColor Green }"
    )


UPGRADE_NOTE = ("Better voices are available: Kokoro v1.0 has more, better-rated voices and "
                "a real British accent (a {mb} MB download). To get them, run the "
                "one line under \"Upgrade the voice pack to Kokoro v1.0\" in "
                "backend\\README.md on your PC, then restart Jarvis. Your choice carries over.")


def upgrade_note() -> str:
    """The sentence both apps show while the old pack is installed, or ""
    when there is no checksum to install against."""
    if not install_line():
        return ""
    return UPGRADE_NOTE.format(mb=round(int(V1_PACK["bytes"]) / 1_000_000))
