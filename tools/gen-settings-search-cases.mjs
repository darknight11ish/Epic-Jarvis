// Derive the shared cross-app fixture from the DESKTOP engine, which is the
// verified half (PR #350, 15/15 passing). Generated from behaviour rather than
// written by hand, so the phone is held to what the desktop actually does.
import { rank, fuzzyBudget } from '../jarvis-desktop/src/settings-search.js';
import { writeFileSync } from 'node:fs';

/** label, text - both as the page would hand them over. */
const PARTS = {
  voice: ['Voice', 'Whether Jarvis knows your voice, how strict that check is, and the voice Jarvis answers in.'],
  idleNew: ['A new conversation starts after', 'How long a chat can sit idle before the next message starts a new one.'],
  notifications: ['Notifications from Jarvis', 'Android decides whether this phone shows what Jarvis sends from your PC.'],
  folders: ['Folders Jarvis may look in', 'Which folders Jarvis may read. Obsidian, Logseq and Joplin notes.'],
  mail: ['Sending email', 'Send an email, drafts, recipients and replies.'],
  appearance: ['Appearance', 'Theme, colours, the face and how it all looks.'],
  search: ['Search settings', 'Type a word to show only the settings that match.'],
  // THE SUBSTRING TRAP, added because the first version of this fixture could
  // not catch it. The phone's floor used to be `word.contains(token)`, so a
  // short token matched INSIDE a longer unrelated body word. The original
  // fixture put "conversation" in a LABEL, where the heading rule handles it,
  // and had no case with a long word in the BODY - so it would have stayed
  // green with that bug present. This part puts the long words where the body
  // floor reads them.
  bodySubstring: [
    'Sending email',
    'The conversation and the catalogue of drafts are both kept on your PC.',
  ],
};

const QUERIES = [
  'voice', 'voise', 'notifcation', 'notification', 'folders', 'folder',
  'email', 'emial', 'appearance', 'apearance', 'search', 'settings',
  'voice strict', 'voice backup', 'wi fi', 'cat', 'chat', 'conversation',
  'obsidian', 'theme', 'zzzz', 'docket', 'rocket',
  // The substring class: 'cat' is INSIDE "catalogue" and 'voice' is not in
  // "conversation" at all; 'conversation' is a whole body word. A body floor
  // that is whole-word gives cat->[], voice->[], conversation->[bodySubstring].
  'cat', 'voice', 'conversation', 'catalogue', 'draft',
];

const cases = [];
for (const q of QUERIES) {
  const ranks = {};
  for (const [key, [label, text]] of Object.entries(PARTS)) ranks[key] = rank(label, text, q);
  const hits = Object.entries(ranks).filter(([, r]) => r > 0).map(([k]) => k).sort();
  cases.push({ query: q, hits, ranks });
}

const out = {
  _comment: [
    'SHARED cross-app fixture for Settings search. Generated from the desktop',
    'engine (jarvis-desktop/src/settings-search.js) by tools/gen-settings-search-cases.mjs.',
    'BOTH apps must satisfy every case: the desktop suite and the Kotlin',
    'SettingsSearchTest each read this file. Regenerate with that script rather',
    'than editing by hand, so the two engines cannot drift on the fuzzy rules.',
    '',
    '`hits` lists the part keys the query must match, in sorted order.',
    '`ranks` is the desktop tier per part. The tier NUMBERS are desktop-only:',
    'the phone returns 2 for a heading-only match and 1 for a body match, and',
    'that is fine because neither app orders results by the number - both only',
    'ask whether it is above zero. Match `hits`; do not match `ranks` exactly.',
  ],
  parts: Object.fromEntries(Object.entries(PARTS).map(([k, [label, text]]) => [k, { label, text }])),
  budget: { 3: fuzzyBudget('abc'), 4: fuzzyBudget('abcd'), 7: fuzzyBudget('abcdefg'), 8: fuzzyBudget('abcdefgh') },
  cases,
};

writeFileSync('jarvis-desktop/tests/fixtures/settings-search-cases.json', JSON.stringify(out, null, 2) + '\n');
console.log('wrote', cases.length, 'cases');
for (const c of cases) console.log('  ' + c.query.padEnd(14) + ' -> ' + (c.hits.join(',') || '(none)'));
