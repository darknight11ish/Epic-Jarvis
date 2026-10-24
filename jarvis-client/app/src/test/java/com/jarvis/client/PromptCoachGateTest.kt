package com.jarvis.client

import com.jarvis.client.net.PromptCoach
import com.jarvis.client.ui.screens.coachBarShown
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The "Coach this" bar's gate (the 2026-10-24 round-2 audit, H1).
 *
 * The bar used to `return` while the PC's switch was ON, so the feature
 * disappeared in the one state it exists for and appeared in the state where
 * the PC can only refuse it ("The prompt coach is switched off.",
 * `backend/jarvis_prompt_coach.py:1220`; `on` is the `enabled` switch, parsed
 * from `body.flag("on")` and written back as `{"enabled": on}`).
 *
 * The one rule is [coachBarShown] and these tests hold it and the bar's use.
 * The bar is a Compose function, so there is no JVM host to drive it - the same
 * source-pin approach `ExpiredCardShowsNoButtonsTest` and `OpenPlaceTest` use.
 * The phone's real look and TalkBack order stay a NOT-TESTABLE field-test row.
 */
class PromptCoachGateTest {

    private fun view(on: Boolean, routeKnown: Boolean = true) = PromptCoach.View(
        on = on,
        why = "",
        label = "Coach",
        detail = "",
        heading = "",
        button = "Coach this",
        sendMine = "",
        sendSuggestion = "",
        routeKnown = routeKnown,
    )

    @Test
    fun theBarIsDrawnWithTheSwitchOnAndHiddenWithItOff() {
        assertTrue(
            "the bar is hidden while the prompt coach is ON - the inverted gate is back",
            coachBarShown(view(on = true)),
        )
        assertFalse(
            "nothing is drawn for a coach that is simply off",
            coachBarShown(view(on = false)),
        )
    }

    @Test
    fun nothingIsDrawnBeforeThePcHasAnswered() {
        assertFalse("a null view draws the bar", coachBarShown(null))
    }

    @Test
    fun aPcWithNoCoachAtAllIsStillSaidInWords() {
        // absentView() has on = false and routeKnown = false; its MISSING line
        // is drawn through this same bar, and hiding it would be a silent gap
        // where the owner expected to be told why there is no button.
        assertFalse("absentView() unexpectedly claims the coach is on", PromptCoach.absentView().on)
        assertTrue(
            "an older PC's MISSING line is no longer drawn",
            coachBarShown(PromptCoach.absentView()),
        )
    }

    @Test
    fun theNoRouteSentenceWinsOverAContradictorySwitch() {
        // Need not happen in practice (a PC with no route sends no switch), but
        // the bar must still say "this PC has no prompt coach" rather than hide
        // on a value it cannot trust - the same reason `absentView()` exists.
        assertTrue(
            "a route-less answer with on=true hides the MISSING line",
            coachBarShown(view(on = true, routeKnown = false)),
        )
    }

    @Test
    fun theBarReallyAsksThatOneRule() {
        val bar = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/PromptCoachBar.kt",
        ).readText()
        assertTrue(
            "the bar no longer asks the one gate",
            bar.contains("if (!coachBarShown(view)) return"),
        )
        assertFalse(
            "the old inverted gate is back (it returns while the switch is ON)",
            bar.contains("if (v == null || v.on) return"),
        )
        // It is still drawn from Home.
        val home = repoFile(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt",
        ).readText()
        assertTrue("Home no longer draws the coach bar", home.contains("PromptCoachBar("))
    }

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
