package com.jarvis.client.net

import android.os.Build
import android.util.Log
import com.jarvis.client.data.OfflineMemory
import com.jarvis.client.data.OfflineStore
import com.jarvis.client.data.OfflineTurn
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull

/**
 * Two-way offline sync client for the Android companion.
 *
 * When the phone operates offline (disconnected from desktop Jarvis), conversations
 * and memories are persisted in [OfflineStore]. When the event stream reconnects,
 * [performSync] pushes pending items to `POST /api/sync/offline-batch` and marks
 * accepted items as SYNCED.
 */
object OfflineSync {

    private const val TAG = "OfflineSync"
    const val BATCH_PATH = "/api/sync/offline-batch"
    const val STATUS_PATH = "/api/sync/status"

    data class Batch(
        val deviceId: String,
        val turns: List<OfflineTurn>,
        val memories: List<OfflineMemory>,
        val syncTimestamp: Long = System.currentTimeMillis()
    ) {
        fun toJsonString(): String = buildJsonObject {
            put("device_id", JsonPrimitive(deviceId))
            put("sync_timestamp", JsonPrimitive(syncTimestamp))
            put("turns", JsonArray(turns.map { it.toJson() }))
            put("memories", JsonArray(memories.map { it.toJson() }))
            put("tasks", JsonArray(emptyList()))
        }.toString()
    }

    data class SyncResponse(
        val ok: Boolean,
        val acceptedTurns: List<String>,
        val acceptedMemories: List<String>,
        val acceptedTasks: List<String>,
        val serverSyncTime: Long
    ) {
        companion object {
            fun fromJson(obj: JsonObject): SyncResponse {
                val ok = (obj["ok"] as? JsonPrimitive)?.booleanOrNull ?: false
                val turns = (obj["accepted_turns"] as? JsonArray)?.mapNotNull {
                    (it as? JsonPrimitive)?.contentOrNull
                } ?: emptyList()
                val memories = (obj["accepted_memories"] as? JsonArray)?.mapNotNull {
                    (it as? JsonPrimitive)?.contentOrNull
                } ?: emptyList()
                val tasks = (obj["accepted_tasks"] as? JsonArray)?.mapNotNull {
                    (it as? JsonPrimitive)?.contentOrNull
                } ?: emptyList()
                val time = (obj["server_sync_time"] as? JsonPrimitive)?.longOrNull ?: 0L
                return SyncResponse(ok, turns, memories, tasks, time)
            }
        }
    }

    sealed interface SyncResult {
        data class Success(val response: SyncResponse) : SyncResult
        data object Empty : SyncResult
        data class Failed(val error: ApiError) : SyncResult
    }

    fun defaultDeviceId(): String {
        val model = runCatching { Build.MODEL }.getOrNull()?.trim()
        return if (!model.isNullOrEmpty()) model.lowercase().replace(" ", "-") else "android-companion"
    }

    suspend fun performSync(
        api: JarvisApi,
        store: OfflineStore,
        deviceId: String = defaultDeviceId()
    ): SyncResult {
        val pendingTurns = store.pendingTurns()
        val pendingMemories = store.pendingMemories()
        if (pendingTurns.isEmpty() && pendingMemories.isEmpty()) {
            return SyncResult.Empty
        }

        val batch = Batch(
            deviceId = deviceId,
            turns = pendingTurns,
            memories = pendingMemories
        )

        return when (val res = api.syncOfflineBatch(batch.toJsonString())) {
            is ApiResult.Ok -> {
                val response = SyncResponse.fromJson(res.value)
                if (response.acceptedTurns.isNotEmpty()) {
                    store.markTurnsSynced(response.acceptedTurns)
                }
                if (response.acceptedMemories.isNotEmpty()) {
                    store.markMemoriesSynced(response.acceptedMemories)
                }
                Log.i(TAG, "Offline sync complete: ${response.acceptedTurns.size} turns, ${response.acceptedMemories.size} memories synced")
                SyncResult.Success(response)
            }
            is ApiResult.Failed -> {
                Log.w(TAG, "Offline sync failed: ${res.error}")
                SyncResult.Failed(res.error)
            }
        }
    }
}
