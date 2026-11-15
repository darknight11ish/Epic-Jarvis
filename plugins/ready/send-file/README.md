# send-file

**Send one file from the PC to the phone** (the owner's ask of 2026-10-31:
*"am i able to ask jarvis to search for a file for me and send it to the
jarvis android app to view and or download directly?"*; Gemini ruling Q7).

**Drop-in.** Copy this folder into the backend's `jarvis_plugins\` folder (or
run `scripts\add-plugin.ps1 -Name send-file`) and restart Jarvis. The module it
names ships with this repository (`backend/jarvis_send_file.py`), copied into the
backend by `scripts/apply-patches.ps1`; this folder adds no patch and changes no
`jarvis_hud.py` line.

## The routes

```
GET /api/files/send                 approved files waiting for the phone (no path)
GET /api/files/download?id=<id>     one 1 MiB piece of the bytes, by opaque id (no path parameter)
POST /api/files/prepare             the desktop button's route: one path the owner picked himself
POST /api/files/ack                 the phone's receipt: the whole file arrived, so consume the id
```

All four go through the core's own origin + token checks (`X-Jarvis-Client` and
the pairing token), exactly like `/api/protection` and `/api/pictures/file`; the
module adds no new auth scheme. The button's route also refuses a request that
says it comes from the phone, because only the desktop dialog may name a path.
The receipt is the phone's, and a repeat receipt is answered "already finished"
rather than as an error.

## The one card

The model tool `send_file_to_phone` searches the "Folders Jarvis may look in"
list (minus anything the optional Protected from Jarvis check refuses), picks
ONE match, and raises ONE card - `send_file_to_phone`, tier "ask" - whose words
show the exact filename, the folder and the byte size. Nothing is fetchable
until that card is approved. The desktop's "Send a file to your phone…" button
raises the same card for the one file the owner picked in the dialog.

## The named limits

- one file per card, up to 2 GB (2,147,483,648 bytes); over it is refused in
  words, never truncated;
- the link lasts 10 minutes from the last piece served, and one completed
  download uses it up - a piece before the last may be retried;
- at most 8 ids in memory, cleared on restart;
- only inside the "Folders Jarvis may look in" allow-list, unless the owner
  picked the file himself in the desktop button's dialog.

The phone's View / Save to Downloads UI (`FileProvider`, `ACTION_VIEW`,
`MediaStore.Downloads`) is the phone lane's work; this folder only makes the
bytes reachable by an approved id.
