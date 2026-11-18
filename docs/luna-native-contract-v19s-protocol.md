# V1.9s: Can a nearly matching chain supply a false endpoint?

V1.8s supplied many records that explicitly identified themselves as
unrelated. This standalone experiment tests a different question: when
several *complete, internally consistent* chains are mixed together, does
lexical similarity make the model borrow another request's pool or citations?
All records are supplied directly; no retrieval or memory writes are involved.

## Frozen comparison

Use two new authored targets (construction seed 26110322). Show the first
with its complete chain and again without its endpoint. Show the second with
an explicitly pending endpoint. Add six disconnected request → team → line →
pool chains to each view. Every assigned pool is distinct. No distractor
announces itself as unrelated; the scorer matches the actual typed edges.

| View | Correct value | Required citations |
|---|---|---|
| Complete | Target's pool | Assignment, link, endpoint |
| Endpoint removed | Unknown | Assignment, link |
| Pending endpoint | Unknown | Assignment, link, pending record |

Each view has a **far** and **near** version. The six decoy request, team and
line keys have the same prefix, width and alphabet as their target counterparts.
Only their five hex digits change: all five differ in far, just the final digit
in near. Decoy pools, evidence IDs, positions, public wording, target facts and
answer key are held fixed within each contrast. Shuffle with a case-local seed
before assigning record IDs; removing the endpoint does not renumber records.
Distance order reverses for the second target; format order alternates by view.
Both formats receive identical visible input, not necessarily equal billed tokens.

## Bounds and interpretation

- 2 target cases, 3 evidence states, 2 distances, 2 formats: **12 requests**.
  Output allocation 49,152 tokens total (4,096 each); serialized input cap
  200,000 bytes. GPT-6 Luna, high reasoning, no citation enums.
- Same provider stop rules, no repair, no retry, no replacement or retrieval
  pilot. A stopped prefix stays stopped. Preparation itself uses no API key.
- Success requires all 6 views per format to pass the unchanged caller and
  semantic contracts. Compare near vs far *within each state and format*;
  inspect wrong values and extraneous IDs separately. Getting the value right
  with another chain's evidence is not a pass. Keep null and failed contrasts.
- These are dependent, descriptive contrasts, not six independent cases,
  a rate estimate, a comparison against V1.8s, or authorization to scale up.

## Reproduction

From the committed source, prepare a new, unused directory:

```sh
python3 -S -m great_scratchpad.native_contract_experiment prepare \
  --spec scenarios/luna_native_contract_v19s.json \
  --out-dir .great_scratchpad/runs/luna-native-contract-v19s-20261118 \
  --max-calls 12 --max-output-tokens 49152 --max-input-bytes 200000
```

Only after approval, use the same directory and the printed explicit digest
with `run --out-dir ... --plan-sha256 ...`. `report` accepts the same arguments
and audits saved responses without calling the provider.
