package com.jarvis.client

import com.jarvis.client.data.BaseUrl
import com.jarvis.client.data.PhoneAddress
import com.jarvis.client.net.HostSource
import com.jarvis.client.net.TokenSource

/**
 * The three things `JarvisApi` asks of Android, answered without it.
 *
 * `ApiContractTest`, `EventStreamContractTest` and `PicturesConfirmContractTest`
 * used to live in `androidTest`, because `ClientSettings` and `TokenStore` need
 * a `Context` to reach SharedPreferences and the Keystore. A test that needs an
 * emulator is a test that runs in the `Jarvis client` job, and that job is
 * path-filtered on `pull_request` - a pull request that touches no phone file
 * does not start it - and it is not one of the seven required checks. The wire
 * contract does not belong in the one place a merge cannot be gated on. What
 * these suites prove is the WIRE: which route, which header, which body, how
 * many requests one tap makes. None of that needs a phone.
 *
 * The route is not a detail. DEF-047 recorded the phone's Delete button posting
 * to the uncarded `/api/history/delete` while the carded route was
 * `POST /api/conversations/clear`; #1281 (`23d509235`) moved the button across.
 * These suites are what pin a route afterwards, and from here they do it in a
 * job that is required to merge.
 *
 * [com.jarvis.client.net.JarvisApi] now asks for two interfaces - `baseUrl`,
 * `baseProblem` and `token` - so these fakes are the whole of what it can tell
 * apart from the real thing.
 *
 * [FakeHost] normalises and judges the address with the same two functions
 * `ClientSettings` calls, so a test address is measured by the app's own rule
 * rather than by a rule invented here. The one deliberate difference is
 * `allowLoopback = true`: a release build refuses loopback addresses, and this
 * suite talks to a MockWebServer on 127.0.0.1 on purpose.
 *
 * [FakeTokens] holds the token in memory. The real Keystore path is still
 * tested on a device, by `TokenStoreTest` in `androidTest`, where it belongs.
 */
class FakeHost : HostSource {
    private var saved: String = ""

    fun setHost(value: String) {
        saved = value.trim().trim('/')
    }

    /** Nothing is persisted on a plain JVM, so there is no resume point to clear. */
    fun clearResumePoint() {
    }

    override fun baseUrl(): String? = BaseUrl.normalise(saved)?.takeIf {
        PhoneAddress.problem(it, allowLoopback = true) == null
    }

    override fun baseProblem(): String? = BaseUrl.normalise(saved)?.let {
        PhoneAddress.problem(it, allowLoopback = true)
    }
}

class FakeTokens : TokenSource {
    private var saved: String = ""

    fun setToken(value: String) {
        saved = value
    }

    fun clear() {
        saved = ""
    }

    override fun token(): String = saved
}
