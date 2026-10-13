package com.jarvis.client

import com.jarvis.client.net.PlainErrors
import com.jarvis.client.ui.MenuPlaces
import com.jarvis.client.ui.screens.BrainSections
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Choose a model" must land on the Models plate, and the Models plate must
 * stay the phone's two allowed halves.
 *
 * The owner, 2026-10-13: "when its prompting me on the android app to select
 * an AI model jarvis uses because its not installed on my pc ... selecting
 * choose a model doesn't take me to a list to actually choose from".
 *
 * WHY IT DEAD-ENDED, measured: the button's action was `onOpenBrain`, which is
 * `nav.go(Screen.BRAIN)` (MainActivity.kt) - the Brain's front door, with no
 * `pendingSection`. The Models plate is not on the Brain's first screen: it is
 * the first plate of the LAST heading, "Jarvis on your PC"
 * (BrainSections.kt, `Section(key = "pc", plates = listOf(Plate("models", ...)))`),
 * behind its own menu (`menus.shows("brain.model.models")`, BrainScreen.kt).
 * Nothing was missing, nothing threw and no list was empty - the destination
 * was simply never named. The fix names it, the same way "open the galaxy" and
 * every "open <a place>" link already do.
 *
 * THE RULE THE NEXT READER MUST NOT "FIX", quoted from the owner's standing
 * decision (CLAUDE.md, amended 2026-09-20): **browsing models on the phone is
 * deliberately OFF** - "there is no catalogue to scroll or search, no list of
 * what could be installed, only of what already is. The owner types the name by
 * hand, the same as at a terminal (`ollama pull <ref>`)". What IS allowed:
 * switching between the models the PC already has (`/api/models/switch`, which
 * raises an approval card), and installing BY TYPED REFERENCE
 * (`/api/models/install`, tier `ask`, nothing downloading until that card is
 * approved). The last test in this file fails if a catalogue route ever appears
 * on the phone, so the button cannot quietly become one.
 */
class ModelPromptTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    @Test
    fun theButtonGoesToTheModelsPlateAndNotToTheBrainsFrontDoor() {
        val home = repoFile("$main/ui/screens/HomeScreen.kt").readText()
        assertTrue(
            "the model_missing notice no longer opens the model choices",
            home.contains("PlainErrors.MODELS -> actions.onOpenModelChoices"),
        )
        assertFalse(
            "it still opens the Brain's front door, which is the dead end the " +
                "owner reported",
            home.contains("PlainErrors.MODELS -> actions.onOpenBrain"),
        )

        // And the destination it names must be the plate, not another screen.
        val activity = repoFile("$main/MainActivity.kt").readText()
        val block = activity.substringAfter("onOpenModelChoices = {").substringBefore("\n                                },")
        assertTrue("no models jump in MainActivity", block.isNotBlank())
        assertTrue(
            "the jump does not name the models plate:\n$block",
            block.contains("pendingSection = \"models\""),
        )
        assertTrue(
            "the jump does not name the screen the section belongs to:\n$block",
            block.contains("pendingSectionScreen = Screen.BRAIN.name"),
        )
        assertTrue("the jump does not open the Brain:\n$block", block.contains("nav.go(Screen.BRAIN)"))
        assertTrue(
            "a hidden Models menu is never shown for the visit, so the jump " +
                "lands on a heading with the plate missing:\n$block",
            block.contains("showForVisit"),
        )
    }

    @Test
    fun thePlaceAndTheMenuAreTheOnesTheBrainReallyDraws() {
        // Real calls, not text: the heading that holds the plate, and the menu
        // id the screen guards it with.
        assertEquals("brain.model.models", MenuPlaces.BRAIN["models"])
        assertEquals("pc", BrainSections.sectionOf("models")?.key)
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        // Two facts, checked separately: the screen draws a plate named
        // "models", and it is guarded by the menu the place maps to. (The one
        // line is `if (menus.shows("brain.model.models")) plate("models", ...)`
        // - a single string match across both would have been an assertion
        // about the punctuation between them, and it failed on exactly that
        // the first time this test ran.)
        assertTrue(
            "BrainScreen no longer draws a plate named \"models\"",
            brain.contains("plate(\"models\""),
        )
        assertTrue(
            "the Models plate is no longer behind the menu MenuPlaces names",
            brain.contains("menus.shows(\"brain.model.models\")"),
        )
    }

    @Test
    fun thePlateStillOffersBothAllowedHalves() {
        val brain = repoFile("$main/ui/screens/BrainScreen.kt").readText()
        val plate = brain.substringAfter("private fun ModelsPlate(")
            .substringBefore("private fun LiveModelsBody(")
        assertTrue("the plate no longer offers the PC's own models", plate.contains("onSwitch"))
        assertTrue(
            "the plate lost the box to type a model's name",
            plate.contains("placeholder = \"model:tag\""),
        )
        assertTrue("the typed name is no longer sent to install", plate.contains("onInstall(installRef)"))
        // The catalogue rule, in the plate's own words, so a later reader meets
        // it before changing anything.
        assertTrue(brain.contains("The catalogue is still not allowed"))
    }

    @Test
    fun noCatalogueRouteExistsOnThePhone() {
        // The guard on the rule above. Listing what COULD be installed is the
        // one thing the phone is not allowed to do; the routes it may use are
        // the PC's own models (`/api/models`), a switch and a typed install.
        val api = repoFile("$main/net/JarvisApi.kt").readText()
        for (route in listOf(
            "/api/models/available",
            "/api/models/catalogue",
            "/api/models/search",
            "/api/models/remote",
        )) {
            assertFalse("a browsable model catalogue appeared on the phone: $route", api.contains(route))
        }
        assertTrue("the switch route is gone", api.contains("/api/models/switch"))
        assertTrue("the typed-install route is gone", api.contains("/api/models/install"))
    }

    @Test
    fun theNoticesOwnWordsStillSayWhatTheButtonDoes() {
        // The words are shared with the desktop and pinned by the contract
        // file, so this only checks the phone still reads that mapping: a
        // model_missing failure offers the model choices, and says in its fix
        // that it may need typing the name rather than choosing.
        assertEquals("models", PlainErrors.MODELS)
        assertEquals("Choose a model", PlainErrors.BUTTONS[PlainErrors.MODELS])
        val kind = PlainErrors.KINDS.getValue("model_missing")
        assertEquals(PlainErrors.MODELS, kind.action)
        assertTrue("the fix no longer mentions installing one", kind.fix.contains("install"))
    }
}
