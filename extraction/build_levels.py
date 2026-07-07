#!/usr/bin/env python3
"""Build per-level puzzle tables with the starting reveal state.

For each level we emit:
  level            - level id (int for the main set, date string for dailies)
  quote            - the solution with ONLY letters and spaces (punctuation,
                     quotes, author, etc. stripped), original casing kept
  num_letters      - count of letter cells (spaces don't count)
  num_revealed     - how many cells start pre-filled
  revealed_positions - 1-indexed letter positions that start revealed (the
                     game's `pr` field; per-cell, spaces skipped)
  mask             - string of '1'(revealed)/'0'(hidden), length num_letters
  start_board      - the quote with hidden letters shown as '_' (spaces kept)

Outputs, per decrypted dataset, a .csv and a .jsonl in data/levels/.
The `pr` field is authored per level (deterministic), not randomized.
"""
import os, json, csv, glob, re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "levels")

def clean_quote(q):
    """Keep letters and word spaces only; punctuation is removed outright
    (so "don't" -> "dont"), original word breaks preserved."""
    s = "".join(ch if (ch.isalpha() or ch.isspace()) else "" for ch in q)
    return re.sub(r"\s+", " ", s).strip()

APOS = set("'’`")

def _letter_positions_revealed(rec, n_letters):
    """Map the game's `pr` cell indices to 1-based letter-only positions.

    Almost every level indexes `pr` over letter cells only. A handful of daily
    puzzles (with apostrophes) index over letters+apostrophes instead, which we
    detect by an out-of-range index and handle by remapping onto letter cells.
    Returns (revealed_letter_positions, clipped_count).
    """
    pr = sorted(int(x) for x in rec["pr"].split("_")) if rec.get("pr") else []
    if not pr:
        return [], 0
    if max(pr) <= n_letters:                      # letters-only indexing (the norm)
        return [p for p in pr if 1 <= p <= n_letters], 0
    # apostrophe-inclusive indexing: build cell list, keep only letter cells
    cells = [("L" if ch.isalpha() else "P")
             for ch in rec["q"] if ch.isalpha() or ch in APOS]
    letter_rank = {}                              # cell index (1-based) -> letter rank
    rank = 0
    for i, t in enumerate(cells, 1):
        if t == "L":
            rank += 1
            letter_rank[i] = rank
    out, clipped = [], 0
    for p in pr:
        if p in letter_rank:
            out.append(letter_rank[p])
        else:
            clipped += 1                          # pr pointed at a non-letter cell
    return sorted(out), clipped

def build_record(level, rec):
    quote = clean_quote(rec["q"])
    n = sum(1 for ch in quote if ch.isalpha())
    revealed, clipped = _letter_positions_revealed(rec, n)
    rset = set(revealed)
    mask = "".join("1" if (k + 1) in rset else "0" for k in range(n))
    board = []
    lc = 0
    for ch in quote:
        if ch.isalpha():
            lc += 1
            board.append(ch if lc in rset else "_")
        else:
            board.append(ch)
    return {
        "level": level,
        "quote": quote,
        "num_letters": n,
        "num_revealed": len(revealed),
        "revealed_positions": revealed,
        "mask": mask,
        "start_board": "".join(board),
    }

def process(path):
    d = json.load(open(path))
    name = os.path.basename(path).replace("_decrypted.json", "")
    os.makedirs(OUT, exist_ok=True)
    recs = []
    # sort numerically when possible
    def keyf(k):
        return (0, int(k)) if k.isdigit() else (1, k)
    for lvl in sorted(d.keys(), key=keyf):
        recs.append(build_record(lvl, d[lvl]))
    with open(os.path.join(OUT, name + "_levels.jsonl"), "w") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, name + "_levels.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["level", "quote", "num_letters", "num_revealed",
                    "revealed_positions", "mask", "start_board"])
        for r in recs:
            w.writerow([r["level"], r["quote"], r["num_letters"], r["num_revealed"],
                        "_".join(map(str, r["revealed_positions"])),
                        r["mask"], r["start_board"]])
    return name, len(recs)

if __name__ == "__main__":
    for p in sorted(glob.glob(os.path.join(DATA, "*_decrypted.json"))):
        if "_es" in p:   # keep language variants too, but label them
            pass
        name, n = process(p)
        print(f"{n:>5} levels  ->  data/levels/{name}_levels.{{csv,jsonl}}")
