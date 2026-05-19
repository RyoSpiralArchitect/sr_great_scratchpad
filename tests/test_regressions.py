from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sr_great_scratchpad as gs


class GreatScratchpadRegressionTests(unittest.TestCase):
    def test_raw_markdown_headings_do_not_truncate_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gs.ensure_thread_dirs(root, "t")
            _, path = gs.add_turn(
                root=root,
                thread_id="t",
                speaker="user",
                raw="before\n## User-visible heading\nafter",
                center="center",
            )

            md = path.read_text(encoding="utf-8")
            raw = gs.parse_section(md, "Raw articulation")
            self.assertIn("## User-visible heading", raw)
            self.assertIn("after", raw)

            block = gs.compact_one_range(root / "threads" / "t", 1, 1, raw_excerpt_chars=200)
            block_text = block.read_text(encoding="utf-8")
            self.assertIn("## User-visible heading", block_text)
            self.assertIn("after", block_text)

    def test_compact_rejects_non_positive_block_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gs.ensure_thread_dirs(root, "t")
            gs.add_turn(root=root, thread_id="t", speaker="user", raw="hello")

            args = argparse.Namespace(
                root=str(root),
                thread="t",
                start=None,
                end=None,
                block_size=0,
                raw_excerpt_chars=900,
            )
            with self.assertRaises(SystemExit):
                gs.cmd_compact(args)

    def test_chat_action_bad_numeric_field_returns_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            gs.add_turn(root=root, thread_id="t", speaker="user", raw="hello")

            observation = gs.run_scratchpad_action(
                root=root,
                tdir=tdir,
                thread_id="t",
                action_obj={
                    "action": "scratchpad.search",
                    "query": "hello",
                    "top": "oops",
                },
            )
            self.assertIn("scratchpad.search failed", observation)
            self.assertIn("top must be an integer", observation)

    def test_local_command_allows_literal_braces(self) -> None:
        cfg = {
            "backend": "command",
            "command": [
                sys.executable,
                "-S",
                "-c",
                "print('{\"type\":\"final\",\"message\":\"ok\"}')",
            ],
            "timeout": 5,
        }

        output = gs.call_command_llm(cfg, "ignored")
        self.assertEqual(output, '{"type":"final","message":"ok"}')

    def test_local_command_usage_is_estimated(self) -> None:
        cfg = {
            "backend": "command",
            "command": [
                sys.executable,
                "-S",
                "-c",
                "import json; print(json.dumps({'type':'final','message':'ok'}))",
            ],
            "timeout": 5,
        }

        result = gs.call_llm_result(cfg, "hello local model", "Return JSON.")
        self.assertEqual(result["usage"]["estimated"], True)
        self.assertGreater(result["usage"]["prompt_tokens"], 0)
        self.assertGreater(result["usage"]["completion_tokens"], 0)

    def test_annotation_json_repair_recovers_invalid_output(self) -> None:
        code = (
            "import json,sys\n"
            "p=sys.stdin.read()\n"
            "if 'Previous output:' in p:\n"
            " print(json.dumps({'center':'c','trajectory':'t','anchors':'a',"
            "'assumptions':'s','open_questions':'q','drift_risks':'d'}))\n"
            "else:\n"
            " print('not json')\n"
        )
        cfg = {
            "backend": "command",
            "command": [sys.executable, "-S", "-c", code],
            "timeout": 5,
        }

        annotation = gs.draft_annotation("raw", cfg, json_repair_steps=1)
        self.assertEqual(annotation["center"], "c")

    def test_chat_json_repair_recovers_invalid_runtime_output(self) -> None:
        code = (
            "import json,sys\n"
            "p=sys.stdin.read()\n"
            "if 'not valid JSON' in p:\n"
            " print(json.dumps({'type':'final','message':'repaired final'}))\n"
            "else:\n"
            " print('not json')\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            cfg = {
                "backend": "command",
                "command": [sys.executable, "-S", "-c", code],
                "timeout": 5,
            }
            events: list[dict] = []

            message = gs.run_chat_turn(
                root=root,
                tdir=tdir,
                thread_id="t",
                cfg=cfg,
                user_text="repair please",
                history=[],
                verbose=False,
                trace_events=events,
                json_repair_steps=1,
            )

            self.assertEqual(message, "repaired final")
            self.assertIn("json_parse_error", [event["event"] for event in events])
            self.assertEqual(events[-1]["repair_attempts"], 1)

    def test_chat_normalizes_action_name_in_type_field(self) -> None:
        code = (
            "import json,sys\n"
            "p=sys.stdin.read()\n"
            "if 'Action 1: scratchpad.add_note' in p:\n"
            " print(json.dumps({'type':'final','message':'done'}))\n"
            "else:\n"
            " print(json.dumps({'type':'scratchpad.add_note','text':'note from drifted schema'}))\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            cfg = {
                "backend": "command",
                "command": [sys.executable, "-S", "-c", code],
                "timeout": 5,
            }
            events: list[dict] = []

            message = gs.run_chat_turn(
                root=root,
                tdir=tdir,
                thread_id="t",
                cfg=cfg,
                user_text="write",
                history=[],
                yes=True,
                verbose=False,
                trace_events=events,
            )

            self.assertEqual(message, "done")
            tool_event = next(event for event in events if event["event"] == "tool_observation")
            self.assertEqual(tool_event["action"], "scratchpad.add_note")
            self.assertIn("wrote turn", tool_event["observation"])

    def test_audit_short_raw_roomy_annotation_is_not_overgrown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gs.ensure_thread_dirs(root, "t")
            _, path = gs.add_turn(
                root=root,
                thread_id="t",
                speaker="user",
                raw=(
                    "Semantic Compression preserves conclusions but destroys "
                    "Trajectory. Topic Drift starts when the center pin moves."
                ),
                center="semantic compression and trajectory loss",
                trajectory=(
                    "The turn moves from useful summarization toward practical "
                    "Topic Drift risk and retrieval timing."
                ),
                anchors="Semantic Compression, Trajectory, Topic Drift, center pin",
                assumptions="Markdown raw files preserve more articulation than terse YAML",
                open_questions="when retrieval should become agentic",
                drift_risks="saving only conclusions and losing the path",
            )

            result = gs.audit_turn_md(path)
            self.assertEqual(result["status"], "roomy")
            self.assertEqual(result["missing_fields"], [])
            self.assertEqual(result["anchor_count"], 4)

    def test_audit_ignores_placeholder_annotation_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gs.ensure_thread_dirs(root, "t")
            _, path = gs.add_turn(
                root=root,
                thread_id="t",
                speaker="user",
                raw="A raw turn without annotation should audit as compressed.",
            )

            result = gs.audit_turn_md(path)
            self.assertEqual(result["annotation_chars"], 0)
            self.assertEqual(result["status"], "too_compressed")
            self.assertGreaterEqual(len(result["missing_fields"]), 4)

    def test_context_pack_includes_trajectory_source_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            gs.add_turn(
                root=root,
                thread_id="t",
                speaker="user",
                raw="Semantic Compression can cause Topic Drift.",
                center="semantic compression",
                trajectory="The thread moves toward retrieval-backed continuity.",
                anchors="Semantic Compression, Topic Drift",
                open_questions="how retrieval should choose sources",
                drift_risks="losing the path while keeping the answer",
            )

            pack = gs.build_context_pack(
                root=root,
                tdir=tdir,
                query="Topic Drift",
                recent_n=1,
                top=1,
                max_chars_per_doc=1200,
            )

            self.assertIn("## Source trajectory index", pack)
            self.assertIn("### recent: turns/000001-user.md", pack)
            self.assertIn("- Selection: recent window", pack)
            self.assertIn("- Center: semantic compression", pack)
            self.assertIn("- Trajectory: The thread moves toward retrieval-backed continuity.", pack)

    def test_chat_runtime_records_trace_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            gs.add_turn(
                root=root,
                thread_id="t",
                speaker="user",
                raw="Semantic Compression can cause Topic Drift.",
                center="semantic compression",
                anchors="Semantic Compression, Topic Drift",
            )
            cfg = {
                "backend": "command",
                "command": [
                    sys.executable,
                    "-S",
                    str(Path("scripts/fake_chat_llm.py").resolve()),
                ],
                "timeout": 5,
            }
            events: list[dict] = []

            message = gs.run_chat_turn(
                root=root,
                tdir=tdir,
                thread_id="t",
                cfg=cfg,
                user_text="Use memory.",
                history=[],
                yes=True,
                verbose=False,
                trace_events=events,
            )

            self.assertIn("Fake chat final", message)
            event_names = [event["event"] for event in events]
            self.assertIn("turn_start", event_names)
            self.assertGreaterEqual(event_names.count("model_output"), 3)
            self.assertGreaterEqual(event_names.count("tool_observation"), 2)
            self.assertEqual(event_names[-1], "final")
            model_events = [event for event in events if event["event"] == "model_output"]
            self.assertIn("prompt_chars", model_events[0]["llm"])
            self.assertIn("duration_ms", model_events[0]["llm"])

            trace_path = root / "chat_trace.jsonl"
            gs.append_trace_events(trace_path, events)
            saved = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(saved), len(events))
            self.assertEqual(saved[-1]["event"], "final")

    def test_provider_smoke_uses_openai_compatible_endpoint_and_usage(self) -> None:
        requests: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                requests.append({"path": self.path, "body": body})
                content = json.dumps({"type": "final", "message": "provider final"})
                payload = {
                    "model": "fake-provider-model",
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                }
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tdir = gs.ensure_thread_dirs(root, "t")
                cfg = {
                    "backend": "openai-compatible",
                    "profile": "provider-test",
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "model": "fake-model",
                    "top_p": 0.7,
                    "seed": 42,
                    "stop": ["STOP"],
                    "json_mode": "json_object",
                    "timeout": 5,
                }
                events: list[dict] = []

                message = gs.run_chat_turn(
                    root=root,
                    tdir=tdir,
                    thread_id="t",
                    cfg=cfg,
                    user_text="provider please",
                    history=[],
                    verbose=False,
                    trace_events=events,
                )

                self.assertEqual(message, "provider final")
                self.assertEqual(requests[0]["path"], "/v1/chat/completions")
                self.assertEqual(requests[0]["body"]["top_p"], 0.7)
                self.assertEqual(requests[0]["body"]["seed"], 42)
                self.assertEqual(requests[0]["body"]["stop"], ["STOP"])
                self.assertEqual(requests[0]["body"]["response_format"], {"type": "json_object"})
                model_event = next(event for event in events if event["event"] == "model_output")
                self.assertEqual(model_event["llm"]["profile"], "provider-test")
                self.assertEqual(model_event["llm"]["usage"]["total_tokens"], 10)
        finally:
            server.shutdown()
            server.server_close()

    def test_smoke_cli_writes_trace_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parser = gs.build_parser()
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "llm-config",
                    "local",
                    "--profile",
                    "smoke-local",
                    "--command",
                    (
                        f"{sys.executable} -S -c "
                        "\"import json; print(json.dumps({'ok': True, 'message': 'passed'}))\""
                    ),
                    "--default",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)

            trace_path = root / "nested" / "traces" / "smoke.jsonl"
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "smoke",
                    "--profile",
                    "smoke-local",
                    "--trace-out",
                    str(trace_path),
                    "--run-id",
                    "test-smoke-run",
                    "--json",
                ]
            )
            out = io.StringIO()
            with redirect_stdout(out):
                args.func(args)

            report = json.loads(out.getvalue())
            self.assertEqual(report["ok"], True)
            self.assertTrue(trace_path.exists())
            manifest_path = root / "nested" / "traces" / "smoke.manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_id"], "test-smoke-run")
            saved = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all(event["run_id"] == "test-smoke-run" for event in saved))

    def test_chat_cli_writes_run_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parser = gs.build_parser()
            gs.ensure_thread_dirs(root, "t")
            gs.add_turn(root=root, thread_id="t", speaker="user", raw="Semantic Compression causes Topic Drift.")
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "llm-config",
                    "local",
                    "--profile",
                    "fake-chat",
                    "--command",
                    f"{sys.executable} -S {Path('scripts/fake_chat_llm.py').resolve()}",
                    "--default",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)

            trace_path = root / "runs" / "chat.jsonl"
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "chat",
                    "t",
                    "--profile",
                    "fake-chat",
                    "--text",
                    "Use memory.",
                    "--queue-writes",
                    "--yes",
                    "--quiet",
                    "--trace-out",
                    str(trace_path),
                    "--run-id",
                    "chat-run",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)

            manifest = json.loads((root / "runs" / "chat.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_id"], "chat-run")
            self.assertEqual(manifest["command"], "chat")
            self.assertEqual(manifest["summary"]["event_counts"]["final"], 1)

    def test_hf_config_is_optional_profile_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parser = gs.build_parser()
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "llm-config",
                    "hf",
                    "--profile",
                    "hf-local",
                    "--model",
                    "local/model",
                    "--device",
                    "cpu",
                    "--capture-hidden",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)
            cfg = gs.load_llm_config(root, None, "hf-local")
            self.assertEqual(cfg["backend"], "huggingface")
            self.assertEqual(cfg["model"], "local/model")
            self.assertEqual(cfg["capture_hidden"], True)

    def test_queue_writes_defers_add_note_until_review_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            gs.add_turn(root=root, thread_id="t", speaker="user", raw="hello")
            cfg = {
                "backend": "command",
                "command": [
                    sys.executable,
                    "-S",
                    str(Path("scripts/fake_chat_llm.py").resolve()),
                ],
                "timeout": 5,
            }

            message = gs.run_chat_turn(
                root=root,
                tdir=tdir,
                thread_id="t",
                cfg=cfg,
                user_text="queue write",
                history=[],
                yes=True,
                verbose=False,
                queue_writes=True,
            )

            self.assertIn("Fake chat final", message)
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 1)
            items = gs.iter_review_items(root, "t")
            self.assertEqual(len(items), 1)
            item_id = items[0][0].name
            edited, _edited_path = gs.edit_review_item(
                root,
                "t",
                item_id,
                {
                    "text": "edited queued note",
                    "center": "edited center",
                },
            )
            self.assertEqual(edited["text"], "edited queued note")
            turn_no, turn_path, _item_path = gs.apply_review_item(root, "t", item_id)
            self.assertEqual(turn_no, 2)
            self.assertTrue(turn_path.exists())
            self.assertIn("edited queued note", turn_path.read_text(encoding="utf-8"))
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 2)

    def test_trace_report_and_show_summarize_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "trace.jsonl"
            events = [
                {
                    "event": "turn_start",
                    "run_id": "trace-test",
                    "llm": {"profile": "p", "model": "m", "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1}},
                },
                {
                    "event": "model_output",
                    "run_id": "trace-test",
                    "tool_step": 0,
                    "payload": {"type": "action", "action": "scratchpad.search", "query": "Topic Drift"},
                    "llm": {"profile": "p", "model": "m", "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}},
                },
                {
                    "event": "tool_observation",
                    "run_id": "trace-test",
                    "tool_step": 1,
                    "action": "scratchpad.add_note",
                    "observation": "scratchpad.add_note queued for review: review_queue/t/item.json",
                },
                {"event": "final", "run_id": "trace-test", "message": "done"},
            ]
            gs.append_trace_events(trace_path, events)

            loaded = gs.load_trace_events(trace_path)
            data = gs.trace_report_data(loaded)
            report = gs.trace_report_markdown(loaded)

            self.assertEqual(data["run_ids"], ["trace-test"])
            self.assertEqual(data["queued_writes"], 1)
            self.assertIn("scratchpad.search", report)
            self.assertIn("Queued writes: 1", report)
            self.assertIn('"event": "model_output"', gs.trace_show(loaded, line=2))

    def test_review_show_and_apply_all_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            action = {
                "text": (
                    "Semantic Compression and Topic Drift need a review queue before scratchpad notes are applied. "
                    "The queue lets us inspect anchors, center pins, and drift risks before memory becomes durable."
                ),
                "center": "Semantic Compression and Topic Drift review queue",
                "trajectory": "A queued note becomes inspectable before durable memory",
                "anchors": "Semantic Compression, Topic Drift, review queue",
                "assumptions": "review queue protects scratchpad memory",
                "open_questions": "when queued notes should auto-apply",
                "drift_risks": "unsafe notes becoming memory without review",
            }
            item_path = gs.queue_add_note(root, "t", action)
            item = json.loads(item_path.read_text(encoding="utf-8"))
            audit = gs.audit_review_item(item, item_path)

            self.assertTrue(gs.review_item_is_safe(item, audit))
            rendered = gs.render_review_item(item_path, item)
            self.assertIn("## Audit preview", rendered)
            applied = gs.apply_safe_review_items(root, "t")

            self.assertEqual(len(applied), 1)
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 1)
            self.assertIn("Semantic Compression", applied[0][1].read_text(encoding="utf-8"))

    def test_read_only_policy_blocks_add_note(self) -> None:
        code = (
            "import json,sys\n"
            "p=sys.stdin.read()\n"
            "if 'blocked: read-only policy' in p:\n"
            " print(json.dumps({'type':'final','message':'blocked observed'}))\n"
            "else:\n"
            " print(json.dumps({'type':'action','action':'scratchpad.add_note','text':'Do not write this'}))\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            cfg = {
                "backend": "command",
                "command": [sys.executable, "-S", "-c", code],
                "timeout": 5,
            }
            events: list[dict] = []

            message = gs.run_chat_turn(
                root=root,
                tdir=tdir,
                thread_id="t",
                cfg=cfg,
                user_text="try to write",
                history=[],
                yes=True,
                verbose=False,
                trace_events=events,
                policy="read-only",
            )

            self.assertEqual(message, "blocked observed")
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 0)
            self.assertIn("read-only policy", events[2]["observation"])

    def test_experiment_run_writes_profile_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parser = gs.build_parser()
            scenario = root / "scenario.md"
            scenario.write_text(
                "# Topic drift scenario\n\n"
                "## First\n"
                "Use memory to re-center Topic Drift.\n\n"
                "## Second\n"
                "Now decide whether a queued note helps.\n",
                encoding="utf-8",
            )
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "llm-config",
                    "local",
                    "--profile",
                    "fake-chat",
                    "--command",
                    f"{sys.executable} -S {Path('scripts/fake_chat_llm.py').resolve()}",
                    "--default",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)

            out_dir = root / "runs" / "scenario"
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "experiment",
                    "run",
                    str(scenario),
                    "--profiles",
                    "fake-chat",
                    "--out-dir",
                    str(out_dir),
                    "--queue-writes",
                    "--yes",
                    "--quiet",
                    "--policy",
                    "active",
                    "--json",
                ]
            )
            out = io.StringIO()
            with redirect_stdout(out):
                args.func(args)

            result = json.loads(out.getvalue())
            self.assertEqual(result["turn_count"], 2)
            self.assertEqual(result["policy"], "active")
            self.assertTrue(Path(result["report_path"]).exists())
            profile = result["profiles"][0]
            self.assertEqual(profile["status"], "ok")
            self.assertTrue(Path(profile["trace_path"]).exists())
            self.assertTrue(Path(profile["report_path"]).exists())


if __name__ == "__main__":
    unittest.main()
