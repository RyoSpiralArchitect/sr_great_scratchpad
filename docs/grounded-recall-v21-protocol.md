# Grounded recall v2.1: clarify the abstention instruction

Date: 2026-10-26. This is a new bounded cohort, not a repaired v2 receipt.
The user requested recalibration and fair, more demanding task design.

## Fixed change

Keep the **same v2 answer schema, assessor, source-citation rules and 16/16
calibration gate**. Only clarify the system instruction with a complete
unavailable-answer example and an explicit prohibition on `{"value": null}`
inside a role object. The entire role field must be null. v2's two object-null
outputs remain failures. `assess_answer` is byte-identical to the pre-v2-call
commit, protected by a source-hash regression test.

Add a separate diagnostic recognizing explicit abstention in top-level-null
and object-null forms. It reports serialization and epistemic abstention
separately, never changes the strict gate, never treats abstention as recovered
memory, and never excuses extra prose, fabricated history or citations.

Fresh calibration cases are `canal` (earlier adoption unestablished) and
`sensor` (explicit earlier adoption). The four confirmation cases `station`,
`library`, `service`, `tile` have not been sent to either provider and retain
exactly the v2 JSON values. The case-file format remains the v2 source/truth
format; `calibration_contract: v2.1` prevents accidental use of the old cohort.

This is not a randomized causal test of the instruction edit: calibration
content also changed. It is a new conformance check on fresh records.

## Execution bounds

- Same four conditions: none, original, prose, roles. Only the system prompt
  changes; user-prompt construction and order remain the v2 implementation.
- Existing `openai-5.6-luna` and `mistral-large` profiles and environment keys.
- Freeze all 48 prompts and effective configs before the first request.
- 16 calibration calls. Proceed only if all 16 pass the original strict gate.
- Then, and only then, 32 confirmation calls (four cases per source-visible
  condition/provider). No-source requests are identical repeated controls.
- Ceiling: 48 calls, 1,000 output tokens per call, 48,000 output tokens total,
  plus input tokens. This is a separate budget from the completed v2 cohort.
- Zero retries, repairs, model substitutions, rescoring, overwritten results
  or reruns of the same stage. Transport errors stop the cohort. Individual
  assessment failures finish the declared stage but prevent the next stage.
- Match the frozen plan, code and profile identity at execution; independently
  audit ordered raw receipts before accepting the calibration gate.

The shared runner accepts an explicit plan builder; the CLI defaults to v2 for
backward compatibility and requires `--contract v2.1` for this plan. Running a
v2.1 plan through the v2 builder fails before provider access. Runtime hashes
intentionally change with new code: old v2 live execution requires its frozen
checkout. Offline v2 receipt reassessment still uses the unchanged v2 assessor.

## Commands

```bash
python3 -S -m unittest discover -s tests
python3 -S sr_great_scratchpad.py experiment grounded-prepare \
  --contract v2.1 --cases scenarios/grounded_recall_v21_cases.json \
  --profiles openai-5.6-luna,mistral-large \
  --out-dir .great_scratchpad/runs/grounded-recall-v21-20261026
# Commit the protocol, code and printed digest before executing.
python3 -S sr_great_scratchpad.py experiment grounded-run --contract v2.1 \
  --plan-dir .great_scratchpad/runs/grounded-recall-v21-20261026 \
  --plan-sha256 FROZEN_DIGEST --stage calibration
python3 -S sr_great_scratchpad.py experiment grounded-run --contract v2.1 \
  --plan-dir .great_scratchpad/runs/grounded-recall-v21-20261026 \
  --plan-sha256 FROZEN_DIGEST --stage confirmation
```

## Claim boundary

A pass establishes this narrow structured contract on the declared records.
It cannot demonstrate a role-label advantage when original notes also reach
the ceiling, or a full-dialogue scratchpad benefit. The separate
[memory task design](memory-task-design-v1.md) is offline-only; its answer schema
and harder tasks are not validated by passing this calibration. No live task
pilot, automatic augmentation, or model-authored memory writer is authorized
by the v2.1 gate.

## Pre-call freeze

- Canonical plan digest: `484124899a5bb750e0c04993812d4a4464186fe6158bbaf5ef17085dd7746121`.
- Plan file SHA-256: `e61169ef8018e94abb24a086a85ede556684a3c901c4cdae4f005dc3b99f3c74`.
- Case file SHA-256: `35c97d508d8bc25e52a547b0be6a7c685f15fbf658c85b6dad6ab308b02fbd97`.
- 192/192 original scorer checks, 6/6 separate abstention diagnostic checks,
  122 repository tests, scoped Ruff, compilation and fake-model CLI smoke passed.
- Input estimate for all 48 calls: 38,786 character/word-estimated tokens,
  not provider billing. Output ceiling remains 48,000 tokens including reasoning.
- Pre-existing run-file aggregate before this turn's new artifacts:
  `d048188663c1ca39e9988a584a6a6890f324a490eae00a64d8152c0602311aa5`.

This is the identity to commit before calling either provider. Live outcomes
will be recorded separately, including a failed gate if one occurs.

Completed outcomes are in the [v2.1 result](grounded-recall-v21-results.md);
the frozen gate and source identities above were not changed after execution.
