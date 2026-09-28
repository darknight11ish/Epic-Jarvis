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
