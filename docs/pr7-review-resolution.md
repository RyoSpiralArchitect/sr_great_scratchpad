# PR 7 review resolution

Date: 2026-09-28. This records the four unresolved review comments addressed
before merge, without replacing earlier experiment receipts.

## Fixes

1. **Bound centerline input to visible history.** Normal chat derives hints
   from the same bounded text sent to the provider. Plain dialogue and
   centerline-only do the same. An evicted user message, including the clipped
   beginning of a partially retained message, cannot return through the hints.
   Analysis now sees the visible transcript, including visible assistant text,
   rather than an independently selected list of earlier user-role messages.
2. **Use one dialogue history representation.** All dialogue modes receive the
   same bounded `Speaker A/B` and `Moderator` transcript. Scratchpad dialogue
   does not spend the character budget on extra `user:`/`assistant:` prefixes.
   Existing standalone chat formatting is unchanged.
3. **Inspect every request at a probe.** Semantic analysis retains system/user
   inputs for every request at the same turn and speaker. A note returned by
   `search`, `recent`, or `pack` counts only when a subsequent model request
   actually contains it. A tool observation alone does not count. The score is
   the maximum per-request containment, not a fabricated union of partial views.
4. **Inspect every note field.** Containment uses the same all-field
   `analysis_text` used for semantic classification. A generic raw `text` field
   alone cannot establish visibility of an absent correction in the annotation.
   Per-request scores, best request index, and per-field scores are retained.

The visibility definition is explicitly versioned as
`all-note-fields-max-provider-request-v2` in semantic schema 3. Its threshold
remains 0.72. It is a lexical exposure proxy, not proof of source attribution,
retrieval provenance, understanding, or factual correctness. Retrieval benchmark
queries still use the first request, before tool observations.

## Verification

The new regression suite reproduced all four review issues before the code
change and passes afterward. It covers clipped/evicted/zero-budget history,
identical transcript windows across all four ablation modes, all seven note
fields, post-action requests for all three read tools, absent annotations,
other speakers/turns, missing requests, system inputs, and partial-view isolation.

- Full suite: 70 tests pass.
- Scoped Ruff, Python compilation, and whitespace checks pass.
- Existing `scripts/live_run.sh` smoke passes using fake models only.
- No new paid model calls, no endpoint vocabulary changes, and no new efficacy
  experiment were performed for this review.
- GitHub has no configured status checks for this PR; these are local checks,
  not a claim of hosted CI approval.

## Historical artifact check

Offline re-analysis was written only under
`.great_scratchpad/runs/pr7-review-20260928/`, outside the frozen source runs.
Each cohort's original assessment object was extracted from its saved report
and reused. This matters because the current taxonomy has acquired relation
probes/contrasts since some original reports were produced. Only fields that
existed in each original result are compared as historical endpoints.

| Source cohort | Target responses | Existing behavioral fields changed | Visibility booleans changed |
|---|---:|---:|---:|
| independent n=8 | 32 | 0 | 0 |
| frozen-note calibration 1 | 4 | 0 | 0 |
| selective-recall calibration 1 | 4 | 0 | 0 |

The compared behavioral fields are frame score, literal counts, existing
relation counts, and note-response similarity. Containment numbers themselves
can change under the corrected definition; their booleans happened not to cross
the threshold in these 40 targets.

As a separate diagnostic, recomputing centerline active centers from the actual
old visible history/current-message input removed no old center in 288 n=8
first requests or 48 selective-calibration requests. It removed the generic
`center pin / drift control` hint in frozen replay's `replay-full-r01`, turn 6
(1/48 requests). This is not a count of proven correction leaks or an exhaustive
audit of causal validity. Source manifests, traces, transcripts, and original
semantic reports were hash-checked unchanged during the audit.

The audit's per-cohort `audit.json` stores those source hashes and diagnostic
differences; `original-assessment.snapshot.json` and `matched-assessment.json`
retain the matched assessment and new output. They are local ignored artifacts,
not files supplied by a fresh Git clone.

## Interpretation boundary

Earlier observations remain observations under the earlier runner. These fixes
do not retroactively equalize its history windows or remove information that a
provider already saw. Historical claims that the complete implementation was
free of these confounds are superseded by this qualification, even where the
recorded numerical result is unchanged.

Future generation needs the corrected runner and fresh protocol identity. The
fixed-probe Luna/Mistral calibration still demonstrates limitations of both the
representation and the lexical endpoint; it is not a repaired full-dialogue run.
Preserve the rejected-alternative versus historically-adopted-state distinction,
and correct ground truth/assessment offline before another paid calibration.
