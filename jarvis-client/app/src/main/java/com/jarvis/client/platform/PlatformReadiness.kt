package com.jarvis.client.platform

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat
import com.jarvis.client.service.ApprovalNotifier
import com.jarvis.client.service.EventService
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

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
        val url = parsed(host) ?: return false
        // https is not cleartext at all, so the policy simply does not apply and
        // warning about it would be a false alarm.
        if (!url.isHttp) return true
        val h = url.host
        if (h in CLEARTEXT_EXACT) return true
        return CLEARTEXT_SUFFIXES.any { h.endsWith(it) }
    }

    /**
     * The host OkHttp will actually dial, parsed rather than split.
     *
     * The previous version took `substringBefore(':')`, and a colon is not where
     * a host ends. It got four cases wrong, and the one that mattered was not
     * the malicious one:
     *
     * - `http://desktop.ts.net:4719` — a form [ClientSettings.baseUrl] expressly
     *   accepts — reduced to `"http"`, so the screen told the owner their host
     *   was NOT permitted and to go and find a MagicDNS name they had already
     *   typed. A false alarm on the one screen whose job is to stop people
     *   chasing phantom network faults.
     * - `https://desktop.ts.net` warned about cleartext for a connection that
     *   does not use any.
     * - `evil.com/foo.ts.net` and `foo.ts.net:8080@evil.com` both reported
     *   permitted while OkHttp would dial `evil.com`. The platform still refuses
     *   those connections, so this failed safe — but it is the identical shape
     *   to the bug that, in the other app, put a bearer token on the wire to a
     *   public host, and the comment above already cites it.
     *
     * Hand-splitting a URL is what produced all four. This asks the same parser
     * the request will use.
     */
    private data class Parsed(val host: String, val isHttp: Boolean)

    private fun parsed(raw: String): Parsed? {
        val t = raw.trim().trim('/')
        if (t.isEmpty()) return null
        val withScheme = when {
            t.startsWith("http://", ignoreCase = true) ||
                t.startsWith("https://", ignoreCase = true) -> t
            // Matches ClientSettings.baseUrl(), which assumes http for a bare host.
            else -> "http://$t"
        }
        val url = runCatching { withScheme.toHttpUrlOrNull() }.getOrNull() ?: return null
        return Parsed(url.host.lowercase(), url.scheme.equals("http", ignoreCase = true))
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

    fun micGranted(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

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
                "Granted. Approvals are announced in the drawer, and the ongoing " +
                    "service notification is visible."
            } else {
                // The old wording here was "its notification is hidden from the
                // drawer and only appears in the Task Manager". True of the
                // ongoing service notification, and it buried the part that
                // matters: with this denied, NOT ONE approval is announced. The
                // service keeps running, the link stays up, nothing looks
                // broken - and requests waiting on an answer sit unseen.
                // ApprovalNotifier counts them; this is where that count shows.
                val silenced = ApprovalNotifier.silenced
                val waiting = when (silenced) {
                    0 -> ""
                    1 -> " - one is waiting unannounced right now"
                    else -> " - $silenced are waiting unannounced right now"
                }
                "Denied, and that is worse than it sounds: no approval is " +
                    "announced at all" + waiting +
                    ". The service still runs and nothing else looks broken, so " +
                    "this screen is the only place it shows. The ongoing service " +
                    "notification is hidden too, and appears only in the Task Manager."
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
