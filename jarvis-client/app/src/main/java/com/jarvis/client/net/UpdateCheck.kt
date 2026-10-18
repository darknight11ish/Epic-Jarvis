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
 * release page in the browser.
 *
 * Since 2026-10-11 the newer build can also be downloaded from inside the app
 * (the owner's request: "check github ... download if i press download, and
 * will show a simple changelogg"). [Published] carries the release body's
 * changes as plain lines, the APK asset's own address and its size; the
 * Download button fetches it, reads the file's signing certificate and
 * REFUSES anything that is not signed with the digest pinned in
 * [SIGNER_SHA256]. Only a verified file is ever offered to Android's
 * installer. Nothing moves until that button is pressed: the check itself
 * still only reads a few kilobytes of JSON.
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

    /**
     * The SHA-256 of the certificate the published APK must be signed with,
     * **pinned in the app** (the owner's request of 2026-10-11: "verify before
     * offering to install"). A download whose certificate does not match this
     * is refused; it is never handed to the installer.
     *
     * Where the number comes from, and how it was checked: the release APK is
     * signed with the project's `keystore/debug.keystore`, so this must agree
     * with what `keytool` reads from it AND with what `apksigner` reads from
     * the file itself. Both were read on 2026-10-11:
     *
     *   keytool -list -v -keystore "$USERPROFILE\.android\debug.keystore" `
     *       -storepass android -alias androiddebugkey
     *     -> SHA256: 62:EF:77:42:E3:5E:74:2A:94:A0:71:BB:A8:36:31:FD:
     *                6D:B7:8B:5B:50:96:1F:7B:45:71:9D:73:65:00:D7:B5
     *   apksigner verify --print-certs   (on the copy installed on the owner's
     *       own CPH2419, taken with `pm path com.jarvis.client`)
     *     -> Signer #1 certificate SHA-256 digest: 62ef7742…d7b5
     *
     * The publish step prints the same value in the release body
     * (`.github/workflows/jarvis-client.yml` derives it from the keystore it
     * restored), so it is not a secret - it is in every APK. It IS the one
     * thing a swapped file cannot fake.
     */
    const val SIGNER_SHA256 =
        "62ef7742e35e742a94a071bba83631fd6db78b5b50961f7b45719d736500d7b5"

    /**
     * The heading the publish step writes above the changes. The app shows the
     * `- line` entries under it as plain lines.
     */
    const val CHANGES_HEADING = "What's changed"

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
        /**
         * Where the APK itself is, from the asset's own
         * `browser_download_url` - or null when the answer did not carry one,
         * in which case the app offers no Download button at all rather than
         * inventing an address. Checked with [isReleaseDownload] before it is
         * ever fetched.
         */
        val downloadUrl: String? = null,
        /** The APK's size in bytes, when GitHub said. 0 when it did not. */
        val downloadBytes: Long = 0L,
        /**
         * The changes the release names, as plain lines (the commit subjects
         * the publish step writes under [CHANGES_HEADING]). Empty when the
         * release body carries none - the app then simply shows no list.
         */
        val changes: List<String> = emptyList(),
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
        val changes = changesIn(obj.text("body"))
        val apks = assets.mapNotNull { a ->
            // An upload still in progress (or abandoned) is "starter", not
            // "uploaded", and there is nothing to install from it yet.
            if (a.text("state").let { it != null && it != "uploaded" }) return@mapNotNull null
            val name = a.text("name") ?: return@mapNotNull null
            val sha = APK.matchEntire(name)?.groupValues?.get(1) ?: return@mapNotNull null
            val url = a.text("browser_download_url")?.takeIf { isReleaseDownload(it) }
            Published(
                sha = sha,
                uploadedAt = a.text("created_at")?.let { runCatching { Instant.parse(it) }.getOrNull() },
                branch = null,
                downloadUrl = url,
                downloadBytes = (a["size"] as? JsonPrimitive)?.content?.toLongOrNull() ?: 0L,
                changes = changes,
            )
        }
        // The workflow deletes the old APK after uploading the new one, so
        // there is normally one; if a publish was cut short there can be
        // two, and the newer upload is the release.
        val newest = apks.maxByOrNull { it.uploadedAt ?: Instant.EPOCH }
            ?: return Read.Unreadable("The release on GitHub has no app file on it.")
        return Read.Found(newest.copy(branch = branchOf(obj.text("name"))))
    }

    /**
     * Whether [url] is a file on this repository's own releases - the only
     * address the Download button may fetch. GitHub hands us this string, and
     * the app never follows a link a reply chose: it must be `https` on
     * `github.com`, under this repository's `releases/download/` path, and
     * nothing else. Anything else is treated as "no download offered".
     */
    fun isReleaseDownload(url: String): Boolean {
        val u = url.trim()
        if (!u.startsWith("https://github.com/", ignoreCase = true)) return false
        if (u.contains("@")) return false          // no credentials before the host
        if (u.contains("\n") || u.contains("\r")) return false
        return u.startsWith("$REPO_URL/releases/download/", ignoreCase = true)
    }

    /**
     * The changes a release body names, as plain lines - one per `- ` or `* `
     * entry under [CHANGES_HEADING]. The publish step writes the commit
     * subjects there, so this is the owner's "simple changelog".
     *
     * Everything else the body may carry (headings, paragraphs, code blocks,
     * the checksum lines, a bare URL) is left out: the phone shows CHANGES,
     * not instructions. At most [MAX_CHANGES] lines, each cut to
     * [MAX_CHANGE_CHARS], because a release body is written by CI and this is
     * a phone screen.
     */
    fun changesIn(body: String?): List<String> {
        if (body.isNullOrBlank()) return emptyList()
        val out = ArrayList<String>()
        val lines = body.replace("\r\n", "\n").replace('\r', '\n').split('\n')
        // A body with no heading at all keeps every bullet it has: the
        // workflow may write a plain list, and dropping it would show the
        // owner an empty changelog for a release that named its changes.
        val headings = body.contains(CHANGES_HEADING, ignoreCase = true)
        var headingSeen = !headings
        var inFence = false
        for (raw in lines) {
            val line = raw.trim()
            if (line.startsWith("```")) {
                inFence = !inFence
                continue
            }
            if (inFence) continue
            if (line.startsWith("#")) {
                // A heading: only the changes one opens the section, and any
                // other heading closes it again.
                headingSeen = line.trimStart('#').trim().startsWith(CHANGES_HEADING, ignoreCase = true)
                continue
            }
            val isBullet = line.startsWith("- ") || line.startsWith("* ")
            if (!isBullet || !headingSeen) continue
            val text = plain(line.drop(2))
            if (text.isNotEmpty()) out.add(text.take(MAX_CHANGE_CHARS))
            if (out.size >= MAX_CHANGES) break
        }
        return out
    }

    /** One changelog line with the markdown taken off: backticks, bold, links. */
    private fun plain(s: String): String {
        var t = s
        // [text](url) -> text, and a bare <url> dropped.
        t = LINK.replace(t, "$1")
        t = t.replace(BARE_URL, "")
        t = t.replace("`", "").replace("**", "").replace("__", "")
        return t.replace(WHITESPACE, " ").trim().trimEnd(':').trim()
    }

    /**
     * Whether a downloaded file's certificate digest matches the one pinned in
     * the app ([SIGNER_SHA256]). [found] is what Android read out of the file,
     * or null when it could read none at all. A null is a REFUSAL, not a
     * warning: a file whose signature cannot be read is a file we cannot
     * vouch for.
     */
    fun signerMatches(found: String?): Boolean {
        val want = SIGNER_SHA256.lowercase()
        val got = found?.trim()?.lowercase()?.replace(":", "")?.replace(" ", "") ?: return false
        return got.isNotEmpty() && got == want
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

    /**
     * Whether a cached line is about the build that is now installed. The
     * line carries the published short sha in its parentheses. After the
     * owner installs exactly that build, the cached line must stop being
     * shown at once - not six hours later when the next check runs. The
     * prefixes are compared both ways because the line has 7 characters and
     * the build knows 40 (or vice versa for an old build).
     */
    fun lineNamesBuild(line: String?, ownSha: String?): Boolean {
        val own = ownSha?.trim()?.lowercase().orEmpty()
        if (own.isEmpty() || line.isNullOrBlank()) return false
        val open = line.lastIndexOf('(')
        val close = line.lastIndexOf(')')
        if (open < 0 || close <= open) return false
        val inside = line.substring(open + 1, close).trim()
        val named = inside.split(',').lastOrNull()?.trim()?.lowercase().orEmpty()
        if (!HEX.matches(named)) return false
        return named.startsWith(own) || own.startsWith(named)
    }

    /**
     * The cached banner line this build may still show, or null when it must
     * be dropped. Two rules, both needed:
     *
     *  1. **The cache belongs to this app version.** [cachedOnVersion] is the
     *     `BuildConfig.VERSION_NAME` that was running when the line was
     *     stored (null for a cache written before that was recorded). A
     *     different - or absent - version means the line was written by an
     *     older APK, and installing an APK is exactly the moment "anything
     *     cached before this install is stale" becomes true. This is the rule
     *     [lineNamesBuild] alone cannot give: installing `0.2.1825 (b0f2c25)`
     *     leaves a cached line naming `7ddb5b8`, which is different from the
     *     running sha but still stale.
     *  2. **The line must not name this build.** [lineNamesBuild] compares
     *     the commit in the line's parentheses with the running build, so even
     *     a live poll that named the very sha now installed is never shown as
     *     "newer".
     *
     * When the running build does not know its version (blank [ownVersion]) the
     * version rule cannot be applied, so only rule 2 is used rather than
     * dropping a cache that may still be right.
     */
    fun cachedLineForBuild(
        cachedLine: String?,
        cachedOnVersion: String?,
        ownVersion: String?,
        ownSha: String?,
    ): String? {
        val line = cachedLine?.takeIf { it.isNotBlank() && !lineNamesBuild(it, ownSha) }
            ?: return null
        val own = ownVersion?.trim().orEmpty()
        if (own.isEmpty()) return line
        return line.takeIf { cachedOnVersion?.trim() == own }
    }
    /** The one quiet line. */
    fun line(p: Published): String =
        "A newer build of this app is on GitHub (" +
            (p.branch?.let { "$it, " } ?: "") + p.sha + "). Nothing is downloaded until you choose to."

    /**
     * What the phone shows. [newerLine] is Home's quiet line (and Checks');
     * [problem] is why the last check got no answer, shown on Checks only.
     *
     * [published] is the newer build itself, kept in memory only: it is what
     * the Download button needs (the asset's address, its size and the
     * changes). It is deliberately NOT written to the settings file - an
     * address that survived a restart is one more thing that could go stale -
     * so after a restart the button comes back with the next check, which the
     * app already runs on start.
     */
    data class State(
        val newerLine: String? = null,
        val problem: String? = null,
        val lastTryMs: Long? = null,
        val published: Published? = null,
    )

    /**
     * What the Download button is doing. Nothing is fetched until
     * [com.jarvis.client.platform.UpdateChecker.download] is called by a real
     * press - this is only the shape that press moves through.
     */
    sealed interface Download {
        /** Nothing downloaded (or nothing offered). No bytes have moved. */
        data object Idle : Download

        /** Fetching, with what has arrived so far. */
        data class Fetching(val bytes: Long, val total: Long) : Download

        /**
         * Downloaded, certificate checked, ready to hand to Android's
         * installer. [file] is the app's own private copy.
         */
        data class Ready(val file: java.io.File) : Download

        /**
         * Refused or failed. [why] is plain words for the owner. A REFUSED
         * certificate lands here and the file is deleted, never offered.
         */
        data class Refused(val why: String) : Download
    }

    /**
     * What [Download] comes to after a fetch ended. [cert] is the SHA-256
     * Android read out of the downloaded file, or null when it could read
     * none - and null is a refusal, not a warning.
     */
    fun afterFetch(bytes: Long, cert: String?, onVerified: (String) -> Download): Download =
        if (!signerMatches(cert)) Download.Refused(refusal(cert)) else onVerified(cert!!)

    /** Plain words for a file the app will not offer: the owner asked why. */
    fun refusal(cert: String?): String =
        "The downloaded file is not signed by Jarvis's own key, so it was not offered for install. " +
            "It has been deleted. (Expected ${SIGNER_SHA256.take(16)}…, " +
            (cert?.take(16)?.let { "got $it…" } ?: "and its signature could not be read at all") + ")"

    /** Plain words while a download is running. */
    fun progress(bytes: Long, total: Long): String =
        if (total > 0) "${bytes * 100 / total}% of ${mb(total)} MB"
        else "${mb(bytes)} MB downloaded"

    private fun mb(bytes: Long): String = "%.1f".format(bytes / 1_000_000.0)

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
                    is Result.Newer -> State(line(c.published), null, nowMs, c.published)
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

    /** The most changelog lines the phone shows, and how long each may be. */
    const val MAX_CHANGES = 40
    const val MAX_CHANGE_CHARS = 200

    /** This repository, as the release downloads are addressed. */
    const val REPO_URL = "https://github.com/darknight11ish/Epic-Jarvis"

    /**
     * The largest app file this will download. The published APK is around
     * 80 MB; anything past this is not one, and the download stops rather
     * than filling the phone.
     */
    const val MAX_APK_BYTES = 400L * 1024 * 1024

    /**
     * Whether [host] is one of GitHub's own hosts - the only place the app
     * will write an APK from. GitHub answers a release asset with a redirect
     * to `objects.githubusercontent.com`, so that hop has to be allowed; a
     * hop anywhere else is refused, which is the point of checking every one.
     */
    fun isGithubHost(host: String?): Boolean {
        val h = host?.trim()?.lowercase() ?: return false
        return h == "github.com" || h.endsWith(".github.com") || h == "githubusercontent.com" ||
            h.endsWith(".githubusercontent.com")
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private val HEX = Regex("^[0-9a-f]{7,40}$")
    private val APK = Regex("^jarvis-client-([0-9a-fA-F]{7,40})\\.apk$")
    private val TITLE = Regex("\\(([^()@]+) @ [0-9a-fA-F]{7,40}\\)\\s*$")
    private val LINK = Regex("\\[([^\\]]+)\\]\\([^)]*\\)")
    private val BARE_URL = Regex("<?https?://\\S+>?")
    private val WHITESPACE = Regex("\\s+")
}
