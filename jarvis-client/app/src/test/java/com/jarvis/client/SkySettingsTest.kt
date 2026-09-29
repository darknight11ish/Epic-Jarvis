package com.jarvis.client

import com.jarvis.client.face.Sky
import com.jarvis.client.net.SkySettings
import kotlinx.serialization.json.Json
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
 * "Sun, moon and weather" on the phone reads what the PC really answers
 * (`contract/sky-cases.json`, made by `tools/gen_sky_cases.py` from the real
 * `jarvis_sky.view()`), shows the PC's words, sends only the changes a phone
 * may send (never a town), and keeps only the rounded position and the
 * weather numbers.
 */
class SkySettingsTest {

    private val doc: JsonObject by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("contract/sky-cases.json")) {
            "contract/sky-cases.json is missing - run tools/gen_sky_cases.py"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    private fun case(name: String): JsonObject = doc.getValue("cases").jsonObject.getValue(name).jsonObject

    @Test
    fun everyRealAnswerIsReadInThePcsWords() {
        for ((name, v) in doc.getValue("cases").jsonObject) {
            val parsed = SkySettings.parse(v.jsonObject)
            assertNotNull(name, parsed)
            val view = parsed!!
            val o = v.jsonObject
            assertEquals(name, o.getValue("show_label").jsonPrimitive.content, view.showLabel)
            assertEquals(name, o.getValue("weather").jsonObject.getValue("status").jsonPrimitive.content, view.status)
            assertEquals(name, listOf("off", "home_assistant", "open_meteo"), view.choices.map { it.id })
        }
        assertEquals(doc.getValue("missing").jsonPrimitive.content, SkySettings.MISSING)
        // The fallbacks are the PC's own words, word for word.
        val choices = doc.getValue("choices").jsonArray.map { it.jsonObject }
        choices.forEachIndexed { i, c ->
            assertEquals(c.getValue("label").jsonPrimitive.content, SkySettings.CHOICES[i].label)
            assertEquals(c.getValue("why").jsonPrimitive.content, SkySettings.CHOICES[i].why)
        }
        val off = case("off")
        assertEquals(off.getValue("show_label").jsonPrimitive.content, SkySettings.SHOW_LABEL)
        assertEquals(off.getValue("show_detail").jsonPrimitive.content, SkySettings.SHOW_DETAIL)
        assertEquals(off.getValue("place_none").jsonPrimitive.content, SkySettings.PLACE_NONE)
        assertEquals(case("town_on_the_phone").getValue("place_detail").jsonPrimitive.content, SkySettings.PLACE_PHONE)
    }

    @Test
    fun offByDefaultDrawsNothing() {
        val v = SkySettings.parse(case("off"))!!
        assertFalse(v.show)
        assertNull(v.place)
        assertEquals("off", v.source)
        assertNull(SkySettings.storedOf(v).live(1_759_000_000_000L))
    }

    @Test
    fun rainFromThePcIsDrawnAndKeptWithoutTheTownsName() {
        val v = SkySettings.parse(case("open_meteo_rain"))!!
        assertEquals("open_meteo", v.source)
        assertEquals(0.6, v.now!!.rain, 1e-9)
        assertEquals(-1, v.now!!.dir)
        val stored = SkySettings.storedOf(v)
        val text = SkySettings.encode(stored)
        assertFalse("never the town's name", text.contains("Denver"))
        assertEquals(stored, SkySettings.decode(text))
        val live = stored.live(v.nowAtMs + 60_000)!!
        assertEquals(Sky.Place(39.7, -105.0), live.place)
        assertEquals(0.6, live.weather!!.rain, 1e-9)
        // Ninety minutes on, the shower is no longer drawn; the sun and moon are.
        val later = stored.live(v.nowAtMs + 3 * 3600_000L)!!
        assertNull(later.weather)
        assertNotNull(later.place)
    }

    @Test
    fun onlyThePhonesChangesAreSent() {
        assertEquals("""{"show":true}""", SkySettings.showBody(true))
        assertEquals("""{"forget_place":true}""", SkySettings.forgetBody())
        assertEquals("""{"weather":"open_meteo"}""", SkySettings.weatherBody("open_meteo"))
        assertNull(SkySettings.weatherBody("brave"))
        // Adding waits for a live link; taking away never does.
        assertTrue(SkySettings.adds(SkySettings.showBody(true)))
        assertTrue(SkySettings.adds(SkySettings.weatherBody("home_assistant")!!))
        assertFalse(SkySettings.adds(SkySettings.showBody(false)))
        assertFalse(SkySettings.adds(SkySettings.forgetBody()))
        assertFalse(SkySettings.adds(SkySettings.weatherBody("off")!!))
        // Damaged storage is "nothing kept", never a guess.
        assertEquals(SkySettings.Stored(false, null, null, 0L), SkySettings.decode("{nope"))
        assertEquals(SkySettings.Stored(false, null, null, 0L), SkySettings.decode(null))
    }
}
