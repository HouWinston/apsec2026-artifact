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

Usage:  python redact.py <SRC_poc_dir> <DST_artifact_dir> [--spec-readable]

Release modes
-------------
  default (option A, "blanked"):   proprietary SYRS/golden free text is BLANKED.
  --spec-readable (option B):      SYRS/golden free text is RELEASED after
      signal-token de-identification (readable text, <SIG_n> placeholders), and
      a de-identified SYRS+golden corpus file is exported to syrs_corpus/.
      The placeholder mapping is written to the PRIVATE source tree only
      (never into the artifact).
"""
import csv, json, re, sys, pathlib

SRC = pathlib.Path(sys.argv[1]); DST = pathlib.Path(sys.argv[2])
MODE = "readable" if "--spec-readable" in sys.argv[3:] else "blank"

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

SYRSREF_RE = re.compile(r"\bSYRS[\s_]*\d{4,}\b")          # proprietary internal req. numbers
CAMEL_RE   = re.compile(r"\b[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*\b")  # bare camelCase signal/feature names
# standard ISO-14229 (UDS) / ISO-15765-2 service names are public, not proprietary -> keep
STD_TERMS = {"ReadDataByIdentifier","WriteDataByIdentifier","ClearDiagnosticInformation",
 "ReadDTCInformation","TransferData","RequestDownload","RequestUpload","RoutineControl",
 "SecurityAccess","TesterPresent","DiagnosticSessionControl","CommunicationControl",
 "ControlDTCSetting","InputOutputControlByIdentifier","RequestTransferExit","ResponsePending",
 "SingleFrame","FirstFrame","ConsecutiveFrame","FlowControl","BoundaryValue","FaultInjection",
 # public ISO 14229 NRC mnemonics — not proprietary
 "SecurityAccessDenied","RequestOutOfRange","GeneralProgrammingFailure",
 "RequestCorrectlyReceived","RequestSequenceError","SubFunctionNotSupported",
 "ServiceNotSupportedInActiveSession","ConditionsNotCorrect","ResponseTooLong",
 "IncorrectMessageLengthOrInvalidFormat","BusyRepeatRequest"}

def redact_text(s):
    if not isinstance(s,str): return s
    s = SYRSREF_RE.sub("<SYRS_REF>", s)
    s = SIG_RE.sub(lambda m: m.group(0) if m.group(0) in WHITELIST else _placeholder(m.group(0)), s)
    s = CAMEL_RE.sub(lambda m: m.group(0) if m.group(0) in STD_TERMS else "<SIG>", s)
    return s

def _chanC_key(k):
    k=k.lower(); return "chc" in k or "cve" in k or k in ("c","channel_c","channelc")

def _spec_field(v):
    """Proprietary spec text: blank (option A) or de-identify readable (option B)."""
    return redact_text(v) if MODE == "readable" else REDACT_BLANK

def walk_json(o, key=None):
    if isinstance(o,dict):
        return {k:(_spec_field(v) if k.lower() in BLANK_KEYS
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
            if col in BLANK_COLS: r[i]=_spec_field(r[i])
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

# --- option B: export de-identified SYRS + golden-VC corpus (pipeline-attempted set)
if MODE == "readable":
    data_dir = SRC.parent / "data"
    corpus = json.load(open(data_dir/"SYRS_Classified_20260429_085505.json",encoding="utf-8"))
    golden = json.load(open(data_dir/"golden_vc_text_20260429_091653.json",encoding="utf-8"))
    chA = {x["syrs_id"] for x in json.load(open(SRC/"output/matches.json",encoding="utf-8"))}
    chB = {x["syrs_id"] for x in json.load(open(SRC/"output_nhtsa/nhtsa_matches.json",encoding="utf-8"))}
    used, seen, items = chA|chB, set(), []
    TIER_EN = {"优秀":"excellent","良好":"good"}
    for tier, cats in corpus.items():
        for cat, lst in cats.items():
            for it in (lst if isinstance(lst,list) else [lst]):
                sid = it["SYRS_ID"]
                if sid not in used or sid in seen: continue
                seen.add(sid)
                items.append({
                    "syrs_id": sid,
                    "channel": "A-GitHub" if sid in chA else "B-NHTSA",
                    "category": cat,
                    "quality_tier": TIER_EN.get(tier, tier),
                    "requirement": redact_text(it["System_Requirements"]),
                    "golden_vc": redact_text(golden.get(sid, "")),
                })
    items.sort(key=lambda x: x["syrs_id"])
    outp = DST/"syrs_corpus"/"syrs_with_golden_vcs.json"
    outp.parent.mkdir(parents=True,exist_ok=True)
    json.dump(items, open(outp,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"option-B corpus release: {len(items)} SYRS items "
          f"(A:{sum(1 for i in items if i['channel']=='A-GitHub')} "
          f"B:{sum(1 for i in items if i['channel']=='B-NHTSA')}) -> {outp}")

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
STOP |= {"Security","Unlock","Unlocked","Confirmation","Precondition","Preconditions",
 "Identifier","Humidity","Pressure","Irradiance","Luminance","Brightness","Headlight",
 "Headlights","Wiper","Wipers","Daytime","Nighttime","Latency","Measurement","Resolution",
 "Continuous","Duration","Plausibility","Consistency","Redundant","Redundancy","Interference"}
_stop_lc = {s.lower() for s in STOP} | {w.lower() for w in WHITELIST} | {t.lower() for t in STD_TERMS}
def is_camel(p): return re.search(r"[a-z][A-Z]", p) is not None
def _protected(part):
    # case-insensitive stop check + never sweep fragments of public standard terms
    pl = part.lower()
    return pl in _stop_lc or any(pl in t.lower() for t in STD_TERMS)
frags=set()
for sig in _sigmap:
    for part in re.split(r"[_\W]+", sig):
        if part and part not in WHITELIST and not _protected(part) and (is_camel(part) or len(part)>=8):
            frags.add(part)
order=sorted(frags,key=len,reverse=True)
swept=0
for fp in [p for p in DST.rglob("*") if p.is_file() and p.suffix in (".csv",".json",".jsonl",".md")]:
    if fp.name in ("README.md","UPLOAD_WI.md","redact.py"): continue
    t=fp.read_text(encoding="utf-8"); orig=t
    for fr in order: t=t.replace(fr,"<SIG>")
    if t!=orig: fp.write_text(t,encoding="utf-8"); swept+=1

print(f"redacted {done} data files; pass2 swept {swept} files; {len(_sigmap)} signals + {len(frags)} fragments masked")
# --- terminology normalization to match the paper (Distill->Filter, Abl-ND->Abl-NF) ---
TERMMAP=[("Abl-ND","Abl-NF"),("abl_nd","abl_nf"),("No Distill","No Filter"),
         ("Distillation","Filtering"),("distillation","filtering"),
         ("Distill","Filter"),("distill","filter")]
for fp in [p for p in DST.rglob("*") if p.is_file() and p.suffix in (".csv",".json",".jsonl",".md")]:
    if fp.name=="REDACTION_MAP.json": continue
    t=fp.read_text(encoding="utf-8"); o=t
    for a,b in TERMMAP: t=t.replace(a,b)
    if t!=o: fp.write_text(t,encoding="utf-8")
for fp in list(DST.rglob("abl_nd_*")):
    fp.replace(fp.with_name(fp.name.replace("abl_nd_","abl_nf_")))

# PRIVATE mapping (placeholder -> original proprietary name). NEVER ship in DST:
# with the map, the de-identification is reversible.
json.dump(_sigmap, open(SRC/"redaction_map_private.json","w",encoding="utf-8"),
          ensure_ascii=False,indent=1)
stale = DST/"REDACTION_MAP.json"
if stale.exists(): stale.unlink()

# --- NDA review report: surviving Capitalized tokens in released spec text -----
if MODE == "readable":
    from collections import Counter
    final = (DST/"syrs_corpus"/"syrs_with_golden_vcs.json").read_text(encoding="utf-8")
    toks = Counter(t for t in re.findall(r"\b[A-Z][A-Za-z]{3,}\b", final)
                   if t not in STOP and t not in WHITELIST and t not in STD_TERMS
                   and not t.startswith("SIG"))
    rpt = SRC/"release_review_report.txt"
    with open(rpt,"w",encoding="utf-8") as f:
        f.write("Surviving capitalized tokens in syrs_with_golden_vcs.json\n")
        f.write("(review before publishing; add proprietary ones to redact.py and re-run)\n\n")
        for t,n in toks.most_common(120): f.write(f"{n:5d}  {t}\n")
    print(f"NDA review report -> {rpt}")
