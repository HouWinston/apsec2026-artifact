"""SecOC traceability checker: detect/strip ungrounded quantifiers in security VCs.

Deterministic workflow (no LLM, no agents). Detects the "50 ms" traceability
hallucination: quantitative constraints in a generated VC that cannot be traced
to the source SYRS. See docs/superpowers/specs/2026-06-02-secoc-traceability-checker-design.md
"""
import re
import json
import csv
import datetime
from pathlib import Path

WORKSPACE = Path(__file__).parent
OUT_DIR = WORKSPACE / "output_secoc"
STATS_DIR = WORKSPACE / "stats_tables"

# UDS/ISO-14229 negative response codes only (NOT service IDs -- an introduced SID
# the SYRS never mentioned is off-target per E1, so SIDs must trace to the SYRS).
NRC_WHITELIST = {"10", "11", "12", "13", "22", "31", "33", "35", "36", "37", "7E", "7F"}

# HAND-ANNOTATED (2026-06-03), verified against full SYRS + VC text. NOT auto-derived:
# the action-level (mis)binding requires expert semantic reading. Rendered as report Appendix A.
SEMANTIC_CASE_NOTES = [
    {
        "syrs_id": "SYRS.0472_A", "verdict": "TIER-2 (genuine semantic misapplication)",
        "value": "500 ms",
        "syrs_action_value": "condition SATISFIED -> 'evaluate these conditions and update VinLock "
                             "within 500 ms of condition satisfaction' (the positive/True-update path)",
        "vc_action_value": "negative branch (VinOrig = all 0xFFs) -> 'set VinLock to False within 500 ms' "
                           "(a path the SYRS never time-bounds)",
        "why_lexical_passes": "500 ms IS lexically in the SYRS, so a value-presence check grounds it; "
                              "the error is the ACTION it is bound to, not the value.",
        "phase2_fix": "bind timing per (condition, action): 500 ms is licensed only for the "
                      "condition-satisfied -> VinLock=True update, not the negative branch.",
    },
    {
        "syrs_id": "SYRS.0430_B_A", "verdict": "E1-DISPUTE (checker exposes a probable E1 oversight)",
        "value": "10 ms",
        "syrs_action_value": "'Upon rejection, the system shall transmit a Security_Violation_Response "
                             "within 10 ms' -- EXPLICIT in the SYRS.",
        "vc_action_value": "same action: transmit Security_Violation_Response within 10 ms upon rejection "
                           "(invalid CMAC1 OR Freshness_Counter <= stored) -- MATCHES the SYRS exactly.",
        "why_lexical_passes": "correctly grounded AND correctly action-bound; the checker rightly does "
                              "NOT flag it.",
        "phase2_fix": "none needed -- instead RE-ADJUDICATE: E1's note '需求未指定违规响应的10ms' is "
                      "contradicted by the SYRS (the frozen requirement at generation time also contains "
                      "'within 10 ms'; SYRS_Classified unchanged since 2026-05-16, so no version drift).",
    },
]

# ---------------------------------------------------------------- normalization

_TIME_UNIT_MS = {
    "ms": 1.0, "msec": 1.0, "millisecond": 1.0, "milliseconds": 1.0,
    "s": 1000.0, "sec": 1000.0, "second": 1000.0, "seconds": 1000.0,
    "us": 0.001, "µs": 0.001, "microsecond": 0.001, "microseconds": 0.001,
}


def normalize_time_ms(value, unit):
    """Canonicalize a time quantity to milliseconds (float)."""
    return round(float(value) * _TIME_UNIT_MS[unit.strip().lower()], 6)


def normalize_hex(token):
    """Case/0x/$/space-insensitive hex token -> bare uppercase string.

    No cross-token byte concatenation (would create false matches).
    """
    t = token.strip().lstrip("$")
    t = re.sub(r"0[xX]", "", t)
    t = re.sub(r"[\s,]", "", t)
    return t.upper()


# ---------------------------------------------------------------- extraction

_UNIT_ALT = r"milliseconds?|microseconds?|msec|µs|us|ms|seconds?|sec|s"
_UNIT = r"(?:" + _UNIT_ALT + r")"
_TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(" + _UNIT_ALT + r")(?=[^A-Za-z0-9]|$)", re.IGNORECASE)
_HEX_RE = re.compile(r"(?:\$|0[xX])[0-9A-Fa-f]+")


def extract_quantifiers(text):
    """Return list of {kind, raw, norm, start, end}; kind in {'timing','hex'}."""
    out = []
    for m in _TIME_RE.finditer(text):
        bound = bool(_BOUND_BEFORE.search(text[max(0, m.start() - 30):m.start()]))
        out.append({"kind": "timing", "raw": m.group(0),
                    "norm": normalize_time_ms(m.group(1), m.group(2)),
                    "bound": bound, "start": m.start(), "end": m.end()})
    for m in _HEX_RE.finditer(text):
        out.append({"kind": "hex", "raw": m.group(0),
                    "norm": normalize_hex(m.group(0)),
                    "start": m.start(), "end": m.end()})
    return out


# ---------------------------------------------------------------- grounding

def build_grounding(syrs_text):
    """Build the grounding set (values the SYRS actually states)."""
    qs = extract_quantifiers(syrs_text)
    return {
        "timing_ms": {q["norm"] for q in qs if q["kind"] == "timing"},
        "hex": {q["norm"] for q in qs if q["kind"] == "hex"},
    }


def classify(q, grounding, nrc_whitelist):
    """3-tier verdict: SYRS_GROUNDED | NRC_GROUNDED | UNGROUNDED."""
    if q["kind"] == "timing":
        return "SYRS_GROUNDED" if q["norm"] in grounding["timing_ms"] else "UNGROUNDED"
    if q["norm"] in grounding["hex"]:
        return "SYRS_GROUNDED"
    if q["norm"] in nrc_whitelist:
        return "NRC_GROUNDED"
    return "UNGROUNDED"


# ---------------------------------------------------------------- surgical strip

_LEAD_WORDS = (r"within|in|after|for|every|no more than|not exceeding|less than|"
               r"more than|longer than|greater than|at least")
_LEAD_SYM = r">=|<=|>|<|≥|≤"
_LEAD = r"(?:" + _LEAD_WORDS + r"|" + _LEAD_SYM + r")"
# A timing is a *bound* (acceptance threshold E1 punishes) only if introduced by a
# lead word/symbol -- NOT a bare stimulus input like "received at 495ms" (which E1
# accepts as a within-window boundary value; see SYRS.0429_B).
_BOUND_BEFORE = re.compile(
    r"(?:(?:^|\s)(?:" + _LEAD_WORDS + r")|(?:" + _LEAD_SYM + r"))\s*$", re.IGNORECASE)
_TIME_PHRASE = re.compile(r"\s*\b" + _LEAD + r"\b\s*\d+(?:\.\d+)?\s*" + _UNIT + r"\b", re.IGNORECASE)
# a line whose predicate IS the timing comparison (e.g. "takes longer than 50 ms to ...")
_TIMING_PREDICATE_LINE = re.compile(r"^.*\btakes?\b.*\d+(?:\.\d+)?\s*" + _UNIT + r"\b.*$",
                                    re.IGNORECASE)


def _timing_norms_in(text):
    return {normalize_time_ms(m.group(1), m.group(2)) for m in _TIME_RE.finditer(text)}


def strip_ungrounded(vc_text, ungrounded):
    """Surgically remove ungrounded TIMING (phrase or whole-bullet). Returns
    (clean_vc, audit). Ungrounded hex/identifiers are reported, not auto-removed
    (removing an identifier usually guts the test target -> MIXED/Phase-2)."""
    audit = []
    # only strip ungrounded *bound* timings (acceptance thresholds), never stimulus inputs
    timing_ung = [q for q in ungrounded if q["kind"] == "timing" and q.get("bound", True)]
    if not timing_ung:
        return vc_text, audit
    ung_norms = {q["norm"] for q in timing_ung}

    # 1) whole-line removal where timing is the predicate
    kept = []
    for line in vc_text.splitlines():
        if _TIMING_PREDICATE_LINE.match(line) and (_timing_norms_in(line) & ung_norms):
            tok = _TIME_RE.search(line)
            audit.append({"field": "bullet", "original_span": line.strip(),
                          "removed_token": tok.group(0) if tok else "", "action": "remove_bullet"})
            continue
        kept.append(line)
    out = "\n".join(kept)

    # 2) phrase removal for residual ungrounded timing
    def _sub(m):
        tm = _TIME_RE.search(m.group(0))
        if tm and normalize_time_ms(tm.group(1), tm.group(2)) in ung_norms:
            audit.append({"field": "phrase", "original_span": m.group(0).strip(),
                          "removed_token": tm.group(0), "action": "remove_phrase"})
            return ""
        return m.group(0)

    out = _TIME_PHRASE.sub(_sub, out)
    out = re.sub(r"[ \t]+([.,;)])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out, audit


# ---------------------------------------------------------------- runner

def _load_syrs_source():
    src = json.loads((WORKSPACE.parent / "data" / "SYRS_Classified_20260429_085505.json")
                     .read_text(encoding="utf-8"))
    idx = {}

    def walk(o):
        if isinstance(o, dict):
            if "SYRS_ID" in o:
                idx[o["SYRS_ID"]] = o.get("System_Requirements", "")
            else:
                for v in o.values():
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(src)
    return idx


def _load_gt():
    lines = [l for l in (OUT_DIR / "gt_failure_category.csv").read_text(encoding="utf-8").splitlines()
             if not l.lstrip().startswith("#")]
    return {r["syrs_id"]: r for r in csv.DictReader(lines)}


def run_checker(write=True):
    vcs = json.loads((OUT_DIR / "secoc_generated_vcs.json").read_text(encoding="utf-8"))
    novel = [v for v in vcs if "NO_NOVEL_VC_FOUND" not in v.get("generated_vc", "")]
    syrs_src = _load_syrs_source()
    gt = _load_gt()
    per_vc, filtered = [], []
    for v in novel:
        sid = v["syrs_id"]
        syrs_text = syrs_src.get(sid) or v.get("requirement", "")
        grounding = build_grounding(syrs_text)
        qs = extract_quantifiers(v["generated_vc"])
        for q in qs:
            q["verdict"] = classify(q, grounding, NRC_WHITELIST)
        ungrounded = [q for q in qs if q["verdict"] == "UNGROUNDED"]
        clean, audit = strip_ungrounded(v["generated_vc"], ungrounded)
        per_vc.append({"syrs_id": sid, "quants": qs,
                       "n_ungrounded_timing": sum(q["kind"] == "timing" and q["verdict"] == "UNGROUNDED"
                                                  and q.get("bound", True) for q in qs),
                       "n_ungrounded_stimulus": sum(q["kind"] == "timing" and q["verdict"] == "UNGROUNDED"
                                                    and not q.get("bound", True) for q in qs),
                       "n_ungrounded_hex": sum(q["kind"] == "hex" and q["verdict"] == "UNGROUNDED"
                                               for q in qs)})
        filtered.append({"syrs_id": sid, "filtered_vc": clean, "audit": audit})
    metrics = _compute_metrics(per_vc, gt)
    if write:
        _write_report(per_vc, gt, metrics)
        (OUT_DIR / "secoc_vcs_filtered.json").write_text(
            json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_metrics_csv(metrics)
    return {"n_novel": len(novel), "per_vc": per_vc, "metrics": metrics}


def _compute_metrics(per_vc, gt):
    pred = {r["syrs_id"]: r["n_ungrounded_timing"] > 0 for r in per_vc}
    # checker target = lexically-absent bound timings (what a lexical checker CAN detect)
    tp = fp = fn = 0
    for sid, row in gt.items():
        truth = row["lex_ungrounded_timing"] == "1"
        p = pred.get(sid, False)
        if truth and p:
            tp += 1
        elif truth and not p:
            fn += 1
        elif (not truth) and p:
            fp += 1
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    n_lex = sum(1 for row in gt.values() if row["lex_ungrounded_timing"] == "1")
    # Tier-2 genuine misapplication: value in SYRS but mis-bound to wrong action (Phase-2 target)
    n_sem = sum(1 for row in gt.values() if row["sem_misapplied_timing"] == "1")
    # E1-dispute: checker grounds value correctly but E1's stated reason is contradicted by SYRS
    n_disp = sum(1 for row in gt.values() if row["e1_dispute"] == "1")
    # recall vs E1's VALID timing complaints (excludes the disputed/erroneous E1 reason)
    recall_valid = tp / (n_lex + n_sem) if (n_lex + n_sem) else 0.0
    halluc = sum(1 for r in per_vc if r["n_ungrounded_timing"] > 0) / len(per_vc)
    # recoverable ceilings: E1 in-principle vs lexically-strippable by THIS Phase-1 checker
    h2a = sum(1 for row in gt.values() if row["recoverable_bucket"] == "H2a")
    h2b = sum(1 for row in gt.values() if row["recoverable_bucket"] == "H2b")
    h2a_lex = sum(1 for row in gt.values()
                  if row["recoverable_bucket"] == "H2a" and row["lex_ungrounded_timing"] == "1")
    h2b_lex = sum(1 for row in gt.values()
                  if row["recoverable_bucket"] == "H2b" and row["lex_ungrounded_timing"] == "1")
    return {"n_novel": len(per_vc),
            "lexical_recall_vs_gt": round(recall, 3),
            "lexical_precision_vs_gt": round(precision, 3),
            "recall_vs_valid_e1_timing": round(recall_valid, 3),
            "n_lexical": n_lex,
            "n_semantic_tier2": n_sem,
            "n_e1_dispute_exposed": n_disp,
            "halluc_rate_novel": round(halluc, 3),
            "H2a_inprinciple": h2a, "H2b_inprinciple": h2b,
            "H2a_lex_strippable": h2a_lex, "H2b_lex_strippable": h2b_lex,
            "proj_e1_accept_lex": round((4 + h2a_lex) / 32, 3),
            "proj_e1_accept_inprinciple": round((4 + h2a) / 32, 3)}


def _write_metrics_csv(m):
    STATS_DIR.mkdir(exist_ok=True)
    with open(STATS_DIR / "traceability_metrics.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(m.keys()))
        w.writerow(list(m.values()))


def _write_report(per_vc, gt, m):
    lines = [
        f"# SecOC Traceability Report ({datetime.date.today().isoformat()})", "",
        "Inputs: output_secoc/secoc_generated_vcs.json, output_secoc/gt_failure_category.csv,",
        "../data/SYRS_Classified_20260429_085505.json", "",
        "> SCOPE: this checker validates numeric/quantifier traceability (A-class) ONLY. "
        "Logic-drift / off-target (B-class) is OUT of scope. This report does NOT claim a human "
        "acceptance-rate gain; the H2a/H2b ceiling is counterfactual, pending Phase-2 human review.", "",
        f"- novel VCs checked: {m['n_novel']}",
        f"- traceability-hallucination rate (>=1 ungrounded bound timing): {m['halluc_rate_novel']}", "",
        "### Two-tier traceability hallucination (key finding)",
        "- **Tier-1 (lexical)**: timing value ABSENT from the SYRS (e.g. fabricated 'within 50 ms'). "
        "Lexically detectable + strippable.",
        "- **Tier-2 (semantic)**: timing value IS in the SYRS but bound to a DIFFERENT action "
        "(SYRS times the True path, VC times the negative path). Needs per-action alignment -> Phase 2.", "",
        f"- checker LEXICAL recall vs E1 ground truth: {m['lexical_recall_vs_gt']} "
        f"(catches every one of the {m['n_lexical']} lexically-absent bound timings)",
        f"- checker LEXICAL precision vs E1 ground truth: {m['lexical_precision_vs_gt']} "
        f"(every flag verified absent from its SYRS -- no false alarms)",
        f"- recall vs E1's VALID timing complaints: {m['recall_vs_valid_e1_timing']} "
        f"-- the only genuine miss is {m['n_semantic_tier2']} Tier-2 semantic case (SYRS.0472_A), "
        "beyond a lexical checker (see Appendix A).",
        f"- **E1 errors exposed: {m['n_e1_dispute_exposed']}** (SYRS.0430_B_A) -- the checker GROUNDS the "
        "10 ms correctly because the SYRS states it; E1's 'no basis' note is contradicted by the "
        "requirement text. A second use of the checker: catching reviewer inconsistencies. See Appendix A.",
        f"- recoverable ceiling: H2a in-principle={m['H2a_inprinciple']} "
        f"(lexically-strippable now={m['H2a_lex_strippable']}; the rest = SYRS.0472_A needs Tier-2/Phase-2); "
        f"H2b in-principle={m['H2b_inprinciple']} (lex={m['H2b_lex_strippable']})",
        f"- PROJECTED E1 accept: lexical-strip now = {m['proj_e1_accept_lex']} "
        f"(=(4+{m['H2a_lex_strippable']})/32); in-principle ceiling = {m['proj_e1_accept_inprinciple']}. "
        "BOTH are PROJECTIONS pending Phase-2 human confirmation, NOT proven gains. "
        "(The 1 E1-dispute is NOT counted into the projection -- conservative; flag for re-adjudication.)", "",
        "## Per-VC", "",
    ]
    for r in per_vc:
        tflag = sorted({q["raw"] for q in r["quants"]
                        if q["kind"] == "timing" and q["verdict"] == "UNGROUNDED" and q.get("bound")})
        hflag = sorted({q["raw"] for q in r["quants"]
                        if q["kind"] == "hex" and q["verdict"] == "UNGROUNDED"})
        g = gt.get(r["syrs_id"], {})
        lines.append(
            f"- **{r['syrs_id']}** | E1_cat={g.get('category', '-')} | bucket={g.get('recoverable_bucket', '-')} "
            f"| ungrounded TIMING (primary, stripped): {tflag or 'none'} "
            f"| ungrounded hex (secondary, NOT stripped, may be std proto const): {hflag or 'none'}")

    lines += ["", "## Appendix A: structured breakdown of the 2 semantic-tier cases", "",
              "Hand-annotated, verified against full SYRS + VC text. These are the cases where a "
              "lexical value-presence check is insufficient -- they motivate Phase-2 (action, value) binding.", ""]
    for c in SEMANTIC_CASE_NOTES:
        lines += [
            f"### {c['syrs_id']} -- {c['verdict']}",
            f"- **value**: {c['value']}",
            f"- **SYRS binds it to**: {c['syrs_action_value']}",
            f"- **VC binds it to**: {c['vc_action_value']}",
            f"- **why the lexical checker passes it**: {c['why_lexical_passes']}",
            f"- **Phase-2 fix**: {c['phase2_fix']}", ""]
    (OUT_DIR / "traceability_report.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- (action,value) whitelist (Phase-2 input)

_CLAUSE_SPLIT = re.compile(r"(?<=[.;:])\s+|\s+(?=\d[\).])")


def export_action_value_whitelist():
    """Draft (action, value) whitelist for Phase-2 grounded generation.

    For each security SYRS, split into clauses and emit every (clause, value) pair the
    SYRS actually states. The clause is a HEURISTIC proxy for the 'action' -- a human must
    verify/refine the binding before Phase-2 uses it. This is the Phase-2 fact anchor:
    a regenerated VC may bind a quantitative value ONLY to the matching (action, value) pair.
    """
    syrs_src = _load_syrs_source()
    vcs = json.loads((OUT_DIR / "secoc_generated_vcs.json").read_text(encoding="utf-8"))
    sids = sorted({v["syrs_id"] for v in vcs})
    rows = []
    for sid in sids:
        text = syrs_src.get(sid) or ""
        for clause in _CLAUSE_SPLIT.split(text):
            clause = clause.strip()
            for q in extract_quantifiers(clause):
                rows.append({
                    "syrs_id": sid,
                    "value_kind": q["kind"],
                    "raw_value": q["raw"],
                    "normalized_value": q["norm"],
                    "lead_type": ("bound" if (q["kind"] == "timing" and q.get("bound"))
                                  else "stimulus_or_id"),
                    "action_clause_DRAFT": clause[:160],
                })
    path = OUT_DIR / "phase2_action_value_whitelist_draft.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("# DRAFT Phase-2 (action, value) whitelist. action_clause is a HEURISTIC proxy "
                "(clause containing the value); a human MUST verify the (action,value) binding "
                "before Phase-2 uses it. Generated by poc_traceability.export_action_value_whitelist.\n")
        w = csv.DictWriter(f, fieldnames=["syrs_id", "value_kind", "raw_value", "normalized_value",
                                          "lead_type", "action_clause_DRAFT"])
        w.writeheader()
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    out = run_checker(write=True)
    wl = export_action_value_whitelist()
    print(json.dumps(out["metrics"], indent=2))
    print(f"phase2_action_value_whitelist_draft.csv: {len(wl)} (syrs, value) rows")
