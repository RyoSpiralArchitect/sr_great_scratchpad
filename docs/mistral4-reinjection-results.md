# Mistral Large 4 reinjection results

Date: 2026-10-28 (Asia/Tokyo). All 168 planned pilot requests were attempted
once: 167 provider responses and one client timeout. Original stopped runs stay
failed. These are exploratory end-to-end results after two stopping-rule
amendments, not a passing preregistered pilot or independent confirmation.

## Question and implementation

Does identifier-linked, budget-filling retrieval improve grounded answers
relative to the legacy top-4 ranker and a recency archive under the same
additional-memory cap? The new reader follows public identifier links across
at most two expansion hops, excludes recently visible records, and packs whole
verbatim records. It uses no model call, answer ledger or gold filtering.

The normal chat runtime exposes the ranker through `--recall-policy linked`
and packs complete raw/annotation fields with file provenance. Recent-record
exclusion belongs to the benchmark wrapper; normal chat uses the current query
and can repeat information already mentioned in history. Its payload also
differs, so these scores do not measure autonomous note-writing or ordinary
conversational trajectory retention.

## Append-only campaign ledger

| Attempt | Pre-call commit | New inference HTTP attempts | Outcome |
|---|---|---:|---|
| v1, reasoning none | `607c2bbbd06d0abfed37cfd2bfcfc351ca2bbfb4` | 6 | 5/6 calibration; pilot blocked |
| v1.1, reasoning low | `42833167ca4c4a7901f388ca815d427ec3bf1eba` | 1 | HTTP 400: only none/high supported; no response |
| v1.2, high with default nucleus sampling | `51f7b19dadd73fb045954d951237ed60c4b1b9bf` | 1 | HTTP 400: greedy sampling requires top_p=1; no response |
| v1.2-r1, high with explicit top_p=1 | `cd484d474c44180351b57815ffb0d41e0dab6eb1` | 70 | 6/6 calibration; original pilot stops at request 64 on output limit |
| length-aware continuation | `2d7400e475d1a188e51313a8f50f947485720cfb` | 93 | imports 64; stops at overall request 157 on read timeout |
| client-error tail | `144398c4087a4939c110cf94d8a157c04149c877` | 11 | imports 156 responses plus the unreceived-attempt event; all 168 cells recorded |

The first failure was a reader error: the prompt supplied all scoped-routing
records, the response cited them, but it chose the hold route although the hold
flag was disabled. Its score remains failed. The two rejected requests have no
provider usage receipt. No stage was resumed in place or silently retried.

The high-reasoning cohort has fresh seeds relative to v1. Its first transport
attempt produced no generated responses; the repaired request plan reuses those
still-unanswered cases. Cases and reasoning budgets both changed from v1, so
the campaign cannot isolate the causal effect of reasoning effort.

The continuations keep the original prompts, settings and every attempted
cell. Neither repeats an attempted request. A length limit is an observed
failure; the timeout has `raw_output=null` and `usage=null`, not a reconstructed
model answer. Imported raw JSONL prefixes remain byte-identical. The original
pilot and continuation still have status `error`. See the
[length amendment](mistral4-reinjection-continuation.md) and
[client-error amendment](mistral4-reinjection-timeout-tail.md).

## Frozen identities and conditions

- run directory: `.great_scratchpad/runs/mistral4-reinjection-v12-r1-20261028/`
- plan digest: `97c3485741d46ced29fdde6a8976c4fe1848b758aed089b71252b15daf88aba1`
- requested and calibrated returned model: `mistral-large-4`
- profile: `mistral-large-4-high`; high reasoning, temperature 0, top_p 1,
  random_seed 261028, JSON mode, output limit 4,096 tokens including reasoning
- calibration seed: 26102820; pilot seed: 26102821
- ordinary history: 700 characters; additional archive: 1,200 characters
- 3 task families x 4 regimes x 2 pressure tiers x 7 conditions = 168 pilot requests

Both tiers reuse the same task semantics and are not independent replications.
Full history is an information-rich reference; oracle evidence is privileged.
The primary comparison is linked minus archive-recent on six answerable
delayed/interference cases per tier. All cases, ties, failures and insufficient
controls remain in the cohort. The explicit model name is not an immutable
weight revision.

## Delayed/interference recovery

Each entry has six answerable paired cases per tier. Strict success requires
the exact value, complete reference proof, and visible cited records.

| Distractors | Window | Recency archive | Legacy top-4 | Linked | Irrelevant | Oracle | Full history |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 18 | 0/6 | 6/6 | 2/6 | 6/6 | 0/6 | 6/6 | 6/6 |
| 72 | 0/6 | 1/6 | 2/6 | 5/6 | 0/6 | 5/6 | 6/6 |

The linked failure in the larger tier is the client timeout. Its frozen prompt
contains complete proof, but its model answer is unknown and receives no
end-to-end success credit.

| Tier | Linked minus control | Mean delta | Descriptive bootstrap 95% interval | Both | Linked only | Control only | Neither |
|---:|---|---:|---|---:|---:|---:|---:|
| 18 | recency archive | 0.000 | [0.000, 0.000] | 6 | 0 | 0 | 0 |
| 18 | legacy top-4 | +0.667 | [0.333, 1.000] | 2 | 4 | 0 | 0 |
| 72 | recency archive | +0.667 | [0.333, 1.000] | 1 | 4 | 0 | 1 |
| 72 | legacy top-4 | +0.500 | [0.167, 0.833] | 2 | 3 | 0 | 1 |

Bootstrap: 10,000 deterministic resamples, seed 20260826, at case level. This
small templated cohort with post-hoc continuation does not support population
significance claims. Shared semantics across tiers are not independent repeats.

Complete proof exposure was linked 6/6 at each tier, top-4 2/6 at each tier,
and recency 6/6 versus 1/6. The treatment combines identifier navigation,
candidate filling, whole-record packing and recent-record exclusion. Its gain
is not isolated to graph traversal or established over general RAG.

## All tasks and abstention

| Condition | Strict success /24 | Answerable recovery /18 | Strict insufficient abstention /6 | Schema /24 |
|---|---:|---:|---:|---:|
| window-only | 12 | 6 | 6 | 24 |
| archive-recent | 16 | 13 | 3 | 23 |
| scratchpad-retrieve | 16 | 10 | 6 | 23 |
| linked-retrieve | 17 | 17 | 0 | 19 |
| irrelevant-notes | 12 | 6 | 6 | 24 |
| oracle-evidence | 22 | 17 | 5 | 23 |
| full-history | 18 | 18 | 0 | 21 |

Every condition passed all six recent-control cells. Linked recovered 17/18
answerable tasks, with the timeout its only failure. Its insufficient responses
reveal two different failure classes:

- Four returned null with source citations. The frozen contract requires null
  with an empty evidence list, so these stay strict schema failures. They
  express uncertainty and must not be called invented answers.
- Two returned a concrete base route although the hold flag was unconfirmed.
  Those are unsupported decisions. They reuse the same scoped-exception
  semantics at two tiers, not two independent demonstrations.

For example, `{"value": null, "evidence": ["m001", "m005", "m009"]}` is an
abstention-shaped format violation. `BASEPce3b2` in the unknown-hold case instead
acts on an unconfirmed condition as if it were disabled. The post-hoc diagnostic
does not revise either strict score.

Full history likewise failed all six insufficient cases. Its outputs include
null-with-citations and Japanese prose meaning "not yet decided" instead of
JSON null, as well as an unsupported route and an output-limit failure. More
evidence did not ensure correct abstention formatting or uncertainty handling.
The oracle's answerable failure had the correct value but omitted a required
exception-rule citation; its other failure was an output limit.

## Resource failures and cost

Three responses exhausted 4,096 output tokens, including 4,095 reasoning tokens,
and returned empty final text:

- small-tier delayed distributed join, legacy top-4
- large-tier insufficient scoped exception, oracle evidence
- large-tier insufficient scoped exception, full history

The additional linked timeout occurred on the large-tier interfering join.
All four remain failures. No failed response is regenerated or dropped.

| Condition | Received /24 | Known input | Known output | Mean received-call seconds | Mean archive chars |
|---|---:|---:|---:|---:|---:|
| window-only | 24 | 18,864 | 25,543 | 10.384 | 20.0 |
| archive-recent | 24 | 35,873 | 32,739 | 12.959 | 1,044.5 |
| scratchpad-retrieve | 24 | 23,002 | 36,490 | 13.440 | 260.2 |
| linked-retrieve | 23 | 31,253 | 37,027 | 14.742 | 861.9 |
| irrelevant-notes | 24 | 37,805 | 26,020 | 10.475 | 1,166.9 |
| oracle-evidence | 24 | 20,398 | 32,137 | 11.780 | 97.4 |
| full-history | 24 | 69,622 | 41,268 | 14.012 | 20.0 |

Full history uses the larger history field rather than extra archive memory.
Usage and latency above cover received responses only; the linked timeout is
not assigned zero cost or zero latency. Its configured timeout was 90 seconds.
No speed/cost advantage is established. Linked supplies more actual context
than top-4 despite their equal maximum allowance.

Pilot known usage: 236,817 input + 231,224 output = 468,041 tokens, including
227,465 reported reasoning tokens. Including both six-response calibrations,
campaign known usage is 240,206 input + 234,971 output = 475,177 tokens.
One timed-out request has unavailable usage; the two parameter rejections have
no usage receipt. These are known totals, not an exact bill.

The campaign made 182 inference HTTP attempts: 180 generation-intended requests
plus two parameter rejections. It has 179 received model responses across
calibration/pilot and one unreceived attempt. Neither continuation reissued a
received-response or timed-out slot; both consumed only originally unattempted
slots. The rejected parameter calls remain separate attempts in the ledger.

## Audit and receipts

All parent artifact hashes, imported prefixes, 168 unique cell identities,
prompt digests, received request parameters, model identifiers, raw-response
scores and known usage were re-audited. Summary generation reproduced identical
bytes twice. All received pilot model names were `mistral-large-4`. The full
168-cell matrix, including all failures, remains in the local plan/results.

Final directory: `.great_scratchpad/runs/mistral4-reinjection-tail-20261028/`.
It is ignored and not bundled in a fresh clone. Final pre-call commit:
`144398c4087a4939c110cf94d8a157c04149c877`. Final plan digest:
`a809601b18e57ad70b31f75e73aa0bdc51bf7d2f9511dc03814233dca23f5562`.

| File | Byte SHA-256 |
|---|---|
| plan.json | `bb27dae72fda616d372d611f3ebdf1eeb6c7681e634f137b41b3ae787ac795c1` |
| pilot/result.json | `c222121c75eaa6353679bcfe1fb21c7fa385dae0ada2e206397bab9a15d2fa61` |
| pilot/responses.jsonl | `bf198c4695dda904e33d9f66fe5f3ee432e1c5cec1ee760e20bc18e55cd8dd41` |
| summary.json | `48d6ea167a572e8f6425a45f9b26024bb05bffd08a9a039c3fae611f87c56801` |
| audit.json | `d686991ce9d134de836ff33fb4b83e20513f4327c425a68e83872a3623c042d4` |

Repository validation passed 154 tests, scoped Ruff, compilation and the
fake-model CLI smoke. No hosted CI success is claimed.

## Next boundary

Preserve every current score and receipt. The next target is grounded
uncertainty, before spending on more repeats of this exact retrieval grid:

1. Version an answer contract that distinguishes an unknown value from
   evidence explaining why it is unknown. Consider cited abstention there;
   do not retroactively pass the current null-with-citations responses.
2. Independently test unknown-versus-disabled flags, partial evidence,
   contradictory updates, verbal abstention and malformed JSON. Separate
   schema conformance from unsupported concrete claims.
3. Freeze client/output failures as outcomes from the start, with unavailable
   usage explicit. Calibrate partial-evidence abstention before an untouched
   confirmation cohort.
4. Use fresh semantics and natural-language/coined-name targets, then ablate
   candidate filling versus identifier traversal. Current evidence covers three
   synthetic families with machine-readable IDs and one model profile.
