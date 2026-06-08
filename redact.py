#!/usr/bin/env python3
"""
Auditable de-identification for the IssueDriven-VC replication package (release
option A: "de-identified full"). Conservative / over-redacting by design.

What it does
------------
1. BLANKS proprietary free-text fields (the company's SYRS requirement text and
   golden VCs) -> "<REDACTED: proprietary SYRS text>".
2. TOKEN-REPLACES every signal-shaped identifier (PREFIX_token) that is not in a
   whitelist of structural/schema/category/sentinel tokens -> "<SIG_n>", using a
   stable mapping (same signal -> same placeholder) for cross-file traceability.
3. KEEPS: scores, labels, channel, category, SYRS_ID, Issue_Source (public
   GitHub refs), protocol/standard names (ISO 15765-2, LIN, UDS, CAN ...).

It is intentionally over-redactive: a few generic terms (e.g. Vehicle_Speed) are
also masked. The statistical results remain fully reproducible from the kept
score columns; see stats/.

Usage:  python redact.py <SRC_poc_dir> <DST_artifact_dir>
"""
import csv, json, re, sys, pathlib

SRC = pathlib.Path(sys.argv[1]); DST = pathlib.Path(sys.argv[2])

# --- tokens that are STRUCTURE/SCHEMA/CATEGORY/SENTINEL, never redacted --------
WHITELIST = {
    "VC_Item","VC_ID","VC_SYRS","VC_SYS","Pass_Fail_Criteria","Issue_Source",
    "Source_Complaint","CVE_Reference","NO_NOVEL_VC_FOUND","Golden_VC",
    "Golden_VC_count","Golden_VC_excerpt","Generated_VC","Row_Number",
    "Correctness_1to5","Novelty_YN","Usefulness_YN","Scope_ECU_Net_HW_OOS",
    "SYRS_ID","Body_Control","IO_HMI","System_State","Functional_Safety",
    "Comm_Stack","Communication_Stack","System_State_Mgmt","Diagnostic_Services",
    "Fail_Present","Not_Active","ISO_15765","ISO_14229","ISO_11898",
}
# CSV columns whose entire content is proprietary spec -> blanked
BLANK_COLS = {"Requirement","Golden_VC_excerpt"}
# CSV columns that are free text -> signal-token redaction applied
TEXT_COLS  = {"Generated_VC","Notes"}
# JSON keys whose value is proprietary spec -> blanked
BLANK_KEYS = {"requirement","golden_vc","syrs_text","golden_vc_excerpt","syrs_requirement"}
# JSON keys kept verbatim (ids / public refs / labels)
SKIP_KEYS  = {"syrs_id","id","vc_id","issue_source","source_complaint","category",
              "channel","role","model","llm"}

REDACT_BLANK = "<REDACTED: proprietary SYRS text>"
SIG_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
_sigmap, _ctr = {}, [0]

def _placeholder(tok):
    if tok in _sigmap: return _sigmap[tok]
    _ctr[0]+=1; _sigmap[tok]=f"<SIG_{_ctr[0]}>"; return _sigmap[tok]

def redact_text(s):
    if not isinstance(s,str): return s
    def repl(m):
        t=m.group(0)
        return t if t in WHITELIST else _placeholder(t)
    return SIG_RE.sub(repl, s)

def _chanC_key(k):
    k=k.lower(); return "chc" in k or "cve" in k or k in ("c","channel_c","channelc")

def walk_json(o, key=None):
    if isinstance(o,dict):
        return {k:(REDACT_BLANK if k.lower() in BLANK_KEYS
                   else (v if k.lower() in SKIP_KEYS else walk_json(v,k)))
                for k,v in o.items() if not _chanC_key(k)}
    if isinstance(o,list): return [walk_json(x,key) for x in o]
    if isinstance(o,str):  return redact_text(o)
    return o

def _is_chanC(v):
    v=v.strip().upper(); return v=="C" or v.startswith("C-") or "CVE" in v

def do_csv(src,dst):
    with open(src,newline="",encoding="utf-8-sig") as f: rows=list(csv.reader(f))
    if not rows: return
    hdr=rows[0]; idx={h:i for i,h in enumerate(hdr)}
    chan_i=next((i for h,i in idx.items() if h.strip().lower()=="channel"), None)
    body=rows[1:]
    if chan_i is not None:        # drop Channel-C (CVE) rows -> A+B+baseline (489) only
        body=[r for r in body if not (chan_i<len(r) and _is_chanC(r[chan_i]))]
    for r in body:
        for col,i in idx.items():
            if i>=len(r): continue
            if col in BLANK_COLS: r[i]=REDACT_BLANK
            elif "id" in col.lower(): pass                 # keep IDs verbatim (SYRS_ID etc.)
            else: r[i]=redact_text(r[i])                   # redact ALL other cells
    dst.parent.mkdir(parents=True,exist_ok=True)
    with open(dst,"w",newline="",encoding="utf-8") as f: csv.writer(f).writerows([hdr]+body)

def do_text(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    open(dst,"w",encoding="utf-8").write(redact_text(open(src,encoding="utf-8").read()))

def do_json(src,dst):
    txt=open(src,encoding="utf-8").read()
    dst.parent.mkdir(parents=True,exist_ok=True)
    try:
        json.dump(walk_json(json.loads(txt)),open(dst,"w",encoding="utf-8"),
                  ensure_ascii=False,indent=1)
    except json.JSONDecodeError:   # jsonl
        with open(dst,"w",encoding="utf-8") as out:
            for line in txt.splitlines():
                line=line.strip()
                if not line: continue
                out.write(json.dumps(walk_json(json.loads(line)),ensure_ascii=False)+"\n")

# --- file plan (A+B only; NO cve/secoc/chC) -----------------------------------
JOBS = [
  ("evaluation_template/eval_E2.csv","evaluation_data/eval_E2.csv"),
  ("evaluation_template/eval_E3.csv","evaluation_data/eval_E3.csv"),
  ("evaluation_template/eval_E3_batch1_rows1-201.csv","evaluation_data/eval_E3_batch1.csv"),
  ("evaluation_template/eval_E3_batch2_rows202-403.csv","evaluation_data/eval_E3_batch2.csv"),
  ("evaluation_template/eval_E4.csv","evaluation_data/eval_E4.csv"),
  ("evaluation_template/eval_E2_secondary_task.csv","evaluation_data/eval_E2_secondary.csv"),
  ("evaluation_template/eval_E4_secondary_task.csv","evaluation_data/eval_E4_secondary.csv"),
  ("evaluation_template/_adjudication_B.csv","evaluation_data/E1_adjudication.csv"),
  ("evaluation_template/evaluation_sheet_merged.csv","evaluation_data/evaluation_sheet_merged.csv"),
  ("docs/ablation_e1_ratings.csv","ablation/ablation_e1_ratings.csv"),
  ("docs/ablation_e2_ratings.csv","ablation/ablation_e2_ratings.csv"),
  ("docs/ablation_e3_ratings.csv","ablation/ablation_e3_ratings.csv"),
  ("docs/ablation_e4_ratings.csv","ablation/ablation_e4_ratings.csv"),
  ("output/generated_vcs.json","generated_vcs/chA_github_generated_vcs.json"),
  ("output/matches.json","generated_vcs/chA_github_matches.json"),
  ("output_nhtsa/nhtsa_generated_vcs.json","generated_vcs/chB_nhtsa_generated_vcs.json"),
  ("output_nhtsa/nhtsa_matches.json","generated_vcs/chB_nhtsa_matches.json"),
  ("output_baseline/baseline_vcs.json","generated_vcs/baseline_vcs.json"),
  ("output_ablation/abl_lm_chA_generated_vcs.json","generated_vcs/ablation/abl_lm_chA.json"),
  ("output_ablation/abl_lm_chB_generated_vcs.json","generated_vcs/ablation/abl_lm_chB.json"),
  ("output_ablation/abl_nd_chA_generated_vcs.json","generated_vcs/ablation/abl_nd_chA.json"),
  ("output_ablation/abl_nd_chB_generated_vcs.json","generated_vcs/ablation/abl_nd_chB.json"),
  ("output_ablation/ablation_acceptance_results.json","generated_vcs/ablation/ablation_acceptance_results.json"),
  ("output_ablation/ablation_multirater_results.json","generated_vcs/ablation/ablation_multirater_results.json"),
  ("output_ablation/ablation_novel_rate_summary.json","generated_vcs/ablation/ablation_novel_rate_summary.json"),
  ("output_domain2/chA_generated_vcs.json","generated_vcs/domain2_chA_generated_vcs.json"),
  ("output_domain2/domain2_matches.json","generated_vcs/domain2_matches.json"),
]
SENS = ["deepseek-chat","deepseek-v4-flash","glm-5","kimi-k2.6","qwen-max","qwen-plus","qwen3.6-plus"]
for ch in ("chA","chB"):
    for m in SENS:
        JOBS.append((f"output_sensitivity/{ch}_{m}.jsonl",f"sensitivity/{ch}_{m}.jsonl"))

done=0
for s,d in JOBS:
    sp=SRC/s
    if not sp.exists(): continue
    (do_csv if sp.suffix==".csv" else do_json)(sp, DST/d); done+=1

# --- pass 1b: redact the .md protocol/prompt files already copied into DST -----
for md in DST.rglob("*.md"):
    if md.name in ("README.md","UPLOAD_WI.md"): continue
    do_text(md, md)

# --- pass 2: sweep bare camelCase / long (German) signal fragments -------------
STOP={"Status","Sensor","Vehicle","Speed","Command","Response","Request","Signal",
 "Output","Input","State","Mode","Fault","Error","Timeout","Active","Inactive",
 "Voltage","Current","Switch","Light","Ambient","Ignition","Brake","Steering",
 "Angle","Indicator","Button","Volume","Audio","Power","Safety","Condition",
 "Initialization","Operational","Diagnostic","Network","Message","Frame","Payload",
 "Transport","Protocol","Address","Server","Client","Timer","Counter","Sequence",
 "Number","Value","Boundary","Criteria","Method","Technique","Positive","Negative",
 "Dynamic","Static","Reference","Complaint","Source","Present","Module","System",
 "Control","Function","Service","Format","Version","Default","Enable","Disable","Update"}
STOP |= {"Communication","Diagnostics","Diagnostic","Chassis","Powertrain",
 "Transmission","Acceleration","Temperature","Frequency","Threshold","Parameter",
 "Configuration","Calibration","Information","Application","Implementation",
 "Interface","Component","Requirement","Verification","Validation","Specification",
 "Behavior","Behaviour","Reception","Functional","Electrical","Mechanical",
 "Hardware","Software","Operation","Detection","Activation","Deactivation",
 "Transition","Position","Standard","Internal","External","Maximum","Minimum",
 "Nominal","Tolerance","Reassembly","Consecutive","Multiframe","Scenario",
 "Procedure","Expected","Received","Transmit","Receive","Controller","Stalk",
 "Steering","Network","Message","Vehicle","Channel","Baseline","Ablation",
 "Sensitivity","Generated","Acceptance","Evaluation","Rationale","Embedding"}
def is_camel(p): return re.search(r"[a-z][A-Z]", p) is not None
frags=set()
for sig in _sigmap:
    for part in re.split(r"[_\W]+", sig):
        if part and part not in WHITELIST and part not in STOP and (is_camel(part) or len(part)>=8):
            frags.add(part)
order=sorted(frags,key=len,reverse=True)
swept=0
for fp in [p for p in DST.rglob("*") if p.is_file() and p.suffix in (".csv",".json",".jsonl",".md")]:
    if fp.name in ("README.md","UPLOAD_WI.md","redact.py"): continue
    t=fp.read_text(encoding="utf-8"); orig=t
    for fr in order: t=t.replace(fr,"<SIG>")
    if t!=orig: fp.write_text(t,encoding="utf-8"); swept+=1

print(f"redacted {done} data files; pass2 swept {swept} files; {len(_sigmap)} signals + {len(frags)} fragments masked")
json.dump(_sigmap, open(DST/"REDACTION_MAP.json","w",encoding="utf-8"),
          ensure_ascii=False,indent=1)
