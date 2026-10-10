package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Backup
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Backups" on the phone ([Backup], ui/screens/BackupPlate.kt; the owner's
 * decision of 2026-09-27, docs/JARVIS-API.md section 45).
 *
 * The two fixtures are the two REAL answers `GET /api/backup` gives, taken
 * from the owner's own running PC on 2026-10-10:
 *
 *  - [PHONE_VIEW] is the shape a caller that is not this PC is sent
 *    (`jarvis_backup.view`, `here=False`): two keys and nothing else.
 *  - [PC_VIEW] is what this PC is sent, taken from
 *    `http://127.0.0.1:4719/api/backup` that morning - the folder's path, the
 *    waiting cards, the erase limit.
 *
 * WHAT THIS TEST IS FOR. The phone used to read three keys out of the PC-only
 * view (`pending_delete_older_card`, `last_delete_older`, `erase_limit`) and
 * draw a line for each. A non-PC caller never receives them, so those three
 * branches could never run on a phone, and the screen ALSO said "No backup has
 * been made yet." when the PC simply had not made one since it started - the
 * owner's PC had four backup files in its folder at the time. A dead branch is
 * not harmless and a false sentence is not acceptable, so both are held here.
 */
class BackupTest {

    /** The two keys a phone is sent, and nothing else. */
    private val PHONE_VIEW = """{"available": true, "last_backup_at": null}"""

    /** Verbatim from the owner's PC, 2026-10-10 (the PC-only view). */
    private val PC_VIEW = """{"available": true, "folder": "C:\\Users\\pcadmin\\Documents\\Jarvis Backups", "keep": 5, "pending_delete_older_card": null, "last_delete_older": null, "last_backup": null, "pending_folder_card": null, "last_folder_card": null, "pending_restore_card": null, "last_restore": null, "erase_limit": "\"Erase the words\" cannot reach into an older backup: an erased fact's original words may still be readable in a backup kept from before it was erased, until that backup ages out of the last 5 kept."}"""

    private fun obj(text: String): JsonObject = JarvisJson.parseToJsonElement(text) as JsonObject

    // --------------------------------------------------------- what arrives --

    @Test
    fun aPhoneLearnsWhenTheLastBackupWasAndNothingElse() {
        val status = Backup.parse(obj("""{"available":true,"last_backup_at":1759999999.0}"""))
        assertEquals(1759999999.0, status!!.lastBackupAt!!, 0.001)

        // The two real answers, as the owner's PC gave them.
        assertNull("no backup yet in this run", Backup.parse(obj(PHONE_VIEW))!!.lastBackupAt)
        assertNull("the PC's own view carries keys a phone must never draw",
            Backup.parse(obj(PC_VIEW))!!.lastBackupAt)

        // An older PC with no backups feature at all.
        assertNull(Backup.parse(obj("""{"available":false}""")))
        assertTrue(Backup.missing(ApiError.NotFound))
        assertTrue(Backup.missing(ApiError.NotAvailable))
        assertFalse(Backup.missing(ApiError.BadToken))
    }

    @Test
    fun aPhoneNeverSaysNoBackupHasEverBeenMade() {
        // THE BUG THIS EXISTS FOR (found 2026-10-10). `last_backup_at` is null
        // both when nothing was ever made AND when the PC's Jarvis has simply
        // restarted since the last one - `jarvis_backup._B_STATE` is memory
        // only, and the owner's PC answered null with four backup files sitting
        // in its folder. "No backup has been made yet." was therefore false on
        // screen.
        val said = Backup.line(Backup.Status(lastBackupAt = null))
        assertEquals(Backup.NEVER_MADE, said)
        assertTrue("it must not claim there has never been one:\n$said", !said.contains("yet"))
        assertTrue("it says what the PC can actually support:\n$said",
            said.contains("since it last started"))
        assertTrue("and that older backups are not gone:\n$said",
            said.contains("still in the folder you chose on your PC"))

        // With a real time it is still the plain "how long ago" line.
        assertEquals("Last backup: 3 days ago.",
            Backup.line(Backup.Status(lastBackupAt = 1_000_000.0), nowSeconds = 1_000_000.0 + 3 * 86400.0))
        assertEquals("Last backup: just now.",
            Backup.line(Backup.Status(lastBackupAt = 1_000_000.0), nowSeconds = 1_000_000.0 + 10.0))
        assertEquals("Last backup: 2 hours ago.",
            Backup.line(Backup.Status(lastBackupAt = 1_000_000.0), nowSeconds = 1_000_000.0 + 2 * 3600.0))
    }

    // ------------------------------------------------------- what it says ----

    @Test
    fun theScreenSaysWhyThereIsNoBackUpNowButton() {
        // The owner asked for one (2026-10-10). The PC refuses `/api/backup/now`
        // from anything but itself (`jarvis_owner_check.from_this_pc`), so a
        // phone over Tailscale/Meshnet gets 403 every time - the screen says so
        // instead of drawing a control that cannot work.
        val words = Backup.PC_ONLY
        assertTrue("it names the route's own refusal:\n$words",
            words.contains("refuses a backup asked for from a phone"))
        assertTrue("and says what to do instead:\n$words",
            words.contains("Jarvis Desktop on your PC") && words.contains("Settings > Backups"))
        // The recovery code, before the owner walks to the PC: shown once,
        // and lost for good if it is not written down.
        val code = Backup.CODE_WARNING
        assertTrue(code, code.contains("ONCE"))
        assertTrue(code, code.contains("never show it again"))
        assertTrue(code, code.contains("cannot"))
        // And it must never tell the owner the code stops working later
        // either: it is shown once, at the moment the backup is made.
        assertTrue(code, code.contains("When your PC makes a backup"))
    }

    // ------------------------------------------------------ what it draws ----

    @Test
    fun thePlateDrawsNoDeadBranchAndKeepsTheTwoRulesOnScreen() {
        val plate = code(PLATE)
        val model = code(MODEL)
        // The three PC-only keys are gone from BOTH halves - a branch that can
        // never run is worse than no branch, because a reader cannot tell a
        // live one from a dead one.
        for (dead in listOf("eraseLimit", "pendingDeleteOlder", "lastDeleteOlder", "DeleteOlder")) {
            assertFalse("$dead can never arrive on a phone: it is PC-only", plate.contains(dead))
            assertFalse("$dead must not be read either", model.contains(dead))
        }
        for (dead in listOf("\"erase_limit\"", "\"pending_delete_older_card\"", "\"last_delete_older\"")) {
            assertFalse("$dead is PC-only and must not be parsed on a phone", model.contains(dead))
        }
        // The two rules the owner needs are drawn whatever the read answered.
        assertTrue("the plate says why the button is not there", plate.contains("Backup.PC_ONLY"))
        assertTrue("and warns about the recovery code", plate.contains("Backup.CODE_WARNING"))
        assertEquals("/api/backup", Backup.PATH)
    }

    @Test
    fun nothingOnThisPhoneCanAskThePcToMakeABackup() {
        // The button's absence is a decision, not an oversight: no route that
        // makes a backup may be named by the phone's model, its API or its
        // screen. `/api/backup` (the read) is the only one.
        val model = code(MODEL)
        assertEquals(setOf("/api/backup"), Regex("\"(/api/[A-Za-z0-9_/]*)\"")
            .findAll(model).map { it.groupValues[1] }.toSet())
        val api = code(API)
        assertFalse("the API must not post to the backup-now route",
            api.contains("/api/backup/now"))
        assertFalse("and the plate must not either", code(PLATE).contains("/api/"))
    }

    // ------------------------------------------------------------- helpers --

    /**
     * Just the code: `//` lines and every line of a block comment dropped, so
     * an assertion on what a file DOES is never satisfied by a comment that
     * names the same thing on purpose (the same idea as LimitsTest's helper,
     * one step further because these two files explain the removed keys by
     * name).
     */
    private fun code(rel: String): String =
        repoFile(rel).readText().lines()
            .filterNot {
                val t = it.trimStart()
                t.startsWith("//") || t.startsWith("/*") || t.startsWith("*") || t.startsWith("*/")
            }
            .joinToString("\n")

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

    private val MODEL = "jarvis-client/app/src/main/java/com/jarvis/client/net/Backup.kt"
    private val API = "jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt"
    private val PLATE = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BackupPlate.kt"
}
