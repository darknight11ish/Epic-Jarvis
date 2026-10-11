package com.jarvis.client.platform

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.content.FileProvider
import com.jarvis.client.BuildConfig
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.net.UpdateCheck
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * The one request to GitHub, for "a newer version is available". What it
 * decides, and why it is shaped this way, is in [UpdateCheck].
 *
 * Its own HTTP client, built from nothing - NOT one of [com.jarvis.client.net.JarvisApi]'s.
 * Those talk to the owner's PC; this talks to github.com, and must not
 * share a connection pool, a timeout tuned for the tailnet, or anything a
 * later change to JarvisApi might add to every request (the token rides
 * on each request there today, not on the client, but that is one refactor
 * away). No redirects: the one address in [UpdateCheck.URL] is the only
 * place this ever connects. No cookies and no cache, which is OkHttp's
 * default when none is set.
 */
class UpdateChecker(private val settings: ClientSettings) {

    private val _state = MutableStateFlow(
        UpdateCheck.State(
            newerLine = settings.updateNewerLine,
            problem = settings.updateProblem,
            lastTryMs = settings.updateLastTryMs,
        ),
    )
    val state: StateFlow<UpdateCheck.State> = _state.asStateFlow()

    private val _download = MutableStateFlow<UpdateCheck.Download>(UpdateCheck.Download.Idle)

    /** The Download button's own state: idle, fetching, ready, or refused. */
    val download: StateFlow<UpdateCheck.Download> = _download.asStateFlow()

    private val busy = AtomicBoolean(false)
    private val downloading = AtomicBoolean(false)

    private val http: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .callTimeout(20, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .build()
    }

    /**
     * The APK download needs its own client: GitHub answers a release asset
     * with a redirect to `objects.githubusercontent.com`, and the check's
     * client deliberately follows nothing. Redirects ARE followed here - and
     * every hop is checked to be an https address on github.com or one of its
     * own asset hosts before a byte of it is written.
     */
    private val files: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .callTimeout(15, TimeUnit.MINUTES)
            .followRedirects(true)
            .followSslRedirects(true)
            .retryOnConnectionFailure(true)
            .build()
    }

    /** "Check for new versions" was turned off: forget what was shown. */
    fun cleared() {
        _state.value = UpdateCheck.State(lastTryMs = settings.updateLastTryMs)
        forgetDownload()
    }

    /** Removes the downloaded copy, if there is one, and forgets it. */
    fun forgetDownload() {
        (_download.value as? UpdateCheck.Download.Ready)?.file?.delete()
        _download.value = UpdateCheck.Download.Idle
    }

    /**
     * Asks GitHub if the setting is on and a check is due ([UpdateCheck.due]).
     * Never throws; a failure becomes a line on Checks and nothing else.
     */
    suspend fun checkIfDue(onStart: Boolean) {
        if (!settings.updateChecks.value) return
        val now = System.currentTimeMillis()
        if (!UpdateCheck.due(now, settings.updateLastTryMs, onStart)) return
        if (!busy.compareAndSet(false, true)) return
        try {
            // Recorded before asking, so a request that hangs or crashes is
            // not repeated at once.
            settings.updateLastTryMs = now
            val fetched = withContext(Dispatchers.IO) { fetch() }
            // Turned off while the request was out: say nothing.
            if (!settings.updateChecks.value) return
            val next = UpdateCheck.next(
                _state.value,
                fetched,
                UpdateCheck.ownSha(BuildConfig.GIT_SHA),
                BuildConfig.GIT_COMMIT_TIME,
                now,
            )
            settings.updateNewerLine = next.newerLine
            settings.updateProblem = next.problem
            _state.value = next
        } finally {
            busy.set(false)
        }
    }

    private fun fetch(): UpdateCheck.Fetched {
        val request = Request.Builder()
            .url(UpdateCheck.URL)
            .get()
            // GitHub's documented media type. No token, no header that says
            // which phone or which owner is asking.
            .header("Accept", "application/vnd.github+json")
            .build()
        return try {
            http.newCall(request).execute().use { response ->
                if (response.code != 200) return UpdateCheck.Fetched.Http(response.code)
                val source = response.body?.source() ?: return UpdateCheck.Fetched.Http(response.code)
                // request(n) is true when at least n bytes arrived: one past
                // the cap means this is not a release answer.
                if (source.request(UpdateCheck.MAX_BYTES + 1L)) return UpdateCheck.Fetched.TooBig
                UpdateCheck.Fetched.Body(source.buffer.readUtf8())
            }
        } catch (e: IOException) {
            UpdateCheck.Fetched.NoNetwork
        } catch (e: IllegalStateException) {
            UpdateCheck.Fetched.NoNetwork
        }
    }

    // ------------------------------------------------ the Download button ----
    // The owner's request of 2026-10-11. Nothing here runs until he presses
    // Download, and nothing is offered to Android's installer until the file's
    // signing certificate has been read out of it and matched against the
    // digest pinned in the app (`UpdateCheck.SIGNER_SHA256`).

    /**
     * Fetches the published APK, checks its certificate, and - only if that
     * matches - puts it in [download] as `Ready`. Never throws: every ending is
     * a value the screen can show.
     *
     * [context] is only used for the app's own private cache directory, which
     * is the file's ONLY home: no shared storage, no external path, so nothing
     * else on the phone can swap the bytes between the check and the install.
     */
    suspend fun download(context: Context) {
        val p = _state.value.published
        val url = p?.downloadUrl
        if (url == null || !UpdateCheck.isReleaseDownload(url)) {
            // Nothing has been offered: no address, or one that is not this
            // repository's own release. Not an error to report - simply no
            // Download button on screen.
            _download.value = UpdateCheck.Download.Idle
            return
        }
        if (!downloading.compareAndSet(false, true)) return
        try {
            _download.value = UpdateCheck.Download.Fetching(0, p.downloadBytes)
            val saved = withContext(Dispatchers.IO) { fetchApk(context, url, p.downloadBytes) }
            when (saved) {
                is Saved.No -> _download.value = UpdateCheck.Download.Refused(saved.why)
                is Saved.Yes -> {
                    val cert = withContext(Dispatchers.IO) { certificateSha256(context, saved.file) }
                    _download.value = UpdateCheck.afterFetch(saved.bytes, cert) { _ ->
                        UpdateCheck.Download.Ready(saved.file)
                    }
                    if (_download.value is UpdateCheck.Download.Refused) saved.file.delete()
                }
            }
        } finally {
            downloading.set(false)
        }
    }

    /** One fetch ended: the bytes are on disk, or they are not. */
    private sealed interface Saved {
        data class Yes(val file: File, val bytes: Long) : Saved
        data class No(val why: String) : Saved
    }

    private fun fetchApk(context: Context, url: String, expected: Long): Saved {
        if (expected > UpdateCheck.MAX_APK_BYTES) {
            return Saved.No("That build is larger than this app will download, so nothing was saved.")
        }
        val dir = File(context.cacheDir, UPDATE_DIR)
        if (!dir.exists() && !dir.mkdirs()) {
            return Saved.No("There was nowhere on this phone to put the download.")
        }
        // One file, overwritten: a failed attempt never leaves a second copy
        // behind for the installer to find.
        val part = File(dir, "download.part")
        val file = File(dir, "jarvis-client.apk")
        return try {
            val request = Request.Builder().url(url).get()
                .header("Accept", "application/vnd.android.package-archive")
                .build()
            files.newCall(request).execute().use { response ->
                if (response.code != 200) return Saved.No("GitHub answered HTTP ${response.code} for the app file.")
                val body = response.body ?: return Saved.No("GitHub sent nothing for the app file.")
                val announced = body.contentLength().takeIf { it > 0 } ?: expected
                // A hop off GitHub's own hosts means stop before writing.
                if (!UpdateCheck.isGithubHost(response.request.url.host)) {
                    return Saved.No("The download was sent somewhere that is not GitHub, so it was stopped.")
                }
                var seen = 0L
                part.outputStream().use { out ->
                    body.byteStream().use { input ->
                        val buffer = ByteArray(64 * 1024)
                        while (true) {
                            val n = input.read(buffer)
                            if (n <= 0) break
                            seen += n
                            if (seen > UpdateCheck.MAX_APK_BYTES) {
                                return Saved.No("That build is larger than this app will download, so nothing was saved.")
                            }
                            out.write(buffer, 0, n)
                            _download.value = UpdateCheck.Download.Fetching(seen, announced)
                        }
                    }
                }
                if (seen <= 0) return Saved.No("GitHub sent an empty app file.")
                if (expected > 0 && seen != expected) {
                    return Saved.No("The app file arrived incomplete (${seen} of ${expected} bytes), so it was not kept.")
                }
                if (!part.renameTo(file)) {
                    part.delete()
                    return Saved.No("The download could not be put in place.")
                }
                Saved.Yes(file, seen)
            }
        } catch (e: IOException) {
            Saved.No("The download did not finish: the connection to GitHub was lost.")
        } catch (e: IllegalStateException) {
            Saved.No("The download did not finish.")
        } finally {
            part.delete()
        }
    }

    /**
     * The SHA-256 of the certificate [file] is signed with, as Android reads
     * it, or null when it is not an APK, carries no signature, or cannot be
     * read at all. A null is treated as a refusal by [UpdateCheck.afterFetch].
     */
    private fun certificateSha256(context: Context, file: File): String? {
        val flags = PackageManager.GET_SIGNING_CERTIFICATES
        val info = context.packageManager.getPackageArchiveInfo(file.absolutePath, flags) ?: return null
        val signing = info.signingInfo ?: return null
        val cert = (if (signing.hasMultipleSigners()) signing.apkContentsSigners else signing.signingCertificateHistory)
            ?.firstOrNull() ?: return null
        val digest = MessageDigest.getInstance("SHA-256").digest(cert.toByteArray())
        return digest.joinToString("") { "%02x".format(it) }
    }

    /**
     * Hands a VERIFIED file to Android's own installer. Refuses outright
     * unless [download] is `Ready` - the only state a matching certificate
     * produces - so an unverified file can never reach this.
     *
     * Android asks the owner once to allow installs from Jarvis; that is
     * Android's own screen, not a failure of this app.
     */
    fun install(context: Context): Boolean {
        val ready = _download.value as? UpdateCheck.Download.Ready ?: return false
        if (!ready.file.exists()) {
            _download.value = UpdateCheck.Download.Refused("The downloaded file is gone. Download it again.")
            return false
        }
        return try {
            val uri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.updates",
                ready.file,
            )
            val intent = Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, APK_MIME)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            true
        } catch (e: ActivityNotFoundException) {
            _download.value = UpdateCheck.Download.Refused(
                "This phone has no installer that will take the file. Open the release page and install it by hand.",
            )
            false
        } catch (e: IllegalArgumentException) {
            _download.value = UpdateCheck.Download.Refused(
                "The downloaded file could not be handed to the installer. Open the release page instead.",
            )
            false
        }
    }

    private companion object {
        const val UPDATE_DIR = "updates"
        const val APK_MIME = "application/vnd.android.package-archive"
    }
}
