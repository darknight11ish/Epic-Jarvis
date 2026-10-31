package com.jarvis.client

import com.jarvis.client.net.ModelLane
import com.jarvis.client.ui.SettingsJump
import com.jarvis.client.ui.SettingsSearch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The owner's screenshot of 2026-10-31: the top of Home carried, permanently,
 * a green dot + "Connected", the PC's own paragraph "Jarvis is not starting the
 * local model by itself: automatic restarting is off." AND its "Restart it
 * automatically again" button, then a "History" link. He asked: *"what's with
 * the wording at the top of the screen? it's there all the time and unnecessary.
 * it should be in settings."*
 *
 * This branch moves the automatic-restart sentence and its switch into Settings
 * as "The local model" - it does NOT delete the feature. Home keeps its compact
 * link indicator (the dot and "Connected") and its one-tap History link, and the
 * Start button appears only while the lane is really down.
 *
 * These are source pins, the suite's usual kind (ModelLaneTest, PipTest,
 * SettingsSearchTest): a JVM cannot render Compose, and the repo's own rule is
 * that a claim about a screen is held to the text that draws it. They pin:
 *  1. Home no longer draws the automatic-restart paragraph or switch;
 *  2. Home still draws the compact status words and the History door;
 *  3. Settings draws "The local model" card, from the runtime's own flows;
 *  4. the card keeps the same PC words and the same two calls;
 *  5. Settings search and the jump list both name it, so it stays discoverable;
 *  6. the sentence it explains the switch with is ModelLane's own constant.
 */
class ModelLaneSettingsTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val base = "jarvis-client/app/src/main/java/com/jarvis/client/"
    private val homePath = base + "ui/screens/HomeScreen.kt"
    private val settingsPath = base + "ui/screens/SettingsScreen.kt"
    private val cardPath = base + "ui/screens/ModelLaneSection.kt"

    private fun source(rel: String): String = repoFile(rel).readText()

    /** Source with `//` and `/* */` comments removed, so prose cannot trip a pin. */
    private fun stripComments(src: String): String =
        src.replace(Regex("/\\*[\\s\\S]*?\\*/"), "")
            .replace(Regex("//[^\n]*"), "")

    @Test
    fun `Home no longer draws the automatic-restart wording or its switch`() {
        val home = stripComments(source(homePath))
        assertFalse("Home must not draw the PC's auto-restart sentence",
            home.contains("ModelLane.notice("))
        assertFalse("Home must not draw the auto-restart switch",
            home.contains("ModelLane.switchWords("))
        assertFalse("Home must not ask the switch's question",
            home.contains("ModelLane.switchAsks("))
        // The Start button is NOT the moved paragraph: it appears only while
        // the lane is really down, and it stays on Home.
        assertTrue("the start-the-lane door must stay on Home",
            home.contains("buttonWords("))
        assertTrue("...with its own press", home.contains("onStartModelLane"))
    }

    @Test
    fun `Home keeps its compact status words and its History door`() {
        val home = stripComments(source(homePath))
        assertTrue("Home keeps the compact status row", home.contains("StatusWordsRow("))
        assertTrue("Home keeps its one-tap History door", home.contains("ChatLog.HOME_ENTRY"))
        // The moved sentence is the PARAGRAPH, not the connection state: the
        // owner's own revision kept the dot and the word.
        assertTrue("the connection state stays compact on Home",
            home.contains("ChatLog.HOME_ENTRY_TITLE"))
    }

    @Test
    fun `Settings draws The local model card`() {
        val settings = stripComments(source(settingsPath))
        assertTrue("Settings has no model-lane row",
            settings.contains("item(key = \"model-lane\")"))
        assertTrue("the row does not draw ModelLaneSection",
            settings.contains("ModelLaneSection()"))
        val card = stripComments(source(cardPath))
        assertTrue("the card uses the PC's own sentence", card.contains("ModelLane.notice("))
        assertTrue("the card draws the switch's own words", card.contains("ModelLane.switchWords("))
        assertTrue("the card keeps the same runtime call",
            card.contains("JarvisRuntime.setLaneAuto("))
        assertTrue("the card explains itself with ModelLane's own line",
            card.contains("ModelLane.SECTION_ABOUT"))
        assertTrue("the card reads the lane from the runtime it already uses",
            card.contains("JarvisRuntime.modelLane"))
        // It is a Settings card, not a second Home: no chat, no approval, no
        // new network call of its own.
        for (banned in listOf("sendChat", "JarvisRuntime.decide(", "ApprovalNotifier")) {
            assertFalse("the card must not carry $banned", card.contains(banned))
        }
    }

    @Test
    fun `the moved sentence is the model lane's own constant`() {
        assertEquals(
            "Whether your PC starts the local model again by itself when it dies.",
            ModelLane.SECTION_ABOUT,
        )
        val card = source(cardPath)
        assertTrue("the card's sentence must be the constant, not a copy",
            card.contains("ModelLane.SECTION_ABOUT"))
    }

    @Test
    fun `Settings search and the jump list both find The local model`() {
        val row = SettingsSearch.ROWS.firstOrNull { it.key == "model-lane" }
        assertNotNull("no search row for the moved card", row)
        assertEquals("The local model", row?.title)
        assertTrue("the search row does not name the switch's own words",
            row?.titles?.contains(ModelLane.AUTO_SWITCH_ON) == true)
        assertTrue("the search row does not name the other half of the switch",
            row?.titles?.contains(ModelLane.AUTO_SWITCH_OFF) == true)
        val jump = source(base + "ui/SettingsJump.kt")
        assertTrue("the jump list has no entry for the moved card",
            jump.contains("Entry(\"The local model\", \"model-lane\")"))
        val open = source(base + "ui/OpenPlace.kt")
        assertTrue("\"open the local model\" has no phone decision",
            open.contains("\"model-lane\" to Where.Go(Screen.SETTINGS, \"model-lane\")"))
    }

    @Test
    fun `the switch still asks the PC and never claims the change itself`() {
        val card = source(cardPath)
        assertTrue("the card must ask through the switch words' own rule",
            card.contains("ModelLane.switchAsks("))
        // The PC's answer is the new reading (JarvisRuntime.setLaneAuto does
        // that); this card composes no success sentence of its own.
        assertFalse("the card must not claim automatic restarting was changed",
            card.contains("was turned"))
        assertFalse("the card must not draw its own success line",
            card.contains("is on now"))
    }
}
