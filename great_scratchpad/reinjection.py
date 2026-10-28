"""Frozen, bounded read-path pilot with separate format calibration."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import subprocess
import tempfile

from .centerline import analyze_centerline, render_centerline_hints
from .chat import build_chat_prompt, llm_trace
from .dialogue import add_usage, append_jsonl, canonical_json_sha256, empty_usage, render_dialogue_context
from .experiments import write_manifest
from .grounded_recall import runtime_hashes, strict_json
from .llm import api_key_from_config, call_llm_result, estimate_token_count
from .memory import retrieve_linked
from .memory_task_design import (
    CONDITIONS as ORIGINAL_CONDITIONS, FAMILIES, REGIMES, SYSTEM, assess_task_answer,
    build_conditions, make_case, pack_records, source_text, validate_constructed_case,
)
from .semantics import paired_bootstrap_mean_interval
from .storage import load_llm_config, now_iso

METHOD = "memory-reinjection-v1"
PROTOCOLS = {METHOD: ("none", 600), "memory-reinjection-v1.1": ("low", 1200)}
CONDITIONS = (*ORIGINAL_CONDITIONS[:3], "linked-retrieve", *ORIGINAL_CONDITIONS[3:])
CONFIG_FIELDS = {
    "profile", "backend", "adapter", "base_url", "api_key_env", "model", "temperature",
    "seed", "reasoning_effort", "json_mode", "max_tokens", "timeout",
}


def validate_spec(spec: dict) -> None:
    if spec.get("schema") not in PROTOCOLS:
        raise ValueError("Unsupported reinjection protocol.")
    expected = {"families": list(FAMILIES), "regimes": list(REGIMES),
                "conditions": list(CONDITIONS), "archive_distractors": [18, 72],
                "history_chars": 700, "memory_chars": 1200, "retrieval_top": 4,
                "linked_top": 16, "linked_hops": 2, "linked_per_hop": 4,
                "per_call_output_tokens": PROTOCOLS[spec["schema"]][1]}
    if any(spec.get(k) != v for k, v in expected.items()):
        raise ValueError("Frozen reinjection arms, tiers or budgets changed; version the protocol.")
    seeds = [spec.get("calibration_seed"), spec.get("pilot_seed")]
    if any(type(s) is not int or s < 1 for s in seeds) or len(set(seeds)) != 2:
        raise ValueError("Require disjoint positive calibration and pilot seeds.")


def experiment_config(cfg: dict) -> dict:
    cfg = {k: v for k, v in cfg.items() if k != "_config_path"}
    if set(cfg) - CONFIG_FIELDS:
        raise ValueError("Profile contains unsupported or secret fields.")
    if (cfg.get("model") != "mistral-large-4" or cfg.get("base_url") != "https://api.mistral.ai/v1"
            or cfg.get("backend") != "openai-compatible" or cfg.get("adapter") != "chat-completions"
            or cfg.get("api_key_env") != "MISTRAL_API_KEY" or cfg.get("temperature") != 0
            or cfg.get("seed") != 261028
            or (cfg.get("reasoning_effort"), cfg.get("max_tokens")) not in PROTOCOLS.values()
            or cfg.get("json_mode") != "json_object"
            or not cfg.get("profile")):
        raise ValueError("Use the explicit Mistral Large 4 calibration profile.")
    return dict(cfg)


def linked_condition(case: dict, spec: dict, archive: Path) -> dict:
    records = case["records"]
    transcript = [{"kind": "utterance", "speaker": "A", "message": source_text(r)} for r in records]
    history = render_dialogue_context(transcript, spec["history_chars"])
    recent = {r["id"] for r in records if source_text(r) in history}
    excluded = {archive / "turns" / f"{r['turn']:06d}-note.md" for r in records if r["id"] in recent}
    hits, rounds = retrieve_linked(archive, case["query"], spec["linked_top"],
                                   max_hops=spec["linked_hops"], per_hop=spec["linked_per_hop"], excluded=excluded)
    by_turn = {r["turn"]: r for r in records}
    ranked = [by_turn[int(path.name.split("-", 1)[0])] for _, path, _ in hits]
    _, selected = pack_records(ranked, spec["memory_chars"])
    selected_records = [r for r in records if r["id"] in selected]
    context, selected = pack_records(selected_records, spec["memory_chars"])
    hints = render_centerline_hints(analyze_centerline(case["query"], [{"role": "user", "content": history}]))
    common = dict(thread_id="memory-task-probe", user_text=case["query"], history=[], observations=[],
                  centerline_hints=hints, history_context=history)
    prompt = build_chat_prompt(recent_context=context, **common)
    visible = [r["id"] for r in records if source_text(r) in prompt]
    support = set(case["truth"]["support"])
    return {"condition": "linked-retrieve", "prompt": prompt,
            "prompt_sha256": canonical_json_sha256(prompt),
            "outside_memory_sha256": canonical_json_sha256(build_chat_prompt(recent_context="", **common)),
            "context_chars": len(context), "history_chars": len(history), "selected_ids": selected,
            "visible_ids": visible, "support_visible": bool(support) and support.issubset(visible),
            "retrieval_rounds": rounds, "retrieval_hits": [
                {"id": by_turn[int(p.name.split('-', 1)[0])]["id"], "score": score} for score, p, _ in hits]}


def build_plan(spec: dict, cfg: dict) -> dict:
    validate_spec(spec)
    cfg = experiment_config(cfg)
    if (cfg["reasoning_effort"], cfg["max_tokens"]) != PROTOCOLS[spec["schema"]]:
        raise ValueError("Profile must match this protocol's reasoning and output allowance.")
    cases, cells = [], []

    def cell(case: dict, row: dict, stage: str, **extra: object) -> dict:
        prompt = row["prompt"]
        return {**row, **extra, "id": case["id"] + ":" + row["condition"], "case_id": case["id"],
                "stage": stage, "family": case["family"], "regime": case["regime"],
                "input_utf8_bytes": len((SYSTEM + "\n" + prompt).encode("utf-8")),
                "input_tokens_estimated": estimate_token_count(SYSTEM + "\n" + prompt)}

    for family in FAMILIES:
        case = make_case(spec["calibration_seed"], family, "recent", "calibration", 18)
        cases.append(case)
        for visible in (True, False):
            context = "\n".join(source_text(r) for r in case["records"] if r["id"] in case["truth"]["support"]) if visible else "(no archive records)"
            prompt = build_chat_prompt("memory-task-probe", case["query"], context, [], [], "", history_context="(empty)")
            row = {"condition": "source" if visible else "empty", "prompt": prompt,
                   "prompt_sha256": canonical_json_sha256(prompt), "support_visible": visible,
                   "context_chars": len(context)}
            cells.append(cell(case, row, "calibration"))

    with tempfile.TemporaryDirectory(prefix="scratchpad-reinjection-") as temporary:
        for pressure in spec["archive_distractors"]:
            for family in FAMILIES:
                for regime in REGIMES:
                    case = make_case(spec["pilot_seed"], family, regime, "pilot", pressure)
                    case["id"] += f"-n{pressure}"
                    cases.append(case)
                    archive = Path(temporary) / case["id"]
                    rows = build_conditions(case, spec, archive)
                    validate_constructed_case(case, rows, spec)
                    rows.append(linked_condition(case, spec, archive))
                    normal = [r for r in rows if r["condition"] != "full-history"]
                    if len({r["outside_memory_sha256"] for r in normal}) != 1:
                        raise ValueError("Condition inputs differ outside the archive field.")
                    if any(r["context_chars"] > spec["memory_chars"] for r in normal):
                        raise ValueError("Whole-record packing exceeded the archive budget.")
                    by_arm = {r["condition"]: r for r in rows}
                    index = len([c for c in cases if c["split"] == "pilot"]) - 1
                    offset = index % len(CONDITIONS)
                    order = CONDITIONS[offset:] + CONDITIONS[:offset]
                    cells.extend(cell(case, by_arm[arm], "pilot", archive_distractors=pressure,
                                      condition_position=position + 1) for position, arm in enumerate(order))
    return {"method": spec["schema"], "spec": spec, "config": cfg, "system_prompt": SYSTEM,
            "cases": cases, "cells": cells, "runtime_sha256": runtime_hashes(),
            "budget": {"max_calls": len(cells), "per_call_output_tokens": cfg["max_tokens"],
                       "max_output_tokens": cfg["max_tokens"] * len(cells), "retries": 0,
                       "input_utf8_bytes": sum(c["input_utf8_bytes"] for c in cells),
                       "input_tokens_estimated": sum(c["input_tokens_estimated"] for c in cells)}}


def prepare_reinjection(root: Path, spec_path: Path, config_path: str, profile: str, out_dir: Path,
                        max_calls: int, max_output: int, max_input_bytes: int) -> dict:
    spec = strict_json(spec_path.read_text(encoding="utf-8"))
    plan = build_plan(spec, load_llm_config(root, config_path, profile))
    budget = plan["budget"]
    if (budget["max_calls"] > max_calls or budget["max_output_tokens"] > max_output
            or budget["input_utf8_bytes"] > max_input_bytes):
        raise ValueError("Complete campaign exceeds the supplied call/output/input budget.")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, check=True).stdout.strip()
    plan["source_commit"] = commit
    plan["limits"] = {"calls": max_calls, "output_tokens": max_output, "input_utf8_bytes": max_input_bytes}
    envelope = {"plan_sha256": canonical_json_sha256(plan), "plan": plan}
    out_dir.mkdir(parents=True, exist_ok=False)
    write_manifest(out_dir / "plan.json", envelope)
    return envelope


def load_plan(root: Path, out_dir: Path, digest: str, config_path: str) -> dict:
    envelope = strict_json((out_dir / "plan.json").read_text(encoding="utf-8"))
    plan = envelope["plan"]
    if envelope["plan_sha256"] != digest or canonical_json_sha256(plan) != digest:
        raise ValueError("Frozen plan digest mismatch.")
    cfg = experiment_config(load_llm_config(root, config_path, plan["config"]["profile"]))
    if cfg != plan["config"] or runtime_hashes() != plan["runtime_sha256"]:
        raise ValueError("Provider profile or runtime changed after plan freeze.")
    return plan


def assess_cell(plan: dict, cell: dict, raw: str) -> dict:
    case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
    result = assess_task_answer(raw, case, cell["prompt"])
    if cell["stage"] == "calibration":
        result["gate_passed"] = result["grounded_success"] if cell["condition"] == "source" else bool(result["schema_ok"] and result["safe_abstention"])
    return result


def audit_stage(plan: dict, digest: str, out_dir: Path, stage: str) -> dict:
    result = strict_json((out_dir / stage / "result.json").read_text(encoding="utf-8"))
    responses = [strict_json(s) for s in (out_dir / stage / "responses.jsonl").read_text().splitlines()]
    planned = [c for c in plan["cells"] if c["stage"] == stage]
    if (result["plan_sha256"] != digest or result["stage"] != stage or result["status"] != "complete"
            or result["attempted_calls"] != len(planned)
            or len(responses) != len(planned) or len(result["cells"]) != len(planned)):
        raise ValueError("Incomplete or mismatched stage receipts.")
    usage = empty_usage()
    for cell, saved, receipt in zip(planned, result["cells"], responses):
        if (saved["id"] != cell["id"] or receipt["id"] != cell["id"] or saved["status"] != "ok"
                or receipt["prompt_sha256"] != cell["prompt_sha256"]
                or canonical_json_sha256(receipt) != saved["response_sha256"]
                or assess_cell(plan, cell, receipt["raw_output"]) != saved["assessment"]):
            raise ValueError("Raw response identity, digest or reassessment mismatch.")
        if (receipt["llm"].get("response_model") not in {"mistral-large-4", "mistral-large-4-0"}
                or receipt.get("finish_reason") != "stop"):
            raise ValueError("Raw response model or completion status mismatch.")
        add_usage(usage, receipt["llm"].get("usage"))
    if usage != result["usage"]:
        raise ValueError("Saved usage differs from the response receipts.")
    passed = all(c["assessment"].get("gate_passed", True) for c in result["cells"])
    if passed != result["gate_passed"]:
        raise ValueError("Saved gate differs from raw-receipt reassessment.")
    return result


def run_reinjection(root: Path, out_dir: Path, digest: str, config_path: str, stage: str) -> dict:
    if stage not in {"calibration", "pilot"}:
        raise ValueError("Unknown reinjection stage.")
    plan = load_plan(root, out_dir, digest, config_path)
    if stage == "pilot" and not audit_stage(plan, digest, out_dir, "calibration")["gate_passed"]:
        raise ValueError("Format calibration failed; no pilot calls made.")
    key = api_key_from_config(plan["config"])
    if not key:
        raise ValueError("Mistral credential unavailable.")
    directory = out_dir / stage
    directory.mkdir(exist_ok=False)
    planned = [c for c in plan["cells"] if c["stage"] == stage]
    result = {"method": plan["method"], "stage": stage, "plan_sha256": digest, "started_at": now_iso(),
              "status": "running", "attempted_calls": 0, "gate_passed": False, "usage": empty_usage(),
              "cells": [{"id": c["id"], "status": "not-run"} for c in planned]}

    def save() -> None:
        result["updated_at"] = now_iso()
        write_manifest(directory / "result.json", result)

    save()
    for cell, saved in zip(planned, result["cells"]):
        saved["status"] = "running"
        result["attempted_calls"] += 1
        save()
        try:
            response = call_llm_result(plan["config"], cell["prompt"], plan["system_prompt"])
            raw = response.get("content", "")
            if not isinstance(raw, str) or key in raw:
                raise ValueError("Unexpected or credential-containing response; output not saved.")
            receipt = {"id": cell["id"], "prompt_sha256": cell["prompt_sha256"], "raw_output": raw,
                       "llm": llm_trace(response), "finish_reason": response.get("finish_reason", ""),
                       "response_id": response.get("response_id", ""), "request_params": response.get("request_params", {})}
            append_jsonl(directory / "responses.jsonl", receipt)
            saved["response_sha256"] = canonical_json_sha256(receipt)
            add_usage(result["usage"], response.get("usage"))
            if response.get("response_model") not in {"mistral-large-4", "mistral-large-4-0"}:
                raise ValueError("Provider returned an unexpected model; no substitution permitted.")
            if response.get("finish_reason") != "stop":
                raise ValueError("Provider did not complete the response within the frozen limit.")
            saved["assessment"] = assess_cell(plan, cell, raw)
            saved["status"] = "ok"
        except (Exception, SystemExit, KeyboardInterrupt) as exc:
            saved.update(status="error", error=str(exc).replace(key, "[REDACTED]"))
            result["status"] = "error"
            save()
            return result
        save()
    result["status"] = "complete"
    result["gate_passed"] = all(c["assessment"].get("gate_passed", True) for c in result["cells"])
    save()
    return audit_stage(plan, digest, out_dir, stage)


def summarize_pilot(plan: dict, result: dict) -> dict:
    by_id = {c["id"]: c for c in result["cells"]}
    summaries, contrasts = [], []
    for pressure in plan["spec"]["archive_distractors"]:
        cells = [c for c in plan["cells"] if c["stage"] == "pilot" and c["archive_distractors"] == pressure]
        for arm in CONDITIONS:
            rows = [c for c in cells if c["condition"] == arm]
            counts = Counter()
            for c in rows:
                a = by_id[c["id"]]["assessment"]
                for k in ("schema_ok", "grounded_success", "recovered", "safe_abstention"):
                    counts[k] += bool(a[k])
                counts["support_visible"] += c["support_visible"]
                if c["regime"] == "insufficient":
                    counts["insufficient_correct_abstention"] += a["grounded_success"]
                elif c["regime"] in {"delayed", "interference"}:
                    counts["old_evidence_success"] += a["grounded_success"]
                    counts["old_evidence_visible"] += c["support_visible"]
            summaries.append({"archive_distractors": pressure, "condition": arm, "cases": len(rows), **dict(counts)})
        for control in ("archive-recent", "scratchpad-retrieve"):
            pairs, outcomes = [], Counter()
            for c in cells:
                if c["condition"] != "linked-retrieve" or c["regime"] not in {"delayed", "interference"}:
                    continue
                other = by_id[c["case_id"] + ":" + control]["assessment"]["grounded_success"]
                treatment = by_id[c["id"]]["assessment"]["grounded_success"]
                outcomes["both" if treatment and other else "linked_only" if treatment else "control_only" if other else "neither"] += 1
                pairs.append({"case_id": c["case_id"], "delta": int(treatment) - int(other)})
            deltas = [p["delta"] for p in pairs]
            contrasts.append({"archive_distractors": pressure, "control": control, "pairs": pairs,
                              "mean_delta": sum(deltas) / len(deltas),
                              "bootstrap_95": paired_bootstrap_mean_interval(deltas), "outcomes": dict(outcomes)})
    return {"method": plan["method"], "scope": "Synthetic read-path pilot; tiers share task semantics, not independent replications.",
            "conditions": summaries, "contrasts": contrasts, "usage": result["usage"]}
