package com.jarvis.client.data

import org.junit.Assert.assertEquals
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

    /** Only ever smaller than the original: larger costs frame time nobody has measured. */
    @Test
    fun nothingIsBiggerThanTheOriginal() {
        assertEquals(260, FaceSize.DEFAULT.sizeDp)
        assertTrue(FaceSize.entries.all { it.sizeDp <= 260 })
    }
}
