from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from .centerline import analyze_centerline, render_centerline_hints
from .chat import append_trace_events, llm_trace, run_chat_turn
from .experiments import add_run_id, make_run_id, write_manifest
from .llm import call_llm_result, config_with_output_token_limit, llm_config_metadata
from .storage import ensure_root, ensure_thread_dirs, load_llm_config, now_iso, safe_id
from .text import limit_text_tail

DIALOGUE_CONDITIONS = {
    "raw-raw": ("raw", "raw"),
    "raw-scratchpad": ("raw", "scratchpad"),
    "scratchpad-raw": ("scratchpad", "raw"),
    "scratchpad-scratchpad": ("scratchpad", "scratchpad"),
    "centerline-only": ("centerline-only", "centerline-only"),
    "write-no-recall": ("write-no-recall", "write-no-recall"),
    "probe-top1": ("probe-top1", "probe-top1"),
    "probe-top2": ("probe-top2", "probe-top2"),
}
DEFAULT_DIALOGUE_CONDITIONS = (
    "raw-raw",
    "raw-scratchpad",
    "scratchpad-scratchpad",
)
ABLATION_DIALOGUE_CONDITIONS = (
    "raw-raw",
    "centerline-only",
    "write-no-recall",
    "scratchpad-scratchpad",
)
MECHANISM_DIALOGUE_CONDITIONS = (
    "write-no-recall",
    "probe-top1",
    "probe-top2",
    "scratchpad-scratchpad",
)
PLAIN_DIALOGUE_MODES = frozenset({"raw", "centerline-only"})
SCRATCHPAD_DIALOGUE_MODES = frozenset(
    {"scratchpad", "write-no-recall", "probe-top1", "probe-top2"}
)
RELATION_PROBE_METHOD = "marker-role-order-v1"


def load_dialogue_scenario(path: Path) -> dict:
    path = path.expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"Dialogue scenario not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Dialogue scenario is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Dialogue scenario must be one JSON object.")

    scenario = dict(data)
    scenario.setdefault("id", path.stem)
    scenario.setdefault("title", scenario["id"])
    for field in ("agenda", "opening"):
        if not str(scenario.get(field, "")).strip():
            raise SystemExit(f"Dialogue scenario requires a non-empty {field!r} field.")

    try:
        default_turns = int(scenario.get("default_turns", 8))
    except (TypeError, ValueError) as exc:
        raise SystemExit("Dialogue scenario default_turns must be an integer.") from exc
    if default_turns < 2:
        raise SystemExit("Dialogue scenario default_turns must be at least 2.")
    scenario["default_turns"] = default_turns
    try:
        max_reply_chars = int(scenario.get("max_reply_chars", 180))
    except (TypeError, ValueError) as exc:
        raise SystemExit("Dialogue scenario max_reply_chars must be an integer.") from exc
    if max_reply_chars < 40:
        raise SystemExit("Dialogue scenario max_reply_chars must be at least 40.")
    scenario["max_reply_chars"] = max_reply_chars

    interventions: list[dict] = []
    for item in scenario.get("interventions", []):
        if not isinstance(item, dict):
            raise SystemExit("Each dialogue intervention must be a JSON object.")
        try:
            before_turn = int(item.get("before_turn"))
        except (TypeError, ValueError) as exc:
            raise SystemExit("Dialogue intervention before_turn must be an integer.") from exc
        message = str(item.get("message", "")).strip()
        if before_turn < 1 or not message:
            raise SystemExit("Dialogue interventions require before_turn >= 1 and a message.")
        interventions.append({"before_turn": before_turn, "message": message})
    scenario["interventions"] = interventions
    scenario["anchors"] = [str(item).strip() for item in scenario.get("anchors", []) if str(item).strip()]
    scenario["review_questions"] = [
        str(item).strip() for item in scenario.get("review_questions", []) if str(item).strip()
    ]
    literal_probes: list[dict] = []
    for item in scenario.get("literal_probes", []):
        if not isinstance(item, dict):
            raise SystemExit("Each dialogue literal probe must be a JSON object.")
        probe_id = str(item.get("id", "")).strip()
        try:
            probe_turn = int(item.get("turn"))
        except (TypeError, ValueError) as exc:
            raise SystemExit("Dialogue literal probe turn must be an integer.") from exc
        match = str(item.get("match", "all")).strip().lower()
        terms = [str(term).strip() for term in item.get("terms", []) if str(term).strip()]
        if not probe_id or probe_turn < 1 or not terms or match not in {"all", "any"}:
            raise SystemExit(
                "Dialogue literal probes require id, turn >= 1, non-empty terms, "
                "and match=all|any."
            )
        literal_probes.append(
            {"id": probe_id, "turn": probe_turn, "match": match, "terms": terms}
        )
    scenario["literal_probes"] = literal_probes

    relation_probes: list[dict] = []
    for item in scenario.get("relation_probes", []):
        if not isinstance(item, dict):
            raise SystemExit("Each dialogue relation probe must be a JSON object.")
        probe_id = str(item.get("id", "")).strip()
        try:
            probe_turn = int(item.get("turn"))
            max_marker_gap = int(item.get("max_marker_gap", 80))
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                "Dialogue relation probe turn and max_marker_gap must be integers."
            ) from exc
        before_markers = [
            str(value).strip()
            for value in item.get("before_markers", ["変更前"])
            if str(value).strip()
        ]
        before_terms = [
            str(value).strip() for value in item.get("before_terms", []) if str(value).strip()
        ]
        after_markers = [
            str(value).strip()
            for value in item.get("after_markers", ["変更後"])
            if str(value).strip()
        ]
        after_terms = [
            str(value).strip() for value in item.get("after_terms", []) if str(value).strip()
        ]
        boundary_terms = [
            str(value).strip()
            for value in item.get("boundary_terms", [])
            if str(value).strip()
        ]
        boundary_match = str(item.get("boundary_match", "any")).strip().lower()
        if (
            not probe_id
            or probe_turn < 1
            or max_marker_gap < 1
            or not before_markers
            or not before_terms
            or not after_markers
            or not after_terms
            or not boundary_terms
            or boundary_match not in {"all", "any"}
        ):
            raise SystemExit(
                "Dialogue relation probes require id, turn >= 1, before/after markers "
                "and terms, boundary_terms, boundary_match=all|any, and max_marker_gap >= 1."
            )
        relation_probes.append(
            {
                "id": probe_id,
                "turn": probe_turn,
                "before_markers": before_markers,
                "before_terms": before_terms,
                "after_markers": after_markers,
                "after_terms": after_terms,
                "boundary_terms": boundary_terms,
                "boundary_match": boundary_match,
                "max_marker_gap": max_marker_gap,
            }
        )
    scenario["relation_probes"] = relation_probes

    selective_raw = scenario.get("selective_recall", {})
    if selective_raw is None:
        selective_raw = {}
    if not isinstance(selective_raw, dict):
        raise SystemExit("Dialogue selective_recall must be one JSON object.")
    default_recall_turns = sorted(
        {
            int(item["turn"])
            for item in [*literal_probes, *relation_probes]
        }
    )
    try:
        selective_turns = sorted(
            {int(value) for value in selective_raw.get("turns", default_recall_turns)}
        )
        selective_max_chars = int(selective_raw.get("max_chars_per_doc", 700))
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            "Dialogue selective_recall turns and max_chars_per_doc must be integers."
        ) from exc
    selective_query_source = str(
        selective_raw.get("query_source", "current-message")
    ).strip().lower()
    if (
        any(turn < 1 for turn in selective_turns)
        or selective_max_chars < 1
        or selective_query_source not in {"current-message", "intervention"}
    ):
        raise SystemExit(
            "Dialogue selective_recall requires turns >= 1, max_chars_per_doc >= 1, "
            "and query_source=current-message|intervention."
        )
    intervention_turns = {int(item["before_turn"]) for item in interventions}
    if selective_query_source == "intervention":
        missing_interventions = [
            turn for turn in selective_turns if turn not in intervention_turns
        ]
        if missing_interventions:
            raise SystemExit(
                "Dialogue selective_recall query_source=intervention requires an "
                f"intervention at every recall turn; missing {missing_interventions}."
            )
    scenario["selective_recall"] = {
        "turns": selective_turns,
        "max_chars_per_doc": selective_max_chars,
        "query_source": selective_query_source,
    }
    scenario["_path"] = str(path)
    return scenario


def dialogue_scenario_hash(scenario: dict) -> str:
    public = {key: value for key, value in scenario.items() if not key.startswith("_")}
    payload = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_condition_name(name: str) -> str:
    normalized = name.strip().lower().replace("_", "-").replace("/", "-")
    aliases = {
        "raw-sr": "raw-scratchpad",
        "sr-raw": "scratchpad-raw",
        "sr-sr": "scratchpad-scratchpad",
        "raw": "raw-raw",
        "centerline": "centerline-only",
        "full": "scratchpad-scratchpad",
        "full-scratchpad": "scratchpad-scratchpad",
        "write-only": "write-no-recall",
        "probe-only": "probe-top1",
        "selective": "probe-top1",
        "selective-recall": "probe-top1",
        "selective-top2": "probe-top2",
    }
    return aliases.get(normalized, normalized)


def resolve_dialogue_conditions(
    value: str | None,
    mirror_mixed: bool = True,
    preset: str = "matrix",
) -> list[str]:
    if preset not in {"matrix", "ablation", "mechanism"}:
        raise SystemExit(f"Unknown dialogue preset: {preset!r}")
    defaults = {
        "matrix": DEFAULT_DIALOGUE_CONDITIONS,
        "ablation": ABLATION_DIALOGUE_CONDITIONS,
        "mechanism": MECHANISM_DIALOGUE_CONDITIONS,
    }[preset]
    requested = (
        [part for part in str(value).split(",") if part.strip()]
        if value
        else list(defaults)
    )
    conditions: list[str] = []
    for raw in requested:
        name = normalize_condition_name(raw)
        if name not in DIALOGUE_CONDITIONS:
            available = ", ".join(DIALOGUE_CONDITIONS)
            raise SystemExit(f"Unknown dialogue condition: {raw!r}. Available: {available}")
        if name not in conditions:
            conditions.append(name)

    if mirror_mixed:
        if "raw-scratchpad" in conditions and "scratchpad-raw" not in conditions:
            index = conditions.index("raw-scratchpad") + 1
            conditions.insert(index, "scratchpad-raw")
        elif "scratchpad-raw" in conditions and "raw-scratchpad" not in conditions:
            index = conditions.index("scratchpad-raw") + 1
            conditions.insert(index, "raw-scratchpad")
    return conditions


def dialogue_condition_order(
    conditions: list[str],
    replicate: int,
    rotate: bool = False,
) -> list[str]:
    if replicate < 1:
        raise SystemExit("Dialogue replicate index must be at least 1.")
    ordered = list(conditions)
    if not rotate or len(ordered) < 2:
        return ordered
    offset = (replicate - 1) % len(ordered)
    return ordered[offset:] + ordered[:offset]


def dialogue_budget_plan(
    conditions: list[str],
    turns: int,
    replicates: int,
    turn_output_tokens: int,
    max_steps: int,
    json_repair_steps: int,
    alternate_starter: bool = False,
    rotate_condition_order: bool = False,
) -> dict:
    if turns < 2:
        raise SystemExit("Dialogue turns must be at least 2.")
    if replicates < 1:
        raise SystemExit("Dialogue replicates must be at least 1.")
    if turn_output_tokens < 1:
        raise SystemExit("Turn output token budget must be positive.")
    if max_steps < 0 or json_repair_steps < 0:
        raise SystemExit("max_steps and json_repair_steps must be non-negative.")

    scratchpad_call_cap = 1 + max_steps + json_repair_steps
    scratchpad_final_reserve_tokens = max(1, turn_output_tokens // 3)
    scratchpad_call_output_tokens = max(
        1,
        turn_output_tokens - scratchpad_final_reserve_tokens,
    )
    worst_api_calls = 0
    mode_turns = {mode: 0 for modes in DIALOGUE_CONDITIONS.values() for mode in modes}
    sessions = len(conditions) * replicates
    condition_orders: list[dict] = []
    for replicate in range(1, replicates + 1):
        starter_index = 1 if alternate_starter and replicate % 2 == 0 else 0
        ordered_conditions = dialogue_condition_order(
            conditions,
            replicate,
            rotate=rotate_condition_order,
        )
        condition_orders.append(
            {"replicate": replicate, "conditions": ordered_conditions}
        )
        for condition in ordered_conditions:
            modes = DIALOGUE_CONDITIONS[condition]
            for turn in range(1, turns + 1):
                mode_index = starter_index if turn % 2 == 1 else 1 - starter_index
                mode = modes[mode_index]
                mode_turns[mode] += 1
                call_cap = 1 if mode in PLAIN_DIALOGUE_MODES else scratchpad_call_cap
                worst_api_calls += call_cap
    accepted_output_tokens = sessions * turns * turn_output_tokens
    repair_output_tokens = (
        sum(mode_turns[mode] for mode in SCRATCHPAD_DIALOGUE_MODES)
        * json_repair_steps
        * scratchpad_call_output_tokens
    )
    return {
        "sessions": sessions,
        "turns_per_session": turns,
        "utterances": sessions * turns,
        "mode_turns": mode_turns,
        "turn_output_tokens": turn_output_tokens,
        "max_output_tokens_per_session": turns * turn_output_tokens,
        "max_output_tokens_suite": accepted_output_tokens,
        "max_repair_output_tokens_suite": repair_output_tokens,
        "max_provider_output_tokens_suite": accepted_output_tokens + repair_output_tokens,
        "scratchpad_model_calls_per_turn": scratchpad_call_cap,
        "scratchpad_output_tokens_per_call": scratchpad_call_output_tokens,
        "scratchpad_final_reserve_tokens": scratchpad_final_reserve_tokens,
        "worst_api_calls": worst_api_calls,
        "condition_orders": condition_orders,
    }


def empty_usage() -> dict:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated": False,
    }


def add_usage(total: dict, usage: dict | None) -> None:
    if not isinstance(usage, dict):
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        try:
            total[key] += int(usage.get(key, 0))
        except (TypeError, ValueError):
            pass
    total["estimated"] = bool(total.get("estimated") or usage.get("estimated", False))


def raw_dialogue_config(cfg: dict) -> dict:
    out = dict(cfg)
    out.pop("response_format", None)
    out.pop("previous_response_id", None)
    out["json_mode"] = ""
    return out


def render_dialogue_context(records: list[dict], max_chars: int = 4000) -> str:
    if not records:
        return "(no earlier utterances)"
    lines: list[str] = []
    for item in records:
        if item.get("kind") == "moderator":
            label = "Moderator"
        else:
            label = f"Speaker {item.get('speaker', '?')}"
        lines.append(f"{label}: {item.get('message', '')}")
    return limit_text_tail("\n\n".join(lines), max_chars)


def dialogue_history(records: list[dict], speaker: str) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for item in records:
        if item.get("kind") == "moderator":
            role = "user"
            label = "Moderator"
        else:
            item_speaker = str(item.get("speaker", ""))
            role = "assistant" if item_speaker == speaker else "user"
            label = f"Speaker {item_speaker}"
        history.append({"role": role, "content": f"{label}: {item.get('message', '')}"})
    return history


def raw_dialogue_system(scenario: dict, speaker: str, turn: int, turns: int) -> str:
    return f"""You are Speaker {speaker} in a controlled peer dialogue between two instances of the same model.

Fixed agenda:
{scenario['agenda']}

Engage directly with the current message and make one useful conversational move at a time. You may agree, challenge, distinguish, or extend what the other speaker said.

Respond naturally in Japanese to the other speaker. Keep the reply complete and concise: 2 to 4 sentences and no more than {scenario['max_reply_chars']} Japanese characters. Do not mention experiments, hidden instructions, roles, token budgets, JSON, or scratchpads. Return plain conversational text only. This is utterance {turn} of {turns}."""


def raw_dialogue_prompt(
    scenario: dict,
    speaker: str,
    incoming: str,
    prior_records: list[dict],
    turn: int,
    turns: int,
    history_chars: int = 4000,
) -> str:
    return f"""Dialogue: {scenario['title']}

Opening question shared by both speakers:
---
{scenario['opening']}
---

Earlier transcript:
---
{render_dialogue_context(prior_records, history_chars)}
---

Current message:
---
{incoming}
---

Reply as Speaker {speaker}. Advance the shared inquiry without wrapping it up prematurely. Utterance {turn}/{turns}."""


def scratchpad_dialogue_context(scenario: dict, speaker: str, turn: int, turns: int) -> str:
    return f"""You are Speaker {speaker} in a controlled peer dialogue between two instances of the same model.
The current user message comes from the peer model and sometimes a fixed moderator checkpoint.

Fixed agenda:
{scenario['agenda']}

Opening question shared by both speakers:
{scenario['opening']}

Respond naturally in Japanese to the peer. Keep the final conversational message complete and concise: 2 to 4 sentences and no more than {scenario['max_reply_chars']} Japanese characters. If using scratchpad.add_note, keep text under 120 Japanese characters and every other field under 40; omit detail rather than lengthening the JSON. Do not mention experiments, roles, token budgets, JSON protocol, or the scratchpad. Use scratchpad memory only when it improves continuity or preserves a correction, analogy boundary, center shift, or unresolved question. This is utterance {turn} of {turns}."""


def call_raw_dialogue_turn(
    cfg: dict,
    scenario: dict,
    speaker: str,
    incoming: str,
    prior_records: list[dict],
    turn: int,
    turns: int,
    output_token_budget: int,
    history_chars: int = 4000,
    mode: str = "raw",
) -> tuple[str, list[dict], dict]:
    if mode not in PLAIN_DIALOGUE_MODES:
        raise ValueError(f"Unsupported plain dialogue mode: {mode}")
    started = time.perf_counter()
    system_prompt = raw_dialogue_system(scenario, speaker, turn, turns)
    history = dialogue_history(prior_records, speaker)
    centerline = analyze_centerline(incoming, history)
    if mode == "centerline-only":
        system_prompt += (
            "\nUse these deterministic centerline hints silently. They are navigation aids, "
            "not claims to repeat:\n---\n"
            + render_centerline_hints(centerline)
            + "\n---\n"
        )
    prompt = raw_dialogue_prompt(
        scenario,
        speaker,
        incoming,
        prior_records,
        turn,
        turns,
        history_chars=history_chars,
    )
    call_cfg = config_with_output_token_limit(raw_dialogue_config(cfg), output_token_budget)
    events = [
        {
            "time": now_iso(),
            "event": "turn_start",
            "speaker": speaker,
            "mode": mode,
            "turn": turn,
            "output_token_budget": output_token_budget,
            "llm": llm_config_metadata(call_cfg),
        },
        {
            "time": now_iso(),
            "event": "centerline",
            "speaker": speaker,
            "mode": mode,
            "turn": turn,
            "provider_visible": mode == "centerline-only",
            **centerline,
        },
        {
            "time": now_iso(),
            "event": "model_request",
            "speaker": speaker,
            "mode": mode,
            "turn": turn,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "remaining_output_tokens": output_token_budget,
            "history_chars": history_chars,
            "llm": llm_config_metadata(call_cfg),
        },
    ]
    try:
        result = call_llm_result(call_cfg, prompt, system_prompt)
    except SystemExit as exc:
        events.append(
            {
                "time": now_iso(),
                "event": "error",
                "speaker": speaker,
                "mode": mode,
                "turn": turn,
                "error": str(exc),
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )
        raise
    message = str(result.get("content", "")).strip()
    if not message:
        raise SystemExit("Raw dialogue model returned an empty response.")
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    events.extend(
        [
            {
                "time": now_iso(),
                "event": "model_output",
                "speaker": speaker,
                "mode": mode,
                "turn": turn,
                "raw_output": message,
                "raw_output_chars": len(message),
                "llm": llm_trace(result),
            },
            {
                "time": now_iso(),
                "event": "final",
                "speaker": speaker,
                "mode": mode,
                "turn": turn,
                "message": message,
                "model_calls": 1,
                "tool_steps": 0,
                "duration_ms": duration_ms,
            },
        ]
    )
    summary = {
        "status": "ok",
        "model_calls": 1,
        "tool_steps": 0,
        "tool_actions": [],
        "memory_writes": 0,
        "centerline_flags": sorted(set(centerline.get("flags", []))),
        "usage": dict(result.get("usage", {})),
        "duration_ms": duration_ms,
    }
    return message, events, summary


def summarize_scratchpad_turn(events: list[dict], message: str) -> dict:
    usage = empty_usage()
    tool_actions: list[str] = []
    memory_writes = 0
    memory_context_injections = 0
    retrieval_context_injections = 0
    retrieval_context_sources = 0
    retrieval_context_chars = 0
    protocol_recoveries = 0
    json_parse_errors = 0
    centerline_flags: list[str] = []
    model_calls = 0
    tool_steps = 0
    duration_ms = 0.0
    status = "ok"
    for event in events:
        name = event.get("event")
        if name in {"model_output", "json_parse_error"}:
            model_calls += 1
            llm = event.get("llm")
            if isinstance(llm, dict):
                add_usage(usage, llm.get("usage"))
        if name == "tool_observation" and not event.get("duplicate_request"):
            tool_steps += 1
            action = str(event.get("action", ""))
            tool_actions.append(action)
            if action == "scratchpad.add_note" and "wrote turn" in str(event.get("observation", "")):
                memory_writes += 1
        if name == "turn_start" and event.get("recent_context_present"):
            memory_context_injections += 1
            if event.get("memory_context_mode") == "retrieved":
                retrieval_context_injections += 1
                retrieval_context_sources += int(event.get("recent_context_sources", 0))
                retrieval_context_chars += int(event.get("recent_context_chars", 0))
        if name == "json_protocol_recovery":
            protocol_recoveries += 1
        if name == "json_parse_error":
            json_parse_errors += 1
        if name == "centerline":
            centerline_flags.extend(str(flag) for flag in event.get("flags", []))
        if name in {"final", "stopped", "error"}:
            try:
                duration_ms = float(event.get("duration_ms", duration_ms))
            except (TypeError, ValueError):
                pass
        if name in {"stopped", "error"}:
            status = "stopped"
    if message.startswith("(chat runtime stopped:"):
        status = "stopped"
    return {
        "status": status,
        "model_calls": model_calls,
        "tool_steps": tool_steps,
        "tool_actions": tool_actions,
        "memory_writes": memory_writes,
        "memory_context_injections": memory_context_injections,
        "retrieval_context_injections": retrieval_context_injections,
        "retrieval_context_sources": retrieval_context_sources,
        "retrieval_context_chars": retrieval_context_chars,
        "protocol_recoveries": protocol_recoveries,
        "json_parse_errors": json_parse_errors,
        "centerline_flags": sorted(set(centerline_flags)),
        "usage": usage,
        "duration_ms": duration_ms,
    }


def tag_dialogue_events(
    events: list[dict],
    run_id: str,
    session_id: str,
    condition: str,
    turn: int,
    speaker: str,
    mode: str,
) -> list[dict]:
    add_run_id(events, run_id)
    for event in events:
        event.setdefault("session_id", session_id)
        event.setdefault("condition", condition)
        event.setdefault("dialogue_turn", turn)
        event.setdefault("speaker", speaker)
        event.setdefault("mode", mode)
    return events


def append_jsonl(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def anchor_coverage(records: list[dict], anchors: list[str]) -> dict:
    transcript = "\n".join(
        str(item.get("message", "")) for item in records if item.get("kind") == "utterance"
    )
    folded = re.sub(r"\s+", "", transcript).casefold()
    found = [anchor for anchor in anchors if re.sub(r"\s+", "", anchor).casefold() in folded]
    return {
        "found": found,
        "missing": [anchor for anchor in anchors if anchor not in found],
        "count": len(found),
        "total": len(anchors),
    }


def literal_probe_evidence(records: list[dict], probes: list[dict]) -> dict:
    utterances = {
        int(item["turn"]): item
        for item in records
        if item.get("kind") == "utterance" and isinstance(item.get("turn"), int)
    }
    results: list[dict] = []
    for probe in probes:
        record = utterances.get(int(probe["turn"]))
        message = str(record.get("message", "")) if record else ""
        folded = re.sub(r"\s+", "", message).casefold()
        found = [
            term
            for term in probe["terms"]
            if re.sub(r"\s+", "", term).casefold() in folded
        ]
        passed = len(found) == len(probe["terms"])
        if probe["match"] == "any":
            passed = bool(found)
        results.append(
            {
                **probe,
                "speaker": record.get("speaker") if record else None,
                "found": found,
                "missing": [term for term in probe["terms"] if term not in found],
                "passed": passed,
            }
        )
    return {
        "passed": sum(1 for item in results if item["passed"]),
        "total": len(results),
        "results": results,
    }


def _all_positions(text: str, needle: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while needle:
        position = text.find(needle, start)
        if position < 0:
            break
        positions.append(position)
        start = position + 1
    return positions


def _role_matches(
    text: str,
    markers: list[str],
    terms: list[str],
    max_gap: int,
    stop_markers: list[str],
) -> list[dict]:
    matches: list[dict] = []
    for marker in markers:
        folded_marker = re.sub(r"\s+", "", marker).casefold()
        for marker_position in _all_positions(text, folded_marker):
            marker_end = marker_position + len(folded_marker)
            next_marker_positions = [
                position
                for stop_marker in stop_markers
                for position in _all_positions(
                    text,
                    re.sub(r"\s+", "", stop_marker).casefold(),
                )
                if position >= marker_end
            ]
            window_end = min(next_marker_positions, default=len(text))
            for term in terms:
                folded_term = re.sub(r"\s+", "", term).casefold()
                for term_position in _all_positions(text, folded_term):
                    gap = term_position - marker_end
                    if 0 <= gap <= max_gap and term_position < window_end:
                        matches.append(
                            {
                                "marker": marker,
                                "term": term,
                                "marker_position": marker_position,
                                "term_position": term_position,
                                "gap": gap,
                            }
                        )
    return sorted(
        matches,
        key=lambda item: (
            int(item["marker_position"]),
            int(item["term_position"]),
            str(item["marker"]),
            str(item["term"]),
        ),
    )


def relation_probe_evidence(records: list[dict], probes: list[dict]) -> dict:
    utterances = {
        int(item["turn"]): item
        for item in records
        if item.get("kind") == "utterance" and isinstance(item.get("turn"), int)
    }
    results: list[dict] = []
    for probe in probes:
        record = utterances.get(int(probe["turn"]))
        message = str(record.get("message", "")) if record else ""
        folded = re.sub(r"\s+", "", message).casefold()
        before_matches = _role_matches(
            folded,
            probe["before_markers"],
            probe["before_terms"],
            int(probe["max_marker_gap"]),
            [*probe["before_markers"], *probe["after_markers"]],
        )
        after_matches = _role_matches(
            folded,
            probe["after_markers"],
            probe["after_terms"],
            int(probe["max_marker_gap"]),
            [*probe["before_markers"], *probe["after_markers"]],
        )
        reversed_before = _role_matches(
            folded,
            probe["before_markers"],
            probe["after_terms"],
            int(probe["max_marker_gap"]),
            [*probe["before_markers"], *probe["after_markers"]],
        )
        reversed_after = _role_matches(
            folded,
            probe["after_markers"],
            probe["before_terms"],
            int(probe["max_marker_gap"]),
            [*probe["before_markers"], *probe["after_markers"]],
        )
        order_passed = any(
            int(before["marker_position"]) < int(after["marker_position"])
            for before in before_matches
            for after in after_matches
        )
        boundary_found = [
            term
            for term in probe["boundary_terms"]
            if re.sub(r"\s+", "", term).casefold() in folded
        ]
        boundary_passed = len(boundary_found) == len(probe["boundary_terms"])
        if probe["boundary_match"] == "any":
            boundary_passed = bool(boundary_found)
        reversed_roles = bool(reversed_before or reversed_after)
        passed = bool(
            before_matches
            and after_matches
            and order_passed
            and boundary_passed
            and not reversed_roles
        )
        results.append(
            {
                **probe,
                "speaker": record.get("speaker") if record else None,
                "before_matches": before_matches,
                "after_matches": after_matches,
                "order_passed": order_passed,
                "boundary_found": boundary_found,
                "boundary_missing": [
                    term for term in probe["boundary_terms"] if term not in boundary_found
                ],
                "boundary_passed": boundary_passed,
                "reversed_roles": reversed_roles,
                "passed": passed,
            }
        )
    return {
        "passed": sum(1 for item in results if item["passed"]),
        "total": len(results),
        "results": results,
    }


def transcript_markdown(scenario: dict, session: dict, records: list[dict]) -> str:
    lines = [
        f"# {scenario['title']}",
        "",
        f"- Session: {session['session_id']}",
        f"- Condition: {session['condition']}",
        f"- Speaker A: {session['speaker_modes']['A']}",
        f"- Speaker B: {session['speaker_modes']['B']}",
        f"- Starting speaker: {session['starting_speaker']}",
        f"- Recent dialogue window: {session['history_chars']} characters",
        f"- Per-utterance output budget: {session['turn_output_tokens']} tokens",
        "",
        "## Opening",
        "",
        str(scenario["opening"]),
        "",
        "## Transcript",
        "",
    ]
    for item in records:
        if item.get("kind") == "moderator":
            lines.extend([f"### Moderator before turn {item['before_turn']}", "", item["message"], ""])
            continue
        lines.extend(
            [
                f"### Turn {item['turn']}: Speaker {item['speaker']} ({item['mode']})",
                "",
                item["message"],
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def dialogue_report_markdown(result: dict) -> str:
    plan = result["budget_plan"]
    lines = [
        "# Model Dialogue Experiment Report",
        "",
        f"- Run id: {result['run_id']}",
        f"- Status: {result['status']}",
        f"- Scenario: {result['scenario']['title']}",
        f"- Profile: {result['llm']['profile']}",
        f"- Model: {result['llm']['model']}",
        f"- Adapter: {result['llm']['adapter']}",
        f"- Sessions: {plan['sessions']}",
        f"- Utterances per session: {plan['turns_per_session']}",
        f"- Shared output budget per utterance: {plan['turn_output_tokens']} tokens",
        f"- Recent dialogue window: {result['history_chars']} characters (newest text retained)",
        f"- Scratchpad action/repair per-call cap: {plan['scratchpad_output_tokens_per_call']} tokens",
        f"- Scratchpad final reserve: {plan['scratchpad_final_reserve_tokens']} tokens",
        f"- Accepted-output allowance: {plan['max_output_tokens_suite']} tokens",
        f"- JSON-repair reserve: {plan['max_repair_output_tokens_suite']} tokens",
        f"- Provider-output ceiling: {plan['max_provider_output_tokens_suite']} tokens",
        f"- Worst-case API calls: {plan['worst_api_calls']}",
        "",
        "The accepted output-token allowance is pooled across valid internal calls in each scratchpad utterance. Invalid JSON is charged to a separate bounded repair reserve; provider usage reports both. Input tokens are intentionally reported separately because prompt and memory overhead are part of the treatment cost.",
        "",
        "## Conditions",
        "",
        "| Session | Start | A | B | Status | Calls | Tools | Writes | Memory ctx | Retrieval ctx | Recoveries | Parse errors | Prompt tok | Output tok | Anchors | Literal | Relation |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for session in result.get("sessions", []):
        usage = session.get("usage", {})
        coverage = session.get("anchor_coverage", {})
        probes = session.get("literal_probe_evidence", {})
        relations = session.get("relation_probe_evidence", {})
        lines.append(
            "| {session_id} | {start} | {a} | {b} | {status} | {calls} | {tools} | {writes} | {memory_ctx} | {retrieval_ctx} | {recoveries} | {parse_errors} | {prompt} | {completion} | {found}/{total} | {probe_passed}/{probe_total} | {relation_passed}/{relation_total} |".format(
                session_id=session["session_id"],
                start=session["starting_speaker"],
                a=session["speaker_modes"]["A"],
                b=session["speaker_modes"]["B"],
                status=session["status"],
                calls=session["model_calls"],
                tools=session["tool_steps"],
                writes=session["memory_writes"],
                memory_ctx=session["memory_context_injections"],
                retrieval_ctx=session.get("retrieval_context_injections", 0),
                recoveries=session["protocol_recoveries"],
                parse_errors=session["json_parse_errors"],
                prompt=usage.get("prompt_tokens", 0),
                completion=usage.get("completion_tokens", 0),
                found=coverage.get("count", 0),
                total=coverage.get("total", 0),
                probe_passed=probes.get("passed", 0),
                probe_total=probes.get("total", 0),
                relation_passed=relations.get("passed", 0),
                relation_total=relations.get("total", 0),
            )
        )
    lines.extend(
        [
            "",
            "## Review Lenses",
            "",
            "Raw/raw is the sampling baseline. Centerline-only adds deterministic navigation without the JSON/tool protocol. Write-no-recall uses the same writing runtime but blocks every read path and injects no saved notes. Probe-top1 and probe-top2 keep those read actions blocked and inject only the top one or two lexical hits at frozen probe turns. Scratchpad/scratchpad enables writing plus recent-note recall throughout. Mixed sessions, when selected, expose position effects.",
            "",
        ]
    )
    for question in result["scenario"].get("review_questions", []):
        lines.append(f"- {question}")
    lines.extend(
        [
            "",
            "Literal probes report exact term presence. Relation probes additionally require before/after role assignment, order, and a stated boundary term. Neither is a complete semantic quality score. No automatic quality winner is declared, and transcripts plus deterministic usage/tool evidence remain separate from interpretation.",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def run_dialogue_matrix(
    root: Path,
    scenario_path: Path,
    profile: str,
    llm_config: str | None,
    out_dir: Path,
    conditions: list[str],
    turns: int | None,
    replicates: int,
    turn_output_tokens: int,
    max_steps: int,
    recent_n: int,
    max_tool_chars: int,
    json_repair_steps: int,
    policy: str,
    max_api_calls: int,
    max_suite_output_tokens: int,
    quiet: bool,
    history_chars: int = 900,
    alternate_starter: bool = False,
    rotate_condition_order: bool = False,
) -> dict:
    ensure_root(root)
    scenario = load_dialogue_scenario(scenario_path)
    turn_count = int(turns if turns is not None else scenario["default_turns"])
    plan = dialogue_budget_plan(
        conditions,
        turn_count,
        replicates,
        turn_output_tokens,
        max_steps,
        json_repair_steps,
        alternate_starter=alternate_starter,
        rotate_condition_order=rotate_condition_order,
    )
    if max_api_calls < 1:
        raise SystemExit("max_api_calls must be positive.")
    if plan["worst_api_calls"] > max_api_calls:
        raise SystemExit(
            f"Dialogue preflight refused {plan['worst_api_calls']} worst-case API calls; "
            f"--max-api-calls is {max_api_calls}."
        )
    if max_suite_output_tokens < 1:
        raise SystemExit("max_suite_output_tokens must be positive.")
    if plan["max_provider_output_tokens_suite"] > max_suite_output_tokens:
        raise SystemExit(
            f"Dialogue preflight refused {plan['max_provider_output_tokens_suite']} worst-case provider output tokens; "
            f"--max-suite-output-tokens is {max_suite_output_tokens}."
        )
    if history_chars < 1:
        raise SystemExit("history_chars must be positive.")

    cfg = load_llm_config(root, llm_config, profile)
    run_id = make_run_id("dialogue")
    out_dir = out_dir.expanduser().resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"Dialogue output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    public_scenario = {key: value for key, value in scenario.items() if not key.startswith("_")}
    scenario_hash = dialogue_scenario_hash(scenario)
    (out_dir / "scenario.snapshot.json").write_text(
        json.dumps(public_scenario, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    result: dict = {
        "run_id": run_id,
        "status": "running",
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "root": str(root),
        "out_dir": str(out_dir),
        "scenario_path": str(scenario["_path"]),
        "scenario_sha256": scenario_hash,
        "dialogue_runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scenario": public_scenario,
        "llm": llm_config_metadata(cfg),
        "policy": policy,
        "history_chars": history_chars,
        "alternate_starter": alternate_starter,
        "rotate_condition_order": rotate_condition_order,
        "budget_plan": plan,
        "limits": {
            "max_api_calls": max_api_calls,
            "max_suite_output_tokens": max_suite_output_tokens,
        },
        "sessions": [],
    }
    suite_manifest_path = out_dir / "suite_manifest.json"
    write_manifest(suite_manifest_path, result)

    abort = False
    for replicate in range(1, replicates + 1):
        ordered_conditions = dialogue_condition_order(
            conditions,
            replicate,
            rotate=rotate_condition_order,
        )
        for condition_position, condition in enumerate(ordered_conditions, start=1):
            modes = DIALOGUE_CONDITIONS[condition]
            session_id = safe_id(f"{condition}-r{replicate:02d}")
            session_dir = out_dir / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            trace_path = session_dir / "trace.jsonl"
            transcript_path = session_dir / "transcript.jsonl"
            transcript_md_path = session_dir / "transcript.md"
            session_manifest_path = session_dir / "manifest.json"
            speaker_modes = {"A": modes[0], "B": modes[1]}
            starting_speaker = "B" if alternate_starter and replicate % 2 == 0 else "A"
            scratchpads: dict[str, tuple[Path, Path, str]] = {}
            for speaker in ("A", "B"):
                if speaker_modes[speaker] not in SCRATCHPAD_DIALOGUE_MODES:
                    continue
                scratch_root = session_dir / "scratchpads" / f"speaker-{speaker.lower()}"
                thread_id = safe_id(f"{session_id}-speaker-{speaker.lower()}")
                tdir = ensure_thread_dirs(
                    scratch_root,
                    thread_id,
                    title=f"{scenario['title']} / {session_id} / Speaker {speaker}",
                )
                scratchpads[speaker] = (scratch_root, tdir, thread_id)

            session: dict = {
                "session_id": session_id,
                "condition": condition,
                "condition_position": condition_position,
                "replicate": replicate,
                "status": "running",
                "speaker_modes": speaker_modes,
                "starting_speaker": starting_speaker,
                "history_chars": history_chars,
                "turns_planned": turn_count,
                "turns_completed": 0,
                "turn_output_tokens": turn_output_tokens,
                "model_calls": 0,
                "tool_steps": 0,
                "memory_writes": 0,
                "memory_context_injections": 0,
                "retrieval_context_injections": 0,
                "retrieval_context_sources": 0,
                "retrieval_context_chars": 0,
                "protocol_recoveries": 0,
                "json_parse_errors": 0,
                "usage": empty_usage(),
                "trace_path": str(trace_path),
                "transcript_path": str(transcript_path),
                "transcript_markdown_path": str(transcript_md_path),
                "manifest_path": str(session_manifest_path),
                "messages": [],
            }
            records: list[dict] = []
            write_manifest(session_manifest_path, session)

            for turn in range(1, turn_count + 1):
                speaker = (
                    starting_speaker
                    if turn % 2 == 1
                    else ("B" if starting_speaker == "A" else "A")
                )
                mode = speaker_modes[speaker]
                if turn == 1:
                    incoming = f"Moderator opening:\n{scenario['opening']}"
                    prior_records: list[dict] = []
                else:
                    previous = next(item for item in reversed(records) if item.get("kind") == "utterance")
                    incoming = f"Speaker {previous['speaker']}:\n{previous['message']}"
                    prior_records = records[:-1]

                current_interventions = [
                    item for item in scenario["interventions"] if item["before_turn"] == turn
                ]
                for intervention in current_interventions:
                    incoming += f"\n\nModerator intervention:\n{intervention['message']}"

                events: list[dict] = []
                try:
                    if mode in PLAIN_DIALOGUE_MODES:
                        message, events, turn_summary = call_raw_dialogue_turn(
                            cfg=cfg,
                            scenario=scenario,
                            speaker=speaker,
                            incoming=incoming,
                            prior_records=prior_records,
                            turn=turn,
                            turns=turn_count,
                            output_token_budget=turn_output_tokens,
                            history_chars=history_chars,
                            mode=mode,
                        )
                    else:
                        scratch_root, tdir, thread_id = scratchpads[speaker]
                        mode_recent_n = recent_n if mode == "scratchpad" else 0
                        allowed_actions = (
                            {"scratchpad.add_note"}
                            if mode in {"write-no-recall", "probe-top1", "probe-top2"}
                            else None
                        )
                        selective_recall = scenario["selective_recall"]
                        retrieval_active = (
                            mode in {"probe-top1", "probe-top2"}
                            and turn in selective_recall["turns"]
                        )
                        retrieval_query = incoming
                        if selective_recall["query_source"] == "intervention":
                            retrieval_query = "\n\n".join(
                                item["message"] for item in current_interventions
                            )
                        events = []
                        message = run_chat_turn(
                            root=scratch_root,
                            tdir=tdir,
                            thread_id=thread_id,
                            cfg=cfg,
                            user_text=incoming,
                            history=dialogue_history(prior_records, speaker),
                            max_steps=max_steps,
                            recent_n=mode_recent_n,
                            yes=True,
                            max_tool_chars=max_tool_chars,
                            verbose=not quiet,
                            trace_events=events,
                            json_repair_steps=json_repair_steps,
                            queue_writes=False,
                            policy=policy,
                            output_token_budget=turn_output_tokens,
                            max_model_calls=1 + max_steps + json_repair_steps,
                            per_call_output_token_limit=plan[
                                "scratchpad_output_tokens_per_call"
                            ],
                            system_addendum=scratchpad_dialogue_context(
                                scenario, speaker, turn, turn_count
                            ),
                            trace_io=True,
                            history_chars=history_chars,
                            allowed_actions=allowed_actions,
                            retrieval_query=retrieval_query if retrieval_active else "",
                            retrieval_top=(
                                (1 if mode == "probe-top1" else 2)
                                if retrieval_active
                                else 0
                            ),
                            retrieval_max_chars=selective_recall[
                                "max_chars_per_doc"
                            ],
                        )
                        turn_summary = summarize_scratchpad_turn(events, message)
                except SystemExit as exc:
                    events.append(
                        {
                            "time": now_iso(),
                            "event": "dialogue_error",
                            "error": str(exc),
                        }
                    )
                    tag_dialogue_events(
                        events, run_id, session_id, condition, turn, speaker, mode
                    )
                    append_trace_events(trace_path, events)
                    session["status"] = "failed"
                    session["error"] = str(exc)
                    abort = True
                    break

                tag_dialogue_events(events, run_id, session_id, condition, turn, speaker, mode)
                append_trace_events(trace_path, events)
                for intervention in current_interventions:
                    moderator_record = {
                        "kind": "moderator",
                        "before_turn": turn,
                        "message": intervention["message"],
                    }
                    records.append(moderator_record)
                    append_jsonl(transcript_path, moderator_record)
                record = {
                    "kind": "utterance",
                    "turn": turn,
                    "speaker": speaker,
                    "mode": mode,
                    "message": message,
                    **turn_summary,
                }
                records.append(record)
                append_jsonl(transcript_path, record)
                session["turns_completed"] = turn
                session["model_calls"] += int(turn_summary["model_calls"])
                session["tool_steps"] += int(turn_summary["tool_steps"])
                session["memory_writes"] += int(turn_summary["memory_writes"])
                session["memory_context_injections"] += int(
                    turn_summary.get("memory_context_injections", 0)
                )
                session["retrieval_context_injections"] += int(
                    turn_summary.get("retrieval_context_injections", 0)
                )
                session["retrieval_context_sources"] += int(
                    turn_summary.get("retrieval_context_sources", 0)
                )
                session["retrieval_context_chars"] += int(
                    turn_summary.get("retrieval_context_chars", 0)
                )
                session["protocol_recoveries"] += int(
                    turn_summary.get("protocol_recoveries", 0)
                )
                session["json_parse_errors"] += int(
                    turn_summary.get("json_parse_errors", 0)
                )
                add_usage(session["usage"], turn_summary["usage"])
                session["messages"].append(
                    {
                        "turn": turn,
                        "speaker": speaker,
                        "mode": mode,
                        "status": turn_summary["status"],
                    }
                )
                transcript_md_path.write_text(
                    transcript_markdown(scenario, session, records), encoding="utf-8"
                )
                if turn_summary["status"] != "ok":
                    session["status"] = turn_summary["status"]
                    abort = True
                    write_manifest(session_manifest_path, session)
                    break
                write_manifest(session_manifest_path, session)

            if session["status"] == "running":
                session["status"] = "ok"
            session["anchor_coverage"] = anchor_coverage(records, scenario["anchors"])
            session["literal_probe_evidence"] = literal_probe_evidence(
                records, scenario["literal_probes"]
            )
            session["relation_probe_evidence"] = relation_probe_evidence(
                records, scenario["relation_probes"]
            )
            session["updated_at"] = now_iso()
            transcript_md_path.write_text(
                transcript_markdown(scenario, session, records), encoding="utf-8"
            )
            write_manifest(session_manifest_path, session)
            result["sessions"].append(session)
            result["updated_at"] = now_iso()
            result["status"] = "failed" if abort else "running"
            write_manifest(suite_manifest_path, result)
            if abort:
                break
        if abort:
            break

    result["status"] = "failed" if abort else "ok"
    result["updated_at"] = now_iso()
    report_path = out_dir / "report.md"
    result["report_path"] = str(report_path)
    report_path.write_text(dialogue_report_markdown(result), encoding="utf-8")
    write_manifest(suite_manifest_path, result)
    return result
