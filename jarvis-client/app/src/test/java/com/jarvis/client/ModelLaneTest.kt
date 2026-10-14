package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.ModelLane
import com.jarvis.client.net.ModelLaneInfo
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Start the local model" - the button on the standing line both apps now draw
 * (backend/model-lanes.patch, `backend/jarvis_model_lanes.py`; the owner's
 * decision of 2026-10-13; [ModelWords] for the line itself).
 *
 * THE DEFECT THIS ANSWERS. On 2026-10-13 both of the owner's Ollama lanes died
 * at about 16:30 and nothing said so for about five hours. The line now says it,
 * and until this work it deliberately did NOTHING. He has since decided it
 * should offer one action: start the lane that is down, by running HIS OWN
 * Windows logon task on the PC.
 *
 * THE FAILURE THIS SUITE EXISTS TO MAKE IMPOSSIBLE is named in the brief that
 * asked for the feature: **a button that reports success and changes nothing.**
 * Starting a Windows task returns long before a model is loaded, so every check
 * here is about what is CLAIMED against what is TRUE:
 *
 *  * a down lane offers the button, an up lane does not, and neither does a lane
 *    the PC did not report - "the PC did not say" is not "it is down";
 *  * a start that does not come up does NOT clear the warning, and its sentence
 *    never claims the model is answering;
 *  * only the lane really answering (`up`) - or the PC's own `ollama` field -
 *    clears it;
 *  * the phone sends an EMPTY body, so no tap can name another lane and nothing
 *    can start both at once.
 *
 * Pure Kotlin, so no phone is needed: [ModelLane] holds the words and the rules,
 * and the desktop's copy of the same sentences lives in
 * `jarvis-desktop/src/lane-start.js`.
 */
class ModelLaneTest {

    /** A lane reading, as the PC sends it. Defaults: down, and pressable. */
    private fun lane(
        state: String = ModelLane.DOWN,
        canStart: Boolean = true,
        message: String = "",
        error: String = "",
        elapsedS: Double? = null,
    ) = ModelLaneInfo(
        lane = "everyday",
        words = "the everyday model (the main one chat uses)",
        port = 11436,
        task = "Jarvis Ollama - Everyday model (RTX 2060)",
        state = state,
        canStart = canStart,
        why = "Nothing is answering on port 11436.",
        elapsedS = elapsedS,
        message = message,
        error = error,
    )

    // ------------------------------------------------------------ the offer --

    @Test
    fun `a lane that is down offers the one action`() {
        assertTrue(ModelLane.offers(lane()))
        assertEquals(ModelLane.START, ModelLane.buttonWords(lane()))
        assertTrue(ModelLane.canPress(lane()))
        assertEquals("Start the local model", ModelLane.START)
    }

    /**
     * CONTROL. The half of the rule that keeps the button honest. Drawing it for
     * an up lane would be offering an action with nothing to do; drawing it for
     * a null reading would be inventing a lane the PC never mentioned - the same
     * mistake, one field over, that [ModelWordsTest] already guards for the
     * warning itself.
     */
    @Test
    fun `an up lane, an unknown lane and a PC that said nothing offer nothing`() {
        for (reading in listOf(
            lane(state = ModelLane.UP, canStart = false),
            lane(state = ModelLane.STARTING, canStart = false),
            null,
        )) {
            assertFalse("a button was offered: $reading", ModelLane.offers(reading))
            assertFalse(ModelLane.canPress(reading))
            if (reading == null) assertEquals("", ModelLane.buttonWords(null))
        }
    }

    /**
     * A PC with no such task is down and CANNOT be started from here: the PC
     * says so in `can_start`, and the reason is shown instead of a button. A
     * button that would be refused is worse than none - it is what the owner
     * would press.
     */
    @Test
    fun `a PC with no such task shows the reason and no button`() {
        val none = lane(canStart = false, message = "")
            .copy(task = "", why = "This PC has no scheduled task whose name starts with \"Jarvis Ollama - Everyday model\".")
        assertFalse(ModelLane.offers(none))
        assertEquals("", ModelLane.buttonWords(none))
        assertTrue(none.why.contains("no scheduled task"))
    }

    @Test
    fun `while it is starting the button says so and cannot be pressed again`() {
        val starting = lane(
            state = ModelLane.STARTING,
            canStart = false,
            message = "Starting the local model. It has been 6 seconds; this can take up to a minute.",
        )
        assertEquals(ModelLane.STARTING_WORDS, ModelLane.buttonWords(starting))
        assertFalse(ModelLane.canPress(starting))
        // And a press already being watched cannot be pressed again, whatever
        // the last read said.
        assertFalse(ModelLane.canPress(lane(), busy = true))
        assertEquals(ModelLane.STARTING_WORDS, ModelLane.STARTING_WORDS)
    }

    // ------------------------------------------------------- clearing it ----

    /**
     * THE CHECK THIS FILE EXISTS FOR. A start was asked for, the lane never
     * answered, and nothing may say it did.
     */
    @Test
    fun `a start that does not come up does not clear the warning`() {
        val failed = lane(
            state = ModelLane.DOWN,
            canStart = false,
            message = "The lane did not answer within 90 seconds of its task being started, " +
                "so it did not come up. It is still down.",
        )
        assertFalse("a failed start cleared the warning", ModelLane.clearsWarning(failed, ollamaUp = false))
        assertFalse("a failed start was reported as up", ModelLane.isUp(failed))
        val said = ModelLane.failureWords(failed, ModelLane.UNSETTLED)
        assertTrue(said, said.contains("did not come up"))
        assertFalse("it claimed the model is answering: $said", said.contains("is answering"))
        // And with the PC saying its model is still not running, the standing
        // line stays exactly where it was.
        assertTrue(ModelWords.isDown(false))
        assertEquals(ModelWords.HOME_SUFFIX, ModelWords.homeSuffix(false))
    }

    @Test
    fun `only the lane really answering clears it`() {
        assertTrue(ModelLane.clearsWarning(lane(state = ModelLane.UP, canStart = false), ollamaUp = false))
        // The PC's own `ollama` field is the other half of the same fact: it is
        // the backend's reachability check of the address the chat uses.
        assertTrue(ModelLane.clearsWarning(null, ollamaUp = true))
        // And nothing else does.
        assertFalse(ModelLane.clearsWarning(lane(state = ModelLane.STARTING, canStart = false), ollamaUp = false))
        assertFalse(ModelLane.clearsWarning(lane(), ollamaUp = false))
        assertFalse(ModelLane.clearsWarning(null, ollamaUp = false))
    }

    /**
     * A refusal is the PC's own sentence, not a generic failure: it names the
     * task it could not find, which is the one thing that tells the owner what
     * to fix.
     */
    @Test
    fun `a refusal is shown in the PC's own words`() {
        val said = "This PC has no scheduled task whose name starts with \"Jarvis Ollama - Everyday model\", so there is nothing to start."
        assertEquals(said, ModelLane.failureWords(lane(canStart = false, error = said)))
        assertEquals(
            "The PC would not start it just now. The local model is still not running.",
            ModelLane.failureWords(null, ModelLane.UNREACHED),
        )
        assertTrue(ModelLane.failureWords(null, ModelLane.UNSETTLED).contains("still not running"))
    }

    // ----------------------------------------------------------- the body ----

    /**
     * One empty object, and that is the whole contract: the PC starts the lane
     * IT is pointed at, so no tap can name another lane and nothing can start
     * both at once. There is deliberately no "lane" key and no "all".
     */
    @Test
    fun `the one body this phone sends is empty`() {
        assertTrue(ModelLane.startBody().isEmpty())
        assertEquals("/api/model-lanes", ModelLane.PATH)
        assertEquals("/api/model-lanes/start", ModelLane.START_PATH)
    }

    @Test
    fun `the watch beat and its ceiling are the same numbers on both apps`() {
        assertEquals(2_000L, ModelLane.WATCH_MS)
        // The PC's own limit is ninety seconds; this app outlasts it, so the
        // PC's verdict is what the owner sees rather than this app's guess.
        assertTrue("the phone must outlast the PC's own 90 s", ModelLane.WATCH_LIMIT_MS > 90_000L)
        // The waits it would take: the beat, repeated, and never past its own
        // ceiling.
        val waits = ModelLane.waits(ModelLane.WATCH_LIMIT_MS)
        assertTrue(waits.isNotEmpty())
        assertEquals(ModelLane.WATCH_LIMIT_MS, waits.sum())
        assertTrue(waits.all { it == ModelLane.WATCH_MS })
        assertTrue(ModelLane.waits(0).isEmpty())
    }

    // -------------------------------------------------- the wire and words --

    /**
     * The three readings have to arrive as three different things through the
     * real decoder - not squashed by a default, which would make every lane look
     * startable, or every lane look down.
     */
    @Test
    fun `the lane's three states decode as three different things, through the real decoder`() {
        fun decode(text: String) =
            JarvisJson.decodeFromString(ModelLaneInfo.serializer(), text)

        val down = decode(
            """{"ok":true,"lane":"everyday","port":11436,"state":"down","can_start":true,""" +
                """"task":"Jarvis Ollama - Everyday model (RTX 2060)","why":"Nothing is answering on port 11436."}"""
        )
        assertTrue(ModelLane.offers(down))
        assertEquals(11436, down.port)
        assertEquals("Jarvis Ollama - Everyday model (RTX 2060)", down.task)

        val starting = decode(
            """{"ok":true,"state":"starting","can_start":false,"elapsed_s":6.0,"left_s":84.0,""" +
                """"message":"Starting the local model. It has been 6 seconds."}"""
        )
        assertEquals(ModelLane.STARTING, starting.state)
        assertFalse(ModelLane.offers(starting))
        assertEquals(6.0, starting.elapsedS!!, 0.001)

        val up = decode("""{"ok":true,"state":"up","can_start":false}""")
        assertTrue(ModelLane.isUp(up))
        assertFalse(ModelLane.offers(up))

        // A refusal carries the PC's own sentence and nothing else.
        val refused = decode(
            """{"ok":false,"changed":false,"state":"down","can_start":false,""" +
                """"error":"This PC has no scheduled task whose name starts with \"Jarvis Ollama\"."}"""
        )
        assertFalse(refused.ok)
        assertTrue(refused.error.contains("no scheduled task"))
        assertEquals(refused.error, ModelLane.failureWords(refused))

        // An older backend with none of these fields: not a crash, and not a
        // lane that is down.
        val bare = decode("{}")
        assertEquals(ModelLane.DOWN, bare.state)
        assertFalse(ModelLane.offers(bare))
        assertNull(bare.port)
        assertNull(bare.elapsedS)
    }

    /**
     * The words both apps show, pinned. The desktop's copy is
     * `jarvis-desktop/src/lane-start.js`; `jarvis-desktop/tests/lane-start.mjs`
     * pins its side, and these are the sentences that have to match it.
     */
    @Test
    fun `the button's words are the desktop's own, and promise nothing they cannot do`() {
        assertEquals("Start the local model", ModelLane.START)
        assertFalse("no alarm in the button", ModelLane.START.contains("!"))
        assertFalse("no product name in the button", ModelLane.START.contains("Ollama"))
        assertTrue(ModelLane.STARTING_DETAIL.contains("up to a minute"))
        assertTrue(ModelLane.UNREACHED.contains("still not running"))
        assertTrue(ModelLane.UNSETTLED.contains("still not running"))
        // The line under the button is the PC's own sentence when it sent one,
        // then the seconds it has been, never a made-up "nearly there".
        assertEquals(
            "The local model came back after 21 seconds.",
            ModelLane.detail(lane(state = ModelLane.UP, canStart = false, message = "The local model came back after 21 seconds.")),
        )
        assertTrue(ModelLane.detail(lane(state = ModelLane.STARTING, canStart = false, elapsedS = 6.0)).contains("6 seconds"))
        assertEquals(ModelLane.STARTING_DETAIL, ModelLane.detail(lane(state = ModelLane.STARTING, canStart = false)))
        assertEquals("", ModelLane.detail(lane()))
        assertEquals("", ModelLane.detail(null))
    }

    /**
     * Nothing in this feature builds a command line: the PC runs its own task,
     * and this app names no program. Read from the source, so a well-meaning
     * "just run ollama serve" cannot creep in unnoticed.
     */
    @Test
    fun `this app never builds a command line of its own`() {
        val file = java.io.File("src/main/java/com/jarvis/client/net/ModelLane.kt")
        assertTrue("ModelLane.kt is not where the test expects it", file.isFile)
        val code = file.readText()
            .replace(Regex("""/\*[\s\S]*?\*/"""), "")
            .replace(Regex("""^\s*//.*$""", RegexOption.MULTILINE), "")
        for (verb in listOf("ollama serve", "Start-ScheduledTask", "schtasks", "ProcessBuilder", "Runtime.getRuntime")) {
            assertFalse("ModelLane.kt builds a command line of its own: $verb", code.contains(verb))
        }
    }

    // ------------------------------------------------------------- the UI ---

    /**
     * The screen draws the button from [ModelLane] rather than inventing its own
     * words or its own rule: `HomeScreen.kt`'s `StatusLine` reads `buttonWords`
     * and `canPress`. A screen that wrote its own sentence would pass every
     * check above and still say something different to the owner.
     */
    @Test
    fun `Home's status line draws the button from this one rule`() {
        val home = java.io.File("src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt")
        assertTrue("HomeScreen.kt is not where the test expects it", home.isFile)
        val text = home.readText()
        assertTrue("Home does not draw the button from ModelLane", text.contains("ModelLane"))
        assertTrue("Home does not use the shared button words", text.contains("buttonWords("))
        assertTrue("Home does not use the shared pressability rule", text.contains("canPress("))
        assertTrue("Home does not wire the one action", text.contains("onStartModelLane"))
        // And only while the standing line is drawn.
        assertTrue(text.contains("if (modelDown)"))
    }

    // ------------------------------------- Jarvis restarts it by itself -----

    /**
     * The owner's decision of 2026-10-14: *"Also restart the lane automatically
     * when it dies."* The BACKEND does that - on its own thread, through the
     * same one action as the button - and this phone's job is to BE TOLD, in the
     * PC's own words.
     *
     * A silent automatic restart would be a change to his machine that he did
     * not make, so the failure this half exists to make impossible is a phone
     * that either says nothing about it, or makes up a sentence of its own.
     */

    /** A lane reading with the automatic half filled in, as the PC sends it. */
    private fun autoLane(
        on: Boolean? = true,
        note: String = "",
        capped: Boolean = false,
        attempts: Int = 0,
        state: String = ModelLane.UP,
    ) = ModelLaneInfo(
        lane = "everyday",
        state = state,
        autoNote = note,
        auto = on,
        autoAttempts = attempts,
        autoLimit = 3,
        autoCapped = capped,
    )

    @Test
    fun `the PC's own sentence is drawn verbatim, and nothing is composed here`() {
        val sentence = "Jarvis started the local model again at 08:19, because it was " +
            "not running. It is waiting for it to answer."
        assertEquals(sentence, ModelLane.notice(autoLane(note = sentence)))
        // A lane with nothing to say draws nothing - and never a sentence of the
        // phone's own making.
        assertEquals("", ModelLane.notice(autoLane(note = "")))
        assertEquals("", ModelLane.notice(null))
        assertEquals("", ModelLane.notice(autoLane(note = "   ")))
    }

    @Test
    fun `the capped fallback is the PC's sentence, and the warning stays standing`() {
        val gaveUp = "Jarvis started the local model 3 times and it did not come up, so " +
            "it has stopped trying. You can still start it yourself."
        val info = autoLane(note = gaveUp, capped = true, attempts = 3,
            state = ModelLane.DOWN)
        assertEquals(gaveUp, ModelLane.notice(info))
        assertTrue(info.autoCapped)
        assertEquals(3, info.autoAttempts)
        assertEquals(3, info.autoLimit)
        // The phone never clears the standing line from it: only the lane
        // answering does, or the PC's own `ollama` field.
        assertFalse(ModelLane.clearsWarning(info, ollamaUp = false))
    }

    @Test
    fun `the switch is offered only when the PC reports it, and asks for the opposite`() {
        assertEquals(ModelLane.AUTO_SWITCH_OFF, ModelLane.switchWords(autoLane(on = true)))
        assertEquals(false, ModelLane.switchAsks(autoLane(on = true)))
        assertEquals(ModelLane.AUTO_SWITCH_ON, ModelLane.switchWords(autoLane(on = false)))
        assertEquals(true, ModelLane.switchAsks(autoLane(on = false)))
        // The words themselves, so a change to them is a change this test sees.
        assertEquals("Don't restart it for me", ModelLane.AUTO_SWITCH_OFF)
        assertEquals("Restart it automatically again", ModelLane.AUTO_SWITCH_ON)
    }

    @Test
    fun `an older backend offers no switch at all`() {
        fun decode(text: String) =
            JarvisJson.decodeFromString(ModelLaneInfo.serializer(), text)
        val old = decode("""{"ok":true,"lane":"everyday","state":"down","can_start":true}""")
        assertNull("an absent field became a switch", old.auto)
        assertEquals("", ModelLane.switchWords(old))
        assertNull(ModelLane.switchAsks(old))
        // And a real `false` is not an absent one: the field decodes as a
        // boolean, and that is what draws the "turn it back on" press.
        val off = decode("""{"ok":true,"state":"up","auto":false}""")
        assertEquals(false, off.auto)
        assertEquals(ModelLane.AUTO_SWITCH_ON, ModelLane.switchWords(off))
    }

    @Test
    fun `the automatic half decodes through the real decoder`() {
        fun decode(text: String) =
            JarvisJson.decodeFromString(ModelLaneInfo.serializer(), text)
        val info = decode(
            "{\"ok\":true,\"state\":\"up\",\"auto_note\":\"Jarvis restarted the local " +
                "model by itself at 08:19, and it is answering now.\",\"auto\":true," +
                "\"auto_attempts\":2,\"auto_limit\":3,\"auto_capped\":true}"
        )
        assertEquals(
            "Jarvis restarted the local model by itself at 08:19, and it is answering now.",
            ModelLane.notice(info),
        )
        assertEquals(true, info.auto)
        assertEquals(2, info.autoAttempts)
        assertEquals(3, info.autoLimit)
        assertTrue(info.autoCapped)
    }

    @Test
    fun `the body says the one fact and nothing else`() {
        // One fact about this PC's one lane: no lane name, no "all", so no tap
        // can aim the switch at another lane or at both.
        assertEquals("{\"on\": true}", ModelLane.autoBody(true))
        assertEquals("{\"on\": false}", ModelLane.autoBody(false))
        assertFalse(ModelLane.autoBody(true).contains("lane"))
        assertFalse(ModelLane.autoBody(true).contains("all"))
        assertFalse(ModelLane.autoBody(false).contains("lane"))
        assertEquals(ModelLane.AUTO_PATH, "/api/model-lanes/auto")
    }

    @Test
    fun `a press that never landed says so and claims no change`() {
        assertEquals(ModelLane.AUTO_UNREACHED, ModelLane.autoFailureWords(""))
        assertEquals(ModelLane.AUTO_UNREACHED, ModelLane.autoFailureWords("   "))
        // The PC's own sentence when it sent one - a refusal names what went
        // wrong - and never a softened success.
        val said = "This PC could not write its own setting file, so nothing changed."
        assertEquals(said, ModelLane.autoFailureWords(said))
        assertFalse(ModelLane.AUTO_UNREACHED.contains("is on"))
    }

    @Test
    fun `the two apps say the same two things about the switch`() {
        // The desktop's copy of these words lives in
        // `jarvis-desktop/src/lane-auto.js`, and both apps offer one action on
        // one fact: a phone and a PC disagreeing about what a button does is how
        // the owner presses the wrong thing.
        val js = repoFile("jarvis-desktop/src/lane-auto.js").readText()
        assertTrue(
            "the desktop's AUTO_SWITCH_OFF_WORDS is not this sentence",
            js.contains("export const AUTO_SWITCH_OFF_WORDS = \"${ModelLane.AUTO_SWITCH_OFF}\";"),
        )
        assertTrue(
            "the desktop's AUTO_SWITCH_ON_WORDS is not this sentence",
            js.contains("export const AUTO_SWITCH_ON_WORDS = \"${ModelLane.AUTO_SWITCH_ON}\";"),
        )
        // And the desktop draws the backend's own sentence rather than composing
        // one, exactly as this phone does.
        assertTrue(js.contains("auto_note"))
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): java.io.File {
        var dir: java.io.File? = java.io.File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = java.io.File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    // ------------------------------------------------------- who draws it ---

    @Test
    fun `Home draws the automatic line and its switch from this one rule`() {
        val home = java.io.File("src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt")
        assertTrue("HomeScreen.kt is not where the test expects it", home.isFile)
        val text = home.readText()
        assertTrue("Home does not draw the PC's sentence", text.contains("ModelLane.notice("))
        assertTrue("Home does not read the shared switch words", text.contains("switchWords("))
        assertTrue("Home does not use the shared switch rule", text.contains("switchAsks("))
        assertTrue("Home does not wire the switch", text.contains("onSetLaneAuto"))
        // Its own state, apart from the Start button's failure: one press
        // failing must never be shown as the other's.
        assertTrue(text.contains("laneAutoFailure"))
        assertTrue(text.contains("laneAutoBusy"))
    }

    @Test
    fun `the runtime reads the lane on the beat whether or not the warning is drawn`() {
        // It used to be read only while the standing line was drawn, which is
        // exactly when "the model went down and Jarvis started it again" can
        // never be said: that is news about a lane that has come BACK.
        val runtime = java.io.File("src/main/java/com/jarvis/client/JarvisRuntime.kt")
        assertTrue("JarvisRuntime.kt is not where the test expects it", runtime.isFile)
        val text = runtime.readText()
        assertTrue(
            "the runtime never reads the lane on its beat",
            text.contains("refreshModelLane()"),
        )
        assertFalse(
            "the runtime still reads the lane only while the model is down",
            text.contains("ModelWords.isDown(_status.value?.ollama)"),
        )
        assertTrue("the runtime has no switch action", text.contains("suspend fun setLaneAuto("))
        assertTrue("the switch action does not ask the API", text.contains("api.setModelLaneAuto("))
    }
}
