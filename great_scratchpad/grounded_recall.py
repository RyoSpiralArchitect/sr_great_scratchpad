"""Frozen, citation-grounded record probes, not a general free-text judge."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Callable

from .centerline import analyze_centerline, render_centerline_hints
from .chat import build_chat_prompt, llm_trace
from .dialogue import add_usage, append_jsonl, canonical_json_sha256, empty_usage, render_dialogue_context
from .experiments import write_manifest
from .llm import (
    OPENAI_CHAT_ADAPTER, OPENAI_RESPONSES_ADAPTER, api_key_from_config,
    call_llm_result, config_with_output_token_limit, estimate_token_count, resolve_llm_adapter,
)
from .semantics import normalize_semantic_text
from .storage import load_llm_config, now_iso

METHOD = "grounded-record-recall-v2"
ROLES = ("rejected_alternative", "accepted_unit", "comparison_boundary")
STATUSES = ("established", "not_established", "refuted")
CONDITIONS = ("none", "original", "prose", "roles")
STAGES = {"calibration": 2, "confirmation": 4}
CALL_OUTPUT_TOKENS = 1000
MAX_CALLS = 48
CONFIG_FIELDS = {
    "backend", "adapter", "api", "base_url", "model", "api_key_env", "profile",
    "temperature", "top_p", "seed", "reasoning_effort", "json_mode", "timeout",
}
TOKEN_FIELDS = {"max_tokens", "max_output_tokens", "max_new_tokens"}
QUERY = "提示された記録に基づき、退けた比較案、今回採用した比較単位、比較の範囲、退けた案の過去の採用について整理してください。"
SYSTEM = """You are answering a synthetic record-grounding probe. Use only the supplied records.
Return exactly one JSON object, without Markdown, tools, commentary, or extra fields:
{"rejected_alternative": {"value": "short Japanese value", "evidence": [{"source_id": "record id", "quote": "exact supporting sentence"}]},
 "accepted_unit": {"value": "short Japanese value", "evidence": [{"source_id": "record id", "quote": "exact supporting sentence"}]},
 "comparison_boundary": {"value": "short Japanese value", "evidence": [{"source_id": "record id", "quote": "exact supporting sentence"}]},
 "prior_adoption": {"status": "established|not_established|refuted", "evidence": []}}
For each of the first three fields, use null if the records do not establish an answer.
When available, prefer the short phrase inside the Japanese quotation marks as the value.
Quote the complete supporting sentence verbatim, including its role, limitation or negation.
Cite only original source records, not added summaries. Do not invent source ids or quotes.
prior_adoption asks whether the NOW REJECTED alternative was actually adopted BEFORE the correction.
Use established only with an earlier explicit adoption sentence, and cite it in evidence.
Use refuted only with explicit earlier non-adoption evidence, and cite it.
Otherwise use not_established and an empty evidence array. Missing records or rejection now
do not prove either earlier adoption or earlier non-adoption. No other prose is permitted."""


def strict_json(text: str) -> object:
    def pairs(items: list) -> dict:
        out: dict = {}
        for key, value in items:
            if key in out:
                raise ValueError("Duplicate JSON key.")
            out[key] = value
        return out

    def invalid_constant(value: str) -> None:
        raise ValueError("Non-finite JSON constant.")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)


def aliases(claim: dict) -> set[str]:
    return {normalize_semantic_text(value) for value in [claim["value"], *claim["aliases"]]}


def evidence_shape(items: object) -> bool:
    return isinstance(items, list) and len(items) <= 4 and all(
        isinstance(item, dict) and set(item) == {"source_id", "quote"}
        and all(isinstance(item[key], str) and item[key].strip() for key in item)
        for item in items
    )


def validate_case(case: dict) -> None:
    records = case["records"]
    sources = {record["source_id"]: record for record in records}
    if not records or len(sources) != len(records):
        raise ValueError("Source ids must be unique and nonempty.")
    for record in records:
        if (not isinstance(record["source_id"], str) or not record["source_id"].isalnum()
                or type(record["turn"]) is not int or not 0 < record["turn"] < case["probe_turn"]
                or not isinstance(record["text"], str) or not record["text"].strip()):
            raise ValueError("Invalid source record or future evidence.")
    truth = case["truth"]
    if set(truth) != {*ROLES, "prior_adoption"}:
        raise ValueError("Exactly four truth fields are required.")
    for role, claim in truth.items():
        if not evidence_shape(claim["evidence"]):
            raise ValueError("Invalid truth evidence.")
        if role in ROLES:
            if (not isinstance(claim["value"], str) or not claim["value"].strip()
                    or not isinstance(claim["aliases"], list) or len(claim["aliases"]) < 2
                    or not all(isinstance(v, str) and v.strip() for v in claim["aliases"])
                    or not claim["evidence"]):
                raise ValueError("Each role requires a value, paraphrases and source evidence.")
        elif claim["status"] not in STATUSES:
            raise ValueError("Invalid prior-adoption status.")
        for evidence in claim["evidence"]:
            source = sources.get(evidence["source_id"])
            if source is None or evidence["quote"] not in source["text"]:
                raise ValueError("Truth quote is not in the source record.")
            if role in ROLES and claim["value"] not in evidence["quote"]:
                raise ValueError("Truth evidence must include the declared value.")
    if any(aliases(truth[a]) & aliases(truth[b]) for a in ROLES for b in ROLES if a != b):
        raise ValueError("Role aliases must not overlap.")
    prior = truth["prior_adoption"]
    if (prior["status"] == "not_established") != (not prior["evidence"]):
        raise ValueError("Historical claims require evidence; absence requires no citation.")
    correction_turn = min(sources[e["source_id"]]["turn"] for e in truth["rejected_alternative"]["evidence"])
    for evidence in prior["evidence"]:
        if (sources[evidence["source_id"]]["turn"] >= correction_turn
                or truth["rejected_alternative"]["value"] not in evidence["quote"]):
            raise ValueError("Historical evidence must establish the rejected unit before correction.")


def validate_suite(suite: dict) -> None:
    if suite.get("schema") != "grounded-recall-cases-v2":
        raise ValueError("Unsupported grounded-recall fixture.")
    cases = suite["cases"]
    if len(cases) != 6 or len({case["id"] for case in cases}) != 6:
        raise ValueError("Exactly six distinct cases are required.")
    for case in cases:
        if not isinstance(case["id"], str) or not case["id"].isalnum():
            raise ValueError("Case ids must be alphanumeric.")
        validate_case(case)
    for stage, count in STAGES.items():
        group = [case for case in cases if case["stage"] == stage]
        statuses = [case["truth"]["prior_adoption"]["status"] for case in group]
        if (len(group) != count or statuses.count("established") != count // 2
                or statuses.count("not_established") != count // 2):
            raise ValueError("Each stage must balance established and unestablished history.")


def valid_citations(items: list, expected: list, records: list[dict]) -> bool:
    if not expected:
        return items == []
    sources = {record["source_id"]: record["text"] for record in records}
    return bool(items) and all(
        item["source_id"] in sources and item["quote"] in sources[item["source_id"]]
        and any(e["source_id"] == item["source_id"] and e["quote"] in item["quote"] for e in expected)
        for item in items
    )


def assess_answer(raw: str, case: dict, visible: bool) -> dict:
    result = {"schema_ok": False, "passed": False, "recovered_roles": 0,
              "recovery_total": 3, "abstention_ok": False, "errors": [], "roles": {}}
    try:
        obj = strict_json(raw)
        if not isinstance(obj, dict) or set(obj) != {*ROLES, "prior_adoption"}:
            raise ValueError("Expected exactly four answer fields.")
        for role in ROLES:
            claim = obj[role]
            if claim is not None and (
                not isinstance(claim, dict) or set(claim) != {"value", "evidence"}
                or not isinstance(claim["value"], str) or not claim["value"].strip()
                or not evidence_shape(claim["evidence"])
            ):
                raise ValueError("Invalid role claim schema.")
        prior = obj["prior_adoption"]
        if (not isinstance(prior, dict) or set(prior) != {"status", "evidence"}
                or prior["status"] not in STATUSES or not evidence_shape(prior["evidence"])):
            raise ValueError("Invalid prior-adoption schema.")
    except (ValueError, TypeError, RecursionError) as exc:
        result["errors"].append(str(exc))
        return result
    result["schema_ok"] = True
    sources = case["records"] if visible else []
    for role in ROLES:
        claim, expected = obj[role], case["truth"][role]
        value_ok = claim is not None and normalize_semantic_text(claim["value"]) in aliases(expected)
        citation_ok = claim is not None and valid_citations(claim["evidence"], expected["evidence"], sources)
        recovered = bool(visible and value_ok and citation_ok)
        result["roles"][role] = {"value_ok": value_ok, "citation_ok": citation_ok, "recovered": recovered}
        result["recovered_roles"] += int(recovered)
        if visible and not recovered:
            reason = "missing_claim" if claim is None else "undeclared_value" if not value_ok else "unsupported_citation"
            result["errors"].append(f"{role}:{reason}")
        if not visible and claim is not None:
            result["errors"].append(f"{role}:claim_without_visible_records")
    expected_prior = case["truth"]["prior_adoption"] if visible else {"status": "not_established", "evidence": []}
    result["prior_status_ok"] = prior["status"] == expected_prior["status"]
    result["prior_evidence_ok"] = valid_citations(prior["evidence"], expected_prior["evidence"], sources)
    if not (result["prior_status_ok"] and result["prior_evidence_ok"]):
        result["errors"].append("prior_adoption:unsupported_status_or_citation")
    result["passed"] = not result["errors"]
    result["abstention_ok"] = not visible and result["passed"]
    return result


def reference_answer(case: dict, visible: bool = True) -> dict:
    if not visible:
        return {**dict.fromkeys(ROLES), "prior_adoption": {"status": "not_established", "evidence": []}}
    return {**{role: {k: deepcopy(case["truth"][role][k]) for k in ("value", "evidence")} for role in ROLES},
            "prior_adoption": deepcopy(case["truth"]["prior_adoption"])}


def offline_checks(suite: dict) -> dict:
    """Deterministic contract tests; not held-out validation of general semantics."""
    checks = []

    def encode(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def check(name: str, raw: str, case: dict, visible: bool, expected: bool) -> None:
        actual = assess_answer(raw, case, visible)
        checks.append({"id": case["id"] + ":" + name, "input_sha256": canonical_json_sha256(raw),
                       "expected": expected, "actual": actual["passed"], "ok": actual["passed"] == expected})

    for case in suite["cases"]:
        answer = reference_answer(case)
        raw = encode(answer)
        check("canonical", raw, case, True, True)
        check("hidden-source", raw, case, False, False)
        check("absent-source-abstention", encode(reference_answer(case, False)), case, False, True)
        check("visible-source-abstention", encode(reference_answer(case, False)), case, True, False)
        for role in ROLES:
            for index, alias in enumerate(case["truth"][role]["aliases"]):
                changed = deepcopy(answer)
                changed[role]["value"] = alias
                check(f"{role}-paraphrase-{index}", encode(changed), case, True, True)
            for name, value in (("negation", answer[role]["value"] + "ではない"), ("undeclared", "別の比較対象")):
                changed = deepcopy(answer)
                changed[role]["value"] = value
                check(f"{role}-{name}", encode(changed), case, True, False)
            for name, quote, source in (
                ("value-only-quote", answer[role]["value"], "r2"),
                ("wrong-source", answer[role]["evidence"][0]["quote"], "r1"),
                ("invented-quote", "この文は原文にはない。", "r2"),
            ):
                changed = deepcopy(answer)
                changed[role]["evidence"] = [{"source_id": source, "quote": quote}]
                check(f"{role}-{name}", encode(changed), case, True, False)
        changed = deepcopy(answer)
        changed["rejected_alternative"], changed["accepted_unit"] = changed["accepted_unit"], changed["rejected_alternative"]
        check("reversal", encode(changed), case, True, False)
        for status in STATUSES:
            if status != answer["prior_adoption"]["status"]:
                changed = deepcopy(answer)
                changed["prior_adoption"]["status"] = status
                check("wrong-history-" + status, encode(changed), case, True, False)
        changed = deepcopy(answer)
        changed["prior_adoption"]["evidence"] = deepcopy(answer["rejected_alternative"]["evidence"])
        check("correction-as-history", encode(changed), case, True, False)
        changed = {**answer, "message": "以前の採用は確実である。"}
        check("extra-unscored-prose", encode(changed), case, True, False)
        check("duplicate-key", raw[:-1] + ', "accepted_unit": null}', case, True, False)
        check("malformed", raw[:-5], case, True, False)
    return {"total": len(checks), "passed": sum(c["ok"] for c in checks), "checks": checks}


def experiment_config(cfg: dict) -> dict:
    unknown = set(cfg) - CONFIG_FIELDS - TOKEN_FIELDS - {"_config_path"}
    if unknown or not cfg.get("api_key_env"):
        raise ValueError("Grounded recall requires an environment-key profile with only supported config fields.")
    if resolve_llm_adapter(cfg) not in {OPENAI_CHAT_ADAPTER, OPENAI_RESPONSES_ADAPTER}:
        raise ValueError("Grounded recall requires an API profile.")
    # This explicit experimental cap replaces, not clamps to, a prior experiment's cap.
    safe = {key: value for key, value in cfg.items() if key in CONFIG_FIELDS}
    return config_with_output_token_limit(safe, CALL_OUTPUT_TOKENS)


def render_records(case: dict, condition: str) -> str:
    if condition == "none":
        return "(no source records)"
    original = "\n".join(f"[{r['source_id']}; turn {r['turn']}] {r['text']}" for r in case["records"])
    truth = case["truth"]
    if condition == "original":
        return original
    prior = {"established": "以前の採用は明示されている", "not_established": "以前の採用は未確認である",
             "refuted": "以前の非採用が明示されている"}[truth["prior_adoption"]["status"]]
    if condition == "prose":
        summary = (f"退けた比較案は「{truth['rejected_alternative']['value']}」であり、"
                   f"今回の比較単位は「{truth['accepted_unit']['value']}」である。"
                   f"比較は「{truth['comparison_boundary']['value']}」に限る。{prior}。")
    elif condition == "roles":
        summary = "\n".join(f"{role}: {truth[role]['value']}" for role in ROLES)
        summary += f"\nprior_adoption: {prior}"
    else:
        raise ValueError("Unknown representation.")
    return original + "\n\nSource-derived summary (not an original source record):\n" + summary


def runtime_hashes() -> dict:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(__file__).parent.glob("*.py"))}


def build_plan(suite: dict, configs: list[dict]) -> dict:
    validate_suite(suite)
    if len(configs) != 2 or len({cfg["profile"] for cfg in configs}) != 2:
        raise ValueError("Exactly two distinct model profiles are required.")
    configs = [experiment_config(cfg) for cfg in configs]
    offline = offline_checks(suite)
    if offline["passed"] != offline["total"]:
        raise ValueError("Offline assessor contract failed.")
    history = render_dialogue_context([
        {"kind": "utterance", "speaker": "A", "message": "次の記録確認に移ろう。"},
        {"kind": "utterance", "speaker": "B", "message": "利用できる記録に限って確認しよう。"},
    ], max_chars=700)
    hints = render_centerline_hints(analyze_centerline(QUERY, [{"role": "user", "content": history}]))
    cells = []
    for stage in STAGES:
        for index, case in enumerate(c for c in suite["cases"] if c["stage"] == stage):
            order = CONDITIONS[index % 4:] + CONDITIONS[:index % 4]
            for condition_index, condition in enumerate(order):
                context = render_records(case, condition)
                common = dict(thread_id="grounded-record-probe", user_text=QUERY, history=[], observations=[],
                              centerline_hints=hints, history_context=history)
                prompt = build_chat_prompt(recent_context=context, **common)
                for cfg in configs[(index + condition_index) % 2:] + configs[:(index + condition_index) % 2]:
                    cells.append({
                        "id": f"{stage}-{case['id']}-{condition}-{cfg['profile']}",
                        "stage": stage, "case_id": case["id"], "condition": condition, "profile": cfg["profile"],
                        "visible_source_ids": [r["source_id"] for r in case["records"]] if condition != "none" else [],
                        "context": context, "context_chars": len(context),
                        "prompt": prompt, "prompt_sha256": canonical_json_sha256(prompt),
                        "outside_memory_sha256": canonical_json_sha256(build_chat_prompt(recent_context="", **common)),
                        "input_tokens_estimated": estimate_token_count(SYSTEM + "\n" + prompt),
                    })
    return {
        "method": METHOD, "suite": suite, "suite_sha256": canonical_json_sha256(suite),
        "runtime_sha256": runtime_hashes(), "configs": configs, "offline": offline,
        "system_prompt": SYSTEM, "cells": cells,
        "budget": {"max_calls": MAX_CALLS, "per_call_output_tokens": CALL_OUTPUT_TOKENS,
                   "max_output_tokens": MAX_CALLS * CALL_OUTPUT_TOKENS, "retries": 0,
                   "input_tokens_estimated": sum(c["input_tokens_estimated"] for c in cells)},
        "gate": "All 16 calibration rows must pass the frozen grounded/abstention contract; then 32 confirmation calls.",
        "scope": "Six authored records, not full dialogues. Closed-alias citation contract, not a general semantic judge.",
    }


def prepare_grounded_recall(root: Path, cases_path: Path, profiles: list[str], out_dir: Path,
                            llm_config: str | None = None, max_api_calls: int = 48,
                            max_output_tokens: int = 48000, *,
                            plan_builder: Callable[[dict, list[dict]], dict] = build_plan) -> dict:
    if MAX_CALLS > max_api_calls or MAX_CALLS * CALL_OUTPUT_TOKENS > max_output_tokens:
        raise ValueError("Frozen suite exceeds the authorized call or output-token budget.")
    suite = strict_json(cases_path.read_text(encoding="utf-8"))
    plan = plan_builder(suite, [load_llm_config(root, llm_config, profile) for profile in profiles])
    envelope = {"plan_sha256": canonical_json_sha256(plan), "plan": plan}
    out_dir.mkdir(parents=True, exist_ok=False)
    write_manifest(out_dir / "plan.json", envelope)
    return envelope


def load_plan(root: Path, plan_dir: Path, plan_sha256: str, llm_config: str | None = None, *,
              plan_builder: Callable[[dict, list[dict]], dict] = build_plan) -> dict:
    envelope = strict_json((plan_dir / "plan.json").read_text(encoding="utf-8"))
    plan = envelope["plan"]
    if envelope["plan_sha256"] != plan_sha256 or canonical_json_sha256(plan) != plan_sha256:
        raise ValueError("Frozen plan digest mismatch.")
    configs = [load_llm_config(root, llm_config, cfg["profile"]) for cfg in plan["configs"]]
    if plan_builder(plan["suite"], configs) != plan:
        raise ValueError("Runtime, profile, prompts or offline gate differ from the frozen plan.")
    return plan


def audit_stage(plan: dict, plan_sha256: str, stage_dir: Path, stage: str) -> dict:
    """Recompute from complete raw receipts; never trust only a saved gate boolean."""
    result = strict_json((stage_dir / "result.json").read_text(encoding="utf-8"))
    planned = [cell for cell in plan["cells"] if cell["stage"] == stage]
    responses = [strict_json(line) for line in (stage_dir / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
    if (result["plan_sha256"] != plan_sha256 or result["stage"] != stage or result["method"] != plan["method"]
            or result["status"] != "complete" or result["attempted_calls"] != len(planned)
            or len(result["cells"]) != len(planned) or len(responses) != len(planned)):
        raise ValueError("Incomplete or mismatched stage receipt.")
    cases = {case["id"]: case for case in plan["suite"]["cases"]}
    assessments = []
    for cell, saved, response in zip(planned, result["cells"], responses):
        if (cell["id"] != saved["id"] or cell["id"] != response["id"]
                or response["prompt_sha256"] != cell["prompt_sha256"] or saved["status"] != "ok"
                or saved["response_sha256"] != canonical_json_sha256(response)):
            raise ValueError("Raw response identity or digest mismatch.")
        assessment = assess_answer(response["raw_output"], cases[cell["case_id"]], cell["condition"] != "none")
        if assessment != saved["assessment"]:
            raise ValueError("Saved assessment does not match raw response.")
        assessments.append(assessment)
    passed = all(a["passed"] for a in assessments)
    if passed != result["gate_passed"]:
        raise ValueError("Saved gate does not match re-assessment.")
    return {"passed": passed, "rows": len(assessments), "assessments": assessments,
            "result_sha256": canonical_json_sha256(result), "responses_sha256": canonical_json_sha256(responses)}


def run_grounded_recall(root: Path, plan_dir: Path, plan_sha256: str, stage: str,
                       llm_config: str | None = None, *,
                       plan_builder: Callable[[dict, list[dict]], dict] = build_plan) -> dict:
    if stage not in STAGES:
        raise ValueError("Unknown experiment stage.")
    plan = load_plan(root, plan_dir, plan_sha256, llm_config, plan_builder=plan_builder)
    gate = None
    if stage == "confirmation":
        gate = audit_stage(plan, plan_sha256, plan_dir / "calibration", "calibration")
        if not gate["passed"]:
            raise ValueError("Calibration failed: confirmation is blocked; no provider calls made.")
    configs = {cfg["profile"]: cfg for cfg in plan["configs"]}
    secrets = [api_key_from_config(cfg) for cfg in configs.values()]
    if not all(secrets):
        raise ValueError("Both API credentials must be available before stage execution.")
    out_dir = plan_dir / stage
    out_dir.mkdir(exist_ok=False)
    planned = [cell for cell in plan["cells"] if cell["stage"] == stage]
    cases = {case["id"]: case for case in plan["suite"]["cases"]}
    result = {
        "method": plan["method"], "stage": stage, "plan_sha256": plan_sha256, "started_at": now_iso(),
        "status": "running", "attempted_calls": 0, "gate_passed": False,
        "usage": empty_usage(), "calibration_gate": gate,
        "cells": [{"id": c["id"], "case_id": c["case_id"], "profile": c["profile"],
                   "condition": c["condition"], "status": "not-run"} for c in planned],
    }

    def save() -> None:
        result["updated_at"] = now_iso()
        write_manifest(out_dir / "result.json", result)

    save()
    for cell, saved in zip(planned, result["cells"]):
        saved["status"] = "running"
        result["attempted_calls"] += 1
        save()
        try:
            response = call_llm_result(configs[cell["profile"]], cell["prompt"], plan["system_prompt"])
            raw = response.get("content", "")
            if any(secret in raw for secret in secrets):
                raise ValueError("Response contained a credential; raw output not persisted.")
            receipt = {"id": cell["id"], "prompt_sha256": cell["prompt_sha256"],
                       "raw_output": raw, "llm": llm_trace(response)}
            append_jsonl(out_dir / "responses.jsonl", receipt)
            saved["response_sha256"] = canonical_json_sha256(receipt)
            add_usage(result["usage"], response.get("usage"))
            saved["assessment"] = assess_answer(raw, cases[cell["case_id"]], cell["condition"] != "none")
            saved["status"] = "ok"
        except (Exception, SystemExit, KeyboardInterrupt) as exc:
            message = str(exc)
            for secret in secrets:
                message = message.replace(secret, "[REDACTED]")
            saved.update(status="error", error=message)
            result["status"] = "error"
            save()
            return result
        save()
    result["status"] = "complete"
    result["gate_passed"] = all(cell["assessment"]["passed"] for cell in result["cells"])
    save()
    audit_stage(plan, plan_sha256, out_dir, stage)
    return result
