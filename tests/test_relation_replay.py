from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from great_scratchpad.chat import build_chat_prompt
from great_scratchpad.dialogue import canonical_json_sha256, load_dialogue_memory_fixture, load_dialogue_scenario
from great_scratchpad.memory import add_turn, render_recent_turns, render_retrieved_turns
from great_scratchpad.relation_replay import MEMORY_END, MEMORY_START, prepare_relation_replay, run_relation_replay
from great_scratchpad.relations import load_note_relations, render_memory_with_relations, render_relation, text_sha256
from great_scratchpad.storage import ensure_thread_dirs

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "scenarios/luna_delayed_recall_frozen_notes.json"
RELATIONS = REPO / "scenarios/luna_delayed_recall_relations.json"


class RelationReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_dir = self.root / "relocated-source"
        self.run_dir.mkdir()
        self.scenario = load_dialogue_scenario(REPO / "scenarios/luna_delayed_recall_ablation.json")
        self.scenario = {key: value for key, value in self.scenario.items() if not key.startswith("_")}
        self.fixture = load_dialogue_memory_fixture(FIXTURE)
        self.write_json(self.run_dir / "scenario.snapshot.json", self.scenario)
        self.write_json(self.run_dir / "suite_manifest.json", {
            "status": "ok", "run_id": "source-run", "scenario": self.scenario,
            "scenario_sha256": canonical_json_sha256(self.scenario),
            "memory_fixture_sha256": self.fixture["_sha256"],
            "sessions": [{"session_id": "source", "status": "ok", "trace_path": "/stale/source/trace.jsonl"}],
        })
        note_root = self.run_dir / "source/scratchpads/speaker-a"
        self.tdir = ensure_thread_dirs(note_root, "source-a")
        for entry in self.fixture["entries"]:
            if entry["source_speaker"] != "A":
                continue
            payload = dict(entry["payload"])
            payload["raw"] = payload.pop("text")
            add_turn(note_root, "source-a", "note", created_at=entry["created_at"], **payload)
        self.query = next(item["message"] for item in self.scenario["interventions"] if item["before_turn"] == 11)
        self.request = {
            "event": "model_request", "dialogue_turn": 11, "mode": "replay-no-recall", "speaker": "A",
            "prompt": build_chat_prompt("source-a", self.query, "(no recent turns)",
                                        [{"role": "user", "content": "FROZEN HISTORY"}], [], "FROZEN HINTS"),
            "system_prompt": "Return one final JSON object.",
        }
        self.trace = self.run_dir / "source/trace.jsonl"
        self.trace.write_text(json.dumps(self.request, ensure_ascii=False) + "\n", encoding="utf-8")
        self.kwargs = dict(root=self.root, run_dir=self.run_dir, session_id="source", probe_turn=11,
                           fixture_path=FIXTURE, relations_path=RELATIONS, profile="test", llm_config=None,
                           out_dir=self.root / "output")
        self.config = {"backend": "openai-compatible", "model": "mistral-large-latest",
                       "base_url": "https://api.mistral.ai/v1", "profile": "test", "api_key": "test-secret"}

    def write_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def prepare(self) -> dict:
        return prepare_relation_replay(self.run_dir, "source", 11, FIXTURE, RELATIONS)

    def test_prompt_isolation_ranks_and_note_identity(self) -> None:
        before = {p.name: p.read_bytes() for p in self.tdir.rglob("*.md")}
        plan = self.prepare()
        self.assertEqual(len(plan["cells"]), 12)
        self.assertEqual(plan["ranked_notes"][1]["sha256"], self.fixture["entries"][0]["source_note_sha256"])
        outside = set()
        for visibility in ("none", "top1", "top2", "full-at-probe"):
            cells = [cell for cell in plan["cells"] if cell["visibility"] == visibility]
            self.assertEqual(len({json.dumps(cell["selected_notes"]) for cell in cells}), 1)
            self.assertEqual(len({cell["prompt_sha256"] for cell in cells}), 1 if visibility in {"none", "top1"} else 3)
            for cell in cells:
                prefix, rest = cell["prompt"].split(MEMORY_START)
                _, suffix = rest.split(MEMORY_END)
                outside.add(prefix + suffix)
                self.assertIn("FROZEN HISTORY", suffix)
                self.assertIn(self.query, suffix)
        self.assertEqual(len(outside), 1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.tdir.rglob("*.md")})

    def test_renderings_preserve_values_uncertainty_and_default(self) -> None:
        relations = load_note_relations(RELATIONS, self.fixture, self.scenario)
        annotation = next(iter(relations["_by_hash"].values()))
        for rendering in ("prose", "roles"):
            text = render_relation(annotation, rendering)
            for role in ("before_state", "after_state", "comparison_boundary"):
                self.assertIn(annotation[role]["value"], text)
            self.assertIn("unverified", text)
        default = render_recent_turns(self.tdir)
        self.assertEqual(default, render_recent_turns(self.tdir, relations=relations["_by_hash"]))
        original, sources = render_retrieved_turns(self.tdir, self.query, 2)
        rendered, new_sources = render_retrieved_turns(self.tdir, self.query, 2, relations=relations["_by_hash"], rendering="roles")
        self.assertNotIn("before_state", original)
        self.assertIn("before_state", rendered)
        self.assertEqual([s["path"] for s in sources], [s["path"] for s in new_sources])

    def test_relation_overflow_fails_without_silent_truncation(self) -> None:
        relations = load_note_relations(RELATIONS, self.fixture, self.scenario)
        source = (self.tdir / "turns/000001-note.md").read_text(encoding="utf-8")
        for rendering in ("prose", "roles"):
            with self.assertRaisesRegex(ValueError, "display budget"):
                render_memory_with_relations(source, source, 20, relations["_by_hash"], rendering)
        with self.assertRaises(ValueError):
            render_memory_with_relations(source, source, 1000, rendering="unknown")

    def test_annotations_reject_invalid_hash_quote_future_and_adoption(self) -> None:
        base = json.loads(RELATIONS.read_text(encoding="utf-8"))
        cases = []
        for field in ("fixture_sha256", "scenario_sha256"):
            data = copy.deepcopy(base)
            data[field] = "0" * 64
            cases.append(data)
        for field, value in (("note_sha256", "0" * 64), ("prior_adoption", "confirmed"), ("before_status", "adopted")):
            data = copy.deepcopy(base)
            data["annotations"][0][field] = value
            cases.append(data)
        for change in ({"quote": "invented"}, {"entry_id": "turn-09-centers-separated"},
                       {"kind": "scenario", "field": "interventions"}):
            data = copy.deepcopy(base)
            data["annotations"][0]["before_state"]["evidence"].update(change)
            cases.append(data)
        for data in cases:
            with self.subTest(data=data):
                path = self.root / "bad-relations.json"
                self.write_json(path, data)
                with self.assertRaises(SystemExit):
                    load_note_relations(path, self.fixture, self.scenario)

    def test_source_note_tampering_and_future_notes_are_rejected(self) -> None:
        path = self.tdir / "turns/000001-note.md"
        path.write_text(path.read_text(encoding="utf-8") + "changed", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "pre-probe"):
            self.prepare()

    def test_ambiguous_memory_and_non_replay_source_are_rejected(self) -> None:
        for request in ({**self.request, "prompt": self.request["prompt"] + MEMORY_START},
                        {**self.request, "mode": "replay-top2"}):
            self.trace.write_text(json.dumps(request), encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.prepare()

    def test_budget_refusal_precedes_any_calls(self) -> None:
        with patch("great_scratchpad.relation_replay.call_llm_result") as call:
            for overrides in ({"max_api_calls": 11}, {"max_suite_output_tokens": 4799}, {"call_output_tokens": 0}):
                with self.subTest(overrides=overrides), self.assertRaises(SystemExit):
                    run_relation_replay(**self.kwargs, **overrides)
            call.assert_not_called()
        self.assertFalse(self.kwargs["out_dir"].exists())

    def test_dry_run_freezes_all_prompts_without_provider(self) -> None:
        with patch("great_scratchpad.relation_replay.load_llm_config", return_value=self.config), \
             patch("great_scratchpad.relation_replay.call_llm_result") as call:
            result = run_relation_replay(**self.kwargs, dry_run=True)
            call.assert_not_called()
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(len(json.loads((self.kwargs["out_dir"] / "plan.json").read_text())["cells"]), 12)
        self.assertNotIn("test-secret", (self.kwargs["out_dir"] / "result.json").read_text())

    def test_success_freezes_plan_before_calls_and_scores_original_endpoint(self) -> None:
        probe = self.scenario["relation_probes"][0]
        message = (probe["before_markers"][0] + ": " + probe["before_terms"][0] + ". " +
                   probe["after_markers"][0] + ": " + probe["after_terms"][0] + ". " + probe["boundary_terms"][0])

        def respond(cfg: dict, prompt: str, system: str) -> dict:
            plan = json.loads((self.kwargs["out_dir"] / "plan.json").read_text(encoding="utf-8"))
            self.assertIn(prompt, [cell["prompt"] for cell in plan["cells"]])
            self.assertEqual(system, plan["system_prompt"])
            self.assertEqual(cfg["max_tokens"], 400)
            return {"content": json.dumps({"type": "final", "message": message}),
                    "response_model": "resolved-model", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

        with patch("great_scratchpad.relation_replay.load_llm_config", return_value=self.config), \
             patch("great_scratchpad.relation_replay.call_llm_result", side_effect=respond) as call:
            result = run_relation_replay(**self.kwargs)
        self.assertEqual(call.call_count, 12)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["usage"]["completion_tokens"], 60)
        self.assertTrue(all(cell["relation"]["passed"] == 1 for cell in result["cells"]))
        self.assertTrue(all(cell["llm"]["response_model"] == "resolved-model" for cell in result["cells"]))

    def test_bad_output_is_saved_and_stops_without_retry(self) -> None:
        for raw in ("not-json", '{"type":"action","action":"scratchpad.search"}'):
            kwargs = {**self.kwargs, "out_dir": self.root / text_sha256(raw)}
            with patch("great_scratchpad.relation_replay.load_llm_config", return_value=self.config), \
                 patch("great_scratchpad.relation_replay.call_llm_result", return_value={"content": raw}) as call:
                result = run_relation_replay(**kwargs)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["cells"][0]["raw_output"], raw)
            self.assertEqual(result["cells"][1]["status"], "not-run")
            self.assertTrue((kwargs["out_dir"] / "responses.jsonl").exists())

    def test_provider_error_redacts_key_and_counts_attempt(self) -> None:
        with patch("great_scratchpad.relation_replay.load_llm_config", return_value=self.config), \
             patch("great_scratchpad.relation_replay.call_llm_result", side_effect=SystemExit("error test-secret")) as call:
            result = run_relation_replay(**self.kwargs)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["attempted_calls"], 1)
        self.assertEqual(result["cells"][0]["error"], "error [REDACTED]")

    def test_existing_output_is_never_overwritten(self) -> None:
        self.kwargs["out_dir"].mkdir()
        sentinel = self.kwargs["out_dir"] / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with patch("great_scratchpad.relation_replay.load_llm_config", return_value=self.config), \
             patch("great_scratchpad.relation_replay.call_llm_result") as call, self.assertRaises(SystemExit):
            run_relation_replay(**self.kwargs)
        call.assert_not_called()
        self.assertEqual(sentinel.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
