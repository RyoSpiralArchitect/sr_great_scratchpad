from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from great_scratchpad.chat import run_chat_turn
from great_scratchpad.dialogue import call_raw_dialogue_turn, run_dialogue_matrix
from great_scratchpad.semantics import NOTE_FIELDS, analyze_dialogue_semantics
from great_scratchpad.storage import ensure_thread_dirs


class VisibleHistoryTests(unittest.TestCase):
    def test_chat_centerline_cannot_restore_evicted_or_partially_clipped_text(self) -> None:
        histories = [
            [{"role": "user", "content": "EVICTED_SAFFRON_DIRECTIVE"},
             {"role": "assistant", "content": "padding " * 100 + "VISIBLE_TAIL"}],
            [{"role": "user", "content": "EVICTED_SAFFRON_DIRECTIVE " + "padding " * 100 + "VISIBLE_TAIL"}],
        ]
        for history in histories:
            for budget in (0, 80):
                with self.subTest(history=history, budget=budget), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    tdir = ensure_thread_dirs(root, "test")
                    events: list[dict] = []
                    with patch("great_scratchpad.chat.call_llm_result", return_value={
                        "content": '{"type":"final","message":"done"}'
                    }):
                        run_chat_turn(root, tdir, "test", {}, "Continue.", history,
                                      recent_n=0, history_chars=budget, trace_io=True,
                                      trace_events=events, verbose=False)
                    request = next(event for event in events if event["event"] == "model_request")
                    self.assertNotIn("EVICTED_SAFFRON_DIRECTIVE", request["prompt"] + request["system_prompt"])
                    if budget:
                        self.assertIn("VISIBLE_TAIL", request["prompt"])

    def test_plain_centerline_cannot_restore_evicted_correction(self) -> None:
        scenario = {"title": "test", "agenda": "Discuss the material.", "opening": "Begin.", "max_reply_chars": 180}
        records = [
            {"kind": "utterance", "speaker": "B", "message": "EVICTED_SAFFRON_DIRECTIVE"},
            {"kind": "utterance", "speaker": "A", "message": "padding " * 100 + "VISIBLE_TAIL"},
        ]
        with patch("great_scratchpad.dialogue.call_llm_result", return_value={"content": "done"}):
            _, events, _ = call_raw_dialogue_turn({}, scenario, "A", "Continue.", records,
                                                  3, 4, 100, history_chars=80, mode="centerline-only")
        request = next(event for event in events if event["event"] == "model_request")
        self.assertNotIn("EVICTED_SAFFRON_DIRECTIVE", request["prompt"] + request["system_prompt"])
        self.assertIn("VISIBLE_TAIL", request["prompt"])

    def test_dialogue_modes_share_the_exact_bounded_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenario = root / "scenario.json"
            scenario.write_text(json.dumps({
                "id": "shared-history", "title": "test", "agenda": "Discuss the material.",
                "opening": "Begin.", "default_turns": 6,
                "interventions": [{"before_turn": 3, "message": "BOUNDARY_CORRECTION " + "q" * 75}],
            }), encoding="utf-8")
            reply = "A fixed reply with enough text to exercise the moving boundary."
            with patch("great_scratchpad.dialogue.load_llm_config", return_value={"backend": "command"}), \
                 patch("great_scratchpad.dialogue.call_llm_result", return_value={"content": reply}), \
                 patch("great_scratchpad.chat.call_llm_result", return_value={
                     "content": json.dumps({"type": "final", "message": reply})
                 }):
                result = run_dialogue_matrix(
                    root=root / "root", scenario_path=scenario, profile="test", llm_config=None,
                    out_dir=root / "run", conditions=["raw-raw", "centerline-only", "write-no-recall", "scratchpad-scratchpad"],
                    turns=6, replicates=1, turn_output_tokens=100, max_steps=0, recent_n=0,
                    max_tool_chars=1000, json_repair_steps=0, policy="writer", max_api_calls=24,
                    max_suite_output_tokens=2400, quiet=True, history_chars=150,
                )
            by_turn: dict[int, list[str]] = {}
            for session in result["sessions"]:
                events = [json.loads(line) for line in Path(session["trace_path"]).read_text().splitlines()]
                for event in events:
                    if event["event"] != "model_request":
                        continue
                    header = ("Earlier transcript:\n---\n" if session["condition"] in {"raw-raw", "centerline-only"}
                              else "Conversation so far in this runtime:\n---\n")
                    visible = event["prompt"].split(header, 1)[1].split("\n---\n", 1)[0]
                    by_turn.setdefault(event["dialogue_turn"], []).append(visible)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(len(by_turn), 6)
            for turn, windows in by_turn.items():
                with self.subTest(turn=turn):
                    self.assertEqual(len(windows), 4)
                    self.assertEqual(len(set(windows)), 1)
                    self.assertLessEqual(len(windows[0]), 150)


class NoteVisibilityTests(unittest.TestCase):
    def analyze(self, fields: dict, requests: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "sample"
            session.mkdir()
            suite = {"status": "ok", "run_id": "review-test", "scenario": {},
                     "sessions": [{"session_id": "sample", "condition": "scratchpad-scratchpad", "replicate": 1}]}
            (root / "suite_manifest.json").write_text(json.dumps(suite), encoding="utf-8")
            taxonomy = root / "taxonomy.json"
            taxonomy.write_text(json.dumps({
                "id": "visibility-test", "frames": [{"id": "correction", "label": "Correction",
                "prototypes": ["source correction"], "terms": ["correction"]}],
                "targets": [{"id": "probe", "frame_id": "correction", "turn": 3, "source_turn": 1}],
            }), encoding="utf-8")
            events = [
                {"event": "model_output", "dialogue_turn": 1, "speaker": "A",
                 "payload": {"action": "scratchpad.add_note", **fields}},
                {"event": "tool_observation", "dialogue_turn": 1, "speaker": "A",
                 "action": "scratchpad.add_note", "observation": "wrote turn 1"},
                *requests,
            ]
            (session / "trace.jsonl").write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
            (session / "transcript.jsonl").write_text(json.dumps({
                "kind": "utterance", "turn": 3, "speaker": "A", "message": "source correction",
            }), encoding="utf-8")
            return analyze_dialogue_semantics(root, taxonomy)["targets"][0]

    def request(self, prompt: str, **kwargs: object) -> dict:
        return {"event": "model_request", "dialogue_turn": 3, "speaker": "A", "prompt": prompt, **kwargs}

    def test_post_action_visibility_includes_search_recent_and_pack(self) -> None:
        text = "UNIQUE correction about preserved ultraviolet calibration"
        for action in ("scratchpad.search", "scratchpad.recent", "scratchpad.pack"):
            with self.subTest(action=action):
                result = self.analyze({"text": text}, [
                    self.request("No saved memory in the first request."),
                    {"event": "tool_observation", "dialogue_turn": 3, "speaker": "A", "action": action, "observation": text},
                    self.request(f"Tool observations so far:\n{action}\n{text}"),
                ])
                self.assertTrue(result["note_visible"])
                self.assertEqual(result["note_prompt_request_count"], 2)
                self.assertEqual(result["note_prompt_best_request"], 2)

    def test_every_annotation_field_can_establish_visibility(self) -> None:
        for field in NOTE_FIELDS:
            with self.subTest(field=field):
                text = "Distinct correction about ultraviolet calibration of local channels"
                result = self.analyze({field: text}, [self.request(f"## {field}\n{text}")])
                self.assertTrue(result["note_visible"])

    def test_generic_raw_text_does_not_hide_missing_annotation(self) -> None:
        result = self.analyze({"text": "OK", "anchors": "UNSEEN ultraviolet calibration must use independent local channels"},
                              [self.request("OK")])
        self.assertFalse(result["note_visible"])

    def test_other_turn_speaker_and_unconsumed_observation_do_not_count(self) -> None:
        text = "UNIQUE correction about ultraviolet calibration of local channels"
        result = self.analyze({"text": text}, [
            self.request(text, dialogue_turn=2),
            self.request(text, speaker="B"),
            self.request("No memory here."),
            {"event": "tool_observation", "dialogue_turn": 3, "speaker": "A", "observation": text},
        ])
        self.assertFalse(result["note_visible"])

    def test_system_prompt_also_counts_as_provider_visible(self) -> None:
        text = "UNIQUE correction about ultraviolet calibration of local channels"
        result = self.analyze({"text": text}, [self.request("Current request.", system_prompt=text)])
        self.assertTrue(result["note_visible"])

    def test_no_requests_remain_invisible(self) -> None:
        result = self.analyze({"text": "UNIQUE correction"}, [])
        self.assertFalse(result["note_visible"])

    def test_separate_partial_requests_are_not_a_synthetic_complete_note(self) -> None:
        left = "01234567890123456789012345"
        right = "abcdefghijklmnopqrstuvwxyz"
        result = self.analyze({"text": left + right}, [self.request(left), self.request(right)])
        self.assertFalse(result["note_visible"])
        self.assertEqual(result["note_prompt_request_count"], 2)
        self.assertEqual(result["note_prompt_containment"], max(result["note_prompt_request_containments"]))


if __name__ == "__main__":
    unittest.main()
