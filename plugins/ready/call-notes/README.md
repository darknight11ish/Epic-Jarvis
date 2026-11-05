# call-notes

Recording a phone call, from the Android app to a new Obsidian note. Five
routes, so the phone can send the audio, either app can read what happened, and
the PC can delete one recording:

    POST /api/call/recording/start
         {"started_at": "2026-11-04T13:36:05-08:00", "sample_rate": 16000,
          "channels": 1, "format": "s16le", "device": "phone"}
         -> {"ok": true, "session": "call_<24 hex>", "state": "recording"}
    202 while the `record_call` approval card waits: NO AUDIO is kept until it
    is answered (the session's folder, its receipt and an empty audio.pcm are
    made first, so a crash cannot lose the first piece), and a chunk that
    arrives before then is refused with 409 - the phone keeps recording and
    retries the same seq, then the queue flows in order once the card is
    approved.

    POST /api/call/recording/chunk
         {"session": "call_...", "seq": 1, "data_b64": "<base64 PCM>"}
         -> {"ok": true, "bytes": <the running total>, "seq": 1,
             "chunk_bytes": <this piece>}
    In order from seq 1, at most 512 KiB a chunk (16 s at 16 kHz mono), 4 hours
    in all. A failed send retries the SAME number. **A repeated (lower) seq is
    not an error**: it is a chunk this PC already has (a crash between its 200
    and the phone's own bookkeeping), so it answers 200 with `already: true`
    and writes nothing twice. Only a seq above the next one is a gap, and only
    a gap is a 409.

    POST /api/call/recording/finish
         {"session": "call_...", "duration_sec": 812.4, "title": "...",
          "consent_notice": "on"}
         -> {"ok": true, "receipt": "<one line>", "note": "<path>" | "pending",
             "wav": "<path>", "recording": {...}}
    `receipt` is a STRING (the frozen contract); the structured record is
    `recording`. The 16 kHz mono WAV is assembled and the transcription starts
    on a daemon thread, so the request never waits for the model.

    GET /api/call/recording              the recent recordings (PC only)
    GET /api/call/recording?session=ID   one of them (PC only)

    POST /api/call/recording/delete
         {"session": "call_..."}
         -> {"ok": true, "state": "deleted", "removed": [...], "message": "..."}
    PC only, and ONE `delete_call_recording` card at tier `ask`: it removes
    that recording's whole folder (audio.pcm, audio.wav, transcript.md,
    receipt.json and part files), which is also its row in the list. The
    Obsidian note is a document of its own and STAYS; the answer names it.
    202 while the card waits. It does not need the feature switch on - removing
    something is the safe direction.

**Retention.** Recordings and transcripts are kept until the owner deletes
them. Nothing expires on a timer, and the 400-recording cap REFUSES a new start
rather than deleting anything; the delete route above (or the owner's own
Explorer) is the only thing that removes one. `docs/CALL-RECORDING.md` §7 is
the policy in full.

**Why the phone records on the speaker path.** The call happens on the owner's
phone, and his primary phone is a **Google Pixel 9**. Android does not let an
ordinary app capture the call's own audio stream (`VOICE_CALL` is privileged),
so the phone records through its microphone with the call on speaker, and the
far end is heard through the speaker - quieter and noisier than a system
recorder would give. That is said plainly in the docs rather than hidden.
**No real call was driven on that phone by either lane**, so how the speaker
path sounds and how good the words are afterwards are NOT-TESTABLE until the
owner's field test.

**Drop-in, and this one replaces NO patch.** The module itself
(`backend/jarvis_call_notes.py`) is shipped by `scripts\apply-patches.ps1`
exactly as before; its routes existed as no patch because it needs none. Copy
this folder into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name call-notes`) and restart Jarvis - the same
mechanism `plugins/ready/media-index` uses.

- Module the loader calls: `jarvis_call_notes.install()` (takes the core's Handler)
- The patch this replaces: none - it is born as a folder
- Position in the loader's order: 173, the first free slot after the highest
  generated folder (`skill-menu` is 172)

**Off by default.** `[call_recording] enabled = false` in
`jarvis-framework.toml`; with no such table the feature is off too. Turning it
on is a hand edit of that one line, the same shape `github_search` and
`shell_exec` use. While it is off, every route answers 403 in plain words and
nothing is written.

**The POST routes for the audio are the phone's by necessity; the read route
and the delete route are PC-only, and neither is an oversight.**
`jarvis_media_index` refuses its POST from another device because a change to
the index is a PC decision; here the device that holds the microphone IS the
phone, so a PC-only start would make the feature impossible. Their controls are
the origin+token checks on every request, the `record_call` card (tier `ask`),
and the feature being off until the owner turns it on. `GET
/api/call/recording` lists the owner's recordings and where each note went, and
`POST /api/call/recording/delete` removes one of them, so both refuse any device
but this PC (`jarvis_owner_check.from_this_pc`) - the phone has no read route
and deletes nothing on the PC. The delete is its own card
(`delete_call_recording`, tier `ask`) because deleting audio cannot be undone.

An older backend that has the module but not this folder answers 404 on the
routes; both apps then say so in words instead of showing a control that does
nothing.
