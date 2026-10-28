# Mistral Large 4 reinjection pilot v1.2

Frozen on 2026-10-28 before high-reasoning generation. The v1 calibration
passed 5/6, with a scoped-routing reader error; its pilot stayed blocked.
The v1.1 calibration made one HTTP request that failed before generation:
Mistral reports that Large 4 supports reasoning `none` or `high`, not `low`.
Those plans, raw receipts and errors remain unchanged in their original runs.

This protocol retains the [v1 retrieval design](mistral4-reinjection-protocol.md),
all seven conditions, pressure tiers 18/72, common history and archive limits,
the same strict assessor and the same six-response gate. It uses profile
`mistral-large-4-high`, reasoning effort `high`, and an output allowance of
4,096 tokens including provider-accounted reasoning. Seeds 26102820 and
26102821 are fresh calibration and pilot cases. No task or endpoint is selected
according to observed treatment gains.

The high-reasoning cohort permits at most 174 calls and 712,704 requested output
tokens. Input UTF-8 payload is capped at 2,000,000 bytes; actual provider usage
is reported separately. Including the earlier calibration, the complete
campaign permits at most 180 generated responses plus the one rejected HTTP
attempt (181 wire attempts). Old known output use is 97 tokens; there is no
usage receipt for the rejected request. No retries or substitutions occur
inside any frozen run. If this valid-parameter calibration fails, stop.

Changes in cases and reasoning budget prevent a causal before/after claim
about reasoning effort. Retrieval comparisons remain paired within the new
cohort. The explicit requested name and returned model are retained, without
claiming that an alias identifies immutable weights.

```bash
python3 -S sr_great_scratchpad.py experiment reinjection-prepare \
  --spec scenarios/mistral4_reinjection_v12.json \
  --profile mistral-large-4-high \
  --out-dir .great_scratchpad/runs/mistral4-reinjection-v12-20261028 \
  --max-api-calls 174 --max-suite-output-tokens 712704
```

Run `reinjection-run` using this directory and its digest for calibration,
then for the pilot only after the complete raw-receipt gate passes. All 168
pilot responses are retained regardless of treatment effect. The old v1.1
specification is historical and now fails preparation rather than spending
another unsupported-parameter request.
