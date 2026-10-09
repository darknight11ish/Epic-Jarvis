package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PlainErrors
import com.jarvis.client.net.Watch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The "What is new" block on Watches, and the one sentence it may not say.
 *
 * N1 of the second Android audit (`docs/ANDROID-AUDIT-2-2026-10-09.md`,
 * 2026-10-09): the plate wrote its findings only on a successful
 * `GET /api/watch/report`, so a failed read kept the previous list on screen -
 * and once a read this visit had come back empty, a later failed one went on
 * drawing "Nothing new since you last marked the list read." over a read that
 * never happened. On a security-watch list that is the same lie as the
 * notification all-clear fixed in #128.
 *
 * The plate now draws [Watch.reportLine] of its one [Watch.Report] and nothing
 * else, so the words asserted here are the words the owner sees.
 */
class WatchReportTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    /** Every kind of failure the report route can come back with. */
    private val failures = listOf(
        ApiError.BadToken,
        ApiError.NotFound,
        ApiError.NotAvailable,
        ApiError.Server(500, "boom"),
        ApiError.Malformed("bad json"),
        ApiError.Unreachable("Connection refused", "refused"),
    )

    @Test
    fun `a failed report says so, and never says nothing is new`() {
        for (e in failures) {
            val report = Watch.reportOf(ApiResult.Failed(e))
            assertTrue("$e came back as a read", report is Watch.Report.Failed)

            val line = Watch.reportLine(report)
            assertNotNull("$e must draw a line where the list would be", line)
            assertTrue("$e must say the read failed: $line", line!!.startsWith("Couldn't read what is new: "))
            assertFalse("$e must not draw the all-clear: $line", line.contains(Watch.ALL_CLEAR))
            assertTrue("$e in plain words", line.endsWith((report as Watch.Report.Failed).reason))
        }
    }

    @Test
    fun `the failure line is the plain sentence, or the watch's own when the module is missing`() {
        assertEquals(
            "Couldn't read what is new: ${PlainErrors.forApiError(ApiError.BadToken).text}",
            Watch.reportLine(Watch.reportOf(ApiResult.Failed(ApiError.BadToken))),
        )
        assertEquals(
            "Couldn't read what is new: ${Watch.failure(ApiError.NotFound)}",
            Watch.reportLine(Watch.reportOf(ApiResult.Failed(ApiError.NotFound))),
        )
    }

    @Test
    fun `the all-clear is drawn for a read that answered empty, and for nothing else`() {
        // The audit's own probe: both bodies read as an empty list.
        assertEquals(Watch.Report.Read(emptyList()), Watch.reportOf(ApiResult.Ok(obj("""{"ok":true}"""))))
        assertEquals(Watch.Report.Read(emptyList()), Watch.reportOf(ApiResult.Ok(obj("{}"))))
        assertEquals(Watch.ALL_CLEAR, Watch.reportLine(Watch.reportOf(ApiResult.Ok(obj("""{"findings":[]}""")))))

        // Every other state: no all-clear anywhere.
        assertNull("still reading draws nothing", Watch.reportLine(Watch.Report.Waiting))
        for (e in failures) {
            assertNotEquals(Watch.ALL_CLEAR, Watch.reportLine(Watch.reportOf(ApiResult.Failed(e))))
        }
        val rows = Watch.reportOf(ApiResult.Ok(obj("""{"findings":[{"full_name":"a/b"}]}""")))
        assertNull("findings are drawn as rows, not as a sentence", Watch.reportLine(rows))
    }

    /**
     * The exact sequence the audit proved: a read that answered empty, then a
     * refresh that fails. The plate keeps one state and assigns it on every
     * read (`WatchPlate.kt`), so the reassuring sentence cannot survive the
     * failure - which is where it used to sit indefinitely.
     */
    @Test
    fun `an all-clear on screen does not survive a failed refresh`() {
        var drawn = Watch.reportLine(Watch.reportOf(ApiResult.Ok(obj("""{"ok":true}"""))))
        assertEquals(Watch.ALL_CLEAR, drawn)

        drawn = Watch.reportLine(Watch.reportOf(ApiResult.Failed(ApiError.Server(500, "boom"))))
        assertNotEquals(Watch.ALL_CLEAR, drawn)
        assertTrue(drawn!!.startsWith("Couldn't read what is new: "))
    }

    @Test
    fun `findings that arrived are drawn as findings`() {
        val report = Watch.reportOf(ApiResult.Ok(obj("""{"items":[{"name":"x/y"},{"name":"z/w"}]}""")))
        assertTrue(report is Watch.Report.Read)
        assertEquals(
            listOf("x/y", "z/w"),
            (report as Watch.Report.Read).findings.map { it.title },
        )
    }
}
