package com.jarvis.client.platform

import android.Manifest
import android.app.role.RoleManager
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
    /** One or two plain sentences: what it means for the owner, and what to do. */
    val detail: String,
    val state: State,
    /**
     * The same finding in the platform's own words - manifest attributes, API
     * names - for whoever is debugging. Hidden behind a tap on the Checks
     * screen, because the owner is not expected to know what `specialUse` is,
     * and the plain sentence above has to be enough on its own. Null when the
     * plain sentence already says everything.
     */
    val technical: String? = null,
    /** The button that fixes this, shown inside this item's card. Null for none. */
    val fix: Fix? = null,
) {
    enum class State { OK, WARN, INFO }

    /**
     * Which action the card offers. The screen decides the label and whether
     * it applies right now; this only says which one belongs to which card,
     * so a button can never again sit in a strip far from the card that
     * explains why it is there.
     */
    enum class Fix { NOTIFICATIONS, BATTERY, START_LINK, ASSISTANT_ROLE }
}

object PlatformReadiness {

    /**
     * Hosts the network security config permits in cleartext. Kept in step with
     * res/xml/network_security_config.xml by hand: there is no API to read the
     * parsed config back, so a mismatch here is a lie on the readiness screen
     * rather than a runtime failure.
     *
     * Two mesh products, same shape: Tailscale's MagicDNS name and NordVPN
     * Meshnet's Nord Name are both a name the user types at run time, so both
     * get a suffix entry here exactly like the XML's two `<domain>` rows.
     */
    private val CLEARTEXT_EXACT = setOf("ts.net", "nord", "localhost", "127.0.0.1")
    private val CLEARTEXT_SUFFIXES = listOf(".ts.net", ".nord")

    /**
     * Mirrors what `<domain includeSubdomains="true">ts.net</domain>` (and the
     * `nord` row beside it) actually match: the domain itself and labels
     * beneath it, and nothing else.
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

    /**
     * Whether this app is the system's held `RoleManager.ROLE_ASSISTANT`.
     *
     * Not whether the role EXISTS on this device (`isRoleAvailable` - every
     * phone this app's minSdk reaches has it) but whether the OWNER actually
     * picked Jarvis for it, which is the thing worth reporting: the plain
     * `ACTION_ASSIST` intent-filter alone made this app a candidate in the
     * old-style "Assist app" picker some OEMs still show, but said nothing
     * about the newer role-based one, and nothing in the app could tell
     * which state the phone was actually in.
     */
    fun assistantRoleHeld(context: Context): Boolean {
        val rm = ContextCompat.getSystemService(context, RoleManager::class.java) ?: return false
        return runCatching { rm.isRoleHeld(RoleManager.ROLE_ASSISTANT) }.getOrDefault(false)
    }

    /** False only where the API predates the role entirely - this app's own
     *  minSdk (33) is well past that, but a defensive check costs nothing
     *  and a stray `RoleManager` failure must not crash this screen. */
    fun assistantRoleAvailable(context: Context): Boolean {
        val rm = ContextCompat.getSystemService(context, RoleManager::class.java) ?: return false
        return runCatching { rm.isRoleAvailable(RoleManager.ROLE_ASSISTANT) }.getOrDefault(false)
    }

    /**
     * Every check, in plain words first.
     *
     * Rewritten for the owner rather than for the person who wrote it: each
     * [ReadinessItem.detail] now says what the finding means and what to tap,
     * and the platform vocabulary it used to lead with (`specialUse`,
     * `startForeground`, FCM) moved to [ReadinessItem.technical]. Nothing was
     * dropped - every technical sentence is still here, one tap away.
     *
     * @param host the desktop address to judge. Before pairing, the caller
     *   passes the one being typed on the pairing screen, not the saved one.
     */
    fun report(context: Context, host: String): List<ReadinessItem> = listOf(
        ReadinessItem(
            title = "Desktop address",
            detail = if (host.isBlank()) {
                "No desktop address yet. Type the desktop's name on your private " +
                    "network: its Tailscale name (ends in .ts.net) or its NordVPN " +
                    "Meshnet name (ends in .nord)."
            } else if (cleartextPermitted(host)) {
                "Android will let this app connect to $host."
            } else {
                "Android will block $host. Use the desktop's name on your private " +
                    "network instead of its number: its Tailscale name (ends in " +
                    ".ts.net) or its NordVPN Meshnet name (ends in .nord)."
            },
            technical = "Cleartext HTTP. The desktop serves plain HTTP over the private " +
                "network, and Android refuses plain HTTP except to names listed in " +
                "res/xml/network_security_config.xml: *.ts.net (Tailscale MagicDNS) " +
                "and *.nord (Meshnet Nord Name). The config can list a name but " +
                "cannot express an IP range, so a 100.x address is refused.",
            state = if (host.isNotBlank() && cleartextPermitted(host)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
        ),
        ReadinessItem(
            title = "Microphone",
            detail = if (micGranted(context)) {
                "Allowed. Holding the talk button records one message and sends it " +
                    "to your desktop."
            } else {
                "Not allowed yet. Jarvis asks the first time you hold the talk " +
                    "button, not before. The recording goes to your desktop, which " +
                    "turns it into text. This phone never does."
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
            title = "Running in the background",
            detail = "Set up correctly. Android lets Jarvis keep its connection open " +
                "in the background with no daily time limit.",
            technical = "Foreground service type is specialUse. dataSync would be " +
                "capped at six hours a day on Android 15 and the service would be " +
                "killed when the budget ran out.",
            state = ReadinessItem.State.OK,
        ),
        ReadinessItem(
            title = "Notifications",
            detail = if (notificationsGranted(context)) {
                "Allowed. New approvals show up in your notifications."
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
                    1 -> " One is waiting unannounced right now."
                    else -> " $silenced are waiting unannounced right now."
                }
                "Not allowed, so you are not told about any approval." + waiting +
                    " Nothing else looks broken, so this is the only place it " +
                    "shows. Tap Allow notifications to fix it."
            },
            technical = if (notificationsGranted(context)) {
                "POST_NOTIFICATIONS granted. The ongoing link-service notification " +
                    "is visible too."
            } else {
                "POST_NOTIFICATIONS denied. The ongoing link-service notification is " +
                    "hidden as well, and appears only in the Task Manager."
            },
            state = if (notificationsGranted(context)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
            fix = ReadinessItem.Fix.NOTIFICATIONS,
        ),
        ReadinessItem(
            title = "Background restart",
            detail = if (batteryExempt(context)) {
                "Allowed. If Android closes Jarvis to free up memory, the " +
                    "connection starts again by itself."
            } else {
                "Not allowed yet. If Android closes Jarvis to save battery, " +
                    "approvals stop arriving until you open the app again. Tap " +
                    "Keep link alive to fix it."
            },
            technical = if (batteryExempt(context)) {
                "Exempt from battery optimisation, so the service can be restarted " +
                    "by the system after the process is reclaimed."
            } else {
                "Not exempt from battery optimisation. If Android reclaims the " +
                    "process, the sticky restart happens in the background, " +
                    "startForeground is refused, and the link stops for good until " +
                    "the app is reopened."
            },
            state = if (batteryExempt(context)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
            fix = ReadinessItem.Fix.BATTERY,
        ),
        ReadinessItem(
            title = "Link service",
            detail = if (EventService.lastStartFailure != null) {
                "Android refused to start the connection, so it stopped. Allow " +
                    "Background restart first, then tap Start link."
            } else {
                "No problems starting the connection so far."
            },
            technical = EventService.lastStartFailure?.let {
                "The foreground service was refused by the platform ($it) and " +
                    "stopped itself. The battery-optimisation exemption is what " +
                    "lets it start from the background."
            },
            state = if (EventService.lastStartFailure == null) {
                ReadinessItem.State.INFO
            } else {
                ReadinessItem.State.WARN
            },
            fix = ReadinessItem.Fix.START_LINK,
        ),
        ReadinessItem(
            title = "Digital assistant",
            detail = if (!assistantRoleAvailable(context)) {
                "This phone has no assistant setting to give Jarvis. On some " +
                    "phones, long-pressing home may still open it."
            } else if (assistantRoleHeld(context)) {
                "Jarvis is your assistant app. Long-pressing home, or the assist " +
                    "gesture, opens it. Nothing else about the app changes."
            } else {
                "Not set. This is optional: it lets long-pressing home open Jarvis " +
                    "on phones that only offer that to the chosen assistant app."
            },
            technical = "RoleManager.ROLE_ASSISTANT. Launchers that still use the " +
                "plain ACTION_ASSIST intent-filter can open Jarvis without the role.",
            state = when {
                !assistantRoleAvailable(context) -> ReadinessItem.State.INFO
                assistantRoleHeld(context) -> ReadinessItem.State.OK
                // Not a warning: nothing is broken or missing by not holding
                // this - it is a convenience, and the plain intent-filter
                // already covers the launchers that use it. Same tier as
                // Microphone above, for the same reason.
                else -> ReadinessItem.State.INFO
            },
            fix = ReadinessItem.Fix.ASSISTANT_ROLE,
        ),
        ReadinessItem(
            title = "Deep sleep (Doze)",
            detail = "When the phone sleeps deeply, Android can interrupt the " +
                "connection. If it does, Jarvis says the link is stale and will not " +
                "let you approve anything until it catches up.",
            technical = "A persistent socket is a deliberate departure from the " +
                "platform's documented direction, which is FCM (Firebase Cloud " +
                "Messaging). FCM routes through Google and this app talks only to " +
                "your backend, so the socket stands and the stale indicator is the " +
                "mitigation.",
            state = ReadinessItem.State.INFO,
        ),
    )
}
