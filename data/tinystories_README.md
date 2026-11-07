# TinyStories data for Qasida

Source: roneneldan/TinyStories, train split, first 200 stories,
fetched 2026-10-26 via the Hugging Face
datasets-server rows API (no Kaggle, no account needed).

Cleaning: lowercase; apostrophes/quotes removed (don't -> dont);
every other non-letter becomes a space; split on whitespace.
Vocab: the 499 most frequent words, plus <unk>
(id 499) for everything else. Kept words: 24000.
UNK rate in the kept words: 0.148.

Files:
- tinystories_vocab.txt — one word per line, id = line number (0-based)
- tinystories_ids.txt — space-separated word ids in story order
