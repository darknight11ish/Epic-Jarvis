package com.jarvis.client.net

/**
 * "Open a chat" while Floating Jarvis is up - expands the bubble or overlay
 * avatar into the real chat screen (`docs/JARVIS-API.md` section 56).
 *
 * NOT a new speech-to-text path (CLAUDE.md: "a client must not do
 * speech-to-text"). The desktop already transcribes and voice-checks every
 * "hey Jarvis" clip and hands the words back as [com.jarvis.client.net.Heard.text]
 * - the exact same field [com.jarvis.client.voice.VoiceSession] already
 * reads to send the turn on to the model. This only matches THAT text, on
 * the phone, against a short fixed phrase list, the same shape as
 * [CardWords] and the backend's own `jarvis_quick.py` grammar (a small,
 * exact set, never a guess): a sentence that is not wholly one of these
 * phrases is an ordinary question and goes to the model as always, floating
 * avatar or not.
 *
 * Deliberately no attempt to also mirror `jarvis_quick.py`'s own normaliser
 * (leading "please", trailing "thanks", and so on): that engine also
 * decides what the model never sees, and copying its exact edge cases here
 * would risk this list quietly drifting from it. This list is only ever
 * consulted for ONE extra thing - whether to also bring the app to the
 * front - never instead of sending the turn.
 */
object OpenChatPhrase {

    /** Fixed phrasings, already lower-cased and trimmed of outer whitespace. */
    private val PHRASES = setOf(
        "open a chat",
        "open the chat",
        "open chat",
        "open a chat window",
        "open the chat window",
        "open the chat screen",
        "show me the chat",
        "show the chat",
        "show me the chat screen",
        "show the chat screen",
        "open jarvis",
        "open the jarvis app",
        "open the app",
        "bring up the chat",
        "let's chat",
        "lets chat",
    )

    private val LEAD = Regex("^(?:(?:hey|hi|ok|okay)\\s+jarvis\\b[\\s,]*|jarvis\\b[\\s,]*)+")

    /**
     * True when [text] - the words the desktop already transcribed and
     * checked - is WHOLLY one of [PHRASES], a leading "hey Jarvis"/"Jarvis"
     * aside. Case- and punctuation-insensitive; nothing fuzzier than that,
     * on purpose (see the class doc).
     */
    fun matches(text: String): Boolean {
        val t = normalise(text)
        return t.isNotEmpty() && t in PHRASES
    }

    private fun normalise(text: String): String {
        var t = text.trim().lowercase()
            .replace('’', '\'').replace('‘', '\'')
        t = Regex("[\\s.!?]+$").replace(t, "")
        t = LEAD.replace(t, "")
        t = Regex("\\s+").replace(t, " ").trim()
        return t
    }
}
