#!/usr/bin/env python3
"""
Ablation multi-rater analysis: parse E2/E3/E4, combine with E1, compute statistics.
Output: ablation_multirater_results.json + printed report
"""
import re
import json
import math
from pathlib import Path

BASE = Path(__file__).parent
E1_JSON  = BASE / "output_ablation/ablation_acceptance_results.json"
E2_FILE  = BASE / "evaluation_template/消融E2评估输出.txt"
E3_FILE  = BASE / "evaluation_template/消融E3评估输出.txt"
E4_FILE  = BASE / "evaluation_template/消融E4评估输出.txt"
OUT_JSON = BASE / "output_ablation/ablation_multirater_results.json"

def accepts(c, n, u):
    """Framework B: C>=3 AND N=Y AND U=Y"""
    if c is None or n is None or u is None:
        return None
    return c >= 3 and n == 'Y' and u == 'Y'

# ── Parse E1 ──────────────────────────────────────────────────────────────────
def load_e1():
    data = json.loads(E1_JSON.read_text(encoding='utf-8'))
    results = {}
    for item in data['items']:
        n = item['num']
        results[n] = {
            'lm': {'c': item['lm_c'], 'n': item['lm_n'], 'u': item['lm_u'],
                   'accept': item['lm_accept']},
            'nd': {'c': item['nd_c'], 'n': item['nd_n'], 'u': item['nd_u'],
                   'accept': item['nd_accept']},
        }
    return results

# ── Parse E2 ──────────────────────────────────────────────────────────────────
def parse_e2():
    text = E2_FILE.read_text(encoding='utf-8')
    results = {}
    sections = re.split(r'\n## (\d+)\n', text)
    for i in range(1, len(sections), 2):
        num = int(sections[i])
        block = sections[i+1]
        xm = re.search(r'\* X=(\d),([YN]),([YN])', block)
        ym = re.search(r'\* Y=(\d),([YN]),([YN])', block)
        if xm and ym:
            xc, xn, xu = int(xm.group(1)), xm.group(2), xm.group(3)
            yc, yn, yu = int(ym.group(1)), ym.group(2), ym.group(3)
            results[num] = {
                'lm': {'c': xc, 'n': xn, 'u': xu, 'accept': accepts(xc,xn,xu)},
                'nd': {'c': yc, 'n': yn, 'u': yu, 'accept': accepts(yc,yn,yu)},
            }
    return results

# ── Parse E3 ──────────────────────────────────────────────────────────────────
def parse_e3():
    text = E3_FILE.read_text(encoding='utf-8')
    results = {}
    issues = []
    items = re.split(r'\[(\d+)/50\]', text)
    for i in range(1, len(items), 2):
        num = int(items[i])
        block = items[i+1]
        # Split at first "Y VC:" to separate X and Y sections
        parts = re.split(r'Y VC:', block, maxsplit=1)
        x_block = parts[0]
        y_block = parts[1] if len(parts) > 1 else ''

        def extract(b, label):
            cm = re.search(r'C:\s*(\d)', b)
            nm = re.search(r'N:\s*([YN])', b)
            um = re.search(r'U:\s*([YN])', b)
            c = int(cm.group(1)) if cm else None
            n = nm.group(1) if nm else None
            u = um.group(1) if um else None
            if c is None:
                issues.append(f"E3 item {num} {label}: missing C score")
            if n is None:
                issues.append(f"E3 item {num} {label}: missing N score")
            if u is None:
                issues.append(f"E3 item {num} {label}: missing U score — treating as N")
                u = 'N'
            return c, n, u

        xc, xn, xu = extract(x_block, 'X(lm)')
        yc, yn, yu = extract(y_block, 'Y(nd)')
        results[num] = {
            'lm': {'c': xc, 'n': xn, 'u': xu, 'accept': accepts(xc, xn, xu)},
            'nd': {'c': yc, 'n': yn, 'u': yu, 'accept': accepts(yc, yn, yu)},
        }
    print(f"\n[E3 parse issues] {len(issues)} warnings:")
    for iss in issues:
        print(f"  {iss}")
    return results

# ── Parse E4 ──────────────────────────────────────────────────────────────────
def parse_e4():
    text = E4_FILE.read_text(encoding='utf-8')
    results = {}
    issues = []
    csv_lines = re.findall(r'^(\d+),(\d),([YN]),([YN]),(\d),([YN]),([YN])', text, re.MULTILINE)
    for line in csv_lines:
        num = int(line[0])
        xc, xn, xu = int(line[1]), line[2], line[3]
        yc, yn, yu = int(line[4]), line[5], line[6]
        results[num] = {
            'lm': {'c': xc, 'n': xn, 'u': xu, 'accept': accepts(xc, xn, xu)},
            'nd': {'c': yc, 'n': yn, 'u': yu, 'accept': accepts(yc, yn, yu)},
        }
    # Items 4/21/50 discrepancies resolved 2026-05-23 per E4 correction:
    #   Item 4  ND: N=N→N=Y (CSV typo confirmed by E4)
    #   Item 21 ND: C=4→C=1 (inconsistent description; C=1 confirmed by E4)
    #   Item 50 X/Y: U=N→U=Y (CSV typo; note N=N unchanged so accept unchanged)
    return results

# ── Gwet's AC1 ───────────────────────────────────────────────────────────────
def gwet_ac1(r1_accepts, r2_accepts):
    """Binary Gwet's AC1 between two raters (lists of True/False/None)."""
    pairs = [(a, b) for a, b in zip(r1_accepts, r2_accepts) if a is not None and b is not None]
    n = len(pairs)
    if n == 0:
        return None
    agree = sum(1 for a, b in pairs if a == b)
    p_o = agree / n
    p1 = sum(1 for a, _ in pairs if a) / n
    p2 = sum(1 for _, b in pairs if b) / n
    p_e = (p1 * p2 + (1-p1) * (1-p2)) + (1/2) * (p1*(1-p2) + p2*(1-p1)) * (0)  # simple AC1
    # AC1 = (p_o - p_e_gwet) / (1 - p_e_gwet)
    # Gwet's p_e = (pi_hat * (1-pi_hat)) where pi_hat = (p1+p2)/2 * something
    # Simplified: Gwet's AC1 uses p_e = 2 * pi * (1 - pi) where pi = (p1+p2)/2
    pi = (p1 + p2) / 2
    p_e_gwet = 2 * pi * (1 - pi)
    if 1 - p_e_gwet == 0:
        return 1.0
    ac1 = (p_o - p_e_gwet) / (1 - p_e_gwet)
    return round(ac1, 4)

# ── Majority vote (≥2/3 of E2,E3,E4) ────────────────────────────────────────
def majority(accepts_list):
    valid = [a for a in accepts_list if a is not None]
    if len(valid) < 2:
        return None
    return sum(valid) >= (len(valid) / 2 + 0.01)  # strict majority

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    e1 = load_e1()
    e2 = parse_e2()
    e3 = parse_e3()
    e4 = parse_e4()

    print("\n" + "="*70)
    print("ABLATION MULTI-RATER ANALYSIS (Framework B: C≥3 AND N=Y AND U=Y)")
    print("="*70)

    # Check completeness
    for name, data in [("E2", e2), ("E3", e3), ("E4", e4)]:
        missing = [i for i in range(1, 51) if i not in data]
        print(f"\n[Completeness] {name}: {len(data)}/50 items parsed. Missing: {missing or 'none'}")

    # Per-rater acceptance rates
    conditions = ['lm', 'nd']
    cond_labels = {'lm': 'Abl-LM (X)', 'nd': 'Abl-ND (Y)'}
    raters = {'E1': e1, 'E2': e2, 'E3': e3, 'E4': e4}

    print("\n" + "-"*70)
    print("PER-RATER ACCEPTANCE RATES")
    print("-"*70)
    rate_data = {}
    for cond in conditions:
        rate_data[cond] = {}
        print(f"\n  Condition: {cond_labels[cond]}")
        for rname, rdata in raters.items():
            accepts_list = [rdata[i][cond]['accept'] for i in range(1,51) if i in rdata]
            n = len(accepts_list)
            acc = sum(1 for a in accepts_list if a)
            rate = acc/n if n > 0 else 0
            rate_data[cond][rname] = {'n': n, 'accept': acc, 'rate': rate, 'accepts_list': accepts_list}
            print(f"    {rname}: {acc}/{n} = {rate:.1%}")

    # Majority vote (E2, E3, E4)
    print("\n" + "-"*70)
    print("MAJORITY VOTE (E2+E3+E4, ≥2/3 accept)")
    print("-"*70)
    majority_results = {}
    flagged_items = []
    for cond in conditions:
        maj_list = []
        for i in range(1, 51):
            e2a = e2.get(i, {}).get(cond, {}).get('accept')
            e3a = e3.get(i, {}).get(cond, {}).get('accept')
            e4a = e4.get(i, {}).get(cond, {}).get('accept')
            maj = majority([e2a, e3a, e4a])
            maj_list.append(maj)
            # Flag disagreements
            votes = [e2a, e3a, e4a]
            valid = [v for v in votes if v is not None]
            if len(valid) == 3 and sum(valid) == 1:  # 2-1 split
                pass  # normal majority
            if len(valid) == 3 and sum(valid) != 0 and sum(valid) != 3:
                # Check if E3 is the outlier
                e3_outlier = (e3a != e2a and e3a != e4a and e2a == e4a)
                e2_outlier = (e2a != e3a and e2a != e4a and e3a == e4a)
                e4_outlier = (e4a != e2a and e4a != e3a and e2a == e3a)
                if e3_outlier:
                    flagged_items.append(f"Item {i} {cond.upper()}: E3={e3a} vs E2={e2a},E4={e4a} (E3 outlier)")
                elif e2_outlier:
                    flagged_items.append(f"Item {i} {cond.upper()}: E2={e2a} vs E3={e3a},E4={e4a} (E2 outlier)")
                elif e4_outlier:
                    flagged_items.append(f"Item {i} {cond.upper()}: E4={e4a} vs E2={e2a},E3={e3a} (E4 outlier)")
        majority_results[cond] = maj_list
        n = len([m for m in maj_list if m is not None])
        acc = sum(1 for m in maj_list if m)
        print(f"\n  {cond_labels[cond]}: {acc}/{n} = {acc/n:.1%}")

    print("\n" + "-"*70)
    print("INTER-RATER AGREEMENT (Gwet's AC1)")
    print("-"*70)
    for cond in conditions:
        print(f"\n  Condition: {cond_labels[cond]}")
        rater_names = ['E1', 'E2', 'E3', 'E4']
        rater_accepts = {}
        for rname, rdata in raters.items():
            rater_accepts[rname] = [rdata.get(i, {}).get(cond, {}).get('accept') for i in range(1, 51)]
        pairs = [(r1, r2) for r1 in rater_names for r2 in rater_names if r1 < r2]
        for r1, r2 in pairs:
            ac1 = gwet_ac1(rater_accepts[r1], rater_accepts[r2])
            print(f"    {r1}<->{r2}: AC1={ac1}")

    print("\n" + "-"*70)
    print(f"E3 OUTLIER ITEMS ({len([f for f in flagged_items if 'E3 outlier' in f])} items)")
    print("-"*70)
    for f in flagged_items:
        if 'E3 outlier' in f:
            print(f"  {f}")

    print("\n" + "-"*70)
    print(f"ALL MINORITY-VOTE ITEMS ({len(flagged_items)} total splits)")
    print("-"*70)
    for f in flagged_items:
        print(f"  {f}")

    # Save combined results
    output = {
        "meta": {
            "evaluation_date": "2026-05-23",
            "evaluators": ["E1-author", "E2-ASPICE", "E3-PhD", "E4-Tier1"],
            "protocol": "Framework B: C>=3 AND N=Y AND U=Y, majority vote E2/E3/E4"
        },
        "per_rater": {
            cond: {
                rname: {"n": rate_data[cond][rname]['n'],
                        "accept": rate_data[cond][rname]['accept'],
                        "rate": round(rate_data[cond][rname]['rate'], 4)}
                for rname in raters
            }
            for cond in conditions
        },
        "majority_vote": {
            cond: {
                "n": 50,
                "accept": sum(1 for m in majority_results[cond] if m),
                "rate": round(sum(1 for m in majority_results[cond] if m) / 50, 4)
            }
            for cond in conditions
        },
        "items_detail": {}
    }
    for i in range(1, 51):
        output["items_detail"][str(i)] = {
            "E1_lm": e1.get(i, {}).get('lm', {}).get('accept'),
            "E1_nd": e1.get(i, {}).get('nd', {}).get('accept'),
            "E2_lm": e2.get(i, {}).get('lm', {}).get('accept'),
            "E2_nd": e2.get(i, {}).get('nd', {}).get('accept'),
            "E3_lm": e3.get(i, {}).get('lm', {}).get('accept'),
            "E3_nd": e3.get(i, {}).get('nd', {}).get('accept'),
            "E4_lm": e4.get(i, {}).get('lm', {}).get('accept'),
            "E4_nd": e4.get(i, {}).get('nd', {}).get('accept'),
            "maj_lm": majority_results['lm'][i-1],
            "maj_nd": majority_results['nd'][i-1],
        }
    OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n[Saved] {OUT_JSON}")

if __name__ == "__main__":
    main()
