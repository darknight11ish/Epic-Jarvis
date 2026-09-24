package com.jarvis.client.voice

import com.jarvis.client.net.Approvals
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.VoiceCalibration
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.VoiceStrict
import com.jarvis.client.net.VoiceTrainingLast
import com.jarvis.client.net.VoiceTrainingReply
import java.util.Locale

/**
 * "Train my voice": the words and rules, with no Android in them, so every
 * sentence the screen shows is unit-tested (`VoiceTrainingTest`).
 *
 * What the feature is. Jarvis only obeys the owner's voice, and it learns
 * that voice from a few recorded sentences. The phone records them - the same
 * recorder and format as the talk button, so the PC checks like with like -
 * and sends them to the PC. The PC does NOT learn from them straight away: it
 * raises an approval card, and only approving it replaces the voice print.
 * The phone keeps no copy of the clips once they are sent.
 *
 * Nothing here turns speech into text. The sentences are shown for the owner
 * to read; nobody checks the words, only the voice.
 */
object VoiceTraining {

    /**
     * Twelve short sentences, each about two to four seconds read aloud -
     * about two minutes in all, including the tapping.
     *
     * Chosen to cover different sounds rather than to mean anything: a
     * pangram (every letter), requests in an ordinary voice, questions (the
     * voice rises at the end), a run of "s" and "th" sounds, numbers and
     * colours. Four start with "Hey Jarvis": the PC learns from those how
     * the owner says the wake word (its "hey Jarvis" check), and the rest
     * teach it what the owner sounds like saying anything else. More, and
     * more varied, sentences than the old five give the voice print a
     * steadier middle and the PC more to measure the owner's own spread by.
     */
    val SENTENCES: List<String> = listOf(
        "Hey Jarvis, what's on my calendar today?",
        "The quick brown fox jumps over the lazy dog.",
        "Please remind me to call my sister on Thursday.",
        "Hey Jarvis, turn the lights down a little.",
        "What is the weather going to be like this weekend?",
        "Six thick thistle sticks stood by the gate.",
        "Hey Jarvis, play some quiet music.",
        "I'd like a cup of tea with milk, no sugar.",
        "How long will it take to drive into town?",
        "Hey Jarvis, set a timer for ten minutes.",
        "My favourite colours are red, green and blue.",
        "Good morning, it's nice to hear your voice again.",
    )

    /** This phone's microphone, as the PC names it (one voice print per microphone). */
    const val MIC = JarvisApi.MIC_PHONE

    /**
     * For the "someone else" check: three sentences for another person to
     * read, so the PC can see how close a different voice gets.
     */
    val OTHER_SENTENCES: List<String> = listOf(
        "Hey Jarvis, what time is it?",
        "Can you read me the news headlines?",
        "Turn the heating up a couple of degrees.",
    )

    /**
     * The PC's limits (`jarvis_voice_enroll.py`: MIN_SECONDS, MAX_SECONDS).
     * Checked here too so a clip the PC would refuse is redone now, while the
     * owner is still holding the phone, rather than after sending all five.
     */
    const val MIN_SECONDS = 1.0f
    const val MAX_SECONDS = 10.0f

    /**
     * All the clips together, at most (`jarvis_voice_enroll.py`
     * MAX_TOTAL_SECONDS): twelve long clips would not fit in one request.
     */
    const val MAX_TOTAL_SECONDS = 80.0f

    /** The first screen, word for word. */
    const val INTRO =
        "Jarvis only listens to your voice. Read these 12 short sentences so it learns what you " +
            "sound like, and how you say \"hey Jarvis\". It takes about two minutes."

    const val INTRO_DETAIL =
        "Find a quiet spot and speak normally, at the distance you usually hold the phone. " +
            "Your PC will then ask you to approve the change on an approval card - nothing " +
            "changes until you do. The recordings are deleted from this phone as soon as " +
            "they are sent, and from the PC once the card is answered."

    const val AFTER_SENDING = "Sent. A card is waiting to finish it. " + Approvals.WHERE

    /** One recorded sentence, held in memory only until it is sent. */
    class Clip(val wav: ByteArray, val seconds: Float)

    /** What the recorder produced, without the recorder's Android types. */
    sealed interface Take {
        class Captured(val wav: ByteArray, val seconds: Float) : Take

        /** @param needsPermission the microphone permission is what is missing. */
        data class Failed(val message: String, val needsPermission: Boolean = false) : Take
    }

    /** What pressing Send came to. [accepted] means a card is now up on the PC. */
    data class SendResult(val accepted: Boolean, val message: String)

    /** "3.4 s" - always a dot, whatever the phone's language, like the other readouts. */
    fun lengthLabel(seconds: Float): String = String.format(Locale.US, "%.1f s", seconds)

    /** Why this clip must be recorded again, or null when it is fine. */
    fun clipProblem(seconds: Float): String? = when {
        seconds < MIN_SECONDS ->
            "That was too short. Tap Record, read the whole sentence, then tap Stop."
        seconds > MAX_SECONDS ->
            "That was too long. Keep it under ${MAX_SECONDS.toInt()} seconds."
        else -> null
    }

    /**
     * Why "Send to your PC" cannot be pressed, or null when it can.
     *
     * The link comes first: a stale link is the app's standing rule for not
     * acting (the same `actionBlocker` every other write uses), and it is the
     * answer the owner can do something about from here.
     */
    fun sendBlocker(
        recorded: Int,
        total: Int,
        linkBlocker: String?,
        totalSeconds: Float = 0f,
    ): String? = when {
        linkBlocker != null -> linkBlocker
        recorded < total -> "Record all $total sentences first ($recorded done)."
        totalSeconds > MAX_TOTAL_SECONDS ->
            "The recordings are ${totalSeconds.toInt()} seconds in all; the most is " +
                "${MAX_TOTAL_SECONDS.toInt()}. Redo the longest ones a little quicker."
        else -> null
    }

    /** One line: is Jarvis trained on the owner's voice, as the PC last said. */
    fun stateLine(status: VoiceStatus, answered: Boolean): String {
        val gate = status.gate
        return when {
            !answered -> "Your PC has not answered yet, so this is not known."
            !status.available -> "The voice part of Jarvis is not running on your PC."
            gate.training.pending -> "Waiting for your approval. " + Approvals.WHERE
            gate.needsRetraining ->
                "Your PC's voice check changed since you trained it. Train your voice again."
            gate.prints.phone.trained ->
                "Trained on this phone, from ${plural(gate.prints.phone.samples, "sample")}."
            gate.enrolled -> "Trained, from ${plural(gate.samples, "sample")}."
            gate.mode.trim().lowercase(Locale.ROOT) == "broad" ->
                "Not trained. Jarvis is set to listen to anyone, so this is optional."
            else -> "Not trained yet. Until it is, Jarvis will not act on anyone's voice."
        }
    }

    /**
     * The one warning about the basic check, or null when a real speaker model
     * is installed (or the PC has not answered - no claim either way then).
     *
     * Stronger than "less reliable" on purpose: the basic check compares how
     * loud each pitch band is, and when it was tried on four synthesised
     * voices (2026-09-23, backend/README.md "voice-enroll") it scored every
     * one of them above 0.9 against the others, where the bar is 0.35. It
     * stops silence and noise, not a stranger.
     */
    fun basicCheckLine(status: VoiceStatus, answered: Boolean): String? =
        if (answered && status.available && !status.gate.speakerModel) {
            "Using the basic voice check, which cannot reliably tell two people apart. " +
                "Install the better one on your PC for more reliable results."
        } else {
            null
        }

    /**
     * One line about the PC's microphone, or null when there is nothing
     * worth saying (the PC did not report per-microphone prints).
     */
    fun desktopLine(status: VoiceStatus, answered: Boolean): String? {
        val p = status.gate.prints
        if (!answered || !status.available || !(p.phone.trained || p.general.trained)) return null
        return if (p.desktop.trained) {
            "The PC's microphone has its own voice print too."
        } else {
            "Your PC's own microphone uses this one until it is trained separately."
        }
    }

    /**
     * How the last voice card ended, or null if none has since the PC started.
     *
     * Since the stricter check (2026-09-24) the PC's `training.last` also
     * reports a card that changed a SETTING (very strict / balanced, private
     * answers), and rounds that were cancelled or ran out of time. [strict]
     * is the same `last`, read by [VoiceStrict.parse], which has the fields
     * that tell those apart - without it a denied setting card read "Last
     * training was denied", and a changed one "Last training:
     * setting_changed."
     */
    fun lastLine(last: VoiceTrainingLast?, strict: VoiceStrict.Last?, view: VoiceStrict.View? = null): String? {
        if (strict != null && strict.setting.isNotBlank()) return StrictVoice.lastLine(strict, view)
        return when {
            last?.outcome == "enrolled" && strict?.added == true ->
                "Your extra recordings were approved and added: the voice print now has " +
                    "${plural(last.samples, "sample")}." + wakeCheckSuffix(last.wakeCheck)
            last?.outcome == "cancelled" -> "The last training was cancelled. Nothing changed."
            last?.outcome == "expired" ->
                "The rounds your PC was holding were deleted after 15 minutes with no new " +
                    "round. Nothing changed."
            else -> lastLine(last)
        }
    }

    /** How the last training ended, or null if none has since the PC started. */
    fun lastLine(last: VoiceTrainingLast?): String? = when (last?.outcome) {
        null, "" -> null
        "enrolled" -> "Last training was approved: ${plural(last.samples, "sample")} saved." +
            wakeCheckSuffix(last.wakeCheck)
        "threshold_set" -> "The new setting was approved: voices must now score " +
            "${score(last.threshold)} to pass."
        "denied" -> "Last training was denied on the card. Nothing changed."
        "timed_out" -> "Nobody answered the last training card in time. Nothing changed."
        "refused" -> "Your PC refused the last training" + reasonSuffix(last.reason)
        "failed" -> "The last training failed" + reasonSuffix(last.reason)
        else -> "Last training: ${last.outcome}."
    }

    /** What to show after pressing Send, from the PC's answer. */
    fun replyLine(reply: VoiceTrainingReply): String = when {
        reply.error.isNotBlank() -> reply.error.trim().replaceFirstChar { it.uppercase() }
            .let { if (it.endsWith(".")) it else "$it." }
        reply.ok -> AFTER_SENDING
        else -> "Your PC did not say whether it got the recordings."
    }

    /** Whether the PC accepted the clips (a card is up, or was just answered). */
    fun accepted(reply: VoiceTrainingReply): Boolean = reply.ok && reply.error.isBlank()

    // ------------------------------------------------ the "someone else" check

    /** What the PC said about the other person's clips, in plain words. */
    data class CheckResult(val ok: Boolean, val message: String, val suggested: Double? = null)

    /** Offered only when the PC is new enough ([com.jarvis.client.net.VoiceTrainingState.calibrate]) and a print exists. */
    fun canCheck(status: VoiceStatus, answered: Boolean): Boolean =
        answered && status.available && status.gate.training.calibrate &&
            (status.gate.prints.phone.trained || status.gate.prints.general.trained)

    const val CHECK_INTRO =
        "Want to make sure Jarvis turns other people away? Ask someone else to read 3 " +
            "sentences into this phone. Your PC compares them with your voice and suggests a " +
            "setting. Nothing changes unless you approve it."

    /** The result, from the PC's answer. */
    fun checkResult(c: VoiceCalibration): CheckResult {
        if (c.error.isNotBlank()) {
            return CheckResult(false, c.error.trim().replaceFirstChar { it.uppercase() }
                .let { if (it.endsWith(".")) it else "$it." })
        }
        if (!c.ok) return CheckResult(false, c.message.ifBlank { "Your PC could not compare the voices." })
        val theirs = c.scores.filterNotNull()
        val passed = theirs.count { it >= c.threshold }
        val head = when {
            theirs.isEmpty() -> "None of the clips could be scored."
            passed == 0 -> "Good: none of their ${theirs.size} clips would pass as you now."
            else -> "$passed of their ${theirs.size} clips would pass as you now."
        }
        val tail = when {
            c.suggested != null && c.suggested > c.threshold + 0.005 ->
                " A stricter setting, ${score(c.suggested)} (now ${score(c.threshold)}), would " +
                    "turn them away and still let you in."
            c.suggested != null -> " Your current setting already sits between you and them."
            else -> " " + c.message.ifBlank { "Their voice came too close to yours to suggest a stricter setting." }
        }
        return CheckResult(true, head + tail, c.suggested?.takeIf { it > c.threshold + 0.005 })
    }

    /** "0.52" - always a dot. */
    fun score(v: Double): String = String.format(Locale.US, "%.2f", v)

    private fun wakeCheckSuffix(wakeCheck: String): String = when {
        wakeCheck.isBlank() -> ""
        wakeCheck.startsWith("built") -> " Its \"hey Jarvis\" check was built too."
        else -> " Its \"hey Jarvis\" check was not built (" +
            wakeCheck.removePrefix("not built").trimStart(':', ' ').trimEnd('.') + ")."
    }

    private fun reasonSuffix(reason: String): String =
        if (reason.isBlank()) "." else ": ${reason.trim().trimEnd('.')}."

    private fun plural(n: Int, word: String) = if (n == 1) "1 $word" else "$n ${word}s"
}
