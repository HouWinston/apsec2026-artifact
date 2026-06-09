# IssueDriven-VC — Replication Package

Replication artifact for a double-blind conference submission on
failure-grounded verification-criteria (VC) completion for automotive ECU
requirements.

> **Anonymous artifact for double-blind review.** No author, affiliation, or
> identifying information is included. Please do not attempt to de-anonymize.

## What this package supports

`IssueDriven-VC` is a five-stage pipeline (Fetch → Filter → Match → Generate →
Review) that completes ASPICE SYS.2 verification criteria (VCs) by grounding LLM
generation in empirical field-failure evidence from two external channels:
open-source GitHub issues (**Channel A**) and NHTSA recall notices (**Channel B**).

This package lets an independent reviewer **re-run the pipeline**, **inspect the
prompts and configuration**, and **reproduce the statistical analysis** behind
every reported number (acceptance rates, Fisher/Holm tests, Cohen's *h*,
Gwet's AC1, ablation, cross-LLM sensitivity).

## Contents

| Folder | Contents |
|---|---|
| `pipeline/` | Stage 1–5 scripts: corpus fetch + filter + embed-match + generate (`poc_pipeline.py`), Channel-B/NHTSA (`poc_nhtsa.py`), no-context baseline (`poc_baseline.py`), ablations (`poc_ablation.py`), cross-LLM sensitivity (`poc_sensitivity.py`), Domain-2 pilot (`poc_domain2_run.py`), routing + traceability + E1 packet generation |
| `prompts/` | `prompt_registry.md` (all Stage-2 filtering and Stage-4 generation prompts) and `model_config_manifest.md` (model/version configuration; API keys are read from environment variables, never stored) |
| `evaluation/` | Framework-B evaluation protocol, E1 adjudicator guide, annotation guide, and rater instructions |
| `ablation/` | 50-item ablation evaluation instructions and rater brief |
| `stats/` | Analysis scripts (`stats_optionC_AB.py`, `stats_optionC_iaa.py`, `stats_evaluator.py`, ablation/routing analysis, token-cost extraction) |
| `stats/tables/` | Aggregate result tables: channel-vs-baseline, A+B combined, raw-vs-Holm-corrected p-values, traceability metrics |
| `evaluation_data/` | **De-identified** per-VC ratings (E2/E3/E4), majority labels, and E1 adjudication for all 489 VCs |
| `generated_vcs/` | **De-identified** generated VC corpus: Ch-A (GitHub), Ch-B (NHTSA), baseline, ablations, Domain-2 |
| `sensitivity/` | Cross-LLM novel-rate runs (7 LLMs × Ch-A/Ch-B), de-identified |
| `redact.py` | The auditable de-identification script used to produce this package |

## Reproducing the statistics

```bash
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt                   # numpy, scipy, pandas, statsmodels
python stats/stats_optionC_AB.py                  # channel-vs-baseline: rates, OR, Cohen's h, Fisher + Holm
python stats/stats_optionC_iaa.py                 # Gwet's AC1 inter-annotator agreement
```

The scripts read the per-VC rating CSVs in `evaluation_data/` and reproduce the
tables under `stats/tables/`.

## NOTE on de-identification

The 347 SYRS items are drawn from a **proprietary automotive ECU specification**.
To protect that IP while supporting replication, this package is **de-identified**
by `redact.py`: proprietary SYRS requirement text and golden-VC text are blanked
(`<REDACTED: proprietary SYRS text>`), and component signal names are replaced by
stable placeholders (`<SIG_n>`). Public protocol/standard names (ISO 15765-2,
LIN, UDS, CAN), test structure, public `Issue_Source` references, and all numeric
scores/labels are preserved, so the statistical analysis is **fully reproducible**
without the proprietary corpus.

## License

- **Code** (`pipeline/`, `stats/`): MIT.
- **Data and documentation**: CC-BY-4.0.

External failure evidence (GitHub issues, NHTSA recalls) is public data retrieved
via the respective public APIs and cited by source ID where used.
