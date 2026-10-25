"""The model PROFILES: the one file that says how a model is set up for Jarvis.

    python3 test_model_profiles.py

WHY THIS EXISTS. `tools/model_tryout/Modelfile.jarvis-qwen35-9b` is a profile
to build and try (Upgrade 3C). Its whole value is that it is Jarvis's own
wrapper with ONE model name changed - and the part that must never drift is the
SYSTEM block: 1,610 characters of invariants that reach the model only when
this file says them. A paraphrase would still *look* right and would silently
drop an invariant (the "never claim an action was taken" line, the privacy
line), so the block is COPIED from backend/jarvis-primary.Modelfile by the
script that wrote the file, and this suite fails if the two ever stop being
byte-identical.

It also checks the stop tokens and every parameter, because those are the
things a hand edit gets wrong quietly, and one arithmetic claim that can be
checked rather than trusted (the KV cache size for a hybrid model).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import REPO  # noqa: E402

FAILED, PASSED = [], []

PRIMARY = REPO / "backend" / "jarvis-primary.Modelfile"
PROFILE = REPO / "tools" / "model_tryout" / "Modelfile.jarvis-qwen35-9b"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def system_block(text: str):
    """The `SYSTEM \"\"\"...\"\"\"` block, or None. `re.S` so the block's own
    newlines are part of it."""
    m = re.search(r'^SYSTEM\s+"""(.*?)"""', text, re.S | re.M)
    return m.group(1) if m else None


def stops(text: str) -> list:
    return re.findall(r'^PARAMETER\s+stop\s+(.+?)\s*$', text, re.M)


def param(text: str, key: str):
    """The value of `PARAMETER <key> ...`, or None. Only the LAST one, so a
    second line for the same key (which is how a typo usually looks) is what
    this returns rather than being hidden."""
    got = re.findall(rf'^PARAMETER\s+{re.escape(key)}\s+(.+?)\s*$', text, re.M)
    return got[-1] if got else None


def count_param(text: str, key: str) -> int:
    return len(re.findall(rf'^PARAMETER\s+{re.escape(key)}\s', text, re.M))


#: The profile's parameters, exactly as Upgrade 3C specifies them: the ones
#: jarvis-primary uses, plus presence_penalty pinned to 0.0.
WANTED_PARAMS = {
    "num_ctx": "16384",
    "num_batch": "512",
    "num_predict": "1024",
    "temperature": "0.7",
    "top_p": "0.8",
    "top_k": "20",
    "repeat_penalty": "1.05",
    "presence_penalty": "0.0",
}

#: The architecture of qwen3.5:9b, read off the installed model with
#: /api/show on 2026-10-15. Kept here as numbers so the KV arithmetic below is
#: a calculation rather than a quotation.
BLOCK_COUNT = 32
FULL_ATTENTION_LAYERS = 8          # qwen35.full_attention_interval = 4
HEAD_COUNT_KV = 4
KEY_LENGTH = 256                   # = value_length
Q8_0_BYTES_PER_ELEMENT = 1.0625    # the q8_0 block format, 34 bytes per 32
F16_BYTES_PER_ELEMENT = 2.0


def kv_cache_gib(tokens: int, bytes_per_element: float) -> float:
    """The KV cache of a HYBRID model: only the full-attention layers keep one.

    A Gated DeltaNet recurrent layer has no KV cache at all, so counting all 32
    blocks - which is what a dense model's arithmetic would do - would be four
    times too big. 0.27 GiB, the figure Upgrade 3C names, is this at q8_0.
    """
    elements = 2 * HEAD_COUNT_KV * KEY_LENGTH * FULL_ATTENTION_LAYERS * tokens
    return elements * bytes_per_element / (1024 ** 3)


def t_the_kv_arithmetic_matches_the_figure_the_profile_states():
    q8 = kv_cache_gib(16384, Q8_0_BYTES_PER_ELEMENT)
    f16 = kv_cache_gib(16384, F16_BYTES_PER_ELEMENT)
    check("the q8_0 KV cache at 16K rounds to the 0.27 GiB the profile states",
          round(q8, 2) == 0.27, f"computed {q8:.4f} GiB")
    check("...and the f16 figure is the 0.50 the profile warns about",
          round(f16, 2) == 0.50, f"computed {f16:.4f} GiB")
    check("only the 8 full-attention layers are counted, not all 32 blocks",
          FULL_ATTENTION_LAYERS < BLOCK_COUNT
          and round(kv_cache_gib(16384, Q8_0_BYTES_PER_ELEMENT), 2)
          != round(2 * HEAD_COUNT_KV * KEY_LENGTH * BLOCK_COUNT * 16384
                   * Q8_0_BYTES_PER_ELEMENT / (1024 ** 3), 2),
          "a dense 32-layer count would have given "
          f"{2 * HEAD_COUNT_KV * KEY_LENGTH * BLOCK_COUNT * 16384 * Q8_0_BYTES_PER_ELEMENT / (1024 ** 3):.2f} GiB")
    check("the profile states that 0.27 GiB figure", "0.27 GiB" in read(PROFILE))


def t_the_system_block_is_jarvis_bes_own_word_for_word():
    src, new = read(PRIMARY), read(PROFILE)
    a, b = system_block(src), system_block(new)
    check("both files have a SYSTEM block", a is not None and b is not None)
    check("the profile's SYSTEM block is BYTE-IDENTICAL to jarvis-primary's",
          a == b, f"primary {len(a or '')} chars, profile {len(b or '')} chars")
    check("...and it is the 1,610-character invariants block, not a stub",
          len(b or "") == 1610, f"{len(b or '')} chars")
    # The lines a paraphrase would quietly drop.
    for phrase in ("Never claim an action was taken that was not.",
                   "Anything recalled about the owner is private and stays on this machine.",
                   "Say what is a guess and what is verified.",
                   # Joined them 2026-10-25 (D2, the live campaign): a search
                   # or a sum is only real if a tool did it.
                   "A search, a lookup or a sum is only real if a tool did it"):
        check(f"the invariants still say: {phrase[:42]}...",
              phrase in (b or ""), "missing from the profile's SYSTEM block")


def t_the_stop_tokens_are_jarvis_bes_own():
    src, new = read(PRIMARY), read(PROFILE)
    check("the primary has stop tokens to copy at all", len(stops(src)) >= 2, f"{stops(src)}")
    check("the profile's stop tokens are the same ones, in the same order",
          stops(new) == stops(src), f"profile {stops(new)} vs primary {stops(src)}")


def t_every_parameter_is_the_one_the_upgrade_specifies():
    text = read(PROFILE)
    check("the profile exists", bool(text), str(PROFILE))
    for key, want in WANTED_PARAMS.items():
        got = param(text, key)
        check(f"PARAMETER {key} is {want}", got == want, f"got {got!r}")
        check(f"...and it is stated exactly once", count_param(text, key) == 1,
              f"{count_param(text, key)} line(s) for {key}")
    check("presence_penalty is NOT the download's 1.5",
          param(text, "presence_penalty") != "1.5", param(text, "presence_penalty"))
    check("the download's own temperature 1 is not what the profile sets",
          param(text, "temperature") != "1")
    check("the download's own top_p 0.95 is not what the profile sets",
          param(text, "top_p") != "0.95")


def t_the_profile_names_the_model_it_is_made_from():
    text = read(PROFILE)
    check("FROM qwen3.5:9b", param(text, "__from__") is None and
          any(line.strip() == "FROM qwen3.5:9b" for line in text.splitlines()),
          "the FROM line is missing or names another model")
    check("exactly one FROM line (a second would silently replace the first)",
          len(re.findall(r'^FROM\s', text, re.M)) == 1)
    check("it never pulls or downloads anything itself",
          not re.search(r'^\s*(?:RUN|ADAPTER)\b', text, re.M))


def t_it_says_what_it_is_and_not_a_cutover():
    text = read(PROFILE)
    low = text.lower()
    check("it says plainly that nothing points at this name yet",
          "nothing in jarvis points at this name" in low, "the warning line is missing")
    check("it records where presence_penalty 1.5 came from",
          "presence_penalty" in low and "1.5" in text,
          "the measured default it overrides is not written down")


if __name__ == "__main__":
    for fn in (t_the_kv_arithmetic_matches_the_figure_the_profile_states,
               t_the_system_block_is_jarvis_bes_own_word_for_word,
               t_the_stop_tokens_are_jarvis_bes_own,
               t_every_parameter_is_the_one_the_upgrade_specifies,
               t_the_profile_names_the_model_it_is_made_from,
               t_it_says_what_it_is_and_not_a_cutover):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            import traceback
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
