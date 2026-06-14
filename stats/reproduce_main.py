"""
Single canonical reproducer for the main evaluation (RQ1 + IAA).

Run:  python reproduce_main.py
Input: ../evaluation_data/evaluation_sheet_merged.csv  (489 rows, 2 channels)

Acceptance model (Framework B, matches the paper headline):
  Each row is rated by exactly two external raters (E2/E3/E4).
  A row is a *dispute* if |C_p - C_s| >= 2 OR the two accept-labels differ.
    - dispute      -> final label = E1 adjudication (accept iff E1 accepts; reject if E1 absent)
    - both agree   -> conservative resolution: final C = min(C_p, C_s),
                      final N/U = logical AND; accept iff C>=3 AND N=Y AND U=Y
  Accept(rater) := C>=3 AND N=Y AND U=Y.

All statistics (Fisher exact, Holm-Bonferroni, Cohen's h, Wilson CI, Gwet AC1)
are implemented inline; stdlib only. This file is self-contained and is the
single source of truth for the main-evaluation numbers in the paper.
"""
import csv
import math
from math import comb
from pathlib import Path
from collections import Counter

SHEET = Path(__file__).parent.parent / "evaluation_data" / "evaluation_sheet_merged.csv"
EXT = ("E2", "E3", "E4")


# ── statistics (stdlib only) ────────────────────────────────────────────────
def wilson_ci(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return round(p, 4), round(max(0, centre - margin), 4), round(min(1, centre + margin), 4)


def cohen_h(p1, p2):
    return round(2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2)), 4)


def fisher_exact(a, b, c, d):
    """2x2 Fisher's exact test (one-tailed, upper)."""
    n = a + b + c + d
    r1, r2 = a + b, c + d
    c1 = a + c
    p_val = sum(
        comb(r1, k) * comb(r2, c1 - k) / comb(n, c1)
        for k in range(a, min(r1, c1) + 1)
        if 0 <= c1 - k <= r2
    )
    odds = (a * d) / (b * c) if b * c > 0 else float("inf")
    return round(odds, 3), round(p_val, 4)


def holm_bonferroni(p_values):
    n = len(p_values)
    if n == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    raw = [min(1.0, p * (n - rank)) for rank, (_, p) in enumerate(indexed)]
    for i in range(1, len(raw)):
        raw[i] = max(raw[i], raw[i - 1])
    out = [0.0] * n
    for rank, (orig, _) in enumerate(indexed):
        out[orig] = round(raw[rank], 4)
    return out


def gwet_ac1(a_list, b_list):
    n = len(a_list)
    if n == 0:
        return None
    p_a = sum(1 for a, b in zip(a_list, b_list) if a == b) / n
    cats = list(set(a_list) | set(b_list))
    q = len(cats)
    if q <= 1:
        return 1.0
    p_e = sum(
        ((a_list.count(c) + b_list.count(c)) / (2 * n)) *
        (1 - (a_list.count(c) + b_list.count(c)) / (2 * n))
        for c in cats
    ) / (q - 1)
    return round((p_a - p_e) / (1 - p_e), 4) if p_e < 1 else 1.0


# ── row helpers ─────────────────────────────────────────────────────────────
def has(r, ev):
    return bool(r.get(f"{ev}_Correctness_1to5", "").strip())


def cscore(r, ev):
    try:
        return int(r[f"{ev}_Correctness_1to5"])
    except (ValueError, KeyError):
        return None


def yn(r, ev, dim):
    return r.get(f"{ev}_{dim}_YN", "N").strip().upper() == "Y"


def acc(r, ev):
    c = cscore(r, ev)
    return c is not None and c >= 3 and yn(r, ev, "Novelty") and yn(r, ev, "Usefulness")


def channel(ch):
    ch = (ch or "").strip()
    if ch.lower().startswith("baseline"):
        return "Baseline"
    return ch[0] if ch[:1] in "AB" else ch


def final_accept(r):
    """Final accept/reject label under the canonical model; None if <2 raters."""
    present = [ev for ev in EXT if has(r, ev)]
    if len(present) < 2:
        return None
    p, s = present[0], present[1]
    cp, cs = cscore(r, p), cscore(r, s)
    dispute = (abs(cp - cs) >= 2) or (acc(r, p) != acc(r, s))
    if dispute:
        return acc(r, "E1") if has(r, "E1") else False
    fc = min(cp, cs)
    return fc >= 3 and (yn(r, p, "Novelty") and yn(r, s, "Novelty")) \
        and (yn(r, p, "Usefulness") and yn(r, s, "Usefulness"))


# ── main ────────────────────────────────────────────────────────────────────
def main():
    rows = list(csv.DictReader(open(SHEET, encoding="utf-8-sig")))
    acc_cnt = Counter()
    tot_cnt = Counter()
    for r in rows:
        lab = final_accept(r)
        if lab is None:
            continue
        c = channel(r.get("Channel"))
        tot_cnt[c] += 1
        if lab:
            acc_cnt[c] += 1

    print("=" * 70)
    print(f"CANONICAL MAIN-EVALUATION REPRODUCER   sheet rows: {len(rows)}")
    print("=" * 70)

    print("\n[RQ1] Acceptance rate (majority vote + E1 adjudication)")
    base_k, base_n = acc_cnt["Baseline"], tot_cnt["Baseline"]
    for c, paper in (("A", "65.5% 57/87"), ("B", "67.2% 86/128"),
                     ("Baseline", "45.3% 124/274")):
        k, n = acc_cnt[c], tot_cnt[c]
        p, lo, hi = wilson_ci(k, n)
        print(f"  {c:9s} {k:3d}/{n:3d} = {100*k/n:5.1f}%  Wilson[{100*lo:.1f},{100*hi:.1f}]"
              f"   (paper {paper})")

    # combined A+B
    ab_k, ab_n = acc_cnt["A"] + acc_cnt["B"], tot_cnt["A"] + tot_cnt["B"]
    print(f"  {'A+B':9s} {ab_k:3d}/{ab_n:3d} = {100*ab_k/ab_n:5.1f}%   (paper 66.5% 143/215)")

    print("\n[RQ1] Effect sizes vs Baseline (Fisher exact, Cohen's h)")
    comps = []
    for name, k, n in (("A", acc_cnt["A"], tot_cnt["A"]),
                       ("B", acc_cnt["B"], tot_cnt["B"]),
                       ("A+B", ab_k, ab_n)):
        a, b = k, n - k
        cc, d = base_k, base_n - base_k
        odds, p = fisher_exact(a, b, cc, d)
        h = cohen_h(k / n, base_k / base_n)
        comps.append((name, odds, p, h))
    holm = holm_bonferroni([p for _, _, p, _ in comps])
    paper_ref = {"A": "OR2.30 h0.41 Holm0.0007", "B": "OR2.48 h0.45 Holm<.001",
                 "A+B": "OR2.40 h0.43 Holm<.001"}
    for (name, odds, p, h), hp in zip(comps, holm):
        print(f"  {name:5s} OR={odds:5.3f}  h={h:+.4f}  raw-p={p:.4f}  Holm-p={hp:.4f}"
              f"   (paper {paper_ref[name]})")

    print("\n[RQ2] Scope-stratified acceptance by category (pipeline vs baseline)")
    cats = {}
    for r in rows:
        lab = final_accept(r)
        if lab is None:
            continue
        cat = (r.get("Category") or "").strip()
        ch = channel(r.get("Channel"))
        d = cats.setdefault(cat, {"pk": 0, "pn": 0, "bk": 0, "bn": 0})
        if ch in ("A", "B"):
            d["pn"] += 1; d["pk"] += 1 if lab else 0
        elif ch == "Baseline":
            d["bn"] += 1; d["bk"] += 1 if lab else 0
    for cat in sorted(cats):
        d = cats[cat]
        pr = f"{d['pk']}/{d['pn']}={100*d['pk']/d['pn']:.1f}%" if d["pn"] else "      n/a"
        br = f"{d['bk']}/{d['bn']}={100*d['bk']/d['bn']:.1f}%" if d["bn"] else "n/a"
        print(f"  {cat:22s} pipeline {pr:16s} baseline {br}")
    print("  (paper Tab. rq2_scope: IO/HMI 23/31=74.2 vs 18/39; Body_Control 28/41=68.3 vs 21/42;")
    print("   Comm_Stack(A) 19/31=61.3 vs 31/55; Func_Safety 23/32=71.9; <SIG_43>=DCM(A) 29/44=65.9)")

    print("\n[IAA] Gwet AC1 on Completeness (C>=3), pairwise, 2-channel scope")
    print("      (paper reports 0.84 / 0.65 / 0.43 mean 0.64  <- 0.43/0.64 were 3-channel incl Channel-C)")
    def c_label(r, ev):
        c = cscore(r, ev)
        return None if c is None else ("Y" if c >= 3 else "N")
    pairs = [("E2", "E3"), ("E2", "E4"), ("E3", "E4")]
    for scope_name, keep in (("A+B only", {"A", "B"}), ("A+B+Baseline", {"A", "B", "Baseline"})):
        acs = []
        line = []
        for e1, e2 in pairs:
            a, b = [], []
            for r in rows:
                if channel(r.get("Channel")) not in keep:
                    continue
                if not has(r, e1) or not has(r, e2):
                    continue
                x, y = c_label(r, e1), c_label(r, e2)
                if x and y:
                    a.append(x); b.append(y)
            ac = gwet_ac1(a, b)
            if ac is not None:
                acs.append(ac)
                line.append(f"{e1}-{e2}(n={len(a)})={ac}")
        mean = round(sum(acs) / len(acs), 4) if acs else None
        print(f"  [{scope_name:13s}] " + "  ".join(line) + f"   mean={mean}")

    print("\n[IAA] Gwet AC1 on the ACCEPT label (Framework B), 2-channel — transparency")
    for e1, e2 in pairs:
        a, b = [], []
        for r in rows:
            if channel(r.get("Channel")) not in {"A", "B"}:
                continue
            if not has(r, e1) or not has(r, e2):
                continue
            a.append("Y" if acc(r, e1) else "N")
            b.append("Y" if acc(r, e2) else "N")
        ac = gwet_ac1(a, b)
        if ac is not None:
            print(f"  {e1}-{e2}(n={len(a)}) accept-AC1={ac}")


if __name__ == "__main__":
    main()
