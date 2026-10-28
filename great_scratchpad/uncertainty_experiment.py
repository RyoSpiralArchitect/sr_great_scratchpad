"""Freeze, run and audit a bounded three-contract Mistral uncertainty pilot."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import tempfile
import time

from .chat import build_chat_prompt, llm_trace
from .dialogue import add_usage, append_jsonl, canonical_json_sha256, empty_usage
from .experiments import write_manifest
from .grounded_recall import runtime_hashes, strict_json
from .llm import api_key_from_config, call_llm_result, estimate_token_count
from .memory_task_design import build_conditions, source_text
from .reinjection import experiment_config, linked_condition
from .storage import load_llm_config, now_iso
from .uncertainty_contract import (
    CALIBRATION_CASES, METHOD, PILOT_CASES, SYSTEMS, VARIANTS,
    assess_answer, make_state_case, reference_state,
)

CONDITIONS = ("window-only", "linked-retrieve", "full-history")
SPEC = {"schema": METHOD, "calibration_seed": 26102840, "pilot_seed": 26102850,
        "calibration_cases": list(CALIBRATION_CASES), "pilot_cases": list(PILOT_CASES),
        "conditions": list(CONDITIONS), "variants": list(VARIANTS),
        "archive_distractors": 72, "history_chars": 700, "memory_chars": 1200,
        "retrieval_top": 4, "linked_top": 16, "linked_hops": 2, "linked_per_hop": 4,
        "per_call_output_tokens": 4096, "retries": 0,
        "calibration_gate": "12/12 contract_success from audited raw receipts",
        "failure_policy": "client errors and output limits fail once; continue remaining cells"}
SPEC_V21 = {**SPEC, "schema": "evidence-state-v2.1", "calibration_seed": 26102841, "pilot_seed": 26102851}
SYSTEMS_V21 = {**SYSTEMS, "evidence-state": SYSTEMS["evidence-state"] + """
Complete empty-source routing example (the request itself is not supplied):
{"status":"unknown","value":null,"evidence":[],
 "flags":{"urgent":"unobserved","hold":"unobserved"}}
The question still concerns routing even when no request record is supplied, so
flags must NOT be {} in that case. In a non-routing task with no relevant records:
{"status":"unknown","value":null,"evidence":[],"flags":{}}
"""}
METRICS = ("schema_ok", "value_correct", "epistemic_success", "contract_success", "recovered",
           "explicit_abstention", "unsupported_concrete", "unrecognized_value")


def request_params(cfg: dict) -> dict:
    return {"model": cfg["model"], "temperature": cfg["temperature"], "top_p": cfg["top_p"],
            "random_seed": cfg["seed"], "reasoning_effort": cfg["reasoning_effort"],
            "max_tokens": cfg["max_tokens"], "response_format": {"type": "json_object"}}


def build_plan(spec: dict, cfg: dict) -> dict:
    if spec not in (SPEC, SPEC_V21):
        raise ValueError("Frozen cases, contracts or budgets changed; version the protocol.")
    cfg = experiment_config(cfg)
    if cfg["reasoning_effort"] != "high" or cfg["max_tokens"] != 4096 or cfg.get("timeout") != 90:
        raise ValueError("Use the supported high-reasoning Mistral profile with a 90s timeout.")
    cases, cells = [], []
    systems = SYSTEMS if spec == SPEC else SYSTEMS_V21

    def add_cell(case: dict, row: dict, variant: str, stage: str) -> None:
        prompt, system = row["prompt"], systems[variant]
        cells.append({**row, "id": f"{case['id']}:{row['condition']}:{variant}",
                      "case_id": case["id"], "scenario": case["scenario"], "family": case["family"],
                      "variant": variant, "stage": stage, "system_sha256": canonical_json_sha256(system),
                      "request_sha256": canonical_json_sha256({"system": system, "prompt": prompt,
                                                               "params": request_params(cfg)}),
                      "input_utf8_bytes": len((system + "\n" + prompt).encode()),
                      "input_tokens_estimated": estimate_token_count(system + "\n" + prompt),
                      "expected": reference_state(case, row["visible_ids"])})

    for scenario in CALIBRATION_CASES:
        case = make_state_case(spec["calibration_seed"], scenario, "calibration", 18)
        cases.append(case)
        relevant = [r for r in case["records"] if r["kind"] != "distractor"]
        for empty in ((False, True) if scenario in {"hold-unknown", "complete-join"} else (False,)):
            context = "(no archive records)" if empty else "\n".join(source_text(r) for r in relevant)
            prompt = build_chat_prompt("memory-task-probe", case["query"], context, [], [], "", history_context="(empty)")
            visible = [] if empty else [r["id"] for r in relevant]
            add_cell(case, {"condition": "empty" if empty else "source", "prompt": prompt,
                            "prompt_sha256": canonical_json_sha256(prompt), "visible_ids": visible,
                            "context_chars": len(context)}, "evidence-state", "calibration")

    with tempfile.TemporaryDirectory(prefix="evidence-state-") as directory:
        for index, scenario in enumerate(PILOT_CASES):
            case = make_state_case(spec["pilot_seed"], scenario, "pilot", spec["archive_distractors"])
            cases.append(case)
            archive = Path(directory) / case["id"]
            rows = build_conditions(case, spec, archive)
            linked = linked_condition(case, spec, archive)
            selected = {r["condition"]: r for r in rows if r["condition"] in CONDITIONS}
            selected["linked-retrieve"] = linked
            window = selected["window-only"]
            if window["outside_memory_sha256"] != linked["outside_memory_sha256"]:
                raise ValueError("Window/linked inputs differ outside the archive field.")
            if linked["context_chars"] > spec["memory_chars"]:
                raise ValueError("Linked memory exceeded the whole-record budget.")
            for position, condition in enumerate(CONDITIONS):
                offset = (index + position) % len(VARIANTS)
                for variant in VARIANTS[offset:] + VARIANTS[:offset]:
                    add_cell(case, selected[condition], variant, "pilot")
    if len(cells) != 84 or len({c["id"] for c in cells}) != 84:
        raise ValueError("Missing or repeated planned cells.")
    return {"method": spec["schema"], "spec": spec, "config": cfg, "systems": systems,
            "cases": cases, "cells": cells, "runtime_sha256": runtime_hashes(),
            "budget": {"max_calls": len(cells), "max_output_tokens": len(cells) * cfg["max_tokens"],
                       "input_utf8_bytes": sum(c["input_utf8_bytes"] for c in cells),
                       "input_tokens_estimated": sum(c["input_tokens_estimated"] for c in cells), "retries": 0}}


def prepare(out_dir: Path, spec_path: Path, config_path: str, max_calls: int,
            max_output: int, max_input_bytes: int) -> dict:
    cfg = load_llm_config(Path("."), config_path, "mistral-large-4-high")
    plan = build_plan(strict_json(spec_path.read_text()), cfg)
    budget = plan["budget"]
    if (budget["max_calls"] > max_calls or budget["max_output_tokens"] > max_output
            or budget["input_utf8_bytes"] > max_input_bytes):
        raise ValueError("Full campaign exceeds the explicit resource limits.")
    plan["source_commit"] = subprocess.run(["git", "rev-parse", "HEAD"],
                                           cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                           text=True, check=True).stdout.strip()
    plan["limits"] = {"calls": max_calls, "output_tokens": max_output, "input_utf8_bytes": max_input_bytes}
    envelope = {"plan_sha256": canonical_json_sha256(plan), "plan": plan}
    out_dir.mkdir(parents=True, exist_ok=False)
    write_manifest(out_dir / "plan.json", envelope)
    return envelope


def load_plan(out_dir: Path, digest: str, config_path: str) -> dict:
    envelope = strict_json((out_dir / "plan.json").read_text())
    plan = envelope["plan"]
    if envelope["plan_sha256"] != digest or canonical_json_sha256(plan) != digest:
        raise ValueError("Frozen plan digest mismatch.")
    cfg = experiment_config(load_llm_config(Path("."), config_path, plan["config"]["profile"]))
    if cfg != plan["config"] or runtime_hashes() != plan["runtime_sha256"]:
        raise ValueError("Profile or runtime changed after plan freeze.")
    return plan


def receipt_status(receipt: dict, cfg: dict) -> str:
    if receipt["llm"] is None:
        return "client-error"
    if receipt["llm"].get("response_model") not in {"mistral-large-4", "mistral-large-4-0"}:
        return "model-mismatch"
    if receipt["request_params"] != request_params(cfg):
        return "request-mismatch"
    if receipt["finish_reason"] != "stop":
        return "output-limit" if receipt["finish_reason"] == "length" else "unexpected-finish"
    return "ok"


def assess_receipt(plan: dict, cell: dict, receipt: dict) -> dict:
    case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
    assessment = assess_answer(receipt["raw_output"] or "", case, cell["prompt"], cell["variant"])
    status = receipt_status(receipt, plan["config"])
    assessment["outcome_ok"] = status == "ok"
    if status != "ok":
        for key in ("value_correct", "epistemic_success", "contract_success", "recovered"):
            assessment[key] = False
    return assessment


def audit_stage(plan: dict, digest: str, out_dir: Path, stage: str) -> dict:
    directory = out_dir / stage
    result = strict_json((directory / "result.json").read_text())
    receipts = [strict_json(line) for line in (directory / "responses.jsonl").read_text().splitlines()]
    attempts = [strict_json(line) for line in (directory / "attempts.jsonl").read_text().splitlines()]
    planned = [c for c in plan["cells"] if c["stage"] == stage]
    if (result["plan_sha256"] != digest or result["stage"] != stage or result["status"] != "complete"
            or len(receipts) != len(planned) or len(attempts) != len(planned)
            or len(result["cells"]) != len(planned) or result["attempted_calls"] != len(planned)):
        raise ValueError("Incomplete stage; no missing slots or automatic reissue permitted.")
    usage, unavailable = empty_usage(), 0
    for cell, saved, receipt, attempt in zip(planned, result["cells"], receipts, attempts):
        if (any(r["id"] != cell["id"] for r in (saved, receipt, attempt))
                or receipt["request_sha256"] != cell["request_sha256"]
                or attempt["request_sha256"] != cell["request_sha256"]
                or attempt["plan_sha256"] != digest
                or saved["response_sha256"] != canonical_json_sha256(receipt)
                or saved["status"] != receipt_status(receipt, plan["config"])
                or saved["assessment"] != assess_receipt(plan, cell, receipt)):
            raise ValueError("Raw receipt, attempt, status or reassessment mismatch.")
        if receipt["llm"] and receipt["llm"].get("usage"):
            add_usage(usage, receipt["llm"]["usage"])
        else:
            unavailable += 1
    passed = all(c["assessment"]["contract_success"] for c in result["cells"])
    if (result["known_usage"] != usage or result["unavailable_usage_calls"] != unavailable
            or result["all_contracts_passed"] != passed):
        raise ValueError("Usage or success aggregate differs from raw receipts.")
    return result


def run(out_dir: Path, digest: str, config_path: str, stage: str) -> dict:
    if stage not in {"calibration", "pilot"}:
        raise ValueError("Unknown stage.")
    plan = load_plan(out_dir, digest, config_path)
    if stage == "pilot" and not audit_stage(plan, digest, out_dir, "calibration")["all_contracts_passed"]:
        raise ValueError("Calibration gate failed; no pilot calls made.")
    key = api_key_from_config(plan["config"])
    if not key:
        raise ValueError("Mistral credential unavailable.")
    directory = out_dir / stage
    directory.mkdir(exist_ok=False)
    planned = [c for c in plan["cells"] if c["stage"] == stage]
    result = {"method": plan["method"], "stage": stage, "plan_sha256": digest, "started_at": now_iso(),
              "status": "running", "attempted_calls": 0, "all_contracts_passed": False,
              "known_usage": empty_usage(), "unavailable_usage_calls": 0, "cells": []}

    def save() -> None:
        result["updated_at"] = now_iso()
        write_manifest(directory / "result.json", result)

    save()
    for cell in planned:
        attempt = {"id": cell["id"], "request_sha256": cell["request_sha256"],
                   "plan_sha256": digest, "started_at": now_iso()}
        append_jsonl(directory / "attempts.jsonl", attempt)
        result["attempted_calls"] += 1
        save()
        started = time.perf_counter()
        receipt = {"id": cell["id"], "request_sha256": cell["request_sha256"],
                   "raw_output": None, "llm": None, "finish_reason": None,
                   "response_id": None, "request_params": None, "client_error": None}
        try:
            response = call_llm_result(plan["config"], cell["prompt"], plan["systems"][cell["variant"]])
            if key in json.dumps(response, ensure_ascii=False) or not isinstance(response.get("content"), str):
                raise ValueError("Unsafe or invalid provider response; content not persisted.")
            receipt.update(raw_output=response["content"], llm=llm_trace(response),
                           finish_reason=response.get("finish_reason"), response_id=response.get("response_id"),
                           request_params=response.get("request_params"))
        except (Exception, SystemExit) as exc:
            receipt["client_error"] = {"type": type(exc).__name__, "message": str(exc).replace(key, "[REDACTED]")[:500]}
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        append_jsonl(directory / "responses.jsonl", receipt)
        status = receipt_status(receipt, plan["config"])
        assessment = assess_receipt(plan, cell, receipt)
        result["cells"].append({"id": cell["id"], "status": status,
                                "response_sha256": canonical_json_sha256(receipt), "assessment": assessment})
        if receipt["llm"] and receipt["llm"].get("usage"):
            add_usage(result["known_usage"], receipt["llm"]["usage"])
        else:
            result["unavailable_usage_calls"] += 1
        save()
        print(f"{stage} {result['attempted_calls']}/{len(planned)} {cell['scenario']} "
              f"{cell['condition']} {cell['variant']}: {status} success={assessment['contract_success']}", flush=True)
        if status in {"model-mismatch", "request-mismatch"}:
            result["status"] = "stopped-identity-mismatch"
            save()
            return result
    result["status"] = "complete"
    result["all_contracts_passed"] = all(c["assessment"]["contract_success"] for c in result["cells"])
    save()
    return audit_stage(plan, digest, out_dir, stage)


def summarize(plan: dict, result: dict) -> dict:
    saved = {c["id"]: c for c in result["cells"]}
    cells = [c for c in plan["cells"] if c["stage"] == "pilot"]
    groups = []
    for condition in CONDITIONS:
        for variant in VARIANTS:
            rows = [c for c in cells if c["condition"] == condition and c["variant"] == variant]
            counts = Counter({key: 0 for key in METRICS})
            counts.update({"world_known": 0, "world_unknown": 0, "visible_known": 0,
                           "grounded_unknown": 0, "unknown_with_evidence": 0,
                           "flags_faithful": 0, "flag_cases": 0})
            statuses = Counter()
            for cell in rows:
                s, a = saved[cell["id"]], saved[cell["id"]]["assessment"]
                case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
                for metric in METRICS:
                    counts[metric] += bool(a[metric])
                counts["world_known" if case["truth"]["status"] == "known" else "world_unknown"] += 1
                counts["visible_known"] += a["expected"]["status"] == "known"
                counts["grounded_unknown"] += a["epistemic_success"] and a["expected"]["status"] == "unknown"
                counts["unknown_with_evidence"] += (a["epistemic_success"] and a["expected"]["status"] == "unknown"
                                                    and bool(a["expected"]["support"]))
                counts["flag_cases"] += a["flags_faithful"] is not None
                counts["flags_faithful"] += a["flags_faithful"] is True
                statuses[s["status"]] += 1
            groups.append({"condition": condition, "variant": variant, "cases": len(rows),
                           "counts": dict(counts), "statuses": dict(statuses)})
    contrasts = []
    for condition in CONDITIONS:
        for control, treatment in (("legacy", "guarded-legacy"), ("guarded-legacy", "evidence-state")):
            outcomes = Counter()
            for scenario in PILOT_CASES:
                pair = {c["variant"]: saved[c["id"]]["assessment"]["epistemic_success"]
                        for c in cells if c["scenario"] == scenario and c["condition"] == condition}
                a, b = pair[control], pair[treatment]
                outcomes["both" if a and b else "treatment_only" if b else "control_only" if a else "neither"] += 1
            contrasts.append({"condition": condition, "control": control, "treatment": treatment,
                              "paired_common_diagnostic": dict(outcomes)})
    return {"method": plan["method"], "scope": "Eight authored cases; paired contracts, not independent replications or a retrieval efficacy estimate.",
            "groups": groups, "contrasts": contrasts, "known_usage": result["known_usage"],
            "unavailable_usage_calls": result["unavailable_usage_calls"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--stage", choices=("calibration", "pilot"))
    parser.add_argument("--spec", type=Path, default=Path("scenarios/uncertainty_contract_v2.json"))
    parser.add_argument("--llm-config", default="examples/mistral-large-4.json")
    parser.add_argument("--max-calls", type=int, default=84)
    parser.add_argument("--max-output-tokens", type=int, default=344064)
    parser.add_argument("--max-input-bytes", type=int, default=2000000)
    args = parser.parse_args()
    if args.command == "prepare":
        envelope = prepare(args.out_dir, args.spec, args.llm_config, args.max_calls,
                           args.max_output_tokens, args.max_input_bytes)
        print(json.dumps({"plan_sha256": envelope["plan_sha256"], "budget": envelope["plan"]["budget"]}))
    else:
        if not args.plan_sha256 or args.command == "run" and not args.stage:
            parser.error("frozen digest and (for run) stage are required")
        if args.command == "run":
            result = run(args.out_dir, args.plan_sha256, args.llm_config, args.stage)
            print(json.dumps({k: v for k, v in result.items() if k != "cells"}))
        else:
            plan = load_plan(args.out_dir, args.plan_sha256, args.llm_config)
            calibration = audit_stage(plan, args.plan_sha256, args.out_dir, "calibration")
            pilot = audit_stage(plan, args.plan_sha256, args.out_dir, "pilot")
            if not calibration["all_contracts_passed"]:
                raise ValueError("Calibration did not license this pilot.")
            summary = summarize(plan, pilot)
            summary["calibration_usage"] = calibration["known_usage"]
            write_manifest(args.out_dir / "summary.json", summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
