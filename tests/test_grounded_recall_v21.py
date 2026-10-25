from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from great_scratchpad import grounded_recall as v2
from great_scratchpad import grounded_recall_v21 as v21
from tests.test_grounded_recall import CONFIGS, REPO

CASES = REPO / "scenarios" / "grounded_recall_v21_cases.json"


class ClarifiedContractTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads(CASES.read_text())

    def test_original_assessor_source_is_byte_unchanged(self):
        source = inspect.getsource(v2.assess_answer).rstrip().encode()
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         "a467293b862fe354d94a9899f160953349c7d4791dfe9d33ce31cfdd850169f5")

    def test_fresh_calibration_and_identical_unqueried_confirmation(self):
        old = json.loads((REPO / "scenarios" / "grounded_recall_v2_cases.json").read_text())
        self.assertEqual([c for c in old["cases"] if c["stage"] == "confirmation"],
                         [c for c in self.suite["cases"] if c["stage"] == "confirmation"])
        self.assertFalse({c["id"] for c in old["cases"] if c["stage"] == "calibration"}
                         & {c["id"] for c in self.suite["cases"] if c["stage"] == "calibration"})
        v2.validate_suite(self.suite)

    def test_complete_unavailable_example_and_strict_gate_unchanged(self):
        raw = json.dumps(v21.UNAVAILABLE_EXAMPLE, separators=(",", ":"))
        self.assertIn(raw, v21.SYSTEM)
        self.assertTrue(v2.assess_answer(raw, self.suite["cases"][0], False)["passed"])
        object_null = {**{r: {"value": None, "evidence": []} for r in v2.ROLES},
                       "prior_adoption": {"status": "not_established", "evidence": []}}
        raw = json.dumps(object_null)
        self.assertFalse(v2.assess_answer(raw, self.suite["cases"][0], False)["passed"])
        self.assertTrue(v21.abstention_diagnostic(raw)["explicit_abstention"])

    def test_diagnostic_cannot_excuse_invented_history_extra_prose_or_citations(self):
        result = v21.diagnostic_checks()
        self.assertEqual(result["passed"], result["total"])
        self.assertIsNone(v21.abstention_diagnostic("broken")["explicit_abstention"])
        self.assertIsNone(v21.abstention_diagnostic('{"a":1,"a":2}')["explicit_abstention"])

    def test_gate_and_sampling_are_identical_but_plan_identity_is_not(self):
        old, new = v2.build_plan(self.suite, CONFIGS), v21.build_plan(self.suite, CONFIGS)
        for field in ("configs", "offline", "gate"):
            self.assertEqual(old[field], new[field])
        self.assertEqual([c["prompt"] for c in old["cells"]], [c["prompt"] for c in new["cells"]])
        self.assertNotEqual(old["system_prompt"], new["system_prompt"])
        self.assertNotEqual(v2.canonical_json_sha256(old), v2.canonical_json_sha256(new))
        wrong = deepcopy(self.suite)
        wrong.pop("calibration_contract")
        with self.assertRaises(ValueError):
            v21.build_plan(wrong, CONFIGS)

    def test_end_to_end_new_contract_and_cross_version_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root, run = Path(temp), Path(temp) / "run"
            (root / "llm.json").write_text(json.dumps({"profiles": {c["profile"]: c for c in CONFIGS}}))
            prepared = v2.prepare_grounded_recall(root, CASES, [c["profile"] for c in CONFIGS], run,
                                                 plan_builder=v21.build_plan)
            plan, digest = prepared["plan"], prepared["plan_sha256"]
            with patch("great_scratchpad.grounded_recall.call_llm_result") as call:
                with self.assertRaises(ValueError):
                    v2.run_grounded_recall(root, run, digest, "calibration")
                call.assert_not_called()

            def answer(cfg, prompt, system):
                self.assertEqual(system, v21.SYSTEM)
                cell = next(c for c in plan["cells"] if c["prompt"] == prompt)
                case = next(c for c in plan["suite"]["cases"] if c["id"] == cell["case_id"])
                return {"content": json.dumps(v2.reference_answer(case, cell["condition"] != "none"))}

            with patch.dict("os.environ", {"TEST_LUNA": "fake-key-one", "TEST_MISTRAL": "fake-key-two"}):
                with patch("great_scratchpad.grounded_recall.call_llm_result", side_effect=answer) as call:
                    result = v2.run_grounded_recall(root, run, digest, "calibration", plan_builder=v21.build_plan)
                    self.assertTrue(result["gate_passed"])
                    self.assertEqual(result["method"], v21.METHOD)
                    confirmed = v2.run_grounded_recall(root, run, digest, "confirmation", plan_builder=v21.build_plan)
                    self.assertTrue(confirmed["gate_passed"])
                    self.assertEqual(call.call_count, 48)

    def test_old_failed_cohort_stays_failed_under_original_assessor(self):
        case = self.suite["cases"][0]
        raw = json.dumps({**{r: {"value": None, "evidence": []} for r in v2.ROLES},
                          "prior_adoption": {"status": "not_established", "evidence": []}})
        assessed = v2.assess_answer(raw, case, False)
        plan = {"cells": [{"id": "failed", "condition": "none"}]}
        diagnostic = v21.summarize_diagnostics(plan, [{"id": "failed", "raw_output": raw}], [assessed])
        self.assertFalse(diagnostic["changes_strict_gate"])
        row = diagnostic["rows"][0]
        self.assertFalse(row["strict_passed"])
        self.assertFalse(row["schema_ok"])
        self.assertTrue(row["epistemic_abstention"]["explicit_abstention"])
        self.assertIsNone(row["source_grounding_passed"])
        self.assertEqual(row["recovered_roles"], 0)


if __name__ == "__main__":
    unittest.main()
