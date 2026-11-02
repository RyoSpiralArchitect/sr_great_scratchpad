# GPT-6 Luna Native Contract V1.1: Fresh Input-Compatibility Revision

## Why A New Version

V1 stopped after2/30 attempts at source `bf05f2b291ba864650e7261dd49f48c6105feae8`.
The native request completed, preserving unknown/null and both flag states, but
returned prose in `evidence` rather than exact supplied IDs. The helper rejected
it and retained218 output plus578 input tokens. This is a real caller-contract
failure, not a format repair or a pass.

The paired JSON-mode request was rejected with HTTP400: the provider required the
word `json` in the **input**. The shared system instructions already said JSON,
but that did not satisfy this input check. No control model response or usage was
received. Its usage is unavailable, not zero. A zero intention-to-treat contrast
from that stopped prefix must not be read as model equivalence.

A preceding shell-setup failure occurred before the model process started and
before any attempt/execution directory existed. It is separately retained in
`launcher-note.json`; it is not a model retry.

V1's two attempts, raw responses, result, summary, audit and initial launch note
are byte-witnessed unchanged. Its28 remaining slots stay unattempted. The source
and plan remain available; no old case is reissued or rescored. Current code will
not prepare another V1 campaign. Exact V1 audit uses its recorded source revision,
not a runtime-hash bypass.

The cooperator explicitly authorized a new30-call campaign after seeing this stop,
for **32 total API attempts** across V1 and V1.1. This is a disclosed deterministic
input-compatibility revision, not a preregistered first attempt or a successful
historical gate.

## Frozen Difference

Retain all V1 model/profile settings, native schemas, source templates,15 view
types, ordering, budgets, scorer, local validators and15/15 semantic gate.
Use case-construction seed **26110312**, disjoint from both V1 and the old Luna v3
cases. Record IDs remain case-local; target/entity IDs and case seeds are fresh.

Change `Output schema (structure only)` to `Output JSON schema (structure only)`
in **both arms' input question**. The input now contains the explicit JSON marker
required by the observed provider check. No additional proof hints, source-ID
enums, output repairs, model switches or semantic tuning are introduced.

Every new pair still has byte-identical prompt/system/source records, model/high
reasoning and4096 output cap. Only Responses `text.format` differs: the same
schema as text with JSON-object mode versus PR #11's strict native schema. Pair
order alternates native-first8 / control-first7. The native arm exercises the
real `call_structured_task` helper; neither arm sees answer ledgers or prior turns.

Keep the previously observed prose-citation failure as a measured failure. Do not
silently substitute IDs or treat descriptions containing `m009` as that exact ID.
Any future citation-ID constraints require a separate prospective revision and
fresh evaluation; they are not part of this comparison.

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
- Equal visible prompts and output allocation do not imply equal provider input
  tokens or latency; native schema overhead remains part of measured usage.

Retain negative effects, ties, first failures and incomplete/unknown usage. The
change is not a result-selected case subset: all ten scenario templates and all
fifteen view types are kept. Old results remain descriptive context, not an
identical-input comparison to these fresh cases.

## Reproduction

Commit the revised runner, spec and this protocol before preparing. Freeze the
complete plan and runtime hashes before sending. Audit the recorded prefix if
stopped; never loosen a guard to resume a frozen run.

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v11.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v11-20261103 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v11-20261103 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v11-20261103 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```

Historical V1 command reproduction requires source `bf05f2b`, because this
prospective runner revision intentionally changes runtime hashes. No historical
raw file, score, failed gate or source dependency is rewritten for compatibility.
