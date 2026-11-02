# GPT-6 Luna Native Contract V1: Frozen Paired Calibration

## Question And Scope

Does enforcing the caller-selected output shape in the Responses request change
shape fidelity, uncertainty handling or grounded decisions relative to the same
schema supplied only in text? This is a new bounded contract calibration based
on PR #11, not a retrieval pilot, a historical rerun or an adoption decision.

The caller-side implementation is `structured_tasks.call_structured_task` from
PR #11. Native calls exercise that helper directly. Control calls use the shared
Responses adapter without the native format. Ordinary chat and old experiments
are not altered. No model substitution or new credential is requested.

## Frozen Inputs

- Model: `gpt-6-luna`, profile `examples/gpt-6-luna.json` / `openai-6-luna`.
- Adapter: `openai-responses`, `https://api.openai.com/v1`, high reasoning,
  store=false, timeout90s, max_output_tokens4096.
- No temperature, top_p or seed request parameter is added. The case-construction
  seed is **26110311**, not a provider sampling seed.
- Ten authored scenarios: hold-unknown, urgent-unknown, hold-dominates,
  urgent-enabled, approved-update, proposals-only, complete-join, pending-join,
  base-route, hold-unobserved.
- Fifteen views: ten source views, three empty-source controls (routing, decision,
  join), one missing-override view and one truncated-chain view.
- All entities, case identities and construction seeds are disjoint from the
  retained Luna v3 cases. Record IDs such as `m001` are case-local labels; they
  are not globally unique across historical cases.
- New entities use the existing authored templates. Views share ten underlying
  cases and are not fifteen independent natural tasks.
- Source views contain all relevant authored records, not distracting archives.
  No retrieval, model-authored note, hidden-state inspection or memory write occurs.

The runner freezes all cases, public task objects, exact prompts/system strings,
visible IDs, source-limited expected states and request-body fingerprints before
spending. Typed answer ledgers stay in the local plan/scorer, never in model
input. Public records contain exactly `id` and the complete original source text.

The prior run is byte-witnessed using its plan, attempts, responses, result,
summary and audit hashes. Its source and scores are not regraded under current
operational code. No historical hash guard is relaxed.

## Two Arms

Each pair has byte-identical user prompt and system text, the same caller-chosen
family and complete public records, the same explicit schema text in its question,
and the same model, reasoning and output cap. The system text is PR #11's minimal
native-task system; no additional branch-proof instructions are added.

| Arm | Responses `text.format` |
|---|---|
| json-mode | `{"type":"json_object"}` |
| native | Task-specific JSON Schema with `type=json_schema`, `strict=true` |

Only `text.format` changes on the wire. Native calls do not receive extra answer
or evidence hints. The schema admits unknown/null with supplied evidence and
requires both routing flags, including unknown and unobserved states.

Pair order alternates: native first for8 views, JSON mode first for7. The scenario
and view order are fixed. Calls are stateless and do not see earlier responses.
Provider caches or unobserved service changes are not controlled.

Both arms have the same output-token allocation. Native schema transport can
add reported input tokens and first-schema processing overhead; equal visible
prompts and caps do **not** promise equal billed tokens or latency. Measure those
from receipts, separately from correctness. Input-token preflight estimates count
visible text only and explicitly do not estimate this schema overhead.

## Budget And Stop Rules

- Exactly30 planned requests: 15 per arm.
- At most4096 output tokens per call; total allocation122,880, or61,440 per arm.
- Explicit serialized-input bound:300,000 UTF-8 bytes across the campaign.
- Retries, JSON repair, smoke requests, paid schema pilots and retrieval pilots:0.
- Write an attempt record and increment the manifest before each request.
- One execution directory can be created only once. Never resume or reissue a slot.
- Local contract failures retain the received result and count as failures; they
  do not trigger repair. Refusals/incomplete responses retain known usage and do
  not count as successful answers.
- Stop the campaign on transport/API rejection (including unsupported schema,
  model or quota), identity/parameter mismatch or credential reflection. Retain
  the partial ledger, count unavailable usage explicitly, and do not switch models,
  weaken the format, or spend a corrective call under this protocol.
- A stopped run with no complete pair reports a null paired difference, not zero.
- The run command exits nonzero when stopped; the retained prefix can still be audited.
- Never store a reflected credential. Redaction is marked, the received usage is
  retained, and the campaign stops.

## Measurements And Gate

Apply the same strict local parser and source-ID checks to both arms. Reuse the
unchanged typed reference semantics and evidence-state assessor. Measure these
separately:

1. Provider completion, model/request identity, refusals/errors and usage reporting.
2. Output shape and caller-contract conformance, including status/value consistency.
3. Correct value and faithful urgent/hold state, without unknown-as-disabled coercion.
4. Supplied/relevant citation IDs and coverage of the required connected proof.
5. Strict success: completed correct-identity response, local caller contract,
   correct value, faithful flags, relevant visible citations and full required proof.

In particular, every visible partial-rule record being cited does not authorize
a known FAST value if the override rule is absent. Structural success cannot
turn that decision into a pass. Unknown/null can and should retain its connected
evidence; an empty view should not cite anything.

The future conformance gate for an arm is **all15/15 strict passes**. Both a caller
contract and the independent semantic score must pass. Even passing this narrow
gate does not authorize a retrieval pilot or establish scratchpad efficacy,
general model quality, prompt-injection resistance or decision authorization in
unseen tasks. All historical failed gates remain unchanged.

Analyze all planned slots, report attempted denominators and unattempted slots
when stopped, and retain ties, nulls, negative effects and first failures. Do not
select cases after results, remove a failed slot or revise the scorer. Compare
the old v3 results only descriptively: templates, prompts and generation dates
are different. The paired new-format contrast is the actual controlled comparison.

## Reproduction

Commit source/spec/this protocol before preparing a plan. `prepare` refuses
uncommitted runtime/spec/protocol changes; `run` and `report` verify the frozen
runtime hashes, profile and explicit plan digest. Later source changes require
the recorded source revision or a new protocol, not a guard bypass.

```bash
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --out-dir .great_scratchpad/runs/luna-native-contract-v1-20261103 \
  --max-calls 30 --max-output-tokens 122880 --max-input-bytes 300000

python3 -S -m great_scratchpad.native_contract_experiment run \
  --out-dir .great_scratchpad/runs/luna-native-contract-v1-20261103 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST

python3 -S -m great_scratchpad.native_contract_experiment report \
  --out-dir .great_scratchpad/runs/luna-native-contract-v1-20261103 \
  --plan-sha256 THE_PRINTED_FROZEN_DIGEST
```

The existing credential is supplied through `OPENAI_API_KEY`; no secret is written
to a profile, plan or source file. Raw results remain in the ignored run directory.
Checked-in results will identify source/plan/receipt hashes and disclose the
validation boundary instead of publishing a key or claiming an unrun live gate.
