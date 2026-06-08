"""
Extract token/cost summary from run_logs/*.jsonl
Outputs a summary table and structured data for paper §4.
"""
import json
from pathlib import Path
from collections import defaultdict

LOG_DIR = Path(__file__).parent / "run_logs"
log_files = sorted(LOG_DIR.glob("run_metadata_*.jsonl"))

print(f"Log files found: {[f.name for f in log_files]}\n")

# Accumulate data keyed by (script, model, channel)
stats = defaultdict(lambda: {
    "n_calls": 0,
    "tokens_prompt": 0,
    "tokens_completion": 0,
    "tokens_total": 0,
    "cost_usd": 0.0,
})

all_entries = []
parse_errors = 0

for lf in log_files:
    with open(lf, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                all_entries.append(rec)
            except json.JSONDecodeError as e:
                parse_errors += 1
                if parse_errors <= 5:
                    print(f"  [parse error] {lf.name}:{lineno}: {e}")

print(f"Total entries parsed: {len(all_entries)}  (parse errors: {parse_errors})\n")

# Show unique field keys present
sample_keys = set()
for e in all_entries[:50]:
    sample_keys.update(e.keys())
print(f"Fields in records: {sorted(sample_keys)}\n")

# Show unique (script, model, channel) combos
combos = set()
for e in all_entries:
    combos.add((e.get("script",""), e.get("model",""), e.get("channel","")))
print(f"Unique (script, model, channel) combos ({len(combos)} total):")
for c in sorted(combos):
    print(f"  {c}")
print()

# Accumulate
for e in all_entries:
    key = (e.get("script",""), e.get("model",""), e.get("channel",""))
    s = stats[key]
    s["n_calls"] += 1
    s["tokens_prompt"]     += e.get("tokens_prompt", 0) or 0
    s["tokens_completion"] += e.get("tokens_completion", 0) or 0
    s["tokens_total"]      += e.get("tokens_total", 0) or 0
    s["cost_usd"]          += e.get("cost_usd_estimate", 0.0) or 0.0

# ── Print detailed table ──────────────────────────────────────────────────────
print(f"{'Script':<20} {'Model':<20} {'Channel':<12} {'Calls':>6} {'Tok-In':>10} {'Tok-Out':>10} {'Tok-Total':>10} {'Cost-USD':>10}")
print("-" * 100)

grand_cost = 0.0
grand_in = 0
grand_out = 0

for key in sorted(stats.keys()):
    s = stats[key]
    script, model, channel = key
    print(f"{script:<20} {model:<20} {channel:<12} {s['n_calls']:>6} "
          f"{s['tokens_prompt']:>10,} {s['tokens_completion']:>10,} "
          f"{s['tokens_total']:>10,} {s['cost_usd']:>10.4f}")
    grand_cost += s["cost_usd"]
    grand_in   += s["tokens_prompt"]
    grand_out  += s["tokens_completion"]

print("-" * 100)
print(f"{'GRAND TOTAL':<53} {grand_in:>10,} {grand_out:>10,} {grand_in+grand_out:>10,} {grand_cost:>10.4f}")

# ── Stage-level summary for paper table ──────────────────────────────────────
print("\n\n=== PAPER TABLE: Stage × Channel ===\n")

# Map (script, channel) → stage label
stage_map = {
    ("poc_pipeline",   "A"): "S2-Distill / A",
    ("poc_sensitivity","A"): "S4-Generate / A",
    ("poc_sensitivity","B"): "S4-Generate / B",
    ("poc_sensitivity","C"): "S4-Generate / C",
    ("poc_ablation",   "classify"): "Abl-LM Classify",
    ("poc_ablation",   "ND-ChA"): "Abl-ND Generate / A",
    ("poc_ablation",   "ND-ChB"): "Abl-ND Generate / B",
    ("poc_ablation",   "ND-ChC"): "Abl-ND Generate / C",
    ("poc_ablation",   "LM-ChA"): "Abl-LM Generate / A",
    ("poc_ablation",   "LM-ChB"): "Abl-LM Generate / B",
    ("poc_ablation",   "LM-ChC"): "Abl-LM Generate / C",
}

# Aggregate by (script, channel) ignoring model for summary
agg_stage = defaultdict(lambda: {
    "models": set(), "calls": 0, "tok_in": 0, "tok_out": 0, "cost": 0.0
})
for key, s in stats.items():
    script, model, channel = key
    sk = (script, channel)
    agg_stage[sk]["models"].add(model)
    agg_stage[sk]["calls"]  += s["n_calls"]
    agg_stage[sk]["tok_in"] += s["tokens_prompt"]
    agg_stage[sk]["tok_out"] += s["tokens_completion"]
    agg_stage[sk]["cost"]   += s["cost_usd"]

print(f"{'Stage':<30} {'Model(s)':<35} {'Calls':>6} {'Tok-In':>10} {'Tok-Out':>10} {'Cost-USD':>10}")
print("-" * 100)
total_calls = total_in = total_out = total_cost = 0
for sk in sorted(agg_stage.keys()):
    a = agg_stage[sk]
    label = stage_map.get(sk, f"{sk[0]}/{sk[1]}")
    models_str = ",".join(sorted(a["models"]))
    print(f"{label:<30} {models_str:<35} {a['calls']:>6} {a['tok_in']:>10,} {a['tok_out']:>10,} {a['cost']:>10.4f}")
    total_calls += a["calls"]
    total_in    += a["tok_in"]
    total_out   += a["tok_out"]
    total_cost  += a["cost"]

print("-" * 100)
print(f"{'TOTAL':<30} {'':<35} {total_calls:>6} {total_in:>10,} {total_out:>10,} {total_cost:>10.4f}")

# ── Structured output for paper integration ───────────────────────────────────
print("\n\n=== STRUCTURED NUMBERS FOR PAPER ===")
print(f"Total API calls logged : {len(all_entries):,}")
print(f"Total input tokens     : {grand_in:,}")
print(f"Total output tokens    : {grand_out:,}")
print(f"Grand total tokens     : {grand_in+grand_out:,}")
print(f"Total estimated cost   : ${grand_cost:.2f} USD")
print()

# Cost breakdown by primary stage
print("By script:")
script_agg = defaultdict(lambda: {"tok_in":0,"tok_out":0,"cost":0.0})
for key, s in stats.items():
    script_agg[key[0]]["tok_in"]  += s["tokens_prompt"]
    script_agg[key[0]]["tok_out"] += s["tokens_completion"]
    script_agg[key[0]]["cost"]    += s["cost_usd"]
for sc, v in sorted(script_agg.items()):
    print(f"  {sc:<20}: in={v['tok_in']:>10,}  out={v['tok_out']:>10,}  cost=${v['cost']:.4f}")
