#!/usr/bin/env python3
"""Find callers of IL2CPP methods by scanning every ARM64 `bl` in libil2cpp.so.

Usage: il2cpp_xrefs.py <libil2cpp.so> <cpp2il DiffableCs dir> <Type.Method | 0xoffset> ...
Prints each call site with the containing managed method (from Cpp2IL's [Address] map).
"""
import bisect, sys
import numpy as np
sys.path.insert(0, __import__('os').path.dirname(__file__))
from il2cpp_disasm import build_map

so, root, *targets = sys.argv[1:]
B = open(so, 'rb').read()
M = build_map(root)
starts = sorted(M)
byname = {}
for off, (k, ln) in M.items():
    byname.setdefault(k, []).append(off)
w = np.frombuffer(B[:len(B) & ~3], dtype='<u4')
is_bl = (w >> 26) == 0x25
idx = np.nonzero(is_bl)[0]
imm = (w[idx] & 0x3FFFFFF).astype(np.int64)
imm = np.where(imm & 0x2000000, imm - 0x4000000, imm)
src = idx.astype(np.int64) * 4
dst = src + imm * 4
order = np.argsort(dst)
dst_sorted = dst[order]

def owner(a):
    i = bisect.bisect_right(starts, a) - 1
    if i >= 0 and a < starts[i] + M[starts[i]][1]:
        return M[starts[i]][0]
    return '?'

for t in targets:
    offs = [int(t, 16)] if t.startswith('0x') else byname.get(t, [])
    for off in offs:
        lo = np.searchsorted(dst_sorted, off, 'left'); hi = np.searchsorted(dst_sorted, off, 'right')
        callers = src[order[lo:hi]]
        print(f'== {t} @ 0x{off:X}: {len(callers)} call sites')
        seen = {}
        for s in callers:
            o = owner(int(s)); seen.setdefault(o, []).append(int(s))
        for o, ss in sorted(seen.items()):
            print(f'   {o}  ' + ' '.join(f'0x{s:X}' for s in ss[:4]))
