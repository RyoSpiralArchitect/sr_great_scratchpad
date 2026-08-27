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
    def test_chat_history_window_keeps_newest_text(self) -> None:
        history = [
            {"role": "user", "content": "OLD-CORRECTION " + "x" * 80},
            {"role": "assistant", "content": "middle " + "y" * 80},
            {"role": "user", "content": "LATEST-PROBE"},
        ]

        rendered = gs.chat_history_text(history, max_chars=90)

        self.assertNotIn("OLD-CORRECTION", rendered)
        self.assertIn("LATEST-PROBE", rendered)
        self.assertIn("earlier history truncated", rendered)

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

    def test_parse_section_accepts_compact_block_headings(self) -> None:
        md = (
            "# Block\n"
            "#### Center pin\n"
            "中心軸\n"
            "#### Trajectory\n"
            "軌道\n"
            "#### Anchors\n"
            "Topic Drift\n"
        )

        self.assertEqual(gs.parse_section(md, "Center pin"), "中心軸")
        self.assertEqual(gs.parse_section(md, "Trajectory"), "軌道")

    def test_annotation_prompt_preserves_roomy_scaffold_intent(self) -> None:
        prompt = gs.build_annotation_prompt("Semantic Compression causes Topic Drift.")

        self.assertIn("This is not a summary task.", prompt)
        self.assertIn("roomy self-scaffold note", prompt)
        self.assertIn("do not over-compress", prompt)

    def test_add_turn_prioritizes_annotation_keys_before_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gs.ensure_thread_dirs(root, "t")
            raw = ", ".join(f"raw-fragment-{i}" for i in range(30))
            _, path = gs.add_turn(
                root=root,
                thread_id="t",
                speaker="user",
                raw=raw,
                center="Great Scratchpad key priority",
                trajectory="Use annotation fields as retrieval signposts",
                anchors="Semantic Compression, Topic Drift",
            )

            keys = [
                key.strip()
                for key in gs.parse_section(path.read_text(encoding="utf-8"), "Retrieval keys").split(",")
            ]
            self.assertEqual(keys[:2], ["Semantic Compression", "Topic Drift"])

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
            " print('x' * 80)\n"
        )
        cfg = {
            "backend": "command",
            "command": [sys.executable, "-S", "-c", code],
            "timeout": 5,
        }

        annotation = gs.draft_annotation("raw", cfg, json_repair_steps=1)
        self.assertEqual(annotation["center"], "c")

    def test_json_parser_recovers_first_of_multiple_complete_objects(self) -> None:
        first, metadata = gs.extract_json_object_with_metadata(
            '{"type":"action","action":"scratchpad.recent"}\n'
            '{"type":"final","message":"too early"}'
        )

        self.assertEqual(first["type"], "action")
        self.assertTrue(metadata["recovered"])
        self.assertGreater(metadata["trailing_chars"], 0)
        self.assertEqual(metadata["trailing_object"]["type"], "final")

    def test_chat_traces_multiple_json_object_recovery(self) -> None:
        code = (
            "import json,sys\n"
            "p=sys.stdin.read()\n"
            "if 'Action 1: scratchpad.recent' in p:\n"
            " print(json.dumps({'type':'final','message':'after observation'}))\n"
            "else:\n"
            " print(json.dumps({'type':'action','action':'scratchpad.recent','n':1}))\n"
            " print(json.dumps({'type':'final','message':'too early'}))\n"
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
                user_text="recover two objects",
                history=[],
                max_steps=1,
                verbose=False,
                trace_events=events,
            )

            self.assertEqual(message, "after observation")
            recovery = next(event for event in events if event["event"] == "json_protocol_recovery")
            self.assertGreater(recovery["trailing_chars"], 0)

    def test_chat_uses_buffered_final_after_successful_add_note(self) -> None:
        code = (
            "import json\n"
            "print(json.dumps({'type':'action','action':'scratchpad.add_note','text':'keep this'}))\n"
            "print(json.dumps({'type':'final','message':'buffered final'}))\n"
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
                user_text="write then answer",
                history=[],
                max_steps=1,
                yes=True,
                verbose=False,
                trace_events=events,
            )

            self.assertEqual(message, "buffered final")
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 1)
            final = next(event for event in events if event["event"] == "final")
            self.assertEqual(final["model_calls"], 1)
            self.assertIn("buffered_final_used", [event["event"] for event in events])

    def test_chat_recovers_duplicate_add_note_after_successful_write(self) -> None:
        code = (
            "import json,sys\n"
            "p=sys.stdin.read()\n"
            "if 'Duplicate action request' in p:\n"
            " print(json.dumps({'type':'final','message':'final after duplicate'}))\n"
            "elif 'Action 1: scratchpad.add_note' in p:\n"
            " print(json.dumps({'type':'action','action':'scratchpad.add_note','text':'duplicate'}))\n"
            "else:\n"
            " print(json.dumps({'type':'action','action':'scratchpad.add_note','text':'first'}))\n"
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
                user_text="write once then answer",
                history=[],
                max_steps=1,
                max_model_calls=3,
                yes=True,
                verbose=False,
                trace_events=events,
            )

            self.assertEqual(message, "final after duplicate")
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 1)
            duplicate = next(
                event
                for event in events
                if event["event"] == "tool_observation" and event.get("duplicate_request")
            )
            self.assertEqual(duplicate["tool_step"], 1)
            final = next(event for event in events if event["event"] == "final")
            self.assertEqual(final["model_calls"], 3)
            self.assertEqual(final["tool_steps"], 1)

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
                output_token_budget=20,
                max_model_calls=2,
                per_call_output_token_limit=20,
            )

            self.assertEqual(message, "repaired final")
            self.assertIn("json_parse_error", [event["event"] for event in events])
            self.assertEqual(events[-1]["repair_attempts"], 1)
            self.assertGreater(events[-1]["repair_output_tokens_used"], 0)
            self.assertLessEqual(events[-1]["output_tokens_used"], 20)

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

    def test_chat_allows_only_one_add_note_per_turn(self) -> None:
        code = (
            "import json,sys\n"
            "p=sys.stdin.read()\n"
            "if 'a memory write was already handled' in p:\n"
            " print(json.dumps({'type':'final','message':'done'}))\n"
            "else:\n"
            " print(json.dumps({'type':'action','action':'scratchpad.add_note','text':'repeat note'}))\n"
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
                user_text="write once",
                history=[],
                yes=True,
                queue_writes=True,
                verbose=False,
                trace_events=events,
            )

            self.assertEqual(message, "done")
            self.assertEqual(len(gs.iter_review_items(root, "t")), 1)
            observations = [
                event["observation"]
                for event in events
                if event["event"] == "tool_observation"
            ]
            self.assertIn("queued for review", observations[0])
            self.assertIn("already handled", observations[1])

    def test_chat_injects_centerline_hints_and_traces_them(self) -> None:
        code = (
            "import json,sys\n"
            "p=sys.stdin.read()\n"
            "seen = 'Centerline hints:' in p and 'should_checkpoint: True' in p\n"
            "msg = 'checkpoint seen' if seen else 'missing checkpoint'\n"
            "print(json.dumps({'type':'final','message':msg}))\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            cfg = {
                "backend": "command",
                "command": [sys.executable, "-S", "-c", code],
                "timeout": 5,
            }
            history = [
                {"role": "user", "content": "クラゲの神経叢は分散型なの？"},
                {"role": "assistant", "content": "脳ではなく神経叢で反応します。"},
                {"role": "user", "content": "そういえば味噌も地域に分散しているね。"},
                {"role": "assistant", "content": "地域ごとに違いがあります。"},
            ]
            events: list[dict] = []

            message = gs.run_chat_turn(
                root=root,
                tdir=tdir,
                thread_id="t",
                cfg=cfg,
                user_text="てことは結局なんなんだろう？",
                history=history,
                verbose=False,
                trace_events=events,
            )

            self.assertEqual(message, "checkpoint seen")
            centerline = next(event for event in events if event["event"] == "centerline")
            self.assertIn("checkpoint", centerline["flags"])
            self.assertTrue(centerline["should_checkpoint"])
            self.assertTrue(centerline["should_queue_note"])
            self.assertIn("distributed systems / analogy fit", centerline["active_centers"])

    def test_centerline_marks_ambiguous_short_question(self) -> None:
        analysis = gs.analyze_centerline(
            "あんかけは？",
            [
                {"role": "user", "content": "モーニングの発祥は名古屋ではないそうだね？"},
                {"role": "assistant", "content": "発祥には諸説あります。"},
            ],
        )

        self.assertIn("ambiguous_short_question", analysis["flags"])
        self.assertTrue(analysis["should_clarify"])
        self.assertFalse(analysis["should_checkpoint"])

    def test_centerline_distinguishes_explanation_from_explicit_control_cues(self) -> None:
        explanation = gs.analyze_centerline(
            "つまり個体内の局所回路が協調するということです。",
            [],
        )
        correction = gs.analyze_centerline(
            "補正する。種間差ではなく個体内差を問う。",
            [],
        )
        detour = gs.analyze_centerline(
            "ここで関連する脱線を入れる。発祥について考えよう。",
            [],
        )
        checkpoint = gs.analyze_centerline(
            "チェックポイント。結局ここまでで何が分かった？",
            [],
        )

        self.assertNotIn("checkpoint", explanation["flags"])
        self.assertIn("correction", correction["flags"])
        self.assertTrue(correction["should_queue_note"])
        self.assertIn("center_shift", detour["flags"])
        self.assertTrue(detour["should_queue_note"])
        self.assertIn("checkpoint", checkpoint["flags"])

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

    def test_openai_auto_adapter_uses_responses_for_gpt_5_6(self) -> None:
        requests: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                requests.append({"path": self.path, "body": body})
                content = json.dumps({"type": "final", "message": "responses final"})
                payload = {
                    "id": "resp_fake",
                    "model": "gpt-5.6-luna",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": content}],
                        }
                    ],
                    "usage": {"input_tokens": 11, "output_tokens": 5, "total_tokens": 16},
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
                    "backend": "openai",
                    "adapter": "auto",
                    "profile": "openai-5.6-luna",
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "model": "gpt-5.6-luna",
                    "max_output_tokens": 321,
                    "top_p": 0.8,
                    "seed": 99,
                    "stop": ["STOP"],
                    "json_mode": "json_object",
                    "reasoning_effort": "low",
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

                self.assertEqual(message, "responses final")
                self.assertEqual(requests[0]["path"], "/v1/responses")
                body = requests[0]["body"]
                self.assertEqual(body["model"], "gpt-5.6-luna")
                self.assertEqual(body["max_output_tokens"], 321)
                self.assertEqual(body["top_p"], 0.8)
                self.assertEqual(body["seed"], 99)
                self.assertEqual(body["stop"], ["STOP"])
                self.assertEqual(body["text"], {"format": {"type": "json_object"}})
                self.assertEqual(body["reasoning"], {"effort": "low"})
                model_event = next(event for event in events if event["event"] == "model_output")
                self.assertEqual(model_event["llm"]["adapter"], "openai-responses")
                self.assertEqual(model_event["llm"]["usage"]["prompt_tokens"], 11)
                self.assertEqual(model_event["llm"]["usage"]["completion_tokens"], 5)
                self.assertEqual(model_event["llm"]["usage"]["total_tokens"], 16)
        finally:
            server.shutdown()
            server.server_close()

    def test_chat_pools_output_budget_across_internal_model_calls(self) -> None:
        requests: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                requests.append(body)
                if len(requests) == 1:
                    content = json.dumps(
                        {
                            "type": "action",
                            "action": "scratchpad.add_note",
                            "text": "budgeted note",
                        }
                    )
                    output_tokens = 12
                else:
                    content = json.dumps({"type": "final", "message": "budgeted final"})
                    output_tokens = 8
                payload = {
                    "id": f"resp_{len(requests)}",
                    "model": "gpt-5.6-luna",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": content}],
                        }
                    ],
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": output_tokens,
                        "total_tokens": 10 + output_tokens,
                    },
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
                    "backend": "openai",
                    "adapter": "auto",
                    "profile": "budget-test",
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "model": "gpt-5.6-luna",
                    "max_output_tokens": 321,
                    "json_mode": "json_object",
                    "timeout": 5,
                }
                events: list[dict] = []

                message = gs.run_chat_turn(
                    root=root,
                    tdir=tdir,
                    thread_id="t",
                    cfg=cfg,
                    user_text="remember within budget",
                    history=[],
                    max_steps=1,
                    yes=True,
                    verbose=False,
                    trace_events=events,
                    json_repair_steps=0,
                    output_token_budget=40,
                    max_model_calls=2,
                    per_call_output_token_limit=25,
                )

                self.assertEqual(message, "budgeted final")
                self.assertEqual([item["max_output_tokens"] for item in requests], [25, 25])
                final = next(event for event in events if event["event"] == "final")
                self.assertEqual(final["output_token_budget"], 40)
                self.assertEqual(final["output_tokens_used"], 20)
        finally:
            server.shutdown()
            server.server_close()

    def test_provider_auto_adapter_keeps_legacy_chat_by_default(self) -> None:
        self.assertEqual(
            gs.resolve_llm_adapter({"backend": "openai-compatible", "model": "gpt-5.6-luna"}),
            "openai-chat-completions",
        )
        self.assertEqual(
            gs.resolve_llm_adapter({"backend": "openai-compatible", "adapter": "auto", "model": "gpt-5.6-luna"}),
            "openai-responses",
        )
        self.assertEqual(
            gs.endpoint_url({"base_url": "https://api.example.com/v1/chat/completions"}, "responses"),
            "https://api.example.com/v1/responses",
        )

    def test_openai_config_cli_writes_auto_responses_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parser = gs.build_parser()
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "llm-config",
                    "openai",
                    "--profile",
                    "openai-5.6-terra",
                    "--model",
                    "gpt-5.6-terra",
                    "--reasoning-effort",
                    "high",
                    "--default",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)

            cfg = gs.load_llm_config(root, None, "openai-5.6-terra")
            self.assertEqual(cfg["backend"], "openai")
            self.assertEqual(cfg["adapter"], "auto")
            self.assertEqual(cfg["api_key_env"], "OPENAI_API_KEY")
            self.assertEqual(cfg["model"], "gpt-5.6-terra")
            self.assertEqual(cfg["reasoning_effort"], "high")
            self.assertEqual(gs.resolve_llm_adapter(cfg), "openai-responses")

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
            queued_item = json.loads(items[0][0].read_text(encoding="utf-8"))
            self.assertEqual(queued_item["source"]["kind"], "chat_runtime")
            self.assertEqual(queued_item["source"]["user_text"], "queue write")
            self.assertEqual(len(queued_item["source"]["observations"]), 1)
            self.assertIn("scratchpad.search", queued_item["source"]["observations"][0])
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
            self.assertEqual(data["add_note_actions"], 1)
            self.assertEqual(data["durable_writes"], 0)
            self.assertEqual(data["queued_writes"], 1)
            self.assertIn("scratchpad.search", report)
            self.assertIn("Add-note actions: 1", report)
            self.assertIn("Durable writes: 0", report)
            self.assertIn("Queued writes: 1", report)
            self.assertIn('"event": "model_output"', gs.trace_show(loaded, line=2))

    def test_trace_centerline_report_handles_legacy_trace(self) -> None:
        events = [
            {"event": "turn_start", "run_id": "r", "user_text": "クラゲは脳みそがないの？"},
            {"event": "final", "run_id": "r", "message": "神経叢があります。", "tool_steps": 0},
            {"event": "turn_start", "run_id": "r", "user_text": "そういえば味噌も分散しているね。"},
            {"event": "final", "run_id": "r", "message": "地域ごとの差があります。", "tool_steps": 0},
            {"event": "turn_start", "run_id": "r", "user_text": "あんかけは？"},
            {"event": "final", "run_id": "r", "message": "とろみのあるあんです。", "tool_steps": 0},
            {"event": "turn_start", "run_id": "r", "user_text": "てことは結局なんなんだろう？"},
            {"event": "final", "run_id": "r", "message": "まとめです。", "tool_steps": 0},
        ]

        data = gs.trace_report_data(events)
        report = gs.trace_report_markdown(events)
        centerline = gs.trace_centerline_markdown(events)

        self.assertEqual(data["centerline_summary"]["turns"], 4)
        self.assertGreaterEqual(data["centerline_summary"]["checkpoints"], 1)
        self.assertIn("## Centerline", report)
        self.assertIn("center_shift", centerline)
        self.assertIn("ambiguous_short_question", centerline)
        self.assertIn("checkpoint", centerline)

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
            self.assertIn("## Source", rendered)
            applied = gs.apply_safe_review_items(root, "t")

            self.assertEqual(len(applied), 1)
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 1)
            self.assertIn("Semantic Compression", applied[0][1].read_text(encoding="utf-8"))

    def test_review_apply_audit_preview_does_not_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            parser = gs.build_parser()
            action = {
                "text": "Topic Drift should stay pending while audit preview only renders.",
                "center": "audit preview",
                "trajectory": "Previewing a queued note should not make memory durable",
                "anchors": "Topic Drift, audit preview",
            }
            item_path = gs.queue_add_note(root, "t", action)

            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "review",
                    "apply",
                    "t",
                    item_path.name,
                    "--audit-preview",
                ]
            )
            out = io.StringIO()
            with redirect_stdout(out):
                args.func(args)

            item = json.loads(item_path.read_text(encoding="utf-8"))
            self.assertIn("## Audit preview", out.getvalue())
            self.assertEqual(item["status"], "pending")
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 0)

    def test_review_apply_safe_only_rejects_unsafe_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = gs.ensure_thread_dirs(root, "t")
            parser = gs.build_parser()
            item_path = gs.queue_add_note(
                root,
                "t",
                {
                    "text": "short",
                    "center": "unsafe item",
                    "trajectory": "thin",
                    "anchors": "unsupported anchor",
                },
            )

            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "review",
                    "apply",
                    "t",
                    item_path.name,
                    "--safe-only",
                ]
            )
            with self.assertRaises(SystemExit):
                args.func(args)

            item = json.loads(item_path.read_text(encoding="utf-8"))
            self.assertEqual(item["status"], "pending")
            self.assertEqual(len(list((tdir / "turns").glob("*.md"))), 0)

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
            tool_event = next(event for event in events if event["event"] == "tool_observation")
            self.assertIn("read-only policy", tool_event["observation"])

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

    def test_dialogue_matrix_runs_mirrored_raw_and_scratchpad_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "scratchpad"
            out_dir = Path(tmp) / "matrix"
            parser = gs.build_parser()
            fake_model = Path("scripts/fake_dialogue_llm.py").resolve()
            scenario = Path("scenarios/luna_centerline_dialogue.json").resolve()
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "llm-config",
                    "local",
                    "--profile",
                    "fake-dialogue",
                    "--command",
                    f"{sys.executable} -S {fake_model}",
                    "--default",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)

            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "experiment",
                    "dialogue",
                    str(scenario),
                    "--profile",
                    "fake-dialogue",
                    "--turns",
                    "4",
                    "--turn-output-tokens",
                    "200",
                    "--max-api-calls",
                    "64",
                    "--max-suite-output-tokens",
                    "5000",
                    "--out-dir",
                    str(out_dir),
                    "--quiet",
                    "--json",
                ]
            )
            out = io.StringIO()
            with redirect_stdout(out):
                args.func(args)
            result = json.loads(out.getvalue())

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["budget_plan"]["sessions"], 4)
            self.assertEqual(result["budget_plan"]["worst_api_calls"], 32)
            self.assertEqual(
                [session["condition"] for session in result["sessions"]],
                ["raw-raw", "raw-scratchpad", "scratchpad-raw", "scratchpad-scratchpad"],
            )
            calls = {session["condition"]: session["model_calls"] for session in result["sessions"]}
            self.assertEqual(calls["raw-raw"], 4)
            self.assertEqual(calls["raw-scratchpad"], 6)
            self.assertEqual(calls["scratchpad-raw"], 6)
            self.assertEqual(calls["scratchpad-scratchpad"], 8)
            self.assertTrue(Path(result["report_path"]).exists())
            mixed = next(
                session for session in result["sessions"] if session["condition"] == "raw-scratchpad"
            )
            self.assertEqual(mixed["memory_writes"], 2)
            self.assertEqual(mixed["memory_context_injections"], 1)
            self.assertEqual(mixed["anchor_coverage"]["count"], 6)
            note_files = list(
                (out_dir / mixed["session_id"] / "scratchpads" / "speaker-b" / "threads").glob(
                    "*/turns/*.md"
                )
            )
            self.assertEqual(len(note_files), 2)
            mirrored = next(
                session for session in result["sessions"] if session["condition"] == "scratchpad-raw"
            )
            mirrored_events = gs.load_trace_events(Path(mirrored["trace_path"]))
            correction = next(
                event
                for event in mirrored_events
                if event["event"] == "centerline" and event["dialogue_turn"] == 3
            )
            self.assertIn("correction", correction["flags"])
            self.assertNotIn("checkpoint", correction["flags"])

    def test_dialogue_preflight_rejects_suite_call_overflow(self) -> None:
        conditions = gs.resolve_dialogue_conditions(None, mirror_mixed=True)
        self.assertEqual(
            conditions,
            ["raw-raw", "raw-scratchpad", "scratchpad-raw", "scratchpad-scratchpad"],
        )
        plan = gs.dialogue_budget_plan(
            conditions,
            turns=8,
            replicates=1,
            turn_output_tokens=480,
            max_steps=1,
            json_repair_steps=1,
        )
        self.assertEqual(plan["worst_api_calls"], 64)
        self.assertEqual(plan["max_output_tokens_suite"], 15360)
        self.assertEqual(plan["scratchpad_output_tokens_per_call"], 320)
        self.assertEqual(plan["scratchpad_final_reserve_tokens"], 160)
        self.assertEqual(plan["max_repair_output_tokens_suite"], 5120)
        self.assertEqual(plan["max_provider_output_tokens_suite"], 20480)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(SystemExit, "worst-case API calls"):
                gs.run_dialogue_matrix(
                    root=Path(tmp) / "root",
                    scenario_path=Path("scenarios/luna_centerline_dialogue.json"),
                    profile="missing-profile",
                    llm_config=None,
                    out_dir=Path(tmp) / "out",
                    conditions=conditions,
                    turns=8,
                    replicates=1,
                    turn_output_tokens=480,
                    max_steps=1,
                    recent_n=4,
                    max_tool_chars=6000,
                    json_repair_steps=1,
                    policy="writer",
                    max_api_calls=63,
                    max_suite_output_tokens=20000,
                    quiet=True,
                )

    def test_dialogue_ablation_separates_centerline_write_and_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "scratchpad"
            out_dir = Path(tmp) / "ablation"
            parser = gs.build_parser()
            fake_model = Path("scripts/fake_ablation_dialogue_llm.py").resolve()
            scenario = Path("scenarios/luna_delayed_recall_ablation.json").resolve()
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "llm-config",
                    "local",
                    "--profile",
                    "fake-ablation",
                    "--command",
                    f"{sys.executable} -S {fake_model}",
                    "--default",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)

            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "experiment",
                    "dialogue",
                    str(scenario),
                    "--profile",
                    "fake-ablation",
                    "--preset",
                    "ablation",
                    "--turns",
                    "12",
                    "--history-chars",
                    "500",
                    "--turn-output-tokens",
                    "200",
                    "--max-api-calls",
                    "96",
                    "--max-suite-output-tokens",
                    "13000",
                    "--out-dir",
                    str(out_dir),
                    "--quiet",
                    "--json",
                ]
            )
            out = io.StringIO()
            with redirect_stdout(out):
                args.func(args)
            result = json.loads(out.getvalue())

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["history_chars"], 500)
            self.assertEqual(
                [session["condition"] for session in result["sessions"]],
                [
                    "raw-raw",
                    "centerline-only",
                    "write-no-recall",
                    "scratchpad-scratchpad",
                ],
            )
            sessions = {session["condition"]: session for session in result["sessions"]}
            self.assertEqual(sessions["raw-raw"]["literal_probe_evidence"]["passed"], 0)
            self.assertEqual(
                sessions["centerline-only"]["literal_probe_evidence"]["passed"], 0
            )
            self.assertEqual(
                sessions["write-no-recall"]["literal_probe_evidence"]["passed"], 0
            )
            self.assertEqual(
                sessions["scratchpad-scratchpad"]["literal_probe_evidence"]["passed"], 2
            )
            self.assertEqual(sessions["write-no-recall"]["memory_writes"], 1)
            self.assertEqual(sessions["write-no-recall"]["memory_context_injections"], 0)
            self.assertEqual(sessions["scratchpad-scratchpad"]["memory_writes"], 1)
            self.assertGreater(
                sessions["scratchpad-scratchpad"]["memory_context_injections"], 0
            )

            write_events = gs.load_trace_events(Path(sessions["write-no-recall"]["trace_path"]))
            full_events = gs.load_trace_events(
                Path(sessions["scratchpad-scratchpad"]["trace_path"])
            )
            raw_events = gs.load_trace_events(Path(sessions["raw-raw"]["trace_path"]))
            write_probe = next(
                event
                for event in write_events
                if event["event"] == "model_request" and event["dialogue_turn"] == 11
            )
            full_probe = next(
                event
                for event in full_events
                if event["event"] == "model_request" and event["dialogue_turn"] == 11
            )
            raw_probe = next(
                event
                for event in raw_events
                if event["event"] == "model_request" and event["dialogue_turn"] == 11
            )
            self.assertNotIn("個体内の異質性を種間差と取り違えない", write_probe["prompt"])
            self.assertIn("個体内の異質性を種間差と取り違えない", full_probe["prompt"])
            self.assertNotIn("重要な補正を置く", raw_probe["prompt"])

            semantic_prefix = Path(tmp) / "semantic" / "analysis"
            semantic = gs.analyze_dialogue_semantics(
                run_dir=out_dir,
                taxonomy_path=Path(
                    "scenarios/luna_delayed_recall_semantic_taxonomy.json"
                ),
                out_prefix=semantic_prefix,
            )
            self.assertEqual(semantic["corpus"]["utterances"], 48)
            self.assertEqual(semantic["corpus"]["notes"], 2)
            targets = {
                item["condition"]: item
                for item in semantic["targets"]
                if item["target_id"] == "delayed-correction-turn-11"
            }
            self.assertFalse(targets["write-no-recall"]["note_visible"])
            self.assertTrue(targets["scratchpad-scratchpad"]["note_visible"])
            self.assertGreater(
                targets["scratchpad-scratchpad"]["frame_score"],
                targets["write-no-recall"]["frame_score"],
            )
            self.assertGreater(semantic["contrasts"][0]["frame_score_delta"], 0)
            self.assertEqual(
                semantic["contrasts"][0]["frame_score_delta_bootstrap_ci"]["lower"],
                semantic["contrasts"][0]["frame_score_delta"],
            )
            self.assertEqual(
                semantic["contrasts"][0]["literal_session_outcomes"]["treatment_only"],
                1,
            )
            self.assertEqual(
                semantic["contrasts"][0]["literal_item_outcomes"]["treatment_only"],
                2,
            )
            first_json = semantic_prefix.with_suffix(".json").read_bytes()
            gs.analyze_dialogue_semantics(
                run_dir=out_dir,
                taxonomy_path=Path(
                    "scenarios/luna_delayed_recall_semantic_taxonomy.json"
                ),
                out_prefix=semantic_prefix,
            )
            self.assertEqual(first_json, semantic_prefix.with_suffix(".json").read_bytes())
            self.assertTrue(semantic_prefix.with_suffix(".md").exists())

    def test_dialogue_counterbalances_starter_and_condition_order(self) -> None:
        plan = gs.dialogue_budget_plan(
            ["raw-scratchpad"],
            turns=3,
            replicates=2,
            turn_output_tokens=100,
            max_steps=1,
            json_repair_steps=1,
            alternate_starter=True,
            rotate_condition_order=True,
        )
        self.assertEqual(plan["mode_turns"]["raw"], 3)
        self.assertEqual(plan["mode_turns"]["scratchpad"], 3)
        self.assertEqual(plan["worst_api_calls"], 12)
        self.assertEqual(
            plan["condition_orders"],
            [
                {"replicate": 1, "conditions": ["raw-scratchpad"]},
                {"replicate": 2, "conditions": ["raw-scratchpad"]},
            ],
        )

        four_way = gs.dialogue_budget_plan(
            ["raw-raw", "centerline-only", "write-no-recall", "scratchpad-scratchpad"],
            turns=2,
            replicates=4,
            turn_output_tokens=100,
            max_steps=1,
            json_repair_steps=1,
            rotate_condition_order=True,
        )
        self.assertEqual(
            [item["conditions"][0] for item in four_way["condition_orders"]],
            ["raw-raw", "centerline-only", "write-no-recall", "scratchpad-scratchpad"],
        )
        for position in range(4):
            self.assertEqual(
                {item["conditions"][position] for item in four_way["condition_orders"]},
                {"raw-raw", "centerline-only", "write-no-recall", "scratchpad-scratchpad"},
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "scratchpad"
            out_dir = Path(tmp) / "parity"
            parser = gs.build_parser()
            fake_model = Path("scripts/fake_ablation_dialogue_llm.py").resolve()
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "llm-config",
                    "local",
                    "--profile",
                    "fake-parity",
                    "--command",
                    f"{sys.executable} -S {fake_model}",
                    "--default",
                ]
            )
            with redirect_stdout(io.StringIO()):
                args.func(args)
            args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "experiment",
                    "dialogue",
                    "scenarios/luna_delayed_recall_ablation.json",
                    "--profile",
                    "fake-parity",
                    "--conditions",
                    "raw,centerline",
                    "--turns",
                    "2",
                    "--replicates",
                    "2",
                    "--alternate-starter",
                    "--rotate-condition-order",
                    "--turn-output-tokens",
                    "100",
                    "--max-api-calls",
                    "8",
                    "--max-suite-output-tokens",
                    "800",
                    "--out-dir",
                    str(out_dir),
                    "--quiet",
                    "--json",
                ]
            )
            out = io.StringIO()
            with redirect_stdout(out):
                args.func(args)
            result = json.loads(out.getvalue())

            self.assertEqual(len(result["dialogue_runner_sha256"]), 64)
            self.assertEqual(
                [session["condition"] for session in result["sessions"]],
                ["raw-raw", "centerline-only", "centerline-only", "raw-raw"],
            )
            self.assertEqual(
                [session["condition_position"] for session in result["sessions"]],
                [1, 2, 1, 2],
            )
            self.assertEqual(
                [session["starting_speaker"] for session in result["sessions"]],
                ["A", "A", "B", "B"],
            )


if __name__ == "__main__":
    unittest.main()
