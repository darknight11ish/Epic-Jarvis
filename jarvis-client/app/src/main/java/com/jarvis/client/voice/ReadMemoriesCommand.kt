package com.jarvis.client.voice

/**
 * The phone's remembered-answers switch, changed by a typed or SPOKEN sentence
 * (the owner's decision of 2026-11-07).
 *
 * THE OWNER'S WORDS: "i wanted to read everything out loud if i ask it to by
 * Default or unless I can change it through chat turn that off. unless it's
 * extremely sensitive information it's okay." The switch itself is the phone's
 * own (`MemoryAloud`, `ClientSettings.readMemoriesAloud`, ON by default). This
 * object is the grammar for changing it from the chat:
 *
 *   "stop reading remembered answers out loud" / "don't read everything out
 *   loud" / "stop reading everything out loud"  -> OFF, at once
 *   "read everything out loud" / "read your replies out loud" /
 *   "read remembered answers out loud"          -> ON, at once
 *   "are you reading everything out loud?"      -> the state, in words
 *
 * WHY THE PHONE ANSWERS THESE ITSELF. The setting lives in this phone's own
 * preferences, not on the PC, so the PC cannot change it - and the model has
 * no tool for it, so sending the sentence on would get an invented success.
 * The same parser is called from the typed box (before anything is sent) and
 * from a spoken/Live turn ([com.jarvis.client.voice.VoiceSession.answer]); a
 * model ANSWER never goes through it, so a model can never toggle the switch.
 *
 * A miss is harmless: the words go to Jarvis as an ordinary question, exactly
 * as before. A hijack is not, so the matches are whole sentences.
 *
 * Pure Kotlin, no Android types: `ReadMemoriesCommandTest` runs it on a plain
 * JVM.
 */
object ReadMemoriesCommand {

    /** What the owner asked for, or that he asked about the state. */
    enum class Change { ON, OFF, ASK }

    /** The line said after a real change; the switch is the phone's own. */
    const val SAID_ON =
        "Reading remembered answers out loud is on now. A voice answer that uses what " +
            "Jarvis remembers is read aloud, including in Jarvis Live and after \"hey " +
            "Jarvis\". An extremely sensitive saved fact still stays on your screen."
    const val SAID_OFF =
        "Reading remembered answers out loud is off now. An answer that uses what Jarvis " +
            "remembers stays on your screen; tap Read aloud on an answer to hear that one."

    /** The state answer, in the switch's own words. */
    fun stateLine(on: Boolean): String = if (on) {
        "Yes - remembered answers are read aloud by default on this phone, including in " +
            "Jarvis Live and after \"hey Jarvis\". Say \"stop reading remembered answers " +
            "out loud\" to turn that off. An extremely sensitive saved fact always stays " +
            "on your screen."
    } else {
        "No - remembered answers are not read aloud automatically on this phone. Say " +
            "\"read everything out loud\" to turn that back on. A typed answer is read " +
            "only when you tap Read aloud."
    }

    /** Every whole sentence that asks for a change, and what it asks for. */
    private val PHRASES: Map<String, Change> = linkedMapOf(
        "stop reading remembered answers out loud" to Change.OFF,
        "stop reading remembered answers aloud" to Change.OFF,
        "stop reading remembered facts out loud" to Change.OFF,
        "stop reading remembered answers" to Change.OFF,
        "stop reading everything out loud" to Change.OFF,
        "stop reading everything aloud" to Change.OFF,
        "dont read remembered answers out loud" to Change.OFF,
        "don't read remembered answers out loud" to Change.OFF,
        "dont read everything out loud" to Change.OFF,
        "don't read everything out loud" to Change.OFF,
        "do not read everything out loud" to Change.OFF,
        "turn off reading remembered answers out loud" to Change.OFF,
        "turn off reading everything out loud" to Change.OFF,
        "read everything out loud" to Change.ON,
        "read everything aloud" to Change.ON,
        "read remembered answers out loud" to Change.ON,
        "read your replies out loud" to Change.ON,
        "read your answers out loud" to Change.ON,
        "read all of your answers out loud" to Change.ON,
        "turn on reading remembered answers out loud" to Change.ON,
        "turn on reading everything out loud" to Change.ON,
        "are you reading everything out loud" to Change.ASK,
        "are you reading everything aloud" to Change.ASK,
        "are you reading remembered answers out loud" to Change.ASK,
        "are you reading remembered answers aloud" to Change.ASK,
        "are you reading your replies out loud" to Change.ASK,
        "are remembered answers read out loud" to Change.ASK,
        "is reading everything out loud on" to Change.ASK,
        "is reading remembered answers out loud on" to Change.ASK,
    )

    /** "hey jarvis" or "jarvis", with an optional separator, at the start. */
    private val WAKE = Regex("""^(hey\s+jarvis|jarvis)\s*[,:;-]?\s*""")

    private val WHITESPACE = Regex("""\s+""")

    /** Trailing punctuation stripped before matching. */
    private const val END_PUNCTUATION = "?!."

    /** Case, spacing and a last "?" / "!" / "." taken off; nothing inside. */
    fun normalise(text: String?): String = text.orEmpty()
        .trim()
        .lowercase()
        .replace(WHITESPACE, " ")
        .trimEnd { it in END_PUNCTUATION }
        .trim()

    /**
     * The change one sentence asks for, or null when it is an ordinary
     * question. A whole sentence only, optionally after "hey jarvis"/"jarvis".
     */
    fun command(text: String?): Change? {
        val said = normalise(text)
        if (said.isEmpty()) return null
        PHRASES[said]?.let { return it }
        val asked = said.replaceFirst(WAKE, "").trim()
        if (asked.isEmpty() || asked == said) return null
        return PHRASES[asked]
    }
}
