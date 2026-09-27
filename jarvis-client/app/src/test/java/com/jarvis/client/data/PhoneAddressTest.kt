package com.jarvis.client.data

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.PlainErrors
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Which desktop addresses THIS phone can use (docs/ARCHITECTURE.md §2,
 * "Which addresses the phone can use"): the owner's own networks
 * ([OwnNetwork], the backend's rule) AND a name Android lets this app send
 * plain http:// to (res/xml/network_security_config.xml).
 *
 * Nothing here is a second hand-written table. The addresses are the shared
 * `contract/own-network-cases.json` (tools/gen_own_network_cases.py, from the
 * backend's own code), and what Android allows is read from the real config
 * file with an XML parser - so the app's copy of the list cannot drift from
 * the file the platform enforces.
 */
class PhoneAddressTest {

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

    /** Found by walking up from Gradle's working folder, as SpeechTextTest does. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun children(parent: Element, tag: String): List<Element> {
        val out = mutableListOf<Element>()
        val nodes = parent.childNodes
        for (i in 0 until nodes.length) {
            val n = nodes.item(i)
            if (n is Element && n.tagName == tag) out += n
        }
        return out
    }

    /** The config file, parsed for real (its long comment is skipped, not matched). */
    private val config: Element by lazy {
        DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(repoFile(CONFIG)).documentElement
    }

    /** Its one cleartext block's `<domain>` rows, as (name, includeSubdomains). */
    private val fileRules: List<Pair<String, Boolean>> by lazy {
        val block = children(config, "domain-config").single()
        children(block, "domain").map {
            it.textContent.trim().lowercase() to (it.getAttribute("includeSubdomains") == "true")
        }
    }

    /**
     * Android's own matching (AOSP ApplicationConfig.getConfigForHostname),
     * over the rows read from the FILE - this test's own reading, not
     * [PhoneAddress]'s copy of the list.
     */
    private fun fileAllows(host: String): Boolean {
        var h = host.lowercase()
        if (h.isEmpty() || h.startsWith(".")) return false
        if (h.endsWith(".")) h = h.dropLast(1)
        return fileRules.any { (d, sub) -> h == d || (sub && h.endsWith(".$d")) }
    }

    @Test
    fun `the app's list is the config file's list`() {
        assertEquals("network-security-config", config.tagName)
        val base = children(config, "base-config").single()
        assertEquals("plain http:// must stay refused by default", "false", base.getAttribute("cleartextTrafficPermitted"))
        val blocks = children(config, "domain-config")
        assertEquals("one cleartext block, and only one", 1, blocks.size)
        assertEquals("true", blocks[0].getAttribute("cleartextTrafficPermitted"))
        assertTrue("no nested domain-config", children(blocks[0], "domain-config").isEmpty())
        assertEquals(fileRules, PhoneAddress.CLEARTEXT_DOMAINS)
    }

    @Test
    fun `the manifest uses the file and nothing overrides it`() {
        val manifest = repoFile(MANIFEST).readText()
        assertTrue(manifest.contains("android:networkSecurityConfig=\"@xml/network_security_config\""))
        assertFalse(manifest.contains("usesCleartextTraffic"))
    }

    /** Android's matching, name for name, on both sides of every line. */
    @Test
    fun `matching is the platform's`() {
        val yes = listOf(
            "ts.net", "desk.ts.net", "desktop.tail1234.ts.net", "DESK.TS.NET", "desk.ts.net.",
            "nord", "marioirelan11-alps.nord", "a.b.nord", "localhost", "foo.localhost", "127.0.0.1",
        )
        val no = listOf(
            "", ".", ".nord", "notmyts.net", "ts.net.evil.com", "mynord.com", "127.0.0.10",
            "1.127.0.0.1", "192.168.1.20", "10.0.0.5", "100.64.0.1", "fd7a:115c:a1e0::1", "::1",
            "homeassistant.local", "desk.lan", "nas.home.arpa", "jarvis-pc", "evil.com",
        )
        for (h in yes) {
            assertTrue(h, PhoneAddress.cleartextPermitted(h))
            assertTrue(h, fileAllows(h))
        }
        for (h in no) {
            assertFalse(h, PhoneAddress.cleartextPermitted(h))
            assertFalse(h, fileAllows(h))
        }
    }

    /**
     * Every address in the shared table: off the owner's networks gets
     * [OwnNetwork]'s sentence, unchanged; on them, it is either one Android
     * would carry (https://, or a host the FILE allows) or refused up front
     * in the phone's own sentence - never accepted only to fail every request.
     */
    @Test
    fun `every address is usable or refused in plain words`() {
        var usable = 0
        var refused = 0
        for ((url, own) in rows("origins")) {
            if (!own) {
                assertNotNull(url, PhoneAddress.problem(url))
                assertEquals(url, OwnNetwork.problem(url), PhoneAddress.problem(url))
                continue
            }
            val parsed = url.toHttpUrl()
            if (parsed.isHttps || fileAllows(parsed.host)) {
                assertNull(url, PhoneAddress.problem(url))
                usable++
            } else {
                assertEquals(url, PhoneAddress.message(url), PhoneAddress.problem(url))
                refused++
            }
        }
        assertTrue("the table has no address this phone can use", usable > 0)
        assertTrue("the table has no home-network address", refused > 0)
        for ((url, own) in rows("tricky")) {
            if (!own) assertNotNull("$url was accepted", PhoneAddress.problem(url))
        }
    }

    /** What the owner types, through [BaseUrl.normalise] as the app does. */
    @Test
    fun `mesh names pair, home-network forms are refused with the reason`() {
        for (typed in listOf("marioirelan11-alps.nord", "desktop.tail1234.ts.net/", "localhost")) {
            assertNull(typed, PhoneAddress.problem(BaseUrl.normalise(typed)!!))
        }
        val refused = listOf(
            "192.168.1.20", "10.0.0.5", "172.16.0.1", "homeassistant.local", "desk.lan",
            "nas.home.arpa", "jarvis-pc", "100.64.12.3", "100.101.102.103:4719", "[fd7a:115c:a1e0::1]",
        )
        for (typed in refused) {
            val base = BaseUrl.normalise(typed)!!
            assertNull("$typed is on the owner's own networks", OwnNetwork.problem(base))
            assertEquals(typed, PhoneAddress.message(base), PhoneAddress.problem(base))
        }
        assertEquals(
            "Jarvis's address http://192.168.1.20:4719 is on your own network, but this phone can only " +
                "reach your PC by its Tailscale name (ending in .ts.net) or its NordVPN Meshnet name " +
                "(ending in .nord), not by a number or a home-network name: type the name the " +
                "Tailscale or NordVPN app shows for your PC.",
            PhoneAddress.problem(BaseUrl.normalise("192.168.1.20")!!),
        )
    }

    /** CONTROL: a public address still gets the own-networks sentence, not this one. */
    @Test
    fun `a public tunnel is still refused as off your networks`() {
        val base = BaseUrl.normalise("abc123.ngrok-free.app")!!
        assertEquals(OwnNetwork.problem(base), PhoneAddress.problem(base))
        assertTrue(PhoneAddress.problem(base)!!.contains("is not on your own networks"))
    }

    /** It names only what works, and never repeats a password back. */
    @Test
    fun `the sentence points only at names that work`() {
        assertTrue(PhoneAddress.MESSAGE.contains(".ts.net"))
        assertTrue(PhoneAddress.MESSAGE.contains(".nord"))
        assertFalse(PhoneAddress.MESSAGE.contains("192.168"))
        assertFalse(PhoneAddress.MESSAGE.contains(".local"))
        val said = PhoneAddress.message("http://me:hunter2@192.168.1.20:4719")
        assertFalse(said, "hunter2" in said)
        assertTrue(said, said.startsWith("Jarvis's address is on your own network"))
    }

    /**
     * A request with such an address fails with the sentence itself
     * (JarvisApi.noAddress) - not "The connection to your PC dropped.", which
     * is what OkHttp's refusal used to be shown as.
     */
    @Test
    fun `the notice shows the sentence as it is`() {
        val said = PhoneAddress.problem("http://192.168.1.20:4719")!!
        val shown = PlainErrors.forApiError(ApiError.Unreachable(said))
        assertEquals(said, shown.text)
    }

    private companion object {
        const val CONFIG = "jarvis-client/app/src/main/res/xml/network_security_config.xml"
        const val MANIFEST = "jarvis-client/app/src/main/AndroidManifest.xml"
    }
}
