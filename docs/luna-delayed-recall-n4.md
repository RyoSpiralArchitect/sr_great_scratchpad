# Luna delayed-recall Stage 1: n=4 pilot

## Result boundary

This pilot tests whether a provider-visible scratchpad note helps
`gpt-5.6-luna` recover a corrected biological comparison level after the
ordinary 700-character dialogue window has dropped the correction. It does not
establish general conversational-memory quality.

The frozen primary contrast is paired within replicate:

`scratchpad-scratchpad - write-no-recall`

## Append-only run ledger

No failed run was resumed, overwritten, or included in the behavioral result.

| Attempt | Source commit | Status | Last session | Failure classification | Suite SHA-256 |
|---|---|---|---|---|---|
| n4 | `45167c56119d96944f85fd144e9814017a99704e` | failed | `scratchpad-scratchpad-r03`, turn 5 | malformed output and repair consumed the accepted-output pool before final | `c1e9367037ce9a897606b59846ab2bc2f1ae3fe382ba70e81250114605978161` |
| n4-rerun1 | `69a23100e8fda46334693b5af618473a4bad31de` | failed | `scratchpad-scratchpad-r04`, turn 3 | the note action and its repair were both truncated at the old 300-token per-call cap | `edd0522a728357031c629483adc8a53368cd241bea4cadef7270109e08a89d34` |
| n4-rerun2 | `4b87a6b1bfd5abe556df6afebdfd1b6e5654f5a5` | valid | all 16 sessions | 400-token action/repair cap plus 200-token final reserve | `1487910eced85f01d0367f64a999df339dc46c2a22411ea304cceb8cae805eb6` |

The repair design keeps the 600-token accepted action/final allowance unchanged.
Invalid JSON is charged to a separate bounded provider-cost reserve. The valid
cohort needed no parse repair, but the reserve remains part of the preflight.

## Valid-run provenance

- run id: `dialogue-2026-08-26T165909-0700-effcf0fb`
- model/profile: `gpt-5.6-luna` / `openai-5.6-luna`
- scenario SHA-256: `df65f5481971f5a2d7f22001d4ac6dde7abb523b536c749eb440fad18b44f5ee`
- dialogue runner SHA-256: `d017d16bb30bfeb0b59de9c90b29d0b5d8d9206a0b0f383e1c2cb8dc70ca1d21`
- taxonomy SHA-256: `bd995316c76764f436024fe57cc66a1bdd3dc3831cbc10a952de36442b22b964`
- analyzer SHA-256: `2b664b66a2580b28b13c570cf579eb07ec4213555d1bf334a7e92890afe5fd11`
- semantic JSON SHA-256: `36b5203793ea03de66e27ede50b60fc367c8ac2b9cbb93d29702a19da9f7bfe3`
- semantic Markdown SHA-256: `f8f98f434a43c3f9f435a9485f7ae65fa70937f7bd200d1865aae279b340fd22`
- report SHA-256: `032754980f159a0508d7e329764b259408ea0e81158c611d371371b4e85f5555`
- corpus: 192 utterances and 28 successful notes

The semantic analyzer was replayed twice with byte-identical JSON and Markdown
outputs.

## Validity gate

| Check | Result |
|---|---|
| 16 sessions completed | pass |
| deterministic four-way condition rotation | pass |
| starting speaker balanced A/B/A/B | pass |
| unrecovered JSON failures or stopped turns | 0 |
| original correction absent from all turn-11 provider prompts | pass |
| pre-probe correction note in both writing conditions | 4/4 pairs |
| write-no-recall correction note hidden at turn 11 | 4/4 |
| full correction note visible at turn 11 | 4/4 |

## Primary paired result

| Replicate | Starter | Write position | Full position | Write score | Full score | Delta | Literal write | Literal full |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | A | 3 | 4 | 0.030507 | 0.211539 | +0.181032 | 0/2 | 1/2 |
| 2 | B | 2 | 3 | 0.012313 | 0.230151 | +0.217838 | 0/2 | 1/2 |
| 3 | A | 1 | 2 | 0.006791 | 0.216505 | +0.209714 | 0/2 | 2/2 |
| 4 | B | 4 | 1 | 0.102581 | 0.228910 | +0.126329 | 1/2 | 2/2 |

- mean paired delta: `+0.183728`
- median paired delta: `+0.195373`
- sample standard deviation: `0.041395`
- positive direction: `4/4`
- fixed-seed paired-bootstrap 95% interval: `[0.147175, 0.213776]`

The interval uses 10,000 deterministic SHA-256-indexed resamples with seed
`20260826`. At n=4 it is a descriptive stability readout, not a substitute for
the independent confirmation cohort.

## Literal paired outcomes

Complete two-probe recovery by session:

| Both pass | Full only | Write only | Neither | Discordant |
|---:|---:|---:|---:|---:|
| 0 | 2 | 0 | 2 | 2 |

Across the eight paired literal items:

| Both pass | Full only | Write only | Neither | Discordant |
|---:|---:|---:|---:|---:|
| 1 | 5 | 0 | 2 | 5 |

The semantic endpoint and literal probes agree directionally, but they measure
different things. Prototype alignment is continuous and does not certify factual
correctness; literal probes require the predeclared old and new comparison-level
terms.

## Cost and mechanics

- model calls: 203 (preflight worst case 384; calibration projection 220)
- prompt tokens: 246,485 (projection 280,964)
- completion tokens: 27,096 (projection 28,924)
- total provider tokens: 273,581
- successful writes: 28 (`write-no-recall` 13; full 15)
- full memory-context injections: 28
- deterministic multi-object protocol recoveries: 17
- JSON parse errors: 0

## Broader semantic readout

Full scratchpad had lower primary-frame entropy (`0.650`) than raw (`0.717`),
centerline (`0.774`), and write-no-recall (`0.788`). Unlike calibration 3,
full also had the highest same-speaker lag similarity (`0.053` versus `0.043`
for write-no-recall). The earlier n=1 suggestion that recall avoided repetition
therefore did not persist and should not be promoted as an effect.

Correction-frame content in saved notes was nearly matched between writing
conditions (`0.1193` write versus `0.1200` full). The delayed response difference
appeared after note availability diverged, not because the control failed to
write the correction.

## Stage 2 decision

The preregistered rule advances when three or four valid paired deltas are
positive. This pilot produced four of four. Proceed to a fresh independent n=8
confirmation with the same model, scenario, taxonomy, history window, budgets,
starter balance, condition rotation, and validity gate. Do not pool this pilot
into the confirmatory primary estimate.
