package com.jarvis.client.localai

/**
 * The real engine: a thin, honest wrapper around [LlamaNative].
 *
 * ## The library is loaded once, lazily, and only here
 *
 * The library load for `jarvis_llama` runs inside [create] and nowhere else.
 * Not in a constructor, not in a companion `init`, not in [LlamaNative]. That
 * is what lets this app's JVM tests run on a machine with no ARM native
 * library, and what lets the app start with the engine switched off without
 * touching a `.so` that may not even be in the build yet.
 *
 * [loadLibrary] is injectable so a JVM test can prove that timing: construct
 * an engine, assert the loader has not run, call [create], and assert it ran
 * once - without needing the real library to exist.
 *
 * ## Failure is a sentence, never a crash
 *
 * Every JNI call is wrapped. A missing library, a `0` handle, a non-zero
 * return code and an empty stats array all become an [EngineResult.Failed] or
 * [GenerationResult.Failed] carrying words a beginner can act on. Nothing is
 * thrown past this class, because an exception thrown into Compose on the
 * owner's phone is a crash screen, not an explanation.
 *
 * CPU only for E1: [LoadPlan.threads] comes from [DeviceTiers.safeThreads],
 * and the native lane builds one CPU backend. GPU/Vulkan is a later slice and
 * deliberately absent here.
 */
class LlamaEngine(
    private val loadLibrary: () -> Unit = { System.loadLibrary(LIBRARY) },
) : LocalEngine {

    private var handle: Long = 0L
    private var loaded: Boolean = false
    private var lastStats: EngineStats? = null

    override var version: String = ""
        private set

    /** True once a native handle exists. Visible for tests, not for the UI. */
    internal fun hasHandle(): Boolean = handle != 0L

    override fun create(): EngineResult {
        if (handle != 0L) return EngineResult.Ok
        return try {
            loadLibrary()
            val made = LlamaNative.nativeCreate()
            if (made == 0L) {
                EngineResult.Failed(NO_ENGINE_WORDS)
            } else {
                handle = made
                version = runCatching { LlamaNative.nativeVersion() }.getOrDefault("").orEmpty()
                EngineResult.Ok
            }
        } catch (missing: UnsatisfiedLinkError) {
            // The normal state on a JVM test machine and on a build made
            // before the native lane's library is integrated. It is not an
            // error the owner caused, and the words say so.
            EngineResult.Failed(NO_LIBRARY_WORDS)
        } catch (failure: Throwable) {
            EngineResult.Failed(couldNotStart(failure))
        }
    }

    override fun load(modelPath: String, plan: LoadPlan): EngineResult {
        val engine = handle
        if (engine == 0L) return EngineResult.Failed(NOT_STARTED_WORDS)
        if (modelPath.isBlank()) return EngineResult.Failed(NO_FILE_WORDS)
        return try {
            val code = LlamaNative.nativeLoad(
                engine,
                modelPath,
                plan.threads.coerceAtLeast(1),
                plan.contextTokens.coerceAtLeast(MIN_CONTEXT_TOKENS),
            )
            if (code == 0) {
                loaded = true
                lastStats = null
                EngineResult.Ok
            } else {
                loaded = false
                EngineResult.Failed(lastError(engine) ?: LOAD_FAILED_WORDS)
            }
        } catch (failure: Throwable) {
            loaded = false
            EngineResult.Failed(loadFailed(failure))
        }
    }

    override fun generate(
        prompt: String,
        maxTokens: Int,
        temperature: Float,
        onToken: (String) -> Unit,
        stopped: () -> Boolean,
    ): GenerationResult {
        val engine = handle
        if (engine == 0L) return GenerationResult.NotReady(NOT_STARTED_WORDS)
        if (!loaded) return GenerationResult.NotReady(NO_MODEL_WORDS)

        val text = StringBuilder()
        val sink = object : TokenSink {
            override fun emit(piece: String) {
                if (piece.isEmpty()) return
                text.append(piece)
                onToken(piece)
            }

            override fun stopped(): Boolean = stopped()
        }

        lastStats = null
        val code = try {
            LlamaNative.nativeGenerate(
                engine,
                prompt,
                maxTokens.coerceAtLeast(1),
                temperature,
                sink,
            )
        } catch (failure: Throwable) {
            return GenerationResult.Failed(couldNotAnswer(failure))
        }
        if (code != 0) {
            return GenerationResult.Failed(lastError(engine) ?: ANSWER_FAILED_WORDS)
        }

        val stats = runCatching { LlamaNative.nativeStats(engine) }
            .getOrNull()
            ?.takeIf { it.size >= 3 }
            ?.let { EngineStats(it[0], it[1], it[2]) }
        lastStats = stats
        return GenerationResult.Done(
            text = text.toString(),
            stats = stats,
            // The Kotlin side knows only that it asked the native loop to
            // stop; the loop reports how it ended by returning 0 either way.
            // The controller's own flag is the authority for the sentence it
            // shows, so this is a copy of the same answer, not a second guess.
            stoppedAtTimeLimit = stopped(),
        )
    }

    override fun stats(): EngineStats? = lastStats

    override fun unload() {
        val engine = handle
        loaded = false
        lastStats = null
        if (engine == 0L) return
        runCatching { LlamaNative.nativeUnload(engine) }
    }

    override fun destroy() {
        val engine = handle
        handle = 0L
        loaded = false
        lastStats = null
        version = ""
        if (engine == 0L) return
        // Unload before destroy: a native implementation is allowed to need
        // the model gone before the context is freed, and calling both is
        // harmless when the model was already unloaded.
        runCatching { LlamaNative.nativeUnload(engine) }
        runCatching { LlamaNative.nativeDestroy(engine) }
    }

    private fun lastError(engine: Long): String? =
        runCatching { LlamaNative.nativeLastError(engine) }
            .getOrNull()
            ?.trim()
            ?.takeIf { it.isNotEmpty() }

    private fun couldNotStart(failure: Throwable): String =
        if (failure is UnsatisfiedLinkError) NO_LIBRARY_WORDS else NO_ENGINE_WORDS

    private fun loadFailed(failure: Throwable): String =
        if (failure is UnsatisfiedLinkError) NO_LIBRARY_WORDS else LOAD_FAILED_WORDS

    private fun couldNotAnswer(failure: Throwable): String =
        if (failure is UnsatisfiedLinkError) NO_LIBRARY_WORDS else ANSWER_FAILED_WORDS

    companion object {

        /** The native library's name, without the platform's `lib`/`.so` parts. */
        const val LIBRARY = "jarvis_llama"

        /** The native lane's smallest accepted context; below this a model is useless. */
        const val MIN_CONTEXT_TOKENS = 128

        const val NO_LIBRARY_WORDS =
            "This build of Jarvis does not have the on-device model engine yet. " +
                "Nothing was loaded and nothing left this phone."

        const val NO_ENGINE_WORDS =
            "The on-device model engine could not start on this phone. " +
                "Nothing was loaded and nothing left this phone."

        const val NOT_STARTED_WORDS =
            "The on-device engine is not started yet. Load a model first."

        const val NO_MODEL_WORDS = "No model is loaded on this phone yet. Load one first."

        const val NO_FILE_WORDS = "That model has no file on this phone."

        const val LOAD_FAILED_WORDS =
            "The model could not be loaded. It may be damaged, or too big for this phone's memory."

        const val ANSWER_FAILED_WORDS =
            "The model could not answer. Nothing left this phone."
    }
}
