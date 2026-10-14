package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * [ModelWords], and the two halves of the phone that draw it: the `ollama`
 * field on `/api/status`, and Home's own status line.
 *
 * The defect this is written against, measured on the owner's PC on
 * 2026-10-13: both of his Ollama lanes were dead from about 16:30 until about
 * 21:5x, and this app looked normally connected the whole time. `GET
 * /api/status` carried `"ollama": false` from the first minute - the phone was
 * already asking for that route - and its `StatusInfo` had no field to put it
 * in, so the fact arrived and was thrown away. Jarvis only admitted it when the
 * owner asked a question and the answer came back `model_not_running`.
 *
 * Every check here is one of three things: the words themselves, the rule for
 * when they are drawn, or a pin on the source that draws them - because the
 * first two pass just as happily against a screen that never calls them.
 */
class ModelWordsTest {

    // ------------------------------------------------------------- the rule --

    @Test
    fun `only the PC saying its model is down draws the warning`() {
        assertTrue(ModelWords.isDown(false))
        assertEquals(ModelWords.HOME_SUFFIX, ModelWords.homeSuffix(false))
    }

    /**
     * CONTROL. This is the half of the rule that keeps the warning worth
     * reading. `null` is not "down": it is an older backend with no such field,
     * or a read that never landed - and a line drawn from either would be the
     * app telling the owner something the PC never said. The first time it
     * cries wolf over nothing is the last time he believes it.
     */
    @Test
    fun `a model that is up, and a PC that said nothing, draw nothing`() {
        assertFalse(ModelWords.isDown(true))
        assertNull(ModelWords.homeSuffix(true))

        assertFalse("an absent field is not a down lane", ModelWords.isDown(null))
        assertNull(ModelWords.homeSuffix(null))
    }

    /**
     * The field is `status()`'s own, so the three readings have to arrive as
     * three different things through the real decoder - not squashed by a
     * default of `false`, which would have made every backend that has never
     * sent the field report a dead lane.
     *
     * Read through [com.jarvis.client.net.JarvisJson], the instance the API
     * client actually uses, not a decoder invented here.
     */
    @Test
    fun `the status field decodes as three different things`() {
        val json = com.jarvis.client.net.JarvisJson
        fun decode(text: String) =
            json.decodeFromString(com.jarvis.client.net.StatusInfo.serializer(), text)

        assertEquals(false, decode("""{"ollama":false}""").ollama)
        assertEquals(true, decode("""{"ollama":true}""").ollama)
        assertNull("a backend with no such field", decode("""{"power":"active"}""").ollama)
        assertNull("a field that is null", decode("""{"ollama":null}""").ollama)
        assertNull("an empty body", decode("{}").ollama)

        // And the older fields still decode beside it.
        val both = decode("""{"power":"quiet","activity":"idle","ollama":false}""")
        assertEquals("quiet", both.power)
        assertEquals(false, both.ollama)
    }

    /**
     * A field that is not a boolean at all: the decode fails, so `status()`
     * returns a failure and the app keeps the last reading. It must NOT be read
     * as a down lane - that would put a warning on screen out of a value the PC
     * never sent.
     */
    @Test
    fun `a field that is not a boolean cannot become a down lane`() {
        val threw = try {
            com.jarvis.client.net.JarvisJson.decodeFromString(
                com.jarvis.client.net.StatusInfo.serializer(),
                """{"ollama":"yes"}""",
            )
            false
        } catch (e: Exception) {
            true
        }
        assertTrue("a non-boolean was accepted as a model state", threw)
    }

    // ------------------------------------------------------------ the words --

    /**
     * Calm and plain, and not "Jarvis isn't connected": the PC IS answering
     * here, and saying otherwise would send the owner to fix the wrong thing.
     */
    @Test
    fun `the warning is not the link's words`() {
        assertFalse(ModelWords.DOWN.contains("isn't connected"))
        assertFalse(ModelWords.HOME_SUFFIX.contains("Offline", ignoreCase = true))
        // No alarm. A dead lane is not a crash, and the app carries on.
        assertFalse(ModelWords.DOWN.contains("!"))
        assertFalse(ModelWords.HOME_SUFFIX.contains("!"))
        // It says what to do, in the words he already uses at a terminal.
        assertTrue(ModelWords.DOWN.contains("ollama serve"))
    }

    /** The suffix is a suffix: no stop, and no second sentence on a status line. */
    @Test
    fun `the home suffix is a fragment, not a sentence`() {
        assertFalse(ModelWords.HOME_SUFFIX.contains("."))
        assertTrue(ModelWords.HOME_SUFFIX.length < 30)
    }

    /**
     * The desktop says the same thing, and this is the pin that stops the two
     * apps from drifting into two wordings for one fact. That file cannot be
     * imported from here, so the sentence is read out of it.
     */
    @Test
    fun `the desktop's sentence is the same sentence`() {
        val js = repoFile("jarvis-desktop/src/lane-warning.js").readText()
        val sentence = ModelWords.DOWN.substringBefore(" Open Ollama")
        assertTrue(
            "the desktop's LANE_DOWN_WORDS is not this sentence",
            js.contains("export const LANE_DOWN_WORDS = \"$sentence\";"),
        )
    }

    // ------------------------------------------------------ who draws it ----

    /**
     * Home is where the owner looks without navigating, so the warning is drawn
     * on its always-visible status line - and it is drawn from the PC's field,
     * never from a hardcoded string that would stand there for ever.
     */
    @Test
    fun `Home draws the warning from the PC's own field`() {
        val home = repoFile("$main/ui/screens/HomeScreen.kt").readText()
        assertTrue(
            "Home no longer reads StatusInfo.ollama",
            home.contains("ModelWords.isDown(state.status?.ollama)"),
        )
        assertTrue(
            "Home builds its status line without the model warning",
            home.contains("ModelWords.homeSuffix(state.status?.ollama)"),
        )
        // A live link with a dead model must not keep the all-is-well tone.
        assertTrue(
            "a dead model on a live link is still drawn as all-is-well",
            home.contains("modelDown -> chrome.warnInk"),
        )
    }

    /**
     * And something has to ask again. Before this, `ollama` was only ever read
     * when a power, activity or persona event happened to bring a
     * `refreshStatus()` with it - which on a quiet PC is nothing at all, and is
     * how five hours went by unnoticed. The beat is the whole fix.
     */
    @Test
    fun `something asks again on a beat`() {
        val runtime = repoFile("$main/JarvisRuntime.kt").readText()
        assertTrue(
            "nothing re-reads the model state",
            runtime.contains("refreshModelState()"),
        )
        assertTrue(
            "the beat does not use ModelWords' own interval",
            runtime.contains("ModelWords.POLL_MS"),
        )
        assertTrue("the beat is longer than the watchdog's own tick", ModelWords.POLL_MS > 10_000)
        assertTrue("the beat is at most a couple of minutes", ModelWords.POLL_MS <= 120_000)
        // And it never asks a PC that is not there: that is the link line's job.
        assertTrue(
            "the model beat runs on a link that is down",
            runtime.contains(
                "suspend fun refreshModelState() {\n" +
                    "        if (_link.value != LinkState.CONNECTED) return",
            ),
        )
    }

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client"
}
