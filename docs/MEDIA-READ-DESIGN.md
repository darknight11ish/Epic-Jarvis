# Reading the words in a recording or video: F5 S1 (2026-10-18)

The feasibility note asked whether the text in the owner's own audio and video
can be used with the local stack alone. The answer: **yes for one on-demand
READ, with no new model; the only new outside prerequisite is the local
`ffmpeg`.** This is that smallest slice (S1), built as `my_files`'s action
`read_media` under the existing `read_files_readonly` tier. **It stores
nothing.** A searchable media index (S2) is a separate owner decision and is
not built.

## What it does

1. One file is named. The existing `jarvis_documents.allowed_path()` rule
   decides whether it may be read: only inside a listed folder, no hidden
   folder, no protected place, no reserved Windows name.
2. Caps: at most 100 MB and 10 minutes. WAV is decoded in-process; every other
   format is decoded by the LOCAL `ffmpeg` as a child process with
   `-protocol_whitelist file,pipe`, a scrubbed environment, a wall-clock
   timeout and a bounded stdout.
3. Speech: the existing sherpa-onnx **Parakeet TDT** model through
   `jarvis_speech._transcribe()`. Audio is cut into 10-second windows; silent
   windows are skipped; each remaining window returns a timestamped segment.
   **English only**, no speaker labels, no summary.
4. Video: additionally one frame every 10 seconds (at most 60) through the
   existing Windows OCR (`jarvis_ocr.read_text()`). No vision model is used.
5. The result is bounded (~20,000 characters) and carries `{path, seconds}`;
   the agent's existing `took_in` path marks it as outside text and
   `jarvis_sources.from_tool_result` shows the file and duration. Nothing is
   stored or sent anywhere.

## Measured cost (feasibility run, this PC, 2026-10-18)

| Measurement | Result |
| --- | --- |
| STT model on disk | 661.2 MB (`encoder.int8.onnx` 652.2 MB) |
| STT model load | 2.66 s cold, once per process |
| STT decode, 60 s audio | 4.93 s cold / 4.96 s warm = **~4.9 s per audio minute** |
| STT peak RSS | **1,225 MB** while decoding 60 s (~716 MB after load) |
| Transcript output | 982 characters / 184 words per minute |
| ffmpeg 60 s video: audio extract | 0.081 s |
| ffmpeg 60 s video: 1 fps frames | 0.278 s, ~2.9 MB transient |
| Windows OCR per frame | 0.022-0.024 s; 6 sampled frames/minute = 0.136 s |
| **Text-only video total** | **~5.4 s per video minute** |
| Vision (not used) | qwen3-vl 27.2 s/frame; qwen2.5vl:7b not installed |

One audio minute costs about 5 seconds; one video minute about 5.4 seconds,
plus a 2.7 s model load once per process and about 1.2 GB peak RSS - which is
why one file is capped and two reads never run at once.

## Honest limits

* English only; segment timestamps; no diarization; a transcript, not a summary.
* Video is text-only: frames are OCR'd for visible words, there is no picture
  understanding and no vision model in S1.
* **ffmpeg is a new outside prerequisite** for everything except WAV. It is
  installed here but is not in `requirements.txt`/`.lock` (a binary, not a
  Python package); the reader refuses in one sentence when absent, runs it only
  as a bounded child with the protocol whitelist, and never downloads/updates it.
* **No live "owner is talking" flag exists in this tree yet.** The reader has
  the pause seam and its test; the chat turn is single-flight, and one read at a
  time is enforced. Wiring a real live-voice pause is part of a later slice.
* Measured on one repeated speech clip and one static-slide video; no varied or
  noisy recordings, no real camera video, no language except English, no
  long-run memory growth, no live-voice contention test. Try it on two or three
  of the owner's own files before calling it finished.

## Why S2 is not here

A persistent transcript index is a NEW retained copy of private speech and
needs its own owner switch, storage, deletion/forget and backup-exclusion rules.
S1 leaves nothing behind; that is the point of calling it a read. S2 is a
separate decision and is not started.

## S2, built on the owner's decision of 2026-10-19

The separate decision was put to the owner as a clickable multiple choice on
2026-10-19 14:50 PT. They chose **B - keep the transcript text too**, and added
**"built in the next slice, on by default."** That slice is
`backend/jarvis_media_index.py` (JARVIS-API section 149): an index at
`~/.openjarvis/media-index.db` holding the READABLE words, only from the
owner's listed folders, never the audio/video itself, never a learned fact,
with rows for deleted/moved files dropped on the next run, one Delete that
removes the index file, and `media-index.db` excluded from backups from day
one so that Delete cannot be undone. The switch ships ON (the owner's explicit
override of this brief's recommendation), OFF is instant, and turning it back
ON is one normal approval card. S1's read of one file is unchanged by it.
