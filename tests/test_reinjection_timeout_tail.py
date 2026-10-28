from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_reinjection_continuation as fixtures
from great_scratchpad import reinjection_continuation as previous
from great_scratchpad.reinjection_timeout_tail import assessment, audit, client_receipt, load, prepare, run


class TimeoutTailTests(unittest.TestCase):
    def parent(self, base):
        source, old = fixtures.ContinuationTests().source(base)
        parent = base / "parent"
        env = previous.prepare(source, old["plan_sha256"], parent, 167, 100200)
        with patch("great_scratchpad.reinjection_continuation.call_llm_result", side_effect=TimeoutError("The read operation timed out")):
            result = previous.run(parent, env["plan_sha256"], fixtures.CONFIG)
        self.assertEqual(result["attempted_calls"], 2)
        self.assertEqual(result["status"], "error")
        return parent, env

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_timed_out_cell_is_never_repeated_and_unknown_usage_stays_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            parent, old = self.parent(base)
            before = (parent / "pilot/responses.jsonl").read_bytes()
            before_result = (parent / "pilot/result.json").read_bytes()
            directory = base / "tail"
            env = prepare(parent, old["plan_sha256"], directory, 166, 99600)
            with patch("great_scratchpad.reinjection_timeout_tail.call_llm_result", return_value=fixtures.response('{"value":null,"evidence":[]}')) as call:
                result = run(directory, env["plan_sha256"], fixtures.CONFIG)
            self.assertEqual(call.call_count, 166)
            self.assertEqual(result["attempted_calls"], 168)
            self.assertEqual(result["unavailable_usage_calls"], 1)
            self.assertEqual(result["known_usage"]["total_tokens"], 167 * 15)
            self.assertEqual(result["cells"][1]["assessment"]["resource_failure"], "client_error")
            self.assertFalse(result["cells"][1]["assessment"]["grounded_success"])
            self.assertTrue((directory / "pilot/responses.jsonl").read_bytes().startswith(before))
            self.assertEqual((parent / "pilot/result.json").read_bytes(), before_result)
            self.assertEqual(audit(directory, env["plan_sha256"], fixtures.CONFIG), result)
            with self.assertRaises(FileExistsError):
                run(directory, env["plan_sha256"], fixtures.CONFIG)

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_budget_and_parent_tampering_block_before_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            parent, old = self.parent(base)
            directory = base / "tail"
            with self.assertRaises(ValueError):
                prepare(parent, old["plan_sha256"], directory, 165, 99600)
            with self.assertRaises(ValueError):
                prepare(parent, old["plan_sha256"], directory, 166, 99599)
            env = prepare(parent, old["plan_sha256"], directory, 166, 99600)
            with (parent / "pilot/result.json").open("a") as stream:
                stream.write("\n")
            with self.assertRaises(ValueError):
                load(directory, env["plan_sha256"], fixtures.CONFIG)

    @patch.dict("os.environ", {"MISTRAL_API_KEY": "test-secret"})
    def test_later_client_errors_are_kept_without_retries_or_fabricated_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            parent, old = self.parent(base)
            directory = base / "tail"
            env = prepare(parent, old["plan_sha256"], directory, 166, 99600)
            with patch("great_scratchpad.reinjection_timeout_tail.call_llm_result", side_effect=TimeoutError("The read operation timed out")) as call:
                result = run(directory, env["plan_sha256"], fixtures.CONFIG)
            self.assertEqual(call.call_count, 166)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["unavailable_usage_calls"], 167)
            self.assertEqual(result["known_usage"]["total_tokens"], 15)
            self.assertFalse(any(c["assessment"]["grounded_success"] for c in result["cells"]))

    def test_client_failure_cannot_carry_fabricated_model_text(self):
        cell = {"id": "case", "prompt_sha256": "digest"}
        receipt = client_receipt(cell, "timeout")
        self.assertFalse(assessment({}, cell, receipt)["grounded_success"])
        receipt["raw_output"] = "invented model answer"
        with self.assertRaises(ValueError):
            assessment({}, cell, receipt)


if __name__ == "__main__":
    unittest.main()
