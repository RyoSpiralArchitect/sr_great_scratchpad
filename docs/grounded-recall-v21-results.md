# Grounded recall v2.1: calibration and four-case confirmation

Date: 2026-10-26. The [pre-call protocol](grounded-recall-v21-protocol.md)
passed its unchanged strict gate: **16/16 calibration, then 32/32 confirmation**.
This is conformance to a narrow sourced-answer contract, not demonstrated
scratchpad or role-label superiority.

## Results

| Stage | Source-visible responses passed | No-source strict abstentions | Total |
|---|---:|---:|---:|
| Fresh calibration: canal, sensor | 12/12 | 4/4 | 16/16 |
| Confirmation: station, library, service, tile | 24/24 | 8/8 | 32/32 |
| Total | 36/36 | 12/12 | 48/48 |

Each provider passed all 24 of its calls. Confirmation by condition:

| Profile | none | original | prose | roles |
|---|---:|---:|---:|---:|
| openai-5.6-luna | 4/4 | 4/4 | 4/4 | 4/4 |
| mistral-large | 4/4 | 4/4 | 4/4 | 4/4 |

The four source-visible confirmation cases were predeclared and previously
unqueried, not selected from successful calibration outputs. The no-source
condition is repeated draws of the same empty-record prompt; those four calls
are not four distinct no-source tasks or evidence of memorized content.

All 108 role claims across the 36 source-visible responses had accepted values
and supporting visible quotes. Earlier-adoption status/evidence passed 36/36;
both established and unestablished histories are represented. Explicit
non-adoption remains an offline test, not a live case stratum.

No object-null outputs occurred. The separate diagnostic recognizes all 12
no-source outputs as explicit abstentions and does not count any as recovery.
Raw-receipt reassessment reproduced both stage results. No schemas, aliases,
criteria or code changed between calibration and confirmation.

## What changed, and what did not

The system instruction now supplies the entire unavailable-answer object and
explicitly forbids a null `value` inside a role object. The v2 schema and
assessor are unchanged. The old v2 cohort was independently re-audited and
remains **14/16, gate failed**; no old receipt or score was overwritten.

The fresh calibration cases differ from v2, and provider versions/time are not
controlled. Do not attribute the whole before/after difference causally to one
prompt sentence. The direct observation is that the clarified contract worked
on this frozen new cohort, including the previously unused four cases.

Original records, prose and roles again all reached the ceiling. This shows
neither an advantage from structured labels nor full-dialogue memory utility.
The new [memory-sensitive task pack](memory-task-design-v1.md) was constructed
and audited separately, with **zero provider calls** and model difficulty still
`NOT_MEASURED`. This confirmation does not validate that different task schema.

## Provenance and budget

Pre-call commit: `0abe0921bec182d37e2b5329228ff39325eaff40`.
Canonical plan digest:
`484124899a5bb750e0c04993812d4a4464186fe6158bbaf5ef17085dd7746121`.

Calibration ran `2026-10-26T01:06:15+09:00` to `01:07:38+09:00`.
After its complete raw-receipt gate passed, confirmation ran
`2026-10-26T01:08:05+09:00` to `01:10:32+09:00`.
There were 48 attempted/recorded calls, zero retries and zero transport errors.

| Profile | Calls | Provider input tokens | Provider output tokens | Total |
|---|---:|---:|---:|---:|
| openai-5.6-luna | 24 | 20,757 | 5,778 | 26,535 |
| mistral-large | 24 | 22,262 | 5,367 | 27,629 |
| Total | 48 | 43,019 | 11,145 | 54,164 |

Usage is provider-reported, not estimated. Output, including any reasoning
accounted there, remained within the 48,000-token ceiling. Input is additional;
the character/word estimate of 38,786 for all inputs underpredicted actual
provider accounting. It is not a reliable billing cap or a dollar-cost estimate.
Returned model identifiers were `gpt-5.6-luna` and `mistral-large-latest`, which
are aliases rather than immutable weight revisions.

The local ignored run directory is
`.great_scratchpad/runs/grounded-recall-v21-20261026/`. It is not included in a
fresh clone. File-byte SHA-256 receipts:

| File | SHA-256 |
|---|---|
| plan.json | `e61169ef8018e94abb24a086a85ede556684a3c901c4cdae4f005dc3b99f3c74` |
| calibration/result.json | `f8db5ce2b02bf7e89a27b8e64a9b7a07527a9fe5ba91f8e828a0312109701d8b` |
| calibration/responses.jsonl | `851d81c74c68708b715118226b71e9a1cda45fadcb691a008820de136619ba88` |
| confirmation/result.json | `3368d19f26fb4e584f7fa7e1ef20213df32f780c8f18732457301966d8465b7b` |
| confirmation/responses.jsonl | `634c5405a0300a7f20f6a7fbd7aeeea9559fd23f84b9fff59556e685d46ccb0f` |

Each stage also has a derived `diagnostic.json` separating strict format/pass,
source-grounding and explicit abstention. Its interpretation cannot alter the
frozen stage's `gate_passed` field. The audit's canonical result digests are
`24adccaec6bc4ad46d82df6c5567c6b691574f63eb2b3f1608da48db18cc7ac0`
and `5c92f4b4924486aff928d1fe503e3957a5f0e81556a10f34da6036c75d5a02aa`.

The previous run files retain aggregate hash
`d048188663c1ca39e9988a584a6a6890f324a490eae00a64d8152c0602311aa5`.
Stored provider configuration is byte-unchanged. Code, cases and tests retain
the pre-call commit contents; only result documentation was added afterward.
Local validation passed 122 tests, scoped Ruff, compilation, whitespace checks
and the existing fake-model CLI smoke. No hosted test-CI success is claimed.

## Next experiment boundary

The task pack intentionally retains all failures: on the six old-evidence pilot
tasks, the current top-4 ranker exposes the complete proof in 2/6 while the
recency archive exposes it in 6/6. These are exposure counts, **not model scores**.
The small archive fits into that active control's character budget. The result
locates current selection limits without a fabricated positive treatment effect.

Before paid task evaluation, separately calibrate the new two-field answer
contract, predeclare archive-pressure tiers retaining the current small tier,
and compare any multi-query/budget-filling retrieval policy as a new treatment.
Freeze models, counts and total budgets before calls. Keep all null/negative
results, compare against the active archive baseline, and leave automatic
augmentation and autonomous memory-writing claims out of scope.
