# GPT-6 Luna Native Contract V1.3s: Standalone Semantic-Contract Campaign

## Why A Standalone Version

V1.3 freezes the explicit semantic-contract factor on the V1.1 baseline and
requires byte-identical witnesses of the parent, stopped-V1 and completed-V1.1
run directories. Those artifacts live on a machine that is currently
unreachable, so the witnessed V1.3 campaign cannot be prepared here.

The cooperator authorized a **standalone** campaign instead: identical task
content and budget to V1.3, but rooted as a fresh lineage with no byte
witnesses and no claimed continuity. Fresh case identities cannot be
cryptographically proven disjoint from prior campaigns; they are disjoint only
by construction (seed 26110315 differs from every recorded seed). This is a
disclosed evidential weakness, recorded in the spec as `"standalone": true`
and in the plan (`parent: null`, no retained witnesses).

A standalone campaign is not a downgrade of the witnessed protocols: V1.3
keeps its witness chain for whenever the artifacts are reachable, and V1.3s
results are never presented as the witnessed V1.3 execution or merged into the
retained lineage.

## Frozen Difference

Same as V1.3 relative to V1.1: the `Semantic contract:` block (verbatim
`task_contract.PROOF_INSTRUCTIONS`) is appended to the shared question for
both arms, citation IDs remain free strings (no enum), and all
model/profile/view/budget/gate settings are unchanged. The only further
difference is lineage: seed 26110315, `parent: null`, `retained_failed: null`,
`retained_completed: null`, and no witness verification at prepare time.

## Budget And Gate

Identical limits to V1.3:30 requests maximum,15 per arm,122,880 allocated
output tokens,300,000 serialized input-byte ceiling,4096 per-call output cap,
0 retries/repairs/pilot calls. Same stop rules, same separate measurements,
same15/15 future gate. No retrieval pilot or broad claim is authorized even if
the gate passes, and standalone status additionally bars any lineage-relative
claim against V1/V1.1.

## Reproduction

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v13s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v13s-20261115 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v13s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v13s-20261115 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```

Preparing needs no run artifacts; the runner still freezes plan/runtime hashes
and audits the ledger exactly as witnessed campaigns. Any future standalone
descendant must witness this run's own directory like any other parent.
