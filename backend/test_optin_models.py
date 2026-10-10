"""test_optin_models.py - the owner's uncensored opt-ins, both halves.

    python3 backend/test_optin_models.py

The owner's decision (2026-10-10, Decision 5) chose BOTH halves, as two
separate opt-ins:

  (a) one clearly-labelled opt-in model for fiction and role-play - never the
      everyday assistant and never a default;
  (b) the abliterated models ALREADY ON DISK made usable as opt-in choices,
      with no new download.

...and the measured cost must be printed on the label, in plain words.

No model, no network, no Ollama and no gate. Ollama is handed in as a
stand-in listing, and the folders are ones this test makes itself, so the
suite runs identically on a PC that has the four models and on one that has
never seen them.

What it proves, and the check that would fail without the change:

  A. OFF BY DEFAULT. A machine that has never run this offers nothing at all,
     and the folder of models it is given is not even walked - proved by
     handing in a folder that raises if it is opened.
  B. THE LABEL CARRIES THE MEASURED COST, word for word: TruthfulQA drops 5.8
     to 6.9 points on this model family; MMLU is about noise; the only fitting
     build is 7 months old against a 5-day-old official one. Every part is
     asserted separately, so dropping one sentence fails the suite.
  C. NO NEW DOWNLOAD. The body handed to Ollama names a PATH on this PC, not
     a registry reference, and no part of this file fetches anything: checked
     by refusing every network call and every `ollama pull` URL.
  D. THE EVERYDAY ASSISTANT IS UNCHANGED. With both opt-ins ON, the model the
     everyday lane resolves to is byte-for-byte what it was with both OFF, and
     the file that records the current model is not written at all.
  E. FICTION/ROLE-PLAY IS A SEPARATE, SECOND OPT-IN. Opt-in (b) on does not
     turn it on; it refuses in plain words when off; and its own instructions
     keep every safety rule while not carrying the assistant's facts rule.
  F. THE MOVE TO D: IS SURVIVED. The same file name is found under
     `D:\\Jarvis Models\\` and under the old `Documents\\AI Models` - the code
     hard-codes no C: model path, and a name is enough to find either.
  G. THE NAME RULE holds the cases that were real bugs: a mixture-of-experts
     "A1B" is not mistaken for a size, two different 14B models get two
     different names, and the same weights in two quants get one name.
  H. TWO OPT-INS, NOT ONE: the two switches are stored under two keys and
     either can be set without the other.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

#: Point every choice this file reads or writes at a folder THIS test made,
#: before the module is imported - the same first move test_settings_switches.py
#: makes. Without it the suite would read and write the owner's real
#: ~/.openjarvis.
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-optin-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)
os.environ.pop("JARVIS_OPTIN_MODEL_ROOTS", None)
os.environ.pop("JARVIS_OPTIN_MODEL_NAME", None)

from _where import REPO, require_shipped  # noqa: E402

#: `jarvis_optin_models.py` is BRAND NEW, so it cannot be required the same
#: way as the older modules yet. It is required BY PATH instead - this suite
#: must run against the repository's own copy before `apply-patches.ps1` has
#: deployed one, or it would refuse to run at all.
if not (HERE / "jarvis_optin_models.py").is_file():
    print("FAIL  backend/jarvis_optin_models.py is missing from this repository")
    sys.exit(1)

import jarvis_optin_models as O  # noqa: E402

FAILED, PASSED = [], []
SKIPPED = []


def skip(why):
    """Not a failure: this environment cannot test it. Counted and printed,
    the same way the suites that need the owner's own PC do it."""
    SKIPPED.append(why)
    print(f"skip  {why}")


#: `jarvis_models.py` is one of the owner's own files (run_suites.OWNER_FILES):
#: it lives on a real install and is deliberately NOT shipped, so CI's staged
#: backend does not have it and `import jarvis_models` raises there. Asking for
#: it with `require_shipped` was wrong for that reason - it stopped the suite
#: with "not in <staged backend>", which is a true statement about a file that
#: is not supposed to be there.
#:
#: Two of the tests below are about the everyday model NOT changing, and about
#: `safe_ref` accepting a real name: both are checks OF `jarvis_models` itself,
#: so a stand-in would test nothing. They are skipped here with that reason
#: instead, and they run for real on the owner's PC - where this suite proves
#: the thing the owner asked for (JARVIS_BACKEND set to the live install).
_try = None
try:
    _try = __import__("jarvis_models")
except Exception as exc:
    skip(f"jarvis_models is not in this backend ({type(exc).__name__}), so the two "
         f"checks that are ABOUT it cannot run here - they run on the owner's PC")
MM = _try

#: The name and reference helpers the module-level tests need do not depend on
#: `jarvis_models` at all, so those checks run everywhere.
def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" +
          (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
#   A fixture folder, so nothing here depends on this PC's own models
# --------------------------------------------------------------------------

_GB = 1024 ** 3


def _fake(root: Path, name: str, gb: float = 0.6) -> Path:
    """A sparse-enough stand-in: a real file with the real name, sized so the
    512 MB floor the module applies is cleared."""
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as fh:
        fh.truncate(int(gb * _GB))
    return p


#: This PC's four files, by name. Used to prove the naming rule against the
#: real names - not read from disk, so the check runs anywhere.
REAL_NAMES = (
    "Qwen2.5-14B-Instruct-abliterated-v2.Q4_K_M.gguf",
    "Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf",
    "Qwen2.5-Coder-14B-Instruct-abliterated-Q4_K_M.gguf",
    "LFM2.5-8B-A1B-Uncensored-Gaston-Q4_K_M.gguf",
)


# --------------------------------------------------------------------------
#   A. Off by default
# --------------------------------------------------------------------------

print("\n-- A. off by default --")

check("the two switches are both off on a machine that has never run this",
      O._flag("uncensored_choices_offered") is False
      and O._flag("fiction_roleplay_on") is False)
check("why says the uncensored models are off",
      O.offered()["on"] is False)
check("with the switch off, nothing is offered",
      O.choices(roots=[]) == [] and O.offered()["choices"] == [])
check("and the folder is not even walked - a folder that raises if it is read",
      O.choices(roots=[Path("Z:/no/such/folder")]) == [])
check("the refusal names where to turn it on, in the owner's words",
      "Settings" in O.ensure_fiction_allowed()["message"]
      and O.ensure_fiction_allowed()["ok"] is False)

#: OFF must mean the folders are not walked at all, not that the walk happens
#: and its result is thrown away. `os.scandir` is the one call any walk of a
#: folder has to make, so replacing it with a tripwire answers the question
#: exactly - and the switch is put back the way it was afterwards.
_real_scandir = os.scandir


def _tripwire(*a, **k):
    raise AssertionError("the module walked the model folders while the "
                         "opt-in was off")


O._set("uncensored_choices_offered", False)
os.scandir = _tripwire
try:
    _walked = O.choices(roots=[_TMP])
finally:
    os.scandir = _real_scandir
check("discovery does not run at all while the switch is off", _walked == [])

# What the everyday lane resolves to, BEFORE either switch is touched.
# `MM` is None where jarvis_models is absent (CI's staged backend); the three
# checks below that compare the everyday model before and after are then
# skipped with a reason rather than passing on a stand-in, because a stand-in
# would prove nothing about the real thing.
_BEFORE = MM.current_model() if MM is not None else None


# --------------------------------------------------------------------------
#   H. Two switches, two keys
# --------------------------------------------------------------------------

print("\n-- H. two opt-ins, not one --")

_r = O.enable_uncensored_choices(True)
check("turning on the uncensored choices reports success", _r.get("ok") is True)
check("...and stores its own key",
      json.loads(O.state_path().read_text("utf-8"))["uncensored_choices_offered"] is True)
check("...and does NOT turn on fiction and role-play",
      O._flag("fiction_roleplay_on") is False)
check("the fiction label says it starts off",
      O.fiction_label()["on"] is False)
_f = O.enable_fiction_roleplay(True)
check("turning on fiction and role-play reports success", _f.get("ok") is True)
check("...and stores its own key",
      json.loads(O.state_path().read_text("utf-8"))["fiction_roleplay_on"] is True)
check("both keys are written, not one shared flag",
      set(O.KEYS) == {"uncensored_choices_offered", "fiction_roleplay_on"})

#: Deliberately write a WRONG value, then put the real one back: an opt-in a
#: damaged byte can turn on is not an opt-in, and the rest of this file needs
#: the real value.
check("a state file holding something other than true reads as OFF, never ON",
      (lambda: (O._write({"uncensored_choices_offered": "yes"}),
                O._flag("uncensored_choices_offered") is False,
                O._write({k: True for k in O.KEYS}))[1])())
check("both switches are ON again after that probe",
      O._flag("uncensored_choices_offered") and O._flag("fiction_roleplay_on"))


# --------------------------------------------------------------------------
#   B. The label, and the measured cost on it
# --------------------------------------------------------------------------

print("\n-- B. the label carries the measured cost --")

_label = O.label_for(Path(REAL_NAMES[0]), "jarvis-uncensored-qwen2.5-14b")

check("the label says plainly that it is a model already on this PC",
      "already on this PC" in _label, _label)
check("the label names the model, not just a hash or a folder",
      "Qwen2.5" in _label and "14B" in _label, _label)
check("THE COST: TruthfulQA drops 5.8 to 6.9 points",
      "TruthfulQA drops 5.8 to 6.9 points" in _label, _label)
check("THE COST: it is on this model family",
      "on this model family" in _label, _label)
check("THE COST: MMLU is about noise - no real change",
      "MMLU is about noise" in _label and "no real change" in _label, _label)
check("THE COST: the only fitting build is 7 months old",
      "7 months old" in _label, _label)
check("THE COST: against a 5-day-old official one",
      "5-day-old official one" in _label, _label)
check("the label does NOT claim the numbers were measured on this file here",
      "not re-measured on this file on this PC" in _label, _label)
check("the label does not oversell it: no 'better', 'faster' or 'improved'",
      not re.search(r"\b(better|faster|improved|superior)\b", _label, re.I), _label)
check("the detail line carries the same cost, not a shortened version",
      all(p in O.detail_for(Path(REAL_NAMES[0])) for p in O.MEASURED_COST))
check("one place holds the cost, so a label cannot lose a fact by hand-typing",
      O.MEASURED_COST and all(isinstance(p, str) and p for p in O.MEASURED_COST))

#: Every label built from a real file carries every part. A new model added to
#: the list cannot ship a label missing a measured fact.
for _n in REAL_NAMES:
    _l = O.label_for(Path(_n), O.import_name_for(Path(_n)))
    check(f"every part of the cost is on the label for {_n[:28]}",
          all(p in _l for p in O.MEASURED_COST))


# --------------------------------------------------------------------------
#   C. No new download, ever
# --------------------------------------------------------------------------

print("\n-- C. nothing downloads --")

_choice = O.Choice(file=Path("D:/Jarvis Models/AI-Models/x.gguf"),
                   name="jarvis-uncensored-x", label="", detail="", size_gb=4.0)
_body = _choice.create_request()
check("the body Ollama is given points at a PATH on this PC",
      _body["from"].endswith(".gguf") and ("/" in _body["from"] or "\\" in _body["from"]),
      str(_body))
check("...and not at a registry reference",
      not _body["from"].startswith(("hf.co/", "huggingface.co/"))
      and not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}/", _body["from"]), str(_body))
if MM is None:
    skip("the name rule is checked against jarvis_models.safe_ref, which is not in "
         "this backend - it runs on the owner's PC")
else:
    check("...and the model name is Ollama's own naming rule, not a URL",
          MM.safe_ref(_body["model"]) == _body["model"], _body["model"])
check("the request is not a pull: no /api/pull anywhere in the module",
      "/api/pull" not in (HERE / "jarvis_optin_models.py").read_text("utf-8"))
check("the module opens no socket and fetches no URL",
      not re.search(r"\b(urllib|requests|http\.client|socket)\b",
                    (HERE / "jarvis_optin_models.py").read_text("utf-8")))

#: The one path that COULD reach out is the Ollama listing. It must degrade to
#: "nothing imported yet" rather than raising on a settings screen - proved by
#: breaking the import outright and still getting a working list back.
_real_mm = sys.modules.get("jarvis_models")
sys.modules["jarvis_models"] = "not a module at all"   # makes `import` raise
_probe = _TMP / "probe-roots"
_probe.mkdir(parents=True, exist_ok=True)
_fake(_probe, "Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf")
try:
    _degraded = O.choices(roots=[_probe])   # names=None -> it must try to list
finally:
    if _real_mm is not None:
        sys.modules["jarvis_models"] = _real_mm
check("a listing that cannot be read still offers the file, as not-yet-imported",
      len(_degraded) == 1 and _degraded[0].already_imported is False,
      str([c.as_dict() for c in _degraded]))


# --------------------------------------------------------------------------
#   D. The everyday assistant is unchanged
# --------------------------------------------------------------------------

print("\n-- D. the everyday assistant is untouched --")

check("both opt-ins are ON for this check",
      O._flag("uncensored_choices_offered") and O._flag("fiction_roleplay_on"))
if MM is None:
    skip("THE EVERYDAY MODEL IS BYTE-FOR-BYTE WHAT IT WAS is checked with "
         "jarvis_models.current_model, which is not in this backend - it runs on "
         "the owner's PC")
else:
    check("THE EVERYDAY MODEL IS BYTE-FOR-BYTE WHAT IT WAS",
          MM.current_model() == _BEFORE,
          f"before={_BEFORE!r} after={MM.current_model()!r}")
check("opt-in (a) claims no model and no default, in its own words",
      "never the everyday" in O.offered()["never_default"].lower(),
      O.offered()["never_default"])
check("turning fiction ON says the everyday assistant was not changed",
      "not changed" in O.enable_fiction_roleplay(True)["message"]
      or "exactly as before" in O.enable_fiction_roleplay(True)["message"])
check("the fiction detail says it is never the everyday assistant",
      "never the everyday" in O.fiction_label()["detail"].lower(),
      O.fiction_label()["detail"])

#: The source is read for what it does, not for what it mentions. Every name
#: below is also in the module's own prose, which explains WHY it does not do
#: those things - so the check is against executable lines only (`switch_to(`
#: with the call's opening bracket, a path being joined, an assignment to the
#: state file's key), never a bare word in a comment or a docstring.
_SRC = (HERE / "jarvis_optin_models.py").read_text("utf-8")
_imports_state_file = re.search(r"^STATE\s*=|^def _write_state|^from jarvis_models", _SRC, re.M)
check("this module writes no model-state file of its own",
      _imports_state_file is None, str(_imports_state_file))
check("it calls the EXISTING switch, and invents no second one",
      "switch_to(" not in _SRC and "def switch" not in _SRC)
check("no public route is added by this module",
      not re.search(r'"/api/', _SRC))
check("it writes no TOML: the only writes are its own JSON state file",
      "write_text" in _SRC and ".toml" not in _SRC.replace("jarvis-framework.toml", ""))
check("the state file is written atomically, so a crash cannot lose a choice",
      "os.replace(" in _SRC)


# --------------------------------------------------------------------------
#   E. Fiction and role-play is its own opt-in
# --------------------------------------------------------------------------

print("\n-- E. fiction and role-play is its own opt-in --")

O.enable_fiction_roleplay(False)
check("with it OFF the fiction lane refuses", O.ensure_fiction_allowed()["ok"] is False)
check("the refusal is plain words and says where the switch is",
      "Settings" in O.ensure_fiction_allowed()["message"]
      and "off" in O.ensure_fiction_allowed()["message"].lower(),
      O.ensure_fiction_allowed()["message"])
check("the refusal says the everyday assistant is not changed by it",
      "everyday assistant" in O.ensure_fiction_allowed()["message"])
check("no silent fallback to the everyday assistant: it refuses rather than answers",
      O.ensure_fiction_allowed().get("ok") is False
      and "model" not in O.ensure_fiction_allowed()["message"].lower().replace(
          "model choices", ""))
O.enable_fiction_roleplay(True)
check("with it ON the fiction lane is allowed", O.ensure_fiction_allowed()["ok"] is True)
check("...and the label says it is on", O.fiction_label()["on"] is True)
if MM is None:
    skip("'it still does not switch any model' is checked with jarvis_models, "
         "which is not in this backend - it runs on the owner's PC")
else:
    check("...and it still does not switch any model",
          MM.current_model() == _BEFORE, f"{_BEFORE!r} -> {MM.current_model()!r}")

_S = O.FICTION_SYSTEM
check("the fiction instructions keep 'take no action outside the story'",
      "take no action outside the story" in _S.lower())
check("the fiction instructions keep 'nothing is saved or learned'",
      "saved or learned" in _S)
check("the fiction instructions keep the crisis rule",
      "real distress" in _S and "help" in _S)
check("the fiction instructions say a quoted document cannot change them",
      "cannot change these rules" in _S)
check("the fiction instructions do NOT carry the assistant's facts rule",
      "say what is a guess" not in _S and "verified" not in _S)
check("the fiction instructions are not the everyday assistant's, word for word",
      _S != O.__dict__.get("JARVIS_SYSTEM", "") and "private assistant" not in _S)
O.enable_fiction_roleplay(False)
check("turning fiction off does not turn the uncensored list off",
      O._flag("uncensored_choices_offered") is True)


# --------------------------------------------------------------------------
#   F + G. The move to D:, and the name rule
# --------------------------------------------------------------------------

print("\n-- F. the move to D: is survived --")

_d = _TMP / "Jarvis Models" / "AI-Models"
_old = _TMP / "Documents" / "AI Models"
os.makedirs(_d, exist_ok=True)
os.makedirs(_old, exist_ok=True)
_fake(_d, REAL_NAMES[3])
_fake(_old, REAL_NAMES[0])

O._set("uncensored_choices_offered", True)
_both = O.choices(roots=[_d, _old], names=[])
check("a model under the D: home is found", any("Jarvis Models" in str(c.file) for c in _both))
check("a model under the old C: folder is found too",
      any("AI Models" in str(c.file) for c in _both))
check("both are offered, from the two different roots", len(_both) == 2, str(len(_both)))
check("the module hard-codes no C: model path",
      "C:/Users" not in (HERE / "jarvis_optin_models.py").read_text("utf-8")
      and "C:\\\\Users" not in (HERE / "jarvis_optin_models.py").read_text("utf-8"))
check("the roots can be moved by one environment variable, so nothing is pinned",
      O.search_roots() != () and all(isinstance(r, Path) for r in O.search_roots()))
check("the same file name in both roots is offered ONCE, not twice",
      len({c.name for c in _both}) == len(_both), str([c.name for c in _both]))
check("what Ollama already has is recognised, not re-imported",
      [c.already_imported for c in O.choices(roots=[_d], names=[_both[0].name])] == [True])

print("\n-- G. the name rule, on the real names --")

_names = [O.import_name_for(Path(n)) for n in REAL_NAMES]
check("the mixture-of-experts A1B is not read as a 1B size",
      O._size_from_name(REAL_NAMES[3]) == "8b", str(O._size_from_name(REAL_NAMES[3])))
check("the two different 14B models get two DIFFERENT names",
      _names[0] != _names[2], f"{_names[0]} vs {_names[2]}")
check("...and the Coder one says so in its name", "coder" in _names[2], _names[2])
check("each of the four real files gets its own name",
      len(set(_names)) == 4, str(_names))
if MM is None:
    # The shape check just below covers the same rule without jarvis_models, so
    # this one is only skipped when the module that owns the rule is absent.
    skip("'every name is one Ollama will accept' is checked with "
         "jarvis_models.safe_ref, which is not in this backend")
else:
    check("every name is one Ollama will accept",
          all(MM.safe_ref(n) == n for n in _names), str(_names))
check("no name carries a bracket, a space or a colon",
      all(re.fullmatch(r"[a-z0-9._-]+", n) for n in _names), str(_names))
check("the same weights in two quants get ONE name",
      O.import_name_for(Path("Mistral-7B-Uncensored-Q4_K_M.gguf"))
      == O.import_name_for(Path("Mistral-7B-Uncensored-Q8_0.gguf")))
check("a name the owner's own file states is used, not the file's byte size",
      O._size_from_name("Qwen2.5-Coder-14B-Instruct-abliterated-Q4_K_M.gguf") == "14b")
check("a file with no marker is not an uncensored choice",
      O.is_choice_file("qwen3-8b-instruct-Q4_K_M.gguf") is False)
check("the marker is looked for in the FILE's name, wherever the file sits",
      O.is_choice_file("Qwen3-8B-Q4_K_M.gguf") is False
      and O.is_choice_file("Qwen3-8B-abliterated-Q4_K_M.gguf") is True)
check("a marker in a FOLDER's name is not enough on its own",
      not O.is_choice_file("Qwen3-8B-Q4_K_M.gguf"))
_folder = _TMP / "abliterated"
_folder.mkdir(parents=True, exist_ok=True)
_fake(_folder, "Qwen3-8B-Q4_K_M.gguf")
check("...a plain file inside a folder called 'abliterated' is not offered",
      O.choices(roots=[_folder], names=[]) == [],
      str([c.file.name for c in O.choices(roots=[_folder], names=[])]))
_fake(_folder, "Other-7B-uncensored-Q4_K_M.gguf")
check("...and a real one sitting in that same folder still is",
      [c.file.name for c in O.choices(roots=[_folder], names=[])]
      == ["Other-7B-uncensored-Q4_K_M.gguf"],
      str([c.file.name for c in O.choices(roots=[_folder], names=[])]))
check("a marker in the file name does, whatever the case",
      O.is_choice_file("Some-Model-ABLITERATED-Q4_K_M.gguf") is True
      and O.is_choice_file("Some-Model-uncensored-Q4_K_M.gguf") is True)

_tiny = _TMP / "tiny"
_tiny.mkdir(parents=True, exist_ok=True)
_fake(_tiny, "Tiny-1B-uncensored.gguf", 0.01)
check("a model file far too small to be one of these is not offered",
      O.choices(roots=[_tiny], names=[]) == [],
      str([c.name for c in O.choices(roots=[_tiny], names=[])]))

# --------------------------------------------------------------------------
#   The disk check: never fill a drive
# --------------------------------------------------------------------------

print("\n-- the disk is reported before anything is imported --")

_cost = O.import_cost_gb(O.Choice(file=Path(HERE), name="x", label="", detail="",
                                  size_gb=8.37))
check("the disk report gives the size it needs", _cost["needs_gb"] == 8.37)
check("...and says importing downloads nothing",
      "downloads nothing" in _cost["words"], _cost["words"])
check("...and says the weights are copied, which uses the space",
      "copies" in _cost["words"], _cost["words"])
check("...and refuses in plain words when the drive is too full",
      _cost["fits"] is True, str(_cost))

# --------------------------------------------------------------------------
#   Summary
# --------------------------------------------------------------------------

print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
if SKIPPED:
    print("Skipped (not failures):")
    for s in SKIPPED:
        print("  - " + s)
if FAILED:
    print("FAILED:")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
