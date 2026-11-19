package com.jarvis.client

import com.jarvis.client.net.CardDetail
import com.jarvis.client.net.CardSummary
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.decodePendingRows
import java.io.File
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * THE BLANK CHEQUE, measured on the owner's phone on 2026-11-18.
 *
 * Two `change_own_config` cards were waiting, one asking to change his cloud
 * settings, and that one drew **no detail at all** while still drawing a normal
 * Approve. The backend had sent the detail for both; the phone dropped one on
 * the way to the screen:
 *
 *  1. `normalisePendingRow` builds the row's `summary` out of the detail's
 *     readable part and then deleted `detail` when it thought the two repeated
 *     (`PendingRows.kt`, the `detailRepeats` branch - removed here). For a
 *     cloud provider card the gate stores `{"text": "Send hard questions to …"}`
 *     (`jarvis_presets.apply_cloud`), which is a ONE-key object: every key was
 *     the preview key, so the detail was removed.
 *  2. The card never draws that derived `summary` - `ApprovalCard` passes only
 *     `item.notice?.summary` and `notice.full` into [CardSummary.shown]. Those
 *     are built from the action NAME (`jarvis_gate.notice_for`), so they can say
 *     "Jarvis wants to change one of its settings" but never which setting or to
 *     what. The only text naming the actual change was the removed detail.
 *
 * The sibling cloud card (the escalation switch) sends `{"text", "costs_money",
 * "pid"}`, so its detail was NOT a "repeat" and was drawn - exactly the "backend
 * sent detail for both, the phone drew one and not the other" the owner saw.
 *
 * The two halves of the fix, and what this test holds:
 *
 *  - the detail the backend sent now survives the read, so the card draws it
 *    ([cloudChangeCardKeepsItsDetailAndCanStillBeApproved] - it failed on the
 *    pre-fix tree, where `item.detail` was null);
 *  - a card that STILL has no readable detail never offers Approve: it says
 *    [CardDetail.MISSING_LINE] and offers a Refresh instead, keeping Deny
 *    ([aCardWithNoReadableDetailNeverOffersApprove]).
 *
 * Where this stops: `ApprovalCard` is a `@Composable`, and this project has no
 * Compose UI test, so the last test reads the card's SOURCE and holds the
 * structural claim the fix makes (Affirm is only reachable when the detail is
 * readable; Refresh is drawn otherwise). It asserts the branch, not the drawn
 * screen - the same limit `ExpiredCardShowsNoButtonsTest` names for itself. The
 * pure rule is the part a JVM test can drive directly.
 */
class CardDetailTest {

    // ----------------------------------------------------- wire rows ----

    /** A risk object every card carries, the way `jarvis_gate.pending()` sends it. */
    private fun risk() = buildJsonObject {
        put("reversible", "no")
        put("reach", "outbound")
        put("swipe_ok", false)
        put("why", "it changes what leaves this PC, and nothing can take it back")
        put("classified", true)
    }

    /**
     * The notice the PC builds for every `change_own_config` card - the words
     * the card DOES draw, built from the action name only and therefore unable
     * to name the change (`jarvis_gate.notice_for`, `approval-notice.patch`).
     */
    private fun notice() = buildJsonObject {
        put("title", "Jarvis wants to change one of its settings")
        put(
            "summary",
            "Jarvis wants to change one of its settings.",
        )
        put(
            "full",
            "it writes one setting into your own settings file. nothing has happened yet.",
        )
        put("weight", "heavy")
        put("deny_ok", true)
        put("approve_ok", false)
    }

    /**
     * One live-shaped `/api/pending` row: the gate stores `detail` as
     * `json.dumps(detail)[:4000]`, so a live wire carries it as a JSON *string*.
     * A JSON null is [JsonNull]; a missing detail is no key at all.
     */
    private fun row(action: String, detail: JsonElement? = null): JsonObject =
        buildJsonObject {
            put("id", "cloud-1")
            put("action", action)
            put("tier", "ask")
            if (detail != null) put("detail", detail)
            put("risk", risk())
            put("notice", notice())
            put("replaces_kind", JsonNull)
            put("replaces", false)
        }

    /** The gate's stored detail text, as the wire carries it. */
    private fun stored(text: String) = JsonPrimitive(text)

    private fun item(row: JsonObject): PendingItem =
        decodePendingRows(listOf(row), nowMs = 0L).items.single()

    /** The exact sentence the cloud provider card's detail carries. */
    private val cloudSentence =
        "Send hard questions to OpenAI (api.openai.com, model gpt-4o) instead of " +
            "answering them on this PC. Every message then goes to OpenAI's own servers, " +
            "under its terms, and is billed to your account there."

    /** The provider card's stored detail: a ONE-key object, which is why it was dropped. */
    private fun providerDetail() = """{"text": "$cloudSentence"}"""

    /** The escalation card's stored detail: the SAME text plus two keys (so it survived). */
    private fun escalateDetail(): String =
        "{\"text\": \"Jarvis may send a hard question to OpenAI without asking you first.\", " +
            "\"costs_money\": \"cloud\", \"pid\": \"openai\"}"

    // --------------------------------------------- the detail survives ----

    @Test
    fun cloudChangeCardKeepsItsDetailAndCanStillBeApproved() {
        val card = item(row("change_own_config", stored(providerDetail())))

        // THE REGRESSION: before this fix `item.detail` was null here - the
        // normaliser had moved the sentence into `summary` (which the card never
        // draws) and deleted the detail. This assertion failed on that tree.
        val detail = checkNotNull(card.detail) {
            "the change the backend sent must reach the card"
        }
        val readable = CardDetail.words(card.detail)
        assertTrue(
            "the exact change is readable words: $detail",
            readable.contains("Send hard questions to OpenAI"),
        )

        val actions = CardDetail.actions(card.detail)
        assertTrue("a card that says what it changes keeps its Approve", actions.approve)
        assertFalse("and needs no Refresh: it has the detail", actions.refresh)
        assertTrue("Deny is always kept", actions.deny)

        // ...and it really is what the screen draws: open, the card's body
        // carries the sentence word for word (folded, it is one tap away).
        val open = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = card.notice?.summary,
            full = card.notice?.full,
            detail = card.detail,
            expanded = true,
        )
        assertTrue(
            "the change is on the opened card: ${open.body}",
            open.body.contains("Send hard questions to OpenAI"),
        )
        val folded = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = card.notice?.summary,
            full = card.notice?.full,
            detail = card.detail,
        )
        assertEquals(
            "the PC's own short phrase is still the folded line",
            card.notice?.summary,
            folded.summary,
        )
        assertTrue("with Explain more, because the detail is folded away", folded.control)
    }

    @Test
    fun bothCloudCardsTheOwnerSawKeepTheirDetails() {
        // The asymmetry that produced "drew one and not the other": one detail
        // object had exactly the preview key, the other had two more keys. Both
        // must now arrive readable - the extra-key shape must not be the reason
        // a card keeps its words.
        val provider = item(row("change_own_config", stored(providerDetail())))
        val escalate = item(row("change_own_config", stored(escalateDetail())))
        for (card in listOf(provider, escalate)) {
            assertTrue("${card.id}: the detail survives", CardDetail.readable(card.detail))
            assertTrue("${card.id}: and it may be approved", CardDetail.actions(card.detail).approve)
        }
    }

    // ------------------------------------- no detail means no Approve ----

    @Test
    fun aCardWithNoReadableDetailNeverOffersApprove() {
        // Every shape a missing detail reaches this phone in: absent, JSON null,
        // a blank string, an empty object, and machine JSON with nothing sayable.
        val wireShapes = listOf(
            "absent" to null,
            "null" to JsonNull,
            "blank" to stored(""),
            "spaces" to stored("   "),
            "empty object" to stored("{}"),
            "nothing sayable" to stored("""{"why": null, "count": null}"""),
        )
        for ((name, detail) in wireShapes) {
            val card = item(row("change_own_config", detail))
            val actions = CardDetail.actions(card.detail)
            assertFalse("$name: a card with no readable detail must not offer Approve", actions.approve)
            assertTrue("$name: it offers Refresh in Approve's place", actions.refresh)
            assertTrue("$name: and it keeps Deny - refusing needs no reading", actions.deny)
        }
        // The sentence the owner reads is the brief's own, word for word.
        assertEquals(
            "Jarvis did not describe this change. Refresh, or deny it and ask again.",
            CardDetail.MISSING_LINE,
        )
        assertEquals("the action takes Approve's place", "Refresh", CardDetail.REFRESH)
    }

    @Test
    fun theUndescribedCardHasNothingToShowUnderItsTitle() {
        // The blank-cheque shape itself: no readable detail, so the body is
        // empty and the card's own heading and the missing-detail line are all
        // that is left. This is why a normal Approve there agreed to nothing.
        val card = item(row("change_own_config"))
        val shown = CardSummary.shown(
            mode = CardSummary.START_SHORT,
            summary = card.notice?.summary,
            full = card.notice?.full,
            detail = card.detail,
        )
        assertTrue("no body is drawn: '${shown.body}'", shown.body.isBlank())
        // The notice's generic phrase is the only text - it says "change one of
        // its settings" and cannot say which one, which is the whole defect.
        assertEquals(card.notice?.summary, shown.summary)
        assertFalse(
            "nothing in the notice names the change",
            shown.summary!!.contains("OpenAI") || shown.summary!!.contains("cloud"),
        )
    }

    @Test
    fun aCardWithACommandDetailStillApproves() {
        // The other ordinary shapes - a command, an email, a diff - are exactly
        // the plain-string details the old `detailRepeats` branch deleted.
        for (detail in listOf(
            "rm -rf ~/Documents",
            "To: doctor@clinic.example\nSubject: your appointment",
            "--- a/notes.md\n+++ b/notes.md",
        )) {
            val card = item(row("run_command", stored(detail)))
            assertTrue("a command is the detail the card must show: $detail", CardDetail.readable(card.detail))
            val actions = CardDetail.actions(card.detail)
            assertTrue("$detail: still approvable", actions.approve)
            assertFalse("$detail: and no Refresh", actions.refresh)
        }
    }

    @Test
    fun theDetailIsReadTheSameWayTheCardsBodyIs() {
        // One reading, not two: the rule and the body both go through
        // CardBodyWords, so a value the card says in words counts as readable.
        assertTrue(CardDetail.readable("""{"from": "a", "to": "b"}"""))
        assertTrue(CardDetail.readable("""{"path": "C:/x"}"""))
        assertFalse(CardDetail.readable("""{"why": null}"""))
        assertFalse(CardDetail.readable(""))
        assertFalse(CardDetail.readable(null))
    }

    // --------------------------------- the card actually uses the rule ----

    private val card = "jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt"

    /** The button row's own block, by brace depth, from its `Row(` to its close. */
    private fun buttonRow(src: String): String {
        val start = src.indexOf("AN EXPIRED CARD SHOWS NO BUTTONS")
        assertTrue("the button row's own comment is gone, so this test cannot find it", start > 0)
        val rowStart = src.lastIndexOf("Row(", start)
        var depth = 0
        var i = rowStart
        while (i < src.length) {
            when (src[i]) {
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) return src.substring(rowStart, i + 1)
                }
            }
            i++
        }
        error("the button row's block never closed")
    }

    @Test
    fun theCardDrawsNoApproveWithoutAReadableDetailAndOffersRefreshInstead() {
        val src = repoFile(card).readText()

        // Approve is gated on the rule, so the swipe (which reads `canApprove`)
        // cannot approve what the button refuses either.
        assertTrue(
            "canApprove no longer reads the detail rule: a card with no detail could approve again",
            src.contains("detailOffers.approve"),
        )
        assertTrue(
            "the detail rule is not read from CardDetail at all",
            src.contains("val detailOffers = CardDetail.actions(item.detail)"),
        )

        val row = buttonRow(src)
        val refresh = row.indexOf("if (detailOffers.refresh) {")
        assertTrue(
            "the button row no longer replaces Approve with a Refresh on a detail-less card",
            refresh > 0,
        )
        val affirm = row.indexOf("Affirm(")
        assertTrue("the button row no longer draws Approve at all", affirm > 0)
        assertTrue(
            "Approve is drawn before the detail guard, so a card with no detail would still show it",
            affirm > refresh,
        )
        val refreshBranch = row.substring(refresh, affirm)
        assertTrue(
            "the Refresh branch does not draw CardDetail.REFRESH",
            refreshBranch.contains("CardDetail.REFRESH"),
        )
        val refuse = row.indexOf("Refuse(")
        assertTrue("Deny is no longer drawn", refuse > 0)
        assertTrue(
            "Deny is inside the detail guard, but refusing must never need a reading",
            refuse < refresh,
        )
        // One decision button in the whole file, and it is inside the row.
        assertEquals(
            "a second Affirm call would be reachable with no readable detail",
            1,
            Regex("\\bAffirm\\(").findAll(src).count(),
        )
        // The sentence that says why is drawn from the one shared constant.
        assertTrue(
            "the card no longer says the detail did not arrive",
            src.contains("CardDetail.MISSING_LINE"),
        )
        // And that constant is still the owner's own words, from the PC's one
        // source (jarvis_card_words.NO_DETAIL -> CardWords.NO_DETAIL).
        val rule = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/net/CardDetail.kt").readText()
        assertTrue(
            "CardDetail stopped taking the sentence from CardWords",
            rule.contains("const val MISSING_LINE: String = CardWords.NO_DETAIL"),
        )
        val words = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/net/CardWords.kt").readText()
        assertTrue(
            "CardWords.NO_DETAIL stopped carrying the owner's sentence",
            words.contains("Jarvis did not describe this change. Refresh, or deny it and ask again."),
        )
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
}
