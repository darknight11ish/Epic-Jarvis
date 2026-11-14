package com.jarvis.client

import java.io.File
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The owner's request of 2026-11-13, in their words: *"can you have it so the
 * notification that says that this action can't be undone times out after 15
 * seconds"*.
 *
 * WHAT IT IS. After an approval is sent, `JarvisRuntime.decide` puts one
 * sentence up: "This cannot be undone." for a card whose `risk.reversible` is
 * `no`, and shorter siblings ("Inbox tidy: 10 minutes to undo.") for the rest.
 * Before this it stayed on screen until something else replaced it.
 *
 * HOW THE 15 SECONDS ARE DRIVEN. Not by sleeping them. `kotlinx-coroutines-test`
 * would have to be a new dependency (the BOM forces it to 1.9.0, and only
 * 1.8.1 is in this machine's offline Gradle cache), so the runtime exposes one
 * seam instead: [JarvisRuntime.undoNoticeWait], a suspend wait that delays for
 * the duration it is handed. [FakeUndoWait] is a tiny virtual clock standing in
 * for it, so the timer is released only when the test advances past its
 * deadline - "still up at 14.9 s, gone at 15.0 s" is deterministic, and the
 * duration production asks for is asserted to be exactly 15,000 ms.
 *
 * WHAT ELSE IS PINNED. A newer, different notice survives an older timer;
 * re-setting the same sentence restarts its 15 seconds (the choice the
 * runtime's own comment documents); and an error notice - which goes through
 * `setNotice`, not this path - opens no timer at all.
 *
 * WHAT IT CANNOT DO. `decide` needs a real card and the desktop behind it, so
 * the behavioural tests drive the exact function `decide` calls
 * ([JarvisRuntime.showUndoNotice]), and one structural assertion keeps that
 * call wired. No device is involved; `phone-unit-tests` runs this suite.
 */
class UndoNoticeTimeoutTest {

    /** The production wait, put back after each test so no seam leaks. */
    private val productionWait = JarvisRuntime.undoNoticeWait

    @After
    fun putTheRuntimeBack() {
        JarvisRuntime.undoNoticeWait = productionWait
        JarvisRuntime.clearNotice()
    }

    /**
     * Joins [timer], failing the test rather than hanging the whole suite if
     * the notice never goes: a broken timer must be a red test, not a CI
     * timeout. Only a broken build ever waits this long; a working one joins
     * immediately.
     */
    private suspend fun joinOrFail(timer: Job) {
        withTimeout(JOIN_TIMEOUT_MS) { timer.join() }
    }

    @Test
    fun `the undo notice is still up at 14 point 9 seconds and gone at 15`() = runBlocking {
        val clock = FakeUndoWait()
        JarvisRuntime.undoNoticeWait = clock::wait

        val timer = JarvisRuntime.showUndoNotice(UNDO)
        assertEquals(
            "production did not ask for a 15-second wait",
            15_000L,
            clock.awaitArmed(),
        )
        assertEquals("the sentence was not put up", UNDO, JarvisRuntime.notice.value)

        clock.advanceBy(14_900)
        assertEquals("the sentence went before its 15 seconds", UNDO, JarvisRuntime.notice.value)

        clock.advanceBy(100)
        joinOrFail(timer)
        assertNull("the sentence was still up at 15.0 seconds", JarvisRuntime.notice.value)
    }

    @Test
    fun `a newer different notice is not wiped by the older timer`() = runBlocking {
        val clock = FakeUndoWait()
        JarvisRuntime.undoNoticeWait = clock::wait

        val timer = JarvisRuntime.showUndoNotice(UNDO)
        clock.awaitArmed()

        clock.advanceBy(5_000)
        JarvisRuntime.setNotice(ERROR)
        assertEquals(ERROR, JarvisRuntime.notice.value)

        // The undo sentence's own deadline arrives while the error is up.
        clock.advanceBy(10_000)
        joinOrFail(timer)
        assertEquals("an old undo timer wiped a newer notice", ERROR, JarvisRuntime.notice.value)
    }

    @Test
    fun `setting the same sentence again restarts its 15 seconds`() = runBlocking {
        val clock = FakeUndoWait()
        JarvisRuntime.undoNoticeWait = clock::wait

        val first = JarvisRuntime.showUndoNotice(UNDO)
        clock.awaitArmed()

        clock.advanceBy(10_000)
        // A second approval, with the same sentence: the owner is owed a full
        // read of it, so the clock starts again.
        val second = JarvisRuntime.showUndoNotice(UNDO)
        assertEquals(15_000L, clock.awaitArmed())
        joinOrFail(first)
        assertTrue("the first timer was not cancelled", first.isCancelled)

        // 15 s after the FIRST set, but only 5 s after the second.
        clock.advanceBy(5_000)
        assertEquals(
            "the first timer took down a sentence that had been set again",
            UNDO,
            JarvisRuntime.notice.value,
        )

        // 15 s after the second set.
        clock.advanceBy(10_000)
        joinOrFail(second)
        assertNull("the restarted 15 seconds never ended", JarvisRuntime.notice.value)
    }

    @Test
    fun `an error notice opens no timer and waits to be dismissed`() = runBlocking {
        val clock = FakeUndoWait()
        JarvisRuntime.undoNoticeWait = clock::wait

        JarvisRuntime.setNotice(ERROR)
        clock.advanceBy(60_000)
        assertEquals("an error notice acquired an undo timeout", ERROR, JarvisRuntime.notice.value)
    }

    @Test
    fun `decide still sends an approved card's undo sentence through the timed path`() {
        // `decide` needs the desktop, so this is the structural half only: the
        // one call that sets the undo notice is the function tested above.
        val src = repoFile(RUNTIME).readText()
        assertTrue(
            "decide no longer routes its undo sentence through showUndoNotice",
            src.contains("undoNoticeFor(item)?.let { showUndoNotice(it) }"),
        )
        assertTrue(
            "the undo sentence was set back to a bare _notice write",
            !src.contains("undoNoticeFor(item)?.let { _notice.value = it }"),
        )
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /**
     * A fake for [JarvisRuntime.undoNoticeWait], and a tiny virtual clock.
     *
     * Production asks for a duration; the fake records the deadline and
     * suspends. [advanceBy] moves the clock and releases the wait only once
     * the deadline is reached, so a test can stand exactly on either side of
     * 15 seconds without a real sleep. [awaitArmed] says when the wait has
     * actually been entered, which is what makes the boundary deterministic
     * rather than a race with the dispatcher.
     */
    private class FakeUndoWait {
        private val lock = Any()
        private val armed = Channel<Long>(Channel.UNLIMITED)
        private var nowMs = 0L
        private var deadlineMs = 0L
        private var gate = CompletableDeferred<Unit>()

        suspend fun wait(ms: Long) {
            val waiting: CompletableDeferred<Unit>
            synchronized(lock) {
                deadlineMs = nowMs + ms
                waiting = CompletableDeferred()
                gate = waiting
            }
            armed.send(ms)
            waiting.await()
        }

        /** The duration production asked for; suspends until the wait is entered. */
        suspend fun awaitArmed(): Long = armed.receive()

        /** Let [ms] of fake time pass, releasing the wait once its deadline is reached. */
        fun advanceBy(ms: Long) {
            val release = synchronized(lock) {
                nowMs += ms
                if (nowMs >= deadlineMs) gate else null
            }
            release?.complete(Unit)
        }
    }

    private companion object {
        const val UNDO = "This cannot be undone."
        const val ERROR = "Could not reach the desktop. Check the connection settings."
        const val RUNTIME = "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt"

        /** Long enough to never trip on a working timer; short enough that a broken one fails. */
        const val JOIN_TIMEOUT_MS = 10_000L
    }
}
