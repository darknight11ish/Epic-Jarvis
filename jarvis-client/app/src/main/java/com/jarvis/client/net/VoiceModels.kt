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
     * refusing ones" two lines up, and it does not: a desktop older than
     * 2026-09-23 **omits this key** when the module is healthy (the one in
     * this repository's `backend/jarvis_speech.py` now sends `true`).
     * Defaulting it to false would make `canPushToTalk` false on every good
     * response from those and hide the microphone button permanently. The
     * refusal is carried by `listening.pushToTalk`, which does default to
     * false.
     *
     * Until 2026-09-23 `jarvis_speech.status()` sent none of the nested keys
     * below - only flat ones - so `listening.pushToTalk` was always missing
     * and the talk button never appeared. It now sends both shapes, and
     * `backend/test_voice_contract.py` checks them against this file.
     */
    val available: Boolean = true,
    val error: String? = null,
    val listening: VoiceListening = VoiceListening(),
    val stt: VoiceEngine = VoiceEngine(),
    val tts: VoiceEngine = VoiceEngine(),
    @SerialName("audio_in") val audioIn: VoiceAudioIn = VoiceAudioIn(),
    /**
     * The owner-voice check: whether Jarvis knows the owner's voice yet, and
     * with which check. Read by "Train my voice" on the Checks screen. The
     * defaults say "not trained" - the refusing answer.
     */
    val gate: VoiceGate = VoiceGate(),
    /**
     * "Hey Jarvis" on the desktop: the switch (turned on only by approving a
     * card), a card waiting, and whether the PC itself can hear the phrase.
     * Defaults say "off, no card". Read by the Checks screen's wake-word card
     * and by the phone's own listener (its threshold).
     */
    val wake: VoiceWake = VoiceWake(),
    /**
     * Smart Turn ("finished, or only paused?"): the owner's switch and the
     * bar, from the PC so both listeners follow one setting. The phone runs
     * its own copy of the model; [VoiceTurn.available] is only about the PC's.
     * Defaults: on, at the model's own 0.5 - a PC from before 2026-09-24
     * does not send this, and the phone's copy works without it.
     */
    val turn: VoiceTurn = VoiceTurn(),
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
    /**
     * Why [pushToTalk] is false, in the desktop's own plain words - "Jarvis
     * has not learned your voice yet", "the PC has no speech-to-text set up".
     * Blank when it is true. Shown on the Checks screen's voice card, so a
     * missing talk button has a reason somewhere.
     */
    @SerialName("push_to_talk_why") val pushToTalkWhy: String = "",
    @SerialName("wake_word") val wakeWord: Boolean = false,
    @SerialName("wake_word_why") val wakeWordWhy: String = "",
    /**
     * A card to turn the wake word ON is waiting for the owner. Asking for it
     * does not turn it on; approving the card does. False on a desktop from
     * before 2026-09-23.
     */
    @SerialName("wake_word_pending") val wakeWordPending: Boolean = false,
)

/** `/api/voice/status` -> `wake`. See [VoiceStatus.wake]. */
@Serializable
data class VoiceWake(
    val enabled: Boolean = false,
    val pending: Boolean = false,
    /** openWakeWord's model name, "hey_jarvis". */
    val phrase: String = "hey_jarvis",
    /** The spotter's bar, 0..1. The phone uses the desktop's so one number means one thing. */
    val threshold: Double = 0.5,
    /** After "hey Jarvis." on its own, how long the desktop waits for the next sentence. */
    @SerialName("awake_seconds") val awakeSeconds: Double = 8.0,
    /** Whether the PC can hear "hey Jarvis" in a clip (it checks every one the phone sends). */
    val spotter: VoiceSpotter = VoiceSpotter(),
)

/** `/api/voice/status` -> `turn`. See [VoiceStatus.turn]. */
@Serializable
data class VoiceTurn(
    /** `[voice] turn_enabled` on the PC. False: the old fixed one-second pause. */
    val enabled: Boolean = true,
    /** Whether the PC has the model (the desktop app asks it; the phone has its own). */
    val available: Boolean = false,
    /** "Finished" at or above this probability. */
    val threshold: Double = 0.5,
    /** Quiet this long after speech, and the model is asked. */
    @SerialName("ask_after_ms") val askAfterMs: Int = 200,
    /** The longest pause kept inside a sentence the model called unfinished. */
    @SerialName("max_pause_ms") val maxPauseMs: Int = 2000,
    val why: String = "",
)

@Serializable
data class VoiceSpotter(
    val available: Boolean = false,
    val engine: String = "",
    /** Why [available] is false, in the desktop's words. */
    val why: String = "",
)

/**
 * The owner-voice check on the desktop (`jarvis_voice.status()`, nested under
 * `gate` by `jarvis_speech.status()`).
 *
 * `backend/test_voice_contract.py` reads this file and fails if the desktop
 * stops sending any field here, so a rename on either side is caught there
 * rather than showing up as a card that quietly says "not trained".
 */
@Serializable
data class VoiceGate(
    /** "owner": only the trained voice is obeyed. "broad": anyone is. */
    val mode: String = "owner",
    val enabled: Boolean = false,
    /** Whether a voice print exists. False means every voice is refused in owner mode. */
    val enrolled: Boolean = false,
    /** How many clips the voice print was made from. */
    val samples: Int = 0,
    val threshold: Double = 0.0,
    /** "spectral-v1" (the basic check), "ecapa", or "sherpa-onnx:…". Shown, never branched on. */
    val embedder: String = "",
    /**
     * True when a real speaker model is installed on the PC. False means the
     * basic check, which cannot reliably tell two people apart.
     */
    @SerialName("speaker_model") val speakerModel: Boolean = false,
    /**
     * The voice print was made with a different check than the one installed
     * now, so it will be refused until the owner trains again. Happens once,
     * the day the better model is installed.
     */
    @SerialName("needs_retraining") val needsRetraining: Boolean = false,
    val note: String = "",
    val training: VoiceTrainingState = VoiceTrainingState(),
    /**
     * One voice print per microphone (since 2026-09-24): the phone's, the
     * PC's, and "general" - the single print every training before then
     * made. A clip is checked against its own microphone's print first.
     * All untrained on a PC that does not send this.
     */
    val prints: VoicePrints = VoicePrints(),
)

/** `gate.prints`. See [VoiceGate.prints]. */
@Serializable
data class VoicePrints(
    val phone: VoicePrint = VoicePrint(),
    val desktop: VoicePrint = VoicePrint(),
    /** The old single print (owner.json). Replaced the next time the phone trains. */
    val general: VoicePrint = VoicePrint(),
)

@Serializable
data class VoicePrint(
    val trained: Boolean = false,
    val samples: Int = 0,
    /** How close a voice must be to pass, 0..1. */
    val threshold: Double = 0.0,
    val created: Double = 0.0,
    @SerialName("needs_retraining") val needsRetraining: Boolean = false,
)

/** "Train my voice" on the desktop side: whether a card is waiting, and how the last one ended. */
@Serializable
data class VoiceTrainingState(
    /** False when the desktop does not have voice training installed at all. */
    val available: Boolean = false,
    /** A training card is waiting for the owner's answer. */
    val pending: Boolean = false,
    /** How many clips the waiting card is about. Present only while [pending]. */
    val clips: Int = 0,
    /** Seconds until the waiting card expires. Present only while [pending]. */
    @SerialName("expires_in") val expiresIn: Int = 0,
    /** How the last training ended, since the desktop started. Null if none has. */
    val last: VoiceTrainingLast? = null,
    /** Why [available] is false. */
    val why: String = "",
    /**
     * The PC understands the "someone else" check and the threshold card
     * (`mode: calibrate` / `mode: threshold`, 2026-09-24). **The phone must
     * not send either without this**: an older PC reads any body with
     * clips in it as a training, and would raise a card to replace the
     * owner's voice with the other person's.
     */
    val calibrate: Boolean = false,
)

@Serializable
data class VoiceTrainingLast(
    /** "enrolled", "denied", "timed_out", "refused" or "failed". */
    val outcome: String = "",
    val at: Double = 0.0,
    val samples: Int = 0,
    val reason: String = "",
    /**
     * The "hey Jarvis" check built from the same clips, in the PC's words:
     * "built from 4 "hey Jarvis" sentences" or "not built: ...". Blank from
     * a PC older than 2026-09-24, or for an outcome that trained nothing.
     */
    @SerialName("wake_check") val wakeCheck: String = "",
    /** "threshold_set" outcomes: the new bar. */
    val threshold: Double = 0.0,
)

/**
 * The answer to `POST /api/voice/enroll`. A 202 carries `ok`/`pending`; a
 * refusal (400 bad clip, 409 already waiting or wrong tier, 503 not
 * installed) carries `error`, a sentence meant for the owner.
 */
/**
 * The body of `POST /api/voice/enroll`: `{"clips": ["<base64 WAV>", ...]}`.
 *
 * JSON with base64 rather than one raw WAV like `/api/voice/utterance`,
 * because this carries several clips and each needs its own boundary; the
 * desktop names a bad one by its number ("clip 3 is too short"). Built by
 * hand rather than through a serializer: base64 never contains a character
 * JSON needs escaped, so there is nothing to get wrong, and a multi-megabyte
 * string is not copied through a JSON tree on the way.
 *
 * java.util.Base64 rather than android.util.Base64, so the unit test runs on
 * a plain JVM; it has been on Android since API 26 and minSdk is 33.
 */
fun enrollRequestBody(clips: List<ByteArray>, mic: String? = null, mode: String? = null): String {
    val enc = java.util.Base64.getEncoder()
    // `mode` and `mic` are fixed words from this app (never user text), so
    // they need no escaping either. Absent, the PC reads "enrol" and "no
    // microphone named" - which is what a PC older than 2026-09-24 does anyway.
    val head = buildString {
        append("{")
        if (mode != null) append("\"mode\":\"").append(mode).append("\",")
        if (mic != null) append("\"mic\":\"").append(mic).append("\",")
        append("\"clips\":[")
    }
    return clips.joinToString(prefix = head, postfix = "]}", separator = ",") {
        "\"" + enc.encodeToString(it) + "\""
    }
}

/** `{"mode": "threshold", "mic": ..., "threshold": 0.52}` - asks for a card; changes nothing itself. */
fun thresholdRequestBody(value: Double, mic: String): String =
    "{\"mode\":\"threshold\",\"mic\":\"$mic\",\"threshold\":" +
        String.format(java.util.Locale.US, "%.2f", value) + "}"

/**
 * The PC's answer to the "someone else" check (`mode: calibrate`): how
 * each of the other person's clips scored against the owner's print, how
 * the owner's own training clips scored, and - only when the two are
 * clearly apart - a stricter bar to propose. Nothing changed on the PC.
 */
@Serializable
data class VoiceCalibration(
    val ok: Boolean = false,
    /** One per clip; null where a clip was too short to score. */
    val scores: List<Double?> = emptyList(),
    /** The bar in use now. */
    val threshold: Double = 0.0,
    /** The owner's own lowest training score. */
    @SerialName("owner_low") val ownerLow: Double = 0.0,
    /** The other person's highest score. */
    @SerialName("others_high") val othersHigh: Double = 0.0,
    /** True when every one of the owner's clips beat every one of theirs. */
    val separated: Boolean = false,
    /** The bar to propose, or null when there is no safe one. */
    val suggested: Double? = null,
    /** The PC's own plain sentence about the result. */
    val message: String = "",
    val error: String = "",
)

@Serializable
data class VoiceTrainingReply(
    val ok: Boolean = false,
    val pending: Boolean = false,
    val clips: Int = 0,
    val seconds: Double = 0.0,
    val message: String = "",
    val error: String = "",
    @SerialName("expires_in") val expiresIn: Int = 0,
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
    /**
     * False when the desktop could not do this at all (no speech engine; for
     * a wake-word clip, the wake word switched off or its model missing).
     * Defaults to true, like the desktop's own `voice.rs`, so an older desktop
     * that omits it is not read as broken.
     */
    val available: Boolean = true,
    /** `source=wake_word` only: "hey Jarvis" was heard in the clip, from the owner. */
    @SerialName("wake_heard") val wakeHeard: Boolean = false,
    /** The clip was "hey Jarvis" and nothing else: send the next sentence. */
    val awake: Boolean = false,
    @SerialName("awake_seconds") val awakeSeconds: Float = 0f,
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
