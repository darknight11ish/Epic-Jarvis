package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Backups": read-only on the phone, on purpose (the owner's decision of
 * 2026-09-27, CLAUDE.md: "one locked backup file into a folder the owner
 * picks ... locked with a recovery code only the owner has"; design in
 * docs/CUTTING-EDGE-2026-09-26-round2-trust.md, "The phone shows 'last
 * backup: 3 days ago' only"; docs/JARVIS-API.md section 45).
 *
 * The full flow - choosing the folder, backing up now, seeing the recovery
 * code, restoring - is the PC's alone: the folder picker is Windows', the
 * recovery code is typed on the PC, and restoring needs Windows Hello there
 * (docs/ARCHITECTURE.md section 8). This reads the SAME `GET /api/backup`
 * the desktop does, and shows only the one field a phone can usefully know:
 * when the last backup was made. Everything else the PC's answer carries
 * (the folder's path, waiting cards, a one-time recovery code) is simply
 * never looked at here.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM.
 */
object Backup {
    const val PATH = "/api/backup"
    const val TITLE = "Backups"
    const val DETAIL =
        "Backups are made and restored on the PC, in Jarvis Desktop's Settings. This is a " +
            "read-only status - the folder, making one now and restoring all live there."
    const val NEVER_MADE = "No backup has been made yet."
    const val MISSING = "Your PC's Jarvis cannot make backups yet - run apply-patches.ps1 on the PC."

    data class DeleteOlder(val outcome: String, val message: String?, val deleted: Int)

    data class Status(
        val lastBackupAt: Double?,
        val pendingDeleteOlder: Boolean = false,
        val lastDeleteOlder: DeleteOlder? = null,
        val eraseLimit: String? = null,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }

    /** `GET /api/backup`, read - or null when it is not one (an older PC). */
    fun parse(body: JsonObject): Status? {
        if ((body["available"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == false) return null
        val at = (body["last_backup_at"] as? JsonPrimitive)?.doubleOrNull
        val pendingDelete = body["pending_delete_older_card"] is JsonObject
        val deleteObj = body["last_delete_older"] as? JsonObject
        val lastDelete = deleteObj?.let {
            val outcome = it.text("outcome") ?: ""
            val message = it.text("message")
            val deleted = (it["deleted"] as? JsonPrimitive)?.intOrNull ?: 0
            DeleteOlder(outcome = outcome, message = message, deleted = deleted)
        }
        val eraseLimit = body.text("erase_limit")
        return Status(
            lastBackupAt = at,
            pendingDeleteOlder = pendingDelete,
            lastDeleteOlder = lastDelete,
            eraseLimit = eraseLimit,
        )
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
