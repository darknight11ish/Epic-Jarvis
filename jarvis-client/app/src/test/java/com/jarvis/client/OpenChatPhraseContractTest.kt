package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.OpenChatPhrase
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

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

    /**
     * The other direction of the contract: every literal in `PHRASES` (read
     * as text - it is private, and does not need to stop being so just to
     * be read here) is itself one of the fixture's own "matches". Without
     * this, a phrase added straight to `PHRASES` that is in NEITHER list
     * would still pass both tests above - matching here and refused by
     * neither check - while quietly disagreeing with the backend's grammar,
     * exactly the drift this contract exists to catch (Opus 5.5 re-check,
     * 2026-09-27: the two tests above only ever checked the fixture against
     * the app, never the app against the fixture).
     */
    @Test
    fun `every literal in PHRASES is one the backend's grammar accepts`() {
        val matches = cases["matches"]!!.jsonArray.map { it.jsonPrimitive.content }.toSet()
        val src = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/net/OpenChatPhrase.kt").readText()
        val body = src.substringAfter("private val PHRASES = setOf(").substringBefore("\n    )")
        val phrases = Regex("\"([^\"]*)\"").findAll(body).map { it.groupValues[1] }.toList()
        assertTrue("PHRASES is empty - this test's own extraction did not find it", phrases.isNotEmpty())
        for (p in phrases) {
            assertTrue("PHRASES has \"$p\", which open-chat-cases.json's own \"matches\" does not", p in matches)
        }
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
}
