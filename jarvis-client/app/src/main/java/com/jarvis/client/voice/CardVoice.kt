package com.jarvis.client.voice

import com.jarvis.client.net.CardWords

/**
 * Which card line a SPOKEN question says, as the chat stream's status words
 * arrive (`: jarvis-status approval`, then how the card ended: `approved`,
 * `denied` or `timed_out` - backend/jarvis_agent.py).
 *
 * Before this, a spoken question that needed an approval card went silent:
 * the owner, perhaps across the room, heard nothing while the card waited
 * and ran out of time (the creativity audit, 2026-09-25, finding 2). Now
 * Jarvis says a card is waiting, and afterwards what happened - in fixed
 * words ([CardWords.VOICE]), never the card's, so it is safe in any room.
 *
 * It only SAYS where the card is. Nothing here, or anywhere, approves by
 * voice: the voice check cannot tell a recording from the owner, so a "yes"
 * said aloud answers nothing - only a tap on the card does.
 *
 * "approval" says the waiting line once per card; an outcome word says what
 * happened - only after the waiting line was said, so an outcome never
 * arrives out of nowhere. The desktop's `createCardVoice` (card-words.js)
 * does exactly this; CardWordsContractTest runs both through the same
 * `voice_script` cases.
 */
class CardVoice {
    private var waiting = false

    /** A new question: nothing said yet. */
    fun reset() {
        waiting = false
    }

    /** The line to say for [word], or null. */
    fun onStatus(word: String): String? = when (word) {
        "approval" -> if (waiting) {
            null
        } else {
            waiting = true
            CardWords.VOICE.getValue("waiting")
        }
        "approved", "denied", "timed_out" -> if (!waiting) {
            null
        } else {
            waiting = false
            CardWords.VOICE.getValue(word)
        }
        else -> null
    }

    companion object {
        /** True for one of the fixed card lines (never an answer's words). */
        fun isCardLine(text: String): Boolean = text in CardWords.VOICE.values
    }
}
