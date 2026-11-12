package com.jarvis.client

import com.jarvis.client.ai.MobileAgentDispatcher
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MobileAgentDispatcherTest {

    private val dispatcher = MobileAgentDispatcher()

    @Test
    fun takeNoteWithEmptyContentReturnsError() {
        val result = dispatcher.dispatch("take_note", mapOf("title" to "Test", "content" to ""))
        assertFalse(result.ok)
        assertTrue(result.output.contains("cannot be empty"))
    }

    @Test
    fun takeNoteValidQueuesForSync() {
        val result = dispatcher.dispatch("take_note", mapOf("title" to "Grocery", "content" to "Buy milk"))
        assertTrue(result.ok)
        assertTrue(result.queuedForSync)
        assertTrue(result.output.contains("Grocery"))
    }

    @Test
    fun rememberFactValidQueuesForSync() {
        val result = dispatcher.dispatch(
            "remember_fact",
            mapOf("fact" to "Mom's birthday is June 4", "category" to "dates", "sensitive" to "false")
        )
        assertTrue(result.ok)
        assertTrue(result.queuedForSync)
        assertTrue(result.output.contains("offline memory"))
    }

    @Test
    fun rule4GuardsRiskyToolsFromRunningOffline() {
        val riskyTools = listOf("shell_exec", "run_command", "send_email", "delete_file", "git_push")
        for (tool in riskyTools) {
            val result = dispatcher.dispatch(tool, emptyMap())
            assertFalse("Tool $tool must not run offline", result.ok)
            assertTrue("Tool $tool must require desktop approval", result.needsDesktopApproval)
            assertTrue("Output must reference Rule 4", result.output.contains("Rule 4"))
        }
    }

    @Test
    fun unknownToolReturnsClearError() {
        val result = dispatcher.dispatch("unknown_quantum_teleport", emptyMap())
        assertFalse(result.ok)
        assertTrue(result.output.contains("Unknown or unsupported"))
    }
}
