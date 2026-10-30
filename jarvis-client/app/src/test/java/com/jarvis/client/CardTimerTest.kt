package com.jarvis.client

import com.jarvis.client.net.decodePendingRows
import com.jarvis.client.ui.approval.countdownReadout
import java.io.File
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The timer on a card with a limited time (the owner's ruling, 2026-10-30:
 * *"if there is a card with a limited time of any kind, be sure to put the
 * timer on it"*).
 *
 * WHY THIS EXISTS. The phone had a deadline readout since DEF-010 (2026-10-11)
 * and the only thing missing on 2026-10-30 was the number: `no-deadline-cards.patch`
 * stopped sending `expires_in`, so `expiresAtMs` was always null and the card
 * drew no clock - his app-builder card ran out twice while he was reading it.
 * `show-card-timer.patch` sends the field again, for a routine card whose
 * REQUEST is still waiting. This test holds the phone's half of that: the row
 * is read, the deadline is computed at the moment of the read, and the readout
 * says what it says - with no Compose and no device.
 *
 * WHAT IT CANNOT DO, said plainly. `ApprovalCard` is a `@Composable`, so this
 * cannot draw the card. It drives the two pure pieces the card reads
 * (`normalisePendingRow` through `decodePendingRows`, and `countdownReadout`),
 * and pins - as text - that the card body still passes the deadline to them,
 * the same way `ExpiredCardShowsNoButtonsTest` pins its branch. The real check
 * is the phone in the owner's hand; `phone-unit-tests` runs this one.
 *
 * THE MUTATION ON THE RECORD. Taking `expires_in` out of `normalisePendingRow`
 * fails `a routine card ... carries a live countdown` and the countdown-going-
 * down case; making the label `EXPIRING SOON` at 61 s fails the boundary case.
 * Both were driven before this landed, so this is not a test that has never
 * failed.
 */
class CardTimerTest {

    /** A fixed "now", so nothing here depends on when it is run. */
    private val nowMs = 1_800_000_000_000L

    private fun row(id: String, action: String, expiresIn: Double? = null): JsonObject {
        val fields = mutableMapOf<String, JsonElement>(
            "id" to JsonPrimitive(id),
            "action" to JsonPrimitive(action),
            "tier" to JsonPrimitive("ask"),
            "created" to JsonPrimitive(1.0),
        )
        if (expiresIn != null) fields["expires_in"] = JsonPrimitive(expiresIn)
        return JsonObject(fields)
    }

    private fun read(vararg rows: JsonObject, at: Long = nowMs) = decodePendingRows(rows.toList(), at)

    @Test
    fun `a routine card whose request is still waiting carries a live countdown`() {
        val got = read(row("a1", "send_email", expiresIn = 900.0))
        assertEquals(1, got.items.size)
        val item = got.items.single()
        val deadline = item.expiresAtMs
        assertTrue("a waiting routine card drew no timer at all", deadline != null)
        // The backend sends seconds LEFT; the phone turns that into a moment on
        // its own clock, so the two machines never have to agree on the time.
        assertEquals(nowMs + 900_000L, deadline)
        assertTrue("the timer is not in the future", deadline!! > nowMs)
    }

    @Test
    fun `the countdown goes DOWN when the queue is read again`() {
        // Two reads 20 seconds apart, as the poller makes them: the same card,
        // 20 fewer seconds left. That is the number on the card going down.
        val first = read(row("a1", "send_email", expiresIn = 900.0)).items.single()
        val second = read(row("a1", "send_email", expiresIn = 880.0), at = nowMs + 20_000L)
            .items.single()
        // The moment it points at is the SAME one either way: it is the
        // REQUEST's end, not a number re-started by each read.
        assertEquals(first.expiresAtMs, second.expiresAtMs)
        // ...which is what makes the number on the card go down: 20 seconds
        // passed, so 20 fewer seconds are left even though the deadline is
        // unchanged. (The first version of this assertion compared the two
        // DEADLINES and asked for a 20 s difference - impossible by
        // construction, and phone-unit-tests caught it in CI.)
        val firstLeft = first.expiresAtMs!! - nowMs
        val secondLeft = second.expiresAtMs!! - (nowMs + 20_000L)
        assertEquals(
            "a later read with fewer seconds left did not count down",
            20_000L,
            firstLeft - secondLeft,
        )
        assertEquals("EXPIRES IN", countdownReadout(firstLeft / 1000L).label)
        // A card raised late (a short wait) gets a genuinely shorter timer.
        val short = read(row("a2", "send_email", expiresIn = 42.0)).items.single()
        assertEquals(nowMs + 42_000L, short.expiresAtMs)
    }

    @Test
    fun `a ceremony card and a request that has ended draw no timer at all`() {
        // What the backend sends for the four ceremonies of the 2026-10-23
        // ruling: no field at all, because their request has no last moment.
        val ceremonies = read(
            row("pair", "pair_device"),
            row("key", "register_approval_key"),
            row("restore", "restore_backup"),
        )
        assertEquals(3, ceremonies.items.size)
        ceremonies.items.forEach {
            assertNull("${it.id} (a ceremony) was given a countdown", it.expiresAtMs)
        }
        // A routine card whose request has already ended is sent no field
        // either - the card keeps its buttons and loses its clock.
        assertNull(read(row("done", "send_email")).items.single().expiresAtMs)
        // An unreadable value is never a countdown: not a string, and not a
        // number longer than a day, which would draw a clock that never ends.
        assertNull(read(row("s", "send_email", expiresIn = 90_000.0)).items.single().expiresAtMs)
        assertNull(
            decodePendingRows(
                listOf(
                    JsonObject(
                        mapOf(
                            "id" to JsonPrimitive("t"),
                            "action" to JsonPrimitive("send_email"),
                            "tier" to JsonPrimitive("ask"),
                            "expires_in" to JsonPrimitive("120"),
                        ),
                    ),
                ),
                nowMs,
            ).items.single().expiresAtMs,
        )
    }

    @Test
    fun `zero is still "expired now", and a negative is no timer at all`() {
        // The backend never sends 0 any more (show-card-timer.patch rounds UP
        // and sends nothing once the request has ended), but an OLD backend did
        // mean "expired now" by it, and that reading must not change on the way
        // through this client: 0 seconds left is a deadline at this instant.
        val zero = read(row("z", "send_email", expiresIn = 0.0)).items.single()
        assertEquals(nowMs, zero.expiresAtMs)
        // Nothing negative ever becomes a moment in the past, which would draw
        // a card that is expired before it is shown.
        assertNull(read(row("n", "send_email", expiresIn = -5.0)).items.single().expiresAtMs)
    }

    @Test
    fun `the last minute is the warning minute, and the clock reads by itself`() {
        // What the readout says. Above a minute: the plain clock. In the last
        // minute: the same digits under "EXPIRING SOON" and in warning ink.
        val minuteBefore = countdownReadout(61)
        assertEquals("EXPIRES IN", minuteBefore.label)
        assertEquals("01:01", minuteBefore.digits)
        assertFalse(minuteBefore.soon)

        val oneMinute = countdownReadout(60)
        assertEquals("EXPIRING SOON", oneMinute.label)
        assertEquals("01:00", oneMinute.digits)
        assertTrue(oneMinute.soon)

        assertEquals("EXPIRING SOON", countdownReadout(59).label)
        assertEquals("00:59", countdownReadout(59).digits)
        assertEquals("EXPIRING SOON", countdownReadout(1).label)
        assertEquals("00:01", countdownReadout(1).digits)

        // Past ten minutes the seconds are noise, so the readout says minutes.
        assertEquals("15 MIN", countdownReadout(900).digits)
        assertEquals("10 MIN", countdownReadout(600).digits)
        assertEquals("2 H 05 MIN", countdownReadout(7_500).digits)
        // Zero is not "about to expire": the card stops drawing the readout.
        assertFalse(countdownReadout(0).soon)
        // Nothing here can be negative; a clock handed one says 00:00.
        assertEquals("00:00", countdownReadout(-5).digits)
    }

    @Test
    fun `the card body still hands its deadline to the readout, and only while it has one`() {
        // A JVM test cannot compose the card, so this is the STRUCTURAL half:
        // the readout exists only when the row carries a deadline and the card
        // has not passed it. Removing either guard silently removes the timer
        // from the screen while every case above still passes.
        val src = repoFile(CARD).readText()
        assertTrue(
            "the card no longer draws the readout only when the row carries a deadline",
            src.contains("if (expiry != null && secondsLeft != null && !expired) {"),
        )
        assertTrue(
            "the readout is no longer fed the card's own seconds",
            src.contains("ExpiryCountdown(secondsLeft)"),
        )
        assertTrue(
            "the readout no longer comes from the one function this test drives",
            src.contains("val readout = countdownReadout(left)"),
        )
        assertTrue(
            "the readout's label and its warning colour no longer come from the same answer",
            src.contains("readout.label") && src.contains("if (readout.soon)"),
        )
        // The expiry still comes from the row, never from a clock the card owns.
        assertTrue(
            "the card stopped taking its deadline from the row",
            src.contains("val expiry = item.expiresAtMs"),
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

    private companion object {
        const val CARD = "jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt"
    }
}
