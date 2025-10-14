# How to Programmatically Prune Invalid Dictionary Words (Automated)

This workflow uses NYT Spelling Bee outputs as an empirical validator for the submodule dictionary (`english-words/words_alpha.txt`). It automates deriving “fake” words and safely updating the dictionary.

## Prerequisites

- **Dictionary** at `english-words/words_alpha.txt`
- **Scripts executable**:
  
  ```bash
  chmod +x prune/derive_fakes.sh prune/batch_prune.sh
  ```
- **Data directory**: store daily files in `prune/data/`
  - `answers_*.txt`, `output_*.txt`, `fakes_*.txt`
- Optional: System dictionary at `/usr/share/dict/words` for conservative mode

## 1) Generate the day’s raw output

From repo root, write the generator output to `prune/data/`:

```bash
python3 spelling_bee.py vdeciut c > prune/data/output_080925.txt
```

Replace letters/center letter as appropriate; adjust the 6‑digit date token.

## 2) Provide the official answers

Option A — file (one per line, lowercase):

```bash
printf "%s\n" civic cede edict vice > prune/data/answers_080925.txt
```

Option B — paste directly (no answers file):

```bash
# JSON array
python3 prune/pruner.py --data-dir prune/data \
  --output prune/data/output_080925.txt \
  --answers-str '["civic","cede","edict","vice"]'

# comma/whitespace
python3 prune/pruner.py --data-dir prune/data \
  --output prune/data/output_080925.txt \
  --answers-str 'civic, cede, edict, vice'

# clipboard (macOS)
pbpaste | python3 prune/pruner.py --data-dir prune/data \
  --output prune/data/output_080925.txt --answers-stdin
```

## 3) Derive the day’s fake words (file-based)

If you have both `output_*.txt` and `answers_*.txt` files, compute fakes to `fakes_*.txt`:

```bash
./prune/derive_fakes.sh --data-dir prune/data 080925
```

This writes `prune/data/fakes_080925.txt`.

Note: When using pasted answers with `--output`, `pruner.py` can compute fakes in-memory (no `fakes_*.txt` needed).

## 4) Analyze (dry‑run by default)

`pruner.py` shows what it would add/remove without writing unless `--apply` is given.

```bash
# using date token (reads from prune/data/)
python3 prune/pruner.py --date 080925 --data-dir prune/data --conservative

# in-memory fakes from pasted answers and an output file
python3 prune/pruner.py --data-dir prune/data \
  --output prune/data/output_080925.txt \
  --answers-str 'civic, cede, edict, vice' \
  --conservative
```

- `--conservative` only removes words NOT in the system dictionary (helps avoid stripping proper nouns/common words). Omit to remove all fakes.
- Use `--show N` to change preview counts.

You can also run with explicit files:

```bash
python3 prune/pruner.py --data-dir prune/data \
  --bad prune/data/fakes_080925.txt \
  --true prune/data/answers_080925.txt \
  --dict english-words/words_alpha.txt
```

## 5) Apply changes safely

When satisfied with the dry‑run, apply:

```bash
python3 prune/pruner.py --date 080925 --data-dir prune/data --apply -y
# or with pasted answers
python3 prune/pruner.py --data-dir prune/data \
  --output prune/data/output_080925.txt \
  --answers-str 'civic, cede, edict, vice' \
  --apply -y
```

- Creates a timestamped backup next to `english-words/words_alpha.txt`
- Writes atomically to avoid partial writes
- Reports counts added/removed and new size

Additional useful flags:

- `--no-add` to skip adding missing true words
- `--no-remove` to skip removing fakes
- `--dict PATH` to target a different dictionary file
- `--system-dict PATH` to point at an alternate system dictionary

## 6) Batch mode across many days (optional)

Process multiple dates that have both `answers_*.txt` and `output_*.txt` in your data dir:

```bash
./prune/batch_prune.sh --data-dir prune/data --conservative
# restrict to certain dates and regenerate fakes
./prune/batch_prune.sh --data-dir prune/data --dates 072125,080925 --regen-fakes --apply -y
```

## Notes and tips

- If your primary goal is a Spelling Bee‑specific dictionary, omit `--conservative` so fakes are aggressively removed.
- If you want to preserve proper nouns or broader English usage, include `--conservative`.
- Always review the dry‑run summary before applying.
- Restore anytime from the created `.bak-YYYYMMDD-HHMMSS` backup next to `words_alpha.txt`.
