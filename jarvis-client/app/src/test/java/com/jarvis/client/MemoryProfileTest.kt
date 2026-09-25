package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryProfile
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Always keep in mind" on the phone (the owner's decision, 2026-09-24;
 * [MemoryProfile]). The bodies are the ones `backend/rebuilt/jarvis_memory.py`
 * `handle_profile` / `profile_view` send (backend/test_memory_profile.py runs
 * them).
 */
class MemoryProfileTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    @Test
    fun theWordsAreBothAppsWordForWord() {
        assertEquals("Always keep in mind", MemoryProfile.TITLE)
        assertEquals("Jarvis reads these with every question, word for word. Keep it short.", MemoryProfile.UNDER)
        assertEquals("Pin", MemoryProfile.PIN)
        assertEquals("Unpin", MemoryProfile.UNPIN)
        assertEquals("19 of 1,200 characters used", MemoryProfile.usedLine(19, 1200))
        assertEquals("1,200 of 1,200 characters used", MemoryProfile.usedLine(1200, 1200))
        assertEquals("1,234,567", MemoryProfile.grouped(1234567))
        assertEquals("0", MemoryProfile.grouped(-3))
        // The desktop's copy (jarvis-desktop/src/memory-profile.js) says the same.
        val js = repoFile("jarvis-desktop/src/memory-profile.js").readText()
        val flat = Regex("\"\\s*\\+\\s*\"").replace(js, "")
        for (words in listOf(MemoryProfile.TITLE, MemoryProfile.UNDER, MemoryProfile.PINNED,
            MemoryProfile.UNPINNED, MemoryProfile.EMPTY)) {
            assertTrue("the desktop does not say: $words", flat.contains("\"$words\""))
        }
        assertTrue(flat.contains("export const PIN_LABEL = \"Pin\";"))
        assertTrue(flat.contains("export const UNPIN_LABEL = \"Unpin\";"))
        assertTrue(flat.contains("\"Your PC's Jarvis does not have the \\\"Always keep in mind\\\" list yet.\""))
        assertTrue(flat.contains("characters used`"))
    }

    @Test
    fun oneFactAndOneAnswerPerRequest() {
        assertEquals("/api/memory/profile", MemoryProfile.PATH)
        assertEquals("{\"id\":42,\"pinned\":true}", MemoryProfile.body(42, true))
        assertEquals("{\"id\":42,\"pinned\":false}", MemoryProfile.body(42, false))
    }

    @Test
    fun theListIsReadWordForWord() {
        val p = MemoryProfile.parse(obj("""{"facts":[
            {"id":3,"text":"Owner drinks tea, not coffee","added":1790000000.5},
            {"id":"4","text":"an id in quotes"},
            {"id":5},
            {"id":6,"text":"Owner is vegetarian","added":null}],
            "chars":47,"limit":1200}"""))!!
        assertEquals(
            listOf(MemoryProfile.Fact(3, "Owner drinks tea, not coffee", 1790000000.5),
                MemoryProfile.Fact(6, "Owner is vegetarian", null)),
            p.facts,
        )
        assertEquals(47, p.chars)
        assertEquals(1200, p.limit)
        assertEquals(setOf(3L, 6L), p.ids)
        // Not the list at all: null, never an empty list that reads as "nothing pinned".
        assertNull(MemoryProfile.parse(obj("""{"ok":true}""")))
        // No numbers: counted here, and the PC's usual limit.
        val bare = MemoryProfile.parse(obj("""{"facts":[{"id":1,"text":"abc"}]}"""))!!
        assertEquals(3, bare.chars)
        assertEquals(MemoryProfile.DEFAULT_LIMIT, bare.limit)
        assertTrue(MemoryProfile.missing(ApiError.NotFound))
        assertTrue(MemoryProfile.missing(ApiError.Server(501, "")))
        assertFalse(MemoryProfile.missing(ApiError.NotAvailable))
        assertFalse(MemoryProfile.missing(ApiError.Server(500, "")))
    }

    @Test
    fun whatThePcAnsweredReadsRight() {
        val pinned = MemoryProfile.Reply(200, obj("""{"ok":true,"id":5,"pinned":true,"changed":true,
            "chars":19,"limit":1200,"note":"Jarvis will read this with every question, word for word."}"""))
        assertEquals(true to MemoryProfile.PINNED, MemoryProfile.said(pinned, pinned = true))
        val unpinned = MemoryProfile.Reply(200, obj("""{"ok":true,"id":5,"pinned":false,"changed":true}"""))
        assertEquals(true to MemoryProfile.UNPINNED, MemoryProfile.said(unpinned, pinned = false))
        // The limit: the PC's own sentence, exactly as the desktop shows it.
        val tooLong = MemoryProfile.Reply(409, obj("""{"ok":false,"reason":"too_long",
            "error":"That would make the list too long - unpin something first","chars":1190,"limit":1200}"""))
        assertEquals(false to "That would make the list too long - unpin something first",
            MemoryProfile.said(tooLong, pinned = true))
        val gone = MemoryProfile.Reply(404, obj("""{"ok":false,"reason":"no_such_fact","error":"no fact with that id"}"""))
        assertEquals(true to MemoryProfile.ALREADY_GONE, MemoryProfile.said(gone, pinned = true))
        // A PC without the route: never "pinned".
        for (old in listOf(MemoryProfile.Reply(404, obj("""{"error":"not found"}""")),
            MemoryProfile.Reply(404, null), MemoryProfile.Reply(501, obj("""{"error":"too old"}""")))) {
            assertEquals(false to MemoryProfile.TOO_OLD, MemoryProfile.said(old, pinned = true))
        }
        assertEquals(false to MemoryProfile.NOT_RUNNING,
            MemoryProfile.said(MemoryProfile.Reply(503, null), pinned = true))
        assertEquals(false to "Not changed. Need an integer id.",
            MemoryProfile.said(MemoryProfile.Reply(400, obj("""{"ok":false,"error":"need an integer id"}""")), true))
        assertFalse(MemoryProfile.said(MemoryProfile.Reply(500, obj("""{"error":"OperationalError"}""")), true).first)
    }

    @Test
    fun theWiringPinsFromSavedAutomaticallyAndHoldsItOnAStaleLink() {
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val plate = repoFile("$main/ui/screens/AutoLearnPlate.kt").readText()
        // Pin / Unpin on each "Saved automatically" row, greyed on a stale
        // link like Forget beside it, and no confirm before it.
        val pin = plate.substring(plate.indexOf("pinned?.let { ids ->"))
        val pinBlock = pin.substring(0, pin.indexOf("\"Forgetting…\""))
        assertTrue(pinBlock.contains("enabled = canAct && busyId == null"))
        assertTrue(pinBlock.contains("JarvisRuntime.pinFact(fact.id, pinned = !on)"))
        assertFalse("pinning asked first", pinBlock.contains("confirmId = fact.id"))
        val section = repoFile("$main/ui/screens/ProfilePlate.kt").readText()
        assertTrue(section.contains("Section(MemoryProfile.TITLE"))
        assertTrue(section.contains("Text(MemoryProfile.UNDER"))
        assertTrue(section.contains("MemoryProfile.usedLine(shown.chars, shown.limit)"))
        assertTrue(section.contains("JarvisRuntime.pinFact(fact.id, pinned = false)"))
        assertTrue(section.contains("enabled = canAct && busyId == null"))
        assertTrue(section.contains("HiddenSection(MemoryProfile.TITLE"))
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        val fn = rt.substring(rt.indexOf("suspend fun pinFact("))
        val body = fn.substring(0, fn.indexOf("\n    }\n"))
        assertTrue(body, body.indexOf("actionBlocker()") in 0 until body.indexOf("api.pinFact("))
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        assertTrue(api.contains("suspend fun pinFact(id: Long, pinned: Boolean): ApiResult<MemoryProfile.Reply>"))
        assertTrue(api.contains("suspend fun memoryProfile(): ApiResult<JsonObject> = probe(MemoryProfile.PATH)"))
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        assertTrue(brain.indexOf("item(key = \"memory-auto\")") in 0 until brain.indexOf("item(key = \"memory-profile\")"))
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
