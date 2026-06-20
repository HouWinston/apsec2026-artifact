# Evaluation Protocol (Three-Criterion C/N/U)

Human evaluation protocol for the generated Verification Criteria (VCs). This
single document supersedes the earlier per-rater stub files.

## Acceptance criterion

Each VC is scored on three dimensions; it is **accepted iff all three hold**:

| Dim | Meaning | Scale | Accept threshold |
|---|---|---|---|
| **C** — Completeness | Does the SYRS omit this VC? | 1–5 | C ≥ 3 |
| **N** — Novelty | Absent from the SYRS and its existing golden VCs? | Y/N | N = Y |
| **U** — Usefulness | Actionable for downstream test design / qualification? | Y/N | U = Y |

`Accept ⇔ (C ≥ 3) AND (N = Y) AND (U = Y)`.

## Raters

Four raters spanning the three ASPICE V&V stakeholder roles:

- **E1** — Embedded-systems project manager (10 yr); **adjudicator**.
- **E2** — ASPICE assessor and functional-safety consultant.
- **E3** — PhD candidate in automotive software testing.
- **E4** — Senior functional-test engineer (OEM/Tier-1).

## Procedure

1. Each VC receives **exactly two independent external ratings** from E2/E3/E4.
2. The per-VC label is the **majority** of the present raters where they agree.
3. A VC is a **split** when the two raters disagree on the accept label or
   differ by ≥2 on C; **E1 adjudicates** splits under this protocol.
4. E1 adjudicated **285 of 489** VCs (the splits): 50/87 Channel-A,
   89/128 Channel-B, 146/274 baseline.

## Adjudicator transparency (see paper §VI)

E1 serves as the internal adjudicator; E2–E4 are independent external raters.
The adjudicator was **not blind** to the generation channel.
To constrain adjudicator influence, E1's rulings were bound to this protocol
rather than free judgement, and on disputed Channel-B acceptances they
**followed the rulings of E2** (an independent ASPICE assessor). The headline
rates are therefore **adjudication-dependent**; a no-E1 floor and an
agreed-subset sensitivity analysis are reported in the paper and reproduced by
`stats/reproduce_main.py`. Single-adjudicator, non-blind scoring is a stated
limitation; a larger blinded independent panel is the natural strengthening.

## Released files

- `evaluation_data/evaluation_sheet_merged.csv` — per-VC ratings (E2/E3/E4),
  E1 columns, majority labels, for all 489 VCs.
- `evaluation_data/E1_adjudication.csv` — the 285 E1-adjudicated split rows.
- `evaluation/matching_precision_sample.csv` — 200-pair retrieval-precision
  study (seed 42; 73.5 % overall).
- `ablation/` — the 50-item RQ3 ablation ratings and replication table.
