package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.WebSearch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
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
 * Mind's "Web search", read from what the PC REALLY answers.
 *
 * `contract/web-search-cases.json` is the real `GET /api/search` answer
 * (jarvis_search.view()) and the POST answers, written by
 * tools/gen_web_search_cases.py - byte for byte the file the desktop builds
 * against. Nothing here is a shape typed to suit this client.
 */
class WebSearchTest {

    private val doc: JsonObject = run {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/web-search-cases.json")) {
            "contract/web-search-cases.json is missing - run tools/gen_web_search_cases.py"
        }.readText()
        JarvisJson.parseToJsonElement(text) as JsonObject
    }
    private val cases = doc["cases"]!!.jsonObject

    private fun view(case: String): WebSearch.View =
        requireNotNull(WebSearch.parse(cases[case]!!.jsonObject)) { "$case did not parse" }

    private fun post(case: String): ApiResult<JsonObject> {
        val c = cases[case]!!.jsonObject
        return WebSearch.classifyPost(c["status"]!!.jsonPrimitive.int, c["body"]!!.jsonObject)
    }

    @Test
    fun `the four lines, the labels and Whoogle's reason are the PC's own words`() {
        val why = doc["why"]!!.jsonObject
        val labels = doc["labels"]!!.jsonObject
        assertEquals(doc["providers"]!!.jsonArray.map { it.jsonPrimitive.content }, WebSearch.PROVIDERS)
        for (p in WebSearch.PROVIDERS) {
            assertEquals(p, why[p]!!.jsonPrimitive.content, WebSearch.WHY[p])
            assertEquals(p, labels[p]!!.jsonPrimitive.content, WebSearch.LABEL[p])
        }
        val whoogle = doc["left_out"]!!.jsonArray[0].jsonObject
        assertEquals(whoogle["why"]!!.jsonPrimitive.content, WebSearch.WHOOGLE_WHY)
        assertEquals(1, doc["left_out"]!!.jsonArray.size)
        assertTrue(WebSearch.WHY["brave"]!!.contains("payment card that is charged"))
    }

    @Test
    fun `every real view is read, the four in the PC's order`() {
        val gets = cases.keys.filter { !it.startsWith("post_") && !it.startsWith("test_") }
        assertTrue(gets.size >= 5)
        for (name in gets) {
            assertEquals(name, WebSearch.PROVIDERS, view(name).providers.map { it.id })
        }
        val d = view("default")
        assertEquals("searxng", d.provider)
        assertEquals("http://127.0.0.1:8888", d.address)
        assertFalse(d.askEveryTime)
        assertEquals("In use. Ready.", WebSearch.providerLine(d.providers[0], d.provider))
        assertEquals(listOf("Whoogle"), d.leftOut.map { it.label })
        assertNull(view("damaged").provider)
        assertTrue(view("damaged").why.contains("damaged"))
        assertTrue(view("exa_no_key_ask_every_time").askEveryTime)
        val tavily = view("tavily_key_saved").providers.first { it.id == "tavily" }
        assertEquals(WebSearch.KEY_SAVED, WebSearch.keyLine(tavily))
        val exa = view("exa_no_key_ask_every_time").providers.first { it.id == "exa" }
        assertEquals(WebSearch.KEY_NONE, WebSearch.keyLine(exa))
        assertTrue(WebSearch.providerLine(exa, "exa").contains("No Exa key"))
        val brave = view("brave_no_key")
        assertEquals("brave", brave.provider)
        assertEquals(WebSearch.KEY_NONE, WebSearch.keyLine(brave.providers.first { it.id == "brave" }))
    }

    @Test
    fun `one change per request, and nothing but the four`() {
        assertEquals("{\"provider\":\"duckduckgo\"}", WebSearch.providerBody("duckduckgo"))
        assertNull(WebSearch.providerBody("whoogle"))
        assertEquals("{\"provider\":\"brave\"}", WebSearch.providerBody("brave"))
        assertEquals("{\"searxng_url\":\"http://nas.local:8888\"}", WebSearch.addressBody(" http://nas.local:8888 "))
        assertEquals("{\"searxng_url\":\"a\\\"b\"}", WebSearch.addressBody("a\"b"))
        assertNull(WebSearch.addressBody("x".repeat(201)))
        assertEquals("{\"ask_every_time\":false}", WebSearch.askBody(false))
    }

    @Test
    fun `the PC's answers become its own sentences`() {
        assertTrue(WebSearch.replyLine(post("post_provider")).startsWith("Web search now uses DuckDuckGo."))
        assertTrue(WebSearch.replyLine(post("post_bad_address")).startsWith("That SearXNG address cannot be used"))
        assertTrue(WebSearch.replyLine(post("post_ask_off")).startsWith("Waiting for your approval."))
        val (ok, line) = WebSearch.testLine(post("test_not_running"))
        assertFalse(ok)
        assertTrue(line.contains("SearXNG isn't running on this PC"))
        assertTrue(line.contains("Switch web search to DuckDuckGo?"))
        assertTrue(WebSearch.testLine(post("test_works")).first)
        val (braveOk, braveLine) = WebSearch.testLine(post("test_brave_key_missing"))
        assertFalse(braveOk)
        assertTrue(braveLine.contains("No Brave Search key"))
        assertTrue(WebSearch.testLine(post("test_key_missing")).second.contains("desktop app's Settings"))
        assertEquals(WebSearch.MISSING, WebSearch.replyLine(ApiResult.Failed(ApiError.NotFound)))
        assertTrue(WebSearch.missing(ApiError.NotFound))
        assertNotNull(WebSearch.parse(cases["default"]!!.jsonObject))
        assertNull(WebSearch.parse(JsonObject(emptyMap())))
    }

    @Test
    fun `the phone never asks for a key`() {
        assertTrue(WebSearch.KEY_ENTRY.contains("The phone never asks for one"))
    }
}
