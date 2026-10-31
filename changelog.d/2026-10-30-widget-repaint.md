- **A home-screen Jarvis widget keeps showing the widget its slot was given (2026-10-30).** On the release
  APK the shrinker merged the seven widget classes into two, and Glance tells the cards apart by class
  name - so "Jarvis widget 2" kept reading "No widget chosen" after the owner picked a widget for it, and
  the approval, quick-link and calendar cards could each repaint with another's content. The build now
  keeps every widget class distinct (app/proguard-rules.pro carries the dexdump evidence and the
  field-test symptom), and a unit test fails if a keep rule is ever removed.
