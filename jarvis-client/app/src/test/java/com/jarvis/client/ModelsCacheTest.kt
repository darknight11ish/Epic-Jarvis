package com.jarvis.client

import com.jarvis.client.net.CachedModels
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.ModelEntry
import com.jarvis.client.net.ModelOffload
import com.jarvis.client.net.ModelsInfo
import com.jarvis.client.net.ModelsView
import com.jarvis.client.net.modelsView
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `docs/OFFLINE-MODELS-DESIGN-2026-09-27.md`: Brain -> Model replays the
 * phone's own last successful `GET /api/models` read, clearly marked as
 * old, when a live read fails - never a live disk read (the phone has no
 * access to the PC's disk) and never a browsable catalogue (CLAUDE.md).
 *
 * The store itself ([com.jarvis.client.data.ModelsCacheStore]) needs a real
 * `Context` and so is not covered here, the same way [TokenStore]'s own
 * `SharedPreferences` file is only checked by an instrumentation test
 * (`TokenStoreTest`) rather than a JVM one - this file covers the pure
 * decision logic ([modelsView]) and the JSON shape ([CachedModels]) that
 * sit either side of that store, both of which have no Android dependency.
 */
class ModelsCacheTest {

    private fun sampleInfo(withLiveOnlyFields: Boolean = false) = ModelsInfo(
        currentRef = "qwen3:8b",
        previous = "qwen3:4b",
        entries = listOf(
            ModelEntry(ref = "qwen3:8b", sizeBytes = 5_100_000_000L, family = "qwen3"),
            ModelEntry(ref = "qwen3:4b", sizeBytes = 2_600_000_000L, family = "qwen3"),
        ),
        offload = if (withLiveOnlyFields) ModelOffload(status = "cpu", note = "spilled") else null,
        speed = null,
    )

    // ---------------------------------------------------- a successful read --

    @Test
    fun `a successful read's cacheable subset round-trips through JSON exactly`() {
        val cached = CachedModels.from(sampleInfo(), asOfMs = 1_758_960_000_000L)
        val roundTripped = CachedModels.fromJson(cached.toJson())

        assertEquals(cached, roundTripped)
        assertEquals("qwen3:8b", roundTripped?.currentRef)
        assertEquals("qwen3:4b", roundTripped?.previous)
        assertEquals(1_758_960_000_000L, roundTripped?.asOfMs)
        assertEquals(listOf("qwen3:8b", "qwen3:4b"), roundTripped?.entries?.map { it.ref })
        assertEquals(5_100_000_000L, roundTripped?.entries?.get(0)?.sizeBytes)
        assertEquals("qwen3", roundTripped?.entries?.get(0)?.family)
    }

    // this JSON is what `ModelsCacheStore.save` writes and `.load` reads back -
    // see that class's own doc comment for why the Context-backed half of the
    // round trip is not repeated here.
    @Test
    fun `the cached JSON is exactly what a real backend read would leave on disk`() {
        val json = CachedModels.from(sampleInfo(), asOfMs = 42L).toJson()
        assertEquals("qwen3:8b", (json["current"] as? kotlinx.serialization.json.JsonPrimitive)?.content)
        assertEquals(42L, (json["as_of_ms"] as? kotlinx.serialization.json.JsonPrimitive)?.content?.toLong())
    }

    // -------------------------------------------------- live-only fields -----

    @Test
    fun `offload and speed never survive into the cache, whether or not they were reported live`() {
        val withThem = sampleInfo(withLiveOnlyFields = true)
        assertTrue("the fixture actually has an offload value to lose", withThem.offload != null)

        val cached = CachedModels.from(withThem, asOfMs = 1L)
        // CachedModels structurally has no offload/speed property at all - this
        // is the strongest form of "hidden on the stale path" available
        // without a Compose UI test: it is not merely unset, there is no
        // field for a later reader to read stale by mistake.
        val json = cached.toJson().toString()
        assertFalse("offload leaked into the cached JSON", json.contains("offload"))
        assertFalse("cpu/spilled leaked into the cached JSON", json.contains("cpu") || json.contains("spilled"))
    }

    // ------------------------------------------------------------- decision --

    @Test
    fun `a live success shows Live, never mixing in an old cache`() {
        val info = sampleInfo()
        val staleCache = CachedModels.from(sampleInfo(), asOfMs = 1L).copy(currentRef = "old:model")
        val view = modelsView(live = info, cached = staleCache)
        assertTrue(view is ModelsView.Live)
        assertEquals("qwen3:8b", (view as ModelsView.Live).info.currentRef)
    }

    @Test
    fun `a failed read after an earlier success shows Stale with that success's own timestamp`() {
        val cached = CachedModels.from(sampleInfo(), asOfMs = 1_758_960_000_000L)
        val view = modelsView(live = null, cached = cached)
        assertTrue(view is ModelsView.Stale)
        assertEquals(1_758_960_000_000L, (view as ModelsView.Stale).cached.asOfMs)
        assertEquals("qwen3:8b", view.cached.currentRef)
    }

    @Test
    fun `a failed read with no prior cache shows NeverConnected, not fabricated data`() {
        val view = modelsView(live = null, cached = null)
        assertEquals(ModelsView.NeverConnected, view)
    }

    // ------------------------------------------------------------ robustness -

    @Test
    fun `an unreadable cache document is null, never a guess`() {
        assertNull(CachedModels.fromJson(JarvisJson.parseToJsonElement("{}") as JsonObject))
        assertNull(
            CachedModels.fromJson(
                JarvisJson.parseToJsonElement("""{"current": "qwen3:8b"}""") as JsonObject,
            ),
        )
    }

    @Test
    fun `installed entries missing a ref are dropped, not crashed on`() {
        val json = JarvisJson.parseToJsonElement(
            """{"as_of_ms": 5, "installed": [{"size": 10}, {"ref": "a"}]}""",
        ) as JsonObject
        val cached = CachedModels.fromJson(json)
        assertEquals(listOf("a"), cached?.entries?.map { it.ref })
    }
}
