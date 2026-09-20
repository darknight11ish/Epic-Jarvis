package com.jarvis.client.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * What the voice path can do on this desktop — and what this client may not do
 * itself.
 *
 * Read before offering a microphone button at all, per §4.1. Every field is
 * defaulted, and the defaults are the *refusing* ones: a status call that fails
 * leaves push-to-talk off rather than on.
 */
@Serializable
data class VoiceStatus(
    /**
     * Present and false only when the module failed to load on the desktop.
     *
     * Defaulting this to `true` looks like it contradicts "the defaults are the
     * refusing ones" two lines up, and it does not: `jarvis_speech.status()`
     * **omits this key entirely** when the module is healthy — the real payload
     * is `{listening, stt, tts, audio_in, gate}` and nothing else. Defaulting
     * it to false would make `canPushToTalk` false on every good response and
     * hide the microphone button permanently. The refusal is carried by
     * `listening.pushToTalk`, which does default to false.
     */
    val available: Boolean = true,
    val error: String? = null,
    val listening: VoiceListening = VoiceListening(),
    val stt: VoiceEngine = VoiceEngine(),
    val tts: VoiceEngine = VoiceEngine(),
    @SerialName("audio_in") val audioIn: VoiceAudioIn = VoiceAudioIn(),
) {
    /**
     * Whether to show a microphone button.
     *
     * Hidden rather than shown-and-failing: §2's rule is that a capability
     * reporting false means hide the UI, not offer a button that 404s.
     */
    val canPushToTalk: Boolean get() = available && listening.pushToTalk

    /**
     * Whether the wake word may be *used*. Built either way — it is a trigger
     * on this side, not a second protocol — but never assumed.
     */
    val wakeWordOn: Boolean get() = available && listening.wakeWord

    /**
     * True when the desktop said it has no engine to transcribe with.
     *
     * **Nothing reads this yet** — the sentence it was written for was never
     * put on the screen. It is kept because the intention is right, and made
     * evidence-based so that wiring it up later cannot produce a fabricated
     * claim: `stt.status` is blank unless the desktop actually described an
     * engine, so a `{}` or an unrecognised payload now reports nothing rather
     * than "there is no speech-to-text engine installed" about a desktop that
     * said no such thing.
     */
    val sttMissing: Boolean get() = available && stt.status.isNotBlank() && !stt.available
}

/**
 * What the wake word is doing, as three states rather than a boolean.
 *
 * The third one is the point. `VoiceStatus`'s defaults are the refusing ones,
 * so a status call that never reached the desktop looks exactly like a desktop
 * reporting the wake word off — and those must not be shown the same way.
 * "Off, nothing is listening" is a promise about a microphone; saying it when
 * the truth is "I could not ask" is the worst thing this screen could do.
 */
enum class WakeWord {
    /** The desktop confirms it will accept wake-word audio. */
    ON,

    /** The desktop confirms it will not. */
    OFF,

    /** No successful answer yet. Not the same as off, and never shown as off. */
    UNKNOWN,
    ;

    companion object {
        /**
         * @param answered whether `/api/voice/status` has ever succeeded for
         *   the current desktop. A failed call leaves the last known status in
         *   place on purpose; this is what says whether to trust it.
         */
        fun of(answered: Boolean, status: VoiceStatus): WakeWord = when {
            !answered -> UNKNOWN
            // `available` false means the voice module did not load at all, so
            // there is nothing on that side that could be listening. That is a
            // real "off" rather than an unknown.
            status.wakeWordOn -> ON
            else -> OFF
        }
    }
}

@Serializable
data class VoiceListening(
    @SerialName("push_to_talk") val pushToTalk: Boolean = false,
    @SerialName("wake_word") val wakeWord: Boolean = false,
    @SerialName("wake_word_why") val wakeWordWhy: String = "",
)

@Serializable
data class VoiceEngine(
    val engine: String = "none",
    val available: Boolean = false,
    val status: String = "",
    /** Only meaningful on `tts`: whether the client may speak with its own voice. */
    @SerialName("client_fallback_ok") val clientFallbackOk: Boolean = false,
)

@Serializable
data class VoiceAudioIn(
    val format: String = "WAV, 16-bit mono PCM",
    @SerialName("sample_rate") val sampleRate: Int = 16_000,
    @SerialName("max_seconds") val maxSeconds: Double = 30.0,
    /**
     * **False, and this client must honour it.**
     *
     * The owner voice-print gate can only check a voice if it is given the
     * voice. Transcribing here would send text, the gate would have nothing to
     * examine, and "is this the owner?" would quietly become "is this someone
     * holding the owner's phone?". Android's own recogniser is also a network
     * service unless on-device recognition happens to be installed, so the
     * privacy boundary would move without anyone being told.
     *
     * The field exists so this is checkable rather than merely written down.
     * `VoiceRulesTest` asserts on it.
     */
    @SerialName("client_stt_allowed") val clientSttAllowed: Boolean = false,
    val why: String = "",
)

/**
 * One utterance's verdict.
 *
 * Three outcomes, and they are not the same thing — see [outcome]. All three
 * arrive as **HTTP 200**, including the refusal, because a voice that did not
 * match is a normal answer rather than a transport error.
 */
@Serializable
data class Heard(
    val ok: Boolean = false,
    val owner: Boolean = false,
    val text: String = "",
    val score: Float = 0f,
    val threshold: Float = 0f,
    val mode: String = "owner",
    val reason: String = "",
    val seconds: Float = 0f,
    val engine: String = "",
) {
    enum class Outcome {
        /** Verified, transcribed. Feed [text] to the chat. */
        TRANSCRIBED,

        /**
         * Not the owner's voice. Never retried, never surfaced as a network
         * error — and there is no transcript, because a voice that is not his
         * is never turned into words.
         */
        NOT_THE_OWNER,

        /**
         * It *was* him, and there is no speech engine on the desktop. Its own
         * case: an empty transcript would read downstream as silence, and
         * acting on silence is acting on nothing.
         */
        NO_ENGINE,

        /** Unusable audio, too short, or silence. [reason] says which. */
        REFUSED,
    }

    val outcome: Outcome
        get() = when {
            ok && owner -> Outcome.TRANSCRIBED

            // owner:true with ok:false can only mean the gate recognised him
            // and there was nothing to transcribe with.
            owner -> Outcome.NO_ENGINE

            // `owner:false` covers TWO different things, and conflating them
            // tells people the wrong story. jarvis_speech.hear() refuses in
            // order: unusable audio, then too short or silent, then the voice
            // gate. The first two never reach the gate, so they come back with
            // score and threshold at zero. Only a refusal that actually ran the
            // gate has a threshold to compare against — and only that one is
            // "that didn't sound like you". A 50ms cough is not a stranger.
            threshold > 0f -> Outcome.NOT_THE_OWNER

            else -> Outcome.REFUSED
        }

    /** What to put on screen. Plain, and never a retry prompt for a refusal. */
    fun message(): String = when (outcome) {
        Outcome.TRANSCRIBED -> text
        Outcome.NOT_THE_OWNER -> "That didn't sound like you."
        Outcome.NO_ENGINE ->
            "That was you, but the desktop has no speech-to-text engine installed."
        // The server's own words: "too short to identify a voice (0.09s)",
        // "silence", "need 16000Hz". All of them are safe to show and all of
        // them tell the owner something they can act on.
        Outcome.REFUSED -> reason.ifBlank { "Didn't catch that." }
    }
}
