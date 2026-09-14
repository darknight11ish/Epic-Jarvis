package com.jarvis.client.platform

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat
import com.jarvis.client.service.EventService

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
    private val CLEARTEXT_EXACT = setOf("ts.net", "localhost", "127.0.0.1")
    private val CLEARTEXT_SUFFIXES = listOf(".ts.net")

    /**
     * Mirrors what `<domain includeSubdomains="true">ts.net</domain>` actually
     * matches: the domain itself and labels beneath it, and nothing else.
     *
     * The previous predicate held a bare `"ts.net"` and tested it with `endsWith`,
     * so `notmyts.net` and `evilts.net` — registrable public domains that have
     * nothing to do with Tailscale — reported "permitted" on the one screen whose
     * whole job is to make this policy legible. It failed in the safe direction,
     * because the platform would still refuse the connection, but the same shape of
     * bug in the other app sent a bearer token to a public host in the clear.
     */
    fun cleartextPermitted(host: String): Boolean {
        val h = host.trim().lowercase().substringBefore(':').trim('/')
        if (h.isEmpty()) return false
        if (h in CLEARTEXT_EXACT) return true
        return CLEARTEXT_SUFFIXES.any { h.endsWith(it) }
    }

    /**
     * Whether the app is exempt from battery optimisation.
     *
     * This is the exemption that lets the service go foreground from the background,
     * which is what a sticky restart after the system reclaims the process needs.
     * Without it, one reclaim ends the link permanently.
     */
    fun batteryExempt(context: Context): Boolean {
        val pm = ContextCompat.getSystemService(context, PowerManager::class.java) ?: return false
        return runCatching { pm.isIgnoringBatteryOptimizations(context.packageName) }
            .getOrDefault(false)
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
            title = "Microphone",
            detail = if (micGranted(context)) {
                "Granted. Push-to-talk will record and send one utterance at a time."
            } else {
                "Not granted yet. Asked for the first time you hold the microphone " +
                    "button, not at launch. Audio is sent to your desktop to be " +
                    "checked and transcribed there — this app never transcribes."
            },
            state = if (micGranted(context)) {
                ReadinessItem.State.OK
            } else {
                // Not a warning. Push-to-talk is opt-in by holding a button,
                // and an app that nags for a microphone it is not using is the
                // reason people refuse the prompt that matters.
                ReadinessItem.State.INFO
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
            title = "Background restart",
            detail = if (batteryExempt(context)) {
                "Exempt from battery optimisation, so the service can be restarted " +
                    "by the system after the process is reclaimed."
            } else {
                "Not exempt. If Android reclaims the process, the sticky restart " +
                    "happens in the background, startForeground is refused, and the " +
                    "link stops for good until you reopen the app."
            },
            state = if (batteryExempt(context)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
        ),
        ReadinessItem(
            title = "Link service",
            detail = EventService.lastStartFailure?.let {
                "The service was refused by the platform ($it) and stopped itself. " +
                    "Grant the battery-optimisation exemption above and start it again."
            } ?: "No start failures recorded.",
            state = if (EventService.lastStartFailure == null) {
                ReadinessItem.State.INFO
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
