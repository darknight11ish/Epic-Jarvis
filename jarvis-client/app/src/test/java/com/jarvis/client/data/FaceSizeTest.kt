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
     * The fixed sizes never exceed the original 260dp; only the two opt-in
     * "fill" sizes grow past it, and the default is not one of them.
     */
    @Test
    fun onlyTheOptInSizesGrowPastTheOriginal() {
        assertEquals(260, FaceSize.DEFAULT.sizeDp)
        assertFalse(FaceSize.DEFAULT.fill)
        assertFalse(FaceSize.DEFAULT.voiceOnly)
        assertTrue(FaceSize.entries.filter { !it.fill }.all { it.sizeDp <= 260 })
        assertEquals(listOf(FaceSize.FULL_SCREEN), FaceSize.entries.filter { it.voiceOnly })
        assertTrue(FaceSize.entries.filter { it.voiceOnly }.all { it.fill })
    }
}
