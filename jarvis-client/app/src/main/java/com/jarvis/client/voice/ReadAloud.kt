package com.jarvis.client.voice

/**
 * Read-aloud of a TYPED chat answer (the owner's ask, 2026-10-27): the desktop
 * HUD already reads typed answers aloud under the owner's 2026-10-16 decision,
 * so the phone's silence was a parity gap, not a design choice.
 *
 * WHY THIS IS ITS OWN OBJECT. The voice path already has the never-speak rules
 * ([PrivateAloud]); a typed answer has no `Heard` reply to read them from, so
 * the runtime works the same facts out from the answer's own `X-Jarvis-Route`
 * header plus the tool-run counters it keeps for the voice path, and hands them
 * here. This object is pure: no Android, no JSON, no network - only the decision
 * and the sentences - so [ReadAloudTest] can prove every branch off-device.
 *
 * FAIL CLOSED. Anything unknown is "do not speak": no route, an answer that used
 * saved facts, a private gate, a screen read, a tool that ran, a stream that
 * could not say, a stale link, a locked phone. The refusal words say only that
 * it is on screen - never why, never the answer, never a fact.
 *
 * THE WORDS ARE PENDING THE HUD SLICE. The desktop read-aloud work (Lead's lane,
 * in flight) will send the exact sentence-cap, refusal wording and
 * sensitive-skip rules; until that link lands, [ON_SCREEN]/[LABEL]/[STOP] mirror
 * [PrivateAloud.ON_SCREEN] and the proposed phone wording, marked here so the
 * one place to change is obvious.
 */
object ReadAloud {

    /** The control, beside Copy. */
    const val LABEL = "Read aloud"

    /** The same control while it is speaking. */
    const val STOP = "Stop"

    /** Nothing to read: no finished typed answer is held. */
    const val NOTHING = "There is no answer here to read aloud yet."

    /** A spoken question or answer has the speaker/microphone just now. */
    const val BUSY = "Jarvis is using the microphone or the speaker just now. Try again after this turn."

    /** The PC has no voice engine for this answer. */
    const val NO_ENGINE = "Your PC has no voice for this, so the answer stays on screen."

    /** The clip could not be fetched. */
    const val CANNOT = "That answer could not be read aloud just now."

    /**
     * Refusal words when a privacy rule keeps the answer on screen (pending HUD
     * link). Kept as a literal - never a reference - so this object stays pure
     * Kotlin and its test can run off-device; the wiring test pins that it is
     * exactly `PrivateAloud.ON_SCREEN`'s sentence.
     */
    const val ON_SCREEN = "It's on your screen."

    /** Refusal words when App lock would ask for the fingerprint first. */
    const val LOCKED = "Not now - the phone is locked."

    /** Refusal words when the link is down or stale. */
    const val OFFLINE = "Not connected, so that answer cannot be read aloud just now."

    /**
     * At most this many sentences per answer: every sentence is one round trip
     * to `/api/voice/say`, so a long answer is capped rather than turned into
     * hundreds of requests. One named constant so the HUD read-aloud slice
     * adopts the identical number.
     */
    const val READ_ALOUD_SENTENCE_CAP = 24

    /**
     * The facts the runtime worked out for one finished typed answer. Every
     * field fails closed; [mayRead] is the only decision the UI acts on.
     */
    data class Facts(
        /** The answer carried a readable `X-Jarvis-Route` header at all. */
        val hasRoute: Boolean,
        /** `gate == "private"`: the PC itself kept this answer off the speaker. */
        val privateGate: Boolean,
        /** How many saved facts went into the answer. */
        val injectedFacts: Int,
        /** How many of those are sensitive (fail-closed count from the header). */
        val injectedSensitive: Int,
        /** A tool ran for this turn (the `step` event). */
        val toolRan: Boolean,
        /** Whether the stream could have told us ([PrivateAloud.toolsKnown]). */
        val toolsKnown: Boolean,
        /** The screen or camera was read for this turn. */
        val screenRead: Boolean,
        /** The link is down or stale: nothing new can be fetched. */
        val stale: Boolean,
        /** App lock would ask for the fingerprint now. */
        val locked: Boolean,
    ) {
        /** The one decision: may this answer be spoken? Unknown or private means no. */
        val mayRead: Boolean
            get() = when {
                locked -> false
                stale -> false
                !hasRoute -> false
                injectedSensitive > 0 -> false
                screenRead -> false
                privateGate -> false
                injectedFacts > 0 -> false
                toolRan -> false
                !toolsKnown -> false
                else -> true
            }

        /** What to say when it may not be read aloud; null when it may. */
        val refusal: String?
            get() = when {
                mayRead -> null
                locked -> LOCKED
                stale -> OFFLINE
                else -> ON_SCREEN
            }
    }

    /**
     * One finished typed answer the phone may offer to read: the text to speak
     * and the facts that decide it. Held by the runtime; replaced by the next
     * typed answer and cleared when a new question is sent.
     */
    data class Offer(val text: String, val facts: Facts) {
        val mayRead: Boolean get() = facts.mayRead
        val refusal: String? get() = facts.refusal
    }

    /**
     * The answer split into speakable sentences, capped at [max] (never below
     * one). Blank paragraphs are dropped; a paragraph with no stop punctuation
     * stays one sentence, which is what the voice path does with it too.
     */
    fun sentences(text: String, max: Int = READ_ALOUD_SENTENCE_CAP): List<String> {
        val limit = if (max < 1) 1 else max
        val cleaned = text.replace("\r\n", "\n").replace('\r', '\n').trim()
        if (cleaned.isEmpty()) return emptyList()
        return cleaned
            .split(BREAK)
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .take(limit)
    }

    /** A sentence ends at . ! or ? followed by space, or at a line break. */
    private val BREAK = Regex("(?<=[.!?])\\s+|\\n+")
}
