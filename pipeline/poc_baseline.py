"""
Zero-shot Baseline: generate VCs from SYRS alone, NO issue retrieval.
This is the ablation condition to compare against Channel A and B.

Same model (qwen-max), same output format, same SYRS set.
Run AFTER Channel A/B generate steps so all conditions are comparable.

python poc_baseline.py
"""
import os, json, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

WORKSPACE = Path(__file__).parent
DATA_DIR = WORKSPACE.parent / "data"
OUT_DIR = WORKSPACE / "output_baseline"
OUT_DIR.mkdir(exist_ok=True)

TARGET_CATEGORIES = {
    "Diagnostics_DCM", "Communication_Stack", "Diagnostics_DEM",
    "Diagnostic_Services", "Body_Control", "IO_HMI", "System_State",
}

BASELINE_PROMPT = """You are an automotive ECU systems testing expert (ASPICE SYS.5).

Generate ADDITIONAL Verification Conditions for this automotive ECU requirement.
"Additional" means test scenarios beyond the most obvious happy-path test.

SYRS (System Requirement):
{syrs_text}

Existing VCs already written (DO NOT repeat):
{golden_vcs}

Generate 1-2 additional VCs in YAML format that test corner cases, boundary values,
or error handling scenarios a test engineer might overlook:

- VC_Item:
    VC_ID: {vc_id_prefix}.BASELINE.1
    Title: <title>
    Method:
      Type: Dynamic
      Technique: <technique>
    Pass_Fail_Criteria:
      Pass: |
        1. <step>
        2. Verify: <expected>
      Fail: |
        - <failure condition>

If no meaningful additional VC is identifiable beyond the golden VCs, output:
NO_NOVEL_VC_FOUND
"""

def load_syrs():
    with open(DATA_DIR / "SYRS_Classified_20260429_085505.json", encoding="utf-8") as f:
        raw = json.load(f)
    with open(DATA_DIR / "golden_vc_text_20260429_091653.json", encoding="utf-8") as f:
        golden = json.load(f)
    syrs = []
    for qual_key, subcats in raw.items():
        for cat, items in subcats.items():
            if cat not in TARGET_CATEGORIES:
                continue
            if isinstance(items, list):
                for item in items:
                    if item["SYRS_ID"] in golden:
                        syrs.append({"syrs_id": item["SYRS_ID"], "category": cat,
                                     "requirement": item["System_Requirements"],
                                     "golden_vc": golden[item["SYRS_ID"]]})
            elif isinstance(items, dict):
                if items["SYRS_ID"] in golden:
                    syrs.append({"syrs_id": items["SYRS_ID"], "category": cat,
                                 "requirement": items["System_Requirements"],
                                 "golden_vc": golden[items["SYRS_ID"]]})
    return syrs

def main():
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ.get("DASHSCOPE_BASE_URL",
                                "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )

    syrs_list = load_syrs()
    cache_file = OUT_DIR / "baseline_vcs.json"
    results = []
    if cache_file.exists():
        results = json.loads(cache_file.read_text(encoding="utf-8"))
        done = {r["syrs_id"] for r in results}
        syrs_list = [s for s in syrs_list if s["syrs_id"] not in done]

    print(f"Zero-shot baseline: {len(syrs_list)} SYRS remaining")
    for i, s in enumerate(syrs_list):
        prompt = BASELINE_PROMPT.format(
            syrs_text=s["requirement"],
            golden_vcs=(s["golden_vc"] or "")[:600],
            vc_id_prefix=f"VC_{s['syrs_id']}",
        )
        try:
            resp = client.chat.completions.create(
                model="qwen-max",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=600,
            )
            generated = resp.choices[0].message.content.strip()
        except Exception as e:
            generated = f"ERROR: {e}"

        results.append({**s, "generated_vc": generated, "condition": "zero-shot-baseline"})

        if (i + 1) % 10 == 0:
            cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  {i+1}/{len(syrs_list)} done")
        time.sleep(0.3)

    cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    novel = sum(1 for r in results if "NO_NOVEL_VC_FOUND" not in r.get("generated_vc", ""))
    print(f"\nBaseline complete: {novel}/{len(results)} generated VCs")
    print(f"Output: {cache_file}")

if __name__ == "__main__":
    main()
