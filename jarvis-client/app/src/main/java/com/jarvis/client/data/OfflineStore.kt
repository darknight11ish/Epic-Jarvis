package com.jarvis.client.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull

@Serializable
data class OfflineTurn(
    val turnId: String,
    val conversationId: String,
    val timestamp: Long,
    val userQuery: String,
    val modelResponse: String,
    val modelName: String,
    val syncStatus: String = "PENDING"
) {
    fun toJson(): JsonObject = kotlinx.serialization.json.buildJsonObject {
        put("turn_id", kotlinx.serialization.json.JsonPrimitive(turnId))
        put("conversation_id", kotlinx.serialization.json.JsonPrimitive(conversationId))
        put("timestamp", kotlinx.serialization.json.JsonPrimitive(timestamp))
        put("user_query", kotlinx.serialization.json.JsonPrimitive(userQuery))
        put("model_response", kotlinx.serialization.json.JsonPrimitive(modelResponse))
        put("model_name", kotlinx.serialization.json.JsonPrimitive(modelName))
        put("sync_status", kotlinx.serialization.json.JsonPrimitive(syncStatus))
    }

    companion object {
        fun fromJson(obj: JsonObject): OfflineTurn? {
            val tid = obj["turn_id"]?.jsonPrimitive?.contentOrNull ?: return null
            val cid = obj["conversation_id"]?.jsonPrimitive?.contentOrNull ?: "default"
            val ts = obj["timestamp"]?.jsonPrimitive?.longOrNull ?: System.currentTimeMillis()
            val uq = obj["user_query"]?.jsonPrimitive?.contentOrNull ?: ""
            val mr = obj["model_response"]?.jsonPrimitive?.contentOrNull ?: ""
            val mn = obj["model_name"]?.jsonPrimitive?.contentOrNull ?: "ondevice:local"
            val ss = obj["sync_status"]?.jsonPrimitive?.contentOrNull ?: "PENDING"
            return OfflineTurn(tid, cid, ts, uq, mr, mn, ss)
        }
    }
}

@Serializable
data class OfflineMemory(
    val memoryId: String,
    val timestamp: Long,
    val factText: String,
    val category: String = "general",
    val sensitive: Boolean = false,
    val syncStatus: String = "PENDING"
) {
    fun toJson(): JsonObject = kotlinx.serialization.json.buildJsonObject {
        put("memory_id", kotlinx.serialization.json.JsonPrimitive(memoryId))
        put("timestamp", kotlinx.serialization.json.JsonPrimitive(timestamp))
        put("fact_text", kotlinx.serialization.json.JsonPrimitive(factText))
        put("category", kotlinx.serialization.json.JsonPrimitive(category))
        put("sensitive", kotlinx.serialization.json.JsonPrimitive(sensitive))
        put("sync_status", kotlinx.serialization.json.JsonPrimitive(syncStatus))
    }

    companion object {
        fun fromJson(obj: JsonObject): OfflineMemory? {
            val mid = obj["memory_id"]?.jsonPrimitive?.contentOrNull ?: return null
            val ts = obj["timestamp"]?.jsonPrimitive?.longOrNull ?: System.currentTimeMillis()
            val ft = obj["fact_text"]?.jsonPrimitive?.contentOrNull ?: return null
            val cat = obj["category"]?.jsonPrimitive?.contentOrNull ?: "general"
            val sens = obj["sensitive"]?.jsonPrimitive?.booleanOrNull ?: false
            val ss = obj["sync_status"]?.jsonPrimitive?.contentOrNull ?: "PENDING"
            return OfflineMemory(mid, ts, ft, cat, sens, ss)
        }
    }
}

/**
 * Manages offline turns and memories captured when disconnected from the PC.
 * Persisted in private SharedPreferences for simplicity, safety and zero-dependency footprint.
 */
class OfflineStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val lock = Any()

    fun recordTurn(turn: OfflineTurn) = synchronized(lock) {
        val list = loadTurns().filterNot { it.turnId == turn.turnId }.toMutableList()
        list.add(turn)
        saveTurns(list)
    }

    fun recordMemory(memory: OfflineMemory) = synchronized(lock) {
        val list = loadMemories().filterNot { it.memoryId == memory.memoryId }.toMutableList()
        list.add(memory)
        saveMemories(list)
    }

    fun pendingTurns(): List<OfflineTurn> = synchronized(lock) {
        loadTurns().filter { it.syncStatus == "PENDING" }
    }

    fun pendingMemories(): List<OfflineMemory> = synchronized(lock) {
        loadMemories().filter { it.syncStatus == "PENDING" }
    }

    fun markTurnsSynced(acceptedIds: Collection<String>) = synchronized(lock) {
        if (acceptedIds.isEmpty()) return
        val idSet = if (acceptedIds is Set<String>) acceptedIds else acceptedIds.toSet()
        val list = loadTurns().map { turn ->
            if (turn.turnId in idSet) turn.copy(syncStatus = "SYNCED") else turn
        }
        saveTurns(list)
    }

    fun markMemoriesSynced(acceptedIds: Collection<String>) = synchronized(lock) {
        if (acceptedIds.isEmpty()) return
        val idSet = if (acceptedIds is Set<String>) acceptedIds else acceptedIds.toSet()
        val list = loadMemories().map { mem ->
            if (mem.memoryId in idSet) mem.copy(syncStatus = "SYNCED") else mem
        }
        saveMemories(list)
    }

    fun clearSynced() = synchronized(lock) {
        saveTurns(loadTurns().filter { it.syncStatus != "SYNCED" })
        saveMemories(loadMemories().filter { it.syncStatus != "SYNCED" })
    }

    private fun loadTurns(): List<OfflineTurn> {
        val raw = prefs.getString(KEY_TURNS, null) ?: return emptyList()
        return runCatching {
            val arr = JarvisJson.parseToJsonElement(raw).jsonArray
            arr.mapNotNull { if (it is JsonObject) OfflineTurn.fromJson(it) else null }
        }.getOrDefault(emptyList())
    }

    private fun saveTurns(turns: List<OfflineTurn>) {
        val arr = kotlinx.serialization.json.JsonArray(turns.map { it.toJson() })
        prefs.edit { putString(KEY_TURNS, arr.toString()) }
    }

    private fun loadMemories(): List<OfflineMemory> {
        val raw = prefs.getString(KEY_MEMORIES, null) ?: return emptyList()
        return runCatching {
            val arr = JarvisJson.parseToJsonElement(raw).jsonArray
            arr.mapNotNull { if (it is JsonObject) OfflineMemory.fromJson(it) else null }
        }.getOrDefault(emptyList())
    }

    private fun saveMemories(memories: List<OfflineMemory>) {
        val arr = kotlinx.serialization.json.JsonArray(memories.map { it.toJson() })
        prefs.edit { putString(KEY_MEMORIES, arr.toString()) }
    }

    companion object {
        const val PREFS_NAME = "jarvis_offline_store"
        private const val KEY_TURNS = "offline_turns"
        private const val KEY_MEMORIES = "offline_memories"
    }
}
