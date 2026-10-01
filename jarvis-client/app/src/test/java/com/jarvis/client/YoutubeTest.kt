package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Quiz
import com.jarvis.client.net.Youtube
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Quiz me on a YouTube video" on the phone (docs/STUDY-FROM-TEXT-DESIGN.md
 * section 14, JARVIS-API section 112; [Youtube]). The words and the sample
 * replies are read from contract/youtube-cases.json, which
 * tools/gen_youtube_cases.py writes and the desktop's tests read as well. The
 * PC's side of the same contract is `backend/test_youtube.py`.
 */
class YoutubeTest {

    private fun obj(json: String) = JarvisJson.parseToJsonElement(json) as JsonObject

    private val fixture: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/youtube-cases.json")) {
            "contract/youtube-cases.json is missing - run tools/gen_youtube_cases.py"
        }.readText()
        obj(text)
    }
    private val words get() = fixture["words"]!!.jsonObject
    private fun w(key: String) = words[key]!!.jsonPrimitive.content
    private val samples get() = fixture["samples"]!!.jsonObject

    private fun sample(name: String): Pair<Quiz.Reply, JsonObject> {
        val s = samples[name]!!.jsonObject
        return Quiz.Reply(s["status"]!!.jsonPrimitive.int, s["body"]!!.jsonObject) to s["expect"]!!.jsonObject
    }

    private fun str(o: JsonObject, k: String): String? =
        o[k]?.takeIf { it !is JsonNull }?.jsonPrimitive?.content
    private fun flag(o: JsonObject, k: String): Boolean? = o[k]?.jsonPrimitive?.content?.toBooleanStrictOrNull()

    // -------------------------------------------------------------- words ----

    @Test
    fun theWordsAreTheGeneratedFixturesWordsForWord() {
        listOf(
            "title" to Youtube.TITLE,
            "intro" to Youtube.INTRO,
            "terms" to Youtube.TERMS,
            "outside" to Youtube.OUTSIDE,
            "placeholder" to Youtube.PLACEHOLDER,
            "start" to Youtube.START,
            "cancel" to Youtube.CANCEL,
            "label" to Youtube.LABEL,
            "missing" to Youtube.MISSING,
        ).forEach { (key, mine) -> assertEquals(key, w(key), mine) }
        // And the fixture holds nothing this phone does not check.
        assertEquals(9, words.size)
    }

    @Test
    fun theSmallRulesAreTheFixturesRules() {
        assertEquals(fixture["poll_seconds"]!!.jsonPrimitive.int, Youtube.POLL_SECONDS)
        assertEquals(fixture["unknown_state_limit_seconds"]!!.jsonPrimitive.int, Youtube.UNKNOWN_STATE_LIMIT_SECONDS)
        assertEquals(fixture["link_max"]!!.jsonPrimitive.int, Youtube.LINK_MAX)
        for ((state, phase) in fixture["phases"]!!.jsonObject) {
            assertEquals(state, phase.jsonPrimitive.content, Youtube.phase(state).name.lowercase())
            assertTrue(state, Youtube.isKnown(state))
        }
        // The state words the phone falls back on are the contract's reference words.
        for ((state, said) in fixture["state_words"]!!.jsonObject) {
            val r = Youtube.Request("0123456789ab", state, "", null, false, null, null, null)
            assertEquals(state, said.jsonPrimitive.content, Youtube.shown(r))
        }
    }

    @Test
    fun theTermsLineSaysItBreaksYouTubesTermsAndIsAlwaysThere() {
        assertTrue(Youtube.TERMS.contains("breaks YouTube's terms"))
        assertTrue(Youtube.TERMS.contains("never the video or its sound"))
        assertTrue(Youtube.INTRO.contains("card first, every time"))
    }

    // ------------------------------------------------------------- phases ----

    @Test
    fun onlyWaitingOffersCancelAndAnUnknownStateKeepsWorking() {
        assertEquals(Youtube.Phase.WAITING, Youtube.phase("waiting"))
        assertEquals(Youtube.Phase.WORKING, Youtube.phase("fetching"))
        assertEquals(Youtube.Phase.WORKING, Youtube.phase("writing"))
        assertEquals(Youtube.Phase.READY, Youtube.phase("ready"))
        for (s in listOf("denied", "timed_out", "withdrawn", "refused", "failed")) {
            assertEquals(s, Youtube.Phase.ENDED, Youtube.phase(s))
            assertFalse(s, Youtube.keepPolling(Youtube.phase(s)))
        }
        assertEquals(Youtube.Phase.WORKING, Youtube.phase("something_new"))
        assertEquals(Youtube.Phase.WORKING, Youtube.phase(null))
        assertFalse(Youtube.isKnown("something_new"))
        assertTrue(Youtube.keepPolling(Youtube.Phase.WAITING))
        assertTrue(Youtube.keepPolling(Youtube.Phase.WORKING))
        assertFalse(Youtube.keepPolling(Youtube.Phase.READY))
    }

    @Test
    fun anUnknownStateIsGivenUpAfterThreeMinutesExactly() {
        assertFalse(Youtube.giveUpOnUnknown(null, 999_999L))
        assertFalse(Youtube.giveUpOnUnknown(1_000L, 1_000L + 179_999L))
        assertTrue(Youtube.giveUpOnUnknown(1_000L, 1_000L + 180_000L))
    }

    // ------------------------------------------------------------ parsing ----

    @Test
    fun everySampleReplyIsReadAsTheFixtureSays() {
        for (name in samples.keys) {
            val (reply, expect) = sample(name)
            when {
                name == "info" || name == "info_no_latest" -> {
                    val info = Youtube.parseInfo(reply.body!!)!!
                    assertEquals(name, flag(expect, "available"), info.available)
                    assertEquals(name, expect["link_max"]!!.jsonPrimitive.int, info.linkMax)
                    val want = str(expect, "latest_phase")
                    assertEquals(name, want, info.latest?.phase?.name?.lowercase())
                }
                name.startsWith("refused") || name.startsWith("too_many") -> {
                    val out = Youtube.startedSaid(reply)
                    assertFalse(name, out.ok)
                    assertEquals(name, str(expect, "shown"), out.said)
                    assertEquals(name, str(expect, "code"), out.code)
                }
                else -> {
                    val out = Youtube.readSaid(reply)
                    assertEquals(name, flag(expect, "ok"), out.ok)
                    val req = out.request
                    if (flag(expect, "unreadable") == true) {
                        assertTrue(name, out.said.contains(Youtube.UNREADABLE))
                    } else {
                        assertNotNull(name, req)
                        assertEquals(name, str(expect, "shown"), out.said)
                    }
                    // A "ready" with no quiz in it is over for the phone (the fixture's "ended"):
                    // the outcome is not ok and the runtime forgets the request.
                    str(expect, "phase")?.let {
                        if (req != null && flag(expect, "unreadable") != true) {
                            assertEquals(name, it, req.phase.name.lowercase())
                        }
                    }
                    str(expect, "quiz_id")?.let { assertEquals(name, it, req!!.quiz!!.id) }
                    expect["questions"]?.let { assertEquals(name, it.jsonPrimitive.int, req!!.quiz!!.questions.size) }
                    str(expect, "source")?.let { assertEquals(name, it, req!!.quiz!!.source) }
                    flag(expect, "truncated")?.let { assertEquals(name, it, req!!.truncated) }
                }
            }
        }
    }

    @Test
    fun aReadyRequestOpensTheOrdinaryQuizWithItsSource() {
        val (reply, _) = sample("ready")
        val r = Youtube.parseRequest(reply.body!!)!!
        val q = r.quiz!!
        assertTrue(Youtube.fromCaptions(q))
        assertEquals(listOf(1, 2), q.questions.map { it.n })
        assertNull(q.questions[0].mark)
        // A text quiz has no source.
        val text = Quiz.parseQuiz(obj("""{"ok":true,"quiz":{"id":"abc","questions":[{"n":1,"prompt":"p"}]}}"""))!!
        assertNull(text.source)
        assertFalse(Youtube.fromCaptions(text))
        assertFalse(Youtube.fromCaptions(null))
        // A source word this phone does not know is not "youtube".
        val odd = Quiz.parseQuiz(obj("""{"ok":true,"quiz":{"id":"abc","source":"vimeo","questions":[{"n":1,"prompt":"p"}]}}"""))!!
        assertNull(odd.source)
    }

    @Test
    fun aTruncatedVideoShowsThePcsOwnSentenceAndAWholeOneShowsNone() {
        val (cut, _) = sample("ready_truncated")
        val r = Youtube.parseRequest(cut.body!!)!!
        assertTrue(r.truncated)
        assertEquals(42, r.minutes)
        assertTrue(Youtube.truncatedNote(r)!!.startsWith("Ready. The video is long"))
        val (whole, _) = sample("ready")
        assertNull(Youtube.truncatedNote(Youtube.parseRequest(whole.body!!)!!))
    }

    @Test
    fun unknownKeysAndStatesAreIgnoredNotRefused() {
        val r = Youtube.parseRequest(obj("""{"ok":true,"request":{"id":"0123456789ab","state":"brand_new",
            "message":"Hold on.","x":{"y":1},"quiz":"not an object"}}"""))!!
        assertEquals(Youtube.Phase.WORKING, r.phase)
        assertEquals("Hold on.", r.message)
        assertNull(r.quiz)
        assertNull(Youtube.parseRequest(obj("""{"ok":true,"request":{"state":"waiting"}}""")))
        assertNull(Youtube.parseRequest(obj("""{"ok":true,"request":{"id":"../x","state":"waiting"}}""")))
        assertNull(Youtube.parseRequest(obj("""{"ok":true}""")))
        assertNull(Youtube.parseInfo(obj("""{"ok":true}""")))
    }

    @Test
    fun aReadyRequestWithNoQuestionsIsNotAQuiz() {
        val out = Youtube.readSaid(Quiz.Reply(200, obj(
            """{"ok":true,"request":{"id":"0123456789ab","state":"ready","quiz":{"id":"abc","questions":[]}}}""")))
        assertFalse(out.ok)
        assertTrue(out.said.contains(Youtube.UNREADABLE))
    }

    // ------------------------------------------------------------- bodies ----

    @Test
    fun theStartBodyHasOnlyTheLinkAndTheCount() {
        val b = obj(Youtube.startBody("  https://youtu.be/dQw4w9WgXcQ  "))
        assertEquals(setOf("url", "count"), b.keys)
        assertEquals("https://youtu.be/dQw4w9WgXcQ", b["url"]!!.jsonPrimitive.content)
        assertEquals(Quiz.DEFAULT_COUNT, b["count"]!!.jsonPrimitive.int)
        // No language is offered in the first version.
        assertFalse(b.containsKey("language"))
    }

    @Test
    fun onlyAnEmptyFieldIsRefusedHereAndEverythingElseIsThePcsCall() {
        assertFalse(Youtube.canStart(""))
        assertFalse(Youtube.canStart("   "))
        assertTrue(Youtube.canStart("not a link at all"))
        assertTrue(Youtube.canStart("https://example.com/x"))
    }

    // ------------------------------------------------------------ messages ----

    @Test
    fun everyRefusalIsShownInThePcsOwnWordsNeverRewritten() {
        val refusals = fixture["refusals"]!!.jsonObject
        assertTrue(refusals.size >= 15)
        for ((code, v) in refusals) {
            val status = v.jsonObject["status"]!!.jsonPrimitive.int
            val message = v.jsonObject["message"]!!.jsonPrimitive.content
            val reply = Quiz.Reply(status, buildJsonObject {
                put("ok", false)
                put("error", code)
                put("message", message)
            })
            val out = Youtube.startedSaid(reply)
            assertFalse(code, out.ok)
            assertEquals(code, message, out.said)
            assertEquals(code, code, out.code)
            // "not_found" on a read means the request is gone.
            assertEquals(code, code == "not_found", Youtube.readSaid(reply).gone)
        }
    }

    @Test
    fun aFailedRequestShowsThePcsSentenceAndNeverAnErrorCode() {
        for ((code, said) in fixture["failures"]!!.jsonObject) {
            val text = said.jsonPrimitive.content
            val r = Youtube.parseRequest(buildJsonObject {
                put("ok", true)
                put("request", buildJsonObject {
                    put("id", "0123456789ab")
                    put("state", "failed")
                    put("error", code)
                    put("message", text)
                })
            })!!
            assertEquals(code, Youtube.Phase.ENDED, r.phase)
            assertEquals(code, text, Youtube.shown(r))
            assertFalse(code, Youtube.shown(r).contains(code))
        }
    }

    @Test
    fun aRefusalWithNoMessageGetsAGenericSentenceThatNamesNoLink() {
        val gone = Youtube.startedSaid(Quiz.Reply(404, null))
        assertEquals(Youtube.MISSING, gone.said)
        val busy = Youtube.startedSaid(Quiz.Reply(503, null))
        assertEquals("Not started. Your PC's Jarvis cannot do this right now.", busy.said)
        val odd = Youtube.startedSaid(Quiz.Reply(500, obj("""{"ok":false}""")))
        assertEquals("Not started. Your PC answered 500.", odd.said)
        for (o in listOf(gone, busy, odd)) assertFalse(o.said.contains("youtube.com"))
    }

    @Test
    fun aMissingFeatureIsA404Or501Or503OnTheInfoRead() {
        assertTrue(Youtube.missing(Quiz.Reply(404, null)))
        assertTrue(Youtube.missing(Quiz.Reply(501, null)))
        assertTrue(Youtube.missing(Quiz.Reply(503, null)))
        assertFalse(Youtube.missing(Quiz.Reply(200, obj("""{"ok":true}"""))))
    }

    @Test
    fun theCancelledAnswerIsTheWithdrawnRequest() {
        val out = Youtube.cancelledSaid(Quiz.Reply(200, obj(
            """{"ok":true,"request":{"id":"0123456789ab","state":"withdrawn",
                "message":"You cancelled before the card was answered, so nothing was fetched."}}""")))
        assertTrue(out.ok)
        assertEquals(Youtube.Phase.ENDED, out.request!!.phase)
        assertEquals("You cancelled before the card was answered, so nothing was fetched.", out.said)
        val late = Youtube.cancelledSaid(Quiz.Reply(409, obj(
            """{"ok":false,"error":"already_started","message":"It is already reading the captions and can no longer be cancelled."}""")))
        assertFalse(late.ok)
        assertEquals("already_started", late.code)
        assertFalse(late.gone)
    }

    @Test
    fun aQuizFromCaptionsIsHiddenLikeATextQuiz() {
        val (reply, _) = sample("ready")
        val q = Youtube.parseRequest(reply.body!!)!!.quiz!!
        val hidden = Quiz.hide(q)
        assertTrue(hidden.questions.all { it.prompt == Quiz.HIDDEN_TEXT })
        assertEquals("", hidden.title)
        assertTrue(Youtube.fromCaptions(hidden))
    }

    // --------------------------------------------- the source files' rules ----

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client"

    private fun codeOf(rel: String): String = repoFile("$main/$rel").readText()
        .replace(Regex("/\\*.*?\\*/", RegexOption.DOT_MATCHES_ALL), "")
        .replace(Regex("(?m)(^|\\s)//.*$"), "$1")

    /** The body of one runtime function, from its `fun` line to the next `suspend fun`/`fun`. */
    private fun fnBody(src: String, name: String): String {
        val at = src.indexOf("fun $name(")
        assertTrue("$name not found", at >= 0)
        val rest = src.substring(at + 5)
        val next = Regex("\\n    (private |suspend |internal )*fun ").find(rest)?.range?.first ?: rest.length
        return src.substring(at, at + 5 + next)
    }

    @Test
    fun startingIsHeldOnAStaleLinkButPollingAndCancelAreNot() {
        val rt = codeOf("JarvisRuntime.kt")
        assertTrue(fnBody(rt, "startYoutube").contains("actionBlocker()"))
        assertFalse(fnBody(rt, "pollYoutube").contains("actionBlocker()"))
        assertFalse(fnBody(rt, "cancelYoutube").contains("actionBlocker()"))
        assertFalse(fnBody(rt, "youtubeCheck").contains("actionBlocker()"))
    }

    @Test
    fun theLinkIsNeverKeptLoggedOrPutInAUrlOrANotification() {
        for (f in listOf("net/Youtube.kt", "ui/screens/QuizPlate.kt")) {
            val src = codeOf(f)
            listOf("SharedPreferences", "rememberSaveable", "DataStore", "openFileOutput", "FileWriter",
                "writeText", "Log.", "println", "Notification", "Toast").forEach {
                assertFalse("$f uses $it", src.contains(it))
            }
        }
        val rt = codeOf("JarvisRuntime.kt")
        val whole = listOf("startYoutube", "pollYoutube", "cancelYoutube", "youtubeCheck").joinToString("\n") { fnBody(rt, it) }
        listOf("Log.", "println", "Notification", "SharedPreferences", "writeText").forEach {
            assertFalse("the YouTube functions use $it", whole.contains(it))
        }
        // The link is in the body of the start call only: the path calls carry an id, never the link.
        assertTrue(fnBody(rt, "startYoutube").contains("startBody(link)"))
        assertFalse(fnBody(rt, "startYoutube").contains("_youtube.value = link"))
    }

    @Test
    fun theBlockIsBehindTheHiddenListsAndTheFieldIsClearedOnceTheCardIsRaised() {
        val ui = codeOf("ui/screens/QuizPlate.kt")
        val block = ui.substring(ui.indexOf("private fun YoutubeBlock"))
        assertTrue(block.contains("privateHidden"))
        assertTrue(block.contains("link = \"\""))
        // The link field is drawn only when the lists are shown.
        assertTrue(block.contains("else if (!privateHidden)"))
        // Cancel is offered for the waiting phase only.
        assertTrue(block.contains("Youtube.Phase.WAITING"))
        // Whoever uses the outside line for a captions quiz uses the YouTube one.
        assertTrue(ui.contains("Youtube.OUTSIDE"))
        assertTrue(ui.contains("Youtube.LABEL"))
    }

    @Test
    fun theFourRoutesAreWrittenOutSoTheParityToolCanSeeThem() {
        val src = repoFile("$main/net/Youtube.kt").readText() + repoFile("$main/JarvisRuntime.kt").readText()
        assertTrue(src.contains("\"/api/youtube\""))
        assertTrue(src.contains("\"/api/youtube/quiz\""))
        assertTrue(src.contains("/cancel"))
    }

    /** A file of this repository, found from wherever the tests run. */
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
