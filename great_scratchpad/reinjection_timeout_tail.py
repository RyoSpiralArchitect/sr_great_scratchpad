"""Finish unattempted cells once; missing client responses remain explicit failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from .chat import llm_trace
from .dialogue import add_usage, append_jsonl, canonical_json_sha256, empty_usage
from .experiments import write_manifest
from .grounded_recall import runtime_hashes, strict_json
from .llm import api_key_from_config, call_llm_result
from .reinjection import experiment_config, summarize_pilot
from .reinjection_continuation import file_hash, inspect_source, read_json, received_assessment
from .storage import load_llm_config, now_iso

METHOD = "memory-reinjection-exploratory-client-failures-v1"
PARENT_FILES = ("plan.json", "pilot/result.json", "pilot/responses.jsonl")


def client_receipt(cell: dict, error: str, response_received: bool = False) -> dict:
    return {"id": cell["id"], "prompt_sha256": cell["prompt_sha256"], "receipt_kind": "client_error",
            "response_received": response_received, "raw_output": None, "usage": None, "error": error}


def assessment(plan: dict, cell: dict, receipt: dict) -> dict:
    if receipt.get("receipt_kind") == "client_error":
        if receipt.get("raw_output") is not None or type(receipt.get("response_received")) is not bool or receipt.get("usage") is not None:
            raise ValueError("A client error must not invent model text or usage.")
        return {"schema_ok": False, "answer_correct": None, "grounded_success": False,
                "safe_abstention": None, "recovered": False, "resource_failure": "client_error",
                "errors": ["no_provider_response"]}
    return received_assessment(plan, cell, receipt)


def inspect_parent(source: Path, digest: str) -> tuple[dict, dict, list[dict], dict]:
    env = read_json(source / "plan.json")
    parent = env["plan"]
    if env["plan_sha256"] != digest or canonical_json_sha256(parent) != digest:
        raise ValueError("Parent continuation digest mismatch.")
    current = runtime_hashes()
    if any(current.get(k) != v for k, v in parent["runtime_sha256"].items()):
        raise ValueError("A parent runtime module changed.")
    original_source = Path(parent["source_dir"])
    if {k: file_hash(original_source / k) for k in parent["source_files_sha256"]} != parent["source_files_sha256"]:
        raise ValueError("Original artifacts changed.")
    original, _, old_receipts = inspect_source(original_source, parent["source_plan_sha256"])
    if original != parent["original_plan"]:
        raise ValueError("Original generation plan drifted.")
    result = read_json(source / "pilot/result.json")
    raw = (source / "pilot/responses.jsonl").read_bytes()
    receipts = [strict_json(s) for s in raw.decode("utf-8").splitlines()]
    cells = [c for c in original["cells"] if c["stage"] == "pilot"]
    count = len(receipts)
    if (result["status"] != "error" or result["plan_sha256"] != digest
            or result["attempted_calls"] != count + 1 or not count < len(cells)
            or len(result["cells"]) != len(cells)
            or not raw.startswith((original_source / "pilot/responses.jsonl").read_bytes())):
        raise ValueError("Require a received prefix followed by exactly one unreceived attempt.")
    usage = empty_usage()
    for index, (cell, saved, receipt) in enumerate(zip(cells, result["cells"], receipts)):
        if (saved["status"] != "ok" or saved["id"] != cell["id"] or receipt["id"] != cell["id"]
                or receipt["prompt_sha256"] != cell["prompt_sha256"]
                or saved["response_sha256"] != canonical_json_sha256(receipt)
                or saved.get("imported") != (index < len(old_receipts))
                or saved["assessment"] != received_assessment(original, cell, receipt)):
            raise ValueError("Parent received-prefix audit failed.")
        add_usage(usage, receipt["llm"].get("usage"))
    failed = result["cells"][count]
    if (usage != result["usage"] or failed["status"] != "error" or failed["id"] != cells[count]["id"]
            or result["new_attempted_calls"] != count + 1 - len(old_receipts)
            or "timed out" not in failed.get("error", "").lower()
            or any(c["status"] != "not-run" for c in result["cells"][count + 1:])):
        raise ValueError("Parent missing-response or usage ledger mismatch.")
    return original, result, receipts, client_receipt(cells[count], failed["error"])


def prepare(source: Path, source_digest: str, out_dir: Path, max_calls: int, max_output: int) -> dict:
    source = source.resolve()
    original, result, receipts, lost = inspect_parent(source, source_digest)
    remaining = len(result["cells"]) - result["attempted_calls"]
    if remaining > max_calls or remaining * original["config"]["max_tokens"] > max_output:
        raise ValueError("Unattempted tail exceeds the remaining campaign allowance.")
    plan = {"method": METHOD, "source_dir": str(source), "source_plan_sha256": source_digest,
            "source_files_sha256": {k: file_hash(source / k) for k in PARENT_FILES},
            "original_plan": original, "received_prefix": len(receipts), "client_error_receipt": lost,
            "runtime_sha256": runtime_hashes(),
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "budget": {"new_calls": remaining, "max_new_calls": max_calls, "max_new_output_tokens": max_output},
            "policy": "Exploratory client-error amendment. Never repeat an attempted request; unavailable output/usage stays unknown."}
    env = {"plan_sha256": canonical_json_sha256(plan), "plan": plan}
    out_dir.mkdir(parents=True, exist_ok=False)
    write_manifest(out_dir / "plan.json", env)
    return env


def load(out_dir: Path, digest: str, config: str) -> tuple[dict, list[dict]]:
    env = read_json(out_dir / "plan.json")
    plan = env["plan"]
    if env["plan_sha256"] != digest or canonical_json_sha256(plan) != digest or runtime_hashes() != plan["runtime_sha256"]:
        raise ValueError("Tail plan or runtime drifted.")
    source = Path(plan["source_dir"])
    if {k: file_hash(source / k) for k in PARENT_FILES} != plan["source_files_sha256"]:
        raise ValueError("Parent continuation artifacts changed.")
    original, _, receipts, lost = inspect_parent(source, plan["source_plan_sha256"])
    cfg = experiment_config(load_llm_config(Path("."), config, original["config"]["profile"]))
    if original != plan["original_plan"] or cfg != original["config"] or lost != plan["client_error_receipt"]:
        raise ValueError("Tail inputs, provider or missing-response record changed.")
    return plan, receipts


def run(out_dir: Path, digest: str, config: str) -> dict:
    plan, imported = load(out_dir, digest, config)
    original = plan["original_plan"]
    key = api_key_from_config(original["config"])
    if not key:
        raise ValueError("Mistral credential unavailable.")
    directory = out_dir / "pilot"
    directory.mkdir(exist_ok=False)
    shutil.copyfile(Path(plan["source_dir"]) / "pilot/responses.jsonl", directory / "responses.jsonl")
    append_jsonl(directory / "responses.jsonl", plan["client_error_receipt"])
    imported = [*imported, plan["client_error_receipt"]]
    cells = [c for c in original["cells"] if c["stage"] == "pilot"]
    rows = [{"id": c["id"], "status": "not-run"} for c in cells]
    result = {"method": METHOD, "plan_sha256": digest, "status": "running", "started_at": now_iso(),
              "attempted_calls": len(imported), "new_attempted_calls": 0,
              "known_usage": empty_usage(), "unavailable_usage_calls": 0, "cells": rows}

    def observe(cell: dict, saved: dict, receipt: dict, imported: bool) -> None:
        saved.update(status="ok", imported=imported, response_sha256=canonical_json_sha256(receipt),
                     assessment=assessment(original, cell, receipt))
        if receipt.get("receipt_kind") == "client_error":
            result["unavailable_usage_calls"] += 1
        else:
            add_usage(result["known_usage"], receipt["llm"].get("usage"))

    def save() -> None:
        result["updated_at"] = now_iso()
        write_manifest(directory / "result.json", result)

    for cell, saved, receipt in zip(cells, rows, imported):
        observe(cell, saved, receipt, True)
    save()
    for cell, saved in zip(cells[len(imported):], rows[len(imported):]):
        saved["status"] = "running"
        result["attempted_calls"] += 1
        result["new_attempted_calls"] += 1
        save()
        response_received = False
        try:
            response = call_llm_result(original["config"], cell["prompt"], original["system_prompt"])
            response_received = True
            raw = response.get("content", "")
            if not isinstance(raw, str) or key in raw:
                raise ValueError("Unexpected or credential-containing output; not saved.")
            receipt = {"id": cell["id"], "prompt_sha256": cell["prompt_sha256"], "raw_output": raw,
                       "llm": llm_trace(response), "finish_reason": response.get("finish_reason", ""),
                       "response_id": response.get("response_id", ""), "request_params": response.get("request_params", {})}
        except (Exception, SystemExit) as exc:
            receipt = client_receipt(cell, str(exc).replace(key, "[REDACTED]"), response_received)
        append_jsonl(directory / "responses.jsonl", receipt)
        observe(cell, saved, receipt, False)
        save()
    result["status"] = "complete"
    save()
    return audit(out_dir, digest, config)


def audit(out_dir: Path, digest: str, config: str) -> dict:
    plan, imported = load(out_dir, digest, config)
    result = read_json(out_dir / "pilot/result.json")
    data = (out_dir / "pilot/responses.jsonl").read_bytes()
    receipts = [strict_json(s) for s in data.decode("utf-8").splitlines()]
    cells = [c for c in plan["original_plan"]["cells"] if c["stage"] == "pilot"]
    if (result["status"] != "complete" or result["plan_sha256"] != digest
            or result["attempted_calls"] != len(cells) or len(receipts) != len(cells)
            or len(result["cells"]) != len(cells)
            or result["new_attempted_calls"] != plan["budget"]["new_calls"]
            or not data.startswith((Path(plan["source_dir"]) / "pilot/responses.jsonl").read_bytes())
            or receipts[len(imported)] != plan["client_error_receipt"]):
        raise ValueError("Incomplete tail or changed imported bytes/client-failure event.")
    usage, missing = empty_usage(), 0
    for index, (cell, saved, receipt) in enumerate(zip(cells, result["cells"], receipts)):
        if (saved["id"] != cell["id"] or receipt["id"] != cell["id"] or saved["status"] != "ok"
                or receipt["prompt_sha256"] != cell["prompt_sha256"]
                or saved.get("imported") != (index <= len(imported))
                or saved["response_sha256"] != canonical_json_sha256(receipt)
                or saved["assessment"] != assessment(plan["original_plan"], cell, receipt)):
            raise ValueError("Tail receipt or reassessment mismatch.")
        if receipt.get("receipt_kind") == "client_error":
            missing += 1
        else:
            add_usage(usage, receipt["llm"].get("usage"))
    if usage != result["known_usage"] or missing != result["unavailable_usage_calls"]:
        raise ValueError("Unknown usage was hidden or known usage drifted.")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--source-plan-sha256")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--llm-config", default="examples/mistral-large-4.json")
    parser.add_argument("--max-new-calls", type=int, default=11)
    parser.add_argument("--max-new-output-tokens", type=int, default=45056)
    args = parser.parse_args()
    if args.command == "prepare":
        if not args.source_dir or not args.source_plan_sha256:
            parser.error("source directory and digest required")
        env = prepare(args.source_dir, args.source_plan_sha256, args.out_dir, args.max_new_calls, args.max_new_output_tokens)
        print(f"plan_sha256={env['plan_sha256']} new_calls={env['plan']['budget']['new_calls']}")
    elif args.command == "run":
        result = run(args.out_dir, args.plan_sha256, args.llm_config)
        print(f"status={result['status']} total_cells={result['attempted_calls']} new_calls={result['new_attempted_calls']} missing_usage={result['unavailable_usage_calls']}")
    else:
        result = audit(args.out_dir, args.plan_sha256, args.llm_config)
        plan, _ = load(args.out_dir, args.plan_sha256, args.llm_config)
        summary = summarize_pilot(plan["original_plan"], {**result, "usage": result["known_usage"]})
        summary.update(method=METHOD, inference="exploratory end-to-end success; stopping rules amended after observed failures",
                       usage_scope="received responses only", unavailable_usage_calls=result["unavailable_usage_calls"])
        write_manifest(args.out_dir / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
