package com.jarvis.client.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The face-size setting is read back from preferences by id, so an id that
 * is missing, renamed or corrupt must land on the default rather than throw
 * - a bad preference must never be a phone that will not open.
 */
class FaceSizeTest {

    @Test
    fun everyIdRoundTrips() {
        for (size in FaceSize.entries) assertEquals(size, FaceSize.byId(size.id))
    }

    @Test
    fun unknownOrMissingIsTheDefault() {
        assertEquals(FaceSize.DEFAULT, FaceSize.byId(null))
        assertEquals(FaceSize.DEFAULT, FaceSize.byId(""))
        assertEquals(FaceSize.DEFAULT, FaceSize.byId("huge"))
    }

    /**
     * The fixed sizes never exceed 260dp; only the two "fill" sizes grow past
     * it. The DEFAULT is now one of the fill sizes - Extra large - because the
     * owner reported on 2026-10-13 that the face was "way too small" on every
     * option except Full screen when the app first opened. A fixed default
     * (Large, 260dp) showed a face that the leftover pane height could undercut
     * and that looked the same as Medium beside it.
     */
    @Test
    fun onlyTheOptInSizesGrowPastTheOriginal() {
        assertEquals(260, FaceSize.DEFAULT.sizeDp)
        assertTrue(FaceSize.DEFAULT.fill)
        assertFalse(FaceSize.DEFAULT.voiceOnly)
        assertTrue(FaceSize.entries.filter { !it.fill }.all { it.sizeDp <= 260 })
        assertEquals(listOf(FaceSize.FULL_SCREEN), FaceSize.entries.filter { it.voiceOnly })
        assertTrue(FaceSize.entries.filter { it.voiceOnly }.all { it.fill })
    }

    /** Small and Tiny were removed; a phone that saved one gets Medium, not a crash or a jump. */
    @Test
    fun retiredSizesLandOnMedium() {
        assertEquals(FaceSize.MEDIUM, FaceSize.byId("small"))
        assertEquals(FaceSize.MEDIUM, FaceSize.byId("tiny"))
    }

    @Test
    fun hiddenIsOnlyEverChosen() {
        assertFalse(FaceSize.DEFAULT.hidden)
        assertEquals(listOf(FaceSize.HIDDEN), FaceSize.entries.filter { it.hidden })
        assertFalse(FaceSize.HIDDEN.voiceOnly)
    }
}
