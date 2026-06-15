# Field2VC — Replication Package

Replication artifact for a double-blind conference submission on
failure-grounded verification-criteria (VC) completion for automotive ECU
requirements.

> **Anonymous artifact for double-blind review.** No author, affiliation, or
> identifying information is included. Please do not attempt to de-anonymize.

## What this package supports

`Field2VC` is a five-stage pipeline (Fetch → Filter → Match → Generate →
Review) that completes ASPICE SYS.2 verification criteria (VCs) by grounding LLM
generation in empirical field-failure evidence from two external channels:
open-source GitHub issues (**Channel A**) and NHTSA ODI consumer complaints
(**Channel B**).

This package lets an independent reviewer **re-run the pipeline**, **inspect the
prompts and configuration**, and **reproduce the statistical analysis** behind
every reported number (acceptance rates, Fisher/Holm tests, Cohen's *h*,
Gwet's AC1, ablation, cross-LLM sensitivity).

## Contents

| Folder | Contents |
|---|---|
| `pipeline/` | Stage 1–5 scripts: corpus fetch + filter + embed-match + generate (`poc_pipeline.py`), Channel-B/NHTSA (`poc_nhtsa.py`), no-context baseline (`poc_baseline.py`), ablations (`poc_ablation.py`), cross-LLM sensitivity (`poc_sensitivity.py`), Domain-2 pilot (`poc_domain2_run.py`) |
| `prompts/` | `prompt_registry.md` (all Stage-2 filtering and Stage-4 generation prompts) and `model_config_manifest.md` (model/version configuration; API keys are read from environment variables, never stored) |
| `evaluation/` | `EVALUATION_PROTOCOL.md` (Framework B criteria, rater roles, two-rater + E1-adjudication procedure, adjudicator-transparency note) and `matching_precision_sample.csv` (200-pair annotated retrieval-precision study, seed=42, 73.5 % overall precision) |
| `ablation/` | 50-item ablation per-rater rating CSVs (E1–E4) and the RQ3 replication table (`eval_2x2_FL_RQ3_replication.csv`); ablation methodology is described in the paper (§IV, RQ3) |
| `syrs_corpus/` | `syrs_with_golden_vcs.json` — de-identified SYRS corpus covering all 350 benchmark items (307 of which entered evaluation) with expert-annotated golden VCs |
| `stats/` | Three self-contained canonical reproducers (stdlib only): `reproduce_main.py` (RQ1 accept rates + OR/Fisher/Holm/Cohen's *h*, RQ2 scope-stratified, Gwet's AC1 IAA, and adjudication-sensitivity floors), `reproduce_ablation.py` (RQ3 ablation: FL/Abl-LM/Abl-NF + reject attribution), and `reproduce_sensitivity.py` (RQ4 cross-LLM generation rates, 7 models). Each prints every number next to its paper value. |
| `evaluation_data/` | **De-identified** per-VC ratings (E2/E3/E4), majority labels, and E1 adjudication for all 489 VCs |
| `generated_vcs/` | **De-identified** generated VC corpus: Ch-A (GitHub), Ch-B (NHTSA), baseline, ablations, Domain-2 |
| `sensitivity/` | Cross-LLM novel-rate runs (7 LLMs × Ch-A/Ch-B), de-identified |
| `redact.py` | The auditable de-identification script used to produce this package |

## Reproducing the statistics

```bash
# No third-party dependencies — Python 3.9+ standard library only.
python stats/reproduce_main.py        # RQ1 rates + OR/Fisher/Holm/Cohen's h, RQ2 scope, Gwet's AC1 IAA, adjudication sensitivity
python stats/reproduce_ablation.py    # RQ3 ablation: FL/Abl-LM/Abl-NF + reject attribution
python stats/reproduce_sensitivity.py # RQ4 cross-LLM generation-rate proxy (7 models)
```

`reproduce_main.py` reads the per-VC ratings in `evaluation_data/`;
`reproduce_ablation.py` reads `ablation/` and `generated_vcs/ablation/`.
Each script prints every value next to its paper number for direct comparison.
The acceptance/adjudication model is documented in each script's header
(each VC scored by exactly two external raters; E1 adjudicates split decisions
under Framework~B). Cross-LLM sensitivity (RQ4) generation rates are derived
from the per-call logs under `sensitivity/`.

## NOTE on de-identification

The SYRS items are drawn from a **proprietary automotive ECU specification**.
To protect that IP while supporting replication, this package is **de-identified**
by `redact.py` (run with `--spec-readable`): the SYRS requirement text and
golden-VC text are released in readable form with proprietary component/signal
names replaced by stable placeholders (`<SIG_n>`); the placeholder-to-original
mapping is never distributed. Public protocol/standard vocabulary (ISO 15765-2,
LIN, UDS, CAN, ISO 14229 service and NRC names), test structure, public
`Issue_Source` references, and all numeric scores/labels are preserved verbatim.

`syrs_corpus/syrs_with_golden_vcs.json` contains the de-identified corpus
covering the **full 350-item benchmark** (208 Channel-A, 142 Channel-B), each
with its channel, category, quality tier, requirement text, and golden
(ground-truth) VCs — sufficient to independently re-run matching, generation,
and the novelty assessment for all released labels. Of the 350, **307 entered
expert evaluation**; the remaining 43 (all Channel-A Diagnostics) carry golden
VCs but yielded no generated VC under any pipeline condition, so they back no
released rating or reported statistic.

## License

- **Code** (`pipeline/`, `stats/`): MIT.
- **Data and documentation**: CC-BY-4.0.

External failure evidence (GitHub issues, NHTSA ODI complaints) is public data
retrieved via the respective public APIs and cited by source ID where used.

## Known data limitation

In the merged rating sheet, the free-text `E2_Notes` column is misaligned for
some Channel-B rows (an artifact of parsing E2's free-form review output).
The numeric/categorical score columns (`Correctness`, `Novelty`, `Usefulness`,
`Scope`) were cross-checked against E2's original task sheet and are correct;
all reported statistics derive from the score columns only. Treat Channel-B
`E2_Notes` text as unreliable.
