package com.jarvis.client

import com.jarvis.client.net.CardBodyWords
import com.jarvis.client.net.CardSummary
import com.jarvis.client.net.CardWords
import com.jarvis.client.net.decodePendingRows
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A card's body is never raw machine JSON (phone field test, 2026-10-29,
 * `REPORT.md` B7).
 *
 * The card in `xml/approval-card.xml` drew, as its body:
 *
 *     {
 *         "from": "qwen3.5:9b",
 *         "to": "hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M",
 *         "why": "preset"
 *     }
 *
 * on a PC whose Approval cards setting was "Start short (default)". The PC had
 * sent its own title but NO short summary and NO whole card text for that row,
 * so [CardSummary.shown] had no short line to fold to and fell back to the
 * row's `detail` - which [com.jarvis.client.net]'s `normalisePendingRow` stores
 * as pretty-printed JSON - drawing it unfolded and with no "Explain more"
 * control at all.
 *
 * These tests hold the fix, on a plain JVM:
 *
 *  1. From a wire row shaped like the field-test card, the JSON really does
 *     arrive as `detail`, with `notice.summary` and `notice.full` empty.
 *  2. Folded, that card draws NO body at all (so no braces, no quotes), its own
 *     title as the readable line, and an "Explain more" control.
 *  3. Opened, it says the change in plain words - never the raw JSON.
 *  4. The humaniser itself: the common from/to/why shape is one sentence, every
 *     other object is labelled lines, lists are lists of words, and machine text
 *     with nothing to say is left out.
 *  5. An ordinary card (PC summary + plain detail) and an older PC whose whole
 *     card is already words draw exactly as they did before.
 */
class CardBodyWordsTest {

    // ------------------------------------------------- the field-test card ----

    /** The wire `detail` object the field-test card carried, as the PC sent it. */
    private fun switchDetail(): JsonObject = JsonObject(
        mapOf(
            "from" to JsonPrimitive("qwen3.5:9b"),
            "to" to JsonPrimitive("hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M"),
            "why" to JsonPrimitive("preset"),
        ),
    )

    /**
     * The switch-model row from the field test: the PC sent its own title, an
     * empty `notice.summary` and an empty `notice.full`, and the change itself
     * rides in `detail` as a JSON object - which is why the phone drew JSON.
     */
    private fun switchModelRow(): JsonObject = JsonObject(
        mapOf(
            "id" to JsonPrimitive("switch-1"),
            "action" to JsonPrimitive("switch_model"),
            "tier" to JsonPrimitive("ask"),
            "detail" to switchDetail(),
            "risk" to JsonObject(
                mapOf(
                    "reversible" to JsonPrimitive("yes"),
                    "reach" to JsonPrimitive("local"),
                    "swipe_ok" to JsonPrimitive(true),
                    "why" to JsonPrimitive("rollback is one tap, which is why rollback is tier auto"),
                    "classified" to JsonPrimitive(true),
                ),
            ),
            "notice" to JsonObject(
                mapOf(
                    "title" to JsonPrimitive("Jarvis wants to switch to a different AI model"),
                    "summary" to JsonPrimitive(""),
                    "full" to JsonPrimitive(""),
                    "weight" to JsonPrimitive("heavy"),
                    "deny_ok" to JsonPrimitive(true),
                    "approve_ok" to JsonPrimitive(false),
                ),
            ),
            "replaces" to JsonPrimitive(false),
            "expires_in" to JsonPrimitive(120.0),
        ),
    )

    private fun fieldTestCard() = decodePendingRows(listOf(switchModelRow()), nowMs = 0L).items.single()

    /** The whole card as it is drawn folded - the state the field test caught. */
    private fun folded() = fieldTestCard().let {
        CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = it.notice?.summary,
            full = it.notice?.full,
            detail = it.detail,
        )
    }

    @Test
    fun theJsonBodyArrivesAsTheRowsDetail() {
        val read = decodePendingRows(listOf(switchModelRow()), nowMs = 0L)
        assertEquals("the row itself is readable", 0, read.skipped)
        val item = read.items.single()
        assertEquals("the PC's own title", "Jarvis wants to switch to a different AI model", item.title)
        val notice = checkNotNull(item.notice) { "the PC sent a notice with the title" }
        assertEquals("the PC sent no short summary for this card", "", notice.summary)
        assertEquals("and no whole card text of its own", "", notice.full)
        val detail = checkNotNull(item.detail) { "the change arrives as the row's detail" }
        assertTrue(
            "as pretty-printed JSON, exactly the machine text the phone drew: $detail",
            detail.trim().startsWith("{"),
        )
        assertTrue(detail.contains("\"from\": \"qwen3.5:9b\""))
        assertTrue(detail.contains("\"why\": \"preset\""))
    }

    @Test
    fun aCardWithNoSummaryAndMachineDetailStartsFoldedWithAReadableLineAndAControl() {
        val item = fieldTestCard()
        val shown = folded()
        assertFalse("folded, not open", shown.expanded)
        assertTrue(
            "no body is unfolded, so no machine text is on the card: ${shown.body}",
            shown.body.isBlank(),
        )
        // The readable line is the card's own title: the PC sent no `summary`
        // and no `full`, so CardWords.summaryFallback answers with the title -
        // which ApprovalCard already draws as the card's heading.
        val line = shown.summary ?: CardWords.summaryFallback(item.notice?.full, item.title)
        assertEquals("the card's own title is the readable line", item.title, line)
        assertFalse("which is words, not JSON", line.contains("{") || line.contains("}"))
        assertTrue("with an Explain more control, as Start short (default) promises", shown.control)
        assertEquals("Explain more", shown.label)
    }

    @Test
    fun openingItSaysTheDetailInPlainWordsAndNeverDumpsTheJson() {
        val item = fieldTestCard()
        val shown = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = item.notice?.summary,
            full = item.notice?.full,
            detail = item.detail,
            expanded = true,
        )
        assertTrue("open", shown.expanded)
        assertEquals("the way back", "Show less", shown.label)
        assertNoMachineText(shown.body)
        assertTrue(
            "the change is said plainly: ${shown.body}",
            shown.body.contains(
                "From qwen3.5:9b to hf.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-GGUF:Q4_K_M",
            ),
        )
        assertTrue("and the reason is in brackets", shown.body.contains("(preset)"))
        assertFalse("never the raw detail", shown.body == item.detail)
    }

    @Test
    fun thePcSettingToShowEverythingStillNeverDrawsRawJson() {
        val item = fieldTestCard()
        val shown = CardSummary.shown(
            mode = CardSummary.ALWAYS_FULL,
            summary = item.notice?.summary,
            full = item.notice?.full,
            detail = item.detail,
        )
        assertTrue("drawn open", shown.expanded)
        assertFalse("nothing is folded away, so no control", shown.control)
        assertNoMachineText(shown.body)
        assertTrue("the change is still said in plain words", shown.body.contains("(preset)"))
    }

    // -------------------------------------------------- the humaniser ----

    @Test
    fun theCommonChangeShapeIsSaidAsOneSentence() {
        assertEquals(
            "From a to b (preset)",
            CardBodyWords.words("""{"from":"a","to":"b","why":"preset"}"""),
        )
        // The phone stores `detail` pretty-printed, so the whitespace
        // PrettyJson writes must read the same as the compact shape.
        assertEquals(
            "From a to b (preset)",
            CardBodyWords.words(
                """
                {
                    "from": "a",
                    "to": "b",
                    "why": "preset"
                }
                """.trimIndent(),
            ),
        )
        assertTrue("a JSON object is machine text", CardBodyWords.isMachine("""{"from":"a"}"""))
        assertTrue("and so is a JSON list", CardBodyWords.isMachine("""["a"]"""))
        assertFalse("a sentence is not", CardBodyWords.isMachine("Jarvis wants to send an email."))
    }

    @Test
    fun everyOtherFieldReadsAsALabelledLineNeverAsBraces() {
        assertEquals(
            "Path: C:/x\nSize: 3 GB",
            CardBodyWords.words("""{"path":"C:/x","size":"3 GB"}"""),
        )
        assertEquals(
            "First name: Priya\nLast verified at: today",
            CardBodyWords.words("""{"first_name":"Priya","last_verified_at":"today"}"""),
        )
        assertEquals(
            "Model: minicpm-v\nCount: 3",
            CardBodyWords.words("""{"model":"minicpm-v","count":3}"""),
        )
        assertEquals(
            "a list of plain values is a list of words",
            "Models: a, b",
            CardBodyWords.words("""{"models":["a","b"]}"""),
        )
        // Whatever the shape, no braces and no JSON quotes reach the card.
        for (raw in listOf(
            """{"a":{"b":"c"}}""",
            """[{"a":"1"},{"b":"2"}]""",
            """{"x":true,"y":["one","two"]}""",
        )) {
            assertNoMachineText(CardBodyWords.words(raw))
        }
    }

    @Test
    fun machineTextThatSaysNothingIsLeftOutRatherThanDumped() {
        assertEquals("a JSON object with no sayable field", "", CardBodyWords.words("""{"why":null}"""))
        assertEquals("an empty JSON list", "", CardBodyWords.words("[]"))
        assertEquals("blank text", "", CardBodyWords.words("   "))
        assertEquals("absent text", "", CardBodyWords.words(null))
        // A card whose only text is such an object draws no body at all - and
        // no empty "Explain more" either.
        val shown = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = "",
            full = "",
            detail = """{"why":null}""",
        )
        assertEquals("nothing to show", "", shown.body)
        assertFalse("nothing to open", shown.control)
    }

    @Test
    fun ordinaryProseIsNeverRewritten() {
        val command = "rm -rf ~/Documents"
        val plan = "Jarvis would like to do this in the window \"Outlook - Compose\": send the draft"
        val diff = "--- a/notes.md\n+++ b/notes.md"
        for (text in listOf(command, plan, diff)) {
            assertEquals("word for word", text, CardBodyWords.words(text))
            assertFalse("not machine text", CardBodyWords.isMachine(text))
        }
    }

    // ------------------------------------ cards that already worked ----

    @Test
    fun anOrdinaryCardWithAShortSummaryAndPlainDetailIsUnchanged() {
        val summary = "Jarvis wants to email the clinic."
        val full = "It sends the one email shown and changes nothing else. nothing has happened yet."
        val detail = "To: doctor@clinic.example\nSubject: your appointment"
        val folded = CardSummary.shown(CardSummary.START_SHORT, summary, full, detail)
        assertEquals("the short summary is the folded line", summary, folded.summary)
        assertEquals("nothing else is drawn", "", folded.body)
        assertTrue("with the control", folded.control)
        assertFalse(folded.expanded)

        val open = CardSummary.shown(CardSummary.START_SHORT, summary, full, detail, expanded = true)
        assertEquals("the summary stays at the top when open", summary, open.summary)
        assertTrue("the PC's whole card, word for word", open.body.contains(full))
        assertTrue("and the plain detail, word for word", open.body.contains(detail))
        assertEquals("Show less", open.label)

        val always = CardSummary.shown(CardSummary.ALWAYS_FULL, summary, full, detail)
        assertTrue(
            "always show everything: the whole card and the detail",
            always.body.contains(full) && always.body.contains(detail),
        )
        assertFalse("nothing folded away, so no control", always.control)
    }

    @Test
    fun anOrdinaryCardWhoseDetailIsJsonOpensInPlainWordsToo() {
        val item = fieldTestCard()
        val shown = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = "Jarvis wants to switch to a different AI model.",
            full = "not classified, so treated as the worst case. nothing has happened yet.",
            detail = item.detail,
            expanded = true,
        )
        assertNoMachineText(shown.body)
        assertTrue(
            "the PC's own whole card is still there, word for word",
            shown.body.contains("not classified, so treated as the worst case"),
        )
        assertTrue("and the detail is words, not JSON", shown.body.contains("From qwen3.5:9b to"))
    }

    @Test
    fun aPcWithNoShortSummaryWhoseWholeCardIsAlreadyWordsIsUnchanged() {
        // An older backend sends no `notice.summary`, but its whole card is
        // already words: there is no machine text to fold away, so the card
        // draws that text exactly as before. (CardSummaryTest holds this same
        // rule; the new fold-and-control case is the one with only machine text.)
        val whole = "replaces your memory and notes with an older backup. Nothing else changes."
        val shown = CardSummary.shown(CardSummary.START_SHORT, summary = null, full = whole)
        assertEquals("the whole word text stays on the card", whole, shown.body)
        assertFalse("with nothing to fold away", shown.control)
        assertNull("and no second summary line", shown.summary)
    }

    @Test
    fun aCardWithOnlyMachineDetailAndNoNoticeAtAllAlsoFolds() {
        val row = JsonObject(
            mapOf(
                "id" to JsonPrimitive("old-pc-1"),
                "action" to JsonPrimitive("switch_model"),
                "tier" to JsonPrimitive("ask"),
                "detail" to switchDetail(),
            ),
        )
        val item = decodePendingRows(listOf(row), nowMs = 0L).items.single()
        assertNull("an older PC sends no notice at all", item.notice)
        val shown = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = item.notice?.summary,
            full = item.notice?.full,
            detail = item.detail,
        )
        assertTrue("folded, so no machine text", shown.body.isBlank())
        assertTrue("with the control", shown.control)
        val line = shown.summary ?: CardWords.summaryFallback(item.notice?.full, item.title)
        assertFalse("and a readable line, never JSON", line.contains("{"))
        assertTrue("the PC's own action words: $line", line.contains("switch model"))
    }

    // ---------------------------------------------------------- helpers ----

    private fun assertNoMachineText(text: String) {
        assertFalse("no opening brace in: $text", text.contains("{"))
        assertFalse("no closing brace in: $text", text.contains("}"))
        assertFalse("no JSON quote in: $text", text.contains("\""))
    }
}
