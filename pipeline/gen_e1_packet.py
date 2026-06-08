"""Generate E1 adjudication packet for SecOC v2 items where the 3 raters SPLIT on
accept/reject (the genuinely contested items). Unanimous items keep their verdict.
Per Framework B: E1 (domain expert) independently rules on split items; E1's verdict
is final for those. Neutral presentation -- both directions of disagreement included.
"""
import csv, json
from pathlib import Path

WS = Path(__file__).parent / "output_secoc"

tmpl = {}
with open(WS / "secoc_eval_template_v2_E2.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        tmpl[int(r["Item_No"])] = r["SYRS_ID"]
gen = {r["syrs_id"]: r for r in json.load(open(WS / "secoc_generated_vcs.json", encoding="utf-8"))}


def parse_md(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        cells = [c.strip().strip("*").strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        if not cells or not cells[0].isdigit():
            continue
        it = int(cells[0]); rest = cells[1:]
        if rest and rest[0].startswith("SYRS"):
            rest = rest[1:]
        out[it] = {"C": rest[0], "N": rest[1], "U": rest[2],
                   "Notes": rest[-1] if len(rest) > 3 else ""}
    return out


def parse_csv(path):
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out[int(r["Item_No"])] = {"C": r["Correctness_1to5"], "N": r["Novelty_YN"],
                                      "U": r["Usefulness_YN"], "Notes": r.get("Notes", "")}
    return out


E = {"E2": parse_md(WS / "secoc_eval_filled_E2V2.txt"),
     "E3": parse_md(WS / "secoc_eval_filled_E3V2.txt"),
     "E4": parse_csv(WS / "secoc_eval_filled_E4V2.txt")}


def acc(d):
    try:
        c = int(float(d["C"]))
    except (TypeError, ValueError):
        return None
    return c >= 3 and d["N"].upper().startswith("Y") and d["U"].upper().startswith("Y")


items = sorted(tmpl)
unanimous_accept = [it for it in items if all(acc(E[k][it]) for k in E)]
unanimous_reject = [it for it in items if all(acc(E[k][it]) is False for k in E)]
split = [it for it in items if it not in unanimous_accept and it not in unanimous_reject]

print(f"unanimous accept: {len(unanimous_accept)}  unanimous reject: {len(unanimous_reject)}  SPLIT(need E1): {len(split)}")

# fillable CSV
with open(WS / "secoc_e1_adjudication.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["Item_No", "SYRS_ID", "E2_C", "E2_N", "E2_U", "E3_C", "E3_N", "E3_U",
                "E4_C", "E4_N", "E4_U", "E1_Correctness_1to5", "E1_Novelty_YN", "E1_Usefulness_YN", "E1_Notes"])
    for it in split:
        w.writerow([it, tmpl[it]] + [E[k][it][x] for k in ("E2", "E3", "E4") for x in ("C", "N", "U")] + ["", "", "", ""])

# readable markdown packet
fence = chr(96) * 3
L = ["# E1 Adjudication Packet - SecOC v2 split items (Framework B)", "",
     f"{len(split)} contested items (raters split on accept/reject). For each, give E1's "
     "Correctness(1-5)/Novelty(Y/N)/Usefulness(Y/N) in secoc_e1_adjudication.csv.",
     "Accept = C>=3 AND N=Y AND U=Y. Judge independently; do not follow the majority.",
     f"(Unanimous: {len(unanimous_accept)} accept + {len(unanimous_reject)} reject are already settled.)", ""]
for it in split:
    sid = tmpl[it]
    L += [f"## Item {it} - {sid}", f"**Requirement:** {gen[sid]['requirement'][:240]}", "",
          "**Generated VC:**", fence, gen[sid]["generated_vc"][:1400], fence, "",
          f"- E2: C={E['E2'][it]['C']} N={E['E2'][it]['N']} U={E['E2'][it]['U']} | {E['E2'][it]['Notes']}",
          f"- E3: C={E['E3'][it]['C']} N={E['E3'][it]['N']} U={E['E3'][it]['U']} | {E['E3'][it]['Notes']}",
          f"- E4: C={E['E4'][it]['C']} N={E['E4'][it]['N']} U={E['E4'][it]['U']} | {E['E4'][it]['Notes']}",
          "- **E1 ruling:** C=___ N=___ U=___", "", "---", ""]
(WS / "secoc_e1_adjudication_packet.md").write_text("\n".join(L), encoding="utf-8")

base_accept = len(unanimous_accept)
print(f"已生成 secoc_e1_adjudication.csv + secoc_e1_adjudication_packet.md ({len(split)} 条待裁)")
print(f"基底(已定接受)={base_accept}; 最终接受率 = ({base_accept} + E1判接受的split数)/32")
