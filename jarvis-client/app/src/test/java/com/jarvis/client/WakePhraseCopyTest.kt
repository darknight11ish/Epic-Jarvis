package com.jarvis.client

import org.junit.Assert.assertEquals
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
 * and **since 2026-11-25 the phone carries the same file**:
 * `assets/wakeword/hey_atlas.onnx`, named by `OrtWakeModels.WAKE_FILE` and
 * scored by the phone's own spotter. So the copy says "Hey Atlas" and this
 * suite REQUIRES it, on both surfaces it can read: the two plates that state
 * the phrase (Settings' `VoiceSwitchesPlate` and Platform checks'
 * `ReadinessScreen`) - the same two sentences the desktop's
 * `jarvis-desktop/tests/wake-copy.mjs` checks on its side.
 *
 * What it still forbids is the wording that would still be false: any claim
 * that a wake phrase is "in training" or "being trained", the old factual
 * sentence coming back, and any sentence saying THIS PHONE hears "hey jarvis"
 * now that its own model hears "Atlas".
 *
 * KDoc and comments may explain the history - the ruling allows that - so
 * comments are stripped before scanning. One file is scanned for the forbidden
 * wording but never held to the phrase: `assets/features.json`, which is
 * generated from `features/features.json` and must stay byte-identical to it
 * (`tools/check_feature_list.py`), so renaming the wake-word row is a change to
 * that source, not to the phone's copy.
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

    /* ── What THIS PHONE's own listener hears ───────────────────────────── */

    /**
     * The phone's own copy promised "Hey Atlas" while its assets carried only
     * openWakeWord's `hey_jarvis` model - the one-sided gap of 2026-11-25.
     * Both halves have moved together now, so the model the copy promises and
     * the sentences that describe this phone's listening are held to each
     * other: if either drifts back, this fails.
     */
    @Test
    fun `this phone's own listening copy names the phrase its shipped model hears`() {
        val models = code(text("voice/OrtWakeModels.kt"))
        assertTrue(
            "OrtWakeModels.WAKE_FILE no longer loads the atlas head - the copy below would be false",
            models.contains("WAKE_FILE = \"hey_atlas.onnx\""),
        )
        val settings = code(text("ui/screens/VoiceSwitchesPlate.kt"))
        assertTrue(
            "Settings' phone line no longer says the phone waits until it hears \"Hey Atlas\"",
            settings.contains("""the phone until it hears \"Hey Atlas\""""),
        )
        assertTrue(
            "Settings' phone line no longer says it heard \"Hey Atlas\"",
            settings.contains("""Heard \"Hey Atlas\" - listening to what you say next."""),
        )
        val resume = code(text("data/WakeResume.kt"))
        assertTrue(
            "the restart notice no longer names \"Hey Atlas\" as what is off",
            resume.contains("\"\\\"Hey Atlas\\\" is off since the phone restarted\""),
        )
        assertTrue(
            "the back-on line no longer says listening for \"Hey Atlas\"",
            resume.contains("\"Listening for \\\"Hey Atlas\\\" on this phone again.\""),
        )
        val strings = xmlText(SourceFile.read("jarvis-client/app/src/main/res/values/strings.xml"))
        for (name in listOf("channel_wake_name", "channel_wake_desc", "wake_listening_title",
                            "wake_listening_text", "wake_heard_text")) {
            // A string may wrap over several source lines, so read the whole
            // <string name="..."> ... </string> block, not one line of it.
            val at = strings.indexOf("<string name=\"$name\">")
            assertTrue("$name is gone from strings.xml", at >= 0)
            val block = strings.substring(at).substringBefore("</string>")
            assertTrue(
                "$name no longer names \"Hey Atlas\": $block",
                block.contains("""\"Hey Atlas\""""),
            )
        }
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
        Rule(
            Regex("(?i)hears\\s*\\\\?\"hey jarvis"),
            "says THIS PHONE hears \"hey jarvis\"; its own model hears \"Hey Atlas\"",
        ),
        Rule(
            Regex("(?i)heard\\s*\\\\?\"hey jarvis"),
            "says THIS PHONE heard \"hey jarvis\"; its own model hears \"Hey Atlas\"",
        ),
        Rule(
            Regex("(?i)listening (?:for|to)\\s*\\\\?\"hey jarvis"),
            "says THIS PHONE listens for \"hey jarvis\"; its own model hears \"Hey Atlas\"",
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
        assertEquals("the ruling is broken in user-facing copy:\n      ${problems.joinToString("\n      ")}",
            emptyList<String>(), problems)
    }
}
