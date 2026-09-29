package com.jarvis.client

import com.jarvis.client.data.FaceTuning
import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.QualityTier
import com.jarvis.client.net.AnimalOptions
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Animal options" on the phone reads what the PC really answers
 * (`contract/animal-cases.json`, made by `tools/gen_animal_cases.py` from the
 * real `jarvis_animal.py`): its fallback words are the PC's word for word,
 * it sends only a switch the PC lists, and "make the animal sharper"
 * (X-Jarvis-Route `face_tuning`) makes the same change on this phone that
 * the PC's own rule - and the desktop's - makes.
 */
class AnimalOptionsTest {

    private val doc: JsonObject by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("contract/animal-cases.json")) {
            "contract/animal-cases.json is missing - run tools/gen_animal_cases.py"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    private val view: JsonObject get() = doc.getValue("view").jsonObject
    private fun JsonObject.s(key: String) = getValue(key).jsonPrimitive.content

    @Test
    fun theFallbackWordsAreThePcsWordForWord() {
        val pc = view.getValue("switches").jsonArray.map { it.jsonObject }
        assertEquals(pc.map { it.s("id") }, AnimalOptions.SWITCHES.map { it.id })
        pc.forEachIndexed { i, o ->
            val here = AnimalOptions.SWITCHES[i]
            assertEquals(o.s("label"), here.label)
            assertEquals(o.s("detail"), here.detail)
            assertEquals(o.getValue("default").jsonPrimitive.boolean, here.default)
            assertEquals(o.getValue("built").jsonPrimitive.boolean, here.built)
        }
        assertEquals(view.s("title"), AnimalOptions.TITLE)
        assertEquals(view.s("intro"), AnimalOptions.INTRO)
        assertEquals(view.s("shared_title"), AnimalOptions.SHARED_TITLE)
        assertEquals(view.s("shared_note"), AnimalOptions.SHARED_NOTE)
        assertEquals(view.s("serious_note"), AnimalOptions.SERIOUS_NOTE)
        assertEquals(view.s("coming"), AnimalOptions.COMING)
        assertEquals(doc.s("missing"), AnimalOptions.MISSING)
    }

    @Test
    fun theOwnersDefaults() {
        assertEquals(
            mapOf(
                "still" to false, "nods" to true, "focus_buddy" to true, "acks" to true,
                "petting" to true, "cute_moments" to true, "seasonal" to false,
            ),
            AnimalOptions.DEFAULTS,
        )
        val d = doc.getValue("defaults").jsonObject.mapValues { it.value.jsonPrimitive.boolean }
        assertEquals(d, AnimalOptions.DEFAULTS)
    }

    @Test
    fun theRealAnswerIsRead() {
        val v = readView(AnimalOptions.parse(view))
        assertEquals(AnimalOptions.DEFAULTS, v.shared.values)
        assertEquals(7, v.switches.size)
        assertFalse(v.shared.still)
        assertNull("an older PC", AnimalOptions.parse(JsonObject(mapOf("available" to JsonPrimitive(false)))))
        assertNull("not an answer", AnimalOptions.parse(JsonObject(mapOf("title" to JsonPrimitive("x")))))
    }

    private fun readView(v: AnimalOptions.View?): AnimalOptions.View {
        assertTrue("the real answer was not read", v != null)
        return v!!
    }

    @Test
    fun onlyASwitchThePcListsIsSent() {
        assertEquals("""{"nods":false}""", AnimalOptions.body("nods", false))
        assertEquals("""{"still":true}""", AnimalOptions.body("still", true))
        assertNull(AnimalOptions.body("sparkles", true))
    }

    @Test
    fun theStepsAreThePcsForEveryChangeFromEveryStart() {
        val changes = doc.getValue("device_changes").jsonArray.map { it.jsonPrimitive.content }
        assertEquals(changes, AnimalOptions.DEVICE_CHANGES)
        for (c in doc.getValue("steps").jsonArray.map { it.jsonObject }) {
            val from = c.getValue("from").jsonObject
            val start = FaceTuning(
                quality = QualityTier.byId(from.s("quality")),
                frameRate = FrameRateTarget.byId(from.s("frameRate")),
                speed = 0.5f,
                autoAdjust = from.getValue("autoAdjust").jsonPrimitive.boolean,
                batterySaver = true,
            )
            val change = c.s("change")
            val got = AnimalOptions.step(start, change)
            val want = c.getValue("tuning").jsonObject
            val what = "${from} + $change"
            assertEquals(what, want.s("quality"), got.tuning.quality.id)
            assertEquals(what, want.s("frameRate"), got.tuning.frameRate.id)
            assertEquals(what, want.getValue("autoAdjust").jsonPrimitive.boolean, got.tuning.autoAdjust)
            assertEquals(what, c.getValue("changed").jsonPrimitive.boolean, got.changed)
            assertEquals(what, c.s("line"), got.line)
            assertEquals("speed kept", 0.5f, got.tuning.speed)
            assertTrue("battery saver kept", got.tuning.batterySaver)
        }
    }

    @Test
    fun onlyAListedChangeIsReadOffTheRoute() {
        assertEquals("sharper", AnimalOptions.fromRoute("""{"quick":"animal_device","face_tuning":"sharper"}"""))
        assertEquals("frame_rate:60", AnimalOptions.fromRoute("""{"face_tuning":"frame_rate:60"}"""))
        assertNull(AnimalOptions.fromRoute("""{"face_tuning":"rm -rf"}"""))
        assertNull(AnimalOptions.fromRoute("""{"face_tuning":3}"""))
        assertNull(AnimalOptions.fromRoute("""{"lane":"x"}"""))
        assertNull(AnimalOptions.fromRoute(null))
        assertNull(AnimalOptions.fromRoute("not json"))
        // Every answer the PC can give for one is on the list.
        for (k in doc.getValue("device_said").jsonObject.keys) {
            assertTrue(k, k in AnimalOptions.DEVICE_CHANGES)
        }
    }

    @Test
    fun stillIsThePcsOnceHeardAndAnOldOnCountsUntilItMoved() {
        val off = AnimalOptions.Shared(AnimalOptions.DEFAULTS)
        val on = AnimalOptions.Shared(AnimalOptions.DEFAULTS + ("still" to true))
        assertTrue("an older PC keeps this phone's own", AnimalOptions.effectiveStill(null, true, false))
        assertFalse(AnimalOptions.effectiveStill(null, false, false))
        assertTrue("an old 'on' lost before it moved", AnimalOptions.effectiveStill(off, true, false))
        assertFalse("after the move, the PC rules", AnimalOptions.effectiveStill(off, true, true))
        assertTrue(AnimalOptions.effectiveStill(on, false, true))
    }

    @Test
    fun theOldStillMovesOnlyBeforeAnyoneChose() {
        assertTrue("a PC nobody has changed", AnimalOptions.stillMoveNeeded(view))
        val chosen = Json.parseToJsonElement("""{"values":{"still":false},"changed":1759000000.5}""").jsonObject
        assertFalse("a choice made since wins", AnimalOptions.stillMoveNeeded(chosen))
        val on = Json.parseToJsonElement("""{"values":{"still":true},"changed":0}""").jsonObject
        assertFalse("already on", AnimalOptions.stillMoveNeeded(on))
        assertFalse(AnimalOptions.stillMoveNeeded(JsonObject(mapOf("available" to JsonPrimitive(false)))))
    }

    @Test
    fun whatThePhoneKeepsRoundTrips() {
        val s = AnimalOptions.Shared(AnimalOptions.DEFAULTS + ("nods" to false) + ("still" to true))
        assertEquals(s, AnimalOptions.decode(AnimalOptions.encode(s)))
        assertNull(AnimalOptions.decode(null))
        assertNull(AnimalOptions.decode("not json"))
        // A damaged value is that switch's default, never a guess.
        assertEquals(AnimalOptions.DEFAULTS, AnimalOptions.decode("""{"still":"yes"}""")!!.values)
    }
}
