package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.Backup
import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Backups" on the phone ([Backup], ui/screens/BackupPlate.kt; the owner's
 * decision of 2026-09-27 for the feature, his request of 2026-10-10 for a
 * button answered for real on 2026-10-13; docs/JARVIS-API.md section 45).
 *
 * THE THREE FIXTURES are the three REAL answers the PC gives:
 *
 *  - [STATUS] is `GET /api/backup/status` - the read-only view a phone gets,
 *    written to the shape `jarvis_backup.status_view` returns.
 *  - [PHONE_VIEW] is the old `GET /api/backup` answer a non-PC caller is sent
 *    (`jarvis_backup.view`, `here=False`), taken from the owner's own running PC
 *    on 2026-10-10: two keys and nothing else. An older PC still sends only
 *    this, and the screen must still say something true.
 *  - [PC_VIEW] is what this PC is sent, verbatim from
 *    `http://127.0.0.1:4719/api/backup` that morning - the folder's PATH, the
 *    waiting cards, the erase limit. None of that may be drawn here.
 *
 * WHAT THIS TEST IS FOR. Three things the screen may not get wrong:
 *
 *  1. THE CODE GATE. Every backup is locked with its own one-time code, the
 *     code is stored nowhere, and a new backup deletes the oldest of five. So a
 *     run whose code was never read does not merely add a file nobody can open
 *     - it pushes out an older backup whose own code still works. The plate
 *     must therefore hold the code on screen and refuse to finish until the
 *     owner has ticked that he saved it.
 *  2. THE HONEST LIMIT. Nothing on a phone can prove a backup OPENS; only the
 *     code opens one and codes are only typed on the PC. The screen says so and
 *     never draws a pass as "this backup works".
 *  3. A FAILURE IS NEVER A SUCCESS. A run that failed is drawn, in the PC's own
 *     words, from `last_attempt`.
 */
class BackupTest {

    /** `GET /api/backup/status`, the shape `jarvis_backup.status_view` returns. */
    private val STATUS = """{"available": true, "folder": "Jarvis Backups", "keep": 5, "kept": 3,
        "last_backup_at": 1759999999.0, "last_backup_name": "jarvis-backup-20261010-030000.jbak",
        "verify": {"ok": true, "why": "complete", "words": "Jarvis checked this file just now: it is a complete, well-formed backup, and nothing about it has changed since it was written.",
        "proves_open": false, "limit": "Jarvis cannot prove from your phone that a backup OPENS - that needs the recovery code, and codes are only ever typed on your PC."},
        "last_attempt": {"ok": true, "at": 1759999999.0, "error": ""}, "prepared": null}"""

    /** The two keys a phone was sent before this feature. Still parses. */
    private val PHONE_VIEW = """{"available": true, "last_backup_at": null}"""

    /** Verbatim from the owner's PC, 2026-10-10 (the PC-only view). */
    private val PC_VIEW = """{"available": true, "folder": "C:\\Users\\pcadmin\\Documents\\Jarvis Backups", "keep": 5, "pending_delete_older_card": null, "last_delete_older": null, "last_backup": null, "pending_folder_card": null, "last_folder_card": null, "pending_restore_card": null, "last_restore": null, "erase_limit": "\"Erase the words\" cannot reach into an older backup: an erased fact's original words may still be readable in a backup kept from before it was erased, until that backup ages out of the last 5 kept."}"""

    private fun obj(text: String): JsonObject = JarvisJson.parseToJsonElement(text) as JsonObject

    // ------------------------------------------------------- what arrives ----

    @Test
    fun aPhoneLearnsWhenWhereHowManyAndWhetherTheNewestChecksOut() {
        val s = Backup.parse(obj(STATUS))!!
        val check = s.check!!
        assertEquals(1759999999.0, s.lastBackupAt!!, 0.001)
        assertEquals("Jarvis Backups", s.folder)
        assertEquals(5, s.keep)
        assertEquals(3, s.kept)
        assertTrue(check.ok)
        assertEquals("complete", check.why)
        assertTrue("the PC sent no proof that it opens", !check.provesOpen)
        assertTrue(Backup.verifies(s))

        // The four lines the brief asks for, in the PC's own numbers.
        assertEquals("Last backup: just now.",
            Backup.line(s, nowSeconds = 1759999999.0 + 10.0))
        assertEquals("In: Jarvis Backups", Backup.folderLine(s))
        assertEquals("Kept: 3 of the last 5.", Backup.keptLine(s))
        assertTrue(Backup.checkLine(s)!!.contains("well-formed backup"))

        // The honest limit, drawn beside the pass rather than left to be assumed.
        assertTrue(Backup.checkLine(s)!!.isNotBlank())
        assertTrue("the limit names the recovery code as what is missing:\n${check.limit}",
            check.limit.contains("recovery code") && check.limit.contains("PC"))

        // An older PC: the old two-key answer still parses, and the screen says
        // only what that PC can support - no folder, no count, nothing invented.
        val old = Backup.parse(obj(PHONE_VIEW))!!
        assertNull(old.lastBackupAt)
        assertNull(old.folder)
        assertNull("no count arrived, so no count line is drawn", Backup.keptLine(old))
        assertNull("no folder arrived, so no folder line is drawn", Backup.folderLine(old))
        assertNull("no check arrived, so no check line is drawn", Backup.checkLine(old))
        assertEquals(Backup.NEVER_MADE, Backup.line(old))

        // The PC's own view carries keys a phone must never draw: it parses to
        // the same absence, never to the PC's folder path.
        val pc = Backup.parse(obj(PC_VIEW))!!
        assertNull(pc.folder)
        assertNull(pc.kept)
        assertNull(pc.attempt)
        assertFalse("the PC's own path must not reach the screen", Backup.folderLine(pc) != null)

        // An older PC with no backups feature at all.
        assertNull(Backup.parse(obj("""{"available":false}""")))
        assertTrue(Backup.missing(ApiError.NotFound))
        assertTrue(Backup.missing(ApiError.NotAvailable))
        assertFalse(Backup.missing(ApiError.BadToken))
    }

    @Test
    fun theFolderIsNamedByItsLastSegmentAndNeverByTheWholePath() {
        // The PC sends the last segment (`jarvis_backup._folder_name`), and this
        // side never invents a longer one: a full path names the owner's Windows
        // account, which is what docs/ARCHITECTURE.md section 8 keeps off a phone
        // for the memory store's own path, for the same reason.
        val s = Backup.parse(obj(STATUS))!!
        val words = Backup.folderLine(s)!!
        assertFalse("the owner's account must not be in the words:\n$words",
            words.contains("\\") || words.contains("/") || words.contains("pcadmin"))
        assertEquals("In: Jarvis Backups", words)
    }

    @Test
    fun aBackupThatFailedIsSaidAndNeverDrawnAsASuccess() {
        val failed = Backup.parse(obj("""{"available":true,"folder":"Jarvis Backups","keep":5,
            "kept":0,"last_backup_at":null,"last_backup_name":null,
            "verify":{"ok":false,"why":"empty","words":"There is no backup in the folder on your PC yet.","proves_open":false,"limit":"Jarvis cannot prove from your phone that a backup OPENS."},
            "last_attempt":{"ok":false,"at":1759999999.0,"error":"could not write the backup file (OSError)"}}"""))!!
        val why = failed.check!!
        val said = Backup.attemptLine(failed)!!
        assertFalse(Backup.verifies(failed))
        assertFalse(why.ok)
        assertTrue("the failure is drawn, in the PC's own words:\n$said",
            said.contains("could not write the backup file (OSError)"))
        assertFalse("and nothing on this screen claims a backup that is not there",
            Backup.line(failed).contains("Last backup"))
        assertEquals(Backup.NEVER_MADE, Backup.line(failed))
        assertEquals("Kept: 0 of the last 5.", Backup.keptLine(failed))

        // A failure with no sentence still says it failed, rather than silence.
        val bare = Backup.parse(obj("""{"available":true,"kept":0,"keep":5,
            "verify":{"ok":false,"why":"missing","words":"","proves_open":false,"limit":"x"},
            "last_attempt":{"ok":false,"at":1.0,"error":""}}"""))!!
        assertEquals("The last backup attempt failed.", Backup.attemptLine(bare))
    }

    @Test
    fun aPhoneNeverSaysNoBackupHasEverBeenMade() {
        // THE BUG THIS EXISTS FOR (found 2026-10-10, and it must not come back
        // through the new door). `last_backup_at` used to be the PC's memory
        // only, and the owner's PC answered null the morning after a restart
        // with four backup files sitting in its folder. "No backup has been
        // made yet." was therefore false on screen. The words now say what the
        // FOLDER holds.
        val said = Backup.line(Backup.Status(null, null, null, null, null, null, null, false))
        assertEquals(Backup.NEVER_MADE, said)
        assertTrue("it must not claim there has never been one:\n$said", !said.contains("yet"))
        assertTrue("it says where the truth is read from:\n$said", said.contains("folder"))
    }

    // -------------------------------------------------------- the two calls --

    @Test
    fun askingThePcForABackupHandsBackTheCodeAndNothingElse() {
        val asked = Backup.asked(obj("""{"ok":true,"pending":true,"id":"abc123",
            "recovery_code":"4F3DH-P6F4M-BXRS8-9JJT3","at":1759999999.0,
            "folder":"Jarvis Backups","keep":5,
            "message":"Nothing is written until you say you have saved that code."}"""))
        assertTrue(asked is Backup.Asked.Ready)
        val p = (asked as Backup.Asked.Ready).prepared
        assertEquals("abc123", p.id)
        assertEquals("4F3DH-P6F4M-BXRS8-9JJT3", p.code)
        assertEquals("Jarvis Backups", p.folder)
        assertEquals(23, p.code.length)
        assertEquals(3, p.code.count { it == '-' })
        assertTrue(p.words.contains("Nothing is written until you say you have saved"))

        // The PC's refusal is an ANSWER with words in it, never a bare failure.
        val no = Backup.asked(obj("""{"ok":false,"error":"Choose a folder for backups first (Settings, Backups)."}"""))
        assertTrue(no is Backup.Asked.Refused)
        assertTrue((no as Backup.Asked.Refused).words.contains("Choose a folder"))

        // A body with no `ok` at all - a proxy's error page - is a refusal, NOT
        // a prepared run with an empty code. Otherwise "save this code" would
        // be drawn over nothing.
        val junk = Backup.asked(obj("""{"detail":"Not Found"}"""))
        assertTrue(junk is Backup.Asked.Refused)
        assertTrue((junk as Backup.Asked.Refused).words.isNotBlank())
    }

    @Test
    fun onlyATickedCodeGoesBackAndItGoesBackWithoutTheHyphens() {
        // The PC shows the code in four groups of five and stores the groups
        // together (`jarvis_backup.generate_code` / `_clean_code`), so the
        // hyphens are presentation: sending them or not is the same code.
        assertEquals("""{"id":"abc123","code":"4F3DHP6F4MBXRS89JJT3"}""",
            Backup.commitBody("abc123", "4F3DH-P6F4M-BXRS8-9JJT3"))
        assertEquals(Backup.commitBody("abc123", "4F3DH-P6F4M-BXRS8-9JJT3"),
            Backup.commitBody("abc123", "4f3dh p6f4m bxrs8 9jjt3"))
        // The id is echoed, and a quote in it cannot break the JSON.
        assertEquals("""{"id":"a\"b","code":"X"}""", Backup.commitBody("a\"b", "x"))
    }

    @Test
    fun aWrittenBackupIsReadAndARefusalIsNotMistakenForOne() {
        val w = Backup.written(obj("""{"ok":true,"name":"jarvis-backup-20261013-030000.jbak",
            "at":1759999999.0,"size":4096,"folder":"Jarvis Backups","counts":{"memory.db":12}}"""))
        assertNotNull(w)
        assertEquals("jarvis-backup-20261013-030000.jbak", w!!.name)
        assertEquals(4096L, w.size)
        // `ok: false` is never read as a written backup, whatever else arrives.
        assertNull(Backup.written(obj("""{"ok":false,"error":"nothing was written"}""")))
        assertNull(Backup.written(obj("""{"ok":true}""")))
        assertEquals("nothing was written",
            Backup.refusalWords(obj("""{"ok":false,"error":"nothing was written"}""")))
        // And a refusal with no words is translated from the PC's status code.
        assertTrue(Backup.commitRefusal(ApiError.Server(403, "")).contains("Your PC"))
        assertTrue(Backup.commitRefusal(ApiError.Server(409, "")).contains("expired"))
        assertEquals("", Backup.commitRefusal(ApiError.BadToken))
    }

    // ------------------------------------------------------- what it draws ---

    @Test
    fun thePlateHoldsTheScreenOpenUntilTheCodeIsTicked() {
        val plate = code(PLATE)
        val model = code(MODEL)
        // The gate itself: the tick, the label, and the words that say nothing
        // is written until it is set.
        assertTrue("the tick exists", plate.contains("Backup.SAVED_TICK"))
        assertTrue("the write is behind the tick",
            plate.contains("enabled = saved && canAct && !writing"))
        assertTrue("the code is drawn, not hidden", plate.contains("prepared.code"))
        assertTrue("the warning is drawn beside it", plate.contains("Backup.CODE_NOW"))
        assertTrue("and cancelling is offered, and writes nothing",
            plate.contains("Backup.CANCEL_LABEL"))
        // A stray tap outside must not dismiss it: the whole point is that the
        // code is read before anything is written.
        assertTrue("the dialog cannot be dismissed by a tap outside",
            plate.contains("dismissOnClickOutside = false"))
        // The code's warning is on the plate as well, before the button is
        // pressed, and its words are the model's own.
        assertTrue(plate.contains("Backup.CODE_WARNING"))
        assertTrue(model.contains("recovery code"))
    }

    @Test
    fun theScreenSaysWhatACheckProvesAndWhatOnlyTheCodeProves() {
        val plate = code(PLATE)
        val model = code(MODEL)
        // The limit is drawn from the PC's own sentence, not invented here.
        assertTrue("the limit is drawn under a pass", plate.contains("check.limit"))
        assertTrue("and the model never claims a check proves it opens",
            model.contains("provesOpen") && model.contains("proves_open"))
        // A failed run is drawn.
        assertTrue(plate.contains("attemptLine"))
        // The PC's own sentences are preferred, so the two apps cannot drift.
        assertTrue(model.contains("c.words.isNotBlank()"))
    }

    @Test
    fun thePhoneAsksForABackupButNeverPostsToThePcsOwnRoute() {
        // The button's existence is now a decision FOR the phone; what stays
        // the PC's is `/api/backup/now`, which mints a code and returns it in
        // one call with no chance to show it. The phone must never call it, and
        // must never call the routes that write a folder or restore one.
        val api = code(API)
        val plate = code(PLATE)
        val model = code(MODEL)
        for (forbidden in listOf(
            "/api/backup/now", "/api/backup/folder", "/api/backup/restore",
            "/api/backup/list", "/api/backup/delete-older",
        )) {
            assertFalse("$forbidden is the PC's own route", api.contains(forbidden))
            assertFalse("$forbidden must not be drawn either", plate.contains(forbidden))
        }
        // The four backup routes the phone DOES name, and no other.
        assertEquals(
            setOf("/api/backup", "/api/backup/status", "/api/backup/prepare", "/api/backup/commit"),
            Regex("\"(/api/[A-Za-z0-9_/]*)\"").findAll(model).map { it.groupValues[1] }.toSet(),
        )
        // The two calls are told apart where it matters: the write is held on a
        // stale link, the ask is not (it writes nothing anywhere).
        val runtime = code(RUNTIME)
        assertTrue("the write is held", runtime.contains("commitBackup") &&
            Regex("suspend fun commitBackup[\\s\\S]{0,200}actionBlocker\\(\\)")
                .containsMatchIn(runtime))
        assertFalse("the ask is not held, because it writes nothing",
            Regex("suspend fun prepareBackup[\\s\\S]{0,200}actionBlocker\\(\\)")
                .containsMatchIn(runtime))
    }

    // ------------------------------------------------------------- helpers --

    /**
     * Just the code: `//` lines and every line of a block comment dropped, so
     * an assertion on what a file DOES is never satisfied by a comment that
     * names the same thing on purpose (the same idea as LimitsTest's helper,
     * one step further because these files explain the removed keys by name).
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
    private val RUNTIME = "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt"
}
