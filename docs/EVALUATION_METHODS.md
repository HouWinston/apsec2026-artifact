# Evaluation and calculation definitions

## Unit and rubric

The main evaluation unit is one generated output containing two VC candidates. Historical candidate-level judgments and a rule for combining candidate-level judgments were not recorded. The release preserves output-level observations rather than constructing candidate-level data.

For each rater, C is Correctness on a 1–5 scale, N is Novelty (Y/N), and U is Usefulness (Y/N). Per-rater acceptance is `C >= 3 AND N = Y AND U = Y`. An absent score remains absent and is not imputed as a rejection. A scope label is descriptive and does not replace a quality rating.

## Main evaluation resolution

Each main output has two present external ratings from E2/E3/E4. A dispute occurs if their acceptance decisions differ or their C scores differ by at least two. For disputed rows, the recorded E1 adjudication determines final acceptance; the historical calculation treats a disputed row without E1 as rejected. Non-disputed rows use the minimum C score and the conjunction of the two N and U labels. Fewer than two external ratings produces an undefined final decision.

E1 adjudicated 285 of the 489 outputs. E1 was not blind to the generation channel. The retained results include adjudication sensitivity; the public numerical export does not establish an independent blinded evaluation.

## RQ3 ablation

For the 50-item FL (filter plus LLM matching) condition, final acceptance is the majority of E2/E3/E4. E1 does not override that majority. The Abl-LM and Abl-NF rating records retain their separately recorded item links. A common item position across source files is not assumed to prove common requirement identity across all three conditions.

The X-to-LM and Y-to-NF labels follow source row-index alignment and exact agreement of 400 derived acceptance decisions with the retained canonical JSON. This checks the numerical interpretation used by that JSON; it does not independently verify a blind condition key, requirement identity, or original assignment provenance.

Older author-only ablation summaries are not substituted for the external-rater majority results. Those historical records remain in the private archive.

## RQ4 sensitivity

Generation rate is the number of distinct requirement groups whose last logged record has `is_novel = true`, divided by the number of distinct logged groups for that model/channel. This matches the historical last-record-wins calculation. All numerical log rows are retained separately, including earlier records where present. Assigned benchmark totals are 208 for Channel A and 142 for Channel B; logged coverage and generation counts must not be conflated.

The logged indicator describes generation versus the no-novel-VC sentinel. It does not establish the novelty, correctness, usefulness or acceptance of a generated VC. API model aliases in the historical runs do not necessarily identify immutable backend snapshots.

## Generation flow

The historical generation-flow calculation marks a record as generated when its withheld text contains `VC_Item` and does not contain `NO_NOVEL_VC_FOUND`. A separate flag records presence of that sentinel. Unique generated groups, raw generated records, rated outputs, and assigned benchmark items are separate counts. The numerical flags allow count checks but cannot independently verify how the withheld text was classified.

## Statistical definitions and limits

- Acceptance rate: accepted defined output decisions divided by all defined output decisions in the stated condition.
- Wilson interval: 95% score interval with z = 1.96, using the recorded numerator and denominator.
- Odds ratio: `(a*d)/(b*c)` for the stated two-by-two acceptance table.
- Cohen's h: `2*asin(sqrt(p1)) - 2*asin(sqrt(p2))`.
- Fisher calculation in the retained historical reproducer: one-sided upper-tail hypergeometric probability. The historical implementation rounds p values to four decimals before its Holm adjustment; saved results retain that implementation behavior and do not claim higher precision.
- Holm adjustment: ordered p values multiplied by the number of remaining tests, made monotone and bounded at one, for the stated comparison family.
- Gwet AC1: `(observed agreement - chance agreement)/(1 - chance agreement)` on genuinely jointly rated records for each rater pair. Missing scores and absent pair assignments are excluded, not filled. Pair counts and the analysis scope are reported.

The main Fisher/Holm output is a historical numerical analysis, not proof of independent observations. Pseudonymized group IDs do not establish independence or remove overlap between experimental conditions.

Some retained legacy agreement outputs call thresholded C `Completeness`; the primary C/N/U rubric defines C as Correctness. Preserving that legacy file label does not create a separately collected completeness rating. Pair assignment differs across conditions, so pooled agreement cannot by itself identify a condition effect.

The release does not include retrieval-precision item labels whose annotation provenance was unavailable. Numerical coverage is limited to the main evaluation, the documented RQ3 ablation, RQ4 generation logs and retained agreement summaries; it does not claim complete public replication of Domain-2, retrieval semantics, or every statement in the article.
