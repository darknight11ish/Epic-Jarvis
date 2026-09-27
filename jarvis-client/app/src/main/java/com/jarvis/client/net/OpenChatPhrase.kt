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
 * [CardWords]: a sentence that is not wholly one of these phrases is an
 * ordinary question and goes to the model as always, floating avatar or
 * not.
 *
 * [PHRASES] is a hand-picked subset of the backend's own `jarvis_quick.py`
 * `_OPEN_CHAT` grammar - every "chat"-wording phrase it accepts (the
 * backend also has "jarvis bar" wording, which is the desktop's own window
 * name and has no place in this app's vocabulary). Cross-checked against
 * that grammar by `tools/gen_open_chat_cases.py`
 * (`open-chat-cases.json`, [OpenChatPhraseContractTest]) rather than
 * hand-copied, after the cross-cutting audit (2026-09-27, finding #7)
 * found this list had already drifted from it - phrases like "open
 * jarvis" and "let's chat" used to bring the app to the front here but
 * would not have opened anything if typed or said as an ordinary chat
 * message, which is exactly the inconsistency unifying the two closes.
 * Still deliberately narrower than the backend's own normaliser (leading
 * "please", trailing "thanks", and so on): that engine also decides what
 * the model never sees, and this list is only ever consulted for ONE
 * extra thing - whether to also bring the app to the front - never
 * instead of sending the turn, so it does not need to match everything
 * the backend's fuller normaliser tolerates, only to never disagree about
 * the phrases it does claim.
 */
object OpenChatPhrase {

    /**
     * Fixed phrasings, already lower-cased and trimmed of outer whitespace.
     * Every entry here must equal one of `open-chat-cases.json`'s own
     * "matches" - [OpenChatPhraseContractTest] checks it.
     */
    private val PHRASES = setOf(
        "open a chat",
        "open a chat window",
        "open the chat",
        "open the chat window",
        "show me a chat",
        "show me a chat window",
        "show me the chat",
        "show me the chat window",
        "show chat",
        "show chat window",
        "show the chat",
        "show the chat window",
        "bring up a chat",
        "bring up a chat window",
        "bring up the chat",
        "bring up the chat window",
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
