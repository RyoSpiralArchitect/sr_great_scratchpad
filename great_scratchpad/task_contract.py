"""Explicit task shape and branch proof instructions, without answer ledgers."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from .memory_task_design import FAMILIES

PROOF_INSTRUCTIONS = """
Before returning, check the proof obligations for the task. Do not output this
checklist, invent records, or append citations from outside the supplied input.

Routing:
- A known HOLD route needs the hold-override rule and the target request.
- A known FAST or BASE route needs THREE kinds of records: the policy, the
  hold-override rule, AND the target request. Even with hold disabled, cite the
  supplied higher-priority override: it establishes which exception was ruled
  out. Citing only the directly selected policy and request is incomplete.
- If a required rule is absent, do not guess a route. Return unknown and cite
  the supplied connected records, including the request if available.
- If hold is unknown/unobserved, or hold is disabled and urgent is unknown/
  unobserved, preserve unknown with all supplied connected supporting records.
- Enabled hold can still determine HOLD despite an unknown urgent flag.

Approved decisions:
- A known value needs the latest supplied approved decision for the target.
- Proposals alone do not approve a value; cite all supplied target proposals
  when reporting unknown. An unrelated approved decision is not evidence.

Joins:
- A known endpoint needs every supplied link from target to team to line to pool.
- A pending or missing endpoint requires unknown. Cite the connected chain as
  far as it is supplied, including a supplied pending statement.
- Without a target-linked starting record, do not cite disconnected endpoints.

With no relevant records, evidence is empty. Never erase valid uncertainty
evidence merely because value is null. Preserve flag states even if they do not
affect the selected branch. Validate the final citations, not just the value.
"""


def task_schema(family: str) -> dict:
    """Select structure from the declared operation, never from a hidden answer."""
    if family not in FAMILIES:
        raise ValueError("Unknown task kind.")
    path = Path(__file__).resolve().parents[1] / "schemas/evidence_state_v2.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    options = schema["properties"]["flags"]["oneOf"]
    schema["properties"]["flags"] = deepcopy(options[1 if family == "scoped-exception" else 0])
    schema["title"] = f"Evidence-state v2: {family}"
    return schema


def declare_task(prompt: str, family: str) -> str:
    schema = json.dumps(task_schema(family), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (f"Declared task kind: {family}. This remains the task kind even when records are empty.\n"
            f"Required output schema (structure only; cite actual supplied records):\n{schema}\n\n{prompt}")
