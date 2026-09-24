package com.jarvis.client.net

import java.time.Instant
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * "A newer version is available" - the phone's side.
 *
 * The phone asks GitHub about ONE thing: the rolling `client-latest` release
 * of this public repository, which CI updates every time a build passes the
 * emulator check (`.github/workflows/jarvis-client.yml`). One plain GET, no
 * token, no header naming this phone, at most every [START_EVERY_MS] when
 * the app opens and every [DAILY_MS] while it stays open. The answer is
 * compared with the commit this build was made from (`BuildConfig.GIT_SHA`),
 * and if the published one is newer, one quiet line offers to open the
 * release page in the browser. Nothing is downloaded or installed: the owner
 * installs with adb or by tapping the APK on that page, as before.
 *
 * Nothing Jarvis knows goes anywhere near this request, and it never touches
 * the desktop - it is not a Jarvis request at all, which is also why it does
 * not carry `X-Jarvis-Client`. The "Check for new versions" setting turns it
 * off entirely.
 *
 * Everything here is pure, for the JVM tests; the request itself is
 * [com.jarvis.client.JarvisRuntime.checkForUpdate].
 */
object UpdateCheck {

    const val URL = "https://api.github.com/repos/darknight11ish/Epic-Jarvis/releases/tags/client-latest"

    /**
     * Where the button goes. Fixed here, not taken from the answer: the
     * phone opens its own idea of the release page, never a link a reply
     * handed it.
     */
    const val RELEASE_PAGE = "https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest"

    const val START_EVERY_MS = 6 * 60 * 60 * 1000L
    const val DAILY_MS = 24 * 60 * 60 * 1000L

    /** A release answer is a few kilobytes. Anything past this is not one. */
    const val MAX_BYTES = 512 * 1024

    /**
     * Whether to ask now. [lastTryMs] is the last attempt, whether or not it
     * worked, so a failing network is not asked again and again. A clock
     * that went backwards counts as due, once: the attempt then records the
     * new time.
     */
    fun due(nowMs: Long, lastTryMs: Long?, onStart: Boolean): Boolean {
        val last = lastTryMs ?: return true
        if (nowMs < last) return true
        return nowMs - last >= if (onStart) START_EVERY_MS else DAILY_MS
    }

    /** This build's commit, or null when it does not know it. */
    fun ownSha(buildSha: String?): String? =
        buildSha?.trim()?.lowercase()?.takeIf { HEX.matches(it) }

    /** The build on the release page, as read from the APK's name. */
    data class Published(
        /** The short commit in the APK's name. */
        val sha: String,
        /** When that APK was uploaded, or null when the answer did not say. */
        val uploadedAt: Instant?,
        /** The branch it was built from, from the release title, or null. */
        val branch: String?,
    )

    sealed interface Read {
        data class Found(val published: Published) : Read

        /** The answer was not a release this phone can read. [why] is for Checks. */
        data class Unreadable(val why: String) : Read
    }

    /**
     * Reads GitHub's answer for the release. Only the APK's name is trusted
     * for the commit (`jarvis-client-<7 hex>.apk`); the release's own
     * `target_commitish` is not, because the workflow moves the tag and not
     * always that field.
     */
    fun read(body: String): Read {
        val obj = runCatching { JarvisJson.parseToJsonElement(body) as? JsonObject }.getOrNull()
            ?: return Read.Unreadable("GitHub's answer was not readable.")
        val assets = (obj["assets"] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
        val apks = assets.mapNotNull { a ->
            // An upload still in progress (or abandoned) is "starter", not
            // "uploaded", and there is nothing to install from it yet.
            if (a.text("state").let { it != null && it != "uploaded" }) return@mapNotNull null
            val name = a.text("name") ?: return@mapNotNull null
            val sha = APK.matchEntire(name)?.groupValues?.get(1) ?: return@mapNotNull null
            Published(sha, a.text("created_at")?.let { runCatching { Instant.parse(it) }.getOrNull() }, null)
        }
        // The workflow deletes the old APK after uploading the new one, so
        // there is normally one; if a publish was cut short there can be
        // two, and the newer upload is the release.
        val newest = apks.maxByOrNull { it.uploadedAt ?: Instant.EPOCH }
            ?: return Read.Unreadable("The release on GitHub has no app file on it.")
        return Read.Found(newest.copy(branch = branchOf(obj.text("name"))))
    }

    /**
     * "Jarvis client - latest build (main @ abc1234)" -> "main". The title
     * is the workflow's own; anything else is simply not shown.
     */
    internal fun branchOf(title: String?): String? =
        title?.let { TITLE.find(it)?.groupValues?.get(1)?.trim() }?.takeIf { it.isNotEmpty() && it.length <= 100 }

    sealed interface Result {
        /** A build published after this one was made. */
        data class Newer(val published: Published) : Result

        /** This build, or one no newer than it. Nothing to say. */
        data object UpToDate : Result

        /** Cannot compare. [why] is for Checks. */
        data class Unknown(val why: String) : Result
    }

    /**
     * Newer means: a different commit, uploaded after this build's commit
     * was made. The tag is rolling and any branch can publish to it, so a
     * different commit alone could be older - a build from another branch
     * that finished before this one's commit existed.
     */
    fun compare(ownSha: String?, ownCommitSeconds: Long, published: Published): Result {
        val own = ownSha ?: return Result.Unknown("This build does not know which commit it is, so it cannot compare.")
        if (own.startsWith(published.sha.lowercase()) || published.sha.lowercase().startsWith(own)) {
            return Result.UpToDate
        }
        val uploaded = published.uploadedAt
        if (ownCommitSeconds > 0 && uploaded != null && uploaded.epochSecond <= ownCommitSeconds) {
            return Result.UpToDate
        }
        return Result.Newer(published)
    }

    /** The one quiet line. */
    fun line(p: Published): String =
        "A newer build of this app is on GitHub (" +
            (p.branch?.let { "$it, " } ?: "") + p.sha + "). Nothing is downloaded until you choose to."

    /**
     * What the phone shows. [newerLine] is Home's quiet line (and Checks');
     * [problem] is why the last check got no answer, shown on Checks only.
     */
    data class State(
        val newerLine: String? = null,
        val problem: String? = null,
        val lastTryMs: Long? = null,
    )

    /** How one request ended, before its body is read. */
    sealed interface Fetched {
        data object NoNetwork : Fetched
        data class Http(val code: Int) : Fetched
        data object TooBig : Fetched
        data class Body(val text: String) : Fetched
    }

    /**
     * The state after one request. A failure changes nothing the owner sees
     * on Home - a newer build already found stays found - and only adds the
     * reason on Checks. A real answer replaces everything.
     */
    fun next(prev: State, fetched: Fetched, ownSha: String?, ownCommitSeconds: Long, nowMs: Long): State {
        val failed = prev.copy(lastTryMs = nowMs)
        return when (fetched) {
            Fetched.NoNetwork -> failed.copy(problem = NETWORK_PROBLEM)
            is Fetched.Http -> failed.copy(problem = httpProblem(fetched.code))
            Fetched.TooBig -> failed.copy(problem = "GitHub's answer was too large to be a release.")
            is Fetched.Body -> when (val r = read(fetched.text)) {
                is Read.Unreadable -> failed.copy(problem = r.why)
                is Read.Found -> when (val c = compare(ownSha, ownCommitSeconds, r.published)) {
                    is Result.Newer -> State(line(c.published), null, nowMs)
                    Result.UpToDate -> State(null, null, nowMs)
                    is Result.Unknown -> State(null, c.why, nowMs)
                }
            }
        }
    }

    /** A failed check, for Checks only. */
    fun httpProblem(code: Int): String = when (code) {
        403, 429 -> "GitHub is limiting how often it answers (HTTP $code). It will be asked again later."
        404 -> "GitHub has no client-latest release right now (HTTP 404)."
        else -> "GitHub answered HTTP $code."
    }

    const val NETWORK_PROBLEM = "Could not reach GitHub."

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private val HEX = Regex("^[0-9a-f]{7,40}$")
    private val APK = Regex("^jarvis-client-([0-9a-fA-F]{7,40})\\.apk$")
    private val TITLE = Regex("\\(([^()@]+) @ [0-9a-fA-F]{7,40}\\)\\s*$")
}
