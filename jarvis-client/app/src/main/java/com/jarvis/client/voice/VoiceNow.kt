package com.jarvis.client.voice

import com.jarvis.client.net.CustomVoices

/**
 * Which voice Jarvis Live is speaking in on this phone, and the one line that
 * says so. No Android in this file, so [VoiceNowTest] runs it.
 *
 * WHY THIS EXISTS (2026-10-28). The owner reported: *"when i change the jarvis
 * voice in the android app it still stays the same in jarvis live in the
 * android app"*. Live is not a second voice path on the phone - every reply,
 * Live's included, asks the PC's `/api/voice/say` for its sound
 * ([VoiceSession.speakStreamed] -> `api.say`), so Live already speaks in the
 * PC's built-in voice. What the phone never did was SAY which voice that was,
 * so a voice that did not change sounded like a Live fault rather than a
 * setting fault. The one real exception is the PC having no voice engine at
 * all: then `/api/voice/say` answers 503, the PC says the phone may speak
 * instead (`client_fallback_ok`), and Live speaks in the phone's own offline
 * voice - which no setting on the PC can change. That is said plainly rather
 * than shown as the PC's voice.
 *
 * The name shown here is the same `CustomVoices.Speaker` row the Voices screen
 * shows, from the same `GET /api/voice/voices` read, so the two screens cannot
 * name different voices.
 */
object VoiceNow {

    /** Where the sound of the last spoken reply came from. */
    enum class Source {
        /** The PC's voice (`/api/voice/say` answered a WAV). */
        PC,

        /** This phone's own offline voice - the PC had no engine to speak with. */
        PHONE,

        /** Nothing spoken yet on this screen, so there is nothing to claim. */
        NONE,
    }

    /**
     * The event that makes the phone read the PC's voice again, whatever screen
     * is open (the PC rings it for a picker change, a personality that applies
     * its voice, and a speed change). One list, so the runtime and this test
     * cannot disagree about which doorbell it is.
     */
    const val RELOAD_EVENT = "voices"

    /** True when an event kind means "read the PC's voice again". */
    fun rereadOn(kind: String): Boolean = kind == RELOAD_EVENT

    /** The chosen built-in voice's word on screen ("American (female) - Bella"), or null. */
    fun label(status: CustomVoices.Status?): String? {
        val sk = status?.speaker ?: return null
        val choice = sk.choice.trim()
        if (choice.isEmpty()) return null
        return sk.choices.firstOrNull { it.id == choice }?.label?.trim()
            ?.takeIf { it.isNotEmpty() }
            ?: choice
    }

    const val PC_LINE = "Voice: Jarvis's own on your PC"
    const val PHONE_LINE =
        "Voice: this phone's own - your PC has no voice to speak with, so Live " +
            "speaks with the phone's, and changing it on your PC changes nothing here."

    /**
     * The one line under the Live controls, or null when there is nothing
     * honest to say (nothing has been spoken here yet).
     *
     * A reply from the PC names the voice the Voices screen names, so a change
     * made in either app is visible here as well as heard. A reply from the
     * phone says so, and says why, because no PC setting can change it.
     */
    fun line(status: CustomVoices.Status?, source: Source): String? = when (source) {
        Source.NONE -> null
        Source.PHONE -> PHONE_LINE
        Source.PC -> label(status)?.let { "Voice: $it, from your PC" } ?: PC_LINE
    }

    /**
     * The source a `SaidAloud` answer means: the PC's sound, the phone's own
     * voice, or nothing spoken. Kept here rather than in [VoiceSession] so the
     * decision is testable without Android's `TextToSpeech`.
     *
     * [spoke]: whether the phone's own voice really made a sound (`Speaker
     * .speakOnDevice` returns false when it was stopped or had no offline
     * voice), so a refusal is never reported as "the phone's voice".
     */
    fun sourceOf(saidOnPc: Boolean, fallbackAllowed: Boolean, spoke: Boolean): Source = when {
        saidOnPc -> Source.PC
        fallbackAllowed && spoke -> Source.PHONE
        else -> Source.NONE
    }
}
