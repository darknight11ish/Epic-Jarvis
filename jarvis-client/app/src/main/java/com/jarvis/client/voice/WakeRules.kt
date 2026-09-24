package com.jarvis.client.voice

import com.jarvis.client.net.Approvals
import com.jarvis.client.net.Heard
import com.jarvis.client.net.VoiceStatus

/**
 * The wake word's decisions that need no Android: when this phone may listen,
 * when it may send, and what a verdict from the desktop means. Unit-tested
 * in `WakeRulesTest`.
 */
object WakeRules {

    /** What the listener does with the desktop's answer to a wake-word clip. */
    enum class Verdict {
        /** "Hey Jarvis, ..." from the owner, transcribed: answered like push-to-talk. */
        ANSWER,

        /** "Hey Jarvis." on its own: record the next sentence and send that. */
        AWAKE,

        /** Not addressed to Jarvis, or not the owner: dropped without a word. */
        IGNORE,

        /** The desktop cannot take wake-word clips right now (switched off, no model): stop listening. */
        STOP,

        /**
         * "Hey Jarvis" was heard from the owner, but the command after it was
         * too short to check: show the PC's own sentence ([Heard.message]),
         * send nothing. The desktop's quickbar does the same (main.js,
         * "voice-heard"). A short clip WITHOUT the phrase could be anyone in
         * the room, so that one stays [IGNORE].
         */
        TOO_SHORT,
    }

    fun verdict(h: Heard): Verdict = when {
        !h.available -> Verdict.STOP
        h.tooShort && h.wakeHeard -> Verdict.TOO_SHORT
        h.tooShort -> Verdict.IGNORE
        h.awake && h.owner -> Verdict.AWAKE
        h.wakeHeard && h.owner -> Verdict.ANSWER
        else -> Verdict.IGNORE
    }

    /**
     * Whether this phone may listen for "hey Jarvis" at all. Null means yes;
     * otherwise the sentence to show.
     *
     * docs/WAKE-WORD.md §4 step 5: a wake-word capture is never made while the
     * desktop says the wake word is off - the client half of the desktop's
     * own refusal, so it never relies on being told no. An unanswered status
     * is not "on".
     */
    fun mayListen(answered: Boolean, status: VoiceStatus): String? = when {
        !answered ->
            "The desktop has not answered, so this phone cannot tell whether \"hey Jarvis\" is on."
        !status.wakeWordOn ->
            "\"Hey Jarvis\" is off on your desktop. Turn it on first - it asks for your approval."
        else -> null
    }

    /**
     * Whether a clip may be sent now. Also refused while the event stream is
     * stale (rule 4: nothing acts on a link that may be dead or out of date);
     * the listener keeps listening and says why it did not send.
     */
    fun mayPost(answered: Boolean, status: VoiceStatus, stale: Boolean): String? =
        mayListen(answered, status)
            ?: if (stale) {
                "Heard \"hey Jarvis\", but the link to your desktop is down, so nothing was sent."
            } else {
                null
            }

    /**
     * Whether asking the desktop to change the wake word may go now. Null means
     * yes; otherwise the sentence to show, and nothing is sent.
     *
     * Turning it ON raises a `change_own_config` approval card, so it is held
     * on a stale or dropped link exactly like every other card-raising action
     * (rule 4) - [linkBlocker] is the runtime's `actionBlocker()`. Turning it
     * OFF is never held: it only closes things, and must not wait on a link.
     */
    fun requestBlocker(enabled: Boolean, linkBlocker: String?): String? =
        if (enabled) linkBlocker else null

    /** The desktop's threshold, held inside the range anyone would mean. */
    fun threshold(status: VoiceStatus): Float = status.wake.threshold.toFloat().coerceIn(0.1f, 0.99f)

    /**
     * What to tell the owner after asking the desktop to turn the wake word
     * on or off, from what the desktop reports AFTERWARDS. Null: it did.
     */
    fun afterRequest(enabled: Boolean, nowOn: Boolean, pending: Boolean): String? = when {
        enabled == nowOn -> null
        enabled && pending ->
            "A card to turn it on is waiting. ${Approvals.WHERE} Nothing changes until you do."
        enabled ->
            "The desktop did not raise an approval card, so \"hey Jarvis\" is still off. " +
                "Its settings may not allow it (change_own_config must be \"ask\")."
        else ->
            // The honest version of the failure the re-read exists for.
            "The desktop accepted the change but still reports the wake word ON. " +
                "It may need restarting before it takes effect."
    }
}
