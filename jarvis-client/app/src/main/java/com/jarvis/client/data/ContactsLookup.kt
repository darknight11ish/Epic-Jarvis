package com.jarvis.client.data

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.ContactsContract
import android.util.Log
import androidx.core.content.ContextCompat
import com.jarvis.client.net.SmsSend

/**
 * The phone's own address book, read for ONE name and thrown away again.
 *
 * This is the only place in the app that touches contacts, and it exists for
 * one reason: the PC names the person in the owner's words ("Alex") and the
 * NUMBER lives on this phone. Nothing is cached, nothing is written, and the
 * rows go straight into [SmsSend.resolve], which decides whether the name is
 * exact and unique. Nothing about a contact leaves the phone except the number
 * the message is sent to - and the number is never posted to the PC either
 * (the result carries whether it was sent, not who to).
 *
 * The SQL below is a FILTER, not the decision. `LIKE ?` is deliberately loose
 * (case-insensitive for ASCII, and a `%` typed by the owner only widens it),
 * because the strict rule - exact, ignoring case and spacing, one number only,
 * ambiguity refused - is [SmsSend.resolve]'s and is held by tests on the JVM.
 * A wide read here can therefore cost a longer list, and never a wrong send.
 */
object ContactsLookup {

    private const val TAG = "JarvisContacts"

    /**
     * Every stored number whose contact name matches [name] loosely.
     *
     * Empty - never a throw - when `READ_CONTACTS` is not held: the caller
     * checks the permission first and its own sentence says what is missing
     * ([SmsSend.NO_CONTACTS_PERMISSION]), so a failure here degrading to an
     * empty list would turn "may not look" into "no such contact", which are
     * two different things to tell the owner.
     */
    fun phones(context: Context, name: String): List<SmsSend.Contact> {
        val want = name.trim()
        if (want.isEmpty()) return emptyList()
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) ==
            PackageManager.PERMISSION_GRANTED
        // It IS a different sentence, so the caller must be told which one:
        // SmsSend.gate refuses before this is reached when the permission is
        // missing, and this guard is only the belt to that brace.
        if (!granted) return emptyList()
        val rows = mutableListOf<SmsSend.Contact>()
        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
            ContactsContract.CommonDataKinds.Phone.NUMBER,
        )
        val selection = "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?"
        runCatching {
            context.contentResolver.query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                projection,
                selection,
                arrayOf(want),
                null,
            )?.use { cursor ->
                val nameAt = cursor.getColumnIndexOrThrow(
                    ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                )
                val numberAt = cursor.getColumnIndexOrThrow(
                    ContactsContract.CommonDataKinds.Phone.NUMBER,
                )
                while (cursor.moveToNext() && rows.size < MAX_ROWS) {
                    val display = cursor.getString(nameAt) ?: continue
                    val number = cursor.getString(numberAt) ?: continue
                    rows += SmsSend.Contact(display, number)
                }
            }
        }.onFailure { Log.w(TAG, "could not read contacts for a name", it) }
        return rows
    }

    /**
     * A bound on the read. A name typed loosely ("A") can match thousands of
     * rows, and this app needs enough to decide unique-or-ambiguous, not a
     * whole address book in memory - two distinct numbers are already the
     * answer "do not send".
     */
    private const val MAX_ROWS = 64
}
