package com.jarvis.client.net

/**
 * "Was this answer right?" typed into the chat box, and what it means.
 *
 * The owner's field test of 2026-11-01: they typed exactly this into the
 * phone's chat, and the phone sent it to the PC as an ordinary question -
 * Jarvis answered it conversationally, and the answer's own menu stayed shut.
 * The words are a request for the menu the chevron opens (the owner's request
 * of 2026-10-27: "put a carrot that opens a menu on each chat that has this"),
 * so the phone answers them itself and sends nothing.
 *
 * Pure Kotlin, no Android types, so `AnswerMenuAskTest` runs it on a plain JVM.
 * Nothing here reads or writes the PC, and nothing here keeps a word.
 *
 * WHY THE LIST IS THIS SHORT. A miss is harmless - the words go to Jarvis as a
 * question, which is what happened before - but a hijack is not: a real
 * question must never be swallowed by a menu. So only whole sentences about
 * THIS answer are on the list. "was this right for you" and "was that right
 * about the weather" are questions, and `matches` says no to them (the match
 * is on the whole sentence, never on a prefix). "is this answer right",
 * "was my answer right" and "was the answer correct" are not on the list at
 * all: they are the owner asking about something, not asking the phone for
 * this answer's menu.
 */
object AnswerMenuAsk {

    /**
     * Said, in this screen's own words, when the words were a menu request but
     * there is no finished answer on the screen to open one for. One short
     * sentence: nothing was sent, so the PC has nothing to say about it.
     */
    const val NO_ANSWER = "There is no finished answer on the screen to open a menu for yet."

    /** Every sentence that opens the menu, already normalised (see [normalise]). */
    val PHRASES: Set<String> = linkedSetOf(
        "was this answer right",
        "was that answer right",
        "was the last answer right",
        "was the previous answer right",
        "was this right",
        "was that right",
    )

    /** "hey jarvis" or "jarvis", with an optional comma after it, at the start. */
    private val WAKE = Regex("""^(hey\s+jarvis|jarvis)\s*[,:;-]?\s*""")

    private val WHITESPACE = Regex("""\s+""")

    /** The last characters the owner's sentence may end with, stripped before matching. */
    private const val END_PUNCTUATION = "?!."

    /**
     * The words with case, spacing and a last "?" / "!" / "." taken off - so
     * "  Was  this answer RIGHT?! " and "was this answer right" are the same.
     * Never touches anything inside the sentence: that is what keeps a real
     * question from matching by accident.
     */
    fun normalise(text: String?): String = text.orEmpty()
        .trim()
        .lowercase()
        .replace(WHITESPACE, " ")
        .trimEnd { it in END_PUNCTUATION }
        .trim()

    /**
     * Do these typed words ask for the answer's own menu?
     *
     * True only for a whole sentence on [PHRASES], optionally after "hey
     * jarvis" / "jarvis". Everything else - a real question, a longer
     * sentence, a near miss - is false, and is sent to Jarvis as before.
     */
    fun matches(text: String?): Boolean {
        val said = normalise(text)
        if (said.isEmpty()) return false
        // One greeting only: "jarvis jarvis was this right" is not on the list.
        val asked = said.replaceFirst(WAKE, "").trim()
        if (asked == said) return asked in PHRASES
        // Only the greeting came off, and there must be something left.
        return asked.isNotEmpty() && asked in PHRASES
    }
}
