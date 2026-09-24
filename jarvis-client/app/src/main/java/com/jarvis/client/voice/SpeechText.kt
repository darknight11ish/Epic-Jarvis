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
     * Finds every complete piece in `text` starting at `from`, in the order
     * they appear, each paired with how far it consumed (an index into
     * `text` a caller can pass back as the next call's `from`).
     *
     * A piece is a sentence. A period alone does not prove the stream will
     * not continue the same sentence, so a match requires real trailing
     * whitespace too - the same rule the desktop's own sentence-streaming
     * TTS uses.
     *
     * [firstPiece]: nothing of this answer has been cut yet. Then the first
     * piece found may end sooner, at its first comma ([firstCut]), so the
     * phone starts speaking sooner; the pieces after it are sentences.
     */
    fun findSentences(text: String, from: Int, firstPiece: Boolean = false): List<Pair<String, Int>> {
        val out = mutableListOf<Pair<String, Int>>()
        var at = from.coerceIn(0, text.length)
        var first = firstPiece
        while (true) {
            val cut = if (first) {
                firstCut(text, at)
            } else {
                SENTENCE_BOUNDARY.find(text, at)?.let { it.groupValues[1] to it.range.last + 1 }
            } ?: break
            first = false
            val sentence = cut.first.trim()
            at = cut.second
            if (sentence.isNotEmpty()) out.add(sentence to at)
        }
        return out
    }

    // -- The first piece of an answer --------------------------------------
    //
    // The owner's decision of 2026-09-24: "speech starts at the first
    // comma". Making the first sentence's sound is the slowest step before
    // Jarvis says anything, so the FIRST piece of an answer is cut as soon
    // as there is a phrase worth saying:
    //
    //  - at `,` `;` or `:` followed by whitespace (so "1,450" and "10:30"
    //    are never cut), once at least FIRST_PIECE_MIN_CHARS characters come
    //    before it and the word before it is not in AVOID_PAUSE_WORDS;
    //  - at a sentence end, if that comes first;
    //  - or, with no such mark, after FIRST_PIECE_FORCE_WORDS complete words
    //    (at the first one from there that is not in AVOID_PAUSE_WORDS).
    //
    // The SAME rule, numbers and word list as the desktop
    // (jarvis-desktop/src/speech-pieces.js); both apps are held to one list
    // of cases, jarvis-desktop/tests/fixtures/first-piece-cases.json
    // (SpeechTextTest). The idea, the 10 and the word list are from KoljaB's
    // stream2sentence (MIT - THIRD-PARTY-NOTICES.txt); the code is written
    // here.

    /** Characters that must come before a first-piece cut at `,` `;` `:`. */
    const val FIRST_PIECE_MIN_CHARS = 10

    /** Complete words after which the first piece is cut even with no mark. */
    const val FIRST_PIECE_FORCE_WORDS = 12

    /** The marks the first piece may end at, besides a sentence end. */
    const val FIRST_PIECE_MARKS = ",;:"

    /** Words a speaker does not pause after - stream2sentence's
     *  avoid_pause_words.py, in its order, lowercased, each word once. */
    val AVOID_PAUSE_WORDS: List<String> = listOf(
        // conjunctions
        "and", "or", "but", "so", "for", "nor", "yet",
        // prepositions
        "in", "on", "at", "by", "with", "about", "of", "to", "from", "as", "over", "under",
        "through", "between", "during", "there",
        // articles
        "a", "an", "the",
        // possessives and demonstratives
        "my", "your", "his", "her", "its", "our", "their", "this", "that", "these", "those",
        // auxiliary verbs
        "is", "are", "was", "were", "am", "be", "been", "being", "do", "does", "did", "have",
        "has", "had", "can", "could", "shall", "should", "will", "would", "may", "might", "must",
        // pronouns
        "i", "we", "you", "he", "she", "it", "they", "who", "whom", "whose", "which",
        // quantifiers
        "some", "many", "few", "all", "any", "most", "much", "none", "several",
        // adverbs
        "very", "too", "just", "quite", "almost", "nearly", "only",
        // interrogatives
        "what", "where", "when", "why", "how",
        // subordinating conjunctions
        "although", "because", "if", "since", "though", "while", "until", "unless",
    )

    private val AVOID: Set<String> = AVOID_PAUSE_WORDS.toHashSet()
    private val WORD_EDGES = Regex("""^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$""")
    private val SPACES = Regex("[ \t\n\r\u000C\u000B]+")

    /** Whitespace, the same six characters on both apps (Java's `\s`). */
    private fun isSpace(c: Char): Boolean =
        c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\u000C' || c == '\u000B'

    /** The last word of `text`, without the punctuation around it, lowercased. */
    private fun lastWord(text: String): String =
        text.trim().split(SPACES).last().replace(WORD_EDGES, "").lowercase()

    /**
     * The first piece of an answer in `text` from `from`: the piece and how
     * far it reached (trailing whitespace included), or null when none is
     * complete yet.
     */
    internal fun firstCut(text: String, from: Int): Pair<String, Int>? {
        var words = 0
        var i = from
        while (i < text.length - 1) {
            val c = text[i]
            if (!isSpace(c) && isSpace(text[i + 1])) {
                words += 1
                val piece = text.substring(from, i + 1)
                val before = piece.dropLast(1)
                val cut = when {
                    c == '.' || c == '!' || c == '?' -> true
                    c in FIRST_PIECE_MARKS &&
                        before.trim().length >= FIRST_PIECE_MIN_CHARS &&
                        lastWord(before) !in AVOID -> true
                    else -> words >= FIRST_PIECE_FORCE_WORDS && lastWord(piece) !in AVOID
                }
                if (cut) {
                    var end = i + 1
                    while (end < text.length && isSpace(text[end])) end++
                    return piece to end
                }
            }
            i++
        }
        return null
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
