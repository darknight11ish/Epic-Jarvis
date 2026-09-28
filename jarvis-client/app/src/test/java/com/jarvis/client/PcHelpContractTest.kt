package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PcHelp
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "PC help" on the Brain screen, read from what the PC REALLY answers.
 *
 * `contract/pc-help-cases.json` is the real `GET /api/pc/help` answer
 * (jarvis_pc_help.read() with made-up readings), written by
 * tools/gen_pc_help_cases.py - byte for byte the file the desktop builds
 * against (backend/test_pc_help.py checks it is up to date).
 */
class PcHelpContractTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/pc-help-cases.json")) {
            "contract/pc-help-cases.json is missing - run tools/gen_pc_help_cases.py"
        }.readText()
        (JarvisJson.parseToJsonElement(text) as JsonObject)["cases"]!!.jsonObject
    }

    @Test
    fun `every case is read, five answers in the PC's order, word for word`() {
        assertTrue(cases.size >= 4)
        for ((name, el) in cases) {
            val raw = el.jsonObject
            val read = PcHelp.readOf(ApiResult.Ok(raw))
            assertTrue(name, read is PcHelp.Read.Loaded)
            val answer = (read as PcHelp.Read.Loaded).answer
            assertEquals(name, listOf("slow", "disk", "gpu", "heat", "restart"), answer.sections.map { it.id })
            val words = raw["sections"]!!.jsonArray.map { it.jsonObject["words"]!!.jsonPrimitive.content }
            assertEquals(name, words, answer.sections.map { it.words })
            assertEquals(name, 2, answer.notes.size)
            assertNull(PcHelp.readLine(read))
        }
    }

    @Test
    fun `Jarvis's own model is named in the busy case`() {
        val answer = (PcHelp.readOf(ApiResult.Ok(cases["busy"]!!.jsonObject)) as PcHelp.Read.Loaded).answer
        assertTrue(answer.sections[0].words.contains("Jarvis's AI model (38%)"))
        assertTrue(answer.notes.last().startsWith("PC help only reads."))
    }

    @Test
    fun `an older backend is told to update, in words`() {
        assertEquals(PcHelp.Read.OlderBackend, PcHelp.readOf(ApiResult.Failed(ApiError.NotFound)))
        assertEquals(PcHelp.Read.OlderBackend, PcHelp.readOf(ApiResult.Failed(ApiError.NotAvailable)))
        assertEquals(PcHelp.UPDATE, PcHelp.readLine(PcHelp.Read.OlderBackend))
        val odd = PcHelp.readOf(ApiResult.Ok(JsonObject(emptyMap())))
        assertTrue(odd is PcHelp.Read.Failed)
    }

    @Test
    fun `the labels are the desktop's`() {
        assertEquals("PC help", PcHelp.HEADING)
        assertEquals("Check now", PcHelp.CHECK)
        assertEquals("Checking your PC…", PcHelp.CHECKING)
        assertEquals("/api/pc/help", PcHelp.PATH)
    }
}
