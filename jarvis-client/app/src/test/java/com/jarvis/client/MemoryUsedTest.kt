package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ChatHistory
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.MemoryUsed
import com.jarvis.client.net.TemporaryChat
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * A temporary chat, and "Used in this answer" / "Jarvis remembered N things"
 * on the phone (the owner's decisions of 2026-09-25; [TemporaryChat],
 * [MemoryUsed]). The headers and bodies are the ones the patch stack and
 * `backend/rebuilt/jarvis_memory.py` `used_view` send
 * (backend/test_temporary_chat.py runs them).
 */
class MemoryUsedTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    @Test
    fun theWordsAreBothAppsWordForWord() {
        assertEquals(
            "Temporary chat: Jarvis won't use or learn from your memory, and this chat isn't kept.",
            TemporaryChat.LINE,
        )
        assertEquals("Remember: is off in a temporary chat.", TemporaryChat.REMEMBER_OFF)
        assertEquals("Used 1 memory", MemoryUsed.usedLine(1))
        assertEquals("Used 2 memories", MemoryUsed.usedLine(2))
        assertNull(MemoryUsed.usedLine(0))
        assertEquals("1 of them is no longer on this PC.", MemoryUsed.missingLine(1))
        assertEquals("3 of them are no longer on this PC.", MemoryUsed.missingLine(3))
        // The desktop's copy (jarvis-desktop/src/memory-used.js) says the same.
        val js = repoFile("jarvis-desktop/src/memory-used.js").readText()
        val flat = Regex("\"\\s*\\+\\s*\"").replace(js, "")
        for (words in listOf(TemporaryChat.LABEL, TemporaryChat.LINE, TemporaryChat.UNAVAILABLE,
            TemporaryChat.NOT_CONFIRMED, TemporaryChat.REMEMBER_OFF, TemporaryChat.STARTED,
            TemporaryChat.ENDED, MemoryUsed.USED_TITLE, MemoryUsed.REMEMBERED_TITLE, MemoryUsed.MISSING,
            MemoryUsed.PINNED_MARK, MemoryUsed.NOT_CURRENT_MARK, MemoryUsed.SHOW_ALL)) {
            assertTrue("the desktop does not say: $words", flat.contains("\"$words\""))
        }
        // The capability is the one the PC's handshake reports.
        val events = repoFile("backend/rebuilt/jarvis_events.py").readText()
        assertTrue(events.contains("\"${TemporaryChat.CAPABILITY}\": _hud_has(\"_temporary_chat\")"))
    }

    @Test
    fun onlyTheFactIdsOfTheRouteHeaderAreRead() {
        val header = """{"lane":"qwen3:8b","where":"local","injected_facts":5,
            "injected_ids":["mem:12","fact:3","mem:7","mem:12","mem:0","mem:-2","mem:1e3","mem:٣",5],
            "injected_sensitive":1,"turn_id":"${"a".repeat(32)}"}"""
        assertEquals(listOf(12L, 7L), MemoryUsed.idsFromRouteHeader(header))
        assertEquals(emptyList<Long>(), MemoryUsed.idsFromRouteHeader(null))
        assertEquals(emptyList<Long>(), MemoryUsed.idsFromRouteHeader("not json"))
        assertEquals(emptyList<Long>(), MemoryUsed.idsFromRouteHeader("""{"injected_ids":"mem:1"}"""))
        val many = (1..150).joinToString(",") { "\"mem:$it\"" }
        assertEquals(MemoryUsed.MAX, MemoryUsed.idsFromRouteHeader("""{"injected_ids":[$many]}""").size)
    }

    @Test
    fun theReadAsksForTheIdsAndNothingElse() {
        assertEquals("/api/memory/used?ids=12,7", MemoryUsed.path(listOf(12L, 7L, 12L)))
        assertNull(MemoryUsed.path(emptyList()))
        assertNull(MemoryUsed.path((1L..101L).toList()))
        assertEquals("/api/memory/used", MemoryUsed.PATH)
    }

    @Test
    fun theFactsAreReadAsThePcSaysAndAnErasedOneNeverShowsWords() {
        val v = MemoryUsed.parse(obj("""{"facts":[
            {"id":12,"text":"Owner is vegetarian","current":true,"pinned":true,"erased_at":null},
            {"id":7,"text":"Owner lives in Harrogate","current":false,"pinned":false,"valid_to":1780000000.0},
            {"id":9,"text":"[erased]","current":false,"erased_at":1790000000.0},
            {"id":"4","text":"an id in quotes"}],
            "missing":[424242]}"""))!!
        assertEquals(listOf(12L, 7L, 9L), v.facts.map { it.id })
        assertEquals(listOf(424242L), v.missing)
        val (veg, old, erased) = v.facts
        assertTrue(veg.pinned && veg.current && veg.canForget)
        assertFalse("a fact no longer in use has nothing to forget", old.canForget)
        assertEquals(1780000000.0, old.validTo!!, 0.0)
        assertEquals("", erased.text)
        assertFalse(erased.canForget || erased.current || erased.pinned)
        assertNull(MemoryUsed.parse(obj("""{"ok":true}""")))
        assertTrue(MemoryUsed.missing(ApiError.NotFound))
        assertTrue(MemoryUsed.missing(ApiError.Server(501, "")))
        assertFalse(MemoryUsed.missing(ApiError.BadToken))
    }

    @Test
    fun aTemporaryAnswerSaysWhatThePcDidAndNeverPretends() {
        assertEquals(emptyList<String>(), TemporaryChat.notes(false, """{"temporary":true}"""))
        assertEquals(emptyList<String>(), TemporaryChat.notes(true, """{"temporary":true,"injected_facts":0}"""))
        assertEquals(
            listOf(TemporaryChat.REMEMBER_OFF),
            TemporaryChat.notes(true, """{"temporary":true,"remember_off":true}"""),
        )
        for (unconfirmed in listOf(null, "", "{}", """{"temporary":"true"}""", """{"temporary":false}""")) {
            assertEquals(listOf(TemporaryChat.NOT_CONFIRMED), TemporaryChat.notes(true, unconfirmed))
        }
    }

    @Test
    fun theRequestCarriesTemporaryOnlyWhenOn() {
        val asking = ChatHistory.asking("hello")
        val on = JarvisJson.parseToJsonElement(
            ChatHistory.requestBody(emptyList(), asking, conversationId = "conv-00000001", temporary = true),
        ).jsonObject
        assertEquals(JsonPrimitive(true), on[TemporaryChat.FIELD])
        val off = JarvisJson.parseToJsonElement(
            ChatHistory.requestBody(emptyList(), asking, conversationId = "conv-00000001"),
        ).jsonObject
        assertFalse("an ordinary request is exactly what it was", off.containsKey(TemporaryChat.FIELD))
    }

    @Test
    fun thePhonesWiringHoldsTheRules() {
        val session = repoFile("$main/net/ChatSession.kt").readText()
        // Asked again before every temporary question, not only when turned on.
        val send = session.substring(session.indexOf("suspend fun send("))
        assertTrue(send.contains("if (asTemporary && !canTemporary()) {\n            _error.value = TemporaryChat.UNAVAILABLE\n            return null"))
        assertTrue(send.indexOf("canTemporary()") < send.indexOf("api.chatCall("))
        // Turning it on or off starts a new conversation.
        val toggle = session.substring(session.indexOf("fun setTemporary("))
        assertTrue(toggle.substring(0, toggle.indexOf("\n    }\n")).contains("newConversation()"))
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        assertTrue(rt.contains("canTemporary = { can(com.jarvis.client.net.TemporaryChat.CAPABILITY) }"))
        // Forget from these lists is the one held on a stale link.
        val forget = rt.substring(rt.indexOf("suspend fun forgetAutoFact("))
        assertTrue(forget.substring(0, 200).contains("actionBlocker()?.let { return false to it }"))
        val plate = repoFile("$main/ui/screens/UsedMemoriesPlate.kt").readText()
        assertTrue("hidden like the other memory lists", plate.contains("if (privateHidden) {"))
        assertTrue("Forget waits for a live link", plate.contains("enabled = canAct && busyId == null"))
        assertTrue("asked first, in Mind's words", plate.contains("Text(AutoLearn.FORGET_CONFIRM"))
        assertFalse("Erase is not offered here on the phone", plate.contains("eraseAutoFact"))
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client"
}
