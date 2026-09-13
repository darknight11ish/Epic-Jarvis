package com.jarvis.client.platform

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat

/**
 * The four items in ANDROID-BUILD.md §3.1, reported rather than assumed.
 *
 * Three of them fail silently and look like something else: cleartext looks
 * like a network outage, a denied notification looks like the service not
 * running, and Doze looks like the backend going away. Step 0 exists so those
 * are visible on the device before anything talks to the network.
 */
data class ReadinessItem(
    val title: String,
    val detail: String,
    val state: State,
) {
    enum class State { OK, WARN, INFO }
}

object PlatformReadiness {

    /**
     * Hosts the network security config permits in cleartext. Kept in step with
     * res/xml/network_security_config.xml by hand: there is no API to read the
     * parsed config back, so a mismatch here is a lie on the readiness screen
     * rather than a runtime failure.
     */
    private val CLEARTEXT_SUFFIXES = listOf(".ts.net", "ts.net", "localhost", "127.0.0.1")

    fun cleartextPermitted(host: String): Boolean {
        val h = host.trim().lowercase().substringBefore(':').trim('/')
        if (h.isEmpty()) return false
        return CLEARTEXT_SUFFIXES.any { h == it || h.endsWith(it) }
    }

    fun notificationsGranted(context: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
        } else {
            true
        }

    fun report(context: Context, host: String): List<ReadinessItem> = listOf(
        ReadinessItem(
            title = "Cleartext HTTP",
            detail = if (host.isBlank()) {
                "No host set yet. A MagicDNS name ending .ts.net is permitted; a bare IP is not."
            } else if (cleartextPermitted(host)) {
                "Permitted for $host by the network security config."
            } else {
                "$host is NOT permitted in cleartext. Use the desktop's MagicDNS " +
                    "name (….ts.net) rather than its IP address."
            },
            state = if (host.isNotBlank() && cleartextPermitted(host)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
        ),
        ReadinessItem(
            title = "Foreground service type",
            detail = "specialUse. dataSync would be capped at six hours a day on " +
                "Android 15 and the service would be killed when the budget ran out.",
            state = ReadinessItem.State.OK,
        ),
        ReadinessItem(
            title = "Notifications",
            detail = if (notificationsGranted(context)) {
                "Granted. The ongoing service notification will be visible."
            } else {
                "Denied. The service will still run, but its notification is hidden " +
                    "from the drawer and only appears in the Task Manager."
            },
            state = if (notificationsGranted(context)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
        ),
        ReadinessItem(
            title = "Doze",
            detail = "A persistent socket is a deliberate departure from the " +
                "platform's documented direction, which is FCM. FCM routes through " +
                "Google and this app talks only to your backend, so the socket " +
                "stands and the stale indicator is the mitigation.",
            state = ReadinessItem.State.INFO,
        ),
    )
}
