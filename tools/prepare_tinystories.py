#!/usr/bin/env python3
"""Prepare TinyStories for Qasida word-level training.

Downloads the first N stories of roneneldan/TinyStories (train
split) through the Hugging Face datasets-server rows API — the
same API route this workspace already uses for HF dataset rows
(see AGENTS.md) — cleans them, and writes three files:

  data/tinystories_vocab.txt  one word per line; the last line
                              is <unk> (id = vocab_size - 1)
  data/tinystories_ids.txt    space-separated word ids
  data/tinystories_README.md  provenance + cleaning rules

Cleaning (documented, so the Qasida side can be audited):
  * lowercase everything (TinyStories sentence-case is dropped;
    a 200-word vocab cannot afford two cases of every word)
  * apostrophes and quotes are removed, so don't -> dont
  * every other non-letter becomes a space, then split on
    whitespace (so punctuation never becomes a token)
  * vocab = the 199 most frequent words in the fetched stories,
    plus <unk> for everything else

Usage:
    python3 tools/prepare_tinystories.py --stories 200
    python3 tools/prepare_tinystories.py --stories 200 --max-words 24000
"""

import argparse
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

API = ("https://datasets-server.huggingface.co/rows"
       "?dataset=roneneldan%2FTinyStories&config=default"
       "&split=train&offset={offset}&length={length}")


def fetch_stories(n):
    stories = []
    offset = 0
    while len(stories) < n:
        length = min(100, n - len(stories))
        url = API.format(offset=offset, length=length)
        req = urllib.request.Request(url, headers={"User-Agent": "qasida/0.4"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
        rows = data.get("rows", [])
        if not rows:
            break
        for row in rows:
            stories.append(row["row"]["text"])
        offset += len(rows)
    return stories


def clean(text):
    text = text.lower().replace("'", "").replace('"', "")
    text = re.sub(r"[^a-z]+", " ", text)
    return text.split()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stories", type=int, default=200)
    ap.add_argument("--max-words", type=int, default=24000)
    ap.add_argument("--vocab-size", type=int, default=200)
    ap.add_argument("--out-dir", default="data",
                    help="output directory under the repo root (default: data)")
    args = ap.parse_args()

    stories = fetch_stories(args.stories)
    all_words = []
    for s in stories:
        all_words.extend(clean(s))
    print(f"fetched {len(stories)} stories, {len(all_words)} words total")

    counts = Counter(all_words)
    top = [w for w, _ in counts.most_common(args.vocab_size - 1)]
    vocab = top + ["<unk>"]
    index = {w: i for i, w in enumerate(vocab)}
    unk_id = args.vocab_size - 1
    words = all_words[: args.max_words]
    ids = [index.get(w, unk_id) for w in words]
    unk_rate = sum(1 for i in ids if i == unk_id) / max(1, len(ids))
    print(f"vocab: {len(vocab)} (top word: {top[0]!r})")
    print(f"kept {len(ids)} words, UNK rate: {unk_rate:.3f}")

    root = Path(__file__).resolve().parent.parent
    out = root / args.out_dir
    out.mkdir(exist_ok=True)
    (out / "tinystories_vocab.txt").write_text("\n".join(vocab) + "\n", encoding="utf-8")
    (out / "tinystories_ids.txt").write_text(" ".join(str(i) for i in ids), encoding="utf-8")
    readme = f"""# TinyStories data for Qasida

Source: roneneldan/TinyStories, train split, first {len(stories)} stories,
fetched {__import__('datetime').date.today().isoformat()} via the Hugging Face
datasets-server rows API (no Kaggle, no account needed).

Cleaning: lowercase; apostrophes/quotes removed (don't -> dont);
every other non-letter becomes a space; split on whitespace.
Vocab: the {args.vocab_size - 1} most frequent words, plus <unk>
(id {unk_id}) for everything else. Kept words: {len(ids)}.
UNK rate in the kept words: {unk_rate:.3f}.

Files:
- tinystories_vocab.txt — one word per line, id = line number (0-based)
- tinystories_ids.txt — space-separated word ids in story order
"""
    (out / "tinystories_README.md").write_text(readme, encoding="utf-8")
    print(f"wrote {out / 'tinystories_vocab.txt'} and {out / 'tinystories_ids.txt'}")


if __name__ == "__main__":
    main()
