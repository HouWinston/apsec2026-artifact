"""RQ7 analysis: security-layer SecOC vs CVE head-to-head + domain-layered routing.

Primary result (verifier-perspective SecOC source replacing code-level CVE-RAG):
  - SecOC acceptance (3-rater Framework-B majority) vs CVE-RAG Cybersecurity 13/40.
Secondary:
  - Domain-layered routing: naive A+B+C merge vs routed A+B+SecOC (drop dominated CVE).
  - Inter-rater agreement (honest disclosure; E4 is a harsher outlier).

All numbers from real human eval; nothing hardcoded. Reproduces from:
  output_secoc/secoc_eval_filled_{E2,E3,E4}.{csv,txt}  (3 expert raters, this study)
  ../submission_icse2027/zenodo_package/evaluation/evaluation_labels_605.csv  (CVE baseline)
"""
import csv
import itertools
from pathlib import Path

WS = Path(__file__).parent
RATER_FILES = {"E2": WS / "output_secoc" / "secoc_eval_filled_E2.csv",
               "E3": WS / "output_secoc" / "secoc_eval_filled_E3.txt",
               "E4": WS / "output_secoc" / "secoc_eval_filled_E4.txt"}
EVAL605 = WS.parent / "submission_icse2027" / "zenodo_package" / "evaluation" / "evaluation_labels_605.csv"
LABELS_OUT = WS / "output_secoc" / "secoc_eval_labels.csv"


def accept(c, n, u):
    """Framework B acceptance: Correctness>=3 AND Novelty=Y AND Usefulness=Y."""
    try:
        c = int(float(c))
    except (TypeError, ValueError):
        return None
    return c >= 3 and str(n).strip().upper().startswith("Y") and str(u).strip().upper().startswith("Y")


def fisher_greater(a1, n1, a2, n2):
    """One-sided Fisher exact (group1 > group2). Returns (odds_ratio, p_value)."""
    from scipy.stats import fisher_exact
    odds, p = fisher_exact([[a1, n1 - a1], [a2, n2 - a2]], alternative="greater")
    return float(odds), float(p)


def _read(path):
    with open(path, encoding="utf-8-sig") as f:
        return {int(r["Item_No"]): r for r in csv.DictReader(f)}


def merge_raters():
    """Merge 3 raters -> per-item majority-vote FrameworkB_Accept; write labels CSV."""
    raters = {k: _read(v) for k, v in RATER_FILES.items()}
    items = sorted(raters["E2"])
    rows = []
    for it in items:
        per = {k: accept(raters[k][it]["Correctness_1to5"], raters[k][it]["Novelty_YN"],
                         raters[k][it]["Usefulness_YN"]) for k in raters}
        cs = {}
        for k in raters:
            try:
                cs[k] = int(float(raters[k][it]["Correctness_1to5"]))
            except (TypeError, ValueError):
                cs[k] = None
        n_acc = sum(1 for v in per.values() if v)
        majority = n_acc >= 2
        crange = (max(cs.values()) - min(cs.values())) if all(v is not None for v in cs.values()) else 0
        halt = crange >= 2 or len(set(per.values())) > 1
        rows.append({"Item_No": it, "SYRS_ID": raters["E2"][it]["SYRS_ID"],
                     "Category": raters["E2"][it].get("Category", ""),
                     "Channel": "D-SecOC",
                     "E2_C": cs["E2"], "E3_C": cs["E3"], "E4_C": cs["E4"],
                     "n_accept": n_acc, "FrameworkB_Accept": int(majority),
                     "DATA_HALT": int(halt)})
    with open(LABELS_OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return raters, items, rows


def main():
    raters, items, rows = merge_raters()
    sa = sum(r["FrameworkB_Accept"] for r in rows)
    sn = len(rows)
    print(f"[SecOC] security-layer acceptance (3-rater majority): {sa}/{sn} = {sa/sn:.1%}")
    cats = {}
    for r in rows:
        cats[r["Category"]] = cats.get(r["Category"], 0) + 1
    print(f"        category split: {cats}; abstained (NO_NOVEL) not in eval set")

    for k in raters:
        n = sum(1 for it in items if accept(raters[k][it]["Correctness_1to5"],
                                            raters[k][it]["Novelty_YN"], raters[k][it]["Usefulness_YN"]))
        print(f"        per-rater accept {k}: {n}/{sn} = {n/sn:.0%}")

    r605 = list(csv.DictReader(open(EVAL605, encoding="utf-8-sig")))
    cve = [r for r in r605 if r["Channel"] == "C-Security" and r["Category"] == "Cybersecurity"]
    ca, cn = sum(1 for r in cve if r["FrameworkB_Accept"] == "1"), len(cve)
    print(f"[CVE]   CVE-RAG Cybersecurity baseline: {ca}/{cn} = {ca/cn:.1%}")

    try:
        odds, p = fisher_greater(sa, sn, ca, cn)
        print(f"[Head-to-head] SecOC > CVE: OR={odds:.2f}, Fisher p(greater)={p:.4g}"
              f"  ({'SIGNIFICANT' if p < 0.05 else 'directional, n.s. at 0.05'})")
    except ImportError:
        print("[Head-to-head] scipy not installed; pip install scipy to get Fisher p")

    print("\n[IAA] pairwise agreement on Accept label:")
    for x, y in itertools.combinations(raters, 2):
        agree = sum(1 for it in items
                    if accept(raters[x][it]["Correctness_1to5"], raters[x][it]["Novelty_YN"], raters[x][it]["Usefulness_YN"])
                    == accept(raters[y][it]["Correctness_1to5"], raters[y][it]["Novelty_YN"], raters[y][it]["Usefulness_YN"]))
        print(f"        {x}-{y}: {agree}/{len(items)} = {agree/len(items):.0%}")

    print("\n[Routing] naive multi-source merge vs domain-layered routing:")
    def rate(rows_):
        a = sum(1 for r in rows_ if r["FrameworkB_Accept"] == "1")
        return a, len(rows_)
    aa, an = rate([r for r in r605 if r["Channel"] == "A-GitHub"])
    ba, bn = rate([r for r in r605 if r["Channel"] == "B-NHTSA"])
    cc, ccn = rate([r for r in r605 if r["Channel"] == "C-Security"])
    print(f"        naive A+B+C:            {aa+ba+cc}/{an+bn+ccn} = {(aa+ba+cc)/(an+bn+ccn):.1%}")
    print(f"        routed A+B+SecOC(-CVE): {aa+ba+sa}/{an+bn+sn} = {(aa+ba+sa)/(an+bn+sn):.1%}")


if __name__ == "__main__":
    main()
