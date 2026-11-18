- **2026-11-18 — The phone may approve the update card with its own fingerprint:**
  The owner asked that the phone be able to ask for the same desktop update the
  PC can already do, with the phone's own fingerprint. The decision is to keep
  ONE action (`desktop_update`, tier "ask", the same card, the same written
  words) and change only WHERE it may be confirmed: it left
  `jarvis_owner_check.PC_ONLY_ACTIONS`, exactly as `raise_api_limit` left it on
  2026-10-11 for the same owner's reason. Nothing about who confirms it was
  loosened - on the PC the card still asks Windows Hello (the action has no
  `_RISK` row, so the gate gives it the worst case and `is_risky` puts it at the
  prompt), and on the phone it needs that phone's signed approval, a fresh
  fingerprint or PIN over a one-use challenge, with `no_approval_key` refused in
  the existing words. A second action name was turned down: the old attempt's
  `update_jarvis` would have been a second name for an ability that already had
  one. What runs after the yes depends on where it was given - a PC approval
  still runs the desktop shell's own `update_both`; a phone approval cannot reach
  that command, so the backend runs `scripts/update-jarvis.ps1`, the repository's
  own both-halves updater, in a detached helper that holds the shared
  `update-in-progress.lock` so the two roads cannot patch the PC at once. This
  entry deliberately does not claim the phone screen: it is the next pull
  request, `docs/ARCHITECTURE.md` section 8 records it as one-sided on purpose
  for now, and `tools/check_parity.py` holds both routes `planned` with that
  slice named in `PENDING_CLIENTS`.
