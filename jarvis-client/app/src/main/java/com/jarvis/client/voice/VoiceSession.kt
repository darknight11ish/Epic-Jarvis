package com.jarvis.client.voice

import android.content.Context
import android.util.Log
import com.jarvis.client.audio.Recorder
import com.jarvis.client.audio.Speaker
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Heard
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.WakeWord
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
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
    /** Sends a turn and returns the reply, or null if it could not be sent. */
    private val chat: suspend (String) -> String?,
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
    @Volatile private var releaseRequested = false

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
        // Only now, once the previous turn is genuinely finished. Resetting it
        // while the old recorder was still running took away the one flag that
        // could stop it — `Recorder.record`'s read loop has no suspension
        // point, so cancelling its job cannot interrupt it.
        releaseRequested = false
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
                stopWhen = { releaseRequested },
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
                _micLevel.value = null
                if (_phase.value != Phase.OFF) _phase.value = Phase.OFF
            }
        }
    }

    /** Release of the button. The capture ends and the utterance goes. */
    fun release() { releaseRequested = true }

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
        releaseRequested = true
        val running = job
        job = null
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
        val reply = chat(text)
        if (reply.isNullOrBlank()) {
            _phase.value = Phase.OFF
            return
        }

        _phase.value = Phase.SPEAKING
        speak(reply)
        _phase.value = Phase.OFF
    }

    /**
     * The desktop's voice if it has one, this phone's if it does not.
     *
     * A 503 from `/api/voice/say` is an honest answer rather than a failure,
     * and falling back weakens nothing: the text is already here, so speaking
     * it reveals nothing new and skips no check. That asymmetry is the whole
     * reason one of the two voice routes may be missing and the other may not.
     */
    private suspend fun speak(text: String) {
        val said = api.say(text)
        val wav = (said as? ApiResult.Ok)?.value
        if (wav != null && wav.isNotEmpty()) {
            speaker.play(wav)
        } else {
            runCatching { speaker.speakLocally(text) }
                .onFailure { Log.w(TAG, "local synthesis failed", it) }
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
