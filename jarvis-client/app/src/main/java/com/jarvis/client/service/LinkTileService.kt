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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
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
 */
class LinkTileService : TileService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

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
            ) { link, activity, attention -> Triple(link, activity, attention) }
                .collect { (link, activity, attention) ->
                    render(link, activity, attention.muted, attention.pending)
                }
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
        scope.launch { JarvisRuntime.setMuted(!muted) }
    }

    private fun render(
        link: LinkState,
        activity: Activity,
        muted: Boolean,
        pending: Int,
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
            muted -> Tile.STATE_INACTIVE
            else -> Tile.STATE_ACTIVE
        }
        tile.label = "Jarvis"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            tile.subtitle = when {
                link != LinkState.CONNECTED -> "Offline"
                muted -> if (pending > 0) "Muted · $pending waiting" else "Muted"
                pending > 0 -> "$pending waiting"
                activity == Activity.THINKING -> "Thinking"
                activity == Activity.SPEAKING -> "Speaking"
                activity == Activity.LISTENING -> "Listening"
                activity == Activity.PAUSED -> "Paused"
                else -> "Linked"
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
