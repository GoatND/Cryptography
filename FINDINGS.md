# Cryptogram APK — Level Data Extraction: Findings

## APK
- File: `Cryptogram.apk` (101,047,453 bytes)
- SHA-256: `539b4dc3173435b3aa71a3bbaf542e6e3b683d6697df52f2f5e5724cd9ba9e77`
- Engine: **Flutter** (Dart). Level data lives in `assets/flutter_assets/assets/configs/`.

## What was extracted
All level datasets are present in the APK and copied to `data/`:

| File | Records | Contents |
|------|--------:|----------|
| `puzzle_info_encrypted.json` | 2387 | Main puzzle set (English) |
| `puzzle_info_encrypted_es.json` | — | Main puzzle set (Spanish) |
| `dp_info_encrypted.json` | 670 | Daily puzzles (keyed by date) |
| `dq_secret_puzzle_encrypted.json` | 89 | Secret/quest puzzles (keyed by date) |
| `puzzle_info_var1_encrypted.json` (+`_es`) | 2387 | A/B variant set (in APK, not copied) |

## Record structure
Each record (keyed by puzzle number, or date for daily) has:

```json
{
  "q":  "<base64 ciphertext>",   // the quote text (encrypted)
  "a":  "<base64 ciphertext>",   // answer/author (encrypted)
  "sa": "<base64 ciphertext>",   // secondary (encrypted)
  "ul": "O-2_T-10_A-13_...",     // CLEARTEXT: letter -> cipher-number map
  "pr": "1_2_3_4_6_7_...",       // CLEARTEXT: positions of letters in the grid
  "s": "", "lp": "", "dlp": "", "db": "0"
}
```

The `ul` and `pr` fields — the substitution key and the grid layout — are in
**cleartext**. The human-readable quote/answer text is encrypted.

## Cipher analysis (see `extraction/analyze.py`)
- Ciphertext byte-lengths are all multiples of **4** but **not** multiples of
  16 → **stream cipher**, not AES-ECB/CBC.
- Pooled entropy ≈ **7.93 bits/byte** → strong encryption, no obvious encoding.
- First bytes uniformly distributed; two-time-pad / keystream-reuse tests
  (whole-field and tail-after-nonce) all failed → **per-record random nonce,
  no keystream reuse**. Ciphertext-only attack is not feasible.
- Length signature fits `[ 8-byte nonce ] + streamcipher(plaintext padded to
  4)` → most likely **Salsa20 / ChaCha20** (8-byte nonce family) or AES-CTR.

## The blocker: missing key
- The decryption key + algorithm are compiled into the Flutter Dart snapshot
  **`libapp.so`**.
- This APK is an **AAB base split — it contains ZERO native libraries**
  (`lib/<abi>/*.so` is absent). The key is therefore not in this file.
- The key is **not** in the DEX (Java/Kotlin side — the `updatePuzzleInfo` /
  `puzzle_info_encrypted` symbols don't appear there; the AES refs in DEX
  belong to bundled ad SDKs) and **not** in any cleartext config.

## To finish decryption
Provide the native library **`libapp.so`** (arm64-v8a) from an install of this
game — e.g. a "universal" APK or the `config.arm64_v8a` split. The key is
recoverable from it (`strings libapp.so` for a hardcoded key, or by locating
the Salsa20/ChaCha20 key setup). Then set `KEY` / `SCHEME` in
`extraction/decrypt.py` and run it to emit fully decrypted level data.

## Tooling in this repo
- `extraction/analyze.py` — reproduces the structural / cipher analysis.
- `extraction/decrypt.py` — plug in the recovered key to decrypt all datasets.
