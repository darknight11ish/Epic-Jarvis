package com.jarvis.client.voice

import com.jarvis.client.net.VoiceStatus
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
     * Five sentences, each about three to five seconds read aloud.
     *
     * Chosen to cover different sounds rather than to mean anything: a
     * pangram (every letter), a request in an ordinary voice, a question
     * (the voice rises at the end), a run of "s" and "th" sounds, and the
     * name Jarvis itself, which is what the owner will actually say most.
     */
    val SENTENCES: List<String> = listOf(
        "The quick brown fox jumps over the lazy dog near the riverbank.",
        "Please remind me to call my sister on Thursday afternoon.",
        "What is the weather going to be like this weekend?",
        "Six thick thistle sticks stood beside the old wooden gate.",
        "Jarvis, turn the lights down low and play some quiet music.",
    )

    /**
     * The PC's limits (`jarvis_voice_enroll.py`: MIN_SECONDS, MAX_SECONDS).
     * Checked here too so a clip the PC would refuse is redone now, while the
     * owner is still holding the phone, rather than after sending all five.
     */
    const val MIN_SECONDS = 1.0f
    const val MAX_SECONDS = 10.0f

    /** The first screen, word for word. */
    const val INTRO =
        "Jarvis only listens to your voice. Read these 5 sentences so it learns what you " +
            "sound like. It takes about a minute."

    const val INTRO_DETAIL =
        "Find a quiet spot and speak normally, at the distance you usually hold the phone. " +
            "Your PC will then ask you to approve the change on an approval card - nothing " +
            "changes until you do. The recordings are deleted from this phone as soon as " +
            "they are sent, and from the PC once the card is answered."

    const val AFTER_SENDING = "Approve the card on your PC or phone to finish."

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
    fun sendBlocker(recorded: Int, total: Int, linkBlocker: String?): String? = when {
        linkBlocker != null -> linkBlocker
        recorded < total -> "Record all $total sentences first ($recorded done)."
        else -> null
    }

    /** One line: is Jarvis trained on the owner's voice, as the PC last said. */
    fun stateLine(status: VoiceStatus, answered: Boolean): String {
        val gate = status.gate
        return when {
            !answered -> "Your PC has not answered yet, so this is not known."
            !status.available -> "The voice part of Jarvis is not running on your PC."
            gate.training.pending -> "Waiting for you to approve the card on your PC or phone."
            gate.needsRetraining ->
                "Your PC's voice check changed since you trained it. Train your voice again."
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

    /** How the last training ended, or null if none has since the PC started. */
    fun lastLine(last: VoiceTrainingLast?): String? = when (last?.outcome) {
        null, "" -> null
        "enrolled" -> "Last training was approved: ${plural(last.samples, "sample")} saved."
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

    private fun reasonSuffix(reason: String): String =
        if (reason.isBlank()) "." else ": ${reason.trim().trimEnd('.')}."

    private fun plural(n: Int, word: String) = if (n == 1) "1 $word" else "$n ${word}s"
}
