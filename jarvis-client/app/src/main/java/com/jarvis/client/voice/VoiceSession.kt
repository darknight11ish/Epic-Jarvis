package com.jarvis.client.voice

import android.content.Context
import android.util.Log
import com.jarvis.client.audio.Recorder
import com.jarvis.client.audio.Speaker
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.SaidAloud
import com.jarvis.client.net.Heard
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.WakeWord
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * One turn of the voice loop: hold, speak, release, hear.
 *
 * Push-to-talk and the wake word are the same transport — both post one
 * complete utterance to the same endpoint and get one answer — so the wake word
 * will be a *trigger* into [begin] rather than a second path through here.
 *
 * The three verdicts are kept apart on purpose, because they are three
 * different things and only one of them is a transcript. See [Heard.Outcome].
 */
class VoiceSession(
    context: Context,
    private val api: JarvisApi,
    private val scope: CoroutineScope,
    /**
     * Sends a turn and returns the reply, or null if it could not be sent.
     * `onDelta` is called, zero or more times, with the reply accumulated so
     * far as it streams in - see [ChatSession.send]'s own doc for why this is
     * a call-local callback and not a subscription to a shared flow.
     */
    private val chat: suspend (String, onDelta: (String) -> Unit) -> String?,
) {

    enum class Phase {
        /** Nothing happening. */
        OFF,

        /** The microphone is open and the owner is speaking. */
        CAPTURING,

        /**
         * Sent. The desktop is checking whose voice it is, and only then
         * transcribing — verify first, transcribe second, so a voice that is
         * not his is never turned into words.
         */
        VERIFYING,

        /** The transcript is with the model. */
        THINKING,

        /** Jarvis is speaking the answer back. */
        SPEAKING,
    }

    val recorder = Recorder(context)
    val speaker = Speaker(context)

    private val _phase = MutableStateFlow(Phase.OFF)
    val phase: StateFlow<Phase> = _phase.asStateFlow()

    private val _micLevel = MutableStateFlow<Float?>(null)

    /** Raw per-buffer RMS while capturing. The face owns the envelope. */
    val micLevel: StateFlow<Float?> = _micLevel.asStateFlow()

    private val _status = MutableStateFlow(VoiceStatus(available = false))

    /** What the desktop says the voice path can do. Refusing defaults. */
    val status: StateFlow<VoiceStatus> = _status.asStateFlow()

    private val _answered = MutableStateFlow(false)

    /**
     * Whether `/api/voice/status` has ever actually answered.
     *
     * Kept apart from [status] because the refusing defaults make an
     * unreachable desktop indistinguishable from one that has everything
     * switched off — and for the wake word those two must never be shown the
     * same way. See [WakeWord].
     */
    val answered: StateFlow<Boolean> = _answered.asStateFlow()

    /** The wake word as three states, which is what the UI should read. */
    val wakeWord: StateFlow<WakeWord> = combine(_answered, _status) { a, s ->
        WakeWord.of(a, s)
    }.stateIn(scope, SharingStarted.Eagerly, WakeWord.UNKNOWN)

    private val _transcript = MutableStateFlow<String?>(null)

    /** What the desktop heard, shown so a mis-hearing is visible rather than acted on silently. */
    val transcript: StateFlow<String?> = _transcript.asStateFlow()

    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    private var job: Job? = null

    /**
     * One turn's identity and its own stop flag.
     *
     * Both used to be shared across turns, and both went wrong on a
     * slip-and-re-press - release the button, press again ~150 ms later:
     *
     * - The stop flag was one instance-wide `releaseRequested`, and [begin]
     *   reset it to false for the new turn. `Recorder.record`'s read loop has no
     *   suspension point, so cancelling the old turn's job cannot interrupt it;
     *   that flag was the only thing that could stop it, and the new turn had
     *   just un-set it. The old microphone stayed open to its 30-second cap.
     * - The phase was written by whichever turn happened to finish last. When
     *   the old loop finally unwound, its `finally` stamped OFF over the NEW
     *   turn's CAPTURING: the face went idle and the button un-armed while the
     *   microphone was still live, and nothing on screen said so.
     *
     * A turn now only ever writes the shared phase while it IS [current] - the
     * same guard `cancel`'s `invokeOnCompletion` already had - and reads its own
     * flag, which nobody else can clear.
     */
    private class Turn {
        @Volatile var releaseRequested = false
    }

    private var current: Turn? = null

    /** Call before offering the button. Never assumes; a failure leaves it hidden. */
    suspend fun refreshStatus() {
        when (val r = api.voiceStatus()) {
            is ApiResult.Ok -> { _status.value = r.value; _answered.value = true }
            is ApiResult.Failed -> { _status.value = VoiceStatus(available = false); _answered.value = false }
        }
    }

    /**
     * Turns the desktop's wake word off (or on), then asks what actually
     * happened.
     *
     * The re-read is not belt and braces. `/api/voice/wake` is a **config
     * write**: the value lands in the desktop's TOML and a 200 means the change
     * was accepted, not that the wake word has stopped listening. Flipping a
     * switch in the UI on the strength of that response would show "off" over a
     * microphone that is still open, which is the one lie this control must not
     * tell. So the response is discarded and [refreshStatus] decides.
     *
     * @return null on success, or a sentence to show the owner.
     */
    suspend fun setWakeWord(enabled: Boolean): String? {
        val sent = api.setWakeWord(enabled)
        if (sent is ApiResult.Failed) {
            refreshStatus()
            return "Could not reach the desktop to change that."
        }
        refreshStatus()
        if (!_answered.value) {
            return "The change was sent, but the desktop did not say what it is doing now."
        }
        if (_status.value.wakeWordOn == enabled) return null
        return if (enabled) {
            "The desktop accepted that but still reports the wake word off."
        } else {
            // The honest version of the failure this whole re-read exists for.
            "The desktop accepted the change but still reports the wake word ON. " +
                "It may need restarting before it takes effect."
        }
    }

    fun clearNotice() { _notice.value = null }

    fun clearTranscript() { _transcript.value = null }

    /**
     * Opens the microphone.
     *
     * @param source `push_to_talk` or `wake_word`. The server refuses a
     *   wake-word capture while the wake word is switched off, and says so —
     *   which is why this is passed through rather than assumed.
     */
    fun begin(source: String = JarvisApi.SOURCE_PUSH_TO_TALK) {
        val previous = job
        if (previous != null && !previous.isCompleted) {
            // Not silent. The old guard returned having done nothing — no
            // notice, no phase change — so after a 30-second capture hit its
            // cap the button was simply inert for the several seconds the
            // desktop spent verifying, with nothing on screen saying why.
            _notice.value = "Still finishing the last one."
            return
        }
        // A fresh flag for this turn rather than resetting a shared one. The old
        // code cleared the instance-wide flag here, and after `cancel()` - which
        // sets `job = null`, so the guard above lets a new turn straight through
        // - the previous loop was often still running and reading that very
        // flag. Clearing it told a recorder that had already been asked to stop
        // to carry on. See [Turn].
        val turn = Turn()
        current = turn
        _notice.value = null
        _transcript.value = null

        job = scope.launch {
            // Whatever escapes below — a throw from AudioTrack, a cancelled
            // HTTP call — the phase must not be left reading CAPTURING or
            // SPEAKING for ever, because the button and the face both render
            // from it.
            try {
            _phase.value = Phase.CAPTURING
            val maxSeconds = status.value.audioIn.maxSeconds.toFloat()
            val captured = recorder.record(
                maxSeconds = maxSeconds,
                onLevel = { _micLevel.value = it },
                stopWhen = { turn.releaseRequested },
            )
            _micLevel.value = null

            when (captured) {
                is Recorder.Result.Refused -> {
                    _phase.value = Phase.OFF
                    _notice.value = describe(captured.why)
                }
                is Recorder.Result.Captured -> deliver(captured.wav, source)
            }
            } finally {
                // Only if this turn is still the current one - the same guard
                // `cancel()`'s invokeOnCompletion carries, and for the same
                // reason. Unguarded, a turn unwinding late wrote OFF and a null
                // level over a turn that had already started, un-arming the
                // button and idling the face with the microphone open. Checking
                // the phase was not a substitute: the phase it found was the NEW
                // turn's CAPTURING, which is exactly the value it then destroyed.
                if (current === turn) {
                    _micLevel.value = null
                    if (_phase.value != Phase.OFF) _phase.value = Phase.OFF
                }
            }
        }
    }

    /** Release of the button. The capture ends and the utterance goes. */
    fun release() { current?.releaseRequested = true }

    /**
     * Slide-away, or a second thought. Nothing is sent and nothing is kept.
     *
     * The phase is cleared twice on purpose. Once now, because the button must
     * go idle the instant the finger leaves it and a cancelled HTTP call does
     * not unwind instantly; and once when the coroutine has actually finished,
     * because between those two moments it may still run as far as its next
     * suspension point and write a phase of its own. Without the second write a
     * cancel landing in that window leaves the UI stuck in VERIFYING with
     * nothing on the way back.
     */
    fun cancel() {
        // Its OWN flag, and it stays set. Nothing resets it afterwards, so the
        // recorder this turn is holding still stops even though a new turn may
        // begin before this one has unwound.
        current?.releaseRequested = true
        val running = job
        job = null
        // Also cleared, so the turn being cancelled can no longer write the
        // phase from its `finally` - it is not the current turn any more, and
        // between here and the handler below there is nothing it should say.
        current = null
        speaker.stop()
        _micLevel.value = null
        _phase.value = Phase.OFF
        if (running == null) return
        running.invokeOnCompletion {
            // Only if no newer turn has taken over. This handler belongs to the
            // turn being cancelled, and it used to write the shared phase
            // unconditionally — so a dying turn could stamp OFF over a turn
            // that had just started, leaving the button un-armed and the face
            // idle while the microphone was open and nothing on screen said so.
            if (job == null) {
                _micLevel.value = null
                _phase.value = Phase.OFF
            }
        }
        running.cancel()
    }

    private suspend fun deliver(wav: ByteArray, source: String) {
        _phase.value = Phase.VERIFYING
        val result = api.utterance(wav, source)
        if (result is ApiResult.Failed) {
            _phase.value = Phase.OFF
            _notice.value = "Could not reach the desktop to check that."
            return
        }
        val heard = (result as ApiResult.Ok).value

        when (heard.outcome) {
            // All three of these arrive as HTTP 200. A voice that did not match
            // is a normal outcome shown plainly, never a transport error and
            // never retried — retrying a refusal would be a client quietly
            // brute-forcing the owner gate.
            Heard.Outcome.NOT_THE_OWNER,
            Heard.Outcome.NO_ENGINE,
            Heard.Outcome.REFUSED,
            -> {
                _phase.value = Phase.OFF
                _notice.value = heard.message()
                return
            }
            Heard.Outcome.TRANSCRIBED -> Unit
        }

        val text = heard.text.trim()
        if (text.isEmpty()) {
            // Belt and braces: `ok:true` with nothing in it would read
            // downstream as silence, and acting on silence is acting on
            // nothing at all.
            _phase.value = Phase.OFF
            _notice.value = "Nothing came back to send."
            return
        }

        _transcript.value = text
        _phase.value = Phase.THINKING
        speakStreamed(text)
        _phase.value = Phase.OFF
    }

    /**
     * Sends the turn and speaks the reply sentence by sentence, as it
     * arrives, rather than waiting for the whole answer - the same
     * sentence-streaming shape the desktop app's quickbar already uses for
     * its own voice turns, ported to this app's plain-text (not SSE/JSON)
     * chunked body.
     *
     * `spokenUpTo`/the queue are turn-local (declared here, not on the
     * instance) on purpose: a second voice turn cannot begin while this one's
     * `job` has not completed (see [begin]'s own guard), so there is never a
     * second call in flight to confuse this one's state with - but keeping
     * them as locals rather than fields makes that true by construction
     * rather than by remembering to reset them.
     */
    private suspend fun speakStreamed(text: String) {
        var spokenUpTo = 0
        var spokeAny = false
        val queue = Channel<String>(Channel.UNLIMITED)

        // Speaks whatever lands in the queue, one sentence at a time, in
        // order - concurrently with `chat` below, so the first sentence can
        // be playing while the model is still writing the third. Ends only
        // when the queue is closed AND drained, never merely when it is
        // momentarily empty (a fast model can easily outrun TTS).
        val drainJob = scope.launch {
            for (sentence in queue) speak(sentence)
        }

        try {
            val reply = chat(text) { soFar ->
                for ((sentence, consumedTo) in SpeechText.findSentences(soFar, spokenUpTo)) {
                    spokenUpTo = consumedTo
                    if (!spokeAny) {
                        spokeAny = true
                        _phase.value = Phase.SPEAKING
                    }
                    SpeechText.stripMarkdownForSpeech(sentence).takeIf { it.isNotBlank() }
                        ?.let { queue.trySend(it) }
                }
            }
            val remainder = reply.orEmpty()
                .let { if (spokenUpTo <= it.length) it.substring(spokenUpTo) else "" }
                .let(SpeechText::stripMarkdownForSpeech)
                .trim()
            if (remainder.isNotEmpty()) {
                if (!spokeAny) _phase.value = Phase.SPEAKING
                queue.trySend(remainder)
            }
            queue.close()
            drainJob.join()
        } finally {
            // A no-op if `join()` above already returned; the real job here is
            // covering the path where `chat` itself threw (a cancellation,
            // most likely) and the queue was never closed - without this the
            // drain coroutine would sit forever waiting for a close that is
            // not coming, alongside a turn that has already ended.
            drainJob.cancel()
        }
    }

    /**
     * The desktop's voice if it has one, this phone's if it does not.
     *
     * A 503 from `/api/voice/say` is an honest answer rather than a failure,
     * and falling back weakens nothing: the text is already here, so speaking
     * it reveals nothing new and skips no check. That asymmetry is the whole
     * reason one of the two voice routes may be missing and the other may not.
     */
    /**
     * Speaks the reply, or says plainly that it cannot.
     *
     * This used to read `(said as? ApiResult.Ok)?.value` and fall through to
     * the handset's default engine whenever that was null - which is null on a
     * *Failed* result too, not only on the 503. So both branches reached an
     * unrestricted `TextToSpeech`, and because the desktop's speech module is
     * not installed, every voice turn took that path. The text being handed
     * over is Jarvis's reply, composed from the owner's recalled facts, and on
     * a stock handset the default engine synthesises it over the network.
     *
     * Substituting this device's voice is now the server's call, and it is
     * refused unless the server says otherwise. Silence with the reply on
     * screen is an acceptable outcome; uploading it is not.
     */
    private suspend fun speak(text: String) {
        when (val said = api.say(text)) {
            is ApiResult.Ok -> when (val out = said.value) {
                is SaidAloud.Audio -> speaker.play(out.wav)
                is SaidAloud.NoEngine -> {
                    if (!out.fallbackOk) {
                        _notice.value = out.reason
                            ?: "Jarvis has no voice on this desktop. The reply is on screen."
                        return
                    }
                    val spoke = runCatching { speaker.speakOnDevice(text) }
                        .onFailure { Log.w(TAG, "on-device synthesis failed", it) }
                        .getOrDefault(false)
                    if (!spoke) {
                        _notice.value =
                            "No offline voice on this phone, so it was not spoken aloud. " +
                            "The reply is on screen."
                    }
                }
            }
            // Deliberately no fallback. `client_fallback_ok` is the only thing
            // that authorises this device to speak the text, and a failure is
            // not that - it carries no permission at all.
            is ApiResult.Failed -> {
                _notice.value = "Could not reach the desktop to speak that. The reply is on screen."
            }
        }
    }

    private fun describe(why: Recorder.Failure): String = when (why) {
        Recorder.Failure.NoPermission ->
            "Jarvis needs the microphone for this. Grant it in the platform checks."
        Recorder.Failure.Unavailable ->
            "No microphone available right now."
        Recorder.Failure.TooShort ->
            "Too short to make out. Hold the button while you speak."
        is Recorder.Failure.Failed -> "The microphone stopped (${why.detail})."
    }

    private companion object {
        const val TAG = "JarvisVoice"
    }
}
