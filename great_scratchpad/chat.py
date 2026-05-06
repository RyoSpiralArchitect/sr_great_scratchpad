from __future__ import annotations

import json
import sys
from pathlib import Path

from .constants import CHAT_PROMPT_TEMPLATE, CHAT_RUNTIME_SYSTEM
from .llm import call_llm, extract_json_object
from .memory import add_turn, build_context_pack, render_audit, render_recent_turns, render_search_results
from .storage import now_iso
from .text import limit_text

def parse_chat_json(text: str) -> dict:
    try:
        return extract_json_object(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not parse chat runtime JSON: {exc}\nOutput:\n{text}") from exc

def chat_history_text(history: list[dict[str, str]], max_chars: int = 4000) -> str:
    lines: list[str] = []
    for msg in history:
        lines.append(f"{msg['role']}: {msg['content']}")
    text = "\n\n".join(lines).strip()
    return limit_text(text, max_chars) if text else "(empty)"

def build_chat_prompt(
    thread_id: str,
    user_text: str,
    recent_context: str,
    history: list[dict[str, str]],
    observations: list[str],
    history_chars: int = 4000,
) -> str:
    return CHAT_PROMPT_TEMPLATE.format(
        thread_id=thread_id,
        recent_context=recent_context,
        history=chat_history_text(history, history_chars),
        user_text=user_text.strip(),
        observations="\n\n".join(observations).strip() or "(none yet)",
    )

def maybe_confirm_write(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        return False
    answer = input(f"{prompt} [y/N]> ").strip().lower()
    return answer in {"y", "yes"}

def action_int(
    action_obj: dict,
    field: str,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = action_obj.get(field, default)
    if isinstance(raw, bool):
        raise ValueError(f"{field} must be an integer, got {raw!r}")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer, got {raw!r}") from exc

    if min_value is not None and value < min_value:
        raise ValueError(f"{field} must be >= {min_value}, got {value}")
    if max_value is not None and value > max_value:
        return max_value
    return value

def action_bool(action_obj: dict, field: str, default: bool = False) -> bool:
    raw = action_obj.get(field, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError(f"{field} must be a boolean, got {raw!r}")

def record_trace(trace_events: list[dict] | None, event: str, **fields: object) -> None:
    if trace_events is None:
        return
    trace_events.append({"time": now_iso(), "event": event, **fields})

def append_trace_events(path: Path, events: list[dict]) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

def run_scratchpad_action(
    root: Path,
    tdir: Path,
    thread_id: str,
    action_obj: dict,
    yes: bool = False,
    max_tool_chars: int = 6000,
) -> str:
    action = str(action_obj.get("action", "")).strip()

    try:
        if action == "scratchpad.search":
            query = str(action_obj.get("query", "")).strip()
            if not query:
                return "scratchpad.search failed: missing query"
            top = action_int(action_obj, "top", 5, min_value=1, max_value=50)
            width = action_int(action_obj, "width", 420, min_value=80, max_value=4000)
            return limit_text(render_search_results(tdir, query, top=top, width=width), max_tool_chars)

        if action == "scratchpad.recent":
            n = action_int(action_obj, "n", 5, min_value=0, max_value=50)
            max_chars = action_int(action_obj, "max_chars", 1600, min_value=1, max_value=20000)
            return limit_text(render_recent_turns(tdir, n=n, max_chars=max_chars), max_tool_chars)

        if action == "scratchpad.pack":
            query = str(action_obj.get("query", "")).strip()
            if not query:
                return "scratchpad.pack failed: missing query"
            output = build_context_pack(
                root=root,
                tdir=tdir,
                query=query,
                recent_n=action_int(action_obj, "recent", 6, min_value=0, max_value=50),
                top=action_int(action_obj, "top", 6, min_value=0, max_value=50),
                max_chars_per_doc=action_int(
                    action_obj,
                    "max_chars_per_doc",
                    2200,
                    min_value=1,
                    max_value=20000,
                ),
                include_guide=action_bool(action_obj, "include_guide", False),
            )
            return limit_text(output, max_tool_chars)

        if action == "scratchpad.audit":
            return limit_text(
                render_audit(
                    tdir,
                    as_json=action_bool(action_obj, "json", True),
                    max_flags=action_int(action_obj, "max_flags", 8, min_value=0, max_value=100),
                ),
                max_tool_chars,
            )

        if action == "scratchpad.add_note":
            raw = str(action_obj.get("text", "")).strip()
            if not raw:
                return "scratchpad.add_note failed: missing text"
            if not maybe_confirm_write("Allow scratchpad.add_note write?", yes):
                return "scratchpad.add_note skipped: write was not confirmed"
            turn_no, path = add_turn(
                root=root,
                thread_id=thread_id,
                speaker="note",
                raw=raw,
                center=str(action_obj.get("center", "")),
                trajectory=str(action_obj.get("trajectory", "")),
                anchors=str(action_obj.get("anchors", "")),
                assumptions=str(action_obj.get("assumptions", "")),
                open_questions=str(action_obj.get("open_questions", "")),
                drift_risks=str(action_obj.get("drift_risks", "")),
            )
            return f"scratchpad.add_note wrote turn {turn_no:06d}: {path.relative_to(tdir)}"
    except ValueError as exc:
        return f"{action or 'scratchpad action'} failed: {exc}"

    return f"Unknown scratchpad action: {action!r}"

def run_chat_turn(
    root: Path,
    tdir: Path,
    thread_id: str,
    cfg: dict,
    user_text: str,
    history: list[dict[str, str]],
    max_steps: int = 4,
    recent_n: int = 4,
    yes: bool = False,
    max_tool_chars: int = 6000,
    verbose: bool = True,
    trace_events: list[dict] | None = None,
) -> str:
    observations: list[str] = []
    recent_context = render_recent_turns(tdir, n=recent_n, max_chars=1200)
    record_trace(
        trace_events,
        "turn_start",
        thread_id=thread_id,
        user_text=user_text,
        recent_n=recent_n,
        max_steps=max_steps,
    )

    for step in range(max_steps + 1):
        prompt = build_chat_prompt(
            thread_id=thread_id,
            user_text=user_text,
            recent_context=recent_context,
            history=history,
            observations=observations,
        )
        raw_output = call_llm(cfg, prompt, CHAT_RUNTIME_SYSTEM)
        obj = parse_chat_json(raw_output)
        kind = str(obj.get("type", "")).strip().lower()
        record_trace(trace_events, "model_output", step=step, kind=kind, payload=obj)

        if kind == "final" or "message" in obj:
            message = str(obj.get("message", "")).strip()
            if not message:
                message = "(empty final message)"
            record_trace(trace_events, "final", step=step, message=message)
            return message

        if kind != "action" and "action" not in obj:
            message = f"(chat runtime stopped: expected action/final JSON, got {obj})"
            record_trace(trace_events, "stopped", step=step, reason="unexpected_payload", message=message)
            return message

        if step >= max_steps:
            message = "(chat runtime stopped: max tool steps reached before final answer)"
            record_trace(trace_events, "stopped", step=step, reason="max_steps", message=message)
            return message

        action_name = str(obj.get("action", "")).strip()
        if verbose:
            print(f"[tool] {action_name}")
        observation = run_scratchpad_action(
            root=root,
            tdir=tdir,
            thread_id=thread_id,
            action_obj=obj,
            yes=yes,
            max_tool_chars=max_tool_chars,
        )
        record_trace(
            trace_events,
            "tool_observation",
            step=step,
            action=action_name,
            observation=observation,
        )
        observations.append(
            f"Action {len(observations) + 1}: {action_name}\nObservation:\n{observation}"
        )
        if verbose:
            print(limit_text(observation, 800))

    message = "(chat runtime stopped unexpectedly)"
    record_trace(trace_events, "stopped", reason="unexpected_loop_exit", message=message)
    return message
