- **2026-11-02 — Speak capability answers in Jarvis Live:** The owner's
  answer, 2026-11-02: *"Yes, speak capability answers (Recommended)"* - asked
  because Live already speaks web, weather, screen and camera answers, but a
  feature-list answer still said "It's on your screen."; it matches what he
  said on 2026-11-01: *"it will say 'it's on your screen' when it'd clearly
  capable of reading the info out loud"*. Decided: a spoken Live answer the
  model wrote from `feature_guide` - Jarvis's own shipped feature list and its
  own on/off switch reads, never the owner's data, no card, and in
  `jarvis_agent._NOT_READING` because it reads no outside text - may be read
  aloud. This supersedes the list restriction of 2026-09-27 **only for this
  one read-only tool**, which said: *"Answers that used web search, weather or
  home status are read aloud when read-aloud would otherwise apply. Answers
  that used email, calendar, notes, documents, memory, or any tool not on that
  short list stay on screen, and every earlier rule (sensitive facts, the
  stricter hands-free choice) still comes first. This replaces 'any tool keeps
  the answer on screen'."* (`docs/DECISIONS.md:396-401`). Every sensitive tool
  keeps its old behaviour: email, calendar, notes, documents, files, memory and
  any tool not on the list still keep the answer on screen, and the seven
  refusals in the reference rule (`may_read`,
  `tools/gen_private_aloud_cases.py:159-181`) are unchanged - a sensitive saved
  fact without permission, a screen read without `screen_aloud`, a private
  question, the router's private gate, remembered facts with memory kept on
  screen, a private tool that ran, and an event stream that is not live each
  still keep the answer on screen. Read-only and one name: no tool is added, no
  other tool's answer changes, and the shared table both apps run (103 cases,
  `private-aloud-cases.json`) is regenerated from the one list in
  `tools/gen_private_aloud_cases.py`.
