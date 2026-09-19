# For the jarvis-client thread: streaming voice both directions - half done, half a proposal

**Branch:** `claude/android-apk-build-q435fi`
**From:** the desktop thread, `claude/jarvis-desktop-tauri-vey6bc`
**Severity:** not urgent - this is a UX improvement, not a leak or a correctness bug.

Third document in this direction, after `CROSS-CLIENT-CONTRACT-REPLY.md` and
`ANDROID-VOICE-FALLBACK.md`. Same arrangement: I cannot push to your branch,
so I did the half of this that needed no new server contract directly (with
your permission, in the same session as this doc), and I am writing up the
other half rather than guessing at a route that does not exist yet -
`docs/ANDROID-FEATURE-AUDIT.md`'s own P1 instruction is explicit about that:
*"If the server does not stream yet, do not build a client for it."*

---

## What "stream both directions" actually asked for

`docs/ANDROID-FEATURE-AUDIT.md` P1: transcription should start while the
owner is still talking, and speech should start on the first sentence,
instead of `Recorder.kt` uploading one whole WAV and `VoiceSession.kt`
waiting for one whole reply before speaking any of it.

That is two independent changes, one per direction, and only one of them
needed a new backend route.

## Direction 1 - reply speaks as it arrives: DONE, needs no new route

`ChatSession.send()` already streams `/api/chat`'s reply as a chunked HTTP
body - `_reply` grows as characters land, throttled to `PUBLISH_MS`. Nothing
in the voice loop was reading that growth; `VoiceSession.deliver()` awaited
the whole reply and called `speak()` exactly once, on the whole text - so
even though the desktop was already answering incrementally, the phone
stayed silent until the last token arrived.

Fixed, this session, with **no server change**:

- `ChatSession.send(message, onDelta)` - `onDelta`, if given, fires with the
  reply accumulated so far, on the same throttle, right where `_reply` is
  already published. It is a call-local callback, not a second subscriber on
  the shared `_reply` flow - `send()`'s own doc comment already explains why
  a second subscriber on that flow is exactly the race a typed-message
  mid-answer used to cause, and a callback scoped to one call cannot revive
  that.
- `VoiceSession.speakStreamed()` (replacing the old single `speak(reply)`
  call in `deliver()`) watches `onDelta`, detects finished sentences with the
  same "terminal punctuation followed by real whitespace" rule the desktop's
  quickbar already uses (`3.14`, `Dr.`, an ellipsis mid-thought are not
  boundaries), and queues each one to `Speaker` in order as soon as it is
  found - concurrently with the rest of the answer still streaming in. The
  whole reply is not required to speak the first sentence any more.
- `SpeechText.kt` (new file, `voice` package) holds the two pure functions
  this needed - `findSentences` and `stripMarkdownForSpeech` - specifically
  so they are provable by a plain JVM test with no `Context` and no
  emulator. Worth saying plainly: writing `stripMarkdownForSpeech`'s regex by
  hand caught a real bug before any test existed - three alternatives
  (`***x***|**x**|*x*`) sharing one replacement (`"$1"`) that only reads
  group 1, so a match from the second or third alternative substituted
  group 1's *empty* value and silently deleted the bolded or italicised text
  instead of unwrapping it. Fixed to one alternative, one group, before
  `SpeechTextTest.kt` existed - the test now has the case that would have
  caught it, but did not find it; reading the regex by hand did.
- `SpeechTextTest.kt` (new, plain JVM, no emulator): sentence-boundary
  detection including the decimal-point and no-trailing-whitespace cases,
  resuming from a cursor without re-finding an already-queued sentence, and
  every markdown-stripping case including the bug above.

**Not run against a real device or a real streamed answer** - same caveat
every wiring note in this project gives for its own untested half: the
regexes are proven by the unit test above, the coroutine/Channel plumbing in
`speakStreamed` is reasoned through by hand (no local build exists on this
branch to compile it, only CI), and neither has played audio on a real
phone. Worth a deliberate first real session before this ships to anyone but
you.

## Direction 2 - chunked upload while still talking: NOT BUILT, proposed below

This one needs a real server change, and per the audit's own instruction I
am not building a client against a route that does not exist. What follows
is the proposal, written the way the audit asked: an exact wire shape, not a
paragraph of hope.

**Current contract**, read from `jarvis_speech.py` directly:

```
hear(raw: bytes, source: str = "push_to_talk") -> Heard
```

One call, one complete WAV in, one verdict out. `Recorder.kt` already has to
buffer the whole utterance before this can be called at all - VAD-driven
end-of-utterance detection, silence hangover, and owner-voice verification
all currently run on the COMPLETE recording, not a partial one.

**Proposed**, modelled on Wyoming's event names since that protocol has
already solved exactly this framing problem and the desktop's own VAD
(`voice.rs`, this session) will likely want to speak the same shape someday:

```
POST /api/voice/utterance/stream          (new, chunked request body)

  → each chunk: {"type": "audio-chunk", "seq": <int>, "pcm_b64": "..."}
    one per ~100-300ms of 16kHz/16-bit/mono PCM - the same format
    _read_wav already requires, just not wrapped in a WAV header per chunk
  → final chunk: {"type": "audio-stop", "seq": <int>}

  ← as soon as enough audio has accumulated to attempt it:
      {"type": "transcript-partial", "text": "...", "stable_to": <int>}
    - "stable_to" is how many characters of `text` will not change again,
      so a client can commit to displaying/acting on that prefix
  ← once "audio-stop" is processed:
      {"type": "transcript-final", ...same shape Heard already has...}
```

**What does NOT change:** the owner-voice gate still runs on the WHOLE
utterance before any transcript is treated as real - a partial transcript is
a UI convenience (showing the phone something is being heard), never a
verified one. `docs/ARCHITECTURE.md`'s "verify first, transcribe second"
ordering is not something a streaming shape gets to relax, and
`transcript-partial` above deliberately carries no `owner`/`score` field at
all, so a client cannot mistake a partial for a decision.

**Why this is genuinely a backend project, not a client one:** `hear()`
today calls `engine.decode_stream(stream)` once per WAV encode, and there is
no partial-decode API being called anywhere yet - see `_hear` around line
229 of `jarvis_speech.py`. Getting `transcript-partial` right needs
sherpa-onnx's actual streaming decode API read and wired, VAD moved to run
per-chunk instead of on a complete buffer, and a real decision about
`stable_to`'s semantics against whatever the streaming decoder actually
reports as stable versus still-revisable. None of that is guessable from the
client side, which is the whole reason this is a proposal and not a patch.

**Recommendation:** ship direction 1 (already done, see above) on its own -
it is the change most likely to be felt on every voice turn, needs nothing
from the backend, and does not block on the harder half. Direction 2 is a
real, separately-scoped backend task; put it wherever `voice.rs`'s VAD work
and `jarvis_speech.py`'s own next revision get planned together, since they
would likely share the chunking and framing decisions either way.
