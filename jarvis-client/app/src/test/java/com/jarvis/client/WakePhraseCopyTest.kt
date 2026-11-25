package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The owner's ruling of 2026-11-25 (recorded in
 * `decisions.d/2026-11-25-hey-atlas-wake-model-ships.md`), which is the step
 * the 2026-11-21 ruling left open, in the owner's own words:
 *
 *   "Once the custom Hey Atlas model passes local false-accept testing, swap
 *    the string in one PR."
 *
 * The model passed and it ships with the PC (`backend/wakeword/hey_atlas.onnx`),
 * so the copy says "Hey Atlas" and this suite REQUIRES it. What it still
 * forbids is the wording that would still be false: any claim that a wake
 * phrase is "in training" or "being trained", and the old factual sentence
 * coming back.
 *
 * This is the phone's half of the guard (the desktop's is
 * `jarvis-desktop/tests/wake-copy.mjs`): the two screens that SHOW the wake
 * phrase state it as that factual sentence, and no user-facing phone copy
 * promises a phrase that does not ship. KDoc and comments may explain the
 * history - the ruling allows that - so comments are stripped before scanning.
 *
 * ONE-SIDED, AND SAID SO: the phone's OWN listener still runs openWakeWord's
 * `hey_jarvis` model (`assets/wakeword/`), so the sentences that describe what
 * THIS PHONE hears keep saying "hey jarvis" on purpose - changing them would be
 * the false claim. `docs/ARCHITECTURE.md` section 8 records why the phone was
 * not rebuilt in the same change.
 */
class WakePhraseCopyTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun text(rel: String): String = SourceFile.read(main + rel)

    /** The file's code only: its own docs explain the history in words. */
    private fun code(raw: String): String = raw.lines().joinToString("\n") { line ->
        val t = line.trimStart()
        when {
            t.startsWith("//") || t.startsWith("*") || t.startsWith("/*") -> ""
            else -> line.substringBefore(" //")
        }
    }

    private fun xmlText(raw: String): String = raw.replace(Regex("<!--[\\s\\S]*?-->"), "")

    /* ── The sentence where the phrase is shown ─────────────────────────── */

    @Test
    fun `Settings and Platform checks state the wake phrase as the ruling's factual sentence`() {
        val settings = code(text("ui/screens/VoiceSwitchesPlate.kt"))
        val checks = code(text("ui/screens/ReadinessScreen.kt"))
        assertTrue(
            "Settings no longer says \"Wake phrase: Hey Atlas.\"",
            settings.contains("\"Wake phrase: Hey Atlas.\""),
        )
        assertTrue(
            "Platform checks no longer says \"Wake phrase: Hey Atlas.\"",
            checks.contains("\"Wake phrase: Hey Atlas.\""),
        )
        assertFalse("Settings still carries the old wake-word title", settings.contains("Wake word - "))
        assertFalse("Platform checks still carries the old wake-word title", checks.contains("Wake word - "))
    }

    /* ── Nothing on the phone promises a phrase that does not ship ──────── */

    private data class Rule(val re: Regex, val why: String)

    private val forbidden = listOf(
        Rule(
            Regex("(?i)\\bin training\\b"),
            "tells the owner a model is in training - nothing is: the model shipped on 2026-11-25",
        ),
        Rule(
            Regex("(?i)\\bbeing trained\\b"),
            "promises a wake phrase that is still being trained - it shipped on 2026-11-25",
        ),
        Rule(
            Regex("(?i)wake phrase:\\s*hey jarvis"),
            "states the old phrase as the factual sentence; it is \"Wake phrase: Hey Atlas.\" now",
        ),
    )

    @Test
    fun `no user-facing phone copy names an unshipped wake phrase or a model in training`() {
        // Every source a person can read on this phone: the Compose screens and
        // their modules, the resource strings, and the feature list the phone
        // shows. The walk starts at the app's own main source folder.
        val appRoot = repoFile(main + "ui/screens/VoiceSwitchesPlate.kt").parentFile!!.parentFile!!.parentFile!!
        val copyFiles = buildList {
            addAll(appRoot.walkTopDown().filter { it.isFile && it.extension == "kt" }.toList())
            add(repoFile("jarvis-client/app/src/main/res/values/strings.xml"))
            add(repoFile("jarvis-client/app/src/main/assets/features.json"))
        }
        assertTrue("the walk found almost nothing - it is broken", copyFiles.size > 100)

        val problems = mutableListOf<String>()
        for (file in copyFiles) {
            val raw = file.readText()
            val shown = when (file.extension) {
                "xml" -> xmlText(raw)
                "json" -> raw
                else -> code(raw)
            }
            shown.lines().forEachIndexed { index, line ->
                for (rule in forbidden) {
                    if (rule.re.containsMatchIn(line)) {
                        problems += "${file.relativeTo(appRoot.parentFile!!.parentFile!!.parentFile!!)}:${index + 1} - ${rule.why}\n        ${line.trim()}"
                    }
                }
            }
        }
        assertTrue("the ruling is broken in user-facing copy:\n      ${problems.joinToString("\n      ")}", problems.isEmpty())
    }
}
