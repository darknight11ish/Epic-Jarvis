package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * "Backups": what a PHONE can see - and, plainly, what it cannot
 * (the owner's decision of 2026-09-27, CLAUDE.md: "one locked backup file into
 * a folder the owner picks ... locked with a recovery code only the owner has";
 * docs/JARVIS-API.md section 45; ui/screens/BackupPlate.kt draws this).
 *
 * WHY THERE IS NO "BACK UP NOW" BUTTON HERE (checked against the owner's own
 * PC, 2026-10-10). The owner asked for one. The PC's route exists -
 * `POST /api/backup/now`, `jarvis_backup.request_backup_now` - and it refuses
 * every caller that is not this PC ([jarvis_backup.PC_ONLY]; the check is
 * `jarvis_owner_check.from_this_pc`, and docs/ARCHITECTURE.md section 8's
 * "only on the PC" table says why: the folder is Windows' own picker and the
 * recovery code that locks a backup is shown on the PC, once). A phone
 * reaching the PC over Tailscale or NordVPN Meshnet is not this PC, so a
 * button here would answer 403 every time - a control that cannot work, drawn
 * as if it could. What the phone says instead is [PC_ONLY], in plain words.
 *
 * WHAT A PHONE IS SENT, AND WHY THE REST IS GONE. A non-PC caller is answered
 * `{"available", "last_backup_at"}` and nothing else (`jarvis_backup.view`,
 * `here=False`). The folder's path, a waiting card, the last restore's outcome
 * and the erase limit are all sent to this PC only. This file used to also
 * read `pending_delete_older_card`, `last_delete_older` and `erase_limit` and
 * the plate drew a line for each - three branches that could never run on a
 * phone, which is worse than useless: a reader cannot tell a live branch from
 * a dead one. They are removed rather than kept "just in case".
 *
 * [lastBackupAt] IS IN THE PC'S MEMORY ONLY, so [NEVER_MADE] says exactly what
 * the PC can support and no more. `_B_STATE` is cleared when the backend
 * starts, so a null here does NOT mean "this PC has never made a backup" - the
 * owner's PC had four backup files in its folder and still answered null the
 * morning after a restart. The older sentence ("No backup has been made yet.")
 * was therefore false on screen, which is the one thing this screen may not be.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Backup {
    const val PATH = "/api/backup"
    const val TITLE = "Backups"

    /** What this screen is for, said before anything else. */
    const val DETAIL =
        "This shows when your PC last made a backup. Backups are made, restored and deleted " +
            "on the PC, in Jarvis Desktop's Settings - the folder is Windows' own picker."

    /**
     * Why there is no "Back up now" here. The owner asked for one (2026-10-10)
     * and the PC's own rule is what settles it: it refuses `/api/backup/now`
     * from anything but this PC, so the honest thing on a phone is the
     * sentence, not a button that would fail every time.
     */
    const val PC_ONLY =
        "\"Back up now\" is not offered here, and it is not missing: your PC refuses a backup " +
            "asked for from a phone. To make one, open Jarvis Desktop on your PC and use " +
            "Settings > Backups."

    /**
     * The recovery code, said BEFORE the owner goes to the PC to make one -
     * the reason the PC route is the PC's alone, and the thing that is lost
     * for good if it is not written down. Never that a code is kept anywhere:
     * neither app stores one, and the PC shows it exactly once.
     */
    const val CODE_WARNING =
        "When your PC makes a backup it shows a recovery code ONCE. Write it down or save it " +
            "somewhere safe there and then: Jarvis will never show it again and cannot " +
            "recover it, and without that code the backup can never be opened."

    /**
     * `last_backup_at` is null. True words only: the PC keeps this in memory,
     * so this is not "never" - it is "not since your PC's Jarvis last started"
     * (see the class comment).
     */
    const val NEVER_MADE =
        "Your PC's Jarvis has not made one since it last started. Any backup made before that " +
            "is still in the folder you chose on your PC."

    const val MISSING = "Your PC's Jarvis cannot make backups yet - run apply-patches.ps1 on the PC."

    /**
     * Everything a PHONE is told about backups: when the last one was made,
     * or null when the PC's memory holds none (see [NEVER_MADE]).
     */
    data class Status(val lastBackupAt: Double?)

    /** `GET /api/backup`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): Status? {
        if ((body["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == false) return null
        val at = (body["last_backup_at"] as? JsonPrimitive)?.doubleOrNull
        return Status(lastBackupAt = at)
    }

    /** A read that failed because this PC has no backups feature. */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && error.code == 501)

    private fun plural(n: Int, unit: String) = "$n $unit${if (n == 1) "" else "s"} ago"

    /** "Last backup: 3 days ago." or [NEVER_MADE] - never a raw timestamp. */
    fun line(status: Status, nowSeconds: Double = System.currentTimeMillis() / 1000.0): String {
        val at = status.lastBackupAt ?: return NEVER_MADE
        val ago = (nowSeconds - at).coerceAtLeast(0.0)
        val words = when {
            ago < 90 -> "just now"
            ago < 90 * 60 -> plural((ago / 60).toInt(), "minute")
            ago < 36 * 3600 -> plural((ago / 3600).toInt(), "hour")
            else -> plural((ago / 86400).toInt(), "day")
        }
        return "Last backup: $words."
    }
}
