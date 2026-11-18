# GPT-6 Luna Native Contract V1.6s: Standalone Distracted-View Campaign

## Why A New Version

Every campaign so far filters distractor records out of every view, so
`citations_relevant` has only ever been measured without noise. The V1.3s
analysis recorded this as an unmeasured dimension. V1.6s adds a `distracted`
view that supplies **all** records — relevant and distractor alike — for each
of the ten scenarios, on top of the best current input contract
(V1.5s: semantic contract + flag lexicon + flag scope), in the same standalone
lineage discipline.

## Frozen Difference

Identical input semantics to V1.5s. The change is the task matrix: each
scenario gains one `distracted` view supplying all18 records of the case.
Views per scenario grow from 15 to25 total, so `max_calls` becomes50 (25
views ×2 arms) and the allocated output ceiling becomes204,800 tokens. The
distractor texts are ordinary public record text — they name other targets
explicitly — and no expected answer changes: `reference_state` still derives
the typed ledger from all supplied ids, so citing a distractor id is a
measured citation failure exactly as before.

Seed 26110319 is fresh; `standalone: true`, `parent: null`, no witnesses.
This is not a prompt factor stacked for isolation claims; it widens the
measured surface under the best contract so far.

## Budget And Gate

- Fifty new requests maximum:25 per arm,204,800 allocated output tokens.
- Explicit400,000 serialized input-byte ceiling (distracted views are larger)
  and4096 per-call output cap.
- Retries, repairs, schema smoke requests and retrieval/pilot calls:0.
- Same stop rules, same separate measurements, same future gate, now25/25
  per arm. No retrieval pilot or broad claim is authorized; standalone status
  bars lineage-relative claims.

## Reproduction

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v16s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v16s-20261115 \
  --max-calls 50 --max-output-tokens 204800 --max-input-bytes 400000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v16s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v16s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```
