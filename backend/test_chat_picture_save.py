"""test_chat_picture_save.py - a picture attached in chat, saved to the PC.

    python backend/test_chat_picture_save.py

THE OWNER'S REPORT (2026-11-23, with a screenshot): he attached a screenshot
in chat and typed "transfer these to my PC"; the answer was "I can't transfer
this screenshot to your PC myself". There was no path: the chat picture path
decodes a picture for the vision lane and writes nothing, and the upload path
lands files only for bytes a phone sent in chunks.

WHAT THIS PROVES
    `jarvis_upload.save_chat_picture` lands ONE picture through the SAME
    machinery the phone's folder door uses: one `receive_uploaded_document`
    card raised before the bytes are staged, the upload's own staging folder,
    its own `finish` (measure, header check, ONE `os.replace`), and its own
    denial path - which removes the staging and leaves nothing behind. The
    bytes that land are byte for byte the bytes that arrived.

    No model, no network, no port, no real folder: a temp folder plays the
    listed one, and the card is a fake gate.
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_chat_picture as CP  # noqa: E402
import jarvis_upload as U  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: A real 1x1 transparent PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20
GIF = b"GIF89a" + b"\x00" * 20
BMP = b"BM" + b"\x00" * 20


class FakeDocs:
    """The listed-folder module, in a temp folder."""

    PHONE_ADD = "Add a folder on the PC first."

    def __init__(self, root: Path):
        self.root = str(root)
        self.folders = [{"path": str(root), "name": "Documents"}]

    def load(self):
        return {"folders": list(self.folders), "why": ""}

    def _key(self, path):
        return os.path.normcase(os.path.realpath(str(path)))

    def protected(self, path):
        return False

    def _inside(self, parent, child):
        parent = os.path.normcase(os.path.realpath(str(parent)))
        child = os.path.normcase(os.path.realpath(str(child)))
        return child == parent or child.startswith(parent + os.sep)


def approved(action, detail, text):
    return types.SimpleNamespace(allowed=True, outcome="approved", tier="ask", reason="")


def denied(action, detail, text):
    return types.SimpleNamespace(allowed=False, outcome="denied", tier="ask", reason="")


inline = lambda fn: fn()          # the card thread, run in place

work = Path(tempfile.mkdtemp(prefix="jarvis-chat-picture-"))
U.docs = FakeDocs(work)

# ---------------------------------------------------------------- the name ---

check("a PNG's own header names the file .png",
      (U.chat_picture_name(PNG) or "").endswith(".png"), U.chat_picture_name(PNG))
check("a JPEG's header names it .jpg",
      (U.chat_picture_name(JPEG) or "").endswith(".jpg"), U.chat_picture_name(JPEG))
check("a WEBP's header names it .webp",
      (U.chat_picture_name(WEBP) or "").endswith(".webp"), U.chat_picture_name(WEBP))
check("a GIF's header names it .gif",
      (U.chat_picture_name(GIF) or "").endswith(".gif"), U.chat_picture_name(GIF))
check("a BMP's header names it .bmp",
      (U.chat_picture_name(BMP) or "").endswith(".bmp"), U.chat_picture_name(BMP))
check("bytes that are not a picture get no name",
      U.chat_picture_name(b"not a picture") is None)
check("the name never carries a path",
      "/" not in (U.chat_picture_name(PNG) or "/")
      and "\\" not in (U.chat_picture_name(PNG) or "\\"))

# ------------------------------------------------------------- the refusals ---

code, out = U.save_chat_picture("shot.png", b"", gate=approved, spawn=inline)
check("an empty picture is refused", code == 400 and out.get("said") == U.NO_BYTES, (code, out))

code, out = U.save_chat_picture("shot.txt", PNG, gate=approved, spawn=inline)
check("a name that is not a picture kind is refused",
      code == 400 and out.get("said") == U.CHAT_NOT_A_PICTURE, (code, out))

old = list(U.docs.folders)
U.docs.folders = []
code, out = U.save_chat_picture("shot.png", PNG, gate=approved, spawn=inline)
check("with no listed folder it refuses in the PC's own words",
      code == 409 and out.get("said") == FakeDocs.PHONE_ADD, (code, out))
U.docs.folders = old

# ------------------------------------------------------------- the landing ---

code, out = U.save_chat_picture("shot.png", PNG, gate=approved, spawn=inline)
landed = work / "From my phone" / "shot.png"
check("an approved card saves the picture", code == 202 and landed.is_file(), (code, out))
check("the bytes that land are the bytes that arrived",
      landed.is_file() and landed.read_bytes() == PNG)
check("the answer says a card is up and names the folder",
      "Asked your PC to save" in str(out.get("said"))
      and work.name in str(out.get("said")), out.get("said"))
check("the staging folder is gone once the file is real",
      not list(work.glob(".jarvis-upload-*")))

# --------------------------------------------------------------- the denial ---

before = set(work.rglob("*"))
code, out = U.save_chat_picture("denied.png", PNG, gate=denied, spawn=inline)
after = set(work.rglob("*"))
check("a denied card saves nothing",
      code == 202 and not (work / "From my phone" / "denied.png").exists(), (code, out))
check("...and its staging is removed", after == before, (len(before), len(after)))

# -------------------------------------------------------- the picture reader ---

body = {"messages": [
    {"role": "user", "content": [
        {"type": "text", "text": "look"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,"
                                                    + base64.b64encode(PNG).decode("ascii")}},
    ]},
]}
pics = CP.raw_pictures(body["messages"])
check("the request's picture is read back byte for byte",
      len(pics) == 1 and pics[0] == PNG, pics)
check("a request with no picture reads none",
      CP.raw_pictures([{"role": "user", "content": "hello"}]) == [])
check("a picture part with no readable bytes is skipped, never guessed",
      CP.raw_pictures([{"role": "user", "content": [
          {"type": "image", "image": ""}]}]) == [])


# ------------------------------------------------------- the chat turn ---

import jarvis_quick as Q  # noqa: E402

check("the owner's own sentence is claimed",
      Q.match("transfer these to my PC") is not None
      and Q.match("transfer these to my PC").name == "chat_picture_save")
check('"transfer this screenshot to my PC" is claimed',
      Q.match("transfer this screenshot to my PC") is not None
      and Q.match("transfer this screenshot to my PC").name == "chat_picture_save")
check("a sentence naming no picture is left to the model",
      Q.match("send this to my PC") is None)

calls = []
_orig_save = U.save_chat_picture
U.save_chat_picture = lambda name, data, **k: (
    calls.append((name, data)) or (202, {"said": "Asked your PC to save " + name + "."}))
try:
    res = Q.run(Q.match("transfer these to my PC"), None, 1e9, messages=body["messages"])
    check("the handler hands the picture's own bytes to the door",
          len(calls) == 1 and calls[0][1] == PNG, calls)
    check("...and answers with the door's sentence",
          res is not None and res.reply.startswith("Asked your PC to save"), res)
    empty = Q.run(Q.match("transfer these to my PC"), None, 1e9, messages=[])
    check("a turn with no picture is refused in plain words",
          empty is not None and empty.reply == U.CHAT_NO_PICTURE, empty)
finally:
    U.save_chat_picture = _orig_save
print()
print(f"{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    for name in FAILED:
        print(f"FAILED: {name}")
    sys.exit(1)
