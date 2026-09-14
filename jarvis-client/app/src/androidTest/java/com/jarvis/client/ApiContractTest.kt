package com.jarvis.client

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.data.TokenStore
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisApi
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

    private companion object {
        const val TOKEN = "jarvis_pair_contract_test"
    }
}
