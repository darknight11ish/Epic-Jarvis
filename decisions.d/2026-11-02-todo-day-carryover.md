- **2026-11-02 — To-do day carry-over: BOTH modes, full daily rollover by
  default, and `created_date` is immutable:** The owner's answer, 2026-11-02
  ~00:41 PT, to the measured gap in the to-do list: *"To-do carry-over: build
  BOTH, with full daily rollover (option B) as the DEFAULT, changeable by asking
  Jarvis or in Settings."* He asked the question himself the same night - *is
  Jarvis smart enough that next day "what's on my to-do list today" brings up
  yesterday's unfinished items while saying they are from yesterday?* - and the
  measurement against `origin/main` said: yes, they carried over, but nothing
  said they were yesterday's, and the Today board's `rollover_cards` had never
  been built. Gemini's ruling 8 fixed the design: an **immutable `created_date`**
  (YYYY-MM-DD, the PC's local day) written once when an item is created and
  never rewritten - not at midnight, not by an edit, not by the mode switch -
  because a rollover that re-stamped items with "today" would erase the age it
  is meant to show; **dynamic tags measured from it** (1 day = "from
  yesterday", 2-6 days = "from <Weekday> (<N>d ago)", 7+ = "from <MMM D>"), so
  a 3-day-old item never says "from yesterday"; **full daily rollover as the
  default**; **a day-labelled mode as the alternative, switched in Settings on
  either app or by asking Jarvis**, lossless in both directions because no item
  moves; and a **migration** backfilling `created_date` from each row's
  `created`, or today for a legacy row with no usable stamp. This is NOT the
  already-documented `rollover_cards` plan for the Today board and does not
  build it: that needs a per-day completion record for a card, while this is the
  scheduler's to-do list, whose items carry their own day. Everything ends at
  ONE PC method (`jarvis_schedule.set_todo_mode_here`), so a tap and a sentence
  cannot disagree; no approval card either way, because it changes how the
  owner's own list is drawn and touches no row. Both apps draw it: the desktop's
  Brain "Coming up" card and its Settings card, and the phone's "Coming up"
  plate and its control under Limits (JARVIS-API §179). The same night's second
  half - the phone's UI text removals - is a separate decision, not this one.
