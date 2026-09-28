package com.jarvis.client.platform

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.jarvis.client.LinkWords

/**
 * Watches which network this phone is using, for two things (phone
 * walk-through N1, 2026-09-27):
 *
 * - **A change of network reconnects at once.** Walking out of Wi-Fi, or
 *   switching Tailscale on, left the event stream holding a dead connection
 *   that nothing replaced until ~70 seconds of silence (the watchdog) plus
 *   up to 30 seconds of back-off. Now [onChange] fires on the change itself;
 *   the caller reconnects ([com.jarvis.client.JarvisRuntime.reconnectForNetworkChange]).
 * - **Whether a VPN is up at all.** Tailscale and NordVPN Meshnet both run
 *   as a VPN on the phone, and Android marks the network of any VPN that
 *   covers this app with `TRANSPORT_VPN`. [onVpn] gets true or false, or
 *   null when there is no network (or nothing is known).
 *
 * Android's "default network" callback: the network this app's traffic
 * actually uses, a VPN included. It reads nothing but that, needs only
 * ACCESS_NETWORK_STATE (already in the manifest), and sends nothing
 * anywhere. Callbacks arrive on the main thread.
 */
object NetworkWatch {

    /** The kinds Android can report for a network, checked one by one. */
    private val KINDS = intArrayOf(
        NetworkCapabilities.TRANSPORT_CELLULAR,
        NetworkCapabilities.TRANSPORT_WIFI,
        NetworkCapabilities.TRANSPORT_BLUETOOTH,
        NetworkCapabilities.TRANSPORT_ETHERNET,
        NetworkCapabilities.TRANSPORT_VPN,
        NetworkCapabilities.TRANSPORT_WIFI_AWARE,
        NetworkCapabilities.TRANSPORT_LOWPAN,
        NetworkCapabilities.TRANSPORT_USB,
    )

    private fun kinds(caps: NetworkCapabilities): Set<Int> =
        KINDS.filter { caps.hasTransport(it) }.toSet()

    /**
     * Starts watching. [onVpn] is called at once with what is known now;
     * [onChange] only for a real change afterwards, never for the report
     * Android sends as the watch starts. Returns the function that stops
     * watching - call it exactly once. If the watch cannot start, nothing is
     * called and the returned function does nothing: the link then behaves
     * exactly as it did before this existed.
     */
    fun watch(context: Context, onVpn: (Boolean?) -> Unit, onChange: () -> Unit): () -> Unit {
        val app = context.applicationContext
        val cm = runCatching { app.getSystemService(ConnectivityManager::class.java) }.getOrNull() ?: return {}

        val active = runCatching { cm.activeNetwork }.getOrNull()
        val activeCaps = active?.let { runCatching { cm.getNetworkCapabilities(it) }.getOrNull() }
        var seen = LinkWords.NetworkSeen(active?.networkHandle, activeCaps?.let { kinds(it) })
        onVpn(activeCaps?.hasTransport(NetworkCapabilities.TRANSPORT_VPN))

        fun report(network: Network, caps: NetworkCapabilities?) {
            val handle = network.networkHandle
            val k = caps?.let { kinds(it) }
            val changed = seen.changedBy(handle, k)
            seen = seen.after(handle, k)
            if (caps != null) onVpn(caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN))
            if (changed) onChange()
        }

        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = report(network, null)

            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) =
                report(network, caps)

            override fun onLost(network: Network) {
                val before = seen
                seen = seen.lostNetwork(network.networkHandle)
                // Only the network in use going away with nothing in its
                // place: "no network", not "no VPN".
                if (seen.lost && !before.lost) onVpn(null)
            }
        }

        val registered = runCatching {
            cm.registerDefaultNetworkCallback(callback, Handler(Looper.getMainLooper()))
        }.onFailure { Log.w(TAG, "could not watch the network", it) }.isSuccess
        if (!registered) return {}

        return {
            runCatching { cm.unregisterNetworkCallback(callback) }
            onVpn(null)
        }
    }

    private const val TAG = "JarvisNetworkWatch"
}
