# GPT-6 Luna Native Contract V1.7s: Standalone Prose-Citation Replication

## Why A New Version

V1.5s's only failure was a native prose-decorated citation
(`"依頼 …（m001）。"`) on the `complete-join source` view — the third
recurrence of the V1/V1.4s shape. The identical contract in V1.6s produced
zero citation failures, so the difference between "recurs" and "does not
recur" is confounded between the fresh case draw (different seed) and the
added distracted views. V1.7s is a straight replication of the V1.5s input
semantics under a new seed, giving a second draw on the exact conditions
where the failure appeared.

## Frozen Difference

Identical to V1.5s: semantic contract + flag lexicon + flag scope, no
citation enum, no distracted views,15 views /30 calls. Seed 26110320 is
fresh; `standalone: true`, `parent: null`, no witnesses.

A recurrence of the prose-citation failure strengthens "seed-dependent,
intermittent"; its absence leaves both explanations (seed draw vs. view
mix) open — no causal claim either way, as before.

## Budget And Gate

- Thirty new requests maximum:15 per arm,122,880 allocated output tokens.
- Explicit300,000 serialized input-byte ceiling and4096 per-call output cap.
- Retries, repairs, schema smoke requests and retrieval/pilot calls:0.
- Same stop rules, same separate measurements, same15/15 future gate.
  No retrieval pilot or broad claim is authorized; standalone status bars
  lineage-relative claims.

## Reproduction

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v17s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v17s-20261115 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v17s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v17s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```
