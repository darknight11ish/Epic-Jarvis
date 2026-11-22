package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The owner's ruling of 2026-11-21 (Gemini's ruling 7; recorded in
 * `decisions.d/2026-11-21-wake-copy-hey-jarvis.md`), verbatim:
 *
 *   "Standardize on `Hey Jarvis` everywhere until `Hey Atlas` actually ships.
 *    Drop `Hey Atlas is in training` from user-facing guides and in-app
 *    Settings copy - users shouldn't read about an unshipped model in daily UI.
 *    Keep the copy simple and factual: 'Wake phrase: Hey Jarvis.'"
 *
 * This is the phone's half of the guard (the desktop's is
 * `jarvis-desktop/tests/wake-copy.mjs`): the two screens that SHOW the wake
 * phrase state it as that factual sentence, and no user-facing phone copy
 * promises a phrase that does not ship. KDoc and comments may explain the
 * history - the ruling allows that - so comments are stripped before scanning.
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
            "Settings no longer says \"Wake phrase: Hey Jarvis.\"",
            settings.contains("\"Wake phrase: Hey Jarvis.\""),
        )
        assertTrue(
            "Platform checks no longer says \"Wake phrase: Hey Jarvis.\"",
            checks.contains("\"Wake phrase: Hey Jarvis.\""),
        )
        assertFalse("Settings still carries the old wake-word title", settings.contains("Wake word - "))
        assertFalse("Platform checks still carries the old wake-word title", checks.contains("Wake word - "))
    }

    /* ── Nothing on the phone promises an unshipped phrase ──────────────── */

    private data class Rule(val re: Regex, val why: String)

    private val forbidden = listOf(
        Rule(
            Regex("(?i)hey atlas"),
            "names a wake phrase the shipped spotter cannot hear (the ruling says Hey Jarvis until the model ships)",
        ),
        Rule(
            Regex("(?i)\\bin training\\b"),
            "tells the owner a model is in training - the ruling drops that from user-facing copy",
        ),
        Rule(
            Regex("(?i)\\bbeing trained\\b"),
            "promises a wake phrase that is still being trained",
        ),
        Rule(
            Regex("(?i)spoken name is atlas"),
            "promises an unshipped spoken name",
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
