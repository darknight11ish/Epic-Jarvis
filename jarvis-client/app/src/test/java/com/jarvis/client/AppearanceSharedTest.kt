package com.jarvis.client

import com.jarvis.client.AppearanceShared.Status
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [AppearanceShared]: the Appearance screen's sentences about the part it
 * shares with the desktop follow the SEND, not a capability flag.
 *
 * UI audit 2026-10-05, finding A1 - "the project's worst case: a claim that is
 * not true". The screen said the face and the state colours "are sent to your
 * desktop" whenever the backend had the `appearance` capability, while
 * `JarvisRuntime.pushAppearance` called `api.postAppearance(...)` and never
 * read the `ApiResult` it got back. Each test below fails if the capability
 * flag is put back in charge of that sentence.
 */
class AppearanceSharedTest {

    @Test
    fun `the capability alone never earns the claim`() {
        // The exact reverted shape: `capability = true`, no send result known.
        assertEquals(Status.MAYBE_NEXT, AppearanceShared.statusOf(capability = true, sendOk = null))
        assertFalse(
            "a phone that has not sent anything must not say 'are sent'",
            AppearanceShared.groupWords(Status.MAYBE_NEXT).contains("are sent"),
        )
    }

    @Test
    fun `only a send that landed says the desktop has it`() {
        assertEquals(Status.SENT, AppearanceShared.statusOf(capability = true, sendOk = true))
        assertTrue(AppearanceShared.groupWords(Status.SENT).contains("are sent to your desktop"))
    }

    @Test
    fun `a send that failed says so in plain words, and does not claim it arrived`() {
        assertEquals(Status.NOT_SENT, AppearanceShared.statusOf(capability = true, sendOk = false))
        val words = AppearanceShared.groupWords(Status.NOT_SENT)
        assertFalse(words.contains("are sent"))
        assertTrue("says plainly it did not go: $words", words.startsWith("Not sent to your desktop"))
        assertTrue("says where the change is instead: $words", words.contains("on this phone only"))
        assertTrue("still promises the retry: $words", words.contains("next time a change is made"))
    }

    @Test
    fun `a backend without the route says the desktop does not support it yet`() {
        assertEquals(Status.UNSUPPORTED, AppearanceShared.statusOf(capability = false, sendOk = null))
        // Even a stale "it sent once" cannot beat a backend that has no route now.
        assertEquals(Status.UNSUPPORTED, AppearanceShared.statusOf(capability = false, sendOk = true))
        assertTrue(
            AppearanceShared.groupWords(Status.UNSUPPORTED)
                .contains("your desktop doesn't support it yet"),
        )
    }

    @Test
    fun `exactly one status is allowed to claim a send, and it is the one that landed`() {
        val all = Status.entries.map { AppearanceShared.groupWords(it) }
        val claiming = all.filter { it.contains("are sent") }
        assertEquals("one, and one only", 1, claiming.size)
        assertTrue(claiming.single().contains("desktop"))
        // Every other sentence says the change did not reach the desktop.
        for (status in Status.entries - Status.SENT) {
            val words = AppearanceShared.groupWords(status)
            assertFalse("$status: $words", words.contains("are sent"))
            assertTrue("$status must say it is not there: $words", words.contains("Not "))
        }
    }

    @Test
    fun `the undo line never promises a send that cannot happen`() {
        // After a failed send, the group above already says it; a second
        // sentence repeating it is noise.
        assertNull(AppearanceShared.undoLineSuffix(Status.NOT_SENT))
        assertNull(AppearanceShared.undoLineSuffix(Status.UNSUPPORTED))
        // Before anything is sent the promise is still true: the window's
        // close is what sends it.
        assertNotNull(AppearanceShared.undoLineSuffix(Status.MAYBE_NEXT))
        assertTrue(AppearanceShared.undoLineSuffix(Status.MAYBE_NEXT)!!.contains("when this goes away"))
        assertTrue(AppearanceShared.undoLineSuffix(Status.SENT)!!.contains("Sent to your desktop"))
    }

    @Test
    fun `the face editor is told the desktop takes the shared part only when it does`() {
        assertTrue(AppearanceShared.capabilityOf(Status.SENT))
        assertTrue(AppearanceShared.capabilityOf(Status.MAYBE_NEXT))
        assertFalse(AppearanceShared.capabilityOf(Status.UNSUPPORTED))
        // Cannot tell a refused send from a missing route: says no.
        assertFalse(AppearanceShared.capabilityOf(Status.NOT_SENT))
    }
}
