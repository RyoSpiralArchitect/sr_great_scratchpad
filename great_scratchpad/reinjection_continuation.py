"""Exploratory continuation of a frozen pilot stopped by a received length limit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from .chat import llm_trace
from .dialogue import add_usage, append_jsonl, canonical_json_sha256, empty_usage
from .experiments import write_manifest
from .grounded_recall import runtime_hashes, strict_json
from .llm import api_key_from_config, call_llm_result
from .reinjection import assess_cell, audit_stage, experiment_config, summarize_pilot
from .storage import load_llm_config, now_iso

METHOD = "memory-reinjection-exploratory-continuation-v1"
SOURCE_FILES = ("plan.json", "calibration/result.json", "calibration/responses.jsonl",
                "pilot/result.json", "pilot/responses.jsonl")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return strict_json(path.read_text(encoding="utf-8"))


def received_assessment(plan: dict, cell: dict, receipt: dict) -> dict:
    if receipt["llm"].get("response_model") not in {"mistral-large-4", "mistral-large-4-0"}:
        raise ValueError("Unexpected model in receipt.")
    reason = receipt.get("finish_reason")
    if reason not in {"stop", "length"}:
        raise ValueError("Continuation requires an observed stop or length response.")
    assessment = assess_cell(plan, cell, receipt["raw_output"])
    if reason == "length":
        assessment.update(grounded_success=False, recovered=False, resource_failure="output_limit")
    return assessment


def inspect_source(source: Path, digest: str) -> tuple[dict, dict, list[dict]]:
    envelope = read_json(source / "plan.json")
    plan = envelope["plan"]
    if envelope["plan_sha256"] != digest or canonical_json_sha256(plan) != digest:
        raise ValueError("Source plan digest mismatch.")
    current = runtime_hashes()
    if any(current.get(name) != value for name, value in plan["runtime_sha256"].items()):
        raise ValueError("An original generation/scoring module changed.")
    if not audit_stage(plan, digest, source, "calibration")["gate_passed"]:
        raise ValueError("Original calibration gate is not valid.")
    result = read_json(source / "pilot/result.json")
    receipts = [strict_json(line) for line in (source / "pilot/responses.jsonl").read_text().splitlines()]
    planned = [c for c in plan["cells"] if c["stage"] == "pilot"]
    count = len(receipts)
    if (result["status"] != "error" or result["plan_sha256"] != digest
            or not 0 < count < len(planned) or result["attempted_calls"] != count
            or len(result["cells"]) != len(planned)
            or receipts[-1].get("finish_reason") != "length"):
        raise ValueError("Require a complete received prefix ending at a length-limit stop.")
    usage = empty_usage()
    for index, (cell, saved, receipt) in enumerate(zip(planned, result["cells"], receipts)):
        expected_status = "error" if index == count - 1 else "ok"
        if (saved["id"] != cell["id"] or receipt["id"] != cell["id"]
                or saved["status"] != expected_status
                or receipt["prompt_sha256"] != cell["prompt_sha256"]
                or canonical_json_sha256(receipt) != saved["response_sha256"]):
            raise ValueError("Source receipt prefix is not complete and ordered.")
        received_assessment(plan, cell, receipt)
        if index < count - 1 and saved["assessment"] != assess_cell(plan, cell, receipt["raw_output"]):
            raise ValueError("Source assessment differs from its raw receipt.")
        add_usage(usage, receipt["llm"].get("usage"))
    if usage != result["usage"] or any(c["status"] != "not-run" for c in result["cells"][count:]):
        raise ValueError("Source usage or remaining-attempt ledger mismatch.")
    return plan, result, receipts


def prepare(source: Path, source_digest: str, out_dir: Path, max_calls: int, max_output: int) -> dict:
    source = source.resolve()
    original, result, receipts = inspect_source(source, source_digest)
    remaining = len(result["cells"]) - len(receipts)
    if remaining > max_calls or remaining * original["config"]["max_tokens"] > max_output:
        raise ValueError("Continuation exceeds the remaining call/output allowance.")
    plan = {"method": METHOD, "source_dir": str(source), "source_plan_sha256": source_digest,
            "source_files_sha256": {name: file_hash(source / name) for name in SOURCE_FILES},
            "original_plan": original, "imported_responses": len(receipts),
            "runtime_sha256": runtime_hashes(),
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "budget": {"new_calls": remaining, "max_new_calls": max_calls,
                       "max_new_output_tokens": max_output},
            "policy": "Post-hoc exploratory amendment: received length limits count as failures; never regenerate a received cell."}
    envelope = {"plan_sha256": canonical_json_sha256(plan), "plan": plan}
    out_dir.mkdir(parents=True, exist_ok=False)
    write_manifest(out_dir / "plan.json", envelope)
    return envelope


def load(out_dir: Path, digest: str, config_path: str) -> tuple[dict, dict, list[dict]]:
    envelope = read_json(out_dir / "plan.json")
    plan = envelope["plan"]
    if envelope["plan_sha256"] != digest or canonical_json_sha256(plan) != digest:
        raise ValueError("Continuation plan digest mismatch.")
    if runtime_hashes() != plan["runtime_sha256"]:
        raise ValueError("Continuation runtime changed after freeze.")
    source = Path(plan["source_dir"])
    if {name: file_hash(source / name) for name in SOURCE_FILES} != plan["source_files_sha256"]:
        raise ValueError("Original artifacts changed after continuation freeze.")
    original, _, receipts = inspect_source(source, plan["source_plan_sha256"])
    cfg = experiment_config(load_llm_config(Path("."), config_path, original["config"]["profile"]))
    if original != plan["original_plan"] or cfg != original["config"] or len(receipts) != plan["imported_responses"]:
        raise ValueError("Continuation generation identity drifted.")
    return plan, original, receipts


def run(out_dir: Path, digest: str, config_path: str) -> dict:
    plan, original, imported = load(out_dir, digest, config_path)
    key = api_key_from_config(original["config"])
    if not key:
        raise ValueError("Mistral credential unavailable.")
    directory = out_dir / "pilot"
    directory.mkdir(exist_ok=False)
    shutil.copyfile(Path(plan["source_dir"]) / "pilot/responses.jsonl", directory / "responses.jsonl")
    planned = [c for c in original["cells"] if c["stage"] == "pilot"]
    rows = [{"id": c["id"], "status": "not-run"} for c in planned]
    result = {"method": METHOD, "plan_sha256": digest, "status": "running", "started_at": now_iso(),
              "attempted_calls": len(imported), "new_attempted_calls": 0, "imported_responses": len(imported),
              "usage": empty_usage(), "cells": rows}
    for cell, saved, receipt in zip(planned, rows, imported):
        saved.update(status="ok", imported=True, response_sha256=canonical_json_sha256(receipt),
                     assessment=received_assessment(original, cell, receipt))
        add_usage(result["usage"], receipt["llm"].get("usage"))

    def save() -> None:
        result["updated_at"] = now_iso()
        write_manifest(directory / "result.json", result)

    save()
    for cell, saved in zip(planned[len(imported):], rows[len(imported):]):
        saved["status"] = "running"
        result["attempted_calls"] += 1
        result["new_attempted_calls"] += 1
        save()
        try:
            response = call_llm_result(original["config"], cell["prompt"], original["system_prompt"])
            raw = response.get("content", "")
            if not isinstance(raw, str) or key in raw:
                raise ValueError("Unexpected or credential-containing response; output not saved.")
            receipt = {"id": cell["id"], "prompt_sha256": cell["prompt_sha256"], "raw_output": raw,
                       "llm": llm_trace(response), "finish_reason": response.get("finish_reason", ""),
                       "response_id": response.get("response_id", ""), "request_params": response.get("request_params", {})}
            append_jsonl(directory / "responses.jsonl", receipt)
            saved["response_sha256"] = canonical_json_sha256(receipt)
            add_usage(result["usage"], response.get("usage"))
            saved.update(status="ok", imported=False, assessment=received_assessment(original, cell, receipt))
        except (Exception, SystemExit, KeyboardInterrupt) as exc:
            saved.update(status="error", error=str(exc).replace(key, "[REDACTED]"))
            result["status"] = "error"
            save()
            return result
        save()
    result["status"] = "complete"
    save()
    return audit(out_dir, digest, config_path)


def audit(out_dir: Path, digest: str, config_path: str) -> dict:
    plan, original, imported = load(out_dir, digest, config_path)
    result = read_json(out_dir / "pilot/result.json")
    data = (out_dir / "pilot/responses.jsonl").read_bytes()
    prefix = (Path(plan["source_dir"]) / "pilot/responses.jsonl").read_bytes()
    receipts = [strict_json(line) for line in data.decode("utf-8").splitlines()]
    planned = [c for c in original["cells"] if c["stage"] == "pilot"]
    if (result["status"] != "complete" or result["plan_sha256"] != digest or not data.startswith(prefix)
            or result["attempted_calls"] != len(planned) or len(receipts) != len(planned)
            or len(result["cells"]) != len(planned)
            or result["new_attempted_calls"] != len(planned) - len(imported)):
        raise ValueError("Incomplete continuation or changed original receipt bytes.")
    usage = empty_usage()
    for index, (cell, saved, receipt) in enumerate(zip(planned, result["cells"], receipts)):
        if (saved["status"] != "ok" or saved["id"] != cell["id"] or receipt["id"] != cell["id"]
                or saved.get("imported") != (index < len(imported))
                or receipt["prompt_sha256"] != cell["prompt_sha256"]
                or canonical_json_sha256(receipt) != saved["response_sha256"]
                or received_assessment(original, cell, receipt) != saved["assessment"]):
            raise ValueError("Continuation receipt identity or assessment mismatch.")
        add_usage(usage, receipt["llm"].get("usage"))
    if usage != result["usage"]:
        raise ValueError("Continuation usage differs from raw receipts.")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--source-plan-sha256")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--llm-config", default="examples/mistral-large-4.json")
    parser.add_argument("--max-new-calls", type=int, default=104)
    parser.add_argument("--max-new-output-tokens", type=int, default=425984)
    args = parser.parse_args()
    if args.command == "prepare":
        if not args.source_dir or not args.source_plan_sha256:
            parser.error("prepare requires the source directory and digest")
        envelope = prepare(args.source_dir, args.source_plan_sha256, args.out_dir,
                           args.max_new_calls, args.max_new_output_tokens)
        print(f"plan_sha256={envelope['plan_sha256']} new_calls={envelope['plan']['budget']['new_calls']}")
        return
    if not args.plan_sha256:
        parser.error("run/report requires the continuation digest")
    if args.command == "run":
        result = run(args.out_dir, args.plan_sha256, args.llm_config)
        print(f"status={result['status']} new_calls={result['new_attempted_calls']} total_cells={result['attempted_calls']}")
        if result["status"] != "complete":
            raise SystemExit(1)
    else:
        result = audit(args.out_dir, args.plan_sha256, args.llm_config)
        _, original, _ = load(args.out_dir, args.plan_sha256, args.llm_config)
        summary = summarize_pilot(original, result)
        summary.update(method=METHOD, inference="exploratory; stopping rule amended after a length-limit response")
        write_manifest(args.out_dir / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
