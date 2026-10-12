"""The graph `jarvis_pictures.py` posts to ComfyUI must fit the models on THIS PC.

WHY THIS SUITE EXISTS (2026-10-11, a real defect found by reading file headers)

`jarvis_pictures.py` shipped with ONE graph, whose only loader was
`CheckpointLoaderSimple` - the loader for a FUSED checkpoint, which hands out a
model, a CLIP and a VAE from a single file. No picture model on this PC is
fused: Chroma1-HD is a diffusion model with a separate T5-XXL text encoder and
a separate FLUX VAE, and the Qwen one is an sd.cpp GGUF. So the picture feature
could not draw a picture here at all: the graph failed at its first node,
whatever the switch said. Nothing caught it, because the suite that covers the
routes uses a STUB runtime (as it must - it needs no graphics card), and a stub
happily returns a picture for a graph that could never load.

WHAT THIS CHECK IS, AND WHAT IT DELIBERATELY IS NOT

It is a check against the FILE, not against a list of names someone typed: it
reads the model's own safetensors header (or its `.gguf` extension) and asks
whether the loader the graph uses can open that file. A machine with a
genuinely fused checkpoint passes with `CheckpointLoaderSimple`; this one cannot,
and says why. The one hard-coded thing is that the loaders must match
`jarvis_picture_card.IMAGE_MODELS` - this machine's own record, which
`test_picture_card.py` already checks against the real files byte for byte - so
a graph and a record that disagree are caught even on a runner that has no
models at all.

The machine-only parts skip WITH THE REASON PRINTED (no models, no ComfyUI on a
CI runner); the structural, record and sensitivity checks always run.

    python backend/test_pictures_graph.py
"""
from __future__ import annotations

import json
import struct
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_picture_card as C  # noqa: E402
import jarvis_pictures as P  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


#: A loader that takes CLIP **and** VAE out of the file it loads.
FUSED_LOADERS = {"CheckpointLoaderSimple", "CheckpointLoader"}
#: A loader that takes only the diffusion model out of its file.
COMPONENT_LOADERS = {"UNETLoader", "UnetLoaderGGUF", "UnetLoaderGGUFAdvanced"}
#: Tensor-name prefixes that only a FUSED checkpoint has inside it.
FUSED_PREFIXES = ("vae.", "first_stage_model.", "cond_stage_model.",
                  "conditioner.", "text_encoder", "clip_l.", "clip_g.",
                  "clip.", "text_model.", "visual.")


def safetensors_prefixes(path: Path) -> list:
    """Top-level tensor-name prefixes, read from the file's own header.

    The header is JSON at the start of a safetensors file: no weights are
    loaded, so this is cheap and safe - it is how the defect above was found.
    """
    with path.open("rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        if n <= 0 or n > 200 * 1024 * 1024:
            raise ValueError(f"implausible safetensors header length {n}")
        header = json.loads(fh.read(n).decode("utf-8"))
    return sorted({k.split(".", 1)[0] for k in header if k != "__metadata__"})


def looks_fused(prefixes) -> bool:
    """True when the file carries a VAE or a text encoder of its own."""
    return any(p.startswith(FUSED_PREFIXES) for p in prefixes)


def unet_node(nodes: dict):
    """(the one node that loads the picture model, or None, how many there are)."""
    found = [n for n in nodes.values()
             if "unet_name" in (n.get("inputs") or {})
             or "ckpt_name" in (n.get("inputs") or {})]
    return (found[0] if len(found) == 1 else None), len(found)


def graph_problems(nodes: dict, entry: dict, model_path=None) -> list:
    """Everything wrong with `nodes` for `entry`'s model. `[]` is good.

    Pure: the sensitivity checks below feed it deliberately wrong graphs.
    """
    problems = []
    name = Path(str(entry.get("file", ""))).name
    node, count = unet_node(nodes)
    if node is None:
        return [f"{count} node(s) load a picture model; exactly one must"]
    loader = str(node.get("class_type") or "")
    if entry.get("loader") and loader != entry["loader"]:
        problems.append(f"the graph loads {name} with {loader}; this PC's own "
                        f"record says {entry['loader']}")
    known_file = model_path is not None and Path(model_path).is_file()
    fused = None
    if known_file:
        path = Path(model_path)
        if path.suffix.lower() == ".gguf":
            if "GGUF" not in loader:
                problems.append(f"{name} is a .gguf file and {loader} cannot "
                                f"open one")
            fused = False
        else:
            try:
                fused = looks_fused(safetensors_prefixes(path))
            except Exception as exc:
                problems.append(f"{name}: its header could not be read ({exc})")
                fused = None
            if fused is False and loader in FUSED_LOADERS:
                problems.append(
                    f"{name} holds no VAE and no text encoder of its own "
                    f"(its tensors start {'/'.join(safetensors_prefixes(path)[:4])} "
                    f"...), so {loader} would hand the graph an empty CLIP and an "
                    f"empty VAE - this file needs a diffusion-model loader plus "
                    f"the two companions beside it")
            if fused is True and loader not in FUSED_LOADERS:
                problems.append(f"{name} IS a fused checkpoint, so it needs a "
                                f"fused loader, not {loader}")
    if entry.get("loader") in COMPONENT_LOADERS:
        want = {kind: str(f) for f, kind, _s in entry.get("companions", ())}
        clips = [n for n in nodes.values() if n.get("class_type") == "CLIPLoader"]
        vaes = [n for n in nodes.values() if n.get("class_type") == "VAELoader"]
        if len(clips) != 1:
            problems.append(f"{len(clips)} CLIPLoader node(s); a component "
                            f"model needs exactly one text encoder")
        elif str((clips[0].get("inputs") or {}).get("clip_name")) != want.get("text_encoders"):
            problems.append(f"the graph names text encoder "
                            f"{(clips[0].get('inputs') or {}).get('clip_name')!r}; "
                            f"the record says {want.get('text_encoders')!r}")
        if len(vaes) != 1:
            problems.append(f"{len(vaes)} VAELoader node(s); a component model "
                            f"needs exactly one VAE")
        elif str((vaes[0].get("inputs") or {}).get("vae_name")) != want.get("vae"):
            problems.append(f"the graph names VAE "
                            f"{(vaes[0].get('inputs') or {}).get('vae_name')!r}; "
                            f"the record says {want.get('vae')!r}")
    for ident, node in nodes.items():
        for key, value in (node.get("inputs") or {}).items():
            for link in (value if isinstance(value, list) else []):
                if isinstance(link, str) and link not in nodes:
                    problems.append(f"node {ident}.{key} points at node {link!r}, "
                                    f"which is not in the graph")
    return problems


def model_path_of(entry) -> Path:
    return Path(str(entry.get("file", "")))


def comfy_dir() -> Path:
    return Path(str(getattr(C, "COMFY_DIR", "") or ""))


def companion_path_of(entry, kind: str) -> Path:
    for name, where, _size in entry.get("companions", ()):
        if where == kind:
            return comfy_dir() / "models" / where / str(name)
    return comfy_dir() / "models" / kind / "missing"


# --------------------------------------------------------------------------
#   1. Every model's graph, checked against the file and the record
# --------------------------------------------------------------------------

def t_each_model_gets_a_graph_that_fits_it():
    adapter = P.ComfyUI("http://127.0.0.1:8188")
    for entry in C.IMAGE_MODELS:
        name = Path(str(entry["file"])).name
        graph, knobs = adapter._workflow("a red panda sitting on a mossy rock",
                                         {"model": name, "seed": 12345})
        problems = graph_problems(graph, entry, model_path_of(entry))
        check(f"{name}: the graph fits the file on disk", not problems,
              "; ".join(problems))
        check(f"{name}: the recorded loader is a real ComfyUI node name",
              entry.get("loader") in (COMPONENT_LOADERS | FUSED_LOADERS),
              str(entry.get("loader")))
        check(f"{name}: no fused-checkpoint loader is used anywhere",
              "CheckpointLoaderSimple" not in {n["class_type"] for n in graph.values()},
              str({n["class_type"] for n in graph.values()}))
        check(f"{name}: width and height are the graph's own defaults, in range",
              P.MIN_SIDE <= knobs["width"] <= P.MAX_SIDE
              and P.MIN_SIDE <= knobs["height"] <= P.MAX_SIDE, str(knobs))


def t_the_full_path_and_the_bare_name_both_resolve():
    for entry in C.IMAGE_MODELS:
        bare = Path(str(entry["file"])).name
        check(f"{bare} is found by its bare name",
              (P.placement_for(bare) or {}).get("model") == bare)
        check(f"{bare} is found by its full path",
              (P.placement_for(str(entry["file"])) or {}).get("model") == bare)
    check("a name this PC has no record of resolves to nothing",
          P.placement_for("some-model-from-another-machine.safetensors") is None)
    check("the model a prompt-only caller gets is one of this PC's own",
          P.default_model() in [Path(str(e["file"])).name for e in C.IMAGE_MODELS],
          P.default_model())


# --------------------------------------------------------------------------
#   2. The sensitivity proof: wrong graphs must be caught, here, every run
# --------------------------------------------------------------------------

def t_the_check_catches_the_defect_it_was_written_for():
    """The exact regression: a fused-checkpoint graph for a component model."""
    entry = C.IMAGE_MODELS[0]
    name = Path(str(entry["file"])).name
    wrong = {"1": {"class_type": "CheckpointLoaderSimple",
                   "inputs": {"ckpt_name": name}},
             "2": {"class_type": "CLIPTextEncode",
                   "inputs": {"text": "x", "clip": ["1", 1]}},
             "6": {"class_type": "VAEDecode", "inputs": {"samples": ["1", 0],
                                                         "vae": ["1", 2]}},
             "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0],
                                                         "filename_prefix": "jarvis"}}}
    problems = graph_problems(wrong, entry, model_path_of(entry))
    check("a fused-checkpoint graph for a component model is caught",
          any("CheckpointLoaderSimple" in p or "fused" in p
              or "no VAE and no text encoder" in p for p in problems),
          "; ".join(problems) or "(nothing reported)")
    check("... and the same graph with the right loaders is clean",
          not graph_problems(_fixed_chroma_graph(entry), entry,
                             model_path_of(entry)))

    gguf = C.IMAGE_MODELS[-1]
    if Path(str(gguf["file"])).suffix.lower() == ".gguf":
        wrong_gguf = {"1": {"class_type": "UNETLoader",
                            "inputs": {"unet_name": Path(str(gguf["file"])).name,
                                       "weight_dtype": "default"}}}
        problems = graph_problems(wrong_gguf, gguf, model_path_of(gguf))
        check("a safetensors-diffusion loader on a .gguf file is caught",
              any(".gguf" in p for p in problems), "; ".join(problems) or "(nothing)"
              )
    else:
        check("a safetensors-diffusion loader on a .gguf file is caught",
              False, "the small model is not a .gguf any more - this control "
                     "needs writing again")

    check("a graph whose link points at a missing node is caught",
          any("not in the graph" in p for p in graph_problems(
              {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "x"}},
               "6": {"class_type": "VAEDecode",
                     "inputs": {"samples": ["99", 0], "vae": ["1", 0]}},
               "7": {"class_type": "SaveImage",
                     "inputs": {"images": ["6", 0]}}},
              C.IMAGE_MODELS[0], None)))


def _fixed_chroma_graph(entry) -> dict:
    """The graph the module builds today, built directly for the control."""
    return P.ComfyUI("http://127.0.0.1:8188")._workflow(
        "x", {"model": Path(str(entry["file"])).name})[0]


# --------------------------------------------------------------------------
#   3. The route refuses a model this PC cannot load, before it draws
# --------------------------------------------------------------------------

def t_the_route_refuses_an_unknown_model_in_plain_words():
    called = []

    class Stub(P.LocalRuntime):
        name = "comfyui"

        def available(self):
            called.append("available")
            return True

        def draw(self, prompt, *, seed=None, settings=None):
            called.append("draw")
            raise AssertionError("the route must not reach the program")

    P.register_runtime("comfyui", Stub)
    try:
        base = {"enabled": True, "runtime": "comfyui", "address": None,
                "folder": None}
        code, out = P.make_answer({"prompt": "a red panda",
                                   "settings": {"model": "nope.safetensors"}},
                                  base)
        check("an unknown model is refused with one plain sentence",
              code == 503 and out.get("ok") is False
              and out.get("error") == P.WORDS["unknown_model"], str(out))
        check("... and the drawing program was never asked to draw",
              called == [], str(called))
    finally:
        P.register_runtime("comfyui", P.ComfyUI)


# --------------------------------------------------------------------------
#   4. Only this machine can answer these - each skip says why
# --------------------------------------------------------------------------

def t_the_files_and_the_program_are_really_here():
    comfy = comfy_dir()
    if not comfy.is_dir():
        skip(f"ComfyUI is not installed here ({comfy}), so the files a graph "
             f"names and the node classes it uses cannot be checked")
        return
    core = sorted(p for p in comfy.glob("*.py")) + \
        sorted(comfy.glob("comfy/**/*.py")) + \
        sorted(comfy.glob("comfy_extras/**/*.py")) + \
        sorted(comfy.glob("custom_nodes/**/*.py"))
    if not core:
        skip(f"no ComfyUI source found under {comfy}, so its node classes "
             f"cannot be checked")
        return
    text = "\n".join(p.read_text("utf-8", "replace") for p in core)

    adapter = P.ComfyUI("http://127.0.0.1:8188")
    for entry in C.IMAGE_MODELS:
        name = Path(str(entry["file"])).name
        path = model_path_of(entry)
        if not path.is_file():
            skip(f"{path} is not on this machine, so its loader and its "
                 f"companions cannot be checked against the file")
            continue
        got = path.stat().st_size
        check(f"{name} is here at the size the record says",
              got == int(entry.get("bytes") or got),
              f"{got} bytes on disk, {entry.get('bytes')} in the record")
        graph = adapter._workflow("x", {"model": name})[0]
        classes = sorted({n["class_type"] for n in graph.values()})
        missing = [c for c in classes if f'"{c}"' not in text]
        check(f"{name}: every node class the graph uses exists in this ComfyUI",
              not missing, f"not in the installed ComfyUI: {missing}")
        clip_type = str((graph.get("2", {}).get("inputs") or {}).get("type") or "")
        if clip_type:
            check(f"{name}: this ComfyUI knows the CLIP type {clip_type!r}",
                  f'"{clip_type}"' in text, clip_type)
        for _fname, where, size in entry.get("companions", ()):
            want = comfy / "models" / where / str(_fname)
            if not want.is_file():
                skip(f"the companion {want} is not on this machine")
                continue
            check(f"{_fname} is beside it at the size the record says",
                  want.stat().st_size == int(size),
                  f"{want.stat().st_size} on disk, {size} in the record")


def main():
    for fn in (t_each_model_gets_a_graph_that_fits_it,
               t_the_full_path_and_the_bare_name_both_resolve,
               t_the_check_catches_the_defect_it_was_written_for,
               t_the_route_refuses_an_unknown_model_in_plain_words,
               t_the_files_and_the_program_are_really_here):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    if SKIPPED:
        print("\nSkipped (not failures):")
        for why in SKIPPED:
            print(f"  - {why}")
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
