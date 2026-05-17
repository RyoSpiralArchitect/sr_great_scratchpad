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

def parse_scenario_file(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Scenario file not found: {path}")
    text = path.read_text(encoding="utf-8")
    turns: list[dict[str, str]] = []
    current_title: str | None = None
    buf: list[str] = []
    saw_turn_heading = False

    def flush() -> None:
        nonlocal buf, current_title
        body = "\n".join(buf).strip()
        if body:
            turns.append(
                {
                    "title": current_title or f"Turn {len(turns) + 1}",
                    "text": body,
                }
            )
        buf = []

    for line in text.splitlines():
        if line.startswith("## "):
            if saw_turn_heading:
                flush()
            else:
                buf = []
            saw_turn_heading = True
            current_title = line[3:].strip() or f"Turn {len(turns) + 1}"
            continue
        if saw_turn_heading:
            buf.append(line)
        elif not line.startswith("# "):
            buf.append(line)

    if saw_turn_heading:
        flush()
    else:
        body = "\n".join(buf).strip() or text.strip()
        if body:
            turns.append({"title": path.stem, "text": body})

    if not turns:
        raise SystemExit(f"Scenario has no runnable turns: {path}")
    return turns

def experiment_report_markdown(result: dict) -> str:
    lines = [
        "# Great Scratchpad Experiment Report",
        "",
        f"- Scenario: {result['scenario_path']}",
        f"- Started: {result['started_at']}",
        f"- Policy: {result['policy']}",
        f"- Queue writes: {result['queue_writes']}",
        f"- Turns: {result['turn_count']}",
        "",
        "## Profiles",
        "",
    ]
    for profile in result["profiles"]:
        summary = profile.get("summary", {})
        counts = summary.get("event_counts", {})
        usage = summary.get("usage", {})
        lines.extend(
            [
                f"### {profile['profile']}",
                "",
                f"- Status: {profile['status']}",
                f"- Thread: {profile['thread_id']}",
                f"- Run id: {profile['run_id']}",
                f"- Trace: {profile['trace_path']}",
                f"- Manifest: {profile['manifest_path']}",
                f"- Report: {profile['report_path']}",
                f"- Final events: {counts.get('final', 0)}",
                f"- Tool observations: {counts.get('tool_observation', 0)}",
                f"- JSON repairs: {counts.get('json_parse_error', 0)}",
                f"- Queued writes: {profile['queued_writes']}",
                f"- Total tokens: {usage.get('total_tokens', 0)}",
                "",
            ]
        )
        if profile.get("message"):
            lines.extend(["#### Last message", "", profile["message"], ""])
    return "\n".join(lines).strip() + "\n"

def run_scenario_profiles(
    root: Path,
    scenario_path: Path,
    profiles: list[str],
    llm_config: str | None,
    out_dir: Path,
    thread_prefix: str,
    policy: str,
    queue_writes: bool,
    yes: bool,
    max_steps: int,
    recent_n: int,
    max_tool_chars: int,
    json_repair_steps: int,
    quiet: bool,
) -> dict:
    from .chat import append_trace_events, run_chat_turn
    from .llm import llm_config_metadata
    from .storage import ensure_root, ensure_thread_dirs, load_llm_config, safe_id
    from .trace import trace_report_markdown

    ensure_root(root)
    scenario_path = scenario_path.resolve()
    turns = parse_scenario_file(scenario_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    result: dict = {
        "scenario_path": str(scenario_path),
        "started_at": started_at,
        "policy": policy,
        "queue_writes": queue_writes,
        "turn_count": len(turns),
        "profiles": [],
    }

    for profile_name in profiles:
        cfg = load_llm_config(root, llm_config, profile_name)
        profile_label = str(cfg.get("profile", profile_name) or profile_name or "default")
        profile_id = safe_id(profile_label)
        run_id = make_run_id(f"experiment-{profile_id}")
        profile_dir = out_dir / profile_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        trace_path = profile_dir / "trace.jsonl"
        manifest_path = profile_dir / "manifest.json"
        report_path = profile_dir / "report.md"
        if trace_path.exists():
            trace_path.write_text("", encoding="utf-8")
        thread_id = safe_id(f"{thread_prefix}-{scenario_path.stem}-{profile_label}")
        tdir = ensure_thread_dirs(root, thread_id, title=f"{scenario_path.stem} / {profile_label}")
        history: list[dict[str, str]] = []
        all_events: list[dict] = []
        status = "ok"
        message = ""

        for turn in turns:
            trace_events: list[dict] = []
            try:
                message = run_chat_turn(
                    root=root,
                    tdir=tdir,
                    thread_id=thread_id,
                    cfg=cfg,
                    user_text=turn["text"],
                    history=history,
                    max_steps=max_steps,
                    recent_n=recent_n,
                    yes=yes,
                    max_tool_chars=max_tool_chars,
                    verbose=not quiet,
                    trace_events=trace_events,
                    json_repair_steps=json_repair_steps,
                    queue_writes=queue_writes,
                    policy=policy,
                )
            except SystemExit as exc:
                status = "failed"
                message = str(exc)
                add_run_id(trace_events, run_id)
                all_events.extend(trace_events)
                append_trace_events(trace_path, trace_events)
                break
            add_run_id(trace_events, run_id)
            all_events.extend(trace_events)
            append_trace_events(trace_path, trace_events)
            history.extend(
                [
                    {"role": "user", "content": turn["text"]},
                    {"role": "assistant", "content": message},
                ]
            )

        queued_writes = sum(
            1 for event in all_events
            if event.get("event") == "tool_observation"
            and "queued for review" in str(event.get("observation", ""))
        )
        summary = trace_summary(all_events)
        profile_report = trace_report_markdown(
            all_events,
            title=f"Experiment Trace Report: {profile_label}",
        )
        report_path.write_text(profile_report, encoding="utf-8")
        manifest = {
            "run_id": run_id,
            "command": "experiment run",
            "status": status,
            "message": message,
            "started_at": started_at,
            "updated_at": now_iso(),
            "root": str(root),
            "scenario_path": str(scenario_path),
            "thread_id": thread_id,
            "trace_path": str(trace_path),
            "policy": policy,
            "queue_writes": queue_writes,
            "turns": len(turns),
            "llm": llm_config_metadata(cfg),
            "summary": summary,
        }
        write_manifest(manifest_path, manifest)
        result["profiles"].append(
            {
                "profile": profile_label,
                "status": status,
                "message": message,
                "thread_id": thread_id,
                "run_id": run_id,
                "trace_path": str(trace_path),
                "manifest_path": str(manifest_path),
                "report_path": str(report_path),
                "queued_writes": queued_writes,
                "summary": summary,
            }
        )

    result["updated_at"] = now_iso()
    report_path = out_dir / "experiment_report.md"
    result["report_path"] = str(report_path)
    report_path.write_text(experiment_report_markdown(result), encoding="utf-8")
    return result
