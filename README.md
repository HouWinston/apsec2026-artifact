# Field2VC — Numerical Data and Results

Companion numerical materials for Field2VC, accepted at APSEC 2026.

Repository address: https://github.com/HouWinston/apsec2026-artifact

This release contains text-free evaluation records, aggregate results, and evaluation-method documentation. Industrial requirement specifications, existing and generated verification-criteria texts, prompts, source code, and analysis scripts are excluded from the public release.

The camera-ready article describes a broader replication package. The scope of public access is narrower than that description; [AVAILABILITY.md](AVAILABILITY.md) identifies the public and restricted materials. Requests for additional materials are considered case by case and do not guarantee access.

## Contents

| Location | Contents |
|---|---|
| `data/` | Pseudonymized, text-free ratings and numerical generation records |
| `results/` | Acceptance, generation, ablation, sensitivity and agreement summaries; saved outputs from offline statistical recomputation |
| `docs/DATA_DICTIONARY.md` | File definitions, field encodings, missingness, and linkage limits |
| `docs/EVALUATION_METHODS.md` | Evaluation unit, scoring criteria, adjudication and calculation definitions |
| `MANIFEST.sha256` | File-integrity checksums for this release |

## Interpreting the data

The main evaluation contains 489 rated **outputs** involving 307 distinct requirements. Each output contains two VC candidates, but the historical records contain one score set per rater for the output. The data are not 978 independently scored VCs. E1 adjudicated 285 outputs; missing ratings remain missing.

Channel A denotes GitHub evidence, Channel B denotes NHTSA evidence, and Baseline denotes generation without field-failure context. New opaque identifiers preserve necessary within-release group relationships while removing original item identifiers. They do not establish independence between groups or guarantee anonymity against holders of prior copies.

RQ3 uses E2/E3/E4 majority acceptance for the 50-item ablation. RQ4 `is_novel` is a logged generation/sentinel indicator; it is not an expert novelty rating or a quality-acceptance label. Non-generation outcomes and all recorded numerical rows are retained; repeated sensitivity records are identified rather than silently discarded.

The release permits inspection and reanalysis of the supplied numerical records. It does not permit end-to-end regeneration of the experiment or independent assessment of requirement/VC content. Saved statistical outputs are author-side recomputations, not independent validation of the scientific claims. Refer to the data dictionary for analyses not covered by these files.

## Requests

Contact **Wei Hou** at **71275902063@stu.ecnu.edu.cn** with subject `APSEC 2026 Field2VC Material Request`. Please identify the requested materials, intended use, and affiliation. Access depends on applicable permissions and confidentiality restrictions; some materials may remain unavailable.

## License

The numerical data and documentation actually included in this public release are provided under CC BY 4.0; see [LICENSE](LICENSE). This release does not license or provide access to withheld materials.
