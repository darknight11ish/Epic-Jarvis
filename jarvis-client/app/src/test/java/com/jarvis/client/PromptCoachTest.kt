package com.jarvis.client

import com.jarvis.client.net.DesktopWrite
import com.jarvis.client.net.PromptCoach
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The prompt coach on the phone (docs/PROMPT-COACH-DESIGN.md;
 * `net/PromptCoach.kt`, `ui/screens/PromptCoachPlate.kt`,
 * `ui/screens/PromptCoachBar.kt`; backend `jarvis_prompt_coach.py`).
 *
 * WHAT THIS COVERS, and why it is here rather than in a hand-written fixture:
 * the four settings that arrived on 2026-10-09 (when it speaks up, how blunt
 * it is, what it coaches on, per-platform behaviour) and the per-AI notes that
 * came with them. Every one of their names and lines is the PC's, so the
 * payloads below are the SHAPE `jarvis_prompt_coach.status()` and `.parse()`
 * really write - key for key, including `targets` and `stale_days` - and the
 * checks are that this side reads them without inventing a word of its own.
 *
 * A PC that answers with none of it (an older backend) must draw the switch
 * alone: that is the last two checks, and it is the case a hand-written
 * fixture would have quietly missed.
 */
class PromptCoachTest {

    private fun view(
        on: Boolean = true,
        settings: kotlinx.serialization.json.JsonArray? = null,
        targets: kotlinx.serialization.json.JsonArray? = null,
    ): JsonObject = buildJsonObject {
        put("ok", true)
        put("on", on)
        put("why", "")
        put("label", "Prompt coach")
        put("detail", "Off (the default): nothing is read and there is no Coach this button.")
        put("heading", "Prompt coach")
        put("button", "Coach this")
        put("send_mine", "Send mine")
        put("send_suggestion", "Send the suggestion")
        if (settings != null) put("settings", settings)
        if (targets != null) put("targets", targets)
        put("stale_days", 180)
    }

    /** The four, exactly as `jarvis_prompt_coach.settings_rows()` builds them. */
    private val settings = Json.parseToJsonElement(
        """
        [
          {"key": "speaks_up", "name": "when it speaks up", "names": ["when it speaks up"],
           "value": "any", "default": "any",
           "choices": [
             {"value": "any", "name": "Whenever it has something to say", "detail": "Every gap."},
             {"value": "weak", "name": "Only when the prompt is weak", "detail": "7 or more is passed."}]},
          {"key": "bluntness", "name": "how blunt it is", "names": ["how blunt it is"],
           "value": "gentle", "default": "gentle",
           "choices": [
             {"value": "gentle", "name": "A gentle nudge", "detail": "Suggestions."},
             {"value": "direct", "name": "Direct about what is wrong", "detail": "Said plainly."}]},
          {"key": "coaches_on", "name": "what it coaches on", "names": ["what it coaches on"],
           "value": "shape", "default": "shape",
           "choices": [
             {"value": "shape", "name": "Shape only - length and clarity", "detail": "How it is built."},
             {"value": "content", "name": "Content too", "detail": "And the right task."}]},
          {"key": "platform", "name": "per-platform behaviour", "names": ["per-platform behaviour"],
           "value": "same", "default": "same",
           "choices": [
             {"value": "same", "name": "The phone behaves the same as the PC", "detail": "One setting."},
             {"value": "quieter_phone", "name": "Quieter on the phone", "detail": "Two gaps at most."}]}
        ]
        """.trimIndent(),
    ) as kotlinx.serialization.json.JsonArray

    // ---- The switch and the four settings beside it (2026-10-09) -----------

    @Test
    fun theFourSettingsAreReadInThePcsOwnWords() {
        val v = PromptCoach.parse(view(settings = settings))!!
        assertEquals(
            listOf("speaks_up", "bluntness", "coaches_on", "platform"),
            v.settings.map { it.key },
        )
        assertEquals("when it speaks up", v.settings[0].name)
        assertEquals("any", v.settings[0].value)
        assertEquals(
            listOf("any", "weak"),
            v.settings[0].choices.map { it.value },
        )
        assertEquals("Only when the prompt is weak", v.settings[0].choices[1].name)
        assertEquals("7 or more is passed.", v.settings[0].choices[1].detail)
        assertEquals("A gentle nudge", v.settings[1].choices[0].name)
        assertEquals("Content too", v.settings[2].choices[1].name)
        assertEquals("Quieter on the phone", v.settings[3].choices[1].name)
        // The list of AIs Jarvis has notes for rides with them.
        assertEquals(
            listOf("local", "openai_api"),
            PromptCoach.parse(
                view(
                    settings = settings,
                    targets = Json.parseToJsonElement("""["local","openai_api"]""")
                        as kotlinx.serialization.json.JsonArray,
                ),
            )!!.targets,
        )
    }

    @Test
    fun aHalfWrittenRowIsDroppedRatherThanDrawnAsAnEmptyPicker() {
        // No key, no choices, no current value, or a value that is not one of
        // its own choices: not a control this screen can draw.
        val broken = Json.parseToJsonElement(
            """
            [
              {"name": "no key", "value": "a", "choices": [{"value": "a"}]},
              {"key": "empty", "value": "a", "choices": []},
              {"key": "novalue", "choices": [{"value": "a"}]},
              {"key": "wrong", "value": "z", "choices": [{"value": "a"}]},
              {"key": "good", "name": "kept", "value": "a", "choices": [{"value": "a"}]}
            ]
            """.trimIndent(),
        ) as kotlinx.serialization.json.JsonArray
        val v = PromptCoach.parse(view(settings = broken))!!
        assertEquals(listOf("good"), v.settings.map { it.key })
        // A choice with no name falls back to its own value, never to a blank.
        val unnamed = Json.parseToJsonElement(
            """[{"key": "k", "value": "a", "choices": [{"value": "a"}]}]""",
        ) as kotlinx.serialization.json.JsonArray
        assertEquals("a", PromptCoach.parse(view(settings = unnamed))!!.settings[0].choices[0].name)
    }

    @Test
    fun anOlderPcDrawsNoPickersAndStillWorks() {
        val old = PromptCoach.parse(view(settings = null))!!
        assertEquals(emptyList<String>(), old.settings)
        assertEquals(emptyList<String>(), old.targets)
        assertTrue(old.on)
        assertTrue(old.routeKnown)
    }

    @Test
    fun oneSettingMovesThroughItsOwnBodyAndNoOther() {
        assertEquals(
            """{"key":"bluntness","value":"direct"}""",
            PromptCoach.choiceBody("bluntness", "direct"),
        )
        // A quote or a backslash in a value cannot break out of its field.
        assertEquals(
            """{"key":"bluntness","value":"a\"b"}""",
            PromptCoach.choiceBody("bluntness", "a\"b"),
        )
        // The line after the change is the PC's own row and choice - and the
        // PC sends the whole state back, so it is read from that. It names the
        // value the PC HAS, not the one that was asked for: a page that kept
        // its own copy of the request would say "direct" over a state that had
        // stayed "gentle".
        val after = PromptCoach.parse(view(settings = settings))!!
        assertEquals(
            "how blunt it is: A gentle nudge.",
            PromptCoach.saidChoice("bluntness", DesktopWrite.Outcome.Done(null), after),
        )
        val moved = PromptCoach.parse(
            view(
                settings = Json.parseToJsonElement(
                    """
                    [{"key": "bluntness", "name": "how blunt it is", "value": "direct",
                      "default": "gentle",
                      "choices": [
                        {"value": "gentle", "name": "A gentle nudge", "detail": "Suggestions."},
                        {"value": "direct", "name": "Direct about what is wrong", "detail": "Said plainly."}]}]
                    """.trimIndent(),
                ) as kotlinx.serialization.json.JsonArray,
            ),
        )!!
        assertEquals(
            "how blunt it is: Direct about what is wrong.",
            PromptCoach.saidChoice("bluntness", DesktopWrite.Outcome.Done(null), moved),
        )
        // A PC whose answer has no such row says something true rather than
        // naming a setting it does not know.
        assertEquals(
            "Changed.",
            PromptCoach.saidChoice("wittiness", DesktopWrite.Outcome.Done(null), after),
        )
        // A refusal is the PC's own sentence, word for word.
        assertEquals(
            "Not changed. \"shouty\" is not one of the choices for bluntness; it has: gentle, direct.",
            PromptCoach.saidChoice(
                "bluntness",
                DesktopWrite.Outcome.Refused("\"shouty\" is not one of the choices for bluntness; " +
                    "it has: gentle, direct."),
                after,
            ),
        )
        // The switch's own body is untouched: one field, as it always was.
        assertEquals("""{"enabled":true}""", PromptCoach.enabledBody(true))
        assertEquals("""{"enabled":false}""", PromptCoach.enabledBody(false))
    }

    // ---- Which AI the prompt is headed for --------------------------------

    @Test
    fun theCritiqueCarriesTheAiItWasCoachedFor() {
        val body = Json.parseToJsonElement(
            """
            {"ok": true, "coach": {
               "score": 4, "clear": false,
               "issues": [{"what": "No output shape", "why": "prose or a list", "fix": "Say: a table."}],
               "missing": ["Which PC is this for?"],
               "suggestion": "Compare them as a table.",
               "advice_given": true, "said": "",
               "target": {"known": true, "id": "openai_api",
                          "name": "ChatGPT (OpenAI API, gpt-5-mini)",
                          "advice": "ChatGPT (OpenAI API, gpt-5-mini). gpt-5-mini is the preset's default.",
                          "quirks": ["Hidden reasoning can shorten the visible answer."],
                          "style": ["State the deliverable first."],
                          "checked": "2026-09-28", "source": "preset notes in jarvis_chatbot_api.py",
                          "stale": false}
            }}
            """.trimIndent(),
        ).let { PromptCoach.parseCritique(it as JsonObject) }!!
        val t = body.target!!
        assertTrue(t.known)
        assertEquals("openai_api", t.id)
        assertEquals("ChatGPT (OpenAI API, gpt-5-mini)", t.name)
        assertEquals(listOf("Hidden reasoning can shorten the visible answer."), t.quirks)
        assertEquals("2026-09-28", t.checked)
        assertFalse(t.stale)
        assertTrue(t.advice.startsWith("ChatGPT (OpenAI API"))
        assertEquals("What Jarvis knows, from preset notes in jarvis_chatbot_api.py",
            PromptCoach.sourceLine(t.source))
    }

    @Test
    fun anAiJarvisDoesNotKnowIsSaidSoAndNothingIsInventedForIt() {
        // The owner's words of 2026-10-09: it must SAY it does not know, not
        // guess. The PC sends known=false with its own sentence and no notes.
        val body = PromptCoach.parseCritique(
            Json.parseToJsonElement(
                """
                {"ok": true, "coach": {"score": 5, "clear": false, "issues": [], "missing": [],
                  "suggestion": "", "advice_given": true, "said": "",
                  "target": {"known": false, "id": "", "name": "",
                             "advice": "Jarvis does not know \"mystery-9000\" yet, so it cannot say what that one handles badly.",
                             "quirks": [], "style": [], "checked": "", "source": "", "stale": false}}}
                """.trimIndent(),
            ) as JsonObject,
        )!!
        val t = body.target!!
        assertFalse(t.known)
        assertEquals(emptyList<String>(), t.quirks)
        assertEquals(emptyList<String>(), t.style)
        assertEquals("", t.checked)
        assertTrue(t.advice.contains("does not know"))
        assertEquals(PromptCoach.UNKNOWN_TITLE, "Jarvis does not know this AI yet")
        assertEquals(PromptCoach.TARGET_TITLE, "The AI this is going to")
    }

    @Test
    fun anOldSetOfNotesSaysItMayBeOutOfDate() {
        val body = PromptCoach.parseCritique(
            Json.parseToJsonElement(
                """
                {"ok": true, "coach": {"score": 5, "clear": false, "issues": [], "missing": [],
                  "suggestion": "", "advice_given": true, "said": "",
                  "target": {"known": true, "id": "local", "name": "the model on this PC (Ollama)",
                             "advice": "the model on this PC (Ollama). (Last checked 2001-01-01 - this may be out of date.)",
                             "quirks": [], "style": [], "checked": "2001-01-01",
                             "source": "the shipped table", "stale": true}}}
                """.trimIndent(),
            ) as JsonObject,
        )!!
        assertTrue(body.target!!.stale)
        assertTrue(body.target!!.advice.contains("may be out of date"))
    }

    // ---- "Only when the prompt is weak" ------------------------------------

    @Test
    fun adviceHeldBackIsNotTheSameAsNoAdviceFound() {
        // The PC held its advice back rather than finding none, and sent its
        // own sentence for that. It is a real answer with a score, so it must
        // not be read as a malformed one - and the screen must not show the
        // "nothing missing" line, which would say the opposite.
        val held = PromptCoach.parseCritique(
            Json.parseToJsonElement(
                """
                {"ok": true, "coach": {"score": 9, "clear": true, "issues": [], "missing": [],
                  "suggestion": "Put the kettle on at eight.",
                  "advice_given": false, "said": "Nothing here was weak enough to flag. Your question is fine as it is - send it."}}
                """.trimIndent(),
            ) as JsonObject,
        )!!
        assertFalse(held.adviceGiven)
        assertTrue(held.said.startsWith("Nothing here was weak enough"))
        assertEquals(9, held.score)
        assertNull(held.target)
        // An older backend sends neither field, and "it had advice to give" is
        // what it did then - never "it held something back".
        val older = PromptCoach.parseCritique(
            Json.parseToJsonElement(
                """{"ok": true, "coach": {"score": 9, "clear": true, "issues": [], "missing": [], "suggestion": "x"}}""",
            ) as JsonObject,
        )!!
        assertTrue(older.adviceGiven)
        assertEquals("", older.said)
    }

    @Test
    fun aCritiqueThePcDidNotSendIsStillRefusedNotHalfShown() {
        // The one rule that must survive every new field: a body with no coach
        // object, or with no score, is not a critique and is never drawn as an
        // empty panel.
        assertNull(PromptCoach.parseCritique(buildJsonObject { put("ok", true) }))
        assertNull(
            PromptCoach.parseCritique(
                buildJsonObject { putJsonObject("coach") { putJsonArray("issues") {} } },
            ),
        )
        assertNull(
            PromptCoach.parseCritique(
                buildJsonObject {
                    putJsonObject("coach") {
                        put("score", "4")
                        putJsonArray("issues") { }
                    }
                },
            ),
        )
    }
}
