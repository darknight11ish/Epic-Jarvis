package com.jarvis.client

import com.jarvis.client.net.FocusPresets
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The measured speed, drawn ON each preset row (the owner's ask, 2026-11-17).
 *
 * The contract shape is the preset's one `measured` object:
 *
 *     "measured": { "tok_s": 38.1, "tok_s_on": "2026-11-17",
 *                   "tok_s_note": "9.18 GiB, 0 spill, one card (RTX 2060), ..." }
 *
 * `tok_s` already exists (General is 44.9 today) and is what this row has always
 * parsed; `tok_s_on` and `tok_s_note` arrive with the backend change that adds
 * the date and the note. THIS file proves the phone works with BOTH shapes, so
 * the two pull requests can land in either order:
 *
 *  - the SHIPPED shape (`tok_s` alone) still draws the number, with no date and
 *    no note - it must never read as "not measured";
 *  - the DATED shape draws the number and the day, and the screen-reader line
 *    says the unit and the day in words, not "38 point 1 tok slash s";
 *  - a missing/null `tok_s`, or no `tok_s` in `measured` at all, is NOT
 *    MEASURED: never 0, and never a pass.
 *
 * The generated fixture `backend/fixtures/work_presets.json` is read as it is
 * on the branch being tested, and the loop derives each row's expected words
 * from the row itself, so the desktop agent regenerating it (new dated fields,
 * a changed number) cannot make this file lie about either shape.
 */
class PresetSpeedTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** One-preset contract carrying exactly the `measured` block a case needs. */
    private fun contractWith(measured: JsonObject? = null): JsonObject = buildJsonObject {
        put("presets", buildJsonArray {
            add(buildJsonObject {
                put("id", "one")
                put("title", "One")
                put("lane", buildJsonObject { put("card", "one card") })
                put("apply", buildJsonObject { put("action", "Use this preset") })
                if (measured != null) put("measured", measured)
            })
        })
    }

    private fun preset(measured: JsonObject? = null): FocusPresets.Preset =
        requireNotNull(FocusPresets.parse(contractWith(measured))) { "the contract did not parse" }
            .presets.single()

    @Test
    fun `a preset with a measured speed draws it in the row and speaks it as words`() {
        val measured = preset(
            buildJsonObject {
                put("tok_s", 38.1)
                put("tok_s_on", "2026-11-17")
                put("tok_s_note", "9.18 GiB, 0 spill, one card (RTX 2060), 196,608 context")
            },
        )
        assertEquals(38.1, measured.measured!!.tokensPerSecond!!, 0.0001)
        assertEquals("2026-11-17", measured.measured!!.measuredOn)
        assertEquals(
            "the PC's own measurement note is kept",
            "9.18 GiB, 0 spill, one card (RTX 2060), 196,608 context",
            measured.measured!!.note,
        )
        // The row's own visible words: short, with the day the contract names.
        assertEquals("38.1 tok/s - measured 2026-11-17", FocusPresets.speedLine(measured))
        // The same line as a screen reader must hear it: the unit and the day
        // spelled out, and the PC's note after it - never "tok slash s".
        val spoken = FocusPresets.speedSpoken(measured)
        assertTrue(spoken, spoken.contains("38.1 tokens per second"))
        assertTrue(spoken, spoken.contains("17 November 2026"))
        assertTrue(
            spoken,
            spoken.contains("9.18 GiB, 0 spill, one card (RTX 2060), 196,608 context"),
        )
        assertFalse(
            "a screen reader would say \"tok slash s\": $spoken",
            spoken.contains(FocusPresets.TOK_S),
        )
    }

    @Test
    fun `the shipped shape - tok_s with no date - still draws the number, never not measured`() {
        // This is what the PC sends TODAY, before the dated fields land. The
        // brief's hard rule: the app must keep working against it, so the row
        // draws the number with no day and no note and says nothing false.
        val shipped = preset(
            buildJsonObject {
                put("tok_s", 44.9)
                put("size_gib", 6.1)
                put("vram_gib", 9.17)
                put("spill_gib", 0.0)
            },
        )
        assertEquals(44.9, shipped.measured!!.tokensPerSecond!!, 0.0001)
        assertNull("the shipped shape has no day", shipped.measured!!.measuredOn)
        assertNull("the shipped shape has no note", shipped.measured!!.note)
        assertEquals("44.9 tok/s", FocusPresets.speedLine(shipped))
        assertFalse(
            "the shipped shape must not read as unmeasured",
            FocusPresets.speedLine(shipped).contains("not measured"),
        )
        assertEquals(
            "Measured 44.9 tokens per second.",
            FocusPresets.speedSpoken(shipped),
        )
    }

    @Test
    fun `a null tok_s is not measured - never a zero and never a pass`() {
        // An explicit null and a missing field are the SAME answer: no
        // measurement. The row says so and never draws 0.
        val nulled = preset(buildJsonObject { put("tok_s", JsonNull) })
        assertNull("a null number is not a measurement", nulled.measured)
        assertEquals(FocusPresets.NOT_MEASURED, FocusPresets.speedLine(nulled))
        assertTrue(FocusPresets.speedLine(nulled), FocusPresets.speedLine(nulled).contains("not measured"))
        assertFalse(
            "a missing number became a zero: ${FocusPresets.speedLine(nulled)}",
            FocusPresets.speedLine(nulled).contains("0"),
        )
        assertEquals(FocusPresets.NOT_MEASURED_SPOKEN, FocusPresets.speedSpoken(nulled))

        // A `measured` block that exists but has no `tok_s` at all (the real
        // Agentic + Vision row carries latency, not generation speed) is not a
        // measured speed either.
        val noTok = preset(
            buildJsonObject {
                put("vision_latency_s", 4.45)
                put("size_gib", 6.1)
            },
        )
        assertNull(noTok.measured!!.tokensPerSecond)
        assertEquals(FocusPresets.NOT_MEASURED, FocusPresets.speedLine(noTok))

        // A contract that literally says 0 is not a pass either.
        val zero = preset(buildJsonObject { put("tok_s", 0.0) })
        assertNull(zero.measured)
        assertEquals(FocusPresets.NOT_MEASURED, FocusPresets.speedLine(zero))

        // No `measured` block at all is the same answer again.
        assertEquals(FocusPresets.NOT_MEASURED, FocusPresets.speedLine(preset()))
    }

    @Test
    fun `a day is spoken as a day and anything unparseable is said as it came`() {
        assertEquals("17 November 2026", FocusPresets.spellDay("2026-11-17"))
        assertEquals("someday", FocusPresets.spellDay("someday"))
        assertNull(FocusPresets.spellDay(" "))
        assertNull(FocusPresets.spellDay(null))
    }

    @Test
    fun `every row of the real generated fixture draws a figure or says not measured`() {
        val fixture = JarvisJson.parseToJsonElement(
            repoFile("backend/fixtures/work_presets.json").readText(),
        ) as JsonObject
        val view = requireNotNull(FocusPresets.parse(fixture)) { "the generated fixture did not parse" }
        val measuredRows = view.presets.filter { it.measured?.tokensPerSecond != null }
        assertTrue("the fixture carries no measured speed at all", measuredRows.isNotEmpty())
        for (row in view.presets) {
            val line = FocusPresets.speedLine(row)
            val tokens = row.measured?.tokensPerSecond
            if (tokens != null) {
                // The visible figure is the contract's own number, formatted.
                val want = String.format(java.util.Locale.UK, "%.1f tok/s", tokens)
                assertTrue("${row.id}: '$line' does not carry '$want'", line.startsWith(want))
                assertFalse("${row.id}: a measured row says not measured", line.contains("not measured"))
            } else {
                assertEquals(
                    "${row.id}: an unmeasured row must not invent a figure",
                    FocusPresets.NOT_MEASURED,
                    line,
                )
            }
            // Whatever shape the fixture carries today (dated or shipped), the
            // screen reader gets words and never the abbreviation.
            assertFalse(
                "${row.id}: a screen reader would say \"tok slash s\": ${FocusPresets.speedSpoken(row)}",
                FocusPresets.speedSpoken(row).contains(FocusPresets.TOK_S),
            )
        }
    }

    @Test
    fun `the preset row draws the speed closed and gives the screen reader words`() {
        // There is no screen reader on the JVM, so the words themselves are
        // tested for real above; this pin holds the drawing rule: the figure is
        // drawn on the CLOSED row (before the "Why this one" fold - no tap, no
        // expand control) and it carries the spoken description.
        val plate = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FocusPresetsPlate.kt",
        ).readText()
        val speed = plate.indexOf("FocusPresets.speedLine(p)")
        assertTrue("the preset row no longer draws the measured speed", speed > 0)
        val foldTap = plate.indexOf("if (show) \"Hide why\" else \"Why this one\"")
        val folded = plate.indexOf("if (show) {")
        assertTrue("the preset row has no fold any more", foldTap > 0 && folded > foldTap)
        assertTrue(
            "the speed line moved behind the row's fold (a tap is now needed)",
            speed < foldTap && speed < folded,
        )
        assertTrue(
            "the speed line has no screen-reader words",
            plate.contains("contentDescription = FocusPresets.speedSpoken(p)"),
        )
        assertFalse(
            "the visible \"tok/s\" is used as the screen-reader words",
            plate.contains("contentDescription = FocusPresets.speedLine"),
        )
    }
}
