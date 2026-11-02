# GPT-6 Luna: Task Kind and Proof Calibration v3

## Questions

1. Do the previous Mistral failures recur on GPT-6 Luna with byte-identical
   source-visible prompts and system instructions?
2. On fresh cases, does explicitly declaring task kind/output shape help?
3. Do branch-specific citation obligations help independently, and does combining
   them cause an interaction or a regression under the same output ceiling?

This is calibration and failure diagnosis, not a retrieval pilot, model
leaderboard, or adoption gate. The previous [v2/v2.1 failures](uncertainty-contract-results.md)
remain failed. No Mistral generation is reissued; neither abandoned pilot runs.
The frozen assessor and its scoring dependencies remain byte-identical.

## Model and Access

The human request was `gpt-luna-6`, referring to GPT-6 Luna. The official model
page and the authenticated model catalog identify it as **`gpt-6-luna`**; the
literal alternate spelling was not listed. The canonical name was disclosed
before implementation. No other model is substituted.

The existing OpenAI key was explicitly approved for reuse. Only its environment
variable name appears in configuration, never the value. The new profile is
opt-in and does not replace existing profiles or alter ordinary chat contracts.

Use the Responses API, high reasoning, JSON-object mode, max_output_tokens4096,
timeout90s and store=false. Do not send temperature, top_p or seed. Official
guidance prohibits temperature/top_p at non-none reasoning, and no sampling seed
is assumed here. High is supported by GPT-6 Luna. Matching the word "high" and
output ceilings is not matching compute or determinism across providers.

Primary references, checked before generation:
- [GPT-6 Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [GPT-6 parameter compatibility](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#migration-quickstart)

## Stage A: Historical Replication

Replicate all twelve calibration cells from each prior protocol, 24 new Luna
requests. Import prompts and system strings directly from the frozen plans;
do not regenerate, translate, normalize, select only failed cells, or fix their
instructions. The original Mistral request settings and raw assessments remain
in the new plan alongside the new native Luna settings.

The original files are authenticated by the exact byte hashes recorded in v2
and v2.1, including plan, attempts, results and raw responses. Recompute their
strict assessments with the unchanged scorer before preparing new calls. Only
the received calibration is reused, never the unissued historical pilot slots.

The comparison is paired by exact input, but provider, adapter, native sampling,
generation date and possibly serving revisions differ. It therefore compares
these two configured systems, not a causal effect of weights alone. There is one
response per cell, no variance estimate, and repeated source/empty views are not
independent case samples.

## Stage B: Fresh Factorial Calibration

Fresh construction seed26110240 was selected on November2 before generation;
the execution directory may use November3 after the local date rollover. Seeds,
case ids and answer ids are disjoint from both historical cohorts. Keep all ten
scenario types. Each has a source-visible view. Additional views:

- Empty records for routing, decision update, and join: three controls.
- Policy plus request, but no override, for urgent-enabled routing: one partial
  rule control. Its flags are known; its route is not licensed.
- Assignment plus team/line link, but no endpoint, for the complete-join case:
  one partial chain control. Cite the available connected chain with null.

These make **15 views of ten authored cases**, five source-known and ten
view-unknown. They are not fifteen independent task instances. Each view is
tested under all four predeclared arms (60 requests):

| Arm | Explicit Kind/Shape | Branch Proof Instructions |
|---|---|---|
| generic | no | no |
| task-kind | yes | no |
| proof | no | yes |
| task-kind+proof | yes | yes |

The generic system is the unchanged v2.1 evidence-state system. The kind factor
prepends the declared task operation and its task-specific output schema to the
user prompt. It keeps both routing flag keys even on empty routing records, and
forbids routing flags on other tasks. This is a kind-plus-shape package, not an
isolated test of a single word or label. The schema is **prompt-visible**, not a
provider-enforced decoder change: all arms use the same JSON-object API mode.

The proof factor adds one fixed instruction block, independently of the case's
hidden ledger or expected value. It lists HOLD versus FAST/BASE obligations,
including the higher-priority exception ruled out by disabled hold, as well as
approved/proposal and complete/partial/pending join obligations. It contains no
gold answer identifiers or source ids. It cannot fill missing facts or authorize
a decision merely because the flags themselves are known.

Whole public source records and their visibility are identical across all four
arms. No new summaries, model-authored notes, retrieved answers, or hidden truth
appear in any provider-visible prompt. No source ids are appended after the
response. No coercion of unknown/unobserved into disabled is permitted.

Rotate arm order cyclically by view. Do not adapt order, cases, budgets or prompt
text to observed responses. All 60 requests are calibration; failed generic or
historical calibration cannot authorize a retrieval pilot. None is planned here.
Finishing all calibration arms is not advancing past any failed historical gate.

## Frozen Budget and Failure Policy

- Exactly24 replication +60 fresh requests, maximum84.
- Maximum4096 output tokens each, 344064 total output allowance.
- Maximum2000000 UTF-8 input-content bytes; exact plan count is saved at freeze.
- Zero retries, repair requests, model substitutions or paid revisions in this
  campaign. One provider invocation per predeclared cell, including failures.
- Client errors, provider incompletion and output limits remain failed outcomes.
  Continue the remaining cells without reissuing the failed slot.
- Stop on model/request identity mismatch or reflected credential material.
  Interruptions remain incomplete, not silently resumable. Execution directories
  are exclusive, so the runner cannot accidentally issue the campaign twice.
- Missing usage is unknown, not zero. Even a response with no final text retains
  its reported reasoning usage and incomplete status. A well-formed partial JSON
  response at an output limit still fails.
- Future work would need15/15 strict for an arm and a separately frozen
  confirmation before any adoption claim; no such follow-up is authorized here.

## Measures and Interpretation

Freeze the v2 semantic assessor, including its legacy `unsupported_concrete`
diagnostic. Report separately: schema, value/null correctness, flag fidelity,
visible/relevant citations, complete proof, strict success and recovered known
answer. Do not convert correct abstention under absent sources into recovery.

Add a named **diagnostic taxonomy**, without changing strict scores: JSON/shape,
flag shape, flag state, unknown-as-disabled, wrong value, over-abstention,
missing citation, invisible citation, irrelevant citation, and resource/transport
outcome. Tags are multilabel, not mutually exclusive. In particular, a correct
FAST route missing the override citation is missing-citation, not wrong-value.

Predeclared contrasts: kind effect without/with proof, and proof effect without/
with kind. Report paired discordance counts and descriptive mean differences.
Do not interpret repeated views as independent observations or use a cell-level
significance test to promote an effect. Retain ties, regressions, ceiling effects,
output failures and all empty/partial controls. Historical shared failures must
be shared on the same paired inputs, not merely on similarly named new cases.

Hypotheses, not observations: explicit kind may reduce field contamination;
branch obligations may reduce proof omissions; either addition may have no effect
at a ceiling or may consume budget and regress another dimension. Abstract any
mechanism only after examining both value decisions and failure receipts.

## Reproduction

Implementation uses standard-library Python. Prior raw directories are local
and ignored; preparation requires their exact pinned receipts, not invented
replacement histories. The plan retains the necessary imported data for audit.

```bash
python3 -S -m unittest tests.test_luna_uncertainty -b
python3 -S -m great_scratchpad.luna_uncertainty prepare \
  --out-dir .great_scratchpad/runs/luna-uncertainty-v3-20261103
python3 -S -m great_scratchpad.luna_uncertainty run \
  --out-dir .great_scratchpad/runs/luna-uncertainty-v3-20261103 \
  --plan-sha256 "$PLAN_SHA256"
python3 -S -m great_scratchpad.luna_uncertainty report \
  --out-dir .great_scratchpad/runs/luna-uncertainty-v3-20261103 \
  --plan-sha256 "$PLAN_SHA256"
```

Commit code, tests, profile and protocol before preparing the plan. Freeze its
source revision, full runtime hashes, schema hash, native parameters, all cases,
prompts, order and exact budgets. Log attempts before issuance and raw final text,
response identity/status, parameters, usage or typed client failure afterwards.
Audit every raw response hash, recompute assessment, and reproduce summary bytes
before interpreting results. Old protocols/results remain unchanged.
