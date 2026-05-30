from __future__ import annotations

import json
from pathlib import Path

from .experiments import trace_summary
from .text import limit_text

def load_trace_events(path: Path) -> list[dict]:
    events: list[dict] = []
    if not path.exists():
        raise SystemExit(f"Trace file not found: {path}")
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSONL at {path}:{lineno}: {exc}") from exc
        if isinstance(item, dict):
            item.setdefault("_line", lineno)
            events.append(item)
    return events

def trace_actions(events: list[dict]) -> list[dict]:
    actions: list[dict] = []
    for event in events:
        if event.get("event") == "model_output":
            payload = event.get("payload")
            if isinstance(payload, dict) and payload.get("action"):
                actions.append(
                    {
                        "line": event.get("_line"),
                        "tool_step": event.get("tool_step"),
                        "action": payload.get("action"),
                        "query": payload.get("query", ""),
                        "payload": payload,
                    }
                )
    return actions

def trace_finals(events: list[dict]) -> list[str]:
    return [
        str(event.get("message", ""))
        for event in events
        if event.get("event") == "final"
    ]

def trace_repairs(events: list[dict]) -> int:
    return sum(1 for event in events if event.get("event") == "json_parse_error")

def trace_report_data(events: list[dict]) -> dict:
    summary = trace_summary(events)
    actions = trace_actions(events)
    finals = trace_finals(events)
    run_ids = sorted({str(event.get("run_id", "")) for event in events if event.get("run_id")})
    profiles = sorted(
        {
            str(event.get("llm", {}).get("profile", ""))
            for event in events
            if isinstance(event.get("llm"), dict) and event.get("llm", {}).get("profile")
        }
    )
    models = sorted(
        {
            str(event.get("llm", {}).get("model", "") or event.get("llm", {}).get("model_path", ""))
            for event in events
            if isinstance(event.get("llm"), dict)
            and (event.get("llm", {}).get("model") or event.get("llm", {}).get("model_path"))
        }
    )
    queued = [
        event for event in events
        if event.get("event") == "tool_observation"
        and "queued for review" in str(event.get("observation", ""))
    ]
    writes = [
        event for event in events
        if event.get("event") == "tool_observation"
        and "scratchpad.add_note" in str(event.get("action", ""))
    ]
    return {
        "run_ids": run_ids,
        "profiles": profiles,
        "models": models,
        "summary": summary,
        "actions": actions,
        "json_repairs": trace_repairs(events),
        "queued_writes": len(queued),
        "write_actions": len(writes),
        "final_messages": finals,
    }

def trace_report_markdown(events: list[dict], title: str = "Great Scratchpad Trace Report") -> str:
    data = trace_report_data(events)
    lines = [
        f"# {title}",
        "",
        "## Overview",
        "",
        f"- Run ids: {', '.join(data['run_ids']) or '(none)'}",
        f"- Profiles: {', '.join(data['profiles']) or '(none)'}",
        f"- Models: {', '.join(data['models']) or '(none)'}",
        f"- Events: {sum(data['summary']['event_counts'].values())}",
        f"- JSON repairs: {data['json_repairs']}",
        f"- Write actions: {data['write_actions']}",
        f"- Queued writes: {data['queued_writes']}",
        "",
        "## Event Counts",
        "",
    ]
    for name, count in sorted(data["summary"]["event_counts"].items()):
        lines.append(f"- {name}: {count}")

    usage = data["summary"].get("usage", {})
    lines.extend(
        [
            "",
            "## Usage",
            "",
            f"- Prompt tokens: {usage.get('prompt_tokens', 0)}",
            f"- Completion tokens: {usage.get('completion_tokens', 0)}",
            f"- Total tokens: {usage.get('total_tokens', 0)}",
            f"- Estimated: {usage.get('estimated', False)}",
            "",
            "## Tool Actions",
            "",
        ]
    )
    if data["actions"]:
        for i, action in enumerate(data["actions"], start=1):
            query = f" query={action['query']!r}" if action.get("query") else ""
            lines.append(f"{i}. {action.get('action')} step={action.get('tool_step')}{query}")
    else:
        lines.append("(none)")

    lines.extend(["", "## Final Messages", ""])
    if data["final_messages"]:
        for i, message in enumerate(data["final_messages"], start=1):
            lines.extend([f"### Final {i}", "", limit_text(message, 2000), ""])
    else:
        lines.append("(none)")

    return "\n".join(lines).strip() + "\n"

def trace_show(events: list[dict], step: int | None = None, line: int | None = None) -> str:
    if line is not None:
        matches = [event for event in events if event.get("_line") == line]
    elif step is not None:
        matches = [
            event for event in events
            if event.get("tool_step") == step
            or (
                isinstance(event.get("payload"), dict)
                and event.get("payload", {}).get("type") == "action"
                and event.get("tool_step") == step
            )
        ]
    else:
        matches = events
    if not matches:
        return "(no matching trace events)"
    return "\n".join(json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True) for event in matches)
