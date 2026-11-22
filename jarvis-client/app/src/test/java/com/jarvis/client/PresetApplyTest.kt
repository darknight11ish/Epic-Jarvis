package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.FocusPresets
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.atomic.AtomicInteger

/**
 * The owner's report of 2026-11-21, second half, in their words: *"the preset
 * should finish loading even if i exit the app or go to another menu or area
 * of the map."*
 *
 * WHAT IT IS. The phone used to press a preset on `rememberCoroutineScope()` -
 * the composition's own scope - so navigating away cancelled the phone's half
 * of the request while the PC kept loading the model, the row came back
 * pressable, and the list could read "Chosen - not running now" over a model
 * that was in fact being prepared. `JarvisRuntime.useFocusPresetNow` now runs
 * the whole press on the runtime's long-lived scope, publishes the preset id in
 * `presetApplying` while it waits and keeps the sentence in `presetNotice`
 * afterwards; after a 200 it re-reads `/api/work` every 2 s for at most 120 s
 * until the PC's own lane says the pressed preset is running.
 *
 * HOW IT IS DRIVEN WITHOUT A PC. A fake [JarvisRuntime.PresetIo] answers the
 * press's reads and its one POST, and a fake wait stands in for the 2 s
 * `delay` - the same seam shape `UndoNoticeTimeoutTest` uses for its 15 s
 * timer. Nothing here sleeps out the two-minute cap, and nothing needs an
 * Android device or a desktop: this is the required `phone-unit-tests` suite.
 *
 * WHAT IT CANNOT DO. The last check - the real PC's `/api/work` answer saying
 * a model finished loading - is not a device pass here. The rules that make
 * the wait honest are proved against the contract's own [FocusPresets] view,
 * so the confirmation is exactly the rule the row's mark draws. The on-phone
 * check is in the PR body.
 */
class PresetApplyTest {

    /** The runtime is a singleton, so every seam and every launched job is put back. */
    private val jobs = mutableListOf<Job>()
    private var io: FakePresetIo? = null

    @After
    fun putTheRuntimeBack() {
        // Release a POST the failing test left gated, then let the launch end:
        // a leaked coroutine would answer the NEXT test's fake.
        io?.gate?.complete(Unit)
        runBlocking {
            jobs.forEach { job -> runCatching { withTimeout(5_000) { job.join() } } }
        }
        JarvisRuntime.resetPresetApplyState()
        JarvisRuntime.clearNotice()
    }

    // ------------------------------------------------- the owner's ask ----

    @Test
    fun `leaving the screen cannot cancel a preset that is still loading`() = runBlocking {
        val fake = install(
            FakePresetIo { n -> if (n == 1) view(chosen = null, runningLane = LANE_MAIN) else view(ID, LANE_POOLED) },
            FakePollWait(),
        )

        // The screen's own scope: the composition that presses the button and
        // is cancelled the moment the owner goes to another menu. The job the
        // runtime hands back is tracked so a failing test still cleans up.
        val screenScope = CoroutineScope(Job())
        val applyJob = CompletableDeferred<Job>()
        screenScope.launch { applyJob.complete(JarvisRuntime.useFocusPresetNow(ID)) }

        withTimeout(TIMEOUT_MS) { fake.applyStarted.receive() }
        val press = withTimeout(TIMEOUT_MS) { applyJob.await() }
        jobs += press
        assertEquals("the row cannot see the press yet", ID, JarvisRuntime.presetApplying.value)

        // The owner leaves. Everything the composition owns dies here - and it
        // must not touch the press.
        screenScope.cancel()
        fake.gate.complete(Unit)

        // The press still finishes: the POST returns, the poll sees the PC's
        // lane, and the in-flight state is cleared by the runtime itself.
        withTimeout(TIMEOUT_MS) { press.join() }
        assertEquals("the apply POST did not complete after the screen left", 1, fake.applies.get())
        assertEquals(
            "the one POST was the contract's route and body",
            listOf(FocusPresets.APPLY_PATH to """{"preset":"$ID"}"""),
            fake.posted.toList(),
        )
        assertEquals(FocusPresets.APPLIED, JarvisRuntime.presetNotice.value)
        assertEquals(1, fake.afterApplies.get())
    }

    // --------------------------------------------------- the two flows ----

    @Test
    fun `the applying state is visible while in flight and cleared after success`() = runBlocking {
        val fake = install(
            FakePresetIo { n -> if (n == 1) view(chosen = null, runningLane = LANE_MAIN) else view(ID, LANE_POOLED) },
            FakePollWait(),
        )
        val job = JarvisRuntime.useFocusPresetNow(ID)
        jobs += job

        withTimeout(TIMEOUT_MS) { fake.applyStarted.receive() }
        assertEquals("nothing tells the plate a preset is being prepared", ID, JarvisRuntime.presetApplying.value)
        assertNull("an old sentence was not cleared when the press started", JarvisRuntime.presetNotice.value)

        fake.gate.complete(Unit)
        withTimeout(TIMEOUT_MS) { job.join() }
        assertNull("a finished press still says it is applying", JarvisRuntime.presetApplying.value)
        assertEquals(FocusPresets.APPLIED, JarvisRuntime.presetNotice.value)
        assertEquals("the answer must be read, but only once", 1, fake.applies.get())
        assertEquals("the queue and the card are re-read after the wait", 1, fake.afterApplies.get())
    }

    @Test
    fun `a refusal clears the applying state and says why`() = runBlocking {
        val fake = install(FakePresetIo { view(chosen = null, runningLane = LANE_MAIN) }, FakePollWait())
        fake.applyAnswer = {
            ApiResult.Ok(
                409 to buildJsonObject { put("error", "the model switch did not happen") },
            )
        }
        val job = JarvisRuntime.useFocusPresetNow(ID)
        jobs += job

        withTimeout(TIMEOUT_MS) { fake.applyStarted.receive() }
        assertEquals(ID, JarvisRuntime.presetApplying.value)
        fake.gate.complete(Unit)
        withTimeout(TIMEOUT_MS) { job.join() }

        assertNull("a refused press still says it is applying", JarvisRuntime.presetApplying.value)
        assertEquals(
            "the refusal's own words are kept",
            "Not changed. the model switch did not happen",
            JarvisRuntime.presetNotice.value,
        )
        // No 200 means no wait, and no second POST either.
        assertEquals(1, fake.applies.get())
        assertEquals("only the pre-press read ran", 1, fake.reads.get())
        assertEquals(1, fake.afterApplies.get())
    }

    @Test
    fun `a broken POST clears the applying state and says why`() = runBlocking {
        val fake = install(FakePresetIo { view(chosen = null, runningLane = LANE_MAIN) }, FakePollWait())
        fake.applyAnswer = { ApiResult.Failed(ApiError.Unreachable("the desktop did not answer")) }
        val job = JarvisRuntime.useFocusPresetNow(ID)
        jobs += job

        fake.gate.complete(Unit)
        withTimeout(TIMEOUT_MS) { job.join() }

        assertNull("a failed POST still says it is applying", JarvisRuntime.presetApplying.value)
        val notice = JarvisRuntime.presetNotice.value
        assertTrue("a failed POST says nothing: $notice", notice != null && notice.startsWith("Not changed."))
        assertEquals(1, fake.applies.get())
        assertEquals("a failed POST re-reads nothing", 0, fake.afterApplies.get())
    }

    // ------------------------------------------------- one press at a time --

    @Test
    fun `while one preset is being prepared a second press posts nothing`() = runBlocking {
        val fake = install(
            FakePresetIo { n -> if (n == 1) view(chosen = null, runningLane = LANE_MAIN) else view(ID, LANE_POOLED) },
            FakePollWait(),
        )
        val first = JarvisRuntime.useFocusPresetNow(ID)
        jobs += first
        withTimeout(TIMEOUT_MS) { fake.applyStarted.receive() }

        // A second tap that reaches the runtime before the plate redraws.
        assertEquals(FocusPresets.ALREADY_APPLYING, JarvisRuntime.useFocusPreset(ID))
        assertEquals("the second press posted a second apply", 1, fake.applies.get())

        fake.gate.complete(Unit)
        withTimeout(TIMEOUT_MS) { first.join() }
        assertNull(JarvisRuntime.presetApplying.value)
        assertEquals("the first press did not finish alone", 1, fake.applies.get())
    }

    @Test
    fun `a stale link still blocks the apply before anything is posted`() = runBlocking {
        val fake = install(FakePresetIo { view(chosen = null, runningLane = LANE_MAIN) }, FakePollWait())
        fake.blocker = FocusPresets.STALE
        val job = JarvisRuntime.useFocusPresetNow(ID)
        jobs += job

        withTimeout(TIMEOUT_MS) { job.join() }
        assertEquals("rule 4: nothing may be posted on a stale link", 0, fake.applies.get())
        assertEquals("the contract is not even read when the link is stale", 0, fake.reads.get())
        assertNull(JarvisRuntime.presetApplying.value)
        assertEquals(FocusPresets.STALE, JarvisRuntime.presetNotice.value)
    }

    // ---------------------------------------------------------- the wait --

    @Test
    fun `polling stops as soon as the PC reports the chosen lane active`() = runBlocking {
        val wait = FakePollWait()
        val fake = install(
            FakePresetIo { n ->
                when (n) {
                    1 -> view(chosen = null, runningLane = LANE_MAIN) // the read before the POST
                    2, 3 -> view(ID, LANE_MAIN) // still loading: the PC is on the old lane
                    else -> view(ID, LANE_POOLED) // the PC's own lane is the preset's lane now
                }
            },
            wait,
        )
        val job = JarvisRuntime.useFocusPresetNow(ID)
        jobs += job
        fake.gate.complete(Unit)
        withTimeout(TIMEOUT_MS) { job.join() }

        assertNull(JarvisRuntime.presetApplying.value)
        assertEquals("the apply was posted once", 1, fake.applies.get())
        assertEquals(
            "reads: the pre-press read, the two mismatches and the match",
            4,
            fake.reads.get(),
        )
        assertEquals("the wait stopped at the match", listOf(2_000L, 2_000L), wait.waits.toList())
        assertEquals(FocusPresets.APPLIED, JarvisRuntime.presetNotice.value)
        // And the last read is the plate's list: it now says Current.
        val shown = (JarvisRuntime.focusPresets.value as FocusPresets.Read.Loaded).view
        assertEquals(FocusPresets.CHOSEN, FocusPresets.rowMark(shown, shown.presets.single()))
        assertFalse(FocusPresets.chosenNotRunning(shown))
    }

    @Test
    fun `polling gives up honestly after the cap and never invents a lane`() = runBlocking {
        val wait = FakePollWait()
        // Every answer after the press still says the PC is on the OLD lane -
        // exactly the owner's report, where the phone gave up on its own.
        val fake = install(
            FakePresetIo { n -> if (n == 1) view(null, LANE_MAIN) else view(ID, LANE_MAIN) },
            wait,
        )
        val job = JarvisRuntime.useFocusPresetNow(ID)
        jobs += job
        fake.gate.complete(Unit)
        withTimeout(TIMEOUT_MS) { job.join() }

        assertNull("a timed-out wait still says it is applying", JarvisRuntime.presetApplying.value)
        assertEquals("the apply was posted once, and never again while waiting", 1, fake.applies.get())
        val capReads = JarvisRuntime.PRESET_POLL_CAP_MS / JarvisRuntime.PRESET_POLL_INTERVAL_MS
        assertEquals(
            "the wait kept asking for the whole cap and then stopped",
            (capReads + 2).toInt(), // 1 pre-press read + 1 read per interval + the read at the cap
            fake.reads.get(),
        )
        assertEquals(
            "each wait was the measured interval, and there were cap/interval of them",
            List(capReads.toInt()) { 2_000L },
            wait.waits.toList(),
        )
        assertEquals(FocusPresets.COULD_NOT_CONFIRM, JarvisRuntime.presetNotice.value)
        // The list is the PC's own answer, not a state the phone made up: the
        // saved preset and the running lane still disagree, and the row says so.
        val shown = (JarvisRuntime.focusPresets.value as FocusPresets.Read.Loaded).view
        assertTrue("the mismatch was hidden instead of shown", FocusPresets.chosenNotRunning(shown))
        assertEquals(FocusPresets.CHOSEN_NOT_RUNNING, FocusPresets.rowMark(shown, shown.presets.single()))
        assertEquals(1, fake.afterApplies.get())
    }

    // ------------------------------------------------ the wiring itself ----

    /**
     * There is no Compose test rule here (the reactor's frame loop never goes
     * idle), so the screen's half is held by reading the shipped source for the
     * exact line - the same shape [PresetsLandingTest] already uses for its two
     * wiring rules. It fails on today's tree for a real reason, not a typo: the
     * plate launched the press on its own scope and kept `busy`/`notice` in
     * `remember`, which is exactly what lost the press when the owner navigated.
     */
    @Test
    fun `the plate presses through the runtime and reads both flows from it`() {
        val plate = repoFile(PLATE).readText()
        assertEquals(
            "both surfaces must press through the runtime's long-lived entry",
            2,
            plate.split("JarvisRuntime.useFocusPresetNow(").size - 1,
        )
        assertFalse(
            "a surface still launches the press on the screen's own scope",
            plate.contains("scope.launch { JarvisRuntime.useFocusPreset("),
        )
        assertEquals(
            "the in-flight state must come from the runtime on both surfaces",
            2,
            plate.split("val applying by JarvisRuntime.presetApplying.collectAsState()").size - 1,
        )
        assertEquals(
            "the sentence must come from the runtime on both surfaces",
            2,
            plate.split("val notice by JarvisRuntime.presetNotice.collectAsState()").size - 1,
        )
        assertFalse(
            "the plate remembers its own busy again, so navigation loses it",
            plate.contains("var busy by remember"),
        )
        assertTrue(
            "the pressed row does not say Being prepared",
            plate.contains("if (busy == p.id) FocusPresets.PENDING else FocusPresets.USE_THIS"),
        )
    }

    @Test
    fun `the runtime owns the press, posts once, and polls by reading only`() {
        val runtime = repoFile(RUNTIME).readText()
        assertTrue(
            "the non-suspending entry no longer launches on the runtime's own scope",
            runtime.contains("fun useFocusPresetNow(id: String): Job = scope.launch { applyFocusPreset(id) }"),
        )
        assertEquals("the press gained a second POST", 1, runtime.split("presetIo.apply(").size - 1)
        assertTrue(
            "the production transport does not post the contract's action through the api",
            runtime.contains("api.focusPresetApply(route, body)"),
        )
        assertTrue(
            "the stale-link rule is no longer the app's existing blocker",
            runtime.contains("override fun blocker(): String? = actionBlocker()"),
        )
        assertTrue(
            "the in-flight flow is not set before the press and cleared in finally",
            runtime.contains("_presetApplying.value = id") &&
                runtime.contains("finally") &&
                runtime.contains("_presetApplying.value = null"),
        )
    }

    // ------------------------------------------------------------- fakes ----

    private fun install(fake: FakePresetIo, wait: FakePollWait): FakePresetIo {
        io = fake
        JarvisRuntime.presetIo = fake
        JarvisRuntime.presetPollWait = wait::wait
        return fake
    }

    private fun view(chosen: String?, runningLane: String?): FocusPresets.Read =
        FocusPresets.Read.Loaded(
            FocusPresets.View(
                presets = listOf(PRESET),
                chosen = chosen,
                found = null,
                switchPath = null,
                activeLane = runningLane?.let { FocusPresets.ActiveLane(it, "http://127.0.0.1:11450") },
            ),
        )

    /**
     * The press's outside world, answering from a script. [answers] is handed
     * the 1-based read number: read 1 is the one the press makes before its
     * POST, the rest are the wait's reads. The POST suspends on [gate] so a
     * test can stand exactly in the middle of the press - the only way to see
     * "in flight" deterministically.
     */
    private class FakePresetIo(
        private val answers: (Int) -> FocusPresets.Read,
    ) : JarvisRuntime.PresetIo {
        val gate = CompletableDeferred<Unit>()
        val applyStarted = Channel<Unit>(Channel.UNLIMITED)
        val applies = AtomicInteger()
        val reads = AtomicInteger()
        val afterApplies = AtomicInteger()
        val posted = mutableListOf<Pair<String, String>>()

        var blocker: String? = null
        var applyAnswer: () -> ApiResult<Pair<Int, JsonObject?>> =
            { ApiResult.Ok(200 to buildJsonObject { put("changed", true) }) }

        override fun blocker(): String? = blocker

        override suspend fun read(): FocusPresets.Read = answers(reads.incrementAndGet())

        override suspend fun apply(route: String, body: String): ApiResult<Pair<Int, JsonObject?>> {
            applies.incrementAndGet()
            synchronized(posted) { posted += route to body }
            applyStarted.send(Unit)
            gate.await()
            return applyAnswer()
        }

        override suspend fun afterApply() {
            afterApplies.incrementAndGet()
        }
    }

    /**
     * A fake for [JarvisRuntime.presetPollWait]: it records every duration
     * production asked for and returns at once, so the two-minute cap is
     * driven without sleeping it (the same shape as `FakeUndoWait`).
     */
    private class FakePollWait {
        val waits = mutableListOf<Long>()

        suspend fun wait(ms: Long) {
            synchronized(waits) { waits += ms }
        }
    }

    private companion object {
        const val ID = "general"
        const val LANE_MAIN = "main"
        const val LANE_POOLED = "pooled"

        /** Long enough that a working press never trips it; short enough that a hung one fails. */
        const val TIMEOUT_MS = 10_000L

        const val PLATE = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/FocusPresetsPlate.kt"
        const val RUNTIME = "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt"

        /**
         * The owner's heavy preset in the shape the real contract sends for it:
         * a pooled-lane row with an apply action. The words are deliberately
         * minimal - this suite is about the press's state, not the copy, which
         * `FocusPresetsTest` holds against the generated fixture.
         */
        val PRESET = FocusPresets.Preset(
            id = ID,
            title = "General",
            focus = "everyday questions, writing, life admin",
            what = "what it is for",
            cost = "what it costs",
            worse = "what it is worse at",
            model = "gemma4:26b-a4b-it-qat",
            lane = FocusPresets.Lane(
                key = LANE_POOLED,
                card = "all three cards",
                port = null,
                words = "one model across all three cards",
            ),
            context = 32768,
            helper = null,
            measured = null,
            pending = false,
            heavyMode = true,
            apply = FocusPresets.Apply(
                action = FocusPresets.USE_THIS,
                route = FocusPresets.APPLY_PATH,
                body = null,
                switchRoute = null,
                laneStart = true,
                auto = false,
            ),
        )
    }
}
