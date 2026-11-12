package com.jarvis.client.data

import android.content.Context
import android.net.Uri
import androidx.core.content.edit
import com.jarvis.client.net.JarvisJson
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream

/**
 * Metadata for a local GGUF model stored on the Android companion phone.
 */
@Serializable
data class LocalModel(
    val name: String,
    val filePath: String,
    val sizeBytes: Long,
    val isVulkanCapable: Boolean = true,
    val quantization: String = "Q4_K_M",
    val parameterCount: String = "1.5B"
) {
    fun toJson(): JsonObject = buildJsonObject {
        put("name", JsonPrimitive(name))
        put("file_path", JsonPrimitive(filePath))
        put("size_bytes", JsonPrimitive(sizeBytes))
        put("is_vulkan_capable", JsonPrimitive(isVulkanCapable))
        put("quantization", JsonPrimitive(quantization))
        put("parameter_count", JsonPrimitive(parameterCount))
    }

    companion object {
        fun fromJson(obj: JsonObject): LocalModel? {
            val name = obj["name"]?.jsonPrimitive?.contentOrNull ?: return null
            val path = obj["file_path"]?.jsonPrimitive?.contentOrNull ?: return null
            val size = obj["size_bytes"]?.jsonPrimitive?.longOrNull ?: 0L
            val vk = obj["is_vulkan_capable"]?.jsonPrimitive?.booleanOrNull ?: true
            val quant = obj["quantization"]?.jsonPrimitive?.contentOrNull ?: "Q4_K_M"
            val params = obj["parameter_count"]?.jsonPrimitive?.contentOrNull ?: "1.5B"
            return LocalModel(name, path, size, vk, quant, params)
        }
    }
}

/**
 * Manages on-device AI model files in private app storage.
 * Supports GGUF magic validation, active model selection, and storage cleanup.
 */
class ModelStore(private val context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val lock = Any()

    val modelsDir: File
        get() {
            val dir = File(context.applicationContext.filesDir, "models")
            if (!dir.exists()) dir.mkdirs()
            return dir
        }

    fun listModels(): List<LocalModel> = synchronized(lock) {
        val raw = prefs.getString(KEY_MODELS, null) ?: return emptyList()
        runCatching {
            val arr = JarvisJson.parseToJsonElement(raw).jsonArray
            arr.mapNotNull { if (it is JsonObject) LocalModel.fromJson(it) else null }
        }.getOrDefault(emptyList())
    }

    fun activeModel(): LocalModel? = synchronized(lock) {
        val activePath = prefs.getString(KEY_ACTIVE_MODEL_PATH, null) ?: return null
        listModels().find { it.filePath == activePath }
    }

    fun setActiveModel(model: LocalModel?) = synchronized(lock) {
        prefs.edit {
            if (model != null) {
                putString(KEY_ACTIVE_MODEL_PATH, model.filePath)
            } else {
                remove(KEY_ACTIVE_MODEL_PATH)
            }
        }
    }

    fun registerModel(model: LocalModel) = synchronized(lock) {
        val current = listModels().filterNot { it.filePath == model.filePath }.toMutableList()
        current.add(model)
        val arr = JsonArray(current.map { it.toJson() })
        prefs.edit {
            putString(KEY_MODELS, arr.toString())
            if (activeModel() == null) {
                putString(KEY_ACTIVE_MODEL_PATH, model.filePath)
            }
        }
    }

    fun removeModel(filePath: String) = synchronized(lock) {
        val current = listModels().filterNot { it.filePath == filePath }
        val arr = JsonArray(current.map { it.toJson() })
        prefs.edit {
            putString(KEY_MODELS, arr.toString())
            if (prefs.getString(KEY_ACTIVE_MODEL_PATH, null) == filePath) {
                remove(KEY_ACTIVE_MODEL_PATH)
            }
        }
        val file = File(filePath)
        if (file.exists() && file.startsWith(modelsDir)) {
            runCatching { file.delete() }
        }
    }

    /**
     * Verifies that the file contains the 4-byte GGUF magic ('G', 'G', 'U', 'F').
     */
    fun isValidGguf(file: File): Boolean {
        if (!file.exists() || file.length() < 4) return false
        return runCatching {
            FileInputStream(file).use { stream ->
                val header = ByteArray(4)
                val read = stream.read(header)
                read == 4 && header[0] == 'G'.code.toByte() &&
                    header[1] == 'G'.code.toByte() &&
                    header[2] == 'U'.code.toByte() &&
                    header[3] == 'F'.code.toByte()
            }
        }.getOrDefault(false)
    }

    /**
     * Imports a GGUF file from a content URI into private app storage.
     */
    fun importFromUri(uri: Uri, displayName: String): LocalModel? {
        val destFile = File(modelsDir, displayName)
        return runCatching {
            context.contentResolver.openInputStream(uri)?.use { input ->
                FileOutputStream(destFile).use { output ->
                    input.copyTo(output)
                }
            }
            if (isValidGguf(destFile)) {
                val model = LocalModel(
                    name = displayName.removeSuffix(".gguf"),
                    filePath = destFile.absolutePath,
                    sizeBytes = destFile.length()
                )
                registerModel(model)
                model
            } else {
                destFile.delete()
                null
            }
        }.getOrNull()
    }

    companion object {
        const val PREFS_NAME = "jarvis_model_store"
        private const val KEY_MODELS = "registered_models"
        private const val KEY_ACTIVE_MODEL_PATH = "active_model_path"
        private const val KEY_USE_VULKAN = "use_vulkan"
        private const val KEY_THREADS = "cpu_threads"
        private const val KEY_CONTEXT_SIZE = "context_size"
        private const val KEY_AUTO_SYNC = "auto_sync_on_reconnect"
        private const val KEY_CAPTURE_MEMORIES = "capture_offline_memories"
        private const val KEY_BATTERY_GUARD = "battery_saver_guard"
    }

    private val _useVulkan = MutableStateFlow(prefs.getBoolean(KEY_USE_VULKAN, true))
    val useVulkan: StateFlow<Boolean> = _useVulkan.asStateFlow()

    private val _threads = MutableStateFlow(prefs.getInt(KEY_THREADS, 4))
    val threads: StateFlow<Int> = _threads.asStateFlow()

    private val _contextSize = MutableStateFlow(prefs.getInt(KEY_CONTEXT_SIZE, 2048))
    val contextSize: StateFlow<Int> = _contextSize.asStateFlow()

    private val _autoSyncOnReconnect = MutableStateFlow(prefs.getBoolean(KEY_AUTO_SYNC, true))
    val autoSyncOnReconnect: StateFlow<Boolean> = _autoSyncOnReconnect.asStateFlow()

    private val _captureOfflineMemories = MutableStateFlow(prefs.getBoolean(KEY_CAPTURE_MEMORIES, true))
    val captureOfflineMemories: StateFlow<Boolean> = _captureOfflineMemories.asStateFlow()

    private val _batteryGuard = MutableStateFlow(prefs.getBoolean(KEY_BATTERY_GUARD, true))
    val batteryGuard: StateFlow<Boolean> = _batteryGuard.asStateFlow()

    fun setUseVulkan(enabled: Boolean) = synchronized(lock) {
        prefs.edit { putBoolean(KEY_USE_VULKAN, enabled) }
        _useVulkan.value = enabled
        applyCurrentConfig()
    }

    fun setThreads(count: Int) = synchronized(lock) {
        val clamped = count.coerceIn(1, 8)
        prefs.edit { putInt(KEY_THREADS, clamped) }
        _threads.value = clamped
        applyCurrentConfig()
    }

    fun setContextSize(tokens: Int) = synchronized(lock) {
        val clamped = if (tokens in listOf(1024, 2048, 4096)) tokens else 2048
        prefs.edit { putInt(KEY_CONTEXT_SIZE, clamped) }
        _contextSize.value = clamped
        applyCurrentConfig()
    }

    fun setAutoSyncOnReconnect(enabled: Boolean) = synchronized(lock) {
        prefs.edit { putBoolean(KEY_AUTO_SYNC, enabled) }
        _autoSyncOnReconnect.value = enabled
    }

    fun setCaptureOfflineMemories(enabled: Boolean) = synchronized(lock) {
        prefs.edit { putBoolean(KEY_CAPTURE_MEMORIES, enabled) }
        _captureOfflineMemories.value = enabled
    }

    fun setBatteryGuard(enabled: Boolean) = synchronized(lock) {
        prefs.edit { putBoolean(KEY_BATTERY_GUARD, enabled) }
        _batteryGuard.value = enabled
    }

    fun applyCurrentConfig() {
        val active = activeModel() ?: return
        com.jarvis.client.ai.MobileLlamaEngine.configure(
            com.jarvis.client.ai.MobileLlamaEngine.Config(
                modelPath = active.filePath,
                modelName = active.name,
                threads = _threads.value,
                useVulkan = _useVulkan.value && active.isVulkanCapable,
                contextSize = _contextSize.value
            )
        )
    }
}
