"""
LLM Sensitivity Analysis — Field2VC
==========================================
Re-runs VC generation on the same matches with alternative models.

Compares: qwen-max (primary) vs. qwen3.6-plus, qwen-flash, deepseek-v3, kimi-k2.5, glm-5
Same prompt, same SYRS+issues context → fair model comparison.

Output: output_sensitivity/<channel>_<model>.jsonl (one JSON record per line)
        output_sensitivity/run_summary.json (aggregated stats after completion)

Usage:
  python poc_sensitivity.py                              # all channels, default models
  python poc_sensitivity.py --channels A B              # subset
  python poc_sensitivity.py --models deepseek-v4-pro    # single model
  python poc_sensitivity.py --workers 4                 # API concurrency per channel

Per-record fields saved (for paper §4 / reproducibility):
  [id]       run_id, timestamp_utc, channel, syrs_id, category
  [model]    model_name, model_provider, api_base_url, temperature, max_tokens_req
  [tokens]   prompt_tokens, completion_tokens, total_tokens
  [timing]   latency_ms, finish_reason, attempt_number
  [output]   generated_vc, is_novel, output_chars
  [context]  golden_vc_chars, golden_vc_item_count, top1_sim, mean_top5_sim,
             issues_context_chars, prompt_chars_total
  [error]    error (null or message)
"""

import os
import json
import time
import threading
import argparse
import uuid
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent.parent / ".env")

WORKSPACE = Path(__file__).parent
OUT_DIR = WORKSPACE / "output_sensitivity"
OUT_DIR.mkdir(exist_ok=True)

# ── Run metadata logging ──────────────────────────────────────────────────────

LOG_DIR = WORKSPACE / "run_logs"
LOG_DIR.mkdir(exist_ok=True)

# Approximate cost per 1M tokens (input/output) in USD.
# Values are best-effort estimates; update as pricing changes.
_COST_PER_1M: dict[str, tuple[float, float]] = {
    # Alibaba Qwen (prices in USD per 1M tokens, input/output)
    "qwen-max":          (2.40,  9.60),
    "qwen3.6-plus":      (0.40,  1.20),   # same tier as qwen-plus
    "qwen-plus":         (0.40,  1.20),
    "qwen-flash":        (0.07,  0.28),   # qwen-flash pricing
    "qwen-turbo":        (0.07,  0.28),
    # DeepSeek (via DashScope)
    "deepseek-v3":       (0.27,  1.10),
    "deepseek-chat":     (0.27,  1.10),   # legacy alias for deepseek-v3
    # Moonshot AI / Kimi (via DashScope)
    "kimi-k2.5":         (0.90,  0.90),
    "kimi-k2.6":         (0.90,  0.90),   # same tier as k2.5
    # Zhipu AI / GLM (via DashScope)
    "glm-5":             (0.70,  0.70),   # approximate DashScope pricing
}
_DEFAULT_COST = (1.00, 3.00)  # fallback when model not in table

_log_lock = threading.Lock()


def log_run_metadata(log_dir: Path, entry: dict) -> None:
    """Append one metadata entry to run_logs/run_metadata_YYYYMMDD.jsonl (thread-safe)."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_path = log_dir / f"run_metadata_{date_str}.jsonl"
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _log_lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)


def _cost_usd(model: str, prompt_tok: int, completion_tok: int) -> float:
    in_rate, out_rate = _COST_PER_1M.get(model, _DEFAULT_COST)
    return round((prompt_tok * in_rate + completion_tok * out_rate) / 1_000_000, 6)

# ── Channel data sources ──────────────────────────────────────────────────────

CHANNEL_SOURCES = {
    "A": WORKSPACE / "output" / "matches.json",
    "B": WORKSPACE / "output_nhtsa" / "nhtsa_matches.json",
    "C": WORKSPACE / "output_cve" / "cve_matches.json",
}

# ── Model registry (all use OpenAI-compatible interface) ─────────────────────

MODEL_REGISTRY = {
    # ── Alibaba Qwen ──────────────────────────────────────────────────────────
    # Primary model (main experiment, full human evaluation — do not re-run)
    "qwen-max": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "qwen-max",
        "provider": "alibaba-qwen",
        "temperature": 0.2,
        "max_tokens": 800,
    },
    # Qwen3 Plus — Qwen3 architecture, mid-tier capability (RQ4 sensitivity)
    "qwen3.6-plus": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "qwen3.6-plus",
        "provider": "alibaba-qwen",
        "temperature": 0.2,
        "max_tokens": 800,
    },
    # Qwen Flash — lightweight, cost-efficiency test (RQ4 sensitivity)
    "qwen-flash": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "qwen-flash",
        "provider": "alibaba-qwen",
        "temperature": 0.2,
        "max_tokens": 800,
    },
    # ── DeepSeek (via DashScope, same DASHSCOPE_API_KEY) ─────────────────────
    # DeepSeek V3 — correct official model name per DashScope API docs
    "deepseek-v3": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "deepseek-v3",
        "provider": "deepseek-via-dashscope",
        "temperature": 0.2,
        "max_tokens": 800,
        "is_reasoning": False,
    },
    # Legacy alias kept for backward compat with existing sensitivity output files
    "deepseek-chat": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "deepseek-chat",
        "provider": "deepseek-via-dashscope",
        "temperature": 0.2,
        "max_tokens": 800,
        "is_reasoning": False,
    },
    # Qwen Plus — mid-tier, verified working (TTFT 2.30s in .env benchmark)
    "qwen-plus": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "qwen-plus",
        "provider": "alibaba-qwen",
        "temperature": 0.2,
        "max_tokens": 800,
    },
    # ── DeepSeek lightweight (via DashScope) ─────────────────────────────────
    # deepseek-v4-flash — verified working (TTFT 1.91s, 23.67s total in .env)
    "deepseek-v4-flash": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "deepseek-v4-flash",
        "provider": "deepseek-via-dashscope",
        "temperature": 0.2,
        "max_tokens": 800,
        "is_reasoning": False,
    },
    # ── Moonshot AI / Kimi (via DashScope, same DASHSCOPE_API_KEY) ───────────
    # kimi-k2.6 — verified working via DashScope (49.16s in .env benchmark)
    "kimi-k2.6": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "kimi-k2.6",
        "provider": "moonshot-via-dashscope",
        "temperature": 0.2,
        "max_tokens": 800,
    },
    # ── Zhipu AI / GLM (via DashScope, same DASHSCOPE_API_KEY) ───────────────
    "glm-5": {
        "api_key":  os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get("DASHSCOPE_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model_id": "glm-5",
        "provider": "zhipu-via-dashscope",
        "temperature": 0.2,
        "max_tokens": 800,
    },
    # ── Excluded models ───────────────────────────────────────────────────────
    # deepseek-r1 / deepseek-v4-pro / qwq-plus: reasoning/thinking models —
    #   thinking-mode output pollutes generated_vc sentinel detection
    # kimi-k2.5: superseded by kimi-k2.6 (both on DashScope, use k2.6)
}

# RQ4 sensitivity — 5 models covering 4 vendors (all verified via .env benchmark)
# Vendors: Alibaba Qwen (3 tiers) + DeepSeek + Moonshot Kimi + Zhipu GLM
# deepseek-chat already done (output_sensitivity/ch*_deepseek-chat.jsonl)
DEFAULT_MODELS = ["qwen3.6-plus", "qwen-plus", "deepseek-v4-flash", "kimi-k2.6", "glm-5"]

# ── Channel-specific prompts (verbatim from each channel's pipeline script) ──
# Keeping these identical to the originals ensures sensitivity test is model-only.

PROMPT_A = """You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

Your task: generate MISSING verification conditions for an automotive ECU system requirement.
"Missing" means test scenarios NOT already covered by the existing golden VCs.

The insight comes from real-world issues in open-source automotive protocol software.
These issues reveal corner cases that spec authors typically overlook.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (already covered — DO NOT repeat these):
{golden_vcs}

Related issues from automotive protocol software (potential missing corner cases):
{issues_context}

Generate 1-2 additional VCs in this YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.SEN.1
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
1. Genuinely testing the SYRS requirement (not testing the protocol library)
2. Not redundant with existing golden VCs
3. Inspired by a real failure pattern from the issues above
4. Testable at ECU system integration test level

If no genuinely useful missing VC can be identified from these issues, output:
NO_NOVEL_VC_FOUND
"""

PROMPT_B = """You are an automotive ECU system test engineer (ASPICE SYS.5).

Generate MISSING verification conditions for an automotive ECU body/control system requirement.
The insight comes from real NHTSA vehicle owner complaints — these are real-world corner cases
that specification authors typically miss.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (DO NOT repeat):
{golden_vcs}

Related NHTSA complaints (real-world failure corner cases):
{complaints_context}

Generate 1-2 additional VCs in YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.NHTSA.1
    Title: <test title>
    Method:
      Type: Dynamic
      Technique: <e.g. Fault Injection, Boundary Value Analysis, State Transition>
    Pass_Fail_Criteria:
      Pass: |
        1. <setup>
        2. <action>
        3. Verify: <expected ECU response>
      Fail: |
        - <failure condition>
    Source_Complaint: ODI#{odi} ({make} {model})

Only generate VCs that are:
1. Testable at ECU system integration level
2. Not redundant with existing golden VCs
3. Directly motivated by the real failure pattern in the complaint

If no useful missing VC is identifiable, output: NO_NOVEL_VC_FOUND
"""

PROMPT_C = """You are an automotive ECU cybersecurity test engineer (ISO/SAE 21434, ASPICE SYS.5).

Generate MISSING security verification conditions for this automotive SYRS.
Insight source: real CVE vulnerability reports from automotive systems.

SYRS:
{syrs_text}

Existing golden VCs (do not repeat):
{golden_vcs}

Related CVEs (attack patterns to test against):
{cve_context}

Generate 1-2 security VCs in YAML format:
- VC_Item:
    VC_ID: {vc_id}.CVE.1
    Title: <security test title>
    Method:
      Type: Dynamic
      Technique: Penetration Test / Fault Injection / Boundary Value Analysis
    Pass_Fail_Criteria:
      Pass: |
        1. <attack setup>
        2. <attack execution>
        3. Verify: <ECU SHALL reject/respond correctly>
      Fail: |
        - <security violation condition>
    CVE_Reference: {cve_ref}

Only generate VCs testable at ECU software integration level (not network infrastructure).
If no useful security VC, output: NO_NOVEL_VC_FOUND
"""


def _build_context(match: dict, channel: str) -> tuple[str, str, float, float, int]:
    """Build (prompt_text, issues_context, top1_sim, mean_top5_sim, issues_ctx_chars)."""
    golden = (match.get("golden_vc") or "")[:800] or "(none)"
    syrs_id = match["syrs_id"]

    if channel == "A":
        items = match.get("top_issues", [])
        ctx = "\n".join([
            f"Issue [{iss['repo']}#{iss['issue_id']}]: {iss['title']}\n"
            f"  Trigger: {iss['distilled'].get('trigger', 'N/A')}\n"
            f"  Behavior: {iss['distilled'].get('behavior', 'N/A')}\n"
            f"  Fault: {iss['distilled'].get('fault_mode', 'N/A')}"
            for iss in items
        ])
        prompt = PROMPT_A.format(
            syrs_text=match["requirement"],
            golden_vcs=golden,
            issues_context=ctx,
            vc_id_prefix=f"VC_{syrs_id}",
        )

    elif channel == "B":
        items = match.get("top_complaints", [])
        ctx = "\n".join([
            f"ODI#{c['odi']} ({c['make']} {c['model']} {c['year']}) component={c['component']}\n"
            f"  {c['summary']}\n"
            f"  → Trigger: {c['distilled'].get('trigger', '')}\n"
            f"  → Fault: {c['distilled'].get('fault_mode', '')}"
            for c in items
        ])
        top = items[0] if items else {}
        prompt = PROMPT_B.format(
            syrs_text=match["requirement"],
            golden_vcs=(match.get("golden_vc") or "")[:600] or "(none)",
            complaints_context=ctx,
            vc_id_prefix=f"VC_{syrs_id}",
            odi=top.get("odi", "N/A"),
            make=top.get("make", ""),
            model=top.get("model", ""),
        )

    elif channel == "C":
        items = match.get("top_cves", [])
        ctx = "\n".join([
            f"{c['cve_id']}: {c['description'][:150]}\n"
            f"  Attack: {c['distilled'].get('attack_vector', '')}\n"
            f"  Impact: {c['distilled'].get('security_impact', '')}"
            for c in items[:3]
        ])
        cve_ref = items[0]["cve_id"] if items else "N/A"
        prompt = PROMPT_C.format(
            syrs_text=match["requirement"],
            golden_vcs=(match.get("golden_vc") or "")[:600] or "(none)",
            cve_context=ctx,
            vc_id=f"VC_{syrs_id}",
            cve_ref=cve_ref,
        )

    else:
        raise ValueError(f"Unknown channel: {channel}")

    sims = [item.get("similarity", 0.0) for item in items]
    top1_sim   = max(sims) if sims else 0.0
    mean5_sim  = sum(sims) / len(sims) if sims else 0.0
    return prompt, ctx, top1_sim, mean5_sim, len(ctx)

# ── Per-file write lock (thread-safe JSONL appending) ────────────────────────

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
    done = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    done.add(rec["syrs_id"])
                except Exception:
                    pass
    return done

# ── Progress tracker ──────────────────────────────────────────────────────────

class ChannelProgress:
    def __init__(self, channel: str, model: str, total: int):
        self.channel = channel
        self.model = model
        self.total = total
        self._lock = threading.Lock()
        self.done = 0
        self.novel = 0
        self.errors = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.latencies: list[float] = []

    def update(self, record: dict) -> None:
        with self._lock:
            self.done += 1
            if record.get("is_novel"):
                self.novel += 1
            if record.get("error"):
                self.errors += 1
            self.tokens_in  += record.get("prompt_tokens", 0) or 0
            self.tokens_out += record.get("completion_tokens", 0) or 0
            if record.get("latency_ms"):
                self.latencies.append(record["latency_ms"])

    def summary_line(self) -> str:
        avg_lat = (sum(self.latencies) / len(self.latencies)) if self.latencies else 0
        novel_pct = (self.novel / self.done * 100) if self.done else 0
        return (
            f"Ch-{self.channel}|{self.model}: "
            f"{self.done}/{self.total} done | "
            f"novel={self.novel}({novel_pct:.0f}%) | "
            f"err={self.errors} | "
            f"tokens_in={self.tokens_in:,} out={self.tokens_out:,} | "
            f"avg_lat={avg_lat:.0f}ms"
        )

# ── Single VC generation call ─────────────────────────────────────────────────

def generate_one(
    match: dict,
    model_cfg: dict,
    run_id: str,
    channel: str,
) -> dict:
    model_name = model_cfg["model_id"]

    # Build channel-appropriate prompt and context metrics
    prompt, issues_context, top1_sim, mean_top5_sim, issues_ctx_chars = (
        _build_context(match, channel)
    )

    golden_vc_chars    = len(match.get("golden_vc") or "")
    golden_vc_count    = (match.get("golden_vc") or "").count("VC_Item:")
    prompt_chars_total = len(prompt)

    # API call with retry
    client = OpenAI(api_key=model_cfg["api_key"], base_url=model_cfg["base_url"])
    generated = None
    prompt_tokens = completion_tokens = total_tokens = 0
    reasoning_tokens = 0   # DeepSeek thinking tokens (separate from answer tokens)
    finish_reason = None
    error_msg = None
    attempt = 0
    t_start = time.perf_counter()
    is_reasoning_model = model_cfg.get("is_reasoning", False)

    for attempt in range(1, 4):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=model_cfg["temperature"],
                max_tokens=model_cfg["max_tokens"],
            )
            msg = resp.choices[0].message

            # Reasoning models (DeepSeek R-series, etc.) separate chain-of-thought
            # from the final answer. `content` holds the answer; `reasoning_content`
            # holds the thinking trace. If content is empty (thinking used all tokens),
            # fall back to extracting from reasoning_content.
            content = getattr(msg, "content", None) or ""
            reasoning = getattr(msg, "reasoning_content", None) or ""

            generated = content.strip()
            if not generated and reasoning and is_reasoning_model:
                # Answer was truncated — mark and keep reasoning excerpt for debug
                generated = f"TRUNCATED_REASONING: {reasoning[:200]}"

            finish_reason = resp.choices[0].finish_reason
            if resp.usage:
                prompt_tokens     = resp.usage.prompt_tokens or 0
                completion_tokens = resp.usage.completion_tokens or 0
                total_tokens      = resp.usage.total_tokens or 0
                # DeepSeek exposes thinking tokens via completion_tokens_details
                details = getattr(resp.usage, "completion_tokens_details", None)
                if details:
                    reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

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
        and not generated.startswith("TRUNCATED_REASONING:")
    )

    record = {
        # --- Identification ---
        "run_id":           run_id,
        "timestamp_utc":    datetime.now(timezone.utc).isoformat(),
        "channel":          channel,
        "syrs_id":          match["syrs_id"],
        "category":         match.get("category", ""),
        # --- Model config ---
        "model_name":       model_name,
        "model_provider":   model_cfg["provider"],
        "api_base_url":     model_cfg["base_url"],
        "temperature":      model_cfg["temperature"],
        "max_tokens_req":   model_cfg["max_tokens"],
        # --- Token usage ---
        "prompt_tokens":      prompt_tokens,
        "completion_tokens":  completion_tokens,
        "total_tokens":       total_tokens,
        "reasoning_tokens":   reasoning_tokens,   # thinking-trace tokens (DeepSeek R-series)
        # --- Timing & completion ---
        "latency_ms":       latency_ms,
        "finish_reason":    finish_reason,
        "attempt_number":   attempt,
        # --- Output ---
        "generated_vc":     generated,
        "is_novel":         is_novel,
        "output_chars":     len(generated),
        # --- Context metrics ---
        "golden_vc_chars":       golden_vc_chars,
        "golden_vc_item_count":  golden_vc_count,
        "top1_sim":              round(top1_sim, 4),
        "mean_top5_sim":         round(mean_top5_sim, 4),
        "issues_context_chars":  issues_ctx_chars,
        "prompt_chars_total":    prompt_chars_total,
        # --- Error ---
        "error": error_msg,
    }

    # ── Persist token/latency/cost metadata for every API call ───────────────
    log_run_metadata(LOG_DIR, {
        "timestamp":         record["timestamp_utc"],
        "script":            "poc_sensitivity",
        "model":             model_name,
        "channel":           channel,
        "syrs_id":           match["syrs_id"],
        "tokens_prompt":     prompt_tokens,
        "tokens_completion": completion_tokens,
        "tokens_total":      total_tokens,
        "latency_ms":        latency_ms,
        "cost_usd_estimate": _cost_usd(model_name, prompt_tokens, completion_tokens),
    })

    return record


# ── Channel worker ────────────────────────────────────────────────────────────

def run_channel(
    channel: str,
    model_name: str,
    run_id: str,
    workers: int,
    progress: ChannelProgress,
) -> list[dict]:
    model_cfg = MODEL_REGISTRY[model_name]
    source    = CHANNEL_SOURCES[channel]

    if not source.exists():
        print(f"[ERROR] Ch-{channel}: matches file not found: {source}")
        return []

    matches = json.loads(source.read_text(encoding="utf-8"))

    out_file = OUT_DIR / f"ch{channel}_{model_name.replace('/', '_')}.jsonl"
    done_ids = load_done_ids(out_file)
    todo     = [m for m in matches if m["syrs_id"] not in done_ids]

    print(f"[Ch-{channel}|{model_name}] {len(todo)} todo / {len(matches)} total "
          f"(resume: {len(done_ids)} already done) → {out_file.name}")

    if not todo:
        print(f"[Ch-{channel}|{model_name}] All done, skipping.")
        return []

    results = []

    def task(match):
        rec = generate_one(match, model_cfg, run_id, channel)
        append_jsonl(out_file, rec)
        progress.update(rec)
        return rec

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(task, m): m["syrs_id"] for m in todo}
        completed = 0
        for fut in as_completed(futures):
            completed += 1
            try:
                rec = fut.result()
                results.append(rec)
            except Exception as exc:
                print(f"  [warn] Ch-{channel} task failed: {exc}")
            if completed % 10 == 0:
                print(f"  {progress.summary_line()}")

    print(f"[Ch-{channel}|{model_name}] DONE — {progress.summary_line()}")
    return results


# ── Summary writer ────────────────────────────────────────────────────────────

def write_summary(run_id: str, progressors: list[ChannelProgress]) -> None:
    summary = {
        "run_id": run_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "channels": {},
    }
    for p in progressors:
        avg_lat = (sum(p.latencies) / len(p.latencies)) if p.latencies else 0
        summary["channels"][f"Ch{p.channel}_{p.model}"] = {
            "total": p.total,
            "done": p.done,
            "novel": p.novel,
            "novel_rate_pct": round(p.novel / p.done * 100, 1) if p.done else 0,
            "errors": p.errors,
            "tokens_in": p.tokens_in,
            "tokens_out": p.tokens_out,
            "avg_latency_ms": round(avg_lat),
            "total_latency_s": round(sum(p.latencies) / 1000, 1),
        }

    out = OUT_DIR / "run_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSummary written → {out}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LLM sensitivity analysis for VC generation")
    parser.add_argument("--channels", nargs="+", default=["A", "B", "C"],
                        choices=["A", "B", "C"], help="Channels to process")
    parser.add_argument("--models",   nargs="+", default=DEFAULT_MODELS,
                        choices=list(MODEL_REGISTRY.keys()), help="Models to compare")
    parser.add_argument("--workers",  type=int, default=3,
                        help="Max concurrent API calls per (channel, model) pair")
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:12]
    print(f"=== Sensitivity Run {run_id} ===")
    print(f"Channels : {args.channels}")
    print(f"Models   : {args.models}")
    print(f"Workers  : {args.workers} per channel-model pair")
    print()

    # Check API keys
    for m in args.models:
        cfg = MODEL_REGISTRY[m]
        if not cfg["api_key"]:
            print(f"[ERROR] Model {m}: api_key not found in environment")
            return

    # Load match counts for progress init
    channel_sizes = {}
    for ch in args.channels:
        src = CHANNEL_SOURCES[ch]
        if src.exists():
            channel_sizes[ch] = len(json.loads(src.read_text(encoding="utf-8")))
        else:
            channel_sizes[ch] = 0

    # Build tasks: one thread per (channel, model) pair
    all_progressors = []
    thread_args = []
    for model_name in args.models:
        for channel in args.channels:
            p = ChannelProgress(channel, model_name, channel_sizes.get(channel, 0))
            all_progressors.append(p)
            thread_args.append((channel, model_name, run_id, args.workers, p))

    print(f"Launching {len(thread_args)} parallel channel-model threads...\n")

    threads = []
    for ta in thread_args:
        t = threading.Thread(target=run_channel, args=ta, daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    write_summary(run_id, all_progressors)
    print("\nAll done.")


if __name__ == "__main__":
    main()
