"""
Ablation experiments for IssueDriven-VC (paper §Ablation / RQ3).

Two ablation conditions, three channels each:

  Abl-ND (No-Distill):
    Skip the LLM distillation step.  Embed raw issue title+body directly.
    Shows the value of [Trigger|Behavior|FaultMode] semantic extraction.

  Abl-LM (LLM-Match, CrUISE-AC style):
    Skip embedding-based matching.  Use LLM binary relevance classification
    to select top-K issues.  Shows the value of our embedding approach.

Usage:
  python poc_ablation.py --condition no-distill --channels A B C
  python poc_ablation.py --condition llm-match  --channels A B C
  python poc_ablation.py --condition all         --channels A B C   # run both
"""

import os, json, time, argparse
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

WORKSPACE = Path(__file__).parent
DATA_DIR   = WORKSPACE.parent / "data"
OUT_DIR    = WORKSPACE / "output_ablation"
OUT_DIR.mkdir(exist_ok=True)

# ── Run metadata logging ──────────────────────────────────────────────────────

LOG_DIR = WORKSPACE / "run_logs"
LOG_DIR.mkdir(exist_ok=True)

# Approximate cost per 1M tokens (input/output) in USD.
_COST_PER_1M: dict[str, tuple[float, float]] = {
    "qwen-max":    (2.40, 9.60),
    "qwen-plus":   (0.40, 1.20),
    "qwen-turbo":  (0.05, 0.15),
    "deepseek-chat": (0.27, 1.10),
}
_DEFAULT_COST = (1.00, 3.00)


def log_run_metadata(log_dir: Path, entry: dict) -> None:
    """Append one metadata entry to run_logs/run_metadata_YYYYMMDD.jsonl."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_path = log_dir / f"run_metadata_{date_str}.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _cost_usd(model: str, prompt_tok: int, completion_tok: int) -> float:
    in_rate, out_rate = _COST_PER_1M.get(model, _DEFAULT_COST)
    return round((prompt_tok * in_rate + completion_tok * out_rate) / 1_000_000, 6)

TOP_K = 5
TARGET_CATEGORIES_A = {"Diagnostics_DCM", "Communication_Stack",
                        "Diagnostics_DEM", "Diagnostic_Services"}
TARGET_CATEGORIES_B = {"Body_Control", "IO_HMI", "Functional_Safety", "System_State"}
TARGET_CATEGORIES_C = {"Cybersecurity", "Diagnostic_Services", "Diagnostics_DCM"}


# ── LLM client ────────────────────────────────────────────────────────────────

def _client():
    from openai import OpenAI
    return OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ.get("DASHSCOPE_BASE_URL",
                                "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )


# ── Load data helpers ─────────────────────────────────────────────────────────

def load_syrs(categories: set) -> list[dict]:
    with open(DATA_DIR / "SYRS_Classified_20260429_085505.json", encoding="utf-8") as f:
        raw = json.load(f)
    with open(DATA_DIR / "golden_vc_text_20260429_091653.json", encoding="utf-8") as f:
        golden = json.load(f)
    result = []
    for qual_key, subcats in raw.items():
        for cat, items in subcats.items():
            if cat not in categories:
                continue
            if isinstance(items, list):
                for item in items:
                    result.append({
                        "syrs_id": item["SYRS_ID"],
                        "category": cat,
                        "requirement": item["System_Requirements"],
                        "golden_vc": golden.get(item["SYRS_ID"], ""),
                    })
            elif isinstance(items, dict):
                result.append({
                    "syrs_id": items["SYRS_ID"],
                    "category": cat,
                    "requirement": items["System_Requirements"],
                    "golden_vc": golden.get(items["SYRS_ID"], ""),
                })
    return result


def load_raw_issues_A() -> list[dict]:
    path = WORKSPACE / "cache" / "all_issues.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_raw_issues_B() -> list[dict]:
    path = WORKSPACE / "cache_nhtsa" / "nhtsa_complaints_raw.json"
    if not path.exists():
        raise FileNotFoundError(f"NHTSA cache not found: {path}. Run poc_nhtsa.py --step fetch first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for c in data:
        summary = c.get("summary", "")
        component = c.get("component", "")
        body_parts = []
        if component: body_parts.append(f"Component: {component}")
        if summary:   body_parts.append(summary)
        result.append({
            "id": c.get("odi", c.get("odiNumber", c.get("id", ""))),
            "title": summary[:200] or f"NHTSA complaint {c.get('odi','')}",
            "body": " | ".join(body_parts)[:2000],
            "source": "NHTSA",
        })
    return result


def load_raw_issues_C() -> list[dict]:
    path = WORKSPACE / "cache_cve" / "cve_raw.json"
    if not path.exists():
        raise FileNotFoundError(f"CVE cache not found: {path}. Run poc_cve.py --step fetch first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for c in data:
        desc = c.get("description", c.get("body", ""))
        result.append({
            "id": c.get("cve_id", c.get("id", "")),
            "title": desc[:120] if desc else "CVE",
            "body": desc[:2000],
            "source": "CVE",
        })
    return result


# ── Embedding helpers ─────────────────────────────────────────────────────────

def embed_texts(texts: list[str], batch_size: int = 10,
                cache_path: Path = None) -> list[list[float]]:
    if cache_path and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    client = _client()
    all_emb = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(model="text-embedding-v3", input=batch)
        all_emb.extend([r.embedding for r in resp.data])
        time.sleep(0.2)
    if cache_path:
        cache_path.write_text(json.dumps(all_emb), encoding="utf-8")
    return all_emb


def cosine_top_k(syrs_embs, issue_embs, k=TOP_K):
    import numpy as np
    a = np.array(syrs_embs)
    b = np.array(issue_embs)
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-9
    b /= np.linalg.norm(b, axis=1, keepdims=True) + 1e-9
    sim = a @ b.T
    top_indices = np.argsort(sim, axis=1)[:, ::-1][:, :k]
    top_scores  = np.sort(sim, axis=1)[:, ::-1][:, :k]
    return top_indices, top_scores


# ── LLM relevance classifier (Abl-LM, CrUISE-AC style) ──────────────────────

RELEVANCE_PROMPT = """\
You are a requirements engineer for automotive ECU systems.

Determine whether the following issue/complaint is relevant to the given ECU requirement.
"Relevant" means the issue describes a failure mode, edge case, or behavior that could
constitute a missing verification condition for this requirement.

Requirement: {syrs_text}

Issue title: {title}
Issue description: {body}

Answer with ONLY a JSON object: {{"relevant": true}} or {{"relevant": false}}
"""


def llm_classify_relevance(syrs_text: str, issues: list[dict],
                            cache_path: Path = None) -> list[bool]:
    cache_key = hash((syrs_text[:100], len(issues)))
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if str(cache_key) in cached:
            return cached[str(cache_key)]

    client = _client()
    results = []
    for iss in issues:
        prompt = RELEVANCE_PROMPT.format(
            syrs_text=syrs_text[:500],
            title=iss.get("title", "")[:150],
            body=iss.get("body", "")[:600],
        )
        _model_cls = "qwen-plus"
        t_start = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=_model_cls,           # cheaper model for binary classification
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=20,
                response_format={"type": "json_object"},
            )
            _latency_ms = round((time.perf_counter() - t_start) * 1000)
            obj = json.loads(resp.choices[0].message.content)
            results.append(bool(obj.get("relevant", False)))
            _ptok = resp.usage.prompt_tokens if resp.usage else 0
            _ctok = resp.usage.completion_tokens if resp.usage else 0
            log_run_metadata(LOG_DIR, {
                "timestamp":         datetime.now(timezone.utc).isoformat(),
                "script":            "poc_ablation",
                "model":             _model_cls,
                "channel":           "classify",
                "syrs_id":           "",
                "tokens_prompt":     _ptok,
                "tokens_completion": _ctok,
                "tokens_total":      (_ptok + _ctok),
                "latency_ms":        _latency_ms,
                "cost_usd_estimate": _cost_usd(_model_cls, _ptok, _ctok),
            })
        except Exception as e:
            results.append(False)
        time.sleep(0.1)

    if cache_path:
        existing = {}
        if cache_path.exists():
            existing = json.loads(cache_path.read_text(encoding="utf-8"))
        existing[str(cache_key)] = results
        cache_path.write_text(json.dumps(existing), encoding="utf-8")
    return results


# ── VC generation (same prompt as main pipeline) ─────────────────────────────

GENERATE_PROMPT = """\
You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

Your task: generate MISSING verification conditions for an automotive ECU system requirement.
"Missing" means test scenarios NOT already covered by the existing golden VCs.

The insight comes from real-world issues/complaints/vulnerabilities in automotive software.
These reveal corner cases that spec authors typically overlook.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (already covered — DO NOT repeat these):
{golden_vcs}

Related issues from automotive software (potential missing corner cases):
{issues_context}

Generate 1-2 additional VCs in YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.NEW.1
    Title: <concise test title>
    Method:
      Type: Dynamic
      Technique: <e.g. Boundary Value Analysis, Fault Injection>
    Pass_Fail_Criteria:
      Pass: |
        1. <step>
        2. <step>
        3. Verify: <expected outcome>
      Fail: |
        - <failure condition>
    Issue_Source: <issue id that inspired this VC>

Only generate VCs that are genuinely novel (not in golden VCs) and testable at ECU level.
If no useful novel VC can be identified, output: NO_NOVEL_VC_FOUND
"""


def generate_vc(match: dict, condition_tag: str) -> dict:
    client = _client()
    # Build issue context depending on what's available
    ctx_items = []
    for iss in match["top_issues"]:
        ctx_items.append(
            f"[{iss.get('source', iss.get('repo', ''))}#{iss.get('issue_id', iss.get('id', ''))}]"
            f" {iss.get('title', '')}\n"
            f"  {iss.get('body_excerpt', iss.get('distilled_text', ''))[:300]}"
        )
    issues_context = "\n".join(ctx_items) or "(no issues matched)"
    golden_summary = match.get("golden_vc", "")[:800] or "(none)"

    prompt = GENERATE_PROMPT.format(
        syrs_text=match["requirement"],
        golden_vcs=golden_summary,
        issues_context=issues_context,
        vc_id_prefix=f"VC_{match['syrs_id']}.{condition_tag}",
    )
    _model_gen = "qwen-max"
    t_start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=_model_gen,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800,
        )
        _latency_ms = round((time.perf_counter() - t_start) * 1000)
        _ptok = resp.usage.prompt_tokens if resp.usage else 0
        _ctok = resp.usage.completion_tokens if resp.usage else 0
        log_run_metadata(LOG_DIR, {
            "timestamp":         datetime.now(timezone.utc).isoformat(),
            "script":            "poc_ablation",
            "model":             _model_gen,
            "channel":           condition_tag,
            "syrs_id":           match["syrs_id"],
            "tokens_prompt":     _ptok,
            "tokens_completion": _ctok,
            "tokens_total":      (_ptok + _ctok),
            "latency_ms":        _latency_ms,
            "cost_usd_estimate": _cost_usd(_model_gen, _ptok, _ctok),
        })
        return {**match, "generated_vc": resp.choices[0].message.content.strip(),
                "ablation_condition": condition_tag}
    except Exception as e:
        return {**match, "generated_vc": f"ERROR: {e}",
                "ablation_condition": condition_tag}


# ── No-Distill pipeline ───────────────────────────────────────────────────────

def run_no_distill(channel: str, syrs_list: list, raw_issues: list,
                   out_path: Path):
    print(f"\n[Abl-ND] Channel {channel}: {len(syrs_list)} SYRS × {len(raw_issues)} raw issues")

    # Load cached SYRS embeddings (reuse from main pipeline if same categories)
    syrs_cache = WORKSPACE / "cache" / "syrs_embeddings.json"
    syrs_texts = [s["requirement"] for s in syrs_list]
    syrs_embs  = embed_texts(syrs_texts, cache_path=syrs_cache if syrs_cache.exists() else None)

    # Embed raw issue text (title + body[:500])
    issue_texts = [f"{iss.get('title','')}. {iss.get('body','')[:500]}" for iss in raw_issues]
    issue_emb_cache = OUT_DIR / f"nodistill_ch{channel}_issue_embs.json"
    print(f"  Embedding {len(raw_issues)} raw issues...")
    issue_embs = embed_texts(issue_texts, cache_path=issue_emb_cache)

    top_idx, top_scores = cosine_top_k(syrs_embs, issue_embs)

    # Load existing output (incremental)
    results = []
    if out_path.exists():
        results = json.loads(out_path.read_text(encoding="utf-8"))
    done_ids = {r["syrs_id"] for r in results}

    for i, syrs in enumerate(syrs_list):
        if syrs["syrs_id"] in done_ids:
            continue
        top_issues = []
        for j, score in zip(top_idx[i], top_scores[i]):
            iss = raw_issues[j]
            top_issues.append({
                "id": iss.get("id", j),
                "title": iss.get("title", ""),
                "body_excerpt": iss.get("body", "")[:300],
                "source": iss.get("source", iss.get("repo", "raw")),
                "similarity": float(score),
            })
        match = {
            "syrs_id": syrs["syrs_id"],
            "category": syrs["category"],
            "requirement": syrs["requirement"],
            "golden_vc": syrs["golden_vc"],
            "top_issues": top_issues,
        }
        result = generate_vc(match, f"ND-Ch{channel}")
        results.append(result)
        done_ids.add(syrs["syrs_id"])
        if len(results) % 10 == 0:
            out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  {len(results)} done...")
        time.sleep(0.3)

    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    novel = sum(1 for r in results if "NO_NOVEL_VC_FOUND" not in r.get("generated_vc", ""))
    print(f"  Done: {novel}/{len(results)} novel VCs → {out_path.name}")
    return results


# ── LLM-Match pipeline (CrUISE-AC style) ─────────────────────────────────────

def run_llm_match(channel: str, syrs_list: list, raw_issues: list,
                  out_path: Path, max_issues: int = 50, max_syrs: int = 0):
    """
    Abl-LM: LLM binary relevance classification (CrUISE-AC style).

    max_issues: cap the issue pool per SYRS for feasibility (default 50).
                Randomly samples from raw_issues if len > max_issues.
                Set 0 to use all (warning: may take hours for large pools).
    max_syrs:   cap the number of SYRS items processed (0 = all).
    """
    import random
    random.seed(42)

    # Subsample issues pool once for all SYRS (reproducible, same pool per run)
    if max_issues and len(raw_issues) > max_issues:
        sampled_issues = random.sample(raw_issues, max_issues)
        print(f"\n[Abl-LM] Channel {channel}: {len(syrs_list)} SYRS × {max_issues} sampled issues "
              f"(from {len(raw_issues)} total, seed=42)")
    else:
        sampled_issues = raw_issues
        print(f"\n[Abl-LM] Channel {channel}: {len(syrs_list)} SYRS × {len(raw_issues)} raw issues")

    if max_syrs and len(syrs_list) > max_syrs:
        syrs_list = syrs_list[:max_syrs]
        print(f"  Capping SYRS to first {max_syrs} items.")

    print(f"  Using qwen-plus for binary relevance classification (CrUISE-AC style)")

    # Load existing output (incremental)
    results = []
    if out_path.exists():
        results = json.loads(out_path.read_text(encoding="utf-8"))
    done_ids = {r["syrs_id"] for r in results}

    relevance_cache = OUT_DIR / f"llmmatch_ch{channel}_relevance_cache.json"

    for i, syrs in enumerate(syrs_list):
        if syrs["syrs_id"] in done_ids:
            continue

        # Classify sampled issues for this SYRS (LLM binary relevance)
        print(f"  [{i+1}/{len(syrs_list)}] {syrs['syrs_id']}: classifying {len(sampled_issues)} issues...")
        relevant_flags = llm_classify_relevance(
            syrs["requirement"], sampled_issues, cache_path=relevance_cache
        )

        # Collect relevant issues (up to TOP_K)
        relevant_issues = [
            sampled_issues[j] for j, flag in enumerate(relevant_flags) if flag
        ][:TOP_K]

        if not relevant_issues:
            # Fall back to first TOP_K issues if nothing relevant found
            relevant_issues = sampled_issues[:TOP_K]

        top_issues = [{
            "id": iss.get("id", j),
            "title": iss.get("title", ""),
            "body_excerpt": iss.get("body", "")[:300],
            "source": iss.get("source", iss.get("repo", "raw")),
            "llm_relevant": True,
        } for j, iss in enumerate(relevant_issues)]

        match = {
            "syrs_id": syrs["syrs_id"],
            "category": syrs["category"],
            "requirement": syrs["requirement"],
            "golden_vc": syrs["golden_vc"],
            "top_issues": top_issues,
        }
        result = generate_vc(match, f"LM-Ch{channel}")
        results.append(result)
        done_ids.add(syrs["syrs_id"])
        if len(results) % 5 == 0:
            out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"    {len(results)} done...")
        time.sleep(0.3)

    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    novel = sum(1 for r in results if "NO_NOVEL_VC_FOUND" not in r.get("generated_vc", ""))
    print(f"  Done: {novel}/{len(results)} novel VCs → {out_path.name}")
    return results


# ── Novel rate proxy metric ────────────────────────────────────────────────────

def compute_novel_rate(results: list) -> dict:
    total = len(results)
    novel = sum(1 for r in results if "NO_NOVEL_VC_FOUND" not in r.get("generated_vc", ""))
    return {"total": total, "novel": novel, "novel_rate": round(novel / total, 4) if total else 0}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--condition", choices=["no-distill", "llm-match", "all"],
                   default="all")
    p.add_argument("--channels", nargs="+", choices=["A", "B", "C"],
                   default=["A", "B", "C"])
    p.add_argument("--max-issues", type=int, default=50,
                   help="[Abl-LM] Max issues to classify per SYRS (0=all, default=50). "
                        "Larger pools can take hours; 50 gives a fair sample.")
    p.add_argument("--max-syrs", type=int, default=0,
                   help="[Abl-LM] Max SYRS items to process per channel (0=all).")
    args = p.parse_args()

    conditions = (["no-distill", "llm-match"] if args.condition == "all"
                  else [args.condition])

    channel_configs = {
        "A": (load_syrs(TARGET_CATEGORIES_A), load_raw_issues_A),
        "B": (load_syrs(TARGET_CATEGORIES_B), load_raw_issues_B),
        "C": (load_syrs(TARGET_CATEGORIES_C), load_raw_issues_C),
    }

    summary = {}

    for cond in conditions:
        for ch in args.channels:
            syrs_list, load_issues_fn = channel_configs[ch]
            tag = "ND" if cond == "no-distill" else "LM"
            out_path = OUT_DIR / f"abl_{tag.lower()}_ch{ch}_generated_vcs.json"

            try:
                raw_issues = load_issues_fn()
            except FileNotFoundError as e:
                print(f"[skip] {e}")
                continue

            if cond == "no-distill":
                results = run_no_distill(ch, syrs_list, raw_issues, out_path)
            else:
                results = run_llm_match(ch, syrs_list, raw_issues, out_path,
                                        max_issues=args.max_issues,
                                        max_syrs=args.max_syrs)

            nr = compute_novel_rate(results)
            key = f"{tag}-Ch{ch}"
            summary[key] = nr
            print(f"  {key}: novel_rate={nr['novel_rate']:.3f} ({nr['novel']}/{nr['total']})")

    # Print comparison table
    if summary:
        print(f"\n{'='*55}")
        print(f"{'Condition':<15} {'Total':>7} {'Novel':>7} {'Novel_Rate':>12}")
        print(f"{'='*55}")
        for k, v in summary.items():
            print(f"{k:<15} {v['total']:>7} {v['novel']:>7} {v['novel_rate']:>12.3f}")

        # Save proxy metric summary
        summary_path = OUT_DIR / "ablation_novel_rate_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nProxy metric summary → {summary_path}")


if __name__ == "__main__":
    main()
