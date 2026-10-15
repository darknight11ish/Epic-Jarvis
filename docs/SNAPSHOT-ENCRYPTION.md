# The weekly snapshots are encrypted now, and the key is the thing to look after

**This is turned on. It was done on 2026-10-14, on your PC, and measured.**
Nothing here is a proposal or a plan.

Your personal data - 19 SQLite databases and about 1.6 MB, 604 rows the day this
was written - is snapshotted every Sunday at 03:00 by
`%LOCALAPPDATA%\JarvisDataBackup\jarvis_data_backup.py`. The snapshots were
**plain files on the disk**: anyone who took the drive, or copied your profile
folder, had your chat history, your memory, your schedule and your approvals in
readable form with no password at all.

They are now encrypted with **Windows EFS** (Encrypting File System - Windows'
own file encryption, built into the version of Windows you have). It is tied to
your Windows account rather than to a password you type, which is the whole
reason it was chosen: **the Sunday task keeps working untouched, with nobody
there to type anything.**

## What is encrypted, and what deliberately is not

Encrypted, and verified file by file:

* **`C:\Users\pcadmin\jarvis-data-snapshots`** - the folder the weekly task
  writes to. 230 paths, every one of them encrypted.
* **`C:\Users\pcadmin\Documents\Jarvis Backups`** - the folder you chose in
  Jarvis. 177 paths, every one encrypted. That includes the **four
  `.jbak` archives** from the older backup tool, and every snapshot folder
  inside it.

Deliberately **not** encrypted, and this is the important half of the list:

* **`C:\Users\pcadmin\.openjarvis`** - the live databases Jarvis is using right
  now. Encrypting these would put EFS in the path of the running app: every read
  and write, by every part of Jarvis and by any other tool that opens them. It
  is not needed for this job (the snapshots are the copy that leaves the
  machine's protection), and a problem there is a problem with the live data.
  The snapshots exist precisely so the live files can be left alone.
* **The program folders** - `%LOCALAPPDATA%\JarvisDataBackup`, the backend, the
  desktop app. They hold code, not your data.
* **Your whole profile, and the rest of `Documents`.** Only those two folders
  were touched. Nothing else on the disk changed.

The line is: **the copies that sit still get encrypted; the files being used
stay as they are.** An encrypted folder you are actively writing through is
where "the app cannot open its own database" stories come from.

## Why the obvious command was not enough

This is the trap, and it is why there is a checker next to this document.

`cipher /e <folder>` does **not** encrypt the files already in the folder. It
sets an attribute on the *folder* meaning "files written here from now on are
encrypted". Run that on its own and you get the worst of both: next Sunday's
snapshot is ciphertext, and every snapshot already there - including the `.jbak`
archives and last week's copy - is still plain on the disk. Nothing looks wrong.
The files open normally, the tool verifies them normally, and no screen anywhere
says "plain".

So each folder was done twice, second command first in effect:

```powershell
cipher /e "C:\Users\pcadmin\jarvis-data-snapshots" ; cipher /e /s:"C:\Users\pcadmin\jarvis-data-snapshots"
```

The first line is what makes **future** snapshots encrypted; the second, with
`/s`, reaches every file already inside. Both were run for both folders. The
same two lines, with the other path, did the chosen folder.

What `cipher` itself reported:

```
230 file(s) [or directorie(s)] within 22 directorie(s) were encrypted.   (jarvis-data-snapshots)
120 file(s) [or directorie(s)] within 12 directorie(s) were encrypted.   (Jarvis Backups)
```

And what an individual file says now - `E` means Encrypted, `U` would mean
plain:

```
C:\Users\pcadmin\jarvis-data-snapshots\jarvis-snap-20261014-001555\
New files added to this directory will be encrypted.

E manifest.json
```

## Proving it still works - because encrypted-and-unreadable is not a backup

Configuration that nobody re-ran is how this project has been burned before, so
the weekly run was rehearsed for real, with the environment cleared so it
behaved exactly as the Sunday task does. Both folders, in order:

| What was run | What came back |
| --- | --- |
| backup into `jarvis-data-snapshots` | OK - snapshot `jarvis-snap-20261014-001555`, 19 databases, 604 rows, 31 other files, verified |
| encryption of the **new** snapshot | 56 of 56 paths encrypted, 0 plain - written *after* the folder was flagged, so nothing in the backup tool needs to know about EFS |
| `verify` on the new snapshot | every one of the 19 databases opened and matched its manifest, 604 rows |
| `restore --to-temp` from it | restored, 604 rows in total across the same 19 databases, live data untouched |
| backup into `Jarvis Backups` | OK - snapshot `jarvis-snap-20261014-001624`, 19 databases, 604 rows |
| encryption of that folder afterwards | 177 of 177 paths encrypted, 0 plain, `.jbak` files included |

Two things there matter more than the rest:

* **The new snapshot came out encrypted on its own.** The backup tool was not
  changed, and does not need to be: the folder's attribute does the work. That
  is what keeps the unattended 03:00 run encrypted.
* **A restore from an encrypted snapshot really works.** SQLite opened the
  encrypted `chat-history.db`, `memory.db`, `schedule.db` and `approvals.db`
  directly and reported `integrity=ok`, then the tool's own restore counted the
  rows - **604**, the same number `verify` counted on the way in.

The scheduled task itself was then read back and is **unchanged**: `Jarvis
Personal Data Backup`, next run `10/18/2026 3:00:00 AM`, state `Ready`, running
as `pcadmin` through `pythonw.exe` with no administrator and no stored password.
Nothing about it needed to change for EFS, because EFS is tied to that same
account.

**And the backup tool's own suite still passes.** `backend/test_data_backup.py`
is not on `main` - it arrives with the pending backup pull request - so it was
run out of a scratch copy of that branch's `tools/jarvis_data_backup.py` and its
suite, with `JARVIS_BACKEND` and both config-dir variables cleared:
**73 passed, 0 skipped, 0 failed.** That includes its fixture-based proof that a
database whose newest rows are still only in the `-wal` is snapshotted whole,
that a truncated or table-losing snapshot is caught, that the tool never writes
into the folder it reads, and that **the tool contains no network call at all**
- checked by reading its own source. None of these invariants depends on the
snapshot being encrypted, and none changed.

## The key: this is the part that can lose your data

EFS encrypts each file with a random key, and then locks that key with a
certificate and private key belonging to your Windows account
(`CN=pcadmin`, valid until 2126). Files encrypted that way can be read by your
account and by nothing else - not by another account on this PC, not by you
after a Windows reinstall, not by a repair shop, not by Microsoft.

**Lose the Windows profile, or reinstall Windows, without exporting that key
first, and the snapshots are not locked - they are gone.** There is no password
to guess and no reset. That is the honest cost of encryption that runs by itself
with nobody to type a passphrase, and it is worth paying, but only if the key is
kept somewhere else.

**Run this yourself, and choose your own password when it asks.** The password
is not printed anywhere and this assistant did not choose one - a password that
has been through a chat window is not a secret.

```powershell
$pw = Read-Host "New password for the key file" -AsSecureString ; Export-PfxCertificate -Cert Cert:\CurrentUser\My\22A53F1F46CD7134C6888458290A983A8AC2C8EF -FilePath "$env:USERPROFILE\Desktop\pcadmin-efs-key.pfx" -Password $pw
```

One line, ready to paste. It asks once for a password (nothing appears as you
type, and it is not stored anywhere), then writes the key file. **Run it
yourself, and choose your own password** - a password that has been through a
chat window is not a secret, and this assistant did not choose one for you.

* **Where the file lands:** your **Desktop**, as `pcadmin-efs-key.pfx`. The full
  path is printed on screen as well.
* **Then move it off this PC.** A password manager entry (attach the file), or a
  USB key you keep somewhere else. **A key stored beside the backup protects
  nothing** - if the drive is stolen, both halves are in the same bag, and if the
  profile dies, so does the key that could have recovered it.
* **`.pfx` holding a private key is written as a normal file** - it is not
  itself encrypted beyond the password you just chose. Delete the Desktop copy
  once it is safely stored elsewhere.
* Windows' own equivalent, if you would rather use the built-in menu: run
  `cipher /x "%USERPROFILE%\Desktop\pcadmin-efs-key.pfx"` in a terminal and type
  the password twice in the window that appears. (`cipher /x` writes the file
  the moment you press Enter and then waits in a small dialog for the password -
  so in a script with no screen to answer it, it looks like it hung. The
  PowerShell line above has no such trap.)

**What exported is enough to recover.** The `.pfx` is the certificate *and* its
private key together, password-protected. On a new Windows install you import it
(`Import-PfxCertificate -FilePath <the .pfx> -CertStoreLocation Cert:\CurrentUser\My`)
**before** trying to open any snapshot, and the files open normally again. Losing
the password on the `.pfx` is the same as losing the key.

### A second account that can decrypt: not worth it here

EFS can have a **recovery agent** - a second certificate that can open every
encrypted file, normally set up by an organisation's policy. It is worth having
where a helpdesk gets locked out of employees' files.

**For a one-person PC it is a second copy of the same secret on the same
machine**, which is exactly the thing that makes a backup useless. It does not
help with the case that actually threatens these snapshots (drive lost,
Windows reinstalled), because the recovery key would sit on the same disk. If
the profile is lost, a recovery agent stored on that profile is lost with it.
The export above, kept off the PC, is the answer to that case, and it is the
recommendation. **Not set up, on purpose.**

## A folder you pick next month will NOT be encrypted by itself

EFS is a property of a folder. Nothing in Jarvis sets it.

* `C:\Users\pcadmin\jarvis-data-snapshots` stays encrypted for every future
  snapshot, forever, with no further action - the folder is flagged.
* `C:\Users\pcadmin\Documents\Jarvis Backups` is the same.
* **A third folder you choose later starts out plain, and nothing will warn
  you.** Snapshots would be written into it unencrypted and every check in the
  backup tool would still pass, because the backup is fine - it is just not
  encrypted.

The honest answer is that this cannot be fixed from here: the code that would
have to set the attribute at run time (`tools/jarvis_data_backup.py`) is being
changed by three other pieces of work at once, and a change to it made blind
from here would collide with all three. So it is written down instead, with a
one-liner. **When you point Jarvis at a new folder, run this once, with that
folder's path in place of the example:**

```powershell
cipher /e "D:\Jarvis Backups" ; cipher /e /s:"D:\Jarvis Backups"
```

The first command flags the folder so everything written into it afterwards is
encrypted; the second encrypts anything already there. Then check it:

```powershell
python -B tools\check_snapshots_encrypted.py --dest "D:\Jarvis Backups"
```

That checker is in this repository and is the thing to trust here: it reads the
EFS attribute of the folder and of every file and subfolder inside it, and fails
naming the plain ones. Run it with no arguments and it checks both folders
above. Its `--self-test` proves the reader itself on a real temporary folder, so
"it says encrypted" is a measurement rather than a habit.

## What EFS does not protect against

Say this plainly, because a security note that only lists wins is a lie:

* **Anyone using your Windows account.** EFS decrypts transparently for you -
  that is why the 03:00 task works. Someone at your unlocked PC, or anything
  running as you, reads these files exactly as before.
* **A copy taken while you are logged in.** Cryptography cannot help there.
* **The key file, if you keep it on this PC.** Then the drive that holds the
  snapshots holds the way to open them, and the encryption has bought nothing
  against a stolen disk.
* **`cipher /w` was not run, and on this PC it should not be run casually.** Windows
  warned that converting a file leaves pieces of the old plaintext in free space,
  and that is true here: the snapshots were plain for weeks before this change, so
  a forensic tool could still find fragments of them in unallocated space. The
  cleanup command is `cipher /w:C:`, and what it actually costs on this machine is
  measured: **C: has 118.2 GB free, and that command overwrites all of it three
  times** (zeroes, then ones, then random). That is hours of continuous disk
  activity during which the PC is not usable for much, and it is a much bigger
  action than the two small folders it would be cleaning up after (6.3 MB and
  20.6 MB of data). It is written down as **not done, deliberately** - start it
  yourself, when you can leave the machine alone, if the disk-leaving-the-house
  case is one you care about that much. Encryption protects everything written
  from now on either way; this only clears the past.

## The one-paragraph version

The two snapshot folders are encrypted, every file already in them and every
file written from now on. The weekly Sunday 03:00 task and the backup tool are
unchanged and both were re-run to prove it, up to a full restore with the same
604 rows. Nothing outside those two folders was touched - not the live databases
in `~/.openjarvis`, not the program folders. **Now export the key to your
Desktop with the command above, choose your own password, and put the file
somewhere that is not this PC.** Until you do that, the snapshots are encrypted
against a thief and hostage to a dead profile at the same time.
