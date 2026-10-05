package com.jarvis.client.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The look record (docs/UI-AUDIT-2026-09-23.md §4). The presets it once had
 * were removed at the owner's request; what is left is the record's own
 * defaults and ranges.
 *
 * Pure Kotlin on purpose: the JSON half lives in AppearanceStore and needs
 * org.json, which a JVM unit test only has as stubs.
 */
class LookTest {

    @Test
    fun theDefaultLookIsTheOneHomeHadBefore() {
        val look = Look()
        assertEquals(0.75f, look.faceFraction, 0f)
        // Shown by default since 2026-10-05 (ease-of-use audit row 3). This
        // line is the whole change: it fails on the old `false`.
        assertTrue(look.navAlwaysShown)
        assertEquals(1f, look.glow, 0f)
        assertEquals(MotionPref.FOLLOW, look.motion)
        // "Keep the animal still" is off unless chosen (owner, 2026-09-28).
        assertFalse(look.stillAnimal)
        assertFalse(look.compact)
        assertTrue(look.makeRoomForApprovals)
        // The default is already inside the ranges setLook clamps to.
        assertEquals(look, look.clamped())
    }

    /**
     * An owner who already chose "Hidden until swiped" keeps it.
     *
     * The saved record is the choice: every field is written on save, so a
     * record holding `nav_always_shown: false` means he turned the row off.
     * Only a record that says nothing about it - a fresh install, or one saved
     * before the field existed - takes the new default. `tabsRowShown` is the
     * rule `AppearanceStore.loadLook` applies, and the null below is exactly
     * what it passes for "the record does not mention it" (the JSON half needs
     * org.json, a stub in a JVM unit test).
     */
    @Test
    fun aStoredChoiceOfHiddenIsNotOverwrittenByTheNewDefault() {
        // Unset: the new default, shown.
        assertTrue(tabsRowShown(null))
        // Chosen hidden, before this change: still hidden.
        assertFalse(tabsRowShown(false))
        // Chosen shown: shown, so the check cannot pass by ignoring the record.
        assertTrue(tabsRowShown(true))
    }

    @Test
    fun clampedPullsEverythingIntoRange() {
        val wild = Look(faceFraction = 3f, glow = 7f, textScale = 0.1f).clamped()
        assertEquals(Look.MAX_FACE_FRACTION, wild.faceFraction, 0f)
        assertEquals(1f, wild.glow, 0f)
        assertEquals(Look.MIN_TEXT_SCALE, wild.textScale, 0f)

        val low = Look(faceFraction = 0f, glow = 0f, textScale = 9f).clamped()
        assertEquals(Look.MIN_FACE_FRACTION, low.faceFraction, 0f)
        assertEquals(Look.MIN_GLOW, low.glow, 0f)
        assertEquals(Look.MAX_TEXT_SCALE, low.textScale, 0f)
    }

    /** NaN survives coerceIn, so it has to be caught first - see AppearanceStore.parseBindings. */
    @Test
    fun clampedTurnsNanIntoTheDefault() {
        val nan = Look(faceFraction = Float.NaN, glow = Float.NaN, textScale = Float.NaN).clamped()
        assertEquals(Look.DEFAULT_FACE_FRACTION, nan.faceFraction, 0f)
        assertEquals(1f, nan.glow, 0f)
        assertEquals(1f, nan.textScale, 0f)
    }

    /** Home's own drag limits and this record's agree. */
    @Test
    fun faceFractionRangeMatchesHome() {
        assertEquals(0.20f, Look.MIN_FACE_FRACTION, 0f)
        assertEquals(0.85f, Look.MAX_FACE_FRACTION, 0f)
        assertEquals(0.75f, Look.DEFAULT_FACE_FRACTION, 0f)
    }

    @Test
    fun idsRoundTripAndUnknownIsTheDefault() {
        for (m in MotionPref.entries) assertEquals(m, MotionPref.byId(m.id))
        for (e in EdgePref.entries) assertEquals(e, EdgePref.byId(e.id))
        assertEquals(MotionPref.FOLLOW, MotionPref.byId(""))
        assertEquals(EdgePref.HAIRLINE, EdgePref.byId("neon"))
    }
}
