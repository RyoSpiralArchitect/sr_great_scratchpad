from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .chat import llm_trace
from .dialogue import (
    add_usage,
    append_jsonl,
    canonical_json_sha256,
    empty_usage,
    literal_probe_evidence,
    load_dialogue_memory_fixture,
    load_dialogue_scenario,
    relation_probe_evidence,
)
from .experiments import write_manifest
from .llm import api_key_from_config, call_llm_result, config_with_output_token_limit, llm_config_metadata
from .memory import recent_turn_files, render_recent_turns, render_retrieved_turns, retrieve
from .relations import RELATION_RENDERINGS, load_note_relations, text_sha256
from .retrieval_benchmark import intervention_query
from .storage import load_llm_config, now_iso

VISIBILITIES = ("none", "top1", "top2", "full-at-probe")
MEMORY_START = "\n\nScratchpad context supplied for this turn:\n---\n"
MEMORY_END = "\n---\n\nConversation so far in this runtime:\n---\n"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_prompt_parts(prompt: str) -> tuple[str, str]:
    if prompt.count(MEMORY_START) != 1 or prompt.count(MEMORY_END) != 1:
        raise SystemExit("Replay requires one unambiguous scratchpad context section.")
    prefix, rest = prompt.split(MEMORY_START)
    memory, suffix = rest.split(MEMORY_END)
    if not prefix.startswith("Thread: ") or "\n" in prefix:
        raise SystemExit("Replay source has an unexpected thread header.")
    if memory != "(no recent turns)":
        raise SystemExit("Replay source must be a no-recall prompt.")
    return "Thread: frozen-probe" + MEMORY_START, MEMORY_END + suffix


def prepare_relation_replay(
    run_dir: Path,
    session_id: str,
    probe_turn: int,
    fixture_path: Path,
    relations_path: Path,
) -> dict:
    run_dir = run_dir.expanduser().resolve()
    if Path(session_id).name != session_id or session_id in {".", ".."}:
        raise SystemExit("Replay requires a local session name.")
    suite = json.loads((run_dir / "suite_manifest.json").read_text(encoding="utf-8"))
    session = next((s for s in suite["sessions"] if s["session_id"] == session_id), None)
    if suite.get("status") != "ok" or not session or session.get("status") != "ok":
        raise SystemExit("Replay requires a completed successful source session.")
    scenario = load_dialogue_scenario(run_dir / "scenario.snapshot.json")
    public_scenario = {key: value for key, value in scenario.items() if not key.startswith("_")}
    scenario_hash = canonical_json_sha256(public_scenario)
    fixture = load_dialogue_memory_fixture(fixture_path)
    if (
        scenario_hash != suite.get("scenario_sha256")
        or canonical_json_sha256(suite["scenario"]) != scenario_hash
        or fixture["source"]["scenario_sha256"] != scenario_hash
        or fixture["_sha256"] != suite.get("memory_fixture_sha256")
    ):
        raise SystemExit("Replay scenario or fixture differs from the frozen source run.")
    relations = load_note_relations(relations_path, fixture, scenario)
    probes = {
        name: [p for p in scenario[name] if p["turn"] == probe_turn]
        for name in ("literal_probes", "relation_probes")
    }
    if not all(probes.values()):
        raise SystemExit("Replay turn requires frozen literal and relation probes.")
    trace_path = run_dir / session_id / "trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    requests = [e for e in events if e.get("event") == "model_request" and e.get("dialogue_turn") == probe_turn]
    if len(requests) != 1 or requests[0].get("mode") != "replay-no-recall":
        raise SystemExit("Replay requires exactly one request at a frozen no-recall probe.")
    request = requests[0]
    prefix, suffix = frozen_prompt_parts(request["prompt"])
    speaker = request["speaker"]
    thread_id = request["prompt"].split("\n", 1)[0].removeprefix("Thread: ")
    if speaker not in {"A", "B"} or Path(thread_id).name != thread_id or thread_id in {".", ".."}:
        raise SystemExit("Invalid source speaker or thread id.")
    # Resolve from the supplied run directory, not stale absolute paths in old manifests.
    tdir = run_dir / session_id / "scratchpads" / f"speaker-{speaker.lower()}" / "threads" / thread_id
    expected = {
        f"turns/{entry['source_note_number']:06d}-note.md": entry["source_note_sha256"]
        for entry in fixture["entries"]
        if entry["source_speaker"] == speaker and entry["after_turn"] < probe_turn
    }
    notes = {
        str(path.relative_to(tdir)): path.read_text(encoding="utf-8")
        for path in sorted(tdir.rglob("*.md"))
    }
    if not expected or {path: text_sha256(text) for path, text in notes.items()} != expected:
        raise SystemExit("Source memory differs from the exact pre-probe fixture notes.")
    if not set(relations["_by_hash"]).issubset(expected.values()):
        raise SystemExit("Annotated memory is not available to this speaker before the probe.")
    query = intervention_query(suite, probe_turn)
    if not query or query not in suffix:
        raise SystemExit("Frozen intervention query is absent from the provider prompt.")
    ranked = [
        {"path": str(path.relative_to(tdir)), "score": round(score, 3), "sha256": text_sha256(text)}
        for score, path, text in retrieve(tdir, query, len(notes))
    ]
    cells: list[dict] = []
    for index, visibility in enumerate(VISIBILITIES):
        # Rotate representation order; all calls share exactly the same frozen history.
        order = RELATION_RENDERINGS[index % 3:] + RELATION_RENDERINGS[:index % 3]
        for rendering in order:
            kwargs = {"relations": relations["_by_hash"], "rendering": rendering}
            if visibility == "none":
                context, selected = "(no recent turns)", []
            elif visibility == "full-at-probe":
                context = render_recent_turns(tdir, n=len(notes), max_chars=1600, **kwargs)
                selected = [str(path.relative_to(tdir)) for path in recent_turn_files(tdir, len(notes))]
            else:
                context, sources = render_retrieved_turns(tdir, query, top=int(visibility[-1]), **kwargs)
                selected = [source["path"] for source in sources]
            prompt = prefix + context + suffix
            cells.append({
                "id": f"{visibility}-{rendering}", "visibility": visibility, "rendering": rendering,
                "selected_notes": [{"path": path, "sha256": expected[path]} for path in selected],
                "annotated_note_visible": any(expected[path] in relations["_by_hash"] for path in selected),
                "context_chars": len(context), "context_sha256": text_sha256(context),
                "prompt": prompt, "prompt_sha256": text_sha256(prompt),
            })
    for visibility in VISIBILITIES:
        group = [cell for cell in cells if cell["visibility"] == visibility]
        if len({canonical_json_sha256(cell["selected_notes"]) for cell in group}) != 1:
            raise SystemExit("Representation unexpectedly changed selected notes.")
        if not group[0]["annotated_note_visible"] and len({cell["prompt_sha256"] for cell in group}) != 1:
            raise SystemExit("Relation content leaked into a no-target condition.")
    return {
        "method": "fixed-probe-relation-replay-v1",
        "source": {"run_id": suite["run_id"], "session_id": session_id, "probe_turn": probe_turn,
                   "speaker": speaker, "trace_sha256": file_sha256(trace_path),
                   "request": request, "notes": notes},
        "scenario": public_scenario, "scenario_sha256": scenario_hash,
        "fixture": {key: value for key, value in fixture.items() if not key.startswith("_")},
        "fixture_sha256": fixture["_sha256"],
        "relations": {key: value for key, value in relations.items() if not key.startswith("_")},
        "relations_sha256": relations["_sha256"],
        "assessment": probes, "assessment_sha256": canonical_json_sha256(probes),
        "ranked_notes": ranked, "query": query,
        "system_prompt": request["system_prompt"],
        "system_prompt_sha256": text_sha256(request["system_prompt"]),
        "outside_memory_sha256": text_sha256(prefix + suffix), "cells": cells,
    }


def replay_report(result: dict) -> str:
    lines = [
        "# Fixed-probe relation replay", "", f"- Status: {result['status']}",
        f"- Model: {result['llm']['model']}", f"- Plan SHA-256: {result['plan_sha256']}",
        f"- Attempted calls: {result['attempted_calls']}", "",
        "| Condition | Status | Literal | Strict relation | Context chars |",
        "|---|---|---:|---:|---:|",
    ]
    for cell in result["cells"]:
        literal = cell.get("literal", {})
        relation = cell.get("relation", {})
        lines.append(f"| {cell['id']} | {cell['status']} | {literal.get('passed', 0)}/{literal.get('total', 0)} | "
                     f"{relation.get('passed', 0)}/{relation.get('total', 0)} | {cell['context_chars']} |")
    lines.extend(["", "Each cell is one response to the same frozen probe, not a new full dialogue.",
                  "The strict marker-based endpoint is unchanged; it does not establish historical adoption.",
                  "Prose and roles add the same sourced propositions, but differ in length and layout.", ""])
    for cell in result["cells"]:
        if cell.get("message"):
            lines.extend([f"## {cell['id']}", "", cell["message"], ""])
    return "\n".join(lines)


def run_relation_replay(
    root: Path, run_dir: Path, session_id: str, probe_turn: int,
    fixture_path: Path, relations_path: Path, profile: str, llm_config: str | None,
    out_dir: Path, max_api_calls: int = 12, max_suite_output_tokens: int = 4800,
    call_output_tokens: int = 400, dry_run: bool = False,
) -> dict:
    call_count = len(VISIBILITIES) * len(RELATION_RENDERINGS)
    if call_output_tokens < 1 or call_count > max_api_calls or call_count * call_output_tokens > max_suite_output_tokens:
        raise SystemExit("Relation replay preflight exceeds the call or output-token budget.")
    plan = prepare_relation_replay(run_dir, session_id, probe_turn, fixture_path, relations_path)
    cfg = config_with_output_token_limit(load_llm_config(root, llm_config, profile), call_output_tokens)
    secret = api_key_from_config(cfg) if not dry_run else ""
    out_dir = out_dir.expanduser().resolve()
    if out_dir.exists():
        raise SystemExit("Relation replay requires a fresh output directory.")
    out_dir.mkdir(parents=True)
    write_manifest(out_dir / "plan.json", plan)
    result = {
        "method": plan["method"], "status": "prepared" if dry_run else "running",
        "started_at": now_iso(), "llm": llm_config_metadata(cfg),
        "sampling": {key: cfg[key] for key in ("temperature", "top_p", "seed", "reasoning_effort", "json_mode") if key in cfg},
        "plan_sha256": file_sha256(out_dir / "plan.json"),
        "runtime_sha256": {name: file_sha256(Path(__file__).with_name(name + ".py"))
                           for name in ("relation_replay", "relations", "memory", "dialogue", "llm", "text")},
        "budget": {"max_calls": call_count, "per_call_output_tokens": call_output_tokens,
                   "max_output_tokens": call_count * call_output_tokens, "retries": 0},
        "attempted_calls": 0, "usage": empty_usage(),
        "report_path": str(out_dir / "report.md"),
        "cells": [{**{key: value for key, value in cell.items() if key != "prompt"}, "status": "not-run"}
                  for cell in plan["cells"]],
    }

    def save() -> None:
        result["updated_at"] = now_iso()
        write_manifest(out_dir / "result.json", result)
        (out_dir / "report.md").write_text(replay_report(result), encoding="utf-8")

    save()
    if dry_run:
        return result
    for planned, cell in zip(plan["cells"], result["cells"]):
        cell["status"] = "running"
        result["attempted_calls"] += 1
        save()
        try:
            response = call_llm_result(cfg, planned["prompt"], plan["system_prompt"])
            cell["llm"] = llm_trace(response)
            cell["raw_output"] = response.get("content", "")
            add_usage(result["usage"], response.get("usage"))
            # Persist the unmodified output before parsing; no repair or tool calls are allowed.
            append_jsonl(out_dir / "responses.jsonl", {"cell_id": cell["id"], **response})
            payload = json.loads(cell["raw_output"])
            if not isinstance(payload, dict) or payload.get("type") != "final" or not isinstance(payload.get("message"), str) or not payload["message"].strip():
                raise ValueError("Expected a non-empty final message, with no tool action.")
            cell["message"] = payload["message"]
            records = [{"kind": "utterance", "turn": probe_turn, "speaker": plan["source"]["speaker"], "message": cell["message"]}]
            cell["literal"] = literal_probe_evidence(records, plan["assessment"]["literal_probes"])
            cell["relation"] = relation_probe_evidence(records, plan["assessment"]["relation_probes"])
            cell["reply_chars"] = len(cell["message"])
            cell["within_reply_char_limit"] = cell["reply_chars"] <= plan["scenario"]["max_reply_chars"]
            cell["status"] = "ok"
        except (Exception, SystemExit, KeyboardInterrupt) as exc:
            cell["status"] = "error"
            message = str(exc)
            cell["error"] = message.replace(secret, "[REDACTED]") if secret else message
            result["status"] = "error"
            save()
            break
        save()
    else:
        result["status"] = "ok"
        save()
    return result
