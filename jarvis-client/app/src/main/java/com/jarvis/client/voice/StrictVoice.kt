package com.jarvis.client.voice

import com.jarvis.client.net.Approvals
import com.jarvis.client.net.VoiceStrict
import java.util.Locale
import kotlin.math.roundToInt

/**
 * The voice check's two settings, the guided repeat test and the "how often
 * did I have to say it again" numbers - the words and the rules, with no
 * Android in them (`StrictVoiceTest`).
 *
 * THE TWO SETTINGS (docs/JARVIS-API.md section 16, the owner's decisions).
 *
 * - How strict: VERY STRICT (the default) or BALANCED. Very strict turns
 *   other people away more reliably and asks for a little more speech;
 *   balanced asks the owner to repeat less.
 * - Private answers: STAY ON SCREEN (the default) or VOICE CHECK IS ENOUGH -
 *   read an answer from email, the calendar or notes aloud when the voice
 *   passed. The second is only offered while the check is very strict;
 *   choosing balanced puts private answers back on screen.
 * - What Jarvis remembers (added 2026-09-24, the owner's choice: "looser
 *   now, with a setting to make it more strict"): answers that use it are
 *   READ ALOUD by default, or KEPT ON SCREEN. Offered only when the PC
 *   reports the setting.
 *
 * The same shape as every other switch that widens what Jarvis does:
 * LOOSENING (balanced, voice is enough) raises one approval card on the PC
 * and changes nothing until it is approved - so it is held on a stale link
 * (rule 4). TIGHTENING applies at once and always goes: it only narrows.
 */
object StrictVoice {

    /** One choice on the settings screen. */
    data class Choice(val value: String, val label: String, val detail: String)

    val STRICTNESS: List<Choice> = listOf(
        Choice(
            VoiceStrict.VERY_STRICT,
            "Very strict (recommended)",
            "Better at turning other people away. You may have to say things again now and " +
                "then, and a command needs about two seconds of speech.",
        ),
        Choice(
            VoiceStrict.BALANCED,
            "Balanced",
            "You repeat yourself less, but a voice close to yours gets through more easily. " +
                "Private answers then always stay on screen.",
        ),
    )

    val PRIVACY: List<Choice> = listOf(
        Choice(
            VoiceStrict.PRIVATE_ON_SCREEN,
            "Private answers stay on screen (recommended)",
            "When you ask by voice, answers from your email, calendar or notes are shown, " +
                "not read aloud.",
        ),
        Choice(
            VoiceStrict.VOICE_IS_ENOUGH,
            "Voice check is enough",
            "Jarvis reads those answers aloud when your voice passes the very strict check. " +
                "Anyone near the speaker will hear them.",
        ),
    )

    val MEMORY: List<Choice> = listOf(
        Choice(
            VoiceStrict.MEMORY_ALOUD,
            "Read aloud (recommended)",
            "When you ask by voice, answers that use what Jarvis remembers about you are read " +
                "aloud. Anyone near the speaker will hear them. Questions about email, your " +
                "calendar, notes, health or money still stay on screen.",
        ),
        Choice(
            VoiceStrict.MEMORY_ON_SCREEN,
            "Keep on screen",
            "Those answers are shown, not read aloud, like email and notes.",
        ),
    )

    const val MEMORY_TITLE = "Answers that use what Jarvis remembers"

    const val PRIVACY_ONLY_VERY_STRICT =
        "Only while the voice check is very strict."

    const val NOT_ON_THIS_PC =
        "Your PC does not have these settings yet. Run the patch script on the PC first."

    /** The label for [value], in the same words as the choices above. */
    fun label(setting: String, value: String): String {
        val list = when (setting) {
            VoiceStrict.STRICTNESS -> STRICTNESS
            VoiceStrict.MEMORY -> MEMORY
            else -> PRIVACY
        }
        return list.firstOrNull { it.value == value }?.label?.removeSuffix(" (recommended)") ?: value
    }

    /** What is set now, as one line, or null when the PC has not said. */
    fun nowLine(view: VoiceStrict.View): String? {
        if (!view.settings || view.strictness.isBlank()) return null
        val how = label(VoiceStrict.STRICTNESS, view.strictness)
        val priv = if (view.privacy == VoiceStrict.VOICE_IS_ENOUGH) {
            "private answers may be read aloud"
        } else {
            "private answers stay on screen"
        }
        // "Voice check is enough" already reads every private answer aloud.
        val mem = if (view.privacy == VoiceStrict.VOICE_IS_ENOUGH) "" else when (view.memory) {
            VoiceStrict.MEMORY_ALOUD -> "; answers using what Jarvis remembers are read aloud"
            VoiceStrict.MEMORY_ON_SCREEN -> "; answers using what Jarvis remembers stay on screen"
            else -> ""
        }
        return "Voice check: $how; $priv$mem."
    }

    /**
     * Whether [value] can be chosen for [setting] right now, or why not.
     * Null means send it.
     *
     * The link is only asked about for LOOSENING: that one raises a card, and
     * a card raised against a stream this phone cannot confirm is live is what
     * rule 4 is about. Tightening always goes - like the wake word's OFF.
     */
    fun blocker(setting: String, value: String, view: VoiceStrict.View, linkBlocker: String?): String? {
        val loosening = VoiceStrict.isLoosening(setting, value)
        return when {
            !view.settings -> NOT_ON_THIS_PC
            setting == VoiceStrict.MEMORY && view.memory.isBlank() -> NOT_ON_THIS_PC
            loosening && linkBlocker != null -> linkBlocker
            setting == VoiceStrict.PRIVACY && value == VoiceStrict.VOICE_IS_ENOUGH && !view.isVeryStrict ->
                PRIVACY_ONLY_VERY_STRICT
            loosening && view.pendingKind == "setting" && view.pendingSetting == setting ->
                "A card for this is already waiting. " + Approvals.WHERE
            else -> null
        }
    }

    /** Whether [value] is what the PC has now - pressing it does nothing. */
    fun isCurrent(setting: String, value: String, view: VoiceStrict.View): Boolean =
        when (setting) {
            VoiceStrict.STRICTNESS -> view.strictness
            VoiceStrict.MEMORY -> view.memory
            else -> view.privacy
        } == value

    /** A card to loosen [setting] is waiting: one line saying so, or null. */
    fun waitingLine(setting: String, view: VoiceStrict.View): String? {
        if (view.pendingKind != "setting" || view.pendingSetting != setting) return null
        return "Waiting for your approval to change this to " +
            "\"${label(setting, view.pendingValue)}\". " + Approvals.WHERE
    }

    /** What to show after a setting was sent, from the PC's answer. */
    fun answerLine(answer: VoiceStrict.Answer): String = when {
        answer.error.isNotBlank() -> VoiceRounds.sentence(answer.error)
        answer.pending -> "Waiting for your approval. " + Approvals.WHERE + " Nothing changes until you do."
        answer.changed -> answer.message.ifBlank { "Done - that applies now." }
        answer.ok -> "It was already set that way."
        else -> "Your PC did not say whether it changed."
    }

    /** How the last setting card ended, or null when the last card was not a setting's. */
    fun lastLine(last: VoiceStrict.Last?): String? {
        if (last == null || last.setting.isBlank()) return null
        val what = "\"${label(last.setting, last.value)}\""
        return when (last.outcome) {
            "setting_changed" -> "Approved: $what is on now."
            "denied" -> "The change to $what was denied on the card. Nothing changed."
            "timed_out" -> "Nobody answered the card for $what in time. Nothing changed."
            "withdrawn" -> "You made it stricter again while the card for $what waited, so " +
                "approving it changed nothing."
            "refused", "failed" -> "Your PC did not change it to $what" +
                (if (last.reason.isBlank()) "." else ": ${last.reason.trim().trimEnd('.')}.")
            else -> null
        }
    }

    /**
     * The plain warning about which voice-ID model very strict can use, or
     * null when the stronger one is installed (or the PC did not say).
     */
    fun modelLine(view: VoiceStrict.View): String? {
        if (!view.settings) return null
        return when (view.veryStrictModel) {
            "strong" -> null
            "small" ->
                "Only the small voice-ID model is installed on your PC. Until the stronger one " +
                    "is installed there, very strict will turn you away far more often."
            else ->
                "No voice-ID model is installed on your PC, so Jarvis turns every voice away, " +
                    "yours too. Very strict also needs the stronger one, or it will turn you " +
                    "away far more often."
        }
    }

    // ----------------------------------------------- the guided repeat test --

    /**
     * Twenty ordinary things to say, read by the owner for the guided test.
     * Each is a sentence of two to four seconds - at least the two seconds of
     * speech very strict asks for a command - and none is one of the
     * training sentences, so the test asks "would it know me?" of words it
     * has not heard.
     */
    val MEASURE_SENTENCES: List<String> = listOf(
        "What time is my first meeting tomorrow morning?",
        "Remind me to take the bins out tonight.",
        "How long would it take to walk to the station?",
        "Read me the last message from my brother.",
        "Add bread, eggs and coffee to the shopping list.",
        "Is it going to rain later this afternoon?",
        "Turn the heating down by two degrees, please.",
        "Set an alarm for half past six tomorrow.",
        "What did I ask you to remember about the car?",
        "Play something calm while I cook dinner.",
        "When is the next bus into the city centre?",
        "Make a note that the plumber comes on Friday.",
        "How many steps have I walked so far today?",
        "Tell me the news headlines in two minutes.",
        "Switch off the lights in the living room.",
        "What is on my calendar for the weekend?",
        "Remind me to call the dentist after lunch.",
        "How much battery does my phone have left?",
        "Find the recipe I saved for lemon chicken.",
        "Wake me up gently at seven on Saturday.",
    )

    /** What the guided test came to: the result in plain words, or why there is none. */
    data class Tested(val ok: Boolean, val lines: List<String>)

    const val NO_TEST_ON_THIS_PC =
        "Your PC does not have this test yet. Run the patch script on the PC first."

    const val MEASURE_INTRO =
        "How often would you have to say things twice? Read 20 ordinary sentences in your " +
            "normal voice, the way you would talk to Jarvis. Your PC checks each one at both " +
            "settings and tells you how many would have got through. Nothing is saved except " +
            "the counts, and nothing changes."

    /**
     * Splits the clips into requests the PC will take: at most [maxClips]
     * and [maxSeconds] each (its 80-second limit per request). In order, so
     * the counts can simply be added up.
     */
    fun batches(seconds: List<Float>, maxClips: Int = 20, maxSeconds: Double = 80.0): List<IntRange> {
        val out = mutableListOf<IntRange>()
        var start = 0
        var sum = 0.0
        for (i in seconds.indices) {
            val s = seconds[i].toDouble()
            if (i > start && (i - start >= maxClips || sum + s > maxSeconds)) {
                out += start until i
                start = i
                sum = 0.0
            }
            sum += s
        }
        if (start < seconds.size) out += start until seconds.size
        return out
    }

    /** The counts of several requests, added up. Null if any is missing. */
    fun combine(parts: List<VoiceStrict.Measured?>): VoiceStrict.Measured? {
        if (parts.isEmpty() || parts.any { it == null }) return null
        val p = parts.filterNotNull()
        fun sum(pick: (VoiceStrict.Measured) -> VoiceStrict.Tally) = VoiceStrict.Tally(
            p.sumOf { pick(it).passed }, p.sumOf { pick(it).of }, p.sumOf { pick(it).tooShort },
        )
        return VoiceStrict.Measured(
            clips = p.sumOf { it.clips },
            strongModel = p.all { it.strongModel },
            veryStrict = sum { it.veryStrict },
            balanced = sum { it.balanced },
        )
    }

    /** "about 3 in 10", "about 1 in 20", "never" - how often something happens. */
    fun howOften(rate: Double): String = when {
        rate.isNaN() || rate <= 0.0 -> "never"
        rate >= 0.95 -> "almost every time"
        rate >= 0.15 -> "about ${(rate * 10).roundToInt()} in 10"
        else -> "about 1 in ${(1 / rate).roundToInt()}"
    }

    /** The guided test's result in plain words. */
    fun measureLines(m: VoiceStrict.Measured): List<String> {
        val vs = m.veryStrict
        val ba = m.balanced
        val lines = mutableListOf<String>()
        lines += "Very strict let ${vs.passed} of your ${vs.of} sentences through; balanced let " +
            "${ba.passed} of ${ba.of} through."
        if (vs.of > 0) {
            val vsAgain = 1.0 - vs.passed.toDouble() / vs.of
            val baAgain = if (ba.of > 0) 1.0 - ba.passed.toDouble() / ba.of else 0.0
            lines += "So at very strict you would have to say it again ${howOften(vsAgain)}; " +
                "at balanced, ${howOften(baAgain)}."
        }
        if (vs.tooShort > 0) {
            lines += "${plural(vs.tooShort, "sentence was", "sentences were")} too short for very " +
                "strict, which needs about two seconds of speech. Speaking a little longer helps."
        }
        if (!m.strongModel) {
            lines += "This was checked with the small voice-ID model only; the stronger one is " +
                "not installed on your PC."
        }
        return lines
    }

    /**
     * How often the owner really had to say something again, since the PC's
     * voice part started (`gate.repeat`) - or null when nothing was said yet.
     * "Again" is the PC's own measure: turned away, then let in within
     * [VoiceStrict.View.repeatWindowSeconds].
     */
    fun repeatLines(view: VoiceStrict.View): List<String> {
        val out = mutableListOf<String>()
        for ((name, c) in listOf("very strict" to view.veryStrict, "balanced" to view.balanced)) {
            if (c.accepted == 0 && c.refused == 0 && c.tooShort == 0) continue
            val rate = if (c.accepted > 0) c.refusedThenAccepted.toDouble() / c.accepted else 0.0
            var line = "At $name: ${plural(c.accepted, "command")} let through; you had to say " +
                "it again ${howOften(rate)}"
            line += if (c.refusedThenAccepted > 0) " (${plural(c.refusedThenAccepted, "time")})." else "."
            val away = c.refused + c.tooShort
            if (away > 0) {
                line += " Turned away: $away" + (if (c.tooShort > 0) ", ${c.tooShort} of them too short." else ".")
            }
            out += line
        }
        return out
    }

    const val REPEAT_NONE =
        "No spoken commands yet since your PC's voice part last started. These numbers are " +
            "kept in memory only and start again when it restarts."

    /** A guided-test clip that must be recorded again, or null. */
    fun measureClipProblem(seconds: Float): String? = when {
        seconds < 1.0f -> "That was too short. Tap Record, read the whole sentence, then tap Stop."
        seconds > 10.0f -> "That was too long. Keep it under 10 seconds."
        else -> null
    }

    fun score(v: Double): String = String.format(Locale.US, "%.2f", v)

    private fun plural(n: Int, one: String, many: String? = null): String =
        if (n == 1) "1 $one" else "$n ${many ?: one + "s"}"
}
