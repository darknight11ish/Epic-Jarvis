package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.voice.LiveRules
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Why this phone's Live stopped, and what it says (the owner's Pixel 9,
 * 2026-10-17). Pure functions, so this runs on the JVM: no device, no Android.
 *
 * `contract/live-cases.json` is written by the real PC code
 * (tools/gen_live_cases.py) and is byte for byte the file the desktop builds
 * against; `backend/test_live.py` holds the PC side of the same table. Every
 * reason, every sentence and the reasons an app may send come from it - if
 * the phone and the PC ever word an end differently, one of the two tests
 * fails.
 *
 * THE BITE. Change `endedWords(FGS_REFUSED)` back to "You ended it." and
 * [an android refusal never says the owner ended it] plus the fixture check
 * fail. Drop `fgs_refused` from `END_REASONS` and the wire-reason check fails
 * (the PC would word it as its own "Live ended." instead of Android's).
 * Return [LiveRules.LiveStop.OWNER] from `stopForClasses` for an unrelated
 * exception and [an unexplained exception is never the owner's end] fails.
 */
class LiveStopReasonTest {

    private val table: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/live-cases.json")) {
            "contract/live-cases.json is missing - run python3 tools/gen_live_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private fun words(key: String): Map<String, String> =
        table[key]!!.jsonObject.mapValues { (_, v) -> v.jsonPrimitive.content }

    private val endWords = words("end_words")
    private val appStopWords = words("app_stop_words")
    private val appEndReasons =
        table["app_end_reasons"]!!.jsonArray.map { it.jsonPrimitive.content }.toSet()

    // ------------------------------------------------------- the words -----

    @Test
    fun `an android refusal never says the owner ended it`() {
        val why = LiveRules.LiveStop.FGS_REFUSED
        assertEquals(LiveRules.ENDED_FGS_REFUSED, LiveRules.endedWords(why))
        assertEquals(endWords["fgs_refused"], LiveRules.endedWords(why))
        assertEquals(appStopWords["fgs_refused"], LiveRules.stopWords(why))
        assertFalse(LiveRules.endedWords(why).contains("You ended it"))
        assertFalse(LiveRules.endedByOwner(why))
    }

    @Test
    fun `a microphone permission refusal is not the owner's end`() {
        val why = LiveRules.LiveStop.MIC_PERMISSION
        assertEquals(endWords["mic_permission"], LiveRules.endedWords(why))
        assertEquals(appStopWords["mic_permission"], LiveRules.stopWords(why))
        assertTrue(LiveRules.stopWords(why).contains("microphone"))
        assertFalse(LiveRules.endedWords(why).contains("You ended it"))
        assertFalse(LiveRules.endedByOwner(why))
    }

    @Test
    fun `a microphone taken away is not reported as a background refusal`() {
        val why = LiveRules.LiveStop.MIC_STOPPED
        assertEquals(LiveRules.STOP_MIC_STOPPED, LiveRules.endedWords(why))
        assertEquals(endWords["mic_stopped"], LiveRules.endedWords(why))
        assertEquals(appStopWords["mic_stopped"], LiveRules.stopWords(why))
        assertFalse(LiveRules.endedWords(why).contains("background"))
        assertFalse(LiveRules.endedByOwner(why))
    }

    @Test
    fun `only the owner's own end says you ended it`() {
        val why = LiveRules.LiveStop.OWNER
        assertEquals("You ended it.", LiveRules.endedWords(why))
        assertEquals(endWords["owner"], LiveRules.endedWords(why))
        assertTrue(LiveRules.endedByOwner(why))
        for (other in LiveRules.LiveStop.values()) {
            if (other != why) assertFalse(LiveRules.endedByOwner(other))
        }
    }

    @Test
    fun `the refusal words name Android and the background, the microphone words do not`() {
        assertTrue(LiveRules.stopWords(LiveRules.LiveStop.FGS_REFUSED).contains("Android"))
        assertTrue(LiveRules.stopWords(LiveRules.LiveStop.FGS_REFUSED).contains("background"))
        assertTrue(LiveRules.stopWords(LiveRules.LiveStop.MIC_STOPPED).contains("microphone"))
        assertFalse(LiveRules.stopWords(LiveRules.LiveStop.MIC_STOPPED).contains("background"))
    }

    // ------------------------------------------------- the wire reasons ----

    @Test
    fun `every stop has the wire reason the PC accepts, and the shared table has the same list`() {
        // The phone's list is a SUBSET of the PC's accepted set - the PC also
        // accepts its OWN reasons ("locked", "bye", "quiet"...) that the phone
        // must never send.
        assertTrue(
            "the phone sends a reason the PC does not accept: " +
                (LiveRules.END_REASONS.toSet() - appEndReasons),
            appEndReasons.containsAll(LiveRules.END_REASONS),
        )
        for (code in listOf("owner", "app_lock", "screen_lock",
                            "fgs_refused", "mic_permission", "mic_stopped")) {
            assertTrue(code, code in LiveRules.END_REASONS)
        }
        assertFalse("locked is the PC's own reason; the phone never sends it",
            "locked" in LiveRules.END_REASONS)
        assertEquals("owner", LiveRules.whyOf(LiveRules.LiveStop.OWNER))
        assertEquals("fgs_refused", LiveRules.whyOf(LiveRules.LiveStop.FGS_REFUSED))
        assertEquals("mic_permission", LiveRules.whyOf(LiveRules.LiveStop.MIC_PERMISSION))
        assertEquals("mic_stopped", LiveRules.whyOf(LiveRules.LiveStop.MIC_STOPPED))
        for (stop in LiveRules.LiveStop.values()) {
            assertTrue(LiveRules.whyOf(stop), LiveRules.whyOf(stop) in LiveRules.END_REASONS)
        }
        // The PC words every reason an app may send (`jarvis_live.END_WORDS`).
        for (reason in appEndReasons) assertNotNull("no PC words for $reason", endWords[reason])
    }

    @Test
    fun `a stop body carries the phone's real reason, and an unexplained one is unknown`() {
        for (code in listOf("fgs_refused", "mic_permission", "mic_stopped")) {
            val body = LiveRules.stopBody(code)
            assertTrue(body, body.contains("\"why\":\"$code\""))
        }
        assertTrue(LiveRules.stopBody("owner").contains("\"why\":\"owner\""))
        // A reason this phone has no business sending is "unknown", NEVER
        // "owner": both apps word "owner" as "You ended it." (2026-10-17).
        val odd = LiveRules.stopBody("something-the-app-invented")
        assertTrue(odd, odd.contains("\"why\":\"unknown\""))
        assertFalse(odd, odd.contains("\"why\":\"owner\""))
        assertFalse("unknown" in LiveRules.END_REASONS)
    }

    @Test
    fun `a wire reason is worded only when this phone can word it`() {
        assertEquals(LiveRules.LiveStop.OWNER, LiveRules.stopOf("owner"))
        assertEquals(LiveRules.LiveStop.FGS_REFUSED, LiveRules.stopOf("fgs_refused"))
        assertEquals(LiveRules.LiveStop.MIC_PERMISSION, LiveRules.stopOf("mic_permission"))
        assertEquals(LiveRules.LiveStop.MIC_STOPPED, LiveRules.stopOf("mic_stopped"))
        // App lock and the screen lock are the PC's to word; "unknown" never
        // names a stop this phone can show.
        assertNull(LiveRules.stopOf("app_lock"))
        assertNull(LiveRules.stopOf("screen_lock"))
        assertNull(LiveRules.stopOf("unknown"))
        assertNull(LiveRules.stopOf(""))
    }

    // ------------------------------------------------- the split catch -----

    @Test
    fun `the split catch names Android's foreground-service refusal`() {
        assertEquals(
            LiveRules.LiveStop.FGS_REFUSED,
            LiveRules.stopForClasses(
                listOf(
                    "android.app.ForegroundServiceStartNotAllowedException",
                    "android.app.ServiceStartNotAllowedException",
                    "java.lang.IllegalStateException",
                    "java.lang.Exception",
                ),
            ),
        )
    }

    @Test
    fun `the split catch names a missing microphone permission`() {
        assertEquals(
            LiveRules.LiveStop.MIC_PERMISSION,
            LiveRules.stopForClasses(
                listOf("java.lang.SecurityException", "java.lang.RuntimeException", "java.lang.Exception"),
            ),
        )
    }

    @Test
    fun `an unexplained exception is never the owner's end`() {
        // Anything else says nothing about why: the caller uses the generic
        // microphone stop (never OWNER, which would word it "You ended it.").
        assertNull(LiveRules.stopForClasses(listOf("java.lang.IllegalStateException",
            "java.lang.Exception")))
        assertNull(LiveRules.stopForClasses(emptyList()))
        for (classes in listOf(
            listOf("java.lang.IllegalStateException", "java.lang.Exception"),
            emptyList(),
        )) {
            assertFalse(LiveRules.stopForClasses(classes) == LiveRules.LiveStop.OWNER)
        }
    }
}
