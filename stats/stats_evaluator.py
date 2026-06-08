"""
Statistical evaluation for IssueDriven-VC paper (Framework B, v2.0).
Run after human review CSV is filled in.

Usage (Phase 3/4 full analysis):
    python stats_evaluator.py --sheet evaluation_template/evaluation_sheet_merged.csv

Show DATA_HALT rows for E1 adjudication:
    python stats_evaluator.py --sheet ... --data-halt-only
"""
import sys, math, argparse, csv
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Row-range → rater pair mapping (EVALUATION_PROTOCOL §6) ─────────────────
#   Rows 001-201 : E2 (Primary) + E3 (Secondary)
#   Rows 202-403 : E3 (Primary) + E4 (Secondary)
#   Rows 404-605 : E4 (Primary) + E2 (Secondary)

def get_row_raters(row_1indexed: int):
    """Return (primary, secondary) rater codes for a given 1-indexed row number."""
    if row_1indexed <= 201:
        return "E2", "E3"
    elif row_1indexed <= 403:
        return "E3", "E4"
    else:
        return "E4", "E2"


# ── Core stat functions ──────────────────────────────────────────────────────

def wilson_ci(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2*n)) / denom
    margin = (z * math.sqrt(p*(1-p)/n + z**2/(4*n**2))) / denom
    return round(p, 4), round(max(0, centre-margin), 4), round(min(1, centre+margin), 4)


def cohen_kappa(ratings1, ratings2):
    """Cohen's κ for two lists of categorical ratings (same length)."""
    assert len(ratings1) == len(ratings2)
    n = len(ratings1)
    cats = sorted(set(ratings1) | set(ratings2))
    p_o = sum(1 for a, b in zip(ratings1, ratings2) if a == b) / n
    p_e = sum((ratings1.count(c) / n) * (ratings2.count(c) / n) for c in cats)
    if p_e >= 1.0:
        return 1.0
    return round((p_o - p_e) / (1 - p_e), 4)


def gwet_ac1(ratings1, ratings2):
    """
    Gwet's AC1 — kappa-paradox-resistant agreement for binary {Y,N} lists.
    Preferred over Cohen's κ when prevalence is skewed.
    """
    assert len(ratings1) == len(ratings2)
    n = len(ratings1)
    p_a = sum(1 for a, b in zip(ratings1, ratings2) if a == b) / n
    cats = list(set(ratings1) | set(ratings2))
    q = len(cats)
    if q <= 1:
        return 1.0
    p_e = sum(
        ((ratings1.count(c) + ratings2.count(c)) / (2 * n)) *
        (1 - (ratings1.count(c) + ratings2.count(c)) / (2 * n))
        for c in cats
    ) / (q - 1)
    if p_e >= 1.0:
        return 1.0
    return round((p_a - p_e) / (1 - p_e), 4)


def icc21(scores_by_rater):
    """
    ICC(2,1) — two-way random effects, single measures.
    scores_by_rater: list of [rater1_score, rater2_score] per subject (row).
    Returns (icc, p_value).
    """
    data = [pair for pair in scores_by_rater if None not in pair and len(pair) >= 2]
    if len(data) < 3:
        return None, None
    n = len(data)
    k = 2  # two raters per row in this study

    grand_mean = sum(v for pair in data for v in pair) / (n * k)
    row_means = [sum(pair) / k for pair in data]
    col_means = [sum(data[i][j] for i in range(n)) / n for j in range(k)]

    ss_r = k * sum((m - grand_mean)**2 for m in row_means)
    ss_c = n * sum((m - grand_mean)**2 for m in col_means)
    ss_t = sum((v - grand_mean)**2 for pair in data for v in pair)
    ss_e = ss_t - ss_r - ss_c

    ms_r = ss_r / (n - 1)
    ms_c = ss_c / (k - 1)
    ms_e = ss_e / ((n - 1) * (k - 1)) if (n - 1) * (k - 1) > 0 else 1e-9

    denom = ms_r + (k - 1) * ms_e + k * (ms_c - ms_e) / n
    icc = round((ms_r - ms_e) / denom, 4) if denom > 0 else 0.0

    f_stat = ms_r / ms_e if ms_e > 0 else float('inf')
    try:
        from scipy.stats import f as fdist
        p = round(fdist.sf(f_stat, n - 1, (n - 1) * (k - 1)), 4)
    except ImportError:
        p = None
    return icc, p


def cohen_h(p1, p2):
    """Effect size for difference between two proportions."""
    return round(2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2)), 4)


def fisher_exact(a, b, c, d):
    """2×2 Fisher's exact test (one-tailed)."""
    from math import comb
    n = a + b + c + d
    r1, r2 = a + b, c + d
    c1 = a + c
    p_val = sum(
        comb(r1, k) * comb(r2, c1 - k) / comb(n, c1)
        for k in range(a, min(r1, c1) + 1)
        if 0 <= c1 - k <= r2
    )
    odds = (a * d) / (b * c) if b * c > 0 else float('inf')
    return round(odds, 3), round(p_val, 4)


def holm_bonferroni(p_values):
    """Holm-Bonferroni step-down correction. Returns list of corrected p-values (same order as input)."""
    n = len(p_values)
    if n == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    raw_corrected = [min(1.0, p * (n - rank)) for rank, (_, p) in enumerate(indexed)]
    # Enforce monotonicity
    for i in range(1, len(raw_corrected)):
        raw_corrected[i] = max(raw_corrected[i], raw_corrected[i - 1])
    corrected = [0.0] * n
    for rank, (orig_idx, _) in enumerate(indexed):
        corrected[orig_idx] = round(raw_corrected[rank], 4)
    return corrected


def spearman_corr(x, y):
    """Spearman ρ between two lists."""
    n = len(x)

    def rank(lst):
        sorted_idx = sorted(range(n), key=lambda i: lst[i])
        ranks = [0] * n
        for rank_val, idx in enumerate(sorted_idx):
            ranks[idx] = rank_val + 1
        return ranks

    rx, ry = rank(x), rank(y)
    d2 = sum((a - b)**2 for a, b in zip(rx, ry))
    rho = 1 - 6 * d2 / (n * (n**2 - 1))
    if abs(rho) >= 1.0:
        return round(rho, 4), 0.0
    t = rho * math.sqrt((n - 2) / (1 - rho**2))
    try:
        from scipy.stats import t as tdist
        p = round(2 * tdist.sf(abs(t), df=n - 2), 4)
    except ImportError:
        p = None
    return round(rho, 4), p


# ── Acceptance logic (Framework B, v2.0) ────────────────────────────────────

def accepted(row, evaluator="E1"):
    """Framework B: C≥3 AND N=Y AND U=Y. Scope is NOT an acceptance gate."""
    try:
        corr = int(row.get(f"{evaluator}_Correctness_1to5", 0) or 0)
        novel = row.get(f"{evaluator}_Novelty_YN", "N").strip().upper()
        useful = row.get(f"{evaluator}_Usefulness_YN", "N").strip().upper()
        return corr >= 3 and novel == "Y" and useful == "Y"
    except Exception:
        return False


def has_rating(row, evaluator):
    """True if evaluator has filled in a Correctness score for this row."""
    return bool(row.get(f"{evaluator}_Correctness_1to5", "").strip())


# ── Majority vote logic ──────────────────────────────────────────────────────

def majority_vote_row(row, primary, secondary):
    """
    Compute majority-vote final label for a row.

    Returns dict with Final_Accept, Final_C, Final_N, Final_U, is_data_halt.
    Returns None if either rater hasn't rated this row yet.

    Rules (EVALUATION_PROTOCOL §6):
      - Both agree            → shared score is final
      - C differs by exactly 1 → lower C wins (conservative)
      - C differs by ≥ 2 OR   → DATA_HALT (E1 adjudication required)
        Accept/Reject disagrees
    """
    if not has_rating(row, primary) or not has_rating(row, secondary):
        return None

    try:
        c_p = int(row[f"{primary}_Correctness_1to5"])
        c_s = int(row[f"{secondary}_Correctness_1to5"])
    except (ValueError, KeyError):
        return None

    n_p = row.get(f"{primary}_Novelty_YN", "N").strip().upper()
    n_s = row.get(f"{secondary}_Novelty_YN", "N").strip().upper()
    u_p = row.get(f"{primary}_Usefulness_YN", "N").strip().upper()
    u_s = row.get(f"{secondary}_Usefulness_YN", "N").strip().upper()

    acc_p = c_p >= 3 and n_p == "Y" and u_p == "Y"
    acc_s = c_s >= 3 and n_s == "Y" and u_s == "Y"

    c_diff = abs(c_p - c_s)
    accept_disagree = acc_p != acc_s

    if c_diff >= 2 or accept_disagree:
        reasons = []
        if c_diff >= 2:
            reasons.append(f"C_diff={c_diff} ({primary}:{c_p} vs {secondary}:{c_s})")
        if accept_disagree:
            reasons.append(f"Accept disagree ({primary}:{acc_p} vs {secondary}:{acc_s})")
        return {
            "Final_Accept": None,
            "Final_C": None,
            "Final_N": None,
            "Final_U": None,
            "is_data_halt": True,
            "data_halt_reason": "; ".join(reasons),
            "primary": primary,
            "secondary": secondary,
        }

    # Conservative resolution: lower C, N=Y only if both Y, U=Y only if both Y
    final_c = min(c_p, c_s)
    final_n = "Y" if n_p == "Y" and n_s == "Y" else "N"
    final_u = "Y" if u_p == "Y" and u_s == "Y" else "N"
    final_accept = final_c >= 3 and final_n == "Y" and final_u == "Y"

    return {
        "Final_Accept": final_accept,
        "Final_C": final_c,
        "Final_N": final_n,
        "Final_U": final_u,
        "is_data_halt": False,
        "data_halt_reason": "",
        "primary": primary,
        "secondary": secondary,
    }


# ── Load sheet ───────────────────────────────────────────────────────────────

def load_sheet(csv_path):
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


# ── Helpers ──────────────────────────────────────────────────────────────────

def count_notes_tags(rows):
    """Count novel-invalid and novel-supplement tags across all Notes fields."""
    novel_invalid = novel_supplement = 0
    for row in rows:
        notes = " ".join(
            row.get(f"{ev}_Notes", "") for ev in ("E1", "E2", "E3", "E4")
        ).lower()
        if "novel-invalid" in notes:
            novel_invalid += 1
        if "novel-supplement" in notes:
            novel_supplement += 1
    return novel_invalid, novel_supplement


def get_scope_majority(row, evaluators=("E2", "E3", "E4")):
    """Return majority-voted scope for a row; fall back to E1 if no peer scores."""
    valid = {"ECU", "NETWORK", "NET", "HW", "OOS"}
    scopes = []
    for ev in evaluators:
        s = row.get(f"{ev}_Scope_ECU_Net_HW_OOS", "").strip().upper()
        if s in valid:
            scopes.append("NETWORK" if s == "NET" else s)
    if scopes:
        from collections import Counter
        return Counter(scopes).most_common(1)[0][0]
    s = row.get("E1_Scope_ECU_Net_HW_OOS", "?").strip().upper()
    return "NETWORK" if s == "NET" else s


# ── IAA block ────────────────────────────────────────────────────────────────

def _run_iaa(all_rows):
    """Compute per-rater-pair IAA statistics, including C-only variant."""
    pairs = [
        ("E2", "E3", range(1, 202)),     # rows 001-201
        ("E3", "E4", range(202, 404)),   # rows 202-403
        ("E4", "E2", range(404, 606)),   # rows 404-605
    ]
    for ev1, ev2, row_range in pairs:
        accept1, accept2, c_only1, c_only2, c_pairs = [], [], [], [], []
        for row in all_rows:
            rn = row["_row_num"]
            if rn not in row_range:
                continue
            if not has_rating(row, ev1) or not has_rating(row, ev2):
                continue
            accept1.append("Y" if accepted(row, ev1) else "N")
            accept2.append("Y" if accepted(row, ev2) else "N")
            try:
                c1 = int(row[f"{ev1}_Correctness_1to5"])
                c2 = int(row[f"{ev2}_Correctness_1to5"])
                c_only1.append("Y" if c1 >= 3 else "N")
                c_only2.append("Y" if c2 >= 3 else "N")
                c_pairs.append([c1, c2])
            except (ValueError, KeyError):
                c_only1.append("N")
                c_only2.append("N")

        n_pair = len(accept1)
        if n_pair == 0:
            print(f"    {ev1}/{ev2}: no dual ratings yet")
            continue

        kappa = cohen_kappa(accept1, accept2)
        ac1 = gwet_ac1(accept1, accept2)
        kappa_c = cohen_kappa(c_only1, c_only2)
        ac1_c = gwet_ac1(c_only1, c_only2)
        icc, icc_p = icc21(c_pairs) if len(c_pairs) >= 3 else (None, None)

        kappa_lv = (
            "Substantial" if kappa >= 0.6
            else "Moderate" if kappa >= 0.4
            else "Fair" if kappa >= 0.2
            else "Slight"
        )
        kappa_c_lv = (
            "Substantial" if kappa_c >= 0.6
            else "Moderate" if kappa_c >= 0.4
            else "Fair" if kappa_c >= 0.2
            else "Slight"
        )
        print(f"    {ev1}/{ev2} (n={n_pair}):  κ(full)={kappa} [{kappa_lv}]  AC1={ac1}", end="")
        if icc is not None:
            icc_lv = "Excellent" if icc >= 0.75 else "Good" if icc >= 0.6 else "Moderate"
            print(f"  ICC(2,1)={icc} [{icc_lv}, p={icc_p}]", end="")
        print()
        print(f"    {ev1}/{ev2}           κ(C-only)={kappa_c} [{kappa_c_lv}]  AC1(C-only)={ac1_c}"
              f"  ← Correctness-only (cf. CrUISE-AC κ=0.44)")


# ── DATA_HALT report ─────────────────────────────────────────────────────────

def _print_data_halt(data_halt_rows):
    print(f"\n{'='*65}")
    print(f"DATA_HALT ROWS — E1 adjudication required ({len(data_halt_rows)} rows)")
    print(f"{'='*65}")
    for row in data_halt_rows:
        mv = row.get("_mv", {})
        rn = row.get("_row_num", "?")
        p, s = mv.get("primary", "?"), mv.get("secondary", "?")
        print(f"\n  Row {rn:03d} | {row.get('Channel','?')} | {row.get('SYRS_ID','?')}")
        print(f"  {p}: C={row.get(f'{p}_Correctness_1to5','?')}  "
              f"N={row.get(f'{p}_Novelty_YN','?')}  "
              f"U={row.get(f'{p}_Usefulness_YN','?')}")
        print(f"  {s}: C={row.get(f'{s}_Correctness_1to5','?')}  "
              f"N={row.get(f'{s}_Novelty_YN','?')}  "
              f"U={row.get(f'{s}_Usefulness_YN','?')}")
        print(f"  Reason: {mv.get('data_halt_reason','?')}")
        vc = row.get("Generated_VC", "")
        print(f"  VC: {vc[:100]}{'...' if len(vc) > 100 else ''}")


# ── Main analysis ────────────────────────────────────────────────────────────

def run_analysis(csv_path, data_halt_only=False):
    all_rows = load_sheet(csv_path)
    for i, row in enumerate(all_rows):
        row["_row_num"] = i + 1

    print(f"\n{'='*65}")
    print(f"IssueDriven-VC — Statistical Evaluation (Framework B, v2.0)")
    print(f"{'='*65}")
    print(f"Total rows in sheet: {len(all_rows)}")

    # ── Classify rows ────────────────────────────────────────────────────
    rated_rows = []
    data_halt_rows = []
    e1_resolved_count = 0

    for row in all_rows:
        rn = row["_row_num"]
        primary, secondary = get_row_raters(rn)
        result = majority_vote_row(row, primary, secondary)

        if result is None:
            continue  # awaiting both raters

        row["_mv"] = result

        if result["is_data_halt"]:
            if has_rating(row, "E1"):
                # E1 has adjudicated this DATA_HALT row
                row["_mv"]["Final_Accept"] = accepted(row, "E1")
                row["_mv"]["Final_C"] = int(row.get("E1_Correctness_1to5") or 0)
                row["_mv"]["Final_N"] = row.get("E1_Novelty_YN", "N").strip().upper()
                row["_mv"]["Final_U"] = row.get("E1_Usefulness_YN", "N").strip().upper()
                row["_mv"]["is_data_halt"] = False
                row["_mv"]["e1_resolved"] = True
                e1_resolved_count += 1
                rated_rows.append(row)
            else:
                data_halt_rows.append(row)
        else:
            rated_rows.append(row)

    if data_halt_only:
        _print_data_halt(data_halt_rows)
        return

    n_dual = len(rated_rows) + len(data_halt_rows)
    print(f"Rows with both raters completed: {n_dual}")
    print(f"  → Majority-decided:               {len(rated_rows) - e1_resolved_count}")
    print(f"  → DATA_HALT resolved by E1:        {e1_resolved_count}")
    print(f"  → DATA_HALT pending E1:            {len(data_halt_rows)}")

    if not rated_rows:
        print("\n[!] No rows with complete dual ratings yet.")
        return

    # ── RAW-MAJORITY (§5 main result) ────────────────────────────────────
    print(f"\n{'─'*65}")
    print(f"RAW-MAJORITY RESULTS  (main, §5 RQ-2)")
    print(f"{'─'*65}")

    n_total = len(rated_rows)
    n_acc = sum(1 for r in rated_rows if r["_mv"].get("Final_Accept"))
    rate, lo, hi = wilson_ci(n_acc, n_total)
    print(f"\n[1] Overall Acceptance Rate (majority vote)")
    print(f"    {n_acc}/{n_total} = {rate*100:.1f}%  95%CI [{lo*100:.1f}%, {hi*100:.1f}%]")

    # ── By channel ───────────────────────────────────────────────────────
    print(f"\n[2] Acceptance by Channel")
    channels = defaultdict(list)
    for r in rated_rows:
        channels[r.get("Channel", "?")].append(r)

    ch_rates = {}
    for ch, ch_rows in sorted(channels.items()):
        n = len(ch_rows)
        k = sum(1 for r in ch_rows if r["_mv"].get("Final_Accept"))
        rate_ch, lo_ch, hi_ch = wilson_ci(k, n)
        ch_rates[ch] = (k, n, rate_ch)
        print(f"    {ch:<15} {k:3d}/{n:3d} = {rate_ch*100:.1f}%  [{lo_ch*100:.1f}%, {hi_ch*100:.1f}%]")

    pipeline_chs = [ch for ch in ch_rates if ch != "Baseline"]
    fisher_rows = []  # for Holm correction and CSV export

    if pipeline_chs and "Baseline" in ch_rates:
        k_b, n_b, _ = ch_rates["Baseline"]

        # Full pipeline vs Baseline
        k_f = sum(ch_rates[ch][0] for ch in pipeline_chs)
        n_f = sum(ch_rates[ch][1] for ch in pipeline_chs)
        if n_f and n_b:
            odds, p_val = fisher_exact(k_f, n_f - k_f, k_b, n_b - k_b)
            h = cohen_h(k_f / n_f, k_b / n_b)
            print(f"\n    Full Pipeline vs Baseline:")
            print(f"    Fisher p={p_val}, OR={odds}, Cohen's h={h} "
                  f"({'large' if abs(h) > 0.5 else 'medium' if abs(h) > 0.2 else 'small'})")
            fisher_rows.append(("Full Pipeline", k_f, n_f, p_val, odds, h))

        # Per-channel vs Baseline
        print(f"\n    Per-channel vs Baseline:")
        for ch in sorted(pipeline_chs):
            k_c, n_c, rate_c = ch_rates[ch]
            if n_c and n_b:
                odds_c, p_c = fisher_exact(k_c, n_c - k_c, k_b, n_b - k_b)
                h_c = cohen_h(k_c / n_c, k_b / n_b)
                size = 'large' if abs(h_c) > 0.5 else 'medium' if abs(h_c) > 0.2 else 'small'
                print(f"    {ch:<15}  Fisher p={p_c}, OR={odds_c}, h={h_c} [{size}]")
                fisher_rows.append((ch, k_c, n_c, p_c, odds_c, h_c))

        # Holm-Bonferroni correction
        if len(fisher_rows) > 1:
            raw_ps = [r[3] for r in fisher_rows]
            corrected_ps = holm_bonferroni(raw_ps)
            print(f"\n    Holm-Bonferroni corrected p-values:")
            k_b_rate, lo_b, hi_b = wilson_ci(k_b, n_b)
            print(f"    {'Comparison':<20} {'Raw p':>8}  {'Holm p':>8}  {'Sig':>5}  OR")
            for (label, k_c, n_c, p_raw, odds, h), p_corr in zip(fisher_rows, corrected_ps):
                sig = "***" if p_corr < 0.001 else "**" if p_corr < 0.01 else "*" if p_corr < 0.05 else "ns"
                print(f"    {label:<20} {p_raw:>8.4f}  {p_corr:>8.4f}  {sig:>5}  {odds}")

    # ── IAA ──────────────────────────────────────────────────────────────
    print(f"\n[3] Inter-rater Agreement (IAA)")
    _run_iaa(all_rows)

    # ── Correctness distribution ─────────────────────────────────────────
    print(f"\n[4] Correctness Distribution (majority final C)")
    c_dist = defaultdict(int)
    for r in rated_rows:
        c = r["_mv"].get("Final_C")
        if c is not None:
            c_dist[c] += 1
    for score in sorted(c_dist):
        pct = c_dist[score] / n_total * 100
        bar = "#" * int(pct / 2)
        print(f"    C={score}: {c_dist[score]:4d}/{n_total}  {pct:5.1f}%  {bar}")
    c3_plus = sum(v for k, v in c_dist.items() if k >= 3)
    print(f"    C≥3:  {c3_plus:4d}/{n_total} = {c3_plus/n_total*100:.1f}%"
          f"  ← Framework B 'useful starting point' threshold")

    # ── Scope distribution ───────────────────────────────────────────────
    print(f"\n[5] Scope Distribution (deployment context, not an acceptance gate)")
    scope_counts = defaultdict(int)
    for r in rated_rows:
        scope_counts[get_scope_majority(r)] += 1
    for sc in ["ECU", "NETWORK", "HW", "OOS", "?"]:
        cnt = scope_counts[sc]
        if cnt == 0:
            continue
        pct = cnt / n_total * 100
        print(f"    {sc:<10} {cnt:4d}/{n_total} = {pct:.1f}%")

    ecu_rows = [r for r in rated_rows if get_scope_majority(r) == "ECU"]
    ecu_acc = sum(1 for r in ecu_rows if r["_mv"].get("Final_Accept"))
    if ecu_rows:
        rate_ecu, lo_ecu, hi_ecu = wilson_ci(ecu_acc, len(ecu_rows))
        print(f"\n    ECU-scope acceptance (primary metric):")
        print(f"    {ecu_acc}/{len(ecu_rows)} = {rate_ecu*100:.1f}%  [{lo_ecu*100:.1f}%, {hi_ecu*100:.1f}%]")

    # ── Tag counts ───────────────────────────────────────────────────────
    n_invalid, n_supp = count_notes_tags(rated_rows)
    print(f"\n[6] VC Classification Tags (Notes field)")
    print(f"    novel-invalid:    {n_invalid}  (N=Y, U=N, no reuse path)")
    print(f"    novel-supplement: {n_supp}  (N=Y, U=N, protocol robustness value)")

    # ── C=3 showcase (Framework B) ───────────────────────────────────────
    c3_accepted = [
        r for r in rated_rows
        if r["_mv"].get("Final_Accept") and r["_mv"].get("Final_C") == 3
    ]
    print(f"\n[7] C=3 Accepted VCs  (co-pilot value: right direction, correctable flaw)")
    print(f"    {len(c3_accepted)} VCs — engineer can adopt after ~10-min fix")
    for ex in c3_accepted[:2]:
        vc = ex.get("Generated_VC", "")
        print(f"    [{ex.get('Channel','?')}] {ex.get('SYRS_ID','?')}: "
              f"{vc[:80]}{'...' if len(vc) > 80 else ''}")

    # ── EXPERT-ADJUSTED (sensitivity, appendix) ───────────────────────────
    if e1_resolved_count:
        print(f"\n{'─'*65}")
        print(f"EXPERT-ADJUSTED RESULTS  (sensitivity, appendix)")
        print(f"{'─'*65}")
        k_ea = sum(1 for r in rated_rows if r["_mv"].get("Final_Accept"))
        n_ea = len(rated_rows)
        rate_ea, lo_ea, hi_ea = wilson_ci(k_ea, n_ea)
        print(f"    Acceptance: {k_ea}/{n_ea} = {rate_ea*100:.1f}%  "
              f"95%CI [{lo_ea*100:.1f}%, {hi_ea*100:.1f}%]")
        print(f"    (includes {e1_resolved_count} E1-adjudicated DATA_HALT rows)")

    print(f"\n{'='*65}")

    # ── Export stats tables ──────────────────────────────────────────────────
    _export_stats_tables(csv_path, rated_rows, ch_rates, fisher_rows)


def _export_stats_tables(csv_path, rated_rows, ch_rates, fisher_rows):
    """Export channel_vs_baseline_table.csv and pvalue_raw_vs_corrected.csv."""
    import os
    tables_dir = Path(csv_path).parent.parent / "stats_tables"
    tables_dir.mkdir(exist_ok=True)

    # ── channel_vs_baseline_table.csv ────────────────────────────────────────
    channel_csv = tables_dir / "channel_vs_baseline_table.csv"
    with open(channel_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Channel", "Accepted", "Total", "Acceptance_Rate",
                         "Wilson_CI_lo", "Wilson_CI_hi", "Fisher_OR", "Fisher_p_raw",
                         "Fisher_p_holm", "Cohen_h", "Significance"])

        raw_ps = [r[3] for r in fisher_rows] if fisher_rows else []
        corrected_ps = holm_bonferroni(raw_ps) if raw_ps else []

        k_b, n_b, rate_b = ch_rates.get("Baseline", (0, 0, 0))
        b_rate, b_lo, b_hi = wilson_ci(k_b, n_b)
        writer.writerow(["Baseline", k_b, n_b,
                         f"{b_rate:.4f}", f"{b_lo:.4f}", f"{b_hi:.4f}",
                         "—", "—", "—", "—", "—"])

        for (label, k_c, n_c, p_raw, odds, h), p_corr in zip(fisher_rows, corrected_ps):
            rate_c, lo_c, hi_c = wilson_ci(k_c, n_c)
            sig = "***" if p_corr < 0.001 else "**" if p_corr < 0.01 else "*" if p_corr < 0.05 else "ns"
            writer.writerow([label, k_c, n_c,
                             f"{rate_c:.4f}", f"{lo_c:.4f}", f"{hi_c:.4f}",
                             odds, f"{p_raw:.4f}", f"{p_corr:.4f}", f"{h:.4f}", sig])
    print(f"\n[Export] {channel_csv}")

    # ── pvalue_raw_vs_corrected.csv ───────────────────────────────────────────
    pvalue_csv = tables_dir / "pvalue_raw_vs_corrected.csv"
    with open(pvalue_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Comparison", "k_treatment", "n_treatment",
                         "k_baseline", "n_baseline",
                         "OR", "p_raw_one_sided", "p_holm_corrected", "Cohen_h"])
        k_b, n_b, _ = ch_rates.get("Baseline", (0, 0, 0))
        for (label, k_c, n_c, p_raw, odds, h), p_corr in zip(fisher_rows, corrected_ps):
            writer.writerow([label, k_c, n_c, k_b, n_b,
                             odds, f"{p_raw:.4f}", f"{p_corr:.4f}", f"{h:.4f}"])
    print(f"[Export] {pvalue_csv}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="IssueDriven-VC statistical evaluation (v2.0)")
    p.add_argument("--sheet", default="evaluation_template/evaluation_sheet.csv",
                   help="Path to merged evaluation CSV")
    p.add_argument("--data-halt-only", action="store_true",
                   help="Print only DATA_HALT rows requiring E1 adjudication")
    args = p.parse_args()
    run_analysis(args.sheet, data_halt_only=args.data_halt_only)
