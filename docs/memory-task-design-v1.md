# Memory-sensitive task design v1

Date: 2026-10-26. **Offline design only; no model calls for these tasks.**
We want to find where external memory helps, fails, or harms under a bounded
context budget, not pick cases that make a treatment look good.

## Motivation and scope

The earlier grounded-record probe was short and templated; original records,
prose and role labels all reached the ceiling. Making those records longer
without changing the reasoning requirement would not answer the next question.

LongMemEval separates extraction, multi-session reasoning, updates, temporal
reasoning and abstention. We borrow those *axes*, not its datasets, scoring,
or reported results. [LongMemEval paper](https://arxiv.org/abs/2410.10813)
RULER motivates going beyond a single hidden fact to multi-hop tracing and
aggregation. Our dependency-chain task is an independent small mechanism probe,
not a RULER reproduction. [RULER paper](https://arxiv.org/abs/2404.06654)

The hypothesis is conditional: external memory may help when a decision needs
information outside a fixed recent window, provided the relevant records can
be retrieved and interpreted. It may add no value when the answer is recent,
and should not create certainty when information is missing. This does **not**
assume a scratchpad should beat a full-history model or an equally resourced
retrieval baseline.

## Task families

All facts describe synthetic project decisions, not real operational advice.
IDs and values are generated deterministically from declared seeds, family and
regime, so the answer cannot be supplied from world knowledge. The construction
is still templated; passing it would not establish natural-dialogue generality.

| Family | Question | Memory-dependent reasoning | Failure to detect |
|---|---|---|---|
| Decision update | Which compression choice is currently approved for this project? | Earlier approved choice, approved replacement, then a later unapproved proposal | Treating the newest mention or another project's decision as current approval |
| Scoped exception | Where should this request be routed? | Join request flags to its group's base policy and higher-priority hold exception | Using another group's policy, dropping the exception, or treating an unknown flag as false |
| Distributed join | What final execution pool handles this request? | Request to team, team to processing line, line to pool in three records | Matching only the first link or borrowing another request's endpoint |

The generator emits public source text and a separate typed event ledger.
`solve_case` computes the declared answer and proof records from the ledger.
The ledger and answer are never indexed or included in a non-oracle prompt.
Policy precedence and missing-link behavior have independent negative tests.
This reference oracle describes our authored world; it is not a free-text
semantic parser or an independent human validation of realistic conversation.

## Difficulty and negative controls

Every family appears in all four regimes; none can be dropped from a cohort:

1. **Recent:** all necessary evidence fits in the common 700-character recent
   window. This is a ceiling/control case where a scratchpad need not improve.
2. **Delayed:** the necessary records are distributed through an old prefix;
   18 mostly unrelated records push them outside the recent window. This tests
   recoverable retention, not inability to solve a task with all information.
3. **Interference:** the same number of distractors now mention similar request
   names, choices, routes or endpoints. Some explicitly mention the target while
   denying applicability. This tests selection and scope, and may harm a lexical
   retriever. No record is removed because it causes a retrieval failure.
4. **Insufficient:** an approval, hold flag, or final link is actually missing.
   Full history still cannot establish the answer. Correct behavior is to abstain.

`recent` and delayed/answerable exposure are checked mechanically. Full-history
and oracle-evidence prompts must contain the required proof. These checks prove
prompt construction, **not measured model difficulty**. All four regimes share
templates; delayed versus interference is not an exactly length-matched causal
experiment. Record counts are matched; character/token lengths are reported.

## Conditions

All conditions except the full-history reference share the same recent window,
query, system instruction and centerline hints. Hints only see that exact
window. The memory field alone changes. Additional memory has a 1,200-character
cap and whole records are packed without cutting supporting sentences.

| Condition | Memory and purpose |
|---|---|
| window-only | No archive. Diagnostic of what the recent context alone permits |
| archive-recent | Recent older raw records, newest first, under the same extra-memory cap; primary active control |
| scratchpad-retrieve | Existing `memory.retrieve`, current query, top 4, same extra-memory cap; query-relevant archive access |
| irrelevant-notes | Unrelated records under the same cap; detects harm or false certainty from extra memory |
| oracle-evidence | Gold proof records, explicitly privileged; diagnoses reader limits, never a deployable treatment |
| full-history | All original records in history, more input; information-rich cost/quality reference, not budget-matched |

Memory construction is deliberately **query-blind verbatim storage** using the
repo's note format. Every original record is stored before retrieval; there are
no author-selected answer notes, synthetic role annotations, query-aware writes
or hidden truth fields. The existing lexical ranker is used without an oracle
filter. It searches all notes, including ones already present in recent history;
any resulting wasted retrieval is retained. One retrieval query is allowed in
this design; an adaptive multi-query reader would be a separate treatment with
its own call budget.

This first design measures the **archive/retrieval read path**, not the quality
of autonomous note-writing, semantic compression, or a special advantage over
ordinary RAG. Scratchpad retrieval here *is* raw-note retrieval. To test a learned
scratchpad writer later, add a separately frozen query-blind writer with the
same storage budget, then compare its output against this raw-retrieval baseline
and include write/inference costs. Do not pass gold proof labels to that writer.

Equal character caps are **not** equal actual input tokens. Selected note counts,
context characters and evidence visibility are retained; actual provider token
usage/cost and latency must be reported when a live reader is added. Padding
irrelevant text to pretend exact equality is not part of this design.

## Endpoints and comparisons

The future answer shape is `{"value": "recorded value or null", "evidence": []}`;
an unavailable answer is exactly `{"value": null, "evidence": []}`. This is a
different task contract from the four-field v2.1 calibration. It needs its own
live format calibration before a task pilot.

Offline `assess_task_answer` separates:

- Strict schema validity, including duplicate-key and extra-field rejection.
- Exact answer correctness against the authored reference semantics.
- Complete proof coverage and visibility of every cited source ID.
- Grounded task success: correct answer plus visible complete proof.
- Safe abstention, regardless of whether answerable evidence was recoverable.
- Recovered answer: grounded success on an answerable task only. Correct
  abstention on an insufficient task is never credited as recovered memory.

Primary estimand: paired **scratchpad-retrieve minus archive-recent** grounded
success on answerable delayed/interference cases, per provider. This tests query
selection at the same additional-memory cap. Paired scratchpad minus window-only
is secondary: it restores withheld information and cannot by itself demonstrate
a special scratchpad design advantage. Full-history and oracle conditions are
diagnostic references, not targets the treatment must beat.

Report all family/regime/condition cells, including zeros, ties, schema failures
and unanswerable false assertions. Separate retrieval support coverage from
reader success; failure after complete evidence exposure is not a retrieval
failure. Abstention penalties on answerable tasks must not be relabeled as
hallucinations. Do not pool repeated arms as independent samples.

## Frozen selection and future execution

The spec declares 12 pilot tasks (3 families x 4 regimes x 1 seed) and 24
confirmation tasks (the same grid x 2 different seeds). Case IDs/values are
disjoint. The pilot's six answerable delayed/interference cases are small;
confirmation has 12 such paired cases per provider, still insufficient for broad
capability claims. Repeated template families limit independence/generalization.

No API responses or treatment gains have been observed for these tasks. Do not
select a "sweet spot" by maximizing observed scratchpad gain, drop difficult
families, widen the window for one arm, hide retrieval failures, tune the ranker
on confirmation answers, or turn an oracle-assisted result into a real-system
score. A bug that invalidates construction can be repaired only with a new
design identity, retaining the old artifacts. Evidence-based system changes
after a pilot need a fresh protocol and untouched evaluation cohort.

Before any future live task run, freeze models, sampling, exact prompts/order,
the task-format gate and call/input/output budgets. Validate all cells as built;
do not require a positive treatment effect to publish the completed pilot.
Both a null result and a negative effect remain useful outcomes. Report paired
differences and uncertainty for the predeclared primary comparison, treating
cases (not model calls) as sampling units; avoid significance claims from this
small synthetic grid. Distinguish negative-control safety from recovery.

At two providers, a complete pilot with six arms would require 144 response
calls; confirmation would require 288 more. These are **design counts, not an
authorization or an execution budget**. No task-provider runner is added here.
The current tool has `live_calls_authorized: 0` and always reports `NOT_MEASURED`.

## Reproduce the offline pack

```bash
python3 -S sr_great_scratchpad.py experiment memory-task-design \
  --spec scenarios/memory_task_design_v1.json \
  --out-dir .great_scratchpad/runs/memory-task-design-v1-20261026
```

`design.json` contains the specification, 36 public-record/assessment cases,
216 condition prompts, per-prompt exposure/ranking diagnostics, source/runtime
hashes and an overall digest. Provider-facing prompts exclude the assessment
ledger. The raw JSON bundle is a local ignored artifact, not bundled in a fresh
clone; the spec and generator reproduce it. Its live model difficulty, reader
accuracy, agentic writing quality and treatment effects are **not measured**.

## Frozen offline audit

Design digest: `f61cc831af58f35fd5a7ae3cd0712ca4fc7692f721015b19b445e0d09b2d575a`.
File SHA-256: `a4179ae7216d146268f94e50ef3601e0f85ce1841397f277051da7c8827415af`.
Spec file SHA-256: `698047bf674849c935123bc52f275d6f4ae6b4c2381fb0bad17200d4b4f175ea`.
All 36 construction checks passed. No source/query/model selection was changed
after inspecting the following pilot-only exposure diagnostics.

| Answerable old-evidence pilot tasks | window-only | archive-recent | scratchpad-retrieve | oracle/full-history |
|---|---:|---:|---:|---:|
| Decision update: delayed/interference | 0/2 | 2/2 | 1/2 | 2/2 |
| Scoped exception: delayed/interference | 0/2 | 2/2 | 1/2 | 2/2 |
| Distributed join: delayed/interference | 0/2 | 2/2 | 0/2 | 2/2 |
| Total complete proof visible | 0/6 | 6/6 | 2/6 | 6/6 |

These are **not answer-accuracy results**. In this small archive, the recency
buffer can fit all of the old prefix within the 1,200-character cap, so this
design does not yet impose information compression on that active control.
The fixed top-4 ranker retrieves fewer characters; it loses every interference
case and misses the middle link in the delayed chain. We retain these losses,
not just the two tasks where retrieval exposes the complete proof. They locate
selection/integration risks before spending money on a reader.

A future archive-pressure sweep should retain this fits-in-budget tier alongside
predeclared larger histories (for example, fixed record-count tiers), without
choosing the length that maximizes a model's observed treatment gain. Likewise,
a multi-query retriever must be a new treatment, not an unlogged repair of these
rows. Neither change is included in this frozen artifact. The present result
does not predict a scratchpad advantage and does not justify a live task cohort
until its separate format/budget protocol is reviewed.
