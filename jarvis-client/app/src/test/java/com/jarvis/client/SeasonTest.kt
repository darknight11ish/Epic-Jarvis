package com.jarvis.client

import com.jarvis.client.face.Season
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.double
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

/**
 * The seasonal touches are the same on the phone as on the desktop (the
 * owner's decision of 2026-09-28, "seasonal touches from the date, off by
 * default").
 *
 * The two apps cannot share code, so each has its own copy: `season.js` on
 * the desktop and [Season] here. `tools/gen_season.py` runs the JavaScript
 * at fixed moments and saves the answers in `season-golden.json`; this
 * checks the Kotlin copy gives the same ones - the calendar (which season,
 * which holiday, how far faded, in both halves of the world and several
 * time zones), the approval/error hold, the shapes, and every drawing step
 * of every scene. If it fails after a change to one copy, make the same
 * change to the other and re-run the generator. What the touches promise
 * (calm, behind the face, never a state colour) is checked by the desktop's
 * `tests/season.mjs`.
 */
class SeasonTest {

    private val golden: JsonObject by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("season-golden.json")) {
            "season-golden.json is missing from test resources - run tools/gen_season.py"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    private fun near(what: String, want: Double, got: Double, tol: Double = 1e-6) {
        assertTrue("$what: desktop $want, phone $got", abs(want - got) <= tol)
    }

    private fun JsonObject.d(key: String) = getValue(key).jsonPrimitive.double
    private fun JsonObject.dOrNull(key: String) = (this[key] as? JsonPrimitive)?.doubleOrNull

    @Test
    fun tablesMatch() {
        val layout = golden.getValue("layout").jsonObject
        near("floor", layout.d("FLOOR"), Season.FLOOR)
        near("left", layout.d("LEFT_X"), Season.LEFT_X)
        near("right", layout.d("RIGHT_X"), Season.RIGHT_X)
        near("lights top", layout.d("LIGHTS_TOP"), Season.LIGHTS_TOP)
        near("lights sag", layout.d("LIGHTS_SAG"), Season.LIGHTS_SAG)
        near("sparkle", golden.d("sparkle_s"), Season.SPARKLE_S)
        val seasons = golden.getValue("seasons").jsonArray.map { it.jsonArray }
        assertEquals(seasons.size, Season.SEASONS.size)
        seasons.forEachIndexed { i, s ->
            assertEquals(s[0].jsonPrimitive.content, Season.SEASONS[i].first)
            assertEquals(s[1].jsonPrimitive.int, Season.SEASONS[i].second)
            assertEquals(s[2].jsonPrimitive.int, Season.SEASONS[i].third)
        }
        val holidays = golden.getValue("holidays").jsonArray.map { it.jsonArray }
        assertEquals(holidays.size, Season.HOLIDAYS.size)
        holidays.forEachIndexed { i, h ->
            assertEquals(h[0].jsonPrimitive.content, Season.HOLIDAYS[i].first)
            for (j in 0 until 4) assertEquals(h[j + 1].jsonPrimitive.int, Season.HOLIDAYS[i].second[j])
        }
        golden.getValue("snowman").jsonArray.forEachIndexed { i, v -> assertEquals(v.jsonPrimitive.int, Season.SNOWMAN[i]) }
        for ((key, table) in listOf("leaf_rgb" to Season.LEAF_RGB, "petal_rgb" to Season.PETAL_RGB, "bulb_rgb" to Season.BULB_RGB)) {
            val rows = golden.getValue(key).jsonArray
            assertEquals("$key count", rows.size, table.size)
            rows.forEachIndexed { i, row ->
                row.jsonArray.forEachIndexed { j, v -> near("$key[$i][$j]", v.jsonPrimitive.double, table[i][j]) }
            }
        }
        val shapes = golden.getValue("shapes").jsonObject
        for ((key, got) in listOf("leaf" to Season.leafShape(), "petal" to Season.petalShape(), "glint" to Season.glintShape())) {
            val want = shapes.getValue(key).jsonArray
            assertEquals("$key points", want.size, got.size)
            want.forEachIndexed { i, p ->
                near("$key[$i].x", p.jsonArray[0].jsonPrimitive.double, got[i][0])
                near("$key[$i].y", p.jsonArray[1].jsonPrimitive.double, got[i][1])
            }
        }
    }

    @Test
    fun calendarMatches() {
        for (c in golden.getValue("civil").jsonArray.map { it.jsonObject }) {
            val days = c.d("days")
            val ymd = Season.civilFromDays(days)
            c.getValue("ymd").jsonArray.forEachIndexed { i, v -> assertEquals("civil $days", v.jsonPrimitive.int, ymd[i]) }
            near("back $days", c.d("back"), Season.daysFromCivil(ymd[0], ymd[1], ymd[2]))
        }
        for (c in golden.getValue("calendars").jsonArray.map { it.jsonObject }) {
            val at = "at ${c.d("ms")} tz ${c.d("tz")} lat ${c["lat"]}"
            val k = Season.calendar(c.d("ms"), c.d("tz"), c.dOrNull("lat"))
            assertEquals("south $at", c.getValue("south").jsonPrimitive.booleanOrNull, k.south)
            assertEquals("season $at", c.getValue("season").jsonPrimitive.content, k.season)
            val local = c.getValue("local").jsonArray
            assertEquals("year $at", local[0].jsonPrimitive.int, k.local.y)
            assertEquals("month $at", local[1].jsonPrimitive.int, k.local.m)
            assertEquals("day $at", local[2].jsonPrimitive.int, k.local.d)
            near("hour $at", local[3].jsonPrimitive.double, k.local.hour)
            for ((name, v) in c.getValue("seasons").jsonObject) near("$name $at", v.jsonPrimitive.double, k.seasons.getValue(name))
            for ((name, v) in c.getValue("day").jsonObject) near("day $name $at", v.jsonPrimitive.double, k.day.getValue(name), 1e-5)
            for ((name, v) in c.getValue("items").jsonObject) near("$name $at", v.jsonPrimitive.double, k.items.getValue(name))
            near("sparkle sec $at", c.d("sparkleSec"), k.sparkleSec, 1e-3)
        }
    }

    @Test
    fun holdMatches() {
        for (h in golden.getValue("holds").jsonArray.map { it.jsonObject }) {
            val st = h.getValue("state").jsonPrimitive.content
            val prev = h.getValue("prev").jsonPrimitive.content
            near("hold $st from $prev at ${h.d("since")}", h.d("w"), Season.holdWeight(st, prev, h.d("since")))
        }
    }

    @Test
    fun scenesMatch() {
        for (c in golden.getValue("scenes").jsonArray.map { it.jsonObject }) {
            val o = c.getValue("opts").jsonObject
            val sc = Season.scene(
                c.d("ms"), c.d("tz"), c.d("t"),
                lat = o.dOrNull("lat"),
                calm = (o["calm"] as? JsonPrimitive)?.booleanOrNull ?: false,
                hide = o.dOrNull("hide") ?: 0.0, hold = o.dOrNull("hold") ?: 0.0,
                ax0 = o.dOrNull("ax") ?: 1.0, ay0 = o.dOrNull("ay") ?: 1.0,
                sunAlt0 = o.dOrNull("sunAlt"),
                snow = o.dOrNull("snow") ?: 0.0, rain = o.dOrNull("rain") ?: 0.0,
                snowman = (o["snowman"] as? JsonPrimitive)?.booleanOrNull ?: true,
            )
            val at = "scene at ${c.d("ms")} ${c["opts"]}"
            assertEquals("season $at", c.getValue("season").jsonPrimitive.content, sc.season)
            near("ax $at", c.d("ax"), sc.ax)
            near("ay $at", c.d("ay"), sc.ay)
            val ops = c.getValue("ops").jsonArray
            assertEquals("step count $at", ops.size, sc.ops.size)
            ops.forEachIndexed { i, e ->
                val row = e.jsonArray
                assertEquals("step $i kind $at", row[0].jsonPrimitive.int, sc.ops[i].k)
                assertEquals("step $i length $at", row.size - 1, sc.ops[i].v.size)
                for (j in 1 until row.size) {
                    near("step $i[$j] $at", row[j].jsonPrimitive.double, sc.ops[i].v[j - 1])
                }
            }
        }
    }

    @Test
    fun nothingWhenHidden() {
        val ms = 1_798_000_000_000.0
        val sc = Season.scene(ms, 0.0, ms / 1000, lat = 40.0, hide = 1.0)
        assertTrue("Still or a serious moment: nothing is drawn", sc.ops.isEmpty())
    }
}
