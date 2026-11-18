package com.jarvis.client

import com.jarvis.client.net.FocusPresets
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The compact unit is for EYES; speech is words (2026-11-18).
 *
 * The screen-reader line appends the PC's own `tok_s_note` after the measured
 * figure, and the note is allowed to carry the compact "tok/s" - it is also the
 * tooltip a human reads. So the note's abbreviation used to reach a screen
 * reader as "tok slash s" (the real fixture's Coding note says "two runs read
 * 40.3-51.2 tok/s, the low end is shown"): a REQUIRED phone check caught it,
 * not the desktop suites. This file pins the fix from the other side - whatever
 * the note contains, [FocusPresets.speedSpoken] returns words, while
 * [FocusPresets.speedLine] keeps the compact form for the human row.
 */
class PresetSpeedAbbreviationTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** One preset whose `measured` block carries exactly [note] as its note. */
    private fun presetWithNote(note: String): FocusPresets.Preset {
        val contract = buildJsonObject {
            put("presets", buildJsonArray {
                add(buildJsonObject {
                    put("id", "one")
                    put("title", "One")
                    put("lane", buildJsonObject { put("card", "one card") })
                    put("apply", buildJsonObject { put("action", "Use this preset") })
                    put("measured", buildJsonObject {
                        put("tok_s", 40.3)
                        put("tok_s_on", "2026-11-17")
                        put("tok_s_note", note)
                    })
                })
            })
        }
        return requireNotNull(FocusPresets.parse(contract)) { "the contract did not parse" }
            .presets.single()
    }

    @Test
    fun `a note carrying the abbreviation is still spoken as words`() {
        // The exact shape the backend now ships for Coding: the range is written
        // with the compact unit a tooltip wants.
        val note = "16.17 GiB, 0 spill, all three cards, 49,152 context; " +
            "two runs read 40.3-51.2 tok/s, the low end is shown"
        val row = presetWithNote(note)
        val spoken = FocusPresets.speedSpoken(row)
        assertFalse(
            "a screen reader would say \"tok slash s\": $spoken",
            spoken.contains(FocusPresets.TOK_S),
        )
        assertTrue(spoken, spoken.contains("40.3 tokens per second"))
        assertTrue(
            "the note's own range is not said in words: $spoken",
            spoken.contains("40.3-51.2 tokens per second"),
        )
        // ... and the row a human reads keeps the compact unit. The note is the
        // tooltip, where "tok/s" is the right form.
        assertTrue(
            "the visible row lost the compact unit: ${FocusPresets.speedLine(row)}",
            FocusPresets.speedLine(row).contains(FocusPresets.TOK_S),
        )
    }

    @Test
    fun `every row of the real generated fixture speaks without the abbreviation`() {
        val fixture = JarvisJson.parseToJsonElement(
            repoFile("backend/fixtures/work_presets.json").readText(),
        ) as JsonObject
        val view = requireNotNull(FocusPresets.parse(fixture)) { "the generated fixture did not parse" }
        for (row in view.presets) {
            val spoken = FocusPresets.speedSpoken(row)
            assertFalse(
                "${row.id}: a screen reader would say \"tok slash s\": $spoken",
                spoken.contains(FocusPresets.TOK_S),
            )
        }
        // The Coding row's note really does carry the abbreviation today, so the
        // loop above guards a live case, not a hypothetical one.
        val coding = view.presets.firstOrNull { it.id == "coding" }
        assertNotNull("the fixture no longer carries the Coding row", coding)
        assertTrue(
            "the Coding note no longer carries the abbreviation - update this guard",
            coding!!.measured?.note?.contains(FocusPresets.TOK_S) == true,
        )
    }
}
