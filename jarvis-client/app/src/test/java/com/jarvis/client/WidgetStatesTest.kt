package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.decodePendingRows
import com.jarvis.client.widget.ApprovalWidgetRules
import com.jarvis.client.widget.WidgetStates
import com.jarvis.client.widget.WidgetStates.Approval
import com.jarvis.client.widget.WidgetStates.Board
import com.jarvis.client.widget.WidgetStates.Link
import com.jarvis.client.widget.WidgetStates.Read
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The owner's 2026-10-27 bug, pinned so it cannot come back silently.
 *
 * On two phones every Jarvis home-screen widget sat on a spinner for ever
 * while the app itself was connected and drawing live PC data. The spinner
 * was not this app's - it was the launcher's `initialLayout`, Glance's own
 * bare ProgressBar, because no Glance worker could run in the release APK
 * (WorkManager's InputMerger had lost its constructor to R8; see
 * app/proguard-rules.pro, which carries the device evidence).
 *
 * A JVM test cannot execute Glance or WorkManager, so it cannot prove that
 * fix directly - CI's `phone-unit-tests` compiles the widget code but does not
 * run a launcher. What this file CAN prove, and does, is the half that is
 * testable and was actually missing:
 *
 *  1. every widget draw ends in a terminal state, and no "loading" state
 *     exists to fall into (there is no such enum member);
 *  2. every wait has a ceiling, and a blocked one really does return;
 *  3. a timeout draws the error sentence, not a spinner and not an empty
 *     widget;
 *  4. App lock still hides the card's words;
 *  5. a real `/api/pending` row still decodes and still reaches the card;
 *  6. no widget's `initialLayout` names Glance's spinner any more - the
 *     layout the owner actually saw, checked as source text because it is
 *     only ever read by the launcher.
 */
class WidgetStatesTest {

    private val bools = listOf(false, true)

    // ------------------------------------------------- the states itself ----

    @Test
    fun `every approvals combination lands in exactly one terminal state`() {
        for (ready in bools) for (paired in bools) for (connected in bools) for (stale in bools) {
            for (waiting in 0..2) {
                val state = WidgetStates.approval(ready, paired, connected, stale, waiting)
                val label = "ready=$ready paired=$paired connected=$connected stale=$stale waiting=$waiting"

                // A card needs a link that can deliver the decision, a paired
                // run and a real queue. Everything else is a message.
                assertEquals(label, ready && paired && connected && waiting > 0, state == Approval.CARD)
                assertEquals(
                    label,
                    ready && paired && waiting <= 0 && (stale || !connected),
                    state == Approval.NOT_CHECKED,
                )
                assertEquals(
                    label,
                    ready && paired && waiting <= 0 && !stale && connected,
                    state == Approval.EMPTY,
                )
                assertEquals(
                    label,
                    ready && paired && waiting > 0 && !connected,
                    state == Approval.UNREACHABLE,
                )
                assertEquals(label, !ready, state == Approval.NOT_STARTED)
                assertEquals(label, ready && !paired, state == Approval.NOT_PAIRED)
            }
        }
    }

    @Test
    fun `an unread queue is not an empty one`() {
        // The distinction the widget exists for: nothing fetched yet must
        // never read as "nothing waiting". Stale, or link down, and empty.
        assertEquals(Approval.NOT_CHECKED, WidgetStates.approval(true, true, false, false, 0))
        assertEquals(Approval.NOT_CHECKED, WidgetStates.approval(true, true, true, true, 0))
        // Only a live, paired link may say there is nothing waiting.
        assertEquals(Approval.EMPTY, WidgetStates.approval(true, true, true, false, 0))
        // A last-known card on a stale-but-connected link is still shown.
        assertEquals(Approval.CARD, WidgetStates.approval(true, true, true, true, 1))
    }

    @Test
    fun `there is no loading state in any widget`() {
        // The regression pin. If someone adds LOADING to any of these, this
        // fails: a widget must always have something to say instead.
        for (state in Approval.entries) assertFalse(state.name, state.name.contains("LOAD"))
        for (state in Board.entries) assertFalse(state.name, state.name.contains("LOAD"))
        for (state in Link.entries) assertFalse(state.name, state.name.contains("LOAD"))
    }

    @Test
    fun `every message state has words, and none of them is a spinner`() {
        for (state in Approval.entries) {
            val (headline, sub) = WidgetStates.approvalWords(state)
            if (state == Approval.EMPTY || state == Approval.CARD) {
                assertEquals(state.name, "" to "", headline to sub) // real content instead
            } else {
                assertTrue(state.name, headline.isNotBlank() && sub.isNotBlank())
                assertFalse(state.name, (headline + sub).contains("loading", ignoreCase = true))
            }
        }
        for (state in Board.entries) {
            val (headline, sub) = WidgetStates.boardWords(state)
            if (state == Board.CONTENT) {
                assertEquals("" to "", headline to sub)
            } else {
                assertTrue(state.name, headline.isNotBlank() && sub.isNotBlank())
                assertFalse(state.name, (headline + sub).contains("loading", ignoreCase = true))
            }
        }
        for (state in Link.entries) {
            assertTrue(state.name, WidgetStates.linkWords(state).isNotBlank())
        }
    }

    @Test
    fun `a failed or timed-out read is an error sentence, never an empty widget`() {
        val live = { read: Read -> WidgetStates.board(true, true, true, true, read) }
        assertEquals(Board.CONTENT, live(Read.CONTENT))
        assertEquals(Board.GONE, live(Read.GONE))
        assertEquals(Board.FAILED, live(Read.FAILED))
        assertEquals(Board.TIMED_OUT, live(Read.TIMED_OUT))
        // The exact sentence the brief asked for, and not the same words as a
        // deleted widget: "could not reach" and "it is gone" send the reader
        // to different places.
        val timedOut = WidgetStates.boardWords(Board.TIMED_OUT)
        assertEquals("Could not reach your PC" to "Tap to open Jarvis and reconnect", timedOut)
        assertFalse(WidgetStates.boardWords(Board.GONE) == timedOut)
        assertFalse(WidgetStates.boardWords(Board.FAILED) == timedOut)
    }

    @Test
    fun `the board never asks the PC before it can use the answer`() {
        // The pre-read order the old `when` had: not started, not paired, no
        // widget chosen, then not live. Each is its own words, so a widget
        // that cannot read the PC never claims to be empty.
        assertEquals(Board.NOT_STARTED, WidgetStates.board(false, true, true, true, Read.CONTENT))
        assertEquals(Board.NOT_PAIRED, WidgetStates.board(true, false, true, true, Read.CONTENT))
        assertEquals(Board.NO_WIDGET, WidgetStates.board(true, true, false, true, Read.CONTENT))
        assertEquals(Board.STALE, WidgetStates.board(true, true, true, false, Read.CONTENT))
        assertEquals(Board.CONTENT, WidgetStates.board(true, true, true, true, Read.CONTENT))
    }

    @Test
    fun `the quick link says which of offline and not-paired it is`() {
        assertEquals(Link.NOT_STARTED, WidgetStates.link(false, false, false, false))
        assertEquals(Link.NOT_PAIRED, WidgetStates.link(true, false, false, false))
        assertEquals(Link.OFFLINE, WidgetStates.link(true, true, false, false))
        assertEquals(Link.RECONNECTING, WidgetStates.link(true, true, false, true))
        assertEquals(Link.CONNECTED, WidgetStates.link(true, true, true, false))
        // A connected link wins over a stale reconnecting flag, so the two
        // can never both be drawn.
        assertEquals(Link.CONNECTED, WidgetStates.link(true, true, true, true))
    }

    // ---------------------------------------------------------- bounds ----

    @Test
    fun `a wait that never finishes still ends`() = runBlocking {
        val began = System.nanoTime()
        val answer = WidgetStates.bounded(150) {
            // The shape a widget really meets: a BLOCKING call (the runtime's
            // `initialize` builds objects and reads the Keystore). It runs on
            // the worker dispatcher, so blocking there is fine - what matters
            // is that the waiting side stops at the budget. Written the
            // obvious way (`withTimeoutOrNull { withContext(IO) { ... } }`)
            // this took the full 1.5 s, which is the bug this pins.
            Thread.sleep(1_500)
            "never reached"
        }
        val elapsedMs = (System.nanoTime() - began) / 1_000_000
        assertNull("the budget must be what ends the wait", answer)
        assertTrue("waited ${elapsedMs}ms for a 150ms budget", elapsedMs < 1_000)
    }

    @Test
    fun `a wait that finishes inside the budget returns its value`() = runBlocking {
        assertEquals("done", WidgetStates.bounded(2_000) { "done" })
    }

    @Test
    fun `a cancelled wait is a timeout, not a crash`() = runBlocking {
        assertNull(WidgetStates.bounded(50) { delay(5_000); "late" })
    }

    @Test
    fun `the budgets are short enough to be a home screen`() {
        // The general HTTP client's read timeout is 120 s on purpose (chat
        // streams). A widget must never sit on that clock.
        assertTrue(WidgetStates.INIT_TIMEOUT_MS in 1..15_000)
        assertTrue(WidgetStates.READ_TIMEOUT_MS in 1..30_000)
    }

    // -------------------------------------------------------- App lock ----

    @Test
    fun `App lock hides the card's own words, even when it has some`() {
        assertEquals(
            ApprovalWidgetRules.HIDDEN_TITLE,
            ApprovalWidgetRules.cardTitle(hidden = true, noticeTitle = "Let me read your email", title = "Read email"),
        )
        assertEquals(
            "",
            ApprovalWidgetRules.cardDetail(hidden = true, noticeBody = "the clinic letter", riskWhy = "because"),
        )
        // Unhidden, the notice wins and the row prose is only a fallback.
        assertEquals(
            "Let me read your email",
            ApprovalWidgetRules.cardTitle(hidden = false, noticeTitle = "Let me read your email", title = "Read email"),
        )
        assertEquals("Read email", ApprovalWidgetRules.cardTitle(false, noticeTitle = "  ", title = "Read email"))
        assertEquals("the clinic letter", ApprovalWidgetRules.cardDetail(false, "the clinic letter", "because"))
        assertEquals("because", ApprovalWidgetRules.cardDetail(false, null, "because"))
        // Unreadable settings still count as locked, so the card is drawn but
        // its words are not.
        assertTrue(ApprovalWidgetRules.hidden(settingsKnown = false, appLock = false, privateLists = false))
        assertEquals(Approval.CARD, WidgetStates.approval(true, true, true, false, 1))
    }

    // --------------------------------- the buttons on the card itself ----

    /** The owner's 2026-10-28 field bug: on a locked phone the card offered a
     *  button labelled "Deny", and the tap only opened the app - the label
     *  promised a refusal the tap could not perform. The safety rule stays (a
     *  locked phone never denies an unseen card), so the fix is the label: a
     *  locked card draws one button that says what it does. */
    @Test
    fun `a locked card draws no Deny and exactly one app-opening button`() {
        // The same real `/api/pending` row the decode test uses, so the shape
        // is checked against a row the PC actually sent - and `deny_ok` must
        // change nothing while locked.
        val first = pendingRows().first()
        for (denyOk in listOf(first.notice?.denyOk != false, true, false)) {
            val buttons = ApprovalWidgetRules.cardButtons(hidden = true, denyOk = denyOk)
            val labels = buttons.map { it.label }
            assertFalse("locked, denyOk=$denyOk: $labels", labels.contains("Deny"))
            assertEquals("locked, denyOk=$denyOk: $labels", 1, buttons.size)
            assertEquals(
                "the one locked button opens the app; it never decides",
                listOf(ApprovalWidgetRules.Tap.OPEN_APP),
                buttons.map { it.tap },
            )
            assertEquals(ApprovalWidgetRules.UNLOCK_LABEL, buttons.single().label)
        }
    }

    @Test
    fun `an unlocked card is Deny acting directly, then Review opening the app`() {
        // Deny is the widget's one direct decision, and it comes first; Review
        // is the way to Approve and opens the app (it is never a one-tap yes).
        val open = ApprovalWidgetRules.cardButtons(hidden = false, denyOk = true)
        assertEquals(listOf("Deny", "Review"), open.map { it.label })
        assertEquals(
            listOf(ApprovalWidgetRules.Tap.DENY_NOW, ApprovalWidgetRules.Tap.OPEN_APP),
            open.map { it.tap },
        )
        // An item the PC marked unsafe to refuse unread has no Deny at all:
        // the same condition the lock-screen notification already runs on.
        assertEquals(listOf("Review"), ApprovalWidgetRules.cardButtons(false, denyOk = false).map { it.label })
    }

    /** A JVM test cannot draw Glance, so this is the half that is checkable
     *  about the composition itself: the words come from the rule above, and
     *  the tap comes from the button's own [ApprovalWidgetRules.Tap]. A label
     *  literal in the drawing code is exactly how the 2026-10-28 bug happened. */
    @Test
    fun `the card's buttons are the rule's, not literals in the drawing code`() {
        val widget = moduleFile("src/main/java/com/jarvis/client/widget/ApprovalWidget.kt").readText()
        assertTrue(widget.contains("ApprovalWidgetRules.cardButtons("))
        // Code lines only: the comments explain the old bug and may name it.
        val code = widget.lines().filterNot {
            val line = it.trim()
            line.startsWith("//") || line.startsWith("*") || line.startsWith("/*")
        }.joinToString("\n")
        assertFalse("a label literal is how the label and the tap drifted apart", code.contains("label = \"Deny\""))
        assertFalse("a label literal is how the label and the tap drifted apart", code.contains("label = \"Review\""))
        assertTrue(code.contains("button.tap == ApprovalWidgetRules.Tap.DENY_NOW"))
    }

    // ------------------------------------------------- the real payload ----

    @Test
    fun `a real pending row still decodes, and still reaches the card`() {
        val items = pendingRows()
        assertNotNull(items.firstOrNull())
        val first = items.first()
        assertEquals(Approval.CARD, WidgetStates.approval(true, true, true, false, items.size))
        // What the widget's headline is built from, under App lock and without.
        assertEquals(ApprovalWidgetRules.HIDDEN_TITLE, ApprovalWidgetRules.cardTitle(true, first.notice?.title, first.title))
        assertTrue(ApprovalWidgetRules.cardTitle(false, first.notice?.title, first.title).isNotBlank())
        // And with no queue at all, the same live link says "Nothing waiting".
        assertEquals(Approval.EMPTY, WidgetStates.approval(true, true, true, false, 0))
    }

    /**
     * The real `/api/pending` rows, from the same fixture
     * `PendingRowsContractTest` uses - generated from the real backend
     * `notice_for`, not typed to suit the client.
     */
    private fun pendingRows(): List<PendingItem> {
        val text = requireNotNull(javaClass.classLoader?.getResource("contract/pending-rows.json")) {
            "contract/pending-rows.json is missing - run backend/test_approval_contract.py --write"
        }.readText()
        val fixture = JarvisJson.parseToJsonElement(text) as JsonObject
        val nowMs = (fixture["now"]!!.jsonPrimitive.content.toDouble() * 1000).toLong()
        return decodePendingRows((fixture["rows"] as JsonArray).toList(), nowMs).items
    }

    // ------------------------------------------------- the layout itself ----

    @Test
    fun `no widget points at Glance's spinner any more`() {
        // The layout the owner saw was `glance_default_loading_layout` - one
        // ProgressBar and nothing else. A launcher only ever reads these XMLs,
        // so source text is the only way a JVM test can hold this. Only the
        // ATTRIBUTE is read, not the whole file: the comments deliberately
        // name the old layout to explain why it went.
        val attribute = Regex("""android:(initialLayout|previewLayout)="([^"]+)"""")
        for (name in listOf("widget_approval_info", "widget_board_info", "widget_quicklink_info")) {
            val xml = moduleFile("src/main/res/xml/$name.xml").readText()
            val found = attribute.findAll(xml).associate { it.groupValues[1] to it.groupValues[2] }
            assertEquals("$name initialLayout", "@layout/widget_initial", found["initialLayout"])
            assertEquals("$name previewLayout", "@layout/widget_initial", found["previewLayout"])
        }
        val initial = moduleFile("src/main/res/layout/widget_initial.xml").readText()
        // The ELEMENT, not the word: the comment above it explains what a
        // ProgressBar was doing there, and must be allowed to say so.
        assertFalse("the fallback layout must not be a spinner", initial.contains("<ProgressBar"))
        assertTrue(initial.contains("@string/widget_initial_words"))
    }

    /** A file under the app module, found from wherever the test process starts. */
    private fun moduleFile(relative: String): File {
        // Gradle runs unit tests from the module directory; an IDE may run
        // them from the checkout root. Try every shape of that, walking up
        // until one exists, then fail loudly rather than skip.
        val shapes = listOf(relative, "app/$relative", "jarvis-client/app/$relative")
        var dir: File? = File("").absoluteFile
        while (dir != null) {
            for (shape in shapes) {
                val candidate = File(dir, shape)
                if (candidate.isFile) return candidate
            }
            dir = dir.parentFile
        }
        throw AssertionError("could not find $relative from ${File("").absolutePath}")
    }
}
