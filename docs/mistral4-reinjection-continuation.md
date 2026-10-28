# Exploratory continuation after the output-limit stop

On 2026-10-28 the v1.2-r1 pilot stopped at request 64/168. Requests 1-63
completed; request 64 returned HTTP 200 with `finish_reason=length`, 4,096
completion tokens (4,095 reasoning tokens) and empty final text. The original
runner correctly retained its response and stopped. The original result remains
`error`, not a retrospectively passing preregistered pilot.

The amendment treats a received length-limit response as an observed failure
under the fixed resource budget. It makes no additional call for that cell,
awards no task success even if partial JSON parses, and continues only the
remaining 104 unattempted cells. It retains the same prompts, case order,
provider model, sampling, reasoning, character and token budgets. No retrieval,
answer schema or reference semantics change. Both later length limits and
reader failures stay in the full matrix. A transport error still stops execution.

This stopping-rule change is post-hoc. Result estimates are exploratory, not a
successful completion of the original frozen protocol or held-out confirmation.
All seven conditions and both pressure tiers remain; no cell is selected by
treatment gain. The complete campaign still fits its existing ceiling of 180
generated responses plus two rejected inference requests.

The standalone continuation module leaves every original generation/scoring
module byte-unchanged. It verifies the original plan digest, passed calibration,
ordered received prefix, original assessments, response hashes, provider model,
and usage before preparing a new plan in a fresh directory. The imported raw
JSONL prefix stays byte-identical. New receipts are appended to that copy;
original artifacts are never changed. The new manifest records imported and new
call counts separately, hashes all parent artifacts and freezes the extension.

```bash
python3 -S -m great_scratchpad.reinjection_continuation prepare \
  --source-dir .great_scratchpad/runs/mistral4-reinjection-v12-r1-20261028 \
  --source-plan-sha256 97c3485741d46ced29fdde6a8976c4fe1848b758aed089b71252b15daf88aba1 \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-cont-20261028 \
  --max-new-calls 104 --max-new-output-tokens 425984

python3 -S -m great_scratchpad.reinjection_continuation run \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-cont-20261028 \
  --plan-sha256 CONTINUATION_DIGEST

python3 -S -m great_scratchpad.reinjection_continuation report \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-cont-20261028 \
  --plan-sha256 CONTINUATION_DIGEST
```
