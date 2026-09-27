package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.OpenChatPhrase
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `net/OpenChatPhrase.kt`'s own phrase list, held to
 * `src/test/resources/contract/open-chat-cases.json`, which
 * tools/gen_open_chat_cases.py makes from the backend's real
 * `jarvis_quick._OPEN_CHAT` grammar - so this app's local "open a chat"
 * check can never recognize a phrase the backend's own `/api/chat` intent
 * matching does not, or the other way round (cross-cutting audit
 * 2026-09-27, finding #7 - the two had already drifted apart before this).
 */
class OpenChatPhraseContractTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/open-chat-cases.json")) {
            "contract/open-chat-cases.json is missing - run python3 tools/gen_open_chat_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }

    @Test
    fun `every phrase the backend's grammar accepts is recognized here`() {
        for (c in cases["matches"]!!.jsonArray) {
            val phrase = c.jsonPrimitive.content
            assertTrue(phrase, OpenChatPhrase.matches(phrase))
        }
    }

    @Test
    fun `every phrase the backend's grammar refuses is refused here too`() {
        for (c in cases["non_matches"]!!.jsonArray) {
            val phrase = c.jsonPrimitive.content
            assertFalse(phrase, OpenChatPhrase.matches(phrase))
        }
    }
}
