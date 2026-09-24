package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryAsOf
import com.jarvis.client.net.MemoryErase
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.ZoneId

/**
 * "Erase the words" on the phone (the owner's decision, 2026-09-24;
 * [MemoryErase]). The bodies are the ones `backend/rebuilt/jarvis_memory.py`
 * `handle_erase` sends (backend/test_memory_erase.py runs it).
 */
class MemoryEraseTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    @Test
    fun theWordsAreBothAppsWordForWord() {
        assertEquals("Erase the words", MemoryErase.LABEL)
        assertEquals(
            "Erase the words of this fact from your PC for good? Jarvis keeps only the date it was saved, " +
                "so its history shows something was erased here. This cannot be undone.",
            MemoryErase.CONFIRM,
        )
        assertEquals("Erased.", MemoryErase.ERASED)
        // The desktop's copy (jarvis-desktop/src/auto-learn.js) says the same.
        val js = repoFile("jarvis-desktop/src/auto-learn.js").readText()
        val flat = Regex("\"\\s*\\+\\s*\"").replace(js, "")
        assertTrue(flat.contains(MemoryErase.CONFIRM))
        assertTrue(js.contains("export const ERASED = \"Erased.\";"))
        assertTrue(js.contains("export const ERASE_LABEL = \"Erase the words\";"))
    }

    @Test
    fun oneIdPerRequestAndNothingElse() {
        assertEquals("/api/memory/erase", MemoryErase.PATH)
        assertEquals("{\"id\":42}", MemoryErase.body(42))
    }

    @Test
    fun whatThePcAnsweredReadsRight() {
        val ok = MemoryErase.Reply(200, obj("""{"ok":true,"id":5,"erased_at":1790000000.5,
            "already_erased":false,"retired_now":true,"file_clean":true,"copies":1,"note":"Erased."}"""))
        assertEquals(true to "Erased.", MemoryErase.said(ok))
        // No such fact: nothing left, so it counts as gone.
        val gone = MemoryErase.Reply(404, obj("""{"ok":false,"reason":"no_such_fact","error":"no fact with that id"}"""))
        assertEquals(true to MemoryErase.ALREADY_GONE, MemoryErase.said(gone))
        // A PC without the route: a 404 with no reason, or 501. NOT gone -
        // the words are still on the PC, so the row must stay.
        for (old in listOf(MemoryErase.Reply(404, obj("""{"error":"not found"}""")),
            MemoryErase.Reply(404, null),
            MemoryErase.Reply(501, obj("""{"error":"this PC's jarvis_memory.py cannot erase words yet"}""")))) {
            val (erased, said) = MemoryErase.said(old)
            assertFalse("$old read as erased", erased)
            assertEquals(MemoryErase.TOO_OLD, said)
        }
        assertEquals(false to MemoryErase.NOT_RUNNING, MemoryErase.said(MemoryErase.Reply(503, null)))
        assertEquals(
            false to "Not erased. Need an integer id.",
            MemoryErase.said(MemoryErase.Reply(400, obj("""{"ok":false,"error":"need an integer id"}"""))),
        )
        assertEquals(
            false to "Not erased. Something broke.",
            MemoryErase.said(MemoryErase.Reply(200, obj("""{"ok":false,"error":"something broke"}"""))),
        )
        assertFalse(MemoryErase.said(MemoryErase.Reply(500, obj("""{"error":"OperationalError"}"""))).first)
    }

    @Test
    fun anErasedFactIsADateNeverItsWords() {
        val row = obj("""{"id":5,"text":"[erased]","erased_at":1790000000.0,"current":false}""")
        assertEquals(1790000000.0, MemoryErase.erasedAt(row)!!, 0.0)
        for (v in listOf("null", "\"1790000000\"", "true", "0", "-5")) {
            assertNull(v, MemoryErase.erasedAt(obj("""{"erased_at":$v}""")))
        }
        assertNull(MemoryErase.erasedAt(obj("""{"text":"x"}""")))
        assertEquals("Erased on 21 September 2026",
            MemoryErase.erasedLine(1790000000.0, ZoneId.of("UTC")))
        // "What did Jarvis know on this date?": the erased row is kept, as a
        // date, and the marker is never its text.
        val answer = MemoryAsOf.parse(obj("""{"available":true,"facts":[
            {"id":3,"text":"The owner lives on Elm Street","current":true,"erased_at":null},
            {"id":5,"text":"[erased]","current":true,"erased_at":1790000000.0}]}"""))!!
        assertEquals(MemoryAsOf.Fact("The owner lives on Elm Street", trueThen = true), answer.facts[0])
        assertEquals(MemoryAsOf.Fact("", trueThen = true, erasedAt = 1790000000.0), answer.facts[1])
    }

    @Test
    fun theWiringOffersItBesideForgetAndHoldsItOnAStaleLink() {
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val plate = repoFile("$main/ui/screens/AutoLearnPlate.kt").readText()
        assertTrue(plate.contains("Text(MemoryErase.CONFIRM"))
        assertTrue(plate.contains("JarvisRuntime.eraseAutoFact(fact.id)"))
        assertTrue(plate.contains("if (busyId == fact.id && erasing) MemoryErase.BUSY else MemoryErase.LABEL"))
        // Greyed on a stale link, the same guard as Forget's.
        val erase = plate.substring(plate.indexOf("MemoryErase.BUSY else MemoryErase.LABEL"))
        assertTrue(erase.substring(0, 200).contains("enabled = canAct && busyId == null"))
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        val fn = rt.substring(rt.indexOf("suspend fun eraseAutoFact("))
        val body = fn.substring(0, fn.indexOf("\n    }\n"))
        assertTrue(body, body.indexOf("actionBlocker()") in 0 until body.indexOf("api.eraseFact("))
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        assertTrue(api.contains("suspend fun eraseFact(id: Long): ApiResult<MemoryErase.Reply>"))
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        assertTrue(brain.contains("com.jarvis.client.net.MemoryErase.erasedLine("))
    }

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
