package com.jarvis.client.data

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.PlainErrors
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The desktop address: the owner's own networks only (CLAUDE.md, decided
 * 2026-09-26). Held to `src/test/resources/contract/own-network-cases.json`,
 * which tools/gen_own_network_cases.py writes from the backend's own rule
 * (backend/jarvis_local_http.py, `_own_network`). The desktop's Rust reads a
 * byte-identical copy, so the two apps cannot judge an address differently.
 */
class OwnNetworkTest {

    private val cases: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/own-network-cases.json")) {
            "contract/own-network-cases.json is missing - run python3 tools/gen_own_network_cases.py"
        }.readText()
        Json.parseToJsonElement(text) as JsonObject
    }

    private fun rows(list: String): List<Pair<String, Boolean>> =
        cases[list]!!.jsonArray.map { row ->
            val o = row.jsonObject
            val text = (o["host"] ?: o["url"])!!.jsonPrimitive.content
            text to o["own"]!!.jsonPrimitive.boolean
        }

    /** The phone's sentence: it names only the names this phone can connect to. */
    private val message: String get() = cases["phone_message"]!!.jsonPrimitive.content

    @Test
    fun `the words are the shared ones`() {
        assertEquals(message, OwnNetwork.MESSAGE)
        assertEquals(cases["phone_message_unshown"]!!.jsonPrimitive.content, OwnNetwork.message("http://me:pw@evil.com"))
        // The same first half as the desktop's sentence.
        val desktop = cases["message"]!!.jsonPrimitive.content
        assertEquals(desktop.substringBefore(": use "), message.substringBefore(": on this phone"))
    }

    /** Every host, exactly as the backend's `_own_network` judges it. */
    @Test
    fun `every host is judged as the backend judges it`() {
        val hosts = rows("hosts")
        assertTrue("the table lost its hosts", hosts.size > 40)
        for ((host, own) in hosts) {
            assertEquals("\"$host\"", own, OwnNetwork.ownHost(host))
        }
    }

    /** Every whole address the way it is saved: the same verdict, and a refusal in the shared words. */
    @Test
    fun `every origin is judged the same and a refusal says why`() {
        for ((url, own) in rows("origins")) {
            if (own) {
                assertNull(url, OwnNetwork.problem(url))
            } else {
                assertEquals(url, message.replace("{address}", url), OwnNetwork.problem(url))
            }
        }
    }

    /** Odd shapes: nothing the backend refuses gets through. */
    @Test
    fun `nothing the backend refuses is accepted`() {
        for ((url, own) in rows("tricky")) {
            if (!own) assertNotNull("$url was accepted", OwnNetwork.problem(url))
        }
    }

    /**
     * What the owner types goes through [BaseUrl.normalise] first (which adds
     * http:// and Jarvis's port): the rule still holds, and the address named
     * in the sentence is the one the app would have used.
     */
    @Test
    fun `a typed public tunnel is refused after the port is added`() {
        val base = BaseUrl.normalise("abc123.ngrok-free.app")!!
        assertEquals("http://abc123.ngrok-free.app:4719", base)
        assertEquals(message.replace("{address}", base), OwnNetwork.problem(base))
        assertNotNull(OwnNetwork.problem(BaseUrl.normalise("https://my-jarvis.trycloudflare.com")!!))
    }

    /** CONTROL: the names the pairing screen asks for still pass. */
    @Test
    fun `a meshnet or tailscale name still pairs`() {
        assertNull(OwnNetwork.problem(BaseUrl.normalise("marioirelan11-alps.nord")!!))
        assertNull(OwnNetwork.problem(BaseUrl.normalise("desktop.tail1234.ts.net/")!!))
        assertNull(OwnNetwork.problem(BaseUrl.normalise("[fd7a:115c:a1e0::1]")!!))
    }

    /**
     * A request with a refused address fails with the sentence itself
     * (JarvisApi.noAddress), and the notice shows it word for word - not
     * "not paired", which would be untrue.
     */
    @Test
    fun `the notice shows the sentence as it is`() {
        val said = OwnNetwork.problem("https://abc123.ngrok-free.app")!!
        val shown = PlainErrors.forApiError(ApiError.Unreachable(said))
        assertEquals(said, shown.text)
    }

    /** A password written into an address is never repeated back. */
    @Test
    fun `a password in the address is not echoed`() {
        val said = OwnNetwork.problem("http://me:hunter2@evil.com:4719")!!
        assertFalse(said, "hunter2" in said)
        assertTrue(said, said.startsWith("Jarvis's address is not on your own networks"))
    }
}
