package com.jarvis.client.service

import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import com.jarvis.client.Activity
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.data.QuickTiles
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/**
 * A quick-settings tile carrying the link's real state, and muting spoken
 * interruptions.
 *
 * **Not a power tile.** A route to set power exists now
 * (`POST /api/power`, the desktop's `backend/power-mode.patch`), and the
 * Mind screen has Active / Quiet / Standby buttons for it. The tile stays a
 * mute toggle on purpose: a tile has one tap, and cycling three modes blind
 * from a pulled-down shade - Standby unloads the model - is easy to get
 * wrong. Muting (`/api/attention/mute`, until tomorrow) is the one-tap job.
 *
 * The state is read from the event stream rather than inferred locally, so
 * the tile never assumes that sending a message made Jarvis active: a Quiet
 * set by hand survives being spoken to (JARVIS-API §4; the desktop's tray
 * says "set by hand" for it). This comment used to say such a Quiet "comes
 * back `"held": true`". Nothing in this repository shows what sets
 * `/api/status`'s `held` - its producer is the owner's jarvis_hud.py - and
 * the Mind screen reads it as something held back from sending, so the two
 * disagreed; this tile does not read `held` at all.
 *
 * THE ONE THING HELD LOCALLY is a mute the owner has just asked for and the
 * PC has not confirmed yet ([asked]): the tile says "Muting..." and drops a
 * second tap for that round trip only (Android audit 2026-10-08). It never
 * claims the mute happened - "Muted" still comes from the PC's own re-read,
 * exactly as the paragraph above requires.
 */
class LinkTileService : TileService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    /**
     * The mute state the owner has asked for and the runtime's own re-read has
     * not shown yet: null when nothing is in flight.
     *
     * `attention.muted` only moves when the PC answers `GET /api/attention`,
     * which `setMuted` runs after its POST - so without this the tile kept
     * drawing the OLD value for the whole round trip, a second tap read that
     * same value and sent "mute" again, and the tap meant to unmute muted
     * instead (Android audit 2026-10-08). [render] uses it to answer the tap
     * at once ("Muting..."), and [onClick] to drop a second tap aimed at the
     * state it is already going to be in ([QuickTiles.muteCommand]).
     */
    private val asked = MutableStateFlow<Boolean?>(null)

    override fun onStartListening() {
        super.onStartListening()
        // SystemUI can re-bind or re-request listening without an intervening
        // onStopListening, which would leave two collectors racing on one Tile.
        watcher?.cancel()
        JarvisRuntime.initialize(this)

        watcher = scope.launch {
            combine(
                JarvisRuntime.link,
                JarvisRuntime.activity,
                JarvisRuntime.attention,
                asked,
            ) { link, activity, attention, ask ->
                render(link, activity, attention.muted, attention.pending, ask)
            }.collect { }
        }
    }

    override fun onStopListening() {
        watcher?.cancel()
        watcher = null
        super.onStopListening()
    }

    override fun onDestroy() {
        watcher?.cancel()
        watcher = null
        // The scope, not only the one child it tracked. onClick and
        // onStartCommand launch untracked work on it, so a service torn
        // down mid-call left a coroutine running on a live job, holding
        // the destroyed instance.
        scope.cancel()
        super.onDestroy()
    }

    override fun onClick() {
        super.onClick()
        if (!JarvisRuntime.isPaired()) {
            openApp()
            return
        }
        if (JarvisRuntime.link.value != LinkState.CONNECTED) {
            // Nothing useful to toggle against a desktop we cannot reach.
            EventService.start(this)
            openApp()
            return
        }
        // `muted` is its own field on the budget. `blocked_by` says WHY the
        // budget is zero — "quiet", "standby", a locked session — and is null
        // most of the time, so reading it here meant the tile believed it was
        // never muted: every tap sent mute, and it could never unmute.
        val muted = JarvisRuntime.attention.value.muted
        // What this tap should send, or nothing: a tap while the previous
        // mute is still unconfirmed would otherwise read this same `muted`
        // and send the same command again, so the second tap never unmuted
        // (Android audit 2026-10-08). Never queued - the tile turns dark the
        // moment the first tap is sent, so that second tap was aimed at the
        // state it is already going to be in.
        val command = QuickTiles.muteCommand(shown = muted, asked = asked.value) ?: return
        // App lock on and the phone locked: Android's own unlock first, like
        // every other tile (QuickTileService). Dismissed, nothing is done.
        if (QuickTiles.muteNeedsUnlock(JarvisRuntime.settings.security.value.appLock, isLocked)) {
            unlockAndRun { scope.launch { sendMute(command) } }
            return
        }
        scope.launch { sendMute(command) }
    }

    /**
     * One Mute or Unmute, holding the state it asked for until the round trip
     * is over: [render] draws "Muting..." and [onClick] ignores a second tap
     * while `asked` disagrees with what the tile shows.
     *
     * Cleared whatever the answer, and that is deliberate - held after a
     * failure it would ignore every later tap, the same frozen-control shape
     * this replaced. On a failure the re-read never happened, so the old value
     * is still the true one and the next tap sends the same command again,
     * which is right: nothing had changed on the PC.
     */
    private suspend fun sendMute(muted: Boolean) {
        asked.value = muted
        try {
            JarvisRuntime.setMuted(muted)
        } finally {
            asked.value = null
        }
    }

    private fun render(
        link: LinkState,
        activity: Activity,
        muted: Boolean,
        pending: Int,
        askedFor: Boolean?,
    ) {
        val tile = qsTile ?: return
        // INACTIVE, not UNAVAILABLE, when the link is down. SystemUI does not
        // dispatch onClick to an unavailable tile, so marking it that way
        // deleted the branch in onClick that starts EventService and opens the
        // app - the one thing worth doing from the tile, refused in exactly the
        // state that makes it worth doing. The subtitle below already says
        // "Offline", so the tile still reads as off rather than as ready.
        tile.state = when {
            link != LinkState.CONNECTED -> Tile.STATE_INACTIVE
            // Sent but not yet confirmed counts as dimmed too: the tile's only
            // feedback is what it draws, and it draws the new state at once
            // rather than staying lit for the round trip.
            muted || askedFor == true -> Tile.STATE_INACTIVE
            else -> Tile.STATE_ACTIVE
        }
        tile.label = "Jarvis"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            tile.subtitle = when {
                link != LinkState.CONNECTED -> "Offline"
                askedFor != null -> if (askedFor) "Muting..." else "Unmuting..."
                muted -> if (pending > 0) "Muted · $pending waiting" else "Muted"
                pending > 0 -> "$pending waiting"
                activity == Activity.THINKING -> "Thinking"
                activity == Activity.SPEAKING -> "Speaking"
                activity == Activity.LISTENING -> "Listening"
                activity == Activity.PAUSED -> "Paused"
                else -> "Connected"
            }
        }
        tile.updateTile()
    }

    private fun openApp() {
        val intent = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // The Intent overload was deprecated at API 34 in favour of this one.
            startActivityAndCollapse(
                PendingIntent.getActivity(
                    this,
                    0,
                    intent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                ),
            )
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }
}
