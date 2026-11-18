# V1.14s: Was the handoff active then, as known by the filing cutoff?

Extend the [two-register challenge](luna-native-contract-v113s-results.md)
with two independent, inclusive clocks. One fresh synthetic packet (seed
26110327), same target, same 23 records in the same order for every call.
Only the dates in the question change between views. Some visible records
are inadmissible at a given cutoff; their IDs nevertheless remain in the enum.

Receipts must match all five fields as before. A receipt or state notice
must meet **both** cutoffs: effective day <= target day, filing day <= filing
cutoff. A state notice must also match all five fields and originate at the
destination register. For each matched pair use the eligible notice with
the greatest effective day (filing day breaks ties); otherwise it is active.
Offers, assignments and endpoint mappings are standing records.

The first pair is initially active. Its suspension is effective on day 20
but filed on day 50. Its reinstatement is effective on day 40 and filed on
day 58. A subsequently filed suspension (day 60) has an earlier effective
day (16): it cannot override either later-effective notice. The second
pair starts on day 35, filed on day 38. A wrong-issuer suspension and a
correct but late-filed day-61 suspension remain visible as distractors.

| Target day / filing cutoff | 42 | 50 | 60 |
|---|---|---|---|
| 20 | First only | Neither | Neither |
| 40 | Both | Second only | Both |

Always cite the scoped assignment, both offers, all matched eligible receipts
(even for suspended pairs) and **only** their governing notices. Cite the
scoped endpoint only when exactly one pair is active. Known, no active pair,
and conflict have two views each. A null value with a superseded, future or
unauthorized citation is not a strict success. No repair or ID normalization.

## Frozen limits

- GPT-6 Luna, high reasoning, 6 paired queries, maximum 12 calls,
  4,096 output tokens each, 49,152 total allocated; 200,000 serialized input
  bytes maximum. No retries, pilots, replacements, retrieval or memory writes.
- Native/strict in both arms, same prompt and schema name; only treatment
  enumerates all 23 public IDs for evidence items. Alternate first arm in
  the query order recorded in the spec. Retain failures and stopped prefixes.
- Report value/status, exact proof, out-of-scope citations, and prose
  citations separately. Require all six strict passes per arm. One packet;
  no population error rate, superiority claim or comparison of effect sizes
  with an earlier task. Do not extend the run to seek a failure or a pass.

## Reproduction

```sh
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v114s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v114s-20261118 \
  --max-calls 12 --max-output-tokens 49152 --max-input-bytes 200000
```

Use the printed digest and directory for a single `run`. The corresponding
`report` audits the saved responses offline.
