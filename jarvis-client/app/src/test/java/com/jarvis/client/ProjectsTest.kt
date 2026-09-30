package com.jarvis.client

import com.jarvis.client.net.Projects
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.double
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.intOrNull
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Projects on the phone (the owner's decision of 2026-09-28), read from what
 * the PC REALLY answers.
 *
 * `contract/projects-cases.json` is written by tools/gen_projects_cases.py
 * from the real backend (jarvis_projects.py) - byte for byte the file the
 * desktop's projects.mjs and brain/projects.rs build against. Its `words`
 * are the screens' sentences in both apps; `numbers` how the PC writes a
 * number; `scales` where a chart's bottom and top go.
 */
class ProjectsTest {

    private val json = Json { ignoreUnknownKeys = true }

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/projects-cases.json")) {
            "contract/projects-cases.json is missing - run tools/gen_projects_cases.py"
        }.readText()
        json.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject
    private val posts = doc["posts"]!!.jsonObject

    private fun project(name: String) = Projects.parseProject(cases[name]!!.jsonObject["project"]!!.jsonObject)!!

    @Test
    fun `the words are the desktop's, word for word`() {
        val words = doc["words"]!!.jsonObject
        assertEquals(words.keys, Projects.WORDS.keys)
        for ((k, v) in words) assertEquals(k, v.jsonPrimitive.content, Projects.WORDS[k])
        assertEquals(words["missing"]!!.jsonPrimitive.content, Projects.MISSING)
    }

    @Test
    fun `numbers are written the PC's way`() {
        for (n in doc["numbers"]!!.jsonArray) {
            val o = n.jsonObject
            val got = Projects.withUnit(o["value"]!!.jsonPrimitive.double, o["unit"]!!.jsonPrimitive.content)
            assertEquals(o.toString(), o["text"]!!.jsonPrimitive.content, got)
        }
    }

    @Test
    fun `the chart's scale is the shared one`() {
        for (s in doc["scales"]!!.jsonArray) {
            val o = s.jsonObject
            val values = o["values"]!!.jsonArray.map { it.jsonPrimitive.double }
            val target = o["target"]!!.jsonPrimitive.doubleOrNull
            val want = o["scale"]!!.jsonArray.map { it.jsonPrimitive.double }
            val (lo, hi) = Projects.chartScale(values, target)
            assertEquals(o.toString(), want[0], lo, 1e-9)
            assertEquals(o.toString(), want[1], hi, 1e-9)
        }
        val (pts, t) = Projects.chartGeometry(
            listOf(Projects.Point("a", 1.0, 10.0), Projects.Point("b", 3.0, 20.0)), 25.0, 320f, 120f,
        )
        assertEquals(8f, pts[0].x, 0.01f)
        assertEquals(312f, pts[1].x, 0.01f)
        assertTrue("higher is up", pts[1].y < pts[0].y)
        assertTrue("the target is above the top point", t!! < pts[1].y)
        val (one, none) = Projects.chartGeometry(listOf(Projects.Point("a", 5.0, 3.0)), null, 320f, 120f)
        assertEquals(160f, one[0].x, 0.01f)
        assertNull(none)
    }

    @Test
    fun `every real answer reads`() {
        val list = Projects.parseList(cases["list_two"]!!.jsonObject)!!
        assertEquals(listOf("Half marathon", "Jarvis Desktop"), list.projects.map { it.name })
        assertEquals(2, list.projects[1].benchmarks)
        assertEquals("No projects yet.", Projects.parseList(cases["list_empty"]!!.jsonObject)!!.empty)
        assertNull(Projects.parseList(JsonObject(emptyMap())))
        val life = project("life")
        assertEquals("life", life.kind)
        assertEquals(listOf("Long runs on Sundays", "Knee: stop if it hurts"), life.notes)
        assertEquals("Half marathon list", life.workListTitle)
        assertFalse(life.shareable)
        val coding = project("coding")
        assertEquals("C:\\Users\\owner\\Code\\jarvis-desktop", coding.folder!!.path)
        val cmd = coding.benchList.first { it.kind == "command" }
        assertEquals("pytest -q", cmd.command)
        assertTrue(cmd.notRunnableWhy.contains("nothing runs yet"))
        val run = Projects.parseBench(cases["bench_run"]!!.jsonObject["benchmark"]!!.jsonObject)!!
        assertEquals(3, run.points!!.size)
        assertEquals(21.1, run.target!!, 1e-9)
        assertEquals("Better than last time (up 1.5).", run.said)
        // The real read carries the finish-time range too (3 numbers: 2 more needed), so the
        // spoken chart text is the numbers sentence, a space, then the PC's words as sent.
        assertEquals("not_enough", run.forecast!!.state)
        assertEquals("3 numbers. Latest: 12 km. Not enough numbers yet - 2 more needed.", Projects.chartSummary(run))
        val empty = Projects.parseBench(cases["bench_empty"]!!.jsonObject["benchmark"]!!.jsonObject)!!
        assertEquals(Projects.w("chart_empty"), Projects.chartSummary(empty))
    }

    @Test
    fun `private numbers and the mark - a card for Jarvis's own, instant for yours`() {
        val by = project("life").benchList.associateBy { it.name }
        assertFalse(by.getValue("Long run").keepOnScreen)
        assertNull(Projects.unmarkOffer(by.getValue("Long run")))
        for (n in listOf("Weight", "5k time", "Stretching")) assertTrue(n, by.getValue(n).keepOnScreen)
        assertEquals("card", Projects.unmarkOffer(by.getValue("5k time"))!!.kind)
        assertEquals(Projects.w("remove_mark_card"), Projects.unmarkOffer(by.getValue("Weight"))!!.why)
        assertEquals("instant", Projects.unmarkOffer(by.getValue("Stretching"))!!.kind)
        val waiting = project("life_waiting")
        assertTrue(waiting.shareableWaiting)
        val five = waiting.benchList.first { it.name == "5k time" }
        assertTrue(five.unmarkWaiting)
        assertNull("no second card while one waits", Projects.unmarkOffer(five))
        val answered = project("life_answered")
        assertTrue(answered.shareableLast.contains("you said no"))
        val five2 = answered.benchList.first { it.name == "5k time" }
        assertFalse(five2.keepOnScreen)
        assertTrue(five2.unmarkLast.contains("may read these numbers aloud"))
    }

    private fun reply(name: String): Projects.Reply {
        val p = posts[name]!!.jsonObject
        return Projects.Reply(p["status"]!!.jsonPrimitive.int, p["body"]!!.jsonObject)
    }

    @Test
    fun `answers to a change - done, a card, or the PC's own sentence`() {
        val card = Projects.said(reply("shareable_on"), "Done.")
        assertTrue(card.waiting)
        assertTrue(card.said.startsWith("Waiting for your approval"))
        val unmark = Projects.said(reply("unmark_card"), "Done.")
        assertTrue(unmark.waiting)
        val off = Projects.said(reply("shareable_off"), "Done.")
        assertFalse(off.waiting)
        assertTrue(off.changed)
        val yours = Projects.said(reply("unmark_yours"), "Done.")
        assertEquals("Your private mark is off.", yours.said)
        val phone = Projects.said(reply("folder_from_phone"), "Done.")
        assertFalse(phone.changed)
        assertTrue(phone.said.contains("on the PC only"))
        assertEquals("There is already a project with that name.", Projects.said(reply("name_twice"), "").said)
        assertEquals(Projects.MISSING, Projects.said(Projects.Reply(404, JsonObject(emptyMap())), "").said)
        assertEquals("No such project, benchmark or number.", Projects.said(reply("no_such"), "").said)
        // A private number stays out of what TalkBack reads out.
        val logged = Projects.said(reply("log"), "Logged.", quiet = true)
        assertEquals("Logged.", logged.said)
        assertNotNull(Projects.benchOf(reply("log")))
        assertEquals("Half marathon", Projects.projectOf(reply("create_life"))!!.name)
    }

    @Test
    fun `only real ids reach a URL, and the phone never sends a folder or a command`() {
        val p = "0".repeat(31) + "a"
        val b = "f".repeat(32)
        assertEquals("/api/projects/$p", Projects.projectPath(p))
        assertEquals("/api/projects/$p/benchmarks/$b?points=1000", Projects.benchPath(p, b, 5000))
        for (bad in listOf("", "../config", "ABCDEF0123456789ABCDEF0123456789")) {
            assertNull(Projects.projectPath(bad))
            assertNull(Projects.writePath("update", bad))
        }
        assertEquals("/api/projects/$p/benchmarks/$b/results/$b/delete", Projects.writePath("result_delete", p, b, b))
        assertEquals("/api/projects/$p/benchmarks/$b/unmark", Projects.writePath("unmark", p, b))
        assertNull(Projects.writePath("run", p, b))
        assertFalse(Projects.heldOnStale("shareable", on = false))
        assertTrue(Projects.heldOnStale("shareable", on = true))
        assertTrue(Projects.heldOnStale("log"))
        assertFalse(Projects.createBody("Run").contains("folder"))
        assertEquals("{\"name\":\"Run\",\"kind\":\"life\"}", Projects.createBody(" Run "))
        val (body, err) = Projects.benchBody(" Long run ", "km", "higher", "21,1")
        assertNull(err)
        assertEquals("{\"name\":\"Long run\",\"kind\":\"number\",\"unit\":\"km\",\"better\":\"higher\",\"target\":21.1}", body)
        assertNotNull(Projects.benchBody("", "", null, "").second)
        assertNotNull(Projects.benchBody("x", "", null, "far").second)
        assertEquals(72.5, Projects.valueFrom("72,5")!!, 1e-9)
        assertNull(Projects.valueFrom("five"))
        assertEquals(listOf("a", "b"), Projects.notesFrom("a\n\n b \n"))
        assertEquals(
            "{\"instructions\":\"Keep \\\"honest\\\"\",\"notes\":[\"a\",\"b\"]}",
            Projects.textBody("Keep \"honest\"", "a\nb"),
        )
    }
    // ------------------------------------------------ the finish-time range ----

    private val forecastCases = doc["forecast_cases"]!!.jsonArray.map { it.jsonObject }

    private fun pointsOf(c: JsonObject) = c["points"]!!.jsonArray.mapIndexed { i, el ->
        val o = el.jsonObject
        Projects.Point("p$i", o["at"]!!.jsonPrimitive.double, o["value"]!!.jsonPrimitive.double)
    }

    private fun targetOf(c: JsonObject) = c["target"]!!.jsonPrimitive.doubleOrNull

    /** The benchmark the phone would build from the PC's read of this case. */
    private fun benchOf(c: JsonObject): Projects.Bench {
        val pts = c["points"]!!.jsonArray
        val latest = pts.lastOrNull()?.jsonObject
        val text = buildString {
            append("{\"id\":\"b\",\"name\":\"Run\",\"unit\":\"min\",\"results\":${pts.size},")
            append("\"points\":${pts},")
            if (latest != null) append("\"latest\":{\"value\":${latest["value"]},\"at\":${latest["at"]}},")
            append("\"future_key\":{\"x\":1},\"forecast\":${c["forecast"]}}")
        }
        return Projects.parseBench(json.parseToJsonElement(text) as JsonObject)!!
    }

    @Test
    fun `every forecast reads and says the PC's words`() {
        assertEquals(16, forecastCases.size)
        for (c in forecastCases) {
            val name = c["name"]!!.jsonPrimitive.content
            val want = c["forecast"]!!.jsonObject
            val f = Projects.parseForecast(want)
            assertNotNull(name, f)
            assertEquals(name, want["state"]!!.jsonPrimitive.content, f!!.state)
            assertEquals(name, want["words"]!!.jsonPrimitive.content, f.words)
            assertEquals(name, want["basis"]!!.jsonPrimitive.content, f.basis)
            assertEquals(name, want["low_weeks"]!!.jsonPrimitive.intOrNull, f.lowWeeks)
            assertEquals(name, want["high_weeks"]!!.jsonPrimitive.intOrNull, f.highWeeks)
            assertEquals(name, want["used"]!!.jsonPrimitive.int, f.used)
            assertEquals(name, want["needed"]!!.jsonPrimitive.int, f.needed)
            // Only a range or an open-ended one has anything to draw; the other four are words alone.
            val drawn = f.state == "range" || f.state == "open_ended"
            assertEquals(name, drawn, f.drawable)
            assertEquals(name, drawn, f.line != null && f.band != null)
        }
        val by = forecastCases.associate { it["name"]!!.jsonPrimitive.content to Projects.parseForecast(it["forecast"]!!.jsonObject)!! }
        // Never is its own answer: no weeks, no line, and never "0 weeks".
        val never = by.getValue("flat")
        assertEquals("never", never.state)
        assertEquals(Projects.parseForecast(forecastCases.first { it["name"]!!.jsonPrimitive.content == "wrong_way" }["forecast"]!!.jsonObject)!!.state, "never")
        assertNull(never.lowWeeks)
        assertNull(never.highWeeks)
        assertFalse(never.words.contains("0 weeks"))
        assertEquals("Not reached at this pace.", never.words)
        assertEquals("You have reached your target.", by.getValue("reached").words)
        assertEquals("Set a target to see a pace.", by.getValue("no_target").words)
        // A range has both ends; open-ended has only the low end (105 = "more than 2 years").
        assertEquals(6, by.getValue("steady_fall").lowWeeks)
        assertNotNull(by.getValue("steady_fall").highWeeks)
        assertNull(by.getValue("very_scattered").highWeeks)
        assertNotNull(by.getValue("very_scattered").lowWeeks)
        assertTrue(by.getValue("more_than_two_years").overTwoYears)
        assertEquals("scattered", by.getValue("very_scattered").why)
        assertTrue(by.getValue("clipped_at_the_edge").line!!.clipped)
    }

    @Test
    fun `the chart's edges are the shared extent`() {
        for (c in forecastCases) {
            val name = c["name"]!!.jsonPrimitive.content
            val want = c["extent"]!!.jsonObject
            val x = want["x"]!!.jsonArray.map { it.jsonPrimitive.double }
            val y = want["y"]!!.jsonArray.map { it.jsonPrimitive.double }
            val e = Projects.forecastExtent(
                pointsOf(c), Projects.parseForecast(c["forecast"]!!.jsonObject), targetOf(c),
            )
            assertEquals(name, x[0], e.xLo, 1e-6)
            assertEquals(name, x[1], e.xHi, 1e-6)
            assertEquals(name, y[0], e.yLo, 1e-6)
            assertEquals(name, y[1], e.yHi, 1e-6)
        }
        // No forecast at all changes nothing.
        val pts = listOf(Projects.Point("a", 1.0, 10.0), Projects.Point("b", 3.0, 20.0))
        val plain = Projects.forecastExtent(pts, null, 25.0)
        val (lo, hi) = Projects.chartScale(listOf(10.0, 20.0), 25.0)
        assertEquals(1.0, plain.xLo, 1e-9)
        assertEquals(3.0, plain.xHi, 1e-9)
        assertEquals(lo, plain.yLo, 1e-9)
        assertEquals(hi, plain.yHi, 1e-9)
    }

    @Test
    fun `the dashed line, band, bracket and arrows land where the extent says`() {
        val w = 320f
        val h = 96f
        val inset = 8f
        for (c in forecastCases) {
            val name = c["name"]!!.jsonPrimitive.content
            val f = Projects.parseForecast(c["forecast"]!!.jsonObject)!!
            val d = Projects.forecastGeometry(pointsOf(c), f, targetOf(c), w, h, inset)
            if (!f.drawable) {
                assertNull("$name draws nothing but its words", d)
                continue
            }
            d!!
            val line = f.line!!
            val band = f.band!!
            // The picture grows to the right: the farthest end sits on the right edge, the first number on the left.
            val farthest = (listOf(d.lineTo.x, d.bandFast.x, d.bandSlow.x) + d.points.map { it.x }).max()
            assertEquals(name, w - inset, farthest, 0.01f)
            assertEquals(name, inset, d.points.first().x, 0.01f)
            for (p in d.points + listOf(d.lineFrom, d.lineTo, d.bandFrom, d.bandFast, d.bandSlow)) {
                assertTrue("$name x in the box", p.x in 0f..w)
                assertTrue("$name y in the box", p.y in 0f..h)
            }
            // The line starts on the first number's date and the band on the last number's.
            assertEquals(name, d.points.first().x, d.lineFrom.x, 0.01f)
            assertEquals(name, d.points.last().x, d.bandFrom.x, 0.01f)
            // A clipped or open end gets an arrow; nothing else does.
            assertEquals(name, line.clipped, d.arrowLine)
            assertEquals(name, band.fast.clipped, d.arrowFast)
            assertEquals(name, band.slow.clipped || band.slow.open, d.arrowSlow)
            // The bracket needs a target and both crossing dates; an open end has no bracket.
            val both = targetOf(c) != null && f.crossLowAt != null && f.crossHighAt != null
            assertEquals(name, both, d.bracketFrom != null && d.bracketTo != null)
            if (d.bracketFrom != null) assertTrue(name, d.bracketFrom!! <= d.bracketTo!!)
            if (band.slow.open) assertNull(name, d.bracketTo)
            // Lower is better, so the line falls in value: on the screen (y grows downward) it ends lower down.
            if (c["better"]!!.jsonPrimitive.content == "lower") {
                assertTrue("$name a falling line rises on the screen", d.lineTo.y >= d.lineFrom.y)
            }
        }
    }

    @Test
    fun `the screen reader hears the summary and the words`() {
        for (c in forecastCases) {
            val name = c["name"]!!.jsonPrimitive.content
            assertEquals(name, c["summary"]!!.jsonPrimitive.content, Projects.chartSummary(benchOf(c)))
        }
        val steady = benchOf(forecastCases.first { it["name"]!!.jsonPrimitive.content == "steady_fall" })
        assertEquals("5 numbers. Latest: 76 min. About 6 weeks at this pace.", Projects.chartSummary(steady))
        // No forecast (an older PC, or a list read): the old sentence, unchanged.
        assertEquals("5 numbers. Latest: 76 min.", Projects.chartSummary(steady.copy(forecast = null)))
    }

    @Test
    fun `a forecast with something missing draws nothing rather than guess`() {
        fun parse(text: String) = Projects.parseForecast(json.parseToJsonElement(text) as JsonObject)
        assertNull("no forecast", Projects.parseForecast(null))
        assertEquals("blank words keep the forecast", "", parse("""{"state":"range","words":""}""")!!.words)
        assertNull("no state", parse("""{"words":"About 6 weeks at this pace."}"""))
        val noBand = parse(
            """{"state":"range","words":"About 6 weeks at this pace.","future":[1,2],
                "line":{"from":{"at":1,"value":2},"to":{"at":3,"value":4},"clipped":false},"band":null}""",
        )!!
        assertEquals("About 6 weeks at this pace.", noBand.words)
        assertNull("a line without its band is not drawn", noBand.line)
        assertFalse(noBand.drawable)
        val halfCorner = parse(
            """{"state":"open_ended","words":"More than 2 years at this pace.",
                "line":{"from":{"at":1,"value":2},"to":{"at":3,"value":4},"clipped":true},
                "band":{"from":{"at":1,"value":2},"fast":{"at":3},"slow":{"at":3,"value":4,"open":true}}}""",
        )!!
        assertNull(halfCorner.band)
        assertNull(halfCorner.line)
        // A state we do not know keeps its words and draws nothing.
        val odd = parse("""{"state":"soon","words":"Soon.","line":{"from":{"at":1,"value":2},"to":{"at":3,"value":4}}}""")!!
        assertEquals("Soon.", odd.words)
        assertFalse(odd.drawable)
        // A bench read without `forecast` at all still reads (the real read has one; take it out).
        val real = cases["bench_run"]!!.jsonObject["benchmark"]!!.jsonObject
        assertNotNull(Projects.parseBench(real)!!.forecast)
        assertNull(Projects.parseBench(JsonObject(real - "forecast"))!!.forecast)
    }

    @Test
    fun `a forecast with blank words is still drawn, and only its words line is left out`() {
        val steady = forecastCases.first { it["name"]!!.jsonPrimitive.content == "steady_fall" }
        val want = steady["forecast"]!!.jsonObject
        val blank = JsonObject(want + ("words" to kotlinx.serialization.json.JsonPrimitive("")))
        val f = Projects.parseForecast(blank)!!
        assertEquals("", f.words)
        assertTrue("the drawing survives blank words", f.drawable)
        assertNotNull(Projects.forecastGeometry(pointsOf(steady), f, targetOf(steady), 300f, 96f, 8f))
        // The summary for a screen reader adds nothing after the chart's own sentence.
        assertEquals("5 numbers. Latest: 76 min.", Projects.chartSummary(benchOf(steady).copy(forecast = f)))
    }

    @Test
    fun `the chart is drawn by the same rule as the desktop's`() {
        // docs/GOALS-PROGRESS-DESIGN.md "Forecast drawing rule": the trend line and the band's
        // edge in the accent colour, dashed; the trend line under the numbers; the arrow is an
        // open chevron with its tip at the clip point. Read from the source - Compose cannot draw here.
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        var src: String? = null
        while (dir != null && src == null) {
            val f = File(dir, "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/ProjectsPlate.kt")
            if (f.isFile) src = f.readText()
            dir = dir.parentFile
        }
        val plate = src ?: error("ProjectsPlate.kt not found")
        val chart = plate.substring(plate.indexOf("private fun Chart("), plate.indexOf("private fun AddBench"))
        assertTrue("an open chevron, not a filled triangle", chart.contains("drawChevron") && !chart.contains("drawArrow"))
        val trend = chart.indexOf("fore.lineFrom.x")
        val numbers = chart.indexOf("for (pt in placed) drawCircle")
        assertTrue("the trend line is drawn under the numbers", trend in 0 until numbers)
        assertTrue("the band's edge is the accent colour", chart.contains("band, accent.copy(alpha = 0.7f)"))
        assertTrue("the trend line is the accent colour", chart.contains("accent, Offset(fore.lineFrom.x"))
        assertFalse("no grey trend colour any more", chart.contains("val trend = chrome.textMid"))
    }
}
