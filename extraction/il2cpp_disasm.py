#!/usr/bin/env python3
"""Annotated ARM64 disassembly of IL2CPP methods using Cpp2IL's [Address] attributes.

Usage:
  il2cpp_disasm.py <libil2cpp.so> <cpp2il DiffableCs dir> list  <TypeName>
  il2cpp_disasm.py <libil2cpp.so> <cpp2il DiffableCs dir> dis   <TypeName.Method | 0xoffset[:len]> ...
Call targets (bl/b) are resolved to managed method names; file offsets are used as
addresses (Cpp2IL's RVA == file offset for this binary's text segment).
"""
import os, re, sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

ADDR = re.compile(r'\[Address\(RVA = "0x([0-9A-Fa-f]+)", Offset = "0x[0-9A-Fa-f]+", Length = "0x([0-9A-Fa-f]+)"\)\]')
SIG = re.compile(r'^\s*(?:\[[^\]]*\]\s*)*(?:public|private|protected|internal|static|override|virtual|abstract|readonly|sealed|\s)*[\w<>\[\]`,.&]+\s+([\w<>.`]+)\s*\(')


def build_map(root):
    methods = {}  # offset -> (Type.Method, length)
    for dp, _, fs in os.walk(root):
        for f in fs:
            if not f.endswith('.cs'):
                continue
            path = os.path.join(dp, f)
            tname = f[:-3]
            lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
            for i, l in enumerate(lines):
                m = ADDR.search(l)
                if not m:
                    continue
                off, ln = int(m.group(1), 16), int(m.group(2), 16)
                name = None
                for j in range(i + 1, min(i + 6, len(lines))):
                    s = lines[j].strip()
                    if s.startswith('['):
                        continue
                    if s in ('get { }', 'set { }') or s.startswith(('get {', 'set {')):
                        # property accessor: find property name above
                        for k in range(i - 1, max(i - 8, 0), -1):
                            pm = re.match(r'^\s*(?:[\w<>\[\]`,.]+\s+)+([\w<>`]+)\s*$', lines[k])
                            if pm:
                                name = ('get_' if s.startswith('get') else 'set_') + pm.group(1); break
                        break
                    sm = SIG.match(s)
                    if sm:
                        name = sm.group(1); break
                    break
                key = f'{tname}.{name or "?"}'
                if off not in methods or methods[off][1] < ln:
                    methods[off] = (key, ln)
    return methods


def main():
    so, root, cmd, *args = sys.argv[1:]
    B = open(so, 'rb').read()
    M = build_map(root)
    byname = {}
    for off, (k, ln) in M.items():
        byname.setdefault(k, []).append((off, ln))
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    if cmd == 'list':
        t = args[0]
        rows = sorted((off, k, ln) for off, (k, ln) in M.items() if k.startswith(t + '.'))
        for off, k, ln in rows:
            print(f'0x{off:X} len 0x{ln:X} {k}')
        return
    for a in args:
        if a.startswith('0x'):
            off, ln = (int(x, 16) for x in (a.split(':') + ['0x200'])[:2]) if ':' in a else (int(a, 16), 0x200)
            name = M.get(off, ('?', 0))[0]
        else:
            cands = byname.get(a)
            if not cands:
                print(f'# {a}: not found'); continue
            off, ln = max(cands, key=lambda x: x[1]); name = a
        print(f'===== {name} @ 0x{off:X} len 0x{ln:X} =====')
        for i in md.disasm(B[off:off + ln], off):
            note = ''
            if i.mnemonic in ('bl', 'b') and i.op_str.startswith('#0x'):
                tgt = int(i.op_str[1:], 16)
                if tgt in M:
                    note = f'    ; -> {M[tgt][0]}'
            print(f'  {i.address:08x}  {i.mnemonic:8s} {i.op_str}{note}')


if __name__ == '__main__':
    main()
