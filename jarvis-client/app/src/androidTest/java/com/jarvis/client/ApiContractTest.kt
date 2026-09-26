package com.jarvis.client

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.AnswerMark
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Briefing
import com.jarvis.client.net.ChatSession
import com.jarvis.client.net.Hardware
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.MemoryCards
import com.jarvis.client.net.SaidAloud
import com.jarvis.client.net.Schedule
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.TimeUnit

/**
 * The client against a server that answers.
 *
 * Everything else in this suite is either a pure-JVM test of one function or a
 * three-assertion check that the app opens. Nothing had ever put the real
 * OkHttp client, the real headers, the real token store and the real decoders
 * end to end against something speaking the protocol — so a mismatch between
 * what this client sends and what `jarvis_hud.py` expects could only be found
 * by a human with a paired phone.
 *
 * MockWebServer rather than a hand-rolled socket: it records what arrived,
 * which is the half that matters. Most of these assertions are about the
 * REQUEST, not the response.
 *
 * On 127.0.0.1, which `network_security_config.xml` already permits in
 * cleartext alongside `localhost` and `ts.net` — so this exercises the real
 * policy rather than working around it.
 */
@RunWith(AndroidJUnit4::class)
class ApiContractTest {

    private val context get() = ApplicationProvider.getApplicationContext<android.content.Context>()

    private lateinit var server: MockWebServer
    private lateinit var settings: ClientSettings
    private lateinit var tokens: TokenStore
    private lateinit var api: JarvisApi

    /** Whatever the dispatcher should answer next, by path. */
    private val routes = mutableMapOf<String, MockResponse>()

    private fun ok(json: String) = MockResponse().setResponseCode(200)
        .setHeader("Content-Type", "application/json").setBody(json)

    @Before
    fun start() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.path?.substringBefore('?').orEmpty()
                return routes[path] ?: MockResponse().setResponseCode(404).setBody("{}")
            }
        }
        server.start()

        settings = ClientSettings(context)
        settings.setHost("${server.hostName}:${server.port}")
        tokens = TokenStore(context)
        tokens.setToken(TOKEN)
        api = JarvisApi(settings, tokens)
    }

    @After
    fun stop() {
        tokens.clear()
        settings.setHost("")
        server.shutdown()
    }

    // ------------------------------------------------------------ headers ---

    /**
     * §2: the token on every request, and `X-Jarvis-Client: hud` beside it.
     *
     * Asserted across several routes rather than one, because the header is
     * applied by a helper that a new endpoint can simply forget to call — and
     * forgetting it is a 403 from the origin check that reads like the desktop
     * being unreachable.
     */
    @Test
    fun everyRequestCarriesTheTokenAndTheClientHeader() = runBlocking {
        routes["/api/status"] = ok("""{"ok":true}""")
        routes["/api/pending"] = ok("""{"available":true,"pending":[]}""")
        routes["/api/attention"] = ok("""{"available":true}""")
        routes["/api/approve"] = ok("{}")

        api.status(); api.pending(); api.attention(); api.approve("a1")

        repeat(4) {
            val req = server.takeRequest(10, TimeUnit.SECONDS)
            assertNotNull("a request never arrived", req)
            assertEquals(
                "${req!!.path} did not carry the token",
                TOKEN, req.getHeader("X-Jarvis-Token"),
            )
            assertEquals(
                "${req.path} did not identify the client",
                "hud", req.getHeader("X-Jarvis-Client"),
            )
        }
    }

    /**
     * Rule 3 says the token is the one secret this app stores. A secret in a
     * URL is a secret in every proxy log and every crash report that quotes
     * the request line, so it belongs in a header and nowhere else.
     */
    @Test
    fun theTokenNeverAppearsInTheRequestLineOrABody() = runBlocking {
        routes["/api/pending"] = ok("""{"available":true,"pending":[]}""")
        routes["/api/approve"] = ok("{}")

        api.pending(); api.approve("a1")

        repeat(2) {
            val req = server.takeRequest(10, TimeUnit.SECONDS)!!
            assertFalse("the token is in the request line", req.path!!.contains(TOKEN))
            assertFalse("the token is in the body", req.body.readUtf8().contains(TOKEN))
        }
    }

    // ------------------------------------------------------------- shapes ---

    /**
     * The wrapper `/api/pending` actually sends, decoded through the real
     * stack. The row carries what jarvis_gate.pending() puts on it - `action`,
     * `detail` as JSON text, `notice` - and no `title`: this test used to
     * hand the phone a title the server never sends.
     */
    @Test
    fun pendingDecodesTheServersRealShape() = runBlocking {
        routes["/api/pending"] = ok(
            """{"available":true,
                "pending":[{"id":"a1","action":"send_email","tier":"ask",
                            "detail":"{\"to\": \"dana@example.com\"}",
                            "prompt":"Send the email to Dana",
                            "notice":{"title":"Jarvis wants to send an email",
                                      "body":"there is no unsend. nothing has happened yet.",
                                      "weight":"heavy","deny_ok":true,"approve_ok":false},
                            "risk":{"why":"leaves this machine","swipe_ok":false},
                            "expires_in":120}],
                "history":[{"id":"old"}]}""",
        )
        val out = api.pending()
        assertTrue("the documented shape did not decode: $out", out is ApiResult.Ok)
        val items = (out as ApiResult.Ok).value
        assertEquals(1, items.size)
        assertEquals("a1", items[0].id)
        assertEquals("Jarvis wants to send an email", items[0].title)
        assertEquals("Send the email to Dana", items[0].summary)
        assertTrue(items[0].expiresAtMs != null)
    }

    /** One row the phone cannot read costs that row, never the whole queue. */
    @Test
    fun oneUnreadableRowDoesNotSinkTheQueue() = runBlocking {
        routes["/api/pending"] = ok(
            """{"available":true,"pending":[{"action":"no_id"},
                {"id":7,"action":"send_email","detail":{"to":"x"},"raised":true}]}""",
        )
        val out = api.pendingRead()
        assertTrue("$out", out is ApiResult.Ok)
        val read = (out as ApiResult.Ok).value
        assertEquals(1, read.skipped)
        assertEquals("7", read.items.single().id)
        assertTrue(read.items.single().raised != null)
    }

    /**
     * "There is no approval queue here" and "the approval queue is empty" are
     * different sentences and only one of them is reassuring. Covered as a
     * pure function elsewhere; covered here through HTTP, because that is
     * where it would actually be wrong.
     */
    @Test
    fun availableFalseIsNotAnEmptyQueue() = runBlocking {
        routes["/api/pending"] = ok("""{"available":false}""")
        val out = api.pending()
        assertTrue(out is ApiResult.Failed)
        assertEquals(ApiError.NotAvailable, (out as ApiResult.Failed).error)
    }

    /** A decision posts the id and nothing else — no verdict duplicated in the body. */
    @Test
    fun approvePostsTheIdAlone() = runBlocking {
        routes["/api/approve"] = ok("{}")
        api.approve("a1")
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("POST", req.method)
        assertEquals("/api/approve", req.path)
        assertEquals("""{"id":"a1"}""", req.body.readUtf8())
    }

    /**
     * CLAUDE.md's 2026-09-20 amendment: install joins switch as tier `ask`,
     * so the request shape is the same one `approvePostsTheIdAlone` proves
     * above for a different route - the same `{"ref": ...}` body
     * `switchModel` already sends, on `/install` instead of `/switch`.
     *
     * The 202 is the point, not an afterthought: `docs/JARVIS-API.md` says
     * install answers 202 while switch answers a 2xx generically, and
     * `postJson`'s own `isSuccessful` check treats every 2xx alike - so this
     * is the one place that distinction would go unnoticed if `postJson`
     * ever narrowed to `== 200`.
     */
    @Test
    fun installPostsTheRefAloneAndAcceptsA202() = runBlocking {
        routes["/api/models/install"] = MockResponse().setResponseCode(202).setBody("{}")
        val out = api.installModel("llama3.1:8b")
        assertTrue(out is ApiResult.Ok)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("POST", req.method)
        assertEquals("/api/models/install", req.path)
        assertEquals("""{"ref":"llama3.1:8b"}""", req.body.readUtf8())
    }

    /**
     * A refused token must be BadToken, not a generic server error: the two
     * produce different sentences, and only one of them tells the owner to go
     * and re-pair.
     */
    @Test
    fun aRefusedTokenIsReportedAsARefusedToken() = runBlocking {
        routes["/api/pending"] = MockResponse().setResponseCode(401).setBody("{}")
        val out = api.pending()
        assertTrue(out is ApiResult.Failed)
        assertEquals(ApiError.BadToken, (out as ApiResult.Failed).error)
    }

    // ---------------------------------------------------------- learning ---

    /**
     * `feedback.patch`: one answer id and one mark, and nothing else - the
     * route refuses a list, so there can be no "mark all".
     */
    @Test
    fun markingAnAnswerPostsOneIdAndOneMark() = runBlocking {
        routes["/api/feedback/mark"] = ok(
            """{"ok":true,"turn_id":"$TURN","mark":"wrong","was":"none","changed":true,"facts":2,"retire_cards_raised":0}""",
        )
        val out = api.markAnswer(TURN, AnswerMark.WRONG)
        assertTrue("mark failed: $out", out is ApiResult.Ok)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("POST", req.method)
        assertEquals("/api/feedback/mark", req.path)
        assertEquals("hud", req.getHeader("X-Jarvis-Client"))
        assertEquals("""{"turn_id":"$TURN","mark":"wrong"}""", req.body.readUtf8())
    }

    /** A backend without jarvis_feedback.py answers 503 - "not here", not "broken". */
    @Test
    fun markingOnABackendWithoutTheModuleIsNotAvailable() = runBlocking {
        routes["/api/feedback/mark"] = MockResponse().setResponseCode(503)
            .setBody("""{"error":"ModuleNotFoundError: jarvis_feedback"}""")
        val out = api.markAnswer(TURN, AnswerMark.RIGHT)
        assertEquals(ApiError.NotAvailable, (out as ApiResult.Failed).error)
    }

    /** An id the backend would refuse is never sent at all. */
    @Test
    fun aBadAnswerIdIsNeverSent() = runBlocking {
        val out = api.markAnswer("not-an-id", AnswerMark.WRONG)
        assertTrue(out is ApiResult.Failed)
        assertEquals(0, server.requestCount)
    }

    /** `memory-intake.patch`: "Both are true" posts ONE proposal id, like decide. */
    @Test
    fun bothAreTruePostsOneProposalId() = runBlocking {
        routes["/api/memory/keep_both"] = ok(
            """{"ok":true,"id":7,"fact_id":40,"kept_id":12,"kept_text":"old"}""",
        )
        val out = api.keepBothMemory(7)
        assertTrue(out is ApiResult.Ok)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("/api/memory/keep_both", req.path)
        assertEquals("""{"id":7}""", req.body.readUtf8())
    }

    /** A card with no old fact to keep: 409, reported as "already handled", not a crash. */
    @Test
    fun bothAreTrueRefusedIsA409NotAFailureWall() = runBlocking {
        routes["/api/memory/keep_both"] = MockResponse().setResponseCode(409)
            .setBody("""{"ok":false,"reason":"not_a_correction","note":"x"}""")
        val out = api.keepBothMemory(7)
        assertEquals(ApiError.AlreadyHandled, (out as ApiResult.Failed).error)
    }

    /**
     * The review queue is read WITH `retire_cards=1`, because this app labels
     * the "stop using this fact?" card for what it does. Without it the
     * backend hides those cards and they wait for ever.
     */
    @Test
    fun theReviewQueueAsksForRetireCards() = runBlocking {
        routes["/api/memory/pending"] = ok("""{"available":true,"pending":[],"setup":{}}""")
        api.probe(MemoryCards.PENDING_PATH)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("/api/memory/pending?retire_cards=1&sleep_offer=1", req.path)
    }

    /**
     * The answer's id comes from the `X-Jarvis-Route` response header, through
     * the real ChatSession, and a new question clears it before its own
     * answer arrives.
     */
    @Test
    fun theAnswersIdIsReadFromTheRouteHeader() = runBlocking {
        routes["/api/chat"] = MockResponse().setResponseCode(200)
            .setHeader("Content-Type", "text/plain")
            .setHeader("X-Jarvis-Route", """{"lane":"local","injected_ids":["mem:3"],"turn_id":"$TURN"}""")
            .setBody("Hello there.")
        val chat = ChatSession(api)
        val reply = chat.send("hi")
        assertEquals("Hello there.", reply)
        assertEquals(TURN, chat.turnId.value)

        // An older backend: no turn_id, so no mark buttons for this answer.
        routes["/api/chat"] = MockResponse().setResponseCode(200)
            .setHeader("Content-Type", "text/plain")
            .setHeader("X-Jarvis-Route", """{"lane":"local"}""")
            .setBody("Again.")
        chat.send("again")
        assertEquals(null, chat.turnId.value)
    }

    /**
     * Every reply the desktop REALLY sends, through the real ChatSession.
     *
     * `chat-stream-cases.json` is written by running the backend's producer
     * (`backend/test_chat_stream_contract.py --write`, which fails if this
     * copy is stale): Ollama's real stream as relayed by `/api/chat`, with
     * the Content-Type the desktop sends, keepalive and approval-status
     * lines, an answer cut short at the length limit, and the desktop's own
     * error sentences. The test above uses "Hello there." as text/plain,
     * which no server of this project sends; this is the one that matters.
     */
    @Test
    fun theRealRepliesReadThroughTheRealChatSession() = runBlocking {
        val text = requireNotNull(javaClass.classLoader?.getResourceAsStream("chat-stream-cases.json")) {
            "chat-stream-cases.json is missing from androidTest resources"
        }.bufferedReader().readText()
        val doc = org.json.JSONObject(text)
        val headers = doc.getJSONArray("route_headers")
        val localRoute = (0 until headers.length()).map { headers.getJSONObject(it) }
            .first { it.getJSONObject("expect").getString("where") == "local" }
            .getString("header")
        val cases = doc.getJSONArray("cases")
        assertTrue("no cases", cases.length() >= 10)
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val name = c.getString("name")
            val exp = c.getJSONObject("expect")
            routes["/api/chat"] = MockResponse().setResponseCode(200)
                .setHeader("Content-Type", c.getString("content_type"))
                .setHeader("X-Jarvis-Route", localRoute)
                .setBody(c.getString("body"))
            val chat = ChatSession(api)
            val reply = chat.send("hi")
            if (!exp.isNull("error")) {
                assertEquals(name, null, reply)
                assertEquals(name, exp.getString("error"), chat.error.value)
                assertEquals("$name: a failed turn is not kept", 0, chat.history.value.size)
                continue
            }
            assertEquals(name, exp.getString("text"), reply)
            assertEquals("$name: no error", null, chat.error.value)
            assertEquals("$name: a finished answer is kept", 1, chat.history.value.size)
            assertEquals(
                "$name: cut short is said under the answer",
                exp.getBoolean("length"),
                chat.answerNote.value?.startsWith("Cut short") == true,
            )
            assertEquals("$name: nothing left waiting", null, chat.waiting.value)
        }
    }

    /**
     * A follow-up carries the conversation so far (net/ChatHistory.kt). The
     * phone used to send the newest question alone, so every follow-up
     * reached the desktop with nothing before it. Read off the wire, from
     * the real ChatSession, not from the body builder alone.
     */
    @Test
    fun aFollowUpCarriesTheConversationAndNewConversationDropsIt() = runBlocking {
        // "role:content" for each message in the request body, in order.
        fun roles(req: RecordedRequest): List<String> {
            val msgs = org.json.JSONObject(req.body.readUtf8()).getJSONArray("messages")
            return (0 until msgs.length()).map {
                val o = msgs.getJSONObject(it)
                "${o.getString("role")}:${o.getString("content")}"
            }
        }
        fun answer(text: String) = MockResponse().setResponseCode(200)
            .setHeader("Content-Type", "text/plain").setBody(text)
        val chat = ChatSession(api)

        routes["/api/chat"] = answer("Tuesday at 3.")
        chat.send("when is the dentist?")
        assertEquals(listOf("user:when is the dentist?"),
            roles(server.takeRequest(10, TimeUnit.SECONDS)!!))

        routes["/api/chat"] = answer("Yes, Wednesday is free.")
        chat.send("can I move it?")
        assertEquals(
            listOf("user:when is the dentist?", "assistant:Tuesday at 3.", "user:can I move it?"),
            roles(server.takeRequest(10, TimeUnit.SECONDS)!!),
        )
        assertEquals(2, chat.history.value.size)

        // A failed answer is not added: nothing half-said gets replayed.
        routes["/api/chat"] = MockResponse().setResponseCode(503).setBody("""{"error":"loading"}""")
        chat.send("and the vet?")
        server.takeRequest(10, TimeUnit.SECONDS)
        assertEquals(2, chat.history.value.size)

        chat.newConversation()
        assertEquals(0, chat.history.value.size)
        assertEquals(null, chat.question.value)
        routes["/api/chat"] = answer("Hello.")
        chat.send("hi")
        assertEquals(listOf("user:hi"), roles(server.takeRequest(10, TimeUnit.SECONDS)!!))
    }

    /**
     * Chat history on the PC (docs/JARVIS-API.md section 18), read off the
     * wire from the real ChatSession: every request says which conversation
     * it belongs to and that it came from the phone, each question says
     * where its words came from - and keeps saying so when it is sent again -
     * and shared text goes as its own message, before the typed one. "New
     * conversation" means a new id.
     */
    @Test
    fun everyChatSaysItsConversationAndWhereEachQuestionCameFrom() = runBlocking {
        fun body(req: RecordedRequest): org.json.JSONObject = org.json.JSONObject(req.body.readUtf8())
        fun tags(o: org.json.JSONObject): List<String> {
            val msgs = o.getJSONArray("messages")
            return (0 until msgs.length()).map { msgs.getJSONObject(it).optString("provenance") }
        }
        routes["/api/chat"] = MockResponse().setResponseCode(200)
            .setHeader("Content-Type", "text/plain").setBody("Noted.")
        val chat = ChatSession(api)

        chat.send("what is this about?", shared = "an article from another app")
        val first = body(server.takeRequest(10, TimeUnit.SECONDS)!!)
        val id = first.getString("conversation_id")
        assertEquals("phone", first.getString("device"))
        assertEquals(listOf("shared", "typed"), tags(first))
        assertEquals(
            "an article from another app",
            first.getJSONArray("messages").getJSONObject(0).getString("content"),
        )

        chat.send("and this?", provenance = "voice")
        val second = body(server.takeRequest(10, TimeUnit.SECONDS)!!)
        assertEquals(id, second.getString("conversation_id"))
        // The earlier turn's tags ride along with it; the answer has none.
        assertEquals(listOf("shared", "typed", "", "voice"), tags(second))

        chat.newConversation()
        chat.send("hi")
        val third = body(server.takeRequest(10, TimeUnit.SECONDS)!!)
        assertFalse("a new conversation kept the old id", third.getString("conversation_id") == id)
        assertEquals(listOf("typed"), tags(third))
    }

    /**
     * The History routes (section 18), with the token and the client header
     * like every other: one page, one conversation, and one delete - by id,
     * in the body, never in bulk.
     */
    @Test
    fun theHistoryRoutesAreTheContracts() = runBlocking {
        routes["/api/history"] = ok(
            """{"enabled":true,"recording":true,"why_not":"","waiting":false,"keep_days":0,
               "encrypted":true,"conversations":[{"id":"abcd1234","title":"Dentist","started":1,
               "updated":2,"turns":2,"device":"phone","has_voice":false,"tainted":false}]}""",
        )
        routes["/api/history/delete"] = ok("""{"ok":true}""")

        val page = api.history()
        assertTrue(page is ApiResult.Ok)
        val list = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("/api/history?limit=30", list.path)
        assertEquals("hud", list.getHeader("X-Jarvis-Client"))
        assertEquals(TOKEN, list.getHeader("X-Jarvis-Token"))

        val gone = api.deleteHistory("abcd1234")
        assertTrue(gone is ApiResult.Ok)
        val del = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("POST", del.method)
        assertEquals("abcd1234", org.json.JSONObject(del.body.readUtf8()).getString("id"))
        assertEquals("hud", del.getHeader("X-Jarvis-Client"))

        // Gone already: 404, said as such.
        val missing = api.historyConversation("nope1234")
        assertEquals(ApiResult.Failed(ApiError.NotFound), missing)
        assertEquals("/api/history/conversation?id=nope1234", server.takeRequest(10, TimeUnit.SECONDS)!!.path)
    }

    // ------------------------------------------------------------- voice ---

    /**
     * A 503 from `/api/voice/say` is not permission to speak the text here.
     *
     * The client used to treat "no audio came back" as licence to hand the
     * reply to the handset's default engine - which on a stock phone
     * synthesises over the network. The reply is composed from the owner's
     * recalled facts, so that was rule 1 being broken on the normal path.
     * Whether this device may substitute its own voice is the server's call,
     * and an ABSENT flag must read as no.
     */
    @Test
    fun anAbsentFallbackFlagMeansDoNotSpeakItHere() = runBlocking {
        routes["/api/voice/say"] = MockResponse().setResponseCode(503)
            .setHeader("Content-Type", "application/json")
            .setBody("""{"error":"speech module not installed"}""")

        val out = api.say("the reply, composed from recalled facts")
        assertTrue(out is ApiResult.Ok)
        val said = (out as ApiResult.Ok).value
        assertTrue("a 503 must decode as NoEngine", said is SaidAloud.NoEngine)
        assertFalse(
            "an absent client_fallback_ok was read as permission",
            (said as SaidAloud.NoEngine).fallbackOk,
        )
    }

    /** And when the server does allow it, that is carried through honestly. */
    @Test
    fun anExplicitFallbackFlagIsHonoured() = runBlocking {
        routes["/api/voice/say"] = MockResponse().setResponseCode(503)
            .setHeader("Content-Type", "application/json")
            .setBody("""{"client_fallback_ok": true, "reason": "no engine installed"}""")

        val said = (api.say("hello") as ApiResult.Ok).value
        assertTrue(said is SaidAloud.NoEngine)
        assertTrue((said as SaidAloud.NoEngine).fallbackOk)
        assertEquals("no engine installed", said.reason)
    }

    /** A 200 carrying no audio is a server fault, not a licence either. */
    @Test
    fun anEmptySuccessIsNotPermissionEither() = runBlocking {
        routes["/api/voice/say"] = MockResponse().setResponseCode(200).setBody("")
        val said = (api.say("hello") as ApiResult.Ok).value
        assertTrue(said is SaidAloud.NoEngine)
        assertFalse((said as SaidAloud.NoEngine).fallbackOk)
    }

    // ---------------------------------------------------------- hardware ---

    /**
     * `hardware.patch` (JARVIS-API §20): the GET carries the token and the
     * client header like every other route, and its answer is read by the
     * same parser the JVM test checks against the real fixture.
     */
    @Test
    fun theHardwareReadCarriesTheHeadersAndParses() = runBlocking {
        routes[Hardware.PATH] = ok(
            """{"available":true,"found":"Found 1 graphics card.","cards":[],"presets":[],""" +
                """"now":{"label":"Custom (your own setup)","words":""}}""",
        )
        val out = api.hardware()
        assertTrue("read failed: $out", out is ApiResult.Ok)
        assertNotNull(Hardware.parse((out as ApiResult.Ok).value))
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals(Hardware.PATH, req.path)
        assertEquals(TOKEN, req.getHeader("X-Jarvis-Token"))
        assertEquals("hud", req.getHeader("X-Jarvis-Client"))
    }

    /** Choosing a setup posts the setup's id and nothing else. */
    @Test
    fun choosingASetupPostsTheIdAlone() = runBlocking {
        routes[Hardware.APPLY_PATH] = ok("""{"ok":true,"chosen":"smart","message":"chosen"}""")
        val out = api.hardwarePost(Hardware.APPLY_PATH, Hardware.applyBody("smart"))
        assertTrue(out is ApiResult.Ok)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("POST", req.method)
        assertEquals("""{"preset":"smart"}""", req.body.readUtf8())
    }

    /**
     * A step is posted only to one of the four routes a step may name; any
     * other route is refused before a request is made.
     */
    @Test
    fun aHardwarePostToAnyOtherRouteIsNeverSent() = runBlocking {
        val out = api.hardwarePost("/api/shutdown", "{}")
        assertTrue(out is ApiResult.Failed)
        assertEquals("a request reached the server", 0, server.requestCount)
    }

    /** A refusal's own sentence comes back to be shown, not a failure wall. */
    @Test
    fun aRefusedMakeIsThePcsOwnSentence() = runBlocking {
        routes[Hardware.CREATE_PATH] = MockResponse().setResponseCode(409)
            .setHeader("Content-Type", "application/json")
            .setBody("""{"error":"download qwen3:8b first"}""")
        val out = api.hardwarePost(Hardware.CREATE_PATH, """{"name":"jarvis-chat"}""")
        assertTrue(out is ApiResult.Ok)
        assertEquals("Download qwen3:8b first.", Hardware.replyLine(out))
    }

    // ---------------------------------------------------------- schedule ---

    /**
     * `schedule.patch` (JARVIS-API §21): the list is read with the token and
     * the client header, and one job is read by id for a notification.
     */
    @Test
    fun theScheduleReadCarriesTheHeadersAndParses() = runBlocking {
        routes[Schedule.PATH] = ok(
            """{"available":true,"jobs":[{"id":"s0123456789","kind":"timer","text":"",""" +
                """"state":"active","left":60,"duration":60}],"todo":[]}""",
        )
        val out = api.schedule()
        assertTrue("read failed: $out", out is ApiResult.Ok)
        assertEquals(1, Schedule.parse((out as ApiResult.Ok).value)!!.jobs.size)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals(Schedule.PATH, req.path)
        assertEquals(TOKEN, req.getHeader("X-Jarvis-Token"))
        assertEquals("hud", req.getHeader("X-Jarvis-Client"))
        val one = api.scheduleJob("s0123456789")
        assertTrue(one is ApiResult.Ok)
        assertEquals(Schedule.PATH + "?id=s0123456789", server.takeRequest(10, TimeUnit.SECONDS)!!.path)
    }

    /** One change posts one id and one action, and nothing else. */
    @Test
    fun oneChangeIsOneIdAndOneAction() = runBlocking {
        routes[Schedule.ACT_PATH] = ok("""{"ok":true,"id":"s0123456789","said":"Paused."}""")
        val out = api.scheduleWrite(Schedule.ACT_PATH, Schedule.actBody("s0123456789", "pause")!!)
        assertTrue(out is ApiResult.Ok)
        assertEquals("Paused.", Schedule.said((out as ApiResult.Ok).value).second)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("POST", req.method)
        assertEquals("""{"id":"s0123456789","do":"pause"}""", req.body.readUtf8())
    }

    /** A schedule write to any other route, or for a job id that is not one, is never sent. */
    @Test
    fun aScheduleWriteElsewhereIsNeverSent() = runBlocking {
        assertTrue(api.scheduleWrite("/api/shutdown", "{}") is ApiResult.Failed)
        assertTrue(api.scheduleJob("all") is ApiResult.Failed)
        assertEquals("a request reached the server", 0, server.requestCount)
    }

    // -------------------------------------------------- morning briefing ---

    /**
     * `briefing.patch` (JARVIS-API §22): the briefing is read with the token
     * and the client header; "Brief me now" is a POST of an empty object.
     */
    @Test
    fun theBriefingReadAndBriefMeNow() = runBlocking {
        val body = """{"available":true,"building":false,"briefing":null,"setups":[],"sources":{}}"""
        routes[Briefing.PATH] = ok(body)
        routes[Briefing.NOW_PATH] = ok(body)
        val out = api.briefing()
        assertTrue("read failed: $out", out is ApiResult.Ok)
        assertNotNull(Briefing.parse((out as ApiResult.Ok).value))
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals(Briefing.PATH, req.path)
        assertEquals(TOKEN, req.getHeader("X-Jarvis-Token"))
        assertEquals("hud", req.getHeader("X-Jarvis-Client"))
        assertTrue(api.briefingNow() is ApiResult.Ok)
        val now = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("POST", now.method)
        assertEquals(Briefing.NOW_PATH, now.path)
        assertEquals("{}", now.body.readUtf8())
    }

    /** Setting one up is the scheduler's own route, with ONE repeat and nothing else. */
    @Test
    fun settingUpABriefingIsOneRepeatOnTheSchedulersRoute() = runBlocking {
        routes[Schedule.ADD_PATH] = MockResponse().setResponseCode(202)
            .setHeader("Content-Type", "application/json")
            .setBody("""{"ok":true,"waiting":true,"job":{"id":"s0123456789","kind":"briefing"}}""")
        val out = api.scheduleWrite(Schedule.ADD_PATH, Briefing.setupBody("weekday", "07:00")!!)
        assertTrue(out is ApiResult.Ok)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("""{"kind":"briefing","repeat":{"every":"weekday","at":"07:00"}}""", req.body.readUtf8())
    }

    /** The overnight-tidy card's "Not now" sends not_now and nothing else. */
    @Test
    fun notNowOnTheOvernightCardSendsOnlyNotNow() = runBlocking {
        routes["/api/memory/sleep_time"] = ok("""{"ok":true}""")
        assertTrue(api.setSleepTime(notNow = true) is ApiResult.Ok)
        val req = server.takeRequest(10, TimeUnit.SECONDS)!!
        assertEquals("""{"not_now":true}""", req.body.readUtf8())
    }

    private companion object {
        const val TOKEN = "jarvis_pair_contract_test"
        const val TURN = "0123456789abcdef0123456789abcdef"
    }
}
