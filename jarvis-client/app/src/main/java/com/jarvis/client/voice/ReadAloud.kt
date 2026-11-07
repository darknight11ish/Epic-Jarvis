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
 * it is on screen - never why, never the answer, never a fact. The two
 * exceptions are the owner's own taps of 2026-11-06, below.
 *
 * THE WORDS AND THE CAP ARE DECIDED (2026-10-27). [ON_SCREEN] is
 * [PrivateAloud.ON_SCREEN]'s own sentence, [LABEL] and [STOP] are the desktop
 * read-aloud setting's own name and its while-speaking word, and
 * [READ_ALOUD_SENTENCE_CAP] is the one number the HUD read-aloud slice adopts.
 * This object stays the one place to change all four.
 *
 * THE OWNER'S OKAY, FOR ONE ANSWER AT A TIME (2026-11-06). He reported on
 * 2026-11-06 that his phone still refused to read two things he is happy to
 * hear - answers refused with "It's on your screen." and answers that used
 * what Jarvis remembers: "it's okay to read these ones out loud". Two narrow
 * doors, both his own tap on his own unlocked phone, neither a new default and
 * neither a new route:
 *
 *  1. the PHONE'S OWN SETTING of 2026-11-05 ([Facts.phoneMemoryAloud],
 *     `MemoryAloud`) now covers a TYPED answer too. When it is ON and the ONLY
 *     rule keeping the answer back is remembered NON-sensitive facts, "Read
 *     aloud" speaks it. The runtime still asks the live lock before every
 *     sentence, so a phone that locked since the answer arrived says nothing.
 *     Sensitive facts, a private question, the router's private gate, a private
 *     tool, a stale link and a locked phone are untouched (the 2026-09-24 rule
 *     is not loosened anywhere).
 *
 *  2. a ONE-OFF "Read it aloud anyway" ([ANYWAY]) is drawn on the refusal strip
 *     only when the ONLY blockers are remembered non-sensitive facts ([Why.MEMORY])
 *     or a screen read ([Why.SCREEN]), and only while the phone is unlocked.
 *     It reads that one answer once, on that tap. It is not a setting, not a
 *     standing grant, and nothing about it is stored afterwards - pressing it
 *     again is a second tap by the owner, never a remembered permission. It is
 *     never drawn for a sensitive fact, a private tool, a stale link or a
 *     locked phone.
 *
 * A refusal the owner can fix in Settings may NAME the switch (the memory
 * sentence together with [MEMORY_SWITCH_HINT], the same sentence the voice path
 * says) - and never says any more than that, never quotes the answer and never
 * quotes a fact.
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
     * Refusal words when a privacy rule keeps the answer on screen. Kept as a
     * literal - never a reference - so this object stays pure Kotlin and its
     * test can run off-device; the wiring test pins that it is exactly
     * `PrivateAloud.ON_SCREEN`'s sentence.
     */
    const val ON_SCREEN = "It's on your screen."

    /**
     * What the strip says when the ONLY rule keeping the answer back is the
     * remembered-facts one: the SAME sentence the voice path says since
     * 2026-11-05 ([PrivateAloud.MEMORY_ON_SCREEN]), kept as its own literal for
     * the same off-device reason as [ON_SCREEN] (pinned by the wiring test).
     *
     * The owner's report of 2026-11-06 was about hearing the bare "It's on your
     * screen." for an answer he could hear: a typed memory answer used to draw
     * [ON_SCREEN], which says nothing about why. It now says what happened, and
     * (when the phone setting is OFF) names the switch that fixes it.
     */
    const val MEMORY_ON_SCREEN = "That answer used things I remember, so it's on your screen."

    /**
     * Names the phone's own switch, and nothing more: the words on its button
     * ("Read them out") and where it lives. The same sentence as
     * [PrivateAloud.MEMORY_SWITCH_HINT], pinned by the wiring test. Never a
     * reason beyond the one the previous sentence already gives, never the
     * answer, never a fact.
     */
    const val MEMORY_SWITCH_HINT = "To hear these every time, turn on \"Read them out\" in Voice settings."

    /**
     * The one-off control drawn on the refusal strip (the owner's decision of
     * 2026-11-06). It reads THIS answer once, on his tap. See [Facts.oneOffAt]
     * for where it may be drawn at all, and its own doc for what it is not.
     */
    const val ANYWAY = "Read it aloud anyway"

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
     * Every rule that can keep a typed answer on screen, in the order they are
     * asked. [NONE] is the only value that is not a blocker; the rest are the
     * same ladder [PrivateAloud] holds for the voice path, with this path's own
     * two hard extra facts (a stale link, a locked phone) FIRST because they are
     * facts, not owner choices.
     */
    enum class Why {
        /** Nothing keeps it back. */
        NONE,

        /** App lock would ask for the fingerprint, or the phone is locked. */
        LOCKED,

        /** The link is down or stale, so nothing can be fetched. */
        OFFLINE,

        /** No `X-Jarvis-Route` header has arrived: nothing is known. */
        NO_ROUTE,

        /** A sensitive saved fact went into it and the owner did not allow those. */
        SENSITIVE,

        /** The screen or camera was read for this turn. */
        SCREEN,

        /** The router's own `gate: "private"`. */
        PRIVATE_GATE,

        /** It used remembered NON-sensitive facts, and those are kept on screen. */
        MEMORY,

        /** A PRIVATE tool ran while it was written. */
        TOOL,

        /** The event stream could not say whether a tool ran. */
        TOOLS_UNKNOWN,
    }

    /**
     * The facts the runtime worked out for one finished typed answer. Every
     * field fails closed; [blockers] is the whole rule, [mayRead] is the only
     * decision the UI acts on, and [oneOffAt] is the owner's one-off.
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
        /** App lock would ask for the fingerprint now (a snapshot, re-asked at the tap). */
        val locked: Boolean,
        /**
         * The phone's OWN setting of 2026-11-05 ("Read out answers that use
         * what Jarvis remembers", `data/ClientSettings.readMemoriesAloud`,
         * [PrivateAloud.MEMORY_ALOUD_DEFAULT]): OFF unless the owner turned it
         * on. It is consulted here so a TYPED answer gets the same door the
         * talk button got - and it lifts ONLY [Why.MEMORY], never a sensitive
         * fact, a screen read, a tool, a stale link or a lock.
         */
        val phoneMemoryAloud: Boolean = false,
    ) {
        /**
         * Every rule that says no, in the ladder's order. Empty means it may be
         * read. This is the ONE list: the words, the decision and the one-off
         * are all read from it, so they cannot drift apart.
         *
         * The order is the voice path's ([PrivateAloud.refusal]) with the two
         * facts a typed answer carries of its own first: a locked phone and a
         * stale link are not owner choices and are never overridable.
         */
        val blockers: List<Why>
            get() = buildList {
                if (locked) add(Why.LOCKED)
                if (stale) add(Why.OFFLINE)
                if (!hasRoute) add(Why.NO_ROUTE)
                if (injectedSensitive > 0) add(Why.SENSITIVE)
                if (screenRead) add(Why.SCREEN)
                if (privateGate) add(Why.PRIVATE_GATE)
                if (injectedFacts > 0) add(Why.MEMORY)
                if (toolRan) add(Why.TOOL)
                if (!toolsKnown) add(Why.TOOLS_UNKNOWN)
            }

        /** The first rule that says no, or [Why.NONE]. */
        val why: Why
            get() = blockers.firstOrNull() ?: Why.NONE

        /**
         * The one decision: may this answer be spoken? Unknown or private means
         * no. The phone's own memory setting lifts [Why.MEMORY] and nothing
         * else - and only when that rule is the ONLY one left, so a private tool
         * that also ran still refuses.
         */
        val mayRead: Boolean
            get() = blockers.isEmpty() ||
                (phoneMemoryAloud && blockers == listOf(Why.MEMORY))

        /** What to say when it may not be read aloud; null when it may. */
        val refusal: String?
            get() = when {
                mayRead -> null
                why == Why.LOCKED -> LOCKED
                why == Why.OFFLINE -> OFFLINE
                else -> ON_SCREEN
            }

        /**
         * The ONE sentence to SHOW beside the answer when a read is withheld for
         * privacy; null when it may be read, and null when the reason is not
         * privacy (locked, offline - those are not what "It's on your screen."
         * says, and this project shows no invented sentence).
         *
         * A control that is not drawn at all is silent about why, and a control
         * that does nothing when pressed is worse (the Lead's ruling of
         * 2026-10-27: show the one sentence, and nothing beyond it). The phone
         * therefore draws this sentence where the Read aloud control would have
         * been.
         *
         * When the ONLY reason is the remembered-facts rule it says what happened
         * ([MEMORY_ON_SCREEN]), and names the switch that fixes it
         * ([MEMORY_SWITCH_HINT]) while that switch is OFF - the owner's own
         * report of 2026-11-06 was the bare "It's on your screen." about an
         * answer he expected to hear. Nothing else ever gets a second sentence.
         */
        val withheld: String?
            get() = when {
                mayRead -> null
                why == Why.LOCKED || why == Why.OFFLINE -> null
                blockers == listOf(Why.MEMORY) ->
                    if (phoneMemoryAloud) MEMORY_ON_SCREEN else "$MEMORY_ON_SCREEN $MEMORY_SWITCH_HINT"
                else -> ON_SCREEN
            }

        /**
         * May the one-off "Read it aloud anyway" action be drawn and act, on a
         * phone unlocked at THIS tap (the owner's decision of 2026-11-06)?
         *
         * ONLY when the only blockers are remembered non-sensitive facts or a
         * screen read - [blockers] must be exactly one of those, so an answer
         * that ALSO used a sensitive fact, ran a private tool, hit the private
         * gate, has no route, is stale or is locked offers nothing. The screen
         * case has no per-answer `screen_aloud` on this path (a typed answer has
         * no utterance reply; the desktop HUD's typed speaker passes none
         * either), so this one-off is its only door - the voice path keeps the
         * PC's own `hands_free_screen` rule untouched.
         */
        fun oneOffAt(unlockedNow: Boolean): Boolean =
            unlockedNow && !mayRead &&
                (blockers == listOf(Why.MEMORY) || blockers == listOf(Why.SCREEN))
    }

    /**
     * One finished typed answer the phone may offer to read: the text to speak
     * and the facts that decide it. Held by the runtime; replaced by the next
     * typed answer and cleared when a new question is sent.
     */
    data class Offer(val text: String, val facts: Facts) {
        val mayRead: Boolean get() = facts.mayRead
        val refusal: String? get() = facts.refusal

        /** See [Facts.withheld]: the one sentence to show when the read is withheld. */
        val withheld: String? get() = facts.withheld

        /**
         * The one-off action's words, or null when it must not be drawn: only
         * on a refusal that is ONLY remembered facts or ONLY a screen read, and
         * only while the phone is unlocked at this tap (the owner's decision of
         * 2026-11-06). Nothing is stored: the tap reads the answer once.
         */
        fun oneOffLabel(unlockedNow: Boolean): String? =
            if (facts.oneOffAt(unlockedNow)) ANYWAY else null
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
