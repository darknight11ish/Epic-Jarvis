package com.jarvis.client

import com.jarvis.client.face.Sky
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.double
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

/**
 * The sun, the moon and the weather are the same on the phone as on the
 * desktop (the owner's decisions of 2026-09-28, "Sun and moon behind the
 * animals" and "Weather in the animals' scene").
 *
 * The two apps cannot share code, so each has its own copy: `sky.js` on the
 * desktop and [Sky] here. `tools/gen_sky.py` runs the JavaScript at fixed
 * moments and places and saves the answers in `sky-golden.json`; this checks
 * the Kotlin copy gives the same ones. If it fails after a change to one
 * copy, make the same change to the other and re-run the generator. The
 * astronomy itself is checked against published times by the desktop's
 * `tests/sky.mjs`.
 */
class SkyTest {

    private val golden: JsonObject by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("sky-golden.json")) {
            "sky-golden.json is missing from test resources - run tools/gen_sky.py"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    private fun near(what: String, want: Double, got: Double, tol: Double = 1e-6) {
        assertTrue("$what: desktop $want, phone $got", abs(want - got) <= tol)
    }

    /** Angles compared round the circle, so 359.9999999 and 0 agree. */
    private fun nearAngle(what: String, want: Double, got: Double) {
        val d = abs(((want - got) % 360 + 540) % 360 - 180)
        assertTrue("$what: desktop $want, phone $got", d <= 1e-6)
    }

    private fun JsonObject.d(key: String) = getValue(key).jsonPrimitive.double

    private fun weatherOf(e: JsonElement?): Sky.Weather? {
        val o = e as? JsonObject ?: return null
        return Sky.Weather(
            o.d("rain"), o.d("snow"), o.d("wind"), o.d("cloud"), o.d("fog"),
            o.getValue("dir").jsonPrimitive.int,
        )
    }

    private fun placeOf(e: JsonElement?): Sky.Place? {
        val o = e as? JsonObject ?: return null
        return Sky.Place(o.d("lat"), o.d("lon"))
    }

    @Test
    fun namesAndTablesMatch() {
        val phases = golden.getValue("phases").jsonArray.map { it.jsonPrimitive.content }
        assertEquals(phases, Sky.PHASES)
        val layout = golden.getValue("layout").jsonObject
        near("horizon", layout.d("HORIZON"), Sky.HORIZON)
        near("rx", layout.d("RX"), Sky.RX)
        near("ry", layout.d("RY"), Sky.RY)
        near("sun r", layout.d("SUN_R"), Sky.SUN_R)
        near("moon r", layout.d("MOON_R"), Sky.MOON_R)
        golden.getValue("tint").jsonArray.forEachIndexed { i, row ->
            row.jsonArray.forEachIndexed { j, v -> near("tint[$i][$j]", v.jsonPrimitive.double, Sky.TINT[i][j]) }
        }
        golden.getValue("tints").jsonArray.forEach { row ->
            val alt = row.jsonArray[0].jsonPrimitive.double
            val got = Sky.tintAt(alt)
            row.jsonArray[1].jsonArray.forEachIndexed { j, v -> near("tintAt($alt)[$j]", v.jsonPrimitive.double, got[j]) }
        }
        golden.getValue("hashes").jsonArray.forEach { row ->
            val n = row.jsonArray[0].jsonPrimitive.int
            near("hash01($n)", row.jsonArray[1].jsonPrimitive.double, Sky.hash01(n), 1e-9)
        }
    }

    @Test
    fun sunAndMoonMatch() {
        for (c in golden.getValue("bodies").jsonArray.map { it.jsonObject }) {
            val ms = c.d("ms")
            val lat = c.d("lat")
            val lon = c.d("lon")
            val at = "at $ms, $lat, $lon"
            nearAngle("gmst $at", c.d("gmst"), Sky.gmst(ms))
            val s = Sky.sun(ms, lat, lon)
            val ws = c.getValue("sun").jsonObject
            near("sun alt $at", ws.d("alt"), s.alt)
            nearAngle("sun az $at", ws.d("az"), s.az)
            nearAngle("sun H $at", ws.d("H"), s.h)
            nearAngle("sun ra $at", ws.d("ra"), s.ra)
            near("sun dec $at", ws.d("dec"), s.dec)
            val m = Sky.moon(ms, lat, lon)
            val wm = c.getValue("moon").jsonObject
            near("moon alt $at", wm.d("alt"), m.alt)
            near("moon altGeo $at", wm.d("altGeo"), m.altGeo)
            nearAngle("moon az $at", wm.d("az"), m.az)
            nearAngle("moon H $at", wm.d("H"), m.h)
            near("moon dec $at", wm.d("dec"), m.dec)
            near("moon parallax $at", wm.d("parallax"), m.parallax)
            nearAngle("moon elong $at", wm.d("elong"), m.elong)
            near("moon fraction $at", wm.d("fraction"), m.fraction)
            assertEquals("moon waxing $at", wm.getValue("waxing").jsonPrimitive.boolean, m.waxing)
            assertEquals("moon phase $at", wm.getValue("phase").jsonPrimitive.int, m.phase)
            nearAngle("moon chi $at", wm.d("chi"), m.chi)
            nearAngle("moon tilt $at", wm.d("tilt"), m.tilt)

            val sm = Sky.summary(ms, lat, lon)
            val w = c.getValue("summary").jsonObject
            fun time(what: String, key: String, got: Long?) {
                val want = (w[key] as? JsonPrimitive)?.doubleOrNull?.toLong()
                if (want == null) assertNull("$what $at", got)
                else assertTrue("$what $at: desktop $want, phone $got", got != null && abs(got - want) <= 2000)
            }
            assertEquals("sun up $at", w.getValue("sunUp").jsonPrimitive.boolean, sm.sunUp)
            assertEquals("moon up $at", w.getValue("moonUp").jsonPrimitive.boolean, sm.moonUp)
            time("sunrise", "sunrise", sm.sunrise)
            time("sunset", "sunset", sm.sunset)
            time("moonrise", "moonrise", sm.moonrise)
            time("moonset", "moonset", sm.moonset)
            assertEquals("phase name $at", w.getValue("phaseName").jsonPrimitive.content, sm.phaseName)
            assertEquals("percent $at", w.getValue("percent").jsonPrimitive.int, sm.percent)
            val utc = java.text.SimpleDateFormat("HH:mm").apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }
            assertEquals(
                "the settings line $at", c.getValue("today").jsonPrimitive.content,
                Sky.todayWords(sm) { utc.format(java.util.Date(it)) },
            )
        }
    }

    private fun rows(what: String, want: JsonElement?, got: List<DoubleArray>) {
        val arr = want?.jsonArray ?: JsonArray(emptyList())
        assertEquals("$what count", arr.size, got.size)
        arr.forEachIndexed { i, row ->
            row.jsonArray.forEachIndexed { j, v -> near("$what[$i][$j]", v.jsonPrimitive.double, got[i][j]) }
        }
    }

    @Test
    fun scenesMatch() {
        for (c in golden.getValue("scenes").jsonArray.map { it.jsonObject }) {
            val opts = c.getValue("opts").jsonObject
            val sc = Sky.scene(
                c.d("ms"), c.d("t"), placeOf(c["place"]), weatherOf(c["weather"]),
                calm = (opts["calm"] as? JsonPrimitive)?.booleanOrNull ?: false,
                ax0 = (opts["ax"] as? JsonPrimitive)?.doubleOrNull ?: 1.0,
                ay0 = (opts["ay"] as? JsonPrimitive)?.doubleOrNull ?: 1.0,
            )
            val want = c.getValue("scene").jsonObject
            val at = "scene at ${c.d("ms")}"
            near("ax $at", want.d("ax"), sc.ax)
            near("ay $at", want.d("ay"), sc.ay)
            val tint = want["tint"]
            if (tint == null || tint is JsonNull) assertNull(sc.tint) else {
                tint.jsonArray.forEachIndexed { j, v -> near("tint $at", v.jsonPrimitive.double, sc.tint!![j]) }
            }
            val glow = want["glow"]
            if (glow == null || glow is JsonNull) assertNull("glow $at", sc.glow) else {
                val g = glow.jsonObject
                val got = checkNotNull(sc.glow) { "glow $at" }
                near("glow x $at", g.d("x"), got.x); near("glow y $at", g.d("y"), got.y)
                near("glow r $at", g.d("r"), got.r); near("glow a $at", g.d("alpha"), got.alpha)
            }
            val sun = want["sun"]
            if (sun == null || sun is JsonNull) assertNull(sc.sun) else {
                val s = sun.jsonObject
                val got = checkNotNull(sc.sun)
                near("sun x $at", s.d("x"), got.x); near("sun y $at", s.d("y"), got.y)
                near("sun r $at", s.d("r"), got.r); near("sun alpha $at", s.d("alpha"), got.alpha)
                near("sun glow $at", s.d("glow"), got.glow); near("sun warm $at", s.d("warm"), got.warm)
            }
            val moon = want["moon"]
            if (moon == null || moon is JsonNull) assertNull(sc.moon) else {
                val m = moon.jsonObject
                val got = checkNotNull(sc.moon)
                near("moon x $at", m.d("x"), got.x); near("moon y $at", m.d("y"), got.y)
                near("moon alpha $at", m.d("alpha"), got.alpha); near("moon glow $at", m.d("glow"), got.glow)
                near("moon fraction $at", m.d("fraction"), got.fraction)
                assertEquals("moon phase $at", m.getValue("phase").jsonPrimitive.int, got.phase)
                near("moon bx $at", m.d("bx"), got.bx); near("moon by $at", m.d("by"), got.by)
            }
            near("cloudDay $at", want.d("cloudDay"), sc.cloudDay)
            near("fog $at", want.d("fog"), sc.fog)
            near("sunAlt $at", want.d("sunAlt"), sc.sunAlt)
            rows("clouds $at", want["clouds"], sc.clouds)
            rows("rain $at", want["rain"], sc.rain)
            rows("snow $at", want["snow"], sc.snow)
            rows("wisps $at", want["wisps"], sc.wisps)
        }
    }

    @Test
    fun moonOutlinesMatch() {
        for (c in golden.getValue("outlines").jsonArray.map { it.jsonObject }) {
            val pts = Sky.moonOutline(c.d("fraction"), c.d("bx"), c.d("by"), c.getValue("n").jsonPrimitive.int)
            rows("outline ${c.d("fraction")}", c["pts"], pts)
        }
    }

    @Test
    fun whatIsDrawnFollowsTheSettings() {
        val now = 1_760_000_000_000L
        val w = Sky.Weather(rain = 0.5)
        assertNull(Sky.liveInput(false, Sky.Place(40.7, -74.0), null, 0, now))
        assertEquals(Sky.Place(40.7, -74.0), Sky.liveInput(true, Sky.Place(40.7, -74.0), null, 0, now)?.place)
        // Weather on its own, without the sun and moon.
        val live = Sky.liveInput(false, Sky.Place(40.7, -74.0), w, now - 600_000, now)
        assertNull(live?.place)
        assertEquals(0.5, live?.weather?.rain ?: 0.0, 1e-9)
        // A shower read four hours ago is not drawn any more.
        assertNull(Sky.liveInput(false, null, w, now - 4 * 3600_000L, now))
        assertEquals(Sky.Place(40.7, -74.0), Sky.placeOf(40.71, -74.01))
        assertNull(Sky.placeOf(400.0, 0.0))
        assertNull(Sky.placeOf(null, 0.0))
        assertEquals(1.0, Sky.Weather(rain = 7.0, dir = 3).clean().rain, 0.0)
        assertEquals(1, Sky.Weather(dir = 3).clean().dir)
    }
}
