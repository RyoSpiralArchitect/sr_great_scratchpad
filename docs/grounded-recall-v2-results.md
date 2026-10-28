# Grounded record recall v2: calibration stopped at the gate

Date: 2026-10-26. See the [frozen protocol](grounded-recall-v2-protocol.md).
**Confirmation n=4 was not run.** Calibration completed all 16 planned calls;
14 passed the strict contract. The preregistered gate required 16/16.

## Results

Each source-visible cell below contains the board and room cases. `none` is
two draws of the same empty-record prompt per provider, not two different
questions: removing the records removes all case-specific information.

| Profile | none, strict abstention | original | prose | roles | Total |
|---|---:|---:|---:|---:|---:|
| openai-5.6-luna | 0/2 | 2/2 | 2/2 | 2/2 | 6/8 |
| mistral-large | 2/2 | 2/2 | 2/2 | 2/2 | 8/8 |

All **12 source-visible responses** satisfied all three value/citation checks
(36/36 role claims) and historical status/evidence (12/12). Both providers
distinguished an unestablished earlier adoption (board) from an explicitly
established one (room). No augmented condition improved on original records in
these two templated cases: every source-visible condition reached the ceiling.

Luna's two no-source outputs used the following form for each role:

```json
{"value": null, "evidence": []}
```

The frozen contract required the role field itself to be `null`. Both outputs
therefore failed schema validation. Inspection of the preserved raw JSON shows
that they **abstained rather than fabricated**: all three values are null and
`prior_adoption` is `not_established` with empty evidence. This is a diagnostic
reading of a serialization mismatch, not a rescoring or a passed gate. It would
be misleading to call these two outputs factual-history errors. Mistral used
the required top-level null fields in both no-source responses.

The original protocol's prose showed an object-shaped example and separately
asked for null when unavailable. Luna retained the object shape. That points
to an ambiguity in the answer contract/instructions as the next engineering
target, not evidence that Luna cannot abstain. An undeclared-but-valid semantic
paraphrase was not the cause of any failure in this cohort.

## Gate and receipts

- Implementation/protocol commit before any call:
  `20c815e191f63cfa5353cf61173a62cbce629efd`.
- Frozen canonical plan digest:
  `f12e13f85d07d8323e551a6f113c1d2690885a77385068084382deb1eb039ea8`.
- Calibration host timestamps: `2026-10-26T00:04:53+09:00` to
  `2026-10-26T00:06:04+09:00`.
- 16 attempted calls, 16 recorded responses, zero transport errors or retries.
  Model response identifiers were `gpt-5.6-luna` and `mistral-large-latest`.
  These returned aliases do not identify immutable provider model revisions.
- Raw replay of all 16 receipts reproduced the saved assessments and failed
  gate. An actual `grounded-run --stage confirmation` invocation then exited
  before provider access with `Calibration failed: confirmation is blocked`.
  No confirmation directory was created and all 32 conditional calls remain unused.
- No post-hoc alias expansion, response repair, model substitution, new prompt,
  or replacement cohort. Frozen prompt/code/config identity still validates.

Provider-reported token usage (not estimated):

| Profile | Calls | Input tokens | Output tokens | Total |
|---|---:|---:|---:|---:|
| openai-5.6-luna | 8 | 5,878 | 2,290 | 8,168 |
| mistral-large | 8 | 6,286 | 1,730 | 8,016 |
| Total | 16 | 12,164 | 4,020 | 16,184 |

Actual tokens, including any billed reasoning in provider output accounting,
are distinct from the plan's character/word input estimate. No dollar-cost
estimate is inferred from these counts.

Local artifact directory: `.great_scratchpad/runs/grounded-recall-v2-20261026/`.
These ignored artifacts are not available in a fresh clone.

| File | SHA-256 of file bytes |
|---|---|
| plan.json | `de122b44ac96e4e6d12cc53d46087cf67a6eda1b2b39317624d470fb390392dd` |
| calibration/result.json | `885968e9aa2fa793dac5e7f73a6dbbff6230673a767d94d1dd4e1fb8d9ad1304` |
| calibration/responses.jsonl | `37c7375b23e96527a74bdeb08cfcc15153602a6577776ecc005927634c0ee12f` |

The independent raw-receipt audit additionally returned canonical result digest
`a0cfa9aa057514f3998ba24a2647b2e7ce3068093a7d087149317e586762ab88`
and parsed-response-list digest
`4b7aaff71d022724568b748fd04563ee25c68b43185ef5bd61d220ca7f91fb0e`.
These canonical digests intentionally differ from the file-byte hashes.

The 1,396 pre-existing local run files retain aggregate digest
`211c411d279b5b55352b1b6630332e1a76a69b16589fe93e4e3cc0b44d1a792b`.
The stored model configuration is also byte-unchanged. Historical results have
not been rewritten or recast as results from this new protocol.

Local verification after calibration: 99 repository tests pass, including a
regression preserving object-null abstention as a v2 schema failure. Scoped
Ruff, compilation and whitespace checks pass; the existing fake-model CLI smoke
passed before the run. The new runtime did not change after its pre-call
commit. A credential-value scan of all three new run artifacts and seven changed
source/document files found zero matches. No claim of hosted test CI is made.

## Interpretation and next boundary

This cohort supports a narrow observation: under an explicit structured task
with short complete records, both models produced the declared source-grounded
relations and did not confuse current rejection with proof of earlier adoption.
It does not isolate the effect of better source wording, instructions, output
format, scoring or memory representation. The previous experiment used other
inputs and another endpoint; a before/after causal improvement is not established.
There is no demonstrated advantage of role labels over plain records here.

Before another paid cohort:

1. Define one unambiguous unavailable-value schema and include its full example.
   Keep the v2 failure and assessor immutable; version any new contract separately.
2. Test object-null/top-level-null behavior offline, with structural validity,
   epistemic abstention and factual grounding reported separately. This must
   not turn missing evidence into a successful recovery score.
3. Freeze fresh calibration inputs, prompts and a new bounded budget. Only a
   new passing gate may authorize the four as-yet-unqueried confirmation cases.
4. After that, design a less templated, full-dialogue test before claiming
   conversational memory improvement or enabling augmentation by default.

No new paid run or altered gate is implied by these next-step proposals.
