package com.jarvis.client

import com.jarvis.client.data.QuickTiles
import com.jarvis.client.data.QuickTiles.Decision
import com.jarvis.client.data.TileAction
import com.jarvis.client.data.WakeResume
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Phone conveniences" (docs/JARVIS-API.md section 81): the Quick Settings
 * tiles' safe list and what a tap does, and the restart notice's decision.
 */
class QuickTilesTest {

    private val staleWords = "The connection to your PC is catching up."

    private fun decide(
        action: TileAction?,
        paired: Boolean = true,
        connected: Boolean = true,
        stale: Boolean = false,
        appLock: Boolean = false,
        phoneLocked: Boolean = false,
    ) = QuickTiles.decide(action, paired, connected, stale, appLock, phoneLocked, staleWords)

    @Test
    fun theSafeListIsExactlyTheFiveChosenOnesAndNeverAnApproval() {
        assertEquals(
            listOf("focus", "timer", "brief_me", "stop_everything", "pc_play_pause"),
            TileAction.entries.map { it.wire },
        )
        for (a in TileAction.entries) {
            for (bad in listOf("approve", "deny", "rush", "latch", "bulk", "decide")) {
                assertFalse("${a.wire} looks like $bad", a.wire.contains(bad) || a.tileLabel.lowercase().contains(bad))
            }
        }
        assertEquals(3, QuickTiles.SLOTS)
    }

    @Test
    fun savedChoicesReadBackAndUnknownOnesAreNothing() {
        TileAction.entries.forEach { assertEquals(it, TileAction.fromWire(it.wire)) }
        assertNull(TileAction.fromWire("approve"))
        assertNull(TileAction.fromWire(null))
        val slots = QuickTiles.slotsFrom { listOf("timer", null, "approve_all").getOrNull(it) }
        assertEquals(listOf(TileAction.TIMER, null, null), slots)
    }

    @Test
    fun anActingTileIsHeldOnAStaleLinkButStopEverythingNeverIs() {
        for (a in listOf(TileAction.FOCUS, TileAction.TIMER, TileAction.PC_PLAY_PAUSE)) {
            assertEquals(Decision.Held(staleWords), decide(a, stale = true))
            assertEquals(Decision.Run, decide(a))
            assertEquals(Decision.Reconnect, decide(a, connected = false))
        }
        assertEquals(Decision.Run, decide(TileAction.STOP_EVERYTHING, stale = true))
        assertEquals(Decision.Run, decide(TileAction.STOP_EVERYTHING, connected = false))
        assertEquals(Decision.Run, decide(TileAction.STOP_EVERYTHING, appLock = true, phoneLocked = true))
    }

    @Test
    fun briefMeOnlyOpensTheAppAndAnEmptySlotOpensTheChooser() {
        assertEquals(Decision.OpenBriefing, decide(TileAction.BRIEF_ME))
        assertEquals(Decision.OpenBriefing, decide(TileAction.BRIEF_ME, stale = true, appLock = true, phoneLocked = true))
        assertEquals(Decision.OpenChooser, decide(null, paired = false))
        assertEquals(Decision.Reconnect, decide(TileAction.TIMER, paired = false))
    }

    @Test
    fun withAppLockOnALockedPhoneIsUnlockedFirst() {
        assertEquals(Decision.UnlockThenRun, decide(TileAction.TIMER, appLock = true, phoneLocked = true))
        assertEquals(Decision.Run, decide(TileAction.TIMER, appLock = true, phoneLocked = false))
        assertEquals(Decision.Run, decide(TileAction.TIMER, appLock = false, phoneLocked = true))
        // Stale still wins over unlocking: nothing to unlock for.
        assertEquals(Decision.Held(staleWords), decide(TileAction.FOCUS, stale = true, appLock = true, phoneLocked = true))
    }

    @Test
    fun underAppLockAWidgetButtonOnlyOpensJarvisExceptStopEverything() {
        // The owner, 2026-09-28: under App lock the home-screen widget's
        // buttons open the locked app first and never act on their own.
        for (a in listOf(TileAction.FOCUS, TileAction.TIMER, TileAction.PC_PLAY_PAUSE, TileAction.BRIEF_ME)) {
            assertTrue(a.wire, QuickTiles.widgetOpensApp(a, appLock = true))
            // Settings that cannot be read count as locked.
            assertTrue(a.wire, QuickTiles.widgetOpensApp(a, appLock = null))
        }
        // Stop everything only makes Jarvis do less: never behind an unlock.
        assertFalse(QuickTiles.widgetOpensApp(TileAction.STOP_EVERYTHING, appLock = true))
        assertFalse(QuickTiles.widgetOpensApp(TileAction.STOP_EVERYTHING, appLock = null))
        // App lock off: the buttons act as before ("Brief me" still only opens the app).
        for (a in listOf(TileAction.FOCUS, TileAction.TIMER, TileAction.PC_PLAY_PAUSE, TileAction.STOP_EVERYTHING)) {
            assertFalse(a.wire, QuickTiles.widgetOpensApp(a, appLock = false))
        }
        assertTrue(QuickTiles.widgetOpensApp(TileAction.BRIEF_ME, appLock = false))
        // Tiles keep their own rule: an unlocked phone under App lock still runs.
        assertEquals(Decision.Run, decide(TileAction.TIMER, appLock = true, phoneLocked = false))
    }

    @Test
    fun theTileShowsWhetherItCanActNow() {
        assertTrue(QuickTiles.ready(TileAction.TIMER, paired = true, connected = true, stale = false))
        assertFalse(QuickTiles.ready(TileAction.TIMER, paired = true, connected = true, stale = true))
        assertTrue(QuickTiles.ready(TileAction.STOP_EVERYTHING, paired = true, connected = false, stale = true))
        assertFalse(QuickTiles.ready(null, paired = true, connected = true, stale = false))
        assertEquals(QuickTiles.SUB_STALE, QuickTiles.subtitle(TileAction.FOCUS, true, true, true))
        assertEquals(QuickTiles.SUB_OFFLINE, QuickTiles.subtitle(TileAction.FOCUS, true, false, false))
        assertEquals(QuickTiles.SUB_CHOOSE, QuickTiles.subtitle(null, true, true, false))
        assertEquals(QuickTiles.SUB_UNPAIRED, QuickTiles.subtitle(TileAction.TIMER, false, false, false))
    }

    @Test
    fun theTimerIsOnePlainTenMinuteTimer() {
        assertEquals("{\"kind\":\"timer\",\"seconds\":600}", QuickTiles.timerBody())
    }

    @Test
    fun aSecondMuteTapInsideTheRoundTripIsDroppedInsteadOfSentAgain() {
        // Android audit 2026-10-08. `shown` only moves when the PC's re-read
        // lands, so the tap is the opposite of what the tile draws.
        assertEquals(true, QuickTiles.muteCommand(shown = false, asked = null))
        assertEquals(false, QuickTiles.muteCommand(shown = true, asked = null))
        // A mute is in flight and the tile still shows the old state: the
        // second tap is dropped, never sent as a second "mute" (the bug -
        // tap to mute, tap again, still muted).
        assertNull(QuickTiles.muteCommand(shown = false, asked = true))
        assertNull(QuickTiles.muteCommand(shown = true, asked = false))
        // The re-read has agreed (the tile now draws what was asked for):
        // the next tap is a real toggle again, so unmuting still works.
        assertEquals(false, QuickTiles.muteCommand(shown = true, asked = true))
        assertEquals(true, QuickTiles.muteCommand(shown = false, asked = false))
    }

    @Test
    fun playPauseFollowsThePcsOwnSentence() {
        assertEquals("pause", QuickTiles.playPauseAction("Playing: “Song” by Band."))
        assertEquals("play", QuickTiles.playPauseAction("Paused: “Song” by Band."))
        assertEquals("play", QuickTiles.playPauseAction("Nothing seems to be playing right now."))
        assertEquals("play", QuickTiles.playPauseAction(null))
    }

    @Test
    fun privateWordsHideThePcsSentenceButNeverARefusal() {
        val pc = "Stopped: reading your email."
        assertEquals(pc, QuickTiles.shown(TileAction.STOP_EVERYTHING, ok = true, said = pc, private = false))
        assertFalse(QuickTiles.shown(TileAction.STOP_EVERYTHING, ok = true, said = pc, private = true).contains("email"))
        assertFalse(QuickTiles.shown(TileAction.FOCUS, ok = true, said = "Focus on taxes.", private = true).contains("taxes"))
        assertEquals(staleWords, QuickTiles.shown(TileAction.FOCUS, ok = false, said = staleWords, private = true))
        assertEquals("Paused.", QuickTiles.shown(TileAction.PC_PLAY_PAUSE, ok = true, said = "Paused.", private = true))
    }

    @Test
    fun theLinkTileSendsWhatMuteCommandSaysAndHoldsItUntilTheReRead() {
        // The pure decision above is only worth anything if the tile uses it.
        // Source, not behaviour: the tap needs a bound TileService on a phone
        // (CI's Gradle build is the first compile). Before the fix this read
        // `setMuted(!muted)` in place and never held anything.
        val src = listOf(
            File("src/main/java/com/jarvis/client/service/LinkTileService.kt"),
            File("app/src/main/java/com/jarvis/client/service/LinkTileService.kt"),
        ).first { it.isFile }.readText()
        assertTrue("the tap must ask the pure rule", src.contains("QuickTiles.muteCommand("))
        assertFalse("never negate the shown value in place again", src.contains("setMuted(!muted)"))
        assertTrue("and send that answer", src.contains("setMuted(muted)"))
        assertTrue("holding what it asked for", src.contains("asked.value = muted"))
        assertTrue("answering the tap before the round trip", src.contains("\"Muting...\""))
    }

    @Test
    fun everyTileLabelSaysWhatItsTapDoes() {
        // Two labels did not, found by the sweep of 2026-10-10 and both
        // confirmed in the code. A tile has no room to explain itself: whatever
        // the label says IS the promise, so a label that promises something the
        // tap does not do is a trap.

        // 1. "Brief me" only OPENS the app on the Briefing screen
        // ([QuickTiles.decide] answers OpenBriefing and never asks the PC for
        // one). It is not made to start one instead: a briefing names new
        // senders, and a tile draws on a locked screen. The smaller, honest
        // change is the label.
        assertEquals("Open briefing", QuickTiles.tileLabel(TileAction.BRIEF_ME, 0))
        assertEquals("the Settings chooser says the same thing", "Open briefing",
            TileAction.BRIEF_ME.choiceLabel)
        assertEquals("the tap itself is unchanged", Decision.OpenBriefing, decide(TileAction.BRIEF_ME))
        // The fix is the TILE's own words, not the shared list's: TileAction
        // .tileLabel is the PC's `jarvis_widgets.ACTIONS`, drawn by the
        // home-screen widget's buttons on both apps and held byte for byte by
        // contract/widget-cases.json (JarvisWidgetsTest) - so it stays exactly
        // as the PC has it.
        assertEquals("the PC's shared word is untouched", "Brief me", TileAction.BRIEF_ME.tileLabel)
        val tile = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/service/QuickTileService.kt")
            .readText()
        assertTrue("the tile draws the tile's own words",
            tile.contains("tile.label = QuickTiles.tileLabel(action, slot)"))
        assertFalse("never the shared word straight onto a tile again",
            tile.contains("action?.tileLabel"))
        // The other four are unchanged, so this cannot quietly rename them.
        assertEquals("Focus session", QuickTiles.tileLabel(TileAction.FOCUS, 0))
        assertEquals("Play/pause PC", QuickTiles.tileLabel(TileAction.PC_PLAY_PAUSE, 2))
        assertEquals("an empty slot still says which tile it is",
            "Jarvis tile 3", QuickTiles.tileLabel(null, 2))
        // ...and the words the owner reads elsewhere were corrected with it.
        assertFalse("the lock note still promises a briefing",
            QuickTiles.LOCK_NOTE.contains("\"Brief me\""))
        assertTrue(QuickTiles.LOCK_NOTE.contains("\"Open briefing\""))

        // 2. The link tile is a MUTE SWITCH ([QuickTiles.muteCommand],
        // LinkTileService). It used to draw "Jarvis" - the app's own name - so
        // tapping the tile with Jarvis's name on it silently muted Jarvis.
        assertEquals("Mute Jarvis", QuickTiles.LINK_TILE_LABEL)
        val link = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/service/LinkTileService.kt")
            .readText()
        assertTrue("the tile draws that label", link.contains("tile.label = QuickTiles.LINK_TILE_LABEL"))
        assertFalse("never the app's own name again", link.contains("tile.label = \"Jarvis\""))

        // Android's own tile editor reads the MANIFEST, not the runtime label,
        // so the service must be declared with the same words - and the string
        // it points at must be those words.
        val manifest = repoFile("jarvis-client/app/src/main/AndroidManifest.xml").readText()
        val at = manifest.indexOf(".service.LinkTileService\"")
        assertTrue("the link tile is declared", at >= 0)
        val block = manifest.substring(at, manifest.indexOf("</service>", at))
        assertTrue("the manifest label names the tap:\n$block",
            block.contains("android:label=\"@string/link_tile_label\""))
        val strings = repoFile("jarvis-client/app/src/main/res/values/strings.xml").readText()
        assertTrue("and that string is the same label",
            strings.contains("<string name=\"link_tile_label\">${QuickTiles.LINK_TILE_LABEL}</string>"))
    }

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

    @Test
    fun theTileServiceNeverDecidesACard() {
        val src = listOf(
            File("src/main/java/com/jarvis/client/service/QuickTileService.kt"),
            File("app/src/main/java/com/jarvis/client/service/QuickTileService.kt"),
        ).first { it.isFile }.readText()
        for (bad in listOf("decide(item", ".approve", "approveAll", "denyAll", "clearRush", "decisionBlocker")) {
            assertFalse("QuickTileService must not call $bad", src.contains(bad))
        }
        val manifest = listOf(File("src/main/AndroidManifest.xml"), File("app/src/main/AndroidManifest.xml"))
            .first { it.isFile }.readText()
        for (name in listOf("QuickTileOneService", "QuickTileTwoService", "QuickTileThreeService")) {
            val at = manifest.indexOf(".service.$name\"")
            assertTrue("$name is declared", at >= 0)
            val block = manifest.substring(at, manifest.indexOf("</service>", at))
            assertTrue(block.contains("android.permission.BIND_QUICK_SETTINGS_TILE"))
            assertTrue(block.contains("android.service.quicksettings.action.QS_TILE"))
        }
    }

    @Test
    fun theRestartNoticeOnlyForAPairedPhoneThatWasListening() {
        assertTrue(WakeResume.offer(WakeResume.BOOT, paired = true, wanted = true))
        assertTrue(WakeResume.offer(WakeResume.UPDATED, paired = true, wanted = true))
        assertFalse(WakeResume.offer(WakeResume.BOOT, paired = true, wanted = false))
        assertFalse(WakeResume.offer(WakeResume.BOOT, paired = false, wanted = true))
        assertFalse(WakeResume.offer("android.intent.action.SCREEN_ON", paired = true, wanted = true))
        assertFalse(WakeResume.offer(null, paired = true, wanted = true))
        assertTrue(WakeResume.title(WakeResume.BOOT).contains("restarted"))
        assertTrue(WakeResume.title(WakeResume.UPDATED).contains("updated"))
        assertEquals("android.intent.action.BOOT_COMPLETED", WakeResume.BOOT)
        assertEquals("android.intent.action.MY_PACKAGE_REPLACED", WakeResume.UPDATED)
    }

    @Test
    fun theBootReceiverNeverStartsTheMicrophone() {
        val src = listOf(
            File("src/main/java/com/jarvis/client/service/BootReceiver.kt"),
            File("app/src/main/java/com/jarvis/client/service/BootReceiver.kt"),
        ).first { it.isFile }.readText()
        assertFalse(src.contains("WakeWordService.start"))
        assertTrue(src.contains("WakeResumeNotifier.post"))
    }
}
