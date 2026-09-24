package com.jarvis.client.net

import java.util.Locale

/**
 * Where the words in one user message came from - the `provenance` field on
 * each `role: "user"` message of `POST /api/chat` (docs/JARVIS-API.md
 * section 18, "Chat history", added 2026-09-24).
 *
 * WHY. The PC now keeps a record of each chat (chat history, on by default),
 * and the automatic learning built after it will learn facts about the owner
 * from the owner's OWN words only - never from something shared from another
 * app, pasted in, or read off a web page. So each message says where it came
 * from, and the PC records that with it. A message with no tag, or a tag the
 * PC does not know, is treated as "not the owner's own words" (fail closed),
 * so getting this wrong in the careful direction costs nothing but a fact
 * Jarvis does not learn.
 *
 * The phone's tags:
 * - [TYPED] - typed into the chat box.
 * - [PASTED] - the box got more than [PASTE_CHARS] characters in ONE edit
 *   since it was last empty: a paste, a clipboard chip, a keyboard's
 *   "insert" of a long snippet. Typing never does that - one key, one
 *   autocorrect or one suggestion is a word at a time.
 * - [VOICE] - the transcript the PC's own speech route gave back for this
 *   turn. The PC checks this against its own recent transcripts and records
 *   a claimed voice turn it does not recognise as "voice_unverified".
 * - [SHARED] - text another app handed over through Android's Share sheet.
 *   Sent as its own message, before the owner's typed one, never mixed in.
 * - [PICTURE_CAPTION] - the words sent alongside a picture.
 *
 * The desktop also has "clipboard" (its hotkey prefill). The phone has no
 * such path, so it never sends it.
 *
 * Pure Kotlin, no Android types, so the rules run in a plain JVM test
 * (`ProvenanceTest`).
 */
object Provenance {
    const val TYPED = "typed"
    const val VOICE = "voice"
    const val SHARED = "shared"
    const val PASTED = "pasted"
    const val PICTURE_CAPTION = "picture_caption"

    /** More than this many characters arriving in one edit is a paste, not typing. */
    const val PASTE_CHARS = 40

    /**
     * How many characters one edit put into the box: [after] minus what it
     * kept of [before] at the start and at the end. A paste in the middle of
     * a sentence counts only the pasted part; a paste over a selection counts
     * the whole paste; a deletion counts nothing.
     */
    fun inserted(before: String, after: String): Int {
        val most = minOf(before.length, after.length)
        var head = 0
        while (head < most && before[head] == after[head]) head++
        var tail = 0
        while (tail < most - head &&
            before[before.length - 1 - tail] == after[after.length - 1 - tail]
        ) {
            tail++
        }
        return (after.length - head - tail).coerceAtLeast(0)
    }

    /**
     * Whether the box counts as pasted into after one edit, from [before] to
     * [after]. Once pasted, it stays pasted until the box is empty again -
     * editing a pasted paragraph does not make it the owner's own words. An
     * empty box starts over.
     */
    fun pastedAfter(wasPasted: Boolean, before: String, after: String): Boolean = when {
        after.isEmpty() -> false
        wasPasted -> true
        else -> inserted(before, after) > PASTE_CHARS
    }

    /** The chat box's own tag. A picture's words are tagged by [ChatHistory.asking]. */
    fun forComposer(pasted: Boolean): String = if (pasted) PASTED else TYPED

    /**
     * Text shared from another app while some is already held: kept, both of
     * them, in the order they arrived. A share must never eat an earlier one.
     */
    fun joinShared(held: String?, incoming: String): String =
        if (held.isNullOrBlank()) incoming else "$held\n\n$incoming"

    /** The chip above the chat box: "Shared text · 1,204 characters". */
    fun sharedLine(text: String): String {
        val n = text.length
        val count = String.format(Locale.US, "%,d", n)
        return "Shared text · $count ${if (n == 1) "character" else "characters"}"
    }
}
