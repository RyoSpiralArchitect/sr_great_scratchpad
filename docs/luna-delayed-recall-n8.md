# Luna delayed-recall Stage 2: independent n=8 confirmation

## Result boundary

This independent cohort tests whether provider-visible scratchpad recall helps
`gpt-5.6-luna` recover a corrected biological comparison level after the
ordinary 700-character dialogue window has dropped the correction. It does not
establish general conversational-memory quality across topics or models.

The frozen primary contrast is paired within replicate:

`scratchpad-scratchpad - write-no-recall`

The Stage 1 n=4 pilot selected this confirmation run. It is not pooled into the
n=8 primary estimate.

## Frozen provenance

- source commit: `4aaf4e4b90bd2de3086053b1308d79450e3a034c`
- run id: `dialogue-2026-08-26T171844-0700-5844ce2e`
- model/profile: `gpt-5.6-luna` / `openai-5.6-luna`
- scenario identity: `df65f5481971f5a2d7f22001d4ac6dde7abb523b536c749eb440fad18b44f5ee`
- dialogue runner SHA-256: `d017d16bb30bfeb0b59de9c90b29d0b5d8d9206a0b0f383e1c2cb8dc70ca1d21`
- taxonomy SHA-256: `bd995316c76764f436024fe57cc66a1bdd3dc3831cbc10a952de36442b22b964`
- analyzer SHA-256: `2b664b66a2580b28b13c570cf579eb07ec4213555d1bf334a7e92890afe5fd11`
- suite manifest SHA-256: `297cbef66d2addebb1a7419130886b989a295feb1230a1684a286b9673971cc3`
- dialogue report SHA-256: `60eab070beda3ab0097c5088fa0da3f6645a3afd92952d9f5e4d1ce87e6cbf34`
- semantic JSON SHA-256: `a80a21b2e8f73a0482f0da109e44fc54c93f3efd4aedc8e5480c78e4f83bf12a`
- semantic Markdown SHA-256: `40a7a6768812956de3aa864024f7442f99e8b6bc018fc0a31cdafff17843dea7`
- corpus: 384 utterances and 58 notes

The semantic analyzer was replayed twice with byte-identical JSON and Markdown
outputs.

## Validity gate

| Check | Result |
|---|---|
| 32 sessions and 384 utterances completed | pass |
| two deterministic four-way condition rotations | pass |
| starting speaker balanced A/B/A/B/A/B/A/B | pass |
| unrecovered JSON failures or stopped turns | 0 |
| original correction absent from all turn-11 provider prompts | pass |
| pre-probe correction note in both writing conditions | 8/8 pairs |
| write-no-recall correction note hidden at turn 11 | 8/8 |
| full correction note visible at turn 11 | 8/8 |

The run therefore passes the preregistered gate before behavioral
interpretation.

## Primary paired result

| Replicate | Starter | Write position | Full position | Write score | Full score | Delta | Literal write | Literal full |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | A | 3 | 4 | 0.011390 | 0.201353 | +0.189963 | 0/2 | 2/2 |
| 2 | B | 2 | 3 | 0.005186 | 0.215503 | +0.210317 | 0/2 | 1/2 |
| 3 | A | 1 | 2 | 0.108069 | 0.184836 | +0.076767 | 1/2 | 1/2 |
| 4 | B | 4 | 1 | 0.019111 | 0.271994 | +0.252883 | 0/2 | 2/2 |
| 5 | A | 3 | 4 | 0.028297 | 0.220322 | +0.192025 | 0/2 | 2/2 |
| 6 | B | 2 | 3 | 0.019238 | 0.269364 | +0.250126 | 0/2 | 2/2 |
| 7 | A | 1 | 2 | 0.019212 | 0.254992 | +0.235780 | 0/2 | 2/2 |
| 8 | B | 4 | 1 | 0.014915 | 0.188899 | +0.173984 | 0/2 | 1/2 |

- mean paired delta: `+0.197731`
- median paired delta: `+0.201171`
- sample standard deviation: `0.056924`
- positive direction: `8/8`
- fixed-seed paired-bootstrap 95% interval: `[0.156559, 0.230211]`

The interval uses 10,000 deterministic SHA-256-indexed resamples with seed
`20260826`. All treatment-control deltas are positive across both starting
speakers and all four execution positions. Position and starter summaries are
descriptive at this sample size, not separate effect estimates.

## Literal paired outcomes

Complete two-probe recovery by session:

| Both pass | Full only | Write only | Neither | Discordant |
|---:|---:|---:|---:|---:|
| 0 | 5 | 0 | 3 | 5 |

Across the sixteen paired literal items:

| Both pass | Full only | Write only | Neither | Discordant |
|---:|---:|---:|---:|---:|
| 1 | 12 | 0 | 3 | 12 |

Full recall recovered 13/16 literal items versus 1/16 without recall. It
recovered the new individual-level term in all eight sessions, but explicitly
named the old species-level term in only five. The treatment therefore improved
the frozen endpoint without achieving perfect instruction compliance.

## What the notes contained

Both writing conditions produced 29 notes and valid correction notes before the
probe. Their source correction-frame scores were closely matched: `0.248878`
for write-no-recall and `0.254209` for full recall.

Primary note labels differed later in the dialogue:

| Condition | Biological correction | Origin/establishment | Center/branch | Analogy boundary | Total |
|---|---:|---:|---:|---:|---:|
| write-no-recall | 13 | 15 | 1 | 0 | 29 |
| scratchpad-scratchpad | 12 | 8 | 8 | 1 | 29 |

The full condition retained more explicit center-versus-branch checkpoints,
while the write-only condition concentrated later notes on origin versus local
establishment. This is a trajectory difference inside this scenario, not yet a
general note-quality claim.

At turn 11, mean source-note-to-response similarity was `0.165007` with recall
and `0.026303` without recall. The structural visibility check remained exactly
`1.0` versus `0.0`; lexical overlap in an ordinary prompt is not counted as a
note injection.

## Broader semantic readout

Origin versus establishment remained the most occupied utterance frame in all
conditions. Epistemic calibration stayed sparse, so this cohort says little
about preservation of uncertainty or evidence boundaries.

Full and write-only same-speaker lag similarity were close (`0.040208` versus
`0.042499`), as were adjacent-turn similarities (`0.095628` versus `0.094415`).
The direction of repetition and semantic concentration has changed across the
n=1 calibration, n=4 pilot, and n=8 confirmation. No stable repetition effect
should be claimed.

Raw and centerline-only each recovered 2/16 literal items and completed neither
two-item probe. Centerline guidance by itself did not recover the evicted
comparison-level correction in this cohort.

## Cost and mechanics

| Condition | Calls | Prompt tokens | Completion tokens | Writes | Injections | Recoveries |
|---|---:|---:|---:|---:|---:|---:|
| raw-raw | 96 | 77,521 | 10,480 | 0 | 0 | 0 |
| centerline-only | 96 | 89,174 | 10,692 | 0 | 0 | 0 |
| write-no-recall | 101 | 139,284 | 16,662 | 29 | 0 | 24 |
| scratchpad-scratchpad | 102 | 166,296 | 15,746 | 29 | 52 | 23 |

- model calls: 395 (preflight worst case 768; projection 440)
- prompt tokens: 472,275 (projection 561,928)
- completion tokens: 53,580 (projection 57,848)
- total provider tokens: 525,855
- deterministic multi-object protocol recoveries: 47
- JSON parse errors: 0
- wall time: 19 minutes 27 seconds

Relative to write-no-recall, full recall added 27,012 prompt tokens (`19.4%`)
and 26,096 total tokens (`16.7%`) across eight sessions. This is the measured
provider-token cost of making the saved context visible in this cohort.

## Independent confirmation

The independent n=4 pilot had a positive paired delta in 4/4 replicates with a
mean of `+0.183728`. This n=8 cohort has a positive paired delta in 8/8
replicates with a mean of `+0.197731`. The matching direction is confirmatory,
but the absolute scores are not pooled or compared as model drift because each
cohort fits its own TF-IDF representation.

The bounded conclusion is that, for this Luna profile, scenario, 700-character
history window, and frozen taxonomy, making a successfully written correction
note provider-visible improved delayed recovery relative to writing the same
kind of note without recall.

## Next stage

Do not spend immediately on n=16 for this exact cell. The next uncertainty is
generalization, not the sign of the within-cell effect. Freeze new topic
families that test evidence/uncertainty boundaries and competing center/branch
corrections, then cross at least one API profile and one local Hugging Face
profile. Each model-topic cell should use its own n=4 gate and fresh n=8
confirmation, with within-cell paired estimates and no cross-taxonomy absolute
score comparison.
