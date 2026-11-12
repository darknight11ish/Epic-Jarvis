package com.jarvis.client

import com.jarvis.client.data.OfflineMemory
import com.jarvis.client.data.OfflineTurn
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.OfflineSync
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineSyncTest {

    private fun obj(json: String): JsonObject = JarvisJson.parseToJsonElement(json).jsonObject

    @Test
    fun endpointPathsMatchFrozenContract() {
        assertEquals("/api/sync/offline-batch", OfflineSync.BATCH_PATH)
        assertEquals("/api/sync/status", OfflineSync.STATUS_PATH)
    }

    @Test
    fun batchSerializesExpectedFields() {
        val turns = listOf(
            OfflineTurn(
                turnId = "turn_123",
                conversationId = "conv_456",
                timestamp = 1700000000000L,
                userQuery = "What is the capital of France?",
                modelResponse = "The capital of France is Paris.",
                modelName = "qwen2.5-1.5b-q4",
                syncStatus = "PENDING"
            )
        )
        val memories = listOf(
            OfflineMemory(
                memoryId = "mem_789",
                timestamp = 1700000001000L,
                factText = "User likes black coffee",
                category = "preference",
                sensitive = false,
                syncStatus = "PENDING"
            )
        )

        val batch = OfflineSync.Batch(
            deviceId = "pixel-9-test",
            turns = turns,
            memories = memories,
            syncTimestamp = 1700000002000L
        )

        val json = obj(batch.toJsonString())
        assertEquals("pixel-9-test", json["device_id"]?.jsonPrimitive?.content)
        assertEquals("1700000002000", json["sync_timestamp"]?.jsonPrimitive?.content)

        val turnsArr = json["turns"] as JsonArray
        assertEquals(1, turnsArr.size)
        val t0 = turnsArr[0] as JsonObject
        assertEquals("turn_123", t0["turn_id"]?.jsonPrimitive?.content)
        assertEquals("conv_456", t0["conversation_id"]?.jsonPrimitive?.content)
        assertEquals("What is the capital of France?", t0["user_query"]?.jsonPrimitive?.content)
        assertEquals("The capital of France is Paris.", t0["model_response"]?.jsonPrimitive?.content)
        assertEquals("qwen2.5-1.5b-q4", t0["model_name"]?.jsonPrimitive?.content)

        val memArr = json["memories"] as JsonArray
        assertEquals(1, memArr.size)
        val m0 = memArr[0] as JsonObject
        assertEquals("mem_789", m0["memory_id"]?.jsonPrimitive?.content)
        assertEquals("User likes black coffee", m0["fact_text"]?.jsonPrimitive?.content)
        assertEquals("preference", m0["category"]?.jsonPrimitive?.content)
        assertEquals("false", m0["sensitive"]?.jsonPrimitive?.content)
    }

    @Test
    fun syncResponseParsesServerPayload() {
        val raw = """
            {
                "ok": true,
                "accepted_turns": ["turn_123"],
                "accepted_memories": ["mem_789"],
                "accepted_tasks": [],
                "server_sync_time": 1700000003000
            }
        """.trimIndent()

        val parsed = OfflineSync.SyncResponse.fromJson(obj(raw))
        assertTrue(parsed.ok)
        assertEquals(listOf("turn_123"), parsed.acceptedTurns)
        assertEquals(listOf("mem_789"), parsed.acceptedMemories)
        assertTrue(parsed.acceptedTasks.isEmpty())
        assertEquals(1700000003000L, parsed.serverSyncTime)
    }
}
