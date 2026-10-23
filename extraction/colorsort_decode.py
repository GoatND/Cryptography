#!/usr/bin/env python3
"""Decode Color Sort (com.zm.watersort) level TextAssets.

Each level TextAsset is a text file with one base64 line per level. Each line is a
MemoryPack-serialized `LevelData` object (schema recovered from the IL2CPP metadata
with Cpp2IL, see FINDINGS-colorsort.md). This script decodes every *_Binary.bytes file
in an input directory to JSON and a flat CSV.

Usage: colorsort_decode.py <dir with *.bytes> <output dir>
"""
import base64, csv, json, os, struct, sys


class Reader:
    def __init__(self, b):
        self.b = b
        self.p = 0

    def u8(self):
        v = self.b[self.p]; self.p += 1; return v

    def i32(self):
        v = struct.unpack_from('<i', self.b, self.p)[0]; self.p += 4; return v

    def boolean(self):
        return self.u8() != 0

    def string(self):
        h = self.i32()
        if h == -1:
            return None
        if h >= 0:                       # UTF-16 encoded
            s = self.b[self.p:self.p + h * 2].decode('utf-16-le'); self.p += h * 2; return s
        n = ~h                           # UTF-8 encoded: ~utf8ByteCount, then utf16 length
        self.i32()
        s = self.b[self.p:self.p + n].decode('utf-8'); self.p += n; return s

    def int_list(self):
        n = self.i32()
        if n == -1:
            return None
        return [self.i32() for _ in range(n)]

    def bool_array(self):
        n = self.i32()
        if n == -1:
            return None
        v = [x != 0 for x in self.b[self.p:self.p + n]]; self.p += n; return v

    def obj_list(self, fn):
        n = self.i32()
        if n == -1:
            return None
        return [fn() for _ in range(n)]

    def members(self, fields):
        """Object header: member count byte (0xFF = null). Fields = [(name, reader)]."""
        n = self.u8()
        if n == 0xFF:
            return None
        if n > len(fields):
            raise ValueError(f'object has {n} members but only {len(fields)} known')
        out = {}
        for name, fn in fields[:n]:
            out[name] = fn()
        for name, _ in fields[n:]:
            out[name] = None   # absent in this (older) schema version
        return out


def flask_segment(r):
    return r.members([
        ('colorId', r.i32),
        ('size', r.i32),
        ('isSegmentPartsHidden', r.bool_array),
        ('hiddenCount', r.i32),
        ('id', r.i32),
    ])


def lock_by_position(r):
    # Current schema has two ints (x, y). The legacy locked_by_position_levels file was
    # written by an older build whose class had four int members; the shipped game code
    # (MemoryPack "Object" mode, non version-tolerant) cannot read that file any more.
    return r.members([('x', r.i32), ('y', r.i32), ('legacy_m2', r.i32), ('legacy_m3', r.i32)])


def flask_data(r):
    return r.members([
        ('segments', lambda: r.obj_list(lambda: flask_segment(r))),
        ('maxSegmentsCount', r.i32),
        ('hiddenSegmentsCount', r.i32),
        ('lockByColor', r.i32),
        ('receiveOnly', r.boolean),
        ('isLockedByNeighbors', r.boolean),
        ('hiddenItemIndexes', r.int_list),
        ('receiveOnlyColorId', r.i32),
        ('lockByPosition', lambda: lock_by_position(r)),
        ('needFill', r.boolean),
    ])


LEVEL_TYPE = {0: 'Default', 1: 'Secret'}
RULE_SET = {0: 'Standard', 1: 'IndependentColors'}


def level_data(r):
    d = r.members([
        ('Flasks', lambda: r.obj_list(lambda: flask_data(r))),
        ('FirstMovesHint', lambda: r.obj_list(lambda: flask_segment(r))),
        ('DifficultyCategory', r.i32),
        ('InternalId', r.i32),
        ('Layout', r.i32),
        ('Hash', r.string),
        ('LevelType', r.i32),
        ('RuleSet', r.i32),
        ('LayoutId', r.string),
    ])
    d['LevelTypeName'] = LEVEL_TYPE.get(d['LevelType'])
    d['RuleSetName'] = RULE_SET.get(d['RuleSet'])
    return d


def decode_line(line):
    b = base64.b64decode(line)
    r = Reader(b)
    d = level_data(r)
    if r.p != len(b):
        raise ValueError(f'trailing bytes: consumed {r.p} of {len(b)}')
    return d


def flask_summary(f):
    """Compact text: segments in file order, 'colorId' or 'colorId*size' if size>1,
    '?' marks a segment with any hidden parts, '+' = empty slots. Flags appended."""
    parts = []
    for s in f['segments'] or []:
        t = str(s['colorId'])
        if s['size'] and s['size'] != 1:
            t += f"*{s['size']}"
        if s['isSegmentPartsHidden'] and any(s['isSegmentPartsHidden']):
            t += '?'
        parts.append(t)
    txt = ','.join(parts) if parts else '-'
    flags = []
    if f['lockByColor'] not in (None, -1): flags.append(f"lockColor={f['lockByColor']}")
    if f['receiveOnly']: flags.append('receiveOnly')
    if f['receiveOnlyColorId'] not in (None, -1): flags.append(f"receiveColor={f['receiveOnlyColorId']}")
    if f['isLockedByNeighbors']: flags.append('lockedByNeighbors')
    if f['hiddenItemIndexes']: flags.append(f"hidden={f['hiddenItemIndexes']}")
    if f['lockByPosition']: flags.append(f"lockPos=({f['lockByPosition']['x']},{f['lockByPosition']['y']})")
    if f['needFill']: flags.append('needFill')
    if f['maxSegmentsCount'] is not None:
        txt += f"/{f['maxSegmentsCount']}"
    if flags:
        txt += '[' + ' '.join(flags) + ']'
    return txt


def main(src, out):
    os.makedirs(out, exist_ok=True)
    summary = []
    for fn in sorted(os.listdir(src)):
        if not fn.endswith('.bytes'):
            continue
        name = fn[:-6]
        lines = [l for l in open(os.path.join(src, fn), 'rb').read().split(b'\n') if l.strip()]
        levels, errors = [], 0
        for i, line in enumerate(lines):
            try:
                d = decode_line(line); d['index'] = i; levels.append(d)
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f'  {name} line {i}: {e}', file=sys.stderr)
        safe = name.replace(' ', '_')
        json.dump(levels, open(os.path.join(out, safe + '.json'), 'w'), indent=1)
        with open(os.path.join(out, safe + '.csv'), 'w', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['index', 'internal_id', 'difficulty', 'layout', 'layout_id', 'level_type',
                        'rule_set', 'num_flasks', 'num_empty_flasks', 'num_colors', 'flask_capacity',
                        'flasks', 'first_moves_hint', 'hash'])
            for d in levels:
                flasks = d['Flasks'] or []
                colors = {s['colorId'] for f in flasks for s in (f['segments'] or [])}
                caps = sorted({f['maxSegmentsCount'] for f in flasks})
                hint = ','.join(str(s['colorId']) for s in (d['FirstMovesHint'] or []))
                w.writerow([d['index'], d['InternalId'], d['DifficultyCategory'], d['Layout'],
                            d['LayoutId'] or '', d['LevelTypeName'], d['RuleSetName'], len(flasks),
                            sum(1 for f in flasks if not f['segments']), len(colors),
                            '/'.join(map(str, caps)), ' | '.join(flask_summary(f) for f in flasks),
                            hint, d['Hash']])
        summary.append((name, len(lines), len(levels), errors))
        print(f'{name}: {len(levels)}/{len(lines)} levels decoded, {errors} errors')
    return summary


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
