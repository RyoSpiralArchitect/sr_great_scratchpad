# Evidence-State Contract: Mistral Large 4 Results

## Outcome

The new output contract can preserve an undetermined value together with its
supporting records. It distinguishes enabled, disabled, explicitly unconfirmed,
and unobserved flags; neither of the latter two is treated as false by the
reference logic or validator.

**Neither live calibration passed the frozen 12/12 gate. No three-variant pilot
was run.** V2 completed at 11/12 and v2.1 at 10/12. These are retained negative
gates, not an adoption decision or a scratchpad-vs-raw-model effect estimate.
The [earlier reinjection results](mistral4-reinjection-results.md), raw receipts
and strict scores remain unchanged. Normal chat's wire protocol is unchanged.

## What Ran

- Explicit `mistral-large-4`, high reasoning, temperature0, top_p1,
  random_seed261028, JSON-object mode, max_tokens4096, timeout90s.
- Two disjoint ten-case calibration cohorts, each with two additional
  empty-source controls: 24 calls total, not 24 independent scenarios.
- Every call returned a completed response from the requested model. Zero
  retries, repair calls, output-limit failures, client errors or missing usage.
- V2.1 changed only the complete empty-source examples; its validator, reference,
  proof requirements and gate were unchanged. The two legacy prompts were also
  unchanged, but neither legacy pilot arm was issued.
- Total provider-reported usage: 57112 tokens (16661 input / 40451 output).
  Planned but abandoned pilot cells incurred no generation calls.

See the frozen [v2 protocol](uncertainty-contract-v2-protocol.md) and
[v2.1 revision](uncertainty-contract-v21-protocol.md). V2.1 was a calibration-driven
prompt revision, not a preregistered first attempt. The campaign stopped after
that revision failed, as announced; no further paid revision was attempted.

## Separate the Measurements

| Calibration | Value/null correct | Schema valid | Flags faithful | Value + cited proof | Strict contract |
|---|---:|---:|---:|---:|---:|
| v2 | 12/12 | 11/12 | 11/12 | 12/12 | 11/12 |
| v2.1 | 12/12 | 11/12 | 11/12 | 11/12 | 10/12 |

The value/proof diagnostic ignores the schema-specific flag shape. Strict
success additionally requires that shape and exact flag fidelity. These are new,
versioned diagnostics, not retroactive changes to the old two-field assessor.

Across the two cohorts:

- Evidence-bearing unknown **with relevant source records**: 10/10 strict.
  This covers unconfirmed routing flags, proposals without approval, a pending
  endpoint, and an absent hold declaration.
- Three routing uncertainty controls per cohort (hold unknown, urgent unknown,
  hold unobserved): 6/6 strict; no default BASE/FAST decision was made.
- Hold overriding an unknown urgent flag: 2/2 strict. The model did not simply
  abstain whenever any flag was unknown.
- Globally known, source-visible controls: values 10/10 correct, strict 9/10.
- Empty-source controls: values 4/4 correct abstentions, strict only 2/4.

Those repeated scenario types are not independent population samples. There is
no basis here for claiming universal uncertainty handling, an improvement over
the old cohort, retrieval efficacy, or a benefit relative to the legacy arms.

## Preserved Failure Cases

### V2: Missing Flag Fields

The empty-source routing control returned:

```json
{"status":"unknown","value":null,"evidence":[],"flags":{}}
```

Its decision is safe, but routing requires both flags to be `unobserved` when
the request itself is absent. The strict gate stayed failed at 11/12. Its 72
pilot cells were never issued. V2.1 added explicit routing and non-routing
empty-source examples and used new cases, without loosening assessment.

### V2.1: Correct Value, Incomplete Proof

The urgent-enabled source case returned:

```json
{"status":"known","value":"FASTPe77c2","evidence":["m001","m009"],
 "flags":{"urgent":"enabled","hold":"disabled"}}
```

The route and flag states are correct. However, the frozen proof requires
`m005`, the hold-override rule, as well as the policy and request. That rule was
supplied but not cited. This is a citation-completeness failure, **not a wrong
route or a fabricated answer**. It remains a strict failure.

The frozen diagnostic named `unsupported_concrete` counts concrete outputs with
missing required citations as well as wrong/unlicensed values; it is 1 here.
Do not relabel that count as a hallucinated routing decision. Its exact metric
is retained, while value correctness and this error taxonomy are reported
separately. No route/value disagreement with the supplied-record reference was
observed in these 24 responses.

### V2.1: Task-Type Contamination

The empty-source **join**, not routing, control returned:

```json
{"status":"unknown","value":null,"evidence":[],
 "flags":{"urgent":"unobserved","hold":"unobserved"}}
```

This correctly abstains but imports routing-only fields into a non-routing
question, whose flags must be `{}`. The fresh empty-source routing control did
pass. These two observations do not establish a causal benefit/harm of the new
examples; the cohorts also differ. They show that task-kind inference remains
fragile even with complete examples. V2.1's 72 pilot cells were also not issued.

## Next Bounded Development

The parser fails closed on both flag shapes and never repairs uncertainty into
false, invents missing citations, or silently fills proof from the hidden ledger.
The remaining work is not solved by simply permitting evidence with null:

1. Make task kind explicit in the input and select a task-specific output schema,
   so absent records do not force the model to infer whether flags are required.
2. Express branch-specific proof obligations clearly, including the supplied
   higher-priority rule when a known flag disables its exception. Validate each
   obligation without auto-appending a citation the model did not provide.
3. Freeze another fresh calibration only after offline tests, retaining empty
   controls in every family and the known HOLD counterexample to over-abstention.
   Any later provider run needs a new version, cohort and bounded authorization.

These are prospective proposals, not additional paid work in this campaign.

## Provenance and Verification

| Cohort | Source Commit | Frozen Plan Digest |
|---|---|---|
| v2 | f3c198a63f2dcbf7651d3633412057aed0177870 | cac1989ce3fcdbc52d5f3726cd9dbe959a48371134b9a25e5a1b1d74a20bc318 |
| v2.1 | 31a65ac75f658e1f36834889cd911d16d546b801 | 5fc5472176d619e1b100e5c749653ff10f5c69f0c4f05ef7efbaf6f9e687b59a |

Local directories are `.great_scratchpad/runs/uncertainty-contract-v2-20261028`
and `.great_scratchpad/runs/uncertainty-contract-v21-20261028`. Both retain
plan, raw attempts/responses, results, audit and calibration-only summary.
Use the recorded source revision for exact runtime-hash replay. The ordinary
`report` command is for a gated, complete pilot; no pilot report is claimed here.

V2.1 assessments were recomputed from raw receipts twice with equal results. A direct
pilot invocation was also checked to fail at the gate, before credential lookup
or model invocation, with no pilot directory created. V2 was audited before the
revision and reassessed without changing its contract module.

| v2.1 Artifact | SHA-256 |
|---|---|
| plan.json | fa6a6310db635e770962af98eb87a03846bd4c65a472bf2764da0b2e3afd5825 |
| calibration/result.json | 05675287a43e03f6fc0d16c3df140ded41aba22cea7f6408bd732ce2523f06c4 |
| calibration/attempts.jsonl | 112d52b306e5d685ffb04e8e807225f5ec6072122aad4df4618ccff331f38514 |
| calibration/responses.jsonl | 073614b0e97537595d89f31d9dada967bf4a79060e5af047cdf6e132b13802ea |
| summary.json | b6ade057fd5feffaa051ff9cf79c21db6bc73ff0fd04c03e3bdcaf94499f0626 |
| audit.json | feafd709a7e9240cdb5a68b0906d2778c9cc1089582de9d3026b45f471db8a16 |

V2 receipt hashes are in its revision protocol. The previous reinjection tail's
five recorded artifact hashes were checked unchanged after this work.

Offline verification: 175 unit tests, scoped Ruff, and the existing fake-provider
REPL/runtime smoke all passed. The tests cover all sixteen flag pairs, missing
rules, known controls, empty/partial inputs, retained unknown evidence, duplicate
keys, irrelevant/invisible citations, wrong flags, raw-receipt tampering, failed
gates, output limits, client errors without retries and response identity mismatch.
Those simulations test failure handling; the new live cohorts had no resource or
transport failures. Offline tests do not override the failed live gates.
An exact credential-value scan over 22 new source/artifact files found zero
matches; no key value is stored in the plans, receipts or report.
