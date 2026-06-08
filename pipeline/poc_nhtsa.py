"""
Thread B: NHTSA Complaint-Driven VC Generation for Body_Control SYRS
No API key required for NHTSA. Uses Qwen for distillation + generation.

NHTSA API: https://api.nhtsa.gov/complaints/complaintsByVehicle?make=X&model=Y&modelYear=Z
Component categories relevant to Body_Control SYRS:
  - ELECTRICAL SYSTEM:BODY:LOCK  (ESCL, door locks)
  - STEERING:LOCKS/COLUMNS       (steering column lock)
  - ELECTRICAL SYSTEM            (general ECU body)

Run:
  python poc_nhtsa.py --step fetch      # crawl NHTSA complaints
  python poc_nhtsa.py --step distill    # extract [Trigger|Behavior|Fault]
  python poc_nhtsa.py --step match      # embed + match to Body_Control SYRS
  python poc_nhtsa.py --step generate   # generate missing VCs
  python poc_nhtsa.py --step review     # export human review sheet
"""

import os
import json
import time
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

WORKSPACE = Path(__file__).parent
DATA_DIR = WORKSPACE.parent / "data"
CACHE_DIR = WORKSPACE / "cache_nhtsa"
OUT_DIR = WORKSPACE / "output_nhtsa"

CACHE_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

TARGET_CATEGORIES = {"Body_Control", "IO_HMI", "Functional_Safety", "System_State"}
TOP_K = 5

# NHTSA component keywords → maps to our SYRS categories
COMPONENT_KEYWORDS = [
    "ELECTRICAL SYSTEM:BODY",
    "STEERING:LOCKS",
    "DOOR LOCKS",
    "BODY:DOOR",
    "ELECTRICAL SYSTEM:IGNITION",
    "POWER TRAIN:AUTOMATIC TRANSMISSION:GEAR",
    "ELECTRICAL SYSTEM:SWITCHES",
    "SEATS:FRONT:SEAT BELT",
    "VISIBILITY:WIPER",
    "ELECTRICAL SYSTEM:LIGHTING",
]

# Vehicle makes to sample from (broad coverage)
SAMPLE_MAKES_MODELS = [
    ("TOYOTA", "CAMRY", 2022),
    ("TOYOTA", "COROLLA", 2022),
    ("BMW", "3 SERIES", 2022),
    ("VOLKSWAGEN", "GOLF", 2022),
    ("HONDA", "CIVIC", 2022),
    ("FORD", "FOCUS", 2022),
    ("MERCEDES BENZ", "C CLASS", 2022),
    ("AUDI", "A4", 2022),
    ("TOYOTA", "CAMRY", 2021),
    ("BMW", "5 SERIES", 2022),
]


# ── Step 1: Fetch NHTSA Complaints ───────────────────────────────────────────

def fetch_nhtsa_complaints() -> list[dict]:
    cache_file = CACHE_DIR / "nhtsa_complaints_raw.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        print(f"  [cache] {len(data)} complaints loaded")
        return data

    all_complaints = []
    seen_ids = set()

    for make, model, year in SAMPLE_MAKES_MODELS:
        url = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
        params = {"make": make, "model": model, "modelYear": year}
        print(f"  [fetch] {make} {model} {year} ...")
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code}")
                continue
            data = resp.json()
            complaints = data.get("results", [])
            for c in complaints:
                cid = c.get("odiNumber", "")
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    # Keep only fields we need
                    all_complaints.append({
                        "odi": str(cid),
                        "make": make,
                        "model": model,
                        "year": year,
                        "component": c.get("components", ""),
                        "summary": c.get("summary", "")[:1000],
                        "crash": c.get("crash", False),
                        "fire": c.get("fire", False),
                        "mileage": c.get("mileage", 0),
                    })
            print(f"    → {len(complaints)} complaints ({len(all_complaints)} total unique)")
            time.sleep(0.3)
        except Exception as e:
            print(f"    [error] {e}")

    # Also try component-specific search if available
    # NHTSA flat file approach: filter by component keyword
    filtered = []
    kw_lower = [k.lower() for k in COMPONENT_KEYWORDS]
    for c in all_complaints:
        comp = c.get("component", "").lower()
        summary = c.get("summary", "").lower()
        if any(k in comp or k in summary for k in ["lock", "door", "wiper", "ignition",
                                                     "steering column", "body control",
                                                     "sensor", "warning", "display"]):
            filtered.append(c)

    print(f"\nFiltered relevant complaints: {len(filtered)} / {len(all_complaints)}")
    cache_file.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    return filtered


def cmd_fetch():
    complaints = fetch_nhtsa_complaints()
    print(f"\nTotal cached: {len(complaints)} complaints")


# ── Step 2: Distill Complaints ────────────────────────────────────────────────

NHTSA_DISTILL_PROMPT = """You are an automotive ECU requirements engineer.
Extract the technical essence from this NHTSA vehicle complaint.

Output ONLY a JSON object:
{{
  "trigger": "what operational condition or user action triggered the failure",
  "behavior": "what the system was expected to do vs what actually happened",
  "fault_mode": "failure category: e.g. no-response, false-activation, timing-violation, state-stuck, unexpected-lock, sensor-error"
}}

If this complaint is not related to automotive ECU system behavior (e.g., cosmetic, noise, smell), output:
{{"trigger": null, "behavior": null, "fault_mode": null}}

Component: {component}
Complaint: {summary}
"""


def cmd_distill():
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ.get("DASHSCOPE_BASE_URL",
                                "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )

    complaints = json.loads((CACHE_DIR / "nhtsa_complaints_raw.json").read_text(encoding="utf-8"))

    cache_file = CACHE_DIR / "nhtsa_distilled.json"
    if cache_file.exists():
        results = json.loads(cache_file.read_text(encoding="utf-8"))
        done_ids = {r["odi"] for r in results}
        complaints = [c for c in complaints if c["odi"] not in done_ids]
    else:
        results = []

    print(f"Distilling {len(complaints)} new complaints...")
    for i, c in enumerate(complaints):
        prompt = NHTSA_DISTILL_PROMPT.format(
            component=c.get("component", ""),
            summary=c.get("summary", "")[:800],
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
            extracted = {"trigger": None, "behavior": None, "fault_mode": None}

        results.append({**c, "distilled": extracted})

        if (i + 1) % 30 == 0:
            cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  {i+1}/{len(complaints)} done")
            time.sleep(1)

    cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    valid = sum(1 for r in results if r["distilled"].get("trigger"))
    print(f"Valid: {valid} / {len(results)}")


# ── Step 3: Load SYRS + Match ─────────────────────────────────────────────────

def load_body_control_syrs() -> list[dict]:
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
    print(f"Body_Control SYRS loaded: {len(syrs_list)}")
    return syrs_list


def embed_texts_qwen(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ.get("DASHSCOPE_BASE_URL",
                                "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )
    all_emb = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(model="text-embedding-v3", input=batch)
        all_emb.extend([r.embedding for r in resp.data])
        time.sleep(0.2)
    return all_emb


def cmd_match():
    import numpy as np

    syrs_list = load_body_control_syrs()
    distilled = json.loads((CACHE_DIR / "nhtsa_distilled.json").read_text(encoding="utf-8"))
    valid = [d for d in distilled if d["distilled"].get("trigger")]
    print(f"Valid distilled complaints: {len(valid)}")

    syrs_emb_cache = CACHE_DIR / "syrs_body_embeddings.json"
    if syrs_emb_cache.exists():
        syrs_emb = json.loads(syrs_emb_cache.read_text())
    else:
        print("Embedding SYRS...")
        syrs_emb = embed_texts_qwen([s["requirement"] for s in syrs_list])
        syrs_emb_cache.write_text(json.dumps(syrs_emb))

    nhtsa_emb_cache = CACHE_DIR / "nhtsa_embeddings.json"
    if nhtsa_emb_cache.exists():
        nhtsa_emb = json.loads(nhtsa_emb_cache.read_text())
    else:
        print("Embedding NHTSA complaints...")
        texts = [
            f"{d['distilled']['trigger']}. {d['distilled']['behavior']}. {d['distilled']['fault_mode']}"
            for d in valid
        ]
        nhtsa_emb = embed_texts_qwen(texts)
        nhtsa_emb_cache.write_text(json.dumps(nhtsa_emb))

    A = np.array(syrs_emb)
    B = np.array(nhtsa_emb)
    A /= (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
    B /= (np.linalg.norm(B, axis=1, keepdims=True) + 1e-9)
    sim = A @ B.T

    matches = []
    for i, s in enumerate(syrs_list):
        top_idx = np.argsort(sim[i])[::-1][:TOP_K]
        top = []
        for j in top_idx:
            top.append({
                "odi": valid[j]["odi"],
                "make": valid[j]["make"],
                "model": valid[j]["model"],
                "year": valid[j]["year"],
                "component": valid[j].get("component", ""),
                "summary": valid[j].get("summary", "")[:200],
                "distilled": valid[j]["distilled"],
                "similarity": float(sim[i][j]),
            })
        matches.append({**s, "top_complaints": top})

    (OUT_DIR / "nhtsa_matches.json").write_text(
        json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== Sample Matches ===")
    for m in matches[:3]:
        req_safe = m['requirement'][:100].encode('ascii', errors='replace').decode('ascii')
        print(f"\n[{m['syrs_id']}] {req_safe}")
        for c in m["top_complaints"][:2]:
            summary_safe = c['summary'][:80].encode('ascii', errors='replace').decode('ascii')
            print(f"  sim={c['similarity']:.3f} ODI#{c['odi']} {c['make']} {c['model']}: {summary_safe}")


# ── Step 4: Generate VCs ──────────────────────────────────────────────────────

NHTSA_GENERATE_PROMPT = """You are an automotive ECU system test engineer (ASPICE SYS.5).

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


def cmd_generate():
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ.get("DASHSCOPE_BASE_URL",
                                "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )

    matches = json.loads((OUT_DIR / "nhtsa_matches.json").read_text(encoding="utf-8"))
    results = []
    cache_file = OUT_DIR / "nhtsa_generated_vcs.json"
    if cache_file.exists():
        results = json.loads(cache_file.read_text(encoding="utf-8"))
        done = {r["syrs_id"] for r in results}
        matches = [m for m in matches if m["syrs_id"] not in done]

    print(f"Generating VCs for {len(matches)} SYRS...")
    for i, m in enumerate(matches):
        top = m["top_complaints"][:3]
        complaints_ctx = "\n".join([
            f"ODI#{c['odi']} ({c['make']} {c['model']} {c['year']}) component={c['component']}\n"
            f"  {c['summary']}\n"
            f"  → Trigger: {c['distilled'].get('trigger', '')}\n"
            f"  → Fault: {c['distilled'].get('fault_mode', '')}"
            for c in top
        ])
        odi_ref = top[0]["odi"] if top else "N/A"
        make_ref = top[0]["make"] if top else ""
        model_ref = top[0]["model"] if top else ""

        prompt = NHTSA_GENERATE_PROMPT.format(
            syrs_text=m["requirement"],
            golden_vcs=(m["golden_vc"] or "")[:600],
            complaints_context=complaints_ctx,
            vc_id_prefix=f"VC_{m['syrs_id']}",
            odi=odi_ref, make=make_ref, model=model_ref,
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

        results.append({**m, "generated_vc": generated})
        if (i + 1) % 10 == 0:
            cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  {i+1} done")
        time.sleep(0.5)

    cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    novel = sum(1 for r in results if "NO_NOVEL_VC_FOUND" not in r.get("generated_vc", ""))
    print(f"\nNovel VCs: {novel}/{len(results)}")


# ── Step 5: Export Review Sheet ───────────────────────────────────────────────

def cmd_review():
    results = json.loads((OUT_DIR / "nhtsa_generated_vcs.json").read_text(encoding="utf-8"))
    novel = [r for r in results if "NO_NOVEL_VC_FOUND" not in r.get("generated_vc", "")]

    lines = [
        "# Human Expert Review — NHTSA Complaint-Driven VC Generation",
        f"**Source:** NHTSA ODI complaints  **SYRS type:** Body_Control / IO_HMI / Functional_Safety",
        f"**Evaluator:** _____________  **Date:** ___________",
        "",
        "Rate each generated VC:",
        "- **Correctness** (1-5): Valid test condition for this SYRS?",
        "- **Novelty** (Y/N): Not already in golden VC?",
        "- **Usefulness** (Y/N): Would add to real test spec?",
        "",
        "---",
    ]

    for i, r in enumerate(novel, 1):
        top = r.get("top_complaints", [])
        lines += [
            f"## {i}. [{r['syrs_id']}] ({r['category']})",
            f"**SYRS:** {r['requirement'][:300]}",
            "",
            "**Top NHTSA Complaints:**",
        ]
        for c in top[:3]:
            lines += [
                f"- ODI#{c['odi']} {c['make']} {c['model']} {c['year']} *(sim={c['similarity']:.2f})*",
                f"  - {c['summary'][:120]}",
                f"  - Fault: {c['distilled'].get('fault_mode', 'N/A')}",
            ]
        lines += [
            "",
            "**Existing Golden VCs (excerpt):**",
            f"```\n{r['golden_vc'][:400]}\n```" if r['golden_vc'] else "*(none)*",
            "",
            "**Generated Missing VC:**",
            f"```yaml\n{r['generated_vc']}\n```",
            "",
            "| Correctness (1-5) | Novelty (Y/N) | Usefulness (Y/N) | Notes |",
            "|---|---|---|---|",
            "| | | | |",
            "",
            "---",
        ]

    out = OUT_DIR / "nhtsa_review_sheet.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {out}  ({len(novel)} SYRS for review)")


STEPS = {"fetch": cmd_fetch, "distill": cmd_distill,
         "match": cmd_match, "generate": cmd_generate, "review": cmd_review}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=list(STEPS.keys()), required=True)
    args = parser.parse_args()
    STEPS[args.step]()
