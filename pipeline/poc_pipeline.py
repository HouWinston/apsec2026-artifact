"""
POC: Issue-Driven VC Generation for Automotive SYRS
Goal: validate whether GitHub protocol-level issues can inspire missing VCs
      for ASPICE-compliant Diagnostics_DCM + Communication_Stack SYRS

Pipeline:
  1. Load DCM/CommStack SYRS (from golden corpus)
  2. Fetch issues from udsoncan + python-isotp + python-can
  3. Distill each issue to [Trigger | Protocol Behavior | Fault Mode]
  4. Embed SYRS + distilled issues, compute similarity
  5. For each SYRS: retrieve top-K issues, generate missing VC
  6. Output for manual expert review

Usage:
  set GITHUB_TOKEN=ghp_xxxxx   (optional, increases rate limit 60→5000/hr)
  set OPENAI_API_KEY=sk-xxx
  python poc_pipeline.py --step fetch     # step 1: crawl issues to disk
  python poc_pipeline.py --step distill   # step 2: LLM distillation
  python poc_pipeline.py --step match     # step 3: embed + match
  python poc_pipeline.py --step generate  # step 4: VC generation
  python poc_pipeline.py --step review    # step 5: export human review sheet
"""

import os
import json
import time
import argparse
import hashlib
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from workspace root
load_dotenv(Path(__file__).parent.parent / ".env")

WORKSPACE = Path(__file__).parent
DATA_DIR = WORKSPACE.parent / "data"
CACHE_DIR = WORKSPACE / "cache"
OUT_DIR = WORKSPACE / "output"

CACHE_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

TARGET_REPOS = [
    "pylessard/python-udsoncan",
    "pylessard/python-can-isotp",
    "hardbyte/python-can",
    "ecubus/EcuBus-Pro",
]
TARGET_CATEGORIES = {"Diagnostics_DCM", "Communication_Stack", "Diagnostics_DEM", "Diagnostic_Services"}
MAX_ISSUES_PER_REPO = 300
TOP_K_ISSUES = 5


# ── Step 1: Fetch Issues ──────────────────────────────────────────────────────

def fetch_issues(repo: str, max_issues: int = MAX_ISSUES_PER_REPO) -> list[dict]:
    cache_file = CACHE_DIR / f"issues_{repo.replace('/', '_')}.json"
    if cache_file.exists():
        print(f"  [cache] {repo}")
        return json.loads(cache_file.read_text(encoding="utf-8"))

    print(f"  [fetch] {repo} ...")
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Authorization": f"token {token}"} if token else {}
    headers["Accept"] = "application/vnd.github.v3+json"

    issues = []
    page = 1
    while len(issues) < max_issues:
        url = f"https://api.github.com/repos/{repo}/issues"
        params = {"state": "all", "per_page": 100, "page": page,
                  "labels": "bug"}  # bug-labeled issues only for signal quality
        # retry up to 3 times on timeout
        resp = None
        for _attempt in range(3):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=60)
                break
            except requests.exceptions.Timeout:
                print(f"  [warn] timeout on {repo} page {page}, attempt {_attempt+1}/3, retrying...")
                time.sleep(5)
        if resp is None:
            print(f"  [error] all retries failed for {repo}, skipping")
            break
        if resp.status_code == 403:
            print(f"  [warn] rate limited — sleep 60s")
            time.sleep(60)
            continue
        if resp.status_code != 200:
            print(f"  [warn] {repo} page {page}: HTTP {resp.status_code}")
            break
        batch = resp.json()
        if not batch:
            break
        for issue in batch:
            if issue.get("pull_request"):  # skip PRs
                continue
            issues.append({
                "repo": repo,
                "id": issue["number"],
                "title": issue.get("title", ""),
                "body": (issue.get("body") or "")[:3000],  # cap length
                "labels": [l["name"] for l in issue.get("labels", [])],
                "state": issue.get("state", ""),
            })
        page += 1
        time.sleep(0.5)

    # Also fetch without label filter to get more coverage
    if len(issues) < 50:
        page = 1
        while len(issues) < max_issues:
            url = f"https://api.github.com/repos/{repo}/issues"
            params = {"state": "closed", "per_page": 100, "page": page}
            resp = None
            for _attempt in range(3):
                try:
                    resp = requests.get(url, headers=headers, params=params, timeout=60)
                    break
                except requests.exceptions.Timeout:
                    print(f"  [warn] timeout on {repo} page {page}, attempt {_attempt+1}/3")
                    time.sleep(5)
            if resp is None:
                break
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            for issue in batch:
                if issue.get("pull_request"):
                    continue
                issues.append({
                    "repo": repo,
                    "id": issue["number"],
                    "title": issue.get("title", ""),
                    "body": (issue.get("body") or "")[:3000],
                    "labels": [l["name"] for l in issue.get("labels", [])],
                    "state": issue.get("state", ""),
                })
            page += 1
            time.sleep(0.5)
            if len(issues) >= max_issues:
                break

    issues = issues[:max_issues]
    cache_file.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    → {len(issues)} issues saved")
    return issues


def cmd_fetch():
    all_issues = []
    for repo in TARGET_REPOS:
        issues = fetch_issues(repo)
        all_issues.extend(issues)
    print(f"\nTotal issues fetched: {len(all_issues)}")
    (CACHE_DIR / "all_issues.json").write_text(
        json.dumps(all_issues, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Step 2: Distill Issues ────────────────────────────────────────────────────

DISTILL_PROMPT = """You are an automotive embedded systems expert.
Extract the technical essence from this GitHub issue report.

Output ONLY a JSON object with these three fields:
{{
  "trigger": "what system state or input caused the issue (protocol service, service ID, conditions)",
  "behavior": "what protocol or system behavior was expected vs observed",
  "fault_mode": "the failure category: e.g. missing response, wrong NRC, timing violation, silent failure, protocol non-compliance"
}}

If the issue is not about automotive protocol behavior (e.g., pure Python packaging, docs), output:
{{"trigger": null, "behavior": null, "fault_mode": null}}

Issue title: {title}
Issue body: {body}
"""


def _qwen_client():
    from openai import OpenAI
    return OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ.get("DASHSCOPE_BASE_URL",
                                "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )

def distill_issue_batch(issues: list[dict]) -> list[dict]:
    client = _qwen_client()

    cache_file = CACHE_DIR / "distilled_issues.json"
    if cache_file.exists():
        existing = json.loads(cache_file.read_text(encoding="utf-8"))
        existing_ids = {f"{d['repo']}#{d['id']}" for d in existing}
    else:
        existing = []
        existing_ids = set()

    results = list(existing)
    new_count = 0

    for issue in issues:
        key = f"{issue['repo']}#{issue['id']}"
        if key in existing_ids:
            continue

        prompt = DISTILL_PROMPT.format(
            title=issue["title"][:200],
            body=issue["body"][:2000]
        )
        try:
            resp = client.chat.completions.create(
                model="qwen-plus",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            extracted = json.loads(resp.choices[0].message.content)
        except Exception as e:
            print(f"  [warn] distill {key}: {e}")
            extracted = {"trigger": None, "behavior": None, "fault_mode": None}

        results.append({
            **issue,
            "distilled": extracted,
        })
        existing_ids.add(key)
        new_count += 1

        if new_count % 20 == 0:
            cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  distilled {new_count} issues...")
            time.sleep(1)

    cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def cmd_distill():
    issues = json.loads((CACHE_DIR / "all_issues.json").read_text(encoding="utf-8"))
    results = distill_issue_batch(issues)
    # Filter out null distillations
    valid = [r for r in results if r["distilled"].get("trigger")]
    print(f"Valid distilled issues: {len(valid)} / {len(results)}")


# ── Step 3: Load SYRS + Embed + Match ────────────────────────────────────────

def load_target_syrs() -> list[dict]:
    with open(DATA_DIR / "SYRS_Classified_20260429_085505.json", encoding="utf-8") as f:
        raw = json.load(f)
    with open(DATA_DIR / "golden_vc_text_20260429_091653.json", encoding="utf-8") as f:
        golden_vcs = json.load(f)

    syrs_list = []
    for qual_key, subcats in raw.items():
        for cat, items in subcats.items():
            if cat not in TARGET_CATEGORIES:
                continue
            if isinstance(items, list):
                for item in items:
                    syrs_list.append({
                        "syrs_id": item["SYRS_ID"],
                        "category": cat,
                        "requirement": item["System_Requirements"],
                        "golden_vc": golden_vcs.get(item["SYRS_ID"], ""),
                    })
            elif isinstance(items, dict):
                syrs_list.append({
                    "syrs_id": items["SYRS_ID"],
                    "category": cat,
                    "requirement": items["System_Requirements"],
                    "golden_vc": golden_vcs.get(items["SYRS_ID"], ""),
                })
    print(f"Target SYRS loaded: {len(syrs_list)}")
    return syrs_list


def embed_texts(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    client = _qwen_client()

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(
            model="text-embedding-v3",
            input=batch,
        )
        all_embeddings.extend([r.embedding for r in resp.data])
        time.sleep(0.2)
    return all_embeddings


def cosine_similarity_matrix(vecs_a, vecs_b):
    import numpy as np
    a = np.array(vecs_a)
    b = np.array(vecs_b)
    # normalize
    a = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    b = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return a @ b.T


def cmd_match():
    import numpy as np

    syrs_list = load_target_syrs()
    distilled = json.loads((CACHE_DIR / "distilled_issues.json").read_text(encoding="utf-8"))
    valid_issues = [d for d in distilled if d["distilled"].get("trigger")]

    print(f"Embedding {len(syrs_list)} SYRS...")
    syrs_texts = [f"{s['requirement']}" for s in syrs_list]
    syrs_emb_cache = CACHE_DIR / "syrs_embeddings.json"
    if syrs_emb_cache.exists():
        syrs_embeddings = json.loads(syrs_emb_cache.read_text())
    else:
        syrs_embeddings = embed_texts(syrs_texts)
        syrs_emb_cache.write_text(json.dumps(syrs_embeddings))

    # Distilled issue text: combine trigger + behavior + fault_mode
    issue_texts = []
    for iss in valid_issues:
        d = iss["distilled"]
        text = f"{d.get('trigger', '')}. {d.get('behavior', '')}. {d.get('fault_mode', '')}"
        issue_texts.append(text)

    print(f"Embedding {len(valid_issues)} distilled issues...")
    issue_emb_cache = CACHE_DIR / "issue_embeddings.json"
    if issue_emb_cache.exists():
        issue_embeddings = json.loads(issue_emb_cache.read_text())
    else:
        issue_embeddings = embed_texts(issue_texts)
        issue_emb_cache.write_text(json.dumps(issue_embeddings))

    sim_matrix = cosine_similarity_matrix(syrs_embeddings, issue_embeddings)

    matches = []
    for i, syrs in enumerate(syrs_list):
        scores = sim_matrix[i]
        top_k_idx = np.argsort(scores)[::-1][:TOP_K_ISSUES]
        top_issues = []
        for j in top_k_idx:
            top_issues.append({
                "repo": valid_issues[j]["repo"],
                "issue_id": valid_issues[j]["id"],
                "title": valid_issues[j]["title"],
                "distilled": valid_issues[j]["distilled"],
                "similarity": float(scores[j]),
            })
        matches.append({
            "syrs_id": syrs["syrs_id"],
            "category": syrs["category"],
            "requirement": syrs["requirement"],
            "golden_vc": syrs["golden_vc"],
            "top_issues": top_issues,
        })

    (OUT_DIR / "matches.json").write_text(
        json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Print sample matches for sanity check
    print("\n=== Sample Matches (first 3 SYRS) ===")
    for m in matches[:3]:
        print(f"\n[{m['syrs_id']}] {m['requirement'][:120]}")
        for iss in m["top_issues"][:2]:
            print(f"  sim={iss['similarity']:.3f} [{iss['repo']}#{iss['issue_id']}] {iss['title'][:80]}")
            print(f"    trigger: {iss['distilled'].get('trigger', '')[:80]}")


# ── Step 4: Generate VCs ──────────────────────────────────────────────────────

GENERATE_PROMPT = """You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

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
    VC_ID: {vc_id_prefix}.NEW.1
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


def generate_vcs_for_match(match: dict) -> dict:
    client = _qwen_client()

    issues_context = "\n".join([
        f"Issue [{iss['repo']}#{iss['issue_id']}]: {iss['title']}\n"
        f"  Trigger: {iss['distilled'].get('trigger', 'N/A')}\n"
        f"  Behavior: {iss['distilled'].get('behavior', 'N/A')}\n"
        f"  Fault: {iss['distilled'].get('fault_mode', 'N/A')}"
        for iss in match["top_issues"]
    ])

    golden_summary = match["golden_vc"][:800] if match["golden_vc"] else "(none)"

    prompt = GENERATE_PROMPT.format(
        syrs_text=match["requirement"],
        golden_vcs=golden_summary,
        issues_context=issues_context,
        vc_id_prefix=f"VC_{match['syrs_id']}",
    )

    try:
        resp = client.chat.completions.create(
            model="qwen-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800,
        )
        generated = resp.choices[0].message.content.strip()
    except Exception as e:
        generated = f"ERROR: {e}"

    return {**match, "generated_vc": generated}


def cmd_generate():
    matches = json.loads((OUT_DIR / "matches.json").read_text(encoding="utf-8"))

    results = []
    cache_file = OUT_DIR / "generated_vcs.json"
    if cache_file.exists():
        results = json.loads(cache_file.read_text(encoding="utf-8"))
        done_ids = {r["syrs_id"] for r in results}
        matches = [m for m in matches if m["syrs_id"] not in done_ids]

    print(f"Generating VCs for {len(matches)} SYRS...")
    for i, match in enumerate(matches):
        result = generate_vcs_for_match(match)
        results.append(result)
        if (i + 1) % 10 == 0:
            cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  {i+1}/{len(matches) + len(results) - len(matches)} done")
        time.sleep(0.5)

    cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    novel = sum(1 for r in results if "NO_NOVEL_VC_FOUND" not in r.get("generated_vc", ""))
    print(f"\nGenerated: {novel} SYRS with novel VCs / {len(results)} total")


# ── Step 5: Export Human Review Sheet ────────────────────────────────────────

def cmd_review():
    results = json.loads((OUT_DIR / "generated_vcs.json").read_text(encoding="utf-8"))
    novel = [r for r in results if "NO_NOVEL_VC_FOUND" not in r.get("generated_vc", "")]

    # Markdown review sheet
    lines = [
        "# Human Expert Review Sheet — Issue-Driven VC Generation POC",
        f"**Date:** 2026-05-21  **Evaluator:** ___________",
        "",
        "**Instructions:** For each generated VC below, rate:",
        "- **Correctness** (1-5): Is this a valid test condition for the SYRS?",
        "- **Novelty** (Y/N): Is this NOT already covered by the golden VCs?",
        "- **Usefulness** (Y/N): Would you add this to the test spec?",
        "",
        "---",
        "",
    ]

    for i, r in enumerate(novel, 1):
        sim_scores = [f"{iss['similarity']:.2f}" for iss in r["top_issues"][:3]]
        lines += [
            f"## {i}. [{r['syrs_id']}] ({r['category']})",
            f"**SYRS:** {r['requirement'][:300]}",
            "",
            f"**Top Issue Similarity Scores:** {', '.join(sim_scores)}",
            f"**Inspiring Issues:**",
        ]
        for iss in r["top_issues"][:3]:
            lines.append(f"- [{iss['repo']}#{iss['issue_id']}] {iss['title']} *(sim={iss['similarity']:.2f})*")
            lines.append(f"  - Trigger: {iss['distilled'].get('trigger', 'N/A')}")
            lines.append(f"  - Fault: {iss['distilled'].get('fault_mode', 'N/A')}")
        lines += [
            "",
            "**Existing Golden VCs (excerpt):**",
            f"```\n{r['golden_vc'][:400]}\n```" if r['golden_vc'] else "*(none)*",
            "",
            "**Generated Missing VC:**",
            f"```yaml\n{r['generated_vc']}\n```",
            "",
            "**Evaluation:**",
            "| Correctness (1-5) | Novelty (Y/N) | Usefulness (Y/N) | Notes |",
            "|---|---|---|---|",
            "| | | | |",
            "",
            "---",
            "",
        ]

    review_file = OUT_DIR / "human_review_sheet.md"
    review_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"Review sheet saved: {review_file}")
    print(f"Total SYRS for review: {len(novel)}")


# ── Main ──────────────────────────────────────────────────────────────────────

STEPS = {
    "fetch": cmd_fetch,
    "distill": cmd_distill,
    "match": cmd_match,
    "generate": cmd_generate,
    "review": cmd_review,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=list(STEPS.keys()), required=True)
    args = parser.parse_args()
    STEPS[args.step]()
