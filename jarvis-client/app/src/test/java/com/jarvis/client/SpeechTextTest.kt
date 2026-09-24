package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.voice.SpeechText
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The pure text-shaping half of sentence-streaming TTS on Android -
 * [SpeechText.findSentences] and [SpeechText.stripMarkdownForSpeech].
 *
 * Written after finding a real bug by hand while writing the code: an
 * earlier draft of the markdown-stripping regex used three alternatives
 * (`***x***|**x**|*x*`) with three different capture groups but a
 * replacement that only ever substituted group 1 - so a match from the
 * second or third alternative substituted group 1's EMPTY value, silently
 * DELETING `**bold**` and `*italic*` text instead of unwrapping it. Fixed to
 * one alternative with one group before this test existed; the case below
 * is what would have caught it.
 */
class SpeechTextTest {

    private fun sentences(text: String, from: Int = 0) = SpeechText.findSentences(text, from)

    @Test
    fun `a single finished sentence is found once`() {
        val found = sentences("First sentence. ")
        assertEquals(listOf("First sentence." to 16), found)
    }

    @Test
    fun `two sentences in one call are both found in order`() {
        val found = sentences("One. Two. ")
        assertEquals(listOf("One." to 5, "Two." to 10), found)
    }

    @Test
    fun `punctuation alone with no trailing whitespace is not a boundary yet`() {
        // The stream may simply not have produced the next character.
        assertTrue(sentences("Wait for it.").isEmpty())
    }

    @Test
    fun `a decimal point does not end the sentence early`() {
        val found = sentences("Pi is about 3.14 and that is all. ")
        assertEquals(1, found.size)
        assertEquals("Pi is about 3.14 and that is all.", found[0].first)
    }

    @Test
    fun `resuming from a previous cursor only reports what is new`() {
        // Simulates the real call pattern: `speakStreamed` calls this again
        // on the GROWING buffer, each time starting from the cursor the
        // previous call returned - never re-finding a sentence already sent
        // to the speech queue once.
        val partial = "One. Two. "
        val first = sentences(partial)
        assertEquals(listOf("One." to 5, "Two." to 10), first)

        val whole = "One. Two. Three. "
        val rest = sentences(whole, first.last().second)
        assertEquals(listOf("Three." to whole.length), rest)
    }

    @Test
    fun `an empty or blank input finds nothing`() {
        assertTrue(sentences("").isEmpty())
        assertTrue(sentences("   ").isEmpty())
    }

    @Test
    fun `a starting cursor past the end of the text finds nothing rather than crashing`() {
        assertTrue(sentences("Short.", from = 500).isEmpty())
        assertTrue(SpeechText.findSentences("Short, yes", 500, firstPiece = true).isEmpty())
    }

    // -- The first piece: speech starts at the first comma ------------------
    //
    // The cases are `jarvis-desktop/tests/fixtures/first-piece-cases.json`,
    // the same file the desktop's tests/speech-pieces.mjs reads, found by
    // walking up from Gradle's working folder - one copy, so the two apps
    // cannot drift apart.

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val fixture: JsonObject by lazy {
        JarvisJson.parseToJsonElement(
            repoFile("jarvis-desktop/tests/fixtures/first-piece-cases.json").readText(),
        ).jsonObject
    }

    /** What VoiceSession.speakStreamed does as an answer streams in, `step`
     *  characters at a time, then at its end: the pieces, trimmed. */
    private fun speak(text: String, step: Int): List<String> {
        val out = mutableListOf<String>()
        var spokenUpTo = 0
        var end = minOf(step, text.length)
        while (true) {
            val soFar = text.substring(0, end)
            for ((piece, consumedTo) in SpeechText.findSentences(soFar, spokenUpTo, spokenUpTo == 0)) {
                spokenUpTo = consumedTo
                out.add(piece)
            }
            if (end >= text.length) break
            end = minOf(text.length, end + step)
        }
        val rest = if (spokenUpTo <= text.length) text.substring(spokenUpTo).trim() else ""
        if (rest.isNotEmpty()) out.add(rest)
        return out
    }

    @Test
    fun `the numbers and the word list are the ones the desktop uses`() {
        assertEquals(fixture["min_chars"]!!.jsonPrimitive.int, SpeechText.FIRST_PIECE_MIN_CHARS)
        assertEquals(fixture["force_words"]!!.jsonPrimitive.int, SpeechText.FIRST_PIECE_FORCE_WORDS)
        assertEquals(fixture["marks"]!!.jsonPrimitive.content, SpeechText.FIRST_PIECE_MARKS)
        assertEquals(
            fixture["avoid_pause_words"]!!.jsonArray.map { it.jsonPrimitive.content },
            SpeechText.AVOID_PAUSE_WORDS,
        )
    }

    @Test
    fun `every shared case is cut the same, all at once and one character at a time`() {
        val cases = fixture["cases"]!!.jsonArray
        assertTrue("found the shared cases", cases.size >= 10)
        for (case in cases) {
            val c = case.jsonObject
            val name = c["name"]!!.jsonPrimitive.content
            val text = c["text"]!!.jsonPrimitive.content
            val want = c["pieces"]!!.jsonArray.map { it.jsonPrimitive.content }
            assertEquals("$name (all at once)", want, speak(text, maxOf(1, text.length)))
            assertEquals("$name (one character at a time)", want, speak(text, 1))
        }
    }

    @Test
    fun `only the first piece may end at a comma`() {
        val text = "Tomorrow looks mild, with rain, and wind. "
        assertEquals(
            listOf("Tomorrow looks mild," to 21, "with rain, and wind." to text.length),
            SpeechText.findSentences(text, 0, firstPiece = true),
        )
        // Without firstPiece - the old call - the same text is one sentence.
        assertEquals(listOf("Tomorrow looks mild, with rain, and wind." to text.length), sentences(text))
    }

    @Test
    fun `the voice session asks for the first piece while nothing is cut yet`() {
        val kt = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/voice/VoiceSession.kt",
        ).readText()
        assertTrue(kt.contains("val firstPiece = spokenUpTo == 0"))
        assertTrue(kt.contains("SpeechText.findSentences(soFar, spokenUpTo, firstPiece)"))
    }

    // --------------------------------------------------- markdown cleanup ---

    private fun clean(text: String) = SpeechText.stripMarkdownForSpeech(text)

    @Test
    fun `bold text is unwrapped, not deleted`() {
        assertEquals("This is bold text.", clean("This is **bold** text."))
    }

    @Test
    fun `italic text is unwrapped, not deleted`() {
        assertEquals("This is italic text.", clean("This is *italic* text."))
    }

    @Test
    fun `bold italic text is unwrapped, not deleted`() {
        assertEquals("This is emphatic text.", clean("This is ***emphatic*** text."))
    }

    @Test
    fun `inline code is unwrapped`() {
        assertEquals("Run make build to build it.", clean("Run `make build` to build it."))
    }

    @Test
    fun `a code block is dropped rather than read character by character`() {
        val out = clean("Here you go: ```const x = 1;``` done.")
        assertTrue(!out.contains("const x"))
    }

    @Test
    fun `a link speaks its label, not its url`() {
        assertEquals(
            "See the docs for more.",
            clean("See [the docs](https://example.com/docs) for more."),
        )
    }

    @Test
    fun `a heading marker is dropped`() {
        assertEquals("Summary", clean("## Summary"))
    }

    @Test
    fun `plain text with no markdown is unchanged`() {
        assertEquals("Nothing special here.", clean("Nothing special here."))
    }

    /** T6: after "stop", a sentence not spoken is not blamed on a missing voice. */
    @Test
    fun `no offline voice is said only when the phone's voice really failed`() {
        assertEquals(
            com.jarvis.client.voice.SpokenNotice.NO_OFFLINE_VOICE,
            com.jarvis.client.voice.SpokenNotice.afterOnDevice(spoke = false, stoppedThisTurn = false),
        )
        assertEquals(null, com.jarvis.client.voice.SpokenNotice.afterOnDevice(spoke = false, stoppedThisTurn = true))
        assertEquals(null, com.jarvis.client.voice.SpokenNotice.afterOnDevice(spoke = true, stoppedThisTurn = false))
    }
}
