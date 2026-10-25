"""Prompt-only schema clarification; the v2 assessor and gate are unchanged."""

from __future__ import annotations

import json

from . import grounded_recall as v2
from .llm import estimate_token_count

METHOD = "grounded-record-recall-v2.1"
UNAVAILABLE_EXAMPLE = {
    "rejected_alternative": None,
    "accepted_unit": None,
    "comparison_boundary": None,
    "prior_adoption": {"status": "not_established", "evidence": []},
}
SYSTEM = v2.SYSTEM + """

Schema clarification: the first three top-level fields are EACH either an
entire JSON null OR an object with a NON-NULL string value and source evidence.
Never emit an object whose value is null. No status field belongs inside them.
If all source records are absent, return EXACTLY this complete object:
""" + json.dumps(UNAVAILABLE_EXAMPLE, ensure_ascii=False, separators=(",", ":")) + """
For a missing individual role when other records are available, likewise set
that whole top-level role field to null. Do not invent content to fill an object.
"""


def abstention_diagnostic(raw: str) -> dict:
    """Recognize two explicit abstention shapes without changing strict scoring."""
    result = {"parseable": False, "explicit_abstention": None, "shape": "unassessed"}
    try:
        obj = v2.strict_json(raw)
    except (ValueError, TypeError, RecursionError):
        return result
    result["parseable"] = True
    if not isinstance(obj, dict) or set(obj) != {*v2.ROLES, "prior_adoption"}:
        return result
    prior = obj["prior_adoption"]
    prior_empty = prior == {"status": "not_established", "evidence": []}
    top_null = all(obj[role] is None for role in v2.ROLES)
    object_null = all(obj[role] == {"value": None, "evidence": []} for role in v2.ROLES)
    result["explicit_abstention"] = prior_empty and (top_null or object_null)
    result["shape"] = "top-level-null" if top_null else "object-null" if object_null else "other"
    return result


def diagnostic_checks() -> dict:
    vectors = [
        ("top-null", UNAVAILABLE_EXAMPLE, True),
        ("object-null", {**{r: {"value": None, "evidence": []} for r in v2.ROLES},
                         "prior_adoption": UNAVAILABLE_EXAMPLE["prior_adoption"]}, True),
        ("invented-history", {**UNAVAILABLE_EXAMPLE, "prior_adoption": {"status": "established", "evidence": []}}, False),
        ("extra-prose", {**UNAVAILABLE_EXAMPLE, "message": "An earlier choice is certain."}, None),
        ("uncited-value", {**UNAVAILABLE_EXAMPLE, "accepted_unit": {"value": "guess", "evidence": []}}, False),
        ("null-with-citation", {**UNAVAILABLE_EXAMPLE, "accepted_unit": {
            "value": None, "evidence": [{"source_id": "r1", "quote": "guess"}]}}, False),
    ]
    checks = [{"id": name, "expected": expected,
               "actual": abstention_diagnostic(json.dumps(value))["explicit_abstention"]}
              for name, value, expected in vectors]
    return {"total": len(checks), "passed": sum(c["expected"] == c["actual"] for c in checks), "checks": checks}


def build_plan(suite: dict, configs: list[dict]) -> dict:
    plan = v2.build_plan(suite, configs)
    if suite.get("calibration_contract") != "v2.1":
        raise ValueError("v2.1 requires its own predeclared fresh calibration fixture.")
    checks = diagnostic_checks()
    if checks["total"] != checks["passed"]:
        raise ValueError("Abstention diagnostic failed.")
    plan.update(method=METHOD, system_prompt=SYSTEM, diagnostic_checks=checks,
                assessor_method=v2.METHOD, schema_change="none; prompt clarification only")
    for cell in plan["cells"]:
        cell["input_tokens_estimated"] = estimate_token_count(SYSTEM + "\n" + cell["prompt"])
    plan["budget"]["input_tokens_estimated"] = sum(c["input_tokens_estimated"] for c in plan["cells"])
    return plan


def summarize_diagnostics(plan: dict, responses: list[dict], assessments: list[dict]) -> dict:
    if len(responses) != len(assessments):
        raise ValueError("Diagnostic rows must match assessed receipts.")
    cells = {cell["id"]: cell for cell in plan["cells"]}
    rows = []
    for response, assessment in zip(responses, assessments):
        cell = cells[response["id"]]
        rows.append({"id": cell["id"], "schema_ok": assessment["schema_ok"],
                     "strict_passed": assessment["passed"], "recovered_roles": assessment["recovered_roles"],
                     "epistemic_abstention": abstention_diagnostic(response["raw_output"])
                     if cell["condition"] == "none" else None,
                     "source_grounding_passed": assessment["passed"] if cell["condition"] != "none" else None})
    return {"method": "explicit-abstention-shape-diagnostic-v1", "changes_strict_gate": False, "rows": rows}
