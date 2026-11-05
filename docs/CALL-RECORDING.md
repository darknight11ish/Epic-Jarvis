# Recording a phone call, on this PC, into a new Obsidian note

**What it is.** The owner's request of 2026-11-04, in their own words: *"add the
ability of jarvis to record a call if I tell it a keyword 'record call' where it
will record all the audio, transcribe it, put a date and identify the speakers
in the transcription, and store all of it in a new obsidian note labeled with
the date and time"*. The call is taken through the Android Jarvis app.

Two halves:

- **the phone** (its own pull request, against the same frozen contract) records
  the call and uploads it;
- **this PC** (`backend/jarvis_call_notes.py`, routes from
  `plugins/ready/call-notes`) assembles the audio, transcribes it locally,
  labels who spoke, and creates ONE new note named for the date and time.

**Both halves exist as pull requests; neither was driven on a real call.** The
owner's Pixel 9 was not attached while either lane was built, so how the speaker
path really sounds and how good the words are afterwards are NOT-TESTABLE until
his own field test - see "What is not done" at the bottom, which is the honest
list rather than a promise. The feature is off by default until he turns it on.

## 1. Why the phone records through its microphone (the platform truth)

Not contradicted anywhere in the code or the docs:

- The call happens on the owner's phone, and his primary phone is a **Google
  Pixel 9**. This PC can neither see nor hear that call.
- **Android does not let an ordinary app capture the call's own audio stream.**
  `MediaRecorder.AudioSource.VOICE_CALL` is privileged; a normal app asking for
  it gets silence or a `SecurityException`. There is no third-party route to the
  downlink/uplink mix.
- So the phone records **through its microphone with the call on speaker** -
  the "speaker path" - and the PC does everything after.
- **No real call was driven on that phone by either lane.** The Pixel was not
  attached while this was built (the Android half's own pull request says the
  same), so how the speaker path really sounds, how much of the far end it
  catches, and how good the words are afterwards are **NOT-TESTABLE** until the
  owner's own field test. Nothing here claims otherwise.

**The honest quality caveat.** The far end is heard through the speaker and
re-recorded by the phone's microphone, so it is quieter, roomier and noisier
than a system recorder would give, and the words are less reliable than a
recording of the call's own stream. Nothing in this feature claims otherwise,
and the note itself says where the sound came from.

**If the phone's built-in call recorder exists**, importing its file is a later
addition. It is NOT built here and is not claimed.

## 2. The wire contract (phone → PC)

Everything is JSON over the same origin+token rules as every other route
(`X-Jarvis-Token`, and `X-Jarvis-Client: hud` from either app). One audio shape
only - 16 kHz, mono, signed 16-bit little-endian PCM - because a second shape
would be a second decoder nobody needs.

    POST /api/call/recording/start
         {"started_at": "2026-11-04T13:36:05-08:00",
          "sample_rate": 16000, "channels": 1,
          "format": "s16le", "device": "phone"}
      -> 200 {"ok": true, "session": "call_<24 hex>", "state": "recording",
              "sample_rate": 16000, "channels": 1, "format": "s16le"}
         202 {"ok": true, "session": ..., "state": "waiting",
              "message": "An approval card is waiting on this PC..."}
         400 {"ok": false, "state": "refused", "error": "<one sentence>"}
         403 {"ok": false, "state": "off"|"refused", "error": "<one sentence>"}

    POST /api/call/recording/chunk
         {"session": "call_...", "seq": 1, "data_b64": "<base64 PCM>"}
      -> 200 {"ok": true, "session": ..., "seq": 1, "bytes": 32000,
              "chunk_bytes": 32000}
         404 {"ok": false, "error": "that recording is not on this PC..."}
         409 {"ok": false, "state": "waiting", "error": "..."}      (card up)
         409 {"ok": false, "expected": <n>, "error": "...in order..."}
         413 {"ok": false, "error": "...over the 512 KiB limit..."}
         400 (bad base64, an empty chunk, a missing seq or one below 1)

    POST /api/call/recording/finish
         {"session": "call_...", "duration_sec": 812.4,
          "title": "Talk with Sam", "consent_notice": "on"}
      -> 200 {"ok": true, "session": ..., "receipt": "<one line>",
              "note": "<vault path>" | "pending", "wav": "<path>",
              "recording": {...}}
         400 (no `consent_notice: "on"`, or no audio arrived)
         403 (the feature is off, or the start card was denied)
         409 (already finished, or not recording yet)

    GET  /api/call/recording              (this PC only)
      -> 200 {"ok": true, "enabled": true, "recordings": [ {...}, ... ],
              "where": "<the recordings folder>"}
    GET  /api/call/recording?session=call_...   (this PC only)
      -> 200 {"ok": true, "recording": {...}}; 404 for an unknown id
         403 from any device but this PC

**The rules a client must follow**

1. **In order, from 1.** `seq` starts at **1** (the Android half's own first
   chunk) and goes up by one per chunk; a gap or a repeat is refused with 409
   and the number it wanted, and seq 0 is a 400. The PC never re-orders or
   guesses. `bytes` in the answer is the running total the PC holds, and
   `chunk_bytes` is the piece that just landed.
2. **At most 512 KiB per chunk decoded** (16 seconds of 16 kHz mono); about
   683 KiB once base64 is applied, comfortably inside the PC's 4 MiB request
   ceiling. A longer call is fine - 4 hours in all.
3. **Nothing is kept while the card waits.** A `start` that answers 202 has
   created a session but records nothing; a chunk before the card is approved
   is refused with 409 `state: "waiting"`. The phone keeps recording and retries
   the same number; there is **no poll**, because the read route is PC-only (see
   §8), so the phone has no read route at all.
4. **`consent_notice: "on"` is required to finish.** It is the phone saying the
   "this call is being recorded" notice was shown. A missing or different value
   is refused.
5. **`finish` returns before the words exist.** The 16 kHz mono WAV is
   assembled and the transcription starts on a daemon thread; `note` says
   `pending` until the transcription thread has created the note (or failed).
   The **`receipt` is a STRING** (one line: session, length, lines, speakers,
   note or pending) and the structured record rides in `recording`; the phone
   cannot poll for more, so a refused `finish` means "keep the audio and retry
   later", never "delete it".

**The session record** (`receipt.json` beside the audio, and the `recording`
object on `finish` and the `GET`) carries: `session`, `status` (`waiting` |
`recording` | `transcribing` | `done` | `refused` | `empty` | `failed`),
`started_at`, `finished_at`, `duration_sec`, `sample_rate`, `channels`, `format`,
`device`, `bytes`, `chunks` (how many were taken), `audio`, `note`, `note_job`,
`transcript`, `speakers`, `speaker_method`, `speaker_why`, `lines`, `message`,
`consent_notice`, `english_only`, and `date`. `finish`'s `receipt` string is the
one-line summary of the same facts.

This is the session's own record - what was recorded and where it went. It is
not an action receipt with an Undo; the note's create leaves its own undo
receipt through the notes editor.

## 3. The chat directive (`call_record`)

The eight whole messages (and nothing else) are the owner's command:

| says | does |
|---|---|
| "record call", "record this call", "record the call", "start recording the call", "start call recording" | arms the phone's recorder |
| "stop recording", "stop the call recording", "stop call recording" | stops it |

They are matched **whole-message only**, after the repo's own tidier
(`normalize_spoken_command`, which drops a polite lead-in like "can you ..." for
every command in that file). "record call now", "record a call" or "I recorded a
call yesterday" are the model's sentences.

The chat answer carries ONE new field in `X-Jarvis-Route`:

```json
"call_record": {"action": "arm"}
```

or

```json
"call_record": {"action": "stop"}
```

The Android app reads it and starts/stops its own recorder. The reply says
plainly what will happen (the phone records on speaker, the PC transcribes and
labels, the note is created at the end, tell the other person) and, when this
PC's tier makes the start ask, that a card will appear. With the feature
switched off the reply says so and **the directive is absent** - an app that
acts on `call_record` must treat its absence as "record nothing".

"stop recording" is always answered, even with the feature off: stopping only
narrows what is happening.

## 4. Transcription - the local reader, nothing new

`jarvis_media_read.read_media(path)` - the existing sherpa-onnx Parakeet TDT
model (`jarvis_speech._transcribe`), English only, no network - transcribes the
assembled WAV. Its own ceiling is 10 minutes per file, so a longer call is cut
into **9-minute parts of the same WAV** and each part's segment times are
shifted by its offset. One engine, one loop; no second speech-to-text and no
model download.

A segment is the reader's own **~10-second window**. Two people talking inside
one window get one label; that is the reader's granularity, said here rather
than papered over. A part that cannot be read (for example while Jarvis is
listening or speaking on this PC) is retried six times, and then recorded in the
note as "(not transcribed: ...)" - never filled in with invented words.

## 5. Speaker labels

Local only, from assets already on this PC
(`<config dir>/voice-models/speaker/model.onnx`, plus `strong.onnx`):

1. **The owner first.** Each segment's speaker embedding
   (`jarvis_voice.EcapaEmbedder`, the real speaker model) is compared with the
   owner's enrolled print (`jarvis_voice.find_profile("phone")` - its centroid
   and every sub-print, whichever scores highest) using `jarvis_voice.cosine`
   and the print's OWN threshold. At or above it: **You**.
2. **Then clusters.** Every other segment joins the cluster it is at least
   `SPEAKER_MERGE_SIMILARITY` (0.55) similar to; otherwise it starts one, up to
   six. A final merge pass joins clusters that similar, until none are. Clusters
   are numbered **Speaker 1, Speaker 2, ...** in the order they first speak.
3. **Short lines** (under 0.6 s) or empty embeddings carry the previous line's
   label; they never invent a name.
4. **If the speaker model is not installed, or no voice has been trained, EVERY
   line says "Speaker"** and the note records which of the two was missing
   (`speaker_labels_why`). Never a guessed name, never "You" on a guess.

## 6. The note

A NEW file, never an edit: `Calls/YYYY-MM-DD HHMM - Call.md` (a second call in
the same minute gets " (2)", " (3)", ...). Created through
`jarvis_notes_edit.handle_create()` - the notes editor's own public create path
- so the vault/protected/hidden/collision checks, the File Guardian copy, the
undo receipt and the ONE `edit_vault_note` card are the ones the owner already
has. The transcript is marked `after_outside_text` provenance, because a call's
words are other people's, so that card is never skipped.

```markdown
---
date: 2026-11-04
started_at: "2026-11-04T13:36:05-08:00"
duration: "13m 32s"
duration_seconds: 812
source: "phone call, speaker recording"
speakers: ["You", "Speaker 1"]
audio: "C:\\Users\\pcadmin\\.openjarvis\\call-recordings\\call_...\\audio.wav"
session: "call_..."
consent: "Recorded locally; tell the other person"
speaker_labels: "owner-print+clusters"
english_only: true
---

# Call - 2026-11-04 13:36

> Recorded locally; tell the other person.

Source: phone call, speaker recording (Android cannot record the call's own
audio, so the phone records it through its microphone with the call on
speaker). Transcribed on this PC.

Speakers: You, Speaker 1.

[13:36:09] You: hello?
[13:36:12] Speaker 1: hi, can you hear me?
...
Audio: C:\Users\pcadmin\.openjarvis\call-recordings\call_...\audio.wav
```

Every line's time is the **time of day** it was said (the call's start plus the
segment's offset).

**If the vault is missing or invalid**, the transcript is still written as
`transcript.md` beside the audio, and that path is returned with a plain
sentence saying why there is no note. The transcript is in fact **always**
written there first, so a vault problem or a refused card can never lose a
recording.

## 7. What is stored, for how long, and what deletes it

Everything stays on this PC:

    <config dir>/call-recordings/<session>/
        audio.pcm        the chunks exactly as they arrived (raw 16 kHz mono)
        audio.wav        the assembled recording (16 kHz mono, 16-bit)
        receipt.json     the session's own record (see §2)
        transcript.md    the transcript, written before the vault is touched
        part-000.wav ... temporary 9-minute cuts; deleted as soon as they are read

The folder is `JARVIS_CALL_RECORDINGS` if set, else `<config dir>/call-recordings`
(the config dir is `OPENJARVIS_CONFIG_DIR` / `JARVIS_CONFIG_DIR`, else
`~/.openjarvis`). The audio is **not encrypted at rest**; see §9.

### 7.1 The retention policy

**A recording and its transcript are kept until the owner deletes them.**
Nothing expires on a timer, and nothing is pruned for age: a call the owner
asked Jarvis to record is not something a background job may throw away, and a
note in the vault would outlive a deleted recording either way, so an automatic
expiry would produce a note with no audio behind it and no way to tell.

Three things touch a recording, and only one of them deletes:

1. **`POST /api/call/recording/delete` - the only route that deletes.** PC-only,
   ONE `delete_call_recording` approval card at tier `ask`, one recording per
   request, no bulk form, no undo. It removes the whole folder for that session
   (`audio.pcm`, `audio.wav`, `transcript.md`, `receipt.json` and any
   `part-*.wav`), which is also that recording's row in `GET
   /api/call/recording`. It refuses (409, in words) while the session is still
   `recording` or `transcribing`, because a folder must not vanish under a live
   writer. It does **not** need the feature switch on: removing something is
   the safe direction, and an owner who has switched the feature off must still
   be able to delete what it kept.
2. **The 400-recording cap - refuses, never deletes.** `start` answers 507 when
   the folder already holds 400 recordings, and names the folder. Nothing is
   removed to make room; the owner deletes with the route above (or by hand)
   and asks again. A `waiting` session counts toward the cap, so a refused
   start's own folder is one of the ones the owner may want to delete.
3. **The owner, by hand.** `%USERPROFILE%\.openjarvis\call-recordings\` is a
   dot-folder Explorer hides by default; typing the path into the address bar
   opens it. Deleting a session's folder by hand is equivalent to the route.

**The Obsidian note is not deleted by the route.** It is a document of its own,
written through the notes editor (its own card, File Guardian copy and undo
receipt), and it may since have been edited. The delete route's answer names
the note path so the owner knows what is left; deleting the note is done in
Obsidian, or through the notes editor's own delete.

**`part-*.wav`** are temporary cuts made only while transcribing; each is
deleted as soon as it has been read, so they do not accumulate.

## 8. Safety

- **Starts only from the owner's own command.** The keyword or the phone app
  asks `POST .../start`, and that route asks the approval gate under the action
  **`record_call`** - tier `ask` in the shipped `jarvis-framework.toml`. Never
  on boot, never on a timer, never because something else asked.
- **Off by default.** `[call_recording] enabled = false`. Turning it on is a
  hand edit of that one line - there is no in-app switch, the same shape
  `github_search` and `shell_exec` use. With the table missing, it is off too.
- **The consent reminder** is on the phone (its own recording notification), on
  the start card, in the reply, in the note's frontmatter and as a visible line
  in the note's body. `consent_notice: "on"` is required before a recording can
  be finished.
- **No network, no tunnel, no cloud.** The module imports no HTTP client and
  opens no socket. The audio and the words never leave this PC.
- **The three POST routes for the audio are the phone's by necessity; the read
  route and the delete route are PC-only.** The device that holds the
  microphone is the phone, so a PC-only start would make the feature impossible;
  their controls are the origin+token checks on every request, the `record_call`
  card, and the feature being off until the owner turns it on, with the note
  write keeping the editor's own `edit_vault_note` card. `GET
  /api/call/recording` and `POST /api/call/recording/delete` are a DIFFERENT
  matter: the first lists the owner's recordings and the note paths they went
  to, the second deletes one, so both refuse any device but this PC through
  `jarvis_owner_check.from_this_pc`, exactly as `jarvis_media_index` refuses its
  own POST. The phone has no read route and deletes nothing on the PC. The
  delete is its own card (`delete_call_recording`, tier `ask`) because deleting
  the audio and its transcript cannot be undone.
- **No audio before yes, and the empty folder is not audio.** The session's
  folder, its `receipt.json` and an empty `audio.pcm` are created before the
  start card (so a crash between the phone's first chunk and the approval cannot
  lose it), and not one audio byte is written until the card is approved - a
  chunk that arrives while it waits is refused with 409. A denied card leaves
  that empty session behind; the delete route removes it.
- **A call can raise two cards.** `record_call` before anything is kept, and the
  notes editor's own `edit_vault_note` card before the note is written: a
  transcript is other people's words, so it is never a card-free write.

## 9. What is not done (the honest list)

- **The Android half is its own pull request.** This one ships the PC module,
  its four routes and their tests; the phone's recorder, its notification and
  its upload loop are written against §2 and §3 of this document. **No real call
  was driven on the owner's Pixel 9 by either lane**, so how the speaker path
  sounds and how good the words are afterwards are NOT-TESTABLE until his own
  field test. The feature is off by default until he turns it on.
- **The card's warning line is the action's own, not the generic one.** The
  gate's `_RISK` table HAS a row for `record_call` (added 2026-11-05):
  `("yes", "local", ...)` - a recording changes nothing on this PC, can be
  deleted again, and never leaves the machine. Before that row the gate treated
  the action as unclassified and its card printed the generic "unclassified
  action - treated as permanent and able to leave this PC"; **the second half of
  that sentence was wrong for this action**, and it is the sentence the row
  replaced. The tier is still `ask` - the row does not loosen it.
- **A repeated `seq` is accepted, not refused (2026-11-05).** A chunk whose `seq`
  is below the next one the recording needs is a retry of a chunk the PC
  already has - the phone died between the PC's 200 and its own `sent.txt`
  append - so the route answers 200 with `already: true` and writes nothing.
  Only a `seq` above the next one is a gap, and only a gap is a 409. The phone
  half reads `expected` off the 409 and marks everything below it as sent.
  Refusing the repeat retried the same number for ever and made a recording
  permanently unsendable.
- **The audio is not encrypted at rest.** `audio.pcm`, `audio.wav` and
  `transcript.md` are plaintext under `<config dir>/call-recordings`, protected
  by the PC's own account, the feature being off by default and the delete
  route. Encrypting them is an OWNER decision and is **not implemented** here;
  §7 lists what deletes them instead.
- **No import of the phone's own call recorder.** Not built (§1).
- **English only**, because the local reader is English only.
- **A segment is the reader's 10-second window**, so overlapping speakers in one
  window share a label.
- **Nothing was driven on real hardware by this lane.** No real phone
  recording, no real transcription run, no real speaker model run, no real vault
  write and no real approval card. `backend/test_call_notes.py` drives fake
  readers, fake embedders, fake voice prints and a fake note creator. Those rows
  are **NOT-TESTABLE** here, never "passed".
