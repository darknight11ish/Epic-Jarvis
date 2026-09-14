package com.jarvis.assistant

import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.network.InboundEvent
import com.jarvis.assistant.network.JarvisJson
import com.jarvis.assistant.network.OutboundMessage
import com.jarvis.assistant.network.QuickNoteMessage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QuickNoteSerializationTest {

    @Test
    fun `quick_note serializes to the documented wire frame`() {
        val json = JarvisJson.encodeToString(
            OutboundMessage.serializer(),
            QuickNoteMessage(
                target = "logseq",
                mode = "append",
                content = "Captured text...",
                timestampMs = 1_726_200_000_000,
            ),
        )
        assertTrue(json, json.contains("\"type\":\"quick_note\""))
        assertTrue(json, json.contains("\"target\":\"logseq\""))
        assertTrue(json, json.contains("\"mode\":\"append\""))
        assertTrue(json, json.contains("\"content\":\"Captured text...\""))
        assertTrue(json, json.contains("\"timestamp_ms\":1726200000000"))
    }

    @Test
    fun `quick_note round-trips`() {
        val original = QuickNoteMessage("joplin", "create", "Body\nwith newline", 42L)
        val encoded = JarvisJson.encodeToString(OutboundMessage.serializer(), original)
        val decoded = JarvisJson.decodeFromString(OutboundMessage.serializer(), encoded)
        assertEquals(original, decoded)
    }

    @Test
    fun `note approval_request deserializes with its payload`() {
        val frame = """
            {"type":"approval_request","id":"a1","title":"Edit note",
             "action":"edit_joplin_note",
             "note":{"target":"joplin","title":"Ideas","before":"one\ntwo","after":"one\nthree"}}
        """.trimIndent()

        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
        assertTrue(event is ApprovalRequestEvent)
        event as ApprovalRequestEvent

        assertTrue(event.isNoteEdit)
        assertEquals("joplin", event.note?.target)
        assertTrue(event.note!!.isJoplin)
        assertEquals("Ideas", event.note?.title)
    }

    @Test
    fun `logseq page action counts as a note edit without a payload`() {
        val frame = """{"type":"approval_request","id":"a2","action":"edit_logseq_page"}"""
        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
            as ApprovalRequestEvent
        assertTrue(event.isNoteEdit)
        assertNull(event.note)
    }

    @Test
    fun `a shell approval is not treated as a note edit`() {
        val frame = """{"type":"approval_request","id":"a3","action":"shell"}"""
        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
            as ApprovalRequestEvent
        assertTrue(!event.isNoteEdit)
    }
}
