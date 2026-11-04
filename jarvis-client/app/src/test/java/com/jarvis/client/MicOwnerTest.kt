package com.jarvis.client

import com.jarvis.client.voice.MicLedger
import com.jarvis.client.voice.MicOwner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The one microphone ledger: who holds the microphone, and who therefore closes
 * its recorder.
 *
 * This is the whole of "Live and 'hey Jarvis' pause their recorders while the
 * answer window is open and resume after": both of them ask [MicLedger.freeFor]
 * before opening a recorder and while reading, and the hands-free window is the
 * only part that ever HOLDS the microphone. The rules below are what make that
 * safe - a refused acquire never steals it, and a release from a part that does
 * not hold it never frees it for a third.
 */
class MicOwnerTest {

    @Test
    fun `one part holds it at a time, and the second is refused rather than queued`() {
        val mic = MicLedger()
        assertNull("nobody holds it to begin with", mic.holder())
        assertTrue(mic.freeFor(MicOwner.LIVE))

        assertTrue(mic.acquire(MicOwner.HANDSFREE))
        assertEquals(MicOwner.HANDSFREE, mic.holder())

        // Live and the wake word ask; they never take. Both are told no, and
        // neither can disturb the holder.
        assertFalse(mic.freeFor(MicOwner.LIVE))
        assertFalse(mic.freeFor(MicOwner.WAKE))
        assertFalse(mic.freeFor(MicOwner.TALK))
        assertFalse("a plain listener cannot take it either", mic.acquire(MicOwner.LIVE))
        assertEquals("and nothing changed", MicOwner.HANDSFREE, mic.holder())
    }

    @Test
    fun `the holder may ask again - a double acquire is harmless`() {
        val mic = MicLedger()
        assertTrue(mic.acquire(MicOwner.HANDSFREE))
        assertTrue(mic.acquire(MicOwner.HANDSFREE))
        assertEquals(MicOwner.HANDSFREE, mic.holder())
        assertTrue(mic.freeFor(MicOwner.HANDSFREE))
    }

    @Test
    fun `a release from a part that does not hold it is a no-op, not a free`() {
        val mic = MicLedger()
        mic.acquire(MicOwner.HANDSFREE)
        // A service shutting down releases "its own" microphone in a finally;
        // if that freed another part's, a third could start recording over it.
        mic.release(MicOwner.LIVE)
        mic.release(MicOwner.WAKE)
        mic.release(MicOwner.TALK)
        assertEquals(MicOwner.HANDSFREE, mic.holder())
        assertFalse(mic.freeFor(MicOwner.LIVE))

        mic.release(MicOwner.HANDSFREE)
        assertNull(mic.holder())
        assertTrue("Live may open its recorder again", mic.freeFor(MicOwner.LIVE))
        assertTrue(mic.acquire(MicOwner.LIVE))
    }

    @Test
    fun `every owner has its own name, so two parts cannot collide`() {
        assertEquals(MicOwner.ALL.size, MicOwner.ALL.toSet().size)
        assertEquals(4, MicOwner.ALL.size)
        // The one that holds, and the three that ask. Nothing else.
        assertTrue(MicOwner.HANDSFREE in MicOwner.ALL)
        assertTrue(MicOwner.LIVE in MicOwner.ALL)
        assertTrue(MicOwner.WAKE in MicOwner.ALL)
        assertTrue(MicOwner.TALK in MicOwner.ALL)
        for (name in MicOwner.ALL) assertTrue(name.isNotBlank())
    }
}
