# Field2VC — Numerical Results and Prompt Templates

Companion numerical materials for Field2VC, accepted at APSEC 2026.

Repository address: https://github.com/HouWinston/apsec2026-artifact

This release contains text-free evaluation records, aggregate results, evaluation-method documentation, source-derived prompt templates and model-configuration documentation, and an offline numerical reanalysis script. Industrial requirement specifications, existing and generated verification-criteria texts, text-bearing logs, and the original pipeline and analysis scripts are not publicly distributed.

The camera-ready article describes a broader replication package. The scope of public access is narrower than that description; [AVAILABILITY.md](AVAILABILITY.md) identifies the public and restricted materials. Requests for additional materials are considered case by case and do not guarantee access.

## Contents

| Location | Contents |
|---|---|
| `data/` | Pseudonymized, text-free ratings and numerical generation records |
| `results/` | Acceptance, generation, ablation, sensitivity and agreement summaries; saved outputs from offline statistical recomputation |
| `docs/DATA_DICTIONARY.md` | File definitions, field encodings, missingness, and linkage limits |
| `docs/EVALUATION_METHODS.md` | Evaluation unit, scoring criteria, adjudication and calculation definitions |
| `prompts/` | Main, baseline, ablation, sensitivity and Domain-2 prompt templates; model configuration and provenance limits |
| `scripts/reanalyze_numeric.py` | Standard-library checker using only public CSVs; no model/API calls |
| `MANIFEST.sha256` | File-integrity checksums for this release |

## Reanalyzing the released numbers

From the repository root, with Python 3.9 or later:

```bash
python -B scripts/reanalyze_numeric.py
```

The checker reads public `data/` records, recalculates the documented numerical summaries and compares them with `results/*.csv`. It exits with a nonzero status on a mismatch and does not modify the data. Its output specifies the checked coverage. Assigned benchmark totals are documented constants, not independently inferred from withheld requirements.

This script is a public-data adapter prepared on 2026-11-16, not the historical experiment runner. It does not regenerate the saved `reproduced_*.txt` outputs or rerun model generation. Prompt text is extracted from archived source constants; the configuration document distinguishes source defaults from recorded historical settings. Neither extraction nor numerical agreement proves which exact prompt or model backend served every historical call.

## Interpreting the data

The main evaluation contains 489 rated **outputs** involving 307 distinct requirements. Each output contains two VC candidates, but the historical records contain one score set per rater for the output. The data are not 978 independently scored VCs. E1 adjudicated 285 outputs; missing ratings remain missing.

Channel A denotes GitHub evidence, Channel B denotes NHTSA evidence, and Baseline denotes generation without field-failure context. New opaque identifiers preserve necessary within-release group relationships while removing original item identifiers. They do not establish independence between groups or guarantee anonymity against holders of prior copies.

RQ3 uses E2/E3/E4 majority acceptance for the 50-item ablation. RQ4 `is_novel` is a logged generation/sentinel indicator; it is not an expert novelty rating or a quality-acceptance label. Non-generation outcomes and all recorded numerical rows are retained; repeated sensitivity records are identified rather than silently discarded.

The release permits inspection and reanalysis of the supplied numerical records and inspection of the published templates. It does not permit end-to-end regeneration of the experiment or independent assessment of requirement/VC content. Saved statistical outputs are author-side recomputations, not independent validation of the scientific claims. Refer to the data dictionary for analyses not covered by these files.

## Requests

Contact **Wei Hou** at **71275902063@stu.ecnu.edu.cn** with subject `APSEC 2026 Field2VC Material Request`. Please identify the requested materials, intended use, and affiliation. Access depends on applicable permissions and confidentiality restrictions; some materials may remain unavailable.

## License

The numerical data, documentation and prompt templates actually included in this public release are provided under CC BY 4.0. The public Python checker is provided under MIT; see [LICENSE](LICENSE). This release does not license or provide access to withheld materials.
