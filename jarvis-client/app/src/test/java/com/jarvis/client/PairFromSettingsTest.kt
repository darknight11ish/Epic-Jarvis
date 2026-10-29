package com.jarvis.client

import com.jarvis.client.net.Devices
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Pair with your PC" in Settings, Devices - the way back into pairing from
 * the phone's own Settings screen (2026-10-28).
 *
 * Why it exists, in the owner's words: a phone that would not pair, and a
 * Settings screen with "nothing for pair/reconnect to the PC". Both halves
 * were true. The pairing flow itself was complete (`net/Pairing.kt`,
 * `PairingScreen.kt`), but Settings offered exactly one pairing-adjacent
 * control - "Unpair & clear the token" - which takes the pairing AWAY, and
 * the pairing screen is drawn only while `!paired || repairing`, so a phone
 * that still holds a token never saw it again.
 *
 * What these tests hold:
 *  - the sentence choice: a PC that cannot be reached is not reported as a
 *    PC that is too old ([Devices.notShown]);
 *  - the button is in BOTH branches of the card, because the branch that used
 *    to say "does not have a device list yet" is where an unreachable PC
 *    lands;
 *  - it is drawn ABOVE "Unpair & clear the token", so the safe action is read
 *    first;
 *  - pressing it really opens the pairing screen (`repairing = true`), not
 *    merely a Settings row that looks like it should.
 *
 * The source pins follow `SettingsJumpTest`'s own idiom (read the real file,
 * comments stripped) rather than trusting a second hand-kept list.
 */
class PairFromSettingsTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
    private val root = "jarvis-client/app/src/main/java/com/jarvis/client/"

    // ── The sentence choice ───────────────────────────────────────────────

    @Test
    fun an_unreachable_pc_is_never_reported_as_an_old_one() {
        // The bug this fixes: `version == null` means "have not reached the
        // PC", not "your PC is too old". Before 2026-10-28 the card drew
        // Devices.MISSING for both, so a paired phone whose PC was off, asleep
        // or logged out of Tailscale was told its PC "does not have a device
        // list yet" - a claim about the PC with no evidence behind it.
        assertEquals(Devices.NOT_REACHED, Devices.notShown(versionKnown = false))
        assertFalse(
            "an unreached PC must not be described with the too-old sentence",
            Devices.notShown(versionKnown = false) == Devices.MISSING,
        )
    }

    @Test
    fun a_pc_that_answered_and_has_no_list_still_says_so() {
        // The other half is a real fact: the PC answered, and it has no device
        // list. That sentence stays exactly as it was.
        assertEquals(Devices.MISSING, Devices.notShown(versionKnown = true))
    }

    @Test
    fun both_sentences_say_what_the_owner_can_do_or_why_not() {
        assertTrue(
            "the unreachable sentence names the cause, not a code",
            Devices.NOT_REACHED.contains("cannot reach your PC"),
        )
        assertTrue(
            "the too-old sentence still names the PC's own state",
            Devices.MISSING.contains("device list"),
        )
    }

    // ── The button, and where it sits ─────────────────────────────────────

    @Test
    fun the_devices_card_draws_the_pair_button_above_unpair() {
        val src = code(repoFile(screens + "DevicesPlate.kt").readText())
        val pair = src.indexOf("Devices.PAIR_BUTTON")
        val unpair = src.indexOf("Devices.UNPAIR_BUTTON")
        assertTrue("the card offers Pair with your PC", pair >= 0)
        assertTrue("and still offers Unpair & clear the token", unpair >= 0)
        // Order is the point: the action that KEEPS the pairing is read
        // before the one that throws it away.
        assertTrue(
            "Pair with your PC is drawn above Unpair & clear the token",
            pair < unpair,
        )
        assertTrue(
            "the pair button is a Primary action, not a quiet link",
            Regex("Primary\\(\\s*text = Devices\\.PAIR_BUTTON").containsMatchIn(src),
        )
    }

    @Test
    fun the_settings_row_offers_it_even_when_the_pc_cannot_be_reached() {
        val src = code(repoFile(screens + "SettingsScreen.kt").readText())
        // Both branches of `item(key = "devices")`: the real device list, and
        // the "no list" one an unreachable PC lands in.
        assertTrue(
            "the device-list branch hands the pair action to the card",
            src.contains("DevicesSection(onPair = onPairWithPc)"),
        )
        assertTrue(
            "the no-list branch draws the same button",
            src.contains("com.jarvis.client.net.Devices.PAIR_BUTTON"),
        )
        assertTrue(
            "and the branch picks its sentence from the two real reasons",
            src.contains("com.jarvis.client.net.Devices.notShown(version != null)"),
        )
    }

    @Test
    fun pressing_it_opens_the_pairing_screen_and_not_only_settings() {
        // A row that leaves the owner where he was would be the same bug with
        // a friendlier label. The pair screen is drawn while `repairing`, so
        // the handler must set it.
        val src = code(repoFile(root + "MainActivity.kt").readText())
        val at = src.indexOf("onPairWithPc = {")
        assertTrue("Settings is given onPairWithPc", at >= 0)
        val handler = src.substring(at, minOf(at + 700, src.length))
        assertTrue("it starts re-pairing", handler.contains("repairing = true"))
        assertTrue(
            "it fills in the saved address, as Platform checks does",
            handler.contains("pairingHost = JarvisRuntime.settings.host.value"),
        )
        assertTrue("and it hands the screen over to the pairing flow", handler.contains("nav.resetTo(Screen.HOME)"))
    }

    @Test
    fun the_wording_stays_the_apps_own() {
        // The pair screen's title is "Pair with your desktop"
        // (PairingScreen.kt); the Devices card and the owner both say "PC",
        // so the button does too - one phrase, not two inventions.
        assertEquals("Pair with your PC", Devices.PAIR_BUTTON)
        val pairScreen = code(repoFile(screens + "PairingScreen.kt").readText())
        assertTrue(
            "the pair screen still calls the destination a desktop",
            pairScreen.contains("\"Pair with your desktop\""),
        )
        // Plain, beginner-readable, and short enough to be a button label:
        // no jargon the owner would have to look up.
        assertTrue("the label fits on one button", Devices.PAIR_BUTTON.length <= 24)
        for (jargon in listOf("token", "auth", "endpoint", "keystore", "base url", "URL")) {
            assertFalse(
                "the label says none of the jargon: $jargon",
                Devices.PAIR_BUTTON.contains(jargon, ignoreCase = true),
            )
        }
        assertTrue(
            "the help line says the old pairing survives a failed attempt",
            Devices.PAIR_HELP.contains("stay until new ones connect"),
        )
    }

    // ── Helpers (the same two SettingsJumpTest uses) ──────────────────────

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var d: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (d != null) {
            val f = File(d, rel)
            if (f.isFile) return f
            d = d.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** Just the code, with whole-line `//` comments dropped. */
    private fun code(text: String): String =
        text.lines().filterNot { it.trimStart().startsWith("//") }.joinToString("\n")
}
