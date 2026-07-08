#!/usr/bin/env python3
"""Automated solver for the Cryptogram game (in.playsimple.cryptogram) via adb.

How it works
------------
1. Capture a uiautomator dump of the puzzle screen. Each grid tile exposes its
   solution + cipher number in `content-desc` as "<L> <L> <N>" (e.g. "E E 10");
   locked "board" tiles have an empty content-desc; the on-screen keyboard
   exposes single-letter tiles with their pixel bounds.
2. Build the cipher map number->letter from the readable tiles, and (optionally)
   identify the exact level by matching the visible letters against the
   decrypted quote set in data/ — which yields the full answer including the
   letters hidden under boards.
3. Solve by cipher group: for each distinct number, tap one visible tile of that
   number then tap the correct keyboard letter (the game fills every tile with
   that number). Scroll + re-dump to reach off-screen tiles and to pick up
   "board" tiles once they unlock.

adb runs on YOUR machine (where the phone is attached), so run this there.
Default is a dry run — it prints the tap plan without touching the device.

    python3 solver.py --dump-file tests/sample_dump.xml --plan   # offline test
    python3 solver.py --run                                       # live dry-run
    python3 solver.py --run --execute                             # live, taps!
"""
import sys, os, re, time, json, glob, argparse, subprocess
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
CELL_RE = re.compile(r"^([A-Za-z])\s+([A-Za-z])\s+(\S+)$")
KEYS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


# ----------------------------------------------------------------------------- parsing
class Cell:
    __slots__ = ("x1", "y1", "x2", "y2", "kind", "letter", "number")

    def __init__(self, b, kind, letter=None, number=None):
        self.x1, self.y1, self.x2, self.y2 = b
        self.kind, self.letter, self.number = kind, letter, number  # kind: letter|board|punct

    @property
    def cx(self): return (self.x1 + self.x2) // 2
    @property
    def cy(self): return (self.y1 + self.y2) // 2


def _bounds(s):
    m = BOUNDS_RE.match(s or "")
    return tuple(map(int, m.groups())) if m else None


def parse_dump(xml_str):
    """Return (cells_in_reading_order, keyboard{letter:(x,y)}, scroll_bounds)."""
    root = ET.fromstring(xml_str)
    nodes = [(n, _bounds(n.get("bounds"))) for n in root.iter("node")]
    nodes = [(n, b) for n, b in nodes if b and b[2] > b[0] and b[3] > b[1]]

    # keyboard = single-letter tiles (take the lowest-on-screen match per letter)
    keyboard = {}
    for n, b in nodes:
        cd = (n.get("content-desc") or "").strip()
        if len(cd) == 1 and cd.upper() in KEYS:
            c = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
            if cd.upper() not in keyboard or c[1] > keyboard[cd.upper()][1]:
                keyboard[cd.upper()] = c

    # grid = clickable leaf Views inside the ScrollView
    scroll = next((b for n, b in nodes if "ScrollView" in (n.get("class") or "")), None)
    cells, seen = [], set()
    for n, b in nodes:
        if (n.get("class") or "") != "android.view.View":
            continue
        if scroll and not (b[0] >= scroll[0] - 5 and b[3] <= scroll[3] + 120
                           and b[1] >= scroll[1] - 5):
            continue
        if b in seen:                      # real boards nest a duplicate child node
            continue
        w = b[2] - b[0]
        cd = (n.get("content-desc") or "").strip()
        m = CELL_RE.match(cd)
        if m:
            num = int(m.group(3)) if m.group(3).isdigit() else None
            cells.append(Cell(b, "letter", m.group(1).upper(), num)); seen.add(b)
        elif cd == "" and n.get("clickable") == "true" and 40 <= w <= 100:
            cells.append(Cell(b, "board")); seen.add(b)            # tile-sized only
        elif len(cd) == 1 and not cd.isalnum() and w < 40:
            cells.append(Cell(b, "punct", cd)); seen.add(b)
    return order_cells(cells), keyboard, scroll


def order_cells(cells):
    """Sort tiles into reading order (rows top→bottom, tiles left→right)."""
    if not cells:
        return []
    cells = sorted(cells, key=lambda c: (c.y1, c.x1))
    rows, cur, y0 = [], [], cells[0].y1
    for c in cells:
        if abs(c.y1 - y0) > 60:          # new row
            rows.append(sorted(cur, key=lambda c: c.x1)); cur, y0 = [], c.y1
        cur.append(c)
    rows.append(sorted(cur, key=lambda c: c.x1))
    return [c for row in rows for c in row]


# ----------------------------------------------------------------------------- level id
def _norm(q):
    return "".join(ch.upper() for ch in q if ch.isalpha())


def load_quotes():
    quotes = {}
    for p in glob.glob(os.path.join(DATA, "*_decrypted.json")):
        if "_es" in p or "var1" in p:      # var1 duplicates the main set → skip
            continue
        for lvl, rec in json.load(open(p)).items():
            quotes[(os.path.basename(p), lvl)] = _norm(rec["q"])
    return quotes


def identify(cells, quotes):
    """Match the visible letters (boards = wildcard) to a known quote prefix."""
    seq = [c for c in cells if c.kind in ("letter", "board")]
    pat = "".join(c.letter if c.kind == "letter" else "." for c in seq)
    if not pat:
        return None, None, {}
    rx = re.compile(pat)
    hits = [(k, q) for k, q in quotes.items() if rx.match(q)]
    if len(hits) != 1:
        return None, None, {}
    (filelvl, quote) = hits[0]
    # map each ordered letter/board cell to its solved letter
    solved = {id(c): quote[i] for i, c in enumerate(seq) if i < len(quote)}
    return filelvl, quote, solved


# ----------------------------------------------------------------------------- planning
def cipher_map(cells, solved):
    """number -> letter, learned from readable tiles (and solved board letters)."""
    m = {}
    for c in cells:
        if c.kind == "letter" and c.number is not None:
            m[c.number] = c.letter
    return m


def plan(cells, keyboard, solved):
    """Yield (why, tapcell(x,y), key(x,y)) actions to fill the visible board."""
    num2let = cipher_map(cells, solved)
    actions, seen_numbers = [], set()
    for c in cells:
        if c.kind == "letter" and c.number is not None:
            if c.number in seen_numbers:
                continue
            seen_numbers.add(c.number)
            letter = num2let[c.number]
            if letter in keyboard:
                actions.append((f"#{c.number}->{letter}", (c.cx, c.cy), keyboard[letter]))
        elif c.kind == "letter" and c.number is None:
            # number unreadable (e.g. single-occurrence tile) -> tap it directly
            if c.letter in keyboard:
                actions.append((f"{c.letter}(direct)", (c.cx, c.cy), keyboard[c.letter]))
        elif c.kind == "board":
            letter = solved.get(id(c))
            if letter and letter in keyboard:
                # locked now; will be tappable after neighbours fill. queue as direct tap.
                actions.append((f"board->{letter}", (c.cx, c.cy), keyboard[letter]))
    return actions


# ----------------------------------------------------------------------------- adb
def adb(*args, timeout=20):
    return subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)


def adb_dump():
    adb("shell", "uiautomator", "dump", "/sdcard/ps_dump.xml")
    return adb("shell", "cat", "/sdcard/ps_dump.xml").stdout


def adb_tap(x, y, execute):
    print(f"    tap ({x},{y})")
    if execute:
        adb("shell", "input", "tap", str(x), str(y))
        time.sleep(0.28)


def adb_scroll(scroll, execute):
    x = (scroll[0] + scroll[2]) // 2
    y1, y2 = int(scroll[1] + (scroll[3] - scroll[1]) * 0.75), int(scroll[1] + (scroll[3] - scroll[1]) * 0.25)
    print(f"    scroll up {x},{y1}->{x},{y2}")
    if execute:
        adb("shell", "input", "swipe", str(x), str(y1), str(x), str(y2), "400")
        time.sleep(0.6)


def run_live(execute):
    quotes = load_quotes()
    keyboard, applied, stagnant = {}, set(), 0
    while True:
        cells, kb, scroll = parse_dump(adb_dump())
        keyboard = kb or keyboard                      # keyboard is fixed; keep first good read
        filelvl, quote, solved = identify(cells, quotes)
        if filelvl:
            print(f"  level: {filelvl[1]} ({filelvl[0]})  quote: {quote[:48]}...")
        num2let = cipher_map(cells, solved)
        todo = [c for c in cells if c.kind == "letter" and c.number is not None
                and c.number not in applied and num2let.get(c.number) in keyboard]
        if todo:
            for c in {x.number: x for x in todo}.values():   # one rep per number
                letter = num2let[c.number]
                print(f"  fill #{c.number} -> {letter}")
                adb_tap(c.cx, c.cy, execute); adb_tap(*keyboard[letter], execute)
                applied.add(c.number)
            stagnant = 0
        else:
            if scroll:
                adb_scroll(scroll, execute)
            stagnant += 1
        if stagnant >= 3:
            print("  no new tiles after scrolling — assuming solved / stuck.")
            break


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump-file", help="parse a saved uiautomator xml instead of a device")
    ap.add_argument("--plan", action="store_true", help="print the tap plan and exit")
    ap.add_argument("--run", action="store_true", help="solve on a live adb device")
    ap.add_argument("--execute", action="store_true", help="actually send taps (else dry run)")
    a = ap.parse_args()

    if a.dump_file:
        cells, keyboard, scroll = parse_dump(open(a.dump_file).read())
        quotes = load_quotes()
        filelvl, quote, solved = identify(cells, quotes)
        print(f"tiles: {sum(c.kind=='letter' for c in cells)} letters, "
              f"{sum(c.kind=='board' for c in cells)} boards, "
              f"{sum(c.kind=='punct' for c in cells)} punct; keyboard keys: {len(keyboard)}")
        if filelvl:
            print(f"identified level {filelvl[1]} in {filelvl[0]}")
            print(f"  quote: {json.load(open(os.path.join(DATA, filelvl[0])))[filelvl[1]]['q']}")
        print(f"cipher map (number->letter): {dict(sorted(cipher_map(cells, solved).items()))}")
        boards = [ (i+1, solved.get(id(c))) for i,c in enumerate(c for c in cells if c.kind in('letter','board')) if c.kind=='board']
        print(f"board (locked) letter-positions: {boards}")
        if a.plan:
            print("\ntap plan:")
            for why, tapc, key in plan(cells, keyboard, solved):
                print(f"  {why:14s} tap tile {tapc} then key {key}")
        return
    if a.run:
        run_live(a.execute)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
