# Luna delayed-recall calibration 3: semantic NLP readout

## Provenance

- run id: `dialogue-2026-08-26T085141-0700-0a39007a`
- scenario SHA-256: `df65f5481971f5a2d7f22001d4ac6dde7abb523b536c749eb440fad18b44f5ee`
- taxonomy SHA-256: `bd995316c76764f436024fe57cc66a1bdd3dc3831cbc10a952de36442b22b964`
- analyzer SHA-256: `2b664b66a2580b28b13c570cf579eb07ec4213555d1bf334a7e92890afe5fd11`
- semantic JSON SHA-256: `bc5970f0494eea23fc1499f5bb9b84ecd2c48866558fd4a792433ef5a363e2ce`
- corpus: 48 utterances and 7 successful notes

The analyzer was replayed twice with byte-identical JSON and Markdown outputs. The updated assessment adds a fixed-seed paired bootstrap and paired literal-outcome tables without regenerating the dialogue.

## Delayed correction

| Condition | Correction-frame score | Literal probe | Note visible | Note-response similarity |
|---|---:|---:|---:|---:|
| raw/raw | 0.126 | 1/2 | no | - |
| centerline-only | 0.101 | 0/2 | no | - |
| write-no-recall | 0.008 | 0/2 | no | 0.017 |
| scratchpad/scratchpad | 0.282 | 2/2 | yes | 0.131 |

The frozen paired full-minus-write contrast was `+0.274`. Both writing conditions had already saved a correct correction note. The identified provider-visible difference was recall availability at turn 11.

Raw received a moderate prototype score while recovering the wrong old level. This is why prototype similarity and exact literal probes remain separate; semantic similarity is not a correctness oracle.

## What the notes contained

The first note in each writing condition was primarily the biological comparison-level correction. Later write-no-recall notes were primarily classified as origin-versus-establishment, while later full-scratchpad notes were primarily center-versus-branch separation.

Mean note-frame scores:

| Condition | Biological correction | Analogy boundary | Origin/establishment | Center/branch | Epistemic calibration |
|---|---:|---:|---:|---:|---:|
| write-no-recall | 0.127 | 0.178 | 0.215 | 0.151 | 0.016 |
| scratchpad/scratchpad | 0.181 | 0.125 | 0.162 | 0.148 | 0.012 |

Both note sets were multi-frame rather than single-topic summaries. They preserved the correction, analogy limit, and branch structure in different proportions.

## Repetition and concentration

| Condition | Semantic entropy | Mean pair similarity | Same-speaker lag similarity |
|---|---:|---:|---:|
| raw/raw | 0.718 | 0.030 | 0.046 |
| centerline-only | 0.536 | 0.046 | 0.054 |
| write-no-recall | 0.629 | 0.049 | 0.060 |
| scratchpad/scratchpad | 0.580 | 0.038 | 0.039 |

Full scratchpad was more semantically concentrated than raw but less repetitive than write-no-recall in this replicate. Memory did not produce a simple repetition increase here.

## Weakly represented frame

Epistemic calibration was sparse in every condition: mean utterance scores ranged from `0.004` to `0.014`. The dialogue distinguished origins and establishment readily, but rarely demanded sources, historical evidence, or explicit uncertainty. A future topic family should test whether scratchpad memory preserves uncertainty and evidence boundaries, not only conceptual corrections.

## Claim boundary

This n=1 analysis identifies treatment plumbing and one aligned behavioral observation. It does not establish a stable quality effect. The next cohort must use paired replicates, balanced starting speakers, rotated condition order, frozen identities, and predeclared validity gates.
