# Report 14 (audit), agent a74727dc, 2026-09-29T21:03Z

> **What it was asked** (first 600 characters of the task): Bug-hunt two areas merged in PR #34, with `main` checked out read-only at /tmp/main34 (compare `git -C /tmp/main34 diff 7df0be91 0fdd81be`, ignore docs/SOURCE-BUNDLE.md): (1) CHAT-PICTURE CLEANING: backend/jarvis_chat_picture.py, jarvis_picture.py, jarvis_ocr.py, jarvis_photo_remind.py, tests test_chat_picture.py/test_picture_text.py/test_ocr_words.py, and the agent hooks - pictures the owner attaches are cleaned before any model sees them; look for metadata (EXIF/GPS) leaks, cleaning skipped on some path, crashes on odd files, size/decompression bombs, temp files left on disk. (2) VOICES/MOUT

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

I found no serious bug in either area. I found two real but smaller ones, and I read no way for the owner's own voice to be cloned. All seven test files I ran pass (test_chat_picture 125, test_picture_text 50, test_ocr_words 35, test_photo_remind 148, test_mouth 92, test_kokoro 159, test_blend_voices 104). The venv has no pytest, so I ran each file directly with the venv python. Everything below is against /tmp/main34 (0fdd81be).

**1. Picture cleaning: a small PNG can blow up memory (low to medium; ran it)**
- Where: /tmp/main34/backend/jarvis_picture.py:92, `raw = zlib.decompress(b"".join(idat))`.
- The size cap at line 86 only checks the header's width times height. The compressed data is then unpacked with no limit.
- What I ran: a 10x10 PNG whose picture data unpacks to 400 MB, but is only 407 KB as a file. `decode_png` returned a result and the process used 817 MB. The chat message limit is 4 MiB, so a crafted PNG could ask for roughly 4 GB and take the backend down.
- Reached only when the reader finds a secret in the picture and jarvis_chat_picture asks for a cleaned copy (`want_png=True`). The owner would have to attach a crafted picture that also has readable text like a key.
- Fix: unpack with `zlib.decompressobj().decompress(data, expected + 1)`, where expected is (stride+1)*h. Refuse the picture if there is more data than that, which the caller already treats as "cannot check".

**2. Voices: Ashby or Clara can speak unchecked against the owner's voice print (low; ran it)**
- Where: /tmp/main34/backend/jarvis_voices.py:453, `if got in K.MIX and blend_refused(got)`. `blend_refused` (line 712) is true only if a stored failing check exists.
- The stored checks live in memory only (`_BLEND_CHECKS`, lines ~211 and 1119) and are keyed on the voice prints. So after every Jarvis restart, after the owner retrains their voice print, or when a check could not run ("unchecked" is deliberately not stored), there is no stored check.
- What I ran: with speaker "mix_ashby" saved, `blend_verdict` is None and `_builtin_now(V1MIX)` returns `{'name': 'mix_ashby', 'sid': 53, 'fell_back': False}`. So Jarvis speaks in it.
- The module comment says "Not being able to check ... the voice is not used until it can be". The code does the opposite. The only re-check is `_recheck_saved_blend`, started from `speaker_view`, so it runs only when the owner opens the voice settings. If the owner never does, it never runs.
- Harm is small. These are Kokoro voice blends, not recordings of anyone. But the rule "never speak in anything that sounds like the owner" is not enforced in that window.
- Fix: treat "no verdict for the current prints" as not usable and fall back to the default voice. Start the re-check from `_builtin_now` or at engine start, not only from the settings view.

**3. Picture cleaning: unchanged originals keep their hidden data (very low; read only)**
- Where: /tmp/main34/backend/jarvis_chat_picture.py:260-263 and jarvis_picture.py:250-251. When no secret is found, the original bytes go on untouched, as the file's own header says ("not even re-encoded").
- Nothing in the backend strips EXIF/GPS, an embedded thumbnail, PNG text chunks or data after the end of the file (I grepped for exif/gps). Only a picture where something was painted black gets re-encoded, and that one is clean.
- I found no way it leaves the PC. Pictures stay local (jarvis_router) and jarvis_chat_log keeps only a "has picture" flag, so the model gets EXIF it cannot read.
- It matters only if the bytes are ever stored or exported later. If the owner wants "no metadata" as a promise, re-encode in all cases or strip it. Do not describe the cleaning as removing metadata today.

**Checked and found fine (read it, most also ran it)**
- Cleaning on every path: `jarvis_agent.run_local_turn` (jarvis_agent.py ~6300) cleans every picture in every message before the second card's picture model, the main model or the text-only reader sees it. It withholds any picture it cannot check, tells the owner in the answer itself, and never re-reads the raw picture (`reader_for` refuses unknown images).
- Odd files: the "never raises" contract holds for the odd and malformed parts I read (non-data addresses, webp, oversize, more than 3 pictures, bad base64). The secret scan has a time and size limit (80,000 characters, 35 s) and fails closed. There are no temp files in any of these modules; the picture goes to Windows over stdin or in memory.
- `jarvis_photo_remind._clean_words` cleans the words before a title or date is picked.
- The 2.5-million-pixel filtered-PNG worst case took 2.3 s, so that is not a stall.
- Owner voice: the "Hear it" route and `set_speaker` accept only names from the offered list. The desktop's `speaker_name` allows only lowercase, digits and underscore, and the UI uses `textContent`, so no injection. `mix_ashby`/`mix_clara` are Kokoro vector blends, checked with `owner_check`. Animals cannot be given them (`pickable_for_animals`). No recorded voice is reachable from "Hear it".
- Downloads and files: the v1.0 pack is pinned by SHA-256 and byte size, and the install line deletes a mismatching file before unpacking. The blend file is written to a `.tmp` and kept only if its SHA-256 matches the pin. `jarvis_mouth.prepare` for v1.0 accepts only the one pinned model file, and `_check_against_model` compares the slice with the real model. I found no path traversal; the archive is pinned by hash.
- PowerShell: `scripts/apply-patches.ps1` parses with 0 errors in PowerShell 7. It has no `??`, `?.` or `&&`. The two new patches and all new shipped modules exist, and every backend module listed as shipped is present.
- Minor, not reported as bugs: the Kokoro v1.0 install line prints a misleading "not the expected file" message if the download itself fails, and each v1.0 install leaves a `tts-old-<date>` folder of about 400 MB.

No files were changed.
