# Labelled facts for the topic sorter

`cases.jsonl` - one made-up fact per line, with the topic a person would file it
under (`null` = it belongs to no ready-made topic, so it is Unsorted). Written
for the self-test (`backend/eval_topics.py`) and for `tools/topic_accuracy.py`.
No data of the owner's. English, except the two health/money lines in Spanish
and French that the measured sensitive-topic lists (`jarvis_sensitive`) cover.

It is small on purpose and it is NOT a measure of how well REAL facts are sorted:
real facts are messier. Add your own lines (a line per fact) and run
`tools/topic_accuracy.py --extra your-file.jsonl` on the PC.
