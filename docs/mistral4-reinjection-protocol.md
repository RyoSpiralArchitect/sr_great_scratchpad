# Mistral Large 4 reinjection pilot v1

Historical initial protocol: calibration finished 5/6 and its pilot stayed
blocked. Subsequent high-reasoning attempts and exploratory continuations are
reported in [the full result](mistral4-reinjection-results.md).

Frozen on 2026-10-28 before generation. This is a new read-path pilot using
fresh synthetic decisions, scoped exceptions and distributed joins. Historical
Luna and Mistral runs, assessors, and offline task-design v1 remain intact.

## Change and hypothesis

The legacy reader asks the lexical ranker for four notes. That can omit a
middle link and underfill its memory budget. The opt-in linked reader first
matches public mixed letter/digit identifiers, favors the first identifier in
a record over incidental mentions, then follows identifiers from retrieved
records through at most two expansion hops, with four candidates per hop.
It considers at most sixteen unique notes and backfills with remaining lexical
matches. Citation labels are excluded from entity extraction.

Identifiers are navigation hints, not evidence of approval or applicability.
Negated claims, proposals and distractors remain original source text for the
reader to interpret. No answer labels or typed reference events enter ranking.
The ranker searches one thread and makes zero provider calls. Whole records
are packed up to the same 1,200-character archive cap, skipping oversize
records and already visible recent records in the benchmark wrapper. Public
source IDs remain intact. Normal chat uses the current query without the
benchmark's history-aware exclusion.

The experiment compares this package of changes; it does not isolate the effect
of graph traversal from budget filling or recent-record deduplication.

The normal chat runtime exposes the same ranker through `--recall-policy linked`.
Chat packs complete raw/annotation fields with file provenance, including local
assumptions, under `--recall-chars`. It skips notes that cannot fit whole.
The synthetic pilot uses verbatim source records as payload, so its numeric
results apply to that read path, not to autonomous note-writing or long chats.

## Frozen matrix

- Explicit model: `mistral-large-4`; accept returned `mistral-large-4` or its
  listed `mistral-large-4-0` alias, with no fallback to `latest`.
- Sampling: temperature 0, random seed 261028, reasoning effort `none`, JSON
  mode, output limit 600 tokens, one request per cell, no retries or repairs.
- Seeds: calibration 26102800, pilot 26102801.
- Three families, four regimes, and two pressure tiers (18 and 72 distractors).
- The same task semantics are reused across tiers. Treat the tiers as repeated
  pressure measurements, not independent replications.
- Common ordinary history: newest 700 characters; common query, instruction,
  and hints outside the memory field, except the full-history reference.
- Seven arms: window-only, archive-recent, legacy scratchpad-retrieve,
  linked-retrieve, irrelevant-notes, oracle-evidence, full-history.
- All 24 cases and 168 arm responses stay in the cohort, including negatives.
  Condition order rotates deterministically by case.

Full history is an information-rich reference. Oracle evidence is privileged.
Archive-recent is the primary active control at the same character cap. Actual
input token counts differ and must be reported. No padding or gold filtering
is used to equalize input usage.

## Gate, budgets and evidence

Six fresh calibration responses cover the three families with source-visible
and source-absent prompts. All must satisfy the existing strict two-field
answer contract and complete grounding or explicit abstention. Re-audit raw
receipts before the pilot. A failed gate stops the campaign.

The complete campaign has at most 174 generation calls and 104,400 requested
output tokens. The frozen prompts contain 800,587 UTF-8 bytes before HTTP
framing and an estimated 208,343 input tokens; preparation rejects a payload
above 2,000,000 input UTF-8 bytes. The byte cap is a payload bound, not a
provider-token or billing guarantee. Record actual usage and latency separately.

`reinjection-prepare` freezes every prompt, runtime hash, profile, source commit,
budget and construction check before the first call. Execution refuses drift,
existing stage directories, incomplete gates and model substitution. Transport
errors preserve partial results and stop; they are not retried in place.
Reassessment must reproduce all saved scores and usage from raw receipts.

## Endpoints

Use the unchanged `assess_task_answer` exact value plus visible proof contract.
Keep schema validity, complete evidence exposure, reader success, recovery and
safe abstention separate. Insufficient cases count as safety, not recovery.

Primary: paired linked-minus-archive-recent grounded success on the six
answerable delayed/interference cases in each tier. Secondary: linked versus
legacy top-4 under the same cap. Publish every cell, discordant pairs, mean
delta and a deterministic bootstrap interval at case level. Bootstrap intervals
in this tiny templated pilot are descriptive; no population significance claim.

Do not tune on pilot answers and then call the same cohort confirmation. A
subsequent independent cohort needs a new frozen protocol and fresh seeds.

## Offline exposure preflight

These counts describe supplied evidence, not measured answer accuracy:

| Distractors | Legacy top-4 | Linked | Archive-recent | Oracle/full-history |
|---:|---:|---:|---:|---:|
| 18 | 2/6 | 6/6 | 6/6 | 6/6 |
| 72 | 2/6 | 6/6 | 1/6 | 6/6 |

## Run

```bash
python3 -S sr_great_scratchpad.py experiment reinjection-prepare \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-20261028

python3 -S sr_great_scratchpad.py experiment reinjection-run \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-20261028 \
  --plan-sha256 PLAN_DIGEST --stage calibration

python3 -S sr_great_scratchpad.py experiment reinjection-run \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-20261028 \
  --plan-sha256 PLAN_DIGEST --stage pilot

python3 -S sr_great_scratchpad.py experiment reinjection-report \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-20261028 \
  --plan-sha256 PLAN_DIGEST
```

Credentials come only from `MISTRAL_API_KEY`. The checked-in profile contains
the environment-variable name. Provider model catalog and API details were
verified against [the model card](https://docs.mistral.ai/models/mistral-large-4)
and [Chat Completion API](https://docs.mistral.ai/api/endpoint/chat).
