# Grounded record recall v2

Protocol date: 2026-10-26. Freeze this protocol, fixture, implementation and
all prompts before any provider calls. Record host timestamps as emitted;
the protocol date is the client/session date, not an assertion about host time.

## Question and scope

Can a model distinguish a rejected comparison, an accepted comparison unit,
an analogy boundary, and evidence of **earlier adoption of the rejected unit**?
The old marker-order endpoint could reward a fluent but unsupported history.
This is an additive, structured record-grounding diagnostic. It does not repair,
rescore, or replace the historical fixed-probe or full-dialogue results.

The six new Japanese cases are authored synthetic records, not new generated
conversations, real scientific facts, or samples from a population. Topics differ
but share a sentence template. Two cases are calibration (board, room); four
are confirmation (station, library, service, tile). In each stage, half contain
an explicit earlier adoption record and half leave earlier adoption unestablished.
`n=4` means four distinct confirmation cases **per model/condition**, not four
repetitions, four cases per historical-status stratum, or statistical validation.

Post-calibration clarification (no gate/input change): the distinct-input claim
applies to source-visible conditions. `none` removes all case-specific text,
so its requests are repeated draws of an identical prompt. Case labels in the
local manifest must not be mistaken for distinct no-source provider inputs.
See the [result and failed gate](grounded-recall-v2-results.md).

## Ground truth and assessor

- `rejected_alternative`: the option explicitly rejected by the correction.
- `accepted_unit`: the comparison unit explicitly selected by that correction.
- `comparison_boundary`: the stated limited scope, not a general equivalence.
- `prior_adoption`: `established`, `not_established`, or `refuted`. Rejection
  now alone proves neither adoption nor non-adoption earlier. `refuted` requires
  explicit evidence; it is tested offline but is not a live fixture stratum.

The answer has exactly four fields; extra prose, duplicate JSON keys and tool
actions fail. Role values must equal a predeclared value/alias after the repo's
NFKC/case/punctuation normalization. Each non-null role must cite a visible
source ID and an exact original substring containing its **whole supporting
sentence**, including the role/limitation/negation. A bare quoted value is not
enough. Historical support must come from before the correction, not from the
correction itself. Unestablished history has no supporting affirmative citation.

This is a closed-alias, typed-claim/evidence contract, **not a general semantic
judge**. A valid but undeclared paraphrase fails with `undeclared_value`; that
does not prove factual error. No live outputs may be used to extend this run's
aliases, adjust the gate, change cases, or repair responses. Truth annotations
and allowed quote spans are author-declared, not independently human-validated.

Offline checks cover declared paraphrases, role reversal, negation, unsupported
history, absent records, incorrect/missing sources, incomplete quotes, malformed
JSON and additional unscored prose. These are contract tests, not a held-out
natural-language classifier benchmark. Unit tests also exercise explicit
non-adoption and runner/provenance failure paths. All must pass before live use.

## Conditions and identity

For each case and provider, compare:

| Condition | Visible context |
|---|---|
| none | No source records; negative control |
| original | Both original records, byte-identical across visible conditions |
| prose | Original records plus a source-derived prose summary |
| roles | Original records plus the same propositions as named role fields |

This isolates presentation **given complete record exposure**. No retrieval
ranking or top-k treatment is involved. Summaries expose authored supervision;
they do not test an automatic summarizer. Source visibility, answer schema,
value matching and citation support are separate diagnostics. Memory length is
recorded, not equalized. Role labels overlap the requested answer schema, which
can favor the roles condition without implying general conversational benefit.

All conditions use the corrected shared `render_dialogue_context` and
`build_chat_prompt(history_context=...)` path. Centerline hints see only that
same bounded transcript plus the current question. The generic query does not
presuppose earlier adoption. No case/condition label is present in the thread
header. System prompt and prompt bytes outside memory are identical. Order is
deterministic: rotate conditions by case and alternate provider order within
cells. Confirmation has one complete rotation; calibration is only a partial
rotation. No seed/repeated-sampling or provider-time stationarity claim is made.

## Preregistered gates and budget

1. Pass offline checks and all repository tests. Prepare all 48 prompts, exact
   effective profiles, code hashes and assessment snapshot in `plan.json`.
   Preparation makes no API call and does not require reading credential values.
2. Freeze/commit the protocol and plan identity before calibration. Use existing
   `openai-5.6-luna` (`gpt-5.6-luna`) and `mistral-large`
   (`mistral-large-latest`) profiles, without model substitution.
3. Calibration: 2 cases x 4 conditions x 2 providers = **16 calls**.
   A source-visible response passes only when all three values and citations,
   and the historical status/evidence, are correct under the frozen contract.
   A no-source response passes only with three null roles and unestablished
   history with empty evidence. Abstention is safety, **not recovered memory**.
4. Confirmation: proceed only if **all 16 calibration responses pass**. Before
   any additional call, recompute the gate from complete raw receipts, exact
   ordered cell/prompt identities, code/config hashes and saved assessments.
   Then run 4 new cases x 4 conditions x 2 providers = **32 calls**. Report the
   same endpoint, per-component failures, safety and recovery separately.

The total ceiling is **48 calls and 48,000 output tokens** (1,000 per call,
including reasoning tokens where charged as output). Input is additional;
the plan records a conservative character/word estimate, not a provider token
count or a dollar estimate. The experiment explicitly replaces old profile
token limits (900/400) with 1,000 in memory only. Stored configuration and keys
are not changed. Profiles' other supported sampling parameters are frozen.

Calls use existing environment credentials. No secret enters the plan or
request text. No retries, model fallback, JSON repair, tools, continuation or
automatic alias changes are allowed. Every attempted call is recorded before
network access, raw output before assessment. Transport/interruption failures
stop the stage; unsuccessful assessments finish the declared calibration cohort
but block confirmation. A pre-existing stage directory always blocks rerun,
including an incomplete/error directory. No implicit resume or overwrite.
The budget/rerun guard applies to this plan directory, not a global quota across
arbitrarily copied plans. Hashes detect drift; they are not signed provenance
against an actor who can rewrite every receipt and its digest.

## Commands

```bash
python3 -S -m unittest discover -s tests
python3 -S sr_great_scratchpad.py experiment grounded-prepare \
  --cases scenarios/grounded_recall_v2_cases.json \
  --profiles openai-5.6-luna,mistral-large \
  --out-dir .great_scratchpad/runs/grounded-recall-v2-20261026
# Freeze the printed digest and commit before provider execution.
python3 -S sr_great_scratchpad.py experiment grounded-run \
  --plan-dir .great_scratchpad/runs/grounded-recall-v2-20261026 \
  --plan-sha256 FROZEN_DIGEST --stage calibration
# Only if the frozen calibration gate passes:
python3 -S sr_great_scratchpad.py experiment grounded-run \
  --plan-dir .great_scratchpad/runs/grounded-recall-v2-20261026 \
  --plan-sha256 FROZEN_DIGEST --stage confirmation
```

Provider artifacts are local ignored files. A committed result document should
record the plan hash, pre-call commit, actual models, attempts/usage, raw receipt
hashes and failures. Local evidence is not available from a fresh clone unless
explicitly published. Passing this narrow probe cannot establish full-dialogue
memory efficacy, a role-label advantage, robust semantic understanding, or
production readiness. Keep automatic augmentation disabled.

## Frozen local plan

Prepared before provider execution on 2026-10-26:

- Canonical plan digest: `f12e13f85d07d8323e551a6f113c1d2690885a77385068084382deb1eb039ea8`.
- Serialized `plan.json` file SHA-256: `de122b44ac96e4e6d12cc53d46087cf67a6eda1b2b39317624d470fb390392dd`.
- Case fixture file SHA-256: `6102b687feca5efa601effb467740313a05cf7e8126322f05586fa83e516ead9`.
- Offline checks: 192/192; repository suite: 98 passing tests; scoped Ruff,
  compilation, whitespace checks and fake-model CLI smoke passed.
- Input estimate for all 48 planned calls: 33,082 tokens. Actual provider token
  accounting, including any reasoning, is recorded separately after execution.
- The 1,396 pre-existing local run files were hashed before execution. The
  aggregate of path-sorted `shasum -a 256` lines is
  `211c411d279b5b55352b1b6630332e1a76a69b16589fe93e4e3cc0b44d1a792b`.

The plan includes every module hash, effective profile and prompt. Rebuilding it
from a different runtime intentionally changes its identity. This document's
freeze is not a claim that either live stage has passed.
