# Numerical data dictionary

All CSV files are UTF-8 with a header. Empty cells mean missing/unrecorded values, never an imputed zero or a negative judgment. Derived decision fields use 1/0 unless a field explicitly retains the original categorical labels. Rates are proportions in [0,1]; saved textual outputs may display percentages.

## Files and units

| File | Rows / lines | Unit and coverage |
|---|---:|---|
| `data/main_ratings.csv` | 489 | One row per rated output; main C/N/U and scope ratings, derived acceptance and dispute flags. |
| `results/main_acceptance.csv` | 4 | Main acceptance counts, disputes and Wilson intervals; A+B is an aggregate, not extra observations. |
| `results/main_category_acceptance.csv` | 16 | Category-level pipeline-versus-baseline counts, including groups without a baseline. |
| `data/ablation_fl_ratings.csv` | 50 | One row per FL ablation item; all four raters, external majority, fixed rejection category. |
| `data/ablation_condition_ratings.csv` | 400 | Long-form Abl-LM/Abl-NF ratings: 50 items x 2 conditions x 4 raters. |
| `data/ablation_majority_items.csv` | 100 | One row per anonymous item and Abl-LM/Abl-NF condition; individual and majority decisions. |
| `results/ablation_acceptance.csv` | 3 | External-rater majority acceptance for FL, LM and NF. |
| `results/ablation_fl_reject_attribution.csv` | 3 | All 21 FL rejections in three fixed categories. |
| `data/sensitivity_records.csv` | 3841 | Every parsed numerical log record; generation proxy and within-key last-record selection. |
| `results/sensitivity_generation.csv` | 14 | Seven model configurations x two channels, with all-record and distinct-item counts. |
| `data/generation_records.csv` | 630 | Numerical generation/sentinel flags for every record in the main-generation source files. |
| `results/generation_flow.csv` | 3 | Assigned, observed, generated and rated item/output counts; these denominators differ. |
| `results/iaa_condition_rater_pair_counts.csv` | 9 | Retained joint-rating counts by analysis scope, condition and rater pair. |
| `results/iaa_per_dimension_by_rater_pair.csv` | 60 | Retained pair-level agreement, AC1 and effective n. |
| `results/iaa_summary.csv` | 20 | Retained unweighted mean AC1 over eligible rater pairs. |
| `results/reproduced_main.txt` | 51 lines | Saved stdout from the historical offline main statistical reproducer; category placeholders recoded. |
| `results/reproduced_ablation.txt` | 16 lines | Saved stdout from the historical offline ablation statistical reproducer. |
| `results/reproduced_sensitivity.txt` | 15 lines | Saved stdout from the historical offline sensitivity statistical reproducer. |

## Identity, grouping and order

- `Sample_ID` identifies a rated output or FL item with a new random identifier.
- `Requirement_Group_ID` preserves equality of the original requirement identifiers within the main, generation and sensitivity projections. No text or reverse mapping is public. The main ratings contain 307 distinct groups; the wider generation logs cover the 350-item benchmark. A common group does not imply a new independent observation.
- `Item_ID` links the two non-FL ablation conditions and their raters within the source-indexed 50-item set. X is presented as LM and Y as NF by matching original row indices and all 400 derived acceptance decisions against the retained canonical JSON. This is numerical reconciliation, not independent verification of a blind condition key, requirement identity, or original condition assignment. The FL and non-FL identifier domains remain unlinked: this release does not assert an unverified paired mapping.
- `Record_ID` is random. Main/FL outputs sort by random ID, and run records sort by random record ID rather than preserving their source global order.
- Sensitivity `Record_Order` is the 1-based order within one (Model, Channel, Requirement_Group_ID) key, not an original global line number. `Last_Record = 1` selects its final logged row for the retained historical calculation. All 3,841 records remain present, including 1,391 records in excess of one per key.
- `Has_Error = 1` indicates a nonempty error field in the source record. The error text itself is withheld. These rows remain in the data and are not silently excluded from the historical last-record calculation.

## Labels and rating fields

- `Channel`: A (GitHub evidence), B (NHTSA evidence), or Baseline. `A+B` occurs only as an aggregate result.
- `Category`: public broad categories retained from the source; two placeholder category labels have been recoded as `Category_03` and `Category_04`. This is a categorical relabeling, not a score change.
- `Condition`: FL, LM (Abl-LM), NF (Abl-NF), or the stated main-study grouping. Condition labels in retained agreement summaries follow their original fixed vocabulary.
- `Evaluator`: E1, E2, E3 or E4. E1 is the internal adjudicator in the main study; E2/E3/E4 are the external raters.
- `*_Correctness_1to5` / `*_C` / `C`: integer 1–5 when recorded.
- `*_Novelty_YN` / `*_N` / `N` and `*_Usefulness_YN` / `*_U` / `U`: Y/N when recorded.
- `*_Scope_ECU_Net_HW_OOS`: the source's fixed scope categories, with missing cells preserved.
- `*_Accept` / `Accept`: derived rater decision (1 accepted, 0 rejected, blank absent rating); result-table `Accept` is a count.
- `Dispute`: main-study acceptance disagreement or a C-score difference of at least two. `Final_Accept` applies the documented adjudication/majority rule.
- In the FL table only, `E1_Accept` through `E4_Accept` retain A/R (accepted/rejected), and `Final_Label` retains Accept/Reject. `E1_Dispute_with_MV` retains Y/N; `MV_Votes_of_3` counts acceptance votes from E2/E3/E4 only. The other per-item acceptance tables use 1/0.
- `Reject_Category`: fixed labels Tool_Contamination, Semantic_Drift and Gen_Failure for rejected FL items; blank for accepted items. No arbitration free text is included.
- `Model`: the recorded API model alias, not a guaranteed immutable backend snapshot.
- Sensitivity `is_novel`: 1/0 for the recorded generation/sentinel proxy; never interpret it as a human quality label.
- Generation `Generated` / `Sentinel`: text-derived binary flags defined in EVALUATION_METHODS.md. They preserve numerical flow checks without releasing or independently verifying the text.

## Aggregate fields

`Outputs`, `Rated_Outputs`, `Records`, `Raw_Records`, `Generated_Records`, `Unique_Items`, `Generated_Items`, `Generated_Unique_Items`, `Observed_Unique_Items`, `Rated_Unique_Items`, `Assigned_Items`, `Duplicate_Records`, `Items_Without_Evaluation`, `Sentinel_Only_Items`, `Reject`, `Missing_Final` and `Disputes` are nonnegative counts, as distinguished by each file's unit. `Rate` and `Generation_Rate` are proportions; `Wilson_Low` and `Wilson_High` are 95% interval bounds.

Agreement summaries retain `scope`/`outer_scope`, `condition`, `dimension`, `rater_pair`, effective `n`/`n_jointly_rated`, `raw_agreement`, `gwet_ac1`, `n_pairs_with_data` and `mean_ac1_unweighted`. The three agreement CSVs retain the original values and labels byte for byte after field/value checks. A legacy `Completeness` dimension label refers to thresholded C in those outputs; it is not evidence that a separate completeness construct was rated.

## Exact headers

### `data/main_ratings.csv`

`Sample_ID`, `Requirement_Group_ID`, `Channel`, `Category`, `E1_Correctness_1to5`, `E1_Novelty_YN`, `E1_Usefulness_YN`, `E1_Scope_ECU_Net_HW_OOS`, `E2_Correctness_1to5`, `E2_Novelty_YN`, `E2_Usefulness_YN`, `E2_Scope_ECU_Net_HW_OOS`, `E3_Correctness_1to5`, `E3_Novelty_YN`, `E3_Usefulness_YN`, `E3_Scope_ECU_Net_HW_OOS`, `E4_Correctness_1to5`, `E4_Novelty_YN`, `E4_Usefulness_YN`, `E4_Scope_ECU_Net_HW_OOS`, `E1_Accept`, `E2_Accept`, `E3_Accept`, `E4_Accept`, `Dispute`, `Final_Accept`.

### `results/main_acceptance.csv`

`Channel`, `Outputs`, `Rated_Outputs`, `Accept`, `Reject`, `Missing_Final`, `Disputes`, `Rate`, `Wilson_Low`, `Wilson_High`.

### `results/main_category_acceptance.csv`

`Category`, `Condition`, `Accept`, `Rated_Outputs`, `Rate`.

### `data/ablation_fl_ratings.csv`

`Sample_ID`, `E1_C`, `E1_N`, `E1_U`, `E1_Accept`, `E2_C`, `E2_N`, `E2_U`, `E2_Accept`, `E3_C`, `E3_N`, `E3_U`, `E3_Accept`, `E4_C`, `E4_N`, `E4_U`, `E4_Accept`, `MV_Votes_of_3`, `Final_Label`, `E1_Dispute_with_MV`, `Reject_Category`.

### `data/ablation_condition_ratings.csv`

`Item_ID`, `Condition`, `Evaluator`, `C`, `N`, `U`, `Accept`.

### `data/ablation_majority_items.csv`

`Item_ID`, `Condition`, `E1_Accept`, `E2_Accept`, `E3_Accept`, `E4_Accept`, `MV_Votes_of_3`, `Final_Accept`.

### `results/ablation_acceptance.csv`

`Condition`, `Accept`, `Outputs`, `Rate`.

### `results/ablation_fl_reject_attribution.csv`

`Reject_Category`, `Outputs`.

### `data/sensitivity_records.csv`

`Model`, `Channel`, `Requirement_Group_ID`, `Record_ID`, `Record_Order`, `is_novel`, `Last_Record`, `Has_Error`.

### `results/sensitivity_generation.csv`

`Model`, `Channel`, `Records`, `Unique_Items`, `Duplicate_Records`, `Generated_Items`, `Generation_Rate`.

### `data/generation_records.csv`

`Record_ID`, `Requirement_Group_ID`, `Channel`, `Generated`, `Sentinel`.

### `results/generation_flow.csv`

`Channel`, `Assigned_Items`, `Raw_Records`, `Observed_Unique_Items`, `Duplicate_Records`, `Generated_Records`, `Generated_Unique_Items`, `Generation_Rate`, `Rated_Outputs`, `Rated_Unique_Items`, `Items_Without_Evaluation`, `Sentinel_Only_Items`.

### `results/iaa_condition_rater_pair_counts.csv`

`outer_scope`, `condition`, `rater_pair`, `n_jointly_rated`.

### `results/iaa_per_dimension_by_rater_pair.csv`

`scope`, `dimension`, `rater_pair`, `n`, `raw_agreement`, `gwet_ac1`.

### `results/iaa_summary.csv`

`scope`, `dimension`, `n_pairs_with_data`, `mean_ac1_unweighted`.

## Coverage and limitations

The projections retain every row of the canonical 489-output main sheet, the documented ablation inputs, the 14 parsed sensitivity logs, and the three main-generation record files. They do not export all historical rating-table duplicates or older author-only ablation summaries as additional observations. Those originals remain privately archived.

No requirement text, existing/generated VC text, original identifiers, source links, free-form notes, prompts or scripts are included. The data do not independently validate semantic judgments or confer rights to withheld materials. Domain-2 and retrieval-precision claims are not covered by this numerical release. See AVAILABILITY.md and EVALUATION_METHODS.md for the exact access and interpretation limits.
