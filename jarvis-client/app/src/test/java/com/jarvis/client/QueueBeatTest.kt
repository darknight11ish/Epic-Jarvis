package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The phone's fallback queue read (the owner's report of 2026-10-29): *"no stale
 * card left showing, no dead Approve/Deny on a resolved card."*
 *
 * Every Android surface - the home-screen approval widget, the notification,
 * Home's card, the Inbox plate - draws from `JarvisRuntime.pending`, and before
 * this the only thing that ever re-assigned it was the PC's `approval` event. A
 * doorbell that is missed leaves a decided card on the lock screen for ever, so
 * `JarvisRuntime` now re-reads the queue on a 30-second beat while a card is
 * waiting on a link that can answer. [QueueBeat] is that decision on its own,
 * because the runtime is a singleton built from a `Context` and cannot be
 * constructed in a JVM test.
 *
 * Four cases, and the two that must be FALSE matter as much as the two that
 * must be true: a beat that fired on an empty queue would be a poll of the
 * owner's PC every 30 seconds for nothing, and one that fired on a dead link
 * would replace a card with "Could not re-read what is waiting" over a queue
 * that is fine.
 */
class QueueBeatTest {

    @Test
    fun `a card waiting on a live link is re-read`() {
        assertTrue(
            "this is the whole case: something is on the home screen and the PC can be asked",
            QueueBeat.due(waiting = 1, connected = true),
        )
        assertTrue(QueueBeat.due(waiting = 4, connected = true))
    }

    @Test
    fun `an empty queue is never asked about`() {
        // Nothing is drawn from the queue, so there is nothing a stale read could
        // hold open. This is what keeps the beat from being a poll.
        assertFalse(QueueBeat.due(waiting = 0, connected = true))
    }

    @Test
    fun `a link that is down is left to its own recovery`() {
        // `refreshPending`'s failure arm sets `stale` and a notice, so asking on
        // a dead line would turn a phone with no signal into one that says
        // "Could not re-read what is waiting" every 30 seconds.
        assertFalse(QueueBeat.due(waiting = 1, connected = false))
        assertFalse(QueueBeat.due(waiting = 0, connected = false))
        assertFalse(QueueBeat.due(waiting = 9, connected = false))
    }

    @Test
    fun `the beat is the same thirty seconds the desktop's safety net uses`() {
        // `jarvis_hud.html`'s `setInterval(() => apprPoll(), 30000)` and
        // `stream.rs`'s `QUEUE_BEAT` are the other two halves. One number, so
        // "how stale can a card be" has one answer across the three surfaces.
        assertTrue(
            "the beat must not be slower than the desktop's: ${QueueBeat.EVERY_MS}",
            QueueBeat.EVERY_MS == 30_000L,
        )
        assertTrue(
            "and not a busy loop either",
            QueueBeat.EVERY_MS >= 10_000L,
        )
    }

    // ------------------------------------------------------- the wiring ----

    /**
     * The rule above decides nothing on its own: `JarvisRuntime` is the thing
     * that runs it, and there is no way to construct that singleton (it takes a
     * `Context` and starts collectors) in a JVM test. So this is a SOURCE test
     * and says so, the same shape `ApprovalDecisionTest` uses for its own
     * finding - the closure that clears the card's flag cannot be reached
     * off-device either.
     *
     * Comments are stripped before anything is looked for, so no assertion here
     * can be satisfied by a comment naming the same thing on purpose.
     */
    @Test
    fun `the runtime runs the beat and does not stack a second one`() {
        val src = code(repoFile("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt").readText())
        assertTrue(
            "nothing starts the beat - every surface is back to the event only",
            src.contains("queueBeat = scope.launch {"),
        )
        assertTrue(
            "the beat must not be re-created beside a running one on a restart",
            src.contains("queueBeat?.cancel()"),
        )
        assertTrue(
            "the wait must be QueueBeat's, not a number typed here",
            src.contains("delay(QueueBeat.EVERY_MS)"),
        )
        assertTrue(
            "and it must ask the rule rather than re-read unconditionally",
            src.contains("QueueBeat.due("),
        )
        // The read itself must be refreshPending - the ONE assignment of
        // `pending` every Android surface draws from.
        val fromBeat = src.substringAfter("queueBeat = scope.launch {")
        val loop = fromBeat.substringBefore("\n        }")
        assertTrue(
            "the beat must re-read through refreshPending, the one queue read",
            loop.contains("refreshPending()"),
        )
    }

    private fun repoFile(rel: String): File {
        var d: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (d != null) {
            val f = File(d, rel)
            if (f.isFile) return f
            d = d.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** Comments become empty lines, so a comment cannot satisfy an assertion. */
    private fun code(text: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in text.lines()) {
            val t = line.trimStart()
            if (inBlock) {
                if (t.contains("*/")) inBlock = false
                out.add("")
                continue
            }
            if (t.startsWith("/*")) {
                if (!t.contains("*/")) inBlock = true
                out.add("")
                continue
            }
            if (t.startsWith("//")) {
                out.add("")
                continue
            }
            out.add(line)
        }
        return out.joinToString("\n")
    }
}
