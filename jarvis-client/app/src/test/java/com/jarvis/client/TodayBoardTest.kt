package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.Today
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The Today board (`GET /api/today/cockpit`, GTD-2, 2026-10-18) on the phone:
 * the contract's own answers read the way the phone reads them, the sections'
 * words held to the desktop's, and the wiring that makes the parity audit's
 * one real gap (G1, 2026-10-31) closed.
 *
 * The desktop draws this board at the bottom of its Today page
 * (`jarvis-desktop/src/today.js`'s board section, `brain.js`'s
 * `todayBoardNodes`); the phone draws it at the bottom of its own Today plate,
 * and this file reads `today.js` so a word that drifts apart fails here. That
 * is the same one-copy-of-the-shapes rule the desktop's own `tests/today.mjs`
 * keeps for the card page.
 *
 * What this proves:
 *  - the hidden answer is read as hidden and draws no words; absence of the
 *    board (an older PC) is NOT a failure, but a failed READ says so - never an
 *    empty day (silent-failure audit 2026-10-27, row 5);
 *  - a due reminder's rows, prompt and Break offer exactly as the desktop
 *    derives them; a sensitive one never offers Break;
 *  - the next steps carry the project's "work list" first;
 *  - the said-I'd-do shelf shows nothing while OFF, and the switch's own
 *    answer is read as waiting / on / off - the phone never decides its card;
 *  - the phone calls the one route, with ?hidden=1 when the private lists are
 *    hidden, and its tap only copies a prompt (nothing is created).
 */
class TodayBoardTest {

    private fun json(text: String): JsonObject = JarvisJson.parseToJsonElement(text).jsonObject

    // ------------------------------------------------------------ the read ----

    @Test
    fun `the board asks with hidden=1 while the private lists are hidden`() {
        assertEquals("/api/today/cockpit", Today.cockpitPath(hidden = false))
        assertEquals("/api/today/cockpit?hidden=1", Today.cockpitPath(hidden = true))
        assertEquals("/api/today/cockpit", Today.COCKPIT_PATH)
    }

    @Test
    fun `the board answer is read whole, and the sections it does not carry are empty`() {
        val b = Today.cockpit(
            json(
                """{"available": true, "unspoken_commitments_enabled": true, "rollover_cards": [],
                    "due_reminders": [
                      {"id": "s1", "kind": "reminder", "text": "Call the vet", "due": 1761900000.0,
                       "when": "07:00", "went_off": true, "overdue": false},
                      {"id": "s2", "kind": "alarm", "text": "", "when": "09:30",
                       "went_off": false, "overdue": true}
                    ],
                    "active_next_steps": [
                      {"kind": "goal", "id": "g1", "name": "Move house", "step": "Phone the solicitor",
                       "by": "Nov 3"},
                      {"kind": "project", "id": "p1", "name": "Loft", "step": "Book the survey", "by": ""}
                    ],
                    "proposals": [
                      {"text": "fix the shed door", "suggested_due": "next week",
                       "source_conv_id": "c1"}
                    ]}""",
            ),
        )!!
        assertTrue(b.available)
        assertFalse(b.hidden)
        assertTrue(b.unspokenEnabled)
        assertEquals(2, b.due.size)
        assertEquals(2, b.steps.size)
        assertEquals(1, b.proposals.size)
    }

    @Test
    fun `a hidden board carries no words, and a quiet one is empty without a lie`() {
        val hidden = Today.cockpit(json("""{"available": true, "hidden": true}"""))!!
        assertTrue(hidden.hidden)
        assertTrue(hidden.due.isEmpty())
        assertTrue(hidden.steps.isEmpty())
        assertTrue(hidden.proposals.isEmpty())
        assertFalse("a hidden answer must not claim the shelf is on", hidden.unspokenEnabled)
        val quiet = Today.cockpit(json("""{"available": true}"""))!!
        assertEquals(0, quiet.due.size + quiet.steps.size + quiet.proposals.size)
    }

    @Test
    fun `a PC with no board at all says nothing, and a failed read says it could not ask`() {
        // An older install: the desktop draws nothing for 404/501, and so does this.
        assertNull(Today.boardFailure(ApiError.NotFound))
        assertNull(Today.boardFailure(ApiError.NotAvailable))
        assertNull(Today.boardFailure(ApiError.Server(501, "not implemented")))
        // A failed read is never an empty day.
        assertEquals(Today.BOARD_UNREADABLE, Today.boardFailure(ApiError.Server(500, "boom")))
        assertEquals(Today.BOARD_UNREADABLE,
            Today.boardFailure(ApiError.Unreachable("timeout")))
        // A 503 keeps the PC's own sentence when it sent one.
        val why = Today.boardFailure(
            ApiError.Server(503, """{"available": false, "why": "This PC has no board module yet."}"""),
        )
        assertEquals("This PC has no board module yet.", why)
        assertEquals(Today.BOARD_UNREADABLE, Today.boardFailure(ApiError.Server(503, "not json")))
    }

    // ---------------------------------------------------------- the sections ----

    @Test
    fun `a due reminder's row says what the desktop says - hidden, went off, overdue`() {
        val shown = Today.Due(
            id = "s1", kind = "reminder", text = "Call the vet", whenShown = "07:00",
            wentOff = true, overdue = false, sensitive = false, stuckHint = true,
            suggestedPrompt = "",
        )
        assertEquals("reminder", shown.tag)
        assertEquals("Call the vet", shown.title)
        assertEquals(listOf("Went off (07:00)"), shown.meta)
        assertEquals("Help me with this reminder: Call the vet.", shown.prompt())
        assertEquals("Help me break this into 3 easy steps: Call the vet.", shown.breakPrompt())

        val overdue = shown.copy(text = "Pay the bill", wentOff = false, overdue = true, kind = "alarm")
        assertEquals(listOf("Overdue - 07:00"), overdue.meta)
        assertEquals("alarm", overdue.tag)

        val bare = shown.copy(whenShown = "", wentOff = false, overdue = false)
        assertEquals(emptyList<String>(), bare.meta)

        val hidden = shown.copy(text = "")
        assertEquals("(hidden) reminder", hidden.title)
        assertNull("a hidden row offers no Break", hidden.breakPrompt())
        assertEquals("Help me with a reminder that is due.", hidden.copy(suggestedPrompt = "").prompt())
    }

    @Test
    fun `a sensitive or non-stuck reminder never offers Break, and the PC's prompt wins`() {
        val base = Today.Due(
            id = "s1", kind = "reminder", text = "Renew the passport", whenShown = "07:00",
            wentOff = false, overdue = false, sensitive = false, stuckHint = false,
            suggestedPrompt = "The PC's own prompt.",
        )
        assertEquals("The PC's own prompt.", base.prompt())
        assertNull("not stuck: no Break", base.breakPrompt())
        assertNotNull("stuck and not sensitive: Break", base.copy(stuckHint = true).breakPrompt())
        assertNull("sensitive: never Break", base.copy(stuckHint = true, sensitive = true).breakPrompt())
    }

    @Test
    fun `next steps carry the project's work list first, then its name, then the date`() {
        val goal = Today.Step(id = "g1", kind = "goal", name = "Move house",
            step = "Phone the solicitor", by = "Nov 3")
        assertEquals("goal", goal.tag)
        assertEquals("Phone the solicitor", goal.title)
        assertEquals(listOf("Move house", "Nov 3"), goal.meta)
        val project = Today.Step(id = "p1", kind = "project", name = "Loft",
            step = "Book the survey", by = "")
        assertEquals("project", project.tag)
        assertEquals(listOf("work list", "Loft"), project.meta)
    }

    @Test
    fun `the said-I'd-do shelf shows nothing while OFF, and a proposal's tap is a prompt`() {
        val board = Today.cockpit(
            json(
                """{"available": true, "unspoken_commitments_enabled": false,
                    "proposals": [{"text": "fix the shed door", "suggested_due": "next week"}]}""",
            ),
        )!!
        assertEquals("off: no rows at all", emptyList<Today.Proposal>(), Today.proposalRows(board))
        val on = board.copy(unspokenEnabled = true)
        assertEquals(1, Today.proposalRows(on).size)
        val p = Today.proposalRows(on).single()
        assertEquals(listOf("a good day: next week"), p.meta)
        assertEquals("Remind me to fix the shed door (next week).", p.prompt())
        assertEquals("Remind me to do the thing I mentioned.", Today.remindPrompt(
            Today.Proposal(text = " ", suggestedDue = "")))
    }

    @Test
    fun `the switch's answer is read as waiting, on or off - and waiting changes nothing`() {
        val waiting = Today.switchSaid(
            json("""{"ok": true, "waiting": true, "enabled": false, "message": "Waiting for your approval. Nothing has changed yet."}"""),
        )
        assertTrue(waiting.waiting)
        assertFalse(waiting.enabled)
        assertEquals("Waiting for your approval. Nothing has changed yet.", waiting.text)
        val on = Today.switchSaid(json("""{"ok": true, "enabled": true, "waiting": false,
            "message": "Said-I'd-do suggestions are on."}"""))
        assertFalse(on.waiting)
        assertTrue(on.enabled)
        val off = Today.switchSaid(json("""{"ok": true, "enabled": false, "waiting": false}"""))
        assertFalse(off.waiting)
        assertFalse(off.enabled)
        assertEquals(Today.PROPOSALS_TURNED_OFF, off.text)
        assertEquals("""{"enabled":true}""", Today.unspokenBody(true))
        assertEquals("""{"enabled":false}""", Today.unspokenBody(false))
    }

    // ------------------------------------------------- the one copy of words ----

    @Test
    fun `every board word is the desktop's own`() {
        val js = file("jarvis-desktop/src/today.js")
        // The file wraps long sentences as "a " + "b"; join that spelling so a
        // sentence can be looked for as the one string the owner reads.
        val joined = js.replace(Regex("\"\\s*\\+\\s*\""), "")
        val words = listOf(
            Today.DUE_TITLE, Today.DUE_DETAIL, Today.NEXT_TITLE, Today.NEXT_DETAIL,
            Today.PROPOSALS_TITLE, Today.PROPOSALS_DETAIL, Today.PROPOSALS_OFF,
            Today.PROPOSALS_ON_LABEL, Today.PROPOSALS_OFF_LABEL,
            Today.PROPOSALS_WAITING, Today.PROPOSALS_TURNED_ON, Today.PROPOSALS_TURNED_OFF,
            Today.DO_THIS_LABEL, Today.DO_THIS_COPIED, Today.BREAK_LABEL, Today.BREAK_COPIED,
            Today.SNOOZE_LABEL, Today.SENSITIVE_NOTE, Today.REMIND_LABEL,
            Today.BOARD_UNREADABLE,
        )
        for (word in words) {
            val quoted = "\"$word\""
            assertTrue("today.js does not say: $word", joined.contains(quoted))
        }
        // The prompt fallbacks are today.js's, too (its doThisPrompt etc.), and
        // the empty-shelf line is brain.js's own - it lives there, not in today.js.
        assertTrue(js.contains("Help me with this reminder: "))
        assertTrue(js.contains("Help me break this into 3 easy steps: "))
        assertTrue(js.contains("Remind me to "))
        assertTrue(file("jarvis-desktop/src/brain.js")
            .contains("\"Nothing new you said you would do.\""))
    }

    // ------------------------------------------------------------- the wiring ----

    @Test
    fun `the phone reads the route and asks the PC for the switch - never decides it`() {
        val api = file("jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt")
        assertTrue("JarvisApi has no board read", api.contains("suspend fun todayCockpit("))
        assertTrue("the board read keeps a 503's sentence",
            api.contains("probeKeeping503(Today.cockpitPath(hidden))"))
        assertTrue("JarvisApi has no switch", api.contains("suspend fun setTodayUnspoken("))
        assertTrue("the switch goes through postExplained",
            api.contains("postExplained(Today.COCKPIT_PATH, Today.unspokenBody(enabled))"))

        val runtime = file("jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt")
        assertTrue("the runtime has no board read", runtime.contains("suspend fun todayCockpit("))
        assertTrue("the runtime has no switch", runtime.contains("suspend fun setTodayUnspoken("))
        assertTrue("the switch's card is never decided here",
            !runtime.substringAfter("suspend fun setTodayUnspoken(")
                .substringBefore("private fun onScheduleEvent").contains("decide("))
        // The waiting switch is re-read from the board, and only while shown.
        assertTrue(runtime.contains("api.todayCockpit(hidden = false)"))

        val plate = file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/TodayPlate.kt")
        for (drawn in listOf(
            "Today.DUE_TITLE", "Today.NEXT_TITLE", "Today.PROPOSALS_TITLE",
            "Today.PROPOSALS_ON_LABEL", "Today.PROPOSALS_OFF_LABEL",
            "Today.DO_THIS_LABEL", "Today.BREAK_LABEL", "Today.REMIND_LABEL",
            "Today.boardFailure(", "Schedule.SNOOZE", "PrivateClipboard.copy",
        )) {
            assertTrue("the plate does not draw/use $drawn", plate.contains(drawn))
        }
        assertTrue("the board is read with the private lists' own state",
            plate.contains("JarvisRuntime.todayCockpit(privateHidden)"))
        // A tap only copies a prompt; nothing is created from a proposal.
        assertTrue(plate.contains("copyPrompt(proposal.prompt(), Today.DO_THIS_COPIED)"))
        // The board lives in the existing Today plate - no new menu id.
        assertTrue(file("jarvis-client/app/src/main/java/com/jarvis/client/ui/MenuPlaces.kt")
            .contains("\"today\" to \"brain.work.today\""))
        assertTrue(file("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainScreen.kt")
            .contains("plate(\"today\", drawn = { true })"))
    }

    /** A repository file, from Gradle's working folder (`jarvis-client/app`). */
    private fun file(rel: String): String {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f.readText()
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
