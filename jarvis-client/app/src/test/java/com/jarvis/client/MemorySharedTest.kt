package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryShared
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Between us" on the phone (the owner's decision, 2026-09-27;
 * [MemoryShared]). The bodies are the ones `backend/rebuilt/jarvis_memory.py`
 * `handle_shared` / `shared_view` send (backend/test_between_us.py runs them).
 */
class MemorySharedTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    @Test
    fun theWordsAreBothAppsWordForWord() {
        assertEquals("Between us", MemoryShared.TITLE)
        assertEquals(
            "Shared jokes and nicknames. Jarvis may bring one up when it fits - never in Plain manner.",
            MemoryShared.UNDER,
        )
        assertEquals("Between us", MemoryShared.SHARE)
        assertEquals("Not between us", MemoryShared.UNSHARE)
        // The desktop's copy (jarvis-desktop/src/memory-shared.js) says the same.
        val js = repoFile("jarvis-desktop/src/memory-shared.js").readText()
        val flat = Regex("\"\\s*\\+\\s*\"").replace(js, "")
        for (words in listOf(MemoryShared.TITLE, MemoryShared.UNDER, MemoryShared.SHARED,
            MemoryShared.UNSHARED, MemoryShared.EMPTY)) {
            assertTrue("the desktop does not say: $words", flat.contains("\"$words\""))
        }
        assertTrue(flat.contains("export const SHARE_LABEL = \"Between us\";"))
        assertTrue(flat.contains("export const UNSHARE_LABEL = \"Not between us\";"))
        assertTrue(flat.contains("\"Your PC's Jarvis does not have the \\\"Between us\\\" list yet.\""))
    }

    @Test
    fun oneFactAndOneAnswerPerRequest() {
        assertEquals("/api/memory/shared", MemoryShared.PATH)
        assertEquals("{\"id\":42,\"shared\":true}", MemoryShared.body(42, true))
        assertEquals("{\"id\":42,\"shared\":false}", MemoryShared.body(42, false))
    }

    @Test
    fun theListIsReadWordForWord() {
        val s = MemoryShared.parse(obj("""{"facts":[
            {"id":3,"text":"We call the printer 'the beast'","created":1790000000.5},
            {"id":"4","text":"an id in quotes"},
            {"id":5},
            {"id":6,"text":"We call the router 'the goblin'","created":null}]}"""))!!
        assertEquals(
            listOf(MemoryShared.Fact(3, "We call the printer 'the beast'", 1790000000.5),
                MemoryShared.Fact(6, "We call the router 'the goblin'", null)),
            s.facts,
        )
        assertEquals(setOf(3L, 6L), s.ids)
        // Not the list at all: null, never an empty list that reads as "nothing tagged".
        assertNull(MemoryShared.parse(obj("""{"ok":true}""")))
        assertTrue(MemoryShared.missing(ApiError.NotFound))
        assertTrue(MemoryShared.missing(ApiError.Server(501, "")))
        assertFalse(MemoryShared.missing(ApiError.NotAvailable))
        assertFalse(MemoryShared.missing(ApiError.Server(500, "")))
    }

    @Test
    fun whatThePcAnsweredReadsRight() {
        val tagged = MemoryShared.Reply(200, obj("""{"ok":true,"id":5,"shared":true,"changed":true}"""))
        assertEquals(true to MemoryShared.SHARED, MemoryShared.said(tagged, shared = true))
        val untagged = MemoryShared.Reply(200, obj("""{"ok":true,"id":5,"shared":false,"changed":true}"""))
        assertEquals(true to MemoryShared.UNSHARED, MemoryShared.said(untagged, shared = false))
        // Not current: the PC's own sentence, exactly as the desktop shows it.
        val notCurrent = MemoryShared.Reply(409, obj("""{"ok":false,"reason":"not_current",
            "error":"That fact is no longer in use, so it cannot be a shared joke"}"""))
        assertEquals(false to "That fact is no longer in use, so it cannot be a shared joke",
            MemoryShared.said(notCurrent, shared = true))
        val gone = MemoryShared.Reply(404, obj("""{"ok":false,"reason":"no_such_fact","error":"no fact with that id"}"""))
        assertEquals(true to MemoryShared.ALREADY_GONE, MemoryShared.said(gone, shared = true))
        // A PC without the route: never "tagged".
        for (old in listOf(MemoryShared.Reply(404, obj("""{"error":"not found"}""")),
            MemoryShared.Reply(404, null), MemoryShared.Reply(501, obj("""{"error":"too old"}""")))) {
            assertEquals(false to MemoryShared.TOO_OLD, MemoryShared.said(old, shared = true))
        }
        assertEquals(false to MemoryShared.NOT_RUNNING,
            MemoryShared.said(MemoryShared.Reply(503, null), shared = true))
        assertEquals(false to "Not changed. Need an integer id.",
            MemoryShared.said(MemoryShared.Reply(400, obj("""{"ok":false,"error":"need an integer id"}""")), true))
        assertFalse(MemoryShared.said(MemoryShared.Reply(500, obj("""{"error":"OperationalError"}""")), true).first)
    }

    @Test
    fun theWiringTagsFromSavedAutomaticallyAndHoldsItOnAStaleLink() {
        val main = "jarvis-client/app/src/main/java/com/jarvis/client"
        val plate = repoFile("$main/ui/screens/AutoLearnPlate.kt").readText()
        // "Between us" / "Not between us" on each "Saved automatically" row,
        // greyed on a stale link like Forget beside it, and no confirm
        // before it.
        val share = plate.substring(plate.indexOf("shared?.let { ids ->"))
        val shareBlock = share.substring(0, share.indexOf("\"Forgetting…\""))
        assertTrue(shareBlock.contains("enabled = canAct && busyId == null"))
        assertTrue(shareBlock.contains("JarvisRuntime.setShared(fact.id, shared = !on)"))
        assertFalse("tagging asked first", shareBlock.contains("confirmId = fact.id"))
        val section = repoFile("$main/ui/screens/SharedPlate.kt").readText()
        assertTrue(section.contains("Section(MemoryShared.TITLE"))
        assertTrue(section.contains("Text(MemoryShared.UNDER"))
        assertTrue(section.contains("JarvisRuntime.setShared(fact.id, shared = false)"))
        assertTrue(section.contains("JarvisRuntime.forgetAutoFact(fact.id)"))
        assertTrue(section.contains("enabled = canAct && busyId == null"))
        assertTrue(section.contains("HiddenSection(MemoryShared.TITLE"))
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        val fn = rt.substring(rt.indexOf("suspend fun setShared("))
        val body = fn.substring(0, fn.indexOf("\n    }\n"))
        assertTrue(body, body.indexOf("actionBlocker()") in 0 until body.indexOf("api.setShared("))
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        assertTrue(api.contains("suspend fun setShared(id: Long, shared: Boolean): ApiResult<MemoryShared.Reply>"))
        assertTrue(api.contains("suspend fun memoryShared(): ApiResult<JsonObject> = probe(MemoryShared.PATH)"))
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        assertTrue(brain.indexOf("item(key = \"memory-profile\")") in 0 until brain.indexOf("item(key = \"memory-shared\")"))
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
