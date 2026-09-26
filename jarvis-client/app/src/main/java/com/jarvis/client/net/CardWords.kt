package com.jarvis.client.net

/**
 * The words on an approval card, and what Jarvis says aloud about a card -
 * the same on this phone as in the desktop's Jarvis bar, widget and HUD.
 *
 * The creativity audit (2026-09-25, docs/creativity-2026-09-25/experience.md
 * finding 1) found the card speaking three dialects - this phone said
 * "Jarvis wants to learning enable", the desktop showed `switch_model`, and
 * Approve and Deny swapped places between screens. Now the PC writes every
 * title (backend/jarvis_card_words.py, served as each row's `notice.title`)
 * and every screen shows the same layout:
 *
 *     Needs your OK                     <- [KICKER]
 *     Jarvis wants to search the web    <- the title
 *     ...the rest of the card...
 *     [Deny]  [Approve]                 <- Deny left, Approve right ([BUTTONS])
 *
 * Deny on the left and Approve on the right matches this card's own swipe
 * (right approves, left denies) and Android's own dialogs, which put the
 * confirming button on the right. docs/ARCHITECTURE.md §3 has the reasons.
 *
 * CardWordsContractTest holds every word here to
 * `contract/card-words-cases.json`, which tools/gen_card_words_cases.py makes
 * from the backend - the desktop's tests/card-words.mjs reads the same file.
 */
object CardWords {
    /** The small label above every card's title. */
    const val KICKER = "Needs your OK"

    /** The two buttons, left to right, on every screen. */
    val BUTTONS = listOf("Deny", "Approve")

    /** The title of a row that names no action at all. */
    const val NO_ACTION = "Jarvis is asking for your approval"

    /** "Open the card" - the line on every screen but Home while a card waits. */
    const val OPEN_CARD = "Open the card"

    /**
     * What Jarvis says during a SPOKEN question that waits on a card, and
     * afterwards - keyed by the chat stream's `: jarvis-status` word
     * (backend/jarvis_agent.py: "approval", then the gate's outcome). Fixed
     * sentences: nothing from the card. There is no approving by voice: the
     * voice check cannot tell a recording from the owner, so these only say
     * where the card is.
     */
    val VOICE: Map<String, String> = mapOf(
        "waiting" to "I need your OK for that. There's a card on your screen.",
        "approved" to "Approved. Carrying on.",
        "denied" to "OK, I won't do that.",
        "timed_out" to "That card timed out, so nothing was done.",
    )

    /** What the "Open the card" line shows: which card, and how many more. */
    data class Waiting(val id: String, val title: String, val more: String)

    /**
     * The "Open the card" line for [items], or null when nothing waits. The
     * NEWEST card is named - the last one read, most likely the one the
     * owner's last tap raised - and "and N more waiting" says the rest are
     * there too. The desktop's `cardLinkView` (card-link.js) says the same.
     */
    fun waiting(items: List<PendingItem>): Waiting? {
        val newest = items.lastOrNull() ?: return null
        val more = items.size - 1
        return Waiting(newest.id, newest.title, if (more > 0) "and $more more waiting" else "")
    }

    private val NOT_A_WORD = Regex("[^A-Za-z0-9 ]+")

    /**
     * A title for a row with no `notice` (a backend older than
     * approval-notice.patch): the action's name, quoted as a name - the PC's
     * own fallback for an action it has no phrase for, letter for letter.
     * Never from `prompt` or `detail`: a title also ends up on a lock screen.
     */
    fun fallbackTitle(action: String?): String {
        val words = (action ?: "")
            .replace('_', ' ')
            .replace(NOT_A_WORD, " ")
            .split(' ')
            .filter { it.isNotEmpty() }
            .joinToString(" ")
            .take(60)
            .trim()
        return if (words.isEmpty()) NO_ACTION else "Jarvis wants your OK for \"$words\""
    }
}
