#!/usr/bin/env python3
"""Decrypt the Cryptogram game's level data and emit clean JSON + CSV.

The encrypted fields (`q` = quote, `a` = author, `sa` = source) are base64 of
an **XXTEA**-encrypted UTF-8 string (data & key little-endian, 16-byte key).
The key was recovered from the Flutter Dart snapshot (libapp.so):

    Key.fromUtf8('xK#9pL@2mN!5vQ8r')

`ul` (letter -> cipher number) and `pr` (letter positions) are already
cleartext in the source files. This script decrypts the text fields and
writes decrypted JSON alongside a flat CSV of quote/author/source.

Usage:  python3 decrypt.py            # decrypts every data/*_encrypted*.json
        python3 decrypt.py in.json out.json
"""
import sys, os, json, base64, struct, glob, csv

KEY = b'xK#9pL@2mN!5vQ8r'                 # 16-byte XXTEA key (from libapp.so)
DELTA = 0x9E3779B9
MASK = 0xFFFFFFFF
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

def b64d(s):
    return base64.b64decode(s + "=" * (-len(s) % 4))

def _mx(z, y, total, k, p, e):
    return (((z >> 5 ^ (y << 2) & MASK) + (y >> 3 ^ (z << 4) & MASK))
            ^ ((total ^ y) + (k[(p & 3) ^ e] ^ z))) & MASK

def _xxtea_decrypt(v, k):
    n = len(v)
    rounds = 6 + 52 // n
    total = (rounds * DELTA) & MASK
    y = v[0]
    for _ in range(rounds):
        e = (total >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - _mx(z, y, total, k, p, e)) & MASK
            y = v[p]
        z = v[-1]
        v[0] = (v[0] - _mx(z, y, total, k, 0, e)) & MASK
        y = v[0]
        total = (total - DELTA) & MASK
    return v

_KWORDS = list(struct.unpack("<4I", KEY))

def decrypt_field(s):
    if not s:
        return ""
    data = b64d(s)
    n = len(data) // 4
    if n < 2:                                    # too short to be XXTEA-encoded
        return data.rstrip(b"\x00").decode("utf-8", "replace")
    v = list(struct.unpack("<%dI" % n, data))
    _xxtea_decrypt(v, _KWORDS)
    return struct.pack("<%dI" % n, *v).rstrip(b"\x00").decode("utf-8", "replace")

def decrypt_file(inp, outp):
    d = json.load(open(inp))
    out = {}
    for pid, rec in d.items():
        r = dict(rec)
        for f in ("q", "a", "sa"):
            if f in r:
                r[f] = decrypt_field(r[f])
        out[pid] = r
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=2)
    return out

def write_csv(out, csv_path):
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "quote", "author", "source"])
        for pid, r in out.items():
            w.writerow([pid, r.get("q", ""), r.get("a", ""), r.get("sa", "")])

def main():
    if len(sys.argv) == 3:
        out = decrypt_file(sys.argv[1], sys.argv[2])
        print(f"{len(out)} records -> {sys.argv[2]}")
        return
    for inp in sorted(glob.glob(os.path.join(DATA, "*_encrypted*.json"))):
        base = os.path.basename(inp).replace("_encrypted", "_decrypted")
        outp = os.path.join(DATA, base)
        out = decrypt_file(inp, outp)
        csv_path = outp[:-5] + ".csv"
        write_csv(out, csv_path)
        print(f"{len(out):>5} records  {os.path.basename(inp)} -> "
              f"{os.path.basename(outp)} + {os.path.basename(csv_path)}")

if __name__ == "__main__":
    main()
