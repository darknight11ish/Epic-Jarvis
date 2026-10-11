package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PlainErrors
import com.jarvis.client.net.Watch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
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
        // A body with none of the keys the route serves is NOT an empty list.
        // Until 2026-10-09 these two lines asserted the opposite - `{"ok":true}`
        // and `{}` read as `Read(emptyList())` - which is the reassuring
        // "Nothing new since you last marked the list read." drawn over a
        // payload nothing had read. That assertion was the fiction that let the
        // key mismatch live on the phone as well as the PC (2026-10-09).
        for (body in listOf("""{"ok":true}""", "{}")) {
            val unreadable = Watch.reportOf(ApiResult.Ok(obj(body)))
            assertEquals(Watch.Report.Failed(Watch.UNREADABLE), unreadable)
            assertEquals("Couldn't read what is new: ${Watch.UNREADABLE}", Watch.reportLine(unreadable))
        }

        // The real empty answer: the module's own keys, both lists empty. This
        // is the one shape the all-clear may be drawn for.
        assertEquals(Watch.Report.Read(emptyList()), Watch.reportOf(ApiResult.Ok(obj(EMPTY))))
        assertEquals(Watch.ALL_CLEAR, Watch.reportLine(Watch.reportOf(ApiResult.Ok(obj(EMPTY)))))

        // Every other state: no all-clear anywhere.
        assertNull("still reading draws nothing", Watch.reportLine(Watch.Report.Waiting))
        for (e in failures) {
            assertNotEquals(Watch.ALL_CLEAR, Watch.reportLine(Watch.reportOf(ApiResult.Failed(e))))
        }
        val rows = Watch.reportOf(ApiResult.Ok(obj("""{"new":[{"repo":"a/b"}],"updated":[]}""")))
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
        var drawn = Watch.reportLine(Watch.reportOf(ApiResult.Ok(obj(EMPTY))))
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

    /**
     * N2 of the same audit, and why it needed no separate fix: with rows already
     * on screen, a failed refresh used to leave them there indefinitely, under a
     * heading that says what is new, with no age line and no error. Same root
     * cause as N1, and the same one-state fix closes it - a failed report is its
     * own state with no findings, so the rows are gone rather than stale, and
     * the line that replaces them says the read failed.
     */
    @Test
    fun `rows on screen do not survive a failed refresh`() {
        val loaded = Watch.reportOf(ApiResult.Ok(obj("""{"findings":[{"full_name":"a/b"}]}""")))
        assertTrue("a successful read with rows is a Read", loaded is Watch.Report.Read)
        assertNull("rows are drawn, not a sentence", Watch.reportLine(loaded))

        val failed = Watch.reportOf(ApiResult.Failed(ApiError.Unreachable("Connection refused", "refused")))
        assertTrue("a failed refresh keeps no rows", failed is Watch.Report.Failed)
        assertTrue(
            "the rows' place now holds the failure line",
            Watch.reportLine(failed)!!.startsWith("Couldn't read what is new: "),
        )
    }

    private companion object {
        /** `GET /api/watch/report` with nothing waiting, in the module's own
         *  keys - `report(mark=False)` as the route answers it (2026-10-09). */
        const val EMPTY = """{"available":true,"new":[],"updated":[],"count":0,""" +
            """"topics":[],"note":"Licences are shown as GitHub reports them."}"""
    }
}

class WatchReportShapeTest {

    private val contract: JsonObject = JarvisJson
        .parseToJsonElement(checkNotNull(
            javaClass.classLoader?.getResourceAsStream("contract/watch-report-cases.json")
        ) { "contract/watch-report-cases.json is missing - run tools/gen_watch_report_cases.py" }
            .readBytes().decodeToString()).jsonObject

    private fun case(name: String): JsonObject = contract["cases"]!!.jsonObject[name]!!.jsonObject

    /** `{available: true}` plus a generated case - what the route hands the app. */
    private fun served(name: String): JsonObject =
        JsonObject(case(name) + ("available" to JsonPrimitive(true)))

    private fun rows(name: String): List<Watch.Finding> {
        val report = Watch.reportOf(ApiResult.Ok(served(name)))
        assertTrue("$name must read as a report, not ${report.javaClass.simpleName}",
            report is Watch.Report.Read)
        return (report as Watch.Report.Read).findings
    }

    @Test
    fun `rows the backend really sends are read, both kinds and in the module's order`() {
        val c = case("new_and_updated")
        assertTrue("this case must carry both kinds", c["new"]!!.jsonArray.isNotEmpty())
        assertTrue("this case must carry both kinds", c["updated"]!!.jsonArray.isNotEmpty())

        // The module's own consumer reads `peek["new"] + peek["updated"]`
        // (jarvis_watch.py:524). A client reading only one of the two loses half
        // the list, silently.
        val expected = (c["new"]!!.jsonArray + c["updated"]!!.jsonArray)
            .map { it.jsonObject["repo"]!!.jsonPrimitive.content }
        assertEquals(expected, rows("new_and_updated").map { it.title })
        assertTrue("a read with rows in it is not an empty list", expected.isNotEmpty())
    }

    @Test
    fun `an empty report is the only one that may draw the all-clear`() {
        for (name in listOf("empty", "after_mark_read")) {
            assertEquals(emptyList<Watch.Finding>(), rows(name))
            assertEquals(Watch.ALL_CLEAR, Watch.reportLine(Watch.reportOf(ApiResult.Ok(served(name)))))
        }
    }

    @Test
    fun `a repository's own name is read, not a placeholder`() {
        val findings = rows("new_only")
        assertTrue(findings.isNotEmpty())
        assertTrue("no row may fall back to the placeholder: ${findings.map { it.title }}",
            findings.none { it.title == "(repository)" })
        assertTrue("the served `repo` is the title",
            findings.all { it.title.contains("/") && it.description.isNotEmpty() })
    }

    @Test
    fun `a row that moved is read from updated, with what changed carried`() {
        val findings = rows("updated_only")
        assertEquals(1, findings.size)
        val c = case("updated_only")["updated"]!!.jsonArray[0].jsonObject
        assertEquals(c["repo"]!!.jsonPrimitive.content, findings[0].title)
        assertTrue("an archived project must read as archived", findings[0].archived)
    }

    @Test
    fun `'none stated' is no licence at all, so the no-permission warning draws`() {
        val c = case("new_only")
        val unlicensed = c["new"]!!.jsonArray.map { it.jsonObject }
            .single { it["licence"]!!.jsonPrimitive.content == "none stated" }
        val finding = rows("new_only").single { it.title == unlicensed["repo"]!!.jsonPrimitive.content }

        // `jarvis_watch.py:492` sends these two words for a repository with no
        // licence file. The filter used to be `^(none|unknown|null)$`, which
        // they do not match, so it was shown back as a settled licence and the
        // warning never drew - on a screen whose whole job is saying what the
        // owner may use.
        assertNull("'none stated' is not a licence", finding.licence)
        assertTrue("the no-permission warning must draw",
            Watch.findingLines(finding).any { it.contains("no permission") })

        // And the real licences must still be read as licences.
        val stated = rows("new_only").filter { it.licence != null }
        assertTrue("the fixture must carry real licences too", stated.isNotEmpty())
        assertTrue(stated.none { Watch.findingLines(it).any { l -> l.contains("no permission") } })
    }

    @Test
    fun `this app reads no key the route does not serve`() {
        // The route's own shape, exactly as the module produced it. A backend
        // rename shows up here as a changed list, which is the point: the
        // client's reads are checked against the served keys, not against
        // whatever the client happens to expect.
        assertEquals(
            listOf("available", "count", "new", "note", "topics", "updated"),
            contract["top_level_keys"]!!.jsonArray.map { it.jsonPrimitive.content },
        )
        val rowKeys = contract["row_keys"]!!.jsonArray.map { it.jsonPrimitive.content }
        assertEquals(
            listOf("archived", "at", "description", "kind", "licence", "repo", "stars",
                "topic", "url", "what_changed"),
            rowKeys,
        )

        // The four keys `Watch` used to read INSTEAD of these, none of which the
        // route has ever served. They survive only as the tolerant fallback, so
        // a future backend renaming `new`/`updated` does not silently empty the
        // list - never as the primary read (2026-10-09).
        val served = contract["top_level_keys"]!!.jsonArray.map { it.jsonPrimitive.content }.toSet()
        for (gone in listOf("findings", "items")) {
            assertFalse("`$gone` is not served, and must never be the primary read", served.contains(gone))
        }
        for (gone in listOf("full_name", "name", "descr", "license")) {
            assertFalse("`$gone` is not a row's key", rowKeys.contains(gone))
        }
    }
}
