package com.jarvis.client.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull

/**
 * Client for advertising and managing the phone's on-device model as a collaborative
 * edge compute lane with the desktop PC.
 */
object MobileLaneClient {

    const val REGISTER_PATH = "/api/models/mobile-lane/register"
    const val STATUS_PATH = "/api/models/mobile-lane/status"
    const val TRANSFER_AVAILABLE_PATH = "/api/models/transfer/available"

    @Serializable
    data class TransferModel(
        val id: String,
        val name: String,
        val filename: String,
        val sizeBytes: Long,
        val sizeHuman: String,
        val recommended: Boolean,
        val description: String
    ) {
        companion object {
            fun fromJson(obj: JsonObject): TransferModel? {
                val id = obj["id"]?.jsonPrimitive?.contentOrNull ?: return null
                val name = obj["name"]?.jsonPrimitive?.contentOrNull ?: id
                val fn = obj["filename"]?.jsonPrimitive?.contentOrNull ?: "$id.gguf"
                val size = obj["size_bytes"]?.jsonPrimitive?.longOrNull ?: 0L
                val human = obj["size_human"]?.jsonPrimitive?.contentOrNull ?: ""
                val rec = obj["recommended"]?.jsonPrimitive?.booleanOrNull ?: false
                val desc = obj["description"]?.jsonPrimitive?.contentOrNull ?: ""
                return TransferModel(id, name, fn, size, human, rec, desc)
            }
        }
    }

    suspend fun registerMobileLane(
        api: JarvisApi,
        deviceId: String,
        modelName: String,
        useVulkan: Boolean = true,
        contextSize: Int = 2048
    ): ApiResult<JsonObject> {
        val body = buildJsonObject {
            put("device_id", JsonPrimitive(deviceId))
            put("model_name", JsonPrimitive(modelName))
            put("vulkan", JsonPrimitive(useVulkan))
            put("context_size", JsonPrimitive(contextSize))
        }.toString()
        return api.registerMobileLane(body)
    }

    suspend fun fetchTransferModels(api: JarvisApi): ApiResult<List<TransferModel>> {
        return api.transferModelsAvailable().map { obj ->
            val arr = obj["models"] as? JsonArray ?: return@map emptyList()
            arr.mapNotNull { if (it is JsonObject) TransferModel.fromJson(it) else null }
        }
    }
}
