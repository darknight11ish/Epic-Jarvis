package com.jarvis.client.voice

import com.jarvis.client.audio.Wav
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * The voice flow on this phone (docs/JARVIS-API.md section 17):
 * interrupting Jarvis by talking, "One moment." when a tool starts, a small
 * "I heard you" sound, and `waited_ms`. Pure - no Android - so it is tested
 * (`VoiceFlowTest`), and these are the desktop's rules word for word
 * (jarvis-desktop `src/voice-flow.js`): both apps are held to one list of
 * cases, `jarvis-desktop/tests/fixtures/voice-flow-cases.json`.
 *
 * INTERRUPTING BY TALKING - "pause first, decide second" (LiveKit agents'
 * shape; the voice research of 2026-09-24, recommendation 4). While Jarvis
 * speaks and "Interrupt Jarvis while it talks" is on, the hands-free
 * listener hears the room through the echo canceller. When [SpeechRun]
 * has heard [ONSET_MS] of speech, the reply is PAUSED at once
 * ([InterruptFlow.onset]) - not talked over for the two seconds the check
 * needs - and about [CLIP_MS] of that speech, from where it started, goes
 * to the PC as `source=barge_in`. The PC answers one question: was it the
 * owner (or the word "stop")? Yes: the reply stops for good, and a sentence
 * made ahead is thrown away (SpeechAhead). No: it carries on from where it
 * paused. No answer within [WAIT_MAX_MS] of pausing: it carries on too.
 * Nothing on this phone turns the speech into words: [SpeechRun] measures
 * loudness only, the same rule the talk button's pause detector uses, and
 * the PC never transcribes a barge-in clip.
 *
 * The first [GRACE_MS] of a reply are ignored: that is when the echo
 * canceller is still learning the room and Jarvis's own voice most often
 * comes back through the microphone (kyutai unmute waits 3 s for the same
 * reason). "Stop" is not affected: the phone's own stop-word head
 * ([BargeIn]) works from the first word, as before.
 */
object VoiceFlow {
    /** The first part of a reply that talking over is ignored for (echo). */
    const val GRACE_MS = 3_000L

    /** Speech heard before the reply is paused. */
    const val ONSET_MS = 500L

    /** About this much speech goes to the PC: it recognised the owner from 2 s clips, not from 1.2-1.5 s. */
    const val CLIP_MS = 2_000L

    /** After the pause started, this much quiet ends the speech early: what there is goes to the PC. */
    const val END_QUIET_MS = 700L

    /** Paused and no answer from the PC this long: carry on talking. */
    const val WAIT_MAX_MS = 4_000L

    /** Kept from before the speech began, so its first sound is in the clip. */
    const val PREROLL_MS = 300L

    enum class Action { NONE, PAUSE, RESUME, STOP }

    /**
     * The marks that end a question - the PC's `jarvis_speech.QUESTION_MARKS`
     * (the shared cases' `question_marks`): ASCII, full-width, and the Greek
     * question mark U+037E.
     */
    val QUESTION_MARKS: List<Char> = listOf('?', '？', ';')

    private val GREEK = Regex("[\\u0370-\\u03ff\\u1f00-\\u1fff]")

    /**
     * Keep listening after a question (section 17, 5): does [text] - the last
     * sentence Jarvis spoke - end with a question mark? Closing quotes and
     * brackets after it are allowed; a plain ";" counts only in Greek, where
     * Unicode folds the Greek question mark into it. The PC's
     * `ends_with_question`, the same rule.
     */
    fun endsWithQuestion(text: String?): Boolean {
        val t = (text ?: "").trimEnd().trimEnd('"', '\'', '”', '’', ')', ']', '»').trimEnd()
        if (t.isEmpty()) return false
        val last = t.last()
        return last in QUESTION_MARKS || (last == ';' && GREEK.containsMatchIn(t))
    }

    /** Whether a `step` event's `data` says a tool is starting. */
    fun isToolStart(data: JsonElement?): Boolean =
        ((data as? JsonObject)?.get("phase") as? JsonPrimitive)?.takeIf { it.isString }?.content == "tool_started"

    /**
     * How long the end of a clip was quiet, in milliseconds: `waited_ms`,
     * "from the moment the speech detector last heard speech to the moment
     * the clip is sent" (section 17, 2). A 30 ms window is speech when it is
     * louder than three times the quietest window in the clip, within the
     * listener's own bounds ([WakeClip.EndOfSpeech.threshold]) - the desktop's
     * `trailing_quiet` (voice_flow.rs), the same rule. Null when nothing in
     * the clip was loud enough to be speech.
     */
    fun trailingQuietMs(pcm: ShortArray, rate: Int = Wav.SAMPLE_RATE): Long? {
        val window = max(1, rate * 30 / 1000)
        if (pcm.isEmpty()) return null
        val levels = (pcm.indices step window).map { start ->
            val n = min(window, pcm.size - start)
            Wav.rms(pcm.copyOfRange(start, start + n), n)
        }
        val floor = levels.minOrNull() ?: return null
        val bar = WakeClip.EndOfSpeech.threshold(floor)
        val lastLoud = levels.indexOfLast { it >= bar }
        if (lastLoud < 0) return null
        return (levels.size - 1 - lastLoud) * 30L
    }
}

/**
 * Interrupting by talking, as a small state machine - `createInterruptFlow`
 * in the desktop's voice-flow.js. Every call takes the time it happened at
 * ([now], milliseconds on one clock) and says what to do.
 */
class InterruptFlow {
    private var replyStartedAt: Long? = null
    private var pausedAt: Long? = null
    private var asked: Long? = null

    /** The reply made its first sound. */
    @Synchronized
    fun replyStarted(now: Long) {
        if (replyStartedAt == null) replyStartedAt = now
    }

    /** The reply is over, stopped, or a new question was asked. */
    @Synchronized
    fun replyEnded() {
        replyStartedAt = null
        pausedAt = null
        asked = null
    }

    @get:Synchronized
    val paused: Boolean get() = pausedAt != null

    /**
     * Half a second of speech was heard, clip [id]. [allowed]: the switch is
     * on, the PC says it can tell the owner's voice now, and the link is not
     * stale. PAUSE means: pause the reply and have that clip checked.
     */
    @Synchronized
    fun onset(now: Long, id: Long, allowed: Boolean): VoiceFlow.Action {
        val started = replyStartedAt
        if (!allowed || pausedAt != null || started == null) return VoiceFlow.Action.NONE
        if (now - started < VoiceFlow.GRACE_MS) return VoiceFlow.Action.NONE
        pausedAt = now
        asked = id
        return VoiceFlow.Action.PAUSE
    }

    /** The PC's answer for clip [id]: [stop] true when it was the owner or "stop". */
    @Synchronized
    fun verdict(id: Long, stop: Boolean): VoiceFlow.Action {
        if (asked == null || asked != id) return VoiceFlow.Action.NONE
        asked = null
        if (stop) {
            replyStartedAt = null
            pausedAt = null
            return VoiceFlow.Action.STOP
        }
        if (pausedAt == null) return VoiceFlow.Action.NONE
        pausedAt = null
        return VoiceFlow.Action.RESUME
    }

    /** Time passing: paused too long with no answer means carry on. */
    @Synchronized
    fun tick(now: Long): VoiceFlow.Action {
        val at = pausedAt ?: return VoiceFlow.Action.NONE
        if (now - at < VoiceFlow.WAIT_MAX_MS) return VoiceFlow.Action.NONE
        pausedAt = null
        return VoiceFlow.Action.RESUME
    }
}

/** "One moment.", at most once per spoken question - `createMomentFlow` in voice-flow.js. */
class MomentFlow {
    private var active = false
    private var played = false
    private var replied = false
    private var stopped = false

    @Synchronized
    fun turnStarted() {
        active = true
        played = false
        replied = false
        stopped = false
    }

    @Synchronized
    fun turnEnded() {
        active = false
    }

    /** The reply made (or is about to make) its first sound. */
    @Synchronized
    fun replyStarted() {
        replied = true
    }

    /** "Stop", or an interruption that stopped the reply. */
    @Synchronized
    fun stopped() {
        stopped = true
    }

    /** A tool started. [enabled]: the owner's switch and the PC's; [ready]: the clip is here. */
    @Synchronized
    fun toolStarted(enabled: Boolean, ready: Boolean): Boolean {
        if (!active || played || replied || stopped || !enabled || !ready) return false
        played = true
        return true
    }
}

/**
 * Speech over a reply, from per-step loudness only (the talk button's own
 * rule, [WakeClip.EndOfSpeech.threshold]). [step] is fed every 80 ms step
 * the barge-in listener reads, and says when half a second of speech has
 * been heard ([Event.ONSET]) and then when its clip is ready to send
 * ([Event.CLIP_DUE]): [VoiceFlow.CLIP_MS] after the speech began, or once
 * [VoiceFlow.END_QUIET_MS] of quiet ends it sooner. After a clip, a new
 * run begins only after that quiet.
 */
class SpeechRun(initialFloor: Float = 0.005f) {
    enum class Event { NONE, ONSET, CLIP_DUE }

    private var floor = initialFloor

    /** When the current run of speech began, or null in quiet. */
    var startedAt: Long? = null
        private set

    private var voicedMs = 0L
    private var lastVoicedAt = 0L
    private var told = false
    private var sent = false

    fun step(now: Long, level: Float, stepMs: Long): Event {
        val voiced = level >= WakeClip.EndOfSpeech.threshold(floor)
        if (!voiced) floor = WakeClip.EndOfSpeech.updateFloor(floor, level)
        val begun = startedAt
        if (begun == null) {
            if (!voiced) return Event.NONE
            startedAt = now - stepMs
            voicedMs = stepMs
            lastVoicedAt = now
            told = false
            sent = false
            return if (voicedMs >= VoiceFlow.ONSET_MS) onset() else Event.NONE
        }
        if (voiced) {
            voicedMs += stepMs
            lastVoicedAt = now
        }
        val quiet = now - lastVoicedAt
        if (!told) {
            if (voicedMs >= VoiceFlow.ONSET_MS) return onset()
            if (quiet >= VoiceFlow.END_QUIET_MS) startedAt = null // a cough: forgotten
            return Event.NONE
        }
        if (!sent && (now - begun >= VoiceFlow.CLIP_MS || quiet >= VoiceFlow.END_QUIET_MS)) {
            sent = true
            return Event.CLIP_DUE
        }
        if (sent && quiet >= VoiceFlow.END_QUIET_MS) startedAt = null
        return Event.NONE
    }

    private fun onset(): Event {
        told = true
        return Event.ONSET
    }
}

/**
 * Where the owner cut the last spoken answer off (section 17, 6): the
 * sentence they heard last, handed to the NEXT question - typed or spoken -
 * as `interrupted`, so the PC can tell its model that the answer was cut off
 * there. Once only, and only within [keepMs]: a question an hour later is
 * not a reply to the interruption. The desktop's `createCutOff`.
 */
class CutOff(private val keepMs: Long = KEEP_MS) {
    private var said: String? = null
    private var at = 0L

    /** The owner stopped the answer while [sentence] was the last one heard. */
    @Synchronized
    fun cut(sentence: String?, now: Long) {
        val s = sentence?.trim()
        if (s.isNullOrEmpty()) return
        said = s
        at = now
    }

    /** The sentence for the question being sent now, or null - and forgotten either way. */
    @Synchronized
    fun take(now: Long): String? {
        val s = said
        said = null
        return s?.takeIf { now - at <= keepMs }
    }

    companion object {
        /** Two minutes. */
        const val KEEP_MS = 120_000L
    }
}

/** The PC's answer to a barge-in clip. */
data class BargeVerdict(val stop: Boolean, val available: Boolean, val why: String) {
    companion object {
        /** An interruption that could not be checked never stops the reply. */
        val FAILED = BargeVerdict(stop = false, available = true, why = "failed")

        /**
         * `{"stop", "available", "why", ...}`. A route without
         * voice-flow.patch answers the usual utterance reply, whose `stop`
         * means the same (section 17). Anything unreadable is [FAILED].
         */
        fun read(body: JsonObject?): BargeVerdict {
            if (body == null) return FAILED
            fun flag(key: String): Boolean? = (body[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull
            return BargeVerdict(
                stop = flag("stop") ?: false,
                available = flag("available") ?: true,
                why = (body["why"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull.orEmpty(),
            )
        }
    }
}

/** "Say 'One moment' if I'm kept waiting": this phone's own switch, on by default. */
object OneMoment {
    /** The switch's name - the desktop's `MOMENT_NAME`, the words section 17 suggests. */
    const val NAME = "Say \"One moment\" if I'm kept waiting"

    /** The desktop's `describeMoment`, word for word. */
    fun describe(on: Boolean): String = if (on) {
        "On: when Jarvis has to look something up for a spoken question, it says \"One moment.\" " +
            "first, once, in its own voice."
    } else {
        "Off: Jarvis stays quiet until its answer is ready."
    }
}

/**
 * "I heard you": a tiny two-note sound when the owner's turn is cut, made
 * from numbers (no file, no new dependency) - the desktop's `HEARD_SOUND`,
 * the same numbers, so both apps sound alike.
 */
object HeardSound {
    const val RATE = 24_000
    val TONES: List<Pair<Int, Int>> = listOf(660 to 55, 990 to 75) // (hz, ms)
    const val GAP_MS = 25
    const val FADE_MS = 10
    const val GAIN = 0.16

    fun samples(): ShortArray {
        val fade = (RATE * FADE_MS / 1000.0).roundToInt()
        val gap = (RATE * GAP_MS / 1000.0).roundToInt()
        val out = ArrayList<Short>()
        TONES.forEachIndexed { i, (hz, ms) ->
            if (i > 0) repeat(gap) { out.add(0) }
            val n = (RATE * ms / 1000.0).roundToInt()
            for (k in 0 until n) {
                val edge = minOf(1.0, k.toDouble() / fade, (n - 1 - k).toDouble() / fade)
                val v = sin(2 * PI * hz * k / RATE) * GAIN * max(0.0, edge)
                out.add(jsRound(v * 32767).toShort())
            }
        }
        return out.toShortArray()
    }

    /** JavaScript's Math.round (halves go up), so both apps make the same numbers. */
    private fun jsRound(x: Double): Int = kotlin.math.floor(x + 0.5).toInt()

    /** The loudest sample, for the test. */
    fun peak(s: ShortArray): Int = s.maxOfOrNull { abs(it.toInt()) } ?: 0
}
