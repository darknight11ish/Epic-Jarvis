package com.jarvis.client

import com.jarvis.client.net.Provenance
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Where the chat box's words came from - `net/Provenance.kt`, for the PC's
 * chat history (docs/JARVIS-API.md section 18). The rule the phone keeps:
 * one edit that put more than 40 characters into the box is a paste, and the
 * box stays "pasted" until it is empty again.
 */
class ProvenanceTest {

    /** Types [text] one character at a time, the way a keyboard does. */
    private fun typed(text: String, start: String = ""): Pair<String, Boolean> {
        var box = start
        var pasted = false
        for (c in text) {
            val next = box + c
            pasted = Provenance.pastedAfter(pasted, box, next)
            box = next
        }
        return box to pasted
    }

    @Test
    fun `typing a long message a key at a time is typed`() {
        val (box, pasted) = typed("This is a long message typed one key at a time, well over forty characters.")
        assertFalse(pasted)
        assertEquals(Provenance.TYPED, Provenance.forComposer(pasted))
        assertTrue(box.length > 40)
    }

    @Test
    fun `forty characters at once is still typing, forty-one is a paste`() {
        val forty = "x".repeat(Provenance.PASTE_CHARS)
        assertFalse(Provenance.pastedAfter(false, "", forty))
        assertTrue(Provenance.pastedAfter(false, "", forty + "y"))
        assertEquals(Provenance.PASTED, Provenance.forComposer(true))
    }

    @Test
    fun `a paste in the middle counts only what was pasted`() {
        val before = "Hello  there"
        val paste = "p".repeat(41)
        val after = "Hello $paste there"
        assertEquals(41, Provenance.inserted(before, after))
        assertTrue(Provenance.pastedAfter(false, before, after))
        // A short one in the middle is not a paste.
        assertEquals(5, Provenance.inserted(before, "Hello world there"))
    }

    @Test
    fun `a paste over a selection counts the whole paste`() {
        val before = "replace ALL OF THIS please"
        val paste = "q".repeat(45)
        val after = "replace $paste please"
        assertEquals(45, Provenance.inserted(before, after))
    }

    @Test
    fun `a deletion inserts nothing, and an autocorrect is a word`() {
        assertEquals(0, Provenance.inserted("hello world", "hello"))
        assertEquals(0, Provenance.inserted("hello", "hello"))
        assertEquals(2, Provenance.inserted("I think teh cat", "I think the cat"))
        assertEquals(9, Provenance.inserted("I think ", "I think tomorrow "))
    }

    @Test
    fun `repeated characters at the join are not counted twice`() {
        // "aaa" + "a" x 41: head and tail overlap; must not go negative or double up.
        val before = "aaa"
        val after = "a".repeat(44)
        assertEquals(41, Provenance.inserted(before, after))
    }

    @Test
    fun `once pasted it stays pasted while the owner edits, until the box is empty`() {
        var pasted = Provenance.pastedAfter(false, "", "z".repeat(60))
        assertTrue(pasted)
        pasted = Provenance.pastedAfter(pasted, "z".repeat(60), "z".repeat(59))
        assertTrue("an edit after a paste does not make it typed", pasted)
        pasted = Provenance.pastedAfter(pasted, "z".repeat(59), "")
        assertFalse("an empty box starts over", pasted)
        val (_, again) = typed("now typed by hand, a character at a time, long enough")
        assertFalse(again)
    }

    @Test
    fun `typing more after a paste keeps it pasted`() {
        val paste = "w".repeat(50)
        val first = Provenance.pastedAfter(false, "", paste)
        var box = paste
        var pasted = first
        for (c in " and my own words") {
            val next = box + c
            pasted = Provenance.pastedAfter(pasted, box, next)
            box = next
        }
        assertTrue(pasted)
    }

    @Test
    fun `the shared chip says how much, with the thousands marked`() {
        assertEquals("Shared text · 1,204 characters", Provenance.sharedLine("s".repeat(1204)))
        assertEquals("Shared text · 1 character", Provenance.sharedLine("s"))
        assertEquals("Shared text · 12 characters", Provenance.sharedLine("s".repeat(12)))
    }

    @Test
    fun `a second share joins the first rather than replacing it`() {
        assertEquals("one", Provenance.joinShared(null, "one"))
        assertEquals("one", Provenance.joinShared("  ", "one"))
        assertEquals("one\n\ntwo", Provenance.joinShared("one", "two"))
    }

    @Test
    fun `the tags are exactly the contract's words`() {
        assertEquals(
            listOf("typed", "voice", "shared", "pasted", "picture_caption"),
            listOf(
                Provenance.TYPED,
                Provenance.VOICE,
                Provenance.SHARED,
                Provenance.PASTED,
                Provenance.PICTURE_CAPTION,
            ),
        )
    }
}
