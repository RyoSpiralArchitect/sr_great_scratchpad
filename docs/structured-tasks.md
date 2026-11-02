# Caller-Owned Native Task Contracts

`great_scratchpad.structured_tasks` is an explicit opt-in single-call path for
the Responses adapter. Ordinary chat, prompt-only `task_contract.declare_task`,
old schemas, frozen cases, raw receipts and scoring rules are unchanged.

The caller selects `decision-update`, `scoped-exception` or `distributed-join`
before requesting an answer. The model cannot select a different task kind,
including when no records are supplied. The client sends that task's closed
schema as Responses `text.format`, with `type=json_schema` and `strict=true`.
It never silently substitutes JSON mode or a prompt-only fallback.

## Inspect Without Spending

```bash
python3 -S -m great_scratchpad.structured_tasks --family scoped-exception
```

This command prints the exact format object. It loads no profile or credential
and contacts no model. The command does not run an experiment.

## Make One Explicit Call

The library call below contacts the configured provider. It is not part of the
offline inspection command or the default REPL workflow.

```python
from pathlib import Path

from great_scratchpad.llm import LLMResponseError
from great_scratchpad.storage import load_llm_config
from great_scratchpad.structured_tasks import TaskContractError, call_structured_task

cfg = load_llm_config(Path("."), "examples/gpt-6-luna.json", "openai-6-luna")
task = {
    "family": "scoped-exception",
    "question": "Which route is licensed for request Q?",
    "records": [
        {"id": "request-Q", "text": "Request Q: urgent unknown; hold enabled."},
        {"id": "hold-rule", "text": "An enabled hold flag selects HOLD."},
    ],
}
try:
    result = call_structured_task(cfg, task, max_output_tokens=4096)
except (TaskContractError, LLMResponseError) as error:
    # Keep the received failure and its usage in the caller's experiment ledger.
    received = error.result
    raise
else:
    answer = result["answer"]
    received = result["llm"]
```

Transport/configuration failures can still raise `SystemExit` without a received
receipt. Missing usage is not zero consumption. When the shared adapter estimates
usage, `usage_reported=false` and `usage.estimated=true` remain visible; do not
present these as reported API tokens.

Inputs contain exactly `family`, `question`, and `records`. Every record has only
nonempty `id` and `text` fields; duplicate IDs, hidden answer/eligibility fields
and additional top-level fields fail before any model call. The client sends
complete record text, without truncating, annotating or retrieving extra records.
Text can still contain misleading instructions: treating records as evidence in
the system message is not a prompt-injection security guarantee.

## Two Validation Layers

| Layer | Check |
|---|---|
| Native schema | Exactly `status`, `value`, `evidence`, `flags`; every field required; no extra keys |
| Routing shape | Both `urgent` and `hold`, each one of enabled/disabled/unknown/unobserved |
| Other task shapes | Empty closed `flags` object, even with no source records |
| Local consistency | known with a nonempty string, or unknown with null |
| Local citation hygiene | At most eight distinct nonempty IDs, all supplied by the caller |
| Local minimum support | A known value requires at least one supplied citation |
| Receipt identity | Completed Responses receipt, exact requested model identifier and exact strict format |

`unknown` plus real supplied evidence is valid. An enabled hold with an unknown
urgent flag can still return known HOLD. No flag is filled in, erased, converted
to a Boolean, or treated as disabled by the validator. An empty/malformed flag
object is an error, not a request to repair it.

The local parser reuses the existing strict answer contract, including duplicate
JSON-key rejection. Invalid output raises `TaskContractError` with the original
received result, including raw text, identity and usage. Provider refusals,
incomplete/failed responses and missing text raise `LLMResponseError` with their
received result. Neither path retries, repairs, writes scratchpad memory, or
discards known usage. The helper itself does not persist a run: the caller owns
attempt logging, manifests, failure receipts and usage accounting.

**Not validated:** truth of the value, relevance/completeness of citations, whether
a rule licenses a decision, faithful flag interpretation, or resistance to record
injection. Even a successful result explicitly reports `semantic_grounding` and
`decision_authorization` as `not_checked`. Citing an arbitrary supplied ID does
not satisfy a semantic proof obligation. Do not use these results as automatic
memory-write approval.

## Compatibility And Limits

The first implementation accepts only `openai-responses`. Command/HF generation
and Chat Completions profiles fail before sending; none is advertised as native
schema support. No provider capability or hidden-state support is inferred from
an OpenAI-compatible URL. Explicit model IDs must match the received model ID;
an alias resolving to another snapshot is rejected, with the receipt retained.

Profiles are copied, not mutated. The caller's explicit output budget can lower,
but never raise, a configured token cap. The helper replaces a profile's weaker
`json_mode` with the native contract; a conflicting explicit `response_format`
or `previous_response_id` is rejected. A provider rejecting this schema/model
combination causes an error, not a fallback or a second request.

The native schema intentionally does not reuse the prompt-only schema's
`if`/`then`/`else`, `uniqueItems` or string constraints. Responses accepts a subset
of JSON Schema; consistency and citation uniqueness remain local checks.
See the official [Structured Outputs schema requirements](https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas)
and [refusal handling](https://developers.openai.com/api/docs/guides/structured-outputs).

## Validation And Next Gate

Offline tests inspect real adapter requests and completed/failure receipts,
including unknown-with-evidence, empty sources, every flag state, missing/extra
fields, duplicate keys/IDs, foreign citations, model mismatch and downgrade
attempts. The initial implementation was verified offline. The subsequent
[frozen GPT-6 Luna calibration](luna-native-contract-results.md) retained a
two-attempt V1 compatibility stop, then completed thirty explicitly authorized
fresh V1.1 requests. Both arms passed shape checks 15/15, but strict success was
native 12/15 versus JSON mode 13/15. Native prose citation strings were correctly
rejected locally; native shape alone did not establish semantic grounding.

Before any adoption, freeze a new bounded protocol using fresh cases. Compare the
same schema-visible prompts, system instructions, records, model, budgets and
order-balancing, changing only the native format versus JSON mode. Record schema
acceptance, refusals and usage separately from local shape success, semantic
grounding, decision licensing and flag faithfulness. Retain every failed slot;
do not rerun the historical campaign or relax its runtime/scoring hash guards.
