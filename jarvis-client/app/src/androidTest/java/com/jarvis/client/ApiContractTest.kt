package com.jarvis.client

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.AnswerMark
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.ChatSession
import com.jarvis.client.net.JarvisApi
import com.jarvis.client.net.MemoryCards
import com.jarvis.client.net.SaidAloud
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

    /** The wrapper `/api/pending` actually sends, decoded through the real stack. */
    @Test
    fun pendingDecodesTheServersRealShape() = runBlocking {
        routes["/api/pending"] = ok(
            """{"available":true,
                "pending":[{"id":"a1","title":"Send the email to Dana",
                            "risk":{"why":"leaves this machine","swipe_ok":false}}],
                "history":[{"id":"old"}]}""",
        )
        val out = api.pending()
        assertTrue("the documented shape did not decode: $out", out is ApiResult.Ok)
        val items = (out as ApiResult.Ok).value
        assertEquals(1, items.size)
        assertEquals("a1", items[0].id)
        assertEquals("Send the email to Dana", items[0].title)
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
        assertEquals("/api/memory/pending?retire_cards=1", req.path)
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

    private companion object {
        const val TOKEN = "jarvis_pair_contract_test"
        const val TURN = "0123456789abcdef0123456789abcdef"
    }
}
