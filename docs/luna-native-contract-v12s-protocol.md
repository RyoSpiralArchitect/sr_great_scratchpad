# GPT-6 Luna Native Contract V1.2s: Standalone Citation-Enum Campaign

## Why A Standalone Version

V1.2 freezes the citation-ID enum factor on the V1.1 baseline and requires the
byte-witnessed parent, stopped-V1 and completed-V1.1 directories, which live on
an unreachable machine. The cooperator authorized this disclosed standalone
variant after the V1.4s run reproduced the prose-decorated citation failure in
the native arm (`"m001: …"` strings in `evidence`), which is exactly the failure
family the enum is meant to constrain at the provider's type layer.

Same task content, arms, budgets and gates as V1.2; rooted as fresh lineage with
`parent: null`, no retained witnesses, seed 26110318. Disjointness is by
construction only, recorded as `"standalone": true`. Results are never merged
into or claimed as the witnessed V1.2 execution or compared lineage-wise to
V1/V1.1/V1.3s/V1.4s.

## Frozen Difference

Native `evidence.items` is `{"type": "string", "enum": <sorted supplied IDs>}`
and `maxItems: 0` when no records are supplied; the identical enum-bearing
schema stays embedded in both arms' questions; the json-mode control is
unenforced. Everything else matches V1.1. No semantic-contract or lexicon lines
are added — the enum factor stays isolated.

## Budget And Gate

Identical to V1.3s:30 requests,15 per arm,122,880 output tokens,300,000
input-byte ceiling,4096 per-call cap,0 retries/pilots, same stop rules,
measurements and15/15 gate. The standalone status bars lineage-relative claims.

## Reproduction

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v12s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v12s-20261115 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v12s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v12s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```
