package com.jarvis.client

import com.jarvis.client.net.ScreenWatch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * "Watch with me" must end the capture the moment the phone locks and when the
 * maximum session length is reached (2026-10-20 Android audit, Area 10B).
 *
 * `ScreenWatch.endReason` is the pure rule; `ScreenWatchService` calls it on a
 * short timer AND keeps the screen-off broadcast and the one-shot timer. No
 * branch of this rule ever says "keep capturing a locked screen".
 */
class ScreenWatchLockTest {

    @Test
    fun `a locked phone ends the session at once`() {
        assertEquals(
            ScreenWatch.ENDED_LOCK,
            ScreenWatch.endReason(
                screenOn = true, keyguardLocked = true,
                startedAtMs = 1_000L, nowMs = 1_100L,
            ),
        )
        // Screen on but locked is the case a screen-off broadcast alone misses.
        assertEquals(
            ScreenWatch.ENDED_LOCK,
            ScreenWatch.endReason(
                screenOn = false, keyguardLocked = true,
                startedAtMs = 1_000L, nowMs = 1_100L,
            ),
        )
    }

    @Test
    fun `a screen that is off ends the session at once`() {
        assertEquals(
            ScreenWatch.ENDED_LOCK,
            ScreenWatch.endReason(
                screenOn = false, keyguardLocked = false,
                startedAtMs = 1_000L, nowMs = 1_100L,
            ),
        )
    }

    @Test
    fun `a healthy session under the limit keeps running`() {
        assertNull(
            ScreenWatch.endReason(
                screenOn = true, keyguardLocked = false,
                startedAtMs = 10_000L, nowMs = 10_000L + 29L * 60_000L,
            ),
        )
        assertNull(
            ScreenWatch.endReason(
                screenOn = true, keyguardLocked = false,
                startedAtMs = 0L, nowMs = 0L,
            ),
        )
    }

    @Test
    fun `the maximum session length ends the session`() {
        assertEquals(
            ScreenWatch.ENDED_TIME,
            ScreenWatch.endReason(
                screenOn = true, keyguardLocked = false,
                startedAtMs = 0L, nowMs = 30L * 60_000L,
            ),
        )
        assertEquals(
            ScreenWatch.ENDED_TIME,
            ScreenWatch.endReason(
                screenOn = true, keyguardLocked = false,
                startedAtMs = 0L, nowMs = 31L * 60_000L,
            ),
        )
    }

    @Test
    fun `an out of range maximum is clamped like a real session`() {
        // 0 is clamped to one minute, exactly as ScreenWatch.started does.
        assertEquals(
            ScreenWatch.ENDED_TIME,
            ScreenWatch.endReason(
                screenOn = true, keyguardLocked = false,
                startedAtMs = 0L, nowMs = 60_000L, maxMinutes = 0,
            ),
        )
        // Above the cap is clamped to MAX_MINUTES, never longer: 31 minutes
        // with a 90-minute request still ends at the 30-minute cap.
        assertEquals(
            ScreenWatch.ENDED_TIME,
            ScreenWatch.endReason(
                screenOn = true, keyguardLocked = false,
                startedAtMs = 0L, nowMs = 31L * 60_000L, maxMinutes = 90,
            ),
        )
        // ...and under the cap it is still running.
        assertNull(
            ScreenWatch.endReason(
                screenOn = true, keyguardLocked = false,
                startedAtMs = 0L, nowMs = 29L * 60_000L, maxMinutes = 90,
            ),
        )
    }

    @Test
    fun `the service really wires the rule and has no always-on branch`() {
        val src = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/service/ScreenWatchService.kt")
        for (needle in listOf(
            "ScreenWatch.endReason(",
            "keyguardLocked()",
            "isKeyguardLocked",
            "sessionCheck",
            "SESSION_CHECK_MS",
            "removeCallbacks(sessionCheck)",
            "main.postDelayed(sessionCheck,",
        )) {
            assert(src.contains(needle)) { "ScreenWatchService.kt must wire $needle" }
        }
        // An end reason always calls end(...); there is no path where the
        // check finds a lock and keeps running.
        assert(src.contains("if (reason != null) {\n                end(reason)")) {
            "a lock/time reason must end the session"
        }
    }
}
