#!/usr/bin/env python3
"""Build the Color Sort level schedule: which decoded level the game shows for level number N.

Rules recovered from StandartLevelsController / LevelControllerConfigurator (see
FINDINGS-colorsort.md, "Level ordering"):
  * levels 1..4            tutorial LevelPreset ScriptableObjects (not in the TextAssets)
  * level N >= 5           main pool line (N - 5)             [GlobalLevelId]
    except when (N - secret_firstshow) % secret_levelsfrequency == 0 (defaults 5 and 3):
                           secret pool line ((N - 5) / 3)      [CalculateSecretLevelIndex]
    (the main-pool line for that N is skipped: GlobalLevelId still advances)
  * after the main pool is exhausted (N > 4 + 1111) the game serves a random permutation
    of the last 500 main-pool lines, re-shuffled every 500 levels (per device) - not listed.

Usage: colorsort_schedule.py <data/colorsort dir> <out csv> [secret_firstshow] [secret_frequency]
"""
import csv, json, os, sys

TUTORIAL = 4


def main(d, out, first=5, freq=3):
    main_pool = json.load(open(os.path.join(d, 'game_competitors_merged_main_shuffeled_levels_1111_Binary.json')))
    secret = json.load(open(os.path.join(d, 'game_competitors_merged_secret_shuffeled_levels_371_Binary.json')))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from colorsort_decode import flask_summary
    rows = []
    for n in range(1, TUTORIAL + len(main_pool) + 1):
        if n <= TUTORIAL:
            rows.append([n, 'tutorial', n - 1, '', '', '', '', '', '', '']); continue
        g = n - TUTORIAL - 1
        if n >= first and (n - first) % freq == 0:
            i = (n - first) // freq
            src, lv = 'secret', (secret[i] if i < len(secret) else None)
        else:
            i, src, lv = g, 'main', main_pool[g]
        if lv is None:
            rows.append([n, src, i, '', '', '', '', '', '', 'index beyond pool']); continue
        flasks = lv['Flasks']
        colors = {s['colorId'] for f in flasks for s in f['segments']}
        rows.append([n, src, i, lv['InternalId'], lv['DifficultyCategory'], len(flasks),
                     sum(1 for f in flasks if not f['segments']), len(colors),
                     ' | '.join(flask_summary(f) for f in flasks), lv['Hash']])
    with open(out, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['level', 'source', 'pool_index', 'internal_id', 'difficulty', 'num_flasks',
                    'num_empty', 'num_colors', 'flasks_top_to_bottom', 'hash'])
        w.writerows(rows)
    print(f'{len(rows)} levels written to {out}')


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], a[1], *(int(x) for x in a[2:]))
