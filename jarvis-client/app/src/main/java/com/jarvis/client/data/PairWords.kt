package com.jarvis.client.data

import android.content.Context

/**
 * The 1,296 words the four pairing words are picked from (docs/PAIRING-DESIGN.md
 * §6.2): EFF's "short word list 2" - every word has its own first three
 * letters, and they were chosen to be easy to read aloud. Shipped as
 * `assets/pair-words.txt`, one word per line, in EFF's order; the PC has
 * the same file (`contract/pair-words.txt`), and the two must be identical
 * or the words would differ. Credited in assets/licenses/NOTICES.txt.
 */
object PairWords {

    const val ASSET = "pair-words.txt"

    @Volatile
    private var cached: List<String>? = null

    /** The list, or null when the asset cannot be read or is not 1,296 words. */
    fun load(context: Context): List<String>? {
        cached?.let { return it }
        val text = runCatching {
            context.applicationContext.assets.open(ASSET).bufferedReader(Charsets.UTF_8).use { it.readText() }
        }.getOrNull() ?: return null
        return parse(text)?.also { cached = it }
    }

    /** One word per line, blank lines ignored; null unless exactly 1,296 distinct words. */
    fun parse(text: String): List<String>? {
        val words = text.lineSequence().map { it.trim() }.filter { it.isNotEmpty() }.toList()
        return words.takeIf { it.size == 1296 && it.toSet().size == 1296 }
    }
}
