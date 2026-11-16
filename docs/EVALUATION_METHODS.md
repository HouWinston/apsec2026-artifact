# Evaluation and calculation definitions

## Unit and rubric

The main evaluation contains 489 rated outputs, each containing two VC candidates. Ratings are recorded at the output level; candidate-level judgments and a rule for combining them were not recorded.

For each rater, C is Correctness on a 1–5 scale, N is Novelty (Y/N), and U is Usefulness (Y/N). Per-rater acceptance is `C >= 3 AND N = Y AND U = Y`. Missing scores remain missing. Scope labels describe the output's domain and are separate from quality ratings.

## Main evaluation resolution

Each main output has two present external ratings from E2/E3/E4. A dispute occurs if their acceptance decisions differ or their C scores differ by at least two. For disputed rows, the recorded E1 adjudication determines final acceptance; the historical calculation treats a disputed row without E1 as rejected. Non-disputed rows use the minimum C score and the conjunction of the two N and U labels. Fewer than two external ratings produces an undefined final decision.

E1 adjudicated 285 of the 489 outputs. Adjudication was not blind to the generation channel. The retained results include adjudication sensitivity.

The legacy heading `majority vote + E1 adjudication` in `results/reproduced_main.txt` refers to the two-external-rater procedure above. Three-external-rater majority voting applies to RQ3.

## RQ3 ablation

For each of the 50-item FL (filter plus LLM matching), Abl-LM and Abl-NF conditions, final acceptance is the majority of E2/E3/E4. E1 does not override that majority. FL and LM/NF have separate identifier domains; a paired requirement mapping between them has not been verified.

The X-to-LM and Y-to-NF labels reconcile source row indices and all 400 derived acceptance decisions with the retained canonical JSON. The release uses this numerical reconciliation; a blind condition key, requirement identity and original assignment provenance were not independently verified. The released results use external-rater majority decisions rather than older author-only summaries.

## RQ4 sensitivity

Generation rate is the number of distinct requirement groups whose last logged record has `is_novel = true`, divided by the number of distinct logged groups for that model/channel. This follows the historical last-record-wins calculation. All numerical log rows, including earlier records, are retained. Assigned benchmark totals are 208 for Channel A and 142 for Channel B; the RQ4 rate uses logged groups as its denominator.

`is_novel` records generation versus the no-novel-VC sentinel. It is a generation indicator, separate from the human C/N/U and acceptance ratings. Historical API model aliases identify the recorded configurations, without fixing an immutable backend snapshot.

## Generation flow

The historical generation-flow calculation marks a record as generated when its source text contains `VC_Item` and does not contain `NO_NOVEL_VC_FOUND`. A separate flag records the sentinel's presence. The public data retain these flags and distinguish unique generated groups, raw generated records, rated outputs and assigned benchmark items. The source text is outside this release.

## Statistical definitions

- Acceptance rate: accepted defined output decisions divided by all defined output decisions in the stated condition.
- Wilson interval: 95% score interval with z = 1.96, using the recorded numerator and denominator.
- Odds ratio: `(a*d)/(b*c)` for the stated two-by-two acceptance table.
- Cohen's h: `2*asin(sqrt(p1)) - 2*asin(sqrt(p2))`.
- Fisher calculation in the retained historical reproducer: one-sided upper-tail hypergeometric probability, with p values rounded to four decimals before Holm adjustment.
- Holm adjustment: ordered p values multiplied by the number of remaining tests, made monotone and bounded at one, for the stated comparison family.
- Gwet AC1: `(observed agreement - chance agreement)/(1 - chance agreement)` on jointly rated records for each rater pair. Missing scores and absent pair assignments are excluded. Pair counts and analysis scope are reported.

Fisher/Holm results use the recorded output-level observations. Pseudonymized group IDs preserve grouping; they do not establish independent sampling or remove overlap between conditions.

Some legacy agreement outputs label thresholded C as `Completeness`; this refers to the same Correctness rating in the C/N/U rubric. Rater-pair assignment differs across conditions, so pooled agreement also reflects that composition.

The numerical release covers the main evaluation, documented RQ3 ablation, RQ4 generation logs, generation flow and retained agreement summaries. Domain-2 results and retrieval-precision item labels are outside its coverage.

## Public numerical checker

`scripts/reanalyze_numeric.py` is a read-only adapter for the public CSV schema, prepared on 2026-11-16. It recalculates rating decisions, acceptance and Wilson summaries, ablation counts, generation counts and agreement statistics, then compares nine `results/*.csv` files. It also checks the stored ablation per-item decisions.

The checker verifies numerical consistency within the release. It does not run model generation or reproduce Fisher/Holm tests, effect sizes or the saved `reproduced_*.txt` stdout. Assigned benchmark totals and text-derived flags are inputs to the checks.
