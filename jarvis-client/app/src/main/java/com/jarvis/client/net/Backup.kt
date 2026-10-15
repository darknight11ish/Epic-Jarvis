package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Backups" on the phone: the state of the folder on your PC, and the one
 * control that makes a new backup (the owner's decision of 2026-09-27 for the
 * feature; his question of 2026-10-10 - "a Back up now button on the phone" -
 * answered for real on 2026-10-13; docs/JARVIS-API.md section 45;
 * ui/screens/BackupPlate.kt draws this).
 *
 * WHAT THE PHONE DOES, AND WHERE EVERY PART OF IT HAPPENS. The archive lives
 * on the PC, always: the phone has no view of the PC's disk, so there is
 * nothing here that could hold one. The phone asks (`prepare`), the PC mints
 * this run's one-time recovery code and writes NOTHING yet, the phone shows
 * the code and waits for the owner to say he has kept it, and only then does
 * the PC write the file (`commit`, which is refused from anywhere but the PC).
 *
 * WHY IT IS TWO CALLS AND NOT ONE, which is the whole safety of the feature.
 * Every backup is locked with its OWN one-time code, the code is stored
 * nowhere, and making a new backup DELETES the oldest of the five kept
 * (`jarvis_backup.KEEP`). So a run whose code never reached the owner would
 * not merely add a file nobody can open - it would push out an older backup
 * whose own code still works. A run that is not finished therefore writes no
 * file at all, and the five already in the folder are untouched. See
 * `jarvis_backup.PREPARE_ROUTE` for the same reasoning on the PC's side.
 *
 * WHAT IS SHOWN, AND WHAT IS NOT. [Status] is read from `GET
 * /api/backup/status`, which answers any paired device: when the last backup
 * was, which folder (its LAST segment - never the whole path, which names the
 * owner's Windows account), how many are kept, and whether the newest file is
 * complete and well formed. It carries no recovery code and never can.
 *
 * THE ONE HONEST LIMIT, drawn on the screen in [CHECK_LIMIT] and never left to
 * be inferred: nothing on the phone can prove a backup OPENS. Only the code
 * opens one and codes are only ever typed on the PC, so a pass here means "the
 * file is complete and well formed", which is the difference between a backup
 * and a copy that was cut short - not "this backup works".
 *
 * THE CODE IS NEVER PERSISTED. It lives in the screen's own state for as long
 * as the run is open, is shown exactly once, and is dropped when the run is
 * finished or the screen is left. It is never written to SharedPreferences,
 * never logged, and never sent anywhere but back to the PC that minted it.
 * [commitBody]'s own comment says why the hyphens come off on the way back.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Backup {
    const val PATH = "/api/backup"
    /** The state of the folder. Read-only, any paired device. */
    const val STATUS_PATH = "/api/backup/status"
    /** Ask for a backup. Any paired device. WRITES NOTHING. */
    const val PREPARE_PATH = "/api/backup/prepare"
    /** Say the code is kept. THIS PC ONLY - this is the call that writes. */
    const val COMMIT_PATH = "/api/backup/commit"

    const val TITLE = "Backups"

    /** What this screen is for, said before anything else. */
    const val DETAIL =
        "Your backups live on your PC, in a folder you chose there. This screen shows what " +
            "is in it and asks your PC to make a new one. The file is written on the PC, " +
            "never here."

    /**
     * The recovery code, said BEFORE the owner asks for a backup. Shown again,
     * word for word, beside the code itself.
     */
    const val CODE_WARNING =
        "Every backup is locked with its own recovery code, and Jarvis keeps no copy of it. " +
            "Write the code down or save it somewhere safe - if it is lost, that backup can " +
            "never be opened again, and there is no other way in."

    /** Drawn under the code, before the run can be finished. */
    const val CODE_NOW =
        "This is the only time this code is ever shown. Nothing is written to your PC until " +
            "you finish - so if you lose the code before saving it, tap Cancel and nothing " +
            "changes."

    /** The button that finishes the run. Its label says what it does. */
    const val COMMIT_LABEL = "I have saved the code - write the backup"

    /** Above that button, and it must be ticked: a code cannot be swept past. */
    const val SAVED_TICK = "I have written this code down somewhere safe"

    const val CANCEL_LABEL = "Cancel - write nothing"

    /** Said once a backup has landed, next to the code that opens it. */
    const val DONE_LEAD =
        "Your PC wrote the backup. The code above opens it and nothing else does - it is not " +
            "shown again."

    /** The state could not be read at all. */
    const val MISSING = "Your PC's Jarvis cannot make backups yet - run apply-patches.ps1 on " +
        "the PC."

    /**
     * The folder has been read, but nothing is in it yet.
     */
    const val NOTHING_YET =
        "No backup in the folder yet. \"Back up now\" makes the first one."

    /**
     * `last_backup_at` is null, so the folder holds no usable backup. The older
     * screen said "No backup has been made yet.", which was false whenever the
     * PC's memory had simply been cleared by a restart ([Backup] used to read
     * the PC's memory only). This one reads the folder, so it can say what the
     * folder holds - and says the limit too. The word "folder" is in it on
     * purpose and is held by a test: it is where the truth is read from.
     */
    const val NEVER_MADE = "Your PC's backup folder holds no complete backup."

    /**
     * Everything a PHONE is told about the folder, read from
     * `GET /api/backup/status`. Everything past [folder] may be absent on an
     * older PC, so each is nullable and the screen draws only what arrived.
     */
    data class Status(
        /** The folder's LAST segment, e.g. "Jarvis Backups". Never the whole path. */
        val folder: String?,
        /** How many backups are kept (the PC's own KEEP). */
        val keep: Int?,
        /** How many complete backups are in the folder right now. */
        val kept: Int?,
        val lastBackupAt: Double?,
        val lastBackupName: String?,
        val check: Check?,
        val attempt: Attempt?,
        /** A run that is prepared and waiting for the owner to keep its code. */
        val prepared: Boolean,
    ) {
        /**
         * The verification of the newest kept file, as the PC read it. [why] is
         * a short key ("complete", "empty", "too_small", ...); [words] is the
         * PC's own sentence and is preferred, so the two apps cannot drift.
         * [provesOpen] is always false today and is read rather than assumed -
         * if the PC ever learns to prove more, this screen says so.
         */
        data class Check(
            val ok: Boolean,
            val why: String,
            val words: String,
            val provesOpen: Boolean,
            val limit: String,
        )

        /** The last run THIS PC's Jarvis made, remembered in the PC's memory. */
        data class Attempt(val ok: Boolean, val at: Double?, val error: String)
    }

    /** `GET /api/backup/status`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): Status? {
        if ((body["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == false) {
            return null
        }
        // A PC that only has the OLD `/api/backup` answer still parses: the new
        // shape is what carries `kept`/`verify`, and the PC's OWN view of the
        // old route carries a `folder` too - the whole Windows path - which must
        // NOT be read as the phone's folder name. Everything the answer does not
        // carry reads as absent, so the screen draws only what arrived.
        if (!body.containsKey("kept") && !body.containsKey("verify")) return oldShape(body)
        val v = body["verify"] as? JsonObject
        val a = body["last_attempt"] as? JsonObject
        return Status(
            folder = str(body, "folder"),
            keep = int(body, "keep"),
            kept = int(body, "kept"),
            lastBackupAt = num(body, "last_backup_at"),
            lastBackupName = str(body, "last_backup_name"),
            check = v?.let {
                Status.Check(
                    ok = flag(it, "ok") ?: false,
                    why = str(it, "why").orEmpty(),
                    words = str(it, "words").orEmpty(),
                    provesOpen = flag(it, "proves_open") ?: false,
                    limit = str(it, "limit").orEmpty(),
                )
            },
            attempt = a?.let {
                Status.Attempt(
                    ok = flag(it, "ok") ?: false,
                    at = num(it, "at"),
                    error = str(it, "error").orEmpty(),
                )
            },
            prepared = body["prepared"] is JsonObject,
        )
    }

    /**
     * The OLD `GET /api/backup` answer, which a phone has always been sent:
     * `{"available", "last_backup_at"}` and nothing else. Kept so an older PC
     * still shows the one line it can support instead of "cannot read it".
     */
    private fun oldShape(body: JsonObject): Status = Status(
        folder = null, keep = null, kept = null,
        lastBackupAt = num(body, "last_backup_at"), lastBackupName = null,
        check = null, attempt = null, prepared = false,
    )

    /** A read that failed because this PC has no backups feature. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    // ------------------------------------------------- the two run routes ----

    /**
     * The answer to `POST /api/backup/prepare`: the code to show, and the id
     * the commit sends back. The code is NOT a secret this app keeps - it lives
     * in the screen's state and nowhere else.
     */
    data class Prepared(
        val id: String,
        /** The one-time recovery code, in four groups of five. */
        val code: String,
        /** The PC's own sentence about what happens next. */
        val message: String,
        /** The folder's last segment, when the PC sent one. */
        val folder: String?,
    ) {
        /** The words to draw: the PC's, or [CODE_WARNING] if it sent none. */
        val words: String get() = message.ifBlank { CODE_WARNING }
    }

    /** The answer to `POST /api/backup/commit`: the file that landed. */
    data class Written(val name: String, val at: Double?, val size: Long?, val folder: String?)

    /** What the PC answered to `prepare` - a [Prepared], or its plain refusal. */
    sealed interface Asked {
        data class Ready(val prepared: Prepared) : Asked
        /** The PC's own words, never a status code. */
        data class Refused(val words: String) : Asked
    }

    /**
     * `POST /api/backup/prepare`'s answer, read. The PC's refusals all carry a
     * sentence (`NO_FOLDER`, and the rest); a shape with no `ok` key at all is
     * treated as one too, so a proxy's error page can never be mistaken for a
     * prepared run with an empty code - which would put "save this code" over
     * nothing.
     */
    fun asked(body: JsonObject): Asked {
        val ok = flag(body, "ok") ?: false
        val code = str(body, "recovery_code").orEmpty()
        if (!ok || code.isBlank()) {
            return Asked.Refused(
                str(body, "error") ?: str(body, "message")
                    ?: "Your PC did not start a backup. Nothing has changed.",
            )
        }
        return Asked.Ready(
            Prepared(
                id = str(body, "id").orEmpty(),
                code = code,
                message = str(body, "message") ?: "",
                folder = str(body, "folder"),
            ),
        )
    }

    /** `POST /api/backup/commit`'s answer, or null when it was not a success. */
    fun written(body: JsonObject): Written? {
        if (flag(body, "ok") != true) return null
        val name = str(body, "name") ?: return null
        return Written(
            name = name,
            at = num(body, "at"),
            size = num(body, "size")?.toLong(),
            folder = str(body, "folder"),
        )
    }

    /** The sentence out of a refusal body, or null when it holds none. */
    fun refusalWords(body: JsonObject): String? =
        str(body, "error") ?: str(body, "message")

    /**
     * Why a commit could not be completed, when the PC did not answer with
     * words of its own. 403 is the PC-only write ([PC_ONLY_WRITE]); 409 and 400
     * are a run that expired or was replaced ([RUN_GONE]).
     */
    fun commitRefusal(error: ApiError): String = when {
        error is ApiError.Server && error.code == 403 -> PC_ONLY_WRITE
        error is ApiError.Server && error.code == 409 -> RUN_GONE
        error is ApiError.Server && error.code == 400 -> RUN_GONE
        else -> ""
    }

    /**
     * The sentence for a run route that failed with no body to read. Empty when
     * this is not a run-route failure, so the caller falls back to the app's own
     * plain-errors wording rather than inventing a second one.
     */
    fun describeRefusal(error: ApiError): String = commitRefusal(error)

    private fun plural(n: Int, unit: String) = "$n $unit${if (n == 1) "" else "s"} ago"

    /** "3 days ago", "just now" - never a raw timestamp. */
    fun ago(at: Double, nowSeconds: Double): String {
        val d = (nowSeconds - at).coerceAtLeast(0.0)
        return when {
            d < 90 -> "just now"
            d < 90 * 60 -> plural((d / 60).toInt(), "minute")
            d < 36 * 3600 -> plural((d / 3600).toInt(), "hour")
            else -> plural((d / 86400).toInt(), "day")
        }
    }

    /**
     * "Last backup: 3 days ago." - or [NEVER_MADE] when the folder holds none.
     * The time is the newest kept file's own date, which is TRUE after the PC's
     * Jarvis restarts (it is read from the folder, not from the PC's memory).
     */
    fun line(status: Status, nowSeconds: Double = System.currentTimeMillis() / 1000.0): String {
        val at = status.lastBackupAt ?: return NEVER_MADE
        return "Last backup: ${ago(at, nowSeconds)}."
    }

    /**
     * "Kept: 3 of the last 5." - how many are there, and the PC's own limit.
     * Null when the PC did not say, so the screen draws nothing rather than a
     * number it invented.
     */
    fun keptLine(status: Status): String? {
        val kept = status.kept ?: return null
        val keep = status.keep ?: return "Kept: $kept."
        return "Kept: $kept of the last $keep."
    }

    /** "In: Jarvis Backups" - the folder's last segment, never the whole path. */
    fun folderLine(status: Status): String? =
        status.folder?.takeIf { it.isNotBlank() }?.let { "In: $it" }

    /**
     * What the check found. The PC's own sentence is preferred so the two apps
     * cannot drift; a short fallback covers a PC that sent the key alone.
     */
    fun checkLine(status: Status): String? {
        val c = status.check ?: return null
        if (c.words.isNotBlank()) return c.words
        return when (c.why) {
            "complete" -> "Jarvis checked the newest backup just now: it is complete."
            "empty", "no_folder" -> NEVER_MADE
            "missing" -> "Jarvis cannot find that backup file in the folder any more."
            "too_small" -> "That backup file is smaller than a real backup can be, so it is " +
                "not usable - make a new one on your PC."
            "unreadable" -> "Jarvis could not read that backup file just now - another " +
                "program may be holding it."
            "not_a_backup" -> "That file is not one of Jarvis's own backup files."
            else -> "Jarvis could not check the newest backup."
        }
    }

    /** The last run's outcome, when there is one. Null when there is nothing to say. */
    fun attemptLine(status: Status): String? {
        val a = status.attempt ?: return null
        if (!a.ok) {
            val why = a.error.takeIf { it.isNotBlank() }
            return if (why == null) "The last backup attempt failed." else
                "The last backup attempt failed: $why"
        }
        return "The last backup your PC made finished."
    }

    /** True when the last check passed AND there is a file it passed on. */
    fun verifies(status: Status): Boolean =
        status.check?.ok == true && status.lastBackupAt != null

    /**
     * `POST /api/backup/prepare {}` - ask the PC for a backup. It writes
     * NOTHING; the answer carries this run's one-time code, which the screen
     * must show. An empty object is all this ever sends.
     */
    fun prepareBody(): String = "{}"

    /**
     * `POST /api/backup/commit {"id","code"}` - say the code is kept. THIS is
     * the call that writes the file on the PC, and the PC refuses it from any
     * device but itself ([runNowFromThePhone] says what that means on screen).
     *
     * The code goes back WITHOUT its hyphens: the PC shows it in four groups of
     * five so a person can read it out, and stores the groups together
     * (`jarvis_backup.generate_code` / `_clean_code`), so the hyphens are
     * presentation and nothing else. Sending them or not is therefore the same
     * code, and the PC cleans both sides anyway.
     *
     * The id is sent back because the PC mints one per run; it is not a secret.
     */
    fun commitBody(id: String, code: String): String =
        """{"id":${quote(id)},"code":${quote(code.filter { it.isLetterOrDigit() }.uppercase())}}"""

    /**
     * The one thing that can still go wrong after this much work, said in
     * advance rather than discovered: the PC writes the file, and it takes the
     * PC to do it.
     */
    const val NEEDS_THE_PC =
        "Your PC is not answering, so nothing was asked for. Nothing has changed - try again " +
            "when your PC is reachable."

    /** The PC refused the commit because the caller was not the PC. */
    const val PC_ONLY_WRITE =
        "Your PC writes the backup, and it did not accept the write from your phone. Nothing " +
            "was written. Ask for a backup again from the phone; if it keeps happening, make " +
            "one at the PC - Settings, Backups."

    /**
     * The run's code no longer matches the PC's (it expired, or a newer ask
     * replaced it). Nothing was written.
     */
    const val RUN_GONE =
        "That backup run had expired, so nothing was written and your folder is unchanged. " +
            "Ask for a backup again."

    private fun quote(s: String): String = buildString {
        append('"')
        for (ch in s) when (ch) {
            '"' -> append("\\\"")
            '\\' -> append("\\\\")
            '\n' -> append("\\n")
            '\r' -> append("\\r")
            '\t' -> append("\\t")
            else -> if (ch < ' ') append("\\u%04x".format(ch.code)) else append(ch)
        }
        append('"')
    }

    private fun prim(o: JsonObject, k: String): JsonPrimitive? = o[k] as? JsonPrimitive

    private fun str(o: JsonObject, k: String): String? =
        prim(o, k)?.takeIf { it.isString }?.content?.takeIf { it.isNotBlank() }

    private fun num(o: JsonObject, k: String): Double? = prim(o, k)?.doubleOrNull

    private fun int(o: JsonObject, k: String): Int? = prim(o, k)?.intOrNull

    private fun flag(o: JsonObject, k: String): Boolean? =
        prim(o, k)?.takeIf { !it.isString }?.booleanOrNull
}
