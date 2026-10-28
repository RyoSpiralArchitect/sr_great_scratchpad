# Exploratory tail after an unreceived response

The length-aware continuation stopped at overall attempt 157/168: the linked
arm of the 72-distractor distributed-join interference case hit the configured
API read timeout. Attempts 1-156 have provider receipts. The timed-out attempt
has no received model text or usage; neither is reconstructed or guessed.
The original continuation remains `error` and its files remain unchanged.

This second post-hoc amendment records that attempted cell as a client failure
and calls only the final 11 unattempted cells, once each, with identical frozen
inputs and settings. It imports the existing 156 raw responses byte-for-byte
and appends an explicitly typed client-error event with `raw_output=null` and
`usage=null`. The event is derived from the saved error and the frozen request,
not presented as a provider response. Later client errors are likewise failures
and never retried. Human interruption still stops execution.

All original generation/scoring modules and both parent artifact layers are
hash-verified before any new call. The final report is exploratory end-to-end
success under output/client limits, not a successful original preregistered
pilot or a pure model-accuracy estimate. Failure remains in the linked arm;
there is no favorable cell removal. Report known provider usage separately
from unavailable usage, and never claim zero billed tokens for the lost response.

The remaining ceiling is 11 calls and 45,056 requested output tokens. The
overall campaign retains its previous maximum of 180 generation requests plus
two rejected parameter requests. There are no replacements for attempted cells.

```bash
python3 -S -m great_scratchpad.reinjection_timeout_tail prepare \
  --source-dir .great_scratchpad/runs/mistral4-reinjection-cont-20261028 \
  --source-plan-sha256 144200131d2f6607d0b747d59d6b76fd1f0c464cc6c08aff984860f6702d64f0 \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-tail-20261028 \
  --max-new-calls 11 --max-new-output-tokens 45056

python3 -S -m great_scratchpad.reinjection_timeout_tail run \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-tail-20261028 \
  --plan-sha256 TAIL_DIGEST

python3 -S -m great_scratchpad.reinjection_timeout_tail report \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-tail-20261028 \
  --plan-sha256 TAIL_DIGEST
```
