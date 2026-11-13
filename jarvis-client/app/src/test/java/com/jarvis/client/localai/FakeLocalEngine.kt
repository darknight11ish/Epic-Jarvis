package com.jarvis.client.localai

/**
 * A deterministic engine for JVM tests: no library, no threads of its own, no
 * timing guesses.
 *
 * It hands out [pieces] one at a time, asks [stopped] before each, and reports
 * [stats] for the generation. That is exactly the seam the real [LlamaEngine]
 * exposes, so `LocalAiControllerTest` can prove the state machine, the
 * five-minute idle unload and the 180-second cap without a phone.
 */
class FakeLocalEngine(
    private val failCreate: String? = null,
    private val failLoad: String? = null,
    private val pieces: List<String> = listOf("Hello", " from", " the", " phone."),
    private val stats: EngineStats? = EngineStats(promptTokens = 5, generatedTokens = 4, generateMillis = 500),
    private val emitDelayMillis: Long = 0L,
    private val loadDelayMillis: Long = 0L,
) : LocalEngine {

    var createCalls: Int = 0
        private set
    var loadCalls: Int = 0
        private set
    var generateCalls: Int = 0
        private set
    var unloadCalls: Int = 0
        private set
    var destroyCalls: Int = 0
        private set

    var lastPath: String? = null
        private set
    var lastPlan: LoadPlan? = null
        private set
    var lastPrompt: String? = null
        private set

    var modelLoaded: Boolean = false
        private set

    private var lastStats: EngineStats? = null

    override var version: String = "fake-engine-1"
        private set

    override fun create(): EngineResult {
        createCalls++
        return if (failCreate != null) EngineResult.Failed(failCreate) else EngineResult.Ok
    }

    override fun load(modelPath: String, plan: LoadPlan): EngineResult {
        loadCalls++
        lastPath = modelPath
        lastPlan = plan
        if (loadDelayMillis > 0L) Thread.sleep(loadDelayMillis)
        if (failLoad != null) {
            modelLoaded = false
            return EngineResult.Failed(failLoad)
        }
        modelLoaded = true
        return EngineResult.Ok
    }

    override fun generate(
        prompt: String,
        maxTokens: Int,
        temperature: Float,
        onToken: (String) -> Unit,
        stopped: () -> Boolean,
    ): GenerationResult {
        generateCalls++
        lastPrompt = prompt
        if (!modelLoaded) return GenerationResult.NotReady(LlamaEngine.NO_MODEL_WORDS)

        val text = StringBuilder()
        for (piece in pieces) {
            if (stopped()) {
                return GenerationResult.Done(text.toString(), stats, stoppedAtTimeLimit = true)
            }
            text.append(piece)
            onToken(piece)
            if (emitDelayMillis > 0L) Thread.sleep(emitDelayMillis)
        }
        lastStats = stats
        return GenerationResult.Done(
            text = text.toString(),
            stats = stats,
            stoppedAtTimeLimit = stopped(),
        )
    }

    override fun stats(): EngineStats? = lastStats

    override fun unload() {
        unloadCalls++
        modelLoaded = false
        lastStats = null
    }

    override fun destroy() {
        destroyCalls++
        modelLoaded = false
        lastStats = null
    }
}
