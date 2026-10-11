package com.jarvis.client

import com.jarvis.client.net.ChatHistory
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.TemporaryChat
import com.jarvis.client.net.Thinking
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Think about this one" and "When Jarvis thinks" (the owner's decision of
 * 2026-10-11).
 *
 * THE PROBLEM, MEASURED. The everyday model is becoming `qwen3.5:9b`, a model
 * that thinks before it answers. Measured on the owner's PC with `qwen3:8b`:
 * thinking left on with a normal answer allowance spent every token reasoning
 * and came back with an EMPTY answer on all three test questions; with thinking
 * off the same questions were answered correctly in 0.29 s. So whether Jarvis
 * thinks before answering is the owner's choice, and on the phone it is:
 *
 *   * one per-question key - "Think" beside the chat box - which asks for
 *     thinking on THAT question and no other, and
 *   * the two-choice setting on Settings, drawn from the PC's own answer.
 *
 * WHAT THIS FILE HOLDS THE PHONE TO
 *
 *   1. The request body carries the field on the question it was asked for,
 *      and NOT on an ordinary question - the same rule `temporary` follows.
 *   2. The key is one question only: `ChatSession.send` takes the flag and
 *      clears it before the request is built, so a later question is ordinary.
 *   3. It is never the reason a message fails to send or an answer comes back
 *      blank: nothing refuses the send over it, the send path is unchanged,
 *      and the PC's capability gates whether the key is even drawn (never a
 *      version number).
 *   4. The setting's two choices are plain words a beginner can read, and a
 *      PC that sends no WHEN fields at all still gets both rows, marked with
 *      the safe one.
 *
 * Pure JVM: no Android types, no network.
 */
class ThinkingChoiceTest {

    @Test
    fun `a question asking for thinking carries the field and an ordinary one does not`() {
        val asking = ChatHistory.asking("what is the capital of France?")
        val thought = JarvisJson.parseToJsonElement(
            ChatHistory.requestBody(
                emptyList(), asking, conversationId = "conv-00000001", think = true,
            ),
        ).jsonObject
        assertEquals(JsonPrimitive(true), thought[Thinking.ONE_SHOT])
        val ordinary = JarvisJson.parseToJsonElement(
            ChatHistory.requestBody(emptyList(), asking, conversationId = "conv-00000001"),
        ).jsonObject
        assertFalse(
            "an ordinary question is exactly the request it always was",
            ordinary.containsKey(Thinking.ONE_SHOT),
        )
        // Never sent as false either: the field is present or absent, like
        // temporary and cloud_yes - there is no `"think":false` to misread.
        assertFalse(ordinary.toString().contains("\"${Thinking.ONE_SHOT}\""))
    }

    @Test
    fun `the field rides with the question and nothing else changes`() {
        val asking = ChatHistory.asking("think about this one")
        val body = JarvisJson.parseToJsonElement(
            ChatHistory.requestBody(
                emptyList(), asking, conversationId = "conv-00000001",
                temporary = true, cloudYes = true, think = true,
            ),
        ).jsonObject
        assertEquals(JsonPrimitive(true), body[Thinking.ONE_SHOT])
        assertEquals(JsonPrimitive(true), body[TemporaryChat.FIELD])
        assertEquals(JsonPrimitive(true), body["cloud_yes"])
        // A question asked for thinking about is still an ordinary chat
        // request in every other way: same stream, same device, same words.
        assertEquals(JsonPrimitive(true), body["stream"])
        assertEquals(JsonPrimitive(true), body["auto"])
        assertEquals(JsonPrimitive(ChatHistory.DEVICE), body["device"])
        assertTrue(body["messages"].toString().contains("think about this one"))
    }

    @Test
    fun `the key covers one question and then lets go`() {
        // Read from the source, the way the other phone contracts are: the
        // flag is taken BEFORE the request is built and cleared in the same
        // breath, so no failure, interrupt or retry can leave it on.
        val send = source("$main/net/ChatSession.kt")
            .substringAfter("suspend fun send(")
            .substringBefore("\n    /**")
        val take = send.indexOf("val asThought = _thinkOnce.value")
        val clear = send.indexOf("_thinkOnce.value = false")
        val build = send.indexOf("api.chatCall(")
        assertTrue("the flag is read in send()", take >= 0)
        assertTrue("and cleared in the same breath", clear > take)
        assertTrue("both happen before the request is built", build > clear)
        assertTrue(
            "the field is passed to the request",
            send.substring(build).contains("think = asThought"),
        )
        // Nothing refuses the send over it - it can never be why a message
        // failed to go. The only guard before the call is the temporary one.
        val guard = send.substring(0, build)
        assertFalse("no refusal over thinking", guard.contains("asThought &&"))
        assertFalse("and nothing is stored", guard.contains("_thinkOnce.value = true;"))
    }

    @Test
    fun `the key is offered only on a PC that understands the field`() {
        assertTrue(Thinking.offered { it == Thinking.CAPABILITY })
        assertFalse(Thinking.offered { false })
        assertFalse(Thinking.offered { it == "temporary_chat" })
        assertEquals("think_per_question", Thinking.CAPABILITY)
        // Never a version number: the same rule the rest of the phone follows.
        assertFalse(Thinking.CAPABILITY.any { it.isDigit() })
    }

    @Test
    fun `the two choices are few and plain`() {
        assertEquals(listOf(Thinking.WHEN_ASKED, Thinking.ALWAYS), Thinking.WHEN_MODES)
        assertEquals(Thinking.WHEN_ASKED, Thinking.WHEN_DEFAULT)
        for (id in Thinking.WHEN_MODES) {
            val label = Thinking.WHEN_LABELS.getValue(id)
            val why = Thinking.WHEN_WHY.getValue(id)
            assertTrue("$id has a short label", label.isNotBlank() && label.length <= 24)
            assertTrue("$id says what it does in plain words", why.length > 40)
            assertFalse(
                "$id says nothing a beginner cannot read",
                listOf("token", "reasoning_effort", "json", "api", "inference")
                    .any { why.lowercase().contains(it) },
            )
        }
        assertTrue(Thinking.WHEN_DETAIL.lowercase().contains("think"))
    }

    @Test
    fun `the safe choice is what a PC that says nothing reads as`() {
        val quiet = Thinking.parse(
            JsonObject(mapOf("models" to JsonArray(emptyList()))),
        )
        assertNotNull(quiet)
        assertEquals(Thinking.WHEN_ASKED, quiet!!.mode)
        val marked = quiet.whenChoices.first { it.selected }
        assertEquals(Thinking.WHEN_ASKED, marked.id)
        assertEquals("Only when I ask", marked.label)
    }

    @Test
    fun `the PCs own two choices are drawn as they were sent`() {
        val view = Thinking.parse(
            JsonObject(
                mapOf(
                    "models" to JsonArray(emptyList()),
                    "when" to JsonPrimitive(Thinking.ALWAYS),
                    "when_choices" to JsonArray(
                        listOf(
                            JsonObject(
                                mapOf(
                                    "id" to JsonPrimitive(Thinking.WHEN_ASKED),
                                    "label" to JsonPrimitive("Only when I ask"),
                                    "why" to JsonPrimitive("Ordinary answers are written straight away."),
                                    "selected" to JsonPrimitive(false),
                                ),
                            ),
                            JsonObject(
                                mapOf(
                                    "id" to JsonPrimitive(Thinking.ALWAYS),
                                    "label" to JsonPrimitive("Always"),
                                    "why" to JsonPrimitive("Jarvis may think before every answer."),
                                    "selected" to JsonPrimitive(true),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        assertNotNull(view)
        assertEquals(Thinking.ALWAYS, view!!.mode)
        assertEquals(listOf(Thinking.WHEN_ASKED, Thinking.ALWAYS), view.whenChoices.map { it.id })
        assertEquals(listOf(false, true), view.whenChoices.map { it.selected })
    }

    @Test
    fun `a choice the owner never made is never shown as made`() {
        // A PC that names a "when" but marks no row: the named one wins.
        val named = Thinking.parse(
            JsonObject(
                mapOf(
                    "models" to JsonArray(emptyList()),
                    "when" to JsonPrimitive(Thinking.ALWAYS),
                ),
            ),
        )
        assertEquals(Thinking.ALWAYS, named!!.mode)
        // A "when" nobody recognises (a newer PC's third choice) reads as the
        // safe one rather than as a made-up row.
        val unknown = Thinking.parse(
            JsonObject(
                mapOf(
                    "models" to JsonArray(emptyList()),
                    "when" to JsonPrimitive("sometimes"),
                ),
            ),
        )
        assertEquals(Thinking.WHEN_ASKED, unknown!!.mode)
        assertEquals(Thinking.WHEN_MODES, unknown.whenChoices.map { it.id })
    }

    @Test
    fun `the write is one small object with the id the PC reads`() {
        val asked = JarvisJson.parseToJsonElement(
            Thinking.whenBodyString(Thinking.WHEN_ASKED),
        ).jsonObject
        assertEquals(JsonPrimitive(Thinking.WHEN_ASKED), asked["when"])
        assertEquals(1, asked.size)
        val always = JarvisJson.parseToJsonElement(
            Thinking.whenBodyString(Thinking.ALWAYS),
        ).jsonObject
        assertEquals(JsonPrimitive("always"), always["when"])
        // The level write is unchanged, and carries no "when" of its own.
        val level = JarvisJson.parseToJsonElement(
            Thinking.bodyString("everyday", "deep"),
        ).jsonObject
        assertFalse(level.containsKey("when"))
        assertEquals(JsonPrimitive("deep"), level["level"])
        // A made-up choice is refused here rather than sent to the PC.
        var threw = false
        try {
            Thinking.whenBodyString("sometimes")
        } catch (e: IllegalArgumentException) {
            threw = true
        }
        assertTrue(threw)
    }

    @Test
    fun `the setting is reachable and held on a live link`() {
        val rt = source("$main/JarvisRuntime.kt")
        val set = rt.substringAfter("suspend fun setThinkingWhen(")
            .substringBefore("\n    }")
        assertTrue("held on a stale link, like every change", set.contains("actionBlocker()?.let"))
        assertTrue("the same route the levels use", set.contains("api.thinkingPost("))
        val plate = source("$main/ui/screens/ThinkingPlate.kt")
        assertTrue("the two choices are drawn", plate.contains("v.whenChoices.forEach"))
        assertTrue("and changing one calls the WHEN function", plate.contains("chooseWhen(choice.id)"))
        assertTrue(
            "the PC's own sentence, or the refusal in plain words, is what the owner sees",
            source("$main/net/Thinking.kt").contains("fun whenReplyLine(")
                && plate.contains("JarvisRuntime.setThinkingWhen("),
        )
    }

    @Test
    fun `the key beside the chat box sends nothing on its own`() {
        val home = source("$main/ui/screens/HomeScreen.kt")
        val key = home.substringAfter("if (state.thinkOffered) {").substringBefore("Spacer(Modifier.width(4.dp))\n        }")
        assertTrue("the label is the word the owner reads", key.contains("Thinking.ONE_SHOT_LABEL"))
        assertTrue("it is a toggle, not a send", key.contains("onClick = actions.onToggleThinkOnce"))
        assertFalse("nothing is sent by tapping it", key.contains("onSend"))
        val activity = source("$main/MainActivity.kt")
        assertTrue(
            "the key is drawn only when the PC says it has the feature",
            activity.contains("version?.can(com.jarvis.client.net.Thinking.CAPABILITY) == true"),
        )
        assertTrue(
            "and it is wired to the chat's one-question flag",
            activity.contains("onToggleThinkOnce = { chat.setThinkOnce(!chat.thinkOnce.value) }"),
        )
        // The runtime's toggle sends nothing either.
        val rt = source("$main/JarvisRuntime.kt")
        val toggle = rt.substringAfter("fun setThinkOnce(").substringBefore("\n    }")
        assertFalse("no request", toggle.contains("api."))
        assertTrue(toggle.contains("chat.setThinkOnce(on)"))
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

    private fun source(rel: String): String = repoFile(rel).readText()

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client"
}
