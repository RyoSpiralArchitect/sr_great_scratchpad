from __future__ import annotations

import json
import uuid
from pathlib import Path

from .storage import now_iso

def make_run_id(prefix: str = "run") -> str:
    stamp = now_iso().replace(":", "").replace("+", "-")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"

def add_run_id(events: list[dict], run_id: str) -> list[dict]:
    if not run_id:
        return events
    for event in events:
        event.setdefault("run_id", run_id)
    return events

def trace_summary(events: list[dict]) -> dict:
    event_counts: dict[str, int] = {}
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated": False,
    }
    for event in events:
        name = str(event.get("event", ""))
        event_counts[name] = event_counts.get(name, 0) + 1
        llm = event.get("llm")
        if not isinstance(llm, dict):
            continue
        item = llm.get("usage")
        if not isinstance(item, dict):
            continue
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                usage[key] += int(item.get(key, 0))
            except (TypeError, ValueError):
                pass
        usage["estimated"] = bool(usage["estimated"] or item.get("estimated", False))
    return {
        "event_counts": event_counts,
        "usage": usage,
    }

def default_manifest_path(trace_path: Path | None) -> Path | None:
    if trace_path is None:
        return None
    if trace_path.suffix:
        return trace_path.with_suffix(".manifest.json")
    return trace_path.with_name(trace_path.name + ".manifest.json")

def write_manifest(path: Path | None, manifest: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

