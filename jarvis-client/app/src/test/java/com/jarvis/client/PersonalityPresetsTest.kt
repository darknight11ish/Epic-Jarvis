package com.jarvis.client

import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Manner
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "How Jarvis talks" is ONE list on both screens (the owner, 2026-10-28:
 * "make sure the presets for jarvis personality and other presets are
 * consistent too").
 *
 * Before this, the phone's Mind screen drew only the legacy Warm/Plain pair
 * while the PC had ten personality presets, and it marked "Plain (in use)"
 * whenever the PC was on ANY preset other than Warm Collaborator - because
 * `jarvis_manner.current()` derives that word from the active preset. So the
 * phone named a preset Jarvis was not in, and a tap on "Plain" sent
 * `{"manner": "plain"}`, which the PC's legacy branch turns into
 * `tactical_ops` and also resets the four dials: a desktop choice silently
 * replaced from the phone.
 *
 * What is proven here, against the REAL `contract/personalities.json` (the
 * file `tools/gen_personalities.py` generates the PC's copy from) rather than
 * a list typed to suit this client:
 *
 *  - the phone lists the contract's presets, in the contract's order, with the
 *    contract's titles and descriptions;
 *  - the row marked "in use" is the PC's own `personality`, and only that row;
 *  - the write is ONE field, `{"personality": "<id>"}`, never a manner word;
 *  - a PC older than §27.7 still gets its two Warm/Plain choices, and the
 *    screen does not pretend a list the PC never sent;
 *  - the answer naming a preset it does not list marks nothing (no phantom);
 *  - the shipped screen really draws that list and really listens for the
 *    PC's `manner` doorbell - pinned in the source, because there is no
 *    emulator in this container (the device pass is in the PR body).
 */
class PersonalityPresetsTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun source(rel: String): String = repoFile(main + rel).readText()

    /** The contract's ten presets, in the contract's order. */
    private fun contract() = JarvisJson.parseToJsonElement(
        repoFile("contract/personalities.json").readText(),
    ).jsonObject["personalities"]!!.jsonArray.map { it.jsonObject }

    /** One `GET /api/manner` answer in the shape `jarvis_manner.view()` sends. */
    private fun answer(
        active: String = "classic_butler",
        withPersonalities: Boolean = true,
        rowsOverride: List<JsonObject>? = null,
    ): JsonObject = buildJsonObject {
        put("available", true)
        // Derived on the PC from the active preset: warm only for warm_peer.
        put("manner", if (active == "warm_peer") "warm" else "plain")
        put("default", "warm")
        put("title", Manner.TITLE)
        put("detail", Manner.DETAIL)
        put("spoken", Manner.SPOKEN)
        put("humor", false)
        put("personality", active)
        put("choices", buildJsonArray {
            add(buildJsonObject { put("id", "warm"); put("label", "Warm and brief (default)"); put("why", "Friendly.") })
            add(buildJsonObject { put("id", "plain"); put("label", "Plain"); put("why", "Just the answer.") })
        })
        if (withPersonalities) {
            put("personalities", buildJsonArray {
                for (row in rowsOverride ?: contract().map { p ->
                    buildJsonObject {
                        p["id"]?.jsonPrimitive?.let { put("id", it) }
                        p["title"]?.jsonPrimitive?.let { put("title", it) }
                        p["description"]?.jsonPrimitive?.let { put("description", it) }
                        put("builtin", true)
                    }
                }) {
                    add(row)
                }
            })
        }
    }

    @Test
    fun `the phone lists the contract's presets in the contract's order`() {
        val view = Manner.parse(answer())!!
        val expected = contract()
        assertTrue("the PC's list was not parsed at all", view.hasPersonalities)
        assertEquals(
            "the ids (and so the order) are not the contract's",
            expected.map { it["id"]!!.jsonPrimitive.content },
            view.personalities.map { it.id },
        )
        assertEquals(
            "the names are not the contract's, so the two apps would read differently",
            expected.map { it["title"]!!.jsonPrimitive.content },
            view.personalities.map { it.title },
        )
        assertEquals(
            "the descriptions are not the contract's",
            expected.map { it["description"]!!.jsonPrimitive.content },
            view.personalities.map { it.description },
        )
        assertEquals(
            "the contract's ten built-ins are not ten rows",
            expected.size,
            view.personalities.size,
        )
    }

    @Test
    fun `the row marked in use is the PC's own personality, and only that row`() {
        val view = Manner.parse(answer(active = "classic_butler"))!!
        assertEquals("classic_butler", view.personality)
        assertEquals("classic_butler", view.activePersonality?.id)
        assertEquals(
            "more than one row claims to be in use",
            listOf("classic_butler"),
            view.personalities.filter { view.isCurrent(it) }.map { it.id },
        )
        // The derived manner word is "plain" here, and no personality is
        // called that: the mark must never come from it.
        assertEquals("plain", view.manner)
        assertNull(
            "a legacy manner word was matched to a preset id",
            view.personalities.firstOrNull { it.id == view.manner },
        )
    }

    @Test
    fun `the write is one field, personality, and never a manner word`() {
        assertEquals(
            """{"personality":"classic_butler"}""",
            Manner.personalityBody("classic_butler"),
        )
        assertFalse(
            "the switch body carries the legacy manner word, which flattens the preset",
            Manner.personalityBody("classic_butler")!!.contains("\"manner\""),
        )
        assertNull("an empty id must not be sent", Manner.personalityBody("  "))
    }

    @Test
    fun `an older PC still gets its two choices and no invented list`() {
        val view = Manner.parse(answer(withPersonalities = false))!!
        assertFalse("an older PC was given a personality list", view.hasPersonalities)
        assertEquals(Manner.MANNERS, view.choices.map { it.id })
        assertEquals("", view.personality)
        assertNull(view.activePersonality)
    }

    @Test
    fun `an answer naming a preset it does not list marks nothing`() {
        val view = Manner.parse(answer(active = "gone_in_a_later_version"))!!
        assertEquals("", view.personality)
        assertNull(view.activePersonality)
        assertTrue("the list itself should still be drawn", view.hasPersonalities)
    }

    @Test
    fun `a row without an id is skipped, and a missing description is not fatal`() {
        val view = Manner.parse(
            answer(
                rowsOverride = listOf(
                    buildJsonObject { put("title", "No id here") },
                    buildJsonObject { put("id", "warm_peer"); put("title", "Warm Collaborator") },
                ),
            ),
        )!!
        assertEquals(listOf("warm_peer"), view.personalities.map { it.id })
        assertEquals("", view.personalities.first().description)
        assertEquals("Warm Collaborator", view.personalities.first().title)
    }

    @Test
    fun `the PC's own switch line is what the phone shows`() {
        val ok = JarvisJson.parseToJsonElement(
            """{"ok":true,"said":"Very good, sir. Classic British Butler protocols are online."}""",
        ).jsonObject
        assertEquals(
            "Very good, sir. Classic British Butler protocols are online.",
            Manner.personalityReplyLine(
                ApiResult.Ok(ok),
                "Classic British Butler",
            ),
        )
    }

    @Test
    fun `the shipped screen draws the PC's list and listens for its doorbell`() {
        val plate = source("ui/screens/MannerPlate.kt")
        assertTrue(
            "the screen does not branch on the PC's list:\n$plate",
            plate.contains("v.hasPersonalities"),
        )
        assertTrue(
            "the screen does not draw the PC's presets",
            plate.contains("v.personalities.forEach"),
        )
        assertTrue(
            "the screen does not switch a preset through the one-field write",
            plate.contains("JarvisRuntime.usePersonality("),
        )
        assertTrue(
            "the screen does not read the PC's manner doorbell",
            plate.contains("JarvisRuntime.mannerTick"),
        )
        val runtime = source("JarvisRuntime.kt")
        assertTrue(
            "the runtime does not handle the PC's manner event",
            runtime.contains("com.jarvis.client.net.Manner.EVENT -> _mannerTick.update"),
        )
        assertTrue(
            "the runtime has no one-field personality write",
            runtime.contains("suspend fun usePersonality("),
        )
    }
}
