# Field2VC — Research Artifacts

Field2VC uses field-failure evidence to generate verification criteria (VCs) for automotive system requirements.

This repository accompanies the APSEC 2026 paper and provides evaluation records, result summaries, source-derived prompt templates, model configuration metadata, and a numerical reanalysis script.

## Contents

| Location | Contents |
|---|---|
| `data/` | Pseudonymized, text-free ratings and numerical generation records |
| `results/` | Acceptance, generation, ablation, sensitivity and agreement summaries; saved statistical outputs |
| `docs/DATA_DICTIONARY.md` | File definitions, fields, units and coverage |
| `docs/EVALUATION_METHODS.md` | Evaluation unit, scoring criteria, adjudication and calculation definitions |
| `prompts/` | Source-derived prompt templates and model configuration metadata |
| `scripts/reanalyze_numeric.py` | Python script for numerical reanalysis |
| `MANIFEST.sha256` | File-integrity checksums for this release |

## Reanalysis

From the repository root, with Python 3.9 or later:

```bash
python -B scripts/reanalyze_numeric.py
```

The script recalculates acceptance, generation, sensitivity and agreement summaries from the released records and checks nine result CSVs. It uses only the Python standard library, makes no model or API calls, and leaves the data unchanged. See [Evaluation Methods](docs/EVALUATION_METHODS.md) for calculations and checker coverage.

## Evaluation Data

- **Main evaluation:** 489 rated outputs across 307 requirement groups. Each output contains two VC candidates, with ratings recorded at the output level.
- **RQ3 ablation:** 50 FL items and 400 LM/NF condition ratings.
- **RQ4 sensitivity:** 3,841 numerical generation records across seven model configurations and two evidence channels.

Channel A uses GitHub evidence; Channel B uses NHTSA evidence. Baseline generation uses no field-failure context. Identifiers are pseudonymized and preserve within-release grouping; missing ratings remain empty.

See the [Data Dictionary](docs/DATA_DICTIONARY.md) for fields, units and grouping details.

## Additional Materials

For materials beyond this public release and research access requests, see [Material Availability](AVAILABILITY.md).

## License

Numerical data, documentation and prompt templates are licensed under CC BY 4.0. The Python checker is licensed under MIT. See [LICENSE](LICENSE).
