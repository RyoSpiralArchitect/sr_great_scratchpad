from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from .audit import audit_turn_md
from .chat import append_trace_events, run_chat_turn
from .constants import ACTION_POLICIES, ROOT_DEFAULT
from .experiments import add_run_id, default_manifest_path, make_run_id, run_scenario_profiles, trace_summary, write_manifest
from .llm import call_llm_result, draft_annotation, extract_json_object, llm_config_metadata, print_annotation
from .memory import add_turn, apply_review_item, apply_safe_review_items, audit_review_item, build_context_pack, compact_one_range, edit_review_item, iter_review_items, load_review_item, recent_turn_files, reject_review_item, render_audit, render_recent_turns, render_review_item, retrieve, review_item_is_safe
from .storage import ensure_root, ensure_thread, ensure_thread_dirs, llm_config_path, load_llm_config, load_meta, now_iso, read_llm_config_document, read_text_arg, root_path, safe_id, save_meta, thread_path, write_llm_config_document
from .text import limit_text, snippet
from .trace import load_trace_events, trace_report_data, trace_report_markdown, trace_show

REPL_HELP = """Great Scratchpad REPL commands:

  help                         Show this help.
  root                         Show active scratchpad root.
  list | threads               List threads.
  new THREAD [TITLE...]        Create or open a thread.
  use THREAD                   Set the active thread.
  thread                       Show the active thread.
  add [SPEAKER] [THREAD]       Add one turn. Raw articulation is multiline.
  note [THREAD]                Add a note turn.
  search QUERY [--top N]       Search the active thread.
  recent [N]                   Show recent turns from the active thread.
  pack QUERY [options]         Build a context pack from the active thread.
  audit [--json]               Audit the active thread.
  llm                          Show active LLM config.
  annotate [SPEAKER] [THREAD]  Draft annotations with the configured LLM.
  guide                        Print the annotation guide.
  compact [options]            Create trajectory blocks for the active thread.
  quit | exit                  Leave the REPL.

Multiline raw input ends with a single '.' line.
"""

def cmd_init(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    print(f"Initialized Great Scratchpad at: {root}")

def cmd_new(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)

    tdir = thread_path(root, args.thread)
    (tdir / "turns").mkdir(parents=True, exist_ok=True)
    (tdir / "blocks").mkdir(parents=True, exist_ok=True)

    meta_path = tdir / "meta.json"
    if not meta_path.exists():
        save_meta(
            tdir,
            {
                "thread_id": safe_id(args.thread),
                "title": args.title or args.thread,
                "created_at": now_iso(),
                "last_turn": 0,
                "principle": "Store articulation trajectory, not only conclusions.",
            },
        )

    print(f"Thread ready: {tdir}")

def cmd_list(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    threads_dir = root / "threads"

    threads = sorted(p for p in threads_dir.iterdir() if p.is_dir())
    if not threads:
        print("(no threads)")
        return

    for tdir in threads:
        meta = load_meta(tdir)
        print(f"{tdir.name}\tturns={meta.get('last_turn', 0)}\ttitle={meta.get('title', '')}")

def cmd_add(args: argparse.Namespace) -> None:
    root = root_path(args)
    raw = read_text_arg(args.text, args.text_file)
    turn_no, path = add_turn(
        root=root,
        thread_id=args.thread,
        speaker=args.speaker,
        raw=raw,
        center=args.center or "",
        trajectory=args.trajectory or "",
        anchors=args.anchors or "",
        assumptions=args.assumptions or "",
        open_questions=args.open_questions or "",
        drift_risks=args.drift_risks or "",
    )

    print(f"Added turn {turn_no:06d}: {path}")

def cmd_search(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread(root, args.thread)

    hits = retrieve(tdir, args.query, args.top)

    if not hits:
        print("(no hits)")
        return

    for i, (score, path, text) in enumerate(hits, start=1):
        rel = path.relative_to(tdir)
        print(f"\n## Hit {i}: score={score:.1f} path={rel}")
        print(snippet(text, args.query, width=args.width))

def cmd_recent(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread(root, args.thread)

    files = recent_turn_files(tdir, args.n)
    if not files:
        print("(no recent turns)")
        return

    for path in files:
        print(f"\n--- {path.relative_to(tdir)} ---")
        print(limit_text(path.read_text(encoding="utf-8"), args.max_chars))

def cmd_audit(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread(root, args.thread)

    files = sorted((tdir / "turns").glob("*.md"))
    if not files:
        print("(no turns to audit)")
        return

    results = [audit_turn_md(path) for path in files]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    for r in results:
        rel = Path(r["path"]).relative_to(tdir)
        print(
            f"{rel}\n"
            f"  raw_chars: {r['raw_chars']}\n"
            f"  annotation_chars: {r['annotation_chars']}\n"
            f"  ratio: {r['ratio']}\n"
            f"  status: {r['status']}"
        )
        flags = r["unsupported_anchors"]
        missing = r.get("missing_fields", [])
        if missing:
            print(f"  missing_fields: {', '.join(missing)}")
        if "anchor_count" in r:
            print(f"  anchor_count: {r['anchor_count']}")
        if flags:
            shown = flags[:args.max_flags]
            print(f"  unsupported_anchors: {', '.join(shown)}")
            if len(flags) > args.max_flags:
                print(f"  ...and {len(flags) - args.max_flags} more")
        print()

def cmd_guide(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    guide = root / "guide.md"
    print(guide.read_text(encoding="utf-8"))

def cmd_llm_config_show(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    path = llm_config_path(root, args.config)
    if not path.exists():
        print(f"(no llm config at {path})")
        return
    print(path.read_text(encoding="utf-8"))

def cmd_llm_config_provider(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    path = llm_config_path(root, args.config)
    data = read_llm_config_document(path)
    profile = args.profile
    cfg = {
        "backend": "openai-compatible",
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "model": args.model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "timeout": args.timeout,
    }
    if args.top_p is not None:
        cfg["top_p"] = args.top_p
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.stop:
        cfg["stop"] = args.stop
    if args.json_mode != "off":
        cfg["json_mode"] = args.json_mode
    data["profiles"][profile] = cfg
    if args.default or not data.get("default_profile"):
        data["default_profile"] = profile
    write_llm_config_document(path, data)
    print(f"Wrote provider LLM profile {profile!r}: {path}")

def cmd_llm_config_local(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    path = llm_config_path(root, args.config)
    data = read_llm_config_document(path)
    profile = args.profile
    data["profiles"][profile] = {
        "backend": "command",
        "command": args.command,
        "model_path": args.model_path,
        "timeout": args.timeout,
    }
    if args.default or not data.get("default_profile"):
        data["default_profile"] = profile
    write_llm_config_document(path, data)
    print(f"Wrote local command LLM profile {profile!r}: {path}")

def cmd_llm_config_hf(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    path = llm_config_path(root, args.config)
    data = read_llm_config_document(path)
    profile = args.profile
    cfg = {
        "backend": "huggingface",
        "model": args.model,
        "model_path": args.model_path,
        "device": args.device,
        "dtype": args.dtype,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_new_tokens": args.max_new_tokens,
        "capture_hidden": args.capture_hidden,
    }
    if args.seed is not None:
        cfg["seed"] = args.seed
    data["profiles"][profile] = cfg
    if args.default or not data.get("default_profile"):
        data["default_profile"] = profile
    write_llm_config_document(path, data)
    print(f"Wrote Hugging Face LLM profile {profile!r}: {path}")

def cmd_annotate(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    raw = read_text_arg(args.text, args.text_file)
    cfg = load_llm_config(root, args.llm_config, args.profile)
    annotation = draft_annotation(raw, cfg, json_repair_steps=args.json_repair_steps)

    if args.json:
        print(json.dumps(annotation, ensure_ascii=False, indent=2))
    else:
        print_annotation(annotation)

    if args.save_thread:
        turn_no, path = add_turn(
            root=root,
            thread_id=args.save_thread,
            speaker=args.speaker,
            raw=raw,
            center=annotation["center"],
            trajectory=annotation["trajectory"],
            anchors=annotation["anchors"],
            assumptions=annotation["assumptions"],
            open_questions=annotation["open_questions"],
            drift_risks=annotation["drift_risks"],
        )
        print(f"Saved turn {turn_no:06d}: {path}")

def cmd_compact(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread(root, args.thread)

    meta = load_meta(tdir)
    last = int(meta.get("last_turn", 0))
    if last <= 0:
        print("(no turns to compact)")
        return

    start = args.start or 1
    end = args.end or last

    if args.block_size < 1:
        raise SystemExit(f"Invalid block size: {args.block_size}. Use --block-size >= 1.")
    if args.raw_excerpt_chars < 0:
        raise SystemExit(
            f"Invalid raw excerpt length: {args.raw_excerpt_chars}. Use --raw-excerpt-chars >= 0."
        )
    if start < 1 or end > last or start > end:
        raise SystemExit(f"Invalid range: start={start}, end={end}, last_turn={last}")

    made: list[Path] = []
    cur = start

    while cur <= end:
        block_end = min(cur + args.block_size - 1, end)
        made.append(compact_one_range(tdir, cur, block_end, args.raw_excerpt_chars))
        cur = block_end + 1

    for path in made:
        print(f"Wrote block: {path.relative_to(tdir)}")

def cmd_pack(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    tdir = ensure_thread(root, args.thread)

    output = build_context_pack(
        root=root,
        tdir=tdir,
        query=args.query,
        recent_n=args.recent,
        top=args.top,
        max_chars_per_doc=args.max_chars_per_doc,
        include_guide=args.include_guide,
    )

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Wrote context pack: {args.out}")
    else:
        print(output)

def cmd_chat(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread_dirs(root, args.thread, title=args.thread)
    thread_id = safe_id(args.thread)
    cfg = load_llm_config(root, args.llm_config, args.profile)
    history: list[dict[str, str]] = []
    trace_path = Path(args.trace_out).expanduser() if args.trace_out else None
    manifest_path = Path(args.manifest_out).expanduser() if args.manifest_out else default_manifest_path(trace_path)
    run_id = args.run_id or make_run_id("chat")
    started_at = now_iso()
    all_trace_events: list[dict] = []
    turns = 0

    def write_chat_manifest(status: str, message: str = "") -> None:
        write_manifest(
            manifest_path,
            {
                "run_id": run_id,
                "command": "chat",
                "status": status,
                "message": message,
                "started_at": started_at,
                "updated_at": now_iso(),
                "root": str(root),
                "thread_id": thread_id,
                "trace_path": str(trace_path) if trace_path else "",
                "turns": turns,
                "policy": args.policy,
                "llm": llm_config_metadata(cfg),
                "summary": trace_summary(all_trace_events),
            },
        )

    def run_one(user_text: str) -> None:
        nonlocal turns
        trace_events: list[dict] = []
        try:
            message = run_chat_turn(
                root=root,
                tdir=tdir,
                thread_id=thread_id,
                cfg=cfg,
                user_text=user_text,
                history=history,
                max_steps=args.max_steps,
                recent_n=args.recent,
                yes=args.yes,
                max_tool_chars=args.max_tool_chars,
                verbose=not args.quiet,
                trace_events=trace_events if (trace_path or manifest_path) else None,
                json_repair_steps=args.json_repair_steps,
                queue_writes=args.queue_writes,
                policy=args.policy,
            )
        except SystemExit as exc:
            turns += 1
            add_run_id(trace_events, run_id)
            all_trace_events.extend(trace_events)
            if trace_path:
                append_trace_events(trace_path, trace_events)
            write_chat_manifest("failed", str(exc))
            raise
        print(message)
        turns += 1
        add_run_id(trace_events, run_id)
        all_trace_events.extend(trace_events)
        if trace_path:
            append_trace_events(trace_path, trace_events)
            if not args.quiet:
                print(f"[trace] {trace_path}")
        write_chat_manifest("ok", message)
        history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": message},
            ]
        )

    if args.text or args.text_file:
        run_one(read_text_arg(args.text, args.text_file))
        return

    print("Great Scratchpad chat runtime. Type /help or /quit.")
    print(f"Thread: {thread_id}")
    while True:
        try:
            user_text = input("you> ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            break

        if not user_text:
            continue
        if user_text in {"/quit", "/exit"}:
            break
        if user_text == "/help":
            print("/quit, /exit, /recent, /audit")
            continue
        if user_text == "/recent":
            print(render_recent_turns(tdir, n=args.recent))
            continue
        if user_text == "/audit":
            print(render_audit(tdir, as_json=False))
            continue

        run_one(user_text)

def cmd_review(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)

    if args.review_cmd == "list":
        items = iter_review_items(root, args.thread, status=args.status)
        if not items:
            print("(no review items)")
            return
        for path, item in items:
            rel = path.relative_to(root)
            text = str(item.get("text", "")).strip().replace("\n", " ")
            audit_label = ""
            if args.audit:
                audit = audit_review_item(item, path)
                audit_label = (
                    f"\taudit={audit.get('status')}"
                    f"\tratio={audit.get('ratio')}"
                    f"\tsafe={review_item_is_safe(item, audit)}"
                )
            print(
                f"{rel}\tstatus={item.get('status')}\t"
                f"thread={item.get('thread_id')}\t"
                f"created={item.get('created_at')}\t"
                f"text={limit_text(text, 140)}"
                f"{audit_label}"
            )
        return

    if args.review_cmd == "show":
        item, item_path = load_review_item(root, args.thread, args.item)
        if args.json:
            payload = dict(item)
            payload["audit_preview"] = audit_review_item(item, item_path)
            payload["safe_to_apply"] = review_item_is_safe(item, payload["audit_preview"])
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_review_item(item_path, item, include_audit=True), end="")
        return

    if args.review_cmd == "apply":
        if args.all_safe:
            applied = apply_safe_review_items(root, args.thread)
            if not applied:
                print("(no safe pending review items)")
                return
            for turn_no, turn_path, item_path, audit in applied:
                print(
                    f"Applied safe review item {item_path.name} "
                    f"as turn {turn_no:06d}: {turn_path} "
                    f"(audit={audit.get('status')}, ratio={audit.get('ratio')})"
                )
            return
        if not args.item:
            raise SystemExit("Provide ITEM or use --all-safe.")
        if args.audit_preview:
            item, item_path = load_review_item(root, args.thread, args.item)
            print(render_review_item(item_path, item, include_audit=True), end="")
        turn_no, turn_path, item_path = apply_review_item(root, args.thread, args.item)
        print(f"Applied review item {item_path.name} as turn {turn_no:06d}: {turn_path}")
        return

    if args.review_cmd == "edit":
        text = None
        if args.text is not None or args.text_file:
            text = read_text_arg(args.text, args.text_file)
        updates = {
            "text": text,
            "center": args.center,
            "trajectory": args.trajectory,
            "anchors": args.anchors,
            "assumptions": args.assumptions,
            "open_questions": args.open_questions,
            "drift_risks": args.drift_risks,
        }
        item, item_path = edit_review_item(root, args.thread, args.item, updates)
        changed = ", ".join(
            key for key, value in updates.items() if value is not None
        )
        print(f"Edited review item {item_path.name}: {changed}")
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return

    if args.review_cmd == "reject":
        item_path = reject_review_item(root, args.thread, args.item)
        print(f"Rejected review item: {item_path}")
        return

def cmd_smoke(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    cfg = load_llm_config(root, args.llm_config, args.profile)
    trace_path = Path(args.trace_out).expanduser() if args.trace_out else None
    manifest_path = Path(args.manifest_out).expanduser() if args.manifest_out else default_manifest_path(trace_path)
    run_id = args.run_id or make_run_id("smoke")
    started_at = now_iso()
    prompt = args.text or (
        "Return exactly one JSON object proving this profile can follow the protocol: "
        "{\"ok\": true, \"message\": \"profile smoke passed\"}"
    )
    system_prompt = "You are a profile smoke test. Return strict JSON only."
    events: list[dict] = [
        {
            "time": now_iso(),
            "event": "smoke_start",
            "run_id": run_id,
            "llm": llm_config_metadata(cfg),
            "prompt_chars": len(prompt),
        }
    ]
    status = "ok"
    message = ""
    exit_code = 0
    report: dict = {}
    try:
        result = call_llm_result(cfg, prompt, system_prompt)
        raw_output = str(result.get("content", ""))
        parsed = extract_json_object(raw_output)
        report = {
            "ok": True,
            "run_id": run_id,
            "profile": cfg.get("profile", ""),
            "llm": {
                **llm_config_metadata(cfg),
                "response_model": result.get("response_model", ""),
                "prompt_chars": result.get("prompt_chars", 0),
                "system_prompt_chars": result.get("system_prompt_chars", 0),
                "duration_ms": result.get("duration_ms", 0),
                "usage": result.get("usage", {}),
                "hidden": result.get("hidden", {}),
            },
            "parsed": parsed,
            "content_excerpt": limit_text(raw_output, args.max_output_chars),
        }
        events.append(
            {
                "time": now_iso(),
                "event": "smoke_model_output",
                "run_id": run_id,
                "ok": True,
                "payload": parsed,
                "raw_output_chars": len(raw_output),
                "llm": report["llm"],
            }
        )
    except SystemExit as exc:
        status = "failed"
        message = str(exc)
        exit_code = exc.code if isinstance(exc.code, int) else 1
        events.append(
            {
                "time": now_iso(),
                "event": "smoke_error",
                "run_id": run_id,
                "error": message,
                "llm": llm_config_metadata(cfg),
            }
        )
        report = {
            "ok": False,
            "run_id": run_id,
            "profile": cfg.get("profile", ""),
            "error": message,
            "llm": llm_config_metadata(cfg),
        }
    except Exception as exc:
        status = "failed"
        message = str(exc)
        exit_code = 1
        events.append(
            {
                "time": now_iso(),
                "event": "smoke_error",
                "run_id": run_id,
                "error": message,
                "llm": llm_config_metadata(cfg),
            }
        )
        report = {
            "ok": False,
            "run_id": run_id,
            "profile": cfg.get("profile", ""),
            "error": message,
            "llm": llm_config_metadata(cfg),
        }
    finally:
        events.append(
            {
                "time": now_iso(),
                "event": "smoke_final",
                "run_id": run_id,
                "status": status,
            }
        )
        if trace_path:
            append_trace_events(trace_path, events)
        write_manifest(
            manifest_path,
            {
                "run_id": run_id,
                "command": "smoke",
                "status": status,
                "message": message,
                "started_at": started_at,
                "updated_at": now_iso(),
                "root": str(root),
                "trace_path": str(trace_path) if trace_path else "",
                "llm": llm_config_metadata(cfg),
                "summary": trace_summary(events),
            },
        )

    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else (
        f"smoke {status}: profile={cfg.get('profile', '')} run_id={run_id}"
    ))
    if status != "ok":
        raise SystemExit(exit_code)

def cmd_trace(args: argparse.Namespace) -> None:
    events = load_trace_events(Path(args.trace).expanduser())

    if args.trace_cmd == "summary":
        data = trace_report_data(events)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(trace_report_markdown(events, title=f"Trace Summary: {args.trace}"), end="")
        return

    if args.trace_cmd == "show":
        print(trace_show(events, step=args.step, line=args.line))
        return

    if args.trace_cmd == "report":
        report = trace_report_markdown(events, title=args.title)
        if args.out:
            out_path = Path(args.out).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(report, encoding="utf-8")
            print(f"Wrote trace report: {args.out}")
        else:
            print(report, end="")
        return

def cmd_experiment(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)

    if args.experiment_cmd == "run":
        profiles = [part.strip() for part in args.profiles.split(",") if part.strip()]
        if not profiles:
            raise SystemExit("Provide at least one profile with --profiles.")
        out_dir = Path(args.out_dir).expanduser() if args.out_dir else root / "runs" / safe_id(Path(args.scenario).stem)
        result = run_scenario_profiles(
            root=root,
            scenario_path=Path(args.scenario).expanduser(),
            profiles=profiles,
            llm_config=args.llm_config,
            out_dir=out_dir,
            thread_prefix=args.thread_prefix,
            policy=args.policy,
            queue_writes=args.queue_writes,
            yes=args.yes,
            max_steps=args.max_steps,
            recent_n=args.recent,
            max_tool_chars=args.max_tool_chars,
            json_repair_steps=args.json_repair_steps,
            quiet=args.quiet,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        print(f"Wrote experiment report: {result['report_path']}")
        for profile in result["profiles"]:
            print(
                f"{profile['profile']}\tthread={profile['thread_id']}\t"
                f"trace={profile['trace_path']}\tstatus={profile['status']}"
            )
        return

def _input_line(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        raise KeyboardInterrupt

def _input_block(label: str) -> str:
    print(f"{label} (finish with a single '.' line)")
    lines: list[str] = []
    while True:
        line = _input_line("| ")
        if line == ".":
            break
        lines.append(line)
    return "\n".join(lines).strip()

def _input_field(label: str) -> str:
    return _input_line(f"{label}> ").strip()

def _active_thread_or_warn(active_thread: str | None) -> str | None:
    if active_thread:
        return active_thread
    print("No active thread. Use: new THREAD or use THREAD")
    return None

def _parse_repl_args(parser: argparse.ArgumentParser, argv: list[str]) -> argparse.Namespace | None:
    try:
        return parser.parse_args(argv)
    except SystemExit:
        return None

def _repl_search_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="search", add_help=False)
    p.add_argument("query", nargs="+")
    p.add_argument("--top", type=int, default=8)
    p.add_argument("--width", type=int, default=420)
    return p

def _repl_recent_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recent", add_help=False)
    p.add_argument("n", nargs="?", type=int, default=6)
    p.add_argument("--max-chars", type=int, default=1600)
    return p

def _repl_pack_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pack", add_help=False)
    p.add_argument("query", nargs="+")
    p.add_argument("--recent", type=int, default=6)
    p.add_argument("--top", type=int, default=6)
    p.add_argument("--max-chars-per-doc", type=int, default=2200)
    p.add_argument("--include-guide", action="store_true")
    p.add_argument("--out", default=None)
    return p

def _repl_audit_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audit", add_help=False)
    p.add_argument("--json", action="store_true")
    p.add_argument("--max-flags", type=int, default=8)
    return p

def _repl_compact_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="compact", add_help=False)
    p.add_argument("--start", type=int, default=None)
    p.add_argument("--end", type=int, default=None)
    p.add_argument("--block-size", type=int, default=30)
    p.add_argument("--raw-excerpt-chars", type=int, default=900)
    return p

def _repl_handle_add(root: Path, active_thread: str | None, tokens: list[str]) -> str | None:
    if tokens[0] == "note":
        speaker = "note"
        thread_id = tokens[1] if len(tokens) > 1 else active_thread
    else:
        speaker = tokens[1] if len(tokens) > 1 else "note"
        thread_id = tokens[2] if len(tokens) > 2 else active_thread

    if speaker not in {"user", "assistant", "system", "tool", "note"}:
        print("Speaker must be one of: user, assistant, system, tool, note")
        return active_thread

    thread_id = _active_thread_or_warn(thread_id)
    if not thread_id:
        return active_thread

    raw = _input_block("Raw articulation")
    if not raw:
        print("No raw articulation; skipped.")
        return active_thread

    center = _input_field("Center pin")
    trajectory = _input_field("Trajectory")
    anchors = _input_field("Anchors")
    assumptions = _input_field("Local assumptions")
    open_questions = _input_field("Open questions")
    drift_risks = _input_field("Drift risks")

    turn_no, path = add_turn(
        root=root,
        thread_id=thread_id,
        speaker=speaker,
        raw=raw,
        center=center,
        trajectory=trajectory,
        anchors=anchors,
        assumptions=assumptions,
        open_questions=open_questions,
        drift_risks=drift_risks,
    )
    print(f"Added turn {turn_no:06d}: {path}")
    return thread_id

def _repl_show_llm(root: Path, explicit_path: str | None, profile: str | None) -> None:
    path = llm_config_path(root, explicit_path)
    print(f"LLM config: {path}")
    if not path.exists():
        print("(not configured)")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if "profiles" in data:
        default_profile = data.get("default_profile") or "(none)"
        profiles = ", ".join(sorted(data.get("profiles", {}))) or "(none)"
        print(f"Default profile: {default_profile}")
        print(f"REPL profile override: {profile or '(none)'}")
        print(f"Profiles: {profiles}")
    else:
        print(f"Backend: {data.get('backend', '(unknown)')}")

def _repl_handle_annotate(
    root: Path,
    active_thread: str | None,
    tokens: list[str],
    explicit_llm_config: str | None,
    llm_profile: str | None,
) -> str | None:
    speaker = tokens[1] if len(tokens) > 1 else "note"
    thread_id = tokens[2] if len(tokens) > 2 else active_thread

    if speaker not in {"user", "assistant", "system", "tool", "note"}:
        print("Speaker must be one of: user, assistant, system, tool, note")
        return active_thread

    thread_id = _active_thread_or_warn(thread_id)
    if not thread_id:
        return active_thread

    raw = _input_block("Raw articulation")
    if not raw:
        print("No raw articulation; skipped.")
        return active_thread

    cfg = load_llm_config(root, explicit_llm_config, llm_profile)
    annotation = draft_annotation(raw, cfg)
    print()
    print_annotation(annotation)

    answer = _input_line("Save this turn? [y/N]> ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Skipped save.")
        return thread_id

    turn_no, path = add_turn(
        root=root,
        thread_id=thread_id,
        speaker=speaker,
        raw=raw,
        center=annotation["center"],
        trajectory=annotation["trajectory"],
        anchors=annotation["anchors"],
        assumptions=annotation["assumptions"],
        open_questions=annotation["open_questions"],
        drift_risks=annotation["drift_risks"],
    )
    print(f"Added turn {turn_no:06d}: {path}")
    return thread_id

def _repl_run_command(
    root: Path,
    active_thread: str | None,
    line: str,
    explicit_llm_config: str | None,
    llm_profile: str | None,
) -> tuple[str | None, bool]:
    try:
        tokens = shlex.split(line)
    except ValueError as exc:
        print(f"Could not parse command: {exc}")
        return active_thread, True

    if not tokens:
        return active_thread, True

    cmd = tokens[0].lower()

    if cmd in {"quit", "exit"}:
        return active_thread, False

    if cmd in {"help", "?"}:
        print(REPL_HELP)
        return active_thread, True

    if cmd == "root":
        print(root)
        return active_thread, True

    if cmd in {"list", "threads"}:
        cmd_list(argparse.Namespace(root=str(root)))
        return active_thread, True

    if cmd == "new":
        if len(tokens) < 2:
            print("Usage: new THREAD [TITLE...]")
            return active_thread, True
        thread_id = tokens[1]
        title = " ".join(tokens[2:])
        cmd_new(argparse.Namespace(root=str(root), thread=thread_id, title=title))
        return thread_id, True

    if cmd == "use":
        if len(tokens) != 2:
            print("Usage: use THREAD")
            return active_thread, True
        thread_id = tokens[1]
        ensure_thread(root, thread_id)
        print(f"Active thread: {safe_id(thread_id)}")
        return safe_id(thread_id), True

    if cmd == "thread":
        print(active_thread or "(none)")
        return active_thread, True

    if cmd in {"add", "note"}:
        return _repl_handle_add(root, active_thread, tokens), True

    if cmd == "llm":
        _repl_show_llm(root, explicit_llm_config, llm_profile)
        return active_thread, True

    if cmd == "annotate":
        return _repl_handle_annotate(root, active_thread, tokens, explicit_llm_config, llm_profile), True

    if cmd == "search":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_search_parser(), tokens[1:])
        if not ns:
            print("Usage: search QUERY [--top N] [--width N]")
            return active_thread, True
        cmd_search(
            argparse.Namespace(
                root=str(root),
                thread=thread_id,
                query=" ".join(ns.query),
                top=ns.top,
                width=ns.width,
            )
        )
        return active_thread, True

    if cmd == "recent":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_recent_parser(), tokens[1:])
        if not ns:
            print("Usage: recent [N] [--max-chars N]")
            return active_thread, True
        cmd_recent(argparse.Namespace(root=str(root), thread=thread_id, n=ns.n, max_chars=ns.max_chars))
        return active_thread, True

    if cmd == "pack":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_pack_parser(), tokens[1:])
        if not ns:
            print("Usage: pack QUERY [--recent N] [--top N] [--include-guide] [--out PATH]")
            return active_thread, True
        cmd_pack(
            argparse.Namespace(
                root=str(root),
                thread=thread_id,
                query=" ".join(ns.query),
                recent=ns.recent,
                top=ns.top,
                max_chars_per_doc=ns.max_chars_per_doc,
                include_guide=ns.include_guide,
                out=ns.out,
            )
        )
        return active_thread, True

    if cmd == "audit":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_audit_parser(), tokens[1:])
        if not ns:
            print("Usage: audit [--json] [--max-flags N]")
            return active_thread, True
        cmd_audit(argparse.Namespace(root=str(root), thread=thread_id, json=ns.json, max_flags=ns.max_flags))
        return active_thread, True

    if cmd == "guide":
        cmd_guide(argparse.Namespace(root=str(root)))
        return active_thread, True

    if cmd == "compact":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_compact_parser(), tokens[1:])
        if not ns:
            print("Usage: compact [--start N] [--end N] [--block-size N]")
            return active_thread, True
        cmd_compact(
            argparse.Namespace(
                root=str(root),
                thread=thread_id,
                start=ns.start,
                end=ns.end,
                block_size=ns.block_size,
                raw_excerpt_chars=ns.raw_excerpt_chars,
            )
        )
        return active_thread, True

    print(f"Unknown command: {tokens[0]}. Type 'help' for commands.")
    return active_thread, True

def cmd_repl(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)

    active_thread = safe_id(args.thread) if args.thread else None
    if active_thread:
        try:
            ensure_thread(root, active_thread)
        except SystemExit as exc:
            print(exc)
            active_thread = None

    print("Great Scratchpad REPL. Type 'help' for commands, 'quit' to exit.")
    print(f"Root: {root}")
    if active_thread:
        print(f"Active thread: {active_thread}")
    if args.llm_config or args.llm_profile:
        _repl_show_llm(root, args.llm_config, args.llm_profile)

    while True:
        prompt = f"sr:{active_thread}> " if active_thread else "sr> "
        try:
            line = _input_line(prompt)
            active_thread, keep_running = _repl_run_command(
                root,
                active_thread,
                line,
                args.llm_config,
                args.llm_profile,
            )
        except KeyboardInterrupt:
            print()
            break
        except SystemExit as exc:
            if exc.code:
                print(exc)
            keep_running = True

        if not keep_running:
            break

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Great Scratchpad: trajectory-preserving markdown memory.",
    )
    p.add_argument(
        "--root",
        default=os.environ.get("GS_ROOT", ROOT_DEFAULT),
        help=f"Scratchpad root directory. Default: {ROOT_DEFAULT}",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Initialize scratchpad root.")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("guide", help="Print the Great Scratchpad annotation guide.")
    sp.set_defaults(func=cmd_guide)

    sp = sub.add_parser("repl", help="Start an interactive Great Scratchpad REPL.")
    sp.add_argument("thread", nargs="?", default=None)
    sp.add_argument("--llm-config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    sp.add_argument("--llm-profile", default=None, help="LLM profile name to use in the REPL.")
    sp.set_defaults(func=cmd_repl)

    sp = sub.add_parser("annotate", help="Draft trajectory annotations with a configured LLM.")
    sp.add_argument("--text", default=None)
    sp.add_argument("--text-file", default=None)
    sp.add_argument("--llm-config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    sp.add_argument("--profile", default=None, help="LLM profile name.")
    sp.add_argument("--json", action="store_true", help="Print annotation JSON.")
    sp.add_argument("--save-thread", default=None, help="Save drafted annotation as a turn in THREAD.")
    sp.add_argument("--speaker", default="note", choices=["user", "assistant", "system", "tool", "note"])
    sp.add_argument("--json-repair-steps", type=int, default=1, help="Retry invalid JSON outputs up to N times.")
    sp.set_defaults(func=cmd_annotate)

    sp = sub.add_parser("llm-config", help="Create or inspect LLM provider/local profiles.")
    sp.add_argument("--config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    llm_sub = sp.add_subparsers(dest="llm_cmd", required=True)

    sp2 = llm_sub.add_parser("show", help="Print LLM config.")
    sp2.set_defaults(func=cmd_llm_config_show)

    sp2 = llm_sub.add_parser("provider", help="Configure an OpenAI-compatible provider API.")
    sp2.add_argument("--profile", default="provider")
    sp2.add_argument("--base-url", required=True, help="Base URL or full /chat/completions URL.")
    sp2.add_argument("--api-key-env", default="", help="Environment variable containing the API key.")
    sp2.add_argument("--model", required=True)
    sp2.add_argument("--temperature", type=float, default=0.2)
    sp2.add_argument("--max-tokens", type=int, default=900)
    sp2.add_argument("--top-p", type=float, default=None)
    sp2.add_argument("--seed", type=int, default=None)
    sp2.add_argument("--stop", action="append", default=[], help="Stop sequence. Repeat for multiple stops.")
    sp2.add_argument("--json-mode", choices=["off", "json_object"], default="off")
    sp2.add_argument("--timeout", type=float, default=120)
    sp2.add_argument("--default", action="store_true", help="Make this the default profile.")
    sp2.set_defaults(func=cmd_llm_config_provider)

    sp2 = llm_sub.add_parser("local", help="Configure a local command-backed LLM.")
    sp2.add_argument("--profile", default="local")
    sp2.add_argument("--command", required=True, help="Command to run. Prompt is passed on stdin unless {prompt} or {prompt_file} is used.")
    sp2.add_argument("--model-path", default="", help="Optional local model path available as {model_path}.")
    sp2.add_argument("--timeout", type=float, default=120)
    sp2.add_argument("--default", action="store_true", help="Make this the default profile.")
    sp2.set_defaults(func=cmd_llm_config_local)

    sp2 = llm_sub.add_parser("hf", help="Configure an optional Hugging Face transformers-backed local LLM.")
    sp2.add_argument("--profile", default="hf")
    sp2.add_argument("--model", default="", help="Hugging Face model id or local path.")
    sp2.add_argument("--model-path", default="", help="Local model path. Overrides --model when set.")
    sp2.add_argument("--device", default="auto", help="Torch device such as auto, cpu, mps, cuda.")
    sp2.add_argument("--dtype", default="", help="Optional torch dtype such as float16 or bfloat16.")
    sp2.add_argument("--temperature", type=float, default=0.1)
    sp2.add_argument("--top-p", type=float, default=None)
    sp2.add_argument("--seed", type=int, default=None)
    sp2.add_argument("--max-new-tokens", type=int, default=900)
    sp2.add_argument("--capture-hidden", action="store_true", help="Capture generated hidden-state shape metadata when supported.")
    sp2.add_argument("--default", action="store_true", help="Make this the default profile.")
    sp2.set_defaults(func=cmd_llm_config_hf)

    sp = sub.add_parser("smoke", help="Run a one-shot LLM profile protocol smoke test.")
    sp.add_argument("--llm-config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    sp.add_argument("--profile", default=None, help="LLM profile name.")
    sp.add_argument("--text", default=None, help="Custom smoke prompt. Must return one JSON object.")
    sp.add_argument("--trace-out", default=None, help="Append smoke trace events as JSONL to PATH.")
    sp.add_argument("--manifest-out", default=None, help="Write experiment manifest. Default: TRACE_OUT with .manifest.json")
    sp.add_argument("--run-id", default="", help="Stable run id to attach to trace and manifest.")
    sp.add_argument("--max-output-chars", type=int, default=1200)
    sp.add_argument("--json", action="store_true", help="Print detailed JSON report.")
    sp.set_defaults(func=cmd_smoke)

    sp = sub.add_parser("chat", help="Run a minimal LLM chat runtime with scratchpad actions.")
    sp.add_argument("thread")
    sp.add_argument("--text", default=None, help="Run one chat turn with this text.")
    sp.add_argument("--text-file", default=None, help="Run one chat turn with text from this file.")
    sp.add_argument("--llm-config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    sp.add_argument("--profile", default=None, help="LLM profile name.")
    sp.add_argument("--max-steps", type=int, default=4, help="Maximum scratchpad action steps per turn.")
    sp.add_argument("--recent", type=int, default=4, help="Recent scratchpad turns included in each prompt.")
    sp.add_argument("--max-tool-chars", type=int, default=6000, help="Maximum chars returned from each scratchpad action.")
    sp.add_argument("--yes", action="store_true", help="Allow runtime write actions without prompting.")
    sp.add_argument("--quiet", action="store_true", help="Do not print tool action progress.")
    sp.add_argument("--trace-out", default=None, help="Append chat runtime trace events as JSONL to PATH.")
    sp.add_argument("--manifest-out", default=None, help="Write experiment manifest. Default: TRACE_OUT with .manifest.json")
    sp.add_argument("--run-id", default="", help="Stable run id to attach to trace and manifest.")
    sp.add_argument("--json-repair-steps", type=int, default=1, help="Retry invalid JSON runtime outputs up to N times.")
    sp.add_argument("--queue-writes", action="store_true", help="Queue scratchpad.add_note writes for review instead of saving immediately.")
    sp.add_argument("--policy", choices=sorted(ACTION_POLICIES), default="balanced", help="Named scratchpad action policy.")
    sp.set_defaults(func=cmd_chat)

    sp = sub.add_parser("trace", help="Inspect chat/smoke/experiment trace JSONL.")
    trace_sub = sp.add_subparsers(dest="trace_cmd", required=True)

    sp2 = trace_sub.add_parser("summary", help="Print a trace summary report.")
    sp2.add_argument("trace")
    sp2.add_argument("--json", action="store_true")
    sp2.set_defaults(func=cmd_trace)

    sp2 = trace_sub.add_parser("show", help="Show raw trace events.")
    sp2.add_argument("trace")
    sp2.add_argument("--step", type=int, default=None, help="Only show events for one tool step.")
    sp2.add_argument("--line", type=int, default=None, help="Only show one JSONL line.")
    sp2.set_defaults(func=cmd_trace)

    sp2 = trace_sub.add_parser("report", help="Write or print a Markdown trace report.")
    sp2.add_argument("trace")
    sp2.add_argument("--title", default="Great Scratchpad Trace Report")
    sp2.add_argument("--out", default=None)
    sp2.set_defaults(func=cmd_trace)

    sp = sub.add_parser("experiment", help="Run repeatable scratchpad scenarios across profiles.")
    experiment_sub = sp.add_subparsers(dest="experiment_cmd", required=True)

    sp2 = experiment_sub.add_parser("run", help="Run a Markdown scenario across LLM profiles.")
    sp2.add_argument("scenario")
    sp2.add_argument("--profiles", required=True, help="Comma-separated LLM profile names.")
    sp2.add_argument("--llm-config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    sp2.add_argument("--out-dir", default=None, help="Directory for traces and reports. Default: ROOT/runs/SCENARIO")
    sp2.add_argument("--thread-prefix", default="experiment", help="Prefix for generated scratchpad thread ids.")
    sp2.add_argument("--policy", choices=sorted(ACTION_POLICIES), default="balanced", help="Named scratchpad action policy.")
    sp2.add_argument("--queue-writes", action="store_true", help="Queue scratchpad.add_note writes for review instead of saving immediately.")
    sp2.add_argument("--yes", action="store_true", help="Allow runtime write actions without prompting.")
    sp2.add_argument("--max-steps", type=int, default=4, help="Maximum scratchpad action steps per turn.")
    sp2.add_argument("--recent", type=int, default=4, help="Recent scratchpad turns included in each prompt.")
    sp2.add_argument("--max-tool-chars", type=int, default=6000, help="Maximum chars returned from each scratchpad action.")
    sp2.add_argument("--json-repair-steps", type=int, default=1, help="Retry invalid JSON runtime outputs up to N times.")
    sp2.add_argument("--quiet", action="store_true", help="Do not print tool action progress.")
    sp2.add_argument("--json", action="store_true", help="Print detailed JSON result.")
    sp2.set_defaults(func=cmd_experiment)

    sp = sub.add_parser("review", help="Review queued scratchpad write requests.")
    review_sub = sp.add_subparsers(dest="review_cmd", required=True)

    sp2 = review_sub.add_parser("list", help="List queued write requests.")
    sp2.add_argument("thread", nargs="?", default=None)
    sp2.add_argument("--status", default="pending", help="Filter by status. Use empty string to show all.")
    sp2.add_argument("--audit", action="store_true", help="Show audit preview status for each item.")
    sp2.set_defaults(func=cmd_review)

    sp2 = review_sub.add_parser("show", help="Show one queued write request with audit preview.")
    sp2.add_argument("thread")
    sp2.add_argument("item")
    sp2.add_argument("--json", action="store_true")
    sp2.set_defaults(func=cmd_review)

    sp2 = review_sub.add_parser("apply", help="Apply one queued write request as a note turn.")
    sp2.add_argument("thread")
    sp2.add_argument("item", nargs="?")
    sp2.add_argument("--audit-preview", action="store_true", help="Print audit preview before applying.")
    sp2.add_argument("--all-safe", action="store_true", help="Apply all pending items whose audit preview is safe.")
    sp2.set_defaults(func=cmd_review)

    sp2 = review_sub.add_parser("edit", help="Edit one pending queued write request before applying it.")
    sp2.add_argument("thread")
    sp2.add_argument("item")
    sp2.add_argument("--text", default=None)
    sp2.add_argument("--text-file", default=None)
    sp2.add_argument("--center", default=None)
    sp2.add_argument("--trajectory", default=None)
    sp2.add_argument("--anchors", default=None)
    sp2.add_argument("--assumptions", default=None)
    sp2.add_argument("--open-questions", default=None)
    sp2.add_argument("--drift-risks", default=None)
    sp2.set_defaults(func=cmd_review)

    sp2 = review_sub.add_parser("reject", help="Reject one queued write request.")
    sp2.add_argument("thread")
    sp2.add_argument("item")
    sp2.set_defaults(func=cmd_review)

    sp = sub.add_parser("new", help="Create or open a thread.")
    sp.add_argument("thread")
    sp.add_argument("--title", default="")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("list", help="List threads.")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("add", help="Add one turn as trajectory-aware markdown.")
    sp.add_argument("thread")
    sp.add_argument("--speaker", required=True, choices=["user", "assistant", "system", "tool", "note"])
    sp.add_argument("--text", default=None)
    sp.add_argument("--text-file", default=None)
    sp.add_argument("--center", default="", help="The center pin of this turn.")
    sp.add_argument("--trajectory", default="", help="How this turn moves the conversation.")
    sp.add_argument("--anchors", default="", help="Phrases, definitions, or metaphors worth preserving.")
    sp.add_argument("--assumptions", default="", help="Local assumptions active in this turn.")
    sp.add_argument("--open-questions", default="", help="Unresolved questions left by this turn.")
    sp.add_argument("--drift-risks", default="", help="Ways future context might drift.")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("search", help="Search thread memory.")
    sp.add_argument("thread")
    sp.add_argument("query")
    sp.add_argument("--top", type=int, default=8)
    sp.add_argument("--width", type=int, default=420)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("recent", help="Show recent turns.")
    sp.add_argument("thread")
    sp.add_argument("-n", type=int, default=6)
    sp.add_argument("--max-chars", type=int, default=1600)
    sp.set_defaults(func=cmd_recent)

    sp = sub.add_parser("compact", help="Create trajectory blocks from raw turns.")
    sp.add_argument("thread")
    sp.add_argument("--start", type=int, default=None)
    sp.add_argument("--end", type=int, default=None)
    sp.add_argument("--block-size", type=int, default=30)
    sp.add_argument("--raw-excerpt-chars", type=int, default=900)
    sp.set_defaults(func=cmd_compact)

    sp = sub.add_parser("pack", help="Build a retrieval context pack for pasting into an LLM thread.")
    sp.add_argument("thread")
    sp.add_argument("query")
    sp.add_argument("--recent", type=int, default=6)
    sp.add_argument("--top", type=int, default=6)
    sp.add_argument("--max-chars-per-doc", type=int, default=2200)
    sp.add_argument("--include-guide", action="store_true", help="Include annotation guide in the generated context pack.")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_pack)

    sp = sub.add_parser("audit", help="Audit annotation/raw ratio and possible anchor hallucinations.")
    sp.add_argument("thread")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--max-flags", type=int, default=8)
    sp.set_defaults(func=cmd_audit)

    return p

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
