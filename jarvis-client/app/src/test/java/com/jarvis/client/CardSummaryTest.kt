package com.jarvis.client

import com.jarvis.client.net.CardSummary
import com.jarvis.client.net.CardWords
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Approval cards read short (the owner's request of 2026-10-09): "a more simple
 * summary, with an explain more button that expands the approval card total word
 * length and explains the details more. and approval card preferences such as
 * this should be changeable in the settings".
 *
 * What this holds, all on a plain JVM and all against the PC's OWN words
 * (`contract/card-words-cases.json`, made by `tools/gen_card_words_cases.py`
 * from the real `notice_for` and `jarvis_card_words.py`):
 *
 *  1. FOLDED, the card shows the short summary and nothing of the whole text.
 *  2. EXPANDED, the whole card IS there - including the exact line being agreed
 *     to, "Nothing else in it changes", the Windows Hello line where it applies
 *     and "If you say no: nothing changes". Those four are asserted word for
 *     word on a row shaped like a real one.
 *  3. OPENING ONE CARD DOES NOT TOUCH ANOTHER: the rule is a pure function of
 *     (this card, this mode, whether this card is open), so two cards with
 *     different ids cannot share it - and a different card's own words never
 *     appear in this one's.
 *  4. THE SETTING'S EFFECT, in both directions, and the control's own words.
 *  5. THE FALLBACK IS NEVER BLANK, for a PC whose notice carries no summary yet.
 */
class CardSummaryTest {

    private val doc: JsonObject by lazy {
        val text = checkNotNull(
            javaClass.classLoader?.getResourceAsStream("contract/card-words-cases.json"),
        ) { "contract/card-words-cases.json is missing - run tools/gen_card_words_cases.py" }
            .bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    private fun notice(action: String): JsonObject =
        doc.getValue("summaries").jsonArray
            .map { it.jsonObject }
            .first { it.getValue("action").jsonPrimitive.content == action }
            .getValue("notice").jsonObject

    private fun str(o: JsonObject, key: String) = o.getValue(key).jsonPrimitive.content

    // ------------------------------------------------------- 1. folded ----

    @Test
    fun foldedShowsTheShortSummaryAndNotTheWholeCard() {
        val n = notice("send_email")
        val short = str(n, "summary")
        val whole = str(n, "full")
        val shown = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = short,
            full = whole,
        )
        assertEquals("the short summary is what a folded card shows", short, shown.summary)
        assertEquals("and the whole card is NOT drawn", "", shown.body)
        assertFalse("folded, not open", shown.expanded)
        assertTrue("and there is a control to open it", shown.control)
        assertEquals("which says what the owner asked for", "Explain more", shown.label)
        assertTrue("the summary really is shorter than the whole card", short.length < whole.length)
    }

    @Test
    fun everyActionsSummaryIsShortAndTheWholeOneIsNot() {
        val rows = doc.getValue("summaries").jsonArray.map { it.jsonObject }
        assertTrue("the fixture carries every action", rows.size > 50)
        for (row in rows) {
            val action = str(row, "action")
            val n = row.getValue("notice").jsonObject
            val short = str(n, "summary")
            val whole = str(n, "full")
            assertTrue("$action: the summary is a sentence", short.endsWith("."))
            assertTrue("$action: the summary is not blank", short.isNotBlank())
            assertTrue(
                "$action: the summary is shorter than the whole card (${short.length} vs ${whole.length})",
                short.length < whole.length,
            )
            assertTrue("$action: the whole card is what it always was", whole.endsWith("."))
            assertFalse("$action: no raw action id in the summary", short.contains("_"))
        }
    }

    // ----------------------------------------------------- 2. expanded ----

    @Test
    fun expandedCarriesEverythingAPersonIsAgreeingTo() {
        // A row shaped like a real plan card: the PC's own notice, and the
        // card's own text as `detail` - which is where the machine-written
        // lines live (jarvis_ui_control.describe, jarvis_calendar, and the rest).
        val n = notice("control_computer")
        val cardText = listOf(
            "Jarvis would like to do this in the window \"Outlook - Compose\": send the draft",
            "",
            "1 step(s), weight: heavy - any click can send something or be impossible to undo.",
            "",
            "  1. click \"Send\" (id: btnSend)",
            "     why: the draft is ready",
            "",
            "Nothing else in it changes.",
            "This PC asks for Windows Hello before a risky approval.",
            "If you say no: nothing in this window changes; the goal is not attempted",
        ).joinToString("\n")

        val shown = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = str(n, "summary"),
            full = str(n, "full"),
            detail = cardText,
            expanded = true,
        )
        assertTrue("expanded", shown.expanded)
        assertEquals("the way back", "Show less", shown.label)
        assertEquals("the short line stays at the top when open", str(n, "summary"), shown.summary)

        // The four things the owner must still be able to read, word for word.
        assertTrue("the exact line being agreed to", shown.body.contains("click \"Send\""))
        assertTrue(
            "the exact value being agreed to",
            shown.body.contains("Jarvis would like to do this in the window"),
        )
        assertTrue("Nothing else in it changes", shown.body.contains("Nothing else in it changes"))
        assertTrue(
            "the Windows Hello line where it applies",
            shown.body.contains("Windows Hello"),
        )
        assertTrue(
            "If you say no: nothing changes",
            shown.body.contains("If you say no: nothing in this window changes"),
        )
        // And the PC's own full text is in there too, whole.
        assertTrue("the whole card, word for word", shown.body.contains(str(n, "full")))
        assertTrue(
            "nothing has happened yet",
            shown.body.contains("nothing has happened yet"),
        )
        // Folded, none of the machine text is on the card.
        val folded = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = str(n, "summary"),
            full = str(n, "full"),
            detail = cardText,
        )
        assertFalse("folded, the plan's own text is not drawn", folded.body.contains("btnSend"))
        assertFalse("and neither is the whole card", folded.body.contains("nothing has happened yet"))
    }

    @Test
    fun alwaysShowEverythingDrawsTheWholeCardAndNoControl() {
        for (action in listOf("send_email", "restore_backup", "learning_enable")) {
            val n = notice(action)
            val shown = CardSummary.shown(
                mode = CardSummary.ALWAYS_FULL,
                summary = str(n, "summary"),
                full = str(n, "full"),
                detail = "the exact line being changed",
            )
            assertTrue("$action: drawn open", shown.expanded)
            assertTrue(
                "$action: the whole card is there",
                shown.body.contains(str(n, "full")) && shown.body.contains("the exact line being changed"),
            )
            assertFalse("$action: nothing is folded away, so no control", shown.control)
            assertEquals("$action: the short line still says what it is", str(n, "summary"), shown.summary)
        }
    }

    // ------------------------------------- 3. one card does not touch another --

    @Test
    fun openingOneCardLeavesAnotherAlone() {
        val a = notice("send_email")
        val b = notice("restore_backup")
        // This is what the card does: one piece of open/closed state per card,
        // and the drawn result worked out from THAT card's own words.
        val openA = CardSummary.shown(
            CardSummary.START_SHORT, str(a, "summary"), str(a, "full"), expanded = true,
        )
        val closedB = CardSummary.shown(
            CardSummary.START_SHORT, str(b, "summary"), str(b, "full"), expanded = false,
        )
        assertTrue("the card that was opened shows its whole text", openA.body.contains(str(a, "full")))
        assertEquals("the card that was not opened shows its short summary", str(b, "summary"), closedB.summary)
        assertEquals("and none of its whole text", "", closedB.body)
        assertFalse("and it is not open", closedB.expanded)
        assertTrue("while the other one is", openA.expanded)
        // A different card's words can never appear in this one's text.
        assertFalse("no bleed between cards", openA.body.contains(str(b, "full")))
        assertFalse("nor the other way", closedB.body.contains(str(a, "full")))
        // The state is per id, so the same card read twice with the same inputs
        // gives the same answer - nothing is remembered between them.
        val again = CardSummary.shown(
            CardSummary.START_SHORT, str(a, "summary"), str(a, "full"), expanded = true,
        )
        assertEquals(openA, again)
    }

    @Test
    fun aRotationOrACloseKeepsOnlyThatCardsPlace() {
        // Standing in for `rememberSaveable(item.id)`: the map is keyed on the
        // card's id, so a different card is a different entry and starts folded.
        val open = mutableMapOf<String, Boolean>()
        open["card-a"] = true
        assertTrue("the card the owner opened is open", open["card-a"] == true)
        assertNull("a card that was never opened has no entry at all", open["card-b"])
        assertFalse(
            "so it is drawn folded",
            CardSummary.shown(
                CardSummary.START_SHORT, "Jarvis wants to send the email shown.",
                "the whole card", expanded = open["card-b"] ?: false,
            ).expanded,
        )
        // And a card that leaves the queue takes its entry with it.
        open.remove("card-a")
        assertNull(open["card-a"])
    }

    // -------------------------------------------------- 4. the setting -----

    @Test
    fun theSettingHasTwoChoicesAndStartShortIsTheDefault() {
        assertEquals("the PC's own two, in its own order", listOf("start_short", "always_full"), CardSummary.MODES)
        assertEquals("start short is the default", "start_short", CardSummary.DEFAULT)
        assertTrue("anything unknown is the default, never a third way", CardSummary.DEFAULT in CardSummary.MODES)
        val parsed = CardSummary.parse(
            Json.parseToJsonElement(
                """{"available":true,"mode":"always_full","stored":true,
                    "more_label":"Explain more","less_label":"Show less"}""",
            ).jsonObject,
        )
        assertNotNull(parsed)
        assertEquals("always_full", parsed!!.mode)
        assertFalse("so cards are drawn open", parsed.folded)
        assertEquals("Explain more", parsed.moreLabel)
        // A damaged or unknown mode is the default, not a guess.
        assertEquals(
            "start_short",
            CardSummary.parse(Json.parseToJsonElement("""{"mode":"half"}""").jsonObject)!!.mode,
        )
        assertNull(
            "an older PC with no such route draws as it always did",
            CardSummary.parse(Json.parseToJsonElement("""{"available":false}""").jsonObject),
        )
    }

    @Test
    fun theChoiceItselfIsThePcsAndOnlyTheTwoValuesAreSent() {
        assertEquals("/api/card-prefs", CardSummary.PATH)
        assertEquals("""{"mode":"always_full"}""", CardSummary.modeBody(CardSummary.ALWAYS_FULL))
        assertEquals("""{"mode":"start_short"}""", CardSummary.modeBody(CardSummary.START_SHORT))
        assertNull("never anything else", CardSummary.modeBody("half"))
        assertNull(CardSummary.modeBody(""))
        assertTrue(CardSummary.MISSING.contains("apply-patches.ps1"))
    }

    @Test
    fun theControlIsTheSameTwoWordsInBothApps() {
        assertEquals("Explain more", CardSummary.MORE_LABEL)
        assertEquals("Show less", CardSummary.LESS_LABEL)
        val prefs = doc.getValue("card_prefs").jsonObject
        assertEquals(
            "the fixture is the PC's own words",
            prefs.getValue("more_label").jsonPrimitive.content,
            CardSummary.MORE_LABEL,
        )
        assertEquals(
            prefs.getValue("less_label").jsonPrimitive.content,
            CardSummary.LESS_LABEL,
        )
        assertEquals(
            "and the PC's own two choices",
            listOf("start_short", "always_full"),
            prefs.getValue("modes").jsonArray.map { it.jsonPrimitive.content },
        )
        assertEquals(
            "with the default marked as the first",
            prefs.getValue("default").jsonPrimitive.content,
            CardSummary.DEFAULT,
        )
        // The row's own copy of the two labels, used only before a read answers.
        assertEquals("Start short (default)", CardSummary.LABELS[CardSummary.START_SHORT])
        assertEquals("Always show everything", CardSummary.LABELS[CardSummary.ALWAYS_FULL])
        for (id in CardSummary.MODES) {
            assertTrue("$id has its own line", !CardSummary.HELP[id].isNullOrBlank())
        }
    }

    // -------------------------------------------------- 5. the fallback ----

    @Test
    fun aRowWithNoShortWordsStillReadsAndIsNeverBlank() {
        // An older PC: no `notice.summary` at all. The card's own first
        // sentence stands in, whole, and the whole card is still behind the
        // control.
        val whole = "replaces your memory and notes with an older backup. Nothing else changes."
        val shown = CardSummary.shown(CardSummary.START_SHORT, summary = null, full = whole)
        assertNull("the card has no short line of its own", shown.summary)
        assertEquals("so the whole text stays on the card", whole, shown.body)
        assertFalse("and there is nothing to fold away", shown.control)
        // The card's own fallback, which is what the phone draws in that case.
        assertEquals(
            "the first whole sentence, never cut",
            "replaces your memory and notes with an older backup.",
            CardWords.summaryFallback(whole, "Jarvis wants to restore from a backup."),
        )
        assertEquals(
            "no full stop at all: the lot, with one added",
            "the whole thing with no stop.",
            CardWords.summaryFallback("the whole thing with no stop", "t"),
        )
        assertEquals(
            "nothing at all: the title, which is never blank",
            "Jarvis wants your OK for \"frobnicate widget\"",
            CardWords.summaryFallback("", CardWords.fallbackTitle("frobnicate_widget")),
        )
        assertEquals(
            "and never the raw action id",
            CardWords.NO_ACTION,
            CardWords.summaryFallback(null, CardWords.NO_ACTION),
        )
        // A summary with something to open: nothing is lost by folding it.
        val both = CardSummary.shown(CardSummary.START_SHORT, summary = "a short line.", full = whole)
        assertEquals("a short line.", both.summary)
        assertEquals("", both.body)
        assertTrue("with a control", both.control)
    }

    @Test
    fun thePureRuleAgreesWithThePcOnWhatIsShort() {
        // Whatever the PC sends as `summary` is what the card shows folded -
        // the phone never shortens it itself, so the two cannot drift.
        for (action in listOf("send_email", "tidy_inbox", "restore_backup", "handoff_keep_offering")) {
            val n = notice(action)
            val shown = CardSummary.shown(
                CardSummary.START_SHORT, str(n, "summary"), str(n, "full"),
            )
            assertEquals(action, str(n, "summary"), shown.summary)
        }
    }
}
