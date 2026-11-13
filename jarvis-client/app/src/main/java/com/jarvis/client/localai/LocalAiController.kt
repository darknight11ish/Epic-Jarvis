package com.jarvis.client.localai

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.InputStream
import java.util.concurrent.atomic.AtomicBoolean

/** One model as the screen shows it: the file, what it is, and whether it fits. */
data class LocalAiModel(
    val name: String,
    val file: java.io.File,
    val bytes: Long,
    val info: GgufInfo?,
    val quant: String?,
    val quantFromName: Boolean,
    val verdict: DeviceTiers.ModelVerdict,
)

/** One line of the on-device chat. */
data class ChatLine(
    val from: From,
    val text: String,
    /** The native side's measured speed for this reply, or null when it reported none. */
    val tokensPerSecond: Double? = null,
    /** True when the 180-second cap ended this reply. */
    val stoppedAtTimeLimit: Boolean = false,
) {
    enum class From { YOU, PHONE }
}

/** Everything the Local AI screen draws, in one immutable value. */
data class LocalAiState(
    val switchOn: Boolean = LocalAiSettings.DEFAULT_ENABLED,
    val engine: EngineState = EngineState.OFF,
    val models: List<LocalAiModel> = emptyList(),
    val loadedModel: String? = null,
    /** A copy, a load or a reply is running: the screen disables what would collide. */
    val busy: Boolean = false,
    val importName: String? = null,
    val importCopied: Long = 0L,
    val importTotal: Long? = null,
    val notice: String? = null,
    val noticeIsProblem: Boolean = false,
    val lines: List<ChatLine> = emptyList(),
    /** The answer as it arrives, before it becomes a [ChatLine]. */
    val streamingText: String = "",
    val generating: Boolean = false,
)

/**
 * The Local AI screen's state machine: switch, models, engine, chat.
 *
 * ## What it refuses to do
 *
 * - It never creates an engine while the switch is off, and turning the
 *   switch on does **not** create one either. The first `Load` tap does. That
 *   is the difference between "the owner turned a screen on" and "this phone
 *   started a native engine".
 * - It never loads a model the tier verdict refused. The words are shown
 *   instead, so a tap cannot push the phone into an out-of-memory kill.
 * - It never loads or downloads anything by itself: there is no download
 *   path at all, and `load` is only ever called from a button.
 * - It never lets a generation run past the policy's hard cap: a watchdog
 *   sets the stop flag at [LocalEnginePolicy.hardCapMillis], and the native
 *   loop polls it at every token.
 *
 * ## Why every heavy call goes through a dispatcher
 *
 * `create`, `load`, `generate`, the model list and a file copy are all
 * blocking. They run on [dispatcher] (IO in the app, unconfined in tests), so
 * the UI thread only ever updates state.
 *
 * The controller is plain Kotlin: no Android, no Compose. `LocalAiScreen` owns
 * one, calls [refreshModels] on open, [tick] about twice a second, and
 * [close] when it leaves. `LocalAiControllerTest` drives the same methods with
 * a fake engine and a hand-moved clock.
 */
class LocalAiController(
    private val engineFactory: () -> LocalEngine,
    private val store: ModelStore,
    val tier: DeviceTiers.Tier,
    private val settings: LocalAiSettings,
    private val policy: LocalEnginePolicy = LocalEnginePolicy(),
    private val dispatcher: CoroutineDispatcher = Dispatchers.IO,
    private val temperature: Float = DEFAULT_TEMPERATURE,
) {

    private val _state = MutableStateFlow(LocalAiState(switchOn = settings.enabled))

    val state: StateFlow<LocalAiState> = _state.asStateFlow()

    private var engine: LocalEngine? = null

    private var stopRequested = AtomicBoolean(false)

    /** A close that arrived while a reply was still running. */
    private var closeDeferred = false

    @Volatile
    private var closed = false

    /** The reply budget for this phone: the tier's recommended number of new tokens. */
    val replyBudget: Int
        get() = minOf(tier.maxTokens, tier.maxSafeTokens).coerceAtLeast(1)

    /**
     * Turns the screen's own switch on or off. OFF destroys the engine and
     * the loaded model immediately; ON only shows the controls, because no
     * model is loaded until the owner asks for one.
     */
    suspend fun setSwitch(on: Boolean) {
        if (closed) return
        if (!on && (_state.value.generating || _state.value.busy)) {
            // A load, a copy or a reply is still running. Turning the switch
            // off would destroy the handle underneath it; the screen disables
            // the toggle in this state too.
            notice(WAIT_FOR_ANSWER_WORDS, problem = true)
            return
        }
        settings.setEnabled(on)
        if (on) {
            _state.update {
                it.copy(
                    switchOn = true,
                    notice = null,
                    noticeIsProblem = false,
                    engine = if (it.engine == EngineState.UNAVAILABLE) EngineState.UNAVAILABLE else EngineState.OFF,
                )
            }
            refreshModels()
            return
        }

        val current = engine
        engine = null
        withContext(dispatcher) { current?.destroy() }
        policy.reset()
        _state.update {
            it.copy(
                switchOn = false,
                engine = EngineState.OFF,
                loadedModel = null,
                busy = false,
                importName = null,
                importCopied = 0L,
                importTotal = null,
                notice = null,
                noticeIsProblem = false,
                lines = emptyList(),
                streamingText = "",
                generating = false,
            )
        }
    }

    /** Re-reads the folder: names, sizes, headers and verdicts. */
    suspend fun refreshModels() {
        val models = withContext(dispatcher) {
            store.list().map { it.toLocalAiModel(tier) }
        }
        _state.update { it.copy(models = models) }
    }

    /**
     * Copies a picked document into the models folder. [open] is called here,
     * once, so the caller can keep all Android `Uri` handling in the screen;
     * a null stream is a plain refusal, not a crash.
     */
    suspend fun importModel(
        displayName: String,
        declaredBytes: Long?,
        open: () -> InputStream?,
    ): Boolean {
        if (closed) return false
        if (!_state.value.switchOn) {
            notice(LocalAiWords.TURN_ON_FIRST, problem = true)
            return false
        }
        val input = runCatching { open() }.getOrNull()
        if (input == null) {
            notice(COULD_NOT_OPEN_WORDS, problem = true)
            return false
        }

        _state.update {
            it.copy(
                busy = true,
                notice = null,
                noticeIsProblem = false,
                importName = displayName,
                importCopied = 0L,
                importTotal = declaredBytes,
            )
        }
        val result = withContext(dispatcher) {
            store.import(displayName, declaredBytes, input) { copied, total ->
                _state.update { state ->
                    state.copy(importCopied = copied, importTotal = total ?: state.importTotal)
                }
            }
        }

        if (closed || closeDeferred) {
            shutdownEngine()
            return false
        }

        return when (result) {
            is ModelStore.ImportResult.Ok -> {
                refreshModels()
                _state.update {
                    it.copy(
                        busy = false,
                        importName = null,
                        importCopied = 0L,
                        importTotal = null,
                        notice = LocalAiWords.imported(result.model.name),
                        noticeIsProblem = false,
                    )
                }
                true
            }

            is ModelStore.ImportResult.Refused -> {
                _state.update {
                    it.copy(
                        busy = false,
                        importName = null,
                        importCopied = 0L,
                        importTotal = null,
                        notice = result.reason,
                        noticeIsProblem = true,
                    )
                }
                false
            }
        }
    }

    /** Deletes one model from this phone, and says so. */
    suspend fun deleteModel(name: String) {
        if (closed) return
        if (_state.value.busy || _state.value.generating) return
        if (_state.value.loadedModel == name) unload()
        val deleted = withContext(dispatcher) { store.delete(name) }
        refreshModels()
        _state.update {
            it.copy(
                notice = if (deleted) {
                    "$name was deleted from this phone."
                } else {
                    "That model could not be deleted. It may have been removed already."
                },
                noticeIsProblem = !deleted,
            )
        }
    }

    /**
     * Loads [name]. Refuses a model the tier said is too big, and refuses
     * anything when the switch is off. This is the only method that creates
     * the engine.
     */
    suspend fun load(name: String) {
        if (closed) return
        val current = _state.value
        if (!current.switchOn) {
            notice(LocalAiWords.TURN_ON_FIRST, problem = true)
            return
        }
        if (current.busy || current.generating) return

        val model = current.models.firstOrNull { it.name == name }
            ?: withContext(dispatcher) { store.find(name)?.toLocalAiModel(tier) }
        if (model == null) {
            notice(NOT_HERE_WORDS, problem = true)
            return
        }
        if (model.verdict is DeviceTiers.ModelVerdict.TooBig) {
            notice(model.verdict.words + " " + LocalAiWords.TOO_BIG_ACTION, problem = true)
            return
        }

        val contextTokens = (model.verdict as? DeviceTiers.ModelVerdict.Fits)
            ?.contextTokens
            ?: tier.contextTokens

        _state.update {
            it.copy(
                busy = true,
                engine = EngineState.LOADING,
                loadedModel = null,
                notice = null,
                noticeIsProblem = false,
            )
        }

        val result = withContext(dispatcher) {
            when (val made = ensureEngine()) {
                is EngineResult.Failed -> made
                EngineResult.Ok -> engine!!.load(
                    modelPath = model.file.absolutePath,
                    plan = LoadPlan(
                        threads = tier.safeThreads,
                        contextTokens = contextTokens,
                        maxTokens = replyBudget,
                    ),
                )
            }
        }

        // The screen may have been left, or the switch flipped by a path that
        // got past the guard, while the native load was still running. Settle
        // it to OFF rather than claiming a READY engine that was destroyed.
        if (closed || closeDeferred) {
            shutdownEngine()
            return
        }

        when (result) {
            EngineResult.Ok -> {
                policy.reset()
                policy.requested()
                _state.update {
                    it.copy(
                        busy = false,
                        engine = EngineState.READY,
                        loadedModel = name,
                        notice = null,
                        noticeIsProblem = false,
                    )
                }
            }

            is EngineResult.Failed -> _state.update {
                it.copy(
                    busy = false,
                    // A missing library is not a failed model: the screen says
                    // the engine is unavailable and keeps the switch where the
                    // owner put it.
                    engine = if (it.engine == EngineState.UNAVAILABLE) {
                        EngineState.UNAVAILABLE
                    } else {
                        EngineState.FAILED
                    },
                    loadedModel = null,
                    notice = result.reason,
                    noticeIsProblem = true,
                )
            }
        }
    }

    /** Frees the loaded model but keeps the engine handle for another load. */
    suspend fun unload() {
        if (closed) return
        val current = engine
        withContext(dispatcher) { current?.unload() }
        if (closed) return
        policy.reset()
        _state.update {
            it.copy(
                engine = if (current == null) EngineState.OFF else EngineState.IDLE,
                loadedModel = null,
                generating = false,
                streamingText = "",
                busy = false,
                notice = null,
                noticeIsProblem = false,
            )
        }
    }

    /**
     * Sends one prompt to the loaded model and appends the answer.
     *
     * The whole generation is bounded by the policy: a watchdog flips the stop
     * flag at the hard cap, which the native loop sees at its next token. The
     * measured speed comes from the native stats, never from a Kotlin timer.
     */
    suspend fun send(text: String) {
        val prompt = text.trim()
        if (closed || prompt.isEmpty()) return
        val current = _state.value
        if (!current.switchOn) {
            notice(LocalAiWords.TURN_ON_FIRST, problem = true)
            return
        }
        val engine = engine
        if (engine == null || current.engine != EngineState.READY || current.loadedModel == null) {
            notice(LocalAiWords.LOAD_FIRST, problem = true)
            return
        }
        if (current.generating || current.busy) return

        // The whole prompt, built BEFORE the new line is added: the JNI call
        // takes one string, and the model itself has no memory between calls.
        val promptForModel = LocalAiPrompt.build(
            modelName = current.loadedModel,
            history = current.lines.map { line ->
                LocalAiPrompt.Turn(
                    role = if (line.from == ChatLine.From.PHONE) {
                        LocalAiPrompt.Role.ASSISTANT
                    } else {
                        LocalAiPrompt.Role.USER
                    },
                    text = line.text,
                )
            },
            message = prompt,
        )

        stopRequested = AtomicBoolean(false)
        policy.generationStarted()
        _state.update {
            it.copy(
                lines = it.lines + ChatLine(ChatLine.From.YOU, prompt),
                streamingText = "",
                generating = true,
                engine = EngineState.GENERATING,
                notice = null,
                noticeIsProblem = false,
            )
        }

        val reply = StringBuilder()
        val result = try {
            coroutineScope {
                val watchdog = launch {
                    delay(policy.hardCapMillis)
                    stopRequested.set(true)
                }
                try {
                    withContext(dispatcher) {
                        engine.generate(
                            prompt = promptForModel,
                            maxTokens = replyBudget,
                            temperature = temperature,
                            onToken = { piece ->
                                reply.append(piece)
                                _state.update { state -> state.copy(streamingText = reply.toString()) }
                            },
                            stopped = { stopRequested.get() },
                        )
                    }
                } finally {
                    watchdog.cancel()
                }
            }
        } catch (cancelled: CancellationException) {
            if (closed || closeDeferred) shutdownEngine()
            throw cancelled
        } catch (failure: Throwable) {
            GenerationResult.Failed(LlamaEngine.ANSWER_FAILED_WORDS)
        }

        policy.generationFinished()
        when (result) {
            is GenerationResult.Done -> {
                val stopped = result.stoppedAtTimeLimit || stopRequested.get()
                val answer = result.text.ifEmpty { reply.toString() }
                if (answer.isEmpty()) {
                    _state.update {
                        it.copy(
                            engine = EngineState.READY,
                            generating = false,
                            streamingText = "",
                            notice = if (stopped) LocalAiWords.HARD_CAP_NOTE else EMPTY_ANSWER_WORDS,
                            noticeIsProblem = true,
                        )
                    }
                } else {
                    _state.update {
                        it.copy(
                            engine = EngineState.READY,
                            generating = false,
                            streamingText = "",
                            lines = it.lines + ChatLine(
                                from = ChatLine.From.PHONE,
                                text = answer,
                                tokensPerSecond = result.stats?.tokensPerSecond,
                                stoppedAtTimeLimit = stopped,
                            ),
                            notice = if (stopped) LocalAiWords.HARD_CAP_NOTE else null,
                            noticeIsProblem = stopped,
                        )
                    }
                }
            }

            is GenerationResult.Failed -> _state.update {
                it.copy(
                    engine = EngineState.READY,
                    generating = false,
                    streamingText = "",
                    notice = result.reason,
                    noticeIsProblem = true,
                )
            }

            is GenerationResult.NotReady -> _state.update {
                it.copy(
                    engine = EngineState.IDLE,
                    generating = false,
                    streamingText = "",
                    loadedModel = null,
                    notice = result.reason,
                    noticeIsProblem = true,
                )
            }
        }

        // The screen may have been left while the native loop was finishing.
        // Destroying the handle from close() at that moment would be a
        // use-after-free in C++; so close() only set the stop flag and this is
        // where the handle finally goes.
        if (closed || closeDeferred) shutdownEngine()
    }

    /**
     * The screen's twice-a-second heartbeat: applies the five-minute idle
     * unload and makes sure a running generation has been asked to stop at the
     * cap.
     */
    suspend fun tick() {
        if (closed) return
        when (policy.decide()) {
            LocalEnginePolicy.Decision.StopAtHardCap -> stopRequested.set(true)

            LocalEnginePolicy.Decision.UnloadAfterIdle -> {
                val current = _state.value
                if (current.engine != EngineState.READY || current.generating) return
                unload()
                _state.update { it.copy(notice = LocalAiWords.IDLE_UNLOAD_NOTE, noticeIsProblem = false) }
            }

            LocalEnginePolicy.Decision.Nothing -> Unit
        }
    }

    /** Drops the current notice, so the screen's line does not stick forever. */
    fun dismissNotice() {
        _state.update { it.copy(notice = null, noticeIsProblem = false) }
    }

    /**
     * The owner is typing. This is not an engine request and it never creates
     * or loads anything; it only restarts the five-minute idle window, so
     * composing a question cannot race the unload that frees the model. A
     * phone that is being typed into is a phone using the model.
     */
    fun noteTyping() {
        if (!closed && _state.value.engine == EngineState.READY) policy.touched()
    }

    /**
     * Releases the engine. If a reply is still running, only the stop flag is
     * set here: [send] destroys the handle after the native loop returns,
     * because destroying it underneath a running generation is a
     * use-after-free in C++.
     */
    fun close() {
        closed = true
        stopRequested.set(true)
        if (_state.value.generating || _state.value.busy) {
            closeDeferred = true
            return
        }
        shutdownEngine()
    }

    private fun shutdownEngine() {
        val current = engine
        engine = null
        policy.reset()
        runCatching { current?.destroy() }
        _state.update {
            it.copy(
                engine = EngineState.OFF,
                loadedModel = null,
                busy = false,
                generating = false,
                streamingText = "",
            )
        }
    }

    private fun ensureEngine(): EngineResult {
        engine?.let { return EngineResult.Ok }
        val made = engineFactory()
        return when (val result = made.create()) {
            EngineResult.Ok -> {
                engine = made
                EngineResult.Ok
            }

            is EngineResult.Failed -> {
                runCatching { made.destroy() }
                _state.update { it.copy(engine = EngineState.UNAVAILABLE) }
                result
            }
        }
    }

    private fun notice(text: String, problem: Boolean) {
        _state.update { it.copy(notice = text, noticeIsProblem = problem) }
    }

    private fun ModelStore.StoredModel.toLocalAiModel(tier: DeviceTiers.Tier): LocalAiModel {
        val headerQuant = info?.quant
        val nameQuant = if (headerQuant == null) GgufFileType.fromName(name) else null
        return LocalAiModel(
            name = name,
            file = file,
            bytes = bytes,
            info = info,
            quant = headerQuant ?: nameQuant,
            quantFromName = headerQuant == null && nameQuant != null,
            verdict = tier.verdict(info),
        )
    }

    companion object {

        /** Low enough that a small model is coherent; the owner has no dial in E1. */
        const val DEFAULT_TEMPERATURE = 0.7f

        const val COULD_NOT_OPEN_WORDS =
            "That file could not be opened. Pick it again from the file picker."

        const val NOT_HERE_WORDS =
            "That model is not on this phone any more. Import it again."

        const val EMPTY_ANSWER_WORDS =
            "The model answered with nothing. Try a shorter or simpler question."

        const val WAIT_FOR_ANSWER_WORDS =
            "Wait for that to finish, then turn it off. Nothing was unloaded."
    }
}
