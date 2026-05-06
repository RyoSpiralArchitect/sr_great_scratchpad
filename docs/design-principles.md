# Great Scratchpad design principles

Great Scratchpad is built around one wager: a future conversation needs a way
back into the path, not only a saved conclusion.

## 1. Preserve trajectory before polish

The primary artifact is roomy Markdown because the stored material is not just
data. It is externally visible articulation: local wording, metaphors,
uncertainty, names, and the pressure of how the conversation moved.

The tool should not turn every turn into terse database facts too early. That
would recreate the semantic compression failure it is meant to study.

## 2. Keep machine boundaries explicit

Roomy Markdown does not mean loose parsing everywhere. Machine-readable
boundaries should be explicit and narrow:

- turn files use canonical `##` section headings
- parsers only treat known section headings as structural boundaries
- context packs preserve source paths
- audit results are flags, not proofs
- LLM writes are draftable and reviewable

This lets the storage format stay humane while the code avoids guessing.

## 3. Retrieval should show its hand

Every retrieval surface should make it easy to see why a memory was included.
Search scores, source paths, center pins, trajectory notes, anchors, open
questions, and drift risks are part of the retrieval result, not decorative
metadata.

The context pack's source index is the compact re-entry map; the full Markdown
below it is the inspectable evidence.

## 4. Audit observes, it does not adjudicate

Audit should make review cheaper without pretending to know the truth. A high
annotation/raw ratio, missing fields, or unsupported anchors are review signals.
They are not automatic accusations.

This matters because the project is explicitly preserving uncertainty and
local language. The audit layer should keep that uncertainty visible.

## 5. Agency belongs above deterministic storage

The lower layer should remain cheap and inspectable: files, deterministic
search, context packs, and audit flags. LLM agency should sit above that layer:
deciding when to search, what to retrieve, and whether a note should be drafted.

This separation keeps experiments reversible. If an agent behaves oddly, the
stored memory and retrieval evidence remain legible without trusting the agent.
