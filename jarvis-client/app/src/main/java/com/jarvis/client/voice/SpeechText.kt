package com.jarvis.client.voice

/**
 * The pure text-shaping half of sentence-streaming TTS - split out of
 * [VoiceSession] on purpose, because everything in this file is a plain
 * function over `String`/`Int` with no `Context`, no coroutine, and no
 * network call anywhere near it. That makes it provable by a plain JVM unit
 * test (`app/src/test`), no emulator required - which matters more than
 * usual here: this app has no local build at all (CI is the only compiler),
 * and this is exactly the kind of regex-heavy logic where an off-by-one or a
 * mis-grouped alternation fails silently rather than loudly. One such bug
 * (`BOLD_ITALIC` matching three different capture groups but only ever
 * substituting group 1 - silently DELETING `**bold**` and `*italic*` text
 * instead of unwrapping it) was caught by hand while writing this, before
 * any test existed; the fix is now also a checked case in
 * `SpeechTextTest.kt`, not just a comment.
 */
internal object SpeechText {

    /** A run of text ending in `.`/`!`/`?`, followed by real whitespace - not
     *  punctuation alone, since the stream may simply not have produced the
     *  next character yet (`3.14`, `Dr.`, mid-ellipsis). */
    private val SENTENCE_BOUNDARY = Regex("""([\s\S]*?[.!?])\s+""")

    private val CODE_BLOCK = Regex("""```[\s\S]*?```""")
    private val INLINE_CODE = Regex("""`([^`]*)`""")

    // One group regardless of how many asterisks wrap the text - **bold**,
    // *italic*, and ***both*** all unwrap the same way. Deliberately not
    // three alternatives with three different groups: replacing with "$1"
    // against a match from the second or third alternative would substitute
    // group 1's EMPTY, unmatched value - silently deleting the text instead
    // of unwrapping it.
    private val BOLD_ITALIC = Regex("""\*{1,3}([^*]+)\*{1,3}""")
    private val LINK = Regex("""\[([^\]]*)]\([^)]*\)""")
    private val HEADING = Regex("""^#{1,6}\s*""")

    /**
     * Finds every complete sentence in `text` starting at `from`, in the
     * order they appear, each paired with how far it consumed (an index
     * into `text` a caller can pass back as the next call's `from`).
     *
     * A period alone does not prove the stream will not continue the same
     * sentence, so a match requires real trailing whitespace too - the same
     * rule the desktop's own sentence-streaming TTS uses.
     */
    fun findSentences(text: String, from: Int): List<Pair<String, Int>> {
        val out = mutableListOf<Pair<String, Int>>()
        var at = from.coerceIn(0, text.length)
        while (true) {
            val m = SENTENCE_BOUNDARY.find(text, at) ?: break
            val sentence = m.groupValues[1].trim()
            at = m.range.last + 1
            if (sentence.isNotEmpty()) out.add(sentence to at)
        }
        return out
    }

    /**
     * A rough pass for speech, not a renderer. A code block is dropped
     * outright rather than read character by character; everything else is
     * unwrapped so the marker itself is never spoken aloud ("asterisk
     * asterisk").
     */
    fun stripMarkdownForSpeech(text: String): String = text
        .replace(CODE_BLOCK, " ")
        .replace(INLINE_CODE, "$1")
        .replace(BOLD_ITALIC, "$1")
        .replace(LINK, "$1")
        .replace(HEADING, "")
        .trim()
}

/**
 * What the phone says about a sentence it did not speak - pure, so the rule
 * is tested (`SpeechTextTest`).
 */
internal object SpokenNotice {

    const val NO_OFFLINE_VOICE =
        "No offline voice on this phone, so it was not spoken aloud. The reply is on screen."

    /**
     * After this phone's own voice was tried for one sentence. Null when it
     * spoke - and null when the owner said "stop" this turn: a stopped voice
     * returns "not spoken" too, and that used to be reported as this phone
     * having no offline voice, which is false and sends the owner looking for
     * a problem that does not exist.
     */
    fun afterOnDevice(spoke: Boolean, stoppedThisTurn: Boolean): String? =
        if (spoke || stoppedThisTurn) null else NO_OFFLINE_VOICE
}
