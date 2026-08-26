# Luna delayed-recall increased-n plan

## Objective

Estimate whether provider-visible scratchpad recall improves delayed recovery of a previously corrected biological comparison level. The primary comparison is paired within replicate:

`scratchpad-scratchpad - write-no-recall`

This isolates recall availability after both conditions have had the ability to write notes. It is not an omnibus claim that the full runtime is always better.

## Frozen identities

- generation scenario: `scenarios/luna_delayed_recall_ablation.json`
- assessment taxonomy: `scenarios/luna_delayed_recall_semantic_taxonomy.json`
- dialogue window: newest 700 characters
- utterances per session: 12
- output allowance: 600 tokens per utterance, pooled across runtime calls
- model profile: `openai-5.6-luna`
- conditions: raw/raw, centerline-only, write-no-recall, scratchpad/scratchpad

Record the merge commit, scenario SHA-256, taxonomy SHA-256, profile metadata, request parameters, and every provider-visible prompt. Do not change the scenario or taxonomy within a cohort.

## Endpoints

Primary:

- paired turn-11 `biological-level-correction` frame-score delta between full recall and write-no-recall

Co-primary manipulation checks:

- write-no-recall note visibility is zero at turn 11
- full scratchpad note visibility is one at turn 11
- the original moderator correction is absent from every ordinary 700-character history window
- a correction note was successfully written before turn 11 in both writing conditions

Secondary:

- exact turn-11 literal probe recovery
- note-to-response semantic similarity
- center/branch and origin/establishment frame occupancy
- same-speaker lag similarity as a repetition measure
- calls, prompt/output tokens, protocol recoveries, parse errors, and memory injections

## Stage 1: n=4

Use four replicates so the starting speaker is exactly balanced A/B/A/B with `--alternate-starter`. Before calling the provider, add deterministic four-way condition-order rotation so time/order effects are not confounded with treatment.

Worst-case preflight:

- 16 sessions, 192 utterances
- 384 API calls
- 115,200 output tokens

Projection from calibration 3, not a cap:

- about 220 calls
- about 280,964 prompt tokens
- about 28,924 output tokens

Validity gate before interpreting behavior:

- all 16 sessions complete
- zero JSON parse failures
- every provider-visible prompt and trace is frozen
- note-visibility checks pass in all paired writing sessions
- at least three of four paired replicates contain a valid pre-probe correction note in both writing conditions

If the gate fails, preserve the run as plumbing evidence, make no efficacy comparison, and start a new run id only after fixing the cause.

## Stage 2 decision

For the four valid paired deltas:

- 3-4 positive: continue to n=8 for confirmation
- 2 positive: continue to n=8 because direction remains unresolved
- 0-1 positive, with valid manipulation checks: stop expansion and inspect semantic failure modes before spending more calls

Literal probes remain a separate exact check. Do not replace the continuous paired endpoint with a post-hoc holistic judge.

## Stage 2: independent n=8 confirmation

Start a fresh eight-replicate cohort in a new output directory without changing
the frozen identities. Do not append to or rewrite the n=4 run, and do not pool
the n=4 pilot into the confirmatory primary estimate. The n=4 cohort decides
whether another call spend is justified; the n=8 cohort supplies the result.

Because TF-IDF is fit jointly within each frozen cohort, compare paired
conditions inside a cohort. Do not interpret an absolute score change from the
n=4 corpus to the independently fitted n=8 corpus as a model change.

Worst-case total at n=8:

- 32 sessions, 384 utterances
- 768 API calls
- 230,400 output tokens

Calibration-based projection at n=8:

- about 440 calls
- about 561,928 prompt tokens
- about 57,848 output tokens

Campaign total if both stages run:

- worst case: 1,152 calls and 345,600 output tokens
- calibration projection: about 660 calls, 842,892 prompt tokens, and 86,772 output tokens

Before provider calls, implement and test deterministic four-way condition-order
rotation. Before reading the n=8 result, add the fixed-seed paired bootstrap and
exact discordant-pair report to the analyzer. Report all paired deltas, mean,
median, sample standard deviation, and positive-direction count. Keep
protocol/mechanical failures separate from semantic failures.

## Stop boundary

The n=8 result can support a bounded claim about this model, scenario, history window, and taxonomy. It cannot establish general conversational memory quality across topics or models. A broader claim requires at least one new topic family and one new model profile with independently frozen taxonomies.
