package com.jarvis.client.voice

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.jarvis.client.audio.Recorder
import com.jarvis.client.audio.Speaker
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.SaidAloud
import com.jarvis.client.net.Heard
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.VoiceStrict
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
     * Why a state-changing request cannot go now (the runtime's
     * `actionBlocker()`: a stale or dropped link, rule 4), or null. Read only
     * by [setWakeWord], and only for turning it ON - see
     * [WakeRules.requestBlocker].
     */
    private val linkBlocker: () -> String? = { null },
    /**
     * What the phone knows about tools right now, for "private answers stay
     * on screen" ([PrivateAloud]): how many `step` events said a tool ran,
     * how many times the event stream dropped, and whether it is live. The
     * default knows nothing - so nothing private-looking is read aloud.
     */
    private val toolWatch: () -> PrivateAloud.Watch = { PrivateAloud.Watch(0, 0, live = false) },
    /**
     * Sends a turn and returns the reply, or null if it could not be sent.
     * `onRoute` is called once with the answer's `X-Jarvis-Route` header (or
     * null) before any words; `onDelta`, zero or more times, with the reply
     * accumulated so far as it streams in - see [ChatSession.send]'s own doc
     * for why these are call-local callbacks and not subscriptions to a
     * shared flow.
     */
    private val chat: suspend (String, onRoute: (String?) -> Unit, onDelta: (String) -> Unit) -> String?,
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

    private val _strict = MutableStateFlow(VoiceStrict.View())

    /**
     * The stricter voice check, from the same `/api/voice/status` read as
     * [status]: very strict or balanced, private answers, training in
     * rounds, the repeat numbers. An older PC's defaults: none of it.
     */
    val strict: StateFlow<VoiceStrict.View> = _strict.asStateFlow()

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

    private val _speakingText = MutableStateFlow<String?>(null)

    /**
     * The sentence being spoken right now, or null. Read by the barge-in
     * listener ([BargeIn.decide]): while Jarvis itself says "stop", its own
     * voice from the speaker must not count as the owner's stop word.
     */
    val speakingText: StateFlow<String?> = _speakingText.asStateFlow()

    private val recentSpeech = RecentSpeech()

    /**
     * Every sentence Jarvis is saying now or said in the last few seconds
     * ([RecentSpeech.WINDOW_MS]). Read by the barge-in listener alongside
     * [speakingText]: the stop head fires after the quiet that follows a
     * word, when Jarvis may already be on its next sentence, so "is the
     * current sentence saying stop" alone missed its own voice.
     */
    fun recentlySpoken(): List<String> = recentSpeech.texts(SystemClock.elapsedRealtime())

    /**
     * Silences the reply being spoken - and nothing else. The turn carries
     * on (the answer still arrives on screen); only the voice stops, for the
     * rest of this turn. The one thing the stop word may do.
     *
     * "For the rest of this turn" is held by the turn's own
     * [Turn.silenced], not only by the speaker's stop flag. Before, the
     * later sentences still went to the PC's say route one by one (the PC
     * made audio nobody would hear), and when the PC had no voice the
     * phone's own voice refused them - which was then reported as "No
     * offline voice on this phone", a false notice.
     */
    fun stopSpeaking() {
        current?.silenced = true
        speaker.stop()
        _speakingText.value = null
    }

    /**
     * "Hey Jarvis" said over a reply: the old turn ends NOW, so the new
     * sentence can be sent at once - the way the desktop aborts its old
     * stream when it is interrupted.
     *
     * Before, the listener stopped the voice and then waited for the whole
     * old answer to finish arriving from the model (tens of seconds for a
     * long one) with the face stuck on "speaking", and only then sent what
     * the owner had just said. Now the old turn's speech is stopped and its
     * job cancelled - which cancels its chat stream, and with it the HTTP
     * call (see `ChatSession.send`'s `closer`) - and its own `finally` puts
     * the phase back to OFF as it unwinds. The cut-off answer stays on screen
     * as far as it got; it is not added to the conversation, as any
     * interrupted answer is not.
     *
     * Not suspending, on purpose: the listener calls this and goes straight
     * on recording the owner's next words, and the microphone's buffer holds
     * well under a second - waiting here for the old turn to unwind could
     * lose the start of the sentence. [deliverWakeClip] waits for it instead,
     * when the new clip is ready to go.
     *
     * Nothing is approved, sent or decided here: the new sentence still goes
     * through every check the desktop makes on any "hey Jarvis".
     */
    fun interruptForWake() {
        stopSpeaking()
        val running = job ?: return
        interrupted = running
        running.cancel()
    }

    /** The turn [interruptForWake] cancelled, until [deliverWakeClip] has waited for it. */
    @Volatile private var interrupted: Job? = null

    private var job: Job? = null

    /**
     * The job [cancel] just tore down, if it has not actually finished
     * unwinding yet - see [begin]'s own use of it.
     *
     * `job` itself is nulled out synchronously in [cancel], with no `join`,
     * so a re-tap landing right after a cancel sees `job == null` and sails
     * straight through the "still finishing" guard in [begin] - correctly,
     * for the state THAT guard is about (button-vs-button double taps), but
     * `job` going null is not evidence the old turn's hardware is free.
     * `Recorder.record`'s read loop blocks on `AudioRecord.read` between
     * checks of its stop flag, so `job.cancel()` (a cooperative request) does
     * not interrupt an in-flight read - the old `AudioRecord` is not
     * `release()`d until that read returns and the loop notices the flag.
     * Rapid slide-to-cancel-then-retap could race a brand new `AudioRecord`
     * against a hardware handle the platform had not freed yet.
     */
    private var releasing: Job? = null

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

        /** "Stop" was said: nothing more of this turn's reply is spoken. See [stopSpeaking]. */
        @Volatile var silenced = false
    }

    private var current: Turn? = null

    // The guard the [Turn] doc above promises ("a turn now only ever writes
    // the shared phase while it IS current"), actually applied to every
    // write rather than to one.
    //
    // Only `begin`'s `finally` carried it. Everything in `deliver` and
    // `speakStreamed` wrote `_phase`/`_notice`/`_transcript` unconditionally,
    // and those run on Dispatchers.Default with long stretches that have no
    // suspension point - so `Job.cancel()` cannot interrupt them. A turn
    // whose `api.utterance` had already returned would run on while the owner
    // slid to cancel and pressed again, then stamp its own OFF and its own
    // "that wasn't you" notice over the NEW turn: button un-armed, face idle,
    // stale notice on screen, and the microphone recording for the turn that
    // is actually live. Verbatim the failure the doc says was eliminated.
    private fun setPhase(t: Turn, phase: Phase) {
        if (current === t) _phase.value = phase
    }

    private fun setNotice(t: Turn, text: String?) {
        if (current === t) _notice.value = text
    }

    private fun setTranscript(t: Turn, text: String?) {
        if (current === t) _transcript.value = text
    }

    private fun setMicLevel(t: Turn, level: Float?) {
        if (current === t) _micLevel.value = level
    }

    /** Call before offering the button. Never assumes; a failure leaves it hidden. */
    suspend fun refreshStatus() {
        // One read, two halves: the talk button's status as before, and the
        // stricter voice check (VoiceStrict), read field by field so that
        // nothing in it can hide the talk button.
        when (val r = api.voiceStatusRead()) {
            is ApiResult.Ok -> {
                _status.value = r.value.first
                _strict.value = r.value.second
                _answered.value = true
            }
            is ApiResult.Failed -> {
                _status.value = VoiceStatus(available = false)
                _strict.value = VoiceStrict.View()
                _answered.value = false
            }
        }
    }

    /**
     * Turns the desktop's wake word off, or asks for it to be turned on, then
     * asks what actually happened.
     *
     * The re-read is not belt and braces. Turning it ON raises an approval
     * card on the desktop (`change_own_config`) and changes nothing until the
     * card is approved, so a 200 means "a card is up", never "it is on".
     * Turning it OFF is immediate. Either way the response is discarded and
     * [refreshStatus] decides - a switch flipped on the strength of the reply
     * would show "off" over a microphone that is still open, or "on" over a
     * card nobody has approved.
     *
     * Turning it ON is held while the link is stale or down, like every
     * other request that raises a card (rule 4); nothing is sent then.
     * Turning it OFF always goes.
     *
     * @return null when the desktop now says what was asked for, or a sentence
     *   to show the owner (including "approve the card").
     */
    suspend fun setWakeWord(enabled: Boolean): String? {
        WakeRules.requestBlocker(enabled, linkBlocker())?.let { return it }
        val sent = api.setWakeWord(enabled)
        refreshStatus()
        if (!_answered.value) {
            return if (sent is ApiResult.Failed) {
                "Could not reach the desktop to change that."
            } else {
                "The change was sent, but the desktop did not say what it is doing now."
            }
        }
        val now = _status.value
        return WakeRules.afterRequest(enabled, now.wakeWordOn, now.listening.wakeWordPending)
    }

    /**
     * One clip the wake-word listener already recorded ([com.jarvis.client.service.WakeWordService]),
     * sent as `source=wake_word` and taken through the same path as a
     * push-to-talk turn from VERIFYING on: the desktop checks the phrase and
     * the voice, transcribes, and the answer is spoken.
     *
     * Returns the desktop's verdict once the whole turn is over (spoken, or
     * refused), so the listener does not hear Jarvis's own reply as a new
     * wake word. Null when it was not sent: a push-to-talk turn is running,
     * or the desktop could not be reached.
     */
    suspend fun deliverWakeClip(wav: ByteArray): Heard? {
        // A turn "hey Jarvis" just cut off may still be unwinding. It has
        // been cancelled, so this is short; without it the guards below
        // could see it half-finished and drop the owner's new sentence.
        interrupted?.let { old ->
            old.join()
            if (interrupted === old) interrupted = null
        }
        val previous = job
        if (previous != null && !previous.isCompleted) return null
        if (_phase.value != Phase.OFF) return null
        val turn = Turn()
        current = turn
        _notice.value = null
        _transcript.value = null
        var verdict: Heard? = null
        val running = scope.launch {
            try {
                verdict = deliver(turn, wav, JarvisApi.SOURCE_WAKE_WORD)
            } finally {
                if (current === turn) {
                    _micLevel.value = null
                    if (_phase.value != Phase.OFF) _phase.value = Phase.OFF
                }
            }
        }
        job = running
        running.join()
        return verdict
    }

    /**
     * One clip for "Train my voice", through the same [recorder] the talk
     * button uses, so the PC gets exactly the format it checks every other
     * utterance in (16 kHz, 16-bit mono WAV, resampled here).
     *
     * Not a voice turn: nothing is sent, nothing is transcribed, and the
     * phase the face and the talk button read is left alone. Refused while a
     * voice turn holds the microphone, rather than fighting it for the
     * hardware. Capped at [VoiceTraining.MAX_SECONDS], the PC's own limit.
     */
    suspend fun recordTrainingClip(
        stopWhen: () -> Boolean,
        onLevel: (Float) -> Unit,
    ): VoiceTraining.Take {
        if (_phase.value != Phase.OFF || job?.isCompleted == false) {
            return VoiceTraining.Take.Failed(
                "The talk button is using the microphone. Try again in a moment.",
            )
        }
        releasing?.join()
        return when (
            val r = recorder.record(
                maxSeconds = VoiceTraining.MAX_SECONDS,
                onLevel = onLevel,
                stopWhen = stopWhen,
            )
        ) {
            is Recorder.Result.Captured -> VoiceTraining.Take.Captured(r.wav, r.seconds)
            is Recorder.Result.Refused -> VoiceTraining.Take.Failed(
                if (r.why == Recorder.Failure.NoPermission) {
                    "Jarvis needs the microphone for this. Tap Allow the microphone below."
                } else {
                    describe(r.why)
                },
                needsPermission = r.why == Recorder.Failure.NoPermission,
            )
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
            setPhase(turn, Phase.CAPTURING)
            // The comment above on `previous`/`job` already covers the
            // SOFTWARE half of a rapid cancel-then-retap - the new turn no
            // longer inherits the old one's stop flag. This is the HARDWARE
            // half: `job` going null in [cancel] is not the old `AudioRecord`
            // being released, only a request that it be. Waiting here, not
            // before launching this coroutine, is what lets the button react
            // instantly (CAPTURING above is already visible) while the
            // actual microphone open stays serialised behind whatever is
            // still unwinding - typically well under the time of one audio
            // buffer, per [releasing]'s own doc comment on why `read()`
            // cannot be interrupted any faster than that.
            releasing?.join()
            val maxSeconds = status.value.audioIn.maxSeconds.toFloat()
            val captured = recorder.record(
                maxSeconds = maxSeconds,
                onLevel = { setMicLevel(turn, it) },
                stopWhen = { turn.releaseRequested },
            )
            setMicLevel(turn, null)

            when (captured) {
                is Recorder.Result.Refused -> {
                    setPhase(turn, Phase.OFF)
                    setNotice(turn, describe(captured.why))
                }
                is Recorder.Result.Captured -> deliver(turn, captured.wav, source)
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
        // Tracked separately from `job`, which is already null above - see
        // [releasing]'s own doc comment. Cleared in the SAME handler that
        // already runs on this job's completion, so nothing new is added
        // beyond remembering which job that handler belongs to.
        releasing = running
        running.invokeOnCompletion {
            if (releasing === running) releasing = null
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

    private suspend fun deliver(turn: Turn, wav: ByteArray, source: String): Heard? {
        setPhase(turn, Phase.VERIFYING)
        val result = api.utterance(wav, source)
        if (result is ApiResult.Failed) {
            setPhase(turn, Phase.OFF)
            setNotice(turn, "Could not reach the desktop to check that.")
            return null
        }
        val heard = (result as ApiResult.Ok).value

        if (source == JarvisApi.SOURCE_WAKE_WORD) {
            when (WakeRules.verdict(heard)) {
                // Not addressed to Jarvis (the desktop did not hear "hey
                // Jarvis" in it, or not from the owner): dropped without a
                // word, the way the desktop dropped it.
                WakeRules.Verdict.IGNORE -> {
                    setPhase(turn, Phase.OFF)
                    return heard
                }
                // "Hey Jarvis." and nothing after it: the listener records
                // the next sentence and sends that.
                WakeRules.Verdict.AWAKE -> {
                    setPhase(turn, Phase.OFF)
                    setNotice(turn, "Listening…")
                    return heard
                }
                // The desktop cannot do this at all right now; the listener
                // stops and shows [Heard.reason].
                WakeRules.Verdict.STOP -> {
                    setPhase(turn, Phase.OFF)
                    setNotice(turn, heard.reason.ifBlank { "The desktop cannot take \"hey Jarvis\" right now." })
                    return heard
                }
                WakeRules.Verdict.ANSWER -> Unit
            }
        }

        when (heard.outcome) {
            // All three of these arrive as HTTP 200. A voice that did not match
            // is a normal outcome shown plainly, never a transport error and
            // never retried — retrying a refusal would be a client quietly
            // brute-forcing the owner gate.
            Heard.Outcome.NOT_THE_OWNER,
            Heard.Outcome.NO_ENGINE,
            Heard.Outcome.REFUSED,
            -> {
                setPhase(turn, Phase.OFF)
                setNotice(turn, heard.message())
                return heard
            }
            Heard.Outcome.TRANSCRIBED -> Unit
        }

        val text = heard.text.trim()
        if (text.isEmpty()) {
            // Belt and braces: `ok:true` with nothing in it would read
            // downstream as silence, and acting on silence is acting on
            // nothing at all.
            setPhase(turn, Phase.OFF)
            setNotice(turn, "Nothing came back to send.")
            return heard
        }

        setTranscript(turn, text)
        setPhase(turn, Phase.THINKING)
        // Armed once, here, for the whole turn - never inside `play`. A reply
        // is spoken sentence by sentence, so clearing the flag per sentence
        // erased a cancel that had arrived during the previous one and Jarvis
        // spoke on. See `Speaker.arm`.
        speaker.arm()
        // What the phone knows about tools as the question goes: every
        // sentence is checked against it before it is read aloud.
        speakStreamed(turn, text, heard, toolWatch())
        setPhase(turn, Phase.OFF)
        return heard
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
    private suspend fun speakStreamed(turn: Turn, text: String, heard: Heard, asked: PrivateAloud.Watch) {
        var spokenUpTo = 0
        var spokeAny = false
        val queue = Channel<String>(Channel.UNLIMITED)
        // This answer's X-Jarvis-Route header, read once before any words
        // (on the HTTP thread, hence the atomic).
        val route = java.util.concurrent.atomic.AtomicReference<PrivateAloud.Route?>(null)

        // Speaks whatever lands in the queue, one sentence at a time, in
        // order - concurrently with `chat` below, so the first sentence can
        // be playing while the model is still writing the third. Ends only
        // when the queue is closed AND drained, never merely when it is
        // momentarily empty (a fast model can easily outrun TTS).
        //
        // "Private answers stay on screen": before EVERY sentence the phone
        // asks whether this answer may be read aloud (PrivateAloud). The
        // first time it may not, it says the one fixed line instead and
        // reads nothing more of this answer - which stays on the screen as
        // always. Asked per sentence because a tool can start halfway.
        val drainJob = scope.launch {
            var hushed = false
            for (sentence in queue) {
                if (hushed) continue
                if (!PrivateAloud.mayRead(heard, route.get(), asked, toolWatch())) {
                    hushed = true
                    speak(turn, PrivateAloud.ON_SCREEN)
                    continue
                }
                speak(turn, sentence)
            }
        }

        try {
            val reply = chat(text, { header -> route.set(PrivateAloud.route(header)) }) { soFar ->
                for ((sentence, consumedTo) in SpeechText.findSentences(soFar, spokenUpTo)) {
                    spokenUpTo = consumedTo
                    if (!spokeAny) {
                        spokeAny = true
                        setPhase(turn, Phase.SPEAKING)
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
                if (!spokeAny) setPhase(turn, Phase.SPEAKING)
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
    private suspend fun speak(turn: Turn, text: String) {
        // Stopped this turn: not spoken, not even asked of the PC. The reply
        // is still on screen; only the voice was told to stop.
        if (turn.silenced) return
        _speakingText.value = text
        recentSpeech.started(text)
        try {
            speakNow(turn, text)
        } finally {
            _speakingText.value = null
            recentSpeech.ended(SystemClock.elapsedRealtime())
        }
    }

    private suspend fun speakNow(turn: Turn, text: String) {
        val said = api.say(text)
        // "Stop" may have landed while the PC was making the audio.
        if (turn.silenced) return
        when (said) {
            is ApiResult.Ok -> when (val out = said.value) {
                is SaidAloud.Audio -> speaker.play(out.wav)
                is SaidAloud.NoEngine -> {
                    if (!out.fallbackOk) {
                        setNotice(
                            turn,
                            out.reason
                                ?: "Jarvis has no voice on this desktop. The reply is on screen.",
                        )
                        return
                    }
                    val spoke = runCatching { speaker.speakOnDevice(text) }
                        .onFailure { Log.w(TAG, "on-device synthesis failed", it) }
                        .getOrDefault(false)
                    // `speakOnDevice` also returns false when it was stopped;
                    // only a real failure is reported as one.
                    SpokenNotice.afterOnDevice(spoke, stoppedThisTurn = turn.silenced)
                        ?.let { setNotice(turn, it) }
                }
            }
            // Deliberately no fallback. `client_fallback_ok` is the only thing
            // that authorises this device to speak the text, and a failure is
            // not that - it carries no permission at all.
            is ApiResult.Failed -> {
                setNotice(
                    turn,
                    "Could not reach the desktop to speak that. The reply is on screen.",
                )
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
