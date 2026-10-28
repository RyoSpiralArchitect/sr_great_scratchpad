from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from great_scratchpad.chat import run_chat_turn
from great_scratchpad.llm import call_openai_compatible_result
from great_scratchpad.memory import memory_identifiers, render_linked_turns, retrieve_linked
from great_scratchpad.memory_task_design import build_conditions, make_case, source_text
from great_scratchpad.reinjection import (
    assess_cell, audit_stage, build_plan, experiment_config, linked_condition,
    load_plan, prepare_reinjection, run_reinjection,
)
from great_scratchpad.storage import ensure_thread_dirs, load_llm_config
from great_scratchpad.text import build_turn_md

REPO = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO / "scenarios/mistral4_reinjection_v1.json"
CONFIG_PATH = str(REPO / "examples/mistral-large-4.json")
SPEC = json.loads(SPEC_PATH.read_text())
CFG = experiment_config(load_llm_config(Path("."), CONFIG_PATH, "mistral-large-4"))


def note(tdir, number, text):
    path = tdir / "turns" / f"{number:06d}-note.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_turn_md(number, "note", text, "", "", "", "", "", "", [], created_at="frozen"))
    return path


class LinkedRecallTests(unittest.TestCase):
    def test_identifier_parser_excludes_citation_and_preserves_order(self):
        self.assertEqual(memory_identifiers("[m001] Request R17 uses T8, then L9; R17 again."), ["r17"])
        self.assertEqual(memory_identifiers("Request R170 uses T80 then L90 then R170."), ["r170", "t80", "l90"])

    def test_multihop_follows_public_links_and_never_crosses_thread(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "thread"
            first = note(archive, 1, "Request R170 uses team T800.")
            second = note(archive, 2, "Team T800 uses line L900.")
            third = note(archive, 3, "Line L900 uses pool P300.")
            note(Path(temporary) / "other", 1, "Request R170 uses BAD999.")
            hits, rounds = retrieve_linked(archive, "Where is R170 routed?", per_hop=1)
            self.assertEqual([p for _, p, _ in hits[:3]], [first, second, third])
            self.assertEqual(len(rounds), 3)
            self.assertFalse(any("BAD999" in t for _, _, t in hits))

    def test_subject_match_beats_incidental_identifier_and_keeps_negation(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            wanted = note(archive, 1, "Request R170 is not approved; hold remains unknown.")
            note(archive, 2, "Request X900 resembles R170 R170 R170; X900 is approved.")
            hits, _ = retrieve_linked(archive, "R170 approved request", top=1)
            self.assertEqual(hits[0][1], wanted)
            context, _, _ = render_linked_turns(archive, "R170", 600)
            self.assertIn("not approved", context)

    def test_whole_note_packing_skips_oversize_and_retains_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            note(archive, 1, "R170 " + "long " * 500)
            selected = note(archive, 2, "R170 requires confirmation.")
            context, sources, _ = render_linked_turns(archive, "R170", 150)
            self.assertLessEqual(len(context), 150)
            self.assertEqual([s["path"] for s in sources], [str(selected.relative_to(archive))])
            self.assertIn("requires confirmation.", context)
            self.assertNotIn("truncated", context)

    def test_no_identifier_uses_lexical_fallback_and_empty_query_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            chosen = note(archive, 1, "compression decision deferred")
            hits, _ = retrieve_linked(archive, "compression decision")
            self.assertEqual(hits[0][1], chosen)
            with self.assertRaises(ValueError):
                retrieve_linked(archive, "")

    def test_excluded_recent_notes_do_not_consume_search_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            hidden = note(archive, 1, "R170 approved OLD900.")
            recent = note(archive, 2, "R170 proposed NEXT900.")
            hits, _ = retrieve_linked(archive, "R170", excluded={recent})
            self.assertEqual([p for _, p, _ in hits], [hidden])

    def test_chat_uses_actual_linked_context_and_traces_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = ensure_thread_dirs(root, "thread")
            note(archive, 1, "R170 requires approval.")
            events = []
            response = {"content": '{"type":"final","message":"ok"}', "usage": {}}
            with patch("great_scratchpad.chat.call_llm_result", return_value=response) as call:
                output = run_chat_turn(root, archive, "thread", {}, "R170?", [],
                                       recall_policy="linked", recall_chars=300,
                                       trace_events=events, verbose=False)
            self.assertEqual(output, "ok")
            self.assertIn("R170 requires approval.", call.call_args.args[1])
            start = next(e for e in events if e["event"] == "turn_start")
            self.assertEqual(start["memory_context_mode"], "linked")
            self.assertEqual(len(start["retrieval_sources"]), 1)
            self.assertTrue(start["retrieval_rounds"])


class ReinjectionPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(SPEC, CFG)

    def prepare(self, directory, **overrides):
        limits = dict(max_calls=174, max_output=104400, max_input_bytes=2000000)
        limits.update(overrides)
        return prepare_reinjection(Path("."), SPEC_PATH, CONFIG_PATH, "mistral-large-4", directory, **limits)

    def test_plan_retains_every_case_arm_and_tier(self):
        self.assertEqual(len(self.plan["cases"]), 27)
        self.assertEqual(len(self.plan["cells"]), 174)
        self.assertEqual(self.plan["budget"]["max_output_tokens"], 104400)
        for tier in (18, 72):
            rows = [c for c in self.plan["cells"] if c.get("archive_distractors") == tier]
            self.assertEqual(len(rows), 84)
            for arm in SPEC["conditions"]:
                self.assertEqual(sum(c["condition"] == arm for c in rows), 12)

    def test_outside_memory_identity_and_whole_record_visibility(self):
        for case in self.plan["cases"]:
            if case["split"] != "pilot":
                continue
            rows = [c for c in self.plan["cells"] if c["case_id"] == case["id"]]
            normal = [c for c in rows if c["condition"] != "full-history"]
            self.assertEqual(len({c["outside_memory_sha256"] for c in normal}), 1)
            self.assertTrue(all(c["context_chars"] <= 1200 for c in normal))
            linked = next(c for c in normal if c["condition"] == "linked-retrieve")
            selected = [r for r in case["records"] if r["id"] in linked["selected_ids"]]
            self.assertTrue(all(source_text(r) in linked["prompt"] for r in selected))

    def test_no_gold_ledger_can_change_linked_selection(self):
        case = make_case(26102899, "distributed-join", "interference", "pilot", 72)
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "archive"
            build_conditions(case, SPEC, archive)
            before = linked_condition(case, SPEC, archive)
            altered = deepcopy(case)
            altered["truth"] = {"value": "FORGED999", "support": []}
            after = linked_condition(altered, SPEC, archive)
            self.assertEqual(before["prompt"], after["prompt"])
            self.assertEqual(before["selected_ids"], after["selected_ids"])
            self.assertNotIn("FORGED999", after["prompt"])

    def test_config_rejects_inline_secrets_latest_and_extra_fields(self):
        for change in ({"api_key": "secret"}, {"model": "mistral-large-latest"}, {"temperature": .2}):
            with self.assertRaises(ValueError):
                experiment_config({**CFG, **change})

    def test_versioned_reasoning_profile_requires_matching_protocol(self):
        spec = json.loads((REPO / "scenarios/mistral4_reinjection_v12.json").read_text())
        high = experiment_config(load_llm_config(Path("."), CONFIG_PATH, "mistral-large-4-high"))
        with self.assertRaises(ValueError):
            build_plan(SPEC, high)
        with self.assertRaises(ValueError):
            build_plan(spec, CFG)
        plan = build_plan(spec, high)
        self.assertEqual(plan["method"], "memory-reinjection-v1.2")
        self.assertEqual(plan["budget"]["max_calls"], 174)
        self.assertEqual(plan["budget"]["max_output_tokens"], 712704)
        with self.assertRaises(ValueError):
            experiment_config({**CFG, "reasoning_effort": "low", "max_tokens": 1200})

    def test_campaign_budget_rejected_before_plan_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            for limits in ({"max_calls": 173}, {"max_output": 104399}, {"max_input_bytes": 1}):
                directory = Path(temporary) / "plan"
                with self.assertRaises(ValueError):
                    self.prepare(directory, **limits)
                self.assertFalse(directory.exists())

    def test_plan_freeze_and_drift_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "plan"
            envelope = self.prepare(directory)
            digest = envelope["plan_sha256"]
            self.assertEqual(load_plan(Path("."), directory, digest, CONFIG_PATH), envelope["plan"])
            with patch("great_scratchpad.reinjection.runtime_hashes", return_value={}):
                with self.assertRaises(ValueError):
                    load_plan(Path("."), directory, digest, CONFIG_PATH)
            with self.assertRaises(FileExistsError):
                self.prepare(directory)
            with self.assertRaises(ValueError):
                load_plan(Path("."), directory, "wrong", CONFIG_PATH)

    def test_failed_calibration_blocks_pilot_from_raw_receipts(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"}):
            directory = Path(temporary) / "plan"
            envelope = self.prepare(directory)
            response = {"content": '{"value":null,"evidence":[]}', "response_model": "mistral-large-4",
                        "finish_reason": "stop", "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}
            with patch("great_scratchpad.reinjection.call_llm_result", return_value=response) as call:
                result = run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG_PATH, "calibration")
                self.assertEqual(call.call_count, 6)
                self.assertFalse(result["gate_passed"])
                with self.assertRaises(ValueError):
                    run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG_PATH, "pilot")
                self.assertEqual(call.call_count, 6)
            self.assertFalse((directory / "pilot").exists())

    def test_calibration_replay_usage_and_tamper_audit(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"}):
            directory = Path(temporary) / "plan"
            envelope = self.prepare(directory)
            plan = envelope["plan"]
            cases = {c["id"]: c for c in plan["cases"]}
            outputs = []
            for c in plan["cells"][:6]:
                truth = cases[c["case_id"]]["truth"]
                answer = {"value": truth["value"], "evidence": truth["support"]} if c["condition"] == "source" else {"value": None, "evidence": []}
                raw = json.dumps(answer)
                self.assertTrue(assess_cell(plan, c, raw)["gate_passed"])
                outputs.append({"content": raw, "response_model": "mistral-large-4", "finish_reason": "stop",
                                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})
            with patch("great_scratchpad.reinjection.call_llm_result", side_effect=outputs):
                result = run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG_PATH, "calibration")
            self.assertTrue(result["gate_passed"])
            self.assertEqual(result["usage"]["total_tokens"], 180)
            path = directory / "calibration" / "responses.jsonl"
            receipts = [json.loads(s) for s in path.read_text().splitlines()]
            receipts[0]["raw_output"] = '{"value":null,"evidence":[]}'
            path.write_text("\n".join(json.dumps(r) for r in receipts) + "\n")
            with self.assertRaises(ValueError):
                audit_stage(plan, envelope["plan_sha256"], directory, "calibration")

    def test_provider_failure_is_preserved_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"}):
            directory = Path(temporary) / "plan"
            envelope = self.prepare(directory)
            with patch("great_scratchpad.reinjection.call_llm_result", side_effect=SystemExit("HTTP error test-secret")) as call:
                result = run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG_PATH, "calibration")
            self.assertEqual(call.call_count, 1)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["attempted_calls"], 1)
            self.assertNotIn("test-secret", (directory / "calibration" / "result.json").read_text())

    def test_unexpected_model_or_truncation_stops_without_substitution(self):
        for change in ({"response_model": "mistral-large-latest"}, {"finish_reason": "length"}):
            with tempfile.TemporaryDirectory() as temporary, patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"}):
                directory = Path(temporary) / "plan"
                envelope = self.prepare(directory)
                response = {"content": "{}", "response_model": "mistral-large-4", "finish_reason": "stop", **change}
                with patch("great_scratchpad.reinjection.call_llm_result", return_value=response) as call:
                    result = run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG_PATH, "calibration")
                self.assertEqual(call.call_count, 1)
                self.assertEqual(result["status"], "error")
                self.assertTrue((directory / "calibration" / "responses.jsonl").exists())

    def test_complete_pilot_keeps_reader_failures_instead_of_filtering_cells(self):
        from great_scratchpad.reinjection import summarize_pilot

        with tempfile.TemporaryDirectory() as temporary, patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"}):
            directory = Path(temporary) / "plan"
            envelope = self.prepare(directory)
            plan = envelope["plan"]
            cases = {c["id"]: c for c in plan["cases"]}
            outputs = []
            for c in plan["cells"]:
                truth = cases[c["case_id"]]["truth"]
                answer = ({"value": truth["value"], "evidence": truth["support"]}
                          if c["stage"] == "calibration" and c["condition"] == "source"
                          else {"value": None, "evidence": []})
                outputs.append({"content": json.dumps(answer), "response_model": "mistral-large-4", "finish_reason": "stop",
                                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
            with patch("great_scratchpad.reinjection.call_llm_result", side_effect=outputs) as call:
                run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG_PATH, "calibration")
                result = run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG_PATH, "pilot")
                self.assertEqual(call.call_count, 174)
            report = summarize_pilot(plan, result)
            self.assertEqual(len(report["conditions"]), 14)
            self.assertTrue(all(row["grounded_success"] == 3 for row in report["conditions"]))
            self.assertTrue(all(row["mean_delta"] == 0 for row in report["contrasts"]))
            with self.assertRaises(FileExistsError):
                run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG_PATH, "pilot")


class MistralWireTests(unittest.TestCase):
    def wire(self, url, content):
        payload = {"model": "mistral-large-4", "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25}}
        with patch("great_scratchpad.llm.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as call:
            result = call_openai_compatible_result({**CFG, "base_url": url, "api_key_env": ""}, "JSON please")
        return result, json.loads(call.call_args.args[0].data)

    def test_mistral_translates_seed_and_preserves_reasoning_parameter(self):
        result, body = self.wire("https://api.mistral.ai/v1", '{"value":null,"evidence":[]}')
        self.assertEqual(body["random_seed"], 261028)
        self.assertNotIn("seed", body)
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(result["finish_reason"], "stop")

    def test_other_provider_keeps_seed_and_does_not_receive_mistral_params(self):
        _, body = self.wire("https://provider.example/v1", "{}")
        self.assertEqual(body["seed"], 261028)
        self.assertNotIn("random_seed", body)
        self.assertNotIn("reasoning_effort", body)

    def test_content_chunks_emit_only_final_text(self):
        result, _ = self.wire("https://api.mistral.ai/v1", [
            {"type": "thinking", "thinking": "internal"}, {"type": "text", "text": "{\"value\":null,"},
            {"type": "text", "text": "\"evidence\":[]}"},
        ])
        self.assertEqual(json.loads(result["content"]), {"value": None, "evidence": []})
        self.assertNotIn("internal", result["content"])


if __name__ == "__main__":
    unittest.main()
