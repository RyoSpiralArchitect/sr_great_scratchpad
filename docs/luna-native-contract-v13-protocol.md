# GPT-6 Luna Native Contract V1.3: Explicit Semantic-Contract Revision

## Why A New Version

V1.1 completed all30/30 attempts at source `42324ef317ea98d70b98dd8e48c066cb4d8da2fb`.
Its results listed three unexecuted improvements; the second was to make the
meaning of `unknown`/`unobserved` and the rule/exception requirements for
determining a value an explicit semantic contract in the input, shown to both
arms. That factor is intentionally verified **without** the V1.2 citation-ID
enum, so the two revisions remain separate single-factor comparisons against
the same V1.1 baseline rather than a confounded stack.

This is a disclosed prospective revision, not a preregistered first attempt and
not a repair of any prior outcome. The stopped V1 and the completed V1.1 stay
byte-witnessed; the unexecuted V1.2 plan remains available for its own campaign
and is unaffected by this revision.

## Frozen Difference

Retain all V1.1 model/profile settings, the15 view types, ordering, budgets,
scorer, local validators, the15/15 semantic gate, the `Output JSON schema`
input label and the unchanged free-string citation representation. Use
case-construction seed **26110314**, disjoint from the parent, the stopped V1
and the completed V1.1 cases; all three historical plans are byte-witnessed
before fresh identities are accepted.

The only change is input semantics:

- A `Semantic contract:` block is appended to the shared question for **both
  arms**, verbatim from the reviewed `task_contract.PROOF_INSTRUCTIONS` text.
- It states flag-state preservation (`unknown`/`unobserved` are never rewritten
  as `disabled`), the records required to license a known value per task
  family, and the citation obligations under missing or pending evidence.
- No answer ledger, expected support list, correctness hint or per-case hint is
  added; the text is identical across all cases and arms and introduces no new
  semantic scoring. The existing `assess_answer` gate is unchanged, so V1.3
  versus V1.1 isolates the effect of stating the contract explicitly.

`call_structured_task` is unchanged: the semantic contract lives in the public
question text, not in the wire schema or helper behavior.

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

Retain negative effects, ties, first failures and incomplete/unknown usage. A
passed semantic gate under the explicit contract is evidence about stated
semantics, not about unstated-contract robustness; unknown conversations and
retrieval failures remain out of scope.

## Reproduction

Commit the revised runner, spec and this protocol before preparing. Freeze the
complete plan and runtime hashes before sending. Audit the recorded prefix if
stopped; never loosen a guard to resume a frozen run.

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v13.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v13-20261115 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v13-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v13-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```

Preparing requires the byte-identical parent, stopped-V1 and completed-V1.1 run
directories under `--runs-root`; missing or altered witnesses stop preparation
before any spend. No historical raw file, score, failed gate or source
dependency is rewritten for compatibility.
