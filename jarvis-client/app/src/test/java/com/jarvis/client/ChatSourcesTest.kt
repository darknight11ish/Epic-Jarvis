package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ChatSources
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Where this came from", and the quote check - feasibility I42/I132 on the
 * phone ([ChatSources]). The shapes are the ones `jarvis_sources.py` and
 * `answer-sources.patch` send (backend/test_sources.py runs them).
 */
class ChatSourcesTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    @Test
    fun theWordsAreBothAppsWordForWord() {
        assertEquals(
            "Your PC's Jarvis cannot show where this answer came from yet - run apply-patches.ps1 " +
                "on the PC to update it.",
            ChatSources.MISSING,
        )
        assertEquals("not found in what Jarvis read", ChatSources.QUOTE_WARNING_LABEL)
        assertEquals("Where this came from", ChatSources.TITLE)
        // The desktop's copy (jarvis-desktop/src/memory-used.js) says the same.
        val js = repoFile("jarvis-desktop/src/memory-used.js").readText()
        val flat = Regex("\"\\s*\\+\\s*\"").replace(js, "")
        for (words in listOf(ChatSources.MISSING, ChatSources.QUOTE_WARNING_LABEL, ChatSources.TITLE)) {
            assertTrue("the desktop does not say: $words", flat.contains("\"$words\""))
        }
    }

    @Test
    fun theReadAsksByTurnIdAndNothingElse() {
        val tid = "a".repeat(32)
        assertEquals("/api/chat/sources?turn_id=$tid", ChatSources.path(tid))
        assertNull(ChatSources.path(null))
        assertNull(ChatSources.path(""))
        assertNull(ChatSources.path("not-hex"))
        assertNull(ChatSources.path("a".repeat(31)))
        assertNull(ChatSources.path("A".repeat(32)))
        assertEquals("/api/chat/sources", ChatSources.PATH)
    }

    @Test
    fun theSourcesAreReadByKindAndUnknownOrEmptyOnesAreDropped() {
        val v = ChatSources.parse(obj("""{"sources":[
            {"kind":"note","ref":"Recipes/Soup.md","title":"Soup ideas"},
            {"kind":"wiki","ref":"Jarvis Wiki/Recipes.md"},
            {"kind":"web","url":"https://example.com/soup","title":"Example Soup Co"},
            {"kind":"file","path":"C:\\notes.txt"},
            {"kind":"spreadsheet","ref":"x"},
            {"kind":"note"}],
            "unverified_quotes":["always add nutmeg","  ", null]}"""))!!
        assertEquals(listOf("note", "wiki", "web", "file"), v.sources.map { it.kind })
        assertEquals(listOf("always add nutmeg"), v.quotes)
        assertNull(ChatSources.parse(obj("""{"ok":true}""")))
        assertTrue(ChatSources.missing(ApiError.NotFound))
        assertTrue(ChatSources.missing(ApiError.Server(501, "")))
        assertFalse(ChatSources.missing(ApiError.BadToken))
    }

    @Test
    fun theLineShowsOnlyWhatIsSafeAWebSourceShowsItsHostOnly() {
        val note = ChatSources.Source("note", ref = "Ideas.md", title = "Ideas")
        val noteNoTitle = ChatSources.Source("note", ref = "Ideas.md")
        val web = ChatSources.Source("web", url = "https://example.com/very/private/path")
        val file = ChatSources.Source("file", path = "C:\\notes.txt")
        assertEquals("Note: Ideas", ChatSources.line(note))
        assertEquals("Note: Ideas.md", ChatSources.line(noteNoTitle))
        assertEquals("Web: example.com", ChatSources.line(web))
        assertEquals("File: C:\\notes.txt", ChatSources.line(file))
        assertEquals("example.com", ChatSources.hostOf("https://example.com/very/private/path?x=1"))
        assertEquals("not a url", ChatSources.hostOf("not a url"))
        assertTrue(ChatSources.isOpenable(web))
        assertFalse("only a web source opens", ChatSources.isOpenable(note))
        assertFalse("not an http(s) link", ChatSources.isOpenable(ChatSources.Source("web", url = "javascript:x")))
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
