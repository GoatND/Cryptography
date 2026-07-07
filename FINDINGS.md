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
  16, and the minimum length is 8 bytes (2 words) → the cipher operates on a
  **`Uint32List`** (confirmed by the `_decryptUint32List` symbol in
  `libapp.so`).
- Pooled entropy ≈ **7.93 bits/byte**; first bytes vary per record and
  two-time-pad tests fail → good diffusion, not a naive XOR/keystream scheme.
- Length signature + uint32-array + 16-byte key → **XXTEA (Corrected Block
  TEA)**, no IV/nonce (deterministic block cipher over the whole array).

## The cipher: XXTEA
- The key + algorithm live in the Flutter Dart snapshot **`libapp.so`** (arm64,
  25 MB). This is **absent from the base APK** (an AAB base split with zero
  native libs) — it was recovered from the **`config.arm64_v8a`** split inside
  the full XAPK bundle (`split_0.apk` → `lib/arm64-v8a/libapp.so`).
- Scheme: **XXTEA**, little-endian words, over the base64-decoded bytes of each
  field; plaintext is the UTF-8 string (zero-padded to a 4-byte boundary).
- Key (16 bytes, `Key.fromUtf8`): **`xK#9pL@2mN!5vQ8r`**
  (`784b2339704c40326d4e213576513872`). Recovered by brute-forcing candidate
  string constants from `libapp.so` against the XXTEA cipher, validated by
  readable-text output.

## Decrypted output
`extraction/decrypt.py` decrypts every field and writes, per dataset, a
`*_decrypted.json` and a flat `*_decrypted.csv` (id, quote, author, source):

| dataset | records | notes |
|---------|--------:|-------|
| `puzzle_info` | 2387 | Main English puzzle set |
| `puzzle_info_es` | 422 | Spanish |
| `puzzle_info_var1` (+`_es`) | 2387 / 422 | Re-encrypted duplicate of the main set |
| `dp_info` | 670 | Daily puzzles (keyed by date) |
| `dq_secret_puzzle` | 89 | Secret/"On This Day" puzzles |

All fields decrypt cleanly (0 garbled records; accented Spanish preserved).

Each record's `q` = quote, `a` = author, `sa` = source/attribution. The
cleartext `ul` gives the letter→cipher-number substitution and `pr` the letter
positions, so the full playable cryptogram is reconstructable per level.

## Tooling in this repo
- `extraction/analyze.py` — reproduces the structural / cipher analysis.
- `extraction/decrypt.py` — decrypts all datasets to JSON + CSV.
