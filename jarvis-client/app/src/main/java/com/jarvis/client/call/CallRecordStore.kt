package com.jarvis.client.call

import java.io.File
import java.io.RandomAccessFile

/**
 * A call recording that is SAFE ON DISK BEFORE IT IS SENT.
 *
 * The owner's requirement: a dropped connection must lose nothing. So the
 * pieces are written to this app's own files directory first, and only then
 * uploaded; the file is the record, not the socket. If the PC is asleep, the
 * call happens on a train, or the app is killed mid-call, everything already
 * cut is still here and the next start of the service picks it up.
 *
 * THE SHAPE ON DISK - one directory per call recording, all of it this app's
 * private storage:
 *
 * ```
 * files/call-record/call-1762375299123/      <- the local id (call start, ms)
 *     meta.txt        started_at=<iso861>   (written once, before any audio)
 *                     pc_session=<id>       (added the first time `start` answers)
 *     chunk-000001.pcm, chunk-000002.pcm .. exactly as cut, PCM16LE mono 16 kHz
 *     sent.txt        one seq per line, appended AFTER the PC acknowledged it
 *     finished.txt    note=<path or pending>  (the PC took the whole recording)
 * ```
 *
 * WHY THERE IS NO SEPARATE INDEX FILE. The chunk files ARE the index: their
 * numbers are the sequence, and `sent.txt` is the only thing that has to be
 * written twice-ish. A crash can therefore lose at most the one chunk being
 * written (which is renamed into place only when complete, so an interrupted
 * write leaves a `.part` file that is ignored and overwritten), and can never
 * leave an index that names a chunk which is not there.
 *
 * WHY `sent.txt` IS APPENDED, NOT REWRITTEN. Appending one short line is
 * cheap and cannot corrupt the earlier lines; a rewritten index could be
 * truncated by a kill halfway through and would then re-upload or skip
 * arbitrarily. A repeated seq after a crash (the line was lost) is safe: the
 * frozen contract says to retry the same seq, and the PC appends in seq order.
 *
 * Pure JVM: `java.io` only, no Android types, no DataStore, no Room. The
 * whole class is exercised by `CallRecordQueueTest` on a temporary folder.
 */
class CallRecordStore(private val root: File) {

    /** One call recording's own folder. */
    inner class Session internal constructor(val dir: File) {

        /** The local id, which is the folder's name. */
        val id: String = dir.name

        /** When the call started, in milliseconds since the epoch (the id carries it). */
        val startedAtMs: Long = id.removePrefix(PREFIX).toLongOrNull() ?: dir.lastModified()

        /** The PC's own session id, once `POST .../start` has answered. */
        var pcSession: String? = null
            private set

        /** What the PC said about the finished recording (`note`), once it took it. */
        var note: String? = null
            private set

        // ------------------------------------------------------------ meta ---

        private fun metaFile(): File = File(dir, META)

        private fun readMeta(): Map<String, String> {
            val f = metaFile()
            if (!f.isFile) return emptyMap()
            return runCatching {
                f.readLines().mapNotNull { line ->
                    val at = line.indexOf('=')
                    if (at <= 0) null else line.substring(0, at) to line.substring(at + 1)
                }.toMap()
            }.getOrDefault(emptyMap())
        }

        /** Read what an earlier run of the app wrote. Called once, when the session is opened. */
        fun load() {
            val meta = readMeta()
            pcSession = meta[KEY_PC_SESSION]?.takeIf { it.isNotBlank() }
            note = if (File(dir, FINISHED).isFile) meta[KEY_NOTE] else null
        }

        fun saveMeta(extra: Map<String, String> = emptyMap()) {
            val all = LinkedHashMap<String, String>()
            all[KEY_STARTED_AT] = readMeta()[KEY_STARTED_AT]
                ?: CallRecordRules.startedAt(startedAtMs)
            pcSession?.let { all[KEY_PC_SESSION] = it }
            note?.let { all[KEY_NOTE] = it }
            all.putAll(extra)
            runCatching {
                val tmp = File(dir, "$META.part")
                tmp.writeText(all.entries.joinToString("") { "${it.key}=${it.value}\n" })
                // A rename over an EXISTING file is not portable (`renameTo`
                // fails on Windows), and this file is rewritten whenever the
                // PC's session id or the note arrives. Delete first, so the
                // write works on every filesystem the app is built on.
                if (!tmp.renameTo(metaFile())) {
                    metaFile().delete()
                    tmp.renameTo(metaFile())
                }
            }
        }

        /** Remember the PC's session id, so a restart resumes the same recording. */
        fun setPcSession(session: String) {
            pcSession = session
            saveMeta()
        }

        /** The PC has taken the whole recording: `note` is what it said (`pending` when it has none yet). */
        fun markFinished(note: String?) {
            this.note = note.orEmpty()
            runCatching { File(dir, FINISHED).writeText(this.note.orEmpty()) }
            saveMeta()
        }

        /** Has the PC taken the whole thing? A finished session is safe to delete. */
        fun finished(): Boolean = File(dir, FINISHED).isFile

        // ---------------------------------------------------------- chunks ---

        /** Every chunk on disk, in `seq` order, by the number in its name. */
        fun chunks(): List<Chunk> {
            val names = dir.list() ?: return emptyList()
            return names.mapNotNull { name ->
                if (!name.startsWith(CHUNK) || !name.endsWith(EXT)) return@mapNotNull null
                val seq = name.removePrefix(CHUNK).removeSuffix(EXT).toIntOrNull() ?: return@mapNotNull null
                val file = File(dir, name)
                Chunk(seq, file, file.length())
            }.sortedBy { it.seq }
        }

        private fun nextSeq(): Int = (chunks().lastOrNull()?.seq ?: 0) + 1

        /**
         * Write one chunk and return its sequence number (1, 2, 3 ...).
         *
         * Written to `.part` and renamed into place, so a chunk that was cut
         * short by a kill is never mistaken for audio. Throws nothing: -1
         * means the disk refused it, and the caller says so rather than
         * pretending the audio is safe.
         */
        fun writeChunk(pcm: ByteArray): Int {
            if (pcm.isEmpty()) return -1
            val seq = nextSeq()
            return runCatching {
                val tmp = File(dir, chunkName(seq) + EXT_PART)
                RandomAccessFile(tmp, "rw").use { out ->
                    out.setLength(0)
                    out.write(pcm)
                    out.fd.sync()
                }
                if (!tmp.renameTo(File(dir, chunkName(seq) + EXT))) {
                    tmp.delete()
                    return -1
                }
                seq
            }.getOrDefault(-1)
        }

        /** The first chunk the PC has not acknowledged, or null when it has them all. */
        fun nextUnsent(): Chunk? {
            val sent = sentSeqs()
            return chunks().firstOrNull { it.seq !in sent }
        }

        /** Which chunks the PC has acknowledged. Read every time, so a crash mid-write cannot mislead it. */
        fun sentSeqs(): Set<Int> {
            val f = File(dir, SENT)
            if (!f.isFile) return emptySet()
            return runCatching {
                f.readLines().mapNotNull { it.trim().toIntOrNull() }.toSet()
            }.getOrDefault(emptySet())
        }

        /** The PC has this chunk: APPEND its number, and lose nothing if the append is cut short. */
        fun markSent(seq: Int) {
            runCatching {
                RandomAccessFile(File(dir, SENT), "rw").use { out ->
                    out.seek(out.length())
                    out.write((seq.toString() + "\n").toByteArray())
                }
            }
        }

        /** How much audio is on disk for this recording. */
        fun bytes(): Long = chunks().sumOf { it.bytes }

        /** The whole seconds this recording would report to `finish`. */
        fun durationSec(): Long = CallRecordRules.durationSec(bytes())

        /** Is there anything at all worth sending? */
        fun hasAudio(): Boolean = chunks().isNotEmpty()

        /** Everything the PC has not taken yet. Only ever called after `finished()` is false. */
        fun remove() {
            runCatching { dir.deleteRecursively() }
        }
    }

    /** One chunk on disk: its sequence, its file, and how many bytes it holds. */
    data class Chunk(val seq: Int, val file: File, val bytes: Long) {
        fun read(): ByteArray = file.readBytes()
    }

    // ------------------------------------------------------------ sessions ---

    private fun dirs(): List<File> =
        root.listFiles()?.filter { it.isDirectory && it.name.startsWith(PREFIX) }.orEmpty()

    /** Every call recording on this phone, oldest first. */
    fun sessions(): List<Session> = dirs().sortedBy { it.name }.map { open(it) }

    private fun open(dir: File): Session = Session(dir).also { it.load() }

    /**
     * Start a new call recording's folder. The audio begins going to disk at
     * once, before any network call, so an unreachable PC cannot cost a
     * recording (the `start` is sent as soon as it can be).
     */
    fun begin(startedAtMs: Long): Session {
        var dir = File(root, PREFIX + startedAtMs)
        // Two calls inside the same millisecond cannot happen (a call is
        // seconds long), but a stale folder with that name can after a clock
        // change: never write into it.
        var bump = 1
        while (dir.exists()) {
            dir = File(root, PREFIX + startedAtMs + "-" + bump)
            bump++
        }
        dir.mkdirs()
        return open(dir).also { it.saveMeta() }
    }

    /** The newest recording the PC has not taken, if any - what a restart resumes. */
    fun unfinished(): Session? = sessions().lastOrNull { !it.finished() }

    /** Everything still to send, oldest first. */
    fun unsent(): List<Session> = sessions().filter { !it.finished() }

    companion object {
        /** The folder's name for one recording: `call-<start ms>`. */
        const val PREFIX = "call-"

        private const val META = "meta.txt"
        private const val SENT = "sent.txt"
        private const val FINISHED = "finished.txt"
        private const val CHUNK = "chunk-"
        private const val EXT = ".pcm"
        private const val EXT_PART = ".pcm.part"
        private const val KEY_STARTED_AT = "started_at"
        private const val KEY_PC_SESSION = "pc_session"
        private const val KEY_NOTE = "note"

        private fun chunkName(seq: Int): String = CHUNK + seq.toString().padStart(6, '0')

        /** The store's own folder inside this app's files directory. */
        fun folder(filesDir: File): File = File(filesDir, "call-record")
    }
}
