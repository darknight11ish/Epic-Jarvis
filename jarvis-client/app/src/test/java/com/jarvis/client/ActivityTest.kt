package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * `Activity.from()`'s wire mapping - a pure function with no Android
 * dependency, so it is checked directly rather than through anything that
 * needs a device. `PAUSED` is AUTONOMY-PROPOSALS.md §3d's own addition: no
 * backend is confirmed to send `"paused"` yet, but the mapping has to be
 * right the moment one does, and this is the one place that would silently
 * keep reading it as idle if the `when` ever lost its branch.
 */
class ActivityTest {

    @Test
    fun `every known wire value maps to its own activity`() {
        assertEquals(Activity.LISTENING, Activity.from("listening"))
        assertEquals(Activity.THINKING, Activity.from("thinking"))
        assertEquals(Activity.SPEAKING, Activity.from("speaking"))
        assertEquals(Activity.WORKING, Activity.from("working"))
        assertEquals(Activity.PAUSED, Activity.from("paused"))
        assertEquals(Activity.ERROR, Activity.from("error"))
    }

    @Test
    fun `matching is case-insensitive`() {
        assertEquals(Activity.PAUSED, Activity.from("PAUSED"))
        assertEquals(Activity.WORKING, Activity.from("Working"))
    }

    @Test
    fun `anything unrecognised, or absent, is idle`() {
        assertEquals(Activity.IDLE, Activity.from(null))
        assertEquals(Activity.IDLE, Activity.from(""))
        assertEquals(Activity.IDLE, Activity.from("something a future backend invents"))
    }
}
