# V1.11s: A visible pool without a path to it

Can the model abstain when the correct pool string is in the supplied records
but the target team cannot be connected to its line? Use one fresh target
(construction seed 26110324), the six complete decoy chains and the line-only
far/near manipulation from [V1.10s](luna-native-contract-v110s-protocol.md).
Replace the separate pending target with a middle-link deletion on the *same*
target used for both controls. No new prompt instructions or scoring rules.

| View (per distance) | Single change from full input | Required output and evidence |
|---|---|---|
| source | none | known pool; assignment, team-line and line-pool |
| missing | remove target endpoint | unknown/null; assignment and team-line |
| missing-link | remove target team-line | unknown/null; assignment only |

Deletion does not renumber or reorder records. In the last view all seven
confirmed endpoints remain visible. Even the target's original endpoint is
not licensed as a value or citation: a complete mapping by elimination is not
an explicit record. No record states that every team maps to a different line.
The two deletion conditions have identical record counts (20).

## Frozen run

- Six dependent views, each in native and JSON mode: 12 requests total.
  Far block then near block; format order alternates. GPT-6 Luna, reasoning
  high, max 4,096 output tokens per call, 49,152 total allocated; at most
  200,000 serialized input bytes. Zero retries, repairs, retrieval or pilots.
- Same stop rules and 6/6 strict gate per format. In the missing-link cells,
  report overcommitment to the visible pool separately from citing the
  disconnected endpoint with a null value. Preserve both errors and ties.
- One target, one sample per cell. This tests explicit evidence use under the
  supplied contract, not retrieval, general error rates or internal reasoning.

## Reproduction

```sh
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v111s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v111s-20261118 \
  --max-calls 12 --max-output-tokens 49152 --max-input-bytes 200000
```

Use the printed digest with the same directory for the one authorized `run`.
`report` audits saved records offline; a stopped prefix must not be resumed.
