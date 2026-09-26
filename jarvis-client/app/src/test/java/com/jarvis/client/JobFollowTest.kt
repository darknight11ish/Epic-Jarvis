package com.jarvis.client

import com.jarvis.client.net.JobFollow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Following a note or wiki job (audit CONN-8): one failed poll used to end
 * the follow for good with "Lost track of it".
 */
class JobFollowTest {

    @Test
    fun `it takes three failures in a row to give up`() {
        assertEquals(3, JobFollow.TOLERATED_FAILURES)
        val f = JobFollow()
        assertFalse(f.failed())
        assertFalse(f.failed())
        assertTrue("the third in a row ends it", f.failed())
    }

    @Test
    fun `an answer in between starts the count again`() {
        val f = JobFollow()
        assertFalse(f.failed())
        assertFalse(f.failed())
        f.answered()
        assertFalse(f.failed())
        assertFalse(f.failed())
        assertTrue(f.failed())
    }

    @Test
    fun `while the link is down nothing is asked, and nothing is counted`() {
        val f = JobFollow()
        assertFalse(f.shouldPoll(linkUp = false))
        assertTrue(f.shouldPoll(linkUp = true))
        // Skipped polls are not failures: two real failures after a long
        // outage still leave the follow going.
        repeat(20) { f.shouldPoll(linkUp = false) }
        assertFalse(f.failed())
        assertFalse(f.failed())
    }
}
