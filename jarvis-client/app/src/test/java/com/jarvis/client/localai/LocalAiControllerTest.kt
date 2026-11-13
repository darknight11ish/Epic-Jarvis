package com.jarvis.client.localai

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.File
import java.util.concurrent.atomic.AtomicLong

/**
 * The Local AI state machine, driven with a fake engine and a clock the test
 * moves: switch off by default, no engine before a Load tap, a model refused
 * when the tier says it is too big, the 5-second idle unload, and a reply cut
 * off at the hard cap.
 */
class LocalAiControllerTest {

    @get:Rule
    val temporary = TemporaryFolder()

    private val clockNow = AtomicLong(1_000L)

    private class MapFlags : LocalAiFlagStore {
        val values = mutableMapOf<String, Boolean>()
        override fun readBoolean(key: String, fallback: Boolean): Boolean = values[key] ?: fallback
        override fun writeBoolean(key: String, value: Boolean) {
            values[key] = value
        }
    }

    private fun fixture(name: String = "qwen2-valid.gguf"): ByteArray =
        javaClass.getResourceAsStream("/gguf/$name")?.readBytes()
            ?: error("missing fixture /gguf/$name")

    private fun storeWith(vararg names: String = arrayOf("small.gguf")): ModelStore {
        val root = File(temporary.root, "models")
        val store = ModelStore(root, freeSpace = { 10L * 1024 * 1024 * 1024 }, minFreeBytes = 0L)
        for (name in names) {
            val source = if (name == "too-big.gguf") fixture("too-big.gguf") else fixture()
            val result = store.import(name, source.size.toLong(), ByteArrayInputStream(source))
            check(result is ModelStore.ImportResult.Ok) { "could not place $name: $result" }
        }
        return store
    }

    private fun policy(
        idle: Long = LocalEnginePolicy.IDLE_UNLOAD_MILLIS,
        cap: Long = LocalEnginePolicy.HARD_CAP_MILLIS,
    ) = LocalEnginePolicy(clock = { clockNow.get() }, idleMillis = idle, hardCapMillis = cap)

    private fun controller(
        engine: FakeLocalEngine = FakeLocalEngine(),
        store: ModelStore = storeWith(),
        settings: LocalAiSettings = LocalAiSettings(MapFlags()),
        policy: LocalEnginePolicy = policy(),
        tier: DeviceTiers.Tier = DeviceTiers.of(12L * DeviceTiers.GIB, 512, 8),
        made: MutableList<FakeLocalEngine> = mutableListOf(),
    ): LocalAiController = LocalAiController(
        engineFactory = {
            made += engine
            engine
        },
        store = store,
        tier = tier,
        settings = settings,
        policy = policy,
        dispatcher = Dispatchers.Default,
    )

    @Test
    fun theScreenShipsOffAndCreatesNothingBeforeALoadTap() = runBlocking {
        val made = mutableListOf<FakeLocalEngine>()
        val controller = controller(made = made)
        try {
            val state = controller.state.value
            assertFalse("the switch must ship OFF", state.switchOn)
            assertEquals(EngineState.OFF, state.engine)
            assertEquals(LocalAiSettings.DEFAULT_ENABLED, state.switchOn)
            assertTrue("no engine may exist before the owner acts", made.isEmpty())
        } finally {
            controller.close()
        }
    }

    @Test
    fun turningTheSwitchOnDoesNotCreateAnEngineOrLoadAnything() = runBlocking {
        val engine = FakeLocalEngine()
        val made = mutableListOf<FakeLocalEngine>()
        val settings = LocalAiSettings(MapFlags())
        val controller = controller(engine = engine, settings = settings, made = made)
        try {
            controller.setSwitch(true)
            assertTrue(controller.state.value.switchOn)
            assertTrue(settings.enabled)
            assertEquals(EngineState.OFF, controller.state.value.engine)
            assertTrue("ON must not create the engine; only Load may", made.isEmpty())
            assertEquals(0, engine.createCalls)
            assertEquals(0, engine.loadCalls)
            assertEquals(
                listOf("small.gguf"),
                controller.state.value.models.map { it.name },
            )
            assertTrue(controller.state.value.models.single().verdict.fits)
        } finally {
            controller.close()
        }
    }

    @Test
    fun loadCreatesTheEngineOnceWithTheTierNumbers() = runBlocking {
        val engine = FakeLocalEngine()
        val made = mutableListOf<FakeLocalEngine>()
        val controller = controller(engine = engine, made = made)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")

            assertEquals(1, engine.createCalls)
            assertEquals(1, engine.loadCalls)
            assertTrue(made.single() === engine)
            val plan = requireNotNull(engine.lastPlan)
            assertEquals(4, plan.threads)
            assertEquals(4096, plan.contextTokens)
            assertEquals(2048, plan.maxTokens)
            assertTrue(engine.lastPath!!.endsWith("small.gguf"))
            assertEquals(EngineState.READY, controller.state.value.engine)
            assertEquals("small.gguf", controller.state.value.loadedModel)
            assertNull(controller.state.value.notice)
        } finally {
            controller.close()
        }
    }

    @Test
    fun aReplyIsOnScreenWithItsMeasuredSpeed() = runBlocking {
        val engine = FakeLocalEngine()
        val controller = controller(engine = engine)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            controller.send("hello")

            val state = controller.state.value
            assertEquals(2, state.lines.size)
            assertEquals(ChatLine.From.YOU, state.lines[0].from)
            assertEquals("hello", state.lines[0].text)
            assertEquals(ChatLine.From.PHONE, state.lines[1].from)
            assertEquals("Hello from the phone.", state.lines[1].text)
            // 4 generated tokens in 500 ms is 8 tokens per second, from the
            // native numbers, not from a Kotlin stopwatch.
            assertEquals(8.0, state.lines[1].tokensPerSecond!!, 0.0001)
            assertFalse(state.lines[1].stoppedAtTimeLimit)
            assertEquals(EngineState.READY, state.engine)
            assertFalse(state.generating)
            assertTrue("the question must reach the model", engine.lastPrompt!!.contains("user\nhello"))
            assertTrue("the phone's template must be applied", engine.lastPrompt!!.startsWith("<|im_start|>system"))
        } finally {
            controller.close()
        }
    }

    @Test
    fun aReplyWithNoNativeNumbersSaysNotMeasuredInsteadOfGuessing() = runBlocking {
        val engine = FakeLocalEngine(stats = null)
        val controller = controller(engine = engine)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            controller.send("hello")
            val reply = controller.state.value.lines.last()
            assertNull(reply.tokensPerSecond)
            assertEquals(LocalAiWords.NOT_MEASURED, LocalAiWords.speedLine(reply.tokensPerSecond))
        } finally {
            controller.close()
        }
    }

    @Test
    fun fiveSecondsWithNothingAskedUnloadsTheModel() = runBlocking {
        val engine = FakeLocalEngine()
        val controller = controller(engine = engine)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            clockNow.addAndGet(LocalEnginePolicy.IDLE_UNLOAD_MILLIS)
            controller.tick()

            assertEquals(EngineState.IDLE, controller.state.value.engine)
            assertNull(controller.state.value.loadedModel)
            assertEquals(1, engine.unloadCalls)
            assertEquals(LocalAiWords.IDLE_UNLOAD_NOTE, controller.state.value.notice)
        } finally {
            controller.close()
        }
    }

    @Test
    fun theIdleRuleDoesNotFireBeforeFiveSeconds() = runBlocking {
        val controller = controller()
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            clockNow.addAndGet(LocalEnginePolicy.IDLE_UNLOAD_MILLIS - 1L)
            controller.tick()
            assertEquals(EngineState.READY, controller.state.value.engine)
        } finally {
            controller.close()
        }
    }

    @Test
    fun aModelTheTierRefusesIsNeverHandedToTheEngine() = runBlocking {
        val engine = FakeLocalEngine()
        val controller = controller(engine = engine, store = storeWith("too-big.gguf"))
        try {
            controller.setSwitch(true)
            controller.load("too-big.gguf")

            assertTrue(controller.state.value.notice!!.startsWith("Too big for this phone"))
            assertEquals(0, engine.createCalls)
            assertEquals(0, engine.loadCalls)
            assertNull(controller.state.value.loadedModel)
        } finally {
            controller.close()
        }
    }

    @Test
    fun aMissingLibraryLeavesTheScreenOnAndSaysWhy() = runBlocking {
        val engine = FakeLocalEngine(failCreate = "No on-device engine in this build.")
        val controller = controller(engine = engine)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")

            assertEquals(EngineState.UNAVAILABLE, controller.state.value.engine)
            assertEquals("No on-device engine in this build.", controller.state.value.notice)
            assertTrue(controller.state.value.switchOn)
            assertEquals(0, engine.loadCalls)
            assertEquals(0, engine.generateCalls)
        } finally {
            controller.close()
        }
    }

    @Test
    fun turningTheSwitchOffDestroysTheEngineAndClearsTheChat() = runBlocking {
        val engine = FakeLocalEngine()
        val settings = LocalAiSettings(MapFlags())
        val controller = controller(engine = engine, settings = settings)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            controller.send("hello")
            controller.setSwitch(false)

            assertEquals(1, engine.destroyCalls)
            assertEquals(EngineState.OFF, controller.state.value.engine)
            assertNull(controller.state.value.loadedModel)
            assertTrue(controller.state.value.lines.isEmpty())
            assertFalse(settings.enabled)
        } finally {
            controller.close()
        }
    }

    @Test
    fun importCopiesThePickedFileAndListsIt() = runBlocking {
        val controller = controller(store = storeWith())
        try {
            controller.setSwitch(true)
            val payload = fixture()
            val imported = controller.importModel("picked.gguf", payload.size.toLong()) {
                ByteArrayInputStream(payload)
            }
            assertTrue(imported)
            assertTrue(controller.state.value.models.any { it.name == "picked.gguf" })
            assertEquals(LocalAiWords.imported("picked.gguf"), controller.state.value.notice)
            assertFalse(controller.state.value.busy)
            assertNull(controller.state.value.importName)

            val duplicate = controller.importModel("picked.gguf", payload.size.toLong()) {
                ByteArrayInputStream(payload)
            }
            assertFalse(duplicate)
            assertTrue(controller.state.value.notice!!.contains("already on this phone"))
        } finally {
            controller.close()
        }
    }

    @Test
    fun importRefusesWhenTheSwitchIsOffAndWhenTheFileCannotBeOpened() = runBlocking {
        val controller = controller()
        try {
            val off = controller.importModel("picked.gguf", 1L) { ByteArrayInputStream(fixture()) }
            assertFalse(off)
            assertEquals(LocalAiWords.TURN_ON_FIRST, controller.state.value.notice)

            controller.setSwitch(true)
            val unopened = controller.importModel("picked.gguf", 1L) { null }
            assertFalse(unopened)
            assertEquals(LocalAiController.COULD_NOT_OPEN_WORDS, controller.state.value.notice)
        } finally {
            controller.close()
        }
    }

    @Test
    fun deleteRemovesTheModelAndSaysSo() = runBlocking {
        val controller = controller(store = storeWith())
        try {
            controller.setSwitch(true)
            controller.deleteModel("small.gguf")
            assertTrue(controller.state.value.models.isEmpty())
            assertTrue(controller.state.value.notice!!.contains("was deleted"))
        } finally {
            controller.close()
        }
    }

    @Test
    fun aReplyStopsAtTheHardCapAndSaysItWasTheLimit() = runBlocking {
        // 200 pieces at 5 ms is 1 second of work if nothing stops it. The cap
        // is 60 ms, so the watchdog must set the stop flag long before that.
        val engine = FakeLocalEngine(
            pieces = List(200) { "x" },
            stats = null,
            emitDelayMillis = 5L,
        )
        val controller = controller(engine = engine, policy = policy(cap = 60L))
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            val startedAt = System.nanoTime()
            controller.send("go")
            val elapsedMillis = (System.nanoTime() - startedAt) / 1_000_000L

            val reply = controller.state.value.lines.last()
            assertEquals(ChatLine.From.PHONE, reply.from)
            assertTrue("the cap must be reported", reply.stoppedAtTimeLimit)
            assertTrue("the reply must be cut short, was ${reply.text.length} pieces", reply.text.length < 200)
            assertEquals(LocalAiWords.HARD_CAP_NOTE, controller.state.value.notice)
            assertTrue("the cap must fire near 60 ms, took $elapsedMillis ms", elapsedMillis < 1_000L)
        } finally {
            controller.close()
        }
    }

    @Test
    fun askingTooEarlyIsRefusedInWords() = runBlocking {
        val controller = controller()
        try {
            controller.send("hello")
            assertEquals(LocalAiWords.TURN_ON_FIRST, controller.state.value.notice)

            controller.setSwitch(true)
            controller.send("hello")
            assertEquals(LocalAiWords.LOAD_FIRST, controller.state.value.notice)

            controller.load("small.gguf")
            controller.unload()
            controller.send("hello")
            assertEquals(LocalAiWords.LOAD_FIRST, controller.state.value.notice)
        } finally {
            controller.close()
        }
    }

    @Test
    fun closingTheScreenReleasesTheEngine() = runBlocking {
        val engine = FakeLocalEngine()
        val controller = controller(engine = engine)
        controller.setSwitch(true)
        controller.load("small.gguf")
        controller.close()
        assertEquals(1, engine.destroyCalls)
        assertEquals(EngineState.OFF, controller.state.value.engine)
    }

    @Test
    fun aSecondQuestionCarriesTheFirstExchangeInThePrompt() = runBlocking {
        val engine = FakeLocalEngine()
        val controller = controller(engine = engine)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            controller.send("first thing")
            controller.send("second thing")
            val prompt = requireNotNull(engine.lastPrompt)
            assertTrue("the earlier question must be in the prompt", prompt.contains("first thing"))
            assertTrue("the earlier answer must be in the prompt", prompt.contains("Hello from the phone."))
            assertTrue(prompt.contains("second thing"))
        } finally {
            controller.close()
        }
    }

    @Test
    fun typingKeepsTheModelAliveButStillNeverLoadsAnything() = runBlocking {
        val engine = FakeLocalEngine()
        val controller = controller(engine = engine)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            clockNow.addAndGet(LocalEnginePolicy.IDLE_UNLOAD_MILLIS - 1L)
            controller.noteTyping()
            clockNow.addAndGet(LocalEnginePolicy.IDLE_UNLOAD_MILLIS - 1L)
            controller.tick()
            assertEquals("typing must restart the idle window", EngineState.READY, controller.state.value.engine)
            clockNow.addAndGet(1L)
            controller.tick()
            assertEquals(EngineState.IDLE, controller.state.value.engine)
            assertEquals(1, engine.unloadCalls)
        } finally {
            controller.close()
        }
    }

    @Test
    fun turningTheSwitchOffMidAnswerIsRefusedInWords() = runBlocking {
        val engine = FakeLocalEngine(pieces = List(40) { "x" }, emitDelayMillis = 5L)
        val controller = controller(engine = engine)
        try {
            controller.setSwitch(true)
            controller.load("small.gguf")
            val answer = launch(Dispatchers.Default) { controller.send("go") }
            withTimeout(2_000L) {
                while (!controller.state.value.generating) delay(2L)
            }
            controller.setSwitch(false)
            assertTrue("the switch must stay on until the answer ends", controller.state.value.switchOn)
            assertEquals(LocalAiController.WAIT_FOR_ANSWER_WORDS, controller.state.value.notice)
            answer.join()
            assertEquals(0, engine.destroyCalls)
            controller.setSwitch(false)
            assertEquals(1, engine.destroyCalls)
        } finally {
            controller.close()
        }
    }

    @Test
    fun theSettingSurvivesButTheEngineStillWaitsForATap() = runBlocking {
        val flags = MapFlags()
        val sharedStore = storeWith()
        val first = controller(store = sharedStore, settings = LocalAiSettings(flags))
        first.setSwitch(true)
        first.close()

        val second = controller(store = sharedStore, settings = LocalAiSettings(flags))
        try {
            assertTrue("a saved ON is shown as ON", second.state.value.switchOn)
            assertEquals(EngineState.OFF, second.state.value.engine)
            assertEquals(0, second.state.value.models.size)
        } finally {
            second.close()
        }
    }
}
