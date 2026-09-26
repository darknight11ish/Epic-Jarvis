package com.jarvis.client.data

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * The desktop address must be on the owner's own networks (CLAUDE.md,
 * decided 2026-09-26): this PC, the home network, Tailscale or NordVPN
 * Meshnet. Anything on the open internet - a public tunnel such as ngrok or
 * Cloudflare included - is refused, so the pairing token never goes there.
 * https:// is refused off those networks too: the question is where the
 * token goes, not whether the line is scrambled.
 *
 * NOT a rule of this app's own. It is the backend's, word for word:
 * `backend/jarvis_local_http.py`, `_own_network` - the rule that already
 * decides where plain http:// may carry the Home Assistant token or the
 * calendar password. tools/gen_own_network_cases.py runs that real code over
 * a table of cases and writes `contract/own-network-cases.json`, which
 * OwnNetworkTest reads; the desktop's Rust (commands.rs, own_network_tests)
 * reads a byte-identical copy, so the two apps cannot drift apart unnoticed.
 *
 * Judged by spelling alone: nothing is looked up, no DNS, no network call.
 *
 * Where it is applied: [ClientSettings.baseUrl] gives no address at all for
 * a refused one, so nothing is ever sent there, and every request and the
 * event stream say [problem]'s sentence instead (JarvisApi, EventStream) -
 * the way any other connection failure is shown.
 *
 * Pure Kotlin, no Android types, so it runs on a plain JVM. OkHttp's
 * [toHttpUrlOrNull] is plain JVM code too - and it is the parser the
 * requests themselves use, which is why it is asked (see [problem]).
 */
object OwnNetwork {

    /**
     * What the owner sees when an address is refused - one sentence, checked
     * against `phone_message` in the shared table. `{address}` is the address
     * as saved. Its first half is the desktop's; its ending names only what
     * this phone can connect to: network_security_config.xml allows plain
     * http:// only to .ts.net and .nord names (and the phone itself), so a
     * home-network address that passes [problem] still cannot be reached
     * (ease-of-use audit 2026-09-27, #1e; PlatformReadiness says so for one).
     */
    const val MESSAGE =
        "Jarvis's address {address} is not on your own networks, so this app will not " +
            "send your pairing key there: on this phone, use your PC's Tailscale name " +
            "(ending in .ts.net) or its NordVPN Meshnet name (ending in .nord)."

    /** Name endings only the owner's own networks answer - the backend's `_OWN_SUFFIXES`. */
    private val OWN_SUFFIXES = listOf(".local", ".lan", ".home.arpa", ".ts.net", ".nord")

    /**
     * Null when [base] (a whole address with its scheme, as [BaseUrl.normalise]
     * makes it) is on the owner's own networks, else the sentence saying why
     * it is refused.
     *
     * Two readings of the host must BOTH pass, the way the backend judges
     * both `urlsplit`'s host and the one urllib dials: a plain split of the
     * text as written, and the host OkHttp parses - the parser every request
     * uses, which also decodes `%6c`-escapes and would take `a@b` as a user
     * name. So an address one of them misreads cannot slip past the other.
     */
    fun problem(base: String): String? {
        val b = base.trim().trimEnd('/')
        val typed = typedHost(b)
        val dialled = runCatching { b.toHttpUrlOrNull()?.host }.getOrNull()
        if (typed != null && dialled != null && ownHost(typed) && ownHost(dialled)) return null
        return message(b)
    }

    /**
     * [MESSAGE] for [base], which is shown as written - unless it holds
     * something that must not be repeated back (a user name or password
     * written into it, "me:pw@...", or a space), when the sentence leaves the
     * address out.
     */
    fun message(base: String): String {
        val unshown = base.isEmpty() || base.any { it == '@' || it.isWhitespace() || it.isISOControl() }
        return if (unshown) MESSAGE.replace("{address} ", "") else MESSAGE.replace("{address}", base)
    }

    /**
     * The host as the address is written: after `scheme://`, up to the first
     * `/`, `?`, `#` or `\`, without a `:port`, and without IPv6's brackets.
     * Null when that is not one host (an unbracketed IPv6 address, which
     * reads as a host and a port, or a port that is not a number).
     */
    internal fun typedHost(base: String): String? {
        val rest = if ("://" in base) base.substringAfter("://") else base
        val authority = rest.takeWhile { it != '/' && it != '?' && it != '#' && it != '\\' }
        val host: String
        val port: String?
        if (authority.startsWith("[")) {
            val close = authority.indexOf(']')
            if (close < 0) return null
            host = authority.substring(1, close)
            val after = authority.substring(close + 1)
            port = when {
                after.isEmpty() -> null
                after.startsWith(":") -> after.substring(1)
                else -> return null
            }
        } else {
            host = authority.substringBefore(':')
            port = if (':' in authority) authority.substringAfter(':') else null
        }
        if (port != null && port.isNotEmpty() && !port.all { it in '0'..'9' }) return null
        return host.ifEmpty { null }
    }

    /**
     * Is [host] this PC or on one of the owner's own networks? The backend's
     * `_own_network`, line for line:
     *
     * - an address (in any spelling the operating system would still dial -
     *   `3232235777`, `0xc0a80101`, `10.1` - judged as that address) must be
     *   in 127.0.0.0/8, ::1, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16,
     *   fc00::/7 (which holds Tailscale's fd7a:115c:a1e0::/48) or
     *   100.64.0.0/10 (Tailscale and NordVPN Meshnet). Link-local
     *   (169.254.x.x, fe80::) is not on the list, the same as the backend;
     * - a name must be `localhost`, a single word with no dot (a
     *   home-network name such as `nas`, which the home router answers), or
     *   end in `.local`, `.lan`, `.home.arpa`, `.ts.net` or `.nord`.
     */
    fun ownHost(host: String): Boolean {
        val h = host.trim().lowercase().trimEnd('.')
        if (h.isEmpty()) return false
        address(h)?.let { return ownAddress(it) }
        if (!plainName(h)) return false // an odd IPv6 form, an "@", a space, a "%"...
        if (h == "localhost" || '.' !in h) return true
        return OWN_SUFFIXES.any { h.endsWith(it) }
    }

    /** The backend's `_OWN_NETS`, for a 4- or 16-byte address. */
    private fun ownAddress(ip: ByteArray): Boolean {
        val a = ip[0].toInt() and 0xff
        val b = ip[1].toInt() and 0xff
        if (ip.size == 4) {
            return a == 127 || a == 10 || (a == 172 && b in 16..31) ||
                (a == 192 && b == 168) || (a == 100 && b in 64..127)
        }
        val loopback = (0 until 15).all { ip[it].toInt() == 0 } && ip[15].toInt() == 1
        return loopback || (a and 0xfe) == 0xfc
    }

    /**
     * The address [host] (lower case) denotes, 4 or 16 bytes, or null when it
     * is a name - the backend's `_as_address`: an IPv6 address, else the
     * numeric forms `inet_aton` reads. An IPv4-mapped IPv6 address
     * (`::ffff:192.168.1.1`) is judged as its IPv4 address.
     */
    internal fun address(host: String): ByteArray? {
        val v6 = ipv6(host)
        if (v6 != null) {
            val mapped = (0 until 10).all { v6[it].toInt() == 0 } &&
                (v6[10].toInt() and 0xff) == 0xff && (v6[11].toInt() and 0xff) == 0xff
            return if (mapped) v6.copyOfRange(12, 16) else v6
        }
        return inetAton(host)
    }

    /**
     * The classic BSD `inet_aton` reading of a numeric host: one to four
     * parts separated by dots, each decimal, `0x` hex or leading-zero octal,
     * the last part filling whatever bytes are left. Each part must start
     * with a digit and hold only hex digits or `x`, as glibc's does (so a
     * `+` or `-` sign is never read as part of a number).
     */
    private fun inetAton(s: String): ByteArray? {
        val parts = s.split('.')
        if (parts.size > 4) return null
        val numeric = parts.all { p ->
            p.isNotEmpty() && p[0] in '0'..'9' && p.all { it in '0'..'9' || it in 'a'..'f' || it == 'x' }
        }
        if (!numeric) return null
        val values = parts.map { p ->
            val (digits, radix) = when {
                p.startsWith("0x") -> p.substring(2) to 16
                p.length > 1 && p.startsWith("0") -> p.substring(1) to 8
                else -> p to 10
            }
            if (digits.isEmpty()) return null
            digits.toLongOrNull(radix) ?: return null
        }
        val head = values.dropLast(1)
        val last = values.last()
        if (head.any { it > 0xff }) return null
        val tailBits = 8 * (4 - head.size)
        if (last >= (1L shl tailBits)) return null
        var out = last
        head.forEachIndexed { i, v -> out = out or (v shl (24 - 8 * i)) }
        return byteArrayOf(
            (out shr 24).toByte(), (out shr 16).toByte(), (out shr 8).toByte(), out.toByte(),
        )
    }

    /** A strict dotted quad: four decimal parts, no leading zeros, each at most 255. */
    private fun strictIpv4(s: String): ByteArray? {
        val parts = s.split('.')
        if (parts.size != 4) return null
        val bytes = ByteArray(4)
        parts.forEachIndexed { i, p ->
            if (p.isEmpty() || p.length > 3 || !p.all { it in '0'..'9' }) return null
            if (p.length > 1 && p[0] == '0') return null
            val v = p.toInt()
            if (v > 255) return null
            bytes[i] = v.toByte()
        }
        return bytes
    }

    /**
     * A textual IPv6 address (lower case, no brackets, no zone) as 16 bytes,
     * or null. Groups of one to four hex digits; one `::` standing for at
     * least one group of zeros; an IPv4 dotted quad allowed as the last 32
     * bits.
     */
    private fun ipv6(s: String): ByteArray? {
        if (':' !in s) return null
        if (!s.all { it in '0'..'9' || it in 'a'..'f' || it == ':' || it == '.' }) return null
        var text = s
        var v4: ByteArray? = null
        val lastColon = text.lastIndexOf(':')
        if ('.' in text.substring(lastColon + 1)) {
            v4 = strictIpv4(text.substring(lastColon + 1)) ?: return null
            text = text.substring(0, lastColon + 1) + "0:0"
        }
        val halves = text.split("::")
        if (halves.size > 2) return null
        val head = groups(halves[0]) ?: return null
        val tail = if (halves.size == 2) groups(halves[1]) ?: return null else emptyList()
        val count = head.size + tail.size
        if (halves.size == 1 && count != 8) return null
        if (halves.size == 2 && count > 7) return null
        val all = head + List(8 - count) { 0 } + tail
        val bytes = ByteArray(16)
        all.forEachIndexed { i, g ->
            bytes[2 * i] = (g shr 8).toByte()
            bytes[2 * i + 1] = g.toByte()
        }
        v4?.copyInto(bytes, destinationOffset = 12)
        return bytes
    }

    /** "1:ab:0" as [1, 0xab, 0]; "" as none; null for an empty or over-long group. */
    private fun groups(part: String): List<Int>? {
        if (part.isEmpty()) return emptyList()
        return part.split(':').map { g ->
            if (g.isEmpty() || g.length > 4) return null
            g.toIntOrNull(16) ?: return null
        }
    }

    /**
     * The backend's `_NAME_RE`, `^[\w-]+(\.[\w-]+)*$`: words of letters,
     * digits, `_` or `-`, joined by single dots.
     */
    private fun plainName(host: String): Boolean =
        host.split('.').all { label ->
            label.isNotEmpty() && label.all { it.isLetterOrDigit() || it == '_' || it == '-' }
        }
}
