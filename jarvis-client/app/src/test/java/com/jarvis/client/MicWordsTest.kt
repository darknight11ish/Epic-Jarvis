package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [MicWords]: the talk button never does nothing in silence.
 *
 * The owner's report of 2026-10-13 - "the mic button ... doesnt work if i tap
 * it or hold it down" - was a greyed button with no sentence anywhere. Each
 * reason it can be greyed has words, and each of the four is reachable and
 * different from the others, so a change that collapses two reasons into one
 * (or into null) fails here rather than on his phone.
 */
class MicWordsTest {

    private fun held(
        link: LinkState = LinkState.CONNECTED,
        streaming: Boolean = false,
        micAllowed: Boolean = true,
        voiceOffered: Boolean = true,
    ) = MicWords.heldLine(link, streaming, micAllowed, voiceOffered)

    @Test
    fun `a microphone that can be used has no line at all`() {
        assertNull(held())
    }

    @Test
    fun `every reason the button can be greyed is named, and the four differ`() {
        // CONTROL: the healthy case is null, so a change that always returns a
        // sentence (or always null) is caught by the test above and this one.
        val reasons = listOf(
            held(link = LinkState.OFFLINE) to "link down",
            held(link = LinkState.RECONNECTING) to "link reconnecting",
            held(streaming = true) to "an answer is streaming",
            held(micAllowed = false) to "the microphone is not allowed",
            held(voiceOffered = false) to "the PC has not offered push-to-talk",
        )
        for ((line, what) in reasons) {
            assertNotNull("$what produced no sentence - the owner taps and nothing says why", line)
            assertTrue("$what gave an empty sentence", line!!.isNotBlank())
        }
        // The four distinct causes say four distinct things: a line that is a
        // copy of another would be right about one of them and wrong about the
        // rest.
        val distinct = setOf(
            held(link = LinkState.OFFLINE),
            held(streaming = true),
            held(micAllowed = false),
            held(voiceOffered = false),
        )
        assertEquals("two different reasons share one sentence", 4, distinct.size)
    }

    @Test
    fun `the link is the first reason a tap meets, and its words are the shared ones`() {
        // The link's sentence is not new prose: it is the one every other
        // plate shows under a control greyed for the link.
        assertEquals(
            LinkWords.composerHeldLine(LinkState.OFFLINE),
            held(link = LinkState.OFFLINE),
        )
        // And the link outranks the rest, because nothing can be sent anyway.
        assertEquals(
            LinkWords.composerHeldLine(LinkState.OFFLINE),
            held(link = LinkState.OFFLINE, streaming = true, micAllowed = false, voiceOffered = false),
        )
    }

    @Test
    fun `on a live link each of the other three is reached in its own turn`() {
        // A denied permission is named before streaming: it is the one the
        // owner has to fix, and Android shows no dialog for it any more.
        assertEquals(MicWords.NO_PERMISSION, held(streaming = true, micAllowed = false))
        assertEquals(MicWords.ANSWERING, held(streaming = true))
        assertEquals(MicWords.NOT_OFFERED, held(voiceOffered = false))
        // An offered voice beats nothing: with all four clear there is no line.
        assertNull(held(voiceOffered = true))
    }

    @Test
    fun `the microphone line points at the place that can fix it`() {
        // The voice reason has to send the owner somewhere real, or it is a
        // second dead end; the permission reason has to name Android's
        // settings, because the app cannot ask again after a permanent denial.
        assertTrue(MicWords.NOT_OFFERED.contains("Train my voice"))
        assertTrue(MicWords.NO_PERMISSION.contains("settings"))
        assertTrue(MicWords.ANSWERING.contains("Stop"))
    }
}
