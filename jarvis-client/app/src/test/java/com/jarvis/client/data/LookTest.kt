package com.jarvis.client.data

import com.jarvis.client.ui.theme.Themes
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The look record and its presets (docs/UI-AUDIT-2026-09-23.md §4).
 *
 * Pure Kotlin on purpose: the JSON half lives in AppearanceStore and needs
 * org.json, which a JVM unit test only has as stubs. What is checked here is
 * the part that decides what the owner is told - "Focus" or "Custom (from
 * Focus)" - and that the presets say what the report's table says.
 */
class LookTest {

    private val reactor = Themes.REACTOR.id

    /** The theme a preset is judged on: its own, or any theme when it names none. */
    private fun themeFor(p: LookPreset): String = p.themeId ?: reactor

    @Test
    fun theDefaultLookIsFocusAndNotCustom() {
        val look = Look()
        assertEquals(LookPreset.FOCUS, look.basedOn)
        assertFalse(look.isCustom(reactor))
        assertEquals("Focus", look.label(reactor))
        // Focus names no theme, so it stays Focus on every one.
        for (t in Themes.ALL) assertFalse(t.id, look.isCustom(t.id))
    }

    @Test
    fun everyPresetMatchesItselfOnceApplied() {
        for (p in LookPreset.entries) {
            val look = p.applyTo(Look())
            assertEquals(p, look.basedOn)
            assertTrue(p.id, p.matches(look, themeFor(p)))
            assertFalse(p.id, look.isCustom(themeFor(p)))
            assertEquals(p.label, look.label(themeFor(p)))
        }
    }

    /** A theme id that stopped existing would make Night or Outdoor silently fall back to Reactor. */
    @Test
    fun presetThemesExist() {
        for (p in LookPreset.entries) {
            val id = p.themeId ?: continue
            assertNotNull("${p.id} names theme '$id', which is not in Themes.ALL", Themes.ALL.firstOrNull { it.id == id })
        }
        assertEquals(Themes.EMBER_DUSK.id, LookPreset.NIGHT.themeId)
        assertEquals(Themes.DAYLIGHT.id, LookPreset.OUTDOOR.themeId)
    }

    /** The report's table, value for value. */
    @Test
    fun presetsSetWhatTheReportSays() {
        val focus = LookPreset.FOCUS.applyTo(Look())
        assertEquals(0.75f, focus.faceFraction, 0f)
        assertFalse(focus.navAlwaysShown)
        assertEquals(1f, focus.glow, 0f)
        assertEquals(MotionPref.FOLLOW, focus.motion)
        assertFalse(focus.compact)

        val conversation = LookPreset.CONVERSATION.applyTo(Look())
        assertEquals(0.35f, conversation.faceFraction, 0f)
        assertTrue(conversation.navAlwaysShown)
        assertTrue(conversation.compact)

        val night = LookPreset.NIGHT.applyTo(Look())
        assertEquals(0.6f, night.glow, 0f)
        assertEquals(MotionPref.CALM, night.motion)

        val outdoor = LookPreset.OUTDOOR.applyTo(Look())
        assertTrue(outdoor.navAlwaysShown)
        assertEquals(1.1f, outdoor.textScale, 0f)
    }

    /** Glow and motion may only reduce. No preset brightens or speeds anything up. */
    @Test
    fun presetsNeverBrightenOrSpeedUp() {
        for (p in LookPreset.entries) {
            val look = p.applyTo(Look())
            assertTrue(p.id, look.glow <= 1f)
            assertTrue(p.id, look.motion != MotionPref.FULL)
            // Every preset value is already inside the ranges setLook clamps to.
            assertEquals(p.id, look, look.clamped())
        }
    }

    @Test
    fun changingAFineControlMakesItCustomAndChangingItBackDoesNot() {
        val focus = LookPreset.FOCUS.applyTo(Look())
        val dimmer = focus.copy(glow = 0.4f)
        assertTrue(dimmer.isCustom(reactor))
        assertEquals("Custom (from Focus)", dimmer.label(reactor))
        assertFalse(dimmer.copy(glow = 1f).isCustom(reactor))
    }

    /** Night is a theme as well as settings: on another theme it is Night no longer. */
    @Test
    fun aPresetOnTheWrongThemeIsCustom() {
        val night = LookPreset.NIGHT.applyTo(Look())
        assertFalse(night.isCustom(Themes.EMBER_DUSK.id))
        assertTrue(night.isCustom(reactor))
        assertEquals("Custom (from Night)", night.label(reactor))
    }

    /** The behaviour switches are not part of any preset, in either direction. */
    @Test
    fun behaviourSwitchesSurviveAPresetAndDoNotMakeItCustom() {
        val mine = Look(
            makeRoomForApprovals = false,
            shrinkWhileTyping = false,
            followReply = false,
            tapFaceOpensMind = false,
        )
        for (p in LookPreset.entries) {
            val applied = p.applyTo(mine)
            assertFalse(p.id, applied.makeRoomForApprovals)
            assertFalse(p.id, applied.shrinkWhileTyping)
            assertFalse(p.id, applied.followReply)
            assertFalse(p.id, applied.tapFaceOpensMind)
            assertFalse(p.id, applied.isCustom(themeFor(p)))
        }
    }

    /** Applying a preset resets the fine controls it does not mention, so it is predictable. */
    @Test
    fun aPresetPutsUnmentionedControlsBackToTheirDefaults() {
        val fiddled = Look(sharp = true, edges = EdgePref.NONE, transitions = false, textScale = 1.3f)
        val conversation = LookPreset.CONVERSATION.applyTo(fiddled)
        assertFalse(conversation.sharp)
        assertEquals(EdgePref.HAIRLINE, conversation.edges)
        assertTrue(conversation.transitions)
        assertEquals(1f, conversation.textScale, 0f)
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
        for (p in LookPreset.entries) assertEquals(p, LookPreset.byId(p.id))
        for (m in MotionPref.entries) assertEquals(m, MotionPref.byId(m.id))
        for (e in EdgePref.entries) assertEquals(e, EdgePref.byId(e.id))
        assertEquals(LookPreset.FOCUS, LookPreset.byId(null))
        assertEquals(LookPreset.FOCUS, LookPreset.byId("disco"))
        assertEquals(MotionPref.FOLLOW, MotionPref.byId(""))
        assertEquals(EdgePref.HAIRLINE, EdgePref.byId("neon"))
    }
}
