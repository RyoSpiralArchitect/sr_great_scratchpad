"""Frozen historical replication and a fresh task-kind/proof calibration."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time

from .chat import build_chat_prompt, llm_trace
from .dialogue import add_usage, append_jsonl, canonical_json_sha256, empty_usage
from .experiments import write_manifest
from .grounded_recall import runtime_hashes, strict_json
from .llm import LLMResponseError, api_key_from_config, call_llm_result, estimate_token_count
from .memory_task_design import source_text
from .storage import load_llm_config, now_iso
from .task_contract import PROOF_INSTRUCTIONS, declare_task
from .uncertainty_contract import CALIBRATION_CASES, assess_answer, make_state_case, reference_state
from .uncertainty_experiment import SYSTEMS_V21, audit_stage as audit_mistral

REPO = Path(__file__).resolve().parents[1]
METHOD = "luna-evidence-state-v3"
VARIANTS = ("generic", "task-kind", "proof", "task-kind+proof")
METRICS = ("schema_ok", "value_correct", "flags_faithful", "epistemic_success", "contract_success", "recovered")
SPEC = {"schema": METHOD, "model": "gpt-6-luna", "fresh_seed": 26110240,
        "variants": list(VARIANTS), "source_scenarios": list(CALIBRATION_CASES),
        "empty_scenarios": ["hold-unknown", "approved-update", "complete-join"],
        "partial_scenarios": ["urgent-enabled", "complete-join"],
        "replication_calls": 24, "fresh_calls": 60, "max_calls": 84,
        "per_call_output_tokens": 4096, "retries": 0, "pilot_calls": 0,
        "future_gate": "all 15 cases for an arm; no retrieval pilot authorized in this campaign"}
CONFIG = {"profile": "openai-6-luna", "backend": "openai", "adapter": "openai-responses",
          "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY",
          "model": "gpt-6-luna", "reasoning_effort": "high", "max_output_tokens": 4096,
          "json_mode": "json_object", "store": False, "timeout": 90}
PARENTS = {
    "v2": {"directory": "uncertainty-contract-v2-20261028",
           "digest": "cac1989ce3fcdbc52d5f3726cd9dbe959a48371134b9a25e5a1b1d74a20bc318",
           "files": {"plan.json": "7135b26d4d996b020a41a9587c95c4a05d8ce9c462b96f392788da47e376755e",
                     "calibration/result.json": "7397efb38099e78af75ea547cb25cf9a1e89e3872d6798c2784c909cf3c1b72a",
                     "calibration/attempts.jsonl": "b13b3bf8afecb017257bc06c8c67b82985e492785f7d640ca6e12c19d98a321d",
                     "calibration/responses.jsonl": "e75491b559fe2f8fcf32b8f13e2fb18a164522c1082320cb546ebced675e9aad"}},
    "v2.1": {"directory": "uncertainty-contract-v21-20261028",
             "digest": "5fc5472176d619e1b100e5c749653ff10f5c69f0c4f05ef7efbaf6f9e687b59a",
             "files": {"plan.json": "fa6a6310db635e770962af98eb87a03846bd4c65a472bf2764da0b2e3afd5825",
                       "calibration/result.json": "05675287a43e03f6fc0d16c3df140ded41aba22cea7f6408bd732ce2523f06c4",
                       "calibration/attempts.jsonl": "112d52b306e5d685ffb04e8e807225f5ec6072122aad4df4618ccff331f38514",
                       "calibration/responses.jsonl": "073614b0e97537595d89f31d9dada967bf4a79060e5af047cdf6e132b13802ea"}},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config(cfg: dict) -> dict:
    clean = {k: v for k, v in cfg.items() if k != "_config_path"}
    if clean != CONFIG:
        raise ValueError("Use the frozen explicit GPT-6 Luna Responses profile; no sampling overrides or inline keys.")
    return clean


def request_params(cfg: dict) -> dict:
    return {"model": cfg["model"], "reasoning": {"effort": cfg["reasoning_effort"]},
            "max_output_tokens": cfg["max_output_tokens"], "text": {"format": {"type": "json_object"}},
            "store": False}


def load_histories(runs_root: Path) -> list[dict]:
    histories = []
    for label, witness in PARENTS.items():
        directory = runs_root / witness["directory"]
        if any(sha(directory / f) != digest for f, digest in witness["files"].items()):
            raise ValueError("Historical raw files changed; never regrade or overwrite them.")
        envelope = strict_json((directory / "plan.json").read_text())
        plan = envelope["plan"]
        if envelope["plan_sha256"] != witness["digest"] or canonical_json_sha256(plan) != witness["digest"]:
            raise ValueError("Historical plan digest mismatch.")
        dependencies = ("uncertainty_contract.py", "grounded_recall.py", "memory_task_design.py", "dialogue.py")
        if any(sha(REPO / "great_scratchpad" / f) != plan["runtime_sha256"][f] for f in dependencies):
            raise ValueError("The frozen assessor or a scoring dependency changed.")
        result = audit_mistral(plan, witness["digest"], directory, "calibration")
        histories.append({"cohort": label, "witness": witness, "config": plan["config"],
                          "source_commit": plan["source_commit"], "system": plan["systems"]["evidence-state"],
                          "cases": [c for c in plan["cases"] if c["split"] == "calibration"],
                          "cells": [c for c in plan["cells"] if c["stage"] == "calibration"],
                          "saved": result["cells"], "known_usage": result["known_usage"],
                          "receipts": [strict_json(s) for s in (directory / "calibration/responses.jsonl").read_text().splitlines()]})
    return histories


def build_plan(cfg: dict, histories: list[dict]) -> dict:
    cfg = config(cfg)
    if [h["cohort"] for h in histories] != list(PARENTS):
        raise ValueError("Both historical cohorts must be retained in order.")
    cases, cells, parents = [], [], []

    def add(case: dict, prompt: str, system: str, *, cell_id: str, **metadata: object) -> None:
        visible = [r["id"] for r in case["records"] if source_text(r) in prompt]
        cells.append({"id": cell_id, "case_id": case["id"], "scenario": case["scenario"],
                      "family": case["family"], **metadata, "prompt": prompt, "system": system,
                      "prompt_sha256": canonical_json_sha256(prompt), "system_sha256": canonical_json_sha256(system),
                      "request_sha256": canonical_json_sha256({"params": request_params(cfg), "prompt": prompt, "system": system}),
                      "visible_ids": visible, "expected": reference_state(case, visible),
                      "input_utf8_bytes": len((system + "\n" + prompt).encode()),
                      "input_tokens_estimated": estimate_token_count(system + "\n" + prompt)})

    for h in histories:
        if not (len(h["cells"]) == len(h["saved"]) == len(h["receipts"]) == 12):
            raise ValueError("Historical calibration must contain every one of its twelve cells.")
        cases.extend(h["cases"])
        parents.append({k: h[k] for k in ("cohort", "witness", "config", "source_commit", "known_usage")})
        by_id = {c["id"]: c for c in h["cases"]}
        for old, saved, receipt in zip(h["cells"], h["saved"], h["receipts"]):
            if (old["id"] != saved["id"] or old["id"] != receipt["id"]
                    or saved["response_sha256"] != canonical_json_sha256(receipt)
                    or saved["assessment"]["expected"] != reference_state(by_id[old["case_id"]], old["visible_ids"])):
                raise ValueError("Historical raw assessment alignment failed.")
            add(by_id[old["case_id"]], old["prompt"], h["system"],
                cell_id=f"replication:{h['cohort']}:{old['id']}", stage="replication", cohort=h["cohort"],
                variant="unchanged", condition=old["condition"],
                mistral={"receipt": receipt, "assessment": saved["assessment"]})

    for scenario in CALIBRATION_CASES:
        case = make_state_case(SPEC["fresh_seed"], scenario, "luna-fresh", 18)
        cases.append(case)
        records = [r for r in case["records"] if r["kind"] != "distractor"]
        views = [("source", records)]
        if scenario in SPEC["empty_scenarios"]:
            views.append(("empty", []))
        if scenario == "urgent-enabled":
            views.append(("partial-rule", [r for r in records if r["kind"] != "override"]))
        if scenario == "complete-join":
            views.append(("partial-chain", [r for r in records if r["kind"] != "line-pool"]))
        for condition, supplied in views:
            context = "\n".join(source_text(r) for r in supplied) or "(no archive records)"
            prompt = build_chat_prompt("memory-task-probe", case["query"], context, [], [], "", history_context="(empty)")
            offset = sum(c["stage"] == "fresh" for c in cells) // len(VARIANTS) % len(VARIANTS)
            for variant in VARIANTS[offset:] + VARIANTS[:offset]:
                typed = variant in {"task-kind", "task-kind+proof"}
                proof = variant in {"proof", "task-kind+proof"}
                system = SYSTEMS_V21["evidence-state"] + (PROOF_INSTRUCTIONS if proof else "")
                add(case, declare_task(prompt, case["family"]) if typed else prompt, system,
                    cell_id=f"fresh:{case['id']}:{condition}:{variant}", stage="fresh", cohort="fresh",
                    condition=condition, variant=variant, task_kind_factor=typed, proof_factor=proof)
    if len(cells) != 84 or len({c["id"] for c in cells}) != 84 or len({c["id"] for c in cases}) != 30:
        raise ValueError("Missing, duplicate or substituted cases.")
    return {"method": METHOD, "spec": SPEC, "config": cfg, "parents": parents, "cases": cases, "cells": cells,
            "runtime_sha256": runtime_hashes(),
            "schema_sha256": sha(REPO / "schemas/evidence_state_v2.schema.json"),
            "budget": {"max_calls": 84, "max_output_tokens": 344064, "retries": 0,
                       "input_utf8_bytes": sum(c["input_utf8_bytes"] for c in cells),
                       "input_tokens_estimated": sum(c["input_tokens_estimated"] for c in cells)}}


def prepare(out: Path, runs_root: Path, spec_path: Path, cfg_path: str,
            max_calls: int, max_output: int, max_input_bytes: int) -> dict:
    if strict_json(spec_path.read_text()) != SPEC:
        raise ValueError("Protocol changed; version it before spending.")
    cfg = load_llm_config(Path("."), cfg_path, CONFIG["profile"])
    plan = build_plan(cfg, load_histories(runs_root))
    if (plan["budget"]["max_calls"] > max_calls or plan["budget"]["max_output_tokens"] > max_output
            or plan["budget"]["input_utf8_bytes"] > max_input_bytes):
        raise ValueError("Whole campaign exceeds explicit limits.")
    plan["source_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                           capture_output=True, text=True, check=True).stdout.strip()
    plan["limits"] = {"calls": max_calls, "output_tokens": max_output, "input_utf8_bytes": max_input_bytes}
    envelope = {"plan_sha256": canonical_json_sha256(plan), "plan": plan}
    out.mkdir(parents=True, exist_ok=False)
    write_manifest(out / "plan.json", envelope)
    return envelope


def load_plan(out: Path, digest: str, cfg_path: str) -> dict:
    envelope = strict_json((out / "plan.json").read_text())
    plan = envelope["plan"]
    if digest != envelope["plan_sha256"] or canonical_json_sha256(plan) != digest:
        raise ValueError("Frozen plan digest mismatch.")
    cfg = config(load_llm_config(Path("."), cfg_path, CONFIG["profile"]))
    if (cfg != plan["config"] or runtime_hashes() != plan["runtime_sha256"]
            or sha(REPO / "schemas/evidence_state_v2.schema.json") != plan["schema_sha256"]):
        raise ValueError("Runtime, schema or provider profile changed after freeze.")
    return plan


def status(receipt: dict) -> str:
    if receipt["llm"] is None:
        return "unsafe-response" if receipt["client_error"]["type"] == "UnsafeResponse" else "client-error"
    if receipt["llm"].get("response_model") != CONFIG["model"]:
        return "model-mismatch"
    if receipt["request_params"] != request_params(CONFIG):
        return "request-mismatch"
    if receipt.get("refusals"):
        return "refusal"
    if receipt["response_status"] != "completed":
        details = receipt.get("incomplete_details") or {}
        return "output-limit" if details.get("reason") == "max_output_tokens" else "provider-incomplete"
    if receipt.get("response_failure"):
        return receipt["response_failure"]
    return "ok"


def failure_tags(raw: str, assessment: dict) -> list[str]:
    """Separate value errors from proof omissions without changing frozen scores."""
    tags = []
    if not assessment["schema_ok"]:
        tags.append("schema")
    try:
        answer = strict_json(raw)
    except (ValueError, TypeError, RecursionError):
        return tags + ["json"]
    if not isinstance(answer, dict):
        return tags + ["shape"]
    expected = assessment["expected"]
    flags = answer.get("flags")
    if not isinstance(flags, dict) or set(flags) != set(expected["flags"]):
        tags.append("flag-shape")
    elif flags != expected["flags"]:
        tags.append("flag-state")
        if any(expected["flags"][k] in {"unknown", "unobserved"} and flags[k] == "disabled" for k in flags):
            tags.append("unknown-as-disabled")
    if "value" in answer and answer["value"] != expected["value"]:
        tags.append("over-abstention" if answer["value"] is None else "wrong-value")
    for field, tag in (("proof_covered", "missing-citation"), ("citations_visible", "invisible-citation"),
                       ("citations_relevant", "irrelevant-citation")):
        if assessment.get(field) is False:
            tags.append(tag)
    return tags


def assess(plan: dict, cell: dict, receipt: dict) -> dict:
    case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
    raw = receipt["raw_output"] or ""
    assessment = assess_answer(raw, case, cell["prompt"], "evidence-state")
    tags = failure_tags(raw, assessment)
    outcome = status(receipt)
    assessment["outcome_ok"] = outcome == "ok"
    if outcome != "ok":
        tags.insert(0, outcome)
        for key in ("value_correct", "epistemic_success", "contract_success", "recovered"):
            assessment[key] = False
    assessment["failure_tags"] = tags
    return assessment


def record_usage(total: dict, receipt: dict) -> int:
    if receipt["llm"] and receipt["usage_reported"] and receipt["llm"].get("usage"):
        add_usage(total, receipt["llm"]["usage"])
        return 0
    return 1


def audit(plan: dict, digest: str, out: Path) -> dict:
    directory = out / "execution"
    result = strict_json((directory / "result.json").read_text())
    receipts = [strict_json(line) for line in (directory / "responses.jsonl").read_text().splitlines()]
    attempts = [strict_json(line) for line in (directory / "attempts.jsonl").read_text().splitlines()]
    if (result["plan_sha256"] != digest or result["status"] != "complete"
            or not (len(plan["cells"]) == result["attempted_calls"] == len(result["cells"]) == len(receipts) == len(attempts))):
        raise ValueError("Incomplete or mismatched campaign; no silent continuation or reissue.")
    known_usage, unavailable = empty_usage(), 0
    for cell, saved, receipt, attempt in zip(plan["cells"], result["cells"], receipts, attempts):
        if (any(r["id"] != cell["id"] for r in (saved, receipt, attempt))
                or any(r["request_sha256"] != cell["request_sha256"] for r in (receipt, attempt))
                or attempt["plan_sha256"] != digest or saved["response_sha256"] != canonical_json_sha256(receipt)
                or saved["status"] != status(receipt) or saved["assessment"] != assess(plan, cell, receipt)):
            raise ValueError("Raw receipt, attempt or reassessment mismatch.")
        unavailable += record_usage(known_usage, receipt)
    if result["known_usage"] != known_usage or result["unavailable_usage_calls"] != unavailable:
        raise ValueError("Saved usage differs from received reports; missing usage is not zero.")
    return result


def run(out: Path, digest: str, cfg_path: str) -> dict:
    plan = load_plan(out, digest, cfg_path)
    key = api_key_from_config(plan["config"])
    if not key:
        raise ValueError("OpenAI credential unavailable.")
    directory = out / "execution"
    directory.mkdir(exist_ok=False)
    result = {"method": METHOD, "plan_sha256": digest, "started_at": now_iso(), "status": "running",
              "attempted_calls": 0, "known_usage": empty_usage(), "unavailable_usage_calls": 0, "cells": []}

    def save() -> None:
        result["updated_at"] = now_iso()
        write_manifest(directory / "result.json", result)

    save()
    for cell in plan["cells"]:
        append_jsonl(directory / "attempts.jsonl", {"id": cell["id"], "request_sha256": cell["request_sha256"],
                                                   "plan_sha256": digest, "started_at": now_iso()})
        result["attempted_calls"] += 1
        save()
        started = time.perf_counter()
        receipt = {"id": cell["id"], "request_sha256": cell["request_sha256"], "raw_output": None,
                   "llm": None, "response_status": None, "response_id": None, "request_params": None,
                   "incomplete_details": None, "response_error": None, "usage_reported": False,
                   "refusals": [], "response_failure": None,
                   "client_error": None}
        try:
            try:
                response = call_llm_result(plan["config"], cell["prompt"], cell["system"])
            except LLMResponseError as exc:
                response = exc.result
            if key in json.dumps(response, ensure_ascii=False):
                receipt["client_error"] = {"type": "UnsafeResponse", "message": "Credential reflected; response not stored."}
            elif not isinstance(response.get("content"), str):
                raise ValueError("Provider content must be text.")
            else:
                receipt.update(raw_output=response["content"], llm=llm_trace(response))
                for field in ("response_status", "response_id", "request_params", "incomplete_details", "response_error", "usage_reported", "refusals", "response_failure"):
                    receipt[field] = response.get(field)
        except (Exception, SystemExit) as exc:
            receipt["client_error"] = {"type": type(exc).__name__, "message": str(exc).replace(key, "[REDACTED]")[:500]}
        receipt["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        append_jsonl(directory / "responses.jsonl", receipt)
        outcome = status(receipt)
        assessment = assess(plan, cell, receipt)
        result["cells"].append({"id": cell["id"], "status": outcome,
                                "response_sha256": canonical_json_sha256(receipt), "assessment": assessment})
        result["unavailable_usage_calls"] += record_usage(result["known_usage"], receipt)
        save()
        print(f"{result['attempted_calls']}/84 {cell['stage']} {cell['scenario']} "
              f"{cell['condition']} {cell['variant']}: {outcome} strict={assessment['contract_success']}", flush=True)
        if outcome in {"unsafe-response", "model-mismatch", "request-mismatch"}:
            result["status"] = "stopped-identity-or-security"
            save()
            return result
    result["status"] = "complete"
    save()
    return audit(plan, digest, out)


def group_counts(assessments: list[dict]) -> dict:
    return {**{k: sum(bool(a[k]) for a in assessments) for k in METRICS},
            "failure_tags": dict(Counter(t for a in assessments for t in a["failure_tags"]))}


def paired_counts(pairs: list[tuple[bool, bool]]) -> dict:
    outcomes = Counter("both" if a and b else "treatment-only" if b else "control-only" if a else "neither" for a, b in pairs)
    return {"pairs": len(pairs), "outcomes": dict(outcomes),
            "mean_delta": sum(int(b) - int(a) for a, b in pairs) / len(pairs)}


def summarize(plan: dict, result: dict) -> dict:
    saved = {c["id"]: c for c in result["cells"]}
    replication, fresh, contrasts, cases = [], [], [], []
    for cohort in PARENTS:
        rows = [c for c in plan["cells"] if c["stage"] == "replication" and c["cohort"] == cohort]
        old, new, pairs, common = [], [], [], Counter()
        for c in rows:
            a, b = c["mistral"]["assessment"], saved[c["id"]]["assessment"]
            tags = failure_tags(c["mistral"]["receipt"]["raw_output"], a)
            old.append({**a, "failure_tags": tags})
            new.append(b)
            pairs.append((a["contract_success"], b["contract_success"]))
            common.update(set(tags) & set(b["failure_tags"]))
            cases.append({"id": c["id"], "stage": "replication", "scenario": c["scenario"],
                          "condition": c["condition"], "mistral_strict": a["contract_success"],
                          "luna_strict": b["contract_success"], "mistral_tags": tags, "luna_tags": b["failure_tags"]})
        replication.append({"cohort": cohort, "cases": len(rows), "mistral": group_counts(old),
                            "luna": group_counts(new), "strict_pairs": paired_counts(pairs),
                            "same_input_shared_failure_tags": dict(common)})
    for variant in VARIANTS:
        rows = [c for c in plan["cells"] if c["stage"] == "fresh" and c["variant"] == variant]
        assessments = [saved[c["id"]]["assessment"] for c in rows]
        fresh.append({"variant": variant, "cases": len(rows), **group_counts(assessments),
                      "all_15_passed": all(a["contract_success"] for a in assessments),
                      "statuses": dict(Counter(saved[c["id"]]["status"] for c in rows))})
    targets = {(c["case_id"], c["condition"]) for c in plan["cells"] if c["stage"] == "fresh"}
    for control, treatment in (("generic", "task-kind"), ("proof", "task-kind+proof"),
                               ("generic", "proof"), ("task-kind", "task-kind+proof")):
        pairs = []
        for case_id, condition in sorted(targets):
            by_variant = {c["variant"]: saved[c["id"]]["assessment"]["contract_success"] for c in plan["cells"]
                          if c["stage"] == "fresh" and c["case_id"] == case_id and c["condition"] == condition}
            pairs.append((by_variant[control], by_variant[treatment]))
        contrasts.append({"control": control, "treatment": treatment, **paired_counts(pairs)})
    for c in plan["cells"]:
        if c["stage"] == "fresh":
            a = saved[c["id"]]["assessment"]
            cases.append({"id": c["id"], "stage": "fresh", "scenario": c["scenario"], "family": c["family"],
                          "condition": c["condition"], "variant": c["variant"], "strict": a["contract_success"],
                          "failure_tags": a["failure_tags"], "expected": a["expected"]})
    return {"method": METHOD, "scope": "Descriptive calibration, not a model leaderboard or retrieval efficacy experiment.",
            "replication": replication, "fresh": fresh, "factor_contrasts": contrasts, "cases": cases,
            "known_usage": result["known_usage"], "unavailable_usage_calls": result["unavailable_usage_calls"],
            "pilot_calls": 0, "note": "Historical providers use different native sampling parameters; fresh views share ten authored cases."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report"))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--llm-config", default="examples/gpt-6-luna.json")
    parser.add_argument("--spec", default="scenarios/luna_uncertainty_v3.json", type=Path)
    parser.add_argument("--runs-root", default=".great_scratchpad/runs", type=Path)
    parser.add_argument("--max-calls", type=int, default=84)
    parser.add_argument("--max-output-tokens", type=int, default=344064)
    parser.add_argument("--max-input-bytes", type=int, default=2000000)
    args = parser.parse_args()
    if args.command == "prepare":
        env = prepare(args.out_dir, args.runs_root, args.spec, args.llm_config,
                      args.max_calls, args.max_output_tokens, args.max_input_bytes)
        print(json.dumps({"plan_sha256": env["plan_sha256"], "budget": env["plan"]["budget"]}))
    else:
        if not args.plan_sha256:
            parser.error("A frozen plan digest is required.")
        if args.command == "run":
            result = run(args.out_dir, args.plan_sha256, args.llm_config)
            print(json.dumps({k: v for k, v in result.items() if k != "cells"}))
        else:
            plan = load_plan(args.out_dir, args.plan_sha256, args.llm_config)
            result = audit(plan, args.plan_sha256, args.out_dir)
            summary = summarize(plan, result)
            write_manifest(args.out_dir / "summary.json", summary)
            print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
