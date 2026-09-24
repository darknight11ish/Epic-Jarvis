package com.jarvis.client.platform

import com.jarvis.client.BuildConfig
import com.jarvis.client.data.ClientSettings
import com.jarvis.client.net.UpdateCheck
import java.io.IOException
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

    private val busy = AtomicBoolean(false)

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

    /** "Check for new versions" was turned off: forget what was shown. */
    fun cleared() {
        _state.value = UpdateCheck.State(lastTryMs = settings.updateLastTryMs)
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
}
