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
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

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
        assertEquals("3 numbers. Latest: 12 km.", Projects.chartSummary(run))
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
}
