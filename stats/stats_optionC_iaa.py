"""
Option-C IAA recompute: inter-rater agreement on A+B rows only (Channel C dropped).
Reuses stats_evaluator agreement functions; only adds a channel filter.

Usage:  python stats_optionC_iaa.py
"""
from pathlib import Path
import stats_evaluator as se

SHEET = Path(__file__).parent / "evaluation_template" / "evaluation_sheet_merged.csv"
KEEP = {"A-GitHub", "B-NHTSA"}

PAIRS = [
    ("E2", "E3", range(1, 202)),
    ("E3", "E4", range(202, 404)),
    ("E4", "E2", range(404, 606)),
]


def main():
    rows = se.load_sheet(SHEET)
    for r in rows:
        try:
            r["_row_num"] = int(r["Row_Number"])
        except (ValueError, KeyError):
            r["_row_num"] = -1

    print(f"{'='*70}\nOPTION C — IAA on A+B rows only\n{'='*70}")
    for ev1, ev2, rng in PAIRS:
        a1, a2, c1l, c2l = [], [], [], []
        for row in rows:
            if row["_row_num"] not in rng:
                continue
            if row.get("Channel") not in KEEP:
                continue
            if not se.has_rating(row, ev1) or not se.has_rating(row, ev2):
                continue
            a1.append("Y" if se.accepted(row, ev1) else "N")
            a2.append("Y" if se.accepted(row, ev2) else "N")
            try:
                x = int(row[f"{ev1}_Correctness_1to5"]); y = int(row[f"{ev2}_Correctness_1to5"])
                c1l.append("Y" if x >= 3 else "N"); c2l.append("Y" if y >= 3 else "N")
            except (ValueError, KeyError):
                c1l.append("N"); c2l.append("N")
        n = len(a1)
        if n == 0:
            print(f"  {ev1}/{ev2}: no A+B dual ratings in range")
            continue
        ac1_full = se.gwet_ac1(a1, a2)
        ac1_c = se.gwet_ac1(c1l, c2l)
        kappa_c = se.cohen_kappa(c1l, c2l)
        print(f"  {ev1}/{ev2} (n={n}):  AC1(accept)={ac1_full}  "
              f"AC1(C-only)={ac1_c}  kappa(C-only)={kappa_c}")


if __name__ == "__main__":
    main()
