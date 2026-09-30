package com.jarvis.client

import com.jarvis.client.net.Progress
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull
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
 * The activity heatmap and balance chart on the phone (the owner's tick of
 * 2026-09-30, docs/JARVIS-API.md section 105), read from what the PC REALLY
 * answers.
 *
 * `contract/progress-cases.json` is written by tools/gen_progress_cases.py from
 * the real backend (jarvis_progress.py) - byte for byte the file the desktop's
 * progress.mjs builds against: the words, the worked heatmap cells, the worked
 * radar polygons, and the PC's refusals.
 */
class ProgressTest {

    private val json = Json { ignoreUnknownKeys = true }

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/progress-cases.json")) {
            "contract/progress-cases.json is missing - run tools/gen_progress_cases.py"
        }.readText()
        json.parseToJsonElement(text) as JsonObject
    }
    private val heat = doc["heat"]!!.jsonObject
    private val balance = doc["balance"]!!.jsonObject

    /** The words the backend must never send (jarvis_progress.FORBIDDEN_WORDS). */
    private val forbidden = listOf(
        "streak", "in a row", "longest", "missed", "keep it up", "don't break", "percent", "average", "points",
    )

    private fun heatOf(name: String): Progress.Heat = Progress.parseHeat(heat[name]!!.jsonObject)!!

    private fun balanceOf(name: String): Progress.Balance = Progress.parseBalance(balance[name]!!.jsonObject)!!

    @Test
    fun `the words are the desktop's, word for word`() {
        val words = doc["words"]!!.jsonObject
        assertEquals(words.keys, Progress.WORDS.keys)
        for ((k, v) in words) assertEquals(k, v.jsonPrimitive.content, Progress.WORDS[k])
    }

    @Test
    fun `no streak or score-keeping word in the app's own strings`() {
        for ((k, v) in Progress.WORDS) {
            for (bad in forbidden) assertFalse("$k has '$bad'", v.lowercase().contains(bad))
        }
    }

    @Test
    fun `the limits and the shading ladder are the contract's`() {
        val limits = doc["limits"]!!.jsonObject
        assertEquals(limits["axes_min"]!!.jsonPrimitive.content.toInt(), Progress.AXES_MIN)
        assertEquals(limits["axes_max"]!!.jsonPrimitive.content.toInt(), Progress.AXES_MAX)
        assertEquals(limits["label_max"]!!.jsonPrimitive.content.toInt(), Progress.LABEL_MAX)
        assertEquals(limits["weeks_default"]!!.jsonPrimitive.content.toInt(), Progress.WEEKS_DEFAULT)
        val alphas = doc["shading"]!!.jsonObject["alpha"]!!.jsonArray.map { it.jsonPrimitive.doubleOrNull!! }
        assertEquals(alphas.size, Progress.ALPHAS.size)
        for (i in alphas.indices) assertEquals(alphas[i], Progress.ALPHAS[i].toDouble(), 1e-6)
        // Neighbouring steps differ by at least 0.20 so the ladder holds in every theme.
        for (i in 1 until Progress.ALPHAS.size) {
            assertTrue(Progress.ALPHAS[i] - Progress.ALPHAS[i - 1] >= 0.20f - 1e-6f)
        }
        assertEquals(0.0f, Progress.alphaFor(-3), 0f)
        assertEquals(0.92f, Progress.alphaFor(9), 0f)
        val g = doc["heat_grid"]!!.jsonObject
        assertEquals(g["cell"]!!.jsonPrimitive.content.toInt(), Progress.CELL)
        assertEquals(g["gap"]!!.jsonPrimitive.content.toInt(), Progress.GAP)
        assertEquals(g["step"]!!.jsonPrimitive.content.toInt(), Progress.STEP)
        for ((weeks, size) in g["sizes"]!!.jsonObject) {
            val o = size.jsonObject
            assertEquals(o["width"]!!.jsonPrimitive.content.toInt(), Progress.heatWidth(weeks.toInt()))
            assertEquals(o["height"]!!.jsonPrimitive.content.toInt(), Progress.HEAT_HEIGHT)
        }
        val rc = doc["radar_constants"]!!.jsonObject
        assertEquals(rc["size"]!!.jsonPrimitive.content.toInt(), Progress.RADAR_SIZE)
        assertEquals(rc["radius"]!!.jsonPrimitive.doubleOrNull!!, Progress.RADAR_RADIUS, 1e-9)
        assertEquals(rc["label_offset"]!!.jsonPrimitive.doubleOrNull!!, Progress.RADAR_LABEL_OFFSET, 1e-9)
        assertEquals(rc["rings"]!!.jsonArray.map { it.jsonPrimitive.doubleOrNull!! }, Progress.RINGS)
    }

    @Test
    fun `every worked heatmap is drawn where the contract says`() {
        for ((name, v) in heat) {
            val o = v.jsonObject
            val h = heatOf(name)
            val want = o["rects"]!!.jsonArray.map { it.jsonObject }
            val got = Progress.heatRects(h.days)
            assertEquals(name, want.size, got.size)
            for (i in want.indices) {
                assertEquals("$name $i date", want[i]["date"]!!.jsonPrimitive.content, got[i].date)
                assertEquals("$name $i x", want[i]["x"]!!.jsonPrimitive.content.toInt(), got[i].x)
                assertEquals("$name $i y", want[i]["y"]!!.jsonPrimitive.content.toInt(), got[i].y)
                assertEquals("$name $i size", want[i]["size"]!!.jsonPrimitive.content.toInt(), got[i].size)
                assertEquals("$name $i level", want[i]["level"]!!.jsonPrimitive.content.toInt(), got[i].level)
            }
            val size = o["size"]!!.jsonObject
            assertEquals(name, size["width"]!!.jsonPrimitive.content.toInt(), Progress.heatWidth(h.weeks))
            assertEquals(name, size["height"]!!.jsonPrimitive.content.toInt(), Progress.HEAT_HEIGHT)
        }
    }

    @Test
    fun `a heatmap answer reads whole`() {
        val e = heatOf("empty")
        assertTrue(e.empty)
        assertEquals(12, e.weeks)
        assertEquals(12, e.columns.size)
        assertTrue(e.days.all { it.level == 0 })
        assertEquals(Progress.w("heat_empty").substringBefore("."), e.words.substringBefore("."))
        val one = heatOf("one_day")
        assertFalse(one.empty)
        assertTrue(one.days.any { it.level == 1 })
        assertTrue(one.summary.startsWith("Activity, last 12 weeks."))
        assertEquals(Progress.w("heat_undated"), one.note)
        // No future day: the last day of the last column is not past today.
        assertEquals(heat["one_day"]!!.jsonObject["today"]!!.jsonPrimitive.content, one.days.last().date)
    }

    @Test
    fun `the week rows are the screen reader's text`() {
        val h = heatOf("mixed_levels")
        val rows = Progress.weekRows(h)
        assertEquals(h.columns.size, rows.size)
        assertEquals(h.columns[0].label, rows[0].label)
        for (r in rows) {
            assertTrue(r.text.startsWith(r.label))
            assertTrue(r.label.startsWith("Week of "))
        }
        val first = h.days.filter { it.col == 0 }.sortedBy { it.row }.joinToString(". ") { it.words }
        assertEquals(h.columns[0].label + ": " + first, rows[0].text)
        // The last week may be short: only days up to today.
        val lastCol = h.columns.last().col
        val inLast = h.days.count { it.col == lastCol }
        assertTrue(inLast in 1..7)
        assertEquals(inLast, rows.last().text.removePrefix(rows.last().label + ": ").split(". ").size)
    }

    @Test
    fun `a private number shades its day and keeps the whole picture on screen`() {
        val h = heatOf("private_number")
        assertTrue(h.keepOnScreen)
        assertTrue(h.days.any { it.level > 0 })
        for (d in h.days) {
            for (bad in forbidden) assertFalse(d.words.lowercase().contains(bad))
        }
        val hidden = Progress.blankedHeat(h)
        assertTrue(hidden.days.isEmpty())
        assertTrue(hidden.columns.isEmpty())
        assertTrue(Progress.heatRects(hidden.days).isEmpty())
        assertEquals(h.hiddenWords, hidden.summary)
        assertEquals(Progress.w("hidden"), h.hiddenWords)
        assertTrue(Progress.weekRows(hidden).isEmpty())
    }

    @Test
    fun `the radar is drawn where the contract says`() {
        for ((name, v) in doc["radar_worked"]!!.jsonObject) {
            val o = v.jsonObject
            val fractions = o["fractions"]!!.jsonArray.map { (it as JsonPrimitive).doubleOrNull }
            sameRadar(name, o, Progress.radar(fractions))
        }
        for ((name, v) in balance) {
            val o = v.jsonObject
            val b = balanceOf(name)
            sameRadar(name, o["radar"]!!.jsonObject, Progress.radar(b.axes.map { it.fraction }))
        }
    }

    private fun sameRadar(name: String, want: JsonObject, got: Progress.Radar) {
        val tol = 0.01
        assertEquals(name, want["size"]!!.jsonPrimitive.content.toInt(), got.size)
        assertEquals(name, want["radius"]!!.jsonPrimitive.doubleOrNull!!, got.radius, tol)
        val rings = want["rings"]!!.jsonArray.map { it.jsonPrimitive.doubleOrNull!! }
        assertEquals(name, rings.size, got.rings.size)
        for (i in rings.indices) assertEquals("$name ring $i", rings[i], got.rings[i], tol)
        val spokes = want["spokes"]!!.jsonArray.map { it.jsonObject }
        assertEquals("$name spokes", spokes.size, got.spokes.size)
        val poly = want["polygon"]!!.jsonArray.map { it.jsonObject }
        val labels = want["labels"]!!.jsonArray.map { it.jsonObject }
        for (i in spokes.indices) {
            assertEquals("$name spoke $i x", spokes[i]["x"]!!.jsonPrimitive.doubleOrNull!!, got.spokes[i].x, tol)
            assertEquals("$name spoke $i y", spokes[i]["y"]!!.jsonPrimitive.doubleOrNull!!, got.spokes[i].y, tol)
            assertEquals("$name vert $i x", poly[i]["x"]!!.jsonPrimitive.doubleOrNull!!, got.polygon[i].x, tol)
            assertEquals("$name vert $i y", poly[i]["y"]!!.jsonPrimitive.doubleOrNull!!, got.polygon[i].y, tol)
            assertEquals(
                "$name vert $i dot",
                poly[i]["dot"]!!.jsonPrimitive.content.toBoolean(), got.polygon[i].dot,
            )
            assertEquals("$name label $i x", labels[i]["x"]!!.jsonPrimitive.doubleOrNull!!, got.labels[i].x, tol)
            assertEquals("$name label $i y", labels[i]["y"]!!.jsonPrimitive.doubleOrNull!!, got.labels[i].y, tol)
            assertEquals("$name label $i anchor", labels[i]["anchor"]!!.jsonPrimitive.content, got.labels[i].anchor)
        }
    }

    @Test
    fun `a balance answer reads whole and has no total`() {
        val b = balanceOf("five_areas_mixed")
        assertEquals(5, b.axes.size)
        assertTrue(b.drawable)
        assertTrue(b.axes.any { it.fraction == null })
        assertTrue(b.summary.endsWith("No overall score."))
        val none = balanceOf("nothing_picked")
        assertFalse(none.drawable)
        assertEquals(Progress.w("balance_none"), none.words)
        val gone = balanceOf("after_a_benchmark_is_deleted")
        assertFalse(gone.drawable)
        assertEquals(2, gone.axes.size)
        assertEquals(Progress.w("balance_few"), gone.words)
        for (name in balance.keys) {
            val x = balanceOf(name)
            for (bad in forbidden) {
                assertFalse("$name summary", x.summary.lowercase().contains(bad))
                for (a in x.axes) assertFalse("$name ${a.label}", axisText(a).lowercase().contains(bad))
            }
        }
    }

    private fun axisText(a: Progress.Axis) = Progress.axisLine(a)

    @Test
    fun `an area with no numbers reads as no numbers yet`() {
        val a = Progress.Axis(
            label = "Running", short = "Running", name = "Running", kind = "bench", ref = "r", project = "p",
            state = "no_numbers", valueWords = "", fraction = null, keepOnScreen = false,
        )
        assertEquals("Running: no numbers yet", Progress.axisLine(a))
        val b = balanceOf("three_areas")
        assertEquals(b.axes[0].label + ": " + b.axes[0].valueWords, Progress.axisLine(b.axes[0]))
    }

    @Test
    fun `hidden lists blank a private balance answer and its picker`() {
        val b = balanceOf("target_reached_private")
        assertTrue(b.keepOnScreen)
        val hidden = Progress.blankedBalance(b)
        assertTrue(hidden.axes.isEmpty())
        assertFalse(hidden.drawable)
        assertEquals(b.hiddenWords, hidden.summary)
        val private = hidden.choices.filter { c -> b.choices.first { it.ref == c.ref }.keepOnScreen }
        assertTrue(private.isNotEmpty())
        for (c in private) {
            assertEquals(Progress.HIDDEN_NAME, c.name)
            assertFalse(Progress.choiceTickable(c))
        }
        for (c in hidden.choices - private.toSet()) assertTrue(Progress.choiceTickable(c))
        // No private name survives anywhere.
        val flat = hidden.toString()
        for (c in b.choices.filter { it.keepOnScreen }) assertFalse(flat.contains(c.name))
        // A public balance answer is left alone.
        val open = balanceOf("three_areas").copy(
            keepOnScreen = false,
            axes = balanceOf("three_areas").axes.map { it.copy(keepOnScreen = false) },
        )
        assertEquals(open.axes, Progress.blankedBalance(open).axes)
    }

    @Test
    fun `the picker allows 3 to 8, or none to clear`() {
        for (n in 0..9) assertEquals("n=$n", n == 0 || n in 3..8, Progress.canSave(n))
        assertTrue(Progress.canPickMore(7))
        assertFalse(Progress.canPickMore(8))
        assertEquals(Progress.w("balance_clear"), Progress.saveLabel(0))
        assertEquals(Progress.w("balance_save"), Progress.saveLabel(3))
        assertEquals(24, Progress.clipLabel("x".repeat(40)).length)
        val b = balanceOf("three_areas")
        assertEquals(b.axes.map { it.ref }, Progress.picksFrom(b).map { it.ref })
    }

    @Test
    fun `the save body is the PC's shape`() {
        val body = json.parseToJsonElement(
            Progress.saveBody(listOf(Progress.Pick("bench", "abc", "Fitness"), Progress.Pick("goal", "g1", "  "))),
        ).jsonObject
        val axes = body["axes"]!!.jsonArray
        assertEquals(2, axes.size)
        assertEquals("bench", axes[0].jsonObject["kind"]!!.jsonPrimitive.content)
        assertEquals("abc", axes[0].jsonObject["ref"]!!.jsonPrimitive.content)
        assertEquals("Fitness", axes[0].jsonObject["label"]!!.jsonPrimitive.content)
        assertFalse("a blank name is left out", axes[1].jsonObject.containsKey("label"))
        assertEquals("""{"axes":[]}""", Progress.saveBody(emptyList()))
    }

    @Test
    fun `a refusal is shown as the PC sent it, and changes nothing`() {
        val refusals = doc["refusals"]!!.jsonObject
        assertTrue(refusals.size >= 5)
        for ((name, v) in refusals) {
            val o = v.jsonObject
            val body = JsonObject(mapOf("ok" to JsonPrimitive(false), "error" to o["error"]!!))
            val out = Progress.saved(Progress.Reply(o["status"]!!.jsonPrimitive.content.toInt(), body))
            assertFalse(name, out.ok)
            assertEquals(name, o["error"]!!.jsonPrimitive.content, out.said)
            assertNull(name, out.balance)
        }
        assertEquals("Not changed.", Progress.saved(Progress.Reply(500, null)).said)
    }

    @Test
    fun `a saved chart comes back as the new answer`() {
        val out = Progress.saved(Progress.Reply(200, balance["three_areas"]!!.jsonObject))
        assertTrue(out.ok)
        assertNotNull(out.balance)
        assertEquals(3, out.balance!!.axes.size)
    }

    @Test
    fun `an older PC, an unavailable answer and unknown keys are handled`() {
        assertTrue(Progress.isMissing(Progress.Reply(404, null)))
        assertTrue(Progress.isMissing(Progress.Reply(501, null)))
        val own = JsonObject(mapOf("ok" to JsonPrimitive(false), "error" to JsonPrimitive("nope")))
        assertFalse("the PC's own 404 is an answer, not a missing route", Progress.isMissing(Progress.Reply(404, own)))
        assertNull(Progress.readProblem(Progress.Reply(404, null)))
        assertEquals("nope", Progress.readProblem(Progress.Reply(404, own)))
        assertEquals("Couldn't read it right now.", Progress.readProblem(Progress.Reply(500, null)))
        val down = JsonObject(mapOf("ok" to JsonPrimitive(false), "available" to JsonPrimitive(false)))
        assertNull(Progress.parseHeat(down))
        assertNull(Progress.parseBalance(down))
        val bare = Progress.parseHeat(JsonObject(mapOf("ok" to JsonPrimitive(true), "new_key" to JsonArray(emptyList()))))!!
        assertTrue(bare.days.isEmpty())
        assertEquals(Progress.w("hidden"), bare.hiddenWords)
        val bareB = Progress.parseBalance(JsonObject(emptyMap()))!!
        assertTrue(bareB.axes.isEmpty())
        assertFalse(bareB.drawable)
        assertEquals(3, bareB.min)
        assertEquals(8, bareB.max)
    }
}
