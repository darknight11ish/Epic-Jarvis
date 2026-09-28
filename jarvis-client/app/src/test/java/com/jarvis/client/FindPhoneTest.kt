package com.jarvis.client

import com.jarvis.client.net.FindPhone
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Ring my phone" on the phone (net/FindPhone.kt; backend jarvis_find_phone.py;
 * docs/JARVIS-API.md section 74): the event is read strictly, a stale one
 * never rings, a stop never rings, and it never rings longer than two minutes.
 */
class FindPhoneTest {
    private fun obj(s: String) = JarvisJson.parseToJsonElement(s) as JsonObject

    private val ring = obj(
        """{"id":"r0123456789ab","state":"ring","at":1000.0,"until":1060.0,"seconds":60}""",
    )

    @Test
    fun aRingFromThePcIsRead() {
        val r = FindPhone.parse(ring)!!
        assertEquals("r0123456789ab", r.id)
        assertFalse(r.stop)
        assertEquals(1000.0, r.at, 0.0)
        assertEquals(60_000L, FindPhone.ringMillis(r))
        assertEquals("find-phone:r0123456789ab", FindPhone.tag(r.id))
    }

    @Test
    fun anythingElseIsNotARing() {
        assertNull(FindPhone.parse(null))
        assertNull(FindPhone.parse(obj("""{"id":"x","state":"ring","at":1.0}""")))
        assertNull(FindPhone.parse(obj("""{"id":"r0123456789ab","state":"dance","at":1.0}""")))
        assertNull(FindPhone.parse(obj("""{"id":"r0123456789ab","state":"ring"}""")))
        assertNull(FindPhone.parse(obj("""{"id":"r0123456789ab","state":"ring","at":"1000"}""")))
    }

    @Test
    fun aStaleOrReplayedRingNeverRingsAndAStopNeverRings() {
        val r = FindPhone.parse(ring)!!
        assertTrue("fresh", FindPhone.shouldRing(r, 1030.0))
        assertTrue("a phone clock a little behind", FindPhone.shouldRing(r, 950.0))
        assertFalse("heard late: silent", FindPhone.shouldRing(r, 1000.0 + FindPhone.FRESH_SECONDS + 1))
        assertFalse("a clock far behind", FindPhone.shouldRing(r, 1000.0 - FindPhone.FRESH_SECONDS - 1))
        val stop = FindPhone.parse(obj("""{"id":"r0123456789ab","state":"stop","at":1010.0}"""))!!
        assertTrue(stop.stop)
        assertFalse(FindPhone.shouldRing(stop, 1010.0))
    }

    @Test
    fun itNeverRingsLongerThanTwoMinutesNorShorterThanTenSeconds() {
        val long = FindPhone.parse(obj("""{"id":"r0123456789ab","state":"ring","at":1.0,"seconds":3600}"""))!!
        assertEquals(FindPhone.MAX_SECONDS * 1000L, FindPhone.ringMillis(long))
        val short = FindPhone.parse(obj("""{"id":"r0123456789ab","state":"ring","at":1.0,"seconds":0}"""))!!
        assertEquals(FindPhone.MIN_SECONDS * 1000L, FindPhone.ringMillis(short))
        assertFalse(FindPhone.TEXT.isBlank() || FindPhone.LOCK_SCREEN.isBlank())
    }
}
