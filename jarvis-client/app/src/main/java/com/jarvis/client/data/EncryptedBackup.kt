/*
 * Adapted for Jarvis from Mobile-Harness:
 *   app/src/main/java/com/jarves/mh/backup/BackupCrypto.kt
 *   Copyright (c) 2026 Mobile Harness Contributors
 *   https://github.com/techjarves/Mobile-Harness  (MIT License)
 *
 * Licensed under the MIT License. The full notice and licence text travel with
 * this app: THIRD-PARTY-NOTICES.txt at the top of the repository, and
 * jarvis-client/app/src/main/assets/licenses/NOTICES.txt inside the APK.
 *
 * WHAT WAS KEPT (the reason this file is a copy and not a fresh design): the
 * versioned header, PBKDF2-HMAC-SHA256 from a typed password, AES-256-GCM in
 * fixed-size segments, and the AAD that binds each segment to its index and to
 * a final marker - so a truncated, reordered or spliced file fails instead of
 * decrypting into something shorter. Those are the parts that are easy to get
 * quietly wrong.
 *
 * WHAT WAS CHANGED FOR JARVIS:
 *  - the magic bytes, exception messages, package and names are Jarvis's;
 *  - a password is REQUIRED (Mobile-Harness also allows an unencrypted file;
 *    a Jarvis settings backup is always encrypted);
 *  - the format version is checked before any key work, and a newer file is
 *    refused with its own exception so the app can say why.
 *
 * This file is deliberately free of `android.*`: the container is plain Java
 * I/O plus `javax.crypto`, so `EncryptedBackupTest` proves it on the JVM.
 * [SettingsBackup] is the one thing written into it, and [SettingsBackupStore]
 * is the Android half that reads and applies the phone's settings.
 */

package com.jarvis.client.data

import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.security.SecureRandom
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

/**
 * The password typed for this file does not open it.
 *
 * Deliberately a distinct type: a wrong password is the owner's mistake and is
 * said plainly ([SettingsBackup.WRONG_PASSWORD]); a damaged file is not.
 */
class WrongBackupPasswordException : IOException("That password does not open this backup")

/** The file is well-formed enough to read a version, and it was made by a newer app. */
class NewerBackupException : IOException("This backup was made by a newer version of the Jarvis app")

/** Not a Jarvis backup, or damaged/tampered. Never carries the password. */
open class InvalidBackupException(message: String) : IOException(message)

/** A well-formed file whose payload is bigger than the app will hold in memory. */
class BackupTooLargeException : InvalidBackupException(SettingsBackup.TOO_BIG)

/** What the plaintext header says, before any key is derived. */
data class BackupHeader(
    val version: Int,
    val encrypted: Boolean,
    val salt: ByteArray?,
    val iterations: Int,
)

/**
 * The `.jarvisbackup` container: a short plaintext header, then the payload
 * (one JSON settings snapshot) cut into AES-256-GCM segments.
 *
 * The header is NOT secret - it names the format version, that the file is
 * encrypted, the salt and the PBKDF2 iteration count. It is authenticated
 * only in the sense that the first segment's tag will not verify if any of it
 * (salt, iterations, version) is changed, because the key derived from them
 * is different.
 */
object EncryptedBackup {

    /** Bumped only when the container's shape changes; a newer file is refused. */
    const val FORMAT_VERSION = 1

    /** "JVBK" - Jarvis Vault BacKup. */
    private val MAGIC = byteArrayOf('J'.code.toByte(), 'V'.code.toByte(), 'B'.code.toByte(), 'K'.code.toByte())

    private const val FLAG_ENCRYPTED = 1
    private const val SALT_BYTES = 16
    private const val NONCE_BYTES = 12
    private const val TAG_BITS = 128

    /**
     * How much plaintext one GCM segment carries. Settings are a few kilobytes,
     * so a real backup is one segment; the streaming shape is kept from the
     * adapted file so the container never has to load a whole file to
     * authenticate it, and so a future owner of a larger backup cannot make
     * this file allocate that size in one go.
     */
    const val SEGMENT_BYTES = 64 * 1024

    /** PBKDF2 rounds. The adapted project used 210,000; kept, and it is in the header. */
    const val DEFAULT_ITERATIONS = 210_000

    /**
     * Writes the header and returns the stream the plaintext payload is written
     * into. Closing the returned stream finishes the last segment, flushes and
     * closes [output].
     */
    fun openWriter(
        output: OutputStream,
        password: CharArray,
        iterations: Int = DEFAULT_ITERATIONS,
    ): OutputStream {
        require(password.isNotEmpty()) { "a password is required" }
        require(iterations in 1..10_000_000) { "iteration count out of range" }
        val data = DataOutputStream(output)
        val salt = ByteArray(SALT_BYTES).also(SecureRandom()::nextBytes)
        data.write(MAGIC)
        data.writeByte(FORMAT_VERSION)
        data.writeByte(FLAG_ENCRYPTED)
        data.write(salt)
        data.writeInt(iterations)
        data.flush()
        return EncryptingOutputStream(output, deriveKey(password, salt, iterations))
    }

    /** Reads only the header; no key is derived and no password is needed. */
    fun readHeader(input: InputStream): BackupHeader {
        val data = DataInputStream(input)
        val magic = ByteArray(MAGIC.size)
        try {
            data.readFully(magic)
        } catch (_: EOFException) {
            throw InvalidBackupException("Not a Jarvis settings backup")
        }
        if (!magic.contentEquals(MAGIC)) throw InvalidBackupException("Not a Jarvis settings backup")
        val version = data.readUnsignedByte()
        if (version > FORMAT_VERSION) throw NewerBackupException()
        if (version < 1) throw InvalidBackupException("Damaged backup header")
        val flags = data.readUnsignedByte()
        if (flags and FLAG_ENCRYPTED == 0) {
            // Every file this app writes is encrypted. An unencrypted one is
            // either foreign or stripped, and either way it is not accepted.
            throw InvalidBackupException("This file is not encrypted, so it is not a Jarvis settings backup")
        }
        val salt = ByteArray(SALT_BYTES).also(data::readFully)
        val iterations = data.readInt()
        if (iterations !in 1..10_000_000) throw InvalidBackupException("Damaged backup header")
        return BackupHeader(version, true, salt, iterations)
    }

    /** Reads the header and returns the plaintext stream. The caller must read it all. */
    fun openReader(input: InputStream, password: CharArray): InputStream {
        val header = readHeader(input)
        if (password.isEmpty()) throw WrongBackupPasswordException()
        return DecryptingInputStream(input, deriveKey(password, header.salt!!, header.iterations))
    }

    /**
     * Reads the whole payload, so EVERY segment's tag is checked before the
     * caller can apply any of it. A settings restore uses this rather than
     * streaming into the preferences, because "half restored, then a tag
     * failed" must not be a state this app can reach.
     *
     * [maxBytes] is a bound, not a hint: a file that decrypts to more than the
     * app will ever use is refused instead of being read into memory. The
     * settings snapshot is a few kilobytes; the cap exists because the file is
     * chosen by a person and a crafted one must not be able to exhaust the
     * phone.
     */
    fun readAll(
        input: InputStream,
        password: CharArray,
        maxBytes: Int = Int.MAX_VALUE,
    ): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(SEGMENT_BYTES)
        openReader(input, password).use { stream ->
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) break
                if (out.size().toLong() + count > maxBytes.toLong()) throw BackupTooLargeException()
                out.write(buffer, 0, count)
            }
        }
        return out.toByteArray()
    }

    /** Derives the AES key. PBKDF2WithHmacSHA256 is in the Java/Android standard libraries. */
    private fun deriveKey(password: CharArray, salt: ByteArray, iterations: Int): SecretKey {
        val spec = PBEKeySpec(password, salt, iterations, 256)
        try {
            val encoded = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded
            return SecretKeySpec(encoded, "AES")
        } finally {
            spec.clearPassword()
        }
    }

    /** Binds a segment to its position and to whether it is the last one. */
    private fun aad(index: Long, final: Boolean): ByteArray =
        ByteBuffer.allocate(9).putLong(index).put(if (final) 1 else 0).array()

    private class EncryptingOutputStream(
        private val output: OutputStream,
        private val key: SecretKey,
    ) : OutputStream() {
        private val data = DataOutputStream(output)
        private val buffer = ByteArray(SEGMENT_BYTES)
        private val random = SecureRandom()
        private var filled = 0
        private var index = 0L
        private var closed = false

        override fun write(b: Int) = write(byteArrayOf(b.toByte()), 0, 1)

        override fun write(b: ByteArray, off: Int, len: Int) {
            var offset = off
            var remaining = len
            while (remaining > 0) {
                if (filled == buffer.size) writeSegment(final = false)
                val count = minOf(remaining, buffer.size - filled)
                System.arraycopy(b, offset, buffer, filled, count)
                filled += count
                offset += count
                remaining -= count
            }
        }

        private fun writeSegment(final: Boolean) {
            val nonce = ByteArray(NONCE_BYTES).also(random::nextBytes)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(TAG_BITS, nonce))
            cipher.updateAAD(aad(index, final))
            val encrypted = cipher.doFinal(buffer, 0, filled)
            // 1 = final, 0 = more follows. The length lets the reader refuse an
            // absurd segment before allocating it.
            data.writeByte(if (final) 1 else 0)
            data.writeInt(encrypted.size)
            data.write(nonce)
            data.write(encrypted)
            index++
            filled = 0
        }

        override fun flush() = data.flush()

        override fun close() {
            if (closed) return
            closed = true
            // Always a final segment, even when nothing was written: an empty
            // payload still authenticates as a final empty segment.
            writeSegment(final = true)
            data.flush()
            output.close()
        }
    }

    private class DecryptingInputStream(
        private val input: InputStream,
        private val key: SecretKey,
    ) : InputStream() {
        private val data = DataInputStream(input)
        private var plain = ByteArray(0)
        private var position = 0
        private var index = 0L
        private var finished = false

        override fun read(): Int {
            val one = ByteArray(1)
            return if (read(one, 0, 1) < 0) -1 else one[0].toInt() and 0xff
        }

        override fun read(b: ByteArray, off: Int, len: Int): Int {
            if (len == 0) return 0
            while (position >= plain.size) {
                if (finished) return -1
                nextSegment()
            }
            val count = minOf(len, plain.size - position)
            System.arraycopy(plain, position, b, off, count)
            position += count
            return count
        }

        private fun nextSegment() {
            val final = try {
                data.readUnsignedByte() == 1
            } catch (_: EOFException) {
                throw InvalidBackupException("Backup file is incomplete")
            }
            val length = data.readInt()
            if (length !in (TAG_BITS / 8)..(SEGMENT_BYTES + TAG_BITS / 8)) {
                throw InvalidBackupException("Backup file is damaged")
            }
            val nonce = ByteArray(NONCE_BYTES)
            val encrypted = ByteArray(length)
            try {
                data.readFully(nonce)
                data.readFully(encrypted)
            } catch (_: EOFException) {
                throw InvalidBackupException("Backup file is incomplete")
            }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, nonce))
            cipher.updateAAD(aad(index, final))
            plain = try {
                cipher.doFinal(encrypted)
            } catch (_: AEADBadTagException) {
                // The first segment is the password check; a later failure means
                // the file is damaged or was tampered with after the first
                // segment was validated. Either way the caller applies nothing.
                throw if (index == 0L) {
                    WrongBackupPasswordException()
                } else {
                    InvalidBackupException("Backup file is damaged")
                }
            }
            position = 0
            index++
            finished = final
        }

        override fun close() = input.close()
    }
}
