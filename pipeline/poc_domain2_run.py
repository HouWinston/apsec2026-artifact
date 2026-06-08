"""
Domain 2 (Diagnostics SYRS) — IssueDriven-VC Pipeline Run
==========================================================
Runs Channel A (GitHub issues → Diagnostics SYRS) for Domain 2.

Domain 2 covers UDS protocol + DTC management requirements:
  - Diagnostics_DCM (35 items): UDS service handling
  - Diagnostics_DEM (35 items): DTC/fault management
  - Diagnostic_Services (10 items): NRC, session management
  - Diagnostics (3 items) + Diagnostics_Communication (2 items)

This script reuses:
  - cache/distilled_issues.json   — already-distilled GitHub issues
  - cache/issue_embeddings.json   — pre-computed 1024-dim embeddings

New work:
  1. Embed Domain 2 SYRS texts (text-embedding-v3 via DashScope)
  2. Match each SYRS to top-5 distilled issues by cosine similarity
  3. Generate missing VCs using qwen-max

Output: output_domain2/
  - domain2_syrs_embeddings.json  — cached SYRS embeddings
  - domain2_matches.json          — per-SYRS top-5 issue matches
  - chA_generated_vcs.json        — final generated VCs (full run)

Usage:
  python poc_domain2_run.py                         # full 85 SYRS
  python poc_domain2_run.py --limit 20              # test run: first 20 SYRS
  python poc_domain2_run.py --workers 4             # API concurrency
  python poc_domain2_run.py --step match            # only embed+match
  python poc_domain2_run.py --step generate         # only generate (needs match done)
"""

import os
import json
import time
import argparse
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

# ── Environment ───────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent.parent / ".env")

WORKSPACE   = Path(__file__).parent
CACHE_DIR   = WORKSPACE / "cache"
OUT_DIR     = WORKSPACE / "output_domain2"
LOG_DIR     = WORKSPACE / "run_logs"

OUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

TOP_K = 5

# ── DashScope client ──────────────────────────────────────────────────────────

def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ.get(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )

# ── Cost logging ──────────────────────────────────────────────────────────────

_COST_PER_1M: dict[str, tuple[float, float]] = {
    "qwen-max":    (2.40, 9.60),
    "qwen-plus":   (0.40, 1.20),
    "deepseek-chat": (0.27, 1.10),
}
_DEFAULT_COST = (1.00, 3.00)

_log_lock = threading.Lock()


def _cost_usd(model: str, p_tok: int, c_tok: int) -> float:
    in_r, out_r = _COST_PER_1M.get(model, _DEFAULT_COST)
    return round((p_tok * in_r + c_tok * out_r) / 1_000_000, 6)


def _log(entry: dict) -> None:
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_path = LOG_DIR / f"run_metadata_{date_str}.jsonl"
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _log_lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)

# ── Step 0: Load Domain 2 SYRS ────────────────────────────────────────────────

def load_domain2_syrs(limit: int | None = None) -> list[dict]:
    """Load domain2_diagnostics_syrs.json and normalise field names."""
    raw = json.loads(
        (WORKSPACE / "data" / "domain2_diagnostics_syrs.json").read_text(encoding="utf-8")
    )
    syrs_list = []
    for item in raw:
        syrs_list.append({
            "syrs_id":     item["SYRS_ID"],
            "category":    item.get("category", "Diagnostics"),
            "requirement": item["System_Requirements"],
            "golden_vc":   item.get("golden_vc", ""),   # domain2 has no golden VCs
        })
    if limit:
        syrs_list = syrs_list[:limit]
    print(f"[load] Domain 2 SYRS: {len(syrs_list)} items")
    cats: dict[str, int] = {}
    for s in syrs_list:
        cats[s["category"]] = cats.get(s["category"], 0) + 1
    print(f"[load] Categories: {cats}")
    return syrs_list


# ── Step 1: Embed SYRS ────────────────────────────────────────────────────────

def embed_texts(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    client = _client()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        for attempt in range(3):
            try:
                resp = client.embeddings.create(
                    model="text-embedding-v3",
                    input=batch,
                )
                all_embeddings.extend([r.embedding for r in resp.data])
                break
            except Exception as exc:
                print(f"  [warn] embed batch {i//batch_size} attempt {attempt+1}: {exc}")
                if attempt < 2:
                    time.sleep(5)
                else:
                    raise
        time.sleep(0.3)
    return all_embeddings


def step_match(syrs_list: list[dict]) -> list[dict]:
    """Embed SYRS, match to distilled issues, save domain2_matches.json."""

    # Load pre-computed issue embeddings
    issue_embs = np.array(
        json.loads((CACHE_DIR / "issue_embeddings.json").read_text(encoding="utf-8"))
    )
    distilled = json.loads(
        (CACHE_DIR / "distilled_issues.json").read_text(encoding="utf-8")
    )
    valid_issues = [d for d in distilled if d["distilled"].get("trigger")]
    assert len(valid_issues) == len(issue_embs), (
        f"Issue count mismatch: {len(valid_issues)} distilled vs {len(issue_embs)} embeddings"
    )
    print(f"[match] Loaded {len(valid_issues)} distilled issues with embeddings")

    # Embed Domain 2 SYRS (with caching)
    emb_cache = OUT_DIR / "domain2_syrs_embeddings.json"
    if emb_cache.exists():
        syrs_embs = np.array(json.loads(emb_cache.read_text(encoding="utf-8")))
        print(f"[match] Loaded SYRS embeddings from cache ({len(syrs_embs)} vectors)")
    else:
        syrs_texts = [s["requirement"] for s in syrs_list]
        print(f"[match] Embedding {len(syrs_texts)} SYRS texts via text-embedding-v3...")
        raw_embs = embed_texts(syrs_texts)
        emb_cache.write_text(json.dumps(raw_embs, ensure_ascii=False), encoding="utf-8")
        syrs_embs = np.array(raw_embs)
        print(f"[match] Embeddings computed and cached → {emb_cache}")

    # Cosine similarity
    syrs_n = syrs_embs / (np.linalg.norm(syrs_embs, axis=1, keepdims=True) + 1e-9)
    issue_n = issue_embs / (np.linalg.norm(issue_embs, axis=1, keepdims=True) + 1e-9)
    sim_matrix = syrs_n @ issue_n.T   # (N_syrs, N_issues)

    matches: list[dict] = []
    for i, syrs in enumerate(syrs_list):
        scores = sim_matrix[i]
        top_k_idx = np.argsort(scores)[::-1][:TOP_K]
        top_issues = [
            {
                "repo":       valid_issues[j]["repo"],
                "issue_id":   valid_issues[j]["id"],
                "title":      valid_issues[j]["title"],
                "distilled":  valid_issues[j]["distilled"],
                "similarity": float(scores[j]),
            }
            for j in top_k_idx
        ]
        matches.append({
            "syrs_id":     syrs["syrs_id"],
            "category":    syrs["category"],
            "requirement": syrs["requirement"],
            "golden_vc":   syrs["golden_vc"],
            "top_issues":  top_issues,
        })

    out_path = OUT_DIR / "domain2_matches.json"
    out_path.write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[match] Saved {len(matches)} matches → {out_path}")

    # Print sample for sanity check
    print("\n=== Sample Matches (first 3 SYRS) ===")
    for m in matches[:3]:
        print(f"\n[{m['syrs_id']}] ({m['category']}) {m['requirement'][:100]}")
        for iss in m["top_issues"][:2]:
            print(f"  sim={iss['similarity']:.3f} [{iss['repo']}#{iss['issue_id']}] {iss['title'][:80]}")
            print(f"    trigger: {iss['distilled'].get('trigger', '')[:80]}")

    return matches


# ── Step 2: Generate VCs ──────────────────────────────────────────────────────

GENERATE_PROMPT = """You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

Your task: generate MISSING verification conditions for an automotive ECU system requirement.
"Missing" means test scenarios NOT already covered by the existing golden VCs.

The insight comes from real-world issues in open-source automotive protocol software (UDS/ISO-TP/CAN).
These issues reveal corner cases that spec authors typically overlook.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (already covered — DO NOT repeat these):
{golden_vcs}

Related issues from automotive protocol software (potential missing corner cases):
{issues_context}

Generate 1-2 additional VCs in this YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.D2.1
    Title: <concise test title>
    Method:
      Type: Dynamic  # or Static
      Technique: <e.g. Boundary Value Analysis, Equivalence Partitioning, Fault Injection>
    Pass_Fail_Criteria:
      Pass: |
        1. <step>
        2. <step>
        3. Verify: <expected outcome>
      Fail: |
        - <condition that constitutes failure>
    Issue_Source: <repo#issue_id that inspired this VC>

Only generate VCs that are:
1. Genuinely testing the SYRS requirement (not testing the protocol library itself)
2. Not redundant with existing golden VCs
3. Inspired by a real failure pattern from the issues above
4. Testable at ECU system integration test level (not unit test)

If no genuinely useful missing VC can be identified from these issues, output:
NO_NOVEL_VC_FOUND
"""


def _build_prompt(match: dict) -> str:
    golden = (match.get("golden_vc") or "")[:800] or "(none — domain 2 has no pre-existing golden VCs)"
    syrs_id = match["syrs_id"]
    items = match.get("top_issues", [])
    ctx = "\n".join([
        f"Issue [{iss['repo']}#{iss['issue_id']}]: {iss['title']}\n"
        f"  Trigger: {iss['distilled'].get('trigger', 'N/A')}\n"
        f"  Behavior: {iss['distilled'].get('behavior', 'N/A')}\n"
        f"  Fault: {iss['distilled'].get('fault_mode', 'N/A')}"
        for iss in items
    ])
    return GENERATE_PROMPT.format(
        syrs_text=match["requirement"],
        golden_vcs=golden,
        issues_context=ctx,
        vc_id_prefix=f"VC_{syrs_id}",
    )


def generate_one(match: dict, run_id: str) -> dict:
    model_name = "qwen-max"
    client = _client()
    prompt = _build_prompt(match)

    generated = None
    prompt_tokens = completion_tokens = 0
    finish_reason = error_msg = None
    attempt = 0
    t_start = time.perf_counter()

    for attempt in range(1, 4):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=800,
            )
            generated = resp.choices[0].message.content.strip()
            finish_reason = resp.choices[0].finish_reason
            if resp.usage:
                prompt_tokens     = resp.usage.prompt_tokens or 0
                completion_tokens = resp.usage.completion_tokens or 0
            error_msg = None
            break
        except Exception as exc:
            error_msg = str(exc)
            if attempt < 3:
                time.sleep(5 * attempt)

    latency_ms = round((time.perf_counter() - t_start) * 1000)
    if generated is None:
        generated = f"ERROR: {error_msg}"

    is_novel = (
        bool(generated)
        and "NO_NOVEL_VC_FOUND" not in generated
        and not generated.startswith("ERROR:")
    )

    items = match.get("top_issues", [])
    sims = [iss.get("similarity", 0.0) for iss in items]

    record = {
        "run_id":          run_id,
        "timestamp_utc":   datetime.now(timezone.utc).isoformat(),
        "channel":         "A",
        "domain":          "domain2_diagnostics",
        "syrs_id":         match["syrs_id"],
        "category":        match.get("category", ""),
        "requirement":     match["requirement"],
        "golden_vc":       match.get("golden_vc", ""),
        "top_issues":      match.get("top_issues", []),
        # model
        "model_name":        model_name,
        "temperature":       0.2,
        # tokens
        "prompt_tokens":     prompt_tokens,
        "completion_tokens": completion_tokens,
        # timing
        "latency_ms":        latency_ms,
        "finish_reason":     finish_reason,
        "attempt_number":    attempt,
        # output
        "generated_vc":      generated,
        "is_novel":          is_novel,
        "output_chars":      len(generated),
        # context metrics
        "top1_sim":          round(max(sims), 4) if sims else 0.0,
        "mean_top5_sim":     round(sum(sims) / len(sims), 4) if sims else 0.0,
        # error
        "error": error_msg,
    }

    _log({
        "timestamp":         record["timestamp_utc"],
        "script":            "poc_domain2_run",
        "model":             model_name,
        "channel":           "A",
        "domain":            "domain2",
        "syrs_id":           match["syrs_id"],
        "tokens_prompt":     prompt_tokens,
        "tokens_completion": completion_tokens,
        "latency_ms":        latency_ms,
        "cost_usd_estimate": _cost_usd(model_name, prompt_tokens, completion_tokens),
    })
    return record


_file_locks: dict[str, threading.Lock] = {}
_lock_meta = threading.Lock()


def _get_file_lock(path: str) -> threading.Lock:
    with _lock_meta:
        if path not in _file_locks:
            _file_locks[path] = threading.Lock()
        return _file_locks[path]


def append_jsonl(path: Path, record: dict) -> None:
    lock = _get_file_lock(str(path))
    with lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_done_ids(path: Path) -> set:
    if not path.exists():
        return set()
    done: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)["syrs_id"])
                except Exception:
                    pass
    return done


def step_generate(matches: list[dict], workers: int, run_id: str) -> list[dict]:
    """Generate VCs for all matches; resume from existing output."""
    out_file = OUT_DIR / "chA_generated_vcs.jsonl"
    done_ids = load_done_ids(out_file)
    todo = [m for m in matches if m["syrs_id"] not in done_ids]
    print(f"[generate] {len(todo)} todo / {len(matches)} total (resume: {len(done_ids)} done)")

    if not todo:
        print("[generate] All done, skipping.")
        return []

    results: list[dict] = []
    done = novel = errors = 0

    def task(match: dict) -> dict:
        rec = generate_one(match, run_id)
        append_jsonl(out_file, rec)
        return rec

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(task, m): m["syrs_id"] for m in todo}
        for fut in as_completed(futures):
            syrs_id = futures[fut]
            done += 1
            try:
                rec = fut.result()
                results.append(rec)
                if rec.get("is_novel"):
                    novel += 1
                if rec.get("error"):
                    errors += 1
            except Exception as exc:
                print(f"  [warn] task {syrs_id} failed: {exc}")
                errors += 1
            if done % 10 == 0 or done == len(todo):
                pct = novel / done * 100 if done else 0
                print(f"  [generate] {done}/{len(todo)} | novel={novel}({pct:.0f}%) | err={errors}")

    print(f"[generate] DONE: {done} processed, {novel} novel VCs, {errors} errors")
    return results


# ── Consolidate JSONL → JSON ──────────────────────────────────────────────────

def consolidate_output() -> list[dict]:
    """Read chA_generated_vcs.jsonl → chA_generated_vcs.json."""
    jsonl_path = OUT_DIR / "chA_generated_vcs.jsonl"
    json_path  = OUT_DIR / "chA_generated_vcs.json"

    if not jsonl_path.exists():
        print("[consolidate] No JSONL file found.")
        return []

    records: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[consolidate] {len(records)} records → {json_path}")
    return records


# ── Summary + Samples ─────────────────────────────────────────────────────────

def print_summary(records: list[dict]) -> None:
    if not records:
        print("[summary] No records to summarise.")
        return

    total   = len(records)
    novel   = sum(1 for r in records if r.get("is_novel"))
    errors  = sum(1 for r in records if r.get("error"))
    cats: dict[str, dict] = {}
    for r in records:
        c = r.get("category", "unknown")
        if c not in cats:
            cats[c] = {"total": 0, "novel": 0}
        cats[c]["total"] += 1
        if r.get("is_novel"):
            cats[c]["novel"] += 1

    print("\n" + "=" * 60)
    print("DOMAIN 2 PIPELINE SUMMARY")
    print("=" * 60)
    print(f"  Total SYRS processed : {total}")
    print(f"  Novel VCs generated  : {novel} ({novel/total*100:.1f}%)")
    print(f"  NO_NOVEL_VC_FOUND    : {total - novel - errors}")
    print(f"  Errors               : {errors}")
    print()
    print("  By category:")
    for cat, s in sorted(cats.items()):
        pct = s["novel"] / s["total"] * 100 if s["total"] else 0
        print(f"    {cat:30s}  {s['novel']:3d}/{s['total']:3d}  ({pct:.0f}%)")

    # Mean similarity
    sims = [r.get("top1_sim", 0.0) for r in records if r.get("top1_sim") is not None]
    mean_sim = sum(sims) / len(sims) if sims else 0.0
    print(f"\n  Mean top-1 issue similarity: {mean_sim:.4f}")

    # Token cost estimate
    total_p = sum(r.get("prompt_tokens", 0) for r in records)
    total_c = sum(r.get("completion_tokens", 0) for r in records)
    cost = _cost_usd("qwen-max", total_p, total_c)
    print(f"  Total tokens (prompt/completion): {total_p:,} / {total_c:,}")
    print(f"  Estimated cost: ${cost:.4f} USD")

    # Sample 3 novel VCs
    novel_recs = [r for r in records if r.get("is_novel")]
    if novel_recs:
        # pick spread across categories
        sample_indices = [0, len(novel_recs) // 2, len(novel_recs) - 1]
        print("\n" + "=" * 60)
        print("SAMPLE GENERATED VCs (3 examples)")
        print("=" * 60)
        for idx in sample_indices:
            r = novel_recs[idx]
            print(f"\n--- [{r['syrs_id']}] ({r['category']}) ---")
            print(f"SYRS: {r['requirement'][:200]}")
            top1 = r["top_issues"][0] if r.get("top_issues") else {}
            if top1:
                print(f"Top issue: [{top1['repo']}#{top1['issue_id']}] "
                      f"{top1['title']} (sim={top1.get('similarity', 0):.3f})")
            print(f"Generated VC:\n{r['generated_vc'][:600]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run IssueDriven-VC pipeline on Domain 2 (Diagnostics SYRS)"
    )
    parser.add_argument("--step", choices=["match", "generate", "all"], default="all",
                        help="Pipeline step to run (default: all)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to first N SYRS (for testing)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Concurrent API calls for generation")
    args = parser.parse_args()

    # Validate API key
    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("[ERROR] DASHSCOPE_API_KEY not set. Check your .env file.")
        return

    run_id = uuid.uuid4().hex[:12]
    print(f"=== Domain 2 Run {run_id} ===")
    print(f"Step    : {args.step}")
    print(f"Limit   : {args.limit or 'all 85'}")
    print(f"Workers : {args.workers}")
    print()

    syrs_list = load_domain2_syrs(limit=args.limit)

    if args.step in ("match", "all"):
        matches = step_match(syrs_list)
    else:
        matches_path = OUT_DIR / "domain2_matches.json"
        if not matches_path.exists():
            print(f"[ERROR] {matches_path} not found. Run --step match first.")
            return
        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        print(f"[load] Loaded {len(matches)} existing matches from {matches_path}")

    if args.step in ("generate", "all"):
        step_generate(matches, workers=args.workers, run_id=run_id)

    # Always consolidate and summarise at the end
    records = consolidate_output()
    print_summary(records)
    print(f"\nOutputs in: {OUT_DIR}/")


if __name__ == "__main__":
    main()
