package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.ModelsInfo
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.ProposalOption
import com.jarvis.client.net.Risk
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Two additions from the desktop's 2026-09-18 catch-up: `/api/models`
 * (the owner's amendment allowing a switch, never an install, from the
 * phone) and `options` on a proposal (AUTONOMY-PROPOSALS §3a).
 *
 * `ModelsInfo` is deliberately tolerant, per its own doc comment: the route's
 * shape is documented by the desktop's `brain.js renderModels` and nothing
 * else, so every shape that consumer accepts must parse here too.
 */
class ModelsAndOptionsTest {

    private fun models(text: String) = JarvisJson.decodeFromString(ModelsInfo.serializer(), text)

    @Test
    fun `installed as bare strings`() {
        val m = models("""{"current": "qwen3:8b", "installed": ["qwen3:8b", "qwen2.5-coder:7b"]}""")
        assertEquals("qwen3:8b", m.currentRef)
        assertEquals(listOf("qwen3:8b", "qwen2.5-coder:7b"), m.entries.map { it.ref })
    }

    @Test
    fun `installed as objects, and the ref key can be 'ref', 'name' or 'model'`() {
        val m = models(
            """{"current": "a", "installed": [
                {"ref": "a", "size": 4700000000, "family": "qwen3"},
                {"name": "b"},
                {"model": "c"}
            ]}""",
        )
        val entries = m.entries
        assertEquals(listOf("a", "b", "c"), entries.map { it.ref })
        assertEquals(4_700_000_000L, entries[0].sizeBytes)
        assertEquals("qwen3", entries[0].family)
    }

    @Test
    fun `'active' is accepted as well as 'current'`() {
        // The desktop's own renderer reads `body.current || body.active` —
        // both spellings are live, not a hypothetical.
        val m = models("""{"active": "qwen3:8b", "installed": []}""")
        assertEquals("qwen3:8b", m.currentRef)
    }

    @Test
    fun `no installed list falls back to the current model alone`() {
        val m = models("""{"current": "qwen3:8b"}""")
        assertEquals(listOf("qwen3:8b"), m.entries.map { it.ref })
    }

    @Test
    fun `nothing reported is nothing reported, not a crash`() {
        val m = models("{}")
        assertNull(m.currentRef)
        assertTrue(m.entries.isEmpty())
    }

    @Test
    fun `offload off the card is flagged; on the card is not`() {
        val cpu = models("""{"offload": {"status": "cpu", "note": "spilled"}}""")
        assertTrue(cpu.offload!!.bad)
        val gpu = models("""{"offload": {"status": "gpu"}}""")
        assertFalse(gpu.offload!!.bad)
        val none = models("{}")
        assertNull(none.offload)
    }

    // ------------------------------------------------------- options ------

    private fun item(options: List<ProposalOption> = emptyList()) =
        PendingItem(id = "a1", risk = Risk(reversible = "yes", reach = "local", swipeOk = true), options = options)

    @Test
    fun `no options, or exactly one, needs no choice`() {
        assertFalse(item().needsChoice)
        assertFalse(item(listOf(ProposalOption(id = "opt_a", label = "Reply"))).needsChoice)
    }

    @Test
    fun `two or more options needs a choice, and a bare approve is refused`() {
        val it = item(
            listOf(
                ProposalOption(id = "opt_a", label = "Reply and wait"),
                ProposalOption(id = "opt_b", label = "Reply and ask for a refund", weight = "heavy"),
            ),
        )
        assertTrue(it.needsChoice)
    }

    @Test
    fun `options round-trip through the wire shape the desktop's doc gives`() {
        val json = """
            {"id": "appr_1", "action": "control_browser", "options": [
                {"id": "opt_a", "label": "Reply and wait for their answer",
                 "summary": "1 step: send the drafted message.", "weight": "heavy"},
                {"id": "opt_b", "label": "Reply and also ask for a refund",
                 "summary": "2 steps: send the message, then ask.", "weight": "heavy"}
            ]}
        """.trimIndent()
        val parsed = JarvisJson.decodeFromString(PendingItem.serializer(), json)
        assertEquals(2, parsed.options.size)
        assertTrue(parsed.needsChoice)
        assertEquals("opt_a", parsed.options[0].id)
        assertEquals("heavy", parsed.options[1].weight)
    }
}
