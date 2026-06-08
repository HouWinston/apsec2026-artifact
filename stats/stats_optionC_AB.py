"""
Option-C recompute: A+B functional channels only (Channel C / Security DROPPED).

Reuses stats_evaluator's Framework-B majority-vote + E1 adjudication so the
numbers stay identical-methodology to the full-pipeline reporting; the only
change is the comparison FAMILY for the Holm-Bonferroni correction, which now
covers {A+B-combined vs Baseline, A vs Baseline, B vs Baseline} = 3 tests
(was 4 when Channel C was included).

Usage:
    python stats_optionC_AB.py
Writes:
    stats_tables/optionC_AB_channel_table.csv
"""
import csv
from pathlib import Path
from collections import defaultdict

import stats_evaluator as se

SHEET = Path(__file__).parent / "evaluation_template" / "evaluation_sheet_merged.csv"
OUT = Path(__file__).parent / "stats_tables" / "optionC_AB_channel_table.csv"

# Channels kept under Option C
KEEP = {"A-GitHub", "B-NHTSA", "Baseline"}


def final_accept_rows():
    """Replicate stats_evaluator.main() row classification (majority vote + E1)."""
    rows = se.load_sheet(SHEET)
    rated = []
    for row in rows:
        try:
            row["_row_num"] = int(row["Row_Number"])
        except (ValueError, KeyError):
            continue
        primary, secondary = se.get_row_raters(row["_row_num"])
        result = se.majority_vote_row(row, primary, secondary)
        if result is None:
            continue
        if result["is_data_halt"]:
            if se.has_rating(row, "E1"):
                result["Final_Accept"] = se.accepted(row, "E1")
                result["is_data_halt"] = False
                row["_mv"] = result
                rated.append(row)
            # else: pending E1, excluded (same as main)
        else:
            row["_mv"] = result
            rated.append(row)
    return rated


def main():
    rated = final_accept_rows()

    # Per-channel counts (Option C subset)
    ch = defaultdict(lambda: [0, 0])  # channel -> [accepted, total]
    for r in rated:
        c = r.get("Channel", "?")
        if c not in KEEP:
            continue
        ch[c][1] += 1
        if r["_mv"].get("Final_Accept"):
            ch[c][0] += 1

    k_b, n_b = ch["Baseline"]

    # Comparisons: A+B combined, A, B  vs Baseline
    k_a, n_a = ch["A-GitHub"]
    k_bn, n_bn = ch["B-NHTSA"]
    k_ab, n_ab = k_a + k_bn, n_a + n_bn

    comparisons = [
        ("A+B (functional)", k_ab, n_ab),
        ("A-GitHub", k_a, n_a),
        ("B-NHTSA", k_bn, n_bn),
    ]

    rows_out = []
    raw_ps = []
    for label, k, n in comparisons:
        odds, p = se.fisher_exact(k, n - k, k_b, n_b - k_b)
        h = se.cohen_h(k / n, k_b / n_b)
        lo, hi = se.wilson_ci(k, n)[1:]
        rows_out.append([label, k, n, round(k / n, 4), lo, hi, odds, p, h])
        raw_ps.append(p)

    holm = se.holm_bonferroni(raw_ps)

    # Baseline row + Wilson CI
    b_rate, b_lo, b_hi = se.wilson_ci(k_b, n_b)

    print(f"{'='*78}")
    print("OPTION C  —  A+B FUNCTIONAL CHANNELS ONLY  (Channel C dropped)")
    print(f"{'='*78}")
    print(f"\nBaseline: {k_b}/{n_b} = {b_rate*100:.1f}%  95%CI[{b_lo*100:.1f}, {b_hi*100:.1f}]")
    print(f"\n{'Comparison':<20}{'k/n':>10}{'Rate':>8}{'OR':>7}{'p_raw':>9}{'p_holm':>9}{'h':>7}{'sig':>5}")
    print("-" * 78)
    for (label, k, n, rate, lo, hi, odds, p, h), p_holm in zip(rows_out, holm):
        sig = "***" if p_holm < 0.001 else "**" if p_holm < 0.01 else "*" if p_holm < 0.05 else "ns"
        print(f"{label:<20}{f'{k}/{n}':>10}{rate*100:>7.1f}%{odds:>7.2f}{p:>9.4f}{p_holm:>9.4f}{h:>7.2f}{sig:>5}")

    # Write CSV
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comparison", "Accepted", "Total", "Acceptance_Rate",
                    "Wilson_CI_lo", "Wilson_CI_hi", "Fisher_OR",
                    "Fisher_p_raw", "Fisher_p_holm", "Cohen_h", "Significance"])
        w.writerow(["Baseline", k_b, n_b, round(b_rate, 4), b_lo, b_hi, "—", "—", "—", "—", "—"])
        for (label, k, n, rate, lo, hi, odds, p, h), p_holm in zip(rows_out, holm):
            sig = "***" if p_holm < 0.001 else "**" if p_holm < 0.01 else "*" if p_holm < 0.05 else "ns"
            w.writerow([label, k, n, round(rate, 4), lo, hi, odds, p, p_holm, h, sig])
    print(f"\n[written] {OUT}")


if __name__ == "__main__":
    main()
