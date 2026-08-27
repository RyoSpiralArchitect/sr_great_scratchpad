# Luna selective-recall mechanism plan

## Evidence boundary

This is a post-hoc mechanism analysis of the frozen n=8 delayed-recall cohort.
It does not alter or replace the preregistered full-recall versus
write-no-recall result. The source generation remains:

- run id: `dialogue-2026-08-26T171844-0700-5844ce2e`
- source commit: `4aaf4e4b90bd2de3086053b1308d79450e3a034c`
- model/profile: `gpt-5.6-luna` / `openai-5.6-luna`
- source corpus: 32 sessions, 384 utterances, and 58 notes

The new retrieval and relation measurements have their own assessment code and
taxonomy hashes in the generated JSON artifacts.

## Offline retrieval result

The taxonomy freezes dialogue turn 3 as the exact source-note turn. Runtime
lexical scoring is then replayed over the target speaker's three-note thread.
A separate stress scope adds the 24 highest-scoring non-target notes from other
sessions; that scope is not the current isolated runtime topology.

| Query | Scope | R@1 | R@2 | R@3 | MRR | Mean chars@1 | Mean chars@2 |
|---|---|---:|---:|---:|---:|---:|---:|
| probe intervention only | own thread | 12/16 | 16/16 | 16/16 | 0.875 | 204.3 | 402.0 |
| full current message | own thread | 5/16 | 9/16 | 16/16 | 0.583 | 199.6 | 395.9 |
| probe intervention only | 24-note stress | 1/16 | 5/16 | 7/16 | 0.279 | 223.9 | 430.4 |
| full current message | 24-note stress | 0/16 | 1/16 | 2/16 | 0.130 | 226.4 | 453.3 |

The peer utterance before the moderator probe adds query drift. Agenda or
opening text also reduced own-thread top-1 accuracy in an exploratory query
sweep, so the next run uses the frozen intervention alone. Top-2 is the first
cutoff with complete exact-source coverage in the actual per-speaker candidate
scope.

Full recall exposed three complete recent notes at turn 11: 1,594.4 characters
on average and 12,755 characters across eight sessions. Compact top-2 would
have exposed about 402 characters per probe. This is a character-level
projection, not a provider-token estimate.

The cross-thread stress failure means thread isolation remains a retrieval
safety boundary. Do not promote this lexical ranker to a shared or global note
pool without a stronger ranker and a separately frozen benchmark.

## Relation-aware rescore

The original literal probes could pass when old and new level terms appeared
without the requested role assignment. The new taxonomy-level relation probe
requires:

- an old species-level term near `変更前` or `補正前`
- a new within-individual term near `変更後` or `補正後`
- old-before-new ordering
- one explicit analogy-boundary expression
- no complete reversal of the old and new roles

Applied post hoc to the frozen n=8 turn-11 responses, the strict relation probe
passed `5/8` full-recall sessions and `1/8` write-no-recall sessions. The paired
table contains five full-only, one write-only, and two neither outcomes. This is
an auditable secondary assessment, not a replacement primary endpoint.

## Next live calibration

The `mechanism` preset runs four conditions:

1. `write-no-recall`
2. `probe-top1`
3. `probe-top2`
4. `scratchpad-scratchpad`

Both probe conditions keep all model-requested read actions blocked. They use
the moderator intervention as the retrieval query and inject compact lexical
hits only at turn 11. Trace events freeze the query, top-k, source paths,
scores, source characters, and injected characters.

Run one replicate before any increased-n spend:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_delayed_recall_ablation.json \
  --profile openai-5.6-luna \
  --preset mechanism \
  --turns 12 \
  --history-chars 700 \
  --replicates 1 \
  --turn-output-tokens 600 \
  --max-api-calls 144 \
  --max-suite-output-tokens 48000 \
  --out-dir .great_scratchpad/runs/luna-selective-recall-cal1
```

Before behavioral interpretation, require all sessions to complete, exactly one
selective injection in each probe condition, zero selective injections at all
other turns, no read actions, and source rank within the requested cutoff.
Compare top-1 and top-2 response efficacy, relation compliance, and provider
tokens against both no-recall and full-recall controls.

The notes are still generated independently by condition. Treat note-content
matching as a manipulation check and do not claim a pure retrieval-cutoff effect
until a later frozen-note replay design removes that remaining variance.
