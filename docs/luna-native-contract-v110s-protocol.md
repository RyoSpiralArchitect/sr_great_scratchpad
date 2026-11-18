# V1.10s: Isolate the final line-to-pool lookup

The [V1.9s protocol](luna-native-contract-v19s-protocol.md) changed the request,
team and line IDs together. This standalone comparison uses two fresh targets
(seed 26110323). Across far/near versions of a target, the six other requests
and their teams are identical, always five hex digits away from the target's.
Only their line IDs vary: five digits different in far, final digit only in
near. Each renamed line occurs in both its team link and its pool record so
every chain stays internally consistent. Source text outside those tokens,
record IDs, order, pools, question, and grading key stay fixed within a pair.

Use the same three states as V1.9s: complete (known, cite three records),
endpoint removed (unknown, cite the remaining two), explicitly pending
(unknown, cite all three). Each state gets both distances and both formats;
format order alternates by view and distance order reverses by target. No
citation enum. Both formats see the same public input for the same view.

## Budget and decision

- GPT-6 Luna, high reasoning. At most 12 calls, 4,096 output tokens each,
  49,152 allocated total and 200,000 input bytes in the serialized requests.
  No retries, repairs, retrieval or replacement calls. Keep a stopped prefix.
- Score each format against the unchanged caller and semantic contracts:
  all 6 views must pass. Inspect the returned pool and evidence IDs separately
  for borrowing from a decoy, including wrong citations with a correct value.
- Contrast near vs far within each state and format. If both pass, record no
  observed difference; if they differ, retain the first raw failure. Two
  targets, one draw per cell: neither outcome estimates a population error
  rate, establishes an internal mechanism, or authorizes a retrieval pilot.

## Reproduction

```sh
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v110s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v110s-20261118 \
  --max-calls 12 --max-output-tokens 49152 --max-input-bytes 200000
```

Use the printed digest and same directory for the single authorized `run`.
`report` takes the same digest and checks saved responses without new requests.
