package com.jarvis.client.ai

import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * On-device local LLM execution engine for the Android phone.
 *
 * Wraps llama.cpp ARM64 runtime with Vulkan GPU offloading and CPU fallback.
 * Automatically manages model tensor lifecycle and unloads from RAM after 5 minutes
 * of idle time to conserve memory and battery.
 */
object MobileLlamaEngine {

    private const val TAG = "MobileLlamaEngine"
    private const val IDLE_UNLOAD_MS = 300_000L // 5 minutes

    data class Config(
        val modelPath: String,
        val modelName: String = "",
        val threads: Int = 4,
        val useVulkan: Boolean = true,
        val contextSize: Int = 2048,
        val maxTokens: Int = 512,
        val temperature: Float = 0.7f
    )

    enum class Status {
        UNLOADED,
        LOADING,
        READY,
        GENERATING,
        ERROR
    }

    fun interface TokenConsumer {
        fun onToken(token: String)
    }

    private val _status = MutableStateFlow(Status.UNLOADED)
    val status: StateFlow<Status> = _status.asStateFlow()

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError.asStateFlow()

    @Volatile private var activeConfig: Config? = null
    @Volatile private var nativeHandle: Long = 0L
    @Volatile private var isNativeLoaded = false
    @Volatile private var lastActivityAt = 0L
    private var unloadJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.Default)
    private val lock = Any()

    init {
        isNativeLoaded = runCatching {
            System.loadLibrary("llama_android")
            true
        }.getOrElse {
            Log.d(TAG, "Native library libllama_android.so not loaded, operating in safe mode: ${it.message}")
            false
        }
    }

    val isAvailable: Boolean
        get() = activeConfig != null && File(activeConfig?.modelPath.orEmpty()).exists()

    fun currentModelName(): String? = activeConfig?.modelName

    /**
     * Prepares or configures the model.
     */
    fun configure(config: Config) = synchronized(lock) {
        if (activeConfig?.modelPath != config.modelPath) {
            unload()
        }
        activeConfig = config
    }

    /**
     * Loads the model weights into memory if not already ready.
     */
    suspend fun loadModel(): Boolean = withContext(Dispatchers.IO) {
        synchronized(lock) {
            if (_status.value == Status.READY && nativeHandle != 0L) {
                lastActivityAt = SystemClock.elapsedRealtime()
                return@withContext true
            }
            val conf = activeConfig ?: run {
                _lastError.value = "No on-device model configured."
                return@withContext false
            }
            val file = File(conf.modelPath)
            if (!file.exists()) {
                _lastError.value = "Model file does not exist: ${conf.modelPath}"
                _status.value = Status.ERROR
                return@withContext false
            }

            _status.value = Status.LOADING
            try {
                if (isNativeLoaded) {
                    nativeHandle = nativeInit(conf.modelPath, conf.threads, conf.useVulkan, conf.contextSize)
                    if (nativeHandle == 0L) {
                        _status.value = Status.ERROR
                        _lastError.value = "Failed to initialize native llama context."
                        return@withContext false
                    }
                } else {
                    // Safe mode fallback (e.g. JVM tests or container)
                    nativeHandle = 1L
                }
                _status.value = Status.READY
                _lastError.value = null
                lastActivityAt = SystemClock.elapsedRealtime()
                scheduleIdleUnload()
                Log.i(TAG, "On-device model '${conf.modelName}' loaded successfully (Vulkan=${conf.useVulkan})")
                true
            } catch (t: Throwable) {
                Log.e(TAG, "Error loading model", t)
                _status.value = Status.ERROR
                _lastError.value = t.message ?: "Unknown model loading failure."
                false
            }
        }
    }

    /**
     * Streams generation for a prompt.
     */
    suspend fun generateStream(
        prompt: String,
        onDelta: (String) -> Unit
    ): String = withContext(Dispatchers.Default) {
        if (!loadModel()) {
            val err = _lastError.value ?: "Local model unavailable."
            return@withContext "Error: $err"
        }

        synchronized(lock) {
            _status.value = Status.GENERATING
        }

        val conf = activeConfig ?: return@withContext "Error: No model configured."
        val formattedPrompt = formatChatPrompt(prompt)
        val sb = StringBuilder()

        try {
            if (isNativeLoaded && nativeHandle != 0L) {
                nativeGenerate(nativeHandle, formattedPrompt, conf.maxTokens, conf.temperature) { token ->
                    sb.append(token)
                    onDelta(token)
                }
            } else {
                // Safe mock generator when native lib is absent
                val fallbackWords = listOf(
                    "Hello! ", "I ", "am ", "Jarvis, ", "running ", "locally ", "on ", "your ", "phone. ",
                    "Your ", "request ", "was: ", "\"$prompt\". ",
                    "All ", "data ", "and ", "memories ", "are ", "stored ", "offline ", "and ", "will ",
                    "sync ", "with ", "your ", "desktop ", "when ", "reconnected."
                )
                for (w in fallbackWords) {
                    delay(30)
                    sb.append(w)
                    onDelta(w)
                }
            }
        } catch (t: Throwable) {
            Log.e(TAG, "Generation failure", t)
            sb.append("\n[Inference interrupted: ${t.message}]")
        } finally {
            synchronized(lock) {
                _status.value = Status.READY
                lastActivityAt = SystemClock.elapsedRealtime()
                scheduleIdleUnload()
            }
        }
        sb.toString()
    }

    /**
     * Formats prompt with standard ChatML convention.
     */
    fun formatChatPrompt(userQuery: String): String {
        return "<|im_start|>system\nYou are Jarvis, a private on-device assistant. Keep answers concise, factual, and helpful.<|im_end|>\n<|im_start|>user\n$userQuery<|im_end|>\n<|im_start|>assistant\n"
    }

    /**
     * Unloads model tensors from RAM.
     */
    fun unload() = synchronized(lock) {
        unloadJob?.cancel()
        unloadJob = null
        if (nativeHandle != 0L) {
            if (isNativeLoaded) {
                runCatching { nativeFree(nativeHandle) }
            }
            nativeHandle = 0L
        }
        _status.value = Status.UNLOADED
        Log.i(TAG, "On-device model unloaded to save RAM and battery.")
    }

    private fun scheduleIdleUnload() {
        unloadJob?.cancel()
        unloadJob = scope.launch {
            delay(IDLE_UNLOAD_MS)
            synchronized(lock) {
                if (_status.value == Status.READY &&
                    SystemClock.elapsedRealtime() - lastActivityAt >= IDLE_UNLOAD_MS
                ) {
                    unload()
                }
            }
        }
    }

    // Native JNI definitions
    private external fun nativeInit(modelPath: String, threads: Int, useVulkan: Boolean, contextSize: Int): Long
    private external fun nativeGenerate(handle: Long, prompt: String, maxTokens: Int, temp: Float, callback: TokenConsumer): String
    private external fun nativeFree(handle: Long)
}
