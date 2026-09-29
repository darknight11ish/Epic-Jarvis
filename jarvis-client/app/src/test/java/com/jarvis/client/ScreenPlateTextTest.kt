package com.jarvis.client

import com.jarvis.client.net.ScreenPlateText
import org.junit.Assert.assertEquals
import org.junit.Test

class ScreenPlateTextTest {
    private data class App(val pkg: String, val label: String)

    private val apps = listOf(
        App("com.whatsapp", "WhatsApp"),
        App("org.mozilla.firefox", "Firefox"),
        App("com.x.y", "Notes"),
    )

    private fun filter(q: String) = ScreenPlateText.filterApps(apps, q, { it.label }, { it.pkg }).map { it.label }

    @Test fun blankQueryKeepsEverything() {
        assertEquals(listOf("WhatsApp", "Firefox", "Notes"), filter(""))
        assertEquals(listOf("WhatsApp", "Firefox", "Notes"), filter("   "))
    }

    @Test fun matchesNameIgnoringCase() {
        assertEquals(listOf("WhatsApp"), filter("whats"))
        assertEquals(listOf("Firefox"), filter("  FIRE "))
    }

    @Test fun fallsBackToPackageName() {
        assertEquals(listOf("Firefox"), filter("mozilla"))
    }

    @Test fun noMatchGivesEmpty() {
        assertEquals(emptyList<String>(), filter("zzz"))
    }

    @Test fun extendHintOnlyWhenEndingSoon() {
        assertEquals("24 min left", ScreenPlateText.withExtendHint("24 min left"))
        assertEquals(
            "Ending soon - 2 min left. Extend it on the PC.",
            ScreenPlateText.withExtendHint("Ending soon - 2 min left"),
        )
        assertEquals("", ScreenPlateText.withExtendHint(""))
    }

    @Test fun buttonLabelsNameTheApp() {
        assertEquals("Remove Chrome", ScreenPlateText.removeLabel("Chrome"))
        assertEquals("Add Chrome", ScreenPlateText.addLabel("Chrome"))
    }
}
