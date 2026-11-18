# V1.13s: When both registers use the same identifiers

The [previous native enum pair](luna-native-contract-v112s-results.md) used
unique chain keys. This new standalone packet requires scope, matching both
halves of a handoff, and distinguishing **no agreement** from **two agreements**.
All support rules are in the public question. Neither the case label nor the
expected proof is sent to the model. This is not a rerun of the earlier target.

## Frozen packet

Construction seed 26110326. Both registers use the *same* request and team IDs.
Each has two offers. A receipt confirms an offer only if source register,
team, destination register, line and code agree. Four additional receipts
have valid-looking codes and the wrong source. Line labels repeat across
registers; look up a pool by destination register **and** line.

| Matching pairs for target | Value | Required evidence, exact set |
|---|---|---|
| One | Known pool | Assignment, matched offer, matched receipt, scoped endpoint (4) |
| None | Unknown/null | Assignment and both target offers (3); no unmatched receipts |
| Two | Unknown/null | Assignment and both complete pairs (5); no endpoint or recency tie-break |

Three snapshots, always 18 records (2 assignments, 4 offers, 8 receipts,
4 endpoints) in the same order with the same IDs. The balanced snapshot
licenses one different pool per register. In each of the other snapshots only
two receipt digits change: one register now lacks agreement and the other has
two agreements. The two snapshots reverse these roles. Query both scopes on
each identical packet; alternate arm order and reverse query order in the
left-gap snapshot. Each request is stateless.

## Decisions before generation

- GPT-6 Luna, high reasoning, exactly the six planned pairs at most (12 calls),
  4,096 output tokens each, total allocation 49,152; serialized input cap
  200,000 bytes. No retries, repairs, retrieval, or alternative models.
  Retain any stopped prefix. No extra draws after observing results.
- Both arms use strict native output. Their request bodies differ only by
  the visible 18-ID enum on evidence items. Same instructions, schema name,
  question, records, token limit, local validation and semantic score.
- Report known values (2), abstention **with exact evidence** for zero (2)
  and two (2) agreements, prose in the citation field, wrong but supplied
  IDs, and strict success (6) per arm. The gate is all six strict per arm;
  do not give full credit just for predicting null.
- One synthetic packet and six dependent views. A tie, failure or complete
  pass is descriptive; none establishes robustness or a causal difficulty
  increase relative to V1.12s. No pilot or expansion is authorized.

## Reproduction

```sh
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v113s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v113s-20261118 \
  --max-calls 12 --max-output-tokens 49152 --max-input-bytes 200000
```

Use the printed digest and directory for one `run`; `report` audits the
saved responses without contacting the provider.
