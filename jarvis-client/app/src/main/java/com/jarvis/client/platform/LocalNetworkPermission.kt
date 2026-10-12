package com.jarvis.client.platform

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat

/**
 * Local network access, and the one Android version that gates it.
 *
 * THE PROBLEM THIS EXISTS FOR, in plain words. From Android 17, an app that
 * targets it may not talk to other devices on the same local network until the
 * owner says yes. "Local network" is the confusing part: Android counts the
 * CGNAT range `100.64.0.0/10` as local, and that is exactly the range Tailscale
 * and NordVPN Meshnet hand out. So this app's ENTIRE transport to the PC - its
 * `*.ts.net` or `*.nord` name - sits inside the thing being gated.
 *
 * WHY NOTHING HAPPENS TODAY. `jarvis-client` targets API 36
 * (`app/build.gradle.kts`), and enforcement is keyed to `targetSdk 37+`. So the
 * permission below is declared and inert, and this object reports ON for every
 * phone in use. It is written now, and declared now, so that the day someone
 * raises that number nothing silently breaks - because the failure has no
 * pointer to its own cause: the app installs, starts, pairs, and then reports
 * *"Your PC isn't answering"* for ever. There is no workaround either, since a
 * user build cannot disable the app-compat override for a non-debuggable app. A
 * real report of exactly that shape is Kodi on GrapheneOS with Android 17.
 *
 * THE RULE THIS FILE FOLLOWS, and the bug it avoids: report "allowed" whenever
 * the permission cannot be asked for. `ContextCompat.checkSelfPermission` on a
 * permission the running platform has never heard of returns DENIED - so a
 * naive check would put a permanent, unfixable warning on every Android 16 and
 * 17 phone, on the one screen whose whole job is to be believable. Hence
 * [required] first, and an early `true`.
 *
 * A GENUINE AMBIGUITY, recorded rather than resolved by guessing. Android's own
 * guidance also says a local network "excludes cellular and VPN connections",
 * and this app's traffic to the PC leaves over the VPN interface. If the rule
 * follows the interface then this app is exempt even at `targetSdk 37`; if it
 * follows the address range then it is not. Both statements are in the official
 * material. Asking for a permission that turns out to be unnecessary is
 * harmless - the dialog appears once and the owner is told why - whereas
 * guessing the other way costs the whole transport, so the permission is
 * requested either way and the real answer comes from a GrapheneOS phone.
 *
 * `ACCESS_LOCAL_NETWORK` is newer than this app's `compileSdk`, so it is
 * written as a string literal rather than `Manifest.permission.*`: that
 * constant does not exist at API 36 and naming it would not compile. It is
 * single-sourced here so the manifest and the code cannot drift apart.
 */
object LocalNetworkPermission {

    /** The manifest declaration and the runtime request must name the same string. */
    const val PERMISSION = "android.permission.ACCESS_LOCAL_NETWORK"

    /** The API level that first enforces it. */
    const val FIRST_API = 37

    /**
     * True when the running Android actually gates local network access, so
     * this permission is real and worth asking for.
     *
     * Read from the DEVICE's own version, not from `targetSdk`: a phone on
     * API 36 has no such permission and never will, whatever this app targets.
     */
    fun required(): Boolean = Build.VERSION.SDK_INT >= FIRST_API

    /**
     * Whether local network access is allowed.
     *
     * True when the platform does not gate it at all, which is every phone this
     * app has run on so far - see the note above about reporting "allowed" for
     * a permission that cannot be asked for.
     */
    fun granted(context: Context): Boolean {
        if (!required()) return true
        return ContextCompat.checkSelfPermission(context, PERMISSION) ==
            PackageManager.PERMISSION_GRANTED
    }

    /** True only when the platform gates it AND the owner has not allowed it. */
    fun blocked(context: Context): Boolean = required() && !granted(context)
}
