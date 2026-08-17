# How to Programmatically Prune Invalid Dictionary Words

This scheme uses NYT Spelling Bee answers as an empirical validator for the submodule dictionary (`english-words/words_alpha.txt`). Words the generator produces that the NYT does *not* accept are treated as "fakes" and removed; official answers missing from the dictionary are added.

## Quick start

From the repo root:

```bash
# dry-run against today's puzzle
python3 -m prune.auto today --conservative

# apply once the summary looks right (backup is created by default here)
python3 -m prune.auto today --conservative --apply --yes
```

That single command fetches the official answers, generates local candidates, derives fakes, writes all three data files, and runs the pruner.

## Prerequisites

- **Dictionary** at `english-words/words_alpha.txt` (`git submodule update --init --recursive` if missing)
- **Data directory**: `prune/data/` holds `answers_*.txt`, `output_*.txt`, `fakes_*.txt`
- **Network access** to `https://www.nytimes.com/puzzles/spelling-bee` for the automated path
- Optional: system dictionary at `/usr/share/dict/words` for `--conservative`
- Only for the manual fallback path (§4/§5): `chmod +x prune/derive_fakes.sh prune/batch_prune.sh`

Date tokens throughout are 6 digits, `MMDDYY` (e.g. `072026`).

## 1) Automated — `prune/auto.py`

Run it as a module from the repo root so the `prune` package and `spelling_bee` both import cleanly:

```bash
python3 -m prune.auto [SELECTOR] [flags]
```

`SELECTOR` is `today` (default), `yesterday`, `MMDDYY`, or `YYYY-MM-DD`. Only the dates the NYT page exposes are reachable; see `--list` in §2.

What it does, in order:

1. Scrapes `window.gameData` from the puzzle page (or `--html FILE`)
2. Generates candidates with `spelling_bee.filter_words` (min length 4, center letter required)
3. Computes fakes (`candidates − answers`) and missing words (`answers − candidates`) in memory
4. Writes `answers_MMDDYY.txt`, `output_MMDDYY.txt`, `fakes_MMDDYY.txt` into the data dir
5. Prints a puzzle/comparison summary, then invokes `pruner.main()` in-process

Flags:

- `--data-dir DIR` — default `prune/data`
- `--dict PATH` — default `english-words/words_alpha.txt`
- `--html FILE` — parse a saved page instead of fetching (offline / reproducible runs)
- `--url URL` — override the puzzle URL
- `--force` — overwrite existing generated files whose contents differ (without it, a differing file raises `FileExistsError`; identical content is a no-op)
- `--show N` — preview size, default 25
- `--no-pruner` — generate files and the summary only, then print the pruner command to run next
- `--apply`, `--yes`, `--conservative`, `--no-add`, `--no-remove` — passed through to the pruner
- `--no-backup` — suppress the dictionary backup that `--apply` otherwise creates

Examples:

```bash
# inspect a specific date without touching the dictionary
python3 -m prune.auto 2026-07-20 --no-pruner

# re-run a day whose files already exist
python3 -m prune.auto 072026 --force --conservative

# apply without a backup (not recommended)
python3 -m prune.auto today --apply --yes --no-backup
```

Note: `--apply` with `--no-pruner` is rejected.

## 2) Fetch answers only — `prune/fetch_sb_answers.py`

Use this when you just want the official list, no candidate generation or pruning:

```bash
# list every puzzle date the page currently exposes
python3 prune/fetch_sb_answers.py --list

# write prune/data/answers_MMDDYY.txt
python3 prune/fetch_sb_answers.py today

# print to stdout instead (pipes into pruner --answers-stdin)
python3 prune/fetch_sb_answers.py yesterday --stdout
```

Also accepts `--data-dir`, `--html`, `--url`, and `--force`. Both this script and `auto.py` share `prune/extractor.py`, which holds the HTML parsing, the `Puzzle` dataclass (`date_token`, `letters_string`, `pangrams`, …), and the file writers.

## 3) Pruner reference — `prune/pruner.py`

Dry-run is the default; nothing is written without `--apply`.

**Input resolution.** Answers come from the first source given, in this order: `--answers-str` → `--answers-stdin` → `--answers/-a FILE` → `--date/-d` (reads `answers_MMDDYY.txt` from the data dir). Fakes come from `--output/-o` minus the answers (computed in memory), else `--fakes/-f FILE`, else `fakes_MMDDYY.txt` for `--date`.

| Flag | Alias | Meaning |
| --- | --- | --- |
| `--date` | `-d` | 6-digit token; resolves `answers_*.txt` / `fakes_*.txt` |
| `--data-dir` | `-D` | Where those files live (default: `prune/`, **not** `prune/data`) |
| `--fakes` | `-f` | Explicit fakes file |
| `--answers` | `-a` | Explicit answers file |
| `--output` | `-o` | Generator output; fakes derived in memory when answers are present |
| `--answers-str` | | Inline answers: JSON array, comma- or whitespace-separated |
| `--answers-stdin` | | Read answers from STDIN |
| `--dict` | | Dictionary to modify |
| `--system-dict` | `-s` | Cross-check list (default `/usr/share/dict/words`) |
| `--conservative` | `-c` | Only remove fakes absent from the system dictionary |
| `--no-add` | `-n` | Skip adding missing official answers |
| `--no-remove` | `-k` | Skip removing fakes |
| `--apply` | `-A` | Write changes (otherwise dry-run) |
| `--yes` | `-y` | Skip the confirmation prompt |
| `--backup` | `-B` | Create a `.bak-YYYYMMDD-HHMMSS` copy before writing |
| `--show` | `-S` | Preview count per category (default 20) |

**Backups are opt-in here.** `prune/auto.py` passes `--backup` for you unless you ask for `--no-backup`; calling `pruner.py` directly does not. Add `-B` yourself.

If `--conservative` is set but the system dictionary is missing, the pruner warns and proceeds *without* the safeguard.

Pasted-answer examples:

```bash
python3 prune/pruner.py --data-dir prune/data \
  --output prune/data/output_072026.txt \
  --answers-str '["civic","cede","edict","vice"]' --conservative

pbpaste | python3 prune/pruner.py --data-dir prune/data \
  --output prune/data/output_072026.txt --answers-stdin
```

Explicit-file example:

```bash
python3 prune/pruner.py --data-dir prune/data \
  --fakes prune/data/fakes_072026.txt \
  --answers prune/data/answers_072026.txt \
  --dict english-words/words_alpha.txt
```

Apply:

```bash
python3 prune/pruner.py --date 072026 --data-dir prune/data --apply -y -B
```

Writes atomically, reports counts added/removed and the new dictionary size.

## 4) Manual fallback (no network)

Useful when the NYT page is unreachable or its markup changes.

```bash
# a) generate candidates yourself (-o writes bare words; stdout adds a count header)
python3 spelling_bee.py vdeciut c -o prune/data/output_072026.txt

# b) supply the official answers
printf "%s\n" civic cede edict vice > prune/data/answers_072026.txt

# c) derive fakes = output − answers
./prune/derive_fakes.sh --data-dir prune/data 072026

# d) dry-run, then apply
python3 prune/pruner.py --date 072026 --data-dir prune/data --conservative
python3 prune/pruner.py --date 072026 --data-dir prune/data --conservative --apply -y -B
```

Step (c) is unnecessary if you pass `--output` plus any answers source — the pruner computes fakes in memory.

## 5) Batch mode across many days

Processes every date with both `answers_*.txt` and `output_*.txt` in the data dir:

```bash
./prune/batch_prune.sh --data-dir prune/data --conservative
./prune/batch_prune.sh --data-dir prune/data --dates 071926,072026 --regen-fakes --apply -y
```

It regenerates missing fakes via `derive_fakes.sh`, then calls `pruner.py` per date. It does **not** pass `--backup`, so back up the dictionary yourself before a batch `--apply`:

```bash
cp english-words/words_alpha.txt english-words/words_alpha.txt.bak-manual
```

## Notes and tips

- For a Spelling Bee–specific dictionary, omit `--conservative` so fakes are removed aggressively; include it to preserve proper nouns and broader English usage.
- Always read the dry-run summary before applying. A suspiciously large "REMOVE" count usually means the answers source was wrong or empty.
- Restore from the `.bak-YYYYMMDD-HHMMSS` file next to `words_alpha.txt` — but only if a backup was actually requested (see §3).
- The dictionary is a git submodule, so `git -C english-words diff --stat` and `git -C english-words checkout -- words_alpha.txt` are also available as review/undo tools.
- `prune/transform_text.py` turns a pasted answer block (e.g. from a spoiler site, with "pangram" markers) into a JSON array, pangrams first — feed it straight to `--answers-str`:

```bash
pbpaste | python3 prune/transform_text.py
```

- `prune/txt_to_array.py` is a scratch script with hardcoded paths that just lowercases a file; edit `src`/`dst` before use.
- Prefer `spelling_bee.py -o FILE` over shell redirection: stdout is prefixed with a `N words found:` header, which leaks into `output_*.txt` and then into `fakes_*.txt` via `derive_fakes.sh`. It is harmless (it never matches a dictionary entry, and `pruner.py --output` filters non-alphabetic lines) but it inflates counts.
