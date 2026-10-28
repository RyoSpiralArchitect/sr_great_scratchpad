# Evidence-State v2.1 Calibration Revision

The [v2 protocol](uncertainty-contract-v2-protocol.md) and output contract remain
the reference. V2 calibration completed at **11/12 strict**, 12/12 value decisions,
with zero unsupported concrete answers. Its empty-source routing response was:

```json
{"status":"unknown","value":null,"evidence":[],"flags":{}}
```

This is correct abstention but violates the required two `unobserved` flag fields.
No v2 pilot calls were issued. Its failed gate and original receipts are retained,
not silently passed or reissued. The raw audit was completed before changing the
runner; replay v2 with source commit `f3c198a63f2dcbf7651d3633412057aed0177870`.

## Fixed Before New Calls

V2.1 adds only two complete empty-source examples to the evidence-state system
prompt: routing with both flags `unobserved`, and non-routing with `flags: {}`.
It clarifies that the question's task type still applies when the request record
is absent. The guard, parser, reference semantics, assessment, JSON Schema and
12/12 gate are **unchanged**. Both legacy system prompts are byte-identical.

Fresh seeds are calibration26102841 and pilot26102851; all eight original pilot
scenario types, all three contexts and all three variants remain. No pilot case
is selected from observed model outcomes. This is one planned revision, not an
open-ended sequence of attempts until calibration passes. If its calibration
fails, stop without a v2.1 pilot or a further paid revision in this campaign.

V2.1 retains a maximum 84 calls / 344064 output tokens / 2000000 input UTF-8 bytes.
Including the 12 v2 calibration calls already attempted, the total campaign cap
is **96 calls / 393216 output tokens**. The abandoned 72 v2 pilot slots are never
issued. Actual usage is recorded separately from allowances. This revision was
announced after the failed calibration and is not a preregistered first attempt
or evidence of an untuned out-of-sample calibration success.

## Commands

```bash
python3 -S -m great_scratchpad.uncertainty_experiment prepare \
  --spec scenarios/uncertainty_contract_v21.json \
  --out-dir .great_scratchpad/runs/uncertainty-contract-v21-20261028
python3 -S -m great_scratchpad.uncertainty_experiment run \
  --out-dir .great_scratchpad/runs/uncertainty-contract-v21-20261028 \
  --plan-sha256 "$PLAN_SHA256" --stage calibration
```

Only if the fresh raw-audited gate passes, run `--stage pilot` and then `report`
using the same directory/digest, exactly as in v2. No response repair, retries,
larger token limits, changed sampling, or substitute cases. Client/output errors
remain failures and missing usage remains unknown. No causal old/new-cohort
effect estimate; within the v2.1 pilot, compare the three matched variants with
value correctness separate from schema and evidence retention.

## Preserved v2 Receipt Identity

Local directory: `.great_scratchpad/runs/uncertainty-contract-v2-20261028`.
Plan digest: `cac1989ce3fcdbc52d5f3726cd9dbe959a48371134b9a25e5a1b1d74a20bc318`.

| Artifact | SHA-256 |
|---|---|
| plan.json | 7135b26d4d996b020a41a9587c95c4a05d8ce9c462b96f392788da47e376755e |
| calibration/result.json | 7397efb38099e78af75ea547cb25cf9a1e89e3872d6798c2784c909cf3c1b72a |
| calibration/attempts.jsonl | b13b3bf8afecb017257bc06c8c67b82985e492785f7d640ca6e12c19d98a321d |
| calibration/responses.jsonl | e75491b559fe2f8fcf32b8f13e2fb18a164522c1082320cb546ebced675e9aad |

V2 consumed 27019 provider-reported tokens (7770 input / 19249 output), with 12
completed responses, zero retries, zero missing usage, and no pilot calls.
