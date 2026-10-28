import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from great_scratchpad.reinjection import prepare_reinjection, run_reinjection
from great_scratchpad.reinjection_continuation import (
    audit, load, prepare, received_assessment, run,
)

REPO = Path(__file__).resolve().parents[1]
CONFIG = str(REPO / "examples/mistral-large-4.json")
SPEC = REPO / "scenarios/mistral4_reinjection_v1.json"


def response(raw, reason="stop"):
    return {"content": raw, "response_model": "mistral-large-4", "finish_reason": reason,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


class ContinuationTests(unittest.TestCase):
    def source(self, base):
        directory = base / "source"
        envelope = prepare_reinjection(Path("."), SPEC, CONFIG, "mistral-large-4", directory,
                                       174, 104400, 2000000)
        plan = envelope["plan"]
        cases = {c["id"]: c for c in plan["cases"]}
        outputs = []
        for cell in plan["cells"][:6]:
            truth = cases[cell["case_id"]]["truth"]
            answer = {"value": truth["value"], "evidence": truth["support"]} if cell["condition"] == "source" else {"value": None, "evidence": []}
            outputs.append(response(json.dumps(answer)))
        with patch("great_scratchpad.reinjection.call_llm_result", side_effect=outputs):
            run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG, "calibration")
        with patch("great_scratchpad.reinjection.call_llm_result", return_value=response("", "length")):
            result = run_reinjection(Path("."), directory, envelope["plan_sha256"], CONFIG, "pilot")
        self.assertEqual(result["status"], "error")
        return directory, envelope

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_continuation_keeps_prefix_and_calls_only_unreceived_cells(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, old = self.source(base)
            old_bytes = (source / "pilot/responses.jsonl").read_bytes()
            old_result = (source / "pilot/result.json").read_bytes()
            directory = base / "continuation"
            env = prepare(source, old["plan_sha256"], directory, 167, 100200)
            with patch("great_scratchpad.reinjection_continuation.call_llm_result", return_value=response('{"value":null,"evidence":[]}')) as call:
                result = run(directory, env["plan_sha256"], CONFIG)
            self.assertEqual(call.call_count, 167)
            self.assertEqual(result["attempted_calls"], 168)
            self.assertEqual(result["new_attempted_calls"], 167)
            self.assertEqual(result["cells"][0]["assessment"]["resource_failure"], "output_limit")
            self.assertFalse(result["cells"][0]["assessment"]["grounded_success"])
            self.assertTrue((directory / "pilot/responses.jsonl").read_bytes().startswith(old_bytes))
            self.assertEqual((source / "pilot/responses.jsonl").read_bytes(), old_bytes)
            self.assertEqual((source / "pilot/result.json").read_bytes(), old_result)
            self.assertEqual(audit(directory, env["plan_sha256"], CONFIG), result)
            with self.assertRaises(FileExistsError):
                run(directory, env["plan_sha256"], CONFIG)

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_undersized_budget_or_changed_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, old = self.source(base)
            directory = base / "continuation"
            with self.assertRaises(ValueError):
                prepare(source, old["plan_sha256"], directory, 166, 100200)
            with self.assertRaises(ValueError):
                prepare(source, old["plan_sha256"], directory, 167, 100199)
            self.assertFalse(directory.exists())
            env = prepare(source, old["plan_sha256"], directory, 167, 100200)
            with (source / "pilot/responses.jsonl").open("a") as stream:
                stream.write("\n")
            with self.assertRaises(ValueError):
                load(directory, env["plan_sha256"], CONFIG)

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_missing_received_response_or_runtime_drift_blocks_continuation(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, old = self.source(base)
            with patch("great_scratchpad.reinjection_continuation.runtime_hashes", return_value={}):
                with self.assertRaises(ValueError):
                    prepare(source, old["plan_sha256"], base / "bad-runtime", 167, 100200)
            (source / "pilot/responses.jsonl").write_text("")
            with self.assertRaises(ValueError):
                prepare(source, old["plan_sha256"], base / "missing", 167, 100200)

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_later_length_limits_are_observed_failures_and_do_not_trigger_retries(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, old = self.source(base)
            directory = base / "continuation"
            env = prepare(source, old["plan_sha256"], directory, 167, 100200)
            with patch("great_scratchpad.reinjection_continuation.call_llm_result", return_value=response("", "length")) as call:
                result = run(directory, env["plan_sha256"], CONFIG)
            self.assertEqual(call.call_count, 167)
            self.assertEqual(result["status"], "complete")
            self.assertTrue(all(c["assessment"].get("resource_failure") for c in result["cells"]))
            self.assertFalse(any(c["assessment"]["grounded_success"] for c in result["cells"]))

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_transport_error_still_stops_and_redacts_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, old = self.source(base)
            directory = base / "continuation"
            env = prepare(source, old["plan_sha256"], directory, 167, 100200)
            with patch("great_scratchpad.reinjection_continuation.call_llm_result", side_effect=SystemExit("test-secret HTTP error")) as call:
                result = run(directory, env["plan_sha256"], CONFIG)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(result["status"], "error")
            self.assertNotIn("test-secret", (directory / "pilot/result.json").read_text())

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_valid_json_at_length_limit_cannot_receive_success_credit(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, old = self.source(Path(temporary))
            plan = old["plan"]
            cell = next(c for c in plan["cells"] if c["stage"] == "pilot")
            case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
            answer = {"value": case["truth"]["value"], "evidence": case["truth"]["support"]}
            receipt = {"raw_output": json.dumps(answer), "finish_reason": "length", "llm": {"response_model": "mistral-large-4"}}
            result = received_assessment(plan, cell, receipt)
            self.assertFalse(result["grounded_success"])
            self.assertEqual(result["resource_failure"], "output_limit")


if __name__ == "__main__":
    unittest.main()
