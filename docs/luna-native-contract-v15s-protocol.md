# GPT-6 Luna Native Contract V1.5s: Standalone Flag-Scope Revision

## Why A New Version

V1.4s removed the flag-lexicon failure but produced a new single observation:
the json-mode cell for `complete-join source` returned `urgent`/`hold` keys in
`flags` even though non-routing families contract `flags: {}`. The recorded
hypothesis is that the lexicon line primes flag emission on families where
flags must stay empty. V1.5s tests that hypothesis alone by adding one scope
line to the shared question, with every other V1.4s setting retained.

## Frozen Difference

Identical to V1.4s — semantic contract, flag lexicon, `standalone: true`,
`parent: null`, no witnesses — plus one appended line:

```text
For non-routing task families, use flags: {}.
```

Seed 26110317 is fresh; disjointness remains by construction. No answer
ledger, per-case hint or scoring change; `assess_answer` is unchanged, so
V1.5s versus V1.4s isolates the flag-scope factor as a descriptive comparison.

## Budget And Gate

Identical limits to V1.4s:30 requests,15 per arm,122,880 output tokens,
300,000 input-byte ceiling,4096 per-call cap,0 retries/pilots, same stop
rules, measurements and15/15 gate. Standalone status bars lineage-relative
claims.

## Reproduction

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v15s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v15s-20261115 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v15s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v15s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```
