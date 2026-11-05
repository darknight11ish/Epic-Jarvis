package com.jarvis.client.call

import java.util.Arrays

/**
 * Cuts a stream of PCM into the chunks the PC takes, exactly.
 *
 * The recorder hands over whatever its buffer held - 80 ms, 160 ms, an odd
 * number of samples when a read is cut short - and this class turns that into
 * pieces of exactly [CallRecordRules.CHUNK_BYTES], holding the remainder until
 * the next read tops it up. Nothing is lost, nothing is duplicated, and the
 * total number of bytes out is always the total number in (plus whatever
 * [flush] returns at the end).
 *
 * WHY IT IS A CLASS AND NOT ARITHMETIC IN THE SERVICE. Chunk boundaries are
 * the one place a dropped or repeated sample can hide: the PC appends chunks
 * **in `seq` order** and turns the result into words, so a duplicated byte
 * becomes a repeated syllable and a missing one a swallowed word - and
 * neither is visible anywhere as an error. This is pure Kotlin so
 * `CallRecordRulesTest` can push awkward sizes through it (1 sample, 1 byte
 * short of a chunk, a chunk and a half at once, a chunk exactly) and add up
 * the output.
 *
 * One thread only: the service pushes from its recording loop and flushes from
 * the same one.
 */
class Chunker(private val chunkBytes: Int = CallRecordRules.CHUNK_BYTES) {

    private var buffer = ByteArray(chunkBytes)
    private var held = 0

    /** Bytes waiting for the rest of their chunk. */
    val buffered: Int get() = held

    /**
     * Add [count] bytes of [src] (from index 0) and return the complete chunks
     * that became available, in order. Usually zero or one; more when the
     * caller hands over more than a chunk at once (a resumed buffer, or a
     * very slow read loop).
     */
    fun push(src: ByteArray, count: Int = src.size): List<ByteArray> {
        if (count <= 0) return emptyList()
        require(count <= src.size) { "count $count is more than the ${src.size} bytes given" }
        val out = ArrayList<ByteArray>(count / chunkBytes + 1)
        var at = 0
        var left = count
        while (left > 0) {
            val room = chunkBytes - held
            val take = minOf(room, left)
            System.arraycopy(src, at, buffer, held, take)
            held += take
            at += take
            left -= take
            if (held == chunkBytes) {
                out.add(buffer)          // handed over whole; a fresh one is made below
                buffer = ByteArray(chunkBytes)
                held = 0
            }
        }
        return out
    }

    /**
     * The last, short chunk: everything held, or null when the recording ended
     * exactly on a boundary. The PC accepts a chunk shorter than the others
     * (the contract says "~32-64 KB"), and a second of audio is worth more
     * than a tidy boundary.
     */
    fun flush(): ByteArray? {
        if (held == 0) return null
        val tail = Arrays.copyOf(buffer, held)
        buffer = ByteArray(chunkBytes)
        held = 0
        return tail
    }

    /** Start again, holding nothing. Used when a recording ends and another begins. */
    fun reset() {
        buffer = ByteArray(chunkBytes)
        held = 0
    }
}
