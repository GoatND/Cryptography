# Color Sort (Get Color) APK — Level Data Extraction: Findings

## APK
- Release asset: `Get.Color_6.3.0.xapk` (201,510,471 bytes),
  SHA-256 `6646f6fbd3573c2e5d22800bf390832aa05966db1a4f747d6d32bd6f7b1079ff`
- Package: **`com.zm.watersort`**, versionName 6.3.0, versionCode 4601, minSdk 25, targetSdk 36
- Bundle contents: `base.apk` (237 MB, assets + Dalvik ad/SDK code, 61,589 classes) and
  `split_0.apk` (40 MB, `lib/arm64-v8a/*.so`).
- Engine: **Unity 6000.3.16f1, IL2CPP** (metadata version 39). The C# game code is compiled
  into `libil2cpp.so` (102 MB, stripped). `global-metadata.dat` (15 MB) is in
  `assets/bin/Data/Managed/Metadata/`.
- Game code lives in `Assembly-CSharp.dll` (namespaces `GetColor.*`, `ZM.*`, `SpecialMode`,
  `DailyChallenge`) plus a separate `WaterSortSolver.dll` and `ZM.Debug.LevelSelect.dll`
  (a developer level picker left in the build).

## Tooling used
| Step | Tool |
|------|------|
| Unpack XAPK / APKs | `unzip` |
| Dalvik side: manifest, package info, class inventory | **REA 6.7.0** (`rea inspect-android-package`) driving `jadx-headless-mcp 0.7.1` |
| Native side: function listing / decompilation | **REA** driving **Ghidra 12.1.4** headless (`rea inspect libil2cpp.so`) |
| Recover C# type/method names from IL2CPP | **Cpp2IL 2022.1.0-pre-release.21** (metadata v39 supported; Il2CppDumper only supports ≤ v31). `--use-processor attributeinjector` adds `[Address(RVA=…)]` to every method so Ghidra/REA lookups can be made by address. |
| Walk Unity serialized assets | **UnityPy 1.25.4** |

REA itself does no decompiling: it needs a caller-supplied engine. On this box that meant
downloading Ghidra 12.1.4 (`GHIDRA_INSTALL_DIR`) and the jadx MCP jar (`REA_JADX_MCP_JAR`).
Nothing in REA understands IL2CPP, so Cpp2IL was still required to name anything.

How REA actually fared here:
- `rea inspect-android-package base.apk` (jadx engine) worked: package, manifest, 61,589
  classes, permissions, in about a minute.
- `rea inspect` / `rea decompile` on `libil2cpp.so` (Ghidra engine) did not produce output.
  The first run was killed by REA's 330 s startup deadline. A second run with
  `REA_GHIDRA_STARTUP_TIMEOUT_MS=7000000` let Ghidra finish auto-analysis (about 100 minutes
  on 4 cores with REA's fixed 2 GB JVM heap), but REA runs `analyzeHeadless` read-only, the
  project was discarded ("Discarded file import due to readOnly option"), the bridge process
  exited, and REA returned `cleanup_incomplete` with no decompilation and no snapshot. So
  for a 102 MB IL2CPP binary the practical route was capstone + Cpp2IL addresses
  (`extraction/il2cpp_disasm.py`), which is what the "Level ordering" section is based on.
  Running Ghidra headless directly (own project, bigger heap) would work but is a separate,
  multi-hour job.

## Where the levels are
No level data is in the Addressables bundles (those hold wallpaper/flask skins only) and
nothing is encrypted. Levels are **`TextAsset`s inside the serialized Unity data files**
(`assets/bin/Data/<guid>`), 17 of them, named `*_Binary`:

| TextAsset | Levels | Type | Notes |
|-----------|-------:|------|-------|
| `game_competitors_merged_main_shuffeled_levels_1111_Binary` | 1111 | Default | Main campaign pool (InternalId 5..1115) |
| `game_competitors_merged_secret_shuffeled_levels_371_Binary` | 371 | Secret | Secret-level pool |
| `ms-6 GC_Layout_fixed_Binary` | 596 | 203 Default / 393 Secret | Alternative pool ("levels with mechanics") |
| `combined special levels_Binary` | 200 | Default | Tutorial/special layouts, capacities 3/6/8, `Layout` 0..16 |
| `A_Levels_3_Binary` / `A_Level_4+_Binary` | 134 / 66 | Default | Subsets of the above (capacity 3; capacity 6/8) |
| `daily_challenge_levels_Binary`, `_2`, `_3` | 31 each | Default, IndependentColors | One per calendar day; `LayoutId` e.g. `DC_7_LONG`, `DC_18_1_HEART` |
| `dc_c12_long`, `dc_c18_long`, `dc_shape`, `dc_special` | 41 / 39 / 13 / 3 | IndependentColors | Daily-challenge shaped boards (tall flasks of 12/18, pictures: HEART, FROG, CAT, OWL, PUMPKIN, GHOST, PINEAPPLE, CLOVER…) |
| `daily_secret_levels_0_Binary` | 100 | Secret | |
| `kitty_alternative_levels_Binary` | 100 | Secret | Kitty quest mode |
| `colored_flask_1_Binary` | 39 | mostly Secret | Colored-flask mechanic |
| `locked_by_position_levels_Binary` | 44 | mostly Secret | **Legacy**: written by an older schema (see below) |

Total: 2,992 levels, all decoded (`data/colorsort/*.json` and `*.csv`).

## Format
Each TextAsset is plain text, **one base64 line per level**. `DefaultLevelProvider(TextAsset)`
splits it into `lines` and `GetLevelByIndex(i)` deserializes line *i*. Each line is a
**MemoryPack** (Cysharp) object graph, `GenerateType.Object`, little-endian:

- Object: 1 byte member count (`0xFF` = null), then members in `[MemoryPackOrder]`.
  Older files carry fewer members (e.g. 7 instead of 9 for `LevelData`); missing ones default.
- `List<T>` / arrays: int32 count (`-1` = null) then elements. `bool` = 1 byte.
- `string`: int32 header; `-1` null; negative = `~utf8ByteCount` followed by int32 UTF-16
  length and the UTF-8 bytes (the only form seen here).

Schema (recovered from Cpp2IL output, `[MemoryPackOrder]` order):

```
LevelData      { List<FlaskData> Flasks; List<FlaskSegment> FirstMovesHint;
                 int DifficultyCategory; int InternalId; int Layout; string Hash;
                 LevelType LevelType; LevelRuleSet RuleSet; string LayoutId }
FlaskData      { List<FlaskSegment> segments; int maxSegmentsCount; int hiddenSegmentsCount;
                 int lockByColor; bool receiveOnly; bool isLockedByNeighbors;
                 List<int> hiddenItemIndexes; int receiveOnlyColorId;
                 LockByPositionData lockByPosition; bool needFill }
FlaskSegment   { int colorId; int size; bool[] isSegmentPartsHidden; int hiddenCount; int id }
LockByPositionData { int x; int y }          // legacy file has 4 ints
enum LevelType { Default=0, Secret=1 }   enum LevelRuleSet { Standard=0, IndependentColors=1 }
enum FlaskMechanicType { Curtains=1, Stone=2, Bush=3, HiddenSegments=4, ColoredFlask=5, LockedByPosition=6 }
```

Semantics verified on the decoded data:
- **`segments` are listed top → bottom.** In all 2,919 levels that have a `FirstMovesHint`,
  its first entry is the colour of some flask's *first* segment (only 61% match the last).
  `FirstMovesHint` is the scripted opening sequence (pour hint[0], then hint[1], …).
- Under `Standard` rules every colour's total `size` equals the capacity of one of the
  flasks (0 violations across all files). `maxSegmentsCount` is per flask (4 in the main
  pool; 3/6/8 in tutorials; 12/14/18 in daily-challenge tall boards).
- `size` > 1 is a pre-merged run of the same colour; `isSegmentPartsHidden` /
  `hiddenItemIndexes` mark the "?" hidden-segment mechanic (6,102 flasks); `lockByColor`
  (1,009), `receiveOnly` (+ `receiveOnlyColorId`, 699), `isLockedByNeighbors` (243) and
  `needFill` (37) are the other mechanics.
- `Hash` is a 64-hex string per level, used as the save-data key (`Level.SaveData.LevelHash`).
- `DifficultyCategory` ∈ {1,2,3}. Main pool: 583 / 235 / 293.
- `locked_by_position_levels_Binary` serializes `LockByPositionData` with **4** ints while the
  shipped class has 2 and is not version-tolerant, so the current game cannot load this
  file; it is a leftover. The decoder reads it anyway (`legacy_m2`, `legacy_m3`).

## Level ordering (how a level number maps to the pools)
Recovered by disassembling `StandartLevelsController`, `LevelControllerConfigurator`,
`DefaultLevelProvider` and `StandardLevelsRandomIndexProvider` from `libil2cpp.so`
(`extraction/il2cpp_disasm.py`, call targets named via Cpp2IL's `[Address]` map) and by
parsing the serialized `LevelsConfig` / `StandartLevelsController` objects with UnityPy.

- `LevelsConfig.standardLevelsJsonConfig` binds `baseConfig` → `game_competitors_merged_main_…_1111`,
  `secretConfig` → `…_secret_…_371`, `levelsWithMechanicsConfig` → `ms-6 GC_Layout_fixed`.
  `DefaultLevelProvider.GetLevelByIndex(i)` = `MemoryPackSerializer.Deserialize<LevelData>(FromBase64(lines[i]))`.
- The controller keeps three saved ints: `CurrentLevelId` (the displayed level number, starts
  at 1), `GlobalLevelId` (index into the main pool) and `NextLevelId`. `OnCompleteCurrentLevel`
  does `CurrentLevelId++`; once the tutorial is over it sets `GlobalLevelId = NextLevelId++`
  **on every completion, secret levels included**.
- **Levels 1–4** are tutorial `LevelPreset` ScriptableObjects (the serialized controller has 4
  `TutorialLevel {DefaultLevel, NewLevel}` entries), not lines from the TextAssets.
- **Level N ≥ 5** loads main-pool line `N − 5` (`GlobalLevelId`). The pool's `InternalId`
  equals N for every line (5…1115), which confirms the mapping.
- **Secret levels**: `IsSecretMode(N) = N ≥ first && (N − first) % freq == 0` with
  `Config.SecretStandardModeStartLevel` / `Frequency` fed by remote config
  `secret_firstshow = 5`, `secret_levelsfrequency = 3` (defaults in
  `assets/Config/remote_config_firebase_android.json`). Such a level is served from the secret
  pool at index `(N − first) / freq` (`CalculateSecretLevelIndex`), and the main-pool line
  for that N is skipped. So by default levels 5, 8, 11, … are secret levels 0, 1, 2, …
- **After the main pool** (`GlobalLevelId ≥ 1111`): `LoadRandomLevel` →
  `StandardLevelsRandomIndexProvider` built by `UpdateMainController` from the **last 500**
  pool indexes (`Config.RANDOM_RANGE_BEFORE_LEVELS`). `SetupRandomLevels` shuffles the first
  400 and the last 100 of those separately (`ListUtils.SortingPairs`, pairwise swaps with an
  unseeded `System.Random`), concatenates them, and re-shuffles after 500 draws. With
  `extended_random_levels_enabled = true` (remote, default false) the index set comes from
  `standardExtraLevelsToRandom` instead and every third level (`N % 3 == 1`) may come from the
  mechanics pool (`LoadRandomLevelWithMechanics`). Random picks are per device, so they are not
  tabulated.
- `TryLoadRemoteLevel` / `TryLoadOverridedLevel` run first and can replace any level with
  remote-config content (`remote_levels`, `override_levels_id`), both empty by default.

`data/colorsort/level_schedule.csv` (from `extraction/colorsort_schedule.py`) lists, for levels
1–1115, the source pool, line index, `InternalId`, difficulty and the flask layout.

## Tooling in this repo
- `extraction/colorsort_decode.py <dir of *_Binary.bytes> <out dir>` — MemoryPack decoder;
  writes per-file JSON (full structure) and CSV (`index, internal_id, difficulty, layout,
  layout_id, level_type, rule_set, num_flasks, num_empty_flasks, num_colors, flask_capacity,
  flasks, first_moves_hint, hash`). In the `flasks` column each flask is
  `top,…,bottom/capacity[flags]`, `c*n` = run of n, `?` = hidden part, `-` = empty.
- `extraction/colorsort_schedule.py` — level number → pool/line table (`data/colorsort/level_schedule.csv`).
- `extraction/il2cpp_disasm.py` — capstone ARM64 disassembly of IL2CPP methods by name, with
  `bl` targets resolved through Cpp2IL's `[Address]` attributes (`--use-processor attributeinjector`).
- `extraction/il2cpp_xrefs.py` — finds callers of a method by scanning every `bl` in the binary.
- The raw `*_Binary.bytes` TextAssets are dumped from `assets/bin/Data` with UnityPy into
  `apk/work/levels_raw/` (git-ignored).
