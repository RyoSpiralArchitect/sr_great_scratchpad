# GPT-6 Luna Native Contract V1.4s: Standalone Flag-Lexicon Revision

## Why A New Version

The completed V1.3s standalone campaign reached14/15 strict contract success on
both arms, with a single **paired** failure: on `hold-dominates source` both
arms returned `urgent: "unobserved"` where the reference requires `unknown`,
while value, citations and proof were all correct. Analysis showed the shown
contract texts never define the flag vocabulary: the case generator writes
「未確認」 for `unknown` and simply omits the flag clause for `unobserved`, but
that mapping lives only in `STATE_SYSTEM`, which the contract helper does not
use. The failure is therefore a measured underspecification of the *meaning
contract*, kept as a failure in the V1.3s record and not rescored.

V1.4s is the disclosed follow-up: identical standalone lineage discipline to
V1.3s plus one explicit flag-lexicon line in the shared question. It isolates
exactly the observed ambiguity; citation enums remain absent so the factor
does not stack with V1.2.

## Frozen Difference

Retain every V1.3s setting — V1.1 model/profile,15 view types, ordering,
budgets, scorer, local validators, the15/15 gate, the `Output JSON schema`
label, the verbatim `Semantic contract:` block, `standalone: true`,
`parent: null` and no retained witnesses. Seed **26110316** is fresh;
disjointness remains by construction only, matching the standalone disclosure.

The single addition is a fixed line appended to the shared question for both
arms:

```text
Flag lexicon: 有効 = enabled; 無効 = disabled; 未確認 = unknown; a flag not stated in the supplied request = unobserved.
```

It states the vocabulary convention only. No answer ledger, expected flag
state, per-case hint or scoring change is introduced; `assess_answer` and the
strict gates are unchanged, so V1.4s versus V1.3s isolates the lexicon factor
as a descriptive (not identical-input) comparison.

## Budget And Gate

Identical limits to V1.3s:30 requests maximum,15 per arm,122,880 allocated
output tokens,300,000 serialized input-byte ceiling,4096 per-call output cap,
0 retries/repairs/pilot calls. Same stop rules, same separate measurements,
same15/15 future gate. No retrieval pilot or broad claim is authorized, and
the standalone status bars lineage-relative claims against V1/V1.1/V1.3.

## Reproduction

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v14s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v14s-20261115 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v14s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v14s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```
