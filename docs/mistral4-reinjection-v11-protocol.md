# Mistral Large 4 reinjection pilot v1.1

Frozen on 2026-10-28 after v1 format/grounding calibration. v1 completed 6 calls,
passed 5/6, and correctly blocked all 168 pilot calls. Its raw receipts and
plan remain unchanged under `.great_scratchpad/runs/mistral4-reinjection-20261028/`.

The failed row had all three scoped-routing records and cited them correctly,
but returned the hold route when the hold flag was explicitly disabled. This
was a reader reasoning error under effort `none`, not a retrieval or schema
failure. No frozen score is revised.

v1.1 keeps the [v1 task design and endpoint](mistral4-reinjection-protocol.md),
all seven arms, both pressure tiers, the same linked ranker, 700-character
history, 1,200-character archive cap and the strict six-response gate.
The provider profile changes to `mistral-large-4-low`: reasoning effort `low`,
with 1,200 output tokens including provider-accounted reasoning. Seeds are
26102810 for calibration and 26102811 for the pilot. All condition prompts
and case order are frozen before this cohort starts.

The new cohort permits 174 calls (6 calibration + 168 pilot), at most 208,800
output tokens, and 2,000,000 UTF-8 input bytes. Including the previous failed
calibration, the campaign ceiling is 180 calls; its realized old output cost
is 97 tokens. No retries, substitutions or in-place resumption are allowed.
If this fresh gate fails, stop the campaign and report the reader failure.

This revision cannot by itself identify the causal effect of reasoning effort,
because the cases also changed. The comparison of retrieval arms remains
within the new frozen cohort, under identical reasoning/sampling settings.
The provider's explicit model name and returned alias are recorded but do not
prove an immutable weight revision.

```bash
python3 -S sr_great_scratchpad.py experiment reinjection-prepare \
  --spec scenarios/mistral4_reinjection_v11.json \
  --profile mistral-large-4-low \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-v11-20261028 \
  --max-api-calls 174 --max-suite-output-tokens 208800
```

Run `reinjection-run` with that new directory and digest, first for
`--stage calibration`, then `--stage pilot` after the raw-receipt gate passes.
