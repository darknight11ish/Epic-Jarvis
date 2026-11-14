- **2026-11-13 — A forget-a-time-frame card carries the count, not every chat:**
  Asked what should happen when Jarvis wants to delete a lot at once, the owner
  ruled: "Show the count, allow it." So the CARD carries the count of facts and
  chats with the date range ("3 facts and 125 chats from 2 to 8 November 2026")
  and the facts' own words while they fit, and the checked list the owner ticked
  from - one click away, unchanged - carries every item in full. This overrules
  the older rule that a card had to list every item in full, and the reason is
  measured, not stylistic: `jarvis_gate` keeps a card's detail as
  `json.dumps(detail)[:4000]`, the HUD disables Approve for a detail that long
  that no longer parses, and the owner's own 125-chat card sat at exactly 4,000
  characters of invalid JSON and expired un-approvable (measured 2026-11-13: 25
  chats fitted at 3,918 characters, 30 took 4,448, and 125 took 14,546). The
  approval itself is unchanged - still a person's yes behind the normal gate,
  Windows Hello on the PC and the screen lock on the phone, still the second yes
  and the 10-minute Undo, still no item cap. A card that would STILL be cut is
  refused before it is raised, in one plain sentence, using
  `jarvis_agent._card_would_be_cut`'s own rule imported from its owner; the
  gate's 4,000 cap and the HUD's cut-off rule are deliberately not loosened -
  they stay the last line of defence.
