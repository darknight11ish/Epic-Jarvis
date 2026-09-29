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
      line that installs it;
    * the two BLENDED voices made for Jarvis, "Ashby" and "Clara" (MIX, below),
      the pinned file that holds them (voices-jarvis.bin) and the command that
      makes it on the owner's PC (`py -3 jarvis_kokoro.py --make-blends`).

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

import hashlib
import os
import sys
from array import array
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

#: Kokoro v1.0 with the pinned blend file (BLEND_FILE) in place of its own
#: voices.bin: the same 54 voices in the same order, except that two slots of
#: voices nobody uses (MIX_SLOTS) hold the two blended voices instead. Same
#: size as V1, so the size alone never says which one a file is - blend_ok()
#: does, by the file's SHA-256.
V1MIX = "v1mix"

#: Which pack a table kind belongs to: V1MIX is Kokoro v1.0 in every way
#: except its two blended slots.
_FAMILY = {V019: V019, V1: V1, V1MIX: V1}

# The blended voices are defined further down (MIX); this is only their slots.
#: Two voices of the pack that Jarvis never speaks with (Portuguese and
#: Spanish "Santa"): the blends are written over their rows in the copy.
MIX_SLOTS = {"mix_ashby": "em_santa", "mix_clara": "pm_santa"}

V1MIX_NAMES = tuple({v: k for k, v in MIX_SLOTS.items()}.get(n, n) for n in V1_NAMES)

_NAMES = {V019: V019_NAMES, V1: V1_NAMES, V1MIX: V1MIX_NAMES}
#: Rows in a pack's voices.bin per voice (v0.19 has 511, v1.0 has 510 - one
#: style vector for each length of sentence), 256 numbers of 4 bytes each.
_ROWS = {V019: 511, V1: 510, V1MIX: 510}
_ROW_BYTES = 256 * 4


def family(kind: str) -> str:
    """The pack a table kind belongs to: "v1" for both "v1" and "v1mix"."""
    return _FAMILY.get(kind, kind)

#: The owner's OLD saved choice: a number, in the numbering of the pack
#: Jarvis shipped with. What each one meant.
LEGACY_NAME = {str(i): n for i, n in enumerate(V019_NAMES)}

#: The voice that stands in for another pack's default. v0.19's "af" and
#: v1.0's "af_heart" are the same kind of voice - the pack's own default
#: American woman - and MEASURED alike: the middle pitch of one sentence in
#: each was 205 Hz and 203 Hz.
_ALIAS = {V1: {"af": "af_heart"}, V1MIX: {"af": "af_heart"}, V019: {"af_heart": "af"}}

#: Each pack's default voice for someone who has chosen nothing.
DEFAULT = {V019: "af", V1: "af_heart", V1MIX: "af_heart", "": "af"}

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
# --------------------------------------------------------------------------
#   The blended voices: "Ashby" and "Clara" (the owner, 2026-09-29)
# --------------------------------------------------------------------------
#
# A Kokoro voice is a table of style vectors: 510 rows of 256 numbers, one row
# for each length of sentence (a sentence of n sounds uses row n - 1). A BLEND
# is the weighted sum of two voices' tables, number by number, with weights
# that add up to 1 - the way kokoro-onnx's own README blends voices
# (`np.add(a * 0.5, b * 0.5)`) and Kokoro's own Python package averages the
# voices it is given. Nothing else is involved: no recording, no person. Both
# are made from Jarvis's own sources (Kokoro voices, a blend and a pace) and
# are checked against the owner's own voice print before they are offered
# (jarvis_voices.blend_check) - the same rule as any recorded voice.
#
#   Ashby - "a warm British butler, not modelled on anyone": 70% bm_george and
#           30% am_michael, spoken as British English, a little slower (0.95).
#   Clara - 60% bf_emma and 40% af_heart: British-leaning and warm, normal pace.
#
# The blends are written into a COPY of the pack's voices.bin, in the two slots
# of MIX_SLOTS, and the copy sits next to the pack as BLEND_FILE. Why a copy
# and not a small extra file: sherpa-onnx counts the voices from the model, not
# from the file, and refuses a voices file of any other size ("Corrupted
# --kokoro-voices ... Expected #floats: 7050240, actual: 7311360", seen with
# sherpa-onnx 1.13.8 when two rows were appended). So the file is the same size
# as the pack's own - 28 MB - with two voices' tables replaced. The pack's own
# voices.bin is never opened for writing.
#
# The file is made on the owner's PC by `py -3 jarvis_kokoro.py --make-blends`
# from the installed pack, and both ends are pinned: the pack's voices.bin must
# be the one the blends were made from (V1_VOICES_SHA256) and the result must be
# the file whose SHA-256 is BLEND_SHA256, or nothing is written. The sums are
# done in double precision and stored as 32-bit numbers - the same on every
# machine - so the pin can be exact.

#: The pinned pieces (see above). BLEND_SHA256 is the SHA-256 of the WHOLE
#: blend file; V1_VOICES_SHA256 is the SHA-256 of the v1.0 pack's voices.bin.
V1_VOICES_SHA256 = "1c5a5b983d3d50d8586d437a51f3faa2da7919ce76a013c081e65671a3447c29"
BLEND_FILE = "voices-jarvis.bin"
BLEND_SHA256 = "5916383e8542460a3e1862a4ea41623b2f1cec98d10973a4a1040662ce11b057"

#: The two voices, in the order they are listed (the top of the picker).
#: `parts`: (a voice of the pack, its weight) - the weights add up to 1.
#: `pace`: times the owner's own speaking speed (Ashby is a little slower).
#: `accent`: "british" is asked for espeak's British English like bf_/bm_.
MIX = {
    "mix_ashby": {
        "name": "Ashby", "label": "Ashby (made for Jarvis)",
        "detail": ("A warm British butler, calm and a little slower. Blended from two "
                   "Kokoro voices; not modelled on anyone."),
        "parts": (("bm_george", 0.7), ("am_michael", 0.3)),
        "pace": 0.95, "accent": "british",
    },
    "mix_clara": {
        "name": "Clara", "label": "Clara (made for Jarvis)",
        "detail": ("A warm woman's voice that leans British. Blended from two Kokoro "
                   "voices; not modelled on anyone."),
        "parts": (("bf_emma", 0.6), ("af_heart", 0.4)),
        "pace": 1.0, "accent": "british",
    },
}
MIX_IDS = tuple(MIX)

#: What the picker says when the blends are not there, in plain words.
BLENDS_NEED_V1 = ("Ashby and Clara, two voices made for Jarvis, need the newer voice pack "
                  "(Kokoro v1.0).")
BLENDS_TO_MAKE = ("Ashby and Clara, two voices made for Jarvis, are not made yet. To make "
                  "them, run the one line under \"Make Ashby and Clara\" in backend\\README.md "
                  "on your PC, then restart Jarvis.")
BLENDS_RESTART = "Ashby and Clara are made. Restart Jarvis to hear them."
BLENDS_BAD = ("The file that holds Ashby and Clara is not the one expected, so they are not "
              "offered. Run the one line under \"Make Ashby and Clara\" in backend\\README.md "
              "again, then restart Jarvis.")

_PICK = {V019: V019_PICK, V1: V1_PICK, V1MIX: MIX_IDS + V1_PICK, "": V019_PICK}

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
    the four English groups; "Ashby (made for Jarvis)" for a blended voice."""
    if not isinstance(name, str) or len(name) < 2:
        return str(name)
    if name in MIX:
        return MIX[name]["label"]
    head = f"{_ACCENT.get(name[0], '')} ({_SEX.get(name[1], '')})".strip()
    if name[0] not in _ACCENT or name[1] not in _SEX or name[2:3] not in ("", "_"):
        return f"Voice {name}"
    who = name[3:].replace("_", " ").title()
    return f"{head} - {who}" if who else head


def known(name) -> bool:
    """`name` is a voice of either pack (a saved choice may be checked
    without knowing which pack is installed), or one of the two blended
    voices made for Jarvis."""
    return isinstance(name, str) and (name in V1_NAMES or name in V019_NAMES or name in MIX)


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
    missing or is neither pack (a v1.1 pack, or a damaged file). The blend
    file (BLEND_FILE) is Kokoro v1.0's size, so it is "v1" here too - the
    PACK; table_kind_of_file() is the one that tells them apart."""
    try:
        size = os.path.getsize(path)
    except (OSError, TypeError, ValueError):
        return ""
    for kind in (V019, V1):
        if size == voices_file_size(kind):
            return kind
    return ""


def table_kind_of_file(path) -> str:
    """kind_of_file(), except "v1mix" when the file is the pinned blend file
    (blend_ok): the one whose table of names - and so whose `sid`s - has
    Ashby and Clara in it."""
    kind = kind_of_file(path)
    return V1MIX if kind == V1 and blend_ok(path) else kind


#: (path, modified time, size, pin) -> the file's SHA-256 matched the pin.
#: A 28 MB hash is a few hundredths of a second, but this is asked for every
#: sentence Jarvis speaks.
_BLEND_OK: dict = {}


def blend_ok(path) -> bool:
    """`path` is the pinned blend file: Kokoro v1.0's size and exactly the
    SHA-256 of BLEND_SHA256. Nothing else is trusted to hold Ashby and Clara -
    a damaged file, or one made for another pack, is not used. Never raises."""
    try:
        st = os.stat(path)
    except (OSError, TypeError, ValueError):
        return False
    if st.st_size != voices_file_size(V1):
        return False
    pin = str(BLEND_SHA256 or "").lower()
    if not pin:
        return False
    key = (str(path), st.st_mtime_ns, st.st_size, pin)
    hit = _BLEND_OK.get(key)
    if hit is None:
        try:
            hit = file_sha256(path) == pin
        except OSError:
            return False
        if len(_BLEND_OK) > 8:
            _BLEND_OK.clear()
        _BLEND_OK[key] = hit
    return hit


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def blend_file_beside(voices_file) -> str:
    """Where the blend file sits: next to the pack's voices file."""
    return os.path.join(os.path.dirname(str(voices_file)), BLEND_FILE)


def blend_state(voices_file) -> str:
    """What is beside this voices file: "ready" (the pinned blend file is
    there), "bad" (a file of that name that is not the pinned one), or
    "none"."""
    p = blend_file_beside(voices_file)
    if not os.path.isfile(p):
        return "none"
    return "ready" if blend_ok(p) else "bad"


def voice_pace(name) -> float:
    """The pace a voice speaks at, times the owner's own speed: 1.0 for every
    voice except Ashby (0.95, a little slower)."""
    row = MIX.get(name) if isinstance(name, str) else None
    return float(row["pace"]) if row else 1.0


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
    rows = []
    for n in pickable(kind):
        row = {"id": n, "label": label_of(n)}
        if n in MIX:
            # One plain line under the name: what it is. (Only these two rows
            # carry a `detail`; the apps show it when there is one.)
            row["detail"] = MIX[n]["detail"]
        rows.append(row)
    if current and current not in pickable(kind) and current in names(kind):
        rows.append({"id": current, "label": f"{label_of(current)} (your current choice)"})
    return rows


def accent_lang(kind: str, name, british: Optional[str] = None) -> Optional[str]:
    """The espeak voice to ask for with this voice, or None for the engine's
    own default (American English). Only Kokoro v1.0 takes a language per
    call; v0.19's speech is always American, so None there. Ashby and Clara
    are British voices too (MIX `accent`)."""
    if family(kind) != V1 or not isinstance(name, str):
        return None
    if not (name.startswith("b") or (name in MIX and MIX[name]["accent"] == "british")):
        return None
    return (british or "").strip() or BRITISH_LANG


def pack_words(kind: str) -> dict:
    """{"kind", "name", "voices"}: what is installed, in words. The blend file
    is still Kokoro v1.0 (the pack), with its 54 voices."""
    kind = family(kind)
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


# --------------------------------------------------------------------------
#   Making the blend file (owner-run: `py -3 jarvis_kokoro.py --make-blends`)
# --------------------------------------------------------------------------

_PER_VOICE = 510 * 256  # numbers in one voice's table

#: The ONE PowerShell line the owner runs to make the blend file (it is also
#: in backend/README.md under "Make Ashby and Clara"; test_blend_voices.py
#: checks they agree). The folder is where apply-patches.ps1 put the backend,
#: the same one the mouth-timing step uses. It writes voices-jarvis.bin next
#: to the voice pack and touches nothing else.
MAKE_LINE = ('Push-Location "C:\\Users\\pcadmin\\Documents\\Claude\\Open jarvis files\\'
             'Desktop program"; py -3 .\\jarvis_kokoro.py --make-blends; Pop-Location')


def _read_table(path) -> array:
    """A voices.bin as a flat array of 32-bit numbers (little-endian on disk)."""
    table = array("f")
    with open(path, "rb") as f:
        table.frombytes(f.read())
    if sys.byteorder == "big":  # pragma: no cover - the PC is little-endian
        table.byteswap()
    return table


def make_blend_table(table: array) -> array:
    """The v1.0 pack's table with the two blends written over their slots
    (MIX_SLOTS), everything else untouched. Each new number is
    `wa * a + wb * b` worked out in double precision and stored as a 32-bit
    number, so it is the same on every machine and matches numpy's
    `(a.astype(float64) * wa + b.astype(float64) * wb).astype(float32)`
    exactly."""
    out = array("f", table)
    for vid, row in MIX.items():
        slot = V1_NAMES.index(MIX_SLOTS[vid])
        (name_a, wa), (name_b, wb) = row["parts"]
        ia, ib = V1_NAMES.index(name_a), V1_NAMES.index(name_b)
        a = table[ia * _PER_VOICE:(ia + 1) * _PER_VOICE]
        b = table[ib * _PER_VOICE:(ib + 1) * _PER_VOICE]
        out[slot * _PER_VOICE:(slot + 1) * _PER_VOICE] = array(
            "f", [wa * x + wb * y for x, y in zip(a, b)])
    return out


def default_tts_dir() -> str:
    """Where the install line puts the pack: <config dir>\\voice-models\\tts."""
    base = (os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
            or os.path.join(os.path.expanduser("~"), ".openjarvis"))
    return os.path.join(base, "voice-models", "tts")


def build_blends(pack_dir: Optional[str] = None) -> tuple:
    """Makes BLEND_FILE beside the pack's voices.bin from that voices.bin:
    (True | False, one plain sentence saying what happened). Never opens the
    pack's own file for writing, writes nothing unless the pack is the pinned
    Kokoro v1.0 AND the result is the pinned file, and does nothing (and says
    so) when the pinned file is already there."""
    d = pack_dir or default_tts_dir()
    src = os.path.join(d, "voices.bin")
    out = os.path.join(d, BLEND_FILE)
    if not os.path.isfile(src):
        return False, (f"There is no voices.bin in {d}. Ashby and Clara are made from the "
                       f"Kokoro v1.0 voice pack: install it first (the one line under "
                       f"\"Upgrade the voice pack to Kokoro v1.0\" in backend\\README.md).")
    if kind_of_file(src) != V1:
        return False, (f"The voice pack in {d} is not Kokoro v1.0, so nothing was made. "
                       f"Ashby and Clara need the newer voice pack.")
    if not str(BLEND_SHA256 or "").strip() or not str(V1_VOICES_SHA256 or "").strip():
        return False, "The blended voices are not pinned in this copy of Jarvis, so nothing was made."
    if os.path.isfile(out) and blend_ok(out):
        return True, f"Already done: Ashby and Clara are in {out}. Restart Jarvis to hear them."
    try:
        if file_sha256(src) != str(V1_VOICES_SHA256).lower():
            return False, (f"The voices.bin in {d} is not the one Ashby and Clara were made "
                           f"from, so nothing was made.")
        table = make_blend_table(_read_table(src))
        if sys.byteorder == "big":  # pragma: no cover
            table.byteswap()
        tmp = out + ".tmp"
        with open(tmp, "wb") as f:
            f.write(table.tobytes())
        if file_sha256(tmp) != str(BLEND_SHA256).lower():
            os.remove(tmp)
            return False, ("The blended voices did not come out as expected, so nothing was "
                           "kept. Nothing else was changed.")
        os.replace(tmp, out)
    except OSError as exc:
        return False, f"Could not make the file ({type(exc).__name__}). Nothing else was changed."
    return True, (f"OK - Ashby and Clara are in {out} (28 MB, next to your voice pack, which was "
                  f"not touched). Restart Jarvis to hear them.")


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--make-blends" not in args:
        print("usage: py -3 jarvis_kokoro.py --make-blends [--pack <the voice pack's folder>]\n"
              "  Makes Ashby and Clara (two blended voices) beside the Kokoro v1.0 pack.")
        return 2
    pack = None
    if "--pack" in args:
        i = args.index("--pack")
        pack = args[i + 1] if i + 1 < len(args) else None
    ok, words = build_blends(pack)
    print(words)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
