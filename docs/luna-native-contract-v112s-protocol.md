# V1.12s: Does a native citation enum preserve abstention and proof?

[V1.11s](luna-native-contract-v111s-results.md) retained a native response
that abstained correctly but wrote explanations in its citation strings.
Do not retry it. Use one fresh target (construction seed 26110325) and the
same three views at both decoy line-ID distances. Both arms use the strict
native Responses format; there is no JSON-mode arm or follow-up question.

| View | Licensed answer | Exact required citation set |
|---|---|---|
| Complete chain | Known target pool | Assignment, link, endpoint |
| Endpoint removed | Unknown/null | Assignment, link |
| Middle link removed; endpoint still visible | Unknown/null | Assignment only |

## Single change

Treatment (`native-enum`) adds `properties.evidence.items.enum` to the
provider response schema. Its values are **all** public record IDs for that
view (21 or 20), including distractors, never only the gold support.
Control (`native`) accepts any string at that path. Remove that one enum and
the paired request bodies must be identical: same native schema name, strict
flag, model, instructions, question (including its generic shape example),
record order, and budget. The same local validator and scorer apply. Alternating
first arm gives three enum-first and three control-first pairs.

## Bounds and interpretation

- GPT-6 Luna, high reasoning, 6 matched views, 12 calls at most, 4,096 output
  tokens each (49,152 allocated), 200,000 serialized input bytes maximum.
  Keep existing stop rules, no retries, repairs, replacements or retrieval.
- Inspect raw evidence strings without stripping prose or extracting IDs.
  Report responses containing an ID plus explanatory prose separately from
  other malformed strings, incorrect but supplied IDs, and omitted support.
  Score known values (2 views), abstention (4), exact proof and overall strict
  success (6 each). Incomplete or missing responses are not clean evidence.
- The gate is 6/6 strict for each arm. A matched control prose error with
  clean enum output and unchanged correct value/proof is evidence for that
  pair, not a general rate. If neither arm emits prose, report non-recurrence:
  the schema excludes explanation strings but observed prevention is unproven.
  If the enum output loses a needed ID or cites a disconnected supplied ID,
  report the semantic failure even when every string satisfies the enum.
- These are dependent views of one new request, not independent replications;
  the historical failure is not an extra control observation.

## Reproduction

```sh
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v112s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v112s-20261118 \
  --max-calls 12 --max-output-tokens 49152 --max-input-bytes 200000
```

Use the printed digest and directory for a single `run`. The `report`
command uses the same digest and audits saved responses without spending.
