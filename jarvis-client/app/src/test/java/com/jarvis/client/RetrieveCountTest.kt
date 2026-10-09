package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.RetrieveCount
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "3 recalled · 2 near" under an answer on the phone - the count-only half of
 * the desktop's retrieval trace (the owner's decision of 2026-10-08, "Just the
 * number"; docs/RETRIEVE-PORT-BRIEF.md option B; [RetrieveCount]).
 *
 * The point of this suite is the one property the feature exists for: **the
 * words the desktop's trace prints never reach the phone, and no count this
 * app draws can hold one.** The bodies below are the ones the PC really sends
 * (`jarvis_hud.py`'s `retrieve()` for the full trace, `_retrieve_counts()` for
 * the count-only reply).
 */
class RetrieveCountTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    /** The desktop's own `/api/retrieve` reply: the matched words, 150 characters each. */
    private val fullTrace = """
        {"available":true,"hits":[
          {"id":"fact:12","kind":"fact","score":0.71,"text":"my sister likes jazz"},
          {"id":"logseq:Work.md","kind":"logseq","score":0.66,"text":"Isoforge: use q8_0 for the cache"},
          {"id":"doc:4","kind":"document","score":0.6,"text":"the landlord's number is 555-0100"}],
         "near":[{"id":"kg:9","kind":"knowledge","score":0.4,"text":"Eve Example, dentist"}]}
    """.trimIndent()

    /** Exactly what `_retrieve_counts()` returns, and all it can return. */
    private val countOnly = """{"available":true,"count_only":true,"recalled":3,"near":1}"""

    // ---------------------------------------------------------------- shape --

    @Test
    fun aCountIsTwoWholeNumbersAndHasNowhereToPutAWord() {
        // By construction, not by care: the fields are the whole object.
        // Adding `val text: String`, or any other field, fails right here.
        val fields = RetrieveCount.Count::class.java.declaredFields
            .filterNot { it.isSynthetic }
            .associate { it.name to it.type }
        assertEquals(
            "a Count holds two whole numbers and no text field",
            mapOf(
                "recalled" to Int::class.javaPrimitiveType,
                "near" to Int::class.javaPrimitiveType,
            ),
            fields,
        )
        assertEquals(3, RetrieveCount.Count(3, 1).recalled)
        assertEquals(1, RetrieveCount.Count(3, 1).near)
    }

    @Test
    fun theWordsMatchTheDesktopsOwnTraceBar() {
        // jarvis_hud.html draws `${hits.length} recalled · ${near.length} near`
        // - the same two words and the same middle dot, not a new surface.
        assertEquals("3 recalled · 1 near", RetrieveCount.line(RetrieveCount.Count(3, 1)))
        assertEquals("7 recalled · 6 near", RetrieveCount.line(RetrieveCount.Count(7, 6)))
        assertNull("nothing recalled and nothing near is no line", RetrieveCount.line(RetrieveCount.Count(0, 0)))
        val hud = repoFile("jarvis-desktop/src/jarvis_hud.html").readText()
        assertTrue(
            "the desktop says the same words",
            hud.contains("recalled · ") && hud.contains("near") &&
                hud.contains("${'$'}{trace.hits.length}") && hud.contains("${'$'}{trace.near.length}"),
        )
    }

    // -------------------------------------------------- no word gets through --

    @Test
    fun theDesktopsFullTraceIsRefusedWholeRatherThanCounted() {
        // The one reply that carries the words. Nothing is read from it: not a
        // count, not an id, not a title - the whole body is dropped.
        assertNull(RetrieveCount.parse(obj(fullTrace)))
        assertNull(RetrieveCount.parse(obj("""{"available":true,"hits":[],"near":[]}""")))
        // Nothing in the object can turn a word into a line, whatever the reply.
        for (body in listOf(fullTrace, """{"available":true,"hits":[],"near":[]}""",
                            """{"hits":[{"text":"my sister likes jazz"}]}""")) {
            val parsed = RetrieveCount.parse(obj(body))
            val drawn = parsed?.let { RetrieveCount.line(it) }.orEmpty()
            for (word in listOf("jazz", "Isoforge", "q8_0", "landlord", "555-0100", "Eve", "fact:12",
                                "logseq", "document", "knowledge", "sister")) {
                assertTrue("a word reached the line: $word", !drawn.contains(word))
            }
        }
    }

    @Test
    fun aWordSmuggledBesideTheCountIsStillNotDrawn() {
        // A PC that sent counts AND words: the counts are read, the words are
        // not, because there is no field, no key and no branch that reads one.
        val smuggled = """
            {"available":true,"count_only":true,"recalled":3,"near":1,
             "text":"my sister likes jazz","id":"fact:12","kind":"fact",
             "note":"the landlord's number is 555-0100"}
        """.trimIndent()
        val parsed = RetrieveCount.parse(obj(smuggled))
        assertEquals(RetrieveCount.Count(3, 1), parsed)
        assertEquals("3 recalled · 1 near", RetrieveCount.line(parsed!!))
    }

    @Test
    fun everyLineIsDigitsAndTheTwoFixedWords() {
        // Sweep: no input can produce anything but `N recalled · M near`.
        val line = Regex("^\\d+ recalled · \\d+ near$")
        for (recalled in 0..9) {
            for (near in 0..9) {
                val c = RetrieveCount.Count(recalled, near)
                val drawn = RetrieveCount.line(c)
                if (recalled == 0 && near == 0) {
                    assertNull(drawn)
                } else {
                    assertTrue("unexpected line: $drawn", line.matches(drawn!!))
                }
            }
        }
        assertTrue(line.matches(RetrieveCount.line(RetrieveCount.Count(1_000_000, 6))!!))
    }

    // -------------------------------------------------------------- reading --

    @Test
    fun onlyAnExplicitCountOnlyReplyIsRead() {
        assertEquals(RetrieveCount.Count(3, 1), RetrieveCount.parse(obj(countOnly)))
        assertEquals(RetrieveCount.Count(0, 0), RetrieveCount.parse(
            obj("""{"available":true,"count_only":true,"recalled":0,"near":0}""")))
        // The flag itself must be a real JSON true, not the string "true".
        assertNull(RetrieveCount.parse(obj("""{"count_only":"true","recalled":3,"near":1}""")))
        assertNull(RetrieveCount.parse(obj("""{"count_only":1,"recalled":3,"near":1}""")))
        assertNull(RetrieveCount.parse(obj("""{"recalled":3,"near":1}""")))
        // A number must be a whole, non-negative number, not a word or a fraction.
        for (bad in listOf("""{"count_only":true,"recalled":"3","near":1}""",
                           """{"count_only":true,"recalled":3,"near":"1"}""",
                           """{"count_only":true,"recalled":3.5,"near":1}""",
                           """{"count_only":true,"recalled":-1,"near":1}""",
                           """{"count_only":true,"recalled":3}""",
                           """{"count_only":true,"near":1}""",
                           """{"count_only":true,"recalled":null,"near":1}""",
                           """{"count_only":true,"recalled":[3],"near":1}""",
                           """{"count_only":true,"recalled":{"n":3},"near":1}""",
                           """{"count_only":false,"recalled":3,"near":1}""")) {
            assertNull("was read: $bad", RetrieveCount.parse(obj(bad)))
        }
    }

    @Test
    fun aPcWithoutTheRouteIsMissingRatherThanFailed() {
        assertTrue(RetrieveCount.missing(ApiError.NotFound))
        assertTrue(RetrieveCount.missing(ApiError.Server(501, "")))
        assertTrue(!RetrieveCount.missing(ApiError.Server(500, "")))
        assertTrue(!RetrieveCount.missing(ApiError.BadToken))
    }

    // ------------------------------------------------------------ the ask ----

    @Test
    fun theQuestionIsEncodedAndTheCountFlagRidesAlong() {
        assertEquals("/api/retrieve?q=what+did+I+decide&count=1",
            RetrieveCount.path("what did I decide"))
        // A `&` or a `#` in the owner's own question cannot smuggle a parameter.
        val sneaky = RetrieveCount.path("a&count=0&x=#frag")!!
        assertTrue(sneaky.startsWith("/api/retrieve?q="))
        assertTrue("exactly one query parameter pair plus the flag",
            sneaky.count { it == '&' } == 1 && sneaky.endsWith("&count=1"))
        assertEquals(RetrieveCount.COUNT_FLAG, "count=1")
        assertNull(RetrieveCount.path(null))
        assertNull(RetrieveCount.path("   "))
    }

    @Test
    fun thePcIsAskedOnlyWhenItSaysItCanCount() {
        // An older PC answers the same question with the words themselves, so
        // nothing is sent - not even the question - unless the handshake says
        // so (RetrieveCount.CAPABILITY, exactly like TemporaryChat).
        val rt = repoFile("$main/JarvisRuntime.kt").readText()
        val fn = rt.substring(rt.indexOf("suspend fun retrieveCount("))
        val body = fn.substring(0, fn.indexOf("\n    }"))
        assertTrue("the capability gates the whole call",
            body.contains("if (!can(com.jarvis.client.net.RetrieveCount.CAPABILITY))") &&
                body.indexOf("api.retrieveCount") > body.indexOf("CAPABILITY"))
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        assertTrue("the request goes out with count=1 only",
            api.contains("val path = RetrieveCount.path(question)"))
        assertTrue("the reply is read as counts or dropped",
            api.contains("RetrieveCount.parse(r.value)"))
    }

    @Test
    fun theCountIsHiddenWithTheMemoryLists() {
        // The PC blanks this route itself while the memory lists are hidden
        // (lock/rules.rs redact_hud_read), so the phone asks for nothing in
        // that state - the same rule, not a second one.
        val home = repoFile("$main/ui/screens/HomeScreen.kt").readText()
        assertTrue(home.contains("retrieve.question != null && !retrieve.hidden"))
        assertTrue(home.contains("RetrieveCount.line("))
        assertTrue("a count, drawn as ordinary quiet text",
            home.contains("val line = shown?.let { com.jarvis.client.net.RetrieveCount.line(it.count) }"))
    }

    // ------------------------------------------------------- the PC's half ---

    @Test
    fun thePcHasACountOnlyBranchAndItNeverPacksTheWords() {
        val patch = repoFile("backend/retrieve-count.patch").readText()
        val added = patch.lines().filter { it.startsWith("+") && !it.startsWith("+++") }
            .map { it.removePrefix("+") }
        assertTrue("the count-only reader is added", added.any { it.startsWith("def _retrieve_counts(") })
        assertTrue("`count=1` is what reaches it", added.any { it.contains("_retrieve_counts(q)") })
        assertTrue("`pack()` - the one place text enters a reply - is never called from it",
            added.none { it.contains("pack(") })
        // The reply's own keys: four, and no `text`, `id`, `kind`, `hits` or `near` list.
        assertTrue(added.any { it.contains("\"count_only\": True") })
        assertTrue(added.any { it.contains("\"recalled\": len(") })
        assertTrue(added.any { it.contains("\"near\": len(") })
        assertTrue(added.none { it.contains("\"text\"") })
        // Registered, so the whole stack applies it on the owner's PC.
        assertTrue("apply-patches.ps1 applies it",
            repoFile("scripts/apply-patches.ps1").readText().contains("'retrieve-count.patch'"))
        // And the capability both apps read is the same word on both sides.
        val events = repoFile("backend/rebuilt/jarvis_events.py").readText()
        assertTrue(events.contains("\"${RetrieveCount.CAPABILITY}\": _hud_has(\"_retrieve_counts\")"))
        assertTrue(repoFile("jarvis-backend/jarvis_events.py").readText()
            .contains("\"${RetrieveCount.CAPABILITY}\": _hud_has(\"_retrieve_counts\")"))
    }

    @Test
    fun theWordsAreBothAppsWordForWord() {
        assertEquals("Your PC's Jarvis cannot count what it reached for yet - run " +
            "apply-patches.ps1 on the PC to update it.", RetrieveCount.MISSING)
        assertEquals("/api/retrieve", RetrieveCount.PATH)
        assertEquals("retrieve_count", RetrieveCount.CAPABILITY)
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
