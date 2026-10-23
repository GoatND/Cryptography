# Mobile puzzle games — level data extraction

Reverse-engineering workspace for extracting level data from puzzle-game APKs.

| Game | Engine | Findings | Decoded data |
|------|--------|----------|--------------|
| Cryptogram word game | Flutter (XXTEA-encrypted JSON) | `FINDINGS.md`, `SOLVER.md` | `data/*.json`, `data/levels/` |
| Color Sort / Get Color (`com.zm.watersort` 6.3.0) | Unity 6 IL2CPP (MemoryPack TextAssets) | `FINDINGS-colorsort.md` | `data/colorsort/` |

APKs are not committed; drop them in `apk/` (git-ignored). Tool downloads and scratch
extraction live under `apk/work/`.
