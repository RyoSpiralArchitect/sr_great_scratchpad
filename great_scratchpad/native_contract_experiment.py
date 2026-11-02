"""Bounded paired JSON-mode/native-schema calibration on fresh public inputs."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import time

from .dialogue import add_usage, append_jsonl, canonical_json_sha256, empty_usage
from .experiments import write_manifest
from .grounded_recall import runtime_hashes, strict_json
from .llm import LLMResponseError, api_key_from_config, call_llm_result, estimate_token_count
from .luna_uncertainty import CONFIG, config, failure_tags, paired_counts, record_usage, sha
from .memory_task_design import source_text
from .storage import load_llm_config, now_iso
from .structured_tasks import (
    SYSTEM, TaskContractError, call_structured_task, native_task_format, native_task_schema, validate_task_answer,
    validate_task_input,
)
from .uncertainty_contract import CALIBRATION_CASES, assess_answer, make_state_case, reference_state

REPO = Path(__file__).resolve().parents[1]
METHOD = "luna-native-contract-v1"
ARMS = ("native", "json-mode")
METRICS = ("provider_completed", "schema_ok", "caller_contract_ok", "value_correct", "flags_faithful",
           "citations_visible", "citations_relevant", "proof_covered", "epistemic_success", "contract_success")
SPEC = {"schema": METHOD, "model": "gpt-6-luna", "fresh_seed": 26110311,
        "arms": list(ARMS), "source_scenarios": list(CALIBRATION_CASES),
        "empty_scenarios": ["hold-unknown", "approved-update", "complete-join"],
        "partial_scenarios": ["urgent-enabled", "complete-join"],
        "max_calls": 30, "per_call_output_tokens": 4096, "retries": 0, "pilot_calls": 0,
        "future_gate": "all 15 views pass both caller and semantic contracts; no retrieval pilot authorized"}
SPEC_V11 = {**SPEC, "schema": "luna-native-contract-v11", "fresh_seed": 26110312}
PARENT = {"directory": "luna-uncertainty-v3-20261103",
          "plan_sha256": "05c71e2f08e61e2d005868342b2c95334af68eeab5d608a26cdad92c09fc03fe",
          "files": {
              "plan.json": "22c81743f602924692a0e6e13e3c19028b919835b3246834d191000ec6b0f131",
              "execution/result.json": "6718014513ebf87b524a273ea5924ed514a66290a59a185ccb973fbf45c9bd1f",
              "execution/attempts.jsonl": "e9655e7184abf99eee4c62ac3b046891817ae5ec4c221fa0133418b2e92f7561",
              "execution/responses.jsonl": "ae86a11dfcb52fda2e6f4ff72bd62e669c97675f0ed8a82774c51503e315109a",
              "summary.json": "5e6744eba927e4fb095a1a96fd693e4ae4e12533e5734d9446b05cd3ceb077e6",
              "audit.json": "3f0d02b3b1dfba99c53acc85bae2adeb8a4ee9a0c141b24eb601848051016805",
          }}
STOPPED_V1 = {"directory": "luna-native-contract-v1-20261103",
              "plan_sha256": "275c4aeb1167950e952781c1ff5c08d0a53620478260bcf2f3fcb5abdd787a74",
              "files": {
                  "plan.json": "fbe484690eb4dd45efb03998866409bcab5bf5d1e75531af47897192e67fc191",
                  "execution/result.json": "8227a8609f666395a1bf17451654a7118ed91be23b4d78d3433bf63f39664a4f",
                  "execution/attempts.jsonl": "39dc28d21b787ca9b384c25c63f782f670b944d272b30b1c891e65d865cab9ab",
                  "execution/responses.jsonl": "29c2fbb563be7f8156310cf86a4a7ac52d687700d900db9e2c1292cc30281723",
                  "summary.json": "855fef019e3f7fc72ea17a14f880fb57f126359369a6d71f881080cc1288b3b3",
                  "audit.json": "2ecad1749350c3df90346d2281ecd3b68c19d8fb4e5f9d6fd5bbf072eb6830f9",
                  "launcher-note.json": "fa0b99091b066d1345e434d627bca1166c04f7a0d50f6dba97aa0e6308272119",
              }}
STOP_OUTCOMES = {"client-error", "unsafe-response", "model-mismatch", "request-mismatch"}


def witness_plan(runs_root: Path, witness: dict) -> dict:
    directory = runs_root / witness["directory"]
    if any(sha(directory / name) != digest for name, digest in witness["files"].items()):
        raise ValueError("Historical evidence changed; do not overwrite or regrade it.")
    envelope = strict_json((directory / "plan.json").read_text())
    if (envelope["plan_sha256"] != witness["plan_sha256"]
            or canonical_json_sha256(envelope["plan"]) != witness["plan_sha256"]):
        raise ValueError("Historical plan digest mismatch.")
    return envelope["plan"]


def load_parent(runs_root: Path, spec: dict = SPEC) -> dict:
    parent = witness_plan(runs_root, PARENT)
    if spec == SPEC_V11:
        stopped = witness_plan(runs_root, STOPPED_V1)
        return {**parent, "cases": parent["cases"] + stopped["cases"]}
    return parent


def request_params(family: str, arm: str) -> dict:
    if arm not in ARMS:
        raise ValueError("Unknown frozen experiment arm.")
    return {"model": CONFIG["model"], "reasoning": {"effort": CONFIG["reasoning_effort"]},
            "max_output_tokens": SPEC["per_call_output_tokens"], "store": False,
            "text": {"format": native_task_format(family) if arm == "native" else {"type": "json_object"}}}


def public_task(case: dict, records: list[dict], json_label: bool = False) -> dict:
    schema = json.dumps(native_task_schema(case["family"]), sort_keys=True, separators=(",", ":"))
    label = "Output JSON schema" if json_label else "Output schema"
    return validate_task_input({"family": case["family"],
                                "question": case["query"] + f"\n{label} (structure only):\n" + schema,
                                "records": [{"id": r["id"], "text": source_text(r)} for r in records]})


def build_plan(cfg: dict, parent_plan: dict, spec: dict = SPEC) -> dict:
    if spec not in (SPEC, SPEC_V11):
        raise ValueError("Unknown calibration protocol; version it before spending.")
    cfg = config(cfg)
    cases, cells = [], []
    view_index = 0
    for scenario in CALIBRATION_CASES:
        case = make_state_case(spec["fresh_seed"], scenario, "native-fresh", 18)
        cases.append(case)
        records = [r for r in case["records"] if r["kind"] != "distractor"]
        views = [("source", records)]
        if scenario in spec["empty_scenarios"]:
            views.append(("empty", []))
        if scenario == "urgent-enabled":
            views.append(("partial-rule", [r for r in records if r["kind"] != "override"]))
        if scenario == "complete-join":
            views.append(("partial-chain", [r for r in records if r["kind"] != "line-pool"]))
        for condition, supplied in views:
            task = public_task(case, supplied, json_label=spec == SPEC_V11)
            prompt = json.dumps(task, ensure_ascii=False, sort_keys=True)
            visible = [r["id"] for r in case["records"] if source_text(r) in prompt]
            if visible != [r["id"] for r in supplied]:
                raise ValueError("JSON serialization changed source visibility.")
            for arm in ARMS[::1 if view_index % 2 == 0 else -1]:
                params = request_params(case["family"], arm)
                body = {**params, "input": prompt, "instructions": SYSTEM}
                cells.append({"id": f"{case['id']}:{condition}:{arm}", "case_id": case["id"], "arm": arm,
                              "scenario": scenario, "family": case["family"], "condition": condition,
                              "task": task, "prompt": prompt, "system": SYSTEM, "request_params": params,
                              "request_sha256": canonical_json_sha256(body), "visible_ids": visible,
                              "expected": reference_state(case, visible),
                              "input_utf8_bytes": len(json.dumps(body).encode()),
                              "input_tokens_estimated": estimate_token_count(SYSTEM + "\n" + prompt)})
            view_index += 1
    old = parent_plan["cases"]
    if any({c[field] for c in cases} & {c[field] for c in old} for field in ("seed", "id", "target")):
        raise ValueError("Fresh case identities overlap the retained parent.")
    if len(cases) != 10 or len(cells) != 30 or len({c["id"] for c in cells}) != 30:
        raise ValueError("Missing or duplicate frozen cases.")
    return {"method": spec["schema"], "spec": spec, "config": cfg, "parent": PARENT,
            "retained_failed": STOPPED_V1 if spec == SPEC_V11 else None,
            "cases": cases, "cells": cells, "runtime_sha256": runtime_hashes(),
            "budget": {"max_calls": 30, "max_output_tokens": 122880, "retries": 0,
                       "input_utf8_bytes": sum(c["input_utf8_bytes"] for c in cells),
                       "visible_input_tokens_estimated": sum(c["input_tokens_estimated"] for c in cells)}}


def source_revision() -> str:
    paths = [str(p.relative_to(REPO)) for p in sorted((REPO / "great_scratchpad").glob("*.py"))]
    paths += ["scenarios/luna_native_contract_v1.json", "docs/luna-native-contract-v1-protocol.md",
              "scenarios/luna_native_contract_v11.json", "docs/luna-native-contract-v11-protocol.md"]
    subprocess.run(["git", "ls-files", "--error-unmatch", *paths], cwd=REPO, capture_output=True, check=True)
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], cwd=REPO, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                          text=True, check=True).stdout.strip()


def prepare(out: Path, runs_root: Path, spec_path: Path, cfg_path: str,
            max_calls: int, max_output: int, max_input_bytes: int) -> dict:
    spec = strict_json(spec_path.read_text())
    if spec not in (SPEC, SPEC_V11):
        raise ValueError("Protocol changed; version it before spending.")
    if spec == SPEC:
        raise ValueError("V1 is a retained stopped campaign; prepare fresh cases under V1.1 instead.")
    cfg = load_llm_config(REPO, cfg_path, CONFIG["profile"])
    plan = build_plan(cfg, load_parent(runs_root, spec), spec)
    if (plan["budget"]["max_calls"] > max_calls or plan["budget"]["max_output_tokens"] > max_output
            or plan["budget"]["input_utf8_bytes"] > max_input_bytes):
        raise ValueError("Whole campaign exceeds explicit limits.")
    plan["source_commit"] = source_revision()
    plan["limits"] = {"calls": max_calls, "output_tokens": max_output, "input_utf8_bytes": max_input_bytes}
    envelope = {"plan_sha256": canonical_json_sha256(plan), "plan": plan}
    out.mkdir(parents=True, exist_ok=False)
    write_manifest(out / "plan.json", envelope)
    return envelope


def load_plan(out: Path, digest: str, cfg_path: str) -> dict:
    envelope = strict_json((out / "plan.json").read_text())
    plan = envelope["plan"]
    cfg = config(load_llm_config(REPO, cfg_path, CONFIG["profile"]))
    if envelope["plan_sha256"] != digest or canonical_json_sha256(plan) != digest:
        raise ValueError("Frozen plan digest mismatch.")
    if (cfg != plan["config"] or plan["spec"] not in (SPEC, SPEC_V11) or PARENT != plan["parent"]
            or plan["method"] != plan["spec"]["schema"]
            or plan.get("retained_failed") != (STOPPED_V1 if plan["spec"] == SPEC_V11 else None)
            or runtime_hashes() != plan["runtime_sha256"]):
        raise ValueError("Runtime, protocol or provider profile changed after freeze.")
    return plan


def outcome(cell: dict, receipt: dict) -> str:
    if receipt["unsafe_response"]:
        return "unsafe-response"
    response = receipt["llm"]
    if response is None:
        return "client-error"
    if response.get("response_model") != CONFIG["model"]:
        return "model-mismatch"
    if response.get("request_params") != cell["request_params"] or response.get("adapter") != "openai-responses":
        return "request-mismatch"
    if response.get("refusals"):
        return "refusal"
    if response.get("response_status") != "completed":
        return "provider-incomplete"
    return response.get("response_failure") or "ok"


def assess(plan: dict, cell: dict, receipt: dict) -> dict:
    case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
    raw = (receipt["llm"] or {}).get("content", "")
    a = assess_answer(raw, case, cell["prompt"], "evidence-state")
    a["provider_completed"] = outcome(cell, receipt) == "ok"
    try:
        validate_task_answer(raw, cell["family"], cell["visible_ids"])
        a["caller_contract_ok"] = True
    except (ValueError, TypeError, RecursionError):
        a["caller_contract_ok"] = False
    a["failure_tags"] = failure_tags(raw, a)
    if not a["caller_contract_ok"]:
        a["failure_tags"].append("caller-contract")
    if not a["provider_completed"]:
        a["failure_tags"].insert(0, outcome(cell, receipt))
        for key in ("value_correct", "epistemic_success", "contract_success", "recovered"):
            a[key] = False
    a["contract_success"] = bool(a["contract_success"] and a["caller_contract_ok"])
    return a


def redact(value: object, key: str) -> object:
    if isinstance(value, str):
        return value.replace(key, "[REDACTED]") if key else value
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, dict):
        return {redact(k, key): redact(v, key) for k, v in value.items()}
    return value


def run(out: Path, digest: str, cfg_path: str) -> dict:
    plan = load_plan(out, digest, cfg_path)
    key = api_key_from_config(plan["config"])
    if not key:
        raise ValueError("OpenAI credential unavailable.")
    directory = out / "execution"
    directory.mkdir(exist_ok=False)
    result = {"method": plan["method"], "plan_sha256": digest, "status": "running", "started_at": now_iso(),
              "attempted_calls": 0, "known_usage": empty_usage(), "unavailable_usage_calls": 0, "cells": []}

    def save() -> None:
        result["updated_at"] = now_iso()
        write_manifest(directory / "result.json", result)

    save()
    for cell in plan["cells"]:
        append_jsonl(directory / "attempts.jsonl", {"id": cell["id"], "plan_sha256": digest,
                                                   "request_sha256": cell["request_sha256"], "started_at": now_iso()})
        result["attempted_calls"] += 1
        save()
        started = time.perf_counter()
        receipt = {"id": cell["id"], "request_sha256": cell["request_sha256"], "llm": None,
                   "unsafe_response": False, "client_error": None, "helper_validation_error": None}
        try:
            try:
                if cell["arm"] == "native":
                    response = call_structured_task(plan["config"], cell["task"],
                                                    max_output_tokens=plan["spec"]["per_call_output_tokens"])["llm"]
                else:
                    response = call_llm_result(plan["config"], cell["prompt"], cell["system"])
            except (LLMResponseError, TaskContractError) as exc:
                response = exc.result
                if isinstance(exc, TaskContractError):
                    receipt["helper_validation_error"] = str(exc)
            if not isinstance(response.get("content"), str):
                raise ValueError("Received provider content is not text.")
            receipt["unsafe_response"] = key in json.dumps(response, ensure_ascii=False)
            receipt["llm"] = redact(response, key)
        except (Exception, SystemExit) as exc:
            receipt["client_error"] = {"type": type(exc).__name__, "message": str(redact(str(exc), key))[:500]}
        receipt = redact(receipt, key)
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        append_jsonl(directory / "responses.jsonl", receipt)
        status = outcome(cell, receipt)
        response = receipt["llm"]
        reported = bool(response and response.get("usage_reported") and response.get("usage"))
        result["cells"].append({"id": cell["id"], "status": status,
                                "response_sha256": canonical_json_sha256(receipt), "assessment": assess(plan, cell, receipt),
                                "known_usage": response["usage"] if reported else {}, "usage_reported": reported,
                                "elapsed_ms": receipt["elapsed_ms"]})
        result["unavailable_usage_calls"] += record_usage(result["known_usage"], {
            "llm": response, "usage_reported": (response or {}).get("usage_reported", False)})
        save()
        print(f"{result['attempted_calls']}/30 {cell['scenario']} {cell['condition']} {cell['arm']}: "
              f"{status} strict={result['cells'][-1]['assessment']['contract_success']}", flush=True)
        if status in STOP_OUTCOMES:
            result["status"] = "stopped"
            save()
            return audit(plan, digest, out)
    result["status"] = "complete"
    save()
    return audit(plan, digest, out)


def audit(plan: dict, digest: str, out: Path) -> dict:
    directory = out / "execution"
    result = strict_json((directory / "result.json").read_text())
    attempts = [strict_json(s) for s in (directory / "attempts.jsonl").read_text().splitlines()]
    receipts = [strict_json(s) for s in (directory / "responses.jsonl").read_text().splitlines()]
    n = result["attempted_calls"]
    if (result["plan_sha256"] != digest or not 1 <= n <= len(plan["cells"])
            or not (n == len(attempts) == len(receipts) == len(result["cells"]))
            or result["status"] not in {"complete", "stopped"}
            or (result["status"] == "complete" and n != len(plan["cells"]))):
        raise ValueError("Incomplete or mismatched ledger; never silently resume or reissue.")
    usage, unavailable = empty_usage(), 0
    for cell, attempt, receipt, saved in zip(plan["cells"][:n], attempts, receipts, result["cells"]):
        response = receipt["llm"]
        reported = bool(response and response.get("usage_reported") and response.get("usage"))
        if (any(r["id"] != cell["id"] for r in (attempt, receipt, saved))
                or attempt["plan_sha256"] != digest
                or any(r["request_sha256"] != cell["request_sha256"] for r in (attempt, receipt))
                or saved["response_sha256"] != canonical_json_sha256(receipt)
                or saved["status"] != outcome(cell, receipt) or saved["assessment"] != assess(plan, cell, receipt)
                or saved["known_usage"] != (response["usage"] if reported else {})
                or saved["usage_reported"] != reported or saved["elapsed_ms"] != receipt["elapsed_ms"]):
            raise ValueError("Receipt/assessment alignment failed.")
        unavailable += record_usage(usage, {"llm": response, "usage_reported": (response or {}).get("usage_reported", False)})
    if (usage != result["known_usage"] or unavailable != result["unavailable_usage_calls"]
            or any(c["status"] in STOP_OUTCOMES for c in result["cells"][:-1])
            or (result["status"] == "complete" and result["cells"][-1]["status"] in STOP_OUTCOMES)
            or (result["status"] == "stopped" and (not n or result["cells"][-1]["status"] not in STOP_OUTCOMES))):
        raise ValueError("Saved usage/stop state differs from received evidence.")
    return result


def summarize(plan: dict, result: dict) -> dict:
    saved = {c["id"]: c for c in result["cells"]}
    arms, pairs = [], []
    for arm in ARMS:
        rows = [c for c in plan["cells"] if c["arm"] == arm and c["id"] in saved]
        scores = [saved[c["id"]]["assessment"] for c in rows]
        usage = empty_usage()
        for cell in rows:
            add_usage(usage, saved[cell["id"]]["known_usage"])
        arms.append({"arm": arm, "attempted": len(rows), "planned": 15,
                     **{k: sum(bool(s.get(k)) for s in scores) for k in METRICS},
                     "all_15_passed": len(scores) == 15 and all(s["contract_success"] for s in scores),
                     "known_usage": usage,
                     "unavailable_usage_calls": sum(not saved[c["id"]]["usage_reported"] for c in rows),
                     "failure_tags": dict(Counter(t for s in scores for t in s["failure_tags"]))})
    for index in range(0, len(plan["cells"]), 2):
        cells = {c["arm"]: c for c in plan["cells"][index:index + 2]}
        if all(c["id"] in saved for c in cells.values()):
            pairs.append((saved[cells["json-mode"]["id"]]["assessment"]["contract_success"],
                          saved[cells["native"]["id"]]["assessment"]["contract_success"]))
    return {"method": plan["method"], "status": result["status"], "arms": arms,
            "paired_strict": paired_counts(pairs) if pairs else {"pairs": 0, "outcomes": {}, "mean_delta": None},
            "known_usage": result["known_usage"],
            "unavailable_usage_calls": result["unavailable_usage_calls"], "pilot_calls": 0,
            "scope": "15 dependent views of ten fresh authored cases; not retrieval efficacy or adoption evidence.",
            "cases": [{k: c[k] for k in ("id", "arm", "scenario", "family", "condition")} | saved[c["id"]]
                      for c in plan["cells"] if c["id"] in saved]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--llm-config", default="examples/gpt-6-luna.json")
    parser.add_argument("--spec", default="scenarios/luna_native_contract_v11.json", type=Path)
    parser.add_argument("--runs-root", default=".great_scratchpad/runs", type=Path)
    parser.add_argument("--max-calls", type=int, default=30)
    parser.add_argument("--max-output-tokens", type=int, default=122880)
    parser.add_argument("--max-input-bytes", type=int, default=300000)
    args = parser.parse_args()
    if args.command == "prepare":
        envelope = prepare(args.out_dir, args.runs_root, args.spec, args.llm_config,
                           args.max_calls, args.max_output_tokens, args.max_input_bytes)
        print(json.dumps({"plan_sha256": envelope["plan_sha256"], "budget": envelope["plan"]["budget"]}))
        return
    if not args.plan_sha256:
        parser.error("A frozen plan digest is required.")
    if args.command == "run":
        result = run(args.out_dir, args.plan_sha256, args.llm_config)
    else:
        plan = load_plan(args.out_dir, args.plan_sha256, args.llm_config)
        result = summarize(plan, audit(plan, args.plan_sha256, args.out_dir))
        write_manifest(args.out_dir / "summary.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "cells" and k != "cases"}, ensure_ascii=False, indent=2))
    if args.command == "run" and result["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
