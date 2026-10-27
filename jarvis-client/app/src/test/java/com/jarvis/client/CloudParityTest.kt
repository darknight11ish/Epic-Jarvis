package com.jarvis.client

import com.jarvis.client.net.FocusPresets
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The phone's READ-ONLY half of the cloud preset work (owner's asks of 2026-10-27):
 *
 *  - the additive `cloud` block on the same `/api/presets` answer must not disturb
 *    the five-preset list, and must be readable for one read-only sentence;
 *  - the phone must never offer the "escalate to the cloud" switch (turning it on
 *    is a loosening that needs the PC's approval card);
 *  - the two existing cloud indications - the per-answer sentence and the
 *    `LaneChip` - are pinned here because nothing pinned them before.
 *
 * Off-device, like [PresetsLandingTest]: data rules are exercised for real, the
 * Compose wiring and the no-write rule are held by reading the shipped source.
 * The on-phone look is a field-test row, not a pass.
 */
class CloudParityTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun source(rel: String): String = repoFile(main + rel).readText()

    private val cloudJson = """
        {"provider":"deepseek-flash","providers":["deepseek-flash","claude"],
         "escalate":{"on":true,"why":"set from the Presets menu"}}
    """.trimIndent()

    private fun cloudBlock(on: Boolean, provider: String = "deepseek-flash"): JsonObject =
        JarvisJson.parseToJsonElement(
            """{"provider":"$provider","providers":["$provider"],"escalate":{"on":$on,"why":""}}""",
        ) as JsonObject

    // --- the additive shape ---------------------------------------------------

    @Test
    fun `the additive cloud block does not disturb the five presets`() {
        val fixture = JarvisJson.parseToJsonElement(
            repoFile("backend/fixtures/work_presets.json").readText(),
        ) as JsonObject
        val without = requireNotNull(FocusPresets.parse(fixture)) { "the generated fixture did not parse" }

        val withCloud = JsonObject(
            fixture.toMutableMap() + ("cloud" to JarvisJson.parseToJsonElement(cloudJson)),
        )
        val parsed = requireNotNull(FocusPresets.parse(withCloud)) { "the fixture with a cloud block did not parse" }

        assertEquals(
            "the cloud block changed the preset rows",
            without.presets.map { it.id },
            parsed.presets.map { it.id },
        )
        assertEquals(without.chosen, parsed.chosen)
        val cloud = parsed.cloud
        assertNotNull("the cloud block was not read at all", cloud)
        assertEquals("deepseek-flash", cloud!!.provider)
        assertTrue("the PC's ON state was not read", cloud.escalateOn)
    }

    @Test
    fun `a PC without the cloud block sends nothing and the phone says nothing`() {
        val fixture = JarvisJson.parseToJsonElement(
            repoFile("backend/fixtures/work_presets.json").readText(),
        ) as JsonObject
        val view = requireNotNull(FocusPresets.parse(fixture))
        assertNull("an older PC's answer must leave cloud null", view.cloud)
    }

    // --- the one read-only sentence ------------------------------------------

    /**
     * The Lead's server shape keeps `why` and `providers[]` additive for the
     * desktop. This is the grep-testable expectation on the phone side: a cloud
     * block with ONLY `provider` and `escalate.on` must parse and read exactly
     * the same, and a missing `why` must never break the reader.
     */
    @Test
    fun `a cloud block with only on and provider still reads`() {
        val minimal = JarvisJson.parseToJsonElement(
            """{"presets":[{"id":"fast","title":"Fast",
                 "lane":{"key":"fast","card":"2080 SUPER","words":"the 2080 SUPER"},
                 "apply":{"action":"Use this preset","apply_route":"/api/work/apply"}}],
               "cloud":{"provider":"deepseek-flash","escalate":{"on":false}}}""",
        ) as JsonObject
        val view = requireNotNull(FocusPresets.parse(minimal)) { "the minimal cloud shape did not parse" }
        val cloud = requireNotNull(view.cloud) { "the minimal cloud block was not read" }
        assertEquals("deepseek-flash", cloud.provider)
        assertFalse(cloud.escalateOn)
        assertEquals("a missing why must not be invented", "", cloud.why)
        assertTrue(FocusPresets.cloudLine(cloud).contains("set on your PC"))
    }

    @Test
    fun `the cloud sentence says what the PC decided, and that it was set there`() {
        val on = FocusPresets.Cloud(provider = "deepseek-flash", escalateOn = true, why = "")
        val line = FocusPresets.cloudLine(on)
        assertTrue(line, line.contains("deepseek-flash"))
        assertTrue(line, line.contains("set on your PC"))
        assertFalse("the phone must never claim it sets this", line.contains("Turn on"))
        assertFalse("no switch words belong here", line.contains("tap to"))

        val off = FocusPresets.Cloud(provider = "deepseek-flash", escalateOn = false, why = "")
        val offLine = FocusPresets.cloudLine(off)
        assertTrue(offLine, offLine.contains("off"))
        assertTrue(offLine, offLine.contains("set on your PC"))

        // The provider name is the PC's; a blank one must not leave a dangling "through".
        val blank = FocusPresets.Cloud(provider = "", escalateOn = true, why = "")
        assertFalse(FocusPresets.cloudLine(blank).contains("through"))
    }

    @Test
    fun `the plate draws the sentence from the view and no control`() {
        val plate = source("ui/screens/FocusPresetsPlate.kt")
        assertTrue(
            "the plate never draws the PC's cloud state",
            plate.contains("view.cloud?.let") && plate.contains("FocusPresets.cloudLine("),
        )
        assertFalse(
            "the phone must not draw a cloud switch",
            plate.contains("Switch(") || plate.contains("Checkbox("),
        )
    }

    // --- the phone holds no cloud write at all -------------------------------

    @Test
    fun `no phone source can turn cloud escalation on or off`() {
        val root = repoFile(main + "net/FocusPresets.kt").parentFile!!.parentFile!! // .../jarvis/client
        val offenders = root.walkTopDown()
            .filter { it.isFile && it.name.endsWith(".kt") }
            .filter { f ->
                val t = f.readText()
                t.contains("cloud-escalate") ||
                    t.contains("cloud_escalate") ||
                    t.contains("/api/work/cloud")
            }
            .map { it.name }
            .toList()
        assertTrue("a phone file holds a cloud write: $offenders", offenders.isEmpty())
        // And the presets contract's ONE write stays the preset apply.
        assertEquals(
            "FocusPresets gained a second write route",
            1,
            source("net/FocusPresets.kt").split("const val APPLY_PATH").size - 1,
        )
    }

    // --- the indications that already existed, pinned now --------------------

    @Test
    fun `a cloud answer still says so in words`() {
        val chat = source("net/ChatSession.kt")
        assertTrue(
            "the cloud-answer sentence is gone, so a cloud turn would look local",
            chat.contains("\"Answered by a cloud model, not on your PC.\""),
        )
    }

    @Test
    fun `LaneChip still names Cloud and carries the model`() {
        val home = source("ui/screens/HomeScreen.kt")
        assertTrue("the Cloud lane word is gone from Home", home.contains("\"Cloud\" + (model?.let"))
        assertTrue("the local lane word is gone from Home", home.contains("\"Local\" + (model?.let"))
        assertTrue("LaneChip no longer reads the PC's lane", home.contains("val lane = status?.lane?.lowercase()"))
        assertTrue("LaneChip no longer reads the PC's model", home.contains("val model = status?.model"))
    }

    @Test
    fun `the phone still offers only the per-question cloud yes`() {
        val offer = source("net/CloudOffer.kt")
        assertTrue("the per-question offer's words are gone", offer.contains("A cloud model could give this one a second look."))
        assertTrue("the per-question button is gone", offer.contains("Try the cloud model"))
        // The offer is read from the header's own gate - never invented locally.
        assertTrue(offer.contains("if (obj.str(\"gate\") != \"offer\") return null"))
    }
}
