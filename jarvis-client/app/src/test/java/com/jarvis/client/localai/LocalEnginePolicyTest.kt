package com.jarvis.client.localai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The five-minute idle rule and the 180-second hard cap, on a clock the test
 * moves by hand: no sleeps, no flakes, and the exact millisecond on both sides
 * of every boundary.
 *
 * The idle window was **5 seconds** until the 2026-11-13 field test on the
 * owner's phone: the model unloaded 16 seconds after Load, before a person
 * could start typing (loaded `06:15:04.976`, unloaded `06:15:20.870`). The
 * measured correction is **5 minutes**, and this test pins that number and its
 * exact boundary instead of the old one. The 180-second hard cap is unchanged.
 */
class LocalEnginePolicyTest {

    private var now: Long = 1_000L

    private fun policy(
        idle: Long = LocalEnginePolicy.IDLE_UNLOAD_MILLIS,
        cap: Long = LocalEnginePolicy.HARD_CAP_MILLIS,
    ) = LocalEnginePolicy(clock = { now }, idleMillis = idle, hardCapMillis = cap)

    @Test
    fun theTwoWindowsAreFiveMinutesAndThreeMinutes() {
        assertEquals(300_000L, LocalEnginePolicy.IDLE_UNLOAD_MILLIS)
        assertEquals(180_000L, LocalEnginePolicy.HARD_CAP_MILLIS)
    }

    @Test
    fun theIdleWindowStartsOnTheLoadRequest() {
        val rules = policy()
        rules.requested()
        now += LocalEnginePolicy.IDLE_UNLOAD_MILLIS - 1L
        assertFalse(rules.idleDue())
        now += 1L
        assertTrue("300,000 ms exactly must unload", rules.idleDue())
        assertEquals(LocalEnginePolicy.Decision.UnloadAfterIdle, rules.decide())
    }

    @Test
    fun aModelThatWasNeverAskedForIsNotUnloadedByAccident() {
        val rules = policy()
        assertFalse(rules.idleDue())
        assertEquals(LocalEnginePolicy.Decision.Nothing, rules.decide())
    }

    @Test
    fun aNewRequestRestartsTheIdleWindow() {
        val rules = policy()
        rules.requestedAt(1_000)
        now = 1_000 + LocalEnginePolicy.IDLE_UNLOAD_MILLIS - 1L
        rules.requested()
        assertFalse(rules.idleDue())
        now += LocalEnginePolicy.IDLE_UNLOAD_MILLIS - 1L
        assertFalse(rules.idleDue())
        now += 1L
        assertTrue(rules.idleDue())
    }

    @Test
    fun typingRestartsTheIdleWindowLikeAnyOtherRequest() {
        val rules = policy()
        rules.requestedAt(1_000)
        now = 1_000 + LocalEnginePolicy.IDLE_UNLOAD_MILLIS - 1L
        rules.touched()
        assertFalse("a person typing must not lose the model", rules.idleDue())
        now += LocalEnginePolicy.IDLE_UNLOAD_MILLIS
        assertTrue(rules.idleDue())
    }

    @Test
    fun aGenerationIsNeverUnloadedForBeingIdle() {
        val rules = policy()
        val start = now
        rules.generationStarted()
        now = start + 10_000L
        assertTrue(rules.isGenerating())
        assertFalse(rules.idleDue())
    }

    @Test
    fun theHardCapIsExactlyOneHundredAndEightySeconds() {
        val rules = policy()
        val start = now
        rules.generationStarted()
        now = start + 179_999L
        assertFalse(rules.hardCapDue())
        now = start + 180_000L
        assertTrue("180,000 ms exactly must stop the reply", rules.hardCapDue())
        assertEquals(LocalEnginePolicy.Decision.StopAtHardCap, rules.decide())
        assertEquals(start + 180_000L, rules.hardDeadline())
    }

    @Test
    fun theHardCapOutranksTheIdleRuleWhileGenerating() {
        val rules = policy()
        rules.generationStartedAt(1_000)
        now = 1_000 + LocalEnginePolicy.HARD_CAP_MILLIS
        assertEquals(LocalEnginePolicy.Decision.StopAtHardCap, rules.decide())
    }

    @Test
    fun theIdleWindowRestartsWhenTheAnswerLandsNotWhenItStarted() {
        val rules = policy()
        rules.generationStartedAt(1_000)
        now = 151_000 // 150 seconds of thinking
        rules.generationFinished()
        assertFalse(rules.isGenerating())
        now = 151_000 + LocalEnginePolicy.IDLE_UNLOAD_MILLIS - 1L
        assertFalse(rules.idleDue())
        now += 1L
        assertTrue(rules.idleDue())
    }

    @Test
    fun resetForgetsBothWindows() {
        val rules = policy()
        rules.generationStarted()
        rules.reset()
        assertFalse(rules.isGenerating())
        assertFalse(rules.idleDue())
        assertNull(rules.hardDeadline())
        assertEquals(LocalEnginePolicy.Decision.Nothing, rules.decide())
    }

    @Test
    fun theClockIsTheOnlyInputSoWindowsCanBeTinyInTests() {
        val rules = LocalEnginePolicy(clock = { now }, idleMillis = 20L, hardCapMillis = 40L)
        rules.generationStartedAt(100L)
        now = 139L
        assertFalse(rules.hardCapDue())
        now = 140L
        assertTrue(rules.hardCapDue())
        rules.generationFinishedAt(140L)
        now = 159L
        assertFalse(rules.idleDue())
        now = 160L
        assertTrue(rules.idleDue())
    }

    @Test(expected = IllegalArgumentException::class)
    fun aZeroIdleWindowIsRefusedRatherThanMeaningInstant() {
        LocalEnginePolicy(idleMillis = 0L)
    }

    @Test(expected = IllegalArgumentException::class)
    fun aZeroHardCapIsRefused() {
        LocalEnginePolicy(hardCapMillis = 0L)
    }
}
