# Fixed-probe relation calibration

Review follow-up: [PR 7 review resolution](pr7-review-resolution.md) corrects
history-window isolation and visibility analysis. The results below remain
frozen observations under their recorded runner, not a rerun of the fixes.

## Protocol frozen before live calls

This follows the frozen-note calibration in `luna-selective-recall-mechanism.md`.
That run exposed the correction note in top-2/full but passed the strict relation
endpoint in none of its four cells. This motivates a representation hypothesis;
it does not establish a representation bottleneck causally.

There is also an important qualification to the endpoint: the opening does not
assert species-level diversity. The turn-3 correction rejects species-level
diversity and specifies within-individual heterogeneity. A rejected interpretation
is not evidence that the dialogue previously adopted it. The new annotation
therefore marks `before_status=rejected_interpretation` and
`prior_adoption=unverified`. The old marker-based endpoint is retained unchanged,
not promoted to a test of truthful historical reconstruction.

### Frozen input and treatment

- Source: `luna-frozen-replay-cal1/replay-no-recall-r01`, first and only model
  request at turn 11. Earlier turns are not regenerated.
- Keep the provider system prompt, ordinary history, centerline hints, current
  message, and observations byte-identical across every cell. Replace only the
  thread identifier with the common neutral `frozen-probe`.
- Three renderings: `original`, `prose`, and `roles`. Prose and roles carry the
  same sourced propositions and the same historical-uncertainty qualification.
  Their wording, token count, and layout are not identical.
- Four visibility modes: `none`, `top1`, `top2`, `full-at-probe`. This last mode
  means full notes at this probe, not recall throughout a new dialogue.
- The three original Markdown notes stay byte-identical. A separate, manually
  authored sidecar is bound to the fixture/scenario/note hashes and source quotes.
  Its fields cannot cite future notes or evaluation answers. Quote containment
  validates traceability, not the semantic truth of the annotation.
- Rank original Markdown first, then render only selected notes. The source note
  remains rank 2. The `none` and `top1` prompts are identical across renderings;
  their three outputs are repeated samples, not representation effects.
- Existing 700-character compact / 1,600-character full per-note ceilings remain.
  Added relations must fit without truncation. The original rendering is still
  the default; no normal chat or annotation behavior changes.

| Visibility | Original context chars | Prose | Roles |
|---|---:|---:|---:|
| none (placeholder) | 17 | 17 | 17 |
| top1 | 297 | 297 | 297 |
| top2 | 558 | 764 | 735 |
| full-at-probe | 1707 | 1914 | 1885 |

The extra content is an intentional intervention. A difference from original
cannot establish that labels alone help. Only the prose/roles contrast tests the
additional role-labelled layout, and even that contrast is not length-matched.

### Budget and assessment

One response per cell, 12 calls per profile, no retries or tool execution, at most
400 output tokens per call and 4,800 per profile. Run the existing
`openai-5.6-luna` profile and `mistral-large-latest`, preserving the requested and
returned model names and sampling settings. Comparisons are within provider;
this Luna-generated dialogue is not a neutral cross-model leaderboard.

All 12 prompts are frozen before any call. Preserve raw output and usage before
parsing. Any provider/protocol error stops that profile and leaves unrun cells
explicitly unrun. Do not repair, silently substitute models, or overwrite runs.

Primary diagnostic: the unchanged strict before/after/boundary endpoint. Also
report both literal probes, reply length compliance, raw answers, and token cost.
Read every answer for unsupported historical claims and endpoint false negatives;
do not adjust the scorer after seeing outputs. No new TF-IDF score is compared
numerically with older fitted cohorts. This n=1/single-probe exercise is a
manipulation check, not replication, significance, or a general efficacy claim.

### Reproduction

The source run is a required local artifact; this command does not regenerate it.
It resolves files relative to the supplied directory, so relocated runs work.

```bash
python3 -S sr_great_scratchpad.py experiment relation-replay \
  .great_scratchpad/runs/luna-frozen-replay-cal1 \
  --fixture scenarios/luna_delayed_recall_frozen_notes.json \
  --relations scenarios/luna_delayed_recall_relations.json \
  --profile openai-5.6-luna \
  --out-dir .great_scratchpad/runs/luna-relation-replay-cal1 \
  --dry-run
```

Use a new output directory and omit `--dry-run` for a paid run. Configure Mistral
with an environment-variable reference, never a persisted secret:

```bash
python3 -S sr_great_scratchpad.py llm-config provider \
  --profile mistral-large --base-url https://api.mistral.ai/v1 \
  --api-key-env MISTRAL_API_KEY --model mistral-large-latest \
  --json-mode json_object --max-tokens 400
```

Then use `--profile mistral-large` with the same inputs and a fresh output
directory. API shape follows the [official Mistral API documentation](https://docs.mistral.ai/api).

### Preflight identities

- Fixture: `c5c72e87815b843d5619aa2e25c2fe1908011c0a1f85227adb0c510b697b125f`
- Relations: `4a35a1b726ea5d9a5c15c9c401bcd9fe3fe042b899c1ff6a93eaf63e8e72bf57`
- Assessment: `1ffa05b9335add09843d7feabdf05aee41c5ce38713a3db5c3df989165773327`
- Shared system: `3726a1f6a5b87d25c2caa57a329c8eab7b3a957617104ffaa431f680792a450f`
- Shared prompt outside memory: `e11f8e6431727fa19102ea979b2846c9f52ee7a0f7ac17b88fd2e5c9a1859838`

Each run stores `plan.json`, `result.json`, `responses.jsonl`, and `report.md`.
The plan includes source-note text, source request, annotation evidence, frozen
assessment, rank receipts, selected-note hashes, and every provider-visible prompt.

## Calibration 1 results: 2026-09-27

Implementation and protocol were committed as
`1adcca2c406db46568c150c7cac4546e27640627` before either live run. Both profiles
completed 12/12 cells, with no retries, parse failures, or tool calls. All 24
replies fit the frozen 180-character limit. Their complete `plan.json` files are
byte-identical across providers. An independent post-run check matched all
responses to result messages, plan hashes, and runtime component hashes.

| Model | Visibility | Rendering | Literal | Strict relation |
|---|---|---|---:|---:|
| Luna | top2 | original | 1/2 | 0/1 |
| Luna | top2 | prose | 2/2 | 1/1 |
| Luna | top2 | roles | 2/2 | 1/1 |
| Luna | full-at-probe | original | 1/2 | 0/1 |
| Luna | full-at-probe | prose | 2/2 | 1/1 |
| Luna | full-at-probe | roles | 2/2 | 1/1 |
| Mistral | top2 | original | 2/2 | 0/1 |
| Mistral | top2 | prose | 2/2 | 0/1 |
| Mistral | top2 | roles | 2/2 | 0/1 |
| Mistral | full-at-probe | original | 2/2 | 0/1 |
| Mistral | full-at-probe | prose | 2/2 | 0/1 |
| Mistral | full-at-probe | roles | 2/2 | 0/1 |

Every no-target call (`none` and `top1`, three repeated samples each) failed the
strict relation endpoint for both models. Aggregate literal matches were Luna
`none=2/6`, `top1=2/6`; Mistral `none=2/6`, `top1=3/6`. These are six term checks
on three repeated identical prompts per visibility, not six independent trials.

### Interpretation and limitations

1. Luna's source-visible prose and roles both passed where original did not.
   This supports testing explicit correction relations further in this cell;
   it does not show a label-specific advantage over prose, or general efficacy.
2. Mistral recovered both level terms in all six source-visible responses,
   including the original control. Manual reading finds the intended species-to-
   within-individual direction, but the frozen scorer recognizes only the exact
   Japanese markers `変更前`/`補正前` and `変更後`/`補正後`. Mistral instead used
   `当初`, `現在`, `修正後`, or a `から...へ` construction. All six have boundary
   matches but empty before/after marker matches. Keep their original `0/1` scores;
   do not interpret this as model incapacity, or retroactively broaden the metric.
3. The uncertainty qualification did not survive in any of the eight
   source-visible augmented answers (two providers, two visibility modes, two
   augmented renderings). All describe species-level comparison as historical.
   Inspection of turns 1-2 in both the donor and source replay confirms that
   neither establishes that prior adoption. The strict endpoint can therefore
   reward an unsupported temporal claim. A pass is not truthful memory recovery.
4. Literal matching also misses paraphrases: Luna's no-memory prose sample uses
   `クラゲ内部` rather than one of the frozen within-individual terms. Neither
   lexical endpoint is a complete semantic or factual evaluator. Biological and
   cultural claims in generated answers have not been fact-checked here.

The next gate is an **offline assessment/ground-truth correction**, before n=4:
separate the rejected alternative, accepted comparison unit, analogy boundary,
and whether prior adoption is actually evidenced. Build independent positive,
paraphrase, reversed-role, negation, and unsupported-history cases; keep these
calibration answers as diagnostic examples, not a new held-out test. A future
protocol should ask what was rejected/accepted without presupposing a historical
change. Do not enable the augmented representation by default or claim the
bottleneck is solved on these results.

### Cost and receipts

| Profile | Requested / returned model | Prompt tokens | Completion tokens | Total |
|---|---|---:|---:|---:|
| openai-5.6-luna | gpt-5.6-luna / gpt-5.6-luna | 23301 | 2605 | 25906 |
| mistral-large | mistral-large-latest / mistral-large-latest | 24347 | 1362 | 25709 |

Total: 24 calls, 47,648 prompt tokens, 3,967 completion tokens, 51,615 total
tokens. Counts are provider-reported, not estimates. Luna used its existing low-
reasoning profile; Mistral used temperature 0.2. The returned Mistral name is still
an alias, not a resolved immutable model version. Credentials were loaded from
the environment and are absent from the saved configuration and artifacts.

Local artifacts live in `.great_scratchpad/runs/` under
`luna-relation-replay-20260927-cal1` and `mistral-relation-replay-20260927-cal1`.
These ignored run directories are not bundled into Git; the hashes below identify
the retained local evidence, not a claim that a fresh clone contains the runs.

| Artifact | SHA-256 |
|---|---|
| Both plans | `868035fb60731dcf4dd45d39ef7f18d34a6d16077d8afe9dbf71c88dc9dd5728` |
| Luna result | `dc4ea0ba3ad2843ecbba0197fe640c7cffefc5483c7accef033904f34d5f4bdf` |
| Luna raw responses | `28772c825907f0dccf65b3e027fa7488c7db81d47e8a1aaeaf69f1f2e56304f0` |
| Mistral result | `b6a5925ac71f92d7511c4903714d96ae1420688946c0cddc56e7dcc31d9cabb0` |
| Mistral raw responses | `676236c366f11a6cd748cac597bde99e2d8477719f8af8904805098810c4a5d0` |

Validation: 60 unit tests, scoped Ruff, compilation, CLI help, existing live-run
smoke with fake models, and diff whitespace checks passed. No additional paid
replication or revised endpoint scoring was performed.
