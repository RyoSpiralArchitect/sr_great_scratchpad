"""Versioned evidence-bearing uncertainty contract and authored reference cases.

The historical two-field contract and its scores remain unchanged.
"""

from __future__ import annotations

from .grounded_recall import strict_json
from .memory_task_design import FAMILIES, SYSTEM as LEGACY_SYSTEM, make_case, source_text

METHOD = "evidence-state-v2"
VARIANTS = ("legacy", "guarded-legacy", "evidence-state")
FLAG_STATES = ("enabled", "disabled", "unknown", "unobserved")
PILOT_CASES = (
    "hold-unknown", "urgent-unknown", "hold-dominates", "urgent-enabled",
    "approved-update", "proposals-only", "complete-join", "pending-join",
)
CALIBRATION_CASES = (*PILOT_CASES, "base-route", "hold-unobserved")

GUARD = """
For routing, extract each flag from the supplied request, not from a default.
An explicitly unconfirmed flag is unknown; a flag absent from supplied records is
unobserved. Neither state means disabled. Apply these rules in order:
1. If hold is enabled and its override is supplied, use the hold route regardless
   of urgent, even if urgent is unknown or unobserved.
2. If hold is not explicitly disabled, the route is unknown.
3. With hold disabled and the applicable policy AND override supplied, urgent
   enabled selects the fast route; urgent disabled selects the base route.
4. Otherwise the route is unknown. Missing rules or links do not license a value.
Proposals do not establish an approved decision. A pending endpoint does not
establish a pool. Use only supplied original records, never guessed defaults.
"""

STATE_SYSTEM = """Answer a question about a fictional project using only supplied records.
Return one JSON object with exactly four fields:
{"status":"known or unknown","value":"exact recorded answer or null",
 "evidence":["source id"],"flags":{}}
status is "known" only when supplied records determine one exact value; value
must then be that nonempty string. Otherwise status is "unknown" and value is
JSON null, not a prose description of uncertainty.
An unknown value CAN have evidence: cite the supplied records establishing why
it is undetermined (unconfirmed flags, proposals, pending links, or a partial
chain). Cite all relevant connected records supporting that uncertainty. If no
relevant records are supplied, use evidence: []. For a known value, cite every
record needed for its inference. Use at most eight distinct visible source ids;
never cite unrelated records, including similarly named requests.
For routing, flags must have exactly urgent and hold, each one of "enabled",
"disabled", "unknown", "unobserved". Copy their states from the supplied request:
有効 = enabled; 無効 = disabled; 未確認 = unknown; absent = unobserved.
Even if one flag is irrelevant to the selected branch, report it faithfully.
For all other task families, use flags: {}.
""" + GUARD

SYSTEMS = {"legacy": LEGACY_SYSTEM, "guarded-legacy": LEGACY_SYSTEM + GUARD,
           "evidence-state": STATE_SYSTEM}


def routing_value(urgent: str, hold: str) -> str | None:
    """Resolve a fully supplied rule set without collapsing unknown to false."""
    if urgent not in FLAG_STATES or hold not in FLAG_STATES:
        raise ValueError("Unknown flag state.")
    if hold == "enabled":
        return "held_value"
    if hold != "disabled":
        return None
    return {"enabled": "fast", "disabled": "base"}.get(urgent)


def make_state_case(seed: int, scenario: str, split: str, distractors: int = 72) -> dict:
    if scenario not in CALIBRATION_CASES:
        raise ValueError("Unknown uncertainty scenario.")
    family = ("decision-update" if scenario in {"approved-update", "proposals-only"}
              else "distributed-join" if scenario in {"complete-join", "pending-join"}
              else "scoped-exception")
    # Keep case identities disjoint even when scenarios share a task family.
    case_seed = seed * 100 + CALIBRATION_CASES.index(scenario)
    case = make_case(case_seed, family, "interference", split, distractors)
    case.update(id=f"{METHOD}-{split}-{scenario}-{seed}", scenario=scenario)
    if family == "scoped-exception":
        urgent, hold = {
            "hold-unknown": ("disabled", "unknown"),
            "urgent-unknown": ("unknown", "disabled"),
            "hold-dominates": ("unknown", "enabled"),
            "urgent-enabled": ("enabled", "disabled"),
            "base-route": ("disabled", "disabled"),
            "hold-unobserved": ("disabled", "unobserved"),
        }[scenario]
        request = next(r for r in case["records"] if r["kind"] == "request")
        request["flag_states"] = {"urgent": urgent, "hold": hold}
        request["urgent"] = {"enabled": True, "disabled": False}.get(urgent)
        request["held"] = {"enabled": True, "disabled": False}.get(hold)
        words = {"enabled": "有効", "disabled": "無効", "unknown": "未確認"}
        clauses = [f"{label}フラグは{words[state]}" for label, state in
                   (("緊急", urgent), ("保留", hold)) if state != "unobserved"]
        request["text"] = f"申請 {case['target']} は対象群 {request['group']}。" + "、".join(clauses) + "。"
    elif scenario == "proposals-only":
        for record in case["records"]:
            if record["kind"] == "decision":
                record["status"] = "proposal"
                record["text"] = (f"案件 {case['target']} の圧縮方式を {record['value']} にする案。"
                                  "これは未承認の提案であり、承認済みの決定ではない。")
    elif scenario == "pending-join":
        endpoint = next(r for r in case["records"] if r["kind"] == "line-pool")
        endpoint.pop("pool")
        endpoint.update(kind="pending", text=f"処理系列 {endpoint['line']} の実行プールは未確定。予約枠は確定記録ではない。")
    case["truth"] = reference_state(case)
    return case


def reference_state(case: dict, visible_ids: list[str] | None = None) -> dict:
    """Independent typed ledger restricted to the records actually supplied."""
    if case["family"] not in FAMILIES:
        raise ValueError("Unknown task family.")
    records = [r for r in case["records"] if visible_ids is None or r["id"] in visible_ids]
    value, support, eligible, flags = None, [], [], {}
    if case["family"] == "decision-update":
        decisions = [r for r in records if r["kind"] == "decision" and r["target"] == case["target"]]
        approved = [r for r in decisions if r["status"] == "approved"]
        eligible = [r["id"] for r in decisions]
        if approved:
            last = max(approved, key=lambda r: r["turn"])
            value, support = last["value"], [last["id"]]
        else:
            support = eligible[:]
    elif case["family"] == "scoped-exception":
        flags = {"urgent": "unobserved", "hold": "unobserved"}
        request = next((r for r in records if r["kind"] == "request" and r["target"] == case["target"]), None)
        if request:
            flags = dict(request["flag_states"])
            policy = next((r for r in records if r["kind"] == "policy" and r["group"] == request["group"]), None)
            override = next((r for r in records if r["kind"] == "override" and r["group"] == request["group"]), None)
            eligible = [r["id"] for r in (policy, override, request) if r]
            if flags["hold"] == "enabled" and override:
                value, support = override["held_value"], [override["id"], request["id"]]
            elif flags["hold"] == "disabled" and policy and override:
                field = {"enabled": "fast", "disabled": "base"}.get(flags["urgent"])
                if field:
                    value, support = policy[field], eligible[:]
            if value is None:
                support = eligible[:]
    else:
        assignment = next((r for r in records if r["kind"] == "assignment" and r["target"] == case["target"]), None)
        link = next((r for r in records if assignment and r["kind"] == "team-line" and r["team"] == assignment["team"]), None)
        endpoint = next((r for r in records if link and r["kind"] in {"line-pool", "pending"} and r["line"] == link["line"]), None)
        support = eligible = [r["id"] for r in (assignment, link, endpoint) if r]
        if endpoint and endpoint["kind"] == "line-pool":
            value = endpoint["pool"]
    return {"status": "unknown" if value is None else "known", "value": value,
            "support": support, "eligible_ids": eligible, "flags": flags}


def parse_answer(raw: str, family: str, variant: str = "evidence-state") -> dict:
    """Strict, reusable contract validation; semantic grounding is separate."""
    if variant not in VARIANTS or family not in FAMILIES:
        raise ValueError("Unknown output contract.")
    answer = strict_json(raw)
    if not basic_answer(answer):
        raise ValueError("Expected a nonempty value or null and at most eight distinct source ids.")
    if variant != "evidence-state":
        if set(answer) != {"value", "evidence"} or (answer["value"] is None and answer["evidence"]):
            raise ValueError("Legacy null requires empty evidence and exactly two fields.")
        return answer
    if set(answer) != {"status", "value", "evidence", "flags"}:
        raise ValueError("Expected exactly status, value, evidence and flags.")
    expected_status = "unknown" if answer["value"] is None else "known"
    if answer["status"] != expected_status:
        raise ValueError("status and value disagree.")
    flags = answer["flags"]
    keys = {"urgent", "hold"} if family == "scoped-exception" else set()
    if (not isinstance(flags, dict) or set(flags) != keys
            or not all(isinstance(s, str) and s in FLAG_STATES for s in flags.values())):
        raise ValueError("Expected explicit routing flag states, or empty flags for other tasks.")
    return answer


def basic_answer(answer: object) -> bool:
    """Format-neutral diagnostic, NOT a replacement for either strict contract."""
    return bool(isinstance(answer, dict) and {"value", "evidence"}.issubset(answer)
                and (answer["value"] is None or isinstance(answer["value"], str) and answer["value"].strip())
                and isinstance(answer["evidence"], list) and len(answer["evidence"]) <= 8
                and all(isinstance(i, str) and i for i in answer["evidence"])
                and len(answer["evidence"]) == len(set(answer["evidence"])))


def assess_answer(raw: str, case: dict, prompt: str, variant: str) -> dict:
    visible = [r["id"] for r in case["records"] if source_text(r) in prompt]
    expected = reference_state(case, visible)
    result = {"schema_ok": False, "value_correct": False, "epistemic_success": False, "contract_success": False,
              "recovered": False, "explicit_abstention": False, "unsupported_concrete": False,
              "unrecognized_value": False, "flags_faithful": None,
              "expected": expected, "errors": []}
    try:
        parse_answer(raw, case["family"], variant)
        result["schema_ok"] = True
    except (ValueError, TypeError, RecursionError) as exc:
        result["errors"].append(str(exc))
    try:
        answer = strict_json(raw)
    except (ValueError, TypeError, RecursionError):
        return result
    if not basic_answer(answer):
        return result
    value, evidence = answer["value"], set(answer["evidence"])
    result.update(value_correct=value == expected["value"], explicit_abstention=value is None,
                  citations_visible=evidence.issubset(visible),
                  citations_relevant=evidence.issubset(expected["eligible_ids"]),
                  proof_covered=set(expected["support"]).issubset(evidence))
    result["epistemic_success"] = all(result[k] for k in
                                      ("value_correct", "citations_visible", "citations_relevant", "proof_covered"))
    if variant == "evidence-state":
        result["flags_faithful"] = answer.get("flags") == expected["flags"]
    result["contract_success"] = (result["schema_ok"] and result["epistemic_success"]
                                  and result["flags_faithful"] is not False)
    truth = reference_state(case)
    result["recovered"] = bool(result["epistemic_success"] and value is not None and value == truth["value"])
    vocabulary = {r[k] for r in case["records"] for k in ("value", "base", "fast", "held_value", "pool") if k in r}
    result["unsupported_concrete"] = value in vocabulary and (not result["value_correct"] or not result["proof_covered"])
    result["unrecognized_value"] = value is not None and value not in vocabulary
    return result
