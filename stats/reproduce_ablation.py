"""
Canonical reproducer for RQ3 (ablation, 50-item Ch-A subset).

Run:  python reproduce_ablation.py
Inputs (released layout):
  ../ablation/eval_2x2_FL_RQ3_replication.csv            (FL condition, per-row)
  ../generated_vcs/ablation/ablation_multirater_results.json (Abl-LM / Abl-NF MV)

Reproduces the paper's RQ3 numbers:
  FL (full pipeline)  29/50 = 58.0%   (majority vote of E2/E3/E4 + E1 adjudication)
  Abl-LM (LLM-match)  29/50 = 58.0%
  Abl-NF (no filter)  41/50 = 82.0%
  Reject attribution: Tool_Contamination 14, Semantic_Drift 5, Gen_Failure 2
Self-contained, stdlib only.
"""
import csv
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).parent.parent
FL_CSV = ROOT / "ablation" / "eval_2x2_FL_RQ3_replication.csv"
MV_JSON = ROOT / "generated_vcs" / "ablation" / "ablation_multirater_results.json"


def main():
    rows = list(csv.DictReader(open(FL_CSV, encoding="utf-8-sig")))
    labels = Counter(r["Final_Label"] for r in rows)
    fl_acc, n = labels["Accept"], len(rows)
    rej = Counter(r["Reject_Category"] for r in rows if r["Final_Label"] == "Reject")
    # FL per-rater accept (from the *_Accept columns)
    per = {e: sum(1 for r in rows if r[f"{e}_Accept"].strip().upper() in ("A", "Y", "TRUE", "1", "ACCEPT"))
           for e in ("E1", "E2", "E3", "E4")}

    mv = json.load(open(MV_JSON, encoding="utf-8"))["majority_vote"]
    lm, nd = mv["lm"], mv["nd"]

    print("=" * 64)
    print("CANONICAL RQ3 (ablation) REPRODUCER")
    print("=" * 64)
    print(f"\n[RQ3] Human acceptance (4-rater majority vote E2/E3/E4 + E1 adjudication)")
    print(f"  Full pipeline (FL)  {fl_acc}/{n} = {100*fl_acc/n:.1f}%   (paper 29/50 = 58.0%)")
    print(f"  Abl-LM (LLM-match)  {lm['accept']}/{lm['n']} = {100*lm['rate']:.1f}%   (paper 29/50 = 58.0%)")
    print(f"  Abl-NF (no filter)  {nd['accept']}/{nd['n']} = {100*nd['rate']:.1f}%   (paper 41/50 = 82.0%)")

    print(f"\n[RQ3] FL reject attribution (paper: Tool 14, Drift 5, GenFail 2)")
    for cat in ("Tool_Contamination", "Semantic_Drift", "Gen_Failure"):
        print(f"  {cat:20s} {rej.get(cat, 0)}")

    print(f"\n[RQ3] FL per-rater accept (paper: E1 33, E2 24, E3 47, E4 27)")
    print("  " + "  ".join(f"{e}={per[e]}" for e in ("E1", "E2", "E3", "E4")))


if __name__ == "__main__":
    main()
