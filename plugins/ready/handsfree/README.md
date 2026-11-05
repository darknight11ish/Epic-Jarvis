# handsfree

**Hands-free mode** (the owner's own request of 2026-11-04: *"a handfree
setting that i can turn off in chat, jarvis live, or through settings. in this
mode any approval card for a task i ask jarvis to do will automatically be read
out and i can answer confirm or deny (including verbally) and it will approve
the card. i want jarvis to be able to write text messages to contacts for me in
particular among the full fledged handsfree mode"*).

**Drop-in.** Copy this folder into the backend's `jarvis_plugins\` folder (or
run `scripts\add-plugin.ps1 -Name handsfree`) and restart Jarvis. The module it
names ships with this repository (`backend/jarvis_handsfree.py`), copied into
the backend by `scripts/apply-patches.ps1`; this folder adds no patch and
changes no `jarvis_hud.py` line. The gate rows it needs (`send_text_message`,
`handsfree_enable`) come from `backend/handsfree.patch`, which *is* applied to
`jarvis_gate.py` - a drop-in module cannot add a `_RISK` row, and without one
the gate would treat a text message as unclassified (still "ask", but with the
generic worst-case words instead of its own).

## The routes

```
GET  /api/handsfree          is it on, the window, the vocabulary, the phone
POST /api/handsfree          {"enabled": true|false} - ON is ONE card, OFF is instant
POST /api/handsfree/answer   {"card_id", "data_b64", "sample_rate"} - one spoken answer
POST /api/phone/result       {"id", "ok", "receipt", "why"} - the phone's own word
```

All go through the core's own origin + token checks (`X-Jarvis-Client` and
`X-Jarvis-Token`), then the module's own handler. Every other request reaches
the original handler untouched, and the Windows Hello check on
`/api/approve` is unchanged: this module never calls it.

## What it does NOT do

- It never approves anything bulk, never clears a rush latch and never touches
  a second card from one answer.
- It does not weaken the non-hands-free path. With the mode off, `answer()`
  refuses before it transcribes; nothing else in the tree calls `approve_one`.
- It stores no phone number and no contact. The phone's own contact list turns
  a name into a number.
- It does not claim a text was sent. The tool says "asked your phone"; only
  the phone's `POST /api/phone/result` produces a receipt.

The frozen contract is `docs/JARVIS-API.md` section 186, and the owner's
decision that a voice yes counts is
`decisions.d/2026-11-04-handsfree-voice-approval.md`.
