"""
Per-dimension and conjunctive final-acceptance inter-rater agreement (Gwet AC1).

Run:
  python recompute_iaa_perdim.py            # main evaluation (RQ1/RQ2), E1 excluded
  python recompute_iaa_perdim.py --rq3      # also emit the RQ3 50-item ablation
                                            # (4-rater incl. E1 *and* external-only)

Inputs (relative to this file; no absolute paths):
  evaluation_sheet_merged.csv               # 489 rows, two channels + baseline
  ../ablation/eval_2x2_FL_RQ3_replication.csv  # 50-item FL ablation (with --rq3)

Outputs (written to ./derived/):
  iaa_per_dimension_by_rater_pair.csv   # one row per (scope, dimension, rater_pair)
  iaa_summary.csv                       # mean AC1 per (scope, dimension)
  iaa_condition_rater_pair_counts.csv   # joint-rating counts: exposes the
                                        # condition x rater-pair confounding

Method (fixed, so repeated runs are bit-for-bit identical):
  * Agreement is computed ONLY on items both raters of a pair actually scored.
  * Missing ratings (blank cells) are EXCLUDED -- never coerced to N / Reject.
  * The final Accept label is derived PER RATER as  C >= 3 AND N == Y AND U == Y
    BEFORE agreement is computed (never from a majority or adjudicated label).
  * E1 is EXCLUDED from the external-rater analysis by default; the RQ3 mode
    reports both the 4-rater (incl. E1) and the external-only figures so the
    effect of including the adjudicator is visible.
  * Agreement statistic = Gwet's AC1 for two raters, binary categories. AC1 is
    symmetric in the category coding, so the C>=3 / Y=1 direction does not
    affect the result; effective n and raw agreement are reported alongside.

Interpretation note (see README): rater-pair assignment is strongly associated
with experimental condition, and one channel-spanning pair jointly rated only a
handful of channel items, so pooled or condition-level AC1 values must NOT be
read as clean estimates of a condition effect. The per-pair n columns make this
checkable.
"""
import argparse
import csv
import itertools
from pathlib import Path

HERE = Path(__file__).resolve().parent
MERGED = HERE / "evaluation_sheet_merged.csv"
RQ3_FILE = HERE.parent / "ablation" / "eval_2x2_FL_RQ3_replication.csv"
DERIVED = HERE / "derived"

# Fixed orderings for deterministic output.
DIM_ORDER = ("C", "N", "U", "Accept")
PRECISION = 4


# ── value parsing (blank => None, i.e. excluded) ────────────────────────────
def parse_c(v):
    """Completeness 1..5 -> binary C>=3; blank/invalid -> None (excluded)."""
    v = (v or "").strip()
    return (1 if int(v) >= 3 else 0) if v in {"1", "2", "3", "4", "5"} else None


def parse_yn(v):
    """Y/N -> 1/0; blank/other -> None (excluded)."""
    v = (v or "").strip().upper()
    return 1 if v == "Y" else (0 if v == "N" else None)


def derive_accept(c, n, u):
    """Per-rater Accept = C>=3 AND N=Y AND U=Y; None if any criterion missing."""
    cb, nb, ub = parse_c(c), parse_yn(n), parse_yn(u)
    if cb is None or nb is None or ub is None:
        return None
    return 1 if (cb == 1 and nb == 1 and ub == 1) else 0


# ── Gwet AC1 (two raters, binary) ───────────────────────────────────────────
def gwet_ac1(pairs):
    """pairs: list of (a, b) in {0,1}. Returns (n, raw_agreement, ac1)."""
    n = len(pairs)
    if n == 0:
        return 0, None, None
    raw = sum(1 for a, b in pairs if a == b) / n
    pi1 = (sum(a for a, _ in pairs) / n + sum(b for _, b in pairs) / n) / 2.0
    pe = 2 * pi1 * (1 - pi1)
    ac1 = (raw - pe) / (1 - pe) if abs(1 - pe) > 1e-12 else None
    return n, raw, ac1


# ── column accessors per file layout ────────────────────────────────────────
def accessors_merged():
    return {
        "C": lambda r, e: parse_c(r.get(f"{e}_Correctness_1to5")),
        "N": lambda r, e: parse_yn(r.get(f"{e}_Novelty_YN")),
        "U": lambda r, e: parse_yn(r.get(f"{e}_Usefulness_YN")),
        "Accept": lambda r, e: derive_accept(
            r.get(f"{e}_Correctness_1to5"),
            r.get(f"{e}_Novelty_YN"),
            r.get(f"{e}_Usefulness_YN"),
        ),
    }


def accessors_rq3():
    return {
        "C": lambda r, e: parse_c(r.get(f"{e}_C")),
        "N": lambda r, e: parse_yn(r.get(f"{e}_N")),
        "U": lambda r, e: parse_yn(r.get(f"{e}_U")),
        "Accept": lambda r, e: derive_accept(
            r.get(f"{e}_C"), r.get(f"{e}_N"), r.get(f"{e}_U")
        ),
    }


def rated(row, rater, acc):
    """A rater scored a row iff its Completeness cell is present."""
    return acc["C"](row, rater) is not None


# ── consistency assertion against a stored _Accept column ───────────────────
def assert_stored_accept(rows, raters, acc):
    """If the file ships a per-rater *_Accept column, the derived Accept MUST
    match it on every jointly-defined cell. A mismatch -- OR a column that is
    present but yields zero validated cells (a parser gap) -- is a hard error."""
    truthy = {"Y", "1", "ACCEPT", "TRUE", "A"}   # this column uses A=Accept
    falsy = {"N", "0", "REJECT", "FALSE", "R"}    # this column uses R=Reject
    has_col = bool(rows) and all(f"{e}_Accept" in rows[0] for e in raters)
    if not has_col:
        print("  [check] no stored _Accept column in this file; cross-check skipped.")
        return
    mismatches = []
    checked = 0
    for i, row in enumerate(rows):
        for e in raters:
            der = acc["Accept"](row, e)
            stored_raw = (row.get(f"{e}_Accept") or "").strip().upper()
            stored = 1 if stored_raw in truthy else (0 if stored_raw in falsy else None)
            if der is not None and stored is not None:
                checked += 1
                if der != stored:
                    mismatches.append((i, e, der, stored, stored_raw))
    if mismatches:
        raise SystemExit(
            f"ABORT: derived Accept disagrees with stored _Accept in "
            f"{len(mismatches)} cell(s) (checked {checked}): {mismatches[:10]}"
        )
    if checked == 0:
        raise SystemExit(
            "ABORT: _Accept columns present but 0 cells cross-checked "
            "(unrecognised stored values -> parser gap)."
        )
    print(f"  [check] derived Accept == stored _Accept on all {checked} cells.")


# ── core: per (scope, dimension, pair) AC1 ──────────────────────────────────
def per_pair_rows(scope_label, rows, raters, acc):
    pairs = list(itertools.combinations(raters, 2))
    detail, summary = [], []
    for dim in DIM_ORDER:
        get = acc[dim]
        ac1s = []
        for ra, rb in pairs:
            data = []
            for row in rows:
                va, vb = get(row, ra), get(row, rb)
                if va is not None and vb is not None:
                    data.append((va, vb))
            n, raw, ac1 = gwet_ac1(data)
            detail.append({
                "scope": scope_label,
                "dimension": dim,
                "rater_pair": f"{ra}-{rb}",
                "n": n,
                "raw_agreement": "" if raw is None else round(raw, PRECISION),
                "gwet_ac1": "" if ac1 is None else round(ac1, PRECISION),
            })
            if n > 0 and ac1 is not None:
                ac1s.append(ac1)
        mean_ac1 = round(sum(ac1s) / len(ac1s), PRECISION) if ac1s else ""
        summary.append({
            "scope": scope_label,
            "dimension": dim,
            "n_pairs_with_data": len(ac1s),
            "mean_ac1_unweighted": mean_ac1,
        })
    return detail, summary


def condition_pair_counts(scope_label, rows, raters, acc, condition_of):
    """Joint-rating counts by (condition, rater_pair) -- exposes the confound."""
    pairs = list(itertools.combinations(raters, 2))
    out = []
    conds = sorted({condition_of(r) for r in rows})
    for ra, rb in pairs:
        for cond in conds:
            n = sum(
                1 for r in rows
                if condition_of(r) == cond and rated(r, ra, acc) and rated(r, rb, acc)
            )
            out.append({
                "outer_scope": scope_label,
                "condition": cond,
                "rater_pair": f"{ra}-{rb}",
                "n_jointly_rated": n,
            })
    return out


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rq3", action="store_true",
                    help="also emit the RQ3 50-item FL ablation (incl. E1 + external-only)")
    args = ap.parse_args()
    DERIVED.mkdir(exist_ok=True)

    detail_rows, summary_rows, count_rows = [], [], []

    # ── Main evaluation (RQ1/RQ2), E1 EXCLUDED ──────────────────────────────
    merged = list(csv.DictReader(open(MERGED, encoding="utf-8-sig")))
    acc_m = accessors_merged()
    ext = ("E2", "E3", "E4")
    print(f"Main eval: {len(merged)} rows from {MERGED.name} (E1 excluded).")
    assert_stored_accept(merged, ext, acc_m)  # no-op if no stored column

    def channel(r):
        return r["Channel"]

    scopes = [
        ("Full(A+B+Baseline)", merged),
        ("A+B(channel)", [r for r in merged if r["Channel"] in ("A-<SIG>", "B-NHTSA")]),
        ("A(GitHub)", [r for r in merged if r["Channel"] == "A-<SIG>"]),
        ("B(NHTSA)", [r for r in merged if r["Channel"] == "B-NHTSA"]),
        ("Baseline", [r for r in merged if r["Channel"] == "Baseline"]),
    ]
    for label, rows in scopes:
        d, s = per_pair_rows(label, rows, ext, acc_m)
        detail_rows += d
        summary_rows += s
    count_rows += condition_pair_counts("MainEval", merged, ext, acc_m, channel)

    # ── RQ3 50-item FL ablation (optional) ──────────────────────────────────
    if args.rq3:
        rq3 = list(csv.DictReader(open(RQ3_FILE, encoding="utf-8-sig")))
        acc_r = accessors_rq3()
        all4 = ("E1", "E2", "E3", "E4")
        print(f"RQ3 FL: {len(rq3)} rows from {RQ3_FILE.name}.")
        assert_stored_accept(rq3, all4, acc_r)  # this file ships _Accept columns
        for label, raters in [("RQ3_FL_4rater(inclE1)", all4),
                              ("RQ3_FL_external(E2E3E4)", ext)]:
            d, s = per_pair_rows(label, rq3, raters, acc_r)
            detail_rows += d
            summary_rows += s

    # ── write (stable order already enforced by construction) ───────────────
    write_csv(DERIVED / "iaa_per_dimension_by_rater_pair.csv",
              ["scope", "dimension", "rater_pair", "n", "raw_agreement", "gwet_ac1"],
              detail_rows)
    write_csv(DERIVED / "iaa_summary.csv",
              ["scope", "dimension", "n_pairs_with_data", "mean_ac1_unweighted"],
              summary_rows)
    write_csv(DERIVED / "iaa_condition_rater_pair_counts.csv",
              ["outer_scope", "condition", "rater_pair", "n_jointly_rated"],
              count_rows)

    # ── console summary ─────────────────────────────────────────────────────
    print("\nmean AC1 (unweighted over rater pairs with data):")
    print(f"  {'scope':<26}{'C':>9}{'N':>9}{'U':>9}{'Accept':>9}")
    by = {(s['scope'], s['dimension']): s['mean_ac1_unweighted'] for s in summary_rows}
    seen = []
    for s in summary_rows:
        if s['scope'] not in seen:
            seen.append(s['scope'])
    for sc in seen:
        vals = "".join(f"{str(by.get((sc, d), '')):>9}" for d in DIM_ORDER)
        print(f"  {sc:<26}{vals}")
    print(f"\nWrote 3 files to {DERIVED.relative_to(HERE.parent)}/")


if __name__ == "__main__":
    main()
