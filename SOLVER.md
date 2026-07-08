# Automated Cryptogram solver (`extraction/solver.py`)

Drives the game over **adb** using an on-screen `uiautomator` dump. Because the
live puzzle layout (cipher numbers, pre-fills, locked boards) is generated at
runtime and does **not** match the baked `ul`/`pr`/`lp`/`dlp` data, the solver
reads the actual on-screen state instead of trusting the static files.

## What it reads from a dump
- **Grid tiles** — `content-desc` like `"E E 10"` gives each cell's solution
  letter and cipher number. Locked **board** tiles have an empty `content-desc`.
- **Keyboard** — single-letter tiles give each key's pixel location.
- It also **identifies the level** by matching visible letters against the
  decrypted quotes in `data/`, which recovers letters hidden under boards.

## How it solves
Solve by cipher group: for each distinct number, tap one tile of that number,
then tap the correct keyboard letter — the game fills every tile sharing that
number. Locked boards fill automatically as their neighbours resolve; the loop
re-dumps to pick up any that unlock, and scrolls to reach off-screen tiles.

## Requirements (run on the machine the phone is plugged into)
- `adb` on PATH, USB debugging enabled, device authorized (`adb devices`).
- Python 3. This repo checked out (needs `data/*_decrypted.json` for level id).
- Be on the puzzle screen in-game before running.

## Usage
```bash
# Offline sanity check against the bundled capture (no device needed):
python3 extraction/solver.py --dump-file tests/sample_dump.xml --plan

# Live DRY RUN — prints every tap it *would* send, touches nothing:
python3 extraction/solver.py --run

# Live for real — sends taps:
python3 extraction/solver.py --run --execute
```

Always run `--run` (dry run) first and eyeball the coordinates against your
screen. Then add `--execute`.

## Caveats / tuning
- **Coordinates are per-device.** The bundled capture is 1080×2316. The solver
  reads fresh bounds from each live dump, so resolution is handled automatically
  — but if your keyboard layout differs, the letter tiles are re-read each time.
- **Tap delays** (`time.sleep` in `adb_tap`/`adb_scroll`) may need raising on a
  slow device if letters get dropped.
- **Completion detection** is heuristic (stops when scrolling reveals no new
  cipher numbers a few times). Watch the first full solve.
- If a number's letter is unreadable in the dump (rare — e.g. a single-occurrence
  tile), the solver taps that tile directly with its own shown letter.
- Accessibility must be exposing the Flutter semantics tree. If a dump comes back
  nearly empty, enable a screen reader (e.g. TalkBack) briefly and re-dump.
