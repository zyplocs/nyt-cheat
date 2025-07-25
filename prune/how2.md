# How to Programmatically Prune Invalid Dictionary Words

## 1 Capture the `spelling_bee.py` Output

```bash
python spelling_bee.py vdeciut c > output_123456.txt
```

Adjust the arguments to match the day's letters. Replace the numbers in the `output` raw text file with the puzzle's date in M-D-Y format.

## 2 Save and Write the Answer Array

```python
answers = ["civic", "cede", "edict", "vice"]
with open("answers_123456.txt", "w") as f:
    print(*answers, sep="\n", file=f)
```

## 3 Derive the "Bad" Words

```bash
comm -23 \
  <(sort output_123456.txt) \
  <(sort answers_123456.txt) \
  > fakes_123456.txt
```

## 4 Edit the File Dates in `pruner.py` and Run

```bash
python pruner.py
```
