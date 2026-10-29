- **2026-10-28 — One approval card, and an expired one is dead on every
  screen:** the owner ruled that *"the cards on android should match the cards
  on desktop"*, and the audit found the two disagreed in three ways that matter.
  (1) **The defect.** The phone has drawn no buttons on an expired card since
  DEF-010 (2026-10-11, measured on his own phone); the Jarvis bar, the widget
  and the HUD page still drew live Approve and Deny on the same card, so a
  request the gate had already refused by itself could be pressed on the PC and
  not on the phone - two apps enforcing two different rules about the same
  deadline. Decided: **an expired card is not decidable on any surface**, and
  hiding the buttons is only the drawing - `decideApproval`, the widget's
  `decide` and the page's `apprDecide` refuse it too, because a hidden button is
  not a refusal. The gate is unchanged: it still answers the card by itself at
  the deadline, exactly as `approval-expiry.patch` and
  `no-expiry-cards.patch` already did. (2) **The words.** The phone said
  "Timed out — ask the desktop to raise this again." and the PC said "Timed out:
  Jarvis stopped waiting and refused it by itself." for the same event. Decided:
  the FACT is `jarvis_card_words.TIMED_OUT`, one sentence drawn by both apps; the
  phone's "ask the desktop to raise this again" stays as `TIMED_OUT_NEXT`, its
  own second sentence, because on the PC the owner is already in front of the
  window that raises cards - a written rule, not an oversight, so it is recorded
  in `docs/ARCHITECTURE.md` §8 rather than quietly kept. (3) **The stale copy.**
  `desktop_update` joined `jarvis_owner_check.PC_ONLY_ACTIONS` on 2026-10-26 and
  the phone's own `PcOnlyActions` did not, so the phone offered an Approve the PC
  refuses; the set is now generated into `contract/card-words-cases.json` from
  that module, which both apps' tests read, so the next PC-only action fails a
  required CI job instead of a tap. What this deliberately does NOT do: no card
  is approved, denied or bulk-decided anywhere, no route or permission changes,
  the phone still may not approve a PC-only card, and the phone's `/api/pending`
  shape is untouched (no backend patch is edited). What it does not settle:
  the desktop's own "start short / Explain more" fold - still `desktop-todo` in
  `tools/check_parity.py`, and the work it needs is
  `docs/DESKTOP-APPROVAL-CARD-PREF.md`'s.
