#!/usr/bin/env python3
"""Structural analysis of the Cryptogram game's encrypted level data.

Reads the *_encrypted.json config files extracted from the APK's
flutter_assets and reports on record counts, field structure, and the
cipher fingerprint (block vs stream, length signature, entropy).

Usage:  python3 analyze.py [path/to/puzzle_info_encrypted.json]
"""
import sys, os, json, base64, math, collections

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "..", "data", "puzzle_info_encrypted.json")

# Encrypted fields carry base64. `q` sometimes uses url-safe (-/_) chars,
# while `a`/`sa` use standard (+//=). Normalise both.
def b64d(s: str) -> bytes:
    s2 = s.replace("-", "+").replace("_", "/")
    return base64.b64decode(s2 + "=" * (-len(s2) % 4))

def entropy(b: bytes) -> float:
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())

def main(path):
    d = json.load(open(path))
    print(f"file: {os.path.basename(path)}")
    print(f"records: {len(d)}")
    keys = list(d.keys())
    print(f"key range: {keys[0]}..{keys[-1]}")
    sample = d[keys[0]]
    print(f"fields: {list(sample.keys())}")

    enc_fields = [f for f in ("q", "a", "sa") if f in sample]
    for f in enc_fields:
        lens = collections.Counter()
        mod16 = collections.Counter()
        pooled = bytearray()
        for v in d.values():
            b = b64d(v[f])
            lens[len(b)] += 1
            mod16[len(b) % 16] += 1
            pooled += b
        print(f"\nfield '{f}':")
        print(f"  length histogram : {dict(sorted(lens.items()))}")
        print(f"  len mod 16       : {dict(sorted(mod16.items()))}  "
              f"(all mult of 4 => stream cipher, not AES-CBC/ECB)")
        print(f"  pooled entropy   : {entropy(bytes(pooled)):.3f} bits/byte")

    # Cleartext fields describe the substitution puzzle directly.
    print("\ncleartext fields (per record):")
    print(f"  ul (letter->cipher-number map): {sample.get('ul')}")
    print(f"  pr (letter positions in grid) : {sample.get('pr')}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
