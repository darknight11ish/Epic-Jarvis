package com.jarvis.client

import com.jarvis.client.voice.SpeechText
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

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
}
