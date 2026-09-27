# Fixed-probe relation calibration

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
