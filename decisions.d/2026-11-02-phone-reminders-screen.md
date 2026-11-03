- **2026-11-02 — The phone's Reminders screen is a screen of its own, with the
  daily to-do list inside it:** The owner's ask, verbatim: *"I want a custom
  reminders screen on the jarvis Android app. right now when I open it it just
  takes me to a subsection of the brain that has reminders. I also want another
  option within the reminders that includes a daily to-do list"*. It replaces the
  destination Home's Reminders button gained earlier the same day (Brain ->
  Coming up); the button now opens `Screen.REMINDERS`, and the Brain plate is
  unchanged and still reachable, still never hideable. The shape is TWO choices
  on one screen rather than a second Home button or a new menu id: **Reminders**
  (the same rows, from the same `GET /api/schedule` read, drawn by the same
  composables) and **Daily to-do list** (the scheduler's to-do list, showing both
  of the PC's ways of carrying it over - daily rollover and day by day - with the
  PC's own age tags and day headings, and the same cardless `todo_mode` write the
  Settings card uses). It deliberately does NOT add a route, a backend file, a
  contract, a permission, an approval card or a bulk action: every write is one
  job per tap through the scheduler's existing doors, held on a stale link, and
  the named lists ("shopping") with their single "Clear list" stay in Brain ->
  Coming up because a second copy of that surface would be a second place to
  delete a whole list from. The desktop keeps its own HUD Reminders tab and no
  desktop surface changed, so this is a phone-only navigation change, not a
  parity gap. The named lists being drawn only by the Brain plate is a deliberate
  surface split, recorded in `docs/ARCHITECTURE.md` section 8.
