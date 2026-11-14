package com.jarvis.client.localai

/**
 * What the on-device engine is doing.
 *
 * The engine is a separate, local session: it never replaces the Jarvis chat
 * that uses the PC, and it has no network path at all. These states are the
 * only vocabulary the screen uses, so "ready" can never be shown while a
 * model is still loading and "off" can never be shown while one is loaded.
 */
enum class EngineState {
    /** The switch is off, or nothing has been started. No native handle exists. */
    OFF,

    /**
     * The native library or engine could not be created. The screen shows the
     * reason in plain words; the switch stays where the owner put it.
     */
    UNAVAILABLE,

    /** An engine handle exists and no model is loaded. */
    IDLE,

    /** A model file is being loaded. */
    LOADING,

    /** A model is loaded and can answer. */
    READY,

    /** The model is answering right now. */
    GENERATING,

    /** Something went wrong; [LocalAiState.notice] says what in plain words. */
    FAILED,
}

/** Whether a step worked, and if not, the one sentence a person can read. */
sealed interface EngineResult {

    data object Ok : EngineResult

    data class Failed(val reason: String) : EngineResult
}

/**
 * The three numbers the native side reports for the last generation. The
 * Kotlin side never times a generation itself: a wall-clock figure measured
 * outside the native loop would include prefill, disk reads and the JNI
 * boundary, and would not be "tokens per second" in any honest sense.
 */
data class EngineStats(
    val promptTokens: Long,
    val generatedTokens: Long,
    val generateMillis: Long,
) {

    /**
     * Generated tokens per second, or null when there is nothing to divide.
     * Null is the honest answer for a model that produced no tokens or a
     * native build that reported no timing; the screen then says "not
     * measured" rather than inventing a number.
     */
    val tokensPerSecond: Double?
        get() = if (generatedTokens > 0 && generateMillis > 0) {
            generatedTokens * 1000.0 / generateMillis
        } else {
            null
        }
}

/** How to load a model on this phone, decided by [DeviceTiers]. */
data class LoadPlan(
    val threads: Int,
    val contextTokens: Int,
    val maxTokens: Int,
)

/** What one generation produced. */
sealed interface GenerationResult {

    /**
     * The model finished (or was stopped at the time limit). [text] is
     * everything [TokenSink.emit] delivered, in order.
     */
    data class Done(
        val text: String,
        val stats: EngineStats?,
        val stoppedAtTimeLimit: Boolean,
    ) : GenerationResult

    /** The native call failed; nothing partial is presented as an answer. */
    data class Failed(val reason: String) : GenerationResult

    /** There is no loaded model to ask. */
    data class NotReady(val reason: String) : GenerationResult
}

/**
 * The engine as the rest of the app sees it: create, load, generate, unload.
 *
 * Deliberately blocking. [com.jarvis.client.localai.LocalAiController] calls
 * these on a background dispatcher, and a JVM test can drive them with a
 * deterministic fake ([FakeLocalEngine] in the test sources) without any
 * Android, native library or timing assumptions.
 *
 * The one hard rule this interface carries: `create` is the only method that
 * may load the native library, and no implementation may do work in its
 * constructor. Opening the Local AI screen with the switch off must not touch
 * the library at all.
 */
interface LocalEngine {

    /** The native build's version, or "" until [create] succeeded. */
    val version: String

    /** Loads the library and creates the native engine handle. */
    fun create(): EngineResult

    /** Loads [modelPath] with the threads and context in [plan]. */
    fun load(modelPath: String, plan: LoadPlan): EngineResult

    /**
     * Generates an answer to [prompt]. [onToken] receives every piece as it
     * arrives (from a background thread), [stopped] is polled by the native
     * side before each further token, and [maxTokens] is the reply budget.
     */
    fun generate(
        prompt: String,
        maxTokens: Int,
        temperature: Float,
        onToken: (String) -> Unit,
        stopped: () -> Boolean,
    ): GenerationResult

    /** The last generation's numbers, or null when none has run. */
    fun stats(): EngineStats?

    /** Frees the model, keeping the handle. */
    fun unload()

    /** Frees the model and the handle; the engine cannot be used afterwards. */
    fun destroy()
}
