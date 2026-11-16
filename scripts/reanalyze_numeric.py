"""Reanalyze the released Field2VC numerical CSVs without network or writes.

Usage: python scripts/reanalyze_numeric.py [--root PATH_TO_PUBLIC_REPOSITORY]

Public-data adapter prepared on 2026-11-16, not an original experiment runner.
Main resolution and Wilson definitions follow the retained reproduce_main.py;
pairwise AC1 follows recompute_iaa_perdim.py (adapted to public columns/labels).
No requirement/VC text, original identifiers, API credentials or private files
are read. Stored derived decisions are checked against the released C/N/U.
Assigned generation denominators (208/142/350) are declared benchmark inputs;
their source/coverage and the semantics of withheld content cannot be checked.
Saved historical stdout, Fisher/Holm and semantic judgments are not reproduced.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import math
from collections import Counter, defaultdict
from pathlib import Path

RATERS = ("E1", "E2", "E3", "E4")
EXTERNAL = RATERS[1:]
ASSIGNED = {"A": 208, "B": 142, "Baseline": 350}
TRUTH = {"1": True, "0": False, "A": True, "R": False}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def load(root, relative, required):
    with (root / relative).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        need(len(fields) == len(set(fields)), f"{relative}: duplicate column")
        need(set(required) <= set(fields), f"{relative}: missing required column")
        rows = list(reader)
    need(bool(rows), f"{relative}: empty file")
    need(all(None not in row and None not in row.values() for row in rows),
         f"{relative}: malformed CSV row")
    return rows


def bit(raw, context):
    need(raw in TRUTH, f"{context}: invalid binary decision")
    return TRUTH[raw]


def integer(raw, context):
    need(raw.isdigit() and str(int(raw)) == raw, f"{context}: invalid integer")
    return int(raw)


def rating(row, c, n, u):
    values = [row[k] for k in (c, n, u)]
    if values == ["", "", ""]:
        return None
    need(values[0] in {"1", "2", "3", "4", "5"}, f"{c}: invalid/incomplete rating")
    need(values[1] in {"Y", "N"} and values[2] in {"Y", "N"},
         f"{n}/{u}: invalid/incomplete rating")
    return int(values[0]) >= 3 and values[1:] == ["Y", "Y"]


def main_rating(row, evaluator):
    return rating(row, f"{evaluator}_Correctness_1to5",
                  f"{evaluator}_Novelty_YN", f"{evaluator}_Usefulness_YN")


def check_stored(raw, value, context):
    need(raw == "" if value is None else raw != "" and bit(raw, context) == value,
         f"{context}: stored decision disagrees with derived value")


def index(rows, keys, context):
    result = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        need(key not in result, f"{context}: duplicate key")
        result[key] = row
    return result


def compare(root, name, expected, keys):
    relative = "results/" + name
    fields = set(expected[0])
    actual = load(root, relative, fields)
    need(all(set(row) == fields for row in actual), f"{relative}: unexpected column")
    a, b = index(actual, keys, relative), index(expected, keys, relative)
    need(a.keys() == b.keys(), f"{relative}: row-key coverage differs")
    for key in a:
        for field in fields:
            value, wanted = a[key][field], b[key][field]
            if isinstance(wanted, (int, float)):
                try:
                    number = float(value)
                except ValueError as exc:
                    raise ValueError(f"{relative}: nonnumeric {field}") from exc
                need(math.isfinite(number) and math.isclose(number, wanted,
                     rel_tol=1e-10, abs_tol=1e-10), f"{relative}: value mismatch in {field}")
            else:
                need(value == wanted, f"{relative}: value mismatch in {field}")
    print(f"PASS {relative}: {len(actual)} rows")


def wilson(k, n):
    need(n > 0, "Wilson interval requires a nonzero denominator")
    p, z = k / n, 1.96
    denominator = 1 + z*z/n
    centre = (p + z*z/(2*n)) / denominator
    margin = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return round(p, 4), round(max(0, centre-margin), 4), round(min(1, centre+margin), 4)


def reanalyze_main(root):
    fields = ["Sample_ID", "Requirement_Group_ID", "Channel", "Category", "Dispute", "Final_Accept"]
    fields += [f"{e}_{s}" for e in RATERS for s in
               ("Correctness_1to5", "Novelty_YN", "Usefulness_YN", "Accept")]
    rows = load(root, "data/main_ratings.csv", fields)
    index(rows, ["Sample_ID"], "main ratings")
    for row in rows:
        need(row["Channel"] in ASSIGNED, "main ratings: unknown channel")
        decisions = {e: main_rating(row, e) for e in RATERS}
        for e in RATERS:
            check_stored(row[f"{e}_Accept"], decisions[e], f"main {e}")
        present = [e for e in EXTERNAL if decisions[e] is not None]
        need(len(present) == 2, "main ratings: expected exactly two external ratings")
        a, b = present
        dispute = (abs(int(row[f"{a}_Correctness_1to5"])-int(row[f"{b}_Correctness_1to5"])) >= 2
                   or decisions[a] != decisions[b])
        final = bool(decisions["E1"]) if dispute else decisions[a] and decisions[b]
        check_stored(row["Dispute"], dispute, "main dispute")
        check_stored(row["Final_Accept"], final, "main final")
    summary = []
    for channel in (*ASSIGNED, "A+B"):
        subset = [r for r in rows if r["Channel"] in ({"A", "B"} if channel == "A+B" else {channel})]
        n, k = len(subset), sum(r["Final_Accept"] == "1" for r in subset)
        p, low, high = wilson(k, n)
        summary.append(dict(Channel=channel, Outputs=n, Rated_Outputs=n, Accept=k,
                            Reject=n-k, Missing_Final=0, Disputes=sum(r["Dispute"] == "1" for r in subset),
                            Rate=p, Wilson_Low=low, Wilson_High=high))
    compare(root, "main_acceptance.csv", summary, ["Channel"])
    categories = []
    for category in sorted({r["Category"] for r in rows}):
        for condition in ("Pipeline", "Baseline"):
            subset = [r for r in rows if r["Category"] == category
                      and (r["Channel"] != "Baseline") == (condition == "Pipeline")]
            n, k = len(subset), sum(r["Final_Accept"] == "1" for r in subset)
            categories.append(dict(Category=category, Condition=condition, Accept=k,
                                   Rated_Outputs=n, Rate=k/n if n else ""))
    compare(root, "main_category_acceptance.csv", categories, ["Category", "Condition"])
    return rows


def reanalyze_ablation(root):
    fields = ["Sample_ID", "MV_Votes_of_3", "Final_Label", "E1_Dispute_with_MV", "Reject_Category"]
    fields += [f"{e}_{d}" for e in RATERS for d in ("C", "N", "U", "Accept")]
    fl = load(root, "data/ablation_fl_ratings.csv", fields)
    index(fl, ["Sample_ID"], "FL ratings")
    for row in fl:
        decisions = {e: rating(row, f"{e}_C", f"{e}_N", f"{e}_U") for e in RATERS}
        need(all(v is not None for v in decisions.values()), "FL ratings: missing rating")
        for e in RATERS:
            check_stored(row[f"{e}_Accept"], decisions[e], f"FL {e}")
        votes = sum(decisions[e] for e in EXTERNAL)
        need(integer(row["MV_Votes_of_3"], "FL votes") == votes, "FL: majority vote mismatch")
        need(row["Final_Label"] == ("Accept" if votes >= 2 else "Reject"), "FL: final mismatch")
        need(row["E1_Dispute_with_MV"] == ("Y" if decisions["E1"] != (votes >= 2) else "N"),
             "FL: E1 disagreement mismatch")
        need(row["Reject_Category"] in ({""} if votes >= 2 else
             {"Tool_Contamination", "Semantic_Drift", "Gen_Failure"}), "FL: invalid reject category")
    long = load(root, "data/ablation_condition_ratings.csv",
                ["Item_ID", "Condition", "Evaluator", "C", "N", "U", "Accept"])
    index(long, ["Item_ID", "Condition", "Evaluator"], "ablation ratings")
    groups = defaultdict(dict)
    for row in long:
        need(row["Condition"] in {"LM", "NF"} and row["Evaluator"] in RATERS, "ablation: invalid condition/rater")
        decision = rating(row, "C", "N", "U")
        need(decision is not None, "ablation: missing rating")
        check_stored(row["Accept"], decision, "ablation per-rater")
        groups[(row["Item_ID"], row["Condition"])][row["Evaluator"]] = decision
    items = []
    for (item, condition), decisions in groups.items():
        need(set(decisions) == set(RATERS), "ablation: incomplete rater coverage")
        votes = sum(decisions[e] for e in EXTERNAL)
        out = dict(Item_ID=item, Condition=condition, MV_Votes_of_3=votes, Final_Accept=int(votes >= 2))
        out.update({f"{e}_Accept": int(decisions[e]) for e in RATERS})
        items.append(out)
    need({r["Item_ID"] for r in items if r["Condition"] == "LM"} ==
         {r["Item_ID"] for r in items if r["Condition"] == "NF"}, "ablation: LM/NF item sets differ")
    # The same comparison routine also verifies the released intermediate table.
    intermediate = load(root, "data/ablation_majority_items.csv", list(items[0]))
    expected = index(items, ["Item_ID", "Condition"], "derived ablation items")
    stored = index(intermediate, ["Item_ID", "Condition"], "stored ablation items")
    need(stored.keys() == expected.keys(), "ablation items: coverage mismatch")
    for key, row in stored.items():
        for field, value in expected[key].items():
            need(row[field] == str(value), f"ablation items: mismatch in {field}")
    summary = [dict(Condition="FL", Accept=sum(r["Final_Label"] == "Accept" for r in fl), Outputs=len(fl))]
    for condition in ("LM", "NF"):
        subset = [r for r in items if r["Condition"] == condition]
        summary.append(dict(Condition=condition, Accept=sum(r["Final_Accept"] for r in subset), Outputs=len(subset)))
    for row in summary:
        row["Rate"] = row["Accept"] / row["Outputs"]
    compare(root, "ablation_acceptance.csv", summary, ["Condition"])
    counts = Counter(r["Reject_Category"] for r in fl if r["Final_Label"] == "Reject")
    compare(root, "ablation_fl_reject_attribution.csv",
            [dict(Reject_Category=k, Outputs=counts[k]) for k in ("Tool_Contamination", "Semantic_Drift", "Gen_Failure")],
            ["Reject_Category"])


def reanalyze_sensitivity(root):
    rows = load(root, "data/sensitivity_records.csv", ["Model", "Channel", "Requirement_Group_ID",
                "Record_ID", "Record_Order", "is_novel", "Last_Record", "Has_Error"])
    index(rows, ["Record_ID"], "sensitivity records")
    groups = defaultdict(list)
    for row in rows:
        need(row["Channel"] in {"A", "B"}, "sensitivity: unknown channel")
        for field in ("is_novel", "Last_Record", "Has_Error"):
            need(row[field] in {"0", "1"}, f"sensitivity: invalid {field}")
        groups[(row["Model"], row["Channel"], row["Requirement_Group_ID"])].append(row)
    aggregate = defaultdict(list)
    for (model, channel, _), records in groups.items():
        ordered = sorted(records, key=lambda r: integer(r["Record_Order"], "sensitivity Record_Order"))
        need([int(r["Record_Order"]) for r in ordered] == list(range(1, len(records)+1)),
             "sensitivity: record order is not contiguous/unique")
        need([r["Last_Record"] for r in ordered] == ["0"]*(len(records)-1)+["1"],
             "sensitivity: last-record marker mismatch")
        aggregate[(model, channel)].append((len(records), int(ordered[-1]["is_novel"])))
    summary = []
    for (model, channel), values in aggregate.items():
        n, count, k = len(values), sum(v[0] for v in values), sum(v[1] for v in values)
        summary.append(dict(Model=model, Channel=channel, Records=count, Unique_Items=n,
                            Duplicate_Records=count-n, Generated_Items=k, Generation_Rate=k/n))
    compare(root, "sensitivity_generation.csv", summary, ["Model", "Channel"])


def reanalyze_generation(root, main):
    rows = load(root, "data/generation_records.csv",
                ["Record_ID", "Requirement_Group_ID", "Channel", "Generated", "Sentinel"])
    index(rows, ["Record_ID"], "generation records")
    for row in rows:
        need(row["Channel"] in ASSIGNED, "generation: unknown channel")
        need(row["Generated"] in {"0", "1"} and row["Sentinel"] in {"0", "1"}, "generation: invalid flag")
        need(not (row["Generated"] == row["Sentinel"] == "1"), "generation: incompatible flags")
    summary = []
    for channel, assigned in ASSIGNED.items():
        subset = [r for r in rows if r["Channel"] == channel]
        observed = {r["Requirement_Group_ID"] for r in subset}
        generated = {r["Requirement_Group_ID"] for r in subset if r["Generated"] == "1"}
        sentinel = {r["Requirement_Group_ID"] for r in subset if r["Sentinel"] == "1"}
        rated = [r for r in main if r["Channel"] == channel]
        unique_rated = {r["Requirement_Group_ID"] for r in rated}
        need(unique_rated <= observed and len(observed) <= assigned, "generation: invalid coverage")
        summary.append(dict(Channel=channel, Assigned_Items=assigned, Raw_Records=len(subset),
            Observed_Unique_Items=len(observed), Duplicate_Records=len(subset)-len(observed),
            Generated_Records=sum(r["Generated"] == "1" for r in subset), Generated_Unique_Items=len(generated),
            Generation_Rate=len(generated)/assigned, Rated_Outputs=len(rated), Rated_Unique_Items=len(unique_rated),
            Items_Without_Evaluation=assigned-len(unique_rated), Sentinel_Only_Items=len(sentinel-generated)))
    compare(root, "generation_flow.csv", summary, ["Channel"])


def reanalyze_iaa(root, main):
    detail, summary, counts = [], [], []
    scopes = [("Full(A+B+Baseline)", set(ASSIGNED)), ("A+B(channel)", {"A", "B"}),
              ("A(GitHub)", {"A"}), ("B(NHTSA)", {"B"}), ("Baseline", {"Baseline"})]
    for scope, channels in scopes:
        rows = [r for r in main if r["Channel"] in channels]
        for dimension in ("C", "N", "U", "Accept"):
            ac1s = []
            for a, b in itertools.combinations(EXTERNAL, 2):
                pairs = []
                for row in rows:
                    values = []
                    for evaluator in (a, b):
                        accept = main_rating(row, evaluator)
                        value = None
                        if accept is not None:
                            value = {"C": int(row[f"{evaluator}_Correctness_1to5"]) >= 3,
                                     "N": row[f"{evaluator}_Novelty_YN"] == "Y",
                                     "U": row[f"{evaluator}_Usefulness_YN"] == "Y", "Accept": accept}[dimension]
                        values.append(value)
                    if all(v is not None for v in values):
                        pairs.append(values)
                n, raw, ac1 = len(pairs), "", ""
                if n:
                    raw = sum(x == y for x, y in pairs) / n
                    pi = sum(x+y for x, y in pairs) / (2*n)
                    chance = 2*pi*(1-pi)
                    ac1 = (raw-chance)/(1-chance)
                    ac1s.append(ac1)
                detail.append(dict(scope=scope, dimension=dimension, rater_pair=f"{a}-{b}", n=n,
                                   raw_agreement=round(raw, 4) if n else "", gwet_ac1=round(ac1, 4) if n else ""))
            summary.append(dict(scope=scope, dimension=dimension, n_pairs_with_data=len(ac1s),
                                mean_ac1_unweighted=round(sum(ac1s)/len(ac1s), 4) if ac1s else ""))
    legacy = {"A": "A-<SIG>", "B": "B-NHTSA", "Baseline": "Baseline"}
    for a, b in itertools.combinations(EXTERNAL, 2):
        for channel in ASSIGNED:
            n = sum(r["Channel"] == channel and main_rating(r, a) is not None
                    and main_rating(r, b) is not None for r in main)
            counts.append(dict(outer_scope="MainEval", condition=legacy[channel], rater_pair=f"{a}-{b}", n_jointly_rated=n))
    compare(root, "iaa_per_dimension_by_rater_pair.csv", detail, ["scope", "dimension", "rater_pair"])
    compare(root, "iaa_summary.csv", summary, ["scope", "dimension"])
    compare(root, "iaa_condition_rater_pair_counts.csv", counts, ["outer_scope", "condition", "rater_pair"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="root containing the released data/ and results/ folders")
    args = parser.parse_args()
    try:
        rows = reanalyze_main(args.root)
        reanalyze_ablation(args.root)
        reanalyze_sensitivity(args.root)
        reanalyze_generation(args.root, rows)
        reanalyze_iaa(args.root, rows)
    except (ValueError, OSError, KeyError, ZeroDivisionError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print("PASS: all 9 released results CSVs match numerical reanalysis; no files written.")
    print("LIMIT: assigned denominators are declared inputs; withheld-text flags/semantics and historical stdout are not verified.")


if __name__ == "__main__":
    main()
