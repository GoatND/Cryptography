#!/usr/bin/env python3
"""Decrypt the Cryptogram game's level data once the key is known.

The encrypted fields (`q` = quote, `a` = answer/author, `sa`) are base64 of
[ nonce || stream-cipher(plaintext) ]. The cipher family and secret key live
in the Flutter Dart snapshot (libapp.so), which is NOT present in the base
APK. Once the key + scheme are recovered from libapp.so, fill in KEY / SCHEME
below and run this to emit fully decrypted JSON.

Supports the most likely schemes for the observed length signature
(8-byte-nonce-prefixed stream): Salsa20, ChaCha20, AES-CTR. Requires
`pip install pycryptodome` for AES/ChaCha/Salsa.

Usage:  python3 decrypt.py [in.json] [out.json]
"""
import sys, os, json, base64

# ---- FILL THESE IN once recovered from libapp.so -------------------------
KEY = None            # bytes, e.g. b"..." (16/24/32 bytes)
SCHEME = "salsa20"    # one of: "salsa20", "chacha20", "aes-ctr", "xor"
NONCE_LEN = 8         # bytes of nonce prefixed to each ciphertext
# --------------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))

def b64d(s: str) -> bytes:
    s2 = s.replace("-", "+").replace("_", "/")
    return base64.b64decode(s2 + "=" * (-len(s2) % 4))

def stream_decrypt(blob: bytes) -> bytes:
    nonce, ct = blob[:NONCE_LEN], blob[NONCE_LEN:]
    if SCHEME == "xor":
        return bytes(c ^ KEY[i % len(KEY)] for i, c in enumerate(ct))
    if SCHEME == "salsa20":
        from Crypto.Cipher import Salsa20
        return Salsa20.new(key=KEY, nonce=nonce).decrypt(ct)
    if SCHEME == "chacha20":
        from Crypto.Cipher import ChaCha20
        return ChaCha20.new(key=KEY, nonce=nonce).decrypt(ct)
    if SCHEME == "aes-ctr":
        from Crypto.Cipher import AES
        from Crypto.Util import Counter
        ctr = Counter.new(128, initial_value=int.from_bytes(nonce.ljust(16, b"\0"), "big"))
        return AES.new(KEY, AES.MODE_CTR, counter=ctr).decrypt(ct)
    raise SystemExit(f"unknown SCHEME {SCHEME!r}")

def dec_field(s: str) -> str:
    pt = stream_decrypt(b64d(s))
    return pt.rstrip(b"\x00").decode("utf-8", "replace")

def main(inp, outp):
    if KEY is None:
        sys.exit("KEY not set. Recover it from libapp.so and edit this file. "
                 "See FINDINGS.md.")
    d = json.load(open(inp))
    out = {}
    for pid, rec in d.items():
        r = dict(rec)
        for f in ("q", "a", "sa"):
            if f in r and r[f]:
                r[f] = dec_field(r[f])
        out[pid] = r
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=2)
    print(f"wrote {len(out)} decrypted records -> {outp}")

if __name__ == "__main__":
    inp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "data", "puzzle_info_encrypted.json")
    outp = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "data", "puzzle_info_decrypted.json")
    main(inp, outp)
