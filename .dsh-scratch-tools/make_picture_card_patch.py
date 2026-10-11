"""Write picture-card.patch with the real context lines taken from jarvis_hud.py.

Building the hunk by hand is how patches silently drift; this reads the anchor
block out of the file and writes the counts from what it actually found.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
HUD = HERE / "jarvis-backend" / "jarvis_hud.py"
lines = HUD.read_text(encoding="utf-8").splitlines()

anchor = "        print(\"             until jarvis_progress.py is back: run apply-patches.ps1 again\")"
idx = lines.index(anchor)
# context: 6 lines before the anchor and 3 after it
start = idx - 6
context_before = lines[start:idx + 1]
context_after = lines[idx + 1:idx + 3]

added = [
    "    # picture-card.patch (\"Which card draws the pictures\", the owner's decision of",
    "    # 2026-10-10; docs/PICTURE-CARDS-DESIGN.md, JARVIS-API section 124): GET and POST",
    "    # /api/picture-card. The three ways of running a picture-maker beside the everyday",
    "    # chat - pictures on the 12 GB card with the chat stepping aside, pictures on the",
    "    # 12 GB card with the chat moved to the 8 GB card, small pictures on the 8 GB card",
    "    # with the chat left alone - each its own switch, all off until the owner turns one",
    "    # on. It draws nothing itself (asking for a picture is jarvis_pictures.py's route,",
    "    # section 123) and it starts nothing: D:\\Jarvis\\ImageGen\\Start-Pictures.ps1 starts",
    "    # the picture-maker on the right card, reading these settings. Wrapped round Handler",
    "    # here, before anything listens, like progress above.",
    "    try:",
    "        import jarvis_picture_card",
    "        print(jarvis_picture_card.install(Handler, origin_ok=_origin_ok,",
    "                                          token_ok=_token_ok, read_body=_read_body))",
    "    except Exception as exc:",
    "        print(f\"  picture-card NOT ON ({type(exc).__name__}) - the three ways of making pictures are off\")",
    "        print(\"             until jarvis_picture_card.py is back: run apply-patches.ps1 again\")",
]

old_count = len(context_before) + len(context_after)
new_count = old_count + len(added)
header = "@@ -{0},{1} +{0},{2} @@".format(start + 1, old_count, new_count)

body = []
body.append("--- a/jarvis_hud.py")
body.append("+++ b/jarvis_hud.py")
body.append(header)
body.extend(" " + line for line in context_before)
body.extend("+" + line for line in added)
body.extend(" " + line for line in context_after)

out = HERE / "backend" / "picture-card.patch"
# LF, not CRLF: this repository is LF everywhere (.gitattributes says so), and a
# CRLF patch does not apply against LF files.
out.write_bytes(("\n".join(body) + "\n").encode("utf-8"))
print("wrote", out, "hunk:", header)
print("anchor line:", idx + 1)
