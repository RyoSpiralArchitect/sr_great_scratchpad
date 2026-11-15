# Design Memo: Splitting Citation IDs From Rationale Text

Status: design only. No code, spec or spend is committed by this memo. Any
adoption requires its own prospective protocol revision and fresh evaluation;
it never regrades V1/V1.1 outcomes or converts a recorded failure into a pass.

## Problem

`evidence` is an array of supplied record IDs with no place for explanation.
The stopped V1 run showed a model returning prose in `evidence` — a real
caller-contract failure, but also a signal that models may want to attach a
short justification to each citation. Options:

### A. `rationale` as a free string field

Add `"rationale": {"type": ["string", "null"]}` beside `evidence`.

- Simple, provider-subset compatible, one extra field.
- A single blob cannot be checked per citation; long prose risks reintroducing
  the failure mode it was meant to contain (IDs embedded in text).

### B. `evidence` items become `{id, note}` objects

Replace the string array with objects: `{"type": "object", "properties":
{"id": ..., "note": {"type": "string"}}, "required": ["id", "note"],
"additionalProperties": false}`.

- Keeps each note bound to its citation; composes with the V1.2 enum by
  putting `enum` on `id`.
- Breaks the existing `evidence ⊆ source_ids` check shape and every consumer
  that reads the array of strings; a breaking contract change.

### C. Parallel `rationale` array of `{id, note}` objects (recommended)

Keep `evidence` unchanged; add `"rationale": {"type": "array", "maxItems": 8,
"items": {"type": "object", "properties": {"id": {"type": "string"}, "note":
{"type": "string"}}, "required": ["id", "note"], "additionalProperties": false}}`.

- Non-breaking for `evidence` consumers; gives prose a bounded outlet.
- Strict mode requires all properties, so `rationale` is mandatory but may be
  an empty array; unknown answers can still leave it empty.
- Local validation extends the existing subset check to `rationale[].id`;
  notes themselves stay `semantic_grounding: not_checked` — an explicitly
  unvalidated claim channel, never evidence.

## Open Questions For The Future Protocol

- Whether `rationale[].id` should reuse the V1.2 enum (composition: yes, if a
  stacked revision is ever versioned; the isolated V1.2/V1.3 comparisons come
  first).
- Whether note length needs a `maxLength` bound to keep rationale from
  becoming a second answer field.
- Whether the semantic gate gains a *descriptive* (non-gating) measure, e.g.
  fraction of cited IDs also appearing in `rationale`, recorded but never
  scored as pass/fail.
- Required-by-strict rationale vs. tolerating provider-side empty output: the
  empty array is already the minimal valid value; no new failure mode.

## Recommendation

Adopt C in a future `evidence-state-native-v2` contract, gated behind its own
spec version and fresh-seed campaign. Do not bundle it with V1.2 or V1.3:
each factor keeps a single isolated comparison against the V1.1 baseline
before any stacking is evaluated.
