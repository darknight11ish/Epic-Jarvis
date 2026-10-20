package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * MainActivity is exported (it is the launcher), so any app on the phone can
 * send it intents. 2026-10-20 Android audit, Area 10C: a sensitive action must
 * never run straight from an untrusted Intent's extras.
 *
 * The rules checked here:
 *  - Live START / RESUME and the handoff screen require [InternalLaunch]'s
 *    proof, which only this app's own PendingIntents can carry;
 *  - without proof they only open a screen, where the owner presses Start;
 *  - the widget's Mic tap only opens Home - it never opens the microphone;
 *  - a share into Live only opens the Live screen now (the audit fix: it used
 *    to auto-start Live);
 *  - an approval notification's id only focuses that card - it approves
 *    nothing.
 */
class MainActivityLaunchTest {

    private fun source(rel: String): String =
        SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/$rel")

    private fun block(src: String, start: String, end: String): String {
        val i = src.indexOf(start)
        assertTrue("missing $start", i >= 0)
        val j = src.indexOf(end, i + start.length)
        assertTrue("missing $end after $start", j >= 0)
        return src.substring(i, j)
    }

    @Test
    fun `live and handoff launches require this app's own proof`() {
        val src = source("MainActivity.kt")
        for (fn in listOf("readLiveIntent", "readHandoffIntent")) {
            val body = block(src, "private fun $fn(", "private fun ")
            assertTrue("$fn must use InternalLaunch.decide", body.contains("InternalLaunch.decide("))
            assertTrue("$fn must pass the proof extra", body.contains("InternalLaunch.EXTRA_PROOF"))
        }
        // Without the proof, START/RESUME fall back to just opening the screen,
        // and the handoff is ignored entirely.
        assertEquals(
            InternalLaunch.Launch.OPEN_LIVE_SCREEN,
            InternalLaunch.decide(MainActivity.ACTION_START_LIVE, null, "x", true),
        )
        assertEquals(
            InternalLaunch.Launch.OPEN_LIVE_SCREEN,
            InternalLaunch.decide(MainActivity.ACTION_RESUME_LIVE, null, "x", true),
        )
        assertEquals(
            InternalLaunch.Launch.IGNORE,
            InternalLaunch.decide(MainActivity.ACTION_OPEN_HANDOFF, null, "x", true),
        )
        assertEquals(
            InternalLaunch.Launch.START_LIVE,
            InternalLaunch.decide(MainActivity.ACTION_START_LIVE, "x", "x", true),
        )
        assertEquals(
            InternalLaunch.Launch.OPEN_HANDOFF,
            InternalLaunch.decide(MainActivity.ACTION_OPEN_HANDOFF, "x", "x", false),
        )
    }

    @Test
    fun `the widget Mic intent only opens Home and never the microphone`() {
        val src = source("MainActivity.kt")
        val body = block(
            src,
            "LaunchedEffect(startVoiceRequested.value) {",
            "LaunchedEffect(",
        )
        assertTrue(body.contains("nav.resetTo(Screen.HOME)"))
        assertFalse("the Mic intent must not open the microphone", body.contains("beginVoice"))
        assertFalse(body.contains("liveStartSoon"))
    }

    @Test
    fun `a share into Live opens the screen but does not auto-start Live`() {
        val src = source("MainActivity.kt")
        val body = block(src, "LaunchedEffect(liveSharedText.value) {", "LaunchedEffect(")
        assertTrue(body.contains("nav.go(Screen.LIVE)"))
        assertFalse(
            "an untrusted share Intent must not start Live (microphone) by itself",
            body.contains("startLiveRequested"),
        )
        assertFalse(body.contains("liveStartSoon"))
    }

    @Test
    fun `an approval notification's extra only focuses the card`() {
        val src = source("MainActivity.kt")
        val body = block(src, "private fun readApprovalIntent(", "private fun ")
        assertTrue(body.contains("focusApproval.value ="))
        // No approval/decision call and no other action hangs off that extra.
        for (forbidden in listOf("approve", "decide(", "startLiveRequested", "beginVoice", "liveStartSoon")) {
            assertFalse("readApprovalIntent must not $forbidden", body.contains(forbidden))
        }
    }

    @Test
    fun `only proof-carrying code paths set the Live start request`() {
        val src = source("MainActivity.kt")
        // Every assignment to startLiveRequested is either inside a
        // LaunchedEffect that reacts to an InternalLaunch decision, or the
        // explicit widget/tile paths cleared by `locked`. This pins that none
        // is reachable from a raw Intent extra read.
        val assignments = src.lines().filter { it.contains("startLiveRequested.value =") }
        assertTrue("startLiveRequested is still used", assignments.isNotEmpty())
        val liveIntent = block(src, "private fun readLiveIntent(", "private fun ")
        assertEquals(
            "readLiveIntent is the only place a start is requested from an Intent",
            (liveIntent.lines().count { it.trimStart().startsWith("InternalLaunch.Launch.") }),
            3,
        )
    }
}
