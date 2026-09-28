package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.ModelChat
import com.jarvis.client.net.ModelsInfo
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Brain › Model offers "Use" only on a model that can chat (play tester,
 * 2026-09-27: it was offered on nomic-embed-text, which only serves memory
 * search). `net/ModelChat.kt` is held to `contract/model-chat-cases.json`,
 * which tools/gen_model_chat_cases.py writes for both apps - the desktop's
 * tests/model-chat.mjs reads a byte-identical copy - so the two cannot drift
 * apart on which rows get "Use" or on the words said instead.
 */
class ModelChatContractTest {

    private val table: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/model-chat-cases.json")) {
            "contract/model-chat-cases.json is missing - run python3 tools/gen_model_chat_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    private val cases: List<JsonObject> = table["cases"]!!.jsonArray.map { it.jsonObject }

    @Test
    fun `the words are the desktop's words`() {
        assertEquals(table["cannot_chat"]!!.jsonPrimitive.content, ModelChat.CANNOT_CHAT)
    }

    @Test
    fun `the table has both answers`() {
        assertTrue(cases.any { it["chats"]!!.jsonPrimitive.content == "true" })
        assertTrue(cases.any { it["chats"]!!.jsonPrimitive.content == "false" })
    }

    @Test
    fun `every case gets the same answer here as on the desktop`() {
        for (c in cases) {
            val ref = c["ref"]!!.jsonPrimitive.content
            val family = c["family"]?.jsonPrimitive?.content
            val caps = (c["capabilities"] as? JsonArray)?.map { it.jsonPrimitive.content }
            val want = c["chats"]!!.jsonPrimitive.content == "true"
            assertEquals("$c", want, ModelChat.canChat(ref, family, caps))
        }
    }

    /**
     * The same cases through the real parser, as `/api/models` would send
     * them: a row with neither family nor capabilities goes as a bare name
     * (the real route's shape), the rest as objects.
     */
    @Test
    fun `every case gets the same answer through ModelsInfo`() {
        for (c in cases) {
            val bare = c.keys == setOf("ref", "chats")
            val row = if (bare) c["ref"].toString() else JsonObject(c - "chats").toString()
            val m = ModelsInfo.from(JarvisJson.parseToJsonElement("""{"installed": [$row]}""") as JsonObject)
            val want = c["chats"]!!.jsonPrimitive.content == "true"
            assertEquals("$c", want, m.entries.single().canChat)
        }
    }

    @Test
    fun `nomic-embed-text, the one the play tester found, cannot chat`() {
        val m = ModelsInfo.from(
            JarvisJson.parseToJsonElement(
                """{"current": "qwen3:8b", "installed": ["qwen3:8b", "nomic-embed-text"]}""",
            ) as JsonObject,
        )
        assertTrue(m.entries[0].canChat)
        assertFalse(m.entries[1].canChat)
        assertNull("a bare name carries no capabilities list", m.entries[1].capabilities)
    }
}
