from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
