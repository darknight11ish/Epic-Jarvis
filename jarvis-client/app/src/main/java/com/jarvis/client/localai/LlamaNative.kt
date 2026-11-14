package com.jarvis.client.localai

/**
 * The JNI bridge to `libjarvis_llama.so` - the exact contract the native
 * lane codes to (`D:\jarvis-scratch\ANDROID-LOCAL-ENGINE-2026-11-13\PLAN.md`,
 * "JNI contract (exact, both lanes code to this)").
 *
 * ## Nothing here loads the library, and that is the point
 *
 * These are `external` declarations: on a desktop JVM they have no
 * implementation at all, and touching one without the library throws
 * `UnsatisfiedLinkError`. That is why there is **no** `init` block, no
 * `System.loadLibrary` call and no static initialiser in this file. The
 * library is loaded lazily inside [LlamaEngine.create] - the one place that
 * needs it - so the 3,600-odd JVM unit tests, which run on a Windows or CI
 * machine with no ARM library, never load it and never fail because of it.
 *
 * A future edit that moves the library load into an `init {}` here would
 * break every one of those tests and, worse, would make the app try to load a
 * native library merely by opening a class. The test `LocalAiShipsOffTest`
 * pins both halves of that rule.
 *
 * ## The C++ symbols
 *
 * Kotlin compiles an `object`'s members as instance methods on the singleton,
 * so the JNI names are the ones the native lane was given:
 *
 * ```
 * Java_com_jarvis_client_localai_LlamaNative_nativeCreate
 * Java_com_jarvis_client_localai_LlamaNative_nativeLoad
 * Java_com_jarvis_client_localai_LlamaNative_nativeGenerate
 * Java_com_jarvis_client_localai_LlamaNative_nativeUnload
 * Java_com_jarvis_client_localai_LlamaNative_nativeDestroy
 * Java_com_jarvis_client_localai_LlamaNative_nativeLastError
 * Java_com_jarvis_client_localai_LlamaNative_nativeVersion
 * Java_com_jarvis_client_localai_LlamaNative_nativeStats
 * ```
 *
 * The library name is `jarvis_llama` ([LlamaEngine.LIBRARY]).
 */
object LlamaNative {

    /** A fresh engine handle, or `0` when the engine could not be created. */
    external fun nativeCreate(): Long

    /**
     * Loads [modelPath] with [nThreads] CPU threads and a context of [nCtx]
     * tokens. Returns `0` on success, non-zero on failure; the reason is
     * [nativeLastError].
     */
    external fun nativeLoad(handle: Long, modelPath: String, nThreads: Int, nCtx: Int): Int

    /**
     * Generates from [prompt], up to [maxTokens] new tokens at [temperature],
     * handing each piece of text to [sink]. Returns `0` on success. The native
     * side must stop at the next token boundary when [TokenSink.stopped]
     * answers true - that is how the 180-second cap and an owner's stop reach
     * a blocking C++ loop.
     */
    external fun nativeGenerate(
        handle: Long,
        prompt: String,
        maxTokens: Int,
        temperature: Float,
        sink: TokenSink,
    ): Int

    /** Frees the model but keeps the handle usable for another load. */
    external fun nativeUnload(handle: Long)

    /** Frees the model and the handle. The handle must not be used afterwards. */
    external fun nativeDestroy(handle: Long)

    /** The last failure's description, or an empty string when there is none. */
    external fun nativeLastError(handle: Long): String

    /** The native build's version string, for About and bug reports. */
    external fun nativeVersion(): String

    /**
     * `[promptTokens, generatedTokens, generateMillis]` for the last
     * generation on [handle], or an empty array when no generation has run.
     * Those three numbers are what the screen turns into "tokens per second";
     * no timing is guessed on the Kotlin side.
     */
    external fun nativeStats(handle: Long): LongArray
}

/**
 * Where generated text arrives, one piece at a time.
 *
 * The native side looks this interface up by name and calls
 * `emit(String)` for each piece and `stopped()` before each further token.
 * Both methods are called from the C++ generation thread, never the UI
 * thread, so an implementation must hand its work to the right place and
 * must not block.
 */
interface TokenSink {

    /** One piece of generated text. May be a partial word, a space or "". */
    fun emit(piece: String)

    /**
     * True once generation must stop: the 180-second cap, or a later manual
     * stop. A blocking native loop polls this at every token, which is the
     * only point at which it can be interrupted safely.
     */
    fun stopped(): Boolean
}
