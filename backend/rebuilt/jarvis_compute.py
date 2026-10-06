"""jarvis_compute.py - what runs on which card.

REBUILT. Three call sites, and between them they name every field:

    jarvis_hud.py:1425   jarvis_compute.plan().as_dict()
    jarvis_hud.py:2233   cp = jarvis_compute.plan()
    jarvis_hud.py:2234   cp.text_model, cp.text_on, cp.vision_resident,
                         cp.tts_resident, cp.simulated

`[compute] prefer` in the config is the only setting, and its own comment is
the specification:

    "speed":      the current-size model on the fastest card at full speed,
                  the second card carries vision + voice resident so nothing
                  swaps.
    "capability": the biggest model the pair can hold, generation bounded by
                  the slower card (a P100 is Pascal: ~2-3x slower per token).

WHICH CARD IS "FIRST" (fixed 2026-09-24). This used to rank "fastest card =
most free memory". With the second card the owner is adding - an RTX 2060
12 GB beside the 2080 Super 8 GB - that put everyday chat on the 2060: more
free memory, about two thirds the memory speed (docs/MODEL-TOPOLOGY.md, "The
planned second card"). The everyday card is now chosen by ONE rule set, in
`everyday_card()` below, which jarvis_second_card.py uses too (it calls this
one rather than keeping a copy):

    1. `[compute] primary_gpu` in the toml - a UUID ("GPU-...") or an
       nvidia-smi index - when it names a card that is there;
    2. otherwise the card the owner himself pinned (the "Everyday chat runs
       on" setting, 2026-10-05), when nvidia-smi still sees that card;
    3. otherwise THE CARD THE MODEL IS OBSERVED ON - the same one reading of
       `ollama ps` and nvidia-smi that jarvis_second_card.where_chat_runs()
       reports with. This is the 2026-10-06 fix ("option B: true to its
       reporting"): `plan()` used to skip that reading and fall back to the
       monitor rule, so the HUD banner could name the 2080 SUPER - and the
       Brain pane, and the phone - while the model was really on the 2060.
       On the owner's PC those two cards are different cards
       (docs/MEASURED-2026-10-05-owner-pc.md), so this was not a corner.
    4. otherwise the card a monitor is plugged into (nvidia-smi's
       `display_active`), because the owner plugs the monitors into the
       fast card (MODEL-TOPOLOGY's install checklist, step 2);
    5. otherwise nvidia-smi index 0.

`everyday_card()` returns the card AND the sentence saying which rule chose
it, so a screen can say why rather than just what - and so a caller can tell
an OBSERVATION (rule 3) from the owner's own choice (rules 1 and 2) from the
ASSUMPTION (rules 4 and 5). `primary()` is kept exactly as it was: the
monitor rule alone, which several callers and tests read directly.

`simulated` is the honest field. When no GPU can be interrogated this returns
a plan anyway - the HUD prints one at startup and must not crash on a machine
with no card - but it says so, rather than reporting a confident layout for
hardware nobody looked at.

WHY THE READER LIVES HERE AND NOT IN jarvis_second_card.py. "One reader" is
the whole point (jarvis_second_card's own `_observed_card` docstring says
so), and the two modules already import one way only: jarvis_second_card
imports THIS module. So the reading is taken here, and jarvis_second_card
delegates to it - `where_chat_runs` still reports with it, `_primary` now
plans with it, and there is exactly one copy of the rule. The one thing this
module cannot know is which of the second card's own lane processes to leave
out (they run on another card by design - `_model_process`'s own comment),
so that list is a parameter the caller passes, defaulting to "none to leave
out".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

#: Every request here goes straight to the address, never through a proxy
#: (bug audit 3, CONN-1): see jarvis_local_http.py. Wrapped, so a backend
#: without that file still runs - the relay is then the plain one, exactly as
#: before it existed.
try:
    import jarvis_local_http
except Exception:
    jarvis_local_http = None  # type: ignore

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


@dataclass
class Device:
    index: int
    name: str
    total_mb: int
    free_mb: int
    # Added 2026-09-24 for the primary-card rule and jarvis_second_card.py.
    # Defaults, so a Device built with the original four fields still works.
    uuid: str = ""
    compute_cap: Optional[float] = None     # None: nvidia-smi did not say
    display_active: Optional[bool] = None   # None: nvidia-smi did not say


@dataclass
class Plan:
    text_model: str = "unknown"
    text_on: str = "cpu"
    vision_resident: bool = False
    tts_resident: bool = False
    simulated: bool = True
    prefer: str = "speed"
    devices: list = field(default_factory=list)
    why: str = ""

    @property
    def total_mb(self) -> int:
        """Total VRAM across the cards, in MB. 0 when nothing was measured.

        jarvis_models.py:489 reads this to size its model budget:

            pl = C.plan()
            if pl.total_mb: return pl.total_mb
            ...
            return int(os.environ.get("JARVIS_VRAM_MB", "8192"))

        wrapped in `except Exception: pass`. Without the attribute the
        AttributeError was SWALLOWED and every machine silently scored its
        models against a fabricated 8192 MB. 0 here falls through to that same
        default honestly, because 0 means "no card was measured".
        """
        total = 0
        for d in self.devices:
            v = d.get("total_mb") if isinstance(d, dict) else getattr(d, "total_mb", 0)
            try:
                v = int(v or 0)
            except (TypeError, ValueError):
                continue
            # Negative is not zero. `if pl.total_mb: return pl.total_mb`
            # above only falls through to the honest default on exactly 0 -
            # a negative reading (corrupt or injected device data; real
            # nvidia-smi cannot emit one, but nothing here enforced that)
            # is truthy and was trusted as a genuine measurement, reported
            # with simulated=False as if it were real VRAM.
            if v > 0:
                total += v
        return total

    def as_dict(self) -> dict:
        d = asdict(self)
        d["devices"] = [asdict(x) if not isinstance(x, dict) else x
                        for x in self.devices]
        d["total_mb"] = self.total_mb      # a property, so asdict misses it
        return d


def _cfg(key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get("compute", {}).get(key, default)
    except Exception:
        return default


# --------------------------------------------------------------------------
#   The owner's own pin on a card (2026-10-05)
#
#   THE SAME FILE jarvis_second_card.py writes and reads (chat-card.json in
#   the config folder) - the address is spelled here as well, and NOT
#   imported from there, because that module imports this one. Duplicating
#   the FILE NAME is a far smaller thing than duplicating the RULE: if the
#   two ever disagreed about which card is "the everyday card", the banner
#   and the running model could name different cards again, which is the
#   whole reason this file changed. A test
#   (test_second_card.py::t_the_banner_and_the_running_card_cannot_disagree)
#   reads both modules' answer for one machine and fails if they differ.
# --------------------------------------------------------------------------

#: The pin file, beside second-card.json (jarvis_second_card). A card id is
#: the only value it may hold; anything else reads as "not pinned".
PIN_FILE = "chat-card.json"
_UUID_RE = re.compile(r"GPU-[0-9A-Fa-f-]{8,64}")
#: The everyday Ollama, the same default jarvis_second_card uses.
MAIN_OLLAMA_PORT = 11434


def _config_dir() -> Path:
    """Where Jarvis keeps its own settings files. The same answer as
    jarvis_second_card._config_dir, read the same way (`fw.CONFIG_DIR` when
    the framework names one, else the environment, else ~/.openjarvis)."""
    cdir = getattr(fw, "CONFIG_DIR", None) if fw is not None else None
    if cdir:
        return Path(cdir)
    return Path(os.environ.get("OPENJARVIS_CONFIG_DIR")
                or os.environ.get("JARVIS_CONFIG_DIR")
                or (Path.home() / ".openjarvis"))


def read_pin() -> Optional[str]:
    """The card id the owner pinned everyday chat to, or None for "leave it
    to Ollama". A missing or broken file reads as None - the default, and
    never an invented card."""
    try:
        raw = json.loads((_config_dir() / PIN_FILE).read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    want = str(raw.get("card") or "").strip()
    return want if want and _UUID_RE.fullmatch(want) else None


def main_ollama_url() -> str:
    """The everyday Ollama's address. Loopback unless the owner set
    OLLAMA_URL, exactly as jarvis_second_card._main_ollama_url reads it."""
    return (os.environ.get("OLLAMA_URL") or f"http://127.0.0.1:{MAIN_OLLAMA_PORT}").rstrip("/")


# --------------------------------------------------------------------------
#   Reading the cards
# --------------------------------------------------------------------------

#: What is asked for. `compute_cap` only exists in newer drivers' nvidia-smi
#: (an older one refuses the WHOLE query, saying the field is not a valid
#: field to query), so a refusal is retried without it, and the generation
#: is then looked up by name (COMPUTE_BY_NAME) or left unknown.
FIELDS_FULL = "index,uuid,name,memory.total,memory.free,compute_cap,display_active"
FIELDS_OLD = "index,uuid,name,memory.total,memory.free,display_active"
FIELDS_OLDEST = "index,name,memory.total,memory.free"

#: Compute capability by marketing name, for a driver too old to report it.
#: Checked in order; the first substring found wins. Only families whose
#: every member shares one capability are listed; anything else is None,
#: which jarvis_second_card treats as "unknown, so not capable".
COMPUTE_BY_NAME = (
    ("ADA", 8.9),
    ("RTX 5000 ADA", 8.9), ("RTX 4000 ADA", 8.9), ("RTX 4500 ADA", 8.9), ("RTX 6000 ADA", 8.9),
    ("RTX A6000", 8.6), ("RTX A5000", 8.6), ("RTX A4500", 8.6), ("RTX A4000", 8.6), ("RTX A2000", 8.6),
    ("RTX 50", 12.0), ("RTX 40", 8.9), ("RTX 30", 8.6), ("A100", 8.0), ("H100", 9.0), ("A10", 8.6),
    ("RTX 20", 7.5), ("GTX 16", 7.5), ("TITAN RTX", 7.5), ("QUADRO RTX", 7.5),
    ("TESLA T4", 7.5), ("TITAN V", 7.0), ("V100", 7.0),
    ("P100", 6.0), ("P40", 6.1), ("GTX 10", 6.1), ("TITAN X", 6.1),
    ("GTX 9", 5.2),
)

_CACHE_SECONDS = 30.0
_cache: dict = {"at": -1e9, "cards": None, "fields": ""}


def _run_smi(args: list) -> Optional[str]:
    """nvidia-smi's stdout, or None if it is absent or refused. Never raises.
    Replaced in tests with recorded output."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe] + list(args), capture_output=True, text=True,
                             timeout=10)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout


# --------------------------------------------------------------------------
#   Which card the MODEL's own process is on (the one reader)
#
#   THE FACTS THAT MATTER HERE, and they are the reason this is one function
#   and not two. `where_chat_runs()` (jarvis_second_card.py) tells the owner
#   where chat really is; `plan()` says where Jarvis will run things. They
#   used to be two readings of the machine, and they disagreed - the plan
#   used the monitor rule while the report named the card the model was on
#   (owner's decision, 2026-10-06, "option B: true to its reporting"). Now
#   both call `observed_card()` below, so they are the same reading.
# --------------------------------------------------------------------------

#: nvidia-smi's process list, in the CSV shape _run_smi gives back.
_APPS_FIELDS = "--query-compute-apps=pid,process_name,gpu_uuid,used_memory"


def query_apps() -> list:
    """[(pid, process name, card uuid, used MiB)] for every process
    nvidia-smi names on a card. [] when it names none or cannot be asked -
    some Windows drivers never name the program using a card
    (docs/MEASURE-CARDS.md section 2), and that reads as "cannot tell",
    never as "nothing is running"."""
    out = []
    try:
        text = _run_smi([_APPS_FIELDS, "--format=csv,noheader,nounits"])
    except Exception:
        return out
    if not text:
        return out
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
        except (TypeError, ValueError):
            continue
        try:
            used = int(float(parts[3]))
        except (TypeError, ValueError):
            used = None
        out.append((pid, parts[1], parts[2], used))
    return out


def _ps_row(url: Optional[str]) -> Optional[dict]:
    """The everyday Ollama's own answer about what is loaded, or None:
    {"model", "on_card_percent"}. Ollama's `size_vram` against `size` is its
    own statement of how much of the model is on a card
    (docs/MEASURE-CARDS.md section 3). `url` None means "do not ask" - the
    caller only wants the process reading. Never through a proxy
    (jarvis_local_http.py, bug audit 3 CONN-1), and it refuses any address
    that is not this PC: a card reading never comes off the network."""
    if not url:
        return None
    try:
        if (urllib.parse.urlparse(url).hostname or "").lower() not in (
                "127.0.0.1", "localhost", "::1"):
            return None
    except Exception:
        return None
    req = urllib.request.Request(f"{url}/api/ps", method="GET")
    try:
        if jarvis_local_http is not None:
            resp = jarvis_local_http.urlopen(req, 2.0)
        else:
            resp = urllib.request.urlopen(req, timeout=2.0)   # noqa: S310
        with resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    rows = body.get("models") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return None
    row = next((m for m in rows if isinstance(m, dict)), None)
    if row is None:
        return None
    # The one the owner's settings file says chat uses, else the first. This
    # preference was jarvis_second_card._ps_row's (its own comment said so),
    # and it moved HERE with the reading: with more than one model loaded,
    # "the first row" can be a different model from the one answering, and a
    # banner naming the wrong MODEL while it reports the right CARD would be
    # the same kind of half-truth this change exists to remove. Import inside
    # the function, wrapped: jarvis_models is one of the owner's own patched
    # files, and its absence must not take the card reading down with it.
    want = ""
    try:
        import jarvis_models
        want = str(jarvis_models.current_model() or "")
    except Exception:
        want = ""
    if want:
        row = next((m for m in rows
                    if isinstance(m, dict)
                    and _same_model(str(m.get("name") or m.get("model") or ""), want)), row)
    size, vram = row.get("size"), row.get("size_vram")
    pct = None
    if isinstance(size, (int, float)) and size > 0 and isinstance(vram, (int, float)):
        pct = int(min(100, round(vram * 100 / size)))
    return {"model": str(row.get("name") or row.get("model") or ""),
            "on_card_percent": pct,
            "context": row.get("context_length")}


def _same_model(a: str, b: str) -> bool:
    """Two model references naming the same model, allowing for the `:latest`
    tag one side may leave off (jarvis_second_card._same_model's own rule)."""
    a, b = str(a or "").strip().lower(), str(b or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        if y == x + ":latest":
            return True
    return False


def _model_process(cards: list, exclude_pids=None) -> Optional[dict]:
    """Which card the model's own process is on, as far as the machine says:
    {"index", "name", "uuid", "used_mb", "process"} or None. Only a process
    whose name is Ollama's or llama.cpp's, and only one the caller did not
    start itself: jarvis_second_card's own lanes run on another card BY
    DESIGN, so it passes their pids in `exclude_pids` and they are skipped
    (its `_model_process` did exactly this before this function existed)."""
    ours = set(exclude_pids or ())
    by_uuid = {(getattr(c, "uuid", "") or "").lower(): c for c in cards
               if getattr(c, "uuid", "")}
    for pid, pname, gpu, used in query_apps():
        low = pname.lower()
        if not ("ollama" in low or "llama" in low) or pid in ours:
            continue
        card = by_uuid.get(gpu.lower())
        if card is None:
            continue
        return {"index": card.index, "name": card.name, "uuid": card.uuid,
                "used_mb": used, "process": pname}
    return None


def observed_card(cards: list, *, exclude_pids=None, ollama_url: Optional[str] = None) -> Optional[dict]:
    """Which card the MODEL's own process is on right now, read from the
    machine (nvidia-smi's process list) - or None when Jarvis cannot tell.

    None covers every way of not knowing, and every caller says it as
    "cannot tell" rather than turning it into a guess: nothing is loaded, the
    driver does not name the program using a card (some Windows drivers do
    not - docs/MEASURE-CARDS.md section 2), no card could be read, or the
    only model processes are the caller's own lanes (see `_model_process`).

    THE ONE READER of that fact. `where_chat_runs` reports with it and
    `everyday_card` PLANS with it, so the card Jarvis plans around and the
    card it reports are the same reading of the same machine. Taken once per
    caller: `cards` is what the caller already read, never re-read here.

    `ollama_url` is only used to answer "is a model really loaded", the same
    `/api/ps` question jarvis_second_card._observed_card asked; None skips
    that and reads the process list alone."""
    proc = _model_process(list(cards or []), exclude_pids)
    if proc is None or not proc.get("uuid"):
        return None
    loaded = _ps_row(ollama_url) or {}
    return {"index": proc["index"], "name": proc["name"], "uuid": proc["uuid"],
            "used_mb": proc.get("used_mb"),
            "model": loaded.get("model"),
            "on_card_percent": loaded.get("on_card_percent"),
            "context": loaded.get("context")}


def observed_card_in(cards: list, **kwargs) -> Optional[object]:
    """`observed_card`, as the Device object in `cards` - the same card, with
    its memory, its free memory and its monitor, so a PLANNING caller gets
    the card itself and not only its name. None when Jarvis cannot tell (see
    `observed_card`)."""
    got = observed_card(cards, **kwargs)
    if got is None:
        return None
    want = str(got["uuid"]).lower()
    return next((c for c in cards
                 if (getattr(c, "uuid", "") or "").lower() == want), None)


def _num(text) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None           # "[N/A]", "[Not Supported]", "", garbage


def compute_from_name(name: str) -> Optional[float]:
    up = " ".join(str(name or "").upper().split())
    for key, cc in COMPUTE_BY_NAME:
        if key in up:
            return cc
    return None


def parse_smi(text: str, fields: str = FIELDS_FULL) -> list:
    """Rows of `nvidia-smi --query-gpu=<fields> --format=csv,noheader,nounits`
    as Devices. A line that does not parse is skipped, never guessed at."""
    names = fields.split(",")
    found = []
    for line in str(text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != len(names):
            continue
        row = dict(zip(names, parts))
        try:
            index = int(row["index"])
            total = int(float(row["memory.total"]))
        except (KeyError, TypeError, ValueError):
            continue
        if index < 0 or total <= 0:
            continue
        free = _num(row.get("memory.free", ""))
        name = row.get("name", "") or f"GPU {index}"
        cc = _num(row.get("compute_cap", "")) if "compute_cap" in row else None
        if cc is None:
            cc = compute_from_name(name)
        da = row.get("display_active", "").strip().lower()
        display = True if da == "enabled" else False if da == "disabled" else None
        uuid = row.get("uuid", "")
        if not uuid.startswith("GPU-"):
            uuid = ""
        found.append(Device(index, name, total,
                            int(free) if free is not None and free >= 0 else 0,
                            uuid=uuid, compute_cap=cc, display_active=display))
    return found


def query_cards(fresh: bool = False) -> list:
    """Every NVIDIA card, via nvidia-smi, cached for 30 seconds. Empty when
    there is none or nvidia-smi is missing. Never raises."""
    now = time.monotonic()
    if not fresh and _cache["cards"] is not None and now - _cache["at"] < _CACHE_SECONDS:
        return list(_cache["cards"])
    cards: list = []
    used = ""
    for fields in (FIELDS_FULL, FIELDS_OLD, FIELDS_OLDEST):
        try:
            out = _run_smi([f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
        except Exception:
            out = None
        if out is None:
            continue
        try:
            cards = parse_smi(out, fields)
        except Exception:
            cards = []
        if cards:
            used = fields
            break
    _cache.update(at=now, cards=list(cards), fields=used)
    return list(cards)


def devices() -> list:
    """The GPUs, via nvidia-smi. Empty list if there are none or it is absent.

    Parsed from --query-gpu CSV rather than any library, because the backend
    is standard-library-only and a dependency here would make the startup
    banner the one thing that needs pip.
    """
    return query_cards()


def primary(devs: list, configured=None) -> tuple:
    """(the everyday card, the sentence saying which rule chose it), or
    (None, why) with no cards. The rule is in this module's docstring.
    `configured` is `[compute] primary_gpu`; None reads it from the toml."""
    devs = [d for d in devs or [] if d is not None]
    if not devs:
        return None, "no graphics card was found"
    if configured is None:
        configured = _cfg("primary_gpu", "")
    want = str(configured if configured is not None else "").strip()
    note = ""
    if want:
        for d in devs:
            if getattr(d, "uuid", "") and d.uuid.lower() == want.lower():
                return d, f"[compute] primary_gpu names this card by its id ({want})"
        if want.isdigit():
            for d in devs:
                if d.index == int(want):
                    return d, (f"[compute] primary_gpu names nvidia-smi number {want} "
                               f"(an id starting GPU- is safer: numbers can change)")
        note = (f"[compute] primary_gpu is {want!r}, which is not a card in this PC, "
                f"so it was ignored and ")
    shown = sorted((d for d in devs if getattr(d, "display_active", None) is True),
                   key=lambda d: d.index)
    if shown:
        return shown[0], note + "a monitor is plugged into it"
    first = min(devs, key=lambda d: d.index)
    return first, note + "it is nvidia-smi's first card (no monitor was seen on any card)"


def everyday_card(cards: list, *, configured=None, pinned=None, exclude_pids=None,
                  ollama_url: Optional[str] = None) -> tuple:
    """(the card Jarvis treats as the everyday chat card, the sentence saying
    which rule chose it). THE ONE RULE SET - see this module's docstring for
    the five rules and their order.

    Kept beside `primary()` and NOT inside it, on purpose (owner's decision,
    2026-10-06): `primary()` keeps its own contract - the monitor rule alone,
    the fallback - because callers and tests read it directly and because
    `_detect` (jarvis_second_card.py) tells an ASSUMPTION from an
    OBSERVATION by the sentence that comes back. A new function is additive;
    changing `primary()` would have changed what every existing caller sees.

    The sentence is about the RULE, so a caller can tell them apart: rule 3's
    sentence starts "Jarvis read the model", and rules 4/5's says the monitor
    or first-card rule (an ASSUMPTION). `configured` is `[compute]
    primary_gpu` (None reads the toml); `pinned` is the owner's own pin (None
    reads chat-card.json); `exclude_pids` is the set of model processes that
    are the caller's own second-card lanes, left out of the reading;
    `ollama_url` is the everyday Ollama, asked only for the report's model
    name and on-card percentage - None skips that question.

    Never raises, never invents a card."""
    cards = [d for d in cards or [] if d is not None]
    if not cards:
        return None, "no graphics card was found"
    if configured is None:
        configured = _cfg("primary_gpu", "")
    want = str(configured if configured is not None else "").strip()
    if want:
        # His own hand-set override, and nothing here writes it back. The
        # owner's pin is not consulted at all when this is set, exactly as
        # jarvis_second_card._primary has always read it.
        return primary(cards, configured=want)
    if pinned is None:
        pinned = read_pin()
    pinned = str(pinned or "").strip()
    if pinned:
        hit = next((d for d in cards
                    if (getattr(d, "uuid", "") or "").lower() == pinned.lower()), None)
        if hit is not None:
            return hit, "you pinned this card (the \"Everyday chat runs on\" setting)"
        # His pinned card is not in the PC any more. The monitor rule answers
        # (card, sentence) and MUST be unpacked: returning it whole made this
        # a ((card, sentence), sentence) tuple once, which blew up in
        # `_detect` on `prim.uuid` (found 2026-10-06, by the test for exactly
        # this branch).
        est, _ = primary(cards)
        return est, (f"you pinned a card (id {pinned}) that nvidia-smi does not see now, so "
                     f"the everyday card is only an estimate")
    seen = observed_card_in(cards, exclude_pids=exclude_pids, ollama_url=ollama_url)
    if seen is not None:
        return seen, ("Jarvis read the model on this card from Ollama and nvidia-smi, and "
                      "you have not pinned a card")
    # Nothing is pinned and nothing was observed. `primary()` is what says so,
    # in words, and the caller's own `_detect` turns that into the ASSUMING
    # sentence the owner reads - "cannot tell" must never come out as a
    # silent guess.
    return primary(cards, configured=want)


# --------------------------------------------------------------------------
#   Who is starting a process on which card (added 2026-09-24)
#
#   jarvis_second_card.py (the second Ollama) and jarvis_big_model.py
#   (colibri with [big_model] cuda = "on") can both want the second card.
#   Each checks the other before starting, but a check and a start are two
#   steps, so both could pass the check at the same moment. The claim below
#   closes that gap: a module takes the card's claim BEFORE it starts a
#   process on it and gives it back when that process is stopped. Only one
#   owner holds a card at a time. In this process only (both modules live
#   in the one backend); nothing is written anywhere.
# --------------------------------------------------------------------------

_CLAIMS_LOCK = threading.Lock()
_CLAIMS: dict = {}            # card id, lower case -> owner


def claim_card(uuid: str, owner: str) -> Optional[str]:
    """Take the card for `owner`. None when it is now `owner`'s (taken, or
    already held); otherwise the owner that holds it, and nothing changes."""
    key = str(uuid or "").strip().lower()
    if not key:
        return None
    with _CLAIMS_LOCK:
        holder = _CLAIMS.get(key)
        if holder is not None and holder != owner:
            return holder
        _CLAIMS[key] = owner
    return None


def release_card(uuid: str, owner: str) -> None:
    """Give the card back, only if `owner` holds it."""
    key = str(uuid or "").strip().lower()
    with _CLAIMS_LOCK:
        if _CLAIMS.get(key) == owner:
            del _CLAIMS[key]


def card_holder(uuid: str) -> Optional[str]:
    """Who holds the card's claim, or None. Reads only."""
    with _CLAIMS_LOCK:
        return _CLAIMS.get(str(uuid or "").strip().lower())


def everyday_chat_words(name: str, rule: str) -> str:
    """The one sentence every screen says about which card everyday chat is
    on, built from `everyday_card`'s own rule sentence.

    WHY THIS EXISTS AT ALL (owner's decision, 2026-10-06, "option B: true to
    its reporting"). A banner that says "everyday chat on the X" and stops
    there makes a CLAIM. When the card was OBSERVED that claim is true. When
    nothing could be read - no model loaded, or a driver that does not name
    the program using a card - the same sentence named a card nobody had
    looked at, which is the confident wrong card this whole change exists to
    remove. So the sentence says which of the two it is, in the same words
    the owner already reads on the Hardware screen:

        observed   "Jarvis read the model on this card from Ollama and
                    nvidia-smi, and you have not pinned a card"
        assumed    "the card a monitor is plugged into" (or nvidia-smi's
                    first) - and the sentence says plainly that this is an
                    assumption, not something read

    Never invents a card and never raises: a rule sentence it does not
    recognise is passed through as "because <rule>", which is still true."""
    rule = str(rule or "")
    if "you pinned this card" in rule:
        return f"everyday chat is pinned to the {name} ({rule})"
    if rule.startswith("Jarvis read the model"):
        return (f"everyday chat on the {name}: Jarvis read the model on this card from "
                f"Ollama and nvidia-smi, and you have not pinned one")
    return (f"Jarvis cannot see which card the model is on, so everyday chat is only "
            f"ASSUMED to be on the {name} ({rule}) - an assumption, not something it read")


def plan(model: Optional[str] = None) -> Plan:
    """Where things should run. Never raises; says `simulated` when guessing."""
    prefer = str(_cfg("prefer", "speed")).strip().lower()
    if prefer not in ("speed", "capability"):
        prefer = "speed"

    name = model or os.environ.get("JARVIS_TEXT_MODEL") or "local"
    devs = devices()

    if not devs:
        return Plan(text_model=name, text_on="cpu", vision_resident=False,
                    tts_resident=False, simulated=True, prefer=prefer,
                    devices=[],
                    why="no GPU could be interrogated; this layout is a guess")

    # The everyday card by the rule set in `everyday_card` (module
    # docstring), never "the one with the most free memory": that picked a
    # 12 GB RTX 2060 over the faster 8 GB 2080 Super. The others follow in
    # nvidia-smi order. This used to be `primary()` alone - the monitor rule -
    # which is what let this banner name the 2080 SUPER while the model ran on
    # the 2060 (owner's decision, 2026-10-06).
    first, rule = everyday_card(devs, ollama_url=main_ollama_url())
    ranked = [first] + sorted((d for d in devs if d is not first), key=lambda d: d.index)
    second = ranked[1] if len(ranked) > 1 else None

    if prefer == "speed":
        text_on = f"cuda:{first.index}"
        # Voice runs on the processor (docs/ARCHITECTURE.md section 11: 0 GB
        # of graphics memory), so it is never resident on a card. Pictures
        # are on the second card only while its "Pictures" switch is on and
        # working (jarvis_second_card.py) - not merely because a second card
        # exists, which is what this used to claim, for voice as well.
        tts = False
        vision = False
        if second is not None:
            try:
                import jarvis_second_card
                vision = jarvis_second_card.lane_for("vision") is not None
            except Exception:
                vision = False
        why = (f"speed: {everyday_chat_words(first.name, rule)}; "
               + ("the second card runs only the second-card features that are "
                  "switched on (GET /api/second-card)"
                  if second else "one card only"))
    else:
        text_on = "+".join(f"cuda:{d.index}" for d in ranked)
        vision = tts = False
        why = ("capability: the model is spread across every card, so nothing "
               "else stays resident; generation is bounded by the slowest card")

    return Plan(text_model=name, text_on=text_on, vision_resident=vision,
                tts_resident=tts, simulated=False, prefer=prefer,
                devices=[asdict(d) for d in ranked], why=why)


if __name__ == "__main__":
    for k, v in plan().as_dict().items():
        print(f"  {k:<18} {v}")
