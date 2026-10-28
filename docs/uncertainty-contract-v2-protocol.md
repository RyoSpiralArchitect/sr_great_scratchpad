# Evidence-Bearing Uncertainty v2

## Scope and Preservation

This is a fresh, bounded Mistral Large 4 contract experiment, not a rescore of
the [previous pilot](mistral4-reinjection-results.md). Its raw receipts, failed
gates, assessor, scores and result document remain unchanged. New cases and
versioned assessment live in separate modules and a new run directory. Normal
chat's tool/final wire protocol is not changed by this experiment.

The question is whether a model can retain both an undetermined value and the
records explaining that uncertainty, without turning an unconfirmed flag into
a disabled flag. The contract and `parse_answer` validator are reusable without
running the experiment. The [JSON Schema](../schemas/evidence_state_v2.schema.json)
checks structural constraints; the validator additionally checks task-specific
flag keys. Source visibility, flag fidelity and grounding are semantic checks.

## Contract

```json
{"status":"unknown","value":null,"evidence":["m001","m005","m009"],
 "flags":{"urgent":"disabled","hold":"unknown"}}
```

- Exactly `status`, `value`, `evidence`, `flags`; no duplicate JSON keys.
- `known` requires a nonempty exact recorded string; `unknown` requires JSON null.
- Unknown values may have supporting citations. With relevant supplied records,
  cite the connected records that establish uncertainty; with none, cite `[]`.
- Routing flags distinguish `enabled`, `disabled`, explicit `unknown`, and
  `unobserved` (absent from supplied records). Unknown/unobserved are never false.
- Report both flags faithfully even when one is irrelevant to the chosen route.
  Non-routing tasks use `flags: {}`.
- At most eight distinct, visible, relevant source ids. No unrelated citations.

Routing precedence, with the required rules supplied:

| Hold | Urgent | Result |
|---|---|---|
| enabled | any state | HOLD |
| unknown / unobserved | any state | unknown |
| disabled | enabled | FAST |
| disabled | disabled | BASE |
| disabled | unknown / unobserved | unknown |

HOLD needs the override and request. FAST/BASE also need the policy. Missing
rules/links do not license a value. All four flag states and sixteen pairs have
independent offline truth-table tests; always abstaining fails the known controls.

## Matched Comparison

Three system prompts share identical user prompts, source records, retrieval,
sampling and output ceilings within each case/context:

1. `legacy`: the unchanged historical two-field prompt, including null => `[]`.
2. `guarded-legacy`: that prompt plus the explicit routing/unknown guard rules.
3. `evidence-state`: four-field evidence-bearing uncertainty plus the same guards.

The last contrast includes both a richer representation and its instructions,
not JSON shape in isolation. Neither change is provider-enforced JSON Schema:
all use the same JSON-object mode. System lengths and actual token consumption
can differ; ceilings are matched, not total realized spend.

Two assessment layers avoid confusing format with semantics:

- Keep each variant's strict schema result separate. Old null-with-citations is
  still invalid under the old contract, even if a common diagnostic finds the
  decision and citations useful. No historical score is changed.
- A new, explicitly versioned common diagnostic checks value/null against the
  **supplied** records, visible/relevant citations and proof coverage. It permits
  evidence-bearing null for any variant. Value correctness is also reported by
  itself, because old prompts forbid the citations now required for grounded
  unknown; the grounding difference alone is not evidence of better decisions.

V2 strict success additionally needs status/value agreement and exact visible
flag states. A world-answerable case with hidden proof may correctly abstain,
but is never counted as recovered. Unsupported concrete answers are distinct
from prose strings that verbalize uncertainty but violate the null contract.

## Frozen Cohort and Budget

`scenarios/uncertainty_contract_v2.json` is fixed before paid calls.

- Calibration seed 26102840: ten source-visible cases, plus empty-source routing
  and join controls, twelve calls total. BASE and absent-hold controls are here.
- Pilot seed 26102850: eight fresh cases: hold unknown; urgent unknown; hold
  overriding unknown urgent; fast route; approved update; proposals only; complete
  join; pending endpoint. Four globally known and four globally unknown cases.
- Actual generator seeds are `seed * 100 + scenario index`; neither cases nor
  answer identifiers reuse the earlier cohort. Calibration/pilot are disjoint.
- Three contexts: window-only, linked retrieval, full history. Each archive has
  72 distractors and three relevant records in the old prefix. Window 700 chars;
  whole-record memory 1200 chars; linked top16/hops2/per-hop4 unchanged. All eight
  cases remain regardless of retrieval coverage; no oracle selection for recall.
- Three variants per context: 72 pilot calls. Rotate variant order by case/context.
- Maximum 84 calls, 344064 output tokens, 2000000 input UTF-8 bytes. Exact planned
  bytes/estimated input tokens are saved before execution. No model-based writing,
  extra tool calls, repair calls, substituted cases or automatic retries.
- Explicit `mistral-large-4`, high reasoning, temperature0, top_p1, seed261028
  (native `random_seed`), JSON-object mode, max_tokens4096, timeout90s. The model
  name is provider-reported identity, not an immutable weight revision.

Provider references checked before this run: [Large 4 model page](https://docs.mistral.ai/models/mistral-large-4)
and [chat API](https://docs.mistral.ai/api/endpoint/chat). Model-specific high
reasoning settings also retain the earlier campaign's working request parameters.

Advance to the pilot only after **12/12 calibration strict successes**, audited
from raw receipts. Do not weaken the gate, scorer or prompts after observing it.
Any failure stops advancement and remains a result; a future revision needs a
new version/cohort rather than rerunning a failed slot.

Client errors and output limits are predeclared failed outcomes. Attempt each
remaining planned cell once, including after such failures. Missing usage stays
unknown, never zero. Identity/request mismatch stops the campaign. Interruption
leaves an incomplete stage that cannot be silently reissued. Completed stage
directories are exclusive, preventing accidental duplicate paid calls.

## Reproduction

Commit code/tests/protocol before freezing the plan. Keys come only from the
existing `MISTRAL_API_KEY` environment; no secret belongs in a plan or report.

```bash
python3 -S -m unittest tests.test_uncertainty_contract
python3 -S -m great_scratchpad.uncertainty_experiment prepare \
  --out-dir .great_scratchpad/runs/uncertainty-contract-v2-20261028
```

Record the printed plan digest, then run calibration, inspect its raw-audited
gate, and only then run the pilot:

```bash
python3 -S -m great_scratchpad.uncertainty_experiment run \
  --out-dir .great_scratchpad/runs/uncertainty-contract-v2-20261028 \
  --plan-sha256 "$PLAN_SHA256" --stage calibration
python3 -S -m great_scratchpad.uncertainty_experiment run \
  --out-dir .great_scratchpad/runs/uncertainty-contract-v2-20261028 \
  --plan-sha256 "$PLAN_SHA256" --stage pilot
python3 -S -m great_scratchpad.uncertainty_experiment report \
  --out-dir .great_scratchpad/runs/uncertainty-contract-v2-20261028 \
  --plan-sha256 "$PLAN_SHA256"
```

Plans hash the full runtime, prompts, sanitized profile, exact order, cases,
truth ledgers and budgets. Each attempt is logged before issuance; each receipt
records output, request parameters, response identity, finish status, duration,
usage or typed client error. Audits recompute assessments and aggregates from raw
receipts and reject tampering/incomplete stages. The eight authored cases are
not independent population samples. Full-history is a visibility ceiling, not
a matched-memory-efficiency control. This is not a general reasoning or retrieval
efficacy claim, and no old/new-cohort causal effect is estimated.
