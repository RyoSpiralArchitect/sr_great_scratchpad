# GPT-6 Luna Native Contract V1.2: Citation-ID Enum Revision

## Why A New Version

V1.1 completed all30/30 attempts at source `42324ef317ea98d70b98dd8e48c066cb4d8da2fb`.
Its results recorded that the narrow contract calibration succeeded under equal
visible prompts, while leaving the citation representation as a free string field.
The retained V1 stop remains byte-witnessed; V1.1 is a retained completed campaign
and current code will not prepare another V1.1 campaign.

The V1.1 results listed three unexecuted improvements. This revision implements
exactly the first one and nothing else: pass citation IDs to the native schema as
the enum of supplied public record IDs, and constrain the evidence array to empty
when no records are supplied. It uses no correctness or relevance ledger, so the
enum can only restrict, never reveal, which citations the semantic gate expects.

This is a disclosed prospective revision, not a preregistered first attempt and
not a repair of any prior outcome. V1's2 stopped attempts and V1.1's30 completed
attempts stay unchanged; their usages remain part of the running ledger.

## Frozen Difference

Retain all V1.1 model/profile settings, the15 view types, ordering, budgets,
scorer, local validators, the15/15 semantic gate and the `Output JSON schema`
input label that the provider's input check required. Use case-construction seed
**26110313**, disjoint from the parent, the stopped V1 and the completed V1.1
cases; all three historical plans are byte-witnessed before fresh identities are
accepted.

The only change is citation representation:

- In the **native** arm, `evidence.items` is `{"type": "string", "enum": <sorted
  supplied record IDs>}`. With zero supplied records the array is constrained by
  `maxItems: 0` so the only legal value is empty.
- The same schema — including the enum — is embedded verbatim in the shared
  question text, so the **json-mode** control sees the identical ID vocabulary.
  Only the native arm is type-enforced; type constraint and hint quantity are
  not confounded.
- Enum IDs come solely from the supplied public records of that view. Expected
  supports, relevance ledgers and prior turns are never consulted.

`call_structured_task` gains an opt-in `citation_enum` flag deriving IDs from the
validated task input. Without it the helper emits the unchanged V1.1 schema, so
earlier callers and receipts are unaffected. The local `validate_task_answer`
subset check is unchanged and remains the authoritative citation gate; provider
enforcement is an added layer, not a replacement.

## Budget And Gate

- Thirty new requests maximum:15 per arm,122,880 allocated output tokens total.
- Same explicit300,000 serialized input-byte ceiling and4096 per-call output cap.
- Retries, repairs, schema smoke requests and retrieval/pilot calls:0.
- Same stop rules: transport/API rejection or identity/security mismatch stops
  without fallback, silent resume, slot substitution or reissue.
- Same separate measurements: completion, strict local contract, value, flags,
  relevant supplied citations, full source-limited proof and strict success.
- Same future gate: all15/15 caller and semantic passes for an arm. No retrieval
  pilot or broad efficacy/adoption claim is authorized even if that gate passes.
- A native-arm enum violation now fails at the provider's schema layer; such an
  outcome is a measured contract failure, not a rescoring opportunity.

Retain negative effects, ties, first failures and incomplete/unknown usage. The
semantic meaning of unknown/unobserved and the split of citation versus rationale
fields are separate factors; neither is changed or claimed by this revision.

## Reproduction

Commit the revised runner, spec and this protocol before preparing. Freeze the
complete plan and runtime hashes before sending. Audit the recorded prefix if
stopped; never loosen a guard to resume a frozen run.

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v12.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v12-20261115 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v12-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v12-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```

Preparing requires the byte-identical parent, stopped-V1 and completed-V1.1 run
directories under `--runs-root`; missing or altered witnesses stop preparation
before any spend. No historical raw file, score, failed gate or source
dependency is rewritten for compatibility.
